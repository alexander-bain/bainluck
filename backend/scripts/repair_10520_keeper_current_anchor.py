"""#10520 — anchor keeper 14969919's OWN current Odds API id. One row, nothing else.

THE SHIP: Vancouver Whitecaps at Chicago Fire (MLS, 2026-10-07 00:30Z) has one
correctly identified game card. This tool is one precondition for that, not the
ship itself; see WHAT THIS DOES NOT DO.

WHY ONE ROW
-----------

Keeper 14969919 owns two Odds API ids. Its ``external_id`` column holds
``1d13bd27…``; the other, ``0d9ff865…``, has been anchored to it since 2026-09-21
(``event_provider_anchors`` 187393). #8278's rescue
(``anchor_channel._is_a_second_id_of_the_row_that_owns_the_first``) accepts a
second id only when the column's OWN id is ALSO anchored to the same row. That
anchor does not exist: shopper's 10:21:21Z read (fingerprint 81ee2b22a8dd7b79)
found no ``odds_api`` game anchor for ``1d13bd27…`` held by ANY row. So a claim
for ``0d9ff865…`` that reaches Step 2 is refused as stale and creates a row, which
is the guard behaving as written (``test_an_unanchored_column_id_refuses``).

The registry never back-fills that anchor. It writes one only when a
correspondence is newly established, and the keeper's column was established in
June, before the channel had writers. This tool writes that one anchor through
the existing writer, :func:`app.services.anchor_channel.record_anchor`
(``INSERT … ON CONFLICT DO NOTHING`` + read-back, never a repoint). It does not
change the matcher, relax #8278/CERT-410/ruling 048, or seed any other row.

WHAT IS WRITTEN
---------------

One ``event_provider_anchors`` row: ``(odds_api, 1d13bd275c7b67b77bea8ff4d03850cc,
game) -> 14969919``. Its ``claim_context`` names this tool, the issue and a
per-invocation id banked in the backup BEFORE the database is touched, so the
restore can tell this invocation's row from any other.

Nothing else is written. ``events`` (keeper and twin), the incoming anchor 187393
and the official-fixture anchors are read, locked and compared, never changed.

ADMISSION (every gate fails closed; the same pure function serves all modes)
--------------------------------------------------------------------------

* KEEPER: the row exists and its identity columns equal the retained evidence
  exactly: sport 1326 (key ``soccer_usa_mls``), teams 16/23, both names,
  ``external_id`` = the current Odds id, ``espn_id`` 761660,
  ``statpal_fixture_id`` 9163448, ``commence_time`` 2026-10-07T00:30Z. ``status`` is
  banked, not fenced — a game going live does not change which game it is.
* INCOMING: ``(odds_api, 0d9ff865…, game)`` exists, is row 187393 and is owned by
  the keeper. A market/container anchor or another provider's row is not it.
* OFFICIAL FIXTURE: ``(statpal, soccer:9163448, game)`` is row 295737, owned by
  the keeper; ``(espn, 761660, game)`` is absent or owned by the keeper.
* CURRENT: ``(odds_api, 1d13bd27…, game)`` absent -> CANDIDATE (the only state that
  writes); owned by the keeper -> NOT_NEEDED (idempotent no-op, exit 0); owned by
  any other row -> REFUSED. Never repointed.

THREE MODES
-----------

``--preflight`` (default) reads in one REPEATABLE READ READ ONLY transaction and
writes an immutable plan (exclusive create, fsync, read-only) with a detached
``<plan>.sha256``. ``--apply`` consumes only that plan by its detached hash, banks
a backup BEFORE connecting, then in one bounded transaction locks the keeper
``FOR UPDATE`` (an anchor FK insert for the keeper needs ``FOR KEY SHARE`` on it,
so no other writer can anchor anything to the keeper meanwhile) and the three
existing anchors ``FOR SHARE``, re-runs admission, compares with the plan, calls
``record_anchor`` and requires ``WROTE`` plus an exact in-transaction read-back.
After COMMIT a new transaction verifies and records whether Step 2 now resolves
the incoming id to the keeper. A failure around COMMIT is classified from an
exact-key read (absent = NOT_APPLIED, this invocation's row = APPLIED, else
COMMIT_UNKNOWN) and the tool stops; it never re-applies.

``--restore`` deletes ONLY the row this invocation created: same key, same owner,
and a ``claim_context`` equal to the one banked in the backup (invocation id
included). A pre-existing row, a row another writer created, or a row that has
changed since is refused and left alone. No row at the key is NOT_APPLIED.
Restoring re-opens #8278's refusal for the incoming id — run it only to undo.

WHAT THIS DOES NOT DO
---------------------

``events.external_id`` is unique and twin 15324922 holds ``0d9ff865…`` in its own
column, so registry Step 1 keeps resolving that id to the twin while the twin
exists. This anchor changes what happens AFTER the twin is gone: 187393 already
names the keeper, so the next claim misses Step 1, reaches Step 2 and is rescued
instead of minting a third row. Apply it before (or with) the twin's disposition.
Twin disposition, natural-poll rescue and reader acceptance are separate.

INTERFACE (specimens only; running any of them needs root's separate admission)
------------------------------------------------------------------------------

    python3 scripts/repair_10520_keeper_current_anchor.py --only 14969919 --preflight --plan-out /abs/plan.json
    python3 scripts/repair_10520_keeper_current_anchor.py --only 14969919 --apply --plan /abs/plan.json --plan-hash <hex> --backup-out /abs/backup.json
    python3 scripts/repair_10520_keeper_current_anchor.py --only 14969919 --restore --backup /abs/backup.json --backup-hash <hex>

Refuses unless ``HEROKU_APP_NAME`` is ``bainluck`` — a target fence, not approval.
Exit codes: 0 PLANNED / APPLIED / NOT_NEEDED / restore NOT_APPLIED (nothing at the
key); 1 REFUSED; 2 usage; 3 COMMIT_UNKNOWN; 4 runtime harness error.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.services.anchor_channel import (  # noqa: E402
    CONFIRMED,
    WROTE,
    anchor_key_for_claim,
    find_event_by_anchor,
    record_anchor,
)
from app.utils.repair_apply_plan import digest_fields  # noqa: E402

TOOL = "repair_10520_keeper_current_anchor"
ISSUE = 10520
PRODUCTION_APPS = frozenset({"bainluck"})

PLAN_SCHEMA = "repair-10520-keeper-anchor-plan/v1"
BACKUP_SCHEMA = "repair-10520-keeper-anchor-backup/v1"
RECEIPT_SCHEMA = "repair-10520-keeper-anchor-receipt/v1"
ADDRESS_NAMESPACE = "bainluck:repair:10520:keeper-current-anchor"

#: The retained evidence this population is pinned to (artifacts, read-only).
EVIDENCE = {
    "keeper_and_twin_rows": "artifacts/shopper/pass-0237/q10520a.json + q10520b.json (2026-10-05 09:25Z)",
    "keeper_anchors": "artifacts/shopper/pass-0237/q10520c.json (2026-10-05 09:25Z)",
    "current_key_unowned": "artifacts/shopper/10520-second-anchor/q10520e (2026-10-05T10:21:21Z, "
                           "fingerprint 81ee2b22a8dd7b79)",
    "source_admission": "ROOT-OFFLINE-REPAIR-PREPARATION-BOUNDARY.md (20261005T082140Z-10520-59fb43)",
}

KEEPER_ID = 14969919
TWIN_ID = 15324922  # recorded only; never read, judged or written
CURRENT_ODDS_ID = "1d13bd275c7b67b77bea8ff4d03850cc"
INCOMING_ODDS_ID = "0d9ff865c4599c72a746da08260279b3"
INCOMING_ANCHOR_ID = 187393
STATPAL_ANCHOR_ID = 295737

SPORT_KEY = "soccer_usa_mls"

#: The keeper's identity columns, exactly as the retained rows carry them.
IDENTITY = {
    "sport_id": 1326,
    "home_team_id": 16,
    "away_team_id": 23,
    "home_team_name": "Chicago Fire",
    "away_team_name": "Vancouver Whitecaps FC",
    "external_id": CURRENT_ODDS_ID,
    "espn_id": "761660",
    "statpal_fixture_id": "9163448",
    "commence_time": "2026-10-07T00:30:00+00:00",
}
FENCED_COLUMNS = tuple(IDENTITY)

#: Every key is built by the channel's own key function — never hand-formatted.
CURRENT_KEY = anchor_key_for_claim("odds_api", CURRENT_ODDS_ID)
INCOMING_KEY = anchor_key_for_claim("odds_api", INCOMING_ODDS_ID)
STATPAL_KEY = anchor_key_for_claim("statpal", IDENTITY["statpal_fixture_id"], sport_key=SPORT_KEY)
ESPN_KEY = anchor_key_for_claim("espn", IDENTITY["espn_id"])
ANCHOR_KEYS = {"current": CURRENT_KEY, "incoming": INCOMING_KEY,
               "statpal": STATPAL_KEY, "espn": ESPN_KEY}

LOCK_TIMEOUT_MS = 5000
STATEMENT_TIMEOUT_MS = 10000

PLANNED, APPLIED, NOT_NEEDED, NOT_APPLIED = "PLANNED", "APPLIED", "NOT_NEEDED", "NOT_APPLIED"
RESTORED, REFUSED, COMMIT_UNKNOWN = "RESTORED", "REFUSED", "COMMIT_UNKNOWN"
EXIT_OK, EXIT_REFUSED, EXIT_USAGE, EXIT_COMMIT_UNKNOWN, EXIT_RUNTIME = 0, 1, 2, 3, 4


class Refused(RuntimeError):
    """A gate refused. Nothing was written."""

    def __init__(self, reason: str, detail: Any = None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


# --- pure ---------------------------------------------------------------------

def canon(value: Any) -> Any:
    """The one JSON form a value is banked, compared and addressed in."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise Refused("naive_timestamp", str(value))
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(k): canon(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [canon(v) for v in value]
    return value


def canon_safe(value: Any) -> Any:
    try:
        return canon(value)
    except Exception:  # detail is diagnostic; never let it mask the refusal
        return repr(value)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_address(schema: str, payload: dict) -> str:
    body = {k: v for k, v in payload.items() if k != "content_address"}
    line = digest_fields(ADDRESS_NAMESPACE, schema, canonical_json(body))
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def key_dict(key) -> dict:
    return {"source": key.source, "source_id": key.source_id, "id_kind": key.id_kind}


def _owned(anchor: dict | None) -> dict | None:
    return None if anchor is None else {"id": anchor["id"], "event_id": anchor["event_id"]}


def admit(keeper: dict | None, sport_key: Any, anchors: dict[str, dict | None]) -> dict:
    """Every gate, in order -> ``{"state": CANDIDATE|NOT_NEEDED, ...}``, or Refused.

    ``keeper``: the keeper row (fenced columns + status) or None. ``sport_key``:
    ``sports.key`` of the keeper's sport. ``anchors``: the exact-key row for each
    of ``ANCHOR_KEYS`` (``{id, event_id, source, source_id, id_kind}``) or None.
    """
    if keeper is None:
        raise Refused("keeper_missing", {"event_id": KEEPER_ID})
    observed = {c: canon(keeper.get(c)) for c in FENCED_COLUMNS}
    changed = [c for c in FENCED_COLUMNS if observed[c] != IDENTITY[c]]
    if changed:
        raise Refused("keeper_identity_changed:" + ",".join(changed),
                      {c: {"expected": IDENTITY[c], "observed": observed[c]} for c in changed})
    if sport_key != SPORT_KEY:
        raise Refused("keeper_sport_key_changed", {"expected": SPORT_KEY, "observed": sport_key})

    for name, row in anchors.items():
        if row is not None and (row.get("source"), row.get("source_id"), row.get("id_kind")) != (
            ANCHOR_KEYS[name].source, ANCHOR_KEYS[name].source_id, ANCHOR_KEYS[name].id_kind
        ):
            raise Refused(f"anchor_read_not_exact_key:{name}", canon_safe(row))

    inc = anchors.get("incoming")
    if inc is None:
        raise Refused("incoming_game_anchor_absent", key_dict(INCOMING_KEY))
    if inc["event_id"] != KEEPER_ID:
        raise Refused("incoming_game_anchor_not_keepers", _owned(inc))
    if inc["id"] != INCOMING_ANCHOR_ID:
        raise Refused("incoming_game_anchor_row_changed", _owned(inc))

    sp = anchors.get("statpal")
    if sp is None:
        raise Refused("official_statpal_anchor_absent", key_dict(STATPAL_KEY))
    if sp["event_id"] != KEEPER_ID or sp["id"] != STATPAL_ANCHOR_ID:
        raise Refused("official_statpal_anchor_not_keepers", _owned(sp))
    espn = anchors.get("espn")
    if espn is not None and espn["event_id"] != KEEPER_ID:
        raise Refused("official_espn_anchor_owned_elsewhere", _owned(espn))

    cur = anchors.get("current")
    if cur is not None and cur["event_id"] != KEEPER_ID:
        raise Refused("current_key_owned_elsewhere", _owned(cur))

    return {
        "state": "CANDIDATE" if cur is None else NOT_NEEDED,
        "keeper_id": KEEPER_ID,
        "write": {"table": "event_provider_anchors", "key": key_dict(CURRENT_KEY), "event_id": KEEPER_ID},
        "identity": observed,
        "sport_key": sport_key,
        "status_banked": keeper.get("status"),
        "anchors": {name: _owned(anchors.get(name)) for name in ANCHOR_KEYS},
    }


#: What must still hold at apply that the plan observed. ``status_banked`` is not
#: here on purpose: it is recorded, never fenced.
_DRIFT_FIELDS = ("identity", "sport_key", "anchors")


def plan_drift(plan: dict, now: dict) -> list[str]:
    return [f for f in _DRIFT_FIELDS if plan.get(f) != now.get(f)]


def claim_context_for(invocation_id: str, plan_address: str) -> dict:
    return {
        "source": "odds_api",
        "written_by": TOOL,
        "issue": ISSUE,
        "invocation_id": invocation_id,
        "plan_content_address": plan_address,
        "basis": (f"keeper {KEEPER_ID} events.external_id; incoming odds_api game anchor "
                  f"{INCOMING_ANCHOR_ID} already owned by the keeper (#8278 second-id corroboration)"),
    }


def created_row_matches(row: dict | None, claim_context: dict) -> list[str]:
    """Fields of the row at CURRENT_KEY that are not this invocation's write."""
    if row is None:
        return ["row_missing"]
    want = {**key_dict(CURRENT_KEY), "event_id": KEEPER_ID, "claim_context": claim_context}
    return [f for f, v in want.items() if canon(row.get(f)) != v]


# --- durable files ------------------------------------------------------------

_fsync = os.fsync  # module seam


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_new_absolute(path: str, what: str) -> None:
    if not path or not os.path.isabs(path):
        raise Refused(f"{what}_path_not_absolute", path)
    for p in (path, path + ".sha256"):
        if os.path.lexists(p):
            raise Refused(f"{what}_path_exists", p)
    if not os.path.isdir(os.path.dirname(path)):
        raise Refused(f"{what}_directory_missing", os.path.dirname(path))


def _write_once(path: str, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        _fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o400)
    dfd = os.open(os.path.dirname(path), os.O_RDONLY)
    try:
        _fsync(dfd)
    finally:
        os.close(dfd)


def write_artifact(path: str, schema: str, body: dict, what: str) -> dict:
    """Exclusive, fsynced, read-only JSON + detached ``<path>.sha256``."""
    _require_new_absolute(path, what)
    payload = {"schema": schema, **body}
    payload["content_address"] = content_address(schema, payload)
    data = (canonical_json(payload) + "\n").encode("utf-8")
    digest = _sha256_hex(data)
    try:
        _write_once(path, data)
        _write_once(path + ".sha256", f"{digest}  {os.path.basename(path)}\n".encode())
    except OSError as exc:
        raise Refused(f"{what}_durability_failed", f"{type(exc).__name__}: {exc}") from exc
    with open(path, "rb") as fh:
        if _sha256_hex(fh.read()) != digest:
            raise Refused(f"{what}_readback_mismatch", path)
    return {"path": path, "sha256": digest, "content_address": payload["content_address"]}


def load_artifact(path: str, expected_hash: str, schema: str, what: str) -> dict:
    """Verify the detached hash, the sidecar, the schema, the address and the scope."""
    if not path or not os.path.isabs(path):
        raise Refused(f"{what}_path_not_absolute", path)
    want = (expected_hash or "").strip().lower()
    if len(want) != 64 or any(ch not in "0123456789abcdef" for ch in want):
        raise Refused(f"{what}_hash_malformed", expected_hash)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        with open(path + ".sha256", "r", encoding="utf-8") as fh:
            sidecar = fh.read().split()
    except OSError as exc:
        raise Refused(f"{what}_missing", f"{type(exc).__name__}: {exc}") from exc
    got = _sha256_hex(data)
    if got != want:
        raise Refused(f"{what}_hash_mismatch", {"expected": want, "actual": got})
    if sidecar[:2] != [want, os.path.basename(path)]:
        raise Refused(f"{what}_sidecar_mismatch", sidecar)
    try:
        payload = json.loads(data)
    except ValueError as err:
        raise Refused(f"{what}_corrupt", str(err)) from err
    if not isinstance(payload, dict) or payload.get("schema") != schema:
        raise Refused(f"{what}_wrong_schema", payload.get("schema") if isinstance(payload, dict) else None)
    if payload.get("content_address") != content_address(schema, payload):
        raise Refused(f"{what}_address_mismatch", payload.get("content_address"))
    if payload.get("keeper_id") != KEEPER_ID or payload.get("write") != {
        "table": "event_provider_anchors", "key": key_dict(CURRENT_KEY), "event_id": KEEPER_ID
    }:
        raise Refused(f"{what}_scope_mismatch", payload.get("write"))
    return payload


def tool_pin() -> dict:
    with open(os.path.abspath(__file__), "rb") as fh:
        tool_sha = _sha256_hex(fh.read())
    return {
        "tool": TOOL,
        "tool_file_sha256": tool_sha,
        "source_version": os.environ.get("SOURCE_VERSION") or os.environ.get("HEROKU_SLUG_COMMIT"),
    }


# --- SQL (exact ids and exact keys only) --------------------------------------

_KEEPER_COLS = ", ".join(FENCED_COLUMNS) + ", status"
_KEEPER = text(f"/* r10520:KEEPER */ SELECT id, {_KEEPER_COLS} FROM events WHERE id = :eid")
_KEEPER_LOCK = text(_KEEPER.text.replace("r10520:KEEPER", "r10520:KEEPER_LOCK") + " FOR UPDATE")
_SPORT = text("/* r10520:SPORT */ SELECT key FROM sports WHERE id = :sid")
_SPORT_LOCK = text(_SPORT.text.replace("r10520:SPORT", "r10520:SPORT_LOCK") + " FOR SHARE")
_ANCHOR_COLS = "id, event_id, source, source_id, id_kind, first_seen_at, claim_context"
_ANCHOR = text(
    f"/* r10520:ANCHOR */ SELECT {_ANCHOR_COLS} FROM event_provider_anchors "
    "WHERE source = :source AND source_id = :source_id AND id_kind = :id_kind"
)
_ANCHOR_LOCK = text(_ANCHOR.text.replace("r10520:ANCHOR", "r10520:ANCHOR_LOCK") + " FOR SHARE")
_ANCHOR_FOR_DELETE = text(_ANCHOR.text.replace("r10520:ANCHOR", "r10520:ANCHOR_DEL") + " FOR UPDATE")
_DELETE = text(
    "/* r10520:RESTORE */ DELETE FROM event_provider_anchors "
    "WHERE id = :aid AND event_id = :eid AND source = :source AND source_id = :source_id "
    "AND id_kind = :id_kind AND claim_context = CAST(:claim_context AS jsonb) RETURNING id"
)


async def _rows(session, stmt, params: dict) -> list[dict]:
    result = await session.execute(stmt, params)
    return [dict(r) for r in result.mappings().all()]


async def _one(session, stmt, params: dict) -> dict | None:
    rows = await _rows(session, stmt, params)
    if len(rows) > 1:
        raise Refused("exact_read_not_unique", {"rows": len(rows)})
    row = rows[0] if rows else None
    if row is not None and isinstance(row.get("claim_context"), str):
        row["claim_context"] = json.loads(row["claim_context"])
    return row


async def _read_anchor(session, key, *, stmt=_ANCHOR) -> dict | None:
    return await _one(session, stmt, key_dict(key))


async def _read_all(session, *, lock: bool) -> tuple:
    keeper = await _one(session, _KEEPER_LOCK if lock else _KEEPER, {"eid": KEEPER_ID})
    sport_key = None
    if keeper is not None and keeper.get("sport_id") is not None:
        sport = await _one(session, _SPORT_LOCK if lock else _SPORT, {"sid": keeper["sport_id"]})
        sport_key = sport["key"] if sport else None
    anchors = {}
    for name, key in ANCHOR_KEYS.items():
        # The current key is the one that may be ABSENT; there is nothing to
        # lock, and the unique index arbitrates any concurrent insert.
        locking = lock and name != "current"
        anchors[name] = await _read_anchor(session, key, stmt=_ANCHOR_LOCK if locking else _ANCHOR)
    return keeper, sport_key, anchors


# --- results ------------------------------------------------------------------

SessionFactory = Callable[[], Any]


def _result(mode: str, state: str, *, reason: str | None = None, detail: Any = None,
            written_rows: int = 0, deleted_rows: int = 0, **extra) -> dict:
    out = {"schema": RECEIPT_SCHEMA, "mode": mode, "state": state,
           "counts": {"keeper_id": KEEPER_ID, "anchor_rows_written": written_rows,
                      "anchor_rows_deleted": deleted_rows}}
    if reason is not None:
        out["reason"] = reason
    if detail is not None:
        out["detail"] = detail
    out.update(extra)
    return out


def _db_reason(exc: BaseException) -> str:
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if code is None and orig is not None:
        code = getattr(getattr(orig, "__cause__", None), "sqlstate", None)
    if code == "55P03":
        return "lock_timeout"
    if code == "57014":
        return "statement_timeout"
    return f"db_error:{type(exc).__name__}"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _set_timeouts(session, lock_ms: int, stmt_ms: int) -> None:
    await session.execute(text(f"SET LOCAL lock_timeout = '{int(lock_ms)}ms'"))
    await session.execute(text(f"SET LOCAL statement_timeout = '{int(stmt_ms)}ms'"))


# --- preflight ----------------------------------------------------------------

async def run_preflight(session_factory: SessionFactory, *, plan_out: str,
                        clock: Callable[[], str] = _utcnow) -> dict:
    """All reads in one REPEATABLE READ READ ONLY transaction; writes the plan."""
    try:
        _require_new_absolute(plan_out, "plan")
        async with session_factory() as session:
            try:
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                keeper, sport_key, anchors = await _read_all(session, lock=False)
            finally:
                await session.rollback()
        body = admit(keeper, sport_key, anchors)
    except Refused as exc:
        return _result("preflight", REFUSED, reason=exc.reason, detail=canon_safe(exc.detail))
    if body["state"] == NOT_NEEDED:
        return _result("preflight", NOT_NEEDED, reason="current_key_already_keepers",
                       anchors=body["anchors"])
    body.update({"twin_recorded_not_read": TWIN_ID, "evidence": EVIDENCE,
                 "pins": tool_pin(), "planned_at": clock()})
    try:
        written = write_artifact(plan_out, PLAN_SCHEMA, body, "plan")
    except Refused as exc:
        return _result("preflight", REFUSED, reason=exc.reason, detail=canon_safe(exc.detail))
    return _result("preflight", PLANNED, plan=written, proposed_insert=body["write"],
                   identity=body["identity"], anchors=body["anchors"])


# --- apply --------------------------------------------------------------------

async def _verify(session_factory, claim_context: dict) -> dict:
    """New transaction: the created row, the incoming owner, and Step 2's answer."""
    async with session_factory() as session:
        try:
            row = await _read_anchor(session, CURRENT_KEY)
            inc = await _read_anchor(session, INCOMING_KEY)
            resolves = await find_event_by_anchor(
                session, INCOMING_KEY, expected_sport_id=IDENTITY["sport_id"]
            )
        finally:
            await session.rollback()
    return {"row": row, "mismatch": created_row_matches(row, claim_context),
            "incoming": _owned(inc), "step2_resolves_incoming_to": resolves}


def _classify_after_ambiguous_commit(row: dict | None, claim_context: dict) -> str:
    if row is None:
        return NOT_APPLIED
    return APPLIED if not created_row_matches(row, claim_context) else COMMIT_UNKNOWN


async def run_apply(session_factory: SessionFactory, *, plan_path: str, plan_hash: str,
                    backup_out: str, lock_timeout_ms: int = LOCK_TIMEOUT_MS,
                    statement_timeout_ms: int = STATEMENT_TIMEOUT_MS,
                    clock: Callable[[], str] = _utcnow) -> dict:
    """Consume the reviewed plan; bank the backup; one ``record_anchor`` write."""
    try:
        plan = load_artifact(plan_path, plan_hash, PLAN_SCHEMA, "plan")
        if plan.get("state") != "CANDIDATE":
            raise Refused("plan_not_a_candidate", plan.get("state"))
        invocation_id = str(uuid.uuid4())
        claim_context = claim_context_for(invocation_id, plan["content_address"])
        backup_body = {
            "keeper_id": KEEPER_ID, "write": plan["write"],
            "pre_state": {"current_key_row": None, "anchors": plan["anchors"],
                          "identity": plan["identity"]},
            "invocation_id": invocation_id, "claim_context": claim_context,
            "plan": {"path": plan_path, "sha256": plan_hash.strip().lower(),
                     "content_address": plan["content_address"]},
            "pins": tool_pin(), "written_at": clock(),
        }
        backup = write_artifact(backup_out, BACKUP_SCHEMA, backup_body, "backup")
        load_artifact(backup_out, backup["sha256"], BACKUP_SCHEMA, "backup")
    except Refused as exc:
        return _result("apply", REFUSED, reason=exc.reason, detail=canon_safe(exc.detail))

    extra = {"plan": {"path": plan_path, "sha256": plan_hash.strip().lower()}, "backup": backup}
    committed = commit_attempted = False
    commit_error = ""
    try:
        async with session_factory() as session:
            staged = False
            try:
                await _set_timeouts(session, lock_timeout_ms, statement_timeout_ms)
                keeper, sport_key, anchors = await _read_all(session, lock=True)
                now = admit(keeper, sport_key, anchors)
                if now["state"] == NOT_NEEDED:
                    return _result("apply", NOT_NEEDED, reason="current_key_already_keepers",
                                   anchors=now["anchors"], **extra)
                drift = plan_drift(plan, now)
                if drift:
                    raise Refused("plan_drift:" + ",".join(drift),
                                  {f: {"plan": plan.get(f), "now": now.get(f)} for f in drift})
                outcome = await record_anchor(
                    session, event_id=KEEPER_ID, key=CURRENT_KEY, claim_context=claim_context
                )
                if outcome.outcome == CONFIRMED:
                    # Same owner, written by someone else since our read: no-op.
                    return _result("apply", NOT_NEEDED, reason="current_key_confirmed_at_write", **extra)
                if outcome.outcome != WROTE:
                    raise Refused(f"record_anchor_{outcome.outcome.lower()}",
                                  {"canonical_event_id": outcome.canonical_event_id})
                created = await _read_anchor(session, CURRENT_KEY)
                bad = created_row_matches(created, claim_context)
                if bad:
                    raise Refused("in_transaction_readback_mismatch", bad)
                inc = await _read_anchor(session, INCOMING_KEY)
                if _owned(inc) != plan["anchors"]["incoming"]:
                    raise Refused("incoming_anchor_moved_in_transaction", _owned(inc))
                staged = True
            finally:
                if not staged:  # any refusal, DB error or cancellation: nothing is kept
                    await session.rollback()
            commit_attempted = True
            try:
                await session.commit()
                committed = True
            except Exception as exc:  # outcome unknown: read, never re-apply
                commit_error = f"{type(exc).__name__}: {str(exc)[:160]}"
    except Refused as exc:
        result = _result("apply", REFUSED, reason=exc.reason, detail=canon_safe(exc.detail), **extra)
        result["receipt"] = _write_receipt(backup_out, "apply", result)
        return result
    except Exception as exc:
        if not commit_attempted:
            result = _result("apply", REFUSED, reason=_db_reason(exc),
                             detail=f"{type(exc).__name__}: {str(exc)[:160]}", **extra)
            result["receipt"] = _write_receipt(backup_out, "apply", result)
            return result
        if not committed:
            commit_error = commit_error or f"{type(exc).__name__}: {str(exc)[:160]}"

    try:
        check = await _verify(session_factory, claim_context)
    except Exception as exc:
        result = _result("apply", COMMIT_UNKNOWN, reason="post_commit_verify_unreadable",
                         detail=f"{type(exc).__name__}: {str(exc)[:160]}", **extra)
        result["receipt"] = _write_receipt(backup_out, "apply", result)
        return result
    if not committed:
        state = _classify_after_ambiguous_commit(check["row"], claim_context)
        result = _result("apply", state, reason="commit_ambiguous", detail=commit_error,
                         written_rows=1 if state == APPLIED else 0, **extra)
    elif check["mismatch"]:
        result = _result("apply", COMMIT_UNKNOWN, reason="post_commit_verify_mismatch",
                         detail=check["mismatch"], **extra)
    else:
        result = _result("apply", APPLIED, written_rows=1, created_row=canon(check["row"]),
                         incoming_after=check["incoming"],
                         step2_resolves_incoming_to=check["step2_resolves_incoming_to"], **extra)
    result["receipt"] = _write_receipt(backup_out, "apply", result)
    return result


def _write_receipt(base: str, suffix: str, result: dict) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = f"{base}.{suffix}-receipt.{stamp}.json"
    body = {"keeper_id": KEEPER_ID, "write": {"table": "event_provider_anchors",
            "key": key_dict(CURRENT_KEY), "event_id": KEEPER_ID}, "result": canon_safe(result)}
    try:
        return write_artifact(path, RECEIPT_SCHEMA, body, "receipt")
    except Refused as exc:
        return {"path": path, "error": exc.reason}


# --- restore ------------------------------------------------------------------

async def run_restore(session_factory: SessionFactory, *, backup_path: str, backup_hash: str,
                      lock_timeout_ms: int = LOCK_TIMEOUT_MS,
                      statement_timeout_ms: int = STATEMENT_TIMEOUT_MS) -> dict:
    """Compare-and-delete ONLY this invocation's unchanged created row."""
    try:
        backup = load_artifact(backup_path, backup_hash, BACKUP_SCHEMA, "backup")
        claim_context = backup["claim_context"]
        if claim_context != claim_context_for(backup["invocation_id"], backup["plan"]["content_address"]):
            raise Refused("backup_claim_context_incoherent")
    except Refused as exc:
        return _result("restore", REFUSED, reason=exc.reason, detail=canon_safe(exc.detail))
    extra = {"backup": {"path": backup_path, "sha256": backup_hash.strip().lower()}}
    commit_attempted = False
    try:
        async with session_factory() as session:
            staged = False
            try:
                await _set_timeouts(session, lock_timeout_ms, statement_timeout_ms)
                row = await _read_anchor(session, CURRENT_KEY, stmt=_ANCHOR_FOR_DELETE)
                if row is None:
                    result = _result("restore", NOT_APPLIED, reason="no_row_at_key", **extra)
                    result["receipt"] = _write_receipt(backup_path, "restore", result)
                    return result
                bad = created_row_matches(row, claim_context)
                if bad:
                    raise Refused("row_is_not_this_invocations_unchanged_write:" + ",".join(bad),
                                  {"id": row.get("id"), "event_id": row.get("event_id")})
                deleted = await _rows(session, _DELETE, {
                    "aid": row["id"], "eid": KEEPER_ID, **key_dict(CURRENT_KEY),
                    "claim_context": canonical_json(claim_context),
                })
                if [d["id"] for d in deleted] != [row["id"]]:
                    raise Refused("delete_fence_lost", {"deleted": [d["id"] for d in deleted]})
                staged = True
            finally:
                if not staged:
                    await session.rollback()
            commit_attempted = True
            await session.commit()
    except Refused as exc:
        result = _result("restore", REFUSED, reason=exc.reason, detail=canon_safe(exc.detail), **extra)
        result["receipt"] = _write_receipt(backup_path, "restore", result)
        return result
    except Exception as exc:
        if not commit_attempted:  # lock/statement timeout or any DB error: nothing deleted
            result = _result("restore", REFUSED, reason=_db_reason(exc),
                             detail=f"{type(exc).__name__}: {str(exc)[:160]}", **extra)
            result["receipt"] = _write_receipt(backup_path, "restore", result)
            return result
        # COMMIT's outcome is unknown: the exact-key read below decides.
    async with session_factory() as session:
        try:
            after = await _read_anchor(session, CURRENT_KEY)
        finally:
            await session.rollback()
    state = RESTORED if after is None else COMMIT_UNKNOWN
    result = _result("restore", state, deleted_rows=1 if after is None else 0,
                     deleted_row=canon(row), **extra)
    result["receipt"] = _write_receipt(backup_path, "restore", result)
    return result


def exit_code(result: dict) -> int:
    state = result.get("state")
    if state in (PLANNED, APPLIED, NOT_NEEDED, RESTORED):
        return EXIT_OK
    if state == NOT_APPLIED and result.get("mode") == "restore":
        return EXIT_OK
    if state == COMMIT_UNKNOWN:
        return EXIT_COMMIT_UNKNOWN
    return EXIT_REFUSED


# --- CLI ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Attended only. Exits: 0 ok, 1 refused, 2 usage, 3 commit unknown, 4 runtime error.",
    )
    ap.add_argument("--only", type=int, action="append", required=True,
                    help=f"must be exactly {KEEPER_ID}, once")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true", help="read-only; the default")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--restore", action="store_true")
    for name in ("--plan-out", "--plan", "--plan-hash", "--backup-out", "--backup", "--backup-hash"):
        ap.add_argument(name)
    return ap


_MODE_ARGS = {
    "preflight": ("plan_out",),
    "apply": ("plan", "plan_hash", "backup_out"),
    "restore": ("backup", "backup_hash"),
}


def parse(argv: list[str]) -> tuple[str, argparse.Namespace]:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.only != [KEEPER_ID]:
        ap.error(f"--only must be exactly {KEEPER_ID}, given once; got {args.only}")
    mode = "apply" if args.apply else "restore" if args.restore else "preflight"
    for name in ("plan_out", "plan", "plan_hash", "backup_out", "backup", "backup_hash"):
        wanted = name in _MODE_ARGS[mode]
        if wanted and not getattr(args, name):
            ap.error(f"--{mode} needs --{name.replace('_', '-')}")
        if not wanted and getattr(args, name):
            ap.error(f"--{name.replace('_', '-')} does not belong to --{mode}")
    return mode, args


def refuse_unless_target(env: dict) -> None:
    app = env.get("HEROKU_APP_NAME", "")
    if app not in PRODUCTION_APPS:
        raise Refused("target_app_refused", {"HEROKU_APP_NAME": app, "accepted": sorted(PRODUCTION_APPS)})


@asynccontextmanager
async def _engine_factory() -> AsyncIterator[SessionFactory]:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.services.database import DATABASE_URL, build_connect_args

    engine = create_async_engine(
        DATABASE_URL, poolclass=NullPool,
        connect_args=build_connect_args(
            DATABASE_URL, statement_timeout_ms=STATEMENT_TIMEOUT_MS, lock_timeout_ms=LOCK_TIMEOUT_MS,
        ),
    )
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


async def main(argv: list[str] | None = None, env: dict | None = None) -> int:
    mode, args = parse(sys.argv[1:] if argv is None else argv)
    try:
        refuse_unless_target(dict(os.environ) if env is None else env)
    except Refused as exc:
        print(json.dumps(_result(mode, REFUSED, reason=exc.reason, detail=exc.detail), indent=2))
        return EXIT_REFUSED
    try:
        async with _engine_factory() as factory:
            if mode == "preflight":
                out = await run_preflight(factory, plan_out=args.plan_out)
            elif mode == "apply":
                out = await run_apply(factory, plan_path=args.plan, plan_hash=args.plan_hash,
                                      backup_out=args.backup_out)
            else:
                out = await run_restore(factory, backup_path=args.backup, backup_hash=args.backup_hash)
    except Exception as exc:
        print(json.dumps(_result(mode, "RUNTIME_ERROR",
                                 detail=f"{type(exc).__name__}: {str(exc)[:200]}"), indent=2))
        return EXIT_RUNTIME
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return exit_code(out)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
