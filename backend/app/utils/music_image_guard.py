"""#12659: prevent music/album/song/chart markets from wearing TMDB film art.

TMDB ``/search/multi`` indexes movies and television, never albums or singles.
When ``enrich_tmdb_images`` matched any entertainment market whose name carried
quotes (``FuturesMarket.name.like('%"%')``), quoted album and song titles
attached unrelated film backdrops — e.g. ``"FRESH" First Week Album Sales?``
received the 2022 thriller *Fresh*, ``"All I Want for Christmas Is You" ·
Billboard Hot 100 rank`` received a film adaptation, and ``Will "Stay" by The
Kid LAROI ... be on the radio in GTA VI at launch?`` and ``Will "Umbrella" be
played at the 2027 Big Game halftime show?`` received same-named films (28
usable music-family rows + 3 radio-track rows = 31 usable / 32 open rows on the
2026-11-12 public census).

This pure helper gates both sides of the boundary:
  1. Write side (``tasks/enrich_tmdb.py``): skips TMDB lookup for music markets
     and clears previously attached ``image.tmdb.org`` URLs on music rows.
  2. Read side (``routes/feed.py`` and ``routes/entertainment.py``): withholds
     any ``image.tmdb.org`` URL (and its stored raster dimensions) on a music
     market immediately at serve time so readers never see wrong film art while
     background cleanup catches up. Non-TMDB URLs are untouched.
"""

from __future__ import annotations

import re

_TMDB_IMAGE_HOST = "image.tmdb.org"

# Explicit film/TV framing wins if both domains appear (e.g. a musical film's
# box office, Rotten Tomatoes score, or Academy Award Best Picture nomination).
_FILM_TV_CONTEXT_RE = re.compile(
    r"\b("
    r"rotten\s+tomatoes|tomatometer|box\s+office|opening\s+weekend|"
    r"2nd\s+weekend|domestic\s+gross|worldwide\s+gross|cinemascore|"
    r"imdb\s+top\s+250|metascore|metacritic|"
    r"academy\s+awards?|oscars?\b|best\s+picture|"
    r"best\s+(?:actor|actress|director|supporting|animated|screenplay|cinematography|international\s+feature)|"
    r"emmys?|golden\s+globes?|baftas?|sag\s+awards?|"
    r"episode\s+released|season\s+\d+|new\s+[\"“][^\"”]+[\"”]\s+episode"
    r")\b",
    re.IGNORECASE,
)

_MUSIC_MARKET_RE = re.compile(
    r"("
    r"\b(album|ep|mixtape|discography|lp)\b"
    r"|\bfirst\s+week\s+(?:album\s+)?sales\b"
    r"|\balbum\s+equivalent\s+units\b"
    r"|\b(billboard|hot\s*100|billboard\s*200|spotify|apple\s+music|itunes|riaa)\b"
    r"|\b(on\s+the\s+radio|halftime\s+show|setlist|coachella|glastonbury|lollapalooza|eurovision)\b"
    r"|\b(grammys?|song\s+of\s+the\s+year|record\s+of\s+the\s+year|album\s+of\s+the\s+year|best\s+new\s+artist)\b"
    r"|\btaylor['’]s\s+version\b"
    r"|\b(weekly|daily|monthly)\s+(?:streams|listeners)\b"
    r"|\b(?:song|track|single)\s+(?:by|from|released|streams|chart|rank)\b"
    r"|\brelease\s+[\"“][^\"”]+[\"”].*\b(album|song|single|ep|track|taylor['’]s\s+version)\b"
    r"|\b(taylor\s+swift|drake|kendrick\s+lamar|beyonc[eé]|sabrina\s+carpenter|bad\s+bunny|billie\s+eilish|"
    r"chappell\s+roan|charli\s+xcx|olivia\s+rodrigo|morgan\s+wallen|the\s+weeknd|ariana\s+grande|lady\s+gaga|"
    r"travis\s+scott|kanye|ye|rihanna|cardi\s+b|nicki\s+minaj|justin\s+bieber|bruno\s+mars|ed\s+sheeran|"
    r"harry\s+styles|dua\s+lipa|post\s+malone|sza|zach\s+bryan|lana\s+del\s+rey|playboi\s+carti|frank\s+ocean|"
    r"bts|blackpink|olivia\s+dean|tate\s+mcrae)\b.*\brelease\s+[\"“]"
    r")",
    re.IGNORECASE,
)


def is_music_market_ineligible_for_tmdb(market_name: str | None) -> bool:
    """Return True when ``market_name`` describes a music/song/album/chart market
    for which a TMDB movie/TV lookup produces false-positive film artwork."""
    if not market_name:
        return False
    if _FILM_TV_CONTEXT_RE.search(market_name):
        return False
    return bool(_MUSIC_MARKET_RE.search(market_name))


def is_tmdb_image_url(image_url: str | None) -> bool:
    """Return True when ``image_url`` is served from TMDB's image CDN."""
    if not image_url:
        return False
    return _TMDB_IMAGE_HOST in image_url.lower()


def sanitize_market_image_url(
    image_url: str | None,
    market_name: str | None,
) -> str | None:
    """Withhold false-positive TMDB movie/TV artwork on music markets (#12659)."""
    if not image_url:
        return None
    if is_tmdb_image_url(image_url) and is_music_market_ineligible_for_tmdb(market_name):
        return None
    return image_url


def sanitize_market_image_fields(
    image_url: str | None,
    image_width: int | None,
    image_height: int | None,
    market_name: str | None,
) -> tuple[str | None, int | None, int | None]:
    """Return ``(image_url, image_width, image_height)`` with TMDB film art
    and its paired dimensions cleared when ``market_name`` is a music market."""
    cleaned_url = sanitize_market_image_url(image_url, market_name)
    if cleaned_url is None:
        return None, None, None
    return cleaned_url, image_width, image_height
