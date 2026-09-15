// #6381 — THE LINK PREVIEW STOPS DENYING A RESULT THE PAGE IT OPENS NOW NAMES.
//
// The page half of this ship (`venueSettledHero6381.test.tsx`) makes
// `/events/15310639` read "Settled · Draw 0-0" instead of "No result reported".
// The preview is drawn from the SAME payload by two other surfaces — the picture
// (`opengraph-image.tsx`) and the copy (`eventShareMeta.buildEventShareCopy`) —
// and #6113's whole finding was those halves answering one question apart:
//
//     og:image  "Live now"                page  "No result reported"
//
// Fixing the page alone would have rebuilt that split with the terms swapped, so
// the two share surfaces read the same two keys through the same function.
//
// ── THE CONTROL THAT MATTERS MOST ────────────────────────────────────────────
//
// Both keys are ABSENT on every payload until the producer (PR #6410) is live,
// and absent on most rows forever — a Final, a live game with a score, anything
// the page has a better answer for. So "absent changes nothing" is not a tail
// case: it is the whole site, and it is asserted on both halves.

import React from "react";
import { buildEventShareCopy, hasNoReportedResultForShare } from "@/lib/eventShareMeta";
import { VENUE_SETTLED_DESCRIPTION, SUSPENDED_DESCRIPTION } from "@/lib/eventState";

/** The element `ImageResponse` was constructed with. `mock`-prefixed for jest hoisting. */
const mockImageResponseCalls: React.ReactElement[] = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import OgImage from "@/app/events/[id]/opengraph-image";

/* ───────────────────────────── the specimens ───────────────────────────── */

/**
 * The Liverpool–Fulham row, trimmed to what these two surfaces read: a tier-1
 * fixture that sat `scheduled` three days past its own kickoff with both scores
 * null while its `Correct Score · Draw 0-0` market was graded `Won`.
 *
 * `opening_odds` is the pre-match reading the card draws once the forecast is
 * withheld — without it the picture has no numbers and the state assertions
 * below would be passing on an empty card.
 */
const LIVERPOOL_FULHAM = {
  id: 15310639,
  home_team: "Liverpool FC",
  away_team: "Fulham FC",
  status: "scheduled",
  sport: "soccer_epl",
  sport_name: "Premier League",
  home_score: null,
  away_score: null,
  completed_at: null,
  // An OFFSET, never a literal date: fixtures in four of the suites #6105
  // touched had rotted from future-dated into past-dated while still calling
  // themselves scheduled (gotcha #44).
  commence_time: new Date(Date.now() - 72 * 60 * 60 * 1000).toISOString(),
  hero_probability_source: "blend",
  hero_settled_result: null,
  current_odds: {
    home_probability: 0.62,
    away_probability: 0.38,
    home_rendered_percent: 62,
    away_rendered_percent: 38,
  },
  opening_odds: {
    home_probability: 0.62,
    away_probability: 0.38,
  },
};

const SETTLED_WITH_SCORE = {
  ...LIVERPOOL_FULHAM,
  venue_settled: true,
  venue_settled_result: "Draw 0-0",
};

/** The tennis shape: props graded, no score market ever quoted. */
const SETTLED_WITHOUT_SCORE = {
  ...LIVERPOOL_FULHAM,
  venue_settled: true,
  venue_settled_result: null,
};

/** We asked and the venue has graded nothing. */
const NOT_SETTLED = {
  ...LIVERPOOL_FULHAM,
  venue_settled: false,
  venue_settled_result: null,
};

/* ────────────────────────────── the harness ────────────────────────────── */

async function renderCard(body: unknown): Promise<React.ReactElement> {
  mockImageResponseCalls.length = 0;
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
  }) as unknown as typeof fetch;

  await OgImage({ params: { id: "15310639" } });

  if (mockImageResponseCalls.length !== 1) {
    throw new Error(
      `expected exactly 1 ImageResponse, captured ${mockImageResponseCalls.length}`,
    );
  }
  return mockImageResponseCalls[0];
}

/** The whole card as one string, for "this must appear NOWHERE" assertions. */
function allText(element: React.ReactElement): string {
  const found: string[] = [];
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (typeof node === "string" || typeof node === "number") {
      found.push(String(node));
      return;
    }
    if (!React.isValidElement(node)) return;
    walk((node.props as { children?: unknown })?.children);
  };
  walk(element);
  return found.join(" ");
}

/* ═══════════════════════════════ THE PICTURE ══════════════════════════════ */

describe("#6381 — the picture names the venue's grade", () => {
  it("draws the graded score instead of the denial", async () => {
    const text = allText(await renderCard(SETTLED_WITH_SCORE));

    expect(text).toContain("Settled · Draw 0-0");
    expect(text).not.toContain("No result reported");
  });

  it("draws the badge alone when no score graded, inventing none", async () => {
    const text = allText(await renderCard(SETTLED_WITHOUT_SCORE));

    expect(text).toContain("Settled");
    expect(text).not.toContain("No result reported");
    expect(text).not.toMatch(/Settled[^A-Za-z]*\d/);
  });

  it("CONTROL: a row the venue graded nothing on is untouched", async () => {
    const text = allText(await renderCard(NOT_SETTLED));

    expect(text).toContain("No result reported");
    expect(text).not.toContain("Settled");
  });

  it("CONTROL: absent keys are untouched — which is every payload today", async () => {
    const text = allText(await renderCard(LIVERPOOL_FULHAM));

    expect(text).toContain("No result reported");
    expect(text).not.toContain("Settled");
  });

  it("CONTROL: the card still draws its pre-match pair, so the state above is on a real card", async () => {
    // A withholding fix's failure mode is an empty picture, which would satisfy
    // every `not.toContain` here for the wrong reason.
    const text = allText(await renderCard(SETTLED_WITH_SCORE));

    expect(text).toContain("Liverpool FC");
    expect(text).toContain("Fulham FC");
    expect(text).toContain("38%");
    expect(text).toContain("62%");
  });
});

/* ════════════════════════════ THE TITLE AND COPY ══════════════════════════ */

describe("#6381 — the title and description say the same thing the picture does", () => {
  it("names the graded score and drops the no-source sentence", () => {
    const copy = buildEventShareCopy(SETTLED_WITH_SCORE);

    expect(copy.title).toBe("Fulham FC vs Liverpool FC: Settled · Draw 0-0");
    expect(copy.description).toContain(VENUE_SETTLED_DESCRIPTION);
    expect(copy.description).not.toContain(SUSPENDED_DESCRIPTION);
  });

  it("says Settled with no score when none graded", () => {
    const copy = buildEventShareCopy(SETTLED_WITHOUT_SCORE);

    expect(copy.title).toBe("Fulham FC vs Liverpool FC: Settled");
    expect(copy.description).toContain(VENUE_SETTLED_DESCRIPTION);
  });

  it("CONTROL: an ungraded row keeps the sentence and the description it had", () => {
    const copy = buildEventShareCopy(NOT_SETTLED);

    expect(copy.title).toBe("Fulham FC vs Liverpool FC: No result reported");
    expect(copy.description).toContain(SUSPENDED_DESCRIPTION);
    expect(copy.description).not.toContain(VENUE_SETTLED_DESCRIPTION);
  });

  it("CONTROL: absent keys keep the sentence they had", () => {
    expect(buildEventShareCopy(LIVERPOOL_FULHAM).title).toBe(
      "Fulham FC vs Liverpool FC: No result reported",
    );
  });

  it("keeps the row OUT of the settled classification", () => {
    // 🔴 `settled` gates the copy that leads with a trusted score
    // (`hero_probability_source === "settled"`, Q441). A graded market outcome
    // is not that measurement, and this ship changes the WORDS, not the
    // classification — flipping it here would reach branches these keys were
    // never verified against.
    expect(buildEventShareCopy(SETTLED_WITH_SCORE).settled).toBe(false);
  });

  it("is still the no-reported-result branch that fires, not some other one", () => {
    // The strawman kill: if `hasNoReportedResultForShare` stopped answering true
    // for this row, every assertion above would be passing on a branch this ship
    // never touched.
    expect(hasNoReportedResultForShare(SETTLED_WITH_SCORE)).toBe(true);
    expect(hasNoReportedResultForShare(NOT_SETTLED)).toBe(true);
  });
});
