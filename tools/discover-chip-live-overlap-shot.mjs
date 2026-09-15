// discover-chip-live-overlap-shot.mjs <url> <out.png> [label] — photograph the Discover
// hero's top row with a long league chip AND the LIVE badge present at the same time.
//
// WHY THE SPECIMEN IS MANUFACTURED. The overlap needs two things true of one card at one
// moment: a league whose chip is wide, and `status === "live"`. 505 of the 2,148 events in
// the NOW-2d..+7d window carry a wide chip, and every one of them is live for about two
// hours of its own match — but at any single instant the intersection is usually empty
// (measured 0 live at 07:30Z). A population you can only see for two hours per row is not
// absent; it is transient. So this probe takes a REAL production card, with production's
// own fonts, padding and card width, and sets the two fields — nothing about the geometry
// is simulated.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 shot it, 2 usage, 4 no event card on this draw, 1 camera.
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

const [url, out, label = 'OTHER SOCCER'] = process.argv.slice(2);
if (!url || !out) { console.error('usage: … <url> <out.png> [label]'); process.exit(2); }

const args = ['--single-process', '--no-sandbox'];
const proxy = process.env.HTTPS_PROXY || process.env.https_proxy;
if (proxy) { args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>'); }

const browser = await chromium.launch({ args });
const page = await browser.newPage({ viewport: { width: 390, height: 900 } });
await page.setExtraHTTPHeaders({ 'x-bainluck-origin': 'agent-ux' });
await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(2500);

const box = await page.evaluate((label) => {
  const card = document.querySelector('[data-card-format="event"]');
  if (!card) return null;
  const chip = [...card.querySelectorAll('div')].find((d) => {
    const cs = getComputedStyle(d);
    return cs.position === 'absolute' && cs.borderRadius.includes('9999')
      && parseFloat(cs.left) < 20 && parseFloat(cs.top) < 20;
  });
  if (!chip) return null;
  const emoji = chip.textContent.trim().split(/\s+/)[0];
  chip.textContent = `${emoji} ${label}`;

  // The LIVE badge exactly as `EventCard.tsx` renders it on a live card.
  const live = document.createElement('div');
  live.className = 'absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 bg-red-500/90 text-white text-[10px] font-bold uppercase px-2.5 py-1 rounded-full';
  live.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-white"></span>LIVE';
  chip.parentElement.appendChild(live);

  const r = card.getBoundingClientRect();
  return { x: r.x, y: r.y, width: r.width, height: Math.min(r.height, 220) };
}, label);

if (!box) { await browser.close(); console.log('NO EVENT CARD ON THIS DRAW'); process.exit(4); }
await page.waitForTimeout(300);
await page.screenshot({ path: out, clip: box });
await browser.close();
console.log(`wrote ${out} — card ${Math.round(box.width)}px, chip label ${JSON.stringify(label)}`);
