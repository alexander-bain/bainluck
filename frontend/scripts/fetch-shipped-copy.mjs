#!/usr/bin/env node
/**
 * DOWNLOAD THE JAVASCRIPT A READER ACTUALLY RUNS.
 *
 * This script carries NO rules. It fetches a live page, reads the
 * `/_next/static/**` chunks that page references, and drops them in a
 * directory. `__tests__/components/shippedCopyBans.test.ts` applies the rules
 * from `lib/copyBans.ts` to whatever is in that directory.
 *
 * The split is deliberate. A scanner that both fetches and judges ends up
 * re-declaring the banned list, and the second copy is the one that drifts —
 * which is the exact failure this whole guard exists to close: a sweep that
 * looked done because the thing it read was not the thing that shipped.
 *
 * Jest cannot do the fetching itself: `jest.setup.network.js` blocks the
 * network on purpose, so a test that reached production would be a test that
 * goes red when a CDN hiccups. Fetch here, judge there.
 *
 * Usage:
 *   node scripts/fetch-shipped-copy.mjs [--url URL] [--out DIR]
 *   SHIPPED_BUNDLE_DIR=<DIR> npx jest shippedCopyBans
 *
 * Exit codes: 0 wrote at least one chunk · 1 fetched nothing (which is a
 * FAILURE, never an all-clear — an empty directory scanned clean is precisely
 * how "it returned" gets mistaken for "it worked").
 */

import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execFileSync } from "node:child_process";

/**
 * GET, over whichever transport this machine actually has.
 *
 * `node --experimental-fetch` is EPERM-blocked in the agent sandbox (the same
 * block that makes `wait-for-frontend-sha` look like a bad deploy), while
 * `curl` is allowed. A production scan that only works on a laptop is a
 * production scan nobody runs, so the fallback is first-class rather than a
 * debugging aid — and it is a FALLBACK, not the default, so this stays a
 * plain node script everywhere node can reach the network.
 */
async function get(url) {
  try {
    const res = await fetch(url, { redirect: "follow" });
    return { ok: res.ok, status: res.status, url: res.url, text: await res.text() };
  } catch (err) {
    if (!/EPERM|ENOTFOUND|ECONNREFUSED|fetch failed/i.test(String(err))) throw err;
    // `-w` writes the final URL after redirects on its own line at the end, so
    // one call yields both the body and where it ended up.
    const raw = execFileSync(
      "curl",
      ["-sSL", "-w", "\\n__EFFECTIVE_URL__%{url_effective}\\n__HTTP_CODE__%{http_code}", url],
      { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }
    );
    const effective = raw.match(/__EFFECTIVE_URL__(.*)/)?.[1]?.trim() ?? url;
    const code = Number(raw.match(/__HTTP_CODE__(\d+)/)?.[1] ?? 0);
    const text = raw.replace(/\n__EFFECTIVE_URL__.*\n__HTTP_CODE__\d+\s*$/, "");
    return { ok: code >= 200 && code < 400, status: code, url: effective, text };
  }
}

const args = process.argv.slice(2);
function arg(name, fallback) {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
}

const pageUrl = arg("url", "https://www.bainluck.com/tournaments/us-open-2026");
const outDir = arg("out", path.join(os.tmpdir(), "bainluck-shipped"));

const res = await get(pageUrl);
if (!res.ok) {
  console.error(`FAIL: ${pageUrl} returned HTTP ${res.status}`);
  process.exit(1);
}
const html = res.text;
const origin = new URL(res.url).origin;

// Both the `<script src>` tags and the flight payload's chunk references. The
// flight payload is where a client-only route's chunks are named, and a scan
// that only reads script tags misses exactly the pages that are worth reading.
const chunks = [...new Set([...html.matchAll(/\/_next\/static\/[^"'\\ )]+?\.js/g)].map((m) => m[0]))];

if (chunks.length === 0) {
  console.error(`FAIL: no /_next/static chunks referenced by ${res.url}`);
  process.exit(1);
}

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });

let written = 0;
let bytes = 0;
for (const chunk of chunks) {
  const url = origin + chunk;
  const r = await get(url);
  if (!r.ok) {
    console.error(`  skip ${chunk} — HTTP ${r.status}`);
    continue;
  }
  const body = r.text;
  // The DIRECTORY STRUCTURE IS DATA. `surfaceOf` derives the route from the
  // `app/<route>/…` path, so flattening these names into one directory would
  // silently reclassify every route chunk as "shared" — and the tournament
  // gate, which is the ship, would pass by scanning nothing.
  const rel = decodeURIComponent(chunk).replace(/^\//, "");
  const dest = path.join(outDir, rel);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, body);
  written += 1;
  bytes += body.length;
}

fs.writeFileSync(
  path.join(outDir, "MANIFEST.json"),
  JSON.stringify({ page: res.url, chunks, written, bytes }, null, 2)
);

console.log(`page:    ${res.url}`);
console.log(`chunks:  ${written}/${chunks.length} written, ${bytes} bytes`);
console.log(`out:     ${outDir}`);
if (written === 0) {
  console.error("FAIL: every chunk fetch failed — this is not an all-clear");
  process.exit(1);
}
console.log(`\nnow run:  SHIPPED_BUNDLE_DIR=${outDir} npx jest shippedCopyBans`);
