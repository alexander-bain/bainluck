"""Deterministic Discover card rendering classification.

This module decides what shape a Discover futures card *could* take without
changing ranking. The frontend can use this as a stable contract for native
cards, while admin/debug views can audit whether the feed is full of cards that
need heatmaps, bundles, distributions, timelines, or recap treatment.
"""

from __future__ import annotations

import re
from typing import Any

from app.utils.market_grouping import extract_threshold
from app.utils.outcome_display import (
    LADDER_MIN_DRAWN_RUNGS,
    incoherent_ladder_indexes,
)
from app.utils.outcome_display_names import display_outcome_names

_IPO_RE = re.compile(r"\b(ipo|initial public offering|market cap|valuation)\b", re.I)
_COMMODITY_RE = re.compile(
    r"\b(gold|xauusd|oil|wti|brent|natural gas|silver|copper|wheat|corn|soybean)\b",
    re.I,
)
_ROTTEN_TOMATOES_RE = re.compile(r"\b(rotten tomatoes|rt score|tomatometer)\b", re.I)
_MACRO_RANGE_RE = re.compile(
    r"\b(cpi|ppi|fed|rate cuts?|gdp|unemployment|consumer confidence|s&p|nasdaq|dow)\b",
    re.I,
)
_WEATHER_RANGE_RE = re.compile(
    r"\b(temperature|high temp|low temp|rainfall|snowfall|hurricane|landfall)\b",
    re.I,
)
_SPORTS_BRACKET_RE = re.compile(
    r"\b(playoff|finals?|champion|championship|world cup|stanley cup|super bowl|"
    r"wimbledon|french open|us open|australian open)\b",
    re.I,
)
# A venue writes its unit glued to the number as often as spaced: "25bps" has no
# word boundary after the 5, so the trailing `\b` refused the whole match and the
# label scored NOTHING while "25 bps" scored 25 (#4364). The bound therefore
# admits ONE extra thing — a basis-point unit sitting directly against the digits
# — and nothing else.
#
# It is deliberately not the general "the number ended" relaxation, which is the
# obvious fix and is wrong: measured over 12,077 production outcome labels it
# changed 3,477 of them, because a digit against a letter is far more often an
# ORDINAL than a unit. "ARI Cardinals wins 2Q by over 7.5 points" stopped scoring
# 7.5 and started scoring 2 — the quarter number — and the gamer tag "Rad3on"
# acquired a rung at 3. Same class as #4226 and #3567: a number inside a name.
#
# The k/m/b/t suffix carries `(?![a-z])` for the matching reason: in "25bps" the
# `b` is the head of "bps", not a billions suffix, and consuming it left the
# bound stranded mid-word.
_COMPACT_VALUE_RE = re.compile(
    r"(\$?)\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*([kmbt](?![a-z]))?(?:\b|(?=bps\b|bp\b))",
    re.I,
)

#: A basis-point unit written against its number — the one glued unit #4364
#: admits, and the only label shape allowed to borrow a comparator below.
_GLUED_BPS_RE = re.compile(r"\d(?:bps|bp)\b", re.I)

# #7778 — A MINUS IN FRONT OF A NUMBER IS A SIGN; A MINUS BETWEEN TWO NUMBERS IS
# A RANGE. `_COMPACT_VALUE_RE`'s value group starts at `\d`, so the sign was
# invisible to it and the negative half of a mixed-sign axis folded onto the
# positive half: the live "South Africa GDP growth rate QoQ" ladder drew
# "Above -0.2%" and "Above 0.2%" at the SAME coordinate, so its cumulative
# prices read 72.5 -> 81.5 -> 62.5 -> 90.5 -> 40.5 and the card said the chance
# of growth above 0.4% exceeded the chance of growth above 0.0%. Same defect as
# #7081, whose `re.findall(r'[\d.]+', label)` put 42 points of probability on
# deflation — a second module, never a regression of the first.
#
# This is matched against the text ENDING at the number's first digit, and it is
# deliberately the narrow form, because the same character separates the two
# halves of a range and #4364's lesson is that widening this regex re-reads a
# whole population. Two conditions, both required:
#
#   * the sign ABUTS its digits (an optional currency mark aside) — so
#     "September 15 - 30, 2026" and "$100 - $200" keep their separator; and
#   * what precedes the sign is the start of the label, a space, or an opening
#     bracket/comparator — so a number ENDING the previous token keeps its
#     separator ("7-8m", "160-170m", "Hike 1-25bps", "$1.00-$1.10T") and a
#     letter ending it does too ("COVID-19", "F-150", "Claude Opus 4-6").
#
# The unsigned population is therefore untouched by construction: a label with
# no minus in front of a digit cannot reach this branch at all.
_LEADING_SIGN_RE = re.compile(r"(?:^|[\s(\[<>=:,])[-−]\$?$")


def _compact_value_thresholds(label: str) -> list[tuple[float, str, str]]:
    """Parse compact finance/range labels such as "$1.5T-$2.0T"."""
    values: list[tuple[float, str, str]] = []
    for match in _COMPACT_VALUE_RE.finditer(label):
        dollar, raw_value, suffix = match.groups()
        value = float(raw_value.replace(",", ""))
        multiplier = {
            "k": 1_000,
            "m": 1_000_000,
            "b": 1_000_000_000,
            "t": 1_000_000_000_000,
        }.get((suffix or "").lower(), 1)
        negative = bool(_LEADING_SIGN_RE.search(label[: match.start(2)]))
        if not negative and not dollar and not suffix and 2020 <= value <= 2099:
            # The bare-year guard reads an UNSIGNED number: "2026-27 Stanley Cup"
            # is a season, "-2026" is a quantity. A signed number is never a year.
            continue
        unit = f"{dollar}{(suffix or '').upper()}".strip()
        values.append((-value * multiplier if negative else value * multiplier, unit, "exact"))
    return values


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


# UX-P005 class (b). A label only earns a threshold rung if it actually reads
# as a numeric threshold. Without this, any digit inside a title becomes a rung
# — "The Bombing of Pan Am 103" scored 103.0 and sorted between the 1s and 3s
# of a Netflix ladder, and "June 30, 2027" scored 30.
#
# The `\d-\d` range branch lives apart from the rest (see `_is_threshold_shaped`)
# because it is the one branch a NON-measurement can satisfy by accident.
_THRESHOLD_SHAPED_RE = re.compile(
    r"[$%<>+]"                     # $6,000 · 45% · <130m · 9m+
    r"|\d\s*[kmbt]\b"              # 6m · 1.5t
    r"|(?<![a-z])(?:bps|bp)\b"     # 1 (25 bps) · 25bps

    r"|\b(?:under|over|above|below|at least|at most|more than|less than)\b",
    re.I,
)

_RANGE_SHAPED_RE = re.compile(r"\d\s*[-–]\s*\d")  # 7-8m · 160-170m · 80–83
_LETTER_RE = re.compile(r"[A-Za-z]")


def _is_threshold_shaped(label: str) -> bool:
    """Does this label read as a numeric threshold at all?

    #4226. The `\\d-\\d` branch was the whole shape test for a bare range, and a
    bare range is exactly what an IDENTIFIER looks like once you stop reading
    the words around it. Measured on production 2026-09-09, that branch was
    minting rungs out of:

      * model versions — "Claude Opus 4-6 Thinking" and "Claude Opus 4-7" both
        scored (4.0, '', 'exact'), so the six-model field "Top AI model in
        September?" was drawn as a two-rung ladder at ONE value and the 71%
        favourite had no rung at all;
      * scorelines — "Barcelona SC 0 - 1 Delfin SC" scored 0.0, turning a
        16-scoreline field into a ladder of repeated goal counts;
      * founding years riding along with a scoreline — "Como 1907 2 - 2 RB
        Leipzig" scored **1907**, because the shape test matched `2 - 2` while
        `_compact_value_thresholds` took the FIRST number in the label.

    Same class as #3567 ("SF 49ers" -> 49.0): a number inside a proper noun.

    The separator, measured rather than guessed: a real range OPENS its label.
    Across the 9,779 production outcome labels carrying a `\\d-\\d` and no other
    threshold shape, every one of the 2,890 with no letters before the range is
    a genuine band ("72-73°F", "80–83", "7-8m"), and every one of the 4,901 with
    letters before it is an identifier — a scoreline ("Draw 1-1", "Exact Score:
    0-2", "Frances Tiafoe wins 3-2", "FC Dallas 2 - 2 Portland Timbers"), a
    model version, or a date range whose rung would be the day number
    ("September 15 - 30, 2026" -> 15). So a bare `\\d-\\d` with letters to its
    LEFT earns no rung.

    Labels carrying a unit, a comparator or a k/m/b/t suffix never reach this
    test — they are shaped on their own account, which is why "Republican
    0-3%", "Under 4-6 inches" and "1 (25 bps)" are unaffected.
    """
    if _THRESHOLD_SHAPED_RE.search(label):
        return True
    match = _RANGE_SHAPED_RE.search(label)
    if not match:
        return False
    return not _LETTER_RE.search(label[: match.start()])

# Two rungs whose values differ by more than this factor cannot be the same
# ladder — it means the label set was parsed on mixed scales. Bail out rather
# than render bars that contradict each other.
_MAX_LADDER_SCALE_SPREAD = 10_000

# At or above this many outcomes a market is a FIELD, not a threshold question,
# and `outcome_distribution` is its card. Pinned to the same number the
# classifier uses for that branch (`count >= 4`); a test asserts they agree, so
# the two can never drift into a window where a market is neither.
_FIELD_OUTCOME_FLOOR = 4


def _suffix_multiplier(label: str) -> int:
    """Largest k/m/b/t multiplier appearing in a label.

    In a range label the suffix is written once but governs both numbers:
    "7-8m" means 7 million to 8 million, not 7 to 8 million. Callers apply this
    to bare leading numbers so a ladder stays on one scale.
    """
    multiplier = 1
    for match in re.finditer(r"(\d)\s*([kmbt])\b", label, re.I):
        multiplier = max(
            multiplier,
            {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000, "t": 1_000_000_000_000}[
                match.group(2).lower()
            ],
        )
    return multiplier


def _outcome_threshold_value(label: str) -> tuple[float, str, str] | None:
    """ONE threshold rung for one outcome label, on a unit-aware scale.

    Replaces a two-parser split that put a single ladder on two different
    scales: ``extract_threshold`` returned the raw number ("<6m" -> 6) while
    ``_compact_value_thresholds`` multiplied it ("<6m" -> 6,000,000). Emitting
    both also produced duplicate rungs — "1 (25 bps)" became a rung at 1 AND a
    rung at 25 in the same Fed ladder.
    """
    if not _is_threshold_shaped(label):
        return None
    compact = _compact_value_thresholds(label)
    if compact:
        value, unit, direction = compact[0]
        if abs(value) < _MAX_LADDER_SCALE_SPREAD:
            # A bare leading number in a range label inherits the label's suffix.
            value *= _suffix_multiplier(label)
        if direction == "exact" and _GLUED_BPS_RE.search(label):
            # `_compact_value_thresholds` is a VALUE parser -- it hardcodes
            # "exact" and has never read a comparator. That was invisible while
            # every comparator label fell through to `extract_threshold`, and
            # #4364's unit fix ended it for exactly one shape: "Hike more than
            # 25bps" now matches compact and would silently lose its "more
            # than". Borrow the direction back rather than restate the
            # comparator vocabulary here -- and borrow it ONLY for the shape
            # this fix newly admitted, so no label that already parsed changes
            # its direction. Applied unconditionally it moved 3,399 labels,
            # reading "$1.00-$1.10T" and "$134-$136" -- bands, whose direction
            # is "exact" by construction -- as "above".
            extracted = extract_threshold(label)
            if extracted and extracted[2] != "exact":
                direction = extracted[2]
        return value, unit, direction
    extracted = extract_threshold(label)
    if not extracted:
        return None
    value, unit, direction = extracted
    return value * _suffix_multiplier(label), unit, direction


# ── SIGNED AXES (#4364) ──
#
# "Hike more than 25bps" and "Cut more than 25bps" both parse to +25: the
# comparator is read, the DIRECTION word is not. Production 2026-09-09 served
# two such cards on page one (South African Reserve Bank September, Bank of
# Japan December) as two-rung ladders whose rungs are semantic opposites drawn
# at one identical coordinate — and with the three middle outcomes ("Hike
# 25bps", "Cut 25bps", "No change") absent altogether, so the reader got the two
# LEAST likely outcomes, stacked, and no modal outcome at all.
#
# Signing is decided by the SET, never by a label on its own, and that is the
# whole safety argument. A ladder earns a signed axis only when both directions
# are represented in it — which is what makes zero an interior point rather than
# an end. So one-directional ladders are untouched by construction: "Above 52 /
# Above 58 / Above 67" carries no fall word, a weather ladder of "falls below"
# rungs carries no rise word, and the 277 band ladders #4226 measured carry no
# direction word at all. Negating on a per-label token instead — the obvious
# implementation — would have moved every one of them.
# The vocabulary is POLICY VERBS, and deliberately excludes the ordinary-English
# direction words — "up", "down", "rise", "fall", "drop". Measured over every
# open market (70 sign), those five are load-bearing for NOTHING: removing all of
# them loses exactly two markets and both are false positives —
# "Top U.S. Selling Vinyl Album: 2026" and its CD twin, which sign on the single
# track title "The Rise and Fall of a Midwest Princess" (one label supplying both
# halves of the gate) alongside "The Fall Off" and "Hurry Up Tomorrow". The
# load-bearing tokens are `hike`/`cut` (43 markets each) and
# `increase`/`decrease` (25 each); the rest are unused today and kept because
# they are unambiguous policy verbs a venue may yet use.
_LADDER_FALL_RE = re.compile(
    r"\b(?:cut|cuts|lower|lowers|decrease|decreases|"
    r"decline|declines|ease|eases)\b",
    re.I,
)
_LADDER_RISE_RE = re.compile(
    r"\b(?:hike|hikes|raise|raises|increase|increases|climb|climbs)\b",
    re.I,
)
# The interior rung of a signed ladder. On an UNSIGNED ladder "no change" is not
# a magnitude at all, and "hold" is a team as often as a rate decision — the
# bidirectional gate is what makes reading these as zero safe.
#
# "maintains" is here because the venue writes it: the eight live "Fed decision
# in <month>" ladders phrase their hold as "Fed maintains rate", not "No change",
# and that rung is the modal outcome of the card. Read off the live population
# rather than guessed — a lexicon written from the two markets in the issue would
# have left those eight without their most likely outcome.
_LADDER_ZERO_RE = re.compile(
    r"\b(?:no\s+change|unchanged|no\s+hike|no\s+cut|maintains?|hold|holds)\b",
    re.I,
)

#: Flipping a rung to the far side of zero flips what "more than" points at:
#: "Cut more than 25bps" is not above -25, it is below it.
_MIRRORED_DIRECTION = {"above": "below", "below": "above"}

#: Reading order within one value, so a tie is resolved by meaning rather than
#: by the order the venue happened to list its outcomes in. An open-ended bucket
#: reaching away from zero sorts outside the exact rung it shares a value with.
_DIRECTION_SORT_RANK = {"below": 0, "exact": 1, "above": 2}


def _ladder_axis_is_signed(labels: list[str]) -> bool:
    """Do these labels describe movement in BOTH directions?

    The trigger for signing, and deliberately a property of the SET: a lone
    "Cut 25bps" on a ladder of cuts is a magnitude, not a negative number.
    """
    return any(_LADDER_FALL_RE.search(label) for label in labels) and any(
        _LADDER_RISE_RE.search(label) for label in labels
    )


# ── DATE BUCKETS (UX-1052 item 4) ──
#
# Alex, on the Discover card "When will Apple release the iPhone 18?":
#
#     "Multi-outcome date questions are unreadable … shows one number (15%,
#      'Before 2027') … Design: outcomes as ordered bars (Before Oct · Before
#      2027 · …) with the leader marked and the mover marked. Applies to every
#      date-bucket / multi-outcome futures card, not this one."
#
# The card's outcomes are "Before April", "Before July", "Before October",
# "Before 2027". None of them is a threshold: `_compact_value_thresholds`
# refuses bare years by design (2020-2099 without a unit -- the guard that stops
# "2026-27 Stanley Cup" scoring a rung at 27), and a month name carries no
# number at all. So the ladder came back empty, the market had only two
# card-eligible outcomes after the fabricated-book filter, and the card fell
# through to the one-number Variant A.
#
# A date bucket IS a rung -- its axis is time rather than magnitude. Parsing it
# as one puts the question on the ladder the design already has for "by WHEN"
# (`threshold_heatmap` + `QuantityGroup wideLabels`), in chronological order.

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# #7403 -- A DAY IS A DATE BUCKET TOO, and it is the one the venues actually
# write. The month-granularity shapes above are the Kalshi/manual phrasing
# ("Before October", "March 2027"); Polymarket's "by when?" ladders are
# day-granularity and carry no framing word at all. Live on production
# 2026-09-19, the Discover bundle card for "Iran leadership change?" served:
#
#     1  June 30, 2027   26%
#     2  December 31     15%
#     3  November 30      9%
#     4  October 31       6%
#     5  Field and 2 more outcomes
#
# Six outcomes summing to 55.5%, strictly nested and monotone in time — a
# cumulative ladder, drawn as a ranked field of rivals with a "Field" row,
# directly under the card's own subtitle "26% chance BY June 30, 2027". Every
# label was refused here: `month`+`monthyear` wants four digits after the month,
# `month2` wants nothing after it at all, so "June 30, 2027" and "December 31"
# both fell through, `_date_bucket_points` returned [], and the cascade dropped
# to the `count >= 4` field arm.
#
# A bare month ("October") still needs its before/by framing — it is a common
# English word and a label as often as a cutoff. A month WITH A DAY does not:
# "December 31" is not a word, it is a date, so the day is its own framing.
#: Days in each month, February read leap-tolerantly for the year-less case.
_MONTH_DAYS = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
               7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


def _month_length(month: int, year: int | None) -> int:
    """How many days this month has -- exactly, when the year is known."""
    if month == 2 and year is not None:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        return 29 if leap else 28
    return _MONTH_DAYS.get(month, 31)


_DATE_BUCKET_RE = re.compile(
    r"""
    ^\s*
    (?:(?P<lead>before|by|prior\s+to|on\s+or\s+before|in|during|after|from)\s+)?
    (?:
        (?P<monthd>[a-z]+)\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?
        (?:\s*,?\s*(?P<dayyear>\d{4}))?
      | (?P<month>[a-z]+)\s+(?P<monthyear>\d{4})
      | (?P<month2>[a-z]+)
      | (?P<year>\d{4})
    )
    (?:\s+(?P<tail>or\s+later|or\s+earlier|or\s+after|or\s+before))?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _parse_date_bucket(label: str) -> tuple[int | None, int, int] | None:
    """Parse a date-bucket outcome label into ``(year_or_None, month, day)``.

        "Before October"     -> (None, 10, 0)
        "Before 2027"        -> (2027, 1, 0)
        "March 2027"         -> (2027, 3, 0)
        "2029 or later"      -> (2029, 1, 0)
        "December 31"        -> (None, 12, 31)
        "June 30, 2027"      -> (2027, 6, 30)

    Day ``0`` means "this bucket names no day", and it sorts BEFORE every real
    day of the same month — which is the correct reading: "Before October" is a
    cutoff at the top of the month, so it precedes "October 31".

    Returns None for anything that is not confidently a date bucket. The
    refusal is the load-bearing half: this parser runs over every outcome label
    on the site, and a false positive turns a candidate field into a fake
    timeline.
    """
    m = _DATE_BUCKET_RE.match(label or "")
    if not m:
        return None
    if m.group("day"):
        # The month-name lookup is the guard, not the digits: "Over 2" and
        # "Top 5" reach here with the same shape and are refused by it.
        month = _MONTHS.get(m.group("monthd").lower())
        if not month:
            return None
        day = int(m.group("day"))
        dayyear = m.group("dayyear")
        year = int(dayyear) if dayyear else None
        if year is not None and not 1900 <= year <= 2999:
            return None
        # A day the month does not have is not a date, and this arm's whole
        # licence is that "December 31" is unambiguously one. "Feb 30" parses
        # to a shape and means nothing, so it is refused rather than placed.
        # With no year to check against, February is read leap-tolerantly —
        # the parser never guesses a year, here or anywhere else in it.
        if not 1 <= day <= _month_length(month, year):
            return None
        return (year, month, day)
    if m.group("monthyear"):
        month = _MONTHS.get(m.group("month").lower())
        return (int(m.group("monthyear")), month, 0) if month else None
    if m.group("month2"):
        # A bare month name only -- no year to anchor it yet.
        month = _MONTHS.get(m.group("month2").lower())
        if not month:
            return None
        # A lone month with no qualifier ("October") is a label, not a bucket;
        # require the "before/by/after" framing that makes it a cutoff.
        return (None, month, 0) if m.group("lead") else None
    year = int(m.group("year"))
    if not 1900 <= year <= 2999:
        return None
    return (year, 1, 0)


def _date_bucket_points(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ladder rungs for a set of date-bucket outcomes, chronologically ordered.

    Returns [] unless EVERY outcome parses. A partial timeline is worse than
    none: the rungs it can place look authoritative while the ones it cannot
    are silently missing, which is the class of defect this queue is clearing.
    """
    if len(outcomes) < 2:
        return []

    parsed: list[tuple[dict[str, Any], int | None, int, int]] = []
    for outcome in outcomes:
        label = _clean_text(outcome.get("name") or outcome.get("label"))
        got = _parse_date_bucket(label)
        if got is None:
            return []
        parsed.append((outcome, got[0], got[1], got[2]))

    years = [y for _, y, _, _ in parsed if y is not None]
    if years and any(y is None for _, y, _, _ in parsed):
        # "Before October" alongside "Before 2027" means October of the year
        # BEFORE the first dated bucket -- that is what makes the sequence a
        # sequence. Anchoring month-only buckets to the earliest named year
        # minus one is the only reading under which they precede it.
        anchor = min(years) - 1
    elif years:
        anchor = None
    else:
        # No year anywhere: relative month order is still a correct ladder.
        anchor = 2000

    points: list[dict[str, Any]] = []
    for outcome, year, month, day in parsed:
        resolved_year = year if year is not None else anchor
        if resolved_year is None:
            return []
        points.append(
            {
                "source": "date_bucket",
                "label": _clean_text(outcome.get("name") or outcome.get("label")),
                # #7403 -- YYYYMMDD, widened from YYYYMM so two rungs in one
                # month cannot tie. `value` is an ordering key and nothing else
                # (`FuturesCard.buildHeatmapRows` reads it only as `sortValue`),
                # so the scale may move as long as every rung on one board is
                # built in this same pass — which it is.
                "value": resolved_year * 10000 + month * 100 + day,
                "unit": "date",
                "direction": "before",
                "probability": (
                    outcome.get("probability")
                    if outcome.get("probability") is not None
                    else outcome.get("current_probability")
                ),
                "movement": (
                    outcome.get("movement")
                    if outcome.get("movement") is not None
                    else outcome.get("probability_change_24h")
                ),
            }
        )
    points.sort(key=lambda p: float(p["value"]))
    return points


def _ladder_is_scale_coherent(points: list[dict[str, Any]]) -> bool:
    magnitudes = [abs(float(p["value"])) for p in points if p.get("value")]
    if len(magnitudes) < 2:
        return True
    return max(magnitudes) / min(magnitudes) <= _MAX_LADDER_SCALE_SPREAD


def _threshold_points(
    *,
    name: str,
    outcomes: list[dict[str, Any]],
    outcome_count: int | None,
    ladder_already_refused: bool = False,
) -> list[dict[str, Any]]:
    # CERT-2451 — the caller may have made this decision already. A serializer
    # that filtered the incoherent rungs out of its own outcome list hands us a
    # ladder that is coherent BY CONSTRUCTION, so the guard below cannot see
    # that it is standing on one rung of a collapsed one. When the caller says
    # it collapsed, the treatment is refused here exactly as if we had found it
    # ourselves — including the market-name fallback, which is skipped because
    # this returns before it (falling back would resurrect the treatment the
    # serializer just refused, the UX-P008 clause 2 failure).
    if ladder_already_refused:
        return []
    # UX-1052 item 4 -- a date question is a ladder whose axis is time. Tried
    # FIRST, and returned whole: a set of date buckets must never be half-read
    # as magnitudes ("Before 2027" scoring a rung at 2027 beside a month that
    # scores nothing) -- which is exactly what the numeric parser below would do
    # if the year guard were ever relaxed.
    date_points = _date_bucket_points(outcomes)
    if date_points:
        return date_points

    points: list[dict[str, Any]] = []

    # #4364 -- decided once, over the whole set, before any label is scored.
    signed_axis = _ladder_axis_is_signed(
        [_clean_text(outcome.get("name")) for outcome in outcomes]
    )

    zero_points: list[dict[str, Any]] = []

    for outcome in outcomes:
        outcome_name = _clean_text(outcome.get("name"))
        # Exactly ONE rung per outcome, on one scale (UX-P005 class b).
        resolved = _outcome_threshold_value(outcome_name)
        is_zero_rung = False
        if resolved is None:
            # "No change" carries no number, so it is not threshold-shaped and
            # never was a rung -- yet on a signed axis it is the one rung the
            # reader most needs, and usually the modal outcome.
            if not (signed_axis and _LADDER_ZERO_RE.search(outcome_name)):
                continue
            resolved = (0.0, "", "exact")
            is_zero_rung = True
        value, unit, direction = resolved
        # #7778 — a label that carries its own minus is ALREADY in signed
        # coordinates ("Cut to -0.25%" is not +0.25 waiting to be flipped), so
        # only a MAGNITUDE is negated by a policy verb. Without the `>= 0` the
        # two mechanisms cancel and the rung lands back on the wrong half.
        if signed_axis and value >= 0 and _LADDER_FALL_RE.search(outcome_name):
            # `-0.0` is a real float and it reaches the payload: the live "NYC
            # population change" ladder opens on "Decrease 0-0.99%", whose
            # magnitude is 0. Normalise it so no served rung is negative zero.
            value = -value if value else 0.0
            direction = _MIRRORED_DIRECTION.get(direction, direction)
        (zero_points if is_zero_rung else points).append(
            {
                "source": "outcome",
                "label": outcome_name,
                "value": value,
                "unit": unit,
                "direction": direction,
                "probability": (
                    outcome.get("probability")
                    if outcome.get("probability") is not None
                    else outcome.get("current_probability")
                ),
            }
        )

    # A zero rung is an ADDITION to a ladder, never a ladder by itself. The live
    # "US test scores in Math in 2026?" set is the case: "Significant decrease /
    # No significant difference / Significant increase" signs the axis on its
    # direction words while carrying no number anywhere, so admitting its middle
    # label alone would mint a one-rung "ladder" out of a market that has no
    # magnitudes at all.
    if points:
        points.extend(zero_points)

    # Monotonic display: a ladder read top-to-bottom must not double back.
    # Two rungs may legitimately share a value (#4226: a band ladder's
    # open-ended first bucket collides with the bucket above it, and 277
    # production markets do). Where they do, the open-ended one reads outside
    # the exact one rather than wherever the venue happened to list it.
    points.sort(
        key=lambda p: (
            float(p["value"]),
            _DIRECTION_SORT_RANK.get(p.get("direction"), 1),
        )
    )

    # #4610 — and neither must its PRICES. On a cumulative ladder ("Above 52",
    # "Above 58", "Above 67") each rung is a strict subset of every looser rung,
    # so a rung priced above one of them is not a bar the reader can be asked to
    # read: the two bars cannot both be true. Runs on the ladder as parsed, not
    # on the [:12] slice the caller returns, because the rung that breaks the
    # ordering is frequently outside the first twelve (production 2026-09-09,
    # "USDINR price on Sep 11": "Above 94.609" at 65% over a 62% floor, rung 21
    # of 30). Callers that own an outcome list filter it upstream as well; this
    # is the display primitive's own guard, for the admin/debug and native
    # callers that do not.
    rejected_incoherent = False
    incoherent = incoherent_ladder_indexes(
        points,
        lambda p: p.get("label"),
        lambda p: p.get("probability"),
    )
    if incoherent:
        survivors = [p for n, p in enumerate(points) if n not in incoherent]
        if len(survivors) >= 2:
            points = survivors
        else:
            # A ladder filtered down to ONE rung must not be handed on as a
            # ladder. The classifier below will still call it `threshold_heatmap`
            # when the market carries a group or canonical key, the frontend
            # needs >= 2 rows to draw a heatmap, finds one, and falls through
            # PAST the distribution branch to the plain leader card — the whole
            # field disappears. That is the UX-P008 failure documented below,
            # reached from a new direction, so it gets the same answer the scale
            # guard gives: refuse the treatment outright.
            points = []
            rejected_incoherent = True

    # Mixed scales mean the labels were never one ladder — drop the threshold
    # treatment entirely rather than render self-contradicting bars.
    if not _ladder_is_scale_coherent(points):
        points = []
        rejected_incoherent = True

    # UX-P008 (#1526 residual). The market-name fallback below is for genuine
    # single-threshold questions ("Will Bitcoin close above $150,000?", 2
    # outcomes). Two conditions must keep it out:
    #
    #   1. A FIELD. With >= _FIELD_OUTCOME_FLOOR outcomes and not one of them
    #      carrying a rung, the outcomes ARE the answer and `outcome_distribution`
    #      is the designed card. A lone rung scraped out of the question hijacks
    #      it — the classifier tests threshold_heatmap BEFORE `count >= 4`, so a
    #      stray number in the title wins, the frontend then needs >= 2 rows to
    #      draw a heatmap, finds one, and falls through PAST the distribution
    #      branch to the plain leader card. The whole field disappears. Measured
    #      on production 2026-08-07: "2026-27 Stanley Cup® Finals Winner" (32
    #      teams) rendered as a lone "Florida Panthers 11%" because "2026-27"
    #      scored a rung at 27.
    #   2. AN ALREADY-REJECTED LADDER. The coherence guard above drops the
    #      threshold treatment *entirely*; falling back to the market name
    #      immediately resurrects the treatment it just refused. Same production
    #      market, both defects at once: the Counter-Strike "BIG vs Fluxo W7M"
    #      card had its 13 outcome rungs correctly binned as incoherent, then
    #      re-acquired a single rung at 7,000,000 from "W7M" in the title.
    if not points and not rejected_incoherent and (outcome_count or 0) < _FIELD_OUTCOME_FLOOR:
        # Same shape guard as the per-outcome path — otherwise an ordinal in
        # the QUESTION becomes a rung: "What will be the #2 global Netflix
        # movie this week?" produced a lone threshold at 2 for a card whose
        # outcomes are film titles.
        resolved = _outcome_threshold_value(name)
        if resolved is not None:
            value, unit, direction = resolved
            points.append(
                {
                    "source": "market_name",
                    "label": name,
                    "value": value,
                    "unit": unit,
                    "direction": direction,
                    "probability": None,
                }
            )

    if len(points) == 1 and (outcome_count or 0) >= 3:
        points[0]["needs_sibling_markets"] = True

    return points


def _has_recent_movement(outcomes: list[dict[str, Any]]) -> bool:
    """Is this market being written — the FORMAT question, not a dated claim.

    `movement_stored` first, and that ordering is the whole point (#4079 numeric
    half). Since the feed's served `movement` became a DATED subtraction — a
    number or nothing, never the per-write delta — a market whose day cannot be
    dated serves `movement: None` on every row while still trading normally.
    Reading that here would have quietly changed which cards get
    `probability_timeline`, turning a truth fix into a layout change nobody
    asked for. So the caller hands both: the dated number to print, and the
    stored delta to decide the shape with.

    The two older keys stay behind it for every caller that has only one —
    `test_date_bucket_ladder_1052` and the search/browse adapters build these
    rows themselves.
    """
    for outcome in outcomes:
        movement = outcome.get("movement_stored")
        if movement is None:
            movement = outcome.get("movement")
        if movement is None:
            movement = outcome.get("probability_change_24h")
        try:
            if movement is not None and abs(float(movement)) >= 0.02:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _distribution_outcomes(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for outcome in outcomes[:8]:
        label = _clean_text(outcome.get("name") or outcome.get("label"))
        if not label:
            continue
        rows.append(
            {
                "label": label,
                "probability": (
                    outcome.get("probability")
                    if outcome.get("probability") is not None
                    else outcome.get("current_probability")
                ),
                "movement": (
                    outcome.get("movement")
                    if outcome.get("movement") is not None
                    else outcome.get("probability_change_24h")
                ),
            }
        )
    return rows


def _comparison_theme(name: str, category: str | None) -> str | None:
    # This is broader than the public bundle allowlist. Some themes, especially
    # macro ranges and sports paths, are useful admin/archetype signals but too
    # broad to collapse publicly without stronger backend grouping evidence.
    category_lower = (category or "").lower()
    if _IPO_RE.search(name):
        return "ipo_valuation"
    if _ROTTEN_TOMATOES_RE.search(name):
        return "rotten_tomatoes_scores"
    if _COMMODITY_RE.search(name):
        return "commodity_ranges"
    if _MACRO_RANGE_RE.search(name) or category_lower == "economics":
        return "macro_ranges"
    if _WEATHER_RANGE_RE.search(name) or category_lower == "weather":
        return "weather_distributions"
    if _SPORTS_BRACKET_RE.search(name):
        return "sports_paths"
    return None


def classify_discover_card_archetype(
    *,
    name: str | None,
    category: str | None = None,
    outcomes: list[dict[str, Any]] | None = None,
    outcome_count: int | None = None,
    source_count: int | None = None,
    sources: list[str] | None = None,
    group_id: str | None = None,
    group_type: str | None = None,
    canonical_market_key: str | None = None,
    discover_llm: dict[str, Any] | None = None,
    resolved: bool = False,
    status: str | None = None,
    ladder_treatment_refused: bool = False,
    field_is_a_race: bool = True,
) -> dict[str, Any]:
    """Return frontend/admin rendering metadata for a Discover futures market.

    Source disagreement is deliberately classified as QA-only. It should help
    us find stale/thin/badly grouped markets, not become a public card format.
    """

    market_name = _clean_text(name)
    # #4151 — RESOLVED HERE, NOT AT THE CALLER, because the labels this module
    # emits are a THIRD copy of the outcome names and the route builds them
    # straight off the ORM row. `top_outcomes[].name` goes through the feed's
    # humanizers; `distribution_outcomes[].label` and `threshold_points[].label`
    # did not, so the live `Top AI model in September?` card served
    # `claude-fable-5.1-max` in all three.
    #
    # 🔴 AND THE COPY THE READER READS IS ONE OF THE TWO THE HUMANIZERS MISS.
    # Measured on production 2026-09-09: that card's `suggested_format` is
    # `threshold_heatmap` (reasons `['threshold_values']`), so the labels it
    # draws are `threshold_points[].label` — not the `top_outcomes` rows. A fix
    # applied only at the feed's humanizers would have left the visible card
    # entirely unchanged while every test that looked at `top_outcomes` passed.
    # One call here covers both label lists and both scoring sites.
    #
    # (Why that card is a threshold ladder at all is a separate defect: the
    # rungs are parsed out of MODEL VERSION NUMBERS — `claude-opus-4-6` scores a
    # rung at 4.0 via the `\d-\d` branch of `_THRESHOLD_SHAPED_RE`. Pre-existing,
    # unchanged by this commit, filed as #4226.)
    outcome_rows = display_outcome_names(outcomes or [], market_name)
    count = outcome_count if outcome_count is not None else len(outcome_rows)
    threshold_points = _threshold_points(
        name=market_name,
        outcomes=outcome_rows,
        outcome_count=count,
        # CERT-2451: a caller that filtered the ladder itself is the only one
        # who can still see whether it collapsed. `outcomes` here is what
        # SURVIVED that filter.
        ladder_already_refused=ladder_treatment_refused,
    )
    distribution_outcomes = _distribution_outcomes(outcome_rows)
    comparison_theme = _comparison_theme(market_name, category)

    suggested_format = "binary_probability"
    reasons: list[str] = []

    if resolved or status == "resolved":
        suggested_format = "resolution_recap"
        reasons.append("resolved_market")
    elif threshold_points and (
        len(threshold_points) >= 2
        or bool(comparison_theme)
        or bool(group_id)
        or bool(canonical_market_key)
    ):
        suggested_format = "threshold_heatmap"
        reasons.append("threshold_values")
    elif ladder_treatment_refused and len(distribution_outcomes) >= LADDER_MIN_DRAWN_RUNGS:
        # CERT-2456 — REFUSING THE TREATMENT IS NOT THE SAME AS SERVING THE FIELD.
        # Skipping the heatmap above only says what this card is NOT. On the
        # grader's specimen (`Above 10` .20 / `Above 20` .90 / `Above 30` .95)
        # nothing is dropped, so `count` is 3 — one short of the `>= 4` branch
        # below — and the cascade fell to `binary_probability`, whose hero prints
        # the leader ALONE. Same field hidden, different fallback hiding it.
        #
        # A refused ladder is precisely the market whose outcomes ARE the answer:
        # we are declining to say which rung is wrong, so the reader gets all of
        # them and can see the contradiction that we could not attribute. The
        # `>= 4` bar below is about when a field becomes more interesting than a
        # leader; it has nothing to say about a ladder we have just refused to
        # rank, so it does not get to gate it.
        suggested_format = "outcome_distribution"
        reasons.append("refused_ladder_field")
    elif count >= 4:
        suggested_format = "outcome_distribution"
        reasons.append("multi_outcome_distribution")
    elif _has_recent_movement(outcome_rows):
        suggested_format = "probability_timeline"
        reasons.append("recent_movement")

    llm_axes = []
    if discover_llm:
        raw_axes = discover_llm.get("comparison_axes") or []
        if isinstance(raw_axes, list):
            llm_axes = [str(axis) for axis in raw_axes if axis]

    bundle_candidate = bool(
        comparison_theme
        or group_type in {"threshold", "progression", "canonical"}
        or llm_axes
    )
    if bundle_candidate:
        reasons.append("bundle_candidate")

    qa_signals: list[str] = []
    if (source_count or 0) > 1 or (sources and len(set(sources)) > 1):
        qa_signals.append("multi_source_consistency_check")

    return {
        "suggested_format": suggested_format,
        "bundle_candidate": bundle_candidate,
        "comparison_theme": comparison_theme,
        "threshold_points": threshold_points[:12],
        # CERT-2456 — TRAVELS TO THE RENDERER, because the renderer is where the
        # refusal is finally honoured or lost. `FuturesCard.tsx` draws the
        # distribution only at four rows; a refused three-rung ladder classified
        # `outcome_distribution` and then dropped by that gate lands on the plain
        # leader hero, which is the same hidden field one component further on.
        # Gating the widened leaf on THIS rather than lowering the bar for every
        # `outcome_distribution` card keeps the change to the population the
        # BLOCK is about.
        "ladder_treatment_refused": ladder_treatment_refused,
        # #7844 half two — MAY THE RENDERER DRAW THESE ROWS AS A PODIUM?
        #
        # Travels for the same reason `ladder_treatment_refused` above travels:
        # the renderer is where the claim is finally made. Half one stopped the
        # CAPTION calling a coalition member the favourite; the board beneath it
        # says the same false thing in chrome — `1 2 3 4` is the grammar this
        # component uses for `2026-27 Stanley Cup® Finals Winner`, where exactly
        # one row can win, and "Field and N more outcomes" is an exhaustiveness
        # claim about a residual that does not exist on a board summing to 225%.
        #
        # Resolved by the route (`_card_field_is_a_race`) and not here, because
        # the two signals it reads are the venue's `mutually_exclusive` column
        # and the percents THE CARD PRINTS — and the printed percents are the
        # route's `top_outcomes_data`, already sliced and already scaled. Taking
        # it here off `distribution_outcomes` would answer for a different set of
        # rows than the one the copy was decided on, and the card would then
        # refuse a comparative while numbering its rows, or the reverse.
        #
        # FAIL TO TODAY'S RENDERING, the same convention as the helper: the
        # default is True and the client treats anything but an explicit `false`
        # as a race, so a caller that has not been taught to pass it keeps the
        # board it draws today. Because that default is silent, route adoption is
        # asserted structurally in the #7844 guard rather than left latent.
        "field_is_a_race": bool(field_is_a_race),
        "distribution_outcomes": distribution_outcomes,
        "remaining_outcome_count": max(0, count - len(distribution_outcomes)),
        "qa_signals": qa_signals,
        "public_source_disagreement": False,
        "reasons": reasons,
    }
