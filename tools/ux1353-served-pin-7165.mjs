// ux1353-served-pin-7165.mjs — AFTER-CHECK for #7165: is the SERVED pin one object?
//
// WHY NOT THE NATURAL SPECIMEN. The issue's frame is an AFL match sitting at
// `suspended` with no result. That specimen rotates: the venue grades it, or it ages
// off, and then a green run means "no ungraded match today" rather than "fixed".
// Worse, the defect was never about that page — the goblet was on every surface with
// a pin. The page only supplied the sentence ("No result reported") that let a reader
// finish the thought.
//
// So this asks the question that is always answerable and is the actual claim: of the
// pin a reader can see and toggle, do the two states draw THE SAME SHAPE? A pushpin
// when pinned and a goblet when not is two objects wearing one affordance, and that
// is exactly what shipped.
//
// It reads the SERVED `d` off the DOM in both states — obtained by CLICKING, so it is
// the pin the reader operates, not a component rendered in a harness. It is keyed on
// the states AGREEING rather than on the fix's own path string, so a later change of
// artwork still passes as long as the two states stay one object; and it names the
// retired goblet separately, so a run can say WHICH failure it found.
//
// Usage: node ux1353-served-pin-7165.mjs [url] [widthPx]
// exit 0 = the two states draw one shape (and the goblet is on neither)
//      3 = the states disagree, or the goblet is still served
//      2 = no pin button on this page, so the check is UNPAID, not passed
//      4 = the pin was found but the click did not change its state — nothing compared
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

const url = process.argv[2] || 'https://bainluck.com/events/15312403';
const width = Number(process.argv[3] || 390);

// The retired outline's stem and foot. No pushpin silhouette contains a bare vertical
// line segment, so either is enough to name the goblet by sight.
const GOBLET_MARKS = ['M12 11v6', 'M9 17h6'];

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
// 🔴 A BARE chromium.launch() DIES IN A LANE SHELL with `bootstrap_check_in …
// Permission denied (1100)`. These args are not optional here.
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

/** The pin, found by what it IS — a button whose label starts with Pin/Unpin. */
const PIN = 'button[aria-label^="Pin "], button[aria-label^="Unpin "], [data-testid="pin-button"]';

const read = () =>
  page.evaluate((sel) => {
    const btn = document.querySelector(sel);
    if (!btn) return null;
    const svg = btn.querySelector('svg');
    if (!svg) return { label: btn.getAttribute('aria-label'), paths: [], fill: null };
    return {
      label: btn.getAttribute('aria-label'),
      fill: svg.getAttribute('fill'),
      stroke: svg.getAttribute('stroke'),
      paths: [...svg.querySelectorAll('path')].map((p) => p.getAttribute('d') || ''),
    };
  }, PIN);

const before = await read();

if (!before) {
  await browser.close();
  console.log(`url=${url} viewport=${width}px load=${mode}`);
  console.log('\nUNPAID: no pin button on this page — re-run on a page that carries one.');
  process.exit(2);
}

await page.click(PIN, { timeout: 15000 }).catch(() => {});
await page.waitForTimeout(900);
const after = await read();

await browser.close();

console.log(`url=${url} viewport=${width}px load=${mode}`);
const show = (n, s) =>
  console.log(
    `  ${n.padEnd(7)} label=${JSON.stringify(s?.label)} fill=${s?.fill} stroke=${s?.stroke} paths=${s?.paths.length}\n` +
      (s?.paths || []).map((d) => `            d=${d.length > 72 ? d.slice(0, 72) + '…' : d}`).join('\n')
  );
show('state A', before);
show('state B', after);

if (!after || before.label === after.label) {
  // Both reads are the same state, so nothing was compared. That is a broken
  // instrument, not a pass — the whole claim is about the two states agreeing.
  console.log('\nNOT CHECKED: the click did not move the pin between its two states.');
  process.exit(4);
}

const goblet = [...before.paths, ...after.paths].filter((d) => GOBLET_MARKS.some((m) => d.includes(m)));
const shapeA = [...before.paths].sort().join('|');
const shapeB = [...after.paths].sort().join('|');
const agree = shapeA === shapeB;

console.log(`\nSTATES_AGREE=${agree}  GOBLET_PATHS=${goblet.length}`);
if (agree && goblet.length === 0) {
  console.log('VERDICT: both states of the served pin draw one shape — the pin is a pin.');
  process.exit(0);
}
if (!agree) console.log('VERDICT: the two states draw DIFFERENT shapes — the affordance is two objects.');
if (goblet.length) console.log('VERDICT: the retired goblet outline is still served.');
process.exit(3);
