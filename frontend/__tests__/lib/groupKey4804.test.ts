/**
 * #4804 (D1 clause c) — Discover's client-side group key.
 *
 * The defect: `groupRelatedMarkets` keyed on "the colon subject, or else the
 * first three words", so two questions that merely opened the same way became
 * one card headed "2 markets". Measured live on `GET /api/feed?limit=100`
 * (2026-09-12 19:2xZ), the three-word arm formed two groups and one of them
 * merged a Swedish government question with a US Press Secretary question.
 *
 * These arms are a CLASS guard over the rule, not a fixture for those two
 * names: the first-three-words cases are asserted through a table of unrelated
 * pairs drawn from different domains, and the colon cases assert the arm that
 * must KEEP working. A guard that only asserted the defect would pass happily
 * if grouping were deleted outright.
 */

import {
  futuresGroupKey,
  MAX_GROUP_SUBJECT_LENGTH,
} from "@/lib/discover/groupKey";

/** The rule as it shipped before #4804, kept so the guard can prove it differed. */
function legacyKey(name: string): string {
  const colonIdx = name.indexOf(":");
  return colonIdx > 0 && colonIdx < 30
    ? name.slice(0, colonIdx).trim()
    : name.split(/\s+/).slice(0, 3).join(" ");
}

/** Two markets group iff they produce the same non-null key. */
function groupsTogether(a: string, b: string): boolean {
  const ka = futuresGroupKey(a);
  return ka !== null && ka === futuresGroupKey(b);
}

describe("#4804 futuresGroupKey — a shared opening is not a shared subject", () => {
  // Each pair opens with the same three words and asks about unrelated things.
  const UNRELATED_PAIRS: ReadonlyArray<readonly [string, string, string]> = [
    [
      "the live specimen: Sweden vs a US press appointment",
      "Who will be a part of the next government of Sweden?",
      "Who will be Trump's next Press Secretary?",
    ],
    [
      "a US House race vs a foreign legislature",
      "Which party will win the U.S. House?",
      "Which party will control the Bundestag in 2029?",
    ],
    [
      "an invasion vs a confirmation vote",
      "Will the U.S. invade Iran before 2027?",
      "Will the U.S. Senate confirm the nominee?",
    ],
    [
      "two different people, same stem",
      "Who will win the Nobel Peace Prize?",
      "Who will win the Best Actress Oscar?",
    ],
  ];

  it.each(UNRELATED_PAIRS)(
    "does not group %s",
    (_label, a, b) => {
      expect(groupsTogether(a, b)).toBe(false);
      expect(futuresGroupKey(a)).toBeNull();
      expect(futuresGroupKey(b)).toBeNull();
    }
  );

  it("is a REAL change: every unrelated pair above did group under the old rule", () => {
    // Without this arm the suite would still pass if `futuresGroupKey` had
    // always returned null for these — it proves the defect was live.
    for (const [, a, b] of UNRELATED_PAIRS) {
      expect(legacyKey(a)).toBe(legacyKey(b));
    }
  });
});

describe("#4804 futuresGroupKey — a stated colon subject still groups", () => {
  const SAME_SUBJECT: ReadonlyArray<readonly [string, string, string]> = [
    [
      "golf tournament markets",
      "Valero Texas Open: Winner",
      "Valero Texas Open: Top 10",
    ],
    [
      "subject is compared case-sensitively but whitespace-insensitively",
      "Valero Texas Open:Winner",
      "Valero Texas Open :  Top 10",
    ],
    ["a hardware family", "DDR5 16GB (2GX8): Q1", "DDR5 16GB (2GX8): Q2"],
  ];

  it.each(SAME_SUBJECT)("groups %s", (_label, a, b) => {
    expect(groupsTogether(a, b)).toBe(true);
  });

  it("keeps different colon subjects apart", () => {
    expect(
      groupsTogether("Valero Texas Open: Winner", "Sanderson Farms: Winner")
    ).toBe(false);
  });

  it("returns the subject itself, so the pill can show it verbatim", () => {
    expect(futuresGroupKey("Valero Texas Open: Winner")).toBe(
      "Valero Texas Open"
    );
  });
});

describe("#4804 futuresGroupKey — the boundary and the degenerate inputs", () => {
  it("refuses a colon that is not a subject: too long", () => {
    const longSubject = "a".repeat(MAX_GROUP_SUBJECT_LENGTH);
    expect(futuresGroupKey(`${longSubject}: tail`)).toBeNull();
  });

  it("accepts a subject one character inside the bound", () => {
    const subject = "a".repeat(MAX_GROUP_SUBJECT_LENGTH - 1);
    expect(futuresGroupKey(`${subject}: tail`)).toBe(subject);
  });

  it("refuses a leading colon (there is no subject before it)", () => {
    expect(futuresGroupKey(": Winner")).toBeNull();
  });

  it("refuses a name with no colon at all", () => {
    expect(futuresGroupKey("Brazil Presidential election winner?")).toBeNull();
  });

  it("survives empty, null and undefined names without grouping them", () => {
    expect(futuresGroupKey("")).toBeNull();
    expect(futuresGroupKey(null)).toBeNull();
    expect(futuresGroupKey(undefined)).toBeNull();
  });

  it("never groups two nameless markets together", () => {
    // The null return is what stops this. A fallback key of "" would have
    // folded every nameless market into one card.
    expect(groupsTogether("", "")).toBe(false);
  });
});
