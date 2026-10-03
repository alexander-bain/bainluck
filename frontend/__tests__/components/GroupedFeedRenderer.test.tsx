// L2-119: the grouped props strip renders the shared Quantity kernel per
// question. formatThresholdTitle enforces the kernel discipline — a ladder
// never renders without its question context (a non-empty title).

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

// framer-motion renders its base element under SSR; map motion.* / m.* to the
// plain tag so the static markup is stable (same proxy as
// groupedFeedImageIdentity.test.tsx).
const tagProxy = () =>
  new Proxy(
    {},
    {
      get: (_t, tag: string) => {
        const Comp = ({ children, ...props }: { children?: React.ReactNode }) =>
          React.createElement(tag, props, children);
        Comp.displayName = `motion.${tag}`;
        return Comp;
      },
    },
  );

jest.mock("framer-motion", () => ({
  __esModule: true,
  motion: tagProxy(),
  m: tagProxy(),
  LazyMotion: ({ children }: { children?: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
  domAnimation: {},
}));

import GroupedFeedRenderer, {
  disambiguateThresholdRungs,
  formatThresholdTitle,
} from "../../components/GroupedFeedRenderer";
import { buildThresholdRungs } from "../../components/QuantityGroup";
import type { ThresholdFeedItem } from "@/lib/types";

describe("formatThresholdTitle", () => {
  test("sentence-cases the lowercased backend stem", () => {
    expect(formatThresholdTitle("will the fed cut rates")).toBe(
      "Will the fed cut rates",
    );
  });

  test("trims dangling stem artifacts left by the numeric-strip", () => {
    // "Will Bitcoin exceed $90,000?" → stem "will bitcoin exceed $" → title
    expect(formatThresholdTitle("will bitcoin exceed $")).toBe(
      "Will bitcoin exceed",
    );
  });

  test("collapses whitespace", () => {
    expect(formatThresholdTitle("player   points   scored")).toBe(
      "Player points scored",
    );
  });

  test("never returns an empty title (kernel discipline)", () => {
    expect(formatThresholdTitle("")).toBe("Threshold market");
    expect(formatThresholdTitle("  # $ ")).toBe("Threshold market");
  });
});

// #10280 — the retained production specimens, verbatim from
// `GET /api/futures/grouped-feed?limit=20&sports_only=true` at 2026-10-03
// 04:06Z (release v5433). One Kalshi event = both clubs' ladders in one card;
// the numeric label alone printed `≥ 1.5 goals 22%` beside `≥ 1.5 goals 37%`.
const WSH_TB_SPREAD: ThresholdFeedItem = {
  type: "threshold",
  kind: "threshold",
  group_key: "threshold:group:kalshi:KXNHLSPREAD-26OCT03WSHTB",
  title: "Washington vs Tampa Bay: Spread",
  outcome_count: 4,
  points: [
    { id: 239380492, name: "Washington wins by over 1.5 goals", probability: 0.22, threshold_value: 1.5, threshold_unit: "goals", threshold_direction: "above" },
    { id: 239380491, name: "Tampa Bay wins by over 1.5 goals", probability: 0.365, threshold_value: 1.5, threshold_unit: "goals", threshold_direction: "above" },
    { id: 239380494, name: "Washington wins by over 2.5 goals", probability: 0.135, threshold_value: 2.5, threshold_unit: "goals", threshold_direction: "above" },
    { id: 239380493, name: "Tampa Bay wins by over 2.5 goals", probability: 0.255, threshold_value: 2.5, threshold_unit: "goals", threshold_direction: "above" },
  ],
} as ThresholdFeedItem;

const ANA_VGK_TEAM_TOTAL: ThresholdFeedItem = {
  type: "threshold",
  kind: "threshold",
  group_key: "threshold:group:kalshi:KXNHLTEAMTOTAL-26OCT02ANAVGK",
  title: "Anaheim vs Vegas: Team Total",
  outcome_count: 10,
  points: [
    { id: 239425223, name: "Vegas over 1.5", probability: 0.41, threshold_value: 1.5, threshold_unit: "", threshold_direction: "above" },
    { id: 239425228, name: "Anaheim over 1.5", probability: 0.99, threshold_value: 1.5, threshold_unit: "", threshold_direction: "above" },
    { id: 239425222, name: "Vegas over 2.5", probability: 0.185, threshold_value: 2.5, threshold_unit: "", threshold_direction: "above" },
    { id: 239425227, name: "Anaheim over 2.5", probability: 0.99, threshold_value: 2.5, threshold_unit: "", threshold_direction: "above" },
    { id: 239425221, name: "Vegas over 3.5", probability: 0.15, threshold_value: 3.5, threshold_unit: "", threshold_direction: "above" },
    { id: 239425226, name: "Anaheim over 3.5", probability: 0.99, threshold_value: 3.5, threshold_unit: "", threshold_direction: "above" },
    { id: 239425220, name: "Vegas over 4.5", probability: 0.03, threshold_value: 4.5, threshold_unit: "", threshold_direction: "above" },
    { id: 239425225, name: "Anaheim over 4.5", probability: 0.715, threshold_value: 4.5, threshold_unit: "", threshold_direction: "above" },
    { id: 239425224, name: "Anaheim over 5.5", probability: 0.3, threshold_value: 5.5, threshold_unit: "", threshold_direction: "above" },
    { id: 239425219, name: "Vegas over 5.5", probability: 0.01, threshold_value: 5.5, threshold_unit: "", threshold_direction: "above" },
  ],
} as ThresholdFeedItem;

// Control: the same game's single-subject Total Goals ladder (same payload).
const MTL_PIT_TOTAL: ThresholdFeedItem = {
  type: "threshold",
  kind: "threshold",
  group_key: "threshold:group:kalshi:KXNHLTOTAL-26OCT03MTLPIT",
  title: "Montreal vs Pittsburgh: Total Goals",
  outcome_count: 4,
  points: [
    { id: 239380591, name: "Over 1.5 goals scored", probability: 0.98, threshold_value: 1.5, threshold_unit: "goals", threshold_direction: "above" },
    { id: 239380592, name: "Over 2.5 goals scored", probability: 0.965, threshold_value: 2.5, threshold_unit: "goals", threshold_direction: "above" },
    { id: 239380593, name: "Over 3.5 goals scored", probability: 0.875, threshold_value: 3.5, threshold_unit: "goals", threshold_direction: "above" },
    { id: 239380594, name: "Over 4.5 goals scored", probability: 0.81, threshold_value: 4.5, threshold_unit: "goals", threshold_direction: "above" },
  ],
} as ThresholdFeedItem;

// Control: a tennis exact score — explicit labels already name the winner.
const EXACT_SCORE: ThresholdFeedItem = {
  type: "threshold",
  kind: "exact_score",
  group_key: "threshold:group:kalshi:EXACT-SPECIMEN",
  title: "Jovic vs Gauff: Exact Match Score",
  outcome_count: 2,
  points: [
    { id: 1, name: "Iva Jovic 2-1", label: "Iva Jovic 2–1", probability: 0.2, threshold_value: 0, threshold_unit: "", threshold_direction: "exact" },
    { id: 2, name: "Coco Gauff 2-1", label: "Coco Gauff 2–1", probability: 0.3, threshold_value: 0, threshold_unit: "", threshold_direction: "exact" },
  ],
} as ThresholdFeedItem;

/** Every rung's `aria-label` ("<label>: <pct>") in render order. */
function renderedRungs(item: ThresholdFeedItem, compact = false): string[] {
  const html = renderToStaticMarkup(
    <GroupedFeedRenderer items={[item]} compact={compact} />,
  );
  return Array.from(html.matchAll(/aria-label="([^"]+: [^"]+)"/g)).map((m) =>
    m[1].replace(/&amp;/g, "&"),
  );
}

function rungsFor(item: ThresholdFeedItem) {
  return buildThresholdRungs(
    item.points.map((p) => ({
      outcome_id: p.id,
      name: p.name,
      probability: p.probability,
      threshold_value: p.threshold_value,
      threshold_unit: p.threshold_unit,
      threshold_direction: p.threshold_direction,
      label: p.label,
    })),
  );
}

describe("#10280 — a two-team ladder names the team on every rung", () => {
  test("WSH/TB spread: four distinct rungs, each with its team and its own number", () => {
    expect(renderedRungs(WSH_TB_SPREAD)).toEqual([
      "Washington wins by over 1.5 goals: 22%",
      "Tampa Bay wins by over 1.5 goals: 37%",
      "Washington wins by over 2.5 goals: 14%",
      "Tampa Bay wins by over 2.5 goals: 26%",
    ]);
  });

  test("ANA/VGK team total: every number kept, labels unique, title order at each line", () => {
    const rows = renderedRungs(ANA_VGK_TEAM_TOTAL);
    expect(rows).toHaveLength(ANA_VGK_TEAM_TOTAL.points.length);
    const labels = rows.map((r) => r.split(": ")[0]);
    expect(new Set(labels).size).toBe(labels.length);
    expect(rows).toEqual([
      "Anaheim over 1.5: 99%",
      "Vegas over 1.5: 41%",
      "Anaheim over 2.5: 99%",
      "Vegas over 2.5: 19%",
      "Anaheim over 3.5: 99%",
      "Vegas over 3.5: 15%",
      "Anaheim over 4.5: 72%",
      "Vegas over 4.5: 3%",
      "Anaheim over 5.5: 30%",
      "Vegas over 5.5: 1%",
    ]);
  });

  test("the /sports compact strip shows both clubs at the first two lines", () => {
    expect(renderedRungs(ANA_VGK_TEAM_TOTAL, true)).toEqual([
      "Anaheim over 1.5: 99%",
      "Vegas over 1.5: 41%",
      "Anaheim over 2.5: 99%",
      "Vegas over 2.5: 19%",
    ]);
  });

  test("every point id and probability survives the relabel", () => {
    for (const item of [WSH_TB_SPREAD, ANA_VGK_TEAM_TOTAL]) {
      const built = rungsFor(item);
      const named = disambiguateThresholdRungs(built, item.points, item.title);
      expect(named).not.toBeNull();
      const byKey = (rs: typeof built) =>
        rs.map((r) => [r.key, r.probability, r.value]).sort((a, b) => Number(a[0]) - Number(b[0]));
      expect(byKey(named!)).toEqual(byKey(built));
    }
  });

  test("strawman: without the relabel these specimens DO collide", () => {
    const labels = rungsFor(WSH_TB_SPREAD).map((r) => r.label);
    expect(labels).toEqual(["≥ 1.5 goals", "≥ 1.5 goals", "≥ 2.5 goals", "≥ 2.5 goals"]);
  });

  test("control: a single-subject Total Goals ladder is unchanged", () => {
    expect(disambiguateThresholdRungs(rungsFor(MTL_PIT_TOTAL), MTL_PIT_TOTAL.points, MTL_PIT_TOTAL.title)).toBeNull();
    expect(renderedRungs(MTL_PIT_TOTAL)).toEqual([
      "≥ 1.5 goals: 98%",
      "≥ 2.5 goals: 97%",
      "≥ 3.5 goals: 88%",
      "≥ 4.5 goals: 81%",
    ]);
  });

  test("control: an exact-score ladder keeps its explicit labels", () => {
    expect(renderedRungs(EXACT_SCORE)).toEqual([
      "Coco Gauff 2–1: 30%",
      "Iva Jovic 2–1: 20%",
    ]);
  });

  test("names that cannot separate the rungs leave the ladder as it was", () => {
    const pts = WSH_TB_SPREAD.points.map((p) => ({ ...p, name: "Spread" }));
    expect(disambiguateThresholdRungs(rungsFor({ ...WSH_TB_SPREAD, points: pts }), pts, WSH_TB_SPREAD.title)).toBeNull();
  });
});
