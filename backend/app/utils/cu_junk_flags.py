"""Content Understanding junk flags that follow from the outcome labels."""

import re
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from app.utils.market_staleness import whole_name_date


_COMPARISON = (
    r"(?:(?:at least|at most|more than|less than|greater than|fewer than|"
    r"above|below|over|under)\b|[<>]=?|[≤≥↑↓])"
)
_WORD = r"[^\W\d_]+"
_WORDS = rf"{_WORD}(?:[ -]{_WORD})*"
_UNIT = rf"(?:%|°[cfk]|{_WORDS})"
_VALUE = (
    r"(?P<currency>[$€£]?)\s*"
    r"(?P<number>[-+−]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)"
    r"(?P<scale>(?:bn|[kmbt])(?![a-z]))?"
)
_PREFIX_THRESHOLD = re.compile(
    rf"(?:(?P<subject>{_WORDS}) )?{_COMPARISON}\s*{_VALUE}\s*(?P<unit>{_UNIT})?"
)
_SUFFIX_THRESHOLD = re.compile(
    rf"(?:(?P<subject>{_WORDS}) )?{_VALUE}"
    rf"(?:\s*\+\s*(?P<plus_unit>{_UNIT})?"
    rf"|\s*(?P<unit>{_UNIT})? or (?:more|higher|above|fewer|less|lower|below))"
)
_SCALE = {
    "": 1,
    "k": 1_000,
    "m": 1_000_000,
    "b": 1_000_000_000,
    "bn": 1_000_000_000,
    "t": 1_000_000_000_000,
}
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _threshold(label: str) -> tuple[tuple[str, str, str], Decimal] | None:
    match = _PREFIX_THRESHOLD.fullmatch(label) or _SUFFIX_THRESHOLD.fullmatch(label)
    if match is None:
        return None
    parts = match.groupdict()
    unit = parts["unit"] or parts.get("plus_unit") or ""
    if unit in {"percent", "per cent"}:
        unit = "%"
    measure = (parts["subject"] or "", parts["currency"], unit.removesuffix("s"))
    number = Decimal(parts["number"].replace(",", "").replace("−", "-"))
    return measure, number * _SCALE[parts["scale"] or ""]


def _date_label(label: str) -> tuple[int, int, int | None] | None:
    if _ISO_DATE.fullmatch(label):
        try:
            day = date.fromisoformat(label)
        except ValueError:
            return None
        return day.month, day.day, day.year
    return whole_name_date(label)


def _option_flag(outcome_names: Iterable[str | None]) -> str | None:
    labels = [" ".join((name or "").casefold().split()) for name in outcome_names]
    if len(labels) < 2:
        return None
    first_threshold = _threshold(labels[0])
    if first_threshold is not None:
        measure, first_value = first_threshold
        values = {first_value}
        for label in labels[1:]:
            threshold = _threshold(label)
            if threshold is None or threshold[0] != measure:
                return None
            values.add(threshold[1])
        return "ladder" if len(values) > 1 else None

    first_date = _date_label(labels[0])
    if first_date is None:
        return None
    dates = {first_date}
    for label in labels[1:]:
        parsed = _date_label(label)
        if parsed is None:
            return None
        dates.add(parsed)
    return "dated_bucket" if len(dates) > 1 else None


def cu_junk_flags(outcome_names: Iterable[str | None], model_flags: object) -> list[str]:
    """Add the flag proved by the labels while retaining the model's flags."""
    flags = (
        [flag for flag in model_flags if isinstance(flag, str)]
        if isinstance(model_flags, list)
        else []
    )
    flag = _option_flag(outcome_names)
    if flag is not None and all(flag != item.strip().casefold() for item in flags):
        flags.append(flag)
    return flags
