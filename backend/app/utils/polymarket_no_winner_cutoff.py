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

FAIL-CLOSED. Every way the prose can be unclear is a refusal and the key stays
ABSENT: no 50-50 clause, a 50-50 clause with no instant, two different
instants, a date with no year, a time or zone this grammar does not read, or
an event text that does not say the same thing as its market's. A date in a
50-50 clause that is not in the one admitted shape is a refusal too, so a
second, differently spelled instant can never hide behind the first.

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
CLAUSE_WITHOUT_INSTANT = "clause_without_instant"
CONFLICTING_INSTANTS = "conflicting_instants"
MISSING_YEAR = "missing_year"
UNPARSEABLE_INSTANT = "unparseable_instant"
EVENT_MARKET_DISAGREE = "event_market_disagree"
NOT_ONE_MARKET = "not_one_market"

#: Every in-family refusal, in the order ingest counts them.
REFUSAL_REASONS = (
    NO_CLAUSE,
    CLAUSE_WITHOUT_INSTANT,
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
# one spelling seen so that a second clause spelled `50/50` is still a clause
# whose instant must agree, rather than an unread sentence.
_FIFTY_FIFTY_RE = re.compile(r"\b50\s*[-‐‑–—/]\s*50\b|\bfifty[\s-]fifty\b", re.I)

# The ONE admitted instant: `by|after <Month> <D>, <YYYY>, <H>:<MM> PM ET`.
_INSTANT_RE = re.compile(
    rf"\b(?:by|after)\s+({_MONTH_ALT})\s+(\d{{1,2}}),\s*(\d{{4}}),\s*(\d{{1,2}}):(\d{{2}})\s*PM\s+ET\b",
    re.I,
)
# Any month-day mention at all. Every one inside a 50-50 clause must sit inside
# an admitted instant, or the clause refuses.
_MONTH_DAY_RE = re.compile(rf"\b({_MONTH_ALT})\s+(\d{{1,2}})\b", re.I)
_YEAR_AFTER_DAY_RE = re.compile(r"\s*,?\s*\d{4}\b")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def is_mlb_series_winner_slug(slug: Optional[str]) -> bool:
    return isinstance(slug, str) and slug.startswith(MLB_SERIES_WINNER_SLUG_PREFIX)


def _clauses(text: str) -> list[str]:
    out: list[str] = []
    for paragraph in re.split(r"\n\s*\n|\n", text):
        out.extend(s for s in _SENTENCE_SPLIT_RE.split(paragraph.strip()) if s)
    return out


def _instant(match: re.Match) -> Optional[datetime]:
    month = _MONTHS.index(match.group(1).lower()) + 1
    day, year = int(match.group(2)), int(match.group(3))
    hour, minute = int(match.group(4)), int(match.group(5))
    if not 1 <= hour <= 12 or not 0 <= minute <= 59:
        return None
    hour = 12 if hour == 12 else hour + 12  # PM
    try:
        local = datetime(year, month, day, hour, minute, tzinfo=_ET)
    except ValueError:
        return None
    return local.astimezone(timezone.utc)


def _read_text(text: Optional[str]) -> tuple[Optional[dict], Optional[str]]:
    """One text → ``({"at", "clauses"}, None)`` or ``(None, reason)``."""
    if not isinstance(text, str) or not text.strip():
        return None, NO_CLAUSE
    clauses = [c for c in _clauses(text) if _FIFTY_FIFTY_RE.search(c)]
    if not clauses:
        return None, NO_CLAUSE
    instants: set[datetime] = set()
    for clause in clauses:
        admitted = list(_INSTANT_RE.finditer(clause))
        spans = [m.span() for m in admitted]
        for mention in _MONTH_DAY_RE.finditer(clause):
            if any(lo <= mention.start() < hi for lo, hi in spans):
                continue
            # A date the admitted shape did not read: say which way it failed.
            if not _YEAR_AFTER_DAY_RE.match(clause, mention.end()):
                return None, MISSING_YEAR
            return None, UNPARSEABLE_INSTANT
        if not admitted:
            return None, CLAUSE_WITHOUT_INSTANT
        for m in admitted:
            at = _instant(m)
            if at is None:
                return None, UNPARSEABLE_INSTANT
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
