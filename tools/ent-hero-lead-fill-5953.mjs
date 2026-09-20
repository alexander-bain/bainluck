// ent-hero-lead-fill-5953.mjs — why the /entertainment lead hero card holds space it cannot fill (#5953).
//
// lane1b measured the HOLE (card.bottom − paddingBottom − deepest child bottom = 227px at 1280).
// A hole is a symptom and a `min-height` is only its nearest cause. This reads the layout engine to
// decide between the two candidate mechanisms, which want opposite fixes:
//
//   A) RESERVATION — `.heroCardLead { min-height }` / the grid's 2-row span make the box taller than
//      its content, and the content is correctly laid out inside it. Fix = change the reservation.
//   B) INERT SPACER — the card IS a flex column and DOES contain a `flex: 1` spacer written to push
//      the body down, but the spacer is not a child of the flex container (it sits inside a wrapper
//      element that is itself the single flex item), so it grows nothing. Fix = the wrapper.
//
// The two are told apart by ONE reading: the flex chain. For each card we print the container's
// computed `display`/`flex-direction`, then walk its children and ask of each whether it is a flex
// ITEM of that container and what `flex-grow` it resolves to. A spacer with `flex-grow: 1` whose
// PARENT is not the flex container is mechanism B and cannot grow however much space is reserved.
//
// The non-lead cards are the control and are the whole weight of the finding: they render the same
// `HeroCardContent`, so if their spacer grows and the lead's does not, the difference is structural
// and not a property of the content.
//
// usage: node ent-hero-lead-fill-5953.mjs [url] [widthPx] [apiCacheDir]
// exit 0 = read OK, no reserved-and-empty block · 2 = bad args · 3 = the hero never rendered
//      4 = #7356, the lead card reserves space it cannot fill · 5 = an upstream API read failed
//
// #7356 — A LOOPBACK URL IS SERVED DIRECTLY AND ITS API CALLS ARE CACHED.
// The launch line below sets `--proxy-bypass-list=<-loopback>`, i.e. do NOT bypass the proxy for
// loopback, which is right for production and makes `http://127.0.0.1:PORT` unreachable — so this
// tool could only ever measure DEPLOYED code, and a before/after on an unmerged CSS branch had no
// rig. For a loopback URL the bypass is inverted (as `tools/look-local.mjs` does) and the page's
// `api.bainluck.com` fetches are fulfilled by `curl`, which has this process's egress.
// `apiCacheDir` is not an optimisation and should always be passed for a before/after: this tool's
// whole output is HEIGHTS, and heights are a function of the lead market's title, hook and outcome
// count. Two runs minutes apart against a live feed get different markets and the difference lands
// in the numbers looking exactly like the change under review. Run BEFORE first to populate, AFTER
// second to replay; the census at the end says which happened.

import { createRequire } from 'module';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'fs';
import path from 'node:path';

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

const url = process.argv[2] || 'https://bainluck.com/entertainment';
const width = Number(process.argv[3] || 1280);
const cacheDir = process.argv[4] || null;
const isLocal = /^https?:\/\/(127\.0\.0\.1|localhost)(:|\/|$)/.test(url);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  args.push(isLocal ? '--proxy-bypass-list=127.0.0.1;localhost' : '--proxy-bypass-list=<-loopback>');
}

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });

let servedFromCache = 0;
let fetchedUpstream = 0;
if (isLocal) {
  if (cacheDir) mkdirSync(cacheDir, { recursive: true });
  await page.route('**://api.bainluck.com/**', async (route) => {
    const target = route.request().url();
    const key = createHash('sha1').update(target).digest('hex').slice(0, 16);
    const file = cacheDir ? path.join(cacheDir, `${key}.json`) : null;
    const ok = (body) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'access-control-allow-origin': '*' },
      body,
    });
    if (file && existsSync(file)) {
      servedFromCache++;
      return ok(readFileSync(file, 'utf8'));
    }
    /* `curl -sS` EXITS 0 ON AN HTTP ERROR, so without `-w` the 60/minute rate-limit body
       (`{"detail":"Rate limit exceeded: 60/minute"}`) is a 200 as far as this process is
       concerned — it gets CACHED, replayed to both the before and the after build, and the two
       runs agree perfectly on a page that rendered no card at all. Read the status, refuse to
       cache anything that is not 2xx, and make the run die rather than measure a stub. */
    let body;
    try {
      body = execFileSync('curl', ['-sS', '--max-time', '45', '-w', '\n%{http_code}', target], {
        maxBuffer: 64 * 1024 * 1024,
        encoding: 'utf8',
      });
    } catch (err) {
      console.error(`UPSTREAM FAILED ${target}: ${err.message}`);
      await browser.close();
      process.exit(5);
    }
    const nl = body.lastIndexOf('\n');
    const status = Number(body.slice(nl + 1));
    body = body.slice(0, nl);
    if (!(status >= 200 && status < 300)) {
      console.error(`UPSTREAM ${status} ${target}: ${body.slice(0, 200)}`);
      await browser.close();
      process.exit(5);
    }
    fetchedUpstream++;
    if (file) writeFileSync(file, body);
    return ok(body);
  });
}

await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });

/* The hero grid is the first grid on the page whose class carries `heroGrid` (CSS modules hash the
   name, so match on the substring rather than an exact class).

   WAIT FOR IT RATHER THAN ASKING ONCE. `/entertainment` is client-rendered — the served HTML carries
   no card markup at all — so `waitUntil: 'networkidle'` can return before React has painted the
   grid. Against a LOCAL build the API is routed by this file and the render lands inside the idle
   window, so a single `evaluate` was enough and the gap never showed; against PRODUCTION this exited
   3 (`NO HERO GRID`) on a page that renders the grid perfectly well a moment later (ux/1376, paying
   #7356's after-check). A poll turns "I looked too early" — which reads exactly like "the page is
   broken" — back into the absence it claims to report. */
const found = await page
  .waitForFunction(
    () =>
      [...document.querySelectorAll('div')].some((d) =>
        [...d.classList].some((c) => /heroGrid/.test(c))
      ),
    null,
    { timeout: 20000 }
  )
  .then(() => true)
  .catch(() => false);
if (!found) {
  console.error('NO HERO GRID — the page did not render `.heroGrid`');
  await browser.close();
  process.exit(3);
}

const report = await page.evaluate(() => {
  const grid = [...document.querySelectorAll('div')].find((d) =>
    [...d.classList].some((c) => /heroGrid/.test(c))
  );
  const cs = (n) => getComputedStyle(n);

  // Deepest rendered bottom under `node`, ignoring zero-area nodes (a 0px spacer is not content).
  const deepestBottom = (node) => {
    let b = -Infinity;
    for (const d of node.querySelectorAll('*')) {
      const r = d.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) b = Math.max(b, r.bottom);
    }
    return b;
  };

  const cards = [];
  for (const cell of grid.children) {
    // The card is the cell itself when the cell carries `heroCard*`, else its first element child
    // (the sibling pattern wraps the card in a <Link>).
    const isCard = (n) => n && [...n.classList].some((c) => /heroCard/.test(c));
    const card = isCard(cell) ? cell : [...cell.children].find(isCard) || cell;

    const rect = card.getBoundingClientRect();
    const style = cs(card);
    const padB = parseFloat(style.paddingBottom) || 0;
    const gap = Math.round(rect.bottom - padB - deepestBottom(card));

    // Walk the card's own children: these are its flex items.
    const items = [...card.children].map((ch) => {
      const s = cs(ch);
      const r = ch.getBoundingClientRect();
      return {
        tag: ch.tagName,
        display: s.display,
        flexGrow: s.flexGrow,
        h: Math.round(r.height),
        kids: ch.children.length,
      };
    });

    // Find every `flex-grow: 1` spacer ANYWHERE under the card, and say whether its parent is the
    // flex container. That is the whole discriminator between mechanism A and mechanism B.
    const spacers = [...card.querySelectorAll('*')]
      .filter((n) => cs(n).flexGrow === '1' && n.children.length === 0 && !n.textContent.trim())
      .map((n) => {
        const p = n.parentElement;
        const ps = cs(p);
        return {
          h: Math.round(n.getBoundingClientRect().height),
          parentTag: p.tagName,
          parentIsFlexColumn: ps.display.includes('flex') && ps.flexDirection === 'column',
          parentIsTheCard: p === card,
        };
      });

    cards.push({
      lead: [...card.classList].some((c) => /heroCardLead/.test(c)),
      h: Math.round(rect.height),
      minH: style.minHeight,
      display: style.display,
      dir: style.flexDirection,
      gap,
      items,
      spacers,
    });
  }
  return { width: innerWidth, cards };
});

console.log(`\n/entertainment hero @ ${report.width}px — ${report.cards.length} cards\n`);
let verdictB = false;
for (const c of report.cards) {
  const tag = c.lead ? 'LEAD ' : 'side ';
  console.log(
    `${tag} h=${c.h}px minH=${c.minH} ${c.display}/${c.dir}  HOLE=${c.gap}px`
  );
  for (const it of c.items) {
    console.log(`        item <${it.tag}> ${it.display} grow=${it.flexGrow} h=${it.h} kids=${it.kids}`);
  }
  for (const sp of c.spacers) {
    /* #7356 — THE DISCRIMINATOR WAS `parentIsTheCard`, AND #5953's OWN FIX MADE IT FALSE.
       This tool was written against the broken page, where the card element and the flex
       container were the same element, so "is the spacer a child of the card" and "can the
       spacer grow" were the same question. The fix made the lead's <a> the flex column, so
       they came apart: on the FIXED page the lead's spacer is a child of the <a>, not of the
       card, and this line printed `h=196px ... -> INERT` at 1280px and stamped MECHANISM B
       under it. A 196px-tall inert spacer is a contradiction on the face of the line, and it
       would have sent the next reader back to re-fix a wrapper that is already right.
       `parentIsFlexColumn` is the question that was always meant — a `flex: 1` item grows iff
       its parent is the flex container — and it was already being computed and printed. */
    const ok = sp.parentIsFlexColumn
      ? `GROWS (child of the flex column${sp.parentIsTheCard ? ', which is the card' : ''})`
      : 'INERT (parent is not a flex column)';
    console.log(
      `        spacer grow=1 h=${sp.h}px parent=<${sp.parentTag}> flexCol=${sp.parentIsFlexColumn} -> ${ok}`
    );
    if (!sp.parentIsFlexColumn && c.lead) verdictB = true;
  }
  console.log('');
}

const lead = report.cards.find((c) => c.lead);
const sides = report.cards.filter((c) => !c.lead);
const sideHoles = sides.map((c) => c.gap);
console.log(`lead hole  : ${lead ? lead.gap : 'n/a'}px`);
console.log(`side holes : ${sideHoles.join(', ')}px`);
console.log(
  `VERDICT    : ${
    verdictB
      ? 'MECHANISM B — the lead card has a flex:1 spacer that is NOT a child of the flex container, so it cannot grow. The reservation is not the cause; the wrapper is.'
      : 'MECHANISM A — every spacer is a direct flex item; the hole is the reservation itself.'
  }`
);

/* #7356 — `gap` ABOVE MEASURES THE HOLE AT THE BOTTOM, AND #5953's FIX MOVED THE HOLE.
   Before #5953 the lead's spacer was inert, so the surplus piled up as trailing whitespace and
   `card.bottom − paddingBottom − deepestChildBottom` saw all 227px of it. Once the spacer could
   grow it absorbed the surplus in the MIDDLE of the card instead, between the title and the first
   outcome — so `gap` fell to 1px and this tool reported a clean card while 55px of blank sat in
   plain sight at 390px. The tool was not wrong about what it measured; it measured the wrong end.

   The reservation surplus is the spacer's own height, and it is only a DEFECT when the reservation
   is what set the card's height. At 1280px the grid's two-row span sets it (421px against a 280px
   min-height) and a tall spacer is the spacer doing its job. When the card's height IS its
   min-height, every pixel the spacer holds is reserved space the content could not fill. */
let exit = 0;
if (lead) {
  const minH = Math.round(parseFloat(lead.minH) || 0);
  const surplus = Math.max(0, ...lead.spacers.map((s) => s.h), 0);
  const reservationBinds = minH > 0 && Math.abs(lead.h - minH) <= 1;
  console.log(
    `lead blank : ${surplus}px reserved-and-empty  (card ${lead.h}px, min-height ${minH}px — ` +
      `${reservationBinds ? 'THE RESERVATION sets the height' : 'the GRID sets the height'})`
  );
  if (reservationBinds && surplus > 8) {
    console.log(
      `\n🔴 #7356: the lead card reserves ${surplus}px it cannot fill ` +
        `(${Math.round((surplus / lead.h) * 100)}% of the card) at ${report.width}px.`
    );
    exit = 4;
  }
}

if (isLocal) {
  // `servedFromCache: N, fetchedUpstream: 0` on the AFTER run is the line that proves the only
  // variable between the two measurements was the code.
  console.log(`api        : servedFromCache ${servedFromCache}, fetchedUpstream ${fetchedUpstream}`);
}

await browser.close();
process.exit(exit);
