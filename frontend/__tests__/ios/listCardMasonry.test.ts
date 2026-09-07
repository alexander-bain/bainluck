/**
 * #3709 — the `List`-backed iPad card grids use a masonry deal, not `LazyVGrid`.
 *
 * `LazyVGrid` lays out in ROWS and pads every cell to the tallest cell in that
 * row. It is a grid, not a masonry layout. Four files had this copied verbatim:
 *
 * ```swift
 * private var iPadGridColumns: [GridItem] {
 *     [GridItem(.adaptive(minimum: 340), spacing: 12)]
 * }
 * ```
 *
 * On iPhone `.adaptive(minimum: 340)` resolves to one column and nothing is
 * ever padded, which is why sixteen sessions of phone screenshots never showed
 * it — the same reason #3651 went unseen on Discover. On iPad the three feed
 * surfaces deal `[FeedItem]`, mixing the tall `EventCardView` with the short
 * futures strip, so the shorter card in a row carries the surplus as dead
 * space below it. Measured on `bainluck://category/tennis`, iPad Pro 11-inch:
 * right-column gap 50 px before, 30 px after, against a left column that did
 * not move (28 px both times).
 *
 * This is #3273's ratchet built the way #3273 taught: it DISCOVERS
 * re-implementations of the idiom instead of naming consumers, because an
 * allowlist cannot catch the file nobody thought to add. Comments are stripped
 * first — the fixed files legitimately quote the old expression in their doc
 * comments, and a raw substring scan would call that a reimplementation.
 *
 * `IOS_ROOT` is the WHOLE `ios/Bain Luck` tree, Widget and Watch targets
 * included. A ratchet scoped to the app target is how #1832 became #3273.
 *
 * It lives in jest because jest is a deploy gate here and the Swift test target
 * is not reachable from CI.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck");
const CANONICAL = join(IOS_ROOT, "Bain Luck/Utilities/DiscoverMasonry.swift");

/** Every surface converted, by #3709 and then #3723. Each uses the deal and holds no grid. */
const CONVERTED = [
  "Bain Luck/Views/FeedView.swift",
  "Bain Luck/Views/SportCategoryView.swift",
  "Bain Luck/Views/MyStuffView.swift",
  "Bain Luck/Views/SearchView.swift",
].map((p) => join(IOS_ROOT, p));

/**
 * Files allowed to keep the 340/12 adaptive grid, each with a stated reason —
 * so adding one is a decision rather than a silent widening.
 *
 * **Currently empty, and that is the finding.** #3709 put `SearchView` here
 * with the reason "both grids are homogeneous (one row builder each), so no
 * cell is ever padded to a differently-shaped neighbour". native/043 and
 * native/044 had each photographed Search full-width on iPad and seen no
 * ragged column, and native/045 wrote the excuse down here rather than leave
 * it as a silent omission — which is what made it cheap to check.
 *
 * It was wrong. ONE ROW BUILDER IS NOT ONE SHAPE: `searchFuturesRow` has a
 * `lineLimit(2)` title, a badge row that collapses when the market has neither
 * a category nor a source, and a conditional top-outcome row. Measured on
 * `bainluck://search?q=US%20Open` (#3723, `artifacts-native-046/`), the "US
 * Open Winner" card came out 291 px wide and 164 px tall against ~721 px and
 * 204 px for every other card in the same grid — 20 px of dead space above and
 * below it, and 40 % of the width it was given.
 *
 * So: an entry here needs a reason that survives a photograph, not one that
 * reads well. The mechanism is kept because a real exemption should be
 * possible; it is empty because there is not one.
 */
const KEEPS_THE_GRID = new Map<string, string>([]);

function swiftFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return swiftFiles(path);
    return entry.isFile() && entry.name.endsWith(".swift") ? [path] : [];
  });
}

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/** Whitespace-insensitive, so a reformat cannot smuggle the idiom back in. */
const LIST_CARD_GRID = /GridItem\(\s*\.adaptive\(\s*minimum:\s*340\s*\)\s*,\s*spacing:\s*12\s*\)/;

// A path typo would otherwise read as a clean pass — the unrunnable-check
// failure mode this whole file exists to stop.
const iosPresent = existsSync(CANONICAL);
const d = iosPresent ? describe : describe.skip;

d("iOS List-backed iPad card grids deal masonry columns", () => {
  const canonical = readFileSync(CANONICAL, "utf8");

  it("the canonical metrics exist and are the ones the LazyVGrid already used", () => {
    // Carried over unchanged is the whole claim that this fix changes layout
    // and not sizing. If either number moves, cards change width.
    expect(canonical).toMatch(/static let listCardMinimumWidth: CGFloat = 340/);
    expect(canonical).toMatch(/static let listCardSpacing: CGFloat = 12/);
    expect(canonical).toMatch(/static func listColumnCount\(availableWidth: CGFloat\) -> Int/);
  });

  it.each(CONVERTED)("%s deals columns instead of asking LazyVGrid for masonry", (file) => {
    const source = stripComments(readFileSync(file, "utf8"));

    // Uses the shared deal...
    expect(source).toContain("DiscoverMasonry.listColumnCount(availableWidth: gridWidth)");
    expect(source).toContain("DiscoverMasonry.columns(");
    // ...and holds no grid at all, so there is no row left to pad to.
    expect(source).not.toContain("LazyVGrid");
    // The per-file copy of the metrics is gone; one rule, one implementation.
    expect(source).not.toMatch(LIST_CARD_GRID);
  });

  it("no iOS file reintroduces the 340/12 adaptive card grid", () => {
    const offenders = swiftFiles(IOS_ROOT)
      .filter((file) => LIST_CARD_GRID.test(stripComments(readFileSync(file, "utf8"))))
      .filter((file) => !KEEPS_THE_GRID.has(file))
      .map((file) => file.slice(IOS_ROOT.length + 1));

    expect(offenders).toEqual([]);
  });

  it("a Search card fills its column instead of hugging its longest line", () => {
    // The half of #3723 the masonry deal does NOT fix, and the reason this is
    // asserted separately rather than folded into the test above: dealing the
    // cards into stacks removes the ROW padding, but a `VStack` still sizes a
    // child at its intrinsic width and centres it. "US Open Winner" was 291 px
    // of a ~721 px column with 261/269 px of empty page either side.
    //
    // The order matters and is the thing worth pinning: the frame sits INSIDE
    // the padding, so the card grows to the column. Padding outside a
    // `maxWidth: .infinity` frame would make it the column PLUS 24 px.
    const source = stripComments(
      readFileSync(join(IOS_ROOT, "Bain Luck/Views/SearchView.swift"), "utf8")
    );
    expect(source).toMatch(
      /\.padding\(12\)\s*\n\s*\.frame\(maxWidth: \.infinity, alignment: \.leading\)\s*\n\s*\.background\(Color\.cardBackgroundDark\)/
    );
  });

  it("no iOS view keeps a UIScreen-derived landscape flag that nothing reads", () => {
    // `@State private var landscapeColumns` was written by an
    // `updateLandscapeColumns()` off `onAppear` plus an orientation observer,
    // and read by NOTHING, in three separate files — MyStuffView (deleted by
    // #3709), FeedView and SearchView (both deleted by #3723). Its only real
    // effect was a `UIScreen.main.bounds` read on a layout path: gotcha #27,
    // the Stage Manager trap, which measures the SCREEN and not the window.
    //
    // Named-symbol ratchets are usually weaker than discovery, but this symbol
    // reached three files by copy-paste and a fourth copy would arrive the same
    // way. Column count comes from a `GeometryReader` now, which IS the window.
    const offenders = swiftFiles(IOS_ROOT)
      .filter((file) => /landscapeColumns/.test(stripComments(readFileSync(file, "utf8"))))
      .map((file) => file.slice(IOS_ROOT.length + 1));

    expect(offenders).toEqual([]);
  });

  it("every allowlisted file still exists and still has the grid it was excused for", () => {
    // An allowlist entry for a file that no longer matches is a stale excuse
    // that would silently cover the next reintroduction in that file.
    for (const [file, reason] of KEEPS_THE_GRID) {
      expect(existsSync(file)).toBe(true);
      expect(stripComments(readFileSync(file, "utf8"))).toMatch(LIST_CARD_GRID);
      expect(reason.length).toBeGreaterThan(30);
    }
  });
});
