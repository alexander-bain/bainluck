/**
 * D96 (#4830, ship 8 / #4462) — Vercel Web Analytics counts EVERY visitor, so
 * it runs before the consent choice and stays out of the consent authority.
 * Alex ruling D96, 2026-09-08.
 *
 * THE SHIP THIS GUARDS. "How many people came to the site this week" is a
 * question about strangers. Behind `TelemetryGate` the answer could not contain
 * one: `decideTelemetry` reads "no choice recorded yet" as a denial — correctly,
 * for the identified rails — and a stranger's first page view is always that.
 * So the dashboard counted people who had already arrived, stayed, found the
 * banner and pressed Accept, and reported it as traffic. Vercel Web Analytics
 * is cookieless (no cookie, no storage read, no cross-site identifier), so
 * there was no consent question being answered by the gate in the first place.
 *
 * This is D30 one provider along, and it is deliberately the same shape of
 * guard as `speedInsightsPreConsent.test.ts` — the two rulings are one rule.
 *
 * WHY A SOURCE-SHAPED GUARD AND NOT A RENDER. `TelemetryGate` is a client
 * component whose decision arrives through `useSyncExternalStore`, and this
 * repo's jest is `testEnvironment: 'node'` with no jsdom: a server render
 * returns `getServerTelemetryDecision()`, which is all-false, so EVERY gated
 * provider is absent from that output whether or not it is gated. A render
 * assertion would therefore be green under both arms — it would pass just as
 * happily on the code this ship replaced. The mount SITE is the claim, so the
 * mount site is what is read.
 *
 * The three things that make it a real guard rather than a spell-check:
 *  1. Comments and import specifiers are stripped before the containment
 *     checks, so the prose in `TelemetryGate` explaining why this provider is
 *     not there cannot satisfy a test looking for its absence — and cannot
 *     break one either.
 *  2. Every parse RAISES when it cannot find what it expects (missing file,
 *     missing import, no JSX tag). A guard whose regex silently misses is a
 *     guard that reports green on a file it never understood.
 *  3. The unconditional-mount check is positional, not textual: the tag must
 *     not sit inside a `&&` or ternary arm. `{x && <Analytics />}` is the exact
 *     regression this exists to catch — it is the literal line D96 removed —
 *     and it contains the same tag text a naive `toContain` would accept.
 *
 * AND ONE MORE, WHICH THE COPY EARNS. Mounting this outside the gate makes the
 * banner's old sentence ("Decline and neither of them loads") false, and the
 * incident this whole subsystem exists for (C90 P1 / #1453) is our banner
 * overstating what the choice did. So the copy is guarded too: the three
 * surfaces that describe the choice must not promise that declining stops
 * Vercel Analytics. That lesson runs in both directions.
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
const BANNER = path.join(FRONTEND, 'components', 'Analytics', 'ConsentBanner.tsx');
const PREFERENCES = path.join(
  FRONTEND,
  'components',
  'Analytics',
  'TelemetryPreferences.tsx',
);
const PRIVACY = path.join(FRONTEND, 'app', 'privacy', 'page.tsx');

/** The package every mount of this provider must come from. */
const PACKAGE = '@vercel/analytics/next';

function read(file: string): string {
  if (!fs.existsSync(file)) {
    throw new Error(
      `vercelAnalyticsPreConsent: ${file} does not exist. This guard reads mount ` +
        `sites and copy by path; a move renames the claim and must be made ` +
        `deliberately.`,
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
 * Whether `code` imports `symbol` from exactly `pkg`. A string equality on the
 * module source, not a regex built from it — see the note in the D30 guard,
 * where interpolating the package name into `new RegExp` was correctly redded
 * by CodeQL as incomplete sanitization.
 */
function importsSymbolFrom(code: string, symbol: string, pkg: string): boolean {
  for (const [, specifiers, source] of code.matchAll(NAMED_IMPORT)) {
    if (source !== pkg) continue;
    const names = specifiers.split(',').map((s) => s.trim().split(/\s+as\s+/)[0].trim());
    if (names.includes(symbol)) return true;
  }
  return false;
}

/**
 * The JSX line a tag renders on, raising if the tag is absent. Absence is never
 * silently a pass here: a rename would make a `toContain` check quietly green
 * on a file that no longer mounts anything.
 *
 * 🔴 The tag is matched WITH its closing punctuation, and that is not
 * tidiness. `<Analytics` is a prefix of `<AnalyticsProvider`, which the root
 * layout also renders — so a bare `indexOf('<Analytics')` finds the PROVIDER
 * first and reports its line. Caught by mutation: deleting the real
 * `<Analytics />` mount left this check green, reading the provider's line and
 * finding no `&&` in it. A guard that matches a prefix is guarding the wrong
 * element.
 */
const TAG_RENDER = /<Analytics\s*\/?>/;

function renderLine(code: string, tag: RegExp, where: string): string {
  const at = code.search(tag);
  if (at === -1) {
    throw new Error(
      `vercelAnalyticsPreConsent: no ${tag.source} tag in ${where}. Either the provider ` +
        `was unmounted (D96 says it must mount) or it was renamed, in which ` +
        `case this guard is reading the wrong name and would go silently ` +
        `green — so it raises instead.`,
    );
  }
  const lineStart = code.lastIndexOf('\n', at) + 1;
  const lineEnd = code.indexOf('\n', at);
  return code.slice(lineStart, lineEnd === -1 ? undefined : lineEnd);
}

describe('Vercel Web Analytics is cookieless and mounts pre-consent (D96)', () => {
  it('the root layout imports it from the real package', () => {
    const code = stripComments(read(LAYOUT));
    // Control: the parser understands this file's imports at all. Without it a
    // regex that silently matched nothing would fail as "no import" and read
    // like a real finding.
    expect(importsSymbolFrom(code, 'TelemetryGate', '@/components/Analytics')).toBe(true);

    expect(importsSymbolFrom(code, 'Analytics', PACKAGE)).toBe(true);
  });

  it('the root layout renders it, and NOT behind a condition', () => {
    const code = stripComments(read(LAYOUT));
    const line = renderLine(code, TAG_RENDER, 'app/layout.tsx');

    expect(line).not.toContain('&&');
    expect(line).not.toContain('?');
    expect(line.trim().startsWith('{')).toBe(false);
    // Positive control: this really is the render line, not an import, and not
    // the `<AnalyticsProvider>` whose opening tag shares this prefix.
    expect(line).toMatch(TAG_RENDER);
    expect(line).not.toContain('AnalyticsProvider');
  });

  it('the consent gate does not mount it — the gate is for gated providers only', () => {
    const code = stripComments(read(GATE));

    // Presence control FIRST: if this file no longer mounts the providers it is
    // supposed to gate, the absence assertions below are trivially true and
    // this whole test means nothing.
    expect(code).toContain('<GoogleAnalytics');
    expect(code).toContain('decision.googleAnalytics');

    expect(code).not.toContain(PACKAGE);
    expect(code).not.toContain('vercelAnalytics');
    // `<Analytics` is a prefix of `<AnalyticsProvider` and of nothing else this
    // file could legitimately render, so the tag is matched with its closing
    // punctuation rather than bare.
    expect(code).not.toMatch(/<Analytics\s*\/?>/);
  });

  it('the consent authority has no vercelAnalytics key — there is no choice to record', () => {
    for (const decision of [
      decideTelemetry(null, { gaConfigured: true }),
      decideTelemetry('none', { gaConfigured: true }),
      decideTelemetry('all', { gaConfigured: true }),
      decideTelemetry('analytics', { gaConfigured: true }),
      getServerTelemetryDecision(),
    ]) {
      // Not `toBeUndefined()`: a key present and set to `false` would read the
      // same way to that matcher, and a present key is exactly what D96
      // forbids — it would imply the banner governs this provider.
      expect(Object.keys(decision)).not.toContain('vercelAnalytics');
      // Control: these are real decision objects, not empty ones.
      expect(Object.keys(decision)).toContain('googleAnalytics');
    }
  });

  it('no reader-facing surface promises that declining stops it (C90 P1, both directions)', () => {
    // Comments are NOT stripped for the banner/preferences files' own JSX prose,
    // because the prose IS the claim under test. They are stripped only where a
    // code comment could accidentally satisfy or break the check — and here the
    // check is on rendered sentences, so what a developer wrote in a `/* */`
    // above them is not what a reader sees. Read the whole file: a promise
    // hidden in a comment is not a promise to a reader, and a promise in JSX is.
    const surfaces: Array<[string, string]> = [
      ['ConsentBanner.tsx', read(BANNER)],
      ['TelemetryPreferences.tsx', read(PREFERENCES)],
      ['app/privacy/page.tsx', read(PRIVACY)],
    ];

    for (const [name, code] of surfaces) {
      // Control: this really is the file that talks about the choice. If a
      // surface stops mentioning analytics at all, that is a change worth
      // failing on rather than passing vacuously.
      expect(code).toMatch(/[Aa]nalytics/);

      // The exact sentences D96 falsified, plus the shapes they would come back
      // as. Each is a claim that a decline covers BOTH providers.
      expect(code).not.toContain('Decline and neither of them loads');
      expect(code).not.toContain('Neither of those loads');
      expect(code).not.toMatch(
        /Vercel (Web )?Analytics[^.]{0,80}\bis\b[^.]{0,40}covered by the analytics choice/,
      );
      expect(code).not.toMatch(
        /Google Analytics and Vercel (Web )?Analytics[^.]{0,60}(load|loads) on this site/,
      );
      // A guard is only as good as its own reachability: prove the matchers
      // above would fire on the text they name, using this same file's content
      // as the negative-control substrate.
      expect(`${name}: Decline and neither of them loads`).toContain(
        'Decline and neither of them loads',
      );
    }
  });
});
