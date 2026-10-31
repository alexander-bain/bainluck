import SwiftUI

/// #10868 — THE CRICKET TEST-MATCH SCREEN'S PRODUCTION ADAPTER, PART THREE:
/// THE ORIGINAL MARKETS ("ALL N ORIGINAL MARKETS") AND THEIR DETAILS.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on `cricket-live` the originals panel and
/// the full catalogue list every original market outcome the page holds, once
/// each, in the page's own catalogue order, and each original's Details print
/// its own pregame chance, its own later reading or its own venue grade — or
/// that slot's own words — never an old price as today's, never a settled 0% or
/// 100% as a chance.
///
/// It decides nothing new. Every rule is the hockey candidate's reviewed
/// originals rule (`HockeyJourneyOriginalsAdapter10868`, source-accepted by
/// Design after H4's currentness correction), reused rather than restated, so a
/// cricket original and a hockey original are read by one rule:
///
///   - membership, order  `Rules.matched` — `QuestionCatalog9483.build`, the one
///                        catalogue the page already draws, mapped back to each
///                        served row by build's own keys.
///   - one original       `Rules.original` — identity from served ids (never a
///                        ticker, a label or a position); before the start the
///                        catalogue's own recent price; during play an in-game
///                        reading only when dated, after the listed start and
///                        recent, else that rule's words with the refused quote
///                        kept as the Details' historical quote; after the final
///                        the contract's own grade (`OutcomeVerdict`), unknown is
///                        "Not yet confirmed", never a loss.
///   - labels             `Rules.label`.
///
/// What this file adds is only the cricket scope and words. On every retained
/// cricket `/game-markets` body the catalogue is EMPTY (every section `[]`), so
/// the panel says `Words.emptyWords` — availability words, never a claim that
/// no original market exists (the page may simply hold none for this match).
///
/// The host passes the event, `/game-markets`, now, the reader's calendar, the
/// tint and its held selection, which reaches the leaf unchanged. Nothing here
/// fetches.
enum CricketOriginalsAdapter10868 {
    typealias Details = OriginalMarketDetails9483
    typealias Rules = HockeyJourneyOriginalsAdapter10868
    typealias Page = CricketEventPageAdapter10868

    enum Words {
        static let emptyWords = "Original markets unavailable for this match"
        static let unavailableChoice = "Unnamed original"

        /// "All 3 original markets", the reference's heading; "1 original market".
        static func heading(_ count: Int) -> String {
            count == 1 ? "1 original market" : "All \(count) original markets"
        }

        static func context(_ count: Int) -> String {
            count == 1 ? "1 original market outcome" : "\(count) original market outcomes"
        }

        static let headingWithoutCount = "Original markets"
    }

    // MARK: - The page's originals

    /// The originals group for the page at `host.now`. No served outcome is no
    /// catalogue, which draws `emptyWords`.
    static func originals(_ event: EventDetail, markets: GameMarketsResponse?, host: Rules.Host, tint: Color,
                          selection: Details.Selection? = nil) -> CricketEventPageOriginals10868 {
        let pagePhase = Page.phase(event, now: host.now)
        let started = HockeyJourneyContributionAdapter10868.hasStarted(event, now: host.now)
        let found = markets.map { Rules.matched($0, status: event.status, now: host.now) } ?? []
        var built: [Details.Original] = []
        var labels: [Details.Identity: String] = [:]
        for match in found {
            let made = Rules.original(match, event: event, phase: CricketHistoryAdapter10868.rulesPhase(pagePhase),
                                      started: started, host: host)
            built.append(made)
            labels[made.identity] = Rules.label(match.source, event: event)
        }
        let catalogue: Details.Catalogue? = built.isEmpty
            ? nil : Details.Catalogue(scope: scope(event, phase: pagePhase), originals: built)
        return CricketEventPageOriginals10868(
            catalogue: catalogue,
            selection: selection,
            recorded: nil,
            labels: labels,
            heading: built.isEmpty ? Words.headingWithoutCount : Words.heading(built.count),
            context: built.isEmpty ? nil : Words.context(built.count),
            emptyWords: Words.emptyWords,
            unavailableChoice: Words.unavailableChoice,
            tint: tint)
    }

    /// One catalogue per event and phase.
    static func scope(_ event: EventDetail, phase: CricketHeadlinePhase10868) -> String {
        "cricket:\(event.id):\(Page.phaseWord(phase)):originals"
    }
}
