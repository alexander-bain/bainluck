// escaping-absolutes-4631.mjs — find scrollers whose absolutely-positioned children ESCAPE their clip.
//
// The companion to `overflow-culprit-4631.mjs`, and the reason both exist (#4631, ux/1168, ux/1169):
//
// `overflow-culprit` answers "what is widening THIS page RIGHT NOW" — it is causal, but it only
// speaks when a page is already broken, and it names the deepest guilty subtree rather than the
// class of defect. This one answers the structural question instead: "which rails are BUILT so
// that an absolutely-positioned child can escape the clip?" It fires on rails that are not
// currently overflowing, which is the whole point — a rail one long player name away from the
// #4631 symptom is a bug that has not been triggered yet, not a healthy rail.
//
// THE RULE IT ENCODES
//
// An absolutely-positioned element is clipped by an ancestor's `overflow` ONLY if that ancestor is
// in its CONTAINING BLOCK chain — and a containing block is established by a POSITIONED ancestor,
// never by a merely overflowing one. So an `overflow-x:auto` rail that is itself `position:static`
// does not clip its own absolute descendants: they resolve past it to whatever positioned ancestor
// sits further up (typically a `relative` wrapper just OUTSIDE the rail) and lay out against the
// document. Tailwind's `sr-only` is `position:absolute`, so this bites hardest on screen-reader
// labels — content that is invisible by construction silently widening the document.
//
// On `/tournaments/us-open` that was 30 labels each parking a 1px box at document x=461: 71px of
// horizontal scroll on a 390px phone, with every rect-based probe pointing at the innocent grid.
//
// WHY IT WALKS THE CHAIN RATHER THAN READING `offsetParent`
//
// `offsetParent` is close to "nearest positioned ancestor" but not equal to it — it is null for
// `display:none` and `position:fixed` elements, and it skips to the body in cases we care about.
// Walking up from the absolute element and asking which comes first, a positioned ancestor or the
// scroller, is the definition itself, so it needs no special-casing.
//
// WHAT A REPORTED ROW MEANS, AND WHAT IT DOES NOT
//
// A row means the rail cannot clip that child. It does NOT prove the page is currently wider than
// the viewport — the escapee may happen to sit inside the viewport today. Rank by `escapeeRight`
// (how far past the viewport the escaped boxes actually reach) and confirm any fix with
// `overflow-culprit-4631.mjs`, which measures the document rather than the structure.
//
// A `sticky` ancestor is POSITIONED and therefore a perfectly good containing block: a label inside
// a `sticky` table cell is already clipped correctly and is NOT reported. That case is why the
// class list cannot be grepped for this — `relative` is not the only thing that fixes it.
//
// Usage: node escaping-absolutes-4631.mjs <url> [widthPx]
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
if (!url) {
  console.error('usage: node escaping-absolutes-4631.mjs <url> [widthPx]');
  process.exit(2);
}

// The same launch args as `overflow-culprit-4631.mjs`, and they are load-bearing rather than
// copied: without `--single-process` this sandbox refuses the Mach port rendezvous and Chromium
// dies before the first navigation (`bootstrap_check_in ... Permission denied (1100)`), and
// without the proxy args there is no egress to production at all.
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });

try {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
  // Rails are frequently below the fold and lazily hydrated; a rail that has not mounted cannot be
  // judged, and reporting it as clean would be the same false negative the rect scans gave us.
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(1200);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(600);

  const report = await page.evaluate((viewportWidth) => {
    const label = (el) => {
      const cls = (el.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 6).join('.');
      const id = el.id ? `#${el.id}` : '';
      const testid = el.getAttribute('data-testid');
      return el.tagName.toLowerCase() + id + (testid ? `[data-testid="${testid}"]` : '') + (cls ? '.' + cls : '');
    };

    const clips = (v) => v === 'auto' || v === 'scroll' || v === 'hidden' || v === 'clip';

    const all = Array.from(document.querySelectorAll('*'));

    // The rails: elements that clip horizontally but establish no containing block, so their own
    // absolute descendants are not theirs to clip.
    const rails = all.filter((el) => {
      const cs = getComputedStyle(el);
      return clips(cs.overflowX) && cs.position === 'static';
    });

    const findings = [];

    for (const rail of rails) {
      const escapees = [];

      for (const el of rail.querySelectorAll('*')) {
        const cs = getComputedStyle(el);
        if (cs.position !== 'absolute') continue;

        // Which comes first walking up: a positioned ancestor, or the rail itself? If the rail
        // comes first, the containing block is outside it and the rail's overflow never applies.
        let node = el.parentElement;
        let contained = false;
        while (node && node !== rail) {
          if (getComputedStyle(node).position !== 'static') { contained = true; break; }
          node = node.parentElement;
        }
        if (contained) continue;

        const r = el.getBoundingClientRect();
        escapees.push({
          selector: label(el),
          srOnly: el.classList.contains('sr-only'),
          text: (el.textContent || '').trim().slice(0, 60),
          right: Math.round(r.right),
        });
      }

      if (escapees.length === 0) continue;

      const railRect = rail.getBoundingClientRect();
      findings.push({
        rail: label(rail),
        railChain: (() => {
          const chain = [];
          for (let n = rail; n && n !== document.body; n = n.parentElement) chain.unshift(label(n));
          return chain.slice(-4);
        })(),
        railScrolls: rail.scrollWidth > rail.clientWidth,
        railScrollWidth: rail.scrollWidth,
        railClientWidth: rail.clientWidth,
        railRight: Math.round(railRect.right),
        escapeeCount: escapees.length,
        srOnlyCount: escapees.filter((e) => e.srOnly).length,
        // How far past the viewport the escaped boxes actually reach — the triage number.
        escapeeRight: Math.max(...escapees.map((e) => e.right)),
        sample: escapees.slice(0, 3),
      });
    }

    findings.sort((a, b) => b.escapeeRight - a.escapeeRight);

    return {
      viewport: viewportWidth,
      documentScrollWidth: document.documentElement.scrollWidth,
      overflow: Math.max(0, document.documentElement.scrollWidth - viewportWidth),
      railsChecked: rails.length,
      findings,
    };
  }, width);

  console.log(JSON.stringify({ url, ...report }, null, 2));
} finally {
  await browser.close();
}
