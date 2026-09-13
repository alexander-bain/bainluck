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
// usage: node ent-hero-lead-fill-5953.mjs [url] [widthPx]
// exit 0 = read OK (verdict printed) · 2 = bad args · 3 = the hero never rendered

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

const url = process.argv[2] || 'https://bainluck.com/entertainment';
const width = Number(process.argv[3] || 1280);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });
await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });

// The hero grid is the first grid on the page whose class carries `heroGrid` (CSS modules hash the
// name, so match on the substring rather than an exact class).
const found = await page.evaluate(() => {
  const el = [...document.querySelectorAll('div')].find((d) =>
    [...d.classList].some((c) => /heroGrid/.test(c))
  );
  return !!el;
});
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
    const ok = sp.parentIsTheCard ? 'GROWS (child of the card)' : 'INERT (parent is not the flex container)';
    console.log(
      `        spacer grow=1 h=${sp.h}px parent=<${sp.parentTag}> flexCol=${sp.parentIsFlexColumn} -> ${ok}`
    );
    if (!sp.parentIsTheCard && c.lead) verdictB = true;
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

await browser.close();
