"""Load Polymarket email-highlight ground truth rows for Discover audits."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Iterable

import httpx


DEFAULT_MIN_INTERESTINGNESS = 8
DEFAULT_LOOKBACK_DAYS = 21


def load_polymarket_email_ground_truth_from_csv_text(
    csv_text: str,
    *,
    min_interestingness: int = DEFAULT_MIN_INTERESTINGNESS,
    lookback_days: int | None = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    """Parse sheet-exported CSV rows into feed ground-truth item dicts.

    Expected headers come from the "Ranker Ground Truth (archival)" tab:
    Date, Source, Market Name, Category, ..., Email Subject, LLM Category,
    Hook, Interestingness, Timeliness, Shareability.
    """
    reader = csv.DictReader(StringIO(csv_text))
    if not reader.fieldnames:
        return []

    cutoff = _cutoff_date(lookback_days=lookback_days, now=now)
    seen: set[str] = set()
    items: list[dict[str, str]] = []

    for row in reader:
        name = (row.get("Market Name") or "").strip()
        source = (row.get("Source") or "").strip().lower()
        if not name or source != "polymarket":
            continue

        row_date = _parse_date(row.get("Date"))
        if cutoff and row_date and row_date < cutoff:
            continue

        interestingness = _parse_int(row.get("Interestingness"))
        if interestingness < min_interestingness:
            continue

        key = _dedupe_key(name)
        if not key or key in seen:
            continue
        seen.add(key)

        category = (
            (row.get("LLM Category") or "").strip()
            or (row.get("Category") or "").strip()
            or "?"
        )
        items.append(
            {
                "source": "polymarket_email",
                "category": category,
                "name": name,
                "probability": (row.get("Leader Probability") or "").strip(),
                "email_subject": (row.get("Email Subject") or "").strip(),
                "hook": (row.get("Hook") or "").strip(),
                "date": row_date.isoformat() if row_date else "",
                "interestingness": str(interestingness),
                "timeliness": (row.get("Timeliness") or "").strip(),
                "shareability": (row.get("Shareability") or "").strip(),
            }
        )

    return items


def load_polymarket_email_ground_truth_from_csv_path(
    path: str | Path,
    *,
    min_interestingness: int = DEFAULT_MIN_INTERESTINGNESS,
    lookback_days: int | None = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    csv_text = Path(path).expanduser().read_text()
    return load_polymarket_email_ground_truth_from_csv_text(
        csv_text,
        min_interestingness=min_interestingness,
        lookback_days=lookback_days,
        now=now,
    )


def load_polymarket_email_ground_truth_from_csv_url(
    url: str,
    *,
    min_interestingness: int = DEFAULT_MIN_INTERESTINGNESS,
    lookback_days: int | None = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
    timeout: float = 20.0,
) -> list[dict[str, str]]:
    response = httpx.get(url, follow_redirects=True, timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type and "<html" in response.text[:500].lower():
        raise RuntimeError(
            "Polymarket email ground-truth URL returned HTML. "
            "Publish/export the sheet tab as CSV or use CSV_PATH."
        )
    return load_polymarket_email_ground_truth_from_csv_text(
        response.text,
        min_interestingness=min_interestingness,
        lookback_days=lookback_days,
        now=now,
    )


def summarize_polymarket_email_ground_truth(
    diagnosed: Iterable[dict],
    email_items: Iterable[dict[str, str]],
) -> dict:
    """Return simple rank coverage for email-highlighted markets."""
    from app.utils.feed_quality_debug import _names_match  # local import avoids cycle

    feed_items = list(diagnosed)
    email_list = list(email_items)
    hits: list[dict] = []
    missing: list[dict] = []

    for item in email_list:
        name = item.get("name") or ""
        matched = next(
            (feed for feed in feed_items if _names_match(name, feed.get("name") or "")),
            None,
        )
        if matched:
            hits.append(
                {
                    "name": name,
                    "rank": matched.get("rank"),
                    "feed_name": matched.get("name"),
                    "category": item.get("category"),
                    "email_subject": item.get("email_subject"),
                }
            )
        else:
            missing.append(item)

    top20_hits = sum(1 for hit in hits if (hit.get("rank") or 999) <= 20)
    top50_hits = len(hits)
    return {
        "total": len(email_list),
        "top20_hits": top20_hits,
        "top50_hits": top50_hits,
        "missing": len(missing),
        "hit_rate_50": round(top50_hits / len(email_list), 4) if email_list else 0,
        "hits": sorted(hits, key=lambda item: item.get("rank") or 999),
        "missing_items": missing,
    }


def _cutoff_date(
    *,
    lookback_days: int | None,
    now: datetime | None,
) -> date | None:
    if not lookback_days or lookback_days <= 0:
        return None
    base = now or datetime.now(timezone.utc)
    return (base.date() - timedelta(days=lookback_days))


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_int(value: str | None) -> int:
    if not value:
        return 0
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return 0


def _dedupe_key(name: str) -> str:
    return " ".join(name.lower().split())
