/**
 * #9876 — a group row says which answer its number is for, and a title that
 * offers a choice shows every choice it offers.
 *
 * Two production specimens, 2026-09-30:
 *
 *   1. IPO VALUATION RANGES group, 390px, 17:05Z (futures 27367840):
 *
 *          Oura IPO Closing Market Cap
 *          No IPO before January 2027 leads at 85%              85%
 *
 *      The bold 85% is the chance Oura does NOT list. Only the grey caption
 *      said so, beside rows whose numbers are chances that something does
 *      happen. Alex: "83% Yes" beside "84% No" misleads when shown like
 *      comparable chances.
 *
 *   2. "Will AOC announce a run for Senate or President before 2028?"
 *      (futures 59159859, Senate 48% · President 41% · Neither 3%). The card
 *      headlined 48% over "Senate", the row printed 48% with "Senate leads at
 *      48%…", and President was on neither. Alex: "title promises two choices
 *      but only Senate is visible."
 *
 * Every case renders the real components from one payload. The unchanged
 * shapes at the bottom pin what must NOT move: the Yes/No swap (UX-P238), a
 * bare Yes, a caption-named positive answer, and a title whose "or" is not
 * between two of its outcomes.
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
import { answerIsNegative, rowAnswerLabel } from "../../lib/discover/rowAnswerLabel";
import { titleNamedChoices } from "../../lib/discover/titleNamedChoices";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

type Outcome = { name: string; probability: number | null; rendered_percent?: number };

function marketData(id: number, name: string, outcomes: Outcome[], outcomeCount = outcomes.length): FeedFuturesData {
  return {
    id,
    name,
    llm_sport_category: "politics",
    resolution_date: "2028-01-01T04:59:00Z",
    top_outcomes: outcomes.map((o, i) => ({ id: i + 1, rank: i + 1, movement: null, ...o })),
    outcome_count: outcomeCount,
    confidence_tier: "moderate",
    discover_card: { suggested_format: null },
  } as unknown as FeedFuturesData;
}

function itemFor(data: FeedFuturesData, caption: string): FeedItem {
  return { type: "futures", score: 90, reason: "", headline: caption, context_summary: caption, data } as unknown as FeedItem;
}

const text = (html: string, testid: string): string[] =>
  Array.from(html.matchAll(new RegExp(`data-testid="${testid}">(.*?)</(?:span|div)>`, "g")), (m) =>
    m[1].replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").trim(),
  );

function row(data: FeedFuturesData, caption: string) {
  const html = renderToStaticMarkup(<FuturesCompactRow item={itemFor(data, caption)} data={data} />);
  return {
    answer: text(html, "compact-row-answer")[0] ?? null,
    others: Array.from(html.matchAll(/data-testid="compact-row-other-choice"><span[^>]*> · <\/span>([^<]*)<\/span>/g), (m) => m[1].trim()),
    percent: text(html, "compact-row-percent")[0] ?? null,
    caption: html.includes(caption),
  };
}

function cardHeroName(data: FeedFuturesData, caption: string): string[] {
  const html = renderToStaticMarkup(
    <FuturesCard item={itemFor(data, caption)} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
  return text(html, "futures-hero-outcome");
}

// ── Specimens, as stored/served 2026-09-30 ──

const AOC_CAPTION = "Senate leads at 48%, up 27 points since Aug 18";
const AOC = marketData(59159859, "Will AOC announce a run for Senate or President before 2028?", [
  { name: "Senate", probability: 0.48 },
  { name: "President", probability: 0.41 },
  { name: "Neither", probability: 0.0265 },
]);

const OURA_CAPTION = "No IPO before January 2027 leads at 85%";
const OURA = marketData(
  27367840,
  "Oura IPO Closing Market Cap",
  [
    { name: "No IPO before January 2027", probability: 0.847, rendered_percent: 85 },
    { name: "$15B–$17.5B", probability: 0.0425, rendered_percent: 4 },
    { name: "$20B+", probability: 0.0335, rendered_percent: 3 },
  ],
  8,
);

describe("#9876 — a negative answer is named in bold on the row", () => {
  it("Oura: the row prints 'No IPO before January 2027' beside its 85%, and drops the caption that only repeated it", () => {
    expect(row(OURA, OURA_CAPTION)).toEqual({
      answer: "No IPO before January 2027",
      others: [],
      percent: "85%",
      caption: false,
    });
  });

  it("a binary whose Yes side has no price names 'No' even when the caption says 'no' in passing", () => {
    const data = marketData(1, "Discord IPO before 2027?", [
      { name: "No", probability: 0.84 },
      { name: "Yes", probability: null },
    ]);
    const r = row(data, "No clear move this week");
    expect(r.answer).toBe("No");
    expect(r.percent).toBe("84%");
    // The caption says something the bold answer does not, so it stays.
    expect(r.caption).toBe(true);
  });

  it("answerIsNegative: the marker needs a word boundary, so 'Norway' and 'No. 1 seed' are answers, not negations", () => {
    for (const n of ["No", "No IPO before January 2027", "Not Neuralink's valuation", "No: Onslaught scores 80", "Neither", "None"]) {
      expect(answerIsNegative(n)).toBe(true);
    }
    for (const n of ["Norway", "No. 1 seed", "Notre Dame", "Yes", "None of the above", "Senate"]) {
      expect(answerIsNegative(n)).toBe(false);
    }
  });
});

describe("#9876 — a title that offers a choice shows every choice it offers", () => {
  it("AOC row: **Senate** · President 41%, beside 48%", () => {
    expect(row(AOC, AOC_CAPTION)).toEqual({
      answer: "Senate",
      others: ["President 41%"],
      percent: "48%",
      caption: false,
    });
  });

  it("AOC card: the hero's name line carries President with its own number", () => {
    expect(cardHeroName(AOC, AOC_CAPTION)).toEqual(["Senate · President 41%"]);
  });

  it("the other choice is only a choice the market serves. Neither is not named, so it is not added", () => {
    expect(titleNamedChoices(AOC.name, AOC.top_outcomes, AOC.top_outcomes[0]).map((o) => o.name)).toEqual([
      "President",
    ]);
  });

  it("a choice with no price is left off, not printed as a dash", () => {
    const data = marketData(2, "Will AOC announce a run for Senate or President before 2028?", [
      { name: "Senate", probability: 0.48 },
      { name: "President", probability: null },
    ]);
    const r = row(data, AOC_CAPTION);
    expect(r.others).toEqual([]);
    expect(cardHeroName(data, AOC_CAPTION)).toEqual(["Senate"]);
  });
});

describe("#9876 — unchanged shapes", () => {
  it("a Yes/No pair still reads as the Yes side with no label (UX-P238's swap is untouched)", () => {
    const data = marketData(3, "OpenAI IPO before 2027?", [
      { name: "No", probability: 0.9745 },
      { name: "Yes", probability: 0.0255 },
    ]);
    const r = row(data, "Resolves within a quarter");
    expect(r.answer).toBeNull();
    expect(r.percent).toBe("3%");
  });

  it("a positive answer the caption already names keeps #4396's no-duplicate rule", () => {
    expect(rowAnswerLabel({ name: "Hike 25bps", probability: 0.56 }, "Hike 25bps leads at 56%")).toBeNull();
  });

  it("a title whose names are not joined by 'or' is not a choice", () => {
    const data = marketData(4, "Will Anthropic and OpenAI both IPO in 2026?", [
      { name: "Anthropic", probability: 0.5 },
      { name: "OpenAI", probability: 0.3 },
    ]);
    expect(titleNamedChoices(data.name, data.top_outcomes, data.top_outcomes[0])).toEqual([]);
    expect(cardHeroName(data, "")).toEqual(["Anthropic"]);
  });

  it("a hero the title does not name keeps the existing label and adds nothing", () => {
    const data = marketData(5, "Will AOC announce a run for Senate or President before 2028?", [
      { name: "Neither", probability: 0.6 },
      { name: "Senate", probability: 0.25 },
      { name: "President", probability: 0.15 },
    ]);
    expect(titleNamedChoices(data.name, data.top_outcomes, data.top_outcomes[0])).toEqual([]);
    expect(row(data, "").answer).toBe("Neither");
  });
});
