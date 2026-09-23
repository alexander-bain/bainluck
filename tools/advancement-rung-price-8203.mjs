// advancement-rung-price-8203.mjs — does a CHAMPIONSHIP PATH rung print a price nobody quoted?
//
// #8203. `RelatedFutures` coerced the wire with `f.probability || 0`, so a rung the venue has
// not priced (`probability: null`) reached `AdvancementPath` as a genuine zero and printed
// `0%` — on a *World Series Champion* rung, "this club cannot win", a claim no market made.
//
// WHY A BROWSER AND NOT A UNIT TEST. The unit suite proves the component refuses a null and the
// caller stops minting one. Neither can say whether the PAGE a reader loads still prints the
// number, because that depends on which of two producer branches the event takes at serve time
// (`league_context` present -> `ctxToFutures`, which already filtered nulls; absent -> the raw
// futures fallback, which did not). So the verdict is read off rendered text.
//
// THE VERDICT IS A JOIN, and that is the point. For each rung the probe reads BOTH:
//   * the rendered readout, off the row's own text
//   * whether the served row behind it carries a price, off /api/events/{id}/related-futures
// A rung printing `0%` is only a defect when its wire price is absent — a market genuinely
// quoted at nought is entitled to print `0%` and must NOT be reported. Reading one side alone
// gives a probe that either convicts honest zeroes or cannot see the defect at all.
//
// Usage: node advancement-rung-price-8203.mjs <eventUrl> [widthPx] [--shot out.png]
// Exit:  0 no rung prints a price its payload withholds · 1 DEFECT SERVED · 2 bad usage
//        3 no CHAMPIONSHIP PATH / SEASON OUTCOMES block on this page · 4 could not read
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
  console.error('usage: advancement-rung-price-8203.mjs <eventUrl> [widthPx] [--shot out.png]');
  process.exit(2);
}
const eventId = (url.match(/\/events\/(\d+)/) || [])[1];
if (!eventId) {
  console.error('usage: the URL must be an /events/{id} page');
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

const out = { url, eventId, width, rungs: [], problems: [] };

try {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  // The section is lazy under "Bigger Picture"; scroll the whole page so it mounts.
  await page.evaluate(async () => {
    for (let y = 0; y < document.body.scrollHeight; y += 600) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 60));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(1500);

  // What the reader sees. `data-stage` is the rung's label; the readout is whatever text the
  // row prints beyond that label, which is exactly the thing under test.
  // 🪤 A RATE-LIMITED PAGE LOOKS EXACTLY LIKE A PAGE WITH NO BLOCK ON IT.
  // Three runs of this probe in quick succession trip `60/minute` and the app renders its
  // "Too many requests" card in place of the whole body. Every selector below then finds
  // nothing and the probe exits 3, "no CHAMPIONSHIP PATH block on this page" — a sentence about
  // the PAGE, from a run that never saw the page. Checked before anything is read, and exit 4
  // (could not read) rather than 3, because that is what happened.
  const blocked = await page.evaluate(() =>
    /Too many requests|Rate limit exceeded/i.test(document.body.innerText),
  );
  if (blocked) {
    out.problems.push('rate limited (60/minute) — the app served its error card, not the page');
    console.log(JSON.stringify(out, null, 2));
    await browser.close();
    process.exit(4);
  }

  const rendered = await page.$$eval('[data-testid="advancement-stage"]', (rows) =>
    rows.map((r) => {
      const label = r.getAttribute('data-stage') || '';
      const text = (r.textContent || '').trim();
      const fill = r.querySelector('div[style*="width"]');
      return {
        label,
        readout: text.startsWith(label) ? text.slice(label.length).trim() : text,
        barWidth: fill ? fill.getAttribute('style') : null,
        hasBar: !!fill,
        dataProbability: r.getAttribute('data-probability'),
        noPrice: r.getAttribute('data-no-price') === 'true',
      };
    }),
  );
  if (rendered.length === 0) {
    out.problems.push('no advancement-stage rows on this page');
    console.log(JSON.stringify(out, null, 2));
    await browser.close();
    process.exit(3);
  }

  // What the payload says, read through the page's own origin so the API's CORS allowlist
  // is satisfied without a shim.
  const served = await page.evaluate(async (id) => {
    const r = await fetch(`https://api.bainluck.com/api/events/${id}/related-futures`);
    const d = await r.json();
    const rows = [...(d.home_team_futures || []), ...(d.away_team_futures || [])];
    const byLabel = {};
    for (const f of rows) {
      const k = f.clean_label || f.market_name;
      // Keep the FIRST row per label and record whether any row for it is priced, so a label
      // served twice (home and away) cannot be called withheld on the strength of one side.
      if (!(k in byLabel)) byLabel[k] = { probability: f.probability, anyPriced: false };
      if (f.probability != null) byLabel[k].anyPriced = true;
    }
    return { byLabel, leagueContext: d.league_context != null };
  }, eventId);
  out.leagueContextPresent = served.leagueContext;
  out.producerBranch = served.leagueContext ? 'league_context (ctxToFutures)' : 'raw futures fallback';

  for (const row of rendered) {
    const wire = served.byLabel[row.label];
    const printsAPercent = /\d\s*%/.test(row.readout);
    const entry = {
      ...row,
      wirePrice: wire ? wire.probability : undefined,
      wireKnown: !!wire,
      anyPriced: wire ? wire.anyPriced : undefined,
    };
    out.rungs.push(entry);
    // Only a rung the payload WITHHOLDS may not print a number. A rung whose label is not in
    // the payload came from league_context, whose cells this probe cannot key by label — it is
    // reported and not judged, rather than convicted on a lookup miss.
    if (!wire) {
      entry.verdict = 'not judged (label not in related-futures; league_context rung)';
      continue;
    }
    if (wire.probability == null && !wire.anyPriced && printsAPercent) {
      entry.verdict = 'DEFECT: prints a percentage over a withheld price';
      out.problems.push(`${row.label}: payload probability is null, page prints "${row.readout}"`);
    } else if (wire.probability == null && !wire.anyPriced && row.hasBar) {
      entry.verdict = 'DEFECT: draws a bar over a withheld price';
      out.problems.push(`${row.label}: payload probability is null, page draws a bar`);
    } else {
      entry.verdict = 'ok';
    }
  }

  if (shotPath) {
    const block = await page.$('[data-testid$="-championship-path"]');
    if (block) {
      // Frame the card the block sits in, so the shot shows the heading and the club above it.
      const card = await block.evaluateHandle((el) => el.closest('div[class*="rounded"]') || el);
      await card.asElement().screenshot({ path: shotPath });
      out.shot = shotPath;
    } else {
      await page.screenshot({ path: shotPath, fullPage: true });
      out.shot = `${shotPath} (full page; no -championship-path testid found)`;
    }
  }
} catch (e) {
  out.problems.push(`read failed: ${e.message}`);
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
  process.exit(4);
}

console.log(JSON.stringify(out, null, 2));
await browser.close();
process.exit(out.problems.length ? 1 : 0);
