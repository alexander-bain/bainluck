"""An already-linked Polymarket fixture gets the venue's kickoff (#6073 rung 2).

THE HALF THE FIRST TWO SHAS CANNOT REACH. `a02aca00a` (CERT-2827) made the MINT
read Gamma's `startTime`; lane1b's `f4a2830a5` (CERT-2830) put that instant on
the child row the mint sees. Both are forward only. An event that was ALREADY
minted from Gamma's `startDate` — the LISTING stamp — is corrected by nothing:

* every mint/link phase selects `FuturesMarket.event_id IS NULL`, so a linked
  market never re-enters the registry at all;
* `claim_is_same_record` returns False for `polymarket` unconditionally (no id
  column on `events`), so even a re-offer could not revise the row;
* and a tie loses, so `polymarket` at rank 0 cannot overwrite `polymarket`.

Measured on production 2026-09-14 06:5xZ, the two specimens this defends:

    event      commence_time (listing)  commence_time_source  status
    15312442   2026-09-13 20:14:27Z     polymarket            suspended
    15312412   2026-09-14 01:59:21Z     polymarket            suspended

Group `polymarket:1019271` — parent 60980453 holds `venue_game_start`
2026-09-14T09:00:00Z; its six children hold the `event_id` and, until
`f4a2830a5` lands, no stamp. 12.8 hours. The page badged LIVE at 04:55Z for a
match the venue had not started, then walked into `suspended`, which the event
page renders as "No result reported" for a match nobody had played.

WHAT EACH TEST DEFENDS

* the ship, end to end through the real `_phase15_revalidate`
  (`test_phase15_redates_the_production_specimen_from_listing_stamp_to_venue_kickoff`);
* that it reaches the specimen ROWS, not a convenient sibling — the two
  production markets `is_game_level_market` calls False
  (`test_the_two_non_game_level_specimen_rows_still_carry_the_correction`);
* the load-bearing refusal: a schedule-sourced event is never re-timed by a
  Polymarket prop (`test_an_event_dated_by_*`, four sources plus unknown);
* DIRECTIONALITY — the listing stamp can never come back over the venue instant
  (`test_the_listing_stamp_can_never_overwrite_the_venue_instant`);
* the rank NOT moving, so the schedule sources still outrank both
  (`test_the_schedule_sources_still_outrank_the_venue_instant`);
* inertness before lane1b's input lands (`test_a_child_row_with_no_stamp_yet_is_left_alone`);
* no churn on agreement (`test_an_event_already_on_the_venue_instant_is_not_rewritten`);
* the #46 inversion guard surviving its extraction, both ways
  (`test_a_scored_completed_event_refuses_the_correction`,
  `test_an_unscored_staleness_artifact_is_voided_by_the_correction`);
* the extraction not changing the registry's own behaviour
  (`test_the_registry_path_still_applies_and_still_refuses_the_inversion`);
* one key, three readers, so ingest and matcher cannot drift
  (`test_the_stamp_key_is_read_by_the_mint_chooser_and_the_redate_alike`).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.services.event_registry import (
    apply_authorized_commence_time,
    commence_time_write_authorized,
    polymarket_venue_corrects_its_own_listing,
)
from app.tasks.prediction_market_matching import (
    POLYMARKET_VENUE_COMMENCE_SOURCE,
    polymarket_venue_redate,
    venue_game_start,
)


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "TEXT"


# ── The production specimen, verbatim (read 2026-09-14) ──────────────────────
HOME = "Mazzola"
AWAY = "Zeltina"
#: Gamma's `startDate`, the moment the market was published.
LISTING_STAMP = datetime(2026, 9, 13, 20, 14, 27, tzinfo=timezone.utc)
#: Gamma's `startTime`, the instant the venue starts the match. 12.8h later.
VENUE_KICKOFF = datetime(2026, 9, 14, 9, 0, 0, tzinfo=timezone.utc)
#: The two market names `is_game_level_market` MEASURES False, and the one it
#: does not. All three are `category='game_prop'` children of one Gamma event.
NOT_GAME_LEVEL = (
    "W50 Pazardzhik: Alessandra Mazzola vs Beatrise Zeltina",
    "Set 1 Winner: Alessandra Mazzola vs Beatrise Zeltina",
)
GAME_LEVEL = "Alessandra Mazzola vs. Beatrise Zeltina: Total Sets O/U 2.5"

NOW = datetime(2026, 9, 14, 6, 30, tzinfo=timezone.utc)


class _AsyncShim:
    """Async surface over a real sync session (no aiosqlite in this sandbox)."""

    def __init__(self, session):
        self._s = session

    async def execute(self, statement, *a, **k):
        return self._s.execute(statement, *a, **k)

    def add(self, obj):
        self._s.add(obj)

    async def commit(self):
        self._s.commit()

    async def flush(self):
        self._s.flush()


def _new_rail():
    from sqlalchemy import create_engine
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    from app.models.models import (
        Base, Event, FuturesMarket, Sport, Team, WinProbSnapshot,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Sport.__table__, Event.__table__, Team.__table__,
            FuturesMarket.__table__, WinProbSnapshot.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    tennis = Sport(key="tennis_other", name="Tennis (other)")
    session.add(tennis)
    session.flush()
    return session, tennis


def _event(
    session, sport, *, commence=LISTING_STAMP, source="polymarket",
    status="suspended", completed_at=None, home_score=None, away_score=None,
):
    """The minted row. `external_id` is NULL, exactly as production has it."""
    from app.models.models import Event

    e = Event(
        sport_id=sport.id, home_team_name=HOME, away_team_name=AWAY,
        commence_time=commence, commence_time_source=source, status=status,
        external_id=None, completed_at=completed_at,
        home_score=home_score, away_score=away_score,
    )
    session.add(e)
    session.flush()
    return e


def _market(
    session, event, *, name=GAME_LEVEL, external_id="60980454",
    venue_start=VENUE_KICKOFF, source="polymarket",
):
    from app.models.models import FuturesMarket

    meta = {}
    if venue_start is not None:
        meta["venue_game_start"] = venue_start.isoformat().replace("+00:00", "Z")
    m = FuturesMarket(
        source=source, external_id=external_id, name=name,
        category="game_prop", status="open", event_id=event.id,
        sport_id=event.sport_id, llm_sport_category="tennis",
        group_id="polymarket:1019271", group_type="polymarket_sub_market",
        market_metadata=meta,
    )
    session.add(m)
    session.commit()
    return m


async def _run_phase15(session):
    """Run the ACTUAL entry point.

    `_find_matching_event` is pinned to None — "no better match" — which is the
    state the specimen is really in and which sends the pass down the arm that
    leaves an auto-created row alone. The redate must not depend on the scorer.
    """
    from app.tasks import prediction_market_matching as task_mod

    stats = {
        "orphaned_snapshots_deleted": 0,
        "funnel": {"stale_relinked": 0, "mislink_fixed": 0},
    }
    with patch.object(
        task_mod, "_find_matching_event", new=AsyncMock(return_value=None),
    ):
        await task_mod._phase15_revalidate(
            _AsyncShim(session), stats, NOW, lambda: 600.0, [],
        )
    session.commit()
    return stats


# ── The ship ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_phase15_redates_the_production_specimen_from_listing_stamp_to_venue_kickoff():
    session, tennis = _new_rail()
    event = _event(session, tennis)
    _market(session, event)

    stats = await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == VENUE_KICKOFF
    assert event.commence_time_source == POLYMARKET_VENUE_COMMENCE_SOURCE
    assert stats["funnel"]["phase15_pm_venue_corrected"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("name", NOT_GAME_LEVEL)
async def test_the_two_non_game_level_specimen_rows_still_carry_the_correction(name):
    """Placement, not luck.

    `is_game_level_market` returns False for both of these production names, so
    an arm sitting below that gate would fix the specimen only when the shard
    happened to hold the O/U sibling. Asserted per row rather than in one pass,
    because a pass holding all three cannot tell which one did the work.
    """
    from app.utils.prediction_market_matching import is_game_level_market

    assert is_game_level_market(name, "game_prop", external_id="60980454") is False

    session, tennis = _new_rail()
    event = _event(session, tennis)
    _market(session, event, name=name)

    await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == VENUE_KICKOFF


# ── The stamp is on the PARENT (lane1b/237, production 07:30Z) ───────────────

def _parent(session, event, *, venue_start=VENUE_KICKOFF, external_id="60980453"):
    """The Gamma EVENT row: carries the stamp, carries NO link.

    `_phase15_eligible_where` requires `event_id IS NOT NULL`, so this row is
    never iterated by the pass. That is the whole shape of the finding.
    """
    from app.models.models import FuturesMarket

    meta = {}
    if venue_start is not None:
        meta["venue_game_start"] = venue_start.isoformat().replace("+00:00", "Z")
    p = FuturesMarket(
        source="polymarket", external_id=external_id,
        name="W50 Pazardzhik: Alessandra Mazzola vs Beatrise Zeltina",
        category="game", status="open", event_id=None,
        sport_id=event.sport_id, llm_sport_category="tennis",
        group_id="polymarket:1019271", group_type="polymarket_event",
        market_metadata=meta,
    )
    session.add(p)
    session.commit()
    return p


@pytest.mark.asyncio
async def test_the_specimen_is_repaired_from_the_parents_stamp_not_the_childs_6073():
    """The production shape, exactly: parent stamped, every child bare.

    Read on production 07:30Z, both repairable specimens — `polymarket:1019271`
    (6 children) and `polymarket:1020508` (1 child) — carry
    `venue_game_start` on the PARENT and on **zero** children. A rail reading
    only the iterated row's own metadata therefore corrects neither, and would
    correct them only if and when Gamma re-serves the group; the STALE group is
    exactly the population #6073 is about. This is the test that fails on the
    own-row-only read and passes on the group-wide one.
    """
    session, tennis = _new_rail()
    event = _event(session, tennis)
    _market(session, event, venue_start=None)   # linked child, no stamp
    _parent(session, event)                     # unlinked parent, stamped

    stats = await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == VENUE_KICKOFF
    assert event.commence_time_source == POLYMARKET_VENUE_COMMENCE_SOURCE
    assert stats["funnel"]["phase15_pm_venue_corrected"] == 1


@pytest.mark.asyncio
async def test_a_group_with_no_stamp_anywhere_is_still_left_alone_6073():
    """The group read widens WHERE we look, never WHETHER we may write."""
    session, tennis = _new_rail()
    event = _event(session, tennis)
    _market(session, event, venue_start=None)
    _parent(session, event, venue_start=None)

    await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == LISTING_STAMP


@pytest.mark.asyncio
async def test_the_parent_is_read_once_per_group_not_once_per_sibling_6073():
    """Six bare children must not buy six identical parent queries a beat."""
    from app.tasks.prediction_market_matching import polymarket_group_venue_start

    session, tennis = _new_rail()
    event = _event(session, tennis)
    children = [
        _market(session, event, venue_start=None, external_id=f"6098045{i}")
        for i in range(4, 10)
    ]
    _parent(session, event)

    shim = _AsyncShim(session)
    calls = {"n": 0}
    real_execute = shim.execute

    async def _counting_execute(statement, *a, **k):
        calls["n"] += 1
        return await real_execute(statement, *a, **k)

    shim.execute = _counting_execute
    cache: dict = {}
    answers = [
        await polymarket_group_venue_start(shim, child, cache)
        for child in children
    ]

    assert answers == [VENUE_KICKOFF] * 6
    assert calls["n"] == 1, "the cache is per group, not per row"


# ── The interleave (CERT-2834, carried over before it is found twice) ─────────

@pytest.mark.asyncio
async def test_score_arriving_after_redate_selection_cannot_be_reset_to_scheduled_6073():
    """A real result landing mid-pass must never be voided by a stale read.

    The dangerous branch: `apply_authorized_commence_time` decides "staleness
    artifact" from the IN-MEMORY status/scores/completed_at and then writes
    `status='scheduled'` + `completed_at=None`. This pass loads its rows in one
    batch before the loop and commits once at the end, so that decision can be
    minutes old by the time it is written.

    The score is landed with raw SQL, deliberately: it must reach the DB WITHOUT
    touching the identity map, which is precisely how a concurrent writer's
    commit appears to this session. It is landed from inside the group read —
    the one await between the load and the write — so the interleave is real
    rather than arranged before the pass starts.
    """
    from sqlalchemy import text

    from app.tasks import prediction_market_matching as task_mod

    session, tennis = _new_rail()
    event = _event(
        session, tennis, status="closed",
        completed_at=VENUE_KICKOFF - timedelta(hours=2),
    )
    _market(session, event)
    event_id = event.id

    real_group_read = task_mod.polymarket_group_venue_start

    async def _score_lands_then_read(inner_session, market, cache=None):
        inner_session._s.execute(
            text(
                "UPDATE events SET home_score = 2, away_score = 1, "
                "status = 'completed' WHERE id = :i"
            ),
            {"i": event_id},
        )
        inner_session._s.commit()
        return await real_group_read(inner_session, market, cache)

    with patch.object(
        task_mod, "polymarket_group_venue_start", new=_score_lands_then_read,
    ):
        stats = await _run_phase15(session)

    row = session.execute(
        text("SELECT status, home_score, away_score, commence_time FROM events "
             "WHERE id = :i"),
        {"i": event_id},
    ).one()
    assert row.status == "completed", "a finished game was un-settled by a stale read"
    assert (row.home_score, row.away_score) == (2, 1)
    assert str(row.commence_time).startswith("2026-09-13 20:14:27")
    assert stats["funnel"]["phase15_pm_venue_redate_refused_row_moved"] == 1
    assert "phase15_pm_venue_corrected_and_voided" not in stats["funnel"]


@pytest.mark.asyncio
async def test_an_untouched_row_still_passes_the_unmoved_assertion_6073():
    """The premise check must refuse a MOVED row, not every row — and it hands
    back the RAW tuple the conditional write needs."""
    from app.tasks.prediction_market_matching import phase15_event_row_is_unmoved

    session, tennis = _new_rail()
    event = _event(session, tennis)
    _market(session, event)

    unmoved, observed = await phase15_event_row_is_unmoved(_AsyncShim(session), event)
    assert unmoved is True
    assert observed.status == "suspended"
    assert (observed.home_score, observed.away_score) == (None, None)


@pytest.mark.asyncio
async def test_score_committed_after_freshness_check_cannot_be_reset_to_scheduled_6073():
    """CERT-2836: narrowing the window is not closing it.

    The freshness SELECT is a PREMISE, not a protection — a writer that commits
    AFTER it still beats a separate write. So the comparison lives in the
    statement: every column the decision read is repeated in the UPDATE's WHERE
    against the value the database served, and the database decides in one
    breath whether the row it is changing is still the row that was reasoned
    about.

    The score is committed from inside `phase15_event_row_is_unmoved`'s own
    return path, which is strictly later than the interleave the previous
    presentation survived — it lands after the check has already answered
    "unmoved", which is the exact ordering CERT-2836 drove.
    """
    from sqlalchemy import text

    from app.tasks import prediction_market_matching as task_mod

    session, tennis = _new_rail()
    event = _event(
        session, tennis, status="closed",
        completed_at=VENUE_KICKOFF - timedelta(hours=2),
    )
    _market(session, event)
    event_id = event.id

    real_check = task_mod.phase15_event_row_is_unmoved

    async def _check_then_score_lands(inner_session, inner_event):
        answer = await real_check(inner_session, inner_event)
        inner_session._s.execute(
            text(
                "UPDATE events SET home_score = 2, away_score = 1, "
                "status = 'completed' WHERE id = :i"
            ),
            {"i": event_id},
        )
        inner_session._s.commit()
        return answer

    with patch.object(
        task_mod, "phase15_event_row_is_unmoved", new=_check_then_score_lands,
    ):
        stats = await _run_phase15(session)

    row = session.execute(
        text("SELECT status, home_score, away_score, commence_time FROM events "
             "WHERE id = :i"),
        {"i": event_id},
    ).one()
    assert row.status == "completed", "a finished game was un-settled by a lost race"
    assert (row.home_score, row.away_score) == (2, 1)
    assert str(row.commence_time).startswith("2026-09-13 20:14:27")
    assert stats["funnel"]["phase15_pm_venue_redate_lost_race"] == 1
    assert "phase15_pm_venue_corrected_and_voided" not in stats["funnel"]


@pytest.mark.asyncio
async def test_the_uncontested_write_still_lands_and_is_counted_once_6073():
    """The twin without which `WHERE false` passes the whole file.

    A conditional write that declines EVERYTHING satisfies every race test ever
    written. This is the arm that says the statement still writes when nobody is
    competing with it — same artifact-void path as the race test above, so the
    two differ in exactly one thing: whether a writer interleaved.
    """
    session, tennis = _new_rail()
    event = _event(
        session, tennis, status="closed",
        completed_at=VENUE_KICKOFF - timedelta(hours=2),
    )
    _market(session, event)

    stats = await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == VENUE_KICKOFF
    assert event.status == "scheduled"
    assert event.completed_at is None
    assert stats["funnel"]["phase15_pm_venue_corrected_and_voided"] == 1
    assert "phase15_pm_venue_redate_lost_race" not in stats["funnel"]


@pytest.mark.asyncio
async def test_the_written_row_is_in_sync_in_memory_and_still_not_dirty_6073():
    """`set_committed_value`, and why it is not `setattr`.

    Two failures this catches, and they pull in opposite directions. Leave the
    in-memory row alone and the rest of the iteration reasons on a status the
    database no longer holds — the artifact void writes `scheduled`, the object
    still says `closed`, and the mislink arms a hundred lines below read the
    stale one. Use a plain `setattr` instead and the row goes DIRTY, so the
    pass's end commit re-writes those same columns UNCONDITIONALLY, which is
    precisely the defect the conditional statement exists to remove — the
    conditional write would be correct and then quietly overwritten by an
    unconditional one.

    `set_committed_value` is the only thing that does both: the object reads as
    the database now reads, and SQLAlchemy is told it came from there.
    """
    from app.tasks.prediction_market_matching import (
        phase15_event_row_is_unmoved,
        phase15_redate_compare_and_write,
    )

    session, tennis = _new_rail()
    event = _event(
        session, tennis, status="closed",
        completed_at=VENUE_KICKOFF - timedelta(hours=2),
    )
    shim = _AsyncShim(session)
    _unmoved, observed = await phase15_event_row_is_unmoved(shim, event)
    assert _unmoved is True

    wrote = await phase15_redate_compare_and_write(
        shim, event,
        {
            "commence_time": VENUE_KICKOFF,
            "commence_time_source": POLYMARKET_VENUE_COMMENCE_SOURCE,
            "status": "scheduled",
            "completed_at": None,
        },
        observed,
    )

    assert wrote is True
    assert event.status == "scheduled", "the in-memory row was left stale"
    assert event.completed_at is None
    assert event.commence_time == VENUE_KICKOFF
    assert event not in session.dirty, (
        "the row must not be dirty — a pending flush would re-write these "
        "columns unconditionally at the end of the pass"
    )


@pytest.mark.asyncio
async def test_the_voids_two_extra_columns_reach_the_DATABASE_not_just_the_object_6073():
    """The chained `.values()` arms, asserted where dropping one would show.

    The sibling test above reads `event.status` — and that is set by
    `set_committed_value` off the SAME map the statement was built from, so it
    says "scheduled" whether or not the column reached the row. Drop the
    `if "status" in writes` arm and that test still passes, the object still
    reads scheduled for the rest of the pass, and the database keeps a FINAL
    badge on a match nobody has played: the exact defect #6073 is about,
    surviving inside a green suite.

    So this one goes around the identity map entirely and asks the table what it
    holds. All four columns, one statement.
    """
    from sqlalchemy import text

    from app.tasks.prediction_market_matching import (
        phase15_event_row_is_unmoved,
        phase15_redate_compare_and_write,
    )

    session, tennis = _new_rail()
    event = _event(
        session, tennis, status="closed",
        completed_at=VENUE_KICKOFF - timedelta(hours=2),
    )
    shim = _AsyncShim(session)
    _unmoved, observed = await phase15_event_row_is_unmoved(shim, event)

    wrote = await phase15_redate_compare_and_write(
        shim, event,
        {
            "commence_time": VENUE_KICKOFF,
            "commence_time_source": POLYMARKET_VENUE_COMMENCE_SOURCE,
            "status": "scheduled",
            "completed_at": None,
        },
        observed,
    )
    assert wrote is True

    row = session.execute(
        text(
            "SELECT status, completed_at, commence_time, commence_time_source "
            "FROM events WHERE id = :i"
        ),
        {"i": event.id},
    ).first()
    assert row.status == "scheduled", "the void's status never reached the table"
    assert row.completed_at is None, "the void's completion clear never landed"
    # Raw SQLite hands back the text it stored, which carries the microsecond
    # field the Python value does not print; the instant is what is asserted.
    assert str(row.commence_time).startswith(
        str(VENUE_KICKOFF.replace(tzinfo=None))
    ), row.commence_time
    assert row.commence_time_source == POLYMARKET_VENUE_COMMENCE_SOURCE


@pytest.mark.asyncio
async def test_a_column_this_site_was_not_written_for_is_refused_not_persisted_6073():
    """The write site's column vocabulary is closed, and closed LOUDLY.

    This statement bypasses `_update_fields_by_priority` deliberately, so nothing
    stands between `authorized_commence_time_write`'s return value and the row.
    A column added there for a different caller would otherwise arrive here and
    be persisted under a WHERE clause that was never reasoned about for it — and
    if it were `win_probability_sources`, a reading written around
    `stamp_source_reading` keeps full weight in the hero average forever (#1829),
    with nothing going red.

    The refusal is an exception rather than a silent drop because the wrapper
    files it as `phase15_pm_venue_redate_write_error_ValueError`: a structural
    fault in the pair says so in the funnel instead of thinning a rail.
    """
    from app.tasks.prediction_market_matching import (
        PHASE15_REDATE_COLUMNS,
        phase15_event_row_is_unmoved,
        phase15_redate_compare_and_write,
    )

    assert set(PHASE15_REDATE_COLUMNS) == {
        "commence_time", "commence_time_source", "status", "completed_at",
    }, "the vocabulary widened — say why in the docstring, then update this"

    session, tennis = _new_rail()
    event = _event(session, tennis)
    shim = _AsyncShim(session)
    _unmoved, observed = await phase15_event_row_is_unmoved(shim, event)

    with pytest.raises(ValueError, match="refuses columns"):
        await phase15_redate_compare_and_write(
            shim, event,
            {
                "commence_time": VENUE_KICKOFF,
                "commence_time_source": POLYMARKET_VENUE_COMMENCE_SOURCE,
                "win_probability_sources": {"polymarket": {"probability": 0.5}},
            },
            observed,
        )

    session.expire_all()
    refreshed = session.get(type(event), event.id)
    assert refreshed.commence_time.replace(tzinfo=timezone.utc) == LISTING_STAMP, (
        "the refusal must write NOTHING, not the subset it recognised"
    )


@pytest.mark.asyncio
async def test_a_statement_the_driver_refuses_is_counted_and_shouted_not_swallowed_6073():
    """A rail that cannot execute must not read as a rail that found nothing.

    Phase 1.5's loop body ends in `except Exception: logger.debug(...)`, which is
    right for one bad row and catastrophic for a statement the driver refuses:
    that would be a debug line per row, every 15 minutes, forever — dead in
    production, green in CI, invisible in the funnel. The counter carries the
    exception's class name so the funnel says WHICH fault without a reproduction,
    and it must be distinct from `lost_race`, which is a healthy outcome.
    """
    from app.tasks import prediction_market_matching as task_mod

    session, tennis = _new_rail()
    event = _event(session, tennis)
    _market(session, event)

    async def _driver_refuses(*a, **k):
        raise TypeError("could not determine data type of parameter $1")

    with patch.object(
        task_mod, "phase15_redate_compare_and_write", new=_driver_refuses,
    ):
        stats = await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == LISTING_STAMP
    assert stats["funnel"]["phase15_pm_venue_redate_write_error_TypeError"] == 1
    assert "phase15_pm_venue_redate_lost_race" not in stats["funnel"], (
        "a statement fault must not be filed as a healthy lost race"
    )
    assert "phase15_pm_venue_corrected" not in stats["funnel"]
    assert stats["funnel"]["phase15_checked"] == 1, "the pass must carry on"


def test_the_redate_write_is_conditional_in_the_statement_not_in_python_6073():
    """The WHERE carries all six columns, and it is asked of the SQL itself.

    A behavioural test cannot tell a conditional statement from an unconditional
    one that happened not to race, and in a sandbox with no second connection it
    cannot see a true concurrent commit at all. So this reads the statement the
    SHIPPED function emits — captured off a recording session, never rebuilt here,
    because a rebuilt statement asserts what the test author believes rather than
    what production sends — and compiles it for POSTGRES, which is the dialect
    that actually runs it.

    Three properties, all load-bearing. The five volatile columns are in the
    WHERE beside the id, so the database is the thing deciding. The NULL
    comparisons render as `IS NULL`, never `= NULL` — the `=` form is never true
    and all three of those columns are NULL across the specimen population, so it
    would decline every row the repair exists for while reporting perfect
    success. And every non-NULL comparison is NULL-safe too, against a bind
    anchored to its column so the type comes from the column rather than from the
    Python value.
    """
    from sqlalchemy.dialects import postgresql

    from app.tasks.prediction_market_matching import (
        phase15_redate_compare_and_write,
    )

    captured = {}

    class _Recorder:
        async def execute(self, statement, *a, **k):
            captured["stmt"] = statement
            return SimpleNamespace(rowcount=0)   # decline: no ORM row to touch

    observed = SimpleNamespace(
        status="closed", home_score=None, away_score=None,
        completed_at=datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc),
        commence_time=LISTING_STAMP,
        # CERT-2849's required repair: the AUTHORITY column joined the tuple.
        commence_time_source="polymarket",
    )
    wrote = asyncio.run(phase15_redate_compare_and_write(
        _Recorder(), SimpleNamespace(id=15312442),
        {"commence_time": VENUE_KICKOFF, "commence_time_source": "x"},
        observed,
    ))
    assert wrote is False, "rowcount 0 must be reported as a lost race"

    sql = str(captured["stmt"].compile(dialect=postgresql.dialect()))
    assert sql.startswith("UPDATE events SET")
    where = sql.split(" WHERE ", 1)[1]
    for column in (
        "events.status", "events.home_score", "events.away_score",
        "events.completed_at", "events.commence_time",
        # CERT-2849: the column that AUTHORIZES the write is part of the row the
        # statement is conditional on, or a higher authority can be overwritten
        # without any other column moving.
        "events.commence_time_source",
    ):
        assert column in where, f"{column} is not in the shipped WHERE"
    assert "= NULL" not in where
    assert where.count("IS NULL") == 2, (
        "the two NULL scores must compare NULL-safely, as IS NULL"
    )
    for valued in ("events.status", "events.completed_at", "events.commence_time"):
        clause = where.split(valued + " ", 1)[1].split(" AND ")[0]
        assert clause.startswith("IS NOT DISTINCT FROM %("), (
            f"{valued} is not compared NULL-safely against a bind: {clause!r}"
        )


# ── The link validation (CERT-2835) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_phase15_mislink_is_detached_without_retiming_the_wrong_event_6073():
    """A detach that leaves the damage behind is not a detach.

    CERT-2835's reproduction, kept as its own specimen: a same-sport Polymarket
    market for two OTHER players sitting on the Mazzola-Zeltina event. Every
    condition in `polymarket_venue_redate` reads True on it — they are all about
    the date, and `commence_time_source == 'polymarket'` says a Polymarket row
    wrote this start, not that THIS one did. Phase 1.5 then detaches it correctly
    a hundred lines later, which is far too late if the instant is already
    written: the event keeps a start belonging to a match it has nothing to do
    with, and no beat ever visits it again to take it back (the market that
    would have is now unlinked).

    Both halves are asserted in one pass on purpose — the detach is what makes
    the write unrecoverable, so a test that only checked the date would pass on
    an implementation that never detached at all.
    """
    session, tennis = _new_rail()
    event = _event(session, tennis)
    stray = _market(
        session, event,
        name="Serena Williams vs. Coco Gauff",
        external_id="60989999",
    )

    stats = await _run_phase15(session)

    session.refresh(event)
    session.refresh(stray)
    assert event.commence_time.replace(tzinfo=timezone.utc) == LISTING_STAMP
    assert event.commence_time_source == "polymarket"
    assert stray.event_id is None, "the mislink arm must still detach it"
    assert stats["funnel"]["phase15_pm_venue_redate_refused_teams_absent"] == 1
    assert "phase15_pm_venue_corrected" not in stats["funnel"]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", NOT_GAME_LEVEL)
async def test_the_validation_admits_the_non_game_level_specimen_rows_6073(name):
    """The twin of the test above, and the reason it is not matchup-gated.

    `extract_matchup_with_ticker_fallback` returns None for BOTH production
    specimen names, so validating through the grammar the mislink arm uses would
    have refused exactly the two rows this ship is for — shipping a correction
    reachable only when the shard happens to hold the O/U sibling. Containment on
    the raw name answers both questions: the surnames are in a prop's name, and
    they are not in a market about two other players.
    """
    from app.tasks.prediction_market_matching import (
        extract_matchup_with_ticker_fallback,
        phase15_link_is_valid_for_redate,
    )

    assert extract_matchup_with_ticker_fallback(
        name, external_id="60980454",
    ) is None, "if the grammar starts reading these, say so here first"

    session, tennis = _new_rail()
    event = _event(session, tennis)
    market = _market(session, event, name=name)

    ok, why = await phase15_link_is_valid_for_redate(
        _AsyncShim(session), market, event,
    )
    assert (ok, why) == (True, "ok")

    stats = await _run_phase15(session)
    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == VENUE_KICKOFF
    assert stats["funnel"]["phase15_pm_venue_corrected"] == 1


@pytest.mark.asyncio
async def test_a_market_naming_only_one_of_the_two_players_is_refused_6073():
    """BOTH, not either — the realistic mislink, and the one a half-check admits.

    A stray naming neither player is refused by any spelling of this test. A
    stray that shares ONE player with the event is the shape a same-tournament
    mislink actually takes ("Mazzola vs Gauff" landing on Mazzola-Zeltina), and
    it is the only one that tells a two-sided check from a one-sided one.
    """
    from app.tasks.prediction_market_matching import (
        phase15_link_is_valid_for_redate,
    )

    session, tennis = _new_rail()
    event = _event(session, tennis)
    market = _market(
        session, event,
        name="Alessandra Mazzola vs. Coco Gauff",
        external_id="60987777",
    )

    ok, why = await phase15_link_is_valid_for_redate(
        _AsyncShim(session), market, event,
    )
    assert (ok, why) == (False, "teams_absent")

    await _run_phase15(session)
    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == LISTING_STAMP


@pytest.mark.asyncio
async def test_colliding_team_names_across_sports_do_not_pass_the_validation_6073():
    """Condition 1 alone is not enough — the "Royals" case it cannot see.

    Two clubs in different sports can share a name, which is why the mislink arm
    below carries a cross-sport check of its own rather than trusting the teams.
    The validation reads the same pair (`_market_sport_prefix` against
    `Sport.key`) so a redate can never be admitted by an agreement the pass
    itself would call a mislink.
    """
    from app.models.models import Sport
    from app.tasks.prediction_market_matching import (
        phase15_link_is_valid_for_redate,
    )

    session, _tennis = _new_rail()
    cricket = Sport(key="cricket_other", name="Cricket (other)")
    session.add(cricket)
    session.flush()

    event = _event(session, cricket)
    event.home_team_name = "Rajasthan Royals"
    event.away_team_name = "Chennai Super Kings"
    session.flush()
    market = _market(
        session, event,
        name="Rajasthan Royals vs. Chennai Super Kings",
        external_id="60988888",
    )
    market.llm_sport_category = "baseball"
    session.commit()

    ok, why = await phase15_link_is_valid_for_redate(
        _AsyncShim(session), market, event,
    )
    assert (ok, why) == (False, "cross_sport")

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == LISTING_STAMP


@pytest.mark.asyncio
async def test_an_event_with_no_team_names_is_refused_not_assumed_6073():
    """Nothing to agree with is a refusal, never a pass-through."""
    from app.tasks.prediction_market_matching import (
        phase15_link_is_valid_for_redate,
    )

    session, tennis = _new_rail()
    event = _event(session, tennis)
    event.away_team_name = ""
    session.flush()
    market = _market(session, event)

    ok, why = await phase15_link_is_valid_for_redate(
        _AsyncShim(session), market, event,
    )
    assert (ok, why) == (False, "unnamed")


# ── The load-bearing refusal ─────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source", ["odds_api", "espn", "statpal", "mlb_schedule_repair", None],
)
async def test_an_event_dated_by_a_schedule_source_is_never_retimed(source):
    """A Polymarket prop may not move a start it does not own.

    `None` is in the list on purpose: unknown provenance is most of the table and
    much of it predates `commence_time_source`. The registry's "unknown confers
    no immunity" rule is about OUTRANKING, and this is not that.
    """
    session, tennis = _new_rail()
    event = _event(session, tennis, source=source, status="scheduled")
    _market(session, event)

    await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == LISTING_STAMP
    assert event.commence_time_source == source


@pytest.mark.asyncio
async def test_a_kalshi_market_never_redates_even_carrying_the_key():
    """The source gate is real. Only `tasks.polymarket` writes that stamp."""
    session, tennis = _new_rail()
    event = _event(session, tennis)
    _market(session, event, source="kalshi", external_id="KXTENNIS-26SEP14MZ")

    await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == LISTING_STAMP


def test_the_listing_stamp_can_never_overwrite_the_venue_instant():
    """DIRECTIONAL. This is why the clause is not `same_record_revision`."""
    assert polymarket_venue_corrects_its_own_listing(
        "polymarket", POLYMARKET_VENUE_COMMENCE_SOURCE
    ) is True
    assert polymarket_venue_corrects_its_own_listing(
        POLYMARKET_VENUE_COMMENCE_SOURCE, "polymarket"
    ) is False
    authorized, _ = commence_time_write_authorized(
        POLYMARKET_VENUE_COMMENCE_SOURCE, "polymarket",
    )
    assert authorized is False


def test_gamma_may_revise_its_own_venue_instant():
    """A fixture that moves. The tie rule would otherwise freeze reading one."""
    authorized, why = commence_time_write_authorized(
        POLYMARKET_VENUE_COMMENCE_SOURCE, POLYMARKET_VENUE_COMMENCE_SOURCE,
    )
    assert authorized is True
    assert "fixture instant" in why


def test_the_schedule_sources_still_outrank_the_venue_instant():
    """The rank did NOT move, and that is deliberate — a venue's own fixture
    time is a good start, not a better one than a schedule's."""
    for better in ("odds_api", "statpal", "espn", "mlb_schedule_repair"):
        authorized, _ = commence_time_write_authorized(
            POLYMARKET_VENUE_COMMENCE_SOURCE, better,
        )
        assert authorized is True, better


# ── Inertness and no-churn ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_child_row_with_no_stamp_yet_is_left_alone():
    """Today's production state, before lane1b's `f4a2830a5` reaches the child.

    No stamp is indistinguishable from a venue that publishes no fixture time,
    and both mean CHANGE NOTHING — the same trade the #4965 linkage guard makes.
    """
    session, tennis = _new_rail()
    event = _event(session, tennis)
    _market(session, event, venue_start=None)

    stats = await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == LISTING_STAMP
    assert "phase15_pm_venue_corrected" not in stats["funnel"]


@pytest.mark.asyncio
async def test_an_event_already_on_the_venue_instant_is_not_rewritten():
    """No-op writes would churn every linked Polymarket row every 15 minutes."""
    session, tennis = _new_rail()
    event = _event(
        session, tennis, commence=VENUE_KICKOFF + timedelta(seconds=30),
        source=POLYMARKET_VENUE_COMMENCE_SOURCE,
    )
    _market(session, event)

    stats = await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == (
        VENUE_KICKOFF + timedelta(seconds=30)
    )
    assert "phase15_pm_venue_corrected" not in stats["funnel"]


def test_drift_just_over_a_minute_is_corrected():
    """The floor is a floor, not a tolerance — it must not swallow real drift."""
    class _M:
        source = "polymarket"
        market_metadata = {"venue_game_start": VENUE_KICKOFF.isoformat()}

    class _E:
        commence_time = VENUE_KICKOFF + timedelta(seconds=61)
        commence_time_source = "polymarket"

    assert polymarket_venue_redate(_M(), _E()) == VENUE_KICKOFF


# ── The #46 guard, surviving its extraction ──────────────────────────────────

@pytest.mark.asyncio
async def test_a_scored_completed_event_refuses_the_correction():
    """gotcha #21 / #46: a real result outranks any schedule correction."""
    session, tennis = _new_rail()
    played_at = VENUE_KICKOFF - timedelta(hours=2)
    event = _event(
        session, tennis, status="completed", completed_at=played_at,
        home_score=2, away_score=1,
    )
    _market(session, event)

    stats = await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == LISTING_STAMP
    assert event.status == "completed"
    assert stats["funnel"]["phase15_pm_venue_refused_inversion"] == 1


@pytest.mark.asyncio
async def test_an_unscored_staleness_artifact_is_voided_by_the_correction():
    """An unscored row closed BEFORE the start the venue publishes was never
    played, so the settlement is the wrong field, not the start."""
    session, tennis = _new_rail()
    event = _event(
        session, tennis, status="closed",
        completed_at=VENUE_KICKOFF - timedelta(hours=2),
    )
    _market(session, event)

    stats = await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == VENUE_KICKOFF
    assert event.status == "scheduled"
    assert event.completed_at is None
    assert stats["funnel"]["phase15_pm_venue_corrected_and_voided"] == 1


def test_the_registry_path_still_applies_and_still_refuses_the_inversion():
    """The extraction moved the #46 guard; it did not change what it decides.

    Driven through `apply_authorized_commence_time` directly, which is the body
    `_update_fields_by_priority` now calls, so the two rails cannot disagree
    about the invariant.
    """
    class _E:
        id = 1
        commence_time = LISTING_STAMP
        commence_time_source = "polymarket"
        completed_at = VENUE_KICKOFF - timedelta(hours=2)
        status = "completed"
        home_score, away_score = 6, 3

    scored = _E()
    assert apply_authorized_commence_time(
        scored, VENUE_KICKOFF, POLYMARKET_VENUE_COMMENCE_SOURCE,
    ) == "refused_inversion"
    assert scored.commence_time == LISTING_STAMP

    unscored = _E()
    unscored.status = "closed"
    unscored.home_score = unscored.away_score = None
    assert apply_authorized_commence_time(
        unscored, VENUE_KICKOFF, POLYMARKET_VENUE_COMMENCE_SOURCE,
    ) == "corrected_and_voided"
    assert unscored.status == "scheduled"
    assert unscored.completed_at is None

    plain = _E()
    plain.completed_at = None
    plain.status = "scheduled"
    assert apply_authorized_commence_time(
        plain, VENUE_KICKOFF, POLYMARKET_VENUE_COMMENCE_SOURCE,
    ) == "corrected"
    assert plain.commence_time == VENUE_KICKOFF
    assert plain.commence_time_source == POLYMARKET_VENUE_COMMENCE_SOURCE


# ── One key, three readers ───────────────────────────────────────────────────

def test_the_stamp_key_is_read_by_the_mint_chooser_and_the_redate_alike():
    """ONE metadata dict, driven through BOTH consumers of lane1b's stamp.

    The failure this exists for is a silent key drift between the ingest half
    (`tasks.polymarket` writes `market_metadata['venue_game_start']`) and the two
    readers. Asserting each reader against its own hand-written dict would pass
    happily on a key production does not have — which is exactly how a GREEN half
    shipped inert. So the same object goes to all three.
    """
    from app.tasks.prediction_market_matching import auto_create_commence_time

    class _M:
        source = "polymarket"
        external_id = "60980454"
        commence_time = LISTING_STAMP
        market_metadata = {
            "venue_game_start": VENUE_KICKOFF.isoformat().replace("+00:00", "Z")
        }

    class _E:
        commence_time = LISTING_STAMP
        commence_time_source = "polymarket"

    market = _M()
    assert venue_game_start(market) == VENUE_KICKOFF
    assert auto_create_commence_time(market, LISTING_STAMP) == (
        VENUE_KICKOFF, POLYMARKET_VENUE_COMMENCE_SOURCE,
    )
    assert polymarket_venue_redate(market, _E()) == VENUE_KICKOFF


@pytest.mark.asyncio
async def test_the_ingest_half_and_this_repair_compose_on_one_real_child_row():
    """END TO END on the composed tree: lane1b's INGEST builds the row, this
    pass corrects the event. No hand-written metadata dict anywhere.

    The gap this closes is the one that let a GREEN half ship inert seventy
    minutes earlier: `a02aca00a` was correct and changed nothing, because the
    only rows it could see carried no such key. A test that hand-builds the
    metadata proves a reader works on a row shape production does not have. So
    the child row here is built by master's real `sub_market_metadata` — the
    exact function `tasks.polymarket` calls at ingest — and its output is written
    to the row unmodified. If the two halves ever disagree about the key, or the
    ingest stops passing the instant through, this reddens and the unit tests
    above do not.
    """
    from app.tasks.polymarket import sub_market_metadata

    ingested = sub_market_metadata(
        event_id="1019271",
        matchup_title=GAME_LEVEL,
        venue_game_start=VENUE_KICKOFF.isoformat().replace("+00:00", "Z"),
    )
    assert "venue_game_start" in ingested, (
        "the ingest half stopped carrying the instant — the chooser and this "
        "repair both go inert, silently"
    )

    session, tennis = _new_rail()
    event = _event(session, tennis)

    from app.models.models import FuturesMarket

    session.add(FuturesMarket(
        source="polymarket", external_id="60980454", name=GAME_LEVEL,
        category="game_prop", status="open", event_id=event.id,
        sport_id=event.sport_id, llm_sport_category="tennis",
        group_id="polymarket:1019271", group_type="polymarket_sub_market",
        market_metadata=ingested,
    ))
    session.commit()

    await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == VENUE_KICKOFF
    assert event.commence_time_source == POLYMARKET_VENUE_COMMENCE_SOURCE


@pytest.mark.asyncio
async def test_higher_authority_committed_after_freshness_check_cannot_be_overwritten_6073():
    """CERT-2849's required repair: the AUTHORITY column is part of the row.

    `commence_time_source` is what AUTHORIZES this write — the pass reads it,
    sees `polymarket`, and concludes Polymarket may re-date its own row. It was
    the one column the decision read that the conditional UPDATE did not repeat,
    and that gap is the ship's remaining race: a HIGHER authority committing
    between the read and the write.

    THE INTERLOPER MOVES NOTHING ELSE. It commits `espn` and leaves the status,
    both scores, `completed_at` and `commence_time` exactly as observed — so the
    five-column CAS matches happily and, before this repair, the statement
    overwrote a higher authority's claim with `polymarket_venue` and the venue
    time. A race witness that also moved the clock would have been caught by the
    existing predicate and would have proved nothing about this one.

    The producer's offer differs from the interloper's write on BOTH columns
    (`polymarket_venue` vs `espn`, VENUE_KICKOFF vs the listing stamp), so a
    no-op write cannot masquerade as a successful one.
    """
    from sqlalchemy import text

    from app.tasks import prediction_market_matching as task_mod

    session, tennis = _new_rail()
    event = _event(session, tennis)
    _market(session, event)
    event_id = event.id

    real_check = task_mod.phase15_event_row_is_unmoved

    async def _check_then_authority_lands(inner_session, inner_event):
        answer = await real_check(inner_session, inner_event)
        # ONLY the authority column moves.
        inner_session._s.execute(
            text("UPDATE events SET commence_time_source = 'espn' WHERE id = :i"),
            {"i": event_id},
        )
        inner_session._s.commit()
        return answer

    with patch.object(
        task_mod, "phase15_event_row_is_unmoved", new=_check_then_authority_lands,
    ):
        stats = await _run_phase15(session)

    row = session.execute(
        text(
            "SELECT commence_time, commence_time_source FROM events WHERE id = :i"
        ),
        {"i": event_id},
    ).one()
    assert row.commence_time_source == "espn", (
        "a higher authority's claim was overwritten by Polymarket — the write "
        "was authorized against a row that no longer existed"
    )
    assert str(row.commence_time).startswith("2026-09-13 20:14:27"), (
        "the venue time landed anyway: the authority column declined the row "
        "but the clock was written, which means the two are not in one statement"
    )
    assert stats["funnel"]["phase15_pm_venue_redate_lost_race"] == 1
    assert "phase15_pm_venue_corrected_and_voided" not in stats["funnel"]


@pytest.mark.asyncio
async def test_the_uncontested_redate_still_lands_with_the_authority_in_the_predicate_6073():
    """The twin for the arm above: `WHERE false` must not pass it.

    Same rail, same path, one difference — nobody interleaves. Without this, a
    predicate that declines every row satisfies the race test perfectly.
    """
    session, tennis = _new_rail()
    event = _event(session, tennis)
    _market(session, event)

    stats = await _run_phase15(session)

    session.refresh(event)
    assert event.commence_time.replace(tzinfo=timezone.utc) == VENUE_KICKOFF
    assert event.commence_time_source == POLYMARKET_VENUE_COMMENCE_SOURCE
    assert stats["funnel"].get("phase15_pm_venue_redate_lost_race", 0) == 0
