import Foundation

/// When the prices a futures surface is drawing were last written — the native
/// half of #6018.
///
/// `FuturesDetailView`'s metadata card has printed an "Updated" stamp for as
/// long as it has existed, and it fed that stamp `market.updated_at`. That
/// column is the moment the MARKET ROW was touched. Prices live one table down,
/// in `futures_outcomes.last_updated`, and a different set of passes writes
/// them: metadata/tier/volume/image work bumps the row without moving a price,
/// and the pollers move prices on rows whose metadata has not changed in
/// months. So the stamp has never been about the numbers beneath it.
///
/// The web twin reached the same finding first and shipped it in
/// `frontend/lib/futuresCardPriceAge.ts`; `components/FuturesCard.tsx` has
/// rendered the price floor since. This file is the half that was never built,
/// so the two tiers answered "how fresh is this?" with two different clocks.
///
/// MEASURED ON PRODUCTION, 2026-09-16 08:4xZ, `/api/futures/{id}` — wrong in
/// BOTH directions, the same way #6018 measured it on the web:
///
///   * 55686530 "Caribbean Premier League Champion" — row stamped Sep 13 00:53Z,
///     every one of its seven prices rewritten Sep 16 05:51Z. The page said
///     **"Updated Sep 12 at 5:53 PM"** over numbers three days newer than that.
///   * 363922 "NASCAR O'Reilly Auto Parts Series Champion" — row Sep 11 20:50Z,
///     all forty prices Sep 16 07:50Z: **4.8 days** of understatement.
///   * 109435 "Will the U.S. confirm that aliens exist?" — the other direction.
///     Row touched Sep 16 06:30Z, two hours before the shot, while a rung the
///     page draws had not moved since **Sep 7 08:50Z**. The stamp vouched for a
///     nine-day-old price.
///
/// ## THE FLOOR, NOT THE CEILING
///
/// One stamp above a ladder is read as covering the whole ladder, so the only
/// honest claim is the oldest row the page can show: *nothing you can see here
/// is older than this*. Taking the newest would let one refreshed favourite
/// vouch for a frozen tail — the flattering half of the very defect this
/// replaces, and what market 109435 already does today.
///
/// ## WHY THE WHOLE OUTCOME SET AND NOT THE FIRST 25
///
/// The web helper scopes to the rows its card draws, because a card draws a
/// fixed `top_outcomes`. The detail page has no such boundary: `outcomesSection`
/// shows 25 and "Show all N" reveals the rest of the SAME list, in place,
/// without leaving the page. A stamp that jumped older when a reader tapped
/// Show-all would be reporting the disclosure, not the data. So the claim is
/// scoped to everything the page can show — stable, and never flattering.
///
/// `nil` means "this payload cannot say", and the caller renders NOTHING then
/// rather than falling back to `updated_at`. An empty row claims nothing; the
/// old stamp claimed something false (Alex, standing notice 34: if a number
/// cannot be shown honestly, leave the space empty).
enum FuturesPriceAge {
    /// The oldest parseable stamp in `stamps`, or `nil` if none parses.
    ///
    /// Takes strings rather than outcomes so the rule is testable as a rule —
    /// the ordering, the unparseable-row skip and the empty case are what break,
    /// and none of them needs a decoded model to exercise.
    static func oldestStamp(_ stamps: [String?]) -> Date? {
        var oldest: Date?
        for stamp in stamps {
            guard let stamp, let date = stamp.asDate else { continue }
            if oldest == nil || date < oldest! { oldest = date }
        }
        return oldest
    }

    /// When the prices on a futures detail page were last written, or `nil`.
    static func pricesAsOf(_ outcomes: [FuturesOutcome]) -> Date? {
        oldestStamp(outcomes.map(\.lastUpdated))
    }
}
