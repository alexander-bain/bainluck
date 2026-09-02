// cold-load.mjs <url> [runs] [outJson] — real-browser COLD-load timing of a production page.
//
// Why this exists: the latency lane has shipped eight certified cuts graded only in BYTES, because
// `curl` cannot exercise srcset and cannot see hydration, and the lane believed it had no browser.
// It does — since ux/976 (2026-09-01) headless Chromium runs in the agent sandbox. Same launch
// recipe as tools/shop-shot.mjs; see that file for why each arg is required.
//
// Every run is COLD: a brand-new browser (so a brand-new disk+memory cache, no service worker, no
// prior connection) plus an explicit CDP Network.setCacheDisabled. --single-process supports
// exactly one context, so one browser per run is forced anyway.
//
// Reports TWO numbers, because one is not enough (alex-inbox/latency-020 §3):
//   usable  — first contentful paint / LCP / DOMContentLoaded: when the reader sees the page
//   finish  — load event and network-quiet: when the page stops working
//
// ⚠️ POPULATION (P188): these run through the session egress proxy on this machine. They are NOT
// comparable to numbers taken on Alex's laptop on his network. They ARE comparable to each other,
// which is what makes this a durable instrument: run it before a cut and after a cut.
import { createRequire } from 'module';
import { existsSync, readdirSync, writeFileSync } from 'fs';

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
const [url, runsArg, outJson] = process.argv.slice(2);
if (!url) { console.error('usage: cold-load.mjs <url> [runs] [out.json]'); process.exit(2); }
const RUNS = parseInt(runsArg || '5', 10);
// Back-to-back cold loads can degrade the surface being measured; pace them by default.
const PACE_MS = parseInt(process.env.COLD_PACE_MS || '3000', 10);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const baseArgs = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) baseArgs.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

// Collected inside the page. Buffered observers so nothing that fired before we attach is lost.
const COLLECT = `(() => {
  const nav = performance.getEntriesByType('navigation')[0] || {};
  const paint = Object.fromEntries(performance.getEntriesByType('paint').map(p => [p.name, p.startTime]));
  const res = performance.getEntriesByType('resource');
  const byType = {};
  for (const r of res) {
    const t = r.initiatorType || 'other';
    byType[t] = byType[t] || { count: 0, transfer: 0, decoded: 0, lastEnd: 0 };
    byType[t].count++;
    byType[t].transfer += r.transferSize || 0;
    byType[t].decoded += r.decodedBodySize || 0;
    byType[t].lastEnd = Math.max(byType[t].lastEnd, r.responseEnd);
  }
  const slowest = res
    .map(r => ({ name: r.name, type: r.initiatorType, start: Math.round(r.startTime), end: Math.round(r.responseEnd), dur: Math.round(r.duration), transfer: r.transferSize || 0 }))
    .sort((a, b) => b.end - a.end)
    .slice(0, 20);
  // Proof of a real render, not an error page timed to look fast (gotcha #53 / timing-on-404).
  const proof = {
    title: document.title,
    status1: (document.querySelector('h1') || {}).textContent || null,
    cards: document.querySelectorAll('a[href^="/futures/"], a[href^="/event/"], a[href^="/events/"]').length,
    pct: (document.body.innerText.match(/\\d+%/g) || []).length,
    bodyChars: document.body.innerText.length,
  };
  return {
    ttfb: nav.responseStart,
    domInteractive: nav.domInteractive,
    dcl: nav.domContentLoadedEventEnd,
    load: nav.loadEventEnd,
    htmlTransfer: nav.transferSize,
    fcp: paint['first-contentful-paint'],
    lcp: window.__lcp || null,
    lcpEl: window.__lcpEl || null,
    cls: window.__cls || 0,
    resourceCount: res.length,
    resourceTransfer: res.reduce((a, r) => a + (r.transferSize || 0), 0),
    lastResourceEnd: res.reduce((a, r) => Math.max(a, r.responseEnd), 0),
    byType,
    slowest,
    proof,
  };
})()`;

const LCP_HOOK = `
  // CLS matters here specifically: the font ships display:swap, so anything that delays the swap
  // trades paint time against a visible reflow. A prize measured without its cost is half a number.
  window.__cls = 0;
  try {
    new PerformanceObserver((l) => {
      for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value;
    }).observe({ type: 'layout-shift', buffered: true });
  } catch (e) {}
  window.__lcp = null; window.__lcpEl = null;
  try {
    new PerformanceObserver((l) => {
      const e = l.getEntries();
      const last = e[e.length - 1];
      window.__lcp = last.startTime;
      // Naming the LCP element is what turns "the page is slow" into "THIS is slow".
      window.__lcpEl = {
        url: last.url || null,
        tag: last.element ? last.element.tagName : null,
        cls: last.element ? String(last.element.className).slice(0, 120) : null,
        text: last.element ? (last.element.textContent || '').trim().slice(0, 80) : null,
        size: last.size,
      };
    }).observe({ type: 'largest-contentful-paint', buffered: true });
  } catch (e) {}
`;

// ABLATION MODE — measure a cut BEFORE building it.
// COLD_ABLATE=<name> blocks a class of requests at the browser and interleaves treatment runs with
// control runs (A,B,A,B,…) inside one invocation, so network drift hits both arms equally. A cut
// that shows no delta here is dead before anyone writes the code for it.
const ABLATIONS = {
  // Next.js App Router prefetch: RSC payloads for card destinations + the JS of nav routes the
  // reader has not opened. Everything here is speculative work for a navigation that may never come.
  prefetch: (url) => /[?&]_rsc=/.test(url) || /\/chunks\/app\/(sports|my-stuff|discover\/stats)\/page-/.test(url),
  // The hero photographs, to size what imagery costs the critical path.
  images: (url) => /images\.pexels\.com/.test(url),
  // The preloaded webfont. Not a shippable change by itself — this sizes the prize, so we know
  // whether subsetting / font-display / dropping a weight is worth a queue.
  font: (url) => /\/_next\/static\/media\/.*\.woff2?$/.test(url),
};
// HTML-REWRITE ablations. Blocking a request tells you what the BYTES cost; it does not tell you
// what a config change would buy, because `preload: false` still downloads the font — it just
// discovers it later. Rewriting the document is the faithful simulation of that change.
const REWRITES = {
  // next/font's `preload: false`: drop the <link rel="preload"> for the woff2, keep everything else.
  // The font still loads, just off the earliest critical window.
  fontpreload: (html) => html.replace(/<link[^>]+rel="preload"[^>]*\.woff2?[^>]*>/g, ''),
};
const ablateName = process.env.COLD_ABLATE || null;
const rewrite = ablateName ? REWRITES[ablateName] : null;
const ablate = ablateName ? ABLATIONS[ablateName] : null;
if (ablateName && !ablate && !rewrite) { console.error(`unknown COLD_ABLATE=${ablateName}; known: ${[...Object.keys(ABLATIONS), ...Object.keys(REWRITES)]}`); process.exit(2); }

// Fetch the document ONCE via curl (which has the session's egress, unlike Node) and derive both
// arms from those exact bytes, so the only difference between them is the rewrite itself.
let DOC_BEFORE = null, DOC_AFTER = null;
if (rewrite) {
  const { execFileSync } = await import('child_process');
  DOC_BEFORE = execFileSync('curl', ['-sL', '--max-time', '30', url], { maxBuffer: 64 * 1024 * 1024 }).toString();
  DOC_AFTER = rewrite(DOC_BEFORE);
  // A rewrite that matched nothing is a vacuous treatment arm: the A/B would compare the page to
  // itself and report "no effect" for a cut that was never applied.
  if (DOC_AFTER === DOC_BEFORE) { console.error(`REWRITE '${ablateName}' MATCHED NOTHING — treatment arm would be vacuous`); process.exit(1); }
  console.error(`rewrite '${ablateName}': document ${DOC_BEFORE.length} -> ${DOC_AFTER.length} bytes`);
}

const results = [];
const TOTAL = (ablate || rewrite) ? RUNS * 2 : RUNS;
for (let i = 0; i < TOTAL; i++) {
  // Interleave: even = control, odd = treatment. Never all-of-one-then-all-of-the-other.
  const treated = (ablate || rewrite) ? (i % 2 === 1) : false;
  if (i > 0 && PACE_MS > 0) await new Promise((r) => setTimeout(r, PACE_MS));
  const browser = await chromium.launch({ args: baseArgs });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    let blocked = 0;
    if (treated && ablate) {
      await page.route('**/*', (route) => {
        const u = route.request().url();
        if (ablate(u)) { blocked++; return route.abort(); }
        return route.continue();
      });
    }
    if (rewrite) {
      // BOTH arms are served the document from memory — control the original bytes, treatment the
      // rewritten ones. Serving only the treatment arm this way would make the document delivery
      // itself the difference between the arms, and the measured delta would be the rig, not the cut.
      // (`route.fetch()` is not an option: it runs in Node, which has no egress in this sandbox.)
      const body = treated ? DOC_AFTER : DOC_BEFORE;
      // Serving from memory gives a ~1ms TTFB, which compresses the timeline and can flatter a
      // delta that would not survive a real server wait. COLD_DOC_DELAY_MS puts a realistic TTFB
      // back — applied to BOTH arms, so it is a shared constant, not a difference between them.
      const docDelay = parseInt(process.env.COLD_DOC_DELAY_MS || '0', 10);
      await page.route('**/*', async (route) => {
        if (route.request().resourceType() !== 'document') return route.continue();
        if (treated) blocked++;
        if (docDelay > 0) await new Promise((r) => setTimeout(r, docDelay));
        return route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body });
      });
    }
    // Belt and braces on top of the fresh profile: no HTTP cache at all.
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
    await page.addInitScript(LCP_HOOK);

    // 🔴 Resource Timing reports transferSize: 0 for every cross-origin response that lacks
    // Timing-Allow-Origin — which here is EVERY hero image (images.pexels.com) and EVERY API call
    // (api.bainluck.com). An in-page byte total therefore omits the largest thing on the page.
    // Count bytes off the wire instead, where CORS does not apply.
    // ⚠️ Do NOT use `content-length`: it is absent on every chunked response, and Playwright's
    // resp.body() fallback returns DECODED bytes, so scripts get counted uncompressed and the
    // total inflates past the raw size. `Network.loadingFinished.encodedDataLength` is the bytes
    // that crossed the wire — compressed, headers included, and unaffected by CORS.
    const wire = { total: 0, byHost: {}, byKind: {}, items: [] };
    const meta = new Map();
    const kindOf = (ct) => {
      if (/^image\//.test(ct || '')) return 'image';
      if (/javascript|ecmascript/.test(ct || '')) return 'script';
      if (/^text\/css/.test(ct || '')) return 'css';
      if (/font/.test(ct || '')) return 'font';
      if (/json/.test(ct || '')) return 'api/json';
      if (/^text\/html/.test(ct || '')) return 'html';
      return (ct || 'other').split(';')[0] || 'other';
    };
    await cdp.send('Network.enable');
    // A LAN-speed cold load cannot tell you whether a byte cut buys a millisecond — everything is
    // fast enough that bytes are free. Throttling is the only way to convert bytes to time, and it
    // is the condition most real readers are actually in.
    const PROFILES = {
      // download B/s, upload B/s, latency ms  — Chrome DevTools presets
      '4g': { downloadThroughput: 9 * 1024 * 1024 / 8, uploadThroughput: 1.5 * 1024 * 1024 / 8, latency: 170 },
      '3g': { downloadThroughput: 1.6 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8, latency: 300 },
    };
    const prof = PROFILES[(process.env.COLD_THROTTLE || '').toLowerCase()];
    if (prof) await cdp.send('Network.emulateNetworkConditions', { offline: false, ...prof });
    const cpu = parseFloat(process.env.COLD_CPU || '1');
    if (cpu > 1) await cdp.send('Emulation.setCPUThrottlingRate', { rate: cpu });
    cdp.on('Network.responseReceived', (e) => {
      meta.set(e.requestId, { url: e.response.url, kind: kindOf(e.response.mimeType) });
    });
    cdp.on('Network.loadingFinished', (e) => {
      const m0 = meta.get(e.requestId);
      if (!m0) return;
      const n = e.encodedDataLength || 0;
      let host = 'unknown';
      try { host = new URL(m0.url).host; } catch {}
      wire.total += n;
      wire.byHost[host] = (wire.byHost[host] || 0) + n;
      wire.byKind[m0.kind] = (wire.byKind[m0.kind] || 0) + n;
      wire.items.push({ url: m0.url, kind: m0.kind, bytes: n });
    });

    const t0 = Date.now();
    await page.goto(url, { waitUntil: 'load', timeout: 120000 });
    const tLoad = Date.now() - t0;
    // "finish" = the network goes quiet. This is the number a reader experiences as "done".
    let quiet = null;
    try {
      await page.waitForLoadState('networkidle', { timeout: 60000 });
      quiet = Date.now() - t0;
    } catch { quiet = null; /* never went quiet inside the window */ }

    const m = await page.evaluate(COLLECT);
    m.wallLoad = tLoad;
    m.wallNetworkIdle = quiet;
    m.wireAboveFold = JSON.parse(JSON.stringify(wire));

    // SECOND, SEPARATELY LABELLED number: what a reader who actually scrolls Discover pays.
    // Heroes below the fold are lazy — a 1280x900 cold load fetches almost none of them, so the
    // banked "~1.39 MB of hero raster per 40-card feed" is a SCROLL cost, not a cold-load cost.
    if (process.env.COLD_SCROLL === '1') {
      const tScroll = Date.now();
      for (let s = 0; s < 12; s++) {
        await page.mouse.wheel(0, 1400);
        await page.waitForTimeout(400);
      }
      try { await page.waitForLoadState('networkidle', { timeout: 30000 }); } catch {}
      m.wallAfterScroll = Date.now() - t0;
      m.scrollMs = Date.now() - tScroll;
      m.wireAfterScroll = JSON.parse(JSON.stringify(wire));
    }
    m.run = i + 1;
    m.arm = (ablate || rewrite) ? (treated ? 'treatment' : 'control') : 'single';
    m.blocked = blocked;
    // 🔴 A PAGE THAT RENDERED NOTHING STILL EMITS A PERFECTLY PLAUSIBLE FCP. Measured here: eight
    // consecutive runs reported FCP ~1,770ms with zero cards and zero probabilities on screen —
    // faster than the healthy runs, and completely meaningless. Averaging those in would have
    // reported the empty page as an improvement. A timing is only a timing if the page happened.
    m.valid = m.proof.cards > 0 && m.proof.pct > 0;
    if (!m.valid) console.error(`   ⚠️ run ${i + 1} INVALID — rendered no cards and no probabilities; excluded from medians`);
    results.push(m);
    console.error(`run ${i + 1}/${TOTAL} ${m.arm.padEnd(9)} blocked=${blocked}  ttfb=${Math.round(m.ttfb)}  fcp=${Math.round(m.fcp || 0)}  lcp=${Math.round(m.lcp || 0)}  dcl=${Math.round(m.dcl)}  load=${Math.round(m.load)}  cls=${(m.cls||0).toFixed(3)}  quiet=${quiet}  wire=${m.wireAboveFold.total}${m.wireAfterScroll ? `  wireScrolled=${m.wireAfterScroll.total}` : ''}  cards=${m.proof.cards}  pct=${m.proof.pct}`);
  } catch (e) {
    console.error(`run ${i + 1}/${RUNS} FAILED :: ${e.message}`);
    results.push({ run: i + 1, error: e.message });
  } finally {
    await browser.close();
  }
}

const ran = results.filter(r => !r.error);
const ok = ran.filter(r => r.valid);
if (!ok.length) { console.error('cold-load: no run produced a rendered page'); process.exit(1); }
if (ok.length < ran.length) console.error(`⚠️ ${ran.length - ok.length} of ${ran.length} runs rendered nothing and were DROPPED (not averaged)`);

const median = (xs) => {
  const s = xs.filter(x => typeof x === 'number' && isFinite(x)).sort((a, b) => a - b);
  if (!s.length) return null;
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const stats = (rows) => ({
  n: rows.length,
  ttfb: median(rows.map(r => r.ttfb)),
  fcp: median(rows.map(r => r.fcp)),
  lcp: median(rows.map(r => r.lcp)),
  dcl: median(rows.map(r => r.dcl)),
  load: median(rows.map(r => r.load)),
  cls: median(rows.map(r => r.cls)),
  networkIdle: median(rows.map(r => r.wallNetworkIdle)),
  resourceCount: median(rows.map(r => r.resourceCount)),
  wireBytesAboveFold: median(rows.map(r => r.wireAboveFold && r.wireAboveFold.total)),
  wireBytesAfterScroll: median(rows.map(r => r.wireAfterScroll && r.wireAfterScroll.total)),
});
const summary = {
  url, runs: RUNS, ok: ok.length,
  throttle: process.env.COLD_THROTTLE || 'none', cpuThrottle: process.env.COLD_CPU || '1',
  ablate: ablateName || 'none',
  median: stats(ok),
};
if (ablate || rewrite) {
  const c = stats(ok.filter(r => r.arm === 'control'));
  const t = stats(ok.filter(r => r.arm === 'treatment'));
  summary.arms = { control: c, treatment: t };
  summary.delta = Object.fromEntries(
    ['ttfb', 'fcp', 'lcp', 'dcl', 'load', 'networkIdle', 'wireBytesAboveFold']
      .map(k => [k, (c[k] != null && t[k] != null) ? +(t[k] - c[k]).toFixed(1) : null])
  );
}
console.log(JSON.stringify({ summary, results }, null, 2));
if (outJson) writeFileSync(outJson, JSON.stringify({ summary, results }, null, 2));
