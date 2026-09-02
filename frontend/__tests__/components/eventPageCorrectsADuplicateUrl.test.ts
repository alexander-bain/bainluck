/**
 * Q050, layer 2 — the event page WIRES the redirect.
 *
 * `canonicalEventUrl.test.ts` proves the decision. It stays green if the page
 * never calls it, which is the exact failure that pattern is prone to
 * (a primitive proved and then dropped from the render). This reads the page.
 *
 * A source-shape guard is the right tool here and not a compromise: the wiring
 * is a `useEffect` calling `router.replace`, and `frontend/jest` is
 * `testEnvironment: node` with no jsdom, so effects have no render path to
 * assert against at all.
 *
 * Comments are STRIPPED before every assertion. The page carries a long comment
 * block explaining this redirect, and it names `router.replace`,
 * `canonicalEventHref` and `/events/` — so a naive substring check would match
 * the explanation and pass over code that had been deleted.
 */
import { readFileSync } from "fs";
import { join } from "path";

const PAGE = join(
  process.cwd(),
  "app",
  "events",
  "[id]",
  "page.tsx",
);

function sourceWithoutComments(): string {
  const raw = readFileSync(PAGE, "utf8");
  return raw
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");
}

describe("the event page corrects a duplicate url", () => {
  const src = sourceWithoutComments();

  it("still contains live code after comments are stripped", () => {
    // The stripper is doing real work; prove it did not eat the file.
    expect(src).toContain("export default function EventPage");
    expect(src.length).toBeGreaterThan(1000);
  });

  it("asks the shared primitive where to go", () => {
    expect(src).toContain("canonicalEventHref(");
    expect(src).toContain('from "@/lib/canonicalEventUrl"');
  });

  it("hands the answer to router.replace, not router.push", () => {
    expect(src).toMatch(/router\.replace\(canonicalHref\)/);
    // `push` would leave the ghost url in history, so Back lands right back on
    // it and redirects again — a page the reader cannot leave.
    expect(src).not.toMatch(/router\.push\(canonicalHref\)/);
  });

  it("guards the effect so a null answer never navigates", () => {
    expect(src).toMatch(/if\s*\(!canonicalHref\)\s*return;/);
  });

  it("passes the ROUTE id and the SERVED id, in that order", () => {
    // Reversed, every correctly-addressed page would redirect to itself.
    expect(src).toMatch(
      /canonicalEventHref\(\s*eventId,\s*canonicalEventId,/,
    );
    expect(src).toMatch(/const canonicalEventId = event\?\.id;/);
  });
});
