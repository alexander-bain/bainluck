/**
 * GA4 hook compliance guard (Queue L2-133 Item 1 — measurement_spec.md §0).
 *
 * CLAUDE.md rule (MANDATORY): "Every frontend page needs 3 GA4 hooks before any
 * conditional return: usePageTracking, useScrollDepth, useEngagementTime."
 *
 * This test freezes that rule structurally: every `frontend/app/**\/page.tsx`
 * must reference all three hooks, OR be an explicitly-documented exemption whose
 * structural reason is re-validated here (so a stub can never silently rot into a
 * real content page that is missing instrumentation).
 *
 * WHAT IS ENFORCED: presence of all 3 hook identifiers in each page.tsx. A
 * whole-file "hooks-before-first-return" check is intentionally NOT done here —
 * helper components/functions defined ABOVE the page component legitimately carry
 * their own `if (...) return null` (e.g. app/search/page.tsx's SuggestionChips),
 * which makes a file-level ordering assertion flaky. Ordering ("before any
 * conditional return") stays a code-review convention; presence is the invariant
 * a machine can guard without false positives. The real regression this catches:
 * a new page shipped with zero (or partial) GA4 instrumentation.
 *
 * Census at authoring (2026-07-16): 53 page.tsx files — 49 carry all 3 hooks
 * directly; 4 are the documented exemptions below. No real content page was
 * missing hooks, so this guard is the deliverable that keeps it that way.
 */
import * as fs from "fs";
import * as path from "path";

const HOOKS = ["usePageTracking", "useScrollDepth", "useEngagementTime"] as const;

const APP_DIR = path.resolve(__dirname, "../../app");

/**
 * Documented exemptions. Each entry names a page.tsx (path relative to app/) that
 * legitimately does NOT call the 3 hooks in its own file, plus a `validate`
 * predicate that re-asserts WHY it is exempt. If the structural reason no longer
 * holds (e.g. a redirect stub grows a real UI), `validate` returns false and the
 * test fails — forcing the maintainer to either add the hooks or update this map.
 */
type Exemption = {
  reason: string;
  validate: (source: string, absPath: string) => boolean;
};

const fileHasAllHooks = (source: string): boolean =>
  HOOKS.every((h) => source.includes(h));

const EXEMPTIONS: Record<string, Exemption> = {
  // Root landing page is a pure re-export of /discover, which is instrumented.
  "page.tsx": {
    reason: "Re-export stub of @/app/discover/page (inherits its hooks at runtime).",
    validate: (src) =>
      /export\s*\{\s*default\s*\}\s*from\s*["']@\/app\/discover\/page["']/.test(src),
  },
  // Server redirect, renders no UI.
  "golf/page.tsx": {
    reason: "Server redirect() to /categories/golf — no rendered UI.",
    validate: (src) => /\bredirect\(/.test(src) && !/\breturn\s*\(/.test(src),
  },
  // Legacy colon-key URL 308 permanentRedirect, renders no UI.
  "event/[domain]/page.tsx": {
    reason: "Legacy event-key 308 permanentRedirect — no rendered UI.",
    validate: (src) => /\b(permanentRedirect|redirect)\(/.test(src),
  },
  // Server component that delegates all 3 hooks to a client child.
  "discover/scorecard/page.tsx": {
    reason: "Server component; delegates the 3 hooks to sibling ScorecardAnalytics.tsx.",
    validate: (src, absPath) => {
      if (!/ScorecardAnalytics/.test(src)) return false;
      const sibling = path.join(path.dirname(absPath), "ScorecardAnalytics.tsx");
      if (!fs.existsSync(sibling)) return false;
      return fileHasAllHooks(fs.readFileSync(sibling, "utf8"));
    },
  },
};

function findPageFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...findPageFiles(full));
    } else if (entry.name === "page.tsx") {
      out.push(full);
    }
  }
  return out;
}

describe("GA4 hook compliance across app/**/page.tsx", () => {
  const pageFiles = findPageFiles(APP_DIR);

  it("finds a sane number of page.tsx files (sanity check on discovery)", () => {
    // Guards against the glob silently matching nothing (which would make every
    // other assertion vacuously pass).
    expect(pageFiles.length).toBeGreaterThan(40);
  });

  it("every page.tsx carries all 3 GA4 hooks, or is a validated exemption", () => {
    const violations: string[] = [];

    for (const abs of pageFiles) {
      const rel = path.relative(APP_DIR, abs).split(path.sep).join("/");
      const source = fs.readFileSync(abs, "utf8");
      const exemption = EXEMPTIONS[rel];

      if (exemption) {
        if (!exemption.validate(source, abs)) {
          violations.push(
            `${rel}: EXEMPTION NO LONGER VALID (${exemption.reason}). ` +
              `Add the 3 GA4 hooks or update EXEMPTIONS in this test.`,
          );
        }
        continue;
      }

      const missing = HOOKS.filter((h) => !source.includes(h));
      if (missing.length > 0) {
        violations.push(`${rel}: missing GA4 hook(s): ${missing.join(", ")}`);
      }
    }

    expect(violations).toEqual([]);
  });

  it("has no stale exemptions (every exempted file still exists)", () => {
    for (const rel of Object.keys(EXEMPTIONS)) {
      const abs = path.join(APP_DIR, rel);
      expect(fs.existsSync(abs)).toBe(true);
    }
  });
});
