// LAT-P200: `next/dynamic` in a Server Component splits NOTHING.
//
// `app/layout.tsx` declared three pieces of header chrome as
// `dynamic(() => import(...), { ssr: false })`. Read as source that says "this
// is off the first load". Measured against the deployed bundle (2026-09-02,
// master 04f6cc6f) it was not: SearchBar.tsx, nprogress, NavigationProgress.tsx
// and MobileSearchTrigger.tsx all sat in the EAGER `app/layout-*.js` entry
// chunk, on the critical path of every route.
//
// The mechanism is structural, not a bug in anyone's diff. A Server Component
// cannot lazily reference a Client Component: every client module a server file
// names becomes a client *reference* of that file, and Next bundles a layout's
// client references into its entry chunk. `dynamic()` wraps the module in
// `React.lazy` afterwards, by which point webpack has no split point left.
//
// Why this is a guard and not a comment: the regression is SILENT in both
// directions. Re-adding `dynamic()` to a server file still renders correctly,
// still typechecks, still builds — it just quietly re-inflates every route, and
// nothing surfaces it except a bundle measurement nobody re-runs. And the
// counter-direction is just as silent: "fixing" this red by deleting the
// deferral altogether would also make the file stop importing next/dynamic.
// Both directions are asserted below.
//
// Prior art for the shape: `__tests__/lib/motionBundle.test.ts`.

import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";

const FRONTEND_ROOT = join(__dirname, "..", "..");
const SOURCE_DIRS = ["app", "components"];

/** The client boundary that owns the layout's deferred chrome. */
const DEFERRED_CHROME = join("components", "layout", "DeferredChrome.tsx");

/**
 * Walk the source tree. Unlike the walk in motionBundle.test.ts this one does
 * NOT swallow a failed readdir: a scan that silently skips what it cannot read
 * reports "no offenders" for a directory it never opened, which is the one
 * result this guard must never be able to produce by accident.
 */
function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
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

const read = (file: string) => readFileSync(file, "utf8");
const relative = (file: string) => file.slice(FRONTEND_ROOT.length + 1);

/**
 * A module is a Client Component only if the `use client` directive precedes
 * every import — that is the position the directive is load-bearing in. A
 * `"use client"` appearing later in a file is a string, not a directive, and
 * treating it as one is how a scan like this goes vacuously green.
 */
function isClientModule(text: string): boolean {
  const lines = text.split("\n");
  const directive = lines.findIndex((l) => /^\s*(["'])use client\1;?\s*$/.test(l));
  if (directive === -1) return false;
  const firstImport = lines.findIndex((l) => /^\s*import[\s{*]/.test(l));
  return firstImport === -1 || directive < firstImport;
}

function importsNextDynamic(text: string): boolean {
  return /^\s*import\s+[\w{][^\n]*from\s*["']next\/dynamic["']/m.test(text);
}

describe("LAT-P200 next/dynamic only appears where it can actually split", () => {
  test("the scan sees a real tree, and classifies both kinds of module", () => {
    // Vacuity control. Every assertion below is "this list is empty"; if the
    // walk returned nothing, or decided every file is a client module, they
    // would all pass while checking nothing. Both known-good anchors are named
    // explicitly so a rename breaks this test rather than hollowing the others.
    const files = sourceFiles();
    expect(files.length).toBeGreaterThan(200);

    const rels = files.map(relative);
    expect(rels).toContain(join("app", "layout.tsx"));
    expect(rels).toContain(DEFERRED_CHROME);

    // A known Server Component and a known Client Component, classified as such.
    expect(isClientModule(read(join(FRONTEND_ROOT, "app", "layout.tsx")))).toBe(false);
    expect(isClientModule(read(join(FRONTEND_ROOT, DEFERRED_CHROME)))).toBe(true);

    const clients = files.filter((f) => isClientModule(read(f)));
    expect(clients.length).toBeGreaterThan(50);
    expect(clients.length).toBeLessThan(files.length);
  });

  test("no Server Component imports next/dynamic", () => {
    // The defect class. On master this list was ["app/layout.tsx"].
    const offenders = sourceFiles()
      .filter((file) => {
        const text = read(file);
        return !isClientModule(text) && importsNextDynamic(text);
      })
      .map(relative)
      .sort();

    expect(offenders).toEqual([]);
  });

  test("the layout still defers its chrome — it did not just stop deferring", () => {
    // The counter-direction. Deleting the deferral would also satisfy the test
    // above, and would put the same bytes back on the critical path by a
    // different route, so the deferral itself is asserted.
    const chrome = read(join(FRONTEND_ROOT, DEFERRED_CHROME));

    expect(isClientModule(chrome)).toBe(true);
    for (const mod of ["NavigationProgress", "SearchBar", "MobileSearchTrigger"]) {
      expect(chrome).toMatch(
        new RegExp(`dynamic\\(\\s*\\(\\)\\s*=>\\s*import\\(\\s*["']@/components/${mod}["']`),
      );
    }

    // And the layout reaches them only through that boundary — a direct
    // `import SearchBar from "@/components/SearchBar"` in the server layout
    // would restore the eager bundling with no dynamic() in sight.
    const layout = read(join(FRONTEND_ROOT, "app", "layout.tsx"));
    expect(layout).toMatch(/from\s*["']@\/components\/layout\/DeferredChrome["']/);
    for (const mod of ["NavigationProgress", "SearchBar", "MobileSearchTrigger"]) {
      expect(layout).not.toMatch(new RegExp(`from\\s*["']@/components/${mod}["']`));
    }
  });

  test("the deferred slots reserve their box, so deferring cannot become a shift", () => {
    // `ssr: false` already leaves these slots empty in the server HTML; an
    // async chunk lengthens that window. Without a placeholder the header would
    // grow when the chunk lands, which trades bytes for CLS.
    const chrome = read(join(FRONTEND_ROOT, DEFERRED_CHROME));
    const loadingOptions = chrome.match(/loading:\s*\w+/g) ?? [];

    expect(loadingOptions.length).toBe(2); // SearchBar + MobileSearchTrigger
    // NavigationProgress renders null, so it has no box and needs no placeholder.
    expect(chrome).toMatch(/const NavigationProgressImpl = dynamic\([\s\S]*?\{ ssr: false \},\n\);/);
  });
});
