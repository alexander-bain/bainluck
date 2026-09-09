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

describe("#4107 the Sources list label column", () => {
  /**
   * THE SLICE IS PROVEN FIRST. Every ban below is a `not.toContain`, and a
   * `not.toContain` on an empty string passes. If the signature ever drifts,
   * `functionBody` throws — but if it matched something tiny or wrong, the bans
   * would go quietly green. So: the slice must be the row-drawing function, and
   * must contain the landmarks only that function has.
   */
  it("slices the function that actually draws the source rows", () => {
    expect(sourceContent.length).toBeGreaterThan(400);
    expect(sourceContent).toContain("ProbabilityBar(");
    expect(sourceContent).toContain("entry.label");
    expect(sourceContent).toContain("formatProbability(");
  });

  it("asks the width model instead of writing a number down", () => {
    expect(sourceContent).toContain("EventSourceLabelColumn.width(");
    expect(sourceContent).toContain("typeSize: dynamicTypeSize");
  });

  /**
   * The literal itself, and the shape of it. `width: <digits>` catches the next
   * hand-picked number as well as this one — the failure mode here is not "118
   * specifically" but "someone wrote a point count in this row again".
   */
  it("has no hardcoded point width left in the row", () => {
    expect(sourceContent).not.toContain("width: 118");
    expect(sourceContent).not.toMatch(/\.frame\(\s*width:\s*\d/);
  });

  /**
   * `.minimumScaleFactor` is banned in this row, not merely absent.
   * `CalibrationSourceTableGeometry` records it measured and REJECTED on the same
   * row shape: SwiftUI scales sibling `Text` together, so a floor shrinks every
   * label in the list to half-rescue one and still truncates a character later.
   * It is the single most tempting thing to add back here.
   */
  it("does not reach for minimumScaleFactor as a backstop", () => {
    expect(sourceContent).not.toContain("minimumScaleFactor");
  });

  /**
   * Both halves of the wrap, together — #3966 found `lineLimit(2)` alone still
   * truncates when the parent proposes one line's height.
   */
  it("lets a clamped label wrap rather than truncate", () => {
    expect(sourceContent).toContain("lineLimit(2)");
    expect(sourceContent).toContain("fixedSize(horizontal: false, vertical: true)");
  });

  /**
   * The clamp protects the bar using `fixedRowCost`, which is a CLAIM about this
   * row's paddings. If the view stops reading those constants from the model, the
   * model can drift from the layout it describes — which is the original defect
   * with extra steps.
   */
  it("reads the row's own constants from the model it clamps against", () => {
    expect(sourceContent).toContain("EventSourceLabelColumn.interColumnSpacing");
    expect(sourceContent).toContain("EventSourceLabelColumn.numericColumnWidth");
    expect(sourceContent).toContain("EventSourceLabelColumn.horizontalPadding");
  });

  it("measures against the view's own text size, not the app's", () => {
    const geometry = readFileSync(GEOMETRY, "utf8");
    // `UIFont.preferredFont(forTextStyle:)` with no trait collection resolves
    // against the process's setting; that is how a column ends up narrower than
    // the string inside it.
    expect(geometry).toContain("compatibleWith: traits");
    expect(geometry).toContain("UIFont.systemFont(ofSize: base.pointSize, weight: .medium)");
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
