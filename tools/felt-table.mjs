// felt-table.mjs — turn the felt-load artifacts into the table Alex reads.
//
// Seconds, not milliseconds: the target is written in seconds ("under 3 s cold,
// under 1 s warm") and a table in milliseconds makes the reader do the division
// before they can tell whether a row passes.
//
// INVALID RUNS ARE COUNTED, NEVER AVERAGED. A run where no real card ever
// appeared is excluded from p50/p95 — averaging it in is impossible anyway,
// there is no number — but it is reported in its own column, because "1 in 5
// visits showed nothing" is the most important thing the table can say and it
// would otherwise be invisible behind a healthy median.
import { readFileSync, existsSync } from 'fs';

const DIR = process.argv[2] || '/tmp/felt-2026-09-02';
const SURFACES = process.argv[3]
  ? process.argv[3].split(',')
  : ['discover', 'sports', 'usopen', 'search', 'event', 'politics', 'calibration', 'profile'];
const CONDITIONS = ['cold', 'warm', 'slow4g'];

const s = (ms) => (ms == null ? '—' : (ms / 1000).toFixed(2));

const rows = [];
for (const cond of CONDITIONS) {
  for (const surf of SURFACES) {
    const path = `${DIR}/${cond}-${surf}.json`;
    if (!existsSync(path)) continue;
    const d = JSON.parse(readFileSync(path, 'utf8'));
    const results = d.results || [];
    const blank = results.filter((r) => !r.valid).length;
    rows.push({
      cond,
      surface: surf,
      how: (results.find((r) => r.how) || {}).how || '—',
      runs: results.length,
      blank,
      shell: d.summary.shell,
      first: d.summary.first,
      fold: d.summary.fold,
      foldCards: d.summary.medianFoldCards,
    });
  }
}

const header = [
  '| condition | surface | how | n | blank runs | shell p50 | **first card p50** | **first card p95** | worst | fold p50 | cards above fold |',
  '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|',
];
const body = rows.map((r) =>
  `| ${r.cond} | ${r.surface} | ${r.how} | ${r.runs} | ${r.blank ? `🔴 ${r.blank}` : '0'} | ${s(r.shell.p50)} | **${s(r.first.p50)}** | **${s(r.first.p95)}** | ${s(r.first.worst)} | ${s(r.fold.p50)} | ${r.foldCards ?? '—'} |`,
);
console.log([...header, ...body].join('\n'));

// The worst row first, which is the standing instruction for what to ship next.
const cold = rows.filter((r) => r.cond === 'cold');
const ranked = [...cold].sort((a, b) => (b.first.p95 ?? 0) - (a.first.p95 ?? 0) || b.blank - a.blank);
console.log('\nWORST COLD ROWS BY p95 (ship this order):');
for (const r of ranked) {
  console.log(`  ${r.surface.padEnd(12)} p50=${s(r.first.p50)}s p95=${s(r.first.p95)}s blank=${r.blank}/${r.runs}`);
}
