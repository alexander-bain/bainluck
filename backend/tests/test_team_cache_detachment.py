"""#2107 — the module-global team cache must never hold live ORM rows.

WHAT BROKE, because the shape of it is the whole reason this file exists.

`_build_team_lookup` cached live `Team` instances in the module globals
`_team_cache` / `_team_cache_time`. Those instances belong to the session of
whichever request happened to populate the cache. An async rollback anywhere
on that session EXPIRES every object it owns (gotcha #6), and closing it
DETACHES them — so the next read of `team.primary_color` raises
`DetachedInstanceError` instead of returning a colour.

Because the cache is process-global, that is not one bad request. ONE rollback
poisoned every subsequent `/api/feed` on that dyno until the 5-minute TTL
rebuilt the cache, and the rebuild was one rollback away from being poisoned
again. Production read 10-for-10 500s on 2026-08-22 with no deploy behind it,
~50% presentation across two dynos, which looked like flakiness rather than
like a total outage of the default landing page.

WHAT THESE TESTS PIN, and the order matters:

1. That the hazard is still real — every test that claims "no 500 after a
   rollback" first proves, on the same objects, that reading the ORM row DOES
   still raise. Without that arm the test would keep passing if SQLAlchemy
   ever stopped expiring on rollback, and would then be asserting nothing.
2. That nothing which outlives a request holds an ORM row.
3. That the cached value is immutable and privately owned, since a shared
   mutable global is the same bug with different symptoms.

The rollback is performed on a real `sqlalchemy.orm.Session`, unbound: expiry
and detachment are pure identity-map operations and need no database, so this
runs in the sandbox (see the no-local-Postgres constraint) while still using
the genuine SQLAlchemy machinery rather than a hand-made stand-in.
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.orm import Session, make_transient_to_detached
from sqlalchemy.orm.exc import DetachedInstanceError

from app.models.models import Team
from app.routes import events as events_module
from app.routes.events import (
    TeamSnapshot,
    _build_team_lookup,
    _compute_standings_context,
    _format_team_data,
)


def _team(**over) -> Team:
    """A Team row shaped the way `_build_team_lookup`'s query returns them."""
    fields = {
        "id": 1,
        "sport_id": 10,
        "name": "Carolina Panthers",
        "slug": "carolina-panthers",
        "abbreviation": "CAR",
        "primary_color": "#0085CA",
        "secondary_color": "#101820",
        "logo_url_small": "https://example.test/car-small.png",
        "logo_url_large": "https://example.test/car-large.png",
        "current_record": "9-8",
        "alternate_names": ["Panthers"],
        "standings_data": {"wins": 9, "losses": 8, "conf_rank": 3, "conference": "NFC"},
        "season_stats": {"ppg": 21.4},
    }
    fields.update(over)
    return Team(**fields)


def _persistent(teams: list[Team]) -> Session:
    """Put rows into a real session as PERSISTENT, without touching a database.

    `make_transient_to_detached` gives each row an identity key; `Session.add`
    on a detached row re-attaches it as persistent. From there `rollback()`
    and `close()` behave exactly as they do behind a real engine — which is
    the point: the failure mode under test is an identity-map behaviour, not
    an I/O one.
    """
    session = Session()
    for row in teams:
        make_transient_to_detached(row)
        session.add(row)
    return session


def _db_returning(teams: list[Team]) -> AsyncMock:
    """An async DB session whose one `execute` yields these rows."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = teams
    db = AsyncMock()
    db.execute.return_value = result
    return db


@pytest.fixture(autouse=True)
def _isolated_team_cache():
    """The cache is a module global; leaving it dirty leaks across the suite.

    This is the same reason `test_route_league_futures.py` resets it — a
    process-wide cache makes whether a later test hits the database depend on
    test ORDER, which is precisely the kind of thing that gets diagnosed as a
    flake in some unrelated file.
    """
    events_module._team_cache = {}
    events_module._team_cache_time = 0.0
    yield
    events_module._team_cache = {}
    events_module._team_cache_time = 0.0


async def test_a_rollback_on_the_populating_session_does_not_500_later_requests():
    """The #2107 reproduction, end to end: poison, then serve.

    Pre-fix this raised `DetachedInstanceError` out of `_format_team_data`,
    which is a 500 on `/api/feed` — the default landing page — for every
    request until the TTL expired.
    """
    rows = [_team()]
    session = _persistent(rows)

    # Request 1 populates the process-global cache off this session's rows.
    lookup = await _build_team_lookup(_db_returning(rows), ["Carolina Panthers"])
    assert "Carolina Panthers" in lookup

    # The poisoning event. `rollback()` expires every object the session owns;
    # `close()` detaches them. Nothing else about the process changes.
    session.rollback()
    session.close()

    # ARM 1 — the hazard is still real. If this stops raising, the assertions
    # below stop meaning anything, and the test must fail loudly rather than
    # keep reporting green over a check that evaporated.
    with pytest.raises(DetachedInstanceError):
        _ = rows[0].primary_color

    # ARM 2 — request 2 lands on the still-warm cache (a fresh DB that would
    # raise if touched, so a silent cache MISS cannot be mistaken for a pass)
    # and formats a full card without a session in sight.
    exploding_db = AsyncMock()
    exploding_db.execute.side_effect = AssertionError(
        "cache MISS — this test must exercise the cached path, not a rebuild"
    )
    cached = await _build_team_lookup(exploding_db, ["Carolina Panthers"])

    data = _format_team_data(cached["Carolina Panthers"])
    assert data["primary_color"] == "#0085CA"
    assert data["logo_small"] == "https://example.test/car-small.png"
    assert data["record"] == "9-8"
    assert data["abbreviation"] == "CAR"
    assert data["slug"] == "carolina-panthers"
    assert data["standings"]["wins"] == 9
    assert data["season_stats"]["ppg"] == 21.4


async def test_standings_context_also_survives_the_rollback():
    """`_compute_standings_context` reads the same rows on the event page.

    The Sentry trace named `_format_team_data`, but the event-detail route
    hands the SAME lookup values to `_compute_standings_context` two calls
    later. Fixing only the frame that happened to appear in the traceback
    would leave the second consumer one rollback from the same 500.
    """
    rows = [
        _team(),
        _team(
            id=2,
            name="Atlanta Falcons",
            slug="atlanta-falcons",
            abbreviation="ATL",
            alternate_names=["Falcons"],
            standings_data={"wins": 8, "losses": 9, "conf_rank": 2, "conference": "NFC"},
        ),
    ]
    session = _persistent(rows)

    lookup = await _build_team_lookup(
        _db_returning(rows), ["Carolina Panthers", "Atlanta Falcons"]
    )

    session.rollback()
    session.close()

    with pytest.raises(DetachedInstanceError):
        _ = rows[0].standings_data

    context = _compute_standings_context(
        lookup.get("Carolina Panthers"),
        lookup.get("Atlanta Falcons"),
        "Carolina Panthers",
        "Atlanta Falcons",
    )
    assert context is not None
    assert context["home"].startswith("9-8")
    assert context["away"].startswith("8-9")
    assert context["stakes"] == "Top seed matchup"


async def test_the_next_requests_recover_through_the_real_feed_reader():
    """The poisoning was PROCESS-WIDE and self-sustaining — pin recovery, not survival.

    Fable's addendum names the distinction this test exists for: proving that
    *one* request survived a rollback is not the claim. The claim is that the
    NEXT requests recover, on a cache that a different request populated, read
    by the frame that actually 500'd in production — `feed.py`'s
    `enrich_event_team_data`, not the events route that owns the cache.

    Two properties are pinned here that the single-request tests cannot see:

    * **Cross-module.** The writer is `routes/events.py`; the reader is
      `routes/feed.py`. The bug lived in the gap.
    * **Not self-sustaining.** The TTL rebuild was itself one rollback from
      being re-poisoned, so this walks a rollback, four requests, a TTL
      expiry, a REBUILD off a second session, another rollback, and four more
      requests. A fix that merely shortened the poisoned window would pass a
      one-request test and fail this one.

    Note on the mechanism, since it is the reason `commit` never showed up in
    the incident: sessions run `expire_on_commit=False`, so a commit leaves
    the cached rows readable. Only ROLLBACK expires them. A reproduction built
    on commit would be green forever against a live P0.
    """
    from app.routes.feed import enrich_event_team_data

    def _feed_items() -> list[dict]:
        return [
            {
                "type": "event",
                "data": {"home_team": "Carolina Panthers", "away_team": "Atlanta Falcons"},
            }
        ]

    rows = [
        _team(),
        _team(id=2, name="Atlanta Falcons", abbreviation="ATL", alternate_names=["Falcons"]),
    ]
    session = _persistent(rows)

    # Request 1 — the writer. Populates the process-global cache.
    await _build_team_lookup(_db_returning(rows), ["Carolina Panthers"])

    session.rollback()
    session.close()

    with pytest.raises(DetachedInstanceError):
        _ = rows[0].primary_color

    exploding_db = AsyncMock()
    exploding_db.execute.side_effect = AssertionError(
        "cache MISS — these requests must be served from the poisoned-era cache"
    )

    # Requests 2-5 — the reader, four consecutive times off the same cache.
    for attempt in range(4):
        items = _feed_items()
        await enrich_event_team_data(exploding_db, items)
        data = items[0]["data"]
        assert data["home_team_data"]["primary_color"] == "#0085CA", (
            f"request {attempt + 2} lost team media"
        )
        assert data["away_team_data"]["logo_small"]

    # The TTL lapses and a SECOND session rebuilds the cache — the step that
    # used to hand the next rollback a fresh set of victims.
    #
    # Age the anchor, do NOT zero it. `_build_team_lookup` measures freshness
    # with `time.monotonic()`, which on Linux is SECONDS SINCE BOOT, and its
    # guard is `(now - _team_cache_time) < _TEAM_CACHE_TTL`. Writing 0.0 here
    # says "cached at boot", which only reads as EXPIRED on a machine whose
    # uptime already exceeds the 300s TTL. It does on a laptop that has been up
    # for days; it does not on a freshly-booted CI runner, where the cache
    # stays FRESH, no rebuild happens, and requests 6-9 see the pre-rebuild
    # colour. That is exactly how this passed locally and failed on CI at
    # `fe28d2c3` (INT-112). Offset first, then use — gotcha #44.
    #
    # The two other resets in this file, and the one in
    # `test_route_league_futures.py`, are safe as 0.0 because they also empty
    # `_team_cache`, and the guard short-circuits on a falsy cache.
    events_module._team_cache_time = (
        time.monotonic() - events_module._TEAM_CACHE_TTL - 1
    )
    rebuilt_rows = [
        _team(primary_color="#111111"),
        _team(id=2, name="Atlanta Falcons", abbreviation="ATL", alternate_names=["Falcons"]),
    ]
    second_session = _persistent(rebuilt_rows)
    await _build_team_lookup(_db_returning(rebuilt_rows), ["Carolina Panthers"])

    second_session.rollback()
    second_session.close()

    with pytest.raises(DetachedInstanceError):
        _ = rebuilt_rows[0].primary_color

    # Requests 6-9 — after the re-poisoning of the rebuilt cache.
    for attempt in range(4):
        items = _feed_items()
        await enrich_event_team_data(exploding_db, items)
        assert items[0]["data"]["home_team_data"]["primary_color"] == "#111111", (
            f"request {attempt + 6} lost team media after the TTL rebuild"
        )


async def test_the_module_cache_holds_no_orm_rows_at_all():
    """The class-closing assertion, not the instance-closing one.

    `_format_team_data` surviving a rollback is the symptom being fixed. This
    is the invariant: if a future edit puts a `Team` back in the cache, the
    500 comes back whether or not the two tests above still pass, because they
    only cover the consumers that exist today.
    """
    rows = [_team(), _team(id=2, name="Atlanta Falcons", alternate_names=["Falcons"])]
    await _build_team_lookup(_db_returning(rows), ["Carolina Panthers"])

    assert events_module._team_cache, "cache should have been populated"
    for key, value in events_module._team_cache.items():
        assert isinstance(value, TeamSnapshot), (
            f"cache entry {key!r} is {type(value).__name__}, not a TeamSnapshot"
        )
        assert not isinstance(value, Team), (
            f"cache entry {key!r} is a live ORM row — this is #2107 restored"
        )


async def test_the_cached_snapshot_is_frozen_and_privately_owned():
    """A process-global that any request can mutate is the same bug, reworn.

    Two ways in, both closed: the snapshot itself is frozen, and its JSONB
    payloads are deep copies, so a route that mutates `response["standings"]`
    in place cannot reach into the shared cache.
    """
    source_standings = {"wins": 9, "losses": 8}
    rows = [_team(standings_data=source_standings)]
    lookup = await _build_team_lookup(_db_returning(rows), ["Carolina Panthers"])
    snapshot = lookup["Carolina Panthers"]

    with pytest.raises(Exception):  # FrozenInstanceError
        snapshot.primary_color = "#FFFFFF"

    # The snapshot does not alias the row's JSONB, in either direction.
    assert snapshot.standings_data is not source_standings
    source_standings["wins"] = 999
    assert snapshot.standings_data["wins"] == 9

    # And a consumer mutating what it was handed cannot corrupt the cache.
    data = _format_team_data(snapshot)
    data["standings"]["wins"] = -1
    assert events_module._team_cache["Carolina Panthers"].standings_data["wins"] == 9


@pytest.mark.parametrize(
    ("column", "response_key"),
    [
        ("standings_data", "standings"),
        ("season_stats", "season_stats"),
    ],
)
async def test_every_jsonb_payload_is_copied_out_not_handed_out(column, response_key):
    """C-2107-R1 P3, closed — and PARAMETRIZED, which is the actual fix.

    🔴 `_format_team_data` deep-copied `standings_data` and handed
    `season_stats` out by reference, while its own docstring said "the JSONB
    payloads are copied on the way out" — plural. That is the most durable way
    for a defect to survive review: the prose a reader checks the code against
    already claims the fix, so the reader confirms the claim and moves on. The
    test above did the same thing, asserting the copy on exactly the one field
    that had it.

    The escape was narrow. `TeamSnapshot` deep-copies at BUILD time, so there
    was one private dict per cache entry rather than an alias of the ORM row —
    but that single dict was then handed to every request for the entry's whole
    lifetime, and a per-request response dict is the one object a caller feels
    entitled to edit in place. Narrow is not absent.

    Parametrized over the columns rather than written twice, so a THIRD JSONB
    column added to `TeamSnapshot` fails the sibling test below until it is
    listed here. A guard that has to be remembered is not a guard.
    """
    source = {"canary": 1}
    rows = [_team(**{column: source})]
    lookup = await _build_team_lookup(_db_returning(rows), ["Carolina Panthers"])
    snapshot = lookup["Carolina Panthers"]

    # BUILD time: the snapshot does not alias the ORM row's dict.
    assert getattr(snapshot, column) is not source
    source["canary"] = 999
    assert getattr(snapshot, column)["canary"] == 1

    # HAND-OUT time: two requests must not share one dict, and mutating what
    # either was handed must not reach the cache.
    first = _format_team_data(snapshot)
    second = _format_team_data(snapshot)
    assert first[response_key] is not second[response_key], (
        f"{response_key} is handed out by reference — every request that "
        "formats this team shares one dict with the process-global cache"
    )

    first[response_key]["canary"] = -1
    assert getattr(events_module._team_cache["Carolina Panthers"], column)["canary"] == 1
    assert second[response_key]["canary"] == 1


async def test_the_jsonb_copy_guard_covers_every_jsonb_column_on_the_snapshot():
    """The guard above is only as complete as its parameter list.

    `season_stats` was missed for exactly this reason — it existed, it was
    JSONB, and nothing forced anyone to notice it was uncovered. This asserts
    the parameter list against the dataclass itself, so a new JSONB column turns
    the suite red instead of quietly shipping uncopied.
    """
    import dataclasses

    from app.routes.events import TeamSnapshot

    jsonb_fields = {
        f.name
        for f in dataclasses.fields(TeamSnapshot)
        if "dict" in str(f.type)
    }
    covered = {"standings_data", "season_stats"}
    assert jsonb_fields == covered, (
        f"TeamSnapshot's JSONB columns are {sorted(jsonb_fields)} but the copy "
        f"guard covers {sorted(covered)} — add the new column to "
        "`test_every_jsonb_payload_is_copied_out_not_handed_out` and make sure "
        "`_format_team_data` copies it"
    )
