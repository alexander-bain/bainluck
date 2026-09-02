"""Q050 — the duplicate url reads the real final. Ruling 048's drain clause, executed.

THE SPECIMEN, measured on production 2026-09-02 AFTER Q048 (CERT-739) deployed:

    futures_markets  KXATPMATCH-26AUG30VALMON  ->  event_id 15293804   (Q048 moved it)
    event_provider_anchors  kalshi/KXATPMATCH-26AUG30VALMON/market -> event_id 15300759

    15300759  tennis_atp          Vallejo v Monfils   scheduled  2026-08-30 00:00Z
              commence_time_source kalshi_ticker      markets held: ZERO
    15293804  tennis_atp_us_open  A. D. Vallejo v Gael Monfils
              completed 1-3, 2026-09-01 23:04Z        ESPN final 2026-09-01 23:05Z

Q048 moved the market and its docstring calls that the drain. It is not the drain:
it ORPHANED the row. `/api/events/15300759` still answered `scheduled, 2026-08-30`
for a match that finished two days later, because nothing consumes the leftover
anchor. Ruling 048 accepts duplicates as a bounded cost on the promise that
"id-keyed reconciliation drains the duplicate when an id arrives" — the arriving
id is right there in `event_provider_anchors`, and until now nothing read it.

WHAT THESE TESTS PROVE, AND HOW
-------------------------------
Part 1 runs `_DRAIN_VERDICT_SQL` — the statement the resolver ACTUALLY issues, not
a paraphrase — over planted rows in stdlib sqlite3, through the real
`resolve_market_born_duplicate`. Every one of the seven refusals is pinned from
BOTH sides: the specimen resolves, and each refusal is proved by taking the
specimen and changing exactly the one fact that refusal is about. A guard that
only pinned the resolving case would pass equally well on a resolver that had
stopped refusing anything.

Part 2 pins the cheap gate against the SQL, in the only direction that matters.

Part 3 pins the route wiring: the row the reader is SERVED, not the row asked for.

Measured population these were written against (production, 2026-09-02): **505
events satisfy all seven refusals, 505 of 505 carry `provenance:unanchored`** —
the class is exactly the declared cost ruling 048 said it was paying.
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from app.services.anchor_channel import (
    MARKET_BORN_COMMENCE_SOURCES,
    _DRAIN_VERDICT_SQL,
    is_drain_candidate_row,
    resolve_market_born_duplicate,
)
from app.utils.event_completion import TICKER_DERIVED_COMMENCE_SOURCE

# The production specimen, id for id and ticker for ticker.
GHOST = 15300759          # tennis_atp, kalshi_ticker midnight stand-in, no markets
CANONICAL = 15293804      # tennis_atp_us_open, odds_api, completed 1-3
WINNER_TICKER = "KXATPMATCH-26AUG30VALMON"

SPORT_TENNIS_ATP = 41
SPORT_TENNIS_US_OPEN = 77
SPORT_SOCCER = 12


# =============================================================================
# The harness: the resolver's OWN SQL, executed.
#
# A fake session that returns whatever it was handed cannot test a predicate —
# it agrees with any WHERE clause, including one that was deleted. So the
# session below is a thin adapter onto a real sqlite3 connection: the resolver
# issues its statements, sqlite executes them, and the verdict comes back out of
# the data. Delete a refusal from the SQL and these go red.
# =============================================================================

_SCHEMA = """
CREATE TABLE sports (id INTEGER PRIMARY KEY, key TEXT);
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    sport_id INTEGER,
    commence_time_source TEXT,
    home_score INTEGER,
    away_score INTEGER,
    completed_at TEXT
);
CREATE TABLE event_provider_anchors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    source TEXT,
    source_id TEXT,
    id_kind TEXT
);
CREATE TABLE futures_markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT,
    external_id TEXT,
    event_id INTEGER
);
"""


class _Row:
    """A sqlite3.Row wearing SQLAlchemy's `._mapping` and positional access."""

    def __init__(self, raw: sqlite3.Row):
        self._raw = raw
        self._mapping = {k: raw[k] for k in raw.keys()}

    def __getitem__(self, index):
        return self._raw[index]


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None


class _SqliteSession:
    """Enough AsyncSession to run `resolve_market_born_duplicate` for real."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.statements: list[str] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append(sql)
        cursor = self.conn.execute(sql, params or {})
        return _Result([_Row(r) for r in cursor.fetchall()])


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _plant_specimen(
    conn: sqlite3.Connection,
    *,
    ghost_provenance: str = TICKER_DERIVED_COMMENCE_SOURCE,
    ghost_sport: int = SPORT_TENNIS_ATP,
    canonical_sport: int = SPORT_TENNIS_US_OPEN,
    ghost_home_score=None,
    ghost_completed_at=None,
) -> None:
    """The production pair, exactly as Q048 left it.

    Every refusal test below starts from THIS and changes one fact, so a refusal
    that fires for the wrong reason shows up as the specimen test going red too.
    """
    conn.executemany(
        "INSERT INTO sports (id, key) VALUES (?, ?)",
        [
            (SPORT_TENNIS_ATP, "tennis_atp"),
            (SPORT_TENNIS_US_OPEN, "tennis_atp_us_open"),
            (SPORT_SOCCER, "soccer_epl"),
        ],
    )
    conn.executemany(
        "INSERT INTO events (id, sport_id, commence_time_source, home_score, "
        "away_score, completed_at) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (GHOST, ghost_sport, ghost_provenance, ghost_home_score, None,
             ghost_completed_at),
            (CANONICAL, canonical_sport, "odds_api", 1, 3,
             "2026-09-02 01:36:28+00"),
        ],
    )
    # The anchor still names the ghost — that is the whole point. It is the
    # birth record the registry wrote when the market created the row.
    conn.execute(
        "INSERT INTO event_provider_anchors (event_id, source, source_id, "
        "id_kind) VALUES (?, ?, ?, ?)",
        (GHOST, "kalshi", WINNER_TICKER, "market"),
    )
    # ...and the market itself has already been moved onto the real row.
    conn.execute(
        "INSERT INTO futures_markets (source, external_id, event_id) "
        "VALUES (?, ?, ?)",
        ("kalshi", WINNER_TICKER, CANONICAL),
    )
    conn.commit()


def _resolve(conn: sqlite3.Connection, event_id: int = GHOST):
    return asyncio.run(resolve_market_born_duplicate(_SqliteSession(conn), event_id))


# =============================================================================
# Part 1 — the verdict. The specimen, then each refusal in isolation.
# =============================================================================


def test_the_specimen_resolves_to_the_row_espn_agrees_with():
    """15300759 reads as 15293804. This is the ship, in one assertion."""
    conn = _connect()
    _plant_specimen(conn)
    assert _resolve(conn) == CANONICAL


def test_the_resolver_issues_its_own_sql_and_not_a_paraphrase():
    """If the module's statement and the executed one ever diverge, say so here."""
    conn = _connect()
    _plant_specimen(conn)
    session = _SqliteSession(conn)
    asyncio.run(resolve_market_born_duplicate(session, GHOST))
    assert session.statements[0].strip() == _DRAIN_VERDICT_SQL.strip()


def test_a_different_sports_row_for_one_sport_still_resolves():
    """`tennis_atp` -> `tennis_atp_us_open` is the SPECIMEN, not an edge case.

    `find_event_by_anchor` can afford `expected_sport_id` equality because it
    guards an absorption. Applying it here would refuse the entire measured
    class: 505 of 505 production pairs pass the family check and only 391 share
    a `sport_id`. This test is why the family, not the id, is the granularity.
    """
    conn = _connect()
    _plant_specimen(conn)
    assert _resolve(conn) == CANONICAL


def test_a_cross_family_resolution_is_refused():
    """Tennis must never be read as soccer, however good the id evidence."""
    conn = _connect()
    _plant_specimen(conn, canonical_sport=SPORT_SOCCER)
    assert _resolve(conn) is None


def test_a_game_anchor_means_a_real_schedule_named_this_row():
    conn = _connect()
    _plant_specimen(conn)
    conn.execute(
        "INSERT INTO event_provider_anchors (event_id, source, source_id, "
        "id_kind) VALUES (?, ?, ?, ?)",
        (GHOST, "odds_api", "abc123", "game"),
    )
    conn.commit()
    assert _resolve(conn) is None


@pytest.mark.parametrize("provenance", ["odds_api", "espn", "statpal", None])
def test_a_row_that_is_not_market_born_is_never_drained(provenance):
    """The guard that stops a real fixture being read as a ghost.

    `_record_claim_anchor` fires on the ATTACH path too for Kalshi and
    Polymarket, so an `odds_api` fixture can hold a market anchor it did not
    come from. `None` is refused for q076's reason, from the other side: most of
    the table predates the column, and reading a missing provenance as
    market-born would put nearly every historic row in this class.
    """
    conn = _connect()
    _plant_specimen(conn, ghost_provenance=provenance)
    assert _resolve(conn) is None


@pytest.mark.parametrize(
    # `key=str` and not a bare `sorted`: the allowlist is a frozenset of
    # strings today, and an edit that slips `None` into it must reach the
    # assertion in `test_a_row_that_is_not_market_born_is_never_drained` rather
    # than blow up in COLLECTION here, where pytest exits 2 and the mutation
    # battery reports "the gate never ran" instead of a verdict (gotcha #54).
    "provenance",
    sorted(MARKET_BORN_COMMENCE_SOURCES, key=str),
)
def test_every_market_born_provenance_resolves(provenance):
    """Both directions: the allowlist is the rule, not one lucky literal."""
    conn = _connect()
    _plant_specimen(conn, ghost_provenance=provenance)
    assert _resolve(conn) == CANONICAL


def test_a_row_with_no_market_anchor_has_nothing_to_contradict():
    conn = _connect()
    _plant_specimen(conn)
    conn.execute("DELETE FROM event_provider_anchors")
    conn.commit()
    assert _resolve(conn) is None


def test_an_anchor_whose_market_we_no_longer_hold_is_silence_not_evidence():
    """Gotcha #53: an empty answer is a response shape, not an absence."""
    conn = _connect()
    _plant_specimen(conn)
    conn.execute(
        "INSERT INTO event_provider_anchors (event_id, source, source_id, "
        "id_kind) VALUES (?, ?, ?, ?)",
        (GHOST, "kalshi", "KXATPGTOTAL-26AUG30VALMON", "market"),
    )
    conn.commit()  # no futures_markets row for that ticker
    assert _resolve(conn) is None


def test_an_unlinked_market_is_not_a_destination():
    """A market sitting on NO event says nothing about where this row went."""
    conn = _connect()
    _plant_specimen(conn)
    conn.execute(
        "INSERT INTO event_provider_anchors (event_id, source, source_id, "
        "id_kind) VALUES (?, ?, ?, ?)",
        (GHOST, "kalshi", "KXATPGSPREAD-26AUG30VALMON", "market"),
    )
    conn.execute(
        "INSERT INTO futures_markets (source, external_id, event_id) "
        "VALUES (?, ?, ?)",
        ("kalshi", "KXATPGSPREAD-26AUG30VALMON", None),
    )
    conn.commit()
    assert _resolve(conn) is None


def test_three_anchors_agreeing_on_one_destination_is_the_strongest_case():
    """`count(DISTINCT target)`, not `count(target)`.

    A Kalshi segment moves several markets at once — the VALMON segment is seven
    — so a ghost that held two of them ends up with two anchors pointing at the
    same canonical. Counting rows instead of destinations would read that as an
    ambiguity and refuse the clearest evidence the system can produce. Not
    exercised by production today (max moved anchors per ghost: 1, measured
    2026-09-02), which is exactly why it needs pinning rather than trusting.
    """
    conn = _connect()
    _plant_specimen(conn)
    for ticker in ("KXATPSETWINNER-26AUG30VALMON-1", "KXATPGTOTAL-26AUG30VALMON"):
        conn.execute(
            "INSERT INTO event_provider_anchors (event_id, source, source_id, "
            "id_kind) VALUES (?, ?, ?, ?)",
            (GHOST, "kalshi", ticker, "market"),
        )
        conn.execute(
            "INSERT INTO futures_markets (source, external_id, event_id) "
            "VALUES (?, ?, ?)",
            ("kalshi", ticker, CANONICAL),
        )
    conn.commit()
    assert _resolve(conn) == CANONICAL


def test_a_container_anchor_is_ignored_not_read_as_a_broken_market():
    """A Polymarket EVENT id is not a market, and must not be resolved as one.

    `event_provider_anchors` holds no `container` rows today (measured
    2026-09-02: 2,447 polymarket/market, 1,663 kalshi/market, 1,902 game, zero
    container) — but `polymarket_anchor_key` produces them, and the day one is
    written a resolver that swept every `id_kind` into the market lookup would
    see an unresolvable "market" and refuse every Polymarket-born ghost on the
    site. Silent under-coverage, which is why it is pinned before it can happen.
    """
    conn = _connect()
    _plant_specimen(conn)
    conn.execute(
        "INSERT INTO event_provider_anchors (event_id, source, source_id, "
        "id_kind) VALUES (?, ?, ?, ?)",
        (GHOST, "polymarket", "pmevent:21455", "container"),
    )
    conn.commit()
    assert _resolve(conn) == CANONICAL


def test_a_correspondence_that_only_half_moved_was_split_not_re_decided():
    """Refused — and refused by the NO-MARKETS rule, which is the whole point.

    A market still pointing back here is a market this row holds, so the
    separate "no anchor still names this row" clause it once had was
    unreachable: nothing could satisfy it that `holds_markets` did not already
    catch. The mutation battery is what proved that (its mutant could not be
    killed), and the clause was deleted rather than kept as decoration. The case
    still needs a test, because the BEHAVIOUR is load-bearing even though the
    line that used to state it was not.
    """
    conn = _connect()
    _plant_specimen(conn)
    conn.execute(
        "INSERT INTO event_provider_anchors (event_id, source, source_id, "
        "id_kind) VALUES (?, ?, ?, ?)",
        (GHOST, "kalshi", "KXATPSETWINNER-26AUG30VALMON-1", "market"),
    )
    conn.execute(
        "INSERT INTO futures_markets (source, external_id, event_id) "
        "VALUES (?, ?, ?)",
        ("kalshi", "KXATPSETWINNER-26AUG30VALMON-1", GHOST),
    )
    conn.commit()
    assert _resolve(conn) is None


def test_two_destinations_is_a_coin_flip_and_is_refused():
    """`_choose_segment_event`'s ambiguity refusal, applied on the read side."""
    conn = _connect()
    _plant_specimen(conn)
    conn.execute("INSERT INTO events (id, sport_id, commence_time_source) "
                 "VALUES (?, ?, ?)", (15299999, SPORT_TENNIS_US_OPEN, "odds_api"))
    conn.execute(
        "INSERT INTO event_provider_anchors (event_id, source, source_id, "
        "id_kind) VALUES (?, ?, ?, ?)",
        (GHOST, "kalshi", "KXATPEXACTMATCH-26AUG30VALMON", "market"),
    )
    conn.execute(
        "INSERT INTO futures_markets (source, external_id, event_id) "
        "VALUES (?, ?, ?)",
        ("kalshi", "KXATPEXACTMATCH-26AUG30VALMON", 15299999),
    )
    conn.commit()
    assert _resolve(conn) is None


def test_a_row_still_holding_a_market_is_not_an_abandoned_husk():
    conn = _connect()
    _plant_specimen(conn)
    conn.execute(
        "INSERT INTO futures_markets (source, external_id, event_id) "
        "VALUES (?, ?, ?)",
        ("polymarket", "0xdeadbeef", GHOST),
    )
    conn.commit()
    assert _resolve(conn) is None


def test_a_row_carrying_a_score_is_not_a_husk_either():
    conn = _connect()
    _plant_specimen(conn, ghost_home_score=2)
    assert _resolve(conn) is None


def test_a_row_carrying_completed_at_is_not_a_husk_either():
    conn = _connect()
    _plant_specimen(conn, ghost_completed_at="2026-09-02 01:36:28+00")
    assert _resolve(conn) is None


def test_a_canonical_can_never_itself_be_drained():
    """No chains, and this is a PROOF rather than a measurement.

    The destination was found by reading a market's `event_id`, so the
    destination holds that market — and "holds no markets" is a refusal. A
    resolution therefore cannot land on a row that resolves onward, whatever the
    data does.
    """
    conn = _connect()
    _plant_specimen(conn)
    assert _resolve(conn, CANONICAL) is None


def test_the_anchor_lookup_is_source_qualified():
    """A Polymarket condition id that happens to equal a Kalshi ticker must not
    resolve through the wrong provider. `uq_futures_source_external` is unique on
    `(source, external_id)`, not on `external_id` alone."""
    conn = _connect()
    _plant_specimen(conn)
    conn.execute("DELETE FROM futures_markets")
    conn.execute(
        "INSERT INTO futures_markets (source, external_id, event_id) "
        "VALUES (?, ?, ?)",
        ("polymarket", WINNER_TICKER, CANONICAL),
    )
    conn.commit()
    assert _resolve(conn) is None


def test_a_destination_row_that_does_not_exist_is_a_refusal_not_a_crash():
    conn = _connect()
    _plant_specimen(conn)
    conn.execute("DELETE FROM events WHERE id = ?", (CANONICAL,))
    conn.commit()
    assert _resolve(conn) is None


def test_an_event_that_does_not_exist_resolves_to_nothing():
    conn = _connect()
    _plant_specimen(conn)
    assert _resolve(conn, 999999999) is None


# =============================================================================
# Part 2 — the cheap gate, pinned against the SQL in the direction that matters.
# =============================================================================


def test_the_gate_admits_the_specimen():
    assert is_drain_candidate_row(
        commence_time_source=TICKER_DERIVED_COMMENCE_SOURCE,
        home_score=None,
        away_score=None,
        completed_at=None,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"commence_time_source": "odds_api"},
        {"commence_time_source": None},
        {"commence_time_source": TICKER_DERIVED_COMMENCE_SOURCE, "home_score": 3},
        {"commence_time_source": TICKER_DERIVED_COMMENCE_SOURCE, "away_score": 0},
        {
            "commence_time_source": TICKER_DERIVED_COMMENCE_SOURCE,
            "completed_at": "2026-09-02 01:36:28+00",
        },
    ],
)
def test_the_gate_refuses_what_the_sql_would_also_refuse(kwargs):
    base = {
        "commence_time_source": TICKER_DERIVED_COMMENCE_SOURCE,
        "home_score": None,
        "away_score": None,
        "completed_at": None,
    }
    base.update(kwargs)
    assert not is_drain_candidate_row(**base)


def test_the_gate_never_hides_a_row_the_verdict_would_drain():
    """The one direction that is not recoverable.

    A gate that refuses too much leaves a ghost rendering — today's behaviour. A
    gate that admits too much costs a query and nothing else, because the SQL
    re-asserts both conditions. So the contract is one-way: for every provenance
    the verdict accepts, the gate must say yes.
    """
    for provenance in MARKET_BORN_COMMENCE_SOURCES:
        conn = _connect()
        _plant_specimen(conn, ghost_provenance=provenance)
        assert _resolve(conn) == CANONICAL
        assert is_drain_candidate_row(
            commence_time_source=provenance,
            home_score=None,
            away_score=None,
            completed_at=None,
        ), f"the gate hides {provenance!r}, which the verdict drains"


def test_a_zero_score_is_a_score():
    """`0` is falsy in Python and is a real result in every sport we carry."""
    assert not is_drain_candidate_row(
        commence_time_source=TICKER_DERIVED_COMMENCE_SOURCE,
        home_score=0,
        away_score=0,
        completed_at=None,
    )


# =============================================================================
# Part 3 — the ROUTE. What the reader is served, not what they asked for.
#
# Part 1 proves the verdict. This proves the wiring, which is a separate thing
# and the one that actually ships: a correct resolver the route never consults
# changes nothing a user sees.
# =============================================================================


@pytest.fixture()
def route_harness(monkeypatch):
    """`get_event` with its three heavy reads stubbed and its resolver recorded."""
    from app.models.models import Event, Sport
    from app.routes import events as events_route

    events_route._event_detail_cache.clear()

    ghost = Event(
        id=GHOST,
        sport_id=SPORT_TENNIS_ATP,
        home_team_name="Vallejo",
        away_team_name="Monfils",
        commence_time=__import__("datetime").datetime(
            2026, 8, 30, 0, 0, tzinfo=__import__("datetime").timezone.utc
        ),
        commence_time_source=TICKER_DERIVED_COMMENCE_SOURCE,
        status="scheduled",
    )
    ghost.sport = Sport(id=SPORT_TENNIS_ATP, key="tennis_atp", name="ATP")

    canonical = Event(
        id=CANONICAL,
        sport_id=SPORT_TENNIS_US_OPEN,
        home_team_name="Adolfo Daniel Vallejo",
        away_team_name="Gael Monfils",
        commence_time=__import__("datetime").datetime(
            2026, 9, 1, 23, 4, tzinfo=__import__("datetime").timezone.utc
        ),
        commence_time_source="odds_api",
        status="completed",
        home_score=1,
        away_score=3,
        completed_at=__import__("datetime").datetime(
            2026, 9, 2, 1, 36, 28, tzinfo=__import__("datetime").timezone.utc
        ),
    )
    canonical.sport = Sport(
        id=SPORT_TENNIS_US_OPEN, key="tennis_atp_us_open", name="US Open"
    )
    rows = {GHOST: ghost, CANONICAL: canonical}

    class _Scalar:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

        def scalars(self):
            return self

        def all(self):
            return []

    class _FakeDb:
        """Answers only the three reads `get_event` makes."""

        def __init__(self):
            self.requested_ids = []

        async def execute(self, stmt, *args, **kwargs):
            compiled = str(stmt)
            # The ONE statement this fake answers is the route's own
            # `select(Event).where(Event.id == …)`. The odds enrichment reads
            # `events` too (it joins), so keying on the table name alone would
            # swallow it and hand back an Event where a snapshot belongs.
            is_event_by_id = (
                "FROM events" in compiled
                and "events.id = " in compiled
                and "odds_snapshots" not in compiled
            )
            if is_event_by_id:
                params = stmt.compile().params
                event_id = next(
                    (v for v in params.values() if isinstance(v, int)), None
                )
                self.requested_ids.append(event_id)
                return _Scalar(rows.get(event_id))
            return _Scalar(None)

    async def _no_percentiles(_db):
        return {}

    async def _no_teams(_db, _names):
        return {}

    monkeypatch.setattr(events_route, "_load_gei_percentiles", _no_percentiles)
    monkeypatch.setattr(events_route, "_build_team_lookup", _no_teams)

    calls: list[int] = []

    def install_resolver(answer):
        async def _resolver(_db, event_id):
            calls.append(event_id)
            return answer

        monkeypatch.setattr(
            events_route, "resolve_market_born_duplicate", _resolver
        )

    db = _FakeDb()
    return {
        "route": events_route,
        "db": db,
        "calls": calls,
        "install_resolver": install_resolver,
        "serve": lambda event_id: asyncio.run(
            events_route.get_event(event_id, db=db)
        ),
    }


def test_the_ghost_url_serves_the_row_espn_agrees_with(route_harness):
    """THE SHIP. `/api/events/15300759` answers with the completed match."""
    route_harness["install_resolver"](CANONICAL)
    response = route_harness["serve"](GHOST)

    assert route_harness["calls"] == [GHOST], (
        "the route must ask about the id it was GIVEN, not the one it served"
    )
    assert response["id"] == CANONICAL
    assert response["status"] == "completed"
    assert response["commence_time"].startswith("2026-09-01")
    assert (response["home_score"], response["away_score"]) == (1, 3)


def test_a_refusal_serves_the_row_that_was_asked_for(route_harness):
    """The control, and it is also the entire pre-Q050 behaviour.

    Green under both arms by construction: this is what the route did before the
    resolver existed, so it pins that the change is additive rather than a
    rewrite of the read path.
    """
    route_harness["install_resolver"](None)
    response = route_harness["serve"](GHOST)
    assert response["id"] == GHOST
    assert response["status"] == "scheduled"


def test_a_real_fixture_never_pays_for_the_verdict_query(route_harness):
    """The gate, on the hot path. Product priority #3 does not fund a query it
    can never pass."""
    route_harness["install_resolver"](GHOST)  # would be WRONG if ever consulted
    response = route_harness["serve"](CANONICAL)
    assert route_harness["calls"] == [], (
        "an odds_api fixture with a score reached the resolver — the cheap gate "
        "is not gating"
    )
    assert response["id"] == CANONICAL


def test_the_ghost_url_is_cached_under_the_id_it_was_asked_for(route_harness):
    """Otherwise the one population that always needs the verdict never caches."""
    route_harness["install_resolver"](CANONICAL)
    route_harness["serve"](GHOST)
    cache = route_harness["route"]._event_detail_cache
    assert GHOST in cache and CANONICAL in cache
    assert cache[GHOST][2]["id"] == CANONICAL

    del route_harness["calls"][:]
    again = route_harness["serve"](GHOST)
    assert again["id"] == CANONICAL
    assert route_harness["calls"] == [], "a cache hit re-ran the verdict query"
