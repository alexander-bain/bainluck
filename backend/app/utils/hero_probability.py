"""ONE definition of the number a surface prints for "who wins this question".

═══ WHY THIS MODULE EXISTS (#3903) ═══

Alex's standing ruling is that **the blend is the product — one question gets
one number, and source divergence is a data bug to fix, not a feature to show.**
On 2026-09-08, during a Slam, the US Open hub and the match page one tap away
printed different numbers for the same quarter-final *and opposite move arrows*:

    /tournaments/us-open   Frances Tiafoe   −2  59%   (opened 61%)
    /events/15306225                        +2  60%   (opened 58%)

They were not rounding one number two ways.  They were two numbers.  The hub
priced the match from its own market rows — Kalshi alone (0.595 / 0.415),
renormalized by its own vig to 0.589 — while the page served
``compute_aggregate_probability``, the staleness-decayed weighted median over
all three sources on the event (kalshi 0.595, betting 0.5764, polymarket 0.605),
which lands on 0.595.  The openings came from two different places again, which
is what inverted the arrow.

Both are defensible numbers.  That is precisely the problem: a reader who taps a
row is not asking a different question, so they must not be given a different
answer.

═══ WHY IT IS AN EXTRACTION AND NOT A THIRD COPY ═══

``routes/events.py`` already carried the cascade **twice** — once in
``get_event`` for the detail page, once in the list/debug formatter — and the
second copy's own comment says why that is dangerous:

    "they are two independent copies of the same six lines, and fixing one is
    how a lane ships half a fix."

Teaching the tournament slate to serve the blend by pasting the cascade a third
time would have made that comment prophecy.  So the six lines move here, both
route sites call this, and the slate calls this.  Three surfaces, one function,
one number — which is the ruling stated as code rather than as an aspiration.

``tournament_slate.build_match_row``'s own docstring had already written the
principle down ("Two surfaces each computing 'the favourite' or 'is this
coherent' is the divergence bug in miniature") while its ``source_count: 1``
quietly did the opposite.  This closes that gap.

Pure logic: every input is read off a plain attribute, so an ``Event`` model, a
lightweight row tuple wrapper or a test stub all work and none of it needs a
database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from app.utils.aggregation import (
    TIER_OPENING,
    compute_aggregate_probability_tiered,
    effective_source_weights,
)
from app.utils.settled_hero import (
    FINAL_UNRESOLVED_SOURCE,
    is_finished_status,
    resolve_settled_hero,
)

__all__ = [
    "HeroReading",
    "resolve_hero",
    "blend_provenance",
]


@dataclass(frozen=True)
class HeroReading:
    """The one number, both sides of it, and the honest name of where it came from.

    ``source`` is the value that reaches ``hero_probability_source`` on the wire
    and it is load-bearing vocabulary, not a label: ``settled`` outranks the
    blend on a finished game (Q441/#1495 — a game that turned late publishes the
    loser as the favourite otherwise), ``final_unresolved`` says the game is over
    but we cannot yet name a winner (CERT-1938). An opening line never supplies
    a current chance (#12824).
    """

    home_probability: float
    away_probability: float
    source: str
    settled_result: Optional[str] = None


def resolve_hero(
    event: Any, *, source_inputs: Optional[list[tuple[str, float]]] = None,
    source_method: Optional[list[str]] = None,
) -> Optional[HeroReading]:
    """Resolve a verified result, then an admitted current chance.

    A finished game with a price but no verified winner retains the
    ``final_unresolved`` label. Historical opening lines stay separate even on
    such a game. ``None`` means there is no chance to print, never zero.
    """
    settled = resolve_settled_hero(
        status=getattr(event, "status", None),
        home_score=getattr(event, "home_score", None),
        away_score=getattr(event, "away_score", None),
        completed_at=getattr(event, "completed_at", None),
    )
    if settled is not None:
        return HeroReading(
            home_probability=settled.home_probability,
            away_probability=settled.away_probability,
            source=settled.source,
            settled_result=settled.result,
        )

    # #12824: the first stored line cannot become a current chance. Retain the
    # tier check defensively for old callers even though the aggregator no
    # longer returns an opening tier.
    blend, blend_tier = compute_aggregate_probability_tiered(
        event, source_inputs=source_inputs, source_method=source_method
    )
    _finished = is_finished_status(getattr(event, "status", None))
    if blend is not None and blend_tier != TIER_OPENING:
        return HeroReading(
            home_probability=blend,
            away_probability=round(1.0 - blend, 6),
            source=FINAL_UNRESOLVED_SOURCE if _finished else "blend",
        )

    return None


def blend_provenance(event: Any) -> tuple[int, Optional[datetime]]:
    """``(source_count, freshest_source_stamp)`` for the blend on this event.

    HOW MANY SOURCES ACTUALLY FED THE NUMBER, not how many the JSONB happens to
    hold.  ``effective_source_weights`` is the same reader
    ``compute_aggregate_probability`` uses to pick its inputs, so the count
    cannot drift from the value it describes — a count computed by a second
    walk over the JSONB is a count that can disagree with its own number, which
    is this module's whole subject matter one level down.

    The stamp is the freshest ``updated_at`` among those same sources.  A source
    block that carries no stamp contributes nothing to it (many do not), so
    ``None`` means "no source dated itself" and never "the sources are old" —
    gotcha #53's shape, and the caller must not read an absence as an age.
    """
    keys, _values, _weights = effective_source_weights(event)
    if not keys:
        return 0, None

    sources = getattr(event, "win_probability_sources", None)
    if not isinstance(sources, dict):
        return len(keys), None

    freshest: Optional[datetime] = None
    for key in keys:
        block = sources.get(key)
        if not isinstance(block, dict):
            continue
        raw = block.get("updated_at")
        if not isinstance(raw, str) or not raw:
            continue
        try:
            stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        # Naive is REFUSED rather than assumed UTC, the same rule
        # `tournament_slate._parse_moment` applies to a fixture time and for the
        # same reason: every comparison downstream is against an aware `now`.
        if stamp.tzinfo is None:
            continue
        if freshest is None or stamp > freshest:
            freshest = stamp

    return len(keys), freshest


def hero_sportsbook_count(event: Any) -> Optional[int]:
    """How many sportsbooks stand behind the blend hero — ``0`` when none do (#9081).

    The page captioned a Kalshi-only 13% "4 sportsbooks" because the caption
    counted the served ``bookmaker_odds`` rows — including a quote 53 days old —
    while ruling 051 had dropped the sportsbook consensus from the number
    (``betting_book_count`` 2, under ``BETTING_BOOK_FLOOR``). The count belongs
    to the number it sits beside, so it is read from the same
    ``effective_source_weights`` the blend is computed from: no ``betting`` among
    the hero's inputs means no sportsbook is behind it, whatever the snapshot
    table holds.

    When ``betting`` does feed the hero, the count is the one its writer stored
    beside it — the books that poll actually read. ``None`` when that count is
    missing or unreadable (a folded bag can carry a sibling's reading without
    it), so a caller keeps whatever it did before rather than printing a guess.
    """
    keys, _values, _weights = effective_source_weights(event)
    if "betting" not in keys:
        return 0
    sources = getattr(event, "win_probability_sources", None)
    if not isinstance(sources, dict):
        return None
    count = sources.get("betting_book_count")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        return None
    return count
