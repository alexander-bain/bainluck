"""#10955 PROTOTYPE — which raw observations of an exclusive FIELD answer for one another's scale.

PILLARS: TRUTH / FORMATTING. SHIP: the three retained Oscars charts recover
genuinely available history without inventing observations or weakening field
truth.

NOT WIRED. Nothing under `app/routes` or `app/tasks` imports this module; it is
the concrete contract release-root asked for (directive live/212) so that Lane1
and Root can rule on it with real examples in hand. Serving and admission are
byte-identical with or without it.

WHAT IT GENERALISES. `async_binary_pair` (#11157) admits a Polymarket Yes/No
pair whose two raw halves sit a few seconds apart. `_venue_field_columns`
(`routes/futures.py`) still requires every member of a squeezable exclusive field
at ONE shared instant. This is the N-leg form of #11157's rule, with every one of
its invariants kept and none added that it does not already have:

  * MEMBERSHIP IS THE WHOLE FIELD the reader validates against (#8000 — the
    deduped board, not the drawn top-N and not the legs the bank happens to
    hold). A member with no observations at all leaves no cell anywhere; that is
    a refusal, never a smaller denominator.
  * ONE GENUINE OBSERVATION PER MEMBER, all of ONE tier label (I5). Nothing is
    carried forward, interpolated, complemented or normalised.
  * BOUNDED TOTAL SPREAD, NOT A CHAIN. Every two samples in a cell must be
    compatible with EACH OTHER: same tier and |skew| <= min(S_tier, half of
    each one's own local spacing in its leg), S_tier being #11157's
    `pair_skew_bound_seconds` (min(30 s, grain/2); 0 for an undeclared grain).
    A cell is a clique, so its whole spread is within the smallest bound of any
    two of its members — never a ladder of adjacent 30 s gaps.
  * MUTUAL UNIQUENESS (I4/I6). Each sample in a cell has, in every other
    member's leg, exactly ONE compatible sample — the one in the cell. Two
    candidates is ambiguity, and an ambiguous sample joins no cell.
  * KNOWLEDGE TIME IS NOT OBSERVATION TIME (I1/I8). `cell_at` is the latest raw
    instant in the cell — the first instant every value existed. Each member
    keeps its own raw instant; `cell_at` is never written into an observation
    field.

For two members this is exactly `pair_observations` (the equivalence is a test).

WHERE IT WOULD RUN. Like #11157: ONCE, in the fill, on each leg's raw layered
series before compaction, written into the bank as an annotation; the reader
VERIFIES the annotation (`verify_field_cells`) and never re-clusters compacted
rows, which can look unique only because compaction dropped a neighbour.

WHAT IT DOES NOT DECIDE. Whether an admitted cell's column is on the printed
scale. That stays the reader's unchanged scale contract (`_venue_scale_refusal`:
the #23 squeeze must be the identity at the cell). `field_cell_squeeze_moves` is
the per-cell form of that question, exposed so the prototype can count how many
cells the existing whole-series refusal would turn on; whether a moved cell
refuses the series whole (today) or is withheld per cell (a policy change) is
the ruling this prototype asks for, not one it makes.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Collection, Mapping, Sequence

from app.utils.async_binary_pair import PAIR_SKEW_MAX_SECONDS, pair_skew_bound_seconds

#: `(observed_at, tier_label)` — what the fill holds per point (as #11157).
Observation = tuple[datetime, str]

#: Why a raw sample joined no cell. Counted per sample, never a series verdict.
MEMBER_UNBANKED = "member_has_no_observations"
PEER_ABSENT = "member_has_no_compatible_sample"
AMBIGUOUS = "member_has_two_compatible_samples"
NOT_MUTUAL = "cell_not_a_mutually_unique_clique"


@dataclass
class FieldCells:
    """The cells the rule admits, plus every refused sample counted by reason."""

    #: One dict per admitted cell: member id -> index into that member's leg.
    cells: list[dict[int, int]] = field(default_factory=list)
    #: reason -> number of raw samples (all members) that joined no cell for it.
    refused: dict[str, int] = field(default_factory=dict)
    #: Members of the field with no observations at all (sorted).
    unbanked_members: list[int] = field(default_factory=list)

    def admitted_samples(self) -> int:
        return sum(len(cell) for cell in self.cells)


def _local_spacing(leg: Sequence[Observation]) -> list[float]:
    """Each sample's distance to its nearest neighbour in its OWN leg (inf if alone)."""
    out: list[float] = []
    for k, (ts, _tier) in enumerate(leg):
        gaps = []
        if k > 0:
            gaps.append((ts - leg[k - 1][0]).total_seconds())
        if k + 1 < len(leg):
            gaps.append((leg[k + 1][0] - ts).total_seconds())
        out.append(min(gaps) if gaps else float("inf"))
    return out


def field_cells(
    legs: Mapping[int, Sequence[Observation]], members: Collection[int]
) -> FieldCells:
    """Every cell the rule admits over `members`. Each leg strictly ascending.

    `members` is the reader's denominator — the whole deduped field. A leg in
    `legs` that is not a member is ignored; a member absent from `legs` (or
    empty) means no cell can exist, and every sample is refused as unbanked.
    """
    result = FieldCells()
    member_ids = sorted({int(m) for m in members})
    if len(member_ids) < 2:
        return result
    unbanked = [m for m in member_ids if not legs.get(m)]
    if unbanked:
        result.unbanked_members = unbanked
        total = sum(len(legs.get(m) or ()) for m in member_ids)
        if total:
            result.refused[MEMBER_UNBANKED] = total
        return result

    series = {m: list(legs[m]) for m in member_ids}
    spacing = {m: _local_spacing(series[m]) for m in member_ids}
    times = {m: [ts for ts, _tier in series[m]] for m in member_ids}
    reach = timedelta(seconds=PAIR_SKEW_MAX_SECONDS)

    def compatible(m: int, i: int, n: int, j: int) -> bool:
        ts_i, tier_i = series[m][i]
        ts_j, tier_j = series[n][j]
        if tier_i != tier_j:
            return False
        bound = min(
            pair_skew_bound_seconds(tier_i), spacing[m][i] / 2.0, spacing[n][j] / 2.0
        )
        return abs((ts_i - ts_j).total_seconds()) <= bound

    def candidates(m: int, i: int, n: int) -> list[int]:
        ts = series[m][i][0]
        lo = bisect_left(times[n], ts - reach)
        hi = bisect_right(times[n], ts + reach)
        return [j for j in range(lo, hi) if compatible(m, i, n, j)]

    # Anchor on the sparsest leg (ties by id). The admitted set does not depend
    # on the choice: a cell that is a mutually unique clique is found from any of
    # its members, and the checks below are symmetric in every member.
    anchor = min(member_ids, key=lambda m: (len(series[m]), m))
    others = [m for m in member_ids if m != anchor]
    in_cell: dict[int, set[int]] = {m: set() for m in member_ids}
    first_reason: dict[tuple[int, int], str] = {}
    for i in range(len(series[anchor])):
        cell = {anchor: i}
        reason = None
        for n in others:
            found = candidates(anchor, i, n)
            if not found:
                reason = PEER_ABSENT
                break
            if len(found) > 1:
                reason = AMBIGUOUS
                break
            cell[n] = found[0]
        if reason is None:
            for m, i_m in cell.items():
                for n, j_n in cell.items():
                    if n == m:
                        continue
                    if candidates(m, i_m, n) != [j_n]:
                        reason = NOT_MUTUAL
                        break
                if reason:
                    break
        if reason is None:
            result.cells.append(cell)
            for m, idx in cell.items():
                in_cell[m].add(idx)
        else:
            first_reason[(anchor, i)] = reason

    for m in member_ids:
        for idx in range(len(series[m])):
            if idx in in_cell[m]:
                continue
            reason = first_reason.get((m, idx))
            if reason is None:
                reason = _sample_reason(m, idx, others_of=member_ids, candidates=candidates)
            result.refused[reason] = result.refused.get(reason, 0) + 1
    return result


def _sample_reason(m: int, idx: int, *, others_of: list[int], candidates) -> str:
    """Why a non-anchor sample joined no cell, asked from its own side."""
    for n in others_of:
        if n == m:
            continue
        found = candidates(m, idx, n)
        if not found:
            return PEER_ABSENT
        if len(found) > 1:
            return AMBIGUOUS
    return NOT_MUTUAL


def cell_at(legs: Mapping[int, Sequence[Observation]], cell: Mapping[int, int]) -> datetime:
    """The cell's KNOWLEDGE time: its latest raw instant. Never an observation time."""
    return max(legs[m][i][0] for m, i in cell.items())


def cell_spread_seconds(legs: Mapping[int, Sequence[Observation]], cell: Mapping[int, int]) -> float:
    stamps = [legs[m][i][0] for m, i in cell.items()]
    return (max(stamps) - min(stamps)).total_seconds()


def verify_field_cells(
    annotated: Mapping[int, Sequence[tuple[datetime, str, datetime | None]]],
    members: Collection[int],
) -> str | None:
    """The READER's check of a bank's cell annotation; None when it verifies.

    `annotated` maps member id -> `(observed_at, tier, cell_at)` per point, as a
    compacted bank would hold them. The reader does not re-cluster. It checks,
    per annotated `cell_at` (and tier), that every member holds EXACTLY ONE point
    so annotated, that `cell_at` is the latest of their raw instants, and that
    every two of them are within `pair_skew_bound_seconds(tier)` — what each
    point can still answer after compaction. Local spacing is a property of the
    RAW series and is not re-asked here (compaction widens it); that is why the
    fill, not the reader, decides ambiguity.
    """
    member_ids = {int(m) for m in members}
    groups: dict[tuple[datetime, str], dict[int, list[datetime]]] = {}
    for oid, points in annotated.items():
        for observed_at, tier, at in points:
            if at is None:
                continue
            if int(oid) not in member_ids:
                return "cell_member_outside_field"
            groups.setdefault((at, tier), {}).setdefault(int(oid), []).append(observed_at)
    for (at, tier), by_member in groups.items():
        if set(by_member) != member_ids:
            return "cell_incomplete_after_compaction"
        if any(len(stamps) != 1 for stamps in by_member.values()):
            return "cell_member_twice"
        stamps = [s[0] for s in by_member.values()]
        if max(stamps) != at:
            return "cell_at_is_not_the_latest_raw_instant"
        if (max(stamps) - min(stamps)).total_seconds() > pair_skew_bound_seconds(tier):
            return "cell_spread_exceeds_tier_bound"
    return None


def field_cell_squeeze_moves(values: Mapping[int, float], *, source: str) -> bool:
    """Would the reader's printed scale MOVE this cell's column off its raw values?

    The per-cell form of `_venue_scale_refusal`'s column check, asked through the
    SAME call it makes (`devigged_consensus_by_time`, `mutually_exclusive=True`)
    and the same 5e-5 tolerance — never a copy of the #23 thresholds. True means
    today's contract refuses the whole series if this cell is admitted.
    """
    from datetime import timezone

    from app.utils.futures_history_basis import devigged_consensus_by_time

    key = datetime(2000, 1, 1, tzinfo=timezone.utc)
    column = {int(k): float(v) for k, v in values.items()}
    printed = devigged_consensus_by_time({key: {source: column}}, mutually_exclusive=True).get(key)
    if printed is None:
        return True
    return any(abs(float(printed.get(k, v + 1.0)) - v) > 5e-5 for k, v in column.items())
