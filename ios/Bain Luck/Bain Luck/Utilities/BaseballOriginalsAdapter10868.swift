import SwiftUI

/// #10868 — THE BASEBALL GAME SCREEN'S PRODUCTION ADAPTER, PART FIVE: "ALL
/// PROPS", THE ORIGINAL CATALOGUE AND ITS DETAILS.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on an MLB event page "All props" lists
/// every original market outcome the page serves, once each, in the page's
/// own catalogue order, and each original's Details print its own pregame
/// chance, its own later reading and its own venue grade — or that slot's own
/// words — so an old quote is never sold as today's chance.
///
/// Membership, order, identity, readings, grade and About are the accepted
/// originals adapter's (H4, `HockeyJourneyOriginalsAdapter10868`), CALLED rather
/// than copied: `matched` (`QuestionCatalog9483.build` mapped back to served
/// rows by build's own keys), `original` (the phase's mode, pregame reading,
/// in-game admission with the historical quote in Details, and the
/// after-final grade where unknown is not loss) and `label`. The phase is this
/// screen's own (part one), passed to H4 as the same three phases.
///
/// Two of H4's absence words are said in Design's chance-and-availability
/// words (2026-10-31): "No pregame chance" reads "Pregame chance unavailable",
/// and "No in-game reading" (a quote observed before the start) reads
/// "In-game chance unavailable" — the reason stays the same; neither claims
/// that no such reading exists upstream. Every other field is H4's, unchanged.
///
/// The host passes the event, `/game-markets`, now, the reader's calendar,
/// the tint and its held selection, passed through unchanged for the leaf to
/// resolve by exact scope and identity. Nothing here fetches.
enum BaseballOriginalsAdapter10868 {
    typealias Details = OriginalMarketDetails9483
    typealias H4 = HockeyJourneyOriginalsAdapter10868
    /// H4's host: now and the reader's calendar, time zone and locale.
    typealias Host = HockeyJourneyOriginalsAdapter10868.Host

    enum Words {
        static let heading = "All props"
        static let emptyWords = "No original props recorded for this game"
        static let unavailableChoice = "Unnamed original"
        static let pregameUnavailable = "Pregame chance unavailable"
        static let inGameUnavailable = "In-game chance unavailable"

        static func context(_ count: Int) -> String {
            count == 1 ? "1 original" : "\(count) originals"
        }
    }

    // MARK: - The page's originals

    /// The originals group for the page at `host.now`. No served outcome is no
    /// catalogue, which draws `emptyWords`. `/game-markets` for another event
    /// is no catalogue.
    static func originals(_ event: EventDetail, markets: GameMarketsResponse?, host: Host, tint: Color,
                          selection: Details.Selection? = nil) -> BaseballEventPageOriginals10868 {
        let phase = BaseballGamePageAdapter10868.phase(event, now: host.now)
        let started = HockeyJourneyContributionAdapter10868.hasStarted(event, now: host.now)
        let served = markets.flatMap { $0.eventId == event.id ? $0 : nil }
        let found = served.map { H4.matched($0, status: event.status, now: host.now) } ?? []
        let built = found.map {
            reworded(H4.original($0, event: event, phase: BaseballHistoryAdapter10868.h2Phase(phase),
                                 started: started, host: host))
        }
        var labels: [Details.Identity: String] = [:]
        for (match, made) in zip(found, built) {
            labels[made.identity] = H4.label(match.source, event: event)
        }
        return BaseballEventPageOriginals10868(
            catalogue: built.isEmpty ? nil : Details.Catalogue(scope: scope(event, phase: phase), originals: built),
            selection: selection,
            labels: labels,
            heading: Words.heading,
            context: built.isEmpty ? nil : Words.context(built.count),
            emptyWords: Words.emptyWords,
            unavailableChoice: Words.unavailableChoice,
            tint: tint)
    }

    /// One catalogue per event and phase.
    static func scope(_ event: EventDetail, phase: BaseballEventPagePhase10868) -> String {
        "mlb:\(event.id):\(phase):originals"
    }

    /// H4's original with its two absence words said in Design's words; every
    /// other field unchanged.
    static func reworded(_ original: Details.Original) -> Details.Original {
        let pregame = original.pregame == Details.Reading.missing(H4.Words.noPregameChance)
            ? Details.Reading.missing(Words.pregameUnavailable) : original.pregame
        let later = original.later == Details.Reading.missing(H4.Words.noInGameReading)
            ? Details.Reading.missing(Words.inGameUnavailable) : original.later
        return Details.Original(
            identity: original.identity, title: original.title, outcome: original.outcome,
            mode: original.mode, pregame: pregame, later: later, grade: original.grade,
            about: original.about, beforeLabel: original.beforeLabel)
    }
}
