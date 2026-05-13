"""Load Polymarket email-highlight ground truth rows for Discover audits."""

from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime, timedelta, timezone
import os
from io import StringIO
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import httpx


DEFAULT_MIN_INTERESTINGNESS = 8
DEFAULT_LOOKBACK_DAYS = 21
DEFAULT_STALE_AFTER_DAYS = 2
DEFAULT_SHEET_NAME = "Audit Export"
SHEETS_READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"


def load_polymarket_email_ground_truth_report_from_env(
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Load optional email ground truth from the configured CSV path or URL."""
    csv_path = os.getenv("POLYMARKET_EMAIL_GROUND_TRUTH_CSV_PATH")
    csv_url = (
        os.getenv("POLYMARKET_EMAIL_GROUND_TRUTH_CSV_URL")
        or os.getenv("POLYMARKET_EMAIL_GROUND_TRUTH_URL")
    )
    spreadsheet_id = os.getenv("POLYMARKET_EMAIL_GROUND_TRUTH_SPREADSHEET_ID")
    sheet_name = os.getenv("POLYMARKET_EMAIL_GROUND_TRUTH_SHEET_NAME", DEFAULT_SHEET_NAME)
    min_interestingness = int(
        os.getenv(
            "POLYMARKET_EMAIL_GROUND_TRUTH_MIN_INTERESTINGNESS",
            str(DEFAULT_MIN_INTERESTINGNESS),
        )
    )
    lookback_days_raw = os.getenv(
        "POLYMARKET_EMAIL_GROUND_TRUTH_LOOKBACK_DAYS",
        str(DEFAULT_LOOKBACK_DAYS),
    )
    lookback_days = int(lookback_days_raw) if lookback_days_raw else None

    if csv_path:
        try:
            return load_polymarket_email_ground_truth_report_from_csv_path(
                csv_path,
                min_interestingness=min_interestingness,
                lookback_days=lookback_days,
                now=now,
            )
        except Exception as exc:
            return _error_report("csv_path", str(exc), source_path=csv_path)
    if spreadsheet_id:
        try:
            return load_polymarket_email_ground_truth_report_from_google_sheet(
                spreadsheet_id,
                sheet_name=sheet_name,
                min_interestingness=min_interestingness,
                lookback_days=lookback_days,
                now=now,
            )
        except Exception as exc:
            return _error_report(
                "google_sheet",
                str(exc),
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
            )
    if csv_url:
        try:
            return load_polymarket_email_ground_truth_report_from_csv_url(
                csv_url,
                min_interestingness=min_interestingness,
                lookback_days=lookback_days,
                now=now,
            )
        except Exception as exc:
            parsed_spreadsheet_id = _extract_spreadsheet_id(csv_url)
            if parsed_spreadsheet_id and _google_service_account_json():
                try:
                    report = load_polymarket_email_ground_truth_report_from_google_sheet(
                        parsed_spreadsheet_id,
                        sheet_name=sheet_name,
                        min_interestingness=min_interestingness,
                        lookback_days=lookback_days,
                        now=now,
                    )
                    report["metadata"]["source_url"] = csv_url
                    report["metadata"]["fallback_from_csv_url_error"] = str(exc)
                    return report
                except Exception as sheet_exc:
                    return _error_report(
                        "csv_url",
                        f"{exc}; Google Sheets API fallback failed: {sheet_exc}",
                        source_url=csv_url,
                        spreadsheet_id=parsed_spreadsheet_id,
                        sheet_name=sheet_name,
                    )
            return _error_report("csv_url", str(exc), source_url=csv_url)
    return {
        "items": [],
        "metadata": {
            "configured": False,
            "source": None,
            "source_url": None,
            "source_path": None,
            "raw_row_count": 0,
            "loaded_count": 0,
            "latest_date": None,
            "stale": None,
            "stale_after_days": DEFAULT_STALE_AFTER_DAYS,
            "min_interestingness": DEFAULT_MIN_INTERESTINGNESS,
            "lookback_days": DEFAULT_LOOKBACK_DAYS,
            "error": None,
        },
    }


def load_polymarket_email_ground_truth_from_csv_text(
    csv_text: str,
    *,
    min_interestingness: int = DEFAULT_MIN_INTERESTINGNESS,
    lookback_days: int | None = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    return load_polymarket_email_ground_truth_report_from_csv_text(
        csv_text,
        min_interestingness=min_interestingness,
        lookback_days=lookback_days,
        now=now,
    )["items"]


def load_polymarket_email_ground_truth_report_from_csv_text(
    csv_text: str,
    *,
    min_interestingness: int = DEFAULT_MIN_INTERESTINGNESS,
    lookback_days: int | None = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Parse sheet-exported CSV rows into feed ground-truth item dicts.

    Accepts either the archival sheet headers ("Market Name") or the stable
    audit export headers ("market_name").
    """
    reader = csv.DictReader(StringIO(csv_text))
    if not reader.fieldnames:
        return {
            "items": [],
            "metadata": _build_metadata([], [], now=now, error="missing_headers"),
        }

    cutoff = _cutoff_date(lookback_days=lookback_days, now=now)
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    source_rows: list[dict[str, str]] = []
    loaded_dates: list[date] = []

    for row in reader:
        row = _normalize_row_keys(row)
        name = _field(row, "market_name", "Market Name").strip()
        source = _field(row, "source", "Source").strip().lower()
        if not name or source != "polymarket":
            continue

        source_rows.append(row)
        row_date = _parse_date(_field(row, "date", "Date"))
        if row_date:
            loaded_dates.append(row_date)
        if cutoff and row_date and row_date < cutoff:
            continue

        interestingness = _parse_int(_field(row, "interestingness", "Interestingness"))
        if interestingness < min_interestingness:
            continue

        key = _dedupe_key(name)
        if not key or key in seen:
            continue
        seen.add(key)

        category = (
            _field(row, "llm_category", "LLM Category").strip()
            or _field(row, "category", "Category").strip()
            or "?"
        )
        items.append(
            {
                "source": "polymarket_email",
                "category": category,
                "name": name,
                "probability": _field(
                    row,
                    "leader_probability",
                    "Leader Probability",
                ).strip(),
                "email_subject": _field(row, "email_subject", "Email Subject").strip(),
                "hook": _field(row, "hook", "Hook").strip(),
                "date": row_date.isoformat() if row_date else "",
                "interestingness": str(interestingness),
                "timeliness": _field(row, "timeliness", "Timeliness").strip(),
                "shareability": _field(row, "shareability", "Shareability").strip(),
            }
        )

    return {
        "items": items,
        "metadata": _build_metadata(
            source_rows,
            loaded_dates,
            loaded_count=len(items),
            min_interestingness=min_interestingness,
            lookback_days=lookback_days,
            now=now,
        ),
    }


def load_polymarket_email_ground_truth_from_csv_path(
    path: str | Path,
    *,
    min_interestingness: int = DEFAULT_MIN_INTERESTINGNESS,
    lookback_days: int | None = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    return load_polymarket_email_ground_truth_report_from_csv_path(
        path,
        min_interestingness=min_interestingness,
        lookback_days=lookback_days,
        now=now,
    )["items"]


def load_polymarket_email_ground_truth_report_from_csv_path(
    path: str | Path,
    *,
    min_interestingness: int = DEFAULT_MIN_INTERESTINGNESS,
    lookback_days: int | None = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    csv_text = Path(path).expanduser().read_text()
    report = load_polymarket_email_ground_truth_report_from_csv_text(
        csv_text,
        min_interestingness=min_interestingness,
        lookback_days=lookback_days,
        now=now,
    )
    report["metadata"].update(
        {
            "configured": True,
            "source": "csv_path",
            "source_path": str(path),
            "source_url": None,
        }
    )
    return report


def load_polymarket_email_ground_truth_from_csv_url(
    url: str,
    *,
    min_interestingness: int = DEFAULT_MIN_INTERESTINGNESS,
    lookback_days: int | None = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
    timeout: float = 20.0,
) -> list[dict[str, str]]:
    return load_polymarket_email_ground_truth_report_from_csv_url(
        url,
        min_interestingness=min_interestingness,
        lookback_days=lookback_days,
        now=now,
        timeout=timeout,
    )["items"]


def load_polymarket_email_ground_truth_report_from_csv_url(
    url: str,
    *,
    min_interestingness: int = DEFAULT_MIN_INTERESTINGNESS,
    lookback_days: int | None = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    response = httpx.get(url, follow_redirects=True, timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type and "<html" in response.text[:500].lower():
        raise RuntimeError(
            "Polymarket email ground-truth URL returned HTML. "
            "Publish/export the sheet tab as CSV or use CSV_PATH."
        )
    report = load_polymarket_email_ground_truth_report_from_csv_text(
        response.text,
        min_interestingness=min_interestingness,
        lookback_days=lookback_days,
        now=now,
    )
    report["metadata"].update(
        {
            "configured": True,
            "source": "csv_url",
            "source_url": url,
            "source_path": None,
        }
    )
    return report


def load_polymarket_email_ground_truth_report_from_google_sheet(
    spreadsheet_id: str,
    *,
    sheet_name: str = DEFAULT_SHEET_NAME,
    min_interestingness: int = DEFAULT_MIN_INTERESTINGNESS,
    lookback_days: int | None = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Load ground truth from a private Google Sheet via service-account auth."""
    values = _read_google_sheet_values(spreadsheet_id, sheet_name)
    csv_text = _sheet_values_to_csv(values)
    report = load_polymarket_email_ground_truth_report_from_csv_text(
        csv_text,
        min_interestingness=min_interestingness,
        lookback_days=lookback_days,
        now=now,
    )
    report["metadata"].update(
        {
            "configured": True,
            "source": "google_sheet",
            "source_path": None,
            "source_url": None,
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": sheet_name,
        }
    )
    return report


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
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
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


def _read_google_sheet_values(spreadsheet_id: str, sheet_name: str) -> list[list[Any]]:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    service_account_json = _google_service_account_json()
    if not service_account_json:
        raise RuntimeError(
            "Google Sheet ground truth requires FIREBASE_SERVICE_ACCOUNT_JSON "
            "or GOOGLE_APPLICATION_CREDENTIALS_JSON."
        )

    credentials = service_account.Credentials.from_service_account_info(
        json.loads(service_account_json),
        scopes=[SHEETS_READONLY_SCOPE],
    )
    credentials.refresh(Request())
    range_name = quote(_quote_sheet_name(sheet_name), safe="")
    response = httpx.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_name}",
        headers={"Authorization": f"Bearer {credentials.token}"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("values", [])


def _sheet_values_to_csv(values: list[list[Any]]) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerows(values)
    return output.getvalue()


def _google_service_account_json() -> str | None:
    return os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") or os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS_JSON"
    )


def _quote_sheet_name(sheet_name: str) -> str:
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'"


def _extract_spreadsheet_id(url: str) -> str | None:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


def _normalize_row_keys(row: dict[str, str]) -> dict[str, str]:
    normalized = dict(row)
    for key, value in row.items():
        normalized[_normalize_header(key)] = value
    return normalized


def _field(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None:
            return str(value)
        value = row.get(_normalize_header(name))
        if value is not None:
            return str(value)
    return ""


def _normalize_header(header: str | None) -> str:
    return "".join(ch for ch in str(header or "").lower() if ch.isalnum())


def _build_metadata(
    source_rows: list[dict[str, str]],
    row_dates: list[date],
    *,
    loaded_count: int = 0,
    min_interestingness: int = DEFAULT_MIN_INTERESTINGNESS,
    lookback_days: int | None = DEFAULT_LOOKBACK_DAYS,
    now: datetime | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    base = now or datetime.now(timezone.utc)
    latest_date = max(row_dates) if row_dates else None
    stale_after = base.date() - timedelta(days=DEFAULT_STALE_AFTER_DAYS)
    stale = latest_date < stale_after if latest_date else None
    return {
        "configured": True,
        "source": None,
        "source_url": None,
        "source_path": None,
        "raw_row_count": len(source_rows),
        "loaded_count": loaded_count,
        "latest_date": latest_date.isoformat() if latest_date else None,
        "stale": stale,
        "stale_after_days": DEFAULT_STALE_AFTER_DAYS,
        "min_interestingness": min_interestingness,
        "lookback_days": lookback_days,
        "error": error,
    }


def _error_report(
    source: str,
    error: str,
    *,
    source_url: str | None = None,
    source_path: str | None = None,
    spreadsheet_id: str | None = None,
    sheet_name: str | None = None,
) -> dict[str, Any]:
    return {
        "items": [],
        "metadata": {
            "configured": True,
            "source": source,
            "source_url": source_url,
            "source_path": source_path,
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": sheet_name,
            "raw_row_count": 0,
            "loaded_count": 0,
            "latest_date": None,
            "stale": None,
            "stale_after_days": DEFAULT_STALE_AFTER_DAYS,
            "min_interestingness": DEFAULT_MIN_INTERESTINGNESS,
            "lookback_days": DEFAULT_LOOKBACK_DAYS,
            "error": error,
        },
    }
