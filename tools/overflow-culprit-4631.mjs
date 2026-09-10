// overflow-culprit-4631.mjs — attribute a page's horizontal overflow to the element that CAUSES it.
//
// Why this exists rather than another rect scan (#4631, ux/1168):
//
// The obvious probe — "list every element whose right edge passes the viewport" — is the trap.
// On `/tournaments/us-open` at 390px it returns 68 elements, and every single one of them is a
// correctly-clipped child of an `overflow-x:auto` snap rail. Filtering to elements with no
// clipping ancestor returns ZERO. So the rect scan can prove the grid is innocent but cannot name
// the guilty party, because the guilty party need not have an escaping rect at all: a `100vw`
// under a scrollbar, a negative margin, a fixed-position bar with an unshrinkable child and a
// `min-width` on a flex item all widen the document while every rect still looks reasonable.
//
// The only causal test is COUNTERFACTUAL: hide a subtree and ask whether the overflow went away.
// That is what this does — a top-down walk that, at each level, sets `display:none` on one child
// at a time, re-reads `document.documentElement.scrollWidth`, and restores it. A child whose
// removal collapses scrollWidth back to the viewport is a cause. The walk then descends INTO that
// child, so the answer is the deepest element still responsible, not its wrapper.
//
// Reports every independent cause, not just the first: two 71px overhangs from unrelated subtrees
// would each individually "fix" the page only if the other is innocent, so a subtree is reported
// when hiding it alone removes the overflow, and the walk continues across its siblings.
//
// Usage: node overflow-culprit-4631.mjs <url> [widthPx]
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
if (!url) { console.error('usage: overflow-culprit-4631.mjs <url> [widthPx]'); process.exit(2); }

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
await page.waitForTimeout(1500);

const out = await page.evaluate(() => {
  const doc = document.documentElement;
  const client = doc.clientWidth;
  const before = doc.scrollWidth;
  const overflow = before - client;

  // A page with nothing to attribute must report nothing (ux/1169). The walk's test is
  // "hiding this subtree brings scrollWidth back to `client`" — when there is no overflow that
  // is already true of EVERY element, so the probe happily indicts the first thing it touches.
  // The first sweep to use it named a cookie banner and a 🍀 in the logo as causes on two pages
  // whose scrollWidth was exactly 390, which is a confident answer to a question nobody asked.
  if (overflow <= 0) return { client, scrollWidth: before, overflow: 0, causes: [] };

  const label = (el) => {
    const cls = (el.getAttribute('class') || '').split(/\s+/).filter(Boolean).slice(0, 6).join('.');
    const id = el.id ? `#${el.id}` : '';
    const testid = el.getAttribute('data-testid');
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return {
      tag: el.tagName.toLowerCase() + id + (cls ? '.' + cls : '') + (testid ? `[data-testid=${testid}]` : ''),
      rect: { left: +r.left.toFixed(1), right: +r.right.toFixed(1), width: +r.width.toFixed(1) },
      position: cs.position,
      overflowX: cs.overflowX,
      minWidth: cs.minWidth,
      width: cs.width,
      marginLeft: cs.marginLeft,
      marginRight: cs.marginRight,
      transform: cs.transform === 'none' ? 'none' : cs.transform,
      text: (el.textContent || '').trim().slice(0, 70),
    };
  };

  // Hiding an element and re-reading scrollWidth is the whole test. Restore exactly what was
  // there — an inline `display` set by the app must survive the probe.
  const withHidden = (el, fn) => {
    const prev = el.style.display;
    const had = el.style.getPropertyValue('display');
    el.style.setProperty('display', 'none', 'important');
    doc.getBoundingClientRect(); // force layout
    const v = fn();
    if (had) el.style.setProperty('display', prev);
    else el.style.removeProperty('display');
    doc.getBoundingClientRect();
    return v;
  };

  const causes = [];
  const TOL = 1; // sub-pixel: a page is "fixed" if it comes back within 1px of the viewport

  const walk = (el, depth) => {
    if (depth > 25) return;
    const kids = Array.from(el.children).filter((k) => {
      const cs = getComputedStyle(k);
      return cs.display !== 'none' && cs.visibility !== 'hidden';
    });
    let descended = false;
    for (const kid of kids) {
      const after = withHidden(kid, () => doc.scrollWidth);
      if (after <= client + TOL) {
        // Hiding this subtree alone removes the whole overflow -> it is a cause.
        // Descend to find the deepest element that is still solely responsible.
        const deeper = [];
        const sub = (node, d) => {
          if (d > 25) return;
          for (const c of Array.from(node.children)) {
            const cs = getComputedStyle(c);
            if (cs.display === 'none' || cs.visibility === 'hidden') continue;
            const a2 = withHidden(c, () => doc.scrollWidth);
            if (a2 <= client + TOL) { deeper.push(c); sub(c, d + 1); return; }
          }
        };
        sub(kid, depth + 1);
        const deepest = deeper.length ? deeper[deeper.length - 1] : kid;
        causes.push({
          culprit: label(deepest),
          chain: [kid, ...deeper].slice(0, -1).map((n) => label(n).tag),
          scrollWidthWhenHidden: after,
        });
        descended = true;
      }
    }
    // No single child accounts for it -> the overflow is this element's own box or is shared.
    if (!descended && el === doc) causes.push({ culprit: label(el), note: 'no single subtree accounts for the overflow', scrollWidthWhenHidden: before });
  };

  walk(document.body, 0);

  return { client, scrollWidth: before, overflow, causes };
});

console.log(JSON.stringify(out, null, 2));
await browser.close();
