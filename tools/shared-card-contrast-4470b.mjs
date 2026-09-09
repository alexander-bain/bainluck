// shared-card-contrast-4470b.mjs — can a reader SEE both halves of the shared game card?
//
// `components/EventCard.tsx` is the /sports, league, search and my-stuff card. It spends
// `teams.primary_color` in two places, and this probe reads the pixel each one actually paints:
//
//   BAR   the two `[role="meter"]` segments. The favourite is painted at opacity 1 and the
//         underdog at 0.4, so each segment is composited at ITS OWN opacity — the number the
//         reader sees, not the token.
//   TILE  the 20x20 initials square, used when a team has no face, flag or crest image.
//
// Ratios reported per element:
//   surface : the element against the card it sits on   (can the reader see it at all?)
//   ink     : the initials against their own tile        (TILE only — can they read the letters?)
//
// THE BEFORE, measured on production at 390px on 2026-09-09 over six league pages:
// **36 of 220 bar segments (16.4%) below 1.5:1**, 26 of them at exactly 1.00 — pure white on
// white (Sevilla, Valencia, Leeds, Fulham, Real Madrid, Augsburg, Eintracht Frankfurt…), plus
// Fenerbahçe `#ffff00` at 1.05, Bodø/Glimt `#fcee33` at 1.09 and Celta/Málaga `#b9e8f0` at 1.12.
//
// THE TILE ARM IS EXPECTED TO PASS, and that is a finding, not filler. discover/023 handed over
// #4470's sibling as "the crest tile paints 33 teams white on white" with the colour census done
// but the reach unmeasured. It is unreachable: all 1,450 teams carrying a `primary_color` also
// carry a `logo_url_small`, so a team with a colour always renders the crest IMAGE and never the
// tile, and a team that reaches the tile has no `teams` row, hence no colour, hence the gray-500
// token default. 116 tiles were read across six league pages and every one painted `#6b7280`.
// The arm stays so that a future data change — a coloured team losing its logo — is caught here
// instead of on Alex's screen.
//
// CONTROL: elements that already pass. A run where everything fails, or where nothing is found,
// is a broken probe rather than a finding — a selector that matched nothing would otherwise
// report "0 of 0 fail" and read as a pass.
//
// Usage: node shared-card-contrast-4470b.mjs <sport_key> [sport_key…]
//        node shared-card-contrast-4470b.mjs --url <full-url>
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

const argv = process.argv.slice(2);
if (!argv.length) {
  console.error('usage: shared-card-contrast-4470b.mjs <sport_key>… | --url <url>');
  process.exit(2);
}
const urls =
  argv[0] === '--url'
    ? argv.slice(1)
    : argv.map((k) => `https://www.bainluck.com/sports/${k}`);

const WIDTH = Number(process.env.SHOT_W || 390);
// "Visible at all", not WCAG text — the floor `lib/probabilityBarPair.ts` picked by replaying the
// real palette. Deliberately the same number: one site-wide notion of "the reader can see it".
const FLOOR = 1.5;

// A bare `chromium.launch()` dies in this sandbox with `bootstrap_check_in … Permission denied`.
// `--single-process` is the arg that matters — and it also means the browser CANNOT survive a
// second page, so each URL gets its own browser.
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const lum = (c) => {
  const f = (v) => {
    const x = v / 255;
    return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
};
const ratio = (a, b) => {
  const la = lum(a), lb = lum(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
};
const over = (fg, bg, extraAlpha = 1) => {
  const a = (fg[3] ?? 1) * extraAlpha;
  return [0, 1, 2].map((i) => a * fg[i] + (1 - a) * bg[i]);
};
const hex = (c) =>
  '#' + [0, 1, 2].map((i) => Math.round(c[i]).toString(16).padStart(2, '0')).join('');

const collect = () => {
  const parse = (s) => {
    const m = String(s).match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map((x) => parseFloat(x.trim()));
    return p.length >= 3 && p.every(Number.isFinite)
      ? [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]
      : null;
  };
  const surfaceOf = (el) => {
    for (let p = el.parentElement; p; p = p.parentElement) {
      const c = parse(getComputedStyle(p).backgroundColor);
      if (c && c[3] > 0) return c;
    }
    return [255, 255, 255, 1];
  };

  const bars = [];
  for (const el of document.querySelectorAll('[role="meter"] > *')) {
    const cs = getComputedStyle(el);
    bars.push({
      bg: parse(cs.backgroundColor),
      op: parseFloat(cs.opacity),
      width: cs.width,
      surface: surfaceOf(el),
      label: (el.closest('[role="meter"]')?.parentElement?.textContent || '').trim().slice(0, 46),
    });
  }

  // The tile carries no testid on either side of this ship, so it is found by shape: a 20x20 box
  // holding 1-4 capitals with a painted background.
  const tiles = [];
  for (const el of document.querySelectorAll('div')) {
    const t = (el.textContent || '').trim();
    if (!/^[A-Z0-9]{1,4}$/.test(t)) continue;
    const r = el.getBoundingClientRect();
    if (Math.round(r.width) !== 20 || Math.round(r.height) !== 20) continue;
    const cs = getComputedStyle(el);
    const bg = parse(cs.backgroundColor);
    if (!bg || bg[3] === 0) continue;
    tiles.push({
      bg,
      ink: parse(cs.color),
      surface: surfaceOf(el),
      text: t,
      label: (el.parentElement?.textContent || '').trim().slice(0, 40),
    });
  }
  return { bars, tiles };
};

let barTotal = 0, barFail = 0, tileTotal = 0, tileFail = 0;
const findings = [];

for (const url of urls) {
  const browser = await chromium.launch({ headless: true, args });
  const page = await browser.newPage({ viewport: { width: WIDTH, height: 1400 } });
  let data;
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
    await page.waitForTimeout(2500);
    data = await page.evaluate(collect);
  } catch (e) {
    await browser.close();
    console.log(`${url}\n  LOAD FAILED — ${e.message.split('\n')[0]}`);
    continue;
  }
  await browser.close();

  let bf = 0, tf = 0;
  for (const b of data.bars) {
    if (!b.bg) continue;
    barTotal++;
    const pix = over(b.bg, b.surface, Number.isFinite(b.op) ? b.op : 1);
    const r = ratio(pix, b.surface);
    if (r < FLOOR) {
      barFail++; bf++;
      findings.push(`BAR   r=${r.toFixed(2)} raw=${hex(b.bg)} op=${b.op} painted=${hex(pix)} w=${b.width}  ${b.label}`);
    }
  }
  for (const t of data.tiles) {
    if (!t.bg || !t.ink) continue;
    tileTotal++;
    const bgPix = over(t.bg, t.surface);
    const inkPix = over(t.ink, bgPix);
    const rInk = ratio(inkPix, bgPix);
    const rTile = ratio(bgPix, t.surface);
    // The INK is the information; a pale tile with dark letters is legible. Both are printed.
    if (rInk < FLOOR) {
      tileFail++; tf++;
      findings.push(`TILE  ink=${rInk.toFixed(2)} surface=${rTile.toFixed(2)} bg=${hex(bgPix)} ink=${hex(inkPix)}  "${t.text}"  ${t.label}`);
    }
  }
  console.log(`${url}\n  bars ${data.bars.length} (${bf} below ${FLOOR})   tiles ${data.tiles.length} (${tf} unreadable)`);
}

console.log(`\nBARS   ${barTotal - barFail}/${barTotal} visible`);
console.log(`TILES  ${tileTotal - tileFail}/${tileTotal} readable`);
if (!barTotal && !tileTotal) {
  console.log('⚠️  INCONCLUSIVE — nothing was found to measure; suspect the probe, not the page');
  process.exit(3);
}
if (findings.length) {
  console.log(`\n❌ FAIL  ${findings.length} element(s) the reader cannot see:`);
  for (const f of findings.slice(0, 40)) console.log('  ' + f);
  process.exit(1);
}
if (barTotal && barTotal === barFail) {
  console.log('⚠️  BROKEN — every bar segment read as failing and none passed; suspect the probe');
  process.exit(3);
}
console.log('\n✅ PASS  every measured element clears the floor');
