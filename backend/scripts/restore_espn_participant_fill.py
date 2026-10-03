"""Undo one #10305 D2 participant fill, byte-for-byte, from the receipt it wrote.

    python3 scripts/restore_espn_participant_fill.py --event-id N                 # dry run
    python3 scripts/restore_espn_participant_fill.py --event-id N --apply \\
        --retirement-proof PATH

WHAT IT RESTORES. Every column the fill wrote returns to its exact prior bytes —
both names, both FKs (NULL) and both normalized values — read from the receipt
inside the fill tag, never defaulted. ``event_tags`` keeps the CURRENT tags with
the one fill element swapped, at its index, for a
``provenance:espn-participant-fill-restored:`` marker that carries the original
receipt verbatim. Anything the fill did not write is left alone, and any later
write to a column the fill did write (a #9482 respelling, a rebind) is drift:
the tool refuses rather than claim it.

THE POLICY IS DEPLOY-THE-REFUSAL-THEN-RESTORE (plan r3/r4 §4.3).

1. A lane1 PR adds the row's id to ``RESTORED_FILL_EVENT_IDS``.
2. That PR goes live on ``bainluck`` — where the scheduled pass runs
   (``sync_espn_live_events``, queue ``realtime``).
   2b. The attended restore packet captures a RETIREMENT/CARRYING PROOF for
   ``bainluck`` AND ``bainluck-heavy``: every fill-capable process instance that
   does not carry the id has EXITED before this tool's lock, and every one still
   up carries it. A release does not satisfy this by being old.
3. ``--dry-run``, then ``--apply --retirement-proof PATH`` under a separately
   attended apply admission, which checks the proof against the raw captures.
4. After-check: the next scheduled pass counts ``refused_restore_denylisted``.

This tool checks the proof's STRUCTURE, BINDING, TIMING AND CLOSURE ON ITS FACE.
Whether the proof is authentic — that it matches the raw platform captures, that
the instance list is complete, that ``carries_id`` for a release other than this
one comes from that release's effective code — is the attended admission's job.

Every refusal prints its reason and exits non-zero; nothing is defaulted. The
dry run (the default) runs every refusal in a READ ONLY transaction, prints
each one that would fire, and still prints the per-column before -> after.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.utils.espn_participant_fill import (  # noqa: E402
    FILL_TAG_PREFIX,
    RESTORED_FILL_EVENT_IDS,
    RESTORED_TAG_PREFIX,
    FillReceipt,
    ReceiptInvalid,
    parse_fill_tag,
)

#: The app the scheduled pass runs on. Restore runs from the same slug.
RESTORE_APP = "bainluck"
#: Both apps run the same Procfile, so both are in every proof.
PROOF_APPS = ("bainluck", "bainluck-heavy")
#: The process types that consume queue ``realtime`` (backend/Procfile; pinned
#: by G-PROCFILE). One-off ``run`` dynos are admitted in a proof as well.
FILL_CAPABLE_PROCESS_TYPES = frozenset({"worker-realtime"})

#: SUPPLEMENTARY ONLY. Release age proves nothing about retirement (the release
#: phase sits between creation and rollover, unbounded); it stays because it is
#: cheap and fails closed.
MIN_RELEASE_AGE = timedelta(seconds=120)
MIN_PROOF_WINDOW = timedelta(seconds=300)
MAX_PROOF_AGE = timedelta(seconds=900)
#: A ``sigterm`` exit is the instance's own SIGTERM line plus this kill bound.
SIGTERM_KILL_BOUND = timedelta(seconds=30)
#: Clock-skew margin between the platform's log clock and the database's.
CLOCK_SKEW_MARGIN = timedelta(seconds=10)

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_ONE_OFF_TYPE_RE = re.compile(r"^run(\.\d+)?$")
_NATIVE_RELEASE_RE = re.compile(r"v([1-9][0-9]*)")

_TOP_KEYS = {"event_id", "denylist_commit", "apps"}
_APP_KEYS = {
    "app", "window_start", "captured_at", "release_version", "release_commit",
    "formation", "instances",
}
_INSTANCE_KEYS = {
    "dyno", "type", "release_version", "release_commit", "carries_id",
    "state_at_capture", "exited_at", "exit_evidence", "evidence_line",
}

ROW_SQL = """
SELECT id, espn_id, status, home_team_name, away_team_name, home_team_id, away_team_id,
       home_team_normalized, away_team_normalized, home_team_alt_names, away_team_alt_names,
       event_tags
FROM events WHERE id = :eid
"""

RESTORE_SQL = """
UPDATE events SET home_team_name = :prior_home_name, away_team_name = :prior_away_name,
  home_team_id = NULL, away_team_id = NULL,
  home_team_normalized = CAST(:prior_home_norm AS varchar),
  away_team_normalized = CAST(:prior_away_norm AS varchar),
  event_tags = CAST(:new_tags AS jsonb)
WHERE id = :eid AND espn_id = :espn_id AND status = 'scheduled'
  AND home_team_name = :after_home_name AND away_team_name = :after_away_name
  AND home_team_id = :after_home_tid AND away_team_id = :after_away_tid
  AND home_team_normalized IS NULL AND away_team_normalized IS NULL
  AND COALESCE(home_team_alt_names, '[]'::jsonb) = '[]'::jsonb
  AND COALESCE(away_team_alt_names, '[]'::jsonb) = '[]'::jsonb
  AND event_tags = CAST(:locked_tags AS jsonb)
RETURNING id, home_team_name, away_team_name, home_team_id, away_team_id,
          home_team_normalized, away_team_normalized, event_tags
"""


# ── Retirement / carrying proof ──────────────────────────────────────────────


class ProofRefusal(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _invalid(reason: str) -> ProofRefusal:
    return ProofRefusal(f"retirement_proof_invalid:{reason}")


@dataclass(frozen=True)
class ProofInstance:
    dyno: str
    type: str
    release_version: int
    release_commit: str
    carries_id: bool
    state_at_capture: str
    exited_at: Optional[datetime]
    exit_evidence: Optional[str]
    evidence_line: Optional[str]


@dataclass(frozen=True)
class ProofApp:
    app: str
    window_start: datetime
    captured_at: datetime
    release_version: int
    release_commit: str
    formation_worker_realtime: int
    instances: tuple[ProofInstance, ...]


@dataclass(frozen=True)
class RetirementProof:
    event_id: int
    denylist_commit: str
    apps: Mapping[str, ProofApp]


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _ts(value, reason: str) -> datetime:
    if not isinstance(value, str) or not _TS_RE.match(value):
        raise _invalid(reason)
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise _invalid(reason)


def _commit(value, reason: str) -> str:
    if not isinstance(value, str) or not _COMMIT_RE.match(value):
        raise _invalid(reason)
    return value


def _parse_instance(raw) -> ProofInstance:
    if not isinstance(raw, dict) or set(raw) != _INSTANCE_KEYS:
        raise _invalid("instance_keys")
    if not isinstance(raw["dyno"], str) or not raw["dyno"]:
        raise _invalid("dyno")
    if not isinstance(raw["type"], str) or not raw["type"]:
        raise _invalid("type")
    if not _is_int(raw["release_version"]):
        raise _invalid("release_version")
    commit = _commit(raw["release_commit"], "release_commit")
    if not isinstance(raw["carries_id"], bool):
        raise _invalid("carries_id")
    state = raw["state_at_capture"]
    if state not in ("up", "exited"):
        raise _invalid("state_at_capture")
    exit_fields = (raw["exited_at"], raw["exit_evidence"], raw["evidence_line"])
    if state == "exited":
        if any(v is None for v in exit_fields):
            raise _invalid("exit_fields")
        exited_at = _ts(raw["exited_at"], "exited_at")
        if raw["exit_evidence"] not in ("exit", "sigterm"):
            raise _invalid("exit_evidence")
        if not isinstance(raw["evidence_line"], str) or not raw["evidence_line"]:
            raise _invalid("evidence_line")
    else:
        if any(v is not None for v in exit_fields):
            raise _invalid("exit_fields")
        exited_at = None
    if raw["type"] not in FILL_CAPABLE_PROCESS_TYPES and not _ONE_OFF_TYPE_RE.match(raw["type"]):
        raise _invalid("out_of_scope_instance")
    return ProofInstance(
        dyno=raw["dyno"],
        type=raw["type"],
        release_version=raw["release_version"],
        release_commit=commit,
        carries_id=raw["carries_id"],
        state_at_capture=state,
        exited_at=exited_at,
        exit_evidence=raw["exit_evidence"],
        evidence_line=raw["evidence_line"],
    )


def _parse_app(raw) -> ProofApp:
    if not isinstance(raw, dict) or set(raw) != _APP_KEYS:
        raise _invalid("app_keys")
    if not isinstance(raw["app"], str):
        raise _invalid("apps")
    formation = raw["formation"]
    if (
        not isinstance(formation, dict)
        or set(formation) != {"worker-realtime"}
        or not _is_int(formation["worker-realtime"])
        or formation["worker-realtime"] < 0
    ):
        raise _invalid("formation")
    if not _is_int(raw["release_version"]):
        raise _invalid("release_version")
    if not isinstance(raw["instances"], list):
        raise _invalid("instances")
    return ProofApp(
        app=raw["app"],
        window_start=_ts(raw["window_start"], "window_start"),
        captured_at=_ts(raw["captured_at"], "captured_at"),
        release_version=raw["release_version"],
        release_commit=_commit(raw["release_commit"], "release_commit"),
        formation_worker_realtime=formation["worker-realtime"],
        instances=tuple(_parse_instance(i) for i in raw["instances"]),
    )


def parse_retirement_proof(raw, *, event_id: int) -> RetirementProof:
    """Strict, default-free parse. Raises :class:`ProofRefusal`."""
    if not isinstance(raw, dict) or set(raw) != _TOP_KEYS:
        raise _invalid("top_keys")
    if not _is_int(raw["event_id"]):
        raise _invalid("event_id")
    if raw["event_id"] != event_id:
        raise _invalid("event_id_mismatch")
    denylist_commit = _commit(raw["denylist_commit"], "denylist_commit")
    if not isinstance(raw["apps"], list):
        raise _invalid("apps")
    apps = [_parse_app(a) for a in raw["apps"]]
    names = [a.app for a in apps]
    if sorted(names) != sorted(PROOF_APPS):
        raise _invalid("apps")
    return RetirementProof(
        event_id=raw["event_id"],
        denylist_commit=denylist_commit,
        apps={a.app: a for a in apps},
    )


def effective_exit(instance: ProofInstance) -> datetime:
    """When the instance is known gone: its exit line, or its SIGTERM + kill bound."""
    if instance.exit_evidence == "sigterm":
        return instance.exited_at + SIGTERM_KILL_BOUND
    return instance.exited_at


def native_release_number(value) -> Optional[int]:
    """The release number in Heroku's own ``HEROKU_RELEASE_VERSION`` (``v5500``).

    Exactly ``v`` and a positive ASCII integer; anything else — absent, bare
    digits, signs, padding, non-ASCII digits — is unknown, never a number.
    """
    if not isinstance(value, str):
        return None
    m = _NATIVE_RELEASE_RE.fullmatch(value)
    return int(m.group(1)) if m else None


def judge_retirement_proof(
    proof: RetirementProof,
    *,
    release_version: Optional[str],
    slug_commit: Optional[str],
    lock_now: datetime,
) -> tuple[list[str], Optional[datetime]]:
    """Every refusal the proof earns on its face, and the latest effective exit."""
    refusals: list[str] = []
    main = proof.apps[RESTORE_APP]

    own_version = native_release_number(release_version)
    if own_version is None or not slug_commit:
        refusals.append("release_metadata_unknown")
    elif own_version != main.release_version or slug_commit != main.release_commit:
        refusals.append("retirement_proof_stale_release")

    stale = False
    for name in PROOF_APPS:
        app = proof.apps[name]
        if app.captured_at - app.window_start < MIN_PROOF_WINDOW:
            refusals.append(f"retirement_window_short:{name}")
        if app.captured_at > lock_now or lock_now - app.captured_at > MAX_PROOF_AGE:
            stale = True
        if any(i.exited_at is not None and app.captured_at < i.exited_at for i in app.instances):
            stale = True
    if stale:
        refusals.append("retirement_proof_stale")

    latest: Optional[datetime] = None
    for name in PROOF_APPS:
        app = proof.apps[name]
        up_realtime = [
            i for i in app.instances
            if i.type == "worker-realtime" and i.state_at_capture == "up"
        ]
        if len(up_realtime) != app.formation_worker_realtime or (
            name == RESTORE_APP and app.formation_worker_realtime == 0
        ):
            refusals.append(f"replacement_absent:{name}:worker-realtime")
        for inst in app.instances:
            if inst.state_at_capture == "up":
                if not inst.carries_id:
                    refusals.append(f"replacement_not_carrying:{inst.dyno}")
                elif name == RESTORE_APP and (
                    inst.release_version != own_version or inst.release_commit != slug_commit
                ):
                    refusals.append(f"replacement_not_carrying:{inst.dyno}")
            if inst.carries_id:
                continue
            if inst.state_at_capture != "exited":
                refusals.append(f"retirement_unproven:{inst.dyno}")
                continue
            gone = effective_exit(inst)
            if gone + CLOCK_SKEW_MARGIN > lock_now:
                refusals.append(f"retirement_after_lock:{inst.dyno}")
            latest = gone if latest is None or gone > latest else latest
    return refusals, latest


def proof_refusals(
    proof_path: Optional[str],
    *,
    event_id: int,
    env: Mapping[str, str],
    lock_now: datetime,
) -> tuple[list[str], Optional[str], Optional[datetime]]:
    """``(refusals, proof sha256, latest effective exit)``. Missing proof refuses."""
    if not proof_path:
        return ["retirement_proof_absent"], None, None
    try:
        with open(proof_path, "rb") as fh:
            blob = fh.read()
    except OSError:
        return ["retirement_proof_absent"], None, None
    sha = hashlib.sha256(blob).hexdigest()
    try:
        raw = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return ["retirement_proof_invalid:json"], sha, None
    try:
        proof = parse_retirement_proof(raw, event_id=event_id)
    except ProofRefusal as exc:
        return [exc.reason], sha, None
    refusals, latest = judge_retirement_proof(
        proof,
        release_version=env.get("HEROKU_RELEASE_VERSION"),
        slug_commit=env.get("HEROKU_SLUG_COMMIT"),
        lock_now=lock_now,
    )
    return refusals, sha, latest


def release_age_refusal(created_at: Optional[str], lock_now: datetime) -> Optional[str]:
    """SUPPLEMENTARY: ``release_too_young`` / ``release_age_unknown``, or None.

    Claims nothing about retirement — see :data:`MIN_RELEASE_AGE`.
    """
    if not created_at:
        return "release_age_unknown"
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return "release_age_unknown"
    if created.tzinfo is None:
        return "release_age_unknown"
    if lock_now - created < MIN_RELEASE_AGE:
        return "release_too_young"
    return None


# ── The row ──────────────────────────────────────────────────────────────────


@dataclass
class RowAdmission:
    refusals: list[str] = field(default_factory=list)
    receipt: Optional[FillReceipt] = None
    new_tags: Optional[list] = None


def admit_row(row: Optional[Mapping[str, Any]], *, event_id: int, denylist=None) -> RowAdmission:
    """Every refusal the locked row earns, and the tags restore would write."""
    out = RowAdmission()
    if row is None:
        out.refusals.append("row_absent")
        return out
    if row["status"] != "scheduled":
        out.refusals.append("not_scheduled")
    tags = row["event_tags"] if isinstance(row["event_tags"], list) else []
    fill_at = [i for i, t in enumerate(tags) if isinstance(t, str) and t.startswith(FILL_TAG_PREFIX)]
    if any(isinstance(t, str) and t.startswith(RESTORED_TAG_PREFIX) for t in tags):
        out.refusals.append("already_restored")
    if not fill_at:
        out.refusals.append("receipt_absent")
    elif len(fill_at) > 1:
        out.refusals.append("receipt_duplicate")
    else:
        try:
            receipt = parse_fill_tag(tags[fill_at[0]])
        except ReceiptInvalid as exc:
            out.refusals.append(exc.reason)
        else:
            out.receipt = receipt
            if row["espn_id"] != receipt.espn_event_id:
                out.refusals.append("espn_id_drift")
            for col, want in (
                ("home_team_name", receipt.after_home_name),
                ("away_team_name", receipt.after_away_name),
                ("home_team_id", receipt.after_home_tid),
                ("away_team_id", receipt.after_away_tid),
            ):
                if row[col] != want:
                    out.refusals.append(f"after_drift:{col}")
            for col in ("home_team_normalized", "away_team_normalized"):
                if row[col] is not None:
                    out.refusals.append(f"after_drift:{col}")
            for col in ("home_team_alt_names", "away_team_alt_names"):
                if row[col] is not None and row[col] != []:
                    out.refusals.append(f"after_drift:{col}")
            fill_tag = tags[fill_at[0]]
            out.new_tags = list(tags)
            out.new_tags[fill_at[0]] = RESTORED_TAG_PREFIX + fill_tag[len(FILL_TAG_PREFIX):]
    listed = RESTORED_FILL_EVENT_IDS if denylist is None else denylist
    if event_id not in listed:
        out.refusals.append("not_denylisted")
    return out


@dataclass
class Admission:
    row: RowAdmission
    refusals: list[str]
    proof_sha256: Optional[str]
    latest_effective_exit: Optional[datetime]
    lock_now: datetime


def _admit(row, *, event_id: int, env: Mapping[str, str], lock_now: datetime, proof_path) -> Admission:
    """Every refusal: the row's, the code denylist, the release age, the proof."""
    row_adm = admit_row(row, event_id=event_id)
    refusals = list(row_adm.refusals)
    age = release_age_refusal(env.get("HEROKU_RELEASE_CREATED_AT"), lock_now)
    if age:
        refusals.append(age)
    p_refusals, sha, latest = proof_refusals(
        proof_path, event_id=event_id, env=env, lock_now=lock_now
    )
    refusals.extend(p_refusals)
    return Admission(row_adm, refusals, sha, latest, lock_now)


async def _read_row(session, event_id: int, *, lock: bool):
    sql = ROW_SQL + (" FOR UPDATE" if lock else "")
    row = (await session.execute(text(sql), {"eid": event_id})).mappings().first()
    return dict(row) if row is not None else None


async def _lock_now(session) -> datetime:
    # clock_timestamp(), not now(): now() is the transaction's START, which
    # precedes any wait for the row lock.
    return (await session.execute(text("SELECT clock_timestamp()"))).scalar()


async def _write(session, row: Mapping[str, Any], admission: RowAdmission) -> list[str]:
    """The one fenced UPDATE (§4.2). Returns refusals; empty means written."""
    r = admission.receipt
    params = {
        "prior_home_name": r.prior_home_name,
        "prior_away_name": r.prior_away_name,
        "prior_home_norm": r.prior_home_norm,
        "prior_away_norm": r.prior_away_norm,
        "new_tags": json.dumps(admission.new_tags),
        "eid": row["id"],
        "espn_id": r.espn_event_id,
        "after_home_name": r.after_home_name,
        "after_away_name": r.after_away_name,
        "after_home_tid": r.after_home_tid,
        "after_away_tid": r.after_away_tid,
        "locked_tags": json.dumps(row["event_tags"]),
    }
    rows = (await session.execute(text(RESTORE_SQL), params)).mappings().all()
    if len(rows) != 1:
        return [f"write_rowcount:{len(rows)}"]
    got = rows[0]
    want = {
        "home_team_name": r.prior_home_name,
        "away_team_name": r.prior_away_name,
        "home_team_id": None,
        "away_team_id": None,
        "home_team_normalized": r.prior_home_norm,
        "away_team_normalized": r.prior_away_norm,
        "event_tags": admission.new_tags,
    }
    return [f"write_mismatch:{col}" for col, value in want.items() if got[col] != value]


def _report(out: Callable[[str], None], event_id: int, row, admission: Admission, apply: bool) -> None:
    mode = "APPLY" if apply else "DRY RUN"
    out(f"restore_espn_participant_fill  event={event_id}  mode={mode}")
    out(f"  lock-time now()        : {admission.lock_now.isoformat()}")
    out(f"  proof sha256           : {admission.proof_sha256}")
    latest = admission.latest_effective_exit
    out(f"  latest effective exit  : {latest.isoformat() if latest else None}")
    r = admission.row.receipt
    if row is not None and r is not None:
        for col, after in (
            ("home_team_name", r.prior_home_name),
            ("away_team_name", r.prior_away_name),
            ("home_team_id", None),
            ("away_team_id", None),
            ("home_team_normalized", r.prior_home_norm),
            ("away_team_normalized", r.prior_away_norm),
            ("event_tags", admission.row.new_tags),
        ):
            out(f"  {col:<22} : {row[col]!r} -> {after!r}")
    for reason in admission.refusals:
        out(f"  REFUSED: {reason}")


async def run_restore(
    maker,
    *,
    event_id: int,
    apply: bool,
    proof_path: Optional[str],
    env: Mapping[str, str] = os.environ,
    out: Callable[[str], None] = print,
) -> int:
    """Exit code: 0 restored (or a clean dry run), 1 refused or not written."""
    app = env.get("HEROKU_APP_NAME")
    if app != RESTORE_APP:
        out(f"REFUSED: off_app (HEROKU_APP_NAME={app!r}; restore runs only on {RESTORE_APP!r})")
        return 1
    async with maker() as session:
        if not apply:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            row = await _read_row(session, event_id, lock=False)
            admission = _admit(
                row, event_id=event_id, env=env, lock_now=await _lock_now(session),
                proof_path=proof_path,
            )
            await session.rollback()
            _report(out, event_id, row, admission, apply)
            out("  dry run — nothing written.")
            return 1 if admission.refusals else 0

        row = await _read_row(session, event_id, lock=True)
        admission = _admit(
            row, event_id=event_id, env=env, lock_now=await _lock_now(session),
            proof_path=proof_path,
        )
        _report(out, event_id, row, admission, apply)
        if admission.refusals:
            await session.rollback()
            out("  nothing written.")
            return 1
        failed = await _write(session, row, admission.row)
        if failed:
            await session.rollback()
            for reason in failed:
                out(f"  REFUSED: {reason}")
            out("  rolled back — nothing written.")
            return 1
        await session.commit()
        out("  restored.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--event-id", type=int, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="write (default: dry run)")
    mode.add_argument("--dry-run", action="store_true", help="the default; writes nothing")
    parser.add_argument("--retirement-proof", default=None, help="the attended packet's proof JSON")
    args = parser.parse_args()

    async def _go() -> int:
        from app.services.database import async_session_maker

        return await run_restore(
            async_session_maker,
            event_id=args.event_id,
            apply=args.apply,
            proof_path=args.retirement_proof,
        )

    return asyncio.run(_go())


if __name__ == "__main__":
    raise SystemExit(main())
