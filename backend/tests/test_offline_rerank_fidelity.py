"""The offline harness must score the world the server runs — LAT-P050.

The measured failure this file exists to make impossible again
--------------------------------------------------------------
On production v3804, same 46 gold probes, same grader:

* production, deployed:                      **35/44**, MRR 0.804
* the harness re-ranking production's OWN output: **30/44**, MRR 0.721

Re-ranking a capture of the scorer's own output, with the same scorer, should be
approximately idempotent. It was not: five passes were destroyed — ``bruins``,
``celtics``, ``patriots``, ``red-sox``, ``yankees``. Every one a TEAM, and every
one for one reason: ``typeahead_search`` ranks a team on its aliases and then
STRIPS them before responding (evidence is not payload). The harness re-ranked
the response, so it re-ranked teams with their aliases withheld. MC0 -> MC1, tie
with a market, lost on ``KIND_ORDER`` (team 4, market 2).

That is the same withheld-evidence defect the route was fixed for three times
(#1836, #1839, #1843), committed by the instrument that grades those fixes. It is
why a projected 39-41 band was published against an actual 32/44, and the old
docstring called the number a FLOOR while it was overstating.

So the fix is not a better field mapping. It is that the endpoint ECHOES the
``Evidence`` it ranked on (``debug_evidence=1``) and the harness rebuilds it
through the one shared wire form. These tests pin that agreement, and pin the
specimen of the old defect so a regression is a red test rather than a quietly
wrong number.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.utils.search_match_class import (
    EVIDENCE_WIRE_KEYS,
    Evidence,
    evidence_from_wire,
    evidence_to_wire,
    rank,
)

REPO_BACKEND = Path(__file__).resolve().parents[1]
RERANK = REPO_BACKEND / "scripts" / "evals" / "search_offline_rerank.py"


# ---------------------------------------------------------------------------
# 1. The wire form is exact, and cannot silently lose a field
# ---------------------------------------------------------------------------


class TestTheWireFormIsExact:
    @pytest.mark.parametrize(
        "ev",
        [
            Evidence(name="Boston Celtics", aliases=("Celtics", "BOS"), kind="team",
                     sport_key="basketball_nba"),
            Evidence(name="NBA Champion", outcomes=("Celtics", "Thunder"),
                     kind="futures", sport_key="basketball_nba"),
            Evidence(name="Emmys", kind="event_concept", derived=True),
            Evidence(name=""),
            Evidence(name="x", within_tier=(1, 2.5, "z")),
        ],
    )
    def test_round_trip_is_identity(self, ev):
        assert evidence_from_wire(evidence_to_wire(ev)) == ev

    def test_wire_is_json_safe(self):
        ev = Evidence(name="a", aliases=("b",), outcomes=("c",), within_tier=(1,))
        assert evidence_from_wire(json.loads(json.dumps(evidence_to_wire(ev)))) == ev

    def test_every_evidence_field_crosses_the_wire(self):
        """A field added to `Evidence` without a wire decision fails HERE.

        Otherwise it would simply not cross, and the harness would diverge from
        the endpoint by exactly one silent field — which is the whole bug, in
        miniature, arriving again later.
        """
        assert {f.name for f in dataclasses.fields(Evidence)} == set(EVIDENCE_WIRE_KEYS)

    def test_missing_keys_do_not_crash_and_do_not_invent(self):
        ev = evidence_from_wire({})
        assert ev == Evidence(name="", kind="market")
        assert ev.derived is False and ev.aliases == () and ev.outcomes == ()


# ---------------------------------------------------------------------------
# 2. The specimen: withholding aliases is what cost the five team probes
# ---------------------------------------------------------------------------


def _celtics_field():
    """The `celtics` probe as production actually returned it on v3804."""
    team = Evidence(
        name="Boston Celtics", aliases=("Celtics", "BOS"), kind="team",
        sport_key="basketball_nba",
    )
    market = Evidence(
        name="Tadcaster Albion AFC vs. Stalybridge Celtic FC", kind="futures",
        sport_key="soccer",
    )
    return team, market


class TestWithheldAliasesDemoteTheRightAnswer:
    def test_with_aliases_the_team_wins(self):
        team, market = _celtics_field()
        assert rank("celtics", [(market, "market"), (team, "team")])[0] == "team"

    def test_without_aliases_a_soccer_market_wins(self):
        """The OLD harness's world. This test asserts a DEFECT on purpose.

        Gotcha #130 governs it: a test that asserts defective behaviour locks the
        defect in, so read the assertion as a sentence and ask whether you would
        sign it as a product claim. "Searching `celtics` should answer with
        Stalybridge Celtic FC" — obviously not. It is signed here as a SPECIMEN
        of the instrument's error, named as such, and its only job is to fail if
        someone reintroduces alias-free construction. If the pairing below ever
        needs "fixing", the fix belongs in the harness, not in this assertion.
        """
        team, market = _celtics_field()
        stripped = dataclasses.replace(team, aliases=())
        assert rank("celtics", [(market, "market"), (stripped, "team")])[0] == "market"


# ---------------------------------------------------------------------------
# 3. Idempotence — the armed control on the instrument itself
# ---------------------------------------------------------------------------


def _capture(fidelity: str, probes: list[dict]) -> dict:
    return {
        "metadata": {"adapter_version": "typeahead-adapter/v2",
                     "evidence_fidelity": fidelity},
        "results": probes,
    }


def _probe_from(query: str, ranked: list[tuple[Evidence, str]]) -> dict:
    """Build a capture probe the way the producer does from a RANKED answer."""
    return {
        "probe_key": f"p-{query}",
        "query": query,
        "has_evidence": True,
        "candidates": [
            {
                "entity_id": eid,
                "surface": ev.kind,
                "item_type": ev.kind,
                "rank": i + 1,
                "display_name": ev.name,
                "evidence": evidence_to_wire(ev),
            }
            for i, (ev, eid) in enumerate(ranked)
        ],
    }


class TestRerankingADeployedCaptureIsIdempotent:
    """The property that would have caught this before it was published.

    A capture is the scorer's own output. Re-ranking it with the same scorer and
    the SAME evidence must return the same order. Any harness that fails this is
    modelling a different server, whatever its projection says.
    """

    def _order(self, doc):
        sys.path.insert(0, str(REPO_BACKEND / "scripts" / "evals"))
        from search_offline_rerank import rerank_document

        out = rerank_document(doc)
        return [[c["entity_id"] for c in p["candidates"]] for p in out["results"]]

    def test_exact_fidelity_preserves_the_deployed_order(self):
        team, market = _celtics_field()
        pairs = [(team, "team:boston-celtics"), (market, "market:58904833")]
        ranked = rank("celtics", [(ev, (ev, eid)) for ev, eid in pairs])
        probe = _probe_from("celtics", [(ev, eid) for ev, eid in ranked])

        assert self._order(_capture("exact", [probe])) == [
            [eid for _, eid in ranked]
        ], "re-ranking the scorer's own output changed it — the harness is not the server"

    def test_legacy_fidelity_does_not_preserve_it_and_says_so(self):
        """The measured 35 -> 30, reproduced in miniature and LABELLED.

        Legacy is allowed to differ — it cannot see aliases. What it may never do
        is present that difference as a floor, so the label is asserted with the
        divergence.
        """
        team, market = _celtics_field()
        legacy = {
            "metadata": {},  # unlabelled == v1 == legacy
            "results": [{
                "probe_key": "p-celtics",
                "query": "celtics",
                "candidates": [
                    {"entity_id": "team:boston-celtics", "surface": "team",
                     "item_type": "team", "rank": 1, "display_name": team.name},
                    {"entity_id": "market:58904833", "surface": "market",
                     "item_type": "futures", "rank": 2, "display_name": market.name},
                ],
            }],
        }
        sys.path.insert(0, str(REPO_BACKEND / "scripts" / "evals"))
        from search_offline_rerank import rerank_document

        out = rerank_document(legacy)
        assert out["metadata"]["rerank_fidelity"] == "legacy"
        assert "not a floor" in out["metadata"]["projection"]
        assert out["results"][0]["candidates"][0]["entity_id"] == "market:58904833", (
            "the specimen stopped reproducing; if the harness got better, move "
            "this test rather than deleting the record of why it exists"
        )


# ---------------------------------------------------------------------------
# 4. Fidelity labelling and the pipeline gate
# ---------------------------------------------------------------------------


class TestFidelityIsNeverAssumed:
    def test_unlabelled_capture_is_legacy_not_exact(self):
        sys.path.insert(0, str(REPO_BACKEND / "scripts" / "evals"))
        from search_offline_rerank import rerank_document

        out = rerank_document({"metadata": {}, "results": []})
        assert out["metadata"]["rerank_fidelity"] == "legacy"

    def test_bogus_fidelity_falls_to_legacy(self):
        sys.path.insert(0, str(REPO_BACKEND / "scripts" / "evals"))
        from search_offline_rerank import rerank_document

        out = rerank_document({"metadata": {"evidence_fidelity": "perfect"},
                               "results": []})
        assert out["metadata"]["rerank_fidelity"] == "legacy"

    @pytest.mark.parametrize(
        "fidelity,required,expect_exit",
        [("exact", "exact", 0), ("legacy", "exact", 2), ("legacy", "legacy", 0),
         ("partial", "exact", 2), ("exact", "legacy", 0)],
    )
    def test_require_fidelity_gate(self, tmp_path, fidelity, required, expect_exit):
        src = tmp_path / "in.json"
        src.write_text(json.dumps(_capture(fidelity, [])))
        proc = subprocess.run(
            [sys.executable, str(RERANK), "--in", str(src),
             "--out", str(tmp_path / "out.json"), "--require-fidelity", required],
            capture_output=True, text=True, cwd=str(REPO_BACKEND),
        )
        assert proc.returncode == expect_exit, proc.stderr


# ---------------------------------------------------------------------------
# 5. The producer preserves what the scorer reads
# ---------------------------------------------------------------------------


class TestProducerPreservesEvidence:
    def _producer(self):
        sys.path.insert(0, str(REPO_BACKEND / "scripts" / "evals"))
        import search_results_producer as p

        return p

    def test_suggestion_is_preserved_verbatim(self):
        p = self._producer()
        s = {"type": "team", "text": "Boston Celtics", "abbreviation": "BOS",
             "team_slug": "boston-celtics", "sport_key": "basketball_nba"}
        row = p.map_suggestion(s, 1)
        assert row["suggestion"] == s
        assert row["entity_id"] == "team:boston-celtics"

    def test_evidence_is_attached_when_supplied(self):
        p = self._producer()
        ev = evidence_to_wire(Evidence(name="Boston Celtics", aliases=("Celtics",),
                                       kind="team"))
        row = p.map_suggestion({"type": "team", "text": "Boston Celtics",
                                "team_slug": "boston-celtics"}, 1, ev)
        assert evidence_from_wire(row["evidence"]).aliases == ("Celtics",)

    def test_absent_evidence_is_absent_not_empty(self):
        """gotcha #53: "no echo" and "an echo of nothing" must not read alike."""
        p = self._producer()
        row = p.map_suggestion({"type": "team", "text": "X", "team_slug": "x"}, 1)
        assert "evidence" not in row

    def test_unmapped_type_still_preserves_the_suggestion(self):
        p = self._producer()
        row = p.map_suggestion({"type": "wormhole", "text": "?"}, 1)
        assert row["entity_id"].startswith("unresolved:")
        assert row["suggestion"]["type"] == "wormhole"

    @pytest.mark.parametrize(
        "payload,n,expected_kept",
        [
            ({"_evidence": [{"name": "a"}, {"name": "b"}]}, 2, True),
            ({"_evidence": [{"name": "a"}]}, 2, False),        # short
            ({"_evidence": [{"name": "a"}] * 3}, 2, False),    # long
            ({}, 2, False),                                    # no echo at all
            ({"_evidence": "nope"}, 2, False),                 # wrong type
            ({"_evidence": []}, 0, True),                      # empty answer, aligned
        ],
    )
    def test_misaligned_echo_is_dropped_whole(self, payload, n, expected_kept):
        p = self._producer()
        got = p.aligned_evidence(payload, [{}] * n)
        assert (got is not None) is expected_kept


class TestLegacyPathUsesTheEndpointsOwnConstruction:
    """The legacy path must route through `_typeahead_evidence`, not a hand-roll.

    Pinned behaviourally rather than by import-inspection: a futures suggestion
    whose NAME says nothing about the query but whose `top_outcomes` do is MC4
    under the endpoint's constructor and MC5 under a name-only hand-roll.

    The competitor is a CONCEPT on purpose. Concepts hold the best `KIND_ORDER`
    (0) and markets are 2, so at equal match class the concept wins — which
    means dropping the market's outcomes flips the answer. A team competitor
    would NOT flip it (team is kind 4 and loses the tie anyway), and a mutation
    that cannot flip the assertion is a mutation the harness scores as killed
    while proving nothing.
    """

    def _doc(self, market_suggestion):
        return {
            "metadata": {},
            "results": [{
                "probe_key": "p", "query": "mahomes",
                "candidates": [
                    {   # name says nothing; the OUTCOME owns the query
                        "entity_id": "market:1", "surface": "market",
                        "item_type": "futures", "rank": 1,
                        "display_name": "NFL MVP",
                        "suggestion": market_suggestion,
                    },
                    {   # matches nothing it owns -> MC5, but best kind
                        "entity_id": "concept:1", "surface": "concept",
                        "item_type": "concept", "rank": 2,
                        "display_name": "Super Bowl",
                        "suggestion": {"type": "concept", "text": "Super Bowl"},
                    },
                ],
            }],
        }

    def _top(self, doc):
        sys.path.insert(0, str(REPO_BACKEND / "scripts" / "evals"))
        from search_offline_rerank import rerank_document

        return rerank_document(doc)["results"][0]["candidates"][0]["entity_id"]

    def test_outcomes_on_the_wire_reach_the_scorer(self):
        top = self._top(self._doc({
            "type": "futures", "text": "NFL MVP",
            "top_outcomes": [{"name": "Patrick Mahomes"}],
        }))
        assert top == "market:1", (
            "the outcome evidence on the wire did not reach the scorer — the "
            "legacy path is hand-rolling Evidence again"
        )

    def test_and_without_those_outcomes_the_concept_would_win(self):
        """Proves the assertion above is load-bearing, not incidentally true."""
        assert self._top(self._doc({"type": "futures", "text": "NFL MVP"})) == "concept:1"
