/**
 * CAPTURE RIG — the real /tournaments/us-open boards, over real production data.
 *
 * Chromium is dead in this sandbox (Mach bootstrap denied), so a screenshot is
 * not available to this lane. This is the substitute the repo already uses:
 * render the ACTUAL shipped components with `renderToStaticMarkup`, wrap them
 * in the app's OWN compiled stylesheet from `.next/static/css`, and write a
 * self-contained HTML file Alex can open. It is the real component and the real
 * CSS over the real numbers — not a re-creation of the page in mock markup,
 * which is what the Day-1 mocks deliberately were.
 *
 * Two jobs, and the second is why it lives under `__tests__`:
 *
 *   1. `UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=usOpenBoardCapture`
 *      writes `us-open-shipped.html` at a 390px mobile viewport.
 *
 *   2. With no env var set it is an ordinary test that renders every state and
 *      asserts the rig still works — a capture harness that has silently rotted
 *      is discovered at exactly the wrong moment.
 *
 * The payload is `docs/mocks/us-open/payload-2026-08-25.json`, produced by the
 * BACKEND's own `build_boards` over a bounded production read. So this file
 * exercises both halves end to end: if the Python changes shape, the render
 * breaks here.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import TournamentBoard from "@/components/tournament/TournamentBoard";
import TournamentBracket from "@/components/tournament/TournamentBracket";
import type { TournamentPayload } from "@/lib/tournament";

const PAYLOAD_PATH = path.join(
  __dirname,
  "..",
  "..",
  "..",
  "docs",
  "mocks",
  "us-open",
  "payload-2026-08-25.json"
);

function loadPayload(): TournamentPayload {
  return JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
}

/** The app's real compiled Tailwind, so the capture is not a lookalike. */
function appStylesheet(): string {
  const dir = path.join(__dirname, "..", "..", ".next", "static", "css");
  try {
    return fs
      .readdirSync(dir)
      .filter((f) => f.endsWith(".css"))
      .map((f) => fs.readFileSync(path.join(dir, f), "utf8"))
      .join("\n");
  } catch {
    return "";
  }
}

describe("US Open board capture rig", () => {
  const payload = loadPayload();

  it("has a payload with both draws", () => {
    expect(payload.boards).toHaveLength(2);
    expect(payload.boards.map((b) => b.draw)).toEqual([
      "mens-singles",
      "womens-singles",
    ]);
  });

  it("carries the real field, not a fixture", () => {
    const men = payload.boards[0];
    expect(men.rows.length).toBeGreaterThan(20);
    expect(men.rows[0].display_name).toBeTruthy();
    expect(men.rows[0].probability).toBeGreaterThan(0);
  });

  it("PRODUCTION STATE 2026-08-25: every row is non-live (#2199)", () => {
    // This is the assertion that documents why the honesty treatment is the
    // whole page this weekend rather than an edge case. When #2199 is fixed in
    // its own lane this test SHOULD start failing — that is the signal to
    // recapture, not to loosen it.
    const allRows = payload.boards.flatMap((b) => b.rows);
    expect(allRows.length).toBeGreaterThan(60);
    expect(allRows.every((r) => r.probability_is_live === false)).toBe(true);
    expect(payload.boards.every((b) => b.price_state === "dark")).toBe(true);
  });

  it("renders both boards without throwing, and says prices are paused", () => {
    const html = payload.boards
      .map((board) => renderToStaticMarkup(<TournamentBoard board={board} />))
      .join("");
    expect(html).toContain("Prices paused");
    expect(html).toContain('data-live="false"');
    expect(html).not.toContain('data-live="true"');
  });

  it("writes the capture when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      expect(true).toBe(true);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });

    const boards = payload.boards
      .map((board) => renderToStaticMarkup(<TournamentBoard board={board} />))
      .join("");
    const bracket = renderToStaticMarkup(
      <TournamentBracket rounds={[]} drawReleased={payload.draw_released} />
    );

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${payload.title} — shipped components</title>
<style>${appStylesheet()}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .phone{width:390px;margin:0 auto;background:#F5F5F7;min-height:100vh;
    border-left:1px solid #E5E7EB;border-right:1px solid #E5E7EB}
  .note{max-width:390px;margin:0 auto;padding:12px 16px;font-size:12px;color:#6B7280;
    background:#F0F0F2;border-bottom:1px solid #E5E7EB}
  .tabs{display:flex;border-bottom:1px solid #E5E7EB;background:#fff}
  .tabs span{flex:1;text-align:center;padding:13px 0;font:600 13.5px inherit;color:#9CA3AF;
    border-bottom:2px solid transparent}
  .tabs span.on{color:#111827;border-bottom-color:#111827}
  header.hero{padding:16px;background:#fff;border-bottom:1px solid #E5E7EB}
  header.hero h1{margin:0;font-size:24px;letter-spacing:-.02em;color:#111827}
  header.hero p{margin:2px 0 0;font-size:13px;color:#6B7280}
  .pad{padding:0 16px 40px}
</style></head>
<body>
<div class="note"><b>Direction C — Split Story.</b> The SHIPPED components
(<code>TournamentBoard</code>, <code>TrendSparkline</code>, <code>TournamentBracket</code>)
rendered over a production read of ${payload.boards.reduce((n, b) => n + b.rows.length, 0)}
registered contenders, ${payload.generated_at}.</div>
<div class="phone">
  <header class="hero"><h1>${payload.title}</h1><p>${payload.subtitle}</p></header>
  <div class="tabs"><span class="on">Title</span><span>Today</span><span>Bracket</span></div>
  <div class="pad">${boards}
    <h2 style="margin:22px 0 8px;font-size:12px;font-weight:700;letter-spacing:.07em;
      text-transform:uppercase;color:#9CA3AF">Bracket (its own tab)</h2>
    ${bracket}
  </div>
</div></body></html>`;

    const out = path.join(dir, "us-open-shipped.html");
    fs.writeFileSync(out, html);
    expect(fs.existsSync(out)).toBe(true);
    // The rig must not silently write an empty page.
    expect(html.length).toBeGreaterThan(5000);
  });
});
