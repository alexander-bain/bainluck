// #1626 slice 6 — two rungs are a ladder, and a lone rung beside ladders wears
// their shape.
//
// Browns @ Steelers (`/events/14780550`, scheduled, 390px, 2026-10-01 22:55Z):
// TOUCHDOWNS read `Jaylen Warren: 1+ 49%` over `Jaylen Warren: 2+ 12%`, and under
// RECEIVING YARDS `Blake Whiteheart: 15+` / `Blake Whiteheart: 25+` sat as two
// `Name: N+` rows in a list of `subject · N+ · percent · +N more` ladder rows.
// Slice 4 asked for three rungs before it laddered.
//
// The fixture is that page's served `props_script`, those two families only,
// banked from `GET /api/events/14780550/game-markets` at ~22:57Z 10/1.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection, { scriptLadders } from "../../components/event/PropsSection";
import type { PropMark, ScriptLadder } from "../../components/event/PropsSection";
import { propLabelDisplay } from "../../lib/playerPropsGrouping";
import specimen from "../fixtures/props_script_14780550_1626s6.json";

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

function ladderSummaries(html: string): Array<[string, string, string, string]> {
  return [
    ...html.matchAll(
      /<summary class="flex[^"]*"><span[^>]*>([^<]+)<\/span><span[^>]*>([^<]+)<\/span><span[^>]*>([^<]+)<\/span><span[^>]*>([^<]+)<\/span><\/summary>/g,
    ),
  ].map((m) => [m[1], m[2], m[3], m[4]]);
}

function loneRungs(html: string): Array<[string, string, string]> {
  return [
    ...html.matchAll(
      /data-testid="script-lone-rung"[^>]*><span[^>]*>([^<]+)<\/span><span[^>]*>([^<]+)<\/span><span[^>]*>([^<]+)</g,
    ),
  ].map((m) => [m[1], m[2], m[3]]);
}

/** Row labels printed outside every ladder disclosure. */
function visibleRowLabels(html: string): string[] {
  const outside = html.replace(/<details class="border-b[^"]*">[\s\S]*?<\/details>/g, "");
  return [...outside.matchAll(/line-clamp-2">([^<]+)<\/span>/g)].map((m) => m[1]);
}

const rungs = (subject: string, values: Array<[number, number | null]>, family = "M: Touchdowns"): PropMark[] =>
  values.map(([n, p]) => ({
    key: `${family}|${subject}: ${n}+`,
    label: `${subject}: ${n}+`,
    pregame_mark: p,
    current: p,
  }));

describe("#1626 slice 6 SHIP: on the served Browns @ Steelers page, every player row reads subject · rung · percent", () => {
  const html = render(served);
  const visible = visibleRowLabels(html);

  test("Jaylen Warren's touchdowns are one row: 1+, 49%, with 2+ behind it", () => {
    expect(ladderSummaries(html)).toContainEqual(["Jaylen Warren", "1+", "49%", "+1 more"]);
    expect(ladderSummaries(html)).toContainEqual(["Quinshon Judkins", "1+", "40%", "+1 more"]);
    expect(visible).not.toContain("Jaylen Warren: 2+");
  });

  test("Blake Whiteheart's two receiving rungs are one row like every other receiver's", () => {
    expect(ladderSummaries(html)).toContainEqual(["Blake Whiteheart", "15+", "19%", "+1 more"]);
    expect(visible).not.toContain("Blake Whiteheart: 15+");
    expect(visible).not.toContain("Blake Whiteheart: 25+");
  });

  test("the one-rung touchdown rows print in the same shape, with no disclosure", () => {
    expect(loneRungs(html)).toContainEqual(["DK Metcalf", "1+", "30%"]);
    // #9148's display rewrite still applies before the rule reads the label.
    expect(loneRungs(html)).toContainEqual(["Steelers D/ST", "1+", "15%"]);
    // 18 touchdown subjects; Warren and Judkins have two rungs and ladder.
    expect(loneRungs(html)).toHaveLength(16);
  });

  test("no `Name: N+` row is left in plain sight, and every rung is still on the page", () => {
    expect(visible.filter((l) => /: \d+\+$/.test(l))).toEqual([]);
    const lone = loneRungs(html).map(([subject, rung]) => `${subject}: ${rung}`);
    for (const m of served) {
      if (m.pregame_mark == null) continue;
      const shown = propLabelDisplay(m.label);
      expect(html.includes(`>${shown}<`) || lone.includes(shown)).toBe(true);
    }
  });
});

describe("#1626 slice 6 CONTROLS", () => {
  test("a two-rung ladder keeps slice 4's headline rule: highest rung at 50%+, else lowest", () => {
    const [up] = scriptLadders(rungs("A", [[1, 0.62], [2, 0.21]]));
    expect((up as ScriptLadder).threshold).toBe("1");
    const [both] = scriptLadders(rungs("A", [[1, 0.8], [2, 0.55]]));
    expect((both as ScriptLadder).threshold).toBe("2");
    const [none] = scriptLadders(rungs("A", [[2, 0.11], [1, 0.47]]));
    expect((none as ScriptLadder).threshold).toBe("1");
  });

  test("a family with no ladder is untouched: lone rungs keep their `Name: N+` rows", () => {
    const items = [...rungs("A", [[1, 0.3]]), ...rungs("B", [[1, 0.2]])];
    expect(scriptLadders(items)).toEqual(items);
    const html = render(items);
    expect(loneRungs(html)).toHaveLength(0);
    expect(visibleRowLabels(html)).toEqual(["A: 1+", "B: 1+"]);
  });

  test("an unmarked rung never joins or becomes a lone ladder row — it folds (D102)", () => {
    const items = [...rungs("A", [[1, 0.5], [2, 0.1]]), ...rungs("B", [[1, null]])];
    const html = render(items);
    expect(loneRungs(html)).toHaveLength(0);
    expect(html).toContain(">More props (1)<");
  });

  test("a settled rung beside a ladder stays its own row, not a lone ladder row", () => {
    const items = [...rungs("A", [[1, 0.5], [2, 0.1]]), ...rungs("B", [[1, 0.3]])];
    items[2] = { ...items[2], settled: true };
    const out = scriptLadders(items);
    expect(out[1]).toBe(items[2]);
  });

  test("THE DIVERGENCE and WHAT HIT still print one row per rung", () => {
    const items = rungs("A", [[1, 0.5], [2, 0.1]]).map((i) => ({ ...i, current: (i.pregame_mark ?? 0) + 0.1 }));
    expect(ladderSummaries(render(items, "divergence"))).toHaveLength(0);
    expect(loneRungs(render(items, "divergence"))).toHaveLength(0);
    const graded = items.map((i) => ({ ...i, graded_result: "hit" as const }));
    expect(ladderSummaries(render(graded, "graded"))).toHaveLength(0);
  });
});

// #1626 slice 7 — the percentages stand in one column. Production after slice 6
// (/events/14780550, 390px, 23:5xZ 10/1): in TOUCHDOWNS, "+1 more" after Warren's
// and Judkins' 48%/40% put those numbers ~55px left of DK Metcalf's lone 30%.
describe("#1626 slice 7: every ladder-shaped row ends in the same fixed-width slot", () => {
  const html = render(served);
  const slots = [...html.matchAll(/<span([^>]*)data-script-more-slot=""([^>]*)>([^<]*)<\/span>/g)].map(
    (m) => ({ attrs: `${m[1]} ${m[2]}`, text: m[3] }),
  );
  const cls = (attrs: string) => /class="([^"]*)"/.exec(attrs)?.[1] ?? "";

  test("one slot per ladder row and per lone rung, all the same fixed width", () => {
    expect(slots).toHaveLength(ladderSummaries(html).length + loneRungs(html).length);
    const classes = new Set(slots.map((s) => cls(s.attrs)));
    expect(classes.size).toBe(1);
    expect([...classes][0]).toMatch(/(^| )w-14( |$)/);
    expect([...classes][0]).toMatch(/(^| )shrink-0( |$)/);
  });

  test("a lone rung's slot is empty and hidden from screen readers; a ladder's says +N more", () => {
    const empty = slots.filter((s) => s.text === "");
    expect(empty).toHaveLength(loneRungs(html).length);
    for (const s of empty) expect(s.attrs).toContain('aria-hidden="true"');
    expect(slots.filter((s) => s.text !== "").map((s) => s.text)).toContain("+1 more");
  });

  test("the lone rung's slot comes AFTER its percent, exactly where a ladder's +N more sits", () => {
    expect(html).toMatch(
      /data-testid="script-lone-rung"[^>]*><span[^>]*>DK Metcalf<\/span><span[^>]*>1\+<\/span><span[^>]*>30%<\/span><span aria-hidden="true" data-script-more-slot=""/,
    );
  });
});
