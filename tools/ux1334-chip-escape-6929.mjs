// ux1334-chip-escape-6929.mjs — does the #6929 chip escape its card, and does the fix stop it?
//
// WHY THIS EXISTS. The natural specimen ROTATED OFF THE FEED: the merged sweep
// `card-horiz-overflow-6929.mjs` read CARD-ESCAPE=1 on `/` at 11:40Z and reads 0 now, while
// `GroupCard.tsx:72` / `ThemeBundleCard.tsx:80` are byte-unchanged. So the defect is not fixed —
// today's page simply carries no 45-character category title. An absent specimen cannot grade a
// fix in either direction, so this MANUFACTURES one.
//
// HOW IT STAYS HONEST. It does not simulate CSS. It loads the real production page (real Tailwind
// build, real fonts, real 390px viewport), CLONES a real card off it, and swaps only the chip's
// class string — OLD (shipped) vs NEW (proposed) — with the same 45-character title the reader
// actually saw. Everything except the one class string is held identical, so a difference in the
// measurement is caused by that string and nothing else.
//
// WHAT IT CANNOT SAY. It measures the class contract in the real engine, not the shipped page's
// own markup. Pairing it with the source-scan guard is what closes that gap: the guard pins the
// shipped chip to the NEW string, this proves the NEW string does not escape and the OLD one does.
//
// Usage: node ux1334-chip-escape-6929.mjs [url] [widthPx]
// exit 0 = OLD escapes and NEW does not (the expected before/after) · 3 = anything else
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

// The exact title the reader saw, from the issue. 45 characters including the emoji and space.
const TITLE = "⛳ Nationwide Children's Hospital Championship";

const CHIP_BASE = 'text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full';
const OLD = `bg-lime-600/15 text-lime-700 ${CHIP_BASE} whitespace-nowrap`;
const NEW = `bg-lime-600/15 text-lime-700 ${CHIP_BASE} min-w-0 max-w-full truncate`;

// Egress here is proxied; without these the navigation dies on ERR_ACCESS_DENIED, which reads
// exactly like the site being down. Same handling as the merged sweep.
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

const result = await page.evaluate(
  ({ title, oldCls, newCls }) => {
    // A real card off the real page: the shell the chip actually lives in, so its width, padding
    // and `overflow-hidden` are the production ones and not a reconstruction.
    const card = [...document.querySelectorAll('div')].find(
      (d) => /rounded-2xl/.test(d.className || '') && /overflow-hidden/.test(d.className || '') && d.getBoundingClientRect().width > 200
    );
    if (!card) return { error: 'no card shell found on page' };

    const host = document.createElement('div');
    host.style.cssText = `position:absolute;left:0;top:0;width:${Math.round(card.getBoundingClientRect().width)}px`;
    document.body.appendChild(host);

    // The header structure verbatim from GroupCard.tsx / ThemeBundleCard.tsx (identical in both).
    const build = (chipCls) => {
      const shell = document.createElement('div');
      shell.className = 'rounded-2xl border border-surface-border bg-surface-card shadow-lg overflow-hidden';
      shell.innerHTML =
        '<button class="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left">' +
        '<div class="flex flex-col gap-1 min-w-0">' +
        '<span class="flex items-center gap-2 min-w-0">' +
        `<span data-chip class="${chipCls}"></span>` +
        '</span>' +
        '<span class="text-sm font-semibold text-text-primary leading-snug">What happens at the Nationwide Children\'s Hospital Championship?</span>' +
        '</div>' +
        '<svg class="w-4 h-4 shrink-0"></svg>' +
        '</button>';
      shell.querySelector('[data-chip]').textContent = title;
      host.appendChild(shell);
      return shell;
    };

    const measure = (shell) => {
      const chip = shell.querySelector('[data-chip]');
      const cs = getComputedStyle(chip);
      const cardBox = shell.getBoundingClientRect();
      const cardStyle = getComputedStyle(shell);
      // Content-box right edge of the card: what the card's own overflow-hidden cuts against.
      const cardRight = cardBox.right - parseFloat(cardStyle.borderRightWidth) - parseFloat(cardStyle.paddingRight);
      const chipRight = chip.getBoundingClientRect().right;
      return {
        cardRight: Math.round(cardRight * 10) / 10,
        chipRight: Math.round(chipRight * 10) / 10,
        escape: Math.round((chipRight - cardRight) * 10) / 10,
        ellipsis: cs.textOverflow === 'ellipsis' && cs.overflow !== 'visible',
        selfClip: Math.round(chip.scrollWidth - chip.clientWidth),
        textOverflow: cs.textOverflow,
        overflowX: cs.overflowX,
      };
    };

    const out = { old: measure(build(oldCls)), neu: measure(build(newCls)) };
    host.remove();
    return out;
  },
  { title: TITLE, oldCls: OLD, newCls: NEW }
);

await browser.close();

if (result.error) {
  console.error('MEASUREMENT FAILED:', result.error);
  process.exit(3);
}

console.log(`url=${url} viewport=${width}px load=${mode}`);
console.log(`title=${JSON.stringify(TITLE)} (${TITLE.length} chars)`);
for (const [name, m] of [['OLD (shipped)', result.old], ['NEW (proposed)', result.neu]]) {
  console.log(
    `${name.padEnd(15)} escape=${m.escape}px cardRight=${m.cardRight} chipRight=${m.chipRight} ` +
      `ellipsis=${m.ellipsis} selfClip=${m.selfClip}px text-overflow=${m.textOverflow} overflow-x=${m.overflowX}`
  );
}

// The expected before/after, asserted rather than eyeballed. A fix that merely shrinks the escape
// is not a fix — the chip must end inside the card AND say so with an ellipsis.
const oldEscapes = result.old.escape > 0.5;
const newClean = result.neu.escape <= 0.5;
const newEllipsised = result.neu.ellipsis;
console.log(`\nOLD-ESCAPES=${oldEscapes} NEW-CLEAN=${newClean} NEW-ELLIPSIS=${newEllipsised}`);
if (oldEscapes && newClean && newEllipsised) {
  console.log('VERDICT: the proposed class string fixes the measured defect.');
  process.exit(0);
}
console.log('VERDICT: NOT the expected before/after — do not claim the fix on this run.');
process.exit(3);
