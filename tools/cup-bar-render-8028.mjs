// cup-bar-render-8028.mjs — paint the FIXED cup cards against the real built CSS (#8028).
//
// The jest guard asserts CLASS STRINGS. A class string is not a colour: #7015 is the
// standing proof that a class living only in `lib/` can be purged from the stylesheet and
// render as nothing at all, silently, with a green build. So this takes the component's
// server markup, drops it into a page that loads `.next/static/css/*.css`, and reads the
// COMPUTED backgroundColor back out — the same question `cup-bar-colours-8028.mjs` asks of
// production, asked of the fix before it is offered.
//
// Usage: node tools/cup-bar-render-8028.mjs <markupJsonPath> <outPng>
import { createRequire } from 'module';
import { existsSync, readdirSync, readFileSync } from 'fs';

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

const [, , markupPath, outPng] = process.argv;
if (!markupPath) { console.error('usage: cup-bar-render-8028.mjs <markupJsonPath> <outPng>'); process.exit(2); }

const cards = JSON.parse(readFileSync(markupPath, 'utf8'));
const cssDir = 'frontend/.next/static/css';
const css = readdirSync(cssDir).filter((f) => f.endsWith('.css'))
  .map((f) => readFileSync(`${cssDir}/${f}`, 'utf8')).join('\n');

const html = `<!doctype html><html><head><meta charset="utf-8"><style>${css}</style>
<style>body{margin:0;background:#F9FAFB;padding:12px;font-family:-apple-system,system-ui,sans-serif}
.spacer{height:14px}</style></head><body>
${cards.map((c) => `<div class="spacer"></div>${c.markup}`).join('\n')}
</body></html>`;

const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width: 390, height: 700 }, deviceScaleFactor: 2 });
await page.setContent(html, { waitUntil: 'load' });

const out = await page.evaluate(() => {
  const bars = [...document.querySelectorAll('div.flex.h-2.rounded-full.overflow-hidden')];
  return bars.map((bar) => {
    const segs = [...bar.children].map((s) => ({
      bg: getComputedStyle(s).backgroundColor,
      w: s.style.width,
      painted: getComputedStyle(s).backgroundColor !== 'rgba(0, 0, 0, 0)',
    }));
    const card = bar.closest('a') || bar.parentElement;
    const names = [...card.querySelectorAll('div.text-xs.font-semibold')].slice(0, 2)
      .map((d) => ({ name: d.textContent.trim(), color: getComputedStyle(d).color }));
    return { names, segs, barSame: segs.length === 2 ? segs[0].bg === segs[1].bg : null };
  });
});

for (const b of out) {
  console.log(`\n── ${b.names.map((n) => n.name).join('  v  ')} ──`);
  b.segs.forEach((s, i) => console.log(`   seg${i}: ${s.bg}  w=${s.w}  PAINTED=${s.painted}`));
  console.log(`   names: ${b.names.map((n) => `${n.name}=${n.color}`).join(' | ')}`);
  console.log(`   BAR SAME? ${b.barSame}   <- must be false`);
  if (b.segs.some((s) => !s.painted)) console.log('   !! A SEGMENT IS TRANSPARENT — the class was purged (#7015)');
}

if (outPng) { await page.screenshot({ path: outPng, fullPage: true }); console.log(`\nwrote ${outPng}`); }
await browser.close();
