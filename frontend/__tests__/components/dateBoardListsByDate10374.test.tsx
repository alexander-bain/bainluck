/**
 * #10374 — A DATE QUESTION'S BOARD LISTS ITS DAYS IN DATE ORDER (Alex, rage shake 170).
 *
 * 🔴 THE READER. `Next Claude Haiku (4.6+) released on...?` (market 63522622)
 * drew its four rows by probability:
 *
 *      1  October 27   14%
 *      2  October 12   14%
 *      3  October 14   13%
 *      4  October 28   13%
 *
 * Alex: "These date oriented cards should be shown in chronological order ...
 * even if that is the true descending order of the probabilities." The producer
 * half (discover, PR #10377) serves `distribution_order: "chronological"` and a
 * per-row ISO `date` (null on the "No release by…" residual) while keeping the
 * list itself in probability order. This is the consumer half.
 *
 * ═══ WHAT MUST HOLD ═══
 *
 *  (a) WHICH rows are drawn is unchanged — the leader-first four (#1526). The
 *      favourite never falls off for being late in the month.
 *  (b) Those four are listed earliest first; a null-dated residual goes last.
 *  (c) The crown (weight + brand bar) sits on the max-probability row, wherever
 *      it lands in the list — never on index 0.
 *  (d) No rank digits on that board (`1 2` beside `Oct 12 · Oct 14` read as ranks).
 *
 * ═══ THE CONTROL EXERCISES THE OPPOSITE BRANCH ═══
 *
 * Every arm runs against ONE fixture rendered twice, differing in ONE key:
 * `distribution_order: "chronological"` vs `"probability"`. The probability arm
 * must render exactly today's podium (probability order, digits 1–4, crown on
 * row 0) — it is what reds if the reorder over-fires onto boards that are not
 * date questions.
 *
 * Fixture rows are the specimen's stored prices (`futures_outcomes`,
 * 2026-10-03 ~21:4xZ), dated as the producer dates them against the market's
 * `resolution_date` 2026-11-01.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedFuturesData, FeedItem } from "@/lib/types";
import { boardRowRanks, futuresDistributionBoard } from "@/lib/discover/futuresBoard";

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
import { FuturesCard } from "../../components/discover/FuturesCard";

const RESIDUAL = "No release by October 31";

/** The specimen's top ten as stored, in the probability order the route serves. */
function haikuRows(residualProbability: number, octoberTwelve: number) {
  const rows = [
    { label: "October 27", probability: 0.14, date: "2026-10-27" },
    { label: "October 12", probability: octoberTwelve, date: "2026-10-12" },
    { label: "October 14", probability: 0.13, date: "2026-10-14" },
    { label: "October 28", probability: 0.125, date: "2026-10-28" },
    { label: "October 13", probability: 0.12, date: "2026-10-13" },
    { label: "October 5", probability: 0.102, date: "2026-10-05" },
    { label: "October 6", probability: 0.1, date: "2026-10-06" },
    { label: RESIDUAL, probability: residualProbability, date: null },
    { label: "October 15", probability: 0.095, date: "2026-10-15" },
    { label: "October 21", probability: 0.09, date: "2026-10-21" },
  ];
  return [...rows]
    .sort((a, b) => b.probability - a.probability)
    .map((row) => ({ ...row, movement: null }));
}

function haikuData(
  order: "chronological" | "probability",
  { residual = 0.095, octoberTwelve = BEATEN }: { residual?: number; octoberTwelve?: number } = {},
): FeedFuturesData {
  const rows = haikuRows(residual, octoberTwelve);
  return {
    id: 63522622,
    name: "Next Claude Haiku (4.6+) released on...?",
    llm_sport_category: "tech",
    sport_name: null,
    status: "open",
    source: "kalshi",
    source_count: 1,
    market_tier: 2,
    confidence_tier: "moderate",
    resolution_date: "2026-11-01T03:59:00+00:00",
    outcome_count: 32,
    top_outcomes: rows.slice(0, 3).map((row, i) => ({
      id: 900000 + i,
      rank: i + 1,
      name: row.label,
      probability: row.probability,
      movement: null,
    })),
    discover_card: {
      suggested_format: "outcome_distribution",
      distribution_outcomes: rows,
      remaining_outcome_count: 22,
      field_is_a_race: true,
      distribution_order: order,
    },
  } as unknown as FeedFuturesData;
}

function itemFor(data: FeedFuturesData): FeedItem {
  return {
    type: "futures",
    score: 80,
    reason: "October 27 (14%) in Next Claude Haiku (4.6+) released on...?",
    headline: "October 27 at 14%",
    data,
  } as unknown as FeedItem;
}

const discoverHtml = (data: FeedFuturesData) =>
  renderToStaticMarkup(
    <FuturesCard item={itemFor(data)} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
const browseHtml = (data: FeedFuturesData) => renderToStaticMarkup(<FeedCard item={itemFor(data)} />);

/**
 * The board's own markup: from its `data-card-format` marker on. The browse card
 * also prints the leader's name with a `title` in its headline, above the board,
 * so a document-wide read would count that as a row.
 */
function boardMarkup(markup: string): string {
  const at = markup.search(/data-card-format="(leaderboard|board)"/);
  if (at === -1) throw new Error("no board rendered");
  return markup.slice(at);
}

/** Board row labels in render order — each row opens on `title="<label>"`. */
function drawnLabels(page: string, candidates: string[]): string[] {
  const markup = boardMarkup(page);
  return candidates
    .map((label) => ({ label, at: markup.indexOf(`title="${label}"`) }))
    .filter(({ at }) => at !== -1)
    .sort((a, b) => a.at - b.at)
    .map(({ label }) => label);
}

function rowIsCrowned(page: string, label: string): boolean {
  const markup = boardMarkup(page);
  const start = markup.indexOf(`title="${label}"`);
  if (start === -1) return false;
  const next = markup.indexOf('title="', start + 1);
  return markup.slice(start, next === -1 ? undefined : next).includes("bg-accent-brand");
}

function renderedRanks(markup: string): number[] {
  return [...markup.matchAll(/aria-label="Rank (\d+)"/g)].map((m) => Number(m[1]));
}

function valueCells(markup: string): string[] {
  return [...markup.matchAll(/tabular-nums[^>]*>([^<]*)</g)]
    .map((m) => m[1])
    .filter((c) => c.endsWith("%"));
}

/**
 * October 12's price is the ONE number that moves between the two crown arms.
 * As stored it is 0.138 — it prints 14% beside October 27's 14%, so #8112's
 * dead-heat rule co-crowns both, and October 12 is ALSO the first row listed by
 * date. That arm cannot tell "crown the favourite" from "crown index 0". At
 * 0.128 (prints 13%) October 27 leads alone and October 12, still listed first,
 * must not wear the crown — that is the arm a crown-by-index regression reds.
 */
const STORED = 0.138;
const BEATEN = 0.128;

const ALL_LABELS = haikuRows(0.095, STORED).map((row) => row.label);
/** With October 12 at 0.128 it sits below October 14 (0.13) by probability. */
const PROBABILITY_ORDER = ["October 27", "October 14", "October 12", "October 28"];
const DATE_ORDER = ["October 12", "October 14", "October 27", "October 28"];

// ─────────────────────────────────────────────────────────────────────────────
describe("#10374 — the shared board rule", () => {
  it("keeps the leader-first four and lists them by date", () => {
    const board = futuresDistributionBoard(haikuData("chronological"))!;
    expect(board.chronological).toBe(true);
    expect(board.rows.map((r) => r.label)).toEqual(DATE_ORDER);
    // Crown by probability: October 27 is third in the list and still rank 1.
    // The three 13% rows share rank 2 (#8112 competition ranking on the printed
    // string), and none of them is rank 1 for being listed first.
    expect(boardRowRanks(board)).toEqual([2, 2, 1, 2]);
  });

  it("as stored, the two level 14% rows share the crown wherever they are listed (#8112)", () => {
    const board = futuresDistributionBoard(haikuData("chronological", { octoberTwelve: STORED }))!;
    expect(board.rows.map((r) => r.label)).toEqual(DATE_ORDER);
    expect(boardRowRanks(board)).toEqual([1, 3, 1, 3]);
  });

  it("lists an undated residual LAST when it is one of the four drawn", () => {
    // 0.135 puts "No release by October 31" second in the leader-first cut and
    // pushes October 28 off it.
    const board = futuresDistributionBoard(haikuData("chronological", { residual: 0.135 }))!;
    expect(board.rows.map((r) => r.label)).toEqual(["October 12", "October 14", "October 27", RESIDUAL]);
  });

  it("control: a probability board is today's board, untouched", () => {
    const board = futuresDistributionBoard(haikuData("probability"))!;
    expect(board.chronological).toBe(false);
    expect(board.rows.map((r) => r.label)).toEqual(PROBABILITY_ORDER);
    expect(boardRowRanks(board)).toEqual([1, 2, 2, 2]);
  });

  it("an absent `distribution_order` is a probability board", () => {
    const data = haikuData("chronological");
    delete (data as unknown as { discover_card: Record<string, unknown> }).discover_card.distribution_order;
    expect(futuresDistributionBoard(data)!.rows.map((r) => r.label)).toEqual(PROBABILITY_ORDER);
  });
});

describe("#10374 — #8033's pair repair travels with its row", () => {
  // A date board whose top two are a complement pair whose own roundings print
  // 59 + 42 = 101: #8033 derives the runner-up as 41. Listed by date the pair
  // lands at positions 1 and 2, so the repaired 41 must stay on October 10 and
  // never be painted onto October 5 by index.
  const pair = haikuData("chronological");
  (pair as unknown as { discover_card: { distribution_outcomes: unknown[]; remaining_outcome_count: number } })
    .discover_card.distribution_outcomes = [
    { label: "October 20", probability: 0.585, date: "2026-10-20", movement: null },
    { label: "October 10", probability: 0.415, date: "2026-10-10", movement: null },
    { label: "October 5", probability: 0.004, date: "2026-10-05", movement: null },
    { label: "October 30", probability: 0.003, date: "2026-10-30", movement: null },
  ];
  (pair as unknown as { discover_card: { remaining_outcome_count: number } }).discover_card.remaining_outcome_count = 0;

  it("prints 59 on October 20 and the repaired 41 on October 10, in date order", () => {
    const markup = discoverHtml(pair);
    expect(drawnLabels(markup, ["October 20", "October 10", "October 5", "October 30"])).toEqual([
      "October 5",
      "October 10",
      "October 20",
      "October 30",
    ]);
    expect(valueCells(markup)).toEqual(["&lt;1%", "41%", "59%", "&lt;1%"]);
    expect(rowIsCrowned(markup, "October 20")).toBe(true);
    expect(rowIsCrowned(markup, "October 5")).toBe(false);
  });
});

describe("#10374 — the Discover card", () => {
  const chrono = discoverHtml(haikuData("chronological"));
  const control = discoverHtml(haikuData("probability"));

  it("lists the same four days earliest first, with the same percentages", () => {
    expect(drawnLabels(chrono, ALL_LABELS)).toEqual(DATE_ORDER);
    expect(valueCells(chrono)).toEqual(["13%", "13%", "14%", "13%"]);
  });

  it("as stored: Oct 12 · 14 · 27 · 28 at 14% · 13% · 14% · 13%, both 14% rows crowned", () => {
    const stored = discoverHtml(haikuData("chronological", { octoberTwelve: STORED }));
    expect(drawnLabels(stored, ALL_LABELS)).toEqual(DATE_ORDER);
    expect(valueCells(stored)).toEqual(["14%", "13%", "14%", "13%"]);
    expect(rowIsCrowned(stored, "October 12")).toBe(true);
    expect(rowIsCrowned(stored, "October 27")).toBe(true);
    expect(rowIsCrowned(stored, "October 14")).toBe(false);
    expect(renderedRanks(stored)).toEqual([]);
  });

  it("puts the crown on October 27 (the favourite), not on the first row", () => {
    expect(rowIsCrowned(chrono, "October 27")).toBe(true);
    expect(rowIsCrowned(chrono, "October 12")).toBe(false);
    expect(rowIsCrowned(chrono, "October 14")).toBe(false);
    expect(rowIsCrowned(chrono, "October 28")).toBe(false);
  });

  it("draws no rank digits, and keeps the remainder sentence", () => {
    expect(renderedRanks(chrono)).toEqual([]);
    expect(chrono).toContain("Field and 28 more outcomes");
    expect(chrono).toContain('data-row="field-remainder"');
  });

  it("control: the probability board keeps its podium exactly", () => {
    expect(drawnLabels(control, ALL_LABELS)).toEqual(PROBABILITY_ORDER);
    expect(renderedRanks(control)).toEqual([1, 2, 2, 2]);
    expect(rowIsCrowned(control, "October 27")).toBe(true);
    expect(rowIsCrowned(control, "October 12")).toBe(false);
  });
});

describe("#10374 — the browse card reads the same board (notice 35)", () => {
  const chrono = browseHtml(haikuData("chronological"));
  const control = browseHtml(haikuData("probability"));

  it("lists by date and crowns the favourite", () => {
    expect(drawnLabels(chrono, ALL_LABELS)).toEqual(DATE_ORDER);
    expect(rowIsCrowned(chrono, "October 27")).toBe(true);
    expect(rowIsCrowned(chrono, "October 12")).toBe(false);
  });

  it("control: the probability board is unchanged", () => {
    expect(drawnLabels(control, ALL_LABELS)).toEqual(PROBABILITY_ORDER);
    expect(rowIsCrowned(control, "October 27")).toBe(true);
  });
});
