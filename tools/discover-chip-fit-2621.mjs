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
// AFTER THE SHIP (#6330 merged `30fbde79e`, 2026-09-15 10:21Z) THE PREMISE ABOVE IS GONE,
// AND THAT IS WHY THIS FILE CHANGED RATHER THAN BEING LEFT ALONE. The chip and the badge
// are now two children of ONE absolutely-positioned flex row, so the chip is no longer an
// absolute itself — and the locator below ("the absolute rounded pill at the hero's
// top-left") stopped matching it and printed `NO EVENT CARD ON THIS DRAW (no chip)` at
// exit 4 over a page full of event cards. An instrument that reports absence when its
// subject is present is worse than no instrument: exit 4 is the "re-run, the feed shuffled"
// code, so it read as noise. The locator now finds the pill whether or not it carries the
// position itself, and the measurement it prints is the one the new markup makes decidable:
// the chip's real box against the badge's real box, on every card of the draw.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 measured and no card overlaps, 2 usage, 3 a chip
// and a LIVE badge INTERSECT on at least one card (the defect is back), 4 no event card on
// this draw (the feed is shuffled — a re-run, not a failure), 1 anything else.
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
  const cards = [...document.querySelectorAll('[data-card-format="event"]')];
  if (cards.length === 0) return { none: true };

  // The pill at the hero's top-left, WHETHER OR NOT it is the positioned element:
  // since #6330 the position lives on the flex row that holds the chip and the LIVE
  // badge, so a `position === 'absolute'` test finds the row and rejects the chip.
  // Asked of the box instead — a rounded pill whose top-left corner sits in the
  // hero's top-left corner — the locator reads both markups.
  const pillAt = (card, pred) => {
    const cardBox = card.getBoundingClientRect();
    return [...card.querySelectorAll('div')].find((d) => {
      const cs = getComputedStyle(d);
      if (!cs.borderRadius.includes('9999')) return false;
      const b = d.getBoundingClientRect();
      if (b.width === 0 || b.height === 0) return false;
      if (b.top - cardBox.top > 24) return false;
      return pred(b, cardBox, d);
    });
  };

  // Every card of the draw, as the reader has it: what the chip says, and whether it
  // shares pixels with the LIVE badge. An intersection is the #6330 defect returning.
  const drawn = cards.map((card) => {
    const cardBox = card.getBoundingClientRect();
    const chipEl = pillAt(card, (b, cb) => b.left - cb.left < 24);
    const liveEl = [...card.querySelectorAll('div')].find(
      (d) => d.textContent.trim() === 'LIVE' && d.getBoundingClientRect().width > 0,
    );
    if (!chipEl) return null;
    const c = chipEl.getBoundingClientRect();
    const l = liveEl ? liveEl.getBoundingClientRect() : null;
    return {
      text: chipEl.textContent.trim(),
      truncated: chipEl.scrollWidth > chipEl.clientWidth + 1,
      live: Boolean(l),
      gap: l ? Math.round(l.left - c.right) : null,
      overlaps: Boolean(l && c.right > l.left && c.left < l.right),
      width: Math.round(c.width),
      cardWidth: Math.round(cardBox.width),
    };
  }).filter(Boolean);

  const card = cards[0];
  const chip = pillAt(card, (b, cb) => b.left - cb.left < 24);
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

  // The width the chip is ALLOWED, which since #6330 is a property of the row and not
  // of the card: the flex row's content box, less the LIVE badge and the gap when the
  // card is live. That is the number a label is long against now — crossing it costs a
  // tail to `truncate`, where before it cost a collision with the badge.
  const row = chip.parentElement;
  const rowBox = row.getBoundingClientRect();
  const rowCs = getComputedStyle(row);
  const liveNow = [...card.querySelectorAll('div')].find(
    (d) => d.textContent.trim() === 'LIVE' && d.getBoundingClientRect().width > 0,
  );
  const reserved = liveNow
    ? liveNow.getBoundingClientRect().width + (parseFloat(rowCs.columnGap) || 0)
    : 0;
  const allowed = rowBox.width - reserved;

  const widthOf = (t) => ctx.measureText(t).width + tracking * t.length;
  const rows = labels.map((l) => {
    const text = prefix + l.toUpperCase();
    const w = widthOf(text) + padX;
    return { label: l, chipWidth: Math.round(w), fits: w <= allowed };
  });

  return {
    cardWidth: Math.round(cardBox.width),
    chipLeft: Math.round(chipBox.left - cardBox.left),
    chipText: chip.textContent.trim(),
    chipWidthNow: Math.round(chipBox.width),
    chipIsAbsolute: cs.position === 'absolute',
    rowWidth: Math.round(rowBox.width),
    allowed: Math.round(allowed),
    liveOnThisCard: Boolean(liveNow),
    font: ctx.font, tracking, padX, prefix,
    rows,
    drawn,
  };
}, LABELS);

await browser.close();

if (result.none) {
  console.log(`NO EVENT CARD ON THIS DRAW${result.reason ? ' (' + result.reason + ')' : ''}`);
  process.exit(4);
}

console.log(`card ${result.cardWidth}px · chip starts ${result.chipLeft}px · chip is its own absolute: ${result.chipIsAbsolute}`);
console.log(`row ${result.rowWidth}px · chip may have ${result.allowed}px of it${result.liveOnThisCard ? ' (LIVE reserved on this card)' : ''}`);
console.log(`chip on screen now: ${JSON.stringify(result.chipText)} = ${result.chipWidthNow}px`);
console.log(`font ${result.font} · tracking ${result.tracking} · padding ${result.padX}\n`);

// EVERY CARD OF THE DRAW — the after-check. `overlaps` is measured box against box, so
// it answers the reader's question rather than a class name's promise.
const overlapping = result.drawn.filter((d) => d.overlaps);
console.log(`${result.drawn.length} event cards on this draw · ${result.drawn.filter((d) => d.live).length} live · ${overlapping.length} with a chip touching LIVE`);
console.log('chip'.padEnd(30), 'px', '  live', ' gap to LIVE', ' clipped');
for (const d of result.drawn) {
  console.log(
    d.text.padEnd(30),
    String(d.width).padStart(4),
    (d.live ? '  yes' : '   no'),
    String(d.gap === null ? '-' : d.gap).padStart(12),
    '  ' + (d.truncated ? 'YES' : 'no'),
  );
}

console.log('\nWOULD THESE LABELS FIT THE SPACE THE ROW LEAVES?');
console.log('label'.padEnd(30), 'chip px', ' fits');
for (const r of result.rows) {
  console.log(r.label.padEnd(30), String(r.chipWidth).padStart(7), '  ' + (r.fits ? 'yes' : 'NO — clipped'));
}

if (overlapping.length > 0) {
  console.log(`\n🔴 ${overlapping.length} chip(s) intersect the LIVE badge: ${overlapping.map((d) => JSON.stringify(d.text)).join(', ')}`);
  process.exit(3);
}
