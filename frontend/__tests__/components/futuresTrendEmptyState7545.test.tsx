/**
 * #7545 — the empty state, which is where a range control is most able to lie.
 *
 * Before the chips there was one emptiness and one sentence: "Not enough price
 * history yet". With a reader-chosen window that sentence is false for the case
 * that matters — /futures/112921 holds 4,527 price points, and a week-long
 * window that happens to miss them would have said the market had none.
 *
 * Two behaviours are pinned here, and the second is the one that would rot
 * silently: the copy must name the window, and the CHIPS MUST SURVIVE the empty
 * result. A control that vanishes exactly when it is needed strands the reader
 * on a rung their own tap put them on.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import FuturesTrendEmptyState from "@/components/futures/FuturesTrendEmptyState";

// `&amp;` unescapes LAST — the reverse order of escaping. Putting it earlier
// double-unescapes (`&amp;#x27;` -> `&#x27;` -> `'`), which is the
// `js/double-escaping` alert this file's sibling was caught by.
function text(node: React.ReactElement): string {
  return renderToStaticMarkup(node)
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

const base = {
  onSelect: () => {},
  createdAt: "2026-02-19T01:41:04.420888+00:00",
};

describe("#7545 an empty NARROW window does not claim the market is empty", () => {
  it.each([
    ["1W" as const, 168, "the last 7 days"],
    ["1M" as const, 720, "the last 30 days"],
  ])("names the window on %s", (range, requestedHours, words) => {
    const t = text(
      <FuturesTrendEmptyState {...base} range={range} requestedHours={requestedHours} />
    );
    expect(t).toContain(`No prices in ${words}`);
    expect(t).not.toContain("Not enough price history yet");
  });

  it("KEEPS THE CHIPS so the reader can widen out of the empty rung", () => {
    const html = renderToStaticMarkup(
      <FuturesTrendEmptyState {...base} range="1W" requestedHours={168} />
    );
    expect(html).toContain('role="group"');
    for (const label of [">1W<", ">1M<", ">All<"]) {
      expect(html).toContain(label);
    }
  });

  it("points at the way out", () => {
    const t = text(
      <FuturesTrendEmptyState {...base} range="1W" requestedHours={168} />
    );
    expect(t).toContain("Try a longer range.");
  });
});

describe("#7545 an empty WIDEST window is the market being empty", () => {
  it("keeps the original sentence on 'all'", () => {
    const t = text(
      <FuturesTrendEmptyState {...base} range="all" requestedHours={8760} />
    );
    expect(t).toContain("Not enough price history yet");
    expect(t).toContain("The trend line appears once this market has a few price points.");
    expect(t).not.toContain("No prices in");
  });

  it("offers no rung to try, because there is no wider one", () => {
    const html = renderToStaticMarkup(
      <FuturesTrendEmptyState {...base} range="all" requestedHours={8760} />
    );
    expect(html).not.toContain('role="group"');
    expect(text(<FuturesTrendEmptyState {...base} range="all" requestedHours={8760} />))
      .not.toContain("Try a longer range.");
  });
});

describe("#7545 the empty card is still the Probability Trend card", () => {
  it.each([["1W" as const, 168], ["all" as const, 8760]])(
    "keeps its heading on %s",
    (range, requestedHours) => {
      expect(
        text(<FuturesTrendEmptyState {...base} range={range} requestedHours={requestedHours} />)
      ).toContain("Probability Trend");
    }
  );
});
