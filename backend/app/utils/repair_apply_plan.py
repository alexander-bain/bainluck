"""Bind an attended apply to the dry-run somebody actually read. Pure.

CAL-P058, answering three of C-CERT-1852's five findings at their root. The
certification's sentence is the design brief: *"neither dispatcher nor repair
accepts a dry-run receipt, expected population digest, approved market/leg IDs,
or expected verdict counts. An operator can review census A and apply a changed
census B — or call apply first — and the rail cannot distinguish either from the
attended plan."*

So this module is the receipt. A dry-run emits an :class:`ApplyPlan`: the exact
leg ids it would write, each with the EXACT prior row state it read, digested
into a content address. An apply presents that address, and the rail:

* refuses when the address does not match the artifact it can load
  (``PLAN_HASH_MISMATCH``),
* refuses when the artifact's own content no longer digests to its stored
  address (``PLAN_ARTIFACT_CORRUPT``),
* refuses to touch any row the artifact does not name
  (``MUTATION_OUTSIDE_APPROVED_SET``),
* and **re-derives nothing** — the venue is not re-asked, the population is not
  re-selected, the classifier is not re-run. The plan IS the work list.

The reason codes are not invented here. They are the ones the committed
canonical corpus ``tests/evals/fixtures/calibration_repair_retention_contract.json``
already demands — ``DRY_RUN_APPLY_IDENTITY_DRIFT``, ``MUTATION_OUTSIDE_APPROVED_SET``,
``CURSOR_SKIPS_UNPROCESSED`` — whose oracle has been passing 5/5 for two cycles
while the shipping rail violated all three. A contract nothing consumes is a
document, not a gate; :func:`evaluate_repair_contract` is this rail consuming it.

THE CURSOR HALF. ``CURSOR_SKIPS_UNPROCESSED`` is the same bug in a different
costume: the old rail paged with ``LIMIT/OFFSET`` over a population its own
writes REMOVE rows from, so advancing the offset by the page size stepped over
exactly as many untouched markets as it had just repaired. A 100-row hostile
model reproduced it — page 1 = rows 1–40, page 2 at offset 40 = rows 81–100,
``exhausted: true``, and rows 41–80 never examined. :func:`keyset_after` and
:func:`cursor_skips_unprocessed` replace the offset with a position in the sort
order, which is stable under deletion because it names WHERE the walk got to
rather than HOW MANY rows used to be behind it.

Pure module: no DB, no network, no clock. Safe to import from tasks and tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from app.utils.calibration_phase_ledger import input_fingerprint

#: Schema of the persisted plan artifact. Bumping it invalidates every artifact
#: in flight, which is correct: a plan written by different code is a plan whose
#: fields mean something different.
APPLY_PLAN_SCHEMA = "calibration-repair-apply-plan/v1"

#: Namespace for the content address, so a digest from this rail can never
#: collide with one from another fingerprinted structure in the codebase.
_PLAN_NS = "calibration-repair-apply-plan"

#: The SECOND rail to adopt this pattern (#1798, queue 362). Deliberately a
#: distinct schema and a distinct digest namespace: a binding plan and a
#: calibration plan must never be interchangeable at an apply, and two plans
#: that happen to contain the same integers must never share an address.
BINDING_APPLY_PLAN_SCHEMA = "event-team-binding-apply-plan/v1"
_BINDING_PLAN_NS = "event-team-binding-apply-plan"

#: Refusal codes. The first three are the canonical corpus's own spelling; the
#: rest are this rail's additions and are named the same way — a verb about what
#: the rail refused to do, never a bare "error".
REASON_PLAN_MISSING = "PLAN_ARTIFACT_MISSING"
REASON_PLAN_CORRUPT = "PLAN_ARTIFACT_CORRUPT"
REASON_PLAN_HASH_MISMATCH = "PLAN_HASH_MISMATCH"
REASON_PLAN_EMPTY = "PLAN_HAS_NOTHING_TO_APPLY"
REASON_OUTSIDE_APPROVED = "MUTATION_OUTSIDE_APPROVED_SET"
REASON_IDENTITY_DRIFT = "DRY_RUN_APPLY_IDENTITY_DRIFT"
REASON_CURSOR_SKIP = "CURSOR_SKIPS_UNPROCESSED"
REASON_CONCURRENT_DRIFT = "CONCURRENT_ROW_DRIFT"


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedLeg:
    """One leg the dry-run decided to write, and the row state it decided on.

    ``expected_is_winner`` / ``expected_source`` are the values the dry-run
    READ. They are carried, not re-read, because they are the compare half of
    the compare-and-set: an apply that re-read them would be asking the same
    question twice and believing the second answer, which is precisely the
    stale-read clobber C-CERT-1852 found in the restore path.
    """

    leg_id: int
    market_id: int
    verdict: str
    expected_is_winner: bool
    expected_source: str | None
    external_id: str | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "leg_id": int(self.leg_id),
            "market_id": int(self.market_id),
            "verdict": self.verdict,
            "expected_is_winner": bool(self.expected_is_winner),
            "expected_source": self.expected_source,
            "external_id": self.external_id,
        }

    #: The digest line for this leg. Every field that the apply will act on
    #: appears here, so a plan that differs in ANY of them is a different plan.
    def digest_line(self) -> str:
        return "|".join(
            [
                str(int(self.leg_id)),
                str(int(self.market_id)),
                self.verdict,
                "1" if self.expected_is_winner else "0",
                self.expected_source or "",
            ]
        )


@dataclass(frozen=True)
class ApplyPlan:
    """The reviewed dry-run, as a content-addressed object."""

    legs: tuple[PlannedLeg, ...] = ()
    #: Free-form provenance the operator reads before approving. Deliberately
    #: OUTSIDE the digest: re-describing a plan must not change its address,
    #: and nothing in here can license a write.
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def entries(self) -> tuple[Any, ...]:
        """The approved work list, under the name every plan shape shares.

        :func:`bind_apply` is the gate for BOTH rails, so it must not know what a
        row of this particular plan is called. Two gates would be two gates to
        keep honest, and the second one is always the one nobody re-reads.
        """
        return self.legs

    @property
    def market_ids(self) -> tuple[int, ...]:
        return tuple(sorted({leg.market_id for leg in self.legs}))

    @property
    def leg_ids(self) -> tuple[int, ...]:
        return tuple(sorted(leg.leg_id for leg in self.legs))

    @property
    def plan_hash(self) -> str:
        """The content address. Order-independent, field-complete.

        Sorted by leg id before digesting, so the same reviewed set produced by
        two differently-ordered scans is the same plan — an address that moved
        because a page came back in another order would train the operator to
        ignore mismatches, which is the failure mode a gate cannot survive.
        """
        lines = sorted(leg.digest_line() for leg in self.legs)
        return input_fingerprint(_PLAN_NS, str(len(lines)), *lines)

    def verdict_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for leg in self.legs:
            counts[leg.verdict] = counts.get(leg.verdict, 0) + 1
        return counts

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema": APPLY_PLAN_SCHEMA,
            "plan_hash": self.plan_hash,
            "leg_count": len(self.legs),
            "market_count": len(self.market_ids),
            "market_ids": list(self.market_ids),
            "verdict_counts": self.verdict_counts(),
            "legs": [leg.as_payload() for leg in self.legs],
            "context": dict(self.context),
        }


def build_plan(
    legs: Iterable[PlannedLeg], *, context: Mapping[str, Any] | None = None
) -> ApplyPlan:
    return ApplyPlan(legs=tuple(legs), context=dict(context or {}))


def decode_plan(raw: Any) -> tuple[ApplyPlan | None, str]:
    """``(plan, reason)`` — a payload that cannot be trusted returns ``None``.

    The stored ``plan_hash`` is re-derived from the stored legs rather than
    believed. An artifact whose address does not match its own content has been
    edited or truncated in the store, and an apply that trusted the stored
    string would be bound to nothing.
    """
    if not isinstance(raw, Mapping):
        return None, REASON_PLAN_MISSING
    if raw.get("schema") != APPLY_PLAN_SCHEMA:
        return None, REASON_PLAN_CORRUPT
    rows = raw.get("legs")
    if not isinstance(rows, list):
        return None, REASON_PLAN_CORRUPT
    legs: list[PlannedLeg] = []
    for row in rows:
        if not isinstance(row, Mapping):
            return None, REASON_PLAN_CORRUPT
        try:
            legs.append(
                PlannedLeg(
                    leg_id=int(row["leg_id"]),
                    market_id=int(row["market_id"]),
                    verdict=str(row["verdict"]),
                    expected_is_winner=bool(row["expected_is_winner"]),
                    expected_source=row.get("expected_source"),
                    external_id=row.get("external_id"),
                )
            )
        except (KeyError, TypeError, ValueError):
            return None, REASON_PLAN_CORRUPT
    ctx = raw.get("context")
    plan = ApplyPlan(legs=tuple(legs), context=dict(ctx) if isinstance(ctx, Mapping) else {})
    if plan.plan_hash != raw.get("plan_hash"):
        return None, REASON_PLAN_CORRUPT
    return plan, "ok"


def bind_apply(
    plan: ApplyPlan | None,
    *,
    decode_reason: str = "ok",
    presented_hash: str | None,
) -> tuple[bool, list[str]]:
    """May this apply proceed, and if not, exactly why. Pure.

    ``presented_hash`` is what the OPERATOR typed — the address of the plan the
    attended MC approved. It is checked against the artifact's own re-derived
    address, so all three of "no plan", "a different plan", and "an edited plan"
    are distinct named refusals instead of one silent proceed.
    """
    reasons: list[str] = []
    if plan is None:
        reasons.append(
            REASON_PLAN_CORRUPT if decode_reason == REASON_PLAN_CORRUPT else REASON_PLAN_MISSING
        )
        return False, reasons
    if not presented_hash:
        reasons.append(REASON_PLAN_HASH_MISMATCH)
        return False, reasons
    if presented_hash != plan.plan_hash:
        reasons.append(REASON_PLAN_HASH_MISMATCH)
        return False, reasons
    if not plan.entries:
        reasons.append(REASON_PLAN_EMPTY)
        return False, reasons
    return True, reasons


def approved_leg_index(plan: ApplyPlan) -> dict[int, PlannedLeg]:
    """leg_id -> the approved decision. The apply's ONLY work list."""
    return {leg.leg_id: leg for leg in plan.legs}


def mutations_outside_approved(
    plan: ApplyPlan, attempted_leg_ids: Iterable[int]
) -> list[int]:
    """Leg ids an apply tried to write that the reviewed plan never named."""
    approved = set(plan.leg_ids)
    return sorted({int(i) for i in attempted_leg_ids} - approved)


def mutations_outside_approved_keys(
    plan: Any, attempted_keys: Iterable[str]
) -> list[str]:
    """The same question for a plan whose rows are keyed by string, not by int.

    A binding row is identified by ``event:side`` — an event id alone is not a
    work item, because the two sides of one event are two independent writes and
    approving one must never license the other.
    """
    approved = set(plan.row_keys)
    return sorted({str(k) for k in attempted_keys} - approved)


# ---------------------------------------------------------------------------
# The binding plan (#1798, queue 362) — the second rail on this pattern
#
# Codex's C-APPLY-PRE BLOCK on the 180-side re-bind was not about the census,
# which was correct, nor about the approval, which Alex had given. It was that
# ``repair()`` had no ``plan_hash`` at all, so ``apply=true`` RE-DERIVED a fresh
# census and wrote whatever that found. The specimen: reviewed set [(1001, away)],
# a candidate 2002:away that appeared afterwards, and the rail wrote BOTH and then
# reported ``miswired_after=0`` — because it re-measured the world it had just
# changed, which is a true statement about the population and says nothing at all
# about whether the writes were the approved ones.
#
# So the plan carries the BEFORE id per side, and the apply is a compare-and-set
# against it. "Refuses stale by name" is that comparison: a row whose bound id has
# moved since review is a row the reviewer did not see.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedBinding:
    """One event side the dry-run decided to re-bind, with the state it read.

    ``expected_before_id`` is the compare half of the compare-and-set. It is
    carried from the dry-run and never re-read at apply time: re-reading it would
    be asking the same question twice and believing the second answer, which is
    exactly how an apply ends up bound to nothing.

    The club NAMES are carried too, and they are load-bearing rather than
    decorative — an id on its own is not reviewable, and Alex approves a list of
    clubs, not a list of integers.
    """

    event_id: int
    side: str
    expected_before_id: int
    before_name: str | None
    after_id: int
    after_name: str | None
    defect: str
    sport_id: int | None = None
    matchup: str | None = None
    commence_time: str | None = None

    @property
    def row_key(self) -> str:
        return f"{int(self.event_id)}:{self.side}"

    def as_payload(self) -> dict[str, Any]:
        return {
            "event_id": int(self.event_id),
            "side": self.side,
            "expected_before_id": int(self.expected_before_id),
            "before_name": self.before_name,
            "after_id": int(self.after_id),
            "after_name": self.after_name,
            "defect": self.defect,
            "sport_id": self.sport_id,
            "matchup": self.matchup,
            "commence_time": self.commence_time,
        }

    def digest_line(self) -> str:
        """Every field the apply ACTS on. Nothing it merely displays.

        ``matchup``/``commence_time`` are outside the digest deliberately: they
        are provenance for the reviewer, and a plan whose address moved because a
        game's start time was corrected would train the operator to wave through
        mismatches. ``before_name``/``after_name`` ARE inside it, because they are
        what the approval was given over — a plan that silently swapped a club
        name while keeping the ids must be a different plan.
        """
        return "|".join(
            [
                str(int(self.event_id)),
                self.side,
                str(int(self.expected_before_id)),
                str(int(self.after_id)),
                self.defect,
                self.before_name or "",
                self.after_name or "",
            ]
        )


@dataclass(frozen=True)
class BindingApplyPlan:
    """The reviewed 180-side re-bind, as a content-addressed object."""

    rows: tuple[PlannedBinding, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def entries(self) -> tuple[Any, ...]:
        return self.rows

    @property
    def row_keys(self) -> tuple[str, ...]:
        return tuple(sorted(r.row_key for r in self.rows))

    @property
    def event_ids(self) -> tuple[int, ...]:
        return tuple(sorted({int(r.event_id) for r in self.rows}))

    @property
    def plan_hash(self) -> str:
        lines = sorted(r.digest_line() for r in self.rows)
        return input_fingerprint(_BINDING_PLAN_NS, str(len(lines)), *lines)

    def defect_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.rows:
            counts[r.defect] = counts.get(r.defect, 0) + 1
        return counts

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema": BINDING_APPLY_PLAN_SCHEMA,
            "plan_hash": self.plan_hash,
            "row_count": len(self.rows),
            "event_count": len(self.event_ids),
            "defect_counts": self.defect_counts(),
            "rows": [r.as_payload() for r in self.rows],
            "context": dict(self.context),
        }


def build_binding_plan(
    rows: Iterable[PlannedBinding], *, context: Mapping[str, Any] | None = None
) -> BindingApplyPlan:
    return BindingApplyPlan(rows=tuple(rows), context=dict(context or {}))


def decode_binding_plan(raw: Any) -> tuple[BindingApplyPlan | None, str]:
    """``(plan, reason)``. The stored address is RE-DERIVED, never believed."""
    if not isinstance(raw, Mapping):
        return None, REASON_PLAN_MISSING
    if raw.get("schema") != BINDING_APPLY_PLAN_SCHEMA:
        return None, REASON_PLAN_CORRUPT
    raw_rows = raw.get("rows")
    if not isinstance(raw_rows, list):
        return None, REASON_PLAN_CORRUPT
    rows: list[PlannedBinding] = []
    for row in raw_rows:
        if not isinstance(row, Mapping):
            return None, REASON_PLAN_CORRUPT
        if row.get("side") not in ("home", "away"):
            return None, REASON_PLAN_CORRUPT
        try:
            rows.append(
                PlannedBinding(
                    event_id=int(row["event_id"]),
                    side=str(row["side"]),
                    expected_before_id=int(row["expected_before_id"]),
                    before_name=row.get("before_name"),
                    after_id=int(row["after_id"]),
                    after_name=row.get("after_name"),
                    defect=str(row["defect"]),
                    sport_id=row.get("sport_id"),
                    matchup=row.get("matchup"),
                    commence_time=row.get("commence_time"),
                )
            )
        except (KeyError, TypeError, ValueError):
            return None, REASON_PLAN_CORRUPT
    ctx = raw.get("context")
    plan = BindingApplyPlan(
        rows=tuple(rows), context=dict(ctx) if isinstance(ctx, Mapping) else {}
    )
    if plan.plan_hash != raw.get("plan_hash"):
        return None, REASON_PLAN_CORRUPT
    return plan, "ok"


# ---------------------------------------------------------------------------
# The cursor
# ---------------------------------------------------------------------------


def keyset_after(rows: Sequence[Any], examined: int) -> dict[str, Any] | None:
    """The resume position: WHERE the walk stopped, never HOW MANY it saw.

    Returns the sort key of the LAST EXAMINED row — not the last returned one.
    A page that stopped early on the wall clock must resume at the row it
    actually reached, or the untouched tail of its own page is skipped by the
    resume, which is the offset bug rebuilt one level down.

    ``None`` means nothing was examined, so there is nothing to advance past.
    """
    if examined <= 0 or not rows:
        return None
    last = rows[min(examined, len(rows)) - 1]
    date = getattr(last, "resolution_date", None)
    return {
        "after_date": date.isoformat() if hasattr(date, "isoformat") else date,
        "after_id": int(getattr(last, "market_id")),
    }


def cursor_skips_unprocessed(
    *,
    selected_ids: Sequence[int],
    processed_ids: Sequence[int],
    next_after_id: int | None,
) -> bool:
    """Would resuming here step over a selected row this page never examined?

    The canonical corpus's ``repair-cap-cursor-skip`` oracle, in the rail's own
    terms. It is the ONE property a resumable bounded walk has to have, and the
    offset form could not have it: an offset counts rows that were there when
    the page was taken, and this rail's whole purpose is to remove them.
    """
    if next_after_id is None:
        return False
    remaining = [int(i) for i in selected_ids if int(i) not in set(map(int, processed_ids))]
    if not remaining:
        return False
    return int(next_after_id) >= max(remaining)


def evaluate_repair_contract(
    *,
    candidate_ids: Sequence[int],
    processed_ids: Sequence[int],
    approved_ids: Sequence[int],
    mutated_ids: Sequence[int],
    dry_run_ids: Sequence[int] | None,
    next_cursor: int | None,
) -> dict[str, Any]:
    """This rail, scored by the canonical corpus's own oracle shape.

    Deliberately mirrors ``scripts/evals/calibration_repair_retention_contract``'s
    ``_repair`` so a specimen can be run against the SHIPPING rail's telemetry
    rather than against a model of it. The oracle passing 5/5 while the rail
    violated the contract is the exact gap C-CERT-1852 named; this closes it by
    making the rail's own return values the thing under test.
    """
    reasons: list[str] = []
    approved = set(map(int, approved_ids))
    mutated = [int(i) for i in mutated_ids]
    if any(i not in approved for i in mutated):
        reasons.append(REASON_OUTSIDE_APPROVED)
    if dry_run_ids is not None and mutated and sorted(mutated) != sorted(map(int, dry_run_ids)):
        reasons.append(REASON_IDENTITY_DRIFT)
    if cursor_skips_unprocessed(
        selected_ids=candidate_ids,
        processed_ids=processed_ids,
        next_after_id=next_cursor,
    ):
        reasons.append(REASON_CURSOR_SKIP)
    action = "REFUSE" if reasons else ("APPLY" if mutated else "NOOP")
    return {
        "action": action,
        "allowed_mutations": [] if reasons else mutated,
        "reason_codes": sorted(set(reasons)),
    }
