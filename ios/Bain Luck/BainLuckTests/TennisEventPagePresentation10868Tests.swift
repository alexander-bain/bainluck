import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the tennis match screen (`tennis`, `tennis-live`, `tennis-final`)
/// as a composition of the accepted leaves before, during and after a match.
///
/// What is asserted is the composition the screen defers to: which actual leaf
/// each phase mounts and with which exact owner input, the phase and variant
/// guards (final totals / final exact tiles after the match only; threshold
/// totals / exact lanes before and during play only), the story links, the hold
/// ordering of stream cards, disclosure writes and page actions, the full-size
/// history and its dated reading, the held reading on the page, the About, All
/// props and Details, and the arrangement candidates. The leaves' own rules are
/// their own tests'. Nothing here claims a compile, a rendered fit beyond the
/// one hosted width measurement, a native runtime or a TestFlight build.
///
/// ARCHIVED values (decoded server bodies, not re-fetched):
/// - `tennis-live`, event 15327807, Arthur Fils vs Botic van de Zandschulp,
///   ATP Shanghai Masters, status `live`, sets 0–1 (`home_score`/`away_score`,
///   `score_observed_at` 2026-10-12T12:20:44Z), hero blend 0.205895 / 0.794105
///   observed 12:23:57Z, opening line 0.7872 / 0.2128
///   (accessible-chart-inspection-v90/raw/tennis-15327807-detail.json). Matrix
///   pins (…-game-markets.json, `game_question_matrix` `comparison.baseline`,
///   basis `pregame_pin`, 10:17:14Z): Set 1 Fils 0.72 / Zandschulp 0.28
///   (245152775 / 245152776); Set Handicap Zandschulp +1.5 0.435 (245152788);
///   Game Spread Zandschulp +4.5 0.55 (245201950). Exact match score outcomes
///   245059338–245059341 carry no pin (`no_pregame_pin`); O/U 22.5 / 23.5
///   (245152784 / 245152786) carry none either (`leg_is_complement`).
/// - `tennis-final`, event 15327291, Alejandro Davidovich Fokina vs Frances
///   Tiafoe, status `completed`, sets 2–1, `hero_settled_result` home, Kalshi
///   pre-match 0.455 / 0.545 rendered 45 / 55
///   (accessible-chart-inspection-v90/raw/tennis-15327291-detail.json). Set 1
///   Fokina won, Set 2 Tiafoe won, exact "Fokina wins 2-1" won, O/U 22.5 Over
///   won, both set handicaps and the +0.5 game spread won for their sides
///   (…-game-markets.json `is_winner`). Its matrix carries no pin, so the final
///   cards here say "Pre-match chance unavailable" except the set and handicap
///   values the accepted leaf tests retain from separately captured histories
///   (sets 50% / 50%, 47.5% / 52.5%; handicaps 67% / 71% / 47%).
///
/// CONSTRUCTED: every display word, clock line, label, tint, scope, action id,
/// About sentence, stream status and reader heading; the BEFORE snapshot (the
/// owner admitting `before` on the live match with only its pre-start pins);
/// the final games count 36 and the 22.5 opening line's words; every
/// foreign-phase, wrong-variant, duplicate and missing-callback case.
@MainActor
final class TennisEventPagePresentation10868Tests: XCTestCase {

    // MARK: Matches

    private struct Match {
        let eventID: String
        let home: String
        let away: String
        let homeCompact: String
        let awayCompact: String
    }

    private static let liveMatch = Match(eventID: "15327807", home: "Arthur Fils", away: "Botic van de Zandschulp",
                                    homeCompact: "Fils", awayCompact: "Zandschulp")
    private static let finalMatch = Match(eventID: "15327291", home: "Alejandro Davidovich Fokina", away: "Frances Tiafoe",
                                     homeCompact: "Fokina", awayCompact: "Tiafoe")

    private static func match(_ phase: TennisEventPagePhase10868) -> Match {
        phase == .final ? finalMatch : liveMatch
    }

    private static let homeTint = Color(red: 0.0, green: 0.36, blue: 0.75)
    private static let awayTint = Color(red: 0.85, green: 0.33, blue: 0.10)

    // MARK: Headline

    private static func ref(_ match: Match, _ side: String) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: "tennis:\(match.eventID):winner", source: "event-hero",
                                     marketID: "\(match.eventID):winner", outcomeID: side)
    }

    private static func reading(_ label: String, _ text: String, _ detail: String) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: label, value: .recorded(text: text, detail: detail))
    }

    private struct Side {
        let key: String
        let name: String
        let compact: String
        let shape: FieldHeadlineKeyShape10868
        let tint: Color
        let before: (Double, String)
        let later: (Double, String)?
        let result: String?
    }

    private static func sides(_ phase: TennisEventPagePhase10868) -> [Side] {
        switch phase {
        case .before:
            // The live match's opening line, as the before hero prints it.
            return [Side(key: "home", name: liveMatch.home, compact: liveMatch.homeCompact, shape: .circle, tint: homeTint,
                         before: (0.7872, "79%"), later: nil, result: nil),
                    Side(key: "away", name: liveMatch.away, compact: liveMatch.awayCompact, shape: .diamond, tint: awayTint,
                         before: (0.2128, "21%"), later: nil, result: nil)]
        case .during:
            return [Side(key: "home", name: liveMatch.home, compact: liveMatch.homeCompact, shape: .circle, tint: homeTint,
                         before: (0.7872, "79%"), later: (0.205895, "21%"), result: nil),
                    Side(key: "away", name: liveMatch.away, compact: liveMatch.awayCompact, shape: .diamond, tint: awayTint,
                         before: (0.2128, "21%"), later: (0.794105, "79%"), result: nil)]
        case .final:
            return [Side(key: "home", name: finalMatch.home, compact: finalMatch.homeCompact, shape: .circle, tint: homeTint,
                         before: (0.455, "45%"), later: nil, result: "Won"),
                    Side(key: "away", name: finalMatch.away, compact: finalMatch.awayCompact, shape: .diamond, tint: awayTint,
                         before: (0.545, "55%"), later: nil, result: "Lost")]
        }
    }

    private static func headlineState(_ phase: TennisEventPagePhase10868) -> FieldHeadlineState10868 {
        switch phase {
        case .before:
            return FieldHeadlineState10868(figure: "Before the match", unit: nil, caption: "Scheduled start",
                                           detail: "Oct 12, 3:55 AM", spoken: "Before the match · Scheduled start · Oct 12, 3:55 AM",
                                           progress: nil)
        case .during:
            return FieldHeadlineState10868(figure: "0–1", unit: "sets", caption: "Live", detail: nil,
                                           spoken: "Sets 0–1 · Live", progress: nil)
        case .final:
            return FieldHeadlineState10868(figure: "2–1", unit: "sets", caption: "Final · Alejandro Davidovich Fokina won",
                                           detail: nil, spoken: "Final · 2–1 sets · Alejandro Davidovich Fokina won",
                                           progress: nil)
        }
    }

    private static func headline(_ phase: TennisEventPagePhase10868,
                                 as headlinePhase: FieldOutlookPhase10868? = nil) -> FieldHeadlineInput10868 {
        let match = Self.match(phase)
        var catalogue: [FieldChooserOriginal10868] = []
        var pairs: [FieldMovementPair10868] = []
        var finishes: [FieldFinishPlace10868] = []
        var slots: [FieldHeadlineSlot10868] = []
        for side in sides(phase) {
            let ref = Self.ref(match, side.key)
            let before = reading("Pre-match chance", side.before.1, "Before the start")
            let later = side.later.map { reading("In-match chance", $0.1, "Recorded Oct 12, 5:23 AM · Bain Luck") }
            let plan: FieldChooserDisplayPlan10868 = later.map { .comparison(before: before, later: $0) } ?? .single(before)
            catalogue.append(FieldChooserOriginal10868(
                ref: ref, name: side.name, plan: plan,
                preview: FieldChooserPreview10868(history: nil, absence: "History in the chart"),
                movement: nil, clock: nil, result: nil, browseStatus: "Pre-match chance", accent: side.tint))
            pairs.append(FieldMovementPair10868(
                ref: ref, before: FieldMovementObservation10868(probability: side.before.0, reading: before),
                later: zip2(side.later, later).map { FieldMovementObservation10868(probability: $0.0.0, reading: $0.1) },
                movement: nil, observation: nil))
            let finish = side.result.map { reading("Match result", $0, "Recorded on the event") }
                ?? FieldChooserReading10868(label: "Match result", value: .missing("Result unavailable"))
            finishes.append(FieldFinishPlace10868(ref: ref, reading: finish))
            slots.append(FieldHeadlineSlot10868(ref: ref, name: side.name, compactName: side.compact, keyShape: side.shape))
        }
        let copy = FieldHeadlineCopy10868(
            eyebrow: "ATP", title: "\(match.home) vs \(match.away)", graphicLabel: "Players’ win chances",
            beforeLabel: "Pre-match chance", recordedLabel: "In-match chance", beforeUnavailable: "Not recorded",
            recordedUnavailable: "No in-match chance", finishLabel: "Match result", finishUnavailable: "Result unavailable",
            empty: "No players in this update", aboutLabel: "About this match",
            aboutHint: "Opens the timing of each chance, the result and sources", openHint: "Opens this player’s history")
        return FieldHeadlineInput10868(
            scope: "tennis:\(match.eventID):winner", catalogue: catalogue, displayed: slots, pairs: pairs,
            finishes: finishes, state: headlineState(phase),
            phase: headlinePhase ?? TennisEventPageModel10868.headlinePhase(phase),
            copy: copy, unavailableWords: "Player unavailable in this update")
    }

    private static func zip2<A, B>(_ a: A?, _ b: B?) -> (A, B)? {
        guard let a, let b else { return nil }
        return (a, b)
    }

    // MARK: History

    private static func history(_ phase: TennisEventPagePhase10868) -> FieldHistoryInput10868 {
        let match = Self.match(phase)
        func series(_ side: String, _ name: String, _ shape: FieldHistoryShape10868, _ tint: Color,
                    _ values: [Double]) -> FieldHistorySeries10868 {
            let id = "blend:\(match.eventID):\(side)"
            let points = values.enumerated().map { index, value in
                FieldHistoryPoint10868(id: "\(id)@\(index)", x: Double(index) * 600, probability: value,
                                       style: index == 0 ? .hollow : .filled)
            }
            return FieldHistorySeries10868(
                id: id, name: name, shape: shape, tint: tint,
                runs: [FieldHistoryRun10868(id: "\(id)#run-1", points: points)], links: [], labelPointID: nil,
                before: .observation(pointID: points[0].id, figure: "\(Int((values[0] * 100).rounded()))%",
                                     provenance: "Before scheduled start · Oct 12, 3:17 AM"),
                recorded: .absent(words: "Not recorded"), absentWords: "No recorded history", choose: nil)
        }
        let home = phase == .final ? [0.455, 0.5, 0.891273] : [0.7872, 0.6, 0.205895]
        return FieldHistoryInput10868(
            title: "Win probability", caption: phase == .before ? "Before the match" : "Match history",
            series: [series("home", match.home, .circle, homeTint, home),
                     series("away", match.away, .diamond, awayTint, home.map { 1 - $0 })],
            selection: .none, domain: FieldHistoryDomain10868(lower: 0, upper: 1200), ceiling: 1,
            yTicks: [], xTicks: [], guides: [], breaks: [],
            readout: .singleBefore(label: "Before scheduled start"),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow · before scheduled start", filled: nil),
            comparisonExplanation: nil, notes: ["Bain Luck", "Gaps remain blank."],
            summary: "Recorded readings for both players.", plotHeight: 230,
            unboundReadingWords: "Not recorded", plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: FieldHistoryAction10868(id: "history.details", label: "History & source details",
                                             spokenLabel: nil, isAvailable: false),
            expand: FieldHistoryAction10868(id: "history.expand", label: "Full chart",
                                            spokenLabel: "Expand match win probability history", isAvailable: true),
            inspect: nil, previous: nil, next: nil, inspection: nil)
    }

    // MARK: Held reading (TennisChartReading9483)

    private static let start = Date(timeIntervalSince1970: 1_791_000_000)

    private static func chartReading(_ minutes: Double, _ home: Double) -> TennisChartReading9483.Reading {
        TennisChartReading9483.Reading(eventId: 15327807, source: "aggregate",
                                       date: start.addingTimeInterval(minutes * 60), home: home, away: nil)
    }

    private static func heldReading(_ shown: TennisChartReading9483.Shown, offersLatest: Bool = false) -> TennisEventPageReading10868 {
        TennisEventPageReading10868(shown: shown, baseline: chartReading(-38, 0.7872), scheduledStart: start,
                                    homeName: liveMatch.home, awayName: liveMatch.away, homeTint: homeTint, awayTint: awayTint,
                                    offersLatest: offersLatest, now: start)
    }

    // MARK: Set winners / first-set expectations

    private static func periodObs(_ value: Double, _ text: String) -> PeriodOutcomeObservation10868 {
        PeriodOutcomeObservation10868(probability: value, text: text, accessibilityDetail: "Before the start · Polymarket")
    }

    private static let periodWords = PeriodOutcomeWords10868(
        pregameTitle: "Pre-match chance", notStarted: "Not started", currentTitle: "Current chance",
        liveResultTitle: "Set result", finalResultTitle: "Final result", selectionUnavailable: "Selected player unavailable.",
        cellUnavailable: "Not offered for this set", selectHint: "Shows this player’s chances",
        detailsHint: "Opens the original outcome")

    private static let setWords = PeriodOutcomeFinalScoreWords10868(
        eyebrow: "SET WINNERS", title: "Set by set", summary: nil, pregameHeading: "Pre-match chance to win each set",
        scoreSeparator: "–", actualTitle: "Actual score", actualMissing: "No score reported for this set",
        winnerUnavailable: "Winner not reported", scaleNote: "Chance bars share a 0–100% scale.",
        detailsNote: "Tap a player for its original outcome and recorded time.")

    /// `phase` is the leaf's own; `optIn` supplies the phase's display permission.
    private static func sets(_ phase: PeriodOutcomePhase10868, optIn: Bool = true) -> PeriodOutcomeFinalScoreInput10868 {
        let isFinal = phase == .final
        let periods = isFinal
            ? [PeriodOutcomePeriod10868(id: "set-1", label: "Set 1"), PeriodOutcomePeriod10868(id: "set-2", label: "Set 2"),
               PeriodOutcomePeriod10868(id: "set-3", label: "Set 3")]
            : [PeriodOutcomePeriod10868(id: "set-1", label: "Set 1")]
        func cell(_ id: String, _ period: String, _ value: Double, _ text: String,
                  _ result: PeriodOutcomeResult10868) -> PeriodOutcomeCell10868 {
            PeriodOutcomeCell10868(id: id, periodID: period, pregame: periodObs(value, text),
                                   pregameMissing: "Pre-match chance unavailable",
                                   current: .unavailable("Current chance unavailable"), result: result)
        }
        let homeCells: [PeriodOutcomeCell10868]
        let awayCells: [PeriodOutcomeCell10868]
        if isFinal {
            homeCells = [cell("65138603:fokina", "set-1", 0.5, "50%", .won("Won")),
                         cell("65138604:fokina", "set-2", 0.475, "47.5%", .lost("Lost"))]
            awayCells = [cell("65138603:tiafoe", "set-1", 0.5, "50%", .lost("Lost")),
                         cell("65138604:tiafoe", "set-2", 0.525, "52.5%", .won("Won"))]
        } else {
            homeCells = [cell("245152775", "set-1", 0.72, "72%", .unconfirmed("Result pending"))]
            awayCells = [cell("245152776", "set-1", 0.28, "28%", .unconfirmed("Result pending"))]
        }
        let match = isFinal ? finalMatch : liveMatch
        let comparison = PeriodOutcomeComparisonInput10868(
            phase: phase, eyebrow: nil, title: "Set-by-set expectations", intro: nil, periods: periods,
            series: [PeriodOutcomeSeries10868(id: "home", label: match.homeCompact, tint: homeTint, symbol: .circle, cells: homeCells),
                     PeriodOutcomeSeries10868(id: "away", label: match.awayCompact, tint: awayTint, symbol: .square, cells: awayCells)],
            selectedSeriesID: nil, plotTitle: nil, scaleCaption: nil,
            axis: PeriodOutcomeAxis10868(lower: 0, upper: 1, ticks: []),
            pointExplanation: "Each dot is a pre-match chance for that set.",
            lineExplanation: "Lines compare sets, not changes over time.", resultsTitle: nil, words: periodWords)
        func actual(_ period: String, _ home: String, _ away: String, winner: String, _ words: String) -> PeriodOutcomeActualContext10868 {
            PeriodOutcomeActualContext10868(
                id: "actual:\(period)", periodID: period,
                state: .reported(PeriodOutcomeActualReport10868(
                    scores: [PeriodOutcomeActualScore10868(seriesID: "home", text: home),
                             PeriodOutcomeActualScore10868(seriesID: "away", text: away)],
                    unit: "games", winner: .reported(seriesID: winner, text: words))),
                provenance: "Scores · ESPN", noOriginal: "No pre-match set chance recorded.")
        }
        var input = PeriodOutcomeFinalScoreInput10868(
            comparison: comparison,
            actuals: isFinal
                ? [actual("set-1", "7", "6", winner: "home", "Fokina won"), actual("set-2", "4", "6", winner: "away", "Tiafoe won"),
                   actual("set-3", "7", "6", winner: "home", "Fokina won")]
                : [actual("set-1", "5", "7", winner: "away", "Zandschulp won")],
            words: setWords)
        if optIn, phase == .during {
            input.completedDuringPlay = PeriodOutcomeCompletedDuringPlay10868(
                completedPeriodIDs: ["set-1"],
                panels: [PeriodOutcomeActualPanel10868(id: "panel:home", periodID: "set-1", seriesID: "home",
                                                       blocks: Array(repeating: .filled, count: 5) + [.empty, .empty],
                                                       state: "Set lost"),
                         PeriodOutcomeActualPanel10868(id: "panel:away", periodID: "set-1", seriesID: "away",
                                                       blocks: Array(repeating: .filled, count: 7), state: "Set won")],
                words: PeriodOutcomeCompletedDuringPlayWords10868(
                    originalResultTitle: "Original market result",
                    blocksNote: "Each block is one game won, not play-by-play order."))
        }
        if optIn, phase == .before {
            input.beforePlay = PeriodOutcomeBeforePlay10868(
                periodIDs: ["set-1"],
                copy: PeriodOutcomeCardCopy10868(eyebrow: "FIRST SET · BEFORE PLAY", title: "Who takes the first set?",
                                                 summary: nil, pregameHeading: "Pre-match chances",
                                                 scaleNote: "Chance bars share a 0–100% scale.", detailsNote: nil))
        }
        return input
    }

    // MARK: Total games

    private static func totalObs(_ value: Double, _ text: String) -> TotalMilestoneObservation10868 {
        TotalMilestoneObservation10868(probability: value, text: text, timeText: nil,
                                       accessibilityDetail: "Before the start · Polymarket")
    }

    private static func totalRow(_ id: String, _ line: Double, before: (Double, String)?,
                                 result: TotalMilestoneResult10868) -> TotalMilestoneRow10868 {
        TotalMilestoneRow10868(id: id, quantity: line, quantityLabel: String(line), title: "Over \(line) games",
                               before: before.map { totalObs($0.0, $0.1) }, beforeMissing: "Pre-match chance unavailable",
                               current: .unavailable("Current chance unavailable"), performance: nil, result: result)
    }

    private static func profile(_ phase: TotalMilestonePhase10868, rows: [TotalMilestoneRow10868],
                                count: TotalMilestoneActual10868?) -> TotalMilestoneInput10868 {
        TotalMilestoneInput10868(
            phase: phase, eyebrow: "TOTAL GAMES", title: "Total games", chartTitle: nil,
            quantityAxisTitle: "Games in the match", milestones: rows, selectedMilestoneID: rows.first?.id,
            actual: count, projection: nil, quantityDomain: TotalMilestoneDomain10868(lower: 0, upper: 40),
            quantityTicks: [], chanceTicks: [], timing: nil)
    }

    private static func gameCount(_ value: Double, _ text: String, _ label: String) -> TotalMilestoneActual10868 {
        .count(TotalMilestoneCount10868(quantity: value, text: text, unit: "games", clock: nil, ruleLabel: label,
                                        accessibilityDetail: "ESPN games"))
    }

    private static let thresholdWords = TotalMilestoneThresholdWords10868(
        beforeTitle: "Pre-match chance", currentTitle: "Current chance", thresholdKey: "Original market thresholds",
        originalsTitle: "Original total-game contracts", note: "Circles mark total-game thresholds, not projected final scores.",
        invitation: nil, unresolved: "Original contract unavailable", subtotalsTitle: "Games won")

    private static func totals(_ phase: TennisEventPagePhase10868, as leafPhase: TotalMilestonePhase10868? = nil,
                               finalVariant: Bool? = nil) -> TennisEventPageTotals10868 {
        let leaf = leafPhase ?? TennisEventPageModel10868.totalPhase(phase)
        if finalVariant ?? (phase == .final) {
            let row = totalRow("65123147:over", 22.5, before: nil, result: .won("Won"))
            return .final(TotalMilestoneLineComparisonInput10868(
                profile: profile(leaf, rows: [row], count: gameCount(36, "36", "36 actual")),
                openingLine: .line(TotalMilestoneOpeningLine10868(
                    quantity: 22.5, text: "22.5", unit: "games", title: "Opening market line", markLabel: "22.5 opening",
                    time: .unknown("Opening time unavailable"), note: "A market threshold, not a projected score",
                    accessibilityDetail: "Sportsbooks’ opening total")),
                difference: TotalMilestoneLineDifference10868(figure: "+13.5", caption: "games above opening line",
                                                              spoken: "+13.5 games above the opening line"),
                quantitiesShareUnit: true, originalsTitle: "Original contracts", invitation: nil))
        }
        let rows = [totalRow("245152784", 22.5, before: nil, result: .unconfirmed("Result pending")),
                    totalRow("245152786", 23.5, before: nil, result: .unconfirmed("Result pending"))]
        var live = TotalMilestoneThresholdLiveInput10868(
            profile: profile(leaf, rows: rows, count: leaf == .before ? nil : gameCount(18, "18", "18 so far")),
            thresholds: [TotalMilestoneThreshold10868(originalID: "245152784", quantity: 22.5, label: "22.5",
                                                      mark: TotalMilestoneThresholdMark10868(shape: .circle, tone: .primary)),
                         TotalMilestoneThreshold10868(originalID: "245152786", quantity: 23.5, label: "23.5",
                                                      mark: TotalMilestoneThresholdMark10868(shape: .diamond, tone: .secondary))],
            subtotals: leaf == .before ? [] : [TotalMilestoneSubtotal10868(text: "8", name: "Fils"),
                                               TotalMilestoneSubtotal10868(text: "10", name: "Zandschulp")],
            quantitiesShareUnit: true, words: thresholdWords)
        if leaf == .before {
            live.beforePresentation = TotalMilestoneThresholdBefore10868(eyebrow: "TOTAL GAMES · BEFORE PLAY",
                                                                         title: "How long a match?", note: nil)
        }
        return .thresholds(live)
    }

    // MARK: Exact set finishes

    private static let exactLegend = ExactScoreMapLegend10868(
        scaleTitle: "Pre-match chance", offScale: "Off scale", notListed: "Not listed", unavailable: "Unavailable",
        result: "Result", selection: "Selected")

    private static let exactWords = ExactScoreMapWords10868(
        pregameTitle: "Pre-match chance", currentTitle: "Current chance", liveResultTitle: "Result",
        finalResultTitle: "Final result", scopeUnavailable: "Finishes unavailable", noSelection: "No finish selected",
        selectionUnavailable: "Selected finish unavailable", recoverSelection: "Show available finishes",
        mapUnavailable: "Finishes unavailable", scaleUnavailable: "Scale unavailable", panHint: "",
        notListed: "Not listed", unavailableMark: "Unavailable", otherChoicesTitle: "Other finishes",
        previous: "Previous", next: "Next", details: "Details", selectedSpoken: "Selected",
        selectScopeHint: "Shows these finishes", selectHint: "Selects this finish", detailsHint: "Opens the original")

    private static func exactOriginal(_ id: String, _ label: String, before: (Double, String)?,
                                      result: ExactScoreMapResult10868) -> ExactScoreMapOriginal10868 {
        ExactScoreMapOriginal10868(
            id: id, label: label, placement: .nonGrid,
            pregame: before.map { .recorded(ExactScoreMapObservation10868(probability: $0.0, text: $0.1, detail: "Before the start")) }
                ?? .unavailable("Pre-match chance unavailable"),
            current: .unavailable("Current chance unavailable"), result: result)
    }

    private static func exactMap(_ phase: ExactScoreMapPhase10868, _ match: Match,
                                 _ originals: [ExactScoreMapOriginal10868], selected: String?) -> ExactScoreMapInput10868 {
        let scope = ExactScoreMapScope10868(
            id: "exact:\(match.eventID)", label: "Exact match score", rows: [], columns: [], originals: originals,
            scale: ExactScoreMapScale10868(lower: 0, upper: 1, ticks: []),
            actual: phase == .final ? ExactScoreMapActual10868(title: "Final score", text: "2–1 sets") : nil)
        return ExactScoreMapInput10868(
            phase: phase, title: "Exact set finishes", intro: nil, homeLabel: match.home, awayLabel: match.away,
            rowsTitle: "", columnsTitle: "", scopes: [scope], selectedScopeID: scope.id, selectedOriginalID: selected,
            legend: exactLegend, words: exactWords)
    }

    private static func exact(_ phase: TennisEventPagePhase10868, as leafPhase: ExactScoreMapPhase10868? = nil,
                              finalVariant: Bool? = nil) -> TennisEventPageExact10868 {
        let leaf = leafPhase ?? TennisEventPageModel10868.exactPhase(phase)
        if finalVariant ?? (phase == .final) {
            let originals = [
                exactOriginal("245000001", "Alejandro Davidovich Fokina wins 2-0", before: nil, result: .lost("Lost")),
                exactOriginal("245000002", "Alejandro Davidovich Fokina wins 2-1", before: nil, result: .won("Won")),
                exactOriginal("245000003", "Frances Tiafoe wins 2-0", before: nil, result: .lost("Lost")),
                exactOriginal("245000004", "Frances Tiafoe wins 2-1", before: nil, result: .lost("Lost")),
            ]
            func tile(_ id: String, _ score: String, _ opponent: Int) -> ExactScoreFinishTile10868 {
                ExactScoreFinishTile10868(originalID: id, score: score, unit: "sets",
                                          counts: ExactScoreFinishSetCounts10868(slots: 2, player: 2, opponent: opponent),
                                          countsSpoken: "\(score) sets")
            }
            return .final(ExactScoreFinishInput10868(
                map: exactMap(leaf, finalMatch, originals, selected: "245000002"),
                players: [ExactScoreFinishPlayer10868(id: "home", name: finalMatch.home,
                                                      tiles: [tile("245000001", "2–0", 0), tile("245000002", "2–1", 1)]),
                          ExactScoreFinishPlayer10868(id: "away", name: finalMatch.away,
                                                      tiles: [tile("245000003", "2–0", 0), tile("245000004", "2–1", 1)])],
                words: ExactScoreFinishWords10868(countsKey: "Sets won · best of 3",
                                                  countsNote: "Blocks count sets won by each player; they do not show playing order.",
                                                  countsUnavailable: "Set blocks unavailable",
                                                  finishUnavailable: "Finish unavailable",
                                                  tapInvitation: "Tap a finish to compare it.")))
        }
        let pending = ExactScoreMapResult10868.unconfirmed("Result pending")
        let originals = [
            exactOriginal("245059339", "Arthur Fils wins 2-1", before: nil, result: pending),
            exactOriginal("245059341", "Botic Van de Zandschulp wins 2-0", before: nil, result: pending),
            exactOriginal("245059340", "Botic Van de Zandschulp wins 2-1", before: nil, result: pending),
            exactOriginal("245059338", "Arthur Fils wins 2-0", before: nil, result: pending),
        ]
        func lane(_ id: String, _ label: String, _ tone: ExactScoreFinishLaneTone10868) -> ExactScoreFinishLane10868 {
            ExactScoreFinishLane10868(originalID: id, fallbackLabel: label, availability: .open("Still possible"), tone: tone)
        }
        var lanes = ExactScoreFinishLaneInput10868(
            map: exactMap(leaf, liveMatch, originals, selected: nil),
            lanes: [lane("245059339", "Fils 2–1", .home), lane("245059341", "Zandschulp 2–0", .away),
                    lane("245059340", "Zandschulp 2–1", .away), lane("245059338", "Fils 2–0", .home)],
            words: ExactScoreFinishLaneWords10868(eyebrow: "EXACT FINISH · SETS", scaleKey: "Pre-match chances · same 0–100% scale",
                                                  availabilityTitle: "Finish status", originalResultTitle: "Original market result",
                                                  laneUnavailable: "Finish unavailable", contextNote: nil))
        if leaf == .before {
            lanes.beforePresentation = ExactScoreFinishLaneBefore10868(title: "How the match could finish", intro: nil,
                                                                       eyebrow: "EXACT FINISH · BEFORE PLAY", contextNote: nil)
        }
        return .lanes(lanes)
    }

    // MARK: Set and game handicaps

    private static func handicapIdentity(_ market: String, _ side: String) -> OriginalMarketDetails9483.Identity {
        OriginalMarketDetails9483.Identity(source: "polymarket", market: market, side: side)
    }

    private static func handicapOriginal(_ identity: OriginalMarketDetails9483.Identity, _ title: String,
                                         _ outcome: String, _ before: (Double, String),
                                         mode: OriginalMarketDetails9483.Mode) -> OriginalMarketDetails9483.Original {
        OriginalMarketDetails9483.Original(
            identity: identity, title: title, outcome: outcome, mode: mode,
            pregame: .value(before.1, placement: before.0, provenance: "Before the start · Polymarket"),
            later: mode == .result || mode == .pregame ? nil : .missing("Current chance unavailable"),
            grade: mode == .result ? OriginalMarketDetails9483.Grade(words: "Won", provenance: nil) : nil,
            about: OriginalMarketDetails9483.About(source: "Polymarket", rules: .unavailable("Rules unavailable"),
                                                  provenance: [], historicalQuote: nil))
    }

    private static func handicaps(_ phase: TennisEventPagePhase10868, as leafPhase: OriginalHandicapCard9483.Phase? = nil,
                                  optIn: Bool = true) -> TennisEventPageHandicaps10868 {
        let leaf = leafPhase ?? TennisEventPageModel10868.handicapPhase(phase)
        let isFinal = phase == .final
        let mode: OriginalMarketDetails9483.Mode = isFinal ? .result : (phase == .during ? .comparison(.current) : .pregame)
        let sets = isFinal ? handicapIdentity("65123150", "244876662") : handicapIdentity("65197801", "245152788")
        let games = isFinal ? handicapIdentity("65149801", "244973047") : handicapIdentity("65212323", "245201950")
        let catalogue = OriginalMarketDetails9483.Catalogue(
            scope: "tennis:\(match(phase).eventID):originals",
            originals: [handicapOriginal(sets, "Set Handicap", isFinal ? finalMatch.home : liveMatch.away,
                                         isFinal ? (0.67, "67%") : (0.435, "44%"), mode: mode),
                        handicapOriginal(games, "Game Spread", isFinal ? finalMatch.home : liveMatch.away,
                                         isFinal ? (0.47, "47%") : (0.55, "55%"), mode: mode)])
        func panel(_ identity: OriginalMarketDetails9483.Identity, _ subject: String, _ predicate: String,
                   _ condition: String) -> OriginalHandicapCard9483.Panel {
            OriginalHandicapCard9483.Panel(original: identity, subject: subject, predicate: predicate, condition: condition,
                                           actual: .missing("Actual unavailable"), resultMark: nil,
                                           openHint: "Opens the original \(condition) prop.")
        }
        let subject = isFinal ? finalMatch.homeCompact : liveMatch.awayCompact
        var input = OriginalHandicapCard9483.Input(
            phase: leaf, catalogue: catalogue, held: nil,
            groups: [OriginalHandicapCard9483.Group(heading: "Sets", panels: [panel(sets, subject, "\(subject) set handicap", "+1.5 sets")]),
                     OriginalHandicapCard9483.Group(heading: "Games", panels: [panel(games, subject, "\(subject) game handicap",
                                                                                      isFinal ? "+0.5 games" : "+4.5 games")])],
            words: OriginalHandicapCard9483.Words(
                eyebrow: "HANDICAPS · DIFFERENT UNITS", title: "Set and game handicaps", explanationTitle: "How these props work",
                explanation: ["A set handicap counts sets; a game handicap counts games."],
                tapInvitation: "Tap a panel to open its original prop.",
                scopeUnavailable: "Handicap props unavailable in this update",
                panelUnavailable: "Prop unavailable in this update",
                comparisonUnavailable: "Pre-match comparison unavailable for this prop"))
        if optIn, leaf == .during { input.showsDuringPlay = true }
        if optIn, leaf == .before { input.showsBeforePlay = true }
        return TennisEventPageHandicaps10868(input: input, tint: homeTint)
    }

    // MARK: Stream and page

    private static let cardIDs = ["sets", "totals", "exact", "handicaps"]

    private static func cardName(_ id: String, _ phase: TennisEventPagePhase10868) -> String {
        switch id {
        case "sets": phase == .final ? "Set winners" : "First-set expectations"
        case "totals": phase == .final ? "Total games" : "Total-game milestones"
        case "exact": "Exact set finishes"
        default: "Set and game handicaps"
        }
    }

    private static func stream(_ phase: TennisEventPagePhase10868, showing: (String, String?) = ("sets", "totals"),
                               wide: Bool = false) -> StoryStreamPresentation10868 {
        let scope = "tennis:\(match(phase).eventID):\(phase.rawValue)"
        func ref(_ id: String) -> StoryStreamPresentation10868.CardRef { .init(scope: scope, id: id) }
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: nil, heading: "Match stories",
            cards: cardIDs.map { StoryStreamPresentation10868.Card(id: $0, name: cardName($0, phase)) },
            primary: ref(showing.0), companion: showing.1.map(ref), companionLabel: showing.1 == nil ? nil : "Next",
            wide: wide, position: "1 of 4", status: "Use Previous or Next to see each story",
            dwellFraction: nil, playback: nil, previous: ref("handicaps"), next: ref("totals"), readerOpen: false)
    }

    private static let stories: [TennisEventPageStory10868] = [
        TennisEventPageStory10868(cardID: "sets", card: .sets),
        TennisEventPageStory10868(cardID: "totals", card: .totals),
        TennisEventPageStory10868(cardID: "exact", card: .exact),
        TennisEventPageStory10868(cardID: "handicaps", card: .handicaps),
    ]

    private static let about = TennisEventPageAbout10868(title: "About this match", sections: [
        TennisEventPageAboutSection10868(title: "Chances", paragraphs: ["Pre-match · Fils 79% · Zandschulp 21%."]),
        TennisEventPageAboutSection10868(title: "History and sources", paragraphs: ["The chart draws recorded readings only."]),
    ])

    private static let copy = TennisEventPageCopy10868(
        storiesLabel: "Match stories",
        storyUnavailable: "This story isn’t available for this match state. Every original is still in All props.",
        headlineUnavailable: "The players’ chances aren’t available for this match state.",
        allPropsLabel: "All 12 original props")

    private static func page(
        _ phase: TennisEventPagePhase10868,
        headline: FieldHeadlineInput10868? = nil,
        reading: TennisEventPageReading10868?? = nil,
        sets: PeriodOutcomeFinalScoreInput10868?? = nil,
        totals: TennisEventPageTotals10868?? = nil,
        exact: TennisEventPageExact10868?? = nil,
        handicaps: TennisEventPageHandicaps10868?? = nil,
        stream: StoryStreamPresentation10868?? = nil,
        stories: [TennisEventPageStory10868]? = nil,
        about: TennisEventPageAbout10868?? = nil,
        copy: TennisEventPageCopy10868? = nil
    ) -> TennisEventPageInput10868 {
        let match = Self.match(phase)
        return TennisEventPageInput10868(
            phase: phase, eventID: match.eventID,
            reader: TennisEventPageReaderHeader10868(
                title: phase == .final ? "Fokina won · 2–1 sets" : "Fils · Zandschulp",
                state: phase == .final ? "Pre-match · Fokina 45% · Tiafoe 55%" : "Pre-match · Fils 79% · Zandschulp 21%"),
            headline: headline ?? Self.headline(phase),
            notice: nil,
            history: Self.history(phase),
            reading: reading ?? heldReading(.reading(chartReading(80, 0.205895), held: false)),
            sets: sets ?? Self.sets(TennisEventPageModel10868.periodPhase(phase)),
            totals: totals ?? Self.totals(phase),
            exact: exact ?? Self.exact(phase),
            handicaps: handicaps ?? Self.handicaps(phase),
            stream: stream ?? Self.stream(phase),
            stories: stories ?? Self.stories,
            about: about ?? Self.about,
            copy: copy ?? Self.copy)
    }

    private static func originals(selection: OriginalMarketDetails9483.Selection? = nil) -> TennisEventPageOriginals10868 {
        let handicap = handicaps(.final).input
        return TennisEventPageOriginals10868(
            catalogue: handicap.catalogue, selection: selection,
            labels: [handicapIdentity("65123150", "244876662"): "Set Handicap · Alejandro Davidovich Fokina"],
            heading: "All props", context: "2 originals", emptyWords: "No retained originals for this match",
            unavailableChoice: "Unnamed original", tint: homeTint)
    }

    private static func activation(_ stream: StoryStreamPresentation10868, _ id: String,
                                   log: @escaping (String) -> Void) -> StoryStreamCardActivation10868 {
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: id)
        return StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
            if case .interaction(_, let card) = intent { log("hold:\(card?.id ?? "-")") } else { log("other") }
        }
    }

    /// A host-owned disclosure flag whose writes are logged.
    private final class Flag {
        var value = false
    }

    private static func binding(_ flag: Flag, _ name: String, log: @escaping (String) -> Void) -> Binding<Bool> {
        Binding(get: { flag.value }, set: { flag.value = $0; log("write:\(name):\($0)") })
    }

    // MARK: Phases

    func testBeforePlayMountsOnlyTheBeforeVariantsAndBothPlayersLeadWithTheirPreMatchChances() {
        let input = Self.page(.before)
        let view = TennisEventPagePresentation10868(input: input)
        XCTAssertEqual(view.mode, .page)
        XCTAssertEqual(view.headlineContent()?.input, input.headline)
        XCTAssertEqual(view.historyContent(reader: false).input, input.history)

        // First-set expectations only with the owner's before-play opt-in.
        XCTAssertEqual(view.setsContent()?.input, input.sets)
        XCTAssertEqual(view.setsContent()?.input.periodIndices, [0])
        // Totals and exact finishes take their before/during variants; the
        // final variants have no content before the match.
        guard case .thresholds(let live)? = input.totals else { return XCTFail("threshold totals before play") }
        XCTAssertEqual(view.thresholdTotalsContent()?.input, live)
        XCTAssertNil(view.finalTotalsContent())
        guard case .lanes(let lanes)? = input.exact else { return XCTFail("exact lanes before play") }
        XCTAssertEqual(view.laneExactContent()?.input, lanes)
        XCTAssertNil(view.finalExactContent())
        XCTAssertEqual(view.handicapsContent()?.input, input.handicaps?.input)

        // Two players, equal standing, pre-match chances only.
        let headline = FieldHeadlineModel10868(input.headline)
        XCTAssertEqual(headline.competitors.map(\.slot.name), ["Arthur Fils", "Botic van de Zandschulp"])
        XCTAssertEqual(headline.competitors.map(\.slot.keyShape), [.circle, .diamond])
        XCTAssertTrue(headline.keyIsHollow)

        // Every card id names its one story.
        let model = TennisEventPageModel10868(input)
        XCTAssertEqual(Self.cardIDs.compactMap { model.storyCard($0) }, [.sets, .totals, .exact, .handicaps])
        XCTAssertTrue(TennisEventPageCard10868.allCases.allSatisfy { model.readerShows($0) })
    }

    func testDuringPlayMountsTheLiveVariantsAndTheSetScoreIsTheOwnersFigureInSets() {
        let input = Self.page(.during)
        let view = TennisEventPagePresentation10868(input: input)
        XCTAssertNotNil(view.headlineContent())
        XCTAssertEqual(view.setsContent()?.input.periodIndices, [0], "the owner's completed first set only")
        XCTAssertNotNil(view.thresholdTotalsContent())
        XCTAssertNil(view.finalTotalsContent())
        XCTAssertNotNil(view.laneExactContent())
        XCTAssertNil(view.finalExactContent())
        XCTAssertNotNil(view.handicapsContent())

        // The match state is the owner's set figure, in sets — never a games
        // projection — and the in-match chance sits beside the pre-match one.
        let headline = FieldHeadlineModel10868(input.headline)
        XCTAssertEqual(headline.state?.figure, "0–1")
        XCTAssertEqual(headline.state?.unit, "sets")
        XCTAssertEqual(headline.competitors.map(\.metrics.count), [2, 2])
        XCTAssertFalse(headline.keyIsHollow)
    }

    func testAfterTheMatchMountsTheFinalVariantsAndEveryResultStaysItsOriginalsOwn() {
        let input = Self.page(.final)
        let view = TennisEventPagePresentation10868(input: input)
        XCTAssertEqual(view.setsContent()?.input.periodIndices, [0, 1, 2])
        guard case .final(let line)? = input.totals else { return XCTFail("final totals") }
        XCTAssertEqual(view.finalTotalsContent()?.input, line)
        XCTAssertNil(view.thresholdTotalsContent())
        guard case .final(let tiles)? = input.exact else { return XCTFail("final exact tiles") }
        XCTAssertEqual(view.finalExactContent()?.input, tiles)
        XCTAssertNil(view.laneExactContent())
        XCTAssertNotNil(view.handicapsContent())

        // The reported result is context beside the pre-match reminder; each
        // card's result is its own original's grade, never the match result.
        let headline = FieldHeadlineModel10868(input.headline)
        XCTAssertEqual(headline.state?.figure, "2–1")
        XCTAssertEqual(headline.state?.caption, "Final · Alejandro Davidovich Fokina won")
        XCTAssertEqual(tiles.state(tiles.players[0].tiles[1], of: tiles.players[0]),
                       ExactScoreFinishTileState10868.placed(tiles.map.scopes[0].originals[1]))
        XCTAssertEqual(line.line?.text, "22.5")
        XCTAssertEqual(line.visibleDifference?.figure, "+13.5")
    }

    // MARK: Guards

    func testALeafFromAnotherPhaseOrTheOtherVariantIsNotMountedAndAStoryResolvesOnlyItsOneExactLink() {
        // A during headline, final-variant totals, before-phase sets, final
        // exact tiles and final-phase handicaps on a during page: none coerced.
        let input = Self.page(.during, headline: Self.headline(.during, as: .final),
                              sets: Self.sets(.before), totals: Self.totals(.during, finalVariant: true),
                              exact: Self.exact(.during, finalVariant: true),
                              handicaps: Self.handicaps(.during, as: .final),
                              stories: Self.stories + [TennisEventPageStory10868(cardID: "sets", card: .sets),
                                                       TennisEventPageStory10868(cardID: "chart", card: .history)])
        let model = TennisEventPageModel10868(input)
        let view = TennisEventPagePresentation10868(input: input)
        XCTAssertNil(model.headline)
        XCTAssertNil(view.headlineContent())
        XCTAssertNil(view.setsContent())
        XCTAssertNil(view.finalTotalsContent())
        XCTAssertNil(view.thresholdTotalsContent())
        XCTAssertNil(view.finalExactContent())
        XCTAssertNil(view.laneExactContent())
        XCTAssertNil(view.handicapsContent())
        XCTAssertFalse(model.readerShows(.totals))
        XCTAssertTrue(model.readerShows(.history))
        XCTAssertNil(model.story("sets"), "two links for one id are none")
        XCTAssertNil(model.story("totals"))
        XCTAssertNil(model.story("chart"))
        XCTAssertNil(model.story("missing"))

        // Threshold totals and lanes after the match are not coerced either.
        let late = Self.page(.final, totals: Self.totals(.final, as: .during, finalVariant: false),
                             exact: Self.exact(.final, as: .during, finalVariant: false))
        XCTAssertNil(TennisEventPageModel10868(late).totals)
        XCTAssertNil(TennisEventPageModel10868(late).exact)

        // Without the leaf's own opt-in a before/during card shows nothing, so
        // it takes no stream cell.
        let silent = Self.page(.before, sets: Self.sets(.before, optIn: false),
                               handicaps: Self.handicaps(.before, optIn: false))
        XCTAssertNil(TennisEventPageModel10868(silent).sets)
        XCTAssertNil(TennisEventPageModel10868(silent).handicaps)
        XCTAssertNil(TennisEventPageModel10868(silent).story("sets"))
        let quietDuring = Self.page(.during, sets: Self.sets(.during, optIn: false),
                                    handicaps: Self.handicaps(.during, optIn: false))
        XCTAssertNil(TennisEventPageModel10868(quietDuring).sets)
        XCTAssertNil(TennisEventPageModel10868(quietDuring).handicaps)

        // A wholly absent stream draws no stories and keeps the hero.
        let quiet = Self.page(.before, stream: .some(nil), stories: [])
        XCTAssertNil(quiet.stream)
        XCTAssertNotNil(TennisEventPagePresentation10868(input: quiet).headlineContent())
    }

    func testTennisIsTwoOutcomeThroughTheAppsOwnDrawRule() {
        // The screen's two-player premise is the app's own rule, not this file's.
        for sport in ["tennis_atp_shanghai_masters", "tennis_atp_us_open", "tennis_wta_us_open"] {
            XCTAssertFalse(DrawPricedWinner.sportPricesADraw(sport))
            XCTAssertEqual(DrawPricedWinner.printablePair(away: 0.794105, home: 0.205895, sport: sport)?.away, 0.794105)
        }
        XCTAssertEqual(SportVocab.forSport("tennis_atp_shanghai_masters").scoreboardUnit, "sets")
    }

    // MARK: Holds

    func testStreamCardActionsAndDisclosureWritesHoldFirstThenReachTheExactOwnerPayloadAndReadsEmitNothing() {
        var log: [String] = []
        let totalFlag = Flag(), handicapFlag = Flag()
        func view(_ input: TennisEventPageInput10868, mode: TennisEventPageMode10868 = .page) -> TennisEventPagePresentation10868 {
            TennisEventPagePresentation10868(
                input: input, mode: mode,
                onSetDetails: { log.append("setDetails:\($0)") },
                onTotalSelect: { log.append("total:\($0)") },
                onTotalDetails: { log.append("totalDetails:\($0)") },
                totalTimingExpanded: Self.binding(totalFlag, "total") { log.append($0) },
                onExactSelect: { log.append("exact:\($0):\($1)") },
                onExactDetails: { log.append("exactDetails:\($0):\($1)") },
                onExactRecover: { log.append("exactRecover") },
                onHandicapSelect: { log.append("handicap:\($0.identity.market)") },
                handicapExplanationExpanded: Self.binding(handicapFlag, "handicap") { log.append($0) },
                onInteraction: { log.append("pageHold") })
        }

        let finished = Self.page(.final, wide: true)
        let page = view(finished)
        let shown = [Self.activation(finished.stream!, "sets") { log.append($0) },
                     Self.activation(finished.stream!, "totals") { log.append($0) }]
        XCTAssertTrue(shown.allSatisfy(\.isAvailable))
        XCTAssertFalse(Self.activation(finished.stream!, "exact") { log.append($0) }.isAvailable,
                       "only displayed cards can hold")

        // Building every card and reading every disclosure asks for nothing.
        let sets = page.setsContent(activation: shown[0])!
        let totals = page.finalTotalsContent(activation: shown[1])!
        _ = totals.timingExpanded?.wrappedValue
        XCTAssertEqual(log, [])

        sets.onDetails?("65138603:fokina")
        totals.onSelect?("65123147:over")
        totals.onDetails?("65123147:over")
        totals.timingExpanded!.wrappedValue = true
        XCTAssertEqual(log, ["hold:sets", "setDetails:65138603:fokina",
                             "hold:totals", "total:65123147:over",
                             "hold:totals", "totalDetails:65123147:over",
                             "hold:totals", "write:total:true"])
        XCTAssertTrue(totalFlag.value)

        // The exact tiles and the handicap card relay the same way; a stream
        // card never passes through the page hook as well.
        log.removeAll()
        let browsed = Self.page(.final, stream: Self.stream(.final, showing: ("exact", "handicaps"), wide: true))
        let exactHook = Self.activation(browsed.stream!, "exact") { log.append($0) }
        let handicapHook = Self.activation(browsed.stream!, "handicaps") { log.append($0) }
        let exact = view(browsed).finalExactContent(activation: exactHook)!
        let handicaps = view(browsed).handicapsContent(activation: handicapHook)!
        exact.onSelectOriginal?("exact:15327291", "245000002")
        exact.onDetails?("exact:15327291", "245000002")
        exact.onRecoverSelection?()
        handicaps.onSelect?(OriginalMarketDetails9483.Selection(scope: "s", identity: Self.handicapIdentity("65123150", "244876662")))
        handicaps.explanationExpanded!.wrappedValue = true
        XCTAssertEqual(log, ["hold:exact", "exact:exact:15327291:245000002",
                             "hold:exact", "exactDetails:exact:15327291:245000002",
                             "hold:exact", "exactRecover",
                             "hold:handicaps", "handicap:65123150",
                             "hold:handicaps", "write:handicap:true"])
        XCTAssertFalse(log.contains("pageHold"))

        // Full-size content keeps the exact callbacks with no activation.
        log.removeAll()
        let reader = view(finished, mode: .reader(.totals))
        reader.finalTotalsContent()?.onSelect?("65123147:over")
        XCTAssertEqual(log, ["total:65123147:over"])

        // The lanes during play relay Details the same way.
        log.removeAll()
        let during = Self.page(.during, stream: Self.stream(.during, showing: ("exact", nil)))
        let laneHook = Self.activation(during.stream!, "exact") { log.append($0) }
        view(during).laneExactContent(activation: laneHook)?.onDetails?("exact:15327807", "245059339")
        XCTAssertEqual(log, ["hold:exact", "exactDetails:exact:15327807:245059339"])
    }

    func testThePageHookHoldsOnceBeforeEachPageCatalogueAndDetailsActionAndNeverForReadersOrPassiveReads() {
        var log: [String] = []
        let selection = OriginalMarketDetails9483.Selection(scope: "tennis:15327291:originals",
                                                            identity: Self.handicapIdentity("65123150", "244876662"))
        func view(_ input: TennisEventPageInput10868, mode: TennisEventPageMode10868 = .page,
                  hook: Bool = true) -> TennisEventPagePresentation10868 {
            TennisEventPagePresentation10868(
                input: input, mode: mode, originals: Self.originals(selection: selection),
                onAbout: { log.append("about") },
                onAllProps: { log.append("allProps") },
                onOriginalSelect: { log.append("select:\($0.identity.market)") },
                onOriginalHistory: { log.append("history:\($0.actionID)") },
                onHeadlineOpen: { log.append("open:\($0.ref.outcomeID)") },
                onHistoryAction: { log.append("action:\($0)") },
                onHistoryInspectionChoice: { log.append("choice:\($0)") },
                onHistoryPlotPosition: { log.append("plot:\($0)") },
                onShowLatestReading: { log.append("latest") },
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        let held = Self.page(.during, reading: Self.heldReading(.reading(Self.chartReading(40, 0.6), held: true),
                                                                offersLatest: true))
        let page = view(held)
        // Building and reading call nothing.
        _ = page.headlineContent()
        _ = page.historyContent(reader: false)
        _ = page.pageReadingContent()
        XCTAssertEqual(log, [])

        page.headlineContent()?.onOpen?(FieldMovementOpen10868(ref: Self.ref(Self.liveMatch, "home"), observation: nil))
        page.headlineContent()?.onAbout?()
        page.historyContent(reader: false).onAction?("history.expand")
        page.historyContent(reader: false).onInspectionChoice?("c")
        page.historyContent(reader: false).onPlotPosition?(60)
        page.pageReadingContent()?.onShowLatest()
        page.openAllProps()
        page.catalogueContent()?.onSelect?(selection)
        page.originalDetailsContent()?.onHistory?(
            OriginalMarketDetails9483.HistoryIntent(selection: selection, entry: .expand, actionID: "x"))
        XCTAssertEqual(log, ["hold", "open:home", "hold", "about", "hold", "action:history.expand",
                             "hold", "choice:c", "hold", "plot:60.0", "hold", "latest", "hold", "allProps",
                             "hold", "select:65123150", "hold", "history:x"])

        // Full-size content keeps the exact callbacks: no second hold.
        log.removeAll()
        let reader = view(held, mode: .reader(.history))
        reader.historyContent(reader: true).onAction?("history.details")
        reader.readerReadingContent()?.onShowLatest?()
        reader.openReaderAbout()
        XCTAssertEqual(log, ["action:history.details", "latest", "about"])

        // Without a hook every callback is the owner's own.
        log.removeAll()
        view(held, hook: false).openAllProps()
        XCTAssertEqual(log, ["allProps"])
    }

    // MARK: History and the held reading

    func testTheFullSizeHistoryChangesOnlyItsLayoutAndExpandAndCarriesTheDatedReading() {
        let input = Self.page(.during)
        let model = TennisEventPageModel10868(input)
        let reader = model.readerHistory
        XCTAssertNil(reader.expand)
        XCTAssertEqual(reader.layout, .expanded)
        XCTAssertEqual(reader.series, input.history.series)
        XCTAssertEqual(reader.details, input.history.details)
        XCTAssertEqual(reader.notes, input.history.notes)
        let view = TennisEventPagePresentation10868(input: input, mode: .reader(.history))
        XCTAssertEqual(view.historyContent(reader: true).input, reader)
        XCTAssertEqual(view.historyContent(reader: false).input, input.history)

        // With nothing held the page shows no reading of its own (the hero
        // already prints the chance); full size shows the latest.
        XCTAssertNil(model.pageReading)
        XCTAssertNil(view.pageReadingContent())
        let dated = view.readerReadingContent()
        XCTAssertEqual(dated?.shown, .reading(Self.chartReading(80, 0.205895), held: false))
        XCTAssertEqual(dated?.baseline, Self.chartReading(-38, 0.7872))
        XCTAssertEqual(dated?.homeName, "Arthur Fils")
        XCTAssertNil(dated?.onShowLatest, "no callback, no control")

        // A held reading, a break or a vanished reading is shown on the page.
        for shown: TennisChartReading9483.Shown in [.reading(Self.chartReading(40, 0.6), held: true),
                                                    .gap(Self.start.addingTimeInterval(3000)), .unavailable] {
            let held = Self.page(.during, reading: Self.heldReading(shown, offersLatest: true))
            XCTAssertEqual(TennisEventPageModel10868(held).pageReading?.shown, shown)
            let page = TennisEventPagePresentation10868(input: held)
            XCTAssertEqual(page.pageReadingContent()?.shown, shown)
            XCTAssertEqual(page.pageReadingContent()?.offersLatest, false, "offered, but no action supplied")
            let acting = TennisEventPagePresentation10868(input: held, onShowLatestReading: {})
            XCTAssertEqual(acting.pageReadingContent()?.offersLatest, true)
        }

        // No reading at all: neither comparison is mounted.
        let none = Self.page(.during, reading: .some(nil))
        XCTAssertNil(TennisEventPagePresentation10868(input: none).readerReadingContent())
        XCTAssertNil(TennisEventPagePresentation10868(input: none).pageReadingContent())
    }

    // MARK: About, All props, Details

    func testTheAboutOpensOnlyThroughItsReadableEntries() {
        let input = Self.page(.final)
        XCTAssertNotNil(TennisEventPagePresentation10868(input: input, onAbout: {}).aboutOpener())
        XCTAssertNil(TennisEventPagePresentation10868(input: input).aboutOpener(), "no callback, no control")
        let blank = Self.page(.final, about: TennisEventPageAbout10868(
            title: " ", sections: [TennisEventPageAboutSection10868(title: "", paragraphs: ["  "])]))
        XCTAssertNil(TennisEventPageModel10868(blank).about)
        XCTAssertNil(TennisEventPagePresentation10868(input: blank, onAbout: {}).aboutOpener())
        XCTAssertNil(TennisEventPagePresentation10868(input: blank, mode: .about).aboutContent())

        // The compact heading's entry is full-size content only.
        let model = TennisEventPageModel10868(input)
        XCTAssertTrue(model.aboutEntry(mode: .reader(.sets), canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .page, canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .catalogue, canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .reader(.sets), canOpen: false))
        XCTAssertEqual(TennisEventPagePresentation10868(input: input, mode: .about).aboutContent()?.about, Self.about)
    }

    func testAllPropsAndDetailsMountTheExistingLeavesWithTheOwnersOriginals() {
        let input = Self.page(.final)
        let originals = Self.originals()
        let view = TennisEventPagePresentation10868(input: input, mode: .catalogue, originals: originals,
                                                    onAllProps: {}, onOriginalSelect: { _ in })
        XCTAssertEqual(view.catalogueContent()?.catalogue, originals.catalogue)
        XCTAssertEqual(view.catalogueContent()?.labels, originals.labels)
        XCTAssertEqual(view.catalogueContent()?.heading, "All props")
        XCTAssertNotNil(view.catalogueContent()?.onSelect)
        XCTAssertEqual(view.originalDetailsContent()?.catalogue, originals.catalogue)
        XCTAssertNil(view.originalDetailsContent()?.recorded)

        let model = TennisEventPageModel10868(input)
        XCTAssertTrue(model.allPropsAvailable(canOpen: true))
        XCTAssertFalse(model.allPropsAvailable(canOpen: false))
        let unlabelled = Self.page(.final, copy: TennisEventPageCopy10868(
            storiesLabel: "Match stories", storyUnavailable: "x", headlineUnavailable: "y", allPropsLabel: nil))
        XCTAssertFalse(TennisEventPageModel10868(unlabelled).allPropsAvailable(canOpen: true))
        XCTAssertNil(TennisEventPagePresentation10868(input: input).catalogueContent(), "no originals, no catalogue")
    }

    // MARK: Arrangement and fit

    func testCompactWideAndAccessibilitySizesChooseTheirArrangements() {
        XCTAssertEqual(TennisEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(TennisEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false),
                       [.sideBySide, .stacked])
        XCTAssertEqual(TennisEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false),
                       [.sideBySide, .stacked])
        XCTAssertEqual(TennisEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
    }

    func testThePageFitsAPhoneWidthAtStandardAndAccessibilityText() {
        for size in [DynamicTypeSize.large, .accessibility3] {
            for phase in TennisEventPagePhase10868.allCases {
                let host = hostForMeasurement(
                    TennisEventPagePresentation10868(input: Self.page(phase), onAllProps: {})
                        .environment(\.horizontalSizeClass, .compact),
                    at: size)
                let fitted = host.sizeThatFits(in: CGSize(width: 375, height: CGFloat.greatestFiniteMagnitude))
                XCTAssertLessThanOrEqual(fitted.width, 375, "\(phase) at \(size) must not scroll sideways")
            }
        }
    }
}

private extension TennisEventPagePresentation10868Tests {
    static func page(_ phase: TennisEventPagePhase10868, wide: Bool) -> TennisEventPageInput10868 {
        page(phase, stream: .some(stream(phase, wide: wide)))
    }
}
