// ux1347-own-moneyline-not-a-prop-7064.mjs — AFTER-CHECK for #7064.
//
// THE SHIP: an event page answers its headline question ONCE, in the hero. The game's own
// moneyline must not also appear as a row in THE DIVERGENCE / THE SCRIPT / WHAT HIT / the props
// list, under ANY venue's wording.
//
// WHAT IT ASKS, AND WHY THIS QUESTION. The defect's visible signature is a props group headed with
// the matchup itself — "BOSTON VS TAMPA BAY", "BOSTON RED SOX VS. TAMPA BAY RAYS" — whose rows are
// the two team names. So the probe walks the props body's own group headings and asks of each:
// does this heading parse as the bare matchup of THIS event's two teams?
//
// It reads the teams from the API, not from the page's chrome, so the check cannot be satisfied by
// the page relabelling something. And it keys on the SHAPE of the heading (a matchup of the two
// sides), never on one venue's spelling — keying on the spelling is the bug being fixed: the two
// offenders differed only in how each venue spells the same two clubs.
//
// 🔴 EXIT 4 IS NOT A PASS. If the page serves no props group headings at all, the subject is
// absent and nothing was proven. An event whose props have rotated out, or a page that failed to
// hydrate, must never read as green — under-counting is safe on RED and fatal on GREEN.
//
// Usage: node ux1347-own-moneyline-not-a-prop-7064.mjs [eventId] [url] [widthPx]
// exit 0 = paid: props groups exist and none is the event's own matchup
//      3 = the defect is on production: a matchup-named group is rendered as a prop
//      4 = UNPAID: no props group headings found (subject absent) — re-run on an event with props
//      5 = the probe could not read the page or the API
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

const eventId = process.argv[2] || '15314172';
const base = process.argv[3] || 'https://bainluck.com';
const width = Number(process.argv[4] || 390);
const url = `${base}/events/${eventId}`;

console.log(`url=${url} width=${width}`);

// Node's global fetch ignores HTTPS_PROXY, so the API read goes through Playwright's request
// context, which uses the browser's networking (and therefore the proxy) like the page does.
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ headless: true, args });
const page = await browser.newPage({ viewport: { width, height: 844 }, deviceScaleFactor: 2 });

let homeTeam = '';
let awayTeam = '';

try {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });

  // ---- the event's own two sides, from the API (never from the page's chrome) ----
  // Read from inside the page: only the browser has egress here, and this is the same origin the
  // app itself calls, so it exercises the real path rather than a side channel.
  const sides = await page.evaluate(async (id) => {
    const r = await fetch(`https://api.bainluck.com/api/events/${id}/game-markets`);
    if (!r.ok) return { error: `game-markets HTTP ${r.status}` };
    const gm = await r.json();
    return { home: gm.home_team || '', away: gm.away_team || '' };
  }, eventId);
  if (sides.error) throw new Error(sides.error);
  homeTeam = sides.home;
  awayTeam = sides.away;
  if (!homeTeam || !awayTeam) {
    console.log(`event ${eventId} does not name two sides (home=${JSON.stringify(homeTeam)} away=${JSON.stringify(awayTeam)})`);
    await browser.close();
    process.exit(5);
  }
  console.log(`sides: away=${JSON.stringify(awayTeam)} home=${JSON.stringify(homeTeam)}`);

  try {
    await page.waitForLoadState('networkidle', { timeout: 25000 });
  } catch {
    /* a live page may never idle; the settle below covers it */
  }
  await page.waitForTimeout(3000);

  // The full prop set lives behind an "All N props" <details>. A row we never rendered is a row we
  // cannot grade, so open every <details> and scroll the column to hydrate what is below the fold.
  await page.evaluate(async () => {
    for (const d of document.querySelectorAll('details')) d.open = true;
    for (let y = 0; y < 20000; y += 800) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 100));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(2000);

  const found = await page.evaluate(() => {
    // Group headings in the props body are short, uppercase-styled labels. Rather than guess a
    // class, take every small heading-ish element and let the matchup test do the discriminating.
    const nodes = Array.from(
      document.querySelectorAll('h2, h3, h4, h5, dt, summary, [class*="uppercase"]'),
    );
    const seen = [];
    for (const n of nodes) {
      const t = (n.textContent || '').trim();
      if (!t || t.length > 120) continue;
      seen.push(t);
    }
    return seen;
  });

  // ---- the predicate, deliberately the same SHAPE as the shipped one ----
  const norm = (s) => s.toLowerCase().replace(/[.]/g, '').replace(/\s+/g, ' ').trim();
  const namesSide = (label, team) => {
    const l = norm(label);
    const t = norm(team);
    if (!l || !t) return false;
    return l === t || t.startsWith(l + ' ') || t.endsWith(' ' + l);
  };
  const isOwnMatchup = (heading) => {
    if (heading.includes(':')) return false;
    const m = norm(heading).match(/^(.+?)\s+(?:vs|v|at|@)\s+(.+)$/);
    if (!m) return false;
    const [a, b] = [m[1], m[2]];
    return (
      (namesSide(a, awayTeam) && namesSide(b, homeTeam)) ||
      (namesSide(a, homeTeam) && namesSide(b, awayTeam))
    );
  };

  // The denominator, printed whether or not anything is found: an under-counting walk that
  // reports "0 offenders" out of "0 headings" has measured nothing, and must say so.
  const matchupHeadings = [...new Set(found.filter(isOwnMatchup))];
  const propGroupHeadings = [...new Set(found.filter((t) => /:/.test(t) || isOwnMatchup(t)))];

  console.log(`heading-ish nodes read: ${found.length}`);
  console.log(`prop group headings seen: ${propGroupHeadings.length}`);

  if (propGroupHeadings.length === 0) {
    console.log('');
    console.log('UNPAID (exit 4): no props group headings on this page — the subject is absent.');
    console.log('This is NOT a pass. Re-run on an event that is serving props.');
    await browser.close();
    process.exit(4);
  }

  if (matchupHeadings.length > 0) {
    console.log('');
    for (const h of matchupHeadings) console.log(`  🔴 OWN-MATCHUP GROUP RENDERED AS A PROP: ${JSON.stringify(h)}`);
    console.log('');
    console.log(`OFFENDERS=${matchupHeadings.length}/${propGroupHeadings.length} prop groups`);
    console.log('VERDICT: the event page still answers its own headline question in the props body.');
    await browser.close();
    process.exit(3);
  }

  console.log('');
  console.log(`OFFENDERS=0/${propGroupHeadings.length} prop groups`);
  console.log("VERDICT: no props group is this event's own matchup — the hero answers it alone.");
  await browser.close();
  process.exit(0);
} catch (e) {
  console.log(`probe could not read the page: ${e.message}`);
  await browser.close();
  process.exit(5);
}
