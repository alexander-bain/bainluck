"""The shared StatPal fixture id finally does something: it names the duplicate.

**SHIP: a game that we hold twice appears ONCE — on search, on the Discover
feed, on the league rails and on the team page — because the two rows already
carry the same StatPal fixture id and that id is now allowed to say so.**
(Pillar: MATCHING. Ship 3, #4457.)

WHY THIS EXISTS, AND WHY IT IS NOT A NEW MATCHER
════════════════════════════════════════════════
Every part of the duplicate machine is already built except one link:

* the WRITE side vocabulary — ``provenance:duplicate-of:<canonical>``, minted by
  :func:`app.services.anchor_channel.duplicate_tag`;
* the READ side — :func:`app.utils.proven_duplicates.not_a_proven_duplicate`
  declines to print the tagged row, and its three folds move the suppressed
  row's markets, its curve and its blend onto the survivor so nothing is lost;
* two writers — ``event_registry._record_proven_duplicates`` (at row creation,
  id-anchored) and ``tennis_twin_sweep`` (tennis, its own pairing).

What has had no writer is the case D50's stampers create every hour: **two of
our rows carrying the SAME ``statpal_fixture_id``.** Measured on production
2026-09-12, 12 such groups across five sports — and in the MLB ones the ghost is
a StatPal-schedule row created days ahead with no score, no ``espn_id`` and no
``external_id``, sitting next to the completed game a reader can see (#5746,
#5779).

The stamper meets those groups as ``VERDICT_AMBIGUOUS`` — "two of our rows for
one contest" — and correctly refuses to act, because *its* evidence is a name
window and ruling 048 deleted name-and-time absorption. **This module's evidence
is not a name window.** Both rows already hold the provider's own id for the
contest, which is the id-anchored correspondence ruling 048 names, and it is the
same bar ``event_merge_invariant.PROVIDER_ID_COLUMNS`` uses.

WHAT IT DOES AND DOES NOT DO
════════════════════════════
It appends ONE tag element to the non-elected rows. **No delete, no merge, no
repoint, no column overwrite, no absorption.** Ruling 048 and gotcha #32 are
untouched: nothing is created and nothing is drained.

**The undo needs no backup table, and that is a proof rather than a habit.** The
only write is ``event_tags = event_tags || '["<tag>"]'`` guarded by
``NOT event_tags @> '["<tag>"]'``, so a ``rowcount`` of 1 means the element was
absent a moment ago and the inverse — ``event_tags - '<tag>'`` — restores the
column exactly. The receipt lists every ``(event_id, tag)`` pair written, so the
undo is a single statement over a named id set (D51). A ``CREATE TABLE`` here
would be unattended DDL for a value we can reconstruct from the write itself.

THE FOUR REFUSALS, AND THE THREE PRODUCTION GROUPS THEY ALREADY STOP
════════════════════════════════════════════════════════════════════
A shared id is strong evidence and it is not infallible: ``/api/admin/repairs``
carries ``statpal-blank-ids`` and ``statpal-fabricated-ids`` for the two ways it
goes wrong. So the id is necessary and never sufficient.

``NOT_A_CONTEST_ID``
    The grouping value is not a StatPal contest id at all — blank, whitespace,
    or the ``statpal_live_…`` sentence #2963 found in the column. Decided by the
    stamper's own :func:`is_statpal_contest_id`, passed in rather than
    re-implemented, so the two cannot drift into disagreeing about what an id is.
``SPLIT_SPORT``
    The rows sharing the id are not in one sport. Two sports' id spaces overlap
    (D55/#2879 is exactly this), and a cross-sport pair is a collision, never a
    duplicate.
``KICKOFF_DIFFERS``
    A member's ``commence_time`` is not the canonical's to the minute. **This is
    the load-bearing one.** Of the 12 production groups on 2026-09-12, THREE are
    two genuinely different games wearing one id — NBA ``1027790`` (2026-04-14
    23:30Z and 2026-04-15 23:40Z), NBA ``1027792`` and NHL ``637968`` (two days
    apart). Tagging those would hide a real game. The other nine agree to the
    second.
``ORIENTATION_DISAGREES``
    The member's home/away slots do not hold the same sides as the canonical's
    (:func:`app.utils.proven_duplicates.orientation_agrees`). It refuses **0 of
    today's nine** — ``St.Louis Cardinals`` and ``St. Louis Cardinals`` are one
    token set, ``Mainz`` is a subset of ``FSV Mainz 05`` — and it is here for the
    swapped pair, because the read side folds the suppressed row's
    ``win_probability_sources`` onto the survivor and a swapped fold prints one
    side's probability under the other's name. Stated as measured-inert rather
    than left to look load-bearing.

Two rows already tagged are skipped rather than re-tagged, and a row already
carrying ANY ``duplicate-of:`` tag is left alone: it is suppressed already, and a
second tag would make it a duplicate of two canonicals at once.

WHY THE ELECTION IS IMPORTED AND NOT DECIDED HERE
═════════════════════════════════════════════════
:func:`app.utils.event_twin_fold.twin_identity_rank` already elects the survivor
at SERVE time on the league rails. If this module elected differently, a page
that folds would print one row and a page that only reads the tag would print the
other — the same game with two ids depending on which surface you opened. One
ranker, one answer. (Measured on the nine admissible groups: it elects the
scored, ESPN-anchored row in every one, which is the row production already
serves for Lazio–AC Milan.)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Sequence

from sqlalchemy import text

from app.services.anchor_channel import DUPLICATE_TAG_PREFIX, duplicate_tag
from app.utils.event_twin_fold import twin_identity_rank
from app.utils.proven_duplicates import orientation_agrees

logger = logging.getLogger(__name__)

REFUSAL_NOT_A_CONTEST_ID = "NOT_A_CONTEST_ID"
REFUSAL_SPLIT_SPORT = "SPLIT_SPORT"
REFUSAL_KICKOFF_DIFFERS = "KICKOFF_DIFFERS"
REFUSAL_ORIENTATION = "ORIENTATION_DISAGREES"
REFUSAL_ALREADY_SUPPRESSED = "ALREADY_SUPPRESSED"

#: Every row this pass may touch, read in one statement off
#: `ix_events_statpal_fixture_id`. `commence_time` is compared to the minute, so
#: it is selected whole and truncated in Python rather than in SQL — a
#: `date_trunc` here would be a second place the tolerance is written down.
SELECT_ROWS_FOR_FIXTURES = """
SELECT id,
       sport_id,
       statpal_fixture_id,
       home_team_name,
       away_team_name,
       commence_time,
       home_score,
       away_score,
       espn_id,
       external_id,
       win_probability_sources,
       event_tags
  FROM events
 WHERE statpal_fixture_id = ANY(:fixture_ids)
"""

#: One element appended, idempotent IN THE DATABASE. The `NOT … @>` is what makes
#: `rowcount` mean "the tag was absent and now is not", which is the whole basis
#: of the backup-free undo described in the module docstring. Core SQL with a
#: server-side `||` and never an ORM assignment: gotcha #4.
APPEND_DUPLICATE_TAG = """
UPDATE events
   SET event_tags = COALESCE(event_tags, '[]'::jsonb) || CAST(:tag_array AS jsonb)
 WHERE id = :event_id
   AND statpal_fixture_id = :fixture_id
   AND NOT COALESCE(event_tags, '[]'::jsonb) @> CAST(:tag_array AS jsonb)
"""


@dataclass(frozen=True)
class DuplicateTag:
    """One tag this pass would write: ``duplicate_id`` duplicates ``canonical_id``."""

    canonical_id: int
    duplicate_id: int
    fixture_id: str
    sport_id: int

    @property
    def tag(self) -> str:
        return duplicate_tag(self.canonical_id)

    def receipt(self) -> dict[str, Any]:
        return {
            "event_id": self.duplicate_id,
            "canonical_id": self.canonical_id,
            "statpal_fixture_id": self.fixture_id,
            "tag": self.tag,
        }


def _tags_of(row: Any) -> list[str]:
    """``event_tags`` as a list of strings, whatever the driver handed back.

    asyncpg gives a real list; the guard suite's SQLite gives the serialised
    text. Iterating a `str` would yield single CHARACTERS and find no tag, which
    is a pass that silently re-tags every row it has already tagged.
    """
    tags = getattr(row, "event_tags", None)
    if isinstance(tags, (list, tuple)):
        return [t for t in tags if isinstance(t, str)]
    if isinstance(tags, str):
        try:
            decoded = json.loads(tags)
        except ValueError:
            return []
        if isinstance(decoded, list):
            return [t for t in decoded if isinstance(t, str)]
    return []


def _already_suppressed(row: Any) -> bool:
    return any(t.startswith(DUPLICATE_TAG_PREFIX) for t in _tags_of(row))


def _same_minute(a: Any, b: Any) -> bool:
    """Both kickoffs, truncated to the minute, are the same instant.

    A missing kickoff is not a match. `commence_time` is NOT NULL in the model,
    so this only fires on a hand-built row — and answering "same" for two rows
    that both know nothing is how a fold hides a real game.
    """
    if a is None or b is None:
        return False
    return a.replace(second=0, microsecond=0) == b.replace(second=0, microsecond=0)


def plan_shared_fixture_duplicates(
    rows: Iterable[Any],
    *,
    is_contest_id: Callable[[Optional[str]], bool],
) -> tuple[list[DuplicateTag], list[dict[str, Any]]]:
    """Which rows this pass would tag, and every row it refuses and why.

    Pure: no session, no clock, no network. ``rows`` is every event row carrying
    one of the fixture ids the caller asked about; grouping happens here so the
    caller cannot group by a key this module has not agreed to.

    Returns ``(tags, refusals)``. A refusal is a receipt, not a log line: a group
    this declines to fold is the interesting output, because it is either a real
    pair of games wearing one id (a repair for ``statpal-fabricated-ids``) or a
    duplicate this rail cannot see.
    """
    groups: dict[str, list[Any]] = {}
    for row in rows:
        key = getattr(row, "statpal_fixture_id", None)
        key = "" if key is None else str(key).strip()
        groups.setdefault(key, []).append(row)

    tags: list[DuplicateTag] = []
    refusals: list[dict[str, Any]] = []

    for fixture_id, members in sorted(groups.items()):
        if len(members) < 2:
            # One row per contest is the healthy case and is not a finding.
            continue
        if not is_contest_id(fixture_id):
            refusals.append(
                {
                    "reason": REFUSAL_NOT_A_CONTEST_ID,
                    "statpal_fixture_id": fixture_id,
                    "event_ids": sorted(int(m.id) for m in members),
                }
            )
            continue

        canonical = max(members, key=twin_identity_rank)
        for member in sorted(members, key=lambda m: int(m.id)):
            if int(member.id) == int(canonical.id):
                continue
            reason = _refuse(canonical, member)
            if reason is not None:
                refusals.append(
                    {
                        "reason": reason,
                        "statpal_fixture_id": fixture_id,
                        "event_id": int(member.id),
                        "canonical_id": int(canonical.id),
                    }
                )
                continue
            tags.append(
                DuplicateTag(
                    canonical_id=int(canonical.id),
                    duplicate_id=int(member.id),
                    fixture_id=fixture_id,
                    sport_id=int(getattr(canonical, "sport_id", 0) or 0),
                )
            )

    return tags, refusals


def _refuse(canonical: Any, member: Any) -> Optional[str]:
    """The reason this member may not be tagged against this canonical, or None."""
    if getattr(member, "sport_id", None) != getattr(canonical, "sport_id", None):
        return REFUSAL_SPLIT_SPORT
    if not _same_minute(
        getattr(canonical, "commence_time", None),
        getattr(member, "commence_time", None),
    ):
        return REFUSAL_KICKOFF_DIFFERS
    if not orientation_agrees(
        getattr(canonical, "home_team_name", None),
        getattr(canonical, "away_team_name", None),
        getattr(member, "home_team_name", None),
        getattr(member, "away_team_name", None),
    ):
        return REFUSAL_ORIENTATION
    if _already_suppressed(member):
        return REFUSAL_ALREADY_SUPPRESSED
    if _already_suppressed(canonical):
        # The elected survivor is itself somebody's duplicate. Tagging against it
        # builds a chain the read side does not follow, so the honest answer is
        # to leave the group for the pass that resolves the outer pair.
        return REFUSAL_ALREADY_SUPPRESSED
    return None


async def reconcile_shared_fixture_ids(
    session: Any,
    fixture_ids: Sequence[str],
    *,
    is_contest_id: Callable[[Optional[str]], bool],
    apply: bool = True,
) -> dict[str, Any]:
    """Tag every row that shares a StatPal contest id with a better row.

    ``fixture_ids`` are the contests the caller's pass read from StatPal, so the
    scan is id-keyed off ``ix_events_statpal_fixture_id`` and never widens to the
    table. ``apply=False`` plans and writes nothing, and the plan it returns is
    the same list the apply path would write.

    One row per transaction, like ``tennis_twin_sweep.write_tags`` and for the
    same reason: ``events`` is write-hot, and a batched UPDATE rolls back every
    row on the one that loses a lock.
    """
    wanted = sorted({str(f).strip() for f in fixture_ids if str(f).strip()})
    if not wanted:
        return {
            "fixtures_examined": 0,
            "tags_planned": 0,
            "tags_written": 0,
            "duplicate_tag_receipts": [],
            "duplicate_refusal_receipts": [],
            "failed_event_ids": [],
        }

    rows = (
        await session.execute(text(SELECT_ROWS_FOR_FIXTURES), {"fixture_ids": wanted})
    ).all()
    plan, refusals = plan_shared_fixture_duplicates(rows, is_contest_id=is_contest_id)

    written = 0
    failed: list[int] = []
    if apply:
        for item in plan:
            payload = json.dumps([item.tag])
            try:
                result = await session.execute(
                    text(APPEND_DUPLICATE_TAG),
                    {
                        "tag_array": payload,
                        "event_id": item.duplicate_id,
                        "fixture_id": item.fixture_id,
                    },
                )
                await session.commit()
                written += result.rowcount or 0
            except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
                await session.rollback()
                logger.warning(
                    "shared-fixture duplicate tag failed for event %s (%s): %s",
                    item.duplicate_id,
                    item.fixture_id,
                    exc,
                )
                failed.append(item.duplicate_id)

    return {
        "fixtures_examined": len(wanted),
        "tags_planned": len(plan),
        # `written` counts DATABASE rowcounts, so a plan entry whose tag was
        # already there contributes 0 — "planned 4 / written 0" is the steady
        # state of a second pass, not a failure (gotcha #53: say which).
        "tags_written": written,
        "duplicate_tag_receipts": [item.receipt() for item in plan],
        "duplicate_refusal_receipts": refusals,
        "failed_event_ids": failed,
    }
