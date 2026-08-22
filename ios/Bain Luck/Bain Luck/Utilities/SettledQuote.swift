import Foundation

/// The settled-quote words on native, and the settled-status list they key off.
///
/// UX-P115 (#2086). The twin of `frontend/lib/settledQuote.ts`. Read that file
/// for WHY these phrases are not verdict words — the short version is that the
/// grade for these rows exists and is authoritative (`api_settlement`) but is
/// not carried on the game-markets payload, so claiming "grading unavailable"
/// would be false, and the honest thing a client can say is what the NUMBER is.
///
/// ** THESE ARE TWO CONSTANTS THE MOMENT ONE IS EDITED. ** A phrase living in
/// TypeScript and Swift is the #1620 shape, twelve instances and counting, and
/// #1650 is the same defect wearing a user-visible face: one backend state
/// wearing several vocabularies on one screen. So `SettledQuoteParityTests`
/// READS `frontend/lib/settledQuote.ts` and asserts these values match it
/// character for character. Parity is mechanical here, not trusted.
enum SettledQuote {
    /// Prefix for a frozen price on a finished game: "last quote 99%".
    static let prefix = "last quote"

    /// The section-level sentence, said once per section.
    static let sectionNote = "settled — showing each market's last quote"

    /// Spelled as web's `propDivergence.isSettledStatus` spells it. Wider than
    /// the `completed`/`closed` pair native used to hard-code, and in practice
    /// a no-op on real data — production `events.status` only ever holds
    /// `scheduled` / `live` / `completed` / `closed` / `voided` (measured over
    /// 30 days, 2026-08-21) — so the widening cannot suppress anything today.
    /// It exists so the two runtimes cannot disagree about a status one of them
    /// starts receiving later.
    static let settledStatuses: Set<String> = ["completed", "closed", "settled", "final", "resolved"]

    static func isSettled(_ status: String?) -> Bool {
        settledStatuses.contains((status ?? "").lowercased())
    }
}
