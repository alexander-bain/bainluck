import SwiftUI

/// #10868 — THE SOCCER MATCH SCREEN'S PRODUCTION ADAPTER, PART SEVEN: HALF BY
/// HALF.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: the half-by-half card keeps each original
/// half result outcome's own pre-match chance for its half, plotted on one
/// scale, and pairs each with its own in-play chance or result — one half
/// never lends another a chance, a state or a result.
///
/// Rules, each an existing owner's:
///
///   - periods       the owner's admitted half markets, in period order, each
///                   with the owner's period identity and words
///                   (`SoccerPropReadingAdapter10868.Markets.halves`). Nothing
///                   here reads a market title to find a half.
///   - series        by the side the SERVER proved on the matrix option
///                   (`QuestionMatrixOption.side`: `home`, `draw`, `away`); a row
///                   with no proved side joins no series — it stays reachable in
///                   All props. Series order home, Draw, away; one cell per
///                   period, by the period's exact identity.
///   - readings      part three's rules (`SoccerPropReadingAdapter10868`). During
///                   play each half's later slot is `periodCurrent`: no decoded
///                   field proves a half is still being played, so a half's quote
///                   is never its current chance — a dated quote shows only as
///                   that dated recorded quote (`.stale`), and the result stays
///                   the venue's grade, else unknown (Design, wave-1 review).
///   - names, tints  `TeamShortName.shortPair`, `TeamTextContrast.cardColors`;
///                   Draw takes the page's neutral `DS.textSecondary`.
///   - axis          the fixed 0–100% scale, scale words not chances.
///
/// This file stays reusable in every phase. WHERE the card is offered is the
/// page's: by default only after the final, the approved route-phase
/// membership (`SoccerPageInputAdapter10868.HalvesAdmission`); the journey and
/// replay hosts admit it explicitly.
enum SoccerHalvesAdapter10868 {
    typealias R = SoccerPropReadingAdapter10868

    enum Words {
        static let eyebrow = "Half-by-half expectations"
        static let title = "Two halves, two sets of expectations"
        static let plotTitle = "Pre-match chances"
        static let scaleCaption = "0–100% scale"
        static let pointExplanation = "Each dot is a pre-match chance for that half."
        static let lineExplanation = "Lines compare halves, not changes over time."
        static let draw = "Draw"
        static let liveResults = "Results so far"
        static let finalResults = "Final results"
    }

    static let words = PeriodOutcomeWords10868(
        pregameTitle: "Pre-match chance", notStarted: R.Words.notStarted, currentTitle: "Current chance",
        liveResultTitle: "Half result", finalResultTitle: "Final result",
        selectionUnavailable: "Selected outcome unavailable.", cellUnavailable: "Chance unavailable for this half",
        selectHint: "Shows this outcome’s chances", detailsHint: "Opens the original prop")

    static let axis = PeriodOutcomeAxis10868(lower: 0, upper: 1, ticks: [
        PeriodOutcomeTick10868(value: 0, text: "0%"),
        PeriodOutcomeTick10868(value: 0.5, text: "50%"),
        PeriodOutcomeTick10868(value: 1, text: "100%"),
    ])

    /// The three sides a series may be, in the card's order.
    static let sides = ["home", "draw", "away"]

    /// The card, or nil when no admitted half serves an original with a proved side.
    static func input(_ event: EventDetail, markets: GameMarketsResponse?, admitted: [R.Markets.Half],
                      host: R.Host, selectedSeriesID: String? = nil) -> PeriodOutcomeComparisonInput10868? {
        guard !admitted.isEmpty else { return nil }
        let phase = SoccerMatchPageAdapter10868.phase(event, now: host.now)
        let names = SoccerMatchPageAdapter10868.names(event)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let byHalf = admitted.map { (half: $0, legs: R.legs($0.marketID, in: markets)) }
        var series: [PeriodOutcomeSeries10868] = []
        for side in sides {
            let cells: [PeriodOutcomeCell10868] = byHalf.compactMap { entry in
                let matching = entry.legs.filter { $0.option?.side == side }
                guard matching.count == 1, let leg = matching.first else { return nil }
                return cell(leg, half: entry.half, event: event, phase: phase, host: host)
            }
            guard !cells.isEmpty else { continue }
            series.append(PeriodOutcomeSeries10868(
                id: side, label: label(side, names: names), tint: tint(side, tints: tints),
                symbol: symbol(side), cells: cells))
        }
        guard !series.isEmpty else { return nil }
        let chosen = selectedSeriesID ?? series.first?.id
        let chosenLabel = series.first { $0.id == chosen }?.label
        let resultsTitle: String? = switch phase {
        case .before: nil
        case .live: chosenLabel.map { "\(Words.liveResults) · \($0)" }
        case .final: chosenLabel.map { "\(Words.finalResults) · \($0)" }
        }
        return PeriodOutcomeComparisonInput10868(
            phase: phase.periodPhase,
            eyebrow: Words.eyebrow,
            title: Words.title,
            intro: nil,
            periods: admitted.map { PeriodOutcomePeriod10868(id: $0.periodID, label: $0.label) },
            series: series,
            selectedSeriesID: chosen,
            plotTitle: Words.plotTitle,
            scaleCaption: Words.scaleCaption,
            axis: axis,
            pointExplanation: Words.pointExplanation,
            lineExplanation: Words.lineExplanation,
            resultsTitle: resultsTitle,
            words: words)
    }

    static func cell(_ leg: R.Leg, half: R.Markets.Half, event: EventDetail, phase: SoccerEventPagePhase10868,
                     host: R.Host) -> PeriodOutcomeCell10868 {
        let before = R.pregame(leg, event: event, host: host)
        let current: PeriodOutcomeCurrent10868
        if phase == .live {
            switch R.periodCurrent(leg, event: event, host: host) {
            case .recorded(let o): current = .recorded(observation(o))
            case .withheld(let words): current = .stale(words)
            case .unavailable(let words): current = .unavailable(words)
            }
        } else {
            current = .unavailable(R.Words.inPlayUnavailable)
        }
        let result: PeriodOutcomeResult10868
        switch phase == .before ? R.Result.unconfirmed(R.Words.resultUnavailable) : R.result(leg) {
        case .won(let words): result = .won(words)
        case .lost(let words): result = .lost(words)
        case .unconfirmed(let words): result = .unconfirmed(words)
        }
        return PeriodOutcomeCell10868(id: "\(half.marketID):\(leg.id)", periodID: half.periodID,
                                      pregame: before.observation.map { Self.observation($0) },
                                      pregameMissing: before.words, current: current, result: result)
    }

    static func observation(_ o: R.Observation) -> PeriodOutcomeObservation10868 {
        PeriodOutcomeObservation10868(probability: o.probability, text: o.text, accessibilityDetail: o.detail)
    }

    static func label(_ side: String, names: (away: String, home: String)) -> String {
        switch side {
        case "home": names.home
        case "away": names.away
        default: Words.draw
        }
    }

    static func tint(_ side: String, tints: (away: Color, home: Color)) -> Color {
        switch side {
        case "home": tints.home
        case "away": tints.away
        default: DS.textSecondary
        }
    }

    static func symbol(_ side: String) -> PeriodOutcomeSymbol10868 {
        switch side {
        case "home": .circle
        case "away": .diamond
        default: .square
        }
    }
}
