// #10109: on the live Bank of Utah page (round 1), Bubble Watch printed
// "SAFE — WILL MAKE CUT" over three golfers at E and 51% under a "Projected
// cut: -2" chip, with golfers at -1 and 49% below the line "on the bubble".
// The rows split on make_cut_prob ≥ 50 while the cut was the median row's
// score, and the three "safe" E golfers hadn't teed off. The guard: the labels
// say "projected", and a cut score is printed only when posted scores agree
// with the probability split.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import BubbleWatch, { projectedCutScore } from "@/components/event/BubbleWatch";
import type { EventConceptCompetitor } from "@/lib/types";

jest.mock("@/components/EntityImage", () => ({
  __esModule: true,
  default: () => null,
}));

function golfer(
  name: string,
  score_to_par: number,
  make_cut_prob: number,
  position: string,
  thru: string | number,
): EventConceptCompetitor {
  return {
    name,
    probability: 0.01,
    score_to_par,
    make_cut_prob,
    position,
    thru,
  } as unknown as EventConceptCompetitor;
}

// The issue's specimen, verbatim: thru arrives as a NUMBER on the wire even
// though the type says string.
const SPECIMEN = [
  golfer("Adam Svensson", 0, 51, "--", 0),
  golfer("Brice Garnett", 0, 51, "--", 0),
  golfer("Nick Hardy", 0, 51, "--", 0),
  golfer("Garrick Higgo", -1, 49, "T32", 12),
  golfer("Joe Highsmith", -1, 48, "T32", 13),
  golfer("Paul Peterson", 0, 48, "T40", 11),
];

const render = (cs: EventConceptCompetitor[]) =>
  renderToStaticMarkup(<BubbleWatch competitors={cs} currentRound={1} domain="golf" />);

describe("#10109 Bubble Watch's cut line agrees with its rows", () => {
  it("the specimen no longer says 'safe — will make cut' or prints a contradicting cut score", () => {
    const html = render(SPECIMEN);
    expect(html).not.toMatch(/will make cut/i);
    expect(html).not.toMatch(/safe/i);
    expect(html).not.toContain("Projected cut:");
    expect(html).toContain("Projected to make the cut");
    expect(html).toContain("Projected to miss the cut");
    // The line still draws, with no score on it.
    expect(html).toMatch(/CUT LINE<\/span>/);
    expect(projectedCutScore(SPECIMEN)).toBeNull();
  });

  it("prints the cut score when posted scores agree with the split", () => {
    const cs = [
      golfer("A", -3, 70, "T10", 14),
      golfer("B", -2, 55, "T20", 15),
      golfer("C", -1, 45, "T30", 16),
      golfer("D", 0, 30, "T40", "F"),
    ];
    expect(projectedCutScore(cs)).toBe(-2);
    const html = render(cs);
    expect(html).toContain("Projected cut: -2");
    expect(html).toContain("CUT LINE · -2");
  });

  it("withholds the score when a started golfer above the line has a worse score than one below", () => {
    const cs = [
      golfer("A", -2, 70, "T20", 14),
      golfer("B", 0, 51, "T40", 12), // E, projected to make it
      golfer("C", -1, 49, "T32", 17), // -1, projected to miss
    ];
    expect(projectedCutScore(cs)).toBeNull();
    expect(render(cs)).not.toContain("Projected cut:");
  });

  it("an unstarted golfer's E is not a score and cannot veto an agreeing field", () => {
    const cs = [
      golfer("A", -2, 60, "T20", 14),
      golfer("Unstarted", 0, 52, "--", "0"),
      golfer("C", -1, 40, "T30", 16),
    ];
    expect(projectedCutScore(cs)).toBe(-2);
  });

  it("a round-2 golfer who hasn't started today keeps their posted round-1 score", () => {
    const cs = [
      golfer("A", -2, 60, "T20", 14),
      golfer("R1 total", 0, 52, "T45", "0"), // E after round 1, holds a position
      golfer("C", -1, 40, "T30", 16),
    ];
    // E is posted, so the maker at E sits above a misser at -1: they disagree.
    expect(projectedCutScore(cs)).toBeNull();
  });

  it("a golfer printed at 50% sits above the line, not under 'projected to miss' (after-LOOK, raw 49.6)", () => {
    const cs = [
      golfer("Nick Hardy", 0, 51, "--", 0),
      golfer("Seamus Power", 0, 49.6, "T41", 12),
      golfer("Patrick Rodgers", -1, 48, "T35", 17),
    ];
    const html = render(cs);
    const line = html.indexOf("CUT LINE");
    expect(line).toBeGreaterThan(-1);
    const power = html.indexOf("Seamus Power");
    expect(html.slice(power, power + 600)).toContain(">50%<");
    expect(power).toBeLessThan(line);
  });
});
