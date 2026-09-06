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
/// Measured off `artifacts-native-038/AFTER-mlb-15305463-s900.png` (Brewers @
/// Reds, iPhone 17, 402 pt wide, scale exactly 3.0) by scanning the PNG for the
/// card background rectangle: the two team cards span x = 3.0…398.7 pt with a
/// 16.0 pt gap, so each card is **190.0 pt** and, after `teamCard`'s
/// `.padding(12)`, each row has **166.0 pt** to spend.
///
/// 80 + 8 + 8 + 70 = **166**. The bar was offered exactly **0.0 pt**, so
/// `max(2, 0 * probability)` returned the 2 pt floor — and the same PNG shows
/// the Brewers' 99.6%, 96.2% and 13.4% rows all drawing an identical 2.00 pt
/// fill at x = 103.0 pt, which is precisely 3 + 12 + 80 + 8. The bar has been
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
/// which hands the bar the width it never had. At 166 pt both a clinched and an
/// ordinary card stack; on iPad and Mac neither does.
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
    static let valueBadgeWidth: CGFloat = 76

    /// The badge column when any row in the card says "clinched".
    ///
    /// Same measurement, plus the checkmark and the word: 89.33 pt at `2.0%`,
    /// 94.00 at `91.3%` — which is the row photographed breaking in #3574,
    /// against a 70 pt column — 95.33 at `99.9%`, and 99.67 at `100.0%`.
    static let clinchedBadgeWidth: CGFloat = 100

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
    static func badgeWidth(for stages: [ProgressionStageData]) -> CGFloat {
        stages.contains { isClinched(probability: $0.probability) }
            ? clinchedBadgeWidth
            : valueBadgeWidth
    }

    /// The width a one-line row needs before its bar starts eating into itself.
    static func inlineRowMinimumWidth(badgeWidth: CGFloat) -> CGFloat {
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

    /// Whether the bar and badges drop below the label instead of sitting beside it.
    ///
    /// A card whose width is not known yet stacks: stacking never wraps a word
    /// and never starves the bar, so it is the safe answer to "not measured".
    static func stacksBelowLabel(contentWidth: CGFloat, stages: [ProgressionStageData]) -> Bool {
        guard contentWidth > 0 else { return true }
        return contentWidth < inlineRowMinimumWidth(badgeWidth: badgeWidth(for: stages))
    }

    /// What the bar actually gets, under the layout the rule chose.
    ///
    /// Exists so a test can assert the number the user sees rather than the
    /// branch that produced it — 0.0 pt was the defect, not "the inline branch".
    static func barWidth(contentWidth: CGFloat, stages: [ProgressionStageData]) -> CGFloat {
        guard contentWidth > 0 else { return 0 }
        let badges = badgeWidth(for: stages)
        if stacksBelowLabel(contentWidth: contentWidth, stages: stages) {
            return max(0, contentWidth - spacing - badges)
        }
        return max(0, contentWidth - labelWidth - spacing - spacing - badges)
    }
}
