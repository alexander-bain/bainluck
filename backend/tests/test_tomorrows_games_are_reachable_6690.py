"""#6690 — the evening feed can reach tomorrow's games, and the quota stops
cutting the ones kicking off next.

Measured on production 2026-09-16 04:15Z: ``GET /api/feed?mode=sports&limit=200``
served 26 event cards of which **zero** were ``scheduled``, and the web
"Upcoming" rail held nine UFC concepts and a golf tournament — not one game.
Thursday night's NFL game was 20.0h out and the nearest marquee kickoff 12.3h
out, against a 12-hour candidate window.

Two independent defects produced that, and each needs its own guard because
either one alone still empties the rail:

1. **The window.** ``scheduled`` rows were admitted only inside 12h, so in the
   evening no North-American game was a candidate at all.
2. **The quota's ordering.** The scheduled tier was row-numbered
   ``commence_time DESC`` — correct for the past-facing tiers, backwards for a
   tier whose rows are all in the future — so the rows the 150-slot quota
   discarded were the *most imminent* games.

Both are executed against a real engine over a corpus shaped like that slate,
and both carry a red-first control that builds the pre-fix behaviour and shows
it failing, so the corpus is proven to exercise the bug rather than merely
coexist with it (the idiom of ``test_feed_event_candidates.py``).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import and_, case, create_engine, func, or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.routes.feed import (  # noqa: E402
    MARQUEE_UPCOMING_WINDOW_HOURS,
    MY_STUFF_ALLOWED_SPORT_KEYS,
)
from app.utils.feed_event_candidates import (  # noqa: E402
    TIER_QUOTAS,
    TIER_SCHEDULED,
    candidate_window_conditions,
    event_candidate_ids,
    status_tier_expr,
)

# 9:15 PM Pacific — the hour the defect was measured, and the hour a reader
# actually opens the app to see what is on tomorrow.
NOW = datetime(2026, 9, 17, 4, 15, 0, tzinfo=timezone.utc)

S_NFL = 1
S_MLB = 2
S_TENNIS = 3

_SPORTS = [
    (S_NFL, "americanfootball_nfl", "NFL"),
    (S_MLB, "baseball_mlb", "MLB"),
    # Deliberately NOT in `MY_STUFF_ALLOWED_SPORT_KEYS`: the ITF/challenger mass
    # that fills the window and is discarded downstream at `min_score`.
    (S_TENNIS, "tennis_other", "Tennis"),
]

NFL_ID = 10           # Lions @ Bills — 20.0h out, the game Alex could not find
MLB_ID = 11           # 19.8h out
MLB_IMMINENT_ID = 12  # 2h out — the row the old DESC ordering cut first
TENNIS_NEAR_ID = 20   # 6h out, inside the original window
TENNIS_FAR_ID = 21    # 20h out, outside it and meant to STAY outside
FLOOD_ID_BASE = 100_000


def _event(id, sport_id, hours_out, status="scheduled"):
    return Event(
        id=id,
        sport_id=sport_id,
        home_team_name=f"Home {id}",
        away_team_name=f"Away {id}",
        commence_time=NOW + timedelta(hours=hours_out),
        status=status,
        win_probability_sources={"betting": {"value": 0.5}},
    )


def _seed(session, rows):
    for sid, key, name in _SPORTS:
        session.add(Sport(id=sid, key=key, name=name))
    for row in rows:
        session.add(row)
    session.commit()


def _slate():
    """The measured slate: a marquee next-day card behind a wall of tennis."""
    return [
        _event(NFL_ID, S_NFL, 20.0),
        _event(MLB_ID, S_MLB, 19.8),
        _event(MLB_IMMINENT_ID, S_MLB, 2.0),
        _event(TENNIS_NEAR_ID, S_TENNIS, 6.0),
        _event(TENNIS_FAR_ID, S_TENNIS, 20.0),
    ]


def _conditions(now=NOW, marquee=True):
    """The predicate the route builds — the SAME function, not a copy of it."""
    return candidate_window_conditions(
        now=now,
        live_start_cutoff=now + timedelta(hours=1),
        upcoming_cutoff=now + timedelta(hours=12),
        recent_cutoff=now - timedelta(hours=24),
        marquee_upcoming_cutoff=(
            now + timedelta(hours=MARQUEE_UPCOMING_WINDOW_HOURS)
            if marquee
            else None
        ),
        marquee_sport_keys=MY_STUFF_ALLOWED_SPORT_KEYS if marquee else (),
    )


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng, tables=[Sport.__table__, Event.__table__])
    return eng


def _admitted(session, conditions, marquee=True):
    stmt = event_candidate_ids(
        conditions, MY_STUFF_ALLOWED_SPORT_KEYS if marquee else ()
    )
    return {r[0] for r in session.execute(stmt).all()}


# ─────────────────────────── 1. the window ────────────────────────────


def test_tomorrow_nights_nfl_game_is_a_candidate(engine):
    """The ship, stated as the reader's sentence: the game is reachable."""
    with Session(engine) as s:
        _seed(s, _slate())
        admitted = _admitted(s, _conditions())
    assert NFL_ID in admitted, "Lions @ Bills (20.0h out) is not a candidate"
    assert MLB_ID in admitted


def test_the_defect_reproduces_without_the_marquee_arm(engine):
    """Red-first: the same corpus under the one-armed 12h predicate.

    Without this the test above proves only that a row 20h out can be selected
    by *some* query, not that the old one refused it.
    """
    with Session(engine) as s:
        _seed(s, _slate())
        admitted = _admitted(s, _conditions(marquee=False), marquee=False)
    assert NFL_ID not in admitted
    assert MLB_ID not in admitted
    # …and the rail really was gameless for the next day, not merely thinner.
    assert not {
        e for e in admitted if e in (NFL_ID, MLB_ID, TENNIS_FAR_ID)
    }


def test_the_widening_is_scoped_and_is_not_a_blanket_window(engine):
    """A non-marquee fixture 20h out stays out; one 6h out stays in.

    This is the assertion that stops the fix becoming "look 36h ahead for
    everything", which is the version that spends the candidate budget on rows
    the feed discards downstream and starves the games it is meant to carry.
    """
    with Session(engine) as s:
        _seed(s, _slate())
        admitted = _admitted(s, _conditions())
    assert TENNIS_FAR_ID not in admitted, "the widening leaked to every sport"
    assert TENNIS_NEAR_ID in admitted, "the original 12h window was narrowed"


def test_my_teams_only_is_untouched(engine):
    """The 7-day branch passes no marquee cutoff, so the predicate is the old one.

    Its window is already wider than the marquee one for *every* sport, so the
    arm would be a no-op there at best and a narrowing at worst.
    """
    with Session(engine) as s:
        _seed(s, _slate())
        conditions = candidate_window_conditions(
            now=NOW,
            live_start_cutoff=NOW + timedelta(hours=1),
            upcoming_cutoff=NOW + timedelta(days=7),
            recent_cutoff=NOW - timedelta(hours=72),
        )
        admitted = _admitted(s, conditions, marquee=False)
    # Every scheduled row in the corpus is inside 7 days, marquee or not.
    assert {NFL_ID, MLB_ID, MLB_IMMINENT_ID, TENNIS_NEAR_ID, TENNIS_FAR_ID} <= admitted


# ──────────────────────── 2. the quota's ordering ─────────────────────────


def _flooded_slate():
    """The real shape: more in-window fixtures than the scheduled tier has slots.

    Production held 170 scheduled rows against a quota of 150 on the night this
    was measured — the module's own comment records 96 when the quota was
    written, so it was inert then and is not now.
    """
    rows = _slate()
    # Enough that MORE THAN a full quota of fixtures start *after* the imminent
    # 2h game — which is what it takes for a DESC ordering to cut that game, and
    # therefore what it takes for the red-first control below to mean anything.
    # Sized deliberately rather than nudged: at quota+10 the flood was 165 rows
    # and only ~140 of them fell later than the 2h game, so the old ordering
    # kept it and the control passed while proving nothing.
    over = TIER_QUOTAS[TIER_SCHEDULED] + 50
    for i in range(over):
        # Spread across the original 12h window so they all legitimately qualify.
        rows.append(
            _event(FLOOD_ID_BASE + i, S_TENNIS, 0.5 + (i * 11.0 / over))
        )
    return rows


def test_a_flood_of_fixtures_cannot_cut_tomorrows_marquee_games(engine):
    """160 in-window fixtures do not push the NFL game out of a 150-slot tier."""
    with Session(engine) as s:
        _seed(s, _flooded_slate())
        admitted = _admitted(s, _conditions())
    assert NFL_ID in admitted
    assert MLB_ID in admitted
    assert MLB_IMMINENT_ID in admitted


def test_the_quota_cuts_the_furthest_fixture_and_never_the_imminent(engine):
    """Among non-marquee rows the survivors are the soonest, not the furthest.

    Both directions, per gotcha #43: the cut really binds (something IS
    dropped), and what it drops is the far tail rather than the next kickoff.
    """
    with Session(engine) as s:
        _seed(s, _flooded_slate())
        admitted = _admitted(s, _conditions())
        times = dict(
            s.execute(
                select(Event.id, Event.commence_time).where(
                    Event.id >= FLOOD_ID_BASE
                )
            ).all()
        )
    kept = {i for i in admitted if i >= FLOOD_ID_BASE}
    dropped = set(times) - kept
    assert dropped, "the quota never bound — the corpus does not exercise it"
    assert max(times[i] for i in kept) <= min(times[i] for i in dropped), (
        "a fixture kicking off sooner was cut in favour of a later one"
    )


def test_the_old_ordering_cut_the_imminent_games(engine):
    """Red-first for the ordering half: `commence_time DESC` drops the next game.

    Builds the pre-fix ranked pass over the same corpus. If this ever stops
    failing to keep `MLB_IMMINENT_ID`, the corpus has drifted and the guard
    above is no longer holding anything up.
    """
    with Session(engine) as s:
        _seed(s, _flooded_slate())
        collapsed = (
            select(
                Event.id.label("id"),
                status_tier_expr().label("tier"),
                Event.commence_time.label("commence_time"),
            )
            .select_from(Event)
            .join(Sport, Event.sport_id == Sport.id)
            .where(and_(*_conditions()))
            .subquery("old_collapsed")
        )
        ranked = select(
            collapsed.c.id,
            func.row_number()
            .over(
                partition_by=collapsed.c.tier,
                order_by=collapsed.c.commence_time.desc(),
            )
            .label("tier_rn"),
        ).subquery("old_ranked")
        old = {
            r[0]
            for r in s.execute(
                select(ranked.c.id).where(
                    ranked.c.tier_rn <= TIER_QUOTAS[TIER_SCHEDULED]
                )
            ).all()
        }
    assert MLB_IMMINENT_ID not in old, (
        "the old DESC ordering kept the imminent game — corpus no longer "
        "reproduces the defect"
    )


# ─────────────────── 3. inertness outside the scheduled tier ───────────────────


def test_the_past_facing_tiers_rank_exactly_as_before(engine):
    """live / recent / suspended still rank `commence_time DESC`.

    The new keys are constant (`marquee_rank`) and NULL (`scheduled_time`) for
    every row outside the scheduled tier, and `row_number` only compares rows
    inside one partition — so this is a structural claim, not a lucky corpus.
    It is asserted anyway because "cannot vary" is exactly the kind of statement
    that stops being true when a fourth tier is added.
    """
    rows = []
    for i in range(6):
        rows.append(_event(200 + i, S_MLB, -1.0 - i, status="completed"))
        rows.append(_event(300 + i, S_MLB, -0.5 - i, status="live"))
    with Session(engine) as s:
        _seed(s, rows)
        with_marquee = _admitted(s, _conditions(), marquee=True)
        without = _admitted(s, _conditions(), marquee=False)
    assert with_marquee == without
    assert len(with_marquee) == 12


class _StopHere(Exception):
    """Sentinel: the route reached the predicate, which is all we are asking."""


@pytest.mark.asyncio
async def test_the_route_actually_passes_the_marquee_window(monkeypatch):
    """The wiring, not the util — without this every test above stays green
    while the route forgets to pass the argument.

    Every other test in this module hands ``candidate_window_conditions`` its
    arguments directly, so they measure the predicate and say nothing about the
    caller. That is the gap the fix could regress through silently: delete both
    keyword arguments at the call site and the util keeps its default-off
    behaviour, the nine tests above keep passing, and the feed goes back to
    12 hours. So this one reaches into ``_score_events`` and reads what the
    route asked for.
    """
    import app.routes.feed as feed_mod

    seen = {}

    def _capture(**kwargs):
        seen.update(kwargs)
        raise _StopHere

    monkeypatch.setattr(feed_mod, "candidate_window_conditions", _capture)

    with pytest.raises(_StopHere):
        await feed_mod._score_events(
            db=None,
            now=NOW,
            sport_filter=None,
            ctx=feed_mod.PersonalizationContext(),
            my_teams_only=False,
        )

    assert seen["marquee_upcoming_cutoff"] == NOW + timedelta(
        hours=MARQUEE_UPCOMING_WINDOW_HOURS
    )
    assert seen["marquee_sport_keys"] is MY_STUFF_ALLOWED_SPORT_KEYS
    # The original window is passed alongside it, not replaced by it.
    assert seen["upcoming_cutoff"] == NOW + timedelta(hours=12)


@pytest.mark.asyncio
async def test_the_route_leaves_my_teams_only_on_the_old_predicate(monkeypatch):
    """My Stuff's 7-day window passes no marquee cutoff — asserted at the call
    site for the same reason as above."""
    import app.routes.feed as feed_mod

    seen = {}

    def _capture(**kwargs):
        seen.update(kwargs)
        raise _StopHere

    monkeypatch.setattr(feed_mod, "candidate_window_conditions", _capture)

    with pytest.raises(_StopHere):
        await feed_mod._score_events(
            db=None,
            now=NOW,
            sport_filter=None,
            ctx=feed_mod.PersonalizationContext(),
            my_teams_only=True,
        )

    assert seen["marquee_upcoming_cutoff"] is None
    assert seen["upcoming_cutoff"] == NOW + timedelta(days=7)


def test_the_statement_compiles_against_postgres(engine):
    """SQLite agreeing is not Postgres agreeing — the module's standing rule."""
    stmt = event_candidate_ids(_conditions(), MY_STUFF_ALLOWED_SPORT_KEYS)
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "row_number() OVER" in sql
    assert "PARTITION BY" in sql
    # The scheduled keys lead the window ordering, DESC trails it.
    assert sql.index("marquee_rank") < sql.index("commence_time DESC")
