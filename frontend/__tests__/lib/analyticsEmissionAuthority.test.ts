/**
 * L2-220 Item 1 (#1453) — ONE authority for every event.
 *
 * Two failure modes this pins, both of which had shipped and neither of which
 * any existing suite could see:
 *
 *  1. **Direct emission.** `app/discover/stats/page.tsx` called
 *     `window.gtag('event', 'share_scorecard', …)` itself. That bypassed the
 *     consent gate AND the sanitation boundary. It was quiet on a declined
 *     visit only by accident (gtag.js is never loaded, so the global is
 *     absent) — but after a grant→revoke the global still exists, so it kept
 *     emitting an unregistered event with unallowlisted params. The census
 *     below fails the build if any direct emitter comes back.
 *
 *  2. **Taxonomy drift.** `my_stuff_load` was added to `AnalyticsEventMap` and
 *     emitted through `trackEvent`, but never registered in the sanitizer's
 *     name allowlist — so every packet was dropped at the last boundary before
 *     `gtag`. Its own suite mocks `@/lib/analytics` wholesale, so the sanitizer
 *     never ran there. These tests exercise the REAL boundary.
 */

import * as fs from 'fs';
import * as path from 'path';

import { sanitizeEvent, KNOWN_EVENT_NAMES } from '@/lib/analytics/sanitize';

export {};

// ============================================================================
// Repo-wide direct-emission census
// ============================================================================

/**
 * The ONLY files allowed to touch `gtag` directly. Everything else must go
 * through `trackEvent`.
 *
 *  - `lib/analytics/core.ts` is the central transport itself.
 *  - `components/Analytics/GoogleAnalytics.tsx` carries the inline bootstrap
 *    that must define `gtag` and push the `denied` Consent Mode defaults BEFORE
 *    gtag.js processes anything — that ordering cannot be routed through the
 *    transport, because it is what creates it.
 */
const TRANSPORT_FILES = new Set([
  'lib/analytics/core.ts',
  'components/Analytics/GoogleAnalytics.tsx',
]);

const ROOT = path.resolve(__dirname, '..', '..');
const SEARCH_DIRS = ['app', 'components', 'lib', 'hooks'];
const SOURCE_RE = /\.(ts|tsx)$/;

function walk(dir: string, out: string[] = []): string[] {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.next') continue;
      walk(full, out);
    } else if (SOURCE_RE.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

/** A call that actually EMITS through gtag, as opposed to reading/defining it. */
const DIRECT_EMIT_RE = /\bgtag\s*\(\s*['"](?:event|config|consent|set|js)['"]/;

/**
 * Strip line and block comments before scanning. Without this the census
 * flags its own documentation: the code comments explaining what the old
 * `window.gtag('event', …)` call did are, textually, direct emissions.
 * Approximate (it does not parse strings), which is fine — the goal is to
 * avoid prose false-positives, and the vacuous-pass guard below covers the
 * opposite failure mode.
 */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

describe('repo-wide direct-emission census', () => {
  it('no source file outside the central transport calls gtag directly', () => {
    const offenders: string[] = [];

    for (const dir of SEARCH_DIRS) {
      for (const file of walk(path.join(ROOT, dir))) {
        const rel = path.relative(ROOT, file).split(path.sep).join('/');
        if (TRANSPORT_FILES.has(rel)) continue;
        const src = stripComments(fs.readFileSync(file, 'utf8'));
        if (DIRECT_EMIT_RE.test(src)) offenders.push(rel);
      }
    }

    expect(offenders).toEqual([]);
  });

  it('finds the source tree it claims to scan (guards a vacuous pass)', () => {
    // If the walk silently found nothing, the census above would "pass" while
    // checking zero files.
    const files = SEARCH_DIRS.flatMap((d) => walk(path.join(ROOT, d)));
    expect(files.length).toBeGreaterThan(100);
    const rels = files.map((f) => path.relative(ROOT, f).split(path.sep).join('/'));
    expect(rels).toContain('app/discover/stats/page.tsx');
    expect(rels).toContain('lib/analytics/core.ts');
  });

  it('the Discover Stats share goes through trackEvent, not window.gtag', () => {
    const src = stripComments(
      fs.readFileSync(path.join(ROOT, 'app/discover/stats/page.tsx'), 'utf8'),
    );
    expect(src).not.toMatch(/window\.gtag/);
    expect(src).toMatch(/trackEvent\(\s*["']share_scorecard["']/);
  });
});

// ============================================================================
// The taxonomy is complete
// ============================================================================

describe('event-name registry completeness', () => {
  it('registers share_scorecard so the Stats share survives the boundary', () => {
    expect(KNOWN_EVENT_NAMES.has('share_scorecard')).toBe(true);
  });

  it('registers my_stuff_load — it was silently dropped here (L2-217 drift)', () => {
    expect(KNOWN_EVENT_NAMES.has('my_stuff_load')).toBe(true);
  });

  it('every name in the registry is unique and non-empty', () => {
    for (const name of Array.from(KNOWN_EVENT_NAMES)) {
      expect(typeof name).toBe('string');
      expect(name.length).toBeGreaterThan(0);
    }
  });

  it('still drops a genuinely unregistered event', () => {
    expect(sanitizeEvent('share_scorecard_v2', { accuracy_percent: 1 })).toBeNull();
  });
});

// ============================================================================
// share_scorecard — the payload contract
// ============================================================================

describe('share_scorecard sanitation', () => {
  it('keeps the three aggregate fields', () => {
    const out = sanitizeEvent('share_scorecard', {
      accuracy_percent: 61,
      total_questions: 12,
      streak: 3,
    });
    expect(out).not.toBeNull();
    expect(out!.name).toBe('share_scorecard');
    expect(out!.params).toMatchObject({
      accuracy_percent: 61,
      total_questions: 12,
      streak: 3,
    });
  });

  it('strips identity that a future caller might attach', () => {
    const out = sanitizeEvent('share_scorecard', {
      accuracy_percent: 61,
      total_questions: 12,
      streak: 3,
      user_id: 'firebase-abc',
      email: 'a@b.com',
      session_id_raw: 'sess-123',
      url: 'https://bainluck.com/discover/scorecard?accuracy=61',
    } as Record<string, unknown>);
    expect(out!.params).not.toHaveProperty('user_id');
    expect(out!.params).not.toHaveProperty('email');
    expect(out!.params).not.toHaveProperty('session_id_raw');
    expect(out!.params).not.toHaveProperty('url');
  });
});

// ============================================================================
// my_stuff_load — strict-key latency packet
// ============================================================================

const MY_STUFF_PACKET = {
  stage: 'first_render',
  auth_ready_ms: 12,
  network_ms: 210,
  backend_elapsed_ms: 180,
  decode_ms: 4,
  required_data_ready_ms: 230,
  first_render_ms: 260,
  cache_outcome: 'miss',
  cache_age_seconds: -1,
  item_count: 3,
  app_build: '1.4.2 (231)',
  surface: 'my_stuff',
  outcome_class: 'network_success',
};

describe('my_stuff_load sanitation', () => {
  it('survives the boundary with all 13 contract fields intact', () => {
    const out = sanitizeEvent('my_stuff_load', { ...MY_STUFF_PACKET });
    expect(out).not.toBeNull();
    expect(out!.params).toEqual(MY_STUFF_PACKET);
  });

  it('does not let session/user/timestamp enrichment ride along', () => {
    const out = sanitizeEvent('my_stuff_load', {
      ...MY_STUFF_PACKET,
      session_id: '1730000000000',
      platform: 'web',
      event_timestamp: '2026-07-31T00:00:00.000Z',
      user_id: 'firebase-abc',
    } as Record<string, unknown>);
    expect(out!.params).not.toHaveProperty('session_id');
    expect(out!.params).not.toHaveProperty('platform');
    expect(out!.params).not.toHaveProperty('event_timestamp');
    expect(out!.params).not.toHaveProperty('user_id');
  });

  it('preserves the app_build tag verbatim (the digit-redaction trap)', () => {
    // L2-219 caught the native rail rewriting "1.4.2 (231)" as "[number]".
    const out = sanitizeEvent('my_stuff_load', { ...MY_STUFF_PACKET });
    expect(out!.params.app_build).toBe('1.4.2 (231)');
  });
});
