// models-chart-line-claim-8182.mjs — does a source card claim a chart line the chart does not draw?
//
// #8182. `/events/{id}/models` printed "Shown as this line on the chart" under every source card
// unconditionally. On `/events/15011303/models` that sentence sat under a green dashed swatch for
// Kalshi while the chart drew no Kalshi mark at all: its series is ONE point in the range the chart
// shows, and every series is stroked `dot={false}`, so it renders nothing.
//
// THE VERDICT IS A JOIN, and the join has to be against the RIGHT PAYLOAD. The page itself reads the
// whole journey (`/history` with no range) where Kalshi has two points; the chart's first paint reads
// `hours=48&range=since_start` where it has one. So a probe that checked the page's own payload would
// call the claim honest. This one fetches the CHART's payload and asks, per source:
//   * does the card claim a line?          (rendered, off `[data-testid="model-source-chart-key"]`)
//   * can the chart stroke one?            (>= 2 points in the chart's range)
// Only claim-without-line is a defect. A source that genuinely draws is entitled to say so and is
// not reported, so this cannot be passed by a page that simply stopped printing the strip.
//
// It also reads the count line, because "1 data points" was the other half of the issue.
//
// Usage: node models-chart-line-claim-8182.mjs <eventModelsUrl> [widthPx] [--shot out.png]
// Exit:  0 no card claims a line the chart does not draw · 1 DEFECT SERVED · 2 bad usage
//        3 no source cards on this page · 4 could not read
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

const url = process.argv[2];
const width = Number(process.argv[3] || 390);
const shotAt = process.argv.indexOf('--shot');
const shotPath = shotAt > -1 ? process.argv[shotAt + 1] : null;
if (!url) {
  console.error('usage: models-chart-line-claim-8182.mjs <eventModelsUrl> [widthPx] [--shot out.png]');
  process.exit(2);
}
const eventId = (url.match(/\/events\/(\d+)/) || [])[1];
if (!eventId) {
  console.error('usage: the URL must be an /events/{id}/models page');
  process.exit(2);
}

// The sandbox needs --single-process; a bare launch dies on bootstrap_check_in (ux/1457 §5).
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  args.push('--proxy-bypass-list=<-loopback>');
}

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });

const out = { url, eventId, width, cards: [], problems: [] };

try {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(1200);

  // 🪤 A RATE-LIMITED PAGE LOOKS EXACTLY LIKE A PAGE WITH NO CARDS ON IT. Three runs inside a
  // minute trip `60/minute` and the app renders its error card in place of the whole body; every
  // selector then finds nothing and an unguarded probe reports "no source cards", a sentence about
  // a page it never saw. Checked FIRST, and exit 4 (could not read), not 3 (nothing here).
  const blocked = await page.evaluate(() =>
    /Too many requests|Rate limit exceeded/i.test(document.body.innerText),
  );
  if (blocked) {
    out.problems.push('rate limited (60/minute) — the app served its error card, not the page');
    console.log(JSON.stringify(out, null, 2));
    await browser.close();
    process.exit(4);
  }

  // 🔴 READ THE CLAIM OFF THE READER'S TEXT, NOT OFF THE TESTIDS THE FIX ADDS.
  // `model-source-chart-key` and `model-source-count` do not exist on the unfixed page, so a probe
  // keyed on them reports "nothing claims a line" against the very defect it was written to catch
  // — green on the BEFORE, for the wrong reason, which makes the after-check worthless. The
  // sentence and the count string are what a reader sees and are identical in both versions, so
  // they are the primary signal; the testids are recorded only as corroboration.
  const rendered = await page.$$eval('[data-testid="model-source-card"]', (cards) =>
    cards.map((c) => {
      const text = (c.textContent || '').replace(/\s+/g, ' ').trim();
      const CLAIM = 'Shown as this line on the chart';
      const countMatch = text.match(/(\d[\d,]*) data points? captured for this event/);
      return {
        source: c.getAttribute('data-source') || '',
        claimsALine: text.includes(CLAIM),
        claimText: text.includes(CLAIM) ? CLAIM : null,
        countText: countMatch ? countMatch[0] : null,
        hasChartKeyTestid: !!c.querySelector('[data-testid="model-source-chart-key"]'),
      };
    }),
  );
  if (rendered.length === 0) {
    out.problems.push('no source cards on this page');
    console.log(JSON.stringify(out, null, 2));
    await browser.close();
    process.exit(3);
  }

  // What the CHART is showing — the same request its first paint makes. Read through the page's
  // own origin so the API's CORS allowlist is satisfied without a shim.
  const served = await page.evaluate(async (id) => {
    const r = await fetch(
      `https://api.bainluck.com/api/events/${id}/history?hours=48&range=since_start`,
    );
    const d = await r.json();
    const len = (a) => (Array.isArray(a) ? a.length : 0);
    const winProb = d.win_prob_history || {};
    const series = { betting: len(d.history) };
    for (const [k, v] of Object.entries(winProb)) series[k] = len(v);
    if (Object.keys(winProb).length === 0) series.espn = len(d.espn_history);
    return { series };
  }, eventId);
  out.chartRangeSeriesLengths = served.series;

  for (const card of rendered) {
    const points = served.series[card.source];
    // `undefined` means the chart's payload carries no series for this source at all — which is
    // also "nothing to draw", but it is worth telling apart from a short one when reading output.
    const strokes = typeof points === 'number' && points >= 2;
    const entry = {
      ...card,
      chartRangePoints: points === undefined ? null : points,
      chartStrokesALine: strokes,
      verdict: 'ok',
    };
    if (card.claimsALine && !strokes) {
      entry.verdict = 'CLAIMS A LINE THE CHART DOES NOT DRAW';
      out.problems.push(
        `${card.source}: says "${card.claimText}" but its series in the chart's range is ` +
          `${points === undefined ? 'absent' : points + ' point(s)'} — nothing is stroked`,
      );
    }
    if (card.countText && /\b1 data points\b/.test(card.countText)) {
      entry.verdict = entry.verdict === 'ok' ? 'COUNT DISAGREES WITH ITSELF' : entry.verdict;
      out.problems.push(`${card.source}: count reads "${card.countText}"`);
    }
    out.cards.push(entry);
  }

  // Both directions (gotcha #43): a page that printed no strips at all would satisfy the check
  // above trivially, so record whether anything on it still claims a line. This is reported, not
  // failed on — a page whose every source is genuinely undrawable is a legitimate zero.
  out.cardsClaimingALine = out.cards.filter((c) => c.claimsALine).length;
  if (out.cardsClaimingALine === 0) {
    out.note =
      'no card claims a line — check this is a page where none is drawable, not a strip that stopped rendering';
  }

  if (shotPath) await page.screenshot({ path: shotPath, fullPage: true });
  out.shot = shotPath;

  console.log(JSON.stringify(out, null, 2));
  await browser.close();
  process.exit(out.problems.length > 0 ? 1 : 0);
} catch (e) {
  out.problems.push(`could not read: ${e.message}`);
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
  process.exit(4);
}
