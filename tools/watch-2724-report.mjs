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
// TSV: epoch, http_code, seconds, and since latency/130 a 4th `rc=<curl exit>` column. `000` is a
// request that got no status back, which during a lock convoy is the reader-facing shape and is NOT
// the same outcome as a slow 200.
//
// 🔴 BUT `000` IS A CLAIM ABOUT THE CLIENT, NOT ABOUT PRODUCTION, and this sampler runs behind a
// sandbox egress proxy that fails on its own. That distinction is not academic: the v4037 window
// (2026-09-03) banked six `000` rows and this file printed `🔴 SYMPTOM WITHOUT A MIGRATION — this
// re-opens #2724 in a WIDER form` off them, while the browser arm called the very same stretch a rig
// error, the ring saw zero new slow events, `watch.log` was logging `tunneling socket could not be
// established, statusCode=503`, and the next window came back 21/21 HTTP 200. One arm that cannot
// audit its own egress outvoted two that were clean.
//
// So a `000` only counts as production having parked the request when the row is CONSISTENT WITH
// HAVING REACHED PRODUCTION. Three rows are not, and are attributed to our egress:
//   * curl exited with a transport code (5/6/7/35/45/56/97) — it never got far enough to reach a
//     Heroku router that could have parked anything;
//   * no duration at all (`curl-failed`) — curl emitted no write-out, same argument;
//   * a duration LONGER than curl's own `--max-time` — curl was told to abort at that bound, so the
//     number is not describing a request. v4037 banked 838 s and 337 s rows under `--max-time 60`.
// What survives is rc 28 (timed out waiting on a response) and any `000` inside the timeout bound.
// Same family as gotcha #53: an absent response is a response SHAPE, and needs a second signal.
const MAXT = parseFloat(E.PROBE_MAX_TIME || '60');
const LOCAL_RC = new Set([5, 6, 7, 35, 45, 56, 97]);
let probe = { n: 0, ok: 0, slow: 0, parked: 0, egress: 0, throttled: 0, worst: 0, gapS: 0, worstAt: null };
const probeLines = [];
try {
  const raw = readFileSync(E.PROBE_PATH || `${OUT}/probe.tsv`, 'utf8').trim().split('\n').filter(Boolean);
  let prevT = null;
  for (const ln of raw) {
    const [t, code, secs, rcCol] = ln.split('\t');
    const ts = parseInt(t, 10); const sec = parseFloat(secs);
    const rc = rcCol && /^rc=(\d+)$/.test(rcCol) ? parseInt(rcCol.slice(3), 10) : null;
    if (!isFinite(ts)) continue;
    probe.n++;
    if (code === '200') probe.ok++;
    if (code === '429') probe.throttled++;
    let why = '';
    if (code === '000' || !isFinite(sec)) {
      // Windows banked before the rc column exists have rc === null; they are still classified, just
      // on the two duration tests alone. A pre-rc window must not silently grade as clean.
      const isEgress = (rc !== null && LOCAL_RC.has(rc)) || !isFinite(sec) || sec > MAXT;
      if (isEgress) { probe.egress++; why = ' ← OUR EGRESS, not production'; }
      else { probe.parked++; why = ' ← no response inside the timeout — production'; }
    } else {
      if (sec >= 5) probe.slow++;
      if (sec > probe.worst) { probe.worst = sec; probe.worstAt = ts; }
    }
    // A gap much larger than the probe cadence means the PREVIOUS request was parked long enough to
    // swallow whole cycles — the prober's own timeline is evidence, not just its rows. Gaps that sit
    // against an egress-attributed row say nothing about the site, so they are tracked separately.
    if (prevT !== null) probe.gapS = Math.max(probe.gapS, ts - prevT);
    prevT = ts;
    if (code !== '200' || sec >= 5) probeLines.push(`  - ${new Date(ts * 1000).toISOString()} HTTP ${code} ${isFinite(sec) ? sec.toFixed(1) + ' s' : secs}${rc !== null ? ` (curl rc=${rc})` : ''}${why}`);
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
// `probe.parked` here is the FILTERED count — rows our own egress cannot explain. `probe.egress` is
// deliberately absent from this boolean: a proxy that dropped our socket is not a symptom, and letting
// it flip the verdict is exactly how v4037 printed a re-open on a window the site sailed through.
// A `000` that survived the egress filter is still only ONE arm's word, and the filter is not perfect:
// it cannot classify a row banked before the `rc=` column existed, and a proxy that drops a socket at
// 27 s is indistinguishable, from the row alone, from production parking one. So a symptom that ONLY
// the prober saw, in a window where the prober is DEMONSTRABLY unreliable (it also banked egress
// failures), is unresolved — the two arms that can audit themselves both came back clean. That is a
// held signal, not a re-open. v4037: 1 surviving `000` at 27.5 s, six seconds from a `curl-failed`,
// against 0 reader-visible blanks and 0 new ring events. It printed a re-open.
const proberOnly = probe.parked > 0 && realBlanks === 0 && releasedTogether.length === 0;
const proberUnresolved = proberOnly && probe.egress > 0;
const symptomFree = realBlanks === 0 && releasedTogether.length === 0
  && (probe.parked === 0 || proberUnresolved);
const noEvidence = runs === 0 && probe.n === 0;
// A window whose prober was mostly talking to a broken proxy did not measure the pipeline half at all.
// Clean-looking is then a blind spot, not a result, and the report has to say which one it is.
const probeBlind = probe.n > 0 && probe.egress > probe.ok;
// CLOSES is the one verdict in this file that ends an investigation, so it takes a stricter gate than
// the rest: `symptomFree` tolerates an unresolved prober row, and closing #2724 must not. A window
// that could not measure the pipeline half cleanly can hold the issue open; it can never shut it.
const closeable = symptomFree && !proberUnresolved && !probeBlind;
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
  verdict = closeable
    ? 'CLOSES #2724 — a migration-carrying release LANDED and neither symptom appeared'
    : symptomFree
      ? '#2724 STAYS OPEN — a migration-carrying release landed and no reader was hurt, but the prober could not clear itself in this window, so this is not the clean verdict window. Wait for the next migration'
      : '🔴 RE-OPENS #2724 — the symptom survived a migration-carrying release that landed';
  headline = `release v${VER} landed a migration — this is the verdict window`;
}
// Both downgrades below attach to the verdict LINE, not to a footnote, because the verdict line is
// the part that gets quoted by someone who was asleep.
if (symptomFree && proberUnresolved) {
  verdict = `${verdict} — ⚠️ ONE UNRESOLVED PROBER SIGNAL: ${probe.parked} sample(s) returned no status inside the timeout, but this window ALSO banked ${probe.egress} egress failure(s), so that row cannot be separated from them. No reader-visible blank and no new ring event corroborate it. HELD, not re-opened`;
}
// A clean read earned by a prober that spent the window arguing with our own proxy is not a clean
// read.
if (symptomFree && probeBlind) {
  verdict = `${verdict} — ⚠️ BUT THE PROBER WAS BLIND: ${probe.egress} of ${probe.n} samples failed in OUR egress (more than the ${probe.ok} that reached the site), so the pipeline half of this window was not measured`;
}

const probeBlock = probe.n === 0
  ? '🔴 **The prober banked nothing.** Its silence is a rig failure, not a clean pipeline — do not read the window as quiet.'
  : [
    `- samples: **${probe.n}** over the window (${E.PROBE_PATH ? E.PROBE_PATH.replace(/^.*\//, '') : 'probe.tsv'})`,
    `- HTTP 200: **${probe.ok}** · 429 (our own budget): **${probe.throttled}** · parked by production: **${probe.parked}** · failed in OUR egress: **${probe.egress}**`,
    `- slowest completed request: **${probe.worst.toFixed(1)} s**${probe.worstAt ? ` at ${new Date(probe.worstAt * 1000).toISOString()}` : ''}`,
    `- largest gap between samples: **${probe.gapS} s** (cadence is ${E.PROBE_S || 6} s; a big gap means a request was parked through whole cycles — or that our own proxy sat on one)`,
    probe.egress
      ? `- ⚠️ **${probe.egress} sample(s) never reached the site.** A status-\`000\` is a claim about this client, not about production: it is attributed to our egress when curl exits with a transport code, emits no duration, or reports one longer than its own \`--max-time ${MAXT}\` s. Those rows do NOT drive the verdict.${probeBlind ? ' More samples failed here than succeeded — **the pipeline half of this window is unmeasured, not clean.**' : ''}`
      : '- every sample that failed to return did so at the site, not in our egress',
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
