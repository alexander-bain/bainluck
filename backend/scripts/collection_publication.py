#!/usr/bin/env python3
"""Preview or explicitly publish/withdraw one reviewed NFL/MLB hub (#9916), or
withdraw/exactly restore a reviewed manifest of its member edges (#9649).

No target discovery, assembly, flag changes or implicit publication. Authority's
correction helpers own all writes; this caller owns commit/rollback. See
``docs/collection-publication-operator.md`` for receipt and rollback limits.

MEMBER OPERATIONS (#9649). ``withdraw-members --manifest`` removes exactly the
reviewed edges through ``withdraw_member`` (whose append-only ledger row keeps
every later assembly pass from re-adding them), recording each edge's full
persisted row in that ledger row. ``readmit-members --restore-from-ledger
--backup`` is the exact undo: ``readmit_member`` plus re-inserting those same
rows, ids and all, because after #9990 assembly never re-proves a game's own
winner market. Preview is the default; one transaction per hub; any drift
refuses the whole hub before its first write.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.services.container_discovery import (  # noqa: E402
    DISCOVERABLE_EDITIONS,
    collection_card,
)
from app.utils import container_corrections as corrections  # noqa: E402
from app.utils.container_game_winner import (  # noqa: E402
    is_the_games_own_winner_market,
)
from app.utils.container_presentation import edition_for_slug  # noqa: E402
from app.utils.market_shape import SHAPE_DUEL  # noqa: E402

MEMBER_WITHDRAW = "withdraw-members"
MEMBER_RESTORE = "readmit-members"
MEMBER_OPERATIONS = (MEMBER_WITHDRAW, MEMBER_RESTORE)
OPERATIONS = ("publish", "withdraw", *MEMBER_OPERATIONS)


class OperatorRefused(ValueError):
    """No operation has been committed."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise OperatorRefused(message)


class SingleValue(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        value: Any,
        option_string: str | None = None,
    ) -> None:
        if getattr(namespace, self.dest, None) is not None:
            parser.error(
                f"{option_string} may be supplied only once; operate one hub per invocation"
            )
        setattr(namespace, self.dest, value)


@dataclass(frozen=True)
class Options:
    container_id: int | None = None
    slug: str | None = None
    operation: str | None = None
    apply: bool = False
    expected_revision: int | None = None
    actor: str | None = None
    reason: str | None = None
    evidence: dict | None = None
    manifest: str | None = None
    backup: str | None = None
    restore_from_ledger: bool = False
    hub_revisions: tuple | None = None
    receipt_dir: str | None = None


def _validate_identity(options: Options) -> None:
    if options.container_id is not None and options.container_id <= 0:
        raise OperatorRefused("container-id must be positive")
    if options.slug is not None and (
        not options.slug or options.slug != options.slug.strip()
    ):
        raise OperatorRefused("slug must be nonblank and exact (no surrounding spaces)")


def _validate_decision(options: Options) -> None:
    for name, value in (("actor", options.actor), ("reason", options.reason)):
        if not isinstance(value, str) or not value.strip():
            raise OperatorRefused(f"apply requires nonblank {name}")
    if len(options.actor.strip()) > 64:
        raise OperatorRefused("actor must fit the existing 64-character ledger field")
    if not isinstance(options.evidence, dict) or not options.evidence:
        raise OperatorRefused("apply requires a nonempty JSON object as evidence")
    try:
        json.dumps(options.evidence, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise OperatorRefused("evidence must contain only valid JSON values") from exc


def validate(options: Options) -> None:
    if options.operation in MEMBER_OPERATIONS:
        validate_member(options)
        return
    if options.container_id is None and not options.slug:
        raise OperatorRefused("an explicit --container-id or --slug is required")
    _validate_identity(options)
    if options.expected_revision is not None and options.expected_revision < 0:
        raise OperatorRefused("expected-revision must be nonnegative")
    if options.operation not in (None, "publish", "withdraw"):
        raise OperatorRefused(f"operation must be one of {', '.join(OPERATIONS)}")
    if (
        options.manifest
        or options.backup
        or options.restore_from_ledger
        or options.hub_revisions
        or options.receipt_dir
    ):
        raise OperatorRefused(
            "manifest/backup/hub-revision/receipt-dir apply only to member operations"
        )
    if options.apply:
        if options.container_id is None or options.slug is None:
            raise OperatorRefused(
                "apply requires BOTH the reviewed container-id and slug"
            )
        if options.operation is None or options.expected_revision is None:
            raise OperatorRefused("apply requires operation and expected-revision")
        _validate_decision(options)


def validate_member(options: Options) -> None:
    """Member operations take their exact scope from a reviewed file, never flags."""
    _validate_identity(options)
    if options.expected_revision is not None:
        raise OperatorRefused(
            "member operations take --hub-revision ID:REVISION per hub, "
            "not --expected-revision"
        )
    if options.operation == MEMBER_WITHDRAW:
        if not options.manifest:
            raise OperatorRefused("withdraw-members requires --manifest")
        if options.backup or options.restore_from_ledger:
            raise OperatorRefused("withdraw-members takes a manifest, never a backup")
    else:
        if not options.restore_from_ledger:
            raise OperatorRefused(
                "readmit-members is offered only as --restore-from-ledger: a bare "
                "readmit writes no edge, and assembly no longer re-proves winners"
            )
        if not options.backup:
            raise OperatorRefused(
                "--restore-from-ledger requires --backup (the withdraw-members "
                "apply receipt)"
            )
        if options.manifest:
            raise OperatorRefused("readmit-members restores a backup, not a manifest")
    seen = set()
    for container_id, revision in options.hub_revisions or ():
        if container_id <= 0 or revision < 0:
            raise OperatorRefused("hub-revision needs a positive id and revision >= 0")
        if container_id in seen:
            raise OperatorRefused(f"hub-revision names container {container_id} twice")
        seen.add(container_id)
    if options.apply:
        if not options.hub_revisions:
            raise OperatorRefused(
                "apply requires --hub-revision ID:REVISION for every hub it changes"
            )
        _validate_decision(options)


def _hub_revision(value: str) -> tuple:
    try:
        container_id, revision = value.split(":")
        return int(container_id), int(revision)
    except ValueError as malformed:
        raise argparse.ArgumentTypeError(
            f"hub-revision must be CONTAINER_ID:REVISION, got {value!r}"
        ) from malformed


def parse_args(argv: list[str] | None = None) -> Options:
    parser = Parser(description=__doc__)
    parser.add_argument("--container-id", action=SingleValue, type=int)
    parser.add_argument("--slug", action=SingleValue)
    parser.add_argument("--operation", action=SingleValue, choices=OPERATIONS)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-revision", action=SingleValue, type=int)
    parser.add_argument("--actor", action=SingleValue)
    parser.add_argument("--reason", action=SingleValue)
    parser.add_argument(
        "--evidence",
        action=SingleValue,
        help="nonempty JSON object recorded in the correction ledger",
    )
    parser.add_argument(
        "--manifest",
        action=SingleValue,
        help="withdraw-members: the reviewed edge manifest (exact targets and pins)",
    )
    parser.add_argument(
        "--backup",
        action=SingleValue,
        help="readmit-members: the withdraw-members apply receipt to restore",
    )
    parser.add_argument("--restore-from-ledger", action="store_true")
    parser.add_argument(
        "--hub-revision",
        dest="hub_revisions",
        action="append",
        type=_hub_revision,
        help="member apply: CONTAINER_ID:REVISION, once per hub operated",
    )
    parser.add_argument(
        "--receipt-dir",
        action=SingleValue,
        help="member operations: also write each hub receipt here (never overwritten)",
    )
    args = parser.parse_args(argv)
    evidence = None
    if args.evidence is not None:
        try:
            evidence = json.loads(args.evidence)
        except (ValueError, TypeError) as exc:
            raise OperatorRefused("evidence must be valid JSON") from exc
        if not isinstance(evidence, dict) or not evidence:
            raise OperatorRefused("evidence must be a nonempty JSON object")
    hub_revisions = tuple(args.hub_revisions) if args.hub_revisions else None
    options = Options(
        **{**vars(args), "evidence": evidence, "hub_revisions": hub_revisions}
    )
    validate(options)
    return options


# Same one-level hub membership as read_published/collection discovery, including
# suppression of withdrawn parts. Values are bound; no broad selector exists.
SNAPSHOT_SQL = """
WITH hub AS (
    SELECT id, slug, name, kind, status, window_start, window_end,
           parent_container_id, publication_state, membership_revision AS revision
    FROM containers WHERE {selector}
), parts AS (
    SELECT id FROM hub
    UNION ALL
    SELECT c.id FROM containers c JOIN hub ON c.parent_container_id = hub.id
    WHERE c.publication_state <> 'withdrawn'
)
SELECT hub.id, hub.slug, hub.name, hub.kind, hub.status, hub.window_start,
       hub.window_end, hub.parent_container_id, hub.publication_state, hub.revision,
       COUNT(e.id) AS edge_count,
       COUNT(DISTINCT ev.id) AS game_count,
       COUNT(DISTINCT fm.id) AS question_count,
       COUNT(e.id) FILTER (WHERE (e.child_type = 'event' AND ev.id IS NULL)
                             OR (e.child_type = 'market' AND fm.id IS NULL)) AS missing_row_count,
       COALESCE(array_agg(DISTINCT e.class) FILTER (WHERE e.id IS NOT NULL), '{{}}') AS classes
FROM hub
LEFT JOIN event_edges e ON e.parent_type = 'container' AND e.kind = 'contains'
                       AND e.parent_id IN (SELECT id FROM parts)
LEFT JOIN events ev ON e.child_type = 'event' AND ev.id = e.child_id
LEFT JOIN futures_markets fm ON e.child_type = 'market' AND fm.id = e.child_id
GROUP BY hub.id, hub.slug, hub.name, hub.kind, hub.status, hub.window_start,
         hub.window_end, hub.parent_container_id, hub.publication_state, hub.revision
"""


async def snapshot(session, options: Options) -> dict:
    selector = (
        "id = :container_id" if options.container_id is not None else "slug = :slug"
    )
    result = await session.execute(
        text(SNAPSHOT_SQL.format(selector=selector)),
        {"container_id": options.container_id, "slug": options.slug},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise OperatorRefused("the explicitly selected container does not exist")
    facts = dict(row)
    if options.container_id is not None and facts["id"] != options.container_id:
        raise OperatorRefused("container ID does not match the reviewed identity")
    if options.slug is not None and facts["slug"] != options.slug:
        raise OperatorRefused("container slug does not match the reviewed identity")
    if (
        options.expected_revision is not None
        and facts["revision"] != options.expected_revision
    ):
        raise corrections.StaleRevision(
            facts["id"], options.expected_revision, facts["revision"]
        )
    return facts


def eligibility(facts: dict) -> tuple[dict, str | None]:
    edition = edition_for_slug(facts["slug"])
    if edition is None or edition["kind"] not in DISCOVERABLE_EDITIONS:
        raise OperatorRefused(
            "target is not a canonical NFL-week/MLB-postseason collection"
        )
    if facts["parent_container_id"] is not None:
        raise OperatorRefused(
            "target is nested; only the explicitly reviewed root may be operated"
        )
    # The producer's own pure eligibility check supplies the prospective reader
    # result. It is NOT a publication-state write or a bypass of its flags.
    _, publish_refusal = collection_card({**facts, "publication_state": "published"})
    return edition, publish_refusal


def rollback_prerequisites(facts: dict, result: corrections.CorrectionResult) -> dict:
    if not result.applied:
        inverse = None
        note = (
            "No new publication change was made; do not undo a pre-existing decision."
        )
    elif result.action == "publish":
        inverse = "withdraw"
        note = "Withdraw preserves membership and the ledger; it does not restore unpublished state."
    elif facts["publication_state"] == "published":
        inverse = "publish"
        note = "Republish only after renewed review of eligibility, members and authorization."
    else:
        inverse = None
        note = "The helpers cannot restore an original unpublished state; no inverse command is offered."
    return {
        "operation": inverse,
        "container_id": result.container_id,
        "slug": facts["slug"],
        "expected_revision_at_commit": result.revision,
        "runnable_without_fresh_review": False,
        "requires": [
            "fresh targeted preview of the same ID and slug",
            "review any revision/member changes; never silently replace expected_revision",
            "explicit apply, operation, actor, reason and rollback evidence",
        ],
        "note": note,
    }


async def prepare(session, options: Options) -> dict:
    """Use a caller-owned transaction; never commit or roll back inside here."""
    validate(options)
    schema = await corrections.correction_schema_present(session)
    if not schema.complete:
        raise corrections.CorrectionSchemaAbsent(
            "container correction schema is not available"
        )
    if options.apply:
        # The helper's own lock ordering closes identity drift between this
        # snapshot and its mutation. Nested targets are still refused below.
        await corrections.lock_container_chain(session, options.container_id)
    facts = await snapshot(session, options)
    edition, publish_refusal = eligibility(facts)
    if options.operation == "publish" and publish_refusal:
        raise OperatorRefused(
            f"publication refused by reader eligibility: {publish_refusal}"
        )
    receipt: dict[str, Any] = {
        "operator": "collection_publication",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "preview",
        "committed": False,
        "operation": options.operation,
        "expected_revision": options.expected_revision,
        "target": facts,
        "edition": edition,
        "publish_eligible": publish_refusal is None,
        "publish_refusal": publish_refusal,
        "coverage_limit": "Stored member coverage only; completeness requires Authority's assembly receipt.",
        "rollback": None,
    }
    if not options.apply:
        return receipt
    helper = (
        corrections.publish_container
        if options.operation == "publish"
        else corrections.withdraw_publication
    )
    result = await helper(
        session,
        container_id=options.container_id,
        expected_revision=options.expected_revision,
        actor=options.actor,
        reason=options.reason,
        evidence=options.evidence,
    )
    receipt.update(
        status="prepared",
        before=facts,
        target={
            **facts,
            "revision": result.revision,
            "publication_state": result.publication_state,
        },
        decision={
            "actor": options.actor.strip(),
            "reason": options.reason.strip(),
            "evidence": options.evidence,
        },
        correction=asdict(result),
        rollback=rollback_prerequisites(facts, result),
    )
    return receipt


def failure_receipt(options: Options, exc: Exception, committing: bool) -> dict:
    known_refusal = isinstance(exc, (OperatorRefused, corrections.CorrectionRefused))
    return {
        "operator": "collection_publication",
        "status": (
            "commit_outcome_unknown"
            if committing
            else "refused" if known_refusal else "failed"
        ),
        "committed": None if committing else False,
        "target": {"id": options.container_id, "slug": options.slug},
        "operation": options.operation,
        "expected_revision": options.expected_revision,
        "current_revision": (
            exc.current if isinstance(exc, corrections.StaleRevision) else None
        ),
        "error": str(exc) if known_refusal else type(exc).__name__,
        "rollback": None,
        "next_step": "Freshly review the selected target before retry or rollback; no revision is assumed current.",
    }


async def run(options: Options, session_factory) -> tuple[dict, int]:
    """The CLI owns its transaction: previews/errors roll back, only apply commits."""
    validate(options)
    committing = False
    receipt = None
    try:
        async with session_factory() as session:
            try:
                if not options.apply:
                    await session.execute(
                        text(
                            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                        )
                    )
                receipt = await prepare(session, options)
                if options.apply:
                    committing = True
                    await session.commit()
                    receipt["committed"] = True
                    receipt["committed_at"] = datetime.now(timezone.utc).isoformat()
                    receipt["status"] = (
                        "applied" if receipt["correction"]["applied"] else "noop"
                    )
                else:
                    await session.rollback()
                return receipt, 0
            except Exception as exc:
                try:
                    await session.rollback()
                except Exception:
                    pass
                return failure_receipt(options, exc, committing), 1
    except Exception as exc:
        # Resource cleanup can fail AFTER an acknowledged commit. Preserve that
        # fact rather than telling an operator their successful write never ran.
        if receipt and receipt.get("committed"):
            return {
                **receipt,
                "status": "cleanup_failed_after_commit",
                "error": type(exc).__name__,
            }, 1
        return failure_receipt(options, exc, committing), 1


# ---------------------------------------------------------------------------
# Member operations (#9649): withdraw reviewed edges, restore them exactly
# ---------------------------------------------------------------------------

WINNER_RULE = "container_game_winner.is_the_games_own_winner_market"

#: How the helpers' revision increments compose. Stated in every receipt so a
#: reader never mistakes the final revision for one decision.
REVISION_COMPOSITION = (
    "each withdraw_member/readmit_member call bumps membership_revision by one "
    "on the hub and every ancestor; N targets move the hub from R to R+N inside "
    "ONE transaction, so readers only ever see R or R+N. Every intermediate "
    "revision is the per-target revision_after and its ledger row's revision."
)

BACKUP_LOCATION = (
    "container_corrections rows (append-only) at ledger_id, evidence.preimage; "
    "this receipt is a copy and must match the ledger exactly to be restored"
)


class MemberDrift(OperatorRefused):
    """The stored state no longer matches the reviewed plan. Nothing written."""

    def __init__(self, container_id: int, errors: list):
        self.errors = list(errors)
        super().__init__(
            f"container {container_id}: {len(self.errors)} precondition(s) drifted; "
            "a changed precondition needs a fresh reviewed plan, never a broader one"
        )


@dataclass(frozen=True)
class HubPlan:
    container_id: int
    slug: str
    #: withdraw: the manifest's historical revision; restore: the backup's post.
    expected_revision: int
    publication_state: str
    targets: tuple
    pin: dict


@dataclass(frozen=True)
class MemberPlan:
    operation: str
    source_kind: str
    source_path: str
    source_sha256: str
    issue: Any
    hubs: tuple

    def source(self) -> dict:
        return {
            "kind": self.source_kind,
            "path": self.source_path,
            "sha256": self.source_sha256,
            "issue": self.issue,
        }


def preimage_fingerprint(preimages) -> str:
    """sha256 over the canonical JSON of the full edge rows, ordered by id."""
    ordered = sorted(preimages, key=lambda row: int(row["id"]))
    blob = json.dumps(ordered, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _read_json(path: str, label: str) -> tuple:
    try:
        raw = Path(path).read_bytes()
        return json.loads(raw), hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError) as exc:
        raise OperatorRefused(f"{label} is not a readable JSON file") from exc


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require(record: dict, fields: dict, where: str) -> None:
    for key, kind in fields.items():
        value = record.get(key)
        ok = _is_int(value) if kind is int else isinstance(value, kind)
        if not ok or (kind is str and not value.strip()):
            raise OperatorRefused(f"{where} has no valid {key}")


def _select_hubs(options: Options, hubs: list, label: str) -> tuple:
    if options.container_id is not None:
        hubs = [h for h in hubs if h.container_id == options.container_id]
        if not hubs:
            raise OperatorRefused(
                f"container {options.container_id} is not in the {label}"
            )
    if options.slug is not None:
        hubs = [h for h in hubs if h.slug == options.slug]
        if not hubs:
            raise OperatorRefused(
                f"slug {options.slug!r} is not a selected {label} hub"
            )
    supplied = dict(options.hub_revisions or ())
    if options.apply or supplied:
        wanted = {h.container_id for h in hubs}
        if set(supplied) != wanted:
            raise OperatorRefused(
                f"--hub-revision must name exactly the hubs operated: {sorted(wanted)}"
            )
        for hub in hubs:
            if supplied[hub.container_id] != hub.expected_revision:
                raise OperatorRefused(
                    f"container {hub.container_id}: supplied revision "
                    f"{supplied[hub.container_id]} is not the {label}'s verified "
                    f"precondition {hub.expected_revision}; a changed precondition "
                    "needs a fresh reviewed plan"
                )
    return tuple(hubs)


_TARGET_FIELDS = {
    "container_id": int,
    "container_slug": str,
    "expected_revision": int,
    "edge_id": int,
    "edge_class": str,
    "child_type": str,
    "market_id": int,
    "venue": str,
    "market_type": str,
    "event_id": int,
    "external_id": str,
}
_PIN_FIELDS = {
    "slug": str,
    "publication_state": str,
    "membership_revision": int,
    "events": int,
    "market_edges": int,
    "targets": int,
    "ledger_rows": list,
}


def load_withdraw_plan(options: Options) -> MemberPlan:
    doc, digest = _read_json(options.manifest, "manifest")
    pins = doc.get("pins") if isinstance(doc, dict) else None
    targets = doc.get("targets") if isinstance(doc, dict) else None
    if not isinstance(pins, dict) or not pins:
        raise OperatorRefused("manifest has no pins")
    if not isinstance(targets, list) or not targets:
        raise OperatorRefused("manifest has no targets")
    by_hub: dict = {}
    edges, members = set(), set()
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            raise OperatorRefused(f"manifest target {index} is not an object")
        _require(target, _TARGET_FIELDS, f"manifest target {index}")
        if target["child_type"] != "market" or target["market_type"] != SHAPE_DUEL:
            raise OperatorRefused(
                f"manifest target {index} is not a market of shape {SHAPE_DUEL}"
            )
        member = (target["container_id"], target["market_id"])
        if target["edge_id"] in edges or member in members:
            raise OperatorRefused(
                f"manifest target {index} duplicates edge {target['edge_id']} "
                f"or market {target['market_id']}"
            )
        edges.add(target["edge_id"])
        members.add(member)
        pin = pins.get(str(target["container_id"]))
        if not isinstance(pin, dict):
            raise OperatorRefused(
                f"manifest target {index} names unpinned container "
                f"{target['container_id']}"
            )
        if target["container_slug"] != pin.get("slug") or target[
            "expected_revision"
        ] != pin.get("membership_revision"):
            raise OperatorRefused(
                f"manifest target {index} disagrees with its container's pin"
            )
        by_hub.setdefault(target["container_id"], []).append(target)
    hubs = []
    for key, pin in pins.items():
        if not key.isdigit() or not isinstance(pin, dict):
            raise OperatorRefused(f"manifest pin {key!r} is malformed")
        _require(pin, _PIN_FIELDS, f"manifest pin {key}")
        if not all(_is_int(i) for i in pin["ledger_rows"]):
            raise OperatorRefused(f"manifest pin {key} ledger_rows must be ids")
        container_id = int(key)
        hub_targets = by_hub.get(container_id, [])
        if not hub_targets or len(hub_targets) != pin["targets"]:
            raise OperatorRefused(
                f"container {container_id}: pin says {pin['targets']} targets, "
                f"manifest lists {len(hub_targets)}"
            )
        hubs.append(
            HubPlan(
                container_id=container_id,
                slug=pin["slug"],
                expected_revision=pin["membership_revision"],
                publication_state=pin["publication_state"],
                targets=tuple(sorted(hub_targets, key=lambda t: t["edge_id"])),
                pin=pin,
            )
        )
    hubs.sort(key=lambda h: h.container_id)
    return MemberPlan(
        operation=MEMBER_WITHDRAW,
        source_kind="manifest",
        source_path=options.manifest,
        source_sha256=digest,
        issue=doc.get("issue"),
        hubs=_select_hubs(options, hubs, "manifest"),
    )


_BACKUP_HUB_FIELDS = {
    "container_id": int,
    "slug": str,
    "publication_state": str,
    "pre_revision": int,
    "post_revision": int,
    "backup_sha256": str,
    "edge_columns": dict,
    "targets": list,
}
_BACKUP_TARGET_FIELDS = {
    "edge_id": int,
    "market_id": int,
    "event_id": int,
    "ledger_id": int,
    "revision_after": int,
    "preimage": dict,
}


def load_restore_plan(options: Options) -> MemberPlan:
    doc, digest = _read_json(options.backup, "backup")
    receipts = doc.get("hubs") if isinstance(doc, dict) and "hubs" in doc else [doc]
    if not isinstance(receipts, list) or not receipts:
        raise OperatorRefused("backup holds no hub receipts")
    hubs, issue = [], None
    for index, receipt in enumerate(receipts):
        where = f"backup hub {index}"
        if not isinstance(receipt, dict) or receipt.get("operator") != (
            "collection_publication"
        ):
            raise OperatorRefused(f"{where} is not a collection_publication receipt")
        if receipt.get("operation") != MEMBER_WITHDRAW:
            raise OperatorRefused(f"{where} is not a withdraw-members receipt")
        if receipt.get("receipt_kind") == "preview":
            raise OperatorRefused(f"{where} is a preview; a preview is never a backup")
        if receipt.get("committed") is None:
            raise OperatorRefused(
                f"{where} has an unknown commit outcome; resolve the ledger first"
            )
        if receipt.get("committed") is not True:
            continue  # refused, rolled back or never attempted: nothing to restore
        if receipt.get("receipt_kind") != "withdraw_apply":
            raise OperatorRefused(
                f"{where} is a {receipt.get('receipt_kind')!r} receipt; only a "
                "committed withdraw apply is a backup"
            )
        _require(receipt, _BACKUP_HUB_FIELDS, where)
        targets = receipt["targets"]
        if not targets:
            raise OperatorRefused(f"{where} lists no targets")
        seen: set = set()
        for t_index, target in enumerate(targets):
            if not isinstance(target, dict):
                raise OperatorRefused(f"{where} target {t_index} is not an object")
            _require(target, _BACKUP_TARGET_FIELDS, f"{where} target {t_index}")
            keys = {("edge", target["edge_id"]), ("ledger", target["ledger_id"])}
            if keys & seen or str(target["preimage"].get("id")) != str(
                target["edge_id"]
            ):
                raise OperatorRefused(f"{where} target {t_index} is duplicated or torn")
            seen |= keys
        if (
            preimage_fingerprint([t["preimage"] for t in targets])
            != receipt["backup_sha256"]
        ):
            raise OperatorRefused(f"{where}: preimages do not match backup_sha256")
        revisions = sorted(t["revision_after"] for t in targets)
        if revisions != list(
            range(receipt["pre_revision"] + 1, receipt["post_revision"] + 1)
        ):
            raise OperatorRefused(
                f"{where}: per-target revisions do not compose pre -> post"
            )
        issue = issue or (receipt.get("source") or {}).get("issue")
        hubs.append(
            HubPlan(
                container_id=receipt["container_id"],
                slug=receipt["slug"],
                expected_revision=receipt["post_revision"],
                publication_state=receipt["publication_state"],
                targets=tuple(sorted(targets, key=lambda t: t["edge_id"])),
                pin=receipt,
            )
        )
    if not hubs:
        raise OperatorRefused("backup has no committed withdrawal to restore")
    if len({h.container_id for h in hubs}) != len(hubs):
        raise OperatorRefused("backup names one container twice")
    hubs.sort(key=lambda h: h.container_id)
    return MemberPlan(
        operation=MEMBER_RESTORE,
        source_kind="backup",
        source_path=options.backup,
        source_sha256=digest,
        issue=issue,
        hubs=_select_hubs(options, hubs, "backup"),
    )


def load_member_plan(options: Options) -> MemberPlan:
    validate(options)
    if options.operation == MEMBER_WITHDRAW:
        return load_withdraw_plan(options)
    return load_restore_plan(options)


HUB_FACTS_SQL = """
SELECT c.id, c.slug, c.parent_container_id, c.publication_state,
       c.membership_revision AS revision,
       (SELECT count(*) FROM event_edges g
         WHERE g.parent_type = 'container' AND g.parent_id = c.id
           AND g.kind = 'contains' AND g.child_type = 'event') AS events,
       (SELECT count(*) FROM event_edges g
         WHERE g.parent_type = 'container' AND g.parent_id = c.id
           AND g.kind = 'contains' AND g.child_type = 'market') AS market_edges
FROM containers c WHERE c.id = :cid
"""

HUB_LEDGER_SQL = (
    "SELECT id, scope, action, child_type, child_id, revision, evidence "
    "FROM container_corrections WHERE container_id = :cid ORDER BY id"
)

EDGE_COLUMNS_SQL = (
    "SELECT a.attname, format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
    "WHERE a.attrelid = 'event_edges'::regclass AND a.attnum > 0 "
    "AND NOT a.attisdropped ORDER BY a.attnum"
)

# Every persisted column, as Postgres's own text form, so a restore re-inserts
# the exact values (numeric scale, microseconds) and no column is forgotten.
EDGE_PREIMAGE_SQL = (
    "SELECT e.id, j.key, j.value FROM event_edges e "
    "CROSS JOIN LATERAL jsonb_each_text(to_jsonb(e)) j "
    "WHERE e.id = ANY(CAST(:ids AS BIGINT[]))"
)

WITHDRAW_TARGETS_SQL = """
SELECT e.id AS edge_id, e.parent_type, e.parent_id, e.child_type, e.child_id,
       e.kind, e.class, fm.id AS market_id, fm.source, fm.external_id, fm.name,
       fm.market_type, fm.event_id, admitted.id AS admitted_edge_id
FROM event_edges e
LEFT JOIN futures_markets fm ON e.child_type = 'market' AND fm.id = e.child_id
LEFT JOIN event_edges admitted
       ON admitted.parent_type = 'container' AND admitted.parent_id = :cid
      AND admitted.kind = 'contains' AND admitted.child_type = 'event'
      AND admitted.child_id = fm.event_id
WHERE e.id = ANY(CAST(:ids AS BIGINT[]))
"""

# Matching and polling writers update futures_markets directly and never take
# the container chain lock, so an apply holds a row lock on every target market
# (ascending id, after the root-first chain) from before it reads identity and
# classifier inputs until the hub commits. SHARE blocks every UPDATE/DELETE of
# those rows and leaves FK KEY SHARE (outcome inserts) alone. A change that
# committed before the lock is read by the checks that follow it and refuses.
# The admitted game edges need no lock of their own: every writer of a
# container's edges (assembly, corrections, this operator) holds the chain lock.
LOCK_MARKETS_SQL = (
    "SELECT id FROM futures_markets WHERE id = ANY(CAST(:ids AS BIGINT[])) "
    "ORDER BY id FOR SHARE"
)

RESTORE_MARKETS_SQL = """
SELECT fm.id AS market_id, fm.source, fm.external_id, fm.name, fm.market_type,
       fm.event_id, admitted.id AS admitted_edge_id
FROM futures_markets fm
LEFT JOIN event_edges admitted
       ON admitted.parent_type = 'container' AND admitted.parent_id = :cid
      AND admitted.kind = 'contains' AND admitted.child_type = 'event'
      AND admitted.child_id = fm.event_id
WHERE fm.id = ANY(CAST(:ids AS BIGINT[]))
"""

RESTORE_OCCUPIED_SQL = (
    "SELECT id, parent_id, child_id FROM event_edges "
    "WHERE id = ANY(CAST(:edge_ids AS BIGINT[])) "
    "   OR (parent_type = 'container' AND parent_id = :cid AND kind = 'contains' "
    "       AND child_type = 'market' AND child_id = ANY(CAST(:market_ids AS BIGINT[])))"
)

RESTORE_RECEIPTS_SQL = (
    "SELECT id FROM market_match_receipts WHERE id = ANY(CAST(:ids AS BIGINT[]))"
)

LATEST_MEMBER_DECISION_SQL = (
    "SELECT id, action, revision FROM container_corrections "
    "WHERE container_id = :cid AND scope = 'member' AND child_type = 'market' "
    "  AND child_id = :mid ORDER BY id DESC LIMIT 1"
)


def _as_json(value):
    return json.loads(value) if isinstance(value, str) else value


async def _begin_member_hub(session, options: Options, hub: HubPlan) -> None:
    # One clock for preimage text, so a restore compares byte-for-byte.
    await session.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    schema = await corrections.correction_schema_present(session)
    if not schema.complete:
        raise corrections.CorrectionSchemaAbsent(
            "container correction schema is not available"
        )
    if options.apply:
        locked = await corrections.lock_container_chain(session, hub.container_id)
        if locked is None:
            raise OperatorRefused(f"container {hub.container_id} does not exist")


async def _lock_markets(session, market_ids) -> None:
    """Apply only: a READ ONLY preview cannot lock and has nothing to protect."""
    await session.execute(text(LOCK_MARKETS_SQL), {"ids": sorted(set(market_ids))})


async def _hub_facts(session, hub: HubPlan) -> dict:
    row = (
        (await session.execute(text(HUB_FACTS_SQL), {"cid": hub.container_id}))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise OperatorRefused(f"container {hub.container_id} does not exist")
    facts = dict(row)
    if facts["slug"] != hub.slug:
        raise OperatorRefused(
            f"container {hub.container_id} slug is {facts['slug']!r}, not {hub.slug!r}"
        )
    edition = edition_for_slug(facts["slug"])
    if edition is None or edition["kind"] not in DISCOVERABLE_EDITIONS:
        raise OperatorRefused("target is not a canonical NFL-week/MLB-postseason hub")
    if facts["parent_container_id"] is not None:
        raise OperatorRefused("target is nested; only a reviewed root may be operated")
    if facts["publication_state"] != hub.publication_state:
        raise OperatorRefused(
            f"container {hub.container_id} publication state drifted: "
            f"{facts['publication_state']!r}, reviewed {hub.publication_state!r}"
        )
    if facts["revision"] != hub.expected_revision:
        raise corrections.StaleRevision(
            hub.container_id, hub.expected_revision, facts["revision"]
        )
    return facts


async def _edge_columns(session) -> dict:
    rows = (await session.execute(text(EDGE_COLUMNS_SQL))).fetchall()
    return {r[0]: r[1] for r in rows}


async def _preimages(session, edge_ids) -> dict:
    rows = (
        await session.execute(text(EDGE_PREIMAGE_SQL), {"ids": sorted(edge_ids)})
    ).fetchall()
    found: dict = {}
    for edge_id, key, value in rows:
        found.setdefault(int(edge_id), {})[key] = value
    return found


async def _ledger(session, container_id: int) -> list:
    rows = (
        (await session.execute(text(HUB_LEDGER_SQL), {"cid": container_id}))
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def _latest_decision(session, container_id: int, market_id: int) -> dict:
    row = (
        (
            await session.execute(
                text(LATEST_MEMBER_DECISION_SQL),
                {"cid": container_id, "mid": market_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else {}


def _hub_receipt(plan: MemberPlan, hub: HubPlan) -> dict:
    return {
        "operator": "collection_publication",
        "operation": plan.operation,
        "receipt_kind": "preview",
        "status": "preview",
        "committed": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "container_id": hub.container_id,
        "slug": hub.slug,
        "source": plan.source(),
        "revision_composition": REVISION_COMPOSITION,
        "errors": [],
        "undo": None,
    }


async def withdraw_hub(
    session, plan: MemberPlan, hub: HubPlan, options: Options
) -> dict:
    """Validate every target under the hub's locks, then withdraw each one.

    Caller-owned transaction. Every check runs before the first write and all
    failures are reported together; one failure refuses the whole hub.
    """
    await _begin_member_hub(session, options, hub)
    facts = await _hub_facts(session, hub)
    pin, errors = hub.pin, []
    ledger_before = [r["id"] for r in await _ledger(session, hub.container_id)]
    if ledger_before != list(pin["ledger_rows"]):
        errors.append(
            f"ledger drift: rows {ledger_before}, manifest pinned {pin['ledger_rows']}"
        )
    for name in ("events", "market_edges"):
        if facts[name] != pin[name]:
            errors.append(f"{name} drift: {facts[name]}, manifest pinned {pin[name]}")
    columns = await _edge_columns(session)
    edge_ids = [t["edge_id"] for t in hub.targets]
    if options.apply:
        await _lock_markets(session, [t["market_id"] for t in hub.targets])
    lock = " FOR UPDATE OF e" if options.apply else ""
    rows = (
        (
            await session.execute(
                text(WITHDRAW_TARGETS_SQL + lock),
                {"cid": hub.container_id, "ids": edge_ids},
            )
        )
        .mappings()
        .all()
    )
    by_edge = {int(r["edge_id"]): dict(r) for r in rows}
    preimages = await _preimages(session, edge_ids)
    entries = []
    for target in hub.targets:
        edge_id, market_id = target["edge_id"], target["market_id"]
        row = by_edge.get(edge_id)
        if row is None:
            errors.append(f"edge {edge_id} (market {market_id}) does not exist")
            continue
        for column, want in (
            ("parent_type", "container"),
            ("parent_id", hub.container_id),
            ("kind", "contains"),
            ("child_type", "market"),
            ("child_id", market_id),
            ("class", target["edge_class"]),
        ):
            if row[column] != want:
                errors.append(
                    f"edge {edge_id}: {column} is {row[column]!r}, expected {want!r}"
                )
        if row["market_id"] is None:
            errors.append(f"edge {edge_id}: market {market_id} does not exist")
            continue
        for column, want in (
            ("source", target["venue"]),
            ("external_id", target["external_id"]),
            ("event_id", target["event_id"]),
            ("market_type", SHAPE_DUEL),
        ):
            if row[column] != want:
                errors.append(
                    f"market {market_id}: {column} is {row[column]!r}, expected {want!r}"
                )
        winner = is_the_games_own_winner_market(
            row["market_type"], row["name"], row["external_id"]
        )
        if not winner:
            errors.append(f"market {market_id}: {WINNER_RULE} no longer says True")
        if row["admitted_edge_id"] is None:
            errors.append(
                f"market {market_id}: event {row['event_id']} is not an admitted "
                f"game of container {hub.container_id}"
            )
        preimage = preimages.get(edge_id)
        if not preimage or set(preimage) != set(columns):
            errors.append(f"edge {edge_id}: full preimage unreadable")
            continue
        entries.append(
            {
                "edge_id": edge_id,
                "market_id": market_id,
                "event_id": target["event_id"],
                "venue": target["venue"],
                "preimage": preimage,
                "classifier": {
                    "rule": WINNER_RULE,
                    "market_type": row["market_type"],
                    "name": row["name"],
                    "external_id": row["external_id"],
                    "result": winner,
                },
                "identity": {
                    "market_id": market_id,
                    "source": row["source"],
                    "external_id": row["external_id"],
                    "event_id": row["event_id"],
                    "admitted_event_edge_id": row["admitted_edge_id"],
                },
            }
        )
    if errors:
        raise MemberDrift(hub.container_id, errors)
    fingerprint = preimage_fingerprint([e["preimage"] for e in entries])
    receipt = _hub_receipt(plan, hub)
    receipt.update(
        publication_state=facts["publication_state"],
        pre_revision=facts["revision"],
        games={"before": facts["events"]},
        market_edges={"before": facts["market_edges"]},
        ledger_ids_before=ledger_before,
        edge_columns=columns,
        backup_sha256=fingerprint,
        targets=entries,
    )
    if not options.apply:
        receipt["would_be_revision"] = facts["revision"] + len(entries)
        return receipt

    decision = options.evidence
    revision = facts["revision"]
    for entry in entries:
        evidence = {
            "operator": "collection_publication",
            "operation": MEMBER_WITHDRAW,
            "source": plan.source(),
            "backup_sha256": fingerprint,
            "hub_pre_revision": facts["revision"],
            "ledger_ids_before": ledger_before,
            "edge_columns": columns,
            "preimage": entry["preimage"],
            "classifier": entry["classifier"],
            "identity": entry["identity"],
            "decision_evidence": decision,
        }
        result = await corrections.withdraw_member(
            session,
            container_id=hub.container_id,
            child_type="market",
            child_id=entry["market_id"],
            reason=options.reason,
            actor=options.actor,
            evidence=evidence,
            expected_revision=revision,
        )
        if not (
            result.applied
            and result.edges_removed == 1
            and result.revision == revision + 1
        ):
            raise OperatorRefused(
                f"market {entry['market_id']}: withdraw_member did not remove exactly "
                f"its edge ({asdict(result)})"
            )
        recorded = await _latest_decision(session, hub.container_id, entry["market_id"])
        if recorded.get("action") != "withdraw" or recorded.get("revision") != (
            result.revision
        ):
            raise OperatorRefused(
                f"market {entry['market_id']}: ledger row not read back"
            )
        revision = result.revision
        entry["ledger_id"] = int(recorded["id"])
        entry["revision_after"] = revision
    after = (
        (await session.execute(text(HUB_FACTS_SQL), {"cid": hub.container_id}))
        .mappings()
        .one()
    )
    if (
        after["revision"] != revision
        or after["events"] != facts["events"]
        or after["market_edges"] != facts["market_edges"] - len(entries)
        or await _preimages(session, edge_ids)
    ):
        raise OperatorRefused(
            f"container {hub.container_id}: post-state is not games kept, targets gone"
        )
    receipt.update(
        receipt_kind="withdraw_apply",
        status="prepared",
        post_revision=revision,
        games={"before": facts["events"], "after": after["events"]},
        market_edges={"before": facts["market_edges"], "after": after["market_edges"]},
        backup_location=BACKUP_LOCATION,
        decision={
            "actor": options.actor.strip(),
            "reason": options.reason.strip(),
            "evidence": decision,
        },
        undo={
            "operation": MEMBER_RESTORE,
            "flags": ["--restore-from-ledger", "--backup <this receipt>"],
            "container_id": hub.container_id,
            "slug": hub.slug,
            "hub_revision": revision,
            "ledger_ids": [e["ledger_id"] for e in entries],
            "backup_sha256": fingerprint,
            "runnable_without_fresh_review": False,
            "requires": [
                f"hub still at revision {revision} with no later ledger rows",
                "a fresh readmit-members --restore-from-ledger preview of this backup",
                "explicit apply, actor, reason and evidence",
            ],
        },
    )
    return receipt


async def _insert_preimage(session, preimage: dict, columns: dict) -> None:
    """Re-insert one edge row verbatim. Names and types come from the catalog."""
    names = list(columns)
    target = ", ".join(f'"{name}"' for name in names)
    values = ", ".join(
        f"CAST(CAST(:v{i} AS TEXT) AS {columns[name]})" for i, name in enumerate(names)
    )
    await session.execute(
        text(f"INSERT INTO event_edges ({target}) VALUES ({values})"),
        {f"v{i}": preimage[name] for i, name in enumerate(names)},
    )


async def restore_hub(
    session, plan: MemberPlan, hub: HubPlan, options: Options
) -> dict:
    """Readmit each withdrawn member AND re-insert its exact backed-up edge row.

    Refuses on any revision, ledger, suppression, edge-id, identity, membership,
    schema or backup drift before the first write. Never recomputes metadata.
    """
    await _begin_member_hub(session, options, hub)
    facts = await _hub_facts(session, hub)
    backup, errors = hub.pin, []
    if options.apply:
        await _lock_markets(session, [t["market_id"] for t in hub.targets])
    ledger = await _ledger(session, hub.container_id)
    by_id = {int(r["id"]): r for r in ledger}
    withdrawals = [t["ledger_id"] for t in hub.targets]
    tail = sorted(int(r["id"]) for r in ledger if int(r["id"]) >= min(withdrawals))
    if tail != sorted(withdrawals):
        errors.append(
            "intervening correction: ledger rows "
            f"{sorted(set(tail) - set(withdrawals))} are not the backed-up withdrawals"
        )
    columns = await _edge_columns(session)
    if columns != backup["edge_columns"]:
        errors.append("event_edges columns changed since the backup was taken")
    evidence_by_edge = {}
    for target in hub.targets:
        row = by_id.get(target["ledger_id"])
        if row is None:
            errors.append(f"ledger row {target['ledger_id']} does not exist")
            continue
        shape = (row["scope"], row["action"], row["child_type"], row["child_id"])
        if shape != ("member", "withdraw", "market", target["market_id"]) or (
            row["revision"] != target["revision_after"]
        ):
            errors.append(
                f"ledger row {target['ledger_id']} is not the withdrawal of market "
                f"{target['market_id']} at revision {target['revision_after']}"
            )
            continue
        evidence = _as_json(row["evidence"]) or {}
        if evidence.get("preimage") != target["preimage"]:
            errors.append(
                f"ledger row {target['ledger_id']}: preimage differs from backup"
            )
        if evidence.get("backup_sha256") != backup["backup_sha256"]:
            errors.append(
                f"ledger row {target['ledger_id']}: backup fingerprint differs"
            )
        evidence_by_edge[target["edge_id"]] = evidence
    edge_ids = [t["edge_id"] for t in hub.targets]
    market_ids = [t["market_id"] for t in hub.targets]
    occupied = (
        await session.execute(
            text(RESTORE_OCCUPIED_SQL),
            {"cid": hub.container_id, "edge_ids": edge_ids, "market_ids": market_ids},
        )
    ).fetchall()
    for edge_id, parent_id, child_id in occupied:
        errors.append(
            f"edge {edge_id} (container {parent_id}, market {child_id}) already exists"
        )
    markets = {
        int(r["market_id"]): dict(r)
        for r in (
            await session.execute(
                text(RESTORE_MARKETS_SQL), {"cid": hub.container_id, "ids": market_ids}
            )
        )
        .mappings()
        .all()
    }
    for target in hub.targets:
        evidence = evidence_by_edge.get(target["edge_id"])
        if evidence is None:
            continue
        market = markets.get(target["market_id"])
        if market is None:
            errors.append(f"market {target['market_id']} does not exist")
            continue
        identity = evidence.get("identity") or {}
        classifier = evidence.get("classifier") or {}
        for column, want in (
            ("source", identity.get("source")),
            ("external_id", identity.get("external_id")),
            ("event_id", identity.get("event_id")),
            ("admitted_edge_id", identity.get("admitted_event_edge_id")),
            ("market_type", classifier.get("market_type")),
            ("name", classifier.get("name")),
        ):
            if market[column] != want:
                errors.append(
                    f"market {target['market_id']}: {column} is {market[column]!r}, "
                    f"backed up as {want!r}"
                )
    receipt_ids = sorted(
        {
            int(t["preimage"]["receipt_id"])
            for t in hub.targets
            if t["preimage"].get("receipt_id") is not None
        }
    )
    if receipt_ids:
        present = {
            int(r[0])
            for r in (
                await session.execute(text(RESTORE_RECEIPTS_SQL), {"ids": receipt_ids})
            ).fetchall()
        }
        for missing in sorted(set(receipt_ids) - present):
            errors.append(f"match receipt {missing} no longer exists")
    if errors:
        raise MemberDrift(hub.container_id, errors)

    receipt = _hub_receipt(plan, hub)
    receipt.update(
        publication_state=facts["publication_state"],
        pre_revision=facts["revision"],
        games={"before": facts["events"]},
        market_edges={"before": facts["market_edges"]},
        backup_sha256=backup["backup_sha256"],
        restores_ledger_ids=withdrawals,
        targets=[
            {
                "edge_id": t["edge_id"],
                "market_id": t["market_id"],
                "event_id": t["event_id"],
                "withdraw_ledger_id": t["ledger_id"],
                "preimage": t["preimage"],
            }
            for t in hub.targets
        ],
    )
    if not options.apply:
        receipt["would_be_revision"] = facts["revision"] + len(hub.targets)
        return receipt

    revision = facts["revision"]
    for entry, target in zip(receipt["targets"], hub.targets):
        result = await corrections.readmit_member(
            session,
            container_id=hub.container_id,
            child_type="market",
            child_id=target["market_id"],
            reason=options.reason,
            actor=options.actor,
            evidence={
                "operator": "collection_publication",
                "operation": MEMBER_RESTORE,
                "restore_from_ledger": target["ledger_id"],
                "source": plan.source(),
                "backup_sha256": backup["backup_sha256"],
                "edge_id": target["edge_id"],
                "decision_evidence": options.evidence,
            },
            expected_revision=revision,
        )
        if not (result.applied and result.revision == revision + 1):
            raise OperatorRefused(
                f"market {target['market_id']}: readmit_member did not apply "
                f"({asdict(result)})"
            )
        await _insert_preimage(session, target["preimage"], columns)
        restored = (await _preimages(session, [target["edge_id"]])).get(
            target["edge_id"]
        )
        if restored != target["preimage"]:
            raise OperatorRefused(f"edge {target['edge_id']} did not restore exactly")
        recorded = await _latest_decision(
            session, hub.container_id, target["market_id"]
        )
        if recorded.get("action") != "readmit" or recorded.get("revision") != (
            result.revision
        ):
            raise OperatorRefused(
                f"market {target['market_id']}: ledger row not read back"
            )
        revision = result.revision
        entry["readmit_ledger_id"] = int(recorded["id"])
        entry["revision_after"] = revision
    after = (
        (await session.execute(text(HUB_FACTS_SQL), {"cid": hub.container_id}))
        .mappings()
        .one()
    )
    if (
        after["revision"] != revision
        or after["events"] != facts["events"]
        or after["market_edges"] != facts["market_edges"] + len(hub.targets)
    ):
        raise OperatorRefused(f"container {hub.container_id}: restore post-state wrong")
    receipt.update(
        receipt_kind="restore_apply",
        status="prepared",
        post_revision=revision,
        games={"before": facts["events"], "after": after["events"]},
        market_edges={"before": facts["market_edges"], "after": after["market_edges"]},
        decision={
            "actor": options.actor.strip(),
            "reason": options.reason.strip(),
            "evidence": options.evidence,
        },
        later_assembly=(
            "restored rows stand until a named correction; assembly never retires "
            "a member it fails to see and, after #9990, never re-proves these"
        ),
    )
    return receipt


def _hub_failure(
    plan: MemberPlan, hub: HubPlan, exc: Exception, committing: bool
) -> dict:
    known = isinstance(exc, (OperatorRefused, corrections.CorrectionRefused))
    return {
        "operator": "collection_publication",
        "operation": plan.operation,
        "receipt_kind": "failure",
        "status": (
            "commit_outcome_unknown" if committing else "refused" if known else "failed"
        ),
        "committed": None if committing else False,
        "container_id": hub.container_id,
        "slug": hub.slug,
        "source": plan.source(),
        "expected_revision": hub.expected_revision,
        "current_revision": (
            exc.current if isinstance(exc, corrections.StaleRevision) else None
        ),
        "error": str(exc) if known else type(exc).__name__,
        "errors": list(getattr(exc, "errors", [])),
        "undo": None,
        "next_step": (
            "Read this hub's ledger and revision before anything else; never retry blind."
            if committing
            else "Nothing was written for this hub. Review the drift and issue a fresh plan."
        ),
    }


def _not_attempted(plan: MemberPlan, hub: HubPlan, why: str) -> dict:
    return {
        "operator": "collection_publication",
        "operation": plan.operation,
        "receipt_kind": "not_attempted",
        "status": "not_attempted",
        "committed": False,
        "container_id": hub.container_id,
        "slug": hub.slug,
        "source": plan.source(),
        "reason": why,
        "undo": None,
    }


async def _run_member_hub(
    options: Options, plan: MemberPlan, hub: HubPlan, session_factory
) -> tuple:
    """One hub, one transaction. Returns (receipt, ok)."""
    work = withdraw_hub if plan.operation == MEMBER_WITHDRAW else restore_hub
    committing = False
    receipt = None
    try:
        async with session_factory() as session:
            try:
                if not options.apply:
                    await session.execute(
                        text(
                            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                        )
                    )
                receipt = await work(session, plan, hub, options)
                if options.apply:
                    committing = True
                    await session.commit()
                    receipt["committed"] = True
                    receipt["committed_at"] = datetime.now(timezone.utc).isoformat()
                    receipt["status"] = "applied"
                else:
                    await session.rollback()
                return receipt, True
            except Exception as exc:
                try:
                    await session.rollback()
                except Exception:
                    # The hub's own failure is the receipt; a rollback that also
                    # fails leaves the transaction uncommitted all the same.
                    pass
                return _hub_failure(plan, hub, exc, committing), False
    except Exception as exc:
        if receipt and receipt.get("committed"):
            return {
                **receipt,
                "status": "cleanup_failed_after_commit",
                "error": type(exc).__name__,
            }, False
        return _hub_failure(plan, hub, exc, committing), False


def _write_receipt(directory: str, receipt: dict, stamp: str) -> None:
    """Exclusive create: a receipt file is never overwritten. Failure is recorded,
    never raised — the database outcome already happened and stands."""
    name = (
        f"{receipt['operation']}-c{receipt['container_id']}-"
        f"{receipt['status']}-{stamp}.json"
    )
    try:
        with open(Path(directory) / name, "x") as handle:
            json.dump(receipt, handle, default=_json_default, sort_keys=True)
        receipt["receipt_file"] = str(Path(directory) / name)
    except OSError as exc:
        receipt["receipt_file_error"] = type(exc).__name__


def _json_default(value):
    return value.isoformat()


async def run_members(
    options: Options, session_factory, plan: MemberPlan | None = None
) -> tuple:
    """Preview every hub, or apply hub by hub (one transaction each).

    An apply first previews EVERY hub read-only; any refusal there attempts
    nothing. A failure under lock rolls that hub back and leaves later hubs
    unattempted, and the document says exactly which hubs committed.
    """
    validate(options)
    plan = plan or load_member_plan(options)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    hubs: list = []
    if options.apply:
        preflight = [
            await _run_member_hub(
                replace(options, apply=False), plan, hub, session_factory
            )
            for hub in plan.hubs
        ]
        if not all(ok for _, ok in preflight):
            hubs = [
                (
                    receipt
                    if not ok
                    else _not_attempted(
                        plan, hub, "another hub failed the read-only preflight"
                    )
                )
                for hub, (receipt, ok) in zip(plan.hubs, preflight)
            ]
    if not hubs:
        failed = False
        for hub in plan.hubs:
            if failed:
                hubs.append(_not_attempted(plan, hub, "an earlier hub did not apply"))
                continue
            receipt, ok = await _run_member_hub(options, plan, hub, session_factory)
            hubs.append(receipt)
            failed = options.apply and not ok
    if options.receipt_dir:
        for receipt in hubs:
            _write_receipt(options.receipt_dir, receipt, stamp)
    committed = [h["container_id"] for h in hubs if h.get("committed") is True]
    unknown = [h["container_id"] for h in hubs if h.get("committed") is None]
    ok = all(h["status"] in ("preview", "applied") for h in hubs)
    if not options.apply:
        status = "preview" if ok else "refused"
    elif ok:
        status = "applied"
    elif committed or unknown:
        status = "partial"
    else:
        status = "refused"
    return {
        "operator": "collection_publication",
        "operation": plan.operation,
        "status": status,
        "apply": options.apply,
        "source": plan.source(),
        "committed_hubs": committed,
        "commit_unknown_hubs": unknown,
        "hubs": hubs,
    }, (0 if ok else 1)


async def _run_configured(
    options: Options, plan: MemberPlan | None = None
) -> tuple[dict, int]:
    if options.apply and os.environ.get("HEROKU_APP_NAME") != "bainluck-heavy":
        raise OperatorRefused(
            "apply requires HEROKU_APP_NAME=bainluck-heavy; attended invocation only"
        )
    if not os.environ.get("DATABASE_URL", "").strip():
        raise OperatorRefused("DATABASE_URL must be explicitly configured")
    from app.services.database import async_session_maker

    if options.operation in MEMBER_OPERATIONS:
        # main() already read and fingerprinted the file; a second read could
        # swap in bytes nobody reviewed.
        if plan is None:
            plan = load_member_plan(options)
        return await run_members(options, async_session_maker, plan)
    return await run(options, async_session_maker)


def main(argv: list[str] | None = None) -> int:
    try:
        options = parse_args(argv)
        if options.operation in MEMBER_OPERATIONS:
            # Read once, before any database: the fingerprint names these bytes.
            plan = load_member_plan(options)
            receipt, code = asyncio.run(_run_configured(options, plan))
        else:
            receipt, code = asyncio.run(_run_configured(options))
    except (OperatorRefused, corrections.CorrectionRefused) as exc:
        receipt, code = {
            "operator": "collection_publication",
            "status": "refused",
            "committed": False,
            "error": str(exc),
            "rollback": None,
        }, 2
    except Exception as exc:
        # Do not print DSNs, credentials or provider bodies from a driver error.
        receipt, code = {
            "operator": "collection_publication",
            "status": "failed",
            "committed": False,
            "error": type(exc).__name__,
            "rollback": None,
        }, 1
    try:
        print(json.dumps(receipt, default=_json_default, sort_keys=True))
    except OSError:
        # Output failed after the database outcome; the ledger is the record.
        return code or 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
