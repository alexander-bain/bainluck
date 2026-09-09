/**
 * ux/1034 A3 — THE HUB STOPS SAYING "NOBODY RAN A MARKET ON IT".
 *
 * Alex, on the live US Open hub: Shelton–Hurkacz shows no pre-match number, and
 * the footnote under the finished list said
 *
 *   > The rest are matches nobody ran a market on
 *
 * which is **false for that row, measurably**. Polymarket had a market on it;
 * its price history simply begins at 17:38Z and the match began at 17:08Z. What
 * is missing is an OPENING, not a market. His instruction: *"say 'no pre-match
 * reading captured' when a market exists but no opening snapshot does.
 * Distinguish the two cases honestly."*
 *
 * ## What the payload can and cannot distinguish
 *
 * `build_results` keys a row `espn:<comp id>` exactly when the draw register
 * carries no matchup for the two players (`matchup_by_pair.get(..., f"espn:…")`
 * is the line), and both players are registered either way — a result with an
 * unregistered player never reaches this list. So the prefix means *we know
 * these two people and could not tie this fixture to a market of ours*, and its
 * absence with no prior means *we hold the fixture and caught no opening*.
 *
 * Those two are counted. The THIRD — whether Kalshi or Polymarket listed
 * anything — is not in this payload at any depth, and the sentence that
 * asserted it was doing so from a field that only ever described us. So the
 * footnote stops claiming it, and says so.
 *
 * ## The numbers below are the served ones
 *
 * From `GET /api/tournaments/us-open` at 2026-09-03T01:42Z, counted over the
 * rendered draw: men's **53 with a prior / 55 untied / 3 held-without-opening**
 * of 111; women's **58 / 65 / 3** of 126. Shelton–Hurkacz (`espn:182730`) is
 * one of the 55, which is the row Alex was reading.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentResults from "@/components/tournament/TournamentResults";
import {
  BOOKS_MARKER,
  prematchAbsenceNote,
  prematchAttribution,
  prematchCoverage,
  resultsForDraw,
  type TournamentResult,
  type TournamentResults as ResultsModel,
} from "@/lib/tournamentResults";

import hub from "../fixtures/tournamentHubUsOpen.20260903.json";

const RESULTS = (hub as unknown as { results: ResultsModel }).results;

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function render(draw: string): string {
  return renderToStaticMarkup(
    <TournamentResults results={RESULTS} draw={draw} initialExpanded={false} />
  );
}

describe("ux/1034 A3 — why a finished row has no pre-match number", () => {
  it("splits the priorless rows on the served men's list", () => {
    const counted = prematchCoverage(resultsForDraw(RESULTS, "mens-singles"));
    expect(counted).toEqual({
      withPrior: 53,
      total: 111,
      untied: 55,
      heldWithoutOpening: 3,
    });
    // The two reasons account for every row without a prior — no third bucket
    // hiding behind a subtraction.
    expect(counted.untied + counted.heldWithoutOpening).toBe(
      counted.total - counted.withPrior
    );
  });

  it("splits them on the women's list too", () => {
    expect(prematchCoverage(resultsForDraw(RESULTS, "womens-singles"))).toEqual({
      withPrior: 58,
      total: 126,
      untied: 65,
      heldWithoutOpening: 3,
    });
  });

  /** Alex's own row. It is in the untied bucket, and the old sentence called it
   *  a match nobody ran a market on. */
  it("puts Shelton–Hurkacz in the untied bucket, not the no-market one", () => {
    const row = resultsForDraw(RESULTS, "mens-singles").find(
      (match) => match.matchup_key === "espn:182730"
    );
    expect(row).toBeDefined();
    expect(row!.players.every((p) => p.prematch_probability == null)).toBe(true);
    expect(prematchCoverage([row!])).toEqual({
      withPrior: 0,
      total: 1,
      untied: 1,
      heldWithoutOpening: 0,
    });
  });

  // ═══ #4125 ITEM 1 — THE WHOLE PARAGRAPH LEFT THE PAGE (notice 34) ═══
  //
  // This test used to pin four clauses of a coverage paragraph. Alex read that
  // paragraph on 2026-09-08 and ruled it off the page — *"all the grey text is
  // madness, and shouldn't be user-facing at all"* — and notice 34 names both
  // halves of what it was doing: a coverage count ("Shown on 53 of 111") and a
  // limitation ("55 are fixtures we could not tie to a market of ours").
  //
  // 🔴 THE LAST CLAUSE IS THE ONE TO READ TWICE. The paragraph ended *"we would
  // rather leave the space empty than fill it with a number about a different
  // question"* — an explanation of an emptiness, which notice 34 forbids **by
  // name**: *"If a number cannot be shown honestly, leave the space empty; do
  // not explain the emptiness in a paragraph."* The page now does the first
  // half of that sentence and not the second.
  //
  // ⚠️ WHAT THIS SUITE IS STILL FOR, AND WHY IT IS NOT DELETED. ux/1034 A3's
  // finding was that the page made a FALSE CLAIM about a venue ("the rest are
  // matches nobody ran a market on") when the truth was only ever about our own
  // register. That claim can return the moment anybody writes a sentence here
  // again, so the honesty arm stays and gets stricter: not "phrased carefully"
  // but "absent". The counts it was phrased from are asserted below, on the
  // attributes, and `prematchAbsenceNote` keeps its own unit tests further down
  // — the vocabulary is intact and unexported to the page, which is the state
  // notice 34 asks for.
  it("makes no claim about a venue, because it makes no claim at all", () => {
    const text = visibleText(render("mens-singles"));

    // THE ORIGINAL DEFECT, still gone.
    expect(text).not.toContain("nobody ran a market on");

    // And now the whole apparatus that replaced it is gone too.
    expect(text).not.toContain("Shown on 53 of 111");
    expect(text).not.toContain("could not tie to a market of ours");
    expect(text).not.toContain("caught no price on before play started");
    expect(text).not.toContain("whether a venue listed one");
    expect(text).not.toContain("rather leave the space empty");

    // POSITIVE CONTROL — the list itself is still rendering, so the absences
    // above are a removal rather than an empty page. The source mark stays
    // (D91) and so does the one short caption notice 34 allows.
    expect(text).toContain("Scores from ESPN.");
    expect(text).toContain("Grey is the pre-match probability.");
  });

  /** The counts are queryable, so a future drift is a failing assertion rather
   *  than a paragraph somebody has to re-read. */
  it("publishes the two counts as attributes", () => {
    const html = render("mens-singles");
    expect(html).toContain('data-with-prematch="53"');
    expect(html).toContain('data-total="111"');
    expect(html).toContain('data-untied="55"');
    expect(html).toContain('data-held-without-opening="3"');
  });

  describe("the sentence itself", () => {
    it("says only what is there, and pluralises", () => {
      expect(
        prematchAbsenceNote({ withPrior: 9, total: 10, untied: 1, heldWithoutOpening: 0 })
      ).toBe(
        "Of the rest, 1 is a fixture we could not tie to a market of ours — " +
          "neither is a statement about whether a venue listed one."
      );
      expect(
        prematchAbsenceNote({ withPrior: 8, total: 10, untied: 0, heldWithoutOpening: 2 })
      ).toBe(
        "Of the rest, 2 are matches we hold but caught no price on before play " +
          "started — neither is a statement about whether a venue listed one."
      );
    });

    it("is empty when every row has a prior", () => {
      expect(
        prematchAbsenceNote({ withPrior: 4, total: 4, untied: 0, heldWithoutOpening: 0 })
      ).toBe("");
    });
  });
});

// ═══ ux/1036 / #2747 — AND THE LABEL WHEN THE PRIOR IS A SPORTSBOOK'S ═══
//
// The books rung now fills rows the market channel cannot reach: measured by
// replaying the served payload (2026-09-03) through `apply_books_prematch`,
// 111 of 245 rows carried a prior and 172 do — including Shelton–Hurkacz, the
// row Alex read, at 68% labelled `books`.
//
// The sentence above those numbers used to say the grey figure is "what the
// market gave that player". That is true of Kalshi and Polymarket and NOT of a
// sportsbook median, and printing the second as the first on this exact list is
// the defect ux/1034 A3 removed from the sentence beside it.
//
// ═══ D91 (Alex, 2026-09-08) — WHAT THESE THREE TESTS NOW READ ═══
//
// They asserted `prematchSourceNote`, the footer legend, which D91 deleted as
// supplier narration in a caption. The rung is still labelled — by the per-row
// marker, which is the attribution D91 keeps — so the assertions moved from the
// aggregate sentence to `prematchAttribution`, the thing that actually decides.
// The lead sentence no longer names a rung at all, which is why no caveat is
// owed; that half is pinned in `hubRowNamesItsSource2747.test.tsx` against the
// render. See the tombstone in `lib/tournamentResults.ts`.
describe("ux/1036 — a sportsbook prior says so, on the row itself", () => {
  const row = (source: string | null) => ({
    matchup_key: `espn:${source ?? "none"}`,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R64",
    players: [
      { entity_key: "a", display_name: "Ben Shelton", seed: null, is_winner: true,
        prematch_probability: 0.6792, prematch_source: source },
      { entity_key: "b", display_name: "Hubert Hurkacz", seed: null, is_winner: false,
        prematch_probability: 0.3208, prematch_source: source },
    ],
    winner_entity_key: "a",
    score: "6-4, 6-4",
    completed_at: "2026-09-02T19:00:00Z",
    source_round: "Round 2",
    source: "espn",
  }) as unknown as TournamentResult;

  /** Every player slot in these rows, which is what carries the attribution. */
  const slotsOf = (...matches: TournamentResult[]) =>
    matches.flatMap((match) => match.players.map((p) => prematchAttribution(p)));

  it("marks the books rows and only the books rows", () => {
    // The property CERT-812 actually required, read where it is now decided.
    // A books slot wears the mark; a market slot does not. Both directions in
    // one assertion so a change that marks everything cannot pass.
    const [booksA, booksB, marketA, marketB] = slotsOf(row("books"), row("kalshi"));
    expect(booksA.marker).toBe(BOOKS_MARKER);
    expect(booksB.marker).toBe(BOOKS_MARKER);
    expect(marketA.marker).toBeNull();
    expect(marketB.marker).toBeNull();
  });

  it("marks nothing when every prior is a prediction market's", () => {
    // Silent on the market population, which is the point: a caveat printed on
    // numbers it does not describe is noise.
    const marks = slotsOf(row("kalshi"), row("polymarket")).map((a) => a.marker);
    expect(marks).toEqual([null, null, null, null]);
  });

  it("marks nothing on a payload that predates the field", () => {
    // An ABSENT source is a prediction-market opening from `_prematch_by_pair`,
    // not an unknown rung — it must not pick up the mark.
    expect(slotsOf(row(null)).map((a) => a.marker)).toEqual([null, null]);
  });

  it("says the SAME venue-free clause on every rung (D65, and D91 keeps it)", () => {
    // The one place a supplier word could still reach a screen reader on this
    // list. One phrase for all four slots, so it cannot name the wrong venue.
    const said = slotsOf(row("books"), row("kalshi")).map((a) => a.said);
    expect(new Set(said).size).toBe(1);
    expect(said[0]).not.toMatch(/sportsbook|\bbooks?\b|kalshi|polymarket/i);
  });
});
