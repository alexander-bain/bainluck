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
    TIER_SUSPENDED,
    candidate_window_conditions,
    deduplicated_event_ids,
    event_candidate_ids,
    status_tier_expr,
    survivor_order,
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
    """The predicate `_score_events` uses — THE SAME OBJECT, not a copy of it.

    This was a hand-written copy until live/048, and its docstring said "the
    exact predicate `_score_events` accumulates". That was true when it was
    written, and it stopped being true silently: the route learned a fifth
    status and the copy did not, so every test in this file kept passing over a
    predicate that no longer described the route (CERT-786). A copy cannot fail
    that way loudly — it fails by agreeing with itself.

    The windows are the anonymous path's (1h live buffer, 12h upcoming, 24h
    recent); `my_teams_only` widens them at the call site, which is why they are
    arguments rather than constants inside the shared function.
    """
    return candidate_window_conditions(
        now=now,
        live_start_cutoff=now + timedelta(hours=1),
        upcoming_cutoff=now + timedelta(hours=12),
        recent_cutoff=now - timedelta(hours=24),
    )


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
    opening_home_probability=None,
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
        opening_home_probability=opening_home_probability,
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
    """Three rows whose identity is entirely blank must stay three rows.

    A partition key groups equal values — and NULLs count as equal — so without
    the id fallback these collapse into ONE and two real events vanish. We cannot
    tell them apart, which is exactly the reason not to assert they are the same
    fixture.

    THE FIRST VERSION OF THIS TEST DID NOT TEST THIS. It blanked only
    `home_team_name` and gave each row a DIFFERENT away name, so the partition
    keys already differed and the rows could never have fused — mutation M2
    (deleting the guard outright) passed all twenty tests. The names have to
    collide for the guard to be the thing keeping them apart.

    Note the live hazard is the EMPTY STRING, not NULL: `home_team_name`,
    `away_team_name` and `commence_time` are all NOT NULL in the schema, so the
    NULL arms of the guard are unreachable today and are kept for the column that
    loosens later.
    """
    with Session(engine) as s:
        t = NOW - timedelta(hours=1)
        src = {"betting": {"home_probability": 0.6}}
        _seed(
            s,
            [
                _event(1, S_LIGUE1, "", "", t, "live", src),
                _event(2, S_LIGUE1, "", "", t, "live", src),
                _event(3, S_LIGUE1, "", "", t, "live", src),
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
    """Every tier flooded at once still fits inside one budget.

    The corpus carries FOUR tiers since live/048. That is not padding: with the
    suspended tier absent the four quotas can only reach 450, and an assertion
    of `== EVENT_CANDIDATE_BUDGET` over three tiers would have to be relaxed to
    `<=` — which would stop noticing a quota edited down to nothing, the exact
    thing `test_the_quota_case_carries_the_declared_numbers` exists to catch
    from the other side.
    """
    rows = []
    for tier_idx, (status, when) in enumerate(
        (
            ("live", NOW - timedelta(minutes=5)),
            ("closed", NOW - timedelta(hours=3)),
            ("scheduled", NOW + timedelta(hours=3)),
            ("suspended", NOW - timedelta(hours=4)),
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


# ---------------------------------------------------------------------------
# 6 — My Stuff (#2213): the branch that never had the collapse
# ---------------------------------------------------------------------------
#
# `_score_events` has always had two arms. The `else:` arm — Discover and Sports
# — routes through `event_candidate_ids` and has been protected since #2065. The
# `my_teams_only` arm built its own query and got NO duplicate guard at all, so
# the one surface with no protection was the one Alex opens by name.
#
# On 2026-08-25 My Stuff rendered "Live Now (2)" for a single Boston Red Sox @
# Miami Marlins game: two cards, 57%/43% from the ESPN/odds row and 50%/50% from
# the StatPal row. Reproduced below with the real production shape of those two
# rows, then asserted collapsed.


# The two production rows, 2026-08-25. Same teams, same start, no shared
# provider id — which is exactly why the registry created rather than absorbed
# (ruling 048), and why a DISPLAY collapse is the right layer for this.
_REDSOX_START = NOW - timedelta(minutes=20)
_ESPN_ROW_ID = 15291666      # espn_id + odds external_id; espn/betting/stat_model
_STATPAL_ROW_ID = 15228865   # statpal fixture only; `mlb` source alone


def _mystuff_corpus():
    return [
        _event(
            id=_ESPN_ROW_ID,
            sport_id=S_MLB,
            home="Miami Marlins",
            away="Boston Red Sox",
            commence_time=_REDSOX_START,
            status="live",
            sources={
                "espn": {"value": 0.382},
                "betting": {"value": 0.3055},
                "stat_model": {"value": 0.2469},
            },
            home_score=0,
            away_score=1,
            opening_home_probability=0.4209,
        ),
        _event(
            id=_STATPAL_ROW_ID,
            sport_id=S_MLB,
            home="Miami Marlins",
            away="Boston Red Sox",
            commence_time=_REDSOX_START,
            status="live",
            sources={"mlb": {"value": 0.413}},
            home_score=0,
            away_score=1,
        ),
    ]


@pytest.fixture()
def mystuff(engine):
    with Session(engine) as s:
        _seed(s, _mystuff_corpus())
        yield s


def _mystuff_admitted(session, conditions=None):
    stmt = deduplicated_event_ids(conditions or _candidate_conditions())
    return {r[0] for r in session.execute(stmt).all()}


def test_the_mystuff_defect_reproduces_without_the_collapse(mystuff):
    """Both rows are admitted by the raw predicate — the two cards Alex saw.

    Without this the fix's test could pass over a corpus that never had a
    duplicate in it, and would certify nothing.
    """
    both = {
        r[0]
        for r in mystuff.execute(
            select(Event.id)
            .join(Sport, Event.sport_id == Sport.id)
            .where(and_(*_candidate_conditions()))
        ).all()
    }
    assert both == {_ESPN_ROW_ID, _STATPAL_ROW_ID}


def test_one_game_yields_one_card(mystuff):
    """THE ship: 'Live Now (2)' for one game becomes one card."""
    assert len(_mystuff_admitted(mystuff)) == 1


def test_the_surviving_card_is_the_one_that_can_render_a_probability(mystuff):
    """The ESPN/odds row wins — three real sources against StatPal's one.

    Direction matters and is not symmetric. Keeping the StatPal row would swap a
    card reading 57/43 off a real blend for one reading 50/50 off a single
    source, which is a worse card than the duplicate pair contained. `survivor_order`
    already encodes this; the assertion pins that My Stuff inherits it.
    """
    assert _mystuff_admitted(mystuff) == {_ESPN_ROW_ID}


def test_my_stuff_gets_no_tier_quotas(mystuff):
    """The collapse is reused; the 200/150/150 split deliberately is not.

    A quota that never binds is dead code, and one that DOES bind on a
    my-teams pool drops one of Alex's own games. Asserted on the SQL so that
    wiring My Stuff through `event_candidate_ids` — the obvious future
    'simplification' — fails here rather than silently capping his slate.
    """
    sql = str(
        deduplicated_event_ids(_candidate_conditions()).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "dup_rn" in sql
    for quota in set(TIER_QUOTAS.values()):
        assert f"THEN {quota}" not in sql, "tier quotas must not reach My Stuff"


def test_a_doubleheader_is_still_two_cards_on_my_stuff(engine):
    """The ruling-048 hazard, on this surface too.

    'Any matcher smart enough to join two same-game claims is provably dumb
    enough to destroy a doubleheader.' The collapse escapes that only because it
    partitions on `commence_time`, and MLB in August is when it gets tested.
    """
    with Session(engine) as s:
        _seed(
            s,
            [
                _event(
                    id=1,
                    sport_id=S_MLB,
                    home="Miami Marlins",
                    away="Boston Red Sox",
                    commence_time=NOW - timedelta(minutes=30),
                    status="live",
                    sources={"betting": {"value": 0.5}},
                ),
                _event(
                    id=2,
                    sport_id=S_MLB,
                    home="Miami Marlins",
                    away="Boston Red Sox",
                    commence_time=NOW + timedelta(hours=4),
                    status="scheduled",
                    sources={"betting": {"value": 0.5}},
                ),
            ],
        )
        assert _mystuff_admitted(s) == {1, 2}


def test_both_rows_remain_addressable_after_the_collapse(mystuff):
    """This collapses two rows into one CARD, never into one ROW.

    Ruling 048's merge needs an id-anchored correspondence, and measurement says
    none exists — 0 of 41 duplicate MLB pairs share any provider id (#2213). So
    the suppressed row must still be a row: nothing is deleted, nothing is
    merged, and `/api/events/{id}` still serves it. Pinned because a future
    'cleanup' that turns this into a DELETE would pass every other test here.
    """
    still_there = {
        r[0]
        for r in mystuff.execute(
            select(Event.id).where(Event.id.in_([_ESPN_ROW_ID, _STATPAL_ROW_ID]))
        ).all()
    }
    assert still_there == {_ESPN_ROW_ID, _STATPAL_ROW_ID}


def test_the_two_arms_cannot_drift_apart(mystuff):
    """One definition of 'the same fixture', not two.

    Both callers go through `_collapsed_subquery`. If someone gives My Stuff its
    own partition key, the two surfaces start disagreeing about what a duplicate
    is — and the surface with the looser key silently grows them back.
    """
    assert _mystuff_admitted(mystuff) == _admitted(mystuff)


# ---------------------------------------------------------------------------
# 7 — CERT-407: the cross-signal tiebreak the first version of this got backwards
# ---------------------------------------------------------------------------
#
# `has_opening` was introduced above to break the #2213 tie, and it was placed
# ABOVE `has_score`. CERT-407 blocked on that placement with an executed
# specimen, and the finding is correct: with the keys in that order a row that
# has only been PRICED outranks a row that has actually been PLAYED. The pair it
# drove kept an opening-priced scoreless row and suppressed the only row
# carrying `2–1`.
#
# The repair is a reordering, not a deletion. Both signals still matter and they
# answer different questions:
#
#   has_score   — "does this row know what is happening in the game?"
#   has_opening — "has a betting source ever priced this row?"
#
# A score is direct evidence about the fixture; an opening price is evidence
# about the pipeline that wrote the row. When they disagree, the row that knows
# the score is the better card, and #2213's own pair is untouched by the swap
# because BOTH of its rows carried a score — the tie it was added to break is
# still broken, one key later.
#
# Both tests below are non-vacuous by construction: in each, the row that SHOULD
# win carries the HIGHER id, so `Event.id.asc()` cannot produce the expected
# answer by accident if a key is dropped.

_CROSS_SIGNAL_START = NOW - timedelta(hours=1)
_SRC = {"betting": {"home_probability": 0.6}}


def test_a_played_row_beats_a_merely_priced_one(engine):
    """CERT-407's specimen. Pre-repair this returns the scoreless row.

    The two rows tie on `has_sources`, so the decision falls to the next key.
    Under `has_opening` -> `has_score` the priced row wins and the card renders
    no score for a game that is 2-1. Under `has_score` -> `has_opening` the row
    that knows the score wins, which is the answer a reader of the card wants.
    """
    with Session(engine) as s:
        _seed(
            s,
            [
                # Priced, but has no idea what the score is. LOWER id, so it also
                # wins the final tiebreak — this test fails loudly if `has_score`
                # is ever demoted again.
                _event(
                    1,
                    S_LIGUE1,
                    "H",
                    "A",
                    _CROSS_SIGNAL_START,
                    "live",
                    _SRC,
                    opening_home_probability=0.55,
                ),
                # Played: the only row carrying the actual 2-1.
                _event(
                    2,
                    S_LIGUE1,
                    "H",
                    "A",
                    _CROSS_SIGNAL_START,
                    "live",
                    _SRC,
                    home_score=2,
                    away_score=1,
                ),
            ],
        )
        assert _admitted(s) == {2}


def test_opening_still_breaks_the_tie_when_both_rows_are_played(engine):
    """The #2213 control — the repair must not undo what `has_opening` is for.

    This is the Red Sox-Marlins shape: both rows carry sources AND a score, so
    `has_score` ties and the decision falls through to `has_opening`. Delete
    `has_opening` and the lowest id wins, which is the StatPal row: a 50/50 card
    replacing a real blend. So this test pins the key's PRESENCE while the test
    above pins its POSITION, and neither alone is sufficient.
    """
    with Session(engine) as s:
        _seed(
            s,
            [
                _event(
                    1,
                    S_LIGUE1,
                    "H",
                    "A",
                    _CROSS_SIGNAL_START,
                    "live",
                    _SRC,
                    home_score=0,
                    away_score=1,
                ),
                _event(
                    2,
                    S_LIGUE1,
                    "H",
                    "A",
                    _CROSS_SIGNAL_START,
                    "live",
                    _SRC,
                    home_score=0,
                    away_score=1,
                    opening_home_probability=0.4209,
                ),
            ],
        )
        assert _admitted(s) == {2}


def test_the_survivor_keys_are_in_the_certified_order():
    """The order itself, asserted on the compiled SQL.

    The two executing tests above each pin one property of one key. This pins
    the whole sequence, so a reordering that happens to leave both of those
    corpora answering correctly still fails here rather than shipping.
    """
    keys = [
        str(clause.compile(dialect=postgresql.dialect()))
        for clause in survivor_order()
    ]
    assert len(keys) == 4, keys
    assert "win_probability_sources" in keys[0]
    assert "home_score" in keys[1] and "away_score" in keys[1]
    assert "opening_home_probability" in keys[2]
    assert "events.id ASC" in keys[3]


# ---------------------------------------------------------------------------
# 8 — the wiring itself, because a library guard cannot see the route
# ---------------------------------------------------------------------------
#
# Every test above drives `deduplicated_event_ids` directly. None of them can
# tell whether `_score_events` still CALLS it: delete the one `query.where(...)`
# line in the My Stuff arm and all thirty stay green while the surface regrows
# the duplicate pair Alex reported. The feed's own harness mocks `db.execute`,
# so there is no cheap way to execute that route end to end here — the honest
# substitute is to assert the wiring structurally, on the parsed route, rather
# than to assert nothing.
#
# `ast` rather than a substring count: this has to know WHICH arm the call is
# in. A count would stay green if the two calls were swapped, which is precisely
# the failure — Discover would get no quotas and My Stuff would get them.

import ast  # noqa: E402
import pathlib  # noqa: E402


#: `_score_events` tests `my_teams_only` four separate times — cutoff windows,
#: the candidate query, and two later shaping steps. The branch this guard is
#: about is identified by a landmark that belongs to it for an INDEPENDENT
#: reason: the tier-1/2 sport allowlist (BR42/BR43), which exists to stop
#: "Boston" matching Boston College hockey. Anchoring on the dedup call instead
#: would make the guard assert its own premise.
_MY_STUFF_ARM_LANDMARK = "MY_STUFF_ALLOWED_SPORT_KEYS"


def _score_events_arms():
    """The two branches of `_score_events`'s candidate-query `if my_teams_only:`."""
    src = pathlib.Path(
        pathlib.Path(__file__).parent.parent / "app" / "routes" / "feed.py"
    ).read_text()
    tree = ast.parse(src)

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != "_score_events":
            continue
        for stmt in ast.walk(node):
            if (
                isinstance(stmt, ast.If)
                and isinstance(stmt.test, ast.Name)
                and stmt.test.id == "my_teams_only"
            ):
                body = "\n".join(ast.unparse(s) for s in stmt.body)
                if _MY_STUFF_ARM_LANDMARK in body:
                    found.append(
                        (body, "\n".join(ast.unparse(s) for s in stmt.orelse))
                    )

    assert len(found) == 1, (
        f"expected exactly one `if my_teams_only:` arm carrying "
        f"{_MY_STUFF_ARM_LANDMARK}, found {len(found)}. The route was "
        f"restructured, so this guard is stale and My Stuff's duplicate "
        f"protection needs re-checking by hand rather than silently."
    )
    return found[0]


def test_the_my_stuff_arm_calls_the_collapse():
    """THE ship, asserted where it can actually be deleted."""
    my_stuff_arm, _ = _score_events_arms()
    assert "deduplicated_event_ids(" in my_stuff_arm


def test_the_discover_arm_still_gets_the_quotas():
    """The control: the repair must not move Discover onto the quota-less pass.

    The two arms want different things — My Stuff is already bounded to one
    user's teams, Discover is not — so a swap here would be silent in every
    other test and would re-open #2065 on the flagship surface.
    """
    my_stuff_arm, discover_arm = _score_events_arms()
    assert "event_candidate_ids(" in discover_arm
    assert "deduplicated_event_ids(" not in discover_arm
    assert "event_candidate_ids(" not in my_stuff_arm


def test_the_my_stuff_arm_keeps_its_own_safety_cap():
    """The collapse replaces no existing bound. 200 is the pool's only ceiling
    now that the quotas are deliberately not inherited, so losing it would make
    a user with many teams unbounded."""
    my_stuff_arm, _ = _score_events_arms()
    assert "limit(200)" in my_stuff_arm
