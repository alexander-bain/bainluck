"""The venue-instant arm reaches its own specimens (#8547, reach).

**SHIP: Friday's Orioles @ Yankees game 2 (15318665) shows its own Polymarket
price, and game 1 (15318575) stops carrying game 2's Polymarket and Kalshi
markets.** (Pillar: MATCHING.)

The arm itself shipped — #8560 for Polymarket, #8614 for Kalshi — and neither
moved its specimen, because Phase 1.5 never handed it the row. Production,
2026-09-25 17:40Z, 19,748 eligible links in 27 shards:

    Gamma 1053347  venue 23:05Z (game 2)  on game 1 (20:05Z)
        61665049  parent      shard 19, position 775 of 775 (cap 750)
        62232220  moneyline   shard  1, position 651 of 682
    KXMLBGAME-26SEP251905BALNYY  (19:05 ET = 23:05Z)  on game 1
        62013568              shard 22, position 627 of 732

The fresh slice (250) is filled from rank 2 — links to rows with no
``external_id``, 11,517 of them — before any anchored scheduled game (rank 3)
is looked at; the rotation sorts a re-polled Polymarket row to the very back of
its shard, where the 750 cap cuts it. Gamma 1047825 (venue 20:05Z) is game 1's
and correctly stays there — the watcher that tracked it had the two ids
swapped.

The fix gives the arm its own slice, selected by the arm's own entry predicate.

WHAT EACH TEST DEFENDS:

* the ship with both slices starved exactly as on production: 1053347 moves to
  game 2, 1047825 stays on game 1
  (``test_a_starved_polymarket_link_still_reaches_the_arm``), and the strawman
  that proves the starvation is real — the same run with the new slice emptied
  moves nothing (``test_strawman_without_the_slice_the_starved_link_is_never_seen``);
* the Kalshi specimen under the same starvation
  (``test_a_starved_kalshi_ticker_still_reaches_the_arm``);
* the pure selector: the arm's predicate verbatim, covered-league rows only,
  soonest game first, bounded (``test_candidate_ids_*``);
* the probe's population: finished, retired and out-of-window rows are not
  probed, and the ``->>`` read executes on the suite's engine
  (``test_the_probe_reads_only_near_term_unfinished_links``).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tests.test_phase15_venue_instant_relink_8547 import (
    GAME_1,
    GAME_2,
    NOW,
    _event,
    _new_rail,
    _on,
    _pm,
    _run_phase15,
)

TICKER = "KXMLBGAME-26SEP251905BALNYY"  # 19:05 ET = 23:05Z = GAME_2
GAME_2_EVENT = "1053347"  # slug mlb-bal-nyy-2026-09-26, startTime 23:05Z today
GAME_1_EVENT = "1047825"  # slug mlb-bal-nyy-2026-09-25, startTime 20:05Z


def _anchored(session, mlb, commence, odds_api_id, *, espn_id=None):
    """A scheduled row carrying its Odds API id — rank 3, like both real games."""
    e = _event(session, mlb, commence, espn_id=espn_id)
    e.external_id = odds_api_id
    session.flush()
    return e


def _filler(session, mlb, n=3):
    """Links that outrank every anchored game in both slices (rank 2: no
    ``external_id`` on their row) and that no arm acts on."""
    from app.models.models import Event, FuturesMarket

    out = []
    for i in range(n):
        e = Event(
            sport_id=mlb.id, home_team_name="Somewhere FC",
            away_team_name="Elsewhere FC", commence_time=GAME_1 + timedelta(days=1),
            status="scheduled", external_id=None,
        )
        session.add(e)
        session.flush()
        m = FuturesMarket(
            source="polymarket", external_id=f"filler-{i}",
            name=f"Will it rain in the Bronx on day {i}?", category="weather",
            status="open", event_id=e.id,
        )
        session.add(m)
        session.flush()
        out.append(m)
    return out


def _production_specimen(session, mlb):
    """Both games anchored; game 2's Polymarket group and Kalshi ticker on game 1."""
    game_1 = _anchored(
        session, mlb, GAME_1, "d4b069a134ec3ae75f0a644498b793c6", espn_id="401817088",
    )
    game_2 = _anchored(session, mlb, GAME_2, "3fe14d478bc1ffac17198c460085ca70")
    parent = _pm(
        session, game_1, pm_event_id=GAME_2_EVENT, venue_start=GAME_2,
        external_id=GAME_2_EVENT, group_type="polymarket_event",
    )
    moneyline = _pm(
        session, game_1, pm_event_id=GAME_2_EVENT, venue_start=GAME_2,
        external_id="0xe7cbc320665f2e0978f6864bec1c26b315d63a71593f94cfaeab933c5732b87f",
        group_type="polymarket_sub_market",
    )
    own = _pm(
        session, game_1, pm_event_id=GAME_1_EVENT, venue_start=GAME_1,
        external_id=GAME_1_EVENT, group_type="polymarket_event",
    )
    _filler(session, mlb)
    session.commit()
    return game_1, game_2, parent, moneyline, own


async def _starved_run(session, *, slice_enabled=True):
    """Phase 1.5 with the fresh and rotation slices one row deep, so the filler
    takes both — the production position of every specimen."""
    from app.tasks import prediction_market_matching as task_mod

    real_fresh = task_mod._phase15_fresh_query
    real_rotation = task_mod._phase15_rotation_query
    patches = [
        patch.object(task_mod, "_phase15_fresh_query", new=lambda: real_fresh(limit=1)),
        patch.object(
            task_mod, "_phase15_rotation_query",
            new=lambda shards, idx: real_rotation(shards, idx, limit=1),
        ),
    ]
    if not slice_enabled:
        patches.append(
            patch.object(
                task_mod, "_phase15_venue_instant_candidate_ids",
                new=lambda rows, limit=50: [],
            )
        )
    for p in patches:
        p.start()
    try:
        return await _run_phase15(session)
    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_a_starved_polymarket_link_still_reaches_the_arm():
    """🔴 THE SHIP. 1053347 (23:05Z) moves to game 2; 1047825 (20:05Z) stays."""
    session, mlb = _new_rail()
    game_1, game_2, parent, moneyline, own = _production_specimen(session, mlb)

    stats, _ = await _starved_run(session)

    assert _on(session, parent, moneyline) == [game_2.id, game_2.id], (
        f"game 1 = {game_1.id}, game 2 = {game_2.id}: Gamma 1053347 is timed "
        f"23:05Z and must leave game 1"
    )
    assert _on(session, own) == [game_1.id], "1047825 (20:05Z) is game 1's"
    assert stats["funnel"]["phase15_venue_instant_candidates"] == 2
    assert stats["funnel"]["phase15_venue_instant_relinked"] >= 1


@pytest.mark.asyncio
async def test_strawman_without_the_slice_the_starved_link_is_never_seen():
    """The production defect, reproduced: same rows, same slices, slice emptied —
    the arm never sees 1053347 and it stays on game 1."""
    session, mlb = _new_rail()
    game_1, _game_2, parent, moneyline, _own = _production_specimen(session, mlb)

    stats, spy = await _starved_run(session, slice_enabled=False)

    assert _on(session, parent, moneyline) == [game_1.id, game_1.id]
    spy.assert_not_awaited()
    assert stats["funnel"].get("phase15_venue_instant_relinked", 0) == 0


@pytest.mark.asyncio
async def test_a_starved_kalshi_ticker_still_reaches_the_arm():
    """62013568 (19:05 ET = 23:05Z) leaves game 1 for game 2 under the same
    starvation; the strawman keeps it on game 1."""
    from app.models.models import FuturesMarket

    for enabled, expect_game in ((False, 1), (True, 2)):
        session, mlb = _new_rail()
        game_1 = _anchored(
            session, mlb, GAME_1, "d4b069a134ec3ae75f0a644498b793c6",
            espn_id="401817088",
        )
        game_2 = _anchored(session, mlb, GAME_2, "3fe14d478bc1ffac17198c460085ca70")
        k = FuturesMarket(
            source="kalshi", external_id=TICKER, name="Baltimore vs New York Y",
            category="championship", status="open", event_id=game_1.id,
            sport_id=mlb.id, llm_sport_category="baseball",
        )
        session.add(k)
        _filler(session, mlb)
        session.commit()

        await _starved_run(session, slice_enabled=enabled)

        want = game_1.id if expect_game == 1 else game_2.id
        assert _on(session, k) == [want], (
            f"slice_enabled={enabled}: {TICKER} on {k.event_id}, want {want}"
        )


def _row(market_id, source, external_id, venue, commence, sport_key="baseball_mlb"):
    return (market_id, source, external_id, venue, commence, sport_key)


def test_candidate_ids_are_the_arms_own_predicate():
    """Claimed: PM ≥90 min off, Kalshi ticker ≥90 min off. Not claimed: 89 min,
    no venue instant, a Kalshi ticker on its own game, a non-game ticker."""
    from app.tasks.prediction_market_matching import (
        _phase15_venue_instant_candidate_ids,
    )

    rows = [
        _row(1, "polymarket", "a", "2026-09-25T23:05:00Z", GAME_1),
        _row(2, "polymarket", "b", "2026-09-25T21:34:00Z", GAME_1),  # 89 min
        _row(3, "polymarket", "c", None, GAME_1),
        _row(4, "kalshi", TICKER, None, GAME_1),
        _row(5, "kalshi", TICKER, None, GAME_2),
        _row(6, "kalshi", "KXMLBTOTAL-26SEP251905BALNYY-9", None, GAME_1),
        _row(7, "polymarket", "d", "2026-09-25T21:35:00Z", GAME_1),  # 90 min
    ]
    assert _phase15_venue_instant_candidate_ids(rows) == [1, 4, 7]


def test_candidate_ids_skip_links_on_uncovered_rows():
    """The arm can never move a link off an uncovered row (its finder names only
    covered leagues), so those rows never take the slice — on production they
    were 434 of 439 claimed, sorting ahead of the doubleheader."""
    from app.tasks.prediction_market_matching import (
        _phase15_venue_instant_candidate_ids,
    )

    early = GAME_1 - timedelta(hours=8)
    rows = [
        _row(1, "polymarket", "s", "2026-09-25T15:00:00Z", early, "soccer_other"),
        _row(2, "kalshi", "KXCS2GAME-26SEP250400PHACENT", None, early, "esports"),
        _row(3, "polymarket", "t", "2026-09-25T15:00:00Z", early, "tennis_wta"),
        _row(4, "polymarket", "m", "2026-09-25T23:05:00Z", GAME_1, "baseball_mlb"),
        _row(5, "polymarket", "n", "2026-09-25T23:05:00Z", GAME_1, None),
    ]
    assert _phase15_venue_instant_candidate_ids(rows, limit=1) == [4]


def test_candidate_ids_are_soonest_game_first_and_bounded():
    from app.tasks.prediction_market_matching import (
        _phase15_venue_instant_candidate_ids,
    )

    base = datetime(2026, 9, 26, tzinfo=timezone.utc)
    rows = [
        _row(i, "polymarket", str(i), (base + timedelta(hours=10 - i + 5)).isoformat(),
             base + timedelta(hours=10 - i))
        for i in range(10)
    ]
    assert _phase15_venue_instant_candidate_ids(rows, limit=3) == [9, 8, 7]


def test_the_probe_reads_only_near_term_unfinished_links():
    """The probe's population and its ``->>`` read, executed on the suite's engine."""
    from app.tasks.prediction_market_matching import (
        _phase15_venue_instant_probe_query,
    )

    session, mlb = _new_rail()
    kept = _event(session, mlb, GAME_1)
    live = _event(session, mlb, NOW - timedelta(hours=5), status="in_progress")
    done = _event(session, mlb, GAME_1, status="completed")
    merged = _event(session, mlb, GAME_1, status="merged")
    old = _event(session, mlb, NOW - timedelta(hours=7))
    far = _event(session, mlb, NOW + timedelta(days=3, minutes=1))
    ids = {}
    for label, ev in (("kept", kept), ("live", live), ("done", done),
                      ("merged", merged), ("old", old), ("far", far)):
        ids[label] = _pm(
            session, ev, pm_event_id=label, venue_start=GAME_2,
            external_id=label, group_type="polymarket_event",
        ).id
    session.commit()

    rows = session.execute(_phase15_venue_instant_probe_query(NOW)).all()

    assert sorted(r[0] for r in rows) == sorted([ids["kept"], ids["live"]])
    assert {r[3] for r in rows} == {"2026-09-25T23:05:00Z"}
