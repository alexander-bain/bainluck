// watch-2724-report.mjs — renders the runner-inbox directive that settles or re-opens #2724.
//
// Split out of the watcher so it can be RUN against banked data before the watcher is armed. A
// reporting step that has only ever executed inside an unattended watcher, on a condition that
// happens once, is a step nobody has tested. `bash tools/watch-release-window.sh` with
// WATCH_SELFTEST=1 does exactly that and writes nothing to the inbox.
//
// REWRITTEN FOR THE RELEASE-WINDOW SHAPE (LAT-P218). The old renderer described "the deploy that
// changed the sha", which is the one shape that could not be the interesting one — see the header of
// `watch-release-window.sh`. It now describes A RELEASE WINDOW, which exists whether or not the
// release landed, and it reads three independent sources rather than one:
//
//   the browser loads   — what a reader saw            (blank / throttled / fine)
//   the HTTP prober     — whether requests were parked (the pipeline half, 6 s resolution)
//   the slow-event ring — the convoy signature         (≥100 s requests finishing in one second)
//
// env: OUT WORK REPORT_PATH MIGS CUR LAST RELEASE_VERSION RELEASE_STATUS RELEASE_CREATED WINDOW_S
//      RING_BEFORE RING_PATH PROBE_PATH RELEASE_OUTPUT QUEUE
import { readFileSync, writeFileSync, readdirSync, existsSync } from 'fs';

const E = process.env;
const { MIGS, CUR, LAST, OUT, REPORT_PATH } = E;
const QUEUE = E.QUEUE || '130';
const VER = E.RELEASE_VERSION || '?';
const STATUS = E.RELEASE_STATUS || 'unknown';
const rd = (p) => { try { return JSON.parse(readFileSync(p, 'utf8')); } catch { return null; } };
const n = (x) => (x == null ? '—' : Math.round(x));

const hasMigration = !!(MIGS && MIGS.trim() && !MIGS.startsWith('UNKNOWN'));
const migUnknown = !!(MIGS && MIGS.startsWith('UNKNOWN'));

// ── THE BROWSER LOADS ──────────────────────────────────────────────────────────────────────────────
// One JSON per load, `load-NNN-<surface>.json`. The old bursts wrote `cold-<surface>.json` with many
// runs inside; both are read, because a report that cannot render yesterday's banked data cannot be
// tested against it.
const files = existsSync(OUT || '') ? readdirSync(OUT).filter((f) => /^(load-\d+-|cold-).*\.json$/.test(f)) : [];
const bySurface = new Map();
const blanks = [];
let runs = 0, valid = 0, throttled = 0;

for (const f of files.sort()) {
  const j = rd(`${OUT}/${f}`);
  if (!j || !j.summary) continue;
  const s = j.summary.surface || f;
  if (!bySurface.has(s)) bySurface.set(s, []);
  for (const r of j.results || []) {
    bySurface.get(s).push(r);
    runs++;
    // 🔴 THREE OUTCOMES, NOT TWO. `valid` means the detector found real content. A run can also be
    // SELF-THROTTLED — the battery spending its own 60/min budget and rendering `Rate limit exceeded`,
    // which has pct=0 and ~673 body chars and is therefore identical to a blank page in every other
    // column. #2783 was filed off exactly that confusion. A throttled run is neither a pass nor a
    // regression; it is the instrument, and it is counted on its own line.
    if (r.throttled) { throttled++; continue; }
    if (r.valid) { valid++; continue; }
    const pct = r.proof ? r.proof.pct : null;
    const bc = r.bodyChars ?? r.proof?.bodyChars ?? null;
    // §4b of LAT-P216: `pct` and `bodyChars` off the same run separate "the reader saw nothing" from
    // "the detector was blind". Ten false blanks nearly went into the #2724 verdict once; an
    // unattended report must not be able to repeat that.
    // 🔴 THE LEGACY BAND (LAT-P218). Runs banked before the status column existed carry no `api429`
    // and no `rateLimitText`, so for them "pct=0" alone cannot separate an empty render from the app
    // rendering `Rate limit exceeded: 60/minute`. That error page measures ~673 body chars and #2783
    // recorded 682; a run in that band with a page TITLE (so the document rendered) is the error page's
    // signature, not an empty one. Calling it a REAL BLANK would re-open #2724 on the battery's own
    // throttling — the single most expensive mistake this instrument can make, unattended, at 4am.
    const legacy = r.api429 === undefined && r.proof?.rateLimitText === undefined;
    const errorPageBand = legacy && pct === 0 && bc >= 550 && bc <= 900;
    const verdict = r.error ? 'RIG ERROR — not a reader-visible blank'
      : r.proof?.rateLimitText || r.api429 > 0 ? 'SELF-THROTTLED — the page rendered our own 429'
      : errorPageBand ? `SUSPECT SELF-THROTTLED — ${bc} body chars with a rendered title is the "Rate limit exceeded" page's signature (~673), not an empty render. Banked as UNPROVEN: this run predates the status column`
      : pct === 0 ? 'REAL BLANK — the reader saw nothing'
      : 'SUSPECT DETECTOR-BLIND — page had content; do NOT count until checked';
    blanks.push(`${s} ${f}: pct=${pct} bodyChars=${bc} api=${r.apiCount ?? '?'}${r.api429 ? ` 429×${r.api429}` : ''}${r.error ? ` err=${r.error}` : ''} → **${verdict}**`);
  }
}
const realBlanks = blanks.filter((b) => b.includes('REAL BLANK')).length;

const pctl = (xs, p) => {
  const s = xs.filter((x) => typeof x === 'number' && isFinite(x)).sort((a, b) => a - b);
  if (!s.length) return null;
  return s[Math.max(0, Math.min(s.length - 1, Math.ceil((p / 100) * s.length) - 1))];
};
const rows = [];
for (const [s, rs] of [...bySurface.entries()].sort()) {
  const ok = rs.filter((r) => r.valid && !r.throttled);
  const thr = rs.filter((r) => r.throttled).length;
  const bl = rs.filter((r) => !r.valid && !r.throttled).length;
  rows.push(`| ${s} | ${ok.length}/${rs.length} | ${bl} | ${thr} | ${n(pctl(ok.map((r) => r.shell), 50))} | ${n(pctl(ok.map((r) => r.first), 50))} | ${n(pctl(ok.map((r) => r.first), 95))} | ${n(pctl(ok.map((r) => r.hero), 50))} |`);
}
if (!rows.length) rows.push('| — | **NO BROWSER LOAD COMPLETED IN THIS WINDOW** | | | | | | |');

// ── THE PROBER ─────────────────────────────────────────────────────────────────────────────────────
// TSV: epoch, http_code, seconds. `000` is a request that never completed, which during a lock convoy
// is the reader-facing shape and is NOT the same outcome as a slow 200.
let probe = { n: 0, ok: 0, slow: 0, parked: 0, throttled: 0, worst: 0, gapS: 0, worstAt: null };
const probeLines = [];
try {
  const raw = readFileSync(E.PROBE_PATH || `${OUT}/probe.tsv`, 'utf8').trim().split('\n').filter(Boolean);
  let prevT = null;
  for (const ln of raw) {
    const [t, code, secs] = ln.split('\t');
    const ts = parseInt(t, 10); const sec = parseFloat(secs);
    if (!isFinite(ts)) continue;
    probe.n++;
    if (code === '200') probe.ok++;
    if (code === '429') probe.throttled++;
    if (code === '000' || !isFinite(sec)) probe.parked++;
    else {
      if (sec >= 5) probe.slow++;
      if (sec > probe.worst) { probe.worst = sec; probe.worstAt = ts; }
    }
    // A gap much larger than the probe cadence means the PREVIOUS request was parked long enough to
    // swallow whole cycles — the prober's own timeline is evidence, not just its rows.
    if (prevT !== null) probe.gapS = Math.max(probe.gapS, ts - prevT);
    prevT = ts;
    if (code !== '200' || sec >= 5) probeLines.push(`  - ${new Date(ts * 1000).toISOString()} HTTP ${code} ${isFinite(sec) ? sec.toFixed(1) + ' s' : secs}`);
  }
} catch { /* no probe file — reported as such below, never as a clean probe */ }

// ── THE RING ───────────────────────────────────────────────────────────────────────────────────────
// One global Redis list, not a per-worker ring (LAT-P216 §3) — one read sees production. Capped at 500
// entries, so its span collapses on a busy day; that is a bound, not a topology.
const ringAfter = rd(E.RING_PATH || `${OUT}/ring-after.json`) || {};
const ringBefore = rd(E.RING_BEFORE || `${OUT}/ring-before.json`) || {};
const evAfter = ringAfter.events || [];
const beforeKeys = new Set((ringBefore.events || []).map((e) => `${e.t}|${e.path}|${e.ms}`));
// NEW events only. The ring holds 500 entries and most of them predate this window; counting them all
// would report yesterday's incident as tonight's.
const fresh = evAfter.filter((e) => !beforeKeys.has(`${e.t}|${e.path}|${e.ms}`));
const convoy = fresh.filter((e) => e.ms >= 100000);
// The convoy signature is not "a slow event" — it is several long requests FINISHING TOGETHER,
// released when whatever held the lock let go. Cluster on completion time, one-second buckets.
const buckets = new Map();
for (const e of convoy) buckets.set(Math.floor(e.t), (buckets.get(Math.floor(e.t)) || 0) + 1);
const releasedTogether = [...buckets.entries()].filter(([, c]) => c >= 2);

// ── DID THE MIGRATION ACTUALLY APPLY ───────────────────────────────────────────────────────────────
// The Procfile still swallows Alembic failures via `|| echo` (#2741), so a migration that silently did
// not apply produces the same clean loads as one that applied safely. `assert_migrations_applied.py`
// is the only thing that can tell them apart and it speaks only in the release log.
// These are the assertion's own words, not a guess at them:
//   backend/scripts/assert_migrations_applied.py:98   "OK: database is at Alembic head (...)"
//   backend/scripts/assert_migrations_applied.py:102  "RELEASE FAILED: the database is NOT at Alembic head."
//   backend/Procfile                                  "Alembic upgrade skipped — may have multiple heads"
// Matching on the script's FILENAME instead would report every healthy release as suspicious, because
// the Procfile invokes it and the log only ever carries its output.
let applied = 'NOT CHECKED — no release output banked, and silence is not a pass';
try {
  const out = readFileSync(E.RELEASE_OUTPUT || `${OUT}/release-output.txt`, 'utf8');
  const unreadable = /^NO RELEASE OUTPUT BANKED/.test(out.trim());
  const atHead = /OK: database is at Alembic head/.test(out);
  const declaredFail = /RELEASE FAILED: the database is NOT at Alembic head/.test(out);
  const swallowed = /Alembic upgrade skipped/.test(out);
  const lockSig = /DeadlockDetected|LockNotAvailable|canceling statement|lock timeout|could not obtain lock/i.test(out);
  applied = unreadable ? `🔴 release output could not be fetched — read it by hand: \`heroku releases:output ${VER} -a bainluck\``
    : declaredFail ? '🔴 `RELEASE FAILED: the database is NOT at Alembic head` — the migration did not apply'
    : lockSig ? '🔴 the release log carries a LOCK signature — this is the #2724 mechanism, read the log before quoting any number here'
    : swallowed && atHead ? '⚠️ `alembic upgrade` was skipped by the Procfile `|| echo` (#2741), but the assertion still found the DB at head'
    : atHead ? '✅ `OK: database is at Alembic head` — the assertion ran and passed'
    : '🔴 the release log carries NEITHER the assertion\'s pass nor its fail line — the release phase did not reach it';
} catch { /* keep the NOT CHECKED default — silence is never a pass */ }
// A release with no migration cannot fail to apply one; saying otherwise puts a permanent red in
// every negative-control report and trains the reader to ignore the column.
if (!hasMigration && !migUnknown) applied = `n/a — no migration in this release (${applied.replace(/^[^ ]+ /, '')})`;

// ── THE VERDICT ────────────────────────────────────────────────────────────────────────────────────
// Stated as a machine read with its inputs beside it, because it is written unattended and will be
// quoted by someone who was asleep.
const symptomFree = realBlanks === 0 && releasedTogether.length === 0 && probe.parked === 0;
const noEvidence = runs === 0 && probe.n === 0;
let verdict, headline;
if (noEvidence) {
  verdict = 'NO VERDICT — the window was sampled but nothing was banked (rig failure, not a clean run)';
  headline = `the v${VER} window banked NO SAMPLES`;
} else if (migUnknown) {
  verdict = `NO VERDICT ON #2724 — could not tell whether v${VER} carried a migration (${MIGS})`;
  headline = `release v${VER} (${STATUS}) sampled, migration content UNKNOWN`;
} else if (!hasMigration) {
  verdict = symptomFree
    ? 'NEGATIVE CONTROL — no migration in this release, so the fix was not exercised. Clean is expected and proves nothing about #2724'
    : '🔴 SYMPTOM WITHOUT A MIGRATION — this re-opens #2724 in a WIDER form: something other than the migration lock is doing it';
  headline = `release v${VER} (${STATUS}) carried no migration — negative control`;
} else if (STATUS !== 'succeeded') {
  verdict = symptomFree
    ? 'READERS ARE FINE, THE PIPELINE IS NOT — the migration could not land, and the armed `lock_timeout` kept the cost off readers. #2724 stays open until one LANDS'
    : '🔴 RE-OPENS #2724 — the migration could not land AND readers paid for it';
  headline = `release v${VER} carried a migration and ${STATUS.toUpperCase()}`;
} else {
  verdict = symptomFree
    ? 'CLOSES #2724 — a migration-carrying release LANDED and neither symptom appeared'
    : '🔴 RE-OPENS #2724 — the symptom survived a migration-carrying release that landed';
  headline = `release v${VER} landed a migration — this is the verdict window`;
}

const probeBlock = probe.n === 0
  ? '🔴 **The prober banked nothing.** Its silence is a rig failure, not a clean pipeline — do not read the window as quiet.'
  : [
    `- samples: **${probe.n}** over the window (${E.PROBE_PATH ? E.PROBE_PATH.replace(/^.*\//, '') : 'probe.tsv'})`,
    `- HTTP 200: **${probe.ok}** · 429 (our own budget): **${probe.throttled}** · never completed: **${probe.parked}**`,
    `- slowest completed request: **${probe.worst.toFixed(1)} s**${probe.worstAt ? ` at ${new Date(probe.worstAt * 1000).toISOString()}` : ''}`,
    `- largest gap between samples: **${probe.gapS} s** (cadence is ${E.PROBE_S || 6} s; a big gap means a request was parked through whole cycles)`,
    probeLines.length ? 'Every non-200 or ≥5 s sample:\n' + probeLines.slice(0, 25).join('\n') : '- every sample was a fast 200',
  ].join('\n');

writeFileSync(REPORT_PATH, `# latency/${QUEUE} — ${headline}

Written unattended by \`tools/watch-release-window.sh\`, which fires on **release START** rather than on
the deployed sha changing. That matters here and nowhere else: a sha-change watcher can only ever
sample the release that succeeded, and succeeding is correlated with the table being free, so the old
instrument was structurally blind to the deploys that hurt readers most.

**Machine read: ${verdict}.**
The three sections below are what that read is made of. Check them before quoting it.

| | |
|---|---|
| release | **v${VER}** — \`${CUR}\`, status **${STATUS}**, created ${E.RELEASE_CREATED || '?'} |
| previous | \`${LAST}\` |
| window sampled | **${E.WINDOW_S || '?'} s** (release phase + tail) |
| alembic files in \`${LAST}..${CUR}\` | ${hasMigration ? '\n\n```\n' + MIGS + '\n```\n' : migUnknown ? `**${MIGS}**` : '**none — negative control**'} |
| did it apply | ${applied} |

## 1. What a reader saw — ${runs} cold browser loads through the window

| surface | valid | blank | self-throttled | shell p50 | first p50 | first p95 | hero p50 |
|---|---:|---:|---:|---:|---:|---:|---:|
${rows.join('\n')}

**${valid}/${runs} valid, ${realBlanks} real reader-visible blanks, ${throttled} runs excluded as self-throttled.**

${blanks.length ? 'Every non-valid run, with the blank-vs-blind-vs-throttled test applied:\n' + blanks.map((b) => `- ${b}`).join('\n') : 'No non-valid runs.'}

## 2. Was the API parked — the HTTP prober

${probeBlock}

## 3. The convoy signature — the slow-event ring

Compared against a ring read taken BEFORE the release, so only events new to this window are counted.

- new slow events in this window: **${fresh.length}**
- of those ≥100 s: **${convoy.length}**
- ≥100 s events finishing in the same second (the convoy signature): **${releasedTogether.length} cluster(s)**
${convoy.slice(0, 10).map((e) => `  - ${new Date(e.t * 1000).toISOString()} ${e.path} ${Math.round(e.ms / 1000)} s (db ${Math.round((e.db_ms || 0) / 1000)} s)`).join('\n') || '  - none'}

## What is still owed before anyone closes #2724

- Read \`release-output.txt\` yourself. The Procfile swallows Alembic failures via \`|| echo\` (#2741),
  so a migration that silently did not apply looks exactly like one that applied safely.
- A clean window on a release with **no** migration is a negative control and closes nothing.
- ${hasMigration && STATUS === 'succeeded' ? 'This window IS the exercised path. If §1-§3 are clean, #2724 can be closed on it.' : 'This is not yet the exercised-and-landed path. The watcher is still armed for it.'}

Raw: \`${OUT}/\` — one JSON per browser load, \`probe.tsv\`, \`ring-before.json\`, \`ring-after.json\`,
\`releases.txt\`, \`release-output.txt\`.
`);
console.log(`wrote ${REPORT_PATH}`);
