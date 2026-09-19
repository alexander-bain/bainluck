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
    but we cannot yet name a winner (CERT-1938), and ``opening`` says nobody has
    quoted this since the line was posted.
    """

    home_probability: float
    away_probability: float
    source: str
    settled_result: Optional[str] = None


def resolve_hero(event: Any) -> Optional[HeroReading]:
    """The hero cascade, once: settled -> blend -> opening, or ``None``.

    ``event`` is anything carrying ``status``, ``home_score``, ``away_score``,
    ``completed_at``, ``win_probability_sources``, ``espn_win_prob_home`` and
    ``opening_home_probability`` / ``opening_away_probability``.

    THE ORDER IS THE WHOLE CONTENT OF THIS FUNCTION and every arm of it was
    bought with a defect:

    1. **Settled outranks the blend** (Q441/#1495).  On a finished game the
       blend is not an answer, it is whatever price was last captured before
       capture stopped — 5 of 44 sampled games published the LOSER as the
       favourite.  Gated to trustworthily-settled only; see ``settled_hero``.
    2. **The blend, labelled honestly** (CERT-1938).  A game can be over without
       us being able to name a winner — a tennis match whose result lives in a
       tournament container we have not graded.  The number is unchanged; only
       the claim about it is.
    3. **The opening, when nothing else exists.**  Not a forecast, a record of
       where the line opened, and named as such.

    ``None`` means we have nothing to print, which is a real state and never a
    zero.
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

    # ── #6694: A TIER-3 ANSWER IS NOT A BLEND AND MUST NOT BE CALLED ONE ─────
    #
    # `compute_aggregate_probability` falls back through three tiers and its
    # third one RETURNS `opening_home_probability`. So on any event that has an
    # opening price it is never `None`, which made arm 3 below structurally
    # unreachable: the `opening` source this module documents as load-bearing
    # vocabulary — "nobody has quoted this since the line was posted" — could
    # not be reached to say it.
    #
    # Measured on production 2026-09-19 12:00–12:40Z: 486 events in a two-day
    # window carry the Tier-3 signature (no weighted source in the bag, no ESPN
    # reading, an opening on file), 8 of them live at that minute, and every one
    # was served `hero_probability_source: "blend"`. Specimen 15314578
    # (Uganda–Kenya, live) printed a 64% hero captioned as a live blend above a
    # chart whose own series ended at 78% — its opening and its market, on one
    # screen, with nothing to tell the reader which was which.
    #
    # 🔴 THE NUMBER IS NOT THE DEFECT AND DOES NOT MOVE. 64% is the honest
    # figure here: the bag holds `betting_book_count: 1` and no `betting`
    # reading, because RULING 051 DROPS the sportsbook consensus below
    # `BETTING_BOOK_FLOOR` (3) — "a consensus of one is not a consensus". The
    # live single-book price sitting in `odds_snapshots` is exactly what that
    # ruling exists to refuse, so reaching for it here would rebuild #1841's
    # 87-13-for-a-team-trailing-5-0. This change moves the CLAIM, not the value,
    # which is the same move CERT-1938 made one arm up: "The number is
    # unchanged; only the claim about it is."
    #
    # The finished-game exemption is not an edge case being tidied away.
    # `final_unresolved` says "this game is over and we cannot name a winner",
    # which is a strictly more urgent thing for a reader to know than where the
    # line opened, so on a finished status it keeps the arm it has today.
    blend, blend_tier = compute_aggregate_probability_tiered(event)
    _finished = is_finished_status(getattr(event, "status", None))
    if blend is not None and not (blend_tier == TIER_OPENING and not _finished):
        return HeroReading(
            home_probability=blend,
            away_probability=round(1.0 - blend, 6),
            source=FINAL_UNRESOLVED_SOURCE if _finished else "blend",
        )

    opening = getattr(event, "opening_home_probability", None)
    if opening is not None:
        home = float(opening)
        away = getattr(event, "opening_away_probability", None)
        return HeroReading(
            home_probability=home,
            away_probability=(
                float(away) if away is not None else round(1.0 - home, 6)
            ),
            source="opening",
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
