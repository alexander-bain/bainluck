/**
 * #7004 — THE DAILY CHALLENGE LABELLED ITS SYNTHETIC NUMBER "Market line".
 *
 * Production, 2026-09-18 18:05Z, `bainluck.com/daily` at 390px signed out:
 *
 *     Market line
 *     Espanyol to win
 *     Is the probability higher or lower than this?
 *     34%
 *     [ ↑ Higher than 34% ]  [ ↓ Lower than 34% ]
 *     Open market details
 *
 * Espanyol's real probability was **54%**. The reader taps the card's own
 * "Open market details" — the control directly beneath the number — lands on
 * `/events/15306048`, and meets 54% in 48pt over a two-day chart that never
 * dips below 50%. We printed a false fact about a market and handed the reader
 * the link that disproves it.
 *
 * ═══ WHY THIS IS NOT A ROUNDING ARTIFACT OR A STALE READ ═══
 *
 * The number is `deterministicThreshold`, which offsets the real probability by
 * a seeded 0.12–0.25 and re-offsets the other way if clamping brings it back
 * within 10 points. latency/567 swept its whole admitted domain — actual 5..95
 * pct × 4,000 question ids × 3 date keys, 1,092,000 inputs — and measured
 * min 11 / max 25 points of gap, with **0 inputs** landing within 10 points.
 * The shared helper `lib/play/threshold.ts` documents the same contract in
 * words: "guaranteed ≥10% away". The codebase promised this is never the
 * market's line while the page called it exactly that.
 *
 * ═══ WHAT THIS FILE CAN AND CANNOT ASSERT ═══
 *
 * 🪤 The fix is an ABSENCE, and an absence is the easiest thing in the world to
 * assert vacuously. `not.toContain("Market line")` passes on a component that
 * renders nothing at all, and it passes on a component that says "Market
 * price" instead. So both holes are closed explicitly:
 *
 *   1. every assertion of absence is paired with an assertion that the box
 *      still renders its subject, its question and its number (the "deleted the
 *      box" mutant), and
 *   2. absence is asserted against a FAMILY of attributions — market, odds,
 *      sportsbook, consensus, "traders say" — not against the one string that
 *      happened to be there (the "reworded it" mutant).
 *
 * 🔴 The box had to MOVE to be testable at all, and that is worth recording.
 * As a local function inside `app/daily/page.tsx` nothing could reach it: the
 * page loads its questions in a `useEffect`, which server rendering never runs,
 * and this suite's environment is `node` (no jsdom, no localStorage). Rendering
 * `DailyPage` yields the loading state forever. A guard that cannot see the
 * thing it guards is the reason #7004 lived on a front-door surface unnoticed.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DailyThresholdBox } from "@/components/daily/DailyThresholdBox";

/** The live specimen from the issue. */
const SUBJECT = "Espanyol to win";
const THRESHOLD = 34;

function render(subject = SUBJECT, threshold = THRESHOLD): string {
  return renderToStaticMarkup(
    <DailyThresholdBox subject={subject} threshold={threshold} />,
  );
}

/** Markup with tags stripped — what a reader actually reads. */
function visibleText(html: string): string {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

describe("the Daily Challenge's guess target", () => {
  it("still says everything the reader needs", () => {
    // 🔴 First, because every absence below is ALSO satisfied by a box that
    // renders nothing. If this fails, nothing else in this file means anything.
    const text = visibleText(render());
    expect(text).toContain(SUBJECT);
    expect(text).toContain("Is the probability higher or lower than this?");
    expect(text).toContain("34%");
  });

  it("does not call the number a market line", () => {
    expect(visibleText(render())).not.toContain("Market line");
  });

  it("attributes the number to NOTHING — not to a market under any name", () => {
    // The reworded-label mutant. "Market price", "Odds", "What traders say" and
    // "Sportsbook consensus" are all the same false claim wearing other words,
    // and a test keyed on the one string that shipped would miss every one.
    const text = visibleText(render());
    for (const attribution of [
      /market/i,
      /\bodds\b/i,
      /sportsbook/i,
      /bookmaker/i, // notice 33, while we are here
      /consensus/i,
      /traders?\s+say/i,
      /\bline\b/i, // betting vocabulary; "Probability, not betting"
    ]) {
      expect(text).not.toMatch(attribution);
    }
  });

  it("makes no claim of any kind about where the number came from", () => {
    // The strongest form, and the one that survives a mutant nobody predicted:
    // the ONLY prose in this box is the question. Anything else is a claim.
    const text = visibleText(render());
    const withoutKnownContent = text
      .replace(SUBJECT, "")
      .replace("Is the probability higher or lower than this?", "")
      .replace("34%", "")
      .trim();
    expect(withoutKnownContent).toBe("");
  });

  it("renders whatever threshold it is handed — the number is not hardcoded", () => {
    // Keeps the assertions above honest: they must be reading a real render,
    // not a fixed string that happens to contain "34%".
    expect(visibleText(render("Arsenal to win", 71))).toContain("71%");
    expect(visibleText(render("Arsenal to win", 71))).toContain("Arsenal to win");
    expect(visibleText(render("Arsenal to win", 71))).not.toContain("34%");
  });
});
