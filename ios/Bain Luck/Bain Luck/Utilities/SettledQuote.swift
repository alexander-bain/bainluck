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

    /// The section-level sentence for a settled section that shows a number,
    /// said once per section.
    ///
    /// #3752 moved it off "showing each market's last quote". Web renders a
    /// decided row as its RESULT (`Shelton won Set 1`) with no number at all,
    /// so "each" was false for 6 of 6 rows on `/events/15305016`. Native does
    /// not have that treatment yet — every row here still prints a quote when
    /// the game is finished, so the old wording was not false ON THIS RUNTIME —
    /// but the phrase is one string across both by construction
    /// (`SettledQuoteParityTests`), and the new wording is true in both.
    ///
    /// Web's companion `SETTLED_SECTION_NOTE_NO_QUOTES` ("settled", used when
    /// nothing under the header shows a percentage) has NO twin here on
    /// purpose: this view cannot reach that state, and an unused constant would
    /// be a claim that it can. Filed as the native gap: see #3752's thread.
    static let sectionNote = "settled — any percentage is a last quote"

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
