// period-labels-7876.mjs — photograph the period-marker strip of BOTH charts on
// an event page at phone width, and read which labels actually reached the page.
//
// #7876: the win-probability chart dropped `HT` from an overtime game. The count
// of markers looked healthy on both arms (four either way), so a probe that
// counts proves nothing — this reads `data-period-labels`, the names, and shoots
// the strip so the arrangement can be judged as a reader would.
//
// Both charts, because the spacing rule is shared and a fix to one is half a fix
// (#6658 / latency-467). Cross-sport, because the rule is shared across sports
// and an NFL-only check cannot see what it did to innings.
//
// Usage: node period-labels-7876.mjs <baseUrl> <eventId> <outDir> [tag]
// Exit:  0 read · 2 bad usage · 4 no chart on the page
import { createRequire } from 'module';
import { existsSync, readdirSync, mkdirSync, writeFileSync } from 'fs';
import { execFile } from 'child_process';
import { promisify } from 'util';
const execFileAsync = promisify(execFile);

function findPlaywright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (existsSync(npx)) {
    for (const d of readdirSync(npx)) {
      const p = `${npx}/${d}/node_modules/`;
      if (existsSync(`${p}playwright`)) return p;
    }
  }
  return process.cwd() + '/';
}
const { chromium } = createRequire(findPlaywright())('playwright');

const [baseUrl, eventId, outDir, tag = 'shot'] = process.argv.slice(2);
if (!baseUrl || !eventId || !outDir) {
  console.error('usage: period-labels-7876.mjs <baseUrl> <eventId> <outDir> [tag]');
  process.exit(2);
}
mkdirSync(outDir, { recursive: true });
const URL = `${baseUrl.replace(/\/$/, '')}/events/${eventId}`;

// Is the page itself served from this machine? Asked of the URL's HOST, parsed,
// never of the URL as a string.
//
// It used to be `/localhost|127\.0\.0\.1/.test(baseUrl)`, which matches anywhere
// in the URL — so `https://bainluck.com/localhost` is "local", and the tool would
// then intercept `api.bainluck.com` through curl and withhold the proxy bypass on
// a PRODUCTION run. CodeQL calls that `js/regex/missing-regexp-anchor` and rates
// it high; here the reachable cost is a probe that quietly measures something
// other than what its argument said, which is the worse half of it for an
// instrument. Anchoring the pattern would silence the alert, but comparing the
// parsed hostname is the thing that is actually being asked.
//
// An unparseable base is NOT local: the remote path is the one that works
// through a proxy, so an argument we cannot read fails toward the safe render.
function isLoopbackBase(url) {
  let host;
  try {
    host = new URL(url).hostname;
  } catch {
    return false;
  }
  return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]';
}
const LOCAL_PAGE = isLoopbackBase(baseUrl);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
// 🪤 A LOCALHOST RENDER STILL NEEDS THE PROXY, because the page is local and its
// DATA is not: every chart on it fetches `api.bainluck.com`. The first attempt
// dropped the proxy entirely when the base was localhost and got a page with no
// chart on it at all — which reads exactly like "the build is broken" and is
// really "the browser could not reach the API".
//
// So the proxy is always set, and only the BYPASS changes. Chromium bypasses
// loopback by default; `<-loopback>` cancels that default and is right when
// every request should go through the proxy, and wrong here — it would send the
// localhost page request to a proxy that cannot see this machine's port.
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!LOCAL_PAGE) args.push('--proxy-bypass-list=<-loopback>');
}

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });

// 🪤 A LOCAL BUILD CANNOT REACH THE API, AND THE PAGE LOOKS BROKEN RATHER THAN
// BLOCKED. Rendering an unmerged change means serving the page from localhost,
// but its data still comes from `api.bainluck.com`, and in this sandbox:
//
//   no proxy flag  → api dies `net::ERR_ACCESS_DENIED` (direct egress is blocked;
//                    `curl --noproxy '*'` returns HTTP 000)
//   proxy flag     → api dies `net::ERR_FAILED` unless `--proxy-bypass-list=<-loopback>`
//                    is also set, which then routes the LOCALHOST page at the
//                    proxy too, and the proxy cannot see this machine's port.
//
// Both arms render the page shell with "Couldn't reach the server" and NO chart,
// which is indistinguishable from the build being broken — the first run of this
// tool was read that way for several minutes.
//
// `curl` honours the proxy and works, so the API is fetched through it and the
// response handed back to the page. The browser then needs no egress at all.
if (LOCAL_PAGE) {
  await page.route(/api\.bainluck\.com/, async (route) => {
    const url = route.request().url();
    try {
      const { stdout } = await execFileAsync(
        'curl',
        ['-s', '--max-time', '40', '-H', `x-bainluck-origin: ${process.env.BL_AGENT || 'ux'}`, url],
        { maxBuffer: 256 * 1024 * 1024 },
      );
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'access-control-allow-origin': '*' },
        body: stdout,
      });
    } catch {
      // Abort rather than fulfil with an empty 200: a blank body would render as
      // a chartless page and be read as the change's fault (gotcha #53).
      await route.abort();
    }
  });
}

// `networkidle` never arrives on a live page (it polls forever) — wait for the
// chart itself, which is what every assertion here is about.
await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 90000 });
try {
  await page.waitForSelector('.recharts-wrapper', { timeout: 45000 });
} catch {
  console.error('no .recharts-wrapper on the page');
}
try {
  const b = page.locator('button', { hasText: /^(Accept|Accept all)$/i }).first();
  if (await b.count()) { await b.click({ timeout: 4000 }); await page.waitForTimeout(500); }
} catch { /* already accepted */ }
await page.waitForTimeout(2000);

/** Every wrapper that reports the period channel — one per chart on the page. */
const read = await page.evaluate(() => {
  const out = [];
  // Selected on `data-period-label-rows`, which BOTH arms carry —
  // `data-period-labels` ships with the #7876 fix, so keying on it would make
  // the before arm report "no chart" and the comparison would silently become a
  // one-armed check.
  for (const el of document.querySelectorAll('[data-period-label-rows]')) {
    const wrapper = el.querySelector('.recharts-wrapper');
    // The painted caption of every period rule, read off the DOM rather than
    // re-derived — a label that is computed and never drawn is the #7876 shape.
    const painted = wrapper
      ? [...wrapper.querySelectorAll('.recharts-reference-line text')].map((t) => ({
          text: t.textContent.trim(),
          x: Math.round(t.getBoundingClientRect().x),
          y: Math.round(t.getBoundingClientRect().y),
          w: Math.round(t.getBoundingClientRect().width),
        }))
      : [];
    out.push({
      labels: el.getAttribute('data-period-labels') ?? '(channel absent — pre-#7876 build)',
      rows: el.getAttribute('data-period-label-rows'),
      count: el.getAttribute('data-period-boundaries'),
      painted,
    });
  }
  return out;
});

if (read.length === 0) {
  console.error('page reported no period channel at all');
  await browser.close();
  process.exit(4);
}

// Overlap check, per row, on the PAINTED boxes — the thing the proportional rule
// is a proxy for. Two captions on one row whose boxes intersect is a smear.
for (const chart of read) {
  const byRow = new Map();
  for (const p of chart.painted) {
    const row = byRow.get(p.y) ?? [];
    row.push(p);
    byRow.set(p.y, row);
  }
  chart.overlaps = [];
  for (const [, row] of byRow) {
    row.sort((a, b) => a.x - b.x);
    for (let i = 1; i < row.length; i++) {
      const gap = row[i].x - (row[i - 1].x + row[i - 1].w);
      if (gap < 0) chart.overlaps.push(`${row[i - 1].text}|${row[i].text} ${gap}px`);
    }
  }
  chart.rowsPainted = byRow.size;
}

writeFileSync(`${outDir}/${tag}.json`, JSON.stringify({ url: URL, at: new Date().toISOString(), charts: read }, null, 2));
for (const [i, c] of read.entries()) {
  console.log(`chart ${i}: labels=[${c.labels}] rows=[${c.rows}] painted=${c.painted.length} rowsPainted=${c.rowsPainted} overlaps=${JSON.stringify(c.overlaps)}`);
  console.log(`          captions: ${c.painted.map((p) => `${p.text}@${p.x},${p.y}`).join(' ')}`);
}

// One frame per chart, aimed at the chart rather than a pixel offset.
const wrappers = await page.locator('[data-period-label-rows]').all();
for (const [i, w] of wrappers.entries()) {
  await w.scrollIntoViewIfNeeded();
  await page.waitForTimeout(600);
  await w.screenshot({ path: `${outDir}/${tag}-chart${i}.png` });
}
await page.screenshot({ path: `${outDir}/${tag}-page.png`, fullPage: false });

await browser.close();
process.exit(0);
