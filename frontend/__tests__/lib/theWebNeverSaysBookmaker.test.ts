/**
 * #4096 — the WEB never says "bookmaker" either.
 *
 * `__tests__/ios/appNeverSaysBookmaker.test.ts` enforced standing notice 33 the
 * day it was issued, correctly and only over `ios/`. This is the half that was
 * missing, and the gap was not theoretical: while that guard was green,
 * `bainluck.com/calibration` was serving all five of these to a reader —
 *
 *   1. "vig-removed consensus closing odds across 20+ **bookmakers**"   (page prose)
 *   2. "the gap is the cost of the fallback, not a finding about **the books**" (page prose)
 *   3. `Per-Bookmaker (Odds API)`  in `calibrationProviders`' house-style map
 *   4. `Per-Bookmaker (Odds API)`  in `sourceColors`' chart-legend registry
 *   5. `Books`                     in `LeagueBinaryBoard`'s venue badge
 *
 * — and the backend was publishing the same name in `source_labels` plus two
 * exclusion notes the page renders verbatim.
 *
 * ═══ THE THING THAT MAKES THIS MORE THAN A COPY RULE ═══
 *
 * (3) is the reason a backend-only rename fixes NOTHING a reader sees.
 * `makeSourceLabeller` puts this page's curated map at tier 1 and the server's
 * published `source_labels` at tier 2 — deliberately, so the SOURCE row can read
 * "Odds API" while the FAMILY row above it reads "Sportsbooks (Odds API)". That
 * precedence is correct and stays; it also means a clean server label loses to a
 * dirty local one, silently and forever. `theHouseStyleMapCannotOutrankTheBan`
 * below is the assertion that catches exactly that, and it is the one that would
 * have failed on master before this ship.
 *
 * ═══ WHAT IS ASSERTED, AND WHAT IS NOT ═══
 *
 * Two different kinds of claim, because two different things went wrong:
 *
 *   · over the LABEL REGISTRIES — a RUNTIME assertion over the values the
 *     functions actually return, not a source scan. New entries are discovered
 *     rather than listed, so the guard covers a source added next month.
 *
 *   · over the CALIBRATION PAGE'S PROSE — a source scan, because copy is not
 *     reachable from a unit test (the page is a `"use client"` component behind
 *     SWR; this is the same reason `calibrationProviders.ts` was extracted).
 *     Comments are stripped: notice 33 is about what a READER sees, and a
 *     comment recording why a word was banned must be free to name it.
 *
 * NOT claimed: that the whole site is clean. This covers the calibration surface
 * and the shared source registries every chart legend reads. Other surfaces are
 * their owning lane's, under notice 33's "fix it in passing".
 */

import { readFileSync } from "fs";
import { join } from "path";

import { bannedWordIn, bannedWordInProse } from "../helpers/bannedSupplierWords";
import {
  makeSourceLabeller,
  prettifySourceKey,
  providerLabel,
  providerOf,
  sourceLabel as providerSourceLabel,
} from "@/lib/calibrationProviders";
import { SOURCE_COLORS, sourceLabel as registrySourceLabel } from "@/lib/sourceColors";

const CALIBRATION_PAGE = join(__dirname, "../../app/calibration/page.tsx");

/**
 * Comments removed, so a comment may name the banned word and prose may not.
 *
 * `(?<!:)` on the line-comment pattern keeps `https://…` from being eaten as a
 * comment and swallowing the rest of the line with it — the page carries a DOI
 * link in the very paragraph this guard exists to police, so without it the
 * scan would silently stop reading mid-sentence and report a clean pass.
 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

describe('#4096 — the web never says "bookmaker"', () => {
  describe("the shared source registries", () => {
    it("no label in the chart-legend registry carries a banned word", () => {
      // Discovered, not listed: every entry, including ones added after this
      // guard was written. `sourceColors` feeds chart legends across the site,
      // so one dirty label here reaches far more than the calibration page.
      const offenders = Object.entries(SOURCE_COLORS)
        .map(([key, { label }]) => [key, label, bannedWordIn(label)] as const)
        .filter(([, , hit]) => hit !== null)
        .map(([key, label, hit]) => `SOURCE_COLORS.${key} = "${label}" — ${hit}`);

      expect(offenders).toEqual([]);
    });

    it("no name either labeller returns for a known source carries one", () => {
      // Both modules export a `sourceLabel` and they are NOT the same function —
      // the page reads one and the charts read the other, which is precisely how
      // `Per-Bookmaker (Odds API)` came to be written down twice and fixed once.
      const keys = Object.keys(SOURCE_COLORS);
      const offenders: string[] = [];

      for (const key of keys) {
        for (const [module, name] of [
          ["sourceColors", registrySourceLabel(key)],
          ["calibrationProviders", providerSourceLabel(key)],
          // Through `providerOf`, not the source key directly: `providerLabel`
          // is only ever handed a PROVIDER, and feeding it `odds_api_bookmaker`
          // would be testing a call the page cannot make.
          ["calibrationProviders/provider", providerLabel(providerOf(key))],
        ] as const) {
          const hit = bannedWordIn(name);
          if (hit) offenders.push(`${module}("${key}") = "${name}" — ${hit}`);
        }
      }

      expect(offenders).toEqual([]);
    });

    it("THE NEXT KEY: the fallback prettifier cannot invent one either", () => {
      // The hazard a pin on today's labels cannot see, and the reason this arm
      // exists at all — it is what the previous arm caught while being written.
      // `odds_api_bookmaker_v2` would arrive with NO curated entry, fall to the
      // prettifier, and reach a reader as "Odds API Bookmaker V2" with every
      // other guard in this file still green. A denylist of known-unknowns hands
      // the claim to the first new one; the token rewrite closes the class.
      const uncurated = [
        "odds_api_bookmaker_v2",
        "some_new_bookmaker_feed",
        "books_consensus",
        "sharp_book",
      ];
      const offenders = uncurated
        .map((key) => [key, prettifySourceKey(key), bannedWordIn(prettifySourceKey(key))] as const)
        .filter(([, , hit]) => hit !== null)
        .map(([key, name, hit]) => `prettifySourceKey("${key}") = "${name}" — ${hit}`);

      expect(offenders).toEqual([]);
      // And it is a RESPELLING, not a deletion — the name still describes the
      // source, or the floor has been traded for a blank.
      expect(prettifySourceKey("odds_api_bookmaker_v2")).toBe("Odds API Sportsbook V2");
      // The rewrite is scoped to whole tokens: a key that merely CONTAINS the
      // letters is untouched, so it cannot mangle an unrelated name.
      expect(prettifySourceKey("bookings_feed")).toBe("Bookings Feed");
    });
  });

  describe("the house-style map cannot outrank the ban", () => {
    it("THE REGRESSION: a clean server label does not rescue a dirty local one", () => {
      // The exact shape of #4096. Tier 1 (this page's curated map) wins over
      // tier 2 (the server's `source_labels`) BY DESIGN, so the only way the
      // reader sees a clean name is for the local entry to be clean. Hand the
      // labeller a perfect server vocabulary and assert on what comes back: on
      // master before this ship this returned "Per-Bookmaker (Odds API)".
      const label = makeSourceLabeller({
        odds_api_bookmaker: { label: "Per-sportsbook (Odds API)" },
        odds_api: { label: "Sportsbooks" },
      });

      for (const key of ["odds_api_bookmaker", "odds_api"]) {
        expect([key, bannedWordIn(label(key))]).toEqual([key, null]);
      }
    });

    it("and the precedence it relies on is still the documented one", () => {
      // Guard the guard. If tier 1 ever stopped winning, the assertion above
      // would pass for the wrong reason — it would be reading the server's
      // label, not the local one — and the local map could rot unnoticed.
      const label = makeSourceLabeller({ odds_api: { label: "Sportsbooks" } });
      expect(label("odds_api")).toBe("Odds API");
    });
  });

  describe("the calibration page's own prose", () => {
    const page = () => stripComments(readFileSync(CALIBRATION_PAGE, "utf8"));

    it("carries no banned word outside its comments", () => {
      // Whole-file rather than JSX-text-only, and that is a deliberate widening:
      // extracting text nodes from 2,000 lines of TSX is guesswork, and the file
      // legitimately contains no supplier identifier at all — the wire keys it
      // touches are `odds_api*`, which are key-shaped and exempt. So the strict
      // form costs nothing today and fails loudly the moment copy regresses.
      const offenders = page()
        .split("\n")
        .map((line, i) => [i + 1, line, bannedWordInProse(line.trim())] as const)
        .filter(([, , hit]) => hit !== null)
        .map(([n, line, hit]) => `page.tsx:${n} — ${hit} — ${line.trim().slice(0, 120)}`);

      expect(offenders).toEqual([]);
    });

    it("fires on the REAL pre-fix lines, verbatim from master before this ship", () => {
      // Not synthetics that prove a regex can match. Both were live on
      // production and both are what a reader actually read.
      const prefix = [
        "we use vig-removed consensus closing odds across 20+ bookmakers.",
        "stronger test, so the gap is the cost of the fallback, not a finding about the books.",
        '  odds_api_bookmaker: "Per-Bookmaker (Odds API)",',
        '  odds_api: "Books",',
      ];
      for (const line of prefix) {
        expect([line, bannedWordInProse(line) !== null]).toEqual([line, true]);
      }
    });

    it("does NOT fire on the approved word, on a wire key, or on the repaired copy", () => {
      // The inverse hazard, and the one that gets scans deleted. Each of these
      // is live after this ship.
      const legitimate = [
        "we use vig-removed consensus closing odds across 20+ sportsbooks.",
        "stronger test, so the gap is the cost of the fallback, not a finding about the",
        '  odds_api_bookmaker: "Per-sportsbook (Odds API)",',
        '  odds_api: "Sportsbooks",',
        "odds_api_bookmaker",
        "sportsbook rows have a close",
      ];
      for (const line of legitimate) {
        expect([line, bannedWordInProse(line)]).toEqual([line, null]);
      }
    });

    it("the scan is reading a real file, and the DOI link does not blind it", () => {
      // Two ways this whole block could pass vacuously: an unreadable path, and
      // the `//` in `https://doi.org/…` eating the rest of the paragraph. The
      // banned word sat in that exact paragraph, so this is not hypothetical.
      const text = page();
      expect(text.length).toBeGreaterThan(10_000);
      expect(text).toContain("https://doi.org/");
      expect(text).toContain("vig-removed consensus closing odds");
    });
  });
});
