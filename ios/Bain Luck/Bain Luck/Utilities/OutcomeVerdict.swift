import Foundation

/// Has a venue already CALLED this futures leg — and is that call allowed to
/// stand on the row we are drawing?
///
/// #8640. The native twin of web's `outcomeRowVerdict`
/// (`frontend/components/futures/OutcomeRow.tsx`) and of
/// `AUTHORITATIVE_RESOLUTION_SOURCES` (`frontend/lib/resolutionAuthority.ts`).
/// Read those for the long WHY; the short version is below, clause by clause.
/// `OutcomeVerdictParityTests` READS both web files and asserts the constants
/// here match them, so this is not a second copy agreed by hand.
///
/// Production 2026-09-25, `/api/events/search?q=Fed chair`: the family card led
/// with "Who will be confirmed as Fed chair — Kevin Warsh >99%" over a leg served
/// `is_winner: true, resolution_source: "api_settlement"` on a market still
/// `open`. A settled question printed as a live one. The web half answered it
/// with this rule; the phone printed the price until this file.
///
/// Kept free of SwiftUI so the decision is unit-testable.
enum OutcomeVerdict: String, Sendable {
    case won
    case lost

    /// The `resolution_source` values that are a venue's own settlement (tier 3
    /// in `backend/app/utils/resolution_authority.py`).
    static let authoritativeResolutionSources: Set<String> = [
        "api_settlement",
        "clob_authoritative",
        "clob_field_repair",
        "clob_never_graded",
        "clob_ordinal",
        "datagolf_settlement",
        "settlement_sync",
    ]

    /// The one `resolution_source` that is a RETRACTION, not a grade (CAL-P056):
    /// it takes a fabricated loss out and asserts no winner.
    static let retractedResolutionSource = "ungradeable_result"

    static func isAuthoritative(_ source: String?) -> Bool {
        guard let source else { return false }
        return authoritativeResolutionSources.contains(source)
    }

    /// `nil` means "print the price", which is also what an ungraded leg prints.
    ///
    /// - `marketResolved`: `market.status == "resolved"`, a MARKET-level fact.
    ///
    /// One deliberate divergence from web, and it is in web's own direction:
    /// web keeps an ABSENT `resolution_source` (a payload from before #8648)
    /// apart from a served `null`, because on web absent falls back to trusting
    /// `is_winner`. `Decodable` folds both into `nil` here, and `nil` withholds
    /// — which on this client is exactly the behaviour before this rule existed.
    static func verdict(
        isWinner: Bool?,
        resolutionSource: String?,
        marketResolved: Bool
    ) -> OutcomeVerdict? {
        // A retraction is refused first and in both directions: a row that is
        // both retracted and crowned is a contradiction, and the honest render
        // for a contradiction is the live one.
        guard let resolutionSource, resolutionSource != retractedResolutionSource else {
            return nil
        }
        guard let isWinner else { return nil }
        // #6082: an OPEN market can hold a genuinely settled leg (a threshold
        // ladder mid-season, a confirmation the venue called before it closed
        // the market). Only the WON arm crosses that line, and only on a
        // venue's own settlement: `is_winner` defaults to FALSE, so on an open
        // market a false is indistinguishable from "nobody graded it yet".
        guard marketResolved else {
            return isWinner && isAuthoritative(resolutionSource) ? .won : nil
        }
        return isWinner ? .won : .lost
    }

    /// The word a row prints in place of its percentage.
    var label: String {
        switch self {
        case .won: return "Won"
        case .lost: return "Lost"
        }
    }
}
