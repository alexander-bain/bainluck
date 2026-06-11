import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import MoversRibbon from "../../components/MoversRibbon";
import type { ChampionshipGridMover } from "../../lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

function makeMover(overrides: Partial<ChampionshipGridMover> = {}): ChampionshipGridMover {
  return {
    name: "Boston Celtics",
    short_name: "Celtics",
    team_id: 1,
    column: "win",
    change_24h: 0.015, // 1.5 percentage points
    direction: "up",
    logo_url: null,
    primary_color: null,
    ...overrides,
  };
}

describe("MoversRibbon", () => {
  it("filters out near-zero movers below the 0.5pp floor", () => {
    const html = renderToStaticMarkup(
      React.createElement(MoversRibbon, {
        // 0.2pp mover: 0.002 fraction < 0.005 floor → must be hidden
        movers: [makeMover({ name: "Tiny Mover", short_name: "Tiny", change_24h: 0.002 })],
      })
    );

    // Nothing renders when all movers are below the floor
    expect(html).toBe("");
  });

  it("shows a 1.5pp mover with its full team name", () => {
    const html = renderToStaticMarkup(
      React.createElement(MoversRibbon, {
        movers: [makeMover({ name: "Boston Celtics", short_name: "Celtics", change_24h: 0.015 })],
      })
    );

    // Full name, not the short name
    expect(html).toContain("Boston Celtics");
    expect(html).not.toContain(">Celtics<");
    // 1.5pp magnitude is displayed and never "0.0"
    expect(html).toContain("1.5");
    expect(html).not.toContain(">0.0<");
  });

  it("keeps real movers and drops sub-floor ones in a mixed list", () => {
    const html = renderToStaticMarkup(
      React.createElement(MoversRibbon, {
        movers: [
          makeMover({ name: "Real Mover", short_name: "Real", change_24h: -0.02 }),
          makeMover({ name: "Noise Mover", short_name: "Noise", change_24h: 0.001 }),
        ],
      })
    );

    expect(html).toContain("Real Mover");
    expect(html).not.toContain("Noise Mover");
  });
});
