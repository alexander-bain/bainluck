"""Server-rendered U.S. snow-chance map for the White Christmas grouping (317: B).

Draws a 1080x540 (2:1, 3x retina for 360x180 phone card banners) PNG using:
- Public-domain Natural Earth 50m contiguous U.S. outline
  (`backend/app/data/us_contiguous_natural_earth_50m.json`), projected via
  standard CONUS Albers Equal-Area Conic (EPSG:5070 parameters).
- The 11 White Christmas U.S. cities marked at geographic coordinates and shaded
  dynamically by their live probability of snow on Christmas Day.
- Zero baked numeric percentages (rule 4 of 317: B), so the picture can never
  disagree with a live row number.
- Deep winter slate-navy palette with luminous sky-to-snow city dots and high-
  contrast halos so the card reads cleanly in both light mode and dark mode
  at 390px phone width without any iOS app update.
"""

from __future__ import annotations

import io
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Optional

from PIL import Image, ImageDraw, ImageFont

OUTLINE_DATA_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "us_contiguous_natural_earth_50m.json"
)

# Public URL wired onto `machinery-white-christmas` so both web and the current
# 1.0.7 iPhone build render the map automatically.
WHITE_CHRISTMAS_MAP_URL = (
    "https://api.bainluck.com/api/containers/machinery-white-christmas/map.png"
)

# Canonical 11 White Christmas cities:
# (canonical_key, display_label, lon, lat, (label_dx, label_dy), anchor, aliases)
WHITE_CHRISTMAS_CITIES: tuple[
    tuple[str, str, float, float, tuple[int, int], str, tuple[str, ...]], ...
] = (
    ("seattle", "Seattle", -122.3321, 47.6062, (34, -12), "lm", ("seattle",)),
    ("denver", "Denver", -104.9903, 39.7392, (0, 56), "mt", ("denver",)),
    (
        "minneapolis",
        "Minneapolis",
        -93.2650,
        44.9778,
        (-40, -14),
        "rm",
        ("minneapolis", "twin cities"),
    ),
    (
        "milwaukee",
        "Milwaukee",
        -87.9065,
        43.0389,
        (-25, -160),
        "rb",
        ("milwaukee",),
    ),
    ("chicago", "Chicago", -87.6298, 41.8781, (-34, 58), "rt", ("chicago",)),
    ("detroit", "Detroit", -83.0458, 42.3314, (30, -155), "lb", ("detroit",)),
    (
        "pittsburgh",
        "Pittsburgh",
        -79.9959,
        40.4406,
        (-10, 105),
        "mt",
        ("pittsburgh",),
    ),
    ("boston", "Boston", -71.0589, 42.3601, (95, -46), "lm", ("boston",)),
    (
        "nyc",
        "NYC",
        -74.0060,
        40.7128,
        (170, -4),
        "lm",
        ("nyc", "new york", "new york city"),
    ),
    (
        "philadelphia",
        "Philly",
        -75.1652,
        39.9526,
        (195, 54),
        "lm",
        ("philadelphia", "philly"),
    ),
    (
        "dc",
        "DC",
        -77.0369,
        38.9072,
        (220, 118),
        "lm",
        ("dc", "d.c.", "washington", "washington dc", "washington, dc"),
    ),
)

# CONUS Albers Equal-Area Conic projection constants (EPSG:5070)
_PHI1 = math.radians(29.5)
_PHI2 = math.radians(45.5)
_PHI0 = math.radians(37.5)
_LAM0 = math.radians(-96.0)
_N = 0.5 * (math.sin(_PHI1) + math.sin(_PHI2))
_C = math.cos(_PHI1) ** 2 + 2.0 * _N * math.sin(_PHI1)
_RHO0 = math.sqrt(_C - 2.0 * _N * math.sin(_PHI0)) / _N

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)


def _albers_conus(lon: float, lat: float) -> tuple[float, float]:
    phi = math.radians(lat)
    lam = math.radians(lon)
    rho = math.sqrt(max(0.0, _C - 2.0 * _N * math.sin(phi))) / _N
    theta = _N * (lam - _LAM0)
    return rho * math.sin(theta), _RHO0 - rho * math.cos(theta)


@lru_cache(maxsize=1)
def load_us_outline() -> dict:
    """Load the embedded Natural Earth 50m contiguous U.S. polygon metadata."""
    with OUTLINE_DATA_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _snow_chance_color(prob: Optional[float]) -> tuple[int, int, int]:
    """Map snow probability [0, 1] to a high-contrast winter slate->sky->snow color."""
    if prob is None:
        return (126, 154, 186)
    clamped = max(0.0, min(1.0, float(prob)))
    # Stretch 8%..45% across the full ramp so differences among U.S. Christmas
    # snow odds read immediately at card size.
    t = max(0.0, min(1.0, (clamped - 0.08) / 0.37))
    if t < 0.5:
        u = t / 0.5
        return (
            int(92 + (56 - 92) * u),
            int(126 + (189 - 126) * u),
            int(168 + (248 - 168) * u),
        )
    u = (t - 0.5) / 0.5
    return (
        int(56 + (245 - 56) * u),
        int(189 + (252 - 189) * u),
        int(248 + (255 - 248) * u),
    )


def match_city_key(text: str | None) -> Optional[str]:
    """Extract canonical White Christmas city key from a market title or label."""
    if not text:
        return None
    norm = re.sub(r"[^a-z0-9\s.]", " ", text.lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    for key, _label, _lon, _lat, _off, _anchor, aliases in WHITE_CHRISTMAS_CITIES:
        for alias in aliases:
            if re.search(rf"(?:^|\s){re.escape(alias)}(?:\s|$)", norm):
                return key
    return None


def extract_white_christmas_city_probs(
    members: list[dict] | tuple[dict, ...] | None,
) -> dict[str, float]:
    """Extract `{city_key: snow_probability}` from container member envelopes."""
    out: dict[str, float] = {}
    for env in members or ():
        if not isinstance(env, Mapping):
            continue
        card = env.get("card") if isinstance(env.get("card"), Mapping) else env
        name = str(card.get("name") or "")
        key = match_city_key(name)
        if not key:
            continue
        top_outcomes = card.get("top_outcomes") or ()
        if top_outcomes and isinstance(top_outcomes[0], Mapping):
            raw_p = top_outcomes[0].get("probability")
            if raw_p is not None:
                try:
                    out[key] = max(0.0, min(1.0, float(raw_p)))
                except (TypeError, ValueError):
                    pass
    return out


def render_white_christmas_map_png(
    city_probs: Optional[Mapping[str, float]] = None,
    *,
    width: int = 1080,
    height: int = 540,
) -> bytes:
    """Render the 11-city White Christmas U.S. map as an anti-aliased PNG."""
    outline = load_us_outline()
    polygon = outline["polygon"]

    # 2x supersampled canvas for crisp lines and labels after LANCZOS downscale.
    scale_ss = 2
    cw, ch = width * scale_ss, height * scale_ss

    proj_poly = [_albers_conus(lon, lat) for lon, lat in polygon]
    xs = [p[0] for p in proj_poly]
    ys = [p[1] for p in proj_poly]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    sx = cw / 2160.0
    sy = ch / 1080.0
    pad_left = 140.0 * sx
    pad_right = 360.0 * sx
    pad_top = 145.0 * sy
    pad_bottom = 115.0 * sy

    map_scale = min(
        (cw - pad_left - pad_right) / max(1e-9, max_x - min_x),
        (ch - pad_top - pad_bottom) / max(1e-9, max_y - min_y),
    )
    map_w = (max_x - min_x) * map_scale
    map_h = (max_y - min_y) * map_scale
    off_x = pad_left + (cw - pad_left - pad_right - map_w) / 2.0
    off_y = pad_top + (ch - pad_top - pad_bottom - map_h) / 2.0

    def to_px(lon: float, lat: float) -> tuple[float, float]:
        x, y = _albers_conus(lon, lat)
        return off_x + (x - min_x) * map_scale, off_y + (max_y - y) * map_scale

    img = Image.new("RGBA", (cw, ch), (15, 29, 50, 255))
    draw = ImageDraw.Draw(img, "RGBA")
    for row in range(ch):
        t = row / max(1, ch - 1)
        draw.line(
            [(0, row), (cw, row)],
            fill=(int(13 + 11 * t), int(26 + 17 * t), int(48 + 22 * t), 255),
        )

    poly_px = [to_px(lon, lat) for lon, lat in polygon]
    shadow_dy = 8.0 * sy
    draw.polygon([(x, y + shadow_dy) for x, y in poly_px], fill=(5, 11, 22, 130))
    draw.polygon(poly_px, fill=(33, 55, 88, 255))
    draw.line(
        poly_px + [poly_px[0]],
        fill=(104, 144, 192, 255),
        width=max(2, int(round(5 * sx))),
        joint="curve",
    )

    probs = {k.lower(): v for k, v in (city_probs or {}).items()}
    font_lbl = _load_font(max(18, int(round(66 * sx))))
    font_leg = _load_font(max(14, int(round(52 * sx))))

    # 1. Leader lines
    for key, _label, lon, lat, (dx, dy), anchor, _aliases in WHITE_CHRISTMAS_CITIES:
        cx, cy = to_px(lon, lat)
        sdx, sdy = dx * sx, dy * sy
        lx, ly = cx + sdx, cy + sdy
        if math.hypot(dx, dy) > 65:
            ex = lx - 14 * sx if anchor.startswith("l") else (lx + 14 * sx if anchor.startswith("r") else lx)
            ey = ly + 10 * sy if anchor.endswith("b") else (ly - 10 * sy if anchor.endswith("t") else ly)
            draw.line(
                [(cx, cy), (ex, ey)],
                fill=(180, 214, 246, 175),
                width=max(2, int(round(4 * sx))),
            )

    # 2. Shaded city markers (no baked numbers)
    for key, _label, lon, lat, _off, _anchor, _aliases in WHITE_CHRISTMAS_CITIES:
        cx, cy = to_px(lon, lat)
        prob = probs.get(key)
        col = _snow_chance_color(prob)
        p_val = prob if prob is not None else 0.25
        r_dot = (23 if p_val >= 0.35 else (20 if p_val >= 0.22 else 17)) * sx
        if p_val >= 0.30:
            glow = r_dot + 18 * sx
            draw.ellipse([cx - glow, cy - glow, cx + glow, cy + glow], fill=(*col, 72))
        ring_r = r_dot + 6 * sx
        draw.ellipse(
            [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
            fill=(13, 26, 48, 240),
        )
        draw.ellipse([cx - r_dot, cy - r_dot, cx + r_dot, cy + r_dot], fill=(*col, 255))

    # 3. High-contrast city labels
    halo_r = max(1, int(round(3 * sx)))
    halo_diag = max(1, int(round(2 * sx)))
    halo_offsets = (
        (-halo_r, 0),
        (halo_r, 0),
        (0, -halo_r),
        (0, halo_r),
        (-halo_diag, -halo_diag),
        (halo_diag, halo_diag),
        (-halo_diag, halo_diag),
        (halo_diag, -halo_diag),
    )
    for _key, label, lon, lat, (dx, dy), anchor, _aliases in WHITE_CHRISTMAS_CITIES:
        cx, cy = to_px(lon, lat)
        lx, ly = cx + dx * sx, cy + dy * sy
        for ox, oy in halo_offsets:
            draw.text(
                (lx + ox, ly + oy),
                label,
                font=font_lbl,
                fill=(9, 18, 34, 235),
                anchor=anchor,
            )
        draw.text((lx, ly), label, font=font_lbl, fill=(240, 248, 255, 255), anchor=anchor)

    # 4. Compact bottom-left qualitative legend (zero numeric percentages)
    leg_x = 110.0 * sx
    leg_y = ch - 68.0 * sy
    draw.text(
        (leg_x, leg_y),
        "Lower",
        font=font_leg,
        fill=(166, 194, 224, 240),
        anchor="lm",
    )
    bar_x0 = int(round(leg_x + 185.0 * sx))
    bar_x1 = int(round(leg_x + 425.0 * sx))
    bar_half_h = int(round(12.0 * sy))
    for i in range(max(1, bar_x1 - bar_x0)):
        t = i / max(1, bar_x1 - bar_x0 - 1)
        c = _snow_chance_color(0.08 + 0.37 * t)
        draw.line(
            [(bar_x0 + i, leg_y - bar_half_h), (bar_x0 + i, leg_y + bar_half_h)],
            fill=(*c, 255),
        )
    draw.rounded_rectangle(
        [bar_x0, leg_y - bar_half_h, bar_x1, leg_y + bar_half_h],
        radius=max(3, int(round(8 * sx))),
        outline=(140, 175, 215, 190),
        width=max(1, int(round(3 * sx))),
    )
    draw.text(
        (bar_x1 + 22.0 * sx, leg_y),
        "Higher snow chance",
        font=font_leg,
        fill=(232, 244, 255, 245),
        anchor="lm",
    )

    final_img = img.resize((width, height), Image.Resampling.LANCZOS).convert("RGB")
    buf = io.BytesIO()
    final_img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
