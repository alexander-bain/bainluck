"""#2065 — the feed's game-event candidate pass, EXECUTED, not just compiled.

The feed's integration harness mocks ``db.execute``, so no existing test in this
repo ever runs ``_score_events``'s SQL.  A window query that satisfies
SQLAlchemy but is wrong in the database would pass every gate and empty the
first screen of the product — which is exactly what #2065 is.  So this module
runs the real statement against a real engine over a corpus shaped like the
production incident, and asserts BOTH directions of the cap (gotcha #43):

* the flood is collapsed, **and**
* the real slate stays populated.

``test_the_defect_reproduces_under_the_old_selection`` builds the pre-fix query
on the same corpus and shows it starving, so the corpus is proven to exercise
the bug rather than merely coexisting with it.

A separate pass compiles against the genuine PostgreSQL dialect, because SQLite
agreeing is not Postgres agreeing.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import and_, case, create_engine, or_, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Session

# SQLite cannot render Postgres-native column types.  These shims affect DDL
# rendering for the sqlite dialect ONLY — production is Postgres and never
# reaches them.  Without them `events` cannot be created and this whole module
# degrades to the shape-only coverage it exists to replace.


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.utils.feed_event_candidates import (  # noqa: E402
    EVENT_CANDIDATE_BUDGET,
    TIER_LIVE,
    TIER_QUOTAS,
    TIER_RECENT,
    TIER_SCHEDULED,
    event_candidate_ids,
    status_tier_expr,
)

NOW = datetime(2026, 8, 21, 19, 0, 0, tzinfo=timezone.utc)

# Sport ids used by the corpus.
S_ESPORTS = 1
S_LIGUE1 = 2
S_MLB = 3

_SPORTS = [
    (S_ESPORTS, "esports", "Esports"),
    (S_LIGUE1, "soccer_france_ligue_one", "Ligue 1"),
    (S_MLB, "baseball_mlb", "MLB"),
]

# Mirrors the production incident: TEN distinct esports matchups, each restated
# many times, none carrying a probability source.  Production measured a mean of
# 291 copies with zero singletons; 60 is enough to overflow every quota here
# while keeping the fixture fast.
ESPORTS_DISTINCT = 10
ESPORTS_COPIES = 60

# Ids are allocated in disjoint bands so a failure message names the cohort.
ESPORTS_ID_BASE = 100_000
REAL_LIVE_IDS = [10, 11, 12]
REAL_SCHEDULED_IDS = [20, 21, 22, 23, 24]
REAL_RECENT_IDS = [30, 31, 32, 33]


def _candidate_conditions(now=NOW):
    """The exact predicate `_score_events` accumulates for the anonymous path."""
    return [
        or_(
            and_(
                Event.status == "live",
                Event.commence_time <= now + timedelta(hours=1),
            ),
            and_(
                Event.status == "scheduled",
                Event.commence_time >= now,
                Event.commence_time <= now + timedelta(hours=12),
            ),
            and_(
                Event.status.in_(["completed", "closed"]),
                Event.commence_time >= now - timedelta(hours=24),
            ),
        )
    ]


def _event(
    id,
    sport_id,
    home,
    away,
    commence_time,
    status,
    sources=None,
    home_score=None,
    away_score=None,
):
    return Event(
        id=id,
        sport_id=sport_id,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence_time,
        status=status,
        win_probability_sources=sources,
        home_score=home_score,
        away_score=away_score,
    )


def _seed(session, rows):
    for sid, key, name in _SPORTS:
        session.add(Sport(id=sid, key=key, name=name))
    for row in rows:
        session.add(row)
    session.commit()


def _incident_corpus():
    """The 2026-08-21 slate: an esports flood plus a small real slate."""
    rows = []

    # --- the flood: 10 distinct matchups, restated ESPORTS_COPIES times each ---
    for m in range(ESPORTS_DISTINCT):
        kickoff = NOW - timedelta(minutes=30)
        for c in range(ESPORTS_COPIES):
            rows.append(
                _event(
                    id=ESPORTS_ID_BASE + m * 1000 + c,
                    sport_id=S_ESPORTS,
                    home=f"Team {m}A",
                    away=f"Team {m}B",
                    commence_time=kickoff,
                    status="live",
                    sources=None,
                )
            )

    # --- the real slate, all of it carrying probability data ---
    for n, eid in enumerate(REAL_LIVE_IDS):
        rows.append(
            _event(
                eid,
                S_LIGUE1,
                f"Home {eid}",
                f"Away {eid}",
                # Older than the flood, so `commence_time DESC` sorts them BELOW
                # it — which is precisely how the old query lost them.
                NOW - timedelta(hours=2, minutes=n),
                "live",
                sources={"betting": {"home_probability": 0.6}},
                home_score=1,
                away_score=0,
            )
        )
    for n, eid in enumerate(REAL_SCHEDULED_IDS):
        rows.append(
            _event(
                eid,
                S_MLB,
                f"Home {eid}",
                f"Away {eid}",
                NOW + timedelta(hours=2, minutes=n),
                "scheduled",
                sources={"betting": {"home_probability": 0.55}},
            )
        )
    for n, eid in enumerate(REAL_RECENT_IDS):
        rows.append(
            _event(
                eid,
                S_MLB,
                f"Home {eid}",
                f"Away {eid}",
                NOW - timedelta(hours=6, minutes=n),
                "closed",
                sources={"betting": {"home_probability": 0.7}},
                home_score=5,
                away_score=3,
            )
        )
    return rows


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng, tables=[Sport.__table__, Event.__table__])
    return eng


@pytest.fixture()
def incident(engine):
    with Session(engine) as s:
        _seed(s, _incident_corpus())
        yield s


def _admitted(session, conditions=None):
    stmt = event_candidate_ids(conditions or _candidate_conditions())
    return {r[0] for r in session.execute(stmt).all()}


def _old_selection(session, conditions=None):
    """The pre-#2065 query: one ORDER BY, one LIMIT, all tiers together."""
    stmt = (
        select(Event.id)
        .join(Sport, Event.sport_id == Sport.id)
        .where(and_(*(conditions or _candidate_conditions())))
        .order_by(
            case(
                (Event.status == "live", 0),
                (Event.status.in_(["completed", "closed"]), 1),
                else_=2,
            ),
            Event.commence_time.desc(),
        )
        .limit(EVENT_CANDIDATE_BUDGET)
    )
    return {r[0] for r in session.execute(stmt).all()}


# ---------------------------------------------------------------------------
# 0 — the corpus really does reproduce the defect
# ---------------------------------------------------------------------------


def test_the_defect_reproduces_under_the_old_selection(incident):
    """Without this, the fix's test could be passing over a corpus that never
    triggered the bug — the whole suite would certify nothing."""
    old = _old_selection(incident)

    assert len(old) == EVENT_CANDIDATE_BUDGET
    # Every admitted row is a live esports duplicate…
    assert all(i >= ESPORTS_ID_BASE for i in old)
    # …so the entire real slate is starved, exactly as production measured.
    assert not (old & set(REAL_LIVE_IDS))
    assert not (old & set(REAL_SCHEDULED_IDS))
    assert not (old & set(REAL_RECENT_IDS))


# ---------------------------------------------------------------------------
# 1 — BOTH directions of the cap (gotcha #43)
# ---------------------------------------------------------------------------


def test_direction_a_the_flood_is_collapsed(incident):
    admitted = _admitted(incident)
    esports = {i for i in admitted if i >= ESPORTS_ID_BASE}
    assert len(esports) == ESPORTS_DISTINCT, (
        f"{ESPORTS_DISTINCT} distinct matchups restated "
        f"{ESPORTS_COPIES}x each must collapse to {ESPORTS_DISTINCT} rows"
    )


def test_direction_b_the_real_slate_stays_populated(incident):
    """The half a one-directional guard would miss — and the half that IS the
    user-visible P1."""
    admitted = _admitted(incident)
    for cohort, ids in (
        ("live", REAL_LIVE_IDS),
        ("scheduled", REAL_SCHEDULED_IDS),
        ("recent", REAL_RECENT_IDS),
    ):
        missing = set(ids) - admitted
        assert not missing, f"{cohort} events starved out of the feed: {missing}"


def test_every_tier_is_represented(incident):
    """#2065's shape was not 'fewer events' — it was two tiers at exactly zero."""
    admitted = _admitted(incident)
    assert admitted & set(REAL_LIVE_IDS)
    assert admitted & set(REAL_SCHEDULED_IDS)
    assert admitted & set(REAL_RECENT_IDS)


def test_no_duplicate_matchup_survives(incident):
    """The user-visible twin of the starvation: on 2026-08-21 the served feed
    printed Strasbourg @ Marseille as two separate cards."""
    admitted = _admitted(incident)
    rows = incident.execute(
        select(
            Event.sport_id,
            Event.home_team_name,
            Event.away_team_name,
            Event.commence_time,
        ).where(Event.id.in_(admitted))
    ).all()
    assert len(rows) == len(set(rows)), "an identical fixture was admitted twice"


# ---------------------------------------------------------------------------
# 2 — which copy survives
# ---------------------------------------------------------------------------


def test_the_copy_with_probability_sources_wins(engine):
    with Session(engine) as s:
        _seed(
            s,
            [
                _event(1, S_LIGUE1, "H", "A", NOW - timedelta(hours=1), "live", None),
                _event(
                    2,
                    S_LIGUE1,
                    "H",
                    "A",
                    NOW - timedelta(hours=1),
                    "live",
                    {"betting": {"home_probability": 0.6}},
                ),
            ],
        )
        # id 1 is lower and would win a naive tiebreak; it renders a blank card.
        assert _admitted(s) == {2}


def test_among_copies_with_sources_the_one_with_a_score_wins(engine):
    with Session(engine) as s:
        src = {"betting": {"home_probability": 0.6}}
        _seed(
            s,
            [
                _event(1, S_LIGUE1, "H", "A", NOW - timedelta(hours=1), "live", src),
                _event(
                    2,
                    S_LIGUE1,
                    "H",
                    "A",
                    NOW - timedelta(hours=1),
                    "live",
                    src,
                    home_score=2,
                    away_score=1,
                ),
            ],
        )
        assert _admitted(s) == {2}


def test_otherwise_the_lowest_id_wins_and_the_choice_is_deterministic(engine):
    with Session(engine) as s:
        src = {"betting": {"home_probability": 0.6}}
        _seed(
            s,
            [
                _event(7, S_LIGUE1, "H", "A", NOW - timedelta(hours=1), "live", src),
                _event(3, S_LIGUE1, "H", "A", NOW - timedelta(hours=1), "live", src),
                _event(9, S_LIGUE1, "H", "A", NOW - timedelta(hours=1), "live", src),
            ],
        )
        assert _admitted(s) == {3}
        # Repeat: an arbitrary survivor would be allowed to drift between reads.
        assert _admitted(s) == {3}


# ---------------------------------------------------------------------------
# 3 — what must NOT be collapsed
# ---------------------------------------------------------------------------


def test_a_doubleheader_is_two_events(engine):
    """Same teams, same day, different start — two real games. `commence_time`
    is in the partition key precisely so this survives."""
    with Session(engine) as s:
        src = {"betting": {"home_probability": 0.6}}
        _seed(
            s,
            [
                _event(1, S_MLB, "H", "A", NOW + timedelta(hours=2), "scheduled", src),
                _event(2, S_MLB, "H", "A", NOW + timedelta(hours=6), "scheduled", src),
            ],
        )
        assert _admitted(s) == {1, 2}


def test_the_same_fixture_in_two_sports_is_not_collapsed(engine):
    with Session(engine) as s:
        src = {"betting": {"home_probability": 0.6}}
        t = NOW - timedelta(hours=1)
        _seed(
            s,
            [
                _event(1, S_LIGUE1, "H", "A", t, "live", src),
                _event(2, S_MLB, "H", "A", t, "live", src),
            ],
        )
        assert _admitted(s) == {1, 2}


def test_rows_with_an_incomplete_identity_are_never_fused(engine):
    """PARTITION BY treats NULLs as EQUAL. Without the id fallback these three
    unrelated rows would collapse into one and two real events would vanish.

    Latent today — production measured zero NULL/empty names — which is why it
    needs a test rather than a comment.
    """
    with Session(engine) as s:
        t = NOW - timedelta(hours=1)
        src = {"betting": {"home_probability": 0.6}}
        _seed(
            s,
            [
                _event(1, S_LIGUE1, "", "A", t, "live", src),
                _event(2, S_LIGUE1, "", "B", t, "live", src),
                _event(3, S_LIGUE1, "", "C", t, "live", src),
            ],
        )
        assert _admitted(s) == {1, 2, 3}


# ---------------------------------------------------------------------------
# 4 — the quotas
# ---------------------------------------------------------------------------


def test_quotas_sum_to_the_budget(engine):
    assert sum(TIER_QUOTAS.values()) == EVENT_CANDIDATE_BUDGET


def test_a_flood_of_DISTINCT_live_events_cannot_starve_the_other_tiers(engine):
    """The class, not the incident: dedupe alone does not fix this. 2,703
    *distinct* esports matchups were created in the 7 days to 2026-08-21."""
    rows = []
    n_live = TIER_QUOTAS[TIER_LIVE] + 250
    for i in range(n_live):
        rows.append(
            _event(
                ESPORTS_ID_BASE + i,
                S_ESPORTS,
                f"H{i}",
                f"A{i}",
                NOW - timedelta(minutes=1),
                "live",
                None,
            )
        )
    for eid in REAL_SCHEDULED_IDS:
        rows.append(
            _event(
                eid,
                S_MLB,
                f"H{eid}",
                f"A{eid}",
                NOW + timedelta(hours=2),
                "scheduled",
                {"betting": {"home_probability": 0.55}},
            )
        )
    with Session(engine) as s:
        _seed(s, rows)
        admitted = _admitted(s)
        live = {i for i in admitted if i >= ESPORTS_ID_BASE}
        assert len(live) == TIER_QUOTAS[TIER_LIVE]
        assert set(REAL_SCHEDULED_IDS) <= admitted


def test_a_tier_under_its_quota_is_admitted_whole(incident):
    """The quotas must be inert on a real slate. Production 2026-08-21 deduped
    to live 39 / recent 144 / scheduled 96, all under cap."""
    admitted = _admitted(incident)
    assert set(REAL_LIVE_IDS) <= admitted
    assert set(REAL_SCHEDULED_IDS) <= admitted
    assert set(REAL_RECENT_IDS) <= admitted


def test_total_never_exceeds_the_budget(engine):
    rows = []
    for tier_idx, (status, when) in enumerate(
        (
            ("live", NOW - timedelta(minutes=5)),
            ("closed", NOW - timedelta(hours=3)),
            ("scheduled", NOW + timedelta(hours=3)),
        )
    ):
        for i in range(400):
            rows.append(
                _event(
                    tier_idx * 10_000 + i,
                    S_ESPORTS,
                    f"H{tier_idx}-{i}",
                    f"A{tier_idx}-{i}",
                    when,
                    status,
                    None,
                )
            )
    with Session(engine) as s:
        _seed(s, rows)
        assert len(_admitted(s)) == EVENT_CANDIDATE_BUDGET


# ---------------------------------------------------------------------------
# 5 — filters are applied INSIDE the window pass
# ---------------------------------------------------------------------------


def test_a_sport_filter_is_applied_before_the_quota_not_after(incident):
    """Quotas computed over the unfiltered pool would hand a filtered request a
    slice of somebody else's sport — or nothing at all."""
    conds = _candidate_conditions() + [Sport.key.ilike("%ligue_one%")]
    admitted = _admitted(incident, conds)
    assert admitted == set(REAL_LIVE_IDS)


# ---------------------------------------------------------------------------
# 6 — the real dialect
# ---------------------------------------------------------------------------


def _pg_sql(conditions=None):
    return str(
        event_candidate_ids(conditions or _candidate_conditions()).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_it_compiles_for_postgresql():
    """SQLite agreeing is not Postgres agreeing, and production is Postgres."""
    sql = _pg_sql()
    assert sql.count("row_number() OVER") == 2
    assert "PARTITION BY events.sport_id, events.home_team_name" in sql
    assert "dup_rn = 1" in sql


def test_extra_conditions_do_not_break_the_or_precedence():
    """`and_(or_(A,B,C), D)` must parenthesise the OR. If it did not, `D` would
    bind to the last arm only and the window would silently change shape."""
    sql = _pg_sql(_candidate_conditions() + [Sport.key.ilike("%soccer%")])
    # The OR group is wrapped, and the extra condition is ANDed OUTSIDE it.
    assert "WHERE (events.status = 'live'" in sql
    assert ") AND sports.key ILIKE" in sql
    # And with no extra condition there is nothing to wrap, so the bare form
    # (which relies on SQL's AND-binds-tighter-than-OR precedence) still holds.
    assert "WHERE events.status = 'live'" in _pg_sql()


def test_the_quota_case_carries_the_declared_numbers():
    """A quota silently edited to zero would empty a tier while every
    behavioural test above still passed on its own fixture size."""
    sql = _pg_sql()
    for tier, quota in (
        (TIER_LIVE, TIER_QUOTAS[TIER_LIVE]),
        (TIER_RECENT, TIER_QUOTAS[TIER_RECENT]),
    ):
        assert f"= {tier}) THEN {quota}" in sql
    assert f"ELSE {TIER_QUOTAS[TIER_SCHEDULED]}" in sql


def test_status_tier_expr_orders_live_before_recent_before_scheduled():
    assert TIER_LIVE < TIER_RECENT < TIER_SCHEDULED
    sql = str(
        select(status_tier_expr()).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert f"'live') THEN {TIER_LIVE}" in sql
    assert f"'closed')) THEN {TIER_RECENT}" in sql
    assert f"ELSE {TIER_SCHEDULED}" in sql
