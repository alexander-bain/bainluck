/**
 * #7405 — a 65% favourite wore "OUT" because the badge had no `null` branch.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/sport/soccer/usa-mls/team/fc-cincinnati`, production, 390px, 2026-09-20
 * (`artifacts-lane1-482/cin-out-row.png`). The "To Score" prop-race card:
 *
 *     FC Cincinnati vs Pumas U…        ✓ WON   100%
 *     FC Cincinnati vs New York…       ✓ WON   100%
 *     … eight more ✓ WON rows …
 *     FC Cincinnati vs DC United: …     OUT     65%      <- stated as fact
 *
 * The page asserted FC Cincinnati did not score first. We had no such fact:
 * all three outcomes of market 60521194 were `is_winner IS NULL` /
 * `resolution_source IS NULL`, and the market's own price made FC Cincinnati
 * the 65% favourite. Ten graded rows said "won"; the one ungraded row was the
 * only one given a negative verdict.
 *
 * ═══ MECHANISM ═══
 *
 * `WhatHitBadge` branched on one of three states:
 *
 *     if (result === "won") return <…>✓ Won</…>;
 *     return <…>Out</…>;                      // null fell in with "lost"
 *
 * The prop type is `"won" | "lost" | null`. The backend populates all three and
 * means them: `utils/prop_families.py::_settled_status` leaves `result` as None
 * deliberately when it can mark a row settled but cannot grade it — a terminal
 * market with no graded outcome, or one settled by `resolution_date` alone.
 * Market-level family rows carry `outcome_id: null`, so the "read the grade off
 * the outcome" guard cannot fire and `result` stays None for all of them.
 *
 * The backend was never wrong. The render collapsed "we don't know" into "no".
 *
 * ═══ REACH, MEASURED, NOT MODELLED ═══
 *
 * 120 team slugs swept against `GET /api/teams/{slug}/prop-families`,
 * 2026-09-20 07:3xZ — the full `(settled, result)` state space:
 *
 *     (false, null)   370   live rows
 *     (true,  null)   330   settled, ungraded  -> rendered "OUT"
 *     (true,  "won")  247
 *     (true,  "lost") 110   the only genuine losses
 *
 * So of the 440 rows that rendered an "OUT" badge, **330 of them — 75% — were
 * fabricated**, across 32 of the 120 teams. That is not a claim that 330 rows
 * were factually wrong; most sit at <=1% where "Out" is right by luck. It is
 * the sharper point: the badge's correctness was unrelated to our evidence, and
 * the hazard concentrated exactly where the price was high.
 *
 * ═══ WHY THE NULL ROW STILL GETS A BADGE ═══
 *
 * Rendering nothing was the tempting fix and it is the wrong one. The row keeps
 * its probability, and a settled-but-unmarked row with a live-looking price is
 * the #6595->#5481 / #6169->#6815 failure — withholding the field moves the lie
 * into the price channel, which has no marker at all. Grey styling does not
 * count: a first-time reader reads grey as "old", not "unknown".
 *
 * ═══ WHAT THIS GUARD IS FOR ═══
 *
 * Both directions, so it cannot pass by widening:
 *   - a `null` row must NOT read the same as a `"lost"` row, and
 *   - a real `"lost"` row must STILL read "Out" (the fix must not soften a
 *     genuine loss into "no result"), and a `"won"` row must still read "✓ Won".
 *
 * Fixtures are production payloads, not hand-built objects: a malformed fake
 * would drive the component down a branch that looks like a principled refusal.
 */

import { renderToStaticMarkup } from "react-dom/server";
import { TeamPropFamilies } from "@/components/TeamPropFamilies";
import type { PropFamily } from "@/lib/api";

import cincinnatiToScore from "./fixtures/teamPropFamilies.fcCincinnati.toScore.json";
import seahawksLost from "./fixtures/teamPropFamilies.seahawks.lostRows.json";

const CINCINNATI = cincinnatiToScore as unknown as PropFamily;
const SEAHAWKS = seahawksLost as unknown as PropFamily;

/**
 * The badge texts a reader sees, in order.
 *
 * Scoped to the badge element by its `rounded-full` class rather than searched
 * for as bare substrings: "Out" is a substring of entity names and of class
 * names, so a `toContain("Out")` over the whole markup would be answering a
 * different question than the one this file asks.
 */
function badgeTexts(markup: string): string[] {
  return [...markup.matchAll(/<span class="rounded-full[^"]*">([^<]*)<\/span>/g)].map((m) =>
    m[1].trim(),
  );
}

function render(family: PropFamily): string {
  return renderToStaticMarkup(
    <TeamPropFamilies families={[family]} teamColor="#003087" />,
  );
}

describe("#7405 — an ungraded settled prop-race row is not a loss", () => {
  it("the fixtures are the real thing: one settled+ungraded row, and two real losses", () => {
    // Non-vacuity: the badge only renders under `row.settled`, so a fixture of
    // live rows would exercise nothing at all.
    const ungraded = CINCINNATI.rows.filter((r) => r.settled && r.result === null);
    expect(ungraded).toHaveLength(1);
    expect(ungraded[0].entity).toContain("DC United");
    expect(ungraded[0].probability).toBeCloseTo(0.65, 2);

    expect(CINCINNATI.rows.filter((r) => r.result === "won")).toHaveLength(10);
    expect(CINCINNATI.rows.filter((r) => r.result === "lost")).toHaveLength(0);

    expect(SEAHAWKS.rows.filter((r) => r.settled && r.result === "lost")).toHaveLength(2);
  });

  it("the 65% ungraded row does NOT claim a negative result", () => {
    const badges = badgeTexts(render(CINCINNATI));

    expect(badges).toHaveLength(11);
    expect(badges.filter((b) => b === "✓ Won")).toHaveLength(10);
    expect(badges.filter((b) => b === "No result")).toHaveLength(1);
    // The defect, stated as the assertion that would have caught it.
    expect(badges).not.toContain("Out");
  });

  it("a genuine loss STILL reads 'Out' — the fix must not soften a real verdict", () => {
    const badges = badgeTexts(render(SEAHAWKS));

    expect(badges).toHaveLength(2);
    expect(badges.filter((b) => b === "Out")).toHaveLength(2);
    expect(badges).not.toContain("No result");
  });

  it("the three states render three DISTINCT badges", () => {
    const all = [...badgeTexts(render(CINCINNATI)), ...badgeTexts(render(SEAHAWKS))];
    const distinct = new Set(all);

    expect(distinct).toEqual(new Set(["✓ Won", "No result", "Out"]));
    // A fix that merged any two states back together would shrink this set —
    // including the original defect, which had only {"✓ Won", "Out"}.
    expect(distinct.size).toBe(3);
  });
});
