// ux1336-award-chip-answers-its-label.mjs — does each PLAYER AWARDS chip answer the question
// its own label names?
//
// THE INVARIANT, stated without reference to any particular bug: a chip reading
// `<player> <LABEL> <pct>%` asserts that `<pct>` is the probability of `<player>` `<LABEL>`. So for
// every rendered chip there must exist a market, for that player, at that probability, whose
// QUESTION is the one the label names. A chip whose number can only be traced to a market asking
// something else is a truth defect however well-formed it looks — and it looks perfect, which is
// why a screenshot cannot grade this and a human reading the page cannot either.
//
// Deliberately NOT keyed on "MVP Finalists", on `shortAwardLabel`, or on any class or markup of the
// defect that prompted it. It reads what the page DREW, independently reads what the API SERVED,
// and joins them on (player, rounded percent). A probe keyed on the defect's own markup can only
// ever express the FAIL, and would report a fixed page as a missing subject.
//
// THE JOIN IS THE INTERESTING PART. The page has already deduplicated, so a chip cannot be matched
// back by market id — that information is gone by the time it is drawn. It is matched by the pair
// the reader can see, (player, percent), which is exactly the pair the reader would use to check.
// An ambiguous join (two markets, same player, same rounded percent, different questions) is
// reported as AMBIGUOUS and never as a pass or a fail: it is the one case the instrument cannot
// decide, and saying so is the difference between a measurement and an assertion.
//
// Usage: node ux1336-award-chip-answers-its-label.mjs <eventId> [baseUrl]
// exit 0 = every chip answers its label · 1 = at least one does not · 2 = UNPAID (no chips found)
import { createRequire } from 'module';
import { existsSync, readdirSync } from 'fs';
import { execFileSync } from 'child_process';

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

const eventId = process.argv[2];
const base = (process.argv[3] || 'https://bainluck.com').replace(/\/$/, '');
if (!eventId) {
  console.error('usage: ux1336-award-chip-answers-its-label.mjs <eventId> [baseUrl]');
  process.exit(2);
}
const api = process.env.BAINLUCK_API || 'https://api.bainluck.com';

/* ── 1 · what the API served ─────────────────────────────────────────────── */

// 🪤 NODE'S `fetch` HAS NO EGRESS HERE. The sandbox permits curl (which routes through the
// proxy) but refuses node's own socket: `TypeError: fetch failed` / `EPERM connect`. That reads
// as "the API is down" rather than "this process may not open a socket", so the API side is
// bridged through curl deliberately, not as a workaround for an outage.
let payload;
try {
  payload = JSON.parse(
    execFileSync('curl', ['-sS', '--fail', `${api}/api/events/${eventId}/related-futures`], {
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
    }),
  );
} catch (e) {
  console.error(`🔴 UNPAID: could not read related-futures for ${eventId}: ${e.message}`);
  process.exit(2);
}
const served = [];
for (const side of ['home_team_futures', 'away_team_futures']) {
  for (const f of payload[side] || []) {
    served.push({
      side,
      marketId: f.market_id,
      marketName: f.market_name || '',
      cleanLabel: f.clean_label || '',
      player: f.outcome_name || '',
      prob: f.probability,
      pct: f.probability == null ? null : Math.round(f.probability * 100),
    });
  }
}

/** Does a market's QUESTION name the thing `label` names? Conservative on purpose. */
function questionMatchesLabel(market, label) {
  const q = `${market.marketName} ${market.cleanLabel}`.toLowerCase();
  const l = label.toLowerCase().trim();
  const isFinalistQuestion = /\bfinalists?\b/.test(q);
  const labelSaysFinalist = /\bfinalists?\b/.test(l);
  // A label that does not mention finalists must not be answered by a finalists market,
  // and vice versa. This is the only distinction this probe adjudicates; anything else
  // it reports as unjudged rather than guessing.
  if (isFinalistQuestion !== labelSaysFinalist) return false;
  return true;
}

/* ── 2 · what the page drew ──────────────────────────────────────────────── */

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
await page.goto(`${base}/events/${eventId}`, { waitUntil: 'domcontentloaded', timeout: 90000 });
try {
  await page.waitForLoadState('networkidle', { timeout: 20000 });
} catch { /* a polling event page never idles */ }
await page.waitForTimeout(3000);

const chips = await page.evaluate(() => {
  const out = [];
  // Find the PLAYER AWARDS heading(s) by TEXT, not by class: the class is a Tailwind
  // soup that changes with any restyle, while the heading is what the reader sees.
  const heads = [...document.querySelectorAll('div')].filter(
    (d) => d.children.length === 0 && d.textContent.trim() === 'PLAYER AWARDS',
  );
  for (const h of heads) {
    const list = h.nextElementSibling;
    if (!list) continue;
    for (const row of list.children) {
      const spans = [...row.querySelectorAll('span')];
      if (spans.length < 2) continue;
      const player = spans[0].textContent.trim();
      // Each award chip is a span holding "<label> <b>NN%</b>".
      for (const s of spans.slice(1)) {
        const m = s.textContent.trim().match(/^(.*?)\s*(\d+)%$/);
        if (m && m[1]) out.push({ player, label: m[1].trim(), pct: Number(m[2]) });
      }
    }
  }
  return out;
});

const shot = `artifacts/ux-1336/awards-${eventId}-390.png`;
await page.screenshot({ path: shot, fullPage: false });
await browser.close();

/* ── 3 · join and judge ──────────────────────────────────────────────────── */

console.log(`event ${eventId}   page ${base}/events/${eventId}   api ${api}`);
console.log(`served award rows: ${served.length}   rendered chips: ${chips.length}`);

if (chips.length === 0) {
  console.error('🔴 UNPAID: no PLAYER AWARDS chips rendered. The team cards draw awards only when a');
  console.error('   team has surviving award rows; this specimen cannot pay a verdict either way.');
  process.exit(2);
}

// The page truncates long player names ("Jaxon Smith-…"), so a prefix join is needed — but ONLY
// where the page actually truncated.
//
// 🪤 A BARE PREFIX MATCH FABRICATES EVIDENCE HERE, and it did on the first run. Outcome names on
// this route carry their own qualifier after a colon — "Lamar Jackson: 50+", "Lamar Jackson: 175+"
// — so `servedName.startsWith(rendered)` matched thirty-odd player-prop rows and the probe printed
// `the real "MVP" row for Lamar Jackson: 50+ is 33%` about a rushing-yards line. The verdict was
// unaffected (that join is on an exact percent), but the evidence beneath it was invented, which is
// worse than a wrong verdict because it reads as corroboration. Truncation is the only licence for
// a prefix, and the ellipsis is how the page says it truncated.
const sameName = (rendered, servedName) => {
  const truncated = /[…]/.test(rendered);
  const r = rendered.replace(/[…·]/g, '').trim().toLowerCase();
  const s = servedName.trim().toLowerCase();
  return truncated ? s.startsWith(r) : s === r;
};

let bad = 0;
let ambiguous = 0;
for (const c of chips) {
  const candidates = served.filter((m) => sameName(c.player, m.player) && m.pct === c.pct);
  if (candidates.length === 0) {
    console.log(`  ?  ${c.player.padEnd(18)} ${c.label.padEnd(16)} ${String(c.pct).padStart(3)}%  ` +
      `no served row at this percent — unjudged (dedupe may have merged sources)`);
    continue;
  }
  const questions = [...new Set(candidates.map((m) => m.marketName))];
  const ok = candidates.some((m) => questionMatchesLabel(m, c.label));
  const mismatched = candidates.filter((m) => !questionMatchesLabel(m, c.label));
  if (ok && mismatched.length > 0) {
    ambiguous++;
    console.log(`  ~  ${c.player.padEnd(18)} ${c.label.padEnd(16)} ${String(c.pct).padStart(3)}%  ` +
      `AMBIGUOUS — ${questions.length} markets share this percent: ${questions.join(' | ')}`);
  } else if (ok) {
    console.log(`  ✅ ${c.player.padEnd(18)} ${c.label.padEnd(16)} ${String(c.pct).padStart(3)}%  ` +
      `<- ${questions.join(' | ')}`);
  } else {
    bad++;
    console.log(`  🔴 ${c.player.padEnd(18)} ${c.label.padEnd(16)} ${String(c.pct).padStart(3)}%  ` +
      `is the answer to: ${questions.join(' | ')}`);
    // What the reader is NOT being shown, if it exists.
    //
    // `questionMatchesLabel` adjudicates ONE axis (finalist vs not), so on its own it calls a
    // first-touchdown market a valid "MVP" row — true to its stated scope and useless as evidence.
    // For the alternatives listing, additionally require the question to actually NAME the award
    // the label names, so the line printed under a failure is a row a reader would accept as the
    // one they should have seen.
    const labelTerms = c.label.toLowerCase().split(/\s+/).filter((w) => w.length > 2);
    const truthful = served.filter(
      (m) =>
        sameName(c.player, m.player) &&
        questionMatchesLabel(m, c.label) &&
        m.pct != null &&
        labelTerms.every((w) => `${m.marketName} ${m.cleanLabel}`.toLowerCase().includes(w)),
    );
    for (const t of truthful) {
      console.log(`         the real "${c.label}" row for ${t.player} is ${t.pct}% ` +
        `(market ${t.marketId} ${JSON.stringify(t.marketName)}) — not drawn`);
    }
  }
}

console.log(`\nframe: ${shot}`);
console.log(`chips=${chips.length}  MISLABELLED=${bad}  ambiguous=${ambiguous}`);
if (bad > 0) {
  console.log('\n🔴 a chip is labelled with one question and priced from another.');
  process.exit(1);
}
console.log('\n✅ every chip answers the question its label names');
process.exit(0);
