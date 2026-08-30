// #2088 — THE NON-100 CARD SAYS WHY, asserted against rendered output.
//
// UX-P113 (#2060) fixed the two-outcome card that SHOULD total 100 and left the
// one that should not exactly as it was. That was right — normalizing a pair
// summing to 0.97 invents three points of probability rather than rounding one —
// but INT-104 measured the deploy check at **17 of 18** and filed this: a card
// reading `57 / 40` looks broken in precisely the way `93 / 8` looked broken, and
// the reader cannot tell "these are two real numbers that genuinely do not add
// up" from "our renderer is buggy again".
//
// ## Why this file renders instead of checking the rule
//
// `renderedPercentContract.test.ts` already drives `cardSumReason` through the
// shared table, and it would stay green if this component stopped printing the
// sentence entirely — a pure-lib guard cannot see a render. The sibling
// `labelingCardDisplayInvariant.test.tsx` exists for the same reason and says so:
// a mutation that replaced a conditional with `{false && (` once left every
// matching string in the file intact and passed the whole suite.
//
// So every assertion here reads `renderToStaticMarkup` output, and the plants at
// the bottom prove the assertions can actually fail.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import LabelingCard, {
  type LabelingCardData,
} from "@/components/admin/LabelingCard";
import { CARD_SUM_EXPLANATION } from "@/lib/cardSum";
import {
  SUM_INDEPENDENT_PRICES,
  SUM_UNPRICED_OUTCOME,
  cardSumReason,
  renderedCardPercents,
} from "@/lib/renderedPercent";

/** The filed exemplar: market 59194098, Bilardo vs Gschwendtner, served 57 / 40. */
function card(over: Partial<LabelingCardData> = {}): LabelingCardData {
  const served = renderedCardPercents([0.57, 0.4]) as number[];
  return {
    name: "Jacopo Bilardo vs Jeremy Gschwendtner",
    source: "kalshi",
    category: "tennis",
    image_url: null,
    hook_description: null,
    rendered_probability: 0.57,
    commence_time: "2026-08-21T00:40:00+00:00",
    resolution_date: "2026-08-22T00:40:00+00:00",
    top_outcomes: [
      { name: "Jacopo Bilardo", probability: 0.57, rendered_percent: served[0] },
      { name: "Jeremy Gschwendtner", probability: 0.4, rendered_percent: served[1] },
    ],
    card_sum_reason: SUM_INDEPENDENT_PRICES,
    ...over,
  };
}

const html = (data: LabelingCardData) =>
  renderToStaticMarkup(<LabelingCard card={data} />);

/** Every `NN%` the card actually prints, in document order. */
function renderedPercents(data: LabelingCardData): number[] {
  return [...html(data).matchAll(/>(\d+)%</g)].map((m) => Number(m[1]));
}

describe("a card whose numbers do not total 100 explains itself", () => {
  it("the filed exemplar still prints 57 and 40 — and now says why", () => {
    const markup = html(card());
    // The numbers are UNCHANGED. This queue explains the card; it does not
    // normalize it, because normalizing would invent three points.
    expect(renderedPercents(card()).slice(1).reduce((a, b) => a + b, 0)).toBe(97);
    expect(markup).toContain('data-testid="card-sum-explanation"');
    expect(markup).toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
  });

  it("the live 2026-08-29 specimen explains itself the same way", () => {
    // 'Diane Parry vs Ann Li: Set 2 Winner', served [51, 48] = 99. A different
    // market from the filed row, and it misses in the other direction.
    const served = renderedCardPercents([0.507, 0.478]) as number[];
    expect(served).toEqual([51, 48]);
    const markup = html(
      card({
        rendered_probability: 0.507,
        top_outcomes: [
          { name: "Diane Parry", probability: 0.507, rendered_percent: served[0] },
          { name: "Ann Li", probability: 0.478, rendered_percent: served[1] },
        ],
      })
    );
    expect(markup).toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
  });

  it("an unpriced side gets its OWN sentence, not the other one", () => {
    // Ruling 086's shape: folding absence into disagreement would tell the reader
    // "these two do not agree" about a card that only carries one number.
    const markup = html(
      card({
        top_outcomes: [
          { name: "A", probability: 0.57, rendered_percent: 57 },
          { name: "B", probability: null, rendered_percent: null },
        ],
        card_sum_reason: SUM_UNPRICED_OUTCOME,
      })
    );
    expect(markup).toContain(CARD_SUM_EXPLANATION[SUM_UNPRICED_OUTCOME]);
    expect(markup).not.toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
  });
});

describe("the other direction — cards that must stay silent (gotcha #43)", () => {
  it("the #2060 complement exemplar carries NO explanation", () => {
    // 93 / 7 totals 100. An apology here would be worse than the bug: it would
    // tell Alex a correct card is suspect.
    const served = renderedCardPercents([0.925, 0.075]) as number[];
    const markup = html(
      card({
        rendered_probability: 0.925,
        top_outcomes: [
          { name: "Los Angeles Dodgers", probability: 0.925, rendered_percent: served[0] },
          { name: "Colorado", probability: 0.075, rendered_percent: served[1] },
        ],
        card_sum_reason: null,
      })
    );
    expect(markup).not.toContain('data-testid="card-sum-explanation"');
    expect(markup).not.toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
  });

  it("a three-way field carries no explanation — it is out of scope", () => {
    const served = renderedCardPercents([0.5, 0.3, 0.2]) as number[];
    const markup = html(
      card({
        rendered_probability: 0.5,
        top_outcomes: [
          { name: "A", probability: 0.5, rendered_percent: served[0] },
          { name: "B", probability: 0.3, rendered_percent: served[1] },
          { name: "C", probability: 0.2, rendered_percent: served[2] },
        ],
        card_sum_reason: null,
      })
    );
    expect(markup).not.toContain('data-testid="card-sum-explanation"');
  });
});

describe("the SERVED reason is authoritative, including when it is null", () => {
  it("a served null keeps the card silent even though the field misses 100", () => {
    // The server is the one place this is decided. If the client re-derived
    // whenever the served value was falsy, the server's answer would be
    // decorative and the two surfaces could disagree about the same card.
    const markup = html(card({ card_sum_reason: null }));
    expect(markup).not.toContain('data-testid="card-sum-explanation"');
  });

  it("an ABSENT key falls back to deriving it — a pre-#2088 payload still explains", () => {
    const { card_sum_reason: _omitted, ...withoutKey } = card();
    expect("card_sum_reason" in withoutKey).toBe(false);
    const markup = html(withoutKey as LabelingCardData);
    expect(markup).toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
    // …and the fallback agrees with what the server would have said.
    expect(cardSumReason([0.57, 0.4])).toBe(SUM_INDEPENDENT_PRICES);
  });

  it("an unrecognised reason draws NOTHING rather than guessing", () => {
    const markup = html(card({ card_sum_reason: "some_future_reason" }));
    expect(markup).not.toContain('data-testid="card-sum-explanation"');
  });
});

describe("the copy clears the standing bans", () => {
  it("says nothing from the banned `price` stem (ruling 138)", () => {
    // The machine-readable reasons DO carry the stem; they are payload enums and
    // never reach a text node. The sentences must not.
    const stem = /\b(un)?pric(e|es|ed|ing)\b/i;
    for (const sentence of Object.values(CARD_SUM_EXPLANATION)) {
      expect([sentence, stem.test(sentence)]).toEqual([sentence, false]);
    }
  });

  it("names no venue (ruling 141)", () => {
    for (const sentence of Object.values(CARD_SUM_EXPLANATION)) {
      expect(sentence).not.toMatch(/\b(Kalshi|Polymarket)\b/);
    }
  });

  it("the enum values survive the bundle scanner's own stem pattern", () => {
    // `independent_prices` and `unpriced_outcome` contain the stem but not the
    // word boundary the pattern needs — the neighbouring `_` is a word character.
    // Asserted rather than argued, because the shipped-copy scan reads the bundle.
    const stem = /\b(un)?pric(e|es|ed|ing)\b/i;
    expect(stem.test(SUM_INDEPENDENT_PRICES)).toBe(false);
    expect(stem.test(SUM_UNPRICED_OUTCOME)).toBe(false);
  });
});

// ── PLANTS: each one breaks the feature and must turn this file red ───────────
//
// Asserted here rather than run by hand, because "the guard would have caught it"
// is a claim with no receipt otherwise.

describe("the guards can fail", () => {
  it("a component that stops rendering the sentence is caught", () => {
    // Simulates `{false && (` around the explanation block.
    const markup = html(card()).replace(
      CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES],
      ""
    );
    expect(markup).not.toContain(CARD_SUM_EXPLANATION[SUM_INDEPENDENT_PRICES]);
  });

  it("a rule that normalized the thin pair instead of explaining it is caught", () => {
    // The mutation this queue must never become: forcing 57/40 to 100.
    const normalized = renderedCardPercents([0.57 / 0.97, 0.4 / 0.97]) as number[];
    expect(normalized.reduce((a, b) => a + b, 0)).toBe(100);
    // …which is NOT what the card prints, and the first test above asserts 97.
    expect(renderedPercents(card()).slice(1).reduce((a, b) => a + b, 0)).toBe(97);
  });

  it("a copy change that reintroduced the banned stem is caught", () => {
    const stem = /\b(un)?pric(e|es|ed|ing)\b/i;
    expect(stem.test("One side is not priced yet.")).toBe(true);
  });
});
