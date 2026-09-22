import SwiftUI

/// One row's name in a market map's probability ladder — `SWI by 1.5+`,
/// `LAR by 2.5+`, `Over 42.5` — and the width of the column they all share.
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
    /// is `Zandschulp by 1.5+` at **112.3 pt**. 118 is that, with room for a
    /// slightly longer surname.
    ///
    /// It is a fixed width rather than a per-card fit on purpose: every row's
    /// bar must start at the same x, or the ladder stops being comparable
    /// down its own column, which is the only thing a ladder is for.
    ///
    /// 🔴 **#7905 SPENT THIS COLUMN'S HEADROOM, AND THAT IS THE PRICE OF THE
    /// RULING.** The labels used to read `Zandschulp +1.5` and wanted 96.7 pt
    /// against the 104 offered. Porting #2442's `by N+` to the phone adds three
    /// characters to every margin rung, so the same population now wants
    /// 112.3 — which is why #3743 declined to ride the notation change and left
    /// it for its own decision. The feasible window is narrow and both ends are
    /// measured: **at least 112.3** or the row silently eats the line it exists
    /// to name, and **under 120** or ``barWidthOnSmallestCard`` stops clearing
    /// the 170 pt floor below (half of a 338 pt card is 169). 118 sits inside
    /// it; by this constant's arithmetic the bar goes from 186 pt to 172 pt and
    /// keeps 50.9% of the row.
    ///
    /// 🟢 **Photographed, not only computed.** `artifacts-native-020/AFTER-7905-se2.png`
    /// — the same live card on an iPhone SE (3rd gen), the narrowest phone the
    /// app runs on — draws all six rungs of event 14780545 at the new width with
    /// nothing truncated and the bar still the larger half of the row. Worth
    /// knowing while you are here: ``smallestPhoneCardWidth`` is the card's
    /// OUTER width, so the real track on that render measures ~150 pt rather
    /// than the 172 the subtraction above implies. The number is a comparator
    /// between the two ends of this window, which is all the floor below asks of
    /// it — not a claim about a measured track.
    ///
    /// If a future grammar needs more than this, the column is not the thing to
    /// grow — the bar is already the smaller half of the trade. Shorten the
    /// label or scale the type, and measure it here.
    static let labelColumnWidth: CGFloat = 118

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
