"""One game, one authority id — the write half. #2693 step 2.

    POST /api/admin/repairs/authority-id-collisions?apply=false
    POST /api/admin/repairs/authority-id-collisions?apply=true&plan_hash=…

Measured on production 2026-09-02: **196 ESPN event ids are worn by 430
``events`` rows**, across 13 sports.  ``events.espn_id`` is the column
``espn_sync`` steers every status, ``commence_time``, ``completed_at`` and
win-probability correction through, so an id naming two rows means the
authority writes one game's truth onto two fixtures — which is how a card
printed "Final" over a match in its fourth set (lane1/057).

WHO DECIDES is not in this file.  ``app/utils/authority_id_collisions``
holds the verdict logic, pure, and the audit script
``scripts/audit_authority_id_collisions.py`` runs the identical copy against
production — so the dry-run counts quoted in a PR and the counts this rail acts
on cannot drift.  Read that module first; it is where the reasoning lives.

═══ THE WRITE IS ONE NULLABLE COLUMN, AND NOTHING ELSE ═══

    UPDATE events SET espn_id = NULL
     WHERE id = :event_id AND espn_id = :contested_espn_id

No merge, no DELETE, no FK re-pointed, no second column.  A twin and a
wrong-fixture row get the same write and are distinguished only in the receipt,
because the follow-ups differ (a twin is a duplicate-EVENT candidate; a wrong
fixture is a matching bug) while the remedy does not.

**The compare is IN the write.** ``AND espn_id = :contested`` is what makes an
apply safe across the hours between the review and the run: a row whose id
moved in that window matches nothing, ``rowcount == 0``, and it is recorded as
``ESPN_ID_MOVED`` rather than written blind.  This is why this rail does NOT
carry the stillness-probe precondition its sibling ``repair_event_espn_id``
carries (ruling 095).  That rail writes a *specific other id* and a stale
review can therefore write a wrong value; this one writes NULL, so the worst
outcome of a moved row is a no-op the response names.  Stated as a departure,
not smuggled: if a reviewer wants the population proven still first, the audit
script re-derives the whole census in one call.

**Correction, never deletion** (ruling 079) holds in the strong sense here —
not one row is removed, and every prior value is in the plan artifact, so the
entire repair reverses with an UPDATE that reads the artifact back.

═══ THE TWO-CALL CONTRACT ═══

``?apply=false`` derives, asks ESPN, decides, persists the plan and returns its
``plan_hash``.  ``?apply=true&plan_hash=…`` loads THAT artifact and writes only
its rows — it re-derives nothing and re-asks ESPN nothing.  An apply with no
hash, or a hash that names no artifact, is REFUSED (#1949): a work list that
can be recomputed at apply time is a work list that can differ from the one a
human read, and no after-measurement can say afterwards which of the two was
written.

═══ WHAT IT WILL LEAVE BEHIND, STATED UP FRONT ═══

Two outcomes write nothing and are expected to survive the run:
``AUTHORITY_UNAVAILABLE`` (ESPN did not answer — 401504210 returns a 502 today)
and ``NO_ROW_AGREES`` (ESPN answered and recognised neither row — ``CA Osasuna``
is not a name ESPN publishes for Osasuna).  Measured 2026-09-02 that is **8 of
196 groups**, and the unique index on ``espn_id`` cannot be created while any
of them stands.  The response reports the residual by name so the migration
note can quote a number rather than a hope.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text

from app.utils.authority_id_collisions import (
    AuthorityRecord,
    CandidateRow,
    authority_names,
    decide_group,
    summarize,
)

logger = logging.getLogger(__name__)

ISSUE = "#2693"

#: Durable identity of the reviewed plan. ONE slot, so a stale artifact fails
#: loudly instead of being found lying around and applied.
PLAN_IDENTITY = "repair:authority_id_collisions:apply_plan"
PLAN_SCHEMA = "authority-id-collisions-plan/v1"

#: How long a persisted plan may be consumed for. Long enough for a review and
#: a bus grade; short enough that yesterday's plan cannot be applied to today's
#: population by accident.
PLAN_MAX_AGE_S = 24 * 3600

REASON_PLAN_REQUIRED = "PLAN_HASH_REQUIRED"
REASON_PLAN_MISSING = "PLAN_MISSING"
REASON_PLAN_MISMATCH = "PLAN_HASH_MISMATCH"
REASON_PLAN_CORRUPT = "PLAN_CORRUPT"
#: "The read failed right now" — a THIRD reading, never folded into MISSING. An
#: operator told the plan is missing goes and makes one, which is the wrong move
#: when it is there and the read fell over.
REASON_PLAN_UNREADABLE = "PLAN_UNREADABLE"

#: Per-row apply outcomes. Closed set.
APPLY_OUTCOMES = ("UNSTAMPED", "ESPN_ID_MOVED")

COLLISION_SQL = text(
    """
    SELECT e.espn_id, e.id, s.key, e.home_team_name, e.away_team_name,
           e.commence_time, e.external_id, ht.espn_id, at.espn_id,
           (SELECT count(*) FROM futures_markets fm WHERE fm.event_id = e.id)
             + (SELECT count(*) FROM odds_snapshots os WHERE os.event_id = e.id)
             AS dependents
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    LEFT JOIN teams ht ON ht.id = e.home_team_id
    LEFT JOIN teams at ON at.id = e.away_team_id
    WHERE e.espn_id IN (
        SELECT espn_id FROM events
        WHERE espn_id IS NOT NULL
        GROUP BY espn_id HAVING count(*) > 1
    )
    ORDER BY e.espn_id, e.id
    """
)

CENSUS_SQL = text(
    """
    SELECT count(*) AS contested_ids, coalesce(sum(n), 0) AS rows_wearing
    FROM (
        SELECT count(*) AS n FROM events
        WHERE espn_id IS NOT NULL
        GROUP BY espn_id HAVING count(*) > 1
    ) t
    """
)

UNSTAMP_SQL = text(
    # The compare is IN the write — see the module docstring. `RETURNING` so a
    # zero-rowcount row is distinguishable from a row that was never attempted.
    """
    UPDATE events SET espn_id = NULL
    WHERE id = :event_id AND espn_id = :contested
    RETURNING id
    """
)


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else None


def _parse_time(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace(" ", "T", 1).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def plan_hash_for(rows: list[dict[str, Any]]) -> str:
    """Content address of the work list, and of nothing else.

    Over the ROWS only — not the census, not the summary, not the clock. Two
    derives that select the same work must produce the same hash, or a reviewer
    who re-ran the dry run to look again would be handed a hash that refuses
    the plan they already read.
    """
    canonical = json.dumps(
        [
            {
                "event_id": int(r["event_id"]),
                "contested_espn_id": str(r["contested_espn_id"]),
                "verdict": str(r["verdict"]),
            }
            for r in rows
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def record_from_summary(
    authority_id: str, payload: Optional[dict[str, Any]]
) -> Optional[AuthorityRecord]:
    """ESPN's ``summary`` body -> an :class:`AuthorityRecord`. Pure.

    ``None`` in, ``None`` out, and ``None`` out for a body with no competition:
    an absent answer must reach ``decide_group`` as an absence, because that is
    the difference between ``AUTHORITY_UNAVAILABLE`` and a real verdict.
    """
    if not payload:
        return None
    competitions = (payload.get("header") or {}).get("competitions") or []
    if not competitions:
        return None
    competition = competitions[0]
    home: frozenset[str] = frozenset()
    away: frozenset[str] = frozenset()
    home_id: Optional[str] = None
    away_id: Optional[str] = None
    labels: dict[str, str] = {}
    for competitor in competition.get("competitors") or []:
        block = competitor.get("team") if isinstance(competitor.get("team"), dict) else competitor
        names = authority_names(competitor)
        side = competitor.get("homeAway")
        team_id = block.get("id")
        labels[str(side)] = block.get("displayName") or (sorted(names)[0] if names else "?")
        if side == "home":
            home, home_id = names, (str(team_id) if team_id is not None else None)
        elif side == "away":
            away, away_id = names, (str(team_id) if team_id is not None else None)
    return AuthorityRecord(
        authority_id=str(authority_id),
        home_names=home,
        away_names=away,
        home_team_id=home_id,
        away_team_id=away_id,
        starts_at=_parse_time(competition.get("date")),
        label=f"{labels.get('home', '?')} v {labels.get('away', '?')}",
    )


async def _fetch_record(service, sport_keys, authority_id: str):
    """Ask ESPN, through the shared client, in each sport the group names.

    A group whose rows span two sport keys (the 2026-05-23 Giants/White Sox
    group spans ``baseball_mlb`` and ``baseball_mlb_preseason``) gets one try
    per key: the id is real and only one league path resolves it.
    """
    from app.services.espn_api import ESPN_API_BASE, ESPNAuthorityDark
    from app.utils.sport_keys import SPORT_LEAGUE_MAP

    for sport_key in dict.fromkeys(sport_keys):
        path = SPORT_LEAGUE_MAP.get(sport_key)
        if path is None:
            continue
        url = f"{ESPN_API_BASE}/{path[0]}/{path[1]}/summary?event={authority_id}"
        try:
            payload = await service._get(url)  # noqa: SLF001 — the 404/dark split lives here
        except ESPNAuthorityDark:
            # NOT an absence. A dark authority must reach the decider as None
            # so the group lands in AUTHORITY_UNAVAILABLE and writes nothing.
            continue
        record = record_from_summary(authority_id, payload)
        if record is not None and record.usable:
            return record
    return None


async def _census(session) -> dict[str, int]:
    row = (await session.execute(CENSUS_SQL)).first()
    return {"contested_ids": int(row[0] or 0), "rows_wearing": int(row[1] or 0)}


async def _load_groups(session, sport: Optional[str]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in (await session.execute(COLLISION_SQL)).all():
        groups.setdefault(str(row[0]), []).append({
            "event_id": int(row[1]),
            "sport": row[2],
            "home": row[3] or "",
            "away": row[4] or "",
            "commence_time": row[5],
            "external_id": row[6],
            "home_team_espn_id": row[7],
            "away_team_espn_id": row[8],
            "dependents": int(row[9] or 0),
        })
    if sport:
        groups = {k: v for k, v in groups.items() if any(r["sport"] == sport for r in v)}
    return groups


async def _save_plan(payload: dict[str, Any]) -> tuple[bool, str]:
    """Persist to the durable snapshot rail — not Redis.

    CAL-P058's reason: a SETEX on an allkeys-lru instance can be evicted, and an
    operator who cannot be handed a hash must be TOLD so, because the next thing
    they will do is try to apply.
    """
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=PLAN_IDENTITY,
                schema_version=PLAN_SCHEMA,
                payload=payload,
                complete=True,
                source="repair:authority-id-collisions",
            )
        )
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        logger.warning("%s plan persist raised: %s", ISSUE, type(exc).__name__)
        return False, f"persist raised: {type(exc).__name__}"
    ok = result.get("status") in ("ok", "superseded")
    return ok, "ok" if ok else f"persist rejected: {result.get('status')}"


async def _read_plan() -> tuple[Optional[dict[str, Any]], str]:
    """``(payload, reason)`` — a raise is "I could not read", never "not there"."""
    from app.services.durable_snapshots import read_snapshot_standalone

    try:
        got = await read_snapshot_standalone(
            PLAN_IDENTITY, expected_version=PLAN_SCHEMA, max_age_s=PLAN_MAX_AGE_S
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s plan read raised: %s", ISSUE, type(exc).__name__)
        return None, REASON_PLAN_UNREADABLE
    if not got.ok or got.envelope is None:
        return None, REASON_PLAN_MISSING
    payload = got.envelope.payload
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        return None, REASON_PLAN_CORRUPT
    return payload, "ok"


async def _derive(session, sport: Optional[str], limit: Optional[int]) -> dict[str, Any]:
    from app.services.espn_api import espn_authority_state, get_espn_service

    before = await _census(session)
    groups = await _load_groups(session, sport)
    ordered = sorted(groups.items())
    truncated = False
    if limit is not None and limit > 0 and len(ordered) > limit:
        ordered, truncated = ordered[:limit], True

    service = get_espn_service()
    decisions = []
    detail: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for authority_id, raw in ordered:
        record = await _fetch_record(service, [r["sport"] for r in raw], authority_id)
        candidates = [
            CandidateRow(
                event_id=r["event_id"],
                sport_key=r["sport"],
                home_team_name=r["home"],
                away_team_name=r["away"],
                commence_time=_parse_time(r["commence_time"]),
                home_team_authority_id=r["home_team_espn_id"],
                away_team_authority_id=r["away_team_espn_id"],
                weight=r["dependents"],
                has_external_id=bool(r["external_id"]),
            )
            for r in raw
        ]
        decision = decide_group(record, candidates, authority_id=authority_id)
        decisions.append(decision)
        by_id = {r["event_id"]: r for r in raw}
        verdict_by_id = {v.event_id: v for v in decision.rows}
        detail.append({
            "authority_id": authority_id,
            "sport": raw[0]["sport"],
            "espn": record.label if record else None,
            "outcome": decision.outcome,
            "keep_event_id": decision.keep_event_id,
            "twin_event_ids": list(decision.twin_event_ids),
            "note": decision.note,
        })
        for event_id in decision.unstamp_event_ids:
            source = by_id[event_id]
            verdict = verdict_by_id[event_id]
            rows.append({
                "event_id": event_id,
                "contested_espn_id": authority_id,
                "verdict": verdict.verdict,
                "sport": source["sport"],
                "matchup": f"{source['home']} v {source['away']}",
                "our_commence_time": _iso(source["commence_time"]),
                "dependents": source["dependents"],
                "keeper_event_id": decision.keep_event_id,
                "espn": record.label if record else None,
                # The team FK's own answer, recorded and not consulted — a row
                # whose names agree while these point elsewhere is #1204.
                "team_fk_espn_ids": [
                    source["home_team_espn_id"], source["away_team_espn_id"]
                ],
                "authority_team_ids": (
                    [record.home_team_id, record.away_team_id] if record else None
                ),
            })

    stats = summarize(decisions)
    digest = plan_hash_for(rows)
    saved, note = await _save_plan({
        "issue": ISSUE,
        "plan_hash": digest,
        "sport": sport,
        "rows": rows,
        "summary": stats,
        "before": before,
    })

    return {
        "issue": ISSUE,
        "apply": False,
        "plan_hash": digest if saved else None,
        "plan_persisted": saved,
        "plan_note": note,
        "before": before,
        "groups_examined": len(ordered),
        "groups_truncated": truncated,
        "summary": stats,
        "rows_planned": len(rows),
        "espn_authority": espn_authority_state(),
        # Named, not summed into "unresolved": a group ESPN could not answer
        # about and a group ESPN answered about clearly are different findings
        # with different next steps.
        "residual": [d for d in detail if d["outcome"] not in ("RESOLVED_ONE", "RESOLVED_MERGE")],
        "groups": detail,
        "note": (
            "Nothing was written. Re-run with ?apply=true&plan_hash=<plan_hash> to "
            "unstamp exactly these rows. The unique index on events.espn_id cannot be "
            f"created while {stats['groups_unresolved']} group(s) remain unresolved."
        ),
    }


async def _apply(session, plan_hash: Optional[str]) -> dict[str, Any]:
    if not plan_hash:
        return {
            "issue": ISSUE, "apply": True, "refused": True,
            "reason_codes": [REASON_PLAN_REQUIRED],
            "note": (
                "An apply is bound to the plan a human read. Run ?apply=false first "
                "and present the plan_hash it returns."
            ),
        }

    stored, reason = await _read_plan()
    if stored is None:
        return {
            "issue": ISSUE, "apply": True, "refused": True,
            "reason_codes": [reason],
            "note": (
                "MISSING means no plan is persisted (or it aged out); UNREADABLE means "
                "the read failed right now; CORRUPT means one is there and cannot be "
                "trusted — do not re-derive to route around it, read it."
            ),
        }
    if str(stored.get("plan_hash")) != str(plan_hash):
        return {
            "issue": ISSUE, "apply": True, "refused": True,
            "reason_codes": [REASON_PLAN_MISMATCH],
            "presented": plan_hash,
            "stored": stored.get("plan_hash"),
            "note": "The persisted plan is not the one presented. Re-derive and re-read.",
        }

    before = await _census(session)
    applied: list[int] = []
    moved: list[dict[str, Any]] = []
    by_verdict: dict[str, int] = {}

    for row in stored["rows"]:
        event_id = int(row["event_id"])
        contested = str(row["contested_espn_id"])
        result = (await session.execute(
            UNSTAMP_SQL, {"event_id": event_id, "contested": contested}
        )).first()
        if result is None:
            # NOT a silent success. The row's id is no longer the one reviewed:
            # ingest moved it, or a sibling apply already took it.
            moved.append({
                "event_id": event_id,
                "expected_espn_id": contested,
                "reason_code": "ESPN_ID_MOVED",
            })
            continue
        applied.append(event_id)
        verdict = str(row.get("verdict") or "UNKNOWN")
        by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
        # `events` is hot — commit per row, the same posture Phase 2 matching
        # takes for deadlock avoidance (gotcha #13).
        await session.commit()

    after = await _census(session)
    return {
        "issue": ISSUE,
        "apply": True,
        "plan_hash": plan_hash,
        "before": before,
        "after": after,
        "rows_in_plan": len(stored["rows"]),
        "unstamped": len(applied),
        "unstamped_by_verdict": dict(sorted(by_verdict.items())),
        "moved": moved,
        "note": (
            f"contested ids {before['contested_ids']} -> {after['contested_ids']}; "
            f"rows wearing a contested id {before['rows_wearing']} -> "
            f"{after['rows_wearing']}. Reversible: every prior value is in the plan "
            f"artifact {PLAN_IDENTITY}."
        ),
    }


async def repair(
    session,
    apply: bool = False,
    plan_hash: Optional[str] = None,
    sport: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """Hand back every authority id worn by a row that is not its game.

    Args:
        apply: False (default) derives, asks ESPN and persists a plan. True
            consumes one and writes.
        plan_hash: content address of the reviewed dry run. REQUIRED on apply.
        sport: restrict the derive to one sport key. The biggest bucket is
            ``baseball_ncaa`` (123 of the 196 contested ids).
        limit: bound the derive to N contested ids. The derive makes one ESPN
            call per id, so an unbounded run over 196 takes ~60s.
    """
    if apply:
        return await _apply(session, plan_hash)
    return await _derive(session, sport, limit)
