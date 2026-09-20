/**
 * #7545, the render half — the chips a reader taps, and the one line that keeps
 * a lit chip from lying about the span it produced.
 *
 * `futuresHistoryRange7545.test.ts` proves the rung arithmetic. This proves the
 * consequence on the screen: which chip is lit, what the reader is told when the
 * backend widened past it, and that the control hands back a KEY.
 *
 * Jest runs `testEnvironment: 'node'` here, so there is no DOM to click. The
 * markup assertions go through `renderToStaticMarkup` like the rest of
 * `__tests__/components/`, and the tap is exercised by reaching into the
 * returned element tree and calling the handler the chips were actually given —
 * which tests the real wiring rather than a re-description of it.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import FuturesTrendRangeControls from "@/components/futures/FuturesTrendRangeControls";
import ChartRangeChips from "@/components/event/ChartRangeChips";
import type { ChartRange, ChartRangeKey } from "@/lib/chartWindow";

/**
 * Visible text only — the coverage line is prose, so tags would mask a match.
 *
 * `&amp;` is unescaped LAST, and that ordering is the whole correctness of this
 * helper: unescaping it first turns a literal `&amp;#8212;` into `&#8212;` and
 * then into an em dash, inventing a character the markup never contained. It is
 * the reverse order of escaping, and CodeQL's `js/double-escaping` caught this
 * file with the ampersand in the middle of the chain.
 */
function text(node: React.ReactElement): string {
  return renderToStaticMarkup(node)
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&#x2F;/g, "/")
    .replace(/&quot;/g, '"')
    .replace(/&#8212;/g, "—")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/** The props the component handed to ChartRangeChips, found in the element tree. */
function chipProps(node: React.ReactElement): {
  ranges: ChartRange[];
  selected: ChartRangeKey;
  onSelect: (k: ChartRangeKey) => void;
} {
  let found: any = null;
  const walk = (n: any) => {
    if (found || !n || typeof n !== "object") return;
    if (Array.isArray(n)) return n.forEach(walk);
    if (n.type === ChartRangeChips) {
      found = n.props;
      return;
    }
    if (n.props?.children) walk(n.props.children);
  };
  // Render one level: call the component to get its element tree.
  walk((FuturesTrendRangeControls as any)(node.props));
  if (!found) throw new Error("ChartRangeChips was not rendered");
  return found;
}

const base = {
  range: "1W" as const,
  onSelect: () => {},
  requestedHours: 168,
};

describe("#7545 the three rungs are on the page", () => {
  it("draws a button for each rung, labelled for a reader", () => {
    const html = renderToStaticMarkup(<FuturesTrendRangeControls {...base} />);
    for (const label of [">1W<", ">1M<", ">All<"]) {
      expect(html).toContain(label);
    }
  });

  it("lights only the rung the reader is on", () => {
    const html = renderToStaticMarkup(
      <FuturesTrendRangeControls {...base} range="1M" requestedHours={720} />
    );
    // one pressed chip, and it is the 1M one
    expect(html.match(/aria-pressed="true"/g) ?? []).toHaveLength(1);
    expect(html).toMatch(/aria-pressed="true"[^>]*>1M</);
  });

  it("marks the group for a screen reader", () => {
    const html = renderToStaticMarkup(<FuturesTrendRangeControls {...base} />);
    expect(html).toContain('role="group"');
    expect(html).toContain('aria-label="Chart time range"');
  });
});

describe("#7545 the control hands back a key, not a label", () => {
  it("passes the tapped rung's key straight through", () => {
    const seen: string[] = [];
    const node = (
      <FuturesTrendRangeControls {...base} onSelect={(k) => seen.push(k)} />
    );
    const { ranges, onSelect } = chipProps(node);
    for (const r of ranges) onSelect(r.key);
    expect(seen).toEqual(["1W", "1M", "all"]);
  });

  it("tells the chips which rung is selected", () => {
    const node = (
      <FuturesTrendRangeControls {...base} range="all" requestedHours={8760} />
    );
    expect(chipProps(node).selected).toBe("all");
  });
});

describe("#7545 the coverage line", () => {
  it("says nothing when the API served the window that was asked for", () => {
    const html = renderToStaticMarkup(
      <FuturesTrendRangeControls {...base} actualHours={168} />
    );
    expect(html).not.toContain("<p");
  });

  // /futures/171, read at hours=168, answered actual_hours=720.
  it("states the real span when the backend widened past the lit chip", () => {
    const node = <FuturesTrendRangeControls {...base} actualHours={720} />;
    const html = renderToStaticMarkup(node);
    // the chip still reads 1W and is still the reader's choice...
    expect(html).toMatch(/aria-pressed="true"[^>]*>1W</);
    // ...and the page does not let that stand as the whole truth.
    expect(text(node)).toContain("Too few prices in 7 days — showing 30 days.");
  });

  it("joins the coverage line and the cadence note into one line", () => {
    const node = (
      <FuturesTrendRangeControls
        {...base}
        actualHours={720}
        cadenceNote="Prices update hourly"
      />
    );
    expect(text(node)).toContain(
      "Too few prices in 7 days — showing 30 days. · Prices update hourly"
    );
  });

  it("shows a cadence note on its own when there is no widening to report", () => {
    const node = (
      <FuturesTrendRangeControls
        {...base}
        range="all"
        requestedHours={8760}
        actualHours={8760}
        cadenceNote="Prices update hourly"
      />
    );
    const t = text(node);
    expect(t).toContain("Prices update hourly");
    expect(t).not.toContain("Too few prices");
  });

  it("never prints machine vocabulary at the reader", () => {
    const t = text(
      <FuturesTrendRangeControls
        {...base}
        range="all"
        requestedHours={8760}
        actualHours={9000}
        cadenceNote="Prices update hourly"
      />
    );
    expect(t).not.toMatch(/actual_hours|since_start|_hours|hours=/);
  });
});
