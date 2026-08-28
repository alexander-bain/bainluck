"""#2214 — the game card carries every source: Kalshi game markets get ingested.

The ship: a live MLB game card shows `kalshi` among its sources.

The mechanism, measured on production 2026-08-26 before this suite existed:

* `futures_markets` holds 1,940 `KXMLBGAME` rows, **all `resolved`**, newest
  created 2026-08-19. Not one game market created in a week.
* The scan report ring says why, and says it without ambiguity:
  `events_fetched 16,340`, `events_processed 389`, `loop_deadline_hit false`
  on all 12 beats, `verdict frozen` on all 12. The upsert loop did NOT run out
  of time. It reached every event and dropped 15,951 of them on
  `if not event.markets: continue`.
* The events were empty because `_HEAVY_TOKENS` fetches the game-level series
  WITHOUT nested markets on the explicit promise that a later step backfills
  their markets per-event — and that step was structurally last in the fetch
  budget with no reserve, so `_past_deadline()` was already true when control
  reached it. It did zero work, deterministically, every beat.

This is the same failure #999 fixed one stage higher in the same function, and
the fix is the same shape: a reserved floor. Two of these tests fail against the
pre-fix code; the last three are the acceptance's must-not-regress controls and
pass both before and after, which is the point of them.

Frozen acceptance: `C-GAMECARD-LINK-1` (measurement lane), G1/G2/G3.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.kalshi_api import KalshiAPIService, KalshiEvent

# `event_series_ticker` / `order_market_backfill_candidates` are imported INSIDE
# the tests that need them, deliberately. A module-level import of a symbol the
# fix introduces turns the whole file into a collection error against pre-fix
# code — pytest exit 2, which is a story about the harness, not a result
# (gotcha #54). The red-first proof that matters is the BEHAVIOURAL one below:
# it uses only pre-existing symbols, so against pre-fix code it collects, runs,
# and fails on the defect itself.

# The slate the mapping table in C-GAMECARD-LINK-PREP-1 froze. `BOS @ MIA`
# 22:40Z is the red-first specimen: canonical event 15291944.
RED_FIRST_TICKER = "KXMLBGAME-26AUG26BOSMIA"
NOW = datetime(2026, 8, 26, 18, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# G1a — the ordering. A bounded reserve is only as good as what it spends on.
# ---------------------------------------------------------------------------


def _ev(ticker: str, category: str | None = "Sports") -> KalshiEvent:
    return KalshiEvent(
        event_ticker=ticker, title=ticker, category=category, markets=[]
    )


def test_event_series_ticker_does_not_conflate_game_with_championship():
    """`KXMLBGAME-…` also startswith `KXMLB`, which is a different series.

    `KXMLB` is the AL/NL championship future and KEEPS its nested markets; only
    `KXMLBGAME` is stripped. A `startswith` test against the series list would
    match both and silently mis-classify, so the split is load-bearing.
    """
    from app.services.kalshi_api import event_series_ticker

    assert event_series_ticker(RED_FIRST_TICKER) == "KXMLBGAME"
    assert event_series_ticker("KXMLB-26") == "KXMLB"
    assert event_series_ticker("KXMLBGAME") == "KXMLBGAME"
    assert event_series_ticker("") == ""


def test_backfill_order_puts_tonights_game_ahead_of_a_settled_one():
    """The candidate list is mostly SETTLED games going back months.

    The supplementary fetch passes `status=None`, i.e. unfiltered, so months of
    finished games arrive alongside tonight's. A settled game's markets cannot
    light up a live card, so spending a 45s reserve on May is spending it on
    nothing. Ordering is the whole behaviour of a bounded step (gotcha #41).
    """
    from app.services.kalshi_api import order_market_backfill_candidates

    stripped = {"KXMLBGAME"}
    settled_may = _ev("KXMLBGAME-26MAY311920CHCSTL")
    tonight = _ev(RED_FIRST_TICKER)
    next_week = _ev("KXMLBGAME-26SEP021940NYYBOS")

    ordered = order_market_backfill_candidates(
        [settled_may, next_week, tonight], stripped, now=NOW
    )

    assert [e.event_ticker for e in ordered] == [
        RED_FIRST_TICKER,              # tonight, soonest unplayed
        "KXMLBGAME-26SEP021940NYYBOS",  # then next week
        "KXMLBGAME-26MAY311920CHCSTL",  # the dead tail goes last, not first
    ]


def test_backfill_order_serves_the_promised_population_before_the_accident():
    """Stripped series first — they are the ones we deliberately emptied.

    Everything else in the candidate list is empty by accident of the upstream
    listing. Serving the accident before the promise is how the promise stayed
    unkept for a week.
    """
    from app.services.kalshi_api import order_market_backfill_candidates

    stripped = {"KXMLBGAME"}
    accidental = _ev("KXFEDDECISION-26AUG27")
    promised = _ev(RED_FIRST_TICKER)

    ordered = order_market_backfill_candidates(
        [accidental, promised], stripped, now=NOW
    )
    assert ordered[0].event_ticker == RED_FIRST_TICKER


def test_backfill_order_is_total_on_unparseable_tickers():
    """A fetch must never fail on a telemetry-shaped concern.

    An undated or malformed ticker sorts last within its group rather than
    raising — but still ahead of the other group, because group membership is
    the stronger signal.
    """
    from app.services.kalshi_api import order_market_backfill_candidates

    stripped = {"KXMLBGAME"}
    undated = _ev("KXMLBGAME-NONSENSE")
    dated = _ev(RED_FIRST_TICKER)
    other = _ev("KXFEDDECISION-26AUG27")

    ordered = order_market_backfill_candidates(
        [other, undated, dated], stripped, now=NOW
    )
    assert [e.event_ticker for e in ordered] == [
        RED_FIRST_TICKER,
        "KXMLBGAME-NONSENSE",
        "KXFEDDECISION-26AUG27",
    ]


def test_backfill_order_keeps_a_game_that_started_an_hour_ago():
    """The floor is yesterday, not `now` — a live game has already started.

    A hard `now` floor would sort tonight's in-progress games into the dead
    tail at exactly the moment their card is on screen, which is the moment the
    ship is about it.
    """
    from app.services.kalshi_api import order_market_backfill_candidates

    stripped = {"KXMLBGAME"}
    started = _ev("KXMLBGAME-26AUG261700DETTB")   # 17:00Z, an hour before NOW
    settled = _ev("KXMLBGAME-26MAY311920CHCSTL")  # months gone
    upcoming = _ev("KXMLBGAME-26AUG262240BOSMIA")  # 22:40Z, four hours out

    ordered = order_market_backfill_candidates(
        [settled, upcoming, started], stripped, now=NOW
    )

    # The in-progress game is above the floor and sorts by start time with the
    # rest of the live slate — it is not exiled to the dead tail at exactly the
    # moment its card is on screen.
    assert [e.event_ticker for e in ordered] == [
        "KXMLBGAME-26AUG261700DETTB",
        "KXMLBGAME-26AUG262240BOSMIA",
        "KXMLBGAME-26MAY311920CHCSTL",
    ]


def test_a_date_only_ticker_for_today_is_not_mistaken_for_a_dead_game():
    """Not every game ticker carries HHMM, and the floor has to absorb that.

    `KXMLBGAME-26AUG26BOSMIA` — the frozen red-first specimen — has no time
    component, so it parses to MIDNIGHT UTC and reads as 18 hours in the past at
    a 18:00Z reading, for a game that starts at 22:40Z. A floor of `now` would
    sort tonight's specimen into the settled tail; the one-day floor is what
    makes the date-only form safe.
    """
    from app.services.kalshi_api import order_market_backfill_candidates

    from app.utils.prediction_market_matching import extract_game_date_from_ticker

    assert extract_game_date_from_ticker(RED_FIRST_TICKER) == datetime(
        2026, 8, 26, 0, 0, tzinfo=timezone.utc
    ), "the specimen is date-only; this test is pointless if that ever changes"

    stripped = {"KXMLBGAME"}
    specimen = _ev(RED_FIRST_TICKER)
    settled = _ev("KXMLBGAME-26MAY311920CHCSTL")

    ordered = order_market_backfill_candidates(
        [settled, specimen], stripped, now=NOW
    )
    assert ordered[0].event_ticker == RED_FIRST_TICKER


# ---------------------------------------------------------------------------
# G1b — the reserve. RED-FIRST: this fails against the pre-fix function.
# ---------------------------------------------------------------------------


class _FakeClock:
    """A clock that only moves when the code under test sleeps.

    Wall-clock in a test is a clock-branching anchor (gotcha #44). Driving time
    from the awaits makes the budget arithmetic exact and the test deterministic
    regardless of how fast the machine is.
    """

    def __init__(self) -> None:
        self.t = 1000.0

    def monotonic(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.t += seconds


@pytest.mark.asyncio
async def test_market_backfill_gets_a_reserved_floor_of_the_fetch_budget(
    monkeypatch,
):
    """The empty-event market backfill runs even when earlier phases are greedy.

    RED-FIRST. Against the pre-fix code the supplementary loop runs until the
    FULL deadline, so `_past_deadline()` is true at the backfill and
    `get_markets` is never called once — `market_backfill_filled` is 0 and the
    game event goes back to the caller with `markets == []`, to be dropped by
    `if not event.markets: continue`.
    """
    import asyncio as _asyncio
    import time as _time

    clock = _FakeClock()
    monkeypatch.setattr(_time, "monotonic", clock.monotonic)
    monkeypatch.setattr(_asyncio, "sleep", clock.sleep)

    svc = KalshiAPIService()

    async def fake_get_events(
        status=None, series_ticker=None, with_nested_markets=True,
        limit=200, cursor=None, deadline=None, progress_cb=None, **kw,
    ):
        # Every page costs real budget, so the earlier phases are genuinely
        # greedy rather than politely yielding.
        clock.t += 4.0
        if series_ticker == "KXMLBGAME":
            # Fetched WITHOUT nested markets by `_HEAVY_TOKENS`, so it arrives
            # empty — exactly the production shape.
            return ([{"event_ticker": RED_FIRST_TICKER,
                      "title": "Red Sox at Marlins",
                      "category": "Sports",
                      "markets": []}], None)
        return ([], None)

    markets_calls: list[str] = []

    async def fake_get_markets(status=None, event_ticker=None, limit=200, **kw):
        markets_calls.append(event_ticker)
        return ([{"ticker": f"{event_ticker}-BOS", "yes_bid": 55, "yes_ask": 57}], None)

    monkeypatch.setattr(svc, "get_events", fake_get_events)
    monkeypatch.setattr(svc, "get_markets", fake_get_markets)

    tel: dict = {}
    events = await svc._fetch_all_events_unfiltered(
        deadline=clock.t + 240.0, telemetry=tel
    )

    assert markets_calls == [RED_FIRST_TICKER], (
        "the backfill never ran: the reserve was consumed by an earlier phase, "
        f"telemetry={tel}"
    )
    assert tel["market_backfill_skipped_past_deadline"] is False
    assert tel["market_backfill_filled"] == 1
    assert tel["market_backfill_stripped_candidates"] == 1

    by_ticker = {e.event_ticker: e for e in events}
    assert by_ticker[RED_FIRST_TICKER].markets, (
        "the game event still carries zero markets, so the upsert loop will "
        "drop it on `if not event.markets: continue` and no Kalshi row is "
        "created for tonight's game"
    )


@pytest.mark.asyncio
async def test_a_stripped_game_series_is_a_candidate_without_a_sport_category(
    monkeypatch,
):
    """The second way the promise could be broken, closed.

    These events are fetched with `with_nested_markets=False`; if Kalshi omits
    or renames `category`, the old `"sport" in category` test made the very rows
    this step exists to serve not candidates at all. The ticker is ours to
    reason about; the category is Kalshi's to change.
    """
    import asyncio as _asyncio
    import time as _time

    clock = _FakeClock()
    monkeypatch.setattr(_time, "monotonic", clock.monotonic)
    monkeypatch.setattr(_asyncio, "sleep", clock.sleep)

    svc = KalshiAPIService()

    async def fake_get_events(
        status=None, series_ticker=None, with_nested_markets=True,
        limit=200, cursor=None, deadline=None, progress_cb=None, **kw,
    ):
        clock.t += 4.0
        if series_ticker == "KXMLBGAME":
            return ([{"event_ticker": RED_FIRST_TICKER,
                      "title": "Red Sox at Marlins",
                      "category": None,          # <- the whole point
                      "markets": []}], None)
        return ([], None)

    markets_calls: list[str] = []

    async def fake_get_markets(status=None, event_ticker=None, limit=200, **kw):
        markets_calls.append(event_ticker)
        return ([{"ticker": f"{event_ticker}-BOS", "yes_bid": 55, "yes_ask": 57}], None)

    monkeypatch.setattr(svc, "get_events", fake_get_events)
    monkeypatch.setattr(svc, "get_markets", fake_get_markets)

    tel: dict = {}
    await svc._fetch_all_events_unfiltered(deadline=clock.t + 240.0, telemetry=tel)

    assert markets_calls == [RED_FIRST_TICKER]
    assert tel["market_backfill_stripped_candidates"] == 1


def test_backfill_telemetry_reaches_the_scan_report():
    """Instrumentation that does not reach the report is not instrumentation.

    These four counters were computed in `kalshi_api` and dropped on the floor —
    no caller copied them into `KalshiScanReport`. That is why the mechanism went
    a week unread while the artifact built to show it sat there answering
    `None`. A field that exists only in a local dict cannot be a gate.
    """
    from app.utils.kalshi_scan_report import KalshiScanReport

    report = KalshiScanReport(
        stop_reason="exhausted",
        events_without_markets=15951,
        market_backfill_candidates=120,
        market_backfill_stripped_candidates=15,
        market_backfill_skipped_past_deadline=False,
        market_backfill_filled=15,
    )
    data = report.to_dict()
    for key in (
        "events_without_markets",
        "market_backfill_candidates",
        "market_backfill_stripped_candidates",
        "market_backfill_skipped_past_deadline",
        "market_backfill_filled",
    ):
        assert key in data, f"{key} never reaches the report a reader loads"
    assert data["events_without_markets"] == 15951
    assert data["market_backfill_filled"] == 15


# ---------------------------------------------------------------------------
# G2 / G3 — the acceptance's must-not-regress controls.
#
# These pass before AND after. That is deliberate: they are the kill, not the
# fix. C-GAMECARD-LINK-1 blocks on any change that widens the matcher to make
# the numbers move, and the cheapest way to widen it is exactly the change these
# forbid. They fail loudly if a later hand reaches for it.
# ---------------------------------------------------------------------------


def test_g3_first_five_innings_winner_is_still_not_a_game_level_market():
    """G3 kill: `winner` must stay in `_MATCHUP_NON_GAME_KEYWORDS`.

    The 1.7% Polymarket "game link rate" in #2214 is a phantom denominator —
    it is counted over `… - First 5 Innings Winner` period markets, which
    SHOULD stay `event_id NULL`. Admitting them would cross-link
    `… Season Series Winner` futures onto a single game and feed a period
    market into a full-game blend. That is a correctness bug wearing a coverage
    win's clothes.
    """
    from app.utils.prediction_market_matching import (
        _MATCHUP_NON_GAME_KEYWORDS,
        is_game_level_market,
    )

    assert "winner" in _MATCHUP_NON_GAME_KEYWORDS
    assert "series" in _MATCHUP_NON_GAME_KEYWORDS

    assert is_game_level_market(
        "Boston Red Sox vs. Miami Marlins - First 5 Innings Winner"
    ) is False
    assert is_game_level_market(
        "Panthers vs Saints Season Series Winner"
    ) is False


def test_g2_player_props_parent_still_strips_to_a_bare_matchup():
    """G2 must-not-regress: tier-5 props link by group inheritance.

    The parent `BOS vs MIA - Player Props` links because `_strip_more_markets`
    takes it down to a bare matchup; its ~20 tier-5 children then inherit
    `event_id` by `group_id` propagation. Tier-5 is the control precisely
    because it is the half that WORKS: a fix that breaks this stripping unlinks
    twenty live props to win back one game market, which is a net loss and a
    BLOCK under the frozen acceptance.
    """
    from app.utils.prediction_market_matching import (
        _strip_more_markets,
        is_game_level_market,
    )

    assert _strip_more_markets("BOS vs MIA - Player Props").strip() == "BOS vs MIA"
    assert is_game_level_market("BOS vs MIA") is True


def test_g1_kalshi_game_ticker_is_still_recognised_as_game_level():
    """The ingested row must be matchable once it exists.

    Ingestion is this queue's fix, but ingestion into a linker that would refuse
    the ticker anyway ships nothing. `is_game_level_market` takes the Kalshi
    ticker as its most reliable signal, and tonight's specimen must satisfy it.
    """
    from app.utils.prediction_market_matching import is_game_level_market

    assert is_game_level_market(
        "Red Sox at Marlins", external_id=RED_FIRST_TICKER
    ) is True


def test_the_reserve_does_not_starve_the_rescue_it_was_carved_beside():
    """`_RESCUE_RESERVE_S` (#999) must survive `_BACKFILL_RESERVE_S` (#2214).

    #999 exists because the golf-majors rescue got zero seconds when an earlier
    phase ate the budget. Fixing #2214 by eating #999's reserve would just move
    the same bug back one stage — so the backfill's floor is carved out of the
    MAIN SCAN, whose cursor is resumable and therefore loses nothing it does not
    simply defer.
    """
    import inspect

    from app.services import kalshi_api

    src = inspect.getsource(kalshi_api.KalshiAPIService._fetch_all_events_unfiltered)
    assert "_RESCUE_RESERVE_S = 60.0" in src
    assert "_BACKFILL_RESERVE_S" in src
    # The main scan pays for both reserves; the rescue pays only for the backfill.
    assert "deadline - _RESCUE_RESERVE_S - _BACKFILL_RESERVE_S" in src
    assert "deadline - _BACKFILL_RESERVE_S if deadline is not None else None" in src
