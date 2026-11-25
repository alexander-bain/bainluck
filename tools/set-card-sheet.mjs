#!/usr/bin/env node
/**
 * Render one composite PNG of requested machinery grouping cards as the real
 * Bain Luck website draws them at 390 px wide, in both Light and Dark.
 *
 * Usage:
 *   node tools/set-card-sheet.mjs --out /tmp/sheet.png [--feed-json feed.json | --feed-url URL] [--web-url URL] <slug1> [slug2 ...]
 */

import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

export const DEFAULT_WEB_URL = "https://bainluck.com/discover";
export const DEFAULT_FEED_URLS = [
  "https://api.bainluck.com/api/feed?machinery=preview&limit=200",
  "https://api.bainluck.com/api/feed?machinery=1&limit=200",
];
export const VIEWPORT_WIDTH = 390;

export function findPlaywrightPath() {
  const candidates = [];
  if (process.env.PLAYWRIGHT_PATH) candidates.push(process.env.PLAYWRIGHT_PATH);
  const npxRoot = `${process.env.HOME || ""}/.npm/_npx`;
  if (existsSync(npxRoot)) {
    for (const entry of readdirSync(npxRoot)) {
      const p = `${npxRoot}/${entry}/node_modules/playwright`;
      if (existsSync(p)) candidates.push(p);
    }
  }
  candidates.push(`${process.cwd()}/node_modules/playwright`);
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  throw new Error("Playwright not found in ~/.npm/_npx, ./node_modules, or $PLAYWRIGHT_PATH");
}

export function parseArgs(argv) {
  let out = null;
  let webUrl = DEFAULT_WEB_URL;
  let feedUrl = null;
  let feedJson = null;
  let scale = 2;
  let lightOnly = false;
  const slugs = [];

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--out" || arg === "-o") {
      out = argv[++i] ?? null;
    } else if (arg.startsWith("--out=")) {
      out = arg.slice("--out=".length);
    } else if (arg === "--web-url") {
      webUrl = argv[++i] ?? "";
    } else if (arg.startsWith("--web-url=")) {
      webUrl = arg.slice("--web-url=".length);
    } else if (arg === "--feed-url") {
      feedUrl = argv[++i] ?? null;
    } else if (arg.startsWith("--feed-url=")) {
      feedUrl = arg.slice("--feed-url=".length);
    } else if (arg === "--feed-json") {
      feedJson = argv[++i] ?? null;
    } else if (arg.startsWith("--feed-json=")) {
      feedJson = arg.slice("--feed-json=".length);
    } else if (arg === "--scale") {
      scale = Number(argv[++i] ?? 2);
    } else if (arg.startsWith("--scale=")) {
      scale = Number(arg.slice("--scale=".length));
    } else if (arg === "--light-only") {
      lightOnly = true;
    } else if (arg === "--help" || arg === "-h") {
      return { help: true, out, webUrl, feedUrl, feedJson, scale, lightOnly, slugs };
    } else if (arg.startsWith("-")) {
      throw new Error(`Unknown flag: ${arg}`);
    } else {
      slugs.push(arg);
    }
  }

  if (!out) throw new Error("--out <path.png> is required");
  if (!slugs.length) throw new Error("At least one set slug is required");
  if (!Number.isFinite(scale) || scale < 1 || scale > 3) {
    throw new Error(`Invalid --scale value: ${scale}`);
  }
  if (feedUrl && feedJson) {
    throw new Error("Pass at most one of --feed-url and --feed-json");
  }
  return { help: false, out, webUrl, feedUrl, feedJson, scale, lightOnly, slugs };
}

export function extractSlugFromItem(item) {
  const data = item?.data || {};
  return data?.collection_ref?.slug || data?.roundup?.machinery_card?.slug || null;
}

export function selectCardsBySlug(feedPayloads, slugs) {
  const bySlug = new Map();
  let template = null;
  for (const payload of feedPayloads) {
    if (!template && payload && typeof payload === "object") template = payload;
    for (const item of payload?.items || []) {
      const slug = extractSlugFromItem(item);
      if (slug && !bySlug.has(slug)) {
        bySlug.set(slug, item);
      }
    }
  }

  const missing = slugs.filter((s) => !bySlug.has(s));
  if (missing.length) {
    throw new Error(
      `Missing set slug(s) in feed (${missing.join(", ")}). Available machinery slugs: ${
        [...bySlug.keys()].filter((s) => s.startsWith("machinery-")).join(", ") || "none"
      }`,
    );
  }

  return {
    items: slugs.map((s) => bySlug.get(s)),
    template: template || {},
  };
}

async function loadFeedPayloads({ feedJson, feedUrl }) {
  if (feedJson) {
    const raw = JSON.parse(readFileSync(resolve(feedJson), "utf8"));
    return Array.isArray(raw) ? raw : [raw];
  }
  const urls = feedUrl ? [feedUrl] : DEFAULT_FEED_URLS;
  const payloads = [];
  for (const url of urls) {
    const res = await fetch(url, { headers: { "User-Agent": "bainluck-set-card-sheet/1.0" } });
    if (!res.ok) {
      throw new Error(`Feed fetch failed (${res.status}) for ${url}`);
    }
    payloads.push(await res.json());
  }
  return payloads;
}

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function captureMode(browser, { webUrl, feedBody, slugs, colorScheme, scale }) {
  const context = await browser.newContext({
    viewport: { width: VIEWPORT_WIDTH, height: 1400 },
    deviceScaleFactor: scale,
    colorScheme,
  });
  try {
    const page = await context.newPage();
    await page.route("**/api/feed*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Expose-Headers": "X-Feed-Cache",
          "X-Feed-Cache": "sheet_mock",
        },
        body: feedBody,
      });
    });

    await page.goto(webUrl, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForSelector('[data-testid="machinery-discover-card"]', { timeout: 25000 });

    if (colorScheme === "dark") {
      await page.evaluate(() => {
        document.documentElement.classList.add("dark");
        document.documentElement.style.colorScheme = "dark";
      });
    } else {
      await page.evaluate(() => {
        document.documentElement.classList.remove("dark");
        document.documentElement.style.colorScheme = "light";
      });
    }

    // Expand viewport so every requested card renders in-flow without sticky headers overlapping clips.
    const docHeight = await page.evaluate(() => Math.max(document.documentElement.scrollHeight, 1400));
    await page.setViewportSize({ width: VIEWPORT_WIDTH, height: docHeight + 120 });
    await page.waitForTimeout(350);

    // Wait for every image inside rendered roundup cards (both native machinery and paired-stage cards) to finish loading cleanly.
    const imgStatus = await page.evaluate(async (expectedSlugs) => {
      const imgs = [
        ...document.querySelectorAll(
          '[data-testid="machinery-discover-card"] img, [data-testid="roundup-card-slot"] img',
        ),
      ];
      await Promise.all(
        imgs.map((img) =>
          img.complete
            ? Promise.resolve()
            : new Promise((res) => {
                img.addEventListener("load", res, { once: true });
                img.addEventListener("error", res, { once: true });
                setTimeout(res, 15000);
              }),
        ),
      );
      const broken = imgs
        .filter((img) => !img.complete || img.naturalWidth === 0)
        .map((img) => img.src);

      const slots = {};
      for (const slug of expectedSlugs) {
        const cardLink =
          document.querySelector(`[data-testid="machinery-discover-card"][href="/collections/${slug}"]`) ||
          document.querySelector(`[data-testid="paired-card-machinery-link"][href="/collections/${slug}"]`);
        if (!cardLink) continue;
        const slot = cardLink.closest('[data-testid="roundup-card-slot"]') || cardLink;
        const cardSurface = slot.querySelector('[data-testid="machinery-discover-card"], article') || cardLink;
        const rect = slot.getBoundingClientRect();
        const headline = slot.querySelector("h2, h3")?.textContent?.trim() || "";
        const style = getComputedStyle(cardSurface);
        slots[slug] = {
          y: Math.max(0, Math.floor(rect.top) - 8),
          height: Math.ceil(rect.height) + 16,
          headline,
          cardBg: style.backgroundColor,
          bodyBg: getComputedStyle(document.body).backgroundColor,
        };
      }
      return { broken, slots };
    }, slugs);

    if (imgStatus.broken.length) {
      throw new Error(`Broken image(s) in ${colorScheme} render: ${imgStatus.broken.join(", ")}`);
    }
    const missingRendered = slugs.filter((s) => !imgStatus.slots[s]);
    if (missingRendered.length) {
      throw new Error(`Card(s) did not render on ${webUrl}: ${missingRendered.join(", ")}`);
    }

    const captures = {};
    for (const slug of slugs) {
      const box = imgStatus.slots[slug];
      const buf = await page.screenshot({
        clip: { x: 0, y: box.y, width: VIEWPORT_WIDTH, height: box.height },
      });
      captures[slug] = {
        ...box,
        dataUri: `data:image/png;base64,${buf.toString("base64")}`,
      };
    }
    return captures;
  } finally {
    await context.close();
  }
}

async function stitchSheet(browser, { out, webUrl, slugs, lightCaps, darkCaps, scale, lightOnly = false }) {
  const sheetWidth = lightOnly ? 444 : 860;
  const rowsHtml = slugs
    .map((slug) => {
      const lc = lightCaps[slug];
      const dc = darkCaps ? darkCaps[slug] : null;
      const darkPane =
        !lightOnly && dc
          ? `
          <div class="pane pane-dark">
            <div class="pane-label">390 px · Dark media + .dark (${escapeHtml(dc.cardBg)})</div>
            <img src="${dc.dataUri}" width="390" />
          </div>`
          : "";
      return `
      <section class="row">
        <div class="row-head">
          <span class="slug">${escapeHtml(slug)}</span>
          <span class="headline">${escapeHtml(lc.headline)}</span>
        </div>
        <div class="cols">
          <div class="pane pane-light">
            <div class="pane-label">390 px · Light (${escapeHtml(lc.cardBg)})</div>
            <img src="${lc.dataUri}" width="390" />
          </div>${darkPane}
        </div>
      </section>`;
    })
    .join("\n");

  const subText = lightOnly
    ? "Light mode (the Bain Luck website is light-mode-only; cards ignore .dark)."
    : "Left: Light (prefers-color-scheme: light). Right: Dark (prefers-color-scheme: dark + .dark class).";

  const html = `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    width: ${sheetWidth}px;
    padding: 20px;
    background: #E5E7EB;
    color: #0F172A;
    font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
  }
  header { margin-bottom: 16px; }
  h1 { font-size: 16px; font-weight: 700; }
  .sub { margin-top: 4px; font-size: 12px; color: #475569; }
  .row {
    margin-top: 16px;
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 12px;
    padding: 12px;
  }
  .row-head { display: flex; flex-direction: column; gap: 2px; margin-bottom: 10px; }
  .slug { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; font-weight: 700; color: #2563EB; }
  .headline { font-size: 13px; font-weight: 600; color: #0F172A; }
  .cols { display: flex; gap: 16px; align-items: flex-start; }
  .pane { width: 400px; border-radius: 8px; padding: 5px; }
  .pane-light { background: #F5F5F7; border: 1px solid #E2E8F0; color: #334155; }
  .pane-dark { background: #0B0F17; border: 1px solid #1E293B; color: #CBD5E1; }
  .pane-label { font-size: 11px; font-weight: 600; padding: 2px 4px 6px; }
  .pane img { display: block; width: 390px; height: auto; border-radius: 6px; }
</style>
</head>
<body>
  <header>
    <h1>Set Card Sheet — ${slugs.length} card${slugs.length === 1 ? "" : "s"} as drawn at 390 px (${escapeHtml(webUrl)})</h1>
    <p class="sub">${subText}</p>
  </header>
  ${rowsHtml}
</body>
</html>`;

  const ctx = await browser.newContext({ viewport: { width: sheetWidth, height: 1000 }, deviceScaleFactor: scale });
  try {
    const page = await ctx.newPage();
    await page.setContent(html, { waitUntil: "load" });
    await page.evaluate(async () => {
      await Promise.all(
        [...document.images].map((img) =>
          img.complete
            ? Promise.resolve()
            : new Promise((res) => {
                img.addEventListener("load", res, { once: true });
                img.addEventListener("error", res, { once: true });
              }),
        ),
      );
    });
    const outPath = resolve(out);
    mkdirSync(dirname(outPath), { recursive: true });
    const buf = await page.screenshot({ fullPage: true });
    writeFileSync(outPath, buf);
    return outPath;
  } finally {
    await ctx.close();
  }
}

export async function main(argv = process.argv.slice(2)) {
  const opts = parseArgs(argv);
  if (opts.help) {
    console.log(
      "Usage: node tools/set-card-sheet.mjs --out <file.png> [--feed-json <path> | --feed-url <url>] [--web-url <url>] [--scale 1..3] <slug1> [slug2 ...]",
    );
    return 0;
  }

  const payloads = await loadFeedPayloads(opts);
  const { items, template } = selectCardsBySlug(payloads, opts.slugs);
  const feedBody = JSON.stringify({
    ...template,
    items,
    total: items.length,
    limit: Math.max(20, items.length),
    offset: 0,
    has_more: false,
  });

  const require = createRequire(import.meta.url);
  const { chromium } = require(findPlaywrightPath());
  const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
  const launchArgs = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
  ];
  if (proxy) launchArgs.push(`--proxy-server=${proxy}`, "--proxy-bypass-list=<-loopback>");

  const browser = await chromium.launch({ headless: true, args: launchArgs });
  try {
    const lightCaps = await captureMode(browser, {
      webUrl: opts.webUrl,
      feedBody,
      slugs: opts.slugs,
      colorScheme: "light",
      scale: opts.scale,
    });
    const darkCaps = opts.lightOnly
      ? null
      : await captureMode(browser, {
          webUrl: opts.webUrl,
          feedBody,
          slugs: opts.slugs,
          colorScheme: "dark",
          scale: opts.scale,
        });
    const outPath = await stitchSheet(browser, {
      out: opts.out,
      webUrl: opts.webUrl,
      slugs: opts.slugs,
      lightCaps,
      darkCaps,
      scale: opts.scale,
      lightOnly: opts.lightOnly,
    });
    console.log(`SHEET ${outPath}`);
    for (const slug of opts.slugs) {
      console.log(`  ${slug}: ${lightCaps[slug].headline}`);
    }
    return 0;
  } finally {
    await browser.close();
  }
}

const isEntrypoint =
  process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url;

if (isEntrypoint) {
  main().then(
    (code) => process.exit(code),
    (err) => {
      console.error(`set-card-sheet failed: ${err?.message || err}`);
      process.exit(1);
    },
  );
}
