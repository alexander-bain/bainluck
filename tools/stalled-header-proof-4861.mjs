// #4861 — prove on PRODUCTION that a page which stops being fed stops claiming to be live.
//
// The claim under test is about a tab a reader LEFT OPEN, so the rig loads the page exactly once
// and never navigates again (`look.sh` reloads, and a reload would photograph this green whether or
// not the fix is deployed). After a control shot it starts REFUSING the page's own event fetch, the
// way a 429 or a dropped connection does, and shoots again once the poll has had its chances.
//
// BEFORE (deployed sha without the fix): the header still prints `LIVE` + `Next update: N`.
// AFTER  (deployed sha with it):         the header prints a grey age and neither of those.
//
// usage: node stalled-header-proof-4861.mjs <url> <outDir> <slug> [waitSeconds]
import { createRequire } from 'module';
import { existsSync, readdirSync, mkdirSync, writeFileSync } from 'fs';

// Same resolution as shop-shot.mjs / norefresh-shop.mjs: playwright lives in the npx cache, not in
// this repo, so a bare `import` resolves to nothing.
function findPlaywright() {
  const npx = `${process.env.HOME}/.npm/_npx`;
  if (existsSync(npx)) {
    for (const d of readdirSync(npx)) {
      const q = `${npx}/${d}/node_modules/`;
      if (existsSync(`${q}playwright`)) return q;
    }
  }
  return process.cwd() + '/';
}
const { chromium } = createRequire(findPlaywright())('playwright');

const [url, outDir, slug, waitArg] = process.argv.slice(2);
if (!url || !outDir || !slug) {
  console.error('usage: stalled-header-proof-4861.mjs <url> <outDir> <slug> [waitSeconds]');
  process.exit(2);
}
const WAIT_S = parseInt(waitArg || '95', 10); // > 2 x the 32s live poll
mkdirSync(outDir, { recursive: true });

const W = parseInt(process.env.SHOT_W || '390', 10);
const H = parseInt(process.env.SHOT_H || '844', 10);
const log = (...m) => console.error(`[${new Date().toISOString()}]`, ...m);

// The two sentences the header must not say once nothing is arriving, and the shape of the honest
// mark that replaces them. Matched on the rendered text, not on a class name.
const PROMISE = 'Next update';
// Word-boundaried: "LIVE" as a pill, never the "live" inside `Live · Bain Luck blend` (which is a
// different claim, #5069) and never a team or market name that happens to contain the letters.
const LIVE_PILL = /\bLIVE\b/;

// The sandbox reaches production through a proxy; without this the goto simply times out.
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const launchArgs = ['--no-sandbox', '--single-process', '--disable-gpu', '--disable-crashpad', '--disable-dev-shm-usage'];
if (proxy) launchArgs.push(`--proxy-server=${proxy}`, '--proxy-bypass-list=<-loopback>');

const browser = await chromium.launch({ args: launchArgs });
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });

// The deployed frontend's own sha — the ONLY frontend authority (lib/buildInfo.ts). Without it a
// "no change" reading cannot be told from "the deploy has not landed".
let deployedSha = null;
await page.goto(url, { waitUntil: 'load', timeout: 60000 });
await page.waitForTimeout(7000);
deployedSha = await page.getAttribute('meta[name="bainluck-frontend-commit"]', 'content');

const read = async () => {
  const body = await page.evaluate(() => document.body.innerText);
  return {
    promise: body.includes(PROMISE),
    livePill: LIVE_PILL.test(body.split('\n').slice(0, 40).join('\n')),
    ageMark: /\b\d+[sm] ago\b/.test(body),
    head: body.slice(0, 320),
  };
};

const shoot = async (tag) => {
  const state = await read();
  await page.screenshot({ path: `${outDir}/${slug}-${tag}.png` });
  log(`${tag}: promise=${state.promise} livePill=${state.livePill} ageMark=${state.ageMark}`);
  return state;
};

log(`deployed frontend sha = ${deployedSha}`);
const control = await shoot('A-control-fetches-landing');

// From here the page's own event fetch is refused. Everything else is left alone, so any part of
// the page fed by another key keeps updating — which is the whole point: that is what made the
// frozen hero look alive.
let refused = 0;
await page.route('**/api/events/**', async (route) => {
  refused += 1;
  await route.abort('failed');
});
log(`event fetch now refused; waiting ${WAIT_S}s (> 2 x the 32s live poll)`);
await page.waitForTimeout(WAIT_S * 1000);

const after = await shoot('B-after-the-fetch-is-refused');
log(`refused ${refused} request(s)`);

const verdict = {
  url,
  deployedSha,
  refusedRequests: refused,
  control: { promise: control.promise, livePill: control.livePill, ageMark: control.ageMark },
  afterRefusal: { promise: after.promise, livePill: after.livePill, ageMark: after.ageMark },
  // The fix is present iff the promise was there while fetches landed and is gone once they stop.
  fixObserved: control.promise === true && after.promise === false,
  controlHead: control.head,
  afterHead: after.head,
};
writeFileSync(`${outDir}/${slug}-verdict.json`, JSON.stringify(verdict, null, 2));
log(`fixObserved=${verdict.fixObserved}`);

await browser.close();
// 0 = the fix was observed · 3 = the page still promised an update · 4 = no control (no ring to lose)
process.exit(verdict.fixObserved ? 0 : control.promise ? 3 : 4);
