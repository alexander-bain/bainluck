// #2088 criterion 3 — THE CARD RULE ON THE FEED, asserted against rendered output.
//
// UX-P159 decided the reason once (`graded_card.card_sum_reason`) and printed it on
// both LABELING surfaces. It left the feed alone and said so. This is what that cost:
// before this queue there was no `rendered_percent` anywhere in `routes/feed.py`, and
// `FeedCard.tsx` printed `Math.round(outcome.probability * 100)` per outcome — one
// independent rounding per side, which is the arithmetic #2060 exists to replace and
// the one surface it had never reached.
//
// ## Which surface this is, measured rather than assumed
//
// NOT Discover. `components/discover/FuturesCard.tsx` prints only the hero leader, so
// a two-outcome card shows ONE number there and no sum is visible. The pair is printed
// by THIS component, which serves `/categories/*`, `/sports` and `/my-stuff`. Both are
// fed by `GET /api/feed`, so one server change covers them; the reader-visible payoff
// is on the category and sports pages.
//
// AMENDED BY UX-P162: still true about the SUM, but that Discover hero was rounding
// its own raw probability while this card took the rule, so one market could read 57%
// there and 56% here. Both now call `renderedLeaderPercent`. See
// `__tests__/components/discoverHeroAgreesWithFeedCard.test.tsx`.
//
// ## Why this file renders instead of checking the rule
//
// `renderedPercentContract.test.ts` already drives `cardSumReason` through the shared
// table and would stay green if this component never printed the sentence — which is
// exactly the state this queue found. A pure-lib guard cannot see a render, so every
// assertion here reads `renderToStaticMarkup` output and the plants at the bottom
// prove the assertions can fail.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FeedCard from "../../components/FeedCard";
import { CARD_SUM_EXPLANATION } from "@/lib/cardSum";
import {
  SUM_INDEPENDENT_PRICES,
  SUM_UNPRICED_OUTCOME,
} from "@/lib/renderedPercent";

type Outcome = {
  id: number;
  name: string;
  probability: number | null;
  rendered_percent?: number | null;
};

/**
 * A futures feed item as the SERVER now serves it — percents annotated per outcome,
 * `card_sum_reason` present (possibly null). `rendered_percent` is deliberately
 * spelled out per fixture rather than derived, so a rule change has to be restated
 * here instead of silently agreeing with itself.
 */
function futures(
  outcomes: Outcome[],
  cardSumReason: string | null | undefined,
  over: Partial<FeedFuturesData> = {}
): FeedItem {
  const data: Record<string, unknown> = {
    id: 108621,
    name: "Which party will win the U.S. House?",
    outcome_count: outcomes.length,
    status: "open",
    top_outcomes: outcomes.map((o, i) => ({ rank: i + 1, movement: null, ...o })),
    ...over,
  };
  // `undefined` must mean the KEY IS ABSENT (a pre-#2088 payload), not a served
  // null — the component distinguishes them and so must the fixture.
  if (cardSumReason !== undefined) data.card_sum_reason = cardSumReason;
  return { type: "futures", data: data as unknown as FeedFuturesData } as FeedItem;
}

// ── 1. THE TWO CARDS THAT PRINT 101 ON THE DEPLOYED BUILD ────────────────────

describe("the complement pair stops printing 101", () => {
  it("`Which party will win the U.S. House?` prints 85 and 15, not 85 and 16", () => {
    // Measured on production 2026-08-29: served 0.845 / 0.155, which is a complement
    // pair on the half-cent grid, so both sides round up independently and the card
    // prints 101. Under the card rule the headline survives and the other side is
    // DERIVED as 100 - 85.
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "Democratic Party", probability: 0.845, rendered_percent: 85 },
            { id: 2, name: "Republican Party", probability: 0.155, rendered_percent: 15 },
          ],
          null
        )}
      />
    );
    expect(html).toContain("85%");
    expect(html).toContain("15%");
    expect(html).not.toContain("16%");
  });

  it("`Will Neuralink's valuation hit (HIGH) $47.5B` prints 73 and 27, not 73 and 28", () => {
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "No", probability: 0.725, rendered_percent: 73 },
            { id: 2, name: "Yes", probability: 0.275, rendered_percent: 27 },
          ],
          null,
          { id: 57792416, name: "Will Neuralink's valuation hit (HIGH) $47.5B by August 31?" }
        )}
      />
    );
    expect(html).toContain("73%");
    expect(html).toContain("27%");
    expect(html).not.toContain("28%");
  });

  it("a corrected pair carries NO sentence — it totals 100 (gotcha #43)", () => {
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "Democratic Party", probability: 0.845, rendered_percent: 85 },
            { id: 2, name: "Republican Party", probability: 0.155, rendered_percent: 15 },
          ],
          null
        )}
      />
    );
    expect(html).not.toContain("data-testid=\"card-sum-explanation\"");
    expect(html).not.toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
  });
});

// ── 2. THE FOUR CARDS THAT PRINT AN UNEXPLAINED NON-100 ──────────────────────

describe("a feed card whose numbers do not total 100 explains itself", () => {
  it("`Texas State House winner?` still prints 25 and 16 — and now says why", () => {
    // 0.25 + 0.16 = 0.41. Normalizing would invent fifty-nine points of probability;
    // the refusal is the point, and the sentence is what makes it readable.
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "Democratic party", probability: 0.25, rendered_percent: 25 },
            { id: 2, name: "Republican party", probability: 0.16, rendered_percent: 16 },
          ],
          SUM_INDEPENDENT_PRICES,
          { id: 52756062, name: "Texas State House winner?" }
        )}
      />
    );
    expect(html).toContain("25%");
    expect(html).toContain("16%");
    expect(html).toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
  });

  it("`Russia x Ukraine ceasefire agreement by...?` explains its 49 / 34", () => {
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "December 31", probability: 0.485, rendered_percent: 49 },
            { id: 2, name: "October 31", probability: 0.335, rendered_percent: 34 },
          ],
          SUM_INDEPENDENT_PRICES,
          { id: 20569379, name: "Russia x Ukraine ceasefire agreement by...?" }
        )}
      />
    );
    expect(html).toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
  });

  it("an unpriced side gets its OWN sentence, not the other one", () => {
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "Yes", probability: 0.57, rendered_percent: 57 },
            { id: 2, name: "No", probability: null, rendered_percent: null },
          ],
          SUM_UNPRICED_OUTCOME
        )}
      />
    );
    expect(html).toContain(CARD_SUM_EXPLANATION[SUM_UNPRICED_OUTCOME]);
    expect(html).not.toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
    // "no price" is not "0%" — the unpriced side prints no number at all. Matched
    // as the PRINTED span (`>0%<`) rather than the bare string, which also occurs
    // in the bar's `width:0%` and would make this assertion pass for the wrong
    // reason. The bar is a length; the span is the claim.
    expect(html).not.toContain(">0%<");
    // …and it does not ANNOUNCE zero either: an absent value is absent, not 0.
    expect(html).not.toContain('aria-valuenow="0"');
  });
});

// ── 3. SCOPE: ARITY OTHER THAN TWO MAKES NO CLAIM ABOUT A TOTAL ──────────────

describe("the rule stays inside the arity UX-P159 scoped it to", () => {
  it("a three-way field carries no explanation even though it misses 100", () => {
    // 27 + 25 + 25 = 77. This is the independent-binary class (gotcha #23), which
    // already has `field_coherence` and `_feed_display_scale`. Widening the reason
    // to cover it is a product decision, not a tidy-up.
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "A", probability: 0.27, rendered_percent: 27 },
            { id: 2, name: "B", probability: 0.25, rendered_percent: 25 },
            { id: 3, name: "C", probability: 0.25, rendered_percent: 25 },
          ],
          null
        )}
      />
    );
    expect(html).toContain("27%");
    expect(html).not.toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
    expect(html).not.toContain(CARD_SUM_EXPLANATION[SUM_UNPRICED_OUTCOME]);
  });
});

// ── 4. THE SERVED ANSWER IS AUTHORITATIVE, INCLUDING WHEN IT IS NULL ─────────

describe("the served reason wins; the fallback keys on ABSENCE, not falsiness", () => {
  it("a served null keeps the card silent even though the pair misses 100", () => {
    // If the fallback keyed on the value being falsy (`?? derive()`), this card would
    // re-derive `independent_prices` and print a sentence the server did not ask for,
    // making the server's answer decorative.
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "A", probability: 0.25, rendered_percent: 25 },
            { id: 2, name: "B", probability: 0.16, rendered_percent: 16 },
          ],
          null
        )}
      />
    );
    expect(html).not.toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
  });

  it("an ABSENT key falls back to deriving it — a pre-#2088 payload still explains", () => {
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "A", probability: 0.25 },
            { id: 2, name: "B", probability: 0.16 },
          ],
          undefined
        )}
      />
    );
    expect(html).toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
    // …and the percents fall back too, rather than vanishing.
    expect(html).toContain("25%");
    expect(html).toContain("16%");
  });

  it("an unrecognised reason draws NOTHING rather than guessing", () => {
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "A", probability: 0.25, rendered_percent: 25 },
            { id: 2, name: "B", probability: 0.16, rendered_percent: 16 },
          ],
          "some_reason_this_build_has_never_heard_of"
        )}
      />
    );
    expect(html).not.toContain("card-sum-explanation");
  });
});

// ── 5. THE PERCENT TRAVELS WITH ITS OUTCOME THROUGH CLIENT REORDERING ────────

describe("the served percent is paired with its own outcome", () => {
  it("survives `leaderFirstSlice` re-ordering an unsorted payload", () => {
    // UX-P005 class (a): ~23% of feed-surfaced markets carry a stored rank that
    // disagrees with the probability order, and this component sorts leader-first
    // before printing. A card-level positional array would be mis-paired on exactly
    // those cards; annotating the outcome cannot be.
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 2, name: "Republican Party", probability: 0.155, rendered_percent: 15 },
            { id: 1, name: "Democratic Party", probability: 0.845, rendered_percent: 85 },
          ],
          null
        )}
      />
    );
    // Scoped to the OUTCOME ROWS via the `title` attribute, which only the rows
    // carry. The headline above them reads `top_outcomes[0]` directly and is NOT
    // leader-first — a pre-existing #1526-class gap in this component that the
    // server's own descending sort keeps latent. Out of scope here, and noted
    // rather than silently fixed under a card-sum change.
    expect(html.indexOf('title="Democratic Party"')).toBeLessThan(
      html.indexOf('title="Republican Party"')
    );
    expect(html).toContain("85%");
    expect(html).toContain("15%");
    expect(html).not.toContain("16%");
  });

  it("the headline and its own row print the SAME number (Queue 283's invariant)", () => {
    // The row takes the card-rule percent, so the headline must take it too. A pair
    // summing to 0.99 normalizes to a leader of 58 while the raw probability rounds
    // to 57 — before this, the card printed both, one line apart.
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "Yes", probability: 0.57, rendered_percent: 58 },
            { id: 2, name: "No", probability: 0.42, rendered_percent: 42 },
          ],
          null
        )}
      />
    );
    expect(html).toContain("58%");
    expect(html).not.toContain("57%");
  });
});

// ── 6. THE COPY CLEARS THE STANDING BANS ─────────────────────────────────────

describe("the copy clears the standing bans", () => {
  it("says nothing from the banned `price` stem (ruling 138)", () => {
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "A", probability: 0.25, rendered_percent: 25 },
            { id: 2, name: "B", probability: 0.16, rendered_percent: 16 },
          ],
          SUM_INDEPENDENT_PRICES
        )}
      />
    );
    const sentence = CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES];
    expect(html).toContain(sentence);
    expect(/\bprices?\b|\bpriced\b|\bunpriced\b/i.test(sentence)).toBe(false);
  });

  it("the enum values survive the bundle scanner's own stem pattern", () => {
    // The machine-readable reasons DO carry the stem, and that is fine: they are
    // payload enums, never rendered, and the scanner's pattern needs a word boundary
    // that `_` does not provide. Asserted rather than argued.
    const stem = /\bprices?\b/i;
    expect(stem.test(SUM_INDEPENDENT_PRICES)).toBe(false);
    expect(stem.test(SUM_UNPRICED_OUTCOME)).toBe(false);
  });
});

// ── 7. THE GUARDS CAN FAIL ───────────────────────────────────────────────────
//
// A mutation that replaced a conditional with `{false && (` once left every matching
// string in the file intact and passed the whole suite. These plants are the answer.

describe("the guards can fail", () => {
  it("a component that stopped rendering the sentence would be caught", () => {
    const withSentence = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "A", probability: 0.25, rendered_percent: 25 },
            { id: 2, name: "B", probability: 0.16, rendered_percent: 16 },
          ],
          SUM_INDEPENDENT_PRICES
        )}
      />
    );
    const withoutSentence = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "A", probability: 0.25, rendered_percent: 25 },
            { id: 2, name: "B", probability: 0.16, rendered_percent: 16 },
          ],
          null
        )}
      />
    );
    // The two renders MUST differ — if they do not, the component is ignoring the
    // reason and every assertion in section 2 is vacuous.
    expect(withSentence).not.toEqual(withoutSentence);
    expect(withSentence).toContain("card-sum-explanation");
    expect(withoutSentence).not.toContain("card-sum-explanation");
  });

  it("a component that ignored the served percent would be caught", () => {
    // Serve a percent that DISAGREES with the probability. If the component still
    // prints its own `Math.round(p * 100)`, this fails — which is the regression
    // this whole queue is about.
    const html = renderToStaticMarkup(
      <FeedCard
        item={futures(
          [
            { id: 1, name: "A", probability: 0.845, rendered_percent: 11 },
            { id: 2, name: "B", probability: 0.155, rendered_percent: 89 },
          ],
          null
        )}
      />
    );
    expect(html).toContain("11%");
    expect(html).toContain("89%");
    expect(html).not.toContain("85%");
  });
});
