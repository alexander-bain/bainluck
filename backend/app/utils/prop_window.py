"""Has a window-bounded in-game prop's window already closed? (#1588)

Some game props ask about a bounded slice of a game rather than its outcome:
"a run in the first inning", "first 5 innings", "1st half", "1st quarter". Once
that slice is over, the question has an answer — and a market quoting a
probability for it is not stale in the ordinary sense of being a few minutes
old. It is the product asserting uncertainty about something the reader just
watched happen.

Alex's 2026-08-08 dogfood, live: **"Will there be a run scored in the first
inning?" showed 52% "No" while the first-inning run was already on the
scoreboard.** That is a direct violation of the standing *settled means settled*
ruling, and under the 2026-08-08(d) batch this class outranks all polish.

WHAT THIS MODULE DOES, AND DELIBERATELY DOES NOT DO
---------------------------------------------------
It answers one question: *can we PROVE this prop's window is over?* It does not
grade the prop — grading needs the resolution input (who scored, when) and
belongs with the resolver. Suppression is what a read path can do safely and
immediately, and against a false number an absent card is strictly better.

FAIL-SAFE DIRECTION
-------------------
Every branch defaults to **False — keep showing it**. On a game still in play a
prop is suppressed only when the sport, the window and the current period are
all positively identified and the period is unambiguously past the window. An
unparsed period string, an unknown sport, a market we cannot classify, a game
that is neither live nor finished: all keep the market visible.

The one place no inference is needed is after full time. A finished game closes
every recognised window outright — see ``prop_window_closed`` for why that is
proof rather than a guess, why it needs no period, and why the original
"a settled game is exempt" carve-out was hiding a live-looking 99% rather than
protecting a graded card.

That asymmetry is deliberate and is the guardrail from gotcha #43. Wrongly
hiding a live market is a visible product regression; wrongly showing one is the
bug we already have, so a partial fix that is never over-eager is a strict
improvement, while an over-eager one trades a known bug for an unknown one.
"""

from __future__ import annotations

import re

__all__ = [
    "parse_period_number",
    "prop_window",
    "prop_window_closed",
]


# ---------------------------------------------------------------------------
# Period parsing
# ---------------------------------------------------------------------------

# Baseball: "Top 5", "Bottom of the 3rd", "Inning 5 (Top)", "T5", "Mid 7", "5".
_BASEBALL_PERIOD_RE = re.compile(
    r"(?:\b(?:top|t|bot|bottom|b|mid|middle|end)\b(?:\s+of)?\s+(?:the\s+)?)?"
    r"(?:inning\s*)?(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:\s*(?:st|nd|rd|th)?\s*inning)?",
    re.IGNORECASE,
)

# Clock sports: "Q3", "3rd Quarter", "2H", "2nd Half", "P2", "OT".
_QUARTER_RE = re.compile(r"\bq(?:uarter)?\s*([1-4])\b|\b([1-4])(?:st|nd|rd|th)\s+quarter\b", re.IGNORECASE)
_HALF_RE = re.compile(r"\bh(?:alf)?\s*([12])\b|\b([12])(?:st|nd)?\s*h\b|\b(first|second|1st|2nd)\s+half\b", re.IGNORECASE)

# These MUST be matched on word boundaries, not with `in`. Substring matching
# here is silently catastrophic in both directions and this module was written
# with the bug before the tests caught it:
#   "ot" is inside "b-OT-tom"   -> every bottom-half inning parsed as overtime
#   "ft" is inside "hal-FT-ime" -> halftime parsed as full time
# Both then returned the "past everything" sentinel, which suppresses live
# markets — the exact over-eager direction the module promises never to take.
_OVERTIME_RE = re.compile(
    r"\b(?:ot\d?|overtime|extra\s+time|extra\s+innings?|shootout)\b", re.IGNORECASE
)
_HALFTIME_RE = re.compile(r"\b(?:halftime|half\s+time|ht|intermission)\b", re.IGNORECASE)
_FINAL_RE = re.compile(r"\b(?:final|ft|full\s+time|game\s+over|ended)\b", re.IGNORECASE)


#: The sentinel scale for overtime/final — past every regulation window on any
#: scale, so it is comparable with a window of any unit.
_PAST_ALL = "past_all"


def parse_period_scale(period: str | None, sport: str | None) -> tuple[str | None, int | None]:
    """``(scale, number)`` for the current period — the scale it is MEASURED on.

    ``scale`` is ``"inning"``, ``"half"``, ``"quarter"``, ``_PAST_ALL`` (overtime
    or final, past everything on every scale) or ``None`` when nothing can be
    proven.

    The scale is returned because the number alone is not comparable with a
    window. A basketball game reading "Q3" is period 3 on the QUARTER scale, and
    a "2nd Half" market judged against that number would compute ``3 > 2`` and
    suppress a market whose window is still open — Q3 is inside the second half.
    Comparing two scales is the over-eager direction this module promises never
    to take, so the caller must check that the scales agree.
    """
    if not period:
        return (None, None)

    text = str(period).strip().lower()
    if not text:
        return (None, None)

    # Overtime/extra time is past every regulation window, but we do not know
    # WHICH number it maps to across sports, so it gets its own sentinel via a
    # large value — every regulation window is closed by then.
    if _OVERTIME_RE.search(text) or _FINAL_RE.search(text):
        return (_PAST_ALL, 99)

    is_baseball = bool(sport and "baseball" in sport.lower())

    if is_baseball:
        match = _BASEBALL_PERIOD_RE.search(text)
        if match:
            try:
                inning = int(match.group(1))
            except (TypeError, ValueError):
                return (None, None)
            # Guard against nonsense like a 40-inning game or a stray score.
            if 1 <= inning <= 30:
                return ("inning", inning)
        return (None, None)

    # Halftime sits between half 1 and half 2 — the first half IS over.
    if _HALFTIME_RE.search(text):
        return ("half", 2)

    quarter = _QUARTER_RE.search(text)
    if quarter:
        value = quarter.group(1) or quarter.group(2)
        if value:
            return ("quarter", int(value))

    half = _HALF_RE.search(text)
    if half:
        value = half.group(1) or half.group(2)
        if value:
            return ("half", int(value))
        word = (half.group(3) or "").lower()
        if word in ("first", "1st"):
            return ("half", 1)
        if word in ("second", "2nd"):
            return ("half", 2)

    return (None, None)


def parse_period_number(period: str | None, sport: str | None) -> int | None:
    """The current period as an integer, or ``None`` when it cannot be proven.

    Baseball returns the inning; clock sports return the quarter or half as
    written. ``None`` means "unknown", never "period 0" — callers must treat it
    as "keep showing the market".

    This drops the scale. Use :func:`parse_period_scale` before comparing the
    number with a window, or a quarter will be compared with a half.
    """
    return parse_period_scale(period, sport)[1]


# ---------------------------------------------------------------------------
# Window classification
# ---------------------------------------------------------------------------

# Each entry: (matcher, sport_family, period AFTER which the window is closed).
#
# "closes_after" is the last period INSIDE the window. The window is over once
# the current period is strictly greater. First-inning props close after inning
# 1, so inning 2 proves it; first-5-innings close after inning 5.
_BASEBALL_WINDOWS: list[tuple[re.Pattern[str], int]] = [
    # NRFI / "run in the first inning" — the market Alex caught.
    (re.compile(r"\bfirst\s+inning\b|\b1st\s+inning\b|\bnrfi\b|\byrfi\b", re.IGNORECASE), 1),
    # "innings" is optional: production carries 2,109 rows named "First 5
    # Spread" against 2,186 "First 5 Innings Total" (measured 2026-09-10), and
    # the bare form is the one the reported specimen wore. Only reached when the
    # title or the sport key already says baseball, so "First 5" cannot pull in
    # a clock sport's market.
    #
    # `1st 5` IS THE SAME WINDOW SPELLED THE OTHER WAY, AND IT IS POLYMARKET'S
    # (CERT-2486). Only "first" was accepted here, while the first-INNING
    # pattern above took both spellings — so the numeral form was invisible.
    # Censused on production 2026-09-10, outcome names:
    #
    #     '%first 5%'  28,512      '%1st 5%'  2,224      '%1st 3%'  4
    #
    # and every sampled `1st 5` row is Polymarket wearing a generic matchup
    # title — 'Chicago White Sox vs. New York Yankees' / '1st 5 Innings Spread
    # -1.5' — so the outcome name is the only place the window appears at all.
    # Matched ahead of `_NTH_INNING_RE` for the same reason "First 5 Innings"
    # is: otherwise "1st 5 Innings" reads as the 1st inning and closes a market
    # four innings early.
    (re.compile(r"\b(?:first|1st)\s+(?:five|5)(?:\s+innings?)?\b|\bf5\b", re.IGNORECASE), 5),
    (re.compile(r"\b(?:first|1st)\s+(?:three|3)(?:\s+innings?)?\b|\bf3\b", re.IGNORECASE), 3),
    (re.compile(r"\b(?:first|1st)\s+(?:seven|7)(?:\s+innings?)?\b|\bf7\b", re.IGNORECASE), 7),
]

# A single inning: "2nd Inning Winner", "7th Inning Total". 918 "First 3
# Innings" + 257-a-piece per-inning rows sit on finished games quoting prices.
_NTH_INNING_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+innings?\b", re.IGNORECASE)

_CLOCK_WINDOWS: list[tuple[re.Pattern[str], str, int]] = [
    (re.compile(r"\bfirst\s+half\b|\b1st\s+half\b|\b1h\b", re.IGNORECASE), "half", 1),
    (re.compile(r"\bsecond\s+half\b|\b2nd\s+half\b|\b2h\b", re.IGNORECASE), "half", 2),
    (re.compile(r"\bfirst\s+quarter\b|\b1st\s+quarter\b|\b1q\b", re.IGNORECASE), "quarter", 1),
    (re.compile(r"\bsecond\s+quarter\b|\b2nd\s+quarter\b|\b2q\b", re.IGNORECASE), "quarter", 2),
    (re.compile(r"\bthird\s+quarter\b|\b3rd\s+quarter\b|\b3q\b", re.IGNORECASE), "quarter", 3),
    (re.compile(r"\bfourth\s+quarter\b|\b4th\s+quarter\b|\b4q\b", re.IGNORECASE), "quarter", 4),
]

# A market that names a period AND the full game is not window-bounded: it is
# still live until the final whistle. "1st Half / Fulltime Result" (76 rows) is
# the whole population of this shape on production, and classifying it as a
# first-half window would suppress a full-game market at halftime — the
# over-eager direction. Checked before any window pattern runs.
_SPANS_FULL_GAME_RE = re.compile(r"\bfull\s*time\b|\bfulltime\b|\bft\s*result\b", re.IGNORECASE)

# Kalshi ticker prefixes that encode the window even when the title does not.
# `KXMLBRFI` = MLB run-in-first-inning (see sport_keys.py).
_TICKER_WINDOWS: list[tuple[re.Pattern[str], str, int]] = [
    (re.compile(r"^kxmlbrfi", re.IGNORECASE), "inning", 1),
    (re.compile(r"^kxmlbf5", re.IGNORECASE), "inning", 5),
]


def _window_from_text(text: str, sport: str | None) -> tuple[str, int] | None:
    """The title-reading half of :func:`prop_window`, on one string.

    Split out so the market name and the OUTCOME name can be read by exactly the
    same rules (#1588 / CERT-2486) — a second copy of this ladder is how the two
    would drift apart.
    """
    if not text:
        return None

    is_baseball = bool(sport and "baseball" in sport.lower())
    # A title naming innings is baseball regardless of a missing sport key.
    if is_baseball or re.search(r"\binnings?\b|\bnrfi\b|\byrfi\b|\bf5\b", text, re.IGNORECASE):
        for pattern, closes_after in _BASEBALL_WINDOWS:
            if pattern.search(text):
                return ("inning", closes_after)
        # A single named inning, after the explicit windows so "First 5 Innings"
        # is not read as the 5th inning alone.
        nth = _NTH_INNING_RE.search(text)
        if nth:
            inning = int(nth.group(1))
            if 1 <= inning <= 30:
                return ("inning", inning)

    for pattern, unit, closes_after in _CLOCK_WINDOWS:
        if pattern.search(text):
            return (unit, closes_after)

    return None


def prop_window(
    name: str | None,
    ticker: str | None = None,
    sport: str | None = None,
    outcome: str | None = None,
) -> tuple[str, int] | None:
    """``(unit, closes_after)`` for a window-bounded prop, else ``None``.

    ``unit`` is ``"inning"``, ``"half"`` or ``"quarter"``. ``None`` means this is
    not a window-bounded prop — a full-game total, a moneyline, a season future —
    and it must never be suppressed by this rule.

    THREE PLACES NAME THE WINDOW, AND ONLY ONE OF THEM IS THE TITLE (CERT-2486)
    --------------------------------------------------------------------------
    The first cut of the caller passed the market name and a literal ``None``
    ticker, and two provider shapes measured on production walked straight
    through it:

        Kalshi      a generic title whose ``KXMLBRFI…`` TICKER is the only thing
                    that says "first inning"
        Polymarket  a generic matchup title where ``1st 5 Innings Spread -1.5``
                    appears ONLY in the outcome name

    So all three are read, in order of how structured they are: ticker, then
    title, then outcome.

    ``outcome`` IS SCOPED BY THE TITLE, WHICH IS WHY THE VETO MOVED UP. A row is
    one outcome of one market, so its own name identifies its own window — but
    only when the market it belongs to is window-bounded at all. If the TITLE
    spans the full game, nothing under it is window-bounded, whatever a
    particular outcome happens to be called; ``1st Half / Fulltime Result`` (76
    rows, the whole population of that shape) has outcomes that name a half and
    runs to the final whistle regardless. The veto therefore returns ``None`` for
    the market before the outcome is ever read.
    """
    text = (name or "").strip()
    tick = (ticker or "").strip()

    # Ticker first: it is structured, and Kalshi titles frequently omit the
    # window that the ticker encodes (gotcha #16 — prefer ticker-derived facts).
    for pattern, unit, closes_after in _TICKER_WINDOWS:
        if tick and pattern.search(tick):
            return (unit, closes_after)

    # A period-and-fulltime combined market runs to the final whistle — and so
    # does every outcome under it, so this is checked before either is read.
    if text and _SPANS_FULL_GAME_RE.search(text):
        return None

    window = _window_from_text(text, sport)
    if window is not None:
        return window

    otext = (outcome or "").strip()
    if not otext or _SPANS_FULL_GAME_RE.search(otext):
        return None
    return _window_from_text(otext, sport)


def prop_window_closed(
    name: str | None,
    ticker: str | None,
    sport: str | None,
    period: str | None,
    status: str | None,
    finished: bool = False,
    outcome: str | None = None,
) -> bool:
    """True only when the prop's window is PROVABLY over.

    For a live game this requires all of: a recognisable window, and a parseable
    current period strictly past that window. Anything missing returns False.

    ``finished`` — the caller's authoritative "this game is really over" verdict
    (`_event_is_really_finished`) — closes every recognised window on its own.
    The caller passes the verdict rather than a status string on purpose: the
    terminal state is `completed` OR `closed`, and that helper additionally
    refuses a row whose `commence_time` is still in the future (the corrupt
    shape of gotcha #32 / #46), which a status test here would wrongly settle.

    A FINISHED GAME IS NOW HANDLED, AND THE ORIGINAL EXEMPTION WAS WRONG
    -------------------------------------------------------------------
    This function first shipped refusing to look at a settled game at all, on
    the reasoning that a finished game's props show a graded result and
    suppressing them would hide the "WHAT HIT" surface. The premise turned out
    to be false for part of the population. Measured on production 2026-09-10:
    of the window-bounded props attached to finished games, 19,498 are
    `resolved` — those are WHAT HIT, and they are still not this rule's
    business — but **367 are still `status='open'`**, and they keep quoting.
    `/api/events/15308050/game-markets`, seven hours after full time, served
    "Tampa Bay vs Atlanta: First 5 Spread — Tampa Bay -1.5 first 5 innings" at
    **0.99** with no grade.

    So the exemption did not protect a graded card; it protected an ungraded one
    that was still asserting uncertainty about a finished game. WHAT HIT is
    preserved where it actually lives — at the caller, which keeps any row
    carrying an authoritative `resolution_source` regardless of this verdict.

    NO PERIOD IS REQUIRED ONCE THE GAME IS OVER, AND DEMANDING ONE WOULD BE
    INERT. Full time is not evidence that the window passed, it is proof: every
    in-game window is behind a final whistle. That is also the only form of the
    rule that reaches the bug — production stores `period = NULL` on the
    finished rows (event 15308050 is `period=None`), so a version that insisted
    on parsing the period would go green against a branch its own data can
    never enter.
    """
    if finished:
        return prop_window(name, ticker, sport, outcome) is not None

    if (status or "").strip().lower() != "live":
        return False

    window = prop_window(name, ticker, sport, outcome)
    if window is None:
        return False

    unit, closes_after = window
    scale, current = parse_period_scale(period, sport)
    if scale is None or current is None:
        return False

    # SCALE SANITY. The number is only comparable with the window when both are
    # measured on the same thing. Overtime/final is past everything on every
    # scale, so it is the one value that compares with any window; otherwise the
    # scales must match outright. Without this, "2nd Half Total" during "Q3"
    # computes 3 > 2 and suppresses a market whose window is still open, and a
    # first-inning window judged against a quarter would do the same.
    if scale != _PAST_ALL and scale != unit:
        return False

    return current > closes_after
