import Foundation

/// What one Market Details outcome row prints in its value slot.
///
/// #10964. `bainluck://futures/54069274` "Boston vs Detroit: Team Total"
/// (Kalshi, resolved; Boston 10, Detroit 3), production 2026-10-12: every leg is
/// served with a grade (`is_winner`, `resolution_source: "game_score"`), yet the
/// row printed only its last quote. The nine winners read `✓ >99%`, Detroit
/// over 3.5/7.5 read `1%` — a live chance on a question already answered — and
/// Detroit over 4.5/5.5/6.5 (price null) printed nothing at all. The event page
/// prints Won/Lost for the same rows.
///
/// `OutcomeVerdict.verdict` IS the rule and is not re-derived here: a retracted
/// or missing `resolution_source` withholds, a null `is_winner` withholds, and
/// on an OPEN market only an authoritative `won` crosses (#6082). A row the rule
/// will not grade prints exactly what it printed before this file.
///
/// Kept free of SwiftUI so the decision is unit-testable.
enum FuturesDetailRowValue: Equatable, Sendable {
    /// The question is answered and the settlement rail says so: `Won` / `Lost`
    /// in the slot the price would take, no bar, no movement.
    case verdict(OutcomeVerdict)
    /// A live (or ungraded) row: the percentage and its bar.
    case price(Double)
    /// No grade and no price: the name and nothing else (notice 34).
    case none

    static func of(_ outcome: FuturesOutcome, marketStatus: String?) -> Self {
        if let verdict = OutcomeVerdict.verdict(
            isWinner: outcome.isWinner,
            resolutionSource: outcome.resolutionSource,
            marketResolved: marketStatus == "resolved"
        ) {
            return .verdict(verdict)
        }
        if let probability = outcome.probability { return .price(probability) }
        return .none
    }

    /// A settled row prints its result, never a 24h move or a "from" opening —
    /// web's `outcomeRowPrintsMove`, verdict arm.
    var printsMovement: Bool {
        if case .verdict = self { return false }
        return true
    }
}
