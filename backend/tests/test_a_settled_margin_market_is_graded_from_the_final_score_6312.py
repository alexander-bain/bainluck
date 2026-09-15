"""#6312 — a market where EVERY leg lost stops being deleted whole.

## The ship

`/events/15306857` (Gwangju FC 1 · FC Anyang 1, K League 1, **Final**) serves
`spreads: []` while holding a settled, fully graded Kalshi Spread market. Three
of that fixture's four Kalshi markets render; the fourth is absent from every
array of the payload. A reader who saw the spread before kickoff cannot find out
what happened to it.

After this change the page serves all four of its lines, each reading `Lost`.

## 🔴 Measured on production before building (2026-09-15)

Market 60672667, ticker `KXKLEAGUESPREAD-26SEP13GWAANY`, `status='resolved'`,
four outcomes, every one of them:

    is_winner = false · resolution_source = api_settlement
    current_probability = 0.000000 · yes_bid 0.0000 · yes_ask 1.0000

    FC Anyang wins by more than 1.5 goals
    FC Anyang wins by more than 2.5 goals
    Gwangju   wins by more than 1.5 goals
    Gwangju   wins by more than 2.5 goals

The grading is CORRECT — a 1–1 draw means nobody wins by more than any line, so
every leg lost and the market has no winner. `GET /api/events/15306857
/game-markets`, same read: `totals` 6, `other` 4 (the moneyline's two losing
legs among them), **`spreads` 0**.

## 🔴 Three gates, not one, and the first is a falsy zero

Executed against the stored values rather than reasoned about:

    is_empty_book_midpoint(0.0, 0.0, 1.0) × 4  -> False   the #5247 filter SPARES them
    has_no_real_price([0, 0, 0, 0])            -> True    routes/events.py, the dropper
    has_no_real_price([1.0, 0, 0, 0])          -> False   control: a snapped winner survives

`real = [float(p) for p in probs if p]` — **0.0 is falsy**, so four answers read
as no price at all and the market is discarded ~330 lines before
`spreads.append(...)`. Two more gates sit behind it and would have taken the
rows anyway: the deep-OTM spread floor (0.0 < 0.02) and the hoisted `> 0` filter
on the spreads bucket. All three are carved here, and each has its own test.

## 🔴 Why the obvious one-liner is NOT the fix

Exempting settled markets at the `has_no_real_price` line moves the absence, it
does not remove it. The market has NO winner, so `_verdict_is_provable(row,
market_has_a_winner=False)` is False on every leg and the rows are dropped one
layer down. That refusal is deliberate and measured: a VOIDED market is graded
on every leg and won by none — 389 markets across 163 events in a trailing
fortnight — so **from the grades alone a draw and a void are the same shape**.

## ⭐ The route that works: the verdict here is arithmetic

What proves this market all-lost is not its grades but the FINAL SCORE the event
row already holds. Margin 0, so "wins by more than 1.5 goals" is false for both
sides by subtraction — no sibling winner needed, and a void at the venue does
not change what the scoreboard says. `margin_verdict_from_final_score` performs
that subtraction and `_score_proves_this_grade` publishes it only when it
RECOMPUTES the row's own stored grade. The sibling-winner rule is untouched: the
score is an additional route to provable, never a relaxation of that one.

## Why the real endpoint

Every gate under test is inside a 900-line builder, and the three sit ~330,
~300 and ~180 lines apart with the dedup, the ladder walk and the `_window_open`
suppression between them. These tests drive the real `_build_game_markets`
against a doubled session, so the subject is what a reader is SERVED. The pure
parser is covered separately at the bottom, where the grammar can be stated.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import events as events_route
from app.routes.events import _game_markets_cache
from app.utils.final_score_margin import margin_verdict_from_final_score

NOW = datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
FINAL_AT = datetime(2026, 9, 13, 11, 56, tzinfo=timezone.utc)

#: Market 60672667 verbatim: `(outcome_name, current_probability, is_winner,
#: resolution_source)`. The game finished 1–1, so every line is a loser.
SPREAD_MARKET = (
    ("FC Anyang wins by more than 1.5 goals", 0.0, False, "api_settlement"),
    ("FC Anyang wins by more than 2.5 goals", 0.0, False, "api_settlement"),
    ("Gwangju wins by more than 1.5 goals", 0.0, False, "api_settlement"),
    ("Gwangju wins by more than 2.5 goals", 0.0, False, "api_settlement"),
)

#: What production served for it: nothing at all. Held as data so the "before"
#: stays quotable once it is gone.
SERVED_BEFORE: tuple = ()


@pytest.fixture(autouse=True)
def _clear_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


def _result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _market(*, id=901, name="Gwangju vs FC Anyang: Spread",
            external_id="KXKLEAGUESPREAD-26SEP13GWAANY", status="resolved"):
    market = MagicMock()
    market.id, market.name, market.external_id = id, name, external_id
    market.event_id, market.category, market.status = 77, "game_prop", status
    market.source, market.sport_id = "kalshi", 3
    market.llm_sport_category = "soccer"
    market.commence_time = KICKOFF
    market.group_id = market.group_type = None
    market.market_metadata = None
    market.market_tier = 5
    return market


def _outcome(*, id, market_id, name, prob, is_winner=None, resolution_source=None,
             bid=None, ask=None):
    outcome = MagicMock()
    outcome.id, outcome.market_id, outcome.name = id, market_id, name
    outcome.current_probability = prob
    outcome.opening_probability = None
    outcome.current_yes_bid, outcome.current_yes_ask = bid, ask
    outcome.is_winner = is_winner
    outcome.resolution_source = resolution_source
    outcome.last_updated = NOW
    return outcome


def _event(*, status="completed", home_score=1, away_score=1,
           home="Gwangju FC", away="FC Anyang", sport_key="soccer_korea_kleague1"):
    event = MagicMock()
    event.id, event.status, event.sport_id = 77, status, 3
    event.sport = MagicMock()
    event.sport.key = sport_key
    event.home_team_name, event.away_team_name = home, away
    event.home_score, event.away_score = home_score, away_score
    event.commence_time = KICKOFF
    event.completed_at = FINAL_AT if status == "completed" else None
    event.box_score_data = None
    event.period, event.game_clock = (
        ("Final", None) if status == "completed" else ("2nd Half", "62'")
    )
    return event


def _book(prob):
    """The two-sided quote a leg at this price carries.

    🔴 THE BOOK IS PART OF THE SPECIMEN AND PART OF THE FIXTURE'S VALIDITY. All
    four measured legs store `yes_bid 0.0000 / yes_ask 1.0000` — a book with
    nothing in it — and the #5247 empty-book filter SPARES them anyway, because
    their stored 0.0 is nowhere near that book's 0.5 midpoint (condition 3 of
    `is_empty_book_midpoint`, which exists for exactly this case). Reproducing
    the real pair is therefore what puts these rows in front of the code under
    test rather than in front of #5247.

    A non-zero control leg must NOT reuse it: a leg priced 0.5 inside a 0.0/1.0
    book IS the empty-book midpoint and is dropped ~340 lines upstream, which
    silently empties the very fixtures that exist to prove a market reached the
    filter at all. Those legs get a tight book around their own price.
    """
    if prob is None:
        return (None, None)
    if prob == 0.0:
        return (0.0, 1.0)
    return (round(max(0.0, prob - 0.01), 4), round(min(1.0, prob + 0.01), 4))


def _legs(rows, *, market_id=901, first_id=9000):
    return [
        _outcome(
            id=first_id + i,
            market_id=market_id,
            name=name,
            prob=prob,
            is_winner=won,
            resolution_source=source,
            bid=_book(prob)[0],
            ask=_book(prob)[1],
        )
        for i, (name, prob, won, source) in enumerate(rows)
    ]


def _db(markets, outcomes):
    rows = [
        SimpleNamespace(
            id=o.id,
            observed_at=NOW - timedelta(hours=16),
            price_changed_at=None,
            resolution_source=None,
            current_probability=None,
        )
        for o in outcomes
    ]
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(scalar=_db.event),
            _result(rows=[]),          # #2693 folded_event_ids
            _result(rows=markets),
            _result(all_rows=[]),      # polymarket parent groups
            _result(rows=[]),          # unlinked fallback
            _result(rows=outcomes),
            _result(all_rows=rows),    # #4970 the observation load
        ]
    )
    return db


def _payload(markets, outcomes, *, event=None):
    _db.event = event if event is not None else _event()
    response, _status, _ids = asyncio.run(
        events_route._build_game_markets(77, _db(markets, outcomes))
    )
    return response


def _served_spreads(payload):
    """`{outcome_name: row}` for the served spreads bucket."""
    return {s["outcome_name"]: s for s in payload.get("spreads", [])}


# ─────────────────────────────────────────────────────────────────────────────
# THE SHIP
# ─────────────────────────────────────────────────────────────────────────────


class TestADrawsSettledSpreadReachesThePage:
    def test_all_four_lines_of_the_specimen_market_are_served(self):
        """🔴 The required regression, on the measured market verbatim.

        Four legs were stored and ZERO were served.
        """
        served = _served_spreads(_payload([_market()], _legs(SPREAD_MARKET)))

        missing = [name for name, *_ in SPREAD_MARKET if name not in served]
        assert missing == [], (
            f"the settled Spread is still dropped: {missing} "
            f"(production served {list(SERVED_BEFORE)})"
        )
        assert len(served) == 4

    def test_each_line_says_it_lost_rather_than_saying_nothing(self):
        """#4788: the client prints a verdict off these two keys and refuses on
        `is_winner is None`. Serving the rows without them moves the blank card
        one layer down instead of removing it."""
        served = _served_spreads(_payload([_market()], _legs(SPREAD_MARKET)))
        for name, *_ in SPREAD_MARKET:
            assert served[name]["is_winner"] is False, f"{name} carries no verdict"
            assert served[name]["resolution_source"] == "api_settlement"

    def test_a_line_that_did_not_come_in_is_served_as_zero_not_null(self):
        """🔴 `round(prob, 4) if prob else None` — 0.0 is falsy, so the row would
        arrive with a real grade and a NULL number. The 0.0 IS the answer."""
        served = _served_spreads(_payload([_market()], _legs(SPREAD_MARKET)))
        for name, *_ in SPREAD_MARKET:
            assert served[name]["probability"] == 0.0, (
                f"{name} is served {served[name]['probability']!r}"
            )

    def test_the_market_that_HAS_a_winner_on_the_same_page_is_undisturbed(self):
        """The moneyline renders today and must keep rendering — the carve-out is
        additive, not a rewrite of the path every other market takes."""
        moneyline = _market(id=902, name="Gwangju vs FC Anyang",
                            external_id="KXKLEAGUEGAME-26SEP13GWAANY")
        legs = _legs(
            (
                ("Tie", 0.99, True, "api_settlement"),
                ("Gwangju", 0.01, False, "api_settlement"),
                ("FC Anyang", 0.01, False, "api_settlement"),
            ),
            market_id=902,
            first_id=9100,
        )
        payload = _payload([moneyline], legs)
        names = {o["outcome_name"] for o in payload.get("other", [])}
        assert names == {"Tie", "Gwangju", "FC Anyang"}, f"served {names}"

    def test_a_score_proved_winner_and_its_losing_siblings_all_reach_the_page(self):
        """The other direction of the same proof, on a game that was NOT a draw.

        Gwangju 2 · FC Anyang 0: the 1.5 line came in, the 2.5 line did not, and
        the away lines never could. Every row is served, each with its own
        verdict, and every one of the three agrees with the scoreboard.
        """
        rows = (
            ("Gwangju wins by more than 1.5 goals", 1.0, True, "api_settlement"),
            ("Gwangju wins by more than 2.5 goals", 0.0, False, "api_settlement"),
            ("FC Anyang wins by more than 1.5 goals", 0.0, False, "api_settlement"),
        )
        served = _served_spreads(
            _payload(
                [_market()],
                _legs(rows),
                event=_event(home_score=2, away_score=0),
            )
        )
        assert set(served) == {name for name, *_ in rows}, f"served {sorted(served)}"
        assert served["Gwangju wins by more than 1.5 goals"]["is_winner"] is True
        assert served["Gwangju wins by more than 2.5 goals"]["is_winner"] is False
        assert served["FC Anyang wins by more than 1.5 goals"]["is_winner"] is False


# ─────────────────────────────────────────────────────────────────────────────
# THE OTHER DIRECTION — readmitting every zero is not a fix
#
# Each test here fails if any of the three carve-outs is written as an
# unconditional exemption, which is the mutation that satisfies every test above.
# ─────────────────────────────────────────────────────────────────────────────


class TestAZeroTheScoreboardDoesNotDecideStillGoes:
    def test_a_voided_market_whose_grades_the_score_contradicts_stays_dropped(self):
        """🔴 THE VOID CONTROL, and the whole reason this is a RECOMPUTATION.

        Gwangju won 3–0, and the venue has graded EVERY leg a loser — the
        signature of a void. The score says "Gwangju wins by more than 1.5
        goals" is TRUE, the row says it lost; one of the two is wrong and
        nothing here can tell which, so nothing is published and the market
        keeps today's behaviour.

        🔴 THE 0.5 LEG IS THE FIXTURE, NOT DECORATION. Void every leg to 0.0 and
        `has_no_real_price` drops the market ~330 lines upstream for the ORIGINAL
        reason, so the rows never reach the code under test and the test proves
        nothing (the #6196 suite learned this the hard way). #6169's own void
        specimen, `/events/15311870`, carried all 45 legs at exactly 0.500000.
        """
        voided = (
            ("FC Anyang wins by more than 1.5 goals", 0.5, False, "clob_authoritative"),
            ("Gwangju wins by more than 1.5 goals", 0.0, False, "clob_authoritative"),
        )
        served = _served_spreads(
            _payload(
                [_market()],
                _legs(voided),
                event=_event(home_score=3, away_score=0),
            )
        )
        assert "FC Anyang wins by more than 1.5 goals" in served, (
            "fixture did not survive `has_no_real_price` — this test is vacuous "
            "without a non-zero leg"
        )
        assert "Gwangju wins by more than 1.5 goals" not in served, (
            "a leg the scoreboard REFUTES was published as a verdict"
        )

    def test_a_live_games_zero_line_is_still_dropped(self):
        """🔴 The anti-strawman. #921's behaviour is unchanged while the question
        is open: a 0% line on a game in play is a dead quote, not an answer."""
        live = (
            ("Gwangju wins by more than 1.5 goals", 0.40, None, None),
            ("Gwangju wins by more than 2.5 goals", 0.0, None, None),
        )
        served = _served_spreads(
            _payload(
                [_market(status="open")],
                _legs(live),
                event=_event(status="live", home_score=1, away_score=0),
            )
        )
        assert "Gwangju wins by more than 1.5 goals" in served, f"built {sorted(served)}"
        assert "Gwangju wins by more than 2.5 goals" not in served, (
            "a live 0% quote was published as a verdict"
        )

    def test_an_ungraded_zero_on_a_finished_game_is_still_dropped(self):
        """A finished game is not enough — the ROW must carry a grade. The score
        recomputes a grade, it does not manufacture one for an ungraded row."""
        rows = (
            ("Gwangju wins by more than 1.5 goals", 0.99, True, "api_settlement"),
            ("FC Anyang wins by more than 1.5 goals", 0.0, None, None),
        )
        served = _served_spreads(
            _payload([_market()], _legs(rows), event=_event(home_score=3, away_score=0))
        )
        assert "Gwangju wins by more than 1.5 goals" in served
        assert "FC Anyang wins by more than 1.5 goals" not in served, (
            "an ungraded 0.0 was served as a verdict"
        )

    def test_a_tier_one_retraction_at_zero_is_still_dropped(self):
        """`ungradeable_result` is a RETRACTION, tier 1 — a reading of a price,
        never an answer (#5411). The scoreboard does not promote it."""
        rows = (
            ("Gwangju wins by more than 1.5 goals", 0.99, True, "api_settlement"),
            ("FC Anyang wins by more than 1.5 goals", 0.0, False, "ungradeable_result"),
        )
        served = _served_spreads(
            _payload([_market()], _legs(rows), event=_event(home_score=3, away_score=0))
        )
        assert "Gwangju wins by more than 1.5 goals" in served
        assert "FC Anyang wins by more than 1.5 goals" not in served, (
            "a tier-1 retraction was served as a verdict"
        )

    def test_an_unscored_event_proves_nothing_and_the_market_stays_dropped(self):
        """The ghost row this fixture's markets actually hang off
        (`15307681`, status `suspended`) stores NULL scores. Without a score
        there is no subtraction and therefore no proof."""
        served = _served_spreads(
            _payload(
                [_market()],
                _legs(SPREAD_MARKET),
                event=_event(home_score=None, away_score=None),
            )
        )
        assert served == {}, f"a scoreless event produced verdicts: {sorted(served)}"

    def test_an_ambiguous_team_name_resolves_to_neither_side(self):
        """"New York" on a Red Bulls/City matchup names both clubs, so it names
        no side and the margin cannot be computed for it."""
        rows = (
            ("New York wins by more than 1.5 goals", 0.5, False, "api_settlement"),
            ("New York wins by more than 2.5 goals", 0.0, False, "api_settlement"),
        )
        served = _served_spreads(
            _payload(
                [_market()],
                _legs(rows),
                event=_event(home_score=1, away_score=1,
                             home="New York Red Bulls", away="New York City FC"),
            )
        )
        assert "New York wins by more than 1.5 goals" in served, (
            "fixture did not reach the code under test"
        )
        assert "New York wins by more than 2.5 goals" not in served, (
            "a verdict was published under an unresolved club's name"
        )


# ─────────────────────────────────────────────────────────────────────────────
# THE PARSER — grammar, and the four refusals
# ─────────────────────────────────────────────────────────────────────────────


class TestMarginVerdictFromFinalScore:
    def test_the_specimens_four_legs_are_all_refuted_by_a_draw(self):
        for name in (
            "Gwangju wins by more than 1.5 goals",
            "Gwangju wins by more than 2.5 goals",
            "FC Anyang wins by more than 1.5 goals",
            "FC Anyang wins by more than 2.5 goals",
        ):
            assert margin_verdict_from_final_score(
                name, "soccer_korea_kleague1", "Gwangju FC", "FC Anyang", 1, 1
            ) is False, name

    def test_it_answers_true_as_readily_as_false(self):
        """A refutation and a confirmation are both proofs; only `None` is not."""
        assert margin_verdict_from_final_score(
            "Gwangju wins by more than 1.5 goals",
            "soccer_korea_kleague1", "Gwangju FC", "FC Anyang", 3, 0,
        ) is True

    def test_the_away_side_subtracts_the_other_way_round(self):
        """🔴 The inversion that makes a wrong side worse than no side."""
        assert margin_verdict_from_final_score(
            "FC Anyang wins by more than 1.5 goals",
            "soccer_korea_kleague1", "Gwangju FC", "FC Anyang", 0, 3,
        ) is True
        assert margin_verdict_from_final_score(
            "Gwangju wins by more than 1.5 goals",
            "soccer_korea_kleague1", "Gwangju FC", "FC Anyang", 0, 3,
        ) is False

    def test_over_is_the_same_comparator_as_more_than(self):
        """65,230 of the 92,583 measured rows say "over"; 27,257 say "more than"."""
        assert margin_verdict_from_final_score(
            "Dodgers wins by over 2 runs", "baseball_mlb", "Dodgers", "Padres", 5, 2,
        ) is True
        assert margin_verdict_from_final_score(
            "Dodgers wins by over 3 runs", "baseball_mlb", "Dodgers", "Padres", 5, 2,
        ) is False, "an exact-3 margin does not clear a strictly-greater-than-3 line"

    def test_or_more_is_inclusive_and_over_is_not(self):
        """🔴 The two spellings differ in their COMPARATOR, and a margin exactly
        on the line is the only input that tells them apart."""
        assert margin_verdict_from_final_score(
            "Celtics wins by 5 or more points", "basketball_nba", "Celtics", "Heat",
            105, 100,
        ) is True
        assert margin_verdict_from_final_score(
            "Celtics wins by over 5 points", "basketball_nba", "Celtics", "Heat",
            105, 100,
        ) is False

    def test_a_band_question_is_refused_rather_than_read_as_a_threshold(self):
        """"wins by 1 to 3 points" (64 rows) is a BAND. Its first number is not a
        threshold and reading it as one would answer a different question."""
        assert margin_verdict_from_final_score(
            "Celtics wins by 1 to 3 points", "basketball_nba", "Celtics", "Heat",
            105, 100,
        ) is None

    def test_a_unit_this_sport_does_not_score_in_is_refused(self):
        """🔴 The scale trap. `home_score` on a tennis row is not proven here to
        be sets, so "wins by over 1.5 sets" (204 rows) is refused rather than
        subtracted against a column whose unit is unknown."""
        assert margin_verdict_from_final_score(
            "Alcaraz wins by over 1.5 sets", "tennis_atp_us_open",
            "Alcaraz", "Sinner", 3, 1,
        ) is None
        assert margin_verdict_from_final_score(
            "Gwangju wins by more than 1.5 points", "soccer_korea_kleague1",
            "Gwangju FC", "FC Anyang", 3, 0,
        ) is None, "a points question on a goals sport is a scale mismatch"

    def test_a_question_carrying_no_unit_is_refused(self):
        assert margin_verdict_from_final_score(
            "Gwangju wins by more than 1.5", "soccer_korea_kleague1",
            "Gwangju FC", "FC Anyang", 3, 0,
        ) is None

    def test_a_missing_or_non_integer_score_is_refused(self):
        for home, away in ((None, 1), (1, None), ("1", 1), (True, False)):
            assert margin_verdict_from_final_score(
                "Gwangju wins by more than 1.5 goals", "soccer_korea_kleague1",
                "Gwangju FC", "FC Anyang", home, away,
            ) is None, (home, away)

    def test_shapes_that_are_not_margin_questions_are_refused(self):
        for name in (
            "Gwangju",
            "Tie",
            "Over 2.5 goals scored",
            "Gwangju wins",
            "Gwangju -1.5",
            "",
            None,
        ):
            assert margin_verdict_from_final_score(
                name, "soccer_korea_kleague1", "Gwangju FC", "FC Anyang", 1, 1,
            ) is None, repr(name)
