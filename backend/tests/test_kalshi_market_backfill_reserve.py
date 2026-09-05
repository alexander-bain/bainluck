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
    tickers = [f"KXMLBGAME-26AUG26BOSMI{i:02d}" for i in range(40)]

    async def fake_get_events(
        status=None, series_ticker=None, with_nested_markets=True,
        limit=200, cursor=None, deadline=None, progress_cb=None, **kw,
    ):
        if series_ticker == "KXMLBGAME":
            return ([{"event_ticker": t, "title": t, "category": "Sports",
                      "markets": []} for t in tickers], None)
        return ([], None)

    calls: list[str] = []

    async def fake_get_markets(status=None, event_ticker=None, limit=200, **kw):
        calls.append(event_ticker)
        # Each candidate costs 3s on top of the loop's own 0.3s sleep — 40 of
        # them is 132s against an 80s budget, so the deadline lands partway
        # down the list. That is the production shape, where the list is 10,901
        # long at 0.3s of mandatory sleep each and the whole beat takes 327s.
        clock.t += 3.0
        return ([{"ticker": f"{event_ticker}-BOS", "yes_bid": 55}], None)

    monkeypatch.setattr(svc, "get_events", fake_get_events)
    monkeypatch.setattr(svc, "get_markets", fake_get_markets)

    tel: dict = {}
    await svc._fetch_all_events_unfiltered(
        deadline=clock.t + 80.0, telemetry=tel
    )

    assert tel["market_backfill_candidates"] == 40
    assert 0 < len(calls) < 40, (
        "precondition: the deadline must cut the loop off PARTWAY, otherwise "
        f"this test proves nothing. attempted={len(calls)}"
    )
    assert tel["market_backfill_skipped_past_deadline"] is False, (
        "precondition: the step DID start — this is the case the existing "
        "field cannot describe, and the reason a reader saw headroom"
    )
    assert tel["market_backfill_truncated_after"] == len(calls), (
        "the beat must say how many candidates it got through before the "
        "deadline; without it a starved backfill is indistinguishable from a "
        "finished one"
    )


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
            return ([{"event_ticker": RED_FIRST_TICKER,
                      "title": "Red Sox at Marlins",
                      "category": "Sports", "markets": []}], None)
        return ([], None)

    async def fake_get_markets(status=None, event_ticker=None, limit=200, **kw):
        return ([{"ticker": f"{event_ticker}-BOS", "yes_bid": 55}], None)

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
        "Red Sox at Marlins", external_id=RED_FIRST_TICKER
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
