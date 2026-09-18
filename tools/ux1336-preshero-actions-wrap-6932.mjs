// ux1336-preshero-actions-wrap-6932.mjs — #6932: does wrapping `.presHeroActions` actually
// resolve the 17px spill, and is it inert above the breakpoint?
//
// WHY A PROBE AND NOT A SCREENSHOT. The finding is a 17px overhang of an interactive control
// past its card's content box. A phone-width screenshot shows a toggle near the edge; it cannot
// say whether the grey track crosses the rounded corner by 17px or sits 1px inside it. So this
// reads the layout engine — `getBoundingClientRect().right` of the control against the CARD's
// computed content-box right — and reports the number, screenshotting only as the human record.
//
// WHY IT MEASURES THE FIX BY INJECTION. `politics.module.css` already carries a fix of exactly
// this shape (#4651's `.presHeroHead { flex-wrap: wrap }`), and its comment records that it was
// "verified by injecting this rule into the live page". This continues that: the candidate rule
// is applied to the REAL production DOM, inside the REAL `@media (max-width: 720px)` it will
// ship in, so the measurement is of the rule and not of a model of it.
//
// 🪤 THE CLASS NAME IS HASHED AND MUST NOT BE HARD-CODED. CSS Modules mint
// `politics_presHeroActions__4UpBg`; the hash changes on any edit to the file, so a literal
// selector silently matches nothing and the AFTER arm reads "fixed" because no node was found.
// The subject is therefore located by class PREFIX in the live DOM and the resolved name is
// printed. Finding zero subjects is exit 2 (UNPAID), never a pass.
//
// THREE ARMS, and the third is the control:
//   390px BEFORE  — the defect, as filed
//   390px AFTER   — the same page with the candidate rule injected
//   1280px AFTER  — the rule is inside a 720px media query, so it must change NOTHING here
//
// Usage: node ux1336-preshero-actions-wrap-6932.mjs [baseUrl]
// exit 0 = spill resolved at 390 AND desktop unchanged · 1 = a claim failed · 2 = UNPAID
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

const base = (process.argv[2] || 'https://bainluck.com').replace(/\/$/, '');
const url = `${base}/politics`;

// The rule under test, verbatim as it will ship.
const CANDIDATE = 'flex-wrap: wrap;';

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

// 🪤 ONE BROWSER PER ARM. `--single-process` is in the house arg list, and under it a SECOND
// `newPage()` kills the target ("Target page, context or browser has been closed") — which reads
// as the site failing to load rather than as a harness limit. Four arms, four browsers.
/** Measure the hero head at one viewport, optionally with the candidate rule applied. */
async function measure(width, { inject }) {
  const browser = await chromium.launch({ headless: true, args });
  const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
  try {
    await page.waitForLoadState('networkidle', { timeout: 20000 });
  } catch { /* a polling page never idles; the DOM is laid out regardless */ }
  await page.waitForTimeout(2500);

  if (inject) {
    const applied = await page.evaluate((decl) => {
      const el = document.querySelector('[class*="presHeroActions"]');
      if (!el) return null;
      const cls = [...el.classList].find((c) => c.includes('presHeroActions'));
      const style = document.createElement('style');
      // The real shipping context: inside the file's existing 720px block.
      style.textContent = `@media (max-width: 720px) { .${cls} { ${decl} } }`;
      document.head.appendChild(style);
      return cls;
    }, CANDIDATE);
    if (!applied) { await browser.close(); return { subjectFound: false }; }
    await page.waitForTimeout(300);
  }

  const out = await page.evaluate(() => {
    const r1 = (n) => Math.round(n * 10) / 10;
    const pick = (frag) => document.querySelector(`[class*="${frag}"]`);

    const card = pick('presHero') && document.querySelector('[class*="presHero"]:not([class*="presHeroHead"]):not([class*="presHeroActions"]):not([class*="presHeroQ"]):not([class*="presHeroMeta"])');
    const head = pick('presHeroHead');
    const actions = pick('presHeroActions');
    const toggle = pick('sourceToggle');
    if (!card || !head || !actions) return { subjectFound: false };

    const cs = getComputedStyle(card);
    const cardRect = card.getBoundingClientRect();
    // Content-box right: the card's own padding is where its content is allowed to end.
    const cardContentRight = cardRect.right - parseFloat(cs.paddingRight) - parseFloat(cs.borderRightWidth);

    const question = head.firstElementChild;
    const escapeOf = (el) => (el ? r1(el.getBoundingClientRect().right - cardContentRight) : null);

    return {
      subjectFound: true,
      resolvedClass: [...actions.classList].find((c) => c.includes('presHeroActions')),
      cardContentRight: r1(cardContentRight),
      actionsRight: r1(actions.getBoundingClientRect().right),
      actionsEscape: escapeOf(actions),
      toggleEscape: escapeOf(toggle),
      headSelfClip: head.scrollWidth - head.clientWidth,
      // Did #4651's wrap fire? If the controls share the question's line, tops match.
      controlsOnOwnLine:
        question != null &&
        Math.round(actions.getBoundingClientRect().top) >
          Math.round(question.getBoundingClientRect().bottom) - 2,
      actionsHeight: r1(actions.getBoundingClientRect().height),
      docScrollWidth: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
    };
  });

  if (out.subjectFound) {
    const tag = `${width}-${inject ? 'AFTER' : 'BEFORE'}`;
    out.shot = `artifacts/ux-1336/6932-${tag}-politics.png`;
    await page.screenshot({ path: out.shot, fullPage: false });
  }
  await browser.close();
  return out;
}

const before390 = await measure(390, { inject: false });
const after390 = await measure(390, { inject: true });
const after1280 = await measure(1280, { inject: true });
const before1280 = await measure(1280, { inject: false });

if (!before390.subjectFound || !after390.subjectFound) {
  console.error('🔴 UNPAID: the presidential hero card was not on the page (no `presHeroActions`).');
  console.error('   The card renders only when the politics payload carries candidates. Re-run later,');
  console.error('   or pick a moment when /politics serves the Presidential 2028 hero.');
  process.exit(2);
}

const row = (label, m) =>
  `${label.padEnd(14)} viewport=${String(m.viewport).padStart(4)}  cardContentRight=${m.cardContentRight}  ` +
  `actionsRight=${m.actionsRight}  ESCAPE=${m.actionsEscape}px  toggleEscape=${m.toggleEscape}px  ` +
  `headSelfClip=${m.headSelfClip}px  actionsH=${m.actionsHeight}  docScrollWidth=${m.docScrollWidth}`;

console.log(`subject: .${before390.resolvedClass}   rule: { ${CANDIDATE} }   url: ${url}`);
console.log(`#4651's wrap fired (controls on their own line at 390): ${before390.controlsOnOwnLine}`);
console.log(row('390 BEFORE', before390));
console.log(row('390 AFTER', after390));
console.log(row('1280 BEFORE', before1280));
console.log(row('1280 AFTER', after1280));
console.log(`shots: ${[before390, after390, before1280, after1280].map((m) => m.shot).join('  ')}`);

const fails = [];

// 1 · The defect was present to begin with. Without this the AFTER proves nothing.
if (!(before390.actionsEscape > 1)) {
  fails.push(`PREMISE: no spill to fix at 390 (escape=${before390.actionsEscape}px). Specimen rotated or already fixed.`);
}
// 2 · The rule resolves it. Inside the card, not merely smaller.
if (!(after390.actionsEscape <= 0)) {
  fails.push(`the controls still leave the card at 390: escape=${after390.actionsEscape}px`);
}
if (!(after390.headSelfClip === 0)) {
  fails.push(`the head still self-clips at 390: ${after390.headSelfClip}px`);
}
// 3 · It resolves by WRAPPING, not by shrinking or hiding anything.
if (!(after390.actionsHeight > before390.actionsHeight)) {
  fails.push(
    `the controls did not wrap (height ${before390.actionsHeight} -> ${after390.actionsHeight}). ` +
      `A fix that makes the row FIT by shrinking a control is a different fix than the one claimed.`,
  );
}
// 4 · THE CONTROL ARM. The rule lives in a 720px media query, so desktop must be untouched.
for (const k of ['actionsEscape', 'actionsRight', 'actionsHeight', 'docScrollWidth']) {
  if (before1280[k] !== after1280[k]) {
    fails.push(`desktop moved: ${k} ${before1280[k]} -> ${after1280[k]} at 1280px (the rule must be inert here)`);
  }
}

if (fails.length) {
  console.log('');
  for (const f of fails) console.log(`🔴 ${f}`);
  console.log(`EXIT 1`);
  process.exit(1);
}
console.log('\n✅ 390: spill resolved by wrapping · head no longer self-clips · 1280 byte-identical');
process.exit(0);
