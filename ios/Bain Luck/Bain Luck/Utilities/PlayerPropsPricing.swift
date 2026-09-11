import Foundation

/// Whether a Player Props stat group is showing a price at all.
///
/// #5137 — A FINISHED GAME PRINTS A COIN FLIP ON EVERY RUNG. Photographed on
/// `bainluck://events/15308637` (TB 1 – ATL 3, hours after the final):
///
///     NICK MARTINEZ   Away
///     EARNED RUNS   chance of hitting
///       1+  ██████████  50%
///       2+  ██████████  50%
///       3+  ██████████  50%
///       4+  ██████████  50%
///       5+  ██████████  50%
///       6+  ██████████  50%
///
/// 🔴 AN ALL-EQUAL LADDER IS NOT A PRICE. These rungs are cumulative — the
/// market's own question is "at least N", so P(≥1) ≥ P(≥2) ≥ … and any two
/// adjacent rungs can only be equal if the stat can never land between them.
/// Six identical bars say "6+ earned runs is exactly as likely as 1+", which is
/// not a claim any market made. It is a placeholder wearing a probability, and
/// under the blend doctrine that is a truth defect, not a cosmetic one.
///
/// It survives because it is monotone. `_enforce_monotonicity`
/// (`backend/app/routes/events.py`) requires non-increasing, and flat satisfies
/// that, so nothing upstream treats the row as suspect. **Equality across every
/// rung is the signal, and it has to be read at the ladder, not the rung.**
///
/// Measured on production before choosing the rule — 40 finished events,
/// 2026-09-11, mirroring this card's own grouping (colon-split outcome name,
/// grouped by served `market_name`):
///
/// | | |
/// |---|---|
/// | player cards | 627 |
/// | stat ladders | 2,353 |
/// | rungs rendered | 4,864 |
/// | **ladders fully flat** | **116 (4.9%)** |
/// | **rungs carrying that non-price** | **286 (5.9%)** |
/// | cards whose *untapped* group is flat | 52 (8.3%) |
/// | cards carrying any flat ladder at all | 108 |
/// | cards where every group is flat | 4 |
///
/// Every one is Kalshi. Two distinct upstream shapes produce it and neither is
/// fixable here: a rung with no usable book stores a literal `0.5` (Martinez's
/// six rungs each carry a different bid/ask, and 0.5 is not the midpoint of any
/// of them), and a stale one-quote book replicates a single wide midpoint across
/// the whole ladder (Gausman's six rungs all read bid 0.60 / ask 1.00 → 0.80).
/// The serving half is #5137's other half and is not iOS's file; what the app
/// owes the reader is to stop printing the number as a probability.
///
/// **203 of those 286 rungs are graded** — the server knows how the stat
/// finished and whether the rung hit. So the ladder is hidden, never deleted:
/// D102's shape (a collapsed "Unpriced props (N)" toggle) keeps the true half —
/// the final value and the ✓/– verdict — one tap away, and drops only the bar
/// and the percentage, which are the parts that are not true.
///
/// The test is on the **displayed** percentage, because that is the claim the
/// reader is being handed: two rungs that differ in the fourth decimal draw
/// indistinguishable bars and print the same "5%". On the 1,364 live multi-rung
/// ladders measured the displayed test and exact-equality of the raw doubles
/// selected **the same 116 ladders**, so this choice costs nothing today and is
/// the one that stays correct if the rounding ever changes.
enum PlayerPropsPricing {

    /// The whole-percent number the rung prints, and the only part of a
    /// probability a reader can actually compare between two rungs.
    ///
    /// Kept here rather than in the view so the rule and the label round the
    /// same way by construction: a ladder judged flat is exactly a ladder whose
    /// printed percentages are all the same string.
    static func displayPercent(_ probability: Double) -> Int {
        Int((probability * 100).rounded())
    }

    /// Is this ladder showing a price?
    ///
    /// A ladder of two or more rungs whose printed percentages are all equal is
    /// not — see the type's note. Everything else is, including:
    ///
    /// - **a single rung**, which makes no claim about a shape. A lone 50% may
    ///   well be the same placeholder, but nothing on the row distinguishes it
    ///   from a genuine coin flip, and inventing that verdict would hide real
    ///   prices. Fail open where the evidence stops, the same way
    ///   ``PlayerPropsCardView/actualStatValue(player:stat:box:)`` fails closed
    ///   where a grade would have to be guessed.
    /// - **a near-flat ladder** (5%, 5%, 4%). It is a weak price, not an absent
    ///   one, and the reader can see it decline.
    /// - **an empty ladder**, which the card never builds.
    static func isPricedLadder(_ probabilities: [Double]) -> Bool {
        guard probabilities.count >= 2 else { return true }
        return Set(probabilities.map(displayPercent)).count > 1
    }
}
