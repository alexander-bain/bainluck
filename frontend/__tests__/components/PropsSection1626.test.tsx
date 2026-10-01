// #1626 — THE DIVERGENCE prints one row per two-sided question.
//
// Alex, NYY–BOS Wild Card (2026-09-29): "interesting idea, but currently
// unreadable", "needs to be way more compact". On CWS @ HOU (2026-09-30, live,
// 390px) every O/U family printed both legs — `SEAN BURKE: STRIKEOUTS O/U 10.5`
// as `Under 90% → 92% ↑ 2` over `Over 10% → 8% ↓ 2` — the second row the first
// one upside down.
//
// The fixture is that page's served `props_script`, banked from
// `GET /api/events/15321836/game-markets` at 22:25Z.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";
import specimen from "../fixtures/props_script_15321836_1626.json";

const MATCHUP = { home: "Houston Astros", away: "Chicago White Sox" };
const HEADER = 'font-semibold uppercase tracking-wide text-text-secondary mb-1">';

const served: PropMark[] = specimen.props_script.map((p, i) => ({
  key: p.key ?? i,
  label: p.label,
  pregame_mark: p.pregame_mark ?? null,
  current: p.current ?? null,
  settled: p.settled ?? null,
}));

const render = (items: PropMark[], state: "script" | "divergence" | "graded" = "divergence") =>
  renderToStaticMarkup(<PropsSection items={items} state={state} matchup={MATCHUP} />);
const count = (html: string, needle: string) => html.split(needle).length - 1;

/** The rows printed under one family header, as "label | level". */
function familyRows(html: string, family: string): string[] {
  const at = html.indexOf(`${HEADER}${family}<`);
  if (at === -1) return [];
  const next = html.indexOf(HEADER, at + HEADER.length);
  const chunk = html.slice(at, next === -1 ? undefined : next);
  return [...chunk.matchAll(/line-clamp-2">([^<]+)<\/span>/g)].map((m) => m[1]);
}

describe("#1626 SHIP: on the served CWS @ HOU page, a two-sided question is one row", () => {
  const html = render(served);

  test("SEAN BURKE: STRIKEOUTS O/U 10.5 prints Under only — the pregame favourite", () => {
    expect(familyRows(html, "Sean Burke: Strikeouts O/U 10.5")).toEqual(["Under"]);
  });

  test("the section is materially shorter: about half the rows it printed", () => {
    const priced = served.filter((m) => m.pregame_mark != null && m.current != null).length;
    const rows = count(html, "→");
    expect(rows).toBeLessThan(priced * 0.6);
    expect(rows).toBeGreaterThan(0);
  });

  test("CONTROL: every question keeps a row — no family header is lost", () => {
    const families = new Set(served.map((m) => String(m.key).split("|")[0]));
    const headers = count(html, HEADER);
    expect(headers).toBeGreaterThanOrEqual(families.size - 1);
  });
});

describe("#1626 CONTROLS", () => {
  const pair = (fam: string, over: [number, number], under: [number, number]): PropMark[] => [
    { key: `P: ${fam}|Over`, label: "Over", pregame_mark: over[0], current: over[1] },
    { key: `P: ${fam}|Under`, label: "Under", pregame_mark: under[0], current: under[1] },
  ];

  test("a non-complement pair keeps both legs (0.555/0.54 vs 0.445/0.445 — Hunter Brown 6.5)", () => {
    const html = render(pair("Strikeouts O/U 6.5", [0.445, 0.445], [0.555, 0.54]));
    expect(familyRows(html, "P: Strikeouts O/U 6.5")).toHaveLength(2);
  });

  test("a complement pair keeps the pregame favourite, whichever side it is", () => {
    const html = render(pair("Hits O/U 0.5", [0.6, 0.72], [0.4, 0.28]));
    expect(html).toContain("↑ 12");
    expect(html).not.toContain("↓ 12");
    expect(html).toContain(">Over<");
  });

  test("a leg with a pending_label leaves its family whole", () => {
    const legs = pair("Hits O/U 0.5", [0.6, 0.72], [0.4, 0.28]);
    legs[1] = { ...legs[1], pending_label: "Void" } as PropMark;
    expect(render(legs)).toContain(">Under<");
  });

  test("a three-way family is untouched", () => {
    const three: PropMark[] = [
      { key: "M: Result|Home", label: "Home", pregame_mark: 0.45, current: 0.5 },
      { key: "M: Result|Draw", label: "Draw", pregame_mark: 0.27, current: 0.25 },
      { key: "M: Result|Away", label: "Away", pregame_mark: 0.28, current: 0.25 },
    ];
    expect(familyRows(render(three), "M: Result")).toHaveLength(3);
  });

  test("THE SCRIPT prints one side too since slice 3 — the favourite by its printed number", () => {
    // Moved by #1626 slice 3 (PropsSection1626Script). THE SCRIPT prints
    // `current` (#9131), 0.72 / 0.28, so it keeps Over.
    const html = render(pair("Hits O/U 0.5", [0.6, 0.72], [0.4, 0.28]), "script");
    expect(html).toContain(">Over<");
    expect(html).not.toContain(">Under<");
  });
});
