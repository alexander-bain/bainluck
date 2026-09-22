// period-marker-position-7901.mjs — read WHERE each period rule is painted, and
// invert the axis to say what instant the chart put it at.
//
// #7901: the first period marker of a late-starting MLB game stood 47 minutes to
// the left of its served timestamp, at `commence_time` exactly, while every other
// marker on the same plot stood in the right place. `period-labels-7876.mjs`
// cannot see this: it reads WHICH labels survive and their caption boxes, and a
// label drawn at the wrong instant is present, correctly named and correctly
// spelled.
//
// 🪤 THE CAPTION IS NOT THE RULE. A period label is anchored `insideTopLeft` or
// `insideTopRight` (#7371), so its text box sits several px to one side of the
// line it names, and `insideTopRight` puts it on the OTHER side. Reading caption
// x as marker x is a 5–25px error that changes sign per marker — larger than some
// of the gaps this is meant to resolve. This reads the `<line>` element of each
// reference-line group and uses the caption only to name it.
//
// The inversion is the axis's own ticks, not a computed scale: two ticks with
// known instants give px→ms, and every other tick is then a CONTROL on that fit
// (`residual` below). The axis is categorical over minute buckets that
// `fillMinuteGaps` guarantees are complete, so time is linear in px — if a
// control tick shows a large residual, that assumption has broken and no marker
// reading from this run means anything.
//
// The browser is pinned to UTC so tick captions are directly comparable to the
// API's timestamps. Without it the captions come out in the laptop's zone, which
// is not the zone anyone reading this output is thinking in (notice 24).
//
// MEASURED with this tool on 15316297, production `e37fb7dc6` vs a local build
// carrying #7901, two minutes apart:
//
//   BEFORE  rule "T1" x=100.0 -> 22:34:59Z  commence-0.0m   (served 23:22:33Z, -47.6m)
//   AFTER   rule "T1" x=158.3 -> 23:21:59Z  commence+47.0m  (served 23:22:33Z,  -0.6m)
//
// -0.6m is the minute-bucket floor every marker shows on both arms, not an error.
//
// Usage: node period-marker-position-7901.mjs <baseUrl> <eventId> <outDir> [tag]
// Exit:  0 read · 2 bad usage · 4 no chart on the page · 5 axis fit unusable
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
  console.error('usage: period-marker-position-7901.mjs <baseUrl> <eventId> <outDir> [tag]');
  process.exit(2);
}
mkdirSync(outDir, { recursive: true });

const PAGE_URL = `${baseUrl.replace(/\/$/, '')}/events/${eventId}`;
const API_URL = `https://api.bainluck.com/api/events/${eventId}/history`;

// Is the page itself served from this machine? Asked of the parsed HOST, never
// of the URL as a string — an unanchored `/localhost/` also matches
// `https://bainluck.com/localhost` and would withhold the proxy bypass on a
// production run (`js/regex/missing-regexp-anchor`, and ux/1429 shipped the
// same trap twice). `globalThis.URL` because a module-level `const URL` in a
// sibling tool shadowed the constructor file-wide and its own catch ate the
// TypeError.
function isLoopbackBase(url) {
  let host;
  try {
    host = new globalThis.URL(url).hostname;
  } catch {
    return false;
  }
  return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]';
}
const LOCAL_PAGE = isLoopbackBase(baseUrl);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!LOCAL_PAGE) args.push('--proxy-bypass-list=<-loopback>');
}

/** The served markers, so the drawing can be compared against its own input. */
async function servedMarkers() {
  const { stdout } = await execFileAsync(
    'curl',
    ['-s', '--max-time', '60', '-H', `x-bainluck-origin: ${process.env.BL_AGENT || 'ux'}`, API_URL],
    { maxBuffer: 256 * 1024 * 1024 },
  );
  const d = JSON.parse(stdout);
  return {
    commenceMs: d.commence_time ? Date.parse(d.commence_time) : null,
    domainStartMs: d.time_domain?.start ? Date.parse(d.time_domain.start) : null,
    markers: (d.period_markers || []).map((m) => ({
      ms: Date.parse(m.timestamp),
      period: m.period,
      source: m.source,
    })),
  };
}

const served = await servedMarkers();

const browser = await chromium.launch({ headless: true, args });
// UTC so a tick caption reads as the same instant the API printed.
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
  timezoneId: 'UTC',
});
const page = await context.newPage();

if (LOCAL_PAGE) {
  await page.route((u) => {
    try {
      return new globalThis.URL(u).hostname === 'api.bainluck.com';
    } catch {
      return false;
    }
  }, async (route) => {
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
      // Abort rather than fulfil an empty 200: a blank body renders a chartless
      // page, which reads as "the change broke it" (gotcha #53).
      await route.abort();
    }
  });
}

await page.goto(PAGE_URL, { waitUntil: 'domcontentloaded', timeout: 90000 });
try {
  await page.waitForSelector('.recharts-wrapper', { timeout: 45000 });
} catch {
  console.error('no .recharts-wrapper on the page');
}
// 🪤 THE CONSENT CARD SITS ON THE CHART, AND THE POINTER DRAWS A TOOLTIP OVER
// IT. Both of the first two runs produced an unreadable frame for a different
// reason: the before shot had "We value your privacy" covering the plot, and the
// after shot had the hover tooltip covering it — a chart tooltip is 300–480px
// tall at 390px (#7848), so it hides most of what is being photographed. A
// screenshot nobody can read is not a LOOK, and both were saved with exit 0.
try {
  const b = page
    .locator('button, [role="button"]', { hasText: /^\s*(Accept|Accept all|Agree)\s*$/i })
    .first();
  if (await b.count()) {
    await b.click({ timeout: 4000 });
    await page.waitForTimeout(600);
  }
} catch { /* already accepted, or no banner on this build */ }
// Park the pointer off the plot so no tooltip is open when the shutter fires.
await page.mouse.move(2, 2);
await page.waitForTimeout(2000);

const read = await page.evaluate(() => {
  const out = [];
  // Keyed on `data-period-label-rows`, which every build carries — keying on a
  // channel that ships with a fix makes the before arm report "no chart".
  for (const el of document.querySelectorAll('[data-period-label-rows]')) {
    const wrapper = el.querySelector('.recharts-wrapper');
    if (!wrapper) continue;

    // Axis ticks: caption text plus the x of the tick's own line, which is the
    // instant the axis is claiming — the text is centred under it and can be
    // shifted at the edges to stay inside the svg.
    const ticks = [...wrapper.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick')]
      .map((g) => {
        const t = g.querySelector('text');
        const ln = g.querySelector('line');
        const box = (ln || t)?.getBoundingClientRect();
        return t && box ? { text: t.textContent.trim(), x: box.x + box.width / 2 } : null;
      })
      .filter(Boolean);

    // Reference rules: the LINE is the marker; the text only names it.
    const rules = [...wrapper.querySelectorAll('.recharts-reference-line')].map((g) => {
      const ln = g.querySelector('line');
      const t = g.querySelector('text');
      const lb = ln?.getBoundingClientRect();
      return {
        label: t ? t.textContent.trim() : '',
        x: lb ? lb.x + lb.width / 2 : null,
        vertical: lb ? lb.height > lb.width : null,
        dashed: ln ? (ln.getAttribute('stroke-dasharray') || '') : '',
      };
    });

    out.push({
      // #7901's channel: the instants handed to recharts. Absent on a pre-fix
      // build, which is a READING and not a failure — say so, never crash.
      times: el.getAttribute('data-period-times'),
      drawnExtent: el.getAttribute('data-drawn-extent') || '',
      labels: el.getAttribute('data-period-labels') ?? '(channel absent)',
      count: el.getAttribute('data-period-boundaries'),
      ticks,
      rules,
    });
  }
  return out;
});

// Verify the shutter fired on a readable frame rather than on a card: an open
// tooltip or a consent banner over the plot is the difference between evidence
// and a saved PNG (D48 — "a saved image is not inspection").
const obscured = await page.evaluate(() => {
  const tip = document.querySelector('.recharts-tooltip-wrapper');
  const tipOpen = !!tip && getComputedStyle(tip).visibility !== 'hidden' && tip.getBoundingClientRect().height > 0;
  const consent = [...document.querySelectorAll('button, [role="button"]')]
    .some((b) => /^\s*(Accept|Accept all|Agree)\s*$/i.test(b.textContent || ''));
  return { tipOpen, consent };
});
if (obscured.tipOpen || obscured.consent) {
  console.error(
    `WARNING: the frame is obscured (tooltip=${obscured.tipOpen} consent-banner=${obscured.consent}) — ` +
    'the numbers above are still good, the PNG is not a LOOK',
  );
}
await page.screenshot({ path: `${outDir}/${tag}-full.png`, fullPage: true });

if (read.length === 0) {
  console.error('page reported no period channel at all');
  await browser.close();
  process.exit(4);
}

/**
 * Resolve a tick caption ("11:22 PM", "Tue 11:22 PM", "Sep 21 11:22 PM") to the
 * instant nearest `anchorMs`. The axis prints no year and, in the short format,
 * no date — so the caption alone is ambiguous by a day, and the chart's own
 * domain is what disambiguates it.
 */
function tickToMs(text, anchorMs) {
  const m = text.match(/(\d{1,2}):(\d{2})\s*(AM|PM)/i);
  if (!m) return null;
  let h = parseInt(m[1], 10) % 12;
  if (/PM/i.test(m[3])) h += 12;
  const min = parseInt(m[2], 10);
  const a = new Date(anchorMs);
  const base = Date.UTC(a.getUTCFullYear(), a.getUTCMonth(), a.getUTCDate(), h, min, 0, 0);
  let best = base;
  for (const d of [-2, -1, 0, 1, 2]) {
    const c = base + d * 86400000;
    if (Math.abs(c - anchorMs) < Math.abs(best - anchorMs)) best = c;
  }
  return best;
}

const anchor = served.domainStartMs ?? served.commenceMs ?? Date.now();
const iso0 = (ms) => new Date(ms).toISOString().replace('T', ' ').slice(0, 19) + 'Z';
const report = [];

read.forEach((chart, i) => {
  const ticks = chart.ticks
    .map((t) => ({ ...t, ms: tickToMs(t.text, anchor) }))
    .filter((t) => t.ms != null)
    .sort((a, b) => a.x - b.x);

  const lines = [];
  lines.push(`chart ${i}: labels=[${chart.labels}] boundaries=${chart.count} ticks=${ticks.length}`);
  lines.push(`          drawn-extent=${chart.drawnExtent}`);

  if (ticks.length < 2) {
    lines.push('          AXIS FIT UNUSABLE: fewer than two readable ticks');
    report.push({ chart: i, usable: false, lines });
    return;
  }

  // 🪤 THE FIRST AND LAST TICK ARE NOT ON THE FIT, AND FITTING ON THEM INDICTS A
  // LINEAR AXIS. Recharts shifts an edge tick's caption INWARD to keep it inside
  // the svg, and when the axis draws no tick marks the only box to measure is
  // that caption. The first cut of this tool fitted on the two extreme ticks and
  // reported "worst residual 286s — NON-LINEAR AXIS, readings not trustworthy"
  // on an axis whose three interior ticks were spaced 74.5px/hour to within a
  // pixel. It was about to discard a correct reading of a real defect.
  //
  // So the fit uses interior ticks when there are enough of them, and the edges
  // become controls rather than anchors — the reverse of the first version.
  const inner = ticks.length >= 4 ? ticks.slice(1, -1) : ticks;
  const a = inner[0];
  const b = inner[inner.length - 1];
  if (b.x === a.x || b.ms === a.ms) {
    lines.push('          AXIS FIT UNUSABLE: fit ticks coincide');
    report.push({ chart: i, usable: false, lines });
    return;
  }
  const msPerPx = (b.ms - a.ms) / (b.x - a.x);
  const pxToMs = (x) => a.ms + (x - a.x) * msPerPx;

  const controls = ticks.filter((t) => t !== a && t !== b);
  const residuals = controls.map((t) => Math.round((pxToMs(t.x) - t.ms) / 1000));
  const interiorControls = controls.filter((t) => t !== ticks[0] && t !== ticks[ticks.length - 1]);
  const interiorWorst = interiorControls.length
    ? Math.max(...interiorControls.map((t) => Math.abs(Math.round((pxToMs(t.x) - t.ms) / 1000))))
    : 0;
  lines.push(
    `          fit: ${(msPerPx / 60000).toFixed(3)} min/px on ${inner.length} interior ticks` +
    ` · controls ${residuals.map((r) => `${r}s`).join(',') || 'none'}` +
    ` · worst INTERIOR residual ${interiorWorst}s` +
    (interiorWorst > 120 ? '  <-- NON-LINEAR AXIS, readings below are not trustworthy' : ''),
  );
  if (chart.times) {
    // #7901's own channel: the instants the component handed recharts. The
    // inversion above says where the rule was PAINTED; this says what it was
    // ASKED for. They answer different questions and a disagreement between
    // them is a recharts placement failure, which is worth seeing separately.
    const asked = chart.times.split(',').filter(Boolean).map(Number);
    lines.push(`          data-period-times: ${asked.map((t) => iso0(t)).join(' ') || '(none)'}`);
  } else {
    lines.push('          data-period-times: (channel absent — pre-#7901 build)');
  }

  const iso = (ms) => new Date(ms).toISOString().replace('T', ' ').slice(0, 19) + 'Z';

  const verticalRules = chart.rules.filter((r) => r.vertical && r.x != null);
  for (const r of verticalRules) {
    const drawnMs = pxToMs(r.x);
    // Name the served marker this rule most plausibly is: the nearest one. That
    // is only a LABEL for the row — the error it reports is measured against
    // that nearest marker, so a genuinely misplaced rule reports the distance to
    // whatever it should have been closest to, which is the conservative read.
    let near = null;
    for (const m of served.markers) {
      if (!near || Math.abs(m.ms - drawnMs) < Math.abs(near.ms - drawnMs)) near = m;
    }
    const errMin = near ? (drawnMs - near.ms) / 60000 : null;
    const toCommence = served.commenceMs ? (drawnMs - served.commenceMs) / 60000 : null;
    lines.push(
      `          rule "${r.label || '(no caption)'}" x=${r.x.toFixed(1)} -> ${iso(drawnMs)}` +
      (near ? ` | nearest served ${iso(near.ms)} "${near.period}" (${errMin >= 0 ? '+' : ''}${errMin.toFixed(1)}m)` : '') +
      (toCommence != null ? ` | commence${toCommence >= 0 ? '+' : ''}${toCommence.toFixed(1)}m` : ''),
    );
  }
  report.push({ chart: i, usable: interiorWorst <= 120, lines });
});

const text = report.flatMap((r) => r.lines).join('\n');
console.log(text);
console.log(`\nserved markers (${served.markers.length}), commence ${new Date(served.commenceMs).toISOString()}:`);
for (const m of served.markers.slice(0, 40)) {
  console.log(`  ${new Date(m.ms).toISOString()}  ${m.period}  [${m.source}]`);
}

writeFileSync(`${outDir}/${tag}-positions.json`, JSON.stringify({ served, read, when: new Date().toISOString() }, null, 2));
await browser.close();
process.exit(report.some((r) => !r.usable) ? 5 : 0);
