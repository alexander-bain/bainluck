/**
 * LAT-P204 (#2508) — the analytics barrel is on the blocking entry path, and
 * `import` is not `render`.
 *
 * THE SHIP THIS GUARDS. Discover's first card cannot be drawn until the entry
 * JavaScript has arrived over a saturated pipe (LAT-P203: not the feed fetch,
 * not the CPU — the download). Two things were putting code on that path that
 * no cold visitor can ever run:
 *
 *  1. `components/Analytics/index.ts` re-exported six symbols, and sixteen
 *     modules import `useAnalyticsContext` from it. A barrel is imported whole,
 *     so `TelemetryPreferences` — renderable only on `/preferences` — and the
 *     consent banner and the gtag.js wrapper rode into the entry chunk of every
 *     route behind one React hook.
 *  2. `TelemetryGate` mounted its three gated providers conditionally but
 *     imported them STATICALLY. Enforcement by absence was true of the beacon
 *     and false of the bytes: a visitor who declined still downloaded all three.
 *
 * WHY A SOURCE-SHAPED GUARD. Same reason as `speedInsightsPreConsent.test.ts`:
 * this repo's jest is `testEnvironment: 'node'`, and the claim here is about
 * the MODULE GRAPH, which a render cannot observe at all. A render assertion
 * would be equally green on the code this replaced.
 *
 * WHAT MAKES IT A GUARD AND NOT A SPELL-CHECK:
 *  - every parse RAISES when it finds nothing, so a regex that stops matching
 *    reds instead of going silently green (gotcha: a scan must raise on what it
 *    cannot parse);
 *  - each absence assertion is paired with a presence CONTROL in the same file,
 *    so "no static import of X" cannot pass because the import parser broke;
 *  - the barrel check compares against real call sites read off disk, not
 *    against a hand-maintained list that would drift.
 */

import fs from 'fs';
import path from 'path';

const FRONTEND = path.join(__dirname, '..', '..');
const BARREL = path.join(FRONTEND, 'components', 'Analytics', 'index.ts');
const GATE = path.join(FRONTEND, 'components', 'Analytics', 'TelemetryGate.tsx');

/** Directories that can contribute to a route's client entry graph. */
const SOURCE_ROOTS = ['app', 'components', 'hooks', 'lib'];
const SOURCE_EXT = new Set(['.ts', '.tsx']);

function read(file: string): string {
  if (!fs.existsSync(file)) {
    throw new Error(
      `analyticsBarrelEntryCost: ${file} does not exist. This guard reads module ` +
        `graph shape by path; a move renames the claim and must be deliberate.`,
    );
  }
  return fs.readFileSync(file, 'utf8');
}

/** Strip comments so prose explaining an absence cannot satisfy — or break — it. */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (SOURCE_EXT.has(path.extname(entry.name))) out.push(full);
  }
  return out;
}

/** Symbols this barrel re-exports, e.g. `export { A, B as C } from './x'`. */
function barrelExports(code: string): string[] {
  const names: string[] = [];
  for (const [, specifiers] of code.matchAll(/export\s*\{([^}]*)\}\s*from\s*['"][^'"]+['"]/g)) {
    for (const raw of specifiers.split(',')) {
      const spec = raw.trim();
      if (!spec) continue;
      // `default as WebVitalsReporter` / `A as B` — the EXPORTED name is the right half.
      const parts = spec.split(/\s+as\s+/);
      names.push(parts[parts.length - 1].trim());
    }
  }
  return names;
}

/** Every symbol any file imports THROUGH the barrel specifier. */
function symbolsImportedThroughBarrel(files: string[]): Map<string, string[]> {
  const seen = new Map<string, string[]>();
  const NAMED_IMPORT = /import\s*(?:type\s*)?\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g;
  for (const file of files) {
    const code = stripComments(fs.readFileSync(file, 'utf8'));
    for (const [, specifiers, source] of code.matchAll(NAMED_IMPORT)) {
      if (source !== '@/components/Analytics') continue;
      for (const raw of specifiers.split(',')) {
        const spec = raw.trim();
        if (!spec) continue;
        const name = spec.split(/\s+as\s+/)[0].trim();
        const at = seen.get(name) || [];
        at.push(path.relative(FRONTEND, file));
        seen.set(name, at);
      }
    }
  }
  return seen;
}

/** Static (top-level) module specifiers of a file — NOT `import(...)` calls. */
function staticImportSources(code: string): string[] {
  const sources: string[] = [];
  for (const [, source] of code.matchAll(/^\s*import\s[^;]*?from\s*['"]([^'"]+)['"]/gm)) {
    sources.push(source);
  }
  // Bare side-effect imports: `import 'x';`
  for (const [, source] of code.matchAll(/^\s*import\s*['"]([^'"]+)['"]\s*;?\s*$/gm)) {
    sources.push(source);
  }
  return sources;
}

/** Module specifiers reached by a `dynamic(() => import('x'))` call. */
function dynamicImportSources(code: string): string[] {
  const sources: string[] = [];
  for (const [, source] of code.matchAll(/import\(\s*['"]([^'"]+)['"]\s*\)/g)) {
    sources.push(source);
  }
  return sources;
}

/**
 * Each `dynamic(...)` call as source text, delimited by BALANCED parentheses.
 *
 * Not a regex. The first draft used `/dynamic\([\s\S]*?\}\s*\)/g`, which is
 * lazy up to the first `}` followed by `)` — with three calls in the file that
 * swallowed all three into one match and reported "parsed 1". A guard that
 * miscounts the thing it is counting is worse than no guard, so the nesting is
 * walked rather than guessed.
 */
function dynamicCallSlices(code: string): string[] {
  const slices: string[] = [];
  const NEEDLE = 'dynamic(';
  for (let at = code.indexOf(NEEDLE); at !== -1; at = code.indexOf(NEEDLE, at + 1)) {
    // `foo.dynamic(` / `myDynamic(` are not this call.
    if (at > 0 && /[\w$.]/.test(code[at - 1])) continue;
    let depth = 0;
    for (let i = at + NEEDLE.length - 1; i < code.length; i++) {
      if (code[i] === '(') depth++;
      else if (code[i] === ')') {
        depth--;
        if (depth === 0) {
          slices.push(code.slice(at, i + 1));
          break;
        }
      }
    }
  }
  return slices;
}

// ============================================================================
// 1. The barrel re-exports only what someone reaches through it
// ============================================================================

describe('the analytics barrel carries nothing a caller does not ask it for', () => {
  const exported = barrelExports(stripComments(read(BARREL)));
  const files = SOURCE_ROOTS.flatMap((d) => walk(path.join(FRONTEND, d)));
  const imported = symbolsImportedThroughBarrel(files);

  it('the parsers found something to reason about', () => {
    // Both halves RAISE rather than assert, because a silent zero on either
    // side makes the real check below trivially true.
    if (exported.length === 0) {
      throw new Error(
        'analyticsBarrelEntryCost: parsed ZERO re-exports out of ' +
          'components/Analytics/index.ts. Either the file changed shape or this ' +
          'guard no longer understands it; it must not report green either way.',
      );
    }
    if (imported.size === 0) {
      throw new Error(
        'analyticsBarrelEntryCost: found ZERO imports from "@/components/Analytics" ' +
          `across ${files.length} source files. The specifier changed, or the scan is ` +
          'reading the wrong tree.',
      );
    }
    // Positive control on both parsers at once: the hot symbol is on both sides.
    expect(exported).toContain('useAnalyticsContext');
    expect([...imported.keys()]).toContain('useAnalyticsContext');
  });

  it('every re-exported symbol has a caller that imports it from the barrel', () => {
    const orphans = exported.filter((name) => !imported.has(name));
    expect(orphans).toEqual([]);
  });

  it('the components only ONE page mounts are not re-exported here', () => {
    // These three each have exactly one mount site, and each of those sites
    // imports the module directly. Re-exporting any of them puts it back into
    // the entry chunk of all sixteen `useAnalyticsContext` callers.
    for (const name of ['TelemetryPreferences', 'GoogleAnalytics', 'WebVitalsReporter']) {
      expect(exported).not.toContain(name);
    }
    // Control: the assertion above is not passing on an empty export list.
    expect(exported.length).toBeGreaterThan(0);
  });
});

// ============================================================================
// 2. The gated providers are imported lazily, not statically
// ============================================================================

describe('a declined visitor does not download the rails they declined', () => {
  const code = stripComments(read(GATE));
  const statics = staticImportSources(code);
  const dynamics = dynamicImportSources(code);

  /** module specifier -> the decision key that permits it */
  const GATED: Array<[string, string]> = [
    ['@vercel/analytics/next', 'decision.vercelAnalytics'],
    ['./GoogleAnalytics', 'decision.googleAnalytics'],
    ['./WebVitalsReporter', 'decision.webVitals'],
  ];

  /**
   * CONTROL — and deliberately the only assertion in this describe that is
   * green under BOTH arms.
   *
   * `@/lib/analytics` is a static import of this file before and after the
   * split, so if it is missing the parser is broken rather than the code. Run
   * against the pre-split tree this test passes while all six below fail,
   * which is what makes those six a detector and not a tautology. An earlier
   * draft also asserted `next/dynamic` here; that is arm-dependent — it is part
   * of the CLAIM, not a control — so it now lives with the claim.
   */
  it('the static-import parser works on this file', () => {
    if (statics.length === 0) {
      throw new Error(
        'analyticsBarrelEntryCost: parsed ZERO static imports out of ' +
          'TelemetryGate.tsx. The absence checks below would be vacuous.',
      );
    }
    expect(statics).toContain('@/lib/analytics');
  });

  it('the gate reaches its providers through next/dynamic at all', () => {
    if (dynamics.length === 0) {
      throw new Error(
        'analyticsBarrelEntryCost: parsed ZERO dynamic import() calls out of ' +
          'TelemetryGate.tsx. The gate is expected to lazily import every gated ' +
          'provider; finding none means either the split was reverted or this ' +
          'guard cannot read it.',
      );
    }
    expect(statics).toContain('next/dynamic');
  });

  it.each(GATED)('%s is lazy, not static', (specifier) => {
    expect(statics).not.toContain(specifier);
    expect(dynamics).toContain(specifier);
  });

  it('each lazy provider is still rendered behind its consent decision', () => {
    // The split must not have quietly turned a gated mount into an
    // unconditional one — that would be a consent regression wearing a
    // performance fix's clothes.
    for (const [, key] of GATED) {
      expect(code).toContain(key);
    }
    // And each decision key must still guard a JSX mount, not merely appear.
    for (const [, key] of GATED) {
      expect(code).toMatch(new RegExp(`\\{\\s*${key.replace('.', '\\.')}\\s*&&\\s*<`));
    }
  });

  it('the split is ssr:false — these were never in the server render anyway', () => {
    // `getServerTelemetryDecision()` is all-false, so no gated provider has ever
    // been part of the server output. Saying so in the option keeps the client
    // bundle from carrying a server variant nothing can reach.
    const dynamicCalls = dynamicCallSlices(code);
    if (dynamicCalls.length !== GATED.length) {
      throw new Error(
        `analyticsBarrelEntryCost: expected ${GATED.length} dynamic() calls in ` +
          `TelemetryGate.tsx, parsed ${dynamicCalls.length}.`,
      );
    }
    for (const call of dynamicCalls) expect(call).toContain('ssr: false');
  });
});
