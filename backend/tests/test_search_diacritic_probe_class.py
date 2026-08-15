"""LAT-P058 / #1881 — the diacritic-folding probe class.

#1861's lesson, applied BEFORE the fix instead of after it: a defect with no
probe cannot be graded, so a window can report it fixed and nobody can check.
The Fable directive for LAT-P058 asked for gold probes on both of #1881's named
specimens *so the gate can grade it*. This file is what makes that claim
falsifiable.

What the class grades, and what it deliberately does not
--------------------------------------------------------
#1881 reads as a ranking bug. **It is not one.** `search_match_class.tokens()`
has folded accents since ruling 041, so both spellings of both specimens already
reach MC1 against the entity the issue says is missing — asserted next door in
`test_p11b_the_scorer_was_never_the_1881_defect`. The defect is upstream, in
RETRIEVAL: `unaccent` is not installed and `pg_trgm` sees `ö` and `o` as
different trigrams, so the SQL never hands the scorer the row.

Measured on production v3820, 2026-08-14 17:5x PDT:

    vuelta a espana  ->  1 suggestion   market 58675941  'Vuelta a Espana 2026: Winner'
    vuelta a españa  ->  0 suggestions  NOTHING AT ALL
    koln             ->  1 suggestion   team fortuna-koln-ii  (the only ASCII-named club)
    köln             ->  7 suggestions  all Köln-named, none of them the ASCII row

So these probes grade an INDEX change. The one scorer-side fold this window did
ship (`fragment_credit`, which was still comparing unfolded text at MC5) cannot
move them — which is precisely why they are recorded as `xfail` rather than as
a claim that something is fixed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils.search_match_class import MC1_ALL_TOKENS, Evidence, match_class

_REGISTRY = (
    Path(__file__).resolve().parents[1] / "scripts" / "evals" / "search_gold_probes.json"
)


def _load() -> tuple[dict, list[dict]]:
    registry = json.loads(_REGISTRY.read_text(encoding="utf-8"))
    diacritic = [
        p
        for p in registry["probes"]
        if p["identity"]["gold_family"] == "diacritic_folding"
    ]
    return registry["metadata"], diacritic


def test_the_class_exists_and_is_declared_in_metadata():
    metadata, probes = _load()
    assert probes, "#1881 has no probe — the gate cannot grade a fix for it"
    assert metadata["diacritic_probes"] == len(probes)


def test_the_class_is_canary_and_the_ledger_cohort_is_untouched():
    """Ruling 060: never grow a graded cohort in place.

    The §5 ledger of `docs/search-scoring-spec.md` is written against a 46-probe
    `test` split graded 44-wide. Putting these three probes there would move the
    denominator under every read ever taken — a measurement defect committed in
    the name of fixing one.
    """
    metadata, probes = _load()
    assert all(p["isolation"]["split"] == "canary" for p in probes)
    assert metadata["split_counts"]["test"] == 46
    assert metadata["migrated"] == 46, (
        "`migrated` counts probes from Alex's gold draft; #1881's are defect-derived"
    )


def test_both_directions_of_the_defect_are_covered_one_probe_each():
    """The property that tells a HALF-fix from a whole one.

    The defect is not symmetric and neither is its fix:

    * `vuelta a españa` — accented query, ASCII-named entity. A query-side fold
      (strip diacritics before matching) fixes this direction; #1881 calls that
      the "cheapest interim".
    * `koln` — ASCII query, accented-named entity. A query-side fold does
      NOTHING here; only an `unaccent` expression index over the column reaches
      it.

    If a future window reports #1881 closed and only the vuelta probe flipped,
    half the defect is still shipping and this test is how that is noticed.
    """
    _, probes = _load()
    lineage = {p["isolation"]["real_world_group_key"] for p in probes}
    assert lineage == {
        "diacritic:control",
        "diacritic:accented_query_ascii_entity",
        "diacritic:ascii_query_accented_entity",
    }


def test_the_control_passes_and_the_two_defects_are_recorded_as_failing():
    """A class with no passing control cannot distinguish a fix from an outage.

    `vuelta a espana` and `vuelta a españa` differ by exactly one character and
    resolve to the same market. One returns it at rank 1; the other returns
    nothing. With the control in the set, no explanation other than the fold
    survives — not coverage, not ranking, not the entity's existence.
    """
    _, probes = _load()
    by_query = {p["presentation"]["query"]: p for p in probes}
    assert by_query["vuelta a espana"]["lifecycle"]["known_failure_status"] == "pass"
    assert by_query["vuelta a españa"]["lifecycle"]["known_failure_status"] == "xfail"
    assert by_query["koln"]["lifecycle"]["known_failure_status"] == "xfail"
    # The pair must point at the SAME entity, or it is not a control.
    assert (
        by_query["vuelta a espana"]["oracle"]["answer"]["expected_entity_id"]
        == by_query["vuelta a españa"]["oracle"]["answer"]["expected_entity_id"]
        == "market:58675941"
    )


def test_every_probe_carries_the_issue_and_a_measured_note():
    _, probes = _load()
    for p in probes:
        assert p["lifecycle"]["issue_gotcha"] == "#1881"
        assert p["lifecycle"]["difficulty"] == "discrimination"
        assert "v3820" in p["oracle"]["evidence"], (
            "every probe in this class must cite the production read it was "
            "specimened from — an unmeasured probe is an assertion"
        )


@pytest.mark.parametrize(
    "query, entity_name",
    [
        ("vuelta a espana", "Vuelta a Espana 2026: Winner"),
        ("vuelta a españa", "Vuelta a Espana 2026: Winner"),
        ("koln", "1. FC Köln"),
        ("köln", "1. FC Köln"),
    ],
)
def test_the_scorer_cannot_be_what_flips_these_probes(query, entity_name):
    """The premise check, pinned.

    Every one of these queries ALREADY scores MC1 — the best non-exact class —
    against the entity the probe expects. There is no scorer change that could
    improve any of them, so if one of these probes flips to green, the thing
    that flipped it was retrieval. Stated as a test so a future window cannot
    credit a scorer tweak with closing #1881.
    """
    assert match_class(query, Evidence(name=entity_name)) == MC1_ALL_TOKENS
