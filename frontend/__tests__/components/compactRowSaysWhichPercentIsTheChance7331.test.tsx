/**
 * #7331 — A BUNDLE ROW WHOSE ANSWER IS A QUANTITY SAYS WHICH PERCENT IS THE CHANCE.
 *
 * ── WHAT A READER SAW ───────────────────────────────────────────────────────
 *
 * Page one at 390px, 2026-09-19 19:4xZ, edition `d7d6f255e5687729`, the FED &
 * RATES bundle, verbatim from `tools/discover-card-by-text.mjs`:
 *
 *     Fed decision in Oct 2026?
 *     Hike 25bps leads at 55%, up 52 points since Feb 19        55%
 *     September Inflation US - Annual
 *     New favorite: 3.6% (41%)                                  41%
 *     Core CPI YoY - September 2026
 *     2.4% · Resolves within a month                            41%
 *
 * Row 3 prints an inflation RATE and a PROBABILITY on one line with a `·` and
 * eight inches of whitespace between them, and says which is which for neither.
 * The `2.4%` is #4396's own fix — the row used to name no answer at all — and it
 * is right whenever the answer is a word. It collapses when the answer is itself
 * a quantity, which is what this file is about.
 *
 * Rows 1 and 2 are the reason the repair is not unconditional: row 1's answer is
 * the word `Hike 25bps`, and row 2's caption already names its `3.6%` (that row
 * is the BACKEND door of the same issue, repaired in `feed_reasons.py`). Neither
 * may gain a word from this door.
 *
 * ── THE SPECIMEN IS THE SERVED OBJECT ───────────────────────────────────────
 *
 * `__tests__/fixtures/compactRowChanceWord7331.json` is that bundle exactly as
 * `GET /api/feed?limit=100` returned it, prices and captions untouched, plus the
 * ROTTEN TOMATOES bundle — four rows whose answer is the quantity `Above 45`,
 * which states its own unit and must come through byte-identical — plus the
 * census of every compact row the same response served, each row carrying its
 * four caption doors verbatim so the census arm runs the real
 * `feedContextSnippet` chain rather than a caption this capture derived.
 *
 * ── WHY IT ENTERS AT `DiscoverCard` ─────────────────────────────────────────
 *
 * The claim is about what a reader sees on page one, and page one routes a
 * bundle through `DiscoverCard -> ThemeBundleCard -> FuturesCompactRow`. It is
 * also the only way to see the defect at all: the word and the percentage it
 * qualifies are in one component and the answer label is in another, so a unit
 * test of either predicate passes on every day this was live.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedBundleData, FeedItem } from "@/lib/types";
import { feedContextSnippet } from "@/components/discover/utils";
import { heroOutcome } from "@/lib/discover/heroOutcome";
import { answerIsBareQuantity, rowAnswerLabel } from "@/lib/discover/rowAnswerLabel";
import fixture from "../fixtures/compactRowChanceWord7331.json";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import DiscoverCard from "../../components/DiscoverCard";

/** A served bundle, deep-copied so an arm cannot leak into the next. */
function bundle(key: "fed_and_rates" | "rotten_tomatoes"): FeedItem {
  return JSON.parse(JSON.stringify((fixture.bundles as Record<string, unknown>)[key])) as FeedItem;
}

function render(item: FeedItem): string {
  return renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item }} positionIndex={0} />);
}

/**
 * The text a reader sees in `fragment` — every run of characters outside a tag.
 *
 * 🔴 NOT `replace(/<[^>]+>/g, "")`: that is the shape of an HTML sanitizer and
 * CodeQL rules it a high-severity `js/incomplete-multi-character-sanitization`
 * (the sibling #4396 file carries the alert number). Walking `<`/`>` by index is
 * the same reading with nothing sanitizer-shaped in it.
 *
 * Whitespace is COLLAPSED, not stripped, because the space before `chance` is
 * part of what is under test — it is what makes the link's accessible name read
 * "41% chance" rather than "41%chance".
 */
function visibleText(fragment: string): string {
  let out = "";
  let i = 0;
  for (;;) {
    const open = fragment.indexOf("<", i);
    out += open < 0 ? fragment.slice(i) : fragment.slice(i, open);
    if (open < 0) break;
    const close = fragment.indexOf(">", open);
    if (close < 0) break;
    i = close + 1;
  }
  return out.replace(/\s+/g, " ").trim();
}

/** Everything a reader reads on the row whose question is `question`. */
function rowText(html: string, question: string): string {
  const at = html.indexOf(question);
  if (at < 0) throw new Error(`the render never printed the row "${question}"`);
  const rest = html.slice(at);
  const end = rest.indexOf("</a>");
  return visibleText(rest.slice(0, end < 0 ? undefined : end));
}

const CORE_CPI = "Core CPI YoY - September 2026";
const INFLATION = "September Inflation US - Annual";
const DECISION = "Fed decision in Oct 2026?";
const DIGGER = "Digger · Rotten Tomatoes score";

describe("#7331 — the compact row says which of its percentages is the chance", () => {
  it("is rendering the real served bundle, collapsed, with all three rows", () => {
    // A fixture that lost its members would make every arm below vacuous.
    const html = render(bundle("fed_and_rates"));
    expect(html).toContain(DECISION);
    expect(html).toContain(INFLATION);
    expect(html).toContain(CORE_CPI);
    expect(html).toContain("2.4%");
  });

  it("the row that printed `2.4% … 41%` now says which 41 is the chance", () => {
    expect(rowText(render(bundle("fed_and_rates")), CORE_CPI)).toBe(
      "Core CPI YoY - September 20262.4% · Resolves within a month41% chance",
    );
  });

  it("the space is in the TEXT, so the link does not read `41%chance`", () => {
    // A margin would satisfy the eye and leave the accessible name wrong; this
    // is the assertion that refuses that repair.
    const row = rowText(render(bundle("fed_and_rates")), CORE_CPI);
    expect(row).toContain("41% chance");
    expect(row).not.toContain("41%chance");
  });

  it("CONTROL — the row whose answer is a WORD gains nothing", () => {
    expect(rowText(render(bundle("fed_and_rates")), DECISION)).toBe(
      "Fed decision in Oct 2026?Hike 25bps leads at 55%, up 52 points since Feb 1955%",
    );
  });

  it("CONTROL — the row the BACKEND door repairs is untouched by this one", () => {
    // `New favorite: 3.6% (41%)` already names its answer, so #4396's label is
    // silent here and this door must be too — otherwise one bundle prints the
    // word twice on one row and the fix reads as noise.
    expect(rowText(render(bundle("fed_and_rates")), INFLATION)).toBe(
      "September Inflation US - AnnualNew favorite: 3.6% (41%)41%",
    );
  });

  it("CONTROL — a quantity answer that PREFIXES A WORD states its own unit and is left alone", () => {
    // `Above 45` is the shape 5 of the 6 labelled rows on this feed carry. It is
    // the whole reason the predicate is "a digit and no letter" rather than
    // "contains a digit", and without this arm "say chance everywhere" passes.
    const html = render(bundle("rotten_tomatoes"));
    expect(rowText(html, DIGGER)).toBe("Digger · Rotten Tomatoes scoreAbove 45 · Resolves within a month87%");
    expect(html).not.toContain("compact-row-chance");
  });

  it("reads the answer off the payload rather than holding one for this question", () => {
    // Reprice Core CPI so a NAMED range leads: the ambiguity is gone with it.
    const item = bundle("fed_and_rates");
    const members = (item.data as unknown as FeedBundleData).items as unknown as FeedItem[];
    const cpi = members.find((m) => (m.data as { name: string }).name === CORE_CPI)!;
    const outcomes = (cpi.data as unknown as { top_outcomes: { name: string; probability: number; rendered_percent?: number }[] }).top_outcomes;
    outcomes[0].name = "Above 2.5%";

    const row = rowText(render(item), CORE_CPI);
    expect(row).toContain("Above 2.5%");
    expect(row).not.toContain("chance");
  });

  it("and the other way: a control row repriced to a bare quantity gains the word", () => {
    // The pair above and below is what stops the predicate being pinned to the
    // one question that reported the bug.
    const item = bundle("rotten_tomatoes");
    const members = (item.data as unknown as FeedBundleData).items as unknown as FeedItem[];
    const digger = members.find((m) => (m.data as { name: string }).name === DIGGER)!;
    const outcomes = (digger.data as unknown as { top_outcomes: { name: string }[] }).top_outcomes;
    outcomes[0].name = "45";

    expect(rowText(render(item), DIGGER)).toBe("Digger · Rotten Tomatoes score45 · Resolves within a month87% chance");
  });

  it("never qualifies a dash, because there is no percentage there to qualify", () => {
    const item = bundle("fed_and_rates");
    const members = (item.data as unknown as FeedBundleData).items as unknown as FeedItem[];
    const cpi = members.find((m) => (m.data as { name: string }).name === CORE_CPI)!;
    const data = cpi.data as unknown as { top_outcomes: { name: string; probability: number | null; rendered_percent?: number | null }[] };
    data.top_outcomes[0].probability = null;
    data.top_outcomes[0].rendered_percent = null;

    const row = rowText(render(item), CORE_CPI);
    expect(row).toContain("—");
    expect(row).not.toContain("chance");
  });

  describe("the production census", () => {
    interface CensusRow {
      bundle: string;
      question: string;
      hero_outcome: string | null;
      rendered_percent: number | null;
      context_summary: string | null;
      headline: string | null;
      reason: string | null;
      hook_description: string | null;
      top_outcomes: { name: string; probability: number }[];
    }
    const CENSUS = fixture.compact_row_census as CensusRow[];

    /** The real chain a row goes through, run over the four served doors. */
    function decide(row: CensusRow): { label: string | null; word: boolean } {
      const item = {
        type: "futures",
        context_summary: row.context_summary,
        headline: row.headline,
        reason: row.reason,
        data: { name: row.question, hook_description: row.hook_description },
      } as unknown as FeedItem;
      const label = rowAnswerLabel(heroOutcome(row.top_outcomes), feedContextSnippet(item));
      return { label, word: answerIsBareQuantity(label) };
    }

    it("is every compact row page one served, not a hand-picked sample", () => {
      expect(CENSUS).toHaveLength(22);
      expect(fixture.edition).toBe("d7d6f255e5687729");
    });

    it("spends the word on exactly one of the 22, and it is the row a reader could not read", () => {
      const said = CENSUS.filter((r) => decide(r).word).map((r) => r.question);
      expect(said).toEqual([CORE_CPI]);
    });

    it("CONTROL — the census really does contain quantity answers that keep their silence", () => {
      // Five `Above 5` / `Above 45` rows. If page one ever stops serving them the
      // arm above proves nothing and this fixture is a dated capture to re-cut —
      // a suppression rule proved on a population with nothing to suppress is
      // not proved at all.
      const quantities = CENSUS.filter((r) => decide(r).label !== null && /\d/.test(decide(r).label!));
      const silent = quantities.filter((r) => !decide(r).word).map((r) => r.hero_outcome);
      expect(silent).toEqual(["Above 5", "Above 45", "Above 45", "Above 45", "Above 45"]);
    });
  });
});
