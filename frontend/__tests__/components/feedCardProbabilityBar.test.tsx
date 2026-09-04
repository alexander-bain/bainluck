// #2962 — the probability bar, asserted against RENDERED markup.
//
// ## Why this file exists separately from the helper's own tests
//
// `__tests__/lib/probabilityBarPair.test.ts` drives the rule over the whole real
// palette and would stay green if this component never called it — which is
// exactly the state this queue found. `FeedCard` hand-rolls its own bar instead
// of using the shared `ProbabilityBar`, and its two fallbacks named CSS custom
// properties (`--color-text-muted`, `--color-accent-brand`) that have never been
// defined anywhere in the app. A `background-color: var(--undefined)` is invalid
// at computed-value time, so the declaration is dropped and the segment paints
// nothing.
//
// Measured on production at 390px, 2026-09-04 05:5x PT, commit `8e9d816c`:
// 7 of 7 bars and 14 of 14 segments computed to `rgba(0, 0, 0, 0)` — MLB, NPB
// and KBO alike, so it was never the tennis-only defect the filing describes.
//
// ## What the assertions read
//
// The inline `background-color` and `opacity` of each segment, bound to the side
// it belongs to via `data-bar-segment`. Reading the two colours as a bare
// ordered pair would not survive a swap, and reading only "is a colour present"
// would pass on two identical greys — which is the native sibling defect
// (#2902) and is what the obvious repair would have produced here.
//
// ## What this file CANNOT see
//
// jsdom does not resolve CSS custom properties against a stylesheet, so it
// cannot itself prove that `var(--color-text-muted)` computes to transparent —
// that claim is the production DOM read above, and the assertions here are
// written against the *inline* value instead, which is the thing the component
// controls and the thing that was wrong.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem, FeedEventData } from "@/lib/types";

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
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FeedCard from "../../components/FeedCard";
import { hexToRgb } from "@/lib/teamColors";
import {
  AWAY_DEFAULT,
  HOME_DEFAULT,
  SEGMENT_OPACITY,
  MIN_PAIR_DISTANCE,
  colorDistance,
} from "@/lib/probabilityBarPair";

type TeamColors = { primary_color?: string | null } | null;

/**
 * A scheduled game card, which is the state that draws a bar. Built from the
 * shape `/api/feed?mode=sports` actually serves: note that `home_team_data` is
 * OMITTED by default rather than set to null, because that is what the endpoint
 * does — the key is absent on 0 of 37 rows measured 2026-09-04.
 */
function gameCard(away: TeamColors, home: TeamColors, over: Partial<FeedEventData> = {}): FeedItem {
  const data: Record<string, unknown> = {
    id: 15300843,
    external_id: "abc123",
    sport: "baseball_mlb",
    sport_name: "MLB",
    home_team: "Los Angeles Dodgers",
    away_team: "St. Louis Cardinals",
    commence_time: "2026-09-05T18:40:00Z",
    status: "scheduled",
    home_score: null,
    away_score: null,
    current_odds: { home_probability: 0.62, away_probability: 0.38 },
    ...over,
  };
  if (away !== null) data.away_team_data = away;
  if (home !== null) data.home_team_data = home;
  return { type: "event", data: data as unknown as FeedEventData } as FeedItem;
}

interface Segment {
  side: string;
  backgroundColor: string;
  opacity: string;
  width: string;
}

/**
 * Pull both segments as (side, colour) PAIRS.
 *
 * ⚠️ Anchored on `rounded-l-full` / `rounded-r-full`, NOT on the
 * `data-bar-segment` attribute this ship adds.
 *
 * The first version of this extractor selected on `data-bar-segment`, and that
 * made every test in the file arm-dependent: on master the attribute does not
 * exist, so the extractor yielded nothing, the width CONTROL threw, and the
 * three "draws no bar" CONTROLs passed for entirely the wrong reason — they
 * would have been green even if master had rendered a bar. A guard whose
 * POPULATION is selected by a marker its own diff adds is not a guard on the
 * parent.
 *
 * These two classes appear exactly once each in the component on BOTH arms and
 * only on the bar, and they encode the side the segment is on (left = away,
 * right = home), which is the fact the assertions need.
 *
 * The extractor also reports its own yield: a bar has exactly two segments, so
 * anything else means the markup moved and the assertions would otherwise
 * quietly measure nothing.
 */
function segments(html: string): Segment[] {
  const found: Segment[] = [];
  for (const [cls, side] of [
    ["rounded-l-full", "away"],
    ["rounded-r-full", "home"],
  ] as const) {
    const re = new RegExp(`<div([^>]*?${cls}[^>]*?)>`, "g");
    let m: RegExpExecArray | null;
    while ((m = re.exec(html)) !== null) {
      const attrs = m[1];
      const style = /style="([^"]*)"/.exec(attrs)?.[1] ?? "";
      const decl = (name: string) =>
        new RegExp(`${name}\\s*:\\s*([^;"]+)`).exec(style)?.[1]?.trim() ?? "";
      found.push({
        side,
        backgroundColor: decl("background-color"),
        opacity: decl("opacity"),
        width: decl("width"),
      });
    }
  }
  const declaredLeft = (html.match(/rounded-l-full/g) ?? []).length;
  const declaredRight = (html.match(/rounded-r-full/g) ?? []).length;
  if (found.length !== declaredLeft + declaredRight) {
    throw new Error(
      `extractor parsed ${found.length} segments but the markup declares ${
        declaredLeft + declaredRight
      }`
    );
  }
  if (found.length && found.length !== 2) {
    throw new Error(`a bar has two segments; found ${found.length}`);
  }
  return found;
}

const bySide = (html: string) =>
  Object.fromEntries(segments(html).map((s) => [s.side, s]));

// ── 1. THE DEFECT, AS THE READER MET IT ──────────────────────────────────────

describe("the bar is drawn at all", () => {
  it("a card with no team colours paints two real colours, not a var()", () => {
    // The whole bug in one assertion. On master both of these read
    // `var(--color-text-muted)` / `var(--color-accent-brand)`.
    const seg = bySide(renderToStaticMarkup(<FeedCard item={gameCard(null, null)} />));
    expect(seg.away.backgroundColor).toBe(AWAY_DEFAULT);
    expect(seg.home.backgroundColor).toBe(HOME_DEFAULT);
  });

  it("neither segment's colour is a CSS variable, an empty string, or transparent", () => {
    for (const seg of segments(renderToStaticMarkup(<FeedCard item={gameCard(null, null)} />))) {
      expect(seg.backgroundColor).not.toContain("var(");
      expect(seg.backgroundColor).not.toBe("");
      expect(seg.backgroundColor).not.toBe("transparent");
      expect(seg.backgroundColor).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
  });

  it("the two halves are DISTINGUISHABLE, not merely different strings — the native sibling's symptom (#2902)", () => {
    // ⚠️ `expect(away).not.toBe(home)` is green on the bug: master's two halves
    // are the strings `var(--color-text-muted)` and `var(--color-accent-brand)`,
    // which are unequal while both paint nothing. The claim has to be about the
    // colours, so it is measured with the same rule the module enforces.
    const seg = bySide(renderToStaticMarkup(<FeedCard item={gameCard(null, null)} />));
    const rgb = (hex: string) => {
      const p = hexToRgb(hex);
      if (!p) throw new Error(`segment colour ${hex} is not a paintable colour`);
      const n = p.split(" ").map(Number);
      return [n[0], n[1], n[2]] as [number, number, number];
    };
    const paint = (hex: string) =>
      rgb(hex).map((v) => SEGMENT_OPACITY * v + (1 - SEGMENT_OPACITY) * 255) as unknown as [
        number,
        number,
        number,
      ];
    expect(
      colorDistance(paint(seg.away.backgroundColor), paint(seg.home.backgroundColor))
    ).toBeGreaterThanOrEqual(MIN_PAIR_DISTANCE);
  });

  it("the data-bar-segment markers agree with the side each segment is rounded on", () => {
    // Part of the ship, not a control: the attribute is new. It exists so a
    // production DOM read can bind a colour to a side without re-deriving it
    // from a Tailwind class, and this pins it to the positional truth so the
    // two cannot drift apart.
    const html = renderToStaticMarkup(<FeedCard item={gameCard(null, null)} />);
    expect(/rounded-l-full[^>]*data-bar-segment="away"/.test(html)).toBe(true);
    expect(/rounded-r-full[^>]*data-bar-segment="home"/.test(html)).toBe(true);
  });

  it("both halves render at ONE opacity, so neither is dimmed out of sight", () => {
    // The old code used 0.3 for the away fallback, which composites to 1.28:1
    // against the white card — below the visibility floor even with a real
    // colour. A per-side opacity must not come back.
    const seg = bySide(renderToStaticMarkup(<FeedCard item={gameCard(null, null)} />));
    expect(seg.away.opacity).toBe(String(SEGMENT_OPACITY));
    expect(seg.home.opacity).toBe(String(SEGMENT_OPACITY));
  });
});

// ── 2. COLOUR IS BOUND TO ITS OWN SIDE ───────────────────────────────────────

describe("each colour lands on the side it belongs to", () => {
  it("a real away colour paints the AWAY half and does not move to home", () => {
    // The one row shape carrying a colour on production today: the malformed
    // `St.Louis Cardinals` twin (external_id null, #2630/#2958).
    const seg = bySide(
      renderToStaticMarkup(
        <FeedCard item={gameCard({ primary_color: "#be0a14" }, null)} />
      )
    );
    expect(seg.away.backgroundColor).toBe("#be0a14");
    expect(seg.home.backgroundColor).not.toBe("#be0a14");
  });

  it("a real home colour paints the HOME half", () => {
    const seg = bySide(
      renderToStaticMarkup(
        <FeedCard item={gameCard(null, { primary_color: "#005A9C" })} />
      )
    );
    expect(seg.home.backgroundColor).toBe("#005A9C");
    expect(seg.away.backgroundColor).not.toBe("#005A9C");
  });

  it("swapping the two inputs swaps the two segments, and nothing else", () => {
    // If the component read the pair positionally from a bare tuple, this
    // would pass while the halves were transposed. Bound per side, it cannot.
    const a = bySide(
      renderToStaticMarkup(
        <FeedCard item={gameCard({ primary_color: "#be0a14" }, { primary_color: "#005A9C" })} />
      )
    );
    const b = bySide(
      renderToStaticMarkup(
        <FeedCard item={gameCard({ primary_color: "#005A9C" }, { primary_color: "#be0a14" })} />
      )
    );
    expect([a.away.backgroundColor, a.home.backgroundColor]).toEqual(["#be0a14", "#005A9C"]);
    expect([b.away.backgroundColor, b.home.backgroundColor]).toEqual(["#005A9C", "#be0a14"]);
  });

  it("a white team colour does not paint a white segment on a white card", () => {
    // 26 teams carry #ffffff. A "real" colour reproducing the reported symptom.
    const seg = bySide(
      renderToStaticMarkup(
        <FeedCard item={gameCard({ primary_color: "#ffffff" }, null)} />
      )
    );
    expect(seg.away.backgroundColor).not.toBe("#ffffff");
    expect(seg.away.backgroundColor).toBe(AWAY_DEFAULT);
  });
});

// ── 3. CONTROLS — GREEN ON THE PARENT TOO ────────────────────────────────────
//
// Each of these asserts something master already did correctly. Every predicate
// they select on — the widths, the card's own text — exists on the parent, so
// they are genuine controls rather than claims dressed as controls.

describe("CONTROL: what this ship must not move", () => {
  it("CONTROL: the widths are still the two probabilities, rounded", () => {
    const seg = bySide(renderToStaticMarkup(<FeedCard item={gameCard(null, null)} />));
    expect(seg.away.width).toBe("38%");
    expect(seg.home.width).toBe("62%");
  });

  it("CONTROL: a FINISHED card still draws no bar at all", () => {
    const html = renderToStaticMarkup(
      <FeedCard
        item={gameCard(null, null, {
          status: "completed",
          home_score: 5,
          away_score: 3,
        })}
      />
    );
    expect(segments(html)).toHaveLength(0);
  });

  it("CONTROL: a SUSPENDED card still draws no bar at all", () => {
    const html = renderToStaticMarkup(
      <FeedCard item={gameCard(null, null, { status: "suspended" })} />
    );
    expect(segments(html)).toHaveLength(0);
  });

  it("CONTROL: a card with no odds draws no bar, rather than a bar of two defaults", () => {
    const html = renderToStaticMarkup(
      <FeedCard item={gameCard(null, null, { current_odds: undefined })} />
    );
    expect(segments(html)).toHaveLength(0);
  });

  it("CONTROL: the card still names both teams", () => {
    const html = renderToStaticMarkup(<FeedCard item={gameCard(null, null)} />);
    expect(html).toContain("Los Angeles Dodgers");
    expect(html).toContain("St. Louis Cardinals");
  });
});
