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

from datetime import datetime
import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.utils.discover_image_policy import _lookup_team_or_nation_logo

__all__ = ["ALLOWED_LAYOUTS", "ALLOWED_MARKS", "validate_kit_v1_card"]

KIT_VERSION = 1

_DATA_DISCOVER_DIR = Path(__file__).resolve().parents[2] / "data" / "discover"
_VERIFIED_ART_PATH = _DATA_DISCOVER_DIR / "verified_discover_art.json"
GOLDEN_EXAMPLES_PATH = _DATA_DISCOVER_DIR / "kit_v1_golden_examples.json"

ALLOWED_LAYOUTS: frozenset[str] = frozenset({"stack", "grid", "calendar", "axis"})
ALLOWED_MARKS: frozenset[str] = frozenset(
    {"picture", "word", "number", "bar", "tile", "ring", "dot", "line"}
)
ALLOWED_BAR_STYLES: frozenset[str] = frozenset({"single", "split", "range"})
ALLOWED_ROW_LAYOUTS: frozenset[str] = frozenset({"matrix", "stacked_cells"})
ALLOWED_SCALE_KINDS: frozenset[str] = frozenset({"percent", "numeric", "time"})
ALLOWED_NUMBER_UNITS: frozenset[str] = frozenset({"%", "days", "one_in_n"})

# Canonical cross-platform contract agreed on #13551 (Fable, Atlas, Builder C):
# - Cosmetic fields: unknown/invalid values render the client default styling token; never trigger fallback.
# - Meaning-carrying fields: unknown/invalid values fail closed to today's standard card.
COSMETIC_KIT_FIELDS: tuple[str, ...] = (
    "variant",
    "word.style",
    "word.tone",
    "word.align",
    "word.width",
    "picture.size",
    "picture.contain",
    "picture.subject_kind",
    "number.tone",
    "number.prominence",
    "number.align",
    "number.width",
    "bar.width",
    "tile.highlight_role",
    "ring.tone",
    "body.header_layout",
)

MEANING_CARRYING_KIT_FIELDS: tuple[str, ...] = (
    "kit_version",
    "layout",
    "mark",
    "bar.bar_style",
    "scale.scale_kind",
    "body.row_layout",
    "number.unit",
    "adaptive_color",
    "picture.url",
    "body",
    "refusal_reason",
    "fallback_today",
)

KIT_V1_FIELD_BEHAVIOR_TABLE: dict[str, dict[str, Any]] = {
    "cosmetic": {
        "fields": COSMETIC_KIT_FIELDS,
        "unknown_value_behavior": "render_default",
    },
    "meaning_carrying": {
        "fields": MEANING_CARRYING_KIT_FIELDS,
        "unknown_value_behavior": "fail_closed_fallback_today",
    },
    "unknown_top_level_keys": {
        "fields": ("<any unknown top-level key>",),
        "unknown_value_behavior": "ignore_and_render_known",
    },
}

TEXT_ONLY_FORBIDDEN_VARIANTS: frozenset[str] = frozenset(
    {
        "word_list",
        "sorted_words",
        "text_list",
    }
)

CALENDAR_STRIP_RULE_NOTE = (
    "Each day shows the chance it is out on that day; "
    "3% falls before Nov 27 and Dec 4 or later holds 10%."
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


def _initials_for_label(label: str) -> str:
    """Return 1-2 uppercase alphanumeric initials for a row without verified art (387: A)."""
    cleaned = str(label or "").strip().rstrip("?").strip()
    if " · " in cleaned:
        cleaned = cleaned.rsplit(" · ", 1)[1].strip()
    elif ":" in cleaned:
        _prefix, right = cleaned.rsplit(":", 1)
        if right.strip():
            cleaned = right.strip()
    raw_words = [w for w in cleaned.split() if re.search(r"[A-Za-z0-9]", w)]
    non_year_words = [w for w in raw_words if not re.fullmatch(r"\d{4}", re.sub(r"[^A-Za-z0-9]", "", w))]
    chosen_words = non_year_words or raw_words
    if not chosen_words:
        return "?"
    if len(chosen_words) == 1:
        chars = re.sub(r"[^A-Za-z0-9]", "", chosen_words[0])
        return (chars[:2] or "?").upper()
    c0 = re.sub(r"[^A-Za-z0-9]", "", chosen_words[0])
    c1 = re.sub(r"[^A-Za-z0-9]", "", chosen_words[1])
    first = c0[:1]
    second = c1[:1] if c1 else c0[1:2]
    return f"{first}{second}".upper() or "?"


def _mark_picture(
    *,
    url: str | None = None,
    alt: str,
    subject_kind: str,
    size: str = "sm",
    contain: bool = True,
    initials: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "mark": "picture",
        "url": url,
        "alt": alt,
        "subject_kind": subject_kind,
        "size": size,
        "contain": contain,
    }
    if url is None:
        out["initials"] = (initials or _initials_for_label(alt)).strip() or "?"
    elif initials is not None:
        out["initials"] = initials
    return out


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
    badge_text: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "mark": "dot",
        "x": float(x),
        "y_lane": y_lane,
        "label": label,
        "color": color,
        "in_band": in_band,
        "picture": picture,
    }
    if badge_text is not None:
        out["badge_text"] = badge_text
    return out


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
    tail_label: str | None = None,
) -> dict[str, Any]:
    """Build Ruling 367: A generic calendar body from one non-dipping cumulative ladder."""
    if len(rungs) < 2:
        raise ValueError("Calendar strip requires at least two cumulative curves")

    cum_values = [int(r["cum_pct"]) for r in rungs]
    for prev_v, next_v in zip(cum_values, cum_values[1:]):
        if next_v < prev_v - 1:
            raise ValueError(
                f"Calendar strip refused: cumulative series dipped ({prev_v}% -> {next_v}%)"
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
                "is_tail": False,
            }
        )

    last_cum = int(rungs[-1]["cum_pct"])
    tail_pct = max(0, 100 - last_cum)
    if tail_label and tail_pct > 0:
        last_entry = rungs[-1]
        raw_days.append(
            {
                "dow": str(last_entry["dow"]),
                "day_num": f"{last_entry['day_num']}+",
                "month_abbr": tail_label,
                "daily_pct": tail_pct,
                "is_peak": False,
                "is_tail": True,
            }
        )

    peak_val = max((d["daily_pct"] for d in raw_days if not d["is_tail"]), default=0)
    if peak_val > 0:
        for d in raw_days:
            if not d["is_tail"] and d["daily_pct"] == peak_val:
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
                        shade=1.0 if d["is_peak"] else min(0.9, daily / max_pct),
                        center_label=d["day_num"],
                        bottom_label="<1%" if daily <= 0 else f"{daily}%",
                        muted=(daily <= 0),
                        highlight_role="day_peak" if d["is_peak"] else None,
                    ),
                    _mark_word(d["month_abbr"], style="meta", tone="muted", align="center"),
                ],
            }
        )

    first = raw_days[0]
    last_date_entry = rungs[-1]
    span = f"{first['month_abbr']} {first['day_num']} – {last_date_entry['month_abbr']} {last_date_entry['day_num']}+"
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
            initials = node.get("initials")
            has_url = _is_valid_image_url(url)
            has_initials = (
                url is None
                and isinstance(initials, str)
                and 1 <= len(initials.strip()) <= 3
                and bool(re.fullmatch(r"[A-Za-z0-9?]+", initials.strip()))
            )
            if has_url:
                stats["verified_picture_count"] = stats.get("verified_picture_count", 0) + 1
            elif not has_initials:
                errors.append(f"Rule 1/4: picture mark missing verified HTTPS image_url ({url!r})")
            stats["picture_count"] += 1
            if node.get("subject_kind") == "person":
                stats["saw_person_picture"] = True
        elif mark_val == "number":
            unit_val = node.get("unit")
            if unit_val is not None and unit_val not in ALLOWED_NUMBER_UNITS:
                errors.append(f"Unsupported number.unit {unit_val!r}")
            if unit_val == "%":
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
            bar_style = node.get("bar_style")
            if bar_style not in ALLOWED_BAR_STYLES:
                errors.append(f"Unsupported bar_style {bar_style!r}")
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
                errors.append(f"Rule 1: {variant} row {idx} refused without picture or initials")
            elif variant == "photo_wall" and not any(
                isinstance(m, dict) and m.get("mark") == "picture" and _is_valid_image_url(m.get("url"))
                for m in item_marks
            ):
                errors.append(f"Rule 1: {variant} row {idx} refused without verified picture")

    if variant == "casting_sheet":
        has_any_verified = any(
            isinstance(m, dict) and m.get("mark") == "picture" and _is_valid_image_url(m.get("url"))
            for item in items
            if isinstance(item, dict)
            for m in (item.get("marks") or [])
        )
        if not has_any_verified:
            errors.append("Rule 1 (387: A): casting_sheet requires at least one verified picture")


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
    if row_layout not in ALLOWED_ROW_LAYOUTS:
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
                errors.append(f"Rule 1: {variant} row {idx} refused without picture or initials")
            elif variant == "photo_wall" and not any(
                isinstance(m, dict) and m.get("mark") == "picture" and _is_valid_image_url(m.get("url"))
                for m in leading
            ):
                errors.append(f"Rule 1: {variant} row {idx} refused without verified picture")

    if variant == "casting_sheet":
        has_any_verified = any(
            isinstance(m, dict) and m.get("mark") == "picture" and _is_valid_image_url(m.get("url"))
            for row in rows
            if isinstance(row, dict)
            for m in (row.get("leading") or [])
        )
        if not has_any_verified:
            errors.append("Rule 1 (387: A): casting_sheet requires at least one verified picture")

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
    if scale.get("scale_kind") not in ALLOWED_SCALE_KINDS:
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
            disclosure="2 more in this set",
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
        ("ceasefire", "US–Iran effective ceasefire begins", us_url, us_kind, [66, 81]),
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
                                shade=val / 100.0,
                                top_label=f"by {col['label']}",
                                center_label=f"{val}%",
                                muted=False,
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
            stat_caption="US–Iran ceasefire is 81% by December 31; Iran leadership change is 24% by June 30",
            source_count=2,
            route_slug="middle-east-deadlines",
            disclosure="4 more in this set",
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
        ("opus", "Next Claude Opus (5.6+) released", 85, ai_url, ai_kind),
        ("arena", "AI model reaches 1550 Chatbot Arena score", 42, dc_url, dc_kind),
        ("france", "France passes a national budget", 42, fr_url, fr_kind),
        ("banksy", "Banksy creates a new mural or street artwork", 31, pop_url, pop_kind),
        ("hegseth", "Pete Hegseth out as Secretary of Defense", 11, ph_url, ph_kind),
        ("x-ban", "X banned in any European country", 8, em_url, em_kind),
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
                    _mark_number(
                        38,
                        "38",
                        unit="days",
                        tone="accent",
                        prominence="hero",
                        align="left",
                        width="auto",
                        deadline_iso="2026-12-31T23:59:59-08:00",
                    ),
                    _mark_word(
                        "days left",
                        secondary_text="all of these end on Dec 31",
                        style="hero_label",
                        tone="primary",
                        bold=True,
                        width="flex",
                        deadline_iso="2026-12-31T23:59:59-08:00",
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
                if p_val - last_p >= 9:
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
        ("mars", "Elon Musk visits Mars in his lifetime", 12, space_url, space_kind),
        ("ryanair", "Elon Musk purchases Ryanair", 5, em_url, em_kind),
        ("superman", "Elon Musk cast in next Superman film", 5, em_url, em_kind),
        ("tesla-ceo", "Elon Musk out as Tesla CEO before 2027", 3, em_url, em_kind),
        ("optimus", "Tesla Optimus released this year", 2, dc_url, dc_kind),
        ("sports-team", "Elon Musk buys a major sports team before 2027", 1, sofi_url, sofi_kind),
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
        ("Portland Trail Blazers", "POR", "#e03a3e", 47, "Philadelphia 76ers", "PHI", "#1d428a", 53, "Mon Nov 23", "4:00 PM PT", "live", [27, 28]),
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
            common_headline="NBA: the next seven games",
            stat_caption="Pistons at Magic (54%–46%) headlines seven NBA matchups",
            source_count=4,
            route_slug="nba-slate",
            disclosure="6 more in this set",
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
    ]
    cards.append(
        build_calendar_strip_367a(
            card_id="kit-spotify-wrapped-2026",
            kicker="CULTURE · 2026",
            common_headline="Spotify Wrapped 2026: release day",
            stat_caption="Spotify Wrapped is most likely to arrive on Wednesday, December 2 (67%)",
            rungs=wrapped_rungs,
            tail_label="Dec+",
            ladder_footer=(
                "Chance it is out before each day: "
                "3% before Nov 27 · 12% before Dec 1 · 18% before Dec 2 · "
                "85% before Dec 3 · 90% before Dec 4 · Dec 4 or later, 10%"
            ),
        )
    )

    # 9–17. Batch 1 Forms Lab looks rebuilt directly in Kit v1 JSON (#13551)
    cards.extend(_build_batch1_forms_lab_examples(nhl_raw))

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


def _build_batch1_forms_lab_examples(
    nhl_raw: list[tuple[str, str, int, str]],
) -> list[dict[str, Any]]:
    """Build all 5 Batch 1 Forms Lab looks as valid Kit v1 JSON with Fable's #13551 fixes."""
    out: list[dict[str, Any]] = []

    org_urls = {
        "Apple": "https://thumb.wikimedia.org/wikipedia/commons/thumb/f/fa/Apple_logo_black.svg/330px-Apple_logo_black.svg.png",
        "NVIDIA": "https://thumb.wikimedia.org/wikipedia/commons/thumb/2/21/Nvidia_logo.svg/330px-Nvidia_logo.svg.png",
        "Microsoft": "https://thumb.wikimedia.org/wikipedia/commons/thumb/9/96/Microsoft_logo_%282012%29.svg/330px-Microsoft_logo_%282012%29.svg.png",
        "Alphabet": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c1/Google_%22G%22_logo.svg/330px-Google_%22G%22_logo.svg.png",
        "Google": "https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c1/Google_%22G%22_logo.svg/330px-Google_%22G%22_logo.svg.png",
        "Anthropic": "https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b0/Claude_AI_symbol.svg/330px-Claude_AI_symbol.svg.png",
        "OpenAI": "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/66/OpenAI_logo_2025_%28symbol%29.svg/330px-OpenAI_logo_2025_%28symbol%29.svg.png",
    }

    # Batch 1 Item 3a: Grid — Largest company places (1st, 2nd, 3rd)
    places_specs = [
        ("Apple", [86, 2, 2]),
        ("NVIDIA", [11, 79, 13]),
        ("Microsoft", [1, 16, 64]),
        ("Alphabet", [1, 3, 18]),
    ]
    places_rows = []
    for idx, (comp, vals) in enumerate(places_specs, 1):
        best_v = max(vals)
        places_rows.append(
            {
                "id": f"places-{comp.lower()}",
                "leading": [
                    _mark_word(str(idx), style="rank", tone="muted", width="xs"),
                    _mark_picture(url=org_urls[comp], alt=comp, subject_kind="organization", size="sm", contain=True),
                    _mark_word(comp, style="row", tone="primary", bold=True, width="flex"),
                ],
                "cells": [
                    {
                        "column_key": col_k,
                        "marks": [
                            _mark_tile(
                                shade=v / 100.0,
                                center_label=f"{v}%",
                                highlight_role="row_peak" if v == best_v else None,
                            )
                        ],
                    }
                    for col_k, v in zip(["1st", "2nd", "3rd"], vals)
                ],
            }
        )
    out.append(
        _make_kit_card(
            card_id="kit-batch1-places-grid",
            layout="grid",
            variant="scoreboard_grid",
            kicker="TECH & ECONOMICS",
            common_headline="Largest company at the end of 2026",
            stat_caption="Apple leads for 1st at 86%, NVIDIA leads for 2nd at 79%, and Microsoft leads for 3rd at 64% on Dec 31",
            source_count=1,
            route_slug="largest-company-2026",
            footnote="Outlined cell marks each company's highest-probability place.",
            body={
                "leading_label": "Company",
                "show_column_headers": True,
                "row_layout": "matrix",
                "columns": [
                    {"key": "1st", "label": "1st"},
                    {"key": "2nd", "label": "2nd"},
                    {"key": "3rd", "label": "3rd"},
                ],
                "rows": places_rows,
            },
        )
    )

    # Batch 1 Item 3b: Grid — AI model leaderboard
    ai_cols = [("overall", "Overall"), ("coding", "Coding"), ("t2v", "Video")]
    ai_matrix = {
        "Google": [81, 29, 52],
        "Anthropic": [13, 51, 0],
        "OpenAI": [4, 16, 7],
    }
    col_peaks = [max(ai_matrix[lab][i] for lab in ai_matrix) for i in range(3)]
    ai_rows = []
    for idx, (lab, vals) in enumerate(ai_matrix.items(), 1):
        ai_rows.append(
            {
                "id": f"ai-grid-{lab.lower()}",
                "leading": [
                    _mark_word(str(idx), style="rank", tone="muted", width="xs"),
                    _mark_picture(url=org_urls[lab], alt=lab, subject_kind="organization", size="sm", contain=True),
                    _mark_word(lab, style="row", tone="primary", bold=True, width="flex"),
                ],
                "cells": [
                    {
                        "column_key": c_key,
                        "marks": [
                            _mark_tile(
                                shade=v / 100.0,
                                center_label="<1%" if v <= 0 else f"{v}%",
                                muted=(v <= 0),
                                highlight_role="column_peak" if v > 0 and v == col_peaks[c_idx] else None,
                            )
                        ],
                    }
                    for c_idx, ((c_key, _), v) in enumerate(zip(ai_cols, vals))
                ],
            }
        )
    out.append(
        _make_kit_card(
            card_id="kit-batch1-ai-leaderboard",
            layout="grid",
            variant="scoreboard_grid",
            kicker="TECH & AI",
            common_headline="AI model leaderboard at year-end",
            stat_caption="Google leads Overall at 81% and Video at 52%; Anthropic leads Coding at 51%",
            source_count=1,
            route_slug="ai-model-leaderboard-2026",
            footnote="Outlined cell marks the column leader across December 31 markets.",
            body={
                "leading_label": "Lab",
                "show_column_headers": True,
                "row_layout": "matrix",
                "columns": [{"key": k, "label": lbl} for k, lbl in ai_cols],
                "rows": ai_rows,
            },
        )
    )

    # Batch 1 Item 3c: Grid — NBA 2026–27 awards with full first & last names
    nba_award_cols = [("mvp", "MVP"), ("dpoy", "DPOY"), ("clutch", "Clutch")]
    nba_award_specs = [
        ("Victor Wembanyama", "https://a.espncdn.com/i/headshots/nba/players/full/5104157.png", [51, 59, 11]),
        ("Luka Dončić", "https://a.espncdn.com/i/headshots/nba/players/full/3945274.png", [29, 0, 19]),
        ("Shai Gilgeous-Alexander", "https://a.espncdn.com/i/headshots/nba/players/full/4278073.png", [4, 1, 26]),
        ("Nikola Jokic", "https://a.espncdn.com/i/headshots/nba/players/full/3112335.png", [5, 0, 15]),
        ("Giannis Antetokounmpo", "https://a.espncdn.com/i/headshots/nba/players/full/3032977.png", [3, 4, 7]),
        ("Evan Mobley", "https://a.espncdn.com/i/headshots/nba/players/full/4432158.png", [0, 17, 0]),
    ]
    nba_peaks = [max(row[2][i] for row in nba_award_specs) for i in range(3)]
    nba_award_rows = []
    for idx, (player, img_url, vals) in enumerate(nba_award_specs, 1):
        nba_award_rows.append(
            {
                "id": f"nba-award-{idx}",
                "leading": [
                    _mark_word(str(idx), style="rank", tone="muted", width="xs"),
                    _mark_picture(url=img_url, alt=player, subject_kind="person", size="sm", contain=False),
                    _mark_word(player, style="row", tone="primary", bold=True, width="flex"),
                ],
                "cells": [
                    {
                        "column_key": c_key,
                        "marks": [
                            _mark_tile(
                                shade=v / 100.0,
                                center_label="<1%" if v <= 0 else f"{v}%",
                                muted=(v <= 0),
                                highlight_role="column_peak" if v > 0 and v == nba_peaks[c_idx] else None,
                            )
                        ],
                    }
                    for c_idx, ((c_key, _), v) in enumerate(zip(nba_award_cols, vals))
                ],
            }
        )
    out.append(
        _make_kit_card(
            card_id="kit-batch1-nba-awards",
            layout="grid",
            variant="scoreboard_grid",
            kicker="SPORTS · BASKETBALL",
            common_headline="NBA 2026–27 major player awards",
            stat_caption="Victor Wembanyama leads MVP (51%) and DPOY (59%); Shai Gilgeous-Alexander leads Clutch (26%)",
            source_count=2,
            route_slug="nba-awards-2027",
            footnote="Outlined cell leads each award field.",
            body={
                "leading_label": "Player",
                "show_column_headers": True,
                "row_layout": "matrix",
                "columns": [{"key": k, "label": lbl} for k, lbl in nba_award_cols],
                "rows": nba_award_rows,
            },
        )
    )

    # Batch 1 Item 4a: Axis / Shared scale — Opening weekend box office ($M)
    avengers_url, avengers_kind = _art_entry("avengers-doomsday")
    dune_url, dune_kind = _art_entry("dune-part-three")
    out.append(
        _make_kit_card(
            card_id="kit-batch1-box-office-scale",
            layout="axis",
            variant="shared_scale",
            kicker="ENTERTAINMENT · BOX OFFICE",
            common_headline="Opening weekend box office",
            stat_caption="Avengers: Doomsday peaks at $400M+ (75%), while Dune: Part Three centers on $110M–$130M (40%)",
            source_count=2,
            route_slug="box-office-2026",
            body={
                "scale": {
                    "scale_kind": "numeric",
                    "unit": "$M",
                    "min": 0,
                    "max": 460,
                    "ticks": [
                        {"x": 0, "label": "$0M"},
                        {"x": 115, "label": "$115M"},
                        {"x": 230, "label": "$230M"},
                        {"x": 345, "label": "$345M"},
                        {"x": 460, "label": "$460M"},
                    ],
                },
                "marks": [],
                "series": [
                    {
                        "id": "bo-avengers",
                        "leading": [
                            _mark_picture(url=avengers_url, alt="Avengers: Doomsday", subject_kind=avengers_kind, size="sm", contain=False),
                            _mark_word("Avengers: Doomsday", style="row", tone="primary", bold=True, width="flex"),
                        ],
                        "marks": [
                            {"mark": "bar", "bar_style": "range", "lo": round(400 / 460, 4), "hi": 1.0, "width": "flex"},
                            _mark_word("$400M+", style="meta", tone="secondary"),
                            _mark_number(75, "75%", unit="%", tone="primary", prominence="primary", align="right", width="sm"),
                        ],
                    },
                    {
                        "id": "bo-dune",
                        "leading": [
                            _mark_picture(url=dune_url, alt="Dune: Part Three", subject_kind=dune_kind, size="sm", contain=False),
                            _mark_word("Dune: Part Three", style="row", tone="primary", bold=True, width="flex"),
                        ],
                        "marks": [
                            {"mark": "bar", "bar_style": "range", "lo": round(110 / 460, 4), "hi": round(130 / 460, 4), "width": "flex"},
                            _mark_word("$110M–$130M", style="meta", tone="secondary"),
                            _mark_number(40, "40%", unit="%", tone="primary", prominence="primary", align="right", width="sm"),
                        ],
                    },
                ],
            },
        )
    )

    # Batch 1 Item 4b: Grid / Dated tiles — AGI achievement timeline (dated tiles avoid false linear gaps)
    agi_rungs = [
        ("jan27", "Jan '27", 5),
        ("apr27", "Apr '27", 11),
        ("jul27", "Jul '27", 21),
        ("oct27", "Oct '27", 34),
        ("jan28", "Jan '28", 49),
        ("jan29", "Jan '29", 70),
        ("jan31", "Jan '31", 76),
    ]
    out.append(
        _make_kit_card(
            card_id="kit-batch1-agi-dated-tiles",
            layout="grid",
            variant="dated_tiles",
            kicker="TECH · MILESTONES",
            common_headline="When any company achieves AGI",
            stat_caption="Cumulative chance crosses 49% by Jan '28 and reaches 76% by Jan '31",
            source_count=1,
            route_slug="when-agi-achieved",
            body={
                "show_column_headers": False,
                "row_layout": "stacked_cells",
                "columns": [{"key": k, "label": lbl} for k, lbl, _ in agi_rungs[:4]],
                "rows": [
                    {
                        "id": "agi-near",
                        "leading": [
                            _mark_word("Through Jan '28", style="row", tone="primary", bold=True, width="flex"),
                        ],
                        "cells": [
                            {
                                "column_key": k,
                                "marks": [_mark_tile(shade=v / 100.0, top_label=f"by {lbl}", center_label=f"{v}%")],
                            }
                            for k, lbl, v in agi_rungs[:4]
                        ],
                    },
                    {
                        "id": "agi-later",
                        "leading": [
                            _mark_word("2028 to 2031", style="row", tone="primary", bold=True, width="flex"),
                        ],
                        "cells": [
                            {
                                "column_key": k,
                                "marks": [_mark_tile(shade=v / 100.0, top_label=f"by {lbl}", center_label=f"{v}%")],
                            }
                            for k, lbl, v in agi_rungs[4:]
                        ],
                    },
                ],
            },
        )
    )

    # Batch 1 Item 4c: Axis — Flagship AI release deadline race
    out.append(
        _make_kit_card(
            card_id="kit-batch1-deadline-race",
            layout="axis",
            variant="deadline_race",
            kicker="TECH · AI RELEASES",
            common_headline="Next flagship AI release race by Dec 31",
            stat_caption="Claude Opus is at 65% vs Gemini Krypton 47% by Dec 15, and 85% vs 57% by Dec 31",
            source_count=1,
            route_slug="flagship-ai-release-race",
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
                "marks": [],
                "series": [
                    {
                        "id": "dr-opus-climb",
                        "leading": [
                            _mark_picture(url=org_urls["Anthropic"], alt="Claude Opus", subject_kind="organization", size="xs", contain=True),
                            _mark_word("Claude Opus · Nov 30 → Dec 15 (65%) → Dec 31", style="row", tone="primary", bold=True, width="flex"),
                        ],
                        "marks": [
                            {"mark": "bar", "bar_style": "range", "lo": 0.14, "hi": 0.85, "pct_label": "14% → 85%", "width": "flex"},
                            _mark_number(85, "85%", unit="%", tone="accent", prominence="primary", align="right", width="sm"),
                        ],
                    },
                    {
                        "id": "dr-krypton-climb",
                        "leading": [
                            _mark_picture(url=org_urls["Google"], alt="Gemini Krypton", subject_kind="organization", size="xs", contain=True),
                            _mark_word("Gemini Krypton · Nov 30 → Dec 15 (47%) → Dec 31", style="row", tone="primary", bold=True, width="flex"),
                        ],
                        "marks": [
                            {"mark": "bar", "bar_style": "range", "lo": 0.10, "hi": 0.57, "pct_label": "10% → 57%", "width": "flex"},
                            _mark_number(57, "57%", unit="%", tone="primary", prominence="primary", align="right", width="sm"),
                        ],
                    },
                ],
            },
        )
    )

    # Batch 1 Item 6a: Stack / casting_sheet — Next James Bond (two rows with separate faces for tied co-favorites)
    boyd_url, boyd_kind = _art_entry("boyd-holbrook")
    mackie_url, mackie_kind = _art_entry("anthony-mackie")
    bond_roles = [
        ("Theme Song", "Raye", "person", "https://image.tmdb.org/t/p/w185/zA5WXnyg8iH8DPpuXvsmJpPT2n1.jpg", 42, "42%"),
        ("Bond Girl", "Margaret Qualley", "person", "https://image.tmdb.org/t/p/w185/r5WeMrU4YLJqRRE3joeOrBVicAH.jpg", 31, "31%"),
        ("M", "Olivia Colman", "person", "https://image.tmdb.org/t/p/w185/lawJUdbLb1YW0niaYjiVGR9IBG8.jpg", 29, "29%"),
        ("Q", "Ben Whishaw", "person", "https://image.tmdb.org/t/p/w185/e74Cz65ifeNb9zHfUTvF5rTix0d.jpg", 25, "25%"),
        ("Villain", "Cillian Murphy", "person", "https://image.tmdb.org/t/p/w185/2lKs67r7FI4bPu0AXxMUJZxmUXn.jpg", 17, "17%"),
        ("Moneypenny", "Naomie Harris", "person", "https://image.tmdb.org/t/p/w185/41TVAcYqKKF7PGf3x7QfaLvkLSW.jpg", 12, "12%"),
        ("Felix Leiter", "Boyd Holbrook", boyd_kind, boyd_url, 11, "11%"),
        ("Felix Leiter", "Anthony Mackie", mackie_kind, mackie_url, 11, "11%"),
    ]
    out.append(
        _make_kit_card(
            card_id="kit-batch1-next-james-bond",
            layout="stack",
            variant="casting_sheet",
            kicker="ENTERTAINMENT · FILM",
            common_headline="Next James Bond",
            stat_caption="Raye leads Theme Song at 42%; Boyd Holbrook and Anthony Mackie share the lead for Felix Leiter at 11% each",
            source_count=2,
            route_slug="next-james-bond",
            body={
                "header_layout": "none",
                "header_marks": [],
                "items": [
                    {
                        "id": f"bond-{idx}",
                        "marks": [
                            _mark_picture(url=img_u, alt=leader, subject_kind=s_kind, size="sm", contain=False),
                            _mark_word(leader, secondary_text=role_name, style="hero_label", tone="primary", width="flex"),
                            _mark_bar_single(p / 100.0, width="sm"),
                            _mark_number(p, disp, unit="%", tone="primary", prominence="primary", align="right", width="auto"),
                        ],
                    }
                    for idx, (role_name, leader, s_kind, img_u, p, disp) in enumerate(bond_roles, 1)
                ],
            },
        )
    )

    # Batch 1 Item 6b: Stack / casting_sheet — Oscars 2027 (verified portraits & posters, no lab notes)
    oscar_roles = [
        ("Best Picture", "The Odyssey", "film", "https://image.tmdb.org/t/p/w342/krVa7rKCQb4OBfsr2LTJv4rTz5q.jpg", 45, True),
        ("Best Actor", "John Malkovich", "person", "https://image.tmdb.org/t/p/w185/7GoOdGNc4ra1L0F5nJTkmIB37iu.jpg", 49, False),
        ("Best Actress", "Julianne Moore", "person", "https://image.tmdb.org/t/p/w185/3YF19rWusxWfEI59ZM33dFhasRq.jpg", 85, False),
        ("Best Director", "Christopher Nolan", "person", "https://image.tmdb.org/t/p/w185/xuAIuYSmsUzKlUMBFGVZaWsY3DZ.jpg", 62, False),
        ("Supp. Actor", "Paul Giamatti", "person", "https://thumb.wikimedia.org/wikipedia/commons/thumb/3/3e/Paul_Giamatti_at_the_2026_New_York_Film_Festival-032.jpg/500px-Paul_Giamatti_at_the_2026_New_York_Film_Festival-032.jpg", 40, False),
        ("Supp. Actress", "Anne Hathaway", "person", "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a5/AnneHathaway-byPhilipRomano-Crop.jpg/500px-AnneHathaway-byPhilipRomano-Crop.jpg", 64, False),
        ("Orig. Screenplay", "Wild Horse Nine", "film", "https://image.tmdb.org/t/p/w342/dNJFRtVg3xLQ7dbNIQ55cmmIniD.jpg", 54, True),
    ]
    out.append(
        _make_kit_card(
            card_id="kit-batch1-oscars-casting",
            layout="stack",
            variant="casting_sheet",
            kicker="ENTERTAINMENT · AWARDS",
            common_headline="Oscars 2027 lead races",
            stat_caption="Julianne Moore leads Best Actress at 85% and Anne Hathaway leads Supporting Actress at 64%",
            source_count=1,
            route_slug="oscars-2027-lead-races",
            body={
                "header_layout": "none",
                "header_marks": [],
                "items": [
                    {
                        "id": f"oscar-{idx}",
                        "marks": [
                            _mark_picture(url=img_u, alt=leader, subject_kind=s_kind, size="sm", contain=is_contain),
                            _mark_word(leader, secondary_text=role_name, style="hero_label", tone="primary", width="flex"),
                            _mark_bar_single(p / 100.0, width="sm"),
                            _mark_number(p, f"{p}%", unit="%", tone="primary", prominence="primary", align="right", width="sm"),
                        ],
                    }
                    for idx, (role_name, leader, s_kind, img_u, p, is_contain) in enumerate(oscar_roles, 1)
                ],
            },
        )
    )

    # Batch 1 Item 7b: Stack / the_cut — NHL Playoffs cut by conference (uniform crest sizes + arrow `→`)
    east_names = {
        "Carolina Hurricanes", "Tampa Bay Lightning", "New Jersey Devils", "Montreal Canadiens",
        "Florida Panthers", "Ottawa Senators", "Boston Bruins", "Washington Capitals",
        "New York Rangers", "New York Islanders", "Buffalo Sabres", "Philadelphia Flyers",
        "Columbus Blue Jackets", "Toronto Maple Leafs", "Detroit Red Wings",
    }
    east_teams = [x for x in nhl_raw if x[0] in east_names][:10]
    west_teams = [x for x in nhl_raw if x[0] not in east_names][:10]
    cut_items: list[dict[str, Any]] = []
    for conf_label, conf_slice in (("East", east_teams), ("West", west_teams)):
        for rank_idx, (team_name, abbr, p_val, color) in enumerate(conf_slice, 1):
            logo_url, _ = _team_logo(team_name)
            pct_disp = "38% each" if (conf_label == "West" and p_val == 38) else f"{p_val}%"
            item_entry: dict[str, Any] = {
                "id": f"cut-{conf_label.lower()}-{abbr.lower()}",
                "sport_key": "icehockey_nhl",
                "marks": [
                    _mark_word(f"{conf_label[0]}{rank_idx}", style="rank", tone="muted", width="xs"),
                    _mark_picture(url=logo_url, alt=abbr, subject_kind="team", size="sm", contain=True),
                    _mark_word(team_name, style="row", tone="primary", bold=(rank_idx <= 8), width="flex"),
                    _mark_bar_single(p_val / 100.0, width="sm", fill_color=_adaptive_team_color(color)),
                    _mark_number(p_val, pct_disp, unit="%", tone="primary", prominence="primary", align="right", width="auto"),
                ],
            }
            if conf_label == "East" and rank_idx == 8:
                item_entry["divider_after"] = {"label": "Top 8 in Eastern Conference advance →"}
            elif conf_label == "West" and rank_idx == 9:
                item_entry["divider_after"] = {"label": "Ducks & Blues tied 38% each at Western #8 cut →"}
            cut_items.append(item_entry)

    out.append(
        _make_kit_card(
            card_id="kit-batch1-nhl-conference-cut",
            layout="stack",
            variant="the_cut",
            kicker="HOCKEY · NHL PLAYOFFS",
            common_headline="2026–27 NHL Playoffs: Eastern vs Western cut",
            stat_caption="Top 8 per conference advance → Ducks and Blues tied 38% each for the Western final spot",
            source_count=2,
            route_slug="nhl-playoffs-conference-cut",
            body={
                "single_sport_key": "icehockey_nhl",
                "header_layout": "split",
                "header_marks": [
                    _mark_word("BY CONFERENCE", style="kicker", tone="muted", bold=True),
                    _mark_word("16 → 8 PLACES", style="kicker", tone="muted", bold=True, align="right"),
                ],
                "items": cut_items,
            },
        )
    )
    return out


def write_golden_examples_json(dest: Path = GOLDEN_EXAMPLES_PATH) -> Path:
    payload = build_kit_v1_worked_examples()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return dest
