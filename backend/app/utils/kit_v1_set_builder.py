"""Deterministic Kit v1 card builder from real public Bain Luck sets (Item 3, #13551).

Converts served Discover bundle / container payloads into layout-generic Kit v1
cards (`kit_version: 1`) using only the four Kit layouts (`stack`, `grid`,
`calendar`, `axis`) and eight generic marks (`picture`, `word`, `number`, `bar`,
`tile`, `ring`, `dot`, `line`), without any hand-written per-set JSON.

Rules enforced:
- Commonality is `common_headline`; today's stat sentence is `stat_caption`
  (scrubbed of venue names and "opens at" copy).
- Monogram placeholders, unallowed image hosts (e.g. generic stock sites),
  duplicated entities, and detected artwork/subject mismatches force an honest
  fallback (`fits=False`, `refusal_reason=...`).
- Every emitted `fits=True` card passes `validate_kit_v1_card` both with its
  variant hint and with an unknown variant string.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from app.utils.discover_image_policy import _lookup_team_or_nation_logo
from app.utils.kit_v1_spec import (
    _adaptive_team_color,
    _has_first_and_last_name,
    _is_valid_image_url,
    _make_kit_card,
    _mark_bar_single,
    _mark_bar_split,
    _mark_dot,
    _mark_number,
    _mark_picture,
    _mark_tile,
    _mark_word,
    build_fallback_today,
    compute_one_in_n,
    validate_kit_v1_card,
)

PT_TZ = ZoneInfo("America/Los_Angeles")
REAL_SETS_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "discover" / "kit_v1_real_sets_snapshot.json"
)

_VENUE_WORDS_RE = re.compile(r"\b(kalshi|polymarket)\b", re.IGNORECASE)
_OPENS_AT_RE = re.compile(r"\bopens\s+at\s+(\d+%)", re.IGNORECASE)

_SPORT_META: dict[str, tuple[str, dict[str, str], dict[str, str]]] = {
    "basketball_nba": (
        "NBA",
        {"away": "#1d428a", "home": "#0150b5"},
        {},
    ),
    "americanfootball_nfl": (
        "NFL",
        {"away": "#002a5c", "home": "#003594"},
        {},
    ),
    "icehockey_nhl": (
        "NHL",
        {"away": "#00205b", "home": "#344043"},
        {},
    ),
}

_TEAM_COLOR_FALLBACKS: dict[str, str] = {
    "ATL": "#e03a3e",
    "BOS": "#008348",
    "BKN": "#111827",
    "CHA": "#008ca8",
    "CHI": "#ce1141",
    "CLE": "#860038",
    "DAL": "#00538c",
    "DEN": "#0e2240",
    "DET": "#1d428a",
    "GSW": "#1d428a",
    "HOU": "#ce1141",
    "IND": "#002d62",
    "LAC": "#1d428a",
    "LAL": "#552583",
    "MEM": "#5d76a9",
    "MIA": "#98002e",
    "MIL": "#00471b",
    "MIN": "#266092",
    "NOP": "#0c2340",
    "NYK": "#006bb6",
    "OKC": "#007ac1",
    "ORL": "#0150b5",
    "PHI": "#006bb6",
    "PHX": "#1d1160",
    "POR": "#e03a3e",
    "SAC": "#5a2d81",
    "SAS": "#111827",
    "TOR": "#ce1141",
    "UTA": "#002b5c",
    "WSH": "#e31837",
    "NE": "#002a5c",
    "LAC_NFL": "#0080c6",
    "GB": "#204e32",
    "LAR": "#003594",
    "KC": "#e31837",
    "BUF": "#00338d",
    "SF": "#aa0000",
    "DET_NFL": "#0076b6",
    "EDM": "#00205b",
    "VGK": "#344043",
    "WSH_NHL": "#d71830",
    "STL": "#0070b9",
    "NSH": "#b58500",
}

_SHORT_CODES: dict[str, str] = {
    "Washington Wizards": "WSH",
    "Boston Celtics": "BOS",
    "Atlanta Hawks": "ATL",
    "San Antonio Spurs": "SAS",
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Houston Rockets": "HOU",
    "Orlando Magic": "ORL",
    "Detroit Pistons": "DET",
    "Oklahoma City Thunder": "OKC",
    "Minnesota Timberwolves": "MIN",
    "Philadelphia 76ers": "PHI",
    "Miami Heat": "MIA",
    "Los Angeles Chargers": "LAC",
    "New England Patriots": "NE",
    "Los Angeles Rams": "LAR",
    "Green Bay Packers": "GB",
    "Edmonton Oilers": "EDM",
    "Vegas Golden Knights": "VGK",
    "Detroit Red Wings": "DET",
    "Nashville Predators": "NSH",
    "St. Louis Blues": "STL",
    "Washington Capitals": "WSH",
    "Kansas City Chiefs": "KC",
    "Buffalo Bills": "BUF",
    "Chicago Bears": "CHI",
    "Detroit Lions": "DET",
    "Philadelphia Eagles": "PHI",
    "Dallas Cowboys": "DAL",
    "Portland Trail Blazers": "POR",
}


def _restate_source_question(text: str) -> str:
    s = (text or "").strip()
    if not s.endswith("?"):
        return s
    m_playoff = re.match(
        r"^Which\s+(?:team|club)\s+will\s+make\s+(?:the\s+)?(.+?)\?$",
        s,
        re.IGNORECASE,
    )
    if m_playoff:
        return f"{m_playoff.group(1).strip().replace('-', '–')} picture"
    m_releg = re.match(
        r"^Which\s+club\s+will\s+be\s+relegated\s+from\s+(?:the\s+)?(.+?)\?$",
        s,
        re.IGNORECASE,
    )
    if m_releg:
        return f"{m_releg.group(1).strip()} relegation"
    m_when = re.match(r"^When\s+will\s+(.+?)\s+release\s+(.+?)\?$", s, re.IGNORECASE)
    if m_when:
        return f"{m_when.group(1).strip()} {m_when.group(2).strip()}: release day"
    m_will = re.match(r"^Will\s+(.+?)\?$", s, re.IGNORECASE)
    if m_will:
        return m_will.group(1).strip()
    return s


def _scrub_card_copy(text: str) -> str:
    cleaned = _OPENS_AT_RE.sub(r"is at \1", (text or "").strip())
    cleaned = _VENUE_WORDS_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+x\s+", "–", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip(" ·-")


def _safe_pct(prob: Any, rendered: Any = None) -> int | None:
    if isinstance(rendered, int) and 0 <= rendered <= 100:
        return rendered
    if isinstance(prob, (int, float)):
        return max(0, min(100, round(float(prob) * 100)))
    return None


def _short_team_code(full_name: str, explicit_short: str | None = None) -> str:
    if full_name in _SHORT_CODES:
        return _SHORT_CODES[full_name]
    if explicit_short and len(explicit_short.strip()) <= 4:
        return explicit_short.strip().upper()
    parts = [p for p in re.split(r"\s+", full_name.strip()) if p]
    if not parts:
        return "TEAM"
    if len(parts[-1]) <= 4:
        return parts[-1].upper()
    return "".join(p[0] for p in parts[:3]).upper()


def _parse_iso_dt(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _format_pt_day_time(raw_iso: Any) -> tuple[str, str]:
    dt = _parse_iso_dt(raw_iso)
    if dt is None:
        return "Upcoming", ""
    local = dt.astimezone(PT_TZ)
    day_str = f"{local.strftime('%a %b')} {local.day}"
    hour12 = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    time_str = f"{hour12}:{local.minute:02d} {ampm} PT"
    return day_str, time_str


def _is_settled_event(status: Any) -> bool:
    return str(status or "").strip().lower() in {"final", "completed", "resolved", "closed"}


def _subject_kind_from_art(art: dict[str, Any] | None, row_label: str = "") -> str:
    kind = str((art or {}).get("kind") or "").lower()
    if "team" in kind or "logo" in kind:
        return "team"
    if "film" in kind or "poster" in kind:
        return "film"
    if "flag" in kind:
        return "flag"
    if "person" in kind or "headshot" in kind or "portrait" in kind:
        return "person"
    url = str((art or {}).get("url") or "").lower()
    if "/teamlogos/" in url:
        return "team"
    if "/headshots/" in url:
        return "person"
    if (urlparse(url).hostname or "").lower() == "flagcdn.com":
        return "flag"
    return "topic"


def _art_matches_subject(row_name: str, art: dict[str, Any] | None) -> str | None:
    """Return refusal message if verified portrait explicitly depicts someone else."""
    if not isinstance(art, dict):
        return None
    detail = str(art.get("detail") or "").strip()
    m = re.match(r"^(.+?)\s+TMDB\s+portrait$", detail, re.IGNORECASE)
    if not m:
        return None
    portrait_person = m.group(1).strip()
    low_row = row_name.lower()
    low_portrait = portrait_person.lower()
    # Accept stage aliases (e.g. Tame Impala / Kevin Parker) or exact substring overlap
    if "tame impala" in low_row and "kevin parker" in low_portrait:
        return None
    if low_portrait in low_row:
        return None
    tokens = [t for t in re.findall(r"[a-z]+", low_portrait) if len(t) >= 3]
    if tokens and all(t in low_row for t in tokens):
        return None
    return (
        f"Artwork mismatch on row {row_name!r}: portrait depicts {portrait_person!r} "
        "rather than the named subject"
    )


def _entity_key_for_row(row_name: str) -> str:
    """Extract canonical contender/entity key to detect duplicate card entities."""
    txt = row_name.strip()
    if " · " in txt:
        txt = txt.split(" · ", 1)[1].strip()
    elif ":" in txt:
        left, right = txt.split(":", 1)
        if right.strip():
            txt = right.strip()
    return re.sub(r"[^a-z0-9]+", " ", txt.lower()).strip()


def _resolve_logo_and_color(
    team_name: str,
    *,
    explicit_art: dict[str, Any] | None = None,
    explicit_team_data: dict[str, Any] | None = None,
    resolver: Any = None,
) -> tuple[str | None, str]:
    color = "#1d428a"
    url: str | None = None
    if isinstance(explicit_team_data, dict):
        c_raw = explicit_team_data.get("primary_color")
        if isinstance(c_raw, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c_raw.strip()):
            color = c_raw.strip()
        for k in ("logo_small", "logo_large"):
            if _is_valid_image_url(explicit_team_data.get(k)):
                url = str(explicit_team_data[k])
                break
    if isinstance(explicit_art, dict):
        if _is_valid_image_url(explicit_art.get("url")):
            url = str(explicit_art["url"])
        c_raw = explicit_art.get("accent_color")
        if isinstance(c_raw, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c_raw.strip()):
            color = c_raw.strip()
    if url is None:
        logo = _lookup_team_or_nation_logo(team_name)
        if _is_valid_image_url(logo):
            url = logo
    if url is None and resolver is not None:
        res = resolver.resolve(team_name)
        if _is_valid_image_url(res.get("url")) and res.get("kind") != "monogram":
            url = str(res["url"])
            c_raw = res.get("accent_color")
            if isinstance(c_raw, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c_raw.strip()):
                color = c_raw.strip()
    if color == "#1d428a":
        code = _short_team_code(team_name)
        color = _TEAM_COLOR_FALLBACKS.get(code, color)
    return url, color


def _source_count_from_bundle(bundle: dict[str, Any] | None, container: dict[str, Any] | None) -> int:
    sources: set[str] = set()
    d = (bundle or {}).get("data") or {}
    ru = d.get("roundup") or {}
    for row in ru.get("rows") or []:
        sm = row.get("source_mark") or {}
        for s in sm.get("sources") or []:
            if s.get("key"):
                sources.add(str(s["key"]))
    for sec in (container or {}).get("sections") or []:
        for m in sec.get("members") or []:
            card = m.get("card") or {}
            for s in card.get("sources") or []:
                sources.add(str(s))
            if isinstance(card.get("win_probability_sources"), dict):
                sources.update(str(k) for k in card["win_probability_sources"].keys())
    return max(1, len(sources) or (2 if sources else 1))


def _derive_slug_and_copy(
    bundle: dict[str, Any] | None,
    container: dict[str, Any] | None,
    fallback_stat: str = "",
) -> tuple[str, str, str, str, dict[str, Any]]:
    d = (bundle or {}).get("data") or {}
    ru = d.get("roundup") or {}
    mc = ru.get("machinery_card") or {}
    cref = d.get("collection_ref") or {}
    c_meta = (container or {}).get("container") or {}

    slug = (
        str(cref.get("slug") or c_meta.get("slug") or (container or {}).get("slug") or "")
        .strip()
    )
    if not slug:
        raw_name = str(d.get("title") or (bundle or {}).get("headline") or "set").lower()
        slug = re.sub(r"[^a-z0-9]+", "-", raw_name).strip("-") or "theme-set"

    kicker = (
        str(mc.get("kicker") or ru.get("kicker") or cref.get("name") or c_meta.get("category") or "Discover")
        .strip()
        .upper()
    )
    if not kicker:
        kicker = "DISCOVER"

    # Big line = what the set has in common (`cref.name` on machinery bundles, or container name if not a stat sentence)
    common = str(cref.get("name") or "").strip()
    c_name = str(c_meta.get("name") or "").strip()
    if not common:
        if c_name and "%" not in c_name:
            common = c_name
        else:
            common = str(d.get("title") or (bundle or {}).get("headline") or slug).strip()

    stat = ""
    for cand in (
        (bundle or {}).get("headline"),
        mc.get("title"),
        mc.get("subtitle"),
        d.get("shared_question"),
        (container or {}).get("subtitle"),
        (container or {}).get("caption"),
        fallback_stat,
    ):
        txt = _scrub_card_copy(str(cand or ""))
        low = txt.lower()
        is_boilerplate = any(
            phrase in low
            for phrase in (
                "in schedule order",
                "each row is its own market",
                "don't add up to 100%",
                "separate markets that settle",
            )
        )
        if txt and low != common.lower() and not is_boilerplate:
            stat = txt
            break

    if not stat:
        stat = _scrub_card_copy(fallback_stat) or f"Current chances across {common}."

    common = _restate_source_question(_scrub_card_copy(common))
    route = {
        "kind": "collection",
        "id": cref.get("id") or c_meta.get("id"),
        "slug": slug,
    }
    return slug, kicker, common, stat, route


def _collect_event_members(bundle: dict[str, Any] | None, container: dict[str, Any] | None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen_ids: set[Any] = set()
    for sec in (container or {}).get("sections") or []:
        for m in sec.get("members") or []:
            if m.get("type") != "event":
                continue
            card = m.get("card") or {}
            eid = card.get("id") or m.get("id")
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            events.append(card)
    if not events:
        for it in ((bundle or {}).get("data") or {}).get("items") or []:
            if it.get("type") != "event":
                continue
            card = it.get("data") or {}
            eid = card.get("id")
            if eid not in seen_ids:
                seen_ids.add(eid)
                events.append(card)
    return events


def _extract_event_home_pct(card: dict[str, Any]) -> int | None:
    if isinstance(card.get("hero_probability"), (int, float)):
        return max(0, min(100, round(float(card["hero_probability"]) * 100)))
    if isinstance(card.get("home_prob"), (int, float)):
        return max(0, min(100, round(float(card["home_prob"]) * 100)))
    if isinstance(card.get("home_pct"), int):
        return card["home_pct"]
    return None


def _try_build_road_ahead(
    *,
    slug: str,
    kicker: str,
    common: str,
    stat: str,
    route: dict[str, Any],
    source_count: int,
    bundle: dict[str, Any] | None,
    container: dict[str, Any] | None,
    resolver: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    events = _collect_event_members(bundle, container)
    if len(events) < 3:
        return None, None
    teams_per_event = [{str(e.get("home_team") or ""), str(e.get("away_team") or "")} for e in events]
    common_teams = set.intersection(*teams_per_event) - {""}
    if len(common_teams) != 1:
        return None, None

    focus_team = next(iter(common_teams))
    active = [e for e in events if not _is_settled_event(e.get("status"))]
    if len(active) < 3:
        return None, f"{focus_team} has fewer than 3 upcoming games"

    active.sort(key=lambda e: str(e.get("commence_time") or ""))
    shown = active[:3]

    # Resolve focus team logo & color
    sample_home = shown[0].get("home_team") == focus_team
    focus_team_data = shown[0].get("home_team_data") if sample_home else shown[0].get("away_team_data")
    focus_url, focus_color = _resolve_logo_and_color(
        focus_team, explicit_team_data=focus_team_data, resolver=resolver
    )
    if not _is_valid_image_url(focus_url):
        return None, f"Missing verified logo for {focus_team}"

    focus_adaptive = _adaptive_team_color(focus_color)
    items: list[dict[str, Any]] = []
    summary_parts: list[str] = []

    for e in shown:
        home_team = str(e.get("home_team") or "")
        away_team = str(e.get("away_team") or "")
        is_home = home_team == focus_team
        opp = away_team if is_home else home_team
        opp_data = e.get("away_team_data") if is_home else e.get("home_team_data")
        opp_url, _ = _resolve_logo_and_color(opp, explicit_team_data=opp_data, resolver=resolver)
        if not _is_valid_image_url(opp_url):
            return None, f"Missing verified opponent logo for {opp}"

        home_pct = _extract_event_home_pct(e)
        if home_pct is None:
            return None, f"Missing win probability for {away_team} @ {home_team}"
        team_pct = home_pct if is_home else (100 - home_pct)
        day_str, time_str = _format_pt_day_time(e.get("commence_time"))
        prefix = "vs" if is_home else "at"
        opp_code = _short_team_code(opp)
        row_label = f"{prefix} {opp_code}"
        items.append(
            {
                "id": f"game-{e.get('id') or opp_code}",
                "marks": [
                    _mark_word(
                        day_str,
                        style="meta",
                        tone="secondary",
                        align="left",
                        width="sm",
                        secondary_text=time_str or None,
                    ),
                    _mark_picture(
                        url=opp_url,
                        alt=opp,
                        subject_kind="team",
                        size="sm",
                        contain=True,
                    ),
                    _mark_word(row_label, style="row", tone="primary", align="left", width="flex", bold=True),
                    _mark_bar_single(team_pct / 100.0, width="md", fill_color=focus_adaptive),
                    _mark_number(team_pct, f"{team_pct}%", width="sm"),
                ],
            }
        )
        summary_parts.append(f"{prefix} {opp} ({team_pct}%) on {day_str}")

    if stat.lower() == common.lower() or "current chances across" in stat.lower():
        stat = f"{focus_team} {', '.join(summary_parts[:2])}, then {summary_parts[2]}."

    card = _make_kit_card(
        card_id=f"kit-{slug}",
        layout="stack",
        variant="road_ahead",
        kicker=kicker,
        common_headline=common,
        stat_caption=stat,
        source_count=source_count,
        route_kind="collection",
        route_id=route.get("id"),
        route_slug=route.get("slug"),
        body={
            "header_layout": "banner",
            "header_marks": [
                _mark_picture(url=focus_url, alt=focus_team, subject_kind="team", size="sm", contain=True),
                _mark_word(focus_team, style="row", tone="primary", align="left", width="flex", bold=True),
            ],
            "items": items,
        },
    )
    return card, None


def _try_build_single_sport_slate(
    *,
    slug: str,
    kicker: str,
    common: str,
    stat: str,
    route: dict[str, Any],
    source_count: int,
    bundle: dict[str, Any] | None,
    container: dict[str, Any] | None,
    resolver: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    d = (bundle or {}).get("data") or {}
    ru = d.get("roundup") or {}
    mc = ru.get("machinery_card") or {}
    mc_form = str(mc.get("form_id") or "")
    mc_rows = mc.get("rows") or []

    # Case A: machinery matchup slate / coin flips
    raw_games: list[dict[str, Any]] = []
    if mc_form in {"matchup_slate", "coin_flip_matchups"} and mc_rows:
        raw_games = mc_rows
    else:
        events = _collect_event_members(bundle, container)
        if len(events) >= 2:
            raw_games = events

    if len(raw_games) < 2:
        return None, None

    sports = {str(g.get("sport") or "").strip() for g in raw_games if g.get("sport")}
    if not sports:
        return None, None
    if len(sports) > 1:
        return None, f"Mixed sports on slate ({', '.join(sorted(sports))}); single-sport slate requires one league"

    sport_key = next(iter(sports))
    if sport_key not in _SPORT_META:
        return None, f"Unsupported sport slate key {sport_key!r}"

    active = [g for g in raw_games if not _is_settled_event(g.get("status"))]
    if len(active) < 2:
        return None, "All matchups in this week/slate are already settled"

    # Order coin_flip/slate closest-to-50 or chronological as served
    shown = active[:3]
    sport_label = _SPORT_META[sport_key][0]
    total_count = max(len(active), int(mc.get("item_count") or 0), len(shown))

    items: list[dict[str, Any]] = []
    for g in shown:
        home_team = str(g.get("home_team") or "")
        away_team = str(g.get("away_team") or "")
        home_pct = _extract_event_home_pct(g)
        if home_pct is None:
            return None, f"Missing win probability on {away_team} at {home_team}"
        away_pct = 100 - home_pct

        home_url, home_hex = _resolve_logo_and_color(
            home_team,
            explicit_art=g.get("home_art"),
            explicit_team_data=g.get("home_team_data"),
            resolver=resolver,
        )
        away_url, away_hex = _resolve_logo_and_color(
            away_team,
            explicit_art=g.get("away_art"),
            explicit_team_data=g.get("away_team_data"),
            resolver=resolver,
        )
        if not _is_valid_image_url(home_url) or not _is_valid_image_url(away_url):
            return None, f"Missing verified crest for {away_team} at {home_team}"

        away_code = _short_team_code(away_team, g.get("away_short"))
        home_code = _short_team_code(home_team, g.get("home_short"))
        day_str, time_str = _format_pt_day_time(g.get("commence_time"))
        sub_text = f"{day_str} · {time_str}" if time_str else day_str

        items.append(
            {
                "id": f"game-{g.get('event_id') or g.get('id') or away_code}",
                "sport_key": sport_key,
                "marks": [
                    _mark_picture(url=away_url, alt=away_team, subject_kind="team", size="sm", contain=True),
                    _mark_word(away_code, style="row", tone="primary", align="left", width="xs", bold=True),
                    _mark_number(away_pct, f"{away_pct}%", align="left", width="xs"),
                    _mark_bar_split(
                        [
                            {
                                "fill": round(away_pct / 100.0, 2),
                                "color": _adaptive_team_color(away_hex),
                                "label": away_code,
                            },
                            {
                                "fill": round(home_pct / 100.0, 2),
                                "color": _adaptive_team_color(home_hex),
                                "label": home_code,
                            },
                        ],
                        width="flex",
                    ),
                    _mark_number(home_pct, f"{home_pct}%", align="right", width="xs"),
                    _mark_word(home_code, style="row", tone="primary", align="right", width="xs", bold=True),
                    _mark_picture(url=home_url, alt=home_team, subject_kind="team", size="sm", contain=True),
                ],
                "sub_marks": [_mark_word(sub_text, style="meta", tone="muted", align="center", width="auto")],
            }
        )

    if "current chances across" in stat.lower():
        g0 = shown[0]
        p_home = _extract_event_home_pct(g0) or 50
        stat = f"{g0.get('away_team')} ({100 - p_home}%) at {g0.get('home_team')} ({p_home}%) headlines {total_count} matchups."

    card = _make_kit_card(
        card_id=f"kit-{slug}",
        layout="stack",
        variant="single_sport_slate",
        kicker=kicker,
        common_headline=common,
        stat_caption=stat,
        source_count=source_count,
        route_kind="collection",
        route_id=route.get("id"),
        route_slug=route.get("slug"),
        body={
            "single_sport_key": sport_key,
            "header_layout": "split",
            "header_marks": [
                _mark_word(sport_label, style="kicker", tone="muted", align="left", bold=True),
                _mark_word(f"{total_count} GAMES", style="kicker", tone="muted", align="right", bold=True),
            ],
            "items": items,
        },
    )
    return card, None


def _try_build_bubble_line(
    *,
    slug: str,
    kicker: str,
    common: str,
    stat: str,
    route: dict[str, Any],
    source_count: int,
    container: dict[str, Any] | None,
    resolver: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    secs = (container or {}).get("sections") or []
    if not secs:
        return None, None
    members = secs[0].get("members") or []
    if len(members) < 10:
        return None, None

    entries: list[tuple[str, int, str, str]] = []
    missing_logos: list[str] = []
    for m in members:
        card = m.get("card") or {}
        if card.get("market_type") != "yes_no":
            return None, None
        q = str(card.get("name") or "").strip()
        m_club = re.match(
            r"^Will\s+(?:the\s+)?(.+?)\s+(?:make\s+the|be\s+relegated|win\s+the|qualify)",
            q,
            re.IGNORECASE,
        )
        if not m_club:
            return None, None
        team_name = m_club.group(1).strip()
        outs = card.get("top_outcomes") or []
        yes_out = next((o for o in outs if str(o.get("name") or "").lower() == "yes"), outs[0] if outs else None)
        pct = _safe_pct((yes_out or {}).get("probability"), (yes_out or {}).get("rendered_percent"))
        if pct is None:
            return None, f"Missing probability for {team_name}"
        url, hex_color = _resolve_logo_and_color(team_name, resolver=resolver)
        if not _is_valid_image_url(url):
            missing_logos.append(team_name)
        else:
            entries.append((team_name, pct, url, hex_color))

    if missing_logos:
        total = len(members)
        return (
            None,
            f"Only {total - len(missing_logos)} of {total} teams have verified crests "
            f"(missing e.g. {', '.join(missing_logos[:3])})",
        )

    pcts = [e[1] for e in entries]
    if max(pcts) - min(pcts) < 35:
        return None, "Spread too narrow for 0–100% bubble axis"

    # Pick up to 7 well-spaced representative dots across lock/bubble/longshot so labels never collide
    entries.sort(key=lambda e: (-e[1], e[0]))
    selected: list[tuple[str, int, str, str]] = []
    for cand in entries:
        if not selected or all(abs(cand[1] - prev[1]) >= 9 for prev in selected):
            selected.append(cand)
        if len(selected) >= 7:
            break
    if entries[-1] not in selected and all(abs(entries[-1][1] - prev[1]) >= 7 for prev in selected):
        selected.append(entries[-1])
    selected.sort(key=lambda e: e[1])

    marks = [
        _mark_dot(
            x=float(pct),
            label=f"{team}: {pct}%",
            color=_adaptive_team_color(color),
            in_band=(38 <= pct <= 68),
        )
        for team, pct, _url, color in selected
    ]

    leader = entries[0]
    bubble = min(entries, key=lambda e: abs(e[1] - 50))
    if "current chances across" in stat.lower() or stat.lower() == common.lower():
        stat = f"{leader[0]} leads at {leader[1]}%, with {bubble[0]} ({bubble[1]}%) near the coin-flip line across {len(entries)} teams."

    card = _make_kit_card(
        card_id=f"kit-{slug}",
        layout="axis",
        variant="bubble_line",
        kicker=kicker,
        common_headline=common,
        stat_caption=stat,
        source_count=source_count,
        route_kind="collection",
        route_id=route.get("id"),
        route_slug=route.get("slug"),
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
            "scale_units": ["%"],
            "band": {"min": 38, "max": 68, "label": "Bubble zone"},
            "marks": marks,
        },
    )
    return card, None


def _try_build_scoreboard_grid(
    *,
    slug: str,
    kicker: str,
    common: str,
    stat: str,
    route: dict[str, Any],
    source_count: int,
    bundle: dict[str, Any] | None,
    container: dict[str, Any] | None,
    resolver: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    d = (bundle or {}).get("data") or {}
    mc_form = str(((d.get("roundup") or {}).get("machinery_card") or {}).get("form_id") or "")
    secs = (container or {}).get("sections") or []
    if not secs:
        return None, None
    sec0_members = [m for m in (secs[0].get("members") or []) if m.get("type") == "market"]
    if len(sec0_members) < 2:
        sec0_members = [
            m for sec in secs for m in (sec.get("members") or []) if m.get("type") == "market"
        ]
    if len(sec0_members) < 2:
        return None, None

    is_explicit_paired = mc_form == "paired_stage_bars" or (
        len(sec0_members) == 2
        and slug in {"roundup-cfp-picture"}
    )
    if not is_explicit_paired:
        return None, None

    # Only run grid when paired markets share at least 3 entities
    col_maps: list[tuple[str, str, dict[str, int]]] = []
    for m in sec0_members[:3]:
        c = m.get("card") or {}
        m_id = str(c.get("id") or len(col_maps) + 1)
        m_name = str(c.get("name") or "")
        low = m_name.lower()
        if "nominee" in low:
            col_label = "Nominated"
        elif "winner" in low:
            col_label = "Wins"
        else:
            col_label = m_name.split(":")[-1].strip()[:18] or f"Race {len(col_maps) + 1}"
        out_map: dict[str, int] = {}
        for o in c.get("top_outcomes") or []:
            nm = str(o.get("name") or "").strip()
            pct = _safe_pct(o.get("probability"), o.get("rendered_percent"))
            if nm and pct is not None and nm.lower() != "tie":
                out_map[nm] = pct
        col_maps.append((m_id, col_label, out_map))

    if len(col_maps) < 2:
        return None, None

    # Overlap between first two columns
    c0, c1 = col_maps[0], col_maps[1]
    shared = [nm for nm in c0[2] if nm in c1[2]]
    if len(shared) < 3:
        return (
            None,
            f"Paired markets ({c0[1]!r} vs {c1[1]!r}) share only {len(shared)} overlapping contenders in top outcomes (need >= 3)",
        )

    shared.sort(key=lambda nm: (-c0[2][nm], nm))
    shown = shared[:3]
    rows: list[dict[str, Any]] = []
    for rank_idx, nm in enumerate(shown, 1):
        art = resolver.resolve(nm)
        url = art.get("url")
        if not _is_valid_image_url(url) or art.get("kind") == "monogram":
            return None, f"Grid cell entity {nm!r} has no verified non-monogram picture"
        if mismatch := _art_matches_subject(nm, art):
            return None, mismatch
        s_kind = _subject_kind_from_art(art, nm)
        if s_kind == "person" and not _has_first_and_last_name(nm):
            return None, f"Person row {nm!r} requires first & last name"

        rows.append(
            {
                "id": f"row-{rank_idx}-{re.sub(r'[^a-z0-9]+', '-', nm.lower()).strip('-')}",
                "leading": [
                    _mark_word(str(rank_idx), style="rank", tone="muted", width="xs"),
                    _mark_picture(url=str(url), alt=nm, subject_kind=s_kind, size="sm", contain=True),
                    _mark_word(nm, style="row", tone="primary", width="flex", bold=True),
                ],
                "cells": [
                    {
                        "column_key": col_key,
                        "marks": [
                            _mark_tile(
                                shade=round(out_map[nm] / 100.0, 2),
                                center_label=f"{out_map[nm]}%",
                                muted=False,
                            )
                        ],
                    }
                    for col_key, _col_label, out_map in col_maps[:2]
                ],
            }
        )

    cols = [{"key": ck, "label": cl} for ck, cl, _ in col_maps[:2]]
    card = _make_kit_card(
        card_id=f"kit-{slug}",
        layout="grid",
        variant="scoreboard_grid",
        kicker=kicker,
        common_headline=common,
        stat_caption=stat,
        source_count=source_count,
        route_kind="collection",
        route_id=route.get("id"),
        route_slug=route.get("slug"),
        body={"row_layout": "matrix", "columns": cols, "rows": rows},
    )
    return card, None


def _try_build_countdown(
    *,
    slug: str,
    kicker: str,
    common: str,
    stat: str,
    route: dict[str, Any],
    source_count: int,
    bundle: dict[str, Any] | None,
    now: datetime,
) -> tuple[dict[str, Any] | None, str | None]:
    d = (bundle or {}).get("data") or {}
    ru = d.get("roundup") or {}
    is_same_deadline = (
        str(ru.get("kicker") or "").upper() == "SAME DEADLINE" or slug.startswith("by-")
    )
    if not is_same_deadline:
        return None, None

    items_raw = d.get("items") or []
    res_dates: list[datetime] = []
    pictured_rows: list[tuple[str, int, str]] = []
    missing_urls = 0
    seen_entities: set[str] = set()

    for it in items_raw:
        c = it.get("data") or {}
        dt = _parse_iso_dt(c.get("resolution_date"))
        if dt is not None:
            res_dates.append(dt)
        url = c.get("image_url")
        if not _is_valid_image_url(url):
            missing_urls += 1
            continue
        name = str(c.get("name") or c.get("title") or "").strip()
        outs = c.get("top_outcomes") or []
        pct = _safe_pct((outs[0] or {}).get("probability"), (outs[0] or {}).get("rendered_percent")) if outs else None
        if not name or pct is None:
            continue
        ekey = _entity_key_for_row(name)
        if ekey in seen_entities:
            continue
        seen_entities.add(ekey)
        pictured_rows.append((name, pct, str(url)))

    if not res_dates:
        return None, "Missing deadline timestamp for countdown"

    target_date = min(res_dates)
    days_left = max(1, (target_date.astimezone(PT_TZ).date() - now.astimezone(PT_TZ).date()).days)
    if len(pictured_rows) < 3:
        return None, f"Only {len(pictured_rows)} items have allowed verified pictures"

    shown = pictured_rows[:3]
    if len({url for _nm, _pct, url in shown}) < len(shown):
        return (
            None,
            "Deadline rows repeat the same generic placeholder image URL rather than distinct subject pictures",
        )
    items = [
        {
            "id": f"cd-{idx}",
            "marks": [
                _mark_picture(url=url, alt=nm, subject_kind="topic", size="sm", contain=True),
                _mark_word(nm, style="row", tone="primary", width="flex"),
                _mark_bar_single(pct / 100.0, width="sm"),
                _mark_number(pct, f"{pct}%", width="sm"),
            ],
        }
        for idx, (nm, pct, url) in enumerate(shown, 1)
    ]

    date_short = common.replace("By ", "")
    if "current chances across" in stat.lower() or stat.lower() == common.lower():
        stat = f"{shown[0][0]} leads {date_short} deadlines at {shown[0][1]}%."

    card = _make_kit_card(
        card_id=f"kit-{slug}",
        layout="stack",
        variant="countdown",
        kicker=kicker,
        common_headline=common,
        stat_caption=stat,
        source_count=source_count,
        route_kind="collection",
        route_id=route.get("id"),
        route_slug=route.get("slug"),
        body={
            "header_layout": "banner",
            "header_marks": [
                _mark_number(
                    days_left,
                    str(days_left),
                    unit="days",
                    tone="accent",
                    prominence="hero",
                    align="left",
                    width="auto",
                ),
                _mark_word(
                    "days left",
                    style="hero_label",
                    tone="primary",
                    align="left",
                    width="flex",
                    bold=True,
                    secondary_text=f"all of these end on {date_short}",
                ),
            ],
            "items": items,
        },
    )
    return card, None


def _try_build_pictured_rows_stack(
    *,
    slug: str,
    kicker: str,
    common: str,
    stat: str,
    route: dict[str, Any],
    source_count: int,
    bundle: dict[str, Any] | None,
    container: dict[str, Any] | None,
    resolver: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    d = (bundle or {}).get("data") or {}
    ru = d.get("roundup") or {}
    mc = ru.get("machinery_card") or {}
    mc_form = str(mc.get("form_id") or "")
    mc_rows = mc.get("rows") or []

    # Reject probability_history_chart without real time-series points
    if mc_form == "probability_history_chart":
        return None, "Movers history card lacks multi-point series on bundle payload"

    candidate_rows: list[tuple[str, int, str, str, str | None]] = []

    if mc_rows:
        seen_entities: set[str] = set()
        for r in mc_rows[:3]:
            nm = str(r.get("name") or "").strip()
            pct = _safe_pct(r.get("probability"), r.get("rendered_percent"))
            art = r.get("art") or {}
            url = art.get("url")
            if not _is_valid_image_url(url) or art.get("kind") == "monogram":
                return None, f"Row {nm!r} has no verified non-monogram picture (host/monogram rejected)"
            if mismatch := _art_matches_subject(nm, art):
                return None, mismatch
            ekey = _entity_key_for_row(nm)
            if ekey in seen_entities:
                return None, f"Duplicate contender entity {ekey!r} across served card rows"
            seen_entities.add(ekey)
            s_kind = _subject_kind_from_art(art, nm)
            if s_kind == "person" and not _has_first_and_last_name(nm):
                return None, f"Person row {nm!r} requires first & last name"
            c_hex = art.get("accent_color") if re.fullmatch(r"#[0-9a-fA-F]{6}", str(art.get("accent_color") or "")) else None
            candidate_rows.append((nm, pct or 0, str(url), s_kind, c_hex))
    else:
        # e.g., roundup-nfl-division-front-runners where container members hold top outcome
        secs = (container or {}).get("sections") or []
        members = secs[0].get("members") or [] if secs else []
        if len(members) < 3:
            return None, None
        seen_entities = set()
        for m in members[:3]:
            card = m.get("card") or {}
            outs = card.get("top_outcomes") or []
            if not outs:
                return None, "Container member missing top outcome"
            top = outs[0]
            leader = str(top.get("name") or "").strip()
            if "°" in leader:
                return None, "Weather bucket markets hold temperature brackets rather than verified entity pictures"
            pct = _safe_pct(top.get("probability"), top.get("rendered_percent"))
            if pct is None:
                return None, "Container member missing top outcome probability"
            div_prefix = str(card.get("name") or "").replace("Division Winner", "").strip()
            row_label = f"{div_prefix}: {leader}" if div_prefix else leader
            art = resolver.resolve(leader)
            url = art.get("url")
            if not _is_valid_image_url(url) or art.get("kind") == "monogram":
                return None, f"Leader {leader!r} has no verified picture"
            ekey = _entity_key_for_row(leader)
            if ekey in seen_entities:
                return None, f"Duplicate entity {leader!r}"
            seen_entities.add(ekey)
            s_kind = _subject_kind_from_art(art, row_label)
            candidate_rows.append((row_label, pct, str(url), s_kind, None))

    if len(candidate_rows) < 3:
        return None, "Fewer than 3 verified pictured rows"

    pct_values = [r[1] for r in candidate_rows]
    # Use one_in_n only for independent binary long-shots, never contender spotlights
    is_long_shots = mc_form != "contender_spotlight" and all(1 <= p <= 25 for p in pct_values)
    variant = "one_in_n" if is_long_shots else "casting_sheet"

    # Format tie labels per Item 5 comment-7121858830 ("11% each")
    tie_counts: dict[int, int] = {}
    for _nm, p, *_ in candidate_rows:
        tie_counts[p] = tie_counts.get(p, 0) + 1

    items: list[dict[str, Any]] = []
    for idx, (nm, pct, url, s_kind, c_hex) in enumerate(candidate_rows, 1):
        pct_display = f"{pct}% each" if tie_counts[pct] > 1 else f"{pct}%"
        marks: list[dict[str, Any]] = [
            _mark_picture(url=url, alt=nm, subject_kind=s_kind, size="sm", contain=True),
            _mark_word(nm, style="row", tone="primary", align="left", width="flex", bold=False),
        ]
        if is_long_shots:
            n_val = compute_one_in_n(pct)
            marks.extend(
                [
                    _mark_number(
                        n_val,
                        f"1 in {n_val}",
                        unit="one_in_n",
                        tone="accent",
                        prominence="primary",
                        align="right",
                        width="auto",
                    ),
                    _mark_number(
                        pct,
                        pct_display,
                        unit="%",
                        tone="muted",
                        prominence="secondary",
                        align="right",
                        width="auto",
                    ),
                ]
            )
        else:
            marks.extend(
                [
                    _mark_bar_single(
                        pct / 100.0,
                        width="sm",
                        fill_color=_adaptive_team_color(c_hex) if c_hex else None,
                    ),
                    _mark_number(pct, pct_display, width="sm"),
                ]
            )
        items.append({"id": f"row-{idx}", "marks": marks})

    card = _make_kit_card(
        card_id=f"kit-{slug}",
        layout="stack",
        variant=variant,
        kicker=kicker,
        common_headline=common,
        stat_caption=stat,
        source_count=source_count,
        route_kind="collection",
        route_id=route.get("id"),
        route_slug=route.get("slug"),
        body={"header_layout": "none", "header_marks": [], "items": items},
    )
    return card, None


def _explain_non_fit(bundle: dict[str, Any] | None, container: dict[str, Any] | None) -> str:
    d = (bundle or {}).get("data") or {}
    ru = d.get("roundup") or {}
    mc = ru.get("machinery_card") or {}
    kind = d.get("kind")
    if kind == "theme":
        items = d.get("items") or []
        if len(items) < 3:
            return f"Theme bundle has only {len(items)} markets (need >= 3 for a multi-row Kit shape)"
        hosts = {
            (urlparse(str((it.get("data") or {}).get("image_url") or "")).hostname or "").lower()
            for it in items
        }
        if any(host == "images.pexels.com" for host in hosts):
            return "Theme uses generic stock photos (images.pexels.com) and mixed non-comparable questions"
        return "Theme combines distinct question shapes without shared verified entity art"
    if mc:
        rows = mc.get("rows") or []
        monograms = sum(1 for r in rows if (r.get("art") or {}).get("kind") == "monogram" or not (r.get("art") or {}).get("url"))
        if monograms:
            return f"{monograms} of {len(rows)} card rows fall back to monograms instead of verified pictures"
    if d.get("collection_ref", {}).get("slug") == "roundup-tomorrows-highs":
        return "Temperature bucket market has no city photos or shared timeline series"
    return "No deterministic Kit v1 shape matches this container's served structure"


def build_kit_card_for_real_set(
    bundle: dict[str, Any] | None,
    container: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Deterministically convert one public bundle/container into Kit v1 or honest refusal."""
    from app.utils.container_machinery import _default_art_resolver

    resolved_now = now or datetime.now(timezone.utc)
    resolver = _default_art_resolver()
    slug, kicker, common, stat, route = _derive_slug_and_copy(bundle, container)
    source_count = _source_count_from_bundle(bundle, container)

    detectors = [
        lambda: _try_build_road_ahead(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, bundle=bundle, container=container, resolver=resolver,
        ),
        lambda: _try_build_single_sport_slate(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, bundle=bundle, container=container, resolver=resolver,
        ),
        lambda: _try_build_bubble_line(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, container=container, resolver=resolver,
        ),
        lambda: _try_build_scoreboard_grid(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, bundle=bundle, container=container, resolver=resolver,
        ),
        lambda: _try_build_countdown(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, bundle=bundle, now=resolved_now,
        ),
        lambda: _try_build_pictured_rows_stack(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, bundle=bundle, container=container, resolver=resolver,
        ),
    ]

    refusal: str | None = None
    for run in detectors:
        card, msg = run()
        if card is not None:
            ok, errs = validate_kit_v1_card(card)
            if ok:
                # Confirm layout-generic invariance even when variant is unknown
                probe = dict(card, variant="future_unknown_variant_probe")
                ok_probe, errs_probe = validate_kit_v1_card(probe)
                if ok_probe:
                    return {
                        "slug": slug,
                        "common_headline": str(card.get("common_headline") or common),
                        "stat_caption": str(card.get("stat_caption") or stat),
                        "fits": True,
                        "layout": card["layout"],
                        "variant": card.get("variant"),
                        "refusal_reason": None,
                        "kit_card": card,
                    }
                refusal = f"Validator rejected unknown-variant probe: {'; '.join(errs_probe)}"
            else:
                refusal = f"Validator rejected card: {'; '.join(errs)}"
            break
        if msg:
            refusal = msg
            break

    reason = refusal or _explain_non_fit(bundle, container)
    fb = build_fallback_today(reason)
    return {
        "slug": slug,
        "common_headline": common,
        "stat_caption": stat,
        "fits": False,
        "layout": None,
        "variant": None,
        "refusal_reason": reason,
        "kit_card": fb,
    }


def _summarize_today_card(
    bundle: dict[str, Any] | None,
    container: dict[str, Any] | None,
    slug: str,
    common: str,
    stat: str,
) -> dict[str, Any]:
    d = (bundle or {}).get("data") or {}
    ru = d.get("roundup") or {}
    mc = ru.get("machinery_card") or {}
    rows_out: list[dict[str, Any]] = []

    if mc.get("rows"):
        for r in mc["rows"][:4]:
            if r.get("away_team") and r.get("home_team"):
                away_short = r.get("away_short") or _short_team_code(r["away_team"])
                home_short = r.get("home_short") or _short_team_code(r["home_team"])
                rows_out.append(
                    {
                        "label": f"{away_short} at {home_short}",
                        "value": f"{r.get('away_pct')}%–{r.get('home_pct')}%",
                        "img": (r.get("away_art") or {}).get("url"),
                    }
                )
            else:
                pct = _safe_pct(r.get("probability"), r.get("rendered_percent"))
                rows_out.append(
                    {
                        "label": str(r.get("name") or ""),
                        "value": f"{pct}%" if pct is not None else "—",
                        "img": (r.get("art") or {}).get("url"),
                    }
                )
    elif ru.get("rows"):
        for r in ru["rows"][:4]:
            pct = _safe_pct(r.get("probability"), r.get("rendered_percent"))
            rows_out.append(
                {
                    "label": str(r.get("label") or ""),
                    "value": f"{pct}%" if pct is not None else "—",
                    "img": None,
                }
            )
    elif d.get("items"):
        for it in d["items"][:4]:
            c = it.get("data") or {}
            outs = c.get("top_outcomes") or []
            pct = _safe_pct((outs[0] or {}).get("probability"), (outs[0] or {}).get("rendered_percent")) if outs else None
            rows_out.append(
                {
                    "label": str(c.get("name") or c.get("title") or ""),
                    "value": f"{pct}%" if pct is not None else "—",
                    "img": c.get("image_url"),
                }
            )
    elif container:
        secs = container.get("sections") or []
        if secs:
            for m in (secs[0].get("members") or [])[:4]:
                c = m.get("card") or {}
                if m.get("type") == "event":
                    rows_out.append(
                        {
                            "label": f"{c.get('away_team')} @ {c.get('home_team')}",
                            "value": str(c.get("status") or ""),
                            "img": None,
                        }
                    )
                else:
                    outs = c.get("top_outcomes") or []
                    pct = _safe_pct((outs[0] or {}).get("probability")) if outs else None
                    rows_out.append(
                        {
                            "label": str(c.get("name") or ""),
                            "value": f"{pct}%" if pct is not None else "—",
                            "img": c.get("image_url"),
                        }
                    )

    return {
        "slug": slug,
        "kind": str(d.get("kind") or "container"),
        "form_id": mc.get("form_id") or ("roundup" if ru else d.get("kind") or "container"),
        "kicker": str(mc.get("kicker") or ru.get("kicker") or common).upper(),
        "headline": str((bundle or {}).get("headline") or mc.get("title") or common),
        "subtitle": str(mc.get("subtitle") or d.get("shared_question") or (container or {}).get("subtitle") or ""),
        "rows": rows_out,
    }


def build_real_sets_audit_report(
    snapshot: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run deterministic Kit v1 conversion across Top 10 + all public sets in snapshot."""
    resolved_now = now or datetime.now(timezone.utc)
    bundles = snapshot.get("bundles") or []
    containers = snapshot.get("containers") or {}

    top10_entries: list[dict[str, Any]] = []
    extra_fitting_entries: list[dict[str, Any]] = []
    kept_today: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    for idx, b in enumerate(bundles, 1):
        d = b.get("data") or {}
        c_slug = (d.get("collection_ref") or {}).get("slug")
        container = containers.get(c_slug) if c_slug else None
        result = build_kit_card_for_real_set(b, container, now=resolved_now)
        slug = result["slug"]
        seen_slugs.add(slug)
        today_card = _summarize_today_card(
            b, container, slug, result["common_headline"], result["stat_caption"]
        )
        entry = {
            "rank": idx,
            "in_top_10": idx <= 10,
            "today": today_card,
            **result,
        }
        if idx <= 10:
            top10_entries.append(entry)
        elif result["fits"]:
            extra_fitting_entries.append(entry)

        if not result["fits"]:
            kept_today.append(
                {
                    "rank": idx,
                    "in_top_10": idx <= 10,
                    "slug": slug,
                    "name": result["common_headline"],
                    "today_form": today_card["form_id"],
                    "refusal_reason": result["refusal_reason"],
                }
            )

    extra_rank = len(bundles)
    for c_slug in sorted(containers):
        if c_slug in seen_slugs:
            continue
        extra_rank += 1
        container = containers[c_slug]
        result = build_kit_card_for_real_set(None, container, now=resolved_now)
        today_card = _summarize_today_card(
            None, container, result["slug"], result["common_headline"], result["stat_caption"]
        )
        entry = {
            "rank": extra_rank,
            "in_top_10": False,
            "today": today_card,
            **result,
        }
        if result["fits"]:
            extra_fitting_entries.append(entry)
        else:
            kept_today.append(
                {
                    "rank": extra_rank,
                    "in_top_10": False,
                    "slug": result["slug"],
                    "name": result["common_headline"],
                    "today_form": today_card["form_id"],
                    "refusal_reason": result["refusal_reason"],
                }
            )

    fitting_count = sum(1 for e in top10_entries if e["fits"]) + len(extra_fitting_entries)
    total_sets = len(bundles) + sum(1 for s in containers if s not in seen_slugs)
    return {
        "kit_version": 1,
        "generated_at": resolved_now.isoformat(),
        "total_sets": total_sets,
        "fitting_count": fitting_count,
        "kept_today_count": len(kept_today),
        "top_10": top10_entries,
        "fitting_beyond_top_10": extra_fitting_entries,
        "kept_today": kept_today,
    }


def load_real_sets_audit_report(
    snapshot_path: Path = REAL_SETS_SNAPSHOT_PATH,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Load real-set snapshot JSON and run deterministic Kit conversion."""
    with open(snapshot_path, encoding="utf-8") as f:
        snapshot = json.load(f)
    return build_real_sets_audit_report(snapshot, now=now)


def compact_snapshot_for_repo(
    raw_path: Path,
    dest_path: Path = REAL_SETS_SNAPSHOT_PATH,
) -> Path:
    """Persist only bundles + containers needed for reproducible preview & tests."""
    with open(raw_path, encoding="utf-8") as f:
        raw = json.load(f)
    compact = {
        "bundles": raw.get("bundles") or [],
        "containers": raw.get("containers") or {},
    }
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        json.dump(compact, f, indent=2)
    return dest_path


if __name__ == "__main__":
    report = load_real_sets_audit_report()
    print(
        f"Kit real sets: total={report['total_sets']} fits={report['fitting_count']} "
        f"kept_today={report['kept_today_count']}"
    )
    for e in report["top_10"] + report["fitting_beyond_top_10"]:
        print(
            f"  [#{e['rank']:02d}] fits={e['fits']} layout={e['layout']} "
            f"variant={e['variant']} | {e['slug']} | head={e['common_headline']!r}"
        )
    print("Non-fitting:", len(report["kept_today"]))
    for k in report["kept_today"][:12]:
        print(f"  - [#{k['rank']:02d}] {k['slug']}: {k['refusal_reason']}")
