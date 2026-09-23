"""Guard: the event page and the league page agree about kick-off (#5905).

WHAT A READER SAW. On 2026-09-13 at 23:0xZ, production served the same game at
two different hours depending on which surface you were standing on:

    /api/leagues/soccer_other  →  Famalicão v Sporting CP   19:30Z
    /api/events/15307690       →  Famalicão v Sporting CP   22:30Z

Tap the card, and the kick-off moves three hours. Same for `15308597`
(20:00 vs 23:00) and `15311626`. Forty-plus such rows were upcoming within
three days.

WHY ONLY THIS ROUTE. Every LIST-shaped surface reaches the correction through
`fold_twin_events`, which runs `recover_kalshi_occurrence_starts` at its top.
The detail route folds nothing — there is one row and nothing to fold it
against — so it served the raw column, and the raw column on a Kalshi-minted
row is the market's EXPECTED EXPIRATION, not the kick-off (gotcha #14).

WHAT THESE TESTS ARE ACTUALLY DEFENDING. Not "a route subtracts three hours".
The ways this can go wrong and reach Alex:

* the wiring is dropped and the page silently goes back to the stored hour
  (`test_the_event_page_serves_the_kickoff_not_the_expected_expiration`);
* it is wired somewhere that a 410 or a duplicate-swap bypasses
  (`test_the_row_actually_served_is_the_row_corrected`);
* it fires on a row a schedule provider anchored, moving a REPORTED start
  (`test_an_anchored_row_is_never_moved_by_the_detail_route`);
* it fires outside soccer, where the pad is not a constant
  (`test_a_basketball_row_is_never_moved_by_the_detail_route`);
* it double-subtracts across the route's own payload cache
  (`test_two_reads_of_the_same_event_do_not_stack_two_pads`).

🔴 THE TWO REFUSAL TESTS ARE THE ONES THAT CAN GO VACUOUS, and the reason is
specific to this rig: the seeded double is a `MagicMock`, so EVERY attribute is
auto-created and truthy. `recover_kalshi_occurrence_starts` opens with
`getattr(event, KALSHI_RECOVERY_STAMP, False)` — on an untouched mock that reads
as "already recovered" and the function returns without doing anything. A
refusal test written on a bare mock therefore passes whether or not any refusal
exists, and so would the POSITIVE test. `_kalshi_minted_row` sets the stamp
False explicitly for exactly this reason, and
`test_the_rig_itself_can_see_a_correction` is the strawman that fails if that
ever stops being true.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.kalshi_occurrence_start import (
    KALSHI_EXPECTED_EXPIRATION_PAD,
    KALSHI_RECOVERY_STAMP,
)
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
)

#: Famalicão v Sporting CP as production held it on 2026-09-13: the stored
#: column is the market's expected expiration, three hours after the whistle.
KICKOFF = datetime(2026, 9, 13, 19, 30, tzinfo=timezone.utc)
EXPECTED_EXPIRATION = datetime(2026, 9, 13, 22, 30, tzinfo=timezone.utc)


def _kalshi_minted_row(event_id: int, *, sport_key: str = "soccer_other", **over):
    """The seeded detail double, shaped into a row this recovery should move.

    Four fields carry the whole population and each one is a refusal if it is
    wrong, so they are set explicitly rather than left to the mock:

    * `external_id=None`   — no schedule provider reported this start, so the
      time is ours to correct. A `MagicMock`'s auto-attribute is truthy, which
      is the anchored case, which refuses.
    * `commence_time_source="kalshi"` — in `KALSHI_OCCURRENCE_TIMED_SOURCES`.
    * `sport.key` a real `str` — `loaded_sport_key` returns `None` for anything
      that is not a string, and `None` refuses.
    * the stamp `False` — see this module's docstring. Without it the recovery
      reads the mock as already-corrected and does nothing, silently.
    """
    event = _make_event(id=event_id, sport_key=sport_key, home_score=None, away_score=None)
    event.external_id = None
    event.commence_time_source = "kalshi"
    event.commence_time = EXPECTED_EXPIRATION
    event.completed_at = None
    event.status = "scheduled"
    event.sport.key = sport_key
    setattr(event, KALSHI_RECOVERY_STAMP, False)
    for key, value in over.items():
        setattr(event, key, value)
    return event


async def _serve(event):
    """Drive the real `/api/events/{id}` handler over one seeded row."""
    from app.main import app
    from app.routes.events import _event_detail_cache, _game_markets_cache

    _game_markets_cache.clear()
    _event_detail_cache.clear()

    session = _make_event_detail_session(event=event)

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                return await ac.get(f"/api/events/{event.id}")
    finally:
        _game_markets_cache.clear()
        _event_detail_cache.clear()
        app.dependency_overrides.clear()


def _served_commence(resp):
    assert resp.status_code == 200, resp.text
    body = resp.json()
    raw = (body.get("event") or body).get("commence_time")
    assert raw, f"the detail payload carried no commence_time: {body!r}"
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


# ── the ship ────────────────────────────────────────────────────────────────


async def test_the_event_page_serves_the_kickoff_not_the_expected_expiration():
    served = _served_commence(await _serve(_kalshi_minted_row(9905001)))
    assert served == KICKOFF, (
        "the event page served the stored expected-expiration hour; this is the "
        "#5905 defect, where /api/leagues said 19:30Z and this route said 22:30Z "
        "for the same game"
    )


async def test_the_correction_is_exactly_the_measured_pad_not_a_rounding():
    served = _served_commence(await _serve(_kalshi_minted_row(9905002)))
    assert EXPECTED_EXPIRATION - served == KALSHI_EXPECTED_EXPIRATION_PAD


async def test_the_two_surfaces_now_agree_to_the_minute():
    """The whole point: the fold's answer and this route's answer are one hour.

    `fold_twin_events` is what every list surface runs, so folding the same row
    and serving it must land on the same instant. If these ever diverge the
    reader is back to a kick-off that moves when they tap.
    """
    from app.utils.event_twin_fold import fold_twin_events

    folded_row = _kalshi_minted_row(9905003)
    fold_twin_events([folded_row])
    served = _served_commence(await _serve(_kalshi_minted_row(9905004)))
    assert folded_row.commence_time == served == KICKOFF


# ── the refusals: rows this route must NOT move ─────────────────────────────


async def test_an_anchored_row_is_never_moved_by_the_detail_route():
    """A start a schedule provider reported is not ours to shift."""
    row = _kalshi_minted_row(9905005, external_id="odds-api-abc123")
    assert _served_commence(await _serve(row)) == EXPECTED_EXPIRATION


async def test_a_basketball_row_is_never_moved_by_the_detail_route():
    """Outside soccer the pad is a spread, not a constant (gotcha #14)."""
    row = _kalshi_minted_row(9905006, sport_key="basketball_nba")
    assert _served_commence(await _serve(row)) == EXPECTED_EXPIRATION


async def test_a_row_whose_time_came_from_a_schedule_is_never_moved():
    row = _kalshi_minted_row(9905007, commence_time_source="odds_api")
    assert _served_commence(await _serve(row)) == EXPECTED_EXPIRATION


async def test_a_ticker_midnight_is_never_moved_by_the_detail_route():
    """`kalshi_ticker` resolves to midnight UTC — a stand-in, not this instant."""
    row = _kalshi_minted_row(9905008, commence_time_source="kalshi_ticker")
    assert _served_commence(await _serve(row)) == EXPECTED_EXPIRATION


# ── idempotence, which is load-bearing rather than tidy ─────────────────────


async def test_two_reads_of_the_same_event_do_not_stack_two_pads():
    """Two requests must not advertise a kick-off SIX hours early.

    The route has an in-process payload cache, so the realistic second read is a
    cache hit; this drives the handler twice over the same hydrated object,
    which is the harsher case and the one `KALSHI_RECOVERY_STAMP` exists for.
    """
    row = _kalshi_minted_row(9905009)
    first = _served_commence(await _serve(row))
    second = _served_commence(await _serve(row))
    assert first == second == KICKOFF


# ── CERT-3342: the write rail and the serve rail, composed ──────────────────
#
# #3565 gives `_refine_stand_in_event_starts` a REVISION arm, so the stored
# column is no longer written once and left alone — the venue can restate its
# occurrence and the rail follows it. That makes the serve-time pad a moving
# target for the first time, and the failure it can produce is arithmetic:
# a revision that is applied to an ALREADY-CORRECTED value instead of to the
# stored occurrence serves a kick-off three hours further out on every
# restatement. The ladder authority/179 measured on the double-fold route is
# the same defect from the other end (21:45 → 18:45 → 15:45 → 12:45).


#: The venue restates the fixture: 45 minutes later, same day. What the refine
#: rail would write into `events.commence_time` on its next pass.
RESTATED_EXPIRATION = datetime(2026, 9, 13, 23, 15, tzinfo=timezone.utc)
RESTATED_KICKOFF = datetime(2026, 9, 13, 20, 15, tzinfo=timezone.utc)


async def test_a_revised_occurrence_serves_one_pad_off_the_NEW_stored_hour():
    """One revision: the page follows the venue, still exactly one pad back."""
    row = _kalshi_minted_row(9905020, commence_time=RESTATED_EXPIRATION)
    assert _served_commence(await _serve(row)) == RESTATED_KICKOFF


async def test_two_successive_revisions_do_not_compound_the_pad():
    """🔴 The two-revision regression CERT-3342 required.

    The rail revises the stored hour twice — 22:30 → 23:15 → 23:45 — and the
    page must read each one as `stored - 3h`. The number that must never
    appear is a compounded one: 23:45 served as 17:45 (two pads) or 14:45
    (three) would be a kick-off advertised hours before the match, which is
    precisely the class #5905 was filed for.

    Each revision is served on a freshly hydrated row, because that is what
    production does — the rail writes, the next request re-reads. The
    in-request stamp cannot help here: it dies with the request, so the only
    thing keeping the arithmetic honest is that the pad comes off the STORED
    column rather than off whatever was served last time.
    """
    second_expiration = datetime(2026, 9, 13, 23, 45, tzinfo=timezone.utc)
    second_kickoff = datetime(2026, 9, 13, 20, 45, tzinfo=timezone.utc)

    served = [
        _served_commence(await _serve(_kalshi_minted_row(9905021 + i,
                                                         commence_time=stored)))
        for i, stored in enumerate(
            (EXPECTED_EXPIRATION, RESTATED_EXPIRATION, second_expiration)
        )
    ]

    assert served == [KICKOFF, RESTATED_KICKOFF, second_kickoff]
    # ...and say the failure out loud, so a regression names itself.
    assert served[-1] != second_expiration - 2 * (EXPECTED_EXPIRATION - KICKOFF)
    assert served[-1] != second_expiration - 3 * (EXPECTED_EXPIRATION - KICKOFF)


async def test_the_served_hour_tracks_the_venue_rather_than_drifting_one_way():
    """A restatement that moves the fixture EARLIER must move the page earlier.

    The revision arm accepts either direction inside the ticker day (an
    order-of-play reshuffle moves matches forward as often as back), so a serve
    path that only ever added time would quietly disagree with the venue on
    half the restatements.
    """
    earlier_expiration = datetime(2026, 9, 13, 21, 0, tzinfo=timezone.utc)
    earlier_kickoff = datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc)

    later = _served_commence(
        await _serve(_kalshi_minted_row(9905030, commence_time=RESTATED_EXPIRATION))
    )
    earlier = _served_commence(
        await _serve(_kalshi_minted_row(9905031, commence_time=earlier_expiration))
    )
    assert (later, earlier) == (RESTATED_KICKOFF, earlier_kickoff)
    assert earlier < later


# ── the strawman: prove this rig can fail ───────────────────────────────────


async def test_the_rig_itself_can_see_a_correction():
    """If the mock's truthy auto-stamp ever comes back, every test above goes green.

    A row identical to the positive specimen EXCEPT that the stamp is left as the
    mock made it must come back UNCORRECTED. That asymmetry is the only evidence
    that the positive tests are measuring the route and not the double.
    """
    row = _kalshi_minted_row(9905010)
    setattr(row, KALSHI_RECOVERY_STAMP, True)  # "already recovered this request"
    assert _served_commence(await _serve(row)) == EXPECTED_EXPIRATION


@pytest.mark.parametrize(
    "sport_key",
    ["soccer_spain_la_liga", "soccer_uefa_champs_league", "soccer_epl", "soccer_other"],
)
async def test_every_soccer_league_reaches_the_correction_not_just_the_listed_ones(
    sport_key,
):
    """`_soccer` is a prefix test; the league vocabulary grows every week."""
    row = _kalshi_minted_row(9905100 + abs(hash(sport_key)) % 800, sport_key=sport_key)
    assert _served_commence(await _serve(row)) == KICKOFF


async def test_the_stored_column_is_not_quietly_rewritten():
    """Serve-time only: the page is corrected, `events` is not (gotcha #4).

    The mock cannot prove SQLAlchemy dirtiness, so this asserts the weaker thing
    the mock CAN prove and that the ORM arm is covered elsewhere
    (`test_kalshi_occurrence_start_5905.py::test_a_real_orm_row_is_corrected_and_is_NOT_left_dirty`):
    nothing on this path writes through a session.
    """
    row = _kalshi_minted_row(9905011)
    await _serve(row)
    assert row.commence_time == KICKOFF, "the served row carries the corrected hour"
    assert KICKOFF == EXPECTED_EXPIRATION - timedelta(hours=3)


# ── CERT-3344: the fixture the rail reached through its DERIVATIVE ──────────
#
# The end-to-end the block required. Every test above starts from an hour
# already stored on the event; these start one step earlier, at the rail that
# decides WHICH sibling's hour gets stored, because that is where the defect
# lived. #6715: one soccer event carries GAME at 22:30Z and BTTS/SPREAD/TOTAL
# at 23:30Z, and `ORDER BY fm.external_id` reaches BTTS first.
#
# The number these exist to keep off the page is 20:30Z — a fixture that kicks
# off at 19:30Z, advertised an hour late, on a page that was correct before.

_MS_DAY = datetime(2026, 9, 13, 0, 0, tzinfo=timezone.utc)
_MS_BTTS = "KXLIGUE1BTTS-26SEP13OLMPSG"
_MS_GAME = "KXLIGUE1GAME-26SEP13OLMPSG"
_MS_SPORT = "soccer_france_ligue_one"
#: GAME says 22:30Z (`EXPECTED_EXPIRATION`); its derivatives say 23:30Z.
_MS_DERIVATIVE_EXPIRATION = EXPECTED_EXPIRATION + timedelta(hours=1)
#: What the page WOULD have served off the unnormalised derivative hour.
_MS_WRONG_SERVED = _MS_DERIVATIVE_EXPIRATION - KALSHI_EXPECTED_EXPIRATION_PAD


def _rail_writes(ticker, market_hour, *, stored, source):
    """What `_refine_stand_in_event_starts` would put in `events.commence_time`."""
    from app.tasks.kalshi import _stand_in_refinement_decision

    return _stand_in_refinement_decision(
        ticker, stored, source, market_hour, sport_key=_MS_SPORT,
    )


def test_the_wrong_hour_is_a_real_hour_this_route_would_have_served():
    """Anti-vacuity. If 20:30Z were unreachable the guards below prove nothing,
    so the strawman is pinned: one pad off the derivative's own hour IS 20:30Z,
    and it is exactly one hour past the kick-off."""
    assert _MS_WRONG_SERVED == datetime(2026, 9, 13, 20, 30, tzinfo=timezone.utc)
    assert _MS_WRONG_SERVED - KICKOFF == timedelta(hours=1)


async def test_a_fixture_reached_through_its_derivative_still_serves_the_kickoff():
    """🔴 CERT-3344, end to end: rail → stored hour → served page.

    BTTS speaks first and its hour is 23:30Z. The reader must still be told
    19:30Z.
    """
    written, reason = _rail_writes(
        _MS_BTTS, _MS_DERIVATIVE_EXPIRATION,
        stored=_MS_DAY, source="kalshi_ticker",
    )
    assert reason == "adopt", reason

    served = _served_commence(
        await _serve(_kalshi_minted_row(9905040, sport_key=_MS_SPORT,
                                        commence_time=written))
    )
    assert served == KICKOFF, (
        f"the page served {served:%H:%M}Z for a fixture that kicks off at "
        f"{KICKOFF:%H:%M}Z — the derivative series' clock reached the reader"
    )
    assert served != _MS_WRONG_SERVED


async def test_the_game_sibling_serves_the_same_hour_as_the_derivative_one():
    """Order independence, read at the surface rather than at the predicate.

    The rail's outcome depends on which sibling `external_id` ordering happens
    to reach first. After the repair that is no longer a question the READER can
    tell has been asked, which is the only place it matters.
    """
    pages = set()
    for ticker, hour in (
        (_MS_BTTS, _MS_DERIVATIVE_EXPIRATION),
        (_MS_GAME, EXPECTED_EXPIRATION),
    ):
        written, reason = _rail_writes(
            ticker, hour, stored=_MS_DAY, source="kalshi_ticker",
        )
        assert reason == "adopt", (ticker, reason)
        pages.add(
            _served_commence(
                await _serve(_kalshi_minted_row(9905041, sport_key=_MS_SPORT,
                                                commence_time=written))
            )
        )
    assert pages == {KICKOFF}, pages


async def test_a_second_pass_over_the_corrected_event_serves_the_same_hour():
    """The no-change / fixed-point half.

    Once the event holds the GAME hour, every sibling — derivatives included —
    must answer `agrees`, nothing is written, and a re-read serves the same
    minute. A rail that answered `adopt` here would move a correct page on every
    beat, which is the flap the anti-flap control exists to prevent.
    """
    for ticker, hour in (
        (_MS_BTTS, _MS_DERIVATIVE_EXPIRATION),
        (_MS_GAME, EXPECTED_EXPIRATION),
    ):
        target, reason = _rail_writes(
            ticker, hour, stored=EXPECTED_EXPIRATION, source="kalshi_occurrence",
        )
        assert (target, reason) == (None, "agrees"), (ticker, target, reason)

    served = _served_commence(
        await _serve(_kalshi_minted_row(9905042, sport_key=_MS_SPORT,
                                        commence_time=EXPECTED_EXPIRATION))
    )
    assert served == KICKOFF


async def test_a_restated_fixture_follows_the_venue_on_the_game_clock():
    """The restatement half. The venue moves the whole fixture an hour later —
    GAME 22:30→23:30, derivatives 23:30→00:30 — and the page must follow to
    20:30Z exactly once, off the GAME clock. Note this is the same wall-clock
    number the unrepaired code served for the UNMOVED fixture: the repair is
    what makes 20:30Z mean "the venue moved it" instead of "we read the wrong
    sibling".
    """
    moved_game = EXPECTED_EXPIRATION + timedelta(hours=1)
    moved_derivative = _MS_DERIVATIVE_EXPIRATION + timedelta(hours=1)

    for ticker, hour in ((_MS_BTTS, moved_derivative), (_MS_GAME, moved_game)):
        written, reason = _rail_writes(
            ticker, hour, stored=EXPECTED_EXPIRATION, source="kalshi_occurrence",
        )
        assert (written, reason) == (moved_game, "adopt"), (ticker, written)
        served = _served_commence(
            await _serve(_kalshi_minted_row(9905043, sport_key=_MS_SPORT,
                                            commence_time=written))
        )
        assert served == KICKOFF + timedelta(hours=1), (ticker, served)
