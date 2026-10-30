import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the soccer match screen composed from the accepted leaves.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// composition only: which actual leaf Views the page mounts at each match
/// phase, that each receives the owner's input unchanged, the header's score,
/// clock and projection words or absences, the three named outcomes with their
/// own absences, the story stream's card-to-leaf wiring, the activation hook
/// before each leaf action, the full-size history without its expand control,
/// the arrangement candidates, and that nothing fires passively. Each leaf's
/// own rules stay with its own tests; nothing here claims a rendered fit, a
/// native runtime, VoiceOver behaviour, a stream hold qualification or a
/// production binding.
///
/// ARCHIVED raw values come from Valladolid–Albacete, Monday, October 12,
/// 2026 (event 15325054), as retained in the pinned prototype captures
/// `liveSoccer.json` (sha256 d835ccdf…a7d2) and `soccerFinal.json`
/// (sha256 05de3275…fffe):
/// - home blend: pre-match 0.4892 at 11:59:00Z, in-match 0.995 at
///   12:55:38.867795Z; the live score 4–0 observed 12:54:19.676980Z; the final
///   score 5–0; Draw and away have no qualified blended reading at all;
/// - a REDUCED SUBSET of the recorded home history points, NOT the complete
///   captured journey. Each run holds only points that are consecutive in the
///   capture; an omitted span between chosen points starts a new run, so no
///   line joins across observations left out here. Live (`liveSoccer.json`
///   rows 0–2 | 30 | 56–57): 11:59, 12:00, 12:01 | 12:29 | 12:55,
///   12:55:38.867795. Final (`soccerFinal.json` rows 360–362 | 390 | 449–450):
///   11:59, 12:00, 12:01 | 12:29 | 13:52, 13:55 — the last observation; the
///   13:57 terminal 1.0 row is excluded. Before kickoff (`soccerFinal.json`
///   rows 0–1 | 360): Oct 5 12:30, Oct 5 13:30 | Oct 12 11:59;
/// - the known kickoff, 12:00Z, as the history's one Kickoff guide during play
///   and after the final; the before-kickoff input has no later guide;
/// - pre-match pins, each with its own clock: goals 3+/5+/6+ (Over 2.5 / 4.5 /
///   5.5) 0.5 / 0.13 / 0.06; both teams to score Yes 0.55, No 0.455; first team
///   to score Valladolid 0.57, Neither 0.065, Albacete 0.335; halftime result
///   Valladolid 0.375, Draw 0.425, Albacete 0.205; second-half result 0.43 /
///   0.38 / 0.23; and their separately admitted final settlements;
/// - the score observation clocks 12:02:45, 12:17:47, 12:28:24, 12:33:45,
///   12:38:45 (0–0 … 4–0) — observation times, not goal times.
///
/// CONSTRUCTED owner input (this layer resolves none of it): every display
/// word, figure text, clock line, colour, shape, tick, scale, scope, story
/// link, copy and phase; the live current prop states (withheld — the
/// published 15% is not an admitted chance); and the before-kickoff example,
/// which is a same-match phase-safety check built only from pre-match records
/// and earns no pregame route credit.
final class SoccerEventPagePresentation10868Tests: XCTestCase {

    // MARK: Archived clocks (epoch seconds)

    private static let octFive1230X = 1_791_203_400.0           // 2026-10-05T12:30:00Z
    private static let octFive1330X = 1_791_207_000.0           // 2026-10-05T13:30:00Z
    private static let preMatchX = 1_791_806_340.0              // 2026-10-12T11:59:00Z
    private static let kickoffX = 1_791_806_400.0               // 2026-10-12T12:00:00Z
    private static let minuteOneX = 1_791_806_460.0             // 2026-10-12T12:01:00Z
    private static let minute29X = 1_791_808_140.0              // 2026-10-12T12:29:00Z
    private static let live1255X = 1_791_809_700.0              // 2026-10-12T12:55:00Z
    private static let liveHeadlineX = 1_791_809_738.867795     // 2026-10-12T12:55:38.867795Z
    private static let final1352X = 1_791_813_120.0             // 2026-10-12T13:52:00Z
    private static let finalLastX = 1_791_813_300.0             // 2026-10-12T13:55:00Z
    private static let completedX = 1_791_813_461.005925        // 2026-10-12T13:57:41.005925Z

    private static let seriesID = "blend:15325054:home"
    /// CONSTRUCTED tints.
    private static let homeColor = Color(red: 0.23, green: 0.51, blue: 0.96)
    private static let drawColor = Color(red: 0.42, green: 0.44, blue: 0.50)
    private static let awayColor = Color(red: 0.55, green: 0.36, blue: 0.96)
    /// The pre-match pins' source and capture time.
    private static let pinProvenance = "Oct 12, 4:47 AM PT · Polymarket"

    // MARK: Header and headline

    private static func header(_ phase: SoccerEventPagePhase10868) -> SoccerEventPageHeader10868 {
        let noProjection = SoccerEventPageProjection10868(
            title: "Projected final", reading: .unavailable("No eligible projected final"), comparison: nil)
        switch phase {
        case .before:
            return SoccerEventPageHeader10868(
                state: "LA LIGA 2 · BEFORE KICKOFF", date: "Mon, Oct 12 · Kickoff 5:00 AM PT",
                home: "Valladolid", away: "Albacete", score: nil, clock: nil,
                projection: noProjection, aboutLabel: "About this match")
        case .live:
            return SoccerEventPageHeader10868(
                state: "LA LIGA 2 · IN PLAY", date: "Mon, Oct 12",
                home: "Valladolid", away: "Albacete",
                score: .actual(home: "4", away: "0", context: "Score observed Oct 12, 5:54 AM PT",
                               spoken: "Valladolid 4, Albacete 0"),
                clock: .unavailable("Match clock unavailable"),
                projection: noProjection, aboutLabel: "About this match")
        case .final:
            return SoccerEventPageHeader10868(
                state: "FINAL · VALLADOLID WON", date: "Mon, Oct 12",
                home: "Valladolid", away: "Albacete",
                score: .actual(home: "5", away: "0", context: "Final score", spoken: "Final: Valladolid 5, Albacete 0"),
                clock: nil, projection: noProjection, aboutLabel: "About this match")
        }
    }

    private static func headline(_ phase: SoccerEventPagePhase10868) -> SoccerThreeOutcomeHeadlineInput11449 {
        let preMatch = SoccerReadingHeading11449(title: "Pre-match chance", context: "Oct 12, 4:59 AM PT")
        func slot(_ label: String, _ color: Color, primary: String?, comparison: String?) -> SoccerOutcomeSlot11449 {
            SoccerOutcomeSlot11449(label: label, color: color, primary: primary, comparison: comparison,
                                   primaryUnavailable: phase == .live ? "No qualified in-match chance" : "No blended pre-match chance",
                                   comparisonUnavailable: "No blended pre-match chance")
        }
        guard phase == .live else {
            return SoccerThreeOutcomeHeadlineInput11449(
                home: slot("Valladolid win", Self.homeColor, primary: "48.9%", comparison: nil),
                draw: slot("Draw", Self.drawColor, primary: nil, comparison: nil),
                away: slot("Albacete win", Self.awayColor, primary: nil, comparison: nil),
                primaryHeading: preMatch, comparisonHeading: nil)
        }
        return SoccerThreeOutcomeHeadlineInput11449(
            home: slot("Valladolid win", Self.homeColor, primary: "99.5%", comparison: "48.9%"),
            draw: slot("Draw", Self.drawColor, primary: nil, comparison: nil),
            away: slot("Albacete win", Self.awayColor, primary: nil, comparison: nil),
            primaryHeading: SoccerReadingHeading11449(title: "In-match chance", context: "Oct 12, 5:55 AM PT · Bain Luck blend"),
            comparisonHeading: preMatch)
    }

    // MARK: History — the real home series only

    private static func point(_ id: String, _ x: Double, _ p: Double, _ style: FieldHistoryMarkStyle10868 = .filled) -> FieldHistoryPoint10868 {
        FieldHistoryPoint10868(id: "\(seriesID)#\(id)", x: x, probability: p, style: style)
    }

    /// The reduced subset, one run per span that is consecutive in the
    /// capture. Never one run across an omitted span.
    private static func runs(_ phase: SoccerEventPagePhase10868) -> [FieldHistoryRun10868] {
        let preMatch = point("1159", preMatchX, 0.4892, .hollow)
        let spans: [[FieldHistoryPoint10868]] = switch phase {
        case .before:
            [[point("oct5-1230", octFive1230X, 0.4761), point("oct5-1330", octFive1330X, 0.4686)], [preMatch]]
        case .live:
            [[preMatch, point("1200", kickoffX, 0.499132), point("1201", minuteOneX, 0.501237)],
             [point("1229", minute29X, 0.888763)],
             [point("1255", live1255X, 0.951805), point("125538", liveHeadlineX, 0.995)]]
        case .final:
            [[preMatch, point("1200", kickoffX, 0.499132), point("1201", minuteOneX, 0.501237)],
             [point("1229", minute29X, 0.888763)],
             [point("1352", final1352X, 0.998702), point("1355", finalLastX, 0.9995)]]
        }
        return spans.enumerated().map { FieldHistoryRun10868(id: "\(seriesID)#subset-run-\($0.offset + 1)", points: $0.element) }
    }

    /// The known kickoff, during play and after the final only.
    private static let kickoffGuide = FieldHistoryGuide10868(id: "guide.kickoff", x: kickoffX, label: "Kickoff")

    private static func action(_ id: String, _ label: String, spoken: String? = nil) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: spoken, isAvailable: true)
    }

    private static func history(_ phase: SoccerEventPagePhase10868) -> FieldHistoryInput10868 {
        let runs = Self.runs(phase)
        let points = runs.flatMap(\.points)
        let recorded: FieldHistoryReading10868 = phase == .live
            ? .observation(pointID: points.last!.id, figure: "99.5%", provenance: "Recorded Oct 12, 5:55 AM PT")
            : .absent(words: "Not recorded")
        let series = FieldHistorySeries10868(
            id: seriesID, name: "Valladolid win", shape: .circle, tint: Self.homeColor,
            runs: runs, links: [], labelPointID: nil,
            before: .independent(figure: "48.9%", provenance: "Pre-match · Oct 12, 4:59 AM PT"),
            recorded: recorded, absentWords: "No captured history", choose: nil)
        let xTicks: [FieldHistoryTick10868] = switch phase {
        case .before: [FieldHistoryTick10868(value: octFive1230X, lines: ["Oct 5"]), FieldHistoryTick10868(value: preMatchX, lines: ["Oct 12"])]
        case .live: [FieldHistoryTick10868(value: preMatchX, lines: ["4:59 AM"]), FieldHistoryTick10868(value: liveHeadlineX, lines: ["5:55 AM"])]
        case .final: [FieldHistoryTick10868(value: preMatchX, lines: ["4:59 AM"]), FieldHistoryTick10868(value: finalLastX, lines: ["6:55 AM"])]
        }
        let windows = phase == .final ? FieldHistoryWindows10868(groupLabel: "Probability history window", choices: [
            FieldHistoryWindowChoice10868(action: action("window.match", "During match"), isSelected: true),
            FieldHistoryWindowChoice10868(action: action("window.before", "Before match"), isSelected: false),
        ]) : nil
        let inspection = phase == .live ? FieldHistoryInspection10868(
            x: liveHeadlineX, caption: "Recorded Oct 12, 5:55 AM PT",
            selections: [seriesID: .point(id: points.last!.id, spoken: "99.5%")],
            choices: [
                FieldHistoryInspectionChoice10868(id: "choice.prematch", lines: ["4:59 AM"], spoken: "Pre-match, 4:59 AM PT", isSelected: false),
                FieldHistoryInspectionChoice10868(id: "choice.latest", lines: ["5:55 AM"], spoken: "Latest captured, 5:55 AM PT", isSelected: true),
            ],
            choicePresentation: .buttons(groupLabel: "Inspect recorded chances"), note: nil) : nil
        return FieldHistoryInput10868(
            title: "Valladolid’s win chance", caption: nil, series: [series],
            selection: .series(id: seriesID, missingWords: "Valladolid history unavailable"),
            domain: FieldHistoryDomain10868(lower: points.first!.x, upper: points.last!.x), ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.5, lines: ["50%"]),
                     FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: xTicks, guides: phase == .before ? [] : [Self.kickoffGuide], breaks: [],
            readout: phase == .live ? .beforeAndRecorded(beforeLabel: "Pre-match", recordedLabel: "Recorded") : .singleBefore(label: "Pre-match"),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow · pre-match", filled: nil),
            comparisonExplanation: nil, notes: ["Draw and Albacete history unavailable."],
            summary: "Valladolid win chance, recorded observations only.", plotHeight: 220,
            unboundReadingWords: "Not recorded", plotUnavailableWords: nil,
            windows: windows, scale: nil, moreOriginals: nil,
            details: action("history.details", "History & source details"),
            expand: action("history.expand", "Full chart", spoken: "Expand win probability history"),
            inspect: phase == .live ? action("history.inspect", "Inspect history") : nil,
            previous: nil, next: nil, inspection: inspection)
    }

    // MARK: Prop stories

    /// ARCHIVED (outcome key, quantity, pre-match chance); CONSTRUCTED figure text.
    private static let goalPins: [(id: String, quantity: Double, chance: Double, text: String)] = [
        ("64353423:242143183", 3, 0.5, "50%"),
        ("64353425:242143187", 5, 0.13, "13%"),
        ("64536538:242765587", 6, 0.06, "6%"),
    ]

    private static func goals(_ phase: SoccerEventPagePhase10868) -> TotalMilestoneInput10868 {
        let rows = goalPins.enumerated().map { index, goal -> TotalMilestoneRow10868 in
            let label = "\(Int(goal.quantity))+"
            let current: TotalMilestoneCurrent10868 = phase == .live
                ? (index == 0 ? .reached("Reached in play") : .withheld("Current chance withheld"))
                : .unavailable("Not started")
            let performance: String? = switch phase {
            case .before: nil
            case .live: ["Already reached", "1 more needed", "2 more needed"][index]
            case .final: index == 2 ? "Finished 1 short" : nil
            }
            let result: TotalMilestoneResult10868 = switch phase {
            case .before: .unconfirmed("Not started")
            case .live: .unconfirmed("Result pending")
            case .final: index == 2 ? .lost("Lost") : .won("Won")
            }
            return TotalMilestoneRow10868(
                id: goal.id, quantity: goal.quantity, quantityLabel: label, title: "\(label) goals",
                before: TotalMilestoneObservation10868(probability: goal.chance, text: goal.text, timeText: "4:47 AM PT",
                                                       accessibilityDetail: "\(label) goals pre-match · Oct 12, 4:47 AM PT · Polymarket"),
                beforeMissing: "No pre-match chance", current: current, performance: performance, result: result)
        }
        let actual: TotalMilestoneActual10868? = switch phase {
        case .before: nil
        case .live: .count(TotalMilestoneCount10868(quantity: 4, text: "4", unit: "goals", clock: "Observed 5:54 AM PT",
                                                     ruleLabel: "4 actual", accessibilityDetail: "Valladolid 4, Albacete 0 · observed Oct 12, 5:54 AM PT"))
        case .final: .count(TotalMilestoneCount10868(quantity: 5, text: "5", unit: "goals", clock: "Final",
                                                      ruleLabel: "5 actual", accessibilityDetail: "Final: Valladolid 5, Albacete 0"))
        }
        return TotalMilestoneInput10868(
            phase: phase.totalPhase, eyebrow: "TOTAL GOALS · EXPECTATIONS VS ACTUAL",
            title: phase == .final ? "Five goals. A 13% milestone reached." : phase == .live ? "Four goals. One more reaches five." : "How many goals?",
            chartTitle: "Chance of reaching each total", quantityAxisTitle: "Total goals in the game",
            milestones: rows, selectedMilestoneID: goalPins[phase == .before ? 0 : 1].id,
            actual: actual, projection: nil,
            quantityDomain: TotalMilestoneDomain10868(lower: 0, upper: 7),
            quantityTicks: ([(0, "0"), (3, "3+"), (5, "5+"), (6, "6+")] as [(Double, String)]).map { TotalMilestoneTick10868(value: $0.0, text: $0.1) },
            chanceTicks: ([(0, "0%"), (0.5, "50%"), (1, "100%")] as [(Double, String)]).map { TotalMilestoneTick10868(value: $0.0, text: $0.1) },
            timing: nil)
    }

    private static func both(_ phase: SoccerEventPagePhase10868) -> BothTeamsScoreInput10868 {
        func outcome(_ id: String, _ label: String, _ chance: Double, _ text: String, finalResult: BothTeamsResult10868) -> BothTeamsOutcome10868 {
            BothTeamsOutcome10868(
                id: id, label: label,
                before: BothTeamsObservation10868(probability: chance, text: text, timeText: "4:47 AM PT", accessibilityDetail: "\(label) pre-match · \(Self.pinProvenance)"),
                beforeMissing: "No pre-match chance",
                current: phase == .live ? .withheld("Current chance withheld") : .unavailable("Not started"),
                result: phase == .final ? finalResult : .unconfirmed(phase == .live ? "Result pending" : "Not started"))
        }
        let scoring: BothTeamsScoring10868 = switch phase {
        case .before:
            BothTeamsScoring10868(title: "Actual goals", home: BothTeamsTeam10868(name: "Valladolid", actual: .unavailable("Not started")),
                                  away: BothTeamsTeam10868(name: "Albacete", actual: .unavailable("Not started")), clock: nil, accessibilityDetail: nil)
        case .live:
            BothTeamsScoring10868(title: "Actual goals", home: BothTeamsTeam10868(name: "Valladolid", actual: .count(text: "4", status: "has scored")),
                                  away: BothTeamsTeam10868(name: "Albacete", actual: .count(text: "0", status: "yet to score")),
                                  clock: "Observed 5:54 AM PT", accessibilityDetail: "Valladolid 4, Albacete 0 · observed Oct 12, 5:54 AM PT")
        case .final:
            BothTeamsScoring10868(title: "Final goals", home: BothTeamsTeam10868(name: "Valladolid", actual: .count(text: "5", status: nil)),
                                  away: BothTeamsTeam10868(name: "Albacete", actual: .count(text: "0", status: nil)),
                                  clock: "Final", accessibilityDetail: "Final: Valladolid 5, Albacete 0")
        }
        return BothTeamsScoreInput10868(
            phase: phase.bothPhase, eventID: "15325054", marketID: "64353426", eyebrow: "BOTH TEAMS TO SCORE",
            subtitle: nil,
            title: phase == .final ? "Only Valladolid found the net." : phase == .live ? "Still waiting for Albacete" : nil,
            beforeContext: phase == .before ? "At least one goal each" : nil,
            outcomes: [outcome("242143189", "Yes", 0.55, "55%", finalResult: .lost("Lost")),
                       outcome("242143190", "No", 0.455, "45.5%", finalResult: .won("Won"))],
            selectedOutcomeID: "242143189", scoring: scoring, timing: nil)
    }

    private static let scoreCheckpoints: [(String, String, String)] = [
        ("2026-10-12T12:02:45.588824Z", "0–0", "5:02 AM"),
        ("2026-10-12T12:17:47.333487Z", "1–0", "5:17 AM"),
        ("2026-10-12T12:28:24.555020Z", "2–0", "5:28 AM"),
        ("2026-10-12T12:33:45.571562Z", "3–0", "5:33 AM"),
        ("2026-10-12T12:38:45.543600Z", "4–0", "5:38 AM"),
    ]

    private static func first(_ phase: SoccerEventPagePhase10868) -> FirstScorerComparisonInput10868 {
        func row(_ id: String, _ name: String, _ chance: Double, _ text: String, finalResult: FirstScorerResult10868) -> FirstScorerRow10868 {
            FirstScorerRow10868(
                id: id, name: name, team: nil,
                pregame: FirstScorerObservation10868(probability: chance, text: text, accessibilityDetail: "\(name) pre-match · \(Self.pinProvenance)"),
                pregameMissing: "No pre-match chance",
                current: .unavailable(phase == .live ? "Current chance withheld" : "Not started"),
                result: phase == .final ? finalResult : .unconfirmed(phase == .live ? "Result pending" : "Not started"))
        }
        let context = FirstScorerOutcomeContext10868(
            pregameTitle: "Pre-match chance", currentTitle: "Current chance", liveResultTitle: "Result",
            finalResultTitle: "Final result", selectionUnavailable: "Selected outcome unavailable.",
            spokenPregame: "Pre-match chance", spokenCurrent: "Current chance", spokenResult: "Result",
            selectHint: "Selects this outcome’s comparison")
        let path = phase == .live ? FirstScorerScorePath10868(
            title: "Observed scores", note: "Observation times, not exact goal times.",
            observations: scoreCheckpoints.map { checkpoint in
                FirstScorerScoreObservation10868(id: checkpoint.0, score: checkpoint.1, time: checkpoint.2,
                                                 accessibilityText: "\(checkpoint.1) · observed Oct 12, \(checkpoint.2) PT")
            }) : nil
        return FirstScorerComparisonInput10868(
            phase: phase.firstPhase,
            title: phase == .before ? "Who scores first?" : "Valladolid struck first",
            context: "FIRST TEAM TO SCORE · Polymarket",
            overview: [row("244237963", "Valladolid", 0.57, "57%", finalResult: .won("Won")),
                       row("244237965", "Neither", 0.065, "6.5%", finalResult: .lost("Lost")),
                       row("244237964", "Albacete", 0.335, "33.5%", finalResult: .lost("Lost"))],
            selectedID: "244237963", selectedRow: nil, plotTitle: "Pre-match chances",
            axis: FirstScorerAxis10868(lower: 0, upper: 1, ticks: [FirstScorerTick10868(value: 0, text: "0%"),
                                                                   FirstScorerTick10868(value: 0.5, text: "50%"),
                                                                   FirstScorerTick10868(value: 1, text: "100%")]),
            coverage: nil,
            confirmed: phase == .final ? FirstScorerConfirmed10868(id: "244237963", name: "Valladolid", caption: "First team to score · confirmed result") : nil,
            timing: nil, outcome: context, scorePath: path)
    }

    /// The final half-by-half comparison: each half's original pre-match chance
    /// and its own separately admitted settlement.
    private static let halves: PeriodOutcomeComparisonInput10868 = {
        func cell(_ id: String, _ period: String, _ chance: Double, _ text: String, _ result: PeriodOutcomeResult10868) -> PeriodOutcomeCell10868 {
            PeriodOutcomeCell10868(id: id, periodID: period,
                                   pregame: PeriodOutcomeObservation10868(probability: chance, text: text, accessibilityDetail: pinProvenance),
                                   pregameMissing: "No pre-match chance", current: .unavailable("Current chance unavailable"), result: result)
        }
        return PeriodOutcomeComparisonInput10868(
            phase: .final, eyebrow: "Half-by-half expectations", title: "Valladolid won both halves.",
            intro: "A draw had the highest pre-match chance for the first half.",
            periods: [PeriodOutcomePeriod10868(id: "first", label: "First half"), PeriodOutcomePeriod10868(id: "second", label: "Second half")],
            series: [
                PeriodOutcomeSeries10868(id: "home", label: "Valladolid", tint: homeColor, symbol: .circle, cells: [
                    cell("63178219:242338171", "first", 0.375, "37.5%", .won("Won")),
                    cell("63178218:246041831", "second", 0.43, "43%", .won("Won"))]),
                PeriodOutcomeSeries10868(id: "draw", label: "Draw", tint: drawColor, symbol: .square, cells: [
                    cell("63178219:242338170", "first", 0.425, "42.5%", .lost("Lost")),
                    cell("63178218:245875499", "second", 0.38, "38%", .lost("Lost"))]),
                PeriodOutcomeSeries10868(id: "away", label: "Albacete", tint: awayColor, symbol: .diamond, cells: [
                    cell("63178219:242338172", "first", 0.205, "20.5%", .lost("Lost")),
                    cell("63178218:245681743", "second", 0.23, "23%", .lost("Lost"))]),
            ],
            selectedSeriesID: "home", plotTitle: "Pre-match chances", scaleCaption: "0–50% scale",
            axis: PeriodOutcomeAxis10868(lower: 0, upper: 0.5, ticks: [PeriodOutcomeTick10868(value: 0, text: "0%"),
                                                                       PeriodOutcomeTick10868(value: 0.25, text: "25%"),
                                                                       PeriodOutcomeTick10868(value: 0.5, text: "50%")]),
            pointExplanation: "Each dot is a pre-match chance for that half.",
            lineExplanation: "Lines compare halves, not changes over time.",
            resultsTitle: "Final results · Valladolid",
            words: PeriodOutcomeWords10868(
                pregameTitle: "Pre-match chance", notStarted: "Not started", currentTitle: "Current chance",
                liveResultTitle: "Half result", finalResultTitle: "Final result",
                selectionUnavailable: "Selected outcome unavailable.", cellUnavailable: "Not offered for this half",
                selectHint: "Shows this outcome’s chances", detailsHint: "Opens the original prop"))
    }()

    // MARK: Stream and page

    private static func scope(_ phase: SoccerEventPagePhase10868) -> String { "soccer:15325054:\(phase)" }

    private static func stream(_ phase: SoccerEventPagePhase10868, wide: Bool = false) -> StoryStreamPresentation10868 {
        let scope = Self.scope(phase)
        let names: [(String, String)] = phase == .final
            ? [("goals", "Goal milestones"), ("halves", "Half-by-half expectations"), ("both", "Both teams to score"), ("first", "First team to score")]
            : [("goals", "Goal milestones"), ("both", "Both teams to score"), ("first", "First team to score")]
        func ref(_ id: String) -> StoryStreamPresentation10868.CardRef { .init(scope: scope, id: id) }
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: "THE MATCH IN PROBABILITIES", heading: "Explore the match",
            cards: names.map { StoryStreamPresentation10868.Card(id: $0.0, name: $0.1) },
            primary: ref("goals"), companion: ref(names[1].0), companionLabel: "Next", wide: wide,
            position: "1 of \(names.count)", status: "Cards advance when you’re watching",
            dwellFraction: 0.4, playback: .pause, previous: ref(names.last!.0), next: ref(names[1].0))
    }

    private static let stories: [SoccerEventPageStory10868] = [
        SoccerEventPageStory10868(cardID: "goals", card: .goals),
        SoccerEventPageStory10868(cardID: "both", card: .both),
        SoccerEventPageStory10868(cardID: "first", card: .first),
        SoccerEventPageStory10868(cardID: "halves", card: .halves),
    ]

    private static let copy = SoccerEventPageCopy10868(
        storiesLabel: "Match stories",
        storyUnavailable: "This story isn’t available for this match state. Every original is still in All props.",
        allPropsLabel: "All props · 98")

    private static func page(_ phase: SoccerEventPagePhase10868, wide: Bool = false) -> SoccerEventPageInput10868 {
        SoccerEventPageInput10868(
            phase: phase, header: header(phase), headline: headline(phase), history: history(phase),
            goals: goals(phase), both: both(phase), first: first(phase),
            halves: phase == .final ? halves : nil,
            stream: stream(phase, wide: wide), stories: stories, copy: copy)
    }

    // MARK: Phases

    @MainActor
    func testLiveMountsTheActualLeavesForTheRetainedMatchAtItsOwnPhase() {
        let input = Self.page(.live)
        let model = SoccerEventPageModel10868(input)
        let view = SoccerEventPagePresentation10868(input: input)
        XCTAssertEqual(view.mode, .page)

        XCTAssertEqual(view.headlineContent().input, input.headline)
        XCTAssertEqual(view.historyContent(reader: false).input, input.history)
        XCTAssertEqual(view.goalsContent()?.input, input.goals)
        XCTAssertEqual(view.goalsContent()?.input.phase, .during)
        XCTAssertEqual(view.bothContent()?.input, input.both)
        XCTAssertEqual(view.firstContent()?.input, input.first)
        // No half-by-half input at this snapshot: nothing is mounted in its place.
        XCTAssertNil(view.halvesContent())
        XCTAssertFalse(model.isMounted(.halves))

        // The live props keep their pre-match chances; current chances stay
        // withheld in the owner's words, and the published 15% appears nowhere.
        let milestones = input.goals!.milestones
        XCTAssertEqual(milestones.compactMap(\.before?.text), ["50%", "13%", "6%"])
        XCTAssertEqual(milestones.map(\.current), [.reached("Reached in play"),
                                                   .withheld("Current chance withheld"), .withheld("Current chance withheld")])
        XCTAssertFalse(String(describing: input).contains("15%"))
        XCTAssertEqual(input.goals?.actual, .count(TotalMilestoneCount10868(
            quantity: 4, text: "4", unit: "goals", clock: "Observed 5:54 AM PT", ruleLabel: "4 actual",
            accessibilityDetail: "Valladolid 4, Albacete 0 · observed Oct 12, 5:54 AM PT")))
        XCTAssertEqual(input.both?.outcomes.map(\.before?.text), ["55%", "45.5%"])
        XCTAssertEqual(input.first?.overview.compactMap(\.pregame?.text), ["57%", "6.5%", "33.5%"])
        // A live score implication settles nothing.
        XCTAssertTrue(milestones.allSatisfy { !$0.result.isAdmitted })
        XCTAssertTrue(input.first!.overview.allSatisfy { !$0.result.isAdmitted })
        XCTAssertNil(input.first?.confirmed)
    }

    @MainActor
    func testFinalMountsTheRequiredHalfComparisonAndEachResultStaysApartFromItsChance() {
        let input = Self.page(.final)
        let view = SoccerEventPagePresentation10868(input: input)
        XCTAssertEqual(view.headlineContent().input, input.headline)
        XCTAssertEqual(view.historyContent(reader: false).input, input.history)
        XCTAssertEqual(view.goalsContent()?.input.phase, .final)
        XCTAssertEqual(view.bothContent()?.input.phase, .final)
        XCTAssertEqual(view.firstContent()?.input.phase, .final)
        XCTAssertEqual(view.halvesContent()?.input, Self.halves)

        // Each original keeps its own pre-match chance beside its own settlement.
        XCTAssertEqual(input.goals!.milestones.map(\.result), [.won("Won"), .won("Won"), .lost("Lost")])
        XCTAssertEqual(input.goals!.milestones.compactMap(\.before?.text), ["50%", "13%", "6%"])
        XCTAssertEqual(input.both!.outcomes.map(\.result), [.lost("Lost"), .won("Won")])
        XCTAssertEqual(view.halvesContent()?.input.series.map { $0.cells.compactMap(\.pregame?.text) },
                       [["37.5%", "43%"], ["42.5%", "38%"], ["20.5%", "23%"]])
        XCTAssertEqual(view.halvesContent()?.input.series.map { $0.cells.map(\.result) },
                       [[.won("Won"), .won("Won")], [.lost("Lost"), .lost("Lost")], [.lost("Lost"), .lost("Lost")]])

        // The final score is a result, never a 100% quote: the headline keeps
        // the pre-match chance only.
        XCTAssertEqual(input.headline.primaryHeading.title, "Pre-match chance")
        XCTAssertEqual(input.headline.outcomes.compactMap(\.primary), ["48.9%"])
        XCTAssertNil(input.headline.comparisonHeading)
    }

    @MainActor
    func testABeforeKickoffSameMatchExampleShowsOnlyPreMatchContentAndRefusesLaterInputs() {
        let input = Self.page(.before)
        let model = SoccerEventPageModel10868(input)
        let view = SoccerEventPagePresentation10868(input: input)
        XCTAssertEqual(view.goalsContent()?.input.phase, .before)
        XCTAssertEqual(view.bothContent()?.input.phase, .before)
        XCTAssertEqual(view.firstContent()?.input.phase, .before)
        XCTAssertNil(view.halvesContent())
        XCTAssertNil(model.score)
        XCTAssertTrue(view.historyContent(reader: false).input.series.flatMap(\.runs).flatMap(\.points).allSatisfy { $0.x < Self.kickoffX })

        // Leak controls: a score, a clock, a projection comparison and later
        // props supplied to a pregame page are never shown or coerced.
        let live = Self.header(.live)
        let leakyHeader = SoccerEventPageHeader10868(
            state: input.header.state, date: input.header.date, home: "Valladolid", away: "Albacete",
            score: live.score, clock: live.clock,
            projection: SoccerEventPageProjection10868(title: "Projected final", reading: .value("2.6 goals"),
                                                       comparison: "1.4 goals above projection"),
            aboutLabel: input.header.aboutLabel)
        let leaky = SoccerEventPageInput10868(
            phase: .before, header: leakyHeader, headline: input.headline, history: input.history,
            goals: Self.goals(.live), both: Self.both(.final), first: Self.first(.live), halves: Self.halves,
            stream: input.stream, stories: input.stories, copy: input.copy)
        let leakyModel = SoccerEventPageModel10868(leaky)
        XCTAssertNil(leakyModel.score)
        XCTAssertNil(leakyModel.clock)
        XCTAssertNil(leakyModel.projectionComparison)
        XCTAssertEqual(leakyModel.projection?.reading, .value("2.6 goals"))
        for card in [SoccerEventPageCard10868.goals, .both, .first, .halves] {
            XCTAssertFalse(leakyModel.isMounted(card), "\(card)")
            XCTAssertNil(leakyModel.storyCard(card.rawValue), "\(card)")
            XCTAssertFalse(leakyModel.readerShows(card), "\(card)")
        }
        let leakyView = SoccerEventPagePresentation10868(input: leaky)
        XCTAssertNil(leakyView.goalsContent())
        XCTAssertNil(leakyView.bothContent())
        XCTAssertNil(leakyView.firstContent())
        XCTAssertNil(leakyView.halvesContent())
        XCTAssertTrue(leakyModel.readerShows(.history))
    }

    // MARK: Headline and header

    @MainActor
    func testThreeNamedOutcomesKeepTheirOwnIndependentAbsencesAndNoComplement() {
        let input = Self.page(.live)
        let headline = SoccerEventPagePresentation10868(input: input).headlineContent().input
        XCTAssertEqual(headline.outcomes.map(\.label), ["Valladolid win", "Draw", "Albacete win"])
        XCTAssertEqual(headline.primaryText(for: headline.home), .value("99.5%"))
        XCTAssertEqual(headline.comparisonText(for: headline.home), .value("48.9%"))
        for outcome in [headline.draw, headline.away] {
            // Each missing reading speaks its own reason; neither stands in for the other.
            XCTAssertEqual(headline.primaryText(for: outcome), .unavailable("No qualified in-match chance"))
            XCTAssertEqual(headline.comparisonText(for: outcome), .unavailable("No blended pre-match chance"))
        }
        // 100% − 99.5% and 100% − 48.9% are never shown for Draw or away.
        let shown = headline.outcomes.flatMap { [$0.primary, $0.comparison] }.compactMap { $0 }
        XCTAssertEqual(shown, ["99.5%", "48.9%"])
        XCTAssertFalse(shown.contains("0.5%"))
        XCTAssertFalse(shown.contains("51.1%"))

        // The full-size history keeps the same three outcomes in view.
        let reader = SoccerEventPagePresentation10868(input: input, mode: .reader(.history))
        XCTAssertEqual(reader.headlineContent().input, headline)
        XCTAssertEqual(reader.historyContent(reader: true).input.series.map(\.name), ["Valladolid win"])
    }

    func testScoreClockAndProjectionKeepTheOwnersWordsOrTheirAbsence() {
        let live = SoccerEventPageModel10868(Self.page(.live))
        XCTAssertEqual(live.score, .actual(home: "4", away: "0", context: "Score observed Oct 12, 5:54 AM PT",
                                           spoken: "Valladolid 4, Albacete 0"))
        XCTAssertEqual(live.clock, .unavailable("Match clock unavailable"))
        XCTAssertEqual(live.projection?.reading, .unavailable("No eligible projected final"))
        XCTAssertNil(live.projectionComparison)

        let final = SoccerEventPageModel10868(Self.page(.final))
        XCTAssertEqual(final.score, .actual(home: "5", away: "0", context: "Final score", spoken: "Final: Valladolid 5, Albacete 0"))
        XCTAssertNil(final.clock)
        // Unavailable stays unavailable at the final; no comparison is invented.
        XCTAssertEqual(final.projection?.reading, .unavailable("No eligible projected final"))
        XCTAssertNil(final.projectionComparison)

        // A comparison the owner supplies is shown once play has started; a
        // blank one draws nothing.
        func with(_ comparison: String?, phase: SoccerEventPagePhase10868) -> SoccerEventPageModel10868 {
            let base = Self.page(phase)
            let header = SoccerEventPageHeader10868(
                state: base.header.state, date: base.header.date, home: base.header.home, away: base.header.away,
                score: base.header.score, clock: base.header.clock,
                projection: SoccerEventPageProjection10868(title: "Projected final", reading: .value("2.6 goals"), comparison: comparison),
                aboutLabel: base.header.aboutLabel)
            return SoccerEventPageModel10868(SoccerEventPageInput10868(
                phase: phase, header: header, headline: base.headline, history: base.history, goals: base.goals,
                both: base.both, first: base.first, halves: base.halves, stream: base.stream, stories: base.stories, copy: base.copy))
        }
        XCTAssertEqual(with("2.4 goals above projection", phase: .final).projectionComparison, "2.4 goals above projection")
        XCTAssertEqual(with("1.4 goals above projection", phase: .live).projectionComparison, "1.4 goals above projection")
        XCTAssertNil(with("  ", phase: .final).projectionComparison)
        XCTAssertNil(with("2.4 goals above projection", phase: .before).projectionComparison)
    }

    func testEachRecordKeepsItsOwnClockAndTheChartStopsAtActualObservations() {
        // Live: the in-match chance and the pre-match chance carry different clocks.
        let live = Self.page(.live)
        XCTAssertEqual(live.headline.primaryHeading.context, "Oct 12, 5:55 AM PT · Bain Luck blend")
        XCTAssertEqual(live.headline.comparisonHeading?.context, "Oct 12, 4:59 AM PT")
        // Every prop record carries its own observation, never a shared or borrowed one.
        XCTAssertEqual(live.goals!.milestones.compactMap(\.before?.probability), Self.goalPins.map { $0.chance })
        XCTAssertTrue(live.goals!.milestones.allSatisfy { $0.before?.timeText != nil })
        XCTAssertEqual(Set(live.goals!.milestones.compactMap(\.before?.accessibilityDetail)).count, 3)
        // Score checkpoints are observation clocks in the owner's order, not goal times.
        XCTAssertEqual(live.first?.scorePath?.observations.map(\.score), ["0–0", "1–0", "2–0", "3–0", "4–0"])
        XCTAssertEqual(live.first?.scorePath?.observations.map(\.id), Self.scoreCheckpoints.map { $0.0 })
        // The one guide is the known kickoff; no half or goal guide is drawn.
        XCTAssertEqual(live.history.guides, [Self.kickoffGuide])
        XCTAssertEqual(Self.page(.final).history.guides, [Self.kickoffGuide])
        XCTAssertEqual(Self.page(.before).history.guides, [])
        XCTAssertEqual(live.history.guides.first?.x, Self.kickoffX)

        // The reduced subset keeps its captured spans apart: an omitted span is
        // a new run, never a line across it.
        XCTAssertEqual(live.history.series[0].runs.map { $0.points.map(\.x) },
                       [[Self.preMatchX, Self.kickoffX, Self.minuteOneX], [Self.minute29X], [Self.live1255X, Self.liveHeadlineX]])
        XCTAssertEqual(Self.page(.final).history.series[0].runs.map { $0.points.map(\.x) },
                       [[Self.preMatchX, Self.kickoffX, Self.minuteOneX], [Self.minute29X], [Self.final1352X, Self.finalLastX]])
        XCTAssertEqual(Self.page(.before).history.series[0].runs.map { $0.points.map(\.x) },
                       [[Self.octFive1230X, Self.octFive1330X], [Self.preMatchX]])

        // The live chart ends at the in-match observation the headline names.
        let livePoints = live.history.series[0].runs.flatMap(\.points)
        XCTAssertEqual(livePoints.last?.x, Self.liveHeadlineX)
        XCTAssertEqual(livePoints.last?.probability, 0.995)
        XCTAssertEqual(live.history.domain.upper, Self.liveHeadlineX)

        // The final chart stops at its last observation, before the completed
        // time; the terminal result row is not a point.
        let final = Self.page(.final)
        let finalPoints = final.history.series[0].runs.flatMap(\.points)
        XCTAssertEqual(finalPoints.last?.x, Self.finalLastX)
        XCTAssertEqual(final.history.domain.upper, Self.finalLastX)
        XCTAssertTrue(finalPoints.allSatisfy { $0.x < Self.completedX && $0.probability < 1 })
        XCTAssertEqual(finalPoints.first, FieldHistoryPoint10868(id: "\(Self.seriesID)#1159", x: Self.preMatchX, probability: 0.4892, style: .hollow))
    }

    // MARK: Stream wiring and readers

    @MainActor
    func testStoryCardsResolveOnlyTheOwnersExactLinksAndReadersReuseTheSameLeaves() {
        let live = SoccerEventPageModel10868(Self.page(.live))
        XCTAssertEqual(live.storyCard("goals"), .goals)
        XCTAssertEqual(live.storyCard("both"), .both)
        XCTAssertEqual(live.storyCard("first"), .first)
        // Linked, but this phase has no half-by-half input: unavailable, not a neighbour.
        XCTAssertNil(live.storyCard("halves"))
        XCTAssertNil(live.storyCard("corners"))
        XCTAssertNil(live.storyCard("Goals"))

        let final = SoccerEventPageModel10868(Self.page(.final))
        XCTAssertEqual(final.input.stream.cards.map(\.id).compactMap(final.storyCard), [.goals, .halves, .both, .first])

        // A duplicated link or a link to the anchor names no story.
        let base = Self.page(.live)
        let ambiguous = SoccerEventPageModel10868(SoccerEventPageInput10868(
            phase: .live, header: base.header, headline: base.headline, history: base.history, goals: base.goals,
            both: base.both, first: base.first, halves: nil, stream: base.stream,
            stories: [SoccerEventPageStory10868(cardID: "goals", card: .goals),
                      SoccerEventPageStory10868(cardID: "goals", card: .both),
                      SoccerEventPageStory10868(cardID: "chart", card: .history)],
            copy: base.copy))
        XCTAssertNil(ambiguous.storyCard("goals"))
        XCTAssertNil(ambiguous.storyCard("chart"))

        // Full-size content is the same leaf with the same input.
        let input = Self.page(.final)
        for card in SoccerEventPageCard10868.allCases {
            XCTAssertTrue(SoccerEventPageModel10868(input).readerShows(card), "\(card)")
        }
        XCTAssertEqual(SoccerEventPagePresentation10868(input: input, mode: .reader(.goals)).goalsContent()?.input, input.goals)
        XCTAssertEqual(SoccerEventPagePresentation10868(input: input, mode: .reader(.both)).bothContent()?.input, input.both)
        XCTAssertEqual(SoccerEventPagePresentation10868(input: input, mode: .reader(.first)).firstContent()?.input, input.first)
        XCTAssertEqual(SoccerEventPagePresentation10868(input: input, mode: .reader(.halves)).halvesContent()?.input, input.halves)
        XCTAssertFalse(live.readerShows(.halves))
    }

    @MainActor
    func testACardActionRequestsTheStreamHoldBeforeTheExactLeafCallbackAndNothingFiresPassively() {
        var log: [String] = []
        let input = Self.page(.final, wide: true)
        let view = SoccerEventPagePresentation10868(
            input: input,
            onAbout: { log.append("about") },
            onAllProps: { log.append("allProps") },
            onStoryIntent: { _ in log.append("stream") },
            onHistoryAction: { log.append("history:\($0)") },
            onHistoryInspectionChoice: { log.append("inspect:\($0)") },
            onHistoryPlotPosition: { log.append("plot:\($0)") },
            onGoalSelect: { log.append("goal:\($0)") },
            onGoalDetails: { log.append("goalDetails:\($0)") },
            onBothSelect: { log.append("both:\($0.outcomeID)") },
            onBothDetails: { log.append("bothDetails:\($0.outcomeID)") },
            onFirstSelect: { log.append("first:\($0)") },
            onFirstDetails: { log.append("firstDetails:\($0)") },
            onHalfSelect: { log.append("half:\($0)") },
            onHalfDetails: { log.append("halfDetails:\($0)") }
        )

        // The activation the real stream hands each displayed card: the primary
        // (goals) and, in the owner's wide presentation, its companion (halves).
        let stream = input.stream
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        func activation(_ id: String) -> StoryStreamCardActivation10868 {
            let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: id)
            return StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
                if case .interaction(_, let card) = intent { log.append("hold:\(card?.id ?? "-")") } else { log.append("other") }
            }
        }
        XCTAssertTrue(activation("goals").isAvailable)
        XCTAssertTrue(activation("halves").isAvailable)

        // Building every leaf, in stream, page and reader form, acts on nothing.
        let goals = view.goalsContent(activation: activation("goals"))!
        let halves = view.halvesContent(activation: activation("halves"))!
        let both = view.bothContent(activation: activation("both"))!
        let readerGoals = SoccerEventPagePresentation10868(input: input, mode: .reader(.goals),
                                                           onGoalSelect: { log.append("goal:\($0)") }).goalsContent()!
        let anchor = view.historyContent(reader: false)
        let readerHistory = view.historyContent(reader: true)
        _ = view.headlineContent()
        _ = view.firstContent()
        XCTAssertEqual(log, [])

        // In the stream: hold first, then the exact leaf action.
        goals.onSelect?("64353425:242143187")
        goals.onDetails?("64536538:242765587")
        halves.onSelect?("draw")
        halves.onDetails?("63178218:246041831")
        XCTAssertEqual(log, ["hold:goals", "goal:64353425:242143187", "hold:goals", "goalDetails:64536538:242765587",
                             "hold:halves", "half:draw", "hold:halves", "halfDetails:63178218:246041831"])

        // A card the stream is not displaying asks for no hold; its action still reaches the host.
        log = []
        both.onSelect?(BothTeamsOutcomeRef10868(eventID: "15325054", marketID: "64353426", outcomeID: "242143190"))
        XCTAssertEqual(log, ["both:242143190"])

        // Full-size content: the exact callback, and no hold from appearing or acting.
        log = []
        readerGoals.onSelect?("64353423:242143183")
        view.firstContent()?.onDetails?("244237964")
        view.bothContent()?.onDetails?(BothTeamsOutcomeRef10868(eventID: "15325054", marketID: "64353426", outcomeID: "242143189"))
        view.halvesContent()?.onSelect?("away")
        anchor.onAction?("history.expand")
        readerHistory.onAction?("history.details")
        anchor.onInspectionChoice?("choice.latest")
        anchor.onPlotPosition?(Self.minute29X)
        view.openAbout()
        view.openAllProps()
        XCTAssertEqual(log, ["goal:64353423:242143183", "firstDetails:244237964", "bothDetails:242143189", "half:away",
                             "history:history.expand", "history:history.details", "inspect:choice.latest",
                             "plot:\(Self.minute29X)", "about", "allProps"])

        // Without host callbacks a leaf has no action even inside the stream,
        // and no page control acts.
        let quiet = SoccerEventPagePresentation10868(input: input)
        XCTAssertNil(quiet.goalsContent(activation: activation("goals"))?.onSelect)
        XCTAssertNil(quiet.halvesContent(activation: activation("halves"))?.onDetails)
        XCTAssertNil(quiet.bothContent()?.onSelect)
        XCTAssertNil(quiet.firstContent()?.onDetails)
        XCTAssertNil(quiet.historyContent(reader: false).onAction)
        let model = SoccerEventPageModel10868(input)
        XCTAssertFalse(model.aboutAvailable(canOpen: false))
        XCTAssertFalse(model.allPropsAvailable(canOpen: false))
        log = []
        quiet.openAbout()
        quiet.openAllProps()
        XCTAssertEqual(log, [])
    }

    @MainActor
    func testATimingDisclosureInTheStreamRequestsTheHoldBeforeItWritesAndAReaderPassesTheOwnersBindingThrough() {
        var log: [String] = []
        var expanded: [String: Bool] = ["goal": false, "both": true, "first": false]
        func owner(_ key: String) -> Binding<Bool> {
            Binding(get: { expanded[key]! }, set: { log.append("\(key)Timing:\($0)"); expanded[key] = $0 })
        }
        let input = Self.page(.live)
        let view = SoccerEventPagePresentation10868(
            input: input,
            goalTimingExpanded: owner("goal"), bothTimingExpanded: owner("both"), firstTimingExpanded: owner("first"))

        // The real stream's hook for a displayed card: goals as primary, and
        // first as primary with both as its wide companion.
        func activation(_ id: String, primary: String) -> StoryStreamCardActivation10868 {
            var stream = input.stream
            func ref(_ id: String) -> StoryStreamPresentation10868.CardRef { .init(scope: stream.scope, id: id) }
            stream.primary = ref(primary)
            stream.companion = ref("both")
            stream.wide = true
            let resolved = stream.resolve(reduceMotion: false, actionable: true)
            return StoryStreamCardActivation10868(card: ref(id), intents: stream.activationIntents(for: ref(id), resolved: resolved)) { intent in
                if case .interaction(_, let card) = intent { log.append("hold:\(card?.id ?? "-")") } else { log.append("other") }
            }
        }
        let goalHook = activation("goals", primary: "goals")
        let bothHook = activation("both", primary: "first")
        let firstHook = activation("first", primary: "first")
        XCTAssertTrue(goalHook.isAvailable && bothHook.isAvailable && firstHook.isAvailable)

        // The bindings the actual child Views receive. Building and reading them
        // acts on nothing and shows the owner's value.
        let goal = view.goalsContent(activation: goalHook)!.timingExpanded!
        let both = view.bothContent(activation: bothHook)!.timingExpanded!
        let first = view.firstContent(activation: firstHook)!.timingExpanded!
        XCTAssertEqual([goal.wrappedValue, both.wrappedValue, first.wrappedValue], [false, true, false])
        XCTAssertEqual(log, [])

        // Opening or closing: the hold first, then the exact new value to the owner.
        goal.wrappedValue = true
        both.wrappedValue = false
        first.wrappedValue = true
        XCTAssertEqual(log, ["hold:goals", "goalTiming:true", "hold:both", "bothTiming:false", "hold:first", "firstTiming:true"])
        XCTAssertEqual(expanded, ["goal": true, "both": false, "first": true])
        XCTAssertEqual([goal.wrappedValue, both.wrappedValue, first.wrappedValue], [true, false, true])

        // Full-size content: the owner's binding passes straight through, no hold.
        log = []
        let reader = SoccerEventPagePresentation10868(
            input: input, mode: .reader(.goals),
            goalTimingExpanded: owner("goal"), bothTimingExpanded: owner("both"), firstTimingExpanded: owner("first"))
        reader.goalsContent()!.timingExpanded!.wrappedValue = false
        reader.bothContent()!.timingExpanded!.wrappedValue = true
        reader.firstContent()!.timingExpanded!.wrappedValue = false
        XCTAssertEqual(log, ["goalTiming:false", "bothTiming:true", "firstTiming:false"])

        // No owner binding: none, in the stream or full size.
        let quiet = SoccerEventPagePresentation10868(input: input)
        XCTAssertNil(quiet.goalsContent(activation: goalHook)?.timingExpanded)
        XCTAssertNil(quiet.bothContent(activation: bothHook)?.timingExpanded)
        XCTAssertNil(quiet.firstContent()?.timingExpanded)
        XCTAssertEqual(log, ["goalTiming:false", "bothTiming:true", "firstTiming:false"])
    }

    @MainActor
    func testTheFullSizeHistoryDropsOnlyItsExpandControlAndKeepsInspectionAndWindows() {
        for phase in [SoccerEventPagePhase10868.live, .final] {
            let input = Self.page(phase)
            let view = SoccerEventPagePresentation10868(input: input, mode: .reader(.history))
            XCTAssertEqual(view.historyContent(reader: false).input.expand?.id, "history.expand")
            let reader = view.historyContent(reader: true).input
            XCTAssertNil(reader.expand)
            XCTAssertEqual(reader.layout, .expanded)
            XCTAssertEqual(input.history.layout, .cohortAbove)

            let page = Mirror(reflecting: input.history).children.map { ($0.label ?? "", String(describing: $0.value)) }
            let full = Mirror(reflecting: reader).children.map { ($0.label ?? "", String(describing: $0.value)) }
            XCTAssertEqual(page.map(\.0), full.map(\.0))
            for (owner, shown) in zip(page, full) where owner.0 != "expand" && owner.0 != "layout" {
                XCTAssertEqual(owner.1, shown.1, "\(phase) \(owner.0)")
            }
            XCTAssertEqual(FieldHistoryGeometry10868.actions(reader).map(\.id),
                           FieldHistoryGeometry10868.actions(input.history).map(\.id).filter { $0 != "history.expand" })
        }
        XCTAssertNotNil(SoccerEventPageModel10868(Self.page(.live)).readerHistory.inspection)
        XCTAssertNotNil(SoccerEventPageModel10868(Self.page(.final)).readerHistory.windows)
    }

    // MARK: Arrangement

    func testCompactAndAccessibilitySizesStackAndAWideOrUnspecifiedWidthTriesSideBySideFirst() {
        XCTAssertEqual(SoccerEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(SoccerEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(SoccerEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(SoccerEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertEqual(SoccerEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: true), [.stacked])
        XCTAssertEqual(SoccerEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: true), [.stacked])
    }
}

// MARK: - All props and the selected original's Details

/// The catalogue and Details content modes, made of the existing
/// `OriginalMarketCatalogueView9483` and `OriginalMarketDetailsView9483`.
/// Asserted: those actual leaves are mounted with the owner's originals group
/// and exact callbacks unchanged; each original keeps its own pre-match chance,
/// its withheld live reading, its historical last quote and its separately
/// admitted grade apart; selections and history intents reach the owner
/// exactly; and entering either mode calls nothing. The leaves' own rules stay
/// with their own tests.
///
/// A SMALL, explicitly labelled SUBSET of the 98 retained originals — rows 1,
/// 4 and 5 of `liveSoccer.json` / `soccerFinal.json`, the same keys at the same
/// rows — NOT the catalogue obligation; it proves no full 98-card native fit:
/// - row 1, `totals:64536548:242765608`, Albacete Balompié O/U 1.5 Under: no
///   pre-match baseline; final result unconfirmed (no result evidence), even
///   though the 5–0 score would satisfy it;
/// - row 4, `totals:64353425:242143187`, O/U 4.5 Over (5+ goals): pre-match
///   0.13 at 11:47:12.057085Z; final won (`prop-64353425.json`);
/// - row 5, `totals:64536538:242765587`, O/U 5.5 Over (6+ goals): pre-match
///   0.06 at 11:47:12.068367Z; final lost (`prop-64536538.json`);
/// - during play each row's published display reads 0.15 at
///   12:55:39.585325Z: not an admitted current chance, shown only as the
///   labelled historical last quote in Details.
///
/// CONSTRUCTED owner input: the scope, display words, figure text, labels,
/// rules words, the "Market ID" row, modes, heading, context and tint.
/// The leaf types are main-actor isolated in the app target, so this whole
/// extension is too.
@MainActor
extension SoccerEventPagePresentation10868Tests {
    private typealias Originals = OriginalMarketDetails9483

    private static let underOneHalf = Originals.Identity(source: "polymarket", market: "64536548", side: "242765608")
    private static let fiveGoals = Originals.Identity(source: "polymarket", market: "64353425", side: "242143187")
    private static let sixGoals = Originals.Identity(source: "polymarket", market: "64536538", side: "242765587")
    private static let fiveGoalsTitle = "Real Valladolid CF vs. Albacete Balompié: O/U 4.5"
    private static let withheld = "Current chance withheld"
    private static let noBaseline = "No qualified pre-match baseline"
    private static let rulesUnavailable = "Rules not retained for this original"
    private static let lastQuote = Originals.HistoricalQuote(text: "15%", recorded: "Oct 12, 5:55 AM PT")

    private static func originalsScope(_ phase: SoccerEventPagePhase10868) -> String { "\(scope(phase)):originals" }

    private static func original(_ identity: Originals.Identity, title: String, outcome: String,
                                 pregame: (text: String, value: Double)?, phase: SoccerEventPagePhase10868,
                                 grade: String?) -> Originals.Original {
        let before = pregame.map {
            Originals.Reading.value($0.text, placement: $0.value, provenance: pinProvenance)
        } ?? .missing(noBaseline)
        return Originals.Original(
            identity: identity, title: title, outcome: outcome,
            mode: phase == .final ? .result : .comparison(.current),
            pregame: before,
            later: phase == .final ? nil : .missing(withheld),
            grade: grade.map { Originals.Grade(words: $0, provenance: nil) },
            about: Originals.About(source: "Polymarket", rules: .unavailable(rulesUnavailable),
                                   provenance: [Originals.Row(label: "Market ID", value: identity.market)],
                                   historicalQuote: phase == .final ? nil : lastQuote))
    }

    private static func originals(_ phase: SoccerEventPagePhase10868,
                                  holding held: Originals.Identity? = SoccerEventPagePresentation10868Tests.fiveGoals)
        -> SoccerEventPageOriginals10868 {
        let rows = [
            original(underOneHalf, title: "Real Valladolid CF vs. Albacete Balompié: Albacete Balompié O/U 1.5",
                     outcome: "Under", pregame: nil, phase: phase, grade: nil),
            original(fiveGoals, title: fiveGoalsTitle, outcome: "Over", pregame: ("13%", 0.13), phase: phase,
                     grade: phase == .final ? "Won" : nil),
            original(sixGoals, title: "Real Valladolid CF vs. Albacete Balompié: O/U 5.5", outcome: "Over",
                     pregame: ("6%", 0.06), phase: phase, grade: phase == .final ? "Lost" : nil),
        ]
        let scope = originalsScope(phase)
        return SoccerEventPageOriginals10868(
            catalogue: Originals.Catalogue(scope: scope, originals: rows),
            selection: held.map { Originals.Selection(scope: scope, identity: $0) },
            labels: Dictionary(uniqueKeysWithValues: rows.map { ($0.identity, "\($0.title) · \($0.outcome)") }),
            heading: "All props",
            context: phase == .final ? "98 retained originals" : "98 retained originals · current chances withheld",
            emptyWords: "No retained originals for this match",
            unavailableChoice: "Unnamed original",
            tint: homeColor)
    }

    /// The cards the mounted catalogue draws, by the leaf's own model.
    private static func cards(_ view: OriginalMarketCatalogueView9483) -> [OriginalMarketCatalogue9483.Card] {
        OriginalMarketCatalogue9483.cards(catalogue: view.catalogue, selection: view.selection,
                                          labels: view.labels, unavailableChoice: view.unavailableChoice)
    }

    /// The Details the mounted leaf draws for its own inputs.
    private static func details(_ view: OriginalMarketDetailsView9483) -> Originals.Content? {
        Originals.content(catalogue: view.catalogue, selection: view.selection)
    }

    func testAllPropsMountsTheExistingCatalogueWithEveryOwnerOriginalInOrderAndNoPublishedLiveValue() {
        let originals = Self.originals(.live)
        let view = SoccerEventPagePresentation10868(input: Self.page(.live), mode: .catalogue, originals: originals)
        let catalogue = view.catalogueContent()!
        XCTAssertEqual(catalogue.catalogue, originals.catalogue)
        XCTAssertEqual(catalogue.selection, originals.selection)
        XCTAssertEqual(catalogue.labels, originals.labels)
        XCTAssertEqual([catalogue.heading, catalogue.context, catalogue.emptyWords, catalogue.unavailableChoice],
                       ["All props", "98 retained originals · current chances withheld",
                        "No retained originals for this match", "Unnamed original"])

        // One card per supplied original, in the owner's order, full name and outcome kept.
        let cards = Self.cards(catalogue)
        XCTAssertEqual(cards.map(\.choice.label), [
            "Real Valladolid CF vs. Albacete Balompié: Albacete Balompié O/U 1.5 · Under",
            "Real Valladolid CF vs. Albacete Balompié: O/U 4.5 · Over",
            "Real Valladolid CF vs. Albacete Balompié: O/U 5.5 · Over",
        ])
        XCTAssertEqual(cards.map(\.choice.isSelected), [false, true, false])
        XCTAssertTrue(cards.allSatisfy { $0.choice.isAvailable && $0.content != nil })

        // Each card keeps its own pre-match figure or its own missing words, and
        // the later slot keeps the owner's withheld words — never the published 15%.
        XCTAssertEqual(cards.map { $0.content!.readings.map(\.text) }, [
            [Self.noBaseline, Self.withheld], ["13%", Self.withheld], ["6%", Self.withheld],
        ])
        XCTAssertEqual(cards.map { $0.content!.readings.map(\.isValue) }, [[false, false], [true, false], [true, false]])
        XCTAssertTrue(cards.allSatisfy { $0.content!.result == nil })
        XCTAssertFalse(cards.flatMap { $0.content!.readings.map(\.text) }.contains("15%"))

        // The owner's empty words when it has no admitted catalogue.
        let none = SoccerEventPageOriginals10868(
            catalogue: nil, selection: nil, heading: "All props", emptyWords: "No retained originals for this match",
            unavailableChoice: "Unnamed original", tint: Self.homeColor)
        let empty = SoccerEventPagePresentation10868(input: Self.page(.live), mode: .catalogue, originals: none)
        XCTAssertEqual(Self.cards(empty.catalogueContent()!), [])
        XCTAssertEqual(empty.catalogueContent()?.emptyWords, "No retained originals for this match")
    }

    func testLiveDetailsKeepTheOwnPreMatchChanceTheWithheldCurrentSlotAndTheHistoricalLastQuoteApart() {
        let originals = Self.originals(.live)
        let view = SoccerEventPagePresentation10868(input: Self.page(.live), mode: .original, originals: originals)
        let mounted = view.originalDetailsContent()!
        XCTAssertEqual(mounted.catalogue, originals.catalogue)
        XCTAssertEqual(mounted.selection, originals.selection)
        XCTAssertNil(mounted.recorded)

        let content = Self.details(mounted)!
        XCTAssertEqual(content.title, Self.fiveGoalsTitle)
        XCTAssertEqual(content.outcome, "Over")
        XCTAssertEqual(content.readings, [
            Originals.ShownReading(label: "Pregame chance", marker: .hollow, text: "13%", isValue: true,
                                   provenance: Self.pinProvenance, placement: 0.13),
            Originals.ShownReading(label: "Current chance", marker: .solid, text: Self.withheld, isValue: false,
                                   provenance: nil, placement: nil),
        ])
        XCTAssertNil(content.result)
        // The last published value is a dated historical row in About, never a reading.
        XCTAssertEqual(content.about, [
            Originals.Row(label: "Market", value: Self.fiveGoalsTitle),
            Originals.Row(label: "Outcome", value: "Over"),
            Originals.Row(label: "Source", value: "Polymarket"),
            Originals.Row(label: "Market ID", value: "64353425"),
            Originals.Row(label: "Last recorded probability (historical)", value: "15%, recorded Oct 12, 5:55 AM PT"),
        ])
        XCTAssertEqual(content.rules, .unavailable(Self.rulesUnavailable))

        // An original with no baseline keeps both slots' own words.
        let unbased = Self.details(SoccerEventPagePresentation10868(
            input: Self.page(.live), mode: .original,
            originals: Self.originals(.live, holding: Self.underOneHalf)).originalDetailsContent()!)!
        XCTAssertEqual(unbased.readings.map(\.text), [Self.noBaseline, Self.withheld])
        XCTAssertTrue(unbased.marks.isEmpty)
    }

    func testFinalDetailsShowEachSeparatelyAdmittedGradeAndTheScoreSettlesNoUnconfirmedOriginal() {
        func shown(_ held: Originals.Identity) -> Originals.Content? {
            Self.details(SoccerEventPagePresentation10868(
                input: Self.page(.final), mode: .original,
                originals: Self.originals(.final, holding: held)).originalDetailsContent()!)
        }
        let five = shown(Self.fiveGoals)!
        XCTAssertEqual(five.readings.map(\.label), ["Pregame chance"])
        XCTAssertEqual(five.readings.map(\.text), ["13%"])
        XCTAssertEqual(five.result, Originals.ShownResult(words: "Won", provenance: "Settlement time unknown"))
        XCTAssertEqual(shown(Self.sixGoals)?.result?.words, "Lost")
        XCTAssertEqual(shown(Self.sixGoals)?.readings.map(\.text), ["6%"])

        // No admitted grade: the leaf's own words, not "Won" from a 5–0 score.
        let under = shown(Self.underOneHalf)!
        XCTAssertEqual(under.readings.map(\.text), [Self.noBaseline])
        XCTAssertEqual(under.result, Originals.ShownResult(words: "Result unavailable", provenance: nil))

        // The final catalogue cards carry the same grades beside their own chances.
        let cards = Self.cards(SoccerEventPagePresentation10868(
            input: Self.page(.final), mode: .catalogue, originals: Self.originals(.final)).catalogueContent()!)
        XCTAssertEqual(cards.map { $0.content?.result?.words }, ["Result unavailable", "Won", "Lost"])
        XCTAssertEqual(cards.map { $0.content!.readings.map(\.text) }, [[Self.noBaseline], ["13%"], ["6%"]])
    }

    func testACardTapHandsTheOwnerTheExactScopeAndIdentityAndAHistoryIntentPassesUnchanged() {
        var selections: [Originals.Selection] = []
        var intents: [Originals.HistoryIntent] = []
        let originals = Self.originals(.final, holding: nil)
        let view = SoccerEventPagePresentation10868(
            input: Self.page(.final), mode: .catalogue, originals: originals,
            onOriginalSelect: { selections.append($0) }, onOriginalHistory: { intents.append($0) })

        let catalogue = view.catalogueContent()!
        for card in Self.cards(catalogue) {
            OriginalMarketCatalogue9483.action(card, onSelect: catalogue.onSelect)?()
        }
        let scope = Self.originalsScope(.final)
        XCTAssertEqual(selections, [Self.underOneHalf, Self.fiveGoals, Self.sixGoals].map {
            Originals.Selection(scope: scope, identity: $0)
        })

        let intent = Originals.HistoryIntent(selection: selections[1], entry: .explore, actionID: "original.history.explore")
        view.originalDetailsContent()!.onHistory?(intent)
        XCTAssertEqual(intents, [intent])

        // A foreign-scope selection opens no Details, and a duplicated identity
        // cannot open: the leaf's own rules, not a second validator here.
        let foreign = SoccerEventPageOriginals10868(
            catalogue: originals.catalogue, selection: Originals.Selection(scope: Self.originalsScope(.live), identity: Self.fiveGoals),
            heading: "All props", emptyWords: "No retained originals for this match",
            unavailableChoice: "Unnamed original", tint: Self.homeColor)
        XCTAssertNil(Self.details(SoccerEventPagePresentation10868(input: Self.page(.final), originals: foreign).originalDetailsContent()!))
        let five = originals.catalogue!.originals[1]
        let doubled = SoccerEventPageOriginals10868(
            catalogue: Originals.Catalogue(scope: scope, originals: [five, five]), selection: nil,
            heading: "All props", emptyWords: "No retained originals for this match",
            unavailableChoice: "Unnamed original", tint: Self.homeColor)
        let twins = Self.cards(SoccerEventPagePresentation10868(input: Self.page(.final), originals: doubled,
                                                                onOriginalSelect: { selections.append($0) }).catalogueContent()!)
        XCTAssertEqual(twins.map(\.choice.isAvailable), [false, false])
        XCTAssertTrue(twins.allSatisfy { OriginalMarketCatalogue9483.action($0, onSelect: { selections.append($0) }) == nil })
    }

    func testEnteringEitherModeActsOnNothingAndWithoutCallbacksNothingPretends() {
        var log: [String] = []
        for phase in [SoccerEventPagePhase10868.live, .final] {
            for mode in [SoccerEventPageMode10868.catalogue, .original] {
                let view = SoccerEventPagePresentation10868(
                    input: Self.page(phase), mode: mode, originals: Self.originals(phase),
                    onAbout: { log.append("about") }, onAllProps: { log.append("allProps") },
                    onOriginalSelect: { log.append("select:\($0.identity.side)") },
                    onOriginalHistory: { log.append("history:\($0.actionID)") },
                    onStoryIntent: { _ in log.append("stream") },
                    onHistoryAction: { log.append("chart:\($0)") },
                    onGoalSelect: { log.append("goal:\($0)") })
                XCTAssertEqual(view.mode, mode)
                let catalogue = view.catalogueContent()!
                let details = view.originalDetailsContent()!
                _ = Self.cards(catalogue)
                _ = Self.details(details)
                XCTAssertNotNil(catalogue.onSelect)
                XCTAssertNotNil(details.onHistory)
            }
        }
        // No selection, history, hold, resume or page action from appearing.
        XCTAssertEqual(log, [])

        // No callbacks: every card is static content and the history is static.
        let quiet = SoccerEventPagePresentation10868(input: Self.page(.live), mode: .catalogue, originals: Self.originals(.live))
        XCTAssertNil(quiet.catalogueContent()?.onSelect)
        XCTAssertNil(quiet.originalDetailsContent()?.onHistory)
        XCTAssertTrue(Self.cards(quiet.catalogueContent()!).allSatisfy {
            OriginalMarketCatalogue9483.action($0, onSelect: quiet.catalogueContent()?.onSelect) == nil
        })
        // No originals group: neither mode has content.
        XCTAssertNil(SoccerEventPagePresentation10868(input: Self.page(.live), mode: .catalogue).catalogueContent())
        XCTAssertNil(SoccerEventPagePresentation10868(input: Self.page(.live), mode: .original).originalDetailsContent())
    }

    func testExistingCallSitesKeepTheirPageAndAllPropsStaysTheOwnersOwnAction() {
        var log: [String] = []
        let input = Self.page(.final)
        let view = SoccerEventPagePresentation10868(input: input, onAllProps: { log.append("allProps") })
        XCTAssertEqual(view.mode, .page)
        XCTAssertNil(view.originals)
        XCTAssertNil(view.onOriginalSelect)
        XCTAssertNil(view.onOriginalHistory)
        XCTAssertNil(view.catalogueContent())
        XCTAssertNil(view.originalDetailsContent())
        XCTAssertEqual(view.goalsContent()?.input, input.goals)
        XCTAssertEqual(view.historyContent(reader: false).input, input.history)

        // The page input is the same eleven owner fields; originals ride beside it.
        XCTAssertEqual(Mirror(reflecting: input).children.map(\.label), [
            "phase", "header", "headline", "history", "goals", "both", "first", "halves", "stream", "stories", "copy",
        ])

        // "All props" opens the owner's catalogue; it selects no original.
        let withOriginals = SoccerEventPagePresentation10868(
            input: input, originals: Self.originals(.final, holding: nil),
            onAllProps: { log.append("allProps") }, onOriginalSelect: { log.append("select:\($0.identity.side)") })
        view.openAllProps()
        withOriginals.openAllProps()
        XCTAssertEqual(log, ["allProps", "allProps"])
        XCTAssertNotEqual(SoccerEventPageMode10868.catalogue, .page)
        XCTAssertNotEqual(SoccerEventPageMode10868.original, .reader(.history))
    }
}
