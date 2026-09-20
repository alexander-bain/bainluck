/**
 * #7536 — the two Accuracy surfaces publish the same benchmarks, or CI says so.
 *
 * THE BUG. Web repaired the "How We Compare" card three times — CAL-P1261
 * (#6278: only our own row is graded, our row carries its cohort, a published
 * RANGE is drawn as a band and never as an invented midpoint) and then #7524
 * (the Iowa Electronic Markets row is a vote-SHARE error, not a calibration
 * error). The Swift twin took none of them. For three ships the app drew a
 * solid bar at **3.5pp** beside its own caption reading **"(2–5pp)"**, printed
 * all four figures green on `eceColor`'s thresholds, and plotted Berg et al.'s
 * 1.5pp beside our per-bucket error.
 *
 * WHY NOTHING CAUGHT IT. Both lists are literals, three thousand miles apart in
 * two languages, and nothing connected them: no iOS test named any of the four
 * numbers, the cross-surface parity hooks cover the hero and the source table
 * but not this card, and CI compiles no Swift at all. Each web ship was
 * correct, complete and invisible to the other surface.
 *
 * SO THIS GUARDS THE COUPLING, NOT EITHER LIST. It reads both files as source
 * and requires that the set of PUBLISHED figures agree — same count, same
 * kinds, same numbers. A new benchmark added to one surface reddens CI until
 * the other has it; a figure edited on one surface reddens CI until both say
 * the same thing. The per-surface rendering rules stay where they can be
 * asserted properly: web's in `calibrationAuditHooks.test.tsx`, iOS's in
 * `CalibrationBenchmarkTests`.
 *
 * It lives in jest because jest is a deploy gate here and the Swift test target
 * is not reachable from CI.
 */

import { readFileSync } from "fs";
import { join } from "path";

const WEB_PAGE = join(__dirname, "../../app/calibration/page.tsx");
const IOS_ROWS = join(
  __dirname,
  "../../../ios/Bain Luck/Bain Luck/Utilities/CalibrationBenchmarks.swift",
);
const IOS_VIEW = join(
  __dirname,
  "../../../ios/Bain Luck/Bain Luck/Views/CalibrationView.swift",
);

/**
 * Both files quote the removed rows in their headers so the record survives —
 * "a fourth row was here: Iowa Electronic Markets, 1.5" is documentation, and a
 * raw substring scan would read it as the defect.
 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/** A published benchmark, in the only terms the two surfaces can be compared in. */
type Benchmark =
  | { kind: "point"; label: string; value: number }
  | { kind: "range"; label: string; low: number; high: number };

/** The first word of a label — the two surfaces word the rest differently on purpose. */
const nameOf = (label: string) => label.trim().split(/[\s(]/)[0];

function webBenchmarks(): { ours: string; published: Benchmark[] } {
  const source = stripComments(readFileSync(WEB_PAGE, "utf8"));
  const end = source.indexOf("] as BenchmarkRow[]");
  expect(end).toBeGreaterThan(-1);
  const start = source.lastIndexOf("([", end);
  expect(start).toBeGreaterThan(-1);
  const block = source.slice(start, end);

  const published: Benchmark[] = [];
  let ours = "";
  for (const line of block.split("\n")) {
    if (!line.includes("label:")) continue;
    const highlight = /highlight:\s*true/.test(line);
    // Our row's label is a `priceCohort` ternary; every other label is a literal.
    const label = [...line.matchAll(/"([^"]+)"/g)].map((m) => m[1]).pop() ?? "";
    if (highlight) {
      ours = label;
      continue;
    }
    const mce = line.match(/\bmce:\s*([\d.]+)/);
    const low = line.match(/\brangeLow:\s*([\d.]+)/);
    const high = line.match(/\brangeHigh:\s*([\d.]+)/);
    if (low && high) {
      published.push({ kind: "range", label, low: +low[1], high: +high[1] });
    } else if (mce) {
      published.push({ kind: "point", label, value: +mce[1] });
    } else {
      throw new Error(`web benchmark row has neither a figure nor a range: ${line}`);
    }
  }
  return { ours, published };
}

function iosBenchmarks(): { ours: string; published: Benchmark[] } {
  const source = stripComments(readFileSync(IOS_ROWS, "utf8"));
  const start = source.indexOf("static func rows(");
  expect(start).toBeGreaterThan(-1);
  const block = source.slice(start);

  // Sliced call-by-call rather than matched with one regex: our own row's
  // `detail:` holds a string interpolation, so any pattern that stops at the
  // first `)` reads half a call and silently drops the `isOurs:` that says
  // whose row it is.
  const calls = [...block.matchAll(/\.(point|range)\(/g)];
  const published: Benchmark[] = [];
  let ours = "";
  calls.forEach((call, i) => {
    const text = block.slice(call.index!, calls[i + 1]?.index ?? block.length);
    const label = text.match(/"([^"]+)"/)?.[1] ?? "";
    if (call[1] === "range") {
      const low = text.match(/\blow:\s*([\d.]+)/);
      const high = text.match(/\bhigh:\s*([\d.]+)/);
      if (!low || !high) throw new Error(`iOS range row has no ends: ${text}`);
      published.push({ kind: "range", label, low: +low[1], high: +high[1] });
      return;
    }
    if (/isOurs:\s*true/.test(text)) {
      ours = label;
      return;
    }
    const value = text.match(/"[^"]+",\s*([\d.]+)/);
    if (!value) throw new Error(`iOS point row has no figure: ${text}`);
    published.push({ kind: "point", label, value: +value[1] });
  });
  return { ours, published };
}

describe("#7536 — the Accuracy card's benchmarks are the same on both surfaces", () => {
  const web = webBenchmarks();
  const ios = iosBenchmarks();

  /** The parse is the load-bearing part: an empty list agrees with anything. */
  it("reads a real list off each surface", () => {
    expect(web.published.length).toBeGreaterThan(0);
    expect(ios.published.length).toBeGreaterThan(0);
    expect(web.ours).toMatch(/Bain Luck/);
    expect(ios.ours).toMatch(/Bain Luck/);
  });

  it("publishes the same benchmarks, by name and by figure", () => {
    const key = (b: Benchmark) =>
      b.kind === "range"
        ? `${nameOf(b.label)}:${b.low}-${b.high}pp`
        : `${nameOf(b.label)}:${b.value}pp`;
    expect(ios.published.map(key).sort()).toEqual(web.published.map(key).sort());
  });

  /**
   * #6278 item 3, as a cross-surface rule: a benchmark published as a range is
   * a range on BOTH surfaces. iOS drew Arrow's 2–5pp as a solid bar at 3.5 for
   * three ships, and 3.5 is the number that must never reappear on either side.
   */
  it("draws every published range as a range, and nowhere as its midpoint", () => {
    for (const surface of [web, ios]) {
      const arrow = surface.published.find((b) => /Academic/.test(b.label));
      expect(arrow).toBeDefined();
      expect(arrow!.kind).toBe("range");
      expect(arrow).toMatchObject({ low: 2, high: 5 });
    }
    for (const b of [...web.published, ...ios.published]) {
      if (b.kind === "point") expect(b.value).not.toBe(3.5);
    }
  });

  /**
   * #7524. Berg et al.'s 1.5pp is an absolute error on predicted vote share,
   * and our figure is a per-bucket calibration error — two quantities that
   * share a unit. It stays in Further Reading, where it is described correctly.
   */
  it("plots no vote-share figure as a calibration benchmark", () => {
    for (const b of [...web.published, ...ios.published]) {
      expect(b.label).not.toMatch(/Iowa|Berg/i);
      if (b.kind === "point") expect(b.value).not.toBe(1.5);
    }
  });

  /**
   * #6278 item 2 on the Swift side. The model decides which figure may be
   * coloured; this is the half that proves the view asks. Both `eceColor` calls
   * in the benchmark row have to be gated — an ungated one prints our verdict
   * over somebody else's published number, which is how all four rows came out
   * green.
   */
  it("colours only the graded figure in the iOS benchmark row", () => {
    const view = stripComments(readFileSync(IOS_VIEW, "utf8"));
    const start = view.indexOf("private func benchmarkRow(");
    expect(start).toBeGreaterThan(-1);
    const body = view.slice(start, view.indexOf("\n    // MARK:", start));
    expect(body).toContain("eceColor");
    expect(body).toMatch(/row\.isGraded\s*\n?\s*\?\s*viewModel\.eceColor/);
    expect(body.match(/eceColor/g)?.length).toBe(1);
  });

  /**
   * #6278 item 1 on the Swift side, same reasoning: the model carries the tag,
   * and a view that never draws it leaves our row reading as un-scoped as the
   * published benchmarks beside it — which is the defect exactly.
   */
  it("draws the cohort tag the iOS benchmark row carries", () => {
    const view = stripComments(readFileSync(IOS_VIEW, "utf8"));
    const start = view.indexOf("private func benchmarkRow(");
    const body = view.slice(start, view.indexOf("\n    // MARK:", start));
    expect(body).toContain("row.cohortTag");
    expect(body).toContain("row.figureQualifier");
  });
});
