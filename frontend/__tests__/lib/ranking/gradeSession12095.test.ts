/** #12095 Phase 2 — the /grade page's pure helpers. */

import { GRADES, formatTally, normalizeGraderName } from '@/lib/ranking/gradeSession';

describe('gradeSession', () => {
  it('offers exactly the three grades the scorecard scores', () => {
    expect([...GRADES]).toEqual(['shareable', 'interesting', 'neither']);
  });

  it('normalizes a grader name', () => {
    expect(normalizeGraderName('  Daphne   B ')).toBe('Daphne B');
    expect(normalizeGraderName('   ')).toBe('');
    expect(normalizeGraderName('x'.repeat(60))).toHaveLength(40);
  });

  it('prints the family tally, skipping anyone at zero', () => {
    expect(
      formatTally([
        { grader: 'Alex', kid: false, today: 10 },
        { grader: 'Dexter', kid: true, today: 10 },
        { grader: 'Daphne', kid: true, today: 7 },
        { grader: 'Nobody', kid: false, today: 0 },
      ]),
    ).toBe('Alex 10 · Dexter 10 · Daphne 7 today');
    expect(formatTally([])).toBe('');
  });
});
