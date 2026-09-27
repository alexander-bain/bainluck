"""One inflation release, one block — the identity two venues' ladders share (#8018).

The /economics "Inflation releases" card stacked two ladders for ONE release —
Polymarket "Argentina Monthly Inflation - September" over Kalshi "Argentina
inflation rate MoM for September" — and they disagreed about the answer. The
generic same-question predicate cannot pair them (Jaccard 0.50: ``monthly``
against ``rate mom``), and loosening it would re-open every control it is bound
by. The US September print is the same shape three times over: Kalshi's headline
series ("CPI in September"), Kalshi's EconStats series ("CPI month-over-month in
Sep 2026?") and Polymarket ("September Inflation US - Monthly") each price
headline MoM, and the same for headline YoY, core MoM and core YoY — twelve
ladders for four questions, measured on production 2026-09-27.

A release's identity is not a string, it is four facts: WHERE (the country),
WHEN (the reference month, plus the year when a title states one), WHICH MEASURE
(month-over-month or year-over-year) and WHICH SERIES (headline or core). This
module reads those four facts off a title and returns ``None`` whenever it
cannot read all of them — and, deliberately, whenever the title carries ANY word
it does not understand. "Core goods CPI MoM", "US gasoline CPI", "CPI MoM Combo
· Headline & Core", "Will UK inflation be above Euro Area inflation" and "South
Africa inflation rate" all carry such a word, so none of them is keyed and none
of them can be folded. A ``None`` costs a duplicate block at worst (the
behaviour before this module); a wrong key DELETES a question the reader wanted.
That asymmetry is why the vocabulary is closed.

Two titles with one identity are still only one release when they resolve
within :data:`SAME_RELEASE_WINDOW` of each other: a title with no year
("Argentina Monthly Inflation - September") is compared to one with a year by
the release date the venues publish, not by guessing which September it means.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from typing import NamedTuple, TypeVar

from app.utils.cross_source_matching import _PLACE_TOKENS, same_question_tokens

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_MOM_TOKENS = frozenset({"mom", "monthly", "month"})
_YOY_TOKENS = frozenset({"yoy", "annual", "year"})

#: Words that carry no identity of their own; ``rate`` is "inflation rate".
#: ``over`` is NOT here: the tokenizer aliases ``above``/``exceeds`` onto it, so
#: "Will core CPI be above headline CPI in September (MoM)?" — a two-outcome
#: comparison — would read as core MoM. ``over`` is understood only as the joint
#: of "month-over-month" / "year-over-year", i.e. beside ``month`` or ``year``.
_FILLER = frozenset({"cpi", "inflation", "rate", "headline", "core"})

#: The venues publish one release's markets a few hours apart (Kalshi 12:25Z
#: and 12:29Z, Polymarket 03:59Z the next day for the US September print;
#: 15:59Z and 18:59Z for Argentina's). A month apart is a different release.
SAME_RELEASE_WINDOW = timedelta(days=3)


class ReleaseIdentity(NamedTuple):
    place: str
    month: int
    year: int | None
    measure: str  # "mom" | "yoy"
    series: str  # "headline" | "core"


def inflation_release_identity(name: str | None) -> ReleaseIdentity | None:
    """The release a ladder title prices, or ``None`` when it cannot be read.

    ``None`` whenever the title names no month, no measure, more than one
    place, more than one month or year, BOTH measures, both "core" and
    "headline", or any word outside the closed vocabulary (months, years,
    places, measure words, filler).

    Two readings are conventions, stated so they can be checked:

    * **No place + "CPI" is the US.** Every venue title of that shape on
      production is a US BLS series; a foreign print always names its country.
    * **"CPI in <month>" with no measure word is month-over-month** — Kalshi's
      headline and core series (``KXCPI`` / ``KXCPICORE``). Only when the title
      says "CPI" and neither "inflation" nor "rate": "US headline CPI inflation
      in December 2030" and "Brazil inflation rate in September" state no
      measure and are NOT keyed. Measured 2026-09-27: "CPI in September" peaks
      at 0.5–0.6% and "CPI core in September" at 0.1–0.2%, exactly where the
      explicitly-MoM EconStats and Polymarket ladders for the same print peak.
    """
    tokens = same_question_tokens(name)
    if not tokens:
        return None

    places = tokens & _PLACE_TOKENS
    months = {_MONTHS[t] for t in tokens if t in _MONTHS}
    years = {int(t) for t in tokens if len(t) == 4 and t.isdigit() and t.startswith("20")}
    measures = set()
    if tokens & _MOM_TOKENS:
        measures.add("mom")
    if tokens & _YOY_TOKENS:
        measures.add("yoy")

    understood = (
        places
        | {t for t in tokens if t in _MONTHS}
        | {str(y) for y in years}
        | (tokens & (_MOM_TOKENS | _YOY_TOKENS))
        | (tokens & _FILLER)
        | ({"over"} if tokens & {"month", "year"} else set())
    )
    if tokens - understood:
        return None
    if len(months) != 1 or len(years) > 1 or len(places) > 1:
        return None
    if "cpi" not in tokens and "inflation" not in tokens:
        return None
    if {"core", "headline"} <= tokens:
        return None

    if not places:
        if "cpi" not in tokens:
            return None
        place = "us"
    else:
        (place,) = places

    if not measures:
        if "cpi" in tokens and not tokens & {"inflation", "rate"}:
            measures = {"mom"}
        else:
            return None
    if len(measures) != 1:
        return None

    return ReleaseIdentity(
        place=place,
        month=next(iter(months)),
        year=next(iter(years)) if years else None,
        measure=next(iter(measures)),
        series="core" if "core" in tokens else "headline",
    )


def _same_release(
    a: ReleaseIdentity, a_resolves: datetime | None,
    b: ReleaseIdentity, b_resolves: datetime | None,
) -> bool:
    if a._replace(year=None) != b._replace(year=None):
        return False
    if a.year is not None and b.year is not None and a.year != b.year:
        return False
    # Without both release dates a year-less title cannot be placed; refuse.
    if a_resolves is None or b_resolves is None:
        return a.year is not None and a.year == b.year
    return abs(_aware(a_resolves) - _aware(b_resolves)) <= SAME_RELEASE_WINDOW


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


T = TypeVar("T")


def fold_same_release(
    items: Iterable[T],
    *,
    name: Callable[[T], str | None],
    volume: Callable[[T], float | None],
    resolves: Callable[[T], datetime | None],
    key: Callable[[T], int],
) -> list[T]:
    """Keep one item per inflation release, in the input order.

    The survivor of each release is the most-traded ladder (then the lowest
    ``key``, so the choice never depends on input order): the venue where the
    most money priced the question is the one number to show. Items whose title
    has no readable identity always survive.
    """
    items = list(items)
    identities = [inflation_release_identity(name(item)) for item in items]
    rank = sorted(
        range(len(items)),
        key=lambda i: (-(volume(items[i]) or 0), key(items[i])),
    )
    kept: list[int] = []
    dropped: set[int] = set()
    for i in rank:
        ident = identities[i]
        if ident is None:
            continue
        if any(
            _same_release(identities[k], resolves(items[k]), ident, resolves(items[i]))
            for k in kept
        ):
            dropped.add(i)
        else:
            kept.append(i)
    return [item for i, item in enumerate(items) if i not in dropped]
