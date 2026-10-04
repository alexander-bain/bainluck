"""#10407 A1 — Polymarket's own stated no-winner cutoff for an MLB series winner.

PILLARS: MATCHING / TRUTH. A playoff game page asks "who wins the series" once,
with one blended number, and each venue keeps its own no-winner rules.

THE INPUT #9387's SETTLEMENT RULE NEEDS, AND THAT INGEST NEVER KEPT. A
Polymarket series-winner market resolves 50-50 if the series is not finished
by a stated instant:

    If a partial series is played and not completed by October 24, 2026,
    11:59 PM ET, this market will resolve to 50-50.

Kalshi's market for the same series says nothing about that case. The two
venues ask one question about the NAMED teams only while the series is decided
before Polymarket's cutoff (`futures_verified_title.compose_members`:
`game_at < deadline`). Ingest stores Gamma's `endDate` as `resolution_date`,
and that is the listing's own estimate (10-12 for a series whose cutoff is
10-24), so reading it as the cutoff would mislabel a field. The instant exists
only in the rule prose, so this module reads it from there.

AFFIRMATIVE, NOT CO-OCCURRENCE (root review, 2026-10-04). A date and the
string "50-50" in one sentence prove nothing: "will NOT resolve to 50-50" and
"If the Rays win by <instant>, this market will resolve to 50-50" both carry
them. So every sentence that mentions a 50-50 resolution must be, word for
word, one of the two no-winner clauses the retained specimens state
(`_CLAUSES`), with only the instant varying. Any other 50-50 sentence, an
amended wording included, refuses.

FAIL-CLOSED. Every way the prose can be unclear is a refusal and the key stays
ABSENT: no 50-50 clause, a 50-50 sentence that is not an admitted clause, two
different instants, a date with no year, a time or zone this grammar does not
read, a playoffs year that is not the instant's, or an event text that does
not say the same thing as its market's.

NEVER: Gamma `endDate`, `resolution_date`, or `neg_risk`. Pure: text in, value
out, no clock read.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

__all__ = [
    "NO_WINNER_CUTOFF_KEY",
    "MLB_SERIES_WINNER_SLUG_PREFIX",
    "MLB_SERIES_WINNER_FAMILY",
    "RULES_TEXT_SOURCE",
    "NOT_IN_FAMILY",
    "REFUSAL_REASONS",
    "is_mlb_series_winner_slug",
    "parse_no_winner_cutoff",
]

#: The `market_metadata` key. Binding name (#10407 A1 packet).
NO_WINNER_CUTOFF_KEY = "no_winner_cutoff"
#: The only Polymarket event family this reads.
MLB_SERIES_WINNER_SLUG_PREFIX = "mlb-playoffs-who-will-win-series-"
MLB_SERIES_WINNER_FAMILY = "mlb_series_winner"
RULES_TEXT_SOURCE = "polymarket_rules_text"

#: Out of family: the key is absent and nothing is counted.
NOT_IN_FAMILY = "not_in_family"

NO_CLAUSE = "no_50_50_clause"
UNSUPPORTED_CLAUSE = "unsupported_clause"
CONFLICTING_INSTANTS = "conflicting_instants"
MISSING_YEAR = "missing_year"
UNPARSEABLE_INSTANT = "unparseable_instant"
EVENT_MARKET_DISAGREE = "event_market_disagree"
NOT_ONE_MARKET = "not_one_market"

#: Every in-family refusal, in the order ingest counts them.
REFUSAL_REASONS = (
    NO_CLAUSE,
    UNSUPPORTED_CLAUSE,
    CONFLICTING_INSTANTS,
    MISSING_YEAR,
    UNPARSEABLE_INSTANT,
    EVENT_MARKET_DISAGREE,
    NOT_ONE_MARKET,
)

_ET = ZoneInfo("America/New_York")

_MONTHS = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)
_MONTH_ALT = "|".join(_MONTHS)

# A 50-50 resolution, in any spelling a dash or slash allows. Wider than the
# one spelling the clauses admit, so a sentence spelled `50/50` is still a
# 50-50 sentence that has to be an admitted clause, rather than an unread one.
_FIFTY_FIFTY_RE = re.compile(r"\b50\s*[-‐‑–—/]\s*50\b|\bfifty[\s-]fifty\b", re.I)

# The ONE admitted instant: `<Month> <D>, <YYYY>, <H>:<MM> PM ET`.
_INSTANT_RE = re.compile(
    rf"({_MONTH_ALT})\s+(\d{{1,2}}),\s*(\d{{4}}),\s*(\d{{1,2}}):(\d{{2}})\s*PM\s+ET",
    re.I,
)
_YEAR_AFTER_DAY_RE = re.compile(rf"({_MONTH_ALT})\s+\d{{1,2}}\s*,?\s*\d{{4}}\b", re.I)

# The two no-winner clauses, as Gamma states them for events 1120800 and
# 1120859. Whole-sentence matches; `when` is the only free slot and must then
# read as `_INSTANT_RE`. `{year}` must be the instant's year.
_CLAUSES = (
    re.compile(
        r"if a partial series is played and not completed by (?P<when>.+?), "
        r"this market will resolve to 50-50\.?",
        re.I,
    ),
    re.compile(
        r"if the (?P<year>\d{4}) mlb playoffs are (?:cancelled|canceled), postponed after "
        r"(?P<when>.+?), or there is otherwise no winner declared within that "
        r"timeframe, this market will resolve to 50-50\.?",
        re.I,
    ),
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def is_mlb_series_winner_slug(slug: Optional[str]) -> bool:
    return isinstance(slug, str) and slug.startswith(MLB_SERIES_WINNER_SLUG_PREFIX)


def _clauses(text: str) -> list[str]:
    out: list[str] = []
    for paragraph in re.split(r"\n\s*\n|\n", text):
        out.extend(s for s in _SENTENCE_SPLIT_RE.split(paragraph.strip()) if s)
    return out


def _instant(when: str) -> tuple[Optional[datetime], Optional[str]]:
    """The admitted instant ``when`` names, or why it is not one."""
    match = _INSTANT_RE.fullmatch(when.strip())
    if match is None:
        if not _YEAR_AFTER_DAY_RE.search(when):
            return None, MISSING_YEAR
        return None, UNPARSEABLE_INSTANT
    month = _MONTHS.index(match.group(1).lower()) + 1
    day, year = int(match.group(2)), int(match.group(3))
    hour, minute = int(match.group(4)), int(match.group(5))
    if not 1 <= hour <= 12 or not 0 <= minute <= 59:
        return None, UNPARSEABLE_INSTANT
    hour = 12 if hour == 12 else hour + 12  # PM
    try:
        local = datetime(year, month, day, hour, minute, tzinfo=_ET)
    except ValueError:
        return None, UNPARSEABLE_INSTANT
    return local.astimezone(timezone.utc), None


def _read_clause(clause: str) -> tuple[Optional[datetime], Optional[str]]:
    """One 50-50 sentence → its instant, or the refusal."""
    sentence = re.sub(r"\s+", " ", clause).strip()
    for template in _CLAUSES:
        match = template.fullmatch(sentence)
        if match is None:
            continue
        at, reason = _instant(match.group("when"))
        if at is None:
            return None, reason
        year = match.groupdict().get("year")
        if year is not None and int(year) != at.astimezone(_ET).year:
            return None, UNSUPPORTED_CLAUSE
        return at, None
    return None, UNSUPPORTED_CLAUSE


def _read_text(text: Optional[str]) -> tuple[Optional[dict], Optional[str]]:
    """One text → ``({"at", "clauses"}, None)`` or ``(None, reason)``."""
    if not isinstance(text, str) or not text.strip():
        return None, NO_CLAUSE
    clauses = [c for c in _clauses(text) if _FIFTY_FIFTY_RE.search(c)]
    if not clauses:
        return None, NO_CLAUSE
    instants: set[datetime] = set()
    for clause in clauses:
        at, reason = _read_clause(clause)
        if at is None:
            return None, reason
        instants.add(at)
    if len(instants) != 1:
        return None, CONFLICTING_INSTANTS
    (at,) = instants
    return {"at": at.isoformat(), "clauses": len(clauses)}, None


def parse_no_winner_cutoff(
    *,
    slug: Optional[str],
    market_descriptions: list[Optional[str]],
    event_description: Optional[str] = None,
) -> tuple[Optional[dict], Optional[str]]:
    """The ``no_winner_cutoff`` value for one Polymarket event, or a refusal.

    Returns ``(value, None)`` on success, ``(None, NOT_IN_FAMILY)`` for any
    other slug, and ``(None, reason)`` with ``reason`` in ``REFUSAL_REASONS``
    otherwise. ``market_descriptions`` is every market's own rule text; the
    family is one market, so anything else refuses.
    """
    if not is_mlb_series_winner_slug(slug):
        return None, NOT_IN_FAMILY
    if len(market_descriptions) != 1:
        return None, NOT_ONE_MARKET
    reading, reason = _read_text(market_descriptions[0])
    if reading is None:
        return None, reason
    if isinstance(event_description, str) and event_description.strip():
        event_reading, _ = _read_text(event_description)
        if event_reading != reading:
            return None, EVENT_MARKET_DISAGREE
    return {
        "at": reading["at"],
        "source": RULES_TEXT_SOURCE,
        "family": MLB_SERIES_WINNER_FAMILY,
        "clauses": reading["clauses"],
    }, None
