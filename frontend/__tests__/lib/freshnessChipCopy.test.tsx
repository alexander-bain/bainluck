/**
 * UX-P251 — THE CHIP SAID "STALE", AND THE BAN ON "STALE" WAS ALREADY THERE.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * `FreshnessChip` renders one of three strings, and past its five-minute
 * threshold it rendered:
 *
 *   Stale · 7m ago
 *
 * `JARGON_BANS` in `lib/copyBans.ts` has carried this since UX-P145:
 *
 *   { id: "stale", pattern: /\bstale\b/i, why: '"stale" is our price_state enum' }
 *
 * So this is not a new rule catching an old string. **The rule was already
 * there, the string shipped anyway, and every copy guard was green.**
 *
 * ═══ WHY THE SHIPPED-BUNDLE GUARD MISSED IT — THE MINIFIER SPLIT THE SENTENCE
 *
 * `shippedCopyBans.test.ts` scans `.next/static/chunks`, and it is a real
 * scanner: `extractBundleStrings` walks the source character by character and
 * even decodes `\xb7` back to `·` precisely so a word boundary lands where a
 * reader sees one. It works. It did not fire because of what it was handed.
 *
 * The component's expression was a ternary with a call in each arm, so the
 * minifier emitted it as concatenations and the banned word ended up alone in
 * a fragment. From the shipped chunk, verbatim:
 *
 *   null==n?"live":s?"Stale \xb7 ".concat(P(n)):"as of ".concat(P(n))
 *
 * The only literal carrying the word is `"Stale · "`. Trimmed, that is SEVEN
 * characters — and `isProse` opens with `if (s.length < 8) return false`.
 *
 * **The sentence a reader sees is four words long; the literal that carries
 * its banned word is one character under the prose floor.** No amount of
 * scanning the bundle harder would have found it, and the scanner was correct
 * at every step it took.
 *
 * ═══ THE GENERAL CLAUSE ═══
 *
 *   🔴 A GUARD THAT READS ASSEMBLED OUTPUT CANNOT SEE COPY ITS TOOLCHAIN TOOK
 *      APART. Interpolation is a pair of scissors: the reader's sentence and
 *      the artifact's literals are different objects, and a copy ban is
 *      enforceable only where the whole sentence exists at once.
 *
 * ═══ SO THE COPY MOVED TO WHERE A TEST CAN HOLD IT WHOLE ═══
 *
 * This repo has no `@testing-library/react` and the npm registry is
 * unreachable from here, so no test in it can run a `useEffect` — which is the
 * only thing that ever computes a non-null age. Rendering the chip through
 * `renderToStaticMarkup` reaches the `live` placeholder and nothing else, so a
 * render-only guard on this component is structurally blind to the exact
 * string that shipped.
 *
 * `freshnessLabel` is therefore the whole sentence in one pure place, and this
 * file covers BOTH halves of the seam:
 *
 *   1. every state of `freshnessLabel`, against the real ban list;
 *   2. a source assertion that the component prints `freshnessLabel`'s output
 *      and nothing else — because a pure function nobody renders is a library
 *      test that stays green the day the component stops using it.
 */

import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";

import FreshnessChip, { freshnessLabel } from "@/components/event/FreshnessChip";
import { ALL_COPY_BANS, findBannedCopy, isProse } from "@/lib/copyBans";

const CHIP_SOURCE = join(__dirname, "../../components/event/FreshnessChip.tsx");

/** Every age the chip can be handed, named by what a reader is looking at. */
const AGES: { label: string; age: number | null }[] = [
  { label: "before the effect has run", age: null },
  { label: "just updated", age: 3_000 },
  { label: "a minute old", age: 90_000 },
  { label: "one second past the threshold", age: 5 * 60 * 1000 + 1_000 },
  { label: "seven minutes old — the state Alex read", age: 7 * 60 * 1000 },
  { label: "hours old", age: 3 * 60 * 60 * 1000 },
  { label: "a day old", age: 26 * 60 * 60 * 1000 },
];

describe("UX-P251 — the freshness chip speaks English", () => {
  it("NEVER prints the word 'stale', in ANY of its states", () => {
    for (const { label, age } of AGES) {
      const { text } = freshnessLabel(age);
      // Pinned against the empty string first: "" contains no banned word, so
      // an implementation that returned nothing would pass the next line
      // vacuously.
      expect(`${label}: ${text}`).not.toBe(`${label}: `);
      expect(`${label}: ${text.toLowerCase()}`).not.toContain("stale");
    }
  });

  it("passes the SAME ban list every other copy guard applies", () => {
    for (const { label, age } of AGES) {
      const { text } = freshnessLabel(age);
      const hits = findBannedCopy(text, ALL_COPY_BANS);
      // Compared as one string so a failure names the state AND the copy,
      // rather than just "expected [] to equal [...]".
      expect(`${label} → "${text}" → ${hits.map((h) => h.ban.id).join(",")}`).toBe(
        `${label} → "${text}" → `
      );
    }
  });

  it("still tells the reader the data has STOPPED — the ban removed a word, not the warning", () => {
    // Renaming the state without keeping the signal would trade one dishonesty
    // for another. Three things must survive: the age, the `stopped` flag that
    // drives the colour and the dot, and a difference from the fresh state.
    const fresh = freshnessLabel(30_000);
    const stopped = freshnessLabel(7 * 60 * 1000);

    expect(fresh.stopped).toBe(false);
    expect(fresh.text).toBe("as of 30s ago");

    expect(stopped.stopped).toBe(true);
    expect(stopped.text).toContain("7m ago");
    expect(stopped.text).not.toBe(fresh.text);
    // The warning is carried by WORDS, not by colour alone — a reader who
    // cannot distinguish the two accent colours must still be told.
    expect(stopped.text).not.toBe("7m ago");
  });

  it("the threshold is a boundary, not a slope", () => {
    expect(freshnessLabel(5 * 60 * 1000).stopped).toBe(false);
    expect(freshnessLabel(5 * 60 * 1000 + 1).stopped).toBe(true);
  });
});

describe("UX-P251 — the pure function is what the component PRINTS", () => {
  /**
   * `reference_plant_must_hit_the_render`: a library test stays green the day
   * the component stops calling the library. The effect cannot run here, so
   * this is asserted on the source — and it RAISES rather than passing when it
   * cannot find what it is looking for, which is the difference between a
   * source scan and a wish.
   */
  it("routes every rendered string through freshnessLabel", () => {
    const src = readFileSync(CHIP_SOURCE, "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "");

    // ⚠️ ANCHOR ON THE *JSX* RETURN, NOT THE FIRST ONE. `indexOf("return (")`
    // lands on `return () => clearInterval(id)` inside the effect, which drags
    // the whole component body into the "markup" and makes this clause fail on
    // clean code. Matched on the tag that follows it, so the anchor cannot
    // drift onto another `return (` later either.
    const jsxMatch = src.match(/return \(\s*\n(\s*<[\s\S]*?)\n\s*\);/);
    if (!jsxMatch) {
      throw new Error("FreshnessChip no longer returns a JSX block — re-anchor this guard.");
    }
    const jsx = jsxMatch[1];

    // The component destructures the function's result and prints the `text`
    // binding.
    expect(src).toContain("const { text, stopped } = freshnessLabel(age);");
    expect(jsx).toContain("{text}");

    // ⚠️ THE FIRST VERSION OF THIS CLAUSE WAS A ONE-LINE REGEX AND A MUTANT
    // WALKED THROUGH IT. `/>[^<>{}\n]*[A-Za-z]{2,}[^<>{}\n]*</` cannot match a
    // text node that has an expression next to it, so planting `Data {text}`
    // in the JSX scored SURVIVE. Kept in the record rather than quietly
    // replaced: it is the same failure this file is about — a check that reads
    // an assembled artifact and misses the seam.
    //
    // The rule instead: strip every `{...}` expression (innermost-out, because
    // `className={`…${x}…`}` nests), then strip every tag. Anything with a
    // letter still standing is copy written directly into the markup.
    let stripped = jsx;
    for (let i = 0; ; i += 1) {
      const next = stripped.replace(/\{[^{}]*\}/g, "");
      if (next === stripped) break;
      if (i > 50) {
        throw new Error("Brace stripping did not reach a fixed point — re-anchor this guard.");
      }
      stripped = next;
    }
    const outsideMarkup = stripped.replace(/<[^>]*>/g, "").replace(/[^A-Za-z]/g, "");
    expect(`copy written into the JSX: ${outsideMarkup}`).toBe("copy written into the JSX: ");
  });

  it("mounts and renders the placeholder, and renders NOTHING without a timestamp", () => {
    // The one state SSR can reach. It proves the component still mounts — a
    // pure-function suite over a component that throws on render would be
    // green and worthless.
    const html = renderToStaticMarkup(<FreshnessChip asOf="2026-09-01T12:00:00Z" />);
    expect(html).toContain(freshnessLabel(null).text);
    expect(html.toLowerCase()).not.toContain("stale");

    expect(renderToStaticMarkup(<FreshnessChip asOf={null} />)).toBe("");
    expect(renderToStaticMarkup(<FreshnessChip asOf="" />)).toBe("");
  });
});

describe("UX-P251 — WHY THE BUNDLE SCANNER COULD NOT HAVE CAUGHT THIS", () => {
  /**
   * The finding, pinned as arithmetic rather than left in prose. If somebody
   * later moves the prose floor, this test names the assumption that moved.
   */
  it("the shipped literal carrying the banned word was UNDER the prose floor", () => {
    // The exact fragment, decoded, as `extractBundleStrings` hands it over.
    const shippedFragment = "Stale · ";
    expect(shippedFragment.trim()).toHaveLength(7);

    // The ban itself was never the problem — it matches the fragment fine.
    expect(findBannedCopy(shippedFragment, ALL_COPY_BANS).map((h) => h.ban.id)).toContain("stale");

    // …and `isProse` discards the fragment before the ban is ever applied.
    // BOTH arms asserted: without the second line this passes even if `isProse`
    // accepted everything, which is the vacuous version of this test.
    expect(isProse(shippedFragment)).toBe(false);
    expect(isProse("Stale · 7m ago")).toBe(true);
  });
});
