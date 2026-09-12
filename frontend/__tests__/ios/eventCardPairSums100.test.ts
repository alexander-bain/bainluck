/**
 * #3049 — the game card's two percentages are ONE decision, so the strip can
 * never print 101.
 *
 * ## What a reader saw
 *
 * On the Sports tab at 15:05Z on 2026-09-04, all three live US Open cards printed
 * a pair summing to 101 — Sabalenka 95/6, Cirstea 61/40, Kostyuk 76/25 — while the
 * `Opened …` line on the same cards summed to 100 every time, and the event page
 * hero for the same match printed 5/95. The app contradicted itself on two screens
 * and within one card.
 *
 * ## Why the existing guard could not see it
 *
 * `duelPercentServedPair.test.ts` (#2279) bans two shapes: a PER-SIDE COALESCE
 * (`odds.awayRenderedPercent ?? …`) and a PRIVATE PERCENT (`Int((p * 100).rounded())`).
 * `EventCardView` committed neither. `probabilityWithMovement(for:)` is invoked
 * once per side and simply called `formatProbability(prob)` with no
 * `renderedPercent:` at all — the OMISSION form of the same defect, which is
 * invisible to both predicates. That surface was also absent from that file's
 * `SURFACES` list, so nothing pointed at it positively either.
 *
 * So the predicate here is the omission: on this surface every `formatProbability`
 * call passes a percent that came from a pair helper. Venues quote on a
 * half-percent grid, so a side whose `p * 100` lands exactly on `.5` rounds up
 * independently on both sides — that is the whole mechanism, and it is why a
 * per-side call site is wrong even when its arithmetic is right.
 *
 * 🔴 STRINGS ARE KEPT, NOT STRIPPED (#4337). One of the three call sites is
 * `Text("Opened \(formatProbability(...))/\(formatProbability(...))")` — Swift
 * computes inside `\( )`, so the strip that protects a scanner from its own
 * explanatory prose also deletes the place two thirds of this defect lives. The
 * capability section below pins that both ways.
 *
 * This file is jest and not Swift because CI compiles no Swift (#4302), and a
 * gate that never runs is not a gate.
 */

import { existsSync, readFileSync } from "fs";
import { join } from "path";

import { renderedDuelPercents } from "@/lib/renderedPercent";

import { swiftCode, swiftCodeKeepingStrings } from "../helpers/swiftSource";

const REPO_ROOT = join(__dirname, "../../..");
const APP_ROOT = join(REPO_ROOT, "ios/Bain Luck/Bain Luck");
const CARD = join(APP_ROOT, "Components/EventCardView.swift");
const SHARED = join(APP_ROOT, "Utilities/RenderedPercent.swift");

const read = (path: string) => readFileSync(path, "utf8");

/**
 * Every `formatProbability(` call in the source, each returned with its argument
 * list BALANCED.
 *
 * 🔴 A SLICE THAT STOPS AT THE FIRST `)` STOPS IN THE WRONG PLACE. The live call
 * site is `formatProbability(prob, renderedPercent: side == .home ? livePercents[1]
 * : livePercents[0])`, and a naive `indexOf(")")` ends inside nothing here — but
 * the sibling idiom `teamColors(event)` cost a previous native guard exactly that
 * (#4117), and the `Opened` line nests two of these calls inside one string. So
 * the depth is counted rather than guessed.
 *
 * Takes ALREADY-STRIPPED code so the caller cannot pick a read; see the note in
 * the header about why the strip must keep strings.
 */
function formatProbabilityCalls(strippedSrc: string): string[] {
  const calls: string[] = [];
  const needle = "formatProbability(";
  let from = 0;
  for (;;) {
    const start = strippedSrc.indexOf(needle, from);
    if (start === -1) break;
    let depth = 0;
    let end = start + needle.length - 1;
    for (let i = start + needle.length - 1; i < strippedSrc.length; i += 1) {
      const ch = strippedSrc[i];
      if (ch === "(") depth += 1;
      else if (ch === ")") {
        depth -= 1;
        if (depth === 0) {
          end = i;
          break;
        }
      }
    }
    calls.push(strippedSrc.slice(start, end + 1));
    from = start + needle.length;
  }
  return calls;
}

/**
 * THE PRODUCTION SCAN. Takes RAW source and answers the one question: does any
 * `formatProbability` call on this surface render a side without a pair-derived
 * percent? Non-empty is the defect.
 *
 * 🔴 The strip lives INSIDE, and the input is raw, so there is no call site left
 * that can choose the blind read. The capability section calls this exact
 * function rather than a copy of its regex.
 */
function callsMissingRenderedPercent(swiftSrc: string): string[] {
  return formatProbabilityCalls(swiftCodeKeepingStrings(swiftSrc)).filter(
    (call) => !call.includes("renderedPercent:"),
  );
}

// ---------------------------------------------------------------------------
// A suite pointed at nothing passes. The paths are asserted as tests, not used
// to skip.
// ---------------------------------------------------------------------------

describe("#3049 — the files this guard reads all exist", () => {
  it.each([CARD, SHARED])("%s", (path) => {
    expect(existsSync(path)).toBe(true);
  });

  it("the card really does draw probabilities for this guard to check", () => {
    expect(formatProbabilityCalls(swiftCodeKeepingStrings(read(CARD))).length)
      .toBeGreaterThanOrEqual(3);
  });
});

// ---------------------------------------------------------------------------
// 0. THE GUARD'S OWN CAPABILITY.
//
// The scan below is a negative assertion over a tree that is now clean, so it
// passes whether or not it can see anything. Its subject here is the SCAN, fed a
// specimen that has re-introduced the defect in the two places Swift writes it.
// ---------------------------------------------------------------------------

describe("#3049 — the scan sees the omission where Swift writes it", () => {
  /** The defect as it actually shipped: a bare per-side call, plus one nested in a string. */
  const DEFECTIVE = [
    "struct SomeCard: View {",
    "    var body: some View {",
    "        Text(formatProbability(prob))",
    '        Text("Opened \\(formatProbability(awayOpen))/\\(formatProbability(homeOpen))")',
    "    }",
    "}",
  ].join("\n");

  /** The same surface written correctly, so the scan is shown to discriminate. */
  const CORRECT = [
    "struct SomeCard: View {",
    "    var body: some View {",
    "        Text(formatProbability(prob, renderedPercent: livePercents[1]))",
    '        Text("Opened \\(formatProbability(awayOpen, renderedPercent: openingPercents[0]))")',
    "    }",
    "}",
  ].join("\n");

  it("the specimen really does contain three bare calls before any strip", () => {
    // Without this the rest of the describe could pass on a typo'd specimen, and
    // a fixture that misrepresents the defect makes every assertion vacuous.
    expect(DEFECTIVE.match(/formatProbability\(/g) ?? []).toHaveLength(3);
    expect(DEFECTIVE).not.toContain("renderedPercent:");
  });

  it("THE PRODUCTION SCAN sees all three, including the two inside the string", () => {
    // 🔴 The one that matters. Two of the three live inside a `Text("…")`, which
    // is exactly what a string-stripping read deletes.
    expect(callsMissingRenderedPercent(DEFECTIVE)).toHaveLength(3);
  });

  it("and reports nothing on the same surface written correctly", () => {
    // A scan that flags everything is as useless as one that flags nothing.
    expect(callsMissingRenderedPercent(CORRECT)).toHaveLength(0);
  });

  it("the string-stripping read is blind to the two in the string", () => {
    // Pinned rather than deleted: it is WHY this scan keeps strings, and it is
    // what an edit back to `swiftCode` would restore. Applies the extractor
    // directly because the scan itself forces the correct read.
    const blind = swiftCode(DEFECTIVE);
    expect(formatProbabilityCalls(blind)).toHaveLength(1);
  });

  it("the scan still strips comments, so the fix may document itself", () => {
    // The original reason for any strip at all. Without it this surface would
    // red on its own explanatory comment and someone would revert the guard.
    const documented = [
      "// Was: Text(formatProbability(prob)) — the per-side form, see #3049.",
      "/* and formatProbability(homeOpen) was the other one. */",
      "Text(formatProbability(prob, renderedPercent: livePercents[1]))",
    ].join("\n");
    expect(callsMissingRenderedPercent(documented)).toHaveLength(0);
  });

  it("the balanced extractor does not stop at the first inner paren", () => {
    // #4117's lesson, pinned: a slice ending at `indexOf(")")` would truncate a
    // call whose argument contains a call, and the truncated text would then
    // satisfy the `renderedPercent:` check by accident or fail it by accident.
    const nested = "Text(formatProbability(probability(for: side), renderedPercent: pcts[0]))";
    const [call] = formatProbabilityCalls(nested);
    expect(call).toBe("formatProbability(probability(for: side), renderedPercent: pcts[0])");
  });
});

// ---------------------------------------------------------------------------
// 1. The production surface.
// ---------------------------------------------------------------------------

describe("#3049 — every probability the card prints came from a pair", () => {
  it("no formatProbability call on the card omits renderedPercent", () => {
    // 🔴 RAW SOURCE IN (#4337). The `Opened` line's two calls are inside a string
    // literal; under the stripping read this assertion would pass on a card that
    // had lost both of them.
    // #5363 — ONE call may omit it, and the set is asserted by EQUALITY so a
    // second one cannot slip in behind this exception.
    //
    // The named single-sided caption ("Opened Boca 68%") prints a lone number
    // on a draw-priced sport. `openingPercents` is a PAIR rounding — it exists
    // to stop two numbers summing to 101, and its home entry is rounded to
    // pair with an away number this branch refuses to print. Consulting it
    // here would reach for the complement by the back door. `formatProbability`
    // applies the identical rounding when `renderedPercent` is nil, so the
    // string a reader sees is unchanged; what changes is that no complement
    // was consulted to produce it. Same reasoning as the hero's draw arm.
    expect(callsMissingRenderedPercent(read(CARD))).toEqual([
      "formatProbability(opened.home)",
    ]);
  });

  it("the live strip takes the served pair, and takes both halves of it", () => {
    const src = swiftCode(read(CARD));
    expect(src).toMatch(/private var livePercents: \[Int\?\]/);
    expect(src).toMatch(/duelPercents\(/);
    // 🔴 SIDE-SPECIFIC ON PURPOSE. A bare `/servedAway:/` passes a call that hands
    // the HOME field to the away parameter — a silent transpose that still sums
    // to 100, so no arithmetic in this file could catch it. The pinned text IS
    // the check.
    expect(src).toMatch(/servedAway:[^\n]*awayRenderedPercent/);
    expect(src).toMatch(/servedHome:[^\n]*homeRenderedPercent/);
    expect(src).not.toMatch(/servedAway:[^\n]*homeRenderedPercent/);
    expect(src).not.toMatch(/servedHome:[^\n]*awayRenderedPercent/);
  });

  it("the opening line passes NO served values", () => {
    // The served pair describes `current_odds` and nothing else. Handing that
    // rounding to `opening_odds`' probabilities prints a mismatched pair that
    // still sums to 100 — the one error a sum guard cannot see.
    const src = swiftCode(read(CARD));
    expect(src).toMatch(/private var openingPercents: \[Int\?\]/);
    expect(src).toMatch(
      /openingPercents: \[Int\?\] \{\s*\n\s*renderedDuelPercents\(/,
    );
    // `openingPercents` must not reach for the served fields at all.
    const body = src.slice(src.indexOf("private var openingPercents"));
    const end = body.indexOf("\n    }");
    expect(body.slice(0, end)).not.toContain("RenderedPercent");
  });

  it("each side reads its own index — away is [0], home is [1]", () => {
    // `duelPercents` and `renderedDuelPercents` both return `[away, home]`.
    // A transpose here prints each team the other's number, which sums to 100
    // and is therefore invisible to every sum assertion in this file.
    const src = swiftCode(read(CARD));
    expect(src).toMatch(/side == \.home \? livePercents\[1\] : livePercents\[0\]/);
    expect(src).toMatch(/side == \.home \? openingPercents\[1\] : openingPercents\[0\]/);
    expect(src).not.toMatch(/side == \.home \? livePercents\[0\]/);
    expect(src).not.toMatch(/side == \.home \? openingPercents\[0\]/);
  });

  it("the card keeps no second, private opinion about the pair", () => {
    // The `Opened` line used to derive its own `openPcts` beside the two bare
    // calls. Three derivations of one rule on one card is how they disagreed.
    const src = swiftCode(read(CARD));
    expect(src).not.toContain("openPcts");
    expect(src.match(/renderedDuelPercents\(/g) ?? []).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// 2. The arithmetic, re-run. The scan proves the card ASKS the helper; this
//    proves the answer is 100 on the values that produced the screenshots.
// ---------------------------------------------------------------------------

describe("#3049 — the half-percent grid sums to 100", () => {
  /** The three live US Open cards from the filing, plus the exact-.5 boundary set. */
  const CASES: Array<[string, number, number]> = [
    ["Sabalenka / Rakhimova", 0.055, 0.945],
    ["Kostyuk / Alexandrova", 0.245, 0.755],
    ["Cirstea / Paolini", 0.605, 0.395],
    ["dead heat on the boundary", 0.505, 0.495],
    ["the mirror of the first", 0.945, 0.055],
  ];

  it.each(CASES)("%s sums to 100", (_label, away, home) => {
    const [awayPct, homePct] = renderedDuelPercents(away, home);
    expect(awayPct).not.toBeNull();
    expect(homePct).not.toBeNull();
    expect((awayPct as number) + (homePct as number)).toBe(100);
  });

  it("the per-side rounding this ship deleted really did print 101", () => {
    // The counterfactual, so the suite states what it is defending against
    // rather than only that the current answer is nice. `Math.round` is the
    // half-up rule all three runtimes use.
    const perSide = (p: number) => Math.round(p * 1000 / 10);
    expect(perSide(0.055) + perSide(0.945)).toBe(101);
    expect(perSide(0.245) + perSide(0.755)).toBe(101);
    expect(perSide(0.605) + perSide(0.395)).toBe(101);
  });

  it("the favourite keeps its own number and the derived point lands on the underdog", () => {
    // Always-away-first would move the favourite half the time. On 0.055/0.945
    // the favourite's own correct value is 95 and it must survive untouched.
    const [awayPct, homePct] = renderedDuelPercents(0.055, 0.945);
    expect(homePct).toBe(95);
    expect(awayPct).toBe(5);
  });

  it("a served pair is used verbatim, and is what the card asks for first", () => {
    // `duelPercents` returns the served pair unchanged when BOTH halves are
    // present; the card's `livePercents` is the call that asks for it. The Swift
    // arm's both-or-neither rule is pinned in duelPercentServedPair.test.ts; what
    // matters here is that the card routes through it rather than rounding.
    const src = swiftCode(read(SHARED));
    expect(src).toMatch(
      /if let servedAway, let servedHome \{\s*\n\s*return \[servedAway, servedHome\]/,
    );
  });
});
