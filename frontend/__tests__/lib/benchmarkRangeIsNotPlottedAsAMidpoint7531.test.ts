// #7531 — a benchmark the page sources as a RANGE is drawn as a range, not as
// the midpoint of one.
//
// "How We Compare" plotted "Metaculus (self-reported) — 2.5pp" as a solid bar
// from 0 to 25% of its 0-10pp axis: a measured point value. The page does not
// have that number. Further Reading, 5,500px down, is where it comes from and
// says "~2-3pp mean calibration error". 2.5 is the midpoint of 2-3 and appears
// nowhere else on the page.
//
// CAL-P1261 (#6278) removed exactly this construction from the Arrow row and
// left the rule in the `BenchmarkRow` type: `mce` and (`rangeLow`, `rangeHigh`)
// are alternatives, because "inventing one to draw a bar with is what CAL-P1261
// removed". It missed the Metaculus row for a legible reason — Arrow's range is
// visible in its own LABEL, so the midpoint was obvious, while Metaculus's lives
// in a section 5,500px away and the row read as a point value.
//
// Distinct from #7524, which removed the Iowa/Berg row because its figure was a
// different STATISTIC. Metaculus's figure is our statistic; only its shape was
// wrong. `benchmarkRowsAreTheSameStatisticAsOurs7524.test.ts` guards the other
// question and the two must not be collapsed.
//
// Source-level, following this page's stated convention
// (`calibrationCensoredWiringReachesThePage6211.test.ts`): a 3,000-line client
// component behind SWR, where "rendering it would prove less and break more".

import * as fs from "fs";
import * as path from "path";

const PAGE = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
const source = fs.readFileSync(PAGE, "utf8");

/**
 * The file with comments stripped.
 *
 * Load-bearing, not hygiene: this fix's own comment quotes both the removed
 * `mce: 2.5` and the Further Reading sentence verbatim, to record why the row
 * changed shape. Every assertion below would read that explanation as the code
 * it constrains, and the obvious "fix" would be to delete the reasoning.
 */
const code = source
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .split("\n")
  .filter(line => !line.trim().startsWith("//"))
  .join("\n");

/** The benchmark list only — heading to the footnote that closes the section. */
function benchmarkList(): string {
  const start = code.indexOf(">How We Compare</h2>");
  expect(start).toBeGreaterThan(-1);
  const end = code.indexOf("reference points, not a ranking", start);
  expect(end).toBeGreaterThan(start);
  return code.slice(start, end);
}

/** The Further Reading list only. */
function furtherReading(): string {
  const start = code.indexOf(">Further Reading</h2>");
  expect(start).toBeGreaterThan(-1);
  const end = code.indexOf("</section>", start);
  expect(end).toBeGreaterThan(start);
  return code.slice(start, end);
}

type ParsedRow = {
  line: string;
  label: string | null;
  mce: number | null;
  rangeLow: number | null;
  rangeHigh: number | null;
  highlight: boolean;
};

/**
 * The row object literals, parsed out of the array the section maps over.
 *
 * Deliberately line-based and deliberately strict about what it recognises: a
 * row it cannot parse is reported, not skipped. A parser that silently drops
 * the row it does not understand is how a guard like this goes quiet — and the
 * row most likely to be unparseable is the newly-added one this file exists to
 * catch.
 */
function benchmarkRows(list: string): ParsedRow[] {
  return list
    .split("\n")
    .map(l => l.trim())
    .filter(l => l.startsWith("{ label:"))
    .map(line => {
      const num = (key: string) => {
        const m = line.match(new RegExp(`\\b${key}:\\s*(-?\\d+(?:\\.\\d+)?)`));
        return m ? parseFloat(m[1]) : null;
      };
      // Our row builds its label from a ternary, so a literal is not required.
      const label = line.match(/label:\s*"([^"]+)"/);
      return {
        line,
        label: label ? label[1] : null,
        mce: num("mce"),
        rangeLow: num("rangeLow"),
        rangeHigh: num("rangeHigh"),
        highlight: /highlight:\s*true/.test(line),
      };
    });
}

/**
 * Every `N-Mpp` range the page publishes for a named source in Further Reading,
 * keyed by the source's name as the row labels spell it.
 *
 * Read from the prose rather than hardcoded, so that a later reword of either
 * side reddens this file instead of quietly re-opening the defect.
 */
function furtherReadingRanges(fr: string): Map<string, [number, number]> {
  const out = new Map<string, [number, number]>();
  for (const li of fr.split("<li>").slice(1)) {
    const name = li.match(/<strong[^>]*>([^<]+)<\/strong>/);
    const range = li.match(/~?(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)pp/);
    if (name && range) {
      out.set(name[1].trim(), [parseFloat(range[1]), parseFloat(range[2])]);
    }
  }
  return out;
}

describe("#7531 control — the machinery this guard runs on is real", () => {
  // Anti-vacuity. Every assertion in this file is satisfied by an empty slice,
  // an empty row list, or an empty range map, and the comment-stripping above
  // is exactly the step that can silently produce one.
  it("both slices are present, substantial and disjoint", () => {
    const list = benchmarkList();
    const fr = furtherReading();
    expect(list.length).toBeGreaterThan(400);
    expect(fr.length).toBeGreaterThan(400);
    expect(list).not.toContain(">Further Reading</h2>");
    expect(fr).not.toContain("cohortMCE");
  });

  it("the parser finds every row, including ours", () => {
    const rows = benchmarkRows(benchmarkList());
    // Matches the count the #7524 guard pins from the other direction.
    expect(rows.length).toBe(3);
    expect(rows.filter(r => r.highlight).length).toBe(1);
    // Ours carries neither literal — it reads the live payload.
    const ours = rows.find(r => r.highlight)!;
    expect(ours.mce).toBeNull();
    expect(ours.line).toContain("cohortMCE");
    // …and every published row carries exactly one of the two shapes, which is
    // the rule the `BenchmarkRow` type states and nothing else enforces.
    for (const row of rows.filter(r => !r.highlight)) {
      const isPoint = row.mce !== null;
      const isRange = row.rangeLow !== null && row.rangeHigh !== null;
      expect(isPoint !== isRange).toBe(true);
    }
  });

  it("Further Reading publishes ranges this guard can read", () => {
    const ranges = furtherReadingRanges(furtherReading());
    expect(ranges.size).toBeGreaterThan(0);
    expect(ranges.get("Metaculus Track Record")).toEqual([2, 3]);
  });
});

describe("#7531 no benchmark is plotted as the midpoint of its own range", () => {
  it("the Metaculus row draws the range Further Reading sources, not 2.5", () => {
    const row = benchmarkRows(benchmarkList()).find(r =>
      (r.label ?? "").startsWith("Metaculus")
    );
    expect(row).toBeDefined();

    // The defect, named by its number: the midpoint of 2-3, shown nowhere else.
    expect(row!.mce).toBeNull();
    expect(benchmarkList()).not.toMatch(/mce:\s*2\.5\b/);

    // Both ends, and both taken from the page's own prose rather than from this
    // file — so a reworded Further Reading entry reddens here instead of
    // letting the two figures drift apart again.
    const published = furtherReadingRanges(furtherReading()).get(
      "Metaculus Track Record"
    );
    expect(published).toBeDefined();
    expect([row!.rangeLow, row!.rangeHigh]).toEqual(published);
  });

  it("no published row carries a point value for a source Further Reading gives as a range", () => {
    // The general rule, so the next row added is covered without an edit here.
    // A row is matched to its citation on the first word of its label, which is
    // how both published rows are named ("Metaculus …", "Academic consensus
    // range (Arrow et al. 2008)" → the Arrow entry carries no range, so it is
    // unconstrained and its provenance stays the open question #7524 named).
    const fr = furtherReading();
    const ranges = furtherReadingRanges(fr);

    for (const row of benchmarkRows(benchmarkList())) {
      if (row.highlight || row.mce === null || !row.label) continue;
      const head = row.label.split(/[\s(]/)[0];
      for (const [cited, [lo, hi]] of ranges) {
        if (!cited.startsWith(head)) continue;
        throw new Error(
          `"${row.label}" plots a point mce of ${row.mce}, but the page sources ` +
            `"${cited}" as ${lo}-${hi}pp. Draw it as a range (rangeLow/rangeHigh); ` +
            `a midpoint invented to give a bar its length is what CAL-P1261 removed.`
        );
      }
    }
  });

  it("strawman: that rule fires on the row as it stood before this fix", () => {
    // The assertion above passes on an empty loop, and it is the one assertion
    // here whose subject is a row that no longer exists. So run the same walk
    // over the pre-fix literal and require it to catch it — otherwise this file
    // would keep passing after someone reintroduced the midpoint in a shape the
    // parser does not recognise.
    const ranges = furtherReadingRanges(furtherReading());
    const before = benchmarkRows(
      '{ label: "Metaculus (self-reported)", mce: 2.5, n: null, highlight: false },'
    );
    expect(before.length).toBe(1);
    expect(before[0].mce).toBe(2.5);

    const caught = before.filter(row => {
      const head = (row.label ?? "").split(/[\s(]/)[0];
      return [...ranges.keys()].some(cited => cited.startsWith(head));
    });
    expect(caught.length).toBe(1);
  });
});
