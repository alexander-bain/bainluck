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
#:
#: **v2 (queue 364, C-APPLY-PRE-R2 finding 2).** The address scheme changed — the
#: digest is length-prefixed instead of ``"|"``-joined, so a v1 artifact's stored
#: ``plan_hash`` is no longer the address of its own content. Bumping is what makes
#: that refusal say *the scheme moved* rather than *somebody edited the file*: both
#: fail closed, but only one of them tells the operator what to do next. Every v1
#: artifact must be re-derived and re-approved. That is the intended cost.
APPLY_PLAN_SCHEMA = "calibration-repair-apply-plan/v2"

#: Namespace for the content address, so a digest from this rail can never
#: collide with one from another fingerprinted structure in the codebase.
_PLAN_NS = "calibration-repair-apply-plan"

#: The SECOND rail to adopt this pattern (#1798, queue 362). Deliberately a
#: distinct schema and a distinct digest namespace: a binding plan and a
#: calibration plan must never be interchangeable at an apply, and two plans
#: that happen to contain the same integers must never share an address.
BINDING_APPLY_PLAN_SCHEMA = "event-team-binding-apply-plan/v2"
_BINDING_PLAN_NS = "event-team-binding-apply-plan"

#: The THIRD rail (#1796/#1902, queue 363) — attended event CREATE from venue
#: truth. Same reasoning for the separate schema and namespace: a create plan and
#: a re-bind plan must never be interchangeable at an apply.
#:
#: **v3 (queue 368, C-APPLY-PRE-CREATE-R2 finding 1).** ``sport_id`` is now inside
#: the address. It is a field the create WRITES and it was outside the digest, so
#: editing it in an artifact left the stored ``plan_hash`` still correct and the
#: plan decoded clean — a reviewed game could be created under a sport nobody
#: approved. That is not hypothetical here: MLB carries TWO team registries
#: (33178 and 53232, all 30 clubs duplicated across them — #1798), so the wrong
#: sport_id binds the new event to the wrong copy of the club. Bumping says *the
#: scheme moved* rather than *somebody edited the file*. Every v2 create artifact
#: must be re-derived and re-approved, including the two GREEN at queue 367.
CREATE_PLAN_SCHEMA = "event-create-from-truth-plan/v3"
_CREATE_PLAN_NS = "event-create-from-truth-plan"

#: Refusal codes. The first three are the canonical corpus's own spelling; the
#: rest are this rail's additions and are named the same way — a verb about what
#: the rail refused to do, never a bare "error".
REASON_PLAN_MISSING = "PLAN_ARTIFACT_MISSING"
REASON_PLAN_CORRUPT = "PLAN_ARTIFACT_CORRUPT"
REASON_PLAN_HASH_MISMATCH = "PLAN_HASH_MISMATCH"
#: "I could not obtain a trustworthy read RIGHT NOW" — the store was unreachable,
#: the read raised, or the artifact aged out. Distinct from MISSING on purpose
#: (C-APPLY-PRE-R2 finding 1, gotcha #53): MISSING tells an operator the plan never
#: existed and the correct next move is to generate one, which is exactly the wrong
#: move during a store outage. Refuses the apply either way; only the sentence differs.
REASON_PLAN_UNREADABLE = "PLAN_ARTIFACT_UNREADABLE"
REASON_PLAN_EMPTY = "PLAN_HAS_NOTHING_TO_APPLY"
REASON_OUTSIDE_APPROVED = "MUTATION_OUTSIDE_APPROVED_SET"
REASON_IDENTITY_DRIFT = "DRY_RUN_APPLY_IDENTITY_DRIFT"
REASON_CURSOR_SKIP = "CURSOR_SKIPS_UNPROCESSED"
REASON_CONCURRENT_DRIFT = "CONCURRENT_ROW_DRIFT"

#: CREATE-rail refusals. ``TRUTH_ID_ALREADY_PRESENT`` is the create analogue of
#: ``CONCURRENT_ROW_DRIFT``: it retires ONE row and never its siblings, because
#: the ordinary pipeline creating a game between review and apply is the system
#: working, not a fault. ``TRUTH_ID_SET_DRIFT`` is the artifact's own gate.
REASON_TRUTH_ID_PRESENT = "TRUTH_ID_ALREADY_PRESENT"
REASON_TRUTH_SET_DRIFT = "TRUTH_ID_SET_DRIFT"

#: #2016: the create-rail analogue of ``MAPPING_ROW_LOCK_TIMEOUT`` — this row was
#: not created because another transaction holds a conflicting lock and the rail
#: declined to keep waiting past the request wall. It retires alone; its siblings
#: continue; the next invocation of the SAME plan_hash finds it still missing and
#: still actionable.
REASON_CREATE_ROW_LOCK_TIMEOUT = "CREATE_ROW_LOCK_TIMEOUT"

#: #2016: the binding rail writes its whole reviewed plan in ONE transaction, so
#: it has no per-row retirement to offer — a contended row aborts the transaction
#: and nothing is committed. That is a REFUSAL with a name, not a hang: the plan
#: is untouched and the same plan_hash can be re-applied once contention clears.
REASON_BINDING_LOCK_TIMEOUT = "EVENT_BINDING_LOCK_TIMEOUT"

#: The three refusals that mean "there is no plan object to bind to". Every one of
#: them stops the apply; they exist separately so the REASON an operator is handed
#: is the one they can act on.
_NO_PLAN_REASONS = frozenset({REASON_PLAN_MISSING, REASON_PLAN_CORRUPT, REASON_PLAN_UNREADABLE})


def digest_fields(*fields: Any) -> str:
    """Encode fields into ONE line that no field's content can forge. Pure.

    ``"|".join([...])`` is not injective over free text, and every plan digest in
    this module used it. C-APPLY-PRE-R2 finding 2 is the specimen::

        before="Old|Club", after="New"    -> "Old|Club|New"
        before="Old",      after="Club|New" -> "Old|Club|New"

    Two materially different reviewed approvals — different club names, shown to
    Alex — collapse onto one content address. The numeric ids were never at risk,
    which is precisely why this survived: the fields it corrupts are the ones a
    human reads, and the address is supposed to be the promise that what the human
    read is what the apply writes.

    Length-prefixing each field makes the encoding prefix-free, so the delimiter
    carries no meaning a value can imitate: ``"Old|Club"`` encodes as ``8:Old|Club``
    and ``"Old"`` as ``3:Old``, which differ in their first character.

    **ABSENT is not EMPTY (C-APPLY-PRE-CREATE finding 1, generalized).** The first
    version of this encoder wrote ``"" if value is None else str(value)``, so a field
    the plan does not carry and a field the plan carries as an empty string produced
    the same ``0:`` — and the field that finding lands on is ``sport_id``, which
    decides WHICH COPY of a club a created game hangs off (MLB has two registries,
    33178 / 53232, all 30 clubs duplicated — #1798). Adding a field to a digest does
    not make the digest injective over it if the encoder still collapses its absence
    onto one of its values; that is the same defect as leaving it out, one layer down.
    ``None`` therefore encodes as the sentinel length ``-1``, which no real length can
    equal, so no value can imitate absence.

    Changing an encoder changes every address it produces. Verified before shipping:
    the three reviewed ``/v3`` CREATE addresses (pop1 ``5edaa440…``, pop2
    ``f1a43a33…``, pop3 ``cdc2bae9…`` — the last carrying Alex's 2026-08-18 MC) are
    BYTE-IDENTICAL under this change, because no digest field in any of their rows is
    ``None``. An encoder change that silently re-addressed an approved plan would
    invalidate the approval, which is the opposite of what an address is for.
    """
    parts: list[str] = []
    for value in fields:
        if value is None:
            parts.append("-1:")
            continue
        text = str(value)
        parts.append(f"{len(text)}:{text}")
    return "|".join(parts)


def plan_reason_for_read(status: str, *, error_class: str | None = None) -> str:
    """Translate a durable :class:`EnvelopeRead` status into a refusal reason. Pure.

    The whole point of the durable layer's careful classification — ``malformed``
    with ``ChecksumMismatch`` is not ``missing`` — was being thrown away one frame
    later, where every non-ok read became the prose string ``"plan artifact
    unreadable: <status>"``. ``bind_apply`` matches on the corrupt CONSTANT, so
    prose fell through to ``PLAN_ARTIFACT_MISSING`` and a torn artifact was
    reported to the attended operator as one that never existed.

    Kept as a pure function rather than inlined in each rail because there are two
    rails (``repair_kalshi_fabricated_loss``, ``repair_event_team_binding``) and
    both had the same defect. One shared eligibility predicate, one contract test.
    """
    from app.utils import durable_state as _ds

    if status == _ds.MISSING:
        return REASON_PLAN_MISSING
    if status in (_ds.MALFORMED, _ds.WRONG_TYPE, _ds.WRONG_VERSION):
        # The artifact IS there and cannot be trusted: torn write, wrong shape, or
        # written under a superseded address scheme. All three are "do not apply
        # this, and do not assume nothing was ever approved".
        return REASON_PLAN_CORRUPT
    if status in (_ds.UNAVAILABLE, _ds.STALE):
        return REASON_PLAN_UNREADABLE
    # An unrecognised status is not evidence of absence either. Fail into the
    # reading that does not tell an operator to go make a new plan.
    return REASON_PLAN_UNREADABLE


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
        return digest_fields(
            int(self.leg_id),
            int(self.market_id),
            self.verdict,
            "1" if self.expected_is_winner else "0",
            self.expected_source or "",
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
        # Pass the loader's own classification through. It used to be narrowed to
        # "corrupt, or else missing", which meant every reading the loader could
        # not spell as the exact corrupt constant — including a checksum failure
        # arriving as prose — was reported as an artifact that never existed.
        reasons.append(decode_reason if decode_reason in _NO_PLAN_REASONS else REASON_PLAN_MISSING)
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

        ``sport_id`` is correctly OUTSIDE here, and that is not an inconsistency
        with the CREATE rail, which digests it (queue 368). This rail rewrites
        team ids on an event that already exists and already has a sport; it
        never writes ``sport_id``, so the field is provenance. The create rail
        writes it. Same test applied to both, opposite answers — do not
        "harmonise" these by copying either decision across.
        """
        return digest_fields(
            int(self.event_id),
            self.side,
            int(self.expected_before_id),
            int(self.after_id),
            self.defect,
            self.before_name or "",
            self.after_name or "",
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
# The CREATE plan (#1796/#1902, queue 363) — the third rail on this pattern
#
# Alex, 2026-08-17, ruling the four MC decisions: attended event-CREATE from
# venue truth is APPROVED, as the pattern — provider anchors, plan artifact,
# pre-cert, always attended.
#
# A create differs from the two update rails in exactly one structural way, and
# every difference below follows from it: THE BEFORE STATE IS ABSENCE. There is
# no ``expected_before_id`` to compare against, because the thing being compared
# does not exist. The compare half of the compare-and-set is therefore the
# existence check itself, and it MUST happen inside the create transaction — a
# check before the transaction is a read of a world the write then changes,
# which is the #1798 defect restated in the create direction.
#
# Two rules this rail inherits from what the population-2 census cost to learn:
#
#   1. **Keyed on the truth id, never on (teams, date).** A doubleheader is two
#      real games with identical clubs on an identical date. An existence check
#      keyed on the matchup would refuse the second one as a duplicate of the
#      first, and the 328-game set contains doubleheaders. R5 hit this blind spot
#      and R6 answered it in the merge primitive; the create rail must not have
#      to learn it a third time.
#   2. **The reviewed object is a SET OF IDS, not a count.** A count is a claim
#      about the world's current state that the ordinary pipeline repairs on its
#      own, so it expires while nothing is wrong (the Aug 10-12 ``2/14 -> 16/0``
#      inversion). :func:`create_gate` therefore compares SETS.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedCreate:
    """One game the dry-run decided to create, with the truth it read.

    ``truth_id`` is the provider's own id for the game (ESPN's, for the MLB
    population) and is this row's whole identity — it is the existence key, the
    row key, and the anchor a reviewer can dereference themselves.
    """

    truth_id: str
    provider: str
    home_team_id: int
    away_team_id: int
    home_name: str
    away_name: str
    commence_time: str
    sport_id: int | None = None
    label: str | None = None

    @property
    def row_key(self) -> str:
        return f"{self.provider}:{self.truth_id}"

    def as_payload(self) -> dict[str, Any]:
        return {
            "truth_id": self.truth_id,
            "provider": self.provider,
            "home_team_id": int(self.home_team_id),
            "away_team_id": int(self.away_team_id),
            "home_name": self.home_name,
            "away_name": self.away_name,
            "commence_time": self.commence_time,
            "sport_id": self.sport_id,
            "label": self.label,
        }

    def digest_line(self) -> str:
        """Every field the create WRITES.

        ``commence_time`` is INSIDE the address here, where the binding rail
        deliberately left it outside. That is not an inconsistency: the binding
        rail only ever displayed the kickoff, so a corrected time there must not
        invalidate a reviewed plan, whereas here the timestamp is a value being
        written into a new row. A create plan whose start times changed since
        review is a create plan the reviewer did not approve.

        ``sport_id`` is INSIDE (queue 368). It was outside, and it is written by
        the create, so the docstring above this line was false: a mutation to it
        retained the approved ``plan_hash`` and decoded clean. MLB has two team
        registries (33178 / 53232, all 30 clubs duplicated — #1798), so that is
        the difference between creating the game against the reviewed club rows
        and against their twins. The test for whether a field belongs here is not
        "is it interesting" but "does the apply WRITE it".

        ``label`` stays out — it is prose assembled for the reviewer from the
        fields above, and re-wording it must not mint a new address.
        """
        return digest_fields(
            self.provider,
            self.truth_id,
            int(self.home_team_id),
            int(self.away_team_id),
            self.home_name,
            self.away_name,
            self.commence_time,
            # NOT `... else ""`. That collapsed an absent sport_id onto an empty one
            # and handed both the same address — a field inside the digest that the
            # digest could not distinguish from its own absence. `digest_fields`
            # encodes None as the `-1:` sentinel; let it.
            int(self.sport_id) if self.sport_id is not None else None,
        )


@dataclass(frozen=True)
class CreatePlan:
    """The reviewed CREATE set, as a content-addressed object."""

    rows: tuple[PlannedCreate, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def entries(self) -> tuple[Any, ...]:
        return self.rows

    @property
    def row_keys(self) -> tuple[str, ...]:
        return tuple(sorted(r.row_key for r in self.rows))

    @property
    def truth_ids(self) -> tuple[str, ...]:
        return tuple(sorted({r.truth_id for r in self.rows}))

    @property
    def plan_hash(self) -> str:
        lines = sorted(r.digest_line() for r in self.rows)
        return input_fingerprint(_CREATE_PLAN_NS, str(len(lines)), *lines)

    def duplicate_truth_ids(self) -> list[str]:
        """Truth ids named more than once. Must be empty: two plan rows for one
        provider id would create the same game twice."""
        seen: dict[str, int] = {}
        for r in self.rows:
            seen[r.truth_id] = seen.get(r.truth_id, 0) + 1
        return sorted(k for k, n in seen.items() if n > 1)

    def doubleheaders(self) -> list[str]:
        """Truth ids sharing a (clubs, **UTC** calendar date) tuple with another row.

        NOT a defect — reported so the reviewer knows the plan contains them and
        so a future existence check keyed on the matchup fails loudly here rather
        than silently dropping the second game of a twin bill.

        Keyed on the UTC date, which OVER-reports: two night games on consecutive
        Eastern dates straddle a single UTC date and are flagged as a twin bill
        (the 328-row plan's only hit is exactly this — Dodgers @ Yankees at
        00:08Z and 23:20Z on 2026-07-19, i.e. the evenings of July 18 and 19 ET).
        Left as-is on purpose: this is a REVIEW flag, and a flag that over-reports
        costs a reviewer one glance, while one that under-reports loses a real
        game. The property that actually protects the twin bill is the row key
        being the truth id, and that holds regardless of what this reports.
        """
        buckets: dict[tuple[int, int, str], list[str]] = {}
        for r in self.rows:
            key = (int(r.home_team_id), int(r.away_team_id), r.commence_time[:10])
            buckets.setdefault(key, []).append(r.truth_id)
        return sorted(tid for ids in buckets.values() if len(ids) > 1 for tid in ids)

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema": CREATE_PLAN_SCHEMA,
            "plan_hash": self.plan_hash,
            "row_count": len(self.rows),
            "truth_id_count": len(self.truth_ids),
            "duplicate_truth_ids": self.duplicate_truth_ids(),
            "doubleheader_truth_ids": self.doubleheaders(),
            "rows": [r.as_payload() for r in self.rows],
            "context": dict(self.context),
        }


def build_create_plan(
    rows: Iterable[PlannedCreate], *, context: Mapping[str, Any] | None = None
) -> CreatePlan:
    return CreatePlan(rows=tuple(rows), context=dict(context or {}))


def decode_create_plan(raw: Any) -> tuple[CreatePlan | None, str]:
    """``(plan, reason)``. The stored address is RE-DERIVED, never believed."""
    if not isinstance(raw, Mapping):
        return None, REASON_PLAN_MISSING
    if raw.get("schema") != CREATE_PLAN_SCHEMA:
        return None, REASON_PLAN_CORRUPT
    raw_rows = raw.get("rows")
    if not isinstance(raw_rows, list):
        return None, REASON_PLAN_CORRUPT
    rows: list[PlannedCreate] = []
    for row in raw_rows:
        if not isinstance(row, Mapping):
            return None, REASON_PLAN_CORRUPT
        try:
            rows.append(
                PlannedCreate(
                    truth_id=str(row["truth_id"]),
                    provider=str(row["provider"]),
                    home_team_id=int(row["home_team_id"]),
                    away_team_id=int(row["away_team_id"]),
                    home_name=str(row["home_name"]),
                    away_name=str(row["away_name"]),
                    commence_time=str(row["commence_time"]),
                    # REQUIRED and coerced (queue 368). It was `row.get(...)`,
                    # which never raises: a missing sport_id decoded as None and
                    # a garbage one decoded as itself, so the corrupt-artifact
                    # path could not see either. Subscript + int() puts both in
                    # the `except` below, where they become PLAN_ARTIFACT_CORRUPT.
                    sport_id=int(row["sport_id"]),
                    label=row.get("label"),
                )
            )
        except (KeyError, TypeError, ValueError):
            return None, REASON_PLAN_CORRUPT
    ctx = raw.get("context")
    plan = CreatePlan(
        rows=tuple(rows), context=dict(ctx) if isinstance(ctx, Mapping) else {}
    )
    if plan.plan_hash != raw.get("plan_hash"):
        return None, REASON_PLAN_CORRUPT
    if plan.duplicate_truth_ids():
        return None, REASON_PLAN_CORRUPT
    return plan, "ok"


def create_gate(
    plan: CreatePlan, rederived_missing_ids: Iterable[str]
) -> tuple[bool, list[str]]:
    """The truth-id gate, spelled exactly as the artifact states it.

    *"Apply may proceed only when a re-derivation at apply time produces a
    MISSING id set whose intersection with THIS set is THIS set."*

    In other words every reviewed id must STILL be missing. An id that has since
    been created is not an error in the world — it is the ordinary pipeline doing
    its job — but it IS an id the plan may no longer act on, and it is named
    rather than skipped, because "the plan shrank and nobody said so" is how a
    reviewed population quietly becomes a different one.

    Returns ``(ok, no_longer_missing)``. Callers drop the named rows and keep
    their siblings; a wholesale refusal would let one upstream create cancel 327
    approved ones.
    """
    still_missing = {str(i) for i in rederived_missing_ids}
    no_longer = sorted(set(plan.truth_ids) - still_missing)
    return (not no_longer), no_longer


# ---------------------------------------------------------------------------
# The mapping repair plan (#1918, queues 363/370) — the fourth rail
#
# ``team_identity_mapping`` rows whose ``team_id`` points at a DIFFERENT club
# than the one ``source_name`` names. Alex approved 133; three were held out
# because a live ``before`` check would abort on them and one was never
# reviewed, leaving the 130 staged at
# ``ARTIFACT-Q370-MAPPING-REPAIR-PLAN-130-STAGED.json``.
#
# HOW THIS DIFFERS FROM THE CREATE RAIL, WHICH IS THE PATTERN IT COPIES
#
# The create rail's compare half is an EXISTENCE check, because the row it
# writes does not exist yet. Here the row does exist and carries a known
# ``before.team_id``, so the compare half is an ordinary compare-and-set — and
# it belongs INSIDE the UPDATE for the same reason the existence check belongs
# inside the INSERT: a check performed in front of the statement reads a world
# the statement then changes. ``resolve_team`` step 3 AUTO-REGISTERS its hit, so
# these rows are written by live traffic, and three of the original 133 were
# observed rotating between review and apply. That is not a hypothetical race.
# ---------------------------------------------------------------------------

#: Bumped to /v2 by the length-prefixed digest (C-APPLY-PRE-MAPPING). A /v1
#: artifact now decodes as CORRUPT, which is the fix working: its address was
#: minted by an encoder that could not distinguish one field's content from a
#: field boundary, so the address did not mean what the reviewer was told.
MAPPING_REPAIR_PLAN_SCHEMA = "team-identity-mapping-repair-plan/v2"
_MAPPING_PLAN_NS = "team-identity-mapping-repair-plan"

#: The CAS lost. Either the row's ``team_id`` is no longer the reviewed
#: ``before`` — ``resolve_team`` re-registered it, which is the live rotation
#: the three held-out rows exhibit — or the row is gone. One reason, because the
#: operator's next move is the same for both: re-derive and get it re-reviewed.
REASON_MAPPING_BEFORE_DRIFT = "MAPPING_BEFORE_TEAM_DRIFT"

#: The reviewed mapping id has no row at all at apply time.
REASON_MAPPING_ROW_MISSING = "MAPPING_ROW_MISSING"

#: #2016: the row is not drifted and not missing — somebody ELSE is holding a
#: lock on it and the rail declined to keep waiting. A third distinct reading,
#: for the same reason MISSING and CORRUPT are distinct (gotcha #53): the
#: operator's next move is "re-invoke, it will still be actionable", which is
#: the opposite of the re-derive-and-re-review that drift demands. Measured in
#: queue 377 against a Celery transaction held open 8m59s.
REASON_MAPPING_ROW_LOCK_TIMEOUT = "MAPPING_ROW_LOCK_TIMEOUT"


@dataclass(frozen=True)
class PlannedMappingRepair:
    """One mapping the dry-run decided to re-point, and the state it decided on.

    ``before_team_id`` is the compare half of the compare-and-set. It is
    CARRIED, not re-read: an apply that re-read it would be asking the same
    question the review already answered, and would answer it from a world that
    has moved.
    """

    mapping_id: int
    source: str
    sport_key: str
    source_name: str
    before_team_id: int
    before_club: str
    after_team_id: int
    after_club: str

    @property
    def row_key(self) -> str:
        """One mapping row is one work item, so its id IS its key.

        Unlike the binding rail — where an event has two independently
        approvable sides — there is nothing here to compose a key from.
        """
        return str(self.mapping_id)

    def as_payload(self) -> dict[str, Any]:
        return {
            "mapping_id": int(self.mapping_id),
            "source": self.source,
            "sport_key": self.sport_key,
            "source_name": self.source_name,
            "before": {"team_id": int(self.before_team_id), "club": self.before_club},
            "after": {"team_id": int(self.after_team_id), "club": self.after_club},
        }

    def digest_line(self) -> str:
        """The eight fields the reviewer read, length-prefixed.

        These are exactly the eight the queue-363 deriver already addressed on —
        deliberately unchanged, so the ONLY difference between the old address
        and the new one is the encoding. Adding a ninth field here would make it
        impossible to say whether a changed address meant "the encoder was
        fixed" or "the plan is about something else now".

        ``club`` names are inside even though the apply writes only
        ``team_id``, and that is the point rather than an oversight: the club
        names are what a human read in order to approve, and an address exists
        to promise that what the human read is what the apply writes. They are
        also the free-text fields — the ones the old ``"|".join`` could not
        encode injectively.
        """
        return digest_fields(
            int(self.mapping_id),
            self.source,
            self.sport_key,
            self.source_name,
            int(self.before_team_id),
            self.before_club,
            int(self.after_team_id),
            self.after_club,
        )


@dataclass(frozen=True)
class MappingRepairPlan:
    """The reviewed re-point set, as a content-addressed object."""

    rows: tuple[PlannedMappingRepair, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def entries(self) -> tuple[Any, ...]:
        return self.rows

    @property
    def row_keys(self) -> tuple[str, ...]:
        return tuple(sorted(r.row_key for r in self.rows))

    @property
    def mapping_ids(self) -> tuple[int, ...]:
        return tuple(sorted({int(r.mapping_id) for r in self.rows}))

    @property
    def plan_hash(self) -> str:
        lines = sorted(r.digest_line() for r in self.rows)
        return input_fingerprint(_MAPPING_PLAN_NS, str(len(lines)), *lines)

    def duplicate_mapping_ids(self) -> list[int]:
        """Mapping ids named more than once. Must be empty.

        Two plan rows for one mapping would be two different re-points of the
        same row, and whichever ran second would silently win — an outcome no
        reviewer chose, because the artifact shows both.
        """
        seen: dict[int, int] = {}
        for r in self.rows:
            seen[int(r.mapping_id)] = seen.get(int(r.mapping_id), 0) + 1
        return sorted(k for k, n in seen.items() if n > 1)

    def self_pointing_rows(self) -> list[int]:
        """Rows whose ``after`` equals their ``before``. Must be empty.

        A no-op WRITE is not harmless here: the CAS cannot distinguish it from a
        successful repair, so it would report as applied while nothing changed.
        """
        return sorted(
            int(r.mapping_id) for r in self.rows
            if int(r.before_team_id) == int(r.after_team_id)
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema": MAPPING_REPAIR_PLAN_SCHEMA,
            "plan_hash": self.plan_hash,
            "row_count": len(self.rows),
            "mapping_id_count": len(self.mapping_ids),
            "duplicate_mapping_ids": self.duplicate_mapping_ids(),
            "self_pointing_mapping_ids": self.self_pointing_rows(),
            "rows": [r.as_payload() for r in self.rows],
            "context": dict(self.context),
        }


def build_mapping_repair_plan(
    rows: Iterable[PlannedMappingRepair], *, context: Mapping[str, Any] | None = None
) -> MappingRepairPlan:
    return MappingRepairPlan(rows=tuple(rows), context=dict(context or {}))


def decode_mapping_repair_plan(raw: Any) -> tuple[MappingRepairPlan | None, str]:
    """``(plan, reason)``. The stored address is RE-DERIVED, never believed."""
    if not isinstance(raw, Mapping):
        return None, REASON_PLAN_MISSING
    if raw.get("schema") != MAPPING_REPAIR_PLAN_SCHEMA:
        return None, REASON_PLAN_CORRUPT
    raw_rows = raw.get("rows")
    if not isinstance(raw_rows, list):
        return None, REASON_PLAN_CORRUPT
    rows: list[PlannedMappingRepair] = []
    for row in raw_rows:
        if not isinstance(row, Mapping):
            return None, REASON_PLAN_CORRUPT
        before = row.get("before")
        after = row.get("after")
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            return None, REASON_PLAN_CORRUPT
        try:
            # Subscript + coerce, never `.get()`: a missing field must land in
            # the `except` and become PLAN_ARTIFACT_CORRUPT, not decode as None
            # and sail past the digest (the queue-368 sport_id lesson).
            rows.append(
                PlannedMappingRepair(
                    mapping_id=int(row["mapping_id"]),
                    source=str(row["source"]),
                    sport_key=str(row["sport_key"]),
                    source_name=str(row["source_name"]),
                    before_team_id=int(before["team_id"]),
                    before_club=str(before["club"]),
                    after_team_id=int(after["team_id"]),
                    after_club=str(after["club"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            return None, REASON_PLAN_CORRUPT
    ctx = raw.get("context")
    plan = MappingRepairPlan(
        rows=tuple(rows), context=dict(ctx) if isinstance(ctx, Mapping) else {}
    )
    if plan.plan_hash != raw.get("plan_hash"):
        return None, REASON_PLAN_CORRUPT
    if plan.duplicate_mapping_ids():
        return None, REASON_PLAN_CORRUPT
    if plan.self_pointing_rows():
        return None, REASON_PLAN_CORRUPT
    return plan, "ok"


def mapping_repair_gate(
    plan: MappingRepairPlan, observed_team_ids: Mapping[int, int | None]
) -> tuple[bool, list[dict[str, Any]]]:
    """The live half of the CAS, asked as a SET before any write.

    *Every reviewed mapping must STILL hold the ``before.team_id`` the reviewer
    approved.* A row that has rotated is not an error in the world —
    ``resolve_team`` step 3 auto-registers, so the pipeline moving a mapping is
    the pipeline working — but it IS a row this plan may no longer act on.

    Named, never skipped, and retiring THAT ROW ONLY: a wholesale refusal would
    let one live re-registration cancel 129 approved siblings, which is the
    failure ``create_gate``'s docstring records from the other rail.

    ``observed_team_ids`` maps mapping_id → current ``team_id``, with ``None``
    for a mapping id that has no row. Both readings are drift; they are reported
    with different ``reason_code``s because "someone re-pointed it" and "it is
    gone" are different facts about the world even though the plan's response to
    them is the same.

    Returns ``(ok, drifted)``.
    """
    drifted: list[dict[str, Any]] = []
    for row in plan.rows:
        observed = observed_team_ids.get(int(row.mapping_id), None)
        if observed is None:
            drifted.append(
                {
                    "mapping_id": int(row.mapping_id),
                    "expected_before_team_id": int(row.before_team_id),
                    "observed_team_id": None,
                    "reason_code": REASON_MAPPING_ROW_MISSING,
                }
            )
        elif int(observed) != int(row.before_team_id):
            drifted.append(
                {
                    "mapping_id": int(row.mapping_id),
                    "expected_before_team_id": int(row.before_team_id),
                    "observed_team_id": int(observed),
                    "reason_code": REASON_MAPPING_BEFORE_DRIFT,
                }
            )
    return (not drifted), drifted


# ---------------------------------------------------------------------------
# The events.espn_id correction rail (SPEC-Q370, #1947 population 1)
# ---------------------------------------------------------------------------
#
# The FIFTH rail on this pattern. Same reasoning as every other one for the
# distinct schema and namespace: an espn_id correction and a team re-point must
# never be interchangeable at an apply, and two plans holding the same integers
# must never share an address.
#
# What makes this rail different from its four siblings, in one line: **the
# BEFORE state exists here.** The CREATE rail's compare had to live inside the
# INSERT because there was no row yet; this is an ordinary UPDATE, so the compare
# is the WHERE clause of the writing statement and `rowcount == 0` is a named
# finding rather than a silent success.
ESPN_ID_PLAN_SCHEMA = "event-espn-id-correction-plan/v1"
_ESPN_ID_PLAN_NS = "event-espn-id-correction-plan"

#: Per-row findings. Each retires ONE row and never its siblings.
#:
#: This list is longer than the other rails' and that is deliberate, not
#: over-engineering: SPEC-Q370 §3's rule is that a refusal collapsing two causes
#: into one word sends the operator at the wrong next action (gotcha #53). On
#: THIS population that is not hypothetical — the five reviewed rows have
#: already produced four of these five states between review and this writing.
REASON_ESPN_ID_ALREADY_CORRECT = "ESPN_ID_ALREADY_CORRECT"
REASON_ESPN_ID_MOVED = "ESPN_ID_MOVED"
REASON_EVENT_ROW_ABSENT = "EVENT_ROW_ABSENT"
REASON_COMMENCE_DRIFTED = "COMMENCE_DRIFTED"
REASON_TRUE_ID_ALREADY_HELD = "TRUE_ESPN_ID_ALREADY_HELD"

#: Ruling 095's gate, as a refusal. A census over a population that is still
#: being written is fiction, and the failure is invisible because such a census
#: SUCCEEDS — it returns rows, mints an artifact, and digests stably, because a
#: digest over fiction is a perfectly good digest. #1947's own rows flapped on a
#: ~2-minute cycle, and `15199901` moved its commence_time sixteen hours between
#: two reads fifty minutes apart.
REASON_POPULATION_NOT_STILL = "POPULATION_NOT_STILL"


@dataclass(frozen=True)
class PlannedEspnIdCorrection:
    """One event whose ``espn_id`` points at a different game, and the state read.

    ``wrong_espn_id`` is the compare half of the compare-and-set. It is CARRIED,
    not re-read — an apply that re-read it would be asking the question the
    review already answered, from a world that has moved. That is #1798's defect
    restated in the UPDATE direction.
    """

    event_id: int
    wrong_espn_id: str
    true_espn_id: str
    our_commence_time: str
    matchup: str | None = None

    @property
    def row_key(self) -> str:
        """One event is one work item, so its id IS its key."""
        return f"event:{int(self.event_id)}"

    def as_payload(self) -> dict[str, Any]:
        return {
            "event_id": int(self.event_id),
            "wrong_espn_id": str(self.wrong_espn_id),
            "true_espn_id": str(self.true_espn_id),
            "our_commence_time": str(self.our_commence_time),
            "matchup": self.matchup,
        }

    def digest_line(self) -> str:
        """The four addressed fields.

        ``our_commence_time`` is INSIDE, and it is the field this rail exists to
        get right. Queue 368's ``sport_id`` finding is the precedent: a field the
        apply depends on that sits outside the digest lets an artifact be edited
        while keeping its approved address and decoding clean. Here the
        dependency is not that the apply *writes* the timestamp — it does not,
        and must not — it is that **commence_time is how a reviewer knows WHICH
        GAME a row is**. #1947's whole history is rows whose commence_time moved,
        so a plan that did not address it could be approved for one game and
        applied to another wearing the same id.

        ``matchup`` stays OUT. It is prose assembled for the reviewer from the
        clubs, and re-wording it must not mint a new address — the same call the
        create rail makes for ``label``.
        """
        return digest_fields(
            int(self.event_id),
            str(self.wrong_espn_id),
            str(self.true_espn_id),
            str(self.our_commence_time),
        )


@dataclass(frozen=True)
class EspnIdCorrectionPlan:
    """The reviewed correction set, as a content-addressed object."""

    rows: tuple[PlannedEspnIdCorrection, ...] = ()
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
        return input_fingerprint(_ESPN_ID_PLAN_NS, str(len(lines)), *lines)

    def duplicate_event_ids(self) -> list[int]:
        """Event ids named twice. Must be empty: whichever ran second would
        silently win, an outcome no reviewer chose because the artifact shows both."""
        seen: dict[int, int] = {}
        for r in self.rows:
            seen[int(r.event_id)] = seen.get(int(r.event_id), 0) + 1
        return sorted(k for k, n in seen.items() if n > 1)

    def self_pointing_rows(self) -> list[int]:
        """Rows whose ``true`` equals their ``wrong``. Must be empty.

        A no-op WRITE is worse than useless on a CAS rail: ``rowcount`` would be
        1, so the row reports APPLIED while nothing changed — the exact
        false-comfort class ``miswired_after=0`` produced on the binding rail.
        """
        return sorted(
            int(r.event_id) for r in self.rows
            if str(r.wrong_espn_id) == str(r.true_espn_id)
        )

    def colliding_true_ids(self) -> list[str]:
        """True ids the plan itself assigns to more than one event. Must be empty.

        ``ix_events_espn_id`` is **NOT unique** (verified, and stated in #1979's
        docstring rather than implied away), so the database will happily accept
        two events carrying one ESPN id. The plan is therefore the only place
        this can be caught, and catching it here is not paranoia: the population
        was produced by rows being dragged onto each OTHER's ids.
        """
        seen: dict[str, int] = {}
        for r in self.rows:
            seen[str(r.true_espn_id)] = seen.get(str(r.true_espn_id), 0) + 1
        return sorted(k for k, n in seen.items() if n > 1)

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema": ESPN_ID_PLAN_SCHEMA,
            "plan_hash": self.plan_hash,
            "row_count": len(self.rows),
            "event_id_count": len(self.event_ids),
            "duplicate_event_ids": self.duplicate_event_ids(),
            "self_pointing_event_ids": self.self_pointing_rows(),
            "colliding_true_espn_ids": self.colliding_true_ids(),
            "rows": [r.as_payload() for r in self.rows],
            "context": dict(self.context),
        }


def build_espn_id_correction_plan(
    rows: Iterable[PlannedEspnIdCorrection],
    *,
    context: Mapping[str, Any] | None = None,
) -> EspnIdCorrectionPlan:
    return EspnIdCorrectionPlan(rows=tuple(rows), context=dict(context or {}))


def decode_espn_id_correction_plan(raw: Any) -> tuple[EspnIdCorrectionPlan | None, str]:
    """``(plan, reason)``. The stored address is RE-DERIVED, never believed."""
    if not isinstance(raw, Mapping):
        return None, REASON_PLAN_MISSING
    if raw.get("schema") != ESPN_ID_PLAN_SCHEMA:
        return None, REASON_PLAN_CORRUPT
    raw_rows = raw.get("rows")
    if not isinstance(raw_rows, list):
        return None, REASON_PLAN_CORRUPT
    rows: list[PlannedEspnIdCorrection] = []
    for row in raw_rows:
        if not isinstance(row, Mapping):
            return None, REASON_PLAN_CORRUPT
        try:
            # Subscript + coerce, never `.get()`: a missing field must land in the
            # `except` and become PLAN_ARTIFACT_CORRUPT, not decode as None and
            # sail past the digest (the queue-368 sport_id lesson).
            rows.append(
                PlannedEspnIdCorrection(
                    event_id=int(row["event_id"]),
                    wrong_espn_id=str(row["wrong_espn_id"]),
                    true_espn_id=str(row["true_espn_id"]),
                    our_commence_time=str(row["our_commence_time"]),
                    matchup=(
                        str(row["matchup"]) if row.get("matchup") is not None else None
                    ),
                )
            )
        except (KeyError, TypeError, ValueError):
            return None, REASON_PLAN_CORRUPT
    ctx = raw.get("context")
    plan = EspnIdCorrectionPlan(
        rows=tuple(rows), context=dict(ctx) if isinstance(ctx, Mapping) else {}
    )
    if plan.plan_hash != raw.get("plan_hash"):
        return None, REASON_PLAN_CORRUPT
    if plan.duplicate_event_ids():
        return None, REASON_PLAN_CORRUPT
    if plan.self_pointing_rows():
        return None, REASON_PLAN_CORRUPT
    if plan.colliding_true_ids():
        return None, REASON_PLAN_CORRUPT
    return plan, "ok"


def espn_id_correction_gate(
    plan: EspnIdCorrectionPlan,
    observed: Mapping[int, Mapping[str, Any] | None],
    *,
    true_id_holders: Mapping[str, Sequence[int]] | None = None,
) -> tuple[list[PlannedEspnIdCorrection], list[dict[str, Any]]]:
    """The live half of the CAS, asked as a SET before any write.

    Returns ``(actionable, retired)``. **A retirement is never fatal to the
    run** — one upstream repair must not cancel four approved siblings. That is
    the count-vs-set rule applied to the failure path, and it is the rule
    ``create_gate``'s docstring records paying for on the other rail.

    ``observed`` maps ``event_id -> {"espn_id": ..., "commence_time": ...}``, or
    ``None`` for an event id with no row. ``true_id_holders`` maps a true id to
    the event ids currently carrying it, so ``TRUE_ESPN_ID_ALREADY_HELD`` can
    fire before a write that a **non-unique** index would otherwise accept.

    The order of the checks is load-bearing and is not alphabetical:

    1. **absent** — nothing else can be asked of a row that is gone.
    2. **already correct** — before ``ESPN_ID_MOVED``, because "the ordinary
       pipeline got there first" and "it rotated somewhere unexpected" are
       different facts and the first is *success*. Collapsing them would report
       a self-healed population as drift and send an operator to re-derive a
       plan that has nothing left to do.
    3. **moved** — neither the wrong id nor the true one.
    4. **commence drifted** — the row still holds the wrong id, but it is no
       longer the game the reviewer read. Checked AFTER the id checks so a
       self-healed row is not reported as drift on a field the apply never writes.
    5. **true id already held** — last, because it is a fact about a *different*
       row and only matters for one this rail would otherwise write.
    """
    holders = {str(k): list(v) for k, v in (true_id_holders or {}).items()}
    actionable: list[PlannedEspnIdCorrection] = []
    retired: list[dict[str, Any]] = []

    def _retire(row: PlannedEspnIdCorrection, code: str, **extra: Any) -> None:
        entry = {
            "event_id": int(row.event_id),
            "expected_wrong_espn_id": str(row.wrong_espn_id),
            "true_espn_id": str(row.true_espn_id),
            "reason_code": code,
        }
        entry.update(extra)
        retired.append(entry)

    for row in plan.rows:
        state = observed.get(int(row.event_id))
        if state is None:
            _retire(row, REASON_EVENT_ROW_ABSENT, observed_espn_id=None)
            continue

        seen_id = state.get("espn_id")
        seen_id = None if seen_id is None else str(seen_id)

        if seen_id == str(row.true_espn_id):
            _retire(
                row, REASON_ESPN_ID_ALREADY_CORRECT, observed_espn_id=seen_id
            )
            continue
        if seen_id != str(row.wrong_espn_id):
            _retire(row, REASON_ESPN_ID_MOVED, observed_espn_id=seen_id)
            continue

        seen_commence = state.get("commence_time")
        if _normalize_instant(seen_commence) != _normalize_instant(row.our_commence_time):
            _retire(
                row,
                REASON_COMMENCE_DRIFTED,
                observed_espn_id=seen_id,
                expected_commence_time=str(row.our_commence_time),
                observed_commence_time=(
                    None if seen_commence is None else str(seen_commence)
                ),
            )
            continue

        others = [
            int(e) for e in holders.get(str(row.true_espn_id), [])
            if int(e) != int(row.event_id)
        ]
        if others:
            _retire(
                row,
                REASON_TRUE_ID_ALREADY_HELD,
                observed_espn_id=seen_id,
                held_by_event_ids=sorted(others),
            )
            continue

        actionable.append(row)

    return actionable, retired


def _normalize_instant(value: Any) -> str | None:
    """Compare two spellings of one instant without pretending they differ.

    The plan carries ``"2026-08-18T22:40:00Z"`` (JSON) and PostgreSQL hands back
    ``"2026-08-18 22:40:00+00:00"`` (``datetime`` str). Those are the same moment,
    and a naive string compare would retire every single row as
    ``COMMENCE_DRIFTED`` — a gate that refuses everything is indistinguishable
    from a gate that works, right up until someone notices the rail has never
    written anything.

    Deliberately narrow: it normalizes SPELLING, never VALUE. A different instant
    is still a drift, which is the whole point of the check.
    """
    if value is None:
        return None
    from datetime import datetime, timezone

    text = str(value).strip()
    if not text:
        return None
    candidate = text.replace(" ", "T")
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        # Unparseable is NOT "equal to everything". Return the raw text so an
        # unrecognised spelling drifts loudly instead of matching by accident.
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def stillness_verdict(
    probes: Sequence[Mapping[str, Any]],
    *,
    min_reads: int = 3,
    min_span_s: int = 300,
) -> tuple[bool, dict[str, Any]]:
    """Ruling 095's precondition, as a verdict. Pure.

    *Before a repair censuses, it must FREEZE the population or PROVE stillness —
    N >= 3 reads spanning > 300 s with identity fields unchanged.*

    Each probe is ``{"at": <epoch seconds>, "rows": {event_id: {"espn_id":…,
    "commence_time":…}}}``. Stillness means every probed event presented the same
    identity in every probe. A row that MOVED is named individually, because
    "the population is not still" and "these two rows are not still" send an
    operator at different next actions.

    Returns ``(still, detail)``. ``detail`` always carries ``reads``, ``span_s``
    and ``moved`` so a REFUSAL says which of the three conditions failed rather
    than just declining.

    Note what this deliberately does NOT do: it does not narrow the census to the
    rows that held still. Ruling 095 is explicit that narrowing selects for rows
    *between writes* — a sample biased toward looking calm — so an unstill
    population produces a refusal, not a smaller plan.
    """
    reads = len(probes)
    times = sorted(float(p.get("at", 0)) for p in probes)
    span = (times[-1] - times[0]) if times else 0.0

    identities: dict[int, set[tuple[Any, Any]]] = {}
    for probe in probes:
        rows = probe.get("rows") or {}
        for raw_id, state in rows.items():
            state = state or {}
            identities.setdefault(int(raw_id), set()).add(
                (
                    None if state.get("espn_id") is None else str(state["espn_id"]),
                    _normalize_instant(state.get("commence_time")),
                )
            )
    moved = sorted(eid for eid, seen in identities.items() if len(seen) > 1)

    detail = {
        "reads": reads,
        "min_reads": int(min_reads),
        "span_s": round(span, 3),
        "min_span_s": int(min_span_s),
        "moved_event_ids": moved,
        "probed_event_ids": sorted(identities),
    }
    still = reads >= int(min_reads) and span > float(min_span_s) and not moved
    if not still:
        detail["reason_code"] = REASON_POPULATION_NOT_STILL
    return still, detail


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


# ---------------------------------------------------------------------------
# The pair-opening complement repair plan (#2212, CAL-P097) — the SIXTH rail
#
# CERT-403A's first P1, verbatim:
#
#   "The historical repair has no executable, immutable ApplyPlan and leaves two
#    mandatory write semantics undecided ... an attended historical UPDATE cannot
#    be certified from a prose predicate. There is no frozen row set, no per-row
#    before value/CAS, no complete-content digest, no refusal vocabulary, no
#    rollback record, and no chosen treatment for the stale American-odds twin."
#
# Same reasoning as every sibling for the distinct schema and namespace: a
# pair-opening repair and a mapping re-point must never be interchangeable at an
# apply, and two plans holding the same integers must never share an address.
#
# THE TWO UNDECIDED WRITE SEMANTICS, NOW DECIDED — both are recorded here rather
# than in a doc, because a decision the code does not enforce is a preference.
#
# 1. ``opening_american_odds``: **MOVES WITH THE PROBABILITY.** The staged spec
#    said "must move with it or be NULLed" and did not choose. It moves, because
#    the column is a pure function of ``opening_probability`` — every other row
#    in the table carries the odds its probability implies, so recomputing is not
#    an invention, it is the only self-consistent option. NULLing would trade one
#    incoherence (a repaired probability beside a stale copied-Over odds) for a
#    different one (a probability with no odds beside it, unique in its table).
#    ``after_american`` is carried in the plan and inside the digest, so the
#    reviewer approves the exact integer the apply writes.
#
# 2. Provenance: **``opening_source = 'pair_complement_repair'``.** The staged
#    spec called provenance mandatory and said that if no column existed, that
#    was a blocker on this half. A column DOES exist —
#    ``FuturesOutcome.opening_source``, ``String(30)``, already carrying
#    ``clob_history`` / ``first_snapshot`` / ``bid_ask_midpoint`` / NULL. So the
#    blocker is discharged with **no migration and no DDL**: a repaired opening
#    is permanently distinguishable from a quote, which is the property the
#    writer gate exists to protect, and the apply is reversible because the
#    before-image is in the plan.
PAIR_OPENING_REPAIR_PLAN_SCHEMA = "pair-opening-complement-repair-plan/v1"
_PAIR_OPENING_PLAN_NS = "pair-opening-complement-repair-plan"

#: The provenance stamp. 22 chars, inside ``String(30)``.
PAIR_OPENING_REPAIR_SOURCE = "pair_complement_repair"

#: The CAS lost: the Under leg's ``opening_probability`` is no longer the value
#: the reviewer approved. Distinct from MISSING for the reason gotcha #53 keeps
#: costing — "someone rewrote it" and "the row is gone" send an operator at
#: different next actions even though the plan's response to both is to skip.
REASON_PAIR_OPENING_DRIFT = "PAIR_OPENING_BEFORE_DRIFT"
#: The other two thirds of the same CAS. CERT-406A returned BLOCK because they
#: did not exist: the gate compared ``opening_probability`` alone, so all three
#: hostile one-field mutations — source rewritten to ``clob_history``, American
#: odds rewritten to 999, and both together with the probability left alone —
#: returned ``(True, [])`` and the rail called the row unchanged. The apply
#: overwrites all three columns, so the compare half must bind all three; a CAS
#: over a subset of its own write set is not a CAS. Separate codes rather than
#: one, because the operator's next action differs: an odds twin that moved is
#: arithmetic somebody recomputed, a source that moved is another writer having
#: claimed the row.
REASON_PAIR_AMERICAN_DRIFT = "PAIR_OPENING_AMERICAN_DRIFT"
REASON_PAIR_SOURCE_DRIFT = "PAIR_OPENING_SOURCE_DRIFT"
#: More than one reviewed field moved. Deliberately NOT a priority pick among
#: the three above: a single-field code on a multi-field drift reads as a
#: complete account of the damage and is not one. ``drifted_fields`` carries the
#: full list on every drift entry regardless.
REASON_PAIR_BEFORE_DRIFT_MULTI = "PAIR_OPENING_BEFORE_DRIFT_MULTI"
REASON_PAIR_OUTCOME_MISSING = "PAIR_OUTCOME_ROW_MISSING"
#: The caller showed the gate a row but not every reviewed column of it. Fails
#: CLOSED, and is its own reason rather than drift, because the two states are
#: not the same claim: drift is "the row moved", this is "nobody looked". The
#: hazard is specific and silent — ``current.get("opening_american_odds")``
#: returns ``None`` both when the column is NULL and when the SELECT never
#: mentioned it, and the reviewed value is very often NULL, so a query that
#: forgot a column would have compared ``None == None`` and passed. That is
#: gotcha #53 exactly: an absence and a value arriving in the same shape.
REASON_PAIR_OBSERVATION_INCOMPLETE = "PAIR_OBSERVATION_INCOMPLETE"
#: The row already carries the repair stamp. NOT drift and NOT an error: it is
#: this plan, already applied. Named separately so a re-invocation of the same
#: plan_hash after a partial run reports "already done" rather than "drifted",
#: which is the difference between resuming and re-reviewing.
REASON_PAIR_ALREADY_REPAIRED = "PAIR_OPENING_ALREADY_REPAIRED"
#: The stamp is there but the values are not the ones this plan would have
#: written. "Already applied" is a claim about THIS plan, so it has to be
#: checked against this plan's own after-image; a bare stamp test would let a
#: row written by some other invocation — or a row this plan wrote and something
#: else then edited — be reported as resumable and skipped without review.
REASON_PAIR_STAMPED_NOT_THIS_PLAN = "PAIR_OPENING_STAMPED_NOT_THIS_PLAN"

#: The three columns the apply overwrites, and therefore exactly the three the
#: compare half must bind. A constant rather than three literals in two places,
#: so the payload, the digest and the gate cannot drift apart in silence.
PAIR_OPENING_REVIEWED_FIELDS: tuple[str, ...] = (
    "opening_probability",
    "opening_american_odds",
    "opening_source",
)

#: Which single-field refusal each reviewed column raises.
_PAIR_OPENING_FIELD_REASON: dict[str, str] = {
    "opening_probability": REASON_PAIR_OPENING_DRIFT,
    "opening_american_odds": REASON_PAIR_AMERICAN_DRIFT,
    "opening_source": REASON_PAIR_SOURCE_DRIFT,
}


@dataclass(frozen=True)
class PlannedPairOpeningRepair:
    """One Under leg the dry-run decided to rewrite, and the state it read.

    ``expected_before_opening`` and ``expected_before_source`` are the compare
    halves of the compare-and-set. They are CARRIED, never re-read: an apply
    that re-read them would be asking the question the review already answered,
    from a world that has moved. That is #1798's defect in the UPDATE direction,
    and the calibration pipeline writes these rows on a live schedule.

    ``over_outcome_id`` / ``over_opening`` are the Over leg, which this apply
    NEVER touches. They are inside the digest anyway, because ``after_opening``
    is *defined* as ``1 - over_opening`` — a plan whose Over price changed since
    review is a plan whose repaired value means something different, even if the
    Under row it writes is untouched.
    """

    outcome_id: int
    market_id: int
    expected_before_opening: float
    expected_before_american: int | None
    expected_before_source: str | None
    after_opening: float
    after_american: int | None
    over_outcome_id: int
    over_opening: float
    market_name: str | None = None

    @property
    def row_key(self) -> str:
        """One Under leg is one work item, so its outcome id IS its key."""
        return f"outcome:{int(self.outcome_id)}"

    def as_payload(self) -> dict[str, Any]:
        return {
            "outcome_id": int(self.outcome_id),
            "market_id": int(self.market_id),
            "before": {
                "opening_probability": float(self.expected_before_opening),
                "opening_american_odds": self.expected_before_american,
                "opening_source": self.expected_before_source,
            },
            "after": {
                "opening_probability": float(self.after_opening),
                "opening_american_odds": self.after_american,
                "opening_source": PAIR_OPENING_REPAIR_SOURCE,
            },
            "over_outcome_id": int(self.over_outcome_id),
            "over_opening": float(self.over_opening),
            "market_name": self.market_name,
        }

    def digest_line(self) -> str:
        """Every field the apply ACTS on, plus the value ``after`` is derived from.

        ``market_name`` stays OUT — it is prose for the reviewer, and re-wording
        it must not mint a new address (the ``label`` / ``matchup`` call the
        create and espn rails already make).

        ``over_opening`` is IN, and that is the queue-368 ``sport_id`` lesson
        applied one rail along: it is not written, but ``after_opening`` is
        arithmetically defined by it, so an artifact whose Over price was edited
        while keeping its approved address would decode clean and repair to a
        number nobody approved.

        The provenance stamp is a module constant rather than a per-row field,
        so it is not digested — but ``expected_before_source`` IS, because a row
        whose source changed between review and apply is a row something else
        has since written.
        """
        return digest_fields(
            int(self.outcome_id),
            int(self.market_id),
            f"{float(self.expected_before_opening):.6f}",
            self.expected_before_american,
            self.expected_before_source,
            f"{float(self.after_opening):.6f}",
            self.after_american,
            int(self.over_outcome_id),
            f"{float(self.over_opening):.6f}",
        )


@dataclass(frozen=True)
class PairOpeningRepairPlan:
    """The reviewed complement repair, as a content-addressed object."""

    rows: tuple[PlannedPairOpeningRepair, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def entries(self) -> tuple[Any, ...]:
        return self.rows

    @property
    def row_keys(self) -> tuple[str, ...]:
        return tuple(sorted(r.row_key for r in self.rows))

    @property
    def outcome_ids(self) -> tuple[int, ...]:
        return tuple(sorted({int(r.outcome_id) for r in self.rows}))

    @property
    def market_ids(self) -> tuple[int, ...]:
        return tuple(sorted({int(r.market_id) for r in self.rows}))

    @property
    def plan_hash(self) -> str:
        lines = sorted(r.digest_line() for r in self.rows)
        return input_fingerprint(_PAIR_OPENING_PLAN_NS, str(len(lines)), *lines)

    def duplicate_outcome_ids(self) -> list[int]:
        """Outcome ids named twice. Must be empty: whichever ran second would
        silently win, an outcome no reviewer chose because the artifact shows both."""
        seen: dict[int, int] = {}
        for r in self.rows:
            seen[int(r.outcome_id)] = seen.get(int(r.outcome_id), 0) + 1
        return sorted(k for k, n in seen.items() if n > 1)

    def self_pointing_rows(self) -> list[int]:
        """Rows whose ``after`` equals their ``before``. Must be empty.

        A no-op WRITE is not harmless on a CAS rail: ``rowcount`` would be 1, so
        the row reports APPLIED while nothing changed. On THIS population it is
        also a live signal rather than a hypothetical — ``before == after``
        means ``p == 1 - p``, i.e. ``p == 0.5``, which is exactly the
        exact-0.5000 placeholder pair the half-spike exclusion removes. Such a
        row must never reach this rail: it is not repairable by complement,
        because its complement is itself.
        """
        return sorted(
            int(r.outcome_id)
            for r in self.rows
            if abs(float(r.after_opening) - float(r.expected_before_opening)) < 1e-9
        )

    def incoherent_rows(self) -> list[int]:
        """Rows where ``after != 1 - over_opening``. Must be empty.

        The plan's whole licence is the measured direction result: ``p`` is the
        Over leg's real price and the Under leg's is its complement. A row whose
        ``after`` is not that complement is asserting a level nobody measured,
        and it would be indistinguishable from a quote once written.
        """
        return sorted(
            int(r.outcome_id)
            for r in self.rows
            if abs(float(r.after_opening) - (1.0 - float(r.over_opening))) > 1e-6
        )

    def out_of_range_rows(self) -> list[int]:
        """Rows writing a probability outside (0, 1). Must be empty."""
        return sorted(
            int(r.outcome_id)
            for r in self.rows
            if not (0.0 < float(r.after_opening) < 1.0)
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema": PAIR_OPENING_REPAIR_PLAN_SCHEMA,
            "plan_hash": self.plan_hash,
            "row_count": len(self.rows),
            "market_count": len(self.market_ids),
            "duplicate_outcome_ids": self.duplicate_outcome_ids(),
            "self_pointing_outcome_ids": self.self_pointing_rows(),
            "incoherent_outcome_ids": self.incoherent_rows(),
            "out_of_range_outcome_ids": self.out_of_range_rows(),
            "provenance_stamp": PAIR_OPENING_REPAIR_SOURCE,
            "rows": [r.as_payload() for r in self.rows],
            "context": dict(self.context),
        }


def build_pair_opening_repair_plan(
    rows: Iterable[PlannedPairOpeningRepair],
    *,
    context: Mapping[str, Any] | None = None,
) -> PairOpeningRepairPlan:
    return PairOpeningRepairPlan(rows=tuple(rows), context=dict(context or {}))


def decode_pair_opening_repair_plan(
    raw: Any,
) -> tuple[PairOpeningRepairPlan | None, str]:
    """``(plan, reason)``. The stored address is RE-DERIVED, never believed."""
    if not isinstance(raw, Mapping):
        return None, REASON_PLAN_MISSING
    if raw.get("schema") != PAIR_OPENING_REPAIR_PLAN_SCHEMA:
        return None, REASON_PLAN_CORRUPT
    raw_rows = raw.get("rows")
    if not isinstance(raw_rows, list):
        return None, REASON_PLAN_CORRUPT
    rows: list[PlannedPairOpeningRepair] = []
    for row in raw_rows:
        if not isinstance(row, Mapping):
            return None, REASON_PLAN_CORRUPT
        before, after = row.get("before"), row.get("after")
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            return None, REASON_PLAN_CORRUPT
        # Subscript + coerce, never ``.get()`` on a field the apply acts on: a
        # missing field must land in the ``except`` and become
        # PLAN_ARTIFACT_CORRUPT, not decode as None and sail past the digest.
        try:
            rows.append(
                PlannedPairOpeningRepair(
                    outcome_id=int(row["outcome_id"]),
                    market_id=int(row["market_id"]),
                    expected_before_opening=float(before["opening_probability"]),
                    expected_before_american=(
                        None
                        if before["opening_american_odds"] is None
                        else int(before["opening_american_odds"])
                    ),
                    expected_before_source=before["opening_source"],
                    after_opening=float(after["opening_probability"]),
                    after_american=(
                        None
                        if after["opening_american_odds"] is None
                        else int(after["opening_american_odds"])
                    ),
                    over_outcome_id=int(row["over_outcome_id"]),
                    over_opening=float(row["over_opening"]),
                    market_name=row.get("market_name"),
                )
            )
        except (KeyError, TypeError, ValueError):
            return None, REASON_PLAN_CORRUPT
        # The provenance stamp is not a free field. An artifact that names a
        # different one is asking for a write this rail does not perform.
        if after.get("opening_source") != PAIR_OPENING_REPAIR_SOURCE:
            return None, REASON_PLAN_CORRUPT
    ctx = raw.get("context")
    plan = PairOpeningRepairPlan(
        rows=tuple(rows), context=dict(ctx) if isinstance(ctx, Mapping) else {}
    )
    if plan.plan_hash != raw.get("plan_hash"):
        return None, REASON_PLAN_CORRUPT
    # Four structural refusals, all fail-closed. Each of them describes a plan
    # that would report success while doing something nobody approved.
    if (
        plan.duplicate_outcome_ids()
        or plan.self_pointing_rows()
        or plan.incoherent_rows()
        or plan.out_of_range_rows()
    ):
        return None, REASON_PLAN_CORRUPT
    return plan, "ok"


def _pair_opening_field_diff(
    expected: Mapping[str, Any], observed: Mapping[str, Any]
) -> list[str]:
    """Which of the three reviewed columns disagree, in declared order.

    ``opening_probability`` compares numerically at 1e-9 because it is
    ``Numeric(7, 6)`` and arrives as ``Decimal`` from asyncpg and ``float`` from
    a fixture. The other two compare by VALUE and by NULL-ness: ``None`` and
    ``0`` are different American odds and ``None`` and ``''`` are different
    sources, so neither may be normalised into the other.
    """
    diffs: list[str] = []
    for name in PAIR_OPENING_REVIEWED_FIELDS:
        want, got = expected.get(name), observed.get(name)
        if name == "opening_probability":
            if got is None or want is None:
                if got is not want:
                    diffs.append(name)
                continue
            if abs(float(got) - float(want)) > 1e-9:
                diffs.append(name)
            continue
        if name == "opening_american_odds":
            if (want is None) != (got is None):
                diffs.append(name)
            elif want is not None and int(got) != int(want):
                diffs.append(name)
            continue
        if want != got:
            diffs.append(name)
    return diffs


def _pair_gate_entry(
    row: PlannedPairOpeningRepair,
    reason: str,
    current: Mapping[str, Any] | None,
    **extra: Any,
) -> dict[str, Any]:
    """One row's refusal record.

    Every entry carries the full reviewed before-image, not merely the field
    that tripped: an operator triaging drift needs the row's whole approved
    state to decide between re-deriving and resuming, and the field that moved
    is rarely the field that explains why.
    """
    seen = dict(current) if current is not None else {}
    return {
        "outcome_id": int(row.outcome_id),
        "reason_code": reason,
        # Retained under their original names: these two keys predate the
        # widening and are what the existing refusal report reads.
        "expected_before_opening": float(row.expected_before_opening),
        "observed_opening": seen.get("opening_probability"),
        "expected_before": {
            "opening_probability": float(row.expected_before_opening),
            "opening_american_odds": row.expected_before_american,
            "opening_source": row.expected_before_source,
        },
        "observed": {k: seen.get(k) for k in PAIR_OPENING_REVIEWED_FIELDS},
        **extra,
    }


def pair_opening_repair_gate(
    plan: PairOpeningRepairPlan,
    observed: Mapping[int, Mapping[str, Any] | None],
) -> tuple[bool, list[dict[str, Any]]]:
    """The live half of the CAS, asked as a SET before any write.

    *Every reviewed Under leg must STILL hold the WHOLE before-image the
    reviewer approved* — the opening, its American twin, and its source.

    ``observed`` maps ``outcome_id`` -> the row's current
    ``{opening_probability, opening_american_odds, opening_source}``, with
    ``None`` for an outcome id that has no row. All three keys are REQUIRED when
    a row is present; a mapping missing any of them is refused rather than
    compared (``REASON_PAIR_OBSERVATION_INCOMPLETE``), because a NULL column and
    an unSELECTed column reach this function as the same ``None``.

    CERT-406A's P1, which this is the fix for: the compare half used to read
    ``opening_probability`` alone while the apply overwrote all three columns.
    A concurrent writer could therefore change the odds twin, the provenance, or
    both, after the dry-run and after the review, and the gate would return
    ``(True, [])`` — destroying a before-image the reviewer had approved and
    making the rollback record false, which is the one thing a rollback record
    exists not to be. The plan's ``digest_line`` had bound all three fields from
    the start; only the live half was narrow, so the artifact's address is
    unchanged by this fix.

    Rows are retired INDIVIDUALLY and by name, never skipped and never in bulk.
    A wholesale refusal would let one live re-write cancel 822 approved
    siblings, which is the failure ``create_gate``'s docstring records from the
    create rail and ``mapping_repair_gate``'s from the mapping rail.

    Returns ``(ok, drifted)``.
    """
    drifted: list[dict[str, Any]] = []
    for row in plan.rows:
        outcome_id = int(row.outcome_id)
        expected = {
            "opening_probability": float(row.expected_before_opening),
            "opening_american_odds": row.expected_before_american,
            "opening_source": row.expected_before_source,
        }

        current = observed.get(outcome_id)
        if current is None:
            drifted.append(
                _pair_gate_entry(row, REASON_PAIR_OUTCOME_MISSING, None, drifted_fields=[])
            )
            continue

        absent = [f for f in PAIR_OPENING_REVIEWED_FIELDS if f not in current]
        if absent:
            drifted.append(
                _pair_gate_entry(
                    row,
                    REASON_PAIR_OBSERVATION_INCOMPLETE,
                    current,
                    drifted_fields=[],
                    unobserved_fields=absent,
                )
            )
            continue

        if current.get("opening_source") == PAIR_OPENING_REPAIR_SOURCE:
            # Carries this rail's stamp. That is only "this plan, already
            # applied" if the row holds what THIS plan would have written; the
            # after-image is the test, not the stamp. Reported so a resumed run
            # is legible, and NOT counted as drift — telling an operator to
            # re-review a plan that simply finished is how a correct partial run
            # gets thrown away.
            after = {
                "opening_probability": float(row.after_opening),
                "opening_american_odds": row.after_american,
                "opening_source": PAIR_OPENING_REPAIR_SOURCE,
            }
            unexpected = _pair_opening_field_diff(after, current)
            drifted.append(
                _pair_gate_entry(
                    row,
                    REASON_PAIR_ALREADY_REPAIRED
                    if not unexpected
                    else REASON_PAIR_STAMPED_NOT_THIS_PLAN,
                    current,
                    drifted_fields=unexpected,
                    expected_after=after,
                )
            )
            continue

        diffs = _pair_opening_field_diff(expected, current)
        if diffs:
            drifted.append(
                _pair_gate_entry(
                    row,
                    _PAIR_OPENING_FIELD_REASON[diffs[0]]
                    if len(diffs) == 1
                    else REASON_PAIR_BEFORE_DRIFT_MULTI,
                    current,
                    drifted_fields=diffs,
                )
            )
    return (not drifted), drifted
