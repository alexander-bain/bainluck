/**
 * #8436 — THE SPORT CHIP ON A CARD'S DARK HERO MUST BE READABLE ON THAT HERO.
 *
 * Production Discover at 390px, 2026-09-24 19:17Z: the "⚾ MLB" chip on every
 * live/final MLB card was faint red on the dark red hero, and the "⛳ GOLF" chip
 * on the FedEx Open de France card was dark lime on the dark green hero. Both
 * cards painted the chip with the `CATEGORY_COLORS` skin (`bg-<hue>-500/15
 * text-<hue>-600`), which is tuned for the WHITE card body, on top of the
 * `CATEGORY_GRADIENTS` hero of the same hue — #4181's defect, on the two hero
 * chips #4181 never reached (`guessBannerChipContrast.test.tsx`).
 *
 * Built to survive the two shapes a naive guard ships green on:
 *
 *  1. THE MUTANT IS "THE CHIP STOPS RENDERING". Every case asserts the chip
 *     exists and prints its label before it asserts anything about colour.
 *  2. THE ARITHMETIC IS READ FROM THE RENDERED CARD. The hero's stops come from
 *     the inline `background:` the card actually rendered, and the chip's
 *     scrim/ink alphas from the classes on the chip it actually rendered — not
 *     from a constant written down here. Swap either card back to a white-card
 *     skin and the parse RAISES; swap it to a weaker scrim and the maths fails.
 *
 * And the other direction (gotcha #43): a sport with no gradient paints a LIGHT
 * team-colour tint, where white ink would be the defect — that card keeps the
 * white-card skin.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import { EventCard } from "@/components/discover/EventCard";
import DiscoverCard from "@/components/DiscoverCard";
import { CATEGORY_GRADIENTS, HERO_CHIP_ON_DARK } from "@/components/discover/constants";
import type { FeedEventData, FeedItem, FeedTournamentData } from "@/lib/types";

/** WCAG 4.5:1 for text below 18px; the chip is `text-[10px]`. */
const BAR = 4.5;

// ── colour maths (same as #4181's file) ─────────────────────────────────────

type RGB = [number, number, number];
const BLACK: RGB = [0, 0, 0];
const WHITE: RGB = [255, 255, 255];

function hex(h: string): RGB {
  const m = /^#([0-9a-f]{6})$/i.exec(h.trim());
  if (!m) throw new Error(`not a 6-digit hex colour: ${h}`);
  return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16)) as RGB;
}
function over(base: RGB, top: RGB, a: number): RGB {
  return base.map((v, i) => v * (1 - a) + top[i] * a) as RGB;
}
function luminance([r, g, b]: RGB): number {
  const s = [r, g, b].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * s[0] + 0.7152 * s[1] + 0.0722 * s[2];
}
function contrast(a: RGB, b: RGB): number {
  const [l1, l2] = [luminance(a), luminance(b)];
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}
function stopsOf(gradient: string): string[] {
  const found = gradient.match(/#[0-9a-f]{6}/gi) ?? [];
  if (found.length < 2) throw new Error(`could not parse two colour stops out of: ${gradient}`);
  return found;
}

/** Scrim/ink alphas out of a class list. RAISES on anything but the on-dark shape. */
function skinOf(classes: string): { scrim: number; ink: number } {
  const bg = /\bbg-black\/(\d{1,3})\b/.exec(classes);
  const white = /\btext-white(?:\/(\d{1,3}))?(?=\s|$)/.exec(classes);
  if (!bg || !white) throw new Error(`chip is not "bg-black/N text-white[/N]": ${classes}`);
  return { scrim: Number(bg[1]) / 100, ink: white[1] ? Number(white[1]) / 100 : 1 };
}

/** Every stop that fails the bar for this skin, as readable strings. */
function failuresOn(gradient: string, classes: string): string[] {
  const { scrim, ink } = skinOf(classes);
  return stopsOf(gradient)
    .map((stop) => {
      const fill = over(hex(stop), BLACK, scrim);
      return { stop, ratio: contrast(over(fill, WHITE, ink), fill) };
    })
    .filter((s) => s.ratio < BAR)
    .map((s) => `${s.stop} ${s.ratio.toFixed(2)}:1`);
}

/** The white-card skin from `CATEGORY_COLORS` — banned on a dark hero. */
const CARD_SKIN = [/\bbg-[a-z]+-\d00\/15\b/, /\btext-[a-z]+-[5-8]00\b/];

function visibleText(markup: string): string {
  const lead = /^[^<>]*/.exec(markup)?.[0] ?? "";
  return lead + (markup.match(/>[^<>]*/g) ?? []).map((r) => r.slice(1)).join("");
}

/** renderToStaticMarkup writes `style="background:linear-gradient(...)"`. */
function heroOf(markup: string): { background: string; inner: string } {
  const m = /<div class="relative h-44[^"]*" style="background:([^"]+)">([\s\S]*)/.exec(markup);
  if (!m) throw new Error("could not find the card hero (relative h-44 with an inline background)");
  return { background: m[1], inner: m[2] };
}

// ── EventCard ───────────────────────────────────────────────────────────────

function eventData(sport: string): FeedEventData {
  return {
    id: 8436,
    external_id: "evt-8436",
    sport,
    sport_name: "League",
    home_team: "Chicago Cubs",
    away_team: "Miami Marlins",
    commence_time: "2030-01-01T12:00:00.000Z",
    status: "live",
    home_score: 0,
    away_score: 1,
    current_odds: { home_probability: 0.51, away_probability: 0.49, home_rendered_percent: 51, away_rendered_percent: 49 },
    home_team_data: null,
    away_team_data: null,
  } as unknown as FeedEventData;
}

function renderEvent(sport: string): string {
  const data = eventData(sport);
  return renderToStaticMarkup(
    <EventCard
      item={{ type: "event", score: 50, reason: "", headline: "", data } as unknown as FeedItem}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );
}

/** The chip: first `truncate … rounded-full` div in the hero's pill row. */
function eventChip(markup: string): { classes: string; text: string } {
  const m = /<div class="(min-w-0 truncate [^"]*rounded-full[^"]*)">([\s\S]*?)<\/div>/.exec(heroOf(markup).inner);
  if (!m) throw new Error("could not find the EventCard hero chip");
  return { classes: m[1], text: visibleText(m[2]) };
}

// The sports on page one, plus the other gradient shelves a game card reaches.
const DARK_HERO_SPORTS: [string, string][] = [
  ["baseball_mlb", "baseball"],
  ["americanfootball_nfl", "football"],
  ["basketball_nba", "basketball"],
  ["icehockey_nhl", "hockey"],
  ["soccer_epl", "soccer"],
];

describe("#8436 · EventCard — the hero chip wears the on-dark skin on every dark hero", () => {
  it.each(DARK_HERO_SPORTS)("%s: chip drawn, labelled, readable at every stop", (sport, shelf) => {
    const html = renderEvent(sport);
    const hero = heroOf(html);
    // The hero really is the shelf's dark gradient (otherwise this case tests nothing).
    expect(hero.background).toBe(CATEGORY_GRADIENTS[shelf]);

    const chip = eventChip(html);
    expect(chip.text.trim().length).toBeGreaterThan(0);
    for (const banned of CARD_SKIN) expect(chip.classes).not.toMatch(banned);
    expect(failuresOn(hero.background, chip.classes)).toEqual([]);
  });

  it("the page-one specimen: an MLB card's chip still says MLB", () => {
    expect(eventChip(renderEvent("baseball_mlb")).text).toContain("MLB");
  });

  it("CONTROL — a sport with no gradient paints a light tint and keeps the white-card chip", () => {
    const html = renderEvent("zz_unknownsport_league");
    const hero = heroOf(html);
    expect(Object.values(CATEGORY_GRADIENTS)).not.toContain(hero.background);
    const chip = eventChip(html);
    expect(chip.text.trim().length).toBeGreaterThan(0);
    expect(chip.classes).not.toContain("bg-black/");
    expect(chip.classes).not.toMatch(/\btext-white\b/);
  });
});

// ── TournamentCard (via DiscoverCard, the path Discover renders) ────────────

function renderTournament(): string {
  const item = {
    type: "tournament",
    score: 85,
    reason: "",
    headline: "Live",
    data: {
      key: "fedex_open_de_france",
      name: "FedEx Open de France",
      tour: "dp_world",
      tour_label: "DP World Tour",
      is_major: false,
      venue: "Le Golf National",
      golfers: [{ name: "Matthew Fitzpatrick", probability: 0.15, rank: 1, movement_24h: null }],
      market_ids: [61814765],
      source_count: 2,
    } as unknown as FeedTournamentData,
  } as unknown as FeedItem;
  return renderToStaticMarkup(
    <DiscoverCard groupedItem={{ type: "single", item }} positionIndex={0} />,
  );
}

describe("#8436 · TournamentCard — the ⛳ Golf chip is readable on the green hero", () => {
  it("chip drawn, labelled, no white-card skin, readable at every stop of the rendered hero", () => {
    const html = renderTournament();
    const hero = heroOf(html);
    const m = /<div class="(absolute top-3 left-3 [^"]*rounded-full[^"]*)">([\s\S]*?)<\/div>/.exec(hero.inner);
    expect(m).not.toBeNull();
    const [, classes, inner] = m!;
    expect(visibleText(inner)).toContain("Golf");
    for (const banned of CARD_SKIN) expect(classes).not.toMatch(banned);
    expect(failuresOn(hero.background, classes)).toEqual([]);
  });
});

// ── the shared skin, and the controls on the maths ──────────────────────────

describe("#8436 · the shared on-dark skin", () => {
  it("clears the bar at every stop of every CATEGORY_GRADIENTS entry", () => {
    const all = Object.entries(CATEGORY_GRADIENTS).flatMap(([cat, g]) =>
      failuresOn(g, HERO_CHIP_ON_DARK).map((f) => `${cat}@${f}`),
    );
    expect(Object.keys(CATEGORY_GRADIENTS).length).toBeGreaterThanOrEqual(18);
    expect(all).toEqual([]);
  });

  it("CONTROL — the skins it replaced really failed on these heroes", () => {
    // MLB: bg-red-500/15 + text-red-600 on #7f1d1d. Golf: bg-lime-600/15 + text-lime-700 on #14532d.
    const mlbFill = over(hex("#7f1d1d"), hex("#ef4444"), 0.15);
    expect(contrast(hex("#dc2626"), mlbFill)).toBeLessThan(BAR);
    const golfFill = over(hex("#14532d"), hex("#65a30d"), 0.15);
    expect(contrast(hex("#4d7c0f"), golfFill)).toBeLessThan(BAR);
  });

  it("CONTROL — the parser refuses a white-card skin rather than scoring nothing", () => {
    expect(() => skinOf("bg-lime-600/15 text-lime-700")).toThrow();
  });
});
