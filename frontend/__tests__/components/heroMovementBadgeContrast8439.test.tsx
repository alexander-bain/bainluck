/**
 * #8439 — THE "▲ N pts" BADGE UNDER THE GOLF HERO'S LEADER MUST BE READABLE.
 *
 * Production Discover at 390px, 2026-09-24 19:17Z: the FedEx Open de France
 * card's hero read "15% · Matthew Fitzpatrick" and, under it, a "▲ 9.8 pts"
 * badge in green-600 on a green-500/15 pill on the `#14532d → #166534` hero —
 * green on green. `MovementBadge` had one skin, tuned for the white card body.
 *
 * Same two shapes as #8436's guard: every case asserts the badge RENDERS and
 * says its number before it scores colour (the mutant "badge stops rendering"
 * must not pass), and the hero stops and badge alphas are parsed from the
 * rendered markup, not written down here. And the other direction (gotcha
 * #43): without `onDark` — the white-card futures rows — the badge keeps its
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

import DiscoverCard from "@/components/DiscoverCard";
import { MovementBadge } from "@/components/discover/shared";
import type { FeedItem, FeedTournamentData } from "@/lib/types";

/** WCAG 4.5:1 for text below 18px; the badge is `text-[10px]`. */
const BAR = 4.5;

// ── colour maths (same as #4181's / #8436's files) ──────────────────────────

type RGB = [number, number, number];
const BLACK: RGB = [0, 0, 0];

/** The Tailwind -300 inks the on-dark skin may use. */
const INK: Record<string, RGB> = {
  "green-300": [134, 239, 172],
  "red-300": [252, 165, 165],
};

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

/** Scrim alpha + ink out of a class list. RAISES on anything but the on-dark shape. */
function skinOf(classes: string): { scrim: number; ink: RGB } {
  const bg = /\bbg-black\/(\d{1,3})\b/.exec(classes);
  const ink = /\btext-((?:green|red)-300)\b/.exec(classes);
  if (!bg || !ink) throw new Error(`badge is not "bg-black/N text-{green,red}-300": ${classes}`);
  return { scrim: Number(bg[1]) / 100, ink: INK[ink[1]] };
}

function failuresOn(gradient: string, classes: string): string[] {
  const { scrim, ink } = skinOf(classes);
  return stopsOf(gradient)
    .map((stop) => {
      const fill = over(hex(stop), BLACK, scrim);
      return { stop, ratio: contrast(ink, fill) };
    })
    .filter((s) => s.ratio < BAR)
    .map((s) => `${s.stop} ${s.ratio.toFixed(2)}:1`);
}

/** The white-card skin — banned on a dark hero. */
const CARD_SKIN = [/\bbg-(?:green|red)-500\/15\b/, /\btext-(?:green|red)-600\b/];

function heroOf(markup: string): { background: string; inner: string } {
  const m = /<div class="relative h-44[^"]*" style="background:([^"]+)">([\s\S]*)/.exec(markup);
  if (!m) throw new Error("could not find the card hero (relative h-44 with an inline background)");
  return { background: m[1], inner: m[2] };
}

/** The badge: the span whose title is its own "Up/Down N points…" label. */
function badgeOf(markup: string): { classes: string; title: string; body: string } | null {
  const m = /<span title="((?:Up|Down) [^"]+)" aria-label="[^"]*" class="([^"]*)">([\s\S]*?)<\/span>/.exec(markup);
  return m ? { title: m[1], classes: m[2], body: m[3].replace(/<[^>]*>/g, "") } : null;
}

// ── TournamentCard (via DiscoverCard, the path Discover renders) ────────────

function renderTournament(movement: number): string {
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
      golfers: [{ name: "Matthew Fitzpatrick", probability: 0.15, rank: 1, movement_24h: movement, movement_is_dated: true }],
      market_ids: [61814765],
      source_count: 2,
    } as unknown as FeedTournamentData,
  } as unknown as FeedItem;
  return renderToStaticMarkup(
    <DiscoverCard groupedItem={{ type: "single", item }} positionIndex={0} />,
  );
}

describe("#8439 · TournamentCard — the hero's move badge is readable on the green hero", () => {
  it.each([
    ["up", 0.098, "Up", "9.8 pts"],
    ["down", -0.098, "Down", "9.8 pts"],
  ])("%s move: badge drawn, says its number, no white-card skin, readable at every stop", (_dir, movement, word, pts) => {
    const hero = heroOf(renderTournament(movement as number));
    const badge = badgeOf(hero.inner);
    expect(badge).not.toBeNull();
    expect(badge!.title.startsWith(word as string)).toBe(true);
    expect(badge!.body).toContain(pts);
    for (const banned of CARD_SKIN) expect(badge!.classes).not.toMatch(banned);
    expect(failuresOn(hero.background, badge!.classes)).toEqual([]);
  });
});

// ── the other direction, and controls on the maths ──────────────────────────

describe("#8439 · controls", () => {
  it("CONTROL — without onDark (the white-card futures rows) the badge keeps its white-card skin", () => {
    const up = badgeOf(renderToStaticMarkup(<MovementBadge m={0.098} prob={0.15} />));
    const down = badgeOf(renderToStaticMarkup(<MovementBadge m={-0.098} prob={0.15} />));
    expect(up!.classes).toContain("bg-green-500/15 text-green-600");
    expect(down!.classes).toContain("bg-red-500/15 text-red-600");
    expect(up!.classes).not.toContain("bg-black/");
  });

  it("CONTROL — the skin it replaced really failed on this hero", () => {
    // green-600 ink on a green-500/15 pill over each stop of the golf hero.
    for (const stop of ["#14532d", "#166534"]) {
      const fill = over(hex(stop), hex("#22c55e"), 0.15);
      expect(contrast(hex("#16a34a"), fill)).toBeLessThan(BAR);
    }
  });

  it("CONTROL — the parser refuses a white-card skin rather than scoring nothing", () => {
    expect(() => skinOf("bg-green-500/15 text-green-600")).toThrow();
  });
});
