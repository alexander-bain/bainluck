"""#5621 — the promised one-command undo, driven end to end on a real server.

WHY THIS FILE EXISTS
====================

`repair_5621_phantom_ffpts_events.py` may be applied at all only because of
D51(b): *a data repair that writes a backup first and ships a one-command
restore may be applied by the owning lane*. The restore is the consideration —
it is what Alex is really approving when he approves the apply.

Until this file, nothing drove `restore_5621_phantom_ffpts_events.py`. It was
named in one comment of the repair's own gate and tested nowhere. The repair
had four real-Postgres tests through its backup and refusal flows; its undo
had none, which is the wrong way round: a repair that goes wrong is recoverable
only through the half that was never exercised.

WHAT IT DRIVES
==============

Both scripts' own `run()`, in the order an operator runs them, against the
corpus the repair gate already pins — seed, `--backup`, `--apply`, then the
undo — rather than a hand-built backup table. A backup this file wrote itself
would agree with this file's expectations by construction and would prove
nothing about the pair; the only witness worth having is a backup the repair
actually took over rows the repair actually wrote.

THE TWO DEFECTS IT WAS WRITTEN AGAINST (both RED before the fix)
================================================================

1. `RESTORED {n_e} events` was printed from the BACKUP's row count, read before
   the UPDATEs ran. An id whose row is gone is silently not restored, and the
   line still said sixteen. That line is the whole verdict on an attended undo.
2. The drift count joined the backup to `events`, so a vanished row contributed
   0 — identical to a row that matches. On the dry run taken before the undo,
   "0 events differing" reads as "there is nothing to undo".

Both are gotcha #53: an absence is not agreement. The fix reports `rowcount`
and counts the missing rows separately.

The last two tests are the controls that keep the rest honest: an undo that
refused unconditionally, or wrote nothing, would satisfy every refusal
assertion here, so one test proves the round trip really restores and one
proves the dry run really writes nothing.
"""

import contextlib
import importlib.util
import types

from sqlalchemy import text

# The corpus, the schema fixture and the repair loader are imported from the
# repair's own gate rather than copied. A second copy of a 33-event corpus is a
# second thing to drift; this way the undo is always tested against whatever
# population the repair currently selects.
from tests.integration.test_repair_5621_population_excludes_real_games_pg import (  # noqa: E501
    ATTACHED_PHANTOM_IDS,
    _SCRIPTS,
    _repair,
    _seed,
    needs_postgres,
    pg_engine,  # noqa: F401 — imported so pytest can resolve it as a fixture
)

BACKUP_TABLES = ("backup_5621_events", "backup_5621_markets")


def _restore():
    name = "restore_5621_phantom_ffpts_events"
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@contextlib.asynccontextmanager
async def _bound(engine, monkeypatch):
    """Bind both scripts' `get_task_session` to the test database.

    Both import it from `app.tasks.base` at call time, so patching the module
    attribute reaches them without any import-order trick.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.tasks.base as task_base

    maker = async_sessionmaker(engine, expire_on_commit=False)

    @contextlib.asynccontextmanager
    async def _session():
        async with maker() as session:
            yield session

    monkeypatch.setattr(task_base, "get_task_session", _session)
    yield


async def _run_repair(engine, monkeypatch, *, backup=False, apply=False):
    async with _bound(engine, monkeypatch):
        # The repair refuses to WRITE off its producer app; that gate is left
        # live rather than stubbed out (notice 47c).
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
        return await _repair().run(
            types.SimpleNamespace(backup=backup, apply=apply)
        )


async def _run_restore(engine, monkeypatch, *, apply=False):
    async with _bound(engine, monkeypatch):
        return await _restore().run(types.SimpleNamespace(apply=apply))


async def _drop_backups(conn):
    for table in BACKUP_TABLES:
        await conn.execute(text(f"DROP TABLE IF EXISTS {table}"))


async def _event_state(conn, ids):
    rows = (
        await conn.execute(
            text("SELECT id, status FROM events WHERE id = ANY(:ids) ORDER BY id"),
            {"ids": ids},
        )
    ).all()
    return {r.id: r.status for r in rows}


async def _market_state(conn):
    """Every column the repair writes, for every `kxnflffpts` market."""
    rows = (
        await conn.execute(
            text(
                "SELECT id, llm_sport_category, sport_id, event_id "
                "FROM futures_markets WHERE lower(external_id) LIKE 'kxnflffpts%' "
                "ORDER BY id"
            )
        )
    ).all()
    return {
        r.id: (r.llm_sport_category, r.sport_id, r.event_id) for r in rows
    }


async def _backed_up_ids(conn):
    return sorted(
        r.id
        for r in (
            await conn.execute(text("SELECT id FROM backup_5621_events"))
        ).all()
    )


async def _seeded_and_repaired(engine, monkeypatch):
    """Seed, snapshot the pre-repair state, then back up and apply.

    Returns the snapshot the undo has to reproduce. Asserts on the way through
    that the repair actually CHANGED something — a round trip over a repair
    that was a no-op would restore perfectly and mean nothing.
    """
    async with engine.begin() as conn:
        await _seed(conn)
        await _drop_backups(conn)
        before_events = await _event_state(conn, await _all_seeded_ids(conn))
        before_markets = await _market_state(conn)

    assert await _run_repair(engine, monkeypatch, backup=True) == 0
    assert await _run_repair(engine, monkeypatch, apply=True) == 0

    async with engine.begin() as conn:
        after_events = await _event_state(conn, list(before_events))
        after_markets = await _market_state(conn)
        backed = await _backed_up_ids(conn)

    assert backed, "the repair took no backup, so there is nothing to undo"
    changed = [i for i in backed if after_events[i] != before_events[i]]
    assert changed, "the repair changed no event, so the round trip is vacuous"
    assert after_markets != before_markets, "the repair changed no market"
    return before_events, before_markets, backed


async def _all_seeded_ids(conn):
    rows = (
        await conn.execute(
            text(
                "SELECT id FROM events WHERE commence_time_source LIKE 'kalshi%' "
                "   OR commence_time_source = 'odds_api'"
            )
        )
    ).all()
    return [r.id for r in rows]


@needs_postgres
async def test_the_undo_refuses_when_no_backup_was_ever_taken(
    pg_engine, monkeypatch, capsys  # noqa: F811
):
    """No backup here means the repair never ran here — refuse, write nothing."""
    async with pg_engine.begin() as conn:
        await _seed(conn)
        await _drop_backups(conn)
        before = await _event_state(conn, await _all_seeded_ids(conn))

    code = await _run_restore(pg_engine, monkeypatch, apply=True)
    out = capsys.readouterr().out

    assert code == 2, out
    assert "REFUSING" in out
    async with pg_engine.begin() as conn:
        assert await _event_state(conn, list(before)) == before


@needs_postgres
async def test_the_full_attended_sequence_puts_every_column_back(
    pg_engine, monkeypatch, capsys  # noqa: F811
):
    """The D51(b) promise, end to end: seed → backup → apply → undo.

    This is also the positive control for the refusal tests: an undo that
    refused or no-opped would pass all of them and fail only here.
    """
    before_events, before_markets, backed = await _seeded_and_repaired(
        pg_engine, monkeypatch
    )

    code = await _run_restore(pg_engine, monkeypatch, apply=True)
    out = capsys.readouterr().out

    assert code == 0, out
    async with pg_engine.begin() as conn:
        assert await _event_state(conn, list(before_events)) == before_events
        assert await _market_state(conn) == before_markets
    # Non-vacuity: the line has to name the rows it wrote, not a bare success.
    assert f"RESTORED {len(backed)} of {len(backed)} events" in out
    assert "WARNING" not in out


@needs_postgres
async def test_a_second_undo_writes_the_same_values(
    pg_engine, monkeypatch, capsys  # noqa: F811
):
    """Idempotent, as the header promises: twice is the same as once."""
    before_events, before_markets, _ = await _seeded_and_repaired(
        pg_engine, monkeypatch
    )
    assert await _run_restore(pg_engine, monkeypatch, apply=True) == 0
    code = await _run_restore(pg_engine, monkeypatch, apply=True)
    out = capsys.readouterr().out

    assert code == 0, out
    async with pg_engine.begin() as conn:
        assert await _event_state(conn, list(before_events)) == before_events
        assert await _market_state(conn) == before_markets


@needs_postgres
async def test_the_undo_dry_run_writes_nothing(
    pg_engine, monkeypatch, capsys  # noqa: F811
):
    """The control on the other side: a bare run must leave the repair standing."""
    before_events, _, backed = await _seeded_and_repaired(pg_engine, monkeypatch)
    async with pg_engine.begin() as conn:
        repaired = await _event_state(conn, list(before_events))

    code = await _run_restore(pg_engine, monkeypatch)
    out = capsys.readouterr().out

    assert code == 0, out
    assert "DRY RUN — nothing written" in out
    async with pg_engine.begin() as conn:
        still = await _event_state(conn, list(before_events))
    assert still == repaired
    # And it is not vacuous: the rows it declined to touch really are the
    # repaired ones, not the original ones.
    assert any(still[i] != before_events[i] for i in backed)


@needs_postgres
async def test_the_backup_tables_survive_the_undo(
    pg_engine, monkeypatch  # noqa: F811
):
    """A restore that destroyed its own evidence could not be checked after."""
    _, _, backed = await _seeded_and_repaired(pg_engine, monkeypatch)
    assert await _run_restore(pg_engine, monkeypatch, apply=True) == 0
    async with pg_engine.begin() as conn:
        assert await _backed_up_ids(conn) == backed


@needs_postgres
async def test_the_undo_counts_what_it_wrote_and_not_what_it_copied(
    pg_engine, monkeypatch, capsys  # noqa: F811
):
    """RED BEFORE THE FIX — the success line came from the backup's row count.

    One backed-up event with no market of its own is deleted after the repair
    applied. The undo can restore every row but that one, and the line the
    operator reads has to say so: sixteen copied, fifteen written. Before the
    fix it printed the copied count and no warning at all.
    """
    before_events, _, backed = await _seeded_and_repaired(pg_engine, monkeypatch)
    victim = next(i for i in backed if i not in ATTACHED_PHANTOM_IDS)
    async with pg_engine.begin() as conn:
        await conn.execute(text("DELETE FROM events WHERE id = :i"), {"i": victim})

    code = await _run_restore(pg_engine, monkeypatch, apply=True)
    out = capsys.readouterr().out

    assert code == 0, out
    assert f"RESTORED {len(backed) - 1} of {len(backed)} events" in out
    assert "WARNING" in out and "could not be restored" in out
    # The survivors are still fully restored — an incomplete undo is not a
    # refused one, and saying so must not cost the rows it could reach.
    async with pg_engine.begin() as conn:
        survivors = await _event_state(conn, [i for i in backed if i != victim])
    assert survivors == {
        i: before_events[i] for i in backed if i != victim
    }


@needs_postgres
async def test_a_deleted_event_does_not_take_the_whole_undo_down(
    pg_engine, monkeypatch, capsys  # noqa: F811
):
    """RED BEFORE THE FIX — and the worst of the three, because it restored NOTHING.

    The repair's own `--apply` sets `futures_markets.event_id = NULL`, which is
    precisely what lets a delete rail aimed at anchorless rows
    (`prune_unanchored_duplicates`, #2020) remove one of these events without
    the foreign key stopping it. The undo then tried to write that dead id back
    in one statement, `futures_markets_event_id_fkey` rejected it, and the
    whole transaction aborted — so the operator asking for their database back
    got a traceback and none of the other fifteen events restored either.

    An undo may report that it could not finish. It may not decline to start
    because one row out of sixteen is unreachable.
    """
    before_events, before_markets, backed = await _seeded_and_repaired(
        pg_engine, monkeypatch
    )
    victim = ATTACHED_PHANTOM_IDS[0]
    assert victim in backed, "the corpus stopped backing up an attached phantom"
    orphaned = [m for m, v in before_markets.items() if v[2] == victim]
    assert orphaned, "the victim has no market, so the FK path is not exercised"

    async with pg_engine.begin() as conn:
        await conn.execute(text("DELETE FROM events WHERE id = :i"), {"i": victim})

    code = await _run_restore(pg_engine, monkeypatch, apply=True)
    out = capsys.readouterr().out

    assert code == 0, out
    async with pg_engine.begin() as conn:
        # Every event that still exists is back, not just "not crashed".
        assert await _event_state(conn, [i for i in backed if i != victim]) == {
            i: before_events[i] for i in backed if i != victim
        }
        markets = await _market_state(conn)
    for mid in orphaned:
        cat, sid, eid = markets[mid]
        # The visible half is restored: it reads as the sport it was filed under
        # before the repair re-filed it.
        assert (cat, sid) == before_markets[mid][:2]
        # The link is the one thing that cannot come back, and it is left NULL
        # rather than pointed at a row that is not there.
        assert eid is None
    assert "NOT their event link" in out


@needs_postgres
async def test_a_row_that_vanished_is_not_counted_as_agreeing(
    pg_engine, monkeypatch, capsys  # noqa: F811
):
    """RED BEFORE THE FIX — the drift line joined, so a gone row read as equal.

    The dry run is the read an operator takes BEFORE deciding to undo. With one
    row deleted and every other row restored, the old output was
    "0 events differing" — which says there is nothing left to do about a row
    that can never be put back.
    """
    _, _, backed = await _seeded_and_repaired(pg_engine, monkeypatch)
    assert await _run_restore(pg_engine, monkeypatch, apply=True) == 0
    victim = next(i for i in backed if i not in ATTACHED_PHANTOM_IDS)
    async with pg_engine.begin() as conn:
        await conn.execute(text("DELETE FROM events WHERE id = :i"), {"i": victim})
    capsys.readouterr()

    code = await _run_restore(pg_engine, monkeypatch)
    out = capsys.readouterr().out

    assert code == 0, out
    # Everything still present matches the backup, so drift alone says "clean".
    assert "rows currently differing from backup: 0 events" in out
    # The missing row is the thing that must not disappear into that zero.
    assert "rows in the backup no longer present: 1 events" in out
