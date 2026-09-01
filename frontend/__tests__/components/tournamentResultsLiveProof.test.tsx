/**
 * #2568 — THE LIVE PRODUCTION PAYLOAD, DRIVEN THROUGH THE REAL COMPONENT.
 *
 * `tournamentResultsLink.test.tsx` is the guard: hand-built rows, arms, controls.
 * This is the EVIDENCE, and it is a different claim. The guard says "given a map
 * entry, the component makes a link"; this says "given the bytes production
 * served at 2026-09-01 22:59Z, the Men's FINISHED list goes from zero clickable
 * rows to twenty-eight" — and it says it by rendering the shipped component
 * over the real payload rather than by reasoning about it. (The page total the
 * shopper counted, 1 of 100, includes the slate's 11 rows one list up; this
 * file is only about the 90 below them.)
 *
 * ═══ WHY THIS EXISTS INSTEAD OF A SCREENSHOT ═══
 *
 * Two reasons, and the first is the stronger one.
 *
 * 1. **A dead link is invisible in a screenshot.** The row that navigates and
 *    the row that does nothing are the same pixels — which is exactly how this
 *    defect survived four mystery-shopper passes over this page. The finding
 *    that produced #2568 came from dumping `a[href]` out of the DOM, not from
 *    looking. So an anchor inventory is the right instrument here even when a
 *    camera is available.
 * 2. A deploy freeze was in force when this shipped (STANDING-NOTICES item 2:
 *    no lane merges until `/api/calibration` publishes 2026-09-02-dated output),
 *    so the production page could not yet be re-shot. This file is what makes
 *    the claim checkable in the meantime, and it does not expire when the page
 *    is finally re-shot — it keeps being the regression guard over real bytes.
 *
 * ═══ THE FIXTURE IS UNEDITED ═══
 *
 * `tournamentHubUsOpen.20260901.json` is `curl $BAINLUCK_API/api/tournaments/us-open`
 * with four top-level keys kept verbatim — `generated_at`, `slug`, `results`,
 * `event_links` — and the boards/props/grids/bracket bulk dropped so the file is
 * 270KB instead of 750KB. Nothing inside the two keys under test was touched:
 * 194 finished matches, a 67-entry `by_matchup`, exactly as served. If it is
 * ever refreshed the numbers below move, and they SHOULD — they are measurements
 * of a real day, and the assertions are written as relations that survive a new
 * capture (the linked count equals the resolvable count) plus one hard number
 * that pins the day this was measured.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentResults from "@/components/tournament/TournamentResults";
import {
  resultEventHref,
  resultsForDraw,
  type TournamentResults as ResultsModel,
} from "@/lib/tournamentResults";

import LIVE from "../fixtures/tournamentHubUsOpen.20260901.json";

const RESULTS = LIVE.results as unknown as ResultsModel;
const BY_MATCHUP = LIVE.event_links.by_matchup as Record<string, number>;

function render(
  draw: string,
  eventIds?: Record<string, number> | null
): string {
  return renderToStaticMarkup(
    <TournamentResults
      results={RESULTS}
      draw={draw}
      eventIds={eventIds}
      initialExpanded
    />
  );
}

function eventHrefs(html: string): string[] {
  return Array.from(html.matchAll(/\shref="(\/events\/\d+)"/g)).map((m) => m[1]);
}

describe("the payload production served on 2026-09-01 at 22:59Z", () => {
  it("is the real thing and not a trimmed sample", () => {
    // The control for everything below. A fixture that quietly lost its
    // `by_matchup` would make the RED arm and the GREEN arm agree at zero.
    expect(RESULTS.matches.length).toBeGreaterThan(150);
    expect(Object.keys(BY_MATCHUP).length).toBeGreaterThan(50);
    expect(LIVE.generated_at).toContain("2026-09-01");
  });

  it("BEFORE: the Men's finished list served ZERO links", () => {
    // The shipped defect, over the real bytes. 90 rows, none of them clickable.
    // The one link the shopper found was on the SLATE, one list up the page.
    const html = render("mens-singles", undefined);
    expect(eventHrefs(html)).toEqual([]);
    expect(html).toContain('data-testid="result-row"');
  });

  it("AFTER: the Men's finished list serves 28 links over the same bytes", () => {
    const html = render("mens-singles", BY_MATCHUP);
    const hrefs = eventHrefs(html);

    expect(hrefs).toHaveLength(28);
    // Every one of them is a distinct event page — a bug that pointed 28 rows
    // at one event would satisfy a bare count.
    expect(new Set(hrefs).size).toBe(28);
  });

  it("links exactly the rows the SERVER resolved — no more, no fewer", () => {
    const mens = resultsForDraw(RESULTS, "mens-singles");
    const resolvable = mens.filter(
      (m) => resultEventHref(m, BY_MATCHUP) !== null
    );
    const html = render("mens-singles", BY_MATCHUP);

    expect(eventHrefs(html)).toHaveLength(resolvable.length);
    // The relation, not the number: the page's link set IS the server's
    // resolution set. This is the assertion that survives a fixture refresh.
    expect(new Set(eventHrefs(html))).toEqual(
      new Set(resolvable.map((m) => resultEventHref(m, BY_MATCHUP)))
    );
  });

  it("the women's draw moves too, and the two draws do not share links", () => {
    const mens = new Set(eventHrefs(render("mens-singles", BY_MATCHUP)));
    const womens = new Set(eventHrefs(render("womens-singles", BY_MATCHUP)));

    expect(womens.size).toBeGreaterThan(0);
    // Disjoint: a men's match and a women's match are never the same event.
    // A join keyed on something looser than `matchup_key` would show up here.
    for (const href of womens) expect(mens.has(href)).toBe(false);
  });

  it("leaves the unroutable rows on the page, and says how many", () => {
    const html = render("mens-singles", BY_MATCHUP);
    const rows = html.match(/data-testid="result-row"/g) ?? [];
    const mens = resultsForDraw(RESULTS, "mens-singles");

    // 90 rows in this capture — the shopper counted 89 twenty minutes earlier
    // and a match finished in between, which is the point of deriving the
    // denominator rather than freezing it. Every row is still rendered: this
    // fix adds links, it does not hide the matches it cannot route.
    expect(rows.length).toBe(mens.length);
    expect(mens.length).toBeGreaterThan(80);
    expect(html).toContain('data-testid="results-link-note"');
    expect(html).toContain(`28 of ${mens.length}`);
  });

  it("never routes one of the 90 ESPN-only rows", () => {
    // The half of the residue that is structural: these finished matches have
    // no register matchup, so no market, so no event. Guarded over real keys.
    const espnOnly = RESULTS.matches.filter((m) =>
      m.matchup_key.startsWith("espn:")
    );
    expect(espnOnly.length).toBeGreaterThan(50);
    for (const match of espnOnly) {
      expect(resultEventHref(match, BY_MATCHUP)).toBeNull();
    }
  });
});
