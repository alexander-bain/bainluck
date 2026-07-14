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
