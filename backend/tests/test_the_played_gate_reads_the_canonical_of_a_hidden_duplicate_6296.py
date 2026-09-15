"""A MATCH THAT IS OVER STOPS BEING OFFERED AS FIVE OPEN QUESTIONS. #6296.

`https://bainluck.com/search?q=Townsend`, production, 390px, 2026-09-14 20:5xZ.
The third game card reads **WTA GUADALAJARA OPEN · Sep 14 · FINAL · Maria 1 – 2
Townsend**. Three inches below it, the ANSWERS block offers the same match as
five open questions, each dated **Sep 20**:

    Set 1 Winner: Maria vs Townsend ........................ No 63%
    Set 2 Winner: Maria vs Townsend ........................ No 69%
    Guadalajara Open Akron: Completed Match: Tatjana Maria . No 94%
    Set Handicap: Townsend (-1.5) vs Maria (+1.5) .......... No 51%

#4914's `_futures_game_already_played()` was already wired into both pools and
did not see them, because the markets do not hang off the match the reader is
looking at. They hang off its hidden duplicate:

    canonical (printed) .. 15312415  completed  1-2  0 markets of its own
    ghost (never printed)  15311057  suspended  ---  7 markets

The ghost carries `provenance:duplicate-of:15312415`. `not_a_proven_duplicate()`
correctly declines to print its card and `folded_event_ids()` correctly folds its
markets onto the canonical's event page — so nothing is lost by suppressing them
here — but the gate asked the ghost, and a ghost never learns its game is over:
the score, the `completed_at` and the `completed` status all land on the
canonical, and the ghost stays `suspended` for ever.

MEASURED ON PRODUCTION 2026-09-15 03:3xZ:

    open markets sitting on a tagged duplicate of a `completed` game ....    25
      of those, `market_tier 1` (the top of the futures ordering) .......     4
    all markets sitting on tagged duplicates ..........................  1,465
      already `resolved`, so never in this pool ........................  1,433
    events carrying MORE than one `duplicate-of` tag ..................      0

WHY THIS IS NOT #5028's GUESS. #4914's docstring declines to suppress the
`suspended` bucket in so many words — *"ZERO of them carry a `completed_at`. We
have not established those games were played."* That is still right, and this
ship does not widen it. It reads the one subset where the evidence exists: the
tag NAMES the row that has already declared the game final.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
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


from app.models import Event, FuturesMarket, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.routes.events import _futures_game_already_played  # noqa: E402
from app.services.anchor_channel import DUPLICATE_TAG_PREFIX, duplicate_tag  # noqa: E402
from app.utils.event_completion import SETTLED_STATUSES  # noqa: E402

# ── The production rows, by id ──────────────────────────────────────────────
CANONICAL_ID = 15312415        # Tatjana Maria v Taylor Townsend, completed 1-2
GHOST_ID = 15311057            # the same match, `suspended`, holding 7 markets
SCHEDULED_CANONICAL_ID = 15312656   # Cardinals v Giants, not yet played
SCHEDULED_GHOST_ID = 15308290       # its StatPal twin, also tagged
PLAIN_SUSPENDED_ID = 15305187       # `suspended`, untagged — #5028's bucket
DIRECTLY_COMPLETED_ID = 15312418    # a completed row holding its own markets

# `duplicate-of:1531` is a prefix of `duplicate-of:15311057`. A settled event
# with the short id must never claim the ghost that names the long one.
SHORT_ID_TWIN = 1531

_T = datetime(2026, 9, 14, 16, 0, tzinfo=timezone.utc)


def _event(event_id, status, *, tags=None):
    return Event(
        id=event_id,
        sport_id=7,
        home_team_name="Tatjana Maria",
        away_team_name="Taylor Townsend",
        commence_time=_T,
        status=status,
        event_tags=tags,
    )


def _market(market_id, event_id, name):
    return FuturesMarket(
        id=market_id,
        source="polymarket",
        external_id=f"ext-{market_id}",
        event_id=event_id,
        name=name,
        category="game_prop",
        status="open",
    )


# The five markets, and what each one is here to prove.
M_ON_GHOST = 60862172             # the specimen — must be suppressed
M_ON_SCHEDULED_GHOST = 61047745   # tomorrow's game — must survive
M_ON_PLAIN_SUSPENDED = 60485360   # #5028's bucket, untouched — must survive
M_UNATTACHED = 60842470           # `event_id IS NULL` — must survive
M_ON_COMPLETED = 61017938         # #4914's own arm — must be suppressed
M_ON_SHORT_PREFIX_GHOST = 60857357  # the prefix trap — must survive


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=7, key="tennis_wta", name="WTA"))
        s.add(_event(CANONICAL_ID, "completed"))
        s.add(_event(GHOST_ID, "suspended", tags=[duplicate_tag(CANONICAL_ID)]))
        s.add(_event(SCHEDULED_CANONICAL_ID, "scheduled"))
        s.add(
            _event(
                SCHEDULED_GHOST_ID,
                "suspended",
                tags=[duplicate_tag(SCHEDULED_CANONICAL_ID)],
            )
        )
        s.add(_event(PLAIN_SUSPENDED_ID, "suspended", tags=["provenance:source:statpal"]))
        s.add(_event(DIRECTLY_COMPLETED_ID, "completed"))
        # The prefix trap: a SETTLED event whose id is a prefix of the ghost's
        # canonical id, and a ghost that names the long id.
        s.add(_event(SHORT_ID_TWIN, "completed"))
        s.add(
            _event(
                GHOST_ID + 1,
                "suspended",
                tags=[duplicate_tag(SCHEDULED_CANONICAL_ID)],
            )
        )

        s.add(_market(M_ON_GHOST, GHOST_ID, "Set 1 Winner: Maria vs Townsend"))
        s.add(_market(M_ON_SCHEDULED_GHOST, SCHEDULED_GHOST_ID, "Cardinals v Giants F5"))
        s.add(_market(M_ON_PLAIN_SUSPENDED, PLAIN_SUSPENDED_ID, "Andorra v Sociedad B"))
        s.add(_market(M_UNATTACHED, None, "Guadalajara Open Akron: Maria vs Townsend"))
        s.add(_market(M_ON_COMPLETED, DIRECTLY_COMPLETED_ID, "Sonmez vs Shymanovich"))
        s.add(_market(M_ON_SHORT_PREFIX_GHOST, GHOST_ID + 1, "Set Handicap: Townsend"))
        s.commit()
    return eng


def _offered(eng, clause):
    with Session(eng) as s:
        return set(
            s.execute(select(FuturesMarket.id).where(clause)).scalars().all()
        )


def _the_4914_arm_alone():
    """#4914 exactly as it shipped, so the new arm's contribution is measured.

    Rebuilt here rather than imported: the point of this control is to be the
    BEFORE state, and a control that reads the code under test cannot be one.
    """
    return ~(
        select(Event.id)
        .where(
            Event.id == FuturesMarket.event_id,
            Event.status.in_(tuple(sorted(SETTLED_STATUSES))),
        )
        .correlate(FuturesMarket)
        .exists()
    )


def _sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


# ---------------------------------------------------------------------------
# 1. The specimen — and the proof that the old predicate let it through
# ---------------------------------------------------------------------------


class TestTheSpecimen:
    def test_the_old_arm_alone_offers_the_finished_match(self, engine):
        """🔴 RED FIRST, on the same rows. If this passes after the fix, the
        fixture stopped reproducing the bug and everything below is decoration.
        """
        assert M_ON_GHOST in _offered(engine, _the_4914_arm_alone())

    def test_the_market_on_the_hidden_duplicate_is_no_longer_offered(self, engine):
        assert M_ON_GHOST not in _offered(engine, _futures_game_already_played())

    def test_the_market_on_a_directly_completed_game_is_still_suppressed(self, engine):
        """#4914's own arm must survive the widening."""
        assert M_ON_COMPLETED not in _offered(engine, _futures_game_already_played())


# ---------------------------------------------------------------------------
# 2. The three populations that must NOT move
# ---------------------------------------------------------------------------


class TestWhatMustStillBeOffered:
    def test_a_ghost_of_a_game_not_yet_played_keeps_its_markets(self, engine):
        """Tomorrow's Cardinals-Giants props hang off a StatPal twin exactly the
        same way. The discriminator is the CANONICAL's state, not the tag.
        """
        assert M_ON_SCHEDULED_GHOST in _offered(engine, _futures_game_already_played())

    def test_an_untagged_suspended_game_keeps_its_markets(self, engine):
        """#5028's 2,597 rows. Nothing here establishes those games were played,
        and this ship does not guess — it reads a tag that names a canonical.
        """
        assert M_ON_PLAIN_SUSPENDED in _offered(engine, _futures_game_already_played())

    def test_an_unattached_market_survives(self, engine):
        """32,483 of the pool carry `event_id IS NULL` (#4914), and the ANSWERS
        block's own headline is one of them (#5261). NOT EXISTS is TRUE on a NULL
        correlation, so they are untouched — by construction, not by luck.
        """
        assert M_UNATTACHED in _offered(engine, _futures_game_already_played())

    def test_a_settled_event_whose_id_is_a_prefix_cannot_claim_the_ghost(self, engine):
        """`duplicate-of:1531` is a prefix of `duplicate-of:15311057`.

        The portable arm quotes the element for this reason and the Postgres arm
        extracts the whole digit run. Drop either and event 1531 — `completed` —
        suppresses a market whose game has not been played.
        """
        assert M_ON_SHORT_PREFIX_GHOST in _offered(
            engine, _futures_game_already_played()
        )


# ---------------------------------------------------------------------------
# 3. The Postgres arm — the one production actually runs
# ---------------------------------------------------------------------------


class TestThePostgresRendering:
    """SQLite runs the portable arm, so every behavioural test above proves the
    WRONG half unless these pin the half production uses.
    """

    def _pg_sql(self):
        return _sql(
            select(FuturesMarket.id).where(
                FuturesMarket.name.ilike("%x%"), _futures_game_already_played()
            )
        )

    def test_the_canonical_is_met_on_its_primary_key(self):
        """Extract-then-primary-key, measured at 15 ms. The portable spelling —
        a LIKE over a concatenated `canonical.id` — is 2,895 ms on the same query
        and times out on the pool's widest shape, so it must never be what
        Postgres compiles to.
        """
        sql = self._pg_sql()
        assert "dup_canonical.id = CAST(SUBSTRING(" in sql, sql
        assert "|| CAST(dup_canonical.id AS VARCHAR)" not in sql, sql

    def test_the_pattern_matches_the_whole_digit_run(self):
        """`([0-9])` would read `1` out of `15312415` and meet a different row."""
        assert f"'{DUPLICATE_TAG_PREFIX}([0-9]+)'" in self._pg_sql()

    def test_the_prefix_is_the_vocabulary_constant_not_a_literal(self):
        """Renaming the tag at its source must move this SQL with it."""
        assert DUPLICATE_TAG_PREFIX in self._pg_sql()

    def test_only_settled_statuses_reach_the_new_arm(self):
        sql = self._pg_sql()
        second = sql[sql.index("dup_canonical") :]
        assert "dup_canonical.status IN ('closed', 'completed')" in second, second
        for never in ("'live'", "'suspended'", "'voided'", "'scheduled'"):
            assert never not in second, f"{never} must not be suppressed: {second}"

    def test_the_new_arm_reads_the_canonical_and_not_the_ghost(self):
        """The one-character mutation that makes the whole ship inert: ask
        `dup_ghost.status` and no ghost is ever settled, so nothing is suppressed.
        """
        sql = self._pg_sql()
        assert "dup_ghost.status" not in sql, sql

    def test_the_predicate_still_survives_an_outer_query_that_joins_events(self):
        """#4914's compile-time crash, re-run against the two-alias shape."""
        sql = _sql(
            select(FuturesMarket.id)
            .join(Event, Event.id == FuturesMarket.event_id)
            .where(_futures_game_already_played())
        )
        assert sql.count("NOT (EXISTS") == 2, sql
        assert "FROM events AS dup_canonical, events AS dup_ghost" in sql, sql
