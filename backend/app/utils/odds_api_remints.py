"""#7993 — a fight The Odds API re-minted under a new id stops printing twice.

**SHIP: `/search?q=Vettori` stops showing Marvin Vettori vs Ismail Naurdiev as an
"Oct 10 5:00 PM" card.** There is one fight, on UFC 332 (Oct 3). (Pillar:
MATCHING.)

THE MECHANISM, MEASURED ON THE PROVIDER, NOT ON OUR MIRROR
═══════════════════════════════════════════════════════════
The Odds API re-issues a combat bout under a NEW 32-hex id when it re-dates it.
UFC 332's nine full-name bouts were minted at ``2026-10-11 00:00Z`` (09-24) and
again at ``2026-10-04 00:00Z`` (09-25 12:06Z) with different ids for the same
pairs. The provider's own ``/events`` listing at 16:30Z carried ONLY the second
set; every first-set id was gone. Nothing retires the first set: the poller only
ever writes to ids the provider returns, so a dropped id just goes quiet and
keeps printing its card in search.

WHY THIS IS RULING 048-COMPATIBLE
═════════════════════════════════
048 forbids absorbing on name and time. The evidence here is neither: it is the
provider's OWN schedule dereferencing both ids — one it no longer lists, one it
does — for the same two fighters. Names only choose which rows to ask about. The
listing decides.

WHY COMBAT SPORTS ONLY
══════════════════════
Two upcoming rows for one pair are routine in team sports. On 2026-09-25, 76
same-pair future Odds-API pairs existed. 59 were team sports: NFL home-and-away
games, an MLB doubleheader, NBA and NHL rematches. A far-future NFL placeholder the
provider has not listed yet is still a real separate game, so "not listed" proves
nothing there. Two fighters cannot meet twice while both bouts are still upcoming,
so in MMA and boxing a same-pair row the provider dropped, beside one it lists, is
the same bout.

A LABEL, NEVER A MERGE — the same rail as the tennis/soccer/container sweeps:
one ``provenance:duplicate-of:<canonical>`` element appended to the ghost's
``event_tags``, which search, the rails and the feed already decline to print.
The prior array is banked first (D51) and one restore command removes the
element. This module is the pure judgement; the task owns every read and write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.utils.event_merge_invariant import fold_participant_name

#: The provider's id shape — the same allowlist `matching_reconciliation` reads
#: as `schedule_provider`. A row carrying any other id was not minted by this
#: provider, so this provider's listing says nothing about it.
ODDS_API_EVENT_ID = re.compile(r"^[0-9a-f]{32}$")

#: Our sport keys ARE the provider's keys for these, which is what lets the task
#: ask `/sports/{key}/events` about a row's own sport.
COMBAT_SPORT_PREFIXES = ("mma_", "boxing_")


@dataclass(frozen=True)
class RemintRow:
    event_id: int
    sport_key: str
    external_id: str | None
    home_team_name: str | None
    away_team_name: str | None
    commence_time: datetime | None
    has_result: bool
    #: The canonical an existing `duplicate-of` tag names, if any.
    duplicate_of: int | None
    #: Weighted sources holding a reading in `win_probability_sources`.
    price_sources: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RemintTag:
    ghost_id: int
    canonical_id: int
    reason: str


@dataclass
class RemintPlan:
    tags: list[RemintTag] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    #: Same-pair groups of two or more in-scope rows — the population the
    #: judgement actually reached.
    groups_examined: int = 0
    #: Ghosts whose tag is already on disk (naming the planned canonical).
    already_tagged: int = 0


def is_in_scope(row: RemintRow, now: datetime) -> bool:
    """Could the provider's listing speak for this row at all?

    Every clause narrows to rows where "not listed" is evidence: this
    provider's id, a combat sport, still upcoming (a finished bout drops off
    the listing normally), and no result (a row holding an outcome is never
    hidden behind another).
    """
    if not row.sport_key or not row.sport_key.startswith(COMBAT_SPORT_PREFIXES):
        return False
    if not row.external_id or not ODDS_API_EVENT_ID.match(row.external_id):
        return False
    if row.commence_time is None or row.commence_time <= now:
        return False
    return not row.has_result


def matchup_key(row: RemintRow) -> frozenset[str] | None:
    """The two fighters, folded, orientation-free. ``None`` when unknowable.

    A name that folds to ``""`` or a bout that folds to one fighter
    (``home == away``) names nobody. Both would compare equal to unrelated rows.
    """
    home = fold_participant_name(row.home_team_name or "")
    away = fold_participant_name(row.away_team_name or "")
    if not home or not away or home == away:
        return None
    return frozenset((home, away))


def _groups(rows, now) -> dict[tuple[str, frozenset[str]], list[RemintRow]]:
    groups: dict[tuple[str, frozenset[str]], list[RemintRow]] = {}
    for row in rows:
        if not is_in_scope(row, now):
            continue
        key = matchup_key(row)
        if key is None:
            continue
        groups.setdefault((row.sport_key, key), []).append(row)
    return {k: v for k, v in groups.items() if len(v) > 1}


def sports_needing_listing(rows, now: datetime) -> set[str]:
    """The sports whose listing the task must read, and no others.

    Only a sport holding a same-pair group has a question to ask, so a quiet
    day costs zero provider calls.
    """
    return {sport for sport, _ in _groups(rows, now)}


def plan_remint_tags(
    rows,
    listed_ids_by_sport: dict[str, frozenset[str]],
    now: datetime,
) -> RemintPlan:
    """Which rows the provider has re-minted, and onto which row. Pure.

    Per same-pair group: exactly one row whose id the provider lists is the
    canonical, and every row whose id it does not list is a ghost of it. Every
    other shape is refused with its reason:

    * listing unread for the sport: absence from a listing nobody read is not
      absence.
    * none listed: the provider has dropped the bout entirely (Shevchenko–Silva
      on 09-25). There is no successor to fold onto, and choosing one of two
      dead rows is a guess.
    * two or more listed: the provider itself says these are separate events.
    * canonical already tagged: a row cannot be the duplicate of a duplicate
      (`canonical_id_from_tags` is one hop by design).
    * ghost holds a price the canonical lacks: the fold GAP-FILLS the hero
      (`merge_probability_sources`), so the dead id's reading would become the
      canonical's number. Ghost 1292 (Makhachev–Usman) holds `betting` 0.7258
      from January, and its canonical 1298 holds none.
    """
    plan = RemintPlan()
    for (sport, _), group in sorted(
        _groups(rows, now).items(), key=lambda kv: min(r.event_id for r in kv[1])
    ):
        plan.groups_examined += 1
        ids = sorted(r.event_id for r in group)
        listed_ids = listed_ids_by_sport.get(sport)
        if listed_ids is None:
            plan.refusals.append(f"{ids}: {sport} listing unread")
            continue
        listed = [r for r in group if r.external_id in listed_ids]
        absent = [r for r in group if r.external_id not in listed_ids]
        if not listed:
            plan.refusals.append(f"{ids}: provider lists none of them")
            continue
        if len(listed) > 1:
            plan.refusals.append(
                f"{ids}: provider lists {len(listed)} of them as separate events"
            )
            continue
        canonical = listed[0]
        if canonical.duplicate_of is not None:
            plan.refusals.append(
                f"{ids}: listed row {canonical.event_id} is itself tagged "
                f"duplicate-of:{canonical.duplicate_of}"
            )
            continue
        for ghost in sorted(absent, key=lambda r: r.event_id):
            if ghost.duplicate_of == canonical.event_id:
                plan.already_tagged += 1
                continue
            if ghost.duplicate_of is not None:
                plan.refusals.append(
                    f"{ghost.event_id}: already tagged duplicate-of:"
                    f"{ghost.duplicate_of}, not {canonical.event_id}"
                )
                continue
            only_ghost = ghost.price_sources - canonical.price_sources
            if only_ghost:
                plan.refusals.append(
                    f"{ghost.event_id}: holds {sorted(only_ghost)} that "
                    f"{canonical.event_id} lacks — the fold would print the "
                    f"dropped id's reading"
                )
                continue
            plan.tags.append(
                RemintTag(
                    ghost_id=ghost.event_id,
                    canonical_id=canonical.event_id,
                    reason=(
                        f"{sport}: id {ghost.external_id} no longer listed; "
                        f"{canonical.external_id} listed for the same pair"
                    ),
                )
            )
    return plan
