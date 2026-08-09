// #1631: framer-motion must stay out of First Load JS.
//
// The full `motion` component ships every animation feature to every route that renders one —
// measured at 40.7 kB gzip on /sports, /search, /my-stuff, /preferences, /futures, /futures/[id]
// and /sports/[key], about 31% of /sports's route-own weight. `components/motion.tsx` replaces it
// with `m` behind a lazily-loaded `domAnimation` feature set.
//
// This guard exists because the regression is SILENT in both directions. Re-importing the full
// `motion` at one new call site quietly re-inflates every one of those routes and nothing fails.
// Adding a `layout` or `drag` prop quietly makes `domAnimation` the wrong feature set, and the
// symptom is an animation that simply never runs. Neither shows up in a build, a typecheck, or a
// render test — only in a bundle nobody re-measures. So it is asserted at the source level.
//
// Prior art: the cycle-35 `searchSuggestionDisplay` guard, written for exactly this class of
// drift, immediately found a second unreported copy of the drift it was written to prevent.

import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";

const FRONTEND_ROOT = join(__dirname, "..", "..");
const SOURCE_DIRS = ["app", "components", "lib", "hooks"];

/** The one module allowed to import framer-motion's feature set — it is what code-splits it. */
const FEATURE_MODULE = join("lib", "motionFeatures.ts");
/** The one module allowed to build provider-bound primitives out of `m` + `LazyMotion`. */
const PRIMITIVES_MODULE = join("components", "motion.tsx");

function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    let entries: string[];
    try {
      entries = readdirSync(dir);
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry === "node_modules" || entry === ".next") continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
      } else if (/\.tsx?$/.test(entry)) {
        out.push(full);
      }
    }
  };
  for (const dir of SOURCE_DIRS) walk(join(FRONTEND_ROOT, dir));
  return out;
}

function read(file: string): string {
  return readFileSync(file, "utf8");
}

function relative(file: string): string {
  return file.slice(FRONTEND_ROOT.length + 1);
}

describe("#1631 framer-motion stays out of First Load JS", () => {
  test("no source file imports the full `motion` component from framer-motion", () => {
    const offenders = sourceFiles().filter((file) => {
      if (file.endsWith(PRIMITIVES_MODULE)) return false;
      const text = read(file);
      // Match the named import list on any `... from "framer-motion"` line, then look for a
      // bare `motion` specifier in it. `m`, `AnimatePresence`, `LazyMotion`, `useSpring`,
      // `useTransform` and type-only imports are all fine.
      const importLines = text.match(/import\s*(type\s*)?\{[^}]*\}\s*from\s*["']framer-motion["']/g) ?? [];
      return importLines.some((line) => {
        if (/^import\s*type/.test(line)) return false;
        const names = line.slice(line.indexOf("{") + 1, line.indexOf("}")).split(",");
        return names.some((n) => n.trim().replace(/\s+as\s+.*$/, "") === "motion");
      });
    });

    expect(offenders.map(relative)).toEqual([]);
  });

  test("animation call sites use the provider-bound primitives or an explicit provider", () => {
    // A file using `m.*` without a LazyMotion ancestor renders an un-animated element. Any file
    // importing the raw `m` primitive must therefore also pull in a provider.
    const offenders = sourceFiles().filter((file) => {
      if (file.endsWith(PRIMITIVES_MODULE)) return false;
      const text = read(file);
      const importsRawM = /import\s*\{[^}]*\bm\b[^}]*\}\s*from\s*["']framer-motion["']/.test(text);
      if (!importsRawM) return false;
      return !/MotionProvider/.test(text);
    });

    expect(offenders.map(relative)).toEqual([]);
  });

  test("no layout or drag props — they would make `domAnimation` the wrong feature set", () => {
    // `domAnimation` (~15 kB) covers animations, variants, exit animations and tap/hover/focus.
    // Layout animations and drag/pan need `domMax` (~25 kB). If either appears, the feature set
    // in lib/motionFeatures.ts must change and the bundle saving must be re-measured.
    const RISKY = /\b(layoutId|layoutDependency|layoutScroll|dragConstraints|dragElastic|whileDrag)\s*=|\blayout\s*=\s*\{|\bdrag\s*=\s*\{/;
    const offenders = sourceFiles().filter((file) => RISKY.test(read(file)));

    expect(offenders.map(relative)).toEqual([]);
  });

  test("the feature set is loaded through a dynamic import, not a static one", () => {
    // This is the whole mechanism: a static import would put domAnimation straight back into
    // First Load JS and the bundle win would silently evaporate.
    const primitives = read(join(FRONTEND_ROOT, PRIMITIVES_MODULE));

    expect(primitives).toMatch(/import\(\s*["']@\/lib\/motionFeatures["']\s*\)/);
    expect(primitives).not.toMatch(/^import .*from ["']@\/lib\/motionFeatures["']/m);
  });

  test("the feature module is isolated so it can be code-split", () => {
    // It must export only the feature set. Anything else imported from here would be dragged
    // into the async chunk, or worse, drag the async chunk into the static graph.
    const features = read(join(FRONTEND_ROOT, FEATURE_MODULE));
    const importCount = (features.match(/^import\s/gm) ?? []).length;

    expect(features).toMatch(/export\s*\{\s*domAnimation as default\s*\}\s*from\s*["']framer-motion["']/);
    expect(importCount).toBe(0);
  });

  test("both directions: the primitives really are provider-bound", () => {
    // The fix direction — a call site writing `<motion.div>` must still get a working animation
    // without knowing a provider exists. If these ever stop being wrapped, every converted
    // component silently stops animating.
    const primitives = read(join(FRONTEND_ROOT, PRIMITIVES_MODULE));

    for (const tag of ["div", "span", "button"]) {
      expect(primitives).toMatch(new RegExp(`<m\\.${tag}\\b`));
    }
    expect(primitives).toMatch(/<LazyMotion\b/);
    expect(primitives).toMatch(/export const motion = \{/);
  });
});
