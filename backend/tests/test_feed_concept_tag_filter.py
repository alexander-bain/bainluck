"""UX-P177 — the concept tier was GATED by the sport tag and never FILTERED by it.

═══ THE DEFECT ═══

`routes/feed.py` had one hand-written set deciding whether a `sport:`-tagged feed
build should run the event-concept tier at all:

    _concept_allowed = {"sport:mma", "sport:motorsports", "sport:f1"}

and then, having admitted the build, it called the builder with no filter:

    return await _score_event_concepts(db, now, sport, ctx)

`sport` is the `?sport=` query parameter. Both readers of the tag path —
`/categories/[slug]` and `components/RelatedByTag.tsx` — send `tags` and nothing
else, so `sport` was always `None` and every source ran on every tagged build.

Measured on production 2026-08-29, one request per tag through the exact URL the
shipped surfaces build:

    ?tags=["sport:mma"]           16 concepts,  5 foreign (1 cycling + 4 F1)
    ?tags=["sport:motorsports"]   the SAME 16, 12 foreign (11 UFC + 1 cycling)
    ?tags=["sport:cycling"]        0            — skipped entirely
    ?tags=["sport:boxing"]         0            — correctly, no source

Two failures, opposite directions, one root:

* **Over-inclusion.** The gate admitted the build and then ignored the tag.
* **Under-inclusion.** `cycling` was missing from the hand-written set, so the
  one surface where the Vuelta belongs was the one surface that skipped it —
  while the Vuelta led the MMA and motorsports lists.

═══ WHY IT IS FIXED WHERE IT IS ═══

`event_concept_population.py` exists because "two copies of one list always
drift" — its own docstring. The allowlist in `feed.py` was exactly that second
copy of the alias vocabulary, one file over, and it had already drifted. So the
gate and the filter become ONE function next to the vocabulary it reads,
`CONCEPT_SPORT_ALIASES`, derived from `CONCEPT_SOURCES`.

The cache key was never the bug and is unchanged: it already carried the tag
tuple (`feed.py`, `_concept_key`). The BUILDER is what ignored it.

═══ WHAT THIS FILE PROVES, AND WHAT IT DOES NOT ═══

The reader-facing half — that a concept must render as a working `/event/...`
link rather than `/futures/undefined` — is a separate defect in a separate layer
and is proven in `frontend/__tests__/capture/relatedByTagConceptCapture.test.tsx`.
The two are genuinely independent: a perfectly filtered backend still handed
`RelatedByTag` four dead links.

The last class here is the one UX-P176 paid for: most of these tests REPLAY the
admission decision as a pure function, which stays green if the route stops
calling it. `TestTheRouteStillRunsWhatThisModuleDecides` pins the call sites.
"""

from __future__ import annotations

import inspect

import pytest

from app.utils import event_concept_population as population
from app.utils.event_concept_population import (
    CONCEPT_SOURCES,
    CONCEPT_SPORT_ALIASES,
    _source_applies,
    concept_filter_for_tags,
)

# The recording double the single-scan suite already drives this module with.
from tests.test_feed_concept_single_scan import _RecordingDB, _categories_named


def _sources_that_run(sport_filter) -> list[str]:
    """The labels `list_all_concepts` would run for this filter."""
    return [s.label for s in CONCEPT_SOURCES if _source_applies(s.aliases, sport_filter)]


# ---------------------------------------------------------------------------
# 1. The vocabulary is DERIVED, not a second hand-written copy
# ---------------------------------------------------------------------------


class TestTheAliasVocabularyIsDerived:
    def test_it_is_exactly_the_registered_aliases_minus_the_wildcard(self):
        expected = {
            alias
            for source in CONCEPT_SOURCES
            for alias in source.aliases
            if alias != "all"
        }
        assert CONCEPT_SPORT_ALIASES == expected

    def test_it_contains_cycling__the_alias_the_hand_written_set_had_lost(self):
        """The under-inclusion half, named.

        `{"sport:mma", "sport:motorsports", "sport:f1"}` never listed cycling, so
        `?tags=["sport:cycling"]` skipped the tier that holds the grand tours
        while the Vuelta sat on the MMA and motorsports pages.
        """
        assert "cycling" in CONCEPT_SPORT_ALIASES
        skip, sport_filter = concept_filter_for_tags(["sport:cycling"])
        assert skip is False
        assert _sources_that_run(sport_filter) == ["cycling"]

    def test_a_fourth_source_registered_tomorrow_is_covered_the_same_day(self):
        """The whole reason this is derived.

        A hardcoded set would leave a new source's tag skipped, and a skipped
        tier returns [] — indistinguishable from "this sport has nothing on"
        (gotcha #53).
        """
        for source in CONCEPT_SOURCES:
            for alias in source.aliases:
                if alias == "all":
                    continue
                skip, sport_filter = concept_filter_for_tags([f"sport:{alias}"])
                assert skip is False, f"{alias} would be skipped"
                assert source.label in _sources_that_run(sport_filter)


# ---------------------------------------------------------------------------
# 2. The admission decision itself, on the real inputs
# ---------------------------------------------------------------------------


class TestTheTagFilterDecidesBothHalves:
    @pytest.mark.parametrize(
        "tags,expected_skip,expected_sources",
        [
            # No sport tag at all — the unfiltered feed, unchanged.
            ([], False, ["ufc", "f1", "cycling"]),
            (None, False, ["ufc", "f1", "cycling"]),
            (["status:live"], False, ["ufc", "f1", "cycling"]),
            # THE FIX. One tag, one source.
            (["sport:mma"], False, ["ufc"]),
            (["sport:motorsports"], False, ["f1"]),
            (["sport:cycling"], False, ["cycling"]),
            (["sport:f1"], False, ["f1"]),
            (["sport:ufc"], False, ["ufc"]),
            # No source — skip the tier rather than build and discard it. This is
            # the half the old gate got right, and it is preserved.
            (["sport:soccer"], True, []),
            (["sport:boxing"], True, []),
            # More than one sport tag: the union, because no single alias says
            # "MMA or motorsports".
            (["sport:mma", "sport:motorsports"], False, ["ufc", "f1"]),
            # A named source alongside an unnamed one still runs the named one.
            (["sport:mma", "sport:soccer"], False, ["ufc"]),
        ],
    )
    def test_the_predicate_on_the_real_inputs(
        self, tags, expected_skip, expected_sources
    ):
        skip, sport_filter = concept_filter_for_tags(tags)
        assert skip is expected_skip
        assert ([] if skip else _sources_that_run(sport_filter)) == expected_sources

    def test_the_two_production_failures_are_both_gone(self):
        """The measured BEFORE, restated as an assertion.

        `sport:mma` served 5 foreign of 16 and `sport:motorsports` served the
        same 16 — the same list, because the builder never saw the tag. They must
        now disagree, and each must name only its own source.
        """
        _, mma = concept_filter_for_tags(["sport:mma"])
        _, motor = concept_filter_for_tags(["sport:motorsports"])

        assert mma != motor
        assert _sources_that_run(mma) == ["ufc"]
        assert _sources_that_run(motor) == ["f1"]
        assert "cycling" not in _sources_that_run(mma)
        assert "cycling" not in _sources_that_run(motor)
        assert "ufc" not in _sources_that_run(motor)


# ---------------------------------------------------------------------------
# 3. `_source_applies` grew a collection form; the single-string form is intact
# ---------------------------------------------------------------------------


class TestSourceApplies:
    ALIASES = ("mma", "all", "ufc")

    def test_no_filter_still_runs_every_source(self):
        assert _source_applies(self.ALIASES, None) is True
        assert _source_applies(self.ALIASES, ()) is True
        assert _source_applies(self.ALIASES, "") is True

    def test_the_single_string_form_is_unchanged(self):
        assert _source_applies(self.ALIASES, "mma") is True
        assert _source_applies(self.ALIASES, "cycling") is False

    def test_a_collection_matches_when_any_entry_names_the_source(self):
        assert _source_applies(self.ALIASES, ("mma",)) is True
        assert _source_applies(self.ALIASES, ("cycling", "mma")) is True
        assert _source_applies(self.ALIASES, ("cycling", "motorsports")) is False

    def test_a_collection_never_matches_on_a_substring(self):
        """`"mma" in ("mma","all","ufc")` is membership; `in` on a string is not.

        A bare string filter of "m" must not select the mma source.
        """
        assert _source_applies(self.ALIASES, "m") is False
        assert _source_applies(self.ALIASES, ("m",)) is False


# ---------------------------------------------------------------------------
# 4. The filter reaches the DB read — it narrows the scan, it does not post-filter
# ---------------------------------------------------------------------------


class TestTheFilterReachesTheQuery:
    @pytest.mark.asyncio
    async def test_a_tag_derived_filter_narrows_the_single_scan(self):
        """Not just "the wrong concepts are dropped" — never fetched.

        Post-filtering would have been the cheap fix and it would have kept
        scanning all three categories on every MMA page.
        """
        _, sport_filter = concept_filter_for_tags(["sport:mma"])
        db = _RecordingDB()
        await population.list_all_concepts(db, sport_filter=sport_filter)

        assert len(db.market_reads) == 1
        assert _categories_named(db.market_reads[0]) == {"mma"}

    @pytest.mark.asyncio
    async def test_a_multi_tag_filter_scans_exactly_the_named_categories(self):
        _, sport_filter = concept_filter_for_tags(
            ["sport:mma", "sport:cycling"]
        )
        db = _RecordingDB()
        await population.list_all_concepts(db, sport_filter=sport_filter)

        assert _categories_named(db.market_reads[0]) == {"mma", "cycling"}

    @pytest.mark.asyncio
    async def test_the_unfiltered_build_still_scans_all_three(self):
        """The control. A change that fixed the tagged feed by emptying the
        untagged one would pass every assertion above.
        """
        _, sport_filter = concept_filter_for_tags([])
        db = _RecordingDB()
        await population.list_all_concepts(db, sport_filter=sport_filter)

        assert _categories_named(db.market_reads[0]) == {
            s.category for s in CONCEPT_SOURCES
        }


# ---------------------------------------------------------------------------
# 5. The route still RUNS what everything above replays
# ---------------------------------------------------------------------------


class TestTheRouteStillRunsWhatThisModuleDecides:
    """Everything above is a pure-function replay of the route's decision.

    A replay-style guard is blind to the deletion of what it replays (UX-P176):
    strip the call out of `get_feed` and every test in this file stays green
    while the tier goes back to serving cycling on the MMA page. These are narrow
    NAMED pins on the two call sites, and each one is mutation-proven.
    """

    @staticmethod
    def _feed_source() -> str:
        from app.routes import feed

        return inspect.getsource(feed)

    def test_the_route_asks_this_module_for_the_decision(self):
        src = self._feed_source()
        assert "concept_filter_for_tags" in src, (
            "the feed no longer calls concept_filter_for_tags — the concept tier "
            "is deciding on the sport tag some other way"
        )
        assert "_tag_skip, _concept_sport_filter = concept_filter_for_tags(" in src

    def test_the_derived_filter_is_passed_to_the_builder(self):
        """The half that was missing. The gate existed; this line did not."""
        src = self._feed_source()
        assert "sport or _concept_sport_filter" in src, (
            "the concept builder is no longer given the tag-derived filter; it "
            "is gated by the sport tag and filtered by nothing, which is the "
            "exact UX-P177 defect"
        )

    def test_the_hand_written_allowlist_has_not_come_back(self):
        """Narrow and literal: the dead variable, not a blunt substring sweep.

        An over-broad source-level `not in` fails on a correct file. This names
        the one identifier that carried the drifted copy.
        """
        assert "_concept_allowed" not in self._feed_source()
