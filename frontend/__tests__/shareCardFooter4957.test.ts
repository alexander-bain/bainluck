/**
 * EVERY SHARE CARD NAMES THE SITE, NOT SOMEONE ELSE'S PAGE — #4957.
 *
 * ═══ WHAT A PERSON SAW ═══
 *
 * The share card for an EVENT printed `bainluck.com/discover` in its footer —
 * the address of a different page than the one in the picture. Fetched live
 * 2026-09-11T00:40Z, `/events/15304803/opengraph-image` drew Pirates 47% /
 * Cubs 53% above the words `bainluck.com/discover`.
 *
 * The clickable target was always the event URL, so nobody landed in the wrong
 * place by tapping. The cost is a card pasted into a group chat advertising an
 * address that is not the thing being shown: type it in and you get the
 * Discover feed instead of the game.
 *
 * ═══ WHY THE GUARD IS CROSS-CARD AND NOT A LINE PIN ═══
 *
 * Three of the four cards already printed the bare wordmark, so this was never
 * a house style — it was a copy-paste leak from the Discover card that only one
 * route carried. Pinning line 149 of `events/[id]` would let the same leak land
 * in `futures/[id]` tomorrow and pass.
 *
 * So the assertion is the CONTRACT the four cards share: each names the site,
 * and none of them names a path. That is the defect class — one card drifting
 * away from its siblings — rather than the one instance of it.
 *
 * A render test is not available honestly here, for the reason
 * `shareCardReaderWords4839.test.ts` sets out: these routes are edge-runtime
 * `ImageResponse` handlers whose output is a PNG. Reading the source is the
 * better instrument. The live PNG read is in the issue, where it belongs.
 *
 * NOT IN SCOPE, deliberately: `app/api/og/stats/route.tsx` also prints
 * `bainluck.com/discover`. That card is a user's own prediction-stats card
 * whose page really does live under Discover (`/discover/stats`), it is a
 * different route family (an `api/og` handler, not an `opengraph-image.tsx`),
 * and #4957's table scopes the defect to the four cards below. Widening a
 * one-word copy fix into a card nobody has looked at is how a sweep breaks a
 * string some earlier decision wanted.
 */

import fs from "node:fs";
import path from "node:path";

/** The four `opengraph-image.tsx` routes named in #4957, by their route path. */
const CARDS: ReadonlyArray<readonly [string, readonly string[]]> = [
  ["/ (default)", ["opengraph-image.tsx"]],
  ["/about", ["about", "opengraph-image.tsx"]],
  ["/events/[id]", ["events", "[id]", "opengraph-image.tsx"]],
  ["/futures/[id]", ["futures", "[id]", "opengraph-image.tsx"]],
];

/** What the footer must read, on every card. */
const WORDMARK = "bainluck.com";

const read = (segments: readonly string[]) =>
  fs.readFileSync(path.join(process.cwd(), "app", ...segments), "utf8");

/**
 * The wordmark text nodes a reader actually sees, extracted from the JSX.
 *
 * Deliberately an EXTRACT-THEN-COMPARE, not a substring or regex test of the
 * source. The first cut of this guard asked `src.includes("bainluck.com")` and
 * matched `/bainluck\.com\/[a-z]/`; CodeQL reads a bare hostname in a substring
 * check or an unanchored regex as URL validation and failed the sha with three
 * HIGH alerts (`js/incomplete-url-substring-sanitization`,
 * `js/regex/missing-regexp-anchor`) — a standing-notice-32 refusal. Comparing an
 * extracted node for equality carries no host pattern, and is the stronger
 * assertion anyway: it catches a path, a deleted footer and a duplicated one,
 * where `includes` caught only the first.
 *
 * Newlines are excluded from the character class so a node cannot span from one
 * tag to a `<` far below and swallow the `API_URL` constant.
 */
const footerWordmarks = (src: string): string[] =>
  (src.match(/>[^<>{}\n]+</g) ?? [])
    .map((node) => node.slice(1, -1).trim())
    .filter((text) => text.toLowerCase().includes("bainluck"));

describe("every share card's footer names the site", () => {
  it("all four cards this guards are actually on disk", () => {
    // A path typo would make every scan below vacuously true — the lesson
    // the #4839 guard paid for.
    for (const [route, segments] of CARDS) {
      const src = read(segments);
      expect(`${route}: ${src.length > 500}`).toBe(`${route}: true`);
      expect(`${route}: ${src.includes("ImageResponse")}`).toBe(`${route}: true`);
    }
  });

  it("prints the bare wordmark, and never a path — the #4957 defect, on any card", () => {
    // Exactly one wordmark node per card, reading exactly the wordmark.
    // `bainluck.com/discover` is what shipped on /events/[id]; any sibling that
    // grows a path fails the same assertion, which is the class.
    for (const [route, segments] of CARDS) {
      expect(`${route}: ${JSON.stringify(footerWordmarks(read(segments)))}`).toBe(
        `${route}: ${JSON.stringify([WORDMARK])}`,
      );
    }
  });

  it("the API base URL is not mistaken for a footer", () => {
    // `api.bainluck.com` is a fetch default in two of these files and must never
    // be what the assertion above is reading. It is not a JSX text node, so the
    // extractor must not see it — one footer node, not two.
    const events = read(["events", "[id]", "opengraph-image.tsx"]);
    expect(events).toContain("https://api.bainluck.com");
    expect(footerWordmarks(events).length).toBe(1);
  });
});
