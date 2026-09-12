/**
 * #5510 — THE SCRIPT CALLED FERNANDO TATIS JR. "Jr."
 *
 * WHAT A READER GOT. Giants–Padres, post-final, "How the props landed"
 * (`/events/15309667`, ux/1206's notice-42 shop):
 *
 *     Jr.'s 1+ hits was marked 35% — and it hit.
 *         Fernando Tatis Jr.: 1+ hits          ← the subtitle, correct
 *
 * The subject is printed correctly one line below the sentence that gets it
 * wrong, which is what makes it read as a bug rather than as a data gap. The
 * same generator runs live, so before the final the page said *"Jr.'s 1+ hits
 * opened at 35% — it's 93% now."*
 *
 * CAUSE. `possessive()` took `parts[parts.length - 1]` as the surname. That is
 * right for `Jung Hoo Lee` and for `Xander Bogaerts`, and wrong for every
 * player carrying a generational suffix — **1,119 legs over 35 distinct
 * subjects** in the issue's 7-day production census.
 *
 * ═══ THIS SUITE IS HALF OF #5510, DELIBERATELY ═══
 *
 * The issue's other half is subjects that are not people — `Hits Allowed` →
 * `Allowed's`, `Bayer 04 Leverkusen Corners` → `Corners'` (834 legs, 115
 * subjects). It is NOT fixed here and is NOT asserted here, because the
 * discriminator must be structural and the payload does not carry one today:
 * `parsePlayerName`'s `identified` is `colonIdx >= 0 || stat !== ""` and is
 * therefore TRUE for `"…: Hits Allowed"`, and `player_headshot` is absent on
 * 119 of 143 rows on one Braves–Phillies page whose subjects include Kyle
 * Schwarber, Bo Bichette and Juan Soto — a coverage gap, not a person flag.
 * A word list is disqualified by `Dalton Rushing`, a real player. Row 9 below
 * PINS the unfixed behaviour so the next session can tell "still open" from
 * "regressed", and so a future word-list patch has something to break.
 *
 * ═══ BOTH DIRECTIONS, OR IT IS ONE-SIDED ═══
 *
 * Gotcha #43 and the issue's own guard clause. A mutant that simply drops the
 * last token unconditionally passes rows 1–4 and fails rows 5–7; a mutant that
 * changes nothing passes 5–7 and fails 1–4. Neither half is sufficient alone.
 *
 * RED-FIRST on the parent `137bf299`, measured rather than reasoned:
 * **6 failed, 6 passed of 12**. Reds: rows 1, 2, 3, 4 (the suffix population),
 * 8 (its three sentence shapes) and 10 (a padded suffix name). Greens: 5, 6, 7,
 * 9, 11, 12 — the prohibitions, which is the distribution a fix with a boundary
 * should have, and the six that survive the fix being reverted.
 *
 * Driven through the exported `divergenceSentence`, not through the private
 * helper: the defect is a sentence a reader saw, and the seam a guard should
 * hold is the one that produced it.
 */

import { divergenceSentence } from "@/lib/propDivergence";

/** The subject of the sentence, i.e. everything before the first space. */
function subject(sentence: string): string {
  return sentence.split(" ")[0];
}

/** The shape the specimen rendered in: settled, resolved, hit. */
function settledSentence(player: string, label: string): string {
  return divergenceSentence(player, label, 0.35, 0.93, true, 1);
}

describe("#5510 a generational suffix is not a surname", () => {
  it("1. the production specimen: Fernando Tatis Jr. is Tatis', not Jr.'s", () => {
    const s = settledSentence("Fernando Tatis Jr.", "Fernando Tatis Jr.: 1+ hits");
    expect(subject(s)).toBe("Tatis'");
    expect(s).toBe("Tatis' 1+ hits was marked 35% — and it hit.");
    expect(s).not.toContain("Jr.");
  });

  it("2. every suffix the census found, with and without the period", () => {
    const cases: Array<[string, string]> = [
      ["Vladimir Guerrero Jr.", "Guerrero's"],
      ["Vladimir Guerrero Jr", "Guerrero's"],
      ["Aaron Jones Sr.", "Jones'"],
      ["Aaron Jones Sr", "Jones'"],
      ["Cedric Mullins II", "Mullins'"],
      ["Robert Griffin III", "Griffin's"],
      ["Bud Dupree IV", "Dupree's"],
    ];
    for (const [player, expected] of cases) {
      expect(subject(settledSentence(player, `${player}: 1+ hits`))).toBe(expected);
    }
  });

  it("3. the suffix is matched case-insensitively", () => {
    expect(subject(settledSentence("Fernando Tatis JR.", "x: 1+ hits"))).toBe("Tatis'");
    expect(subject(settledSentence("Aaron Jones sr", "x: 1+ hits"))).toBe("Jones'");
  });

  it("4. stacked suffixes and a comma-joined one both reach the surname", () => {
    expect(subject(settledSentence("Ken Griffey Jr. III", "x: 1+ hits"))).toBe("Griffey's");
    // The comma belongs to the suffix that was just removed, never to the name.
    expect(subject(settledSentence("Fernando Tatis, Jr.", "x: 1+ hits"))).toBe("Tatis'");
  });

  // ── THE OTHER DIRECTION: NOTHING WITHOUT A SUFFIX MAY MOVE ──────────────

  it("5. 🔴 a plain surname is unchanged — including the trailing-s rule", () => {
    expect(subject(settledSentence("Jung Hoo Lee", "x: 1+ hits"))).toBe("Lee's");
    expect(subject(settledSentence("Xander Bogaerts", "x: 1+ hits"))).toBe("Bogaerts'");
    expect(subject(settledSentence("Janson Junk", "x: 1+ hits"))).toBe("Junk's");
    expect(subject(settledSentence("Shohei Ohtani", "x: 1+ hits"))).toBe("Ohtani's");
  });

  it("6. 🔴 a bare V is an initial, not a fifth generation", () => {
    // Possessivising the wrong token is the defect being fixed, so the
    // ambiguous case keeps today's answer rather than acquiring a new one.
    expect(subject(settledSentence("Ronald Acuna V", "x: 1+ hits"))).toBe("V's");
  });

  it("7. 🔴 a single-token subject is untouched, suffix or not", () => {
    expect(subject(settledSentence("Ohtani", "x: 1+ hits"))).toBe("Ohtani's");
    // Nothing but a suffix: there is nothing better to say, so today's answer
    // stands rather than the walk consuming the only token there is.
    expect(subject(settledSentence("Jr.", "x: 1+ hits"))).toBe("Jr.'s");
    // 🔴 THE BOUND, and it needs its own row because the single-token case
    // cannot see it. Relaxing the walk's floor from `i > 0` to `i >= 0` is an
    // EQUIVALENT mutant on "Jr." — the index falls off the array and the
    // `|| player` fallback hands back the same string — and survived until
    // this line existed. On a multi-token all-suffix name the two diverge: the
    // floor keeps the subject a SINGLE TOKEN ("Jr.'s"), the relaxed walk
    // possessivises the whole string ("Jr. Sr.'s"). The invariant worth
    // holding is not the answer, it is that the subject is always one token.
    expect(subject(settledSentence("Jr. Sr.", "x: 1+ hits"))).toBe("Jr.'s");
  });

  it("8. 🔴 the fix is in the subject only — every other clause is untouched", () => {
    expect(
      divergenceSentence("Fernando Tatis Jr.", "Fernando Tatis Jr.: 1+ hits", 0.35, 0.93, true, 0),
    ).toBe("Tatis' 1+ hits was marked 35% — and it missed.");
    expect(
      divergenceSentence("Fernando Tatis Jr.", "Fernando Tatis Jr.: 1+ hits", 0.35, 0.93, false),
    ).toBe("Tatis' 1+ hits opened at 35% — it's 93% now.");
    // Settled but UNRESOLVED keeps the opened-at clause and swaps only the
    // tail — #2011's branch, quoted here so the row cannot be read as the
    // resolved one with a different verb.
    expect(
      divergenceSentence("Fernando Tatis Jr.", "Fernando Tatis Jr.: 1+ hits", 0.35, 0.58, true),
    ).toBe("Tatis' 1+ hits opened at 35% — finished at 58%.");
  });

  it("9. 🔴 #5510's non-person half is STILL OPEN and this pins it", () => {
    // Not a regression and not an oversight — see this file's header. When the
    // structural person signal exists, this row is the one to flip, and until
    // then it is how a reader of the issue can tell the two halves apart.
    expect(subject(settledSentence("Hits Allowed", "Hits Allowed: 5+"))).toBe("Allowed's");
    expect(
      subject(settledSentence("Bayer 04 Leverkusen Corners", "x: 9+ corners")),
    ).toBe("Corners'");
    // And the half that IS fixed must not have reached into it: a non-person
    // subject carrying no suffix is byte-identical to today.
    expect(subject(settledSentence("Total Corners", "x: 9+ corners"))).toBe("Corners'");
  });

  it("10. 🔴 whitespace runs and padding do not change the subject", () => {
    expect(subject(settledSentence("  Fernando   Tatis   Jr.  ", "x: 1+ hits"))).toBe("Tatis'");
    expect(subject(settledSentence("  Jung Hoo Lee ", "x: 1+ hits"))).toBe("Lee's");
  });

  it("11. 🔴 a suffix in the MIDDLE of a name is not a suffix", () => {
    // The walk starts at the end and stops at the first non-suffix token, so a
    // `II` that is not trailing cannot pull the subject leftwards.
    expect(subject(settledSentence("Jr. Smith", "x: 1+ hits"))).toBe("Smith's");
  });

  it("12. 🔴 a suffix-like word that is a real surname is safe", () => {
    // `Ivey` and `Ivy` are not `IV`; the match is anchored and whole-token.
    expect(subject(settledSentence("Jaden Ivey", "x: 1+ hits"))).toBe("Ivey's");
    expect(subject(settledSentence("Tim Junior", "x: 1+ hits"))).toBe("Junior's");
  });
});
