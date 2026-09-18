// ux1334-served-chip-6929.mjs — AFTER-CHECK for #6929: does the SHIPPED chip carry the fix?
//
// WHY A SECOND PROBE. The sweep (`card-horiz-overflow-6929.mjs`) can only see the defect when a
// long category title happens to be on the feed, and that specimen ROTATES — it was present at
// 11:40Z and gone by 13:30Z with the code unchanged. An after-check that depends on it is
// unpayable most of the day, and a green run would mean "no long title today", not "fixed".
//
// So this asks the question that is always answerable: of the category chips actually served,
// does each one carry the constraint? A chip with `text-overflow: ellipsis` and a clipping
// overflow CANNOT be cut mid-word by its card, whatever title arrives next. That is the fix
// reaching the reader, and it is readable off any group/theme bundle card on the page.
//
// It reads COMPUTED STYLE, not the class attribute, so it is not keyed on the fix's own spelling:
// a future refactor to plain CSS or a different utility still passes if the reader is protected,
// and a class string that never reached the DOM still fails.
//
// Usage: node ux1334-served-chip-6929.mjs [url] [widthPx]
// exit 0 = every served chip is constrained (and at least one was found) · 3 = a bare chip
//          remains · 2 = no chip on the page, so the check is UNPAID, not passed
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

const url = process.argv[2] || 'https://bainluck.com/';
const width = Number(process.argv[3] || 390);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });

let mode = 'networkidle';
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
try {
  await page.waitForLoadState('networkidle', { timeout: 20000 });
} catch {
  mode = 'domcontentloaded+settle (page never went idle)';
}
await page.waitForTimeout(2500);

// Expand nothing and scroll the column so cards below the fold hydrate — bundle cards are not
// guaranteed to be in the first viewport and a chip we never rendered is a chip we cannot grade.
await page.evaluate(async () => {
  for (let y = 0; y < 6000; y += 700) {
    window.scrollTo(0, y);
    await new Promise((r) => setTimeout(r, 120));
  }
  window.scrollTo(0, 0);
});
await page.waitForTimeout(1200);

const chips = await page.evaluate(() => {
  // The category chip, found by what it IS: a small uppercase pill sitting inside a card, whose
  // text starts with an emoji. Not by class — the class is the thing under test.
  const out = [];
  for (const el of document.querySelectorAll('span')) {
    const cs = getComputedStyle(el);
    if (cs.textTransform !== 'uppercase') continue;
    if (parseFloat(cs.borderTopLeftRadius) < 8) continue;
    const t = (el.textContent || '').trim();
    if (!t) continue;
    const card = el.closest('div[class*="rounded-2xl"]');
    if (!card) continue;
    const cardStyle = getComputedStyle(card);
    const cardRight =
      card.getBoundingClientRect().right -
      parseFloat(cardStyle.borderRightWidth) -
      parseFloat(cardStyle.paddingRight);
    out.push({
      text: t.length > 60 ? t.slice(0, 60) + '…' : t,
      chars: t.length,
      ellipsis: cs.textOverflow === 'ellipsis',
      clips: cs.overflowX === 'hidden' || cs.overflowX === 'clip',
      escape: Math.round((el.getBoundingClientRect().right - cardRight) * 10) / 10,
    });
  }
  return out;
});

await browser.close();

console.log(`url=${url} viewport=${width}px load=${mode}`);
console.log(`category chips served: ${chips.length}`);

if (chips.length === 0) {
  // The honest outcome. A page with no bundle card proves nothing about the chip, and calling
  // that a pass is how a broken fix gets signed off.
  console.log('\nUNPAID: no category chip on this page — re-run when the feed carries a bundle card.');
  process.exit(2);
}

let bare = 0;
for (const c of chips) {
  const ok = c.ellipsis && c.clips;
  if (!ok) bare++;
  console.log(
    `  ${ok ? 'CONSTRAINED' : 'BARE       '} chars=${String(c.chars).padStart(3)} ` +
      `ellipsis=${c.ellipsis} clips=${c.clips} escape=${c.escape}px  ${JSON.stringify(c.text)}`
  );
}

const longest = chips.reduce((a, b) => (b.chars > a.chars ? b : a));
console.log(`\nBARE=${bare}/${chips.length}  longest served title=${longest.chars} chars`);
if (bare === 0) {
  console.log('VERDICT: every served chip ellipsises inside its card — the fix reached the reader.');
  process.exit(0);
}
console.log('VERDICT: a served chip can still be cut mid-word by its card.');
process.exit(3);
