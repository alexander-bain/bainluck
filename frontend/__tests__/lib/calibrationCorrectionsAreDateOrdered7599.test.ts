/**
 * #7599 — the dated corrections log renders in date order.
 *
 * THE FIXTURE IS THE SPECIMEN. `LIVE_ORDER` below is the thirteen entries of
 * `https://api.bainluck.com/api/calibration` (q271, `generated_at`
 * 2026-09-15T11:16:10Z) in the order the payload publishes them — read
 * 2026-09-20 21:00Z, not sketched. That is what makes this a guard rather than
 * a restatement: the page rendered this array verbatim, so the fixture CONTAINS
 * the defect and every assertion below failed before the fix.
 *
 * The shape of the bug is why the controls matter. The list is almost sorted —
 * twelve of thirteen are oldest-first and only `2026-07-08` is out of place —
 * so an "is it sorted?" assertion over a fixture somebody later tidied would
 * pass without the sort ever running. `the fixture is out of order to begin
 * with` is that positive control: it asserts the INPUT violates the property
 * the output must have. Delete `orderCorrections` from the call site and the
 * suite goes red; tidy the fixture and it goes red too.
 */

import * as fs from "fs";
import * as path from "path";

import { orderCorrections } from "@/lib/calibrationCorrections";
import type { CalibrationCorrection } from "@/lib/api";

const c = (date: string, title: string, rows: number | null = null): CalibrationCorrection => ({
  date,
  title,
  rows,
  // The page never renders this field (#4067 / CERT-2295 — the backend's
  // paragraph is not this page's copy), so it carries a marker rather than
  // prose: nothing here should ever reach a screen.
  description: "unrendered",
});

/** The live payload's thirteen, in the live payload's own order. */
const LIVE_ORDER: CalibrationCorrection[] = [
  c("2026-07-09", "Polymarket hockey sign-flip", 36_207),
  c("2026-07-08", "Premature golf resolutions", 230),
  c("2026-07-09", "DataGolf survivorship exclusion"),
  c("2026-07-09", "Polymarket no-bid placeholder exclusion"),
  c("2026-07-09", "Malformed-binary exclusion"),
  c("2026-07-09", "Golf FIELD one-sided-ask placeholder exclusion"),
  c("2026-07-10", "Multi-candidate probability normalization"),
  c("2026-07-11", "Soccer 2-way (draw-omission) historical exclusion"),
  c("2026-07-12", "Esports match-bundle exclusion"),
  c("2026-07-13", "Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)"),
  c("2026-09-12", "Prices nobody could have traded at"),
  c("2026-09-12", "A price ladder is one forecast, not forty"),
  c("2026-09-13", "The one-question markets we were throwing away are now scored"),
];

const dates = (rows: CalibrationCorrection[]) => rows.map(r => r.date);
const titles = (rows: CalibrationCorrection[]) => rows.map(r => r.title);

describe("#7599 the corrections log is ordered by its own dates", () => {
  it("the fixture is out of order to begin with — the control that makes the rest non-vacuous", () => {
    const published = dates(LIVE_ORDER);
    const sorted = [...published].sort();
    expect(published).not.toEqual(sorted);
    // And it is out of order in exactly one place, which is the claim the
    // issue's acceptance rests on: one row moves, twelve do not.
    const descents = published.filter((d, i) => i > 0 && d < published[i - 1]);
    expect(descents).toEqual(["2026-07-08"]);
  });

  it("renders the dates non-decreasing top to bottom", () => {
    const out = dates(orderCorrections(LIVE_ORDER));
    for (let i = 1; i < out.length; i++) {
      expect(out[i] >= out[i - 1]).toBe(true);
    }
  });

  it("puts the 2026-07-08 golf entry first and leaves every other row's neighbours alone", () => {
    const out = orderCorrections(LIVE_ORDER);
    expect(out[0].title).toBe("Premature golf resolutions");
    expect(out[0].date).toBe("2026-07-08");
    // The whole point of keeping the direction oldest-first: exactly one row
    // moves. The remaining twelve are the payload's sequence with that row
    // lifted out — asserted as a list, so a second row silently changing place
    // cannot hide behind a spot check.
    expect(titles(out.slice(1))).toEqual(
      titles(LIVE_ORDER.filter(r => r.title !== "Premature golf resolutions")),
    );
  });

  it("is stable in ties, so the five 2026-07-09 rows keep the order the payload published", () => {
    const out = orderCorrections(LIVE_ORDER);
    expect(titles(out.filter(r => r.date === "2026-07-09"))).toEqual([
      "Polymarket hockey sign-flip",
      "DataGolf survivorship exclusion",
      "Polymarket no-bid placeholder exclusion",
      "Malformed-binary exclusion",
      "Golf FIELD one-sided-ask placeholder exclusion",
    ]);
    expect(titles(out.filter(r => r.date === "2026-09-12"))).toEqual([
      "Prices nobody could have traded at",
      "A price ladder is one forecast, not forty",
    ]);
  });

  it("sorts a payload that arrives in any order, not just this one", () => {
    // Reversed is the case a stable sort can get wrong in a way the live order
    // cannot show: every tie group is inverted, so a comparator that leans on
    // the input's position rather than the date fails here and passes above.
    const reversed = [...LIVE_ORDER].reverse();
    const out = dates(orderCorrections(reversed));
    for (let i = 1; i < out.length; i++) {
      expect(out[i] >= out[i - 1]).toBe(true);
    }
    expect(out[0]).toBe("2026-07-08");
    expect(out[out.length - 1]).toBe("2026-09-13");
  });

  it("does not reorder the caller's array — the payload object is SWR's cache, not ours", () => {
    const input = [...LIVE_ORDER];
    const snapshot = titles(input);
    orderCorrections(input);
    expect(titles(input)).toEqual(snapshot);
  });

  it("keeps every entry, and keeps the two row counts on the entries that have them", () => {
    const out = orderCorrections(LIVE_ORDER);
    expect(out).toHaveLength(LIVE_ORDER.length);
    expect(out.filter(r => r.rows != null).map(r => [r.title, r.rows])).toEqual([
      ["Premature golf resolutions", 230],
      ["Polymarket hockey sign-flip", 36_207],
    ]);
  });

  it("surfaces a dateless entry at the top rather than at an unpredictable position", () => {
    const withHole = [...LIVE_ORDER, c("", "An entry the backend forgot to date")];
    const out = orderCorrections(withHole);
    expect(out[0].title).toBe("An entry the backend forgot to date");
    expect(out).toHaveLength(LIVE_ORDER.length + 1);
  });

  it("answers an absent list with an empty one rather than throwing", () => {
    expect(orderCorrections(undefined)).toEqual([]);
    expect(orderCorrections(null)).toEqual([]);
    expect(orderCorrections([])).toEqual([]);
  });
});

/**
 * The function above is only as real as the array the page hands the `<li>`s.
 *
 * Every assertion in the suite above constructs its own input, so reverting the
 * call site to `data.corrections.map(...)` leaves all of them green and puts
 * the defect straight back on the page. That mutation is the regression this
 * block exists for.
 *
 * Asserted at SOURCE level, and scoped to the corrections section rather than
 * grepped over the whole file — the convention `calibrationAuditHooks.test.tsx`
 * sets for this page and states the reason for (a 2,000-line client component
 * behind SWR, where "rendering it would prove less and break more"), and a
 * whole-file search would be satisfied by an `orderCorrections` import that
 * nothing calls.
 */
describe("#7599 — the ordering reaches the rendered list", () => {
  const PAGE = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
  const source = fs.readFileSync(PAGE, "utf8");

  /**
   * The corrections `<section>` with its comments removed.
   *
   * Both halves are load-bearing. The SLICE is so nothing elsewhere in a
   * 3,300-line file can satisfy these assertions. The STRIP is because the
   * first draft of this guard failed against the fix it was written for: the
   * call site's own comment quotes the old expression (`data.corrections.map`)
   * to say what it replaced, and a substring search cannot tell a line of code
   * from a line of prose describing it. A guard that reads comments is a guard
   * that can be turned green by editing a sentence, and red by writing an
   * honest one.
   */
  const block = (() => {
    const start = source.indexOf('data-testid="calibration-corrections"');
    expect(start).toBeGreaterThan(-1);
    const end = source.indexOf("</section>", start);
    expect(end).toBeGreaterThan(start);
    const sliced = source.slice(start, end);
    // Only `/* … */`. The section has no `//` comment, and stripping to a
    // line-end would eat the rest of any JSX line that merely contains a slash.
    const stripped = sliced.replace(/\/\*[\s\S]*?\*\//g, "");
    // The strip must remove something, or a later refactor that moves the
    // comment leaves this reading raw source again without anyone noticing.
    expect(stripped.length).toBeLessThan(sliced.length);
    return stripped;
  })();

  it("maps the ordered list, not the payload array", () => {
    expect(block).toContain("orderCorrections(data.corrections).map(");
  });

  it("does not map the payload array anywhere in the section", () => {
    // The mutation this catches, written out: `orderCorrections(...)` deleted
    // and the raw array mapped again. The count matters more than the presence
    // — the section legitimately reads `data.corrections` four other times, for
    // the `(13)` summary and two data attributes, and none of those is ordered.
    expect(block).not.toContain("data.corrections.map(");
  });

  it("orders the list that carries the dates, so the sort and the render cannot come apart", () => {
    // The `<li>` prints `c.date` in its own column; a sort applied to some other
    // array would be invisible here. One `.map(` in the section, and it is the
    // ordered one.
    const maps = block.match(/\.map\(/g) ?? [];
    expect(maps).toHaveLength(1);
    expect(block).toContain("{c.date}");
  });
});
