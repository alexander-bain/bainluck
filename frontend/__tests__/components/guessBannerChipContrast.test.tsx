/**
 * #4181 — THE "WHAT ARE THE ODDS?" BANNER CHIP MUST BE READABLE ON ITS BANNER.
 *
 * The defect: `GuessCard` painted the category chip with `catStyle.bg` +
 * `catStyle.text` from `CATEGORY_COLORS` — `bg-indigo-500/15` over
 * `text-indigo-600`, a skin designed for the WHITE card surface below the
 * banner. On `catGradient`, the DARK banner of the same hue, a 15% tint of the
 * hue over the hue leaves the fill essentially the gradient, and mid-dark
 * `*-600` text on it vanishes. Every one of the eighteen categories landed
 * between 1.12:1 and 2.14:1 against a 4.5 bar for 10px text, while the sibling
 * "What are the odds?" label on the same strip read 8.56:1.
 *
 * Two things this file is built to survive, both of which a naive version of it
 * would have shipped green:
 *
 *  1. ⚠️ THE MUTANT IS "THE CHIP STOPS RENDERING", NOT "THE CLASS COMES BACK".
 *     A guard that only asserts the old classes are absent is passed perfectly
 *     by a component that draws no chip at all — the classic
 *     `remedy_as_regression` shape. So every case asserts the chip EXISTS and
 *     still prints its category, and PART 1 carries a positive control that
 *     fails if the banner stops being found.
 *
 *  2. ⚠️ THE MIDPOINT OF A GRADIENT IS NOT WHERE THE CHIP IS. The chip is
 *     `ml-auto`; on a `135deg` gradient that puts it over the SECOND, lighter
 *     stop. Sizing the skin against the midpoint is how `bg-black/30
 *     text-white/90` looked fine (6.73:1) while leaving cricket at 4.18:1 on
 *     the pixels the chip actually covers. PART 2 therefore scores EVERY stop
 *     of EVERY gradient, not the average, and not just the one the author
 *     happened to look at.
 *
 * PART 2 derives its categories from `CATEGORY_GRADIENTS` itself, so a
 * nineteenth category with a light crest turns this red without anyone
 * remembering to come back here.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import { GuessCard } from "@/components/discover/GuessCard";
import { CATEGORY_GRADIENTS } from "@/components/discover/constants";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

/** WCAG needs 4.5:1 for text below 18px; the chip is `text-[10px]`. */
const BAR = 4.5;

// ── colour maths ────────────────────────────────────────────────────────────

type RGB = [number, number, number];

function hex(h: string): RGB {
  const m = /^#([0-9a-f]{6})$/i.exec(h.trim());
  if (!m) throw new Error(`not a 6-digit hex colour: ${h}`);
  return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16)) as RGB;
}

/** `over` composited onto `base` at alpha `a` — what the browser paints. */
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

/** Every colour stop in a `linear-gradient(...)` string. */
function stopsOf(gradient: string): string[] {
  const found = gradient.match(/#[0-9a-f]{6}/gi) ?? [];
  if (found.length < 2) {
    // A gradient we cannot parse must RAISE. Returning [] would score zero
    // stops and report a clean pass over a category nobody checked.
    throw new Error(`could not parse two colour stops out of: ${gradient}`);
  }
  return found;
}

// ── the skin under test, READ OUT OF THE COMPONENT ──────────────────────────

const BLACK: RGB = [0, 0, 0];
const WHITE: RGB = [255, 255, 255];

/**
 * ⚠️ These are parsed from `GuessCard.tsx`, not written down here, and that is
 * the whole point. A first draft of this file hardcoded `0.4` / `1`, which
 * meant PART 2 scored the AUTHOR'S ARITHMETIC rather than the component: swap
 * the chip to a failing skin and PART 2 stayed green, because it was still
 * happily proving that `bg-black/40` would have been fine. Only PART 1's string
 * match caught it. Reading the real alphas closes that gap — change the skin
 * and the contrast maths re-runs against what actually ships.
 */
function chipSkinFromSource(): { scrim: number; ink: number } {
  const src = fs.readFileSync(
    path.join(__dirname, "..", "..", "components", "discover", "GuessCard.tsx"),
    "utf8",
  );
  const chip = /<span className="([^"]*\bml-auto\b[^"]*)">/.exec(src);
  if (!chip) throw new Error("could not find the banner chip's className in GuessCard.tsx");
  const classes = chip[1];

  const bg = /\bbg-black\/(\d{1,3})\b/.exec(classes);
  const white = /\btext-white(?:\/(\d{1,3}))?\b/.exec(classes);
  if (!bg || !white) {
    // The chip stopped using a black scrim with white ink. That may be a fine
    // redesign, but this file can no longer score it, and a scan that cannot
    // parse must RAISE rather than quietly score nothing.
    throw new Error(
      `the banner chip is no longer "bg-black/N text-white[/N]" — re-derive #4181's maths for: ${classes}`,
    );
  }
  return { scrim: Number(bg[1]) / 100, ink: white[1] ? Number(white[1]) / 100 : 1 };
}

const { scrim: SCRIM_ALPHA, ink: INK_ALPHA } = chipSkinFromSource();

// ── fixtures ────────────────────────────────────────────────────────────────

function futuresData(category: string): FeedFuturesData {
  return {
    id: 4181,
    name: "Will the challenger take the title?",
    llm_sport_category: category,
    sport_name: category,
    resolution_date: "2027-01-10T00:00:00Z",
    source: "kalshi",
    top_outcomes: [{ id: 1, name: "Yes", probability: 0.58, movement: 2.1 }],
    outcome_count: 2,
    volume_24h: 1_400_000,
    confidence_tier: "high",
  } as unknown as FeedFuturesData;
}

function guessItem(category: string): FeedItem {
  return {
    type: "futures",
    score: 90,
    reason: "",
    headline: "",
    data: futuresData(category),
  } as unknown as FeedItem;
}

/** The banner strip: the element carrying the inline `background:` gradient. */
function bannerOf(markup: string): string {
  const m = /<div class="px-4 py-2\.5 flex items-center gap-2"[^>]*>([\s\S]*?)<\/div>/.exec(markup);
  if (!m) throw new Error("could not find the guess banner strip in the rendered markup");
  return m[1];
}

/** Class values from `CATEGORY_COLORS` — the white-card skin, banned up here. */
const CARD_SKIN_CLASSES = [
  /\bbg-[a-z]+-\d00\/15\b/, // bg-indigo-500/15 &c
  /\btext-[a-z]+-[67]00\b/, // text-indigo-600, text-green-700 &c
];

describe("#4181 · PART 1 — the banner chip wears the on-dark skin, and still exists", () => {
  const categories = Object.keys(CATEGORY_GRADIENTS);

  it("renders a banner for every category (positive control for the scans below)", () => {
    expect(categories.length).toBeGreaterThanOrEqual(18);
    for (const cat of categories) {
      const banner = bannerOf(renderToStaticMarkup(<GuessCard item={guessItem(cat)} />));
      // The sibling label proves we found the right strip and it drew.
      expect(banner).toContain("What are the odds?");
    }
  });

  it.each(Object.keys(CATEGORY_GRADIENTS))(
    "%s: the chip is drawn, names its category, and carries no white-card skin",
    (cat) => {
      const banner = bannerOf(renderToStaticMarkup(<GuessCard item={guessItem(cat)} />));

      // 1. THE CHIP EXISTS AND SAYS SOMETHING. Without this the whole file is
      //    satisfied by deleting the chip.
      const chip = /<span class="([^"]*rounded-full[^"]*ml-auto[^"]*)">([\s\S]*?)<\/span>/.exec(banner);
      expect(chip).not.toBeNull();
      const [, chipClasses, chipText] = chip!;
      expect(chipText.replace(/<[^>]*>/g, "").trim().length).toBeGreaterThan(0);
      expect(chipText).toContain(cat);

      // 2. It wears the on-dark skin.
      expect(chipClasses).toContain("bg-black/40");
      expect(chipClasses).toContain("text-white");

      // 3. And none of the white-card skin that caused #4181.
      for (const banned of CARD_SKIN_CLASSES) {
        expect(chipClasses).not.toMatch(banned);
      }
    },
  );
});

describe("#4181 · PART 2 — every stop of every gradient clears the 4.5 bar", () => {
  it("scores each gradient stop, not the midpoint", () => {
    const scored: { cat: string; stop: string; ratio: number }[] = [];

    for (const [cat, gradient] of Object.entries(CATEGORY_GRADIENTS)) {
      for (const stop of stopsOf(gradient)) {
        const fill = over(hex(stop), BLACK, SCRIM_ALPHA);
        const ink = over(fill, WHITE, INK_ALPHA);
        scored.push({ cat, stop, ratio: contrast(ink, fill) });
      }
    }

    // The scan must have found real work to do — an empty loop reads as a pass.
    expect(scored.length).toBeGreaterThanOrEqual(36);

    const failures = scored.filter((s) => s.ratio < BAR);
    expect(
      failures.map((f) => `${f.cat}@${f.stop} ${f.ratio.toFixed(2)}:1`).join(", "),
    ).toBe("");
  });

  it("the skin it replaced really did fail, so the bar is not vacuous", () => {
    // Positive control on the TEST: score the pre-#4181 skin the same way and
    // require it to fail. If this ever passes, the maths above stopped
    // measuring anything and PART 2's silence means nothing.
    //
    // `bg-indigo-500/15` + `text-indigo-600` on the politics banner.
    const gradientStop = hex("#4338ca"); // the lighter stop, where the chip sits
    const fill = over(gradientStop, hex("#6366f1"), 0.15); // indigo-500 @ 15%
    const ink = hex("#4f46e5"); // indigo-600
    expect(contrast(ink, fill)).toBeLessThan(BAR);
  });

  it("also rejects the tempting `bg-white/20 text-white`, which fails at the light stops", () => {
    // Recorded because it is the fix a reader reaches for first: it lightens
    // the fill toward the ink and makes several categories worse.
    const worst = Object.entries(CATEGORY_GRADIENTS).flatMap(([cat, g]) =>
      stopsOf(g).map((stop) => {
        const fill = over(hex(stop), WHITE, 0.2);
        return { cat, ratio: contrast(WHITE, fill) };
      }),
    );
    expect(worst.some((w) => w.ratio < BAR)).toBe(true);
  });
});
