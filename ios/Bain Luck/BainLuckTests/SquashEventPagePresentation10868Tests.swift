import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the squash match screen (`squash-match`) composed from the shared
/// leaves and its compact actual-game leaf.
///
/// PREPARED / NOT RUN. The view is SwiftUI and is not rasterised here. What is
/// asserted is the composition: which actual leaf each phase mounts and with
/// which exact owner input, the before-play isolation of every later game,
/// total, duration and result, the independent early readings with no
/// baseline claimed, the nine observations with their runs, break and own
/// clocks, exact-minute inspection, the five actual games fixed across
/// inspection, the game scale and tile plans, the full-size readers, the
/// originals' chooser, catalogue and Details, the callbacks and the once-only
/// hold. Each shared leaf's own rules stay with its own tests; nothing here
/// claims a compile, a rendered fit at 375×667 or 393×852, VoiceOver
/// behaviour, a production binding or route readiness.
///
/// ARCHIVED raw values (prototype `squashMatch.json`, sha256 00435c50…0088):
/// British Open semifinal, Mostafa Asal vs Diego Elias, Kalshi event
/// KXSQUASHMATCH-26JUN07ASSELI (the market spells Asal "Assal" and schedules
/// June 7; the report dates the match June 6; schedule, market close
/// 2026-06-06T19:00:17Z and settlement 19:06:24Z give no actual start or end):
/// - the nine positive-volume minute closes: Asal 0.98 at 2026-06-05T21:12Z and
///   0.02 at 21:13Z, 0.99 at 2026-06-06T17:08Z; Elias 0.01 at 17:08, 17:09,
///   17:11, 17:13, 17:21 and 17:25Z — no early Elias trade;
/// - games 11–9, 10–12, 11–9, 9–11, 11–9; match 3–2; total points 52–50;
///   reported duration 115 minutes; no game-end, start or end clock;
/// - contract results Asal yes, Elias no (finalized).
///
/// CONSTRUCTED (owner inputs, not retained facts): every label, figure text,
/// PDT clock line, caption, state word, caution, About, source and report
/// text, tint, scope, identity and action id; the compressed history
/// coordinate (owner minutes, the overnight span shortened to five) and its
/// break; the axis words; the point scale ceiling; the cumulative-games and
/// winner words; and the whole DURING frame — there is no live specimen, so
/// the live phase stays applicable but evidence-missing and every live value
/// here is a construction. The June 5, 4:00 PM PDT boundary (midnight London)
/// is a conservative date boundary, never a start.
@MainActor
final class SquashEventPagePresentation10868Tests: XCTestCase {

    // MARK: Players

    private enum Player: String {
        case asal
        case elias
    }

    private static let asalTint = Color(red: 0.29, green: 0.27, blue: 0.75)
    private static let eliasTint = Color(red: 0.0, green: 0.52, blue: 0.53)

    private static func name(_ player: Player) -> String { player == .asal ? "Mostafa Asal" : "Diego Elias" }
    private static func short(_ player: Player) -> String { player == .asal ? "Asal" : "Elias" }
    private static func tint(_ player: Player) -> Color { player == .asal ? asalTint : eliasTint }

    // MARK: The nine retained observations

    /// ARCHIVED value and clock; CONSTRUCTED owner id, coordinate and words.
    private struct Observation {
        let id: String
        let player: Player
        /// Owner minutes, the overnight span shortened to five.
        let x: Double
        let probability: Double
        let figure: String
        let clock: String
        let early: Bool
    }

    private static let observations: [Observation] = [
        Observation(id: "asal.jun5.2112", player: .asal, x: 0, probability: 0.98, figure: "98%", clock: "June 5, 2:12 PM PDT", early: true),
        Observation(id: "asal.jun5.2113", player: .asal, x: 1, probability: 0.02, figure: "2%", clock: "June 5, 2:13 PM PDT", early: true),
        Observation(id: "asal.jun6.1708", player: .asal, x: 6, probability: 0.99, figure: "99%", clock: "June 6, 10:08 AM PDT", early: false),
        Observation(id: "elias.jun6.1708", player: .elias, x: 6, probability: 0.01, figure: "1%", clock: "June 6, 10:08 AM PDT", early: false),
        Observation(id: "elias.jun6.1709", player: .elias, x: 7, probability: 0.01, figure: "1%", clock: "June 6, 10:09 AM PDT", early: false),
        Observation(id: "elias.jun6.1711", player: .elias, x: 9, probability: 0.01, figure: "1%", clock: "June 6, 10:11 AM PDT", early: false),
        Observation(id: "elias.jun6.1713", player: .elias, x: 11, probability: 0.01, figure: "1%", clock: "June 6, 10:13 AM PDT", early: false),
        Observation(id: "elias.jun6.1721", player: .elias, x: 19, probability: 0.01, figure: "1%", clock: "June 6, 10:21 AM PDT", early: false),
        Observation(id: "elias.jun6.1725", player: .elias, x: 23, probability: 0.01, figure: "1%", clock: "June 6, 10:25 AM PDT", early: false),
    ]

    private static func observation(_ id: String) -> Observation {
        observations.first { $0.id == id }!
    }

    private static func point(_ id: String) -> FieldHistoryPoint10868 {
        let o = observation(id)
        return FieldHistoryPoint10868(id: o.id, x: o.x, probability: o.probability, style: o.early ? .hollow : .filled)
    }

    private static func run(_ ids: [String]) -> FieldHistoryRun10868 {
        FieldHistoryRun10868(id: "run.\(ids[0])", points: ids.map(point))
    }

    /// Each unqualified early trade is its own run; only adjacent later traded
    /// minutes share a run. The owner admits only what the phase holds.
    private static func runs(_ player: Player, _ phase: SquashEventPagePhase10868) -> [FieldHistoryRun10868] {
        switch (player, phase) {
        case (.asal, .before):
            return [run(["asal.jun5.2112"]), run(["asal.jun5.2113"])]
        case (.asal, _):
            return [run(["asal.jun5.2112"]), run(["asal.jun5.2113"]), run(["asal.jun6.1708"])]
        case (.elias, .before):
            return []
        case (.elias, .during):
            return [run(["elias.jun6.1708", "elias.jun6.1709"]), run(["elias.jun6.1711"]), run(["elias.jun6.1713"])]
        case (.elias, .final):
            return [run(["elias.jun6.1708", "elias.jun6.1709"]), run(["elias.jun6.1711"]), run(["elias.jun6.1713"]),
                    run(["elias.jun6.1721"]), run(["elias.jun6.1725"])]
        }
    }

    private static let overnight = FieldHistoryBreak10868(id: "overnight", lower: 1.5, upper: 5.5, mark: "//")
    private static let noBaseline = "No reliable pre-match estimate"
    private static let noEarlyElias = "No early trade recorded"
    private static let noMinute = "No trade in this minute"
    private static let unbound = "Not recorded at this minute"

    private static func reading(_ id: String, qualifier: String? = nil) -> FieldHistoryReading10868 {
        let o = observation(id)
        return .observation(pointID: o.id, figure: o.figure, provenance: qualifier.map { "\(o.clock) · \($0)" } ?? o.clock)
    }

    private static func action(_ id: String, _ label: String) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: nil, isAvailable: true)
    }

    /// `inspected`: the owner's held inspection at the 10:11 AM minute, where
    /// only Elias traded. `omitInspected`: a CONSTRUCTED update that no longer
    /// carries that Elias minute.
    private static func history(_ phase: SquashEventPagePhase10868, inspected: Bool = false,
                                omitInspected: Bool = false) -> FieldHistoryInput10868 {
        let lastElias = phase == .during ? "elias.jun6.1713" : "elias.jun6.1725"
        func series(_ player: Player) -> FieldHistorySeries10868 {
            var playerRuns = runs(player, phase)
            if omitInspected, player == .elias {
                playerRuns = playerRuns.filter { $0.points.first?.id != "elias.jun6.1711" }
            }
            let before: FieldHistoryReading10868
            let recorded: FieldHistoryReading10868
            let label: String?
            switch (player, phase) {
            case (.asal, .before):
                before = reading("asal.jun5.2113", qualifier: "unqualified")
                recorded = .absent(words: "No recorded chance before play")
                label = "asal.jun5.2113"
            case (.elias, .before):
                before = .absent(words: noEarlyElias)
                recorded = .absent(words: "No recorded chance before play")
                label = nil
            case (.asal, _):
                before = .absent(words: noBaseline)
                recorded = reading("asal.jun6.1708")
                label = "asal.jun6.1708"
            case (.elias, _):
                before = .absent(words: noBaseline)
                recorded = reading(inspected ? "elias.jun6.1711" : lastElias)
                label = lastElias
            }
            return FieldHistorySeries10868(
                id: player.rawValue, name: name(player), shape: player == .asal ? .circle : .diamond, tint: tint(player),
                runs: playerRuns, links: [], labelPointID: label, before: before, recorded: recorded,
                absentWords: player == .elias && phase == .before ? noEarlyElias : nil, choose: nil)
        }
        let domain: FieldHistoryDomain10868 = switch phase {
        case .before: FieldHistoryDomain10868(lower: -1, upper: 2)
        case .during: FieldHistoryDomain10868(lower: -1, upper: 12)
        case .final: FieldHistoryDomain10868(lower: -1, upper: 24)
        }
        let endWords: [String] = switch phase {
        case .before: ["2:14 PM", "June 5"]
        case .during: ["10:14 AM", "June 6"]
        case .final: ["10:26 AM", "June 6"]
        }
        let readout: FieldHistoryReadoutIntent10868 = switch phase {
        case .before: .singleBefore(label: "Early recorded trade")
        case .during: .beforeAndRecorded(beforeLabel: "Pre-match", recordedLabel: "Recorded chance")
        case .final: inspected
            ? .beforeAndInspected(beforeLabel: "Pre-match", inspectedLabel: "Inspected chance")
            : .beforeAndRecorded(beforeLabel: "Pre-match", recordedLabel: "Last recorded chance")
        }
        let windows = FieldHistoryWindows10868(
            groupLabel: "History period",
            choices: [FieldHistoryWindowChoice10868(action: action("window.all", "All trades"), isSelected: true)]
                + (phase == .final ? [FieldHistoryWindowChoice10868(action: action("window.day", "Match day"), isSelected: false)] : []))
        let inspection: FieldHistoryInspection10868? = inspected
            ? FieldHistoryInspection10868(
                x: 9, caption: "Inspected June 6, 10:11 AM PDT",
                selections: ["asal": .absent(words: noMinute), "elias": .point(id: "elias.jun6.1711", spoken: "1%")],
                choices: [], choicePresentation: .buttons(groupLabel: "Recorded minutes"),
                note: "Only exact recorded minutes are shown.")
            : nil
        return FieldHistoryInput10868(
            title: phase == .before ? "Early trading history" : "Win probability history",
            caption: "Recorded trades · Pacific time",
            series: [series(.asal), series(.elias)], selection: .none,
            domain: domain, ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.5, lines: ["50%"]),
                     FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: [FieldHistoryTick10868(value: domain.lower, lines: ["June 5", "2:11 PM"]),
                     FieldHistoryTick10868(value: domain.upper, lines: endWords)],
            guides: [],
            breaks: phase == .before ? [] : [overnight],
            readout: readout,
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow: early recorded trade · unqualified", filled: "Filled: recorded trade"),
            comparisonExplanation: nil,
            notes: phase == .before
                ? ["Each line is independent; the two need not total 100%."]
                : ["Shaded break: no trades recorded. Time is shortened.", "Each line is independent; the two need not total 100%."],
            summary: "Asal circles, Elias diamonds. Independent recorded trades, zero to 100 percent. No game timing.",
            plotHeight: 300, unboundReadingWords: unbound, plotUnavailableWords: nil,
            windows: windows, scale: nil, moreOriginals: nil, details: nil,
            expand: action("history.expand", "Open the probability history full size"),
            inspect: inspected ? action("history.latest", "Return to last recorded trades") : nil,
            previous: action("history.previous", "Previous recorded minute"),
            next: action("history.next", "Next recorded minute"),
            inspection: inspection)
    }

    // MARK: Headline

    private static let headlineScope = "constructed.scope.squash.semifinal"

    private static func ref(_ player: Player) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: headlineScope, source: "constructed.source", marketID: "constructed.market.winner",
                                     outcomeID: player.rawValue)
    }

    private static let earlyAsal = FieldChooserReading10868(
        label: "Early recorded trade", value: .recorded(text: "2%", detail: "June 5, 2:13 PM PDT · unqualified"))
    private static let earlyElias = FieldChooserReading10868(label: "Early recorded trade", value: .missing(noEarlyElias))
    private static let livePreMatch = FieldChooserReading10868(label: "Pre-match chance", value: .missing(noBaseline))
    private static let finalPreMatch = FieldChooserReading10868(label: "Pre-match chance",
                                                                value: .missing("Pre-match comparison unavailable"))

    /// CONSTRUCTED live readings: each player's last recorded close by 10:13 AM.
    private static func liveRecorded(_ player: Player) -> FieldChooserReading10868 {
        let o = observation(player == .asal ? "asal.jun6.1708" : "elias.jun6.1713")
        return FieldChooserReading10868(label: "Recorded chance", value: .recorded(text: o.figure, detail: o.clock))
    }

    private static func plan(_ player: Player, _ phase: SquashEventPagePhase10868) -> FieldChooserDisplayPlan10868 {
        switch phase {
        case .before: .single(player == .asal ? earlyAsal : earlyElias)
        case .during: .comparison(before: livePreMatch, later: liveRecorded(player))
        case .final: .single(finalPreMatch)
        }
    }

    private static func pair(_ player: Player, _ phase: SquashEventPagePhase10868) -> FieldMovementPair10868 {
        let before: FieldMovementObservation10868? = phase == .before && player == .asal
            ? FieldMovementObservation10868(probability: 0.02, reading: earlyAsal) : nil
        let later: FieldMovementObservation10868? = phase == .during
            ? FieldMovementObservation10868(probability: player == .asal ? 0.99 : 0.01, reading: liveRecorded(player)) : nil
        return FieldMovementPair10868(ref: ref(player), before: before, later: later, movement: nil, observation: nil)
    }

    private static func state(_ phase: SquashEventPagePhase10868) -> FieldHeadlineState10868 {
        switch phase {
        case .before:
            return FieldHeadlineState10868(
                figure: "Before match", unit: nil, caption: "June 5 archive",
                detail: "Date boundary June 5, 4:00 PM PDT · not the start",
                spoken: "Before match. June 5 archive. Date boundary June 5, 4:00 PM PDT, not the start.", progress: nil)
        case .during:
            return FieldHeadlineState10868(
                figure: "2–1", unit: "games", caption: "Constructed live example", detail: "Current game · points not reported",
                spoken: "Constructed live example. 2 games to 1. Current game points not reported.", progress: nil)
        case .final:
            return FieldHeadlineState10868(
                figure: "3–2", unit: "games", caption: "Asal won · Final", detail: "Reported June 6 · 115 minutes",
                spoken: "Asal won 3 games to 2. Reported June 6. 115 minutes.", progress: nil)
        }
    }

    /// The finishes ride along in every phase; only the final reads them.
    private static func headline(_ phase: SquashEventPagePhase10868,
                                 headlinePhase: FieldOutlookPhase10868? = nil) -> FieldHeadlineInput10868 {
        FieldHeadlineInput10868(
            scope: headlineScope,
            catalogue: [Player.asal, .elias].map { player in
                FieldChooserOriginal10868(
                    ref: ref(player), name: name(player), plan: plan(player, phase),
                    preview: FieldChooserPreview10868(history: nil, absence: "History in the chart"),
                    movement: nil, clock: nil, result: nil, browseStatus: "Recorded trades", accent: tint(player))
            },
            displayed: [Player.asal, .elias].map {
                FieldHeadlineSlot10868(ref: ref($0), name: name($0), compactName: short($0),
                                       keyShape: $0 == .asal ? .circle : .diamond)
            },
            pairs: [pair(.asal, phase), pair(.elias, phase)],
            finishes: [
                FieldFinishPlace10868(ref: ref(.asal), reading: FieldChooserReading10868(
                    label: "Match result", value: .recorded(text: "Won 3–2", detail: "British Open report · June 6"))),
                FieldFinishPlace10868(ref: ref(.elias), reading: FieldChooserReading10868(
                    label: "Match result", value: .recorded(text: "Lost 2–3", detail: "British Open report · June 6"))),
            ],
            state: state(phase),
            phase: headlinePhase ?? SquashEventPageModel10868.headlinePhase(phase),
            copy: FieldHeadlineCopy10868(
                eyebrow: "Squash · British Open semifinal", title: "Mostafa Asal · Diego Elias",
                graphicLabel: "Recorded win chances", beforeLabel: "Pre-match chance", recordedLabel: "Recorded chance",
                beforeUnavailable: noBaseline, recordedUnavailable: "No recorded chance",
                finishLabel: "Match result", finishUnavailable: "Result not reported",
                empty: "No players in this update", aboutLabel: "About this squash match",
                aboutHint: "Opens dates, sources and the report", openHint: "Opens this player’s history"),
            unavailableWords: "Player unavailable in this update",
            keyTreatment: .neutralRecorded)
    }

    private static func headlineModel(_ input: FieldHeadlineInput10868) -> FieldHeadlineModel10868 {
        FieldHeadlineModel10868(input)
    }

    // MARK: Actual games

    private static let firstPlayer = SquashGamePlayer10868(id: "asal", name: "Asal", shape: .circle, tint: asalTint)
    private static let secondPlayer = SquashGamePlayer10868(id: "elias", name: "Elias", shape: .diamond, tint: eliasTint)

    /// ARCHIVED points; CONSTRUCTED ids, winner and cumulative words.
    private static let gameScores: [(asal: Int, elias: Int, winner: Player, games: String)] = [
        (11, 9, .asal, "1–0"), (10, 12, .elias, "1–1"), (11, 9, .asal, "2–1"), (9, 11, .elias, "2–2"), (11, 9, .asal, "3–2"),
    ]

    private static func gameRow(_ index: Int) -> SquashGameRow10868 {
        let score = gameScores[index]
        return SquashGameRow10868(
            id: "game.\(index + 1)", label: "Game \(index + 1)",
            first: .reported(text: "\(score.asal)", value: Double(score.asal)),
            second: .reported(text: "\(score.elias)", value: Double(score.elias)),
            winnerID: score.winner.rawValue, winnerWords: "\(short(score.winner)) won the game",
            games: score.games, gamesSpoken: "Games \(score.games.replacingOccurrences(of: "–", with: " to "))")
    }

    private static let match = SquashGameFact10868(value: "3–2", label: "Final · Asal won the match",
                                                   spoken: "Final. Asal won the match 3 games to 2.")
    private static let totalPoints = SquashGameFact10868(value: "52–50", label: "Total points · not win probability",
                                                         spoken: "Total points 52 to 50. Not a win probability.")
    private static let duration = SquashGameFact10868(value: "115 min", label: "Reported match duration",
                                                      spoken: "Reported match duration 115 minutes.")

    /// The final's five games; the CONSTRUCTED live frame's first three with
    /// its running total, and its own live eyebrow, title, notes and report
    /// label — none describes a finished match. The final-only match score and
    /// duration are supplied in every frame so the phase, not their absence,
    /// keeps them off.
    private static func games(_ phase: SquashEventPagePhase10868, rows: [SquashGameRow10868]? = nil,
                              ceiling: Double = 12) -> SquashGameScoresInput10868 {
        let live = phase == .during
        return SquashGameScoresInput10868(
            phase: phase,
            eyebrow: live ? "Games so far · constructed live example" : "How the match was won",
            title: live ? "Games so far" : "Every game. Two points apart.",
            keyLabel: "Actual points", first: firstPlayer, second: secondPlayer,
            rows: rows ?? (phase == .during ? (0..<3).map(gameRow) : (0..<5).map(gameRow)),
            scale: SquashGameScale10868(
                ceiling: ceiling,
                words: ceiling.isFinite && ceiling > 0 ? "Bars share one 0–\(Int(ceiling)) point scale" : "Shared point scale"),
            notDrawn: "Beyond the shared point scale; not drawn", empty: "No games reported yet",
            match: match,
            totalPoints: phase == .during
                ? SquashGameFact10868(value: "32–30", label: "Points so far · not win probability",
                                      spoken: "Points so far 32 to 30. Not a win probability.")
                : totalPoints,
            duration: duration,
            notes: live
                ? ["Game 2 went beyond 10–10.", "Constructed live example: later games are not part of this frame."]
                : ["Game 2 went beyond 10–10.",
                   "Pre-match expectation unavailable. Sparse trades do not establish how surprising this result was."],
            reportLabel: live ? "Report so far" : "Match report", expandLabel: "Open the game scores full size")
    }

    // MARK: Text, copy and page

    /// The CONSTRUCTED live frame's dates name no report, settlement or end.
    private static func about(_ phase: SquashEventPagePhase10868) -> SquashEventPageText10868 {
        SquashEventPageText10868(title: "About this squash match", sections: [
            SquashEventPageSection10868(title: "Dates", paragraphs: [
                phase == .during
                    ? "The market lists June 7; this constructed live frame is dated June 6. The schedule gives no actual start time."
                    : "The report dates this semifinal June 6; the market lists June 7. Neither the schedule, the market close nor settlement gives the actual start or end.",
            ]),
            SquashEventPageSection10868(title: "Chances", paragraphs: [
                "Each line is an independent recorded trade; the two need not total 100%.",
            ]),
        ])
    }

    private static func source() -> SquashEventPageText10868 {
        SquashEventPageText10868(title: "History & source details", sections: [
            SquashEventPageSection10868(title: nil, paragraphs: [
                "Only positive-volume traded minutes are drawn. Bid and ask values never create history points.",
                "Before match stops at June 5, 4:00 PM PDT — the start of June 6 in London. A conservative date boundary, not the start.",
            ]),
        ])
    }

    /// Before play: no result. The CONSTRUCTED live frame: only its three
    /// admitted games and running points, and no link out to the finished
    /// match report. The final: the whole report with its link.
    private static func report(_ phase: SquashEventPagePhase10868) -> SquashEventPageText10868 {
        switch phase {
        case .before:
            SquashEventPageText10868(title: "Match report", sections: [
                SquashEventPageSection10868(title: nil, paragraphs: [
                    "A retrospective before-play reconstruction; no result is shown in this phase.",
                ]),
            ])
        case .during:
            SquashEventPageText10868(title: "Games so far · constructed live example", sections: [
                SquashEventPageSection10868(title: nil, paragraphs: [
                    "Constructed live example: Asal leads Elias 2–1 in games after 11–9, 10–12 and 11–9, with 32–30 in points so far. Later games are not part of this frame.",
                ]),
            ])
        case .final:
            SquashEventPageText10868(title: "Five-game semifinal", sections: [
                SquashEventPageSection10868(title: nil, paragraphs: [
                    "The British Open match report records Asal beating Elias 3–2 on June 6, with games 11–9, 10–12, 11–9, 9–11, 11–9 in 115 minutes.",
                ]),
            ], link: SquashEventPageLink10868(id: "report.link", label: "British Open match report"))
        }
    }

    private static func reader(_ phase: SquashEventPagePhase10868) -> SquashEventPageReaderHeader10868 {
        switch phase {
        case .before: SquashEventPageReaderHeader10868(title: "Asal vs Elias · Before match", state: "British Open semifinal · June 5 archive")
        case .during: SquashEventPageReaderHeader10868(title: "Asal vs Elias · Constructed live example", state: "British Open semifinal")
        case .final: SquashEventPageReaderHeader10868(title: "Asal vs Elias · Final 3–2", state: "British Open semifinal")
        }
    }

    private static func expectation(_ phase: SquashEventPagePhase10868) -> SquashEventPageExpectation10868 {
        switch phase {
        case .before:
            SquashEventPageExpectation10868(title: noBaseline, reason: "Two conflicting early trades for Asal; none for Elias.")
        case .during:
            SquashEventPageExpectation10868(title: noBaseline, reason: nil)
        case .final:
            SquashEventPageExpectation10868(title: "Pre-match comparison unavailable",
                                            reason: "Sparse trades do not establish how surprising this result was.")
        }
    }

    private static let copy = SquashEventPageCopy10868(
        headlineUnavailable: "Match chances unavailable in this update.",
        sourceLabel: "History & source details", allPropsLabel: "All 2 original markets")

    /// Every input is supplied in every phase — the final's games before play
    /// too — so only the page phase and each leaf's own phase decide.
    private static func page(_ phase: SquashEventPagePhase10868, history: FieldHistoryInput10868? = nil,
                             headline: FieldHeadlineInput10868? = nil) -> SquashEventPageInput10868 {
        SquashEventPageInput10868(
            phase: phase, reader: reader(phase), headline: headline ?? Self.headline(phase),
            notice: nil, expectation: expectation(phase), history: history ?? Self.history(phase),
            readerPlotHeight: 350, games: games(phase == .before ? .final : phase),
            about: about(phase), source: source(), report: report(phase), copy: copy)
    }

    // MARK: Originals

    private static let originalsScope = "constructed.scope.squash.originals"

    private static func identity(_ player: Player) -> OriginalMarketDetails9483.Identity {
        OriginalMarketDetails9483.Identity(source: "kalshi", market: "constructed.market.\(player.rawValue)", side: "Yes")
    }

    private static func selection(_ player: Player) -> OriginalMarketDetails9483.Selection {
        OriginalMarketDetails9483.Selection(scope: originalsScope, identity: identity(player))
    }

    /// The retained rules wording keeps the market's own "Assal" spelling.
    private static func rule(_ player: Player) -> String {
        player == .asal
            ? "If Mostafa Assal wins the Assal vs Elias professional squash match in the 2026 Quilter Cheviot British Open Squash Championships Semifinal after a ball has been played, then the market resolves to Yes."
            : "If Diego Elias wins the Assal vs Elias professional squash match in the 2026 Quilter Cheviot British Open Squash Championships Semifinal after a ball has been played, then the market resolves to Yes."
    }

    private static func title(_ player: Player) -> String {
        player == .asal ? "Will Mostafa Assal win the Assal vs Elias: Semifinal match?"
            : "Will Diego Elias win the Assal vs Elias: Semifinal match?"
    }

    /// `eliasGrade: false` is an owner without Elias's own contract result.
    private static func original(_ player: Player, _ phase: SquashEventPagePhase10868, blankTitle: Bool = false,
                                 eliasGrade: Bool = true) -> OriginalMarketDetails9483.Original {
        let mode: OriginalMarketDetails9483.Mode = switch phase {
        case .before: .pregame
        case .during: .comparison(.recorded)
        case .final: .result
        }
        let pregame: OriginalMarketDetails9483.Reading = phase == .before
            ? (player == .asal ? .value("2%", placement: nil, provenance: "June 5, 2:13 PM PDT · unqualified")
                : .missing(noEarlyElias))
            : .missing("No reliable pre-match chance")
        let liveClose = observation(player == .asal ? "asal.jun6.1708" : "elias.jun6.1713")
        let later: OriginalMarketDetails9483.Reading? = phase == .during
            ? .value(liveClose.figure, placement: liveClose.probability, provenance: liveClose.clock) : nil
        let grade: OriginalMarketDetails9483.Grade? = phase == .final && (player == .asal || eliasGrade)
            ? OriginalMarketDetails9483.Grade(words: player == .asal ? "Won" : "Lost",
                                              provenance: "Contract finalized June 6, 12:06 PM PDT")
            : nil
        let lastClose = observation(player == .asal ? "asal.jun6.1708" : "elias.jun6.1725")
        var original = OriginalMarketDetails9483.Original(
            identity: identity(player), title: blankTitle ? " " : title(player), outcome: name(player), mode: mode,
            pregame: pregame, later: later, grade: grade,
            about: OriginalMarketDetails9483.About(
                source: "Kalshi", rules: .verified([rule(player)]),
                provenance: [OriginalMarketDetails9483.Row(label: "Market schedule", value: "June 7 · not the actual start")],
                historicalQuote: phase == .final
                    ? OriginalMarketDetails9483.HistoricalQuote(text: lastClose.figure, recorded: lastClose.clock) : nil))
        if phase == .before { original.beforeLabel = "Early recorded trade" }
        return original
    }

    private static func catalogue(_ phase: SquashEventPagePhase10868,
                                  originals: [OriginalMarketDetails9483.Original]? = nil) -> OriginalMarketDetails9483.Catalogue {
        OriginalMarketDetails9483.Catalogue(scope: originalsScope,
                                            originals: originals ?? [original(.asal, phase), original(.elias, phase)])
    }

    private static func originals(_ phase: SquashEventPagePhase10868, selected: Player? = .asal,
                                  catalogue: OriginalMarketDetails9483.Catalogue? = nil) -> SquashEventPageOriginals10868 {
        SquashEventPageOriginals10868(
            catalogue: catalogue ?? Self.catalogue(phase), selection: selected.map(selection),
            labels: [identity(.asal): "Asal to win", identity(.elias): "Elias to win"],
            heading: "Original markets", context: "2 retained originals",
            emptyWords: "No retained originals for this match", unavailableChoice: "Original unavailable", tint: asalTint)
    }

    private static func choices(_ originals: SquashEventPageOriginals10868) -> [OriginalMarketChooser9483.Choice] {
        OriginalMarketChooser9483.choices(catalogue: originals.catalogue, selection: originals.selection,
                                          labels: originals.labels, unavailableChoice: originals.unavailableChoice)
    }

    private static func slots(_ input: FieldHistoryInput10868) -> [[FieldHistoryReadoutSlot10868]] {
        input.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: input) }
    }

    private static func allPoints(_ input: FieldHistoryInput10868) -> [FieldHistoryPoint10868] {
        input.series.flatMap { $0.runs.flatMap(\.points) }
    }

    // MARK: Reachable outputs

    /// A fact as a whole token — no digit directly before or after it — so
    /// "2–3" is not found inside the admitted "32–30".
    private static func mentions(_ output: String, _ fact: String) -> Bool {
        let pattern = "(?<![0-9])" + NSRegularExpression.escapedPattern(for: fact) + "(?![0-9])"
        return output.range(of: pattern, options: .regularExpression) != nil
    }

    /// Every word a reader can see or hear from one page input, collected
    /// through the same Views in every content mode with every text callback
    /// supplied: reader heading, copy, caution, the headline, page and
    /// full-size history, page and full-size games, About, source and report
    /// content with any link, and every original's chooser, Details, About
    /// rows, rules and speech.
    private static func reachableOutputs(_ input: SquashEventPageInput10868,
                                         _ originals: SquashEventPageOriginals10868) -> [String] {
        let model = SquashEventPageModel10868(input)
        var outputs: [String] = [input.reader.title, input.copy.headlineUnavailable]
        outputs += [input.reader.state, input.copy.sourceLabel, input.copy.allPropsLabel, model.notice].compactMap { $0 }
        if let caution = model.expectation { outputs += [caution.title] + [caution.reason].compactMap { $0 } }
        let modes: [SquashEventPageMode10868] = [.page, .fullHistory, .fullGames, .catalogue, .original, .about, .source, .report]
        for mode in modes {
            let view = SquashEventPagePresentation10868(input: input, mode: mode, originals: originals,
                                                        onAbout: {}, onSource: {}, onReport: {}, onLink: { _ in })
            if let headline = view.headlineContent()?.input {
                let hm = headlineModel(headline)
                outputs += hm.competitors.map(hm.competitorSummary)
                outputs += hm.competitors.flatMap { $0.metrics.compactMap(FieldChaseModel10868.figure) }
                outputs += [hm.eyebrow, hm.title, hm.stateSummary, hm.aboutLabel(canAbout: true)].compactMap { $0 }
                if let state = hm.state { outputs += [state.figure] + [state.unit, state.caption, state.detail].compactMap { $0 } }
                outputs += [headline.copy.graphicLabel, headline.copy.empty]
                    + [headline.copy.aboutHint, headline.copy.openHint].compactMap { $0 }
            }
            outputs += historyOutputs(view.historyContent(reader: false).input)
            outputs += historyOutputs(view.historyContent(reader: true).input)
            for games in [view.gamesContent(reader: false), view.gamesContent(reader: true)].compactMap({ $0 }) {
                outputs += gamesOutputs(games)
            }
            for content in [view.aboutContent(), view.sourceContent(), view.reportContent()].compactMap({ $0 }) {
                outputs += [content.text.title] + content.text.sections.flatMap { [$0.title].compactMap { $0 } + $0.paragraphs }
                outputs += [content.link?.label].compactMap { $0 }
            }
        }
        outputs += [originals.heading, originals.emptyWords] + [originals.context].compactMap { $0 }
        outputs += choices(originals).map(OriginalMarketChooser9483.spoken)
        if let catalogue = originals.catalogue {
            for original in catalogue.originals {
                let selection = OriginalMarketDetails9483.Selection(scope: catalogue.scope, identity: original.identity)
                guard let content = OriginalMarketDetails9483.content(catalogue: catalogue, selection: selection) else { continue }
                outputs += [content.title, content.outcome, OriginalMarketDetails9483.spoken(content)]
                outputs += content.readings.flatMap { [$0.label, $0.text] + [$0.provenance].compactMap { $0 } }
                if let result = content.result { outputs += [result.words] + [result.provenance].compactMap { $0 } }
                outputs += content.about.flatMap { [$0.label, $0.value] }
                if case .verified(let paragraphs) = content.rules { outputs += paragraphs }
            }
        }
        return outputs
    }

    private static func historyOutputs(_ input: FieldHistoryInput10868) -> [String] {
        var outputs = [input.title, input.summary, input.unboundReadingWords]
        outputs += [input.caption, input.plotUnavailableWords, input.windows?.groupLabel,
                    input.markKey.hollow, input.markKey.filled].compactMap { $0 }
        outputs += input.notes + input.xTicks.flatMap(\.lines) + input.yTicks.flatMap(\.lines) + input.breaks.map(\.mark)
        outputs += FieldHistoryGeometry10868.actions(input).flatMap { [$0.label] + [$0.spokenLabel].compactMap { $0 } }
        for series in input.series {
            outputs += [series.name] + [FieldHistoryGeometry10868.absentWords(series, in: input)].compactMap { $0 }
            outputs += FieldHistoryGeometry10868.readoutSlots(series, in: input).map(FieldHistoryGeometry10868.spokenSlot)
        }
        outputs.append(FieldHistoryGeometry10868.spokenValue(input))
        if let inspection = input.inspection { outputs += [inspection.caption] + [inspection.note].compactMap { $0 } }
        return outputs
    }

    /// The games leaf's drawn and spoken words, through its own gated reads.
    private static func gamesOutputs(_ view: SquashGameScoresPresentation10868) -> [String] {
        let games = view.input
        guard games.isShown else { return [] }
        var outputs = [games.title, games.keyLabel, games.first.name, games.second.name, games.expandLabel]
        outputs += [games.eyebrow, games.accessibilityHeader, games.accessibilityKey, games.visibleScaleWords,
                    view.reportLabel].compactMap { $0 }
        if games.visibleRows.isEmpty { outputs.append(games.empty) }
        for (index, row) in games.visibleRows.enumerated() {
            outputs += [row.label, games.accessibilityRow(row)]
            outputs += [row.first.figure, row.second.figure, row.first.unknownWords, row.second.unknownWords,
                        row.games, games.accessibilityID(at: index)].compactMap { $0 }
            if games.rowShowsNotDrawn(row) { outputs.append(games.notDrawn) }
        }
        for fact in [games.visibleMatch, games.visibleTotalPoints, games.visibleDuration].compactMap({ $0 }) {
            outputs += [fact.value, fact.label, fact.spoken]
        }
        return outputs + games.visibleNotes
    }

    // MARK: Phases

    func testBeforePlayMountsTheEarlyHeadlineAndHistoryWithNoGamesAndNoResult() {
        let input = Self.page(.before)
        let model = SquashEventPageModel10868(input)
        let originals = Self.originals(.before)
        let view = SquashEventPagePresentation10868(input: input, originals: originals)

        // The headline: each player's own early reading, labelled as an
        // unqualified early trade — never a pre-match probability.
        XCTAssertEqual(view.headlineContent()?.input, input.headline)
        let competitors = Self.headlineModel(input.headline).competitors
        XCTAssertEqual(competitors.map(\.metrics.count), [1, 1])
        XCTAssertEqual(competitors.map { $0.metrics.map(FieldChaseModel10868.label) }, [["Early recorded trade"], ["Early recorded trade"]])
        XCTAssertEqual(competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) }, [["2%"], []])
        XCTAssertEqual(competitors[1].metrics.compactMap(FieldChaseModel10868.words), [Self.noEarlyElias])
        XCTAssertFalse(Self.headlineModel(input.headline).keyIsHollow, "no qualified pre-event baseline: neutral recorded keys")

        // The caution leads in readable words.
        XCTAssertEqual(model.expectation, Self.expectation(.before))

        // No games before play, though the final's five are supplied.
        XCTAssertEqual(input.games?.rows.count, 5)
        XCTAssertNil(model.games)
        XCTAssertNil(view.gamesContent(reader: false))
        XCTAssertFalse(model.readerShows(.fullGames))
        XCTAssertTrue(model.readerShows(.fullHistory))
        XCTAssertNil(SquashEventPagePresentation10868(input: input, mode: .fullGames).gamesContent(reader: true))

        // The history: only the two early Asal trades, each its own run.
        let anchor = view.historyContent(reader: false)
        XCTAssertEqual(anchor.input, input.history)
        XCTAssertEqual(Self.allPoints(anchor.input).map(\.probability), [0.98, 0.02])
        XCTAssertEqual(anchor.input.series.map { FieldHistoryGeometry10868.lines($0, in: anchor.input).count }, [0, 0])
        XCTAssertEqual(FieldHistoryGeometry10868.absentWords(anchor.input.series[1], in: anchor.input), Self.noEarlyElias)

        // The two original winner markets with the held original's Details.
        XCTAssertEqual(Self.choices(originals).map(\.label), ["Asal to win", "Elias to win"])
        XCTAssertEqual(view.chooserContent()?.selection, Self.selection(.asal))
        let asal = OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: Self.selection(.asal))
        XCTAssertEqual(asal?.readings.map(\.label), ["Early recorded trade"])
        XCTAssertEqual(asal?.readings.map(\.text), ["2%"])
        XCTAssertNil(asal?.result)
    }

    func testBeforePlayNoLaterScoreTotalDurationOrResultIsShownOrSpoken() {
        let input = Self.page(.before)
        let originals = Self.originals(.before)
        let view = SquashEventPagePresentation10868(input: input, originals: originals)
        let model = SquashEventPageModel10868(input)

        // Every later fact really is supplied: the absence below is gating.
        XCTAssertEqual(input.games?.match?.value, "3–2")
        XCTAssertEqual(input.games?.totalPoints?.value, "52–50")
        XCTAssertEqual(input.games?.duration?.value, "115 min")
        XCTAssertEqual(input.headline.finishes.count, 2)

        var outputs: [String] = [input.reader.title] + [input.reader.state].compactMap { $0 }
        if let headline = view.headlineContent()?.input {
            let hm = Self.headlineModel(headline)
            outputs += hm.competitors.map(hm.competitorSummary)
            outputs += [hm.eyebrow, hm.title, hm.stateSummary].compactMap { $0 }
        } else {
            XCTFail("the before headline mounts")
        }
        if let caution = model.expectation { outputs += [caution.title] + [caution.reason].compactMap { $0 } }
        let anchor = view.historyContent(reader: false)
        outputs += [anchor.input.title, anchor.input.summary] + [anchor.input.caption].compactMap { $0 } + anchor.input.notes
        outputs += anchor.input.xTicks.flatMap(\.lines)
        outputs += Self.slots(anchor.input).flatMap { $0.map(FieldHistoryGeometry10868.spokenSlot) }
        outputs += [FieldHistoryGeometry10868.spokenValue(anchor.input)]
        for text in [model.about, model.source, model.report].compactMap({ $0 }) {
            outputs += [text.title] + text.sections.flatMap { [$0.title].compactMap { $0 } + $0.paragraphs }
        }
        outputs += Self.choices(originals).map(OriginalMarketChooser9483.spoken)
        for player in [Player.asal, .elias] {
            let content = OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: Self.selection(player))
            XCTAssertNil(content?.result, "no contract result before play")
            outputs += content?.readings.map(\.text) ?? []
        }
        XCTAssertNil(view.gamesContent(reader: false))
        XCTAssertNil(view.gamesContent(reader: true))

        let later = ["3–2", "2–3", "11–9", "10–12", "9–11", "52–50", "32–30", "115", "Won", "Lost", " won", "99%", "1%"]
        XCTAssertGreaterThan(outputs.count, 15)
        for output in outputs {
            for fact in later {
                XCTAssertFalse(output.contains(fact), "“\(fact)” reached before play: \(output)")
            }
        }
    }

    func testDuringPlayTheConstructedLiveFrameShowsRecordedChancesAndOnlyAdmittedGames() {
        let input = Self.page(.during)
        let model = SquashEventPageModel10868(input)
        let view = SquashEventPagePresentation10868(input: input)

        // Headline: the owner's no-baseline words beside each recorded chance.
        let competitors = Self.headlineModel(input.headline).competitors
        XCTAssertEqual(competitors.map { $0.metrics.map(FieldChaseModel10868.label) },
                       Array(repeating: ["Pre-match chance", "Recorded chance"], count: 2))
        XCTAssertEqual(competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) }, [["99%"], ["1%"]])
        XCTAssertEqual(competitors.map { $0.metrics.compactMap(FieldChaseModel10868.words) },
                       [[Self.noBaseline], [Self.noBaseline]])

        // The CONSTRUCTED games so far: three rows, the running total, and no
        // final match score or duration although both are supplied.
        guard let games = view.gamesContent(reader: false)?.input else { return XCTFail("live games mount") }
        XCTAssertEqual(games, input.games)
        XCTAssertEqual(games.visibleRows.map(\.games), ["1–0", "1–1", "2–1"])
        XCTAssertEqual(games.visibleTotalPoints?.value, "32–30")
        XCTAssertNotNil(games.match)
        XCTAssertNotNil(games.duration)
        XCTAssertNil(games.visibleMatch, "the match verdict is final only")
        XCTAssertNil(games.visibleDuration, "the reported duration is final only")
        XCTAssertTrue(model.readerShows(.fullGames))

        // History: the owner's recorded readings, each bound to its observation.
        let slots = Self.slots(input.history)
        XCTAssertEqual(slots.map { $0.map(\.label) }, Array(repeating: ["Pre-match", "Recorded chance"], count: 2))
        XCTAssertEqual(slots[0][1].display, .figure("99%", provenance: "June 6, 10:08 AM PDT"))
        XCTAssertEqual(slots[1][1].display, .figure("1%", provenance: "June 6, 10:13 AM PDT"))
        XCTAssertEqual(slots.map { $0[0].display }, [.words(Self.noBaseline), .words(Self.noBaseline)])

        // A final games input is not coerced into live play.
        var foreign = input
        foreign.games = Self.games(.final)
        XCTAssertNil(SquashEventPageModel10868(foreign).games)
        // A final headline shows the owner's unavailable words instead.
        let mismatched = Self.page(.during, headline: Self.headline(.final))
        XCTAssertNil(SquashEventPagePresentation10868(input: mismatched).headlineContent())
    }

    func testDuringPlayEveryReachableOutputKeepsTheAdmittedGamesAndNoLaterFact() {
        // Later than the CONSTRUCTED live frame: the final match score either
        // way, the score after game 4, game 4's points, games 4 and 5, the
        // final points total, the duration and any result words.
        let later = ["3–2", "2–3", "2–2", "9–11", "Game 4", "Game 5", "game.4", "game.5",
                     "52–50", "115", "Won", "Lost", "won the match", "Final"]

        // Positive control: the same collector over the final frame reaches
        // every one of them, so the live scan below cannot pass by reading
        // nothing.
        let finalOutputs = Self.reachableOutputs(Self.page(.final), Self.originals(.final))
        for fact in later {
            XCTAssertTrue(finalOutputs.contains { Self.mentions($0, fact) }, "the collector reaches “\(fact)” at the final")
        }
        // The token rule itself: the admitted running total is not "2–3".
        XCTAssertFalse(Self.mentions("32–30", "2–3"))
        XCTAssertTrue(Self.mentions("Lost 2–3, British Open report", "2–3"))

        let input = Self.page(.during)
        let originals = Self.originals(.during)
        // The live frame still carries the final-only channels: the gating,
        // not their absence, keeps them off.
        XCTAssertEqual(input.games?.match?.value, "3–2")
        XCTAssertEqual(input.games?.duration?.value, "115 min")
        XCTAssertEqual(input.headline.finishes.count, 2)

        let outputs = Self.reachableOutputs(input, originals)
        XCTAssertGreaterThan(outputs.count, 100)

        // Allowed: the admitted 2–1 games, each game's own row, the running
        // 32–30, and the games-so-far report.
        let admitted = ["2–1", "32–30", "1–0", "1–1", "Game 1", "Game 2", "Game 3",
                        "Asal 11. Elias 9. Asal won the game. Games 1 to 0",
                        "Asal 10. Elias 12. Elias won the game. Games 1 to 1",
                        "Asal 11. Elias 9. Asal won the game. Games 2 to 1",
                        "Points so far 32 to 30. Not a win probability.",
                        "Games so far · constructed live example", "Report so far"]
        for words in admitted {
            XCTAssertTrue(outputs.contains { $0.contains(words) }, "the live frame shows “\(words)”")
        }

        // Rejected: nothing later than the frame, anywhere a reader can reach.
        for output in outputs {
            for fact in later {
                XCTAssertFalse(Self.mentions(output, fact), "“\(fact)” reached the live frame: \(output)")
            }
        }

        // The live report: reachable from the games' report control and in
        // report mode, with only the admitted context and no link out to the
        // finished match report.
        var log: [String] = []
        let page = SquashEventPagePresentation10868(input: input, onReport: { log.append("report") })
        XCTAssertEqual(page.gamesContent(reader: false)?.reportLabel, "Report so far")
        page.gamesContent(reader: false)?.onReport?()
        XCTAssertEqual(log, ["report"])
        let report = SquashEventPagePresentation10868(input: input, mode: .report, onLink: { _ in }).reportContent()
        XCTAssertEqual(report?.text, Self.report(.during))
        XCTAssertNil(report?.link)
        XCTAssertEqual(report?.text.sections.flatMap(\.paragraphs).filter { $0.contains("2–1") && $0.contains("32–30") }.count, 1)

        // No later history point is admitted to the live chart.
        XCTAssertEqual(Self.allPoints(input.history).filter { $0.id.hasPrefix("elias.jun6.172") }.count, 0)
        XCTAssertEqual(Self.allPoints(Self.history(.final)).filter { $0.id.hasPrefix("elias.jun6.172") }.count, 2)

        // The final keeps the whole report and the originals' own grades.
        XCTAssertEqual(Self.report(.final).link?.label, "British Open match report")
        XCTAssertTrue(Self.report(.final).sections.flatMap(\.paragraphs).contains { $0.contains("9–11, 11–9 in 115 minutes") })
        let finalOriginals = Self.originals(.final)
        XCTAssertEqual(OriginalMarketDetails9483.content(catalogue: finalOriginals.catalogue,
                                                         selection: Self.selection(.asal))?.result?.words, "Won")
        XCTAssertEqual(OriginalMarketDetails9483.content(catalogue: finalOriginals.catalogue,
                                                         selection: Self.selection(.elias))?.result?.words, "Lost")
        XCTAssertNil(OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: Self.selection(.asal))?.result)
    }

    func testAtTheFinalTheResultSitsBesideNoPreMatchComparisonAndTheFiveGamesStayFixed() {
        let input = Self.page(.final)
        let view = SquashEventPagePresentation10868(input: input)

        // Headline: the owner's "comparison unavailable" words beside the
        // separately reported result — never a chance, never a contract grade.
        let competitors = Self.headlineModel(input.headline).competitors
        XCTAssertEqual(competitors.map { $0.metrics.map(FieldChaseModel10868.label) },
                       Array(repeating: ["Pre-match chance", "Match result"], count: 2))
        XCTAssertEqual(competitors.map { $0.metrics.compactMap(FieldChaseModel10868.words) },
                       Array(repeating: ["Pre-match comparison unavailable"], count: 2))
        XCTAssertEqual(competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) }, [["Won 3–2"], ["Lost 2–3"]])
        XCTAssertEqual(SquashEventPageModel10868(input).expectation?.title, "Pre-match comparison unavailable")

        // The five actual games, the cumulative games, each reported winner by
        // id, the separate match score, 52–50 and 115 minutes as actual facts.
        guard let games = view.gamesContent(reader: false)?.input else { return XCTFail("final games mount") }
        XCTAssertEqual(games.visibleRows.map { [$0.first.figure, $0.second.figure] },
                       [["11", "9"], ["10", "12"], ["11", "9"], ["9", "11"], ["11", "9"]])
        XCTAssertEqual(games.visibleRows.map(\.games), ["1–0", "1–1", "2–1", "2–2", "3–2"])
        XCTAssertEqual(games.visibleRows.map { games.winner($0)?.id }, ["asal", "elias", "asal", "elias", "asal"])
        XCTAssertEqual(games.visibleMatch, Self.match)
        XCTAssertEqual(games.visibleTotalPoints, Self.totalPoints)
        XCTAssertEqual(games.visibleDuration, Self.duration)
        XCTAssertEqual(games.visibleTotalPoints?.label, "Total points · not win probability")
        XCTAssertEqual(games.visibleDuration?.label, "Reported match duration")
        XCTAssertEqual(games.accessibilityRow(games.visibleRows[0]), "Asal 11. Elias 9. Asal won the game. Games 1 to 0")
        XCTAssertEqual(games.accessibilityRow(games.visibleRows[1]), "Asal 10. Elias 12. Elias won the game. Games 1 to 1")

        // Fixed across inspection: inspecting an earlier minute changes the
        // history only; the games — page and full size — are the same input.
        let inspected = Self.page(.final, history: Self.history(.final, inspected: true))
        XCTAssertNotEqual(inspected.history, input.history)
        let inspectedView = SquashEventPagePresentation10868(input: inspected)
        XCTAssertEqual(inspectedView.gamesContent(reader: false)?.input, games)
        XCTAssertEqual(SquashEventPagePresentation10868(input: inspected, mode: .fullGames).gamesContent(reader: true)?.input, games)
        XCTAssertEqual(inspectedView.gamesContent(reader: false)?.input.visibleRows.count, 5)

        // Each original keeps its own contract result, apart from the match.
        let originals = Self.originals(.final)
        let asal = OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: Self.selection(.asal))
        let elias = OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: Self.selection(.elias))
        XCTAssertEqual(asal?.result?.words, "Won")
        XCTAssertEqual(elias?.result?.words, "Lost")
        XCTAssertEqual(asal?.result?.provenance, "Contract finalized June 6, 12:06 PM PDT")
        XCTAssertEqual(asal?.readings.map(\.text), ["No reliable pre-match chance"])
        XCTAssertTrue(asal?.about.contains { $0.value == "99%, recorded June 6, 10:08 AM PDT" } ?? false,
                      "the last recorded trade stays dated and historical")
    }

    // MARK: Early readings, observations and inspection

    func testTheEarlyValuesStayIndependentAndNoReliableBaselineIsClaimed() {
        let before = Self.history(.before)
        // 98% and 2% one minute apart, each its own mark, no line between them.
        let asal = before.series[0]
        XCTAssertEqual(FieldHistoryGeometry10868.marks(asal, in: before).map(\.probability), [0.98, 0.02])
        XCTAssertEqual(FieldHistoryGeometry10868.marks(asal, in: before).map(\.style), [.hollow, .hollow])
        XCTAssertTrue(FieldHistoryGeometry10868.lines(asal, in: before).isEmpty)
        // Elias has no early trade: its own words, no complement of Asal's.
        XCTAssertTrue(FieldHistoryGeometry10868.marks(before.series[1], in: before).isEmpty)
        let slots = Self.slots(before)
        XCTAssertEqual(slots[0], [FieldHistoryReadoutSlot10868(
            label: "Early recorded trade", display: .figure("2%", provenance: "June 5, 2:13 PM PDT · unqualified"))])
        XCTAssertEqual(slots[1], [FieldHistoryReadoutSlot10868(label: "Early recorded trade", display: .words(Self.noEarlyElias))])

        // The headline never titles an early trade a pre-match probability and
        // derives nothing for Elias.
        let headline = Self.headlineModel(Self.headline(.before))
        let labels = headline.competitors.flatMap { $0.metrics.map(FieldChaseModel10868.label) }
        XCTAssertFalse(labels.contains { $0.localizedCaseInsensitiveContains("pre-match") })
        XCTAssertEqual(headline.figures, ["2%"])
        // At the final every pre-match slot is the owner's words, never a figure.
        let finalSlots = Self.slots(Self.history(.final))
        XCTAssertEqual(finalSlots.map { $0[0].display }, [.words(Self.noBaseline), .words(Self.noBaseline)])
        XCTAssertFalse(Self.headlineModel(Self.headline(.final)).figures.contains { $0.hasSuffix("%") })
    }

    func testAllNineObservationsKeepTheirRunsTheOvernightBreakAndTheirOwnClocks() {
        let input = Self.history(.final)
        let asal = input.series[0]
        let elias = input.series[1]

        // Nine marks; only Elias's two adjacent 10:08 and 10:09 minutes join.
        XCTAssertEqual(input.series.flatMap { FieldHistoryGeometry10868.marks($0, in: input) }.count, 9)
        XCTAssertEqual(FieldHistoryGeometry10868.marks(asal, in: input).map(\.probability), [0.98, 0.02, 0.99])
        XCTAssertTrue(FieldHistoryGeometry10868.lines(asal, in: input).isEmpty)
        XCTAssertEqual(FieldHistoryGeometry10868.lines(elias, in: input).map { $0.map(\.id) },
                       [["elias.jun6.1708", "elias.jun6.1709"]])
        XCTAssertEqual(FieldHistoryGeometry10868.marks(elias, in: input).count, 6)

        // The overnight break: even a run the owner joined across it is cut.
        XCTAssertEqual(input.breaks, [Self.overnight])
        XCTAssertTrue(FieldHistoryGeometry10868.breakSeparates(1, 6, breaks: input.breaks))
        let joined = FieldHistoryRun10868(id: "joined", points: [Self.point("asal.jun5.2113"), Self.point("asal.jun6.1708")])
        XCTAssertEqual(FieldHistoryGeometry10868.drawnRuns(joined, in: input).map { $0.map(\.id) },
                       [["asal.jun5.2113"], ["asal.jun6.1708"]])

        // No result point, no guessed start or game marker.
        XCTAssertTrue(Self.allPoints(input).allSatisfy { $0.probability > 0 && $0.probability < 1 })
        XCTAssertTrue(input.guides.isEmpty)

        // Each last recorded chance keeps its own clock.
        let slots = Self.slots(input)
        XCTAssertEqual(slots[0][1], FieldHistoryReadoutSlot10868(label: "Last recorded chance",
                                                                display: .figure("99%", provenance: "June 6, 10:08 AM PDT")))
        XCTAssertEqual(slots[1][1], FieldHistoryReadoutSlot10868(label: "Last recorded chance",
                                                                display: .figure("1%", provenance: "June 6, 10:25 AM PDT")))

        // The full-size history is the same input, expanded, with no expand.
        let reader = SquashEventPageModel10868(Self.page(.final)).readerHistory
        XCTAssertNil(reader.expand)
        XCTAssertEqual(reader.layout, .expanded)
        XCTAssertEqual(reader.plotHeight, 350)
        XCTAssertEqual(reader.series, input.series)
        XCTAssertEqual(reader.breaks, input.breaks)
        XCTAssertEqual(reader.windows, input.windows)
        XCTAssertEqual(reader.previous, input.previous)
        XCTAssertEqual(reader.next, input.next)
        var plain = Self.page(.final)
        plain.readerPlotHeight = nil
        XCTAssertEqual(SquashEventPageModel10868(plain).readerHistory.plotHeight, 300)
    }

    func testAnInspectedMinuteShowsOnlyItsOwnObservationAndKeepsTheValidNeighbour() {
        // 10:11 AM: Elias traded, Asal did not. Asal's slot is the owner's
        // words — never the 99% from 10:08 — and Elias keeps its exact 1%.
        let inspected = Self.history(.final, inspected: true)
        var slots = Self.slots(inspected)
        XCTAssertEqual(slots[0][1], FieldHistoryReadoutSlot10868(label: "Inspected chance", display: .words(Self.noMinute)))
        XCTAssertEqual(slots[1][1], FieldHistoryReadoutSlot10868(label: "Inspected chance",
                                                                display: .figure("1%", provenance: "June 6, 10:11 AM PDT")))
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(inspected.series[0], in: inspected))
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedPoint(inspected.series[1], in: inspected)?.id, "elias.jun6.1711")
        XCTAssertEqual(FieldHistoryGeometry10868.spokenValue(inspected),
                       "Inspected June 6, 10:11 AM PDT; Mostafa Asal: \(Self.noMinute); Diego Elias: 1%")

        // A CONSTRUCTED update without that Elias minute: the held inspection
        // stays, the slot says so, and no neighbouring minute stands in.
        let omitted = Self.history(.final, inspected: true, omitInspected: true)
        slots = Self.slots(omitted)
        XCTAssertEqual(omitted.inspection, inspected.inspection)
        XCTAssertEqual(slots[1][1].display, .words(Self.unbound))
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(omitted.series[1], in: omitted))
        XCTAssertEqual(slots[0][1].display, .words(Self.noMinute), "the neighbour's own words are unchanged")

        // Restored: the same exact reading returns.
        XCTAssertEqual(Self.slots(Self.history(.final, inspected: true))[1][1].display,
                       .figure("1%", provenance: "June 6, 10:11 AM PDT"))

        // The full-size history carries the same held inspection.
        let page = Self.page(.final, history: inspected)
        XCTAssertEqual(SquashEventPagePresentation10868(input: page, mode: .fullHistory).historyContent(reader: true).input.inspection,
                       inspected.inspection)
    }

    // MARK: Actual games

    func testTheGameScaleAndTilePlansFollowTheOwnerScaleWidthAndAccessibilitySize() {
        let games = Self.games(.final)
        // Bars sit on the owner's ceiling, never a fixed 12.
        XCTAssertEqual(games.barFraction(.reported(text: "11", value: 11)) ?? -1, 11.0 / 12.0, accuracy: 1e-9)
        XCTAssertEqual(games.barFraction(.reported(text: "12", value: 12)), 1)
        XCTAssertEqual(games.barFraction(.reported(text: "0", value: 0)), 0, "a real zero is a value")
        XCTAssertNil(games.barFraction(.reported(text: "13", value: 13)), "beyond the scale: no clamped bar")
        XCTAssertTrue(games.showsNotDrawn(.reported(text: "13", value: 13)))
        XCTAssertNil(games.barFraction(.reported(text: "-1", value: -1)))
        XCTAssertNil(games.barFraction(.unknown("Points not reported")))
        XCTAssertFalse(games.showsNotDrawn(.unknown("Points not reported")))
        let wider = Self.games(.final, ceiling: 15)
        XCTAssertEqual(wider.barFraction(.reported(text: "13", value: 13)) ?? -1, 13.0 / 15.0, accuracy: 1e-9)
        XCTAssertEqual(wider.visibleScaleWords, "Bars share one 0–15 point scale")
        XCTAssertNil(Self.games(.final, ceiling: 0).barFraction(.reported(text: "11", value: 11)))
        XCTAssertNil(Self.games(.final, ceiling: .infinity).barFraction(.reported(text: "11", value: 11)))
        XCTAssertEqual(SquashGameScoresGeometry10868.barHeight(11.0 / 12.0, maxHeight: 92) ?? -1, 92 * 11 / 12, accuracy: 1e-9)
        XCTAssertNil(SquashGameScoresGeometry10868.barHeight(1.2, maxHeight: 92))
        XCTAssertNil(SquashGameScoresGeometry10868.barHeight(0.5, maxHeight: 0))

        // Tiles per line from measured widths: 375- and 393-point phones
        // (311 and 329 points inside the page and card padding), wider tiles
        // at larger text, two at most at accessibility sizes, one if two do
        // not fit. Nothing shrinks.
        func columns(_ available: CGFloat?, tile: CGFloat, ax: Bool = false) -> Int {
            SquashGameScoresGeometry10868.columns(count: 5, available: available, spacing: 10, accessibilitySize: ax,
                                                  measure: { _, _ in tile })
        }
        XCTAssertEqual(columns(311, tile: 52), 5)
        XCTAssertEqual(columns(329, tile: 52), 5)
        XCTAssertEqual(columns(311, tile: 60), 4)
        XCTAssertEqual(columns(329, tile: 60), 4)
        XCTAssertEqual(columns(700, tile: 60), 5, "never more than one line of every game")
        XCTAssertEqual(columns(311, tile: 140, ax: true), 2)
        XCTAssertEqual(columns(311, tile: 200, ax: true), 1)
        XCTAssertEqual(columns(nil, tile: 52), 5)
        XCTAssertEqual(columns(nil, tile: 52, ax: true), 2)
        XCTAssertEqual(SquashGameScoresGeometry10868.columns(count: 1, available: 311, spacing: 10, accessibilitySize: false,
                                                            measure: { _, _ in 52 }), 1)
        XCTAssertEqual(SquashGameScoresGeometry10868.lines(count: 5, columns: 4), [[0, 1, 2, 3], [4]])
        XCTAssertEqual(SquashGameScoresGeometry10868.lines(count: 5, columns: 2), [[0, 1], [2, 3], [4]])
        XCTAssertEqual(SquashGameScoresGeometry10868.lines(count: 0, columns: 2), [])

        // Stable, non-colour identity per player.
        XCTAssertEqual(SquashGameScoresGeometry10868.symbol(games.first.shape), "circle.fill")
        XCTAssertEqual(SquashGameScoresGeometry10868.symbol(games.second.shape), "diamond.fill")
        XCTAssertEqual(games.accessibilityKey, "Actual points. Asal. Elias")
        XCTAssertEqual(games.accessibilityID(at: 0), "squashGames10868.game.game.1")
    }

    func testAMissingGameValueKeepsItsRowAndNeighboursAndNeverBecomesZero() {
        var rows = (0..<5).map(Self.gameRow)
        let second = rows[1]
        rows[1] = SquashGameRow10868(id: second.id, label: second.label, first: second.first,
                                     second: .unknown("Points not reported"), winnerID: second.winnerID,
                                     winnerWords: second.winnerWords, games: second.games, gamesSpoken: second.gamesSpoken)
        let fourth = rows[3]
        rows[3] = SquashGameRow10868(id: fourth.id, label: fourth.label, first: .reported(text: "13", value: 13),
                                     second: fourth.second, winnerID: "someone-else", winnerWords: "Winner not reported",
                                     games: nil, gamesSpoken: nil)
        let games = Self.games(.final, rows: rows)

        XCTAssertEqual(games.visibleRows.count, 5, "no row is dropped")
        XCTAssertNil(games.barFraction(games.visibleRows[1].second))
        XCTAssertEqual(games.barFraction(games.visibleRows[1].first) ?? -1, 10.0 / 12.0, accuracy: 1e-9)
        XCTAssertEqual(games.accessibilityRow(games.visibleRows[1]),
                       "Asal 10. Elias: Points not reported. Elias won the game. Games 1 to 1")
        XCTAssertTrue(games.rowShowsNotDrawn(games.visibleRows[3]))
        XCTAssertNil(games.winner(games.visibleRows[3]), "an id naming no player draws no winner mark")
        XCTAssertEqual(games.accessibilityRow(games.visibleRows[3]),
                       "Asal 13. Elias 11. Beyond the shared point scale; not drawn. Winner not reported")
        XCTAssertEqual(games.visibleRows.enumerated().filter { $0.offset != 1 && $0.offset != 3 }.map { games.winner($0.element)?.id },
                       ["asal", "asal", "asal"])
        XCTAssertEqual(games.visibleTotalPoints, Self.totalPoints, "the owner's total stands beside a missing game value")

        // Duplicate or blank player ids name no winner at all.
        let twins = SquashGameScoresInput10868(
            phase: .final, eyebrow: nil, title: "Games", keyLabel: "Actual points", first: Self.firstPlayer,
            second: SquashGamePlayer10868(id: "asal", name: "Elias", shape: .diamond, tint: Self.eliasTint),
            rows: [Self.gameRow(0)], scale: SquashGameScale10868(ceiling: 12, words: nil), notDrawn: "Not drawn",
            empty: "No games", match: nil, totalPoints: nil, duration: nil, notes: [], reportLabel: nil, expandLabel: "Open")
        XCTAssertFalse(twins.hasDistinctPlayers)
        XCTAssertNil(twins.winner(twins.visibleRows[0]))

        // Before play the leaf itself draws and speaks nothing.
        let early = Self.games(.before)
        XCTAssertTrue(early.visibleRows.isEmpty)
        XCTAssertNil(early.visibleTotalPoints)
        XCTAssertNil(early.accessibilityHeader)
        XCTAssertEqual(early.accessibilityRow(Self.gameRow(0)), "")
        XCTAssertNil(early.barFraction(.reported(text: "11", value: 11)))
    }

    // MARK: Readers, callbacks and holds

    func testReadersDetailsAndCallbacksHoldOnceOnThePageAndNeverInFullSizeOrTextContent() {
        var log: [String] = []
        let input = Self.page(.final)
        let intent = OriginalMarketDetails9483.HistoryIntent(selection: Self.selection(.asal), entry: .explore, actionID: "explore")
        func view(_ mode: SquashEventPageMode10868 = .page, hook: Bool = true) -> SquashEventPagePresentation10868 {
            SquashEventPagePresentation10868(
                input: input, mode: mode, originals: Self.originals(.final),
                onAbout: { log.append("about") },
                onSource: { log.append("source") },
                onReport: { log.append("report") },
                onLink: { log.append("link:\($0)") },
                onAllProps: { log.append("allProps") },
                onOriginalSelect: { log.append("original:\($0.identity.market)") },
                onOriginalHistory: { log.append("details:\($0.actionID)") },
                onHeadlineOpen: { log.append("open:\($0.ref.outcomeID)") },
                onHistoryAction: { log.append("history:\($0)") },
                onHistoryInspectionChoice: { log.append("inspect:\($0)") },
                onHistoryPlotPosition: { log.append("plot:\(Int($0))") },
                onGamesExpand: { log.append("games:expand") },
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        // Building and reading every leaf calls nothing.
        let page = view()
        let headline = page.headlineContent()
        let anchor = page.historyContent(reader: false)
        let games = page.gamesContent(reader: false)
        let chooser = page.chooserContent()
        _ = page.catalogueContent()
        _ = page.originalDetailsContent()
        _ = page.aboutContent()
        _ = page.sourceContent()
        _ = page.reportContent()
        _ = page.historyContent(reader: true)
        _ = page.gamesContent(reader: true)
        XCTAssertEqual(log, [])

        // Page, catalogue and Details actions: the hook once, then the exact callback.
        headline?.onAbout?()
        headline?.onOpen?(FieldMovementOpen10868(ref: Self.ref(.asal), observation: nil))
        anchor.onAction?("history.expand")
        anchor.onInspectionChoice?("minute.9")
        anchor.onPlotPosition?(9)
        page.openSource()
        games?.onExpand?()
        games?.onReport?()
        chooser?.onSelect?(Self.selection(.elias))
        page.openAllProps()
        view(.catalogue).catalogueContent()?.onSelect?(Self.selection(.asal))
        view(.original).originalDetailsContent()?.onHistory?(intent)
        XCTAssertEqual(log, ["hold", "about", "hold", "open:asal", "hold", "history:history.expand",
                             "hold", "inspect:minute.9", "hold", "plot:9", "hold", "source",
                             "hold", "games:expand", "hold", "report",
                             "hold", "original:constructed.market.elias", "hold", "allProps",
                             "hold", "original:constructed.market.asal", "hold", "details:explore"])

        // Full-size and text content: the exact callbacks, no hold.
        log = []
        let fullHistory = view(.fullHistory).historyContent(reader: true)
        XCTAssertEqual(fullHistory.input, SquashEventPageModel10868(input).readerHistory)
        fullHistory.onAction?("window.day")
        let fullGames = view(.fullGames).gamesContent(reader: true)
        XCTAssertEqual(fullGames?.input, games?.input, "the same games leaf and input full size")
        XCTAssertNil(fullGames?.onExpand, "no nested expand inside the reader")
        fullGames?.onReport?()
        view(.fullGames).openReaderAbout()
        let reportText = view(.report).reportContent()
        XCTAssertEqual(reportText?.link, SquashEventPageLink10868(id: "report.link", label: "British Open match report"))
        if let link = reportText?.link { reportText?.onLink?(link.id) }
        XCTAssertEqual(log, ["history:window.day", "report", "about", "link:report.link"])
        XCTAssertTrue(SquashEventPageModel10868(input).aboutEntry(mode: .fullGames, canOpen: true))
        XCTAssertFalse(SquashEventPageModel10868(input).aboutEntry(mode: .page, canOpen: true))

        // No owner callback: no control and no hold.
        log = []
        let silent = SquashEventPagePresentation10868(input: input, originals: Self.originals(.final),
                                                      onInteraction: { log.append("hold") })
        XCTAssertNil(silent.headlineContent()?.onAbout)
        XCTAssertNil(silent.headlineContent()?.onOpen)
        XCTAssertNil(silent.historyContent(reader: false).onAction)
        XCTAssertNil(silent.historyContent(reader: false).onPlotPosition)
        XCTAssertNil(silent.gamesContent(reader: false)?.onExpand)
        XCTAssertNil(silent.gamesContent(reader: false)?.onReport)
        XCTAssertNil(silent.gamesContent(reader: false)?.reportLabel)
        XCTAssertNil(silent.reportContent()?.link)
        XCTAssertNil(silent.chooserContent()?.onSelect)
        silent.openSource()
        silent.openAllProps()
        silent.openReaderAbout()
        XCTAssertEqual(log, [])

        // A report callback without readable report text draws no report control.
        var noReport = input
        noReport.report = nil
        let unreported = SquashEventPagePresentation10868(input: noReport, onReport: { log.append("report") })
        XCTAssertNil(unreported.gamesContent(reader: false)?.onReport)
        XCTAssertNil(unreported.gamesContent(reader: false)?.reportLabel)
        // Unreadable source text or no entry words: no source entry.
        var noSource = input
        noSource.source = SquashEventPageText10868(title: " ", sections: [SquashEventPageSection10868(title: nil, paragraphs: ["\n"])])
        XCTAssertFalse(SquashEventPageModel10868(noSource).sourceAvailable(canOpen: true))
        XCTAssertNil(SquashEventPagePresentation10868(input: noSource, mode: .source).sourceContent())
        XCTAssertEqual(log, [])

        // No hook: each page callback is the owner's own.
        view(hook: false).openAllProps()
        view(hook: false).gamesContent(reader: false)?.onExpand?()
        XCTAssertEqual(log, ["allProps", "games:expand"])
    }

    func testAHeldOriginalAndInspectionSurviveUpdatesOmissionRestoreAndEveryModeAndPhase() {
        let held = Self.selection(.asal)

        // The held original through every mode and phase, never replaced.
        let modes: [SquashEventPageMode10868] = [.page, .fullHistory, .fullGames, .catalogue, .original, .about, .source, .report]
        for phase in SquashEventPagePhase10868.allCases {
            for mode in modes {
                let view = SquashEventPagePresentation10868(input: Self.page(phase), mode: mode, originals: Self.originals(phase))
                XCTAssertEqual(view.chooserContent()?.selection, held)
                XCTAssertEqual(view.catalogueContent()?.selection, held)
                XCTAssertEqual(view.originalDetailsContent()?.selection, held)
            }
        }

        // A CONSTRUCTED update omits the held original: no Details, no
        // neighbour selected in its place, and Elias stays usable.
        let omitted = Self.catalogue(.final, originals: [Self.original(.elias, .final)])
        let afterOmission = Self.originals(.final, catalogue: omitted)
        XCTAssertNil(OriginalMarketDetails9483.content(catalogue: omitted, selection: held))
        let omissionChoices = Self.choices(afterOmission)
        XCTAssertEqual(omissionChoices.map(\.label), ["Elias to win"])
        XCTAssertEqual(omissionChoices.map(\.isSelected), [false])
        XCTAssertEqual(omissionChoices.first?.selection, Self.selection(.elias))
        XCTAssertEqual(SquashEventPagePresentation10868(input: Self.page(.final), mode: .original, originals: afterOmission)
                        .originalDetailsContent()?.selection, held)
        // Restored: the same exact original opens again.
        let restored = Self.originals(.final)
        XCTAssertEqual(OriginalMarketDetails9483.content(catalogue: restored.catalogue, selection: held)?.title,
                       "Will Mostafa Assal win the Assal vs Elias: Semifinal match?")
        XCTAssertEqual(Self.choices(restored).map(\.isSelected), [true, false])

        // Withdrawn (no readable title) or ambiguous (one identity twice):
        // no dead control, and the valid neighbour keeps working.
        let withdrawn = Self.originals(.final, catalogue: Self.catalogue(.final, originals: [
            Self.original(.asal, .final, blankTitle: true), Self.original(.elias, .final),
        ]))
        XCTAssertEqual(Self.choices(withdrawn).map { $0.selection != nil }, [false, true])
        let ambiguous = Self.originals(.final, catalogue: Self.catalogue(.final, originals: [
            Self.original(.asal, .final), Self.original(.asal, .final), Self.original(.elias, .final),
        ]))
        XCTAssertEqual(Self.choices(ambiguous).map { $0.selection != nil }, [false, false, true])
        XCTAssertNil(OriginalMarketDetails9483.content(catalogue: ambiguous.catalogue, selection: held))

        // Mixed results: an original without its own result stays unresolved,
        // whatever the match verdict.
        let mixed = Self.catalogue(.final, originals: [Self.original(.asal, .final), Self.original(.elias, .final, eliasGrade: false)])
        XCTAssertEqual(OriginalMarketDetails9483.content(catalogue: mixed, selection: Self.selection(.asal))?.result?.words, "Won")
        XCTAssertEqual(OriginalMarketDetails9483.content(catalogue: mixed, selection: Self.selection(.elias))?.result?.words,
                       OriginalMarketDetails9483.resultUnavailable)
        XCTAssertEqual(Self.games(.final).visibleMatch?.value, "3–2", "the match verdict is a separate fact")

        // The held inspection: the page and the full-size history carry the
        // owner's same inspection; changing mode never changes it.
        let inspected = Self.page(.final, history: Self.history(.final, inspected: true))
        for mode in [SquashEventPageMode10868.page, .fullHistory] {
            let view = SquashEventPagePresentation10868(input: inspected, mode: mode)
            XCTAssertEqual(view.historyContent(reader: mode == .fullHistory).input.inspection, inspected.history.inspection)
        }
    }

    // MARK: Arrangement

    func testCompactWideAndAccessibilitySizesChooseTheirArrangements() {
        XCTAssertEqual(SquashEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(SquashEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(SquashEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(SquashEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        // Whole names travel to the leaves; the compact labels are the owner's.
        let headline = Self.headline(.final)
        XCTAssertEqual(headline.displayed.map(\.name), ["Mostafa Asal", "Diego Elias"])
        XCTAssertEqual(headline.displayed.map(\.compactName), ["Asal", "Elias"])
        XCTAssertEqual(headline.displayed.map(\.keyShape), [.circle, .diamond])
        XCTAssertEqual(Self.history(.final).series.map(\.shape), [.circle, .diamond])
        XCTAssertEqual(Self.history(.final).plotHeight, 300)
    }
}
