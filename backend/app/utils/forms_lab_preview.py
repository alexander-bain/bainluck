"""Admin-only preview payload builder for Forms Lab Batch 1 (#13551).

Strictly isolated from public Discover cards and public container payloads until Alex grades
each look in the blind forms deck (#13550). Every card runs pre-draw truth checks first
and falls back cleanly to plain rows (``status == "refused_fallback_rows"``) on failure.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from app.utils.container_machinery import SubjectArtResolver, _default_art_resolver
from app.utils.forms_lab_truth import (
    TruthCheckResult,
    check_ladder_monotonic,
    check_no_computed_number,
    check_no_price_floor,
    check_one_date_per_family,
    check_one_unit_per_axis,
    check_one_winner_adds_to_100,
    check_ties_handled,
    evaluate_truth_checks,
)
from app.utils.member_art_13551 import (
    resolve_member_art,
    team_conference,
    team_short_code,
)

BATCH1_LOOK_ORDER: tuple[str, ...] = (
    "grid_of_cells",
    "one_axis",
    "calendar_strip",
    "casting_sheet",
    "bubble_and_cut",
)


def _format_pct(pct: float) -> str:
    val = round(float(pct), 1)
    if abs(val - round(val)) < 0.05:
        return f"{int(round(val))}%"
    return f"{val:.1f}%"


def _build_envelope(
    *,
    card_id: str,
    look_id: str,
    form_variant: str,
    topic: str,
    title: str,
    subtitle: str,
    footnote: str,
    source_label: str,
    truth_checks: Sequence[TruthCheckResult],
    body: dict[str, Any],
    fallback_rows: list[dict[str, Any]],
    is_refusal_demo: bool = False,
) -> dict[str, Any]:
    passed, reasons, check_dicts = evaluate_truth_checks(truth_checks)
    return {
        "card_id": card_id,
        "look_id": look_id,
        "form_variant": form_variant,
        "preview_only": True,
        "is_refusal_demo": is_refusal_demo,
        "topic": topic,
        "title": title,
        "subtitle": subtitle,
        "footnote": footnote,
        "source_label": source_label,
        "status": "draw" if passed else "refused_fallback_rows",
        "refusal_reasons": reasons,
        "truth_checks": check_dicts,
        "body": body if passed else {},
        "fallback_rows": fallback_rows,
    }


def _fb_row(
    label: str,
    pct: float,
    art: dict[str, Any],
    *,
    role: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "short_label": art.get("short_label") or label,
        "role": role,
        "pct": round(float(pct), 1),
        "pct_label": _format_pct(pct),
        "art": art,
    }


# ---------------------------------------------------------------------------
# Item 3: Grid of cells (Places grid + Scoreboard grid)
# ---------------------------------------------------------------------------
def build_places_grid_card(
    resolver: SubjectArtResolver,
    *,
    include_mismatched_nov30_date: bool = False,
) -> dict[str, Any]:
    """Build Places grid: Largest company at end of Dec 2026 (1st, 2nd, 3rd)."""
    dates = ["2026-12-31", "2026-12-31", "2026-11-30" if include_mismatched_nov30_date else "2026-12-31"]
    col_defs = [
        ("first", "1st", [("Apple", 86), ("NVIDIA", 11), ("Microsoft", 1), ("Alphabet", 1)]),
        ("second", "2nd", [("NVIDIA", 79), ("Microsoft", 16), ("Alphabet", 3), ("Apple", 2)]),
        ("third", "3rd", [("Microsoft", 64), ("Alphabet", 18), ("NVIDIA", 13), ("Apple", 2)]),
    ]
    rows_order = ["Apple", "NVIDIA", "Microsoft", "Alphabet"]
    value_map = {col_key: dict(pairs) for col_key, _, pairs in col_defs}

    checks: list[TruthCheckResult] = [
        check_one_date_per_family(dates, family_label="Largest Company places"),
    ]
    for _, col_label, pairs in col_defs:
        checks.append(check_one_winner_adds_to_100([p for _, p in pairs], field_label=f"{col_label} place"))
        checks.append(check_no_price_floor([p for _, p in pairs], field_label=f"{col_label} place"))

    columns = [{"key": k, "label": lbl} for k, lbl, _ in col_defs]
    grid_rows: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []
    for company in rows_order:
        art = resolve_member_art(company, resolver=resolver)
        cells: list[dict[str, Any]] = []
        best_val = max(value_map[k].get(company, 0) for k, _, _ in col_defs)
        for col_key, col_lbl, _ in col_defs:
            val = float(value_map[col_key].get(company, 0))
            cells.append({
                "col_key": col_key,
                "col_label": col_lbl,
                "pct": val,
                "pct_label": _format_pct(val),
                "is_row_peak": val > 0 and val == best_val,
                "listed": company in value_map[col_key],
            })
        grid_rows.append({
            "name": company,
            "short_label": art["short_label"],
            "art": art,
            "cells": cells,
        })
        fallback.append(_fb_row(f"1st: {company}", float(value_map["first"].get(company, 0)), art))

    cid = "places-grid-mixed-date-refusal" if include_mismatched_nov30_date else "places-grid-largest-company"
    title = (
        "Largest company · Mixed Dec 31 & Nov 30 (refused)"
        if include_mismatched_nov30_date
        else "Largest company at the end of 2026"
    )
    return _build_envelope(
        card_id=cid,
        look_id="grid_of_cells",
        form_variant="places_grid",
        topic="Tech & Economics",
        title=title,
        subtitle="Dec 31 market-cap ranks across 1st, 2nd, and 3rd · shared % scale",
        footnote="1st, 2nd, 3rd on Dec 31 (Nov 30 contract refused unless aligned)",
        source_label="Polymarket",
        truth_checks=checks,
        body={"columns": columns, "rows": grid_rows, "highlight_mode": "row_peak"},
        fallback_rows=fallback,
        is_refusal_demo=include_mismatched_nov30_date,
    )


def build_scoreboard_ai_card(
    resolver: SubjectArtResolver,
    *,
    include_unclosed_arena: bool = False,
) -> dict[str, Any]:
    """Build Scoreboard grid for AI model leaderboard (Gemini=Google, Claude=Anthropic, ChatGPT=OpenAI)."""
    if include_unclosed_arena:
        cols = [
            ("overall", "Overall", [("Gemini", 81, "Google"), ("Claude", 13, "Anthropic"), ("ChatGPT", 4, "OpenAI")], 98.0),
            ("coding", "Coding", [("Google", 29, "Google"), ("Anthropic", 51, "Anthropic"), ("OpenAI", 16, "OpenAI")], 102.0),
            ("arena", "1550 Arena", [("Gemini", 28, "Google"), ("Claude", 4, "Anthropic"), ("ChatGPT", 4, "OpenAI")], 41.0),
        ]
    else:
        cols = [
            ("overall", "Overall", [("Gemini", 81, "Google"), ("Claude", 13, "Anthropic"), ("ChatGPT", 4, "OpenAI")], 100.0),
            ("coding", "Coding", [("Google", 29, "Google"), ("Anthropic", 51, "Anthropic"), ("OpenAI", 16, "OpenAI")], 102.0),
            ("t2v", "Text-to-Video", [("Google", 52, "Google"), ("Anthropic", 0, "Anthropic"), ("OpenAI", 7, "OpenAI")], 100.0),
        ]

    checks: list[TruthCheckResult] = [check_one_date_per_family(["2026-12-31"] * len(cols), family_label="AI leaderboard")]
    for _, clabel, _, field_sum in cols:
        checks.append(check_one_winner_adds_to_100([field_sum], field_label=clabel))

    labs = ["Google", "Anthropic", "OpenAI"]
    col_maps: dict[str, dict[str, tuple[float, str]]] = {k: {} for k, _, _, _ in cols}
    for col_key, _, pairs, _ in cols:
        for display_name, pct, canonical in pairs:
            col_maps[col_key][canonical] = (float(pct), display_name)

    rows: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []
    for lab in labs:
        art = resolve_member_art(lab, resolver=resolver)
        cells: list[dict[str, Any]] = []
        col_peaks = {k: max(v[0] for v in col_maps[k].values()) for k in col_maps}
        for col_key, col_label, _, _ in cols:
            pct, alias_label = col_maps[col_key].get(lab, (0.0, lab))
            listed = alias_label and pct > 0
            cells.append({
                "col_key": col_key,
                "col_label": col_label,
                "pct": pct,
                "pct_label": _format_pct(pct) if listed else "—",
                "alias_tag": alias_label if alias_label != lab and listed else None,
                "listed": bool(listed),
                "is_col_peak": pct > 0 and pct == col_peaks[col_key],
            })
        rows.append({"name": lab, "short_label": art["short_label"], "art": art, "cells": cells})
        overall_pct = col_maps["overall"].get(lab, (0.0, lab))[0]
        fallback.append(_fb_row(lab, overall_pct, art))

    cid = "scoreboard-ai-arena-refusal" if include_unclosed_arena else "scoreboard-ai-leaderboard"
    title = (
        "Best AI · Unclosed 41% Arena column (refused)"
        if include_unclosed_arena
        else "AI model leaderboard at year-end"
    )
    return _build_envelope(
        card_id=cid,
        look_id="grid_of_cells",
        form_variant="scoreboard_grid",
        topic="Tech & AI",
        title=title,
        subtitle="Gemini = Google · Claude = Anthropic · ChatGPT = OpenAI · 100%–102% single-winner fields",
        footnote="1550 Text Arena field (41% total) excluded until priced to 100%",
        source_label="Polymarket",
        truth_checks=checks,
        body={"columns": [{"key": k, "label": lbl} for k, lbl, _, _ in cols], "rows": rows, "highlight_mode": "col_peak"},
        fallback_rows=fallback,
        is_refusal_demo=include_unclosed_arena,
    )


def build_scoreboard_nba_card(
    resolver: SubjectArtResolver,
    *,
    include_over_115_scoring: bool = False,
) -> dict[str, Any]:
    """Build NBA Awards Scoreboard grid (MVP/DPOY/MIP/Clutch, refusing 184% Scoring per #11995)."""
    if include_over_115_scoring:
        cols = [
            ("mvp", "MVP", [("Victor Wembanyama", 51), ("Luka Doncic", 29), ("Nikola Jokic", 5), ("Shai Gilgeous-Alexander", 4), ("Giannis Antetokounmpo", 3)], 102.5),
            ("scoring", "Scoring Leader", [("Luka Doncic", 68), ("Shai Gilgeous-Alexander", 61), ("Giannis Antetokounmpo", 55), ("Victor Wembanyama", 0), ("Nikola Jokic", 0)], 184.0),
            ("assists", "Assists Leader", [("Nikola Jokic", 58), ("Luka Doncic", 49), ("Shai Gilgeous-Alexander", 32), ("Victor Wembanyama", 0), ("Giannis Antetokounmpo", 0)], 139.0),
        ]
    else:
        cols = [
            ("mvp", "MVP", [("Victor Wembanyama", 51), ("Luka Doncic", 29), ("Nikola Jokic", 5), ("Shai Gilgeous-Alexander", 4), ("Giannis Antetokounmpo", 3)], 102.5),
            ("dpoy", "DPOY", [("Victor Wembanyama", 59), ("Evan Mobley", 17), ("Chet Holmgren", 11), ("Giannis Antetokounmpo", 4), ("Shai Gilgeous-Alexander", 1)], 100.0),
            ("clutch", "Clutch", [("Shai Gilgeous-Alexander", 26), ("Luka Doncic", 19), ("Nikola Jokic", 15), ("Victor Wembanyama", 11), ("Giannis Antetokounmpo", 7)], 98.0),
        ]

    checks: list[TruthCheckResult] = [check_one_date_per_family(["2026-27"] * len(cols), family_label="NBA 2026-27 Awards")]
    for _, clabel, _, total_sum in cols:
        checks.append(check_one_winner_adds_to_100([total_sum], field_label=f"NBA {clabel}"))

    players = ["Victor Wembanyama", "Luka Doncic", "Nikola Jokic", "Shai Gilgeous-Alexander", "Giannis Antetokounmpo"]
    if not include_over_115_scoring:
        players.append("Evan Mobley")

    col_maps = {k: dict(pairs) for k, _, pairs, _ in cols}
    col_peaks = {k: max((v for v in m.values()), default=0) for k, m in col_maps.items()}

    rows: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []
    for player in players:
        art = resolve_member_art(player, resolver=resolver)
        cells = []
        for col_key, col_label, _, _ in cols:
            pct = float(col_maps[col_key].get(player, 0))
            listed = player in col_maps[col_key] and pct > 0
            cells.append({
                "col_key": col_key,
                "col_label": col_label,
                "pct": pct,
                "pct_label": _format_pct(pct) if listed else "—",
                "listed": listed,
                "is_col_peak": listed and pct == col_peaks[col_key],
            })
        rows.append({"name": player, "short_label": art["short_label"], "art": art, "cells": cells})
        fallback.append(_fb_row(f"MVP · {player}", float(col_maps["mvp"].get(player, 0)), art))

    cid = "scoreboard-nba-184-refusal" if include_over_115_scoring else "scoreboard-nba-awards"
    title = (
        "NBA Awards · Scoring 184% & Assists 139% (#11995 refused)"
        if include_over_115_scoring
        else "NBA 2026-27 major player awards"
    )
    return _build_envelope(
        card_id=cid,
        look_id="grid_of_cells",
        form_variant="scoreboard_grid",
        topic="Sports · Basketball",
        title=title,
        subtitle="Only one-winner award fields (98%–102.5%) shown; 184% Scoring / 139% Assists refused (#11995)",
        footnote="NBA 2026-27 individual awards · verified ESPN NBA portraits",
        source_label="Kalshi · Polymarket",
        truth_checks=checks,
        body={"columns": [{"key": k, "label": lbl} for k, lbl, _, _ in cols], "rows": rows, "highlight_mode": "col_peak"},
        fallback_rows=fallback,
        is_refusal_demo=include_over_115_scoring,
    )


# ---------------------------------------------------------------------------
# Item 4: One axis (Shared scale + Deadline race + The climb)
# ---------------------------------------------------------------------------
def build_shared_scale_card(
    resolver: SubjectArtResolver,
    *,
    mix_incompatible_unit: bool = False,
) -> dict[str, Any]:
    """Build Shared scale card: Avengers: Doomsday vs Dune: Part Three opening weekend ($M)."""
    avengers_art = resolve_member_art("Avengers: Doomsday", resolver=resolver)
    dune_art = resolve_member_art("Dune: Part Three", resolver=resolver)

    avengers_bins = [
        {"label": "<$260M", "lo": 220, "hi": 260, "open_low": True, "open_high": False, "pct": 1.0},
        {"label": "$260M–$300M", "lo": 260, "hi": 300, "open_low": False, "open_high": False, "pct": 1.0},
        {"label": "$300M–$340M", "lo": 300, "hi": 340, "open_low": False, "open_high": False, "pct": 4.0},
        {"label": "$340M–$360M", "lo": 340, "hi": 360, "open_low": False, "open_high": False, "pct": 4.0},
        {"label": "$360M–$400M", "lo": 360, "hi": 400, "open_low": False, "open_high": False, "pct": 15.0},
        {"label": "$400M+", "lo": 400, "hi": 460, "open_low": False, "open_high": True, "pct": 75.0},
    ]
    dune_bins = [
        {"label": "<$70M", "lo": 35, "hi": 70, "open_low": True, "open_high": False, "pct": 7.0},
        {"label": "$70M–$90M", "lo": 70, "hi": 90, "open_low": False, "open_high": False, "pct": 9.0},
        {"label": "$90M–$110M", "lo": 90, "hi": 110, "open_low": False, "open_high": False, "pct": 23.0},
        {"label": "$110M–$130M", "lo": 110, "hi": 130, "open_low": False, "open_high": False, "pct": 40.0},
        {"label": "$130M+", "lo": 130, "hi": 170, "open_low": False, "open_high": True, "pct": 21.0},
    ]
    units = ["$M", "% RT Score"] if mix_incompatible_unit else ["$M", "$M"]
    checks = [
        check_one_unit_per_axis(units, axis_label="Opening weekend axis"),
        check_one_winner_adds_to_100([b["pct"] for b in avengers_bins], field_label="Avengers: Doomsday"),
        check_one_winner_adds_to_100([b["pct"] for b in dune_bins], field_label="Dune: Part Three"),
    ]
    for bins in (avengers_bins, dune_bins):
        for b in bins:
            b["pct_label"] = _format_pct(b["pct"])

    series = [
        {
            "id": "avengers",
            "name": "Avengers: Doomsday",
            "short_label": "Avengers",
            "art": avengers_art,
            "unit": "$M",
            "tone": "accent",
            "peak_label": "$400M+ (75%)",
            "bins": avengers_bins,
        },
        {
            "id": "dune",
            "name": "Dune: Part Three",
            "short_label": "Dune: Part 3",
            "art": dune_art,
            "unit": "$M",
            "tone": "c2",
            "peak_label": "$110M–$130M (40%)",
            "bins": dune_bins,
        },
    ]
    fallback = [
        _fb_row("Avengers: Doomsday ($400M+)", 75.0, avengers_art),
        _fb_row("Dune: Part Three ($110M–$130M)", 40.0, dune_art),
    ]
    cid = "one-axis-shared-scale-unit-refusal" if mix_incompatible_unit else "one-axis-shared-scale-box-office"
    title = (
        "Box office $M vs Rotten Tomatoes % (unit mismatch refused)"
        if mix_incompatible_unit
        else "Opening weekend box office on one $M axis"
    )
    return _build_envelope(
        card_id=cid,
        look_id="one_axis",
        form_variant="shared_scale",
        topic="Entertainment · Box Office",
        title=title,
        subtitle="Avengers: Doomsday vs Dune: Part Three · December 18, 2026 domestic debut ($M)",
        footnote="Shared $0M–$460M scale; open-ended tails show arrows",
        source_label="Kalshi · Polymarket",
        truth_checks=checks,
        body={"axis_min": 0, "axis_max": 460, "axis_unit": "$M", "ticks": [0, 100, 200, 300, 400], "series": series},
        fallback_rows=fallback,
        is_refusal_demo=mix_incompatible_unit,
    )


def build_deadline_race_card(resolver: SubjectArtResolver) -> dict[str, Any]:
    """Build Deadline race card: Next Claude Opus vs Gemini Krypton release dates."""
    anthropic_art = resolve_member_art("Anthropic", resolver=resolver)
    google_art = resolve_member_art("Google", resolver=resolver)

    dates = ["Nov 30", "Dec 15", "Dec 31"]
    opus_pts = [{"date": "Nov 30", "pct": 14.0}, {"date": "Dec 15", "pct": 65.0}, {"date": "Dec 31", "pct": 85.0}]
    krypton_pts = [{"date": "Nov 30", "pct": 10.0}, {"date": "Dec 15", "pct": 47.0}, {"date": "Dec 31", "pct": 57.0}]
    for pts in (opus_pts, krypton_pts):
        for p in pts:
            p["pct_label"] = _format_pct(p["pct"])

    checks = [
        check_one_date_per_family([",".join(dates), ",".join(dates)], family_label="Deadline race dates"),
        check_ladder_monotonic(opus_pts, ladder_label="Next Claude Opus"),
        check_ladder_monotonic(krypton_pts, ladder_label="Gemini Krypton"),
        check_no_price_floor([p["pct"] for p in opus_pts], field_label="Next Claude Opus"),
    ]
    series = [
        {"id": "opus", "name": "Next Claude Opus", "short_label": "Claude Opus", "art": anthropic_art, "tone": "accent", "points": opus_pts},
        {"id": "krypton", "name": "Gemini Krypton", "short_label": "Gemini Krypton", "art": google_art, "tone": "c3", "points": krypton_pts},
    ]
    fallback = [
        _fb_row("Claude Opus by Dec 31", 85.0, anthropic_art),
        _fb_row("Gemini Krypton by Dec 31", 57.0, google_art),
    ]
    return _build_envelope(
        card_id="one-axis-deadline-race-ai",
        look_id="one_axis",
        form_variant="deadline_race",
        topic="Tech · AI Releases",
        title="Next flagship AI release race by Dec 31",
        subtitle="Cumulative odds across Nov 30, Dec 15, and Dec 31 · Anthropic vs Google",
        footnote="Opus crosses 50% by mid-December (65% vs Krypton 47%)",
        source_label="Polymarket",
        truth_checks=checks,
        body={"dates": dates, "ref_line_pct": 50, "crossover_note": "Opus leads by +18% on Dec 15", "series": series},
        fallback_rows=fallback,
    )


def build_the_climb_card(
    resolver: SubjectArtResolver,
    *,
    force_dip_refusal: bool = False,
) -> dict[str, Any]:
    """Build The climb card: AGI / Tesla-SpaceX cumulative timeline on one probability axis."""
    openai_art = resolve_member_art("OpenAI", resolver=resolver)
    apple_art = resolve_member_art("Apple", resolver=resolver)

    raw_steps = [
        ("Jan '27", 5.0),
        ("Apr '27", 11.0),
        ("Jul '27", 21.0),
        ("Oct '27", 34.0),
        ("Jan '28", 49.0),
        ("Apr '28", 62.0),
        ("Jul '28", 52.0 if force_dip_refusal else 62.0),
        ("Jan '29", 70.0),
        ("Jan '31", 76.0),
    ]
    points = [{"date": d, "pct": p, "pct_label": _format_pct(p)} for d, p in raw_steps]
    checks = [
        check_one_unit_per_axis(["% cumulative chance"], axis_label="The climb probability"),
        check_ladder_monotonic(points, ladder_label="When will any company achieve AGI?"),
        check_no_price_floor([p["pct"] for p in points], field_label="AGI climb"),
    ]
    fallback = [
        _fb_row("AGI before Jan 2028", 49.0, openai_art),
        _fb_row("AGI before Jan 2031", 76.0, openai_art),
        _fb_row("Apple iPhone 18 before Apr 2027", 85.0, apple_art),
    ]
    cid = "one-axis-climb-dip-refusal" if force_dip_refusal else "one-axis-the-climb-agi"
    title = (
        "AGI timeline · >3% downward inversion (refused)"
        if force_dip_refusal
        else "When will any company achieve AGI?"
    )
    return _build_envelope(
        card_id=cid,
        look_id="one_axis",
        form_variant="the_climb",
        topic="Tech · Milestones",
        title=title,
        subtitle="Cumulative probability climbs toward 76% by Jan 2031 · 50% threshold marked",
        footnote="Monotonicity check refuses any >3% cumulative drop",
        source_label="Polymarket",
        truth_checks=checks,
        body={"subject": "OpenAI · Industry AGI", "art": openai_art, "ref_line_pct": 50, "points": points},
        fallback_rows=fallback,
        is_refusal_demo=force_dip_refusal,
    )


# ---------------------------------------------------------------------------
# Item 5: Calendar strip (NO per-day computed numbers until Decision 367)
# ---------------------------------------------------------------------------
def build_calendar_strip_card(
    resolver: SubjectArtResolver,
    *,
    attempt_computed_daily_numbers: bool = False,
) -> dict[str, Any]:
    """Build Calendar strip for Spotify 2026 Wrapped (shaded daily tiles ONLY until Decision 367)."""
    spotify_art = resolve_member_art("Spotify", resolver=resolver)
    # Real cumulative rungs from machinery-2026-summed-up (id=109527):
    # Before Nov 27: 3%, Nov 28: 5%, Nov 29: 6%, Nov 30: 11%, Dec 1: 12%, Dec 2: 17%, Dec 3: 84%, Dec 4: 88%, Dec 5: 89%
    rungs = [
        ("Nov 27", "Nov", 27, 3.0, 3.0),
        ("Nov 28", "Nov", 28, 2.0, 5.0),
        ("Nov 29", "Nov", 29, 1.0, 6.0),
        ("Nov 30", "Nov", 30, 5.0, 11.0),
        ("Dec 1", "Dec", 1, 1.0, 12.0),
        ("Dec 2", "Dec", 2, 5.0, 17.0),
        ("Dec 3", "Dec", 3, 67.0, 84.0),
        ("Dec 4", "Dec", 4, 4.0, 88.0),
        ("Dec 5", "Dec", 5, 1.0, 89.0),
    ]
    checks = [
        check_ladder_monotonic([(d, cum) for d, _, _, _, cum in rungs], ladder_label="Spotify Wrapped"),
        check_no_computed_number(has_computed_numbers=attempt_computed_daily_numbers, allowed=False),
        check_no_price_floor([cum for _, _, _, _, cum in rungs], field_label="Spotify Wrapped"),
    ]
    max_delta = max(delta for _, _, _, delta, _ in rungs)
    tiles = []
    for label, month, day_num, delta, _ in rungs:
        intensity = round(min(1.0, max(0.08, delta / max_delta)), 2)
        tiles.append({
            "date_label": label,
            "month": month,
            "day_num": day_num,
            "intensity": intensity,
            "is_peak": delta == max_delta,
            # Strictly null while Decision 367 keeps daily numbers off:
            "daily_number_label": None,
        })
    fallback = [
        _fb_row("Released before Dec 3, 2026", 84.0, spotify_art),
        _fb_row("Released before Dec 4, 2026", 88.0, spotify_art),
        _fb_row("Released before Dec 5, 2026", 89.0, spotify_art),
    ]
    cid = "calendar-strip-decision367-refusal" if attempt_computed_daily_numbers else "calendar-strip-spotify-wrapped"
    title = (
        "Spotify 2026 Wrapped · per-day computed numbers (refused per Decision 367)"
        if attempt_computed_daily_numbers
        else "When will Spotify release 2026 Wrapped?"
    )
    return _build_envelope(
        card_id=cid,
        look_id="calendar_strip",
        form_variant="calendar_strip",
        topic="Entertainment · Music",
        title=title,
        subtitle="Daily release window Nov 27 – Dec 5 · peak day Dec 3 shaded by chance jump (3% before Nov 27 · 89% by Dec 5)",
        footnote="Decision 367 pending: tiles shaded only, no per-day computed numbers printed",
        source_label="Polymarket",
        truth_checks=checks,
        body={
            "art": spotify_art,
            "decision_367_daily_numbers_enabled": False,
            "earlier_label": "3% before Nov 27",
            "later_label": "89% by Dec 5",
            "peak_summary": "Peak window: Dec 3",
            "tiles": tiles,
        },
        fallback_rows=fallback,
        is_refusal_demo=attempt_computed_daily_numbers,
    )


# ---------------------------------------------------------------------------
# Item 6: Casting sheet with pictures (Bond 7 roles + Oscars 2027)
# ---------------------------------------------------------------------------
def _certainty_word(pct: float, *, tied: bool = False) -> str:
    if tied:
        return "Tie"
    if pct >= 60.0:
        return "Strong favorite"
    if pct >= 35.0:
        return "Leading"
    if pct >= 20.0:
        return "Wide open"
    return "Toss-up"


def build_casting_bond_card(
    resolver: SubjectArtResolver,
    *,
    omit_felix_tie_rule: bool = False,
) -> dict[str, Any]:
    """Build Next James Bond 7-role Casting sheet with vetted portraits & Felix Leiter 11%-11% tie rule."""
    roles = [
        ("Theme Song", [("Raye", 42.0), ("Olivia Dean", 24.0), ("Dua Lipa", 14.0)]),
        ("Bond Girl", [("Margaret Qualley", 31.0), ("Florence Pugh", 17.0), ("Anya Taylor-Joy", 15.0)]),
        ("M", [("Olivia Colman", 29.0), ("Ralph Fiennes", 17.0), ("Idris Elba", 15.0)]),
        ("Q", [("Ben Whishaw", 25.0), ("Andrew Scott", 15.0), ("Dev Patel", 10.0)]),
        ("Villain", [("Cillian Murphy", 17.0), ("Oscar Isaac", 14.0), ("Adam Driver", 13.0)]),
        ("Moneypenny", [("Naomie Harris", 12.0), ("Jodie Turner-Smith", 11.0), ("Phoebe Dynevor", 11.0)]),
        ("Felix Leiter", [("Boyd Holbrook", 11.0), ("Anthony Mackie", 11.0), ("Steven Yeun", 9.0)]),
    ]
    checks: list[TruthCheckResult] = [
        check_ties_handled(
            roles[-1][1],
            context_label="Felix Leiter",
            tie_rule=None if omit_felix_tie_rule else "Show both co-leaders side by side with explicit Tie pill (11%–11%)",
        ),
    ]
    rows: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []
    for role_name, candidates in roles:
        lead_name, lead_pct = candidates[0]
        second_name, second_pct = candidates[1]
        is_tie = abs(lead_pct - second_pct) <= 0.15
        art = resolve_member_art(lead_name, resolver=resolver)
        co_leader = (
            {
                "name": second_name,
                "pct": second_pct,
                "pct_label": _format_pct(second_pct),
                "art": resolve_member_art(second_name, resolver=resolver),
            }
            if is_tie
            else None
        )
        rows.append({
            "role": role_name,
            "leader": lead_name,
            "short_label": lead_name if not is_tie else f"{lead_name} / {second_name}",
            "pct": lead_pct,
            "pct_label": f"{_format_pct(lead_pct)}–{_format_pct(second_pct)}" if is_tie else _format_pct(lead_pct),
            "certainty": _certainty_word(lead_pct, tied=is_tie),
            "is_tie": is_tie,
            "art": art,
            "co_leader": co_leader,
        })
        fallback.append(_fb_row(f"{role_name}: {lead_name}", lead_pct, art, role=role_name))

    cid = "casting-sheet-bond-tie-refusal" if omit_felix_tie_rule else "casting-sheet-next-james-bond"
    title = (
        "Next James Bond · Rank-1 tie rule omitted (refused)"
        if omit_felix_tie_rule
        else "Next James Bond · All 7 roles"
    )
    return _build_envelope(
        card_id=cid,
        look_id="casting_sheet",
        form_variant="casting_sheet",
        topic="Entertainment · Film",
        title=title,
        subtitle="7 casting & music roles · verified portraits on every leader · Felix Leiter 11%–11% Tie rule",
        footnote="Explicit Tie badge displays co-leaders Boyd Holbrook & Anthony Mackie at 11%",
        source_label="Kalshi · Polymarket",
        truth_checks=checks,
        body={"rows": rows},
        fallback_rows=fallback,
        is_refusal_demo=omit_felix_tie_rule,
    )


def build_casting_oscars_card(resolver: SubjectArtResolver) -> dict[str, Any]:
    """Build Oscars 2027 Casting sheet with film posters & actor portraits (holds critics-choice-and-oscars-2027)."""
    roles = [
        ("Best Picture", [("The Odyssey", 45.0), ("One Battle After Another", 18.0)], 100.0),
        ("Best Actor", [("John Malkovich", 49.0), ("Andrew Scott", 24.0)], 100.0),
        ("Best Actress", [("Julianne Moore", 85.0), ("Inde Navarrette", 10.0)], 114.0),
        ("Best Director", [("Christopher Nolan", 62.0), ("Denis Villeneuve", 16.0)], 100.0),
        ("Supp. Actor", [("Paul Giamatti", 40.0), ("Andrew Garfield", 37.0)], 100.0),
        ("Supp. Actress", [("Anne Hathaway", 64.0), ("Amanda Seyfried", 26.0)], 100.0),
        ("Orig. Screenplay", [("Wild Horse Nine", 54.0), ("Club Kid", 13.0)], 100.0),
    ]
    checks = [
        check_one_winner_adds_to_100([total], field_label=f"Oscars {role}")
        for role, _, total in roles
    ]
    rows: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []
    for role_name, candidates, _ in roles:
        lead_name, lead_pct = candidates[0]
        art = resolve_member_art(lead_name, resolver=resolver)
        rows.append({
            "role": role_name,
            "leader": lead_name,
            "short_label": lead_name,
            "pct": lead_pct,
            "pct_label": _format_pct(lead_pct),
            "certainty": _certainty_word(lead_pct),
            "is_tie": False,
            "art": art,
            "co_leader": None,
        })
        fallback.append(_fb_row(f"{role_name}: {lead_name}", lead_pct, art, role=role_name))

    return _build_envelope(
        card_id="casting-sheet-oscars-2027",
        look_id="casting_sheet",
        form_variant="casting_sheet",
        topic="Entertainment · Awards",
        title="Oscars 2027 · Lead nominees & winners",
        subtitle="7 Academy Award races · TMDB posters & portraits on every row · holds machinery-critics-choice-and-oscars-2027",
        footnote="All 7 single-winner Oscar markets add cleanly inside 100%–114%",
        source_label="Polymarket",
        truth_checks=checks,
        body={"rows": rows},
        fallback_rows=fallback,
    )


# ---------------------------------------------------------------------------
# Item 7: Bubble line + The cut split by conference (NHL Playoffs)
# ---------------------------------------------------------------------------
_NHL_PLAYOFF_FIELDS: tuple[tuple[str, float], ...] = (
    ("Edmonton Oilers", 98.0),
    ("Minnesota Wild", 98.0),
    ("Carolina Hurricanes", 97.0),
    ("Vegas Golden Knights", 94.0),
    ("Tampa Bay Lightning", 90.0),
    ("Colorado Avalanche", 88.0),
    ("Dallas Stars", 85.0),
    ("New Jersey Devils", 83.0),
    ("Montreal Canadiens", 81.0),
    ("Florida Panthers", 76.0),
    ("Ottawa Senators", 73.0),
    ("Utah Mammoth", 73.0),
    ("Boston Bruins", 69.0),
    ("Washington Capitals", 54.0),
    ("New York Rangers", 47.0),
    ("Nashville Predators", 46.0),
    ("New York Islanders", 43.0),
    ("Anaheim Ducks", 38.0),
    ("St. Louis Blues", 38.0),
    ("Los Angeles Kings", 34.0),
    ("Winnipeg Jets", 34.0),
    ("Seattle Kraken", 33.0),
    ("Buffalo Sabres", 32.0),
    ("San Jose Sharks", 24.0),
    ("Philadelphia Flyers", 18.0),
    ("Columbus Blue Jackets", 14.0),
    ("Calgary Flames", 11.0),
    ("Pittsburgh Penguins", 11.0),
    ("Toronto Maple Leafs", 8.0),
    ("Chicago Blackhawks", 8.0),
    ("Detroit Red Wings", 8.0),
    ("Vancouver Canucks", 6.0),
)


def _hydrate_nhl_teams(resolver: SubjectArtResolver) -> list[dict[str, Any]]:
    teams: list[dict[str, Any]] = []
    for name, pct in _NHL_PLAYOFF_FIELDS:
        art = resolve_member_art(name, sport_key="icehockey_nhl", resolver=resolver)
        conf = team_conference(name, "nhl") or "Unknown"
        teams.append({
            "name": name,
            "code": team_short_code(name),
            "conference": conf,
            "pct": pct,
            "pct_label": _format_pct(pct),
            "art": art,
        })
    return teams


def build_bubble_line_card(resolver: SubjectArtResolver) -> dict[str, Any]:
    """Build NHL Bubble line with all 32 ESPN team logos along a 0%–100% playoff axis."""
    teams = _hydrate_nhl_teams(resolver)
    out_n = sum(1 for t in teams if t["pct"] < 40.0)
    doubt_n = sum(1 for t in teams if 40.0 <= t["pct"] <= 60.0)
    in_n = sum(1 for t in teams if t["pct"] > 60.0)

    checks = [
        check_no_price_floor([t["pct"] for t in teams], field_label="NHL make playoffs"),
        check_one_unit_per_axis(["% playoff chance"], axis_label="NHL playoff probability"),
    ]
    focus_teams = [t for t in teams if t["code"] in {"CAR", "BOS", "WSH", "NYR", "NSH", "NYI", "VAN"}]
    fallback = [_fb_row(t["name"], t["pct"], t["art"]) for t in teams[:6]]
    return _build_envelope(
        card_id="bubble-line-nhl-playoffs",
        look_id="bubble_and_cut",
        form_variant="bubble_line",
        topic="Sports · Hockey",
        title="NHL Playoffs 2027 · The bubble line",
        subtitle=f"{out_n} look out · {doubt_n} in doubt · {in_n} look in (40%–60% bubble shaded)",
        footnote="Every dot carries an ESPN team crest directly on the 0%–100% axis",
        source_label="Kalshi · Polymarket",
        truth_checks=checks,
        body={
            "bubble_low": 40,
            "bubble_high": 60,
            "counts": {"look_out": out_n, "in_doubt": doubt_n, "look_in": in_n},
            "teams": teams,
            "focus_teams": focus_teams,
        },
        fallback_rows=fallback,
    )


def build_the_cut_card(
    resolver: SubjectArtResolver,
    *,
    omit_west_cut_tie_rule: bool = False,
) -> dict[str, Any]:
    """Build The cut split by NHL Conference (Eastern 16->8, Western 16->8) with cut-boundary tie check."""
    teams = _hydrate_nhl_teams(resolver)
    east = sorted([t for t in teams if t["conference"] == "Eastern"], key=lambda x: (-x["pct"], x["name"]))
    west = sorted([t for t in teams if t["conference"] == "Western"], key=lambda x: (-x["pct"], x["name"]))

    def _band_tone(pct: float) -> str:
        if pct >= 75.0:
            return "safe"
        if pct >= 40.0:
            return "bubble"
        if pct >= 18.0:
            return "chase"
        return "longshot"

    conferences_out = []
    checks = [
        check_no_price_floor([t["pct"] for t in teams], field_label="NHL conference cut"),
    ]
    for conf_name, conf_list in (("Eastern", east), ("Western", west)):
        cut_n = 8
        has_cut_tie = len(conf_list) > cut_n and abs(conf_list[cut_n - 1]["pct"] - conf_list[cut_n]["pct"]) <= 0.15
        tie_rule_text = "Tied at 8th cut (38%) — tiebreak decides final berth" if has_cut_tie else None
        checks.append(
            check_ties_handled(
                [(t["name"], t["pct"]) for t in conf_list],
                context_label=f"NHL {conf_name} cut",
                tie_rule="Co-#1 seeds share top row",
                cut_index=cut_n,
                cut_tie_rule=None if (omit_west_cut_tie_rule and conf_name == "Western") else tie_rule_text,
            )
        )
        rows = []
        for idx, t in enumerate(conf_list, start=1):
            rows.append({
                **t,
                "rank": idx,
                "above_cut": idx <= cut_n,
                "at_cut_tie": has_cut_tie and idx in (cut_n, cut_n + 1),
                "likelihood_band": _band_tone(t["pct"]),
            })
        conferences_out.append({
            "conference": conf_name,
            "total_teams": len(conf_list),
            "places": cut_n,
            "cut_label": "8 places",
            "has_cut_tie": has_cut_tie,
            "tie_rule_note": tie_rule_text,
            "teams": rows,
        })

    fallback = [_fb_row(f"{t['conference']} · {t['name']}", t["pct"], t["art"]) for t in east[:4] + west[:4]]
    cid = "the-cut-nhl-tie-refusal" if omit_west_cut_tie_rule else "the-cut-nhl-conferences"
    title = (
        "NHL The Cut · Western #8/#9 38% tie unruled (refused)"
        if omit_west_cut_tie_rule
        else "NHL Playoffs 2027 · The cut by conference"
    )
    return _build_envelope(
        card_id=cid,
        look_id="bubble_and_cut",
        form_variant="the_cut",
        topic="Sports · Hockey",
        title=title,
        subtitle="Eastern (16 -> 8 places) & Western (16 -> 8 places) · Ducks & Blues tied at 38% on Western cut",
        footnote="8 teams advance per conference · dashed cut line at place #8",
        source_label="Kalshi · Polymarket",
        truth_checks=checks,
        body={"conferences": conferences_out},
        fallback_rows=fallback,
        is_refusal_demo=omit_west_cut_tie_rule,
    )


def real_sets_catalog() -> dict[str, list[dict[str, str]]]:
    """Return >=5 verified real market sets across >1 topic for each Batch 1 look."""
    return {
        "grid_of_cells": [
            {"set_name": "Largest company at the end of Dec 2026 (1st / 2nd / 3rd)", "topic": "Tech & Economics", "source_ref": "machinery-ai-and-big-tech-race"},
            {"set_name": "AI model leaderboard 2026 (Overall / Coding / Text-to-Video)", "topic": "Tech & AI", "source_ref": "machinery-ai-model-leaderboard-2026"},
            {"set_name": "NBA 2026-27 major player awards (MVP / DPOY / Clutch)", "topic": "Sports · Basketball", "source_ref": "machinery-big-championships-2027"},
            {"set_name": "Oscars 2027 Nominated vs Winner & Golden Globes 2027", "topic": "Entertainment · Awards", "source_ref": "machinery-oscars-best-picture / machinery-golden-globes-2027"},
            {"set_name": "French Presidential 1st Round (1st / 2nd / 3rd Place)", "topic": "Politics", "source_ref": "benchmark ids 65544793 / 65544791"},
            {"set_name": "Google Year in Search 2026 (People / Athletes / Movies / Actors)", "topic": "Culture", "source_ref": "benchmark ids 60634618–60634622"},
        ],
        "one_axis": [
            {"set_name": "Avengers: Doomsday vs Dune: Part Three opening weekend ($M)", "topic": "Entertainment · Box Office", "source_ref": "machinery-2026-box-office-showdown"},
            {"set_name": "Next Claude Opus vs Gemini Krypton release deadlines (Dates)", "topic": "Tech · AI", "source_ref": "machinery-ai-model-leaderboard-2026"},
            {"set_name": "When will any company achieve AGI? (Cumulative climb)", "topic": "Tech · Milestones", "source_ref": "benchmark id 112835 / machinery-ai-math-and-data-centers"},
            {"set_name": "US vs China 2026 real GDP growth (%)", "topic": "Economics & Geopolitics", "source_ref": "benchmark ids 108594 / 114443"},
            {"set_name": "US–Iran Strait of Hormuz normalization vs peace talks (Dates)", "topic": "Geopolitics", "source_ref": "benchmark ids 19927933 / 58918693"},
            {"set_name": "Avengers vs Dune Rotten Tomatoes scores (%)", "topic": "Entertainment · Reviews", "source_ref": "benchmark ids 5398277 / 5602093"},
        ],
        "calendar_strip": [
            {"set_name": "Spotify 2026 Wrapped release day window (Nov 27 – Dec 5)", "topic": "Entertainment · Music", "source_ref": "machinery-2026-summed-up (id=109527)"},
            {"set_name": "Next Claude Opus 5.6+ daily/biweekly release window", "topic": "Tech · AI", "source_ref": "machinery-ai-model-leaderboard-2026 (id=62134324)"},
            {"set_name": "Federal government shutdown end/duration window", "topic": "Politics", "source_ref": "benchmark ids 109600 / 68056249"},
            {"set_name": "FOMC next rate cut meeting window", "topic": "Economics", "source_ref": "machinery-fed-and-macro (id=113883)"},
            {"set_name": "GTA VI / major 2026 album release windows", "topic": "Entertainment · Gaming", "source_ref": "benchmark id 27594646"},
        ],
        "casting_sheet": [
            {"set_name": "Next James Bond (7 casting & music roles)", "topic": "Entertainment · Film", "source_ref": "machinery-next-james-bond"},
            {"set_name": "Oscars 2027 lead categories (holds machinery-critics-choice-and-oscars-2027)", "topic": "Entertainment · Awards", "source_ref": "machinery-oscars-best-picture / machinery-oscars-best-actor-2027"},
            {"set_name": "Golden Globes 2027 film & television acting winners", "topic": "Entertainment · TV & Film", "source_ref": "machinery-golden-globes-2027"},
            {"set_name": "Grammys 2027 Big Four awards slate", "topic": "Entertainment · Music", "source_ref": "machinery-music-and-grammys-2026"},
            {"set_name": "2028 Presidential / Party nominations & Cabinet exits", "topic": "Politics", "source_ref": "machinery-2028-presidential / id=58495120"},
            {"set_name": "NBA 2026-27 individual awards roster", "topic": "Sports · Basketball", "source_ref": "machinery-big-championships-2027"},
        ],
        "bubble_and_cut": [
            {"set_name": "NHL Playoffs 2027 (32 teams · Eastern 16->8 & Western 16->8)", "topic": "Sports · Hockey", "source_ref": "machinery-nhl-this-week / Stanley Cup field"},
            {"set_name": "NBA Playoffs 2027 (30 teams · Eastern 15->8 & Western 15->8)", "topic": "Sports · Basketball", "source_ref": "machinery-nba-night / machinery-big-championships-2027"},
            {"set_name": "NFL Playoffs 2026-27 (32 teams · AFC 16->7 & NFC 16->7)", "topic": "Sports · Football", "source_ref": "machinery-nfl-conference-and-division-races / id=86832"},
            {"set_name": "Premier League Relegation / Top 4 UCL cut (20 teams -> 3 / 4 places)", "topic": "Sports · Soccer", "source_ref": "machinery-soccer-cups-and-relegation (id=59516509)"},
            {"set_name": "UEFA Champions League 2027 & World Cup qualification cuts", "topic": "Sports · Soccer", "source_ref": "machinery-european-league-titles (id=70732924)"},
            {"set_name": "Oscars 2027 Best Picture top-10 nomination cut", "topic": "Entertainment · Awards", "source_ref": "machinery-oscars-best-picture"},
        ],
    }


def build_forms_lab_batch1_preview(
    *,
    look_filter: Optional[str] = None,
    include_refusal_demos: bool = True,
    team_lookup: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble the complete admin-only Batch 1 preview payload across Items 3–7."""
    resolver = SubjectArtResolver(team_lookup=team_lookup) if team_lookup is not None else _default_art_resolver()
    catalog = real_sets_catalog()

    builders: dict[str, list[dict[str, Any]]] = {
        "grid_of_cells": [
            build_places_grid_card(resolver),
            build_scoreboard_ai_card(resolver),
            build_scoreboard_nba_card(resolver),
        ],
        "one_axis": [
            build_shared_scale_card(resolver),
            build_deadline_race_card(resolver),
            build_the_climb_card(resolver),
        ],
        "calendar_strip": [
            build_calendar_strip_card(resolver),
        ],
        "casting_sheet": [
            build_casting_bond_card(resolver),
            build_casting_oscars_card(resolver),
        ],
        "bubble_and_cut": [
            build_bubble_line_card(resolver),
            build_the_cut_card(resolver),
        ],
    }

    if include_refusal_demos:
        builders["grid_of_cells"].extend([
            build_places_grid_card(resolver, include_mismatched_nov30_date=True),
            build_scoreboard_nba_card(resolver, include_over_115_scoring=True),
        ])
        builders["one_axis"].extend([
            build_shared_scale_card(resolver, mix_incompatible_unit=True),
            build_the_climb_card(resolver, force_dip_refusal=True),
        ])
        builders["calendar_strip"].append(
            build_calendar_strip_card(resolver, attempt_computed_daily_numbers=True)
        )
        builders["casting_sheet"].append(
            build_casting_bond_card(resolver, omit_felix_tie_rule=True)
        )
        builders["bubble_and_cut"].append(
            build_the_cut_card(resolver, omit_west_cut_tie_rule=True)
        )

    selected_looks = [lid for lid in BATCH1_LOOK_ORDER if not look_filter or lid == look_filter]
    looks_out = []
    for lid in selected_looks:
        looks_out.append({
            "look_id": lid,
            "cards": builders[lid],
            "real_sets": catalog[lid],
        })

    return {
        "preview_only": True,
        "public_release": False,
        "decision_367_daily_numbers_enabled": False,
        "look_order": list(BATCH1_LOOK_ORDER),
        "looks": looks_out,
    }
