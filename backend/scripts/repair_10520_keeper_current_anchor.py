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
per-invocation id that is minted ON THE OPERATOR'S HOST, inside a backup the host
already holds before the database is touched.

Nothing else is written. ``events`` (keeper and twin), ``odds_snapshots``, the
incoming anchor 187393 and the official-fixture anchors are read, never changed.

ADMISSION (every gate fails closed; the same pure function serves every DB mode)
-------------------------------------------------------------------------------

* KEEPER: the row exists and its identity columns equal the retained evidence
  exactly: sport 1326 (key ``soccer_usa_mls`` — not in the retained reads, so a
  different key REFUSES rather than being guessed), teams 16/23, both names,
  ``external_id`` = the current Odds id, ``espn_id`` 761660,
  ``statpal_fixture_id`` 9163448, ``commence_time`` 2026-10-07T00:30Z. ``status`` is
  banked, not fenced — a game going live does not change which game it is.
* INCOMING: ``(odds_api, 0d9ff865…, game)`` exists, is row 187393 and is owned by
  the keeper. A market/container anchor or another provider's row is not it.
* OFFICIAL FIXTURE: ``(statpal, soccer:9163448, game)`` is row 295737, owned by
  the keeper; ``(espn, 761660, game)`` is absent or owned by the keeper.
* SURVIVOR (Authority's §5 item 1): the ordinary ``merge-duplicate-events`` drain
  would elect the twin exactly when the twin carries an ``external_id`` and
  ``odds_snapshots`` while the keeper has none. That state REFUSES and goes back to
  Root; ``has_snaps`` is read with the drain's own predicate and recorded.
* CURRENT: ``(odds_api, 1d13bd27…, game)`` absent -> CANDIDATE (the only state that
  writes); owned by the keeper -> NOT_NEEDED (idempotent no-op, exit 0); owned by
  any other row -> REFUSED. Never repointed.

TRANSPORT: THE EXISTING ATTENDED EXECUTOR, NOT DYNO FILES
--------------------------------------------------------

A one-off dyno's filesystem dies with the dyno, so nothing this tool needs for
recovery is ever kept only there. The channel is the one #9649 used
(``APPROVED-B1-20261001.sh``): an attended ``heroku run --exit-code --no-tty``
whose STDIN is a host file and whose STDOUT is captured to a no-clobber host
file. So:

* DATABASE modes (``--preflight``, ``--apply``, ``--restore``) run on the dyno,
  read their one input bundle from STDIN, write nothing to disk, and print JSON
  Lines to STDOUT — one canonical object per line, nothing else (logging and
  warnings are captured into the final record, because attached ``heroku run``
  merges dyno stderr into local stdout).
* HOST modes (``--stage-plan``, ``--stage-apply``, ``--stage-restore``) run on the
  operator's machine and REFUSE on a dyno (``DYNO`` set). They write the plan,
  backup and input bundles with exclusive create + fsync + a detached
  ``.sha256`` — retention on the host, where it is real.

Every hash is SHA256 over an artifact's canonical bytes
(``canonical_json(doc) + "\\n"``), which is exactly what the host file holds. A
DB mode recomputes it from STDIN and refuses unless it equals the hash on its
argv — so apply can only consume a plan the operator reviewed and a backup the
operator already holds.

PHASES (each phase boundary is a person; nothing chains across one)
------------------------------------------------------------------

1. ``--preflight`` (dyno, REPEATABLE READ READ ONLY) -> host ``preflight.jsonl``.
2. ``--stage-plan`` (host) -> ``plan.json`` + sha. Review boundary.
3. ``--stage-apply`` (host) -> ``backup.json`` (new invocation id) +
   ``apply-input.json``, each with sha. Retention check on the host.
4. ``--apply`` (dyno, STDIN = apply-input.json) -> host ``apply.jsonl``. One
   bounded transaction: keeper ``FOR UPDATE``, sport + existing anchors
   ``FOR SHARE``, admission, plan drift, ``record_anchor`` must answer ``WROTE``,
   exact in-transaction read-back. Then — BEFORE COMMIT — the ``created_row``
   record (anchor id, ``first_seen_at``, ``claim_context``) is written to STDOUT
   and flushed. Then COMMIT, then a new-transaction verify. An ambiguous COMMIT is
   classified from an exact-key read (absent NOT_APPLIED, this row APPLIED, else
   COMMIT_UNKNOWN); it never re-applies.
5. ``--stage-restore`` (host) -> ``restore-input.json`` = backup + the
   ``created_row`` record from ``apply.jsonl``.
6. ``--restore`` (dyno, STDIN = restore-input.json) deletes ONLY the row that
   record names: same anchor id, same ``first_seen_at``, same key, owner and
   ``claim_context``, repeated in the DELETE's own predicate. A recreated row with
   copied context, a changed timestamp, a pre-existing or changed row: REFUSED and
   left. Nothing at the key: NOT_APPLIED. A failed verify after the delete COMMIT
   is COMMIT_UNKNOWN with the full evidence, never a generic runtime error.
   Restoring re-opens #8278's refusal for the incoming id — run it only to undo.

APPLIED means the anchor write was confirmed. ``step2_resolves_incoming_to`` is
reported, not enforced; it is not a twin, natural-poll or reader claim.

WHAT THIS DOES NOT DO
---------------------

``events.external_id`` is unique and twin 15324922 holds ``0d9ff865…`` in its own
column, so registry Step 1 keeps resolving that id to the twin while the twin
exists. This anchor changes what happens AFTER the twin is gone: 187393 already
names the keeper, so the next claim misses Step 1, reaches Step 2 and is rescued
instead of minting a third row. Apply it before (or with) the twin's disposition.
Twin disposition, natural-poll rescue and reader acceptance are separate.

The operator packet (``artifacts/10520-keeper-anchor/APPLY-RESTORE-PACKET.md``)
carries the exact commands. Running any phase needs Root's separate admission.
Exit codes: 0 PLANNED / STAGED / APPLIED / NOT_NEEDED / RESTORED / restore
NOT_APPLIED; 1 REFUSED; 2 usage; 3 COMMIT_UNKNOWN; 4 runtime harness error.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import uuid
import warnings
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable


class _Captured(logging.Handler):
    """Every log record and warning goes here, never to stderr (attached
    ``heroku run`` merges dyno stderr into the host's stdout receipt)."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if len(self.lines) < 200:
            self.lines.append(f"{record.levelname} {record.name}: {record.getMessage()}"[:500])


CAPTURED = _Captured()
if __name__ == "__main__":  # before the app imports, which can warn at import time
    logging.basicConfig(handlers=[CAPTURED], level=logging.INFO, force=True)
    logging.captureWarnings(True)
    warnings.simplefilter("default")

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

PLAN_SCHEMA = "repair-10520-keeper-anchor-plan/v2"
BACKUP_SCHEMA = "repair-10520-keeper-anchor-backup/v2"
CREATED_ROW_SCHEMA = "repair-10520-keeper-anchor-created-row/v2"
APPLY_INPUT_SCHEMA = "repair-10520-keeper-anchor-apply-input/v2"
RESTORE_INPUT_SCHEMA = "repair-10520-keeper-anchor-restore-input/v2"
RECORD_SCHEMA = "repair-10520-keeper-anchor-record/v2"
ADDRESS_NAMESPACE = "bainluck:repair:10520:keeper-current-anchor"

#: The retained evidence this population is pinned to (artifacts, read-only).
EVIDENCE = {
    "keeper_and_twin_rows": "artifacts/shopper/pass-0237/q10520a.json + q10520b.json (2026-10-05 09:25Z)",
    "keeper_anchors": "artifacts/shopper/pass-0237/q10520c.json (2026-10-05 09:25Z)",
    "current_key_unowned": "artifacts/shopper/10520-second-anchor/q10520e (2026-10-05T10:21:21Z, "
                           "fingerprint 81ee2b22a8dd7b79)",
    "source_admission": "ROOT-OFFLINE-REPAIR-PREPARATION-BOUNDARY.md (20261005T082140Z-10520-59fb43)",
    "survivor_input": "artifacts/10520-keeper-anchor/AUTHORITY-SURVIVOR-IDENTITY-DISPOSITION.md §5",
}

KEEPER_ID = 14969919
TWIN_ID = 15324922  # read (presence, external_id, has_snaps) for the survivor gate; never written
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

PLANNED, STAGED, APPLIED, NOT_NEEDED = "PLANNED", "STAGED", "APPLIED", "NOT_NEEDED"
NOT_APPLIED, RESTORED, REFUSED, COMMIT_UNKNOWN = "NOT_APPLIED", "RESTORED", "REFUSED", "COMMIT_UNKNOWN"
EXIT_OK, EXIT_REFUSED, EXIT_USAGE, EXIT_COMMIT_UNKNOWN, EXIT_RUNTIME = 0, 1, 2, 3, 4


class Refused(RuntimeError):
    """A gate refused. Nothing was written."""

    def __init__(self, reason: str, detail: Any = None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


# --- pure: canonical form, hashes, seals -----------------------------------------

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


def artifact_bytes(doc: dict) -> bytes:
    """Exactly what a host artifact file holds, and what its hash is taken over."""
    return (canonical_json(doc) + "\n").encode("utf-8")


def artifact_sha256(doc: dict) -> str:
    return hashlib.sha256(artifact_bytes(doc)).hexdigest()


def content_address(schema: str, payload: dict) -> str:
    body = {k: v for k, v in payload.items() if k != "content_address"}
    line = digest_fields(ADDRESS_NAMESPACE, schema, canonical_json(body))
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def key_dict(key) -> dict:
    return {"source": key.source, "source_id": key.source_id, "id_kind": key.id_kind}


WRITE_SCOPE = {"table": "event_provider_anchors", "key": key_dict(CURRENT_KEY), "event_id": KEEPER_ID}


def seal(schema: str, body: dict) -> dict:
    doc = {"schema": schema, **canon(body)}
    doc["content_address"] = content_address(schema, doc)
    return doc


def check_sealed(doc: Any, schema: str, what: str) -> dict:
    """Schema, embedded address, and the one-row write scope."""
    if not isinstance(doc, dict) or doc.get("schema") != schema:
        raise Refused(f"{what}_wrong_schema", doc.get("schema") if isinstance(doc, dict) else None)
    if doc.get("content_address") != content_address(schema, doc):
        raise Refused(f"{what}_address_mismatch", doc.get("content_address"))
    if doc.get("keeper_id") != KEEPER_ID or doc.get("write") != WRITE_SCOPE:
        raise Refused(f"{what}_scope_mismatch", doc.get("write"))
    return doc


def require_hash(doc: dict, expected: str, what: str) -> str:
    want = (expected or "").strip().lower()
    if len(want) != 64 or any(ch not in "0123456789abcdef" for ch in want):
        raise Refused(f"{what}_hash_malformed", expected)
    got = artifact_sha256(doc)
    if got != want:
        raise Refused(f"{what}_hash_mismatch", {"expected": want, "actual": got})
    return want


def _owned(anchor: dict | None) -> dict | None:
    return None if anchor is None else {"id": anchor["id"], "event_id": anchor["event_id"]}


# --- pure: admission ----------------------------------------------------------------

def twin_would_survive(survivor: dict) -> bool:
    """Authority §5 item 1: the drain's election (``sports.py`` keep_a/keep_b) picks
    the twin only when the twin has an ``external_id`` AND snapshots and the keeper
    (whose ``external_id`` is fenced non-null) has no snapshots."""
    twin = survivor.get("twin") or {}
    return bool(
        twin.get("present") and twin.get("external_id") is not None
        and twin.get("has_snaps") and not survivor.get("keeper_has_snaps")
    )


def admit(keeper: dict | None, sport_key: Any, anchors: dict[str, dict | None],
          survivor: dict) -> dict:
    """Every gate, in order -> ``{"state": CANDIDATE|NOT_NEEDED, ...}``, or Refused."""
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

    if twin_would_survive(survivor):
        raise Refused("drain_would_elect_twin_return_to_root", canon_safe(survivor))

    cur = anchors.get("current")
    if cur is not None and cur["event_id"] != KEEPER_ID:
        raise Refused("current_key_owned_elsewhere", _owned(cur))

    return {
        "state": "CANDIDATE" if cur is None else NOT_NEEDED,
        "keeper_id": KEEPER_ID,
        "write": WRITE_SCOPE,
        "identity": observed,
        "sport_key": sport_key,
        "status_banked": keeper.get("status"),
        "anchors": {name: _owned(anchors.get(name)) for name in ANCHOR_KEYS},
        "survivor_banked": canon(survivor),
    }


#: What must still hold at apply that the plan observed. ``status_banked`` and
#: ``survivor_banked`` are recorded, not fenced: snapshots arrive continually, and
#: the survivor gate is re-judged on its own inside the apply transaction.
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


_ROW_FIELDS = ("id", "event_id", "source", "source_id", "id_kind", "first_seen_at", "claim_context")


def created_row_matches(row: dict | None, claim_context: dict) -> list[str]:
    """Fields of the row at CURRENT_KEY that are not this invocation's write."""
    if row is None:
        return ["row_missing"]
    want = {**key_dict(CURRENT_KEY), "event_id": KEEPER_ID, "claim_context": claim_context}
    return [f for f, v in want.items() if canon(row.get(f)) != v]


def row_is_the_created_row(row: dict | None, created: dict) -> list[str]:
    """Restore's identity: every field of the receipt's row, id and timestamp included."""
    if row is None:
        return ["row_missing"]
    return [f for f in _ROW_FIELDS if canon(row.get(f)) != created.get(f)]


# --- host-side artifacts ------------------------------------------------------------

_fsync = os.fsync  # module seam


def refuse_on_dyno(env: dict) -> None:
    """Host modes only: fsync on a one-off dyno is not retention."""
    if env.get("DYNO"):
        raise Refused("host_mode_refused_on_dyno", {"DYNO": env.get("DYNO")})


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


def write_host_artifact(path: str, doc: dict, what: str) -> dict:
    """Exclusive, fsynced, read-only canonical JSON + detached ``<path>.sha256``."""
    _require_new_absolute(path, what)
    data = artifact_bytes(doc)
    digest = hashlib.sha256(data).hexdigest()
    try:
        _write_once(path, data)
        _write_once(path + ".sha256", f"{digest}  {os.path.basename(path)}\n".encode())
    except OSError as exc:
        raise Refused(f"{what}_durability_failed", f"{type(exc).__name__}: {exc}") from exc
    with open(path, "rb") as fh:
        if hashlib.sha256(fh.read()).hexdigest() != digest:
            raise Refused(f"{what}_readback_mismatch", path)
    return {"path": path, "sha256": digest}


def read_host_artifact(path: str, expected_hash: str, schema: str, what: str) -> dict:
    """The file's bytes must BE the canonical form; hash, sidecar, seal and scope checked."""
    if not path or not os.path.isabs(path):
        raise Refused(f"{what}_path_not_absolute", path)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        with open(path + ".sha256", "r", encoding="utf-8") as fh:
            sidecar = fh.read().split()
        doc = json.loads(data)
    except (OSError, ValueError) as exc:
        raise Refused(f"{what}_unreadable", f"{type(exc).__name__}: {exc}") from exc
    if not isinstance(doc, dict) or artifact_bytes(doc) != data:
        raise Refused(f"{what}_not_canonical", path)
    want = require_hash(doc, expected_hash, what)
    if sidecar[:2] != [want, os.path.basename(path)]:
        raise Refused(f"{what}_sidecar_mismatch", sidecar)
    return check_sealed(doc, schema, what)


def read_jsonl(path: str, what: str) -> list[dict]:
    """A DB mode's captured STDOUT: every line must be one JSON object, nothing else."""
    try:
        with open(path, "rb") as fh:
            lines = fh.read().decode("utf-8").splitlines()
        records = [json.loads(line) for line in lines]
    except (OSError, ValueError) as exc:
        raise Refused(f"{what}_not_pure_json_lines", f"{type(exc).__name__}: {exc}") from exc
    if not records or not all(isinstance(r, dict) and r.get("schema") == RECORD_SCHEMA for r in records):
        raise Refused(f"{what}_not_this_tools_records", path)
    if records[-1].get("record") != "result":
        raise Refused(f"{what}_has_no_final_result", records[-1].get("record"))
    return records


def tool_pin() -> dict:
    with open(os.path.abspath(__file__), "rb") as fh:
        tool_sha = hashlib.sha256(fh.read()).hexdigest()
    return {
        "tool": TOOL,
        "tool_file_sha256": tool_sha,
        "source_version": os.environ.get("SOURCE_VERSION") or os.environ.get("HEROKU_SLUG_COMMIT"),
    }


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- records (the only thing a DB mode writes to STDOUT) ---------------------------

Emit = Callable[[dict], None]


def stdout_emit(record: dict) -> None:
    sys.stdout.write(canonical_json(record) + "\n")
    sys.stdout.flush()


def _record(kind: str, body: dict) -> dict:
    return {"schema": RECORD_SCHEMA, "record": kind, **body}


def _result(mode: str, state: str, *, reason: str | None = None, detail: Any = None,
            written_rows: int = 0, deleted_rows: int = 0, **extra) -> dict:
    out = _record("result", {"mode": mode, "state": state,
                             "counts": {"keeper_id": KEEPER_ID, "anchor_rows_written": written_rows,
                                        "anchor_rows_deleted": deleted_rows}})
    if reason is not None:
        out["reason"] = reason
    if detail is not None:
        out["detail"] = canon_safe(detail)
    out.update(canon_safe(extra))
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


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:160]}"


# --- SQL (exact ids and exact keys only) ------------------------------------------

_KEEPER_COLS = ", ".join(FENCED_COLUMNS) + ", status"
_KEEPER = text(f"/* r10520:KEEPER */ SELECT id, {_KEEPER_COLS} FROM events WHERE id = :eid")
_KEEPER_LOCK = text(_KEEPER.text.replace("r10520:KEEPER", "r10520:KEEPER_LOCK") + " FOR UPDATE")
_SPORT = text("/* r10520:SPORT */ SELECT key FROM sports WHERE id = :sid")
_SPORT_LOCK = text(_SPORT.text.replace("r10520:SPORT", "r10520:SPORT_LOCK") + " FOR SHARE")
_TWIN = text("/* r10520:TWIN */ SELECT id, external_id FROM events WHERE id = :tid")
#: The drain's own predicate (``sports.py`` merge_duplicate_events, has_snaps_a/b).
_HAS_SNAPS = text(
    "/* r10520:SNAPS */ SELECT EXISTS(SELECT 1 FROM odds_snapshots WHERE event_id = :eid LIMIT 1) AS has_snaps"
)
_ANCHOR_COLS = ", ".join(_ROW_FIELDS)
_ANCHOR = text(
    f"/* r10520:ANCHOR */ SELECT {_ANCHOR_COLS} FROM event_provider_anchors "
    "WHERE source = :source AND source_id = :source_id AND id_kind = :id_kind"
)
_ANCHOR_LOCK = text(_ANCHOR.text.replace("r10520:ANCHOR", "r10520:ANCHOR_LOCK") + " FOR SHARE")
_ANCHOR_FOR_DELETE = text(_ANCHOR.text.replace("r10520:ANCHOR", "r10520:ANCHOR_DEL") + " FOR UPDATE")
_DELETE = text(
    "/* r10520:RESTORE */ DELETE FROM event_provider_anchors "
    "WHERE id = :aid AND first_seen_at = CAST(:first_seen_at AS timestamptz) AND event_id = :eid "
    "AND source = :source AND source_id = :source_id AND id_kind = :id_kind "
    "AND claim_context = CAST(:claim_context AS jsonb) RETURNING id"
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
    # Never locked: the drain locks both rows FOR UPDATE and must not wait on us.
    twin = await _one(session, _TWIN, {"tid": TWIN_ID})
    survivor = {
        "keeper_has_snaps": bool((await _one(session, _HAS_SNAPS, {"eid": KEEPER_ID}))["has_snaps"]),
        "twin": {
            "id": TWIN_ID,
            "present": twin is not None,
            "external_id": twin.get("external_id") if twin else None,
            "has_snaps": bool((await _one(session, _HAS_SNAPS, {"eid": TWIN_ID}))["has_snaps"]),
        },
    }
    return keeper, sport_key, anchors, survivor


async def _set_timeouts(session, lock_ms: int, stmt_ms: int) -> None:
    await session.execute(text(f"SET LOCAL lock_timeout = '{int(lock_ms)}ms'"))
    await session.execute(text(f"SET LOCAL statement_timeout = '{int(stmt_ms)}ms'"))


SessionFactory = Callable[[], Any]


# --- phase 1: preflight (dyno) -----------------------------------------------------

async def run_preflight(session_factory: SessionFactory, *, emit: Emit = stdout_emit,
                        clock: Callable[[], str] = _utcnow) -> dict:
    """All reads in one REPEATABLE READ READ ONLY transaction; the plan rides STDOUT."""
    try:
        async with session_factory() as session:
            try:
                await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
                keeper, sport_key, anchors, survivor = await _read_all(session, lock=False)
            finally:
                await session.rollback()
        body = admit(keeper, sport_key, anchors, survivor)
    except Refused as exc:
        return _finish(emit, _result("preflight", REFUSED, reason=exc.reason, detail=exc.detail))
    if body["state"] == NOT_NEEDED:
        return _finish(emit, _result("preflight", NOT_NEEDED, reason="current_key_already_keepers",
                                     anchors=body["anchors"]))
    body.update({"evidence": EVIDENCE, "pins": tool_pin(), "planned_at": clock()})
    plan = seal(PLAN_SCHEMA, body)
    return _finish(emit, _result("preflight", PLANNED, plan=plan, plan_sha256=artifact_sha256(plan)))


def _finish(emit: Emit, result: dict) -> dict:
    if CAPTURED.lines:
        result["log"] = list(CAPTURED.lines)
    emit(result)
    return result


# --- phases 2, 3, 5: host staging --------------------------------------------------

def stage_plan(*, preflight_output: str, plan_out: str, env: dict) -> dict:
    """Extract the reviewed plan from the captured preflight STDOUT onto the host."""
    try:
        refuse_on_dyno(env)
        final = read_jsonl(preflight_output, "preflight_output")[-1]
        if final.get("mode") != "preflight" or final.get("state") != PLANNED:
            raise Refused("preflight_did_not_plan", {"state": final.get("state"), "reason": final.get("reason")})
        plan = check_sealed(final.get("plan"), PLAN_SCHEMA, "plan")
        require_hash(plan, final.get("plan_sha256"), "plan")
        written = write_host_artifact(plan_out, plan, "plan")
    except Refused as exc:
        return _result("stage-plan", REFUSED, reason=exc.reason, detail=exc.detail)
    return _result("stage-plan", STAGED, plan=written, review={
        "state": plan["state"], "identity": plan["identity"], "anchors": plan["anchors"],
        "survivor_banked": plan["survivor_banked"], "sport_key": plan["sport_key"]})


def stage_apply(*, plan_path: str, plan_hash: str, backup_out: str, bundle_out: str, env: dict,
                clock: Callable[[], str] = _utcnow) -> dict:
    """Mint the invocation on the host: backup + the apply STDIN bundle, both retained here."""
    try:
        refuse_on_dyno(env)
        plan = read_host_artifact(plan_path, plan_hash, PLAN_SCHEMA, "plan")
        if plan.get("state") != "CANDIDATE":
            raise Refused("plan_not_a_candidate", plan.get("state"))
        invocation_id = str(uuid.uuid4())
        backup = seal(BACKUP_SCHEMA, {
            "keeper_id": KEEPER_ID, "write": WRITE_SCOPE,
            "pre_state": {"current_key_row": None, "anchors": plan["anchors"], "identity": plan["identity"]},
            "invocation_id": invocation_id,
            "claim_context": claim_context_for(invocation_id, plan["content_address"]),
            "plan": {"sha256": artifact_sha256(plan), "content_address": plan["content_address"]},
            "pins": tool_pin(), "staged_at": clock(),
        })
        bundle = seal(APPLY_INPUT_SCHEMA, {"keeper_id": KEEPER_ID, "write": WRITE_SCOPE,
                                           "plan": plan, "backup": backup})
        backup_file = write_host_artifact(backup_out, backup, "backup")
        bundle_file = write_host_artifact(bundle_out, bundle, "apply_input")
    except Refused as exc:
        return _result("stage-apply", REFUSED, reason=exc.reason, detail=exc.detail)
    return _result("stage-apply", STAGED, invocation_id=invocation_id, backup=backup_file,
                   apply_input=bundle_file, apply_argv={
                       "--plan-hash": artifact_sha256(plan), "--backup-hash": backup_file["sha256"]})


def stage_restore(*, backup_path: str, backup_hash: str, apply_output: str, bundle_out: str,
                  env: dict) -> dict:
    """Bind the backup to the ``created_row`` record the apply printed before COMMIT."""
    try:
        refuse_on_dyno(env)
        backup = read_host_artifact(backup_path, backup_hash, BACKUP_SCHEMA, "backup")
        created = [r for r in read_jsonl(apply_output, "apply_output") if r.get("record") == "created_row"]
        if len(created) != 1:
            raise Refused("apply_output_created_row_count", {"count": len(created)})
        receipt = created_row_receipt_binds(created[0]["receipt"], backup, backup_hash)
        bundle = seal(RESTORE_INPUT_SCHEMA, {"keeper_id": KEEPER_ID, "write": WRITE_SCOPE,
                                             "backup": backup, "created_row_receipt": receipt})
        bundle_file = write_host_artifact(bundle_out, bundle, "restore_input")
    except Refused as exc:
        return _result("stage-restore", REFUSED, reason=exc.reason, detail=exc.detail)
    return _result("stage-restore", STAGED, restore_input=bundle_file,
                   created_row=receipt["created_row"], restore_argv={
                       "--backup-hash": artifact_sha256(backup),
                       "--receipt-hash": artifact_sha256(receipt)})


def created_row_receipt_binds(receipt: Any, backup: dict, backup_hash: str) -> dict:
    receipt = check_sealed(receipt, CREATED_ROW_SCHEMA, "created_row_receipt")
    if receipt.get("invocation_id") != backup["invocation_id"] or \
            receipt.get("backup_sha256") != (backup_hash or "").strip().lower():
        raise Refused("created_row_receipt_not_this_backups", {
            "receipt_invocation": receipt.get("invocation_id"), "backup_invocation": backup["invocation_id"]})
    row = receipt.get("created_row") or {}
    if created_row_matches(row, backup["claim_context"]) or not isinstance(row.get("id"), int) \
            or not isinstance(row.get("first_seen_at"), str):
        raise Refused("created_row_receipt_incoherent", row)
    return receipt


# --- phase 4: apply (dyno) ---------------------------------------------------------

def _parse_bundle(raw: bytes, schema: str) -> dict:
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise Refused("stdin_not_json", _err(exc)) from exc
    if not isinstance(doc, dict) or artifact_bytes(doc) != raw:
        raise Refused("stdin_not_the_canonical_host_file")
    return check_sealed(doc, schema, "stdin_bundle")


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


async def run_apply(session_factory: SessionFactory, *, stdin: bytes, plan_hash: str,
                    backup_hash: str, emit: Emit = stdout_emit,
                    lock_timeout_ms: int = LOCK_TIMEOUT_MS,
                    statement_timeout_ms: int = STATEMENT_TIMEOUT_MS) -> dict:
    """Consume the host's apply bundle; one ``record_anchor`` write; receipt before COMMIT."""
    try:
        bundle = _parse_bundle(stdin, APPLY_INPUT_SCHEMA)
        plan = check_sealed(bundle.get("plan"), PLAN_SCHEMA, "plan")
        backup = check_sealed(bundle.get("backup"), BACKUP_SCHEMA, "backup")
        plan_hash = require_hash(plan, plan_hash, "plan")
        backup_hash = require_hash(backup, backup_hash, "backup")
        if plan.get("state") != "CANDIDATE":
            raise Refused("plan_not_a_candidate", plan.get("state"))
        if backup["plan"] != {"sha256": plan_hash, "content_address": plan["content_address"]}:
            raise Refused("backup_not_this_plans", backup["plan"])
        claim_context = backup["claim_context"]
        if claim_context != claim_context_for(backup["invocation_id"], plan["content_address"]):
            raise Refused("backup_claim_context_incoherent")
    except Refused as exc:
        return _finish(emit, _result("apply", REFUSED, reason=exc.reason, detail=exc.detail))

    extra = {"plan_sha256": plan_hash, "backup_sha256": backup_hash,
             "invocation_id": backup["invocation_id"]}
    receipt = None
    committed = commit_attempted = False
    commit_error = ""
    try:
        async with session_factory() as session:
            staged = False
            try:
                await _set_timeouts(session, lock_timeout_ms, statement_timeout_ms)
                keeper, sport_key, anchors, survivor = await _read_all(session, lock=True)
                now = admit(keeper, sport_key, anchors, survivor)
                if now["state"] == NOT_NEEDED:
                    return _finish(emit, _result("apply", NOT_NEEDED, reason="current_key_already_keepers",
                                                 anchors=now["anchors"], **extra))
                drift = plan_drift(plan, now)
                if drift:
                    raise Refused("plan_drift:" + ",".join(drift),
                                  {f: {"plan": plan.get(f), "now": now.get(f)} for f in drift})
                outcome = await record_anchor(
                    session, event_id=KEEPER_ID, key=CURRENT_KEY, claim_context=claim_context
                )
                if outcome.outcome == CONFIRMED:
                    # Same owner, written by someone else since our read: no-op.
                    return _finish(emit, _result("apply", NOT_NEEDED,
                                                 reason="current_key_confirmed_at_write", **extra))
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
                receipt = seal(CREATED_ROW_SCHEMA, {
                    "keeper_id": KEEPER_ID, "write": WRITE_SCOPE,
                    "invocation_id": backup["invocation_id"], "backup_sha256": backup_hash,
                    "plan_sha256": plan_hash,
                    "created_row": {f: created[f] for f in _ROW_FIELDS},
                    "note": "emitted BEFORE COMMIT; restore requires this exact row",
                })
                # The restore identity reaches the host before the row can exist
                # for anyone else. If the dyno dies after COMMIT, this line is the
                # record of what to undo.
                emit(_record("created_row", {"receipt": receipt, "receipt_sha256": artifact_sha256(receipt)}))
                staged = True
            finally:
                if not staged:  # any refusal, DB error or cancellation: nothing is kept
                    await session.rollback()
            commit_attempted = True
            try:
                await session.commit()
                committed = True
            except Exception as exc:  # outcome unknown: read, never re-apply
                commit_error = _err(exc)
    except Refused as exc:
        return _finish(emit, _result("apply", REFUSED, reason=exc.reason, detail=exc.detail, **extra))
    except Exception as exc:
        if not commit_attempted:
            return _finish(emit, _result("apply", REFUSED, reason=_db_reason(exc), detail=_err(exc), **extra))
        if not committed:
            commit_error = commit_error or _err(exc)

    extra["created_row_receipt_sha256"] = artifact_sha256(receipt)
    try:
        check = await _verify(session_factory, claim_context)
    except Exception as exc:
        return _finish(emit, _result("apply", COMMIT_UNKNOWN, reason="post_commit_verify_unreadable",
                                     detail=_err(exc), **extra))
    if not committed:
        row = check["row"]
        if row is None:
            state = NOT_APPLIED
        elif not row_is_the_created_row(row, receipt["created_row"]):
            state = APPLIED
        else:
            state = COMMIT_UNKNOWN
        return _finish(emit, _result("apply", state, reason="commit_ambiguous", detail=commit_error,
                                     written_rows=1 if state == APPLIED else 0, **extra))
    if check["mismatch"] or row_is_the_created_row(check["row"], receipt["created_row"]):
        return _finish(emit, _result("apply", COMMIT_UNKNOWN, reason="post_commit_verify_mismatch",
                                     detail=check["mismatch"], **extra))
    return _finish(emit, _result("apply", APPLIED, written_rows=1, created_row=check["row"],
                                 incoming_after=check["incoming"],
                                 step2_resolves_incoming_to=check["step2_resolves_incoming_to"], **extra))


# --- phase 6: restore (dyno) -------------------------------------------------------

async def _read_after_restore(session_factory) -> dict | None:
    async with session_factory() as session:
        try:
            return await _read_anchor(session, CURRENT_KEY)
        finally:
            await session.rollback()


async def run_restore(session_factory: SessionFactory, *, stdin: bytes, backup_hash: str,
                      receipt_hash: str, emit: Emit = stdout_emit,
                      lock_timeout_ms: int = LOCK_TIMEOUT_MS,
                      statement_timeout_ms: int = STATEMENT_TIMEOUT_MS) -> dict:
    """Compare-and-delete ONLY the exact row the apply's pre-COMMIT receipt names."""
    try:
        bundle = _parse_bundle(stdin, RESTORE_INPUT_SCHEMA)
        backup = check_sealed(bundle.get("backup"), BACKUP_SCHEMA, "backup")
        backup_hash = require_hash(backup, backup_hash, "backup")
        receipt = created_row_receipt_binds(bundle.get("created_row_receipt"), backup, backup_hash)
        receipt_hash = require_hash(receipt, receipt_hash, "created_row_receipt")
    except Refused as exc:
        return _finish(emit, _result("restore", REFUSED, reason=exc.reason, detail=exc.detail))
    created = receipt["created_row"]
    extra = {"backup_sha256": backup_hash, "created_row_receipt_sha256": receipt_hash,
             "invocation_id": backup["invocation_id"], "key": key_dict(CURRENT_KEY),
             "created_row": created}
    commit_attempted = committed = False
    commit_error = ""
    try:
        async with session_factory() as session:
            staged = False
            try:
                await _set_timeouts(session, lock_timeout_ms, statement_timeout_ms)
                row = await _read_anchor(session, CURRENT_KEY, stmt=_ANCHOR_FOR_DELETE)
                if row is None:
                    return _finish(emit, _result("restore", NOT_APPLIED, reason="no_row_at_key", **extra))
                bad = row_is_the_created_row(row, created)
                if bad:
                    raise Refused("row_is_not_the_created_row:" + ",".join(bad),
                                  {"now": {f: row.get(f) for f in ("id", "event_id", "first_seen_at")}})
                deleted = await _rows(session, _DELETE, {
                    "aid": created["id"], "first_seen_at": datetime.fromisoformat(created["first_seen_at"]),
                    "eid": KEEPER_ID, **key_dict(CURRENT_KEY),
                    "claim_context": canonical_json(created["claim_context"]),
                })
                if [d["id"] for d in deleted] != [created["id"]]:
                    raise Refused("delete_fence_lost", {"deleted": [d["id"] for d in deleted]})
                staged = True
            finally:
                if not staged:
                    await session.rollback()
            commit_attempted = True
            try:
                await session.commit()
                committed = True
            except Exception as exc:
                commit_error = _err(exc)
    except Refused as exc:
        return _finish(emit, _result("restore", REFUSED, reason=exc.reason, detail=exc.detail, **extra))
    except Exception as exc:
        if not commit_attempted:  # lock/statement timeout or any DB error: nothing deleted
            return _finish(emit, _result("restore", REFUSED, reason=_db_reason(exc), detail=_err(exc), **extra))
        commit_error = commit_error or _err(exc)
    try:
        after = await _read_after_restore(session_factory)
    except Exception as exc:  # the delete may have committed: say so, never retry blindly
        return _finish(emit, _result("restore", COMMIT_UNKNOWN, reason="post_commit_verify_unreadable",
                                     detail={"verify": _err(exc), "commit": commit_error or None,
                                             "commit_acknowledged": committed}, **extra))
    if after is None:
        return _finish(emit, _result("restore", RESTORED, deleted_rows=1,
                                     reason=None if committed else "commit_ambiguous_row_gone", **extra))
    if not committed and not row_is_the_created_row(after, created):
        return _finish(emit, _result("restore", NOT_APPLIED, reason="commit_failed_row_still_present",
                                     detail=commit_error, **extra))
    return _finish(emit, _result("restore", COMMIT_UNKNOWN, reason="post_commit_row_present",
                                 detail={"now": {f: after.get(f) for f in ("id", "event_id", "first_seen_at")}},
                                 **extra))


def exit_code(result: dict) -> int:
    state = result.get("state")
    if state in (PLANNED, STAGED, APPLIED, NOT_NEEDED, RESTORED):
        return EXIT_OK
    if state == NOT_APPLIED and result.get("mode") == "restore" and result.get("reason") == "no_row_at_key":
        return EXIT_OK
    if state == COMMIT_UNKNOWN:
        return EXIT_COMMIT_UNKNOWN
    if state == "USAGE":
        return EXIT_USAGE
    return EXIT_REFUSED


# --- CLI ----------------------------------------------------------------------

class Usage(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # never print to stderr
        raise Usage(message)


DB_MODES = ("preflight", "apply", "restore")
HOST_MODES = ("stage-plan", "stage-apply", "stage-restore")
_MODE_ARGS = {
    "preflight": (),
    "stage-plan": ("preflight_output", "plan_out"),
    "stage-apply": ("plan", "plan_hash", "backup_out", "bundle_out"),
    "apply": ("plan_hash", "backup_hash"),
    "stage-restore": ("backup", "backup_hash", "apply_output", "bundle_out"),
    "restore": ("backup_hash", "receipt_hash"),
}
_ALL_ARGS = ("preflight_output", "plan_out", "plan", "plan_hash", "backup_out", "bundle_out",
             "backup", "backup_hash", "apply_output", "receipt_hash")


def build_parser() -> argparse.ArgumentParser:
    ap = _Parser(description=__doc__.splitlines()[0],
                 epilog="Exits: 0 ok, 1 refused, 2 usage, 3 commit unknown, 4 runtime error.")
    ap.add_argument("--only", type=int, action="append")
    ap.add_argument("--mode", choices=DB_MODES + HOST_MODES)
    for name in _ALL_ARGS:
        ap.add_argument("--" + name.replace("_", "-"))
    return ap


def parse(argv: list[str]) -> tuple[str, argparse.Namespace]:
    args = build_parser().parse_args(argv)
    if args.only != [KEEPER_ID]:
        raise Usage(f"--only must be exactly {KEEPER_ID}, given once; got {args.only}")
    if args.mode is None:
        raise Usage("--mode is required: " + ", ".join(DB_MODES + HOST_MODES))
    for name in _ALL_ARGS:
        wanted = name in _MODE_ARGS[args.mode]
        if wanted and not getattr(args, name):
            raise Usage(f"--mode {args.mode} needs --{name.replace('_', '-')}")
        if not wanted and getattr(args, name):
            raise Usage(f"--{name.replace('_', '-')} does not belong to --mode {args.mode}")
    return args.mode, args


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


def _read_stdin() -> bytes:
    stream = getattr(sys.stdin, "buffer", None)
    return stream.read() if stream is not None else sys.stdin.read().encode("utf-8")


async def main(argv: list[str] | None = None, env: dict | None = None,
               stdin: Callable[[], bytes] = _read_stdin, emit: Emit = stdout_emit) -> int:
    env = dict(os.environ) if env is None else env
    try:
        mode, args = parse(sys.argv[1:] if argv is None else argv)
    except Usage as exc:
        emit(_result("usage", "USAGE", reason=str(exc)))
        return EXIT_USAGE
    if mode in HOST_MODES:
        if mode == "stage-plan":
            out = stage_plan(preflight_output=args.preflight_output, plan_out=args.plan_out, env=env)
        elif mode == "stage-apply":
            out = stage_apply(plan_path=args.plan, plan_hash=args.plan_hash, backup_out=args.backup_out,
                              bundle_out=args.bundle_out, env=env)
        else:
            out = stage_restore(backup_path=args.backup, backup_hash=args.backup_hash,
                                apply_output=args.apply_output, bundle_out=args.bundle_out, env=env)
        emit(out)
        return exit_code(out)
    try:
        refuse_unless_target(env)
    except Refused as exc:
        out = _result(mode, REFUSED, reason=exc.reason, detail=exc.detail)
        emit(out)
        return exit_code(out)
    try:
        raw = stdin() if mode != "preflight" else b""
        async with _engine_factory() as factory:
            if mode == "preflight":
                out = await run_preflight(factory, emit=emit)
            elif mode == "apply":
                out = await run_apply(factory, stdin=raw, plan_hash=args.plan_hash,
                                      backup_hash=args.backup_hash, emit=emit)
            else:
                out = await run_restore(factory, stdin=raw, backup_hash=args.backup_hash,
                                        receipt_hash=args.receipt_hash, emit=emit)
    except Exception as exc:
        out = _result(mode, "RUNTIME_ERROR", detail=_err(exc))
        emit(out)
        return EXIT_RUNTIME
    return exit_code(out)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
