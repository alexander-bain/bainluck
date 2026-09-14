/**
 * #6079 — A PASTED MARKET LINK STOPS CROWNING A ROW NOBODY GRADED.
 *
 * Paying #6061's after-check on the same surface. Check 8 is "a pasted link
 * unfurls as the thing it points at", and on a resolved market with no graded
 * outcome the preview made two claims at once — the picture withholding the
 * verdict the words had already announced.
 *
 * Measured on production 2026-09-14 05:36Z, `/futures/61000391`:
 *
 *   og:title        "No won - Overwatch: Sweden vs France - Game 4 Winner"   ❌
 *   og:description  "No won (Overwatch: Sweden vs France - Game 4 Winner)."  ❌
 *   og:image        64px "No" beside a GREY "RESOLVED" pill                  ✅
 *
 * The row is `is_winner = false` at a frozen 0.91, and `leaderLabel` turns a bare
 * binary into a sentence subject, so the reader's sentence is "No won". The same
 * query returns the class rather than a one-off — `/futures/60982498` served
 * "Cam Skattebo won - Dallas vs New York G: Most Rushing Yards" the same minute,
 * a named player credited with a result no source graded.
 *
 * ═══ WHY THE PICTURE WAS RIGHT AND THE WORDS WERE WRONG ═══
 *
 * Three surfaces describe this state. `FuturesHero` gates its chip on
 * `resolvedWon={resolvedWinner?.is_winner === true}` and `futuresUnfurlCopy`
 * gates `settledWon` the same way (#6032). `layout.tsx` alone called
 * `pickHeroOutcome` and read the result as a verdict — but that helper answers
 * "which row does this surface feature", and its documented fallback when
 * nothing is graded is the PRICE LEADER. Subject and verdict are two questions;
 * `gradedWinner` is now the only place the second one is answered.
 *
 * ═══ WHY THE NARROW FIX WOULD HAVE BEEN WORSE THAN THE DEFECT ═══
 *
 * Gating the word "won" and stopping there drops this market into the branches
 * below it, and both of those publish the frozen last-traded prices:
 *
 *   title        "No won - … Game 4 Winner"  ->  "No 91% - … Game 4 Winner"
 *   description  "No won (…)."               ->  "No 91%, Yes 9%."
 *
 * A live shape on a closed market, which is the exact percentage #883 L2-55
 * keeps out of settled titles and the exact claim the card refuses to draw (no
 * 96px numeral and no bar, once `isResolved`). So `resolved` is terminal in both
 * helpers, and the assertions below pin the absence of the PRICE as hard as the
 * absence of the word.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * "Delete the word 'won'" satisfies every negative assertion in this file. The
 * graded controls are what kills it: a market WITH a winner must still say "won"
 * in the title and the description and still draw the green WON pill, and the
 * winner it names must be the GRADED row rather than the one frozen highest.
 * The live control holds the board sentence and its percentages in place.
 */

import React from "react";

const mockImageResponseCalls: React.ReactElement[] = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import { renderToStaticMarkup } from "react-dom/server";
import { generateMetadata as futuresMetadata } from "@/app/futures/[id]/layout";
import FuturesOgImage from "@/app/futures/[id]/opengraph-image";

/* ────────────────────────────── the harness ────────────────────────────── */

const ID = "61000391";

function respondWith(body: unknown) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
  }) as unknown as typeof fetch;
}

/** The Overwatch specimen, shaped as `/api/futures/{id}` serves it. */
function overwatch(overrides: Record<string, unknown> = {}) {
  return {
    id: Number(ID),
    name: "Overwatch: Sweden vs France - Game 4 Winner",
    status: "resolved",
    outcome_count: 2,
    outcomes: [
      { name: "No", probability: 0.91, is_winner: false },
      { name: "Yes", probability: 0.09, is_winner: false },
    ],
    ...overrides,
  };
}

async function meta(market: unknown) {
  respondWith(market);
  const m = await futuresMetadata({ params: Promise.resolve({ id: ID }) });
  return {
    title: String(m.title ?? ""),
    description: String(m.description ?? ""),
    ogTitle: String(m.openGraph?.title ?? ""),
    twitterTitle: String(m.twitter?.title ?? ""),
  };
}

/**
 * What the card DRAWS, rendered — the card clamps its own strings, so the text
 * reaching the canvas is not the text handed in. `params` is a PLAIN OBJECT
 * here, not a promise: the image route unwraps it directly, and a promise makes
 * `params.id` undefined, which parses to NaN and silently draws the DEAD-LINK
 * card instead (a green harness testing the wrong branch).
 */
async function cardText(market: unknown): Promise<string> {
  respondWith(market);
  mockImageResponseCalls.length = 0;
  await FuturesOgImage({ params: { id: ID } });
  expect(mockImageResponseCalls).toHaveLength(1);
  return renderToStaticMarkup(mockImageResponseCalls[0]).replace(/<[^>]*>/g, " ");
}

beforeEach(() => {
  mockImageResponseCalls.length = 0;
});

/* ══════════ the defect — resolved, nothing graded, no verdict owed ══════════ */

describe("a resolved market with no graded outcome claims no winner", () => {
  it("does not say anyone won, in any of the three title slots", async () => {
    const m = await meta(overwatch());
    for (const slot of [m.title, m.ogTitle, m.twitterTitle]) {
      expect(slot).not.toMatch(/\bwon\b/i);
    }
    // Asserted on every slot because `og:`/`twitter:` are separate namespaces
    // that #5846 already caught disagreeing on this very route.
  });

  it("does not swap the verdict for the frozen price", async () => {
    // The narrow fix's output. Both the bare number and the board pair.
    const m = await meta(overwatch());
    expect(m.title).not.toMatch(/\d+%/);
    expect(m.description).not.toMatch(/\d+%/);
    expect(m.description).not.toContain("Yes 9%");
  });

  it("names the market and its state, and nothing else", async () => {
    const m = await meta(overwatch());
    expect(m.title).toBe("Overwatch: Sweden vs France - Game 4 Winner");
    expect(m.description).toContain("Overwatch: Sweden vs France - Game 4 Winner");
    expect(m.description).toContain("resolved");
  });

  it("agrees with its own picture, which already withheld the verdict", async () => {
    const drawn = await cardText(overwatch());
    const m = await meta(overwatch());
    // The picture was never wrong here; this pins the two together so a later
    // change cannot reopen the gap from either side.
    expect(drawn).toContain("RESOLVED");
    expect(drawn).not.toContain("WON");
    expect(m.title).not.toMatch(/\bwon\b/i);
  });

  it("holds for a named outcome, not just a bare binary", async () => {
    // `/futures/60982498` — "Cam Skattebo won - Dallas vs New York G: Most
    // Rushing Yards". A real person credited with an ungraded result reads as
    // fact in a way "No won" does not, so the fix may not depend on the label
    // being generic.
    const m = await meta(
      overwatch({
        name: "Dallas vs New York G: Most Rushing Yards",
        outcomes: [
          { name: "Cam Skattebo", probability: 0.64, is_winner: false },
          { name: "Javonte Williams", probability: 0.36, is_winner: false },
        ],
      }),
    );
    expect(m.title).not.toContain("Cam Skattebo won");
    expect(m.title).not.toMatch(/\bwon\b/i);
  });

  it("treats a missing is_winner field the same as a false one", async () => {
    // Kalshi rows arrive ungraded rather than graded-false; absence must not be
    // read as a grade by omission.
    const m = await meta(
      overwatch({
        outcomes: [{ name: "No", probability: 0.91 }, { name: "Yes", probability: 0.09 }],
      }),
    );
    expect(m.title).not.toMatch(/\bwon\b/i);
    expect(m.title).not.toMatch(/\d+%/);
  });
});

/* ═══════════ the other direction — a graded market still says so ═══════════ */

describe("a graded market still announces its winner", () => {
  const graded = () =>
    overwatch({
      outcomes: [
        { name: "No", probability: 0.91, is_winner: false },
        { name: "Yes", probability: 0.09, is_winner: true },
      ],
    });

  it("says '<winner> won' in the title, with no percentage", async () => {
    const m = await meta(graded());
    expect(m.title).toBe("Yes won - Overwatch: Sweden vs France - Game 4 Winner");
    expect(m.title).not.toMatch(/\d+%/);
  });

  it("says it in the description too, with the name parenthesised", async () => {
    const m = await meta(graded());
    expect(m.description).toContain("Yes won (Overwatch: Sweden vs France - Game 4 Winner)");
    expect(m.description).not.toMatch(/\d+%/);
    expect(m.description).not.toContain("has resolved");
  });

  it("crowns the GRADED row even when another is frozen higher", async () => {
    // UX-P232: settlement freezes prices, so the winner is routinely not the top
    // of the board. Here `No` is frozen at 91% and `Yes` is the graded winner —
    // reading the leader would name the loser, which is the failure #6032 found
    // on the picture and this file inherits for the words.
    const m = await meta(graded());
    expect(m.title.startsWith("Yes won")).toBe(true);
    expect(m.title).not.toContain("No won");
  });

  it("still draws the green WON pill on the picture", async () => {
    const drawn = await cardText(graded());
    expect(drawn).toContain("WON");
    expect(drawn).toContain("Yes");
  });
});

/* ═══════════════ the live control — the board is untouched ═══════════════ */

describe("a live market is unaffected", () => {
  const live = () =>
    overwatch({
      status: "open",
      outcomes: [
        { name: "Above 1 inch", probability: 0.52 },
        { name: "Above 2 inches", probability: 0.21 },
      ],
    });

  it("keeps the leader-and-price title", async () => {
    const m = await meta(live());
    expect(m.title).toBe("Above 1 inch 52% - Overwatch: Sweden vs France - Game 4 Winner");
  });

  it("keeps the board sentence and its percentages", async () => {
    const m = await meta(live());
    expect(m.description).toContain("Above 1 inch 52%");
    expect(m.description).toContain("Above 2 inches 21%");
    expect(m.description).not.toContain("has resolved");
  });

  it("ignores a stray is_winner on an open market", async () => {
    // `status` is the gate. A live row carrying the flag must not be crowned,
    // which is the mirror of the settled rule the page already reads this way.
    const m = await meta(
      overwatch({
        status: "open",
        outcomes: [{ name: "Above 1 inch", probability: 0.52, is_winner: true }],
      }),
    );
    expect(m.title).not.toMatch(/\bwon\b/i);
    expect(m.title).toContain("52%");
  });
});
