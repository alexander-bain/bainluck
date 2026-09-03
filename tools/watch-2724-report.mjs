// watch-2724-report.mjs — renders the runner-inbox directive that settles or re-opens #2724.
//
// Split out of watch-migration-deploy.sh so it can be RUN against last night's real burst data
// before the watcher is armed. A reporting step that has only ever executed inside an unattended
// watcher, on a condition that happens once, is a step nobody has tested.
//
// env: MIGS CUR LAST OUT WORK REPORT_PATH
import { readFileSync, writeFileSync } from 'fs';

const { MIGS, CUR, LAST, OUT, WORK, REPORT_PATH } = process.env;
const SURFACES = ['discover', 'sports', 'usopen', 'event'];
const rd = (p) => { try { return JSON.parse(readFileSync(p, 'utf8')); } catch { return null; } };

const rows = [];
const blanks = [];
let runs = 0, valid = 0;
for (const s of SURFACES) {
  const j = rd(`${OUT}/cold-${s}.json`);
  if (!j) { rows.push(`| ${s} | **RIG FAILED — no JSON** | | | | |`); continue; }
  runs += j.summary.runs; valid += j.summary.valid;
  // §4b of LAT-P216: a run with first=NONE is a BLANK only if the page really was empty. `pct` and
  // `bodyChars` off the same run separate "the reader saw nothing" (pct=0, bodyChars ~700) from "the
  // detector was blind" (percentages on screen, thousands of characters). Ten false blanks nearly
  // went into the #2724 verdict once; an unattended report must not be able to repeat that.
  for (const r of j.results.filter((r) => !r.valid)) {
    const pct = r.proof ? r.proof.pct : null;
    const bc = r.bodyChars ?? r.proof?.bodyChars ?? null;
    const verdict = r.error ? 'RIG ERROR — not a reader-visible blank'
      : pct === 0 ? 'REAL BLANK — the reader saw nothing'
      : 'SUSPECT DETECTOR-BLIND — page had content; do NOT count until checked';
    blanks.push(`${s} run ${r.run}: pct=${pct} bodyChars=${bc}${r.error ? ` err=${r.error}` : ''} → **${verdict}**`);
  }
  const S = j.summary;
  // `?.` on every stat on purpose: this file must render a report from whatever the rig wrote,
  // including an older rig with no `hero` block. An unattended report that throws leaves the inbox
  // holding the fallback stub and the 40 loads unread.
  const n = (x) => (x == null ? '—' : Math.round(x));
  rows.push(`| ${s} | ${S.valid}/${S.runs} | ${S.runs - S.valid} | ${n(S.shell?.p50)} | ${n(S.first?.p50)} | ${n(S.first?.p95)} | ${n(S.hero?.p50)} |`);
}

const ringAfter = rd(process.env.RING_PATH || `${WORK}/ring-after-${CUR}.json`) || {};
const ev = ringAfter.events || [];
const since = Date.now() / 1000 - 3600;
const fresh = ev.filter((e) => e.t >= since);
const convoy = fresh.filter((e) => e.ms >= 100000);
// The convoy signature is not "a slow event" — it is several long requests FINISHING TOGETHER,
// released when whatever held the lock let go. Cluster on completion time, one-second buckets.
const buckets = new Map();
for (const e of convoy) {
  const k = Math.floor(e.t);
  buckets.set(k, (buckets.get(k) || 0) + 1);
}
const releasedTogether = [...buckets.entries()].filter(([, n]) => n >= 2);

const realBlanks = blanks.filter((b) => b.includes('REAL BLANK')).length;
const STUCK = !!process.env.REPORT_STUCK;
const verdict = STUCK
  ? (realBlanks === 0 && releasedTogether.length === 0
    ? 'READERS ARE FINE, THE PIPELINE IS NOT — the migration cannot land, and the lock_timeout is keeping the cost off readers'
    : 'RE-OPENS #2724 — the migration cannot land AND readers are paying for it')
  : (realBlanks === 0 && releasedTogether.length === 0
    ? 'CLOSES #2724 — the fix was exercised and neither symptom appeared'
    : 'RE-OPENS #2724 — the symptom survived a migration-carrying deploy');

const heading = STUCK
  ? `# latency/129 — a migration-carrying deploy is STUCK: production is still \`${CUR}\`, master is \`${LAST}\``
  : `# latency/129 — #2724 is settled by \`${CUR}\`, the first migration-carrying deploy`;

const preamble = STUCK
  ? `Written unattended by \`tools/watch-migration-deploy.sh\`. The deploy this watcher was armed for
arrived and **the deployed commit never changed** — the release command failed, so \`/api/health\` still
reports the old sha. That shape is invisible to a commit-change watcher and to CI, whose own \`deploy\`
job reports success when the Heroku release phase is what failed.

**Machine read: ${verdict}.** The prose below is what that read is made of; check it before quoting it.

**The pending range:** production \`${CUR}\` → master \`${LAST}\`, carrying:
\`\`\`
${MIGS}
\`\`\`
The watcher has NOT exited: the eventual successful release is still the verdict #2724 is waiting for.
Check \`releases-stuck-${CUR}.txt\` beside the raw runs for the Heroku release list, and
\`pg_stat_activity\` for a long \`idle in transaction\` session — an \`ACCESS EXCLUSIVE\` cannot jump one.`
  : `Written unattended by \`tools/watch-migration-deploy.sh\`. Nobody re-measured #2724 by hand, which is
the point: the verdict had to wait for a condition no session could schedule.

**Machine read: ${verdict}.** The prose below is what that read is made of; check it before quoting it.

**The deploy:** \`${LAST}\` → \`${CUR}\`, carrying:
\`\`\`
${MIGS}
\`\`\`
This is the condition LAT-P216 could not test. The 790 release carried no migration, so its clean
40/40 was a negative control over an unexercised path. Here the \`lock_timeout\` armed on the
migration's connection actually ran.`;

writeFileSync(REPORT_PATH, `${heading}

${preamble}

## 40 cold loads ${STUCK ? 'while the release was failing' : 'across the deploy window'}

| surface | valid | blank | shell p50 | first p50 | first p95 | hero p50 |
|---|---:|---:|---:|---:|---:|---:|
${rows.join('\n')}

**Total ${valid}/${runs} valid, ${runs - valid} invalid, of which ${realBlanks} are real reader-visible blanks.**

${blanks.length ? 'Every invalid run, with the blank-vs-blind test applied:\n' + blanks.map((b) => `- ${b}`).join('\n') : 'No invalid runs.'}

## The slow-event ring

One global Redis list, not a per-worker ring (LAT-P216 §3) — one read sees production. Capped at 500
entries, so its span collapses on a busy day; that is a bound, not a topology.

- events in the last hour: **${fresh.length}**
- of those ≥100 s: **${convoy.length}**
- ≥100 s events finishing in the same second (the convoy signature): **${releasedTogether.length} cluster(s)**
${convoy.slice(0, 10).map((e) => `  - ${new Date(e.t * 1000).toISOString()} ${e.path} ${Math.round(e.ms / 1000)} s (db ${Math.round((e.db_ms || 0) / 1000)} s)`).join('\n')}

## How to finish the verdict

Closing #2724 also needs the release log checked for \`assert_migrations_applied.py\`, because the
Procfile still swallows Alembic failures via \`|| echo\` (#2741): a migration that silently did not
apply produces the same clean loads as a migration that applied safely, and only the release log
tells them apart. Do that read before closing.

Raw: \`${OUT}/\`, \`${process.env.RING_PATH || `${WORK}/ring-after-${CUR}.json`}\`${STUCK ? `, \`${WORK}/releases-stuck-${CUR}.txt\`` : `, \`${WORK}/ring-at-${CUR}.json\``}.
`);
console.log(`wrote ${REPORT_PATH}`);
