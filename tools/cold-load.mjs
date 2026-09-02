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
// Reports THREE numbers, because two were not enough (alex-inbox/latency-020 §3):
//   usable  — first contentful paint / LCP / DOMContentLoaded: when the reader sees the page
//   finish  — load event and network-quiet: when the page stops working
//   ttfc    — TIME TO FIRST CARD: when the reader gets what they actually came for
//
// 🔴 ON DISCOVER, FCP IS THE WRONG NUMBER AND WILL MISLEAD YOU. The server HTML for `/` contains
// 12,441 B of markup, 444 chars of visible text, ZERO event anchors and ZERO percentages — nav
// chrome, tagline, footer. Every card is client-rendered. So FCP answers "when did the header
// appear", and a cut can improve FCP by 660 ms while making the first card 958 ms later (see the
// `scripts` delay arm below — that is a measured trade, not a hypothetical). `ttfc` watches the DOM
// for the first real card link; `ttfp` for the first probability. Grade this page on those.
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
// 🔴 `<-loopback>` REMOVES Chrome's implicit loopback bypass — it sends 127.0.0.1 THROUGH the
// proxy, which is the opposite of what the name reads like. Correct for a production URL (the
// sandbox proxy is the only egress) and fatal for a local `next start`: the proxy cannot reach this
// machine's ports, so every run 200s on 687 bytes and renders nothing. Measured exactly that way —
// ten runs, all INVALID, all "faster" than production. Keep the implicit bypass when either arm is
// local, so localhost is served directly and api.bainluck.com still goes out through the proxy.
const isLoopback = (u) => { try { const h = new URL(u).hostname; return h === 'localhost' || h === '127.0.0.1' || h === '[::1]'; } catch { return false; } };
if (proxy) {
  baseArgs.push(`--proxy-server=${proxy}`);
  if (!isLoopback(url) && !isLoopback(process.env.COLD_ALT_URL || '')) baseArgs.push('--proxy-bypass-list=<-loopback>');
}

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
  // The critical path in full, in request order — the only way to tell a resource that is STARVED
  // (starts early, finishes late) from one that is merely DISCOVERED LATE (starts late).
  const crit = res
    .filter(r => /\\.css(\\?|$)/.test(r.name) || /\\.woff2?(\\?|$)/.test(r.name) || /\\/api\\//.test(r.name)
                 || /webpack-|main-app-|\\/app\\/(page|layout)-/.test(r.name))
    .map(r => ({ n: r.name.split('/').pop().slice(0, 44), t: r.initiatorType,
                 start: Math.round(r.startTime), end: Math.round(r.responseEnd),
                 dur: Math.round(r.duration), enc: r.encodedBodySize || 0 }))
    .sort((a, b) => a.start - b.start);
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
    ttfc: window.__ttfc || null,
    ttfp: window.__ttfp || null,
    stage: window.__stage || null,
    cls: window.__cls || 0,
    resourceCount: res.length,
    resourceTransfer: res.reduce((a, r) => a + (r.transferSize || 0), 0),
    lastResourceEnd: res.reduce((a, r) => Math.max(a, r.responseEnd), 0),
    byType,
    crit,
    slowest,
    proof,
  };
})()`;

const LCP_HOOK = `
  // TIME TO FIRST CARD. FCP on Discover is the paint of the NAV CHROME — the server HTML carries
  // 444 chars of visible text and zero cards — so FCP answers "when did the header appear", not
  // "when did the reader get what they came for". Watch the DOM for the first real card.
  window.__ttfc = null; window.__ttfp = null;
  try {
    const CARD = 'a[href^="/futures/"], a[href^="/event/"], a[href^="/events/"]';
    const check = () => {
      if (window.__ttfc == null && document.querySelector(CARD)) window.__ttfc = performance.now();
      // textContent, NOT innerText: innerText forces a layout on every mutation, and this observer
      // fires hundreds of times during hydration. An instrument that reflows the page it is timing
      // is P202b all over again.
      if (window.__ttfp == null && /\\d+%/.test(document.body ? document.body.textContent : '')) window.__ttfp = performance.now();
      return window.__ttfc != null && window.__ttfp != null;
    };
    const mo = new MutationObserver(() => { if (check()) mo.disconnect(); });
    const start = () => { if (!check()) mo.observe(document.body, { childList: true, subtree: true }); };
    if (document.body) start();
    else document.addEventListener('DOMContentLoaded', start, { once: true });
  } catch (e) {}
  // Stage attribution: when did each class of critical-path resource finish, and when did the
  // client-side feed fetch actually happen. Cross-origin entries without Timing-Allow-Origin still
  // expose startTime/responseEnd (only the connect-phase fields and the size fields are redacted),
  // which is exactly what a timeline needs.
  window.__stage = { cssEnd: 0, scriptEnd: 0, feedStart: null, feedEnd: null, feedCount: 0 };
  try {
    new PerformanceObserver((l) => {
      for (const r of l.getEntries()) {
        if (r.initiatorType === 'link' && /\\.css(\\?|$)/.test(r.name)) window.__stage.cssEnd = Math.max(window.__stage.cssEnd, r.responseEnd);
        if (r.initiatorType === 'script') window.__stage.scriptEnd = Math.max(window.__stage.scriptEnd, r.responseEnd);
        if (/\\/api\\/feed/.test(r.name)) {
          window.__stage.feedCount++;
          if (window.__stage.feedStart == null || r.startTime < window.__stage.feedStart) window.__stage.feedStart = r.startTime;
          window.__stage.feedEnd = Math.max(window.__stage.feedEnd || 0, r.responseEnd);
        }
      }
    }).observe({ type: 'resource', buffered: true });
  } catch (e) {}
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
/**
 * Match on the PARSED url, never on the raw string.
 *
 * A bare `/images\.pexels\.com/.test(url)` also matches
 * `https://example.com/images.pexels.com/x.jpg` and
 * `https://images.pexels.com.example.com/x.jpg` — the host appearing anywhere in the string is not
 * the same claim as the host BEING that host. It is only a measurement rig, so the consequence here
 * is an arm that silently blocks the wrong thing rather than anything unsafe; but an ablation that
 * blocks the wrong requests reports a delta for a cut nobody proposed, which is the one failure
 * this whole file exists to avoid. (CodeQL js/regex/missing-regexp-anchor flagged exactly this.)
 */
const parts = (url) => {
  try {
    const u = new URL(url);
    return { host: u.hostname, path: u.pathname, search: u.search };
  } catch {
    return { host: '', path: '', search: '' };
  }
};

const ABLATIONS = {
  // Next.js App Router prefetch: RSC payloads for card destinations + the JS of nav routes the
  // reader has not opened. Everything here is speculative work for a navigation that may never come.
  prefetch: (url) => {
    const { path, search } = parts(url);
    return /[?&]_rsc=/.test(search) || /^\/_next\/static\/chunks\/app\/(sports|my-stuff|discover\/stats)\/page-/.test(path);
  },
  // The hero photographs, to size what imagery costs the critical path.
  images: (url) => parts(url).host === 'images.pexels.com',
  // The preloaded webfont. Not a shippable change by itself — this sizes the prize, so we know
  // whether subsetting / font-display / dropping a weight is worth a queue.
  font: (url) => /^\/_next\/static\/media\/[^/]+\.woff2?$/.test(parts(url).path),
};
// HTML-REWRITE ablations. Blocking a request tells you what the BYTES cost; it does not tell you
// what a config change would buy, because `preload: false` still downloads the font — it just
// discovers it later. Rewriting the document is the faithful simulation of that change.
const REWRITES = {
  // next/font's `preload: false`: drop the <link rel="preload"> for the woff2, keep everything else.
  // The font still loads, just off the earliest critical window.
  fontpreload: (html) => html.replace(/<link[^>]+rel="preload"[^>]*\.woff2?[^>]*>/g, ''),
  // 🔴 START THE FEED FETCH EARLIER — MEASURED, DEAD. Keep both arms: they are the evidence.
  //
  // The premise looked airtight. `components/discover/FeedBootScript.tsx` already exists to start
  // the anonymous reader's /api/feed fetch early, but it renders inside <body>, after three
  // render-blocking <link rel=stylesheet>, and a parser-inserted synchronous script cannot execute
  // until pending stylesheets have loaded. So the "early" fetch is not early: on production
  // feedStart tracks cssEnd to within ~25ms across two very different values (1978 vs 1948, and
  // 1213 vs 1209 under an unrelated script-delay arm) — same coupling at both, which is causation,
  // not coincidence.
  //
  // `feedbootpreload` is the only BUILDABLE shape of the cut, and it works exactly as designed:
  // the boot script cannot be hoisted above Next's stylesheets (Next owns head positions 0-6 —
  // charSet, viewport, the next/font preload, the three `data-precedence` CSS links — and anything
  // the root layout renders into <head> lands around position 27, still after the CSS), but a
  // <link rel=preload> does not need the parser at all: the HTML preload SCANNER runs ahead of the
  // blocked parser and fetches it from the first packet.
  //
  // 🔴 AND IT BOUGHT NOTHING. 3G/4x CPU, n=4+4 interleaved, all 8 runs valid:
  //     feedStart  1860 -> 398 ms   (-1463 — the scheduling change fully landed)
  //     ttfc       2746 -> 2716 ms  (-30)
  //     wire       +21,988 B        (the preload is never claimed, so the feed is fetched TWICE)
  // The feed payload sat parsed and waiting for ~1.8 s and the page still could not draw a card.
  // TIME TO FIRST CARD IS NOT GATED BY THE FEED FETCH. Confirmed from the other side: 3G with CPU
  // throttling 4x and 1x give ttfc 2509 vs 2508 ms, so it is not execution-bound either. What
  // remains is JS DOWNLOAD over a saturated pipe. Do not re-open "fetch the feed sooner" — it is
  // the cheapest-looking cut on this page and it is worth 30 ms.
  feedbootpreload: (html) => html.replace(
    '<script data-testid="feed-boot">',
    '<link rel="preload" as="fetch" crossorigin="anonymous" href="https://api.bainluck.com/api/feed?limit=20&event_pct=0.15"/><script data-testid="feed-boot">'
  ),
  // The unbuildable upper bound of the same idea, kept only to size the prize: move the script
  // itself above everything. Next 14 cannot emit this document — see the position note above.
  feedboothead: (html) => {
    const m = html.match(/<script data-testid="feed-boot">[\s\S]*?<\/script>/);
    if (!m) return html; // no match => the vacuous-arm guard rejects the run
    return html.replace(m[0], '').replace('<head>', '<head>' + m[0]);
  },
};
// DELAY ablations. Blocking answers "what do these bytes cost"; it cannot answer "what does their
// SCHEDULING cost", and it destroys the page, so every run trips the P202a validity guard and the
// arm has no rendered proof. Holding a request back instead keeps the page whole: the browser still
// fetches everything, just later, so the treatment arm renders and can be graded. This is the
// faithful simulation of deprioritising a class of request rather than deleting it.
const DELAYS = {
  // The async entry chunks. 313 kB of them share one H2 connection with 20 kB of render-blocking
  // CSS, and FCP cannot happen until that CSS lands.
  //
  // MEASURED (3G/4x CPU, n=5+5, COLD_DELAY_MS=1200): the CSS is STARVED, not discovered late.
  // Every critical resource is requested at ~712 ms, but the 17,452 B stylesheet does not finish
  // until 1945 ms because ~345 kB of concurrent script shares 200 kB/s. Holding the chunks back:
  //     cssEnd  1948 -> 1209 ms  (-738)      fcp  1984 -> 1324 ms  (-660)
  //     ttfc    2523 -> 3481 ms  (+958)
  // So FCP on Discover is bandwidth-contention, and it is ALSO the wrong number to chase: the
  // server HTML carries 444 chars of visible text and zero cards, so FCP is the paint of the nav
  // chrome. Buying 660 ms of chrome by costing 958 ms of the first card is a loss. Grade Discover
  // on `ttfc`, and treat this arm as a diagnostic, never as a proposal.
  scripts: (url) => /^\/_next\/static\/chunks\//.test(parts(url).path),
};
const DELAY_MS = parseInt(process.env.COLD_DELAY_MS || '1200', 10);
const ablateName = process.env.COLD_ABLATE || null;
const rewrite = ablateName ? REWRITES[ablateName] : null;
const delay = ablateName ? DELAYS[ablateName] : null;
const ablate = ablateName ? ABLATIONS[ablateName] : null;
if (ablateName && !ablate && !rewrite && !delay) { console.error(`unknown COLD_ABLATE=${ablateName}; known: ${[...Object.keys(ABLATIONS), ...Object.keys(REWRITES), ...Object.keys(DELAYS)]}`); process.exit(2); }

// TWO-BUILD A/B — grade a cut that is BUILT but not DEPLOYED.
//
// The ablation arms above simulate a cut by editing the live page. That is the right instrument
// while the cut is still a proposal, and the wrong one once the code exists: an ablation answers
// "what would removing these requests be worth", never "is this diff worth it". This lane cannot
// push, so without this arm every shipped cut is graded in BYTES and its milliseconds are somebody
// else's post-deploy problem — which is how eight cuts came to be certified on byte counts alone.
//
// COLD_ALT_URL points at a second origin, normally `next start` on two ports over two builds of
// two trees. Control loads `url`, treatment loads COLD_ALT_URL, interleaved A,B,A,B in ONE
// invocation on ONE machine, so machine load and API drift hit both arms equally. Two sequential
// invocations would not: a build is minutes of full-core compile, and the arm that runs after it
// inherits a hotter machine and a warmer server-side cache.
//
// ⚠️ The two origins MUST differ only by the diff under test. Same throttle, same viewport, same
// backing API — everything here is per-run, so that holds by construction; what it cannot check is
// that you built the right two trees.
// COLD_ARM_FILE is the SAME-ORIGIN form of the same A/B, and it exists because the two-origin form
// cannot always be used: the API's CORS allowlist names one local port, so two `next start`s on two
// ports produce two pages that fetch no feed, render no card, and are correctly thrown out by the
// validity guard. Instead both builds sit behind one switchable reverse proxy on the allowed port;
// the rig writes `control` / `treatment` into COLD_ARM_FILE before each navigation and the proxy
// reads it. Origin, CORS, port and document URL are then identical between arms by construction,
// and the only difference left is which build answered.
const altUrl = process.env.COLD_ALT_URL || null;
const armFile = process.env.COLD_ARM_FILE || null;
if ((altUrl || armFile) && (ablate || rewrite || delay)) {
  console.error('COLD_ALT_URL / COLD_ARM_FILE cannot be combined with COLD_ABLATE: both claim the treatment arm');
  process.exit(2);
}
if (altUrl && armFile) { console.error('COLD_ALT_URL and COLD_ARM_FILE are two spellings of one arm; pick one'); process.exit(2); }

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
const TOTAL = (ablate || rewrite || delay || altUrl || armFile) ? RUNS * 2 : RUNS;
for (let i = 0; i < TOTAL; i++) {
  // Interleave: even = control, odd = treatment. Never all-of-one-then-all-of-the-other.
  const treated = (ablate || rewrite || delay || altUrl || armFile) ? (i % 2 === 1) : false;
  const target = treated && altUrl ? altUrl : url;
  // Flip the upstream BEFORE the browser launches, so the very first byte of the run is the
  // arm's own build. Written every run, including the control, so a stale file from a killed
  // run cannot silently make both arms the same build.
  if (armFile) writeFileSync(armFile, treated ? 'treatment' : 'control');
  if (i > 0 && PACE_MS > 0) await new Promise((r) => setTimeout(r, PACE_MS));
  const browser = await chromium.launch({ args: baseArgs });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    let blocked = 0, delayed = 0;
    if (treated && ablate) {
      await page.route('**/*', (route) => {
        const u = route.request().url();
        if (ablate(u)) { blocked++; return route.abort(); }
        return route.continue();
      });
    }
    if (treated && delay) {
      await page.route('**/*', async (route) => {
        if (!delay(route.request().url())) return route.continue();
        delayed++;
        await new Promise((r) => setTimeout(r, DELAY_MS));
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
    await page.goto(target, { waitUntil: 'load', timeout: 120000 });
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
    m.arm = (ablate || rewrite || delay || altUrl || armFile) ? (treated ? 'treatment' : 'control') : 'single';
    m.url = target;
    m.blocked = blocked;
    m.delayed = delayed;
    // 🔴 A PAGE THAT RENDERED NOTHING STILL EMITS A PERFECTLY PLAUSIBLE FCP. Measured here: eight
    // consecutive runs reported FCP ~1,770ms with zero cards and zero probabilities on screen —
    // faster than the healthy runs, and completely meaningless. Averaging those in would have
    // reported the empty page as an improvement. A timing is only a timing if the page happened.
    m.valid = m.proof.cards > 0 && m.proof.pct > 0;
    if (!m.valid) console.error(`   ⚠️ run ${i + 1} INVALID — rendered no cards and no probabilities; excluded from medians`);
    results.push(m);
    console.error(`run ${i + 1}/${TOTAL} ${m.arm.padEnd(9)} blocked=${blocked}${delayed ? ` delayed=${delayed}` : ''}  ttfb=${Math.round(m.ttfb)}  fcp=${Math.round(m.fcp || 0)}  ttfc=${m.ttfc ? Math.round(m.ttfc) : "NONE"}  lcp=${Math.round(m.lcp || 0)}  dcl=${Math.round(m.dcl)}  load=${Math.round(m.load)}  cls=${(m.cls||0).toFixed(3)}  quiet=${quiet}  wire=${m.wireAboveFold.total}${m.wireAfterScroll ? `  wireScrolled=${m.wireAfterScroll.total}` : ''}  cards=${m.proof.cards}  pct=${m.proof.pct}`);
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
  ttfc: median(rows.map(r => r.ttfc)),
  ttfp: median(rows.map(r => r.ttfp)),
  cssEnd: median(rows.map(r => r.stage && r.stage.cssEnd)),
  scriptEnd: median(rows.map(r => r.stage && r.stage.scriptEnd)),
  feedStart: median(rows.map(r => r.stage && r.stage.feedStart)),
  feedEnd: median(rows.map(r => r.stage && r.stage.feedEnd)),
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
  altUrl: altUrl || null,
  armFile: armFile || null,
  median: stats(ok),
};
if (ablate || rewrite || delay || altUrl || armFile) {
  const c = stats(ok.filter(r => r.arm === 'control'));
  const t = stats(ok.filter(r => r.arm === 'treatment'));
  // A treatment arm that touched nothing is the same silent vacuous arm the REWRITE guard above
  // catches at document level: the A/B compares the page to itself and reports "no effect" for a
  // cut that was never applied. A block/delay predicate that matches no request is exactly that,
  // so it fails loudly here rather than being written up as a kill.
  if ((ablate || delay) && !ok.some(r => r.arm === 'treatment' && (r.blocked || r.delayed))) {
    console.error(`ABLATION '${ablateName}' MATCHED NO REQUEST in any treatment run — vacuous arm`);
    process.exit(1);
  }
  summary.arms = { control: c, treatment: t };
  summary.delta = Object.fromEntries(
    ['ttfb', 'fcp', 'ttfc', 'ttfp', 'cssEnd', 'scriptEnd', 'feedStart', 'feedEnd', 'lcp', 'dcl', 'load', 'networkIdle', 'wireBytesAboveFold']
      .map(k => [k, (c[k] != null && t[k] != null) ? +(t[k] - c[k]).toFixed(1) : null])
  );
}
console.log(JSON.stringify({ summary, results }, null, 2));
if (outJson) writeFileSync(outJson, JSON.stringify({ summary, results }, null, 2));
