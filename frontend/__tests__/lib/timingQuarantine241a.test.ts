/**
 * Ruling 241: A guard for `frontend/__tests__/timing_quarantine.json`.
 *
 * Enforces the same contract as `backend/tests/test_timing_quarantine_241a.py`:
 * every quarantined frontend timing check names a real open issue, a 7-day
 * expiry window, and an existing test under `frontend/__tests__/`, while
 * leaving surrounding behavioral assertions strictly blocking.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import {
  assertTimingBudgetMs,
  findActiveTimingQuarantineEntry,
  isValidActiveTimingQuarantineEntry,
  MAX_TIMING_QUARANTINE_DAYS,
  normalizeRepoPath,
  parseIsoDateUtc,
  TIMING_QUARANTINE_FILE,
  utcTodayIso,
} from '../helpers/timingQuarantine';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const SET_PAGES_FILE = 'frontend/__tests__/lib/setPagesLiveReprice10090.test.tsx';
const SET_PAGES_TEST =
  'CollectionHub machinery section (market_preview) and AwardCategoryPairedCard (server invalidation) re-price in < 500 ms';

describe('Ruling 241: A — frontend timing_quarantine.json contract', () => {
  it('shipped quarantine entries are valid, unique, reference an issue, and sit within 7 days', () => {
    expect(fs.existsSync(TIMING_QUARANTINE_FILE)).toBe(true);
    const parsed: unknown = JSON.parse(fs.readFileSync(TIMING_QUARANTINE_FILE, 'utf8'));
    expect(Array.isArray(parsed)).toBe(true);

    const entries = parsed as Record<string, unknown>[];
    const todayIso = utcTodayIso();
    const todayDate = parseIsoDateUtc(todayIso)!;
    const seen = new Set<string>();

    for (const entry of entries) {
      expect(typeof entry.testFile).toBe('string');
      const normFile = normalizeRepoPath(String(entry.testFile));
      expect(normFile.startsWith('frontend/__tests__/')).toBe(true);
      expect(fs.existsSync(path.join(REPO_ROOT, normFile))).toBe(true);

      expect(typeof entry.testName).toBe('string');
      expect(String(entry.testName).trim().length).toBeGreaterThan(0);

      const source = fs.readFileSync(path.join(REPO_ROOT, normFile), 'utf8');
      expect(source).toContain(String(entry.testName));

      const key = `${normFile}::${String(entry.testName)}`;
      expect(seen.has(key)).toBe(false);
      seen.add(key);

      expect(typeof entry.issue).toBe('number');
      expect(Number.isInteger(entry.issue)).toBe(true);
      expect(Number(entry.issue)).toBeGreaterThan(0);

      const addedDate = parseIsoDateUtc(entry.added);
      const expiresDate = parseIsoDateUtc(entry.expires);
      expect(addedDate).not.toBeNull();
      expect(expiresDate).not.toBeNull();

      const spanDays = Math.round((expiresDate!.getTime() - addedDate!.getTime()) / 86_400_000);
      expect(spanDays).toBeGreaterThanOrEqual(0);
      expect(spanDays).toBeLessThanOrEqual(MAX_TIMING_QUARANTINE_DAYS);
      expect(todayDate.getTime()).toBeLessThanOrEqual(expiresDate!.getTime());

      expect(typeof entry.reason).toBe('string');
      expect(String(entry.reason).trim().length).toBeGreaterThan(0);
    }
  });

  it('activates only up to expiry and rejects windows longer than 7 days or missing issues', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'fe-quarantine-'));
    const qFile = path.join(tmpDir, 'timing_quarantine.json');
    try {
      const f = 'frontend/__tests__/lib/example.test.tsx';
      fs.writeFileSync(
        qFile,
        JSON.stringify([
          {
            testFile: f,
            testName: 'active test',
            issue: 13810,
            added: '2026-11-25',
            expires: '2026-12-02',
            reason: 'Ruling 241: A',
          },
          {
            testFile: f,
            testName: 'eight day window',
            issue: 13810,
            added: '2026-11-25',
            expires: '2026-12-03',
            reason: '8-day window must be refused',
          },
          {
            testFile: f,
            testName: 'zero issue',
            issue: 0,
            added: '2026-11-25',
            expires: '2026-12-01',
            reason: 'missing real issue',
          },
        ]),
        'utf8',
      );

      expect(findActiveTimingQuarantineEntry(f, 'active test', { filePath: qFile, todayIso: '2026-11-26' })).not.toBeNull();
      expect(findActiveTimingQuarantineEntry(f, 'active test', { filePath: qFile, todayIso: '2026-12-02' })).not.toBeNull();
      expect(findActiveTimingQuarantineEntry(f, 'active test', { filePath: qFile, todayIso: '2026-12-03' })).toBeNull();
      expect(findActiveTimingQuarantineEntry(f, 'eight day window', { filePath: qFile, todayIso: '2026-11-26' })).toBeNull();
      expect(findActiveTimingQuarantineEntry(f, 'zero issue', { filePath: qFile, todayIso: '2026-11-26' })).toBeNull();
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it('forgives only the timing bar in blocking mode and fails strictly in canary or past expiry', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'fe-quarantine-bar-'));
    const qFile = path.join(tmpDir, 'timing_quarantine.json');
    const f = 'frontend/__tests__/lib/example.test.tsx';
    const name = 'timing budget test';
    const warnings: string[] = [];

    try {
      fs.writeFileSync(
        qFile,
        JSON.stringify([
          {
            testFile: f,
            testName: name,
            issue: 13810,
            added: '2026-11-25',
            expires: '2026-12-02',
            reason: 'Ruling 241: A',
          },
        ]),
        'utf8',
      );

      expect(() =>
        assertTimingBudgetMs(f, name, 780, 500, {
          filePath: qFile,
          todayIso: '2026-11-26',
          mode: '',
          warn: (msg) => warnings.push(msg),
        }),
      ).not.toThrow();

      expect(warnings).toHaveLength(1);
      expect(warnings[0]).toContain('#13810');
      expect(warnings[0]).toContain('780.00 ms >= 500 ms');
      expect(warnings[0]).toContain('2026-12-02');

      expect(() =>
        assertTimingBudgetMs(f, name, 780, 500, {
          filePath: qFile,
          todayIso: '2026-11-26',
          mode: 'canary',
        }),
      ).toThrow();

      expect(() =>
        assertTimingBudgetMs(f, name, 780, 500, {
          filePath: qFile,
          todayIso: '2026-12-03',
          mode: '',
        }),
      ).toThrow();

      expect(isValidActiveTimingQuarantineEntry({ testFile: 'frontend/app/foo.tsx' }, '2026-11-26')).toBe(false);
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it('keeps setPagesLiveReprice10090 behavioral assertions blocking while the timing bar entry is active', () => {
    const warnings: string[] = [];
    // Shipped entry is active today and forgives an overrun on the timing bar alone in blocking mode.
    expect(() =>
      assertTimingBudgetMs(SET_PAGES_FILE, SET_PAGES_TEST, 780, 500, {
        mode: '',
        warn: (msg) => warnings.push(msg),
      }),
    ).not.toThrow();
    expect(warnings).toHaveLength(1);

    // The test itself remains an ordinary `test(...)` calling assertTimingBudgetMs only at the timing bars,
    // so a broken number in that test still fails normally with the entry active.
    const src = fs.readFileSync(path.join(REPO_ROOT, SET_PAGES_FILE), 'utf8');
    expect(src).toContain(`test('${SET_PAGES_TEST}'`);
    expect(src).toContain("expect(container.textContent).toContain('49%')");
    expect(src).toContain('expect(pairedMetricsMock).toHaveBeenCalledTimes(2)');
    expect(src).not.toContain('quarantinedTimingTest');
    expect(() => {
      assertTimingBudgetMs(SET_PAGES_FILE, SET_PAGES_TEST, 780, 500, { mode: '', warn: () => {} });
      expect('48%').toContain('49%');
    }).toThrow();
  });
});
