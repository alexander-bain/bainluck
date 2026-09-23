/**
 * #8123 — reads the EYEBROW LINE of every cup card on /categories/golf.
 *
 * The defect: the Ryder Cup card printed `⛳ Cup  Aug 28` — a 2026 capture
 * timestamp (`commence_time: 2026-08-28T20:16:51+00:00`) standing in for a date
 * of play on an event that does not resolve until 2027-09-30. The sibling
 * Presidents Cup card, which has real `start_date`/`end_date`, correctly read
 * `Sep 24–27` and is the non-widening control: it must be untouched.
 *
 * Prints, per cup card: the eyebrow text, whether that text carries a date, and
 * the card's Y offset (so a LOOK can be framed on it — the offsets move as
 * tournaments come and go, so they are re-measured every run, never reused).
 *
 * RUN IT BEFORE THE DEPLOY AND AFTER. A run that reads "no date" only proves
 * something if the same instrument read the stale date on the same page
 * beforehand.
 *
 *   node ~/bainluck/tools/cup-eyebrow-date-8123.mjs
 */
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
const args = ['--no-sandbox','--single-process','--disable-gpu','--disable-crashpad','--disable-dev-shm-usage'];
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxy) { args.push(`--proxy-server=${proxy}`); args.push('--proxy-bypass-list=<-loopback>'); }

const URL_UNDER_TEST = process.argv[2] || 'https://bainluck.com/categories/golf';

const b = await chromium.launch({ args });
const p = await b.newPage({ viewport: { width: 390, height: 844 } });

await p.goto(URL_UNDER_TEST, { waitUntil: 'load', timeout: 90000 });

// Read the build sha from inside the page: `/api/frontend-build` 307s to the
// canonical host, and an out-of-page request lands on the redirect stub rather
// than the JSON. Which build answered is the whole point of the receipt, so an
// unknown here is a failed run, not a cosmetic gap.
let build = 'unknown';
try {
  build = await p.evaluate(async () => {
    const r = await fetch('/api/frontend-build', { cache: 'no-store' });
    return (await r.json()).commit;
  });
} catch {}
console.log(`url=${URL_UNDER_TEST}`);
console.log(`frontend-build=${build}`);
console.log(`read-at=${new Date().toISOString()}`);

await p.waitForTimeout(6000);
await p.setViewportSize({ width: 390, height: 2000 });
await p.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await p.waitForTimeout(5000);
await p.evaluate(() => window.scrollTo(0, 0));
await p.waitForTimeout(2000);
await p.setViewportSize({ width: 390, height: 844 });

// A cup card is the one whose eyebrow reads "⛳ Cup". Walk every card and read
// the eyebrow row (the ⛳ line) and the name line directly under it.
const rows = await p.evaluate(() => {
  const out = [];
  for (const a of Array.from(document.querySelectorAll('a[href]'))) {
    const eyebrow = a.querySelector('div.text-\\[11px\\]');
    if (!eyebrow) continue;
    const text = (eyebrow.textContent || '').trim();
    if (!text.startsWith('⛳')) continue;
    const nameEl = eyebrow.parentElement?.querySelector('div.text-sm.font-bold');
    const dateSpan = eyebrow.querySelector('span.text-text-tertiary');
    const r = a.getBoundingClientRect();
    out.push({
      name: (nameEl?.textContent || '').trim(),
      eyebrow: text,
      dateText: dateSpan ? (dateSpan.textContent || '').trim() : null,
      href: a.getAttribute('href'),
      y: Math.round(r.top + window.scrollY),
    });
  }
  return out;
});

const cups = rows.filter((r) => r.eyebrow.includes('Cup'));
console.log(`\ncards-with-golf-eyebrow=${rows.length}  cup-cards=${cups.length}\n`);
for (const c of cups) {
  console.log(
    `${(c.name || '(unnamed)').padEnd(22)} eyebrow="${c.eyebrow}"  date=${
      c.dateText === null ? 'NONE' : `"${c.dateText}"`
    }  y=${c.y}  ${c.href}`,
  );
}

const ryder = cups.find((c) => /ryder/i.test(c.name));
const presidents = cups.find((c) => /presidents/i.test(c.name));
console.log('');
console.log(`RYDER CUP PRINTS A DATE?      ${ryder ? (ryder.dateText !== null) : 'card not found'}   ${ryder ? `(${ryder.dateText ?? 'none'})` : ''}`);
console.log(`PRESIDENTS CUP KEEPS ITS DATE? ${presidents ? (presidents.dateText !== null) : 'card not found'}   ${presidents ? `(${presidents.dateText ?? 'none'})` : ''}`);
console.log(`docHeight=${await p.evaluate(() => document.body.scrollHeight)}`);
await b.close();
