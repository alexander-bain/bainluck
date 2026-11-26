/**
 * Ruling 241: A guard for `frontend/__tests__/timing_quarantine.json`.
 *
 * Enforces the same contract as `backend/tests/test_timing_quarantine_241a.py`:
 * every quarantined frontend timing test names a real open issue, a 7-day
 * expiry window, and an existing file under `frontend/__tests__/`.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import {
  findActiveTimingQuarantineEntry,
  isValidActiveTimingQuarantineEntry,
  MAX_TIMING_QUARANTINE_DAYS,
  normalizeRepoPath,
  parseIsoDateUtc,
  runQuarantinedTimingBody,
  TIMING_QUARANTINE_FILE,
  utcTodayIso,
} from '../helpers/timingQuarantine';

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');

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

  it('forgives in blocking mode, warns clearly, and fails strictly when CI_QUARANTINE_MODE=canary or expired', async () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'fe-quarantine-run-'));
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

      await expect(
        runQuarantinedTimingBody(
          f,
          name,
          () => {
            throw new Error('Expected 780 < 500');
          },
          {
            filePath: qFile,
            todayIso: '2026-11-26',
            mode: '',
            warn: (msg) => warnings.push(msg),
          },
        ),
      ).resolves.toBeUndefined();

      expect(warnings).toHaveLength(1);
      expect(warnings[0]).toContain('#13810');
      expect(warnings[0]).toContain('2026-12-02');

      await expect(
        runQuarantinedTimingBody(
          f,
          name,
          () => {
            throw new Error('Expected 780 < 500');
          },
          {
            filePath: qFile,
            todayIso: '2026-11-26',
            mode: 'canary',
          },
        ),
      ).rejects.toThrow('Expected 780 < 500');

      await expect(
        runQuarantinedTimingBody(
          f,
          name,
          () => {
            throw new Error('Expected 780 < 500');
          },
          {
            filePath: qFile,
            todayIso: '2026-12-03',
            mode: '',
          },
        ),
      ).rejects.toThrow('Expected 780 < 500');

      expect(isValidActiveTimingQuarantineEntry({ testFile: 'frontend/app/foo.tsx' }, '2026-11-26')).toBe(false);
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });
});
