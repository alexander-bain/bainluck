"""#1918 — the write-time half of #1798: never bind an event side to the wrong club.

WHAT #1798 IS, AND WHY A DETECTOR WAS NOT ENOUGH

``events`` carries both team NAMES and team FK ids. When the id dereferences to a
club whose name disagrees with the row's own name field, every name-based check in
the codebase still passes — the names are right. ``app/tasks/repair_event_team_binding``
detects that class by DEREFERENCING, and repairs it. But a repair rail is a mop:
queue 360 dry-ran it to exhaustion and found **191 defective sides across the season,
29 of them on games that had not been played yet, created after the previous repair
applied** — roughly five new defective sides a day, still arriving.

So the predicate had to move to the write.

THE ACTUAL TAP (measured in production 2026-08-17, queue 361)

Not a fuzzy-matching miss and not an ordering bug in the event writer. The event
writer is faithful; the INDEX it reads is poisoned. ``team_identity_mapping`` holds
30 rows for ``source='statpal', sport_key='baseball_mlb'``, all written in a single
transaction at ``2026-03-25 17:53:42.738873+00``, and **15 of them name one club and
point at another**:

    source_name 'Milwaukee Brewers'      -> team 10734  Chicago White Sox
    source_name 'Chicago White Sox'      -> team 10735  Milwaukee Brewers
    source_name 'Arizona Diamondbacks'   -> team 10707  Los Angeles Dodgers
    source_name 'New York Yankees'       -> team  6609  San Francisco Giants
    source_name 'Baltimore Orioles'      -> team   865  New York Yankees
    ... 10 more

Those rows have never been updated since (``updated_at == created_at``), so the
corruption is frozen and permanent. ``TeamIdentityService.resolve_team`` finds them at
**step 2 — the exact ``source_name`` hit** — which is the highest-confidence path it
has, short-circuiting before any fuzzy logic can be blamed. ``statpal_sync`` then
writes what it was handed. That is why the damage is a *stable per-club permutation*
rather than noise, why it recurs on every fresh StatPal ingest, and why four months
in the middle look clean: StatPal only creates events inside a -1d/+7d window, and
where Odds API or ESPN bound the side first, ``not event.home_team_id`` is False and
the poison never lands.

Repairing the 15 mapping rows is a production write and therefore attended — it goes
to Alex. This module is the part that does not need permission: it makes the wrong
write impossible regardless of which index, which source, or which future defect
proposes it.

THE INVARIANT

An event side's ``team_id`` MUST dereference to a club whose name matches that side's
own ``*_team_name``, within the event's own ``sport_id``.

Two defect classes, kept distinct because they have different causes — the same split
the detector uses, and deliberately the same predicate, imported by both so the guard
and the detector can never drift:

  ``cross_club``   the id resolves to a genuinely different club.
  ``wrong_sport``  the id resolves to the RIGHT club's duplicate row on another
                   ``sport_id`` (for MLB: ``baseball_mlb_preseason`` 33178 instead of
                   ``baseball_mlb`` 53232). The name agrees; the identity is the wrong
                   half of the pair.

FAIL CLOSED, THEN HEAL

A refused binding leaves the column NULL. That is strictly better than a wrong id:
NULL is visibly absent and every downstream surface already handles it, while a wrong
id is invisible and silently mis-attributes a game to another club's page, favourites
and notifications. It also self-heals — the name-keyed binders (``espn_sync`` via
``upsert_team``, and the Odds API pass in ``tasks/sports``) resolve within the event's
own sport by exact name, so the next cycle fills the NULL correctly.

Refusals are logged at WARNING and counted. A non-zero refusal count is a FINDING, not
noise: it means an upstream index is proposing wrong clubs, which was previously
invisible because the write simply succeeded.

WHERE THIS IS APPLIED, AND THE ONE SITE DELIBERATELY LEFT ALONE

  ``tasks/statpal_sync``  the emitter. Resolves through ``team_identity_mapping``, which
                          crosses sports by ``sport_key`` PREFIX and is the poisoned
                          index above. This is the site that was writing the defect.
  ``tasks/espn_sync``     sound by construction today, but it OVERWRITES rather than
                          only filling NULLs, so it is the site where a future loosening
                          of ``upsert_team``'s fuzzy fallback would do the most damage.

  ``tasks/sports`` is NOT guarded, and that is a judgement rather than an oversight: it
  binds from a dict built as ``{Team.name: Team.id}`` filtered to ``Team.sport_id ==
  sport.id`` and looked up by ``evt.home_team_name`` — the guard's exact predicate,
  already enforced by the query's own shape. A call there could not return False, and a
  check that cannot fail is worse than no check: it reads as protection and teaches the
  next reader that the surrounding code is only safe because of it.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

CROSS_CLUB = "cross_club"
WRONG_SPORT = "wrong_sport"


def normalize_club_name(value: Optional[str]) -> str:
    """Lowercase alphanumerics only — 'St.Louis Cardinals' == 'St. Louis Cardinals'.

    Deliberately NOT a fuzzy matcher. Fuzzy resolution is the most likely producer of
    this bug class in the first place, so the guard that refuses it must not itself
    guess (Alex's ruling 2026-08-12: names are never sufficient — and a loose name
    comparison is the loosest possible reading of that).
    """
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def binding_defect(
    row_name: Optional[str],
    bound_name: Optional[str],
    bound_sport_id: Optional[int],
    event_sport_id: Optional[int],
) -> Optional[str]:
    """Return the defect class for one side, or ``None`` when the binding is sound.

    ``bound_name is None`` means the id dereferences to nothing we can read here — an
    unresolvable FK, not a wrong club. That is not this guard's class, and claiming it
    would make the refusal count unreadable, so it returns ``None``.
    """
    if bound_name is None:
        return None
    if normalize_club_name(bound_name) != normalize_club_name(row_name):
        return CROSS_CLUB
    if (
        bound_sport_id is not None
        and event_sport_id is not None
        and bound_sport_id != event_sport_id
    ):
        return WRONG_SPORT
    return None


def binding_is_sound(
    row_name: Optional[str],
    bound_name: Optional[str],
    bound_sport_id: Optional[int],
    event_sport_id: Optional[int],
) -> bool:
    """True when this side may be written. The inverse of :func:`binding_defect`."""
    return binding_defect(row_name, bound_name, bound_sport_id, event_sport_id) is None


def accept_team_binding(
    *,
    side: str,
    row_name: Optional[str],
    team,
    event_sport_id: Optional[int],
    source: str,
    event_id: Optional[int] = None,
    stats: Optional[dict] = None,
) -> bool:
    """Gate one ``event.<side>_team_id = team.id`` write. True ⇒ the caller may write.

    ``team`` is a ``Team`` ORM row (or anything exposing ``.id``/``.name``/``.sport_id``).
    A falsy ``team`` returns False without counting a refusal — "nothing resolved" is a
    coverage gap, not a wrong club, and conflating the two is how a real signal gets
    buried under routine misses (gotcha #53: an absence and a defect must not share a
    reading).

    On refusal the caller MUST leave the column untouched rather than substituting a
    guess. ``stats`` is incremented in place when supplied, so the emitting task can
    surface the count the same way the repair rail surfaces its census.
    """
    if not team:
        return False

    defect = binding_defect(
        row_name,
        getattr(team, "name", None),
        getattr(team, "sport_id", None),
        event_sport_id,
    )
    if defect is None:
        return True

    if stats is not None:
        stats["team_binding_refused"] = stats.get("team_binding_refused", 0) + 1
        key = f"team_binding_refused_{defect}"
        stats[key] = stats.get(key, 0) + 1

    logger.warning(
        "REFUSED %s team binding (%s): event=%s sport_id=%s source=%s "
        "row_name=%r -> team id=%s name=%r sport_id=%s. "
        "Leaving the column NULL; an upstream index is proposing the wrong club.",
        side,
        defect,
        event_id,
        event_sport_id,
        source,
        row_name,
        getattr(team, "id", None),
        getattr(team, "name", None),
        getattr(team, "sport_id", None),
    )
    return False
