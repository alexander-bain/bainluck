// #1626 slice 4 — THE SCRIPT prints one row per player ladder.
//
// Browns @ Steelers (`/events/14780550`, scheduled, 390px, 2026-10-01): after
// slice 3 the pregame board still printed a row per RUNG — under PASSING YARDS,
// `Aaron Rodgers: 150+` through `325+` was eight rows; 22 such ladders held 138
// rows on a page 16,864px tall. Each ladder is now one row (the highest rung the
// script favours) with every rung behind its disclosure.
//
// The fixture is slice 3's: that page's served `props_script`, banked from
// `GET /api/events/14780550/game-markets` at 06:15Z 10/1.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection, { scriptLadders } from "../../components/event/PropsSection";
import type { PropMark, ScriptLadder } from "../../components/event/PropsSection";
import { propLabelDisplay } from "../../lib/playerPropsGrouping";
import specimen from "../fixtures/props_script_14780550_1626.json";

const MATCHUP = { home: "Pittsburgh Steelers", away: "Cleveland Browns" };

const served: PropMark[] = specimen.props_script.map((p, i) => ({
  key: p.key ?? i,
  label: p.label,
  pregame_mark: p.pregame_mark ?? null,
  current: p.current ?? null,
  settled: p.settled ?? null,
}));

const render = (items: PropMark[], state: "script" | "divergence" | "graded" = "script") =>
  renderToStaticMarkup(<PropsSection items={items} state={state} matchup={MATCHUP} />);

/** The closed ladder rows: subject, rung, printed percent, "+N more". */
function ladderSummaries(html: string): Array<[string, string, string, string]> {
  return [
    ...html.matchAll(
      /<summary class="flex[^"]*"><span[^>]*>([^<]+)<\/span><span[^>]*>([^<]+)<\/span><span[^>]*>([^<]+)<\/span><span[^>]*>([^<]+)<\/span><\/summary>/g,
    ),
  ].map((m) => [m[1], m[2], m[3], m[4]]);
}

/** Every row label printed outside any ladder disclosure. */
function visibleRowLabels(html: string): string[] {
  const outside = html.replace(/<details class="border-b[^"]*">[\s\S]*?<\/details>/g, "");
  return [...outside.matchAll(/line-clamp-2">([^<]+)<\/span>/g)].map((m) => m[1]);
}

const rungs = (subject: string, values: Array<[number, number | null]>): PropMark[] =>
  values.map(([n, p]) => ({
    key: `M: Passing Yards|${subject}: ${n}+`,
    label: `${subject}: ${n}+`,
    pregame_mark: p,
    current: p,
  }));

describe("#1626 SHIP: on the served Browns @ Steelers page, a player's ladder is one row", () => {
  const html = render(served);
  // Slice 5's O/U ladders share the row markup; this slice counts its own,
  // the `N+` ladders.
  const summaries = ladderSummaries(html).filter((s) => s[1].endsWith("+"));

  test("Aaron Rodgers' passing yards read as one row: 200+, 58%, the other seven behind it", () => {
    expect(summaries).toContainEqual(["Aaron Rodgers", "200+", "58%", "+7 more"]);
    expect(visibleRowLabels(html)).not.toContain("Aaron Rodgers: 150+");
    expect(visibleRowLabels(html)).not.toContain("Aaron Rodgers: 325+");
  });

  // AMENDED by slice 6 (2026-10-01): two-rung ladders join, so the count is 24
  // ladders over 142 rungs — slice 4's 22 / 138 plus Jaylen Warren's and
  // Quinshon Judkins' Touchdowns 1+ / 2+.
  test("24 ladders print 24 rows where they printed 142, and every rung is still on the page", () => {
    expect(summaries).toHaveLength(24);
    const hidden = summaries.reduce((n, s) => n + Number(s[3].replace(/\D/g, "")) + 1, 0);
    expect(hidden).toBe(142);
    for (const m of served) {
      if (/^.+: \d+(\.\d+)?\+$/.test(m.label) && m.pregame_mark != null) {
        // #9148 rewrites "PIT Steelers D/ST" before any rule reads a label.
        // AMENDED by slice 6: a lone rung beside ladders prints as its own
        // `subject · N+` row, so its label is the subject and the rung.
        const shown = propLabelDisplay(m.label);
        const lone = /^(.+): (\d+(?:\.\d+)?\+)$/.exec(shown)!;
        const asLoneRow = new RegExp(
          `data-testid="script-lone-rung"[^>]*><span[^>]*>${lone[1].replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}</span><span[^>]*>${lone[2].replace("+", "\\+")}<`,
        );
        expect(html.includes(`>${shown}<`) || asLoneRow.test(html)).toBe(true);
      }
    }
  });
});

describe("#1626 slice 4 CONTROLS", () => {
  test("the headline is the HIGHEST rung at 50% or above, not the one nearest 50%", () => {
    const [entry] = scriptLadders(rungs("A", [[150, 0.8], [200, 0.575], [225, 0.425]]));
    expect((entry as ScriptLadder).threshold).toBe("200");
  });

  test("a ladder favoured at no rung shows its lowest (likeliest) rung", () => {
    const [entry] = scriptLadders(rungs("A", [[10, 0.2], [15, 0.12], [20, 0.07]]));
    expect((entry as ScriptLadder).threshold).toBe("10");
  });

  test("the headline is chosen by threshold, whatever order the rungs arrive in", () => {
    const [entry] = scriptLadders(rungs("A", [[300, 0.1], [100, 0.9], [200, 0.6]]));
    expect((entry as ScriptLadder).threshold).toBe("200");
  });

  // AMENDED by slice 6: this was "two rungs stay two rows". Slice 6 reverses it
  // on purpose — see `PropsSection1626TwoRungLadder.test.tsx`. One rung is
  // still one row.
  test("one rung stays one row", () => {
    const html = render(rungs("A", [[150, 0.8]]));
    expect(ladderSummaries(html)).toHaveLength(0);
    expect(visibleRowLabels(html)).toEqual(["A: 150+"]);
  });

  test("an unmarked rung does not join the ladder — it folds as before (D102)", () => {
    const items = rungs("A", [[150, 0.8], [175, 0.6], [200, 0.4], [225, null]]);
    const out = scriptLadders(items.filter((i) => i.pregame_mark != null));
    expect(out).toHaveLength(1);
    const html = render(items);
    expect(ladderSummaries(html)).toEqual([["A", "175+", "60%", "+2 more"]]);
    expect(html).toContain(">More props (1)<");
  });

  test("a settled rung stays its own row and the rest still ladder if three remain", () => {
    const items = rungs("A", [[150, 0.8], [175, 0.6], [200, 0.4], [225, 0.2]]);
    items[0] = { ...items[0], settled: true };
    const out = scriptLadders(items);
    expect(out[0]).toBe(items[0]);
    expect((out[1] as ScriptLadder).rungs).toHaveLength(3);
  });

  test("two players in one family make two ladders, each where its first rung was", () => {
    const items = [...rungs("A", [[1, 0.7], [2, 0.4], [3, 0.1]]), ...rungs("B", [[1, 0.6], [2, 0.3], [3, 0.1]])];
    const out = scriptLadders(items) as ScriptLadder[];
    expect(out.map((l) => l.subject)).toEqual(["A", "B"]);
  });

  test("THE DIVERGENCE and WHAT HIT keep one row per rung", () => {
    const items = rungs("A", [[150, 0.8], [175, 0.6], [200, 0.4]]).map((i) => ({
      ...i,
      current: (i.pregame_mark ?? 0) + 0.1,
    }));
    expect(ladderSummaries(render(items, "divergence"))).toHaveLength(0);
    const graded = items.map((i) => ({ ...i, graded_result: "hit" as const }));
    expect(ladderSummaries(render(graded, "graded"))).toHaveLength(0);
  });
});
