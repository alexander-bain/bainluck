"""#10090 A1: the one named board-contention case through the existing lifecycle.

Adapter from an executed A1 arm (authority's existing lab, `a1-board-contention`
on fixture `a1`) to `score.py`'s eligible/display contract. It certifies no
unrecorded stage and infers no identity from a percentage.

OBLIGATIONS. The headline of event 1 owes one state per accepted Kalshi input
on the read leg: the outcome the refresher's frames name in `observed_basis`
(verified, never assumed), whose market ticker the arm's own pinned rule reads
(`feeds_win_prob_blend`). The identity is the sealed tape's input index for that
outcome (`A:<index>`), the same in every arm. Eligibility is that input's first
accepted consumer mark (`InputMark.recv_wall`), the consumer receipt. Every mark
seq is retained verbatim. Board inputs owe no headline: the arm's own
`kalshi_headline_aux_ticker` must say so and the frame basis must never name a
board outcome. `TailReceipts.covered` is not used (it can count board inputs).

COVERAGE. A sampled surface covers an obligation only through identity:
`data-display-state` / `data-chart-endpoint-state` verbatim -> the recorded
preview_v3 frame with the same frontend identity, or `fold:1=<rev>` -> the
committed bag at that revision (lab trigger log) -> the Kalshi entry's
`observed_basis` for the read leg -> exactly one RETURNING row of a recorded price
phase whose OUTER commit is witnessed (its `last_updated`, its returned value equal
to the phase's buffered input) -> the tape input carrying that value (values are
unique per outcome; verified). A later input supersedes every earlier one on the
same stream, explicitly. The SEEDED committed revision (lab r2 `origin='seed'`,
written before the tape, no `observed_basis`) is the bounded initial state: it
covers no input, and the first display after it is bracketed by it.

MEMBERSHIP. Every accepted Kalshi mark, classification row and RETURNING row must
name the sealed fixture's own event/market/outcome; anything else is invalid.

BOARD and CONTROLS gate the verdict. Each board input (event 1's and the pre-game
board) is committed by exactly one witnessed RETURNING row whose basis a
successful post-commit MARKET publication names, or explicitly coalesced into a
later committed input; anything else is invalid. Board DOM is not measured. B and
P (events 2/3) resolve each read-leg input through its committed row to the first
committed bag revision carrying it or a successor, and that revision's post-commit
`TailReceipts.resolve` witness: an unresolved input is invalid, and a control
regression (CONTROL_RULE) is `no_improvement_or_regression`. Backend claims only.
"""
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

from score import score

MODE = "a1-board-contention"
EVENT = 1
STREAM = "event:1:kalshi-read-leg"
REQUIRED = ["backend-receipt.json", "reader.jsonl", "SOURCE.json", "CONFIG.json", "RUN.json",
            "SOURCE-AFTER.json", "CLEANUP.json", "OBSERVATION-SCORE.json",
            "sample-boundaries.json", "A1-TAPE.json"]


class Invalid(ValueError):
    """experiment_invalid with its precise reason."""


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def require(condition, reason):
    if not condition:
        raise Invalid(reason)


def tape_inputs(tape):
    """Per role/outcome, the tape's inputs in order: (index, at_ms, value).

    One input = one instant's frames for that outcome (a book snapshot and a
    ticker share it). Values must be unique per outcome: that is what lets a
    buffered value name its input."""
    inputs = {}
    for frame in tape["frames"]:
        data = json.loads(frame["raw"])
        msg = data["msg"]
        if data["type"] == "ticker":
            value = round(float(msg["price_dollars"]), 4)
        else:
            value = round(float(msg["yes_dollars_fp"][0][0]) + .005, 4)
        key = int(frame["outcome_id"])
        series = inputs.setdefault(key, [])
        if series and series[-1]["at_ms"] == frame["at_ms"]:
            require(series[-1]["value"] == value, f"tape input {key}@{frame['at_ms']} carries two values")
            series[-1]["frames"].append(frame)
            continue
        series.append({"index": len(series), "at_ms": frame["at_ms"], "value": value,
                       "role": frame["role"], "cycle": frame["cycle"], "frames": [frame]})
    for key, series in inputs.items():
        values = [x["value"] for x in series]
        require(len(values) == len(set(values)), f"tape values repeat for outcome {key}; identity would be ambiguous")
    return inputs


def classification_check(config, tape):
    cls = (config.get("effective") or {}).get("a1", {}).get("classification")
    require(isinstance(cls, dict), "missing A1 context: the arm's own read-rule classification")
    sealed = {o["external_id"]: {"outcome_id": o["id"], "market_id": m["id"], "event_id": m["event_id"],
                                 "role": m["role"], "market_external_id": m["external_id"]}
              for m in tape["fixture"]["markets"] for o in m["outcomes"]}
    require(set(cls) == set(sealed), "classification does not cover exactly the sealed fixture")
    for ticker, identity in sealed.items():
        c = cls[ticker]
        wrong = sorted(k for k, v in identity.items() if c.get(k) != v)
        require(not wrong, f"classification of {ticker} differs from the sealed fixture on {wrong}")
        role = identity["role"]
        if role == "headline":
            require(c["feeds_win_prob_blend"] and not c["headline_aux"] and not c["non_speaking"],
                    f"headline {ticker} is not read by the arm's own rule")
        else:
            require(not c["feeds_win_prob_blend"] and c["headline_aux"] and not c["non_speaking"],
                    f"board {ticker} is not an in-cohort headline-aux row under the arm's own rule")
    return cls


def json_value(value):
    return json.loads(value) if isinstance(value, str) else value


def frontend_preview_identity(payload):
    """`lib/displayIdentity.ts::previewIdentity` for a single-row reader, from
    the recorded SSE payload's own fields (the page admits one member here)."""
    frame, auth = payload["frame"], payload["authority"]
    preview = frame["preview"]
    base = preview.get("base_fold_revision") or {str(payload["event_id"]): preview["base_rev"]}
    rows = sorted(base, key=lambda r: (int(r) if str(r).isdigit() else math.inf, str(r)))
    fold = "fold:" + ",".join(f"{r}={base[r]}" for r in rows)
    return (f"v3:{auth['incarnation']}:{auth['namespace']}:{payload['stream_session']}:"
            f"e{preview['epoch']}.s{preview['seq']}:{fold}")


INITIAL = "initial"  # the seeded committed revision: covers no input


def wall_of(value):
    """A bag log `logged_at` (PG clock_timestamp, serialized by str()) as epoch seconds."""
    return datetime.fromisoformat(str(value)).timestamp()


def committed_returning(a1, fixture_markets):
    """outcome -> the RETURNING rows of every phase whose OUTER commit the lab r2
    recorder witnessed. A returned iterator precedes the commit, so a phase that
    returned but rolled back, or whose outcome is unknown, contributes nothing.
    Each row must name its sealed market and return the value its phase carried."""
    market_of = {o["id"]: m["id"] for m in fixture_markets for o in m["outcomes"]}
    require(any("outer" in p for p in a1["phases"]), "phase commit witness absent: not the lab r2 recorder")
    rows = {}
    for i, p in enumerate(a1["phases"]):
        if p.get("outer") != "committed":
            continue
        require(p["status"] == "returned", f"phase {i} committed without returning its rows")
        for row in p["rows"]:
            oid = row["id"]
            require(market_of.get(oid) == row["market_id"],
                    f"phase {i} returned outcome {oid} under market {row['market_id']}, outside the sealed membership")
            carried = p["outcomes"].get(str(oid))
            require(carried is not None and row.get("value") is not None
                    and round(float(row["value"]), 4) == round(float(carried[0]), 4),
                    f"phase {i} returned {row.get('value')} for outcome {oid}, not the input it carried")
            rows.setdefault(oid, []).append({"basis": row["last_updated"], "value": round(float(carried[0]), 4),
                                             "market_id": row["market_id"], "phase": i,
                                             "committed_mono": p["committed_mono"], "beside": p["beside"]})
    return rows


def one_row(rows, oid, basis):
    """The one witnessed committed RETURNING row of `oid` at `basis`; two are ambiguous (None)."""
    hits = [r for r in rows.get(oid, []) if abs(r["basis"] - basis) <= 1e-6]
    return hits[0] if len(hits) == 1 else None


def accepted_ticker_marks(marks, oid, item, first_sent):
    return sorted((m for m in marks if m["outcome_id"] == oid and m["kind"] == "ticker"
                   and m["recv_mono"] >= first_sent and round(m["probability"], 4) == item["value"]),
                  key=lambda m: m["seq"])


def a1_arm(path, spec, *, stable_backend_clock=False):
    path = Path(path).resolve()
    for name in REQUIRED:
        require((path/name).exists(), f"missing arm evidence {name}: {path}")
    receipt, source = read(path/"backend-receipt.json"), read(path/"SOURCE.json")
    config, run = read(path/"CONFIG.json"), read(path/"RUN.json")
    bounds, clock = read(path/"sample-boundaries.json"), read(path/"OBSERVATION-SCORE.json")
    cleanup, tape = read(path/"CLEANUP.json"), read(path/"A1-TAPE.json")
    require(run["status"] == "READER_COMPLETE" and not receipt["errors"],
            f"incomplete or failed arm: {path}")
    require(read(path/"SOURCE-AFTER.json")["unchanged"], "prepared source drifted during the arm")
    require(cleanup["stopped"] and not cleanup.get("cleanup_errors"), "arm cleanup incomplete")
    require(clock["status"] == "OBSERVED_CALLBACK_INTERVALS" and not clock["faults"],
            "page observation clock unusable")
    require(config["requested"]["fixture"] == "a1", "not the A1 fixture; refusing substitution")
    require(config["requested"]["preview_sources"] == ["kalshi", "polymarket"], "both DNPL sources must be ON")
    require(source["scenario"] == MODE, "not the A1 scenario; refusing substitution")
    rr, = receipt["runs"]
    require(rr["kind"] == MODE and rr["status"] == "inputs-complete", "A1 run did not complete its inputs")
    require(digest(path/"A1-TAPE.json") == spec["tape_sha256"] == rr.get("a1_tape_sha256")
            == config["effective"]["a1"]["tape_sha256"], "arm did not run the sealed tape")
    a1 = receipt.get("a1")
    require(isinstance(a1, dict) and all(k in a1 for k in (
        "marks", "phases", "asks", "resolved", "sent", "parity", "holds", "bag_log", "plans")),
        "missing A1 context recorders")
    cls = classification_check(config, tape)
    if stable_backend_clock is not True:
        raise Invalid("timing_unknown: explicit stable backend clock assumption required (--stable-backend-clock)")

    start, end = bounds["start_ms"], bounds["end_ms"]
    require(abs(start - rr["sample_start_ms"]) < 1e-6, "sample boundary is not the tape T0")
    window = [0.0, float(end - start)]
    u = max(1.0, float(clock["clock_mapping"]["edge_uncertainty_ms"]))
    t0 = rr["a1_t0_mono"]

    def rel_mono(mono):
        return (mono - t0)*1000.0

    # ── the sent tape, verbatim ──────────────────────────────────────────────
    sent = a1["sent"]
    require(len(sent) == len(tape["frames"]) and [e["i"] for e in sent] == list(range(len(sent))),
            "tape delivery record incomplete")
    for entry, frame in zip(sent, tape["frames"]):
        require(entry["sha256"] == sha(frame["raw"]) and entry["at_ms"] == frame["at_ms"],
                f"frame {entry['i']} was not the sealed bytes on the sealed offset")
        require(entry["sent_count"] >= 1 and not entry["errors"], f"frame {entry['i']} not delivered")
    raw_wire = sha("".join(e["sha256"] for e in sent))

    # ── one consumer run, so seq is one identity space ──────────────────────
    epochs = [e for e in receipt.get("consumer_epochs", []) if e["source"] == "kalshi"]
    require(len(epochs) == 1 and epochs[0]["started"] <= t0
            and (epochs[0].get("ended") is None or epochs[0]["ended"] >= t0 + window[1]/1000),
            "Kalshi consumer did not run one epoch across the sample")

    inputs = tape_inputs(tape)
    fixture_markets = tape["fixture"]["markets"]
    role_of = {o["id"]: m["role"] for m in fixture_markets for o in m["outcomes"]}
    event_of = {o["id"]: m["event_id"] for m in fixture_markets for o in m["outcomes"]}
    board_ids = {oid for oid, role in role_of.items() if role == "board" and event_of[oid] == EVENT}

    # ── sealed membership of every accepted Kalshi mark ─────────────────────
    marks = [m for m in a1["marks"] if m["source"] == "kalshi"]
    for m in marks:
        require(m["outcome_id"] in event_of, f"Kalshi mark {m['seq']} names outcome {m['outcome_id']} outside the sealed fixture")
        require(m["event_id"] == event_of[m["outcome_id"]],
                f"Kalshi mark {m['seq']} names event {m['event_id']} for outcome {m['outcome_id']} "
                f"of sealed event {event_of[m['outcome_id']]}")
    committed = committed_returning(a1, fixture_markets)

    # ── the read leg, from the frames themselves ────────────────────────────
    rows = [json.loads(line) for line in (path/"reader.jsonl").read_text().splitlines()]
    preview_frames = [r for r in rows if r["kind"] == "frame" and r["type"] == "preview_v3"
                      and r["payload"].get("event_id") == EVENT]
    require(all(e.get("origin") in ("seed", "update") for e in a1["bag_log"]),
            "bag log entry without a seed/update origin: not the lab r2 recorder")
    seeds = [e for e in a1["bag_log"] if int(e["event_id"]) == EVENT and e["origin"] == "seed"]
    require(len(seeds) == 1 and seeds[0].get("rev") is not None, "event 1 has no single seeded committed revision")
    seed_rev, seed_bag = int(seeds[0]["rev"]), json_value(seeds[0]["kalshi"]) or {}
    bag = {}
    for entry in a1["bag_log"]:
        if int(entry["event_id"]) == EVENT and entry.get("rev") is not None and entry["origin"] == "update":
            require(int(entry["rev"]) > seed_rev, f"committed revision {entry['rev']} does not follow the seed {seed_rev}")
            bag.setdefault(int(entry["rev"]), []).append(json_value(entry["kalshi"]) or {})
    bag[seed_rev] = [seed_bag]
    named = set()
    for r in preview_frames:
        pending = (r["payload"]["frame"].get("preview") or {}).get("pending_entries") or {}
        named |= {int(k) for k in (pending.get("kalshi") or {}).get("observed_basis", {})}
    for entries in bag.values():
        for e in entries:
            named |= {int(k) for k in (e.get("observed_basis") or {})}
    require(named and named <= set(tape["roles"]["A_read_leg_candidates"]),
            f"frame basis names {sorted(named)}, not exactly the declared read leg")
    require(not (named & board_ids), "a board outcome appears in a headline basis")
    read_leg, = named
    require(cls[next(o["external_id"] for m in fixture_markets for o in m["outcomes"]
                     if o["id"] == read_leg)]["feeds_win_prob_blend"], "read leg is not read by the pinned rule")

    # ── obligations: tape inputs on the read leg, eligible at consumer receipt ──
    by_outcome = {}
    for m in marks:
        by_outcome.setdefault(m["outcome_id"], []).append(m)
    series = inputs[read_leg]
    sent_mono = {e["i"]: e["sent_mono"] for e in sent}
    frame_index = {id(f): i for i, f in enumerate(tape["frames"])}

    def sent_at(item):
        return min(sent_mono[frame_index[id(f)]] for f in item["frames"])

    eligible, excluded, holes = [], {"book_observation": 0, "outside_window": 0}, []
    obligation_of_value = {}
    previous = None
    for item in series:
        first_sent = sent_at(item)
        accepted = accepted_ticker_marks(by_outcome.get(read_leg, []), read_leg, item, first_sent)
        excluded["book_observation"] += sum(
            1 for m in by_outcome.get(read_leg, []) if m["kind"] == "book_observation"
            and m["recv_mono"] >= first_sent and round(m["probability"], 4) == item["value"])
        if not accepted:
            holes.append(f"A:{item['index']} has no accepted consumer mark")
            continue
        recv = min(m["recv_wall"] for m in accepted)*1000.0 - start
        if not (window[0] <= recv - u and recv + u <= window[1]):
            excluded["outside_window"] += 1
            continue
        identity = f"A:{item['index']}"
        record = {"id": identity, "stream": STREAM, "at_ms": [recv - u, recv + u],
                  "evidence": "first accepted InputMark on the read leg; marks " + ",".join(
                      str(m["seq"]) for m in sorted(accepted, key=lambda m: m["seq"])),
                  "tape": {"at_ms": item["at_ms"], "value": item["value"], "role": item["role"],
                           "cycle": item["cycle"]}}
        if previous is not None:
            record["supersedes"] = [previous]
        eligible.append(record)
        obligation_of_value[item["value"]] = identity
        previous = identity
    order = {o["id"]: i for i, o in enumerate(eligible)}

    # ── commits: exactly one witnessed committed RETURNING row -> its input ──
    def obligation_for_basis(basis):
        row = one_row(committed, read_leg, basis)
        return None if row is None else obligation_of_value.get(row["value"])

    # ── displayed identity -> Kalshi basis on the read leg ──────────────────
    preview_basis = {}
    for r in preview_frames:
        payload = r["payload"]
        key = frontend_preview_identity(payload)
        pending = payload["frame"]["preview"].get("pending_entries") or {}
        if "kalshi" in pending:
            value = (pending["kalshi"].get("observed_basis") or {}).get(str(read_leg))
        else:
            value = ("rev", int(payload["frame"]["preview"]["base_rev"]))
        preview_basis.setdefault(key, set()).add(value if not isinstance(value, list) else tuple(value))

    def basis_of_rev(rev):
        entries = bag.get(rev, [])
        values = {(e.get("observed_basis") or {}).get(str(read_leg)) for e in entries}
        value = values.pop() if len(values) == 1 else None
        # Only the seeded revision may lack a basis: it is the initial state.
        # Any other basis-less revision stays unknown.
        return INITIAL if value is None and rev == seed_rev and len(entries) == 1 else value

    def resolve(state):
        if not state:
            return None
        found = re.fullmatch(r"fold:1=(\d+)", state)
        if found:
            return basis_of_rev(int(found.group(1)))
        if state.startswith("v3:"):
            values = preview_basis.get(state)
            if not values or len(values) != 1:
                return None
            value, = values
            return basis_of_rev(value[1]) if isinstance(value, tuple) else value
        return None

    attribute = {"headline": ("headline", "data-display-state"),
                 "chart": ("chart", "data-chart-endpoint-state")}
    samples = sorted((r for r in rows if r["kind"] in ("dom", "dom_mo")
                      and start - 200 <= r["wall"] <= end + 200), key=lambda r: (r["wall"], r["mono"]))
    displays, surface_report = [], {}
    for surface, (key, attr) in attribute.items():
        best, last_lower_wall, transitions = -1, None, []
        report = {"rows": 0, "identity_holes": 0, "unsupported": 0, "regressions": 0,
                  "unbracketed": 0, "initial_display": None}
        for r in samples:
            ident = (r.get("displayIdentity") or {}).get(key) or {}
            if not start <= r["wall"] <= end:
                continue
            report["rows"] += 1
            if ident.get("status") != "present" or ident.get("count") != 1 or not ident.get("visible"):
                report["unsupported"] += 1
                continue
            basis = resolve((ident.get("attributes") or {}).get(attr))
            covered = INITIAL if basis == INITIAL else None if basis is None else obligation_for_basis(basis)
            if covered is None:
                report["identity_holes"] += 1
                continue
            index = -1 if covered == INITIAL else order.get(covered)
            if index is None:
                report["identity_holes"] += 1
                continue
            if report["initial_display"] is None:
                report["initial_display"] = covered
            if index < best:
                report["regressions"] += 1
                continue
            if index > best:
                if last_lower_wall is not None:
                    lo = last_lower_wall - start - u
                    hi = r["wall"] - start + u
                    target = eligible[index]
                    lo = max(lo, target["at_ms"][0])
                    displays.append({"surface": surface, "at_ms": [max(window[0], min(lo, hi)), min(window[1], hi)],
                                     "covers": [target["id"]]})
                    transitions.append({"id": target["id"], "row_wall": r["wall"], "kind": r["kind"]})
                elif index >= 0:
                    # Covered from the first resolvable row: no sample proves it
                    # was not already shown, so no bracket exists.
                    report["unbracketed"] += 1
                best = index
            last_lower_wall = r["wall"]
        report["transitions"] = len(transitions)
        surface_report[surface] = report

    trace = {"window_ms": window, "eligible": [{k: v for k, v in o.items() if k != "tape"} for o in eligible],
             "displays": displays, "violations": [],
             "coverage": {"scope": "every tape input on event 1's read leg inside the sample",
                          "eligible_states_scored": len(eligible), "read_leg": read_leg,
                          "excluded_marks": excluded, "input_holes": holes,
                          "surface": surface_report, "clock_uncertainty_ms": u,
                          "clock_assumption": "backend time.time and browser Date.now share one host wall clock; no step over the sample",
                          "display_resolution": "100ms DOM sample plus MutationObserver rows; not physical paint",
                          "upstream_wait": "none: controlled local tape; consumer receipt is the eligibility anchor",
                          "board_dom_display": "not_measured: the pinned recorder samples headline and chart only"},
             "checks": {"revision_ordering": {s: surface_report[s]["regressions"] for s in surface_report},
                        "identity": {s: surface_report[s]["identity_holes"] for s in surface_report},
                        "expiry": "not measured in this control"}}
    for s, rep in surface_report.items():
        if rep["regressions"]:
            trace["violations"].append(f"{s} displayed an older state after a newer one ({rep['regressions']} rows)")
    for s, rep in surface_report.items():
        require(not rep["identity_holes"] and not rep["unsupported"] and not rep["unbracketed"],
                f"{s} identity coverage incomplete: {rep['identity_holes']} unresolved, "
                f"{rep['unsupported']} unsupported, {rep['unbracketed']} unbracketed rows")
    require(not holes, "input coverage holes: " + "; ".join(holes[:5]))
    surface_report["headline"]["initial_revision"] = surface_report["chart"]["initial_revision"] = seed_rev
    board = board_coverage(a1, tape, inputs, committed, marks, sent_at)
    require(not board["failures"], f"board coverage incomplete ({len(board['failures'])}): "
            + "; ".join(board["failures"][:5]))
    controls = stamp_controls(a1, tape, inputs, committed, marks, sent_at, u)
    for event, control in controls.items():
        require(not control["failures"], f"control event {event} incomplete ({len(control['failures'])}): "
                + "; ".join(control["failures"][:5]))
    scorecard = score(trace)
    scorecard["whole_sample_gap"] = clock.get("longest_wait")
    return {"path": str(path), "source": source, "trace": trace, "score": scorecard,
            "mechanism": mechanism(a1, tape, inputs, rel_mono, read_leg, board_ids),
            "controls": controls,
            "board_publication": board,
            "parity": {"raw_wire_sha256": raw_wire, "frame_offsets_ms": [e["at_ms"] for e in sent],
                       "jitter_ms": [e["jitter_ms"] for e in sent], "snapshot": a1["parity"],
                       "settings": config["effective"]["a1"]["speed_switch_env"],
                       "preview_from_commit_possible": config["effective"]["a1"]["preview_from_commit_possible"],
                       "classification": cls},
            "compute": read(path/"COMPARE-COMPUTE.json") if (path/"COMPARE-COMPUTE.json").exists() else None,
            "hashes": {name: digest(path/name) for name in REQUIRED}}


def mechanism(a1, tape, inputs, rel_mono, read_leg, board_ids):
    """Per deciding cycle: was the board still unfinished while the beside
    writer ran beside the owner's held non-live phase? Baseline's duplicate
    stamp ask is a SEPARATE witness, reported, never required."""
    holds = {h["label"]: h for h in a1["holds"]}
    declared = {h["label"]: h for h in tape["holds"]}
    x, y = tape["roles"]["X"], tape["roles"]["Y"]
    heads = {m["event_id"]: {o["id"] for o in m["outcomes"]} for m in tape["fixture"]["markets"]
             if m["role"] == "headline"}
    b_home = next(o["id"] for m in tape["fixture"]["markets"] if m["role"] == "headline"
                  and m["event_id"] == 2 for o in m["outcomes"] if o.get("leg") == "home")
    phases = [dict(p, t0=rel_mono(p["start_mono"]), t1=rel_mono(p["end_mono"]))
              for p in a1["phases"] if p.get("end_mono") is not None and p["status"] == "returned"]
    cycles = []
    for cycle, c0 in enumerate(tape["cycle_ms"], start=1):
        def hold(kind):
            label = f"cycle-{cycle}-{kind}"
            got = holds.get(label)
            return got is not None and float(got["held_s"]) >= declared[label]["hold_s"] - .05

        def wrote(oid, value, beside):
            return [p for p in phases if p["beside"] is beside and str(oid) in p["outcomes"]
                    and round(float(p["outcomes"][str(oid)][0]), 4) == value
                    and any(r["id"] == oid for r in p["rows"])]
        value = {h["role"]: round(float(h["value"]), 4) for h in tape["holds"] if h["cycle"] == cycle}
        deciding = next(i["value"] for i in inputs[read_leg] if i["cycle"] == cycle and i["at_ms"] == c0 + 1000)
        owner = wrote(y, value["P-board"], False)
        board = wrote(x, value["A-board"], True)
        head = wrote(read_leg, deciding, True)
        pacer = wrote(b_home, value["B-headline"], True)
        same_pass = any(
            p["beside"] and c0 <= rel_mono(p["mono"]) < c0 + 7000
            and any(read_leg in phase for phase in p["phases"]) and any(x in phase for phase in p["phases"])
            for p in a1["plans"])
        checks = {
            "owner_nonlive_phase_held": hold("owner-nonlive-phase") and len(owner) == 1,
            "pacer_held_beside": hold("beside-pacer") and len(pacer) == 1,
            "board_held_beside": hold("board-unfinished-beside") and len(board) == 1,
            "headline_written_beside": len(head) == 1,
            "same_beside_pass": same_pass,
        }
        if all(checks.values()):
            o, b, h = owner[0], board[0], head[0]
            checks["board_unfinished_after_headline_commit"] = h["t1"] < b["t1"]
            checks["inside_owner_phase"] = o["t0"] <= h["t0"] and b["t1"] <= o["t1"]
        cycles.append({"cycle": cycle, "exercised": all(checks.values()), "checks": checks})
    duplicate = 0
    event_rows = heads[EVENT] | board_ids
    for ask in a1["asks"]:
        if ask["kind"] not in ("refresh", "admit_fresh") or EVENT not in (ask.get("fresh") or []):
            continue
        prior = [p for p in phases if p["t1"] <= rel_mono(ask["start_mono"])
                 and event_rows & {int(k) for k in p["outcomes"]}]
        if prior and not heads[EVENT] & {int(k) for k in prior[-1]["outcomes"]}:
            duplicate += 1
    deferred = sum(1 for ask in a1["asks"] if EVENT in (ask.get("defer") or []))
    return {"cycles": cycles, "exercised": sum(c["exercised"] for c in cycles),
            "witness": {"stamp_asks_after_board_only_commit": duplicate,
                        "asks_deferring_event_1": deferred,
                        "note": "separate witness of the candidate's removed work; not required"}}


def stamp_controls(a1, tape, inputs, committed, marks, sent_at, u):
    """Backend-only B/P controls (events 2/3): no DOM is claimed.

    The read leg is the one headline outcome the event's committed bag names in
    `observed_basis`. Each tape input on it resolves by identity: its first
    accepted ticker mark (receipt) -> the first committed bag revision whose basis
    is exactly one witnessed committed RETURNING row carrying it or a later input
    (explicit supersession) -> that revision's post-commit `TailReceipts.resolve`
    witness (`stamped`, the same rev). Delay is [bag write - receipt - u, witness -
    receipt]. A later staged mark is never a read basis. Any input left without
    that chain is a failure (final debt), never a successful control."""
    out = {}
    for m in tape["fixture"]["markets"]:
        if m["role"] != "headline" or m["event_id"] == EVENT:
            continue
        event, heads = m["event_id"], {o["id"] for o in m["outcomes"]}
        updates = [e for e in a1["bag_log"] if int(e["event_id"]) == event and e["origin"] == "update"]
        named = set()
        for e in updates:
            named |= {int(k) for k in ((json_value(e["kalshi"]) or {}).get("observed_basis") or {})}
        failures, updates_out = [], []
        if len(named) != 1 or not named <= heads:
            out[str(event)] = {"leg": None, "failures": [
                f"committed bag basis names {sorted(named)}, not one headline leg of event {event}"]}
            continue
        leg, = named
        index_of_value = {i["value"]: i["index"] for i in inputs[leg]}
        revisions = []
        for e in sorted(updates, key=lambda e: int(e["rev"])):
            basis = ((json_value(e["kalshi"]) or {}).get("observed_basis") or {}).get(str(leg))
            row = None if basis is None else one_row(committed, leg, basis)
            if row is None or row["value"] not in index_of_value:
                failures.append(f"rev {e['rev']} basis {basis} has no single committed RETURNING row of a tape input")
                continue
            witnesses = [r["mono"] for r in a1["resolved"]
                         if (r["dispositions"].get(str(event)) or [None])[0] == "stamped"
                         and len(r["dispositions"][str(event)]) > 4
                         and r["dispositions"][str(event)][4] == str(e["rev"])]
            revisions.append({"rev": int(e["rev"]), "input": index_of_value[row["value"]],
                              "logged": wall_of(e["logged_at"]), "witness": min(witnesses) if witnesses else None})
        for item in inputs[leg]:
            identity = f"{event}:{item['index']}"
            accepted = accepted_ticker_marks(marks, leg, item, sent_at(item))
            if not accepted:
                failures.append(f"{identity} has no accepted consumer mark")
                continue
            covering = next((r for r in revisions if r["input"] >= item["index"]), None)
            if covering is None:
                failures.append(f"{identity} unresolved at end: no committed bag revision carries it or a successor")
                continue
            if covering["witness"] is None:
                failures.append(f"{identity}: rev {covering['rev']} has no post-commit stamped witness")
                continue
            mark = accepted[0]
            lo = max(0.0, (covering["logged"] - mark["recv_wall"])*1000.0 - u)
            hi = (covering["witness"] - mark["recv_mono"])*1000.0
            if lo > hi:
                failures.append(f"{identity}: bag write after its own post-commit witness (clock inconsistent)")
                continue
            updates_out.append({"id": identity, "delay_ms": [lo, hi], "rev": covering["rev"],
                                "via": f"{event}:{covering['input']}", "marks": [x["seq"] for x in accepted],
                                "disposition": "stamped" if covering["input"] == item["index"]
                                else "covered_by_successor"})
        out[str(event)] = {
            "leg": leg, "inputs": len(inputs[leg]), "resolved": len(updates_out), "final_debt": len(inputs[leg]) - len(updates_out),
            "worst_ms": [max((x["delay_ms"][i] for x in updates_out), default=0.0) for i in (0, 1)],
            "cumulative_ms": [sum(x["delay_ms"][i] for x in updates_out) for i in (0, 1)],
            "updates": updates_out, "failures": failures, "dom": "not_measured"}
    return out


def board_coverage(a1, tape, inputs, committed, marks, sent_at):
    """Every board input (event 1's board and the pre-game board), by identity.

    Each input is received (an accepted ticker mark), then committed by exactly
    one witnessed RETURNING row carrying its value, and that row's basis is named
    by exactly one SUCCESSFUL post-commit MARKET publication (`sent` equals its
    change count) for its market. An input with no committed row is coalesced
    only into a later committed input of the same outcome, explicitly. A missing,
    failed or partial publication, or one naming the market without that row's
    basis, is a failure. Board DOM display is not sampled: `dom` stays
    not_measured."""
    publications = a1.get("market_publications")
    require(isinstance(publications, list) and all("sent" in p for p in publications),
            "publication result absent: not the lab r2 recorder")
    named = {}
    for i, pub in enumerate(publications):
        changes = pub.get("changes")
        ok = (pub.get("source") == "kalshi" and isinstance(changes, list) and bool(changes)
              and pub["sent"] == len(changes))
        for change in changes or []:
            if not isinstance(change, dict):
                continue
            for oid, stamp in (change.get("outcome_observed_at") or {}).items():
                named.setdefault((change.get("market_id"), int(oid)), []).append(
                    {"basis": datetime.fromisoformat(stamp).timestamp(), "ok": ok, "mono": pub["mono"], "i": i})

    def publication(row, oid):
        hits = [n for n in named.get((row["market_id"], oid), [])
                if abs(n["basis"] - row["basis"]) <= 1e-6 and n["mono"] >= row["committed_mono"]]
        good = [n for n in hits if n["ok"]]
        if len(good) == 1:
            return "published", good[0]["i"]
        if good:
            return "ambiguous_publication", None
        return ("publication_failed" if hits else "unpublished"), None

    failures, out = [], []
    cohort = [o["id"] for m in tape["fixture"]["markets"] if m["role"] == "board" for o in m["outcomes"]]
    for oid in cohort:
        series = inputs.get(oid, [])
        committed_index = {}
        for item in series:
            hits = [r for r in committed.get(oid, []) if r["value"] == item["value"]]
            if len(hits) > 1:
                failures.append(f"board {oid}:{item['index']} has {len(hits)} committed RETURNING rows")
            elif hits:
                committed_index[item["index"]] = hits[0]
        for item in series:
            identity = f"{oid}:{item['index']}"
            if not accepted_ticker_marks(marks, oid, item, sent_at(item)):
                failures.append(f"board {identity} has no accepted consumer mark")
                continue
            row = committed_index.get(item["index"])
            if row is None:
                later = next((i for i in sorted(committed_index) if i > item["index"]), None)
                if later is None:
                    failures.append(f"board {identity} unresolved: no committed RETURNING row carries it or a successor")
                else:
                    out.append({"id": identity, "disposition": "coalesced", "via": f"{oid}:{later}"})
                continue
            status, pub = publication(row, oid)
            if status != "published":
                failures.append(f"board {identity} committed in phase {row['phase']} but {status}")
                continue
            out.append({"id": identity, "disposition": "committed_and_published", "phase": row["phase"],
                        "publication": pub})
    return {"outcomes": len(cohort), "inputs": sum(len(inputs.get(oid, [])) for oid in cohort),
            "committed_and_published": sum(x["disposition"] == "committed_and_published" for x in out),
            "coalesced": sum(x["disposition"] == "coalesced" for x in out),
            "by_input": out, "failures": failures, "dom": "not_measured"}


def parity(b, c, tolerance):
    """Identical timestamped input and equivalent starting state, or the reason not."""
    reasons, report = [], {}
    pb, pc = b["parity"], c["parity"]
    if pb["raw_wire_sha256"] != pc["raw_wire_sha256"] or pb["frame_offsets_ms"] != pc["frame_offsets_ms"]:
        reasons.append("tape bytes or declared offsets differ between arms")
    jitter = [abs(x) for x in pb["jitter_ms"] + pc["jitter_ms"]]
    report["max_send_jitter_ms"] = max(jitter) if jitter else None
    report["max_jitter_difference_ms"] = max((abs(x - y) for x, y in zip(pb["jitter_ms"], pc["jitter_ms"])), default=None)
    if report["max_send_jitter_ms"] is not None and report["max_send_jitter_ms"] > tolerance["jitter_ms"]:
        reasons.append(f"send jitter {report['max_send_jitter_ms']:.1f} ms exceeds {tolerance['jitter_ms']} ms")
    sb, sc = pb["snapshot"], pc["snapshot"]
    if set(sb["outcomes"]) != set(sc["outcomes"]):
        reasons.append("starting rows differ")
    else:
        values = [k for k in sb["outcomes"] if sb["outcomes"][k]["value"] != sc["outcomes"][k]["value"]]
        ages = [abs(sb["outcomes"][k]["age_s"] - sc["outcomes"][k]["age_s"]) for k in sb["outcomes"]
                if sb["outcomes"][k]["age_s"] is not None and sc["outcomes"][k]["age_s"] is not None]
        report["max_row_age_difference_s"] = max(ages, default=0.0)
        if values:
            reasons.append(f"starting values differ on {len(values)} rows")
        if report["max_row_age_difference_s"] > tolerance["age_s"]:
            reasons.append(f"starting row ages differ by {report['max_row_age_difference_s']:.3f} s")
    for eid in sorted(set(sb["events"]) | set(sc["events"])):
        eb, ec = sb["events"].get(eid), sc["events"].get(eid)
        if not eb or not ec or eb["status"] != ec["status"] or eb["kalshi_value"] != ec["kalshi_value"]:
            reasons.append(f"event {eid} starting status/committed value differs")
            continue
        for field, limit in (("kalshi_entry_age_s", tolerance["age_s"]), ("commence_age_s", tolerance["clause_age_s"])):
            if (eb[field] is None) != (ec[field] is None) or (
                    eb[field] is not None and abs(eb[field] - ec[field]) > limit):
                reasons.append(f"event {eid} {field} differs beyond {limit} s")
    if pb["settings"] != pc["settings"] or pb["preview_from_commit_possible"] != pc["preview_from_commit_possible"]:
        reasons.append("relevant settings differ between arms")
    if pb["classification"] != pc["classification"]:
        reasons.append("read-rule classification differs between arms")
    return reasons, report


DEFAULT_TOLERANCE = {"jitter_ms": 50.0, "age_s": 0.5, "clause_age_s": 600.0}

CONTROL_RULE = ("Declared before any arm: a B/P control regresses when, over the same input identities, the "
                "candidate's worst or cumulative receipt-to-committed-stamp interval lies wholly above the "
                "baseline's (candidate lower bound > baseline upper bound + control_tolerance_ms, default 0), "
                "the rule score.decide applies to the headline/chart. A regression is no_improvement_or_regression.")


def control_regressions(b, c, tolerance_ms):
    regressions = []
    for event in sorted(set(b) | set(c)):
        cb, cc = b.get(event), c.get(event)
        require(cb and cc and {x["id"] for x in cb["updates"]} == {x["id"] for x in cc["updates"]},
                f"control event {event} input identities differ between arms")
        for metric in ("worst_ms", "cumulative_ms"):
            if cc[metric][0] > cb[metric][1] + tolerance_ms:
                regressions.append(f"control event {event} {metric}: candidate {cc[metric][0]:.1f} ms > "
                                   f"baseline {cb[metric][1]:.1f} ms")
    return regressions


def a1_consume(spec, out, *, stable_backend_clock=False):
    """Offline, repeatable: score two retained A1 arms; never modifies them."""
    from score import decide

    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)  # never silently replace a result
    result = {"schema": "dnpl-comparison/1", "mode": MODE, "spec": spec,
              "backend_clock_opt_in": stable_backend_clock}
    try:
        require(spec.get("mode") == MODE, "not the A1 spec; refusing substitution")
        arms = {k: a1_arm(spec[k], spec, stable_backend_clock=stable_backend_clock)
                for k in ("baseline", "candidate")}
        b, c = arms["baseline"], arms["candidate"]
        require(b["source"]["backend_ref"] == spec["baseline_sha"]
                and c["source"]["backend_ref"] == spec["candidate_sha"],
                "arm source differs from the predeclared comparison")
        require(b["source"]["frontend_build_source_sha"] == c["source"]["frontend_build_source_sha"]
                and b["source"]["build_id"] == c["source"]["build_id"],
                "arms did not use the same pinned frontend build")
        reasons, report = parity(b, c, {**DEFAULT_TOLERANCE, **spec.get("parity_tolerance", {})})
        required = int(spec.get("min_exercised_cycles", len(read(spec["tape"])["cycle_ms"])))
        for name, arm in arms.items():
            if arm["mechanism"]["exercised"] < required:
                missing = [x["cycle"] for x in arm["mechanism"]["cycles"] if not x["exercised"]]
                reasons.append(f"{name}: board contention mechanism unexercised in cycles {missing}")
        require(not reasons, "; ".join(reasons))
        regressions = control_regressions(b["controls"], c["controls"], float(spec.get("control_tolerance_ms", 0.0)))
        decision = decide(b["score"], c["score"])
        if regressions and decision != "experiment_invalid":
            decision = "no_improvement_or_regression"
        result.update(decision=decision, control_rule=CONTROL_RULE, control_regressions=regressions,
                      decision_scope="A1 controlled synthetic board-contention tape only; not production",
                      baseline=b, candidate=c, comparability={**report, "same_tape_bytes": True,
                      "limits": ["SYNTHETIC controlled tape and fixture; not a production reproduction.",
                                 "Board DOM display not sampled; every board input is verified committed and "
                                 "published (or explicitly coalesced) from the backend.",
                                 "B/P controls are backend receipt-to-committed-stamp intervals, not DOM timings.",
                                 "Starting ages measured at the parity marker, not rebased.",
                                 "One AB order unless the spec says otherwise; no global subsecond claim."]})
        Path(out/"comparison.json").write_text(json.dumps(result, indent=2, default=str, allow_nan=False) + "\n")
        Path(out/"SHA256SUMS.json").write_text(json.dumps(
            {p.name: digest(p) for p in out.iterdir() if p.is_file()}, indent=2) + "\n")
        return result
    except Exception as exc:
        invalid = {"decision": "experiment_invalid", "reason": str(exc), "spec": spec,
                   "backend_clock_opt_in": stable_backend_clock}
        Path(out/"INVALID.json").write_text(json.dumps(invalid, indent=2, default=str) + "\n")
        raise


LAB_FILES = {"backend_lab.py", "proxy.py", "observe.cjs", "FIXTURE-INPUT.json", "A1-TAPE.json"}


def verify_a1_spec(spec, *, stable_backend_clock):
    """Every pin, before anything is reserved or started."""
    require(spec.get("mode") == MODE, "use the named A1 spec; no substitution")
    require(spec.get("hypothesis") and spec.get("baseline_release_evidence"),
            "name the hypothesis and the released baseline receipt")
    order = spec.get("order", ["baseline", "candidate"])
    require(sorted(order) == ["baseline", "candidate"], "order must contain each arm exactly once")
    helper = Path(spec["helper"]).resolve()
    require(digest(helper) == spec["helper_sha256"], "lab helper drift")
    require(set(spec["lab_files"]) == LAB_FILES, "A1 needs exactly the four lab files plus the sealed tape")
    for name, expected in spec["lab_files"].items():
        require(digest(helper.parent/name) == expected, "lab dependency drift: " + name)
    require(Path(spec["tape"]).resolve() == helper.parent/"A1-TAPE.json"
            and spec["lab_files"]["A1-TAPE.json"] == spec["tape_sha256"], "tape is not the pinned lab tape")
    manifests = {}
    for arm in ("baseline", "candidate"):
        prepared = Path(spec[arm + "_prepared"]).resolve()
        manifest = read(prepared/"PREPARED.json")
        require(manifest["sha"] == spec[arm + "_sha"], f"{arm} prepared source differs")
        require(all(digest(prepared/"source"/n) == h for n, h in manifest["files"].items()),
                f"{arm} prepared source drift")
        manifests[arm] = manifest
    front = {a: (m.get("frontend_build_source_sha", m["sha"]), m["build_id"]) for a, m in manifests.items()}
    require(front["baseline"] == front["candidate"], "arms must share one pinned frontend build (prepare-a1)")
    require(digest(spec["transition_scorer"]) == spec["transition_scorer_sha256"], "primary scorer drift")
    if stable_backend_clock is not True:
        raise Invalid("timing_unknown: explicit stable backend clock assumption required (--stable-backend-clock)")
    return order, manifests


def probe_prerequisites(spec):
    """Probe, never start: the lab-only PG17 and the CDP browser must already be
    up, and the helper's ports free. Unrun resources are named, not seized."""
    import socket
    import subprocess
    import urllib.request
    missing = []
    ready = subprocess.run(["/opt/homebrew/opt/postgresql@17/bin/pg_isready", "-h", "localhost", "-p", "5433"],
                           capture_output=True)
    if ready.returncode != 0:
        missing.append("lab PG17 localhost:5433 not answering (never started from here)")
    browser = spec.get("browser", {})
    if browser.get("fresh_chromium"):
        if not Path(browser["fresh_chromium"]).exists():
            missing.append("bundled Chromium binary absent: " + browser["fresh_chromium"])
    else:
        cdp = browser.get("cdp_url", "http://127.0.0.1:9333")
        try:
            urllib.request.urlopen(cdp + "/json/version", timeout=2).read()
        except Exception as exc:
            missing.append(f"CDP browser at {cdp} not answering: {exc!r}")
    for port in (4633, 4634, 4635):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                missing.append(f"port {port} already owned")
    require(not missing, "prerequisite missing: " + "; ".join(missing))


CHROMIUM_PID = Path("/tmp/a1-lab-chromium.pid")


def fresh_chromium(binary, log):
    """The existing lab's per-arm browser (`run_arms.py --fresh-chromium`): stop
    only the pid this runner started, start a fresh single-process Chromium on
    9333 with an empty profile, wait for CDP. Both arms get the same state."""
    import shutil
    import subprocess
    import time
    import urllib.request
    stop_chromium()
    profile = Path("/tmp/a1-lab-chromium-profile")
    shutil.rmtree(profile, ignore_errors=True)
    profile.mkdir()
    pid = subprocess.check_output(
        ["python3", "/Users/bain/bainluck/tools/detach-run.py", str(log), binary, "--headless=new",
         "--single-process", "--no-sandbox", "--disable-gpu", "--disable-crashpad", "--disable-dev-shm-usage",
         "--no-first-run", f"--user-data-dir={profile}", "--remote-debugging-address=127.0.0.1",
         "--remote-debugging-port=9333", "about:blank"], text=True).strip().split()[-1]
    CHROMIUM_PID.write_text(pid)
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:9333/json/version", timeout=2).read()
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("fresh Chromium never answered on 9333")


def stop_chromium():
    import os
    import signal
    import time
    if CHROMIUM_PID.exists():
        try:
            os.kill(int(CHROMIUM_PID.read_text()), signal.SIGKILL)
        except (ProcessLookupError, ValueError):
            pass
        CHROMIUM_PID.unlink()
        time.sleep(1)


def a1_run(spec, out, *, stable_backend_clock=False, load_module):
    """Run the named A1 case through the existing helper: fresh disposable PG
    database and Redis per arm, its exclusive #10669 lock, real consumers,
    refresher, SSE and page, its cleanup. DNPL ON in both arms."""
    import os
    import time
    from contextlib import redirect_stdout

    if Path(out).exists():
        raise FileExistsError("result already exists; no implicit rerun")
    order, _ = verify_a1_spec(spec, stable_backend_clock=stable_backend_clock)
    probe_prerequisites(spec)
    helper = load_module(Path(spec["helper"]).resolve(), "existing_10669_a1")
    scorer = load_module(Path(spec["transition_scorer"]), "existing_transition_score")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    result_spec, runs, active = dict(spec), [], None
    settings = dict(spec.get("settings_env", {}))
    require(all(k.startswith("SPEED_SWITCH_") for k in settings), "settings_env carries SPEED_SWITCH_* only")
    saved = {k: v for k, v in os.environ.items()
             if k.startswith("SPEED_SWITCH_") or k in ("LOCAL_A1_TAPE", "LOCAL_A1_TAPE_SHA256", "LAB_CDP_URL",
                                                         "LAB_CDP_DEFAULT_CONTEXT")}
    fresh = spec.get("browser", {}).get("fresh_chromium")
    try:
        for k in [k for k in os.environ if k.startswith("SPEED_SWITCH_")]:
            del os.environ[k]  # ambient switches never leak into one arm
        os.environ.update(settings, LOCAL_A1_TAPE=str(Path(spec["tape"]).resolve()),
                          LOCAL_A1_TAPE_SHA256=spec["tape_sha256"],
                          LAB_CDP_URL=spec.get("browser", {}).get("cdp_url", "http://127.0.0.1:9333"))
        if fresh:
            os.environ["LAB_CDP_DEFAULT_CONTEXT"] = "1"
        for arm in order:
            prepared = Path(spec[arm + "_prepared"]).resolve()
            if fresh:
                fresh_chromium(fresh, out/(arm + "-chromium.log"))
            before = {"load": os.getloadavg(), "time": time.time(), "cpu_count": os.cpu_count()}
            active = {"arm": arm, "path": None, "stdout": str(out/(arm + "-helper.log"))}
            with Path(active["stdout"]).open("w") as log, redirect_stdout(log):
                run = helper.arm(prepared, "a1-" + arm, MODE, 60, fixture="a1", dnpl="kalshi",
                                 dnpl_sources="kalshi,polymarket")
            active["path"] = result_spec[arm] = str(run)
            Path(run, "COMPARE-COMPUTE.json").write_text(json.dumps(
                {"before": before, "after_load": os.getloadavg(), "after_time": time.time()}, indent=2) + "\n")
            require(read(Path(run)/"RUN.json")["status"] == "READER_COMPLETE", "arm did not complete: " + str(run))
            snapshots = [json.loads(line) for line in (Path(run)/"reader.jsonl").read_text().splitlines()
                         if json.loads(line).get("kind") == "dom"]
            Path(run, "OBSERVATION-SCORE.json").write_text(json.dumps(
                scorer.score_run(Path(run), snapshots), indent=2, default=str) + "\n")
            runs.append(arm)
            active = None
            Path(out/"RUNS.json").write_text(json.dumps(
                {"completed": runs, "failed_arm": None, "spec": result_spec}, indent=2) + "\n")
    except BaseException as exc:
        Path(out/"RUNS.json").write_text(json.dumps(
            {"completed": runs, "failed_arm": active, "spec": result_spec}, indent=2) + "\n")
        Path(out/"INVALID.json").write_text(json.dumps(
            {"decision": "experiment_invalid", "reason": str(exc), "completed_arms": runs,
             "failed_arm": active, "spec": result_spec}, indent=2, default=str) + "\n")
        raise
    finally:
        if fresh:
            stop_chromium()
        for k in [k for k in os.environ if k.startswith("SPEED_SWITCH_")
                  or k in ("LOCAL_A1_TAPE", "LOCAL_A1_TAPE_SHA256", "LAB_CDP_URL", "LAB_CDP_DEFAULT_CONTEXT")]:
            del os.environ[k]
        os.environ.update(saved)
    return a1_consume(result_spec, out/"report", stable_backend_clock=stable_backend_clock)


def a1_prepare_candidate(helper_path, baseline_prepared, candidate_ref, repo="/Users/bain/bainluck"):
    """The candidate's backend beside the baseline's EXACT frontend build.

    Preparation, not measurement: refuses unless the two frontend trees are
    byte-identical in git, then clones the baseline's built frontend (APFS
    clone, no rebuild) and archives only the candidate's backend."""
    import os
    import subprocess
    import tarfile

    baseline_prepared = Path(baseline_prepared).resolve()
    base = read(baseline_prepared/"PREPARED.json")
    sha = subprocess.check_output(["git", "-C", repo, "rev-parse", "--verify", candidate_ref + "^{commit}"],
                                  text=True).strip()
    require(subprocess.run(["git", "-C", repo, "diff", "--quiet", base["sha"], sha, "--", "frontend"]).returncode == 0,
            "candidate frontend tree differs from the baseline; one build cannot serve both")
    dst = Path(helper_path).resolve().parent/"prepared"/f"{sha}-a1-frontend-{base['sha'][:8]}"
    require(not dst.exists(), f"already prepared: {dst}")
    src = dst/"source"
    src.mkdir(parents=True)
    subprocess.run(["cp", "-cR", str(baseline_prepared/"source"/"frontend"), str(src/"frontend")], check=True)
    archive = dst/"backend.tar"
    subprocess.run(["git", "-C", repo, "archive", "-o", str(archive), sha, "backend"], check=True)
    with tarfile.open(archive) as t:
        t.extractall(src, filter="data")
    archive.unlink()
    files = {}
    for root, dirs, names in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".next", "__pycache__")]
        for name in names:
            f = Path(root)/name
            files[str(f.relative_to(src))] = digest(f)
    manifest = {"sha": sha, "files": files, "lock": base["lock"], "build_id": base["build_id"],
                "installed_dependency_lock_sha256": base.get("installed_dependency_lock_sha256"),
                "lifecycle_helper_sha256": base.get("lifecycle_helper_sha256"),
                "frontend_build_source_sha": base.get("frontend_build_source_sha", base["sha"]),
                "frontend_build_reuse": "Byte-identical frontend tree verified with git diff; "
                                        "APFS clone of the baseline's production .next build"}
    Path(dst/"PREPARED.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return dst
