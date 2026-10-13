/**
 * #10959 — two "all" counts that disagree, one block apart.
 *
 * Production, /events/14780558 (Bills @ Rams, MNF, pregame), 390px,
 * 2026-10-12 23:35Z:
 *
 *     See all 484 props          ← this rail's expand
 *     All 834 props  hide        ← the player-props card directly below
 *
 * The rail counts `eligible` (an opening mark AND a price); the card counts
 * every prop. Both numbers are right, but both are called "all". When the
 * rail's set is smaller it now names its subset. When it is the whole set it
 * still says plain "See all N", because that "all" is true.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropDivergenceRail from "@/components/PropDivergenceRail";
import { selectDivergenceRows } from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import subsetPayload from "../fixtures/eventPlayerProps.15322539.invertedLadder.json";
import wholePayload from "../fixtures/eventPlayerProps.14638896.settled-single.json";

const SUBSET = subsetPayload as unknown as PlayerPropRow[];
const WHOLE = wholePayload as unknown as PlayerPropRow[];

function text(node: React.ReactElement): string {
  return renderToStaticMarkup(node)
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

describe("#10959 — the rail's 'See all' never claims a different 'all' from the props card", () => {
  it("subset: 14 eligible of 88 props → the expand names what it counts", () => {
    const r = selectDivergenceRows({ playerProps: SUBSET, status: "completed" });
    // The specimen really is a subset; without this the test proves nothing.
    expect(r.eligible).toBe(14);
    expect(SUBSET.length).toBe(88);
    const out = text(<PropDivergenceRail playerProps={SUBSET} status="completed" />);
    expect(out).toContain("See all 14 props priced at the open");
  });

  it("whole set: 1 eligible of 1 prop → plain 'See all 1 prop', no qualifier", () => {
    const r = selectDivergenceRows({ playerProps: WHOLE, status: "completed" });
    expect(r.eligible).toBe(WHOLE.length);
    expect(r.notSelected).toBeGreaterThan(0); // the expand renders at all
    const out = text(<PropDivergenceRail playerProps={WHOLE} status="completed" />);
    expect(out).toContain("See all 1 prop");
    expect(out).not.toContain("priced at the open");
  });

  it("expanded: the toggle reads 'Show fewer' with no count either way", () => {
    const out = text(
      <PropDivergenceRail playerProps={SUBSET} status="completed" defaultExpanded />,
    );
    expect(out).toContain("Show fewer");
    expect(out).not.toContain("priced at the open");
  });
});
