// discover-chip-fit-2621.mjs <url> — measure whether a Discover card's sport chip can
// run under the centred LIVE badge, for the label set #2621's ux half would print.
//
// WHY MEASURE RATHER THAN ESTIMATE. The chip (`absolute top-3 left-3`), the LIVE badge
// (`absolute top-3 left-1/2 -translate-x-1/2`) and the dismiss button (`absolute top-3
// right-3`) are three independent absolutes in one hero. Nothing in the markup stops the
// first from growing into the second, so "will BUNDESLIGA - GERMANY overlap LIVE?" is a
// question about the rendered font's advance widths and the card's real width — both of
// which a hand estimate gets wrong in the direction that ships the overlap.
//
// It measures on the REAL page so the font stack, letter-spacing and padding are the ones
// production resolves, not the ones the class names imply.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 measured, 2 usage, 4 no event card on this draw
// (the feed is shuffled — a re-run, not a failure), 1 anything else.
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
if (!url) { console.error('usage: discover-chip-fit-2621.mjs <url>'); process.exit(2); }

// The labels `getSportLabel` returns for the keys #2621 measured as colliding, plus the
// short controls that must not move. Computed from the real helper, not guessed.
const LABELS = [
  'MLB', 'NFL', 'EPL', 'US OPEN',
  'OTHER SOCCER', 'OTHER TENNIS', 'OTHER BASKETBALL', 'OTHER MOTORSPORT',
  'LA LIGA - SPAIN', 'LIGUE 1 - FRANCE', 'UEFA EUROPA LEAGUE',
  'HANDBALL-BUNDESLIGA', 'BUNDESLIGA - GERMANY', 'PREMIER LEAGUE - RUSSIA',
  'PRIMEIRA LIGA - PORTUGAL', 'AUSTRIAN FOOTBALL BUNDESLIGA',
];

// Chromium's default multi-process launch dies in the agent sandbox and the browser does
// not inherit the session proxy — both fixed the way `shop-shot.mjs` fixes them.
const args = ['--single-process', '--no-sandbox'];
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
if (proxy) { args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>'); }

const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: 390, height: 900 } });
await page.setExtraHTTPHeaders({ 'x-bainluck-origin': 'agent-ux' });
await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(2500);

const result = await page.evaluate((labels) => {
  const card = document.querySelector('[data-card-format="event"]');
  if (!card) return { none: true };
  // The chip is the only absolutely-positioned pill at the hero's top-left.
  const chip = [...card.querySelectorAll('div')].find((d) => {
    const cs = getComputedStyle(d);
    return cs.position === 'absolute' && cs.borderRadius.includes('9999')
      && parseFloat(cs.left) < 20 && parseFloat(cs.top) < 20;
  });
  if (!chip) return { none: true, reason: 'no chip' };
  const cs = getComputedStyle(chip);
  const cardBox = card.getBoundingClientRect();
  const chipBox = chip.getBoundingClientRect();

  const ctx = document.createElement('canvas').getContext('2d');
  ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  const tracking = parseFloat(cs.letterSpacing) || 0;
  const padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
  // The emoji + space the chip prefixes to every label.
  const prefix = chip.textContent.trim().split(/\s+/)[0] + ' ';

  const widthOf = (t) => ctx.measureText(t).width + tracking * t.length;
  const rows = labels.map((l) => {
    const text = prefix + l.toUpperCase();
    const w = widthOf(text) + padX;
    return { label: l, chipWidth: Math.round(w), rightEdge: Math.round(chipBox.left - cardBox.left + w) };
  });

  return {
    cardWidth: Math.round(cardBox.width),
    chipLeft: Math.round(chipBox.left - cardBox.left),
    chipText: chip.textContent.trim(),
    chipWidthNow: Math.round(chipBox.width),
    font: ctx.font, tracking, padX, prefix,
    rows,
  };
}, LABELS);

await browser.close();

if (result.none) {
  console.log(`NO EVENT CARD ON THIS DRAW${result.reason ? ' (' + result.reason + ')' : ''}`);
  process.exit(4);
}

// The LIVE badge is centred on the card and is ~62px wide at this type size; its left
// edge is the first pixel a growing chip may not cross.
const LIVE_W = 62;
const liveLeft = result.cardWidth / 2 - LIVE_W / 2;

console.log(`card ${result.cardWidth}px · chip starts ${result.chipLeft}px · font ${result.font} · tracking ${result.tracking} · padding ${result.padX}`);
console.log(`chip on screen now: ${JSON.stringify(result.chipText)} = ${result.chipWidthNow}px`);
console.log(`LIVE badge (centred, ~${LIVE_W}px) occupies ${Math.round(liveLeft)}..${Math.round(liveLeft + LIVE_W)}px\n`);
console.log('label'.padEnd(30), 'chip px', ' right edge', ' overlaps LIVE?');
for (const r of result.rows) {
  const over = r.rightEdge > liveLeft;
  console.log(r.label.padEnd(30), String(r.chipWidth).padStart(7), String(r.rightEdge).padStart(11), '  ' + (over ? 'YES' : 'no'));
}
