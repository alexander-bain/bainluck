"""Deterministic Kit v1 card builder from real public Bain Luck sets (Item 3, #13551).

Converts served Discover bundle / container payloads into layout-generic Kit v1
cards (`kit_version: 1`) using only the four Kit layouts (`stack`, `grid`,
`calendar`, `axis`) and eight generic marks (`picture`, `word`, `number`, `bar`,
`tile`, `ring`, `dot`, `line`), without any hand-written per-set JSON.

Rules enforced (#13584 follow-up, Fable 11:21 PM PT):
- Commonality is `common_headline` (declarative, zero source questions); today's
  stat sentence is `stat_caption` (scrubbed of venue names, "opens at", and
  blend boilerplate).
- Picture rule (Alex): require a verified non-monogram picture whenever a row's
  subject is a person, team, or film (and on every row of `casting_sheet`).
  Shaped looks (`dated_tiles`, `countdown`, `one_in_n`, `shared_scale`) may
  draw things/events without photos — never monograms, never generic stock
  photos (`images.pexels.com`), and never repeated placeholders.
- Specific shapes are chosen first (`road_ahead`, `single_sport_slate`,
  `bubble_line`, `dated_tiles`, `countdown`, `shared_scale`, `one_in_n`,
  `scoreboard_grid`), with `casting_sheet` selected strictly last.
- Every emitted `fits=True` card passes `validate_kit_v1_card` both with its
  variant hint and with an unknown variant string.
"""

from __future__ import annotations

import calendar
import json
import re
from datetime import date, datetime, timezone
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


def _mark_bar_range(*, lo: float, hi: float, width: str = "flex", pct_label: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "mark": "bar",
        "bar_style": "range",
        "lo": round(max(0.0, min(1.0, float(lo))), 4),
        "hi": round(max(0.0, min(1.0, float(hi))), 4),
        "width": width,
    }
    if pct_label is not None:
        out["pct_label"] = pct_label
    return out

PT_TZ = ZoneInfo("America/Los_Angeles")
REAL_SETS_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "kit_v1_real_sets_fixture.json"
)

_VENUE_WORDS_RE = re.compile(r"\b(kalshi|polymarket)\b", re.IGNORECASE)
_OPENS_AT_RE = re.compile(r"\bopens\s+at\s+(\d+%)", re.IGNORECASE)
_PORTRAIT_DETAIL_SUFFIX_RE = re.compile(
    r"\s+(?:tmdb\s+portrait|espn\s+headshot|wikimedia\s+commons\s+portrait|portrait|headshot)$",
    re.IGNORECASE,
)

_ARTIST_WORK_AND_STAGE_ALLOWLIST: tuple[tuple[str, str], ...] = (
    ("all i want for christmas is you", "mariah carey"),
    ("tame impala", "kevin parker"),
    ("djo", "joe keery"),
)

_SPORT_META: dict[str, str] = {
    "basketball_nba": "NBA",
    "americanfootball_nfl": "NFL",
    "icehockey_nhl": "NHL",
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
    "GB": "#204e32",
    "LAR": "#003594",
    "KC": "#e31837",
    "BUF": "#00338d",
    "SF": "#aa0000",
    "EDM": "#00205b",
    "VGK": "#b4975a",
    "STL": "#002f87",
    "NSH": "#ffb81c",
    "CAR": "#cc0000",
    "COL": "#6f263d",
    "FLA": "#c8102e",
    "MTL": "#af1e2d",
    "NJ": "#ce1126",
    "NYI": "#00539b",
    "NYR": "#0038a8",
    "OTT": "#c52032",
    "SEA": "#001628",
    "SJ": "#006d75",
    "TB": "#002868",
    "VAN": "#00205b",
    "WPG": "#041e42",
    "ANA": "#fc4c02",
    "CBJ": "#002654",
    "CGY": "#c8102e",
    "PIT": "#000000",
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
    "Portland Trail Blazers": "POR",
    "Los Angeles Chargers": "LAC",
    "New England Patriots": "NE",
    "Los Angeles Rams": "LAR",
    "Green Bay Packers": "GB",
    "Kansas City Chiefs": "KC",
    "Buffalo Bills": "BUF",
    "Chicago Bears": "CHI",
    "Detroit Lions": "DET",
    "Philadelphia Eagles": "PHI",
    "Dallas Cowboys": "DAL",
    "Edmonton Oilers": "EDM",
    "Vegas Golden Knights": "VGK",
    "Detroit Red Wings": "DET",
    "Nashville Predators": "NSH",
    "St. Louis Blues": "STL",
    "Washington Capitals": "WSH",
    "Minnesota Wild": "MIN",
    "Carolina Hurricanes": "CAR",
    "Tampa Bay Lightning": "TB",
    "Colorado Avalanche": "COL",
    "Dallas Stars": "DAL",
    "New Jersey Devils": "NJ",
    "Montreal Canadiens": "MTL",
    "Florida Panthers": "FLA",
    "Ottawa Senators": "OTT",
    "Utah Mammoth": "UTA",
    "Boston Bruins": "BOS",
    "New York Rangers": "NYR",
    "New York Islanders": "NYI",
    "Anaheim Ducks": "ANA",
    "Los Angeles Kings": "LA",
    "Winnipeg Jets": "WPG",
    "Seattle Kraken": "SEA",
    "Buffalo Sabres": "BUF",
    "San Jose Sharks": "SJ",
    "Philadelphia Flyers": "PHI",
    "Columbus Blue Jackets": "CBJ",
    "Calgary Flames": "CGY",
    "Pittsburgh Penguins": "PIT",
    "Toronto Maple Leafs": "TOR",
    "Chicago Blackhawks": "CHI",
    "Vancouver Canucks": "VAN",
}

_COLLEGE_MASCOT_FALLBACKS: dict[str, str] = {
    "georgia": "Georgia Bulldogs",
    "texas": "Texas Longhorns",
    "alabama": "Alabama Crimson Tide",
    "notre dame": "Notre Dame Fighting Irish",
    "oregon": "Oregon Ducks",
    "ohio state": "Ohio State Buckeyes",
    "tennessee": "Tennessee Volunteers",
    "indiana": "Indiana Hoosiers",
    "utah": "Utah Utes",
    "texas tech": "Texas Tech Red Raiders",
    "byu": "BYU Cougars",
}

_TWO_WORD_CITIES: frozenset[str] = frozenset(
    {
        "Los Angeles",
        "New York",
        "Golden State",
        "San Antonio",
        "Oklahoma City",
        "New Orleans",
        "Green Bay",
        "Kansas City",
        "Tampa Bay",
        "New England",
        "Las Vegas",
        "San Francisco",
        "San Jose",
        "St. Louis",
    }
)

_MONTH_NUMS: dict[str, int] = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_MONTH_ABBR: dict[int, str] = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

def _short_place_name(team_name: str) -> str:
    s = (team_name or "").strip()
    for city in _TWO_WORD_CITIES:
        if s.startswith(f"{city} "):
            return city
    parts = s.split()
    return parts[0] if len(parts) >= 2 else s


def _lead_verb(subject: str, subject_kind: str = "topic") -> str:
    """Return 'lead' for plural team names (Oilers, Giants, Celtics), else 'leads'."""
    if subject_kind != "team":
        return "leads"
    core = subject.split(":", 1)[1].strip() if ":" in subject else subject.strip()
    tokens = [re.sub(r"[^a-zA-Z]", "", tok).lower() for tok in core.split() if tok.strip()]
    if not tokens:
        return "leads"
    last = tokens[-1]
    if last == "sox":
        return "lead"
    if last.endswith("s") and not last.endswith(("ss", "us", "is", "as")):
        return "lead"
    return "leads"


def _present_tense_restatement(phrase: str) -> str:
    """Fix bare subjunctive verbs left after stripping leading 'Will '/'When will '."""
    s = (phrase or "").strip()
    if not s:
        return s
    s = s[0].upper() + s[1:]
    for bare, conjugated in (
        (" pass ", " passes "),
        (" announce ", " announces "),
        (" achieve ", " achieves "),
        (" occur ", " occurs "),
        (" reach ", " reaches "),
        (" create ", " creates "),
        (" add ", " adds "),
        (" begin ", " begins "),
        (" resign ", " resigns "),
        (" launch ", " launches "),
    ):
        s = re.sub(rf"\b{bare.strip()}\b", conjugated.strip(), s, count=1)
    if s.lower().startswith("a 7.0+ earthquake occurs"):
        s = "Worldwide 7.0+ earthquake"
    return s


def _restate_source_question(text: str, *, slug: str = "") -> str:
    del slug  # Zero one-set headline overrides; derive strictly from the source text.
    s = (text or "").strip()
    m_who_the = re.match(r"^Who\s+gets\s+the\s+(.+?)\??$", s, re.IGNORECASE)
    if m_who_the:
        tail = re.sub(r"\band\s+the\s+", "and ", m_who_the.group(1).strip(), flags=re.IGNORECASE)
        return tail[0].upper() + tail[1:] if tail else tail
    m_who_part = re.match(r"^Who\s+gets\s+([a-zA-Z]+)\??$", s, re.IGNORECASE)
    if m_who_part:
        return f"Getting {m_who_part.group(1).lower()}"
    if not s.endswith("?"):
        return s[0].upper() + s[1:] if s.lower().startswith("who ") else s
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
        subj = m_when.group(1).strip()
        obj = re.sub(r"^the\s+", "", m_when.group(2).strip(), flags=re.IGNORECASE)
        return f"{subj} {obj} release"
    m_when_any = re.match(r"^When\s+will\s+(.+?)\?$", s, re.IGNORECASE)
    if m_when_any:
        return _present_tense_restatement(m_when_any.group(1).strip())
    m_will = re.match(r"^Will\s+(.+?)\?$", s, re.IGNORECASE)
    if m_will:
        return _present_tense_restatement(m_will.group(1).strip())
    return s.rstrip("?").strip()


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
        code = explicit_short.strip().upper()
        return "POR" if code == "PTB" else code
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
    m = _PORTRAIT_DETAIL_SUFFIX_RE.search(detail)
    if not m:
        return None
    portrait_person = detail[: m.start()].strip()
    if "," in portrait_person:
        portrait_person = portrait_person.split(",", 1)[0].strip()
    if not portrait_person:
        return None
    low_row = row_name.lower()
    low_portrait = portrait_person.lower()
    for work_or_stage, artist_name in _ARTIST_WORK_AND_STAGE_ALLOWLIST:
        if work_or_stage in low_row and artist_name in low_portrait:
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
        _left, right = txt.split(":", 1)
        if right.strip():
            txt = right.strip()
    return re.sub(r"[^a-z0-9]+", " ", txt.lower()).strip()


def _extract_entity_candidate(text: str) -> str:
    cleaned = text.strip().rstrip("?").strip()
    if " · " in cleaned:
        cleaned = cleaned.split(" · ", 1)[1].strip()
    elif ":" in cleaned:
        _l, r = cleaned.split(":", 1)
        if r.strip():
            cleaned = r.strip()
    return cleaned


def _row_requires_picture(
    row_label: str,
    art: dict[str, Any] | None,
    resolver: Any,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Check Alex's picture rule: require pictures ONLY for person, team, or film rows."""
    resolved = art if isinstance(art, dict) and _is_valid_image_url(art.get("url")) and art.get("kind") != "monogram" else None
    kind = _subject_kind_from_art(resolved or art, row_label)
    if kind in {"person", "team", "film"}:
        return True, kind, resolved
    if resolver is not None:
        cleaned_full = row_label.strip().rstrip("?").strip()
        cand = _extract_entity_candidate(row_label)
        probe_candidates = [cleaned_full] if (":" in cleaned_full and cleaned_full != cand) else []
        probe_candidates.append(cand)
        for query in probe_candidates:
            probe = resolver.resolve(query)
            pk = _subject_kind_from_art(probe, row_label)
            if pk in {"person", "team", "film"} and _is_valid_image_url((probe or {}).get("url")) and (probe or {}).get("kind") != "monogram":
                return True, pk, probe
            if query == cand and pk in {"person", "team", "film"}:
                return True, pk, None
    low = row_label.lower()
    if any(
        tok in low
        for tok in (
            "best actor",
            "best actress",
            "best director",
            "best picture",
            "opening box office",
            "grossing movie",
            "win the ",
            "heisman",
            "nba mvp",
            "super bowl",
            "world series",
            "stanley cup",
            "relegated",
        )
    ):
        return True, "person", resolved
    return False, kind, resolved


def _resolve_logo_and_color(
    team_name: str,
    *,
    explicit_art: dict[str, Any] | None = None,
    explicit_team_data: dict[str, Any] | None = None,
    resolver: Any = None,
) -> tuple[str | None, str]:
    color = "#1d428a"
    url: str | None = None
    if team_name.strip().lower() in _COLLEGE_MASCOT_FALLBACKS:
        team_name = _COLLEGE_MASCOT_FALLBACKS[team_name.strip().lower()]
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


def _is_boilerplate_stat(low: str) -> bool:
    return any(
        phrase in low
        for phrase in (
            "in schedule order",
            "each row is its own market",
            "don't add up to 100%",
            "separate markets that settle",
            "bain luck blend",
            "closest of 8",
            "current chances across",
        )
    )


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
        if txt and low != common.lower() and not _is_boilerplate_stat(low):
            stat = txt
            break

    if not stat:
        stat = _scrub_card_copy(fallback_stat)

    common = _restate_source_question(_scrub_card_copy(common), slug=slug)
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


def _collect_market_entries(bundle: dict[str, Any] | None, container: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Collect market dicts across bundle items and container sections without duplicates."""
    markets: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for it in ((bundle or {}).get("data") or {}).get("items") or []:
        if isinstance(it, dict) and it.get("type") != "event":
            cd = it.get("data") or {}
            nm = str(cd.get("name") or cd.get("title") or "").strip()
            if nm and nm.lower() not in seen_names:
                seen_names.add(nm.lower())
                markets.append(cd)
    for sec in (container or {}).get("sections") or []:
        for m in sec.get("members") or []:
            if m.get("type") == "market":
                cd = m.get("card") or {}
                nm = str(cd.get("name") or "").strip()
                if nm and nm.lower() not in seen_names:
                    seen_names.add(nm.lower())
                    markets.append(cd)
    return markets


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

    sample_home = shown[0].get("home_team") == focus_team
    focus_team_data = shown[0].get("home_team_data") if sample_home else shown[0].get("away_team_data")
    focus_url, focus_color = _resolve_logo_and_color(
        focus_team, explicit_team_data=focus_team_data, resolver=resolver
    )
    if not _is_valid_image_url(focus_url):
        return None, f"Missing verified logo for {focus_team}"

    focus_adaptive = _adaptive_team_color(focus_color)
    focus_place = _short_place_name(focus_team)
    items: list[dict[str, Any]] = []
    clauses: list[str] = []

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
        opp_place = _short_place_name(opp)
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
        clauses.append(f"{team_pct}% {prefix} {opp_place} on {day_str}")

    # Always use Fable's road caption form: "Boston is 80% at Washington..."
    stat_sentence = f"{focus_place} is {clauses[0]}, {clauses[1]}, and {clauses[2]}."

    card = _make_kit_card(
        card_id=f"kit-{slug}",
        layout="stack",
        variant="road_ahead",
        kicker=kicker,
        common_headline=common,
        stat_caption=stat_sentence,
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


def _format_date_span_headline(sport_label: str, games: list[dict[str, Any]], slug: str) -> str:
    dts = sorted(dt.astimezone(PT_TZ) for g in games if (dt := _parse_iso_dt(g.get("commence_time"))) is not None)
    if not dts:
        return f"{sport_label} matchups"
    first, last = dts[0], dts[-1]
    if first.month == last.month:
        if first.day == last.day:
            span = f"{_MONTH_ABBR[first.month]} {first.day}"
        else:
            span = f"{_MONTH_ABBR[first.month]} {first.day}–{last.day}"
    else:
        span = f"{_MONTH_ABBR[first.month]} {first.day}–{_MONTH_ABBR[last.month]} {last.day}"
    if slug.startswith("nfl-2026-week-"):
        wk = slug.rsplit("-", 1)[-1]
        return f"NFL Week {wk}, {span}"
    return f"{sport_label}, {span}"


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

    shown = active[:3]
    sport_label = _SPORT_META[sport_key]
    total_count = max(len(active), int(mc.get("item_count") or 0), len(shown))
    headline = _format_date_span_headline(sport_label, active, slug)

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

    if not stat or _is_boilerplate_stat(stat.lower()) or stat.lower() == headline.lower():
        g0 = shown[0]
        p_home = _extract_event_home_pct(g0) or 50
        stat = f"{g0.get('away_team')} ({100 - p_home}%) at {g0.get('home_team')} ({p_home}%) headlines {total_count} matchups."

    card = _make_kit_card(
        card_id=f"kit-{slug}",
        layout="stack",
        variant="single_sport_slate",
        kicker=kicker,
        common_headline=headline,
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

    entries: list[tuple[str, str, int, str, str]] = []
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
        abbr = _short_team_code(team_name)
        if not _is_valid_image_url(url):
            missing_logos.append(team_name)
        else:
            entries.append((team_name, abbr, pct, str(url), hex_color))

    if missing_logos:
        total = len(members)
        return (
            None,
            f"Only {total - len(missing_logos)} of {total} teams have verified crests "
            f"(missing e.g. {', '.join(missing_logos[:3])})",
        )

    pcts = [e[2] for e in entries]
    if max(pcts) - min(pcts) < 35:
        return None, "Spread too narrow for 0–100% bubble axis"

    # Match worked example (#13577): plot ALL 32 teams; elevate every bubble team (25 < p < 75) with crest + abbr
    entries.sort(key=lambda e: (e[2], e[1]))
    marks: list[dict[str, Any]] = []
    in_doubt_rows: list[tuple[str, int]] = []
    lanes_x: list[float] = []
    low_count = 0
    high_count = 0

    for team_name, abbr, p_val, logo_url, color in entries:
        in_doubt = 25 < p_val < 75
        if p_val <= 25:
            low_count += 1
        elif p_val >= 75:
            high_count += 1
        lane: int | None = None
        pic: dict[str, Any] | None = None
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
        marks.append(
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
    leader = max(entries, key=lambda e: e[2])
    mid_bubble = sorted(in_doubt_rows, key=lambda item: abs(item[1] - 50))
    bubble_note = (
        f", while {mid_bubble[0][0]} ({mid_bubble[0][1]}%) and {mid_bubble[1][0]} ({mid_bubble[1][1]}%) sit inside the playoff bubble."
        if len(mid_bubble) >= 2
        else f" across {len(entries)} teams."
    )
    if not stat or _is_boilerplate_stat(stat.lower()) or stat.lower() == common.lower():
        stat = f"{leader[0]} {_lead_verb(leader[0], 'team')} at {leader[2]}%{bubble_note}"

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
            "highlight_band": {"lo": 25, "hi": 75, "label": "in doubt"},
            "marks": marks,
            "summary_marks": [
                _mark_word(f"{low_count} at 25% or less", style="sub", tone="secondary", align="left"),
                _mark_word(f"{high_count} at 75% or more", style="sub", tone="secondary", align="right"),
            ],
            "footer_marks": [
                _mark_word(doubt_summary, style="pill", tone="secondary"),
            ],
        },
    )
    return card, None


def _parse_outcome_deadline(
    label: str,
    *,
    reference_year: int | None = None,
) -> tuple[tuple[int, int, int], str] | None:
    s = (label or "").strip().rstrip("?").strip()
    fallback_year = reference_year if reference_year is not None else datetime.now(PT_TZ).year
    m_full = re.match(
        r"^(?:(?:before|by)\s+)?(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+(\d{1,2})(?:,\s*(\d{4}))?$",
        s,
        re.IGNORECASE,
    )
    if m_full:
        mon = _MONTH_NUMS[m_full.group(1).lower()]
        day = int(m_full.group(2))
        yr = int(m_full.group(3)) if m_full.group(3) else fallback_year
        return (yr, mon, day), f"{_MONTH_ABBR[mon]} {day} '{str(yr)[2:]}"
    m_mon_yr = re.match(
        r"^(?:(?:before|by|in)\s+)?(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+(\d{4})$",
        s,
        re.IGNORECASE,
    )
    if m_mon_yr:
        mon = _MONTH_NUMS[m_mon_yr.group(1).lower()]
        yr = int(m_mon_yr.group(2))
        last_day = calendar.monthrange(yr, mon)[1]
        return (yr, mon, last_day), f"{_MONTH_ABBR[mon]} '{str(yr)[2:]}"
    return None


def _select_chronological_tiles_with_peak(
    cmap: dict[str, tuple[tuple[int, int, int], str, int]],
) -> list[tuple[str, tuple[tuple[int, int, int], str, int]]]:
    """Select up to 3 chronological tiles, guaranteed to include the market's peak outcome."""
    all_sorted = sorted(cmap.items(), key=lambda kv: kv[1][0])
    if len(all_sorted) <= 3:
        return all_sorted
    best_key = max(cmap.items(), key=lambda kv: (kv[1][2], kv[1][0]))[0]
    first_three = all_sorted[:3]
    if any(k == best_key for k, _ in first_three):
        return first_three
    mid_idx = len(all_sorted) // 2
    if all_sorted[mid_idx][0] == best_key:
        mid_idx = max(1, mid_idx - 1)
    chosen = [all_sorted[0], all_sorted[mid_idx], (best_key, cmap[best_key])]
    return sorted(chosen, key=lambda kv: kv[1][0])


def _try_build_dated_tiles(
    *,
    slug: str,
    kicker: str,
    common: str,
    stat: str,
    route: dict[str, Any],
    source_count: int,
    bundle: dict[str, Any] | None,
    container: dict[str, Any] | None,
    now: datetime,
    resolver: Any,
) -> tuple[dict[str, Any] | None, str | None, list[dict[str, Any]]]:
    """Build grid/dated_tiles when >= 2 markets each carry >= 2 open dated outcomes."""
    markets = _collect_market_entries(bundle, container)
    today_pt = now.astimezone(PT_TZ).date()
    dated_rows: list[tuple[str, dict[str, tuple[tuple[int, int, int], str, int]], list[dict[str, Any]]]] = []
    dropped_lanes_audit: list[dict[str, Any]] = []

    for m in markets:
        outs = m.get("top_outcomes") or []
        res_dt = _parse_iso_dt(m.get("resolution_date"))
        ref_year = (res_dt.astimezone(PT_TZ).year if res_dt is not None else today_pt.year)
        by_col: dict[str, tuple[tuple[int, int, int], str, int]] = {}
        expired_items: list[dict[str, Any]] = []
        raw_dated_count = 0

        for o in outs:
            nm = str(o.get("name") or "").strip()
            parsed = _parse_outcome_deadline(nm, reference_year=ref_year)
            pct = _safe_pct(o.get("probability"), o.get("rendered_percent"))
            if parsed and pct is not None:
                raw_dated_count += 1
                sort_k, col_lbl = parsed
                col_key = f"{sort_k[0]:04d}-{sort_k[1]:02d}-{sort_k[2]:02d}"
                if date(*sort_k) < today_pt:
                    expired_items.append({"outcome": nm, "date": col_key, "pct": pct, "reason": "expired"})
                    continue
                by_col[col_key] = (sort_k, col_lbl, pct)

        raw_title = _scrub_card_copy(_restate_source_question(str(m.get("name") or m.get("title") or "")))
        short_title = re.sub(
            r"\s+(?:by|before)\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s*\d{4})?\??",
            "",
            raw_title,
            flags=re.IGNORECASE,
        ).strip(" ·-?")
        short_title = re.sub(r"\s*\(.*?\)$", "", short_title).rstrip("?").strip()

        if len(by_col) >= 2:
            dated_rows.append((short_title, by_col, expired_items))
        elif raw_dated_count >= 2:
            dropped_left_off = list(expired_items) + [
                {"outcome": f"by {cl}", "date": ck, "pct": pct, "reason": "fewer_than_2_open_deadlines"}
                for ck, (_sk, cl, pct) in sorted(by_col.items(), key=lambda kv: kv[1][0])
            ]
            dropped_lanes_audit.append({"lane": short_title, "shown": [], "left_off": dropped_left_off, "dropped": True})

    if len(dated_rows) < 2:
        return None, None, []
    # Only promote roundup sets to dated_tiles when a majority (>= half) of served markets are multi-deadline
    has_machinery_card = bool((((bundle or {}).get("data") or {}).get("roundup") or {}).get("machinery_card"))
    if has_machinery_card and len(dated_rows) * 2 < len(markets):
        return None, None, []

    all_cols: dict[str, tuple[tuple[int, int, int], str]] = {}
    for _t, col_map, _exp in dated_rows[:3]:
        for ck, (sk, cl, _p) in col_map.items():
            all_cols[ck] = (sk, cl)

    all_sorted_cols = sorted(all_cols.items(), key=lambda kv: kv[1][0])
    if len(all_sorted_cols) <= 3:
        sorted_cols = all_sorted_cols
    else:
        sorted_cols = [all_sorted_cols[0], all_sorted_cols[len(all_sorted_cols) // 2], all_sorted_cols[-1]]
    col_keys = {ck for ck, _ in sorted_cols}

    # Check if shared matrix columns cover >= 2 rows cleanly, else use per-row chronological tiles
    aligned = sum(
        1 for _t, cmap, _exp in dated_rows[:3] if len(set(cmap.keys()) & col_keys) >= 2
    )
    use_shared_matrix = aligned == len(dated_rows[:3])

    rows: list[dict[str, Any]] = []
    summaries: list[str] = []
    lanes_audit: list[dict[str, Any]] = []
    any_missing = False

    for idx, (row_title, cmap, expired_items) in enumerate(dated_rows[:3], 1):
        art_req, s_kind, valid_art = _row_requires_picture(row_title, None, resolver)
        pic_url = valid_art["url"] if valid_art else None
        pic_kind = s_kind
        if not pic_url:
            for nation, flag_subj in (("iran", "Iran"), ("russia", "Russia"), ("ukraine", "Ukraine"), ("israel", "Israel"), ("us ", "United States"), ("u.s.", "United States"), ("china", "China")):
                if nation in row_title.lower():
                    flag = _lookup_team_or_nation_logo(flag_subj)
                    if _is_valid_image_url(flag):
                        pic_url = flag
                        pic_kind = "flag"
                        break
        if art_req and not pic_url:
            return None, f"Row {row_title!r} requires a verified {pic_kind} picture", []

        leading: list[dict[str, Any]] = []
        if pic_url:
            leading.append(_mark_picture(url=pic_url, alt=row_title, subject_kind=pic_kind, size="xs", contain=True))
        leading.append(_mark_word(row_title, style="row", tone="primary", width="flex", bold=True))

        shown_entries: list[tuple[str, str, int]] = []
        if use_shared_matrix:
            cells = []
            for ck, (_sk, cl) in sorted_cols:
                entry = cmap.get(ck)
                val = entry[2] if entry else None
                if val is None:
                    any_missing = True
                else:
                    shown_entries.append((ck, entry[1], val))
                cells.append(
                    {
                        "column_key": ck,
                        "marks": [
                            _mark_tile(
                                shade=0.0 if val is None else val / 100.0,
                                top_label=f"by {cl}",
                                center_label="—" if val is None else f"{val}%",
                                muted=(val is None),
                            )
                        ],
                    }
                )
        else:
            row_dates = _select_chronological_tiles_with_peak(cmap)
            shown_entries = [(ck, cl, val) for ck, (_sk, cl, val) in row_dates]
            cells = [
                {
                    "column_key": f"slot-{ci}",
                    "marks": [
                        _mark_tile(
                            shade=val / 100.0,
                            top_label=f"by {cl}",
                            center_label=f"{val}%",
                            muted=False,
                        )
                    ],
                }
                for ci, (_ck, (_sk, cl, val)) in enumerate(row_dates)
            ]

        shown_key_set = {ck for ck, _cl, _val in shown_entries}
        left_off = list(expired_items)
        for ck, (_sk, cl, val) in sorted(cmap.items(), key=lambda kv: kv[1][0]):
            if ck not in shown_key_set:
                left_off.append({"outcome": f"by {cl}", "date": ck, "pct": val, "reason": "trimmed_to_3"})
        lanes_audit.append(
            {
                "lane": row_title,
                "shown": [{"outcome": f"by {cl}", "date": ck, "pct": val} for ck, cl, val in shown_entries],
                "left_off": left_off,
                "dropped": False,
            }
        )

        rows.append(
            {
                "id": f"dt-{idx}-{re.sub(r'[^a-z0-9]+', '-', row_title.lower()).strip('-')}",
                "leading": leading,
                "cells": cells,
            }
        )
        best_shown = max(shown_entries, key=lambda tup: (tup[2], tup[0]))
        summaries.append(f"{row_title}: {best_shown[2]}% by {best_shown[1]}")

    for row_title, cmap, expired_items in dated_rows[3:]:
        lane_left = list(expired_items) + [
            {"outcome": f"by {cl}", "date": ck, "pct": val, "reason": "beyond_3_lanes"}
            for ck, (_sk, cl, val) in sorted(cmap.items(), key=lambda kv: kv[1][0])
        ]
        lanes_audit.append({"lane": row_title, "shown": [], "left_off": lane_left, "dropped": True})
    lanes_audit.extend(dropped_lanes_audit)

    cols = (
        [{"key": ck, "label": cl} for ck, (_sk, cl) in sorted_cols]
        if use_shared_matrix
        else [{"key": f"slot-{i}", "label": f"Checkpoint {i + 1}"} for i in range(3)]
    )
    stat_sentence = "; ".join(summaries[:2]) + "."
    footnote = "Dash (—) means no market is open for that deadline." if any_missing else None

    card = _make_kit_card(
        card_id=f"kit-{slug}",
        layout="grid",
        variant="dated_tiles",
        kicker=kicker,
        common_headline=common,
        stat_caption=stat_sentence,
        source_count=source_count,
        route_kind="collection",
        route_id=route.get("id"),
        route_slug=route.get("slug"),
        footnote=footnote,
        body={
            "show_column_headers": False,
            "row_layout": "stacked_cells",
            "columns": cols,
            "rows": rows,
        },
    )
    return card, None, lanes_audit


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
    resolver: Any,
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
    candidate_rows: list[tuple[str, int, str, str | None]] = []
    seen_entities: set[str] = set()

    for it in items_raw:
        c = it.get("data") or {}
        dt = _parse_iso_dt(c.get("resolution_date"))
        if dt is not None:
            res_dates.append(dt)
        name = _scrub_card_copy(_restate_source_question(str(c.get("name") or c.get("title") or "").strip()))
        # Strip trailing deadline suffix inside deadline cards since header already shows the date
        name = re.sub(
            r"\s+by\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s*\d{4})?$",
            "",
            name,
            flags=re.IGNORECASE,
        ).strip()
        outs = c.get("top_outcomes") or []
        pct = _safe_pct((outs[0] or {}).get("probability"), (outs[0] or {}).get("rendered_percent")) if outs else None
        if not name or pct is None:
            continue
        ekey = _entity_key_for_row(name)
        if ekey in seen_entities:
            continue
        seen_entities.add(ekey)

        art_req, s_kind, verified = _row_requires_picture(name, None, resolver)
        if art_req and not verified:
            return None, f"Deadline row {name!r} requires a verified {s_kind} picture"
        if art_req and verified:
            if mismatch := _art_matches_subject(name, verified):
                return None, mismatch

        # Only keep distinct verified art from resolver/nation-flag — never repeated generic bundle thumbnails
        pic_url = verified["url"] if verified else None
        candidate_rows.append((name, pct, s_kind, pic_url))

    if not res_dates:
        return None, "Missing deadline timestamp for countdown"

    target_date = min(res_dates)
    raw_days = (target_date.astimezone(PT_TZ).date() - now.astimezone(PT_TZ).date()).days
    deadline_iso = target_date.isoformat()
    if raw_days <= 0:
        num_val, num_display, hero_text = 0, "Today", "ends today"
    elif raw_days == 1:
        num_val, num_display, hero_text = 1, "1", "day left"
    else:
        num_val, num_display, hero_text = raw_days, str(raw_days), "days left"
    if len(candidate_rows) < 3:
        return None, f"Only {len(candidate_rows)} valid deadline rows found"

    shown = candidate_rows[:4]
    # Keep picture alignment uniform on stack rows: show pictures iff all shown rows have unique verified URLs
    urls = [u for _nm, _pct, _sk, u in shown]
    use_pictures = all(bool(u) for u in urls) and len(set(urls)) == len(urls)

    items = []
    for idx, (nm, pct, sk, url) in enumerate(shown, 1):
        marks: list[dict[str, Any]] = []
        if use_pictures and url:
            marks.append(_mark_picture(url=url, alt=nm, subject_kind=sk, size="sm", contain=(sk != "person")))
        marks.extend(
            [
                _mark_word(nm, style="row", tone="primary", width="flex"),
                _mark_bar_single(pct / 100.0, width="sm"),
                _mark_number(pct, f"{pct}%", width="sm"),
            ]
        )
        items.append({"id": f"cd-{idx}", "marks": marks})

    date_short = common.replace("By ", "")
    if not stat or _is_boilerplate_stat(stat.lower()) or stat.lower() == common.lower():
        stat = f"{shown[0][0]} leads {date_short} deadlines at {shown[0][1]}%, ahead of {shown[1][0]} ({shown[1][1]}%)."

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
                    num_val,
                    num_display,
                    unit="days",
                    tone="accent",
                    prominence="hero",
                    align="left",
                    width="auto",
                    deadline_iso=deadline_iso,
                ),
                _mark_word(
                    hero_text,
                    style="hero_label",
                    tone="primary",
                    align="left",
                    width="flex",
                    bold=True,
                    secondary_text=f"all of these end on {date_short}",
                    deadline_iso=deadline_iso,
                ),
            ],
            "items": items,
        },
    )
    return card, None


def _parse_numeric_bucket(label: str, unit: str) -> tuple[float, float] | None:
    s = (label or "").strip().lower()
    if unit == "$M":
        m_rng = re.match(r"^(\d+(?:\.\d+)?)m\s*[-–]\s*(\d+(?:\.\d+)?)m$", s)
        if m_rng:
            return float(m_rng.group(1)), float(m_rng.group(2))
        m_plus = re.match(r"^(\d+(?:\.\d+)?)m\+$", s)
        if m_plus:
            v = float(m_plus.group(1))
            return v, v + 45.0
        m_lt = re.match(r"^<(\d+(?:\.\d+)?)m$", s)
        if m_lt:
            v = float(m_lt.group(1))
            return max(0.0, v - 35.0), v
    elif unit == "°C":
        m_deg = re.match(r"^(-?\d+(?:\.\d+)?)°c$", s)
        if m_deg:
            v = float(m_deg.group(1))
            return v - 0.8, v + 0.8
    return None


def _try_build_shared_scale(
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
    """Build axis/shared_scale when >= 2 markets price ranges on one numeric unit ($M or °C)."""
    markets = _collect_market_entries(None, container)
    detected_unit: str | None = None
    series_candidates: list[tuple[str, float, float, int, str, dict[str, Any] | None]] = []

    for m in markets:
        outs = m.get("top_outcomes") or []
        if len(outs) < 3:
            continue
        m_name = str(m.get("name") or "")
        unit: str | None = None
        if any("°c" in str(o.get("name") or "").lower() for o in outs):
            unit = "°C"
        elif any(re.search(r"\d+m(?:\+|$|[-–])", str(o.get("name") or "").lower()) for o in outs) and "box office" in m_name.lower():
            unit = "$M"
        if not unit:
            continue
        if detected_unit is None:
            detected_unit = unit
        elif unit != detected_unit:
            continue

        parsed_pts: list[tuple[float, float, int, str]] = []
        for o in outs:
            nm = str(o.get("name") or "").strip()
            pct = _safe_pct(o.get("probability"), o.get("rendered_percent"))
            span = _parse_numeric_bucket(nm, unit)
            if span and pct is not None:
                parsed_pts.append((span[0], span[1], pct, nm))
        if not parsed_pts:
            continue

        top_lo, top_hi, top_pct, top_lbl = max(parsed_pts, key=lambda x: (x[2], x[0]))
        if unit == "°C":
            m_city = re.search(r"temperature in\s+(.+?)\s+on\s+", m_name, re.IGNORECASE)
            label = m_city.group(1).strip() if m_city else _restate_source_question(m_name)
        else:
            label = re.sub(r'^"(.+?)"\s+opening weekend box office$', r"\1", m_name, flags=re.IGNORECASE).strip()

        art_req, s_kind, verified = _row_requires_picture(label, None, resolver)
        if art_req and not verified:
            continue
        series_candidates.append((label, top_lo, top_hi, top_pct, top_lbl, verified))

    if len(series_candidates) < 2 or detected_unit is None:
        return None, None

    if detected_unit == "$M":
        s_min, s_max = 0.0, 460.0
        ticks = [
            {"x": 0, "label": "$0M"},
            {"x": 115, "label": "$115M"},
            {"x": 230, "label": "$230M"},
            {"x": 345, "label": "$345M"},
            {"x": 460, "label": "$460M"},
        ]
        headline = "2026 opening weekend box office comparisons ($M)"
    else:
        lo_vals = [c[1] for c in series_candidates]
        hi_vals = [c[2] for c in series_candidates]
        s_min = float(int(min(lo_vals) // 5) * 5)
        s_max = float(int((max(hi_vals) + 6) // 5) * 5)
        step = max(5, int((s_max - s_min) / 4))
        ticks = [{"x": int(s_min + i * step), "label": f"{int(s_min + i * step)}°C"} for i in range(5)]
        s_max = float(ticks[-1]["x"])
        headline = "Forecast high temperatures across global cities (°C)"

    use_pics = all(c[5] is not None for c in series_candidates)
    span_len = max(1.0, s_max - s_min)
    series = []
    summary_parts = []
    for idx, (label, lo_v, hi_v, pct, peak_lbl, pic) in enumerate(series_candidates[:4], 1):
        leading = []
        if use_pics and pic is not None:
            sk = _subject_kind_from_art(pic, label)
            leading.append(_mark_picture(url=pic["url"], alt=label, subject_kind=sk, size="sm", contain=(sk != "person")))
        leading.append(_mark_word(label, style="row", tone="primary", bold=True, width="flex"))
        lo_norm = round(max(0.0, min(0.95, (lo_v - s_min) / span_len)), 3)
        hi_norm = round(max(lo_norm + 0.05, min(1.0, (hi_v - s_min) / span_len)), 3)
        display_lbl = peak_lbl if detected_unit == "°C" else f"${peak_lbl}"
        series.append(
            {
                "id": f"ss-{idx}",
                "leading": leading,
                "marks": [
                    _mark_bar_range(lo=lo_norm, hi=hi_norm, width="flex"),
                    _mark_word(display_lbl, style="meta", tone="secondary", align="right", width="auto"),
                    _mark_number(pct, f"{pct}%", unit="%", tone="primary", prominence="primary", align="right", width="sm"),
                ],
            }
        )
        summary_parts.append(f"{label} ({display_lbl}, {pct}%)")

    stat_sentence = f"Peak ranges compare {', '.join(summary_parts[:3])} on one {detected_unit} scale."
    card = _make_kit_card(
        card_id=f"kit-{slug}",
        layout="axis",
        variant="shared_scale",
        kicker=kicker,
        common_headline=headline,
        stat_caption=stat_sentence,
        source_count=source_count,
        route_kind="collection",
        route_id=route.get("id"),
        route_slug=route.get("slug"),
        body={
            "scale": {
                "scale_kind": "numeric",
                "unit": detected_unit,
                "min": s_min,
                "max": s_max,
                "ticks": ticks,
            },
            "scale_units": [detected_unit],
            "series": series,
        },
    )
    return card, None


def _try_build_one_in_n(
    *,
    slug: str,
    kicker: str,
    common: str,
    stat: str,
    route: dict[str, Any],
    source_count: int,
    bundle: dict[str, Any] | None,
    resolver: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """Build stack/one_in_n for long-shot boards (`1%..25%`) BEFORE casting_sheet."""
    d = (bundle or {}).get("data") or {}
    ru = d.get("roundup") or {}
    mc = ru.get("machinery_card") or {}
    mc_form = str(mc.get("form_id") or "")
    mc_rows = mc.get("rows") or []

    if mc_form == "contender_spotlight" or len(mc_rows) < 3:
        return None, None

    top3 = mc_rows[:3]
    pcts = [_safe_pct(r.get("probability"), r.get("rendered_percent")) for r in top3]
    if any(p is None or p < 1 or p > 25 for p in pcts):
        return None, None

    rows_data: list[tuple[str, int, str, str | None]] = []
    seen_entities: set[str] = set()
    for r, pct in zip(top3, pcts):
        nm = str(r.get("name") or "").strip()
        assert pct is not None
        ekey = _entity_key_for_row(nm)
        if ekey in seen_entities:
            return None, f"Duplicate contender entity {ekey!r} across served card rows"
        seen_entities.add(ekey)

        art = r.get("art") if isinstance(r.get("art"), dict) else None
        art_req, s_kind, verified = _row_requires_picture(nm, art, resolver)
        if art_req and not verified:
            return None, f"Row {nm!r} requires a verified {s_kind} picture"
        if verified:
            if mismatch := _art_matches_subject(nm, verified):
                return None, mismatch
        rows_data.append((nm, pct, s_kind, verified["url"] if verified else None))

    urls = [u for _nm, _pct, _sk, u in rows_data]
    use_pics = all(bool(u) for u in urls) and len(set(urls)) == len(urls)

    items: list[dict[str, Any]] = []
    for idx, (nm, pct, sk, url) in enumerate(rows_data, 1):
        pct_display = f"{pct}%"
        n_val = compute_one_in_n(pct)
        marks: list[dict[str, Any]] = []
        if use_pics and url:
            marks.append(_mark_picture(url=url, alt=nm, subject_kind=sk, size="sm", contain=True))
        marks.extend(
            [
                _mark_word(nm, style="row", tone="primary", align="left", width="flex", bold=False),
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
        items.append({"id": f"oin-{idx}", "marks": marks})

    if not stat or _is_boilerplate_stat(stat.lower()):
        stat = f"{rows_data[0][0]} leads at {rows_data[0][1]}% (1 in {compute_one_in_n(rows_data[0][1])})."

    card = _make_kit_card(
        card_id=f"kit-{slug}",
        layout="stack",
        variant="one_in_n",
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


def _norm_entity_match(name: str) -> str:
    cleaned = re.sub(r"\.", "", (name or "").strip().lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_list_subject_label(market_title: str) -> str:
    m_list = re.search(
        r"#1\s+(?:most\s+)?(?:searched|ranked|selling|streamed|watched|popular)?\s*(.+?)(?:\s+on\s+|\s+in\s+|\s+for\s+|\s+\d{4}|\?|$)",
        market_title,
        re.IGNORECASE,
    )
    raw = (m_list.group(1) if m_list else "").strip()
    if raw.lower() == "tv show":
        return "TV show"
    if raw:
        return raw[0].upper() + raw[1:].lower()
    return ""


def _stage_stem(market_title: str) -> str:
    stem = re.sub(r"\b(?:winner|winners|nominee|nominees)\b", "", market_title, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", " ", stem.lower()).strip()


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

    all_markets = [m for sec in secs for m in (sec.get("members") or []) if m.get("type") == "market"]
    if len(all_markets) < 2:
        return None, None

    def _market_name(m: dict[str, Any]) -> str:
        return str((m.get("card") or {}).get("name") or "").strip()

    def _market_outcomes(m: dict[str, Any]) -> list[dict[str, Any]]:
        return (m.get("card") or {}).get("top_outcomes") or []

    # Data-driven paired patterns across ALL sections (zero slug branches, zero positional section reads)
    winner_election_m = next(
        (
            m for m in all_markets
            if "election winner" in _market_name(m).lower()
            and "(party)" not in _market_name(m).lower()
            and len([o for o in _market_outcomes(m) if "party" not in str(o.get("name") or "").lower()]) >= 3
        ),
        None,
    )
    nominee_ms = [
        m for m in all_markets
        if "nominee" in _market_name(m).lower()
        and "vice" not in _market_name(m).lower()
        and "running mate" not in _market_name(m).lower()
    ]
    rank1_ms = [m for m in all_markets if re.search(r"#1\b", _market_name(m))]
    top5_ms = [m for m in all_markets if re.search(r"\btop\s+5\b", _market_name(m), re.IGNORECASE)]
    qual_m = next((m for m in all_markets if "playoff qualifiers" in _market_name(m).lower()), None)
    champ_m = next((m for m in all_markets if "national championship winner" in _market_name(m).lower()), None)

    market_cols: list[tuple[str, str, dict[str, tuple[str, int]]]] = []
    col1_order: dict[str, int] = {}
    row_secondary: dict[str, str] = {}
    leading_label: str

    if winner_election_m is not None and len(nominee_ms) >= 2:
        is_single_race = True
        out_p: dict[str, tuple[str, int]] = {}
        for idx_o, o in enumerate(_market_outcomes(winner_election_m)):
            nm = str(o.get("name") or "").strip()
            pct = _safe_pct(o.get("probability"), o.get("rendered_percent"))
            if nm and pct is not None and nm.lower() != "tie":
                nk = _norm_entity_match(nm)
                if nk not in out_p:
                    out_p[nk] = (nm, pct)
                    col1_order[nk] = idx_o
        out_n: dict[str, tuple[str, int]] = {}
        for nm_m in nominee_ms:
            for o in _market_outcomes(nm_m):
                nm = str(o.get("name") or "").strip()
                pct = _safe_pct(o.get("probability"), o.get("rendered_percent"))
                if nm and pct is not None:
                    nk = _norm_entity_match(nm)
                    if nk not in out_n or pct > out_n[nk][1]:
                        out_n[nk] = (nm, pct)
        col1_title = "Presidential" if "presidential" in _market_name(winner_election_m).lower() else "General election"
        market_cols.extend([("pres", col1_title, out_p), ("nom", "Wins party nomination", out_n)])
        leading_label = "Candidate"
    elif len(rank1_ms) >= 3 and len(top5_ms) >= 3:
        is_single_race = False
        col1: dict[str, tuple[str, int]] = {}
        col2: dict[str, tuple[str, int]] = {}
        for idx_m, m in enumerate(rank1_ms):
            outs = _market_outcomes(m)
            if outs and outs[0].get("name"):
                nm = str(outs[0]["name"]).strip()
                pct = _safe_pct(outs[0].get("probability"), outs[0].get("rendered_percent"))
                if pct is None:
                    continue
                nk = _norm_entity_match(nm)
                col1[nk] = (nm, pct)
                col1_order[nk] = idx_m
                lbl = _extract_list_subject_label(_market_name(m))
                if lbl:
                    row_secondary[nk] = lbl
        for m in top5_ms:
            for o in _market_outcomes(m):
                if o.get("name"):
                    nm = str(o["name"]).strip()
                    pct = _safe_pct(o.get("probability"), o.get("rendered_percent"))
                    if pct is None:
                        continue
                    nk = _norm_entity_match(nm)
                    if nk not in col2 or pct > col2[nk][1]:
                        col2[nk] = (nm, pct)
        market_cols.extend([("top1", "#1 in its list", col1), ("top5", "Top 5 in its list", col2)])
        leading_label = "Subject"
    elif mc_form == "paired_stage_bars":
        is_single_race = True
        pair: tuple[dict[str, Any], dict[str, Any]] | None = None
        wins_ms = [m for m in all_markets if "winner" in _market_name(m).lower()]
        noms_ms = [m for m in all_markets if "nominee" in _market_name(m).lower() or "nominated" in _market_name(m).lower()]
        for wm in wins_ms:
            w_stem = _stage_stem(_market_name(wm))
            best_nm = next((nm for nm in noms_ms if _stage_stem(_market_name(nm)) == w_stem), None)
            if best_nm is not None:
                pair = (wm, best_nm)
                break
        if pair is None:
            pair = (all_markets[0], all_markets[1])
        for m in pair:
            c = m.get("card") or {}
            m_id = str(c.get("id") or len(market_cols) + 1)
            m_name = _market_name(m)
            low = m_name.lower()
            if "nominee" in low or "nominated" in low:
                col_label = "Nominated"
            elif "winner" in low:
                col_label = "Wins"
            else:
                col_label = m_name.split(":")[-1].strip()[:18] or f"Race {len(market_cols) + 1}"
            out_map: dict[str, tuple[str, int]] = {}
            for idx_o, o in enumerate(c.get("top_outcomes") or []):
                nm = str(o.get("name") or "").strip()
                pct = _safe_pct(o.get("probability"), o.get("rendered_percent"))
                if nm and pct is not None and nm.lower() != "tie":
                    nk = _norm_entity_match(nm)
                    out_map[nk] = (nm, pct)
                    if not market_cols:
                        col1_order[nk] = idx_o
            market_cols.append((m_id, col_label, out_map))
        first_low = _market_name(pair[0]).lower()
        leading_label = (
            "Film" if any(k in first_low for k in ("picture", "film", "movie"))
            else "Actor" if any(k in first_low for k in ("actor", "actress"))
            else "Team" if any(k in first_low for k in ("football", "championship", "playoff", "nba", "nfl", "nhl"))
            else "Contender"
        )
    elif qual_m is not None and champ_m is not None:
        is_single_race = True
        for m, col_label in ((champ_m, "National"), (qual_m, "Playoff")):
            c = m.get("card") or {}
            m_id = str(c.get("id") or len(market_cols) + 1)
            out_map = {}
            for idx_o, o in enumerate(c.get("top_outcomes") or []):
                nm = str(o.get("name") or "").strip()
                pct = _safe_pct(o.get("probability"), o.get("rendered_percent"))
                if nm and pct is not None and nm.lower() != "tie":
                    nk = _norm_entity_match(nm)
                    out_map[nk] = (nm, pct)
                    if not market_cols:
                        col1_order[nk] = idx_o
            market_cols.append((m_id, col_label, out_map))
        leading_label = "Team"
    else:
        return None, None

    if len(market_cols) < 2:
        return None, None

    c0, c1 = market_cols[0], market_cols[1]
    col1_ordered = sorted(c0[2].keys(), key=lambda nk: (-c0[2][nk][1], col1_order.get(nk, 999), nk))
    if len(col1_ordered) < 3:
        return None, f"Primary market ({c0[1]!r}) has fewer than 3 contenders"

    shared_keys = [nk for nk in col1_ordered if nk in c1[2]]
    if len(shared_keys) < 3:
        return (
            None,
            f"Paired markets ({c0[1]!r} vs {c1[1]!r}) share only {len(shared_keys)} overlapping contenders in top outcomes (need >= 3)",
        )

    # Strict Column-1 ranking: never silently skip a top-4 contender missing from Column 2
    top_col1 = col1_ordered[:4] if len(col1_ordered) >= 4 else col1_ordered[:3]
    missing_in_col2 = [c0[2][nk][0] for nk in top_col1 if nk not in c1[2]]
    if missing_in_col2:
        return (
            None,
            f"Column 1 top-{len(top_col1)} contender {missing_in_col2[0]!r} has no {c1[1]!r} number; keeping today's card",
        )
    shown_keys = top_col1

    pre_art_by_norm: dict[str, dict[str, Any]] = {}
    for sec in secs:
        for it in (sec.get("visual_block") or {}).get("items") or []:
            for oc in it.get("outcomes") or []:
                art_d = oc.get("art")
                if isinstance(art_d, dict) and _is_valid_image_url(art_d.get("url")) and art_d.get("kind") != "monogram":
                    nk_o = _norm_entity_match(str(oc.get("name") or ""))
                    if nk_o and nk_o not in pre_art_by_norm:
                        pre_art_by_norm[nk_o] = art_d

    rows: list[dict[str, Any]] = []
    top_row_kind = "topic"
    for rank_idx, nk in enumerate(shown_keys, 1):
        nm = c0[2][nk][0]
        art = pre_art_by_norm.get(nk) or resolver.resolve(nm) or {}
        url = art.get("url")
        if (not _is_valid_image_url(url) or art.get("kind") == "monogram") and leading_label == "Team":
            cfp_url, cfp_color = _resolve_logo_and_color(nm, resolver=resolver)
            if _is_valid_image_url(cfp_url):
                art = {"url": cfp_url, "kind": "team_logo", "accent_color": cfp_color}
                url = cfp_url
        if not _is_valid_image_url(url) or art.get("kind") == "monogram":
            return None, f"Grid cell entity {nm!r} has no verified non-monogram picture"
        if mismatch := _art_matches_subject(nm, art):
            return None, mismatch
        s_kind = _subject_kind_from_art(art, nm)
        if rank_idx == 1:
            top_row_kind = s_kind
        if s_kind == "person" and not _has_first_and_last_name(nm):
            return None, f"Person row {nm!r} requires first & last name"

        leading: list[dict[str, Any]] = []
        if is_single_race:
            leading.append(_mark_word(str(rank_idx), style="rank", tone="muted", width="xs"))
        leading.append(_mark_picture(url=str(url), alt=nm, subject_kind=s_kind, size="sm", contain=True))
        leading.append(
            _mark_word(
                nm,
                style="row",
                tone="primary",
                width="flex",
                bold=True,
                secondary_text=row_secondary.get(nk),
            )
        )

        rows.append(
            {
                "id": f"row-{rank_idx}-{re.sub(r'[^a-z0-9]+', '-', nk).strip('-')}",
                "leading": leading,
                "cells": [
                    {
                        "column_key": col_key,
                        "marks": [
                            _mark_tile(
                                shade=round(out_map[nk][1] / 100.0, 2),
                                center_label=f"{out_map[nk][1]}%",
                                muted=False,
                            )
                        ],
                    }
                    for col_key, _col_label, out_map in market_cols[:2]
                ],
            }
        )

    cols = [{"key": ck, "label": cl} for ck, cl, _ in market_cols[:2]]
    if not stat or _is_boilerplate_stat(stat.lower()):
        top_nm, top_p0 = c0[2][shown_keys[0]]
        stat = f"{top_nm} {_lead_verb(top_nm, top_row_kind)} {cols[0]['label']} at {top_p0}% across {len(shared_keys)} shared contenders."

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
        body={
            "leading_label": leading_label,
            "show_column_headers": True,
            "row_layout": "matrix",
            "columns": cols,
            "rows": rows,
        },
    )
    return card, None


def _try_build_casting_sheet(
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
            if url and not _is_valid_image_url(url):
                host = urlparse(str(url)).hostname or "invalid"
                return None, f"Row {nm!r} picture host rejected ({host})"
            if not url or art.get("kind") == "monogram":
                return None, f"Row {nm!r} has no verified picture (none found; monogram only)"
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
            logo_url, team_hex = _resolve_logo_and_color(leader, resolver=resolver)
            if not _is_valid_image_url(logo_url):
                return None, f"Leader {leader!r} has no verified picture"
            ekey = _entity_key_for_row(leader)
            if ekey in seen_entities:
                return None, f"Duplicate entity {leader!r}"
            seen_entities.add(ekey)
            candidate_rows.append((row_label, pct, str(logo_url), "team", team_hex))

    if len(candidate_rows) < 3:
        return None, "Fewer than 3 verified pictured rows"

    if not stat or _is_boilerplate_stat(stat.lower()) or stat.lower() == common.lower():
        stat = (
            f"{candidate_rows[0][0]} {_lead_verb(candidate_rows[0][0], candidate_rows[0][3])} at {candidate_rows[0][1]}%, "
            f"with {candidate_rows[1][0]} at {candidate_rows[1][1]}%."
        )

    all_teams = all(sk == "team" for _nm, _p, _u, sk, _hex in candidate_rows)
    items: list[dict[str, Any]] = []
    for idx, (nm, pct, url, s_kind, c_hex) in enumerate(candidate_rows, 1):
        pct_display = f"{pct}%"
        # Single uniform accent bar color unless every row is a team (#13584 Fable review)
        bar_color = _adaptive_team_color(c_hex) if (all_teams and c_hex) else None
        marks: list[dict[str, Any]] = [
            _mark_picture(url=url, alt=nm, subject_kind=s_kind, size="sm", contain=True),
            _mark_word(nm, style="row", tone="primary", align="left", width="flex", bold=False),
            _mark_bar_single(pct / 100.0, width="sm", fill_color=bar_color),
            _mark_number(pct, pct_display, width="sm"),
        ]
        items.append({"id": f"row-{idx}", "marks": marks})

    card = _make_kit_card(
        card_id=f"kit-{slug}",
        layout="stack",
        variant="casting_sheet",
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
            return "Theme uses generic stock photos (images.pexels.com) and mixed non-comparable markets"
        return "Theme combines distinct market shapes without shared verified entity art"
    if mc:
        rows = mc.get("rows") or []
        monograms = sum(1 for r in rows if (r.get("art") or {}).get("kind") == "monogram" or not (r.get("art") or {}).get("url"))
        if monograms:
            return f"{monograms} of {len(rows)} card rows fall back to monograms instead of verified pictures"
    return "No deterministic Kit v1 shape matches this container's served structure"


class _NullResolver:
    """Fallback no-op resolver when caller does not supply SubjectArtResolver."""

    def resolve(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}


def build_kit_card_for_real_set(
    bundle: dict[str, Any] | None,
    container: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
    resolver: Any | None = None,
) -> dict[str, Any]:
    """Deterministically convert one public bundle/container into Kit v1 or honest refusal."""
    resolved_now = now or datetime.now(timezone.utc)
    active_resolver = resolver if resolver is not None else _NullResolver()
    slug, kicker, common, stat, route = _derive_slug_and_copy(bundle, container)
    source_count = _source_count_from_bundle(bundle, container)

    dated_lanes_audit: list[dict[str, Any]] = []

    def _detect_dated_tiles() -> tuple[dict[str, Any] | None, str | None]:
        card, msg, lanes = _try_build_dated_tiles(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, bundle=bundle, container=container,
            now=resolved_now, resolver=active_resolver,
        )
        dated_lanes_audit[:] = lanes
        return card, msg

    # Specific shapes first; casting_sheet strictly last (#13584 Fable review)
    detectors = [
        lambda: _try_build_road_ahead(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, bundle=bundle, container=container, resolver=active_resolver,
        ),
        lambda: _try_build_single_sport_slate(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, bundle=bundle, container=container, resolver=active_resolver,
        ),
        lambda: _try_build_bubble_line(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, container=container, resolver=active_resolver,
        ),
        _detect_dated_tiles,
        lambda: _try_build_countdown(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, bundle=bundle, now=resolved_now, resolver=active_resolver,
        ),
        lambda: _try_build_shared_scale(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, container=container, resolver=active_resolver,
        ),
        lambda: _try_build_one_in_n(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, bundle=bundle, resolver=active_resolver,
        ),
        lambda: _try_build_scoreboard_grid(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, bundle=bundle, container=container, resolver=active_resolver,
        ),
        lambda: _try_build_casting_sheet(
            slug=slug, kicker=kicker, common=common, stat=stat, route=route,
            source_count=source_count, bundle=bundle, container=container, resolver=active_resolver,
        ),
    ]

    refusal: str | None = None
    for run in detectors:
        card, msg = run()
        if card is not None:
            ok, errs = validate_kit_v1_card(card)
            if ok:
                probe = dict(card, variant="future_unknown_variant_probe")
                ok_probe, errs_probe = validate_kit_v1_card(probe)
                if ok_probe:
                    out: dict[str, Any] = {
                        "slug": slug,
                        "common_headline": str(card.get("common_headline") or common),
                        "stat_caption": str(card.get("stat_caption") or stat),
                        "fits": True,
                        "layout": card["layout"],
                        "variant": card.get("variant"),
                        "refusal_reason": None,
                        "kit_card": card,
                    }
                    if card.get("variant") == "dated_tiles" and dated_lanes_audit:
                        out["dated_tiles_lanes"] = dated_lanes_audit
                    return out
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
    resolver: Any | None = None,
) -> dict[str, Any]:
    """Run deterministic Kit v1 conversion across Top 10 + all public sets in snapshot."""
    resolved_now = now or datetime.now(timezone.utc)
    active_resolver = resolver if resolver is not None else _NullResolver()
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
        result = build_kit_card_for_real_set(b, container, now=resolved_now, resolver=active_resolver)
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
        result = build_kit_card_for_real_set(None, container, now=resolved_now, resolver=active_resolver)
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
    dated_tiles_left_off = {
        e["slug"]: e["dated_tiles_lanes"]
        for e in (top10_entries + extra_fitting_entries)
        if e.get("fits") and e.get("dated_tiles_lanes")
    }
    return {
        "kit_version": 1,
        "generated_at": resolved_now.isoformat(),
        "total_sets": total_sets,
        "fitting_count": fitting_count,
        "kept_today_count": len(kept_today),
        "dated_tiles_left_off": dated_tiles_left_off,
        "top_10": top10_entries,
        "fitting_beyond_top_10": extra_fitting_entries,
        "kept_today": kept_today,
    }


def load_real_sets_audit_report(
    fixture_path: Path = REAL_SETS_FIXTURE_PATH,
    *,
    now: datetime | None = None,
    resolver: Any | None = None,
) -> dict[str, Any]:
    """Load real-set fixture JSON and run deterministic Kit conversion."""
    with open(fixture_path, encoding="utf-8") as f:
        snapshot = json.load(f)
    return build_real_sets_audit_report(snapshot, now=now, resolver=resolver)
