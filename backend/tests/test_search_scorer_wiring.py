"""`/search` adopts the scorer — and takes #1839's guard with it (LAT-P049).

Ruling 041 says typeahead is the measured surface and `/search` follows the same
order. Only typeahead was wired. Wiring the second surface is not a copy, and the
window that pre-diagnosed it said why: `/search` carried the SAME first-writer-
wins concept guard that produced #1839, mild only because no scorer read the rows
there. Ship the scorer without fixing the guard and the mild ordering miss becomes
the disappearing-concept bug on a second surface — which is why Alex made the
guard acceptance criterion #1 of the wiring rather than a follow-up.

What these tests own:

* the shared upsert core, on BOTH row shapes, including that the typeahead
  wrapper's behaviour is byte-for-byte what it was before the refactor;
* the provenance rule, which `/search` had first and `/typeahead` blanket-flagged
  past until #1846 — see `TestProvenanceIsEvidenceNotDiscoveryPath` for the rule
  and `TestTypeaheadConceptProvenance` (LAT-P051) for the surface that was wrong;
* the two evidence builders, which exist at module level precisely so this file
  can reach them (`_ta_evidence` was a closure, and that is why two defects lived
  in the seam it hid).
"""

import pytest

from app.routes.events import (
    _detect_query_awards_concept,
    _detect_query_world_cup_concept,
    _query_names_concept,
    _query_names_typeahead_concept,
    _search_concept_evidence,
    _search_team_evidence,
    _typeahead_evidence,
    _upsert_query_derived_concept,
    _upsert_search_query_derived_concept,
)
from app.utils.event_awards import derive_awards_concept
from app.utils.search_match_class import (
    MC1_ALL_TOKENS,
    MC5_FRAGMENT,
    UNRANKABLE,
    match_class,
    rank,
    rank_key,
)
from app.utils.search_match_class import rank as _s_rank


def _loop_derived(key: str, name: str, domain: str = "awards", market_id: int = 7) -> dict:
    """A `/search` concept row exactly as the market-derived loop leaves it."""
    return {"key": key, "name": name, "domain": domain, "market_id": market_id}


# ---------------------------------------------------------------------------
# AC#1 — the guard
# ---------------------------------------------------------------------------


class TestSearchUpsertUpgradesRatherThanSkips:
    """The specimen: both paths mint one key, and the loop runs first."""

    def test_key_collision_is_real_on_the_search_shape(self):
        from_query = _detect_query_awards_concept("grammys")
        from_market = derive_awards_concept(None, "Grammy Winner: Best New Artist")
        assert from_query is not None and from_market is not None
        assert from_query["key"] == from_market["key"] == "event:awards:grammys"

    def test_twin_is_upgraded_not_discarded(self):
        """The whole of AC#1. The old guard skipped; this must upgrade."""
        pool = [_loop_derived("event:awards:grammys", "Grammy Winner")]
        pool[0]["_derived"] = True
        seen = {"event:awards:grammys"}

        detected = _detect_query_awards_concept("grammys")
        out = _upsert_search_query_derived_concept(pool, seen, detected)

        assert len(out) == 1, "an upgrade must not duplicate the row"
        assert out[0]["_derived"] is False, "the surviving row must be RANKABLE"
        assert out[0]["name"] == detected["name"], "canonical display name adopted"
        assert out[0]["key"] == "event:awards:grammys"

    def test_upgraded_twin_moves_to_the_front(self):
        """"Prepended so it leads top-1" is the call site's own comment."""
        pool = [
            _loop_derived("event:soccer:some-other", "Some Other Cup", "soccer"),
            _loop_derived("event:awards:grammys", "Grammy Winner"),
        ]
        for row in pool:
            row["_derived"] = True
        seen = {r["key"] for r in pool}

        out = _upsert_search_query_derived_concept(
            pool, seen, _detect_query_awards_concept("grammys")
        )
        assert out[0]["key"] == "event:awards:grammys"
        assert len(out) == 2

    def test_upgrade_survives_the_scorer_where_the_old_guard_did_not(self):
        """End to end: the old skip left only an UNRANKABLE copy, so the
        concept vanished. Assert the outcome, not the mechanism."""
        pool = [_loop_derived("event:awards:grammys", "Grammy Winner")]
        pool[0]["_derived"] = True
        seen = {"event:awards:grammys"}

        # What the OLD guard produced: the derived copy, untouched.
        old_guard_survivors = rank(
            "grammys", [(_search_concept_evidence(c), c) for c in list(pool)]
        )
        assert old_guard_survivors == [], (
            "premise check — a derived-only concept is DROPPED, which is why the "
            "skip was fatal rather than merely mis-ordered"
        )

        out = _upsert_search_query_derived_concept(
            pool, seen, _detect_query_awards_concept("grammys")
        )
        survivors = rank("grammys", [(_search_concept_evidence(c), c) for c in out])
        assert [s["key"] for s in survivors] == ["event:awards:grammys"]

    def test_no_twin_inserts_at_the_front_and_records_the_key(self):
        pool: list[dict] = []
        seen: set[str] = set()
        detected = _detect_query_world_cup_concept("world cup")
        out = _upsert_search_query_derived_concept(pool, seen, detected)
        assert out[0]["key"] == detected["key"]
        assert detected["key"] in seen

    def test_inserted_row_is_a_copy_not_the_detector_dict(self):
        """A detector returns a fresh dict today; relying on that is a trap the
        next reader should not have to check. Mutating the pool row must not be
        able to reach back into a caller's object."""
        detected = _detect_query_world_cup_concept("world cup")
        out = _upsert_search_query_derived_concept([], set(), detected)
        out[0]["name"] = "MUTATED"
        assert detected["name"] != "MUTATED"

    def test_cap_is_the_search_bucket_cap_of_five(self):
        pool = [_loop_derived(f"event:x:{i}", f"C{i}", "soccer", i) for i in range(6)]
        out = _upsert_search_query_derived_concept(
            pool, set(), _detect_query_world_cup_concept("world cup")
        )
        assert len(out) == 5

    def test_a_none_domain_never_clobbers_a_real_one(self):
        pool = [_loop_derived("event:awards:grammys", "Grammy Winner")]
        seen = {"event:awards:grammys"}
        out = _upsert_search_query_derived_concept(
            pool, seen, {"key": "event:awards:grammys", "name": "The Grammys", "domain": None}
        )
        assert out[0]["domain"] == "awards"


class TestTypeaheadWrapperUnchangedByTheRefactor:
    """The refactor moved six lines. A regression here is a regression on the
    MEASURED surface, so it is asserted rather than assumed."""

    def test_upgrade_semantics_preserved(self):
        pool = [{
            "type": "event_concept", "text": "Grammy Winner",
            "event_key": "event:awards:grammys", "sport_key": "awards",
            "_derived": True,
        }]
        seen = {"event:awards:grammys"}
        out = _upsert_query_derived_concept(
            pool, seen, name="The Grammys", key="event:awards:grammys",
            sport_key="awards",
        )
        assert len(out) == 1
        assert out[0]["_derived"] is False
        assert out[0]["text"] == "The Grammys"

    def test_insert_shape_preserved(self):
        out = _upsert_query_derived_concept(
            [], set(), name="The Grammys", key="event:awards:grammys",
            sport_key="awards",
        )
        assert out[0] == {
            "type": "event_concept",
            "text": "The Grammys",
            "event_key": "event:awards:grammys",
            "sport_key": "awards",
        }

    def test_typeahead_cap_is_still_three(self):
        pool = [
            {"type": "event_concept", "text": f"C{i}", "event_key": f"k{i}",
             "sport_key": "awards"}
            for i in range(5)
        ]
        out = _upsert_query_derived_concept(
            pool, set(), name="The Grammys", key="event:awards:grammys",
            sport_key="awards",
        )
        assert len(out) == 3


# ---------------------------------------------------------------------------
# The provenance rule, and why it differs from typeahead's
# ---------------------------------------------------------------------------


class TestProvenanceIsEvidenceNotDiscoveryPath:
    """Both surfaces flag `_derived` per row; `/search` got there first.

    Ruling 041 is about the evidence a candidate OWNS, not the path we reached it
    by, and a blanket flag drops a concept whose own name IS the query. Typeahead
    had exactly that hole (**#1846**) and kept it for one cycle because fixing it
    was a ranking change on the measured surface with two such changes already in
    flight unread (ruling 046). Both those reads are now taken and the fix has
    landed — see `TestTypeaheadConceptProvenance`.

    `test_blanket_flagging_would_have_dropped_it` stays. It was written as a
    specimen waiting for the fix; it now pins the counterfactual permanently, so
    a later "simplification" back to a blanket flag cannot land silently on
    either surface.
    """

    _EMMYS = {"key": "event:awards:emmys", "name": "The Emmys", "domain": "awards"}
    _TDF = {
        "key": "event:cycling:tour-de-france",
        "name": "Tour de France",
        "domain": "cycling",
    }

    def test_over_matched_concept_is_derived_and_therefore_dropped(self):
        """The Emmys family — the failure ruling 041 was written against."""
        row = dict(self._EMMYS)
        row["_derived"] = not _query_names_concept("world series", row)
        assert row["_derived"] is True
        assert match_class("world series", _search_concept_evidence(row)) is UNRANKABLE

    def test_self_named_concept_survives_despite_being_loop_derived(self):
        """The case a blanket flag would destroy, and the reason for the split."""
        row = dict(self._TDF)
        row["_derived"] = not _query_names_concept("tour de france", row)
        assert row["_derived"] is False
        # MC0 in fact — the query IS the concept's name — and the assertion is
        # written as a bound rather than a literal so it states the property
        # (rankable, and at least an all-token match) instead of pinning a tier
        # a later refinement could legitimately improve.
        mc = match_class("tour de france", _search_concept_evidence(row))
        assert mc is not UNRANKABLE and mc <= MC1_ALL_TOKENS

    def test_blanket_flagging_would_have_dropped_it(self):
        """Pins the counterfactual, so a future 'simplification' back to a
        blanket flag cannot land silently on either surface."""
        row = dict(self._TDF)
        row["_derived"] = True
        assert match_class("tour de france", _search_concept_evidence(row)) is UNRANKABLE


# ---------------------------------------------------------------------------
# #1846 (LAT-P051) — the same rule, on the surface that is actually measured
# ---------------------------------------------------------------------------


class TestTypeaheadConceptProvenance:
    """The dropdown's concept rows, flagged per row instead of blanket-true.

    The shape differs (`event_key`/`text`, not `key`/`name`) and the rule does
    not, which is why `_query_names_concept_row` takes the shape as arguments.
    Both directions are asserted here: the Emmys family — the four measured
    over-match failures ruling 041 was written against — must stay UNRANKABLE,
    and a concept whose own name names the query must survive.
    """

    # Exactly as production mints them (verified against
    # GET /api/events/search on v3807, 2026-08-14).
    _US_OPEN = {
        "type": "event_concept",
        "text": "2026 Women’s US Open Winner (Tennis)",
        "event_key": "event:tennis:2026-women-s-us-open-winner-tennis",
        "sport_key": "tennis",
    }
    _EMMYS = {
        "type": "event_concept",
        "text": "The Emmys",
        "event_key": "event:awards:emmys",
        "sport_key": "awards",
    }

    @pytest.mark.parametrize("query", ["super bowl", "world series", "wwe", "stranger things"])
    def test_the_emmys_family_stays_dead(self, query):
        """The over-match defence is not relaxed to buy #1846. These four are the
        measured failures (2026-08-12 21:48Z) that owned-evidence-only exists for."""
        row = dict(self._EMMYS)
        row["_derived"] = not _query_names_typeahead_concept(query, row)
        assert row["_derived"] is True
        assert match_class(query, _typeahead_evidence(row)) is UNRANKABLE

    def test_the_tennis_specimen_survives(self):
        """Alex ruling 2, 2026-08-13: `us open` has no tennis resolver and never
        had a query-derived twin, so #1839's guard could not reach it. It is a
        #1846 sub-case, and this is the specimen that gives it an owner.

        The gold probe expects this exact concept id; on the v3807 read
        production minted it, flagged it derived, dropped it, and answered with
        `market:114160` — the market whose name is byte-identical to the concept
        it had just deleted.
        """
        row = dict(self._US_OPEN)
        row["_derived"] = not _query_names_typeahead_concept("us open", row)
        assert row["_derived"] is False, "the concept OWNS a match on its own name"
        mc = match_class("us open", _typeahead_evidence(row))
        assert mc is not UNRANKABLE and mc <= MC1_ALL_TOKENS

    def test_blanket_flagging_is_what_dropped_it(self):
        """The defect itself, pinned. This is what production did on v3807."""
        row = dict(self._US_OPEN)
        row["_derived"] = True
        assert match_class("us open", _typeahead_evidence(row)) is UNRANKABLE

    def test_the_shape_is_the_only_difference(self):
        """One rule, two shapes — not two rules. If these ever disagree, the
        arrangement gotcha #129 names has come back."""
        for text, key, query in [
            ("2026 Women’s US Open Winner (Tennis)",
             "event:tennis:2026-women-s-us-open-winner-tennis", "us open"),
            ("The Emmys", "event:awards:emmys", "world series"),
            ("Tour de France", "event:cycling:tour-de-france", "tour de france"),
        ]:
            ta = _query_names_typeahead_concept(query, {"text": text, "event_key": key})
            se = _query_names_concept(query, {"name": text, "key": key})
            assert ta is se, f"surfaces disagree on {query!r} -> {key}"

    def test_a_row_missing_both_fields_is_derived_not_crashing(self):
        assert _query_names_typeahead_concept("us open", {}) is False


class TestGolfPrependProtectsTheTie:
    """`the open championship winner` passes on the PREPEND, not on the scoring.

    Before #1846 the cross-sport tennis "US Open" concepts lost that probe by
    being dropped as derived. They are rankable now, and they tie the golf major
    exactly — same match class, same kind, same (absent) prominence — so the only
    thing left deciding rank 1 is position in the candidate list, which
    `_upsert_query_derived_concept` controls by inserting at the front.

    This is a real fragility introduced by the fix, so it is asserted rather than
    left as a comment: a stable sort plus a deliberate prepend is a mechanism, but
    only while both halves hold.

    The pool is assembled through `_upsert_query_derived_concept` — the real
    insertion the route performs — and NOT by hand. Planning the mutations for
    this change is what caught the difference (gotcha #131): a hand-ordered list
    asserts that a stable sort is stable, which is true and worthless, and the
    mutation that turns the prepend into an append survived it untouched.
    """

    _Q = "the open championship winner"
    _GOLF_NAME = "The Open Championship"
    _GOLF_KEY = "event:golf:the-open-championship"
    _TENNIS = [
        ("2026 Women’s US Open Winner (Tennis)",
         "event:tennis:2026-women-s-us-open-winner-tennis"),
        ("2026 Men’s US Open Winner (Tennis)",
         "event:tennis:2026-men-s-us-open-winner-tennis"),
    ]

    def _loop_pool(self):
        """The tennis concepts exactly as the market loop leaves them, with the
        per-row provenance the fix computes."""
        pool = []
        for text, key in self._TENNIS:
            row = {
                "type": "event_concept", "text": text,
                "event_key": key, "sport_key": "tennis",
            }
            row["_derived"] = not _query_names_typeahead_concept(self._Q, row)
            pool.append(row)
        return pool

    def _ranked(self, pool):
        return _s_rank(self._Q, [(_typeahead_evidence(r), r) for r in pool])

    def test_the_tennis_rows_are_rankable_now(self):
        """The premise. Before #1846 they were dropped, so nothing below applied."""
        assert [r["_derived"] for r in self._loop_pool()] == [False, False]

    def test_the_tie_is_real(self):
        """If this ever stops being a tie, the tests below measure nothing."""
        pool = self._loop_pool()
        pool.insert(0, {"type": "event_concept", "text": self._GOLF_NAME,
                        "event_key": self._GOLF_KEY, "sport_key": "golf"})
        keys = {rank_key(self._Q, _typeahead_evidence(r)) for r in pool}
        assert len(keys) == 1, f"expected one shared rank_key, got {keys}"

    def test_the_upsert_puts_the_golf_major_first_and_it_wins(self):
        pool = _upsert_query_derived_concept(
            self._loop_pool(), set(),
            name=self._GOLF_NAME, key=self._GOLF_KEY, sport_key="golf",
        )
        assert pool[0]["event_key"] == self._GOLF_KEY, "the upsert must PREPEND"
        assert self._ranked(pool)[0]["text"] == self._GOLF_NAME

    def test_and_it_loses_when_it_is_not_prepended(self):
        """The counterfactual that makes the assertion above non-vacuous: the
        golf major wins BECAUSE it is inserted first, not because it scores
        higher. Append it instead and the probe flips."""
        pool = self._loop_pool()
        pool.append({"type": "event_concept", "text": self._GOLF_NAME,
                     "event_key": self._GOLF_KEY, "sport_key": "golf"})
        assert self._ranked(pool)[0]["text"] != self._GOLF_NAME


# ---------------------------------------------------------------------------
# The evidence builders — the seam a closure used to hide
# ---------------------------------------------------------------------------


class TestSearchConceptEvidence:
    def test_carries_name_kind_and_derived(self):
        ev = _search_concept_evidence(
            {"key": "k", "name": "The Masters", "domain": "golf", "_derived": False}
        )
        assert ev.name == "The Masters"
        assert ev.kind == "concept"
        assert ev.derived is False

    def test_missing_derived_key_defaults_to_rankable(self):
        ev = _search_concept_evidence({"key": "k", "name": "The Masters"})
        assert ev.derived is False

    def test_domain_is_not_smuggled_in_as_a_sport_key(self):
        """A domain is not a sport key. Filling the prominence term with one
        would feed the scorer a value nothing computed."""
        ev = _search_concept_evidence({"key": "k", "name": "X", "domain": "awards"})
        assert ev.sport_key is None

    def test_missing_name_does_not_raise(self):
        assert _search_concept_evidence({"key": "k"}).name == ""


class TestSearchTeamEvidence:
    _ROW = {
        "id": 1, "name": "Boston Red Sox", "sport_key": "baseball_mlb",
        "abbreviation": "BOS", "_aliases": ["Red Sox", "BoSox"],
    }

    def test_aliases_and_abbreviation_both_reach_the_scorer(self):
        ev = _search_team_evidence(dict(self._ROW))
        assert "Red Sox" in ev.aliases
        assert "BOS" in ev.aliases

    def test_short_name_alias_lifts_the_team_to_mc1(self):
        """The measured correction from spec §3: without `alternate_names`,
        `Boston Red Sox` is not an all-token match for `red sox`."""
        with_alias = _search_team_evidence(dict(self._ROW))
        without = _search_team_evidence({**self._ROW, "_aliases": []})
        # With the short name owned, `red sox` is an EXACT alias hit (MC0).
        # Without it, `Boston Red Sox` covers only 2 of 2 query tokens inside a
        # 3-token name — MC1 at best, and in fact the class drops. What the test
        # asserts is the DIRECTION, which is the claim the SELECT change makes.
        better = match_class("red sox", with_alias)
        worse = match_class("red sox", without)
        assert better is not UNRANKABLE and worse is not UNRANKABLE
        assert better < worse, (
            "withholding alternate_names must cost the team its class — that is "
            "the whole reason the column is SELECTed"
        )

    def test_sport_key_reaches_the_prominence_term(self):
        assert _search_team_evidence(dict(self._ROW)).sport_key == "baseball_mlb"

    def test_no_aliases_key_is_not_an_error(self):
        ev = _search_team_evidence({"name": "Someone", "sport_key": "x"})
        assert ev.aliases == ()


# ---------------------------------------------------------------------------
# Bucket-level behaviour of the wiring
# ---------------------------------------------------------------------------


class TestWithinBucketRanking:
    def test_fragment_team_cannot_outrank_a_token_match(self):
        """`british open` answered a team called `Brito`. Not any more."""
        brito = {"name": "Brito", "sport_key": "soccer_other", "_aliases": []}
        open_team = {
            "name": "Open Championship FC", "sport_key": "soccer_other", "_aliases": [],
        }
        out = rank("open championship", [
            (_search_team_evidence(brito), brito),
            (_search_team_evidence(open_team), open_team),
        ])
        assert [r["name"] for r in out] == ["Open Championship FC", "Brito"]

    def test_a_non_matching_team_is_reordered_never_removed(self):
        """Recall belongs to the SQL. The scorer must not empty a bucket."""
        brito = {"name": "Brito", "sport_key": "soccer_other", "_aliases": []}
        out = rank("open championship", [(_search_team_evidence(brito), brito)])
        assert out == [brito]
        assert match_class("open championship", _search_team_evidence(brito)) == MC5_FRAGMENT

    @pytest.mark.parametrize("query", ["", "   "])
    def test_an_empty_query_does_not_crash_the_bucket(self, query):
        row = {"name": "Boston Red Sox", "sport_key": "baseball_mlb", "_aliases": []}
        assert rank(query, [(_search_team_evidence(row), row)]) == []


# ---------------------------------------------------------------------------
# AC#1, at the route. A STRUCTURAL guard, and labelled as one.
# ---------------------------------------------------------------------------


class TestEveryConceptCallSiteIsRouted:
    """Asserts over `/search`'s SOURCE, deliberately, and it is the weaker kind
    of test — say so rather than let a reader assume otherwise.

    The behavioural version needs the market-derived concept loop to produce a
    row, which needs a seeded futures corpus with outcomes and sports; that
    belongs to the real-Postgres contract suite. **It now EXISTS** — LAT-P053
    built the corpus (`_CONCEPT_FUTURES_SEEDS` in
    `tests/integration/test_search_recall_contract.py`) and the three cases at
    the bottom of that file, wired into the CI `search-recall` job, which fails
    on a skip. This class is therefore no longer the only instrument, and the
    "recorded as owed" note above is discharged.

    It is still kept, and not folded into the behavioural pair, because the two
    catch different things. What a source assertion catches and behaviour cannot:
    someone reintroducing a bare `key not in seen` skip at ONE of four sites —
    behaviour would need a specimen per site to see that, and three of the four
    have no seedable specimen. Same reasoning that makes a beat-schedule
    allowlist a real test (gotcha #12).

    What it CANNOT catch: a routed call site that passes the wrong concept.
    **That gap is now covered** by
    `test_a_concept_the_query_does_not_name_is_dropped`, which reads the wire.
    """

    @staticmethod
    def _source() -> str:
        import inspect

        from app.routes.events import search_events

        return inspect.getsource(search_events)

    def test_all_four_sites_use_the_shared_upsert(self):
        assert self._source().count("_upsert_search_query_derived_concept(") == 4, (
            "three `_detect_query_*` sites plus the #206 team bridge — a guard "
            "fixed at three of four sites still decides provenance at the fourth"
        )

    def test_no_first_writer_wins_skip_survives(self):
        src = self._source()
        assert "event_concepts.insert(0," not in src, (
            "a hand-rolled prepend is how the skip comes back"
        )
        # The loop-internal `if _key in _seen_concept_keys: continue` guards are
        # CORRECT — they dedupe two markets deriving one concept, which is a real
        # duplicate. What must not come back is the NEGATED form, which is the
        # shape that decided provenance: `if <query concept> not in seen: insert`.
        assert "not in _seen_concept_keys" not in src, (
            "the negated membership test is the first-writer-wins guard itself"
        )

    def test_the_scorer_is_applied_to_both_unpaginated_buckets(self):
        assert self._source().count("_search_rank_candidates(") == 2

    def test_private_evidence_is_stripped_before_the_response(self):
        src = self._source()
        assert '.pop("_derived", None)' in src
        assert '.pop("_aliases", None)' in src

    def test_alternate_names_reaches_the_scorer_from_the_select(self):
        assert "Team.alternate_names" in self._source(), (
            "the recall arms filter on this column; withholding it from the "
            "ranker is what turned the floor into a ceiling on typeahead"
        )

    def test_provenance_is_per_row_not_blanket(self):
        """Pins the #1846 divergence so a 'consistency' edit cannot silently
        import typeahead's bug into `/search`."""
        src = self._source()
        assert "_derived\"] = not _query_names_concept(q, _c)" in src
