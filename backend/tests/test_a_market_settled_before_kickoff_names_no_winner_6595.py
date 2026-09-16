"""#6595 — a game that has not been played stops naming a winner.

## What a reader saw

Production, phone width, 2026-09-16 18:18Z. **`/events/15313117`** — Twins vs
Yankees, MLB. The hero reads `live · 3m ago`, `Bottom 2nd`, score `1 – 0`,
`56% – 44%`. Scroll one screen and **Additional Markets** says:

    Minnesota Twins vs New York Yankees
    New York Yankees                     Won

The same page, ~1,500px apart, says the game is in the bottom of the 2nd AND
that the Yankees won it. It is in the served payload, not the render:
`/game-markets` → `other[]` carries `is_winner=True`,
`resolution_source='api_settlement'`, `probability=1.0`, while the same event
serves `status: live`, `completed_at: null` and an OPEN Kalshi market for the
same game priced 0.48 / 0.53.

## Why the guard that exists for exactly this question could not see it

#4965 already compares a Polymarket market's own fixture instant against the
candidate event's kick-off (`_check_polymarket_fixture_reason`). It is INERT
here, and not because its predicate is wrong: `market_metadata->>'venue_game_start'`
is **NULL** on market 60597404 and on every stale weekly container measured,
and present — `2026-09-16T17:40:00+00:00`, exactly the kick-off — only on the
correct same-day container 61181835. Nor is this the "not yet re-polled" case
its docstring deliberately fails open for: sibling 60683990 was updated at
**18:07:11Z that day** and still carries no `venue_game_start`. Gamma does not
publish one for these weekly listings at all.

Two further discriminators were measured and REJECTED before this one:

* `venue_game_start IS NULL` alone — **17,418 of 26,522** attached Polymarket
  rows. Most of the table is not a defect signal.
* nearest `resolution_date` as a chooser between same-named siblings on one
  event — **17 agree / 16 disagree** against the venue-confirmed member. A
  deterministic tiebreak is not a correct one.

## 🔴 WHAT THE ROW PROVES ON ITS OWN

Market 60597404: `settled_at 2026-09-16 05:36Z`. Event 15313117:
`commence_time 17:40Z`. **We observed the market resolved twelve hours before
first pitch.**

`settled_at` is an OBSERVATION stamp — "when status became 'resolved'", never
backfilled, NULL meaning "we did not see it settle" (the column comment on
`FuturesMarket.settled_at`). We notice a settlement late or on time, never
early, so `settled_at < commence_time` puts the VENUE's settlement before
kick-off too. The direction of the error is what makes the test safe. This is
gotcha #46's invariant — `completed_at >= commence_time` — in the markets table.

## BOTH HALVES OF THE GATE ARE LOAD-BEARING

The gate is *settled before kick-off* AND *the event has not finished*, and
neither half survives alone:

* **Unfinished alone** would withhold every market that legitimately settles
  DURING a live game. That is a supported, deliberate shape — a first-quarter
  or first-inning question answers itself while the game runs (#4788/#6082),
  and `SpecialEventMarkets.tsx` says so in as many words. What no period market
  of this game can do is settle BEFORE first pitch.
* **Settled-before-kick-off alone** reaches **1,692 verdict rows on 155
  `suspended`/`voided` events**, whose settlements are explained by a postponed
  fixture moving its `commence_time`, and which this ship has NOT established
  as defective. Plus 147 rows on completed events, where "settled means settled"
  governs and the result may well be the game's own.

Scoped to both, measured on production 2026-09-16: **82 outcome rows across 29
unfinished events, 19 of them declaring a winner** — five MLB games naming a
winner before first pitch (Braves/Cubs, Orioles/Mets, Dodgers/Reds,
Brewers/Pirates, Marlins/Diamondbacks), six Sep-26 boxing bouts, and the
specimen above.

## WHY THE VERDICT IS WITHHELD AND THE MARKET IS NOT

The 19 are two cohorts that disagree about which side is wrong:

| cohort | the market | the event's clock |
|---|---|---|
| 7 Polymarket | foreign — a weekly listing container for another fixture | right |
| 12 Kalshi boxing | right — Kalshi graded Opetaia/Mikaelyan on Sep 13 | **wrong** (our row says Sep 26; #6568's class) |

No single rule can say which. Decisive against dropping the market: **12 of the
19 events have that market as their ONLY market**, so dropping would leave a
blank page — a withholding gate must assert the surface is still a surface.
"We cannot say" is the one statement true of both cohorts, and no verdict beats
a wrong one.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.routes.events import (
    _settled_before_its_event_began,
    _settled_grade_fields,
)
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

KICKOFF = datetime(2026, 9, 16, 17, 40, tzinfo=timezone.utc)
SAW_IT_SETTLE = datetime(2026, 9, 16, 5, 36, tzinfo=timezone.utc)  # 12h early


def _mkt(settled_at, status="resolved"):
    market = MagicMock()
    market.status = status
    market.settled_at = settled_at
    return market


def _out(is_winner=True, resolution_source="api_settlement"):
    outcome = MagicMock()
    outcome.is_winner = is_winner
    outcome.resolution_source = resolution_source
    return outcome


def _grade(settled_at, *, commence=KICKOFF, finished=False, status="resolved"):
    return _settled_grade_fields(
        _mkt(settled_at, status),
        _out(),
        event_commence=commence,
        event_is_finished=finished,
    )


# ── The specimen ────────────────────────────────────────────────────────────


def test_the_yankees_do_not_win_in_the_bottom_of_the_second():
    """Market 60597404 on event 15313117, both halves true."""
    fields = _grade(SAW_IT_SETTLE)
    assert fields["is_winner"] is None, (
        "we saw this market settle 12h before first pitch and the game is still "
        "being played — the payload must not crown anyone"
    )
    assert fields["resolution_source"] is None, (
        "the source must go with the verdict; a lone resolution_source is a "
        "shape `_settled_grade_fields` does not return, and downstream readers "
        "gate on it"
    )


# ── Single-clause controls. Each fails EXACTLY ONE half, so each isolates it ──


def test_a_period_market_settling_during_a_live_game_keeps_its_verdict():
    """#4788/#6082 — the shape this gate must not touch.

    Fails only the settled-before-kick-off half: the event is just as unfinished
    as the specimen's, and the market settled an hour AFTER first pitch. A
    first-inning question answering itself mid-game is honest and stays.
    """
    fields = _grade(KICKOFF + timedelta(hours=1))
    assert fields["is_winner"] is True, (
        "a market that settled DURING the game is the legitimate period-market "
        "case; withholding it would regress #4788/#6082"
    )
    assert fields["resolution_source"] == "api_settlement"


def test_a_finished_event_keeps_a_verdict_that_predates_its_kickoff():
    """Fails only the unfinished half.

    `settled_at < commence_time` on its own reaches 1,692 verdict rows across
    155 suspended/voided events — postponed fixtures whose `commence_time`
    moved — and 147 on completed ones. This ship has not established that
    population as defective, and "settled means settled" governs there.
    """
    fields = _grade(SAW_IT_SETTLE, finished=True)
    assert fields["is_winner"] is True
    assert fields["resolution_source"] == "api_settlement"


def test_settling_exactly_at_kickoff_is_not_before_it():
    """The boundary belongs to the keep side — an element ON the boundary is not
    across it, and a market may be observed settling the instant play begins."""
    assert _grade(KICKOFF)["is_winner"] is True


# ── Fail-open: every missing signal leaves the verdict alone ────────────────


@pytest.mark.parametrize(
    "kwargs,why",
    [
        ({"settled_at": None}, "NULL settled_at means 'we did not see it settle'"),
        ({"settled_at": SAW_IT_SETTLE, "commence": None}, "no kick-off to compare to"),
        (
            {"settled_at": SAW_IT_SETTLE, "finished": None},
            "unknown finished-state — the caller did not say",
        ),
    ],
)
def test_a_missing_signal_never_strips_a_verdict(kwargs, why):
    settled_at = kwargs.pop("settled_at")
    fields = _grade(settled_at, **kwargs)
    assert fields["is_winner"] is True, f"over-refused on no signal: {why}"
    assert fields["resolution_source"] == "api_settlement"


def test_a_non_datetime_settled_at_is_no_signal():
    """A MagicMock attribute, a string, a stray int — none of them is a clock."""
    for junk in ("2026-09-16T05:36:00Z", 1758000000, MagicMock()):
        assert _settled_before_its_event_began(_mkt(junk), KICKOFF, False) is False


def test_naive_timestamps_are_compared_as_utc_not_crashed_on():
    """Mixed tz-awareness must not raise — the comparison is the whole gate."""
    assert _settled_before_its_event_began(
        _mkt(SAW_IT_SETTLE.replace(tzinfo=None)), KICKOFF.replace(tzinfo=None), False
    ) is True


# ── The older gate still decides first ──────────────────────────────────────


def test_an_unauthoritative_row_is_still_refused_by_2089s_gate():
    """#2089's two halves are upstream of this one and unchanged."""
    assert _grade(KICKOFF + timedelta(hours=1), status="open")["is_winner"] is None
    fields = _settled_grade_fields(
        _mkt(KICKOFF + timedelta(hours=1)),
        _out(resolution_source=None),
        event_commence=KICKOFF,
        event_is_finished=False,
    )
    assert fields["is_winner"] is None


def test_the_payload_shape_never_varies():
    """Both keys always, on every arm — #2089's contract."""
    for fields in (
        _grade(SAW_IT_SETTLE),
        _grade(KICKOFF + timedelta(hours=1)),
        _grade(None),
    ):
        assert set(fields) == {"is_winner", "resolution_source"}


# ── The two call sites that do NOT pass the context are provably inert ──────


def test_the_unconverted_call_sites_cannot_reach_this_arm():
    """`_settled_margin_is_provable` and the #5771 settled gate both establish
    the event is FINISHED before they call `_settled_grade_fields`, so the arm
    is unreachable from them by construction rather than by omission.

    Pinned by reading the source, because an unconverted call site is exactly
    where a gate like this silently does not apply.
    """
    import inspect

    from app.routes import events as events_module

    src = inspect.getsource(events_module)
    for call, guard in (
        ("grade = _settled_grade_fields(market, outcome)", "if not event_is_finished:"),
        (
            '_settled_grade_fields(market, o)["resolution_source"] is None',
            "if not _event_is_really_finished(event, now):",
        ),
    ):
        assert call in src, (
            f"{call!r} has moved or been converted — if it now takes the event "
            "context, delete its row here; if it lost its finished-guard, this "
            "arm is silently live on a population it was never measured against"
        )
        before = src.split(call)[0]
        assert guard in before[-2000:], (
            f"the call {call!r} no longer sits behind {guard!r}; it can now "
            "reach the #6595 arm without the event being finished"
        )


def test_every_grade_call_in_the_page_build_carries_the_event_context():
    """The build's own call sites must not drift back to the bare two-arg form.

    The gate is only as wide as its adoption: a serializer that keeps calling
    `_settled_grade_fields(market, o)` inside `_build_game_markets` serves the
    crowned row this ship exists to withhold.
    """
    import inspect

    from app.routes.events import _build_game_markets

    body = inspect.getsource(_build_game_markets)
    assert "_settled_grade_fields(market, o)" not in body, (
        "a call site inside the page build dropped `**_grade_ctx` — that "
        "serializer is now serving pre-kick-off verdicts again"
    )
    assert body.count("_settled_grade_fields(market, o, **_grade_ctx)") == 5


# ── The route serves it, and the surface is still a surface ─────────────────


@pytest.fixture
async def live_game_client():
    """Event 15313117's shape: a live game carrying one foreign settled market
    and one real open one, plus a period market that settled mid-game.
    """
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()

    event = _make_event(
        id=15313117,
        home_team="Minnesota Twins",
        away_team="New York Yankees",
        status="live",
        sport_key="baseball_mlb",
    )
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=1)
    event.completed_at = None

    # The foreign weekly container: we saw it settle 12h before this game began.
    foreign = _make_futures_market(
        id=60597404, name="New York Yankees vs. Minnesota Twins", source="polymarket"
    )
    foreign.status = "resolved"
    foreign.event_id = event.id
    foreign.llm_sport_category = "baseball"
    foreign.settled_at = event.commence_time - timedelta(hours=12)
    foreign.resolution_date = event.commence_time + timedelta(hours=3)

    # A period market that settled DURING the game — honest, and must survive.
    period = _make_futures_market(
        id=61181836, name="Twins vs Yankees: 1st Inning Winner", source="polymarket"
    )
    period.status = "resolved"
    period.event_id = event.id
    period.llm_sport_category = "baseball"
    period.settled_at = event.commence_time + timedelta(minutes=20)
    period.resolution_date = event.commence_time + timedelta(hours=3)

    outcomes = [
        _make_outcome(
            id=1, market_id=60597404, name="New York Yankees",
            probability=1.0, is_winner=True, resolution_source="api_settlement",
        ),
        _make_outcome(
            id=2, market_id=60597404, name="Minnesota Twins",
            probability=0.0, is_winner=False, resolution_source="api_settlement",
        ),
        _make_outcome(
            id=3, market_id=61181836, name="Minnesota Twins 1st Inning",
            probability=0.97, is_winner=True, resolution_source="api_settlement",
        ),
    ]

    mock_session = _make_event_detail_session(
        event=event, futures=[foreign, period], outcomes=outcomes
    )

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    _game_markets_cache.clear()
    app.dependency_overrides.clear()


def _all_rows(payload):
    rows = []
    for key in ("other", "spreads", "totals", "player_props"):
        rows.extend(payload.get(key) or [])
    for matchup in payload.get("matchups") or []:
        rows.extend(matchup.get("outcomes") or [])
    return rows


def _named(rows, needle):
    return [
        r for r in rows
        if needle in (r.get("outcome_name") or r.get("name") or "")
    ]


@pytest.mark.asyncio
async def test_the_live_page_does_not_crown_the_yankees(live_game_client):
    payload = (
        await live_game_client.get("/api/events/15313117/game-markets")
    ).json()
    rows = _named(_all_rows(payload), "New York Yankees")
    assert rows, f"the foreign market's row vanished entirely: {payload}"
    assert all(r.get("is_winner") is None for r in rows), (
        "'New York Yankees — Won' is back on a game in the bottom of the 2nd: "
        f"{rows}"
    )
    assert all(r.get("resolution_source") is None for r in rows)


@pytest.mark.asyncio
async def test_the_row_and_its_price_are_still_on_the_page(live_game_client):
    """A withholding gate must assert the surface is still a surface.

    Twelve of the nineteen production events carry the offending market as their
    ONLY market. Dropping it would have emptied those pages, which is why this
    ship withholds the verdict and nothing else — the row, its name and its
    price all stay.
    """
    payload = (
        await live_game_client.get("/api/events/15313117/game-markets")
    ).json()
    rows = _named(_all_rows(payload), "New York Yankees")
    assert rows, "the market was dropped, not unverdicted"
    assert any(r.get("probability") is not None for r in rows), (
        f"the price went with the verdict; only the verdict may go: {rows}"
    )


@pytest.mark.asyncio
async def test_the_mid_game_period_market_still_states_its_result(live_game_client):
    """The other direction, asserted as hard as the first (gotcha #43)."""
    payload = (
        await live_game_client.get("/api/events/15313117/game-markets")
    ).json()
    rows = _named(_all_rows(payload), "Minnesota Twins 1st Inning")
    assert rows, f"the period market's row vanished: {payload}"
    assert any(r.get("is_winner") is True for r in rows), (
        "a first-inning market that settled 20 minutes into the game is honest "
        f"and must keep its verdict — #4788/#6082: {rows}"
    )
