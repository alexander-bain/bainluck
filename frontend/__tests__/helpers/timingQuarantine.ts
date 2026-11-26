/**
 * Ruling 241: A — frontend tests-only timing quarantine (`frontend/__tests__/timing_quarantine.json`).
 *
 * Mirrors `backend/tests/conftest.py`'s `timing_quarantined_tests`: when a wall-clock
 * timing budget assertion fails on master, passes on re-run, and was untouched by the
 * batch, only that timing budget check is moved to the non-blocking set for <= 7 days
 * with an open issue. Surrounding functional/behavioral assertions remain strictly blocking.
 *
 * When `CI_QUARANTINE_MODE=canary`, or once `expires` has passed, or if the entry is
 * malformed, the timing budget check asserts strictly. Otherwise an overrun logs a warning
 * without reddening blocking `npm run test:ci`.
 */
import * as fs from 'fs';
import * as path from 'path';

export const MAX_TIMING_QUARANTINE_DAYS = 7;
export const TIMING_QUARANTINE_FILE = path.resolve(__dirname, '..', 'timing_quarantine.json');

export interface TimingQuarantineEntry {
  testFile: string;
  testName: string;
  issue: number;
  added: string;
  expires: string;
  reason: string;
}

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Parse strict YYYY-MM-DD string into UTC midnight Date, or null if invalid. */
export function parseIsoDateUtc(raw: unknown): Date | null {
  if (typeof raw !== 'string' || !ISO_DATE_RE.test(raw)) return null;
  const parsed = new Date(`${raw}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return null;
  if (parsed.toISOString().slice(0, 10) !== raw) return null;
  return parsed;
}

/** Return today's UTC date string (YYYY-MM-DD). */
export function utcTodayIso(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

/** Normalize repo-relative path separators to POSIX forward slashes. */
export function normalizeRepoPath(p: string): string {
  return p.replace(/\\/g, '/').replace(/^\.\//, '');
}

/** Return true iff an entry is structurally valid, <= 7 days, and unexpired on `today`. */
export function isValidActiveTimingQuarantineEntry(
  entry: unknown,
  todayIso: string = utcTodayIso(),
): entry is TimingQuarantineEntry {
  if (!entry || typeof entry !== 'object') return false;
  const candidate = entry as Record<string, unknown>;
  const { testFile, testName, issue, added, expires, reason } = candidate;
  if (typeof testFile !== 'string' || !normalizeRepoPath(testFile).startsWith('frontend/__tests__/')) {
    return false;
  }
  if (typeof testName !== 'string' || testName.trim() === '') return false;
  if (typeof issue !== 'number' || !Number.isInteger(issue) || issue <= 0) return false;
  if (typeof reason !== 'string' || reason.trim() === '') return false;

  const addedDate = parseIsoDateUtc(added);
  const expiresDate = parseIsoDateUtc(expires);
  const todayDate = parseIsoDateUtc(todayIso);
  if (!addedDate || !expiresDate || !todayDate) return false;

  const spanDays = Math.round((expiresDate.getTime() - addedDate.getTime()) / 86_400_000);
  if (spanDays < 0 || spanDays > MAX_TIMING_QUARANTINE_DAYS) return false;
  return todayDate.getTime() <= expiresDate.getTime();
}

/** Read and return raw JSON entries from `filePath`, failing closed to `[]` on read/parse error. */
export function loadTimingQuarantineEntries(filePath: string = TIMING_QUARANTINE_FILE): unknown[] {
  try {
    if (!fs.existsSync(filePath)) return [];
    const parsed: unknown = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** Look up an active quarantine entry matching `(testFile, testName)` for `todayIso`. */
export function findActiveTimingQuarantineEntry(
  testFile: string,
  testName: string,
  options?: { filePath?: string; todayIso?: string },
): TimingQuarantineEntry | null {
  const normFile = normalizeRepoPath(testFile);
  const todayIso = options?.todayIso ?? utcTodayIso();
  const entries = loadTimingQuarantineEntries(options?.filePath ?? TIMING_QUARANTINE_FILE);
  for (const raw of entries) {
    if (!isValidActiveTimingQuarantineEntry(raw, todayIso)) continue;
    if (normalizeRepoPath(raw.testFile) === normFile && raw.testName === testName) {
      return raw;
    }
  }
  return null;
}

/**
 * Assert only a wall-clock timing budget (`elapsedMs < budgetMs`).
 *
 * When an active quarantine entry exists in `timing_quarantine.json` and
 * `CI_QUARANTINE_MODE` is not `canary`, an overrun warns instead of failing so
 * surrounding behavioral assertions in the test stay strictly blocking.
 */
export function assertTimingBudgetMs(
  testFile: string,
  testName: string,
  elapsedMs: number,
  budgetMs: number,
  options?: {
    filePath?: string;
    todayIso?: string;
    mode?: string;
    warn?: (message: string) => void;
  },
): void {
  if (elapsedMs < budgetMs) {
    expect(elapsedMs).toBeLessThan(budgetMs);
    return;
  }

  const mode = (options?.mode ?? process.env.CI_QUARANTINE_MODE ?? '').trim().toLowerCase();
  const entry = findActiveTimingQuarantineEntry(testFile, testName, {
    filePath: options?.filePath,
    todayIso: options?.todayIso,
  });

  if (mode !== 'canary' && entry !== null) {
    const warnFn = options?.warn ?? console.warn;
    warnFn(
      `[timing-quarantine #${entry.issue}] non-blocking timing miss in ` +
        `${testFile} :: ${testName} (${elapsedMs.toFixed(2)} ms >= ${budgetMs} ms, expires ${entry.expires})`,
    );
    return;
  }

  expect(elapsedMs).toBeLessThan(budgetMs);
}
