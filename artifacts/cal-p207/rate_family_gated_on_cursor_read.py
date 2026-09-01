#!/usr/bin/env python3
"""CAL-P207 / Q7+Q15: is the BEAT-TIMING report gated on the CURSOR read?

THE CLAIM UNDER TEST
--------------------
``_record_staged_rate`` (calibration_main_build.py:1531) documents itself as
recording "on EVERY terminal", on "the path that always runs, whatever the
terminal", and closes with "None of them records nothing."

Its ONLY call site is :1417, INSIDE ``_record_staged_convergence``'s ``try``,
downstream of ONE durable read (:1394) and behind FOUR exits that have nothing
to do with beat timing:

    :1399  not read.ok / envelope None   -> convergence_reason:{status}, return
    :1403  payload not a dict            -> convergence_reason:payload_shape, return
    :1407  committed_units not a list    -> convergence_reason:no_committed_units, return
    :1418  any exception                 -> convergence_reason:read_raised

Every gauge _record_staged_rate emits EXCEPT ``beats_to_publish`` is computed
from ``runner.ledger`` in-memory state that is available regardless of the read.
So the hypothesis is: a CURSOR-read failure silently erases the BEAT-TIMING
report, which is precisely the "skipped on beats that do not publish" defect
CAL-P066's docstring says it was written to end.

ARMS (the lane's control-arm law, ruling: five clauses)
-------------------------------------------------------
ARM 1 (reproduce a KNOWN hit): the gating is a SOURCE fact, not a statistical
      one. Re-derive it from the AST: assert _record_staged_rate has exactly one
      call site and that the call site is dominated by the read's early exits.
      If the AST says otherwise the whole finding is void.
ARM 2 (state the SHAPE): a hit is a beat carrying a `staged:convergence_reason:*`
      gauge AND missing `staged:units_this_beat`.
ARM 3 (report the FRACTION classified): every beat is classifiable here -- the
      two gauge names are either present or not -- so coverage must be 100%
      or the ring is the wrong population.
ARM 4 (name the POPULATION in the marker's noun): production BEATS, not gauges
      and not call sites. The marker will say "N of 168 beats".
ARM 5 (fail when the status quo would have been right): if the ring shows the
      cursor read never failed, this reports NOT-OBSERVED and refuses to call
      the coupling a defect-in-fact. A source-level coupling with zero observed
      hits is a LATENT coupling, and saying so is the point.
"""
import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "backend" / "app" / "tasks" / "calibration_main_build.py"
RING = ROOT / "artifacts" / "cal-p118" / "beat-ring-full.json"

RATE_FN = "_record_staged_rate"
CONV_FN = "_record_staged_convergence"

# Gauges _record_staged_rate can emit. Only beats_to_publish needs the read.
RATE_GAUGES_INDEPENDENT_OF_READ = [
    "staged:units_this_beat",
    "staged:units_completed_this_beat",
    "staged:unit_cost_reason:no_unit_completed",
    "staged:unit_ms_mean_completed",
    "staged:rate_reason:no_unit_ran",
    "staged:unit_ms_mean",
]
CONV_REASON_PREFIX = "staged:convergence_reason:"


# --------------------------------------------------------------------------
# ARM 1 -- the source fact. If this fails, nothing below means anything.
# --------------------------------------------------------------------------
def arm1_source() -> dict:
    tree = ast.parse(SRC.read_text())

    call_sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = getattr(f, "id", None) or getattr(f, "attr", None)
            if name == RATE_FN:
                call_sites.append(node.lineno)

    conv = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == CONV_FN
        ),
        None,
    )

    inside_conv = conv is not None and all(
        conv.lineno <= ln <= conv.end_lineno for ln in call_sites
    )

    # Count the early `return`s in the convergence function that precede the
    # call site -- each is a path on which the rate report is never written.
    dominating_returns = []
    if conv is not None and call_sites:
        site = min(call_sites)
        for n in ast.walk(conv):
            if isinstance(n, ast.Return) and n.lineno < site:
                dominating_returns.append(n.lineno)

    # Is the call site inside a Try? (a raise before it also erases the report)
    in_try = False
    if conv is not None and call_sites:
        site = min(call_sites)
        for n in ast.walk(conv):
            if isinstance(n, ast.Try) and n.body:
                lo = min(b.lineno for b in n.body)
                hi = max(getattr(b, "end_lineno", b.lineno) for b in n.body)
                if lo <= site <= hi:
                    in_try = True

    # Does the durable read precede the call site in the same function?
    read_lineno = None
    if conv is not None:
        for n in ast.walk(conv):
            if isinstance(n, ast.Call):
                nm = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                if nm == "read_snapshot_standalone":
                    read_lineno = n.lineno

    # How does the rate fn receive its data -- payload dict, or a derived scalar?
    kwarg_shape = None
    if call_sites:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                nm = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if nm == RATE_FN:
                    kwarg_shape = {
                        k.arg: ast.unparse(k.value) for k in node.keywords
                    }

    ok = (
        len(call_sites) == 1
        and inside_conv
        and in_try
        and read_lineno is not None
        and read_lineno < min(call_sites)
        and len(dominating_returns) >= 3
    )
    return {
        "arm": 1,
        "ok": ok,
        "call_sites": call_sites,
        "sole_call_site_inside_convergence": inside_conv,
        "call_site_inside_try": in_try,
        "durable_read_lineno": read_lineno,
        "returns_dominating_call_site": dominating_returns,
        "kwargs_at_call_site": kwarg_shape,
    }


# --------------------------------------------------------------------------
# ARMS 2-5 -- the population.
# --------------------------------------------------------------------------
def arms_population() -> dict:
    beats = json.loads(RING.read_text())
    total = len(beats)

    classified = 0
    read_failed = []          # beat carried a convergence_reason
    rate_missing = []         # beat lacked units_this_beat
    hits = []                 # both -> the coupling actually bit
    banked_missing = []       # the read-derived key absent

    for i, b in enumerate(beats):
        g = b.get("gauges")
        if not isinstance(g, dict):
            continue
        classified += 1
        reasons = [k for k in g if k.startswith(CONV_REASON_PREFIX)]
        has_rate = "staged:units_this_beat" in g
        has_banked = "staged:units_banked" in g
        if reasons:
            read_failed.append((i, reasons))
        if not has_rate:
            rate_missing.append(i)
        if not has_banked:
            banked_missing.append(i)
        if reasons and not has_rate:
            hits.append((i, reasons))

    # ARM 5 counterfactual: if the coupling were ABSENT (rate written
    # unconditionally), every beat would carry units_this_beat regardless of
    # convergence_reason. Under the status quo the two sets must coincide.
    # With zero read failures observed, the two hypotheses are INDISTINGUISHABLE
    # on this population -- and this arm must say so rather than claim a win.
    dissociable = len(read_failed) > 0

    return {
        "arm": "2-5",
        "population": "production beats (artifacts/cal-p118/beat-ring-full.json)",
        "total_beats": total,
        "classified": classified,
        "coverage_pct": round(100.0 * classified / total, 1) if total else 0.0,
        "beats_with_cursor_read_failure": len(read_failed),
        "beats_missing_units_this_beat": len(rate_missing),
        "beats_missing_units_banked": len(banked_missing),
        "observed_hits": len(hits),
        "hit_examples": hits[:5],
        "arms_dissociable": dissociable,
        "verdict": (
            "OBSERVED" if hits
            else ("NOT-OBSERVED (latent)" if not dissociable
                  else "REFUTED-ON-THIS-POPULATION")
        ),
    }


if __name__ == "__main__":
    a1 = arm1_source()
    out = {"arm1_source": a1}
    if not a1["ok"]:
        out["note"] = "ARM 1 FAILED -- the source no longer has the shape claimed; finding void."
        print(json.dumps(out, indent=2))
        sys.exit(1)
    out["arms_population"] = arms_population()
    print(json.dumps(out, indent=2))
