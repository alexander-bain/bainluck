// TWO TILES, TWO QUESTIONS, ONE STRING — #2788.
//
// The specimen is production, not invented: `bainluck.com/events/15301243`
// (Wu Yibing vs Carlos Alcaraz, US Open), Bigger Picture -> OTHER (3), read on
// `842e6167` / v4020 at 2026-09-03 00:53 PT. The three outcome names below are
// verbatim from `GET /api/events/15301243/related-futures` at that head; the
// first two rendered character-for-character identically as `Will Carlos Al…`,
// side by side, at 79% and 55%.
//
// BOTH DIRECTIONS PER GOTCHA #43. Every "it shortened" case has a sibling
// asserting an ordinary group is returned UNTOUCHED. Without them a function
// that trimmed everything to its last word would pass the whole first half and
// wreck every player-prop tile in the product.

import {
  DEFAULT_VISIBLE_CHARS,
  disambiguateLabels,
} from "@/lib/labelDisambiguation";

// Verbatim from the production payload.
const QUARTERS =
  "Will Carlos Alcaraz advance to the Quarterfinals in Men's Singles at the 2026 US Open?";
const SEMIS =
  "Will Carlos Alcaraz advance to the Semifinals in Men's Singles at the 2026 US Open?";
const FRAGMENT = "the 2026 US Open? Win";

/** What the tile actually shows: the visible window before the ellipsis. */
function asRendered(label: string): string {
  return label.slice(0, DEFAULT_VISIBLE_CHARS);
}

describe("the production specimen", () => {
  it("no longer renders two questions as one string", () => {
    // THE bug, stated as the user saw it. This is the whole point of the
    // function, and it is asserted on the TRUNCATED forms rather than the full
    // ones — the full strings always differed, which is exactly why this
    // shipped green.
    const [a, b] = disambiguateLabels([QUARTERS, SEMIS]);
    expect(asRendered(a)).not.toBe(asRendered(b));
  });

  it("keeps the distinguishing clause and drops the shared one", () => {
    expect(disambiguateLabels([QUARTERS, SEMIS])).toEqual([
      "Quarterfinals in Men's Singles at the 2026 US Open?",
      "Semifinals in Men's Singles at the 2026 US Open?",
    ]);
  });

  it("leaves the third tile alone, because it shares nothing", () => {
    // The group is three tiles; only two of them collided. A row that is
    // already distinct must come back exactly as it was.
    const [, , third] = disambiguateLabels([QUARTERS, SEMIS, FRAGMENT]);
    expect(third).toBe(FRAGMENT);
  });

  it("still separates the two questions inside the full three-tile group", () => {
    const [a, b] = disambiguateLabels([QUARTERS, SEMIS, FRAGMENT]);
    expect(asRendered(a)).not.toBe(asRendered(b));
  });

  it("cuts on a word boundary, never mid-word", () => {
    // A fragment is not a shorter label — cutting mid-word is what produced
    // "Will Carlos Al…" in the first place.
    for (const label of disambiguateLabels([QUARTERS, SEMIS])) {
      expect(QUARTERS.includes(label) || SEMIS.includes(label)).toBe(true);
      expect(label).toMatch(/^\S/);
    }
  });
});

describe("what it must NOT touch", () => {
  it("returns a group of ordinary player names unchanged", () => {
    // The regression that matters: these are what the tile normally holds.
    const players = ["Derrick White", "Jaylen Brown", "Jayson Tatum"];
    expect(disambiguateLabels(players)).toEqual(players);
  });

  it("keeps a first name two players share", () => {
    // One shared word is 8 characters — well inside the visible window, so the
    // two tiles are already distinguishable and nothing is gained by trimming.
    // A word-count gate would have eaten "Derrick" here.
    const players = ["Derrick White", "Derrick Whiteman"];
    expect(disambiguateLabels(players)).toEqual(players);
  });

  it("DOES trim two long names that fill the window identically", () => {
    // The other side of the same rule: 22 shared characters means both tiles
    // print "Juan Carlos Ro…" and the reader learns nothing.
    expect(
      disambiguateLabels([
        "Juan Carlos Rodriguez Garcia",
        "Juan Carlos Rodriguez Lopez",
      ]),
    ).toEqual(["Garcia", "Lopez"]);
  });

  it("returns a single label unchanged", () => {
    expect(disambiguateLabels([QUARTERS])).toEqual([QUARTERS]);
  });

  it("returns an empty group unchanged", () => {
    expect(disambiguateLabels([])).toEqual([]);
  });

  it("leaves two IDENTICAL labels identical", () => {
    // Same text twice is a dedup problem, not a truncation one. Shortening them
    // to nothing would hide it.
    expect(disambiguateLabels([QUARTERS, QUARTERS])).toEqual([
      QUARTERS,
      QUARTERS,
    ]);
  });
});

describe("the invariant: it never creates a NEW collision", () => {
  it("bails out rather than colliding a remainder with a short sibling", () => {
    // "A B C Xylophone" / "A B C Yesterday" / "Xylophone": stripping the first
    // two would make the first equal to the third. The whole group is returned
    // untouched instead — worse-but-readable beats a new instance of the exact
    // bug being fixed.
    const labels = [
      "Alpha Bravo Charlie Xylophone",
      "Alpha Bravo Charlie Yesterday",
      "Xylophone",
    ];
    expect(disambiguateLabels(labels)).toEqual(labels);
  });

  it("never reduces how many distinct strings the group holds", () => {
    // The property, asserted over every case above at once.
    const groups = [
      [QUARTERS, SEMIS, FRAGMENT],
      ["Derrick White", "Derrick Whiteman"],
      ["Juan Carlos Rodriguez Garcia", "Juan Carlos Rodriguez Lopez"],
      ["Alpha Bravo Charlie Xylophone", "Alpha Bravo Charlie Yesterday", "Xylophone"],
      [QUARTERS, QUARTERS],
    ];
    for (const group of groups) {
      expect(new Set(disambiguateLabels(group)).size).toBe(new Set(group).size);
    }
  });

  it("returns exactly as many labels as it was given, in order", () => {
    const group = [QUARTERS, SEMIS, FRAGMENT];
    const out = disambiguateLabels(group);
    expect(out).toHaveLength(3);
    // Order is positional — the caller indexes tiles by it.
    expect(SEMIS.endsWith(out[1])).toBe(true);
  });
});
