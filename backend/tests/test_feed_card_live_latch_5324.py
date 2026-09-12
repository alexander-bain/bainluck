"""#5324 — a Discover card must not say LIVE before anyone has served.

`events.status` is a LATCH. `transition_event_statuses` promotes
`scheduled -> live` the moment `commence_time <= now`, and NOTHING re-derives
it. So when ESPN slides a start forward — which we ingest correctly — the row
goes on asserting `live` against its own start time.

MEASURED by ux/1198 on production, US Open men's semifinal Zverev v Khachanov
(15309206), 2026-09-11. Both answers read in the same command:

    18:47Z  status=scheduled                       commence=19:00:00Z
    19:04Z  status=live  0-0 null null  ESPN=upcoming  commence=19:05:00Z
    19:07Z  status=live  0-0 null null  ESPN=upcoming  commence=19:10:00Z
    19:08Z  status=live  0-0 null null  ESPN=upcoming  commence=19:10:00Z

Read the `commence_time` column: it is being UPDATED. We held the corrected
start and ESPN's `upcoming` simultaneously, and served a third answer that
contradicted both. Our own tournament hub rendered the same match, the same
minute, as a normal scheduled card.

`app.utils.lifecycle.served_event_status` is the rule that already exists for
exactly this, and `routes/events.py`, `teams.py`, `league_futures.py`,
`march_madness.py` and `futures.py` all go through it. `routes/feed.py` never
imported it, so every Discover card served the raw column — the one surface
with no repair was the feed.

THESE TESTS DRIVE `_score_events`, NOT THE SERIALIZERS. That is deliberate and
it is the whole point. CERT-2700 filed the follow-up
`4971-FEED-ROUTE-GUARD-PINS-HERO-FIELDS` against this module's sibling test
precisely because direct `format_event_data` guards keep passing when the route
WIRING is removed. Deleting `status=served_status` from any of the five call
sites must turn one of these red, so each is asserted on the card the route
actually builds.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routes.feed import _score_events
from app.utils.lifecycle import EVENT_NOT_STARTED
from app.utils.personalization import PersonalizationContext

NOW = datetime(2026, 9, 11, 19, 7, 0, tzinfo=timezone.utc)


def _sport(key="tennis_atp_us_open", name="US Open"):
    s = MagicMock()
    s.key = key
    s.name = name
    return s


def _event(
    event_id: int,
    *,
    status: str,
    commence_time: datetime,
    home_score=None,
    away_score=None,
    period=None,
    game_clock=None,
    sport_key="tennis_atp_us_open",
):
    """A row shaped like the specimen: latched `live`, nothing observed."""
    e = MagicMock()
    e.id = event_id
    e.status = status
    e.commence_time = commence_time
    e.home_team_id = 10 + event_id
    e.away_team_id = 20 + event_id
    e.home_team_name = "Alexander Zverev"
    e.away_team_name = "Karen Khachanov"
    e.opening_home_probability = 0.62
    e.opening_away_probability = 0.38
    e.win_probability_sources = {"betting": {"home_probability": 0.62}}
    e.opening_home_spread = None
    e.opening_over_under = None
    e.opening_favorite = "Alexander Zverev"
    e.llm_importance = "marquee"
    e.llm_gender = None
    e.llm_level = None
    e.llm_league = None
    e.sport = _sport(sport_key)
    e.statpal_end_time = None
    e.completed_at = None
    e.period = period
    e.game_clock = game_clock
    e.raw_ei = 90.0
    e.ei_metadata = None
    e.home_score = home_score
    e.away_score = away_score
    e.external_id = f"ext-{event_id}"
    e.broadcast_info = None
    e.event_tags = []
    e.image_url = None
    return e


def _mock_db(events):
    db = AsyncMock()

    def make_result(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.all.return_value = []
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "win_prob_snapshots" in s:
            return make_result([])
        if "events" in s:
            return make_result(events)
        return make_result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


async def _cards(events, now=NOW):
    """Drive the real card loop and return the cards it built, by event id.

    `my_teams_only=True` is the My Teams rail, and it is used here for ONE
    reason: it sets `min_score = 0`. On the default rail a not-yet-started
    tennis match is dropped by the `admission_score < min_score` gate before it
    is ever serialized — which is correct ranking behaviour and entirely
    orthogonal to what these tests assert. Every line under test (the five
    consumers fed `served_status`) is the same code on both rails; only the
    admission bar differs. Without this the defect tests would pass on an
    EMPTY result set, which is the vacuous shape, not a guard.
    """
    with patch(
        "app.routes.feed._get_championship_probabilities",
        new=AsyncMock(return_value={}),
    ):
        items = await _score_events(
            _mock_db(events),
            now,
            None,
            PersonalizationContext(),
            True,
            ["Alexander Zverev"],
        )
    cards = {i["data"]["id"]: i for i in items if i["type"] == "event"}
    assert cards, "no card was built at all — the test proves nothing as written"
    return cards


# ── THE DEFECT ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_card_whose_start_is_still_ahead_is_not_served_live_5324():
    """The specimen: 19:07Z, latched live, its own start says 19:10Z."""
    specimen = _event(
        15309206, status="live", commence_time=NOW + timedelta(minutes=3)
    )
    card = (await _cards([specimen]))[15309206]["data"]

    assert card["status"] == EVENT_NOT_STARTED, (
        "the card asserted LIVE for a match whose own commence_time is still "
        f"three minutes away: status={card['status']!r}"
    )


@pytest.mark.asyncio
async def test_the_temporal_badge_stops_reading_live_before_the_start_5324():
    """`_compute_temporal_badge` takes no `commence_time`: live in, Live out."""
    specimen = _event(
        15309206, status="live", commence_time=NOW + timedelta(minutes=3)
    )
    card = (await _cards([specimen]))[15309206]["data"]

    assert card.get("temporal_badge") != "Live", (
        "the card carried a Live badge for a match that had not started — the "
        "second of the two live assertions a Discover card makes"
    )


@pytest.mark.asyncio
async def test_the_tag_and_the_status_cannot_contradict_each_other_5324():
    """One payload, one answer. `compute_event_tags` was fed the raw latch."""
    specimen = _event(
        15309206, status="live", commence_time=NOW + timedelta(minutes=3)
    )
    card = (await _cards([specimen]))[15309206]["data"]
    tags = card.get("event_tags") or card.get("inline_tags") or []

    assert "status:live" not in tags, (
        f"payload served status={card['status']!r} beside a status:live tag: {tags}"
    )


@pytest.mark.asyncio
async def test_the_card_makes_no_live_claim_about_a_match_not_begun_5324():
    """ux/1198 read `0` and `0` beside both players — not nulls, ZEROES.

    That is the shape that makes `compose_live_claim` speak: with a 0–0 "score"
    and a price that moved off its open, the composer's `movement` arm fires and
    the card prints "chance rose from 50% to 90%" as a LIVE development. It is
    handed a status rather than a clock, so it cannot refuse on its own.
    """
    specimen = _event(
        15309206,
        status="live",
        commence_time=NOW + timedelta(minutes=3),
        home_score=0,
        away_score=0,
    )
    item = (await _cards([specimen]))[15309206]
    text = f"{item.get('reason') or ''} {item.get('headline') or ''}".lower()

    assert "rose from" not in text and "fell from" not in text, (
        "the card narrated a live price movement for a match that had not "
        f"started: {text!r}"
    )


# ── THE FLOOR: WHAT MUST NOT MOVE ────────────────────────────────────────────
#
# ux/1198's own comment is the reason this half exists. At 19:09Z, of 75 live
# events: 70 had no `period`, 70 no `game_clock`, 48 NULL scores. Those are
# NOT instances of this bug — they are sports where we hold no clock at all
# (#4571). A fix that demoted on "nothing observed" would call 48 genuinely
# live games scheduled. The ONLY signal this change reads is the row refuting
# ITSELF: live, with its own start still in the future.


@pytest.mark.asyncio
async def test_a_live_game_with_no_clock_and_no_score_is_still_live_4571():
    """The 48-row cohort. Start has passed, nothing observed — still live."""
    started = _event(
        15305057,
        status="live",
        commence_time=NOW - timedelta(minutes=40),
        home_score=None,
        away_score=None,
        period=None,
        game_clock=None,
    )
    card = (await _cards([started]))[15305057]["data"]

    assert card["status"] == "live", (
        "demoted a genuinely live game for having no clock — this is #4571's "
        "population, not #5324's, and it is 48 of 75 live rows"
    )
    assert card.get("temporal_badge") == "Live"


@pytest.mark.asyncio
async def test_a_live_game_in_progress_keeps_its_badge_and_its_claim():
    """The ordinary case, with observations, must be untouched."""
    playing = _event(
        15305058,
        status="live",
        commence_time=NOW - timedelta(hours=1),
        home_score=6,
        away_score=4,
        period="2nd Set",
        game_clock=None,
    )
    card = (await _cards([playing]))[15305058]["data"]

    assert card["status"] == "live"
    assert card.get("temporal_badge") == "Live"


@pytest.mark.asyncio
async def test_only_live_is_ever_rewritten_terminal_rows_pass_through():
    """`served_event_status` rewrites `live` and nothing else.

    A completed row with a future `commence_time` is a REAL state (#4114 — a
    cross-merge rewrites the clock forward under a settled row) and it has its
    own repair in `espn_sync`. This change must not touch it, or a finished
    game starts rendering as a fixture.
    """
    settled = _event(
        14792834,
        status="completed",
        commence_time=NOW + timedelta(hours=2),
        home_score=38,
        away_score=21,
    )
    card = (await _cards([settled]))[14792834]["data"]

    assert card["status"] == "completed", (
        "a terminal status was rewritten — only `live` may ever be repaired"
    )


@pytest.mark.asyncio
async def test_a_scheduled_row_is_not_promoted_by_this_change():
    """The repair only ever demotes. Nothing here may invent liveness."""
    upcoming = _event(
        15309207, status="scheduled", commence_time=NOW - timedelta(minutes=5)
    )
    card = (await _cards([upcoming]))[15309207]["data"]

    assert card["status"] == "scheduled"


# ── THE BOUNDARY ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_repair_fires_on_seconds_not_only_on_hours_5324():
    """The window is the DELAY, and ESPN slid this start by five minutes.

    The specimen was 18 seconds from its own start at 19:04:42Z. A tolerance
    measured in hours — like the `now + 1h` the future-SETTLED repair uses for
    its own, different race — would read as a fix and catch nothing here.
    """
    barely = _event(
        15309206, status="live", commence_time=NOW + timedelta(seconds=18)
    )
    card = (await _cards([barely]))[15309206]["data"]

    assert card["status"] == EVENT_NOT_STARTED, (
        "an 18-second-away start did not trip the repair; the measured "
        "specimen was exactly this far from its own commence_time"
    )


@pytest.mark.asyncio
async def test_a_start_exactly_now_is_started_not_pending():
    """`commence_time == now` is the start, not still-ahead-of-us."""
    on_the_dot = _event(15309208, status="live", commence_time=NOW)
    card = (await _cards([on_the_dot]))[15309208]["data"]

    assert card["status"] == "live"
