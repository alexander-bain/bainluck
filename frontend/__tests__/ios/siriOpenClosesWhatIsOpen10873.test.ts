/**
 * #10873 — a Siri, Shortcuts or Control Center "open" closes what the reader
 * left open before it routes, or the destination opens behind it.
 *
 * Measured on the iOS 27 simulator (master `e948d55104`): with the
 * win-probability chart in Full Screen, Spotlight's "Open My Stuff" ran, the
 * link was handed over and the tab switched to My Stuff (`selectedTab` 0 → 4),
 * and the reader still saw the chart. A sheet or full-screen view is presented
 * from the window's root, above every tab, so switching the tab under it
 * changes nothing a reader can see. `IntentRouteCloser10873` closes it first.
 *
 * What this pins: `ContentView`'s hand-off handler routes the consumed link on
 * iOS only from inside the closer's completion, over every foreground window.
 * The closer's own rules (what it closes, what it leaves up, the once-only
 * route) are XCTest's (`IntentRouteCloser10873Tests`). No test of the closer
 * can see whether `ContentView` still calls it; this can.
 */

import { existsSync, readFileSync } from "fs";
import { join } from "path";

const CONTENT_VIEW = join(__dirname, "../../../ios/Bain Luck/Bain Luck/ContentView.swift");
const HANDLER_HEAD = ".onReceive(IntentRouteHandoff10873.shared.settledPosts)";

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " ");
}

/** The body of the first `{ … }` block after `from`, braces matched. */
function blockAfter(source: string, from: number): string {
  const open = source.indexOf("{", from);
  if (from < 0 || open < 0) return "";
  let depth = 0;
  for (let i = open; i < source.length; i++) {
    if (source[i] === "{") depth++;
    if (source[i] === "}" && --depth === 0) return source.slice(open + 1, i);
  }
  return "";
}

function handlerBody(source: string): string {
  const head = source.indexOf(HANDLER_HEAD);
  return head < 0 ? "" : blockAfter(source, head + HANDLER_HEAD.length);
}

/** The `#if os(iOS)` branch of the handler, up to its `#else`/`#endif`. */
function iosBranch(body: string): string {
  const match = body.match(/#if\s+os\(iOS\)([\s\S]*?)#(?:else|endif)/);
  return match ? match[1] : "";
}

const d = existsSync(CONTENT_VIEW) ? describe : describe.skip;

d("a Siri/Shortcuts open closes what is open before it routes (#10873)", () => {
  const body = handlerBody(stripComments(readFileSync(CONTENT_VIEW, "utf8")));
  const ios = iosBranch(body);

  it("finds the hand-off handler and its iOS branch", () => {
    expect(body).toContain("IntentRouteHandoff10873.shared.consume()");
    expect(ios).not.toBe("");
  });

  it("routes the link only from inside the closer, over every foreground window", () => {
    const close = ios.indexOf("IntentRouteCloser10873.closePresentations(");
    expect(close).toBeGreaterThanOrEqual(0);
    expect(ios).toContain("over: IntentRouteCloser10873.foregroundRoots()");
    // The closer's trailing closure is the only place the link is routed.
    expect(blockAfter(ios, close)).toContain("handleURL(link)");
    expect(ios.match(/handleURL\(/g) ?? []).toHaveLength(1);
  });
});
