// #11499 — A DISCOVER PHOTO CARD KEEPS ITS BIG PERCENTAGE READABLE ON A LIGHT PHOTO.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// bainluck.com at 390px, v5888, 2026-10-23 ~07:50Z, Congress bundle expanded
// (`artifacts/ux-1023-11468-11475-served/congress-expanded.png`). The House card
// sits on a light-grey photo; its white 91% almost vanished into the wall. The
// wall behind the digits read rgb(213–222) after the darkening layer: ~1.4:1.
//
// ── THE MECHANISM ────────────────────────────────────────────────────────────
//
// The layer was `linear-gradient(to top, rgba(0,0,0,0.6), rgba(0,0,0,0.04) 55%, …)`:
// dense only along the bottom edge. The number block sits in the bottom ~35–45%
// of a 16:10 hero, where the layer had already faded toward 4%.
//
// ── THE PIN ──────────────────────────────────────────────────────────────────
//
// The served gradient string is evaluated the way a browser lays out its stops
// (percent → px, a stop placed before its predecessor is clamped up to it, a
// missing first/last position is 0/100%). At every pixel from the bottom edge up
// to the top of the digits, on every hero height the card is drawn at, white
// over a WHITE photo must clear 3:1 — and so must the `opacity-80` moderate tier.
// Above the number block the layer must be no darker than the old one beyond a
// short fade, so a dark photo is not muddied where the number isn't.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import {
  FuturesCard,
  HERO_NUMBER_BLOCK_PX,
  PHOTO_HERO_SCRIM,
  PLAIN_HERO_SCRIM,
} from "@/components/discover/FuturesCard";

const OLD_SCRIM =
  "linear-gradient(to top, rgba(0,0,0,0.6), rgba(0,0,0,0.04) 55%, rgba(0,0,0,0.22))";

type Stop = { alpha: number; pos: string | null };

function parseStops(gradient: string): Stop[] {
  const body = gradient.replace(/^linear-gradient\(\s*to top\s*,/, "").replace(/\)\s*$/, "");
  const re = /rgba\(0,0,0,([\d.]+)\)(?:\s+([\d.]+(?:px|%)))?/g;
  const stops: Stop[] = [];
  for (let m = re.exec(body); m; m = re.exec(body)) {
    stops.push({ alpha: Number(m[1]), pos: m[2] ?? null });
  }
  return stops;
}

/** Black-layer alpha at `y` px above the bottom edge of a hero `height` px tall. */
function alphaAt(gradient: string, height: number, y: number): number {
  const stops = parseStops(gradient);
  const placed: Array<{ alpha: number; at: number | null }> = stops.map((s, i) => {
    if (s.pos == null) return { alpha: s.alpha, at: i === 0 ? 0 : i === stops.length - 1 ? height : null };
    return { alpha: s.alpha, at: s.pos.endsWith("%") ? (parseFloat(s.pos) / 100) * height : parseFloat(s.pos) };
  });
  // CSS Images 3 §3.5.3: a stop before its predecessor is moved up to it.
  let floor = 0;
  for (const p of placed) {
    if (p.at != null) {
      p.at = Math.max(p.at, floor);
      floor = p.at;
    }
  }
  // Unpositioned middle stops are spaced evenly between their neighbours.
  for (let i = 0; i < placed.length; i += 1) {
    if (placed[i].at != null) continue;
    let j = i;
    while (placed[j].at == null) j += 1;
    const a = placed[i - 1].at as number;
    const b = placed[j].at as number;
    for (let k = i; k < j; k += 1) placed[k].at = a + ((b - a) * (k - i + 1)) / (j - i + 1);
  }
  if (y <= (placed[0].at as number)) return placed[0].alpha;
  for (let i = 1; i < placed.length; i += 1) {
    const lo = placed[i - 1];
    const hi = placed[i];
    if (y <= (hi.at as number)) {
      const span = (hi.at as number) - (lo.at as number);
      return span === 0 ? hi.alpha : lo.alpha + ((hi.alpha - lo.alpha) * (y - (lo.at as number))) / span;
    }
  }
  return placed[placed.length - 1].alpha;
}

function luminance(channel: number): number {
  const c = channel / 255;
  const lin = c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  return lin; // grey: R = G = B, so relative luminance is the channel's linear value
}

function contrast(a: number, b: number): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** White text at `opacity` over a white photo darkened by `alpha` black. */
function textOverWhitePhoto(alpha: number, opacity: number): number {
  const bg = 255 * (1 - alpha);
  const fg = opacity * 255 + (1 - opacity) * bg;
  return contrast(fg, bg);
}

// 16:10 heroes: 390px phone (358px card), the bundle's inset card, the
// four-column desktop slot (300px), and a wide single column.
const HERO_HEIGHTS = [358 / 1.6, 330 / 1.6, 300 / 1.6, 640 / 1.6];

describe("#11499 the photo scrim holds behind the hero number", () => {
  it("the strawman: the old layer fails 3:1 behind the digits on a white photo", () => {
    const worst = Math.min(...HERO_HEIGHTS.map((h) => textOverWhitePhoto(alphaAt(OLD_SCRIM, h, HERO_NUMBER_BLOCK_PX), 1)));
    expect(worst).toBeLessThan(3);
  });

  it.each(HERO_HEIGHTS)("white digits clear 3:1 over a white photo on a %fpx hero", (h) => {
    for (let y = 0; y <= HERO_NUMBER_BLOCK_PX; y += 1) {
      expect(textOverWhitePhoto(alphaAt(PHOTO_HERO_SCRIM, h, y), 1)).toBeGreaterThanOrEqual(3);
      // `probabilityAuthorityClass("moderate")` = opacity-80.
      expect(textOverWhitePhoto(alphaAt(PHOTO_HERO_SCRIM, h, y), 0.8)).toBeGreaterThanOrEqual(3);
    }
  });

  it.each(HERO_HEIGHTS)("a dark photo is not muddied above the number on a %fpx hero", (h) => {
    // Never heavier than the old bottom edge…
    for (let y = 0; y <= h; y += 1) expect(alphaAt(PHOTO_HERO_SCRIM, h, y)).toBeLessThanOrEqual(0.65);
    // …and from 150px up, no darker than the old layer was.
    for (let y = 150; y <= h; y += 1) {
      expect(alphaAt(PHOTO_HERO_SCRIM, h, y)).toBeLessThanOrEqual(alphaAt(OLD_SCRIM, h, y) + 1e-9);
    }
  });

  const data = {
    id: 108621,
    name: "Which party will win the U.S. House?",
    llm_sport_category: "politics",
    status: "open",
    source: "kalshi",
    market_tier: 2,
    top_outcomes: [
      { id: 1, name: "Democratic Party", probability: 0.91, rank: 1, movement: null },
      { id: 2, name: "Republican Party", probability: 0.09, rank: 2, movement: null },
    ],
  } as unknown as FeedFuturesData;
  const item = { type: "futures", score: 70, reason: "", headline: "", data } as unknown as FeedItem;
  const render = (d: FeedFuturesData) =>
    renderToStaticMarkup(<FuturesCard item={{ ...item, data: d }} data={d} liked={false} setLiked={() => {}} trending={false} />);
  const scrimOf = (html: string) => {
    const m = html.match(/data-testid="futures-hero-scrim" style="background:([^"]+)"/);
    return m ? m[1].replace(/&quot;/g, '"') : null;
  };

  it("a card with a photo draws the photo scrim, and its digits carry a shadow", () => {
    const html = render({ ...data, image_url: "https://example.com/fists.jpg" } as FeedFuturesData);
    expect(scrimOf(html)).toBe(PHOTO_HERO_SCRIM);
    expect(html).toMatch(/data-testid="futures-hero-probability"/);
    expect(html).toMatch(/class="[^"]*\[text-shadow:0_1px_3px_rgba\(0,0,0,0\.35\)\][^"]*"[^>]*data-testid="futures-hero-probability"/);
  });

  it("a card without a photo keeps the old layer over its category gradient", () => {
    expect(PLAIN_HERO_SCRIM).toBe(OLD_SCRIM);
    expect(scrimOf(render(data))).toBe(PLAIN_HERO_SCRIM);
  });
});
