/**
 * #10405 — expanding the props rail printed its "not shown" line twice.
 *
 * Production, /events/15322539 (Rays 1–0 Yankees, Final), 2026-10-04 03:03Z:
 * "See all 14 questions" ended with
 *
 *     Also not shown: 2 with conflicting prices.
 *     Also not shown: 2 with conflicting prices.
 *
 * because PropDivergenceDetail (the expanded list) carries the line and the
 * rail printed its own under it. Rendered from the same real slice #10397 pins
 * (its withheld Rice ladder is the two conflicting rows).
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropDivergenceRail from "@/components/PropDivergenceRail";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import payload from "../fixtures/eventPlayerProps.15322539.invertedLadder.json";

const ROWS = payload as unknown as PlayerPropRow[];

function text(node: React.ReactElement): string {
  return renderToStaticMarkup(node)
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

const count = (s: string, re: RegExp) => (s.match(re) ?? []).length;
const NOT_SHOWN = /Also not shown: 2 with conflicting prices\./g;

describe("#10405 — the rail's 'not shown' line appears once", () => {
  it("collapsed: the rail prints it once", () => {
    const out = text(<PropDivergenceRail playerProps={ROWS} status="completed" />);
    expect(count(out, NOT_SHOWN)).toBe(1);
    expect(out).toMatch(/See all 14 questions/);
  });

  it("expanded: printed once, by the detail list", () => {
    const out = text(
      <PropDivergenceRail playerProps={ROWS} status="completed" defaultExpanded />,
    );
    expect(count(out, NOT_SHOWN)).toBe(1);
    // The detail really is open: its legend and the Show fewer control render,
    // and the line sits after the legend (the detail's copy, not the rail's).
    expect(out).toMatch(/Show fewer/);
    const legend = out.indexOf("Ordered by how far the outcome landed from the pregame mark.");
    expect(legend).toBeGreaterThan(-1);
    expect(out.search(NOT_SHOWN)).toBeGreaterThan(legend);
  });
});
