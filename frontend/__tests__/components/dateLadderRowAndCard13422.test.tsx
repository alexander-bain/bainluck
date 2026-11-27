/**
 * #13422 & 69603905: website date ladders in both compact row and full card.
 *
 * (a) A date-ladder compact row reads every priced rung (not only the first 8)
 *     so a 10-rung ladder like impeachment (`112818`) names its earliest coming
 *     date at >= 50% (rung 9: `Before Oct 1, 2027`).
 * (b) Full `<FuturesCard>` on a date ladder (`69603905` US x Iran ceasefire)
 *     never highlights or captions a passed date (`November 22`) once a today or
 *     future rung exists.
 * (c) Non-date ladders (`$220..$275` price ladder `71579121` and `Above N`
 *     comparators) stay untouched in both `FuturesCompactRow` and `FuturesCard`.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { FuturesCard, FuturesCompactRow } from "../../components/discover/FuturesCard";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

type Point = {
  label: string;
  probability: number;
  value: number;
  unit?: string | null;
  source?: string | null;
  direction?: string | null;
};

function makeFuturesData(
  id: number,
  name: string,
  points: Point[],
  topOutcomes?: { name: string; probability: number }[],
  suggestedFormat = "threshold_heatmap",
): { item: FeedItem; data: FeedFuturesData } {
  const outcomes =
    topOutcomes ??
    [...points]
      .sort((a, b) => b.probability - a.probability)
      .slice(0, 3)
      .map((p, i) => ({ id: i + 1, name: p.label, probability: p.probability, movement: null }));
  const data = {
    id,
    name,
    llm_sport_category: "politics",
    sport_name: "Politics",
    resolution_date: "2028-02-01T00:00:00Z",
    top_outcomes: outcomes.map((o, i) => ({ id: i + 1, movement: null, ...o })),
    outcome_count: points.length,
    volume_24h: 100_000,
    confidence_tier: "high",
    discover_card: {
      suggested_format: suggestedFormat,
      threshold_points: points,
    },
  } as unknown as FeedFuturesData;
  const item = {
    type: "futures",
    score: 90,
    reason: "",
    headline: "",
    data,
  } as unknown as FeedItem;
  return { item, data };
}

function renderCard(id: number, name: string, points: Point[], topOutcomes?: { name: string; probability: number }[]): string {
  const { item, data } = makeFuturesData(id, name, points, topOutcomes);
  return renderToStaticMarkup(
    <FuturesCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

function renderCompactRow(
  id: number,
  name: string,
  points: Point[],
  topOutcomes?: { name: string; probability: number }[],
): { answer: string | null; percent: string | null; html: string } {
  const { item, data } = makeFuturesData(id, name, points, topOutcomes);
  const html = renderToStaticMarkup(<FuturesCompactRow item={item} data={data} />);
  const ans = html.match(/data-testid="compact-row-answer">([^<]*)<\/span>/);
  const pct = html.match(/data-testid="compact-row-percent">([^<]*)<\/span>/);
  return {
    answer: ans ? ans[1] : null,
    percent: pct ? pct[1] : null,
    html,
  };
}

function highlightedRungs(html: string): string[] {
  return Array.from(
    html.matchAll(/<div class="[^"]*bg-accent-brand\/\[0\.06\][^"]*" aria-label="([^"]*): [^"]*"/g),
    (m) => m[1],
  );
}

function cardCaption(html: string): string | null {
  const m = html.match(
    /<span class="[^"]*text-text-secondary[^"]*">More likely than not:<\/span><span class="[^"]*text-accent-brand[^"]*">([^<]*)<\/span>/,
  );
  return m ? m[1] : null;
}

const datePoint = (label: string, value: number, probability: number): Point => ({
  label,
  value,
  probability,
  unit: "date",
  source: "date_bucket",
});

// Live payload structure from /api/feed for 112818 ("Will the House impeach Trump?")
const IMPEACHMENT_112818_POINTS: Point[] = [
  datePoint("Before Jan 1, 2027", 20270101, 0.0075),
  datePoint("Before Feb 1, 2027", 20270201, 0.055),
  datePoint("Before Mar 1, 2027", 20270301, 0.105),
  datePoint("Before Apr 1, 2027", 20270401, 0.165),
  datePoint("Before May 1, 2027", 20270501, 0.25),
  datePoint("Before Jun 1, 2027", 20270601, 0.325),
  datePoint("Before Jul 1, 2027", 20270701, 0.365),
  datePoint("Before Aug 1, 2027", 20270801, 0.455),
  datePoint("Before Oct 1, 2027", 20271001, 0.505),
  datePoint("Before Jan 1, 2028", 20280101, 0.605),
];

// Live payload structure from /api/feed for 69603905 ("US x Iran Effective Ceasefire begins?")
const CEASEFIRE_69603905_POINTS: Point[] = [
  datePoint("November 22", 20001122, 0.57),
  datePoint("November 30", 20001130, 0.735),
  datePoint("December 31", 20001231, 0.885),
];

// Live specimen 71579121 ("How high will Amazon finish the week?") from #13422
const AMAZON_71579121_POINTS: Point[] = [
  { label: "$220", value: 220, probability: 0.96, unit: "usd", source: "outcome" },
  { label: "$225", value: 225, probability: 0.93, unit: "usd", source: "outcome" },
  { label: "$230", value: 230, probability: 0.89, unit: "usd", source: "outcome" },
  { label: "$235", value: 235, probability: 0.845, unit: "usd", source: "outcome" },
  { label: "$250", value: 250, probability: 0.31, unit: "usd", source: "outcome" },
  { label: "$275", value: 275, probability: 0.04, unit: "usd", source: "outcome" },
];

describe("#13422 & 69603905 date ladders across compact row and full card", () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  test("(a) 112818 compact row scans past 8 rungs to name earliest coming date >= 50%", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-11-26T14:30:00Z"));
    const row = renderCompactRow(
      112818,
      "Will the House impeach Trump?",
      IMPEACHMENT_112818_POINTS,
      [
        { name: "Before Jan 1, 2028", probability: 0.605 },
        { name: "Before Oct 1, 2027", probability: 0.505 },
        { name: "Before Aug 1, 2027", probability: 0.455 },
      ],
    );
    expect(row.answer).toBe("Before Oct 1, 2027");
    expect(row.percent).toBe("51%");
    expect(row.html).not.toContain("61%");
  });

  test("(a) 10-rung date ladder compact row skips an earlier passed >=50% rung and still finds rung 10", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-11-26T14:30:00Z"));
    const withPassedRung: Point[] = [
      datePoint("Before Nov 1, 2026", 20261101, 0.55),
      ...IMPEACHMENT_112818_POINTS.slice(0, 9), // total 10 rungs; rung 10 is Before Oct 1, 2027 (0.505)
    ];
    const row = renderCompactRow(
      11281801,
      "Will the House impeach Trump?",
      withPassedRung,
      [
        { name: "Before Nov 1, 2026", probability: 0.55 },
        { name: "Before Oct 1, 2027", probability: 0.505 },
        { name: "Before Aug 1, 2027", probability: 0.455 },
      ],
    );
    expect(row.answer).toBe("Before Oct 1, 2027");
    expect(row.percent).toBe("51%");
  });

  test("(b) 69603905 full card skips passed November 22 and highlights/captions November 30 on Nov 26", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-11-26T14:30:00Z"));
    const html = renderCard(
      69603905,
      "US x Iran Effective Ceasefire begins?",
      CEASEFIRE_69603905_POINTS,
      [
        { name: "December 31", probability: 0.885 },
        { name: "November 30", probability: 0.735 },
        { name: "November 22", probability: 0.57 },
      ],
    );
    expect(cardCaption(html)).toBe("November 30");
    expect(highlightedRungs(html)).toEqual(["November 30"]);
    expect(html).not.toContain("More likely than not:</span><span class=\"min-w-0 font-semibold text-[13px] text-accent-brand\">November 22");
  });

  test("(b) date-ladder full card still highlights today's date when date == today", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-11-22T14:30:00Z"));
    const html = renderCard(
      69603905,
      "US x Iran Effective Ceasefire begins?",
      CEASEFIRE_69603905_POINTS,
    );
    expect(cardCaption(html)).toBe("November 22");
    expect(highlightedRungs(html)).toEqual(["November 22"]);
  });

  test("(b) when passed date >=50% and upcoming dates are <50%, full card omits caption and highlights highest upcoming rung", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-11-26T14:30:00Z"));
    const html = renderCard(69603905, "US x Iran Effective Ceasefire begins?", [
      datePoint("November 22", 20001122, 0.57),
      datePoint("November 30", 20001130, 0.35),
      datePoint("December 31", 20001231, 0.45),
    ]);
    expect(cardCaption(html)).toBeNull();
    expect(highlightedRungs(html)).toEqual(["December 31"]);
  });

  test("(b) when every date rung has already passed, full card falls back cleanly instead of blanking", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-11-26T14:30:00Z"));
    const html = renderCard(69603906, "Earlier ceasefire window?", [
      datePoint("November 1", 20001101, 0.40),
      datePoint("November 15", 20001115, 0.62),
      datePoint("November 22", 20001122, 0.85),
    ]);
    expect(cardCaption(html)).toBe("November 15");
    expect(highlightedRungs(html)).toEqual(["November 15"]);
  });

  test("(c) non-date ladders ($220-$275 Amazon 71579121 and 10-rung Above comparators) remain unchanged", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-11-26T14:30:00Z"));
    const amazonRow = renderCompactRow(
      71579121,
      "How high will Amazon finish the week?",
      AMAZON_71579121_POINTS,
      [
        { name: "$220", probability: 0.96 },
        { name: "$225", probability: 0.93 },
        { name: "$235", probability: 0.845 },
      ],
    );
    expect(amazonRow.answer).toBe("$220");
    expect(amazonRow.percent).toBe("96%");

    const amazonCardHtml = renderCard(
      71579121,
      "How high will Amazon finish the week?",
      AMAZON_71579121_POINTS,
    );
    expect(cardCaption(amazonCardHtml)).toBe("$235");
    expect(highlightedRungs(amazonCardHtml)).toEqual(["$220"]);

    // 10-rung "Above N" comparator remains clipped to 8 rungs on compact row
    const comparator10: Point[] = Array.from({ length: 10 }, (_, idx) => {
      const thresh = 50 + idx;
      return {
        label: `Above ${thresh}`,
        value: thresh,
        probability: idx < 8 ? 0.65 - idx * 0.01 : idx === 8 ? 0.52 : 0.40,
        unit: null,
        source: "outcome",
      };
    });
    const compRow = renderCompactRow(
      878899,
      "Temperature tomorrow",
      comparator10,
      [
        { name: "Above 50", probability: 0.65 },
        { name: "Above 51", probability: 0.64 },
        { name: "Above 52", probability: 0.63 },
      ],
    );
    // First 8 rungs stop at "Above 57" (last >= 50% in first 8) instead of reaching "Above 58".
    expect(compRow.answer).toBe("Above 57");
  });
});
