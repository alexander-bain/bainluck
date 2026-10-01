"""#8126 — the per-leg verdict a protocol-2 capture banked, turned into a reviewable write plan.

THE SHIP: a settled Kalshi board whose venue declared each leg stops showing a
blank result, because ``futures_outcomes.is_winner`` finally carries what the
settlement sweep read.

The producer (#2077, PR #8120) stores a multi-leg board's verdicts in
``settlement_captures.raw_response -> '_derived' -> 'legs'`` as
``{external_id, disposition, is_winner}``, stamped protocol 2. Nothing read them.
This module is the reader. It is PURE — no DB, no network — so every refusal is
driven by the unit file, and the script that executes the plan
(``scripts/apply_settlement_capture_verdicts_8126.py``) adds only SQL.

WHAT LICENSES A WRITE, AND WHAT DOES NOT
---------------------------------------

* **Only a leg's own** ``disposition == 'settled'`` **with a real bool**
  ``is_winner``. The board's disposition licenses nothing: ``settled_per_leg``
  and ``open_no_settlement`` both carry legs, and neither is a verdict
  (:meth:`Disposition.licenses_grading` is False for both, deliberately).
* ``settled_no_verdict`` — Kalshi's ``finalized``/``scalar`` — is price-down
  only (#1852 / #7987). It never writes ``is_winner`` and never clears one; an
  existing grade on such a leg is reported, not touched.
* The join is ``legs[].external_id == futures_outcomes.external_id`` by EXACT
  string equality, inside the capture's own market, on a Kalshi market. No name
  matching, no normalisation, no prefixes. Zero matches is ``unmatched``; two is
  ``ambiguous_identity`` and refuses.
* The write lands only on a BLANK result — ``resolution_source IS NULL`` — which
  is what the page reads as "nobody graded this" (#4788). A leg already graded
  the same way is left alone; one graded the OTHER way is a conflict, reported
  and never overwritten. Overwriting an incumbent grade is a separate decision.

WHAT REFUSES A WHOLE CAPTURE
----------------------------

A capture is evidence only if all of it parses. One malformed leg means the
derivation that produced the rest is suspect, so the capture is refused whole:
not protocol 2, not Kalshi, a board disposition that cannot carry legs, a leg
board carrying a ``winning_outcome``, a malformed or duplicated leg, or a
``settled_per_leg`` board with a leg still trading (the producer emits that
disposition only when every leg declared — a contradiction is not evidence).

**The current result vocabulary is applied first, whatever the capture's
protocol.** A v1 capture with ``winning_outcome = 'scalar'`` is refused because
``scalar`` is a settlement TYPE, never a verdict
(:data:`~app.utils.kalshi_market_status.NON_VERDICT_RESULTS`) — the protocol
bump protects against re-reading v1 rows under changed rules; it does not
license trusting them.

ACROSS RE-PROBES
----------------

A market is captured more than once. Every valid capture of it in the plan is
evidence, ordered by ``(captured_at, id)``. Two settled captures that disagree,
a settled leg also read ``settled_no_verdict``, or a settled leg later read as
still trading are conflicts and fail closed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.utils.kalshi_market_status import NON_VERDICT_RESULTS, VENUE_SETTLEMENT_SOURCE
from app.utils.resolution_authority import is_downgrade
from app.utils.settlement_truth import Disposition

#: The only probe protocol whose ``_derived.legs`` this consumer reads.
CONSUMED_PROTOCOL_VERSION = 2

KALSHI = "kalshi"

#: The rung a venue's own declaration is written on — the same constant
#: :func:`~app.utils.kalshi_market_status.graded_columns` emits, so the two
#: writers cannot drift apart.
WRITE_RESOLUTION_SOURCE = VENUE_SETTLEMENT_SOURCE

#: Runtime-DDL backup the apply banks into and the restore reads from.
REPAIR_BACKUP_TABLE = "backup_8126_capture_verdicts"

#: Board dispositions that may carry legs (mirrors ``settlement_truth``'s
#: private ``_LEG_BEARING_DISPOSITIONS``; a capture outside it carrying legs is
#: malformed).
LEG_BEARING_BOARD_DISPOSITIONS: frozenset[str] = frozenset(
    {Disposition.SETTLED_PER_LEG.value, Disposition.OPEN_NO_SETTLEMENT.value}
)

_SETTLED = Disposition.SETTLED.value
_NO_VERDICT = Disposition.SETTLED_NO_VERDICT.value
_OPEN = Disposition.OPEN_NO_SETTLEMENT.value

#: The three values a :class:`~app.utils.settlement_truth.LegSettlement` can carry.
LEG_DISPOSITIONS: frozenset[str] = frozenset({_SETTLED, _NO_VERDICT, _OPEN})

#: The exact key set the producer writes per leg (``_capture_row``).
_LEG_KEYS = frozenset({"external_id", "disposition", "is_winner"})


class CaptureRefused(ValueError):
    """A capture that is not evidence. ``code`` is the tally key."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CaptureRow:
    """The columns of one ``settlement_captures`` row the consumer reads."""

    id: int
    market_id: int
    source: str
    protocol_version: Any
    disposition: str
    winning_outcome: str | None
    #: ``raw_response -> '_derived'`` (None when absent). Only this key is read;
    #: the venue body beside it is never re-parsed here.
    derived: Any
    captured_at: datetime | None = None


@dataclass(frozen=True)
class OutcomeRow:
    """One ``futures_outcomes`` row of a captured market, with its market's source."""

    id: int
    market_id: int
    external_id: str
    is_winner: bool | None
    resolution_source: str | None
    market_source: str


@dataclass(frozen=True)
class Leg:
    external_id: str
    disposition: str
    is_winner: bool | None


@dataclass(frozen=True)
class LegWrite:
    """One planned write, with the exact pre-image the apply must find."""

    outcome_id: int
    market_id: int
    external_id: str
    capture_id: int
    pre_is_winner: bool | None
    pre_resolution_source: str | None
    new_is_winner: bool
    new_resolution_source: str = WRITE_RESOLUTION_SOURCE


@dataclass
class Plan:
    writes: list[LegWrite] = field(default_factory=list)
    #: capture id -> refusal code / detail
    refused: dict[int, str] = field(default_factory=dict)
    refused_detail: dict[int, str] = field(default_factory=dict)
    #: skip bucket -> [(market_id, external_id, note)]
    skipped: dict[str, list[tuple[int, str, str]]] = field(default_factory=dict)

    def skip(self, bucket: str, market_id: int, external_id: str, note: str = "") -> None:
        self.skipped.setdefault(bucket, []).append((market_id, external_id, note))

    def tallies(self) -> dict[str, Any]:
        refused: dict[str, int] = defaultdict(int)
        for code in self.refused.values():
            refused[code] += 1
        return {
            "writes": len(self.writes),
            "writes_winner": sum(1 for w in self.writes if w.new_is_winner),
            "writes_loser": sum(1 for w in self.writes if not w.new_is_winner),
            "refused_captures": dict(sorted(refused.items())),
            "skipped_legs": {k: len(v) for k, v in sorted(self.skipped.items())},
        }


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_capture(capture: CaptureRow) -> tuple[Leg, ...]:
    """Return the capture's legs, or raise :class:`CaptureRefused`. Never partial."""
    wo = capture.winning_outcome
    # Current vocabulary FIRST, regardless of protocol: `scalar` is a type.
    if wo is not None and str(wo).strip().lower() in NON_VERDICT_RESULTS:
        raise CaptureRefused(
            "non_verdict_winning_outcome",
            f"winning_outcome={wo!r} is a settlement type, never a verdict",
        )
    if capture.source != KALSHI:
        raise CaptureRefused("not_kalshi", f"source={capture.source!r}")
    pv = capture.protocol_version
    if not _is_int(pv) or pv != CONSUMED_PROTOCOL_VERSION:
        raise CaptureRefused("not_protocol_2", f"protocol_version={pv!r}")
    if capture.disposition not in LEG_BEARING_BOARD_DISPOSITIONS:
        raise CaptureRefused(
            "board_disposition_bears_no_legs", f"disposition={capture.disposition!r}"
        )
    if wo is not None:
        raise CaptureRefused(
            "leg_board_carries_winning_outcome",
            f"{capture.disposition} with winning_outcome={wo!r}",
        )
    derived = capture.derived
    if not isinstance(derived, Mapping):
        raise CaptureRefused("derived_missing", f"_derived={type(derived).__name__}")
    dpv = derived.get("protocol_version")
    if not _is_int(dpv) or dpv != CONSUMED_PROTOCOL_VERSION:
        raise CaptureRefused("derived_not_protocol_2", f"_derived.protocol_version={dpv!r}")
    raw_legs = derived.get("legs")
    if not isinstance(raw_legs, list) or not raw_legs:
        raise CaptureRefused("legs_malformed", "_derived.legs is not a non-empty list")

    legs: list[Leg] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_legs):
        if not isinstance(raw, Mapping) or set(raw) != _LEG_KEYS:
            raise CaptureRefused("leg_malformed", f"leg {i} is not {sorted(_LEG_KEYS)}")
        ext, disp, won = raw["external_id"], raw["disposition"], raw["is_winner"]
        # The producer strips; a ticker that is not its own strip is not the
        # string it stored, and exact equality would then be a lie.
        if not isinstance(ext, str) or not ext or ext != ext.strip():
            raise CaptureRefused("leg_malformed", f"leg {i} external_id={ext!r}")
        if disp not in LEG_DISPOSITIONS:
            raise CaptureRefused("leg_malformed", f"leg {i} disposition={disp!r}")
        if disp == _SETTLED:
            if not isinstance(won, bool):
                raise CaptureRefused("leg_malformed", f"leg {i} settled with is_winner={won!r}")
        elif won is not None:
            raise CaptureRefused("leg_malformed", f"leg {i} {disp} carries is_winner={won!r}")
        if ext in seen:
            raise CaptureRefused("duplicate_leg_identity", f"{ext!r} appears twice")
        seen.add(ext)
        legs.append(Leg(ext, disp, won))

    if capture.disposition == Disposition.SETTLED_PER_LEG.value and any(
        leg.disposition == _OPEN for leg in legs
    ):
        raise CaptureRefused(
            "board_leg_disposition_conflict",
            "settled_per_leg board carries a leg still trading",
        )
    return tuple(legs)


def _resolve_leg(
    evidence: list[tuple[datetime | None, int, Leg]],
) -> tuple[str, bool | None, int | None]:
    """Fold one leg's evidence across captures into ``(state, verdict, capture_id)``.

    ``state`` is ``settled`` / ``no_verdict`` / ``not_declared`` / ``conflict``.
    ``capture_id`` is the newest settled capture — the provenance banked with the write.
    """
    ordered = sorted(
        evidence, key=lambda e: (e[0] is None, e[0] or datetime.min, e[1])
    )
    dispositions = [leg.disposition for _, _, leg in ordered]
    verdicts = {leg.is_winner for _, _, leg in ordered if leg.disposition == _SETTLED}
    if len(verdicts) > 1:
        return "conflict", None, None
    if verdicts:
        if _NO_VERDICT in dispositions:
            return "conflict", None, None
        first = dispositions.index(_SETTLED)
        if any(d != _SETTLED for d in dispositions[first + 1 :]):
            # Settled is terminal; a later read saying otherwise is not evidence.
            return "conflict", None, None
        licensing = [cid for _, cid, leg in ordered if leg.disposition == _SETTLED][-1]
        return "settled", next(iter(verdicts)), licensing
    if _NO_VERDICT in dispositions:
        return "no_verdict", None, None
    return "not_declared", None, None


def plan_writes(captures: Iterable[CaptureRow], outcomes: Iterable[OutcomeRow]) -> Plan:
    """Turn captures + the outcome rows of their markets into a write plan."""
    plan = Plan()

    by_market: dict[int, dict[str, list[OutcomeRow]]] = defaultdict(lambda: defaultdict(list))
    for o in outcomes:
        by_market[int(o.market_id)][o.external_id].append(o)

    evidence: dict[tuple[int, str], list[tuple[datetime | None, int, Leg]]] = defaultdict(list)
    for c in captures:
        try:
            legs = validate_capture(c)
        except CaptureRefused as exc:
            plan.refused[int(c.id)] = exc.code
            plan.refused_detail[int(c.id)] = exc.detail
            continue
        for leg in legs:
            evidence[(int(c.market_id), leg.external_id)].append(
                (c.captured_at, int(c.id), leg)
            )

    for (market_id, ext), ev in sorted(evidence.items()):
        state, verdict, capture_id = _resolve_leg(ev)
        if state == "conflict":
            plan.skip(
                "conflict_across_captures",
                market_id,
                ext,
                ",".join(str(cid) for _, cid, _ in ev),
            )
            continue
        if state == "not_declared":
            plan.skip("not_declared", market_id, ext)
            continue

        matches = by_market.get(market_id, {}).get(ext, [])
        if len(matches) > 1:
            plan.skip("ambiguous_identity", market_id, ext, ",".join(str(o.id) for o in matches))
            continue
        if not matches:
            # A no-verdict leg we cannot find is still never a write.
            plan.skip("no_verdict" if state == "no_verdict" else "unmatched", market_id, ext)
            continue
        o = matches[0]
        if o.market_source != KALSHI:
            plan.skip("market_not_kalshi", market_id, ext, str(o.market_source))
            continue

        if state == "no_verdict":
            # Price-down only. Never written, never cleared — but an existing
            # grade on a scalar leg is the #1852 shape, so it is surfaced.
            if o.resolution_source is not None:
                plan.skip("no_verdict_but_graded", market_id, ext, str(o.resolution_source))
            else:
                plan.skip("no_verdict", market_id, ext)
            continue

        assert verdict is not None and capture_id is not None
        if o.resolution_source is not None:
            if o.is_winner is not None and bool(o.is_winner) == verdict:
                plan.skip("already_graded_agrees", market_id, ext, o.resolution_source)
            else:
                plan.skip(
                    "conflicts_existing_grade",
                    market_id,
                    ext,
                    f"{o.resolution_source}:{o.is_winner}->{verdict}",
                )
            continue
        if o.is_winner is True and verdict is False:
            # `True` with no source is not the ungraded default; refuse to guess.
            plan.skip("conflicts_existing_grade", market_id, ext, f"NULL:True->{verdict}")
            continue
        # Over a NULL source this is never a downgrade; asserted, not assumed.
        assert not is_downgrade(o.resolution_source, WRITE_RESOLUTION_SOURCE)
        plan.writes.append(
            LegWrite(
                outcome_id=int(o.id),
                market_id=market_id,
                external_id=ext,
                capture_id=capture_id,
                pre_is_winner=o.is_winner,
                pre_resolution_source=o.resolution_source,
                new_is_winner=verdict,
            )
        )

    plan.writes.sort(key=lambda w: w.outcome_id)
    return plan
