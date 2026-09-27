// #9131 — before kickoff, THE SCRIPT prints what the market expects NOW.
//
// Specimen: `/events/14781701`, Chiefs @ Dolphins, status `scheduled`, 5h before
// kickoff, 390px, 2026-09-27. `props_script` rows below are the served values.
// Before kickoff `pregame_mark` is `_resolve_pregame_mark`'s fallback — each
// outcome's OPENING price — because the commence-time pin is written only inside
// 15 minutes of the start. THE SCRIPT printed it, so the page said:
//   - "Miami: 4+ 26%" under a rail reading "opened at 26% — it's 6% now";
//   - "Patrick Mahomes: 300+ 16%" rows above "O/U 299.5 · Over 10%" — one question,
//     two numbers, while both venues priced it 9.5% at that moment.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";

const SPECIMEN: PropMark[] = [
  {
    key: "Kansas City vs Miami: Team Field Goals|Miami: 4+",
    label: "Miami: 4+",
    pregame_mark: 0.255,
    current: 0.055,
  },
  {
    key: "Kansas City vs Miami: Passing Yards|Patrick Mahomes: 300+",
    label: "Patrick Mahomes: 300+",
    pregame_mark: 0.16,
    current: 0.095,
  },
  {
    key: "Patrick Mahomes: Passing Yards O/U 299.5|Under",
    label: "Under",
    pregame_mark: 0.9,
    current: 0.905,
  },
  {
    key: "Patrick Mahomes: Passing Yards O/U 299.5|Over",
    label: "Over",
    pregame_mark: 0.1,
    current: 0.095,
  },
];

const render = (items: PropMark[], state: "script" | "divergence" | "graded") =>
  renderToStaticMarkup(<PropsSection items={items} state={state} />);

/** The printed value beside the row labelled exactly `label`. */
function valueOf(html: string, label: string): string | null {
  const esc = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = html.match(
    new RegExp(`>${esc}</span><span class="font-mono[^"]*">([^<]+)</span>`),
  );
  return m ? m[1] : null;
}

describe("#9131 THE SCRIPT prints the live price before kickoff", () => {
  test("THE SHIP: Miami 4+ reads 6%, the price the rail calls 'now' — not the 26% opening", () => {
    const html = render(SPECIMEN, "script");
    expect(valueOf(html, "Miami: 4+")).toBe("6%");
    expect(html).not.toContain("26%");
  });

  test("THE SHIP: Mahomes 300+ and O/U 299.5 · Over stop disagreeing by six points", () => {
    const html = render(SPECIMEN, "script");
    const ladder = parseInt(valueOf(html, "Patrick Mahomes: 300+") ?? "", 10);
    const over = parseInt(valueOf(html, "Over") ?? "", 10);
    // Both read 0.095. The O/U leg is half of a pair and takes #5240's pair
    // rounding (0.905 → 91, so Over prints 9), the lone ladder rung rounds on its
    // own (10). One point of rounding remains; the 16-vs-10 gap was the opening.
    expect(ladder).toBe(10);
    expect(Math.abs(ladder - over)).toBeLessThanOrEqual(1);
    expect(html).not.toContain("16%");
  });

  test("CONTROL: a marked row with no live price still prints its mark", () => {
    const html = render(
      [{ key: "Team Field Goals|Miami: 1+", label: "Miami: 1+", pregame_mark: 0.765, current: null }],
      "script",
    );
    expect(valueOf(html, "Miami: 1+")).toBe("77%");
  });

  test("CONTROL: a row with no mark keeps the em dash and the fold", () => {
    const html = render(
      [
        { key: "Team Field Goals|Miami: 4+", label: "Miami: 4+", pregame_mark: 0.255, current: 0.055 },
        { key: "Team Field Goals|Kansas City: 4+", label: "Kansas City: 4+", pregame_mark: null, current: 0.09 },
      ],
      "script",
    );
    expect(html).toContain("More props (1)");
    expect(valueOf(html, "Kansas City: 4+")).toBe("—");
    expect(html).not.toContain("9%");
  });

  test("CONTROL: THE DIVERGENCE still measures from the pregame mark", () => {
    // Once the game is on, the opening → now arc is the story; this change must
    // not flatten it.
    const html = render([SPECIMEN[0]], "divergence");
    expect(html).toContain("26%");
    expect(html).toContain("6%");
  });
});
