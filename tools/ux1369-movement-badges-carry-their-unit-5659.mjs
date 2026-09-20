#!/usr/bin/env node
/**
 * #5659 — a movement badge prints a bare number with no unit.
 *
 * WHAT THE READER SEES, on the card in the issue:
 *
 *     Above 98      ▲45.0   ███████░░   89%
 *     Above 101     ▲59.5   ██████░░░   83%
 *
 * `movement: 0.45` is a probability delta in 0-1 units, so `45.0` is 45
 * percentage POINTS — a move further than the whole remaining distance to
 * certainty — printed with no unit, in a column between a label and a number
 * that IS a percent. The reader has nothing to tell them what 45.0 is, and the
 * neighbour makes it read as a percentage.
 *
 * THE DETECTOR IS THE ARROW, NOT THE COMPONENT. Every surface in this family
 * prefixes the magnitude with a direction glyph (▲ ▼ ↑ ↓ + -), so the rendered
 * signature of the defect is: a direction glyph, a number, and then anything
 * other than a unit. That reads the three repaired surfaces and any future one
 * without knowing which component drew it.
 *
 * WHY IT DOES NOT FIRE ON A PERCENTAGE. A badge reading `▲8.5%` is the OTHER
 * half of this family (#5666), already closed and separately guarded; a bare
 * `%` is a unit, wrong but present, and this probe is keyed on absence. It is
 * reported separately rather than silently counted as clean.
 *
 * exit 0  every badge on the page carries a unit
 * exit 3  at least one badge prints a bare number
 * exit 4  the page drew no movement badge at all (no specimen — NOT a pass)
 * exit 2  usage / load failure
 *
 * usage: node ux1369-movement-badges-carry-their-unit-5659.mjs <url> [width]
 *
 * EXIT 0 IS NOT BY ITSELF AN AFTER-CHECK. It says the badges THIS PAGE DREW
 * carry units — not that any of the three repaired components rendered. The
 * team page is the trap: it draws its own already-correct `pts` badge from
 * team/[team]/page.tsx:486, so it scored a clean exit 0 against production
 * while the fix was still unmerged. Read the context column and name the
 * surface you actually saw, or the pass is about someone else's code.
 *
 * SELF-TEST, both directions, no network (run before trusting a live read):
 *   node ux1369-movement-badges-carry-their-unit-5659.mjs \
 *     file://$PWD/tools/ux1369-movement-badges-selftest-5659.html 390
 *     → exit 3, bare: 1, 3 matches discarded as rung labels
 *   sed '/id="bare"/d' on that fixture
 *     → exit 0, bare: 0, the same 2 badges still found
 * The fixture carries one of each classifier arm on purpose; `+9.7 pts` has NO
 * accessible name, so it is detected by mono-type-in-a-movement-colour alone.
 * If that arm is ever dropped, TeamChampionshipPath becomes invisible here.
 */
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

const [url, widthArg] = process.argv.slice(2);
if (!url) {
  console.error('usage: <url> [width]');
  process.exit(2);
}
const width = Number(widthArg || 390);

const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxy) {
  args.push(`--proxy-server=${proxy}`);
  if (!/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])([:/]|$)/.test(url)) {
    args.push('--proxy-bypass-list=<-loopback>');
  }
}

const browser = await chromium.launch({ args });
const page = await (await browser.newContext({ viewport: { width, height: 844 } })).newPage();

let found;
try {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 90_000 });
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.setViewportSize({ width, height: Math.min(h, 30_000) });
  await page.waitForTimeout(2500);

  found = await page.evaluate(() => {
    // A direction glyph followed by a magnitude. `[+-]` only counts when it is
    // glued to a digit, so ordinary prose and hyphenated names cannot match.
    const BADGE = /([▲▼↑↓]|(?<![\w%])[+-](?=\d))\s?(\d{1,3}(?:\.\d)?)/;

    // A THRESHOLD LABEL IS NOT A MOVEMENT BADGE. Measured on /economics, which
    // draws "-0.2%", "<-0.3%" and "-0.3% to -0.1%" — GDP/inflation rung labels
    // whose leading MINUS SIGN the `[+-]` arm above happily matched. They are
    // not moves, and counting them is worse than counting nothing: three of
    // them lift a page out of exit 4 ("no specimen") and let a run with no real
    // badge on it report "0 bare" as a pass. A range or a comparator is the
    // shape of a rung, never of a move.
    const RUNG = /(\bto\b|^[<>≤≥≈~]|[–—])/;

    // WHAT MAKES IT A MOVE. `-0.2%` on its own is genuinely ambiguous as text,
    // so the classifier does not rely on text alone. Every surface in this
    // family carries at least one of these three marks, and a rung label
    // carries none of them:
    //   (a) a direction glyph                   — QuantityGroup ▲▼, FuturesCard ↑↓
    //   (b) an accessible name saying "points"  — QuantityGroup, FuturesCard
    //   (c) mono type in a movement colour      — TeamChampionshipPath, which has
    //       NO accessible name at all (measured: it is the one surface of the
    //       three that never spoke its unit to a screen reader).
    const MOVE_COLOUR = /\b(text-accent-live|text-accent-danger|text-emerald-\d|text-red-\d)\b/;
    const SPOKEN_MOVE = /\b(up|down|moved?)\b[\s\S]*\bpoints?\b/i;

    const out = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    for (let el = walker.nextNode(); el; el = walker.nextNode()) {
      // Leaf-ish only: the smallest element that contains the whole badge, so
      // one badge is not reported once per ancestor.
      const txt = (el.textContent || '').trim();
      if (!txt || txt.length > 60) continue;
      if (!BADGE.test(txt)) continue;
      if (Array.from(el.children).some((c) => BADGE.test((c.textContent || '').trim()))) continue;

      const m = txt.match(BADGE);
      const after = txt.slice(txt.indexOf(m[0]) + m[0].length);
      const cls = typeof el.className === 'string' ? el.className : '';
      const aria = el.getAttribute('aria-label') || el.getAttribute('title') || '';

      const glyph = /[▲▼↑↓]/.test(m[1]);
      const spoken = SPOKEN_MOVE.test(aria);
      const styled = /\bfont-mono\b/.test(cls) && MOVE_COLOUR.test(cls);
      const isMove = glyph || spoken || styled;
      const rung = RUNG.test(txt);

      // WHERE IT WAS DRAWN. Prod React emits no component names, so the only
      // honest attribution is the surrounding DOM. Without it "0 bare" on a
      // team page is unreadable: that page draws its OWN correct `pts` badge
      // (team/[team]/page.tsx:486) as well as TeamChampionshipPath's, and the
      // probe cannot otherwise tell you which one it just scored.
      const marks = [];
      for (let a = el, i = 0; a && i < 6; a = a.parentElement, i++) {
        for (const at of ['data-card-format', 'data-testid', 'data-surface']) {
          const v = a.getAttribute && a.getAttribute(at);
          if (v) marks.push(`${at}=${v}`);
        }
      }
      let heading = '';
      for (let a = el; a && !heading; a = a.parentElement) {
        const h = a.querySelector && a.querySelector('h1,h2,h3');
        if (h && h.textContent) heading = h.textContent.trim().slice(0, 40);
      }

      out.push({
        text: txt,
        magnitude: m[2],
        // The unit may be in this element's own text, or supplied by the
        // element immediately after it (`{delta}` + ` pts` split across spans).
        unit: /^\s*(pts|points?)\b/.test(after)
          ? 'pts'
          : /^\s*%/.test(after)
            ? '%'
            : '',
        aria,
        isMove,
        rung,
        why: [glyph && 'glyph', spoken && 'spoken', styled && 'styled'].filter(Boolean).join('+'),
        context: [...new Set(marks)].join(' ') || (heading ? `under "${heading}"` : '(no marks)'),
      });
    }
    return out;
  });
} catch (e) {
  console.error('LOAD FAILED:', e.message);
  await browser.close();
  process.exit(2);
}
await browser.close();

console.log(`${url}  @${width}px`);

// Scored on MOVES only. A rung label that merely looks like one is reported
// under the line, so a discarded match is visible rather than silently dropped.
const badges = found.filter((f) => f.isMove && !f.rung);
const discarded = found.filter((f) => !f.isMove || f.rung);

console.log(`movement badges found: ${badges.length}   (matches discarded as rung labels: ${discarded.length})`);
for (const d of discarded) {
  console.log(`   ·  discarded "${d.text}"   ${d.rung ? 'range/comparator' : 'no move mark'}`);
}
if (!badges.length) {
  console.log('\nNO MOVEMENT BADGE ON THIS PAGE — no specimen here. Not a pass.');
  process.exit(4);
}

const bare = badges.filter((f) => f.unit === '');
const pct = badges.filter((f) => f.unit === '%');
for (const f of badges) {
  const tag = f.unit === '' ? '🔴 BARE NUMBER' : f.unit === '%' ? '🟠 percent (#5666 arm)' : '  ok';
  console.log(
    `${tag}  "${f.text}"   magnitude=${f.magnitude} unit=${f.unit || '(none)'}  [${f.why}]  ${f.context}` +
      (f.aria ? `\n       accessible name: "${f.aria}"` : '')
  );
}

console.log(`\nbare: ${bare.length}   percent: ${pct.length}   with-unit: ${badges.length - bare.length - pct.length}`);
if (bare.length) {
  console.log('\nA bare magnitude is the defect: the accessible name beside several of these');
  console.log('already says "points", so the page is telling a screen reader the unit and the');
  console.log('eye nothing at all.');
}

// READ THE CONTEXT COLUMN BEFORE CALLING A ZERO A PASS. "bare: 0" is a
// statement about the badges this page happened to draw, not about the three
// repaired components: a team page scores clean on its own already-correct
// renderer whether or not TeamChampionshipPath drew anything at all.
console.log('\n"bare: 0" is only evidence for a surface the context column shows was drawn.');
process.exit(bare.length ? 3 : 0);
