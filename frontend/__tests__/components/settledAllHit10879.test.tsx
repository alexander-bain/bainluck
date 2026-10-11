import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import PlayerPropsDashboard from "../../components/PlayerPropsDashboard";
import type { GameMarketsResponse } from "../../lib/api";
import { groupPlayerPropsWithCoverage, type PlayerPropRow } from "../../lib/playerPropsGrouping";
import fixture from "../fixtures/settledAllHit10879.json";

// The exact public Points rows captured alongside the 390px BEFORE on
// /events/15327330: all-hit Nylander/Matthews/Paul and split MacKinnon.
function rowsFor(name: string): PlayerPropRow[] {
  const rows = fixture.player_props.filter((r) => r.outcome_name.startsWith(`${name}:`));
  if (!rows.length) throw new Error(`Missing specimen: ${name}`);
  return rows as PlayerPropRow[];
}

function render(rows: PlayerPropRow[], compact = false, eventStatus = "completed") {
  return renderToStaticMarkup(<PlayerPropsDashboard
    data={{ player_props: rows, other: [] } as unknown as GameMarketsResponse}
    compact={compact} eventStatus={eventStatus}
    homeTeam={fixture.home_team} awayTeam={fixture.away_team}
  />);
}

describe.each([false, true])("#10879 settled highest HIT (compact=%s)", (compact) => {
  test.each([
    ["William Nylander", 5, 3],
    ["Auston Matthews", 4, 3],
    ["Nick Paul", 2, 2],
  ])("%s states the highest published HIT beside its actual", (name, actual, line) => {
    const html = render(rowsFor(name as string), compact);
    expect(html).toContain(name);
    expect(html).toMatch(new RegExp(`>${actual}</div>`));
    expect(html).toMatch(new RegExp(`HIT</span><span[^>]*>${line}\\+`));
    expect(html).not.toContain("of 1");
    expect(html).not.toContain("needed 1+");
  });

  test("the split ladder still states both typed boundaries", () => {
    const html = render(rowsFor("Nathan MacKinnon"), compact);
    expect(html).toContain('data-settled-ladder="split"');
    expect(html).toMatch(/>2<\/div>/);
    expect(html).toMatch(/HIT<\/span><span[^>]*>2\+/);
    expect(html).toMatch(/MISS<\/span><span[^>]*>3\+/);
  });

  test("null actuals have no number row, but retain the typed upper HIT", () => {
    const html = render(rowsFor("Nick Paul").map((r) => ({ ...r, actual: null })), compact);
    expect(html).not.toContain('data-testid="prop-tile-actual"');
    expect(html).not.toContain("—");
    expect(html).toMatch(/HIT<\/span><span[^>]*>2\+/);
  });

  test("a zero count is retained, without adjudicating against the line", () => {
    const html = render(rowsFor("Nick Paul").map((r) => ({ ...r, actual: 0 })), compact);
    expect(html).toMatch(/>0<\/div>/);
    expect(html).toMatch(/HIT<\/span><span[^>]*>2\+/);
    expect(html).not.toContain("MISS");
  });

  test("all-miss ladders keep the lowest target", () => {
    const html = render(rowsFor("William Nylander").map((r) => ({ ...r, hit: false, actual: 0 })), compact);
    expect(html).toContain("MISS");
    expect(html).toContain("needed 1+");
    expect(html).toContain("of 1");
    expect(html).not.toContain("HIT");
  });

  test("an ungraded upper rung is not promoted by a group HIT or large count", () => {
    const rows = rowsFor("William Nylander").map((r) => ({ ...r, hit: r.threshold === 1 ? true : null }));
    const html = render(rows, compact);
    expect(html).toContain("needed 1+");
    expect(html).not.toMatch(/HIT<\/span><span[^>]*>3\+/);
  });

  test("actual-only and ungraded groups never gain a HIT", () => {
    for (const actual of [5, null]) {
      const html = render(rowsFor("William Nylander").map((r) => ({ ...r, hit: null, actual })), compact);
      expect(html).not.toContain("HIT");
      expect(html).not.toContain("MISS");
      if (actual === null) expect(html).toContain("grading unavailable");
    }
  });

  test("a contradictory duplicate verdict cannot use the all-hit summary", () => {
    const rows = rowsFor("William Nylander");
    const html = render([...rows, { ...rows[2], hit: false, source: "polymarket" }], compact);
    expect(html).toContain("grading unavailable");
    expect(html).not.toContain("HIT");
  });

  test("Under MISS twins arriving first do not reverse the Over HITs", () => {
    const rows = rowsFor("William Nylander");
    const unders = rows.map((r) => ({ ...r, _inverted: true, hit: false }));
    const html = render([...unders, ...rows], compact);
    expect(html).toMatch(/HIT<\/span><span[^>]*>3\+/);
    expect(html).not.toContain("MISS");
  });

  test("an Under-only upper rung cannot become a higher Over HIT", () => {
    const rows = rowsFor("William Nylander");
    const html = render([...rows, { ...rows[2], threshold: 4, outcome_name: "William Nylander: 4+", _inverted: true, hit: true }], compact);
    expect(html).toContain("needed 1+");
    expect(html).not.toMatch(/HIT<\/span><span[^>]*>4\+/);
  });

  test("one target retains its existing presentation", () => {
    const html = render(rowsFor("Nick Paul").slice(0, 1), compact);
    expect(html).toContain("needed 1+");
    expect(html).toContain("of 1");
  });

  test.each(["scheduled", "live"])("%s does not use the settled summary", (phase) => {
    const rows = rowsFor("Nick Paul");
    // A final payload on a non-final phase is deliberate: the rendering gate,
    // not missing data in a fixture, must prevent a settled-only label leak.
    const html = render(rows, compact, phase);
    expect(html).toContain("Nick Paul");
    expect(html).toContain("Points");
    expect(html).toContain(!compact && phase === "live" ? "of 1 so far" : "1+");
    expect(html).not.toMatch(/HIT<\/span><span[^>]*>2\+/);
  });
});

test("two-rung layout and pregame coverage stay at their existing first line", () => {
  const rows = rowsFor("Nick Paul");
  const { players, representedScriptKeys } = groupPlayerPropsWithCoverage({ playerProps: rows });
  expect(players[0].stats[0]).toMatchObject({ shape: "line", threshold: 1, settledAllHitLine: 2 });
  expect([...representedScriptKeys]).toEqual([`${rows[0].market_name}|${rows[0].outcome_name}`]);
});

test("input order does not select the displayed highest HIT", () => {
  const rows = rowsFor("William Nylander");
  expect(render([...rows].reverse(), true)).toBe(render(rows, true));
});
