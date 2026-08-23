"""#2085 — the event page's hero pair prints 101, at BOTH of its derive sites.

## The defect

`routes/events.py` derives the away side from the home one at two places:

    hero_away_prob = round(1.0 - hero_home_prob, 6)      # the snapshot path
    "away_probability": round(1.0 - agg_prob, 6)         # the no-snapshot fallback

So the pair is an exact complement BY CONSTRUCTION, and independent half-up
rounding of each side gives `(n+1) + (100-n) = 101` exactly when `home * 100`
lands on a half-percent. The page can print 101; it can never print 99. Measured
on the feed's population 2026-08-21: 34 of 414 (8.2%) scheduled/live events. The
event page draws the same blend, so it carries the same rate.

## What this file adds over the contract suite

`test_graded_card_contract.py` proves `rendered_duel_percents` is correct and
`test_event_card_duel_percents_2114.py` proves the FEED serves it. Neither says
anything about the event DETAIL payload, which is a third surface with its own two
call sites — and #2060's lesson is that a correct helper nobody calls changes
nothing on screen.

Both sites are asserted separately, because they are reached by different branches
(odds snapshots present vs absent) and a fix applied to one looks identical in a
grep to a fix applied to both.

## The other direction is asserted as hard as the first

Gotcha #43, and #2085's own verification clause: this is a RENDERING change. The
underlying probabilities must not move — the hero, the chart's right edge and the
`probability_evidence` block all read them.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.graded_card import rendered_duel_percents
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
)

# The production specimens from #2085 / the v3 contract's `duel_cases`: a home
# probability, the percents the page MUST print as (away, home), and what
# independent rounding printed before.
SPECIMENS = [
    (0.505, (49, 51), (50, 51), "15197813 Toronto FC @ Inter Miami CF"),
    (0.675, (32, 68), (33, 68), "15200290 Green Bay Packers @ Denver Broncos"),
    (0.355, (65, 35), (65, 36), "15277855 Madison Keys @ Sara Bejlek"),
    (0.955, (4, 96), (5, 96), "15176690 Lucrecia Manzur @ Amanda Serrano"),
]


def _event_with_blend(home_prob, event_id=1):
    """An event whose blend is EXACTLY `home_prob`.

    A single betting source, so `compute_aggregate_probability` has nothing to
    average against and the hero is the specimen value rather than a blend of it
    with the fixture's default ESPN reading.
    """
    event = _make_event(id=event_id, home_prob=home_prob)
    event.win_probability_sources = {
        "betting": {"value": home_prob, "home_probability": home_prob}
    }
    event.current_home_probability = home_prob
    event.current_away_probability = round(1.0 - home_prob, 6)
    return event


def _snapshot(home_prob, bookmaker="draftkings"):
    """One odds snapshot, enough to take the snapshot branch of `current_odds`."""
    from datetime import datetime, timezone

    snap = MagicMock()
    snap.bookmaker = bookmaker
    snap.home_win_probability = home_prob
    snap.away_win_probability = round(1.0 - home_prob, 6)
    snap.home_moneyline = -150
    snap.away_moneyline = 130
    snap.home_spread = -3.5
    snap.away_spread = 3.5
    snap.over_under = 210.5
    snap.projected_home_score = 107
    snap.projected_away_score = 103
    snap.captured_at = datetime.now(timezone.utc)
    # `_effective_time` prefers valid_until and falls back to captured_at; a bare
    # MagicMock attribute is neither None nor a datetime, so it must be set
    # explicitly or the staleness filter compares a Mock against a datetime.
    snap.valid_until = None
    snap.event_id = 1
    return snap


async def _payload(event, snapshots=None):
    from app.main import app
    from app.routes.events import _event_detail_cache

    # `/api/events/{id}` caches by event id, and every specimen here is the SAME
    # id — without this, the first specimen's payload is served for all of them
    # and the suite silently grades one case four times.
    _event_detail_cache.clear()

    session = _make_event_detail_session(event=event, snapshots=snapshots)

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
                response = await ac.get(f"/api/events/{event.id}")
        return response.json()
    finally:
        app.dependency_overrides.clear()


# ── Site 2: the no-snapshot fallback ────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("home_prob", "expected", "naive", "specimen"),
    SPECIMENS,
    ids=[s[3].split()[0] for s in SPECIMENS],
)
async def test_the_fallback_site_sums_to_one_hundred(
    home_prob, expected, naive, specimen
):
    odds = (await _payload(_event_with_blend(home_prob)))["current_odds"]
    served = (odds["away_rendered_percent"], odds["home_rendered_percent"])
    assert sum(served) == 100, f"{specimen}: printed {sum(served)} — {served}"
    assert served == expected, f"{specimen}: naive rounding gives {naive}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("home_prob", "expected", "naive", "specimen"), SPECIMENS, ids=[s[3].split()[0] for s in SPECIMENS]
)
async def test_the_fallback_site_leaves_the_probabilities_untouched(
    home_prob, expected, naive, specimen
):
    """Rendering-only. #2085's verification clause, mirrored from UX-P114."""
    odds = (await _payload(_event_with_blend(home_prob)))["current_odds"]
    assert odds["home_probability"] == pytest.approx(home_prob)
    assert odds["away_probability"] == pytest.approx(round(1.0 - home_prob, 6))


# ── Site 1: the snapshot path ───────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("home_prob", "expected", "naive", "specimen"), SPECIMENS, ids=[s[3].split()[0] for s in SPECIMENS]
)
async def test_the_snapshot_site_sums_to_one_hundred(
    home_prob, expected, naive, specimen
):
    """The primary production path — `current_odds` built from odds snapshots.

    Asserted separately from the fallback because it is a different branch, and
    #2085 names it as its own site.
    """
    payload = await _payload(
        _event_with_blend(home_prob), snapshots=[_snapshot(home_prob)]
    )
    odds = payload["current_odds"]
    assert "captured_at" in odds, (
        "this specimen did not take the snapshot branch, so it is not testing "
        f"site 1: {odds}"
    )
    served = (odds["away_rendered_percent"], odds["home_rendered_percent"])
    assert sum(served) == 100, f"{specimen}: printed {sum(served)} — {served}"
    assert served == expected


@pytest.mark.asyncio
async def test_both_sites_agree_with_the_shared_helper():
    """No second implementation — the payload IS `rendered_duel_percents`."""
    for home_prob, _, _, _ in SPECIMENS:
        away = round(1.0 - home_prob, 6)
        expected = rendered_duel_percents(away, home_prob)
        for snapshots in (None, [_snapshot(home_prob)]):
            odds = (await _payload(_event_with_blend(home_prob), snapshots))[
                "current_odds"
            ]
            assert [
                odds["away_rendered_percent"],
                odds["home_rendered_percent"],
            ] == expected


# ── The other direction (gotcha #43) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_already_consistent_pair_is_left_exactly_alone():
    """380 of the 414 measured events were already consistent.

    A rule that "fixed" them would be changing numbers nobody complained about.
    """
    odds = (await _payload(_event_with_blend(0.62)))["current_odds"]
    assert (odds["away_rendered_percent"], odds["home_rendered_percent"]) == (38, 62)


@pytest.mark.asyncio
async def test_the_fields_are_present_whenever_the_hero_pair_is():
    """A sometimes-missing key is a second shape for every client to handle."""
    for snapshots in (None, [_snapshot(0.505)]):
        odds = (await _payload(_event_with_blend(0.505), snapshots))["current_odds"]
        assert "away_rendered_percent" in odds
        assert "home_rendered_percent" in odds
