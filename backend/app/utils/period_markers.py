"""Period marker provenance and domain guarding (#3348).

`GET /api/events/{id}/history` serves `period_markers` — the quarter/inning/half
boundaries both clients draw as gridlines on the win-probability chart. They come
from a four-tier fallback chain in `routes/events.py`, and until this module
existed the four tiers were **byte-identical in shape**: a measured 3rd inning and
a marker the backend placed at `commence_time + 47min` both served as
`{"timestamp": ..., "period": ...}`. No client could prefer the observed one, so
iOS declined to decode the key at all (#3336).

Two rules live here, and they are separate.

**Provenance.** Every marker carries `source`. Measured tiers say which instrument
saw the period; the estimate tier says `estimated` and means *nobody saw this, we
did arithmetic on the scheduled kickoff*. Additive — a client that ignores the
field reads exactly what it read before.

**The domain guard.** A marker whose timestamp falls outside the span of the
series the chart actually draws is a chip with no line under it. Measured on
production 2026-09-05 over native/029's 70-event cohort:

* `15292946` (Londrina v Juventude) — the books stopped quoting on 08-28T03:35,
  the game kicked off 08-29T15:00. Both chips sit **36 hours past the end of the
  drawn line**, over empty axis.
* `15297176` (Atalanta v Cagliari) — the only series point is a single Polymarket
  tick at 06:00:41. Both chips draw to the *left* of the one dot on the chart.
* `15298122` (Ajax v Union SG) — no series at all.

So the guard bounds **both** ends, not just the late one: `before_start` occurs on
10 of the 70 events and `past_end` on 3. Bounding only the end — the defect #3348
headlines — would have left the more common half in place.

**A TIMESTAMP IS NOT A LINE (CERT-1984).** The first cut of this guard defined the
span from timestamps alone, and that is wrong in a shape production actually
serves: `routes/events.py` appends a `history` row for every odds bucket whether or
not `aggregate_bookmaker_odds()` found a probability, so a chart can hold dozens of
timestamped rows whose `home_probability` is `None`. The chart draws *nothing* for
those rows — and the old guard read them as a span and kept the chip. The very
defect, through the guard meant to stop it. A point counts toward a span only when
it carries a value the renderer can plot; see :func:`renderable_span`.

**ONE ARRAY, TWO RENDERERS.** `period_markers` is a single list, and the event page
hands the same list to `OddsChart` (win-probability lines) *and* to
`ScoreDifferentialChart` (projected/actual score lines). Those two draw different
series: the score chart's `score_history` is a real line, and the first cut left it
out of the span entirely, so a score-only chart could lose a truthful *measured*
inning. So the guard now measures each renderer's own span and keeps a marker that
lands on **either** — a chip is wrong only when no chart has ink under it.

Note this is membership in one span or the other, never the min/max of both: two
disjoint lines (a prob line on Monday, a score line on Wednesday) must not
manufacture a Tuesday where neither draws.

The server can only answer "does any chart draw here". Which of the two draws is a
question only the renderer holds, so `OddsChart` clips the same list to its own
drawn probability domain (`filteredPeriodBoundaries`); that is what keeps a chip
off a blank win-prob plot on an event whose score chart is fine.

Why this cannot quietly delete good markers: on a healthy event the odds line
spans days either side of kickoff (the cohort's in-domain events measure 7-13 day
spans), so `commence_time` sits comfortably inside it. And the measured tiers
derive their timestamps *from the very series that define the span*, so the guard
is a no-op for them by construction. `tests/test_period_markers.py` pins both
directions — the three production cases drop, and measured markers plus a healthy
estimated set survive untouched.

One deliberate asymmetry: when no renderer has a line the span is undefined and
**every** marker is dropped. That is the honest reading of "outside the drawn
line" — a chart with no line cannot place a boundary on it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

# Which instrument put a period boundary on the chart.
SOURCE_STATPAL = "statpal"      # tier 1: the scoring_plays table (play-by-play)
SOURCE_ESPN_BOX = "espn_box"    # tier 2: ESPN box-score scoring plays
SOURCE_WIN_PROB = "win_prob"    # tier 3: win_prob_snapshots game_state
SOURCE_ESTIMATED = "estimated"  # tier 4: arithmetic on commence_time

#: Sources that mean "an instrument observed this period start".
MEASURED_SOURCES = frozenset({SOURCE_STATPAL, SOURCE_ESPN_BOX, SOURCE_WIN_PROB})


def _parse(ts: Any) -> Optional[datetime]:
    """Parse an ISO timestamp, tolerating a trailing `Z`. None when unparseable."""
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


#: A span is the closed interval one renderer actually draws ink across, or
#: ``(None, None)`` when it draws nothing at all.
Span = tuple[Optional[datetime], Optional[datetime]]

#: What makes a `history` / `espn_history` / `win_prob_history` point a point on
#: the win-probability line. `draw_probability` is here because a soccer source
#: can carry only the draw leg.
PROBABILITY_KEYS = ("home_probability", "away_probability", "draw_probability")

#: What makes a point a point on the score-differential line. `history` carries
#: the projected pair; `score_history` and `espn_history` carry the actual one.
SCORE_KEYS = (
    "projected_home_score",
    "projected_away_score",
    "home_score",
    "away_score",
)


def renderable_span(
    *series: tuple[Optional[Iterable[dict]], Iterable[str]],
) -> Span:
    """Earliest and latest point ONE renderer can actually plot.

    Each argument pairs a series with the keys that make one of its points
    drawable by that renderer — ``(history, PROBABILITY_KEYS)``. A point counts
    only when it has a parseable `timestamp` **and** at least one named key holds
    a non-null value.

    That second half is the whole point (CERT-1984). `routes/events.py` emits a
    `history` row per odds bucket even when the aggregate probability came back
    `None`, so "has a timestamp" and "is on the line" are different questions and
    production serves payloads where they disagree. Asking the first one keeps a
    chip over a blank plot, which is the defect, not the fix.

    Returns ``(None, None)`` when this renderer plots nothing — the caller must
    read that as "there is no line", never as "no bound".
    """
    stamps: list[datetime] = []
    for points, value_keys in series:
        keys = tuple(value_keys)
        for point in points or ():
            point = point or {}
            if not any(point.get(key) is not None for key in keys):
                continue
            parsed = _parse(point.get("timestamp"))
            if parsed is not None:
                stamps.append(parsed)
    if not stamps:
        return None, None
    return min(stamps), max(stamps)


def extend_span_to(span: Span, moment: Optional[datetime]) -> Span:
    """Stretch a span's late end out to `moment` (a live chart is drawn to now).

    A no-op on an empty span: a chart with no line does not acquire one by the
    clock moving.
    """
    lo, hi = span
    if lo is None or hi is None or moment is None:
        return span
    return lo, max(hi, moment)


def drop_markers_off_every_line(
    markers: list[dict],
    spans: Iterable[Span],
    *,
    tolerance: timedelta = timedelta(minutes=1),
) -> list[dict]:
    """Keep the markers that land on the line of at least one renderer.

    `spans` are per-renderer, from :func:`renderable_span` — one for the
    win-probability chart, one for the score-differential chart. A marker is kept
    when it falls inside ANY of them, because a chip is only wrong when no chart
    has ink under it. Empty spans contribute nothing, so when no renderer draws,
    everything is dropped.

    Membership is tested against each span separately and never against the
    min/max of all of them: two disjoint lines must not manufacture a middle where
    neither draws.

    `tolerance` absorbs the minute-bucket rounding the odds history applies
    (`snapshots_by_time` truncates to the minute), so a marker landing on the
    first or last bucket is not lost to a few seconds of drift. It is deliberately
    small: the defects this guards against miss by 11 minutes at the closest and
    36 hours at the worst.

    A marker with an unparseable timestamp is dropped — it cannot be placed, so it
    cannot be shown to be on the line.
    """
    bounds = [
        (lo - tolerance, hi + tolerance)
        for lo, hi in spans
        if lo is not None and hi is not None
    ]
    if not bounds:
        return []
    kept = []
    for marker in markers:
        parsed = _parse(marker.get("timestamp"))
        if parsed is None:
            continue
        if any(low <= parsed <= high for low, high in bounds):
            kept.append(marker)
    return kept


def estimated_period_markers(
    sport_key: Optional[str],
    commence_time: Optional[datetime],
) -> list[dict]:
    """Tier 4: period boundaries derived from the sport's standard structure.

    Nobody observed these. The offsets are wall-clock estimates including
    breaks — they are what the chart falls back to when no instrument recorded a
    period, and they are tagged `estimated` so a client can decline to draw them.

    Returns ``[]`` for sports with no fixed period structure (tennis, golf,
    cricket, motorsport) rather than inventing one.
    """
    if not commence_time or not sport_key:
        return []

    ct = commence_time

    def at(minutes: int, period: str) -> dict:
        return {
            "timestamp": (ct + timedelta(minutes=minutes)).isoformat(),
            "period": period,
            "source": SOURCE_ESTIMATED,
        }

    if sport_key.startswith("soccer"):
        return [at(0, "1H"), at(47, "2H")]

    if sport_key.startswith("aussierules"):
        # AFL: 4 quarters, ~20 min each + breaks (~6 min quarter, ~20 min half)
        return [
            at(0, "1st Quarter"), at(26, "2nd Quarter"),
            at(72, "3rd Quarter"), at(98, "4th Quarter"),
        ]

    if sport_key.startswith("basketball"):
        if "ncaab" in sport_key or "wncaab" in sport_key:
            # NCAA basketball: 2 halves of 20 min each
            return [at(0, "1st Half"), at(55, "2nd Half")]
        # NBA: 4 quarters of 12 min each (real-time ~30-35 min per quarter)
        return [
            at(0, "1st Quarter"), at(33, "2nd Quarter"),
            at(80, "3rd Quarter"), at(113, "4th Quarter"),
        ]

    if sport_key.startswith("americanfootball"):
        # NFL/NCAA football: 4 quarters of 15 min each (real-time ~45 min each)
        return [
            at(0, "1st Quarter"), at(45, "2nd Quarter"),
            at(110, "3rd Quarter"), at(155, "4th Quarter"),
        ]

    if sport_key.startswith("icehockey"):
        # NHL: 3 periods of 20 min each (~40 min real-time with intermissions)
        return [at(0, "1st Period"), at(40, "2nd Period"), at(80, "3rd Period")]

    return []
