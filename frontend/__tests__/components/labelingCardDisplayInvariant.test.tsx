// #2060 — THE DISPLAY-LAYER INVARIANT, asserted against rendered output.
//
// From Alex's 08-20 gold session: *"Labeling card: 93% + 8% = 101% (complement
// inconsistency), no commence time, truncated team names."* The card was
// `Los Angeles D vs Colorado` (market 59183794, baseball/kalshi).
//
// ## Why this file renders instead of grepping
//
// The other half of this contract lives in `renderedPercentContract.test.ts`,
// which reads source text. That is the right tool for "does native still encode
// the same rule", and the wrong tool for "does the card SHOW this". A source grep
// cannot tell a rendered field from a declared one: while the card JSX lived
// inline in the admin page, a mutation replacing the commence-time conditional
// with `{false && (` left every `commence_time` string in the file intact and
// passed the whole suite. The card is a component now precisely so this test can
// read what a person would see.
//
// Guards run BOTH directions per gotcha #43: the complement pair is forced to
// 100, AND the thin two-outcome book is asserted UNCHANGED at 97 — because
// normalizing that one would invent a probability rather than round one.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import LabelingCard, {
  type LabelingCardData,
} from "@/components/admin/LabelingCard";
import { renderedCardPercents, renderedPercent } from "@/lib/renderedPercent";

function card(over: Partial<LabelingCardData> = {}): LabelingCardData {
  return {
    name: "Los Angeles Dodgers vs Colorado",
    name_at_source: "Los Angeles D vs Colorado",
    source: "kalshi",
    category: "baseball",
    image_url: null,
    hook_description: null,
    rendered_probability: 0.925,
    commence_time: "2026-08-18T00:40:00+00:00",
    resolution_date: "2026-08-22T00:40:00+00:00",
    top_outcomes: [
      { name: "Los Angeles Dodgers", name_at_source: "Los Angeles D", probability: 0.925, rendered_percent: 93 },
      { name: "Colorado", probability: 0.075, rendered_percent: 7 },
    ],
    ...over,
  };
}

/** Every `NN%` the card actually prints, in document order. */
function renderedPercents(data: LabelingCardData): number[] {
  const html = renderToStaticMarkup(<LabelingCard card={data} />);
  return [...html.matchAll(/>(\d+)%</g)].map((m) => Number(m[1]));
}

describe("a two-outcome complement card sums to exactly 100 on screen", () => {
  it("the exemplar prints 93 and 7, and they sum to 100", () => {
    const percents = renderedPercents(card());
    // headline + two outcome rows; the headline repeats the leader.
    expect(percents).toEqual([93, 93, 7]);
    const field = percents.slice(1);
    expect(field.reduce((a, b) => a + b, 0)).toBe(100);
  });

  it("the headline never disagrees with the first outcome row", () => {
    // A pair summing to 1.01 renders 70/30, so a headline that re-rounded the raw
    // leader float would print 71 beside a row saying 70.
    const served = renderedCardPercents([0.705, 0.305]) as number[];
    expect(served).toEqual([70, 30]);
    const percents = renderedPercents(
      card({
        rendered_probability: 0.705,
        top_outcomes: [
          { name: "A", probability: 0.705, rendered_percent: served[0] },
          { name: "B", probability: 0.305, rendered_percent: served[1] },
        ],
      })
    );
    expect(percents).toEqual([70, 70, 30]);
    expect(renderedPercent(0.705)).toBe(71); // what re-rounding would have printed
  });

  it.each([
    [[0.925, 0.075]],
    [[0.915, 0.085]],
    [[0.605, 0.395]],
    [[0.995, 0.01]],
    [[0.705, 0.305]],
    [[0.59, 0.4]],
  ])("%s renders a field summing to 100", (probs) => {
    const served = renderedCardPercents(probs) as number[];
    const percents = renderedPercents(
      card({
        rendered_probability: probs[0],
        top_outcomes: [
          { name: "A", probability: probs[0], rendered_percent: served[0] },
          { name: "B", probability: probs[1], rendered_percent: served[1] },
        ],
      })
    );
    expect(percents.slice(1).reduce((a, b) => a + b, 0)).toBe(100);
  });
});

describe("the other direction — a card that is NOT a complement pair", () => {
  it("a thin two-outcome book still prints 57 and 40, summing to 97", () => {
    const served = renderedCardPercents([0.57, 0.4]) as number[];
    expect(served).toEqual([57, 40]);
    const percents = renderedPercents(
      card({
        rendered_probability: 0.57,
        top_outcomes: [
          { name: "A", probability: 0.57, rendered_percent: served[0] },
          { name: "B", probability: 0.4, rendered_percent: served[1] },
        ],
      })
    );
    expect(percents.slice(1).reduce((a, b) => a + b, 0)).toBe(97);
  });

  it("a three-way field is untouched", () => {
    const served = renderedCardPercents([0.5, 0.3, 0.2]) as number[];
    const percents = renderedPercents(
      card({
        rendered_probability: 0.5,
        top_outcomes: [
          { name: "A", probability: 0.5, rendered_percent: served[0] },
          { name: "B", probability: 0.3, rendered_percent: served[1] },
          { name: "C", probability: 0.2, rendered_percent: served[2] },
        ],
      })
    );
    expect(percents).toEqual([50, 50, 30, 20]);
  });
});

describe("the card shows WHEN (#2060 item 2)", () => {
  it("renders the commence time, labelled as a start", () => {
    const html = renderToStaticMarkup(<LabelingCard card={card()} />);
    expect(html).toContain("Starts");
    expect(html).toContain('data-testid="card-commence"');
  });

  it("distinguishes the start from the resolution date", () => {
    // On a Kalshi game market `resolution_date` is the CLOSE time, not the start
    // (gotcha #14) — so the one date the card used to show was the wrong one.
    const html = renderToStaticMarkup(<LabelingCard card={card()} />);
    expect(html).toContain("Starts");
    expect(html).toContain("Resolves");
  });

  it("shows nothing rather than a guess when there is no commence time", () => {
    const html = renderToStaticMarkup(
      <LabelingCard card={card({ commence_time: null })} />
    );
    expect(html).not.toContain('data-testid="card-commence"');
    expect(html).not.toContain("Starts");
    // …and the resolution date is still shown, so the row does not vanish.
    expect(html).toContain("Resolves");
  });

  it("an unparseable timestamp is omitted, not rendered as Invalid Date", () => {
    const html = renderToStaticMarkup(
      <LabelingCard card={card({ commence_time: "not-a-date" })} />
    );
    expect(html).not.toContain("Invalid Date");
    expect(html).not.toContain("Starts");
  });
});

describe("the card shows readable team names (#2060 item 3)", () => {
  it("renders the repaired name, not the truncated one", () => {
    const html = renderToStaticMarkup(<LabelingCard card={card()} />);
    expect(html).toContain("Los Angeles Dodgers vs Colorado");
    expect(html).not.toContain("Los Angeles D vs Colorado");
    expect(html).toContain("Los Angeles Dodgers");
  });

  it("renders whatever the server sent when nothing could be repaired", () => {
    // The server abstains rather than guessing, and the card must show that
    // honestly — a short name is visibly short, a wrong one is not.
    const html = renderToStaticMarkup(
      <LabelingCard
        card={card({
          name: "Yang vs Vasileva",
          name_at_source: "Yang vs Vasileva",
          top_outcomes: [
            { name: "Yang", probability: 0.96, rendered_percent: 96 },
            { name: "Vasileva", probability: 0.04, rendered_percent: 4 },
          ],
        })}
      />
    );
    expect(html).toContain("Yang vs Vasileva");
  });
});

describe("a pre-#2060 payload still renders", () => {
  it("falls back to the shared scalar rule when no percent was served", () => {
    // An old backend serves no `rendered_percent`. The card must not blank out;
    // it renders the contract's scalar answer, which is what it did before.
    const percents = renderedPercents(
      card({
        top_outcomes: [
          { name: "A", probability: 0.925 },
          { name: "B", probability: 0.075 },
        ],
      })
    );
    expect(percents).toEqual([93, 93, 8]);
  });
});
