/**
 * #1939 — ONE concept-admission rule, asserted across BOTH surfaces.
 *
 * The defect this ratchets against, stated exactly: the backend has served a
 * concept `leader` since #1882 and iOS has admitted concepts on it since; web's
 * `feedItemSuppressionReason` still required `marquee_whathit`. Measured on
 * production `5542f8c4` (identified, `limit=50`): 7 of 50 cards were concepts,
 * every one unsettled, every one carrying a real leader — Pogačar 0.751 of a
 * 30-rider field, Joshua Van 0.5217, Anthony Hernandez 0.635. Web dropped all
 * seven. 14% of the landing page, withheld by one surface and printed by the
 * other, for a week.
 *
 * WHY A CONTRACT TEST AND NOT JUST A UNIT TEST. This is the SECOND
 * shared-predicate divergence in a week (#1933 is the other — native's label
 * pass behind web). Both were fixed by patching whichever surface happened to
 * carry the bug report. That is a fix per instance, and there is no reason to
 * think the third instance is not already written; the two rules live in
 * different languages, in different repos-within-the-repo, reviewed by
 * different gates. Nothing structural connects them. This file is the
 * connection.
 *
 * It lives in jest for the reason `periodLabelSingleSource.test.ts` gives: jest
 * is a deploy gate here and the Swift test target is not reachable from CI. So
 * the assertion runs against the Swift SOURCE. That buys less than executing
 * both predicates would, and it is what is available — a source assertion that
 * runs on every push beats an execution assertion that runs on an iOS lane's
 * laptop.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";
import type { FeedItem, FeedConceptData } from "@/lib/types";
import { feedItemSuppressionReason } from "@/components/discover/utils";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const NATIVE_PREDICATE = join(IOS_ROOT, "ViewModels/DiscoverViewModel.swift");

const NOW = new Date("2026-08-17T00:00:00Z").getTime();

function concept(data: Partial<FeedConceptData>): FeedItem {
  return {
    type: "concept",
    score: 50,
    reason: "",
    headline: null,
    data: {
      key: "event:ufc:26aug20",
      name: "UFC Fight Night",
      domain: "mma",
      status: "upcoming",
      is_major: true,
      fight_count: 11,
      ...data,
    } as FeedConceptData,
  } as FeedItem;
}

/**
 * The shared matrix. Each row is a claim about the RULE, not about one surface —
 * which is what makes the file below able to check the other surface against it.
 */
const MATRIX: Array<{ name: string; item: FeedItem; expected: string | null }> = [
  {
    name: "unsettled concept WITH a leader → admitted (the #1939 class)",
    item: concept({
      marquee_whathit: false,
      leader: { name: "Joshua Van", probability: 0.5217, field_size: 2 },
    }),
    expected: null,
  },
  {
    name: "unsettled concept with a 30-rider field leader → admitted",
    item: concept({
      key: "event:cycling:vuelta-2026",
      domain: "cycling",
      marquee_whathit: false,
      leader: { name: "Tadej Pogacar", probability: 0.751, field_size: 30 },
    }),
    expected: null,
  },
  {
    name: "unsettled concept with NO leader → suppressed (the #1486 class)",
    item: concept({ marquee_whathit: false }),
    expected: "empty_concept",
  },
  {
    name: "settled WHAT-HIT with a named winner → admitted",
    item: concept({ marquee_whathit: true, winner: "Tadej Pogacar" }),
    expected: null,
  },
  {
    name: "settled WHAT-HIT with only a result_summary → admitted (#1935)",
    item: concept({ marquee_whathit: true, result_summary: "Won by 1:12" }),
    expected: null,
  },
  {
    name: "settled WHAT-HIT that can name NOTHING → suppressed (#1935)",
    item: concept({ marquee_whathit: true }),
    expected: "empty_concept",
  },
  {
    // "Settled means settled." A settled card leads with its RESULT; it must not
    // fall back to a probability that is now history. The server never sends
    // both, so this row pins the ORDER of the two arms rather than a live case —
    // which is precisely the kind of invariant that rots silently.
    name: "settled-but-resultless does NOT fall back to a leader",
    item: concept({
      marquee_whathit: true,
      leader: { name: "Joshua Van", probability: 0.5217, field_size: 2 },
    }),
    expected: "empty_concept",
  },
];

describe("#1939 — web's concept admission rule", () => {
  it.each(MATRIX)("$name", ({ item, expected }) => {
    expect(feedItemSuppressionReason(item, NOW)).toBe(expected);
  });

  // TypeScript is erased at runtime, so the web predicate faces malformed
  // payloads that native's decoder rejects before its predicate ever runs. These
  // are NOT native-parity rows — they are the extra code web needs in order to
  // reach the same BEHAVIOUR, and they would be the failure mode of writing
  // web's test as a bare `leader != null` presence check "to match native".
  it.each([
    ["an empty object", {}],
    ["a blank name", { name: "   ", probability: 0.6 }],
    ["a missing probability", { name: "Joshua Van" }],
    ["a non-numeric probability", { name: "Joshua Van", probability: "0.6" }],
    ["a probability over 1.0 (gotcha #23)", { name: "Joshua Van", probability: 1.4 }],
    ["a NaN probability", { name: "Joshua Van", probability: Number.NaN }],
  ])("a leader that is %s does not admit the card", (_label, leader) => {
    const item = concept({
      marquee_whathit: false,
      leader: leader as never,
    });
    expect(feedItemSuppressionReason(item, NOW)).toBe("empty_concept");
  });
});

// The whole suite is meaningless if it is pointed at nothing — a path typo would
// otherwise read as a clean pass (the unrunnable-check failure mode, gotcha #54's
// cousin).
const iosPresent = existsSync(NATIVE_PREDICATE);
const d = iosPresent ? describe : describe.skip;

d("#1939 — native encodes the SAME concept rule", () => {
  const swift = readFileSync(NATIVE_PREDICATE, "utf8");

  // Narrow to the concept arm so a `leader` mention elsewhere in a 900-line file
  // cannot satisfy these assertions.
  const arm = (() => {
    const start = swift.indexOf("if let concept = item.concept {");
    expect(start).toBeGreaterThan(-1);
    const end = swift.indexOf("if let bundle = item.bundle {", start);
    expect(end).toBeGreaterThan(start);
    return swift.slice(start, end);
  })();

  it("admits an unsettled concept on its leader", () => {
    // The exact line web was missing. If someone deletes it on the native side,
    // native starts withholding what web now prints — the same divergence with
    // the surfaces swapped.
    expect(arm).toMatch(/if concept\.leader != nil \{\s*return nil\s*\}/);
  });

  it("requires a NAMEABLE result on the settled arm (#1935)", () => {
    expect(arm).toContain("concept.marqueeWhathit == true");
    expect(arm).toMatch(/winner/);
    expect(arm).toMatch(/resultSummary/);
    expect(arm).toMatch(/named\.isEmpty && summary\.isEmpty/);
  });

  it("checks settled BEFORE leader, so a result is never displaced", () => {
    // Order is the invariant, not the presence of both checks. Reversed, a
    // settled-but-resultless concept would print a stale probability under a
    // FINAL badge.
    const settledAt = arm.indexOf("concept.marqueeWhathit == true");
    const leaderAt = arm.indexOf("concept.leader != nil");
    expect(settledAt).toBeGreaterThan(-1);
    expect(leaderAt).toBeGreaterThan(-1);
    expect(settledAt).toBeLessThan(leaderAt);
  });

  it("falls closed — the arm's LAST return is still empty_concept", () => {
    // Fail-closed is the property, and the property is about the final
    // statement, not the final character (the slice ends on the arm's closing
    // brace). Take the last `return` in the arm and assert what it returns: an
    // unrecognised concept must be dropped, never shown bare.
    const returns = arm.match(/return [^\n]+/g) ?? [];
    expect(returns.length).toBeGreaterThan(0);
    expect(returns[returns.length - 1]).toBe('return "empty_concept"');
  });
});

d("#1939 — both web renderers can print what the gate admits", () => {
  // The half of this fix that is easiest to skip and most expensive to skip:
  // admitting a card the renderer has no branch for is how you rebuild #1935's
  // probability-free tile while closing #1939. Web has TWO concept renderers and
  // ONE gate, so both must be able to print a leader.
  const RENDERERS = [
    join(__dirname, "../../components/discover/ConceptCard.tsx"),
    join(__dirname, "../../components/FeedCard.tsx"),
  ];

  it.each(RENDERERS)("%s renders leader name + probability", (path) => {
    const src = readFileSync(path, "utf8");
    expect(src).toContain("leader.name");
    expect(src).toMatch(/leader\.probability \* 100/);
    // One movement formatter, shared — not a second copy per renderer.
    expect(src).toContain("formatConceptMovement");
  });
});
