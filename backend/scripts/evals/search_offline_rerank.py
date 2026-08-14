"""Apply the tier-lexicographic scorer to CAPTURED producer output (ruling 041).

Why this exists, and what it is honestly worth
----------------------------------------------
The gold-set instrument is end-to-end: ``search_results_producer`` fetches
``/api/events/typeahead`` from production, ``search_gold_eval`` grades the
answer. A ranking change therefore cannot be measured until it is DEPLOYED, and
a program lane never pushes. That leaves a real gap between "the scorer is
written" and "the number moved", and the gap is where unfalsifiable claims live.

This closes it partially and says exactly how partially. It re-ranks the
candidate list each probe already returned, using the same
``app.utils.search_match_class`` the endpoint uses, and emits a producer-shaped
file the unmodified scorer can grade. Same probes, same instrument, same grader.

THE BIAS IS TWO-SIDED. IT IS NOT A FLOOR. (LAT-P050)
----------------------------------------------------
This file used to claim its projection was "biased LOW" and therefore a floor —
"every one of those can only IMPROVE the real result relative to this". That
claim was false, it was load-bearing, and it is why a ratified 39-41 band was
published against an actual 32/44.

Measured 2026-08-13 against production v3804, same 46 probes, same grader:

===========================================  ==============
production, deployed                          **35/44**  (MRR 0.804)
this harness re-ranking production's OWN out  **30/44**  (MRR 0.721)
===========================================  ==============

Re-ranking a capture of the scorer's own output with the same scorer should be
approximately IDEMPOTENT. Instead it destroyed five passes — ``bruins``,
``celtics``, ``patriots``, ``red-sox``, ``yankees``: every one a team, and every
one for the same reason. The endpoint ranks a team on its aliases
(``alternate_names`` + ``abbreviation``) and strips them before responding,
because evidence is not payload. A team re-ranked without its aliases falls MC0
-> MC1, ties with a market, and loses on ``KIND_ORDER`` (team 4, market 2).

So the old harness withheld from the scorer exactly the evidence the ROUTE has
now been fixed three times for withholding (#1836, #1839, #1843). The instrument
contained the bug class it was grading. It could overstate *and* understate, and
it did both.

The two directions, named so neither is forgotten:

* **LOW** — it can only reorder candidates the deployed assembly already
  admitted, so a correct answer that never made the response is invisible here
  and stays a failure in the projection.
* **HIGH** — it scores a 7-candidate field where production scores the whole
  pool. Winning a seven-way contest is not winning a three-hundred-way one.

Fidelity, and why you must read it
----------------------------------
``metadata.evidence_fidelity`` from the capture decides what this run means:

``exact``
    Every probe carries the endpoint's own ``_evidence`` echo
    (``debug_evidence=1``, adapter v2). The scorer is handed the identical
    ``Evidence`` production handed it, rebuilt through the shared
    ``evidence_from_wire``. This is the only fidelity at which a rerank of a
    deployed capture is expected to reproduce the deployed grade — and
    ``tests/test_offline_rerank_fidelity.py`` asserts exactly that idempotence.
``partial``
    Some probes carry the echo. Reported, never averaged into a headline.
``legacy``
    None do (a v1 capture, or a deploy predating the echo). Evidence is rebuilt
    from the wire suggestion through the endpoint's own ``_typeahead_evidence``,
    which recovers ``outcomes``/``sport_key``/``abbreviation`` but CANNOT recover
    ``_aliases`` or ``_derived`` — the endpoint strips them. A legacy run is a
    projection of a different experiment and says so in its own metadata.

Usage
-----
    python scripts/evals/search_offline_rerank.py \\
        --in /tmp/typeahead_base.json --out /tmp/typeahead_reranked.json
    python scripts/evals/search_gold_eval.py \\
        --registry scripts/evals/search_gold_probes.json --split test \\
        --results /tmp/typeahead_reranked.json --mode entity_top_1
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.utils.search_match_class import (  # noqa: E402
    Evidence,
    evidence_from_wire,
    rank,
)

#: Producer `item_type`/`surface` -> the scorer's kind vocabulary. Used ONLY on
#: the legacy path; an `exact` capture carries the endpoint's own `kind`.
_KIND = {
    "futures": "futures",
    "market": "futures",
    "concept": "event_concept",
    "event_concept": "event_concept",
    "event": "event",
    "hub": "hub",
    "team": "team",
}

FIDELITIES = ("exact", "partial", "legacy")


def _legacy_evidence(candidate: dict) -> Evidence:
    """Best available `Evidence` for a candidate with no endpoint echo.

    Routed through the ENDPOINT's own `_typeahead_evidence` rather than
    hand-rolled here. That import is the point of the exercise: a second
    construction is a second thing to drift, and the drift is what published a
    39-41 band against a 32. What the wire cannot carry (`_aliases`,
    `_derived`) is absent rather than guessed, and the run is labelled `legacy`
    so the absence travels with the number.
    """
    suggestion = candidate.get("suggestion")
    if isinstance(suggestion, dict):
        from app.routes.events import _typeahead_evidence

        return _typeahead_evidence(suggestion)

    # A v1 capture kept no suggestion at all: identity and display text only.
    kind = _KIND.get(
        (candidate.get("item_type") or candidate.get("surface") or "").lower(),
        "futures",
    )
    return Evidence(name=candidate.get("display_name") or "", kind=kind)


def rerank_probe(probe: dict) -> dict:
    candidates = probe.get("candidates") or []
    if not candidates:
        return probe

    pairs = []
    for c in candidates:
        echo = c.get("evidence")
        ev = evidence_from_wire(echo) if isinstance(echo, dict) else _legacy_evidence(c)
        pairs.append((ev, c))

    ordered = rank(probe.get("query") or "", pairs)

    # `rank` drops derived-only evidence. On an `exact` capture that CAN fire:
    # production drops before it responds, so a captured row is normally a
    # survivor, but a capture taken against a different deploy than the tree
    # being projected may well contain one this tree would drop. Record it as a
    # number instead of asserting it away — the old assert could not fire at all
    # (evidence was never derived) and so proved nothing.
    out = dict(probe)
    out["dropped_unrankable"] = len(candidates) - len(ordered)
    out["candidates"] = [{**c, "rank": i + 1} for i, c in enumerate(ordered)]
    return out


def rerank_document(doc: dict) -> dict:
    doc = dict(doc)
    src_meta = dict(doc.get("metadata") or {})
    fidelity = src_meta.get("evidence_fidelity")
    if fidelity not in FIDELITIES:
        # An unlabelled capture is a v1 capture. Name it rather than defaulting
        # to the flattering reading.
        fidelity = "legacy"

    doc["results"] = [rerank_probe(p) for p in doc.get("results", [])]

    meta = src_meta
    meta["reranked_by"] = "app.utils.search_match_class (ruling 041)"
    meta["rerank_fidelity"] = fidelity
    meta["projection"] = _PROJECTION_NOTE[fidelity]
    meta["dropped_unrankable_total"] = sum(
        int(p.get("dropped_unrankable") or 0) for p in doc["results"]
    )
    doc["metadata"] = meta
    return doc


_PROJECTION_NOTE = {
    "exact": (
        "PROJECTION at EXACT evidence fidelity: the scorer received the "
        "endpoint's own Evidence echo. Bias is TWO-SIDED, not a floor — it "
        "reorders only candidates the deployed assembly admitted (understates) "
        "and scores a 7-candidate field where production scores the whole pool "
        "(overstates). Not a deployed measurement."
    ),
    "partial": (
        "PROJECTION at PARTIAL evidence fidelity: only some probes carry the "
        "endpoint's Evidence echo; the rest were rebuilt from the wire and are "
        "missing aliases and the derived flag. Do not quote a single headline "
        "number from a partial run."
    ),
    "legacy": (
        "PROJECTION at LEGACY fidelity: NO probe carries the endpoint's "
        "Evidence echo, so aliases and the derived flag are absent — the two "
        "fields production ranks teams and concepts on. Measured on v3804 this "
        "path scored 30/44 against production's own 35/44 on the same capture. "
        "It is a different experiment, not a floor. Re-capture with adapter v2 "
        "against a deploy carrying `debug_evidence`."
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    ap.add_argument(
        "--require-fidelity",
        choices=FIDELITIES,
        help=(
            "Exit non-zero unless the capture is at least this faithful. Use "
            "`--require-fidelity exact` in any pipeline whose number will be "
            "quoted as a projection."
        ),
    )
    args = ap.parse_args()

    doc = rerank_document(json.load(open(args.src)))
    json.dump(doc, open(args.dst, "w"), indent=1)

    meta = doc["metadata"]
    summary = {
        "probes": len(doc["results"]),
        "with_top": sum(
            1 for p in doc["results"] if (p.get("candidates") or [{}])[0].get("entity_id")
        ),
        "evidence_fidelity": meta["rerank_fidelity"],
        "dropped_unrankable_total": meta["dropped_unrankable_total"],
    }
    print(json.dumps(summary, indent=1))

    if args.require_fidelity:
        wanted = FIDELITIES.index(args.require_fidelity)
        if FIDELITIES.index(meta["rerank_fidelity"]) > wanted:
            print(
                f"FIDELITY_TOO_LOW: capture is {meta['rerank_fidelity']!r}, "
                f"required at least {args.require_fidelity!r}",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
