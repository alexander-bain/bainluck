/**
 * THE SHARE CARD SPEAKS THE READER'S WORDS — #4839.
 *
 * ═══ WHAT A PERSON SAW ═══
 *
 * The event share card is the first thing anyone sees of Bain Luck: a pasted
 * link unfurling in iMessage, Slack or a tweet. On 2026-09-10 the card for
 * `/events/15308639` printed, top-right, the raw machine key **`baseball_mlb`**,
 * and drew the New York Yankees' crest as **`YY`**.
 *
 * Both came from the card keeping its own private copy of a rule the codebase
 * had already solved:
 *
 *   - the league pill rendered `event.sport_key || event.sport` with nothing
 *     mapping it, while `getSportLabel` — the call `EventCard` already makes on
 *     the very page the card links to — answers in English;
 *   - a local `initials()` took `.slice(-2)`, the LAST two words, so every
 *     three-word team lost its first: Yankees `YY`, Chiefs `CC`, Lakers `AL`.
 *     `teamCrestBadge` had already been measured over all 19,675 distinct
 *     production team names for exactly this (#4466).
 *
 * Two-word teams were correct throughout, which is why it survived: the
 * Rockies' `CR` sat beside the Yankees' `YY` and made the defect read as a font
 * problem rather than a logic one.
 *
 * ═══ WHY THIS GUARD IS A SOURCE SCAN AND NOT A RENDER ═══
 *
 * The defect class is not "this string is wrong". It is **a second
 * implementation of a solved rule, drifting**. A test that pinned the card's
 * output strings would pass just as happily against a fresh private copy of the
 * rule that happened to agree today — and the copy is the bug. So the load-
 * bearing assertion is that the card DELEGATES.
 *
 * A render test is also not available honestly here: the route is an edge
 * runtime `ImageResponse`, whose output is a PNG. Asserting on decoded pixels
 * would be a worse instrument than reading the call.
 *
 * The behavioural half is still pinned below, on the issue's own specimens,
 * because delegation to a helper that returns `YY` would satisfy the scan.
 */

import fs from "node:fs";
import path from "node:path";

import { getSportLabel } from "@/lib/sportCategories";
import { teamCrestBadge } from "@/lib/teamShortName";

const CARD = path.join(
  process.cwd(),
  "app",
  "events",
  "[id]",
  "opengraph-image.tsx",
);

describe("the event share card delegates, rather than keeping its own rules", () => {
  const src = fs.readFileSync(CARD, "utf8");

  it("the card this guards is actually there", () => {
    // A path typo would make every scan below vacuously true.
    expect(src.length).toBeGreaterThan(500);
    expect(src).toContain("ImageResponse");
  });

  it("names the league through the same helper the event page uses", () => {
    expect(src).toContain("getSportLabel");
  });

  it("never prints a raw sport key straight into the pill", () => {
    // The exact expression that shipped `baseball_mlb`, in the two orderings
    // it could be written.
    expect(src).not.toMatch(/\{\s*event\??\.\s*sport_key\s*\|\|/);
    expect(src).not.toMatch(/\{\s*event\??\.\s*sport\s*\|\|\s*event\??\.\s*sport_key/);
  });

  it("draws crests through the measured badge helper", () => {
    expect(src).toContain("teamCrestBadge");
  });

  it("keeps no local initials rule of its own", () => {
    // `.slice(-2)` is the specific defect; `function initials` is the shape it
    // lived in. Either returning is the regression.
    expect(src).not.toContain("function initials");
    expect(src).not.toContain("slice(-2)");
  });
});

describe("what the helpers actually print for the specimens in #4839", () => {
  it("a three-word team keeps the letters a fan would recognise", () => {
    // The reported defect, and its neighbours from the same rule.
    expect(teamCrestBadge("New York Yankees")).toBe("NYY");
    expect(teamCrestBadge("Los Angeles Lakers")).toBe("LAL");

    // MEASURED, not predicted: the issue guessed `KC` for the Chiefs and the
    // helper says `CHI`. "City" is a CLUB_TYPE_SUFFIX (Manchester City, Norwich
    // City), so `isNonDistinctiveTrailingWord` filters it and two distinctive
    // tokens fall to the last-word rule. That is #4466's shipped answer, drawn
    // on Discover's crest tiles today; the share card agreeing with it is the
    // point of this ship, so the pin follows the helper rather than the issue.
    expect(teamCrestBadge("Kansas City Chiefs")).toBe("CHI");
  });

  it("and none of them is the last-two-words fragment that shipped", () => {
    // Pinned as the ANTI-value, so a future change to the badge rule that
    // happens to re-introduce this class fails here and not in someone's
    // group chat.
    for (const [name, shipped] of [
      ["New York Yankees", "YY"],
      ["Kansas City Chiefs", "CC"],
      ["Los Angeles Lakers", "AL"],
    ] as const) {
      expect(teamCrestBadge(name)).not.toBe(shipped);
    }
  });

  it("a two-word team is unchanged — that half was always right", () => {
    expect(teamCrestBadge("Colorado Rockies")).toBe("ROC");
  });

  it("the league pill reads as words, not as a key", () => {
    const label = getSportLabel("baseball_mlb", null);
    expect(label).toBe("MLB");
    expect(label).not.toContain("_");
  });

  it("the served display name wins when the map has no word for the key", () => {
    // The card passes `sport_name` through, so this is the card's behaviour too.
    expect(getSportLabel("soccer_netherlands_eredivisie", "Dutch Eredivisie")).toBe(
      "Dutch Eredivisie",
    );
  });
});
