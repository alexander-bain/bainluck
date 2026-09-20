/**
 * #4953, the render half — what the sentence actually says on the screen.
 *
 * `propDropNoLine4953.test.ts` proves the taxonomy: a named, thresholdless row
 * is `no_line` and benign. This file proves the consequence a reader sees,
 * because the defect was never in the selector's return value — it was the
 * string under the rail on a live NFL page:
 *
 *     Also not shown: 13 unknown.
 *
 * Rendered from the SAME real production slice
 * (`GET /api/events/14782151/game-markets`, Steelers @ Patriots, 17:0xZ
 * 2026-09-20), so the render and the taxonomy are pinned to one specimen and
 * cannot drift apart.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropDivergenceRail from "@/components/PropDivergenceRail";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import noLinePayload from "../fixtures/eventPlayerProps.14782151.noLine.json";

const ROWS = noLinePayload as unknown as PlayerPropRow[];

/** Visible text only — the sentence is prose, so tags would mask a match. */
function text(node: React.ReactElement): string {
  return renderToStaticMarkup(node)
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

describe("#4953 — the rail's admission sentence", () => {
  it("no longer tells the reader 13 field-market legs are missing", () => {
    const out = text(<PropDivergenceRail playerProps={ROWS} status="live" />);

    // The defect, verbatim, in both of the shapes that string can take.
    expect(out).not.toMatch(/Also not shown/i);
    expect(out).not.toMatch(/couldn't be shown/i);
    // And the enum key must not reach the screen by any other route.
    expect(out).not.toMatch(/\bunknown\b/i);
  });

  it("still renders the rail itself from the same payload", () => {
    // gotcha #43 both directions: silencing the sentence must not have
    // silenced the section. Six priced O/U rows ride in the same fixture, and
    // "What's moving" is the live header.
    const out = text(<PropDivergenceRail playerProps={ROWS} status="live" />);
    expect(out).toMatch(/What's moving/);
  });

  it("still surfaces a genuinely unreadable row", () => {
    // The channel this rail exists for stays open: a nameless row is `unknown`,
    // non-benign, and reaches the screen. If this ever goes quiet, the fix
    // above has over-reached.
    const nameless = {
      market_name: "",
      outcome_name: "",
      threshold: null,
      over_probability: 0.5,
      pregame_mark: 0.3,
    } as unknown as PlayerPropRow;

    const out = text(<PropDivergenceRail playerProps={[nameless]} status="live" />);

    expect(out).toMatch(/couldn't be shown/i);
    // ...and it says it in words, not as its own enum key.
    expect(out).toMatch(/couldn't be read at all/i);
    expect(out).not.toMatch(/1 unknown/i);
  });
});
