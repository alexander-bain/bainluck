// entry-bytes.mjs <route-html> [.next dir] — the BLOCKING javascript of one prerendered route.
//
// 🔴 WHY NOT `next build`'s "First Load JS" TABLE. That table is a webpack accounting of the route's
// module graph; it is not the set of `<script>` tags the browser is actually told to fetch, and the
// two disagree. The number that gates a cold load is the second one, so this reads the emitted
// document and follows its own script tags. LAT-P200 counted them by hand; this is that count, kept.
//
// Excluded, deliberately: `polyfills-*.js`, which carries `noModule=""` and is therefore fetched by
// no browser that can run the app. Counting it inflates every before AND after by the same constant,
// which is harmless for a delta and wrong for a total — and totals get quoted.
//
// Reports raw, gzip -9 and brotli q11 for each chunk and for the set. Vercel serves brotli, so the
// brotli column is the one a reader's connection actually pays; raw is what has to be parsed and
// executed once it lands. A cut should be reported in both, because they move differently.
//
// Usage, both sides of a diff:
//   node tools/entry-bytes.mjs frontend/.next/server/app/index.html frontend/.next
//   node tools/entry-bytes.mjs frontend/.next/server/app/sports.html frontend/.next
import { readFileSync, existsSync } from 'fs';
import { gzipSync, brotliCompressSync, constants } from 'zlib';

const [htmlPath, nextDirArg] = process.argv.slice(2);
if (!htmlPath) {
  console.error('usage: entry-bytes.mjs <prerendered-route.html> [.next dir]');
  process.exit(2);
}
const nextDir = nextDirArg || '.next';
if (!existsSync(htmlPath)) {
  console.error(`entry-bytes: ${htmlPath} does not exist — build first, and check the route name`);
  process.exit(2);
}

const html = readFileSync(htmlPath, 'utf8');
const tags = [...html.matchAll(/<script([^>]*?)src="([^"]+)"([^>]*)>/g)];
if (!tags.length) {
  // A route whose document carries no script tags is either not the file you meant or a build that
  // did not finish. Either way it must not report "0 bytes of blocking JS" as a result.
  console.error(`entry-bytes: parsed ZERO <script src> tags out of ${htmlPath}`);
  process.exit(1);
}

let raw = 0, gz = 0, br = 0, counted = 0, skipped = 0, missing = 0;
const rows = [];
for (const [, pre, src, post] of tags) {
  if (/noModule/.test(pre + post)) { skipped++; continue; }
  if (!src.startsWith('/_next/')) { skipped++; continue; }
  const file = nextDir + src.replace('/_next/', '/').split('?')[0];
  if (!existsSync(file)) {
    // Loudly, not silently: a chunk the document names and the build did not emit is a broken
    // build, and a total computed around the hole would look like a win.
    console.error(`entry-bytes: MISSING ${file} (named by ${htmlPath})`);
    missing++;
    continue;
  }
  const buf = readFileSync(file);
  const g = gzipSync(buf, { level: 9 }).length;
  const b = brotliCompressSync(buf, { params: { [constants.BROTLI_PARAM_QUALITY]: 11 } }).length;
  raw += buf.length; gz += g; br += b; counted++;
  rows.push({ chunk: src.replace('/_next/static/chunks/', '').split('?')[0], raw: buf.length, gzip: g, brotli: b });
}
if (missing) process.exit(1);

rows.sort((a, b) => b.raw - a.raw);
console.error(`${'raw'.padStart(9)}${'gzip'.padStart(9)}${'brotli'.padStart(9)}  chunk`);
for (const r of rows) {
  console.error(`${String(r.raw).padStart(9)}${String(r.gzip).padStart(9)}${String(r.brotli).padStart(9)}  ${r.chunk}`);
}
console.error(`scripts=${counted} (skipped ${skipped}: noModule/external)  raw=${raw} gzip=${gz} brotli=${br}`);
console.log(JSON.stringify({ route: htmlPath, scripts: counted, raw, gzip: gz, brotli: br, chunks: rows }, null, 2));
