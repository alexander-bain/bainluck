"""#8829 — a tennis page shows its own match once, and keeps its set markets.

WHAT A READER SAW (production, 2026-09-26).

* `/events/15318843` (Hangzhou Open doubles, Reynolds / Watt v King / Stevens):
  the match winner was drawn TWICE under Additional Markets — Kalshi `62357729`
  ("Finn Reynolds / James Watt" 37.5%) and Polymarket `62358022` ("Reynolds/Watt"
  45.5%) — and Polymarket's copy again in Bigger Picture. `names_match` reads the
  unspaced "Reynolds/Watt" as one token, so the Polymarket market named no side,
  was never a fold candidate in either door, and #6799 / #4646 left it standing.
* `/events/15319072` (M25 Setubal, Deckers v Henning): Set 1 Winner `62422520` and
  Set 2 Winner `62526440` reached NEITHER door. `_MONEYLINE_MATCHUP_RE` swallows a
  leading "Set 1 Winner:" into the first side, the legs are the two players, and
  the market was folded as if it were the match.

The two halves ship together because they are one change: spacing the slash
alone would make every doubles "Set 1 Winner" a fold candidate too — the singles
defect, spread to doubles.

THE CONTROLS. A fold's failure mode is taking what it should not, so every test
that proves a fold has a sibling proving the neighbour it must leave alone: the
set markets beside the doubles headline, the tournament-prefixed headline beside
the set markets, the Kalshi playoff "Game 1:" winner beside the prop vocabulary,
and an unlinked speaker id beside the linked one.
"""

from types import SimpleNamespace

import pytest

from app.routes.events import (
    _fold_duplicate_match_winner_markets,
    _fold_event_match_winner_futures,
    _headline_winner_market_ids,
    _market_is_event_match_winner,
    _match_winner_side,
)
from app.utils.matchup_sides import names_a_prop_qualifier

# ── the doubles specimen, /events/15318843 ──────────────────────────────────
D_EVENT = 15318843
D_HOME = "Reynolds / Watt"
D_AWAY = "King / Stevens"
D_KALSHI = 62357729
D_POLY = 62358022
D_SET1 = 62358024
D_SET2 = 62358025
D_POLY_NAME = "Hangzhou Open (Doubles): Reynolds/Watt vs King/Stevens"
D_POLY_LEGS = [("Reynolds/Watt", 0.455), ("King/Stevens", 0.545)]
D_KALSHI_NAME = "Reynolds / Watt vs King / Stevens"
D_KALSHI_LEGS = [("Finn Reynolds / James Watt", 0.375), ("Evan King / Bart Stevens", 0.635)]

# ── the singles specimen, /events/15319072 ──────────────────────────────────
S_EVENT = 15319072
S_HOME = "Deckers"
S_AWAY = "Henning"
S_HEAD = 62392768
S_SET1 = 62422520
S_SET2 = 62526440
S_LEGS = [("Alec Deckers", 0.9995), ("Philip Henning", 0.0005)]

STAMP = "2026-09-26T14:00:00+00:00"


def _gm_rows(market_id, source, name, legs):
    """A `/game-markets` `other` row, as `_fold_duplicate_match_winner_markets` reads it."""
    return [
        {
            "market_name": name,
            "outcome_name": leg,
            "probability": prob,
            "source": source,
            "observed_at": STAMP,
            "_market_id": market_id,
        }
        for leg, prob in legs
    ]


def _rf_row(market_id, name, leg):
    """A `/related-futures` row, as `_fold_event_match_winner_futures` reads it."""
    return {"market_id": market_id, "market_name": name, "outcome_name": leg}


def _markets(event_id, *ids, linked_elsewhere=()):
    out = {mid: SimpleNamespace(id=mid, event_id=event_id) for mid in ids}
    for mid in linked_elsewhere:
        out[mid] = SimpleNamespace(id=mid, event_id=99999)
    return out


# ═════════════════════════════════════════════════════ the side mapper ══


class TestADoublesPairAnswersWhateverItsSlashSpacing:
    @pytest.mark.parametrize(
        "leg,expected",
        [
            ("Reynolds/Watt", "home"),
            ("King/Stevens", "away"),
            ("Reynolds / Watt", "home"),
            ("Finn Reynolds / James Watt", "home"),
            ("Evan King / Bart Stevens", "away"),
        ],
    )
    def test_the_production_legs(self, leg, expected):
        assert _match_winner_side(leg, D_HOME, D_AWAY) == expected

    def test_a_stored_side_without_spaces_answers_too(self):
        """Both operands are spaced, not only the leg."""
        assert _match_winner_side("Reynolds / Watt", "Reynolds/Watt", "King/Stevens") == "home"

    def test_a_different_pair_is_still_nobody(self):
        assert _match_winner_side("Arends/Pel", D_HOME, D_AWAY) is None


# ═════════════════════════════════════════════════════ the name test ══


class TestALeadingPropQualifierIsNotTheMatch:
    @pytest.mark.parametrize(
        "name",
        [
            "Set 1 Winner: Alec Deckers vs Philip Henning",
            "Set 2 Winner: Alec Deckers vs Philip Henning",
            "Set 1 Winner: Reynolds/Watt vs King/Stevens",
        ],
    )
    def test_a_set_market_is_refused(self, name):
        home, away = (D_HOME, D_AWAY) if "/" in name else (S_HOME, S_AWAY)
        legs = D_POLY_LEGS if "/" in name else S_LEGS
        rows = [{"market_name": name, "outcome_name": leg} for leg, _p in legs]
        assert _market_is_event_match_winner(rows, home, away) is False

    @pytest.mark.parametrize(
        "name",
        [
            "M25 Setubal: Alec Deckers vs Philip Henning",
            "Hangzhou Open, Qualification: Alec Deckers vs Philip Henning",
            "Alec Deckers vs Philip Henning",
        ],
    )
    def test_a_tournament_prefix_still_qualifies(self, name):
        """The control: the prefix the regex was built to swallow is still swallowed."""
        rows = [{"market_name": name, "outcome_name": leg} for leg, _p in S_LEGS]
        assert _market_is_event_match_winner(rows, S_HOME, S_AWAY) is True

    def test_the_doubles_headline_qualifies(self):
        rows = [{"market_name": D_POLY_NAME, "outcome_name": leg} for leg, _p in D_POLY_LEGS]
        assert _market_is_event_match_winner(rows, D_HOME, D_AWAY) is True

    def test_a_kalshi_playoff_game_number_still_qualifies(self):
        """Measured carve-out: all four open "Game 1: …" rows are their event's own
        verified winner speaker. `game` is in the prop vocabulary, so without the
        carve-out door one would draw Kalshi's and Polymarket's winner twice."""
        rows = [
            {"market_name": "Game 1: Dallas vs Golden State", "outcome_name": leg}
            for leg in ("Golden State", "Dallas")
        ]
        assert _market_is_event_match_winner(rows, "Dallas Wings", "Golden State Valkyries") is True

    def test_a_game_number_with_a_scope_is_still_refused(self):
        rows = [
            {"market_name": "Game 1 Winner: Dallas vs Golden State", "outcome_name": leg}
            for leg in ("Golden State", "Dallas")
        ]
        assert _market_is_event_match_winner(rows, "Dallas Wings", "Golden State Valkyries") is False


class TestNamesAPropQualifier:
    @pytest.mark.parametrize("text", ["Set 1 Winner", "Set Handicap", "Game Spread", "Map Handicap"])
    def test_the_measured_prop_prefixes(self, text):
        assert names_a_prop_qualifier(text) is True

    @pytest.mark.parametrize(
        "text", ["Hangzhou Open (Doubles)", "M25 Setubal, Main Draw", "Roland Garros", "", None]
    )
    def test_tournament_prefixes_and_nothing(self, text):
        assert names_a_prop_qualifier(text) is False


# ══════════════════════════════════════════ door one: /game-markets ══


class TestDoorOneDrawsTheDoublesWinnerOnce:
    def test_kalshi_and_polymarket_fold_to_one_and_the_set_markets_stay(self):
        rows = (
            _gm_rows(D_KALSHI, "kalshi", D_KALSHI_NAME, D_KALSHI_LEGS)
            + _gm_rows(D_POLY, "polymarket", D_POLY_NAME, D_POLY_LEGS)
            + _gm_rows(D_SET1, "polymarket", "Set 1 Winner: Reynolds/Watt vs King/Stevens",
                       [("Reynolds/Watt", 0.59), ("King/Stevens", 0.41)])
            + _gm_rows(D_SET2, "polymarket", "Set 2 Winner: Reynolds/Watt vs King/Stevens",
                       [("Reynolds/Watt", 0.595), ("King/Stevens", 0.405)])
        )
        kept = {r["_market_id"] for r in _fold_duplicate_match_winner_markets(rows, D_HOME, D_AWAY)}
        assert len(kept & {D_KALSHI, D_POLY}) == 1, "the doubles winner is still drawn twice"
        assert {D_SET1, D_SET2} <= kept, "a set market was folded as if it were the match"


class TestDoorOneKeepsTheSinglesSetMarkets:
    def test_the_headline_and_both_set_winners_survive(self):
        rows = (
            _gm_rows(S_HEAD, "polymarket", "M25 Setubal: Alec Deckers vs Philip Henning", S_LEGS)
            + _gm_rows(S_SET1, "polymarket", "Set 1 Winner: Alec Deckers vs Philip Henning", S_LEGS)
            + _gm_rows(S_SET2, "polymarket", "Set 2 Winner: Alec Deckers vs Philip Henning", S_LEGS)
        )
        kept = {r["_market_id"] for r in _fold_duplicate_match_winner_markets(rows, S_HOME, S_AWAY)}
        assert kept == {S_HEAD, S_SET1, S_SET2}

    def test_the_playoff_game_number_still_folds_against_the_other_venue(self):
        home, away = "Dallas Wings", "Golden State Valkyries"
        rows = _gm_rows(62368156, "kalshi", "Game 1: Dallas vs Golden State",
                        [("Golden State", 0.6), ("Dallas", 0.4)]) + _gm_rows(
            62363372, "polymarket", "Dallas vs Golden State",
            [("Golden State", 0.61), ("Dallas", 0.39)])
        kept = {r["_market_id"] for r in _fold_duplicate_match_winner_markets(rows, home, away)}
        assert len(kept) == 1


# ═══════════════════════════════════════ door two: /related-futures ══


class TestDoorTwoDropsTheDoublesHeadlineAndKeepsTheSets:
    def _lists(self):
        home = [
            _rf_row(D_SET1, "Set 1 Winner: Reynolds/Watt vs King/Stevens", "Reynolds/Watt"),
            _rf_row(D_SET2, "Set 2 Winner: Reynolds/Watt vs King/Stevens", "Reynolds/Watt"),
            _rf_row(D_POLY, D_POLY_NAME, "Reynolds/Watt"),
        ]
        away = [
            _rf_row(D_SET1, "Set 1 Winner: Reynolds/Watt vs King/Stevens", "King/Stevens"),
            _rf_row(D_SET2, "Set 2 Winner: Reynolds/Watt vs King/Stevens", "King/Stevens"),
            _rf_row(D_POLY, D_POLY_NAME, "King/Stevens"),
        ]
        return home, away

    def test_by_name(self):
        home, away = self._lists()
        kept_home, kept_away = _fold_event_match_winner_futures(
            home, away, _markets(D_EVENT, D_POLY, D_SET1, D_SET2), D_EVENT, D_HOME, D_AWAY
        )
        ids = {r["market_id"] for r in kept_home + kept_away}
        assert ids == {D_SET1, D_SET2}

    def test_by_headline_id_whatever_the_legs_say(self):
        """The hero's speaker folds even when no leg names a side."""
        home = [_rf_row(D_POLY, D_POLY_NAME, "Team One")]
        away = [_rf_row(D_POLY, D_POLY_NAME, "Team Two")]
        markets = _markets(D_EVENT, D_POLY)

        unfolded = _fold_event_match_winner_futures(home, away, markets, D_EVENT, D_HOME, D_AWAY)
        assert unfolded == (home, away), "control: the name test alone must NOT fold this"

        kept_home, kept_away = _fold_event_match_winner_futures(
            home, away, markets, D_EVENT, D_HOME, D_AWAY, headline_market_ids=frozenset({D_POLY})
        )
        assert kept_home == [] and kept_away == []

    def test_a_speaker_id_linked_to_another_event_is_kept(self):
        home = [_rf_row(D_POLY, D_POLY_NAME, "Team One")]
        away = [_rf_row(D_POLY, D_POLY_NAME, "Team Two")]
        kept = _fold_event_match_winner_futures(
            home, away, _markets(D_EVENT, linked_elsewhere=(D_POLY,)), D_EVENT, D_HOME, D_AWAY,
            headline_market_ids=frozenset({D_POLY}),
        )
        assert kept == (home, away)


class TestDoorTwoKeepsTheSinglesSetMarkets:
    def test_set_winners_stay_and_the_headline_goes(self):
        def rows(leg):
            return [
                _rf_row(S_HEAD, "M25 Setubal: Alec Deckers vs Philip Henning", leg),
                _rf_row(S_SET1, "Set 1 Winner: Alec Deckers vs Philip Henning", leg),
                _rf_row(S_SET2, "Set 2 Winner: Alec Deckers vs Philip Henning", leg),
            ]

        kept_home, kept_away = _fold_event_match_winner_futures(
            rows("Alec Deckers"), rows("Philip Henning"),
            _markets(S_EVENT, S_HEAD, S_SET1, S_SET2), S_EVENT, S_HOME, S_AWAY,
        )
        ids = {r["market_id"] for r in kept_home + kept_away}
        assert ids == {S_SET1, S_SET2}


# ════════════════════════════════════════ the headline id reader ══


def _entry(**record):
    return {"value": 0.45, "eligibility": {"v": 1, **record}}


class TestHeadlineWinnerMarketIds:
    def test_the_production_record(self):
        sources = {
            "polymarket": _entry(status="verified", scope="full_event_winner", market_id=D_POLY),
            "betting": 0.5,
        }
        assert _headline_winner_market_ids(sources) == frozenset({D_POLY})

    def test_a_composite_names_every_contributor(self):
        sources = {
            "kalshi": _entry(
                status="verified", scope="full_event_winner", market_id=1,
                contributors=[{"market_id": 1}, {"market_id": 2}],
            )
        }
        assert _headline_winner_market_ids(sources) == frozenset({1, 2})

    @pytest.mark.parametrize(
        "record",
        [
            {"status": "unverified", "scope": "full_event_winner", "market_id": 7},
            {"status": "ineligible", "scope": "full_event_winner", "market_id": 7},
            {"status": "verified", "scope": "set_winner", "market_id": 7},
            {"status": "verified", "market_id": 7},
        ],
    )
    def test_anything_short_of_a_verified_winner_names_nothing(self, record):
        assert _headline_winner_market_ids({"polymarket": _entry(**record)}) == frozenset()

    def test_a_non_market_source_names_nothing(self):
        sources = {"espn": _entry(status="verified", scope="full_event_winner", market_id=7)}
        assert _headline_winner_market_ids(sources) == frozenset()

    @pytest.mark.parametrize("sources", [None, [], "x", {"polymarket": 0.4}])
    def test_unreadable_columns_name_nothing(self, sources):
        assert _headline_winner_market_ids(sources) == frozenset()


def test_the_route_passes_the_heros_speakers_to_the_fold():
    """The helper tests above all pass against a route that never hands the ids in."""
    import inspect

    from app.routes import events as events_module

    src = inspect.getsource(events_module._build_related_futures)
    call_at = src.find("_fold_event_match_winner_futures(")
    assert call_at != -1
    call = src[call_at : src.find(")\n", call_at) + 1]
    assert "headline_market_ids=_headline_winner_market_ids(event.win_probability_sources)" in call
