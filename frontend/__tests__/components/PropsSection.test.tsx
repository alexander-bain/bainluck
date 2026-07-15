// L2-118 Phase 1: the archetype-agnostic props body — THE SCRIPT / THE
// DIVERGENCE / WHAT HIT. Phase-1 honesty: the pregame-mark + graded fields ship
// with #195; until then the section renders an explicit "pending" line behind the
// same interface (never a fabricated number). Phase 2 is a payload swap.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection, { deriveState } from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";

const ITEMS: PropMark[] = [
  { key: 1, label: "LeBron 25+ points", pregame_mark: 0.6, current: 0.72, graded_result: "hit" },
  { key: 2, label: "Under 220.5 total", pregame_mark: 0.5, current: 0.41, graded_result: "miss" },
];

describe("deriveState (settled-means-settled)", () => {
  test("upcoming → script", () => {
    expect(deriveState("scheduled")).toBe("script");
    expect(deriveState(undefined)).toBe("script");
  });
  test("live → divergence", () => {
    expect(deriveState("live")).toBe("divergence");
    expect(deriveState("in_progress")).toBe("divergence");
  });
  test("settled → graded", () => {
    expect(deriveState("completed")).toBe("graded");
    expect(deriveState("closed")).toBe("graded");
    expect(deriveState("final")).toBe("graded");
  });
});

describe("PropsSection rendering", () => {
  test("THE SCRIPT shows pregame marks when present", () => {
    const html = renderToStaticMarkup(<PropsSection items={ITEMS} state="script" />);
    expect(html).toContain("The script");
    expect(html).toContain("LeBron 25+ points");
    expect(html).toContain("60%"); // pregame_mark
  });

  test("THE DIVERGENCE shows pregame → current with a signed delta", () => {
    const html = renderToStaticMarkup(<PropsSection items={ITEMS} state="divergence" />);
    expect(html).toContain("The divergence");
    expect(html).toContain("72%"); // current
    expect(html).toContain("↑ 12"); // +12 pts, up = accent-brand
    expect(html).toContain("↓ 9"); // -9 pts, down = accent-danger
    expect(html).toContain("text-accent-danger");
  });

  test("WHAT HIT shows graded results", () => {
    const html = renderToStaticMarkup(<PropsSection items={ITEMS} state="graded" />);
    expect(html).toContain("What hit");
    expect(html).toContain("Hit");
    expect(html).toContain("Miss");
  });

  test("honest 'pending' placeholder when #195 fields are null (no fabricated number)", () => {
    const pending: PropMark[] = [
      { key: 9, label: "Anytime TD", pregame_mark: null, current: 0.44, graded_result: null },
    ];
    const script = renderToStaticMarkup(<PropsSection items={pending} state="script" />);
    expect(script).toContain("pregame mark pending");
    const graded = renderToStaticMarkup(<PropsSection items={pending} state="graded" />);
    expect(graded).toContain("grading pending");
  });

  test("L2-123: pending_label renders the honest state, never a fabricated flat", () => {
    // A degenerate (no-price) family — the #199 wide-spread/no-trade class. It must
    // show the honest label in EVERY state, never the fake number, never blank.
    const degenerate: PropMark[] = [
      { key: 7, label: "Round 2 Leader", pregame_mark: null, current: null, pending_label: "Opens after Round 1" },
    ];
    for (const state of ["script", "divergence", "graded"] as const) {
      const html = renderToStaticMarkup(<PropsSection items={degenerate} state={state} />);
      expect(html).toContain("Round 2 Leader");
      expect(html).toContain("Opens after Round 1");
      // Never the fabricated flat, never a bare em-dash value, never the #195 seams.
      expect(html).not.toContain("24%");
      expect(html).not.toContain("pregame mark pending");
      expect(html).not.toContain("script pending");
    }
  });

  test("L2-123: pending_label wins even if a stray current sneaks through", () => {
    // Defense in depth: if the store still holds a fabricated flat, the pending
    // label suppresses it rather than rendering the lie.
    const items: PropMark[] = [
      { key: 8, label: "Top 5 Finish", pregame_mark: null, current: 0.011, pending_label: "No market yet" },
    ];
    const html = renderToStaticMarkup(<PropsSection items={items} state="divergence" />);
    expect(html).toContain("No market yet");
    expect(html).not.toContain("1%");
  });

  test("derives state from eventStatus when state omitted", () => {
    const html = renderToStaticMarkup(<PropsSection items={ITEMS} eventStatus="completed" />);
    expect(html).toContain("What hit");
  });

  test("empty items render nothing", () => {
    expect(renderToStaticMarkup(<PropsSection items={[]} />)).toBe("");
  });

  test("never renders american_odds / moneyline", () => {
    const html = renderToStaticMarkup(<PropsSection items={ITEMS} state="divergence" />);
    expect(html).not.toContain("american_odds");
    expect(html).not.toMatch(/[+-]\d{3,}/);
  });
});

describe("THE DIVERGENCE ranking (biggest mover first)", () => {
  const UNSORTED: PropMark[] = [
    { key: "small", label: "Small mover", pregame_mark: 0.5, current: 0.52 }, // 2
    { key: "big", label: "Big mover", pregame_mark: 0.4, current: 0.72 }, // 32
    { key: "mid", label: "Mid mover", pregame_mark: 0.5, current: 0.62 }, // 12
  ];

  test("divergence sorts by absolute movement, biggest first", () => {
    const html = renderToStaticMarkup(<PropsSection items={UNSORTED} state="divergence" />);
    const iBig = html.indexOf("Big mover");
    const iMid = html.indexOf("Mid mover");
    const iSmall = html.indexOf("Small mover");
    expect(iBig).toBeGreaterThanOrEqual(0);
    expect(iBig).toBeLessThan(iMid);
    expect(iMid).toBeLessThan(iSmall);
  });

  test("rows with no computable movement sink below movers, keeping order", () => {
    const withNulls: PropMark[] = [
      { key: "pending-a", label: "Pending A", pregame_mark: null, current: 0.5 },
      { key: "mover", label: "Real mover", pregame_mark: 0.4, current: 0.6 }, // 20
      { key: "pending-b", label: "Pending B", pregame_mark: 0.5, current: null },
    ];
    const html = renderToStaticMarkup(<PropsSection items={withNulls} state="divergence" />);
    const iMover = html.indexOf("Real mover");
    const iA = html.indexOf("Pending A");
    const iB = html.indexOf("Pending B");
    expect(iMover).toBeLessThan(iA); // movers rank above null-movement rows
    expect(iA).toBeLessThan(iB); // null rows keep original relative order (stable)
  });

  test("SCRIPT state preserves payload order (no divergence re-rank)", () => {
    const html = renderToStaticMarkup(<PropsSection items={UNSORTED} state="script" />);
    const iSmall = html.indexOf("Small mover");
    const iBig = html.indexOf("Big mover");
    expect(iSmall).toBeLessThan(iBig); // original order intact
  });
});
