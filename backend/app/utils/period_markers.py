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

Why this cannot quietly delete good markers: on a healthy event the odds line
spans days either side of kickoff (the cohort's in-domain events measure 7-13 day
spans), so `commence_time` sits comfortably inside it. And the measured tiers
derive their timestamps *from the very series that define the span*, so the guard
is a no-op for them by construction. `tests/test_period_markers.py` pins both
directions — the three production cases drop, and measured markers plus a healthy
estimated set survive untouched.

One deliberate asymmetry: when there is no series at all the span is undefined and
**every** marker is dropped. That is the honest reading of "outside the drawn
line" — a chart with no line cannot place a boundary on it. Note the web already
declines to render the chart in that case (`hasAnyWinProbData`, event page
line 1254), so for that subset this changes the payload and not the pixels; it is
still the right payload, and iOS has no such gate.
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


def series_span(
    *series: Optional[Iterable[dict]],
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Earliest and latest timestamp across every series the chart draws.

    Each argument is a list of points carrying a `timestamp` key (``history``,
    ``aggregate_line``, ``espn_history``, each ``win_prob_history`` source).
    Points without a parseable timestamp are ignored. Returns ``(None, None)``
    when nothing parseable was supplied — the caller must treat that as "there is
    no line", not as "no bound".
    """
    stamps: list[datetime] = []
    for points in series:
        for point in points or ():
            parsed = _parse((point or {}).get("timestamp"))
            if parsed is not None:
                stamps.append(parsed)
    if not stamps:
        return None, None
    return min(stamps), max(stamps)


def drop_markers_outside_span(
    markers: list[dict],
    lo: Optional[datetime],
    hi: Optional[datetime],
    *,
    tolerance: timedelta = timedelta(minutes=1),
) -> list[dict]:
    """Keep only markers that land on the drawn line.

    `lo`/`hi` come from :func:`series_span`. When either is None there is no line
    to land on and everything is dropped.

    `tolerance` absorbs the minute-bucket rounding the odds history applies
    (`snapshots_by_time` truncates to the minute), so a marker landing on the
    first or last bucket is not lost to a few seconds of drift. It is deliberately
    small: the defects this guards against miss by 11 minutes at the closest and
    36 hours at the worst.

    A marker with an unparseable timestamp is dropped — it cannot be placed, so it
    cannot be shown to be on the line.
    """
    if lo is None or hi is None:
        return []
    low = lo - tolerance
    high = hi + tolerance
    kept = []
    for marker in markers:
        parsed = _parse(marker.get("timestamp"))
        if parsed is not None and low <= parsed <= high:
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
