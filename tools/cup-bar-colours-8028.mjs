// cup-bar-colours-8028.mjs — does a cup card's probability bar differentiate its two sides? (#8028)
//
// The defect is "the bar is one grey block", which a screenshot shows but cannot GRADE: two
// segments painted the same colour and two segments painted similar colours look alike at 390px,
// and the whole claim is about which class each segment carries. So this reads the layout engine:
//
//   * each cup card's two team names, as served                -> what the colour map is keyed on
//   * each bar segment's resolved backgroundColor + class      -> the painted answer
//   * SAME vs DISTINCT for the pair                            -> the defect, as a boolean
//   * the card's y offset in the page                          -> the SHOT_SCROLL for a paired frame
//
// A colour is read from `getComputedStyle`, never from the class string: a class that does not
// exist in the built CSS resolves to transparent and would read as "differentiated" by name.
//
// Usage: node cup-bar-colours-8028.mjs <url> [widthPx]
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
if (!url) { console.error('usage: cup-bar-colours-8028.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });

const out = await page.evaluate(() => {
  // A cup card is identified by the "⛳ Cup" eyebrow the cup renderer alone draws, so this
  // finds cards by what CupCard RENDERS rather than by a tournament key the DOM does not carry.
  const cards = [...document.querySelectorAll('a')].filter((a) =>
    /⛳\s*Cup/.test(a.textContent || ''),
  );
  return cards.map((card) => {
    // The bar is the only 2-child flex row of `h-2 rounded-full` segments in the card.
    const bar = [...card.querySelectorAll('div')].find(
      (d) => d.className.includes('rounded-full') && d.className.includes('overflow-hidden') && d.children.length === 2,
    );
    const segs = bar ? [...bar.children] : [];
    const seg = segs.map((s) => ({
      cls: s.className,
      bg: getComputedStyle(s).backgroundColor,
      width: s.style.width,
    }));
    // The two team names sit in the `text-xs font-semibold` divs above the bar.
    const names = [...card.querySelectorAll('div.text-xs.font-semibold')]
      .map((d) => (d.textContent || '').trim())
      .filter(Boolean);
    const r = card.getBoundingClientRect();
    return {
      title: (card.querySelector('div.text-sm.font-bold') || {}).textContent || null,
      names: names.slice(0, 2),
      nameColours: [...card.querySelectorAll('div.text-xs.font-semibold')]
        .slice(0, 2)
        .map((d) => getComputedStyle(d).color),
      seg,
      barSame: seg.length === 2 ? seg[0].bg === seg[1].bg : null,
      nameSame:
        [...card.querySelectorAll('div.text-xs.font-semibold')].length >= 2
          ? getComputedStyle(card.querySelectorAll('div.text-xs.font-semibold')[0]).color ===
            getComputedStyle(card.querySelectorAll('div.text-xs.font-semibold')[1]).color
          : null,
      cardTopAbsolute: Math.round(r.top + window.scrollY),
    };
  });
});

if (out.length === 0) {
  console.log('NO CUP CARDS FOUND — this is a dead instrument, not a clean result.');
  console.log('(the "⛳ Cup" eyebrow is what identifies a cup card; if the page has none, say so)');
} else {
  for (const c of out) {
    console.log(`\n── ${c.title} ──`);
    console.log(`   sides        : ${JSON.stringify(c.names)}`);
    console.log(`   bar segments : ${c.seg.map((s) => `${s.bg} (w=${s.width}) [${s.cls}]`).join('\n                  ')}`);
    console.log(`   BAR SAME?    : ${c.barSame}   <- true IS the defect`);
    console.log(`   name colours : ${JSON.stringify(c.nameColours)}`);
    console.log(`   NAMES SAME?  : ${c.nameSame}  <- true IS the defect`);
    console.log(`   SHOT_SCROLL  : ${Math.max(0, c.cardTopAbsolute - 60)}  (card top ${c.cardTopAbsolute}, 60px of lead-in)`);
  }
}

await browser.close();
