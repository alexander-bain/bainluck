"""#7501 — the filler that gives a slug-less club its page. See ``utils/team_slug``.

WHAT IT WRITES

``teams.slug``, and only where it is NULL. Every UPDATE carries
``WHERE slug IS NULL`` in addition to the id, so the pass is idempotent against
itself, against a concurrent pass, and against the attended script that drives
the same function — two writers cannot produce two slugs for one club, and a
re-run of a completed pass writes nothing.

WHY NOT A SINGLE SET-BASED UPDATE

The column is UNIQUE and 855 of the rows measured on 2026-09-20 have their clean
name-slug already held by a club in another sport, so a bulk statement would
abort the whole batch on the first collision. Each row therefore writes inside
its own SAVEPOINT: a rejected candidate costs that row its next rung, never the
batch (hot-list #42), and a candidate a concurrent writer took between the
pre-read and the write raises ``IntegrityError`` into the savepoint and falls
through to the rung below.

FAIL OPEN, ALWAYS

Any unexpected exception on a row is counted and skipped. The status quo for a
row this function cannot slug is NULL — exactly what it was before — so there is
no failure mode here worse than not having run.

ORDERING

Newest id first. The forward case this beat exists for is the row ``upsert_team``
minted minutes ago, and the reader-visible half of the backlog (clubs with live
games) skews new. Gotcha #41's starvation hazard does not apply: the population
does not expire and the drain is finite — 4,004 rows at 500 per pass, three
passes an hour, reaches the oldest row inside three hours.

THE BANK (D51(b)) IS THE PRECONDITION OF EVERY WRITE, AND IS NEVER CREATED HERE

No ``backup_7501_team_slug_fill``, no writes. Not "writes without banking" —
**zero writes**, reported as a refusal. This is D51(b) read literally: an
unattended production write is permitted because a backup was taken FIRST and a
one-command restore exists, so a pass that fills 500 clubs with no bank behind it
is precisely the unattended-and-unrevertable write the rule forbids. An earlier
revision of this file banked opportunistically and filled regardless; the rows it
wrote before anyone ran ``--backup`` were, by construction, the rows the restore
could never reach (CERT-3171).

The table is created by ``scripts/repair_7501_*.py --backup`` and nowhere else —
runtime DDL, on the named app, invoked by a person (notice 47(c)). This task
never runs DDL: a ``CREATE TABLE`` that executes as a consequence of a release is
migration-class, and a beat is the least attended invocation there is. So the
beat idles, loudly, until that one attended command has been run; after it, every
pass — this one and every future row ``upsert_team`` mints — is banked and
reversible.

The bank write lives INSIDE the same SAVEPOINT as the slug UPDATE, so the pair is
atomic: there is no interleaving in which a club is slugged and its undo record
is not, and none in which the bank claims a slug the club does not carry.
"""

from __future__ import annotations

import logging

from sqlalchemy import Integer, String, bindparam, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Sport, Team
from app.tasks.base import get_task_session
from app.utils.team_slug import slug_candidates

logger = logging.getLogger(__name__)

#: Written when it exists, created only by `scripts/repair_7501_*.py --backup`.
BANK_TABLE = "backup_7501_team_slug_fill"

#: One pass. Small enough that a batch is a couple of seconds on the background
#: queue, large enough that the measured backlog drains in an afternoon.
DEFAULT_LIMIT = 500


async def _bank_exists(session: AsyncSession) -> bool:
    """`to_regclass` rather than a catch — an absent table is the normal case."""
    return (
        await session.execute(
            text("SELECT to_regclass(:name)").bindparams(
                bindparam("name", BANK_TABLE, type_=String)
            )
        )
    ).scalar_one() is not None


async def _remaining(session: AsyncSession) -> int:
    """Clubs still with no page. Read back, never subtracted from a counter —
    "it returned" is not "it worked" (hot-list #53), and this is the number the
    script's loop and the beat's log line both trust."""
    return (
        await session.execute(
            select(func.count()).select_from(Team).where(Team.slug.is_(None))
        )
    ).scalar_one()


async def fill_missing_team_slugs(
    session: AsyncSession,
    *,
    limit: int = DEFAULT_LIMIT,
    dry_run: bool = False,
) -> dict:
    """Give up to ``limit`` slug-less clubs a slug. Returns the pass's ledger.

    ``dry_run`` reads and resolves the full ladder without writing, so the plan
    is checkable — including which rung each row lands on — before a production
    write. It reports the same ``written`` pairs the apply would produce, and
    needs no bank: it writes nothing to refuse.

    An apply with no bank returns ``refused`` and writes NOTHING. See this
    module's header — that is D51(b), not a missing nicety.
    """
    stats: dict = {
        "examined": 0,
        "written": 0,
        "unresolved": 0,
        "errors": 0,
        "dry_run": dry_run,
        "banked": False,
        # None on every pass that was allowed to proceed. A string naming the
        # reason otherwise — the beat logs it at WARNING, so an idling drain is
        # legible from the worker log instead of reading as a quiet success
        # ("it returned" is not "it worked", hot-list #53).
        "refused": None,
        "pairs": [],
        # Seeded, not assigned at the end. The caller loops on this key, and the
        # one pass that must report it honestly is the empty one that ends the
        # loop — an early return that skipped it raised `KeyError` on exactly
        # the "there is nothing left" case (caught by the PG gate, never by a
        # pass that had work to do).
        "remaining": 0,
    }

    # D51(b), checked BEFORE a single row is considered rather than consulted at
    # write time: the refusal has to be structurally incapable of writing, not
    # merely arranged not to. A dry run is exempt because it has nothing to undo.
    if not dry_run:
        stats["banked"] = await _bank_exists(session)
        if not stats["banked"]:
            stats["refused"] = (
                f"{BANK_TABLE} does not exist, so this pass would be an "
                "unattended production write with no way back (D51(b)). Wrote "
                "nothing. Run `scripts/repair_7501_clubs_without_a_slug_have_no"
                "_page.py --backup` on bainluck once; every pass after it is "
                "banked and reversible."
            )
            stats["remaining"] = await _remaining(session)
            return stats

    rows = (
        await session.execute(
            select(Team.id, Team.name, Sport.key)
            .join(Sport, Sport.id == Team.sport_id, isouter=True)
            .where(Team.slug.is_(None))
            .order_by(Team.id.desc())
            .limit(limit)
        )
    ).all()
    stats["examined"] = len(rows)
    if not rows:
        # Measured, not assumed to be zero: an empty batch under `limit=0` is a
        # caller bug, and reporting "nothing remaining" for it would hide it.
        stats["remaining"] = await _remaining(session)
        return stats

    # Pre-read the slugs any of this batch's candidates could collide with. It
    # is an optimisation and nothing more: the UNIQUE index, not this set, is
    # what makes the write safe, and the savepoint below is what catches the
    # rows this read cannot see (a concurrent writer, another pass in flight).
    wanted: set[str] = set()
    ladders: list[tuple[int, list[str]]] = []
    for team_id, name, sport_key in rows:
        ladder = slug_candidates(name, sport_key, team_id)
        ladders.append((team_id, ladder))
        wanted.update(ladder)

    taken: set[str] = set(
        (await session.execute(select(Team.slug).where(Team.slug.in_(sorted(wanted)))))
        .scalars()
        .all()
    )

    for team_id, ladder in ladders:
        try:
            for candidate in ladder:
                if candidate in taken:
                    continue
                if dry_run:
                    taken.add(candidate)
                    stats["written"] += 1
                    stats["pairs"].append((team_id, candidate))
                    break
                try:
                    # ONE savepoint, both statements. The undo record cannot lag
                    # the slug it undoes: either the pair commits or neither
                    # does, and an IntegrityError from the UNIQUE index rolls
                    # both back before the next rung is tried.
                    async with session.begin_nested():
                        result = await session.execute(
                            update(Team)
                            .where(Team.id == team_id, Team.slug.is_(None))
                            .values(slug=candidate)
                        )
                        if result.rowcount:
                            await session.execute(
                                text(
                                    f"INSERT INTO {BANK_TABLE} "
                                    "(team_id, slug_after, taken_at) "
                                    "VALUES (:team_id, :slug, now()) "
                                    # DO UPDATE, not DO NOTHING. A club restored
                                    # and later re-slugged would otherwise keep
                                    # the FIRST fill's value in the bank, and the
                                    # restore's `t.slug = b.slug_after` join
                                    # would then decline to undo the slug the
                                    # club is actually wearing. The bank names
                                    # the write it is the undo for.
                                    "ON CONFLICT (team_id) DO UPDATE SET "
                                    "slug_after = EXCLUDED.slug_after, "
                                    "taken_at = EXCLUDED.taken_at"
                                ).bindparams(
                                    bindparam("team_id", team_id, type_=Integer),
                                    bindparam("slug", candidate, type_=String),
                                )
                            )
                except IntegrityError:
                    # Someone else took this candidate between the read above
                    # and now. Next rung; the last two carry the primary key.
                    continue
                taken.add(candidate)
                if result.rowcount:
                    stats["written"] += 1
                    stats["pairs"].append((team_id, candidate))
                else:
                    # `slug IS NULL` no longer held — a concurrent pass slugged
                    # this row. Not an error and not our write.
                    stats["examined"] -= 1
                break
            else:
                # Every rung taken, including two carrying this row's own id.
                stats["unresolved"] += 1
                logger.warning(
                    "#7501: no free slug candidate for team_id=%s (%s)",
                    team_id,
                    ladder,
                )
        except Exception:
            stats["errors"] += 1
            logger.exception("#7501: slug fill failed for team_id=%s", team_id)

    if not dry_run:
        await session.commit()

    stats["remaining"] = await _remaining(session)
    return stats


async def _backfill_team_slugs(limit: int = DEFAULT_LIMIT) -> dict:
    """Beat entry point. One pass, its own session."""
    async with get_task_session() as session:
        stats = await fill_missing_team_slugs(session, limit=limit)
    if stats["refused"]:
        # WARNING, not info: a beat that fires three times an hour and writes
        # nothing looks identical to a drained backlog in a log line, and the
        # remedy is one attended command that nobody will run unprompted.
        logger.warning(
            "#7501 team slug fill REFUSED (%s clubs still pageless): %s",
            stats["remaining"],
            stats["refused"],
        )
        return {k: v for k, v in stats.items() if k != "pairs"}
    logger.info(
        "#7501 team slug fill: examined=%s written=%s unresolved=%s errors=%s",
        stats["examined"],
        stats["written"],
        stats["unresolved"],
        stats["errors"],
    )
    # The pairs are the pass's own record; useful in a log line, noise in a
    # Celery result that gets stored per run.
    return {k: v for k, v in stats.items() if k != "pairs"}
