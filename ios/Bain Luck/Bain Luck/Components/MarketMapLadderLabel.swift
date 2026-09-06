import SwiftUI

/// One row's name in a market map's probability ladder — `SWI +1.5`,
/// `LAR +2.5`, `Over 42.5` — and the width of the column they all share.
///
/// #3533/#3552, caught on the LOOK of the fix rather than by any test. The
/// ladder printed its lines through `Int(abs(margin))`, so a `-5.5` game line
/// read `+5` and a `-1.5` SET handicap read `+1` — a two-set handicap
/// relabelled as a one-set one, which is a different market. Printing the real
/// line fixed that and immediately overflowed the column it is printed in: the
/// live Sabalenka–Townsend card came back reading **`Townsend…  60%`**, the
/// line gone entirely.
///
/// The column was a bare `.frame(width: 82)` — a fixed width nothing measured,
/// which is the class native/039 found on `ChampionshipStageBadges` the day
/// before. So this is extracted for the same reason: a test can host it and ask
/// what width it actually wants, instead of a comment claiming a number is
/// right.
struct MarketMapLadderLabel: View {
    let text: String
    let color: Color

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(color)
                .frame(width: 5, height: 5)
            Text(text)
                .font(.system(size: 10, weight: .heavy))
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
    }
}

enum MarketMapLadderLayout {
    /// How much room the label column offers.
    ///
    /// **Measured, and here is the thing that measured it:**
    /// `MarketMapLadderTests.testTheColumnHoldsTheWidestLabelProductionServes`
    /// hosts ``MarketMapLadderLabel`` with every label the US Open and NFL
    /// cards actually build and fails if any of them wants more than this. Run
    /// against a deliberately tiny constant it reports the answer: the widest
    /// is `Zandschulp +1.5` at **96.7 pt**, against the 82 pt the column used
    /// to offer. 104 is that, with room for a longer surname.
    ///
    /// It is a fixed width rather than a per-card fit on purpose: every row's
    /// bar must start at the same x, or the ladder stops being comparable
    /// down its own column, which is the only thing a ladder is for.
    static let labelColumnWidth: CGFloat = 104

    /// What the bar is left with, and the reason the column above is capped by
    /// judgement rather than allowed to grow to fit anything.
    ///
    /// The row is `label + 8 + bar + 8 + value(32)` inside a card that is
    /// ~338 pt wide on a 402 pt phone, so the bar gets ~186 pt at the width
    /// above. The bar is the data; a column that swallowed it to spell out a
    /// long name would be trading the measurement for its caption.
    static let smallestPhoneCardWidth: CGFloat = 338
    static let valueColumnWidth: CGFloat = 32
    static let rowSpacing: CGFloat = 8

    /// The bar's width on the narrowest card the app draws.
    static var barWidthOnSmallestCard: CGFloat {
        smallestPhoneCardWidth - labelColumnWidth - valueColumnWidth - rowSpacing * 2
    }
}
