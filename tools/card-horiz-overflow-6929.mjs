// card-horiz-overflow-6929.mjs — does any card's ink run PAST its own card box at phone width?
//
// A screenshot cannot grade an overflow claim: a clipped node renders identically to a node that
// simply ends there, and `overflow:hidden` on an ancestor hides the evidence. So this reads the
// layout engine on two independent signals and reports a node only when it is text-bearing:
//
//   A. SELF-CLIP     scrollWidth > clientWidth  -> the node's own ink does not fit its own box
//   B. CARD-ESCAPE   getBoundingClientRect().right > card content-box right -> it leaves the card
//
// Signal B is the reader-visible one (text cut at the card edge). Signal A alone is normal and
// intended wherever `text-overflow: ellipsis` is set, so the ellipsis state is reported beside it
// and an ellipsised self-clip is NOT a finding.
//
// Deliberately NOT keyed on any class, testid or text of the suspected defect: it walks every
// element under every card and lets the numbers pick the subjects. A probe keyed on the bug's own
// markup can only ever express the FAIL.
//
// Usage: node card-horiz-overflow-6929.mjs <url> [widthPx]
// exit 0 = no escapes · 3 = at least one CARD-ESCAPE · 2 = usage/no cards found
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
if (!url) { console.error('usage: card-horiz-overflow-6929.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
await page.waitForTimeout(1500);

const out = await page.evaluate(() => {
  const r1 = (n) => Math.round(n * 10) / 10;

  // A "card" is any element that paints its own rounded, bordered/shadowed surface directly on the
  // feed column. Found by computed style, not by class name, so a card renamed tomorrow still counts.
  const cards = [...document.querySelectorAll('div, article, li, section')].filter((el) => {
    const cs = getComputedStyle(el);
    const b = el.getBoundingClientRect();
    if (b.width < 200 || b.height < 60) return false;
    if (parseFloat(cs.borderTopLeftRadius) < 6) return false;
    return cs.boxShadow !== 'none' || cs.borderTopWidth !== '0px';
  });

  const seen = new Set();
  const findings = [];
  // Counted, never silently dropped: a suppressed row must leave a trace, or a clean "0" cannot
  // be told from "the filter ate everything".
  let scrollable = 0;

  for (const card of cards) {
    const cs = getComputedStyle(card);
    const cb = card.getBoundingClientRect();
    // content box right edge = border box right - right border - right padding
    const contentRight = cb.right - parseFloat(cs.borderRightWidth) - parseFloat(cs.paddingRight);

    for (const el of card.querySelectorAll('*')) {
      if (seen.has(el)) continue;
      const text = (el.textContent || '').trim();
      if (!text) continue;
      // only leaf-ish text nodes, so a wrapper is not reported for its child's ink
      if ([...el.children].some((c) => (c.textContent || '').trim() === text)) continue;

      const b = el.getBoundingClientRect();
      if (b.width < 8 || b.height < 6) continue;

      const ecs = getComputedStyle(el);
      const selfClip = el.scrollWidth - el.clientWidth;
      const escape = b.right - contentRight;

      // Is the node outside the card because it is CLIPPED, or because it sits in a pane the
      // reader can scroll sideways? Both put `rect.right` past the card, and they are opposite
      // verdicts: one is text destroyed, the other is a table working as designed. Only the
      // ancestor chain can tell them apart -- the node's own `overflow-x` is `visible` in both
      // cases. Measured: /economics reports 38 escapes (one 184px out) and every one of them is
      // a scrollable heatmap row. Without this walk the probe cries wolf on every surface that
      // has a wide table, and a guard that cries wolf is not run twice.
      let scrollPane = null;
      for (let p = el.parentElement; p && p !== card.parentElement; p = p.parentElement) {
        const ox = getComputedStyle(p).overflowX;
        if (ox === 'auto' || ox === 'scroll') { scrollPane = p; break; }
        // A clipping ancestor settles it first: past this point nothing scrolls, it is cut.
        if (ox === 'hidden' || ox === 'clip') break;
      }

      if (escape > 1 && scrollPane) scrollable++;

      if ((escape > 1 && !scrollPane) || selfClip > 1) {
        seen.add(el);
        findings.push({
          kind: escape > 1 ? 'CARD-ESCAPE' : 'SELF-CLIP',
          escapePx: r1(escape),
          selfClipPx: selfClip,
          ellipsis: ecs.textOverflow === 'ellipsis',
          overflowX: ecs.overflowX,
          tag: el.tagName.toLowerCase(),
          cls: (el.className && el.className.baseVal !== undefined ? el.className.baseVal : String(el.className || '')).slice(0, 70),
          cardRight: r1(contentRight),
          nodeRight: r1(b.right),
          text: text.slice(0, 80),
        });
      }
    }
  }
  return { cardCount: cards.length, viewport: innerWidth, findings, scrollable };
});

await browser.close();

console.log(`cards=${out.cardCount} viewport=${out.viewport}px`);
const escapes = out.findings.filter((f) => f.kind === 'CARD-ESCAPE');
const clips = out.findings.filter((f) => f.kind === 'SELF-CLIP' && !f.ellipsis);
for (const f of out.findings) {
  console.log(
    `${f.kind} escape=${f.escapePx}px selfClip=${f.selfClipPx}px ellipsis=${f.ellipsis} ` +
    `overflowX=${f.overflowX} <${f.tag} class="${f.cls}"> cardRight=${f.cardRight} nodeRight=${f.nodeRight}\n    "${f.text}"`
  );
}
console.log(
  `\nCARD-ESCAPE=${escapes.length} SELF-CLIP(no-ellipsis)=${clips.length} ` +
  `suppressed-as-scrollable=${out.scrollable}`
);
if (out.cardCount === 0) process.exit(2);
process.exit(escapes.length ? 3 : 0);
