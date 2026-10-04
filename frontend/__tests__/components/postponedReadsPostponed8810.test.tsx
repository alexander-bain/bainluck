// #8810 — A POSTPONED MATCH READS "No result reported" OVER A BIG 22%.
//
// Measured on production 2026-09-27 ~02:20Z (lane1's after-check for #8943) and
// again by ux at 390px: `/events/15315470`, Crawley Town v Barnet, League Two.
// The row is `suspended` with ESPN anchor 401881358, and ESPN reads it
// `STATUS_POSTPONED`. The hero said:
//
//   pill              "No result reported · last score 0-0"
//   between crests    22%  (the last pre-kickoff reading, 48px, team red)
//   under the crests  0    0
//
// Three claims about a match nobody played: that its sources went dark, that it
// has a live-shaped price, and that play reached 0-0. The authority told us the
// one true thing — Postponed — in the word ESPN sync writes to `period`, served
// as `espn.period`. Specimen with that word on production today: 15314000
// (New York Red Bulls v St. Louis City SC, `period='Postponed'`, #8960's row).
//
// This file drives the REAL helpers and the REAL component; the page guard at
// the bottom pins that the page feeds them from the payload rather than from a
// boolean of its own.

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import {
  SUSPENDED_LABEL,
  authorityStoppageDescription,
  scoresShowPlay,
  suspendedSummary,
} from "@/lib/eventState";
import { authorityStoppageLabel } from "@/lib/gameTimeLabel";

/** Every surface's call shape: the raw period resolved through the one home. */
const summary = (
  away: number | null,
  home: number | null,
  order: "home-away" | "away-home",
  period?: string | null,
) => suspendedSummary(away, home, order, authorityStoppageLabel(period));
import { buildEventShareCopy } from "@/lib/eventShareMeta";

describe("authorityStoppageLabel — the authority's word, allowlisted exactly", () => {
  it("names a postponed or canceled match", () => {
    expect(authorityStoppageLabel("Postponed")).toBe("Postponed");
    expect(authorityStoppageLabel(" postponed ")).toBe("Postponed");
    expect(authorityStoppageLabel("Canceled")).toBe("Canceled");
    expect(authorityStoppageLabel("Cancelled")).toBe("Canceled");
  });

  it("refuses every live period a dark row can be left holding", () => {
    // 15314000's sibling census: of 5,392 suspended rows in 30 days, one held
    // `End 9th`. A dark row keeps its old sentence, never a stoppage word.
    for (const p of ["End 9th", "2nd Half", "Halftime", "FT", "Postponed 0'", "", null, undefined]) {
      expect(authorityStoppageLabel(p as string | null | undefined)).toBeNull();
    }
  });

  it("describes the stoppage instead of claiming no source reported", () => {
    expect(authorityStoppageDescription(authorityStoppageLabel("Postponed"))).toBe(
      "This match has been postponed.",
    );
    expect(authorityStoppageDescription(authorityStoppageLabel("End 9th"))).toBeNull();
  });
});

describe("suspendedSummary with the authority's period", () => {
  it("THE SPECIMEN: Postponed, and ESPN's 0-0 filler is not a last score", () => {
    expect(summary(0, 0, "home-away", "Postponed")).toBe("Postponed");
    expect(summary(null, null, "away-home", "Postponed")).toBe("Postponed");
  });

  it("a match stopped WITH a score keeps it, in the surface's order", () => {
    expect(summary(1, 0, "away-home", "Postponed")).toBe(
      "Postponed · last score 1-0",
    );
    expect(summary(1, 0, "home-away", "Postponed")).toBe(
      "Postponed · last score 0-1",
    );
  });

  it("CONTROL: no period, or a non-stoppage period, is byte-identical to before", () => {
    expect(summary(0, 0, "home-away")).toBe(`${SUSPENDED_LABEL} · last score 0-0`);
    expect(summary(0, 0, "home-away", null)).toBe(`${SUSPENDED_LABEL} · last score 0-0`);
    expect(summary(2, 3, "away-home", "End 9th")).toBe(
      `${SUSPENDED_LABEL} · last score 2-3`,
    );
  });

  it("scoresShowPlay is the scores-only evidence", () => {
    expect(scoresShowPlay(0, 0)).toBe(false);
    expect(scoresShowPlay(null, null)).toBe(false);
    expect(scoresShowPlay(0, 1)).toBe(true);
  });
});

describe("the hero slot prints no price on a stopped match", () => {
  const props = {
    homeProb: 0.2248,
    awayProb: null,
    homePct: 22,
    awayPct: null,
    awayWithheld: true,
    homeColor: "#C8142F",
    awayColor: "#fe7a00",
    probSourceLabel: "Sportsbooks",
    started: true,
  };

  it("THE SPECIMEN: no 22, no %, container kept for the probes", () => {
    const html = renderToStaticMarkup(<EventHeroProbabilityPair {...props} stopped />);
    expect(html).toContain('data-testid="event-hero-probability"');
    expect(html).toContain('data-stopped="true"');
    expect(html).toContain('data-probability=""');
    expect(html).not.toContain(">22<");
    expect(html).not.toContain("%");
    expect(html).not.toContain("No price");
  });

  it("CONTROL: the same reading without `stopped` still prints 22%", () => {
    const html = renderToStaticMarkup(<EventHeroProbabilityPair {...props} />);
    expect(html).toContain(">22<");
    expect(html).not.toContain("data-stopped");
  });
});

describe("the link preview says the same sentence as the page", () => {
  const base = {
    home_team: "Crawley Town",
    away_team: "Barnet",
    home_score: 0,
    away_score: 0,
    status: "suspended",
    commence_time: "2026-09-26T11:30:00+00:00",
  };

  it("THE SPECIMEN: Postponed, with the postponed sentence", () => {
    const copy = buildEventShareCopy(
      { ...base, espn: { period: "Postponed" } },
      null,
      Date.parse("2026-09-27T02:20:00Z"),
    );
    expect(copy.title).toContain("Postponed");
    expect(copy.title).not.toContain("No result reported");
    expect(copy.description).toContain("This match has been postponed.");
    expect(copy.description).not.toContain("no source has reported");
  });

  it("CONTROL: no period keeps the old sentence", () => {
    const copy = buildEventShareCopy(base, null, Date.parse("2026-09-27T02:20:00Z"));
    expect(copy.title).toContain("No result reported");
  });
});

describe("the event page feeds the authority's word from the payload", () => {
  const src = fs.readFileSync(
    path.join(__dirname, "../../app/events/[id]/page.tsx"),
    "utf8",
  );

  it("derives the label beside isSuspended, outranked by the venue's grade", () => {
    expect(src).toMatch(
      /const stoppageLabel =\s*isSuspended && !venueSettledSentence\s*\?\s*authorityStoppageLabel\(event\?\.espn\?\.period\)/,
    );
  });

  it("the pill, the hero slot, both scores and the score chart all read it", () => {
    expect(src).toMatch(/"home-away",[\s\S]{0,200}stoppageLabel,\s*\)/);
    expect(src).toContain("authorityStoppageDescription(stoppageLabel)");
    expect(src).toContain("stopped={stoppageLabel !== null}");
    // Both hero scores, the score chart, and (#10239) the final score handed to the projected final
    // points module: a postponed match's 0–0 filler is never passed in as a final.
    expect(src.match(/!heroScoreIsStoppageFiller/g)?.length).toBe(4);
  });
});

describe("every surface that prints the suspended summary passes the authority's word", () => {
  // One card family (notice 35): the card a reader taps and the page it opens
  // must say the same word. A site calling `suspendedSummary` without the
  // stoppage label would print "No result reported" over a Postponed page.
  const FRONTEND = path.resolve(__dirname, "../..");
  const SITES = [
    "components/EventCard.tsx",
    "components/FeedCard.tsx",
    "components/discover/EventCard.tsx",
    "app/events/[id]/opengraph-image.tsx",
    "lib/eventShareMeta.ts",
    "app/events/[id]/page.tsx",
  ];
  it.each(SITES)("%s", (rel) => {
    const src = fs.readFileSync(path.join(FRONTEND, rel), "utf8");
    const calls = src.match(/suspendedSummary\([^;]*?\)\s*\)?/g) ?? [];
    // strip comments' mentions: only real call expressions with arguments
    const real = calls.filter((c) => /suspendedSummary\(\s*[a-z]/.test(c));
    expect(real.length).toBeGreaterThan(0);
    for (const c of real) {
      expect(c).toMatch(/authorityStoppageLabel\([a-z?.]*espn\?\.period\)|stoppage(Label)?\s*,?\s*\)/);
    }
  });
});
