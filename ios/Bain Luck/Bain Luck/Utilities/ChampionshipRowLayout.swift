import CoreGraphics

// MARK: - How a Championship Path row divides its card

/// How one Championship Path row spends the width of the team card it sits in.
///
/// #3574 and #3580 are the same arithmetic seen from two ends, so the rule that
/// closes them is one rule and it lives here rather than as expressions on a
/// SwiftUI view — the `MarketMapRail` precedent (#3503): a raster can tell you
/// that a bar is 2 pt wide, but it cannot tell you *why*, and a `@ViewBuilder`
/// expression can only be asserted by reading pixels.
///
/// **What went wrong.** The row was three columns with two of them nailed down:
///
/// ```
/// label 80  +  spacing 8  +  [bar]  +  spacing 8  +  badges 70
/// ```
///
/// 80 + 8 + 8 + 70 = **166**, and the bar got whatever was left. Measured off
/// `artifacts-native-038/AFTER-mlb-15305463-s900.png` (Brewers @ Reds, iPhone
/// 17, 402 pt wide, scale exactly 3.0) by scanning the PNG for the card
/// background rectangle, what was left was **0.0 pt**: the two team cards span
/// x = 3.0…398.7 pt, each card 190.0 pt, and after `teamCard`'s `.padding(12)`
/// each row had exactly the 166.0 pt it had already spent.
///
/// The 190 is circular, and that is the whole mechanism. The row *demanded*
/// 166 pt, so the card became 166 + 24 pt of padding whether or not the screen
/// had room — two of them plus the gap came to 396 pt inside the 338.3 pt the
/// page actually offers, so the card overflowed the screen AND left its own bar
/// nothing. `max(2, 0 * probability)` returned the 2 pt floor, and the same PNG
/// shows the Brewers' 99.6%, 96.2% and 13.4% rows all drawing an identical
/// 2.00 pt fill at x = 103.0 pt, which is precisely 3 + 12 + 80 + 8. The bar was
/// decorative, at every probability, on every iPhone-width event page (#3580).
///
/// From the other end, the same absence of slack is why a **clinched** row
/// broke its own words: the badge column has to hold a trend badge *and* the
/// word "clinched", it only has 70 pt, and with nowhere to go SwiftUI wrapped
/// inside the `Text`s — `clinc` / `hed` and `91.3` / `%` (#3574).
///
/// **The rule.** A row keeps the compact one-line shape only where the card is
/// actually wide enough for it, counting the gaps and the padding. Where it is
/// not, the label takes its own line and the bar and badges take the next one,
/// which hands the bar the width it never had.
///
/// Measured on the fixed render (`artifacts-native-039/`): the cards no longer
/// inflate past the page, each is **161.5 pt** with **137.3 pt** of content, and
/// both the clinched and the ordinary card stack. The Brewers' bars went from
/// 2.00 / 2.00 / 2.00 pt to 29.0 / 28.0 / ~4 pt for 99.6% / 96.2% / 13.4%. On
/// iPad and Mac neither card stacks, so those keep the compact row.
///
/// What that leaves open, stated rather than hidden: 137.3 pt is not enough for
/// the bar to reach `minBarWidth` even stacked, so 96% and 99.6% land within a
/// point of each other. The rule gives the bar everything the card has; making
/// the card bigger is a different question from how a row divides it.
/// The two columns of a Championship Path row, as the card actually measured
/// them — not as a constant hoped they would be.
///
/// #4328: every constant in this file was measured at ONE Dynamic Type size and
/// then used at all twelve. `Text(formatProb(prob))` is `.font(.caption)`, a text
/// style, so the probability grows with the reader's setting inside a column that
/// could not: at `.accessibility3` the badge wants 117.67 pt and the column
/// offered 76, so `lineLimit(1)` did what it promised and printed `1…` — the
/// number the row exists to show, truncated, while the trend badge beside it
/// (fixed `.system(size: 9)`) stayed exactly where it was.
///
/// A column that is a function of the reader's text size cannot be a `static let`,
/// and the honest scaling factor is not `@ScaledMetric` either — the badge is one
/// part that scales and one part that does not, so any single multiplier is wrong
/// in one direction or the other. So the card measures what its own rows want and
/// hands the answer back here. The constants below survive as the pre-measurement
/// fallback, which is the same role `contentWidth == 0` already plays.
struct ChampionshipColumnWidths: Equatable, Sendable {
    var label: CGFloat = 0
    var badges: CGFloat = 0

    static let zero = ChampionshipColumnWidths()

    /// Element-wise max: one card, one column, sized to its widest row.
    func merged(with other: ChampionshipColumnWidths) -> ChampionshipColumnWidths {
        ChampionshipColumnWidths(
            label: max(label, other.label), badges: max(badges, other.badges))
    }
}

/// Which of the three shapes a row takes, chosen from measured widths.
enum ChampionshipRowShape: Equatable {
    /// `label │ bar │ badges` — only where the card is genuinely wide enough.
    case inline
    /// The label on its own line, `bar │ badges` below it.
    case stacked
    /// #4328: label, then badges, then a bar across the whole card.
    ///
    /// At `.accessibility5` the badge alone wants 141.33 pt and a phone card has
    /// 137.3 pt, so there is no arrangement in which the bar and the badges share
    /// a line — `stacked` would hand the bar a negative width and draw the 2 pt
    /// floor that #3580 was. Giving the bar the whole card instead makes it
    /// *longer* than at default size, and every row of the card still gets the
    /// same track, so the bars stay comparable.
    case badgesAboveBar
}

enum ChampionshipRowLayout {

    // MARK: Measured constants

    /// The stage-label column in the one-line shape. Unchanged; "Make Playoffs"
    /// measures ~79 pt at `.caption` and fits with ~1 pt to spare.
    static let labelWidth: CGFloat = 80

    /// The gap between a row's columns.
    static let spacing: CGFloat = 8

    /// The gap between the two team cards.
    static let cardSpacing: CGFloat = 16

    /// `teamCard`'s inset, on each side.
    static let cardPadding: CGFloat = 12

    /// The narrowest bar that can still draw what it claims to draw.
    ///
    /// Chosen, not guessed: at 3x, one percentage point of a 0–100% bar is one
    /// device pixel at 33.4 pt, so a bar narrower than that cannot resolve the
    /// quantity it is a picture of. Rounded up to 36.
    static let minBarWidth: CGFloat = 36

    /// The badge column when every row ends in a percentage.
    ///
    /// Measured by hosting the real `ChampionshipStageBadges` and asking what
    /// width it wants, over every combination of trend and probability the view
    /// can produce (`ChampionshipRowLayoutTests`). Two things that table shows:
    ///
    /// * The probability string costs nothing — `<1%`, `13%`, `50%` and `99%`
    ///   all measure the same under `monospacedDigit()`. (`>99%` is unreachable
    ///   here; anything above 0.99 takes the clinched branch.) **The trend badge
    ///   is what drives the width**: 64.67 pt at `2.0%`, 69.67 at `91.3%`,
    ///   70.67 at `99.9%`, 75.00 at `100.0%`.
    /// * So the shipping 70 pt was already short of its own worst case, by 0.67
    ///   pt at `99.9%` and 5 pt at `100.0%` — a truncated probability waiting on
    ///   a large enough day. `trend_24h` is a difference of two probabilities,
    ///   so `100.0%` is in range, and #3581 has the field publishing 91.4% today.
    ///
    /// 🔴 **SINCE #4328 THIS IS A FLOOR, NOT THE ANSWER.** Everything above was
    /// measured at `.large` and is true there and nowhere else: the widest badge
    /// wants 79 pt at `.xLarge` — one notch up from the default — and 141.33 pt at
    /// `.accessibility5`. `columns(measured:for:)` takes the larger of this and
    /// what the card measured, so the reader who changed nothing sees exactly what
    /// they saw before, and everyone else gets a column that fits.
    static let valueBadgeWidth: CGFloat = 76

    /// The badge column when EVERY row in the card says "clinched".
    ///
    /// ## This constant used to mean the opposite, and was 100
    ///
    /// It was "the column when ANY row says clinched", sized for a checkmark and
    /// the word *on top of* a trend badge — 94.00 pt at `91.3%`, 99.67 at
    /// `100.0%`. #4108 removed the trend badge from a clinched row, because a
    /// settled row claiming a 90.9-point 24h move is a false statement that
    /// reads as the probability. With the trend gone, `✓ clinched` measures
    /// **53.5 pt** and a clinched row is now the NARROWEST thing this column
    /// draws, not the widest.
    ///
    /// So the rule inverts. A card is one column wide for every row (see
    /// `badgeWidth(for:)`), and a card with one clinched row still has ordinary
    /// siblings wanting the full `valueBadgeWidth`. Only a card where *every*
    /// row is clinched can take the narrow column — a team that has clinched its
    /// division, pennant and championship alike.
    ///
    /// 🔴 Sizing a mixed card to this width would truncate the ordinary rows,
    /// which is #3574 again with the roles swapped. `ChampionshipRowLayoutTests`
    /// asserts that direction explicitly now; the old suite only ever compared
    /// this constant against clinched rows and would have passed.
    static let allClinchedBadgeWidth: CGFloat = 56

    /// A stage at or below this is shown as a percentage, above it as "clinched".
    static let clinchedProbability: Double = 0.99

    /// Movement smaller than this draws no trend badge.
    static let minimumTrendToShow: Double = 0.005

    // MARK: What a row shows

    static func isClinched(probability: Double?) -> Bool {
        (probability ?? 0) > clinchedProbability
    }

    static func showsTrendBadge(trend: Double?) -> Bool {
        guard let trend else { return false }
        return abs(trend) >= minimumTrendToShow
    }

    // MARK: The rule

    /// The badge column for a whole card.
    ///
    /// One width for every row of the card, deliberately. Sizing each row to its
    /// own content would give the three bars three different track lengths, and
    /// bars of different lengths cannot be compared to each other — which is the
    /// only reason to draw three of them.
    /// The column is the card's WIDEST row, and since #4108 that is an ordinary
    /// row whenever the card has one — `allSatisfy`, not `contains`. Inverted
    /// from the original `contains` reading, which was correct only while a
    /// clinched row was the wider of the two.
    static func badgeWidth(for stages: [ProgressionStageData]) -> CGFloat {
        guard !stages.isEmpty else { return valueBadgeWidth }
        return stages.allSatisfy { isClinched(probability: $0.probability) }
            ? allClinchedBadgeWidth
            : valueBadgeWidth
    }

    /// The width a one-line row needs before its bar starts eating into itself.
    static func inlineRowMinimumWidth(
        labelWidth: CGFloat = ChampionshipRowLayout.labelWidth, badgeWidth: CGFloat
    ) -> CGFloat {
        labelWidth + spacing + minBarWidth + spacing + badgeWidth
    }

    /// What one team card has to spend, gaps and padding included.
    ///
    /// The gaps and the padding are the whole point: a fit formula that omits
    /// them is how the row came to claim it had room for a bar it had already
    /// spent. Pinned in tests against the 396 pt / 2 card / 166 pt content
    /// measured off the production screenshot.
    static func teamCardContentWidth(totalWidth: CGFloat, cardCount: Int) -> CGFloat {
        guard cardCount > 0, totalWidth > 0 else { return 0 }
        let gaps = CGFloat(cardCount - 1) * cardSpacing
        let card = (totalWidth - gaps) / CGFloat(cardCount)
        return max(0, card - cardPadding * 2)
    }

    /// The columns before anything has been measured — the constants above.
    static func fallbackColumns(for stages: [ProgressionStageData]) -> ChampionshipColumnWidths {
        ChampionshipColumnWidths(label: labelWidth, badges: badgeWidth(for: stages))
    }

    /// The columns to use, given what the view measured.
    ///
    /// 🔴 **THE CONSTANTS ARE A FLOOR, AND A MEASUREMENT MAY ONLY RAISE THEM.**
    /// That is deliberate and it is what keeps this fix off the default-size
    /// render: at `.large` the widest badge the Brewers card can draw measures
    /// 69.67 pt against the 76 pt column, so the measurement is *smaller* and
    /// changes nothing. Letting it win would shave 6 pt off every bar on a screen
    /// Alex reads daily, to fix a defect that only exists above `.xLarge` — a
    /// price the reader never asked to pay. Above that the measurement wins and
    /// the probability gets its room back.
    ///
    /// The floor also covers the first layout pass, where nothing is measured yet
    /// and the whole value is zero.
    static func columns(
        measured: ChampionshipColumnWidths, for stages: [ProgressionStageData]
    ) -> ChampionshipColumnWidths {
        fallbackColumns(for: stages).merged(with: measured)
    }

    /// The shape a row takes in a card of this width, given what its columns
    /// actually measured.
    ///
    /// Read in order, and each step is the previous one's failure: sit on one line
    /// if the line holds everything; otherwise give the label its own line; and if
    /// even then the bar cannot resolve what it draws, give the bar the whole card
    /// and put the badges above it.
    static func shape(
        contentWidth: CGFloat, columns: ChampionshipColumnWidths
    ) -> ChampionshipRowShape {
        guard contentWidth > 0 else { return .stacked }
        if contentWidth >= inlineRowMinimumWidth(
            labelWidth: columns.label, badgeWidth: columns.badges) {
            return .inline
        }
        if contentWidth - spacing - columns.badges >= minBarWidth {
            return .stacked
        }
        return .badgesAboveBar
    }

    /// Whether the bar and badges drop below the label instead of sitting beside it.
    ///
    /// A card whose width is not known yet stacks: stacking never wraps a word
    /// and never starves the bar, so it is the safe answer to "not measured".
    static func stacksBelowLabel(contentWidth: CGFloat, stages: [ProgressionStageData]) -> Bool {
        shape(contentWidth: contentWidth, columns: fallbackColumns(for: stages)) != .inline
    }

    /// What the bar actually gets, under the layout the rule chose.
    ///
    /// Exists so a test can assert the number the user sees rather than the
    /// branch that produced it — 0.0 pt was the defect, not "the inline branch".
    static func barWidth(contentWidth: CGFloat, stages: [ProgressionStageData]) -> CGFloat {
        barWidth(contentWidth: contentWidth, columns: fallbackColumns(for: stages))
    }

    /// The same question asked with the card's own measurements.
    static func barWidth(
        contentWidth: CGFloat, columns: ChampionshipColumnWidths
    ) -> CGFloat {
        guard contentWidth > 0 else { return 0 }
        switch shape(contentWidth: contentWidth, columns: columns) {
        case .inline:
            return max(0, contentWidth - columns.label - spacing - spacing - columns.badges)
        case .stacked:
            return max(0, contentWidth - spacing - columns.badges)
        case .badgesAboveBar:
            return contentWidth
        }
    }
}
