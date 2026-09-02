"""True pixel dimensions for enriched market artwork.

WHY THIS EXISTS
---------------
`FuturesMarket.image_url` is a *rendered* URL, not a raster. Pexels serves
through imgix, so `?h=350` means "350 tall, width whatever the aspect gives" —
measured live, the `h=350` family spans 450-586 px wide, and the `h=650&w=940`
family renders 867 or 899 px wide whenever the height binds first. A URL's
parameters are not its pixels.

Any consumer that needs to know how wide the delivered image actually is (a
`srcset` `w` descriptor, an aspect-ratio box) therefore cannot read it off the
URL. It has to be stored. This module is how the value is derived.

TWO DERIVATIONS, ONE QUANTITY
-----------------------------
`delivered_dimensions()` computes the size from the source photo's dimensions,
which the Pexels API already hands us in the response we make anyway — free, no
extra request. `dimensions_from_header()` reads the size out of the first bytes
of the raster itself — exact, but costs a fetch. Ingest uses the first; the
backfill of rows enriched before this module existed uses the second.

They agree, and where they cannot agree exactly the computed one is deliberately
the *smaller*: every computed axis that is not pinned by the URL is floored, so
a stored width never overstates the pixels that exist. That direction is not an
aesthetic preference. A `srcset` descriptor that overstates its rung tells the
browser a small image is big, and the browser then upscales it — the exact
regression that blocked the first version of this work. Understating costs at
most one pixel of sharpness; overstating costs correctness.

If a derivation fails, both return None and the column stays NULL. NULL means
"we do not know", and every consumer must fall back to the conservative
behaviour it had before this module existed. Being wrong about a photo must
degrade to today, never past it.

Imports nothing from `app` — keep it that way (zero circular-import risk).
"""

from __future__ import annotations

import math
import re
import struct
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

Dimensions = Tuple[int, int]

# TMDB renders at a fixed width named in the path: /t/p/w1280/abc.jpg
_TMDB_WIDTH_RE = re.compile(r"/t/p/w(\d+)/")


def _positive_int_param(params: dict, key: str) -> Optional[int]:
    """Read a positive integer query parameter, or None if absent/garbage."""
    raw = params.get(key)
    if not raw:
        return None
    try:
        value = int(raw[0])
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def delivered_dimensions(
    url: str,
    source_width: Optional[int],
    source_height: Optional[int],
) -> Optional[Dimensions]:
    """Size of the raster `url` returns, given the source photo's true size.

    Applies imgix's default `fit=clip`: the image is scaled to fit inside the
    box named by the URL's `w`/`h` parameters with its aspect preserved, and is
    never scaled beyond the source. Either box axis may be absent — `?h=350`
    constrains height only.

    The axis pinned by the URL is exact. The other is floored, so the result is
    never larger than the real raster (see module docstring). Returns None when
    the source size is unusable.
    """
    if not url or not source_width or not source_height:
        return None
    if source_width <= 0 or source_height <= 0:
        return None

    params = parse_qs(urlparse(url).query)
    box_w = _positive_int_param(params, "w")
    box_h = _positive_int_param(params, "h")

    if box_w is None and box_h is None:
        # No resize requested — the source is what gets served.
        return (source_width, source_height)

    # Scale factor that fits the source inside whichever axes are constrained.
    # Capped at 1.0: imgix will not invent pixels the source does not have, and
    # if it ever did, claiming them here is the unsafe direction.
    scales = []
    if box_w is not None:
        scales.append(box_w / source_width)
    if box_h is not None:
        scales.append(box_h / source_height)
    scale = min(min(scales), 1.0)

    if scale >= 1.0:
        return (source_width, source_height)

    # The binding axis lands exactly on its box value; the other is floored.
    width = box_w if (box_w is not None and scale == box_w / source_width) else max(
        1, math.floor(source_width * scale)
    )
    height = box_h if (box_h is not None and scale == box_h / source_height) else max(
        1, math.floor(source_height * scale)
    )
    return (width, height)


def tmdb_declared_width(url: str) -> Optional[int]:
    """Exact rendered width of a TMDB image URL, read from its `/t/p/wNNN/` path.

    TMDB names the width in the URL and honours it exactly, so this needs no
    source dimensions. Height is not derivable here and stays unknown.
    """
    if not url:
        return None
    match = _TMDB_WIDTH_RE.search(url)
    if not match:
        return None
    width = int(match.group(1))
    return width if width > 0 else None


# --------------------------------------------------------------------------
# Header parsing — exact dimensions from the leading bytes of a raster.
#
# Deliberately dependency-free: the backend slug has no image library, and
# adding one to read four integers would be absurd. Every parser below reads
# only the container's size field and never decodes pixel data.
# --------------------------------------------------------------------------


def _png_dimensions(data: bytes) -> Optional[Dimensions]:
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return (width, height) if width and height else None


def _gif_dimensions(data: bytes) -> Optional[Dimensions]:
    if len(data) < 10:
        return None
    width, height = struct.unpack("<HH", data[6:10])
    return (width, height) if width and height else None


def _jpeg_dimensions(data: bytes) -> Optional[Dimensions]:
    """Walk JPEG markers to the first Start-Of-Frame and read its size."""
    index = 2  # past SOI
    length = len(data)
    while index + 9 < length:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        # Standalone markers carry no length payload.
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        if index + 4 > length:
            return None
        seg_len = struct.unpack(">H", data[index + 2 : index + 4])[0]
        # SOF0..SOF15, excluding the non-frame markers DHT/JPG/DAC.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if index + 9 > length:
                return None
            height, width = struct.unpack(">HH", data[index + 5 : index + 9])
            return (width, height) if width and height else None
        index += 2 + seg_len
    return None


def _webp_dimensions(data: bytes) -> Optional[Dimensions]:
    if len(data) < 30:
        return None
    fourcc = data[12:16]
    if fourcc == b"VP8X":
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return (width, height)
    if fourcc == b"VP8L":
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return (width, height)
    if fourcc == b"VP8 ":
        # Lossy: 3-byte start code, then 16-bit width/height (14 bits each).
        if data[23:26] != b"\x9d\x01\x2a":
            return None
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return (width, height) if width and height else None
    return None


def _iso_bmff_dimensions(data: bytes) -> Optional[Dimensions]:
    """AVIF / HEIC: find the primary item's `ispe` box and read its extent.

    `ispe` (ImageSpatialExtentsProperty) is a full box: 4-byte size, 'ispe',
    1-byte version + 3-byte flags, then 32-bit width and height. Scanning for
    the first occurrence is sufficient here — the primary item's property comes
    first in every render Pexels serves, and a wrong guess is caught by the
    caller's sanity check rather than silently trusted.
    """
    marker = data.find(b"ispe")
    if marker == -1 or marker + 16 > len(data):
        return None
    width, height = struct.unpack(">II", data[marker + 8 : marker + 16])
    return (width, height) if width and height else None


def dimensions_from_header(data: bytes) -> Optional[Dimensions]:
    """Exact pixel dimensions from the leading bytes of an image, or None.

    Supports the formats Pexels and TMDB actually serve: AVIF (what a browser
    negotiates), JPEG (what everything else gets), plus PNG/WebP/GIF for
    completeness. Returns None for anything it cannot parse with certainty —
    never a guess.
    """
    if not data or len(data) < 16:
        return None

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return _png_dimensions(data)
    if data[:3] == b"GIF":
        return _gif_dimensions(data)
    if data[:2] == b"\xff\xd8":
        return _jpeg_dimensions(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _webp_dimensions(data)
    if data[4:8] == b"ftyp":
        return _iso_bmff_dimensions(data)
    return None
