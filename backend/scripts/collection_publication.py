#!/usr/bin/env python3
"""Preview or explicitly publish/withdraw one reviewed NFL/MLB hub (#9916).

No target discovery, assembly, flag changes or implicit publication. Authority's
correction helpers own all writes; this caller owns commit/rollback. See
``docs/collection-publication-operator.md`` for receipt and rollback limits.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
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
from app.utils.container_presentation import edition_for_slug  # noqa: E402


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


def validate(options: Options) -> None:
    if options.container_id is None and not options.slug:
        raise OperatorRefused("an explicit --container-id or --slug is required")
    if options.container_id is not None and options.container_id <= 0:
        raise OperatorRefused("container-id must be positive")
    if options.slug is not None and (
        not options.slug or options.slug != options.slug.strip()
    ):
        raise OperatorRefused("slug must be nonblank and exact (no surrounding spaces)")
    if options.expected_revision is not None and options.expected_revision < 0:
        raise OperatorRefused("expected-revision must be nonnegative")
    if options.operation not in (None, "publish", "withdraw"):
        raise OperatorRefused("operation must be publish or withdraw")
    if options.apply:
        if options.container_id is None or options.slug is None:
            raise OperatorRefused(
                "apply requires BOTH the reviewed container-id and slug"
            )
        if options.operation is None or options.expected_revision is None:
            raise OperatorRefused("apply requires operation and expected-revision")
        for name, value in (("actor", options.actor), ("reason", options.reason)):
            if not isinstance(value, str) or not value.strip():
                raise OperatorRefused(f"apply requires nonblank {name}")
        if len(options.actor.strip()) > 64:
            raise OperatorRefused(
                "actor must fit the existing 64-character ledger field"
            )
        if not isinstance(options.evidence, dict) or not options.evidence:
            raise OperatorRefused("apply requires a nonempty JSON object as evidence")
        try:
            json.dumps(options.evidence, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise OperatorRefused(
                "evidence must contain only valid JSON values"
            ) from exc


def parse_args(argv: list[str] | None = None) -> Options:
    parser = Parser(description=__doc__)
    parser.add_argument("--container-id", action=SingleValue, type=int)
    parser.add_argument("--slug", action=SingleValue)
    parser.add_argument(
        "--operation", action=SingleValue, choices=("publish", "withdraw")
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-revision", action=SingleValue, type=int)
    parser.add_argument("--actor", action=SingleValue)
    parser.add_argument("--reason", action=SingleValue)
    parser.add_argument(
        "--evidence",
        action=SingleValue,
        help="nonempty JSON object recorded in the correction ledger",
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
    options = Options(**{**vars(args), "evidence": evidence})
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


async def _run_configured(options: Options) -> tuple[dict, int]:
    if options.apply and os.environ.get("HEROKU_APP_NAME") != "bainluck-heavy":
        raise OperatorRefused(
            "apply requires HEROKU_APP_NAME=bainluck-heavy; attended invocation only"
        )
    if not os.environ.get("DATABASE_URL", "").strip():
        raise OperatorRefused("DATABASE_URL must be explicitly configured")
    from app.services.database import async_session_maker

    return await run(options, async_session_maker)


def main(argv: list[str] | None = None) -> int:
    try:
        options = parse_args(argv)
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
    print(json.dumps(receipt, default=lambda value: value.isoformat(), sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
