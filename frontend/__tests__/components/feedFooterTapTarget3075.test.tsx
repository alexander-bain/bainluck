// #3075 — A FEED CARD'S PRE-GAME CONTEXT MUST NOT BE LAID OUT ON TOP OF THE THUMBS.
//
// ux/1072 found it mystery-shopping `/sports` at 390×844 on 2026-09-04: the last characters
// of `Opened 60/40` painted UNDERNEATH the feedback control. It is not a cosmetic nit — the
// overlapping element is a real `<button>`, so a tap aimed at the pre-game context fires a
// DOWNVOTE, and a downvote is a personalization signal. The card silently mistrains the feed
// for the reader who tapped the number they were reading.
//
// ## What the production measurement actually said (discover/049, 2026-09-12, 390px)
//
// The fix shape the issue suggested was already in the tree — the footer's left group is
// `min-w-0 flex-1`, the reason takes `truncate`, `Opened X/Y` is `flex-shrink-0` — and the
// overlap happened anyway, on LIVE cards, with `truncate` ON. Per-child geometry of one
// 290px group, the two reason branches side by side:
//
//   plain  <p class="… truncate">   shrank to 206.3px   box right 231.3   ✅ clipped
//   styled <span class="inline-flex …">  held at 285.4px   box right 310.4
//     └─ `Opened 76/24` (flex-shrink-0) then laid out 318.5 → 393.3, thumbs begin at 323
//        ⇒ 20px of the text inside BOTH buttons' hit rectangles.
//
// A flex item's `min-width: auto` floors it at min-content. The plain branch escapes that
// floor because `truncate` gives it `overflow:hidden`, which resolves the automatic minimum
// to 0. The styled badge has visible overflow, so the floor applied, the badge never yielded,
// and its inner `truncate` span could never bite. One missing `min-w-0`.
//
// ## Why this file asserts CLASSES, which it would not normally do
//
// The defect is entirely a layout one and jsdom has no layout engine, so there is no honest
// way to re-measure the overlap here — the real proof is the bounding-box probe against a
// built page, quoted in the PR. What CI can hold is the class contract that the measurement
// proved load-bearing: `min-w-0` on the badge, `truncate` on the span inside it, and
// `flex-shrink-0` on the two siblings that must NOT yield. Remove any one and the overlap
// returns. Arm 5 is the vacuity control — without it every class assertion here would pass
// just as happily against a `<p>`, which is the branch that already worked.
//
// Both directions per gotcha #43: the styled branch gains the floor escape AND the plain
// branch is asserted unchanged AND the finished card is asserted NOT to gain it.
//
// ## 2026-09-12, #5749 — the styled specimen changed, and the measurement above did not
//
// The production row measured here reached the styled branch for the WRONG REASON: `reasonStyle`
// matched "wild" inside "Kentucky Wildcats", so the badge was the ⚡ "something wild is happening"
// pill on a sentence that says the favourite is ahead. #5749 pinned each keyword to the phrase its
// template emits, and that row now correctly takes the plain `<p>` branch — the same branch arm 3
// already asserted for its sibling "Oklahoma State Cowboys leading after starting at 8%".
//
// So the pixel record above stands unedited: it is what was measured, on the row that was measured,
// on the code of that day. What it proved — that the styled branch holds at min-content while a
// `flex-shrink-0` sibling is laid out over the thumbs — is a property of the BRANCH, not of that
// sentence. The styled arms therefore move to a reason that reaches the branch on its own merits
// (`{team} odds shifted {dir} {pts} today in {market}`, a real `feed_reasons.py` template) and is
// 61 characters — LONGER than the 47-character row that produced the 20px overlap, so the geometry
// this file stands in for is stressed harder, not less. Nothing was relaxed to make it pass.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FeedCard from "@/components/FeedCard";
import type { FeedEventData, FeedItem } from "@/lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

// The production specimen, verbatim: the row that measured 20px into both buttons. It reached
// the STYLED branch because `reasonStyle` matched "wild" inside "Wildcats" — the #5749 defect.
// Kept, because arm 3 is the place that proves the row is now classified honestly.
const MEASURED_ROW_REASON = "Kentucky Wildcats leading after starting at 24%";

// What the styled arms use since #5749: a real `feed_reasons.py` movement template, which
// reaches the ↕ branch on the words the template itself emits and cannot be reclassified by
// renaming the team. 61 characters vs the measured row's 47.
const SPECIMEN_REASON = "Kentucky Wildcats odds shifted up 5 points today in moneyline";

function makeData(over: Partial<FeedEventData> = {}): FeedEventData {
  return {
    id: 15310999,
    external_id: "evt-15310999",
    sport: "americanfootball_ncaaf",
    sport_name: "NCAAF",
    home_team: "Kentucky Wildcats",
    away_team: "Alabama Crimson Tide",
    commence_time: "2026-09-12T19:30:00.000Z",
    status: "live",
    home_score: 14,
    away_score: 10,
    opening_odds: { away_probability: 0.76, home_probability: 0.24 },
    ...over,
  } as unknown as FeedEventData;
}

function render(data: FeedEventData, reason: string): string {
  const item = {
    type: "event",
    score: 50,
    reason,
    headline: "",
    data,
  } as unknown as FeedItem;
  return renderToStaticMarkup(<FeedCard item={item} />);
}

/** The styled reason pill, or null when this reason took the plain-text branch. */
function badgeSpan(html: string): string | null {
  const m = /<span class="(inline-flex[^"]*)"/.exec(html);
  return m ? m[1] : null;
}

/** The `<p>` the unstyled branch renders, or null. */
function plainParagraph(html: string): string | null {
  const m = /<p class="(text-xs text-text-secondary[^"]*)"/.exec(html);
  return m ? m[1] : null;
}

describe("#3075 — the footer's context text stays out of the thumb buttons", () => {
  // ARM 5 FIRST, because arms 1-4 are worthless if it fails: prove the fixture really
  // reaches the styled branch. A reason that takes the `<p>` branch would satisfy "no
  // overflow" for a reason that has nothing to do with the fix.
  it("vacuity control: the specimen reason reaches the STYLED badge branch, not the <p>", () => {
    const html = render(makeData(), SPECIMEN_REASON);
    expect(badgeSpan(html)).not.toBeNull();
    expect(plainParagraph(html)).toBeNull();
    // And the row really does carry the sibling that was displaced.
    expect(html).toContain('data-testid="feed-card-opened"');
  });

  it("arm 1: on a live card the badge can shrink, and the text inside it can ellipsize", () => {
    const html = render(makeData(), SPECIMEN_REASON);
    const badge = badgeSpan(html);
    expect(badge).toContain("min-w-0");
    // The floor escape is worth nothing unless the inner span truncates — the two are one
    // mechanism, and asserting only the outer class would pass on a badge that overflows
    // its own box instead of its parent's.
    expect(html).toMatch(/<span class="[^"]*\btruncate\b[^"]*">Kentucky Wildcats/);
  });

  it("arm 2: the siblings that must not yield keep flex-shrink-0", () => {
    const html = render(makeData(), SPECIMEN_REASON);
    // `Opened X/Y` is the text that was displaced onto the buttons; it stays non-shrinking
    // on purpose — the reason is what should give way, and now can.
    expect(html).toMatch(/<span class="text-\[11px\] text-text-muted flex-shrink-0"[^>]*data-testid="feed-card-opened"/);
    // The icon must not be the thing that squashes when the badge finally shrinks.
    expect(html).toMatch(/<span class="text-\[10px\] flex-shrink-0">/);
  });

  it("arm 3: the plain-text branch is untouched — it already shrank and clipped correctly", () => {
    // "Oklahoma State Cowboys leading after starting at 8%" measured box right 231.3 in the
    // same 290px group and never reached the buttons. It must not acquire a badge here.
    const html = render(makeData(), "Oklahoma State Cowboys leading after starting at 8%");
    expect(badgeSpan(html)).toBeNull();
    expect(plainParagraph(html)).toContain("truncate");

    // #5749 — and so does the row that was actually measured. Before #5749 these two sentences,
    // the same template with a different team in it, took different branches: the Wildcats one
    // was styled and could not shrink, the Cowboys one was plain and clipped. The team name was
    // the whole difference. This is the assertion that says the layout hazard the file guards is
    // no longer reachable by being called the Wildcats.
    const measured = render(makeData(), MEASURED_ROW_REASON);
    expect(badgeSpan(measured)).toBeNull();
    expect(plainParagraph(measured)).toContain("truncate");
  });

  it("arm 4: a FINISHED card does NOT become shrinkable, because it may not abbreviate", () => {
    // The call site passes `truncate={!isFinished}`. `min-w-0` lets the box shrink below its
    // content, which is only safe when the content may ellipsize — granting it here would
    // shrink the box while the un-truncated text kept painting past it, reproducing #3075
    // from the other side. This arm is what makes the gate deliberate rather than incidental.
    const html = render(
      makeData({ status: "completed", home_score: 31, away_score: 24 } as Partial<FeedEventData>),
      SPECIMEN_REASON,
    );
    const badge = badgeSpan(html);
    expect(badge).not.toBeNull();
    expect(badge).not.toContain("min-w-0");
    expect(html).not.toMatch(/<span class="[^"]*\btruncate\b[^"]*">Kentucky Wildcats/);
  });
});
