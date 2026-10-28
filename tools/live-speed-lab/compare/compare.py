#!/usr/bin/env python3
"""Consume retained evidence or run the existing isolated #10669 arm helper."""
import argparse
from contextlib import redirect_stdout
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

from score import decide, score
from clock_bracket import eligible_interval


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admission_arm(path, *, stable_backend_clock=False):
    """Adapter for the already executed, predeclared admission bottleneck.

    It certifies no unrecorded stage and invents no full-sample eligibility.
    The 72% witness follows the CONTROL.md's .62 K + .82 PM blend, not an
    arbitrary match on a rounded screen percentage.
    """
    path = Path(path).resolve()
    receipt, source = read(path/"backend-receipt.json"), read(path/"SOURCE.json")
    config, run = read(path/"CONFIG.json"), read(path/"RUN.json")
    bounds, clock = read(path/"sample-boundaries.json"), read(path/"OBSERVATION-SCORE.json")
    cleanup = read(path/"CLEANUP.json")
    if (run["status"] != "READER_COMPLETE" or receipt["errors"]
            or not read(path/"SOURCE-AFTER.json")["unchanged"]
            or not cleanup["stopped"] or cleanup.get("cleanup_errors")
            or clock["status"] != "OBSERVED_CALLBACK_INTERVALS" or clock["faults"]):
        raise ValueError("incomplete, failed, drifting or unclean arm: "+str(path))
    if config["requested"]["preview_sources"] != ["kalshi", "polymarket"]:
        raise ValueError("both DNPL sources must be ON")
    if config["requested"]["fixture"] != "singleton":
        raise ValueError("admission adapter requires the executed singleton fixture")
    rr, = receipt["runs"]
    if rr["kind"] != "admission-publication-stall" or rr["status"] != "inputs-complete":
        raise ValueError("this retained adapter requires the completed admission control")
    inputs = receipt["inputs"]
    target, = [x for x in inputs if x["label"] == "fresh-observation-during-publication"]
    if target["source"] != "polymarket" or target["home_value"] != .82:
        raise ValueError("wrong deciding input")
    trigger, = [x for x in inputs if x["label"] == "publication-trigger"]
    if trigger["source"] != "kalshi" or trigger["home_value"] != .62:
        raise ValueError("wrong companion input")
    start, end = bounds["start_ms"], bounds["end_ms"]
    target_wall, target_mono = rr["target_sent_wall_ms"], rr["target_sent_mono"]
    next_input = min(x["mono"] for x in inputs if x["mono"] > target_mono+.001)
    accepted = next(x for x in receipt["accepted"] if target_mono <= x["mono"] < next_input
                    and x["args"][2] == .82)
    mark = accepted["mark"]
    if "event_id=1" not in mark or "outcome_id=250776126" not in mark:
        raise ValueError("retained input identity differs; use a new explicit adapter")
    truth = [x for x in receipt["truth_checks"] if target_mono <= x["mono"] < next_input
             and x["source"] == "polymarket" and x["value"] == .82 and not x["refused"]]
    if not truth:
        raise ValueError("no selected eligible input witness")
    preview = next(x for x in receipt["previews"] if target_mono <= x["mono"] < next_input
                   and any(f.get("source") == "polymarket" and f.get("value") == .82
                           for f in x["frames"]))
    rows = [json.loads(line) for line in (path/"reader.jsonl").read_text().splitlines()]
    dom = [x for x in rows if x["kind"] == "dom"]
    # Date.now's 1 ms granularity plus the retained recorder's measured mapping
    # uncertainty. No claim that wall stamps are exact physical paint times.
    uncertainty = max(1, clock["clock_mapping"]["edge_uncertainty_ms"])
    received_at = target_wall+(accepted["mono"]-target_mono)*1000-start
    anchor = eligible_interval(target, rr, received_at, uncertainty,
                               stable_backend_clock=stable_backend_clock)
    if anchor["status"] != "conditional_interval":
        raise ValueError("timing_unknown: "+anchor["reason"])
    eligible_at = anchor["at_ms"]
    displays, surface_witness = [], {}
    identity = "pm:250776126:target-0.82+kalshi-0.62"
    def matches(row, surface):
        if row.get("visibility") != "visible":
            return False
        if surface == "headline":
            return row.get("hero") == "0.72"
        # Frozen page axis/endpoint, checked against recorded tick geometry.
        expected_ticks = [("100%", "285"), ("50%", "150"), ("100%", "15")]
        if not all(any((t["text"], t["y"]) == tick for t in row["ticks"]) for tick in expected_ticks):
            raise ValueError("chart geometry changed; explicit adapter update required")
        return any(re.search(r"L296,90\.6(?:0*)$", p["d"]) for p in row.get("paths", []))
    for surface in ("headline", "chart"):
        found = next((i for i, x in enumerate(dom) if x["wall"] >= target_wall
                      and x["wall"] < target_wall+(next_input-target_mono)*1000
                      and matches(x, surface)), None)
        if found is None or found == 0:
            raise ValueError("target display or its preceding sample missing: "+surface)
        row, previous = dom[found], dom[found-1]
        if matches(previous, surface):
            raise ValueError("target already shown; value alone cannot identify delivery")
        bracket = [max(eligible_at[0], previous["wall"]-start-uncertainty),
                   row["wall"]-start+uncertainty]
        displays.append({"surface": surface, "at_ms": bracket, "covers": [identity]})
        surface_witness[surface] = {"row_index": found, "at_ms": bracket,
                                    "observed_iso": row.get("observed"), "hero": row["hero"]}
    stages = {
        "input_sent_ms": target_wall-start,
        "consumer_receipt_ms": received_at,
        "admission_ms": None,
        "eligible_blend_check_ms": (truth[0]["mono"]-target_mono)*1000+target_wall-start,
        "publication_call_ms": (preview["started"]-target_mono)*1000+target_wall-start,
        "publication_return_ms": (preview["mono"]-target_mono)*1000+target_wall-start,
        "client_receipt_ms": None,
        "headline": surface_witness["headline"], "chart": surface_witness["chart"],
        "input_mark": mark,
        "observed_basis": [json.loads(f["payload"]).get("observed_basis") for f in preview["frames"]
                           if f.get("source") == "polymarket" and f.get("payload")],
    }
    trace = {"window_ms": [0, end-start], "eligible": [
        {"id": identity, "stream": "event:1", "at_ms": eligible_at,
         "evidence": "predeclared .72 blend; accepted input mark + nonrefused truth check + preview payload"}],
        "displays": displays, "violations": [],
        "coverage": {"scope": "one predeclared eligible blend state, NOT all venue ticks",
                     "eligible_states_scored": 1, "wire_input_groups": len(inputs),
                     "full_sample_eligibility": False, "clock_uncertainty_ms": uncertainty,
                     "backend_anchor": anchor,
                     "display_resolution": "100ms DOM sampling; not physical paint",
                     "upstream_wait": "not measured; controlled local input",
                     "missing_stages": ["exact admission", "blend computation", "preview_v3 client receipt"]},
        "checks": {"revision_ordering": "not fully measured; source regression controls retained",
                   "expiry": "not measured in this control; source regression controls retained",
                   "observation_clock": clock["correctness_findings"],
                   "headline_chart": "both target endpoints observed; sub-sample differences unknown"}}
    if clock["correctness_findings"]:
        trace["violations"].append("retained recorder correctness finding")
    scorecard = score(trace)
    scorecard["whole_sample_gap"] = clock["longest_wait"]
    scorecard["target_stages"] = stages
    tracked = ["backend-receipt.json", "reader.jsonl", "SOURCE.json", "CONFIG.json", "RUN.json",
               "SOURCE-AFTER.json", "CLEANUP.json", "OBSERVATION-SCORE.json", "sample-boundaries.json"]
    compute = None
    if (path/"COMPARE-COMPUTE.json").exists():
        compute = read(path/"COMPARE-COMPUTE.json")
        tracked.append("COMPARE-COMPUTE.json")
    return {"path": str(path), "source": source, "trace": trace, "score": scorecard,
            "compute": compute,
            "timeline": [{"t": x["wall"]-start, "hero": x["hero"], "paths": x.get("paths", []),
                          "headline": x.get("headline"), "observation": x.get("observedText")}
                         for x in dom if start-200 <= x["wall"] <= end+200],
            "input_identity": [(x["source"], x.get("home_value"), x["label"]) for x in inputs],
            "input_relative_ms": [(x["mono"]-target_mono)*1000 for x in inputs],
            "raw_input_hash": hashlib.sha256(json.dumps([x["frames"] for x in inputs], sort_keys=True).encode()).hexdigest(),
            "initial_values": {k: v["value"] for k, v in receipt["initial_state"]["sources"].items()},
            "publication_hold_ms": (rr["publication_hold_end"]-rr["publication_hold_start"])*1000,
            "hashes": {name: digest(path/name) for name in tracked}}


def consume(spec, out, *, stable_backend_clock=False):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)  # never silently replace a result
    try:
        b, c = [admission_arm(spec[k], stable_backend_clock=stable_backend_clock)
                for k in ("baseline", "candidate")]
        if b["source"]["backend_ref"] != spec["baseline_sha"] or c["source"]["backend_ref"] != spec["candidate_sha"]:
            raise ValueError("source differs from predeclared comparison")
        if b["input_identity"] != c["input_identity"] or b["initial_values"] != c["initial_values"]:
            raise ValueError("input sequence or initial source values differ")
        if b["source"]["frontend_build_source_sha"] != c["source"]["frontend_build_source_sha"]:
            raise ValueError("retained backend comparison used different frontend source")
        decision = decide(b["score"], c["score"])
        result = {"schema": "dnpl-comparison/1", "decision": decision,
                  "decision_scope": "retained admission controlled witness only",
                  "backend_clock_opt_in": stable_backend_clock,
                  "spec": spec, "baseline": b, "candidate": c,
                  "comparability": {
                      "same_ordered_input_identity": True, "same_starting_source_values": True,
                      "literal_wire_timestamp_equality": b["raw_input_hash"] == c["raw_input_hash"],
                      "max_input_schedule_difference_ms": max(abs(x-y) for x, y in zip(b["input_relative_ms"], c["input_relative_ms"])),
                      "compute": ("sequential arms, same host and process layout; per-arm load/CPU snapshots retained"
                                  if b["compute"] and c["compute"] else
                                  "sequential arms, same host and process layout; contemporaneous host-load samples absent"),
                      "limits": ["Historical arms rebased timestamps separately; NOT strict identical timestamped input proof.",
                                 "No rerun purchased to retrofit telemetry. Earned targeted comparison retained.",
                                 "Only one witness scored; whole-sample eligibility and cumulative debt remain unknown.",
                                 "Unrecorded stages are null, never zero. No production or installed-iPhone claim."]}}
        from view import render
        render(result, out)
        write(out/"comparison.json", result)
        write(out/"SHA256SUMS.json", {p.name: digest(p) for p in out.iterdir() if p.is_file()})
        return result
    except Exception as e:
        write(out/"INVALID.json", {"decision": "experiment_invalid", "reason": str(e), "spec": spec,
                                   "backend_clock_opt_in": stable_backend_clock})
        raise


def run_existing(spec, out, *, stable_backend_clock=False):
    """Use the existing helper: fresh disposable state and its existing lock.

    New modes are not aliases for the admission fixture. Refuse rather than
    silently substituting synthetic prices for a captured or live stream.
    """
    if spec["mode"] != "controlled-admission":
        raise ValueError("use a named, reviewed replay/shadow adapter; do not substitute the admission control")
    if Path(out).exists():
        raise FileExistsError("result already exists; no implicit rerun")
    order = spec.get("order", ["baseline", "candidate"])
    if sorted(order) != ["baseline", "candidate"]:
        raise ValueError("order must contain each arm exactly once")
    if not spec.get("hypothesis") or not spec.get("baseline_release_evidence"):
        raise ValueError("name hypothesis and relevant released baseline receipt")
    helper_path = Path(spec["helper"]).resolve()
    if digest(helper_path) != spec["helper_sha256"]:
        raise ValueError("lab helper drift")
    for name, expected in spec["lab_files"].items():
        if digest(helper_path.parent/name) != expected:
            raise ValueError("lab dependency drift: "+name)
    result_spec = dict(spec)
    runs = []
    for arm in order:
        prepared = Path(spec[arm+"_prepared"]).resolve()
        manifest = read(prepared/"PREPARED.json")
        if manifest["sha"] != spec[arm+"_sha"]:
            raise ValueError("prepared source differs")
        if any(digest(prepared/"source"/name) != value for name, value in manifest["files"].items()):
            raise ValueError("prepared source drift")
    if digest(spec["transition_scorer"]) != spec["transition_scorer_sha256"]:
        raise ValueError("primary scorer drift")
    # consume() refuses this hook's clock pair without the explicit assumption;
    # refuse before reserving output so no arm is spent on a result it cannot score.
    if stable_backend_clock is not True:
        raise ValueError("timing_unknown: explicit stable backend clock assumption required (--stable-backend-clock)")
    helper = load_module(helper_path, "existing_10669")
    # Reserve output before execution, and retain completed arm paths on failure.
    # The helper owns process cleanup; never stop a process owned by another run.
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    active = None
    try:
        for arm in order:
            prepared = Path(spec[arm+"_prepared"]).resolve()
            before = {"load": os.getloadavg(), "time": time.time(), "cpu_count": os.cpu_count()}
            active = {"arm": arm, "path": None, "stdout": str(out/(arm+"-helper.log"))}
            # The existing helper prints its run path even when cleanup raises.
            # Preserve that output without changing the helper or its lifecycle.
            with Path(active["stdout"]).open("w") as log, redirect_stdout(log):
                run = helper.arm(prepared, "compare-"+arm, "admission-publication-stall", 60,
                                 fixture="singleton", dnpl="kalshi", dnpl_sources="kalshi,polymarket")
            active["path"] = str(run)
            result_spec[arm] = str(run)
            write(Path(run)/"COMPARE-COMPUTE.json", {"before": before, "after_load": os.getloadavg()})
            if read(Path(run)/"RUN.json")["status"] != "READER_COMPLETE":
                raise ValueError("arm did not complete: "+str(run))
            scorer = load_module(Path(spec["transition_scorer"]), "existing_transition_score")
            snapshots = [json.loads(line) for line in (Path(run)/"reader.jsonl").read_text().splitlines()
                         if json.loads(line).get("kind") == "dom"]
            write(Path(run)/"OBSERVATION-SCORE.json", scorer.score_run(Path(run), snapshots))
            runs.append(arm)
            active = None
            write(out/"RUNS.json", {"completed": runs, "failed_arm": None, "spec": result_spec})
        return consume(result_spec, out/"report", stable_backend_clock=stable_backend_clock)
    except BaseException as exc:
        write(out/"RUNS.json", {"completed": runs, "failed_arm": active, "spec": result_spec})
        write(out/"INVALID.json", {"decision": "experiment_invalid", "reason": str(exc),
                                  "completed_arms": runs, "failed_arm": active, "spec": result_spec})
        raise


def stage_recorder(spec, out, *, display_identity=False):
    """One passive listener delta on a copy; preserve the old runs and runner."""
    source = Path(spec["helper"]).resolve().parent
    out = Path(out).resolve()
    if digest(source/"warm_helper.py") != spec["helper_sha256"]:
        raise ValueError("helper drift")
    required = {"backend_lab.py", "proxy.py", "observe.cjs", "FIXTURE-INPUT.json"}
    if set(spec["lab_files"]) != required:
        raise ValueError("recorder staging requires all four lab pins")
    for name, expected in spec["lab_files"].items():
        if digest(source/name) != expected:
            raise ValueError("lab dependency drift: "+name)
    observer = (source/"observe.cjs").read_text()
    old = "['probability','folded_probability','preview']"
    new = "['probability','folded_probability','preview','preview_open_v3','preview_v3','reconcile','reconnect','heartbeat']"
    if observer.count(old) != 1:
        raise ValueError("observer source changed; review the listener delta")
    observer = observer.replace(old, new)
    sample_path = Path(__file__).with_name("display_sample.cjs")
    if display_identity:
        # Capture the product stream's actual URL; never change its negotiation
        # or add a second subscription. All identity rows stay in reader.jsonl.
        sample = sample_path.read_text().split("\nmodule.exports =", 1)[0]
        changes = {
            " let prior='',prev=performance.now();": sample+"\n let prior='',prev=performance.now();",
            "visibility:document.visibilityState,gap:now-prev}":
                "visibility:document.visibilityState,gap:now-prev,displayIdentity:readDisplayIdentity10090()}",
            "payload:JSON.parse(e.data)": "url:this.url,payload:JSON.parse(e.data)",
        }
        for before, after in changes.items():
            if observer.count(before) != 1:
                raise ValueError("display recorder source changed: "+before)
            observer = observer.replace(before, after)
    out.mkdir(parents=True, exist_ok=False)
    for name in ("warm_helper.py", "backend_lab.py", "proxy.py", "FIXTURE-INPUT.json"):
        shutil.copyfile(source/name, out/name)
    (out/"observe.cjs").write_text(observer)
    write(out/"RECORDER-DELTA.json", {"source": str(source), "old_sha256": digest(source/"observe.cjs"),
                                     "new_sha256": digest(out/"observe.cjs"), "before": old, "after": new,
                                     "display_sample_sha256": digest(sample_path) if display_identity else None,
                                     "display_schema": "display-identity-sample/1" if display_identity else None,
                                     "effect": "passive receipt only; product reducers and primary DOM recorder unchanged"})
    staged = dict(spec, helper=str(out/"warm_helper.py"), helper_sha256=digest(out/"warm_helper.py"))
    staged["lab_files"] = {name: digest(out/name) for name in spec["lab_files"]}
    write(out/"comparison-spec.json", staged)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["consume", "run", "score", "stage-recorder", "stage-display-recorder"])
    parser.add_argument("spec", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--stable-backend-clock", action="store_true",
                        help="consume/run: assume no backend wall-clock step over the used interval; "
                             "recorded in the result (default: refuse with timing_unknown)")
    args = parser.parse_args()
    spec = read(args.spec)
    if args.command in ("stage-recorder", "stage-display-recorder"):
        print(stage_recorder(spec, args.out, display_identity=args.command == "stage-display-recorder"))
        return
    if args.command == "score":
        write(args.out, score(spec))
        return
    run = consume if args.command == "consume" else run_existing
    result = run(spec, args.out, stable_backend_clock=args.stable_backend_clock)
    print(json.dumps({"decision": result["decision"], "scope": result["decision_scope"],
                      "view": str(args.out.resolve()/("report" if args.command == "run" else "")/"index.html")}, indent=2))


if __name__ == "__main__":
    main()
