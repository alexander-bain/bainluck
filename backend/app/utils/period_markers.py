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
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, NamedTuple, Optional

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
        if sport_key.startswith("basketball_ncaab"):
            # Men's college basketball: 2 halves of 20 min each
            return [at(0, "1st Half"), at(55, "2nd Half")]
        if sport_key.startswith("basketball_nba"):
            # NBA: 4 quarters of 12 min each (real-time ~30-35 min per quarter)
            return [
                at(0, "1st Quarter"), at(33, "2nd Quarter"),
                at(80, "3rd Quarter"), at(113, "4th Quarter"),
            ]
        # Everyone else plays 4 quarters of 10 min (#10069): FIBA — EuroLeague,
        # NBL, the Olympics — and the WNBA and women's college game (see
        # `sport_keys.py`'s period table: wncaab is quarters, not halves). The
        # NBA table drew EuroLeague's '~Q4' on the final whistle of 15292394
        # (last reading +113). Three WNBA finals games (2026-09-29/30) measured
        # quarter starts at ~+31/+74/+102 from the listed time; FIBA runs
        # tighter, with fewer timeouts.
        return [
            at(0, "1st Quarter"), at(27, "2nd Quarter"),
            at(70, "3rd Quarter"), at(97, "4th Quarter"),
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
# Football, plus four EXACT basketball keys (#10851) — see `_BASKETBALL_LEAGUES`.
# The vocabulary is ESPN's status text, which a row's period carries verbatim;
# innings, sets, soccer halves, hockey periods and every other basketball league
# keep the existing tiers untouched.
#
# This prefix tuple still means FOOTBALL to `routes/events.py`, which also gates
# the first-score label, the unresolved-play skip and the win-prob label tier on
# it. Those were measured on football (#5140/#6718/#9179) and do not widen here;
# the observed-transition call alone asks :func:`observes_period_transitions`.
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
#: A football quarter's clock before its first second has run (#9179).
_QUARTER_OPENING_CLOCK = "15:00"


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


def _football_clock(raw: Any) -> Optional[str]:
    """The game clock on a football state row (`'14:44'`), or ``None``."""
    if not isinstance(raw, str):
        return None
    m = _FOOTBALL_STATE.match(raw.strip())
    return m.group("clock") if m else None


#: ESPN basketball status text (#10851), which differs from football's in two
#: places. The last minute of a period carries tenths (`0:04.2 - 4th Quarter`,
#: `game_state._GAME_CLOCK_RE`), so the clock takes an optional tail. And the
#: men's college game is played in halves (`End of 2nd Half` is in the measured
#: vocabulary, `test_live_state_does_not_run_backwards_6056.py`), so the period
#: word is captured and checked against the league rather than assumed.
#: Measured basketball shapes: `7:40 - 3rd Quarter` and `End of 4th Quarter`
#: (women's college, #5588), `End of 3rd Quarter` (NBA/WNBA), `Halftime`,
#: `End of OT`, `End of 2OT`.
_BASKETBALL_STATE = re.compile(
    r"^(?:(?P<clock>\d{1,2}:\d{2}(?:\.\d+)?)\s*-\s*)?"
    r"(?P<end>end\s+of\s+)?"
    r"(?:"
    r"(?P<n>[1-4])(?:st|nd|rd|th)\s+(?P<word>quarter|half)"
    r"|(?P<ht>half\s*time)"
    r"|(?:(?P<otpre>\d+)(?:st|nd|rd|th)?\s*)?(?:overtime|ot)(?:\s*(?P<otpost>\d+))?"
    r")$",
    re.IGNORECASE,
)


class _League(NamedTuple):
    """How one league's state text reads: its period word, how many regulation
    periods it plays, and the clock a period shows before its first second."""

    word: str
    periods: int
    opening_clock: str


#: Exact keys, never a prefix: `basketball_euroleague` and the rest have no
#: measured vocabulary here and keep the existing tiers. NBA quarters are 12
#: minutes; WNBA and the women's college game play 10-minute quarters; the men's
#: college game plays two 20-minute halves (`sport_keys.py`'s period table).
_BASKETBALL_LEAGUES: dict[str, _League] = {
    "basketball_nba": _League("quarter", 4, "12:00"),
    "basketball_wnba": _League("quarter", 4, "10:00"),
    "basketball_wncaab": _League("quarter", 4, "10:00"),
    "basketball_ncaab": _League("half", 2, "20:00"),
}


def observes_period_transitions(sport_key: Optional[str]) -> bool:
    """True when :func:`observed_transition_markers` can read this sport's stream."""
    if not sport_key:
        return False
    return sport_key.startswith(TRANSITION_SPORT_PREFIXES) or sport_key in _BASKETBALL_LEAGUES


def _basketball_state(raw: Any, league: _League) -> Optional[tuple[int, Optional[str]]]:
    """``(rank, served label)`` for one league's basketball state text, or ``None``.

    Same ranks as football — period n is ``n*100``, its end ``n*100+50``,
    overtime n ``500+(n-1)*100`` — except halftime, which sits after the end of
    the league's middle period: ``260`` for quarters, ``160`` for halves. A period
    word the league does not play (`1st Half` in the NBA, `1st Quarter` in the
    men's college game) or a period past its regulation count is not this
    league's state and reads as ``None``, like any other unknown text.
    `End of Halftime` is refused too: no basketball row has been seen to carry it,
    and its football rank would sit above the next period. So is a clock longer
    than the league's period (`15:00` in the NBA): that row is not this league's
    game, whatever its label says.
    """
    if not isinstance(raw, str):
        return None
    m = _BASKETBALL_STATE.match(raw.strip())
    if not m:
        return None
    clock = _clock_seconds(m.group("clock"))
    if clock is not None and clock > _clock_seconds(league.opening_clock):
        return None
    end = bool(m.group("end"))
    if m.group("n"):
        n = int(m.group("n"))
        if m.group("word").lower() != league.word or n > league.periods:
            return None
        rank = n * _QUARTER_RANK
        if end:
            return (rank + _BREAK_OFFSET, None)
        return (rank, f"{_ordinal(n)} {league.word.capitalize()}")
    if m.group("ht"):
        if end:
            return None
        return ((league.periods // 2) * _QUARTER_RANK + 60, "Halftime")
    n_raw = m.group("otpre") or m.group("otpost")
    n = max(int(n_raw), 1) if n_raw else 1
    rank = _OVERTIME_BASE + (n - 1) * _QUARTER_RANK
    if end:
        return (rank + _BREAK_OFFSET, None)
    return (rank, "Overtime" if n == 1 else f"{_ordinal(n)} Overtime")


def _basketball_clock(raw: Any) -> Optional[str]:
    """The game clock on a basketball state row (`'11:44'`, `'0:04.2'`), or ``None``."""
    if not isinstance(raw, str):
        return None
    m = _BASKETBALL_STATE.match(raw.strip())
    return m.group("clock") if m else None


class _Reader(NamedTuple):
    """One sport's state parser plus what the clock brackets need to know."""

    state: Callable[[Any], Optional[tuple[int, Optional[str]]]]
    clock: Callable[[Any], Optional[str]]
    periods: int
    opening_clock: str


def _reader_for(sport_key: str) -> Optional[_Reader]:
    if sport_key.startswith(TRANSITION_SPORT_PREFIXES):
        return _Reader(_football_state, _football_clock, 4, _QUARTER_OPENING_CLOCK)
    league = _BASKETBALL_LEAGUES.get(sport_key)
    if league is None:
        return None
    return _Reader(
        lambda raw: _basketball_state(raw, league),
        _basketball_clock,
        league.periods,
        league.opening_clock,
    )


def football_period_label(raw: Any) -> Optional[str]:
    """The period a football state row is IN (`'1st Quarter'`), clock stripped.

    ``None`` for a break (`End of 1st Quarter`) and for text that is not football
    state at all (a pre-game date string, `Final`). The win-prob tier keys on this
    so `15:00 - 1st Quarter` and `14:51 - 1st Quarter` are one period, not two
    markers (#9179).
    """
    state = _football_state(raw)
    return state[1] if state else None


def _opening_clock_bracket(
    rows: list,
    i: int,
    can_bound: list[bool],
    periods: int = 4,
    opening_clock: str = _QUARTER_OPENING_CLOCK,
) -> Optional[tuple[int, int]]:
    """``(last opening-clock row, first running-clock row)`` for the quarter first
    seen at ``rows[i]``, or ``None``.

    #9179: the first period of a stream has no earlier STATE to bound it — the
    stream opens on `15:00 - 1st Quarter` — so it got no marker and the chain fell
    to the first-SCORE tier (Q1 drawn at LAC@BUF's touchdown, 7.5 min late; on
    SEA@WSH 17.5). But the quarter's own clock brackets it: at the last `15:00`
    reading no second of it had run, and by the first reading below that it had.
    That is a lower and an upper bound from two observations, which is what #6718
    demands — NOT a start clock standing in for the bracket. A lone `15:00` with
    nothing after it, or a stream that opens already running, gets nothing HERE;
    the second case is :func:`_kickoff_bracket`'s, when the caller has a kickoff.

    It is only ever `first_seen`: the clock can sit at 15:00 through a touchback
    kickoff, so "the clock had not run" is a slightly later instant than "the
    quarter had not begun". Quarters only; an overtime clock's opening value is not
    fixed (10:00 regular season, 15:00 playoffs), and every overtime follows a
    4th quarter the transition tier already brackets it from.

    Basketball (#10851) passes its own regulation count and opening clock —
    `12:00` NBA, `10:00` WNBA and women's college, `20:00` for the men's college
    halves. A basketball clock does not run until the tip, so there the bracket is
    if anything tighter than football's.
    """
    rank = rows[i][1]
    if rank % _QUARTER_RANK or not (_QUARTER_RANK <= rank <= periods * _QUARTER_RANK):
        return None
    opening = _clock_seconds(opening_clock)
    last_open: Optional[int] = None
    for j in range(i, len(rows)):
        r, clock = rows[j][1], rows[j][5]
        if r != rank:
            # Another period's row. A later row of THIS period after the stream
            # moved on is a regression, which `can_bound` already refuses.
            continue
        if not can_bound[j] or clock is None:
            continue
        if _clock_seconds(clock) == opening:
            last_open = j
        elif last_open is not None:
            return (last_open, j)
        else:
            return None  # opened already running: nothing earlier to bound it
    return None


def _clock_seconds(clock: Optional[str]) -> Optional[int]:
    """`'14:55'` → 895, or ``None``.

    A tenths tail (`'0:04.2'`, basketball's last minute) is cut, never rounded:
    whole seconds left can only understate the time remaining, which overstates
    the game time run and so only ever makes the clock-versus-wall check stricter.
    """
    if not clock:
        return None
    minutes, _, seconds = clock.partition(":")
    try:
        return int(minutes) * 60 + int(seconds.split(".", 1)[0])
    except ValueError:
        return None


def _kickoff_bracket(
    rows: list,
    i: int,
    can_bound: list[bool],
    kickoff: Optional[datetime],
    opening_clock: str = _QUARTER_OPENING_CLOCK,
) -> bool:
    """True when the listed kickoff bounds a 1st quarter whose stream opened running.

    #9179, the arm `_opening_clock_bracket` leaves out. SNF LAR@DEN 14780548
    (2026-09-28): `espn_history[0]` was `00:23:51Z 14:55 - 1st Quarter`, no `15:00`
    row, so Q1 got nothing and the chain fell to the first-SCORE tier — the Rams
    touchdown at 00:49:52Z, 26 minutes into the quarter, and the line moved on a
    held page (ux notice-42 frames 17:33 vs 17:53 PT).

    The listed kickoff is a schedule fact, not an observation, so it is only ever
    the LOWER end (`not_before`); the marker still stands on the first running
    reading, `first_seen`. A scheduled time is not an actual start (Alex 9/14), and
    this never claims one. Two conditions make it a bound rather than a guess:

    * the bracket fits `MAX_FIRST_SEEN_BRACKET`, like every other `first_seen`;
    * the quarter's clock has run no more game time than wall time has passed
      since kickoff. A clock cannot outrun the wall (#9020), so a reading that is
      further along than that proves the game began BEFORE the listed kickoff —
      the listing is then no lower bound at all, and there is no marker.

    1st quarter only: every later quarter follows a state the transition tier
    already brackets it from. Basketball (#10851) applies the same rule to its
    first period against its own opening clock. The listed tip is still only the
    lower end, and the marker still stands on an observed running reading.
    """
    if kickoff is None or not can_bound[i]:
        return False
    when, rank, clock = rows[i][0], rows[i][1], rows[i][5]
    opening = _clock_seconds(opening_clock)
    run = _clock_seconds(clock)
    if rank != _QUARTER_RANK or clock is None or run == opening:
        return False
    if run is None or run > opening:
        return False
    wall = when - kickoff
    if wall > MAX_FIRST_SEEN_BRACKET:
        return False
    # Also refuses a reading taken AT or BEFORE the listing: a running clock has
    # spent more than zero game time, and zero or negative wall time cannot hold it.
    return timedelta(seconds=opening - run) <= wall


def observed_transition_markers(
    sport_key: Optional[str],
    observations: Iterable[dict],
    *,
    kickoff_not_before: Any = None,
) -> list[dict]:
    """Period markers from the game-state stream; ``[]`` when it cannot say.

    ``observations`` are ``{"timestamp", "period", "source"}`` rows from any
    state-bearing series (``espn_history``, ``win_prob_history[*].game_state``).
    ``source`` is carried onto the marker it produces, so the payload can say
    which instrument saw the transition rather than attributing every marker to
    one tier (#6718 finding 3); it falls back to :data:`SOURCE_WIN_PROB`.

    Every marker returned carries a real ``not_before``. See the module note
    above for the three shapes this refuses and why each one cost a wrong screen.

    ``kickoff_not_before`` is the row's LISTED kickoff, passed only when it is a
    kickoff and not a venue's expected resolution (#7878). It bounds nothing but
    a 1st quarter whose stream opened already running (:func:`_kickoff_bracket`).

    Football, and the four basketball keys in `_BASKETBALL_LEAGUES` (#10851); every
    other sport returns ``[]``. Basketball runs the identical bracket logic below.
    Only the parser, the regulation count and the opening clock differ.
    """
    reader = _reader_for(sport_key) if sport_key else None
    if reader is None:
        return []
    kickoff = _parse(kickoff_not_before) if kickoff_not_before is not None else None
    if kickoff is not None and kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)

    rows: list[tuple[datetime, int, Optional[str], Any, Any, Optional[str]]] = []
    seen: set[tuple[datetime, int]] = set()
    for obs in observations or ():
        when = _parse((obs or {}).get("timestamp"))
        state = reader.state((obs or {}).get("period"))
        if when is None or state is None or (when, state[0]) in seen:
            continue
        seen.add((when, state[0]))
        rows.append((
            when, state[0], state[1], obs.get("timestamp"), obs.get("source"),
            reader.clock(obs.get("period")),
        ))
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

    for i, (when, rank, label, raw_ts, source, _clock) in enumerate(rows):
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
            # No earlier STATE places this period's start after anything. The one
            # bracket left is the period's own clock leaving its opening value
            # (#9179) — without it, absent, never kickoff.
            clock_bracket = _opening_clock_bracket(
                rows, i, can_bound, reader.periods, reader.opening_clock
            )
            if clock_bracket is None:
                placed.add(label)
                if _kickoff_bracket(rows, i, can_bound, kickoff, reader.opening_clock):
                    markers.append({
                        "timestamp": raw_ts,
                        "period": label,
                        "source": source or SOURCE_WIN_PROB,
                        "precision": PRECISION_FIRST_SEEN,
                        "not_before": kickoff.isoformat(),
                    })
                continue
            last_open, first_run = clock_bracket
            placed.add(label)
            if rows[first_run][0] - rows[last_open][0] <= MAX_FIRST_SEEN_BRACKET:
                markers.append({
                    "timestamp": rows[first_run][3],
                    "period": label,
                    "source": rows[first_run][4] or SOURCE_WIN_PROB,
                    "precision": PRECISION_FIRST_SEEN,
                    "not_before": rows[last_open][3],
                })
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
