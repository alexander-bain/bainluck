/**
 * #4122 — NO DIAGNOSTIC PROSE ON THE TOURNAMENT PAGE (standing notice 34).
 *
 * ═══ THE RULING ═══
 *
 * Alex, Tue 2026-09-08 4:00pm PT, looking at `/tournaments/us-open`: *"all the
 * grey text is madness, and shouldn't be user-facing at all."* Notice 34 turned
 * that into a rule with three named kinds and an example of each:
 *
 *   • coverage counts       — *"shown on 121 of 152"*
 *   • limitations           — *"31 are fixtures we could not tie to a market of ours"*
 *   • method notes          — *"last number is when we last saw…"*,
 *                             *"we mark a number when the market behind it is barely traded…"*
 *
 * ALL THREE EXAMPLES WERE TRANSCRIBED OFF THIS PAGE. That is why the guard
 * lives here rather than anywhere else: the components below rendered, on
 * production, the literal strings the ruling quotes.
 *
 * The positive half of notice 34 is the other thing this file protects: *"A
 * reader sees the number, the small source mark (D91), and at most one short
 * caption."* So every case asserts a REMOVAL beside a SURVIVAL — the numbers,
 * the marks and the scores are still drawn. A component that rendered nothing
 * at all would satisfy a banned-phrase list, and that is the obvious way for
 * this guard to pass while the page is broken.
 *
 * ═══ WHY IT READS TEXT AND NOT TESTIDS ═══
 *
 * #4122's acceptance asks for a guard *"keyed on the rendered text rather than
 * on a testid that can be renamed"*. The sibling suites already assert the
 * testids are absent; those catch a revert. They do NOT catch the likelier
 * regression — somebody adding the same sentence back in a new element with a
 * new testid, which is exactly how this prose accumulated in the first place
 * (seven blocks, eight sentences, each added by a different lane answering a
 * different cert). A phrase list survives that.
 *
 * ═══ MAINTAINING IT ═══
 *
 * `BANNED` is not a denylist of strings anybody happened to notice — that shape
 * hands the claim to the first new sentence. It is one entry per block that was
 * removed, so if a block returns in any wording close to its original it trips.
 * Adding a legitimate caption is fine and does not need an exception here; only
 * re-adding one of these specific paragraphs does.
 *
 * NOT COVERED HERE: the Bracket tab's `grid-liquidity-key` (block 5). It needs a
 * real `PlayoffGrid` model, which `__tests__/capture/liquidityMarkCapture.test.tsx`
 * already builds from the production ladder fixture — that file asserts the key
 * is gone and the marks still carry their tooltip. Rebuilding the grid here to
 * repeat it would be a second, weaker copy of a guard that already exists.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentProps from "@/components/tournament/TournamentProps";
import TournamentResults from "@/components/tournament/TournamentResults";
import {
  FRESHNESS_DEFINITION,
  type PropMarket,
  type PropOutcome,
} from "@/lib/tournamentProps";
import { LIQUIDITY_DEFINITION } from "@/lib/liquidity";
import type {
  TournamentResults as ResultsModel,
} from "@/lib/tournamentResults";

import hub from "../fixtures/tournamentHubBooksRung.20260903T0310Z.json";

const RESULTS = (hub as unknown as { results: ResultsModel }).results;

/** Tags stripped, entities decoded, whitespace flattened — what a reader reads. */
function visibleText(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&rsquo;|&apos;/g, "'")
    .replace(/&mdash;/g, "—")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * One entry per removed block. The `needle` is the load-bearing fragment of
 * that block's sentence — short enough to survive a wording tweak, long enough
 * that no legitimate caption would contain it.
 */
const BANNED: { block: string; needle: RegExp }[] = [
  // 1. `results-prematch-note`, sentence 1 — what the grey figure is.
  { block: "prematch explainer", needle: /is that player's probability/i },
  // 1b. the coverage count notice 34 quotes.
  { block: "prematch coverage count", needle: /\bShown on \d+ of \d+/i },
  // 1c. the limitation notice 34 quotes.
  { block: "prematch limitation", needle: /could not tie to a market of ours/i },
  // 1d. the refusal clause that had to follow the limitation.
  { block: "venue refusal clause", needle: /whether a venue listed one/i },
  { block: "empty-space justification", needle: /rather leave the space empty/i },
  // 2. `results-link-note`.
  { block: "link coverage note", needle: /open a match page/i },
  { block: "link coverage note", needle: /cannot link the rest to one yet/i },
  // 3. `results-provenance`.
  { block: "score provenance", needle: /Scores from ESPN/i },
  { block: "unregistered pair count", needle: /players we hold no market for/i },
  // 4 + 5. LIQUIDITY_DEFINITION, on both tabs.
  { block: "liquidity definition", needle: /barely being traded/i },
  { block: "liquidity definition", needle: /we have not been able to question/i },
  { block: "grid mark count", needle: /numbers here carry a mark/i },
  // 6. `props-moved-to-grid`.
  { block: "bracket-tab pointer", needle: /on the Bracket tab/i },
  // 7. the page footer's chart-method sentence.
  { block: "chart method note", needle: /daily readings with no smoothing/i },
  { block: "chart method note", needle: /labelled top that fits the field/i },
  // 8. FRESHNESS_DEFINITION.
  { block: "freshness definition", needle: /not when it was created/i },
  { block: "freshness definition", needle: /when it last changed hands/i },
];

/**
 * The two constants still exist and are still exported — `lib/tournamentProps`
 * and `lib/liquidity` are untouched by #4122, which was a render-side change.
 * Pinning that here means the banned list above cannot silently stop matching
 * because somebody reworded the constant: if the source sentence changes, this
 * fails and the list gets updated with it.
 */
describe("#4122 — the sentences exist as constants and are simply not rendered", () => {
  it("FRESHNESS_DEFINITION still says the thing notice 34 quoted", () => {
    expect(FRESHNESS_DEFINITION).toMatch(/not when it was created/i);
    expect(FRESHNESS_DEFINITION).toMatch(/when it last changed hands/i);
  });

  it("LIQUIDITY_DEFINITION still says the thing notice 34 quoted", () => {
    expect(LIQUIDITY_DEFINITION).toMatch(/barely being traded/i);
    expect(LIQUIDITY_DEFINITION).toMatch(/we have not been able to question/i);
  });
});

describe("#4122 — the finished list draws results and explains nothing", () => {
  const html = renderToStaticMarkup(
    <TournamentResults results={RESULTS} draw="mens-singles" initialExpanded />
  );
  const text = visibleText(html);

  it.each(BANNED)("does not print the $block ($needle)", ({ needle }) => {
    expect(text).not.toMatch(needle);
  });

  /**
   * THE CONTROL. Without this the suite above passes on an empty render, which
   * is the classic way a "does not contain" guard lies. This is real production
   * data — 116 men's rows — so the numbers are not a fixture author's choice.
   */
  it("still draws the results, the per-row numbers and the D91 marks", () => {
    expect(html).toContain('data-testid="tournament-results"');
    expect((html.match(/data-testid="result-row"/g) ?? []).length).toBeGreaterThan(80);
    expect((html.match(/data-testid="result-prematch"/g) ?? []).length).toBeGreaterThan(80);
    expect(html).toContain('data-testid="result-prematch-marker"');
    expect(html).toContain('data-testid="result-score"');
  });

  /** And the statistics are still computed — they moved, they did not die. */
  it("keeps every removed count readable as an attribute", () => {
    for (const attr of [
      "data-with-prematch",
      "data-prematch-total",
      "data-held-without-opening",
      "data-untied",
      "data-linked",
      "data-link-total",
      "data-unregistered-pairs",
    ]) {
      expect(html).toContain(`${attr}=`);
    }
  });
});

describe("#4122 — the questions section marks its cards and explains nothing", () => {
  /**
   * A quiet, thinly-traded card: the state that used to summon BOTH definition
   * paragraphs at once. If either comes back, it comes back here.
   */
  const outcome = (over: Partial<PropOutcome> = {}): PropOutcome => ({
    entity_key: "sinner-competes:yes",
    display_name: "Yes",
    probability: 0.63,
    probability_is_live: false,
    observed_at: "2026-08-04T20:00:00+00:00",
    age_hours: 856,
    price_state: "dark",
    is_answer: true,
    liquidity: "thin",
    liquidity_reasons: ["no_trades_24h"],
    ...over,
  });

  const market: PropMarket = {
    key: "sinner-competes",
    title: "Will Sinner actually play?",
    hook: null,
    draw: "mens-singles",
    source: "kalshi",
    answer_entity_key: "sinner-competes:yes",
    price_state: "dark",
    observed_at: "2026-08-04T20:00:00+00:00",
    age_hours: 856,
    freshest_observed_at: "2026-08-04T20:00:00+00:00",
    freshest_age_hours: 856,
    stale_outcomes: [],
    mixed_freshness: false,
    liquidity: "barely",
    liquidity_reasons: ["no_trades_24h", "spread_exceeds_price"],
    outcomes: [outcome()],
  };

  const html = renderToStaticMarkup(
    <TournamentProps markets={[market]} draw="mens-singles" />
  );
  const text = visibleText(html);

  it.each(BANNED)("does not print the $block ($needle)", ({ needle }) => {
    expect(text).not.toMatch(needle);
  });

  it("still draws the card, its number and its mark — with the note on the mark", () => {
    expect(html).toContain('data-testid="prop-market"');
    expect(text).toContain("Will Sinner actually play?");
    // The mark survives, and carries the definition itself. This is the
    // disposal notice 34 names — "a tooltip on the source mark" — so if the
    // tooltip ever goes, deleting the paragraph WOULD have cost a reader
    // something, and that must fail rather than pass quietly.
    const marks = html.match(/<[^>]*data-testid="liquidity-mark"[^>]*>/g) ?? [];
    expect(marks.length).toBeGreaterThan(0);
    for (const mark of marks) {
      expect(mark).toMatch(/title="[^"]+"/);
    }
    // The card still says its own age. That is about the question, not about us.
    expect(text).toContain("Last number");
  });
});
