// #7015 follow-on — Tailwind must scan every directory that emits class names.
//
// This exists because of a regression this lane shipped and caught on its own
// after-check. `SPORT_COLORS` moved from `app/sport/page.tsx` into
// `lib/sportDirectory.ts`, and `tailwind.config.ts` listed only `./app/**` and
// `./components/**`. Tailwind therefore never saw the tint strings, purged
// them, and Golf, Tennis and MMA lost tints they had rendered for months.
//
// Every signal said fine. `npm run build` exit 0. `npm run typecheck` exit 0.
// 13,319 jest tests green. The class simply was not in the stylesheet: measured
// on the served CSS, `bg-emerald-50`, `bg-lime-50`, `bg-rose-50` and
// `bg-amber-50` were all absent. `lib/eventKeyStats.ts` and `lib/eiColors.ts`
// had been paying the same tax silently for far longer.
//
// So the guard is not "lib is in the list" — that is the fix restated. It
// COMPUTES which source directories contain class literals and requires each
// to be covered, so the next `utils/` or `hooks/` module that emits a class
// fails here instead of shipping an untinted element.

import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";

const FRONTEND = join(__dirname, "..");
const CONFIG = join(FRONTEND, "tailwind.config.ts");

/** Directories that could plausibly hold rendered class names. */
const CANDIDATE_DIRS = ["app", "components", "lib", "hooks", "utils"];

const SOURCE_EXT = /\.(ts|tsx|js|jsx|mdx)$/;

/**
 * A Tailwind colour utility written as a string literal: `bg-rose-50`,
 * `text-amber-600`, `border-sky-200`. Deliberately narrow — a colour utility is
 * the shape that fails INVISIBLY when purged, because the element still renders,
 * just unstyled. Layout utilities usually announce themselves.
 */
const COLOUR_CLASS = /\b(?:bg|text|border|ring|from|via|to)-[a-z]+-\d{2,3}\b/;

function walk(dir: string, out: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return out; // directory absent — not every candidate exists
  }
  for (const entry of entries) {
    if (entry === "node_modules" || entry === ".next") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (SOURCE_EXT.test(entry)) out.push(full);
  }
  return out;
}

function contentGlobs(): string[] {
  const src = readFileSync(CONFIG, "utf8");
  const start = src.indexOf("content:");
  if (start === -1) {
    throw new Error("tailwind.config.ts has no `content:` key — fix this reader.");
  }
  const open = src.indexOf("[", start);
  const close = src.indexOf("]", open);
  if (open === -1 || close === -1) {
    throw new Error("Could not read the `content` array out of tailwind.config.ts.");
  }
  const globs = [...src.slice(open, close).matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  if (globs.length === 0) {
    throw new Error(
      "Parsed zero globs from `content` — the reader broke. Fix it rather " +
        "than letting this suite pass over an empty list.",
    );
  }
  return globs;
}

describe("#7015 Tailwind scans every directory that emits class names", () => {
  const globs = contentGlobs();

  it("reads the content globs (anti-vacuity)", () => {
    expect(globs.length).toBeGreaterThanOrEqual(3);
    expect(globs.some((g) => g.startsWith("./app/"))).toBe(true);
  });

  it("covers every source directory that contains a colour class literal", () => {
    const emitters = CANDIDATE_DIRS.filter((dir) =>
      walk(join(FRONTEND, dir)).some((file) =>
        COLOUR_CLASS.test(readFileSync(file, "utf8")),
      ),
    );

    // If this is empty the scan broke; every real tree has emitters.
    expect(emitters.length).toBeGreaterThan(0);

    const uncovered = emitters.filter(
      (dir) => !globs.some((glob) => glob.startsWith(`./${dir}/`)),
    );
    expect(uncovered).toEqual([]);
  });

  it("covers lib/ specifically — the directory whose omission shipped the regression", () => {
    expect(globs.some((g) => g.startsWith("./lib/"))).toBe(true);
  });
});

/**
 * Colour families that `theme.extend.colors` redefines as a FLAT STRING
 * (`emerald: '#10B981'`). Doing that replaces the whole default scale, so
 * `bg-emerald-50` stops being a class Tailwind can emit and any element wearing
 * it renders with no background — silently, and identically in dev and CI.
 *
 * Computed from the config, not listed, so a fourth override is caught too.
 */
function flatOverriddenFamilies(): string[] {
  const src = readFileSync(CONFIG, "utf8");
  const open = src.indexOf("colors: {");
  if (open === -1) throw new Error("no `colors:` block in tailwind.config.ts");
  // Only the top level of the block: `  \t\t\tname: '#RRGGBB',`
  const block = src.slice(open, src.indexOf("\n  \t\t},", open));
  const families = [...block.matchAll(/^\s*([a-z]+): '#[0-9A-Fa-f]{3,8}',?$/gm)].map(
    (m) => m[1],
  );
  if (families.length === 0) {
    throw new Error(
      "Parsed zero flat colour overrides — the reader broke. `emerald` and " +
        "`amber` are known to be there, so an empty result is a bug in this " +
        "parser, not a clean config.",
    );
  }
  return families;
}

describe("#7015 the sport directory's tints are classes Tailwind can actually emit", () => {
  it("finds the known flat overrides (anti-vacuity)", () => {
    const flat = flatOverriddenFamilies();
    expect(flat).toContain("emerald");
    expect(flat).toContain("amber");
  });

  it("uses no colour family whose scale the config has destroyed", () => {
    // This is the assertion that would have caught the Boxing card shipping an
    // `amber` tint that can never render, and Golf's long-standing `emerald`.
    const flat = new Set(flatOverriddenFamilies());
    const register = readFileSync(join(FRONTEND, "lib", "sportDirectory.ts"), "utf8");
    const tints = [...register.matchAll(/tint: "([^"]+)"/g)].map((m) => m[1]);

    expect(tints.length).toBe(11);

    const broken = tints.filter((tint) =>
      [...tint.matchAll(/bg-([a-z]+)-\d{2,3}/g)].some((m) => flat.has(m[1])),
    );
    expect(broken).toEqual([]);
  });

  it("declares every tint inside a directory the scanner reads", () => {
    expect(contentGlobs().some((g) => g.startsWith("./lib/"))).toBe(true);
  });
});
