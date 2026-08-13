"""#1798 — events bound to the wrong club's ``team_id``. Detect by DEREFERENCE, never by name.

THE DEFECT

``events`` carries both the team NAMES (``home_team_name``/``away_team_name``) and
FK ids (``home_team_id``/``away_team_id``). Measured in production 2026-08-12 over
the 2026 MLB season: **1,758 events, 153 sides whose id dereferences to a club
whose name disagrees with the row's own name field.** The names are right and the
ids point at other clubs, so *every name-based check in the codebase passes*:

    event 15194469  "Arizona Diamondbacks @ Boston Red Sox"
        away_team_id = 10707 -> Los Angeles Dodgers
        home_team_id =   855 -> Minnesota Twins (baseball_mlb_preseason)

Any surface keyed on ``team_id`` inherits this directly — team pages, My Stuff,
favourites, notifications, and the roster join in ``team_linking``. It is why
``GET /api/teams/10709`` served "Miami Marlins @ Cincinnati Reds" among the Red
Sox's upcoming games.

WHY THE DETECTOR MUST DEREFERENCE

Alex's ruling 2026-08-12: *names are never sufficient*. Nothing in the codebase
asserts, after binding, that ``teams[event.home_team_id].name`` agrees with
``event.home_team_name``; the only comparisons anywhere near this compare a name
to a name, which is exactly the comparison this defect survives. So the predicate
here joins through the FK and reads the club it actually lands on.

TWO CLASSES, DELIBERATELY SEPARATED

  CROSS_CLUB   the id resolves to a genuinely different club. Reciprocal pairs
               dominate the measured population (Diamondbacks<->Dodgers,
               White Sox<->Brewers, Mariners<->Athletics), which is the
               fingerprint of a swapped-orientation merge copying home/away ids
               without swapping them -- see ``_merge_duplicate_events_impl``.
  WRONG_SPORT  the id resolves to the RIGHT club's duplicate row on
               ``baseball_mlb_preseason`` (33178) instead of ``baseball_mlb``
               (53232). The name agrees; only the identity is the wrong half of
               the pair. A different defect with a different cause, so it is
               counted and repaired separately rather than folded in.

REPAIR DIRECTION, AND WHY IT FAILS CLOSED

Re-derive the id from the row's own ``*_team_name`` **within the event's own
``sport_id``**, requiring exactly one match. It deliberately does NOT fuzzy-match:
fuzzy resolution is the most likely producer of this bug in the first place
(``TeamIdentityService.resolve_team`` scopes by a ``sport_key`` PREFIX -- for
``baseball_mlb`` that prefix is ``baseball``, spanning preseason, NCAA and NPB --
accepts a mascot-only match at score >= 40, and then AUTO-REGISTERS the result,
so one bad fuzzy hit becomes a permanent exact hit for every later lookup).
Repairing with the same tool that broke it would launder the error.

Zero candidates or more than one -> ``review``, never a guess.

Dry-run is the default. Every planned change is returned in the ledger with the
before and after id AND the dereferenced club name for both, so the plan is
checkable without a second query.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional, Union

from sqlalchemy import text

logger = logging.getLogger(__name__)


def _as_date(value: Union[str, date, datetime]) -> date:
    """Coerce ``since`` to a real ``date`` before it is bound as a query param.

    asyncpg binds parameters by TYPE, not by rendering them into SQL text: it
    rejects ``'2026-03-01'`` for a timestamp column with ``invalid input for
    query argument $2 ... (expected a datetime.date or datetime.datetime
    instance, got 'str')``. psycopg2 would have adapted the string silently, so
    this is asyncpg-specific and invisible to any test that does not bind
    against the real driver -- which is every test in this module's suite, all
    of which drive a ``_FakeSession`` double. The rail therefore shipped green
    (19/19) and 500-ed on its first production call.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()

# MLB regular season and the duplicate preseason sport that #1798 owns. Kept as
# the default scope because that is the population measured; ``sport`` widens it.
_DEFAULT_SPORT_IDS = (53232, 33178)

# A bound scan, not the whole table: this runs inside the web dyno on a request.
_DEFAULT_LIMIT = 500

_CANDIDATES_SQL = text(
    """
    SELECT e.id,
           e.sport_id,
           e.commence_time,
           e.status,
           e.home_team_name,
           e.home_team_id,
           ht.name      AS home_bound_name,
           ht.sport_id  AS home_bound_sport,
           e.away_team_name,
           e.away_team_id,
           at.name      AS away_bound_name,
           at.sport_id  AS away_bound_sport
      FROM events e
      LEFT JOIN teams ht ON ht.id = e.home_team_id
      LEFT JOIN teams at ON at.id = e.away_team_id
     WHERE e.sport_id = ANY(:sport_ids)
       AND e.commence_time >= :since
       AND (
             (e.home_team_id IS NOT NULL AND ht.id IS NOT NULL)
          OR (e.away_team_id IS NOT NULL AND at.id IS NOT NULL)
           )
     ORDER BY e.commence_time DESC
     LIMIT :lim
    """
)

# Exact-name resolution inside the event's own sport. No ILIKE, no fuzzy.
_RESOLVE_SQL = text(
    """
    SELECT id, name FROM teams
     WHERE sport_id = :sport_id
       AND lower(regexp_replace(name, '[^a-zA-Z0-9]', '', 'g'))
         = lower(regexp_replace(:target, '[^a-zA-Z0-9]', '', 'g'))
    """
)

_UPDATE_SQL = {
    "home": text("UPDATE events SET home_team_id = :tid WHERE id = :eid"),
    "away": text("UPDATE events SET away_team_id = :tid WHERE id = :eid"),
}


def _norm(value: Optional[str]) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _classify(row_name: str, bound_name: Optional[str],
              bound_sport: Optional[int], event_sport: int) -> Optional[str]:
    """Return the defect class for one side, or None when the binding is sound."""
    if bound_name is None:
        return None
    if _norm(bound_name) != _norm(row_name):
        return "cross_club"
    if bound_sport is not None and bound_sport != event_sport:
        return "wrong_sport"
    return None


async def repair(
    session,
    apply: bool = False,
    limit: Optional[int] = None,
    sport: Optional[str] = None,
    since: str = "2026-03-01",
) -> dict[str, Any]:
    """Re-bind events whose ``team_id`` dereferences to the wrong club (#1798).

    Args:
        apply: False (default) plans only. True commits.
        limit: max events scanned this call.
        sport: optional comma-separated ``sport_id`` list overriding the MLB default.
        since: only events at/after this commence_time are considered.

    Returns a census plus a per-side ledger. Every ledger entry names the club the
    id resolved to BEFORE and AFTER, because an id on its own is not reviewable.
    """
    sport_ids = (
        [int(s) for s in sport.split(",") if s.strip()] if sport else list(_DEFAULT_SPORT_IDS)
    )
    scan_limit = int(limit) if limit else _DEFAULT_LIMIT
    # Coerced ONCE and reused by both scans. Both are bound params; the
    # after-census one is the more dangerous of the two, because it runs after
    # the commit and would 500 a run whose writes had already landed.
    since_date = _as_date(since)

    rows = (
        await session.execute(
            _CANDIDATES_SQL,
            {"sport_ids": sport_ids, "since": since_date, "lim": scan_limit},
        )
    ).mappings().all()

    census = {
        "scanned": len(rows),
        "cross_club": 0,
        "wrong_sport": 0,
        "sound": 0,
        "planned": 0,
        "applied": 0,
        "review": 0,
    }
    ledger: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    resolve_cache: dict[tuple[int, str], list] = {}

    for row in rows:
        for side in ("home", "away"):
            row_name = row[f"{side}_team_name"]
            bound_id = row[f"{side}_team_id"]
            bound_name = row[f"{side}_bound_name"]
            bound_sport = row[f"{side}_bound_sport"]

            if bound_id is None or bound_name is None:
                continue

            defect = _classify(row_name, bound_name, bound_sport, row["sport_id"])
            if defect is None:
                census["sound"] += 1
                continue
            census[defect] += 1

            key = (row["sport_id"], _norm(row_name))
            if key not in resolve_cache:
                resolve_cache[key] = (
                    await session.execute(
                        _RESOLVE_SQL, {"sport_id": row["sport_id"], "target": row_name}
                    )
                ).all()
            matches = resolve_cache[key]

            # Fail closed. A guess here re-points a foreign key on a live surface.
            if len(matches) != 1:
                census["review"] += 1
                review.append({
                    "event_id": row["id"],
                    "side": side,
                    "defect": defect,
                    "row_name": row_name,
                    "bound_to": {"id": bound_id, "name": bound_name, "sport_id": bound_sport},
                    "reason": (
                        f"{len(matches)} exact name matches in sport_id={row['sport_id']} "
                        "— refusing to guess"
                    ),
                })
                continue

            target_id, target_name = matches[0]
            if target_id == bound_id:
                # Name agrees and the id is already canonical: nothing to do.
                census["sound"] += 1
                continue

            entry = {
                "event_id": row["id"],
                "commence_time": str(row["commence_time"]),
                "status": row["status"],
                "matchup": f"{row['away_team_name']} @ {row['home_team_name']}",
                "side": side,
                "defect": defect,
                "before": {"id": bound_id, "name": bound_name, "sport_id": bound_sport},
                "after": {"id": target_id, "name": target_name, "sport_id": row["sport_id"]},
            }
            census["planned"] += 1

            if apply:
                await session.execute(
                    _UPDATE_SQL[side], {"tid": target_id, "eid": row["id"]}
                )
                census["applied"] += 1
                entry["applied"] = True
                logger.info(
                    "#1798 re-bound event %s %s_team_id %s (%s) -> %s (%s)",
                    row["id"], side, bound_id, bound_name, target_id, target_name,
                )

            ledger.append(entry)

    if apply and census["applied"]:
        await session.commit()

    # After-census: re-run the predicate over the SAME rows so the response proves
    # the write landed rather than asserting it. A repair that reports success
    # without re-measuring is the failure mode this whole rail exists to kill.
    remaining = None
    if apply and census["applied"]:
        after = (
            await session.execute(
                _CANDIDATES_SQL,
                {"sport_ids": sport_ids, "since": since_date, "lim": scan_limit},
            )
        ).mappings().all()
        remaining = sum(
            1
            for r in after
            for side in ("home", "away")
            if _classify(
                r[f"{side}_team_name"], r[f"{side}_bound_name"],
                r[f"{side}_bound_sport"], r["sport_id"],
            )
        )

    return {
        "issue": "#1798",
        "apply": apply,
        # Echo the value actually used, not the caller's spelling of it.
        "scope": {
            "sport_ids": sport_ids,
            "since": since_date.isoformat(),
            "limit": scan_limit,
        },
        "census": census,
        "miswired_after": remaining,
        "ledger": ledger,
        "review": review,
        "note": (
            "Detection dereferences the FK; it never compares a name to a name. "
            "Repair re-derives from the row's own team name within the event's own "
            "sport_id and requires exactly one exact match — 0 or >1 goes to review."
        ),
    }
