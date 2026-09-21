"""Shared staleness detection for category routes and the Discover feed.

Pure functions — no I/O, no DB. Determines whether a market's title implies
the real-world event has passed (e.g., "Eurovision" after May 31).
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any

_MONTH_NAME_TO_NUMBER = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_EXPLICIT_MONTH_DAY_RE = re.compile(
    r"\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?"
    r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(20\d{2}))?\b",
    re.IGNORECASE,
)

# Month + year with NO day ("Rain in LA in Jun 2026", "June 2026"). Kalshi's
# resolution_date for these is the settlement date ~2 weeks INTO the next month,
# so a `resolution_date > now` filter keeps featuring them after the event month
# has already ended. The real-world period ends at the last day of the named
# month. The explicit month+DAY regex above is checked first and returns, so this
# only fires for day-less month/year periods. #883 L2-56.
_MONTH_YEAR_RE = re.compile(
    r"\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?"
    r")\.?\s+(20\d{2})\b",
    re.IGNORECASE,
)

# 🔴 A DAY RANGE IS DATED BY ITS END, NOT ITS START (#7274 / #1567).
#
# `_EXPLICIT_MONTH_DAY_RE` needs a month name in front of every day it reads, so
# on a range rung ("September 15 - 30, 2026") the only thing it can match is the
# OPENING day — and "last match wins" then dates the rung 15 days before it can
# actually stop happening. Measured on production 2026-09-19, market 58776433
# (*When will the Danube River return to normal levels?*): that rung was read as
# expired on the 19th, INSIDE its own open window, and the Discover card dropped
# a live 14.5% option off the board. The same parse also loses the explicit year
# — " - 30, 2026" is outside the match — so the rung fell to the year-guessing
# path as well.
#
# The trailing day is matched WITHOUT a month name of its own, so a cross-month
# range ("Dec 28 - Jan 3, 2027") is deliberately NOT this pattern: the existing
# last-match-wins rule already reads its end correctly, and re-reading it here
# would be a second answer to a question already answered.
#
# Word separators require real whitespace ("1 to 31"), dashes do not ("1-31"),
# so a bare "1to31" cannot be read as a range.
_MONTH_DAY_RANGE_RE = re.compile(
    r"\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?"
    r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:\s*[-–—]\s*|\s+(?:to|through|thru|until)\s+)"
    r"(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(20\d{2}))?\b",
    re.IGNORECASE,
)

# A tournament whose QUALIFYING campaign runs on a different calendar than the
# tournament itself. World Cup qualifying runs into November, so the July
# final-date rule must not fire on a qualifier title. UX-P006 / #1567.
_QUALIFIER_RE = re.compile(r"\bqualif", re.IGNORECASE)

# (pattern, (end_month, end_day), grace_days, sport_guard, exclude_pattern).
# ``sport_guard`` of None means the rule applies to any category; otherwise the
# market's ``sport_category`` must be in the set. The guard replaces the old
# hardcoded "us open is tennis-only" special case, so the SAME title can carry a
# different calendar per sport — golf's US Open ends in June, tennis's in
# September. ``exclude_pattern`` of None means no exclusion; otherwise a title
# matching it is NOT governed by this rule's calendar — the generic mechanism
# that keeps "World Cup Qualifying" off the World Cup final's calendar without
# a special-cased branch in the loop.
_RECURRING_MARKET_EVENT_END_RULES: tuple[
    tuple[re.Pattern, tuple[int, int], int, frozenset[str] | None, re.Pattern | None],
    ...,
] = (
    (re.compile(r"\beurovision\b", re.IGNORECASE), (5, 31), 0, None, None),
    (re.compile(r"\b(australian open)\b", re.IGNORECASE), (2, 2), 2, None, None),
    (re.compile(r"\b(french open|roland garros)\b", re.IGNORECASE), (6, 8), 0, None, None),
    (re.compile(r"\bwimbledon\b", re.IGNORECASE), (7, 15), 2, None, None),
    (re.compile(r"\bus open\b", re.IGNORECASE), (9, 15), 2, frozenset({"tennis"}), None),
    # Golf majors (UX-P004 class a). A concluded major keeps a NULL
    # resolution_date and keeps being polled, so neither the date gate nor the
    # updated_at staleness gate ever fires — the field sits at live-looking
    # probabilities for months. End dates are the final round, generously
    # rounded late so a running major is never hidden.
    (re.compile(r"\bmasters\b", re.IGNORECASE), (4, 16), 2, frozenset({"golf"}), None),
    (re.compile(r"\bpga champ", re.IGNORECASE), (5, 23), 2, frozenset({"golf"}), None),
    (re.compile(r"\bus open\b", re.IGNORECASE), (6, 23), 2, frozenset({"golf"}), None),
    (
        re.compile(r"\b(the open championship|british open)\b", re.IGNORECASE),
        (7, 23),
        2,
        frozenset({"golf"}),
        None,
    ),
    # FIFA World Cup (UX-P004 class a). Soccer-guarded so cricket/rugby world
    # cups are untouched. Markets naming a FUTURE tournament ("2030 FIFA World
    # Cup Champion") are already protected upstream by the implied-year check,
    # which returns before these rules are consulted.
    #
    # UX-P006 / #1567: the rule is year-agnostic by design (it must also cover
    # the annual Club World Cup), so it fires in NON-tournament years too. That
    # is harmless for the tournament itself but wrong for QUALIFYING, which runs
    # into November — an undated "World Cup Qualifying" market would have been
    # suppressed from ~Aug 3 of a qualifying year (latent; bites 2027-2029 for
    # the 2030 cycle). Excluding qualifier titles is preferred over gating the
    # rule to World Cup years, which the Club World Cup would break anyway.
    (
        re.compile(r"\bworld cup\b", re.IGNORECASE),
        (7, 31),
        3,
        frozenset({"soccer"}),
        _QUALIFIER_RE,
    ),
)

PROBABILITY_EXTREME_LOW = 0.02
PROBABILITY_EXTREME_HIGH = 0.98


def _implied_year_from_market_name(market_name: str, now: datetime) -> int:
    years = [int(year) for year in re.findall(r"\b(20\d{2})\b", market_name)]
    return max(years) if years else now.year


def infer_market_real_world_end(
    market_name: str | None,
    sport_category: str | None,
    now: datetime,
) -> tuple[datetime, str, int] | None:
    """Infer when the real-world question stopped being current."""
    name = market_name or ""
    if not name:
        return None

    explicit_matches = list(_EXPLICIT_MONTH_DAY_RE.finditer(name))
    if explicit_matches:
        match = explicit_matches[-1]
        month = _MONTH_NAME_TO_NUMBER[match.group(1).lower().rstrip(".")]
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else now.year
        try:
            implied_end = datetime(year, month, day, 23, 59, 59, tzinfo=timezone.utc)
        except ValueError:
            return None
        grace_days = 7 if re.search(r"\bweek of\b", name, re.IGNORECASE) else 1
        return implied_end, "explicit_title_date", grace_days

    # Month + year with no day ("... in Jun 2026") — period ends the last day of
    # that month. #883 L2-56.
    month_year_matches = list(_MONTH_YEAR_RE.finditer(name))
    if month_year_matches:
        match = month_year_matches[-1]
        month = _MONTH_NAME_TO_NUMBER[match.group(1).lower().rstrip(".")]
        year = int(match.group(2))
        try:
            if month == 12:
                implied_end = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
            else:
                implied_end = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
        except ValueError:
            return None
        return implied_end, "explicit_title_month", 1

    event_year = _implied_year_from_market_name(name, now)
    if event_year > now.year:
        return None

    sport_lower = (sport_category or "").lower()
    for (
        pattern,
        (month, day),
        grace_days,
        sport_guard,
        exclude_pattern,
    ) in _RECURRING_MARKET_EVENT_END_RULES:
        if not pattern.search(name):
            continue
        if exclude_pattern is not None and exclude_pattern.search(name):
            continue
        if sport_guard is not None and sport_lower not in sport_guard:
            continue
        implied_end = datetime(event_year, month, day, 23, 59, 59, tzinfo=timezone.utc)
        return implied_end, "recurring_event_calendar", grace_days

    return None


def is_title_implied_stale(
    market_name: str | None,
    sport_category: str | None,
    now: datetime,
) -> str | None:
    """Return a stale reason string if the market's title implies it's over, else None."""
    inferred = infer_market_real_world_end(market_name, sport_category, now)
    if not inferred:
        return None
    implied_end, reason, grace_days = inferred
    if now > implied_end + timedelta(days=grace_days):
        return f"stale_{reason}"
    return None


# A bare "July 31" rung parsed in January would look ~7 months stale under a
# current-year assumption when it almost certainly means the COMING July. Only
# treat a year-less rung as expired if it landed within this look-back window.
_BARE_DATE_LOOKBACK_DAYS = 180

# ---------------------------------------------------------------------------
# Day-less rung deadlines ("Before July", "Before 2027"). UX-P006 / #1567.
#
# ``_EXPLICIT_MONTH_DAY_RE`` REQUIRES a day number, so a rung naming only a
# month or only a year was never inspected and survived forever. Live on
# production 2026-08-06, the aliens ladder carried "Before July" and "Before
# August" at 1% next to four correct future rungs.
#
# A day-less period needs a deadline CONTEXT before it can be read as a date:
# a bare month name is also an ordinary English word ("Trump may resign", "a
# 2024 champion"), and stripping a rung is the sharp edge here — a false
# positive deletes a live option from the card. So a day-less period counts
# only when a deadline preposition introduces it, or when it IS the whole
# outcome name.
# ---------------------------------------------------------------------------

_MONTH_ALTERNATION = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?"
)

# A month name NOT followed by a day or a year. The month+day and month+year
# branches are checked first and return, so the lookahead is belt-and-braces —
# it also stops "Before Jul 25" being re-read as a bare "Jul".
_BARE_MONTH_RE = re.compile(
    rf"\b({_MONTH_ALTERNATION})\b\.?(?!\s*,?\s*\d)", re.IGNORECASE
)

_BARE_YEAR_RE = re.compile(r"\b(20\d{2})\b")

# Prepositions that make the following period a DEADLINE. "after" is
# deliberately absent: "After July" does not expire when July ends.
_DEADLINE_PREFIX_RE = re.compile(
    r"(?:^|[\s(\[,–—-])"
    r"(before|by|prior\s+to|earlier\s+than|no\s+later\s+than|on\s+or\s+before|"
    r"through|thru|until|til|till|in|during|end\s+of|month\s+of|as\s+of)"
    r"\s+(?:the\s+)?$",
    re.IGNORECASE,
)

# "Before July" means before July BEGINS — its deadline is June 30, not July 31.
# The aliens ladder proves the reading: the same ladder carries "Before 2027"
# and "Before 2028", where the boundary is unambiguously the START of the named
# period. Every other preposition is ambiguous in English ("by July", "until
# July"), so those take the INCLUSIVE end — the conservative choice, because a
# later deadline suppresses less.
_EXCLUSIVE_DEADLINE_WORDS = frozenset({"before", "prior to", "earlier than"})


def _deadline_context(name: str, match: re.Match) -> bool | None:
    """Is this match a deadline, and is it exclusive?

    Returns True (exclusive, "before X"), False (inclusive, "in X" / bare), or
    None when the match carries no deadline context at all.
    """
    prefix = _DEADLINE_PREFIX_RE.search(name[: match.start()])
    if prefix is not None:
        word = re.sub(r"\s+", " ", prefix.group(1).strip().lower())
        return word in _EXCLUSIVE_DEADLINE_WORDS
    if match.group(0).strip().rstrip(".") == name.strip().rstrip("."):
        return False  # the outcome name IS the period, e.g. a rung named "July"
    return None


def _last_deadline_match(pattern: re.Pattern, name: str) -> tuple[re.Match, bool] | None:
    """Last match of ``pattern`` that sits in a deadline context, plus exclusivity."""
    chosen: tuple[re.Match, bool] | None = None
    for match in pattern.finditer(name):
        exclusive = _deadline_context(name, match)
        if exclusive is not None:
            chosen = (match, exclusive)
    return chosen


def _month_period_end(year: int, month: int, *, exclusive: bool) -> datetime | None:
    """Last instant of a named month, or of the instant before it starts."""
    try:
        if exclusive:
            return datetime(year, month, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
        if month == 12:
            return datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        return datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
    except ValueError:
        return None


def _day_less_deadline(name: str, now: datetime) -> tuple[datetime, bool] | None:
    """(deadline, had_explicit_year) for a day-less month/year rung, else None."""
    # Month + explicit year ("Before July 2026") — exact, no year guessing.
    month_year = _last_deadline_match(_MONTH_YEAR_RE, name)
    if month_year is not None:
        match, exclusive = month_year
        month = _MONTH_NAME_TO_NUMBER[match.group(1).lower().rstrip(".")]
        end = _month_period_end(int(match.group(2)), month, exclusive=exclusive)
        return (end, True) if end else None

    # Bare month ("Before July") — assume the current year, then let the
    # look-back guard below reject anything implausibly stale.
    bare_month = _last_deadline_match(_BARE_MONTH_RE, name)
    if bare_month is not None:
        match, exclusive = bare_month
        month = _MONTH_NAME_TO_NUMBER[match.group(1).lower().rstrip(".")]
        end = _month_period_end(now.year, month, exclusive=exclusive)
        return (end, False) if end else None

    # Bare year ("Before 2027") — also on the aliens ladder, also day-less.
    bare_year = _last_deadline_match(_BARE_YEAR_RE, name)
    if bare_year is not None:
        match, exclusive = bare_year
        year = int(match.group(1)) - 1 if exclusive else int(match.group(1))
        try:
            return datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc), True
        except ValueError:
            return None

    return None


def _named_deadline(
    outcome_name: str | None, now: datetime
) -> tuple[datetime, bool] | None:
    """``(deadline, had_explicit_year)`` named by the rung itself, else ``None``.

    The PARSING half of `outcome_deadline_expired`, lifted out unchanged so that
    two callers can share one reading of a rung's name. That function applies the
    grace period and the year-less look-back to this answer and is the only place
    those judgements live; #7784 needs the instant itself, to ask whether the
    price beside the name was observed before it or after it.

    `None` means "this name does not date itself" — which is every non-ladder
    outcome, and, deliberately, the two shapes the rules below refuse to date: a
    range that closes before it opens, and an impossible calendar day.
    """
    name = outcome_name or ""
    if not name:
        return None

    match = None
    for match in _EXPLICIT_MONTH_DAY_RE.finditer(name):
        pass  # last match wins, mirroring infer_market_real_world_end
    if match is not None:
        month = _MONTH_NAME_TO_NUMBER[match.group(1).lower().rstrip(".")]
        day = int(match.group(2))
        explicit_year = match.group(3)
        # #7274: if the day this matched is the OPENING day of a range, the rung
        # runs until the range's CLOSING day and cannot be expired before it. The
        # containment test is what keeps last-match-wins intact: a range followed
        # by a later date ("September 15 - 30, 2026, resolves October 5, 2026")
        # still expires on the later date, because that match sits outside the
        # range's span.
        day_range = None
        for candidate in _MONTH_DAY_RANGE_RE.finditer(name):
            if candidate.start() <= match.start() < candidate.end():
                day_range = candidate
        if day_range is not None:
            end_day = int(day_range.group(3))
            if end_day < day:
                # A range that closes before it opens is a month rollover we have
                # not been given ("September 30 - 2"), and guessing which month
                # the closing day belongs to would be inventing the deadline. We
                # cannot date the end, so we do not delete the rung.
                return None
            day = end_day
            explicit_year = day_range.group(4)
        year = int(explicit_year) if explicit_year else now.year
        try:
            deadline = datetime(year, month, day, 23, 59, 59, tzinfo=timezone.utc)
        except ValueError:
            return None
        had_explicit_year = explicit_year is not None
    else:
        day_less = _day_less_deadline(name, now)
        if day_less is None:
            return None
        deadline, had_explicit_year = day_less

    return deadline, had_explicit_year


def outcome_deadline_expired(
    outcome_name: str | None,
    now: datetime,
    *,
    grace_days: int = 1,
) -> bool:
    """True if a ladder rung's OWN name names a deadline that has already passed.

    Ladder markets ("When will X happen?") carry dated rungs — "Before Jul 25,
    2026", "July 31". Once a rung's date passes it can no longer happen, but the
    rung keeps its last traded price and renders as a live 1-3% option. Nothing
    else in the pipeline looks at outcome names: the market-level title check
    sees an undated question, and the market keeps being polled so it never goes
    stale. UX-P004 classes b + e.

    UX-P006 / #1567 widened this past month+DAY rungs to DAY-LESS ones ("Before
    July", "Before July 2026", "Before 2027"), which the day-requiring regex
    below skipped entirely.

    #7274 dates a RANGE rung ("September 15 - 30, 2026") by its closing day. It
    was read by its opening day, so a window still open expired mid-window.
    """
    named = _named_deadline(outcome_name, now)
    if named is None:
        return False
    deadline, had_explicit_year = named

    if now <= deadline + timedelta(days=grace_days):
        return False
    if not had_explicit_year and now - deadline > timedelta(days=_BARE_DATE_LOOKBACK_DAYS):
        # Year-less and far in the past — almost certainly next year's rung.
        return False
    return True


# A past-dated rung priced at or above this is NOT a ghost — it is the ladder's
# ANSWER. UX-P006 census, production 2026-08-07: widening the parser to day-less
# rungs put 176 rungs across 83 open markets in scope, and they split cleanly in
# two. Below ~8% sit the ghosts the census class describes ("past-dated options
# still showing 1-3%"). At 89-100% sit rungs that already resolved YES — the
# winner of "In which month will SpaceX IPO?" ("June", 99.95%) and the settled
# rungs of every cumulative "Before X" ladder whose event has happened. Removing
# those would hide the leader, which is the UX-P005 defect class, so a rung this
# confident is kept whatever its date says. 50% sits in the empty middle of that
# split.
EXPIRED_RUNG_MAX_PROBABILITY = 0.5


# ---------------------------------------------------------------------------
# The year a year-less rung is missing is often written on the rung NEXT TO IT.
# #7383.
#
# `outcome_deadline_expired` reads a year-less "December 31" as THIS year, so on
# 2026-09-19 it dates to 2026-12-31, reads as future, and is never expired — the
# `_BARE_DATE_LOOKBACK_DAYS` rescue below it is not even reached. Nothing in the
# pipeline compares a rung against the OTHER RUNGS OF ITS OWN BOARD, which is
# where the year actually is. Live on production that morning, `/futures/112936`
# ("Will Hamas agree to disarm?") was three rows and two of them were the same
# date:
#
#     December 31, 2026   OPEN  31%   LATEST  18%
#     December 31         OPEN 100%   LATEST   0%
#     November 30         OPEN 100%   LATEST   0%
#
# — the bare pair being the 2025 rungs of a rolling ladder, reading to a reader
# as certainties that collapsed to nothing.
#
# 🔴 THE INFERENCE IS "EARLIER", AND EARLIER IS NOT "PAST". Two rungs of one
# ladder cannot name one deadline, so a bare rung sharing a month and day with a
# dated one is a DIFFERENT, EARLIER occurrence. That alone does not make it
# dead: board 20569379 ("Russia x Ukraine ceasefire agreement?") carries a bare
# `December 31` at 21.5% beside `December 31, 2027` at 70.5%, and the bare one is
# 2026 — earlier than its twin and still months away. Stripping it would delete a
# live option, which is the sharp edge this whole module is careful about.
#
# So the test is on the occurrence STRICTLY BEFORE THE TWIN. If that date has
# passed, every occurrence before the twin has passed, and the rung is dead
# whichever one it is — so the rule never has to guess the year, which is the
# only reason it is safe. If it has not passed, we cannot tell 2026 from 2025 and
# we keep the rung.
#
# ⚠️ A GRADE IS NOT THE EVIDENCE HERE, MEASURED BEFORE BUILDING. Every rung in
# this population also carries `is_winner IS FALSE` + `resolution_source =
# 'api_settlement'`, and keying on that pair is the obvious fix. It is wrong:
# that pair is set on 189 rungs whose own label names a FUTURE year on open
# markets (`Before Jan 1, 2030` at 29%, `Before 2030` at 51.5%, `Before Apr 1,
# 2027` at 88%). It does not mean "the venue graded this NO".
#
# Only a WHOLE-NAME date counts, on both sides. A prose rung that merely contains
# a month ("Before Jul 25, 2026") is already read correctly by the rule above,
# and re-reading it here would be a second answer to a settled question.
_WHOLE_NAME_DATE_RE = re.compile(
    r"^\s*("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?"
    r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(20\d{2}))?\s*$",
    re.IGNORECASE,
)


def _whole_name_date(name: str) -> tuple[int, int, int | None] | None:
    """``(month, day, year_or_None)`` when the rung's whole name IS a date."""
    match = _WHOLE_NAME_DATE_RE.match(name)
    if match is None:
        return None
    month = _MONTH_NAME_TO_NUMBER[match.group(1).lower().rstrip(".")]
    day = int(match.group(2))
    year = int(match.group(3)) if match.group(3) else None
    try:
        datetime(year or 2000, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None  # February 30 is not a date, it is a label we cannot read
    return month, day, year


def _live_dated_twins(
    names: list[str], now: datetime, *, grace_days: int
) -> dict[tuple[int, int], int]:
    """``(month, day) -> year`` for each dated rung that has NOT expired.

    A month/day carrying MORE THAN ONE dated rung is left out entirely. With two
    live twins a bare rung is earlier than both, and picking which one to measure
    against is a guess — the whole point of the rule is that it never makes one.
    """
    twins: dict[tuple[int, int], int] = {}
    ambiguous: set[tuple[int, int]] = set()
    for name in names:
        parsed = _whole_name_date(name)
        if parsed is None:
            continue
        month, day, year = parsed
        if year is None:
            continue
        key = (month, day)
        if key in twins:
            ambiguous.add(key)
            continue
        deadline = datetime(year, month, day, 23, 59, 59, tzinfo=timezone.utc)
        if now > deadline + timedelta(days=grace_days):
            # The twin itself has passed, so the bare rung is the LATER one and
            # may well be the live rung of the pair. Board 113013 is this shape:
            # `December 31, 2025` at 0% beside a bare `December 31` at 29.5%.
            continue
        twins[key] = year
    for key in ambiguous:
        twins.pop(key, None)
    return twins


def _twin_deadline(
    name: str, twins: dict[tuple[int, int], int]
) -> datetime | None:
    """The LATEST instant a year-less rung could name, read off its dated twin.

    The parsing half of `_twin_proves_expired`, split out for the same reason
    `_named_deadline` was (#7784): the instant, not the verdict. Two rungs of one
    ladder cannot name one deadline, so this rung is a strictly EARLIER
    occurrence than its twin — the year before it, at the latest.
    """
    parsed = _whole_name_date(name)
    if parsed is None:
        return None
    month, day, year = parsed
    if year is not None:
        return None  # it says its own year; the rule above already read it
    twin_year = twins.get((month, day))
    if twin_year is None:
        return None
    try:
        return datetime(twin_year - 1, month, day, 23, 59, 59, tzinfo=timezone.utc)
    except ValueError:
        # Feb 29 the year before a leap year. The rung is real, our arithmetic
        # is not, and inventing a neighbouring day to strip a live option is
        # exactly the trade this module refuses.
        return None


def _twin_proves_expired(
    name: str,
    twins: dict[tuple[int, int], int],
    now: datetime,
    *,
    grace_days: int,
) -> bool:
    """Does a live dated twin on this board prove a year-less rung is past?"""
    latest_possible = _twin_deadline(name, twins)
    if latest_possible is None:
        return False
    return now > latest_possible + timedelta(days=grace_days)


def _observed_at(value) -> datetime | None:
    """A rung's observation stamp, normalised — or ``None`` for "we cannot tell".

    Takes a datetime off an ORM row or the ISO string a serialised payload
    carries, because the three call sites hold one or the other and neither
    should have to convert. Anything else, and any string that is not a stamp,
    is ``None``: an unreadable stamp is NO EVIDENCE, and the rule below is
    written so that no evidence changes nothing.
    """
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    return _as_utc(value)


def _price_is_the_ladders_answer(
    observed_at: datetime | None, deadline: datetime | None
) -> bool:
    """Is a confident price on a past-dated rung a VERDICT, or a forecast? (#7784)

    ═══ 🔴 THE EXEMPTION NEEDS EVIDENCE, AND THE STAMP IS THE EVIDENCE ═══

    `EXPIRED_RUNG_MAX_PROBABILITY` spares a past-dated rung priced at or above
    it because such a rung "already resolved YES and is the ladder's answer". The
    census that set the constant is quoted above and is sound — but it was taken
    on rungs the venue was still repricing, and the reasoning silently assumes
    the price was seen AFTER the deadline. On a board whose pricing has stopped
    that assumption inverts, and the exemption reads the market's last FORECAST
    as its VERDICT.

    WHAT A READER SAW (#7784, production 2026-09-21). `/futures/109403` — *When
    will DHS be funded again?*, an OPEN board — drew four rungs whose dates were
    15 to 129 days gone, each as a live green bar:

        Before May 15, 2026   66%      last_updated 2026-04-30
        Before May 22, 2026   78%      last_updated 2026-04-30
        Before Jun 1, 2026    86%      last_updated 2026-04-30
        Before Jul 1, 2026    96%      last_updated 2026-04-30

    Every rung on that board carries the identical stamp `2026-04-30T04:46:55`:
    the board stopped being repriced 144 days ago, and every one of those prices
    was taken 15 to 62 days BEFORE its own deadline. `0.66` is not the market
    saying "this happened"; it is the last thing the market said while the
    deadline was still in the future. The chart one inch above the table already
    knew — *"No prices in the last 7 days"*.

    So the test is the one the exemption's own reasoning implies: the price is a
    verdict only if it was observed once the rung's own deadline had arrived.

    ═══ MEASURED TO THE DAY, NOT TO THE SECOND, AND THAT IS THE WHOLE EDGE ═══

    `_named_deadline` dates every rung to **23:59:59 of its named day**, so a
    stamp taken at noon on that day is "before the deadline" by the arithmetic
    while being, to a reader, the day the thing resolved. Measured old-vs-new
    over the 10,133 rungs of the 816 open boards that could possibly move (see
    the ship's artifact): the rule catches **68 rungs on 24 boards**, and only
    **5** of them turn on this hour-vs-day choice:

        September 10          1.00   stamped 2026-09-10 15:08   <- it happened
        September 10          1.00   stamped 2026-09-10 16:08   <- it happened
        Before Apr 15, 2026   0.99   stamped 2026-04-15 08:45   <- it happened
        Before Aug 1, 2026    0.99   stamped 2026-08-01 04:51   <- it happened
        September 18          0.63   stamped 2026-09-18 03:50   <- a forecast

    To the second, all five are deleted and four of them are real verdicts. To
    the DAY, four are kept and one forecast survives. The harmful direction here
    is deleting an answer a reader is entitled to, so the comparison is against
    the START of the deadline's day: a stamp landing on that day or later is
    evidence. ux's own filing reads the second specimen the same way — of its
    three past-dated rungs it calls only "two of them priced before their own
    deadline", the third being stamped on its deadline's date.

    ⚠️ NO STAMP ⇒ THE EXEMPTION STANDS, and that direction is deliberate. This
    gate ends in a row being REMOVED from a reader's screen, and the innocent
    case — a leader we cannot date — leaves no trace on the page it was deleted
    from. A rung nobody stamped is not evidence of a forecast; it is the absence
    of evidence, and it keeps the behaviour it has today. Same for a rung whose
    name we could not date at all, which cannot reach here in the first place.
    """
    if observed_at is None or deadline is None:
        return True
    return observed_at >= deadline.replace(hour=0, minute=0, second=0, microsecond=0)


def _rung_is_a_graded_winner(is_winner: Any) -> bool:
    """Has the venue already declared this rung the answer? (CERT-3236 repair)

    ═══ 🔴 A "BEFORE …" CONTRACT MAY SETTLE YES BEFORE ITS OWN DEADLINE ═══

    :func:`_price_is_the_ladders_answer` asks whether a confident price is a
    verdict or a forecast, and dates the evidence by the stamp. On a CUMULATIVE
    ladder that test has a blind spot the DHS specimen could not show: *Before
    Sep 1, 2026* resolves YES the moment the thing happens, which may be weeks
    EARLY, and the settlement write is the last time the leg is ever touched. Its
    stamp is therefore permanently before its own deadline, and the observation
    test reads the venue's own verdict as a stale forecast.

    MEASURED (CERT-3236's finding, reproduced independently at
    `artifacts/d383-7784r/replay_winners.py` against production 2026-09-21): over
    the 63 open boards carrying a dated graded leg, the observation rule alone
    newly hides **27 rungs, and 25 of them are `is_winner = true` with
    `resolution_source = 'api_settlement'`** — the Claude 5, Makary, baxdrostat
    and DNC-autopsy boards, and every day of the two "Will Russia target Kyiv
    on…?" / "Will Trump publicly insult someone on…?" ladders. Hiding those is a
    strictly worse truth defect than the one this ship set out to fix.

    ``is_winner IS TRUE`` IS THE WHOLE TEST, and the two obvious alternatives are
    both wrong here:

    * ``is_winner`` alone in the FALSE direction would be a disaster — the column
      is ``default=False`` so ``False`` is what a row is BORN with
      (`futures_liveness.leg_is_graded` documents the measurement) — but TRUE is
      never written by accident, which is the only direction this function reads.
    * REQUIRING ``resolution_source = 'api_settlement'`` as well would be tidier
      and buys nothing: all 25 carry it, and a winner graded by any other rail is
      still a winner a reader must not lose. The asymmetry decides it — hiding a
      declared winner deletes an answer from the page, while sparing one leaves a
      row the price exemption kept anyway.

    THIS CLAUSE TAKES NOTHING AWAY FROM MASTER: measured on the same population,
    **0** graded winners are expired by the pre-#7784 rule today, so no rung that
    master hides stops being hidden. The 63 DHS-class stale forecasts the ship
    removes are unaffected — not one of them is graded.
    """
    return is_winner is True


def expired_ladder_rungs(
    outcomes: (
        list[str | None]
        | list[tuple[str | None, float | None]]
        | list[tuple[str | None, float | None, datetime | str | None]]
        | list[tuple[str | None, float | None, datetime | str | None, Any]]
    ),
    now: datetime,
    *,
    grace_days: int = 1,
) -> set[str]:
    """Names of rungs whose own deadline has passed. Empty set for undated ladders.

    Accepts bare names, ``(name, probability)`` pairs, or
    ``(name, probability, observed_at)`` triples. Pass the pairs where
    probabilities are available: a past-dated rung priced at or above
    ``EXPIRED_RUNG_MAX_PROBABILITY`` is the ladder's answer, not a dead option,
    and is never stripped.

    #7784: pass the TRIPLE where the rung's observation stamp is available too.
    That exemption holds only for a price observed at or after the rung's own
    deadline — see `_price_is_the_ladders_answer` for the four-rung board that
    priced four past dates because it does not reprice any more. A pair, or a
    triple with no stamp, behaves exactly as it did before.

    CERT-3236: pass the FOUR-TUPLE where the leg's ``is_winner`` grade is
    available. A rung the venue has already declared the winner is never hidden,
    whenever it was last priced — a cumulative "Before …" contract settles YES on
    the day the thing happens, which may be weeks before its own deadline, so the
    stamp test alone deletes 25 authoritative winners (see
    :func:`_rung_is_a_graded_winner`). An absent grade changes nothing.

    #7383: a rung is ALSO expired when a dated twin on the SAME BOARD proves it
    — see `_live_dated_twins`. That arm reads the whole list, which is why it
    lives here and not in `outcome_deadline_expired`, and it is why the three
    call sites needed no change to inherit it.
    """
    names = [
        (outcome[0] if isinstance(outcome, tuple) else outcome) or ""
        for outcome in outcomes
    ]
    twins = _live_dated_twins(names, now, grace_days=grace_days)

    expired: set[str] = set()
    for outcome in outcomes:
        if isinstance(outcome, tuple):
            name, probability = outcome[0], outcome[1]
            observed_at = _observed_at(outcome[2]) if len(outcome) > 2 else None
            is_winner = outcome[3] if len(outcome) > 3 else None
        else:
            name, probability, observed_at, is_winner = outcome, None, None, None
        if not name:
            continue
        # CERT-3236 — BEFORE EITHER ARM, because a declared winner is not a dead
        # option under any rule that could name it: neither its own passed date
        # nor a live dated twin makes the venue's verdict untrue.
        if _rung_is_a_graded_winner(is_winner):
            continue
        # WHICH ARM CALLED IT DEAD DECIDES WHICH DEADLINE THE STAMP IS MEASURED
        # AGAINST — the rung's own date, or the one its dated twin implies. The
        # order is the order the two rules were written in and is unchanged.
        if outcome_deadline_expired(name, now, grace_days=grace_days):
            named = _named_deadline(name, now)
            deadline = named[0] if named is not None else None
        elif _twin_proves_expired(name, twins, now, grace_days=grace_days):
            deadline = _twin_deadline(name, twins)
        else:
            continue
        if probability is not None and probability >= EXPIRED_RUNG_MAX_PROBABILITY:
            if _price_is_the_ladders_answer(observed_at, deadline):
                continue
        expired.add(name)
    return expired


def _as_utc(value) -> datetime | None:
    """A stamp, normalised to UTC — or ``None`` for anything that is not one.

    Naive stamps are read as UTC: comparing a naive and an aware datetime raises
    ``TypeError``, and it would raise at request time rather than in any test.

    The ``isinstance`` is not defensive noise. This reads a column straight off
    whatever object the caller has, and the one caller sits inside
    ``_score_futures``'s per-market ``try/except`` — so a non-datetime here does
    not surface as an error, it surfaces as a card that silently vanished. The
    DB column is ``DateTime(timezone=True)``, so a non-datetime is never a
    legitimate stamp and reading it as "no evidence" is the right answer.
    """
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


#: How long a market's prices may stand still before the market is treated as
#: over. **This is NOT the parent row's threshold and must never be folded into
#: it** — see `prices_have_stopped` for the measurement that separates them.
PRICES_STOPPED_DAYS = 14


def prices_have_stopped(
    newest_outcome_at: datetime | None,
    now: datetime,
    *,
    max_days: float = PRICES_STOPPED_DAYS,
) -> bool:
    """Has this market's pricing stopped altogether? (UX-P251)

    ``None`` — no outcome carries a stamp — is **False**. That is "no evidence",
    not evidence of death; a writer that never sets the column must not take its
    whole source dark.

    ═══ 🔴 WHY THIS IS A SEPARATE BLOCKER WITH A SEPARATE NUMBER ═══

    The first version of this ship folded the prices' clock into
    ``market.updated_at`` — took the older of the two stamps and let the four
    existing staleness blockers run on the result at their own ``2`` days. It
    was green, its guard was green, and its battery killed 10 of 11 mutants.
    **A census by market tier is what caught it**, before merge and by one query:

        tier 3: 17 of 17 admitted markets blocked — 100%
        tier 4:  6 of 7                          —  86%

    Those are not dead markets. They are ``NFC East Division Winner``,
    ``College Football Heisman Trophy Winner``, ``NHL Pacific Division Winner``,
    ``Top Fantasy Rookie QB/RB/TE/WR``, the Biletnikoff and Doak Walker awards —
    **season futures, priced four days ago, on the eve of the NFL season.** A
    low-liquidity season future legitimately does not reprice daily, and the
    parent-row clock had been accidentally protecting every one of them.

    Two clocks measuring different things must not share a constant. The parent
    stamp answers "is the poller still visiting this row" and 2 days is right
    for it. This one answers "has anybody moved a price" and needs a threshold
    from the price distribution, which is strongly bimodal — measured on
    production 2026-09-01, over the 3,409 candidate markets the parent clock
    admits:

        > 2d   601 blocked      <- kills the whole season-futures shelf
        > 7d   137
        > 14d  107   <-- chosen
        > 21d  107
        > 30d  103
        > 45d   67

    Flat from 14 to 30: **almost nothing is frozen between two weeks and a
    month**, so 14 sits at the start of the plateau with a fortnight of margin
    below it. It catches the bridesmaids card (59 days) and everything above it,
    and spares all 464 markets that merely price weekly.

    Being a separate blocker also means the ``#1090`` broaden pass cannot relax
    it: the two ``*_days`` knobs that pass varies reach the four parent-clock
    blockers only. A market whose prices stopped a fortnight ago should not come
    back merely because the pool is thin, and now it cannot.
    """
    stamp = _as_utc(newest_outcome_at)
    if stamp is None:
        return False
    return (now - stamp).total_seconds() / 86400 > max_days


#: How far behind its OWN board's newest observation a leg may sit and still be
#: read as part of the same column (#7537).
#:
#: 🔴 A THIRD CLOCK, AND IT MUST NOT BE FOLDED INTO EITHER OF THE OTHER TWO —
#: the warning above ``PRICES_STOPPED_DAYS`` applied once more, for the same
#: reason and with its own measurement. The parent stamp asks "is the poller
#: still visiting this row" (2 days). ``PRICES_STOPPED_DAYS`` asks "has anybody
#: moved a price on this market" (14 days). This asks a question neither of them
#: can: **were these legs observed at the same time as each other**. It is a
#: comparison WITHIN a board, not a measurement against ``now``, and that is the
#: whole of its meaning.
#:
#: DERIVED FROM THE SPREAD DISTRIBUTION, in ``prices_have_stopped``'s own style.
#: Measured on production 2026-09-20 over the 8,476 open tier-1/2 boards
#: carrying three or more legs — boards having at least one leg more than X
#: behind their own newest stamp:
#:
#:     > 12h  1825
#:     >  1d  1735
#:     >  2d  1447
#:     >  3d  1395   <- plateau starts
#:     >  5d  1385
#:     >  7d  1360   <- chosen, plateau ends
#:     > 10d  1188
#:     > 14d  1115
#:
#: Flat from 3 to 7 days: **35 boards, 2.5%, across four days**, against 340 in
#: the two days below it. The population is strongly bimodal — 6,452 of the
#: 8,476 spread under one hour (a single clean pass), and the tail sits in
#: weeks — so the constant is not delicately placed between two crowded bands.
#:
#: CHOSEN AT THE FAR END OF THE PLATEAU RATHER THAN THE NEAR ONE, which is the
#: opposite of ``PRICES_STOPPED_DAYS``' choice and is a deliberate difference.
#: That constant wanted the earliest safe catch. This one governs a WITHHOLD:
#: the harmful direction is taking a number off a leg somebody is really
#: quoting, so it buys 2.3x the margin for the 2.5% of catch it gives up. A
#: board polled daily, or one whose pass straddles several hours (the 6-12h
#: bucket holds 154 boards; one measured specimen spreads 7.34h), is nowhere
#: near it.
#:
#: NOT THE RETENTION CUTOFF, and deliberately not derived from one. Codex ruled
#: on 2026-09-20 that "retention is storage policy, not freshness evidence" and
#: that an exclusion age may not be picked from the 48h collapse bound. This
#: number comes from the observed spread of live boards and from nothing else.
OBSERVATION_LAG_DAYS = 7


def stale_observation_keys(
    observations,
    *,
    max_lag_days: float = OBSERVATION_LAG_DAYS,
) -> set:
    """Keys whose stamp sits too far behind the newest stamp in the same group (#7537).

    ``observations`` is ``(key, stamp)`` per leg, in any order. Returns the keys
    that were NOT observed alongside the rest of their own board.

    ═══ WHAT A READER SAW ═══

    ``/futures/3971707`` (*Super League Rugby Championship*) printed **Leeds
    Rhinos 30%** in its hero and its table while the chart above them drew that
    same outcome at **39.5%**, both carrying the stamp ``14:53:14``. Fourteen
    legs summing to **1.7200** went into the table's divisor; exactly **three**
    of them had been observed that day. The other eleven were last written on
    ``2026-09-06 05:46:08`` — all eleven at that identical microsecond, because
    a poll pass stamps every row it touches with one ``now``, which is what
    makes the column readable as a pass at all.

    So the page squeezed three genuinely-quoted prices by the 41% of probability
    mass held by eleven rows nobody had repriced in a fortnight. ``futures.py``
    already names this fiction in its own words, one rule over: *"arithmetic
    over a set that never existed at one instant. That is a second fiction to
    cover the first."*

    ═══ 🔴 WHY EVERY EVIDENCE-BASED RULE ALREADY SHIPPED MISSES IT ═══

    This codebase screens unsupported prices properly and none of those screens
    can see this. ``price_is_unsupported`` reads the leg's ``yes_bid`` /
    ``yes_ask`` / ``last_price``; Hull Kingston Rovers presents
    ``0.1900 / 0.4700``, a healthy two-sided book, and is spared. **That book is
    a fossil too.** Kalshi's own API for ``KXSLRCHAMP-26-HKR``, read 2026-09-20,
    answers ``yes_bid 0.0000 / yes_ask 0.9600 / last_price 0.0000 /
    volume_24h 0`` — an empty book. Every column an evidence rule consults is
    frozen at the same stale instant, so each fossil presents as healthy and the
    rules acquit it on its own stale evidence. Nothing already shipped asks
    whether the evidence is CURRENT, and that is the gap this fills.

    ═══ IT DOES NOT CLAIM THE LEG IS DELISTED, AND THAT IS THE POINT ═══

    All fourteen tickers read ``status = active`` at the venue. The claim here is
    strictly the one the stamps support: *this row was not observed when the
    others were*, so putting it in one divisor with them is arithmetic across
    two instants. Codex ruled on 2026-09-20 that an old snapshot is not by itself
    proof a venue stopped quoting, and required that freshness be treated as "a
    display policy with UNKNOWN/failure behavior rather than proof of delisting".
    This returns the UNKNOWN set; the caller withholds a number it cannot
    source, which is the same answer the page already gives an unsupported price.

    ═══ RELATIVE TO THE BOARD, NEVER TO ``now`` — THE COUNTEREXAMPLE IT ANSWERS ═══

    Codex's objection to an absolute age was exact: a leg last written four days
    ago "is equally compatible with a still-quoted leg whose ingestion has
    failed for four days". A wall-clock rule cannot tell those apart. This one
    never asks the wall clock. If ingestion stalls for the whole market every
    leg ages together, the spread stays at zero, **nothing is stale and nothing
    is withheld** — our own outage can never blank a board. Only a board the
    poller demonstrably DID visit, writing some rows and not others, can produce
    a stale key, and there the split is evidence about the rows rather than
    about us.

    ═══ THE EMPTY SET IS STRUCTURALLY IMPOSSIBLE, NOT MERELY GUARDED ═══

    The reference is the maximum of the stamps, so the leg holding it is always
    within zero of it and can never be stale. A caller therefore cannot be left
    dividing by nothing — the hazard discover/331 measured on 44.8% of the
    oldest 500 open markets under an absolute-age rule simply has no instance
    here. Confirmed rather than assumed: over the 7,933 open tier-1/2
    mutually-exclusive boards, the count of boards with every leg stale is
    **0**.

    ``None``, or anything that is not a datetime, is NOT stale — ``_as_utc``'s
    reading and ``prices_have_stopped``' rule: no evidence is not evidence of
    death, and a writer that never sets the column must not blank its board.
    A group whose stamps are all unreadable yields the empty set.
    """
    stamps: dict = {}
    for key, value in observations:
        stamps[key] = _as_utc(value)

    readable = [stamp for stamp in stamps.values() if stamp is not None]
    if not readable:
        return set()
    newest = max(readable)

    cutoff_seconds = max_lag_days * 86400
    return {
        key
        for key, stamp in stamps.items()
        if stamp is not None and (newest - stamp).total_seconds() > cutoff_seconds
    }


def is_probability_extreme(probability: float | None) -> bool:
    """True if the leader probability is at a dead extreme (<2% or >98%)."""
    if probability is None:
        return False
    return probability < PROBABILITY_EXTREME_LOW or probability > PROBABILITY_EXTREME_HIGH


# Outcome-name prefixes that mark a CUMULATIVE threshold ladder rather than a
# partition into mutually exclusive brackets. Each row of such a ladder is an
# independent "at or above X" probability (gotcha #17), so the rows are NOT a
# distribution: they legitimately sum well over 100% and must never be
# normalized or rescaled against each other.
#
# The temporal forms belong here for the same reason: "Before Jan 1, 2028" is
# a deadline the market either clears or doesn't, and the rungs nest. Every
# prefix below is attested in the open economics pool — a first-word census on
# 2026-08-29 counted 798 markets on "above", 44 on "before" and 16 on "below".
#
# Carried by `routes/economics.py` since #2563; moved here for #6704, when the
# featured gate below had to ask the same question. One copy, because a second
# transcription of the vocabulary is a second thing to forget to update.
CUMULATIVE_THRESHOLD_PREFIXES = (
    "above ",
    "at least ",
    "more than ",
    "over ",
    "greater than ",
    "below ",
    "before ",
)


def outcome_names_are_cumulative_ladder(names) -> bool:
    """True when every one of ≥2 outcome names is a cumulative threshold."""
    marked = 0
    total = 0
    for name in names:
        total += 1
        if (name or "").strip().lower().startswith(CUMULATIVE_THRESHOLD_PREFIXES):
            marked += 1
    return total >= 2 and marked == total


def featured_leader_probability(outcomes) -> float | None:
    """The probability the featured gate should judge as "is this decided?".

    ``outcomes`` is any iterable of ``(name, probability)`` pairs.

    ═══ A LADDER'S MAXIMUM IS ITS LOOSEST RUNG, NOT ITS VERDICT (#6704) ═══

    Three category routes and `/weather` computed this as ``max(probability)``
    and handed it to ``should_exclude_from_featured``, whose
    ``probability_extreme`` arm then deleted anything over
    ``PROBABILITY_EXTREME_HIGH``. That arm was written for a BINARY sitting at
    99% — a question genuinely over. For a **cumulative** ladder the maximum is
    the probability of the loosest bound, which is a near-certainty *by
    construction* for any ladder whose floor is set low enough to be worth
    listing: "gold above $3,000" on a day gold trades near $4,545 is 0.995 and
    tells a reader nothing. So the gate was reading "the market is decided" off
    a number that measures how far the ladder's floor sits below spot.

    Measured on production 2026-09-21 over every open market with ≥2 cumulative
    rungs and a maximum over 0.98 — 323 markets deleted from featured surfaces,
    of which **256 (79%) carried at least one rung between 2% and 98%**. The
    inversion is the tell: the WIDER and better-built the ladder, the further
    its floor reaches below spot, the more certain its exclusion. On the metals
    section of `/economics` the 50-rung copper ladder was excluded and the
    13-rung gold one survived; five of the ten open metals markets never
    reached the page.

    So for a ladder the question becomes **does any rung sit in the live band**,
    and the value returned is the rung nearest even money — extreme exactly when
    no rung is in the band, which is the case a ladder really is over (every
    rung at 99%, or every rung at 0%).

    ⚠️ THE BINARY PATH IS BYTE-IDENTICAL, INCLUDING ITS QUIRK. For anything that
    is not a ladder this returns the maximum, and a falsy maximum (no outcomes,
    a null price, or an honest 0.0) still returns ``None`` — which
    ``is_probability_extreme`` answers False for. That quirk predates this
    helper and is deliberately preserved rather than repaired here: flipping it
    would REMOVE markets from featured surfaces, which is a different change
    with a different population, and folding it into a fix that ADDS them would
    make the before/after unreadable.
    """
    pairs = [(name, prob) for name, prob in outcomes]
    if not pairs:
        return None

    values = [float(prob) for _, prob in pairs if prob is not None]
    if not values:
        return None

    if outcome_names_are_cumulative_ladder(name for name, _ in pairs):
        chosen = min(values, key=lambda p: abs(p - 0.5))
    else:
        chosen = max(values)

    return float(chosen) if chosen else None


def should_exclude_from_featured(
    market_name: str | None,
    sport_category: str | None,
    status: str | None,
    leader_probability: float | None,
    now: datetime,
) -> str | None:
    """Return a reason to exclude from featured sections, or None if OK.

    Checks: resolved status, probability extremes, title-implied staleness.

    ═══ WHAT "FEATURED" COVERS (UX-P194-1) ═══

    Every surface a category page puts a market ON is a featured section, and
    that includes the cross-source spotlight — not only the theme lists. The
    three category routes each ran this predicate over their themed markets and
    then handed `find_cross_source_markets` the RAW query result, so a market
    this predicate had just rejected could still headline the page as its
    source disagreement.

    Measured on production 2026-08-31, across 19 live spotlight cards on
    `/economics`, `/politics` and `/entertainment`: one card survived that had
    no business doing so. `/politics` featured "Will the Supreme Court rule in
    favor of Trump's tariffs" as Kalshi 25.5% vs Polymarket 0.1%, a 25-point
    "disagreement" whose Polymarket side was a dead market with a leader
    probability of 0.0005 — `probability_extreme`, well under
    ``PROBABILITY_EXTREME_LOW``. The page's own theme sections had already
    dropped it. The spotlight had not been told.

    ⚠️ Note which arm caught it. ``find_cross_source_markets`` already skips
    ``is_resolved`` markets on its own, so the `"resolved"` arm was mostly
    covered; the arms that were NOT are `probability_extreme` and the
    `stale_*` title reasons. A guard for this class has to plant one of those.

    ⚠️ And note which SIDE it was on. A cross-source card is a PAIR, and the
    live specimen was unfit on its Polymarket half while its Kalshi half was
    perfectly healthy at 0.255. A guard that only ever makes the Kalshi member
    ineligible would pass while the real production defect walked through.
    Exclude either member and the card must go.
    """
    if status and status != "open":
        return "resolved"
    if is_probability_extreme(leader_probability):
        return "probability_extreme"
    return is_title_implied_stale(market_name, sport_category, now)
