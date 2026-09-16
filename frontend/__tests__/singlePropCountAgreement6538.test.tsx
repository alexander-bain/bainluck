/**
 * #6538 — a game with exactly ONE prop told the reader "1 questions".
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/events/14638896` (Broncos 10 @ Chiefs 31, MNF, Final), production, 390px,
 * 2026-09-16 10:5xZ (`artifacts/ux-1296/BEFORE-kc-390.png`), measured by
 * `artifacts/ux-1296/repro-plural.mjs`:
 *
 *     All 1 props                          ← the props expander
 *     See all 1 questions                  ← the divergence rail's expand
 *     1 question settled here, and none has a published outcome yet — so
 *     there is nothing to rank. They are all listed below.
 *     … these questions settled without a published outcome, so there is no
 *     result to show against their mark.       ← behind the expand
 *
 * Four disagreements about one prop on one screen. The noun in the third line
 * already agreed; its VERB and PRONOUN did not.
 *
 * ═══ MECHANISM ═══
 *
 * `lib/plural.ts` exists for exactly this class. Its own header records why:
 * UX-P265 (#2645) lifted it out after the shopper found `/sports` printing
 * "1 sources", so the next surface would "have something to import instead of
 * a fourth hand-rolled ternary". These four sites are that next surface, and
 * they never adopted it — a helper written to prevent a class does not prevent
 * it at the call sites that never called it.
 *
 * `PropDivergenceRail` is the sharp case: line 100 pluralises the noun with the
 * correct idiom, and line 151, six lines below, hard-codes "questions".
 *
 * ═══ REACH, MEASURED, NOT MODELLED ═══
 *
 * The one-prop page is not an edge case invented for a fixture: the payload in
 * `fixtures/eventPlayerProps.14638896.settled-single.json` is the production
 * `player_props[]` of a Monday Night Football game, fetched the morning this
 * was written. The event page mounts this whole block behind
 * `player_props.length > 0`, so a single prop is explicitly in scope.
 *
 * Sites NOT converted, and why — the grep found twelve more `{n} <plural>`
 * sites and most are already correct:
 *   - GUARDED, can never print "1 X": FeedCard 1111, FuturesCard 188/269,
 *     RelatedFutures 253/492, TotalPointsSpectrum 16, ProgressionTable 92,
 *     SourceAggregationBlock 125 (`if (freshCount < 2) return null`).
 *   - UNREACHABLE: PlayerPropsGrid 127 has no importer — dead code.
 *   - UNPROVEN: discover GroupCard/ComparisonCard, FuturesHero 216,
 *     RelatedFutures 1682. No production specimen with a count of 1 was found
 *     (120 feed items: 0 group cards of length 1), so they are recorded rather
 *     than changed. Converting a site whose count cannot be 1 is churn that
 *     reads as coverage.
 */

import { renderToStaticMarkup } from "react-dom/server";
import PropDivergenceRail from "@/components/PropDivergenceRail";
import PropDivergenceDetail from "@/components/PropDivergenceDetail";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";
import { readFileSync } from "fs";
import { join } from "path";

import single from "./fixtures/eventPlayerProps.14638896.settled-single.json";

const SINGLE = single as unknown as PlayerPropRow[];

/**
 * Visible text, the way a reader gets it. Tags out, entities back, whitespace
 * collapsed — because the copy under test is split across JSX expressions and
 * `{" "}` separators, so a raw-markup `toContain` would fail on correct output.
 */
const ENTITY: Record<string, string> = {
  "&#x27;": "'",
  "&apos;": "'",
  "&rsquo;": "'",
  "&quot;": '"',
  "&ldquo;": '"',
  "&rdquo;": '"',
  "&amp;": "&",
};

function textOf(markup: string): string {
  return (
    markup
      .replace(/<[^>]*>/g, " ")
      // ONE pass, not a chain. Unescaping `&amp;` in its own `.replace` before
      // the others turns `&amp;#x27;` into `'` — CodeQL js/double-escaping, and
      // it failed this sha's check-run as a high-severity alert the first time
      // round. A single alternation cannot double-unescape: each match is
      // consumed once and its replacement is never rescanned.
      .replace(/&(?:#x27|apos|rsquo|quot|ldquo|rdquo|amp);/g, (m) => ENTITY[m])
      .replace(/\s+/g, " ")
      .trim()
  );
}

/** The same row N times, each a distinct player, so the count is the only variable. */
function repeat(n: number): PlayerPropRow[] {
  return Array.from({ length: n }, (_, i) => ({
    ...SINGLE[0],
    outcome_name: `Player ${i}: 1+`,
    _market_id: 900000 + i,
  })) as unknown as PlayerPropRow[];
}

describe("#6538 — one prop, one question, singular copy", () => {
  it("the fixture is genuinely one ungraded prop (the defect's precondition)", () => {
    expect(SINGLE).toHaveLength(1);
    expect(SINGLE[0].is_winner).toBeNull();
    expect(SINGLE[0].resolution_source).toBeNull();
  });

  it("the rail's expand says 'See all 1 question', not '1 questions'", () => {
    const text = textOf(
      renderToStaticMarkup(
        <PropDivergenceRail playerProps={SINGLE} status="completed" />,
      ),
    );
    expect(text).toContain("See all 1 question");
    expect(text).not.toContain("See all 1 questions");
  });

  it("the honest-empty sentence agrees in verb and pronoun for one question", () => {
    const text = textOf(
      renderToStaticMarkup(
        <PropDivergenceRail playerProps={SINGLE} status="completed" />,
      ),
    );
    expect(text).toContain("1 question settled here");
    expect(text).toContain("it has no published outcome yet");
    expect(text).toContain("It is listed below.");
    expect(text).not.toContain("none has a published outcome");
    expect(text).not.toContain("They are all listed below");
  });

  it("the not-graded note says 'this question', not 'these questions'", () => {
    const text = textOf(
      renderToStaticMarkup(
        <PropDivergenceDetail playerProps={SINGLE} status="completed" />,
      ),
    );
    expect(text).toContain("this question settled without a published outcome");
    expect(text).toContain("against its mark");
    expect(text).not.toContain("these questions settled");
  });

  // ─── THE CONTROL. A narrowing that made the plural branch unreachable would
  // pass every assertion above. These pin the branch this ship must NOT move.
  it("CONTROL: several props keep the plural copy, verb and pronoun", () => {
    const text = textOf(
      renderToStaticMarkup(
        <PropDivergenceRail playerProps={repeat(4)} status="completed" />,
      ),
    );
    expect(text).toContain("4 questions settled here");
    expect(text).toContain("none has a published outcome yet");
    expect(text).toContain("They are all listed below.");
    expect(text).not.toContain("It is listed below.");
  });

  it("CONTROL: several props keep 'these questions' in the not-graded note", () => {
    const text = textOf(
      renderToStaticMarkup(
        <PropDivergenceDetail playerProps={repeat(4)} status="completed" />,
      ),
    );
    expect(text).toContain("these questions settled without a published outcome");
    expect(text).toContain("against their mark");
  });

  // ─── The event page's own summary. The page is a 2,900-line client component
  // that no jest render reaches, so the guard reads the line itself. A source
  // scan is weaker than a render — it is here because the alternative is no
  // guard at all on the one site a reader meets first, and the rendered proof
  // for this site is the production after-check in artifacts/ux-1296.
  it("the event page's props expander routes its count through countOf", () => {
    const src = readFileSync(
      join(__dirname, "..", "app", "events", "[id]", "page.tsx"),
      "utf8",
    );
    expect(src).toContain(
      'All {countOf(gameMarkets.player_props.length, "prop", "props")}',
    );
    // the bare form is what printed "All 1 props"
    expect(src).not.toContain("All {gameMarkets.player_props.length} props");
  });
});
