/**
 * #10992 — the website and iPhone niche cards name the same parked categories.
 *
 * On the payload served 2026-10-13 07:29Z web said 42 categories (Rugby 427,
 * Other 386, Boxing 300 …) and the app said 115 / 27.8K outcomes (Serie A 977 …).
 * The app sorted the raw `small_sample_categories` list without web's #7325
 * join, and its normalisation maps had drifted from web's (`mlb`, `lacrosse`),
 * so even the join would have disagreed (46 parked, led by `lacrosse_ncaa`).
 *
 * This file is the web half of the parity pair:
 *   1. web's `normalizeCat` partitions the Swift test's fixture rows into the
 *      list `CalibrationParkedPartition10992Tests` expects from the app;
 *   2. the two Swift maps equal web's `SPORT_KEY_MAP` / `DISPLAY_NAMES` key-for-key,
 *      BOTH directions, so the vocabulary the join runs on cannot drift again;
 *   3. the Swift `smallSampleCategories` is arranged as web's `parkedCategories`
 *      is — filtered on the published `categories` through `normalizedCategory`.
 */

import { readFileSync } from "fs";
import { join } from "path";
import { DISPLAY_NAMES, SPORT_KEY_MAP, normalizeCat } from "@/lib/calibrationCategories";

const REPO = join(__dirname, "../../..");
const IOS_VM = join(REPO, "ios/Bain Luck/Bain Luck/ViewModels/CalibrationViewModel.swift");
const IOS_TEST = join(REPO, "ios/Bain Luck/BainLuckTests/CalibrationParkedPartition10992Tests.swift");

function read(file: string): string {
  try {
    return readFileSync(file, "utf8");
  } catch (err) {
    throw new Error(
      `#10992 parked-partition parity gate could not read ${file}: ${String(err)}. ` +
        `If the file moved, update this guard — do not delete the check.`,
    );
  }
}

/** Comments name the very keys the scans look for; scan code only. */
function stripSwiftComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^[ \t]*\/\/.*$/gm, "").replace(/[ \t]\/\/ .*$/gm, "");
}

function swiftDict(source: string, name: string): Record<string, string> {
  const at = source.indexOf(`let ${name}`);
  if (at === -1) throw new Error(`\`let ${name}\` not found — did it move or get renamed?`);
  const open = source.indexOf("[", source.indexOf("=", at));
  const rest = source.slice(open);
  const end = rest.search(/\n[ \t]*\]/);
  if (end === -1) throw new Error(`could not bound the \`${name}\` literal`);
  const out: Record<string, string> = {};
  for (const m of rest.slice(0, end).matchAll(/"([^"]+)"\s*:\s*"([^"]*)"/g)) out[m[1]] = m[2];
  return out;
}

const vm = stripSwiftComments(read(IOS_VM));

/**
 * The Swift fixture's own JSON literal, read from the Swift test file, so the
 * two halves cannot quietly run on different rows.
 */
function swiftFixture(): {
  buckets: { category: string; n: number }[];
  small_sample_categories: { category: string; outcomes: number }[];
  min_category_outcomes: number;
} {
  const src = read(IOS_TEST);
  const m = src.match(/static let payload = """\n([\s\S]*?)\n\s*"""/);
  if (!m) throw new Error("could not find the Swift test's `payload` literal");
  return JSON.parse(m[1]);
}

/** Web's `categories` + `parkedCategories`, as `app/calibration/page.tsx` computes them. */
function webPartition(data: ReturnType<typeof swiftFixture>) {
  const catMap: Record<string, number> = {};
  for (const b of data.buckets) {
    const k = normalizeCat(b.category);
    catMap[k] = (catMap[k] || 0) + b.n;
  }
  const published = new Set(
    Object.entries(catMap).filter(([, n]) => n >= data.min_category_outcomes).map(([c]) => c),
  );
  const parked = [...data.small_sample_categories]
    .filter((c) => !published.has(normalizeCat(c.category)))
    .sort((a, b) => b.outcomes - a.outcomes);
  return { published, parked };
}

describe("#10992 — web partitions the app's fixture into the list the app is held to", () => {
  it("parks rugby, other and boxing and nothing whose parent is published", () => {
    const data = swiftFixture();
    expect(data.small_sample_categories.length).toBe(8);
    const { published, parked } = webPartition(data);
    expect([...published].sort()).toEqual(["baseball", "football", "lacrosse", "soccer"]);
    expect(parked.map((c) => [c.category, c.outcomes])).toEqual([
      ["rugby", 427],
      ["other", 386],
      ["boxing", 300],
    ]);
    expect(parked.reduce((s, c) => s + c.outcomes, 0)).toBe(1113);
  });

  it("matches the expectation the Swift test asserts, read from that file", () => {
    const src = read(IOS_TEST);
    const m = src.match(/expectedParked[^=]*=\s*\[([\s\S]*?)\]\n/);
    if (!m) throw new Error("could not find `expectedParked` in the Swift test");
    const swiftExpected = [...m[1].matchAll(/\("([^"]+)",\s*(\d+),/g)].map((x) => [x[1], Number(x[2])]);
    expect(swiftExpected.length).toBe(3);
    const { parked } = webPartition(swiftFixture());
    expect(parked.map((c) => [c.category, c.outcomes])).toEqual(swiftExpected);
  });
});

describe("#10992 — the app normalises on web's vocabulary, key-for-key", () => {
  it("sportKeyMap equals SPORT_KEY_MAP, both directions", () => {
    const swift = swiftDict(vm, "sportKeyMap");
    expect(Object.keys(swift).length).toBeGreaterThanOrEqual(20);
    expect(swift).toEqual(SPORT_KEY_MAP);
  });

  it("categoryDisplayNames is keyed exactly as DISPLAY_NAMES, both directions", () => {
    // Keys decide which bases roll up (`normalizedCategory` / `normalizeCat`);
    // the labels are pinned separately (#7722), so this compares the key set.
    const swift = swiftDict(vm, "categoryDisplayNames");
    expect(Object.keys(swift).sort()).toEqual(Object.keys(DISPLAY_NAMES).sort());
  });
});

describe("#10992 — the app's parked list is web's join", () => {
  it("filters on the published categories through normalizedCategory", () => {
    const at = vm.indexOf("var smallSampleCategories:");
    expect(at).toBeGreaterThan(-1);
    const body = vm.slice(at, vm.indexOf("var smallSampleTotal", at));
    expect(body).toMatch(/Set\(categories\)/);
    expect(body).toMatch(/\.filter\s*\{\s*!published\.contains\(Self\.normalizedCategory\(\$0\.category\)\)\s*\}/);
    expect(body).toMatch(/\.sorted\s*\{\s*\$0\.outcomes\s*>\s*\$1\.outcomes\s*\}/);
  });
});
