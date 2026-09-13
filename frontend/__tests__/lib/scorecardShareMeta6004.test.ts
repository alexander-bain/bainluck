/**
 * A SHARED PREDICTION SCORECARD COUNTS IN ENGLISH, AND REFUSES TO INVENT A
 * NUMBER FOR A LINK THAT IS NOT ONE (#6004).
 *
 * ═══ THE TWO DEFECTS, BOTH READ OFF PRODUCTION 2026-09-13 22:0xZ ═══
 *
 * 1. `/discover/stats` guards only `stats.total === 0`, so the reader with
 *    exactly ONE settled prediction is past it — and is, by construction, the
 *    newest sharer we have. Both sentence sites said "${total} predictions"
 *    unconditionally, so what they posted and what unfurled beside it was:
 *
 *      og:description  "100% accurate across 1 predictions on Bain Luck!"
 *
 * 2. The page body sanitized (`parseInt(...) || 0`); `generateMetadata` did
 *    not. One URL therefore told two stories:
 *
 *      ?accuracy=999999&total=abc&correct=-5
 *      og:description  "999999% accurate across abc predictions on Bain Luck!"
 *      the page         999999% over 0 predictions
 *
 *    and a bare `/discover/scorecard` unfurled "0% accurate across 0
 *    predictions on Bain Luck!".
 *
 * ═══ WHY THE SUITE ASSERTS BOTH DIRECTIONS ═══
 *
 * A guard that only asserts "no invented number" is passed by a sanitizer that
 * refuses EVERYTHING — which would delete the feature and print generic copy
 * over every real scorecard a reader ever shares. So every refusal arm is paired
 * with the positive arm that a well-formed scorecard still prints its own real
 * numbers, and the exact URL `handleShare` builds is driven through the reader
 * to prove the product's own share survives the validator.
 *
 * Likewise "1 prediction" alone is passed by dropping the plural everywhere, so
 * the 2-and-up arm is asserted beside it.
 */

import { generateMetadata as scorecardMetadata } from "@/app/discover/scorecard/page";
import {
  buildScorecardShareSentence,
  readScorecardStats,
  type ScorecardStats,
} from "@/lib/share";

type Query = Parameters<typeof readScorecardStats>[0];

/** The route takes a promise of the query, the way Next hands it over. */
const metaFor = (query: Query) => scorecardMetadata({ searchParams: Promise.resolve(query) });

/** A scorecard that is real in every field, to vary one thing at a time from. */
const VALID: Required<Query> = {
  accuracy: "61",
  total: "23",
  correct: "14",
  streak: "3",
  best: "7",
};

describe("readScorecardStats", () => {
  it("reads a well-formed scorecard", () => {
    expect(readScorecardStats(VALID)).toEqual<ScorecardStats>({
      accuracy: 61,
      total: 23,
      correct: 14,
      streak: 3,
      best: 7,
    });
  });

  it("reads the URL our own Share button builds", () => {
    // `app/discover/stats/page.tsx` handleShare, verbatim in shape: five params,
    // accuracy already rounded to a whole percent. If the validator ever refuses
    // this, every real share unfurls generic copy and the feature is gone.
    const stats = { accuracy: 0.6086, total: 23, correct: 14, current_streak: 3, best_streak: 7 };
    const accuracy = Math.round(stats.accuracy * 100);
    const shareParams = `accuracy=${accuracy}&total=${stats.total}&correct=${stats.correct}&streak=${stats.current_streak}&best=${stats.best_streak}`;
    const q = Object.fromEntries(new URLSearchParams(shareParams)) as Query;

    expect(readScorecardStats(q)).toEqual<ScorecardStats>({
      accuracy: 61,
      total: 23,
      correct: 14,
      streak: 3,
      best: 7,
    });
  });

  it.each([
    ["a bare link with no params at all", {}],
    ["a partial link", { accuracy: "61", total: "23" }],
    ["an accuracy above 100", { ...VALID, accuracy: "999999" }],
    ["a non-numeric total", { ...VALID, total: "abc" }],
    ["a negative count", { ...VALID, correct: "-5" }],
    ["a decimal", { ...VALID, accuracy: "61.4" }],
    ["a signed integer", { ...VALID, total: "+23" }],
    ["whitespace", { ...VALID, total: " 23" }],
    ["an empty string", { ...VALID, streak: "" }],
    ["zero predictions", { ...VALID, total: "0", correct: "0", streak: "0", best: "0" }],
    ["more correct than were made", { ...VALID, correct: "24" }],
    ["a streak longer than the record", { ...VALID, streak: "24" }],
  ])("refuses %s", (_label, query) => {
    expect(readScorecardStats(query as Query)).toBeNull();
  });
});

describe("buildScorecardShareSentence", () => {
  const sentenceFor = (total: number) =>
    buildScorecardShareSentence({ accuracy: 100, total, correct: total, streak: total, best: total });

  it("counts one prediction in the singular", () => {
    expect(sentenceFor(1)).toBe("100% accurate across 1 prediction on Bain Luck!");
  });

  it("still counts two and up in the plural", () => {
    expect(sentenceFor(2)).toBe("100% accurate across 2 predictions on Bain Luck!");
    expect(sentenceFor(23)).toBe("100% accurate across 23 predictions on Bain Luck!");
  });
});

describe("the /discover/scorecard unfurl", () => {
  it("prints the reader's own numbers when the link is a real scorecard", async () => {
    const meta = await metaFor(VALID);

    expect(meta.title).toBe("61% Prediction Accuracy | Bain Luck");
    expect(meta.openGraph?.description).toBe("61% accurate across 23 predictions on Bain Luck!");
    expect(meta.twitter?.description).toBe("61% accurate across 23 predictions on Bain Luck!");
  });

  it("says 1 prediction, not 1 predictions", async () => {
    const meta = await metaFor({ accuracy: "100", total: "1", correct: "1", streak: "1", best: "1" });

    expect(meta.openGraph?.description).toBe("100% accurate across 1 prediction on Bain Luck!");
    expect(meta.twitter?.description).toBe("100% accurate across 1 prediction on Bain Luck!");
  });

  it.each([
    ["the bare link", {} as Query],
    ["a mangled link", { accuracy: "999999", total: "abc", correct: "-5" } as Query],
  ])("describes %s in words, with no number in it", async (_label, query) => {
    const meta = await metaFor(query);
    const copy = [meta.title, meta.description, meta.openGraph?.description, meta.twitter?.description];

    for (const line of copy) {
      expect(typeof line).toBe("string");
      expect(line as string).not.toMatch(/\d/);
      expect(line as string).not.toMatch(/accurate across/);
    }
    expect(meta.title).toBe("Prediction Scorecard | Bain Luck");
  });

  it("keeps a mangled query out of the card image URL", async () => {
    const meta = await metaFor({ accuracy: "999999", total: "abc", correct: "-5" });
    const images = meta.openGraph?.images as Array<{ url: string }> | undefined;
    const url = images?.[0]?.url ?? "";

    expect(url).toContain("/api/og/stats");
    expect(url).not.toContain("999999");
    expect(url).not.toContain("abc");
    expect(url).not.toContain("-5");
  });

  it("still sends a real scorecard's numbers to the card image", async () => {
    const meta = await metaFor(VALID);
    const images = meta.openGraph?.images as Array<{ url: string }> | undefined;

    expect(images?.[0]?.url).toContain("accuracy=61&total=23&correct=14&streak=3&best=7");
  });
});
