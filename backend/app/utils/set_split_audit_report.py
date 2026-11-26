"""Report-only public-set split-set audit (#13544 Ask 1).

Delegates directly to Builder E's unified detector
(:func:`app.utils.discover_fun_scout.detect_scout_split_set`, #13703) so public
Discover audit reports use the exact same rules as scout admission rather than
maintaining a second rule copy. If the detector cannot be imported, reports
``"detector unavailable"`` without falling back to a duplicate copy.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional, Sequence

try:
    from app.utils import discover_fun_scout
    from app.utils.discover_fun_scout import ScoutMarketRow
except ImportError:  # pragma: no cover - defensive when detector module unavailable
    discover_fun_scout = None  # type: ignore[assignment]
    ScoutMarketRow = Any  # type: ignore[misc,assignment]


def _load_scout_split_detector() -> Optional[Callable[..., Any]]:
    mod = discover_fun_scout
    if mod is None:
        try:
            from app.utils import discover_fun_scout as imported_mod
        except ImportError:
            return None
        mod = imported_mod
    detector = getattr(mod, "detect_scout_split_set", None)
    return detector if callable(detector) else None


def _coerce_scout_rows(
    members: Sequence[Any],
) -> list[Any]:
    fallback_dt = datetime.now(timezone.utc) + timedelta(days=90)
    rows: list[Any] = []
    for idx, m in enumerate(members, 1):
        if ScoutMarketRow is not Any and isinstance(m, ScoutMarketRow):
            rows.append(m)
            continue
        rows.append(
            ScoutMarketRow(
                market_id=int(m.get("market_id") or m.get("id") or idx),
                source=str(m.get("source") or "kalshi"),
                title=str(m.get("title") or m.get("name") or ""),
                status=str(m.get("status") or "open"),
                category=str(m.get("category") or "culture"),
                resolution_date=m.get("resolution_date") if isinstance(m.get("resolution_date"), datetime) else fallback_dt,
                volume=float(m.get("volume") or 0.0),
                volume_24h=float(m.get("volume_24h") or 0.0),
                market_metadata=m.get("market_metadata") if isinstance(m.get("market_metadata"), Mapping) else None,
            )
        )
    return rows


def audit_public_set_split_report_only(
    set_title: str,
    members: Sequence[Any],
) -> dict[str, Any]:
    """Audit one public set strictly in report-only mode via ``detect_scout_split_set``.

    Never rejects or mutates served sets. Reports ``"detector unavailable"`` if
    :func:`discover_fun_scout.detect_scout_split_set` cannot be imported.
    """
    builder_detector = _load_scout_split_detector()
    if builder_detector is None:
        return {
            "mode": "report_only",
            "detector": "unavailable",
            "is_split": False,
            "reason": "detector unavailable",
            "shared_feature": None,
        }

    rows = _coerce_scout_rows(members)
    finding = builder_detector(set_title, rows)
    reason = None if finding is None else str(getattr(finding, "reason", None) or finding)
    return {
        "mode": "report_only",
        "detector": "detect_scout_split_set",
        "is_split": finding is not None,
        "reason": reason,
        "shared_feature": getattr(finding, "shared_feature", None) if finding is not None else None,
    }


def audit_served_public_sets_report_only(
    served_items: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Run report-only split-set audit across grouped bundles in a served Discover list."""
    findings: list[dict[str, Any]] = []
    for item in served_items:
        if not isinstance(item, Mapping) or item.get("type") != "bundle":
            continue
        data = item.get("data")
        if not isinstance(data, Mapping):
            continue
        set_title = str(data.get("title") or data.get("name") or item.get("headline") or "").strip()
        set_id = str(data.get("id") or data.get("slug") or "")
        members: list[Mapping[str, Any]] = []
        raw_items = data.get("items")
        if isinstance(raw_items, Sequence) and not isinstance(raw_items, (str, bytes)):
            for idx, entry in enumerate(raw_items, 1):
                if not isinstance(entry, Mapping):
                    continue
                inner = entry.get("data") if isinstance(entry.get("data"), Mapping) else entry
                title = str(inner.get("name") or inner.get("title") or "").strip()
                if title:
                    members.append({"market_id": inner.get("id") or idx, "title": title})
        if not members and isinstance(data.get("roundup"), Mapping):
            rows = data["roundup"].get("rows")
            if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
                for idx, row in enumerate(rows, 1):
                    if not isinstance(row, Mapping):
                        continue
                    title = str(row.get("title") or row.get("label") or "").strip()
                    if title:
                        members.append({"market_id": idx, "title": title})
        if len(members) < 3:
            continue
        res = audit_public_set_split_report_only(set_title, members)
        if res["is_split"]:
            findings.append({"set_id": set_id, "title": set_title, **res})
    return findings
