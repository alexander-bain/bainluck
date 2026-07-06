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
    _cohere_by_category,
    _rerank_search_futures,
)


def _mkt(cat, name="m"):
    return SimpleNamespace(llm_sport_category=cat, name=name)


# expanded-terms shape for _rerank_search_futures: [(term, expansion_or_None)]
_LEBRON = [("lebron", None), ("james", None)]
_TRUMP = [("trump", None), ("approval", None)]


class TestRerankSearchFutures:
    def test_name_match_beats_outcome_only(self):
        # lebron: real basketball markets NAME him; election markets only list him
        # as an outcome (name has no 'lebron james') -> those go last.
        ms = [
            _mkt("politics", "Presidential Election Winner 2028"),   # outcome-only
            _mkt("basketball", "LeBron James Next Team"),            # name-match
            _mkt("politics", "Will LeBron James announce a Presidential run"),  # name-match, novelty
            _mkt("basketball", "Will LeBron James retire"),          # name-match
        ]
        out = _rerank_search_futures(ms, _LEBRON)
        assert out[0].name == "LeBron James Next Team"               # basketball leads
        assert out[-1].name == "Presidential Election Winner 2028"   # outcome-only demoted

    def test_cross_category_novelty_demoted_within_name_matches(self):
        ms = [
            _mkt("politics", "Will LeBron James announce a Presidential run"),
            _mkt("basketball", "LeBron James Next Team"),
            _mkt("basketball", "Will LeBron James retire"),
        ]
        out = _rerank_search_futures(ms, _LEBRON)
        assert out[0].llm_sport_category == "basketball"
        assert out[-1].llm_sport_category == "politics"

    def test_politics_query_no_regression(self):
        ms = [
            _mkt("politics", "Will Trump approval exceed 50%"),
            _mkt("politics", "Trump approval rating in 2026"),
            _mkt("economics", "GDP with Trump approval outcome"),   # name has trump+approval too
        ]
        out = _rerank_search_futures(ms, _TRUMP)
        assert out[0].llm_sport_category == "politics"

    def test_single_untouched(self):
        one = [_mkt("basketball", "LeBron James Next Team")]
        assert _rerank_search_futures(one, _LEBRON) is one


class TestCohereByCategory:
    def test_clear_plurality_promoted(self):
        ms = [_mkt("politics"), _mkt("basketball"), _mkt("basketball")]
        assert _cohere_by_category(ms)[0].llm_sport_category == "basketball"

    def test_balanced_untouched(self):
        ms = [_mkt("basketball"), _mkt("politics"), _mkt("basketball"), _mkt("politics")]
        assert _cohere_by_category(ms) == ms


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
        # single- AND two-letter suffixes (live-verify found "Person CF"/"Person AX")
        for n in ("Player B", "Person P", "Person CF", "Movie F", "Movie AX",
                  "Candidate W", "Nominee A"):
            assert _is_placeholder_outcome_name(n) is True, n

    def test_keeps_real_names(self):
        # "Team GB"/"Team USA" are REAL Olympic entrants — must NOT be filtered.
        for n in ("Lakers", "A'ja Wilson", "Donald Trump", "The Odyssey", "Over",
                  "Yes", "Team GB", "Team USA"):
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
