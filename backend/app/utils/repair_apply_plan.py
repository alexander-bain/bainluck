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
