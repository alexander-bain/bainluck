#!/usr/bin/env node
'use strict';

// L2-234 — the one place that turns `tsc --noEmit` output into a comparable
// number. Three callers depend on it agreeing with itself:
//
//   npm run typecheck            --run --check           the developer + the CI gate
//   npm run typecheck:baseline   --run --write-baseline  refresh the recorded debt
//   frontend-lockfile.yml        --delta                 what a types package bought
//
// WHY A BASELINE AND NOT A CLEAN GATE
//
// `npm run build` has never enforced TypeScript: `next.config.mjs` sets
// `typescript.ignoreBuildErrors: true` (gotcha #10), so type errors have been
// able to deploy green for the life of the project. As of L2-234 there are 89
// of them — see typecheck-baseline.json for the inventory and the owner.
//
// Making `tsc --noEmit` blocking today would red every push until all 89 are
// cleared, and the predictable outcome of a step that reds every push is that
// somebody adds `|| true` to it. So the contract is narrower and actually
// holdable: the existing debt is counted, written down, owned, and frozen —
// and one error more than that fails the build.
//
// The ratchet turns in BOTH directions on purpose. Fixing errors without
// lowering the baseline also fails, with instructions, because a baseline above
// the real count is headroom that new debt can be added into without the gate
// ever noticing.

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const FRONTEND = path.resolve(__dirname, '..');
const BASELINE = path.join(FRONTEND, 'typecheck-baseline.json');

// tsc emits `path(line,col): error TSxxxx: message`, then indents any
// elaboration onto following lines. Only the anchored form is an error; the
// continuation lines must not be counted or the census inflates on messages
// that happen to be verbose.
const ERROR_RE =
  /^(?<file>[^\s(].*?)\((?<line>\d+),(?<col>\d+)\): error (?<code>TS\d+): (?<msg>.*)$/;

function parse(text) {
  const byFile = Object.create(null);
  const byCode = Object.create(null);
  let total = 0;
  for (const raw of text.split('\n')) {
    const m = ERROR_RE.exec(raw.replace(/\r$/, ''));
    if (!m) continue;
    byFile[m.groups.file] = (byFile[m.groups.file] || 0) + 1;
    byCode[m.groups.code] = (byCode[m.groups.code] || 0) + 1;
    total += 1;
  }
  return { total, byFile: sortObject(byFile), byCode: sortObject(byCode) };
}

function sortObject(o) {
  const out = {};
  for (const k of Object.keys(o).sort()) out[k] = o[k];
  return out;
}

function readCensus(p) {
  const j = JSON.parse(fs.readFileSync(p, 'utf8'));
  if (typeof j.total !== 'number' || !j.byFile) {
    throw new Error(`${p} is not a census file`);
  }
  return j;
}

const fmtDelta = (n) => (n > 0 ? `+${n}` : String(n));

/**
 * Run tsc and return its combined output.
 *
 * `--incremental false` overrides tsconfig's `incremental: true`: a run that
 * consults a stale tsbuildinfo is not a measurement, and the file is written
 * into the repo where a developer's build state would leak into the gate.
 *
 * tsc is resolved through `require.resolve` rather than `npx`, so the version
 * checked is the one in this lockfile and the command cannot silently fall back
 * to a globally installed compiler.
 */
function runTsc() {
  let tsc;
  try {
    tsc = require.resolve('typescript/bin/tsc', { paths: [FRONTEND] });
  } catch {
    console.error('typescript is not installed — run `npm ci` in frontend/ first.');
    process.exit(2);
  }
  const res = spawnSync(process.execPath, [tsc, '--noEmit', '--incremental', 'false'], {
    cwd: FRONTEND,
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  });
  if (res.error) {
    console.error(`could not run tsc: ${res.error.message}`);
    process.exit(2);
  }
  // tsc exits non-zero whenever it finds errors, and finding errors is the
  // point — the exit code is deliberately not treated as failure here. Only
  // the census comparison decides pass or fail.
  return `${res.stdout || ''}${res.stderr || ''}`;
}

// --delta before.json after.json — informational, but fails if AFTER is worse.
function delta(beforePath, afterPath) {
  const b = readCensus(beforePath);
  const a = readCensus(afterPath);
  console.log(`total: ${b.total} -> ${a.total}  (${fmtDelta(a.total - b.total)})`);

  console.log('\nby code:');
  for (const code of [...new Set([...Object.keys(b.byCode), ...Object.keys(a.byCode)])].sort()) {
    const bc = b.byCode[code] || 0;
    const ac = a.byCode[code] || 0;
    if (bc !== ac) console.log(`  ${code}: ${bc} -> ${ac}  (${fmtDelta(ac - bc)})`);
  }

  const worse = [];
  for (const file of new Set([...Object.keys(b.byFile), ...Object.keys(a.byFile)])) {
    const bc = b.byFile[file] || 0;
    const ac = a.byFile[file] || 0;
    if (ac > bc) worse.push(`  ${file}: ${bc} -> ${ac}`);
  }
  if (worse.length) {
    console.error('\n::error::the census got worse — these files gained errors:');
    for (const w of worse) console.error(w);
    process.exit(1);
  }
  console.log('\nno file gained errors.');
}

/**
 * The gate. Compares a census against the committed baseline per file, not just
 * on the total — otherwise fixing one error in file A would buy silent room to
 * add one to file B.
 */
function check(current, baseline) {
  const files = [...new Set([...Object.keys(baseline.byFile), ...Object.keys(current.byFile)])].sort();

  const gained = [];
  const fixed = [];
  for (const file of files) {
    const was = baseline.byFile[file] || 0;
    const now = current.byFile[file] || 0;
    if (now > was) gained.push({ file, was, now });
    else if (now < was) fixed.push({ file, was, now });
  }

  console.log(`typecheck errors: ${current.total} (baseline ${baseline.total})`);

  if (gained.length) {
    const added = gained.reduce((n, g) => n + (g.now - g.was), 0);
    console.error('');
    console.error(`::error::${added} new TypeScript error(s).`);
    console.error('');
    console.error('`tsc --noEmit` is a fail-on-new gate: the counts below exceed the');
    console.error('recorded baseline, so this change introduced them and they must be');
    console.error('fixed here rather than added to the baseline.');
    console.error('');
    for (const g of gained) {
      console.error(`  ${g.file}: ${g.was} -> ${g.now}  (${fmtDelta(g.now - g.was)})`);
    }
    console.error('');
    console.error('Reproduce locally:  cd frontend && npm run typecheck');
    return 1;
  }

  if (fixed.length) {
    const removed = fixed.reduce((n, f) => n + (f.was - f.now), 0);
    console.error('');
    console.error(`::error::${removed} baseline error(s) were fixed but the baseline still counts them.`);
    console.error('');
    console.error('The ratchet only turns one way: a baseline above the real count is');
    console.error('headroom that new debt can be added into without this gate noticing.');
    console.error('Refresh it and commit the result:');
    console.error('');
    console.error('  cd frontend && npm run typecheck:baseline');
    console.error('');
    for (const f of fixed) {
      console.error(`  ${f.file}: ${f.was} -> ${f.now}  (${fmtDelta(f.now - f.was)})`);
    }
    return 1;
  }

  console.log('no new type errors, and the baseline matches the real count.');
  return 0;
}

function writeBaseline(current) {
  // Preserve the prose. `_meta` is the part a human wrote — what the debt is,
  // who owns it, which issue tracks it — and regenerating the numbers must not
  // silently drop it, or the next reader inherits a bare count with no owner.
  let meta = {};
  if (fs.existsSync(BASELINE)) {
    meta = JSON.parse(fs.readFileSync(BASELINE, 'utf8'))._meta || {};
  }
  const out = { _meta: meta, ...current };
  fs.writeFileSync(BASELINE, JSON.stringify(out, null, 2) + '\n');
  console.log(`wrote ${path.relative(FRONTEND, BASELINE)}: ${current.total} errors in ${Object.keys(current.byFile).length} files`);
}

function printCensus(census) {
  console.log(`total errors: ${census.total}`);
  console.log(`files:        ${Object.keys(census.byFile).length}`);
  for (const [code, n] of Object.entries(census.byCode).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${code}: ${n}`);
  }
}

function usage() {
  console.error('usage: tsc-census.js --run --check            run tsc, fail on new errors');
  console.error('       tsc-census.js --run --write-baseline   run tsc, record the debt');
  console.error('       tsc-census.js --run --census           run tsc, print the census');
  console.error('       tsc-census.js <tsc-output.txt> [out.json]');
  console.error('       tsc-census.js --delta <before.json> <after.json>');
  process.exit(2);
}

function main(argv) {
  const args = argv.slice(2);

  if (args[0] === '--delta') {
    if (args.length !== 3) usage();
    return delta(args[1], args[2]);
  }

  if (args[0] === '--run') {
    const mode = args[1];
    const census = parse(runTsc());
    if (mode === '--check') {
      return process.exit(check(census, readCensus(BASELINE)));
    }
    if (mode === '--write-baseline') return writeBaseline(census);
    if (mode === '--census' || mode === undefined) return printCensus(census);
    return usage();
  }

  if (!args.length || args[0].startsWith('--')) usage();

  const census = parse(fs.readFileSync(args[0], 'utf8'));
  if (args[1]) fs.writeFileSync(args[1], JSON.stringify(census, null, 2) + '\n');
  printCensus(census);
}

if (require.main === module) main(process.argv);

module.exports = { parse, check, BASELINE };
