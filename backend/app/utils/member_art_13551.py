"""Member picture, alias, short-label, and conference helpers for Forms Lab Batch 1 (#13551)."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING, Any, Mapping, Optional

from app.utils.discover_image_policy import _ESPN_TEAM_LOGOS

if TYPE_CHECKING:
    from app.utils.container_machinery import SubjectArtResolver

CANONICAL_CONTENDER_ALIASES: dict[str, str] = {
    "gemini": "Google",
    "google gemini": "Google",
    "google ai": "Google",
    "alphabet": "Google",
    "alphabet inc": "Google",
    "claude": "Anthropic",
    "claude opus": "Anthropic",
    "chatgpt": "OpenAI",
    "gpt": "OpenAI",
    "grok": "xAI",
    "qwen": "Alibaba",
    "ernie": "Baidu",
}

NHL_CONFERENCES: dict[str, tuple[str, ...]] = {
    "Eastern": (
        "Boston Bruins",
        "Buffalo Sabres",
        "Carolina Hurricanes",
        "Columbus Blue Jackets",
        "Detroit Red Wings",
        "Florida Panthers",
        "Montreal Canadiens",
        "New Jersey Devils",
        "New York Islanders",
        "New York Rangers",
        "Ottawa Senators",
        "Philadelphia Flyers",
        "Pittsburgh Penguins",
        "Tampa Bay Lightning",
        "Toronto Maple Leafs",
        "Washington Capitals",
    ),
    "Western": (
        "Anaheim Ducks",
        "Calgary Flames",
        "Chicago Blackhawks",
        "Colorado Avalanche",
        "Dallas Stars",
        "Edmonton Oilers",
        "Los Angeles Kings",
        "Minnesota Wild",
        "Nashville Predators",
        "San Jose Sharks",
        "Seattle Kraken",
        "St. Louis Blues",
        "Utah Mammoth",
        "Vancouver Canucks",
        "Vegas Golden Knights",
        "Winnipeg Jets",
    ),
}

NBA_CONFERENCES: dict[str, tuple[str, ...]] = {
    "Eastern": (
        "Atlanta Hawks",
        "Boston Celtics",
        "Brooklyn Nets",
        "Charlotte Hornets",
        "Chicago Bulls",
        "Cleveland Cavaliers",
        "Detroit Pistons",
        "Indiana Pacers",
        "Miami Heat",
        "Milwaukee Bucks",
        "New York Knicks",
        "Orlando Magic",
        "Philadelphia 76ers",
        "Toronto Raptors",
        "Washington Wizards",
    ),
    "Western": (
        "Dallas Mavericks",
        "Denver Nuggets",
        "Golden State Warriors",
        "Houston Rockets",
        "LA Clippers",
        "Los Angeles Lakers",
        "Memphis Grizzlies",
        "Minnesota Timberwolves",
        "New Orleans Pelicans",
        "Oklahoma City Thunder",
        "Phoenix Suns",
        "Portland Trail Blazers",
        "Sacramento Kings",
        "San Antonio Spurs",
        "Utah Jazz",
    ),
}

NFL_CONFERENCES: dict[str, tuple[str, ...]] = {
    "AFC": (
        "Baltimore Ravens",
        "Buffalo Bills",
        "Cincinnati Bengals",
        "Cleveland Browns",
        "Denver Broncos",
        "Houston Texans",
        "Indianapolis Colts",
        "Jacksonville Jaguars",
        "Kansas City Chiefs",
        "Las Vegas Raiders",
        "Los Angeles Chargers",
        "Miami Dolphins",
        "New England Patriots",
        "New York Jets",
        "Pittsburgh Steelers",
        "Tennessee Titans",
    ),
    "NFC": (
        "Arizona Cardinals",
        "Atlanta Falcons",
        "Carolina Panthers",
        "Chicago Bears",
        "Dallas Cowboys",
        "Detroit Lions",
        "Green Bay Packers",
        "Los Angeles Rams",
        "Minnesota Vikings",
        "New Orleans Saints",
        "New York Giants",
        "Philadelphia Eagles",
        "San Francisco 49ers",
        "Seattle Seahawks",
        "Tampa Bay Buccaneers",
        "Washington Commanders",
    ),
}

_TEAM_SHORT_CODES: dict[str, str] = {
    "edmonton oilers": "EDM",
    "minnesota wild": "MIN",
    "carolina hurricanes": "CAR",
    "vegas golden knights": "VGK",
    "tampa bay lightning": "TBL",
    "colorado avalanche": "COL",
    "dallas stars": "DAL",
    "new jersey devils": "NJD",
    "montreal canadiens": "MTL",
    "florida panthers": "FLA",
    "ottawa senators": "OTT",
    "utah mammoth": "UTA",
    "boston bruins": "BOS",
    "washington capitals": "WSH",
    "new york rangers": "NYR",
    "nashville predators": "NSH",
    "new york islanders": "NYI",
    "anaheim ducks": "ANA",
    "st louis blues": "STL",
    "los angeles kings": "LAK",
    "winnipeg jets": "WPG",
    "seattle kraken": "SEA",
    "buffalo sabres": "BUF",
    "san jose sharks": "SJS",
    "philadelphia flyers": "PHI",
    "columbus blue jackets": "CBJ",
    "calgary flames": "CGY",
    "pittsburgh penguins": "PIT",
    "toronto maple leafs": "TOR",
    "chicago blackhawks": "CHI",
    "detroit red wings": "DET",
    "vancouver canucks": "VAN",
}

_PROP_SUFFIX_RE = re.compile(
    r"\s+(?:to\s+(?:win|make|beat|lead|leave|host|perform|direct)|at\s+end\s+of|by\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)).*$",
    re.IGNORECASE,
)
_NCAA_MASCOT_TAIL_RE = re.compile(
    r"\s+(?:crimson tide|hoosiers|wildcats|bulldogs|tar heels|blue devils|boilermakers|"
    r"buckeyes|wolverines|gators|longhorns|aggies|tigers|bears|cougars|ducks|huskies|"
    r"volunteers|sooners|jayhawks|spartans|seminoles|hurricanes|cavaliers|hokies|cardinals|"
    r"nittany lions|badgers|hawkeyes|fighting illini|golden gophers|cornhuskers|razorbacks|"
    r"rebels|commodores|gamecocks|yellow jackets|demon deacons|wolfpack|orange|irish|bruins|"
    r"trojans|sun devils|utes|buffaloes|aztecs|rams|lobos|falcons|zips|mountaineers|eagles)\s*$",
    re.IGNORECASE,
)
_ROLE_PREFIX_RE = re.compile(
    r"^(?:artist performing (?:the )?|actress cast as |actor cast as |next |202\d )",
    re.IGNORECASE,
)


def fold_unicode_name(name: str) -> str:
    """Fold Unicode accents, punctuation, and whitespace for canonical matching."""
    decomposed = "".join(c for c in unicodedata.normalize("NFKD", name or "") if not unicodedata.combining(c))
    cleaned = decomposed.replace(".", " ").strip().lower()
    return re.sub(r"\s+", " ", cleaned)


def canonical_contender_name(name: str) -> str:
    """Map product/brand contenders onto their canonical organization (e.g. Gemini -> Google)."""
    stripped = _PROP_SUFFIX_RE.sub("", (name or "").strip())
    folded = fold_unicode_name(stripped)
    if folded in CANONICAL_CONTENDER_ALIASES:
        return CANONICAL_CONTENDER_ALIASES[folded]
    return stripped


def compose_short_member_label(label: str, *, max_len: int = 16) -> str:
    """Build a short readable label for every member row, role, or axis mark."""
    s = _ROLE_PREFIX_RE.sub("", (label or "").strip())
    s = _PROP_SUFFIX_RE.sub("", s).strip(" :-")
    if len(s) <= max_len:
        return s
    parts = s.split()
    if len(parts) == 2:
        initial_last = f"{parts[0][0]}. {parts[1]}"
        if len(initial_last) <= max_len:
            return initial_last
        if "-" in parts[1]:
            first_hyphen = f"{parts[0][0]}. {parts[1].split('-')[0]}"
            if len(first_hyphen) <= max_len:
                return first_hyphen
    out: list[str] = []
    for part in parts:
        candidate = " ".join(out + [part])
        if len(candidate) > max_len - 1 and out:
            break
        out.append(part)
    joined = " ".join(out) if out else s[: max_len - 1]
    return joined if len(joined) <= max_len else s[: max_len - 1].rstrip() + "…"


def team_conference(team_name: str, league: str = "nhl") -> Optional[str]:
    """Return a team's conference ('Eastern'/'Western' or 'AFC'/'NFC') when known."""
    tables = {
        "nhl": NHL_CONFERENCES,
        "nba": NBA_CONFERENCES,
        "nfl": NFL_CONFERENCES,
    }
    table = tables.get(league.lower(), NHL_CONFERENCES)
    target = fold_unicode_name(team_name)
    for conf, teams in table.items():
        for team in teams:
            if fold_unicode_name(team) == target:
                return conf
    return None


def team_short_code(team_name: str) -> str:
    """Return a concise 2-4 char code for compact bubble/cut labels."""
    folded = fold_unicode_name(team_name)
    if folded in _TEAM_SHORT_CODES:
        return _TEAM_SHORT_CODES[folded]
    espn_path = _ESPN_TEAM_LOGOS.get(folded) or _ESPN_TEAM_LOGOS.get(fold_unicode_name(_NCAA_MASCOT_TAIL_RE.sub("", team_name)))
    if espn_path:
        tail = espn_path.rsplit("/", 1)[-1].split(".", 1)[0]
        if tail.isalpha() and 2 <= len(tail) <= 4:
            return tail.upper()
    words = [w for w in folded.split() if w]
    if len(words) >= 2:
        return words[-1][:3].upper()
    return folded[:3].upper()


def _espn_logo_direct(name: str) -> Optional[str]:
    folded = fold_unicode_name(name)
    no_mascot = fold_unicode_name(_NCAA_MASCOT_TAIL_RE.sub("", name))
    for cand in (folded, no_mascot):
        path = _ESPN_TEAM_LOGOS.get(cand)
        if path:
            return f"https://a.espncdn.com/i/teamlogos/{path}.png"
    return None


def resolve_member_art(
    name: str,
    *,
    sport_key: Optional[str] = None,
    resolver: Optional[SubjectArtResolver] = None,
    team_lookup: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Resolve a verified picture (logo, portrait, or poster) plus short label metadata for a member."""
    if resolver is not None:
        res = resolver
    else:
        from app.utils.container_machinery import SubjectArtResolver as RuntimeArtResolver, _default_art_resolver

        res = RuntimeArtResolver(team_lookup=team_lookup) if team_lookup is not None else _default_art_resolver()
    clean = _PROP_SUFFIX_RE.sub("", (name or "").strip())
    canonical = canonical_contender_name(clean)
    folded = fold_unicode_name(clean)
    no_punct = re.sub(r"[^a-zA-Z0-9 ]+", " ", clean).strip()
    sk_safe = sport_key if (sport_key and "_" in sport_key) else None

    candidates: list[str] = []
    for c in (clean, name.strip(), canonical, no_punct, folded.title()):
        if c and c not in candidates:
            candidates.append(c)

    art: dict[str, Any] = {}
    for cand in candidates:
        for sk_arg in ((sk_safe, None) if sk_safe else (None,)):
            candidate_art = res.resolve(cand, sport_key=sk_arg, allow_team_lookup=True)
            if candidate_art.get("url"):
                art = dict(candidate_art)
                break
        if art.get("url"):
            break

    if not art.get("url"):
        espn_url = _espn_logo_direct(clean) or _espn_logo_direct(canonical)
        if espn_url:
            art = {
                "url": espn_url,
                "kind": "team_logo",
                "detail": team_short_code(clean),
                "accent_color": "#0F172A",
                "initials": team_short_code(clean)[:2],
            }

    if not art:
        art = dict(res.resolve(clean or name, allow_team_lookup=False))

    kind = str(art.get("kind") or "")
    if kind in {"team_logo", "organization", "flag"}:
        presentation = "logo"
    elif "poster" in kind or kind == "film":
        presentation = "poster"
    else:
        presentation = "portrait"

    return {
        "url": art.get("url"),
        "kind": kind or "monogram",
        "presentation": presentation,
        "detail": str(art.get("detail") or ""),
        "accent_color": str(art.get("accent_color") or "#2563EB"),
        "initials": str(art.get("initials") or team_short_code(clean)[:2]),
        "short_label": compose_short_member_label(clean or name),
        "canonical_name": canonical,
    }
