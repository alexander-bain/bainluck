#!/usr/bin/env node
/**
 * Replay captured production payloads on localhost, so a local browser can
 * render a real page.
 *
 * WHY. Chromium in this sandbox cannot reach `api.bainluck.com` at all — every
 * request comes back `net::ERR_ACCESS_DENIED`, so `next dev` pointed at
 * production paints "Event not found / Failed to fetch". The agent's own
 * `curl` CAN reach it. So capture with curl, replay on loopback, and the
 * browser renders the real app over the real data.
 *
 * SAY WHAT THIS IS AND IS NOT. The build, the bundle, the CSS, the components
 * and the DATA are all real. The TRANSPORT is not, and neither is the timing —
 * so this proves a rendering claim and can never prove a latency, caching or
 * availability claim. Label screenshots taken through it accordingly.
 *
 * Usage:
 *   node scripts/stub-api.js --dir /tmp/apistub --port 8000
 *   # map is <file> -> <path>, edit ROUTES below or pass --map route.json
 */

const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i === -1 ? fallback : process.argv[i + 1];
}

const dir = arg("dir", "/tmp/apistub");
const port = Number(arg("port", 8000));
const mapFile = arg("map", path.join(dir, "routes.json"));

if (!fs.existsSync(mapFile)) {
  console.error(
    `no route map at ${mapFile}. Write {"/api/...": "file.json"} first.`,
  );
  process.exit(1);
}
const routes = JSON.parse(fs.readFileSync(mapFile, "utf8"));

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${port}`);
  const key = routes[url.pathname] ? url.pathname : null;

  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "*");
  if (req.method === "OPTIONS") {
    res.writeHead(204).end();
    return;
  }

  if (!key) {
    // A MISS IS LOUD. A stub that answers 200 `{}` to an unmapped path turns a
    // missing capture into a plausible-looking empty component, which is the
    // exact failure this repo calls "an empty 200 is not an absence".
    console.log(`MISS ${req.method} ${url.pathname}`);
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ detail: "stub: no capture for this path" }));
    return;
  }

  const file = path.join(dir, routes[key]);
  console.log(`HIT  ${req.method} ${url.pathname} -> ${routes[key]}`);
  res.writeHead(200, { "content-type": "application/json" });
  res.end(fs.readFileSync(file));
});

server.listen(port, "127.0.0.1", () => {
  console.log(`stub api on http://127.0.0.1:${port} serving ${dir}`);
  console.log(Object.keys(routes).join("\n"));
});
