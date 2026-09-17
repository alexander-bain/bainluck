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

import re
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

# Which instrument put a period boundary on the chart.
SOURCE_STATPAL = "statpal"      # tier 1: the scoring_plays table (play-by-play)
SOURCE_ESPN_BOX = "espn_box"    # tier 2: ESPN box-score scoring plays
SOURCE_WIN_PROB = "win_prob"    # tier 3: win_prob_snapshots game_state
SOURCE_ESTIMATED = "estimated"  # tier 4: arithmetic on commence_time
#: The ESPN status-text stream (`espn_history`), as distinct from its box score.
#: Added by #6718: the observed-transition tier reads two different state series
#: and stamped every marker `win_prob`, so the payload could not say which
#: instrument saw a transition. No client branches on `source` (checked across
#: `lib/periodMarkers.ts`, both chart components, and `ios/**`, which decodes no
#: marker at all), and this one is as measured as the other three.
SOURCE_ESPN_STATE = "espn_state"

# How much a marker's timestamp can be trusted AS A PERIOD START (#5140). Additive:
# a client that ignores `precision` reads exactly what it read before.
PRECISION_BOUNDARY = "boundary_observed"  # bracketed inside POLL_TOLERANCE
PRECISION_FIRST_SEEN = "first_seen"       # bracketed, but wider than that
PRECISION_FIRST_SCORE = "first_score"     # first SCORE of the period, not its start

#: Sources that mean "an instrument observed this period start".
MEASURED_SOURCES = frozenset({
    SOURCE_STATPAL, SOURCE_ESPN_BOX, SOURCE_WIN_PROB, SOURCE_ESPN_STATE,
})


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


# ── Observed game-state transitions (#5140, corrected #6718) ─────────────────
#
# Tiers 1 and 2 answer "when was the first SCORE of period N", which is bounded
# below by that score and cannot answer "when did period N begin" (Chiefs-Broncos
# 14638896: Q2 drawn at 01:33:43Z, its only touchdown; the feed had said
# `15:00 - 2nd Quarter` at 00:54:43Z). The state stream answers it directly, from
# rows already in the payload.
#
# WHAT A MARKER HERE CLAIMS, and it is not a point. ESPN's status text carries no
# event time — it is what OUR poll saw, when our poll saw it. So a marker is only
# ever the late end of an interval: the period began after `not_before` (the last
# observation that showed an EARLIER state) and at or before `timestamp`. That
# interval is the honest artifact and it is served. `precision` names how wide it
# is; it is a label on the bracket, never a promise about the error:
#
#   boundary_observed  the bracket is inside POLL_TOLERANCE
#   first_seen         wider, but inside MAX_FIRST_SEEN_BRACKET
#   (no marker)        wider still, or no lower bound at all
#
# BOTH CONSTANTS ARE JUDGEMENT, NOT ARITHMETIC (#6718 finding 5). They are cutoffs
# chosen to sort tight brackets from loose ones on the cadence these games actually
# poll at. Nothing here establishes a one-poll error bound, and no docstring should
# claim one: a caller that needs the real uncertainty reads `not_before`.
#
# THREE THINGS THIS REFUSES TO DO, each because the first cut did it (#6718):
#
#   * claim a boundary with no lower bound. The first cut let a `15:00` game clock
#     stand in for the bracket, so a first-ever row was served as the TIGHTEST
#     precision with `not_before: null` — which production did, on 14638896 and
#     15304451. A start clock can persist before play begins and is not an event
#     timestamp, so it corroborates and never substitutes: no earlier qualifying
#     observation means NO MARKER.
#   * read two sources contradicting each other as an observation. When one capture
#     instant carries two different states, that instant is evidence of
#     disagreement, not of a transition; it can neither carry a marker nor bound
#     one. The first cut emitted a zero-width bracket (`not_before == timestamp`)
#     labelled `boundary_observed`.
#   * let a stale row tighten a bracket. A lagging source can deliver an EARLIER
#     state at a LATER capture time; sorting by capture time does not resolve that.
#     Such a row proves nothing about the state at its own capture instant, so it
#     is refused as a lower bound — otherwise it makes a loose bracket look tight.
#
# Football only, on purpose. The vocabulary below is ESPN's football status text;
# innings, sets, halves and hockey periods keep the existing tiers untouched.
TRANSITION_SPORT_PREFIXES = ("americanfootball_",)

#: A bracket this tight is called `boundary_observed`. A sorting cutoff on the
#: cadence these games poll at — not an error bound. See the note above.
POLL_TOLERANCE = timedelta(seconds=150)
#: Wider than this and the period's start is unknown: absent beats drawn late,
#: which is the first-score defect over again.
MAX_FIRST_SEEN_BRACKET = timedelta(minutes=20)

#: ESPN football status text. The overtime arm accepts the ordinal in either
#: position and with or without a space — `OT`, `2nd OT`, `2OT`, `Overtime 2` —
#: because a college game reaching a fourth overtime must not fold into the first
#: (#6718 finding 2: `(?:\d\w*\s+)?` swallowed the ordinal and every OT ranked
#: alike, so the `placed` dedupe dropped all but one).
_FOOTBALL_STATE = re.compile(
    r"^(?:(?P<clock>\d{1,2}:\d{2})\s*-\s*)?"
    r"(?P<end>end\s+of\s+)?"
    r"(?:"
    r"(?P<q>[1-4])(?:st|nd|rd|th)\s+quarter"
    r"|(?P<ht>half\s*time)"
    r"|(?:(?P<otpre>\d+)(?:st|nd|rd|th)?\s*)?(?:overtime|ot)(?:\s*(?P<otpost>\d+))?"
    r")$",
    re.IGNORECASE,
)

#: Ranks are spaced so a break can sit between two periods without colliding with
#: either: quarter q is `q*100`, its end `q*100+50`, halftime `260` (after the end
#: of the 2nd, before the 3rd), overtime n `500+(n-1)*100`. A rank orders the
#: game's states; it is never a duration.
_QUARTER_RANK = 100
_BREAK_OFFSET = 50
_HALFTIME_RANK = 260
_OVERTIME_BASE = 500


def _ordinal(n: int) -> str:
    """`1st`, `2nd`, `3rd`, `4th`… including the teens, which are all `th`."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _football_state(raw: Any) -> Optional[tuple[int, Optional[str]]]:
    """``(rank, served label)``, or ``None`` when this is not football state text.

    The label is ``None`` for a break we do not draw (`End of 1st Quarter`): it
    still ORDERS the stream, and it is one of the most useful lower bounds there
    is, but it is not a period a chart puts a chip on.
    """
    if not isinstance(raw, str):
        return None
    m = _FOOTBALL_STATE.match(raw.strip())
    if not m:
        return None  # "Final", a pre-game date string, another sport's text
    end = bool(m.group("end"))
    if m.group("q"):
        q = int(m.group("q"))
        rank = q * _QUARTER_RANK
        return (rank + _BREAK_OFFSET, None) if end else (rank, f"{_ordinal(q)} Quarter")
    if m.group("ht"):
        return (_HALFTIME_RANK + _BREAK_OFFSET, None) if end else (_HALFTIME_RANK, "Halftime")
    n_raw = m.group("otpre") or m.group("otpost")
    try:
        n = int(n_raw) if n_raw else 1
    except ValueError:
        n = 1
    n = max(n, 1)
    rank = _OVERTIME_BASE + (n - 1) * _QUARTER_RANK
    if end:
        return (rank + _BREAK_OFFSET, None)
    return (rank, "Overtime" if n == 1 else f"{_ordinal(n)} Overtime")


def observed_transition_markers(
    sport_key: Optional[str],
    observations: Iterable[dict],
) -> list[dict]:
    """Period markers from the game-state stream; ``[]`` when it cannot say.

    ``observations`` are ``{"timestamp", "period", "source"}`` rows from any
    state-bearing series (``espn_history``, ``win_prob_history[*].game_state``).
    ``source`` is carried onto the marker it produces, so the payload can say
    which instrument saw the transition rather than attributing every marker to
    one tier (#6718 finding 3); it falls back to :data:`SOURCE_WIN_PROB`.

    Every marker returned carries a real ``not_before``. See the module note
    above for the three shapes this refuses and why each one cost a wrong screen.
    """
    if not sport_key or not sport_key.startswith(TRANSITION_SPORT_PREFIXES):
        return []

    rows: list[tuple[datetime, int, Optional[str], Any, Any]] = []
    seen: set[tuple[datetime, int]] = set()
    for obs in observations or ():
        when = _parse((obs or {}).get("timestamp"))
        state = _football_state((obs or {}).get("period"))
        if when is None or state is None or (when, state[0]) in seen:
            continue
        seen.add((when, state[0]))
        rows.append((when, state[0], state[1], obs.get("timestamp"), obs.get("source")))
    if not rows:
        return []
    rows.sort(key=lambda r: (r[0], r[1]))

    # One capture instant carrying two different states is two sources
    # disagreeing, not a transition. It neither carries a marker nor bounds one.
    ranks_at: dict[datetime, set[int]] = {}
    for when, rank, *_ in rows:
        ranks_at.setdefault(when, set()).add(rank)
    contradictory = {when for when, ranks in ranks_at.items() if len(ranks) > 1}

    # A one-row forward blip — a lone sighting immediately retracted by an earlier
    # state — is not a sighting of that period. Its true start is then unbracketed,
    # so a later sighting can never be better than `first_seen`.
    #
    # THE RETRACTION MUST BE CORROBORATED, or this rule eats the stale-row case it
    # sits next to. "The next row is lower" is true both when THIS row is a
    # spurious forward jump and when a LAGGING SOURCE delivers one old state after
    # a perfectly good transition — opposite anomalies, identical one-row
    # lookahead. Requiring a second low row to agree separates them: a real blip is
    # followed by the stream continuing below it, while a stale delivery is a
    # single row the stream immediately climbs back over. Without this, a genuine
    # 3rd Quarter followed 44 minutes later by a lagging 2nd Quarter row lost its
    # marker entirely (measured while writing #6718).
    is_blip: list[bool] = []
    for i, (_w, rank, *_r) in enumerate(rows):
        retracted = i + 1 < len(rows) and rows[i + 1][1] < rank
        is_blip.append(retracted and i + 2 < len(rows) and rows[i + 2][1] < rank)

    # A row may bound a later marker only if it is non-contradictory, not a blip,
    # and does not regress below the running maximum — a regression is a stale row
    # delivered late, and it says nothing about the state at its own capture
    # instant. A blip is excluded from the running maximum for the same reason.
    can_bound: list[bool] = []
    running_max = -1
    for i, (when, rank, *_r) in enumerate(rows):
        if is_blip[i] or when in contradictory:
            can_bound.append(False)
            continue
        can_bound.append(rank >= running_max)
        running_max = max(running_max, rank)

    # First occurrence of each rank, BLIPS EXCLUDED. Counting the blip as the first
    # sighting is what made the genuine 3rd Quarter unreachable: the spurious row
    # owned the rank, and the real transition 43 minutes later was skipped as a
    # repeat (caught by `test_a_one_row_blip_into_the_next_period_is_not_its_start`).
    first_index: dict[int, int] = {}
    for i, (_w, rank, *_r) in enumerate(rows):
        if not is_blip[i]:
            first_index.setdefault(rank, i)

    markers: list[dict] = []
    placed: set[str] = set()
    unbracketed: set[str] = set()

    for i, (when, rank, label, raw_ts, source) in enumerate(rows):
        if is_blip[i]:
            if label:
                unbracketed.add(label)
            continue
        if label is None or label in placed or first_index.get(rank) != i:
            continue
        if when in contradictory:
            placed.add(label)  # seen, but the instant contradicts itself
            continue

        bound = None
        for j in range(i - 1, -1, -1):
            if can_bound[j] and rows[j][1] < rank and rows[j][0] < when:
                bound = rows[j]
                break
        if bound is None:
            # No observation places this period's start after anything. Absent,
            # never kickoff — and never dressed as an observation.
            placed.add(label)
            continue

        gap = when - bound[0]
        if label in unbracketed or gap > POLL_TOLERANCE:
            precision = PRECISION_FIRST_SEEN
        else:
            precision = PRECISION_BOUNDARY
        if gap > MAX_FIRST_SEEN_BRACKET:
            placed.add(label)  # seen, but its start is unknown
            continue

        placed.add(label)
        markers.append({
            "timestamp": raw_ts,
            "period": label,
            "source": source or SOURCE_WIN_PROB,
            "precision": precision,
            "not_before": bound[3],
        })
    return markers
