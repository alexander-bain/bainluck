/**
 * #4278 — THE SECOND NOTICE-34 SWEEP OF THE TOURNAMENT PAGE.
 *
 * ═══ WHY THERE IS A SECOND ONE ═══
 *
 * `noDiagnosticProseOnTournamentPage4122.test.tsx` is the first sweep and its
 * header carries the ruling in full. Read it first; nothing here restates it.
 *
 * That sweep took nine grey blocks out of `TournamentProps` and
 * `TournamentResults`. **Six more survived it**, in four components it never
 * touched, and they were all still on production at `ae83f1d1` on 2026-09-09
 * — three sweeps after Alex's words. Measured by re-photographing
 * `https://bainluck.com/tournaments/us-open` at `SHOT_W=390`, full page
 * (7,750px), and Reading every one of nine slices:
 *
 *   | string on the page                                          | shape          |
 *   |-------------------------------------------------------------|----------------|
 *   | `3 of 36 · 10d shown`                                        | coverage count |
 *   | `This round is 4 matches. Finished ones move to Finished…`   | method note    |
 *   | `Includes 43 qualifying matches.`                            | limitation     |
 *   | `Movement since 10 Aug.`                                     | method note    |
 *   | `Jannik Sinner: Last number 21 hours ago`                    | method note *  |
 *   | `▸ Does each column add up?  0 of 5 columns within tolerance`| self-audit     |
 *
 *   \* notice 34 quotes this one VERBATIM as an example of the banned class.
 *
 * ═══ THE FIXTURE IS THE ROUTE'S OWN OUTPUT ═══
 *
 * `docs/mocks/us-open/payload-2026-08-27.json` — the same committed payload
 * `__tests__/capture/usOpenBracketCapture.test.tsx` renders from, produced by
 * the real `build_boards` / `build_slate` / `build_results` / `build_grids`
 * over register v7 and a bounded production price read. A guard over a
 * hand-built fixture proves the phrase is absent from a page nobody visits;
 * this one renders the components off the payload production served.
 *
 * ═══ EVERY CASE ASSERTS A REMOVAL BESIDE A SURVIVAL ═══
 *
 * Inherited from the first sweep, and it is the whole discipline of the file:
 * *"A component that rendered nothing at all would satisfy a banned-phrase list,
 * and that is the obvious way for this guard to pass while the page is broken."*
 * So each component is proved to have rendered its NUMBERS before its prose is
 * proved absent. `renderedSomething` is the positive control.
 *
 * ═══ AND IT IS KEYED ON TEXT, NOT ON TESTIDS ═══
 *
 * The sibling suites (`playoffGrid`, `tournamentDeltaWindow`,
 * `tournamentCountsReconcile`, `tournamentAxisAndResults`, `tournamentP142`,
 * `usOpenBracketCapture`) each invert their own testid pin, which catches a
 * straight revert. They do NOT catch the regression that actually produced this
 * prose in the first place: a different lane answering a different cert adds
 * the same sentence back in a new element with a new testid. A phrase list
 * survives that, so this file is phrase-keyed and the testid pins stay where
 * they are.
 *
 * ═══ 🔴 WHAT THIS FILE MUST NOT BE READ AS SAYING ═══
 *
 * Removing `0 of 5 columns within tolerance` does not answer it. The Final
 * column really does sum to 2.5x and **#4174 is open and untouched**. The
 * check still runs, still discriminates, and still rides the section as
 * `data-sum-failing`; a reader is simply not handed our failing self-audit.
 * Ruling 4's actual prohibition — quietly rescaling the numbers until they add
 * up — is asserted intact in `playoffGrid.test.tsx`.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import ContenderChart from "@/components/tournament/ContenderChart";
import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import TournamentBoard from "@/components/tournament/TournamentBoard";
import TournamentMatches from "@/components/tournament/TournamentMatches";
import TournamentProps from "@/components/tournament/TournamentProps";
import TournamentResults from "@/components/tournament/TournamentResults";
import {
  matchListFromSlate,
  matchRoundReconciliation,
  matchRoundSize,
  matchesInRound,
} from "@/lib/matchList";
import { readPlayoffGrid, type PlayoffGrid as GridModel } from "@/lib/playoffGrid";
import type { TournamentPayload } from "@/lib/tournament";

const PAYLOAD = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, "..", "..", "..", "docs", "mocks", "us-open", "payload-2026-08-27.json"),
    "utf8"
  )
) as TournamentPayload;

const MENS_BOARD = PAYLOAD.boards[0];

function mensGrid(): GridModel {
  const grid = readPlayoffGrid(PAYLOAD.grids?.["mens-singles"]);
  if (grid === null) throw new Error("the committed payload carries no men's grid");
  return grid;
}

/**
 * ONE ENTRY PER BLOCK REMOVED, not a denylist of strings somebody noticed —
 * the maintenance rule the first sweep set. Each needle is anchored on the
 * clause that makes the sentence THIS block, so a rewording close to the
 * original still trips and a legitimate new caption does not need an exception.
 *
 * 🔴 The anchoring rule has already cost this lane once: a `not.toContain`
 * on the bare words "last quote" went red on a per-row label that legitimately
 * shares them. Never ban words a good string can also say.
 */
const BANNED: { block: string; needle: RegExp; arm?: string }[] = [
  // 1. ContenderChart's footer count + window.
  { block: "chart coverage count", needle: /\d+ of \d+\s*(<[^>]*>)?\s*·/ },
  { block: "chart window restatement", needle: /\d+d shown/i },
  // 2. TournamentMatches' round reconciliation.
  { block: "round size note", needle: /This round is \d+ matches/i },
  { block: "round grouping note", needle: /move to Finished, below/i },
  // 3. TournamentResults' population note — rendered here as an attribute, so
  //    the needle is anchored on the `>` a text node would carry.
  { block: "qualifying population note", needle: />\s*Includes \d+ qualifying/i },
  // 4. TournamentBoard's delta window.
  { block: "delta window note", needle: />\s*Movement since/i },
  // 5. TournamentProps' `labelled` freshness chip, in the page body.
  //    (The tooltip and sr-only copies are permitted — notice 34 names a
  //    tooltip on the source mark as the sanctioned home for exactly this.)
  //
  //    🔴 SCOPED TO THE PROPS ARM, AND THE REASON IS THE FINDING THAT SCOPED
  //    IT. Written unscoped, this needle went red on `TournamentMatches` —
  //    `slateRowFreshnessLabel` (lib/slate.ts) builds the SAME sentence for a
  //    quiet match row, and `rowFreshnessLabel` mirrors it on the boards. That
  //    is a real seventh instance of the banned shape on this page and it is
  //    FILED, not fixed here: it is 27 references across six source files with
  //    25 test assertions on the phrase, it needs a treatment a match row does
  //    not currently have (there is no `dot` variant for a slate row), and it
  //    was NOT rendering on production this morning — every match was fresh. A
  //    deadline sweep is the wrong place to widen by a two-surface refactor.
  //    Scoping it here rather than deleting the needle keeps the props chip
  //    guarded and leaves an accurate note for whoever takes the seventh.
  { block: "freshness sentence in body", needle: /Last number [^<"]*ago\s*<\/span>/i,
    arm: "props" },
  // 6. PlayoffGrid's self-audit.
  { block: "column self-audit summary", needle: /Does each column add up/i },
  { block: "column self-audit verdict", needle: /columns\s+within tolerance/i },
  { block: "monotonicity paragraph", needle: /higher chance for a later round/i },
  { block: "monotonicity justification", needle: /shown exactly as quoted/i },
];

/**
 * The positive control, applied to every render below. A component that threw,
 * short-circuited on a shape change in the payload, or rendered an empty state
 * would pass every `BANNED` case for the wrong reason — and an all-arms-empty
 * harness reading as a clean pass is a trap this lane has been bitten by.
 */
function renderedSomething(html: string, mustContain: string[]): void {
  expect(html.length).toBeGreaterThan(400);
  for (const needle of mustContain) expect(html).toContain(needle);
}

/**
 * `arm` is the name of the component being rendered. An entry with no `arm`
 * applies to every one of them — that is the default and it should stay the
 * default, because a page-wide ban is the point. An entry WITH an `arm` runs
 * only there, and the entry must say in a comment why it is narrowed; see the
 * freshness chip above for the one case that earns it.
 */
function assertNoBannedProse(arm: string, html: string): void {
  for (const { block, needle, arm: only } of BANNED) {
    if (only !== undefined && only !== arm) continue;
    // The block name rides the failure message: a bare regex in a red is a
    // puzzle, and this file exists to be read by whoever trips it.
    expect(`${arm}/${block}: ${needle.test(html) ? "PRESENT" : "absent"}`).toBe(
      `${arm}/${block}: absent`
    );
  }
}

describe("#4278 — the contender chart shows the chart, not a count of it", () => {
  it("draws its lines and its dated axis with no coverage sentence", () => {
    const html = renderToStaticMarkup(
      <ContenderChart
        rows={MENS_BOARD.rows}
        draw="mens-singles"
        selection={MENS_BOARD.rows.slice(0, 3).map((r) => r.entity_key)}
        onToggle={() => {}}
      />
    );
    // SURVIVAL: the picture and the window it covers are both still drawn, and
    // the axis is what states the window now.
    renderedSomething(html, ['data-testid="chart-axis"', 'data-testid="chart-series"']);
    assertNoBannedProse("chart", html);
  });
});

describe("#4278 — the match list stops explaining its own grouping", () => {
  /**
   * 🔴 THE SPECIMEN HAS TO REACH THE CODE, AND THE FIRST ONE DID NOT.
   *
   * Written as `matchListFromSlate(PAYLOAD.slate.matches)` this arm rendered
   * the whole committed slate — 113 entries, 96 of them R128 — and
   * `matchRoundReconciliation` returns `null` the moment `shown >= size`
   * (a round of 128 IS 64 matches, and the payload is a two-day order of play).
   * So the sentence was never built, the arm went green against a REVERTED
   * `TournamentMatches`, and the guard was decorative. Proved by reverting the
   * component and watching this file pass.
   *
   * The slice below puts `shown` under the round's size so the deleted branch
   * is live, and the reachability is ASSERTED rather than assumed.
   */
  const R128 = matchesInRound(matchListFromSlate(PAYLOAD.slate?.matches ?? []), "R128");
  const PARTIAL_ROUND = R128.slice(0, 10);

  it("has a specimen that reaches the deleted branch", () => {
    expect(PARTIAL_ROUND.length).toBe(10);
    expect(matchRoundSize("R128")).toBe(64);
    // The pure function, unchanged, still WANTS to say it. That is what makes
    // the render-side absence below meaningful.
    expect(matchRoundReconciliation("R128", PARTIAL_ROUND.length)).toContain(
      "This round is 64 matches"
    );
  });

  it("renders the round's matches with no reconciliation sentence", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={PARTIAL_ROUND} initialExpanded />
    );
    // SURVIVAL: the matches and the column header a reader came for.
    renderedSomething(html, ['data-testid="tournament-matches"', 'data-testid="match-column-header"']);
    assertNoBannedProse("matches", html);
  });
});

describe("#4278 — the finished list stops qualifying its own total", () => {
  it("renders the results with the population note as an attribute", () => {
    // The committed payload's results are 76 matches, all of them qualifying,
    // so `resultsPopulationNote` is non-null and the deleted branch is live.
    // (This arm did not exist at first, and its absence is why reverting
    // `TournamentResults` left the guard green — a banned phrase nobody
    // renders is a phrase nobody is guarding.)
    const results = PAYLOAD.results;
    expect(results).toBeTruthy();
    const html = renderToStaticMarkup(
      <TournamentResults results={results!} draw="mens-singles" />
    );
    // SURVIVAL: the finished rows and the total itself.
    renderedSomething(html, ['data-testid="tournament-results"']);
    assertNoBannedProse("results", html);
    // ...and the fact still travels for probes.
    expect(html).toMatch(/data-population-note="Includes \d+ qualifying match/);
  });
});

describe("#4278 — the contenders board stops footnoting its own deltas", () => {
  it("renders the rows and carries the window as an attribute", () => {
    const html = renderToStaticMarkup(<TournamentBoard board={MENS_BOARD} />);
    // SURVIVAL: the board rendered, and the deleted sentence is still readable
    // by a probe rather than destroyed.
    renderedSomething(html, ['data-testid="tournament-board"']);
    // THE BAN RUNS BEFORE THE RELOCATION CHECK, deliberately. Reverting
    // `TournamentBoard` reds either way, but with the order flipped the failure
    // read "expected data-delta-window=" — true, and useless: it names the new
    // attribute, not the sentence that came back. Whoever trips this guard
    // should be told which BLOCK returned, which is what `assertNoBannedProse`
    // prints. Same reason the grid arm bans before it counts cells.
    assertNoBannedProse("board", html);
    expect(html).toContain("data-delta-window=");
  });
});

describe("#4278 — the grid stops printing its own failing self-check", () => {
  it("renders every cell and reports the audit only to machines", () => {
    const grid = mensGrid();
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid} initialExpanded />);
    // SURVIVAL, and the one that matters most: the numbers are all still there.
    // If the sweep had taken the grid with the caption this is what would red.
    renderedSomething(html, ['data-testid="playoff-grid"', 'data-testid="grid-cell"']);
    expect((html.match(/data-testid="grid-cell"/g) ?? []).length).toBe(grid.totalCells);
    assertNoBannedProse("grid", html);

    // 🔴 AND THE CHECK STILL RAN. #4174 is open; this ship hid a sentence, not
    // a defect. The committed payload's men's Final column is the known `over`.
    const failing = grid.columnSums.filter((c) => c.verdict !== "pass").length;
    expect(failing).toBeGreaterThan(0);
    expect(html).toContain(`data-sum-failing="${failing}"`);
  });
});

describe("#4278 / #4251 — a quiet prop shows a mark, not a sentence", () => {
  it("takes the default variant and prints no freshness prose in the body", () => {
    // NO `variant` PROP. The whole point is that PRODUCTION's default is what
    // is being asserted; passing `variant="dot"` here would test the seam and
    // prove nothing about the page.
    const html = renderToStaticMarkup(
      <TournamentProps markets={PAYLOAD.props ?? []} draw="mens-singles" />
    );
    // SURVIVAL: the questions and their numbers are all still drawn.
    renderedSomething(html, ['data-testid="prop-market"']);
    assertNoBannedProse("props", html);

    // 🔴 UNCONDITIONAL, AND THAT IS DELIBERATE. Written as
    // `if (html.includes("prop-age"))` this whole block would pass silently on
    // a payload whose props all happened to be fresh, which is the same class
    // of vacuous green as an empty-render `not.toContain`. The committed
    // payload's two props are 34 days and 8 days old, so the marks are always
    // drawn; if that ever stops being true this line is what says so.
    expect((html.match(/data-testid="prop-age"/g) ?? []).length).toBe(2);

    // AND THE FACT IS NOT DESTROYED, it moved to where notice 34 puts it: a
    // tooltip on the mark, plus the screen-reader copy. This is the assertion
    // that separates "we obeyed the notice" from "we deleted the information".
    expect(html).toContain('data-variant="dot"');
    expect(html).not.toContain('data-variant="labelled"');
    expect(html).toMatch(/title="Last number [^"]*ago"/);
    expect(html).toMatch(/class="sr-only">Last number [^<]*ago/);
    // The "which leg is old" prefix under `dot` is guarded where its fixture
    // already lives — `tournamentPickerRotation.test.tsx`, "a two-market card
    // is as OLD as its oldest leg". That case is what caught the regression the
    // default switch nearly shipped; a second, weaker copy here would be the
    // exact duplication the first sweep's header warns against.
  });
});

describe("#4278 — the guard can fail", () => {
  it("trips on every banned block when the prose is present", () => {
    // WITHOUT THIS THE WHOLE FILE IS UNFALSIFIABLE. A `not.toContain` suite
    // passes just as happily against a regex that matches nothing as against a
    // clean page, and a typo in a needle is invisible. Every needle is proved
    // to match the sentence it was written for.
    const specimens: Record<string, string> = {
      "chart coverage count": "<span>3 of 36<span> · </span></span>",
      "chart window restatement": "<span> · 10d shown</span>",
      "round size note": "<p>This round is 4 matches. Finished ones move to Finished, below.</p>",
      "round grouping note": "<p>Finished ones move to Finished, below.</p>",
      "qualifying population note": "<p>Includes 43 qualifying matches.</p>",
      "delta window note": "<div>Movement since 10 Aug.</div>",
      "freshness sentence in body":
        '<span data-variant="labelled">Jannik Sinner: Last number 21 hours ago</span>',
      "column self-audit summary": "<summary>Does each column add up? </summary>",
      "column self-audit verdict": "<span>0 of 5 columns within tolerance</span>",
      "monotonicity paragraph": "<p>1 player has a higher chance for a later round than an earlier one</p>",
      "monotonicity justification": "<p>the market disagreeing with itself, shown exactly as quoted.</p>",
    };
    // Every entry in BANNED has a specimen, and no specimen is orphaned — so
    // adding a needle without proving it, or renaming a block, both red.
    expect(Object.keys(specimens).sort()).toEqual([...new Set(BANNED.map((b) => b.block))].sort());
    for (const { block, needle } of BANNED) {
      expect(`${block}: ${needle.test(specimens[block])}`).toBe(`${block}: true`);
    }
  });
});
