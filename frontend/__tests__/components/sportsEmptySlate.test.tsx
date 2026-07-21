// #217 — the no-games UX. Guards that the empty-slate panel is honest AND
// helpful (points at what IS on) in both modes, rather than an empty shell.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import SportsEmptySlate from "../../components/SportsEmptySlate";

describe("SportsEmptySlate (#217)", () => {
  test("no-games mode names the situation and points to markets below + Discover", () => {
    const html = renderToStaticMarkup(
      <SportsEmptySlate mode="no-games" hasMarketsBelow onRefresh={() => {}} />,
    );
    expect(html).toContain("No live or upcoming games right now");
    // Points at what IS on.
    expect(html).toContain("See what");
    expect(html).toContain("/discover");
    expect(html).toContain("Top markets are below");
    // Category exploration links present.
    expect(html).toContain("/politics");
    expect(html).toContain("Refresh");
  });

  test("no-games mode without markets omits the 'markets below' pointer", () => {
    const html = renderToStaticMarkup(
      <SportsEmptySlate mode="no-games" hasMarketsBelow={false} onRefresh={() => {}} />,
    );
    expect(html).toContain("No live or upcoming games right now");
    expect(html).not.toContain("Top markets are below");
  });

  test("empty mode is honest about the whole-feed lull", () => {
    const html = renderToStaticMarkup(
      <SportsEmptySlate mode="empty" hasMarketsBelow={false} onRefresh={() => {}} />,
    );
    expect(html).toContain("The slate is quiet right now");
    expect(html).toContain("/discover");
    expect(html).toContain("Refresh");
  });
});
