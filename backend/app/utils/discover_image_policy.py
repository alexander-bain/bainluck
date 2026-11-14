"""Discover image truth policy, verified entity art resolver, and monogram fallback (#12659).

Enforces Alex's Discover image rules across `/api/feed`, `/api/entertainment`, and
background image enrichment:

1. A **person**, **team**, **film**, or **song** (and named public companies /
   tickers) NEVER gets a stock photo (`images.pexels.com`).
2. Music / song / album / chart markets NEVER wear TMDB film backdrops
   (`image.tmdb.org`).
3. Known wrong, misleading, clip-art, or duplicate Pexels photo IDs audited on
   Discover are blocked on every market kind.
4. Where a verified real poster, album cover, headshot, or official team/nation
   crest is registered, serve that exact `https` URL with its `image_presentation`
   hint (`"portrait"`, `"logo"`, `"cover"`, `"photo"`).
5. Otherwise, clear any disallowed stock image to `None` and emit a deterministic
   `image_monogram` (`initials` on a rich subject colour) so no card renders a
   stock photo on a person/team/film/song or a blank mystery box.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.utils.nation_flags import flag_url as nation_flag_url

logger = logging.getLogger(__name__)

_REGISTER_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "discover"
    / "verified_discover_art.json"
)

# Pexels stock photos audited as wrong, misleading, clip-art, or duplicate on
# Discover's first 60 seats (#12659).
BLOCKED_PEXELS_PHOTO_IDS: frozenset[str] = frozenset(
    {
        "8919548",   # "2021 TO INVEST OR TO SELL?" Bitcoin coins on Fed & Rates
        "6289047",   # Toy red rocket on "PROFIT" flashcard (Kimi IPO)
        "6289061",   # Plastic toy bomb on $100 bill + "STOCKS" flashcard (Bloomberg IPO)
        "31825810",  # Shirtless rugby players holding sports cup (French election)
        "3970331",   # Johns Hopkins COVID-19 Global Cases dashboard (U.S. confirm aliens)
        "9321371",   # Brazilian Portuguese impeachment banner (U.S. House impeach Trump)
        "8728168",   # Sci-fi lab coat hologram (Jensen Huang divorce)
        "11460276",  # Taipei street rally (Jensen Huang Congress testimony)
        "12786869",  # "LOST CAT WOLF" utility-pole flyer (Most Searched People)
        "6326317",   # Unrelated man with megaphone (Jensen Huang Congress testimony)
        "32417524",  # Wooden blocks "2026" generic flatlay (AI bundle)
        "8850837",   # Duplicate "POLITICS" newspaper flatlay
        "8850633",   # Duplicate "POLITICS" newspaper flatlay
        "8044086",   # Stock vocal microphone on Song of the Year
        "18326060",  # Stock tuxedo silhouette on Next James Bond actor
    }
)

_PEXELS_ID_RE = re.compile(r"/photos/(\d+)/")

# Rich, high-contrast deterministic subject colours for `initials on a colour`.
_MONOGRAM_PALETTE: tuple[tuple[str, str], ...] = (
    ("#1e3a8a", "#2563eb"),  # Royal cobalt
    ("#312e81", "#4f46e5"),  # Civic indigo
    ("#0f766e", "#14b8a6"),  # Editorial teal
    ("#7c2d12", "#ea580c"),  # Burnt sienna
    ("#581c87", "#9333ea"),  # Deep plum
    ("#831843", "#db2777"),  # Crimson rose
    ("#14532d", "#16a34a"),  # Forest emerald
    ("#7f1d1d", "#dc2626"),  # Arena crimson
    ("#1e293b", "#475569"),  # Cinema slate
    ("#78350f", "#d97706"),  # Warm amber
)

# Official ESPN CDN team & club logos (`https://a.espncdn.com/i/teamlogos/<league>/500/<code>.png`).
_ESPN_TEAM_LOGOS: dict[str, str] = {
    # NHL (32)
    "anaheim ducks": "nhl/500/ana",
    "boston bruins": "nhl/500/bos",
    "buffalo sabres": "nhl/500/buf",
    "calgary flames": "nhl/500/cgy",
    "carolina hurricanes": "nhl/500/car",
    "car hurricanes": "nhl/500/car",
    "chicago blackhawks": "nhl/500/chi",
    "colorado avalanche": "nhl/500/col",
    "columbus blue jackets": "nhl/500/cbj",
    "dallas stars": "nhl/500/dal",
    "detroit red wings": "nhl/500/det",
    "edmonton oilers": "nhl/500/edm",
    "edm oilers": "nhl/500/edm",
    "florida panthers": "nhl/500/fla",
    "los angeles kings": "nhl/500/la",
    "minnesota wild": "nhl/500/min",
    "min wild": "nhl/500/min",
    "montreal canadiens": "nhl/500/mtl",
    "nashville predators": "nhl/500/nsh",
    "new jersey devils": "nhl/500/nj",
    "nj devils": "nhl/500/nj",
    "new york islanders": "nhl/500/nyi",
    "new york rangers": "nhl/500/nyr",
    "ottawa senators": "nhl/500/ott",
    "philadelphia flyers": "nhl/500/phi",
    "pittsburgh penguins": "nhl/500/pit",
    "san jose sharks": "nhl/500/sj",
    "seattle kraken": "nhl/500/sea",
    "st louis blues": "nhl/500/stl",
    "tampa bay lightning": "nhl/500/tb",
    "toronto maple leafs": "nhl/500/tor",
    "utah hockey club": "nhl/500/utah",
    "utah mammoth": "nhl/500/utah",
    "vancouver canucks": "nhl/500/van",
    "vegas golden knights": "nhl/500/vgk",
    "washington capitals": "nhl/500/wsh",
    "winnipeg jets": "nhl/500/wpg",
    # NFL (32 + short names)
    "arizona cardinals": "nfl/500/ari",
    "atlanta falcons": "nfl/500/atl",
    "baltimore ravens": "nfl/500/bal",
    "buffalo bills": "nfl/500/buf",
    "carolina panthers": "nfl/500/car",
    "chicago bears": "nfl/500/chi",
    "cincinnati bengals": "nfl/500/cin",
    "cleveland browns": "nfl/500/cle",
    "dallas cowboys": "nfl/500/dal",
    "denver broncos": "nfl/500/den",
    "broncos": "nfl/500/den",
    "detroit lions": "nfl/500/det",
    "green bay packers": "nfl/500/gb",
    "houston texans": "nfl/500/hou",
    "indianapolis colts": "nfl/500/ind",
    "jacksonville jaguars": "nfl/500/jax",
    "kansas city chiefs": "nfl/500/kc",
    "las vegas raiders": "nfl/500/lv",
    "los angeles chargers": "nfl/500/lac",
    "los angeles rams": "nfl/500/lar",
    "miami dolphins": "nfl/500/mia",
    "minnesota vikings": "nfl/500/min",
    "new england patriots": "nfl/500/ne",
    "new orleans saints": "nfl/500/no",
    "new york giants": "nfl/500/nyg",
    "new york jets": "nfl/500/nyj",
    "philadelphia eagles": "nfl/500/phi",
    "pittsburgh steelers": "nfl/500/pit",
    "san francisco 49ers": "nfl/500/sf",
    "49ers": "nfl/500/sf",
    "seattle seahawks": "nfl/500/sea",
    "tampa bay buccaneers": "nfl/500/tb",
    "tennessee titans": "nfl/500/ten",
    "washington commanders": "nfl/500/wsh",
    # NBA (30)
    "atlanta hawks": "nba/500/atl",
    "boston celtics": "nba/500/bos",
    "brooklyn nets": "nba/500/bkn",
    "charlotte hornets": "nba/500/cha",
    "chicago bulls": "nba/500/chi",
    "cleveland cavaliers": "nba/500/cle",
    "dallas mavericks": "nba/500/dal",
    "denver nuggets": "nba/500/den",
    "detroit pistons": "nba/500/det",
    "golden state warriors": "nba/500/gs",
    "houston rockets": "nba/500/hou",
    "indiana pacers": "nba/500/ind",
    "los angeles clippers": "nba/500/lac",
    "la clippers": "nba/500/lac",
    "los angeles lakers": "nba/500/lal",
    "memphis grizzlies": "nba/500/mem",
    "miami heat": "nba/500/mia",
    "milwaukee bucks": "nba/500/mil",
    "minnesota timberwolves": "nba/500/min",
    "new orleans pelicans": "nba/500/no",
    "new york knicks": "nba/500/ny",
    "oklahoma city thunder": "nba/500/okc",
    "orlando magic": "nba/500/orl",
    "philadelphia 76ers": "nba/500/phi",
    "phoenix suns": "nba/500/phx",
    "portland trail blazers": "nba/500/por",
    "sacramento kings": "nba/500/sac",
    "san antonio spurs": "nba/500/sa",
    "toronto raptors": "nba/500/tor",
    "utah jazz": "nba/500/utah",
    "washington wizards": "nba/500/wsh",
    # MLB (30)
    "arizona diamondbacks": "mlb/500/ari",
    "atlanta braves": "mlb/500/atl",
    "baltimore orioles": "mlb/500/bal",
    "boston red sox": "mlb/500/bos",
    "chicago cubs": "mlb/500/chc",
    "chicago white sox": "mlb/500/chw",
    "cincinnati reds": "mlb/500/cin",
    "cleveland guardians": "mlb/500/cle",
    "colorado rockies": "mlb/500/col",
    "detroit tigers": "mlb/500/det",
    "houston astros": "mlb/500/hou",
    "kansas city royals": "mlb/500/kc",
    "los angeles angels": "mlb/500/laa",
    "los angeles dodgers": "mlb/500/lad",
    "miami marlins": "mlb/500/mia",
    "milwaukee brewers": "mlb/500/mil",
    "minnesota twins": "mlb/500/min",
    "new york mets": "mlb/500/nym",
    "new york yankees": "mlb/500/nyy",
    "athletics": "mlb/500/oak",
    "oakland athletics": "mlb/500/oak",
    "philadelphia phillies": "mlb/500/phi",
    "pittsburgh pirates": "mlb/500/pit",
    "san diego padres": "mlb/500/sd",
    "san francisco giants": "mlb/500/sf",
    "seattle mariners": "mlb/500/sea",
    "st louis cardinals": "mlb/500/stl",
    "tampa bay rays": "mlb/500/tb",
    "texas rangers": "mlb/500/tex",
    "toronto blue jays": "mlb/500/tor",
    "washington nationals": "mlb/500/wsh",
    # NCAA / CFP contenders
    "indiana": "ncaa/500/84",
    "indiana hoosiers": "ncaa/500/84",
    "ohio state": "ncaa/500/194",
    "ohio state buckeyes": "ncaa/500/194",
    "oregon": "ncaa/500/2483",
    "oregon ducks": "ncaa/500/2483",
    "texas": "ncaa/500/251",
    "texas longhorns": "ncaa/500/251",
    "georgia": "ncaa/500/61",
    "georgia bulldogs": "ncaa/500/61",
    "penn state": "ncaa/500/213",
    "notre dame": "ncaa/500/87",
    "alabama": "ncaa/500/333",
    "tennessee": "ncaa/500/2633",
    "clemson": "ncaa/500/228",
    "boise state": "ncaa/500/68",
    "smu": "ncaa/500/2567",
    # Liga Profesional Argentina & global clubs
    "aldosivi": "soccer/500/9739",
    "sarmiento": "soccer/500/10158",
    "velez sarsfield": "soccer/500/21",
    "river plate": "soccer/500/16",
    "boca juniors": "soccer/500/5",
    "racing club": "soccer/500/15",
    "independiente": "soccer/500/11",
    "san lorenzo": "soccer/500/18",
}

_MUSIC_TITLE_RE = re.compile(
    r"\b("
    r"grammys?|grammy\s+awards?|latin\s+grammys?|"
    r"song\s+of\s+the\s+year|record\s+of\s+the\s+year|album\s+of\s+the\s+year|"
    r"best\s+[a-z\s]{0,30}\s+(?:album|song|music\s+performance|rap\s+performance|pop\s+solo\s+performance|vocal\s+album)|"
    r"billboard\s+(?:hot\s+100|200)|spotify|apple\s+music|"
    r"gta\s+vi:\s+the\s+album|featured\s+on\s+.*album|"
    r"eurovision|halftime\s+show\s+headliner"
    r")\b",
    re.IGNORECASE,
)
_FILM_TITLE_RE = re.compile(
    r"\b("
    r"oscars?|academy\s+awards?|golden\s+globes?|emmys?|bafta|cannes|"
    r"best\s+(?:picture|director|actor|actress|casting|animated\s+feature|screenplay)|"
    r"rotten\s+tomatoes|box\s+office|opening\s+weekend|"
    r"james\s+bond|next\s+007|marvel|star\s+wars|dc\s+studios"
    r")\b",
    re.IGNORECASE,
)
_TEAM_SPORT_CATS: frozenset[str] = frozenset(
    {
        "basketball",
        "football",
        "baseball",
        "hockey",
        "soccer",
        "rugby",
        "cricket",
    }
)
_TEAM_TITLE_RE = re.compile(
    r"\b("
    r"super\s+bowl\s+(?:winner|champion|matchup)|"
    r"stanley\s+cup|world\s+series|nba\s+finals|nba\s+champion|"
    r"world\s+cup\s+(?:winner|champion)|champions\s+league|"
    r"playoffs?|division\s+(?:winner|front-runners)|relegated|relegation|"
    r"college\s+football\s+playoff"
    r")\b",
    re.IGNORECASE,
)
_TICKER_RE = re.compile(r"\(([A-Z]{2,5})\)")
_ORG_TITLE_RE = re.compile(
    r"\b("
    r"ipo|quarterly\s+earnings|beat\s+earnings|market\s+cap|"
    r"kimi|moonshot\s+ai|bloomberg|openai|anthropic|spacex|stripe|databricks"
    r")\b",
    re.IGNORECASE,
)
_PARTY_OR_BUCKET_OUTCOME_RE = re.compile(
    r"^("
    r"yes|no|not\s+.+|none|no\s+change|no\s+head\s+of\s+state|"
    r"before\s+.+|after\s+.+|by\s+.+|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}.*|"
    r"above\s+.+|below\s+.+|top\s+\d+|"
    r"[\$<>≤≥\-+\d\.%\s]+(?:\s+bps.*)?|"
    r".*\([A-Z]{2,5}\)$"
    r")$",
    re.IGNORECASE,
)
_PERSON_HEADLINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^Will\s+([A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+(?:\s+(?:de|le|la|van|von|di|del|da|[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ\.\-']*)){1,3}?)\s+"
        r"(?:join|attend|testify|publicly\s+testify|resign|step\s+down|win|beat|divorce|leave|endorse|pardon|visit|meet)\b"
    ),
    re.compile(
        r"^([A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+(?:\s+(?:de|le|la|van|von|di|del|da|[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ\.\-']*)){1,3}?)\s+"
        r"(?:out\s+as|divorce|impeached|pardoned|arrested|confirmed\s+as)\b"
    ),
    re.compile(r"\bimpeach\s+(Trump|Biden|Macron|Lula|Yoon)\b", re.IGNORECASE),
    re.compile(r"\bWill\s+(Trump|Putin|Netanyahu|Zelenskyy?|Xi\s+Jinping|Modi)\s+be\b", re.IGNORECASE),
)
_PERSON_ELECTION_OR_ROLE_RE = re.compile(
    r"\b("
    r"presidential\s+election|governor\s+election|mayor\s+election|"
    r"prime\s+minister|minister\s+of\s+finance|leader\s+end\s+of|"
    r"next\s+ceo\s+of|most\s+searched\s+people|ufc\s+.*champion|mvp\s+winner"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VisualSubject:
    kind: str  # "person" | "team" | "film" | "song" | "organization" | "topic"
    label: str
    initials: str
    bg_hex: str
    accent_hex: str


def _fold_ascii(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9\s]", " ", ascii_only.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


_register_cache: dict[str, dict[str, str]] | None = None


def _load_verified_register() -> dict[str, dict[str, str]]:
    global _register_cache
    if _register_cache is not None:
        return _register_cache
    index: dict[str, dict[str, str]] = {}
    try:
        doc = json.loads(_REGISTER_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("verified_discover_art.json unreadable: %s", exc)
        _register_cache = index
        return index

    allowed = set(doc.get("allowed_hosts") or [])
    for entry in doc.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "").strip()
        verified = str(entry.get("verified_subject") or "").strip()
        if not url or not verified:
            continue
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc not in allowed:
            logger.warning("Refusing unverified host in discover art register: %s", url)
            continue
        record = {
            "url": url,
            "kind": str(entry.get("kind") or "person"),
            "presentation": str(entry.get("presentation") or "photo"),
            "credit": str(entry.get("credit") or ""),
            "verified_subject": verified,
        }
        for alias in entry.get("aliases") or []:
            norm = _fold_ascii(str(alias))
            if norm and norm not in index:
                index[norm] = record
    _register_cache = index
    return index


def is_pexels_url(url: str | None) -> bool:
    if not url:
        return False
    host = urlparse(url).netloc.lower()
    return host.endswith("pexels.com")


def is_tmdb_url(url: str | None) -> bool:
    if not url:
        return False
    host = urlparse(url).netloc.lower()
    return host.endswith("tmdb.org")


def is_blocked_pexels_photo(url: str | None) -> bool:
    if not url or not is_pexels_url(url):
        return False
    match = _PEXELS_ID_RE.search(url)
    if not match:
        return False
    return match.group(1) in BLOCKED_PEXELS_PHOTO_IDS


def _palette_for(label: str, kind: str) -> tuple[str, str]:
    if kind == "film":
        return ("#1e293b", "#475569")
    if kind == "song":
        return ("#581c87", "#9333ea")
    digest = hashlib.sha256(_fold_ascii(label or kind).encode("utf-8")).digest()
    return _MONOGRAM_PALETTE[digest[0] % len(_MONOGRAM_PALETTE)]


_INITIALS_NOISE_WORDS: frozenset[str] = frozenset(
    {
        "the", "of", "and", "or", "in", "on", "at", "to", "for", "from", "with",
        "will", "who", "what", "when", "where", "which", "how", "high", "low",
        "be", "is", "are", "does", "do", "a", "an", "by", "before", "after",
        "end", "during", "through", "next", "new", "announced", "announce",
        "win", "wins", "winner", "champion", "championship", "election",
        "ipo", "closing", "market", "cap", "quarterly", "earnings", "beat",
        "close", "above", "below", "go", "reach", "hit",
        "rotten", "tomatoes", "score", "opening", "weekend", "domestic", "box", "office",
        "inc", "corp", "corporation", "ltd", "llc", "plc", "holdings", "group",
    }
)


def compute_initials(label: str | None, *, ticker_ok: bool = True) -> str:
    raw = (label or "").strip()
    if not raw:
        return "BL"
    if ticker_ok:
        ticker_match = _TICKER_RE.search(raw)
        if ticker_match:
            return ticker_match.group(1)[:5].upper()
    # Special case: "Kimi (Moonshot AI)" -> "KM"
    if re.search(r"\bkimi\b.*\bmoonshot\b", raw, re.IGNORECASE):
        return "KM"
    # Strip trailing artist separator for song titles ("Choosin' Texas - Ella Langley")
    if " - " in raw:
        raw = raw.split(" - ", 1)[0].strip()
    if ": " in raw and raw.lower().startswith(("afc ", "nfc ", "al ", "nl ")):
        raw = raw.split(": ", 1)[1].strip()
    # Remove parenthetical qualifiers so "(Men's)" or "(2026)" never becomes the last initial
    raw_no_parens = re.sub(r"\([^)]*\)", " ", raw).strip() or raw

    raw_tokens = [
        re.sub(r"[^A-Za-z0-9À-ÖØ-öø-ÿ]", "", w)
        for w in raw_no_parens.split()
    ]
    raw_tokens = [w for w in raw_tokens if w]
    filtered = [
        w
        for w in raw_tokens
        if w.lower() not in _INITIALS_NOISE_WORDS
        and not re.fullmatch(r"(?:\d+|q[1-4]|\d+(?:st|nd|rd|th))", w.lower())
    ]
    words = filtered or [
        w for w in raw_tokens if not re.fullmatch(r"\d+", w)
    ] or raw_tokens
    if not words:
        return "BL"
    if len(words) == 1:
        word = words[0].upper()
        return word[:3] if len(word) <= 3 and word.isalpha() else word[:2]
    second_idx = -1 if len(words) <= 3 else 1
    return (words[0][0] + words[second_idx][0]).upper()


def _first_meaningful_outcome_name(top_outcomes: list[dict[str, Any]] | None) -> str | None:
    for out in top_outcomes or []:
        if not isinstance(out, dict):
            continue
        name = str(out.get("name") or out.get("label") or "").strip()
        if not name:
            continue
        if _PARTY_OR_BUCKET_OUTCOME_RE.match(name):
            continue
        return name
    return None


def _looks_like_person_name(text: str | None) -> bool:
    if not text:
        return False
    tokens = [t for t in text.strip().split() if t]
    if not (2 <= len(tokens) <= 4):
        return False
    bad_words = {
        "party", "congress", "united", "states", "republic", "city", "county",
        "team", "club", "hurricanes", "dodgers", "49ers", "yankees", "brewers",
        "celtics", "wild", "oilers", "devils", "avalanche", "apple", "nvidia",
        "alphabet", "microsoft", "amazon", "tesla", "google", "meta", "above",
        "below", "before", "after", "top", "no", "yes",
    }
    lower_tokens = {re.sub(r"[^a-z]", "", t.lower()) for t in tokens}
    if lower_tokens & bad_words:
        return False
    return all(t[0].isupper() for t in tokens if t[0].isalpha())


def classify_market_visual_subject(
    name: str | None,
    category: str | None = None,
    top_outcomes: list[dict[str, Any]] | None = None,
) -> VisualSubject:
    title = (name or "").strip()
    cat = (category or "").strip().lower()
    lead_outcome = _first_meaningful_outcome_name(top_outcomes)

    # 1. Song / music / album / chart
    if _MUSIC_TITLE_RE.search(title):
        subj = lead_outcome or title
        bg, acc = _palette_for(subj, "song")
        return VisualSubject("song", subj, compute_initials(subj, ticker_ok=False), bg, acc)

    # 2. Explicit person in headline (e.g., "Will Justin Bieber attend Super Bowl LXI?",
    #    "Jensen Huang divorce...", "Howard Lutnick out as Secretary of Commerce...")
    for pat in _PERSON_HEADLINE_PATTERNS:
        m = pat.search(title)
        if m:
            person_raw = m.group(1).strip()
            if person_raw.lower() == "trump":
                person_raw = "Donald Trump"
            elif person_raw.lower() == "putin":
                person_raw = "Vladimir Putin"
            bg, acc = _palette_for(person_raw, "person")
            return VisualSubject("person", person_raw, compute_initials(person_raw, ticker_ok=False), bg, acc)

    # 3. Film / TV / Screen awards (note: actor role markets with a person leader
    #    like "Next James Bond actor?" -> Robert Pattinson resolve on the actor if present)
    if _FILM_TITLE_RE.search(title) or (cat == "entertainment" and '"' in title):
        if lead_outcome and _looks_like_person_name(lead_outcome) and "actor" in title.lower():
            bg, acc = _palette_for(lead_outcome, "person")
            return VisualSubject("person", lead_outcome, compute_initials(lead_outcome, ticker_ok=False), bg, acc)
        quoted = re.search(r'["“]([^"”]{2,80})["”]', title)
        subj = quoted.group(1).strip() if quoted else (lead_outcome or title)
        bg, acc = _palette_for(subj, "film")
        return VisualSubject("film", subj, compute_initials(subj, ticker_ok=False), bg, acc)

    # 4. Sports team / club / nation championship or playoff
    if cat == "mma" or "ufc" in title.lower():
        subj = lead_outcome or title
        bg, acc = _palette_for(subj, "person")
        return VisualSubject("person", subj, compute_initials(subj, ticker_ok=False), bg, acc)

    if cat in _TEAM_SPORT_CATS or _TEAM_TITLE_RE.search(title):
        subj = lead_outcome or title
        if " vs " in subj.lower():
            subj = re.split(r"\s+vs\.?\s+", subj, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        bg, acc = _palette_for(subj, "team")
        return VisualSubject("team", subj, compute_initials(subj, ticker_ok=False), bg, acc)

    # 5. Candidate / leader / CEO / Most Searched People markets whose leader is a person
    if _PERSON_ELECTION_OR_ROLE_RE.search(title) and lead_outcome and _looks_like_person_name(lead_outcome):
        bg, acc = _palette_for(lead_outcome, "person")
        return VisualSubject("person", lead_outcome, compute_initials(lead_outcome, ticker_ok=False), bg, acc)

    # 6. Named company / ticker / IPO
    ticker_m = _TICKER_RE.search(title)
    if ticker_m or _ORG_TITLE_RE.search(title):
        # Extract company name if present before ticker
        comp_m = re.search(
            r"(?:Will|How\s+high\s+will)\s+([A-Z][A-Za-z0-9\s\.\(\)&\-]{1,40}?\([A-Z]{2,5}\)|Kimi\s*\(Moonshot\s*AI\)|Bloomberg)",
            title,
        )
        subj = comp_m.group(1).strip() if comp_m else title
        bg, acc = _palette_for(subj, "organization")
        return VisualSubject("organization", subj, compute_initials(subj, ticker_ok=True), bg, acc)

    # 7. General macro / weather / geopolitics / infrastructure topic
    bg, acc = _palette_for(title or cat or "Discover", "topic")
    return VisualSubject("topic", title or "Discover", compute_initials(title, ticker_ok=False), bg, acc)


def _lookup_team_or_nation_logo(candidate: str | None) -> str | None:
    if not candidate:
        return None
    raw = candidate.strip()
    if " vs " in raw.lower():
        raw = re.split(r"\s+vs\.?\s+", raw, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    if ": " in raw and raw.lower().startswith(("afc ", "nfc ", "al ", "nl ")):
        raw = raw.split(": ", 1)[1].strip()
    norm = _fold_ascii(raw)
    if norm in _ESPN_TEAM_LOGOS:
        return f"https://a.espncdn.com/i/teamlogos/{_ESPN_TEAM_LOGOS[norm]}.png"
    flag = nation_flag_url(raw, size="w320")
    if flag:
        return flag
    return None


def _lookup_verified_entry(
    name: str | None,
    subject: VisualSubject,
    top_outcomes: list[dict[str, Any]] | None = None,
) -> dict[str, str] | None:
    reg = _load_verified_register()
    candidates: list[str] = [subject.label]
    lead = _first_meaningful_outcome_name(top_outcomes)
    if lead and lead not in candidates:
        candidates.append(lead)
        if " - " in lead:
            song_part, artist_part = lead.split(" - ", 1)
            candidates.extend([song_part.strip(), artist_part.strip()])
    if name:
        candidates.append(name)

    # Exact alias match first
    for cand in candidates:
        norm = _fold_ascii(cand)
        if norm in reg:
            return reg[norm]

    # Substring phrase match on longer registered aliases (>= 8 chars) against market title
    norm_title = f" {_fold_ascii(name)} "
    if len(norm_title) > 4:
        for alias_norm, entry in reg.items():
            if len(alias_norm) >= 8 and f" {alias_norm} " in norm_title:
                return entry
    return None


def _presentation_for_url(url: str, fallback: str = "photo") -> str:
    host = urlparse(url).netloc.lower()
    if "espncdn.com" in host and "/teamlogos/" in url:
        return "logo"
    if "flagcdn.com" in host:
        return "logo"
    if "espncdn.com" in host and "/headshots/" in url:
        return "portrait"
    if "archive.org" in host or "coverartarchive.org" in host:
        return "cover"
    return fallback


def should_skip_pexels_enrichment(name: str | None, category: str | None = None) -> bool:
    """Return True when a market must NEVER receive a Pexels stock photo."""
    subj = classify_market_visual_subject(name, category, None)
    return subj.kind in {"person", "team", "film", "song", "organization"}


def resolve_discover_market_image(
    *,
    name: str | None,
    category: str | None = None,
    top_outcomes: list[dict[str, Any]] | None = None,
    image_url: str | None = None,
    image_width: int | None = None,
    image_height: int | None = None,
) -> dict[str, Any]:
    """Return resolved `{image_url, image_width, image_height, image_presentation, image_monogram, image_credit}`."""
    subject = classify_market_visual_subject(name, category, top_outcomes)
    existing = (image_url or "").strip() or None

    # 1. Keep existing real non-stock art if valid for this subject
    if existing and not is_pexels_url(existing):
        if subject.kind == "song" and is_tmdb_url(existing):
            existing = None
        else:
            pres = _presentation_for_url(existing, "photo")
            credit = "TMDB" if is_tmdb_url(existing) else None
            return {
                "image_url": existing,
                "image_width": image_width,
                "image_height": image_height,
                "image_presentation": pres,
                "image_monogram": None,
                **({"image_credit": credit} if credit else {}),
            }

    # 2. Check verified entity/landmark register
    verified = _lookup_verified_entry(name, subject, top_outcomes)
    if verified:
        url = verified["url"]
        return {
            "image_url": url,
            "image_width": None,
            "image_height": None,
            "image_presentation": verified["presentation"],
            "image_monogram": None,
            **(
                {"image_credit": verified["credit"]}
                if verified.get("credit")
                else {}
            ),
        }

    # 3. Check official team / club / nation crest map
    if subject.kind == "team":
        logo_url = _lookup_team_or_nation_logo(subject.label)
        if not logo_url and top_outcomes:
            for out in top_outcomes[:3]:
                if isinstance(out, dict):
                    logo_url = _lookup_team_or_nation_logo(out.get("name") or out.get("label"))
                    if logo_url:
                        break
        if logo_url:
            return {
                "image_url": logo_url,
                "image_width": 500 if "espncdn.com" in logo_url else 320,
                "image_height": 500 if "espncdn.com" in logo_url else 213,
                "image_presentation": "logo",
                "image_monogram": None,
            }

    # 4. For general non-entity topic markets ONLY, keep non-blocked Pexels photos
    if (
        existing
        and subject.kind == "topic"
        and is_pexels_url(existing)
        and not is_blocked_pexels_photo(existing)
    ):
        return {
            "image_url": existing,
            "image_width": image_width,
            "image_height": image_height,
            "image_presentation": "photo",
            "image_monogram": None,
        }

    # 5. Deterministic `initials on a colour` monogram fallback (zero stock photos on entities)
    return {
        "image_url": None,
        "image_width": None,
        "image_height": None,
        "image_presentation": None,
        "image_monogram": {
            "initials": subject.initials,
            "label": subject.label,
            "kind": subject.kind,
            "bg_hex": subject.bg_hex,
            "accent_hex": subject.accent_hex,
        },
    }


def _normalize_golf_tournament_base_name(name: str | None) -> str:
    raw = (name or "").strip()
    raw = re.sub(
        r"\s+(?:driven|presented|sponsored)\s+by\s+.+$",
        "",
        raw,
        flags=re.IGNORECASE,
    )
    raw = re.sub(r"\s+at\s+[A-Z].+$", "", raw)
    return _fold_ascii(raw)


def dedup_discover_tournament_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse twin golf tournament feed items (e.g. 'The ANNIKA driven by Gainbridge at Pelican' + 'The ANNIKA')."""
    if len(items) <= 1:
        return items
    kept: list[dict[str, Any]] = []
    by_sig: dict[str, int] = {}

    for item in items:
        data = item.get("data") or {}
        base_name = _normalize_golf_tournament_base_name(data.get("name"))
        top_two = tuple(
            sorted(
                _fold_ascii(g.get("name"))
                for g in (data.get("golfers") or [])[:2]
                if isinstance(g, dict) and g.get("name")
            )
        )
        sig = base_name or ("|".join(top_two) if len(top_two) == 2 else "")
        # Also detect identical top-2 golfer pair in the same week
        pair_sig = f"pair:{'|'.join(top_two)}:{data.get('start_date') or ''}" if len(top_two) == 2 else ""

        existing_idx = by_sig.get(sig) if sig else None
        if existing_idx is None and pair_sig:
            existing_idx = by_sig.get(pair_sig)

        if existing_idx is None:
            idx = len(kept)
            kept.append(item)
            if sig:
                by_sig[sig] = idx
            if pair_sig:
                by_sig[pair_sig] = idx
            continue

        prev = kept[existing_idx]
        prev_data = prev.get("data") or {}
        # Prefer the entry with more sources or fuller sponsor/venue metadata, and merge blended market IDs
        prev_richness = (
            int(prev_data.get("source_count") or 0),
            1 if prev_data.get("venue") else 0,
            len(str(prev_data.get("name") or "")),
        )
        curr_richness = (
            int(data.get("source_count") or 0),
            1 if data.get("venue") else 0,
            len(str(data.get("name") or "")),
        )
        merged_blended = frozenset(prev.get("_blended_market_ids") or ()) | frozenset(
            item.get("_blended_market_ids") or ()
        )
        winner = dict(item if curr_richness > prev_richness else prev)
        winner["_blended_market_ids"] = merged_blended
        winner["score"] = max(float(prev.get("score") or 0), float(item.get("score") or 0))
        kept[existing_idx] = winner
    return kept


def resolve_tournament_discover_image(data: dict[str, Any]) -> dict[str, Any]:
    """Attach verified golfer portrait or golfer monogram to a Discover tournament `data` dict."""
    out = dict(data)
    golfers = out.get("golfers") or []
    leader_name = (
        str(out.get("champion") or "").strip()
        or (str(golfers[0].get("name") or "").strip() if golfers and isinstance(golfers[0], dict) else "")
    )
    resolved = resolve_discover_market_image(
        name=leader_name or out.get("name"),
        category="golf",
        top_outcomes=[{"name": leader_name}] if leader_name else None,
        image_url=out.get("image_url"),
    )
    if leader_name and resolved.get("image_url") is None:
        bg, acc = ("#14532d", "#16a34a")
        resolved["image_monogram"] = {
            "initials": compute_initials(leader_name, ticker_ok=False),
            "label": leader_name,
            "kind": "person",
            "bg_hex": bg,
            "accent_hex": acc,
        }
    out["image_url"] = resolved["image_url"]
    out["image_presentation"] = resolved["image_presentation"]
    out["image_monogram"] = resolved["image_monogram"]
    return out


def resolve_concept_discover_image(data: dict[str, Any]) -> dict[str, Any]:
    """Attach verified fighter/leader portrait or monogram to a Discover concept `data` dict."""
    out = dict(data)
    leader_obj = out.get("leader") if isinstance(out.get("leader"), dict) else None
    bout = out.get("headline_bout") if isinstance(out.get("headline_bout"), dict) else None
    primary_name = (
        str(out.get("winner") or "").strip()
        or (str(leader_obj.get("name") or "").strip() if leader_obj else "")
        or (str(bout.get("fighter_a") or bout.get("away_team") or "").strip() if bout else "")
        or str(out.get("name") or "").strip()
    )
    resolved = resolve_discover_market_image(
        name=out.get("name"),
        category="mma" if "ufc" in str(out.get("domain") or "").lower() else str(out.get("domain") or ""),
        top_outcomes=[{"name": primary_name}] if primary_name else None,
        image_url=out.get("image_url"),
    )
    out["image_url"] = resolved["image_url"]
    out["image_presentation"] = resolved["image_presentation"]
    out["image_monogram"] = resolved["image_monogram"]
    return out


def sanitize_discover_feed_item(item: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow-copied feed item with Discover image policy applied."""
    if not isinstance(item, dict):
        return item
    kind = item.get("type")
    raw_data = item.get("data")
    if not isinstance(raw_data, dict):
        return item

    if kind == "futures":
        resolved = resolve_discover_market_image(
            name=raw_data.get("name"),
            category=raw_data.get("llm_sport_category") or raw_data.get("category"),
            top_outcomes=raw_data.get("top_outcomes"),
            image_url=raw_data.get("image_url"),
            image_width=raw_data.get("image_width"),
            image_height=raw_data.get("image_height"),
        )
        new_data = {**raw_data, **resolved}
        return {**item, "data": new_data}

    if kind == "tournament":
        return {**item, "data": resolve_tournament_discover_image(raw_data)}

    if kind == "concept":
        return {**item, "data": resolve_concept_discover_image(raw_data)}

    if kind == "bundle":
        sub_items = [
            sanitize_discover_feed_item(sub) if isinstance(sub, dict) else sub
            for sub in (raw_data.get("items") or [])
        ]
        # Resolve bundle-level representative art or monogram for non-roundup / audit consumers
        # (`RoundupCard.tsx` deliberately renders text + bars only per Oct 6 R4).
        bundle_img: str | None = None
        bundle_pres: str | None = None
        bundle_mono: dict[str, Any] | None = None
        for sub in sub_items:
            if not isinstance(sub, dict):
                continue
            sd = sub.get("data") or {}
            if sd.get("image_url"):
                bundle_img = sd["image_url"]
                bundle_pres = sd.get("image_presentation")
                break
            if bundle_mono is None and sd.get("image_monogram"):
                bundle_mono = sd["image_monogram"]

        if not bundle_img:
            roundup = raw_data.get("roundup") if isinstance(raw_data.get("roundup"), dict) else None
            rows = (roundup.get("rows") if roundup else None) or []
            row_outcomes = [
                {"name": str(r.get("label") or "")}
                for r in rows[:3]
                if isinstance(r, dict) and r.get("label")
            ]
            # Handle subject_sequence like "Boston Celtics: next 3 games"
            title_str = str(raw_data.get("title") or "")
            subj_prefix = title_str.split(":", 1)[0].strip() if ":" in title_str else title_str
            team_logo = _lookup_team_or_nation_logo(subj_prefix)
            if team_logo:
                bundle_img = team_logo
                bundle_pres = "logo"
            else:
                fallback_res = resolve_discover_market_image(
                    name=title_str,
                    category=None,
                    top_outcomes=row_outcomes,
                    image_url=raw_data.get("image_url"),
                )
                bundle_img = fallback_res["image_url"]
                bundle_pres = fallback_res["image_presentation"]
                bundle_mono = bundle_mono or fallback_res["image_monogram"]

        new_data = {
            **raw_data,
            "items": sub_items,
            "image_url": bundle_img,
            "image_presentation": bundle_pres,
            "image_monogram": None if bundle_img else bundle_mono,
        }
        return {**item, "data": new_data}

    return item


def apply_discover_image_policy_in_place(item: dict[str, Any]) -> None:
    """Mutate a feed item's `data` dict in place to enforce Discover image policy."""
    if not isinstance(item, dict) or not isinstance(item.get("data"), dict):
        return
    sanitized = sanitize_discover_feed_item(item)
    if isinstance(sanitized.get("data"), dict):
        item["data"].clear()
        item["data"].update(sanitized["data"])


def sanitize_feed_response_images(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Non-mutatingly apply Discover image truth policy to a `/api/feed` response payload."""
    if not isinstance(payload, dict):
        return payload
    items = payload.get("items")
    if not isinstance(items, list):
        return payload
    return {
        **payload,
        "items": [sanitize_discover_feed_item(it) for it in items],
    }
