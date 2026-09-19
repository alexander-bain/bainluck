// ux1354-all-tab-axis-runs-forward-7161.mjs <baseUrl> <eventId> [out.png]
//
// #7161 — DOES THE "All" TAB'S X-AXIS RUN FORWARDS, AND IS THE GAME THE INK?
//
// On a FINISHED game, `computeSharedChartDomain` caps the "All" window to two
// hours before kick-off and builds the ticks and the `h:mm a` label format on
// THAT window — but `OddsChart` never clipped `chartData` to it. On
// /events/14638896 the served series reach back to 2026-05-12: 4,017 of 4,607
// `aggregate_line` points (87%) fall before the day of the game. So the
// categorical XAxis carried four months of categories under a format that is
// only unique inside twelve hours, each tick string matched the FIRST category
// bearing it, and the axis rendered `7:00 PM` at x=77 with `3:15 PM` at x=312 —
// a reader is told the game ran backwards.
//
// TWO ARMS, DELIBERATELY NOT THE SAME FACT.
//   A — the reader's complaint: tick times must ascend with tick x.
//   B — the harm underneath it: the pre-window slab. The drawn line opens with
//       a long flat run (months of pre-season drift crushed into the left of a
//       390px chart) and the actual game is a spike at the right edge. A tab
//       whose labels were merely re-sorted would pass A and still fail B.
//
// 🔴 ANCHORED ON WHAT THE REPAIR DOES NOT TOUCH. Both arms read Recharts'
// own output — `.recharts-xAxis` tick `<text>` and the line `path`'s `d` — which
// the unfixed production page draws exactly as the fixed one will. A probe keyed
// on markup the fix introduces cannot measure the build whose defect it exists
// to bank (ux/1351's lesson).
//
// EXIT CODES ARE A STORY (gotcha #124):
//   0  both arms pass — the axis ascends and the game is the ink
//   3  an arm FAILED — the defect, live
//   4  fewer than 2 ticks, or no line path = NOTHING WAS CHECKED, not a pass
//   5  the "All" tab is absent or disabled
//   2  usage · 1 camera/navigation
import { createRequire } from 'module';
import { existsSync, readdirSync } from 'fs';

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

const [base, eventId, out] = process.argv.slice(2);
if (!base || !eventId) {
  console.error('usage: node ux1354-all-tab-axis-runs-forward-7161.mjs <baseUrl> <eventId> [out.png]');
  process.exit(2);
}
const URL = `${base.replace(/\/$/, '')}/events/${eventId}`;

/**
 * Which chart a Recharts wrapper belongs to, by the nearest heading ABOVE it.
 *
 * The first attempt read `wrapper.parentElement.textContent`, which on this page
 * is the plot container and holds no heading at all — every axis came back
 * `axis 0` / `axis 1` and the grader fell through to DOM order. Grading the
 * right chart by position is luck; this walks up until a section containing one
 * of the two headings is found, and prefers the LAST heading at or before the
 * wrapper so a section holding both cannot mislabel the second.
 */
const NAME_CHART = () => {
  window.__blNameChart = (wrapper) => {
    if (!wrapper) return null;
    const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,[class*="heading"]'))
      .map((h) => ({ el: h, text: (h.textContent || '').trim() }))
      .filter((h) => /^(Win Probability|Score Differential)/.test(h.text));
    let best = null;
    for (const h of headings) {
      const pos = h.el.compareDocumentPosition(wrapper);
      // wrapper FOLLOWS the heading in document order
      if (pos & Node.DOCUMENT_POSITION_FOLLOWING) best = h;
    }
    return best ? best.text.match(/Win Probability|Score Differential/)[0] : null;
  };
};

/**
 * Tick text + rendered x, GROUPED BY AXIS.
 *
 * 🔴 The event page draws two Recharts charts — Win Probability and Score
 * Differential — and a flat `.recharts-xAxis … text` query interleaves both in
 * DOM order. The first run of this probe reported an inversion built out of one
 * tick from each chart: a fact about the selector, not about either axis. Each
 * axis is ordered against itself, and the chart is named so a reader of the
 * output knows which one moved.
 */
const READ_TICKS = () =>
  Array.from(document.querySelectorAll('.recharts-xAxis')).map((axis, i) => {
    return {
      chart: window.__blNameChart(axis.closest('.recharts-wrapper')) ?? `axis ${i}`,
      ticks: Array.from(axis.querySelectorAll('.recharts-cartesian-axis-tick text'))
        .map((t) => ({ label: (t.textContent || '').trim(), x: t.getBBox ? t.getBBox().x : NaN }))
        .filter((t) => t.label.length > 0),
    };
  });

/**
 * The longest run of near-constant y at the LEFT of the drawn line, as a
 * fraction of the line's own x-extent. The densest line path is the one the
 * chart is about; a sparse marker path is not.
 */
const READ_LEADING_FLAT = () => {
  // Scoped to the Win Probability chart for the same reason the ticks are: the
  // Score Differential chart below it already clips to the shared domain, so
  // measuring "the densest path on the page" could grade the wrong subject.
  const wrapper = Array.from(document.querySelectorAll('.recharts-wrapper')).find(
    (w) => window.__blNameChart(w) === 'Win Probability',
  );
  const scope = wrapper ?? document;
  const paths = Array.from(scope.querySelectorAll('path.recharts-line-curve, path.recharts-curve'))
    .map((p) => p.getAttribute('d') || '')
    .filter((d) => d.length > 0);
  if (paths.length === 0) return null;
  const parse = (d) => {
    const pts = [];
    const re = /[ML]\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)/g;
    let m;
    while ((m = re.exec(d)) !== null) pts.push({ x: parseFloat(m[1]), y: parseFloat(m[2]) });
    return pts;
  };
  let best = [];
  for (const d of paths) {
    const pts = parse(d);
    if (pts.length > best.length) best = pts;
  }
  if (best.length < 10) return null;
  const xs = best.map((p) => p.x);
  const ys = best.map((p) => p.y);
  const span = Math.max(...xs) - Math.min(...xs);
  const yRange = Math.max(...ys) - Math.min(...ys);
  if (span <= 0 || yRange <= 0) return { points: best.length, span, yRange, flatFraction: null };
  // "Flat" is relative to the line's own vertical travel: a band of 8% of the
  // range. A pre-season slab sits inside that band for months; a live game
  // leaves it within minutes.
  const band = yRange * 0.08;
  const y0 = best[0].y;
  let i = 0;
  while (i < best.length && Math.abs(best[i].y - y0) <= band) i++;
  const flatUntilX = best[Math.max(0, i - 1)].x;
  return {
    points: best.length,
    span,
    yRange,
    flatFraction: (flatUntilX - Math.min(...xs)) / span,
  };
};

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const launchArgs = [
  '--no-sandbox',
  '--single-process',
  '--disable-gpu',
  '--disable-crashpad',
  '--disable-dev-shm-usage',
];
if (proxy) {
  launchArgs.push(`--proxy-server=${proxy}`);
  // ux/1353 trap 2: `<-loopback>` REMOVES Chrome's implicit loopback bypass, so a
  // local `next start` goes through the session proxy, answers TLS-error, and the
  // probe reports "nothing found" — a fact about the camera dressed as a fact
  // about the page. Name the loopback hosts instead; api.bainluck.com still goes
  // through the proxy, and the production run is unaffected.
  launchArgs.push('--proxy-bypass-list=localhost;127.0.0.1');
}

(async () => {
  const browser = await chromium.launch({ args: launchArgs });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  try {
    await page.goto(URL, { waitUntil: 'networkidle', timeout: 90000 });
  } catch (e) {
    console.error(`navigation failed: ${e.message}`);
    await browser.close();
    process.exit(1);
  }
  await page.waitForTimeout(4000);

  // The consent banner sits over the bottom third of the chart at 390px, which
  // is exactly the band the drawn line occupies on a finished game. It changes
  // no measurement below — `getBBox` does not care what is painted on top — but
  // it hides the half of the frame a human is asked to judge, so both the BEFORE
  // and the AFTER are taken with it dismissed, by the same instrument.
  const consent = await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /^(Accept|Decline|Got it|OK)$/i.test((b.textContent || '').trim()),
    );
    if (!btn) return '(no banner)';
    btn.click();
    return `dismissed via "${btn.textContent.trim()}"`;
  });
  console.log(`consent banner: ${consent}`);
  await page.waitForTimeout(800);

  const tapped = await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('button')).filter(
      (b) => (b.textContent || '').trim() === 'All' && !b.disabled,
    );
    if (all.length === 0) return false;
    all[0].click();
    return true;
  });
  if (!tapped) {
    console.error('the "All" tab is absent or disabled — nothing to compare');
    await browser.close();
    process.exit(5);
  }
  await page.waitForTimeout(4000);

  await page.evaluate(NAME_CHART);
  const axes = await page.evaluate(READ_TICKS);
  const ink = await page.evaluate(READ_LEADING_FLAT);

  if (out) {
    await page.screenshot({ path: out });
    console.log(`shot: ${out}`);
  }
  await browser.close();

  // Parse `h:mm a` (and the date-qualified form) to minutes; a window that
  // legitimately crosses noon is exactly what the date-qualified label format
  // exists to express, so such an axis is read on its day first.
  const toMinutes = (label) => {
    const m = label.match(/(?:([A-Za-z]{3})\s+)?(\d{1,2}):(\d{2})\s*(AM|PM)/i);
    if (!m) return null;
    let h = parseInt(m[2], 10) % 12;
    if (/pm/i.test(m[4])) h += 12;
    const day = m[1] ? ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(m[1]) : 0;
    return (day < 0 ? 0 : day) * 1440 + h * 60 + parseInt(m[3], 10);
  };

  const gradeAxis = (axis) => {
    const parsed = axis.ticks.map((t) => ({ ...t, min: toMinutes(t.label) }));
    const byX = parsed.filter((t) => t.min !== null).sort((a, b) => a.x - b.x);
    const inversions = [];
    for (let i = 1; i < byX.length; i++) {
      if (byX[i].min <= byX[i - 1].min) {
        inversions.push(
          `"${byX[i - 1].label}" (x=${Math.round(byX[i - 1].x)}) then "${byX[i].label}" (x=${Math.round(byX[i].x)})`,
        );
      }
    }
    return { ...axis, ordered: byX, unparsed: parsed.filter((t) => t.min === null), inversions };
  };

  const graded = axes.map(gradeAxis);
  for (const a of graded) {
    console.log(`${a.chart} — ${a.ticks.length} tick(s), left to right:`);
    for (const t of [...a.ticks].sort((p, q) => p.x - q.x)) {
      console.log(`  ${String(Math.round(t.x)).padStart(4)}  ${t.label}`);
    }
    if (a.unparsed.length > 0) {
      console.log(`  (${a.unparsed.length} not time-shaped, not ordered: ${a.unparsed.map((t) => t.label).join(', ')})`);
    }
  }

  // #7161 is the Win Probability chart. The Score Differential axis is printed
  // above as context — it already clips to the shared domain — and is not graded
  // here, so a defect of its own can never be laundered into this verdict.
  let subject = graded.find((a) => /Win Probability/.test(a.chart));
  if (!subject) {
    // Falling through to DOM order here is how a probe grades the wrong chart
    // and calls it a pass. With one axis there is nothing to confuse; with more,
    // an unnamed subject means the page changed shape and NOTHING was checked.
    if (graded.length === 1) subject = graded[0];
    else {
      console.error(
        `COULD NOT NAME THE WIN PROBABILITY AXIS among ${graded.length} axes — nothing was checked (this is not a pass)`,
      );
      process.exit(4);
    }
  }
  if (subject.ordered.length < 2) {
    console.error('FEWER THAN 2 TIME-SHAPED TICKS ON THE WIN PROBABILITY AXIS — nothing was checked (this is not a pass)');
    process.exit(4);
  }
  if (!ink || ink.flatFraction === null) {
    console.error('NO LINE PATH TO MEASURE — nothing was checked (this is not a pass)');
    process.exit(4);
  }
  const armA = subject.inversions.length === 0;
  const inversions = subject.inversions;

  // ARM B. Below half the width is the bar: the measured defect is 0.8+.
  const FLAT_BAR = 0.5;
  const armB = ink.flatFraction < FLAT_BAR;

  console.log(`ARM A axis order   : ${armA ? 'ASCENDING' : 'OUT OF ORDER'}`);
  if (!armA) for (const inv of inversions) console.log(`    inversion: ${inv}`);
  console.log(
    `ARM B leading flat : ${(ink.flatFraction * 100).toFixed(1)}% of the line's width ` +
      `(${ink.points} pts, y-range ${ink.yRange.toFixed(1)}px) — bar is <${FLAT_BAR * 100}%`,
  );

  if (armA && armB) {
    console.log('BOTH ARMS PASS: the axis ascends and the game is the ink');
    process.exit(0);
  }
  console.error(`ARM ${!armA ? 'A' : ''}${!armA && !armB ? ' and ' : ''}${!armB ? 'B' : ''} FAILED — #7161 is live`);
  process.exit(3);
})();
