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
Every branch defaults to **False — keep showing it**. A prop is suppressed only
when the sport, the window and the current period are all positively
identified and the period is unambiguously past the window. An unparsed period
string, an unknown sport, a market we cannot classify, a game that is not live:
all keep the market visible.

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


def parse_period_number(period: str | None, sport: str | None) -> int | None:
    """The current period as an integer, or ``None`` when it cannot be proven.

    Baseball returns the inning; clock sports return the quarter or half as
    written. ``None`` means "unknown", never "period 0" — callers must treat it
    as "keep showing the market".
    """
    if not period:
        return None

    text = str(period).strip().lower()
    if not text:
        return None

    # Overtime/extra time is past every regulation window, but we do not know
    # WHICH number it maps to across sports, so it gets its own sentinel via a
    # large value — every regulation window is closed by then.
    if _OVERTIME_RE.search(text) or _FINAL_RE.search(text):
        return 99

    is_baseball = bool(sport and "baseball" in sport.lower())

    if is_baseball:
        match = _BASEBALL_PERIOD_RE.search(text)
        if match:
            try:
                inning = int(match.group(1))
            except (TypeError, ValueError):
                return None
            # Guard against nonsense like a 40-inning game or a stray score.
            if 1 <= inning <= 30:
                return inning
        return None

    # Halftime sits between half 1 and half 2 — the first half IS over.
    if _HALFTIME_RE.search(text):
        return 2

    quarter = _QUARTER_RE.search(text)
    if quarter:
        value = quarter.group(1) or quarter.group(2)
        if value:
            return int(value)

    half = _HALF_RE.search(text)
    if half:
        value = half.group(1) or half.group(2)
        if value:
            return int(value)
        word = (half.group(3) or "").lower()
        if word in ("first", "1st"):
            return 1
        if word in ("second", "2nd"):
            return 2

    return None


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
    (re.compile(r"\bfirst\s+(?:five|5)\s+innings\b|\bf5\b", re.IGNORECASE), 5),
    (re.compile(r"\bfirst\s+three\s+innings\b|\bf3\b", re.IGNORECASE), 3),
]

_CLOCK_WINDOWS: list[tuple[re.Pattern[str], str, int]] = [
    (re.compile(r"\bfirst\s+half\b|\b1st\s+half\b|\b1h\b", re.IGNORECASE), "half", 1),
    (re.compile(r"\bfirst\s+quarter\b|\b1st\s+quarter\b|\b1q\b", re.IGNORECASE), "quarter", 1),
    (re.compile(r"\bsecond\s+quarter\b|\b2nd\s+quarter\b|\b2q\b", re.IGNORECASE), "quarter", 2),
    (re.compile(r"\bthird\s+quarter\b|\b3rd\s+quarter\b|\b3q\b", re.IGNORECASE), "quarter", 3),
]

# Kalshi ticker prefixes that encode the window even when the title does not.
# `KXMLBRFI` = MLB run-in-first-inning (see sport_keys.py).
_TICKER_WINDOWS: list[tuple[re.Pattern[str], str, int]] = [
    (re.compile(r"^kxmlbrfi", re.IGNORECASE), "inning", 1),
    (re.compile(r"^kxmlbf5", re.IGNORECASE), "inning", 5),
]


def prop_window(
    name: str | None,
    ticker: str | None = None,
    sport: str | None = None,
) -> tuple[str, int] | None:
    """``(unit, closes_after)`` for a window-bounded prop, else ``None``.

    ``unit`` is ``"inning"``, ``"half"`` or ``"quarter"``. ``None`` means this is
    not a window-bounded prop — a full-game total, a moneyline, a season future —
    and it must never be suppressed by this rule.
    """
    text = (name or "").strip()
    tick = (ticker or "").strip()

    # Ticker first: it is structured, and Kalshi titles frequently omit the
    # window that the ticker encodes (gotcha #16 — prefer ticker-derived facts).
    for pattern, unit, closes_after in _TICKER_WINDOWS:
        if tick and pattern.search(tick):
            return (unit, closes_after)

    if not text:
        return None

    is_baseball = bool(sport and "baseball" in sport.lower())
    # A title naming innings is baseball regardless of a missing sport key.
    if is_baseball or re.search(r"\binnings?\b|\bnrfi\b|\byrfi\b|\bf5\b", text, re.IGNORECASE):
        for pattern, closes_after in _BASEBALL_WINDOWS:
            if pattern.search(text):
                return ("inning", closes_after)

    for pattern, unit, closes_after in _CLOCK_WINDOWS:
        if pattern.search(text):
            return (unit, closes_after)

    return None


def prop_window_closed(
    name: str | None,
    ticker: str | None,
    sport: str | None,
    period: str | None,
    status: str | None,
) -> bool:
    """True only when the prop's window is PROVABLY over.

    Requires all of: a live game, a recognisable window, and a parseable current
    period strictly past that window. Anything missing returns False.

    A settled game is intentionally NOT handled here — a finished game's props
    should show a graded result, which is the resolver's job, and suppressing
    them would hide the "WHAT HIT" surface that is supposed to show them.
    """
    if (status or "").strip().lower() != "live":
        return False

    window = prop_window(name, ticker, sport)
    if window is None:
        return False

    unit, closes_after = window
    current = parse_period_number(period, sport)
    if current is None:
        return False

    # Unit sanity: an inning window judged against a quarter-shaped period (or
    # vice versa) would be comparing different scales. Baseball periods only
    # parse for baseball, so the remaining risk is a clock sport whose window
    # says "inning" — refuse rather than guess.
    is_baseball = bool(sport and "baseball" in sport.lower())
    if unit == "inning" and not is_baseball and current != 99:
        return False

    return current > closes_after
