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


def _live_ticker(suffix: str = "BOSMIA", series: str = "KXMLBGAME") -> str:
    """A ticker for yesterday's game, built from the real clock.

    #3190 gave the backfill a retention floor, and the floor reads the date the
    ticker embeds against ``datetime.now``. So a hard-coded date in a
    SERVICE-level fixture is a time bomb: `KXMLBGAME-26AUG26…` is a live
    candidate today and a provably-purged one from 2026-11-20, at which point
    nine tests that have nothing to do with retention start failing for a reason
    none of them mentions.

    Offset FIRST, then format (gotcha #44) — no branch on the clock. Yesterday
    rather than today so the ordering treats it as a real played game.

    The PURE-function ordering tests keep :data:`RED_FIRST_TICKER` and its frozen
    :data:`NOW`: they pass their own clock in, so nothing about them rots.
    """
    d = datetime.now(timezone.utc) - timedelta(days=1)
    return f"{series}-{d:%y%b%d}".upper() + suffix


#: The stripped-series candidate the service-level tests below backfill.
LIVE_TICKER = _live_ticker()


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


def _venue_markets(event_tickers) -> list[dict]:
    """Markets shaped the way the venue actually returns them (#3149).

    `GET /markets?series_ticker=…` answers for EVERY event of the series and
    each market carries its own `event_ticker`. Verified directly against
    `api.elections.kalshi.com` on 2026-09-05: `KXMLBGAME` with no status filter
    is 1,826 markets over 2 pages, spanning every event of the series.

    The fakes these replace keyed off the `event_ticker` REQUEST parameter and
    echoed it back, which could not distinguish "the venue answered for this
    event" from "we asked about it" — precisely the confusion a batched fetch
    has to be guarded against.
    """
    return [
        {"ticker": f"{t}-BOS", "event_ticker": t, "yes_bid": 55, "yes_ask": 57}
        for t in event_tickers
    ]


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
            return ([{"event_ticker": LIVE_TICKER,
                      "title": "Red Sox at Marlins",
                      "category": "Sports",
                      "markets": []}], None)
        return ([], None)

    markets_calls: list[str] = []

    async def fake_get_markets(
        status=None, event_ticker=None, series_ticker=None, limit=200, **kw
    ):
        markets_calls.append(series_ticker)
        return (_venue_markets([LIVE_TICKER]), None)

    monkeypatch.setattr(svc, "get_events", fake_get_events)
    monkeypatch.setattr(svc, "get_markets", fake_get_markets)

    tel: dict = {}
    events = await svc._fetch_all_events_unfiltered(
        deadline=clock.t + 240.0, telemetry=tel
    )

    assert markets_calls == ["KXMLBGAME"], (
        "the backfill never ran: the reserve was consumed by an earlier phase, "
        f"telemetry={tel}"
    )
    assert tel["market_backfill_skipped_past_deadline"] is False
    assert tel["market_backfill_filled"] == 1
    assert tel["market_backfill_stripped_candidates"] == 1

    by_ticker = {e.event_ticker: e for e in events}
    assert by_ticker[LIVE_TICKER].markets, (
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
            return ([{"event_ticker": LIVE_TICKER,
                      "title": "Red Sox at Marlins",
                      "category": None,          # <- the whole point
                      "markets": []}], None)
        return ([], None)

    markets_calls: list[str] = []

    async def fake_get_markets(
        status=None, event_ticker=None, series_ticker=None, limit=200, **kw
    ):
        markets_calls.append(series_ticker)
        return (_venue_markets([LIVE_TICKER]), None)

    monkeypatch.setattr(svc, "get_events", fake_get_events)
    monkeypatch.setattr(svc, "get_markets", fake_get_markets)

    tel: dict = {}
    await svc._fetch_all_events_unfiltered(deadline=clock.t + 240.0, telemetry=tel)

    assert markets_calls == ["KXMLBGAME"]
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
# The cut the report could not describe (lane1b/041, #2927 sizing).
#
# `market_backfill_skipped_past_deadline` covers ONE deadline case: the step
# never started. The loop's own mid-flight `break` wrote nothing, so a backfill
# terminated by the deadline every beat reported False — which reads as "the
# reserved floor is holding", i.e. as headroom.
#
# Production, the 24-beat ring read 2026-09-05 07:00Z:
#   candidates 6,968 -> 10,901 over 46h while `filled` stayed flat at 367-496.
#   corr(filled, candidates) = -0.869. Supply FALLING as demand rises is the
#   signature of a time-bound step, and 10,901 candidates at the loop's
#   mandatory 0.3s pre-request sleep is 3,270s of sleep inside beats that
#   finish in 327s — it cannot have reached the end of the list on any of them.
#   `skipped_past_deadline` was False on all 24.
#
# That is the number that decides whether a new heavy series class can be
# admitted at all, so it has to be legible from the artifact.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_backfill_the_deadline_cuts_off_says_where_it_stopped(
    monkeypatch,
):
    """RED-FIRST. Pre-fix, the only deadline field a reader can see stays False
    and nothing anywhere records that most of the list was never attempted."""
    import asyncio as _asyncio
    import time as _time

    clock = _FakeClock()
    monkeypatch.setattr(_time, "monotonic", clock.monotonic)
    monkeypatch.setattr(_asyncio, "sleep", clock.sleep)

    svc = KalshiAPIService()
    # Eight series of five events each. #3149 batches by series, so the cut now
    # lands on a series boundary — the list position it reports must still be
    # the CANDIDATE count, because that is the number of events left with no
    # markets, and that is what a reader is trying to learn.
    series = [f"KXMLBGAME{s}" for s in range(8)]
    tickers = [_live_ticker(f"BOSMI{i:02d}", series=s) for s in series for i in range(5)]

    async def fake_get_events(
        status=None, series_ticker=None, with_nested_markets=True,
        limit=200, cursor=None, deadline=None, progress_cb=None, **kw,
    ):
        if series_ticker == "KXMLBGAME":
            return ([{"event_ticker": t, "title": t, "category": "Sports",
                      "markets": []} for t in tickers], None)
        return ([], None)

    calls: list[str] = []

    async def fake_get_markets(
        status=None, event_ticker=None, series_ticker=None, limit=200, **kw
    ):
        calls.append(series_ticker)
        # Each SERIES request costs 20s on top of the loop's 0.3s sleep — eight
        # of them is 162s against an 80s budget, so the deadline lands partway
        # down the list, which is the production shape at a smaller scale.
        clock.t += 20.0
        return (
            _venue_markets([t for t in tickers if t.startswith(f"{series_ticker}-")]),
            None,
        )

    monkeypatch.setattr(svc, "get_events", fake_get_events)
    monkeypatch.setattr(svc, "get_markets", fake_get_markets)

    tel: dict = {}
    await svc._fetch_all_events_unfiltered(
        deadline=clock.t + 80.0, telemetry=tel
    )

    assert tel["market_backfill_candidates"] == 40
    assert 0 < len(calls) < 8, (
        "precondition: the deadline must cut the loop off PARTWAY, otherwise "
        f"this test proves nothing. series attempted={len(calls)}"
    )
    assert tel["market_backfill_skipped_past_deadline"] is False, (
        "precondition: the step DID start — this is the case the existing "
        "field cannot describe, and the reason a reader saw headroom"
    )
    assert tel["market_backfill_truncated_after"] == len(calls) * 5, (
        "the beat must say how many CANDIDATES it got through before the "
        "deadline; without it a starved backfill is indistinguishable from a "
        "finished one. Batching by series must not turn the cutoff into a "
        "count of requests — 5 requests is 25 events served, not 5"
    )
    assert tel["market_backfill_filled"] == len(calls) * 5


@pytest.mark.asyncio
async def test_a_backfill_that_finishes_the_list_reports_no_cut(monkeypatch):
    """The other half, and the reason the field is nullable rather than an int.

    `or 0` on the carry would render the healthiest possible beat as "cut off
    at candidate zero" — the loudest reading of the quietest fact.
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
        if series_ticker == "KXMLBGAME":
            return ([{"event_ticker": LIVE_TICKER,
                      "title": "Red Sox at Marlins",
                      "category": "Sports", "markets": []}], None)
        return ([], None)

    async def fake_get_markets(
        status=None, event_ticker=None, series_ticker=None, limit=200, **kw
    ):
        return (_venue_markets([LIVE_TICKER]), None)

    monkeypatch.setattr(svc, "get_events", fake_get_events)
    monkeypatch.setattr(svc, "get_markets", fake_get_markets)

    tel: dict = {}
    await svc._fetch_all_events_unfiltered(
        deadline=clock.t + 240.0, telemetry=tel
    )

    assert tel["market_backfill_filled"] == 1
    assert tel["market_backfill_truncated_after"] is None, (
        "a completed backfill must not report a cut"
    )


def test_the_cut_is_carried_into_the_report_and_survives_json():
    """The carry is the step this block was omitted from twice (#2214, #2927).

    A field that exists only in `kalshi_api`'s local telemetry dict is not
    instrumentation — it is the same defect wearing a third hat.
    """
    import ast
    import json
    from pathlib import Path

    from app.utils.kalshi_scan_report import KalshiScanReport

    data = KalshiScanReport(market_backfill_truncated_after=386).to_dict()
    assert data["market_backfill_truncated_after"] == 386
    assert json.loads(json.dumps(data))["market_backfill_truncated_after"] == 386
    assert KalshiScanReport().to_dict()["market_backfill_truncated_after"] is None

    # The call site, parsed rather than grepped: both fields above were correct
    # in isolation and unreachable in production because the one call joining
    # them omitted the keyword.
    src = (Path(__file__).resolve().parents[1]
           / "app" / "tasks" / "kalshi.py").read_text()
    constructions = [
        node for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "KalshiScanReport"
    ]
    assert constructions, "poll_kalshi no longer builds a KalshiScanReport"
    for call in constructions:
        kwargs = {kw.arg for kw in call.keywords if kw.arg}
        assert "market_backfill_truncated_after" in kwargs, (
            "the beat measures the cut and drops it on the floor — #2214 and "
            "#2927 verbatim, for the third time"
        )

        # And it must carry None THROUGH. Every sibling field on this call is
        # coerced with `int(... or 0)`, which is right for a count and wrong
        # here: it renders "worked the whole list" as "cut off at candidate
        # zero", the loudest reading of the healthiest beat. A mutation to the
        # `or 0` shape passes every other assertion in this file, so the guard
        # is on the call site's shape — the value expression has to mention
        # `None` somewhere, which `int(x or 0)` cannot.
        value = next(
            kw.value for kw in call.keywords
            if kw.arg == "market_backfill_truncated_after"
        )
        assert any(
            isinstance(node, ast.Constant) and node.value is None
            for node in ast.walk(value)
        ), (
            "the carry coerces the cut to an int, so a beat that finished its "
            "list reports being cut off at candidate 0"
        )


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
        "Red Sox at Marlins", external_id=LIVE_TICKER
    ) is True


def test_the_reserve_does_not_starve_the_rescue_it_was_carved_beside():
    """`_RESCUE_RESERVE_S` (#999) must survive `_BACKFILL_RESERVE_S` (#2214).

    #999 exists because the golf-majors rescue got zero seconds when an earlier
    phase ate the budget. Fixing #2214 by eating #999's reserve would just move
    the same bug back one stage — so the backfill's floor is carved out of the
    MAIN SCAN, whose cursor is resumable and therefore loses nothing it does not
    simply defer.

    lane1b/024 added a THIRD consumer of this same carve — discovered series —
    and moved the arithmetic out of the method body into
    `kalshi_series_selection.fetch_stage_deadlines`, precisely because two
    incidents in a row turned on getting it wrong inline. This test used to pin
    the arithmetic as a source substring; it now asserts the arithmetic itself,
    which is what the substring was standing in for and is strictly stronger.
    """
    import inspect

    from app.services import kalshi_api
    from app.utils.kalshi_series_selection import fetch_stage_deadlines

    src = inspect.getsource(kalshi_api.KalshiAPIService._fetch_all_events_unfiltered)
    assert "_RESCUE_RESERVE_S = 60.0" in src
    assert "_BACKFILL_RESERVE_S" in src

    rescue, backfill = 60.0, 45.0
    # With nothing discovered, the split is the two-reserve one #999 and #2214
    # settled between them, unchanged.
    d = fetch_stage_deadlines(
        1000.0, has_discovered=False,
        rescue_reserve_s=rescue, discovery_reserve_s=25.0,
        backfill_reserve_s=backfill,
    )
    # The main scan pays for both reserves...
    assert 1000.0 - d.main_scan == pytest.approx(rescue + backfill)
    # ...and the rescue pays only for the backfill.
    assert 1000.0 - d.guaranteed == pytest.approx(backfill)
    # The rescue's own floor is intact: it is not carved out of #999's reserve.
    assert d.guaranteed - d.main_scan == pytest.approx(rescue)


# ---------------------------------------------------------------------------
# #3149 — the cost per candidate is the bug.
#
# The backfill asked the venue once per EVENT, with a mandatory 0.3s sleep in
# front of each request. Against the 10,901-candidate list of 2026-09-05 that
# is 3,270s of sleep alone, inside beats that finish in 327s. `filled` sat at
# 367-496 while candidates climbed past 10,000 — corr(filled, candidates) =
# -0.869, supply falling as demand rose, the signature of a time-bound step.
# No reserve can fix a per-item cost larger than the whole beat.
#
# `GET /markets?series_ticker=…` answers for every event of a series at once.
# Measured against the live venue 2026-09-05: KXMLBGAME with no status filter
# is 1,826 markets over 2 pages in 1.0s — the whole MLB game series for the
# price the old loop paid for three events.
# ---------------------------------------------------------------------------


def _one_series_service(monkeypatch, tickers, *, categories=None):
    """A service whose supplementary fetch hands back `tickers`, all empty."""
    import asyncio as _asyncio
    import time as _time

    clock = _FakeClock()
    monkeypatch.setattr(_time, "monotonic", clock.monotonic)
    monkeypatch.setattr(_asyncio, "sleep", clock.sleep)

    svc = KalshiAPIService()
    cats = categories or {}

    async def fake_get_events(
        status=None, series_ticker=None, with_nested_markets=True,
        limit=200, cursor=None, deadline=None, progress_cb=None, **kw,
    ):
        if series_ticker == "KXMLBGAME":
            return ([{"event_ticker": t, "title": t,
                      "category": cats.get(t, "Sports"), "markets": []}
                     for t in tickers], None)
        return ([], None)

    monkeypatch.setattr(svc, "get_events", fake_get_events)
    return svc, clock


@pytest.mark.asyncio
async def test_the_backfill_asks_once_per_series_not_once_per_event(monkeypatch):
    """THE SHIP. Thirty events of one series cost one request, not thirty.

    RED-FIRST against the per-event loop, which made thirty calls and paid
    thirty 0.3s sleeps for the same markets.
    """
    tickers = [_live_ticker(f"BOSMI{i:02d}") for i in range(30)]
    svc, clock = _one_series_service(monkeypatch, tickers)

    calls: list[str] = []

    async def fake_get_markets(
        status=None, event_ticker=None, series_ticker=None, limit=200, **kw
    ):
        calls.append(series_ticker)
        assert event_ticker is None, (
            "the batched path must ask by series; an event_ticker here means "
            "it silently went back to one request per candidate"
        )
        return (_venue_markets(tickers), None)

    monkeypatch.setattr(svc, "get_markets", fake_get_markets)

    tel: dict = {}
    events = await svc._fetch_all_events_unfiltered(
        deadline=clock.t + 240.0, telemetry=tel
    )

    assert calls == ["KXMLBGAME"], f"{len(calls)} requests for one series"
    assert tel["market_backfill_candidates"] == 30
    assert tel["market_backfill_filled"] == 30, (
        "every event of the series must come back with markets — a batch that "
        "serves one event is not cheaper, it is broken"
    )
    assert tel["market_backfill_requests"] == 1
    assert tel["market_backfill_series_worked"] == 1
    assert tel["market_backfill_unmatched"] == 0
    assert tel["market_backfill_truncated_after"] is None
    filled = [e for e in events if e.markets]
    assert len(filled) == 30


@pytest.mark.asyncio
async def test_a_candidate_the_series_did_not_answer_for_is_counted(monkeypatch):
    """The per-item outage batching could introduce and the old loop could not.

    An aggregate `filled` cannot tell a batch that served 9 of 10 events from
    one that was only ever asked about 9. So the miss is counted by name.
    """
    tickers = [_live_ticker(f"BOSMI{i:02d}") for i in range(10)]
    svc, clock = _one_series_service(monkeypatch, tickers)

    async def fake_get_markets(
        status=None, event_ticker=None, series_ticker=None, limit=200, **kw
    ):
        # The venue answers for nine of the ten. Nothing errors.
        return (_venue_markets(tickers[:9]), None)

    monkeypatch.setattr(svc, "get_markets", fake_get_markets)

    tel: dict = {}
    events = await svc._fetch_all_events_unfiltered(
        deadline=clock.t + 240.0, telemetry=tel
    )

    assert tel["market_backfill_filled"] == 9
    assert tel["market_backfill_unmatched"] == 1, (
        "the tenth event went back to the caller with zero markets and will be "
        "dropped by `if not event.markets: continue`; a beat that cannot say so "
        "reads as a clean batch"
    )
    by_ticker = {e.event_ticker: e for e in events}
    assert not by_ticker[tickers[9]].markets


@pytest.mark.asyncio
async def test_pagination_stops_once_every_candidate_is_served(monkeypatch):
    """A series' history is somebody else's; we stop when our events are served.

    KXMLBGAME carries 1,826 markets across every status at the venue. Walking
    all of it to serve tonight's slate would hand back the per-event problem in
    a new currency.
    """
    tickers = [_live_ticker(f"BOSMI{i:02d}") for i in range(4)]
    svc, clock = _one_series_service(monkeypatch, tickers)

    pages: list[str] = []

    async def fake_get_markets(
        status=None, event_ticker=None, series_ticker=None, limit=200,
        cursor=None, **kw
    ):
        pages.append(cursor or "first")
        # Every candidate is served by page one, and the venue offers more.
        return (_venue_markets(tickers), "there-is-more")

    monkeypatch.setattr(svc, "get_markets", fake_get_markets)

    tel: dict = {}
    await svc._fetch_all_events_unfiltered(deadline=clock.t + 240.0, telemetry=tel)

    assert pages == ["first"], f"walked {len(pages)} pages to serve 4 events"
    assert tel["market_backfill_filled"] == 4


@pytest.mark.asyncio
async def test_a_series_the_venue_paginates_is_walked_until_our_events_appear(
    monkeypatch,
):
    """The other direction: stopping early must not mean stopping too early."""
    tickers = [_live_ticker(f"BOSMI{i:02d}") for i in range(3)]
    svc, clock = _one_series_service(monkeypatch, tickers)

    async def fake_get_markets(
        status=None, event_ticker=None, series_ticker=None, limit=200,
        cursor=None, **kw
    ):
        if cursor is None:
            # Page one is the series' settled history — none of ours.
            return (_venue_markets(["KXMLBGAME-25JUL04OLDOLD"]), "page2")
        return (_venue_markets(tickers), None)

    monkeypatch.setattr(svc, "get_markets", fake_get_markets)

    tel: dict = {}
    await svc._fetch_all_events_unfiltered(deadline=clock.t + 240.0, telemetry=tel)

    assert tel["market_backfill_filled"] == 3
    assert tel["market_backfill_requests"] == 2


@pytest.mark.asyncio
async def test_grouping_keeps_the_stripped_series_at_the_front(monkeypatch):
    """Batching must not undo `order_market_backfill_candidates` (gotcha #41).

    Groups are keyed in first-appearance order over the ORDERED candidate list,
    so a cut still lands on the accidental tail rather than on the game series
    the backfill exists to serve.
    """
    accidental = [_live_ticker(f"X{i:02d}", series="KXFAKEFUTURES") for i in range(3)]
    promised = [_live_ticker(f"BOSMI{i:02d}") for i in range(3)]
    # Deliberately fetched accidental-first, so only the ordering can save it.
    svc, clock = _one_series_service(monkeypatch, accidental + promised)

    calls: list[str] = []

    async def fake_get_markets(
        status=None, event_ticker=None, series_ticker=None, limit=200, **kw
    ):
        calls.append(series_ticker)
        clock.t += 60.0  # one series is all the budget allows
        return (_venue_markets(promised + accidental), None)

    monkeypatch.setattr(svc, "get_markets", fake_get_markets)

    tel: dict = {}
    await svc._fetch_all_events_unfiltered(deadline=clock.t + 70.0, telemetry=tel)

    assert tel["market_backfill_candidates"] == 6
    assert calls[0] == "KXMLBGAME", (
        "the series `_HEAVY_TOKENS` deliberately emptied must be served before "
        f"the ones empty by accident; asked {calls}"
    )
    assert tel["market_backfill_truncated_after"] == 3


def test_the_batched_counters_reach_the_scan_report():
    """The omission this module records three times over, not repeated a fourth.

    `market_backfill_requests` is the one that tells a future reader whether the
    backfill is still cheap: a beat where requests ≈ candidates has quietly gone
    back to asking per event, and no other field would show it.
    """
    import ast
    from pathlib import Path

    from app.utils.kalshi_scan_report import KalshiScanReport

    data = KalshiScanReport(
        market_backfill_series_worked=42,
        market_backfill_requests=57,
        market_backfill_unmatched=3,
    ).to_dict()
    for key in (
        "market_backfill_series_worked",
        "market_backfill_requests",
        "market_backfill_unmatched",
    ):
        assert key in data, f"{key} never reaches the report a reader loads"
    assert data["market_backfill_requests"] == 57

    # And the task actually copies them across — a dataclass field nobody
    # populates is the same defect wearing a fourth hat.
    src = Path(__file__).resolve().parents[1] / "app" / "tasks" / "kalshi.py"
    tree = ast.parse(src.read_text())
    passed = {
        kw.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "KalshiScanReport"
        for kw in node.keywords
    }
    for key in (
        "market_backfill_series_worked",
        "market_backfill_requests",
        "market_backfill_unmatched",
    ):
        assert key in passed, f"{key} is computed and never carried to the report"


# ---------------------------------------------------------------------------
# #3190 — THE RETENTION FLOOR.
#
# The invariant these guard: **a candidate past Kalshi's market-retention bound
# is not requested.** Named after that, not after the queue that shipped it.
#
# Kalshi EVENT data is permanent; MARKET data is purged (gotcha #35). So the
# supplementary listing hands back years of finished games with zero nested
# markets, forever. Measured on the 2026-09-05 10:45Z beat: 11,538 candidates,
# 7,722 unmatched — two thirds of every beat's request budget spent on rows the
# venue has nothing left to answer with.
#
# Checked against the venue, not against a fixture (2026-09-05, Kalshi's own
# API, six game series — KXMLBGAME, KXMLBSPREAD, KXMLBTOTAL, KXNBAGAME,
# KXNHLGAME, KXNFLGAME):
#
#     events listed              12,161
#     events still with markets   2,773   oldest 68.5 days
#     events with no markets      9,388   youngest 69.5 days
#     with markets at >= 86d          0
#
# A sharp cliff at ~69 days, and `PROVABLY_PURGED_AGE_DAYS` (86) sits 17 days
# clear of it on the safe side. Nothing here writes a day count: the module owns
# the number and these tests derive their fixtures from it, so re-measuring the
# venue moves the constant and the tests together.
# ---------------------------------------------------------------------------


def _aged_ticker(
    days_ago: float, suffix: str = "BOSMIA", series: str = "KXMLBGAME"
) -> str:
    """A game ticker whose embedded date is `days_ago` days old.

    Offset FIRST, then format (gotcha #44). The offsets callers pass are derived
    from `PROVABLY_PURGED_AGE_DAYS`, never typed.
    """
    d = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return f"{series}-{d:%y%b%d}".upper() + suffix


def test_a_candidate_past_the_retention_bound_is_not_requested():
    """THE INVARIANT. The venue cannot answer for it, so we do not ask.

    RED-FIRST: before the floor existed every one of these went into the
    request list, came back `unmatched`, and would have again on every beat
    until the heat death of the series.
    """
    from app.services.kalshi_api import drop_provably_purged_candidates
    from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

    dead = [
        _ev(_aged_ticker(PROVABLY_PURGED_AGE_DAYS, "AAABBB")),
        _ev(_aged_ticker(PROVABLY_PURGED_AGE_DAYS + 200, "CCCDDD")),
        _ev(_aged_ticker(PROVABLY_PURGED_AGE_DAYS + 1, "EEEFFF")),
    ]

    live, cut = drop_provably_purged_candidates(dead, {"KXMLBGAME"})

    assert live == [], (
        "a candidate whose markets Kalshi has provably purged was still going "
        "to be asked for; it can only ever come back unmatched"
    )
    assert len(cut) == 3


def test_a_candidate_inside_the_retention_bound_is_still_requested():
    """The other direction, which is the one that would be a regression.

    A floor that also cuts fillable rows is not relief, it is an outage wearing
    a smaller number. This includes the UNCERTAIN band: retention was measured
    at >=74 and <86 days, and the skip-work bound is deliberately the UPPER one
    so a row in the band is still tried. Fail-open is the whole design.
    """
    from app.services.kalshi_api import drop_provably_purged_candidates
    from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

    tonight = _ev(_aged_ticker(-1, "AAABBB"))
    yesterday = _ev(_aged_ticker(1, "CCCDDD"))
    # Inside the 74-86d band the venue's answer is genuinely unknown.
    uncertain = _ev(_aged_ticker(PROVABLY_PURGED_AGE_DAYS - 1, "EEEFFF"))

    live, cut = drop_provably_purged_candidates(
        [tonight, yesterday, uncertain], {"KXMLBGAME"}
    )

    assert cut == [], f"the floor cut a row that may still be fillable: {cut}"
    assert [e.event_ticker for e in live] == [
        tonight.event_ticker, yesterday.event_ticker, uncertain.event_ticker,
    ]


def test_an_undated_candidate_is_never_written_off():
    """Ignorance is not evidence of purging.

    `is_provably_purged(None)` is False by design — an unknown settlement time
    is still attempted rather than abandoned. A floor that inverted that would
    silently drop every series whose ticker shape we cannot parse, which is
    exactly the classes (college, esports, tennis) that have no other net.
    """
    from app.services.kalshi_api import drop_provably_purged_candidates

    undated = _ev("KXMLBGAME-NONSENSE")
    empty = _ev("")

    live, cut = drop_provably_purged_candidates(
        [undated, empty], {"KXMLBGAME"}
    )

    assert cut == []
    assert len(live) == 2


def test_the_floor_leaves_the_ordering_of_what_survives_alone():
    """Both bounds, not one (gotcha #41).

    The floor is the FLOOR. It must not become the ordering: a cut that also
    reshuffled would hand back the starvation the ordering exists to prevent —
    stripped series before accidental ones, soonest-unplayed before the tail.
    """
    from app.services.kalshi_api import (
        drop_provably_purged_candidates,
        order_market_backfill_candidates,
    )
    from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

    stripped = {"KXMLBGAME"}
    tonight = _ev(_aged_ticker(-1, "AAABBB"))
    accidental = _ev(_aged_ticker(-1, "X01", series="KXFEDDECISION"))
    recent_past = _ev(_aged_ticker(3, "CCCDDD"))
    ancient = _ev(_aged_ticker(PROVABLY_PURGED_AGE_DAYS + 30, "EEEFFF"))

    live, cut = drop_provably_purged_candidates(
        [ancient, accidental, recent_past, tonight], stripped
    )
    ordered = order_market_backfill_candidates(live, stripped)

    assert [e.event_ticker for e in cut] == [ancient.event_ticker]
    assert [e.event_ticker for e in ordered] == [
        tonight.event_ticker,      # the promise, soonest unplayed
        recent_past.event_ticker,  # then the most recent past, not the oldest
        accidental.event_ticker,   # the accident goes behind the promise
    ]


@pytest.mark.asyncio
async def test_a_dead_tail_costs_no_request_and_the_live_slate_still_fills(
    monkeypatch,
):
    """THE SHIP, end to end: fewer asks, the same fills.

    RED-FIRST against the pre-floor code, which grouped the purged series into
    `_groups` and spent a request and a page walk on it before serving nobody.

    `filled` not falling is the half that makes this relief rather than a
    regression — it is asserted here and not inferred from the request count.
    """
    live_tickers = [_aged_ticker(1, f"BOSMI{i:02d}") for i in range(4)]
    from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

    dead_tickers = [
        _aged_ticker(PROVABLY_PURGED_AGE_DAYS + 10, f"OLD{i:02d}",
                     series="KXNBAGAME")
        for i in range(6)
    ]
    svc, clock = _one_series_service(monkeypatch, live_tickers + dead_tickers)

    calls: list[str] = []

    async def fake_get_markets(
        status=None, event_ticker=None, series_ticker=None, limit=200, **kw
    ):
        calls.append(series_ticker)
        # The venue answers for the live series only. For the purged one it
        # returns the empty list it really returns — an event that still exists
        # with no markets left (gotcha #53: an empty 200 is a response shape).
        if series_ticker == "KXMLBGAME":
            return (_venue_markets(live_tickers), None)
        return ([], None)

    monkeypatch.setattr(svc, "get_markets", fake_get_markets)

    tel: dict = {}
    events = await svc._fetch_all_events_unfiltered(
        deadline=clock.t + 240.0, telemetry=tel
    )

    assert calls == ["KXMLBGAME"], (
        "the purged series was still asked for; that request and its page walk "
        f"can only ever come back empty. asked={calls}"
    )
    assert tel["market_backfill_candidates"] == 4
    assert tel["market_backfill_dead_candidates"] == 6
    assert tel["market_backfill_filled"] == 4, (
        "the live slate must still fill — a floor that costs a fill is an "
        "outage wearing a smaller candidate count"
    )
    assert tel["market_backfill_unmatched"] == 0, (
        "the 7,722 permanently-unanswerable rows are gone from the ask, so "
        "they are gone from the miss count too"
    )
    # The dead events are still handed back to the caller untouched; the floor
    # decides what to REQUEST, never what exists.
    assert len(events) == 10
    assert not any(e.markets for e in events
                   if e.event_ticker in set(dead_tickers))


def test_the_dead_cut_reaches_the_scan_report():
    """A cut nobody can read is a candidate count that fell for no stated reason.

    Two thirds of the list disappears the beat this deploys. From
    `market_backfill_candidates` alone that is indistinguishable from the
    supplementary fetch going dark, and one of those two is a P1.
    """
    import ast
    from pathlib import Path

    from app.utils.kalshi_scan_report import KalshiScanReport

    data = KalshiScanReport(
        market_backfill_candidates=3816,
        market_backfill_dead_candidates=7722,
    ).to_dict()
    assert data["market_backfill_dead_candidates"] == 7722

    src = Path(__file__).resolve().parents[1] / "app" / "tasks" / "kalshi.py"
    tree = ast.parse(src.read_text())
    passed = {
        kw.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "KalshiScanReport"
        for kw in node.keywords
    }
    assert "market_backfill_dead_candidates" in passed, (
        "the cut is computed in the fetch and never carried to the report — "
        "the same omission this module already records four times"
    )


def test_a_futures_expiry_ticker_is_never_read_as_a_25_year_old_game():
    """The specimen that bounded the cut, kept as a specimen.

    Kalshi writes a GAME ticker as `<SERIES>-YYMMMDD[HHMM]<TEAMS>` and a FUTURES
    ticker as `<SERIES>-DDMMMYY` with nothing after it. Same seven characters,
    and `extract_game_date_from_ticker` reads both as the first:

        KXHONEYDEUCE-01JAN27  ->  2001-01-02
        KXATPADVANCE-15MAR27  ->  2015-03-02

    Both are LIVE 2027-expiry futures in series #2927's discovery had only just
    started ingesting, and both are `is_provably_purged` under the naive read. A
    floor that trusted the parser everywhere would have cut them — shipping an
    outage inside a change whose whole claim is that it takes nothing away.

    So the cut is bounded to STRIPPED GAME series, which always carry the team
    suffix and are where the 7,722 lives anyway. The parser ambiguity itself is
    the matcher's (D39/D35): filed against #2693, not fixed here.
    """
    from app.services.kalshi_api import drop_provably_purged_candidates
    from app.utils.kalshi_retention import is_provably_purged
    from app.utils.prediction_market_matching import (
        extract_game_date_from_ticker,
    )

    honey = "KXHONEYDEUCE-01JAN27"
    advance = "KXATPADVANCE-15MAR27"

    # The trap is real, not hypothetical — assert it, so this test still means
    # something on the day somebody fixes the parser.
    assert is_provably_purged(extract_game_date_from_ticker(honey)), (
        "the specimen no longer misparses; re-derive the bound below rather "
        "than deleting this test"
    )

    live, cut = drop_provably_purged_candidates(
        [_ev(honey), _ev(advance)], {"KXMLBGAME", "KXNBAGAME"}
    )

    assert cut == [], (
        "a live 2027-expiry future was cut as a purged 2001 market; the floor "
        "must only read a date it knows the shape of"
    )
    assert len(live) == 2


def test_the_floor_only_cuts_the_population_it_was_measured_on():
    """Same bound, stated as the invariant rather than through one specimen.

    The venue table behind this floor covers stripped game series. A candidate
    of any other series keeps its request no matter how old its ticker reads —
    that is the difference between a measured cut and a guess applied widely.
    """
    from app.services.kalshi_api import drop_provably_purged_candidates
    from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

    ancient = PROVABLY_PURGED_AGE_DAYS + 400
    measured = _ev(_aged_ticker(ancient, "BOSMIA", series="KXMLBGAME"))
    unmeasured = _ev(_aged_ticker(ancient, "FONSZA", series="KXITFMATCH"))

    live, cut = drop_provably_purged_candidates(
        [measured, unmeasured], {"KXMLBGAME"}
    )

    assert [e.event_ticker for e in cut] == [measured.event_ticker]
    assert [e.event_ticker for e in live] == [unmeasured.event_ticker]


def test_the_production_filter_cuts_the_old_game_and_keeps_the_live_future():
    """CERT-1889's named repair, against the REAL production filter.

    The BLOCK asked for exactly this pairing: "an old measured game with a live
    future-shaped non-stripped ticker", run through the set the service actually
    computes rather than a set the test invents. A hand-made `{"KXMLBGAME"}`
    cannot fail the way production fails — it cannot tell whether
    `_stripped_series` itself admits the wrong series.

    The two counter-specimens behind it, both re-measured at the venue
    2026-09-05:

    * `KXHONEYDEUCE-01JAN27` — a LIVE 2027-expiry future with active markets,
      which the game parser reads as `2001-01-02`, i.e. provably purged.
    * `KXATPMATCH` — 3 of 933 events at **244.5-245.5 days** still carry
      retrievable markets, one quoting `last_price_dollars 0.3100`. Inside the
      stripped set nothing survives past 86 days; outside it, things do. The
      premise is a property of the population, not of Kalshi.
    """
    from app.services.kalshi_api import (
        _HEAVY_TOKENS,
        _SPORTS_SERIES_TICKERS,
        drop_provably_purged_candidates,
    )
    from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

    # The production filter, derived exactly as `_fetch_all_events_unfiltered`
    # derives it — so a change to either constant reaches this test.
    stripped = {
        st.upper()
        for st in _SPORTS_SERIES_TICKERS
        if any(tok in st.upper() for tok in _HEAVY_TOKENS)
    }
    assert "KXMLBGAME" in stripped and "KXATPMATCH" not in stripped, (
        "the production filter no longer describes the measured population; "
        "re-measure the venue before trusting the cut"
    )

    old_measured_game = _ev(
        _aged_ticker(PROVABLY_PURGED_AGE_DAYS + 120, "BOSMIA",
                     series="KXMLBGAME")
    )
    live_future = _ev("KXHONEYDEUCE-01JAN27")
    # The 245-day ATP survivor, in the shape the venue actually returns it.
    old_unmeasured_but_alive = _ev(
        _aged_ticker(245, "ALCSIN", series="KXATPMATCH")
    )

    live, cut = drop_provably_purged_candidates(
        [old_measured_game, live_future, old_unmeasured_but_alive], stripped
    )

    assert [e.event_ticker for e in cut] == [old_measured_game.event_ticker], (
        "the cut must land on the measured population and nowhere else; "
        f"cut={[e.event_ticker for e in cut]}"
    )
    assert [e.event_ticker for e in live] == [
        live_future.event_ticker,
        old_unmeasured_but_alive.event_ticker,
    ]
