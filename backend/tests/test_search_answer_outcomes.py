"""#993 Instant Answers Slice A/B — search/typeahead answer projection.

Covers the shared backend helpers that make search surfaces "answer-first":
- placeholder-outcome filtering (extended family, not just "Player X")
- #23 normalization of the displayed distribution (reuses the politics util)
- _build_search_top_outcomes shape (lean typeahead vs full search)
"""

from types import SimpleNamespace

from app.routes.events import (
    _is_placeholder_outcome_name,
    _normalize_search_outcome_probs,
    _build_search_top_outcomes,
    _strip_search_scaffolding,
    _apply_search_synonyms,
    _is_field_outcome,
    _rerank_search_futures,
    _demote_wrong_league,
    _demote_narrower_scope,
    _build_league_ticker_match,
    _compose_futures_families,
    _query_name_match,
)


def _fmt(m):
    return {"name": m.name}


class TestFamilyComposition:
    _FED = [("fed", None), ("rate", None)]
    _LEBRON = [("lebron", None), ("james", None)]

    def test_story_key_family_forms(self):
        # Fed markets share story:macro_rates -> one family (>=2 members)
        ms = [
            _mkt("economics", "How many Fed rate cuts in 2026?", vol=40_000_000),
            _mkt("economics", "Fed rate cut before 2027?", vol=300_000),
            _mkt("economics", "What will the Fed rate be at the end of 2026?", vol=6_000_000),
        ]
        fams = _compose_futures_families(ms, self._FED, _fmt)
        assert len(fams) == 1
        assert fams[0]["family_key"] == "story:macro_rates"
        assert fams[0]["headline"]["name"] == "How many Fed rate cuts in 2026?"  # reranked leader
        assert fams[0]["member_count"] == 3

    def test_entity_family_forms_for_name_matches(self):
        ms = [
            _mkt("basketball", "NBA: LeBron James Next Team", vol=12_000_000),
            _mkt("basketball", "Will LeBron James retire", vol=700_000),
        ]
        fams = _compose_futures_families(ms, self._LEBRON, _fmt)
        assert len(fams) == 1
        assert fams[0]["family_key"] == "entity:lebron james"
        assert fams[0]["label"] == "Lebron James"

    def test_single_member_no_family(self):
        ms = [_mkt("basketball", "NBA: LeBron James Next Team", vol=1)]
        assert _compose_futures_families(ms, self._LEBRON, _fmt) == []

    def test_more_count_caps_members_at_4(self):
        ms = [_mkt("economics", f"Fed rate scenario {i}", vol=100 - i) for i in range(7)]
        fams = _compose_futures_families(ms, self._FED, _fmt)
        assert len(fams[0]["members"]) == 4          # headline + 4 shown
        assert fams[0]["more_count"] == 2            # 7 total - headline - 4 = 2

    def test_query_name_match(self):
        assert _query_name_match(_mkt("x", "LeBron James Next Team"), self._LEBRON) is True
        assert _query_name_match(_mkt("x", "Presidential Election 2028"), self._LEBRON) is False

    def test_outcome_only_cluster_suppressed(self):
        # election markets that match "lebron" only as an outcome (name has no
        # 'lebron james') + share a story key must NOT form a LeBron family.
        ms = [
            _mkt("politics", "Democratic Presidential Nominee 2028", vol=5_000_000),
            _mkt("politics", "2028 Democratic presidential nominee", vol=1_000_000),
        ]
        # story:us_2028_election groups them, but none name-match "lebron james"
        assert _compose_futures_families(ms, self._LEBRON, _fmt) == []


def _mkt(cat, name="m", vol=0):
    return SimpleNamespace(llm_sport_category=cat, name=name, volume=vol)


# expanded-terms shape for _rerank_search_futures: [(term, expansion_or_None)]
_LEBRON = [("lebron", None), ("james", None)]
_TRUMP = [("trump", None), ("approval", None)]
_PL = [("premier", None), ("league", None)]


class TestRerankSearchFutures:
    def test_name_match_beats_outcome_only(self):
        # election markets list LeBron only as an outcome (name has no 'lebron
        # james') -> below the real name-matches, regardless of volume.
        ms = [
            _mkt("politics", "Presidential Election Winner 2028", vol=9_000_000),  # outcome-only
            _mkt("basketball", "LeBron James Next Team", vol=12_900_000),          # name-match
            _mkt("basketball", "Will LeBron James retire", vol=700_000),           # name-match
        ]
        out = _rerank_search_futures(ms, _LEBRON)
        assert out[0].name == "LeBron James Next Team"
        assert out[-1].name == "Presidential Election Winner 2028"

    def test_volume_sinks_vol0_novelty(self):
        # the tier-2 vol-0 politics novelty (a name-match) sinks below the
        # high-volume real basketball markets.
        ms = [
            _mkt("politics", "Will LeBron James announce a Presidential run", vol=0),
            _mkt("basketball", "LeBron James Next Team", vol=12_900_000),
            _mkt("basketball", "Will LeBron James retire", vol=700_000),
        ]
        out = _rerank_search_futures(ms, _LEBRON)
        assert out[0].name == "LeBron James Next Team"
        assert out[-1].llm_sport_category == "politics"

    def test_dedup_immune_volume_beats_count(self):
        # 'premier league': 1 (deduped) high-volume soccer vs 2 low-volume
        # lacrosse — volume keeps soccer on top (count-based coherence failed here)
        ms = [
            _mkt("lacrosse", "Premier League Lacrosse: 2026 A", vol=8000),
            _mkt("lacrosse", "Premier League Lacrosse: 2026 B", vol=6000),
            _mkt("soccer", "English Premier League Winner?", vol=16_000_000),
        ]
        out = _rerank_search_futures(ms, _PL)
        assert out[0].llm_sport_category == "soccer"

    def test_single_untouched(self):
        one = [_mkt("basketball", "LeBron James Next Team", vol=1)]
        assert _rerank_search_futures(one, _LEBRON) is one


class TestWrongLeagueDemotion:
    _NBA = [("nba", None), ("mvp", None)]
    _WNBA = [("wnba", None), ("mvp", None)]

    def test_wnba_demoted_for_nba_query(self):
        ms = [_mkt("basketball", "WNBA: 2026 MVP"), _mkt("basketball", "NBA: 2026 MVP")]
        out = _demote_wrong_league(ms, self._NBA)
        assert out[0].name == "NBA: 2026 MVP"
        assert out[-1].name == "WNBA: 2026 MVP"

    def test_wnba_query_keeps_wnba(self):
        ms = [_mkt("basketball", "WNBA: 2026 MVP")]
        assert _demote_wrong_league(ms, self._WNBA) == ms  # query IS wnba -> not demoted

    def test_token_boundary_not_substring(self):
        # a real NBA market must never be demoted by the nba->wnba rule
        ms = [_mkt("basketball", "NBA: LeBron James Next Team")]
        assert _demote_wrong_league(ms, self._NBA) == ms

    def test_no_league_token_noop(self):
        ms = [_mkt("basketball", "WNBA: 2026 MVP")]
        assert _demote_wrong_league(ms, [("gavin", None), ("newsom", None)]) == ms

    def test_integrated_in_rerank(self):
        ms = [_mkt("basketball", "WNBA: 2026 MVP"), _mkt("basketball", "NBA MVP Winner")]
        out = _rerank_search_futures(ms, self._NBA)
        assert out[0].name == "NBA MVP Winner"


class TestNarrowerScopeDemotion:
    """#993 L2-44 Item 2: a bare award query headlines the season/full award,
    not a higher-volume narrower sub-award."""

    _NBA_MVP = [("nba", None), ("mvp", None)]

    def test_bare_query_demotes_conference_finals_mvp(self):
        # the sub-award has HIGHER volume but must not headline the bare query
        ms = [
            _mkt("basketball", "Eastern Conference Finals MVP", vol=5_000_000),
            _mkt("basketball", "NBA MVP Winner", vol=2_000_000),
        ]
        out = _demote_narrower_scope(ms, self._NBA_MVP)
        assert out[0].name == "NBA MVP Winner"
        assert out[-1].name == "Eastern Conference Finals MVP"

    def test_scoped_query_keeps_the_scoped_market(self):
        # query names 'finals' -> the Finals MVP is what the user asked for
        low = [("nba", None), ("finals", None), ("mvp", None)]
        ms = [
            _mkt("basketball", "NBA Finals MVP", vol=5_000_000),
            _mkt("basketball", "NBA MVP Winner", vol=2_000_000),
        ]
        out = _demote_narrower_scope(ms, low)
        assert out[0].name == "NBA Finals MVP"  # volume order, not demoted

    def test_volume_order_preserved_within_broad_group(self):
        ms = [
            _mkt("basketball", "NBA MVP Winner", vol=1_000_000),
            _mkt("basketball", "NBA Most Valuable Player", vol=3_000_000),
        ]
        # neither carries an absent qualifier -> untouched (stable, volume order)
        out = _demote_narrower_scope(ms, self._NBA_MVP)
        assert out == ms

    def test_integrated_headline_is_season_award(self):
        # Real scenario: award markets reach results via league-ticker recall, so
        # their names lack "nba" (outcome_only, not name_matches). Narrower-scope
        # demotion must still apply, AND WNBA (wrong league) stays last.
        ms = [
            _mkt("basketball", "Eastern Conference Finals MVP Winner", vol=5_000_000),
            _mkt("basketball", "MVP Winner", vol=2_000_000),
            _mkt("basketball", "WNBA: 2026 MVP", vol=9_000_000),
        ]
        out = _rerank_search_futures(ms, self._NBA_MVP)
        assert out[0].name == "MVP Winner"                        # season award headlines
        assert out[1].name == "Eastern Conference Finals MVP Winner"  # sub-award #2
        assert out[-1].name == "WNBA: 2026 MVP"                   # wrong league last

    def test_single_untouched(self):
        one = [_mkt("basketball", "Eastern Conference Finals MVP")]
        assert _demote_narrower_scope(one, self._NBA_MVP) is one


class TestLeagueTickerMatch:
    """#993 L2-45: the league-token recall clause, SHARED by /search and
    /typeahead so the dropdown fetches the same correct-league market."""

    def test_returns_clause_for_league_plus_nonleague(self):
        # "nba mvp" -> a real SQL clause (kxnba% + name ilike mvp)
        clause = _build_league_ticker_match([("nba", None), ("mvp", None)])
        assert clause is not None

    def test_none_without_league_token(self):
        assert _build_league_ticker_match([("mvp", None)]) is None

    def test_none_without_nonleague_term(self):
        # bare league only -> nothing to disambiguate by name
        assert _build_league_ticker_match([("nba", None)]) is None


class TestTypeaheadSearchParity:
    """#993 L2-45: the search-bar dropdown must rank by the SAME logic as the
    full /search results (league-token divergence flagged for LeBron round 87 and
    nba mvp round 90). Assert both endpoints call the shared recall + rerank
    helpers — the structural guarantee that they can't silently diverge again.
    Source-inspection (like the _format_market_detail guard) rather than a DB
    integration mock; the live browser trace proves it end-to-end."""

    def _src(self, fn_name):
        import inspect
        from app.routes import events
        return inspect.getsource(getattr(events, fn_name))

    def test_typeahead_uses_shared_league_recall(self):
        src = self._src("typeahead_search")
        assert "_build_league_ticker_match" in src

    def test_typeahead_uses_shared_reranker(self):
        src = self._src("typeahead_search")
        assert "_rerank_search_futures" in src

    def test_search_uses_the_same_two_helpers(self):
        src = self._src("search_events")
        assert "_build_league_ticker_match" in src
        assert "_rerank_search_futures" in src


class TestScaffoldingStrip:
    def test_strips_generic_terms_on_long_query(self):
        assert _strip_search_scaffolding(["fed", "rate", "decision"]) == ["fed", "rate"]
        assert _strip_search_scaffolding(["where", "will", "lebron", "go"]) == ["lebron"]
        assert _strip_search_scaffolding(["bitcoin", "price", "2026"]) == ["bitcoin", "2026"]

    def test_two_word_queries_untouched(self):
        # name collisions must survive ("Will Smith", "The Who")
        assert _strip_search_scaffolding(["will", "smith"]) == ["will", "smith"]
        assert _strip_search_scaffolding(["the", "who"]) == ["the", "who"]

    def test_never_strips_to_empty(self):
        assert _strip_search_scaffolding(["who", "will", "win"]) != []


class TestSearchSynonyms:
    def test_champion_expands_to_winner(self):
        out = _apply_search_synonyms([("super", None), ("bowl", None), ("champion", None)])
        assert ("champion", "winner") in out

    def test_existing_expansion_preserved(self):
        out = _apply_search_synonyms([("la", "los angeles")])
        assert out == [("la", "los angeles")]

    def test_coach_fired_maps_to_head_coach(self):
        # #993 L2-43: "next coach fired" must find "…Next Head Coach" markets
        out = _apply_search_synonyms([("next", None), ("coach", None), ("fired", None)])
        assert ("fired", "head coach") in out


class TestFieldOutcome:
    def test_detects_field(self):
        for n in ("Other", "The Field", "None of the above", "Neither", "TBD"):
            assert _is_field_outcome(n) is True, n

    def test_real_names_not_field(self):
        for n in ("Gavin Newsom", "Rory McIlroy", "Yes", "Over"):
            assert _is_field_outcome(n) is False, n


def _oc(name, prob, mv=None, oid=1, odds=None, rank=None):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        current_american_odds=odds, rank=rank, probability_change_24h=mv,
    )


class TestPlaceholderFamily:
    def test_catches_anonymized_slots(self):
        # single- AND two-letter suffixes; "Team C" single-letter (LeBron Next Team)
        for n in ("Player B", "Person P", "Person CF", "Movie F", "Movie AX",
                  "Candidate W", "Nominee A", "Team A", "Team C", "Team E"):
            assert _is_placeholder_outcome_name(n) is True, n

    def test_keeps_real_names(self):
        # "Team GB"/"Team USA" (2+ letter codes) are REAL Olympic entrants — kept.
        for n in ("Lakers", "A'ja Wilson", "Donald Trump", "The Odyssey", "Over",
                  "Yes", "Team GB", "Team USA", "Cleveland Cavaliers", "Miami Heat"):
            assert _is_placeholder_outcome_name(n) is False, n

    def test_multiword_and_empty_safe(self):
        assert _is_placeholder_outcome_name("Person of Interest") is False
        assert _is_placeholder_outcome_name("") is False
        assert _is_placeholder_outcome_name(None) is False


class TestNormalizeSearchProbs:
    def test_over_threshold_normalizes_to_one(self):
        outs = [{"probability": 0.80}, {"probability": 0.60}, {"probability": 0.40}]
        _normalize_search_outcome_probs(outs)
        assert abs(sum(o["probability"] for o in outs) - 1.0) < 0.01

    def test_under_threshold_unchanged(self):
        outs = [{"probability": 0.62}, {"probability": 0.18}]
        _normalize_search_outcome_probs(outs)
        assert outs == [{"probability": 0.62}, {"probability": 0.18}]

    def test_none_probs_safe(self):
        outs = [{"probability": None}, {"probability": 0.9}, {"probability": 0.9}]
        _normalize_search_outcome_probs(outs)  # 1.8 > 1.05 -> normalizes the non-None
        assert outs[0]["probability"] is None
        assert abs(sum(o["probability"] for o in outs if o["probability"]) - 1.0) < 0.01


class TestBuildTopOutcomes:
    def _market(self):
        return SimpleNamespace(outcomes=[
            _oc("Player B", 0.99, oid=1),           # placeholder — dropped
            _oc("Lakers", 0.62, mv=0.05, oid=2, odds=-160, rank=1),
            _oc("Cavaliers", 0.55, mv=-0.01, oid=3, odds=120, rank=2),
            _oc("Warriors", 0.30, oid=4, rank=3),
        ])

    def test_filters_sorts_limits(self):
        out = _build_search_top_outcomes(self._market(), limit=2, lean=True)
        assert [o["name"] for o in out] == ["Lakers", "Cavaliers"]  # placeholder gone, sorted desc

    def test_lean_shape_is_minimal(self):
        out = _build_search_top_outcomes(self._market(), limit=3, lean=True)
        assert set(out[0].keys()) == {"name", "probability", "movement"}

    def test_full_shape_has_odds_rank(self):
        out = _build_search_top_outcomes(self._market(), limit=3, lean=False)
        assert {"id", "american_odds", "rank"}.issubset(out[0].keys())

    def test_distribution_is_normalized(self):
        # 0.62+0.55+0.30 = 1.47 > 1.05 -> normalized
        out = _build_search_top_outcomes(self._market(), limit=3, lean=True)
        assert abs(sum(o["probability"] for o in out) - 1.0) < 0.02

    def test_field_outcome_demoted_below_named_leader(self):
        m = SimpleNamespace(outcomes=[
            _oc("Other", 0.67, oid=1),
            _oc("Gavin Newsom", 0.13, oid=2),
            _oc("AOC", 0.09, oid=3),
        ])
        out = _build_search_top_outcomes(m, limit=3, lean=True)
        assert out[0]["name"] == "Gavin Newsom"   # named leads
        assert any(o["name"] == "Other" for o in out)  # field still visible
