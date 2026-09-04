/**
 * UX-1052 item 2 — the exact-score ladder prints scorelines, not invented rungs.
 *
 * Alex, shopping /sports at 1:00pm PT on 2026-09-03:
 *
 *     "The exact-score ladders are broken. Player Props cards … show rungs
 *      '≥ 0, ≥ 1, ≥ 2, ≥ 2' and '≥ 0, ≥ 0, ≥ 0, ≥ 1' at 1–6% — rung labels are
 *      not the outcomes. Show the real scorelines or the real thresholds; a
 *      rung that cannot be labelled is not rendered."
 *
 * The parser fix lives in `backend/app/utils/market_grouping.py` and is proved
 * by `backend/tests/test_exact_score_ladder_1052.py`. THIS file is the other
 * half, and neither substitutes for the other: the backend suite proves the
 * payload stopped lying, and it would stay green on a build where the renderer
 * ignored the new `label` field and kept formatting "≥ 0" from a zeroed
 * `threshold_value`. So this renders the real components.
 *
 * It also pins the rule Alex stated as a rule, not just its instance: a point
 * that carries no label AND no real threshold is DROPPED — by the renderer and
 * by the admission that feeds the section's count, so the two cannot disagree
 * (the #2646 class `propStripAdmission` exists for).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

import GroupedFeedRenderer from "@/components/GroupedFeedRenderer";
import { buildThresholdRungs } from "@/components/QuantityGroup";
import { admittedPropStripRows } from "@/lib/sports/propStripAdmission";
import type { GroupedFeedItem, ThresholdFeedItem } from "@/lib/types";

/** The AC Milan card from the 2026-09-03 payload, as the fixed backend serves it. */
const EXACT_SCORE_ROW: ThresholdFeedItem = {
  type: "threshold",
  kind: "exact_score",
  group_key: "exact_score:group:polymarket:960217",
  title: "AC Milan vs. Sport Lisboa e Benfica - Exact Score",
  outcome_count: 5,
  points: [
    { id: 1, name: "AC Milan 2 - 2 Sport Lisboa e Benfica", probability: 0.085,
      label: "2–2", threshold_value: 0, threshold_unit: "", threshold_direction: "exact" },
    { id: 2, name: "AC Milan 0 - 3 Sport Lisboa e Benfica", probability: 0.07,
      label: "0–3", threshold_value: 0, threshold_unit: "", threshold_direction: "exact" },
    { id: 3, name: "AC Milan 1 - 3 Sport Lisboa e Benfica", probability: 0.07,
      label: "1–3", threshold_value: 0, threshold_unit: "", threshold_direction: "exact" },
    { id: 4, name: "AC Milan 2 - 3 Sport Lisboa e Benfica", probability: 0.065,
      label: "2–3", threshold_value: 0, threshold_unit: "", threshold_direction: "exact" },
    { id: 5, name: "AC Milan 3 - 3 Sport Lisboa e Benfica", probability: 0.06,
      label: "3–3", threshold_value: 0, threshold_unit: "", threshold_direction: "exact" },
  ],
};

/** A genuine ladder — the control that must keep its "≥ N" rungs. */
const THRESHOLD_ROW: ThresholdFeedItem = {
  type: "threshold",
  kind: "threshold",
  group_key: "threshold:group:total-goals",
  title: "Total Goals",
  outcome_count: 2,
  points: [
    { id: 11, name: "Over 2.5 goals", probability: 0.55, threshold_value: 2.5,
      threshold_unit: "goals", threshold_direction: "above" },
    { id: 12, name: "Over 3.5 goals", probability: 0.3, threshold_value: 3.5,
      threshold_unit: "goals", threshold_direction: "above" },
  ],
};

function render(items: GroupedFeedItem[], compact = true) {
  return renderToStaticMarkup(<GroupedFeedRenderer items={items} compact={compact} />);
}

describe("UX-1052 item 2 — exact-score rungs (render path)", () => {
  it("labels every rung with the scoreline the market offers", () => {
    const html = render([EXACT_SCORE_ROW]);
    for (const label of ["2–2", "0–3", "1–3", "2–3"]) {
      expect(html).toContain(label);
    }
  });

  it("prints no ≥ / ≤ rung anywhere on an exact-score card", () => {
    const html = render([EXACT_SCORE_ROW]);
    expect(html).not.toContain("≥");
    expect(html).not.toContain("≤");
  });

  it("leads with the most likely scoreline, not the lowest one", () => {
    // The compact card shows four of five rungs. Sorted by `value` — which is
    // zero on every exact-score point — the order would be the payload's, and
    // sorted by scoreline it would be "0–3" first. The reading is 2–2 (8.5%).
    const html = render([EXACT_SCORE_ROW]);
    expect(html.indexOf("2–2")).toBeGreaterThan(-1);
    expect(html.indexOf("2–2")).toBeLessThan(html.indexOf("0–3"));
  });

  it("says how many scorelines the glance card left off", () => {
    // 5 rungs, compact cap of 4.
    expect(render([EXACT_SCORE_ROW])).toContain("1 more scoreline");
  });

  it("keeps the question context — the card is never a naked ladder", () => {
    expect(render([EXACT_SCORE_ROW])).toContain("Exact Score");
  });

  it("leaves a real threshold ladder alone (the control)", () => {
    const html = render([THRESHOLD_ROW]);
    expect(html).toContain("≥ 2.5goals");
    expect(html).toContain("≥ 3.5goals");
    expect(html).not.toContain("more scoreline");
  });
});

/** The tennis shape: the winner is IN the label because the digits collide. */
const TENNIS_ROW: ThresholdFeedItem = {
  type: "threshold",
  kind: "exact_score",
  group_key: "exact_score:group:polymarket:tennis-1",
  title: "Iva Jovic vs Magdalena Frech: Exact Match Score",
  outcome_count: 4,
  points: [
    { id: 21, name: "Iva Jovic wins 2-0", probability: 0.99, label: "Iva Jovic 2–0",
      threshold_value: 0, threshold_unit: "", threshold_direction: "exact" },
    { id: 22, name: "Iva Jovic wins 2-1", probability: 0.01, label: "Iva Jovic 2–1",
      threshold_value: 0, threshold_unit: "", threshold_direction: "exact" },
    { id: 23, name: "Magdalena Frech wins 2-0", probability: 0.01, label: "Magdalena Frech 2–0",
      threshold_value: 0, threshold_unit: "", threshold_direction: "exact" },
    { id: 24, name: "Magdalena Frech wins 2-1", probability: 0.01, label: "Magdalena Frech 2–1",
      threshold_value: 0, threshold_unit: "", threshold_direction: "exact" },
  ],
};

describe("UX-1052 item 2 — tennis exact match score", () => {
  it("prints the winner beside the score, so no two rungs read alike", () => {
    const html = render([TENNIS_ROW]);
    for (const label of ["Iva Jovic 2–0", "Iva Jovic 2–1", "Magdalena Frech 2–0"]) {
      expect(html).toContain(label);
    }
    expect(html).not.toContain("≥");
  });

  it("switches to the wide label track so a name is not clipped to nothing", () => {
    // `wideLabels` is what makes the label column 45% instead of the fixed
    // numeric w-11 — a two-word label in w-11 truncates to about two glyphs.
    const html = render([TENNIS_ROW]);
    expect(html).toContain("w-[45%]");
    // …and a bare-score card keeps the tight numeric column.
    expect(render([EXACT_SCORE_ROW])).not.toContain("w-[45%]");
  });

  it("leads with the 99% outcome", () => {
    const html = render([TENNIS_ROW]);
    expect(html.indexOf("Iva Jovic 2–0")).toBeLessThan(html.indexOf("Magdalena Frech 2–0"));
  });
});

describe("UX-1052 item 2 — a rung that cannot be labelled is not rendered", () => {
  /** What a pre-fix warm Redis entry, or any future producer bug, can serve. */
  const UNLABELLED: ThresholdFeedItem = {
    ...EXACT_SCORE_ROW,
    group_key: "exact_score:unlabelled",
    points: EXACT_SCORE_ROW.points.map((p) => ({ ...p, label: null })),
  };

  it("drops unlabelable points instead of inventing ≥ 0 for them", () => {
    const rungs = buildThresholdRungs(
      UNLABELLED.points.map((p) => ({
        outcome_id: p.id,
        name: p.name,
        probability: p.probability,
        threshold_value: p.threshold_value,
        threshold_unit: p.threshold_unit,
        threshold_direction: p.threshold_direction,
        label: p.label,
      })),
    );
    expect(rungs).toEqual([]);
  });

  it("renders no card at all rather than an empty one", () => {
    const html = render([UNLABELLED]);
    expect(html).not.toContain("≥ 0");
    expect(html).not.toContain("Exact Score");
  });

  it("and the section count agrees — admission drops the same row", () => {
    // The renderer and the heading read ONE list. A row the renderer declines
    // must not still be counted beside "Player Props & Progressions".
    expect(admittedPropStripRows([UNLABELLED])).toEqual([]);
    expect(admittedPropStripRows([EXACT_SCORE_ROW])).toHaveLength(1);
    expect(admittedPropStripRows([THRESHOLD_ROW])).toHaveLength(1);
  });
});
