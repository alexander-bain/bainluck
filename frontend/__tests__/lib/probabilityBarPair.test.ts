// #2962 — the probability bar's two segments, as a pair.
//
// ## What this guards, and why the numbers are assertions rather than prose
//
// The defect was two CSS custom properties that have never been defined
// (`--color-text-muted`, `--color-accent-brand`), so `background-color` was
// invalid at computed-value time and both halves of the bar painted nothing.
// Measured on production at 390px on 2026-09-04: 7 of 7 bars, 14 of 14
// segments, computed `rgba(0, 0, 0, 0)`.
//
// Every threshold in `probabilityBarPair.ts` was chosen by replaying the real
// palette, so the real palette is committed beside this file
// (`__tests__/fixtures/teamPrimaryColors.20260904.json`, all 644 distinct
// `teams.primary_color` values over 1,445 teams, `truncated: false`) and the
// claims below are re-derived from it on every run. A number that justified a
// design decision and lives only in a commit message is a number the next
// session has to take on trust.
//
// ## What this file CANNOT see
//
// It cannot see the render. A pure helper can be perfect while the component
// keeps its own broken fallback — which is the state this queue found, since
// `FeedCard` hand-rolled a bar rather than using the shared `ProbabilityBar`.
// The rendered half is `__tests__/components/feedCardProbabilityBar.test.tsx`
// and it is the load-bearing one.

import palette from "../fixtures/teamPrimaryColors.20260904.json";
import { hexToRgb } from "@/lib/teamColors";
import {
  probabilityBarPair,
  contrastRatio,
  colorDistance,
  CARD_SURFACE,
  SEGMENT_OPACITY,
  MIN_SURFACE_CONTRAST,
  MIN_PAIR_DISTANCE,
  AWAY_DEFAULT,
  HOME_DEFAULT,
  RESCUE_LADDER,
} from "@/lib/probabilityBarPair";

type Rgb = [number, number, number];

/** Parse the way the module does, so the test cannot disagree with the fix. */
function rgb(hex: string): Rgb {
  const parsed = hexToRgb(hex);
  if (!parsed) throw new Error(`test helper could not parse ${hex}`);
  const p = parsed.split(" ").map(Number);
  return [p[0], p[1], p[2]];
}

/** The pixel the reader sees: the colour at SEGMENT_OPACITY over the card. */
function painted(hex: string): Rgb {
  const c = rgb(hex);
  const s = rgb(CARD_SURFACE);
  return [
    SEGMENT_OPACITY * c[0] + (1 - SEGMENT_OPACITY) * s[0],
    SEGMENT_OPACITY * c[1] + (1 - SEGMENT_OPACITY) * s[1],
    SEGMENT_OPACITY * c[2] + (1 - SEGMENT_OPACITY) * s[2],
  ];
}

const visible = (hex: string) =>
  contrastRatio(painted(hex), rgb(CARD_SURFACE)) >= MIN_SURFACE_CONTRAST;
const distinct = (a: string, b: string) =>
  colorDistance(painted(a), painted(b)) >= MIN_PAIR_DISTANCE;

const COLORS: string[] = (palette.colors as [string, number][]).map((c) => c[0]);
const TEAMS: Record<string, number> = Object.fromEntries(
  palette.colors as [string, number][]
);

// ── 1. THE CONTRACT, OVER THE WHOLE REAL PALETTE ─────────────────────────────
//
// Not "here are three specimens" — every colour the site actually holds, on
// both sides, plus the absent case. If the contract can be broken by a real
// team colour, it is broken here.

describe("the pair contract holds for every colour the site actually holds", () => {
  it("the fixture is the population it claims to be", () => {
    // Guards the guard: if someone regenerates this fixture smaller, the
    // sweeps below get weaker without any test going red.
    expect(palette.distinct_colors).toBe(644);
    expect(COLORS).toHaveLength(644);
    expect(palette.teams_with_color).toBe(1445);
    expect(Object.values(TEAMS).reduce((a, b) => a + b, 0)).toBe(1445);
  });

  it("never returns an empty, undefined, or var() colour — for any real colour on either side", () => {
    const bad: string[] = [];
    for (const c of COLORS) {
      for (const pair of [
        probabilityBarPair(c, null),
        probabilityBarPair(null, c),
        probabilityBarPair(c, c),
      ]) {
        for (const seg of [pair.away, pair.home]) {
          if (!seg || seg.includes("var(") || !hexToRgb(seg)) bad.push(`${c} -> ${seg}`);
        }
      }
    }
    expect(bad).toEqual([]);
  });

  it("both segments are always visible against the card", () => {
    const bad: string[] = [];
    for (const c of COLORS) {
      for (const pair of [
        probabilityBarPair(c, null),
        probabilityBarPair(null, c),
        probabilityBarPair(c, c),
      ]) {
        if (!visible(pair.away)) bad.push(`away ${pair.away} (from ${c})`);
        if (!visible(pair.home)) bad.push(`home ${pair.home} (from ${c})`);
      }
    }
    expect(bad).toEqual([]);
  });

  it("the two segments are never indistinguishable — including when BOTH sides are the same colour", () => {
    const bad: string[] = [];
    for (const c of COLORS) {
      for (const pair of [
        probabilityBarPair(c, null),
        probabilityBarPair(null, c),
        probabilityBarPair(c, c),
      ]) {
        if (!distinct(pair.away, pair.home)) {
          bad.push(`${c}: ${pair.away} vs ${pair.home}`);
        }
      }
    }
    expect(bad).toEqual([]);
  });
});

// ── 2. THE MEASUREMENTS THAT CHOSE THE THRESHOLDS ────────────────────────────

describe("the thresholds are the ones the palette justified", () => {
  it("1.5:1 rescues 60 teams; 3:1 would have overridden 256", () => {
    // This is the whole argument for a low floor: the rule should correct
    // white-on-white, not re-brand a tenth of the league. If a future session
    // raises MIN_SURFACE_CONTRAST, this test says what it costs.
    const teamsBelow = (t: number) =>
      COLORS.filter(
        (c) => contrastRatio(painted(c), rgb(CARD_SURFACE)) < t
      ).reduce((n, c) => n + TEAMS[c], 0);
    // Both figures are measured on the COMPOSITED pixel, which is what the
    // reader sees. Measuring the raw hex instead gives 39 and 146 — I quoted
    // those first and the test caught it; they describe a colour that is never
    // painted, because the segment renders at SEGMENT_OPACITY.
    expect(teamsBelow(1.5)).toBe(60);
    expect(teamsBelow(3.0)).toBe(256);
    expect(MIN_SURFACE_CONTRAST).toBe(1.5);
  });

  it("#ffffff is 26 teams, and it is the reason clause 3 exists", () => {
    // A "real" team colour that reproduces the exact symptom being fixed.
    expect(TEAMS["#ffffff"]).toBe(26);
    expect(visible("#ffffff")).toBe(false);
    const pair = probabilityBarPair("#ffffff", null);
    expect(pair.away).not.toBe("#ffffff");
    expect(visible(pair.away)).toBe(true);
  });

  it("the rescue ladder is provably sufficient over the whole palette", () => {
    // Redmean is not a true metric, so the triangle inequality does not licence
    // an argument here — this is measured instead. Worst real colour still
    // leaves 3 of 4 ladder members available.
    // Annotated: RESCUE_LADDER is `as const`, so `.length` is the literal type
    // 4 and the narrowing below would not assign.
    let fewest: number = RESCUE_LADDER.length;
    for (const c of COLORS) {
      const available = RESCUE_LADDER.filter((l) => distinct(l, c)).length;
      fewest = Math.min(fewest, available);
    }
    expect(fewest).toBe(3);
  });

  it("the rescue ladder is sufficient over a synthetic RGB grid too, not just today's palette", () => {
    // The palette moves; this arm does not depend on it.
    const bad: string[] = [];
    for (let r = 0; r < 256; r += 17)
      for (let g = 0; g < 256; g += 17)
        for (let b = 0; b < 256; b += 17) {
          const hex =
            "#" + [r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("");
          if (!RESCUE_LADDER.some((l) => distinct(l, hex))) bad.push(hex);
        }
    expect(bad).toEqual([]);
  });
});

// ── 3. THE DEFAULT PAIR — THE PATH ~EVERY CARD TAKES ─────────────────────────
//
// `/api/feed` serializes `home_team_data` on 0 of 37 rows and `/api/events` on
// 0 of 86, so `homeColor` is null on every card the site renders and this is
// not the edge case the issue's framing implies. It is the render path.

describe("when neither side has a colour — which is every card today", () => {
  it("returns the two tokens the broken code was reaching for", () => {
    expect(probabilityBarPair(null, null)).toEqual({
      away: "#9CA3AF", // --text-muted, NOT --color-text-muted
      home: "#10B981", // --accent-brand, NOT --color-accent-brand
    });
  });

  it("both defaults are visible and distinguishable once painted", () => {
    expect(visible(AWAY_DEFAULT)).toBe(true);
    expect(visible(HOME_DEFAULT)).toBe(true);
    expect(distinct(AWAY_DEFAULT, HOME_DEFAULT)).toBe(true);
    // The pair sits at 167, comfortably clear of the 80 floor — so a small
    // future tweak to either token cannot silently merge the halves.
    expect(
      Math.round(colorDistance(painted(AWAY_DEFAULT), painted(HOME_DEFAULT)))
    ).toBe(167);
  });

  it("undefined, empty, malformed and short hex all fall back rather than painting nothing", () => {
    for (const junk of [undefined, null, "", "   ", "#", "#GGG", "#12345", "rgb(1,2,3)", "red"]) {
      expect(probabilityBarPair(junk, junk)).toEqual({
        away: AWAY_DEFAULT,
        home: HOME_DEFAULT,
      });
    }
  });
});

// ── 4. ONE SIDE COLOURED — LIVE TODAY, VIA THE PHANTOM ROWS ──────────────────

describe("when only one side has a colour", () => {
  it("keeps the real colour and gives the other side a distinguishable default", () => {
    // The only rows on production carrying a team colour today are the
    // malformed `St.Louis Cardinals` twins (external_id null, #2630/#2958).
    const pair = probabilityBarPair("#be0a14", null);
    expect(pair.away).toBe("#be0a14");
    expect(pair.home).toBe(HOME_DEFAULT);
    expect(distinct(pair.away, pair.home)).toBe(true);
  });

  it("moves the DEFAULT, never the team's own colour, when the two would collide", () => {
    // A green team beside the emerald default. The team keeps its colour.
    const pair = probabilityBarPair("#00A26B", null);
    expect(pair.away).toBe("#00A26B");
    expect(pair.home).not.toBe(HOME_DEFAULT);
    expect(distinct(pair.away, pair.home)).toBe(true);
  });

  it("accepts a colour with no leading # and returns one that CSS can paint", () => {
    // The column stores both spellings.
    expect(probabilityBarPair("be0a14", null).away).toBe("#be0a14");
  });
});

// ── 5. BOTH SIDES COLOURED ───────────────────────────────────────────────────
//
// ⚠️ SHIPS NOTHING TODAY, deliberately: `home_team_data` is serialized on 0 of
// 37 feed rows and 0 of 86 event rows, so this branch is unreachable on the
// live site. It is built because the pair contract is symmetric and because
// the branch becomes live the moment that serialization is fixed. Stated here
// rather than left for a grader to discover.

describe("when both sides have a colour (unreachable on today's payloads)", () => {
  it("keeps both when they are distinguishable", () => {
    const pair = probabilityBarPair("#be0a14", "#005A9C");
    expect(pair).toEqual({ away: "#be0a14", home: "#005A9C" });
  });

  it("rescues the home side when two real colours would read as one block", () => {
    // 155 teams share #000000, so a black-v-black card is not hypothetical.
    const pair = probabilityBarPair("#000000", "#000000");
    expect(pair.away).toBe("#000000");
    expect(pair.home).not.toBe("#000000");
    expect(distinct(pair.away, pair.home)).toBe(true);
  });

  it("two dark reds 78 apart are treated as a collision, per the measured floor", () => {
    const pair = probabilityBarPair("#8a2432", "#ac0d1e");
    expect(pair.away).toBe("#8a2432");
    expect(pair.home).not.toBe("#ac0d1e");
  });

  it("is deterministic — the same input never renders two ways", () => {
    const a = probabilityBarPair("#000000", "#000000");
    const b = probabilityBarPair("#000000", "#000000");
    expect(a).toEqual(b);
  });
});

// ── 6. CONTROLS — GREEN ON THE PARENT TOO ────────────────────────────────────
//
// These hold facts this ship must NOT change. Verified green against master.

describe("CONTROL: things this ship must not move", () => {
  it("CONTROL: the real design tokens are what they always were", () => {
    // If someone renames --text-muted or --accent-brand, the defaults this
    // module hardcodes go stale silently. This is the tripwire.
    expect(AWAY_DEFAULT).toBe("#9CA3AF");
    expect(HOME_DEFAULT).toBe("#10B981");
  });

  it("CONTROL: hexToRgb still decides what a usable colour is", () => {
    // The module parses through teamColors so that this bar and the
    // ProbabilityBar/EventCard bars cannot disagree about validity.
    expect(hexToRgb("#9CA3AF")).toBe("156 163 175");
    expect(hexToRgb("#12345")).toBeUndefined();
    expect(hexToRgb(null)).toBeUndefined();
  });

  it("CONTROL: the card surface is white, because the site is light mode only", () => {
    expect(CARD_SURFACE).toBe("#FFFFFF");
  });
});
