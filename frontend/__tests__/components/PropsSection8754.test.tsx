// #8754 — THE DIVERGENCE printed `67% → 67% ↑ 1` on a live game.
//
// `/events/15315945` (Northwestern @ Indiana, LIVE, 2026-09-26 00:40Z, 390px)
// served `Team Receiving Touchdowns`, a five-leg non-complement family. Two of
// its legs moved exactly half a point off a `.5` mark:
//
//   Indiana: 2+   0.665 → 0.67   printed `67% → 67%  ↑ 1`
//   Indiana: 3+   0.425 → 0.43   printed `43% → 43%  ↑ 1`
//
// Both levels round up to the same whole number, and so does the half-point raw
// move. #5296 gave complement pairs #2951's rule (a printed delta is the
// difference of the printed levels); every other row kept the raw difference.
// The same page's "What's moving" rail spent its 4th of 5 slots on
// `Indiana: 2+ … opened 67% · now 67%` because its `direction` was a raw
// half-point floor that 0.005 does not fall below.
//
// The rows below are the served `props_script` / `player_props` values verbatim.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";
import {
  railPercentPoints,
  selectDivergenceDetail,
  selectDivergenceRows,
  type DivergenceRow,
} from "../../lib/propDivergence";
import type { PlayerPropRow } from "../../lib/playerPropsGrouping";

const FAMILY = "Northwestern vs Indiana: Team Receiving Touchdowns";

const SCRIPT: PropMark[] = [
  { key: `${FAMILY}|Indiana: 2+`, label: "Indiana: 2+", pregame_mark: 0.665, current: 0.67 },
  { key: `${FAMILY}|Indiana: 3+`, label: "Indiana: 3+", pregame_mark: 0.425, current: 0.43 },
  { key: `${FAMILY}|Indiana: 4+`, label: "Indiana: 4+", pregame_mark: 0.235, current: 0.36 },
  { key: `${FAMILY}|Northwestern: 2+`, label: "Northwestern: 2+", pregame_mark: 0.27, current: 0.39 },
  { key: `${FAMILY}|Northwestern: 3+`, label: "Northwestern: 3+", pregame_mark: 0.09, current: 0.32 },
];

const divergence = (items: PropMark[]) =>
  renderToStaticMarkup(<PropsSection items={items} state="divergence" />);

/** The rendered row for one label: from its label to the next row's label. */
function rowHtml(html: string, label: string): string {
  const at = html.indexOf(`>${label}<`);
  expect(at).toBeGreaterThan(-1);
  const next = SCRIPT.map((r) => html.indexOf(`>${r.label}<`, at + 1)).filter((i) => i > at);
  return html.slice(at, next.length ? Math.min(...next) : undefined);
}

describe("THE DIVERGENCE — an unpaired row's badge is the difference of its printed levels", () => {
  test("Indiana: 2+ (0.665 → 0.67) prints no ↑ 1 between two 67s", () => {
    const html = divergence(SCRIPT);
    expect(html).not.toMatch(/67%[\s\S]{0,400}↑ 1/);
  });

  test("Indiana: 3+ (0.425 → 0.43) prints no ↑ 1 between two 43s", () => {
    const html = divergence(SCRIPT);
    expect(html).not.toMatch(/43%[\s\S]{0,400}↑ 1/);
  });

  test("the two half-point rows are partitioned as unchanged, by the number they print", () => {
    // They leave the moved list for the "didn't move" drawer; before, the raw
    // rounding kept them in the moved list carrying ↑ 1.
    const html = divergence(SCRIPT);
    const moved = html.slice(0, html.indexOf("<details"));
    expect(moved).not.toContain(">Indiana: 2+<");
    expect(moved).not.toContain(">Indiana: 3+<");
  });

  test("Indiana: 4+ (0.235 → 0.36) prints ↑ 12 between 24% and 36%, not ↑ 13", () => {
    // The same page printed `24% → 36% ↑ 13`: the raw move is 12.5 points and
    // rounds up, while the printed levels differ by 12. Same defect, other side.
    const row = rowHtml(divergence(SCRIPT), "Indiana: 4+");
    expect(row).toContain("24% →");
    expect(row).toContain("36%");
    expect(row).toContain("↑ 12");
    expect(row).not.toContain("↑ 13");
  });

  test("CONTROL: rows whose raw and printed moves agree keep their exact badges", () => {
    const html = divergence(SCRIPT);
    expect(rowHtml(html, "Northwestern: 3+")).toContain("↑ 23");
    expect(rowHtml(html, "Northwestern: 2+")).toContain("↑ 12");
  });

  test("a sub-point raw move that crosses a whole number prints its point", () => {
    // 0.674 → 0.676 is a raw 0.2 of a point, printed 67% → 68%. The raw rounding
    // said ±0; the printed levels say ↑ 1, and the printed levels are what the
    // reader holds the badge against.
    const html = divergence([
      { key: `${FAMILY}|Indiana: 2+`, label: "Indiana: 2+", pregame_mark: 0.674, current: 0.676 },
      { key: `${FAMILY}|Indiana: 3+`, label: "Indiana: 3+", pregame_mark: 0.3, current: 0.5 },
      { key: `${FAMILY}|Indiana: 4+`, label: "Indiana: 4+", pregame_mark: 0.2, current: 0.4 },
    ]);
    expect(rowHtml(html, "Indiana: 2+")).toContain("↑ 1");
  });
});

// ── The rail ─────────────────────────────────────────────────────────────────

function rung(outcome: string, line: number, mark: number, current: number): PlayerPropRow {
  return {
    market_name: FAMILY,
    outcome_name: outcome,
    threshold: line,
    over_probability: current,
    pregame_mark: mark,
    source: "kalshi",
  } as unknown as PlayerPropRow;
}

const RUNGS: PlayerPropRow[] = [
  rung("Indiana: 2+", 2, 0.665, 0.67),
  rung("Indiana: 3+", 3, 0.425, 0.43),
  rung("Indiana: 4+", 4, 0.235, 0.36),
  rung("Northwestern: 2+", 2, 0.27, 0.39),
  rung("Northwestern: 3+", 3, 0.09, 0.32),
];

function candidates(rows: PlayerPropRow[], status: string): DivergenceRow[] {
  const d = selectDivergenceDetail({ playerProps: rows, status });
  return [...d.offScript, ...d.onScript, ...d.ungraded];
}

describe("What's moving — a row is flat exactly when both ends print the same number", () => {
  test("the served half-point rows are flat on a live page", () => {
    const rows = candidates(RUNGS, "live");
    const two = rows.find((r) => r.player === "Indiana" && r.threshold === 2)!;
    const three = rows.find((r) => r.player === "Indiana" && r.threshold === 3)!;
    expect(two.direction).toBe("flat");
    expect(three.direction).toBe("flat");
  });

  test("live, the 67 → 67 rung is drawn flat, after every real mover", () => {
    // Production drew `Indiana: 2+ … opened 67% · now 67%` 4th of 5 with a green
    // journey. It still fills the slot (the live rail fills to five), but its bar
    // now says what its numbers say.
    const { rows } = selectDivergenceRows({ playerProps: RUNGS, status: "live" });
    expect(rows.map((r) => [`${r.player} ${r.threshold}`, r.direction])).toEqual([
      ["Northwestern 3", "over"],
      ["Indiana 4", "over"],
      ["Northwestern 2", "over"],
      ["Indiana 2", "flat"],
    ]);
  });

  test("a sub-point move across a whole number is a mover, not flat", () => {
    const rows = candidates([rung("Indiana: 2+", 2, 0.674, 0.676)], "live");
    expect(rows[0].direction).toBe("over");
  });

  test("the bar's printed ends and its direction use one rounding", () => {
    for (const row of candidates(RUNGS, "live")) {
      expect(row.direction === "flat").toBe(
        railPercentPoints(row.pregameMark) === railPercentPoints(row.current),
      );
    }
  });
});
