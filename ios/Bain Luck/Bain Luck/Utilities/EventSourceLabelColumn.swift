import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// The label column of the event page's Sources list.
///
/// #4107 — THE COLUMN WAS A HARDCODED 118pt AND HAD NEVER TRACKED DYNAMIC TYPE.
///
/// Alex read `Sportsbooks (…` on the Angels–Red Sox page. The issue blamed the
/// label growing from `Sportsbooks (10)` to `Sportsbooks (14)`, and the comment
/// on the literal said the width had already been raised 90 → 118 for that
/// reason. **Measured, that is not what happened.** At default type size
/// `Sportsbooks (14)` is 99.9pt in a 118pt column — 18pt of headroom — and even
/// a three-digit count (107.6pt) fits. The label never truncated at `.large`.
///
/// What truncates is the same label at a larger text size, and the row's
/// `.minimumScaleFactor(0.85)` sets exactly where: effective capacity was
/// `118 / 0.85 = 138.8pt`, so
///
///   - xxLarge   `Sportsbooks (14)` = 128.2 — fits, by shrinking every label
///   - xxxLarge  = 142.1 — **truncates**, and `Bain Luck Model` (135.3) does not
///   - a11y1     = 169.2 — truncates badly, and now so does `Bain Luck Model`
///
/// which matches the report: one cut label rather than a broken table. So the
/// bug is Dynamic Type, the `Sportsbooks (N)` row is merely the longest string
/// and therefore first over the line, and `Bain Luck Model` is next. A third
/// literal would be correct for exactly one text size, the same way 90 was and
/// 118 was.
///
/// `CalibrationSourceTableGeometry` and `PeriodChipGeometry` are the pattern:
/// measure the strings THIS render will draw, in the font it will draw them in,
/// at the view's own `dynamicTypeSize`. Sized that way the column also gets
/// NARROWER than 118 at default (about 101pt for a real five-source event),
/// which hands the probability bar back ~17pt on every phone.
///
/// **`.minimumScaleFactor` is deliberately not part of this and was removed from
/// the call site.** `CalibrationSourceTableGeometry` already records it measured
/// and rejected on the same row shape: SwiftUI scales sibling `Text` together,
/// so a floor shrinks every label in the list to half-rescue one, still
/// truncates a character later, and reads as a safety net while changing
/// nothing.
///
/// **What this does NOT do.** Ink alone is unbounded — at accessibility sizes
/// `Sportsbooks (100)` wants 183pt, which on a 375pt phone would leave the bar
/// about 20pt and make the row pointless. So the width is clamped against the
/// space the row actually has, and the call site keeps `lineLimit(2)` +
/// `.fixedSize(horizontal: false, vertical: true)` to absorb whatever the clamp
/// cannot give. Both of those are load-bearing together — #3966 found that
/// `lineLimit(2)` alone still truncates when a parent proposes one line's
/// height. Past the clamp, at the largest accessibility sizes, a long label
/// takes two lines; it does not truncate.
///
/// ---
///
/// #4208 — AND THE TWO PROBABILITY COLUMNS BESIDE IT WERE A HARDCODED 36pt.
///
/// #4107 fixed the label and left the numbers, so at accessibility sizes the two
/// trailing columns stacked one glyph per line — `4` / `9` / `%`, twice per row,
/// a column of loose digits where two percentages should be. Same class of
/// defect, one column over: a point count that was correct at `.large` and
/// nowhere else.
///
/// Measured in the face they are drawn in (`.caption2.monospacedDigit()`, 11pt at
/// `.large` and 40pt at a11y5):
///
///   - `.large`   `>99%` = 31.2 — the 36pt box was GENEROUS, by 4.8pt
///   - a11y1      = 53.6 — over by half again
///   - a11y5      = 106.3 — nearly three times the box
///
/// Note the first line: sized to ink the numbers get NARROWER at default size,
/// so on the phone most people use this hands the probability bar back ~10-24pt
/// per row on top of what #4107 already returned. The bug only LOOKS like it is
/// about accessibility sizes.
///
/// This is why `fixedRowCost` stopped being a constant and `Columns` exists: the
/// numeric columns are part of the cost the label clamps against, so the two
/// have to be computed in one place or a later change fixes half of them again.
///
/// ---
///
/// #4233 — AND AT THE TOP OF THE SCALE THE ROW CANNOT BE A ROW AT ALL.
///
/// #4208 shipped the priority order above and photographed the result, which is
/// how this was found: the labels truncate (`be-tri…`, `bo-va…`, `draf tki…`)
/// while the bar sits on its 72pt floor and reads as a dash. Note what that
/// contradicts — the paragraph above promises "a long label takes two lines; it
/// does not truncate". **Measured, that promise is false**, and it fails earlier
/// and harder than the report of it said.
///
/// Wrapped with UIKit's own line breaking at the width the clamp actually hands
/// the column, on a 375pt phone:
///
///   - books list    a11y3 `draftkings` = 2 lines · a11y5 = **3**
///   - sources list  a11y2 = 2 lines · **a11y3 `Bain Luck Model` = 3** · a11y5 = 5
///
/// So the issue's own title (a11y4/a11y5) understates it: the five-source table
/// is already over its two-line contract at a11y3. A size threshold — the
/// obvious `dynamicTypeSize >= .accessibility1` — would have been this file's
/// original bug written a third time, correct for one text size and one screen
/// width: on a 402pt phone the books list never exceeds two lines at ANY size,
/// and the sources list first does at a11y4.
///
/// **So the trigger is measured, not declared.** The row reflows exactly when the
/// widest label it will draw needs more than `maximumLabelLines` lines in the
/// column the clamp gives it — which is the `lineLimit` the call site applies,
/// now read from here so the view and the model cannot disagree about what
/// "fits" means.
///
/// Reflowed, the label takes the full line and the bar and both numbers take the
/// line under it. Measured at every shipped size on both phones, **every label
/// this page draws then fits on ONE untruncated line** (the worst, a11y5
/// `betanysportsbook`, is 333.3pt of a 343pt line), and the bar recovers from its
/// 72pt floor to 115pt on the narrowest phone at the largest size. The reflow
/// does not trade the bar for the label the way the inline clamp had to; at the
/// point it engages, stacking is simply better for both.
enum EventSourceLabelColumn {

    // MARK: - The row's fixed costs

    /// `.padding(.horizontal, 16)`, applied on each side of the row.
    static let horizontalPadding: Double = 16
    /// `HStack(spacing: 6)` — three gaps between the row's four children.
    static let interColumnSpacing: Double = 6
    static let interColumnGapCount: Double = 3
    /// The two trailing probability columns.
    static let numericColumnCount: Double = 2

    /// Everything in the row that is not the label or the bar.
    ///
    /// A named sum rather than a number written down, because the whole defect
    /// being fixed here is a layout number that stopped matching the layout it
    /// described. If a padding changes, this follows it.
    ///
    /// #4208 — this is a FUNCTION of the text size now, not a constant. It used
    /// to be `122` because the numeric columns were a fixed `36`; once those
    /// track Dynamic Type the row's fixed cost does too, which is why the label
    /// and the numbers have to be computed together (see `Columns`).
    static func fixedRowCost(numericWidth: Double) -> Double {
        horizontalPadding * 2
            + interColumnSpacing * interColumnGapCount
            + numericWidth * numericColumnCount
    }

    /// #4233 — the same sum for a row that has reflowed.
    ///
    /// One gap fewer, because the label has left the line: the bar and the two
    /// numbers are three children with two gaps between them, not four with
    /// three. Written as its own count rather than `interColumnGapCount - 1` so
    /// that a change to the row's children has to be made deliberately in both
    /// places instead of arriving as an off-by-one.
    static let stackedInterColumnGapCount: Double = 2

    /// The vertical gap between the label's line and the bar's line.
    static let stackedLineSpacing: Double = 4

    /// Everything on the BAR's line that is not the bar, once the row reflows.
    static func stackedFixedRowCost(numericWidth: Double) -> Double {
        horizontalPadding * 2
            + interColumnSpacing * stackedInterColumnGapCount
            + numericWidth * numericColumnCount
    }

    /// The floor under the probability bar.
    ///
    /// The bar is the row's entire point — it is the only part a reader compares
    /// across sources — and below roughly this width a two-segment 6pt bar can no
    /// longer show a split anyone can read. The label yields first.
    static let minimumBarWidth: Double = 72

    /// The floor under the label column, so a table of short names
    /// (`Kalshi` is 34.8pt at `.large`) does not collapse into a ragged edge.
    static let minimumLabelWidth: Double = 60

    /// A point of slack over measured ink. `NSString.size` returns a fractional
    /// width and SwiftUI truncates on the fractional overflow, so a column sized
    /// to the exact measurement can still clip its own last glyph.
    static let inkSlack: Double = 1

    /// #4233 — the most lines a label may take before the row must reflow.
    ///
    /// This is the `lineLimit` both call sites apply, moved here so there is one
    /// number rather than two that happen to agree. The model decides the row
    /// reflows *because* the label would exceed the limit; if the view then
    /// applied a different limit, the model would be reasoning about a layout
    /// that is not on screen — which is the whole class of defect this file
    /// exists to close.
    static let maximumLabelLines: Int = 2

    // MARK: - The font the label is actually drawn in

    #if canImport(UIKit)
    /// `.font(.caption.weight(.medium))` at the call site. SwiftUI's `.caption`
    /// is `caption1`; measuring the plain face would under-charge the column,
    /// and measuring without the trait collection would resolve against the
    /// APP's text size rather than the view's — the mistake that makes a column
    /// narrower than the string inside it.
    ///
    /// `weight` exists because the two lists this model now sizes draw in
    /// DIFFERENT faces: the aggregate source rows are `.caption.weight(.medium)`
    /// and the individual sportsbook rows below them are a plain `.caption`.
    /// Measuring both as medium would over-reserve — safe, but it would quietly
    /// contradict the sentence above, which is the whole contract of this file.
    static func labelFont(
        at typeSize: DynamicTypeSize, weight: Font.Weight = .medium
    ) -> UIFont {
        let traits = UITraitCollection(
            preferredContentSizeCategory:
                CalibrationSourceTableGeometry.CellFont.contentSizeCategory(typeSize))
        let base = UIFont.preferredFont(forTextStyle: .caption1, compatibleWith: traits)
        return UIFont.systemFont(ofSize: base.pointSize, weight: uiWeight(weight))
    }

    /// `.font(.caption2.monospacedDigit())` at both call sites — a DIFFERENT text
    /// style from the label (`caption1`) and a different face, so it cannot reuse
    /// `labelFont`. `caption2` is 11pt at `.large` and 40pt at a11y5; measuring
    /// the label's style instead would under-charge the numeric column at every
    /// size, which is the same class of mistake as the literal it replaces.
    static func numericFont(at typeSize: DynamicTypeSize) -> UIFont {
        let traits = UITraitCollection(
            preferredContentSizeCategory:
                CalibrationSourceTableGeometry.CellFont.contentSizeCategory(typeSize))
        let base = UIFont.preferredFont(forTextStyle: .caption2, compatibleWith: traits)
        return UIFont.monospacedDigitSystemFont(ofSize: base.pointSize, weight: .regular)
    }

    /// Only the two faces these rows actually use are mapped. Anything else
    /// resolves to `.regular` rather than guessing: an unmapped weight that
    /// silently measured as `.medium` would over-reserve invisibly, and this
    /// module exists because an invisible width claim went wrong once already.
    private static func uiWeight(_ weight: Font.Weight) -> UIFont.Weight {
        weight == .medium ? .medium : .regular
    }
    #endif

    /// Per-character fallback for a platform that cannot measure text. Never used
    /// on iOS.
    static let fallbackCharacterWidth: Double = 6.5

    /// The ink a label actually occupies, measured in the font it is drawn in.
    static func textWidth(
        _ string: String, typeSize: DynamicTypeSize = .large, weight: Font.Weight = .medium
    ) -> Double {
        #if canImport(UIKit)
        return Double((string as NSString)
            .size(withAttributes: [.font: labelFont(at: typeSize, weight: weight)]).width)
        #else
        return Double(string.count) * fallbackCharacterWidth
        #endif
    }

    /// #4233 — how many lines a label needs when wrapped into `width`.
    ///
    /// Measured with UIKit's own line breaking rather than divided out of the
    /// ink, because the two are not close: at a11y5 in an 87pt column `bovada`
    /// is 135.3pt of ink — comfortably under two 87pt lines on paper — and still
    /// breaks as `bo-` / `va…`. Greedy wrapping, hyphenation and the fact that a
    /// break can only fall between glyphs waste far more of a narrow column than
    /// an `ink / width` estimate predicts, and this trigger has to agree with
    /// what the reader sees, not with an idealised packing of it.
    ///
    /// Rounded from the measured height, so a fractional last line counts as a
    /// line — which is what truncation does.
    ///
    /// **`hyphenationFactor` IS LOAD-BEARING AND WAS FOUND BY PHOTOGRAPH.**
    /// SwiftUI's `Text` hyphenates; `boundingRect` does not unless it is asked
    /// to, and it breaks a too-long word by character instead. The two disagree
    /// by a whole line exactly when it matters — measured on the real books
    /// table at a11y3 in the 131pt column the clamp gives it,
    /// `betanysportsbook` is 2 lines unhyphenated and 3 as SwiftUI draws it —
    /// so the first version of this trigger read "fits" and left the row inline,
    /// and the frame came back reading `be-` / `tanys…`. A measurement of a
    /// layout the renderer is not performing is worse than no measurement,
    /// because it is confident.
    static func labelLineCount(
        _ string: String, width: Double,
        typeSize: DynamicTypeSize = .large, weight: Font.Weight = .medium
    ) -> Int {
        guard width > 0, !string.isEmpty else { return 1 }
        #if canImport(UIKit)
        let font = labelFont(at: typeSize, weight: weight)
        let paragraph = NSMutableParagraphStyle()
        paragraph.hyphenationFactor = 1
        paragraph.lineBreakMode = .byWordWrapping
        let bounds = (string as NSString).boundingRect(
            with: CGSize(width: width, height: .greatestFiniteMagnitude),
            options: [.usesLineFragmentOrigin, .usesFontLeading],
            attributes: [.font: font, .paragraphStyle: paragraph], context: nil)
        guard font.lineHeight > 0 else { return 1 }
        // `.up`, not `.rounded()`: the sentence above says a fractional last
        // line counts as a line and nearest-rounding does not deliver that.
        // Every measured input so far divides evenly, so the two agree today —
        // but they disagree in the direction that leaves a row inline and
        // truncating, which is the defect, so the tie goes to stacking.
        return max(1, Int((Double(bounds.height) / Double(font.lineHeight)).rounded(.up)))
        #else
        let ink = textWidth(string, typeSize: typeSize, weight: weight)
        return max(1, Int((ink / width).rounded(.up)))
        #endif
    }

    /// The ink a rendered probability occupies, in the numbers' own face.
    static func numericTextWidth(_ string: String, typeSize: DynamicTypeSize = .large) -> Double {
        #if canImport(UIKit)
        return Double((string as NSString)
            .size(withAttributes: [.font: numericFont(at: typeSize)]).width)
        #else
        return Double(string.count) * fallbackCharacterWidth
        #endif
    }

    // MARK: - The numeric columns

    /// The shape a reader expects in these columns, used as their floor.
    ///
    /// A template rather than a point count, so the floor tracks Dynamic Type
    /// like everything else here — a literal floor would be this file's own bug
    /// reintroduced one constant over. With monospaced digits `00%` is exactly as
    /// wide as `49%` or any other two-digit percentage, which is what the column
    /// draws on all but a handful of rows.
    ///
    /// It exists for the degenerate list — a books table where no row carries
    /// both prices draws no numbers at all, and a column measured purely on ink
    /// would collapse to zero and quietly hand the label a wider clamp than the
    /// row really has.
    static let numericFloorTemplate = "00%"

    /// One width for BOTH probability columns, sized to the widest number this
    /// render will draw in either of them.
    ///
    /// Shared rather than per-column on purpose: the pair is one away–home unit
    /// that mirrors the hero, and two differently-sized boxes for the same
    /// quantity read as a mistake. Measured worst case (a11y5, `>99%` in both
    /// columns) still leaves the bar 49pt on a 375pt phone, so the symmetry costs
    /// nothing that independent widths would have bought.
    static func numericColumnWidth(
        for values: [String], typeSize: DynamicTypeSize = .large
    ) -> Double {
        let ink = values.map { numericTextWidth($0, typeSize: typeSize) }.max() ?? 0
        let floor = numericTextWidth(numericFloorTemplate, typeSize: typeSize)
        return max(ink, floor).rounded(.up) + inkSlack
    }

    // MARK: - The column

    /// The widest the label column may become, given the row it sits in.
    ///
    /// `availableWidth <= 0` means the row has not been measured yet — the first
    /// layout pass, before the `GeometryReader` behind it has reported. Returning
    /// `.infinity` there uses the ink-derived width for that frame rather than
    /// slamming the column to `minimumLabelWidth` and visibly snapping wider a
    /// frame later.
    static func maximumLabelWidth(availableWidth: Double, numericWidth: Double) -> Double {
        guard availableWidth > 0 else { return .infinity }
        return max(
            minimumLabelWidth,
            availableWidth - fixedRowCost(numericWidth: numericWidth) - minimumBarWidth)
    }

    /// The label column for THIS render: the widest label it will draw, at the
    /// view's own text size, clamped to what the row can spare.
    static func width(
        for labels: [String], availableWidth: Double, numericWidth: Double,
        typeSize: DynamicTypeSize = .large, weight: Font.Weight = .medium
    ) -> Double {
        let ink = labels.map { textWidth($0, typeSize: typeSize, weight: weight) }.max() ?? 0
        let wanted = ink.rounded(.up) + inkSlack
        return min(
            max(wanted, minimumLabelWidth),
            maximumLabelWidth(availableWidth: availableWidth, numericWidth: numericWidth))
    }

    // MARK: - Both columns, computed together

    /// #4208 — THE TWO COLUMNS CANNOT BE SIZED SEPARATELY.
    ///
    /// The numeric columns are part of `fixedRowCost`, which is what the label
    /// clamps against, so a numeric width that tracks Dynamic Type changes what
    /// the label may take at every size. Returning them as one value makes that
    /// coupling impossible to get half-right at a call site — which is how the
    /// numbers were left behind when #4107 fixed the label.
    ///
    /// **The priority order, stated, because at accessibility sizes on a 375pt
    /// phone the row genuinely cannot have everything.** The numbers are sized to
    /// their ink and are never clamped; the label yields; the bar yields last.
    /// That order is not a preference — it follows from which elements can
    /// degrade legibly. The label has a designed degradation (`lineLimit(2)` +
    /// `.fixedSize`, #3966) and the bar simply gets shorter, but a number has
    /// none: `49%` broken across lines is `4` / `9` / `%`, which is the defect
    /// this exists to fix, and a truncated `4…` is a WRONG number rather than a
    /// cramped one.
    ///
    /// Measured cost of that order at the extreme (a11y5, 375pt, `>99%` in both
    /// columns — the widest string `formatProbability` can return): the numbers
    /// take 108pt each, the label sits on its 60pt floor, and the bar gets 49pt
    /// rather than its usual 72pt minimum. Degraded, present, and readable as a
    /// split.
    ///
    /// `barWidth` is deliberately NOT clamped to zero: a row that over-subscribes
    /// should show up as a negative number in a test, not as a silent overflow on
    /// a phone. That it stays positive at every shipped width and text size is a
    /// claim, and `testTheBarSurvivesEveryTypeSizeOnTheNarrowestPhone` is where
    /// that claim is checked.
    /// #4233 — whether the row's four children share a line, or the label takes
    /// one of its own.
    enum RowLayout: Hashable {
        /// `label | bar | away% | home%`, the shape at every size that can hold it.
        case inline
        /// The label on its own line, `bar | away% | home%` on the line below.
        case stacked
    }

    struct Columns: Equatable {
        /// The label column.
        ///
        /// Clamped against the row when `layout` is `.inline`; the full width of
        /// the label's own line when it is `.stacked`. One property rather than
        /// two, so a call site cannot draw a stacked row and then size its label
        /// with the inline clamp — the mistake that #4208 was.
        let label: Double
        /// Each of the two probability columns.
        let numeric: Double
        /// Whether this list's rows draw inline or reflowed. A property of the
        /// LIST, not of a row: rows that reflowed individually would give a table
        /// with a ragged shape down it, so the widest label decides for all.
        let layout: RowLayout

        /// Everything on the bar's line that is not the bar or the label.
        var fixedRowCost: Double {
            switch layout {
            case .inline: return EventSourceLabelColumn.fixedRowCost(numericWidth: numeric)
            case .stacked: return EventSourceLabelColumn.stackedFixedRowCost(numericWidth: numeric)
            }
        }

        /// What the probability bar is actually left with on a row this wide.
        ///
        /// The guards assert against THIS rather than recomputing the clamp's own
        /// arithmetic: a test that re-derives `available - fixed - label` from the
        /// same constants the clamp uses moves both sides of its comparison at
        /// once and cannot fail (native/079's surviving mutant, one file over).
        ///
        /// #4233 — when the row is stacked the label is not on this line, so it
        /// is not subtracted. This is where the reflow pays: on a 375pt phone at
        /// a11y5 the bar goes from its 72pt floor to 115pt.
        func barWidth(availableWidth: Double) -> Double {
            switch layout {
            case .inline: return availableWidth - fixedRowCost - label
            case .stacked: return availableWidth - fixedRowCost
            }
        }
    }

    /// Both column widths for one render of one list.
    ///
    /// - Parameters:
    ///   - labels: every label this list will draw.
    ///   - values: every probability string this list will draw, from BOTH
    ///     columns — they share a width, so a `>99%` in the home column binds the
    ///     away column too.
    static func columns(
        labels: [String], values: [String], availableWidth: Double,
        typeSize: DynamicTypeSize = .large, weight: Font.Weight = .medium
    ) -> Columns {
        let numeric = numericColumnWidth(for: values, typeSize: typeSize)
        let inlineLabel = width(
            for: labels, availableWidth: availableWidth, numericWidth: numeric,
            typeSize: typeSize, weight: weight)

        // #4233 — the reflow decision, taken here so it arrives at the call site
        // already agreed with the widths it depends on. Asked of the INLINE
        // column, because the question is whether the inline row still works.
        let fits = labels.allSatisfy {
            labelLineCount($0, width: inlineLabel, typeSize: typeSize, weight: weight)
                <= maximumLabelLines
        }
        guard !fits, availableWidth > 0 else {
            return Columns(label: inlineLabel, numeric: numeric, layout: .inline)
        }
        return Columns(
            label: labelLineWidth(availableWidth: availableWidth),
            numeric: numeric, layout: .stacked)
    }

    /// The width of a reflowed row's label line: everything inside the padding.
    ///
    /// Measured at every shipped size on both phones, every label this page draws
    /// fits on one untruncated line of this width — the worst of them, a11y5
    /// `betanysportsbook`, is 333.3pt of 343. The call site keeps its
    /// `lineLimit` regardless, since a longer name than any book currently
    /// carries should wrap rather than clip.
    static func labelLineWidth(availableWidth: Double) -> Double {
        max(minimumLabelWidth, availableWidth - horizontalPadding * 2)
    }
}
