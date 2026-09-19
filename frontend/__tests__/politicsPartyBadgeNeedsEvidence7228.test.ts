// #7228 — AN UNEVIDENCED PARTY PAINTS NO BADGE.
//
// On production 2026-09-19 (v4776) the headline card "2028 Democratic
// presidential nominee" badged four Democrats — Rahm Emanuel, James Talarico,
// Ro Khanna, Abdul El-Sayed — as `I`. The lie was in the payload: the server's
// `_detect_party()` fall-through *asserted* "I" on any name its 30-surname
// allowlist had not heard of. The server fix is
// `backend/tests/test_politics_candidate_party_is_evidenced_7228.py`; it now
// sends the contest's party where the race supplies one (`dem_primary` -> "D")
// and `""` where nothing does.
//
// THE HALF THIS FILE GUARDS is what `""` looks like. The row read
//
//     <span className={s.partyBadge} style={{ background: partyBg }}>{c.party}</span>
//
// with `partyBg = PARTY_COLOR[c.party] || PARTY_COLOR.I`, so an empty party
// still drew a grey `.partyBadge` pill — the Independent colour, the
// Independent shape, and no letter. That is the same false claim in a quieter
// voice, and it is exactly what the server stopped saying. So BOTH the badge
// class and the party colour are conditioned on `c.party`.
//
// WHY A SOURCE SCAN AND NOT A RENDER: `PresBarRace` is not exported and the
// page is a client component behind a data fetch; jest swaps the CSS Module for
// a proxy (`__tests__/helpers/cssModuleProxy.js`), so a rendered row can report
// neither the real class name nor a colour. The invariant is a property of the
// markup, so the markup is what is read — and the parser asserts it FOUND the
// cell before it asserts anything about it, because a source guard that
// silently matches nothing is worse than no guard.
//
// THE CELL MUST SURVIVE AS A CELL. `.barRaceRow` is a seven-track grid and
// #3704 counts the row's children by indentation: a cell wrapped in a `{cond ?
// (...) : (...)}` ternary stops being counted, the grid loses a track, and the
// percentage falls onto a second row on every phone. That is why the fix is
// conditional ATTRIBUTES on one span and not a conditional span — and why this
// file asserts the one-line shape that keeps #3704's parser whole.
//
//   npx jest --testPathPatterns=politicsPartyBadgeNeedsEvidence7228

import fs from "node:fs";
import path from "node:path";

const PAGE = fs.readFileSync(
  path.join(__dirname, "..", "app", "politics", "page.tsx"),
  "utf8",
);
const API_TYPES = fs.readFileSync(
  path.join(__dirname, "..", "lib", "api.ts"),
  "utf8",
);

/** The bar-race row's party cell, as one source line. */
function partyCellLine(): string {
  const lines = PAGE.split("\n").map((l) => l.trim());
  const hits = lines.filter(
    (l) => l.startsWith("<span") && l.includes("partyBadge"),
  );
  if (hits.length !== 1) {
    throw new Error(
      `#7228 guard expected exactly one \`.partyBadge\` span in ` +
        `app/politics/page.tsx, found ${hits.length}. If the cell moved or a ` +
        `second badge was added, re-point this guard — do not delete it.`,
    );
  }
  return hits[0];
}

describe("#7228 · the party cell the parser is reasoning about", () => {
  test("the badge cell exists and prints the party letter", () => {
    const cell = partyCellLine();
    expect(cell).toContain("{c.party}");
  });

  test("it is ONE line, so #3704's seven-track child count still sees it", () => {
    // A ternary-wrapped cell starts with `{`, not `<`, and #3704's parser drops
    // it — taking a grid track with it. Keep the condition in the attributes.
    const cell = partyCellLine();
    expect(cell.startsWith("<span")).toBe(true);
    expect(cell.endsWith("</span>")).toBe(true);
  });
});

describe("#7228 · an empty party is drawn as nothing", () => {
  test("the badge CLASS is conditional on there being a party", () => {
    const cell = partyCellLine();
    expect(cell).toMatch(/className=\{c\.party \? s\.partyBadge : undefined\}/);
    expect(cell).not.toMatch(/className=\{s\.partyBadge\}/);
  });

  test("the party COLOUR is conditional too — a grey pill is still a claim", () => {
    // `PARTY_COLOR[""] || PARTY_COLOR.I` is grey, the Independent colour. An
    // unconditional `style={{ background: partyBg }}` would paint the empty
    // cell Independent-grey and put the badge back in all but the letter.
    const cell = partyCellLine();
    expect(cell).toMatch(/style=\{c\.party \? \{ background: partyBg \} : undefined\}/);
    expect(cell).not.toMatch(/style=\{\{ background: partyBg \}\}/);
  });
});

describe("#7228 · the empty case is reachable, so the branch is not dead code", () => {
  test("PoliticsCandidate.party admits the unevidenced state", () => {
    const decl = API_TYPES.match(/party:\s*("R"[^;]*);/);
    if (!decl) {
      throw new Error(
        "#7228 guard cannot find PoliticsCandidate.party in lib/api.ts — " +
          "re-point this guard rather than deleting it.",
      );
    }
    // Narrowing this back to `"R" | "D" | "I"` would make the conditions above
    // unreachable by the type checker, and the next reader would 'simplify'
    // them away. The server can and does send "".
    expect(decl[1]).toContain('""');
  });
});
