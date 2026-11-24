"""Kit v1 (Ruling 366: B, 367: A, and Fable's 7 rules on #13551).

Cross-platform layout-generic card specification (`kit_version: 1`) aligned with
Builder C (`comment-7122170383`, `KitCardEnvelope366B.swift`) and Fable's 9:40 PM PT
`#13577` CHANGES review (`comment-7123162270`):
- Top-level `layout` (`stack | grid | calendar | axis`) + optional `variant` hint
- Layout-generic `body` built exclusively from the 8 marks (`picture`, `word`,
  `number`, `bar`, `tile`, `ring`, `dot`, `line`) so clients draw any future
  variant on a known layout without an app release
- Standard `source_mark`, tap `route`, `footnote`, and fail-closed validation.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.utils.discover_image_policy import _lookup_team_or_nation_logo

KIT_VERSION = 1

_DATA_DISCOVER_DIR = Path(__file__).resolve().parents[2] / "data" / "discover"
_VERIFIED_ART_PATH = _DATA_DISCOVER_DIR / "verified_discover_art.json"
GOLDEN_EXAMPLES_PATH = _DATA_DISCOVER_DIR / "kit_v1_golden_examples.json"

ALLOWED_LAYOUTS: frozenset[str] = frozenset({"stack", "grid", "calendar", "axis"})
ALLOWED_MARKS: frozenset[str] = frozenset(
    {"picture", "word", "number", "bar", "tile", "ring", "dot", "line"}
)

TEXT_ONLY_FORBIDDEN_VARIANTS: frozenset[str] = frozenset(
    {
        "word_list",
        "sorted_words",
        "text_list",
    }
)

CALENDAR_STRIP_RULE_NOTE = (
    "The percent in a day is the chance it arrives that day: "
    "one rung of the ladder minus the rung before it."
)

ALLOWED_KIT_IMAGE_HOSTS: frozenset[str] = frozenset(
    {
        "a.espncdn.com",
        "flagcdn.com",
        "image.tmdb.org",
        "thumb.wikimedia.org",
        "upload.wikimedia.org",
        "coverartarchive.org",
        "archive.org",
        "static.tvmaze.com",
        "api.bainluck.com",
    }
)


@lru_cache(maxsize=1)
def _verified_art_by_key() -> dict[str, dict[str, str]]:
    if not _VERIFIED_ART_PATH.exists():
        return {}
    raw = json.loads(_VERIFIED_ART_PATH.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    for entry in raw.get("entries", []):
        key = entry.get("entity_key")
        url = entry.get("url")
        if isinstance(key, str) and isinstance(url, str) and url.startswith("https://"):
            out[key] = {
                "url": url,
                "kind": str(entry.get("kind") or "topic"),
            }
    return out


def _art_entry(entity_key: str) -> tuple[str, str]:
    art = _verified_art_by_key().get(entity_key)
    if art:
        return art["url"], art["kind"]
    raise ValueError(f"Missing verified art entry for key={entity_key!r}")


def _team_logo(name: str, *, kind: str = "team") -> tuple[str, str]:
    url = _lookup_team_or_nation_logo(name)
    if not url:
        raise ValueError(f"Missing verified team/nation logo for {name!r}")
    return url, kind


def _is_valid_image_url(url: Any) -> bool:
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    host = (urlparse(url).hostname or "").lower()
    return host in ALLOWED_KIT_IMAGE_HOSTS


def _has_first_and_last_name(name: str) -> bool:
    tokens = [tok for tok in str(name or "").strip().split() if tok]
    return len(tokens) >= 2


def compute_one_in_n(pct: int) -> int:
    """Return whole-number `N` for '1 in N' beside `pct%` (Rule 7)."""
    return max(1, round(100 / max(1, int(pct))))


# ---------------------------------------------------------------------------
# Adaptive light/dark team colors (WCAG contrast guaranteed in both themes)
# ---------------------------------------------------------------------------

_LIGHT_SURFACE_HEX = "#ffffff"
_DARK_SURFACE_HEX = "#111827"
_MIN_LIGHT_CONTRAST = 3.0
_MIN_DARK_CONTRAST = 4.5


def _parse_hex_rgb(hex_color: str) -> tuple[int, int, int] | None:
    if not isinstance(hex_color, str) or len(hex_color) != 7 or not hex_color.startswith("#"):
        return None
    try:
        return (
            int(hex_color[1:3], 16),
            int(hex_color[3:5], 16),
            int(hex_color[5:7], 16),
        )
    except ValueError:
        return None


def _linear_channel(channel_8bit: int) -> float:
    c = channel_8bit / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    rgb = _parse_hex_rgb(hex_color)
    if rgb is None:
        return 0.0
    r, g, b = rgb
    return 0.2126 * _linear_channel(r) + 0.7152 * _linear_channel(g) + 0.0722 * _linear_channel(b)


def _contrast_ratio(hex_a: str, hex_b: str) -> float:
    l1 = _relative_luminance(hex_a)
    l2 = _relative_luminance(hex_b)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _blend_for_contrast(
    brand_hex: str,
    target_rgb: tuple[int, int, int],
    surface_hex: str,
    min_ratio: float,
) -> str:
    rgb = _parse_hex_rgb(brand_hex)
    if rgb is None:
        raise ValueError(f"Invalid #rrggbb hex color: {brand_hex!r}")
    if _contrast_ratio(brand_hex, surface_hex) >= min_ratio:
        return brand_hex.lower()
    tr, tg, tb = target_rgb
    r0, g0, b0 = rgb
    for step in range(1, 21):
        t = step / 20.0
        cand = f"#{round(r0 + (tr - r0) * t):02x}{round(g0 + (tg - g0) * t):02x}{round(b0 + (tb - b0) * t):02x}"
        if _contrast_ratio(cand, surface_hex) >= min_ratio:
            return cand
    return f"#{tr:02x}{tg:02x}{tb:02x}"


def _adaptive_team_color(brand_hex: str) -> dict[str, str]:
    """Return adaptive light/dark `#rrggbb` pair with verified contrast on both surfaces."""
    light_hex = _blend_for_contrast(brand_hex, (17, 24, 39), _LIGHT_SURFACE_HEX, _MIN_LIGHT_CONTRAST)
    dark_hex = _blend_for_contrast(brand_hex, (255, 255, 255), _DARK_SURFACE_HEX, _MIN_DARK_CONTRAST)
    return {"light": light_hex, "dark": dark_hex}


def _validate_adaptive_color(val: Any, label: str, errors: list[str]) -> None:
    if not isinstance(val, dict) or set(val.keys()) != {"light", "dark"}:
        errors.append(
            f"{label} must be an adaptive {{'light', 'dark'}} hex object, never a raw bare hex"
        )
        return
    light_hex = val.get("light")
    dark_hex = val.get("dark")
    if _parse_hex_rgb(light_hex or "") is None or _parse_hex_rgb(dark_hex or "") is None:
        errors.append(f"{label} must contain valid #rrggbb light and dark values")
        return
    if _contrast_ratio(light_hex, _LIGHT_SURFACE_HEX) < _MIN_LIGHT_CONTRAST:
        errors.append(f"{label}.light failed >= {_MIN_LIGHT_CONTRAST} contrast on white")
    if _contrast_ratio(dark_hex, _DARK_SURFACE_HEX) < _MIN_DARK_CONTRAST:
        errors.append(f"{label}.dark failed >= {_MIN_DARK_CONTRAST} contrast on dark card")


# ---------------------------------------------------------------------------
# Generic mark constructors (zero `"kind"` or `"type"` keys inside `"marks"`)
# ---------------------------------------------------------------------------


def _mark_picture(
    *,
    url: str,
    alt: str,
    subject_kind: str,
    size: str = "sm",
    contain: bool = True,
) -> dict[str, Any]:
    return {
        "mark": "picture",
        "url": url,
        "alt": alt,
        "subject_kind": subject_kind,
        "size": size,
        "contain": contain,
    }


def _mark_word(
    text: str,
    *,
    style: str = "row",
    tone: str = "primary",
    align: str = "left",
    width: str = "auto",
    bold: bool = False,
    secondary_text: str | None = None,
    deadline_iso: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "mark": "word",
        "text": text,
        "style": style,
        "tone": tone,
        "align": align,
        "width": width,
        "bold": bold,
    }
    if secondary_text is not None:
        out["secondary_text"] = secondary_text
    if deadline_iso is not None:
        out["deadline_iso"] = deadline_iso
    return out


def _mark_number(
    value: int,
    display: str,
    *,
    unit: str = "%",
    tone: str = "primary",
    prominence: str = "primary",
    align: str = "right",
    width: str = "sm",
    deadline_iso: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "mark": "number",
        "value": int(value),
        "display": display,
        "unit": unit,
        "tone": tone,
        "prominence": prominence,
        "align": align,
        "width": width,
    }
    if deadline_iso is not None:
        out["deadline_iso"] = deadline_iso
    return out


def _mark_bar_single(
    fill: float,
    *,
    width: str = "sm",
    fill_color: dict[str, str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "mark": "bar",
        "bar_style": "single",
        "fill": round(max(0.0, min(1.0, float(fill))), 4),
        "width": width,
    }
    if fill_color is not None:
        out["fill_color"] = fill_color
    return out


def _mark_bar_split(
    segments: list[dict[str, Any]],
    *,
    width: str = "flex",
) -> dict[str, Any]:
    return {
        "mark": "bar",
        "bar_style": "split",
        "segments": segments,
        "width": width,
    }


def _mark_tile(
    *,
    shade: float,
    center_label: str,
    top_label: str | None = None,
    bottom_label: str | None = None,
    muted: bool = False,
    highlight_role: str | None = None,
) -> dict[str, Any]:
    return {
        "mark": "tile",
        "shade": round(max(0.0, min(1.0, float(shade))), 4),
        "top_label": top_label,
        "center_label": center_label,
        "bottom_label": bottom_label,
        "muted": muted,
        "highlight_role": highlight_role,
    }


def _mark_dot(
    *,
    x: float,
    label: str,
    y_lane: int | None = None,
    color: dict[str, str] | None = None,
    in_band: bool = False,
    picture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "mark": "dot",
        "x": float(x),
        "y_lane": y_lane,
        "label": label,
        "color": color,
        "in_band": in_band,
        "picture": picture,
    }


def _make_kit_card(
    *,
    card_id: str,
    layout: str,
    variant: str | None,
    kicker: str,
    common_headline: str,
    stat_caption: str,
    body: dict[str, Any],
    source_count: int = 2,
    route_kind: str = "collection",
    route_id: int | None = None,
    route_slug: str | None = None,
    footnote: str | None = None,
    disclosure: str | None = None,
) -> dict[str, Any]:
    if layout not in ALLOWED_LAYOUTS:
        raise ValueError(f"Unknown Kit v1 layout={layout!r}")
    source_label = "1 source" if source_count == 1 else f"{source_count} sources"
    return {
        "kit_version": KIT_VERSION,
        "id": card_id,
        "layout": layout,
        "variant": variant,
        "kicker": kicker,
        "common_headline": common_headline,
        "stat_caption": stat_caption,
        "source_mark": {"label": source_label, "count": source_count},
        "route": {"kind": route_kind, "id": route_id, "slug": route_slug},
        "footnote": footnote,
        "disclosure": disclosure,
        "refusal_reason": None,
        "body": body,
    }


def build_fallback_today(reason: str) -> dict[str, Any]:
    """Return explicit refusal envelope keeping today's standard card (Rule 1)."""
    return {
        "kit_version": KIT_VERSION,
        "id": "fallback-today",
        "layout": None,
        "variant": None,
        "fallback_today": True,
        "refusal_reason": reason.strip() or "No visual shape fits safely",
    }


def build_calendar_strip_367a(
    *,
    card_id: str = "kit-spotify-wrapped-2026",
    kicker: str,
    common_headline: str,
    stat_caption: str,
    rungs: list[dict[str, Any]],
    ladder_footer: str,
    route_slug: str | None = "how-2026-gets-summed-up",
    variant: str | None = "calendar_strip",
) -> dict[str, Any]:
    """Build Ruling 367: A generic calendar body from one non-dipping cumulative ladder."""
    if len(rungs) < 2:
        raise ValueError("Calendar strip requires at least two cumulative rungs")

    cum_values = [int(r["cum_pct"]) for r in rungs]
    for prev_v, next_v in zip(cum_values, cum_values[1:]):
        if next_v < prev_v - 1:
            raise ValueError(
                f"Calendar strip refused: cumulative ladder dipped ({prev_v}% -> {next_v}%)"
            )

    raw_days: list[dict[str, Any]] = []
    for cur, nxt in zip(rungs, rungs[1:]):
        daily = max(0, int(nxt["cum_pct"]) - int(cur["cum_pct"]))
        raw_days.append(
            {
                "dow": str(cur["dow"]),
                "day_num": str(cur["day_num"]),
                "month_abbr": str(cur["month_abbr"]),
                "daily_pct": daily,
                "is_peak": False,
            }
        )

    peak_val = max((d["daily_pct"] for d in raw_days), default=0)
    if peak_val > 0:
        for d in raw_days:
            if d["daily_pct"] == peak_val:
                d["is_peak"] = True
                break

    max_pct = max(1, peak_val)
    day_entries: list[dict[str, Any]] = []
    for d in raw_days:
        daily = d["daily_pct"]
        day_entries.append(
            {
                "date_key": f"{d['month_abbr']}-{d['day_num']}",
                "daily_pct": daily,
                "marks": [
                    _mark_word(d["dow"], style="meta", tone="muted", align="center"),
                    _mark_tile(
                        shade=1.0 if d["is_peak"] else daily / max_pct,
                        center_label=d["day_num"],
                        bottom_label="·" if daily <= 0 else f"{daily}%",
                        muted=daily <= 0,
                        highlight_role="day_peak" if d["is_peak"] else None,
                    ),
                    _mark_word(d["month_abbr"], style="meta", tone="muted", align="center"),
                ],
            }
        )

    first, last = raw_days[0], raw_days[-1]
    span = f"{first['month_abbr']} {first['day_num']} – {last['month_abbr']} {last['day_num']}"
    return _make_kit_card(
        card_id=card_id,
        layout="calendar",
        variant=variant,
        kicker=kicker,
        common_headline=common_headline,
        stat_caption=stat_caption,
        source_count=2,
        route_kind="collection",
        route_slug=route_slug,
        footnote=ladder_footer,
        body={
            "header_marks": [
                _mark_word(span, style="meta", tone="muted", align="left"),
                _mark_word("Daily chance", style="kicker", tone="accent", align="right", bold=True),
            ],
            "days": day_entries,
            "footer_marks": [
                _mark_word(CALENDAR_STRIP_RULE_NOTE, style="sub", tone="secondary"),
            ],
        },
    )


# ---------------------------------------------------------------------------
# Fail-closed validator on layout-generic `body` + 8 marks
# ---------------------------------------------------------------------------


def _check_pct(val: Any, label: str, errors: list[str]) -> None:
    if not isinstance(val, int) or isinstance(val, bool) or not (0 <= val <= 100):
        errors.append(f"{label} must be an integer percent 0..100")


def _walk_and_validate_marks(
    node: Any,
    *,
    inside_marks: bool,
    errors: list[str],
    stats: dict[str, Any],
) -> None:
    if isinstance(node, list):
        for el in node:
            _walk_and_validate_marks(el, inside_marks=inside_marks, errors=errors, stats=stats)
        return
    if not isinstance(node, dict):
        return

    if inside_marks and ("kind" in node or "type" in node):
        errors.append("Compatibility: mark dict inside marks array must not carry 'kind' or 'type'")

    mark_val = node.get("mark")
    if mark_val is not None or inside_marks:
        if mark_val not in ALLOWED_MARKS:
            errors.append(f"Unsupported mark {mark_val!r}")
        elif mark_val == "picture":
            url = node.get("url")
            if not _is_valid_image_url(url):
                errors.append(f"Rule 1/4: picture mark missing verified HTTPS image_url ({url!r})")
            stats["picture_count"] += 1
            if node.get("subject_kind") == "person":
                stats["saw_person_picture"] = True
        elif mark_val == "number" and node.get("unit") == "%":
            _check_pct(node.get("value"), "number mark", errors)
        if node.get("deadline_iso") is not None:
            raw_dl = node.get("deadline_iso")
            if not isinstance(raw_dl, str) or not raw_dl.strip():
                errors.append(f"{mark_val or 'mark'}.deadline_iso must be a non-empty ISO datetime string")
            else:
                try:
                    datetime.fromisoformat(raw_dl.strip().replace("Z", "+00:00"))
                except ValueError:
                    errors.append(f"Invalid deadline_iso {raw_dl!r} on {mark_val or 'mark'}")
        if mark_val == "bar":
            if node.get("fill_color") is not None:
                _validate_adaptive_color(node.get("fill_color"), "bar.fill_color", errors)
            for idx_seg, seg in enumerate(node.get("segments") or []):
                if isinstance(seg, dict) and seg.get("color") is not None:
                    _validate_adaptive_color(seg.get("color"), f"bar.segments[{idx_seg}].color", errors)
        elif mark_val in {"dot", "line"}:
            if node.get("color") is not None:
                _validate_adaptive_color(node.get("color"), f"{mark_val}.color", errors)

    for k, child in node.items():
        if k == "route":
            continue
        _walk_and_validate_marks(
            child,
            inside_marks=(k in {"marks", "header_marks", "footer_marks", "leading", "summary_marks", "sub_marks"}),
            errors=errors,
            stats=stats,
        )


def _check_mark_container_rules(marks: list[Any], *, variant: str | None, errors: list[str]) -> None:
    """Validate Rule 7 (1 in N matches %) and person full names when both marks share a group."""
    pct_vals = [
        m.get("value")
        for m in marks
        if isinstance(m, dict) and m.get("mark") == "number" and m.get("unit") == "%"
    ]
    one_in_n_vals = [
        m
        for m in marks
        if isinstance(m, dict) and m.get("mark") == "number" and m.get("unit") == "one_in_n"
    ]
    if pct_vals and one_in_n_vals and isinstance(pct_vals[0], int):
        expected_n = compute_one_in_n(pct_vals[0])
        for oin in one_in_n_vals:
            if oin.get("value") != expected_n or oin.get("display") != f"1 in {expected_n}":
                errors.append(
                    f"Rule 7: one_in_n must equal 1 in {expected_n} beside {pct_vals[0]}%"
                )

    has_person_pic = any(
        isinstance(m, dict) and m.get("mark") == "picture" and m.get("subject_kind") == "person"
        for m in marks
    )
    if has_person_pic:
        row_words = [
            m.get("text", "")
            for m in marks
            if isinstance(m, dict) and m.get("mark") == "word" and m.get("style") == "row"
        ]
        for nm in row_words:
            if not _has_first_and_last_name(nm):
                errors.append(f"Rule 4: person row {nm!r} requires first & last name")


def _validate_stack_body(body: dict[str, Any], *, variant: str | None, errors: list[str]) -> None:
    items = body.get("items")
    if not isinstance(items, list) or not items:
        errors.append("stack body requires non-empty items[]")
        return

    sport_key = str(body.get("single_sport_key") or "").strip()
    for idx, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append(f"stack item {idx} must be an object")
            continue
        item_marks = item.get("marks")
        if not isinstance(item_marks, list) or not item_marks:
            errors.append(f"stack item {idx} requires non-empty marks[]")
            continue
        _check_mark_container_rules(item_marks, variant=variant, errors=errors)
        if sport_key:
            row_sport = str(item.get("sport_key") or sport_key).strip()
            if row_sport != sport_key:
                errors.append(
                    f"Rule 6: mixed sport on slate (expected {sport_key!r}, got {row_sport!r})"
                )
        if variant in {"casting_sheet", "photo_wall"}:
            if not any(isinstance(m, dict) and m.get("mark") == "picture" for m in item_marks):
                errors.append(f"Rule 1: {variant} row {idx} refused without verified picture")


def _validate_grid_body(body: dict[str, Any], *, variant: str | None, errors: list[str]) -> None:
    cols = body.get("columns")
    rows = body.get("rows")
    if not isinstance(cols, list) or not cols or not isinstance(rows, list) or not rows:
        errors.append("grid body requires non-empty columns[] and rows[]")
        return
    if any(isinstance(c, dict) and c.get("refused_sum") is not None for c in cols):
        errors.append("grid body must strip refused columns server-side before serving")
    if len(cols) < 2:
        errors.append("grid body requires at least 2 valid columns (fallback if < 2)")

    row_layout = body.get("row_layout")
    if row_layout not in {"matrix", "stacked_cells"}:
        errors.append("grid body row_layout must be 'matrix' or 'stacked_cells'")

    for idx, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"grid row {idx} must be an object")
            continue
        leading = row.get("leading") or []
        if not isinstance(leading, list) or not leading:
            errors.append(f"grid row {idx} requires non-empty leading[] marks")
            continue
        _check_mark_container_rules(leading, variant=variant, errors=errors)
        rank_words = [
            m for m in leading if isinstance(m, dict) and m.get("mark") == "word" and m.get("style") == "rank"
        ]
        if rank_words and str(rank_words[0].get("text")) != str(idx):
            errors.append(f"Rule 4: grid row {idx} must carry sequential rank={idx}")
        if variant in {"casting_sheet", "photo_wall"}:
            if not any(isinstance(m, dict) and m.get("mark") == "picture" for m in leading):
                errors.append(f"Rule 1: {variant} row {idx} refused without verified picture")

        cells = row.get("cells") or []
        for c_idx, cell in enumerate(cells):
            if not isinstance(cell, dict) or not isinstance(cell.get("marks"), list) or not cell["marks"]:
                errors.append(f"grid row {idx} cell {c_idx + 1} requires marks[]")


def _validate_calendar_body(body: dict[str, Any], errors: list[str]) -> None:
    days = body.get("days")
    if not isinstance(days, list) or len(days) < 2:
        errors.append("calendar body requires at least 2 day entries")
        return
    footer = body.get("footer_marks") or []
    footer_texts = [
        str(m.get("text") or "").strip()
        for m in footer
        if isinstance(m, dict) and m.get("mark") == "word"
    ]
    if not any(footer_texts):
        errors.append("Ruling 367: A requires plain explanation in calendar footer_marks")
    for idx, day in enumerate(days, 1):
        day_marks = day.get("marks") if isinstance(day, dict) else None
        if not isinstance(day_marks, list) or not day_marks:
            errors.append(f"calendar day {idx} requires non-empty marks[]")
            continue
        tiles = [m for m in day_marks if isinstance(m, dict) and m.get("mark") == "tile"]
        if not tiles:
            errors.append(f"calendar day {idx} requires a tile mark")


def _validate_axis_body(body: dict[str, Any], errors: list[str]) -> None:
    scale = body.get("scale")
    if not isinstance(scale, dict):
        errors.append("Rule 3: axis body requires scale")
        return
    units = body.get("scale_units")
    if isinstance(units, list) and len({str(u) for u in units}) > 1:
        errors.append("Rule 3: shared scale refuses mixed units")
    if scale.get("scale_kind") not in {"percent", "numeric", "time"}:
        errors.append("Rule 3: axis scale requires valid scale_kind")
    if not str(scale.get("unit") or "").strip() or not (scale.get("ticks") or []):
        errors.append("Rule 3: axis scale requires unit and explicit ticks")
    s_min, s_max = scale.get("min"), scale.get("max")
    if not isinstance(s_min, (int, float)) or not isinstance(s_max, (int, float)) or s_min >= s_max:
        errors.append("Rule 3: axis scale requires numeric min < max")

    has_marks = bool(body.get("marks")) or bool(body.get("series"))
    if not has_marks:
        errors.append("axis body requires non-empty marks[] or series[]")


def validate_kit_v1_card(spec: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a Kit v1 card against Ruling 366: B, 367: A, and Fable's 7 rules.

    `variant` is treated strictly as an optional hint — arbitrary future variant
    names (or None) MUST pass validation whenever `layout`, `body`, and `marks`
    are valid.
    """
    errors: list[str] = []
    if not isinstance(spec, dict):
        return False, ["spec must be a dict"]

    if spec.get("kit_version") != KIT_VERSION:
        errors.append("kit_version must equal 1")

    if not str(spec.get("id") or "").strip():
        errors.append("id must be non-empty")

    if spec.get("refusal_reason") or spec.get("fallback_today") is True:
        return False, [str(spec.get("refusal_reason") or "Card refused back to standard")]

    variant = spec.get("variant")
    if variant in TEXT_ONLY_FORBIDDEN_VARIANTS:
        errors.append("Rule 1: text-only fallback variants are forbidden in Kit v1")
        return False, errors
    if variant is not None and (not isinstance(variant, str) or not variant.strip()):
        errors.append("variant must be null or a non-empty string")

    layout = spec.get("layout")
    if layout not in ALLOWED_LAYOUTS:
        errors.append(f"Unsupported kit layout {layout!r}")
        return False, errors

    if not str(spec.get("common_headline") or "").strip():
        errors.append("Rule 2: common_headline must be non-empty")
    if not str(spec.get("stat_caption") or "").strip():
        errors.append("Rule 2: stat_caption must be non-empty")

    source_mark = spec.get("source_mark")
    if not isinstance(source_mark, dict) or not str(source_mark.get("label") or "").strip():
        errors.append("source_mark with non-empty label is required")

    route = spec.get("route")
    if not isinstance(route, dict) or route.get("kind") not in {"collection", "event", "market", "team"}:
        errors.append("route with valid kind (collection|event|market|team) is required")

    body = spec.get("body")
    if not isinstance(body, dict) or not body:
        errors.append("layout-generic body object is required")
        return False, errors

    stats: dict[str, Any] = {"picture_count": 0, "saw_person_picture": False}
    _walk_and_validate_marks(body, inside_marks=False, errors=errors, stats=stats)

    if layout == "stack":
        _validate_stack_body(body, variant=variant, errors=errors)
    elif layout == "grid":
        _validate_grid_body(body, variant=variant, errors=errors)
    elif layout == "calendar":
        _validate_calendar_body(body, errors)
    elif layout == "axis":
        _validate_axis_body(body, errors)

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# All 8 worked examples emitting layout-generic `body` (real snapshot numbers)
# ---------------------------------------------------------------------------


def build_kit_v1_worked_examples() -> dict[str, Any]:
    """Return the 8 worked Kit v1 examples + Rule/367-A refusal examples."""
    cards: list[dict[str, Any]] = []

    # 1. grid / scoreboard_grid — College Football National Championship (rd-57)
    cfb_rows: list[dict[str, Any]] = []
    for idx, (team, nat_p, sec_p) in enumerate(
        [("Georgia", 34, 68), ("Texas", 11, 26), ("Alabama", 10, 3), ("Tennessee", 4, 3)],
        1,
    ):
        url, subj_kind = _team_logo(team)
        cfb_rows.append(
            {
                "id": f"cfb-{idx}-{team.lower()}",
                "leading": [
                    _mark_word(str(idx), style="rank", tone="muted", width="xs"),
                    _mark_picture(url=url, alt=team, subject_kind=subj_kind, size="sm", contain=True),
                    _mark_word(team, style="row", tone="primary", bold=True, width="flex"),
                ],
                "cells": [
                    {
                        "column_key": "181",
                        "marks": [_mark_tile(shade=nat_p / 100.0, center_label=f"{nat_p}%")],
                    },
                    {
                        "column_key": "233",
                        "marks": [_mark_tile(shade=sec_p / 100.0, center_label=f"{sec_p}%")],
                    },
                ],
            }
        )
    cards.append(
        _make_kit_card(
            card_id="kit-cfb-national-title",
            layout="grid",
            variant="scoreboard_grid",
            kicker="SPORTS · COLLEGE FOOTBALL",
            common_headline="College Football Playoff and SEC Championship leaders",
            stat_caption="Georgia leads the college football national championship at 34%, with SEC contenders across the same board",
            source_count=2,
            route_slug="college-football-national-championship",
            footnote="Shaded cells show served chances across both title races.",
            disclosure="2 other markets in this set are not drawn here.",
            body={
                "leading_label": "Contender",
                "show_column_headers": True,
                "row_layout": "matrix",
                "columns": [
                    {"key": "181", "label": "National Title"},
                    {"key": "233", "label": "SEC Title"},
                ],
                "rows": cfb_rows,
            },
        )
    )

    # 2. grid / dated_tiles — Middle East deadlines (rd-13)
    us_url, us_kind = _team_logo("United States", kind="flag")
    ir_url, ir_kind = _team_logo("Iran", kind="flag")
    me_cols = [
        {"key": "2026-11-30", "label": "Nov 30 '26"},
        {"key": "2026-12-31", "label": "Dec 31 '26"},
        {"key": "2027-06-30", "label": "Jun 30 '27"},
    ]
    me_specs = [
        ("ceasefire", "US x Iran Effective Ceasefire begins", us_url, us_kind, [66, 81, None]),
        ("iran-leadership", "Iran leadership change", ir_url, ir_kind, [1, 7, 24]),
    ]
    me_rows = []
    for row_id, title, img_url, subj_kind, pcts in me_specs:
        me_rows.append(
            {
                "id": row_id,
                "leading": [
                    _mark_picture(url=img_url, alt=title, subject_kind=subj_kind, size="xs", contain=True),
                    _mark_word(title, style="row", tone="primary", bold=True, width="flex"),
                ],
                "cells": [
                    {
                        "column_key": col["key"],
                        "marks": [
                            _mark_tile(
                                shade=0.0 if val is None else val / 100.0,
                                top_label=f"by {col['label']}",
                                center_label="—" if val is None else f"{val}%",
                                muted=(val is None),
                            )
                        ],
                    }
                    for col, val in zip(me_cols, pcts)
                ],
            }
        )
    cards.append(
        _make_kit_card(
            card_id="kit-middle-east-deadlines",
            layout="grid",
            variant="dated_tiles",
            kicker="GEOPOLITICS · MIDDLE EAST",
            common_headline="Middle East ceasefire and leadership timelines",
            stat_caption="US x Iran effective ceasefire reaches 81% by December 31, while Iran leadership change climbs to 24% by June 30",
            source_count=2,
            route_slug="middle-east-deadlines",
            disclosure="4 other markets in this set are not drawn here.",
            body={
                "show_column_headers": False,
                "row_layout": "stacked_cells",
                "columns": me_cols,
                "rows": me_rows,
            },
        )
    )

    # 3. stack / countdown — By December 31 (rd-22)
    ai_url, ai_kind = _art_entry("batch5-ai-model-leaderboard-2026")
    dc_url, dc_kind = _art_entry("nersc-data-center")
    fr_url, fr_kind = _team_logo("France", kind="flag")
    pop_url, pop_kind = _art_entry("batch6-pop-culture-oddities")
    ph_url, ph_kind = _art_entry("pete-hegseth")
    em_url, em_kind = _art_entry("elon-musk")
    countdown_specs = [
        ("opus", "Next Claude Opus (5.6+) released?", 85, ai_url, ai_kind),
        ("arena", "Will any AI model reach a Chatbot Arena score of at least 1550?", 42, dc_url, dc_kind),
        ("france", "Will France pass a national budget?", 42, fr_url, fr_kind),
        ("banksy", "Will Banksy create a new mural or street artwork?", 31, pop_url, pop_kind),
        ("hegseth", "Pete Hegseth out as Secretary of Defense?", 11, ph_url, ph_kind),
        ("x-ban", "X banned in any European country?", 8, em_url, em_kind),
    ]
    cards.append(
        _make_kit_card(
            card_id="kit-by-december-31",
            layout="stack",
            variant="countdown",
            kicker="SAME DEADLINE",
            common_headline="By December 31",
            stat_caption="Next Claude Opus (5.6+) release leads December 31 deadlines at 85%",
            source_count=2,
            route_slug="by-december-31",
            body={
                "header_layout": "banner",
                "header_marks": [
                    _mark_number(38, "38", unit="days", tone="accent", prominence="hero", align="left", width="auto"),
                    _mark_word(
                        "days left",
                        secondary_text="all of these end on Dec 31",
                        style="hero_label",
                        tone="primary",
                        bold=True,
                        width="flex",
                    ),
                ],
                "items": [
                    {
                        "id": row_id,
                        "marks": [
                            _mark_picture(
                                url=img_url,
                                alt=label,
                                subject_kind=subj_kind,
                                size="sm",
                                contain=(subj_kind != "person"),
                            ),
                            _mark_word(label, style="row", tone="primary", width="flex"),
                            _mark_bar_single(p / 100.0, width="sm"),
                            _mark_number(p, f"{p}%", unit="%", tone="primary", prominence="primary", align="right", width="sm"),
                        ],
                    }
                    for row_id, label, p, img_url, subj_kind in countdown_specs
                ],
            },
        )
    )

    # 4. stack / road_ahead — Boston Celtics: next 3 games (rd-37)
    bos_url, _ = _team_logo("Boston Celtics")
    wsh_url, _ = _team_logo("Washington Wizards")
    atl_url, _ = _team_logo("Atlanta Hawks")
    sa_url, _ = _team_logo("San Antonio Spurs")
    celtics_games = [
        ("g1-wsh", "Washington Wizards", "WSH", wsh_url, "at", "Tue Nov 24", "5:00 PM PT", 79),
        ("g2-atl", "Atlanta Hawks", "ATL", atl_url, "vs", "Fri Nov 27", "5:00 PM PT", 62),
        ("g3-sa", "San Antonio Spurs", "SA", sa_url, "at", "Sun Nov 29", "1:00 PM PT", 40),
    ]
    cards.append(
        _make_kit_card(
            card_id="kit-boston-celtics-road",
            layout="stack",
            variant="road_ahead",
            kicker="NBA · NEXT 3 GAMES",
            common_headline="Boston Celtics: next 3 games",
            stat_caption="Boston is 79% at Washington on Tuesday, then hosts Atlanta at 62% and visits San Antonio at 40%",
            source_count=4,
            route_kind="team",
            route_slug="boston-celtics",
            body={
                "header_layout": "banner",
                "header_marks": [
                    _mark_picture(url=bos_url, alt="Boston Celtics", subject_kind="team", size="sm", contain=True),
                    _mark_word("Boston Celtics", style="row", tone="primary", bold=True, width="flex"),
                ],
                "items": [
                    {
                        "id": gid,
                        "marks": [
                            _mark_word(day, secondary_text=clock, style="meta", tone="secondary", width="sm"),
                            _mark_picture(url=opp_url, alt=opp_name, subject_kind="team", size="sm", contain=True),
                            _mark_word(f"{loc} {opp_abbr}", style="row", tone="primary", bold=True, width="flex"),
                            _mark_bar_single(team_p / 100.0, width="md", fill_color=_adaptive_team_color("#008348")),
                            _mark_number(team_p, f"{team_p}%", unit="%", tone="primary", prominence="primary", align="right", width="sm"),
                        ],
                    }
                    for gid, opp_name, opp_abbr, opp_url, loc, day, clock, team_p in celtics_games
                ],
            },
        )
    )

    # 5. axis / bubble_line — 2026-27 NHL Playoffs (rd-25)
    nhl_raw = [
        ("Edmonton Oilers", "EDM", 98, "#041e42"),
        ("Minnesota Wild", "MIN", 98, "#154734"),
        ("Carolina Hurricanes", "CAR", 97, "#cc0000"),
        ("Vegas Golden Knights", "VGK", 94, "#b4975a"),
        ("Tampa Bay Lightning", "TB", 90, "#002868"),
        ("Colorado Avalanche", "COL", 88, "#6f263d"),
        ("Dallas Stars", "DAL", 85, "#006847"),
        ("New Jersey Devils", "NJ", 83, "#ce1126"),
        ("Montreal Canadiens", "MTL", 81, "#af1e2d"),
        ("Florida Panthers", "FLA", 76, "#c8102e"),
        ("Ottawa Senators", "OTT", 73, "#c52032"),
        ("Utah Mammoth", "UTAH", 73, "#69b3e7"),
        ("Boston Bruins", "BOS", 69, "#ffb81c"),
        ("Washington Capitals", "WSH", 54, "#c8102e"),
        ("New York Rangers", "NYR", 47, "#0038a8"),
        ("Nashville Predators", "NSH", 46, "#ffb81c"),
        ("New York Islanders", "NYI", 43, "#00539b"),
        ("Anaheim Ducks", "ANA", 38, "#fc4c02"),
        ("St. Louis Blues", "STL", 38, "#002f87"),
        ("Los Angeles Kings", "LA", 34, "#111111"),
        ("Winnipeg Jets", "WPG", 34, "#041e42"),
        ("Seattle Kraken", "SEA", 33, "#001628"),
        ("Buffalo Sabres", "BUF", 32, "#002654"),
        ("San Jose Sharks", "SJ", 24, "#006d75"),
        ("Philadelphia Flyers", "PHI", 18, "#f74902"),
        ("Columbus Blue Jackets", "CBJ", 14, "#002654"),
        ("Calgary Flames", "CGY", 11, "#c8102e"),
        ("Pittsburgh Penguins", "PIT", 11, "#000000"),
        ("Toronto Maple Leafs", "TOR", 8, "#00205b"),
        ("Chicago Blackhawks", "CHI", 8, "#cf0a2c"),
        ("Detroit Red Wings", "DET", 8, "#ce1126"),
        ("Vancouver Canucks", "VAN", 6, "#00205b"),
    ]
    nhl_dots: list[dict[str, Any]] = []
    in_doubt_rows: list[tuple[str, int]] = []
    lanes_x: list[float] = []
    low_count = 0
    high_count = 0
    for team_name, abbr, p_val, color in sorted(nhl_raw, key=lambda x: (x[2], x[1])):
        in_doubt = 25 < p_val < 75
        if p_val <= 25:
            low_count += 1
        if p_val >= 75:
            high_count += 1
        lane: int | None = None
        pic: dict[str, Any] | None = None
        logo_url, _ = _team_logo(team_name)
        if in_doubt:
            for idx_lane, last_p in enumerate(lanes_x):
                if p_val - last_p >= 6:
                    lane = idx_lane
                    lanes_x[idx_lane] = float(p_val)
                    break
            if lane is None:
                lane = len(lanes_x)
                lanes_x.append(float(p_val))
            in_doubt_rows.append((abbr, p_val))
            pic = _mark_picture(url=logo_url, alt=abbr, subject_kind="team", size="xs", contain=True)
        nhl_dots.append(
            _mark_dot(
                x=float(p_val),
                y_lane=lane,
                label=f"{team_name}: {p_val}%",
                color=_adaptive_team_color(color),
                in_band=in_doubt,
                picture=pic,
            )
        )
    doubt_summary = " · ".join(
        f"{abbr} {p_val}%" for abbr, p_val in sorted(in_doubt_rows, key=lambda item: (-item[1], item[0]))
    )
    cards.append(
        _make_kit_card(
            card_id="kit-nhl-playoffs-bubble",
            layout="axis",
            variant="bubble_line",
            kicker="HOCKEY · NHL PLAYOFFS",
            common_headline="2026–27 NHL Playoffs picture",
            stat_caption="Edmonton leads at 98%, while Washington (54%) and the Rangers (47%) sit inside the playoff bubble",
            source_count=2,
            route_slug="nhl-playoffs-2027",
            body={
                "scale": {
                    "scale_kind": "percent",
                    "unit": "%",
                    "min": 0,
                    "max": 100,
                    "ticks": [
                        {"x": 0, "label": "0%"},
                        {"x": 25, "label": "25%"},
                        {"x": 50, "label": "50%"},
                        {"x": 75, "label": "75%"},
                        {"x": 100, "label": "100%"},
                    ],
                },
                "highlight_band": {"lo": 25, "hi": 75, "label": "in doubt"},
                "marks": nhl_dots,
                "summary_marks": [
                    _mark_word(f"{low_count} at 25% or less", style="sub", tone="secondary", align="left"),
                    _mark_word(f"{high_count} at 75% or more", style="sub", tone="secondary", align="right"),
                ],
                "footer_marks": [
                    _mark_word(doubt_summary, style="pill", tone="secondary"),
                ],
            },
        )
    )

    # 6. stack / one_in_n — Elon Musk's wildest side quests (rd-01)
    space_url, space_kind = _art_entry("batch3-elon-musk-side-quests")
    sofi_url, sofi_kind = _art_entry("sofi-stadium-super-bowl")
    side_quests = [
        ("mars", "Will Elon Musk visit Mars in his lifetime?", 12, space_url, space_kind),
        ("ryanair", "Will Elon purchase Ryanair?", 5, em_url, em_kind),
        ("superman", "Next Superman film: Will Elon Musk be cast?", 5, em_url, em_kind),
        ("tesla-ceo", "Elon Musk out as Tesla CEO before 2027?", 3, em_url, em_kind),
        ("optimus", "Tesla Optimus released this year?", 2, dc_url, dc_kind),
        ("sports-team", "Will Elon Musk buy a major sports team before 2027?", 1, sofi_url, sofi_kind),
    ]
    cards.append(
        _make_kit_card(
            card_id="kit-elon-side-quests",
            layout="stack",
            variant="one_in_n",
            kicker="ODD · SIDE QUESTS",
            common_headline="Elon Musk's wildest side quests",
            stat_caption="Visiting Mars in his lifetime is the likeliest long shot at 12% (1 in 8), with buying Ryanair at 5% (1 in 20)",
            source_count=2,
            route_slug="elon-musk-wildest-side-quests",
            body={
                "header_layout": "none",
                "header_marks": [],
                "items": [
                    {
                        "id": row_id,
                        "marks": [
                            _mark_picture(
                                url=img_url,
                                alt=label,
                                subject_kind=subj_kind,
                                size="sm",
                                contain=(subj_kind != "person"),
                            ),
                            _mark_word(label, style="row", tone="primary", width="flex"),
                            _mark_number(
                                compute_one_in_n(p),
                                f"1 in {compute_one_in_n(p)}",
                                unit="one_in_n",
                                tone="accent",
                                prominence="primary",
                                align="right",
                                width="auto",
                            ),
                            _mark_number(
                                p,
                                f"{p}%",
                                unit="%",
                                tone="muted",
                                prominence="secondary",
                                align="right",
                                width="auto",
                            ),
                        ],
                    }
                    for row_id, label, p, img_url, subj_kind in side_quests
                ],
            },
        )
    )

    # 7. stack / single_sport_slate — NBA Slate (rd-02, Rule 6 strictly NBA)
    nba_items = []
    for away_name, away_abbr, away_c, away_p, home_name, home_abbr, home_c, home_p, day, clock, status, score in [
        ("Memphis Grizzlies", "MEM", "#5d76a9", 49, "Charlotte Hornets", "CHA", "#008ca8", 51, "Mon Nov 23", "4:00 PM PT", "live", [28, 32]),
        ("Portland Trail Blazers", "PTB", "#e03a3e", 47, "Philadelphia 76ers", "PHI", "#1d428a", 53, "Mon Nov 23", "4:00 PM PT", "live", [27, 28]),
        ("Oklahoma City Thunder", "OKC", "#007ac1", 63, "Indiana Pacers", "IND", "#0c2340", 37, "Mon Nov 23", "4:30 PM PT", "scheduled", [None, None]),
        ("Milwaukee Bucks", "MIL", "#00471b", 21, "Toronto Raptors", "TOR", "#d91244", 79, "Mon Nov 23", "4:30 PM PT", "scheduled", [None, None]),
        ("Brooklyn Nets", "BKN", "#000000", 19, "Minnesota Timberwolves", "MIN", "#266092", 81, "Mon Nov 23", "4:30 PM PT", "scheduled", [None, None]),
        ("Phoenix Suns", "PHX", "#29127a", 58, "New Orleans Pelicans", "NOP", "#0a2240", 42, "Mon Nov 23", "5:00 PM PT", "scheduled", [None, None]),
        ("Detroit Pistons", "DET", "#1d428a", 54, "Orlando Magic", "ORL", "#0150b5", 46, "Tue Nov 24", "4:00 PM PT", "scheduled", [None, None]),
    ]:
        a_logo, _ = _team_logo(away_name)
        h_logo, _ = _team_logo(home_name)
        status_text = (
            f"Live · {score[0]}–{score[1]}"
            if status == "live" and score[0] is not None and score[1] is not None
            else f"{day} · {clock}"
        )
        nba_items.append(
            {
                "id": f"nba-{away_abbr.lower()}-{home_abbr.lower()}",
                "sport_key": "basketball_nba",
                "marks": [
                    _mark_picture(url=a_logo, alt=away_abbr, subject_kind="team", size="sm", contain=True),
                    _mark_word(away_abbr, style="row", tone="primary", bold=True, width="xs"),
                    _mark_number(away_p, f"{away_p}%", unit="%", tone="primary", prominence="primary", align="left", width="xs"),
                    _mark_bar_split(
                        [
                            {"fill": away_p / 100.0, "color": _adaptive_team_color(away_c), "label": away_abbr},
                            {"fill": home_p / 100.0, "color": _adaptive_team_color(home_c), "label": home_abbr},
                        ],
                        width="flex",
                    ),
                    _mark_number(home_p, f"{home_p}%", unit="%", tone="primary", prominence="primary", align="right", width="xs"),
                    _mark_word(home_abbr, style="row", tone="primary", bold=True, align="right", width="xs"),
                    _mark_picture(url=h_logo, alt=home_abbr, subject_kind="team", size="sm", contain=True),
                ],
                "sub_marks": [
                    _mark_word(status_text, style="meta", tone="muted", align="center"),
                ],
            }
        )
    cards.append(
        _make_kit_card(
            card_id="kit-nba-slate",
            layout="stack",
            variant="single_sport_slate",
            kicker="NBA · THIS SLATE",
            common_headline="Tonight's NBA Slate",
            stat_caption="Pistons at Magic (54%–46%) headlines seven NBA matchups",
            source_count=4,
            route_slug="nba-slate",
            disclosure="6 other markets in this set are not drawn here.",
            body={
                "single_sport_key": "basketball_nba",
                "header_layout": "split",
                "header_marks": [
                    _mark_word("NBA", style="kicker", tone="muted", bold=True),
                    _mark_word(f"{len(nba_items)} GAMES", style="kicker", tone="muted", bold=True, align="right"),
                ],
                "items": nba_items,
            },
        )
    )

    # 8. calendar / calendar_strip (Ruling 367: A) — Spotify Wrapped 2026
    wrapped_rungs = [
        {"dow": "Fri", "day_num": "27", "month_abbr": "Nov", "cum_pct": 3},
        {"dow": "Sat", "day_num": "28", "month_abbr": "Nov", "cum_pct": 5},
        {"dow": "Sun", "day_num": "29", "month_abbr": "Nov", "cum_pct": 6},
        {"dow": "Mon", "day_num": "30", "month_abbr": "Nov", "cum_pct": 12},
        {"dow": "Tue", "day_num": "1", "month_abbr": "Dec", "cum_pct": 12},
        {"dow": "Wed", "day_num": "2", "month_abbr": "Dec", "cum_pct": 18},
        {"dow": "Thu", "day_num": "3", "month_abbr": "Dec", "cum_pct": 85},
        {"dow": "Fri", "day_num": "4", "month_abbr": "Dec", "cum_pct": 90},
        {"dow": "Sat", "day_num": "5", "month_abbr": "Dec", "cum_pct": 90},
    ]
    cards.append(
        build_calendar_strip_367a(
            card_id="kit-spotify-wrapped-2026",
            kicker="CULTURE · 2026",
            common_headline="When will Spotify release 2026 Wrapped?",
            stat_caption="Spotify Wrapped is most likely to arrive on Wednesday, December 2 (67%)",
            rungs=wrapped_rungs,
            ladder_footer="Served ladder: 12% before Dec 1 · 18% before Dec 2 · 85% before Dec 3 · 90% before Dec 4",
        )
    )

    for card in cards:
        ok, errs = validate_kit_v1_card(card)
        if not ok:
            raise AssertionError(f"Worked example {card.get('id')} failed validation: {errs}")

    refusals = [
        {
            "title": "Rule 1 — No text-only fallback (casting_sheet / word_list refused without pictures)",
            "spec": build_fallback_today(
                "Members carry no verified artwork; keep today's standard card instead of text-only fallback."
            ),
        },
        {
            "title": "Rule 6 — Mixed-sport slate refused (The closest games tonight)",
            "spec": build_fallback_today(
                "Slate mixes soccer, basketball, hockey, and cricket (>1 sport_key); keep today's card."
            ),
        },
        {
            "title": "One-winner columns > 115 refused (2028 Presidential Race: 123% & 127%)",
            "spec": build_fallback_today(
                "Mutually exclusive columns sum above 115 as served (123%, 127%) and <2 valid columns remain; keep today's card."
            ),
        },
    ]

    return {
        "kit_version": KIT_VERSION,
        "count": len(cards),
        "items": cards,
        "refusals": refusals,
    }


def write_golden_examples_json(dest: Path = GOLDEN_EXAMPLES_PATH) -> Path:
    payload = build_kit_v1_worked_examples()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return dest
