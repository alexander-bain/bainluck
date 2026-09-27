/**
 * #9148, second surface — THE SCRIPT's prop list named a defense
 * "SEA Seahawks D/ST" after the rail above it had stopped.
 *
 * Production LOOK of `/events/14781702` (Seahawks @ Commanders) at 390px on
 * 2026-09-27 14:05Z, after PR #9150 went live: the script rail read
 * "Seahawks D/ST's 10+ fantasy points…", and further down the same page
 *
 *   > THE SCRIPT  Props
 *   > FANTASY POINTS
 *   > SEA Seahawks D/ST: Over 9.2        46%
 *   > WAS Commanders D/ST: Over 5.7      36%
 *   > TOUCHDOWNS
 *   > SEA Seahawks D/ST: 1+              16%
 *
 * `PropsSection` prints the served `props_script[].label`, which is Kalshi's
 * outcome name verbatim; PR #9150 fixed `parsePlayerName`, which this list
 * never calls. The keys and labels below are the served rows from
 * `/api/events/14781702/game-markets` at that minute.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";
import { propLabelDisplay } from "../../lib/playerPropsGrouping";

const SERVED: PropMark[] = [
  {
    key: "Seattle vs Washington: Fantasy Points|SEA Seahawks D/ST: Over 9.2",
    label: "SEA Seahawks D/ST: Over 9.2",
    pregame_mark: 0.46,
    current: 0.46,
  },
  {
    key: "Seattle vs Washington: Fantasy Points|Jason Myers: Over 8",
    label: "Jason Myers: Over 8",
    pregame_mark: 0.54,
    current: 0.54,
  },
  {
    key: "Seattle vs Washington: Fantasy Points|WAS Commanders D/ST: Over 5.7",
    label: "WAS Commanders D/ST: Over 5.7",
    pregame_mark: 0.36,
    current: 0.36,
  },
  {
    key: "Seattle vs Washington: Touchdowns|SEA Seahawks D/ST: 1+",
    label: "SEA Seahawks D/ST: 1+",
    pregame_mark: 0.16,
    current: 0.16,
  },
];

function render(items: PropMark[]): string {
  return renderToStaticMarkup(
    <PropsSection
      items={items}
      eventStatus="scheduled"
      matchup={{ home: "Washington Commanders", away: "Seattle Seahawks" }}
    />,
  );
}

describe("#9148 THE SCRIPT prop list names a defense by its nickname", () => {
  const html = render(SERVED);

  it("drops the ticker from every served D/ST row", () => {
    expect(html).toContain("Seahawks D/ST: Over 9.2");
    expect(html).toContain("Commanders D/ST: Over 5.7");
    expect(html).toContain("Seahawks D/ST: 1+");
    expect(html).not.toContain("SEA Seahawks");
    expect(html).not.toContain("WAS Commanders");
  });

  it("leaves a player row exactly as served", () => {
    expect(html).toContain("Jason Myers: Over 8");
  });

  it("keeps every row: the rename moves no row into or out of the list", () => {
    // Strawman: the same rows with the ticker already gone render the same
    // markup, so the only thing the helper changes is the words.
    const preRenamed = SERVED.map((i) => ({ ...i, label: propLabelDisplay(i.label) }));
    expect(render(preRenamed)).toBe(html);
  });
});

describe("propLabelDisplay", () => {
  it.each([
    ["SEA Seahawks D/ST: Over 9.2", "Seahawks D/ST: Over 9.2"],
    ["NY Jets D/ST: 1+", "Jets D/ST: 1+"],
    ["Jason Myers: Over 8", "Jason Myers: Over 8"],
    ["Seattle: 4+", "Seattle: 4+"],
    ["Under 63.5", "Under 63.5"],
    ["SEA Seahawks D/ST", "SEA Seahawks D/ST"],
  ])("%s → %s", (served, shown) => {
    expect(propLabelDisplay(served)).toBe(shown);
  });
});
