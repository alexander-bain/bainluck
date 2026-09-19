// ux1352-chart-ends-at-the-whistle-6987.mjs <baseUrl> <eventId> [out.png]
//
// #6987 — DO THE TWO RANGE TABS LABEL THE SAME ENDING?
//
// On a FINAL game the Win Probability chart's end-callout read `100%` under
// "Since Start" and `>99%` under "All". Not one number served two ways: the end
// cutoff (`smartEndTime`) was applied only in the "Since Start" arm, so "All"
// drew ten more minutes of prediction-market quotes taken after the whistle and
// anchored its callout on the last of them. This probe taps between the two
// tabs and reads the string a reader sees each time.
//
// 🔴 IT IS ANCHORED ON THE READER'S GLYPHS, NOT ON THE FIX'S OWN MARKUP.
// ux/1351's second lesson, inverted: the fix adds `data-callout-label` to the
// chart wrapper, and a probe keyed on THAT could never measure the unfixed
// production page — it would report "attribute missing" on exactly the build
// whose defect it exists to bank. So it reads the `<text>` the callout has
// always drawn: monospace, `text-anchor="end"`, inside the probability chart's
// own svg. That selector predates the repair and survives it.
//
// EXIT CODES ARE A STORY (gotcha #124):
//   0  the two tabs print the SAME label — paid
//   3  they DISAGREE — the defect, live
//   4  no callout found in one or both tabs = NOTHING WAS CHECKED, not a pass
//   5  the "All" tab could not be reached (button missing or disabled)
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
  console.error('usage: node ux1352-chart-ends-at-the-whistle-6987.mjs <baseUrl> <eventId> [out.png]');
  process.exit(2);
}
const URL = `${base.replace(/\/$/, '')}/events/${eventId}`;

/**
 * Read the end-callout as a reader sees it.
 *
 * Returns the label plus how many candidates matched, because "one" is part of
 * the claim: two monospace end-anchored numbers on the page would mean this is
 * reading some other chart's glyphs and the comparison below would be about
 * nothing.
 */
const READ_CALLOUT = () => {
  const texts = Array.from(document.querySelectorAll('svg text'))
    .filter((t) => {
      const ff = t.getAttribute('font-family') || getComputedStyle(t).fontFamily;
      const anchor = t.getAttribute('text-anchor') || getComputedStyle(t).textAnchor;
      return /monospace/i.test(ff || '') && anchor === 'end';
    })
    .map((t) => (t.textContent || '').trim())
    .filter((s) => /^[<>]?\d{1,3}%$/.test(s));
  return { label: texts[0] ?? null, matched: texts.length };
};

// The same launch `shop-shot.mjs` documents, and for the same two reasons: the
// default multi-process launch dies in the agent sandbox with
// `bootstrap_check_in … Permission denied (1100)`, and the browser does not
// inherit the session egress proxy. A localhost target keeps Chromium's implicit
// loopback bypass — `<-loopback>` sends a local `next start` through the proxy,
// which answers 503, and the page then reads as "the chart is not there"
// (ux/1200).
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
  if (!/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])([:/]|$)/.test(URL)) {
    launchArgs.push('--proxy-bypass-list=<-loopback>');
  }
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
  // Recharts animates in; the callout shape is drawn with the series.
  await page.waitForTimeout(4000);

  const first = await page.evaluate(READ_CALLOUT);
  // Which tab is ON. `aria-pressed` is the honest handle and arrives with the
  // fix; the fill class is the FALLBACK so this same probe can still read the
  // unfixed production page (ux/1351: anchor on what the repair will not touch,
  // and keep the old selector rather than replacing it).
  const firstTab = await page.evaluate(() => {
    const tabs = Array.from(document.querySelectorAll('button')).filter((b) =>
      /^(All|Since Start)$/.test((b.textContent || '').trim()),
    );
    const on =
      tabs.find((b) => b.getAttribute('aria-pressed') === 'true') ??
      tabs.find((b) => /bg-text-primary|bg-surface-card\/10/.test(b.className));
    return on ? on.textContent.trim() : '(unknown)';
  });
  console.log(`default tab  : ${firstTab}`);
  console.log(`  callout    : ${first.label ?? '(none)'}   [${first.matched} candidate(s)]`);

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

  const second = await page.evaluate(READ_CALLOUT);
  console.log('after tapping "All"');
  console.log(`  callout    : ${second.label ?? '(none)'}   [${second.matched} candidate(s)]`);

  if (out) {
    await page.screenshot({ path: out });
    console.log(`shot: ${out}`);
  }
  await browser.close();

  if (!first.label || !second.label) {
    console.error('NO CALLOUT FOUND — nothing was checked (this is not a pass)');
    process.exit(4);
  }
  if (first.label !== second.label) {
    console.error(
      `DISAGREE: "${firstTab}" prints ${first.label} and "All" prints ${second.label} ` +
        'for the same finished game — #6987 is live',
    );
    process.exit(3);
  }
  console.log(`AGREE: both tabs print ${first.label}`);
  process.exit(0);
})();
