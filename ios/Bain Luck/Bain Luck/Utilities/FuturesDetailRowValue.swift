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
    /// #698: the market is settled but this row's result is not known
    /// (`SettledResultDisplay698`). "Result unknown", plus "Last recorded N%"
    /// for a finite price — never a live bar, a move, or a Won/Lost.
    case resultUnknown(lastRecorded: Double?)

    /// `marketSource` lets the #698 fallback run for a resolved Polymarket
    /// market whose server predates `settlement_display`; a served contract
    /// applies without it.
    static func of(_ outcome: FuturesOutcome, marketStatus: String?, marketSource: String? = nil) -> Self {
        switch SettledResultDisplay698.certainty(outcome, marketSource: marketSource, marketStatus: marketStatus) {
        case .won: return .verdict(.won)
        case .lost: return .verdict(.lost)
        case .unknown:
            // An explicit unknown never falls through to the sourced-false Lost.
            let last = outcome.probability.flatMap { $0.isFinite ? $0 : nil }
            return .resultUnknown(lastRecorded: last)
        case nil:
            break
        }
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
        switch self {
        case .verdict, .resultUnknown: return false
        case .price, .none: return true
        }
    }
}
