"""#5896 — the TWO-MINUTE beat stops writing a settlement back as a price.

## the ship, as the reader sees it

`/events/15313044` — *Derepasko / Lomakin vs Matsuda / Sharma*, ATP Challenger
doubles — served **"Starts in 1h 18m"** above a **1% – 99%** "Aggregate" hero on
2026-09-16, while Kalshi had `finalized` both legs of
`KXATPCHALLENGERDOUBLES-26SEP15DERLOMMATSHA` at 04:24:57Z with `result` declared
on each. The match was over. The page advertised a future kick-off and printed
the settlement grade as a live probability.

## why the fix that already shipped did not fix it

Three writers put a price on a linked Kalshi leg. Two of them — `:20`
`_refresh_linked_game_books` and `:50` `futures_price_refresh` — learned to
refuse a settlement before kick-off (#5771, then CERT-2933/2936/2938). Both run
HOURLY, on `bainluck-heavy`. The third,
`_poll_live_prediction_market_prices`, runs every **two minutes**, on the main
app, over "live events OR scheduled events inside NOW()+3h" — which is exactly
the pre-kick-off window this ship is about — and it had neither gate.

Measured end to end on production, first execution of the shipped code anywhere
(heavy reached the carrying release at 03:43Z):

    05:20:00.048Z  refresh_linked_game_books received
    05:24:43.059Z  withdrew 2 settled quotes + 1 hero on market 61143994
    05:24:45Z      rows read back: both legs NULL, hero key absent   <- it worked
    05:25:44Z      the two-minute beat wrote 0.990000 and the hero BACK
    05:26:58Z      still 0.99

**The ship lived 61 seconds.** The hourly writers refuse 24× a day each; this
one restores up to 720×, so the artifact was on the row ~98% of the time and no
reader ever saw a difference. A pass whose counters read
`pre_kickoff_quotes_withdrawn: 6` was, on the page, a no-op.

## the rule was already stated here, and only half built

The `#4356` branch this file's arms sit beside says, in the source, in these
words: *"Clearing the leg in `_refresh_linked_game_books` alone is therefore not
the ship: this poller would restore it exactly when the reader is most likely to
be looking. Both writers have to agree."* That was built for the leg the venue
**withdrew**. The leg the venue **answered** is the same structure with the sign
flipped, and it never got the same treatment.

## the ladder of controls, and why each one is load-bearing

The dangerous version of this fix is "stop pricing anything the venue has
answered". That would wipe the closing line of every finished game — the
evidence calibration reads (gotcha #21) — and settled means settled. So the
refusal needs BOTH halves of its gate and each half has a control here:

* a game that is **live** keeps its price even when the venue has answered it;
* a game **past its own `commence_time`** keeps its price likewise;
* a **pre-kick-off** game whose venue book is still trading (`result` is the
  EMPTY STRING, not `None` — see `venue_answered`) is priced exactly as before;
* a **graded** row and a row holding a **captured closing line** are never
  un-priced even when both halves of the gate are satisfied.

The arm that would have caught the production defect is
`test_a_leg_the_hourly_pass_already_withdrew_is_not_restored`: it starts from
the post-withdrawal state and asserts this beat leaves it alone. That is the 61
seconds, as a test.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import asyncio

import pytest
from sqlalchemy import Select, Update
from sqlalchemy.sql.elements import TextClause

from app.services.kalshi_api import KalshiAPIService
from app.tasks import prediction_market_matching as pmm
from app.utils.futures_liveness import event_pre_kickoff, venue_answered

# `pytest.ini` runs asyncio in AUTO mode, so the coroutines below need no mark.


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# the harness — the shape `test_live_poll_commit_boundary_5682.py` established,
# carried here rather than imported: a test module importing another test
# module couples two files' collection order, and these arms need their own
# rows anyway (a settled book, which that file has no reason to hold).
# --------------------------------------------------------------------------


class _Outcome:
    def __init__(self, oid, market_id, external_id, name, *, probability=None):
        self.id = oid
        self.market_id = market_id
        self.external_id = external_id
        self.name = name
        self.rank = 1
        self.current_probability = probability
        self.current_american_odds = None if probability is None else -9900
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.probability_change_24h = None
        self.is_winner = None
        self.calibration_probability = None
        self.last_updated = None


class _Market:
    def __init__(self, mid, source, external_id):
        self.id = mid
        self.source = source
        self.external_id = external_id
        self.name = f"market {mid}"
        self.market_type = "game_winner"
        self.market_metadata = None


class _Event:
    def __init__(self, eid, *, status="scheduled", commence=None, completed_at=None):
        self.id = eid
        self.status = status
        self.home_team_name = "Matsuda / Sharma"
        self.away_team_name = "Derepasko / Lomakin"
        # #6608 — the beat's blend group now carries #5820's tri-state, read off
        # this row. `None` is faithful for a pre-kickoff double: no result yet.
        # Carried here even though no arm in this file currently reaches the
        # blend stage, because the absence is a latent AttributeError for the
        # next arm that does — which is exactly how it was found, twice.
        self.completed_at = completed_at
        # Default: inside the poll's +3h population and comfortably clear of
        # the 15-minute pregame-pin window, so an arm aimed at the price loop
        # is not quietly also exercising the pin.
        self.commence_time = commence or (_now() + timedelta(hours=1, minutes=20))


@dataclass
class _Population:
    rows: list
    outcomes: list


def _classify(stmt) -> str:
    if isinstance(stmt, TextClause):
        return "text"
    if isinstance(stmt, Select):
        names = [c.get("name") for c in stmt.column_descriptions]
        if "FuturesMarket" in names:
            return "population"
        if names == ["FuturesOutcome"]:
            return "outcomes"
        return "select:" + ",".join(str(n) for n in names)
    if isinstance(stmt, Update):
        return "update"
    return "insert"


class _Result:
    def __init__(self, rows=(), scalar_value=None):
        self._rows = list(rows)
        self._scalar = scalar_value
        self.rowcount = len(self._rows)

    def all(self):
        return list(self._rows)

    def fetchall(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return _Scalars(self._rows)

    def scalar_one_or_none(self):
        return self._scalar

    def scalar(self):
        return self._scalar

    def __iter__(self):
        return iter(self._rows)


class _Scalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, population: _Population):
        self._population = population
        self.journal = []
        self.added = []

    async def execute(self, stmt, params=None):
        kind = _classify(stmt)
        self.journal.append(kind)
        if kind == "population":
            return _Result(self._population.rows)
        if kind == "outcomes":
            return _Result(self._population.outcomes)
        return _Result()

    async def commit(self):
        self.journal.append("commit")

    async def rollback(self):
        self.journal.append("rollback")

    def expunge_all(self):
        self.journal.append("expunge_all")

    def add(self, obj):
        self.added.append(obj)


def _leg(ticker, event_ticker, *, bid=0.98, ask=1.00, result="", status="active"):
    """One leg in the venue's CURRENT dialect (#3569 — `*_dollars`, never cents).

    ``result`` defaults to the EMPTY STRING because that is what Kalshi sends
    while a contract trades; `None` is not a state the venue produces and an
    arm built on it would be testing a shape that cannot arrive.
    """
    return {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "title": "Matsuda / Sharma win",
        "yes_sub_title": "Matsuda / Sharma",
        "status": status,
        "result": result,
        "yes_bid_dollars": f"{bid:.4f}",
        "yes_ask_dollars": f"{ask:.4f}",
        "last_price_dollars": f"{(bid + ask) / 2:.4f}",
        "volume_fp": "1000",
    }


class _KalshiService:
    """The venue, answered with RAW dicts through the REAL parser."""

    def __init__(self, payloads):
        self._payloads = payloads
        self._real = KalshiAPIService()
        self.fetched = []

    async def get_markets(self, event_ticker=None, status=None, limit=None):
        self.fetched.append(event_ticker)
        return list(self._payloads.get(event_ticker, [])), None

    def parse_markets(self, raw):
        return self._real.parse_markets(raw)

    async def close(self):
        return None


EVENT_TICKER = "KXATPCHALLENGERDOUBLES-26SEP15DERLOMMATSHA"
LEG_TICKER = f"{EVENT_TICKER}-MATSHA"


def _beat(*, event_status="scheduled", commence=None, stored_probability=0.99):
    """One Kalshi market on one event, with one leg we already hold."""
    market = _Market(61143994, "kalshi", EVENT_TICKER)
    event = _Event(15313044, status=event_status, commence=commence)
    outcome = _Outcome(
        1, market.id, LEG_TICKER, "Matsuda / Sharma", probability=stored_probability
    )
    return _Population([(market, event)], [outcome]), outcome


async def _run(monkeypatch, session, kalshi):
    """Run the REAL beat against the fake session and the fake venue."""

    @asynccontextmanager
    async def _fake_session():
        yield session

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(pmm, "get_task_session", _fake_session)
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(
        "app.services.kalshi_api.KalshiAPIService", lambda *a, **kw: kalshi
    )
    # The blend stage is off: these arms are aimed at the price loop, and a
    # blend that silently declined would be an invisible reason for a green
    # arm. `None` from the primary selector is the documented "no market can
    # speak" path. The hero coupling has its own arm at the bottom of the file.
    monkeypatch.setattr(pmm, "_select_primary_market", lambda group: None)
    return await pmm._poll_live_prediction_market_prices()


# --------------------------------------------------------------------------
# the premise, asserted rather than assumed
# --------------------------------------------------------------------------


class TestThePremise:
    def test_the_venue_says_trading_with_an_empty_string_not_a_none(self):
        """If this ever flips, every `result=""` control below goes vacuous."""
        assert venue_answered("") is False
        assert venue_answered(None) is False
        assert venue_answered("yes") is True
        assert venue_answered("no") is True

    def test_the_fixture_book_parses_to_the_price_the_arms_expect(self):
        """A control that asserts "still 0.99" is worthless if the harness
        could never have produced a price at all."""
        parsed = KalshiAPIService().parse_markets([_leg(LEG_TICKER, EVENT_TICKER)])
        assert len(parsed) == 1
        assert parsed[0].ticker == LEG_TICKER
        assert parsed[0].yes_bid == pytest.approx(0.98)


# --------------------------------------------------------------------------
# event_pre_kickoff — one restatement of the hourly writers' SQL clause
# --------------------------------------------------------------------------


class TestEventPreKickoff:
    def test_scheduled_and_still_ahead_of_us_is_pre_kickoff(self):
        now = _now()
        assert event_pre_kickoff(_Event(1, commence=now + timedelta(minutes=1)), now=now)

    def test_scheduled_but_already_past_its_own_clock_is_not(self):
        now = _now()
        assert not event_pre_kickoff(
            _Event(1, commence=now - timedelta(seconds=1)), now=now
        )

    @pytest.mark.parametrize("status", ["live", "completed", "closed", "postponed"])
    def test_only_scheduled_counts(self, status):
        """A live game's price is a price. This is the half of the gate that
        keeps `settled means settled` intact."""
        now = _now()
        assert not event_pre_kickoff(
            _Event(1, status=status, commence=now + timedelta(hours=1)), now=now
        )

    def test_a_missing_event_declines_rather_than_guessing(self):
        assert not event_pre_kickoff(None, now=_now())

    def test_a_missing_commence_time_declines_rather_than_guessing(self):
        """The only action gated on this is a WITHDRAWAL, so "we cannot say"
        must mean "do not act", never "act"."""
        event = _Event(1)
        event.commence_time = None
        assert not event_pre_kickoff(event, now=_now())

    def test_a_naive_clock_raises_instead_of_comparing_wrongly(self):
        """`commence_time` is `timestamptz`. A naive `now` is a caller bug and
        the honest failure is loud — silently treating it as UTC is how a
        clock defect becomes a data defect (gotcha #44)."""
        with pytest.raises(TypeError):
            event_pre_kickoff(_Event(1), now=datetime.now())


# --------------------------------------------------------------------------
# the ship
# --------------------------------------------------------------------------


class TestTheBeatRefusesASettledPreKickoffBook:
    async def test_a_settled_leg_before_kickoff_is_not_repriced(self, monkeypatch):
        population, outcome = _beat()
        session = _Session(population)
        service = _KalshiService(
            {EVENT_TICKER: [_leg(LEG_TICKER, EVENT_TICKER, result="yes",
                                 status="finalized")]}
        )

        stats = await _run(monkeypatch, session, service)

        assert service.fetched == [EVENT_TICKER], "the beat must still READ the venue"
        assert stats["kalshi_pre_kickoff_settled_legs"] == 1
        assert stats["kalshi_pre_kickoff_settled_cleared"] == 1
        assert stats["kalshi_outcomes_updated"] == 0
        assert outcome.current_probability is None
        assert outcome.current_american_odds is None

    async def test_a_leg_the_hourly_pass_already_withdrew_is_not_restored(
        self, monkeypatch
    ):
        """THE PRODUCTION DEFECT, as a test.

        Start from the state the `:20` pass leaves behind at 05:24:43Z — the
        price already taken off — and run this beat. Before the repair it wrote
        0.99 straight back 61 seconds later; the whole ship is that it no
        longer does.
        """
        population, outcome = _beat(stored_probability=None)
        session = _Session(population)
        service = _KalshiService(
            {EVENT_TICKER: [_leg(LEG_TICKER, EVENT_TICKER, result="yes",
                                 status="finalized")]}
        )

        stats = await _run(monkeypatch, session, service)

        assert outcome.current_probability is None, (
            "the two-minute beat restored a price the hourly pass had withdrawn "
            "- this is the 61-second flicker #5896 was measured to have"
        )
        assert stats["kalshi_outcomes_updated"] == 0
        assert stats["kalshi_pre_kickoff_settled_legs"] == 1
        assert stats["kalshi_pre_kickoff_settled_cleared"] == 0, (
            "nothing was on the row to take back, so the CLEARED counter must "
            "stay 0 - it counts writes, not refusals"
        )

    async def test_the_refused_leg_mints_no_chart_point(self, monkeypatch):
        """A chart point for a settlement is the same fiction as the price —
        the `#4356` branch's argument, applied to the answered leg."""
        population, _ = _beat()
        session = _Session(population)
        service = _KalshiService(
            {EVENT_TICKER: [_leg(LEG_TICKER, EVENT_TICKER, result="yes",
                                 status="finalized")]}
        )

        stats = await _run(monkeypatch, session, service)

        assert session.added == []
        assert stats["futures_snapshots_written"] == 0


class TestTheControlsThatKeepSettledMeaningSettled:
    async def test_a_live_game_keeps_its_price_even_when_the_venue_answered(
        self, monkeypatch
    ):
        """Settled means settled: a finished game's closing line is
        calibration's evidence (gotcha #21). The refusal is about the price
        column of a contest that has NOT started."""
        population, outcome = _beat(event_status="live")
        session = _Session(population)
        service = _KalshiService(
            {EVENT_TICKER: [_leg(LEG_TICKER, EVENT_TICKER, result="yes",
                                 status="finalized")]}
        )

        stats = await _run(monkeypatch, session, service)

        assert stats["kalshi_pre_kickoff_settled_legs"] == 0
        assert outcome.current_probability is not None
        assert stats["kalshi_outcomes_updated"] == 1

    async def test_a_game_past_its_own_commence_time_keeps_its_price(
        self, monkeypatch
    ):
        population, outcome = _beat(commence=_now() - timedelta(minutes=5))
        session = _Session(population)
        service = _KalshiService(
            {EVENT_TICKER: [_leg(LEG_TICKER, EVENT_TICKER, result="yes",
                                 status="finalized")]}
        )

        stats = await _run(monkeypatch, session, service)

        assert stats["kalshi_pre_kickoff_settled_legs"] == 0
        assert outcome.current_probability is not None

    async def test_a_pre_kickoff_book_that_is_still_trading_is_priced_as_before(
        self, monkeypatch
    ):
        """The gate is the venue's `result`, never the price. A 0.98/1.00 book
        on a game that has not started is a real quote and must survive — this
        is the arm that stops the fix from blanking heavy favourites."""
        population, outcome = _beat(stored_probability=None)
        session = _Session(population)
        service = _KalshiService({EVENT_TICKER: [_leg(LEG_TICKER, EVENT_TICKER)]})

        stats = await _run(monkeypatch, session, service)

        assert stats["kalshi_pre_kickoff_settled_legs"] == 0
        assert stats["kalshi_pre_kickoff_settled_cleared"] == 0
        assert outcome.current_probability is not None
        assert stats["kalshi_outcomes_updated"] == 1


class TestTheClearRefusesTheRowsItMustNeverTouch:
    """`_clear_outcome_price`'s three conditions, asked through the #5896 door.

    They are shared with `_clear_withdrawn_outcome` now, so an arm here also
    protects #4356 — and the two counters below are what keeps the two facts
    from collapsing into one number.
    """

    def _outcome(self):
        return _Outcome(1, 61143994, LEG_TICKER, "Matsuda / Sharma", probability=0.99)

    def test_a_graded_row_is_never_un_priced(self):
        outcome = self._outcome()
        outcome.is_winner = True
        stats = {"kalshi_pre_kickoff_settled_cleared": 0}

        assert pmm._clear_pre_kickoff_settled_outcome(outcome, _now(), stats) is False
        assert outcome.current_probability == 0.99
        assert stats["kalshi_pre_kickoff_settled_cleared"] == 0

    def test_a_captured_closing_line_is_never_wiped(self):
        outcome = self._outcome()
        outcome.calibration_probability = 0.62
        stats = {"kalshi_pre_kickoff_settled_cleared": 0}

        assert pmm._clear_pre_kickoff_settled_outcome(outcome, _now(), stats) is False
        assert outcome.current_probability == 0.99
        assert stats["kalshi_pre_kickoff_settled_cleared"] == 0

    def test_an_already_clear_leg_is_not_restamped_every_two_minutes(self):
        """`last_updated` is a freshness gate other code reads
        (`routes/playoffs.py` drops a stale outcome from the grid), so a
        restamp is not free."""
        outcome = self._outcome()
        outcome.current_probability = None
        outcome.last_updated = None
        stats = {"kalshi_pre_kickoff_settled_cleared": 0}

        assert pmm._clear_pre_kickoff_settled_outcome(outcome, _now(), stats) is False
        assert outcome.last_updated is None
        assert stats["kalshi_pre_kickoff_settled_cleared"] == 0

    def test_the_two_reasons_keep_two_counters(self):
        """A leg the venue took BACK and a leg the venue ANSWERED are opposite
        facts. One number cannot say both, which is the same argument that
        keeps `books_unreadable` apart from the withdrawn counter."""
        now = _now()
        settled_stats = {
            "kalshi_pre_kickoff_settled_cleared": 0,
            "kalshi_outcomes_withdrawn_cleared": 0,
        }
        withdrawn_stats = dict(settled_stats)

        assert pmm._clear_pre_kickoff_settled_outcome(
            self._outcome(), now, settled_stats
        )
        assert pmm._clear_withdrawn_outcome(self._outcome(), now, withdrawn_stats)

        assert settled_stats == {
            "kalshi_pre_kickoff_settled_cleared": 1,
            "kalshi_outcomes_withdrawn_cleared": 0,
        }
        assert withdrawn_stats == {
            "kalshi_pre_kickoff_settled_cleared": 0,
            "kalshi_outcomes_withdrawn_cleared": 1,
        }


class TestClearingTheLegIsWhatStopsTheHero:
    """The coupling the repair relies on instead of a second statement.

    The blend stage later in the same beat reads the very objects the price
    loop just mutated (`pop.outcomes_by_market` and `pop.outcome_lookup` are
    built from one `scalars().all()` and hold the SAME instances). So a leg
    with no price leaves the blend nothing to speak from and the
    `win_probability_sources` write is skipped — which is why this repair never
    goes near the event row.
    """

    def test_a_group_whose_legs_have_no_price_asserts_nothing(self):
        from app.utils.live_blend import MarketOutcomes, compute_source_home_probability

        market = _Market(61143994, "kalshi", EVENT_TICKER)
        cleared = _Outcome(1, market.id, LEG_TICKER, "Matsuda / Sharma")
        cleared.current_probability = None

        reading = compute_source_home_probability(
            [MarketOutcomes(market=market, outcomes=[cleared])],
            "Matsuda / Sharma",
            "Derepasko / Lomakin",
        )

        assert reading is None, (
            "if the blend can speak from a price-less leg, clearing the leg is "
            "no longer sufficient and #5896 needs an explicit hero statement here"
        )


class TestTheClearedCounterSurvivesNothingTheWriteDoesNot:
    """#5682's rule, applied to this ship's two new counters.

    `_recover` rolls every counter in `_durable_counters` back to the last
    commit boundary, because a write counter that outlives the write it counted
    lies in the one direction that hides an outage. The two counters #5896 adds
    are opposite kinds and must be sorted accordingly: `_cleared` counts a WRITE
    this pass made, `_legs` counts what the VENUE said. The distinction is the
    whole reason they are two numbers, so it is pinned rather than trusted.

    Read from the source tuple rather than by driving a rollback: the mechanism
    already has its own arms in `test_live_poll_commit_boundary_5682.py`, and
    what is unproven here is MEMBERSHIP — which is a fact about that tuple.
    """

    @staticmethod
    def _durable_counter_names() -> set[str]:
        import ast
        from pathlib import Path

        tree = ast.parse(Path(pmm.__file__).read_text())
        found: list[set[str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "_durable_counters" not in targets:
                continue
            assert isinstance(node.value, ast.Tuple), (
                "`_durable_counters` is no longer a literal tuple, so this arm "
                "can no longer read its membership — teach it the new shape "
                "rather than deleting the check"
            )
            found.append(
                {e.value for e in node.value.elts if isinstance(e, ast.Constant)}
            )

        assert len(found) == 1, (
            f"expected exactly one `_durable_counters` assignment, found {len(found)}"
        )
        return found[0]

    def test_the_cleared_counter_is_rolled_back_with_its_write(self):
        names = self._durable_counter_names()

        assert "kalshi_pre_kickoff_settled_cleared" in names, (
            "`kalshi_pre_kickoff_settled_cleared` counts a price this pass took "
            "off a row. Outside `_durable_counters` it survives the rollback of "
            "that very write, so a failed item reports a settlement we took back "
            "while the settlement is still on the row — #5682's lying counter, "
            "and the number the #5896 after-check reads to decide the ship works"
        )

    def test_its_withdrawn_twin_is_there_too_so_this_is_not_an_arbitrary_name(self):
        """Pins the PAIRING, not a constant: both clears write, so both roll back."""
        names = self._durable_counter_names()

        assert "kalshi_outcomes_withdrawn_cleared" in names, (
            "the #4356 clear's counter left `_durable_counters` — the two clears "
            "share one body (`_clear_outcome_price`) and one durability rule, so "
            "either both counters are in that tuple or neither claim holds"
        )

    def test_the_legs_counter_is_NOT_rolled_back(self):
        """The observation half. A venue fact is not undone by our rollback."""
        names = self._durable_counter_names()

        assert "kalshi_pre_kickoff_settled_legs" not in names, (
            "`kalshi_pre_kickoff_settled_legs` counts what the VENUE said — that "
            "it has answered this contract — which stays true however our "
            "transaction ends. Rolling it back would under-report the refusal on "
            "exactly the passes that failed, and `_legs` high with `_cleared` 0 "
            "is this ship's healthy steady state, not a dead branch"
        )
