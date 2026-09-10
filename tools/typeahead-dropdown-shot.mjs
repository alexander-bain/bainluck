// typeahead-dropdown-shot.mjs <url> <out.png> <query> — type <query> into the site search and
// shoot the DROPDOWN, not the page.
//
// WHY THIS RIG EXISTS (lane1/237, #4847).
//
// The LOOK rule says a change to a rendered surface is done when the builder has photographed the
// live production surface and read it like Alex would. The typeahead dropdown is a rendered
// surface with no address: `look.sh <url>` cannot reach it, because it only exists after somebody
// types. Every search ship since #4411 has therefore been proved on the PAYLOAD and left the
// pixels unphotographed — which is exactly the gap that let #4519 ship a payload fix a reader
// could not see.
//
// It also prints the dropdown's full innerText, so the suggestions are evidence in the log as well
// as in the PNG (a reviewer can grep the artifact without opening an image), and it prints the
// COUNT of `data-testid="search-suggestion"` rows.
//
// PHONE FIRST, AND THAT IS TWO DIFFERENT COMPONENTS. At 390px the site opens
// `MobileSearchOverlay` behind a button; on a wide viewport `SearchBar` renders the input inline.
// The rig tries the inline input, and falls back to clicking the search-opening control — so the
// same command shoots either surface and the caller does not have to know which one production
// served.
//
// EXIT CODES ARE A STORY (gotcha #124): 0 shot it, 2 usage, 3 no search input could be reached,
// 4 the input took the text and NO suggestion row ever appeared, 1 anything else. 4 is distinct
// from 1 because "this query returned nothing" is a finding about the site, while "the camera
// failed" is a finding about the camera, and a caller that cannot tell them apart reads a dead
// camera as an honest empty dropdown.
//
// A run that shoots nothing writes NO PNG and deletes any stale one at that path: an artifact
// whose filename claims a specimen it does not contain is worse than no artifact.
import { createRequire } from 'module';
import { existsSync, readdirSync, rmSync } from 'fs';

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
const [url, out, query] = process.argv.slice(2);
if (!url || !out || !query) {
  console.error('usage: typeahead-dropdown-shot.mjs <url> <out.png> <query>');
  console.error('  SHOT_W / SHOT_H   viewport (default 390x844 — this is a phone-first surface)');
  console.error('  SHOT_SETTLE_MS    how long to let the dropdown settle after the last keystroke');
  console.error('                    (default 2500; the endpoint is debounced and raced)');
  process.exit(2);
}
if (existsSync(out)) rmSync(out);

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) args.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args });
let code = 1;
try {
  const W = parseInt(process.env.SHOT_W || '390', 10);
  const H = parseInt(process.env.SHOT_H || '844', 10);
  const settle = parseInt(process.env.SHOT_SETTLE_MS || '2500', 10);
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
  await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(1500);

  // 🔴 `:visible` IS LOAD-BEARING, not tidiness. At 390px the page holds BOTH search
  // components in the DOM — the desktop `SearchBar` (hidden by a `md:` class, `offsetParent ===
  // null`) and, once opened, `MobileSearchOverlay`'s own input. They carry the SAME aria-label, so
  // a bare `.first()` returns the invisible desktop twin and the rig reports "no search input
  // reachable" on a page whose search works perfectly. Measured on production 2026-09-10 21:0xZ:
  // `inputs after: 2`, the first with `vis:false`.
  const INPUT = 'input[aria-label="Search teams, games, and futures"]:visible';
  let input = page.locator(INPUT).first();
  if (!(await input.isVisible().catch(() => false))) {
    // The phone surface: the input lives inside an overlay that has to be opened first. Try the
    // controls that open it, in the order a reader would meet them.
    for (const opener of [
      'button[aria-label="Open search"]',
      'button[aria-label*="earch"]',
      'a[href="/search"]',
      '[data-testid="search-trigger"]',
    ]) {
      const el = page.locator(opener).first();
      if (!(await el.isVisible().catch(() => false))) continue;
      console.log(`opening the search overlay with ${opener}`);
      await el.click().catch(() => {});
      // WAIT for the input, never a fixed sleep: the overlay is a `dynamic(..., {ssr:false})`
      // import, so the click is followed by a network fetch of the chunk and a fixed 600ms read
      // as "no search input reachable" on a cold cache (lane1/237 lost its first LOOK to this).
      await page.locator(INPUT).first().waitFor({ state: 'visible', timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(300);
      break;
    }
    input = page.locator(INPUT).first();
  }
  if (!(await input.isVisible().catch(() => false))) {
    console.error('NO SEARCH INPUT reachable on this page — nothing was typed, nothing shot.');
    code = 3;
  } else {
    await input.click();
    // Typed a character at a time on purpose: this endpoint is per-keystroke and raced
    // (`lib/typeaheadRace.ts`), so `fill()` would exercise a request pattern no reader produces.
    await input.type(query, { delay: 120 });
    await page.waitForTimeout(settle);

    const rows = page.locator('[data-testid="search-suggestion"]:visible');
    const n = await rows.count();
    console.log(`query=${JSON.stringify(query)} suggestion_rows=${n}`);
    if (n === 0) {
      console.error('the input took the text and NO suggestion row appeared.');
      code = 4;
    } else {
      // Row by row, not the listbox's own innerText: on the phone overlay the visible
      // `[role="listbox"]` is a wrapper whose text reads EMPTY (measured — it printed nothing
      // while six rows were on screen), which would have banked an artifact saying the dropdown
      // was blank next to a PNG showing six suggestions.
      console.log('--- dropdown rows ---');
      for (let i = 0; i < n; i++) {
        const t = (await rows.nth(i).innerText().catch(() => '')).replace(/\s+/g, ' ').trim();
        console.log(`  ${i + 1}. ${t}`);
      }
      console.log('--- end ---');
      // Shoot the whole viewport rather than the listbox element: the reader sees the dropdown
      // UNDER the box they typed into, and a crop to the listbox would hide whether the query is
      // even still in the field.
      await page.screenshot({ path: out });
      code = 0;
    }
  }
} catch (e) {
  console.error(String(e && e.stack ? e.stack : e));
  code = 1;
} finally {
  await browser.close();
  if (code !== 0 && existsSync(out)) rmSync(out);
  process.exit(code);
}
