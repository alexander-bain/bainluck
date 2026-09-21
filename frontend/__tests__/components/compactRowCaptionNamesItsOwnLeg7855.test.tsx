/**
 * #7855 — A BUNDLE ROW'S CAPTION IS ABOUT THE LEG ITS PERCENTAGE IS FOR.
 *
 * ── WHAT A READER SAW ───────────────────────────────────────────────────────
 *
 * Page one at 390px, 2026-09-21 18:55Z, edition `9c0cbec4350ab587`, card 6, the
 * AI bundle, verbatim from the rendered row:
 *
 *     Best AI at the end of 2026?
 *     Claude leads at 72%                                       72%
 *     GPT Astra 6.1+ released?
 *     December 31 · October 31 up 20 points today               94%
 *
 * Row 2 carries two dates, one separator, one movement and one percentage, and
 * nothing on the line says which date the 94% is for. The two dates are two
 * different legs of a cumulative ladder: `December 31` is the outcome the 94%
 * belongs to (#4396's label), `October 31` is a different outcome at 63%, and
 * the "20 points" in the sentence belongs to neither number on the row.
 *
 * Row 1 is why the repair is not unconditional: its caption names its own hero,
 * so the number is already tied and #4396's label is already silent.
 *
 * ── THE SPECIMEN IS THE SERVED OBJECT ───────────────────────────────────────
 *
 * `__tests__/fixtures/compactRowCaptionLeg7855.json` is that bundle exactly as
 * `GET /api/feed?limit=200` returned it, prices and captions untouched, plus
 * three control bundles — AWARDS SEASON and FED & RATES each carry a row whose
 * caption names another leg AND its own hero, which is the widening control
 * this door must not touch, and MIDDLE EAST carries a row with the same
 * bare-date label as the defect and a caption about its own odds — plus the
 * census of every compact row that response served, each row carrying its four
 * caption doors verbatim so the census arm runs the real `feedContextSnippet`
 * chain rather than a caption this capture derived.
 *
 * ── WHY IT ENTERS AT `DiscoverCard` ─────────────────────────────────────────
 *
 * The claim is about what a reader sees on page one, and page one routes a
 * bundle through `DiscoverCard -> ThemeBundleCard -> FuturesCompactRow`. The
 * label and the caption are composed in that row from two different modules,
 * so a unit test of either predicate passes on every day this was live.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedBundleData, FeedFuturesData, FeedItem } from "@/lib/types";
import { feedContextSnippet } from "@/components/discover/utils";
import { heroOutcome } from "@/lib/discover/heroOutcome";
import { captionIsAboutAnotherLeg, rowAnswerLabel } from "@/lib/discover/rowAnswerLabel";
import fixture from "../fixtures/compactRowCaptionLeg7855.json";

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
import { FuturesCompactRow } from "@/components/discover/FuturesCard";

type BundleKey = "ai" | "awards_season" | "fed_and_rates" | "middle_east";

/** A served bundle, deep-copied so an arm cannot leak into the next. */
function bundle(key: BundleKey): FeedItem {
  return JSON.parse(JSON.stringify((fixture.bundles as Record<string, unknown>)[key])) as FeedItem;
}

function members(item: FeedItem): FeedItem[] {
  return (item.data as unknown as FeedBundleData).items as unknown as FeedItem[];
}

function member(item: FeedItem, question: string): FeedItem {
  const found = members(item).find((m) => (m.data as { name: string }).name === question);
  if (!found) throw new Error(`the fixture bundle has no member "${question}"`);
  return found;
}

function render(item: FeedItem): string {
  return renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item }} positionIndex={0} />);
}

/**
 * One member row on its own.
 *
 * A collapsed bundle peeks `BUNDLE_PEEK_COUNT` = 5 rows, and two of the rows
 * this file needs are the SIXTH of their bundle — reachable by a reader who
 * expands, unreachable by `renderToStaticMarkup`, which cannot open a client
 * component's state. They enter here rather than being reordered into the peek:
 * the fixture is the served object, and a re-cut capture must keep proving the
 * same thing. Everything above enters at `DiscoverCard`, which is the page-one
 * path; this is the same component that path arrives at.
 */
function renderRow(item: FeedItem): string {
  return renderToStaticMarkup(<FuturesCompactRow item={item} data={item.data as FeedFuturesData} />);
}

/**
 * The text a reader sees in `fragment` — every run of characters outside a tag.
 *
 * 🔴 NOT `replace(/<[^>]+>/g, "")`: that is the shape of an HTML sanitizer and
 * CodeQL rules it a high-severity `js/incomplete-multi-character-sanitization`.
 * Walking `<`/`>` by index is the same reading with nothing sanitizer-shaped in
 * it. Whitespace is COLLAPSED, not stripped — the separator under test is a
 * spaced `·`.
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

const ASTRA = "GPT Astra 6.1+ released?";
const BEST_AI = "Best AI at the end of 2026?";
const SCREENPLAY = "Oscars 2027: Best Original Screenplay Winner";
const DECISION = "Fed decision in Oct 2026?";
const CORE_CPI = "Core CPI YoY - September 2026";
const JORDAN = "Will Iran target Jordan?";

describe("#7855 — the compact row's caption is about the leg its percentage is for", () => {
  it("is rendering the real served AI bundle, collapsed, with both rows", () => {
    // A fixture that lost its members would make every arm below vacuous.
    const html = render(bundle("ai"));
    expect(html).toContain(ASTRA);
    expect(html).toContain(BEST_AI);
    expect(html).toContain("94%");
  });

  it("the served row really is the two-leg one — 94% for December 31, the movement on October 31", () => {
    // The defect is a property of the PAYLOAD, so it is asserted rather than
    // described: if the feed ever stops serving this shape the arm below is
    // proving nothing and this fixture is a dated capture to re-cut.
    const astra = member(bundle("ai"), ASTRA);
    const outcomes = (astra.data as unknown as { top_outcomes: { name: string; probability: number }[] }).top_outcomes;
    expect(outcomes.map((o) => o.name)).toEqual(["December 31", "October 31"]);
    expect(feedContextSnippet(astra)).toBe("October 31 up 20 points today");
    expect(rowAnswerLabel(heroOutcome(outcomes), feedContextSnippet(astra))).toBe("December 31");
  });

  it("the row that printed `December 31 · October 31 up 20 points today` says one thing now", () => {
    expect(rowText(render(bundle("ai")), ASTRA)).toBe("GPT Astra 6.1+ released?December 3194%");
  });

  it("keeps the ANSWER, not the sentence — the number is still tied to an outcome", () => {
    // The other half of "drop one of them" would leave #4396's defect behind:
    // a 94% on a ladder with nothing saying which rung it is.
    const row = rowText(render(bundle("ai")), ASTRA);
    expect(row).toContain("December 31");
    expect(row).not.toContain("October 31");
  });

  it("CONTROL — the sibling row in the same bundle is byte-identical", () => {
    expect(rowText(render(bundle("ai")), BEST_AI)).toBe("Best AI at the end of 2026?Claude leads at 72%72%");
  });

  it("CONTROL — a caption that names another leg AND its own hero keeps every word", () => {
    // `Wild Horse Nine leads at 34%, The Debut up 25.8 points` names a second
    // leg, which is the literal trigger of this door — and it is FINE, because
    // it also names the number's own outcome, so #4396's label is silent and
    // there is nothing for a reader to mis-tie. This is the arm that fails if
    // the gate is moved off the printed label onto the hero.
    expect(rowText(renderRow(member(bundle("awards_season"), SCREENPLAY)), SCREENPLAY)).toBe(
      "Oscars 2027: Best Original Screenplay WinnerWild Horse Nine leads at 34%, The Debut up 25.8 points since Aug 634%",
    );
  });

  it("CONTROL — the same shape in a second bundle is byte-identical too", () => {
    expect(rowText(render(bundle("fed_and_rates")), DECISION)).toBe(
      "Fed decision in Oct 2026?Fed maintains rate at 50%, Hike 25bps up 47 points since Feb 1950%",
    );
  });

  it("CONTROL — a labelled row whose caption names no other leg keeps both halves", () => {
    expect(rowText(render(bundle("fed_and_rates")), CORE_CPI)).toBe(
      "Core CPI YoY - September 20262.4% · Resolves within a month45% chance",
    );
  });

  it("CONTROL — the SAME bare-date label, with a caption about its own odds, is untouched", () => {
    // `October 31` is the very string the defect row drops, printed here as the
    // label. A door that keyed on the date rather than on the relationship
    // would take this row's caption with it.
    expect(rowText(renderRow(member(bundle("middle_east"), JORDAN)), JORDAN)).toBe(
      "Will Iran target Jordan?October 31 · Odds down 6.5 points6 pts67%",
    );
  });

  it("reads the relationship off the payload rather than holding one for this question", () => {
    // Rename the mover to the hero's own outcome: the caption is now about the
    // number beside it, and #4396's label goes silent on its own.
    const item = bundle("ai");
    const astra = member(item, ASTRA);
    astra.headline = "December 31 up 20 points today";
    astra.context_summary = null;
    astra.reason = "";

    const row = rowText(render(item), ASTRA);
    expect(row).toBe("GPT Astra 6.1+ released?December 31 up 20 points today94%");
  });

  it("and the other way: a control row whose caption is rewritten onto another leg drops it", () => {
    // The pair above and below is what stops the predicate being pinned to the
    // one question that reported the bug.
    const jordan = member(bundle("middle_east"), JORDAN);
    const outcomes = (jordan.data as unknown as { top_outcomes: { name: string }[] }).top_outcomes;
    expect(outcomes.length).toBeGreaterThan(1);
    jordan.context_summary = `${outcomes[1].name} up 20 points today`;

    expect(rowText(renderRow(jordan), JORDAN)).toBe("Will Iran target Jordan?October 316 pts67%");
  });

  it("an ordinary English `No` in a caption is not read as a second leg", () => {
    // `No` is a word every third sentence contains. The row below is a real
    // served one repriced so its hero is a date and `No` is its sibling; the
    // caption must survive.
    const jordan = member(bundle("middle_east"), JORDAN);
    const outcomes = (jordan.data as unknown as { top_outcomes: { name: string }[] }).top_outcomes;
    outcomes[1].name = "No";
    jordan.context_summary = "No clear favorite yet";

    expect(rowText(renderRow(jordan), JORDAN)).toBe("Will Iran target Jordan?October 31 · No clear favorite yet6 pts67%");
  });

  describe("the production census", () => {
    interface CensusRow {
      bundle: string;
      question: string;
      hero_outcome: string | null;
      context_summary: string | null;
      headline: string | null;
      reason: string | null;
      hook_description: string | null;
      top_outcomes: { name: string; probability: number | null }[];
    }
    const CENSUS = fixture.compact_row_census as CensusRow[];

    /** The real chain a row goes through, run over the four served doors. */
    function decide(row: CensusRow): { label: string | null; dropped: boolean } {
      const item = {
        type: "futures",
        context_summary: row.context_summary,
        headline: row.headline,
        reason: row.reason,
        data: { name: row.question, hook_description: row.hook_description },
      } as unknown as FeedItem;
      const caption = feedContextSnippet(item);
      const label = rowAnswerLabel(heroOutcome(row.top_outcomes), caption);
      return { label, dropped: captionIsAboutAnotherLeg(caption, label, row.top_outcomes) };
    }

    it("is every compact row page one served, not a hand-picked sample", () => {
      expect(CENSUS).toHaveLength(33);
      expect(fixture.edition).toBe("9c0cbec4350ab587");
    });

    it("drops a caption on exactly one of the 33, and it is the row a reader could not read", () => {
      const dropped = CENSUS.filter((r) => decide(r).dropped).map((r) => r.question);
      expect(dropped).toEqual([ASTRA]);
    });

    it("CONTROL — the census really does contain captions that name a second leg and keep it", () => {
      // Two rows name another outcome and print no label. If page one ever
      // stops serving them, the arm above is a suppression rule proved on a
      // population with nothing to suppress.
      const namesASecondLeg = CENSUS.filter((r) => {
        const { label } = decide(r);
        return captionIsAboutAnotherLeg(captionOf(r), label ?? r.hero_outcome, r.top_outcomes);
      });
      expect(namesASecondLeg.map((r) => r.question)).toEqual([ASTRA, SCREENPLAY, DECISION]);
    });

    function captionOf(row: CensusRow): string {
      return feedContextSnippet({
        type: "futures",
        context_summary: row.context_summary,
        headline: row.headline,
        reason: row.reason,
        data: { name: row.question, hook_description: row.hook_description },
      } as unknown as FeedItem);
    }

    it("CONTROL — 10 of the 33 print a label at all, so the gate is not empty", () => {
      expect(CENSUS.filter((r) => decide(r).label !== null)).toHaveLength(10);
    });
  });
});
