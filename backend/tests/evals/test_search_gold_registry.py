"""Guards for the gold-query Search registry and its results adapter (queue 313).

The registry is GENERATED (`scripts/evals/build_search_gold_registry.py`), so the
first test is a staleness ratchet: edit the generator, forget to regenerate, and
CI says so. The rest guard the two ways a gold set silently stops measuring
anything — an invented entity id, and an adapter that mints identity out of
display text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evals.build_search_gold_registry import (
    GOLD_ROWS,
    GOLD_SET_SOURCE,
    KIND_SHAPE,
    MC_CANDIDATES,
    NON_DRAFT_SOURCES,
    build_registry,
)
from scripts.evals.probe_registry import filter_probes, load_registry, validate_registry
from scripts.evals.search_results_producer import TYPE_MAP, map_suggestion

REGISTRY_PATH = Path(__file__).parents[2] / "scripts" / "evals" / "search_gold_probes.json"

# The gold set is 74 raw rows / 71 unique queries. Note that the repo's own
# ``parse_gold_markdown`` reports only 70/67: its ``^Desktop Recents:`` regex does
# not match the file's ``Desktop Recents (autocomplete-aided):`` heading, so it
# silently drops all four desktop queries. The count below is the true one.
GOLD_SET_UNIQUE_QUERIES = 71


def _probes() -> list[dict]:
    return filter_probes(load_registry(REGISTRY_PATH), task_type="search_entity", split="test")


def test_committed_registry_matches_its_generator() -> None:
    """The committed JSON is generated output — regenerate it, never hand-edit it."""

    expected = json.dumps(build_registry(), indent=2, ensure_ascii=False) + "\n"
    assert REGISTRY_PATH.read_text(encoding="utf-8") == expected, (
        "search_gold_probes.json is stale — re-run "
        "python scripts/evals/build_search_gold_registry.py --out scripts/evals/search_gold_probes.json"
    )


def test_registry_validates_clean() -> None:
    assert validate_registry(build_registry()["probes"]) == []


def test_every_gold_query_is_either_migrated_or_an_open_question() -> None:
    """No query may be silently dropped: migrated + MC candidates must be the whole set.

    LAT-P033: `migrated` counts only rows that came FROM the draft. Probes added
    from a measured production defect (`NON_DRAFT_SOURCES`, e.g. `fed`/#1732) are
    subtracted, because this invariant is a statement about ALEX'S DRAFT — "none
    of the 71 queries he approved was silently dropped". Growing the 71 to absorb
    a defect-derived probe would have turned the constant into "however many rows
    exist today", which cannot fail and so checks nothing.
    """

    migrated = len(GOLD_ROWS) - len(NON_DRAFT_SOURCES)
    deferred = sum(len(queries) for queries, _ in MC_CANDIDATES)
    assert migrated + deferred == GOLD_SET_UNIQUE_QUERIES


def test_defect_derived_probes_are_declared_and_carry_their_issue() -> None:
    """A non-draft probe must not borrow the gold draft's provenance.

    The subtraction above is only honest if `NON_DRAFT_SOURCES` is the complete
    list of rows that did not come from the draft — otherwise it becomes a knob
    for making the accounting balance.
    """

    declared = set(NON_DRAFT_SOURCES)
    assert declared <= {row[0] for row in GOLD_ROWS}, "declared a non-draft query that has no row"

    for probe in _probes():
        query = probe["presentation"]["query"]
        source = probe["evidence"]["source"]
        if query in declared:
            assert source == NON_DRAFT_SOURCES[query][0]
            assert probe["lifecycle"]["issue_gotcha"] == NON_DRAFT_SOURCES[query][1]
            assert "gold_queries_draft" not in source
        else:
            assert source == GOLD_SET_SOURCE


def test_no_duplicate_queries_or_probe_keys() -> None:
    probes = _probes()
    queries = [probe["presentation"]["query"].casefold() for probe in probes]
    keys = [probe["identity"]["probe_key"] for probe in probes]
    assert len(set(queries)) == len(queries)
    assert len(set(keys)) == len(keys)


def test_expected_entities_are_never_invented() -> None:
    """Every expected id must use a kind the adapter can actually emit.

    An id like ``person:taylor-swift`` would validate fine and score forever at
    zero, because no surface can ever return it. That is P8's corruption mode:
    the baseline would measure a fiction rather than Search.
    """

    emittable = {prefix for _, prefix, _, _ in TYPE_MAP.values()}
    for probe in _probes():
        answer = probe["oracle"]["answer"]
        for entity_id in [answer["expected_entity_id"], *answer["allowed_entity_ids"]]:
            kind = entity_id.split(":", 1)[0]
            assert kind in emittable, f"{probe['identity']['probe_key']} expects unemittable kind {kind!r}"
            assert not entity_id.startswith("unresolved:")


def test_alternatives_share_the_expected_kind() -> None:
    """A cross-kind alternative can never pass, so it must never be recorded as one.

    ``_score_probe`` compares ``item_type`` by strict equality and ``surface``
    against a fixed list, so an allowed entity of a different kind fails on
    surface/type even when its id matches — scoring a false failure that reads
    as a Search defect. Three rows hit this on the first run of this queue.
    """

    for probe in _probes():
        answer = probe["oracle"]["answer"]
        expected_kind = answer["expected_entity_id"].split(":", 1)[0]
        surface, item_type = KIND_SHAPE[expected_kind]
        assert answer["expected_surfaces"] == [surface]
        assert answer["expected_item_type"] == item_type
        for alternative in answer["allowed_entity_ids"]:
            assert alternative.split(":", 1)[0] == expected_kind, (
                f"{probe['identity']['probe_key']}: cross-kind alternative {alternative!r} can never pass"
            )


def test_xfail_is_reserved_for_known_broken_and_carries_an_issue() -> None:
    """``xfail`` must not be used for ambiguity — the scorer exits 1 on ``xpass``."""

    for probe in _probes():
        lifecycle = probe["lifecycle"]
        if lifecycle["known_failure_status"] == "xfail":
            assert lifecycle["issue_gotcha"], probe["identity"]["probe_key"]
            assert not probe["oracle"]["answer"]["allowed_entity_ids"], (
                "an xfail probe with alternatives is an ambiguity wearing the wrong marker"
            )


def test_both_gold_halves_survive_the_migration() -> None:
    """P10: the real/coverage split is the reason the set is shaped this way."""

    halves = {probe["identity"]["gold_half"] for probe in _probes()}
    assert halves == {"real", "coverage"}


def test_all_probes_share_one_split_so_no_group_can_leak() -> None:
    probes = _probes()
    assert {probe["isolation"]["split"] for probe in probes} == {"test"}
    for probe in probes:
        assert probe["isolation"]["real_world_group_key"]


def test_queries_that_name_the_same_thing_share_a_group_key() -> None:
    """The group is the indivisible split unit, so aliases must not be separable."""

    groups = {
        probe["presentation"]["query"]: probe["isolation"]["real_world_group_key"]
        for probe in _probes()
    }
    assert groups["pats"] == groups["patriots"]
    assert groups["the open"] == groups["british open"] == groups["The Open Championship Winner"]
    assert groups["world cup"] == groups["2026 FIFA World Cup"]


@pytest.mark.parametrize(
    ("suggestion", "expected_id", "expected_type"),
    [
        ({"type": "team", "team_slug": "boston-red-sox-mlb"}, "team:boston-red-sox-mlb", "team"),
        ({"type": "event", "event_id": "15189221"}, "event:15189221", "event"),
        ({"type": "event_concept", "event_key": "event:golf:the-open-championship"},
         "concept:event:golf:the-open-championship", "concept"),
        ({"type": "futures", "market_id": 113466}, "market:113466", "futures"),
        ({"type": "hub", "competition": "golf"}, "hub:golf", "hub"),
    ],
)
def test_adapter_maps_each_suggestion_type_to_its_own_identifier(
    suggestion: dict, expected_id: str, expected_type: str
) -> None:
    row = map_suggestion(suggestion, 1)
    assert row["entity_id"] == expected_id
    assert row["item_type"] == expected_type
    assert row["rank"] == 1


def test_adapter_never_mints_identity_from_display_text() -> None:
    """A missing id must read as unresolved, not be back-filled from the label.

    A coerced id could collide with a real expected id and score a pass. This is
    live, not hypothetical: typeahead returns Boston Celtics with no
    ``team_slug`` today.
    """

    row = map_suggestion({"type": "team", "text": "Boston Celtics"}, 1)
    assert row["entity_id"] == "unresolved:team:missing_team_slug"
    assert "celtics" not in row["entity_id"].casefold()

    unknown = map_suggestion({"type": "person", "text": "Taylor Swift"}, 2)
    assert unknown["entity_id"] == "unresolved:unmapped_type:person"
