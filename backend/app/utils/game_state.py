"""Display helpers for live game state labels."""

from __future__ import annotations

import re


# Pre-game status_detail strings like "Wed, March 25th at 10:00 PM EDT" should
# not be stored as period values. Lives here rather than in the ESPN task
# module (#5390): it is a pure statement about period strings, this module
# imports nothing but `re`, and its old home forced every caller in
# `utils/espn_helpers.py` into a function-local import to dodge a real cycle.
#
# ESPN writes the pre-game detail in TWO shapes and the pattern only knew the
# long one. The short numeric form ("5/23 - TBD") reached production and sat in
# `events.period`. The `\d{1,2}/\d{1,2}` branch requires a digit on BOTH sides
# of the slash, which is what keeps it off the real period vocabulary —
# "Final/10", "Final/2OT" and "Final/SO" all carry a letter before the slash.
# Measured against the whole `events` table, the branch newly matches 5 rows
# and every one of them is a date.
_PREGAME_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b"
    r"|\b\d{1,2}/\d{1,2}\b",
    re.IGNORECASE,
)


def _sanitize_period(status_detail: str | None) -> str | None:
    """Return status_detail if it looks like a game period, else None."""
    if not status_detail:
        return None
    if _PREGAME_DATE_RE.search(status_detail):
        return None
    return status_detail


_BASEBALL_HALF_ALIASES = {
    "top": "Top",
    "t": "Top",
    "bot": "Bottom",
    "bottom": "Bottom",
    "b": "Bottom",
    "mid": "Mid",
    "middle": "Mid",
    "end": "End",
}
_NON_BASEBALL_PERIODS = {"1h", "2h", "ht", "halftime", "1st half", "2nd half"}


def _ordinal_inning(value: str) -> str | None:
    try:
        inning = int(value)
    except (TypeError, ValueError):
        return None
    if inning <= 0:
        return None
    if 10 <= inning % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(inning % 10, "th")
    return f"{inning}{suffix}"


def _baseball_inning_label(value: str | None) -> str | None:
    if not value:
        return None

    text = str(value).strip()
    lowered = text.lower().strip()
    if lowered in _NON_BASEBALL_PERIODS:
        return None

    half_match = re.search(
        r"\b(top|t|bot|bottom|b|mid|middle|end)\b(?:\s+of)?\s+"
        r"(?:the\s+)?(\d+)(?:st|nd|rd|th)?(?:\s+inning)?\b",
        lowered,
    )
    if half_match:
        half = _BASEBALL_HALF_ALIASES[half_match.group(1)]
        inning = _ordinal_inning(half_match.group(2))
        return f"{half} {inning}" if inning else None

    inning_match = re.search(
        r"\b(?:inning\s+)?(\d+)(?:st|nd|rd|th)?(?:\s+inning)?\b",
        lowered,
    )
    if inning_match and ("inning" in lowered or lowered.isdigit()):
        return _ordinal_inning(inning_match.group(1))

    return None


def normalize_live_game_state(
    sport_key: str | None,
    period: str | None,
    game_clock: str | None,
) -> tuple[str | None, str | None]:
    """Return display-safe ``(period, game_clock)`` for API payloads."""
    if not sport_key or not sport_key.startswith("baseball"):
        return period, game_clock

    inning_label = _baseball_inning_label(period) or _baseball_inning_label(game_clock)
    return inning_label, None


# ─── #6056: WHERE A LIVE ROW IS IN ITS OWN GAME, SO TWO WRITERS CAN BE ORDERED ──
#
# `events.home_score` / `away_score` / `game_clock` / `period` have at least two
# unarbitrated writers on a live row — `espn_helpers.update_event_fields_from_espn`
# and `statpal_sync._sync_statpal_livescores` — and each one writes whatever it
# just fetched. Last write wins, so when the two feeds disagree the served state
# does not converge, it ALTERNATES. Measured on production in our own
# `score_snapshots` table for event 14637256 (Giants v Cowboys, 2026-09-14), the
# two writers are separable by their cadence offsets, `:37` and `:09`:
#
#     02:58:37  28–14   <- ESPN     03:11:37  28–20   <- ESPN
#     02:59:09  21–14   <- other    03:12:09  28–14   <- other
#     02:59:37  28–14   <- ESPN     03:12:37  28–20   <- ESPN
#     03:00:09  27–14   <- other    03:13:09  28–14   <- other
#     03:00:37  28–14   <- ESPN     03:13:39  28–20   <- ESPN
#
# A reader watching that page saw a point un-score itself, and later a
# touchdown leave the page for a minute and come back. ESPN's own snapshots over
# the same window are strictly monotonic, so neither feed is "corrupt" — the
# second one is simply BEHIND, and nothing stops a behind observation
# overwriting an ahead one.
#
# ── WHY THIS ORDERS BY GAME TIME AND NEVER LOOKS AT THE SCORE ──
#
# The obvious guard — "a score may not go down" — is the wrong one and was
# rejected. A score going down is exactly what a legitimate correction looks
# like: a touchdown reversed on review, a point taken off after a penalty. A
# monotonic clamp would pin the first wrong number ever written and call it
# truth, which is a worse failure than the flicker because it never heals.
#
# So the discriminator is WHEN the observation was taken, in game time, and the
# score is not consulted at all. An observation positioned strictly EARLIER in
# the game than the state already stored cannot be news, whatever it says; one
# positioned at or after it is accepted, whatever it says — including a lower
# score. That is the whole rule.
#
# ── IT ONLY REFUSES WHAT IT CAN PROVE, AND IT CANNOT DEADLOCK ──
#
# Unparseable on EITHER side ⇒ no refusal. A position this function cannot
# locate is not evidence of staleness, and a guard that blocks writes it does
# not understand would freeze a live game — far worse than the flicker it is
# fixing. Equal positions are accepted too, so a same-moment correction lands.
#
# There is also no way for a refusal to become permanent. The bar is the STORED
# position, which the game itself moves past: if the ahead writer falls silent,
# the behind writer catches up to the frozen bar within a minute or two and is
# accepted again. Nothing needs a timeout, and no writer is declared the winner
# — the ordering is symmetric, so whichever feed is ahead at that instant wins
# that instant.

#: `M:SS`, `MM:SS` or `MMM:SS`, with an optional tenths tail (ESPN serves
#: `0:04.2` inside the final minute of a period). Anchored: a clock is the whole
#: field or it is not a clock.
_GAME_CLOCK_RE = re.compile(r"^\s*(\d{1,3}):([0-5]\d)(?:\.\d+)?\s*$")

#: The countdown families, measured off `espn_snapshots.period` over two days of
#: production (2026-09-12/14): `'5:21 - 4th Quarter'` for football, and `Period`
#: for the hockey shape of the same string. Both count DOWN, which is what makes
#: a smaller remaining time LATER in the game.
#:
#: `Half` is deliberately absent. Soccer's clock counts UP and college
#: basketball's counts DOWN, so one `Half` label cannot be given a direction
#: from the string alone, and guessing it would invert the comparison for a
#: whole sport. Those rows fall through to "unparseable", i.e. today's
#: behaviour.
_COUNTDOWN_PERIOD_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)\s+(?:quarter|period)\b", re.IGNORECASE
)

#: `'End of 3rd Quarter'` — the same period at its last instant. Given remaining
#: `0`, which sorts it after every clocked observation in that period and before
#: the next one, with no special case anywhere else.
_END_OF_PERIOD_RE = re.compile(
    r"\bend\s+of\s+(\d{1,2})(?:st|nd|rd|th)\s+(?:quarter|period)\b", re.IGNORECASE
)

#: `'OT'`, `'2OT'`, `'Overtime'` — measured on NFL rows as `'10:00 - OT'`. Ranked
#: after regulation for every sport that uses the label (4 quarters, 3 hockey
#: periods, 4 basketball quarters all end below 5).
_OVERTIME_RE = re.compile(r"\b(\d)?\s*(?:ot|overtime)\b", re.IGNORECASE)
_REGULATION_PERIODS = 4

#: TERMINAL LABELS ARE REFUSED BEFORE ANYTHING ELSE IS TRIED, and this is not
#: belt-and-braces — the measured vocabulary contains `'Final/OT'` and
#: `'Final/4OT'`, which the overtime branch below would otherwise place as a
#: LIVE overtime position (and `'Final/4OT'` as the fourth one, ranked above
#: every real moment of the game). A finished row is not a position in a running
#: game; the guard has nothing to say about one and must not pretend otherwise.
#: Caught by `test_unplaceable_labels_are_none[Final/OT]`, not by reading.
_TERMINAL_LABEL_RE = re.compile(
    r"\bfinal\b|\bft\b|\bfull[- ]time\b|\bended\b|\bpostponed\b"
    r"|\bcancell?ed\b|\babandoned\b",
    re.IGNORECASE,
)

#: Baseball has no clock, so its ordering is entirely in the label: two
#: half-innings per inning, top before bottom. Measured vocabulary is exactly
#: `'Top 9th'` / `'Bottom 2nd'`.
_HALF_INNING_RANK = {"top": 1, "bottom": 2}
_HALF_INNING_RE = re.compile(
    r"\b(top|bottom)\s+(\d{1,2})(?:st|nd|rd|th)\b", re.IGNORECASE
)


def _clock_remaining_seconds(*candidates: str | None) -> float | None:
    """Seconds left in the period, from the first candidate that is a clock.

    Both live writers compose `period` as ``f"{clock} - {label}"`` (#5017 made
    StatPal byte-identical to ESPN on purpose), so the clock is usually readable
    off the period string itself; the separate ``game_clock`` column is the
    fallback for a writer that only fills one of them.
    """
    for candidate in candidates:
        if not candidate:
            continue
        match = _GAME_CLOCK_RE.match(str(candidate))
        if match:
            return int(match.group(1)) * 60 + int(match.group(2))
        # `'5:21 - 4th Quarter'`: take the clock off the front, if there is one.
        head = str(candidate).split(" - ", 1)[0]
        match = _GAME_CLOCK_RE.match(head)
        if match:
            return int(match.group(1)) * 60 + int(match.group(2))
    return None


def live_progress_position(
    period: str | None, game_clock: str | None
) -> tuple[float, float] | None:
    """Where this observation sits in its own game, or ``None`` if unreadable.

    Returns ``(period_rank, elapsed_key)``, comparable with ``<``: a LARGER
    tuple is LATER in the game. ``elapsed_key`` is the negated seconds remaining
    for countdown sports, so a smaller clock sorts later without the caller
    having to know which way the clock runs.

    ``None`` means "cannot locate this observation", which every caller must
    treat as "no evidence", never as "earliest". See the module note above.
    """
    if not period:
        return None
    text = str(period).strip()
    if not text:
        return None
    if _TERMINAL_LABEL_RE.search(text):
        return None

    end_of = _END_OF_PERIOD_RE.search(text)
    if end_of:
        return (float(end_of.group(1)), 0.0)

    half_inning = _HALF_INNING_RE.search(text)
    if half_inning:
        inning = int(half_inning.group(2))
        half = _HALF_INNING_RANK[half_inning.group(1).lower()]
        return (float(inning * 2 + half), 0.0)

    countdown = _COUNTDOWN_PERIOD_RE.search(text)
    if countdown:
        remaining = _clock_remaining_seconds(text, game_clock)
        if remaining is None:
            return None
        return (float(countdown.group(1)), -remaining)

    overtime = _OVERTIME_RE.search(text)
    if overtime:
        # `'OT'` is the first overtime; `'2OT'` the second.
        nth = int(overtime.group(1)) if overtime.group(1) else 1
        remaining = _clock_remaining_seconds(text, game_clock)
        if remaining is None:
            return None
        return (float(_REGULATION_PERIODS + nth), -remaining)

    return None


def live_write_would_revert(
    stored_period: str | None,
    stored_clock: str | None,
    incoming_period: str | None,
    incoming_clock: str | None,
) -> bool:
    """Is this incoming live observation from EARLIER in the game than the row?

    ``True`` only when both sides are locatable AND the incoming one is strictly
    earlier — the one case where accepting the write is guaranteed to move the
    served state backwards in front of a reader. Every other case, including
    both unreadable and an exact tie, is ``False``: this function's job is to
    refuse proven reversions, not to gatekeep live updates.
    """
    incoming = live_progress_position(incoming_period, incoming_clock)
    if incoming is None:
        return False
    stored = live_progress_position(stored_period, stored_clock)
    if stored is None:
        return False
    return incoming < stored
