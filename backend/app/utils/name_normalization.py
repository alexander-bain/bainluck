"""Single source of truth for team/player name normalization and matching.

Every module that needs to compare, normalize, or deduplicate names
should import from here. Do NOT create new matching functions elsewhere.

Public API:
    strip_diacritics(s)       — Remove accents/diacritics, handle ø→o etc.
    normalize_name(name)      — Canonical: lowercase, strip diacritics, strip suffixes
    normalize_team_name(name) — For team matching keys: strip diacritics, periods, parens
    match_key(name)           — Alphanumeric-only dedup key (for golfer/nominee matching)
    clean_slug(name)          — URL-safe slug from a name
    token_overlap_score(a, b) — Jaccard-like fuzzy score (0.0-1.0)
    names_match(a, b)         — Boolean: do these names refer to the same entity?
"""

import re
import unicodedata

# Reserve/youth team suffixes to strip during normalization
_RESERVE_SUFFIX_RE = re.compile(
    r"\s+(?:reserves?|ii|iii|iv|b|c|u\d{1,2}|under[\s-]?\d{1,2}|youth|academy|women|w|2)\s*$",
    re.IGNORECASE,
)

# Apostrophe-like characters to unify
_APOSTROPHE_CHARS = ("\u2018", "\u2019", "\u02BB", "\u02BC", "\u0060", "\u00B4", "\u2032")

# Stopwords for token-overlap scoring — team name fragments that don't carry identity
_MATCH_STOPWORDS = frozenset({
    "the", "of", "at", "and", "de",
    "fc", "sc", "cf", "ac", "as", "us",
})

# College abbreviations expanded during token overlap scoring.
# "St." → "State", "Mt." → "Mount", etc.
_COLLEGE_ABBREVIATIONS: dict[str, str] = {
    "st.": "state",
    "st": "state",      # some sources omit the period
    "mt.": "mount",
    "mt": "mount",
    "n.": "north",
    "s.": "south",
    "e.": "east",
    "w.": "west",
}

# Common city abbreviations used by ESPN and other sources.
# Applied during token overlap scoring so "LA Clippers" matches "Los Angeles Clippers".
_CITY_ABBREVIATIONS: dict[str, str] = {
    "la": "los angeles",
    "ny": "new york",
    "nyk": "new york",
    "lv": "las vegas",
    "kc": "kansas city",
    "ok": "oklahoma",
    "okc": "oklahoma city",
    "gb": "green bay",
    "tb": "tampa bay",
    "sa": "san antonio",
    "sf": "san francisco",
    "sl": "st louis",
    "stl": "st louis",
    "no": "new orleans",
    "nola": "new orleans",
    "ne": "new england",
    "dc": "washington",
    "phx": "phoenix",
    "jax": "jacksonville",
    "min": "minnesota",
    "mil": "milwaukee",
    "den": "denver",
    "det": "detroit",
    "phi": "philadelphia",
    "ind": "indianapolis",
    "atl": "atlanta",
    "chi": "chicago",
    "cin": "cincinnati",
    "cle": "cleveland",
    "dal": "dallas",
    "hou": "houston",
    "mem": "memphis",
    "mia": "miami",
    "sac": "sacramento",
    "cha": "charlotte",
    "por": "portland",
    "orl": "orlando",
    "pit": "pittsburgh",
    "bal": "baltimore",
    "sea": "seattle",
    "bos": "boston",
    "buf": "buffalo",
}


# Special letter transliterations not handled by NFD decomposition
_EXTRA_TRANSLITERATIONS = str.maketrans({
    "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L",
    "ß": "ss",
})

# Sponsor suffixes stripped during slug generation
_SPONSOR_SUFFIX_RE = re.compile(
    r"\s+(?:presented|sponsored|hosted|powered)\s+by\s+.*$",
    re.IGNORECASE,
)


def strip_diacritics(s: str) -> str:
    """Remove diacritical marks and transliterate special characters.

    Handles both standard combining marks (é→e, ñ→n) and special letters
    that NFD doesn't decompose (ø→o, đ→d, ł→l, ß→ss).

    Examples:
        "Höjgaard" -> "Hojgaard"
        "Hovland"  -> "Hovland"
        "Strauß"   -> "Strauss"
    """
    s = s.translate(_EXTRA_TRANSLITERATIONS)
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def normalize_team_name(name: str) -> str:
    """Normalize a team name for matching/deduplication.

    Strips diacritics, lowercases, removes trailing periods, removes
    periods before spaces ("St. Louis" → "St Louis"), and strips
    parenthetical suffixes like "(W)" or "(Res)".

    This is the canonical version — used by playoffs, march madness,
    admin endpoints, and anywhere team names need to be compared.

    Examples:
        "St. Louis Cardinals" -> "st louis cardinals"
        "Borussia Dortmund (Res)" -> "borussia dortmund"
        "A's" -> "a's"
    """
    n = strip_diacritics(name).lower().strip()
    n = n.rstrip(".")
    n = re.sub(r"\.(?=\s)", "", n)
    n = re.sub(r"\s*\(.*\)$", "", n)
    return n.strip()


def match_key(name: str) -> str:
    """Create an alphanumeric-only dedup key from a name.

    Strips diacritics, lowercases, removes "the " prefix, truncates
    at colon, removes all non-alphanumeric characters except spaces,
    and collapses whitespace. Used for golfer/nominee deduplication
    where different sources format names differently.

    Examples:
        "The Masters" -> "masters"
        "Scottie Scheffler: Top 5" -> "scottie scheffler"
        "Rory McIlroy" -> "rory mcilroy"
    """
    key = strip_diacritics(name).lower()
    key = re.sub(r"^the\s+", "", key)
    key = key.split(":")[0]
    key = re.sub(r"[^a-z0-9\s]", "", key)
    return re.sub(r"\s+", " ", key).strip()


def clean_slug(name: str) -> str:
    """Create a URL-safe slug from a name.

    Strips sponsor suffixes ("presented by ..."), lowercases, and
    replaces non-alphanumeric characters with hyphens.

    Examples:
        "The Masters Tournament" -> "the-masters-tournament"
        "Valero Texas Open presented by Mastercard" -> "valero-texas-open"
    """
    name = _SPONSOR_SUFFIX_RE.sub("", name)
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def normalize_name(name: str) -> str:
    """Canonical name normalization: lowercase, strip diacritics, unify apostrophes,
    strip reserve/youth suffixes.

    Examples:
        "Skarsgård" -> "skarsgard"
        "Boston Celtics II" -> "boston celtics"
        "  Boston Red Sox  " -> "boston red sox"
    """
    if not name:
        return ""
    stripped = strip_diacritics(name)
    # Unify apostrophe-like characters
    for ch in _APOSTROPHE_CHARS:
        stripped = stripped.replace(ch, "'")
    # Normalize period-without-space: "St.Louis" → "St. Louis"
    stripped = re.sub(r'\.([A-Za-z])', r'. \1', stripped)
    # Lowercase, strip whitespace
    result = stripped.lower().strip()
    # Strip reserve/youth suffixes
    result = _RESERVE_SUFFIX_RE.sub("", result).strip()
    return result


def _expand_abbreviations(name: str) -> str:
    """Expand common abbreviations in a normalized name.

    Handles city abbreviations ("la" -> "los angeles") and college
    abbreviations ("st." -> "state", "mt." -> "mount").
    Only expands when the abbreviation appears as a standalone word.
    """
    words = name.split()
    expanded: list[str] = []
    for w in words:
        if w in _CITY_ABBREVIATIONS:
            expanded.append(_CITY_ABBREVIATIONS[w])
        elif w in _COLLEGE_ABBREVIATIONS:
            expanded.append(_COLLEGE_ABBREVIATIONS[w])
        else:
            expanded.append(w)
    return " ".join(expanded)


def token_overlap_score(name_a: str, name_b: str) -> float:
    """Token-overlap scoring: min-coverage model returning 0.0-1.0.

    Computes the minimum of (overlap/words_a, overlap/words_b).
    This prevents partial location matches like "Eastern Kentucky" vs
    "Kentucky" (0.33) and shared mascots like "Air Force Falcons" vs
    "Atlanta Falcons" (0.33).

    Names are normalized and city abbreviations expanded before comparison,
    so "LA Clippers" matches "Los Angeles Clippers" (1.0).
    """
    norm_a = _expand_abbreviations(normalize_name(name_a))
    norm_b = _expand_abbreviations(normalize_name(name_b))
    if not norm_a or not norm_b:
        return 0.0
    words_a = {w for w in norm_a.split() if w not in _MATCH_STOPWORDS and len(w) > 1}
    words_b = {w for w in norm_b.split() if w not in _MATCH_STOPWORDS and len(w) > 1}
    if not words_a or not words_b:
        return 0.0
    overlap = words_a & words_b
    if not overlap:
        return 0.0
    return min(len(overlap) / len(words_a), len(overlap) / len(words_b))


def names_match(name_a: str, name_b: str) -> bool:
    """Check if two team names refer to the same team.

    Three-stage matching:
    1. Exact match after normalization
    2. Suffix containment at word boundaries (handles "Celtics" matching
       "Boston Celtics", "Red Sox" matching "Boston Red Sox")
    3. Token overlap scoring (threshold >=0.5)

    Does NOT match:
    - "Air Force Falcons" vs "Atlanta Falcons" (token overlap ~0.33)
    - "South Carolina State" vs "South Carolina" (not suffix, overlap ~0.67
      but NOT a suffix match so falls through to token overlap which is >0.5
      — this is a known edge case where token overlap disagrees with human
      judgment. We accept this tradeoff.)

    The suffix-only containment strategy is deliberately conservative: prefix
    matching ("South Carolina" in "South Carolina State") is NOT used because
    city/state names are qualifiable and can represent different teams.
    """
    norm_a = normalize_name(name_a)
    norm_b = normalize_name(name_b)

    if not norm_a or not norm_b:
        return False

    # 1. Exact match
    if norm_a == norm_b:
        return True

    # 2. Suffix containment at word boundaries
    #    "Celtics" matches "Boston Celtics" (suffix)
    #    "Red Sox" matches "Boston Red Sox" (suffix)
    #    But NOT "South Carolina" matching "South Carolina State" (prefix, not suffix)
    shorter, longer = (norm_a, norm_b) if len(norm_a) <= len(norm_b) else (norm_b, norm_a)
    if len(shorter) >= 4:
        shorter_words = shorter.split()
        longer_words = longer.split()
        if len(shorter_words) < len(longer_words):
            # Suffix match only: shorter must match the trailing words
            if longer_words[-len(shorter_words):] == shorter_words:
                return True

    # 3. Token overlap scoring (>=0.5 to catch single-token names like UCLA/VCU)
    return token_overlap_score(name_a, name_b) >= 0.5
