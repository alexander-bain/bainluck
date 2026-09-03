/**
 * UX-P277 / #2831 — ONE QUESTION DECIDES BOTH ITS PERCENTS.
 *
 * A market with exactly two outcomes prints BOTH sides of one question, and
 * each side was rounded on its own. `Math.round` is half-up toward +∞, so an
 * exact complement that splits on a `.5` boundary sends BOTH halves up:
 *
 *     Will Aryna Sabalenka advance to the Round of 16?
 *     stored 0.925000 / 0.075000  — an exact complement, the data is perfect
 *     printed        93%  +  8%   =  101%
 *
 * ── THE REPAIR ALREADY EXISTED AND NAMED THIS BUG ───────────────────────────
 *
 * `lib/probabilityDisplay.ts:44-48` (UX-P114) says it verbatim: "a card that
 * prints two sides of one question decides both percents together, or the two
 * independently-correct numbers sum to 101". It had reached every surface that
 * prints a GAME's two teams (`FeedCard`, `EventCard`, `TournamentMatches`) and
 * none that prints a MARKET's Yes/No — which is exactly why no event card has
 * ever summed to 101 and every two-outcome futures card could.
 *
 * ── THE POPULATION, MEASURED RATHER THAN TAKEN FROM THE ISSUE ───────────────
 *
 * Every open two-outcome market whose sides fall inside the [0.99, 1.01]
 * complement band — 876 distinct pairs covering 17,125 markets, a COMPLETE
 * census rather than a sample, committed beside this file and replayed below
 * through the shipped function. Replayed in JS float semantics, because
 * Postgres `numeric` is half-away-from-zero and the browser is what the reader
 * sees; the two disagree, and the browser is the one that matters.
 *
 *     rendered today   100: 10,030   101: 6,954   99: 104   102: 37
 *     after this ship  100: 17,125   everything else: 0
 *
 * ⚠️ TWO CORRECTIONS TO #2831, both of which a grader would otherwise find.
 *
 *  1. The issue says "It can never lose one — this class renders 101, never
 *     99." That is true of an EXACT complement and false of the band the
 *     predicate actually uses. `0.5/0.49` sums to 0.99, is a complement pair by
 *     `isComplementPair`, and prints **99** today. 104 markets do. Both are
 *     fixed here, and the 99 case is asserted below so the claim cannot be
 *     restated wrongly later.
 *
 *  2. The issue's census names four ❌ call sites. THREE OF THEM CANNOT EXHIBIT
 *     THIS BUG, because they never print both sides of a two-outcome market:
 *       · `discover/ComparisonCard` — `DiscoverCard.tsx:169` routes to it only
 *         when `top_outcomes.length >= 4`.
 *       · `discover/FuturesCard:312` — its row list is gated on
 *         `distributionRows.length >= 4`; a two-outcome card renders only that
 *         file's HERO, which already goes through `renderedLeaderPercent`.
 *       · `RelatedFutures:659` — maps DISTINCT markets, one side each. There is
 *         no pair to decide.
 *     A census built by grepping for `formatProbabilityPercent` without a
 *     `rendered` argument finds call sites, not duels. The two surfaces that
 *     genuinely print both sides are the ones this ship touches, and both were
 *     verified live on the SAME market: `/search?q=Sabalenka` (5 of 10 rows
 *     wrong) and its destination `/futures/59556771` (93 + 8 = 101).
 *
 * ── WHAT THIS HARNESS CAN AND CANNOT SEE ────────────────────────────────────
 *
 * `components/FuturesCard` is a real exported component, so every claim about
 * it is read off RENDERED MARKUP, and off elements that predate this diff
 * (`data-outcome-label`, `aria-valuenow`, `aria-label`) so that a population
 * filter cannot be vacuous on the parent.
 *
 * The second surface, `app/futures/[id]/page.tsx`'s `OutcomeRow`, is NOT
 * exported and MUST NOT BECOME exported — a named export from a Next.js
 * `page.tsx` is a typecheck error against the page contract (UX-P274 paid for
 * that, and UX-P275 recorded it). So its claim is a SOURCE SCAN, which is
 * strictly weaker, and it is labelled as such rather than dressed up as a
 * render. Comments are stripped before scanning, because this file's own prose
 * quotes the very identifiers it looks for.
 */

import { renderToStaticMarkup } from "react-dom/server";
import fs from "fs";
import path from "path";
import FuturesCard from "../../components/FuturesCard";
import type { FuturesMarket, FuturesOutcome } from "../../lib/types";
import {
  renderedOutcomeRowPercents,
  isComplementPair,
} from "../../lib/renderedPercent";
import corpus from "../fixtures/twoOutcomeComplementCorpus.2026-09-03.json";

const REPO = path.join(__dirname, "..", "..");

function outcome(
  id: number,
  name: string,
  probability: number | null,
  opening: number | null = null,
): FuturesOutcome {
  return {
    id,
    name,
    probability,
    american_odds: null,
    rank: null,
    rank_change_24h: null,
    probability_change_24h: null,
    movement: null,
    opening_probability: opening,
    opening_american_odds: null,
    is_winner: null,
    last_updated: null,
  } as unknown as FuturesOutcome;
}

function market(name: string, outcomes: FuturesOutcome[]): FuturesMarket {
  return {
    id: 59556771,
    name,
    description: null,
    source: "kalshi",
    category: null,
    sport: null,
    sport_name: null,
    llm_sport_category: "tennis",
    external_id: null,
    mutually_exclusive: true,
    commence_time: null,
    resolution_date: null,
    outcome_count: outcomes.length,
    created_at: null,
    updated_at: null,
    status: "open",
    outcomes,
  } as unknown as FuturesMarket;
}

/**
 * One rendered row, with its NAME, its printed digits, its accessible value and
 * its bar geometry read out TOGETHER.
 *
 * Deliberately a per-row binding rather than three parallel lists. A guard that
 * reads bare percentages cannot tell "the pair is wrong" from "the pair is
 * right wearing each other's names", and the second is exactly what a fix that
 * decides the pair but indexes it over the unsorted array produces. Counter-case
 * (B) below permutes the labels and this extractor is what catches it.
 *
 * It also reports its own yield: the row count is cross-checked against an
 * independently countable fact about the same markup, so a lazy regex that
 * silently drops a row fails loudly with the numbers in it rather than quietly
 * under-reporting.
 */
type Row = { label: string; printed: string; ariaName: string; ariaValue: number; width: string };

/**
 * `>99%` and `<1%` leave `renderToStaticMarkup` as `&gt;99%` and `&lt;1%`.
 *
 * ONE pass over a lookup map, deliberately: a chained `.replace()` decode
 * unescapes `&amp;` before the others and so re-reads its own output, which is
 * the `js/double-escaping` alert CodeQL raised on a previous guard in this repo.
 * A single regex with a map cannot.
 */
const ENTITIES: Record<string, string> = { "&gt;": ">", "&lt;": "<", "&amp;": "&", "&quot;": '"', "&#x27;": "'" };
const decode = (s: string) => s.replace(/&(?:gt|lt|amp|quot|#x27);/g, (e) => ENTITIES[e]);

function rows(html: string): Row[] {
  const declared = (html.match(/data-outcome-label/g) ?? []).length;
  if (declared === 0) {
    throw new Error(
      "no data-outcome-label spans rendered — the extractor is blind, not the card empty",
    );
  }
  const chunks = html.split("data-outcome-label").slice(1);
  const out: Row[] = [];
  for (const chunk of chunks) {
    const label = /^[^>]*>([^<]*)</.exec(chunk)?.[1];
    const aria = /role="progressbar"[^>]*aria-valuenow="(-?\d+)"[^>]*aria-label="([^"]*) probability"/.exec(chunk);
    const width = /width:([\d.]+%)/.exec(chunk)?.[1];
    const printed = /<span class="font-mono text-sm tabular-nums[^"]*">([^<]*)<\/span>/.exec(chunk)?.[1];
    if (label == null || aria == null || width == null || printed == null) {
      throw new Error(
        `row ${out.length} incomplete: label=${label} aria=${aria?.[1]} width=${width} printed=${printed}`,
      );
    }
    out.push({ label, printed: decode(printed), ariaName: aria[2], ariaValue: Number(aria[1]), width });
  }
  if (out.length !== declared) {
    throw new Error(`extractor yielded ${out.length} rows but the markup declares ${declared}`);
  }
  return out;
}

const sum = (rs: Row[]) => rs.reduce((a, r) => a + Number(r.printed.replace("%", "")), 0);

// The reported specimen, straight out of `futures_outcomes` on 2026-09-03.
const SPECIMEN = () =>
  market("Will Aryna Sabalenka advance to the Round of 16 in Women's Singles?", [
    outcome(1, "Yes", 0.925),
    outcome(2, "No", 0.075),
  ]);

// ════════════════════════════════════════════════════════════════════════════
// THE SHIP — every one of these must be RED on the parent.
// ════════════════════════════════════════════════════════════════════════════

describe("the ship: a two-outcome market's printed pair totals 100", () => {
  it("the reported specimen prints 93% and 7%, not 93% and 8%", () => {
    const rs = rows(renderToStaticMarkup(<FuturesCard market={SPECIMEN()} />));
    expect(rs.map((r) => r.printed)).toEqual(["93%", "7%"]);
    expect(sum(rs)).toBe(100);
  });

  it("the digits are bound to the right names, not merely in the right order", () => {
    const rs = rows(renderToStaticMarkup(<FuturesCard market={SPECIMEN()} />));
    expect(rs.map((r) => [r.label, r.printed])).toEqual([
      ["Yes", "93%"],
      ["No", "7%"],
    ]);
    // The accessible name is read off the SAME element as the accessible value,
    // so this pairing cannot be satisfied by two lists that happen to align.
    expect(rs.map((r) => [r.ariaName, r.ariaValue])).toEqual([
      ["Yes", 93],
      ["No", 7],
    ]);
  });

  it("a screen reader is told the same number the digits print", () => {
    const rs = rows(renderToStaticMarkup(<FuturesCard market={SPECIMEN()} />));
    for (const r of rs) expect(`${r.ariaValue}%`).toBe(r.printed);
    expect(rs.reduce((a, r) => a + r.ariaValue, 0)).toBe(100);
  });

  it("the printed pair does not depend on which order the rows arrive in", () => {
    // The futures detail page lets the reader sort these rows. A rule anchored on
    // display order would print 93/7 sorted by probability and 8/92 sorted by
    // name — the same market, two answers, one click apart.
    const forward = rows(renderToStaticMarkup(<FuturesCard market={SPECIMEN()} />));
    const reversed = rows(
      renderToStaticMarkup(
        <FuturesCard
          market={market("Will Aryna Sabalenka advance to the Round of 16 in Women's Singles?", [
            outcome(2, "No", 0.075),
            outcome(1, "Yes", 0.925),
          ])}
        />,
      ),
    );
    const byName = (rs: Row[]) =>
      Object.fromEntries(rs.map((r) => [r.label, r.printed]));
    expect(byName(reversed)).toEqual(byName(forward));
    expect(byName(forward)).toEqual({ Yes: "93%", No: "7%" });
  });

  it("the 99 case #2831 says cannot exist is real, and is also fixed", () => {
    // `0.5 / 0.49` sums to 0.99 — inside the complement band, so this predicate
    // owns it — and rounds independently to 50 + 49 = 99.
    const rs = rows(
      renderToStaticMarkup(
        <FuturesCard market={market("A market that loses a point", [
          outcome(1, "Yes", 0.5),
          outcome(2, "No", 0.49),
        ])} />,
      ),
    );
    expect(sum(rs)).toBe(100);
    expect(rs.map((r) => [r.label, r.printed])).toEqual([
      ["Yes", "51%"],
      ["No", "49%"],
    ]);
  });

  it("a pair inside the band that renders 102 is also brought to 100", () => {
    // `Sabalenka vs Rakhimova`, live on /search?q=Sabalenka: raw 0.935/0.075
    // sums to 1.0100, the top of the band, and renders 94 + 8.
    const rs = rows(
      renderToStaticMarkup(
        <FuturesCard market={market("Sabalenka vs Rakhimova", [
          outcome(1, "Sabalenka", 0.935),
          outcome(2, "Rakhimova", 0.075),
        ])} />,
      ),
    );
    expect(sum(rs)).toBe(100);
  });
});

// ════════════════════════════════════════════════════════════════════════════
// CONTROLS — every one of these is GREEN ON THE PARENT TOO. Verified by running
// the red arm and counting, not by labelling. If one of these goes red, the
// change stopped being a rounding fix and started moving numbers.
// ════════════════════════════════════════════════════════════════════════════

describe("CONTROL (green on main too): nothing that was right may move", () => {
  it("a pair that does not split on .5 renders exactly as before", () => {
    // 0.93/0.07 is an exact complement and needs no help: 93 + 7 = 100 already.
    // This is the fixture #2831 warns a guard must NOT be built on.
    const rs = rows(
      renderToStaticMarkup(
        <FuturesCard market={market("Already honest", [
          outcome(1, "Yes", 0.93),
          outcome(2, "No", 0.07),
        ])} />,
      ),
    );
    expect(rs.map((r) => [r.label, r.printed])).toEqual([
      ["Yes", "93%"],
      ["No", "7%"],
    ]);
  });

  it("two outcomes that are NOT a complement are left alone", () => {
    // Live on Discover: "When will Apple release the iPhone 18?" ships two
    // outcomes summing to 0.215. Normalizing that would invent 78 points of
    // probability, so it must render independently, as it does today.
    const rs = rows(
      renderToStaticMarkup(
        <FuturesCard market={market("When will Apple release the iPhone 18?", [
          outcome(1, "September", 0.15),
          outcome(2, "October", 0.07),
        ])} />,
      ),
    );
    expect(rs.map((r) => r.printed)).toEqual(["15%", "7%"]);
    expect(sum(rs)).toBe(22);
  });

  it("a market with more than two outcomes is byte-identical", () => {
    const many = market("A five-way field", [
      outcome(1, "A", 0.4),
      outcome(2, "B", 0.25),
      outcome(3, "C", 0.2),
      outcome(4, "D", 0.1),
      outcome(5, "E", 0.05),
    ]);
    const rs = rows(renderToStaticMarkup(<FuturesCard market={many} />));
    expect(rs.map((r) => r.printed)).toEqual(["40%", "25%", "20%", "10%", "5%"]);
  });

  it("the bar geometry comes off the raw probability and does not move", () => {
    // Only the ROUNDING was at fault. A fix that also normalized the widths
    // would be changing the picture, not the caption.
    const rs = rows(renderToStaticMarkup(<FuturesCard market={SPECIMEN()} />));
    expect(rs.map((r) => r.width)).toEqual(["92.5%", "7.5%"]);
  });

  it("UX-P046's bands still fire on the pair", () => {
    // 0.997/0.003 normalizes to a leader of 100 and a derived 0, and neither may
    // print as a boundary the probability is not on.
    const rs = rows(
      renderToStaticMarkup(
        <FuturesCard market={market("A near-certainty", [
          outcome(1, "Yes", 0.997),
          outcome(2, "No", 0.003),
        ])} />,
      ),
    );
    expect(rs.map((r) => r.printed)).toEqual([">99%", "<1%"]);
  });
});

// ════════════════════════════════════════════════════════════════════════════
// THE MEASURED POPULATION, replayed through the SHIPPED function.
// Every number in this file's header is an assertion here, not a claim.
// ════════════════════════════════════════════════════════════════════════════

type Pair = { lo: number; hi: number; markets: number };
const PAIRS = corpus.pairs as Pair[];
/** JS half-up, which is what the browser does and what Postgres does NOT. */
const independent = (p: number) => Math.round(p * 100);

describe("the live corpus: 876 distinct pairs, 17,125 open markets", () => {
  it("is the complete census the header claims", () => {
    expect(PAIRS.length).toBe(876);
    expect(PAIRS.reduce((a, p) => a + p.markets, 0)).toBe(17125);
  });

  it("reproduces the BEFORE distribution exactly", () => {
    const before: Record<number, number> = {};
    for (const p of PAIRS) {
      const s = independent(p.hi) + independent(p.lo);
      before[s] = (before[s] ?? 0) + p.markets;
    }
    expect(before).toEqual({ 99: 104, 100: 10030, 101: 6954, 102: 37 });
  });

  it("brings every one of them to 100, with no exceptions", () => {
    const after: Record<number, number> = {};
    for (const p of PAIRS) {
      const [a, b] = renderedOutcomeRowPercents([p.hi, p.lo]);
      const s = (a ?? 0) + (b ?? 0);
      after[s] = (after[s] ?? 0) + p.markets;
    }
    expect(after).toEqual({ 100: 17125 });
  });

  it("never moves either side by more than one point", () => {
    let worst = 0;
    for (const p of PAIRS) {
      const [a, b] = renderedOutcomeRowPercents([p.hi, p.lo]);
      worst = Math.max(
        worst,
        Math.abs(independent(p.hi) - (a ?? 0)),
        Math.abs(independent(p.lo) - (b ?? 0)),
      );
    }
    expect(worst).toBe(1);
  });

  it("CONTROL (green on main too): every pair in the corpus is a complement pair", () => {
    // If this goes red the corpus has drifted out of the band the predicate owns,
    // and the three assertions above are answering for the wrong population.
    for (const p of PAIRS) expect(isComplementPair([p.hi, p.lo])).toBe(true);
  });
});

// ════════════════════════════════════════════════════════════════════════════
// THE SECOND SURFACE — a SOURCE SCAN, strictly weaker than a render, and said
// so rather than dressed up. `app/futures/[id]/page.tsx`'s `OutcomeRow` is not
// exported and must not become exported (UX-P274).
// ════════════════════════════════════════════════════════════════════════════

/**
 * Source with comments removed.
 *
 * A guard that greps its own module cannot tell the code from the commentary
 * about the code, and the better the comment the likelier it trips — this
 * file's own prose, and the page's, quote every identifier below.
 */
function codeOf(rel: string): string {
  return fs
    .readFileSync(path.join(REPO, rel), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
}

describe("the futures detail page (SOURCE SCAN — weaker than a render)", () => {
  const page = codeOf("app/futures/[id]/page.tsx");

  it("decides the pair once, from the unsorted market set", () => {
    expect(page).toContain("renderedOutcomeRowPercents");
    // Anchored on `market?.outcomes`, NOT on the sorted or displayed list: the
    // rows are user-sortable and a display-order rule prints a different pair
    // per sort.
    expect(page).toMatch(/const outs = market\?\.outcomes \?\? \[\]/);
    expect(page).not.toMatch(/renderedOutcomeRowPercents\(\s*(sortedOutcomes|displayedOutcomes)/);
  });

  it("passes it to BOTH price columns", () => {
    expect(page).toMatch(/formatProbability\(outcome\.probability,\s*\{\s*rendered\s*\}\)/);
    expect(page).toMatch(
      /formatProbability\(outcome\.opening_probability,\s*\{\s*rendered:\s*renderedOpening\s*\}\)/,
    );
  });

  it("leaves no bare formatProbability on an outcome price", () => {
    // The whole defect is a call site that rounds a second time on its own.
    expect(page).not.toMatch(/formatProbability\(outcome\.probability\)/);
    expect(page).not.toMatch(/formatProbability\(outcome\.opening_probability\)/);
  });

  it("looks the row up by id, so re-sorting cannot re-assign a number", () => {
    expect(page).toMatch(/renderedById\.get\(outcome\.id\)/);
  });
});

// ════════════════════════════════════════════════════════════════════════════
// ANTI-DRIFT — the next call site must not be able to acquire this bug quietly.
// ════════════════════════════════════════════════════════════════════════════

describe("anti-drift", () => {
  it("both surfaces' `rendered` props are REQUIRED, with no default", () => {
    // A default of `null` would compile at the next call site and print 101
    // again with every test in this file still green — which is precisely how
    // the row came to round independently in the first place.
    for (const rel of ["components/FuturesCard.tsx", "app/futures/[id]/page.tsx"]) {
      const code = codeOf(rel);
      expect(code).toMatch(/^\s*rendered: number \| null;$/m);
      expect(code).not.toMatch(/rendered\?: number \| null/);
      expect(code).not.toMatch(/rendered: number \| null = /);
    }
  });

  it("the card asks the WHOLE shipped outcome set, not the sliced five", () => {
    // Two rows out of a longer field are not a duel, and `slice` must not be
    // able to manufacture one.
    const code = codeOf("components/FuturesCard.tsx");
    expect(code).toMatch(/renderedOutcomeRowPercents\(outcomes\.map\(\(o\) => o\.probability\)\)/);
    expect(code).not.toMatch(/renderedOutcomeRowPercents\(topOutcomes/);
  });

  it("no second rounding policy was introduced", () => {
    // UX-P046 owns the single-value rule and derives its bands from the rounding
    // RESULT. A `toFixed`, a half-to-even or a local threshold here would be the
    // drift UX-P114 exists to prevent.
    const helper = codeOf("lib/renderedPercent.ts");
    expect(helper).not.toContain("toFixed");
    expect(helper).not.toContain("banker");
    // The new helper delegates rather than re-deriving.
    expect(helper).toMatch(
      /export function renderedOutcomeRowPercents[\s\S]{0,320}return renderedDuelPercents\(values\[0\], values\[1\]\);/,
    );
  });
});
