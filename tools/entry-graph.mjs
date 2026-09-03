#!/usr/bin/env node
// Eager-import graph walker for the Next.js app router entry set.
//
// WHY THIS FILE IS TRACKED: five consecutive latency cycles (LAT-P206, P209, P211, P213, P214)
// each re-derived this walker from prose in a handoff directive, and each re-derivation
// re-introduced the same two resolution quirks. A rig that lives only in /tmp is lost work, not a
// local preference. Landed by LAT-P214 alongside cold-load / arm-proxy / entry-bytes / entry-chunkmap;
// see tools/README-coldpath-rig.md for the whole rig and how the five pieces fit together.
//
// WHAT IT ANSWERS: "how many EAGER importers does module X have on the landing page?" That edge
// count is the first thing to check before proposing a code-split — LAT-P206 converted one of
// `lib/firebase.ts`'s TWO eager importers and made the entry set 362 brotli bytes BIGGER.
//
// Usage (always pass an ABSOLUTE --root; see the cwd guard below):
//   node tools/entry-graph.mjs --root "$PWD/frontend" --list
//   node tools/entry-graph.mjs --root "$PWD/frontend" --target components/discover/TournamentCard.tsx
//   node tools/entry-graph.mjs --root "$PWD/frontend" --validate   # reproduce LAT-P209's known answer
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const opt = (name, dflt) => {
  const i = args.indexOf(name);
  return i === -1 ? dflt : args[i + 1];
};
const has = (name) => args.includes(name);

const ROOT = path.resolve(opt('--root', 'frontend'));
const ROOTS = [
  'app/layout.tsx',
  'app/page.tsx',
  'app/discover/page.tsx',
];
const EXTS = ['.tsx', '.ts', '.jsx', '.js'];

// A scan must RAISE on what it cannot parse. The Bash tool's cwd persists between calls, so a
// relative --root silently resolves to <cwd>/frontend and yields an empty graph that reads as
// "0 eager importers" instead of an error. (Cost LAT-P214 one step.)
for (const r of ROOTS) {
  if (!fs.existsSync(path.join(ROOT, r))) {
    console.error(`FATAL: entry root missing: ${path.join(ROOT, r)} (--root resolved to ${ROOT})`);
    process.exit(3);
  }
}

function resolveSpec(spec, fromFile) {
  let base;
  if (spec.startsWith('@/')) base = path.join(ROOT, spec.slice(2));
  else if (spec.startsWith('./') || spec.startsWith('../')) base = path.resolve(path.dirname(fromFile), spec);
  else return null; // bare package specifier
  // QUIRK (LAT-P213): resolve a path that ALREADY has an extension before appending one,
  // else `components/Foo.tsx` reads absent while `components/Foo` reads present.
  if (path.extname(base) && fs.existsSync(base) && fs.statSync(base).isFile()) return base;
  for (const e of EXTS) if (fs.existsSync(base + e)) return base + e;
  for (const e of EXTS) {
    const idx = path.join(base, 'index' + e);
    if (fs.existsSync(idx)) return idx;
  }
  return null;
}

// Returns { eager: [{spec, clause, raw}], lazy: [{spec}] }
function parseImports(src) {
  const eager = [];
  const lazy = [];

  // strip block+line comments cheaply (good enough: we only need import statements)
  const code = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1');

  // dynamic import('...') — lazy
  for (const m of code.matchAll(/\bimport\s*\(\s*["']([^"']+)["']\s*\)/g)) {
    lazy.push({ spec: m[1] });
  }

  // static: import <clause> from '...'   |   import '...'   |   export <clause> from '...'
  const re = /(^|[\n;}])\s*(import|export)\s+([\s\S]*?)\s+from\s*["']([^"']+)["']/g;
  for (const m of code.matchAll(re)) {
    const clause = m[3].trim();
    const spec = m[4];
    if (/^type\b/.test(clause)) continue;                       // `import type { X } from`
    const braces = clause.match(/\{([\s\S]*)\}/);
    if (braces) {
      const names = braces[1].split(',').map((s) => s.trim()).filter(Boolean);
      const outsideBraces = clause.replace(/\{[\s\S]*\}/, '').replace(/,/g, '').trim();
      // QUIRK (LAT-P213): a clause of ALL `{ type A, type B }` is type-only.
      if (names.length && names.every((n) => /^type\s/.test(n)) && !outsideBraces) continue;
    }
    eager.push({ spec, clause, kind: m[2] });
  }
  // side-effect import: import '...'
  for (const m of code.matchAll(/(^|[\n;}])\s*import\s*["']([^"']+)["']/g)) {
    eager.push({ spec: m[2], clause: '(side-effect)', kind: 'import' });
  }
  return { eager, lazy };
}

const cache = new Map();
function fileInfo(f) {
  if (!cache.has(f)) cache.set(f, parseImports(fs.readFileSync(f, 'utf8')));
  return cache.get(f);
}

// BFS over eager edges only.
const eagerSet = new Set();
const edges = []; // {from, to, clause}
const lazyEdges = [];
const queue = ROOTS.map((r) => path.join(ROOT, r)).filter((f) => fs.existsSync(f));
for (const f of queue) eagerSet.add(f);
while (queue.length) {
  const f = queue.shift();
  const { eager, lazy } = fileInfo(f);
  for (const e of eager) {
    const t = resolveSpec(e.spec, f);
    if (!t) continue;
    edges.push({ from: f, to: t, clause: e.clause });
    if (!eagerSet.has(t)) { eagerSet.add(t); queue.push(t); }
  }
  for (const l of lazy) {
    const t = resolveSpec(l.spec, f);
    if (t) lazyEdges.push({ from: f, to: t });
  }
}

const rel = (f) => path.relative(ROOT, f);

if (has('--list')) {
  const list = [...eagerSet].map(rel).sort();
  console.log(`/'s eager module set: ${list.length} modules`);
  for (const m of list) console.log('  ' + m);
  process.exit(0);
}

function report(targetRel) {
  const target = path.join(ROOT, targetRel);
  const importers = edges.filter((e) => e.to === target && eagerSet.has(e.from));
  const lazyIn = lazyEdges.filter((e) => e.to === target);
  console.log(`TARGET ${targetRel}`);
  console.log(`  in eager set: ${eagerSet.has(target) ? 'YES' : 'no'}`);
  console.log(`  eager importers: ${importers.length}`);
  for (const i of importers) console.log(`    - ${rel(i.from)}   ${i.clause.replace(/\s+/g, ' ')}`);
  if (lazyIn.length) {
    console.log(`  dynamic import() sites: ${lazyIn.length}`);
    for (const i of lazyIn) console.log(`    ~ ${rel(i.from)}`);
  }
  console.log('');
  return importers.length;
}

if (has('--validate')) {
  // KNOWN ANSWER (LAT-P209, re-checked by P211 and P213): lib/eventKey.ts has exactly 4 eager importers.
  const n = report('lib/eventKey.ts');
  console.log(n === 4 ? 'VALIDATE PASS: lib/eventKey.ts = 4 eager importers (matches LAT-P209)'
                      : `VALIDATE FAIL: expected 4, got ${n}`);
  process.exit(n === 4 ? 0 : 1);
}

const targets = args.filter((a, i) => args[i - 1] === '--target');
if (!targets.length) { console.error('need --target <relpath> | --list | --validate'); process.exit(2); }
for (const t of targets) report(t);
