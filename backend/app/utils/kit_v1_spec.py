"""Kit v1 (Ruling 366: B, 367: A, and Fable's 7 rules on #13551).

Cross-platform structured card specification (`kit_version: 1`) reconciled with
Builder C (`comment-7122832951`): top-level `layout` + `variant` envelope with
typed per-variant `data`, standard `source_mark`, tap `route`, `footnote`,
and fail-closed validation. Every worked example uses real numbers from the
batch2 redraw snapshot (`batch2/redraw.json` + Spotify Wrapped 367: A) and verified
repo artwork (`_lookup_team_or_nation_logo` + `verified_discover_art.json`).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.utils.discover_image_policy import _lookup_team_or_nation_logo

KIT_VERSION = 1

_DATA_DISCOVER_DIR = Path(__file__).resolve().parents[2] / "data" / "discover"
_VERIFIED_ART_PATH = _DATA_DISCOVER_DIR / "verified_discover_art.json"
GOLDEN_EXAMPLES_PATH = _DATA_DISCOVER_DIR / "kit_v1_golden_examples.json"

VARIANT_TO_LAYOUT: dict[str, str] = {
    "countdown": "stack",
    "road_ahead": "stack",
    "one_in_n": "stack",
    "single_sport_slate": "stack",
    "casting_sheet": "stack",
    "the_cut": "stack",
    "scoreboard_grid": "grid",
    "places_grid": "grid",
    "dated_tiles": "grid",
    "photo_wall": "grid",
    "calendar_strip": "calendar",
    "bubble_line": "axis",
    "shared_scale": "axis",
    "deadline_line": "axis",
}

ALLOWED_LAYOUTS: frozenset[str] = frozenset(VARIANT_TO_LAYOUT.values())
ALLOWED_VISUAL_VARIANTS: frozenset[str] = frozenset(VARIANT_TO_LAYOUT.keys())

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


def _make_kit_card(
    *,
    card_id: str,
    variant: str,
    kicker: str,
    common_headline: str,
    stat_caption: str,
    source_count: int = 2,
    route_kind: str = "collection",
    route_id: int | None = None,
    route_slug: str | None = None,
    footnote: str | None = None,
    disclosure: str | None = None,
    data: dict[str, Any],
) -> dict[str, Any]:
    layout = VARIANT_TO_LAYOUT.get(variant)
    if layout is None:
        raise ValueError(f"Unknown Kit v1 variant={variant!r}")
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
        "data": data,
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
) -> dict[str, Any]:
    """Build Ruling 367: A calendar strip from one non-dipping cumulative ladder."""
    if len(rungs) < 2:
        raise ValueError("Calendar strip requires at least two cumulative rungs")

    cum_values = [int(r["cum_pct"]) for r in rungs]
    for prev_v, next_v in zip(cum_values, cum_values[1:]):
        if next_v < prev_v - 1:
            raise ValueError(
                f"Calendar strip refused: cumulative ladder dipped ({prev_v}% -> {next_v}%)"
            )

    days: list[dict[str, Any]] = []
    for idx in range(len(rungs) - 1):
        cur = rungs[idx]
        nxt = rungs[idx + 1]
        daily = max(0, int(nxt["cum_pct"]) - int(cur["cum_pct"]))
        days.append(
            {
                "dow": str(cur["dow"]),
                "day_num": str(cur["day_num"]),
                "month_abbr": str(cur["month_abbr"]),
                "daily_pct": daily,
                "is_peak": False,
            }
        )

    peak_val = max((d["daily_pct"] for d in days), default=0)
    if peak_val > 0:
        peak_marked = False
        for d in days:
            if not peak_marked and d["daily_pct"] == peak_val:
                d["is_peak"] = True
                peak_marked = True

    first = days[0]
    last = days[-1]
    span = (
        f"{first['month_abbr']} {first['day_num']} – {last['month_abbr']} {last['day_num']}"
    )
    return _make_kit_card(
        card_id=card_id,
        variant="calendar_strip",
        kicker=kicker,
        common_headline=common_headline,
        stat_caption=stat_caption,
        source_count=2,
        route_kind="collection",
        route_slug=route_slug,
        footnote=ladder_footer,
        data={
            "month_span_label": span,
            "show_percent": True,
            "ladder_rule_note": CALENDAR_STRIP_RULE_NOTE,
            "days": days,
        },
    )


def _check_pct(val: Any, label: str, errors: list[str]) -> None:
    if not isinstance(val, int) or isinstance(val, bool) or not (0 <= val <= 100):
        errors.append(f"{label} must be an integer percent 0..100")


def validate_kit_v1_card(spec: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a Kit v1 card against Ruling 366: B, 367: A, and Fable's 7 rules."""
    errors: list[str] = []
    if not isinstance(spec, dict):
        return False, ["spec must be a dict"]

    if spec.get("kit_version") != KIT_VERSION:
        errors.append("kit_version must equal 1")

    if not str(spec.get("id") or "").strip():
        errors.append("id must be non-empty")

    variant = spec.get("variant")
    if variant in TEXT_ONLY_FORBIDDEN_VARIANTS:
        errors.append("Rule 1: text-only fallback variants are forbidden in Kit v1")
        return False, errors

    if spec.get("refusal_reason"):
        return False, [str(spec["refusal_reason"])]

    layout = spec.get("layout")
    if variant not in ALLOWED_VISUAL_VARIANTS:
        errors.append(f"Rule 1: unsupported visual variant {variant!r}")
        return False, errors

    expected_layout = VARIANT_TO_LAYOUT[variant]
    if layout != expected_layout:
        errors.append(
            f"layout/variant mismatch: variant {variant!r} requires layout={expected_layout!r}, got {layout!r}"
        )
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

    data = spec.get("data")
    if not isinstance(data, dict):
        errors.append("data object is required")
        return False, errors

    # Rule 3: shared scale requires unit, step, ticks, and caption, no mixed units
    if data.get("shared_scale") or "scale_units" in data:
        units = data.get("scale_units")
        if isinstance(units, list) and len({str(u) for u in units}) > 1:
            errors.append("Rule 3: shared scale refuses mixed units")
        for req_key in ("scale_unit", "scale_step", "scale_ticks", "scale_caption"):
            if not data.get(req_key):
                errors.append(f"Rule 3: shared scale requires {req_key}")

    if variant in {"scoreboard_grid", "places_grid"}:
        _validate_scoreboard_grid(data, errors)
    elif variant == "dated_tiles":
        _validate_dated_tiles(data, errors)
    elif variant == "countdown":
        _validate_countdown(data, errors)
    elif variant == "road_ahead":
        _validate_road_ahead(data, errors)
    elif variant == "bubble_line":
        _validate_bubble_line(data, errors)
    elif variant == "one_in_n":
        _validate_one_in_n(data, errors)
    elif variant == "single_sport_slate":
        _validate_single_sport_slate(data, errors)
    elif variant == "calendar_strip":
        _validate_calendar_strip(data, errors)
    elif variant in {"casting_sheet", "photo_wall"}:
        _validate_pictured_people_look(variant, data, errors)

    return len(errors) == 0, errors


def _validate_scoreboard_grid(data: dict[str, Any], errors: list[str]) -> None:
    cols = data.get("columns") or []
    rows = data.get("rows") or []
    if not cols or not rows:
        errors.append("scoreboard_grid requires columns and rows")
        return
    if any(c.get("refused_sum") is not None for c in cols):
        errors.append("scoreboard_grid must strip refused columns server-side before serving")
    if len(cols) < 2:
        errors.append("scoreboard_grid requires at least 2 valid columns (fallback if < 2)")
    valid_keys = {c["key"] for c in cols}
    for idx, row in enumerate(rows, 1):
        if row.get("rank") != idx:
            errors.append(f"Rule 4: scoreboard_grid row {idx} must carry sequential rank={idx}")
        if not _is_valid_image_url(row.get("image_url")):
            errors.append(f"Rule 4: row {idx} missing verified image_url")
        if row.get("image_kind") == "person" and not _has_first_and_last_name(row.get("name", "")):
            errors.append(f"Rule 4: person row {row.get('name')!r} must have first and last name")
        cells = row.get("cells") or {}
        for k in valid_keys:
            if cells.get(k) is not None:
                _check_pct(cells[k], f"row {idx} cell {k}", errors)


def _validate_dated_tiles(data: dict[str, Any], errors: list[str]) -> None:
    cols = data.get("columns") or []
    rows = data.get("rows") or []
    if not cols or not rows:
        errors.append("dated_tiles requires columns and rows")
        return
    col_order = [c["key"] for c in cols]
    for idx, row in enumerate(rows, 1):
        if not _is_valid_image_url(row.get("image_url")):
            errors.append(f"dated_tiles row {idx} missing verified image_url")
        cells = row.get("cells") or {}
        vals = [cells[k] for k in col_order if cells.get(k) is not None]
        for v in vals:
            _check_pct(v, f"dated_tiles row {idx}", errors)
        if all(isinstance(v, int) for v in vals):
            for prev_v, next_v in zip(vals, vals[1:]):
                if next_v < prev_v - 1:
                    errors.append(
                        f"dated_tiles row {row.get('name')!r} dips ({prev_v}% -> {next_v}%)"
                    )


def _validate_countdown(data: dict[str, Any], errors: list[str]) -> None:
    days_left = data.get("days_left")
    if not isinstance(days_left, int) or days_left < 0:
        errors.append("countdown days_left must be a non-negative integer")
    if not str(data.get("deadline_label") or "").strip():
        errors.append("countdown requires deadline_label")
    rows = data.get("rows") or []
    if not rows:
        errors.append("countdown requires rows")
    for idx, row in enumerate(rows, 1):
        _check_pct(row.get("p"), f"countdown row {idx}", errors)
        if not _is_valid_image_url(row.get("image_url")):
            errors.append(f"countdown row {idx} missing verified image_url")
        if row.get("image_kind") == "person" and not _has_first_and_last_name(row.get("name", "")):
            errors.append(f"Rule 4: person row {row.get('name')!r} requires first and last name")


def _validate_road_ahead(data: dict[str, Any], errors: list[str]) -> None:
    if not _is_valid_image_url(data.get("team_image_url")):
        errors.append("road_ahead missing verified team_image_url")
    rows = data.get("rows") or []
    if len(rows) < 2:
        errors.append("road_ahead requires at least 2 scheduled games")
    for idx, row in enumerate(rows, 1):
        _check_pct(row.get("team_p"), f"road_ahead row {idx}", errors)
        if not _is_valid_image_url(row.get("opponent_image_url")):
            errors.append(f"road_ahead row {idx} missing opponent_image_url")
        if row.get("home_or_away") not in {"vs", "at"}:
            errors.append(f"road_ahead row {idx} invalid home_or_away")


def _validate_bubble_line(data: dict[str, Any], errors: list[str]) -> None:
    band_low = data.get("band_low")
    band_high = data.get("band_high")
    if not (
        isinstance(band_low, int)
        and isinstance(band_high, int)
        and 0 <= band_low < band_high <= 100
    ):
        errors.append("bubble_line requires valid 0 <= band_low < band_high <= 100")
    points = data.get("points") or []
    if len(points) < 10:
        errors.append("bubble_line requires at least 10 points")
    for idx, pt in enumerate(points, 1):
        _check_pct(pt.get("p"), f"bubble_line point {idx}", errors)
        if not _is_valid_image_url(pt.get("image_url")):
            errors.append(f"bubble_line point {idx} missing verified image_url")


def _validate_one_in_n(data: dict[str, Any], errors: list[str]) -> None:
    rows = data.get("rows") or []
    if not rows:
        errors.append("one_in_n requires rows")
    for idx, row in enumerate(rows, 1):
        p = row.get("p")
        _check_pct(p, f"one_in_n row {idx}", errors)
        if isinstance(p, int):
            expected_n = compute_one_in_n(p)
            if row.get("one_in_n") != expected_n:
                errors.append(
                    f"Rule 7: one_in_n row {idx} must set one_in_n={expected_n} beside {p}%"
                )
        if not _is_valid_image_url(row.get("image_url")):
            errors.append(f"one_in_n row {idx} missing verified image_url")


def _validate_single_sport_slate(data: dict[str, Any], errors: list[str]) -> None:
    sport_key = str(data.get("sport_key") or "").strip()
    if not sport_key:
        errors.append("Rule 6: single_sport_slate requires sport_key")
        return
    rows = data.get("rows") or []
    if not rows:
        errors.append("single_sport_slate requires rows")
    for idx, row in enumerate(rows, 1):
        row_sport = str(row.get("sport_key") or sport_key).strip()
        if row_sport != sport_key:
            errors.append(
                f"Rule 6: mixed sport on slate (expected {sport_key!r}, got {row_sport!r})"
            )
        for side in ("away", "home"):
            side_obj = row.get(side) or {}
            _check_pct(side_obj.get("p"), f"slate row {idx} {side}", errors)
            if not _is_valid_image_url(side_obj.get("image_url")):
                errors.append(f"slate row {idx} {side} missing verified image_url")


def _validate_calendar_strip(data: dict[str, Any], errors: list[str]) -> None:
    if data.get("show_percent") is not True:
        errors.append("Ruling 367: A requires show_percent=True on calendar_strip")
    if not str(data.get("ladder_rule_note") or "").strip():
        errors.append("Ruling 367: A requires plain ladder_rule_note explanation")
    days = data.get("days") or []
    if len(days) < 2:
        errors.append("calendar_strip requires at least 2 day tiles")
    for idx, day in enumerate(days, 1):
        _check_pct(day.get("daily_pct"), f"calendar_strip day {idx}", errors)


def _validate_pictured_people_look(variant: str, data: dict[str, Any], errors: list[str]) -> None:
    rows = data.get("rows") or []
    if not rows:
        errors.append(f"{variant} requires rows")
        return
    prev_p: int | None = None
    for idx, row in enumerate(rows, 1):
        if not _is_valid_image_url(row.get("image_url")):
            errors.append(f"Rule 1/4: {variant} row {idx} refused without verified image_url")
        if row.get("image_kind") == "person" and not _has_first_and_last_name(row.get("name", "")):
            errors.append(f"Rule 4: {variant} person row {row.get('name')!r} needs first & last name")
        _check_pct(row.get("p"), f"{variant} row {idx}", errors)
        if variant == "photo_wall":
            if row.get("rank") != idx:
                errors.append(f"Rule 5: photo_wall row {idx} must carry rank={idx}")
            p_val = row.get("p")
            if isinstance(p_val, int):
                if prev_p is not None and p_val > prev_p:
                    errors.append("Rule 5: photo_wall must sort likeliest first")
                prev_p = p_val


def build_kit_v1_worked_examples() -> dict[str, Any]:
    """Return the 8 worked Kit v1 examples + Rule/367-A refusal examples."""
    cards: list[dict[str, Any]] = []

    # 1. grid / scoreboard_grid — College Football National Championship (rd-57)
    cfb_rows = []
    for idx, (team, nat_p, sec_p) in enumerate(
        [
            ("Georgia", 34, 68),
            ("Texas", 11, 26),
            ("Alabama", 10, 3),
            ("Tennessee", 4, 3),
        ],
        1,
    ):
        url, kind = _team_logo(team)
        cfb_rows.append(
            {
                "rank": idx,
                "name": team,
                "image_url": url,
                "image_kind": kind,
                "cells": {"181": nat_p, "233": sec_p},
            }
        )
    cards.append(
        _make_kit_card(
            card_id="kit-cfb-national-title",
            variant="scoreboard_grid",
            kicker="SPORTS · COLLEGE FOOTBALL",
            common_headline="College Football Playoff and SEC Championship leaders",
            stat_caption="Georgia leads the college football national championship at 34%, with SEC contenders across the same board",
            source_count=2,
            route_slug="college-football-national-championship",
            footnote="Shaded cells show served chances across both title races.",
            disclosure="2 other markets in this set are not drawn here.",
            data={
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
    cards.append(
        _make_kit_card(
            card_id="kit-middle-east-deadlines",
            variant="dated_tiles",
            kicker="GEOPOLITICS · MIDDLE EAST",
            common_headline="Middle East ceasefire and leadership timelines",
            stat_caption="US x Iran effective ceasefire reaches 81% by December 31, while Iran leadership change climbs to 24% by June 30",
            source_count=2,
            route_slug="middle-east-deadlines",
            disclosure="4 other markets in this set are not drawn here.",
            data={
                "aligned": True,
                "columns": [
                    {"key": "2026-11-30", "label": "Nov 30 '26"},
                    {"key": "2026-12-31", "label": "Dec 31 '26"},
                    {"key": "2027-06-30", "label": "Jun 30 '27"},
                ],
                "rows": [
                    {
                        "name": "US x Iran Effective Ceasefire begins",
                        "image_url": us_url,
                        "image_kind": us_kind,
                        "cells": {"2026-11-30": 66, "2026-12-31": 81, "2027-06-30": None},
                    },
                    {
                        "name": "Iran leadership change",
                        "image_url": ir_url,
                        "image_kind": ir_kind,
                        "cells": {"2026-11-30": 1, "2026-12-31": 7, "2027-06-30": 24},
                    },
                ],
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
    cards.append(
        _make_kit_card(
            card_id="kit-by-december-31",
            variant="countdown",
            kicker="SAME DEADLINE",
            common_headline="By December 31",
            stat_caption="Next Claude Opus (5.6+) release leads December 31 deadlines at 85%",
            source_count=2,
            route_slug="by-december-31",
            data={
                "days_left": 38,
                "deadline_label": "all of these end on Dec 31",
                "rows": [
                    {
                        "name": "Next Claude Opus (5.6+) released?",
                        "p": 85,
                        "image_url": ai_url,
                        "image_kind": ai_kind,
                    },
                    {
                        "name": "Will any AI model reach a Chatbot Arena score of at least 1550?",
                        "p": 42,
                        "image_url": dc_url,
                        "image_kind": dc_kind,
                    },
                    {
                        "name": "Will France pass a national budget?",
                        "p": 42,
                        "image_url": fr_url,
                        "image_kind": fr_kind,
                    },
                    {
                        "name": "Will Banksy create a new mural or street artwork?",
                        "p": 31,
                        "image_url": pop_url,
                        "image_kind": pop_kind,
                    },
                    {
                        "name": "Pete Hegseth out as Secretary of Defense?",
                        "p": 11,
                        "image_url": ph_url,
                        "image_kind": ph_kind,
                    },
                    {
                        "name": "X banned in any European country?",
                        "p": 8,
                        "image_url": em_url,
                        "image_kind": em_kind,
                    },
                ],
            },
        )
    )

    # 4. stack / road_ahead — Boston Celtics: next 3 games (rd-37)
    bos_url, _ = _team_logo("Boston Celtics")
    wsh_url, _ = _team_logo("Washington Wizards")
    atl_url, _ = _team_logo("Atlanta Hawks")
    sa_url, _ = _team_logo("San Antonio Spurs")
    cards.append(
        _make_kit_card(
            card_id="kit-boston-celtics-road",
            variant="road_ahead",
            kicker="NBA · NEXT 3 GAMES",
            common_headline="Boston Celtics: next 3 games",
            stat_caption="Boston opens at 79% in Washington before hosting Atlanta at 62% and visiting San Antonio at 40%",
            source_count=4,
            route_kind="team",
            route_slug="boston-celtics",
            data={
                "team_name": "Boston Celtics",
                "team_abbr": "BOS",
                "team_color": "#008348",
                "team_image_url": bos_url,
                "rows": [
                    {
                        "opponent_name": "Washington Wizards",
                        "opponent_abbr": "WSH",
                        "opponent_color": "#e31837",
                        "opponent_image_url": wsh_url,
                        "home_or_away": "at",
                        "day": "Tue Nov 24",
                        "clock": "5:00 PM PT",
                        "team_p": 79,
                    },
                    {
                        "opponent_name": "Atlanta Hawks",
                        "opponent_abbr": "ATL",
                        "opponent_color": "#c8102e",
                        "opponent_image_url": atl_url,
                        "home_or_away": "vs",
                        "day": "Fri Nov 27",
                        "clock": "5:00 PM PT",
                        "team_p": 62,
                    },
                    {
                        "opponent_name": "San Antonio Spurs",
                        "opponent_abbr": "SA",
                        "opponent_color": "#000000",
                        "opponent_image_url": sa_url,
                        "home_or_away": "at",
                        "day": "Sun Nov 29",
                        "clock": "1:00 PM PT",
                        "team_p": 40,
                    },
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
    nhl_points = []
    lanes_x: list[float] = []
    for team_name, abbr, p_val, color in sorted(nhl_raw, key=lambda x: (x[2], x[1])):
        in_doubt = 25 < p_val < 75
        lane = None
        if in_doubt:
            for idx_lane, last_p in enumerate(lanes_x):
                if p_val - last_p >= 6:
                    lane = idx_lane
                    lanes_x[idx_lane] = float(p_val)
                    break
            if lane is None:
                lane = len(lanes_x)
                lanes_x.append(float(p_val))
        logo_url, _ = _team_logo(team_name)
        nhl_points.append(
            {
                "name": team_name,
                "abbr": abbr,
                "p": p_val,
                "lane": lane,
                "in_doubt": in_doubt,
                "color": color,
                "image_url": logo_url,
            }
        )
    doubt_labels = [
        f"{pt['abbr']} {pt['p']}%"
        for pt in sorted((p for p in nhl_points if p["in_doubt"]), key=lambda x: -x["p"])
    ]
    cards.append(
        _make_kit_card(
            card_id="kit-nhl-playoffs-bubble",
            variant="bubble_line",
            kicker="HOCKEY · NHL PLAYOFFS",
            common_headline="2026–27 NHL Playoffs picture",
            stat_caption="Edmonton leads at 98%, while Washington (54%) and the Rangers (47%) sit inside the playoff bubble",
            source_count=2,
            route_slug="nhl-playoffs-2027",
            data={
                "band_low": 25,
                "band_high": 75,
                "band_label": "in doubt",
                "low_count": sum(1 for pt in nhl_points if pt["p"] <= 25),
                "high_count": sum(1 for pt in nhl_points if pt["p"] >= 75),
                "points": nhl_points,
                "doubt_summary": " · ".join(doubt_labels),
            },
        )
    )

    # 6. stack / one_in_n — Elon Musk's wildest side quests (rd-01)
    space_url, space_kind = _art_entry("batch3-elon-musk-side-quests")
    sofi_url, sofi_kind = _art_entry("sofi-stadium-super-bowl")
    cards.append(
        _make_kit_card(
            card_id="kit-elon-side-quests",
            variant="one_in_n",
            kicker="ODD · SIDE QUESTS",
            common_headline="Elon Musk's wildest side quests",
            stat_caption="Visiting Mars in his lifetime is the likeliest long shot at 12% (1 in 8), with buying Ryanair at 5% (1 in 20)",
            source_count=2,
            route_slug="elon-musk-wildest-side-quests",
            data={
                "rows": [
                    {
                        "name": "Will Elon Musk visit Mars in his lifetime?",
                        "p": 12,
                        "one_in_n": compute_one_in_n(12),
                        "image_url": space_url,
                        "image_kind": space_kind,
                    },
                    {
                        "name": "Will Elon purchase Ryanair?",
                        "p": 5,
                        "one_in_n": compute_one_in_n(5),
                        "image_url": em_url,
                        "image_kind": em_kind,
                    },
                    {
                        "name": "Next Superman film: Will Elon Musk be cast?",
                        "p": 5,
                        "one_in_n": compute_one_in_n(5),
                        "image_url": em_url,
                        "image_kind": em_kind,
                    },
                    {
                        "name": "Elon Musk out as Tesla CEO before 2027?",
                        "p": 3,
                        "one_in_n": compute_one_in_n(3),
                        "image_url": em_url,
                        "image_kind": em_kind,
                    },
                    {
                        "name": "Tesla Optimus released this year?",
                        "p": 2,
                        "one_in_n": compute_one_in_n(2),
                        "image_url": dc_url,
                        "image_kind": dc_kind,
                    },
                    {
                        "name": "Will Elon Musk buy a major sports team before 2027?",
                        "p": 1,
                        "one_in_n": compute_one_in_n(1),
                        "image_url": sofi_url,
                        "image_kind": sofi_kind,
                    },
                ],
            },
        )
    )

    # 7. stack / single_sport_slate — NBA Slate (rd-02, Rule 6 strictly NBA)
    nba_games = []
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
        nba_games.append(
            {
                "sport_key": "basketball_nba",
                "away": {"name": away_name, "abbr": away_abbr, "color": away_c, "image_url": a_logo, "p": away_p},
                "home": {"name": home_name, "abbr": home_abbr, "color": home_c, "image_url": h_logo, "p": home_p},
                "day": day,
                "clock": clock,
                "status": status,
                "score": score,
            }
        )
    cards.append(
        _make_kit_card(
            card_id="kit-nba-slate",
            variant="single_sport_slate",
            kicker="NBA · THIS SLATE",
            common_headline="Tonight's NBA Slate",
            stat_caption="Pistons at Magic (54%–46%) headlines seven NBA matchups",
            source_count=4,
            route_slug="nba-slate",
            disclosure="6 other markets in this set are not drawn here.",
            data={
                "sport_key": "basketball_nba",
                "league_label": "NBA",
                "rows": nba_games,
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
            raise AssertionError(f"Worked example {card.get('variant')} failed validation: {errs}")

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
