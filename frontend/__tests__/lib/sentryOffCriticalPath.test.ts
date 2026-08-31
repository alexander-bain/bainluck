// LAT-P171: the Sentry BROWSER SDK must not sit in the chunk graph every route
// loads before it can hydrate.
//
// ## What was measured, 2026-08-31, against deployed sha 6043c1c0
//
// `@sentry/nextjs` was 102 kB of the 160 kB "First Load JS shared by all" — 42%
// of Discover's 243 kB first load, paid on EVERY route. And it was reporting
// nothing: `NEXT_PUBLIC_SENTRY_DSN` is not set on Vercel, no DSN string appears
// anywhere in the served JS, and over 14 days the org's only reporting SDK was
// `sentry.python.fastapi` (2,396 events) — ZERO events and ZERO transactions
// from the JavaScript SDK. Moving it behind the DSN took `/` from 243 kB to
// 183 kB first load and the shared chunk from 160 kB to 90.5 kB.
//
// This is on the COLD path Alex measured. All entry chunks must download, parse
// and execute before React hydrates, and the `/api/feed` request that gates the
// first card is not issued until hydration runs.
//
// ## Why this is a SOURCE guard and not a bundle scan
//
// A bundle scan answers for whatever `.next` was last built, so it is green on a
// stale build and cannot run before one — the same trap `motionBundle.test.ts`
// documents, and the reason that guard is also asserted at the source level. The
// regression here is silent in the same way: one `import * as Sentry from
// "@sentry/nextjs"` added to any client module re-pins 102 kB onto every route,
// and no build, typecheck or render test fails. Nothing goes red except a bundle
// nobody re-measures.
//
// ## What is deliberately still allowed
//
// The SERVER and EDGE runtimes never ship to a browser, so they keep their plain
// static imports. `next.config.mjs` runs at build time. Everything reachable from
// a client component must reach the SDK through `import("@sentry/nextjs")`, which
// webpack splits into an async chunk — and, because the DSN is inlined at build
// time, drops entirely when there is none.

import { readFileSync, readdirSync, statSync } from "fs";
import { join, relative } from "path";

const FRONTEND_ROOT = join(__dirname, "..", "..");
const SOURCE_DIRS = ["app", "components", "lib", "hooks"];

/**
 * Files permitted to import `@sentry/nextjs` STATICALLY. Each entry is a
 * frontend-root-relative path and each is here for a runtime reason, not a
 * grandfathering reason: none of them is ever parsed by a browser.
 */
const SERVER_ONLY_STATIC_IMPORTERS = new Set([
  "sentry.server.config.ts", // Node runtime, loaded via instrumentation.ts
  "sentry.edge.config.ts", // Edge runtime, loaded via instrumentation.ts
  "next.config.mjs", // build time only
]);

/**
 * Client-reachable files that MUST reach the SDK dynamically. Listing them by
 * name (rather than only asserting the absence of static imports everywhere)
 * makes deleting the dynamic call site a failure too — otherwise a file that
 * drops Sentry entirely, losing error reporting the moment a DSN is set, would
 * pass this guard silently.
 */
const REQUIRED_DYNAMIC_IMPORTERS = ["sentry.client.config.ts", "app/global-error.tsx"];

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
      } else if (/\.(tsx?|mjs)$/.test(entry)) {
        out.push(full);
      }
    }
  };
  for (const dir of SOURCE_DIRS) walk(join(FRONTEND_ROOT, dir));
  // The four config files live at the frontend root, outside SOURCE_DIRS.
  for (const entry of readdirSync(FRONTEND_ROOT)) {
    if (/^(sentry\..*\.ts|next\.config\.mjs|instrumentation\.ts)$/.test(entry)) {
      out.push(join(FRONTEND_ROOT, entry));
    }
  }
  return out;
}

const read = (file: string) => readFileSync(file, "utf8");
const rel = (file: string) => relative(FRONTEND_ROOT, file).split("\\").join("/");

/** `import ... from "@sentry/nextjs"` — the static form webpack cannot split. */
const STATIC_IMPORT = /^\s*import\s[^;]*?from\s+["']@sentry\/nextjs["']/m;
/** `import("@sentry/nextjs")` — the dynamic form that becomes its own chunk. */
const DYNAMIC_IMPORT = /\bimport\s*\(\s*["']@sentry\/nextjs["']\s*\)/;

describe("LAT-P171 — the Sentry browser SDK stays off the hydration path", () => {
  it("no client-reachable module imports @sentry/nextjs statically", () => {
    const offenders = sourceFiles()
      .filter((f) => STATIC_IMPORT.test(read(f)))
      .map(rel)
      .filter((f) => !SERVER_ONLY_STATIC_IMPORTERS.has(f));

    expect(offenders).toEqual([]);
  });

  it("the guard can actually see a static import (it is not vacuous)", () => {
    // If `STATIC_IMPORT` ever stops matching the real syntax, the test above
    // passes for every file and proves nothing. Pin it against both the shape it
    // must catch and the shape it must not.
    expect(STATIC_IMPORT.test('import * as Sentry from "@sentry/nextjs";')).toBe(true);
    expect(STATIC_IMPORT.test('import { init } from "@sentry/nextjs";')).toBe(true);
    expect(STATIC_IMPORT.test('void import("@sentry/nextjs").then(s => s.init());')).toBe(
      false
    );
    // And the allowlist must name files that exist, or it is silently empty.
    for (const f of SERVER_ONLY_STATIC_IMPORTERS) {
      expect(() => read(join(FRONTEND_ROOT, f))).not.toThrow();
    }
  });

  it("the client entry points still load the SDK, dynamically and DSN-gated", () => {
    for (const f of REQUIRED_DYNAMIC_IMPORTERS) {
      const body = read(join(FRONTEND_ROOT, f));
      expect(DYNAMIC_IMPORT.test(body)).toBe(true);
      // The gate is what lets webpack drop the branch when no DSN is configured.
      expect(body).toContain("NEXT_PUBLIC_SENTRY_DSN");
    }
  });
});
