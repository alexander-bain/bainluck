// #7056 / #4040 — a colour family declared as a FLAT STRING silently deletes
// the default scale of the same name, and every `bg-<fam>-500` in the tree
// stops emitting CSS.
//
// The config carried three of them:
//
//     slate:   '#6B7280'      emerald: '#10B981'      amber: '#F59E0B'
//
// Each replaced a whole `{50…950}` scale with one value, so `bg-emerald-50`,
// `text-emerald-600`, `bg-amber-50` and `border-amber-200` were no longer
// classes Tailwind could emit — 207 literals across Discover (the default
// landing page), the event page, calibration and futures.
//
// THE REASON THIS NEEDS A GUARD AND NOT JUST A FIX: every signal we own was
// green the entire time. The element still renders, just with no colour. No
// build error, no lint warning, no type error, 13k jest tests passing. The
// only witness is the built stylesheet, and nothing in CI reads that. #4040
// sat open for weeks with the settled "Won" chip and the hero's green up-arrow
// having literally never rendered green while red-down always did.
//
// So this suite asserts the CLASS of defect from the source tree, where it is
// cheap, in the two independent directions a fix could be undone:
//
//   1. structural — no in-house colour name may shadow a default Tailwind
//      palette. Catches a bad key the moment it is added, before any literal
//      uses it.
//   2. behavioural — no colour literal anywhere under app/, components/ or
//      lib/ may name a family the config has flattened. This is the
//      acceptance criterion of #7056 as filed, and it is what would have gone
//      red on the pre-fix tree (205 emerald/amber/slate literals).
//
// The companion probe `tools/ux1350-dead-palette-census-7056.mjs` checks the
// other end — that the utilities are genuinely present in built CSS — because
// a source-level guard cannot see a purge.

import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";
import defaultColours from "tailwindcss/colors";

const FRONTEND = join(__dirname, "..");
const CONFIG = join(FRONTEND, "tailwind.config.ts");
const SCANNED_DIRS = ["app", "components", "lib"];
const SOURCE_EXT = /\.(ts|tsx|js|jsx|mdx)$/;

/**
 * Colour utilities written as complete literals. Tailwind only ever sees
 * complete strings, so this is the same set the scanner sees.
 */
const COLOUR_CLASS = /\b(?:bg|text|border|ring|from|via|to|divide|fill|stroke)-([a-z]+)-(\d{2,3})\b/g;

/**
 * Default Tailwind palette names — the families a flat override would destroy.
 *
 * Read off the package rather than listed, so a Tailwind upgrade that adds a
 * family is covered without anyone remembering to come back here. The
 * deprecated aliases are skipped explicitly: touching them emits a runtime
 * warning, and they are not names anyone would collide with by accident.
 */
function defaultPaletteNames(): string[] {
  const deprecated = new Set(["lightBlue", "warmGray", "trueGray", "coolGray", "blueGray"]);
  const names = Object.keys(defaultColours).filter((name) => {
    if (deprecated.has(name)) return false;
    const value = (defaultColours as unknown as Record<string, unknown>)[name];
    // A scale is an object of numbered rungs; `inherit`/`current`/`black` are strings.
    return typeof value === "object" && value !== null && "500" in (value as object);
  });
  if (names.length < 15) {
    throw new Error(
      `Read only ${names.length} default palettes off tailwindcss/colors — the ` +
        "reader broke. Tailwind ships ~22; an undercount would let this suite " +
        "pass a genuine collision.",
    );
  }
  return names;
}

/**
 * Families `theme.extend.colors` redefines as a flat string at the TOP level
 * of the block (`forest: '#22C55E'`). Nested objects (`accent: { … }`) keep
 * their scale and are not the hazard.
 *
 * Same parser as the #7015 suite, deliberately — if it drifts, both go red.
 */
function flatOverriddenFamilies(): string[] {
  const src = readFileSync(CONFIG, "utf8");
  const open = src.indexOf("colors: {");
  if (open === -1) throw new Error("no `colors:` block in tailwind.config.ts");
  const block = src.slice(open, src.indexOf("\n  \t\t},", open));
  const families = [...block.matchAll(/^\s*([a-z]+): '#[0-9A-Fa-f]{3,8}',?$/gm)].map((m) => m[1]);
  if (families.length === 0) {
    throw new Error(
      "Parsed zero flat colour overrides — the reader broke. The in-house " +
        "palette (snow, graphite, forest, rust …) is flat by design, so an " +
        "empty result is a bug in this parser, not a clean config.",
    );
  }
  return families;
}

function walk(dir: string, out: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const entry of entries) {
    if (entry === "node_modules" || entry === ".next") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (SOURCE_EXT.test(entry)) out.push(full);
  }
  return out;
}

interface Literal {
  file: string;
  family: string;
  rung: string;
}

function colourLiterals(): Literal[] {
  const found: Literal[] = [];
  for (const dir of SCANNED_DIRS) {
    for (const file of walk(join(FRONTEND, dir))) {
      const src = readFileSync(file, "utf8");
      for (const match of src.matchAll(COLOUR_CLASS)) {
        found.push({ file: file.slice(FRONTEND.length + 1), family: match[1], rung: match[2] });
      }
    }
  }
  return found;
}

describe("#7056 no in-house colour name shadows a default Tailwind palette", () => {
  it("reads both sides (anti-vacuity)", () => {
    // Neither list may be empty: an empty one passes the real check below
    // while examining nothing, which is exactly how this defect survived.
    expect(defaultPaletteNames().length).toBeGreaterThanOrEqual(15);
    expect(flatOverriddenFamilies().length).toBeGreaterThanOrEqual(5);
  });

  it("declares no flat colour whose name is a default palette", () => {
    const defaults = new Set(defaultPaletteNames());
    const collisions = flatOverriddenFamilies().filter((family) => defaults.has(family));

    // On the pre-fix tree this read ["slate", "emerald", "amber"].
    expect(collisions).toEqual([]);
  });

  it("still allows in-house names that collide with nothing", () => {
    // The mechanism must not be read as "flat colours are banned" — the whole
    // in-house palette is flat and correct. Only the collision is the defect.
    const flat = flatOverriddenFamilies();
    expect(flat).toContain("forest");
    expect(flat).toContain("charcoal");
  });
});

describe("#7056 every colour literal names a family that can actually emit", () => {
  const literals = colourLiterals();

  it("finds the tree's colour literals (anti-vacuity)", () => {
    // A broken walk or regex would make the assertion below trivially true.
    expect(literals.length).toBeGreaterThan(500);
    expect(new Set(literals.map((l) => l.file)).size).toBeGreaterThan(50);
  });

  it("uses no family the config has flattened", () => {
    const flat = new Set(flatOverriddenFamilies());
    const dead = literals.filter((l) => flat.has(l.family));

    // Pre-fix this was 205 literals over 60-odd files; the message names them
    // so whoever trips it can see the blast radius rather than a bare count.
    const report = [...new Set(dead.map((l) => `${l.family}-${l.rung} @ ${l.file}`))].sort();
    expect(report).toEqual([]);
  });

  it("keeps the two numeric slate literals that the restored scale now serves", () => {
    // `bg-slate-50/50` and `text-slate-500` were dead for as long as the flat
    // `slate` key existed. They are the cheapest live proof that deleting the
    // key gave a real element its colour back, so they are pinned: if someone
    // reinstates a flat `slate`, the check above fires and this one explains
    // which reader paid for it.
    const slate = literals.filter((l) => l.family === "slate");
    expect(slate.length).toBeGreaterThanOrEqual(2);
    expect(slate.map((l) => l.file)).toContain("components/futures/OutcomeRow.tsx");
  });
});
