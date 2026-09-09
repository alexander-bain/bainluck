// #4466 — A CREST BADGE IS NEVER "GER".
//
// What Alex saw, production `/discover` at 390px, 2026-09-09 12:40 PT: the live
// UCL card "ŠK Slovan Bratislava @ Paris Saint Germain" drew PSG's crest tile
// as **`GER`**. An independent LOOK an hour later (ux/1160, 13:39 PT) shot the
// same fixture drawing **`SAI`**.
//
// Both are the same bug and the pair is the point: the STORED NAME is an input.
//
//     "Paris Saint Germain"   -> last word "Germain"       -> "GER"
//     "Paris Saint-Germain"   -> last word "Saint-Germain" -> "SAI"
//
// So this cannot be validated against one spelling per club, and a fix that
// happens to produce a nice answer for one row has not been tested.
//
// ── WHY teamCrestInitials AND NOT A BETTER LAST-WORD RULE ───────────────────
//
// `teamShortName` is correct for `<place> <nickname>` and is the right function
// for a NAME slot — "Los Angeles Lakers" -> "Lakers". It is wrong for a BADGE,
// where the job is a short distinctive stamp rather than a name, and where the
// club conventions `<place> <club-type>` and `<place> <place> <name>` dominate
// outside North America.
//
// Measured with the REAL helpers over 1,000 production fixtures from the
// trailing 24h where both sides are multi-word, counting fixtures on which the
// two badges come out IDENTICAL:
//
//     teamShortName().slice(0,3)   11   <- what shipped
//     teamCrestInitials (2 glyphs) 15   <- WORSE; Mets and Yankees both "NY"
//     teamCrestBadge    (3 glyphs)  2
//
// The middle row is why this ships `teamCrestBadge` and not the two-glyph
// helper #4466's body suggests: a first pass at this census approximated
// `teamShortName` in Python as a bare last-word rule and reported 48 vs 14,
// which inverted the answer. The Python proxy did not know about
// CLUB_TYPE_SUFFIXES, so it "collided" on pairs the real function already
// separates ("Cheltenham Town" is "CHE", not "TOW"). Re-measured through the
// actual TypeScript, two glyphs is a REGRESSION on collisions and three is a
// 5.5x improvement.
//
// Three glyphs also gives the abbreviations a fan uses — PSG, LAL, NYM, NYY.
// The accepted cost is that a two-word name only has two initials: "Ipswich
// Town" is "IT" (was "IPS") and "Real Madrid" is "RM" (was "MAD").
//
// ── THE THIRD CALL SITE, AND WHY THE SCAN STRIPS COMMENTS ───────────────────
//
// #4466's body names two sites (`discover/EventCard.tsx:171,176`). There is a
// third: `discover/kernels/DuelKernel.tsx`, where the expression sits behind a
// helper named `abbr` and so does not appear in a grep for the inline JSX form.
// Flagged by ux/1161.
//
// The scan below strips comments before matching. That is not tidiness — the
// fix I shipped documents itself with a comment that QUOTES the banned
// expression and names the replacement, so a raw substring scan would both fire
// on the fixed file and pass on a reverted one whose comment still mentioned
// the helper. A guard that reads its target's own prose is measuring the prose.

import { readFileSync } from "fs";
import { join } from "path";
import { teamCrestBadge, teamShortName } from "@/lib/teamShortName";

/** The two live spellings of one club, from the two independent LOOKs. */
const PSG_SPELLINGS = ["Paris Saint Germain", "Paris Saint-Germain"];

/** Every file that paints a crest tile inside `components/discover/`. */
const CREST_CALL_SITES = [
  { file: "components/discover/EventCard.tsx", crests: 2 },
  { file: "components/discover/kernels/DuelKernel.tsx", crests: 1 },
];

/**
 * The shipped-and-wrong expression, as a predicate over CODE.
 *
 * Tolerant of whitespace and of which argument is passed, because the point is
 * the shape `teamShortName(...).slice(...)` — a NAME helper truncated into a
 * BADGE — not the exact text of any one of the three sites.
 */
const LAST_WORD_BADGE = /teamShortName\s*\([^)]*\)\s*\.\s*slice\s*\(/;

function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

function readCode(file: string): string {
  return stripComments(readFileSync(join(process.cwd(), file), "utf8"));
}

describe("#4466 the badge derivation", () => {
  it.each(PSG_SPELLINGS)("%s does not paint GER or SAI", spelling => {
    const badge = teamCrestBadge(spelling);
    expect(badge).not.toBe("GER");
    expect(badge).not.toBe("SAI");
    // The discriminator: this is the value the reverted call site produces.
    expect(badge).not.toBe(teamShortName(spelling).slice(0, 3).toUpperCase());
  });

  it("gives one club the SAME badge under both stored spellings", () => {
    // The half a single-specimen fix passes and a reader still fails: one club
    // must not wear two different badges on two rows of the same page.
    const [a, b] = PSG_SPELLINGS.map(teamCrestBadge);
    expect(a).toBe(b);
    // And it is the club's real abbreviation, not an accident of agreement.
    expect(a).toBe("PSG");
  });

  it("leaves every TWO-part name exactly as it shipped", () => {
    // The fork, and the reason this is not `teamCrestInitials`. The last-word
    // rule is right for these and keeps its answer untouched — at two initials
    // they would have become "IT", "RM", "BC" and "AF".
    expect(teamCrestBadge("Ipswich Town")).toBe("IPS");
    expect(teamCrestBadge("Real Madrid")).toBe("MAD");
    expect(teamCrestBadge("Boston Celtics")).toBe("CEL");
    expect(teamCrestBadge("Altrincham FC")).toBe("ALT");
  });

  it("takes initials for a THREE-part name, where the last word is a fragment", () => {
    expect(teamCrestBadge("Los Angeles Lakers")).toBe("LAL");
    expect(teamCrestBadge("New York Mets")).toBe("NYM");
    // The accepted cost, pinned so it is a decision on the record rather than a
    // surprise the next reader has to litigate.
    expect(teamCrestBadge("Boston Red Sox")).toBe("BRS");
  });

  it("separates the same-city pairs two initials cannot", () => {
    // The measured regression that ruled OUT the two-glyph helper: both of
    // these are "NY" under `teamCrestInitials`.
    expect(teamCrestBadge("New York Mets")).not.toBe(
      teamCrestBadge("New York Yankees"),
    );
    expect(teamCrestBadge("New York Mets")).toBe("NYM");
  });

  it("does not reopen #3110's doubles decision", () => {
    // A pair is not a compound name, it is two names, and #3110 pinned this
    // tile at three letters of the first surname. An earlier draft of this fix
    // routed pairs through `teamCrestInitials` and turned "HUN" into "H/K",
    // which `doublesPairHero3110.test.tsx` caught. Left exactly as it shipped.
    expect(teamCrestBadge("Hunter / Krawczyk")).toBe(
      teamShortName("Hunter / Krawczyk").slice(0, 3).toUpperCase(),
    );
  });

  it("separates the two clubs the last-word rule made identical", () => {
    expect(teamCrestBadge("Altrincham FC")).not.toBe(
      teamCrestBadge("Hartlepool United FC"),
    );
    // Positive control, and it is a REAL fixture from the census rather than an
    // invented pair. "Cheltenham Town vs Crawley Town" was the pair I first
    // reached for and it does NOT collide — `teamShortName` already handles
    // "Town", which is exactly the mistake the Python proxy made. This one is
    // from the measured list.
    expect(teamShortName("Caen Handball").slice(0, 3).toUpperCase()).toBe(
      teamShortName("Fenix Toulouse Handball").slice(0, 3).toUpperCase(),
    );
    expect(teamCrestBadge("Caen Handball")).not.toBe(
      teamCrestBadge("Fenix Toulouse Handball"),
    );
  });
});

describe("#4466 every discover crest call site", () => {
  it.each(CREST_CALL_SITES)(
    "$file does not truncate a NAME into a badge",
    ({ file }) => {
      expect(readCode(file)).not.toMatch(LAST_WORD_BADGE);
    },
  );

  it.each(CREST_CALL_SITES)(
    "$file calls teamCrestBadge for each of its crest tiles",
    ({ file, crests }) => {
      // Stated positively as well as negatively. A ban-shaped guard cannot see
      // an OMISSION — deleting the badge, or replacing it with a bare `?`,
      // satisfies the rule above while leaving the reader worse off.
      const calls = readCode(file).match(/teamCrestBadge\s*\(/g) ?? [];
      expect(calls.length).toBeGreaterThanOrEqual(crests);
    },
  );

  it("the ban predicate actually fires on the expression that shipped", () => {
    // Positive control. Without this the scan passes on a file that no longer
    // contains the call at all, or on a typo'd regex, and reads as green.
    expect(
      "teamShortName(data.home_team).slice(0, 3).toUpperCase()",
    ).toMatch(LAST_WORD_BADGE);
    expect("return teamShortName(team).slice(0, 3).toUpperCase();").toMatch(
      LAST_WORD_BADGE,
    );
  });

  it("comment stripping does not hide real code", () => {
    // The stripper is load-bearing, so it gets its own control: it must remove
    // a commented occurrence and keep an identical uncommented one.
    expect(stripComments("// teamShortName(x).slice(0, 3)\n")).not.toMatch(
      LAST_WORD_BADGE,
    );
    expect(stripComments("const a = teamShortName(x).slice(0, 3);")).toMatch(
      LAST_WORD_BADGE,
    );
  });

  it("does not sweep in teamShortName's legitimate NAME uses", () => {
    // `RelatedFutures.tsx` and the settled-winner sentence in DuelKernel call
    // `teamShortName`/`teamShortNames` for a NAME, which is the function's
    // actual contract. The ban is on truncating one into a badge, not on the
    // helper, and this pins that distinction so a later sweep does not "fix"
    // them too (ux/1161 warned about exactly this).
    const kernel = readCode("components/discover/kernels/DuelKernel.tsx");
    expect(kernel).toMatch(/teamShortNames\s*\(/);
  });
});
