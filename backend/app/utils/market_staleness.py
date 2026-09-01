"""Shared staleness detection for category routes and the Discover feed.

Pure functions — no I/O, no DB. Determines whether a market's title implies
the real-world event has passed (e.g., "Eurovision" after May 31).
"""

import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

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
    """
    name = outcome_name or ""
    if not name:
        return False

    match = None
    for match in _EXPLICIT_MONTH_DAY_RE.finditer(name):
        pass  # last match wins, mirroring infer_market_real_world_end
    if match is not None:
        month = _MONTH_NAME_TO_NUMBER[match.group(1).lower().rstrip(".")]
        day = int(match.group(2))
        explicit_year = match.group(3)
        year = int(explicit_year) if explicit_year else now.year
        try:
            deadline = datetime(year, month, day, 23, 59, 59, tzinfo=timezone.utc)
        except ValueError:
            return False
        had_explicit_year = explicit_year is not None
    else:
        day_less = _day_less_deadline(name, now)
        if day_less is None:
            return False
        deadline, had_explicit_year = day_less

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


def expired_ladder_rungs(
    outcomes: list[str | None] | list[tuple[str | None, float | None]],
    now: datetime,
    *,
    grace_days: int = 1,
) -> set[str]:
    """Names of rungs whose own deadline has passed. Empty set for undated ladders.

    Accepts bare names, or ``(name, probability)`` pairs. Pass the pairs where
    probabilities are available: a past-dated rung priced at or above
    ``EXPIRED_RUNG_MAX_PROBABILITY`` is the ladder's answer, not a dead option,
    and is never stripped.
    """
    expired: set[str] = set()
    for outcome in outcomes:
        if isinstance(outcome, tuple):
            name, probability = outcome
        else:
            name, probability = outcome, None
        if not name:
            continue
        if not outcome_deadline_expired(name, now, grace_days=grace_days):
            continue
        if probability is not None and probability >= EXPIRED_RUNG_MAX_PROBABILITY:
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


#: The two columns this reads, newest-evidence first. Order is the whole
#: semantic: ``price_changed_at`` answers the question being asked and
#: ``last_updated`` is only ever a bound on it. See `newest_outcome_stamp`.
_MOVEMENT_STAMP_COLUMNS = ("price_changed_at", "last_updated")


def _outcome_movement_stamp(outcome) -> datetime | None:
    """When THIS outcome's price last moved — or the tightest bound available.

    ``price_changed_at`` when the row carries one; otherwise ``last_updated``.
    Both shapes the feed carries are read (ORM row and the scoring loop's plain
    dict), and an unreadable value on either column is skipped rather than
    raised on — see `newest_outcome_stamp` for why a raise here is invisible.
    """
    is_mapping = isinstance(outcome, Mapping)
    for column in _MOVEMENT_STAMP_COLUMNS:
        raw = outcome.get(column) if is_mapping else getattr(outcome, column, None)
        stamp = _as_utc(raw)
        if stamp is not None:
            return stamp
    return None


def newest_outcome_stamp(outcomes) -> datetime | None:
    """When any of this market's prices last MOVED, or ``None`` if unknowable.

    ═══ 🔴 WHY THIS IS NOT ``last_updated`` ALONE (CERT-688) ═══

    Version two of this ship read ``FuturesOutcome.last_updated`` and nothing
    else. The cert refuted it in one probe: a market with ``price_changed_at``
    59 days old and ``last_updated`` three minutes old came back ``eligible``
    with no blockers. **An actively polled market whose probability froze two
    months ago still reached the feed** — which is this ship's own failure
    class, one column to the left.

    The model says so in as many words: ``last_updated`` is a *TOUCH-STAMP.
    Written unconditionally by every poll, so it answers "when did the poller
    last SEE this row", NOT "when did this price move"*. ``price_changed_at``
    (#2024) is the column that answers the question this gate asks, maintained
    by `app/utils/price_change_stamp.py` on all five price-writing paths.

    ═══ WHY ``last_updated`` IS STILL THE FALLBACK, NOT DELETED ═══

    ``price_changed_at`` is NULLABLE and populated FORWARD — the model comment
    is explicit that *"a consumer switching to it must decide what NULL means
    for its own question rather than inheriting a fabricated value"*. Measured
    on production 2026-09-01: the column holds 116,719 of 3,911,727 outcome
    rows (3%) and its oldest value is **2026-08-20 — twelve days of history**.
    Keying on it alone would disarm a fourteen-day gate completely, and the
    named specimen proves it: all twelve outcomes of market ``12194657`` read
    ``price_changed_at IS NULL``.

    So NULL falls back to ``last_updated``, and the fallback is *sound* rather
    than merely convenient: **a price cannot have moved after the poller last
    wrote the row.** ``last_updated`` is therefore a genuine UPPER BOUND on the
    movement time, and using an upper bound can only make a market look
    FRESHER than it is. For a suppression gate that is the safe direction —
    it can never over-block, which is exactly the CERT-685 failure this ship
    already has a shelf of regression cases for.

    Because ``price_changed_at`` is written on the same statement as the price,
    it is always ``<= last_updated``, so this can only move a market's clock
    BACKWARDS. Composition, measured across all 37,967 open markets:

        blocked on last_updated alone   9,457
        blocked on this coalesce        9,457
        NEWLY blocked                       0
        clock value actually changed    4,495

    Four and a half thousand markets get a truer clock; none of them crosses
    the fourteen-day line, because twelve days of column history cannot. The
    arm is correct now and *becomes load-bearing* as coverage matures — which
    is why `TestAnActivelyPolledFrozenMarket` fakes the clock rather than
    waiting for it.

    ═══ ALL OUTCOMES, NOT THE TOP TEN ═══

    Measured on production 2026-09-01: of the 29,658 markets that pass the
    candidate SQL, **207 carry a tail outcome more than a day fresher than
    anything in their top ten by probability**. The scoring loop works from a
    top-ten slice, so a stamp taken from that slice would call those 207 dead.
    This takes the whole set.

    ``None`` means *no outcome carries either stamp*, which is different from
    *the stamps are old*. ``freshness_clock`` treats it as "no evidence either
    way" rather than as evidence of death — a writer that never sets the
    column must not take its whole source dark.

    ═══ WHY THIS IS NOT ``market.updated_at`` EITHER (UX-P251) ═══

    ``futures_markets.updated_at`` carries ``onupdate=func.now()``, so it is a
    touch-stamp on the PARENT row: a volume refresh or a category re-label
    rewrites it without a single price moving. Every staleness gate on the feed
    read that column, which is why a market whose twelve prices all froze on
    2026-07-04 reported ``days_stale ≈ 0`` on 2026-09-01 and scored 88 on
    Discover.

    ═══ TWO SHAPES, AND WHY AN UNREADABLE ONE DOES *NOT* RAISE ═══

    The feed carries an outcome in two forms — the ORM row and the plain
    ``outcomes_data`` dict the scoring loop builds from it — and both reach this
    function, so both are read.

    🔴 The first version of this helper RAISED on a shape it could not read, on
    the argument that returning ``None`` would silently disarm the gate. That
    argument was right about the danger and wrong about the remedy, and the full
    suite is what showed it: **the only caller is inside ``_score_futures``'s
    per-market ``try/except``** (gotcha #42, one bad item must never wipe a
    scoring pass). A raise there is not loud. It is caught, logged at WARNING,
    and the market is dropped from the feed — so the "strict" version turned a
    shape mismatch into *invisible card loss*, which is strictly worse than
    falling back to the parent clock and is the very failure class this ship is
    about.

    The tripwire belongs somewhere that cannot be swallowed, so it is a test:
    ``test_the_orm_model_still_carries_the_columns`` asserts the real
    ``FuturesOutcome`` has BOTH columns. A schema change fails CI instead of
    quietly emptying Discover — or, for ``price_changed_at``, instead of
    quietly demoting the gate back to the touch-stamp CERT-688 refuted.
    """
    newest: datetime | None = None
    for outcome in outcomes or ():
        stamp = _outcome_movement_stamp(outcome)
        if stamp is not None and (newest is None or stamp > newest):
            newest = stamp
    return newest


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


def is_probability_extreme(probability: float | None) -> bool:
    """True if the leader probability is at a dead extreme (<2% or >98%)."""
    if probability is None:
        return False
    return probability < PROBABILITY_EXTREME_LOW or probability > PROBABILITY_EXTREME_HIGH


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
