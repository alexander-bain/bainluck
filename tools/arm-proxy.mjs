// arm-proxy.mjs — serve TWO builds of the frontend from ONE port, switchable per request.
//
// This is the server half of `cold-load.mjs`'s `COLD_ARM_FILE` A/B. The rig writes `control` or
// `treatment` into a file before each navigation; this process reads that file when the request
// arrives and answers out of the matching build directory. Origin, port, CORS and document URL are
// then identical between arms by construction, and the only difference left is which build answered.
//
// 🔴 WHY NOT TWO `next start`s ON TWO PORTS. The API's CORS allowlist names ONE local port
// (`http://localhost:3000` / `http://127.0.0.1:3000`, backend/app/main.py). A second port produces a
// page that fetches no feed and draws no card, and every run is (correctly) thrown out by the rig's
// validity guard. LAT-P204 lost a full run to exactly that before the one-origin switch existed.
//
// 🔴 WHY THIS SERVES STATIC FILES RATHER THAN RUNNING NEXT. Both arms are the same prerendered
// route: `/` is static, every card is client-rendered, and the document is bytes on disk. Serving
// `.next/server/app/*.html` plus `.next/static/**` reproduces what Vercel serves for that route and
// makes the two arms trivially symmetric — no two servers, no two warmups, no dev-vs-prod skew.
// What it does NOT reproduce: RSC prefetch responses (`?_rsc=`), which 404 here. That is measured
// ground rather than a guess — App Router prefetch has been ablated twice on this page (LAT-P202 on
// FCP, LAT-P204 on ttfc) and moves the first card by +12 to +24 ms, i.e. nothing — and it 404s
// identically in both arms.
//
// ⚠️ COMPRESSION IS PART OF THE MEASUREMENT. Vercel serves brotli, so a rig that serves raw bytes
// measures a page nobody is served: the entry set is ~616 kB raw and ~164 kB brotli, and on a
// throttled link that is a 4x difference in the very quantity under test. Responses are therefore
// brotli-encoded when the client accepts it (q11, the same setting `tools/entry-bytes.mjs` reports),
// gzip when it does not, and each encoded body is cached in memory so compression cost never lands
// inside a measured run.
//
// Usage:
//   ARM_FILE=/tmp/arm CONTROL=/tmp/arm-control TREATMENT=/tmp/arm-treatment \
//     node tools/arm-proxy.mjs
// where each build directory holds:
//   <dir>/app-html/index.html   (copied from frontend/.next/server/app)
//   <dir>/static/**             (copied from frontend/.next/static)
import { createServer } from 'http';
import { existsSync, readFileSync, statSync } from 'fs';
import { join, normalize, extname } from 'path';
import { gzipSync, brotliCompressSync, constants } from 'zlib';

const ARM_FILE = process.env.ARM_FILE || '/tmp/cold-arm';
const DIRS = { control: process.env.CONTROL, treatment: process.env.TREATMENT };
const PORT = parseInt(process.env.PORT || '3000', 10);
const PUBLIC = process.env.PUBLIC_DIR || null;

for (const [arm, dir] of Object.entries(DIRS)) {
  if (!dir || !existsSync(join(dir, 'app-html', 'index.html')) || !existsSync(join(dir, 'static'))) {
    console.error(`arm-proxy: ${arm} build directory is missing or incomplete: ${dir}`);
    console.error('           expected <dir>/app-html/index.html and <dir>/static/');
    process.exit(2);
  }
}

/**
 * Every `<script src>` and stylesheet the arm's own document names must exist inside the arm's own
 * static directory — checked at STARTUP, in both arms, before a single run is paid for.
 *
 * A snapshot copied while a build was still writing, or copied from the wrong `.next`, produces a
 * document whose hashed chunks 404. That is a dead arm, and the only symptom downstream is twelve
 * INVALID runs eight minutes later. Six milliseconds of stat() here turns it into a refusal.
 */
function assertArmIsWhole(arm, dir) {
  const html = readFileSync(join(dir, 'app-html', 'index.html'), 'utf8');
  const refs = [...html.matchAll(/(?:src|href)="(\/_next\/static\/[^"]+)"/g)].map((m) => m[1]);
  if (refs.length < 5) {
    console.error(`arm-proxy: ${arm}'s index.html names only ${refs.length} static assets — that is`);
    console.error('           not a real Next document; check the snapshot.');
    process.exit(2);
  }
  const missing = refs.filter((r) => !existsSync(join(dir, 'static', r.slice('/_next/static/'.length))));
  if (missing.length) {
    console.error(`arm-proxy: ${arm}'s document names ${missing.length} asset(s) its own static/ does not have:`);
    for (const m of missing.slice(0, 5)) console.error(`           ${m}`);
    console.error('           The snapshot and the build have drifted. Re-copy .next for this arm.');
    process.exit(2);
  }
  console.error(`arm-proxy: ${arm} whole — ${refs.length} static assets, all present`);
}
for (const [arm, dir] of Object.entries(DIRS)) assertArmIsWhole(arm, dir);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain; charset=utf-8',
  '.webmanifest': 'application/manifest+json',
};
// Already-compressed formats: re-encoding them costs CPU and returns nothing.
const OPAQUE = new Set(['.png', '.jpg', '.jpeg', '.webp', '.avif', '.woff2', '.woff', '.ico', '.gif']);

/**
 * path+mtime+size -> { raw, br, gz } — compression happens once, never inside a measured run.
 *
 * 🔴 THE KEY IS NOT THE PATH. It was, for exactly one run, and that run is why this comment
 * exists: re-snapshotting the treatment build leaves every path identical (`app-html/index.html`)
 * while the bytes change, so a path-keyed cache kept serving the PREVIOUS build's document —
 * which pointed at hashed chunks that no longer existed. Every treatment run 404'd its own
 * javascript, rendered nothing, and was thrown out by the rig's validity guard. A switchable
 * two-build server whose cache can serve a build that is no longer on disk is the same failure
 * class as one that serves one build to both arms, and it looks like "the cut broke the page".
 */
const cache = new Map();
function body(file, encoding) {
  const st = statSync(file);
  const key = `${file}:${st.mtimeMs}:${st.size}`;
  let entry = cache.get(key);
  if (!entry) {
    entry = { raw: readFileSync(file) };
    cache.set(key, entry);
  }
  if (encoding === 'br') {
    entry.br ??= brotliCompressSync(entry.raw, {
      params: { [constants.BROTLI_PARAM_QUALITY]: 11 },
    });
    return entry.br;
  }
  if (encoding === 'gzip') {
    entry.gz ??= gzipSync(entry.raw, { level: 9 });
    return entry.gz;
  }
  return entry.raw;
}

/** The arm is re-read per request: the rig rewrites the file between navigations. */
function currentArm() {
  try {
    const v = readFileSync(ARM_FILE, 'utf8').trim();
    if (v === 'control' || v === 'treatment') return v;
  } catch {}
  return 'control';
}

/**
 * Map a URL path to a file inside the arm's build, or null.
 *
 * `normalize` before the prefix check, so `/_next/static/../../etc/passwd` cannot walk out of the
 * build directory. It is a local measurement rig, but a path-traversal hole in a server that runs
 * on a developer machine is still a hole.
 */
function resolveFile(dir, urlPath) {
  const clean = normalize(decodeURIComponent(urlPath.split('?')[0]));
  if (clean.includes('\0')) return null;
  if (clean === '/' || clean === '/index.html' || clean === '/discover' || clean === '/discover/') {
    return join(dir, 'app-html', 'index.html');
  }
  if (clean.startsWith('/_next/static/')) {
    const file = join(dir, 'static', clean.slice('/_next/static/'.length));
    return file.startsWith(join(dir, 'static')) ? file : null;
  }
  if (PUBLIC) {
    const file = join(PUBLIC, clean);
    if (file.startsWith(PUBLIC) && existsSync(file) && statSync(file).isFile()) return file;
  }
  // Any other prerendered route, so a navigation out of `/` still answers.
  const routeHtml = join(dir, 'app-html', `${clean.replace(/^\//, '').replace(/\/$/, '')}.html`);
  if (routeHtml.startsWith(join(dir, 'app-html')) && existsSync(routeHtml)) return routeHtml;
  return null;
}

let served = { control: 0, treatment: 0 };

const server = createServer((req, res) => {
  const arm = currentArm();
  const dir = DIRS[arm];
  const file = resolveFile(dir, req.url || '/');
  if (!file || !existsSync(file)) {
    res.writeHead(404, { 'content-type': 'text/plain', 'cache-control': 'no-store' });
    res.end('not found');
    return;
  }
  const ext = extname(file).toLowerCase();
  const accept = String(req.headers['accept-encoding'] || '');
  let encoding = null;
  if (!OPAQUE.has(ext)) {
    if (/\bbr\b/.test(accept)) encoding = 'br';
    else if (/\bgzip\b/.test(accept)) encoding = 'gzip';
  }
  const payload = body(file, encoding);
  const headers = {
    'content-type': TYPES[ext] || 'application/octet-stream',
    'content-length': payload.length,
    // No caching: every run of the rig is a cold load, and a 304 would silently
    // turn the second arm into a different experiment.
    'cache-control': 'no-store',
    'x-arm': arm,
  };
  if (encoding) headers['content-encoding'] = encoding;
  served[arm]++;
  res.writeHead(200, headers);
  res.end(req.method === 'HEAD' ? undefined : payload);
});

server.listen(PORT, '127.0.0.1', () => {
  console.error(`arm-proxy: :${PORT}  arm-file=${ARM_FILE}`);
  console.error(`  control   = ${DIRS.control}`);
  console.error(`  treatment = ${DIRS.treatment}`);
});

// A count per arm, printed on exit: a switch read from a file is exactly the kind of thing that
// silently serves one build to both arms, and "did each arm actually get requests" is the cheapest
// possible check on that. The authoritative check stays the rig's own re-derivation of each run's
// arm from the `app/page-*.js` hash it fetched.
for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    console.error(`arm-proxy: served control=${served.control} treatment=${served.treatment}`);
    process.exit(0);
  });
}
