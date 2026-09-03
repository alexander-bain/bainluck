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
not one row is removed, and every id this rail clears is receipted to a durable
record as it is cleared, so the repair reverses:

    POST …/authority-id-collisions?undo_identity=<id>            # dry run
    POST …/authority-id-collisions?undo_identity=<id>&apply=true # put them back
    python3 scripts/restore_authority_id_collisions.py --identity <id> --apply

The apply REFUSES to write if that record cannot be persisted (D51: a repair is
applyable unattended because it is reversible, so the reversibility is a
precondition of the write, not a property claimed afterwards). Until 2026-09-03
this docstring said the prior values were "in the plan artifact" — they were,
but that artifact is one rotating slot with a 24h life, so draining MLS and then
planning MLB destroyed MLS's undo. See ``UNDO_IDENTITY_PREFIX``.

**The record receipts what was CLEARED, not what was planned** (CERT-846). Those
differ every time a planned row's id has moved since the review: the apply
reports it ``ESPN_ID_MOVED`` and writes nothing, and a record built from the plan
would still offer to restamp it — putting an id back onto a row this rail never
touched, and re-creating a collision another writer had just resolved. So the
receipt grows one row at a time, after each unstamp commits, and the restore
replays that list and no other. The cost is one durable write per cleared row,
which is why the operator note recommends slices rather than one 352-row call.

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

# ═══ THE UNDO RECORD (D51) ═══
#
# `PLAN_IDENTITY` is ONE slot. That is right for a plan — a stale artifact must
# fail loudly rather than be found lying around and applied — and it is exactly
# wrong for an undo: the next slice's `?apply=false` overwrites the slot, and
# `PLAN_MAX_AGE_S` retires it after a day regardless. So for nine sessions this
# rail's response has closed with
#
#     "Reversible: every prior value is in the plan artifact <one slot>."
#
# while running MLS then MLB destroyed MLS's undo before anyone could use it.
# The claim was true of one apply in isolation and false of the sequence the
# note itself recommends — the same false-completeness shape as #2839's
# zero-blocker all-clear and CERT-843's cursor that never resumed: prose
# asserting a property the code does not have.
#
# An undo therefore gets its OWN dated identity per apply, never reused and
# never rotated, and the apply REFUSES to write until that record is on disk.
UNDO_IDENTITY_PREFIX = "repair:authority_id_collisions:undo"

# v1 recorded the rows the apply was ABOUT to clear and called that its backup.
# CERT-846 showed what that buys: a planned row whose id had moved since the
# review is a no-op for the apply (`ESPN_ID_MOVED`, `unstamped=0`) and was still
# listed in the record, so the restore put an id back onto a row THIS APPLY
# NEVER TOUCHED — re-creating a collision some other writer had just cleared.
# Reproduced exactly: apply `unstamped=0`, its own undo `restamped=1`.
#
# So a v2 record separates the two questions it was conflating:
#
#     rows_planned  — what the apply set out to do (the reviewed work list)
#     rows          — THE RECEIPT: rows this apply actually cleared, and only
#                     those. The restore reads this one and nothing else.
#
# The version bump is load-bearing, not cosmetic: `read_snapshot_standalone`
# is called with `expected_version=UNDO_SCHEMA`, so a v1 record — whose `rows`
# mean the other thing — cannot be read by the v2 restore at all. It reads as
# MISSING rather than being silently reinterpreted as a receipt.
UNDO_SCHEMA = "authority-id-collisions-undo/v2"

#: An undo must outlive the incident that needs it, not the day. Deliberately
#: far longer than `PLAN_MAX_AGE_S`: the two artifacts have opposite duties —
#: a plan going stale is a safety feature, an undo going stale is the loss of
#: the only record that a repair can be taken back.
UNDO_MAX_AGE_S = 365 * 86400

REASON_UNDO_UNWRITTEN = "UNDO_NOT_PERSISTED"
REASON_UNDO_MISSING = "UNDO_MISSING"
REASON_UNDO_CORRUPT = "UNDO_CORRUPT"
REASON_UNDO_UNREADABLE = "UNDO_UNREADABLE"
#: A row was cleared and its receipt could not be written. The apply STOPS —
#: it does not keep clearing rows it has lost the ability to name.
REASON_UNDO_RECEIPT_FAILED = "UNDO_RECEIPT_FAILED"

#: Per-row undo outcomes. Closed set. `ESPN_ID_REOCCUPIED` is not a failure —
#: it is the undo declining to overwrite a fresher truth, and it is named so a
#: reader can tell "restored 3 of 3" from "restored 1 and left 2 alone".
UNDO_OUTCOMES = ("RESTAMPED", "ESPN_ID_REOCCUPIED")

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

RESTAMP_SQL = text(
    # The undo's compare is IN the write too, and it is `IS NULL` rather than
    # the prior value: the only row an undo may touch is one this repair left
    # blank. A row that has since been re-anchored by `espn_sync` wears a
    # CURRENT truth, and putting yesterday's id back over it would be the undo
    # causing the very corruption it exists to reverse.
    """
    UPDATE events SET espn_id = :prior
    WHERE id = :event_id AND espn_id IS NULL
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

    envelope = DurableEnvelope.build(
        identity=PLAN_IDENTITY,
        schema_version=PLAN_SCHEMA,
        payload=payload,
        complete=True,
        source="repair:authority-id-collisions",
    )
    try:
        result = await publish_snapshot_standalone(envelope)
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        logger.warning("%s plan persist raised: %s", ISSUE, type(exc).__name__)
        return False, f"persist raised: {type(exc).__name__}"
    ok = result.get("status") in ("ok", "superseded")
    return ok, "ok" if ok else f"persist rejected: {result.get('status')}"


async def _read_plan() -> tuple[Optional[dict[str, Any]], str]:
    """``(payload, reason)`` — a raise is "I could not read", never "not there"."""
    from app.services.durable_snapshots import read_snapshot_standalone

    read = read_snapshot_standalone(
        PLAN_IDENTITY, expected_version=PLAN_SCHEMA, max_age_s=PLAN_MAX_AGE_S
    )
    try:
        got = await read
    except Exception as exc:  # noqa: BLE001 — a raise is UNREADABLE, not MISSING
        logger.warning("%s plan read raised: %s", ISSUE, type(exc).__name__)
        return None, REASON_PLAN_UNREADABLE
    if not got.ok or got.envelope is None:
        return None, REASON_PLAN_MISSING
    payload = got.envelope.payload
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        return None, REASON_PLAN_CORRUPT
    return payload, "ok"


def undo_identity_for(plan_hash: str, *, at: datetime) -> str:
    """A dated, one-per-apply identity for the undo record.

    Carries the timestamp AND the plan hash because both questions get asked:
    "what did I run at 4pm" and "what did that plan do". Second-resolution is
    enough — two applies of the same plan inside one second would be the same
    write twice, and the `AND espn_id = :contested` compare already makes the
    second a no-op.
    """
    stamp = at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{UNDO_IDENTITY_PREFIX}:{stamp}:{str(plan_hash)[:12]}"


def undo_row_for(plan_row: dict[str, Any]) -> dict[str, Any]:
    """One plan row -> the shape the undo record and the restore both read."""
    return {
        "event_id": int(plan_row["event_id"]),
        "prior_espn_id": str(plan_row["contested_espn_id"]),
        "sport": plan_row.get("sport"),
        "matchup": plan_row.get("matchup"),
        "verdict": plan_row.get("verdict"),
    }


def undo_payload(
    *,
    plan_hash: str,
    taken_at: datetime,
    sport: Optional[str],
    planned: list[dict[str, Any]],
    receipted: list[dict[str, Any]],
    complete: bool,
) -> dict[str, Any]:
    """The v2 record. ``rows`` is the RECEIPT; ``rows_planned`` is the intent.

    Keeping the receipt under ``rows`` is deliberate: it is the key the restore
    and ``--list`` already read, so after this change both speak about rows that
    were really cleared without either having to learn a new name for the only
    list that may be replayed onto the table.
    """
    return {
        "issue": ISSUE,
        "plan_hash": str(plan_hash),
        "taken_at": taken_at.isoformat(),
        "sport": sport,
        # THE RECEIPT — rows whose unstamp returned a row id AND committed.
        # A planned row that turned out to be `ESPN_ID_MOVED` is not here, and
        # that absence is the whole fix: an undo may only put back an id it can
        # prove this apply took away.
        "rows": list(receipted),
        # The intent, kept for the operator's forensics and never replayed.
        "rows_planned": list(planned),
        # False while the loop is still running. A record found `False` is an
        # apply that died or was stopped part-way; its receipt is still exact
        # for every row it names.
        "receipt_complete": complete,
    }


async def _save_undo(identity: str, payload: dict[str, Any]) -> tuple[bool, str]:
    """Persist one apply's undo record. ``superseded`` is a FAILURE here.

    `_save_plan` counts ``superseded`` as success, and for a plan that is
    right: it means a good copy of a NEWER plan is on disk, so the durability
    contract holds. For an undo it is the opposite — the row at that identity
    holds somebody else's content, so the undo on file is not this apply's, and
    accepting it would hand an operator a restore command that puts back the
    wrong rows. Only ``ok`` means "your record is the one stored".
    """
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    envelope = DurableEnvelope.build(
        identity=identity,
        schema_version=UNDO_SCHEMA,
        payload=payload,
        complete=True,
        source="repair:authority-id-collisions:undo",
    )
    try:
        result = await publish_snapshot_standalone(envelope)
    except Exception as exc:  # noqa: BLE001 — reported, never swallowed
        logger.warning("%s undo persist raised: %s", ISSUE, type(exc).__name__)
        return False, f"undo persist raised: {type(exc).__name__}"
    status = result.get("status")
    if status == "ok":
        return True, "ok"
    if status == "superseded":
        return False, (
            f"undo persist SUPERSEDED: identity {identity} already holds a newer "
            f"row, so the record on file is not this apply's"
        )
    return False, f"undo persist rejected: {status}"


async def _read_undo(identity: str) -> tuple[Optional[dict[str, Any]], str]:
    """``(payload, reason)`` — a raise is "I could not read", never "not there"."""
    from app.services.durable_snapshots import read_snapshot_standalone

    # Built outside the `try` so the awaited call is the only thing inside it —
    # the shape `_read_plan` already uses, kept identical here on purpose.
    read = read_snapshot_standalone(
        identity, expected_version=UNDO_SCHEMA, max_age_s=UNDO_MAX_AGE_S
    )
    try:
        got = await read
    except Exception as exc:  # noqa: BLE001 — a raise is UNREADABLE, not MISSING
        logger.warning("%s undo read raised: %s", ISSUE, type(exc).__name__)
        return None, REASON_UNDO_UNREADABLE
    if not got.ok or got.envelope is None:
        return None, REASON_UNDO_MISSING
    payload = got.envelope.payload
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        return None, REASON_UNDO_CORRUPT
    return payload, "ok"


def index_blocker_note(
    *,
    contested_ids: int,
    examined: int,
    slice_unresolved: int,
    sport: Optional[str],
    truncated: bool,
) -> str:
    """The index sentence, scoped to the table it is a statement about.

    #2839: this sentence used to be built from ``summary.groups_unresolved``,
    which counts only the groups THIS call examined.  A bounded call therefore
    printed, over a payload carrying ``before.contested_ids: 164``:

        ?sport=icehockey_nhl -> "cannot be created while 0 group(s) remain
                                 unresolved."

    An all-clear for the index, handed to an operator who had merely scoped to
    a quiet sport.  It is CERT-825's shape one file over — a slice-scoped count
    read as the answer to a table-scoped question — so the two numbers are kept
    apart here by construction: ``group(s)`` is spoken only of the census, and
    the slice's own count never carries that word.  A bounded call says it is
    bounded in the same breath, because a count nobody knows the scope of is
    the thing that misled.
    """
    if contested_ids:
        blocker = (
            f"The unique index on events.espn_id cannot be created while "
            f"{contested_ids} group(s) in events wear a contested espn_id."
        )
    else:
        blocker = (
            "The unique index on events.espn_id has no remaining blocker: "
            "0 group(s) in events wear a contested espn_id."
        )

    bounds = []
    if sport:
        bounds.append(f"sport={sport}")
    if truncated:
        bounds.append("truncated at limit")

    scope = (
        f" This call examined {examined} of them and leaves "
        f"{slice_unresolved} of those unresolved"
    )
    if bounds:
        scope += (
            f"; it is bounded ({', '.join(bounds)}), so its own counts do not "
            "speak for the table."
        )
    else:
        scope += "."
    return blocker + scope


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
            "unstamp exactly these rows. " + index_blocker_note(
                contested_ids=before["contested_ids"],
                examined=len(ordered),
                slice_unresolved=stats["groups_unresolved"],
                sport=sport,
                truncated=truncated,
            )
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

    # ── BACKUP BEFORE WRITE (D51) ────────────────────────────────────────────
    # Not one row is unstamped until this apply's own dated undo record is on
    # disk. The order is the whole point: a backup written afterwards is a
    # backup that does not exist for exactly the run that crashed halfway.
    undo_at = datetime.now(timezone.utc)
    undo_identity = undo_identity_for(str(plan_hash), at=undo_at)
    planned_rows = [undo_row_for(r) for r in stored["rows"]]

    def _record(receipted: list[dict[str, Any]], *, complete: bool) -> dict[str, Any]:
        return undo_payload(
            plan_hash=str(plan_hash),
            taken_at=undo_at,
            sport=stored.get("sport"),
            planned=planned_rows,
            receipted=receipted,
            complete=complete,
        )

    # The record exists before the first write with an EMPTY receipt: at this
    # instant the true answer to "what has this apply cleared" is "nothing", and
    # a backup that claims otherwise is the defect CERT-846 found.
    undo_saved, undo_note = await _save_undo(undo_identity, _record([], complete=False))
    if not undo_saved:
        return {
            "issue": ISSUE, "apply": True, "refused": True,
            "reason_codes": [REASON_UNDO_UNWRITTEN],
            "undo_identity": undo_identity,
            "undo_note": undo_note,
            "rows_in_plan": len(stored["rows"]),
            "unstamped": 0,
            "note": (
                "NOTHING WAS WRITTEN. The undo record for this apply could not be "
                "persisted, and an unstamp that cannot be taken back is not a "
                "repair this rail performs unattended (D51). Fix the durable "
                "snapshot write and re-present the same plan_hash."
            ),
        }

    applied: list[int] = []
    receipted: list[dict[str, Any]] = []
    moved: list[dict[str, Any]] = []
    by_verdict: dict[str, int] = {}
    receipt_failure: Optional[str] = None

    for row, undo_row in zip(stored["rows"], planned_rows):
        event_id = int(row["event_id"])
        contested = str(row["contested_espn_id"])
        result = (await session.execute(
            UNSTAMP_SQL, {"event_id": event_id, "contested": contested}
        )).first()
        if result is None:
            # NOT a silent success, and NOT a row the undo may speak for. The
            # row's id is no longer the one reviewed: ingest moved it, or a
            # sibling apply already took it. Either way this apply did not
            # clear it, so it never enters the receipt.
            moved.append({
                "event_id": event_id,
                "expected_espn_id": contested,
                "reason_code": "ESPN_ID_MOVED",
            })
            continue
        # Said out loud before the commit so the single row that a crash could
        # leave cleared-but-unreceipted is recoverable from the log rather than
        # from archaeology.
        logger.info(
            "%s unstamping event %s (prior espn_id %s) under undo %s",
            ISSUE, event_id, contested, undo_identity,
        )
        # `events` is hot — commit per row, the same posture Phase 2 matching
        # takes for deadlock avoidance (gotcha #13).
        await session.commit()
        applied.append(event_id)
        receipted.append(undo_row)
        verdict = str(row.get("verdict") or "UNKNOWN")
        by_verdict[verdict] = by_verdict.get(verdict, 0) + 1

        # Receipt AFTER the commit, per row. The window this leaves is one row
        # wide and it under-claims: a crash here leaves a row cleared that the
        # restore will not offer to put back. That is the safe direction — the
        # opposite order would let the record claim a row the transaction then
        # rolled back, which is the class of lie being fixed.
        ok, note = await _save_undo(undo_identity, _record(receipted, complete=False))
        if not ok:
            receipt_failure = note
            logger.warning(
                "%s receipt write failed after %s row(s); stopping the apply: %s",
                ISSUE, len(receipted), note,
            )
            break

    # Seals the record: a reader can now tell a finished apply from one that
    # stopped part-way. A failure here costs the seal, never the receipt — the
    # per-row writes above already carry every row that was cleared.
    sealed, seal_note = await _save_undo(
        undo_identity, _record(receipted, complete=receipt_failure is None)
    )

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
        # The number the operator should compare against `unstamped`, and the
        # reason this rail can call itself reversible: rows the undo record can
        # prove this apply cleared. `unstamped` and `rows_receipted` differ only
        # if a receipt write failed, and then the apply has already stopped.
        "rows_receipted": len(receipted),
        "receipt_complete": receipt_failure is None and sealed,
        **(
            {"reason_codes": [REASON_UNDO_RECEIPT_FAILED], "receipt_note": receipt_failure}
            if receipt_failure
            else {}
        ),
        **({"seal_note": seal_note} if not sealed else {}),
        # The undo is quoted as an IDENTITY and a runnable line, not as a
        # reassurance. An operator who has to go and find out how to reverse a
        # write does not have a reversible write.
        "undo_identity": undo_identity,
        "undo_command": (
            f"python3 scripts/restore_authority_id_collisions.py "
            f"--identity {undo_identity} --apply"
        ),
        "note": (
            f"contested ids {before['contested_ids']} -> {after['contested_ids']}; "
            f"rows wearing a contested id {before['rows_wearing']} -> "
            f"{after['rows_wearing']}. Reversible: the {len(receipted)} row(s) this "
            f"apply actually cleared are receipted in its OWN dated record "
            f"{undo_identity}, which no later plan or apply overwrites. The "
            f"{len(moved)} ESPN_ID_MOVED row(s) are NOT in it — this apply did not "
            f"clear them, so the restore must not put their ids back. Restore with "
            f"undo_command."
            + (
                f" WARNING: the apply STOPPED after {len(receipted)} row(s) because a "
                f"receipt could not be written ({receipt_failure}); the rows it names "
                f"are still exactly reversible, and the rest of the plan was not run."
                if receipt_failure
                else ""
            )
        ),
    }


async def _undo(session, undo_identity: str, apply: bool) -> dict[str, Any]:
    """Put back exactly the ids one apply cleared. Dry-run unless ``apply``.

    The mirror of `_apply`, with the same two properties: it acts on a stored
    artifact rather than a re-derivation, and its compare is in the write.

    **It replays the RECEIPT, never the plan.** ``rows`` is the list of rows the
    apply proved it cleared; ``rows_planned`` is what it set out to do, is often
    longer, and is read here only to report the difference. CERT-846: replaying
    the plan let an apply that cleared nothing restamp a row another writer had
    just blanked, re-creating the collision.
    """
    stored, reason = await _read_undo(undo_identity)
    if stored is None:
        return {
            "issue": ISSUE, "undo": True, "apply": apply, "refused": True,
            "undo_identity": undo_identity,
            "reason_codes": [reason],
            "note": (
                "MISSING means no undo record is stored under that identity; "
                "UNREADABLE means the read failed right now; CORRUPT means one is "
                "there and cannot be trusted. Do not re-derive to route around it."
            ),
        }

    rows = stored["rows"]
    planned = stored.get("rows_planned")
    n_planned = len(planned) if isinstance(planned, list) else None
    # A planned row missing from the receipt is a row the apply did NOT clear.
    # Named rather than summed away: an operator comparing "12 planned" with
    # "10 restorable" is looking at ESPN_ID_MOVED rows, not at lost data.
    not_cleared = (n_planned - len(rows)) if n_planned is not None else None
    incomplete = stored.get("receipt_complete") is False
    scope = (
        f"This record receipts {len(rows)} row(s) actually cleared"
        + (f" of {n_planned} planned" if n_planned is not None else "")
        + ". Only receipted rows are ever restamped."
        + (
            f" {not_cleared} planned row(s) were not cleared by that apply "
            f"(ESPN_ID_MOVED) and their ids are deliberately NOT put back."
            if not_cleared
            else ""
        )
        + (
            " The record is NOT sealed: that apply stopped part-way, so it may "
            "have cleared one further row than it receipted — check the logs for "
            "the identity before assuming the table is fully reversed."
            if incomplete
            else ""
        )
    )
    before = await _census(session)
    if not apply:
        return {
            "issue": ISSUE, "undo": True, "apply": False,
            "undo_identity": undo_identity,
            "plan_hash": stored.get("plan_hash"),
            "taken_at": stored.get("taken_at"),
            "before": before,
            "rows_in_record": len(rows),
            "rows_planned_in_record": n_planned,
            "receipt_complete": stored.get("receipt_complete"),
            "rows": rows,
            "note": (
                f"Nothing was written. Re-run with apply=true to put these "
                f"{len(rows)} id(s) back. A row that has since been re-anchored is "
                f"reported ESPN_ID_REOCCUPIED and left alone. " + scope
            ),
        }

    restamped: list[int] = []
    reoccupied: list[dict[str, Any]] = []
    for row in rows:
        event_id = int(row["event_id"])
        prior = str(row["prior_espn_id"])
        result = (await session.execute(
            RESTAMP_SQL, {"event_id": event_id, "prior": prior}
        )).first()
        if result is None:
            reoccupied.append({
                "event_id": event_id,
                "prior_espn_id": prior,
                "reason_code": "ESPN_ID_REOCCUPIED",
            })
            continue
        restamped.append(event_id)
        # Same per-row commit posture as the apply — `events` is hot.
        await session.commit()

    after = await _census(session)
    return {
        "issue": ISSUE, "undo": True, "apply": True,
        "undo_identity": undo_identity,
        "plan_hash": stored.get("plan_hash"),
        "before": before,
        "after": after,
        "rows_in_record": len(rows),
        "rows_planned_in_record": n_planned,
        "receipt_complete": stored.get("receipt_complete"),
        "restamped": len(restamped),
        "reoccupied": reoccupied,
        "note": (
            f"contested ids {before['contested_ids']} -> {after['contested_ids']}; "
            f"rows wearing a contested id {before['rows_wearing']} -> "
            f"{after['rows_wearing']}. Putting ids back RE-CREATES the collisions "
            f"this apply removed — that is what an undo is — so the unique index "
            f"pre-check will rise by the number restored. " + scope
        ),
    }


async def repair(
    session,
    apply: bool = False,
    plan_hash: Optional[str] = None,
    sport: Optional[str] = None,
    limit: Optional[int] = None,
    undo_identity: Optional[str] = None,
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
        undo_identity: put one earlier apply's ids BACK. Takes precedence over
            every other argument — an undo is never also a derive — and is
            itself dry-run unless ``apply`` is true.
    """
    if undo_identity:
        return await _undo(session, undo_identity, apply)
    if apply:
        return await _apply(session, plan_hash)
    return await _derive(session, sport, limit)
