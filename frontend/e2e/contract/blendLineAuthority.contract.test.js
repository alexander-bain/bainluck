"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * #1003 — the chart's blend line is the BACKEND blend, or it is nothing.
 *
 * ## The defect
 *
 * `OddsChart` drew a line called "Bain Luck (aggregated)" from the backend
 * `aggregate_line` — the weighted median the hero and the Discover card also
 * render — and, when that array was empty, silently fell back to an
 * **unweighted mean** of whatever per-source series happened to be loaded. It
 * kept the same name, the same colour, the same legend entry and the same
 * tooltip row.
 *
 * An unweighted mean is not the blend. Production weights are betting 3.0,
 * ESPN 1.5, stat_model 1.0, Kalshi/Polymarket/MLB 0.8. So the fallback could
 * print a number the hero and the card never show — and it fed four readers at
 * once: the tooltip row, the current-probability callout, the lead-change
 * count, and (via `onActivePointChange`) the web live hero itself. That is
 * standing ruling #1 — card == hero == chart, one number per question — broken
 * by the surface that exists to visualise it. It is the 57-vs-20 bug with
 * better manners.
 *
 * The two gates disagreed by construction, which is why the path existed at
 * all: the backend emits `aggregate_line` only when `len(agg_sources) > 1`
 * (bookmaker consensus counts as one of those), while the chart drew the
 * aggregated line whenever `nonBettingSources.length > 0` (bookmakers do not
 * count). One source with no bookmaker history satisfies the second and not
 * the first.
 *
 * ## Why this file and not jest
 *
 * The jest suite is a CI gate now, and a rendering test there would be the
 * richer check. But this invariant is about a line of code that must NOT come
 * back, and the cheapest way to reintroduce it is to "restore the fallback so
 * the chart isn't empty" — a change that looks like a fix. A dependency-free
 * assertion in the suite `deploy` already depends on makes that reintroduction
 * fail loudly and immediately, with the reason attached.
 *
 * It reads source text on purpose. That is a blunt instrument, so every
 * assertion below names what to do if the code legitimately moves: update the
 * fixture, do not delete the check.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const CHART = path.join(REPO_ROOT, "frontend", "components", "OddsChart.tsx");

function read(file) {
  try {
    return fs.readFileSync(file, "utf8");
  } catch (err) {
    assert.fail(
      `#1003 blend-line fixture could not read ${path.relative(REPO_ROOT, file)}: ` +
        `${err.message}. If the component moved, update this fixture — do not delete the check.`
    );
  }
}

describe("#1003: the chart's blend line is the backend blend or nothing", () => {
  const src = read(CHART);

  it("gates the blend line on the backend aggregate line, not just on having sources", () => {
    // #8066 added a THIRD conjunct, and the fixture is updated rather than
    // relaxed: the gate is now strictly narrower than #1003 left it.
    //
    // Why a third was needed. #1003 read "a non-empty `aggregate_line` means
    // the backend blended this event" — true when it was written, and false
    // from the moment #920 shipped, because the page now merges the live
    // stream's published `p` into that same array and the stream publishes for
    // single-source events the backend serves no blend for. Two pushed frames
    // put a 2-point series on the plot under the blend's name and, through
    // `primarySeriesKey`, demoted the real 319-point source line to 1px at
    // 0.28 opacity. `backendBlendServed` is the page's answer, read from the
    // SERVED response before that merge.
    //
    // If this shape moves again: the rule is that the blend line requires a
    // multi-source chart, points to draw, AND those points being the
    // BACKEND's. Update the fixture, do not delete the check.
    assert.match(
      src,
      /const showBlendLine\s*=\s*isMultiSource\s*&&\s*backendBlendServed\s*&&\s*filteredAggregateLine\.length\s*>\s*0/,
      "The `showBlendLine` gate is gone or changed shape. The blend line must " +
        "require a multi-source chart, a non-empty aggregate line, AND that " +
        "line being the backend's blend (`backendBlendServed`). Gating on " +
        "`isMultiSource` alone is the #1003 defect; dropping " +
        "`backendBlendServed` is the #8066 defect."
    );
  });

  it("does not let the page answer `backendBlendServed` from its own merged array", () => {
    // #8066's whole point: the gate must be computed from what the BACKEND
    // served, not from `historyData`, which already contains the live frames
    // the gate exists to disregard. Reading the merged array makes the gate
    // answer "yes" for exactly the pages it protects.
    const page = read(path.join(REPO_ROOT, "frontend", "app", "events", "[id]", "page.tsx"));
    assert.match(
      page,
      /const backendBlendServed\s*=\s*\(servedHistory\?\.aggregate_line\?\.length\s*\?\?\s*0\)\s*>\s*0;/,
      "`backendBlendServed` is not derived from `servedHistory`. If it reads " +
        "`historyData` it is reading #920's merge and the #8066 gate is inert."
    );
    assert.doesNotMatch(
      page,
      /const backendBlendServed\s*=\s*\(historyData/,
      "`backendBlendServed` is being computed from the merged history."
    );
  });

  it("writes bainLuckDelta only under that gate", () => {
    const writes = src.match(/\.bainLuckDelta\s*=/g) || [];
    assert.equal(
      writes.length,
      1,
      `Expected exactly one place that assigns bainLuckDelta, found ${writes.length}. ` +
        "A second writer is how the frontend-computed fallback comes back."
    );

    // The single writer must sit inside the `if (showBlendLine)` block.
    const gate = src.indexOf("if (showBlendLine)");
    assert.notEqual(gate, -1, "The `if (showBlendLine)` guard around the blend-line write is gone.");
    const write = src.indexOf(".bainLuckDelta =");
    assert.ok(
      write > gate && write - gate < 400,
      "The bainLuckDelta assignment is no longer inside the `if (showBlendLine)` block."
    );
  });

  it("never averages source series into the blend line", () => {
    assert.doesNotMatch(
      src,
      /bainLuckDelta\s*=[\s\S]{0,200}?reduce\(/,
      "A reduce() is feeding bainLuckDelta again — this is the unweighted-mean " +
        "fallback #1003 removed. If the chart needs a line when the backend has " +
        "no blend, draw a real source and label it as that source; do not " +
        "compute an average and call it the blend."
    );
    assert.doesNotMatch(
      src,
      /Fallback: average of all available source deltas/,
      "The removed fallback's comment is back, so the code probably is too."
    );
  });

  it("keeps one definition of the primary series for all four of its readers", () => {
    // The fill gradient, the callout, the lead-change count and the hover
    // payload sent to the live hero must agree on which line the chart is
    // about. They were three separate ternaries before #1003, and one of them
    // (the hover payload) defaulted to 50% when its key was all-null.
    assert.match(
      src,
      /const primarySeriesKey: string = showBlendLine/,
      "`primarySeriesKey` is gone. Without a single definition the callout, the " +
        "fill and the live-hero hover payload can disagree about the chart's number."
    );
    assert.doesNotMatch(
      src,
      /isMultiSource \? "bainLuckDelta" : "homeDelta"/,
      "A reader is selecting the blend series off `isMultiSource` again. That is " +
        "the gate that does not know whether a backend blend exists — use " +
        "`primarySeriesKey`."
    );
  });

  it("does not label a line it did not draw", () => {
    // The legend swatch names the blend in the blend's colour. If it renders
    // when the line does not, the chart makes the same false claim with no
    // line under it.
    const legend = src.indexOf("Multi-source mode: Bain Luck aggregated line first");
    assert.notEqual(legend, -1, "The blend legend entry moved; update this fixture.");
    const after = src.slice(legend, legend + 500);
    assert.match(
      after,
      /\{showBlendLine && \(/,
      "The blend's legend entry is gated on something other than `showBlendLine`."
    );
  });
});
