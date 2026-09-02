/**
 * LAT-P197 (#1453 follow-on) — Speed Insights runs BEFORE the consent choice,
 * and stays out of the consent authority. Alex ruling D30, 2026-09-01.
 *
 * THE SHIP THIS GUARDS. Page-speed numbers describe every visitor, not the
 * subset who answered a banner. L2-219 put `<SpeedInsights />` behind
 * `TelemetryGate` along with GA and Vercel Analytics, which was right for the
 * identified rails and wrong for this one: it sets no cookie, reads no storage
 * and carries no identifier, so there is no consent question to ask — and
 * gating it silently re-sampled our own latency work onto the opted-in
 * population. D30 mounts it unconditionally in `app/layout.tsx`.
 *
 * WHY A SOURCE-SHAPED GUARD AND NOT A RENDER. `TelemetryGate` is a client
 * component whose decision arrives through `useSyncExternalStore`, and this
 * repo's jest is `testEnvironment: 'node'` with no jsdom: a server render
 * returns `getServerTelemetryDecision()`, which is all-false, so EVERY gated
 * provider is absent from that output whether or not it is gated. A render
 * assertion would therefore be green under both arms — it would pass just as
 * happily on the code this queue replaced. The mount SITE is the claim, so the
 * mount site is what is read.
 *
 * The three things that make it a real guard rather than a spell-check:
 *  1. Comments and import specifiers are stripped before the containment
 *     checks, so the prose above `TelemetryGate` explaining why Speed Insights
 *     is not there cannot satisfy a test looking for its absence — and cannot
 *     break one either.
 *  2. Every parse RAISES when it cannot find what it expects (missing file,
 *     missing import, no JSX tag). A guard whose regex silently misses is a
 *     guard that reports green on a file it never understood.
 *  3. The unconditional-mount check is positional, not textual: the tag must
 *     not sit inside a `&&` or ternary arm. `{x && <SpeedInsights />}` is the
 *     exact regression this exists to catch, and it contains the same tag text
 *     a naive `toContain` would accept.
 */

import fs from 'fs';
import path from 'path';

import {
  decideTelemetry,
  getServerTelemetryDecision,
} from '@/lib/analytics/telemetryConsent';

const FRONTEND = path.join(__dirname, '..', '..');
const LAYOUT = path.join(FRONTEND, 'app', 'layout.tsx');
const GATE = path.join(FRONTEND, 'components', 'Analytics', 'TelemetryGate.tsx');

/** The package every mount of this provider must come from. */
const PACKAGE = '@vercel/speed-insights/next';
const TAG = '<SpeedInsights';

function read(file: string): string {
  if (!fs.existsSync(file)) {
    throw new Error(
      `speedInsightsPreConsent: ${file} does not exist. This guard reads mount ` +
        `sites by path; a move renames the claim and must be made deliberately.`,
    );
  }
  return fs.readFileSync(file, 'utf8');
}

/**
 * Strip `//` and block comments. Deliberately conservative — it is only ever
 * used to make an ABSENCE check honest, and over-stripping can only make the
 * absence easier to satisfy for text we would then also fail to find in the
 * presence checks, which raise.
 */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

/** Every named-import statement in a module, as `{ symbols, source }`. */
const NAMED_IMPORT = /import\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]/g;

/**
 * Whether `code` imports `symbol` from exactly `pkg`.
 *
 * Deliberately NOT a regex built from `pkg`. The first draft interpolated the
 * package name into a `new RegExp(...)` and hand-escaped it, and CodeQL was
 * right to red it (`js/incomplete-sanitization`, high): that escape missed
 * backslashes, so the pattern a caller got was not the pattern they wrote.
 * Harmless with today's constant, and the wrong shape to leave in a guard —
 * matching a module source is a STRING EQUALITY question, so it is asked as
 * one, and there is nothing left to escape.
 */
function importsSymbolFrom(code: string, symbol: string, pkg: string): boolean {
  for (const [, specifiers, source] of code.matchAll(NAMED_IMPORT)) {
    if (source !== pkg) continue;
    const names = specifiers.split(',').map((s) => s.trim().split(/\s+as\s+/)[0].trim());
    if (names.includes(symbol)) return true;
  }
  return false;
}

describe('Speed Insights is strictly-necessary and mounts pre-consent (D30)', () => {
  it('the root layout imports it from the real package', () => {
    const code = stripComments(read(LAYOUT));
    // Control: the parser understands this file's imports at all. Without it a
    // regex that silently matched nothing would fail as "no import" and read
    // like a real finding.
    expect(importsSymbolFrom(code, 'TelemetryGate', '@/components/Analytics')).toBe(true);

    expect(importsSymbolFrom(code, 'SpeedInsights', PACKAGE)).toBe(true);
  });

  it('the root layout renders it, and NOT behind a condition', () => {
    const code = stripComments(read(LAYOUT));

    const at = code.indexOf(TAG);
    if (at === -1) {
      throw new Error(
        `speedInsightsPreConsent: no ${TAG} tag in app/layout.tsx. Either the ` +
          `provider was unmounted (D30 says it must mount) or it was renamed, ` +
          `in which case this guard is reading the wrong name and would go ` +
          `silently green — so it raises instead.`,
      );
    }

    // The JSX expression container the tag sits in, if any. An unconditional
    // mount is written bare — `<SpeedInsights />` as a sibling element — so it
    // has no enclosing `{ ... }` on its own line at all.
    const lineStart = code.lastIndexOf('\n', at) + 1;
    const lineEnd = code.indexOf('\n', at);
    const line = code.slice(lineStart, lineEnd === -1 ? undefined : lineEnd);

    expect(line).not.toContain('&&');
    expect(line).not.toContain('?');
    expect(line.trim().startsWith('{')).toBe(false);
    // Positive control: this really is the render line, not an import.
    expect(line).toContain(TAG);
  });

  it('the consent gate does not mount it — the gate is for gated providers only', () => {
    const code = stripComments(read(GATE));

    // Presence control FIRST: if this file no longer mounts the providers it is
    // supposed to gate, the absence assertions below are trivially true and
    // this whole test means nothing.
    expect(code).toContain('<Analytics');
    expect(code).toContain('decision.vercelAnalytics');

    expect(code).not.toContain(PACKAGE);
    expect(code).not.toContain(TAG);
    expect(code).not.toContain('speedInsights');
  });

  it('the consent authority has no speedInsights key — there is no choice to record', () => {
    for (const decision of [
      decideTelemetry(null, { gaConfigured: true }),
      decideTelemetry('none', { gaConfigured: true }),
      decideTelemetry('all', { gaConfigured: true }),
      decideTelemetry('analytics', { gaConfigured: true }),
      getServerTelemetryDecision(),
    ]) {
      // Not `toBeUndefined()`: a key present and set to `false` would read the
      // same way to that matcher, and a present key is exactly what D30
      // forbids — it would imply the banner governs this provider.
      expect(Object.keys(decision)).not.toContain('speedInsights');
      // Control: these are real decision objects, not empty ones.
      expect(Object.keys(decision)).toContain('vercelAnalytics');
    }
  });
});
