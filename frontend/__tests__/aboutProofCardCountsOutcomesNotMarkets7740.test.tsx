/**
 * #7740 — `/about`'s proof card names the number it prints.
 *
 * THE SPECIMEN, photographed at 390px on production 2026-09-21 08:04Z:
 *
 *     And we grade ourselves in public: across 449K traded markets, our numbers
 *     land an average of 0.9 points from what actually happened.
 *
 * Both figures are CORRECT and #7564 settled them. The noun is not. `449K` is
 * `proofCohortFigures(...).outcomes` — 449,027 resolved OUTCOMES in the traded
 * cohort. Derived from the served payload alone: that cohort's `winners`
 * (187,068) and `sum_prob` (188,240.8) agree to 0.6%, two independent estimators
 * of the same quantity and the signature of one winner per market, so the cohort
 * covers about 187K markets. The card said 449K markets. 2.4x.
 *
 * `/calibration` prints the identical number three times and calls it "resolved
 * outcomes" / "traded outcomes" every time, so the two surfaces contradicted each
 * other about one number, and `story-content.ts` contradicted itself in place —
 * its own comment said "449,027 outcomes" one line above the word "markets".
 *
 * ── WHY BOTH STRINGS, AND WHY THAT IS THE WHOLE POINT ───────────────────────
 *
 * The sentence exists twice. `app/about/page.tsx` renders the measured version
 * when `/api/calibration` answers; `STORY_BLEND.proofBody` renders when it does
 * not. The editorial fallback carried the same wrong noun — and it is the copy a
 * reader gets at exactly the moment no live figure is on screen to correct it.
 * Fixing only the live half would have left the defect behind a failure mode,
 * which is where nobody looks.
 *
 * ── WHAT IS DELIBERATELY NOT TESTED ─────────────────────────────────────────
 *
 * Not the figures: #7564 owns the cohort, the count and the error, and this suite
 * asserts nothing about their values. Not the payload keys either — `total_outcomes`
 * and friends are machine names, out of scope by notice 33's clarification.
 * This is one claim: the word beside the number is the word for what the number
 * counts, on both paths, and it is the same word on both.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

// The three GA4 hooks read an AnalyticsProvider context that no static render
// supplies; stubbing them is the house idiom for rendering a page in jest, and
// they have nothing to do with the copy under test.
jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));

import AboutPage from "@/app/about/page";
import { STORY_BLEND } from "@/lib/story-content";

const ABOUT_PAGE = join(__dirname, "..", "app", "about", "page.tsx");

/** Tags out, entities in, whitespace collapsed — what a reader actually reads. */
function visibleText(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&#x27;|&rsquo;/g, "'")
    .replace(/&mdash;/g, "—")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The measured sentence's own source line.
 *
 * The live half runs inside `loadProof`'s effect, which a static render never
 * fires — so the rendered DOM below can only ever show the fallback. Rather than
 * leave the measured string unguarded (it is the one a reader sees on a normal
 * day), it is read out of the page's source. Not soft: a miss throws, because a
 * regex that quietly matched nothing would make every assertion over it pass.
 */
function measuredSentenceSource(): string {
  const src = readFileSync(ABOUT_PAGE, "utf8");
  const match = src.match(/across \{proof\.outcomes\} ([^,]+), our numbers land/);
  if (!match) {
    throw new Error(
      `the measured proof sentence was not found in ${ABOUT_PAGE} — it was reworded or ` +
        "moved, and this suite is no longer reading the string it claims about."
    );
  }
  return match[1];
}

/** The fallback's noun phrase, taken the same way from the published string. */
function fallbackNounPhrase(): string {
  const match = STORY_BLEND.proofBody.match(/across hundreds of thousands of ([^,]+),/);
  if (!match) {
    throw new Error(
      "STORY_BLEND.proofBody no longer opens with the 'across …' clause this suite reads."
    );
  }
  return match[1];
}

describe("#7740 — the noun beside the number", () => {
  it("the measured sentence counts outcomes, not markets", () => {
    expect(measuredSentenceSource()).toBe("traded outcomes");
  });

  it("the editorial fallback counts the same thing", () => {
    expect(fallbackNounPhrase()).toBe("traded outcomes");
  });

  it("and the two paths use ONE noun for one number", () => {
    // The property, not the pair of literals. A future reword that moved one
    // half — the failure this issue actually is — fails here even if both new
    // strings pass a "does not say markets" check on their own.
    expect(fallbackNounPhrase()).toBe(measuredSentenceSource());
  });
});

describe("#7740 — what the fallback path renders", () => {
  // Static render never fires `loadProof`, so `proof` is still {null, null} and
  // the page takes the editorial branch. That is the path under test here, and it
  // is the one a reader gets when `/api/calibration` is unreachable.
  const text = visibleText(renderToStaticMarkup(<AboutPage />));

  it("renders the proof card at all", () => {
    // The anti-vacuous arm: every absence below is free on a page that did not
    // render this card.
    expect(text).toContain(STORY_BLEND.proofLead);
    expect(text).toContain("our numbers land an average of");
  });

  it("does not tell a reader the cohort is a count of markets", () => {
    expect(text).not.toContain("traded markets");
    expect(text).toContain("traded outcomes");
  });
});

describe("#7740 — the check is not vacuous", () => {
  it("the pre-fix sentence fails the predicate this suite applies", () => {
    // The exact string that shipped, checked against the exact rule above. A
    // predicate that cannot reject the specimen is a predicate that proves
    // nothing about the replacement.
    const preFix =
      "across hundreds of thousands of traded markets, our numbers land an average of " +
      "about a point from what actually happened.";
    const phrase = preFix.match(/across hundreds of thousands of ([^,]+),/)?.[1];
    expect(phrase).toBe("traded markets");
    expect(phrase).not.toBe(measuredSentenceSource());
  });

  it("and the source read is anchored, so a reworded page throws rather than passes", () => {
    // `measuredSentenceSource` is the only half this suite cannot reach through a
    // render, which makes its failure mode the one worth demonstrating: it throws
    // on a miss instead of returning a value every later assertion would accept.
    const src = readFileSync(ABOUT_PAGE, "utf8");
    expect(src).toContain("across {proof.outcomes} traded outcomes, our numbers land");
    expect(() =>
      "no such sentence here".match(/across \{proof\.outcomes\} ([^,]+), our numbers land/)![1]
    ).toThrow();
  });
});
