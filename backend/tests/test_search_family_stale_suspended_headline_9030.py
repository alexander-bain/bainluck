"""#9030 — a game suspended days ago stops heading a search family.

WHAT THE READER SAW. `https://bainluck.com/search?q=eagles` at 390px,
2026-09-27 03:2xZ, production `b4b1a076`. ANSWERS card "EAGLES", row 1:

    Tohoku Rakuten Golden Eagles vs. Fukuoka SoftBank Hawks          Yes 41%

— an NPB game (61045496) linked to event 15312538, `status='suspended'`,
`commence_time 2026-09-21 04:00Z`, price frozen since that day. The TEAMS row
above it leads with the Philadelphia Eagles.

THE MECHANISM. `_family_headline_index` (#7261) scans the family's ranked order
for the first member that answers its own question. The three Eagles–Bears
members above the NPB game are bundles (O/U, spread, total ladders) and are
correctly skipped; nothing asked whether the next one's game was long past.

THE FIX. A stable partition before that scan: members whose game is `suspended`
and started more than `STALE_SUSPENDED_GAME_HOURS` ago go last. Nothing is
dropped; the pool filter (#4914, which keeps `suspended` on purpose) is untouched.

RED-FIRST. Delete the partition in `_compose_futures_families` and
`TestTheEaglesSpecimen` fails on the headline name.
"""

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from app.routes import events as events_module
from app.routes.events import (
    STALE_SUSPENDED_GAME_HOURS,
    _compose_futures_families,
    _search_stale_game_market_ids,
)


UTC = timezone.utc
NOW = datetime(2026, 9, 27, 3, 20, tzinfo=UTC)  # the specimen's read, fixed


def _outcome(name, prob, oid):
    """Shaped to survive `_search_surviving_legs` (distinct id, real book)."""
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=f"leg-{oid}",
        current_probability=prob,
        current_odds=None,
        current_american_odds=None,
        current_yes_bid=max(0.01, prob - 0.02),
        current_yes_ask=min(0.99, prob + 0.02),
        previous_probability=None,
        is_winner=None,
        rank=None,
        team_id=None,
    )


def _market(mid, name, legs, *, event_id=None):
    return SimpleNamespace(
        id=mid,
        name=name,
        external_id=f"PM-{mid}",
        llm_sport_category="football",
        category="game_prop",
        market_tier=5,
        market_type="prop",
        sport=None,
        sport_id=None,
        source="polymarket",
        volume=0.0,
        status="open",
        mutually_exclusive=False,
        resolution_date=(NOW + timedelta(days=2)).date(),
        updated_at=NOW,
        canonical_market_key=None,
        image_url=None,
        hook_description=None,
        group_id=None,
        event_id=event_id,
        outcomes=[_outcome(n, p, mid * 100 + i) for i, (n, p) in enumerate(legs)],
    )


BEARS_OU = 59148955
BEARS_SPREAD = 61880780
BEARS_TOTAL = 61880781
NPB = 61045496
GIANTS_SERIES = 56722518
COWBOYS_SERIES = 56722502
COMMANDERS_SERIES = 56722519


def _eagles_family():
    """The served family's first seven members, in served order."""
    return [
        _market(BEARS_OU, "Eagles vs. Bears",
                [("O/U 24.5", 0.93), ("Eagles O/U 10.5", 0.91), ("O/U 26.5", 0.90)]),
        _market(BEARS_SPREAD, "PHI Eagles vs CHI Bears: Spread",
                [("PHI Eagles wins by over 1.5", 0.60),
                 ("PHI Eagles wins by over 2.5", 0.585),
                 ("PHI Eagles wins by over 3.5", 0.485),
                 ("PHI Eagles wins by over 4.5", 0.44)]),
        _market(BEARS_TOTAL, "PHI Eagles vs CHI Bears: Total Points",
                [("Over 35.5", 0.705), ("Over 38.5", 0.61), ("Over 41.5", 0.515),
                 ("Over 44.5", 0.40)]),
        _market(NPB, "Tohoku Rakuten Golden Eagles vs. Fukuoka SoftBank Hawks",
                [("Yes", 0.41)], event_id=15312538),
        _market(GIANTS_SERIES, "NFL: Eagles vs. Giants Season Series Winner",
                [("Tie", 0.42), ("Eagles", 0.395), ("Giants", 0.006)]),
        _market(COWBOYS_SERIES, "NFL: Cowboys vs. Eagles Season Series Winner",
                [("Tie", 0.37), ("Eagles", 0.30), ("Cowboys", 0.21)]),
        _market(COMMANDERS_SERIES, "NFL: Eagles vs. Commanders Season Series Winner",
                [("Eagles", 0.875), ("Tie", 0.01), ("Commanders", 0.0)]),
    ]


def _fmt(m):
    return {"id": m.id, "name": m.name}


def _compose(markets, **kw):
    return _compose_futures_families(
        markets, [("eagles", None)], _fmt, {m.id for m in markets}, **kw
    )


def _shown_ids(fam):
    return [fam["headline"]["id"]] + [m["id"] for m in fam["members"]]


class TestTheEaglesSpecimen:
    def test_without_the_stale_set_the_npb_game_heads_it(self):
        """The BEFORE, reproduced: proves the fixture is the specimen."""
        (fam,) = _compose(_eagles_family())
        assert fam["headline"]["id"] == NPB

    def test_a_long_suspended_game_no_longer_heads_the_card(self):
        (fam,) = _compose(_eagles_family(), stale_game_ids={NPB})
        assert fam["headline"]["id"] == GIANTS_SERIES
        assert NPB not in _shown_ids(fam)

    def test_nothing_is_dropped(self):
        (fam,) = _compose(_eagles_family(), stale_game_ids={NPB})
        assert fam["member_count"] == 7
        assert fam["more_count"] == 2  # COMMANDERS_SERIES and the NPB game, below

    def test_the_other_members_keep_their_order(self):
        (fam,) = _compose(_eagles_family(), stale_game_ids={NPB})
        assert [m["id"] for m in fam["members"]] == [
            BEARS_OU, BEARS_SPREAD, BEARS_TOTAL, COWBOYS_SERIES,
        ]


class TestControls:
    def test_empty_stale_set_is_byte_identical_to_the_default(self):
        assert _compose(_eagles_family(), stale_game_ids=set()) == _compose(
            _eagles_family()
        )

    def test_an_all_stale_family_keeps_its_order(self):
        fam_ids = {m.id for m in _eagles_family()}
        assert _compose(_eagles_family(), stale_game_ids=fam_ids) == _compose(
            _eagles_family()
        )

    def test_a_stale_id_outside_the_family_changes_nothing(self):
        assert _compose(_eagles_family(), stale_game_ids={999}) == _compose(
            _eagles_family()
        )


# ==========================================================================
# The stale set, asked of a real SQL engine (the WHERE clause is the rule).
# ==========================================================================


def _ts(dt):
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


class _SyncBackedDB:
    """The helper's own statement, executed by stdlib SQLite (no aiosqlite here)."""

    def __init__(self, conn):
        self.conn = conn

    async def execute(self, stmt):
        return self.conn.execute(stmt)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE events (id INTEGER PRIMARY KEY, status VARCHAR(20), "
            "commence_time DATETIME)"
        ))
        rows = [
            (15312538, "suspended", NOW - timedelta(days=6)),       # the specimen
            (2, "suspended", NOW - timedelta(hours=STALE_SUSPENDED_GAME_HOURS - 1)),
            (3, "live", NOW - timedelta(days=6)),
            (4, "scheduled", NOW - timedelta(days=6)),
            (5, "suspended", NOW + timedelta(days=1)),
        ]
        for eid, status, ct in rows:
            conn.execute(
                text("INSERT INTO events VALUES (:i, :s, :c)"),
                {"i": eid, "s": status, "c": _ts(ct)},
            )
    with engine.connect() as conn:
        yield _SyncBackedDB(conn)
    engine.dispose()


@pytest.mark.asyncio
async def test_only_the_long_suspended_game_is_stale(db):
    facts = [
        (NPB, None, 15312538),
        (20, None, 2),      # suspended, inside the window
        (30, None, 3),      # live
        (40, None, 4),      # scheduled, six days old: not read
        (50, None, 5),      # suspended, future start
        (60, None, None),   # unlinked
        (70, None, 404),    # link to a row that is not there
    ]
    assert await _search_stale_game_market_ids(db, facts, NOW) == {NPB}


@pytest.mark.asyncio
async def test_two_markets_on_one_stale_game_are_both_returned(db):
    facts = [(NPB, None, 15312538), (61045497, None, 15312538)]
    assert await _search_stale_game_market_ids(db, facts, NOW) == {NPB, 61045497}


@pytest.mark.asyncio
async def test_no_linked_card_asks_nothing():
    class _NoDB:
        async def execute(self, stmt):  # pragma: no cover - must not run
            raise AssertionError("queried with nothing linked")

    assert await _search_stale_game_market_ids(_NoDB(), [(1, None, None)], NOW) == set()


def test_the_route_passes_the_stale_set_to_the_composer():
    """The composer defaults to an empty set, so the route must pass it."""
    src = inspect.getsource(events_module.search_events)
    call = src[src.index("futures_families = _compose_futures_families("):]
    call = call[: call.index("\n    )\n")]
    assert "stale_game_ids=_stale_game_ids" in call
    assert src.index("_stale_game_ids = await _search_stale_game_market_ids(") < src.index(
        "futures_families = _compose_futures_families("
    )
