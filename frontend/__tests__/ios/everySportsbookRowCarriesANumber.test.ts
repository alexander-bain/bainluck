/**
 * #4406 — a row under "Individual sportsbooks" is a name AND a number, or it is
 * not a row.
 *
 * `bainluck://events/15307197` (Angels 6 – Sox 1), SE 375pt at accessibility-large:
 *
 *     INDIVIDUAL SPORTSBOOKS
 *     Bally Bet
 *     BetAnySports   ▬▬▬▬  43%  57%
 *     BetMGM         ▬▬▬▬ >99%  <1%
 *     BetOnline      ▬▬▬▬  43%  57%
 *     betPARX
 *     BetRivers
 *     BetUS          ▬▬▬▬  43%  57%
 *
 * Three brands in a row with nothing beside them. The client was drawing what it
 * was sent faithfully — `GET /api/events/15307197` carried eighteen books with
 * eleven `null` on both sides — and what it was sent was mostly nothing. Measured
 * across eleven games the same afternoon: 45 of 180 rows empty, 2 of 18 on a live
 * game and 13 of 18 on a completed one, so this is a book that did not quote the
 * game, not a settled-game artifact and not a decode fault.
 *
 * ═══ WHY A SOURCE SCAN AND NOT (ONLY) AN XCTEST ═══
 *
 * CI COMPILES NO SWIFT (#4302). `EventBookmakerNamesTests` proves the rows and
 * runs on a laptop; nothing in it stands between a regression and production.
 *
 * ═══ THE PREDICATE IS AN OMISSION, WHICH IS WHY IT IS SHAPED LIKE THIS ═══
 *
 * 🔴 #4478's lesson, from #2279's guard missing #3049: A BAN CANNOT SEE AN
 * OMISSION. The defect here writes nothing wrong — no bad call, no wrong helper,
 * no forbidden literal to grep for. A number is simply absent, and every
 * ban-shaped predicate passes a screen full of bare names.
 *
 * So all four predicates below are EXISTENCE claims about the tree, and the
 * load-bearing one is a TYPE: `NamedBookmakerRow.probabilities` is not optional.
 * That is what makes the empty row unrepresentable rather than merely unwritten —
 * the compiler refuses it, and this file's job is only to prove the type has not
 * been loosened back. A future author cannot reintroduce the state without first
 * making this file red.
 *
 * ═══ WHAT THIS FILE DOES NOT CLAIM ═══
 *
 * That the section reads well, or that seven rows is the right cap. It cannot see
 * a glyph. The frames are on #4406's PR.
 */

import { readFileSync } from "fs";
import { join } from "path";

const VIEW = join(
  __dirname,
  "../../../ios/Bain Luck/Bain Luck/Views/EventDetailView.swift",
);

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/**
 * The body of the first Swift block whose header matches, by BRACE DEPTH.
 *
 * 🔴 Not a slice to the next `}`. #4117 lost a session to the paren-depth form of
 * this trap: every one of these blocks contains nested braces (a closure, a
 * `switch`, a trailing `ForEach`), so a first-`}` read returns a fragment that
 * ends mid-declaration — and a predicate over a fragment is a predicate that
 * passes because it cannot see the code it is judging.
 */
function swiftBlock(source: string, header: RegExp): string {
  const match = header.exec(source);
  if (!match) return "";
  const open = source.indexOf("{", match.index);
  if (open < 0) return "";
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(open + 1, i);
    }
  }
  return "";
}

const ROW_STRUCT = /struct\s+NamedBookmakerRow\b[^{]*/;
const FACTORY = /static\s+func\s+namedBookmakerRows\s*\(/;
const ROW_VIEW = /private\s+func\s+sourceProbabilityRow\s*\(/;

/** The declared type of `NamedBookmakerRow.probabilities`, whitespace-collapsed. */
function rowPairType(source: string): string | null {
  const body = swiftBlock(source, ROW_STRUCT);
  const declaration = /let\s+probabilities\s*:\s*([^\n]+)/.exec(body);
  return declaration ? declaration[1].trim().replace(/\s+/g, " ") : null;
}

/**
 * The `probabilities:` parameter of the row view, as declared.
 *
 * 🔴 The parameter LIST is read by paren depth, and the TYPE is matched as a
 * balanced tuple — both for the same #4117 reason as `swiftBlock`. The type here
 * is `(away: Double, home: Double)`, so a slice to the first `)` ends inside it
 * and a `[^\n,]+` capture stops at the comma inside it. Either shortcut returns
 * `"(away: Double"` for the fixed tree AND for the broken one, which is a
 * predicate that can no longer tell them apart.
 */
function rowViewPairParameter(source: string): string | null {
  const match = ROW_VIEW.exec(source);
  if (!match) return null;
  const open = source.indexOf("(", match.index);
  let depth = 0;
  let close = -1;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === "(") depth += 1;
    else if (source[i] === ")") {
      depth -= 1;
      if (depth === 0) {
        close = i;
        break;
      }
    }
  }
  if (close < 0) return null;
  const parameters = source.slice(open + 1, close);
  const declaration = /probabilities\s*:\s*(\([^()]*\)\??)/.exec(parameters);
  return declaration ? declaration[1].trim().replace(/\s+/g, " ") : null;
}

describe("#4406 — every sportsbook row carries a number", () => {
  const source = stripComments(readFileSync(VIEW, "utf8"));

  it("holds the pair as a value, not an optional, so an empty row cannot be built", () => {
    const type = rowPairType(source);
    expect(type).not.toBeNull();
    expect(type).toBe("(away: Double, home: Double)");
  });

  it("decides the row EXISTS on the price, in the factory the view reads", () => {
    const body = swiftBlock(source, FACTORY);
    expect(body).not.toBe("");
    // The binding form specifically: an unbound call would satisfy a substring
    // check while discarding the value the row is built from.
    expect(body).toMatch(/let\s+probabilities\s*=\s*bookmakerProbabilities\(/);
  });

  it("applies the price filter BEFORE the cap, so no empty row holds a slot", () => {
    const body = swiftBlock(source, FACTORY);
    const filter = body.search(/bookmakerProbabilities\(/);
    const cap = body.search(/\.prefix\(/);
    expect(filter).toBeGreaterThanOrEqual(0);
    expect(cap).toBeGreaterThanOrEqual(0);
    // Cap-first and filter-first agree on every payload of ten or fewer, so this
    // ordering is invisible to any fixture the size of a normal game. On the
    // specimen it is worth three real prices: LowVig, MyBookie and Rebet sit at
    // positions 14, 15 and 16 behind six empty rows.
    expect(filter).toBeLessThan(cap);
  });

  it("takes a pair the row view cannot decline to draw", () => {
    expect(rowViewPairParameter(source)).toBe("(away: Double, home: Double)");
    const body = swiftBlock(source, ROW_VIEW);
    // The `if let probabilities` this function used to hold WAS the bare-name
    // state: label drawn, bar and numbers skipped. With a non-optional parameter
    // it no longer compiles, and this is the assertion that says why it is gone.
    expect(body).not.toMatch(/if\s+let\s+probabilities\b/);
  });
});

/**
 * The capability section: the predicates are fed the code as it SHIPPED, and each
 * must report it broken.
 *
 * A guard that has only ever seen the fixed tree is a guard that has never been
 * shown to fail. These four specimens are the four ways back to the photographed
 * screen, and the fourth — cap before filter — is the one that still draws a
 * clean-looking table, just a shorter one, and would pass a reviewer's eye.
 */
describe("#4406 — the guard discriminates", () => {
  const optionalPair = `
    struct NamedBookmakerRow: Identifiable {
        let id: String
        let label: String
        let probabilities: (away: Double, home: Double)?
    }`;

  const unfilteredFactory = `
    static func namedBookmakerRows(
        _ bookmakers: [BookmakerOdds], limit: Int = 10
    ) -> [NamedBookmakerRow] {
        bookmakers
            .compactMap { bm -> NamedBookmakerRow? in
                guard let key = bm.bookmaker,
                      let label = SourceLabels.sportsbookName(for: key)
                else { return nil }
                return NamedBookmakerRow(
                    id: key, label: label, probabilities: bookmakerProbabilities(bm))
            }
            .prefix(limit)
            .map { $0 }
    }`;

  const cappedBeforeFiltering = `
    static func namedBookmakerRows(
        _ bookmakers: [BookmakerOdds], limit: Int = 10
    ) -> [NamedBookmakerRow] {
        bookmakers
            .prefix(limit)
            .compactMap { bm -> NamedBookmakerRow? in
                guard let key = bm.bookmaker,
                      let label = SourceLabels.sportsbookName(for: key),
                      let probabilities = bookmakerProbabilities(bm)
                else { return nil }
                return NamedBookmakerRow(id: key, label: label, probabilities: probabilities)
            }
            .map { $0 }
    }`;

  const skippingRowView = `
    private func sourceProbabilityRow(
        label: String,
        font: Font,
        probabilities: (away: Double, home: Double)?,
        colors: (away: Color, home: Color)
    ) -> some View {
        Group {
            HStack {
                labelText
                if let probabilities {
                    probabilityBarAndNumbers(probabilities, colors: colors)
                }
            }
        }
    }`;

  it("sees an optional pair on the row", () => {
    expect(rowPairType(optionalPair)).toBe("(away: Double, home: Double)?");
  });

  it("sees a factory that builds the row without asking for a price", () => {
    const body = swiftBlock(unfilteredFactory, FACTORY);
    expect(body).not.toBe("");
    expect(body).not.toMatch(/let\s+probabilities\s*=\s*bookmakerProbabilities\(/);
  });

  it("sees the cap applied before the filter", () => {
    const body = swiftBlock(cappedBeforeFiltering, FACTORY);
    expect(body).not.toBe("");
    // Filter-first is the only difference between this specimen and the shipped
    // tree, and both draw a table of named rows carrying numbers.
    expect(body.search(/bookmakerProbabilities\(/)).toBeGreaterThan(
      body.search(/\.prefix\(/),
    );
  });

  it("sees a row view that can decline to draw the numbers", () => {
    expect(rowViewPairParameter(skippingRowView)).toBe("(away: Double, home: Double)?");
    expect(swiftBlock(skippingRowView, ROW_VIEW)).toMatch(/if\s+let\s+probabilities\b/);
  });

  it("reads nested braces to the end of the block rather than to the first `}`", () => {
    // The extractor's own trap, pinned: `skippingRowView` closes an `if`, an
    // `HStack` and a `Group` before its own brace. A first-`}` read returns the
    // fragment above `if let`, which is exactly the text the predicate is looking
    // for — the guard would pass the broken specimen while examining nothing.
    const body = swiftBlock(skippingRowView, ROW_VIEW);
    expect(body).toMatch(/probabilityBarAndNumbers/);
    expect(body.split("}").length).toBeGreaterThan(3);
  });
});
