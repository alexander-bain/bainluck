#!/usr/bin/env node
// Map each eager source module to the emitted chunk that carries it, via source-unique literals.
//
// WHY: `tools/entry-bytes.mjs` says "chunk 487 is 17,785 brotli bytes". This says "chunk 487 is
// THESE 17 files". Without the pair you cannot tell an atomic payload from a bag of unrelated
// modules, and every "is this chunk splittable?" question stays a guess. Companion to
// tools/entry-graph.mjs; see tools/README-coldpath-rig.md.
//
// METHOD: a literal that occurs in exactly ONE source file under app/components/lib/hooks is a
// fingerprint for that file; whichever emitted chunk contains it is that file's chunk. Modules with
// no source-unique literal report NO-UNIQUE-LITERAL rather than guessing (LAT-P209 hit this with
// `hooks/useAnalytics.ts`; the answer there is to anchor on an eager DEPENDENCY instead).
//
//   node tools/entry-chunkmap.mjs --root "$PWD/frontend" --modules <file-with-one-relpath-per-line>
//   node tools/entry-chunkmap.mjs --root "$PWD/frontend" --modules mods.txt --chunk 2140
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i === -1 ? d : args[i + 1]; };
const ROOT = path.resolve(opt('--root', 'frontend'));
const NEXT = path.join(ROOT, '.next');
const SRC_DIRS = ['app', 'components', 'lib', 'hooks'];

function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (e.name !== '__tests__' && e.name !== 'node_modules') walk(p, out); }
    else if (/\.(tsx?|jsx?)$/.test(e.name)) out.push(p);
  }
  return out;
}
const srcFiles = SRC_DIRS.flatMap((d) => walk(path.join(ROOT, d)));

// literals: quoted strings of decent length made of "chunk-survivable" characters
function literalsOf(src) {
  const out = new Set();
  for (const m of src.matchAll(/["'`]([^"'`\n\\]{14,90})["'`]/g)) {
    const s = m[1];
    if (!/[a-zA-Z]/.test(s)) continue;
    if (/^[./@]/.test(s)) continue;          // import specifiers / paths
    out.add(s);
  }
  return out;
}

const litsByFile = new Map();
const litCount = new Map();
for (const f of srcFiles) {
  const l = literalsOf(fs.readFileSync(f, 'utf8'));
  litsByFile.set(f, l);
  for (const s of l) litCount.set(s, (litCount.get(s) || 0) + 1);
}

const chunkDir = path.join(NEXT, 'static', 'chunks');
const chunkFiles = walk(chunkDir).concat(
  fs.existsSync(chunkDir) ? fs.readdirSync(chunkDir).filter((f) => f.endsWith('.js')).map((f) => path.join(chunkDir, f)) : []
);
const uniqChunks = [...new Set(chunkFiles)];
const chunkText = new Map();
for (const c of uniqChunks) { try { chunkText.set(c, fs.readFileSync(c, 'utf8')); } catch {} }

function chunksFor(file) {
  const uniq = [...(litsByFile.get(file) || [])].filter((s) => litCount.get(s) === 1);
  if (!uniq.length) return { status: 'NO-UNIQUE-LITERAL', chunks: [], probes: 0 };
  const hits = new Map();
  let used = 0;
  for (const s of uniq.slice(0, 40)) {
    used++;
    for (const [c, t] of chunkText) if (t.includes(s)) hits.set(c, (hits.get(c) || 0) + 1);
  }
  const ranked = [...hits.entries()].sort((a, b) => b[1] - a[1]);
  return { status: ranked.length ? 'ok' : 'NOT-FOUND-IN-ANY-CHUNK', chunks: ranked, probes: used };
}

const wantChunk = opt('--chunk', null);
const modulesFile = opt('--modules', null);
const mods = modulesFile
  ? fs.readFileSync(modulesFile, 'utf8').split('\n').map((s) => s.trim()).filter(Boolean)
  : args.filter((a, i) => args[i - 1] === '--module');

for (const m of mods) {
  const f = path.join(ROOT, m);
  if (!fs.existsSync(f)) { console.log(`${m}\tMISSING`); continue; }
  const r = chunksFor(f);
  const names = r.chunks.map(([c, n]) => `${path.basename(c)}(${n}/${r.probes})`);
  if (wantChunk) {
    if (names.some((n) => n.startsWith(wantChunk + '-') || n.startsWith(wantChunk + '.'))) console.log(m);
  } else {
    console.log(`${m}\t${r.status}\t${names.slice(0, 3).join(' ')}`);
  }
}
