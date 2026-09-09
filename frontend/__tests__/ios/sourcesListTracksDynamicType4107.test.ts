/**
 * #4107 — the event page's Sources list sizes its label column against measured
 * ink, not a literal.
 *
 * Alex read `Sportsbooks (…` on the Angels–Red Sox page. The issue blamed the
 * count growing from `(10)` to `(14)`, and the comment on the literal said the
 * column had already been widened 90 → 118 for that reason.
 *
 * MEASURED, THAT WAS WRONG. At default type size `Sportsbooks (14)` is 99.9pt in
 * a 118pt column. What truncates is the same label at a LARGER text size: with
 * the row's `.minimumScaleFactor(0.85)` the effective capacity was 138.8pt, so
 * xxLarge (128.2) fit by shrinking every label, xxxLarge (142.1) cut, and
 * accessibility1 (169.2) cut badly — taking `Bain Luck Model` with it. The column
 * had never tracked Dynamic Type at all; 90 and 118 were each correct for exactly
 * one text size.
 *
 * ═══ WHY A SOURCE SCAN AND NOT (ONLY) AN XCTEST ═══
 *
 * CI COMPILES NO SWIFT. `EventSourceLabelColumnTests` proves the width MODEL and
 * runs on a laptop; nothing in it can see whether the VIEW asks the model for a
 * width or goes back to writing one down. That is precisely how this defect
 * survived two rounds — the literal was raised rather than replaced, and the
 * comment above it explained the raise, which made it look considered.
 *
 * So this file asserts the WIRING, scoped to the one function that draws the row.
 *
 * ═══ WHAT THIS FILE DOES NOT CLAIM ═══
 *
 * That the list reads well at any text size. It cannot read a glyph, and a
 * rendered-width claim is exactly the kind this repo has measured wrong before
 * (`CalibrationSourceTableGeometry`: an arithmetic fit model was off by ~21pt in
 * the safe-looking direction). The 375pt default-size and accessibility frames on
 * #4107's PR carry that, and they are re-owed by whoever changes this row.
 */

import { readFileSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const EVENT_DETAIL = join(IOS_ROOT, "Views/EventDetailView.swift");
const GEOMETRY = join(IOS_ROOT, "Utilities/EventSourceLabelColumn.swift");

/**
 * The body of a Swift function, by brace balance from its signature.
 *
 * Scoped to the FUNCTION and not the file on purpose: `EventDetailView.swift` is
 * ~1,100 lines and draws several unrelated tables, at least one of which
 * legitimately uses a fixed 90pt column. A file-wide ban would fail on a
 * neighbour and a file-wide "contains" would pass on one.
 */
function functionBody(source: string, signature: string): string {
  const start = source.indexOf(signature);
  if (start === -1) throw new Error(`signature not found: ${signature}`);
  const open = source.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < source.length; i++) {
    if (source[i] === "{") depth++;
    else if (source[i] === "}") {
      depth--;
      if (depth === 0) return source.slice(open, i + 1);
    }
  }
  throw new Error(`unbalanced braces after: ${signature}`);
}

/**
 * Comments out, so the bans below are about CODE.
 *
 * Learned the hard way on this very file: the first run went red because the
 * comment explaining *why* `.minimumScaleFactor` was removed contains the word
 * `minimumScaleFactor`. A guard that a correct fix cannot satisfy without also
 * deleting its own rationale is a guard that will be weakened by the next person
 * rather than obeyed.
 */
function withoutComments(swift: string): string {
  return swift.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
}

const eventDetail = readFileSync(EVENT_DETAIL, "utf8");
const sourceContent = withoutComments(
  functionBody(
    eventDetail,
    "private func sourceContent(_ event: EventDetail, entries: [WinProbSourceCatalog.Entry])",
  ),
);

/**
 * ═══ #4233 MOVED THE ROW OUT OF BOTH LISTS, ON PURPOSE ═══
 *
 * The `describe.each` below used to hold `sourceContent` and `bookmakerContent`
 * to the same drawing predicates, because "a guard scoped to one of two
 * identical call sites is a guard on one call site" — the lesson #4107 learned
 * when its own fix reached one of the two.
 *
 * #4233 removed the duplication instead of guarding it: there is now ONE row
 * builder and both lists call it, so the half-fixed row is not a defect this
 * file has to catch — it is a shape the code can no longer take. That is
 * strictly better than the guard, and it is why these slices moved.
 *
 * What replaces the old assertions, and is the thing worth pinning now: the two
 * `*Content` functions still MEASURE independently (different faces, different
 * value sets) and must not go back to DRAWING independently.
 */
const sourceRow = withoutComments(
  functionBody(eventDetail, "private func sourceProbabilityRow("),
);
const barAndNumbers = withoutComments(
  functionBody(eventDetail, "private func probabilityBarAndNumbers("),
);

describe("#4233 there is exactly one row builder and both lists use it", () => {
  it("sliced the shared row", () => {
    expect(sourceRow.length).toBeGreaterThan(400);
    expect(sourceRow).toContain("columns.layout");
    expect(sourceRow).toContain("probabilityBarAndNumbers(");
    expect(barAndNumbers).toContain("ProbabilityBar(");
    expect(barAndNumbers).toContain("formatProbability(");
  });

  it("both lists delegate to it", () => {
    expect(sourceContent).toContain("sourceProbabilityRow(");
    expect(bookmakerContent).toContain("sourceProbabilityRow(");
  });

  /**
   * The regression that would undo the consolidation: a list that starts drawing
   * its own row again. That is how the two drifted the first time, and a copy
   * would be invisible to every predicate below, which now scans one slice.
   */
  it("neither list draws a row of its own any more", () => {
    for (const slice of [sourceContent, bookmakerContent]) {
      expect(slice).not.toContain("ProbabilityBar(");
      expect(slice).not.toContain("HStack(");
      expect(slice).not.toContain("lineLimit(");
    }
  });

  /**
   * The whole file draws exactly one of these. `EventDetailView` is ~1,100 lines
   * and this bar is its only probability bar; a second call would mean a row had
   * been forked back out.
   */
  it("the view has a single ProbabilityBar call site", () => {
    expect(withoutComments(eventDetail).match(/ProbabilityBar\(/g)).toHaveLength(1);
  });
});

describe("#4107 the Sources list label column", () => {
  /**
   * THE SLICE IS PROVEN FIRST. Every ban below is a `not.toContain`, and a
   * `not.toContain` on an empty string passes. If the signature ever drifts,
   * `functionBody` throws — but if it matched something tiny or wrong, the bans
   * would go quietly green. So: the slice must be the measuring function, and
   * must contain the landmarks only that function has.
   */
  it("slices the function that actually sizes the source rows", () => {
    expect(sourceContent.length).toBeGreaterThan(400);
    expect(sourceContent).toContain("entry.label");
    expect(sourceContent).toContain("formatProbability(");
    expect(sourceContent).toContain("EventSourceLabelColumn.columns(");
  });

  /**
   * The original literal by name. The shared block below bans ANY `.frame(width:
   * <digits>)` in either row; this one keeps 118 itself on the record, because
   * the failure mode this issue actually had was a literal being RAISED (90 → 118)
   * and the raise being explained in a comment, which made it look considered.
   */
  it("has not gone back to the 118pt literal", () => {
    expect(sourceContent).not.toContain("width: 118");
  });

  it("measures against the view's own text size, not the app's", () => {
    const geometry = readFileSync(GEOMETRY, "utf8");
    // `UIFont.preferredFont(forTextStyle:)` with no trait collection resolves
    // against the process's setting; that is how a column ends up narrower than
    // the string inside it.
    expect(geometry).toContain("compatibleWith: traits");
    expect(geometry).toContain("UIFont.systemFont(ofSize: base.pointSize, weight: uiWeight(weight))");
  });
});

/**
 * ═══ THE SECOND LIST, WHICH THE FIRST VERSION OF THIS FILE COULD NOT SEE ═══
 *
 * Everything above is scoped to `sourceContent`, and every assertion in it passed
 * while `bookmakerContent` — the individual-sportsbook rows drawn directly BELOW
 * those, inside the same disclosure, in the same visual list — still pinned a
 * hardcoded 90pt column with `lineLimit(1)`.
 *
 * Photographed at xxxLarge on a 375pt phone that shipped `Sportsbooks (19)` and
 * `Kalshi` reading in full with `betanysp…` and `betonline…` cut off underneath
 * them: a worse read than the original bug, because a half-fixed list looks
 * deliberate rather than broken.
 *
 * A guard scoped to one of two identical call sites is a guard on one call site.
 * So the predicate is SHARED and both slices are held to it.
 */
const bookmakerContent = withoutComments(
  functionBody(eventDetail, "private func bookmakerContent(_ event: EventDetail)"),
);
// #4284 — the book table's rows are built here now: named through `SourceLabels`,
// then capped. The width model and the `ForEach` both read what this returns.
const namedRows = withoutComments(
  functionBody(eventDetail, "static func namedBookmakerRows("),
);

describe.each([
  ["sourceContent", sourceContent],
  ["bookmakerContent", bookmakerContent],
])("#4107 %s sizes its label column against ink", (name, slice) => {
  it("sliced the right function", () => {
    expect(slice.length).toBeGreaterThan(400);
    expect(slice).toContain("formatProbability(");
    expect(slice).toContain("sourceProbabilityRow(");
  });

  it("asks the width model instead of writing a number down", () => {
    // #4208 — one call returns BOTH columns. It used to be `.width(`, which
    // sized the label alone and is why the numbers beside it were left on a
    // literal through the whole of #4107.
    expect(slice).toContain("EventSourceLabelColumn.columns(");
    expect(slice).toContain("typeSize: dynamicTypeSize");
  });

  it("has no hardcoded point width left in the row", () => {
    expect(slice).not.toMatch(/\.frame\(\s*width:\s*\d/);
  });

  it("does not reach for minimumScaleFactor as a backstop", () => {
    expect(slice).not.toContain("minimumScaleFactor");
  });

  /**
   * #4233 — the measurement each list makes is spent by the shared row, so the
   * `Columns` it computed has to be the one handed over. A list that measured
   * correctly and then passed a stale or default value would be sized against a
   * table that is not on screen: the #4107 bug with an extra hop in it.
   */
  it("spends its own measurement on the shared row", () => {
    expect(slice).toMatch(/sourceProbabilityRow\([\s\S]*?columns: columns\)/);
  });
});

/**
 * Everything the row itself must still do, now asserted once because there is
 * one row.
 */
describe("#4107/#4233 the shared row draws against the measurement", () => {
  it("has no hardcoded point width left in it", () => {
    for (const slice of [sourceRow, barAndNumbers]) {
      expect(slice).not.toMatch(/\.frame\(\s*width:\s*\d/);
    }
  });

  it("does not reach for minimumScaleFactor as a backstop", () => {
    expect(sourceRow).not.toContain("minimumScaleFactor");
  });

  /**
   * #4233 — the limit is READ FROM THE MODEL rather than written here.
   *
   * The model reflows the row exactly because the label would exceed this
   * number. A literal `lineLimit(2)` in the view would still be correct today
   * and would silently decouple the two the moment either moved — the view
   * clipping at a limit the model was not reasoning about is the same class of
   * defect as a width literal, one property over.
   */
  it("lets a clamped label wrap rather than truncate, at the model's own limit", () => {
    expect(sourceRow).toContain("lineLimit(EventSourceLabelColumn.maximumLabelLines)");
    expect(sourceRow).toContain("fixedSize(horizontal: false, vertical: true)");
    // The specific regression this list had: one line and no wrap. And the
    // literal the model is supposed to own.
    expect(sourceRow).not.toContain("lineLimit(1)");
    expect(sourceRow).not.toContain("lineLimit(2)");
  });

  it("reads the row's own constants from the model it clamps against", () => {
    expect(sourceRow).toContain("EventSourceLabelColumn.interColumnSpacing");
    expect(sourceRow).toContain("EventSourceLabelColumn.horizontalPadding");
    expect(sourceRow).toContain("EventSourceLabelColumn.stackedLineSpacing");
    // #4208 — `numericColumnWidth` used to be a constant read here. It is a
    // measurement now and arrives with the label, from the one call above.
    expect(barAndNumbers).toContain("columns.numeric");
    expect(sourceRow).toContain("columns.label");
  });
});

/**
 * ═══ #4233 — THE ROW ACTUALLY HONOURS THE LAYOUT IT WAS GIVEN ═══
 *
 * The Swift tests own the decision: when a label would need more than
 * `maximumLabelLines` in the column the clamp gives it, `columns.layout` is
 * `.stacked`. Nothing in them can see whether the VIEW then draws a stacked row
 * — a model that returns `.stacked` into a view with one hardcoded `HStack` is
 * a fix that passes its own unit tests and changes nothing on the phone, which
 * is the exact failure mode this repo has shipped before.
 */
describe("#4233 the row draws both layouts", () => {
  it("branches on the model's layout rather than on the text size", () => {
    expect(sourceRow).toContain("switch columns.layout");
    expect(sourceRow).toContain("case .inline:");
    expect(sourceRow).toContain("case .stacked:");
    // A size threshold in the view would be the literal this file exists to
    // keep out, wearing a different type.
    expect(sourceRow).not.toContain("dynamicTypeSize >=");
    expect(sourceRow).not.toContain("accessibility1");
  });

  it("stacks into a VStack and keeps the bar and numbers on one line", () => {
    const stacked = sourceRow.slice(sourceRow.indexOf("case .stacked:"));
    expect(stacked).toContain("VStack(");
    expect(stacked).toContain("HStack(spacing: EventSourceLabelColumn.interColumnSpacing)");
    expect(stacked).toContain("probabilityBarAndNumbers(");
  });

  it("keeps the inline layout a single row", () => {
    const inline = sourceRow.slice(
      sourceRow.indexOf("case .inline:"),
      sourceRow.indexOf("case .stacked:"),
    );
    expect(inline).toContain("HStack(spacing: EventSourceLabelColumn.interColumnSpacing)");
    expect(inline).not.toContain("VStack(");
  });
});

/**
 * ═══ #4208 — AND THE TWO COLUMNS OF NUMBERS BESIDE THE LABEL ═══
 *
 * Every assertion above passed while both probability columns were pinned at a
 * hardcoded 36pt, so at accessibility sizes each `49%` wrapped to one glyph per
 * line: `4` / `9` / `%`, twice per row. Same class as the label, one column over
 * — and the third time on this row that a literal correct at `.large` was left
 * behind by a fix aimed at the thing next to it.
 *
 * Measured in `.caption2.monospacedDigit()`, the widest string
 * `formatProbability` can return is `>99%`: 31.2pt at `.large` (so the 36pt box
 * was GENEROUS) and 106.3pt at a11y5 (nearly three times it).
 *
 * The Swift model tests own the arithmetic. What they cannot see — CI compiles
 * no Swift, and even locally they only exercise `EventSourceLabelColumn` — is
 * whether the VIEW spends the measurement or goes back to writing a number
 * down. That is this file's job, and it is the failure mode with the track
 * record here.
 */
describe("#4208 the shared row sizes its probability columns against ink", () => {
  it("draws the numbers at the measured width", () => {
    const frames = barAndNumbers.match(
      /\.frame\(\s*width: columns\.numeric, alignment: \.trailing\)/g,
    );
    // Two columns, away and home. One match would mean half the row was fixed —
    // which is the exact shape of the bug this file keeps finding.
    expect(frames).toHaveLength(2);
  });

  it("has not gone back to the 36pt literal", () => {
    expect(barAndNumbers).not.toContain("width: 36");
    expect(barAndNumbers).not.toContain("numericColumnWidth");
  });
});

describe.each([
  ["sourceContent", sourceContent],
  ["bookmakerContent", bookmakerContent],
])("#4208 %s measures its probability columns against ink", (name, slice) => {
  it("has not gone back to the 36pt literal", () => {
    expect(slice).not.toContain("width: 36");
    expect(slice).not.toContain("numericColumnWidth");
  });

  /**
   * The column is sized from the strings the list PRINTS, so the model has to be
   * handed them. A `values:` that is empty, or built from something other than
   * the row's own formatter, sizes the column against a different table than the
   * one on screen.
   */
  it("hands the model the strings it will actually print", () => {
    const call = slice.slice(slice.indexOf("EventSourceLabelColumn.columns("));
    expect(call).toContain("values:");
    expect(call.slice(0, call.indexOf("availableWidth:"))).toContain("formatProbability(");
  });
});

/**
 * `bookmakerContent` draws numbers only on rows that have BOTH prices. The width
 * model must apply the same test, or the column is measured against strings the
 * view never draws — too wide, silently, starving the bar with whitespace.
 *
 * One predicate, named once and used twice, is the only way to keep those in
 * step; a second inline copy is how they drift.
 */
describe("#4208 the books column measures the rows it actually draws", () => {
  it("derives the measured values through the same predicate as the row", () => {
    // #4284 — the predicate moved once more, and this pin moved with it rather
    // than being relaxed. `namedBookmakerRows` now calls `bookmakerProbabilities`
    // ONCE per book and both halves read the result off the row, so the drift
    // this guards — measuring through one rule and drawing through another —
    // stopped being possible rather than merely being tested for. The call must
    // still be the only way a pair is obtained, so it is pinned where it went.
    expect(namedRows).toContain("bookmakerProbabilities(bm)");

    // #4406 — and it moved once more, in the same direction, which is why the
    // two `if`s this test used to pin are gone rather than relaxed. They were
    // `guard let pair = row.probabilities else { return [] }` here and
    // `if let probabilities {` in the row: the width model skipping a row, and
    // the view skipping that same row's numbers, kept in step with each other.
    // A row without a pair is no longer a row at all, so both skips are dead
    // code and the pair is non-optional. THE PROPERTY IS UNCHANGED AND NOW
    // UNCONDITIONAL: every string measured is a string drawn, because there is
    // no row either half can decline. `everySportsbookRowCarriesANumber.test.ts`
    // holds the type that makes it true; these two pin that this function reads
    // the row rather than re-deriving anything.
    expect(bookmakerContent).toContain("formatProbability(row.probabilities.away)");
    expect(bookmakerContent).toContain("probabilities: row.probabilities");
    expect(sourceRow).not.toContain("if let probabilities {");

    // …and the two halves read ONE array, which is what makes the above true.
    // Two `namedBookmakerRows` calls in this function would re-open the gap with
    // both pins still green (the cap and the naming are order-dependent).
    expect(bookmakerContent).toContain("labels: rows.map(\\.label)");
    expect(bookmakerContent).toContain("ForEach(rows)");
    expect(bookmakerContent.match(/namedBookmakerRows\(/g)).toHaveLength(1);
  });

  it("never substitutes a made-up price for a row that has none", () => {
    // A fallback pair would both fabricate a number and widen the column to the
    // widest string there is.
    expect(bookmakerContent).not.toMatch(/\?\?\s*\(away:/);
  });
});

/**
 * ═══ WHERE THE WIDTH IS MEASURED, WHICH DECIDES WHETHER THE CLAMP RUNS AT ALL ═══
 *
 * `maximumLabelWidth` treats an unmeasured row (`availableWidth == 0`) as
 * UNCLAMPED on purpose — the first layout pass should size on ink rather than
 * snap wider a frame later. That makes the PUBLISH SITE load-bearing rather than
 * incidental: a list that never receives a measurement is not merely unstyled,
 * it has silently lost the probability bar's 72pt floor.
 *
 * The two lists render under INDEPENDENT conditions (`!sourceEntries.isEmpty`
 * and `!bookmakers.isEmpty`). An event with sportsbook odds and no aggregate
 * sources draws the books list alone — the disclosure's own toggle reads
 * "Individual Sportsbooks" for precisely that case, and `win_prob_sources = {}`
 * is a state this repo has photographed on real events. While the
 * `GeometryReader` sat behind `sourceContent`, that event left `sourceRowWidth`
 * at 0 forever and the books column was unclamped on every one of them.
 *
 * SwiftUI preferences travel UP, so this is not a matter of taste: an
 * `onPreferenceChange` attached to one list's subtree cannot see the other's.
 * The measurement belongs to the panel that holds both.
 */
describe("#4107 the row width is measured where BOTH lists can see it", () => {
  const toggle = withoutComments(
    functionBody(eventDetail, "private func sourcesToggle(_ event: EventDetail)"),
  );

  it("sliced the disclosure that renders both lists", () => {
    expect(toggle).toContain("sourceContent(event, entries: sourceEntries)");
    expect(toggle).toContain("bookmakerContent(event)");
  });

  it("publishes and reads the width on the shared panel", () => {
    expect(toggle).toContain("key: SourceRowWidthKey.self");
    expect(toggle).toContain("onPreferenceChange(SourceRowWidthKey.self)");
  });

  /**
   * The regression itself: the measurement scoped back down to one list. Both
   * halves asserted, because moving it into `bookmakerContent` instead would be
   * the same bug pointed the other way.
   */
  it("does not scope the measurement to either list alone", () => {
    expect(sourceContent).not.toContain("SourceRowWidthKey");
    expect(bookmakerContent).not.toContain("SourceRowWidthKey");
  });

  /** Both lists must still be spending it. */
  it("both lists size against the panel measurement", () => {
    expect(sourceContent).toContain("availableWidth: sourceRowWidth");
    expect(bookmakerContent).toContain("availableWidth: sourceRowWidth");
  });
});

/**
 * The two lists draw in DIFFERENT faces — medium for the aggregate sources, plain
 * `.caption` for the individual books — and the model's contract is that a label
 * is measured in the font it is drawn in. Measuring the books as medium would
 * over-reserve: safe, invisible, and wrong in the direction this module exists to
 * rule out. Asserted per-slice because it is the one thing that legitimately
 * differs between them.
 */
describe("#4107 each list measures in the face it draws in", () => {
  /**
   * #4233 — the row is shared, so the face travels as an argument. That makes
   * the contract tighter, not looser: the face a list MEASURES in and the face
   * it hands the row to DRAW in are now two arguments of the same call, and a
   * mismatch is visible in one line rather than split across two functions.
   */
  it("the books list asks for, and draws in, the regular face", () => {
    expect(bookmakerContent).toContain("weight: .regular");
    expect(bookmakerContent).toContain("font: .caption,");
  });

  it("the sources list stays on the medium face it renders", () => {
    expect(sourceContent).toContain("font: .caption.weight(.medium),");
    expect(sourceContent).not.toContain("weight: .regular");
  });

  /** And the row draws the face it was handed rather than one of its own. */
  it("the shared row draws the face it is given", () => {
    expect(sourceRow).toContain(".font(font)");
    expect(sourceRow).not.toContain(".font(.caption)");
  });
});

describe("#4107 the list can be photographed at all", () => {
  /**
   * The other reason a Dynamic Type bug sat here unmeasured: the list is behind a
   * `@State` chevron and the LOOK rig cannot tap, so no screenshot of it had ever
   * been taken. `-launch_expand_sections` is the fix, and it must stay inert for
   * readers.
   */
  it("opens the disclosure only when the rig asks", () => {
    expect(eventDetail).toContain(
      "@State private var showSources = LaunchRig.expandsCollapsedSections()",
    );
    const rig = readFileSync(join(IOS_ROOT, "Utilities/LaunchRig.swift"), "utf8");
    expect(rig).toContain('static let expandSectionsKey = "launch_expand_sections"');
    expect(rig).toContain("defaults.bool(forKey: expandSectionsKey)");
  });
});
