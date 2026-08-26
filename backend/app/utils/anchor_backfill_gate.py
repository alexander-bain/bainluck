"""The sink census, expressed as a predicate the backfill must pass through.

#1946 Item 8, queue 415. The Item-8 backfill has carried a launch gate since
queue 387 (2026-08-21) and the gate has only ever existed as prose:

    *"A backfill whose source is ~150x dirtier than its key (570 sink events)
    does not run until the sink population is censused and its dirty classes are
    named."*

A gate written in prose is read by people and ignored by code, which is exactly
the failure CLAUDE.md gotcha #35 names in a different context: *a predicate
cannot consume a range written in prose.* Four windows of chain rows repeated
"do not read a granted slot as clearance for Item 8" precisely because nothing
in the repository could refuse it. This module is the refusal.

WHAT A SINK IS, AND WHY IT ONLY THREATENS HALF THE BACKFILL
-----------------------------------------------------------

A **sink event** is one ``events`` row that markets from many genuinely
different games are all linked to. Queue 387 found them by inverting the
grouping — ``event_id -> COUNT(DISTINCT game_id)`` rather than the reverse —
and measured **570** of them Feb-Aug 2026, the worst holding **50** distinct
game-ids. Specimen: event ``14741447``, whose two team names are both literally
*"Over 2.5 maps"*, absorbing 25+ CS2/LoL game-ids.

The consequence for a backfill is the whole reason for this module. Anchors
derived from ``futures_markets.event_id`` would faithfully encode every mislink
as identity evidence: a sink holding 25 game-ids does not produce one wrong
anchor, it produces 25, each of them an ``id_kind='game'`` row asserting that a
CS2 map and a soccer fixture are the same game. Under ruling 048 arm A that is
absorption authority, granted on a link that was already known to be wrong.

**But that hazard is a property of the SOURCE, not of the backfill.** It exists
because ``futures_markets.event_id`` is a link table: one event row can be
pointed at by N markets from N different games. It does not exist for the three
provider-id columns on ``events`` itself — ``external_id``, ``espn_id``,
``statpal_fixture_id`` — because a scalar column on a row cannot hold two
values. One row, one ``espn_id``, at most one anchor. There is no grouping to
invert and therefore no sink to census.

So the gate binds the LINK-DERIVED class and only that class. Splitting it this
way is not a loosening of the gate; it is the gate applied to the population it
was measured on. Conflating them would have the perverse effect of holding back
the half that is provably safe on evidence gathered about the half that is not.

WHAT THIS MODULE REFUSES TODAY
------------------------------

:data:`SINK_CENSUS` is ``None``. The census is staged on the measurement bus as
``M-SINK-CENSUS-1`` (``.claude/handoff/CODEX-QUEUE.md``) under ruling 134, which
puts every census in the measurement lane and forbids a build lane from running
its own. Until that mission returns its JSON block and someone pastes it here,
:func:`gate_for` returns ``BLOCKED`` for the link-derived class, and the backfill
task refuses to write a single link-derived anchor.

Filling this in is deliberately a code change and not a config flag. The census
names *dirty classes* with per-class dispositions, and adopting them is a
judgment about which classes may anchor an absorption — the kind of change that
should arrive as a reviewable diff with the measurement quoted in it.
"""

from __future__ import annotations

from typing import Any, Optional

#: The class of anchor whose source is a scalar column on ``events``. One row,
#: one value, no grouping to invert, no sink hazard. Never gated.
CLASS_COLUMN_DERIVED = "column_derived"

#: The class of anchor whose source is ``futures_markets.event_id`` — a link
#: table, and the population the sink census was measured on. Gated.
CLASS_LINK_DERIVED = "link_derived"

#: Gate states. ``BLOCKED`` refuses the whole class; ``CLEAR`` allows it; the
#: middle state allows it minus the classes the census named ``EXCLUDE``.
GATE_BLOCKED = "BLOCKED"
GATE_CLEAR = "CLEAR"
GATE_CLEAR_WITH_EXCLUSIONS = "CLEAR_WITH_EXCLUSIONS"

#: The verdict strings ``M-SINK-CENSUS-1`` is specified to emit.
_CENSUS_VERDICT_CLEAR = "CLEAR_TO_BACKFILL"
_CENSUS_VERDICT_EXCLUSIONS = "BACKFILL_WITH_EXCLUSIONS"
_CENSUS_VERDICT_BLOCK = "BLOCK"

#: The per-class dispositions the census assigns. ``EXCLUDE`` means write
#: nothing; ``OBSERVE`` means write it as ``market`` so it is recorded and can
#: never absorb; ``SAFE`` means write it as ``game``.
DISPOSITION_EXCLUDE = "EXCLUDE"
DISPOSITION_OBSERVE = "OBSERVE"
DISPOSITION_SAFE = "SAFE"

#: **The census result goes here, verbatim, when the measurement lane returns
#: it.** ``None`` means "not measured", which is a different reading from "measured
#: and found clean" — gotcha #53, and the reason this is not an empty dict.
SINK_CENSUS: Optional[dict[str, Any]] = None

#: Named so an operator reading a refusal knows where the answer comes from
#: rather than having to find out.
CENSUS_MISSION = "M-SINK-CENSUS-1 (.claude/handoff/CODEX-QUEUE.md, measurement lane)"


class GateVerdict:
    """Why a class of anchor may or may not be written, and for whom.

    ``reason`` is written to be quoted directly into a task summary. A refusal
    an operator cannot act on is a refusal they will route around.
    """

    __slots__ = ("state", "reason", "excluded_classes")

    def __init__(
        self,
        state: str,
        reason: str,
        excluded_classes: Optional[frozenset[str]] = None,
    ) -> None:
        self.state = state
        self.reason = reason
        self.excluded_classes = excluded_classes or frozenset()

    @property
    def may_write(self) -> bool:
        return self.state != GATE_BLOCKED

    def __repr__(self) -> str:  # pragma: no cover — diagnostics only
        return (
            f"GateVerdict(state={self.state!r}, reason={self.reason!r}, "
            f"excluded_classes={sorted(self.excluded_classes)!r})"
        )


#: Distinguishes "the caller passed no census" from "the caller passed ``None``,
#: meaning explicitly not-measured". Both refuse, but only the second is a
#: statement, and a test needs to be able to make it.
_UNSET = object()


def gate_for(anchor_class: str, census: Any = _UNSET) -> GateVerdict:
    """Is this class of anchor cleared to be written?

    ``census`` defaults to :data:`SINK_CENSUS` and is injectable so a test can
    pin every branch without mutating module state — the branch that matters
    most is the one nobody can reach today, and a gate whose refusal path is
    untested is a gate nobody has read.
    """
    if census is _UNSET:
        census = SINK_CENSUS

    if anchor_class == CLASS_COLUMN_DERIVED:
        return GateVerdict(
            GATE_CLEAR,
            "column-derived anchors are not sink-gated: the source is a scalar "
            "column on `events`, so one row yields at most one anchor and there "
            "is no grouping to invert. The sink census was measured on "
            "`futures_markets.event_id`, a link table, and binds that class only.",
        )

    if anchor_class != CLASS_LINK_DERIVED:
        # An unknown class is refused, loudly. A gate that defaults to "allow"
        # for inputs it does not recognise is not a gate.
        return GateVerdict(
            GATE_BLOCKED,
            f"unknown anchor class {anchor_class!r} — refused. Add it to this "
            "module with an explicit ruling on whether the sink census binds it.",
        )

    if census is None:
        return GateVerdict(
            GATE_BLOCKED,
            "the sink census has NOT been taken. Link-derived anchors are "
            "sourced from `futures_markets.event_id`, measured ~150x dirtier "
            f"than the key it would become. Staged as {CENSUS_MISSION}. This is "
            "an absence, not a clean result (gotcha #53).",
        )

    verdict = str(census.get("verdict") or "").strip()

    if verdict == _CENSUS_VERDICT_BLOCK:
        return GateVerdict(
            GATE_BLOCKED,
            f"the sink census returned {verdict!r} — the measurement lane "
            "refused this backfill on the evidence. Do not override here; "
            "re-measure or change the derivation.",
        )

    if verdict not in (_CENSUS_VERDICT_CLEAR, _CENSUS_VERDICT_EXCLUSIONS):
        return GateVerdict(
            GATE_BLOCKED,
            f"the sink census carries an unrecognised verdict {verdict!r}. A "
            "census whose verdict cannot be parsed has not been consumed, and "
            "an unparseable gate must fail closed.",
        )

    excluded = frozenset(
        str(entry.get("name"))
        for entry in (census.get("dirty_classes") or [])
        if isinstance(entry, dict)
        and str(entry.get("backfill_disposition") or "").strip() == DISPOSITION_EXCLUDE
    )

    if not excluded:
        return GateVerdict(
            GATE_CLEAR,
            f"sink census {census.get('census_id')!r} verdict {verdict!r}, no "
            "class marked EXCLUDE.",
        )

    return GateVerdict(
        GATE_CLEAR_WITH_EXCLUSIONS,
        f"sink census {census.get('census_id')!r} verdict {verdict!r}, "
        f"{len(excluded)} class(es) marked EXCLUDE: {', '.join(sorted(excluded))}.",
        excluded_classes=excluded,
    )
