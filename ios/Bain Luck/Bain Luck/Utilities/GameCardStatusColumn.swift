import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

/// The middle column of the Discover GAME card's hero — the one that reads
/// `Bottom 6th` / `Final` / `vs` between the two crests.
///
/// #8144 — THE COLUMN WAS A HARDCODED 50pt AND HAD NEVER TRACKED DYNAMIC TYPE.
///
/// `DiscoverEventCard.heroContent` drew its status `VStack` at `.frame(width: 50)`.
/// The literal has a comment on it (live/048) saying it is "sized for `Q3`", and
/// that is exactly what it was: correct for one string at one text size.
///
/// **Measured, it was not even correct at the default text size.** In the face the
/// card actually draws it in — `.caption2.weight(.heavy).monospacedDigit()`, 11pt
/// at `.large` — the real strings are:
///
///   - `Q3`          16.5pt — the string the literal was chosen for, 1 line
///   - `Bottom 6th`  65.2pt — **30% over the box before any accessibility setting**
///   - `End of 3rd`  59.3 · `1st Period` 59.4 · `Halftime` 50.0 — all at or over
///   - `104 - 98`    57.2pt in `.footnote` — a FINAL score, also over
///
/// So `Bottom 6th` has always wrapped to two lines on every phone at every text
/// size, and the accessibility report is the same defect further along its curve:
/// the box stays 50pt while the type ramps to 40pt at a11y5, where `Bottom 6th`
/// is 218.3pt of ink and breaks into **six** lines of one or two glyphs, over the
/// team names either side.
///
/// `EventSourceLabelColumn` (#4107/#4208/#4233) is the pattern and the warning:
/// measure the strings THIS render will draw, in the font it will draw them in,
/// at the view's own `dynamicTypeSize`. A third literal would be correct for
/// exactly one text size, the same way 50 was.
///
/// ## The reflow trigger is measured, not declared
///
/// Ink alone is unbounded, so the column cannot simply take what it wants: at
/// a11y5 `Bottom 6th` asks for more width than a 375pt phone's hero HAS. The
/// status stays between the crests exactly while it fits there on one untruncated
/// line inside a share of the row that a piece of CONTEXT may have; otherwise the
/// row reflows and it takes its own centred line under the matchup.
///
/// Two bounds, and both are live:
///
///  1. **Each team column's irreducible content** — its 52pt avatar, or its score
///     if that is wider (`.title2.weight(.black)`: `104` is 45.5pt at `.large` and
///     116.7pt at a11y5, so on a high-scoring final the SCORE is the floor).
///  2. **A third of the row** (`maximumInlineStatusShare`). Bound 1 alone is not
///     enough, and the case that proves it is the ordinary one: a baseball card
///     reads `Bottom 6th` over scores of `4` and `2`, so the score never outgrows
///     the avatar and bound 1 leaves 211pt of a 315pt hero free. At a11y3 the
///     status would then draw itself 160pt wide — HALF the row, wider than either
///     crest beside it. Legible, unshredded, and still wrong: the period would be
///     shouting over the two teams whose game it describes. Equal thirds is the
///     point where a three-column row stops being one.
///
/// Measured for `Bottom 6th` over a 4–2 baseball card, where bound 2 is the one
/// that binds at every size:
///
///   | size     | ink + slack | 375pt phone (105 free) | 440pt phone (126.7 free) |
///   |----------|-------------|------------------------|--------------------------|
///   | large    | 66.2        | inline                 | inline                   |
///   | xxxLarge | 96.4        | inline                 | inline                   |
///   | a11y1    | 111.4       | **stacked**            | inline                   |
///   | a11y2    | 132.6       | stacked                | **stacked**              |
///   | a11y5    | 219.3       | stacked                | stacked                  |
///
/// The trigger lands on a different size on each phone, and on a different size
/// for each string — `Q3` is 59.1pt at a11y5 and stays inline on both phones at
/// every shipped size. A declared threshold, the obvious
/// `dynamicTypeSize >= .accessibility1`, would have been this file's own bug
/// written a second time: it would stack `Q3` where there was room for it and
/// still shred a long period on the narrow phone one size early.
///
/// ## What moves at the default text size
///
/// This is not only an accessibility fix and it is not inert on the phone most
/// people use. At `.large` the column stops being 50pt and becomes the ink it
/// needs — 66.2pt for `Bottom 6th`, which UNWRAPS a string that has been taking
/// two lines since the card shipped; and 17.5pt for `Q3`, which hands 32pt back
/// to the two crests on every hockey and basketball card. It gets narrower where
/// the string is short and wider where it is long, which a literal cannot do in
/// either direction.
enum GameCardStatusColumn {

    // MARK: - The row's irreducible costs

    /// `badgeTile` and the avatar image are both drawn at 52pt square, so this is
    /// the width a team column cannot go below whatever its label does. The label
    /// itself is `lineLimit(1)` and truncates by design, so it is NOT part of the
    /// floor — charging the row for `Chicago Cubs` (279.1pt at a11y5) would stack
    /// every card at every accessibility size and call it measurement.
    static let avatarWidth: Double = 52

    /// A point of slack over measured ink. `NSString.size` returns a fractional
    /// width and SwiftUI truncates on the fractional overflow, so a column sized
    /// to the exact measurement can still clip its own last glyph.
    static let inkSlack: Double = 1

    /// The vertical gap between the matchup and the status line, once reflowed.
    static let stackedLineSpacing: Double = 6

    /// The most of the row the status may take while it sits inside it.
    ///
    /// DERIVED, not picked: "the period never gets more room than either team" is
    /// `S <= (available - S) / 2`, which is `S <= available / 3`. At the limit the
    /// three columns are equal, which is the last arrangement that still reads as
    /// a matchup with a note between the crests rather than a note with two crests
    /// beside it.
    ///
    /// Being a PROPORTION is what keeps it out of the class of bug this file
    /// repairs. It carries no point value and no text size, so it cannot be right
    /// for one phone or one string and wrong for the next — unlike the 50 it
    /// replaces, and unlike the `>= .accessibility1` threshold it was tempting to
    /// write instead.
    static let maximumInlineStatusShare: Double = 1.0 / 3.0

    /// ONE untruncated line is the whole inline contract — applied by the VIEW as
    /// its `lineLimit`, because the model's `ink <= budget` test already decides
    /// it (see `layout`).
    ///
    /// Two would be the softer rule and it is the wrong one: `Bottom 6th` on two
    /// lines at 50pt is where this defect STARTS, and every frame in #8144 is that
    /// same wrap one or two sizes further on. A column that is allowed to wrap has
    /// no principled stopping point between two lines and the six that were
    /// photographed, because the thing that decides is the literal, not the rule.
    static let maximumInlineStatusLines: Int = 1

    /// Reflowed, the status has the hero's whole width and wrapping is no longer
    /// the defect — nothing sits beside it to be shredded against. Every string
    /// this card draws fits on ONE line of that width at every shipped size (the
    /// worst, a11y5 `Bottom 6th`, is 218.3pt of a 315pt line on the narrowest
    /// phone), so this limit is headroom for a period name longer than any ESPN
    /// currently returns: it should wrap rather than clip.
    static let maximumStackedStatusLines: Int = 2

    /// Where the status sits, for a given render.
    enum Layout: Equatable {
        /// Between the two crests, sized to the ink it needs.
        case inline(statusWidth: Double)
        /// On its own centred line under the matchup, which takes the full width.
        case stacked
    }

    // MARK: - The fonts these strings are actually drawn in

    #if canImport(UIKit)
    /// `.font((isLive ? .caption2 : .footnote).weight(.heavy).monospacedDigit())`
    /// at the call site — the live arm is a size smaller than the static one, so
    /// measuring one for the other would mis-size the column in both directions.
    ///
    /// The trait collection is what makes this the VIEW's text size rather than
    /// the APP's: `UIFont.preferredFont` with no traits resolves against the
    /// process setting, and measuring one while drawing the other is how a column
    /// ends up narrower than the string inside it.
    static func statusFont(isLive: Bool, at typeSize: DynamicTypeSize) -> UIFont {
        let traits = UITraitCollection(
            preferredContentSizeCategory:
                CalibrationSourceTableGeometry.CellFont.contentSizeCategory(typeSize))
        let base = UIFont.preferredFont(
            forTextStyle: isLive ? .caption2 : .footnote, compatibleWith: traits)
        return UIFont.monospacedDigitSystemFont(ofSize: base.pointSize, weight: .heavy)
    }

    /// `.font(.title2.weight(.black).monospacedDigit())` — `heroTeam`'s score.
    static func scoreFont(at typeSize: DynamicTypeSize) -> UIFont {
        let traits = UITraitCollection(
            preferredContentSizeCategory:
                CalibrationSourceTableGeometry.CellFont.contentSizeCategory(typeSize))
        let base = UIFont.preferredFont(forTextStyle: .title2, compatibleWith: traits)
        return UIFont.monospacedDigitSystemFont(ofSize: base.pointSize, weight: .black)
    }
    #endif

    /// Per-character fallback for a platform that cannot measure text. Never used
    /// on iOS.
    static let fallbackCharacterWidth: Double = 6.5

    /// The ink a status string occupies, in the font it is drawn in.
    static func statusWidth(
        _ string: String, isLive: Bool, typeSize: DynamicTypeSize = .large
    ) -> Double {
        #if canImport(UIKit)
        return Double((string as NSString)
            .size(withAttributes: [.font: statusFont(isLive: isLive, at: typeSize)]).width)
        #else
        return Double(string.count) * fallbackCharacterWidth
        #endif
    }

    /// The widest a team column can be squeezed to and still draw its own
    /// content: the avatar, or the score standing on top of it.
    ///
    /// `scores` are the strings THIS card will print — empty on a scheduled game,
    /// where the floor is the avatar alone.
    static func teamColumnFloor(
        scores: [String], typeSize: DynamicTypeSize = .large
    ) -> Double {
        #if canImport(UIKit)
        let font = scoreFont(at: typeSize)
        let widest = scores
            .map { Double(($0 as NSString).size(withAttributes: [.font: font]).width) }
            .max() ?? 0
        #else
        let widest = scores.map { Double($0.count) * fallbackCharacterWidth }.max() ?? 0
        #endif
        return max(avatarWidth, widest)
    }

    /// How many lines the status needs when wrapped into `width`.
    ///
    /// Measured with UIKit's own line breaking rather than divided out of the ink.
    /// The two are not close in a narrow column: greedy wrapping, hyphenation and
    /// the fact that a break can only fall between glyphs waste far more than an
    /// `ink / width` estimate predicts — which is how `Bottom 6th` reaches six
    /// lines in a box its ink says should hold it in five.
    static func statusLineCount(
        _ string: String, isLive: Bool, width: Double, typeSize: DynamicTypeSize = .large
    ) -> Int {
        guard width > 0 else { return .max }
        #if canImport(UIKit)
        let font = statusFont(isLive: isLive, at: typeSize)
        let bounding = (string as NSString).boundingRect(
            with: CGSize(width: width, height: .greatestFiniteMagnitude),
            options: [.usesLineFragmentOrigin, .usesFontLeading],
            attributes: [.font: font], context: nil)
        return max(1, Int((bounding.height / font.lineHeight).rounded()))
        #else
        return max(1, Int((statusWidth(string, isLive: isLive, typeSize: typeSize) / width).rounded(.up)))
        #endif
    }

    // MARK: - The decision

    /// Where the status goes on this card, at this text size, in this much room.
    ///
    /// - `availableWidth` is the hero's own content width, published by a
    ///   `GeometryReader` at the call site rather than derived from the screen —
    ///   a card's width is a layout outcome (padding, iPad columns, Stage Manager)
    ///   and a model that recomputed it from a screen size would be asserting a
    ///   layout instead of measuring one.
    static func layout(
        statusText: String,
        isLive: Bool,
        scores: [String],
        availableWidth: Double,
        typeSize: DynamicTypeSize = .large
    ) -> Layout {
        let ink = statusWidth(statusText, isLive: isLive, typeSize: typeSize) + inkSlack

        // Before the first `GeometryReader` pass the hero has no published width.
        // Inline is the honest answer rather than a placeholder: it is the shape
        // the card has always drawn, so an unmeasured first frame looks like the
        // card and not like a reflow that then undoes itself.
        guard availableWidth > 0 else { return .inline(statusWidth: ink) }

        let budget = min(
            availableWidth - teamColumnFloor(scores: scores, typeSize: typeSize) * 2,
            availableWidth * maximumInlineStatusShare)

        // `ink <= budget` IS the one-line test — ink is the unwrapped width, so a
        // string that fits inside the budget cannot need a second line. An
        // additional `statusLineCount(...) <= maximumInlineStatusLines` clause was
        // written here first and removed: it could not fail while this one passed,
        // and a clause that cannot fail reads as a second safeguard while being
        // nothing at all. `maximumInlineStatusLines` is the `lineLimit` the VIEW
        // applies, which is where it does work — as the clip guard on a string
        // this model has not seen.
        guard budget > 0, ink <= budget else { return .stacked }

        return .inline(statusWidth: ink)
    }
}
