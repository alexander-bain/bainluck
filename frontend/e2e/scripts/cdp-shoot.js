#!/usr/bin/env node
/**
 * A browser this lane can actually run — dependency-free, local, interactive.
 *
 * WHY THIS EXISTS. The UX lane's standing constraint has been "this lane cannot
 * produce browser evidence": Playwright is not installed here, the npm registry
 * is unreachable from the sandbox, and the GitHub browser-audit rail can only
 * shoot what is DEPLOYED. That last clause is the binding one — a component
 * built this cycle is by definition not deployed, so the rail structurally
 * cannot photograph it, and cycle 98 shipped THE DIVERGENCE detail view with
 * the rail photographed and the expand not.
 *
 * Two facts make the constraint smaller than it looked:
 *   - the Playwright Chromium BINARY is cached locally even though the package
 *     is not installed (`~/Library/Caches/ms-playwright/chromium-*`), and
 *   - Node 22+ ships a global WebSocket, so the Chrome DevTools Protocol needs
 *     no `ws` dependency.
 *
 * So: launch the cached Chromium, attach over CDP, drive real clicks, shoot.
 * Against `next dev` this photographs code that exists only on this branch.
 *
 * This does NOT replace the deployed browser-audit rail. It answers a different
 * question — "does the thing I just built look right" — and the rail keeps
 * answering "is production right". Do not close a production claim with it.
 *
 * Usage:
 *   node scripts/cdp-shoot.js --url http://localhost:3099/events/14788546 \
 *        --out /tmp/shots --name event.detail \
 *        --click-text "See all" --width 390 --height 900 --mobile
 */

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const CHROMIUM_GLOBS = [
  path.join(os.homedir(), "Library/Caches/ms-playwright"),
  path.join(os.homedir(), ".cache/ms-playwright"),
];

function findChromium() {
  if (process.env.CHROMIUM_BIN) return process.env.CHROMIUM_BIN;
  for (const root of CHROMIUM_GLOBS) {
    if (!fs.existsSync(root)) continue;
    for (const entry of fs.readdirSync(root)) {
      if (!entry.startsWith("chromium")) continue;
      for (const rel of [
        "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
        "chrome-linux/chrome",
      ]) {
        const p = path.join(root, entry, rel);
        if (fs.existsSync(p)) return p;
      }
    }
  }
  throw new Error(
    "no cached Chromium found; set CHROMIUM_BIN to a browser binary",
  );
}

function arg(name, fallback = undefined) {
  const i = process.argv.indexOf(`--${name}`);
  if (i === -1) return fallback;
  const next = process.argv[i + 1];
  return next && !next.startsWith("--") ? next : true;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const url = arg("url");
  const outDir = arg("out", "/tmp/cdp-shots");
  const name = arg("name", "shot");
  const clickText = arg("click-text", null);
  // Consent banners and other chrome that must go before the shot. Comma
  // separated; a miss here is NOT an error, because "the banner was already
  // gone" and "the banner never existed" are both fine outcomes.
  const preClick = arg("pre-click-text", null);
  const waitFor = arg("wait-for", null); // JS expression that must become true
  const width = Number(arg("width", 1440));
  const height = Number(arg("height", 900));
  const mobile = Boolean(arg("mobile", false));
  const settle = Number(arg("settle", 2500));
  // An expanded detail view is ~90 rows tall. At deviceScaleFactor 2 the
  // full-page bitmap blows past Chromium's max texture size and
  // Page.captureScreenshot simply never returns — which surfaces as a CDP
  // timeout, not as an error about size. Default to 1 and let the caller ask
  // for 2 on short pages.
  const scale = Number(arg("scale", 1));
  const clipHeight = Number(arg("clip-height", 0));
  // Scroll an element into view and shoot only the viewport — a 15,000px
  // full-page PNG is proof, but it is not something a person can look at.
  const scrollToText = arg("scroll-to-text", null);
  const viewportOnly = Boolean(arg("viewport-only", false));
  if (!url) throw new Error("--url is required");
  fs.mkdirSync(outDir, { recursive: true });

  const port = 9200 + Math.floor(process.pid % 500);
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "cdp-profile-"));
  const bin = findChromium();
  // `--single-process --no-zygote` is the pair that lets Chromium start at all
  // inside this sandbox; without them the renderer dies on a Mach port
  // rendezvous (`bootstrap_check_in ... Permission denied`).
  const chrome = spawn(
    bin,
    [
      "--headless=new",
      "--no-sandbox",
      "--single-process",
      "--no-zygote",
      "--disable-gpu",
      "--disable-dev-shm-usage",
      "--hide-scrollbars",
      "--force-color-profile=srgb",
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      "about:blank",
    ],
    { stdio: ["ignore", "pipe", "pipe"] },
  );
  let chromeErr = "";
  chrome.stderr.on("data", (d) => (chromeErr += d.toString()));

  let versionInfo = null;
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (r.ok) {
        versionInfo = await r.json();
        break;
      }
    } catch {
      /* not up yet */
    }
    await sleep(250);
  }
  if (!versionInfo) {
    chrome.kill("SIGKILL");
    throw new Error(`Chromium never exposed CDP.\n${chromeErr.slice(0, 800)}`);
  }

  const ws = new WebSocket(versionInfo.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.onopen = res;
    ws.onerror = rej;
  });

  let nextId = 1;
  const pending = new Map();
  const events = [];
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
    } else if (msg.method) {
      events.push(msg);
    }
  };
  const send = (method, params = {}, sessionId) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params, sessionId }));
      setTimeout(() => {
        if (pending.has(id)) {
          pending.delete(id);
          reject(new Error(`CDP timeout: ${method}`));
        }
      }, method === "Page.captureScreenshot" ? 180000 : 60000);
    });

  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await send("Target.attachToTarget", {
    targetId,
    flatten: true,
  });

  const evaluate = async (expression) => {
    const r = await send(
      "Runtime.evaluate",
      { expression, returnByValue: true, awaitPromise: true },
      sessionId,
    );
    if (r.exceptionDetails) {
      throw new Error(`page threw: ${JSON.stringify(r.exceptionDetails).slice(0, 400)}`);
    }
    return r.result.value;
  };

  await send("Page.enable", {}, sessionId);
  await send("Runtime.enable", {}, sessionId);
  // A blank screenshot is almost always a failed request or a thrown render,
  // and both are invisible in the PNG. Capture them so a bad shot explains
  // itself instead of being re-run five times.
  await send("Network.enable", {}, sessionId);
  await send("Log.enable", {}, sessionId);
  await send(
    "Emulation.setDeviceMetricsOverride",
    { width, height, deviceScaleFactor: scale, mobile },
    sessionId,
  );
  await send("Page.navigate", { url }, sessionId);

  // Wait for load, then for the app to actually paint its data. A screenshot
  // taken on `load` photographs a skeleton and reads as a broken component.
  for (let i = 0; i < 120; i++) {
    if (events.some((e) => e.method === "Page.loadEventFired")) break;
    await sleep(250);
  }
  await sleep(settle);

  if (waitFor) {
    let ok = false;
    for (let i = 0; i < 60; i++) {
      if (await evaluate(`Boolean(${waitFor})`)) {
        ok = true;
        break;
      }
      await sleep(500);
    }
    if (!ok) {
      const errs = events
        .filter((e) => e.method === "Log.entryAdded" && e.params.entry.level === "error")
        .map((e) => e.params.entry.text.slice(0, 200));
      const failed = events
        .filter((e) => e.method === "Network.loadingFailed")
        .map((e) => e.params.errorText);
      throw new Error(
        `--wait-for never became true: ${waitFor}\n` +
          `api requests: ${JSON.stringify([
            ...new Set(
              events
                .filter((e) => e.method === "Network.requestWillBeSent")
                .map((e) => e.params.request.url)
                .filter((u) => u.includes("/api/")),
            ),
          ])}\n` +
          `page errors: ${JSON.stringify(errs.slice(0, 6))}\n` +
          `failed requests: ${JSON.stringify([...new Set(failed)].slice(0, 6))}\n` +
          `body text: ${JSON.stringify((await evaluate("document.body.innerText")).slice(0, 300))}`,
      );
    }
  }

  const dismissed = [];
  if (preClick) {
    for (const label of String(preClick).split(",")) {
      const r = await evaluate(`
        (() => {
          const b = [...document.querySelectorAll('button')]
            .find(x => (x.textContent || '').trim() === ${JSON.stringify(label.trim())});
          if (!b) return { label: ${JSON.stringify(label.trim())}, hit: false };
          b.click();
          return { label: ${JSON.stringify(label.trim())}, hit: true };
        })()
      `);
      dismissed.push(r);
      if (r.hit) await sleep(600);
    }
  }

  const shots = [];
  const shoot = async (suffix) => {
    const params = { format: "png", captureBeyondViewport: !viewportOnly };
    if (clipHeight > 0) {
      params.clip = { x: 0, y: 0, width, height: clipHeight, scale: 1 };
      params.captureBeyondViewport = true;
    }
    const { data } = await send("Page.captureScreenshot", params, sessionId);
    const file = path.join(outDir, `${name}.${suffix}.png`);
    fs.writeFileSync(file, Buffer.from(data, "base64"));
    const bytes = fs.statSync(file).size;
    shots.push({ file, bytes });
    console.log(`wrote ${file} (${bytes} bytes)`);
    return file;
  };

  let clicked = null;
  if (clickText) {
    // Report what the click DID, not that it was attempted. A click that hit
    // nothing must not be reported as a state change.
    // NON-VACUITY FOR THE CLICK. `aria-expanded` read synchronously still says
    // the old value because React has not committed yet, so a naive before/after
    // reads "false -> false" on a click that worked. Measure the PAGE instead,
    // after a tick: a real expand changes how much content exists.
    const before = await evaluate(`
      ({ height: document.documentElement.scrollHeight,
         text: document.body.innerText.length })
    `);
    clicked = await evaluate(`
      (() => {
        const btns = [...document.querySelectorAll('button')];
        const b = btns.find(x => (x.textContent || '').includes(${JSON.stringify(clickText)}));
        if (!b) return { found: false, buttons: btns.map(x => (x.textContent||'').trim().slice(0,40)).slice(0,25) };
        b.scrollIntoView({ block: 'center' });
        b.click();
        return { found: true, label: (b.textContent||'').trim() };
      })()
    `);
    if (clicked.found) {
      await sleep(1500);
      const after = await evaluate(`
        ({ height: document.documentElement.scrollHeight,
           text: document.body.innerText.length,
           ariaExpanded: (() => {
             const b = [...document.querySelectorAll('button')]
               .find(x => (x.getAttribute('aria-expanded') !== null));
             return b ? b.getAttribute('aria-expanded') : null;
           })() })
      `);
      clicked.before = before;
      clicked.after = after;
      clicked.changed_the_page =
        after.height > before.height && after.text > before.text;
    }
    if (!clicked.found) {
      throw new Error(
        `--click-text ${JSON.stringify(clickText)} matched no button. ` +
          `buttons on page: ${JSON.stringify(clicked.buttons)}`,
      );
    }
    if (!clicked.changed_the_page) {
      throw new Error(
        `clicked ${JSON.stringify(clicked.label)} and NOTHING CHANGED ` +
          `(${JSON.stringify(clicked.before)} -> ${JSON.stringify(clicked.after)}). ` +
          `A screenshot of this would be a photograph of the unexpanded state.`,
      );
    }
  }

  if (scrollToText) {
    const scrolled = await evaluate(`
      (() => {
        const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
        let el;
        while ((el = walk.nextNode())) {
          if ((el.textContent || '').trim().startsWith(${JSON.stringify(scrollToText)})
              && el.children.length === 0) {
            el.scrollIntoView({ block: 'start' });
            window.scrollBy(0, -80);
            return { found: true, y: Math.round(window.scrollY) };
          }
        }
        return { found: false };
      })()
    `);
    if (!scrolled.found) throw new Error(`--scroll-to-text not found: ${scrollToText}`);
    await sleep(600);
  }

  await shoot(mobile ? "mobile" : "desktop");

  const requested = [
    ...new Set(
      events
        .filter((e) => e.method === "Network.requestWillBeSent")
        .map((e) => e.params.request.url)
        .filter((u) => u.includes("/api/")),
    ),
  ];
  const consoleErrors = events
    .filter((e) => e.method === "Runtime.consoleAPICalled" && e.params.type === "error")
    .map((e) => (e.params.args || []).map((a) => a.value ?? a.description).join(" "))
    .slice(0, 20);
  const failedRequests = events
    .filter((e) => e.method === "Network.loadingFailed")
    .map((e) => ({ error: e.params.errorText, type: e.params.type }))
    .slice(0, 20);
  const logEntries = events
    .filter((e) => e.method === "Log.entryAdded" && e.params.entry.level === "error")
    .map((e) => `${e.params.entry.source}: ${e.params.entry.text}`.slice(0, 200))
    .slice(0, 20);

  const metrics = await evaluate(`
    ({
      title: document.title,
      url: location.href,
      scrollHeight: document.documentElement.scrollHeight,
      textLength: document.body.innerText.length,
    })
  `);

  const manifest = { url, name, width, height, mobile, dismissed, clicked, metrics,
                     requested, consoleErrors, failedRequests, logEntries, shots };
  fs.writeFileSync(
    path.join(outDir, `${name}.${mobile ? "mobile" : "desktop"}.json`),
    JSON.stringify(manifest, null, 2),
  );
  console.log(JSON.stringify(manifest, null, 2));

  ws.close();
  chrome.kill("SIGKILL");
  fs.rmSync(userDataDir, { recursive: true, force: true });
}

main().catch((e) => {
  console.error("FAILED:", e.message);
  process.exit(1);
});
