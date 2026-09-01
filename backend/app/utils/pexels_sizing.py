"""
Pexels hero-image raster sizing.

The Discover card hero (`components/discover/FuturesCard.tsx`) renders into a
fixed `aspect-[16/10]` box inside a masonry column. Measured across every
breakpoint the site actually ships, that box is 300-360 CSS px wide:

    viewport  390 -> 1 col -> 358 css px
    viewport  768 -> 2 col -> 360 css px
    viewport 1024 -> 3 col -> 320 css px
    viewport 1280 -> 4 col -> 300 css px

At DPR 2 that needs at most 720 device px of raster; 16:10 makes the height
450. `HERO_RASTER_W/H` are that number, not a guess.

Two size classes reached production, and the split is a code-version artifact
rather than a per-card decision (measured 2026-09-01 on `/api/feed?limit=40`:
32 small, 14 large, scattered across both card types and all feed positions):

  * `?...&h=350` -- what the original enricher stored (`src.medium`). Delivers
    ~516 px wide, which is BELOW the 720 the retina slot wants.
  * `?...&h=650&w=940` -- what #565 switched to (`src.large`). Delivers ~926 px
    wide, which is ABOVE it.

So this module only ever shrinks. Capping the large class to the measured
raster saved 954,434 -> 608,890 B across the 14 large images on one 40-card
feed (36%), and removed a single 150,354 B outlier. Upsizing the small class
to match would have ADDED ~1 MB, so it is deliberately left alone -- its
softness on retina is a formatting question, not a latency one.

Pure module: imports nothing from `app`, so it is safe to call from tasks,
routes or utils without circular-import risk.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# The rendered hero raster at DPR 2. See module docstring for the measurement.
HERO_RASTER_W = 720
HERO_RASTER_H = 450

_PEXELS_IMAGE_HOSTS = frozenset({"images.pexels.com"})

# Pexels' own delivery knobs. Preserved when present so a capped URL keeps the
# compression settings the enricher (and Pexels' `src.*` presets) rely on.
_PRESERVED_PARAMS = ("auto", "cs")


def _is_pexels_image(url: str) -> bool:
    try:
        return urlsplit(url).hostname in _PEXELS_IMAGE_HOSTS
    except ValueError:
        return False


def _requested_width(params: dict[str, str]) -> int | None:
    """The width this URL asks Pexels for, inferring from `h` when `w` is absent.

    The legacy `src.medium` preset sets only `h=350`; its delivered width tracks
    the source photo's aspect ratio and is not in the URL. Treating a bare `h`
    as a 16:10 width keeps the comparison in one unit instead of guessing.
    """
    for key in ("w", "h"):
        raw = params.get(key)
        if raw is None:
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        if key == "w":
            return value
        return round(value * HERO_RASTER_W / HERO_RASTER_H)
    return None


def is_oversized_pexels_url(url: str) -> bool:
    """True when `url` asks Pexels for more raster than the hero box renders."""
    if not url or not _is_pexels_image(url):
        return False
    params = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
    width = _requested_width(params)
    return width is not None and width > HERO_RASTER_W


def cap_pexels_url(url: str) -> str:
    """Shrink an oversized Pexels URL to the measured hero raster.

    Returns `url` unchanged when it is not a Pexels image, carries no size
    request, or already asks for the raster or less -- this never upsizes, so
    the legacy `h=350` rows keep the bytes they have. Idempotent: capping an
    already-capped URL is a no-op.
    """
    if not is_oversized_pexels_url(url):
        return url

    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))

    capped = {key: params[key] for key in _PRESERVED_PARAMS if key in params}
    capped["w"] = str(HERO_RASTER_W)
    capped["h"] = str(HERO_RASTER_H)
    # Without `fit=crop` Pexels treats w/h as a bounding box and the binding
    # constraint becomes `h` for tall source photos, delivering 600-675 px --
    # under the 720 the slot needs. `fit=crop` pins the exact raster instead.
    capped["fit"] = "crop"

    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(capped), parts.fragment)
    )
