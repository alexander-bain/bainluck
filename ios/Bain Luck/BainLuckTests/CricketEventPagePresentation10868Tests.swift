import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the cricket Test-match screen (`cricket-live`) composed from the
/// accepted leaves.
///
/// PREPARED / NOT RUN. The view is SwiftUI and is not rasterised here. What is
/// asserted is the composition only: which actual leaf Views the page mounts
/// before the match (headline, history and originals, no story stream), at
/// two live score reports and at the final, that each
/// receives the owner's input unchanged, each original's own pregame,
/// recorded and result readings with their own clocks, the reported innings
/// state beside its own report clock and apart from every chance, the match
/// result apart from each contract's result, phase-appropriate absence, the
/// reduced history's separate runs and its guides, the story stream's
/// card-to-leaf wiring, the activation hook before each card action, the
/// owner's interaction hook before each page and catalogue action (and never
/// for full-size content, stream cards or passive reads), the full-size
/// history without its expand control, the headline's exact sources-and-timing
/// payload and the About, the original chooser, catalogue and Details, the
/// Details' optional recorded history and its history intent after the hook,
/// and the arrangement candidates the View uses. Each leaf's own rules stay with
/// its own tests; nothing here claims a rendered fit, a native runtime,
/// VoiceOver behaviour, a stream hold qualification, a production binding, or
/// any other route.
///
/// ARCHIVED raw values: the South Africa v Australia first Test at Durban,
/// Kalshi event KXTESTMATCH-26OCT090330AUSSA, as retained by the accepted
/// cricket headline, history, chase, survival and outlook cases and the pinned
/// reference `cricketLiveCapture.json` / `cricketLifecycleCapture.json`:
/// - three independent Yes originals, each with its own last pregame hourly
///   close at the reference's before-match cutoff 2026-10-09T00:00:00Z (not
///   proof of the first ball): South Africa (-SA) 0.48, Australia (-AUS) 0.47,
///   Draw/tie (-TIE) 0.09 — sum 1.04, never normalized;
/// - the four live score reports (publication clocks, never ball or wicket
///   times): 64 overs 154/4 at 09:11:34Z, lunch 73 overs 166/6 at 09:49:56Z, 84
///   overs 201/6 at 11:03:34Z, 85 overs 201/8 at 11:11:58Z; target 421;
/// - each original's own retained minute close at each report: 64 overs SA
///   0.03 (bar 09:11), AUS 0.64 (09:11), TIE 0.35 (09:11); lunch TIE 0.17
///   (09:45); 84 overs TIE 0.20 (11:02); 85 overs SA 0.01 (11:09), AUS 0.95
///   (11:11), TIE 0.03 (11:11) — candle periods, not trade times;
/// - the final score report at 11:24:20Z: South Africa 206 all out, Australia
///   won by 214 runs, final overs not reported; the separate confirmation at
///   11:26:55Z; each contract's own separately retained result (SA no, AUS
///   yes, TIE no), finalized at 12:35:49Z — later than and separate from the
///   physical result;
/// - a REDUCED SUBSET of each original's retained closes, NOT the complete
///   journey: before, the last hourly closes up to the cutoff (the Draw/tie
///   hours at 19:00, 20:00 and 22:00 have no close); at 64 overs the minute
///   closes 09:06–09:11; at 85 overs and the final a few minute closes from
///   11:03. A minute absent from the retained closes, or left out of this
///   subset, starts a new run, so no line joins across it. No 0% or 100%
///   point is added at the result.
/// Lunch and 84 overs are prepared only as survival checkpoints and history
/// guides, not as page moments.
///
/// CONSTRUCTED (owner display words, not retained facts): every label, figure
/// text, local-calendar provenance line (PDT), movement word, caption, state
/// word, story reason (the reference `cricketMomentOrder` output for each
/// moment; the rule itself is not ported), stream metadata, history domain,
/// tick words (the owner's PDT date and clock for each window's bounds:
/// Oct 8, 10 AM–5 PM before play; Oct 13 from 2 AM or 4 AM to the report's
/// own clock during and after), window and inspection, marker words, About
/// text, tints, originals scope and grade words, the Details' recorded-history
/// context (contract input with no drawn closes, never history evidence), and
/// every canonical reference — no production original or app id is retained,
/// so `constructed.*` refs stand in for the owner's canonical binding.
final class CricketEventPagePresentation10868Tests: XCTestCase {

    // MARK: Retained facts

    private enum Moment { case before, over64, over85, final }

    private static let event = "KXTESTMATCH-26OCT090330AUSSA"
    private static let sides = ["SA", "AUS", "TIE"]
    private static let subjects = ["South Africa", "Australia", "Draw / tie"]
    private static let titles = ["South Africa wins", "Australia wins", "Draw/Tie wins"]
    private static let outcomes = ["South Africa", "Australia", "Draw/Tie"]
    private static let rules = [
        "If South Africa wins the South Africa vs Australia men's professional Test series cricket match originally scheduled for Oct 9, 2026 at 3:30 AM EDT, then the market resolves to Yes.",
        "If Australia wins the South Africa vs Australia men's professional Test series cricket match originally scheduled for Oct 9, 2026 at 3:30 AM EDT, then the market resolves to Yes.",
        "If South Africa and Australia draw or tie in the South Africa vs Australia men's professional Test series cricket match originally scheduled for Oct 9, 2026 at 3:30 AM EDT, then the market resolves to Yes.",
    ]
    private static let pregameValues = [0.48, 0.47, 0.09]
    private static let pregameTexts = ["48%", "47%", "9%"]

    /// Seconds since 1970 (the history's own domain unit).
    private static let pregameX: Double = 1_791_504_000       // 2026-10-09T00:00:00Z
    private static let report64X: Double = 1_791_882_694      // 09:11:34Z
    private static let reportLunchX: Double = 1_791_884_996   // 09:49:56Z
    private static let report84X: Double = 1_791_889_414      // 11:03:34Z
    private static let report85X: Double = 1_791_889_918      // 11:11:58Z
    private static let finalX: Double = 1_791_890_660         // 11:24:20Z

    /// Minute bar end `hh:mm` on Oct 13, as seconds since 1970.
    private static func minute(_ hour: Int, _ minute: Int) -> Double {
        1_791_849_600 + Double(hour * 3600 + minute * 60)
    }

    /// Hourly bar end on Oct 8 (hour 17–23) or the cutoff hour (24).
    private static func hour(_ hour: Int) -> Double {
        pregameX - Double((24 - hour) * 3600)
    }

    private static func phase(_ moment: Moment) -> CricketHeadlinePhase10868 {
        switch moment {
        case .before: .before
        case .over64, .over85: .during
        case .final: .completed
        }
    }

    // MARK: Constructed owner words

    private static let tints: [Color] = [.blue, .orange, .gray]
    private static let outlookShapes: [CricketOutlookShape10868] = [.circle, .diamond, .square]
    private static let historyShapes: [CricketHistoryShape10868] = [.circle, .diamond, .square]
    private static let pregameDetail = "Pregame · hourly close ending Oct 8, 5:00 PM PDT · Kalshi"
    private static let report64Detail = "Score report published Oct 13, 2:11 AM PDT · not the exact ball time"
    private static let finalDetail = "Final score report published Oct 13, 4:24 AM PDT; margin confirmed 4:26 AM PDT · not the exact time of the last ball"
    private static let settlementDetail = "Contract finalized Oct 13, 5:35 AM PDT"

    /// Each original's own recorded close at a live report: value, words, provenance.
    private static func recorded(_ moment: Moment) -> [(Double, String, String)]? {
        switch moment {
        case .over64:
            return [(0.03, "3%", "Recorded · minute ending Oct 13, 2:11 AM PDT · Kalshi"),
                    (0.64, "64%", "Recorded · minute ending Oct 13, 2:11 AM PDT · Kalshi"),
                    (0.35, "35%", "Recorded · minute ending Oct 13, 2:11 AM PDT · Kalshi")]
        case .over85:
            return [(0.01, "1%", "Recorded · minute ending Oct 13, 4:09 AM PDT · Kalshi"),
                    (0.95, "95%", "Recorded · minute ending Oct 13, 4:11 AM PDT · Kalshi"),
                    (0.03, "3%", "Recorded · minute ending Oct 13, 4:11 AM PDT · Kalshi")]
        case .before, .final:
            return nil
        }
    }

    private static func movement(_ moment: Moment) -> [CricketOutlookMovement10868]? {
        switch moment {
        case .over64:
            return [CricketOutlookMovement10868(text: "↓ 45 points", spoken: "Down 45 percentage points from pregame"),
                    CricketOutlookMovement10868(text: "↑ 17 points", spoken: "Up 17 percentage points from pregame"),
                    CricketOutlookMovement10868(text: "↑ 26 points", spoken: "Up 26 percentage points from pregame")]
        case .over85:
            return [CricketOutlookMovement10868(text: "↓ 47 points", spoken: "Down 47 percentage points from pregame"),
                    CricketOutlookMovement10868(text: "↑ 48 points", spoken: "Up 48 percentage points from pregame"),
                    CricketOutlookMovement10868(text: "↓ 6 points", spoken: "Down 6 percentage points from pregame")]
        case .before, .final:
            return nil
        }
    }

    private static let outcomeWords = ["Lost", "Winner", "No draw or tie"]
    private static let gradeWords = ["Lost", "Won", "Lost"]

    private static func outlookRef(_ index: Int) -> CricketOutlookRef10868 {
        CricketOutlookRef10868(event: "constructed.event.aussa", market: "constructed.market.\(sides[index])", outcome: "constructed.yes")
    }

    private static let chaseRef = CricketChaseRef10868(event: "constructed.event.aussa", market: "constructed.market.SA", outcome: "constructed.yes")
    private static let tieRef = CricketChaseRef10868(event: "constructed.event.aussa", market: "constructed.market.TIE", outcome: "constructed.yes")

    /// Every original's row. Later readings and finishes are supplied in EVERY
    /// moment (the 64-over reading before play, for example) so phase gating,
    /// not their absence, is what keeps them off a foreign phase.
    private static func rows(_ moment: Moment) -> [CricketOutlookRow10868] {
        let later = recorded(moment) ?? recorded(.over64)!
        let moves = movement(moment) ?? movement(.over64)!
        return (0..<3).map { index in
            CricketOutlookRow10868(
                id: sides[index], subject: subjects[index], shape: outlookShapes[index], tint: tints[index],
                ref: outlookRef(index),
                before: .observed(CricketOutlookObservation10868(probability: pregameValues[index], text: pregameTexts[index],
                                                                 detail: pregameDetail)),
                comparison: .observed(CricketOutlookObservation10868(probability: later[index].0, text: later[index].1,
                                                                     detail: later[index].2)),
                movement: moves[index],
                finish: CricketOutlookFinish10868(
                    outcome: .admitted(CricketOutlookFinalWord10868(text: outcomeWords[index], symbolName: nil, detail: finalDetail)),
                    grade: .admitted(CricketOutlookFinalWord10868(text: gradeWords[index], symbolName: nil, detail: settlementDetail))
                )
            )
        }
    }

    private static func headlineState(_ moment: Moment) -> CricketHeadlineState10868 {
        switch moment {
        case .final:
            return .reported(CricketHeadlineStateFrame10868(
                entries: [CricketHeadlineStateEntry10868(label: "South Africa", text: "206 all out", spoken: "206 all out"),
                          CricketHeadlineStateEntry10868(label: nil, text: "Australia won by 214 runs", spoken: "Australia won by 214 runs")],
                detail: finalDetail + " · final overs not reported"))
        case .over85:
            return .reported(CricketHeadlineStateFrame10868(
                entries: [CricketHeadlineStateEntry10868(label: "South Africa · batting", text: "201/8", spoken: "201 for 8"),
                          CricketHeadlineStateEntry10868(label: "85 overs", text: "Target 421", spoken: "Target 421 runs")],
                detail: "Score report published Oct 13, 4:11 AM PDT · not the exact ball time"))
        case .before, .over64:
            // Supplied before play too; the headline shows it only during and after.
            return .reported(CricketHeadlineStateFrame10868(
                entries: [CricketHeadlineStateEntry10868(label: "South Africa · batting", text: "154/4", spoken: "154 for 4"),
                          CricketHeadlineStateEntry10868(label: "64 overs", text: "Target 421", spoken: "Target 421 runs")],
                detail: report64Detail))
        }
    }

    private static func headline(_ moment: Moment) -> CricketHeadlineInput10868 {
        let caption: String = switch moment {
        case .before: "Pregame · Oct 8, 5:00 PM PDT"
        case .over64: "Recorded chances · Day 5 · 64 overs"
        case .over85: "Recorded chances · Day 5 · 85 overs"
        case .final: "Final · Australia won by 214 runs"
        }
        return CricketHeadlineInput10868(
            phase: phase(moment), caption: caption, beforeLabel: "Pregame", comparisonLabel: "Recorded",
            outcomeLabel: "Match", outcomeMissing: "Not reported", rows: rows(moment), state: headlineState(moment))
    }

    private static func shifts(_ moment: Moment) -> CricketOutlookInput10868 {
        CricketOutlookInput10868(
            eyebrow: "Pregame → recorded chance", title: "How the outlook changed", beforeLabel: "Pregame",
            comparisonLabel: "Recorded", rows: rows(moment), selectedRowID: nil,
            notes: ["Changes are percentage points, not runs or wickets."])
    }

    private static func expectations() -> CricketOutlookInput10868 {
        CricketOutlookInput10868(
            eyebrow: "Pregame expectations → result", title: "Australia was 47% pregame", beforeLabel: "Pregame",
            comparisonLabel: "Recorded", rows: rows(.final), selectedRowID: "AUS",
            notes: ["Result labels describe the match, not later probabilities."],
            mode: .completed(CricketOutlookFinalFrame10868(
                outcomeLabel: "Match", outcomeMissing: "Not reported", gradeLabel: "Original contract",
                context: ["South Africa 206 all out · target 421", "Final overs not reported"])))
    }

    private static func wickets(lost: Int) -> [CricketChaseWicket10868] {
        Array(repeating: .lost, count: lost) + Array(repeating: .remaining, count: 10 - lost)
    }

    private static func chase(_ moment: Moment) -> CricketChaseInput10868 {
        let pregame = CricketChaseReading10868.observed(CricketChaseFigure10868(text: "48%", detail: pregameDetail))
        switch moment {
        case .final:
            return CricketChaseInput10868(
                phase: .final, subject: "South Africa", eyebrow: "The chase · final", headline: nil,
                pregameLabel: "Pregame", pregame: pregame, comparisonLabel: "Recorded win chance",
                comparison: .withheld("Settled — not a chance"), resultLabel: "Final",
                contractResult: .graded(CricketChaseFigure10868(text: "Lost", detail: settlementDetail)),
                matchResult: .reported(CricketChaseFigure10868(text: "Australia won by 214 runs", detail: finalDetail)),
                actual: .reported(CricketChaseState10868(
                    battingSubject: "South Africa", context: nil, runs: .reported(text: "206", value: 206),
                    runsCaption: "all out", target: .reported(text: "421", value: 421), targetCaption: "runs",
                    wickets: wickets(lost: 10), wicketsText: "All ten wickets lost", oversText: "Final overs not reported",
                    reportDetail: finalDetail)),
                detailsRef: chaseRef, notes: ["Reported final. Target is not a projection."])
        case .over85:
            return CricketChaseInput10868(
                phase: .during, subject: "South Africa", eyebrow: "South Africa · second innings",
                headline: "220 runs still needed", pregameLabel: "Pregame", pregame: pregame,
                comparisonLabel: "Recorded win chance",
                comparison: .observed(CricketChaseFigure10868(text: "1%", detail: recorded(.over85)![0].2)),
                resultLabel: "Final", contractResult: .unavailable("Not yet confirmed"),
                matchResult: .unavailable("Not reported"),
                actual: .reported(CricketChaseState10868(
                    battingSubject: "South Africa", context: "Day 5 · 85 overs", runs: .reported(text: "201", value: 201),
                    runsCaption: "runs scored", target: .reported(text: "421", value: 421), targetCaption: "runs",
                    wickets: wickets(lost: 8), wicketsText: "2 wickets left", oversText: "85 overs played",
                    reportDetail: "Score report published Oct 13, 4:11 AM PDT · not the exact ball time")),
                detailsRef: chaseRef, notes: ["Target, not projected finish."])
        case .before, .over64:
            // Supplied before play too, as a during-play chase; never mounted then.
            return CricketChaseInput10868(
                phase: .during, subject: "South Africa", eyebrow: "South Africa · second innings",
                headline: "267 runs still needed", pregameLabel: "Pregame", pregame: pregame,
                comparisonLabel: "Recorded win chance",
                comparison: .observed(CricketChaseFigure10868(text: "3%", detail: recorded(.over64)![0].2)),
                resultLabel: "Final", contractResult: .unavailable("Not yet confirmed"),
                matchResult: .unavailable("Not reported"),
                actual: .reported(CricketChaseState10868(
                    battingSubject: "South Africa", context: "Day 5 · 64 overs", runs: .reported(text: "154", value: 154),
                    runsCaption: "runs scored", target: .reported(text: "421", value: 421), targetCaption: "runs",
                    wickets: wickets(lost: 4), wicketsText: "6 wickets left", oversText: "64 overs played",
                    reportDetail: report64Detail)),
                detailsRef: chaseRef, notes: ["Target, not projected finish."])
        }
    }

    /// The four retained report checkpoints, each with its own report and its
    /// own separately timed Draw/tie close, all on ONE shared original.
    private static let checkpoints: [CricketSurvivalCheckpoint10868] = [
        ("block-6acdf5298f084a13d13ca4ea", "Day 5 · 64 overs", 4, "6 wickets left", "2:11", "35%", "2:11"),
        ("block-6acdfe288f08741d63f9bedf", "Day 5 · lunch · 73 overs", 6, "4 wickets left", "2:49", "17%", "2:45"),
        ("block-6ace0f308f0874762783cf04", "Day 5 · 84 overs", 6, "4 wickets left", "4:03", "20%", "4:02"),
        ("block-6ace11b98f0811efce0fe34a", "Day 5 · 85 overs", 8, "2 wickets left", "4:11", "3%", "4:11"),
    ].map { id, label, lost, left, reported, chance, bar in
        CricketSurvivalCheckpoint10868(
            id: id, ref: tieRef, label: label,
            actual: .reported(CricketSurvivalReport10868(
                wickets: wickets(lost: lost), wicketsText: left,
                reportDetail: "Score report published Oct 13, \(reported) AM PDT · not the exact ball time")),
            chanceLabel: "Recorded draw / tie",
            chance: .observed(CricketChaseFigure10868(text: chance, detail: "Minute ending Oct 13, \(bar) AM PDT · Kalshi")))
    }

    private static func survival(_ moment: Moment) -> CricketSurvivalInput10868 {
        let count = moment == .over85 ? 4 : 1
        let headline = moment == .over85 ? recorded(.over85)![2] : recorded(.over64)![2]
        return CricketSurvivalInput10868(
            phase: phase(moment) == .during ? .during : .final, subject: "Draw / tie · original market",
            title: "Can they hold on?", pregameLabel: "Pregame",
            pregame: .observed(CricketChaseFigure10868(text: "9%", detail: pregameDetail)),
            comparisonLabel: "Recorded draw / tie chance",
            comparison: .observed(CricketChaseFigure10868(text: headline.1, detail: headline.2)),
            checkpointsLabel: "Reported wickets remaining and separately timed draw or tie probabilities",
            checkpoints: Array(checkpoints.prefix(count)), selectedCheckpointID: nil,
            notes: ["Wickets show the reported score. Percentages are separate market observations."])
    }

    // MARK: History (reduced subset)

    private static func segment(_ side: String, _ points: [(Double, Double)], pregameAt: Double? = nil) -> CricketHistorySegment10868 {
        CricketHistorySegment10868(
            id: "\(side).\(Int(points[0].0))",
            points: points.map { x, value in
                CricketHistoryPoint10868(id: "\(side).\(Int(x))", x: x, probability: value, isPregame: x == pregameAt)
            })
    }

    /// Each original's segments: a new run wherever a minute or hour is
    /// absent from the retained closes or left out of this subset.
    private static func segments(_ moment: Moment) -> [[CricketHistorySegment10868]] {
        let m = minute
        switch moment {
        case .before:
            return [
                [segment("SA", [(hour(20), 0.48), (hour(21), 0.48), (hour(22), 0.48), (hour(23), 0.48), (pregameX, 0.48)], pregameAt: pregameX)],
                [segment("AUS", [(hour(20), 0.46), (hour(21), 0.47), (hour(22), 0.47), (hour(23), 0.47), (pregameX, 0.47)], pregameAt: pregameX)],
                [segment("TIE", [(hour(17), 0.09), (hour(18), 0.09)]),
                 segment("TIE", [(hour(21), 0.09)]),
                 segment("TIE", [(hour(23), 0.09), (pregameX, 0.09)], pregameAt: pregameX)],
            ]
        case .over64:
            return [
                [segment("SA", [(m(9, 6), 0.04), (m(9, 7), 0.04), (m(9, 8), 0.04)]), segment("SA", [(m(9, 11), 0.03)])],
                [segment("AUS", [(m(9, 6), 0.59), (m(9, 7), 0.63), (m(9, 8), 0.64), (m(9, 9), 0.65), (m(9, 10), 0.60), (m(9, 11), 0.64)])],
                [segment("TIE", [(m(9, 6), 0.34), (m(9, 7), 0.34), (m(9, 8), 0.34)]), segment("TIE", [(m(9, 11), 0.35)])],
            ]
        case .over85:
            return [
                [segment("SA", [(m(11, 3), 0.02), (m(11, 4), 0.02), (m(11, 5), 0.01)]), segment("SA", [(m(11, 9), 0.01)])],
                [segment("AUS", [(m(11, 3), 0.79), (m(11, 4), 0.87), (m(11, 5), 0.87)]),
                 segment("AUS", [(m(11, 8), 0.94), (m(11, 9), 0.96), (m(11, 10), 0.94), (m(11, 11), 0.95)])],
                [segment("TIE", [(m(11, 4), 0.15), (m(11, 5), 0.10)]),
                 segment("TIE", [(m(11, 7), 0.13), (m(11, 8), 0.05), (m(11, 9), 0.04), (m(11, 10), 0.05), (m(11, 11), 0.03)])],
            ]
        case .final:
            return [
                [segment("SA", [(m(11, 3), 0.02), (m(11, 4), 0.02), (m(11, 5), 0.01)]), segment("SA", [(m(11, 9), 0.01)]),
                 segment("SA", [(m(11, 12), 0.01)])],
                [segment("AUS", [(m(11, 3), 0.79), (m(11, 4), 0.87), (m(11, 5), 0.87)]),
                 segment("AUS", [(m(11, 8), 0.94), (m(11, 9), 0.96), (m(11, 10), 0.94), (m(11, 11), 0.95), (m(11, 12), 0.96),
                                 (m(11, 13), 0.98), (m(11, 14), 0.97), (m(11, 15), 0.97), (m(11, 16), 0.99)]),
                 segment("AUS", [(m(11, 23), 0.99), (m(11, 24), 0.99)])],
                [segment("TIE", [(m(11, 4), 0.15), (m(11, 5), 0.10)]),
                 segment("TIE", [(m(11, 7), 0.13), (m(11, 8), 0.05), (m(11, 9), 0.04), (m(11, 10), 0.05), (m(11, 11), 0.03), (m(11, 12), 0.03)]),
                 segment("TIE", [(m(11, 15), 0.01), (m(11, 16), 0.01)])],
            ]
        }
    }

    private static func domain(_ moment: Moment) -> CricketHistoryDomain10868 {
        switch moment {
        case .before: CricketHistoryDomain10868(lower: hour(17), upper: pregameX)
        case .over64: CricketHistoryDomain10868(lower: minute(9, 0), upper: report64X)
        case .over85: CricketHistoryDomain10868(lower: minute(11, 0), upper: report85X)
        case .final: CricketHistoryDomain10868(lower: minute(11, 0), upper: finalX)
        }
    }

    /// The owner's PDT words for each window's two bounds.
    private static func xTickLines(_ moment: Moment) -> [[String]] {
        switch moment {
        case .before: [["Oct 8", "10 AM"], ["Oct 8", "5 PM"]]
        case .over64: [["Oct 13", "2 AM"], ["2:11 AM", "64-over report"]]
        case .over85: [["Oct 13", "4 AM"], ["4:11 AM", "85-over report"]]
        case .final: [["Oct 13", "4 AM"], ["4:24 AM", "Final report"]]
        }
    }

    private static func history(_ moment: Moment) -> CricketHistoryInput10868 {
        let span = domain(moment)
        let ticks = xTickLines(moment)
        let through = moment == .before ? "the last pregame hour" : "the selected report"
        let series = (0..<3).map { index in
            CricketHistorySeries10868(id: sides[index], name: subjects[index], shape: historyShapes[index], tint: tints[index],
                                      segments: segments(moment)[index], absentWords: "No recorded trades")
        }
        let window: CricketHistoryWindow10868 = moment == .before
            ? .caption("Hourly history")
            : .choices(groupLabel: "Cricket history window",
                       choices: [CricketHistoryWindowChoice10868(id: "match", label: "Match", isSelected: false),
                                 CricketHistoryWindowChoice10868(id: "day5", label: "Day 5", isSelected: true)])
        let inspection: CricketHistoryInspection10868? = moment == .over64
            ? CricketHistoryInspection10868(
                x: minute(9, 11), caption: "Selected · Oct 13, 2:11 AM PDT",
                selections: ["SA": .point(id: "SA.\(Int(minute(9, 11)))", spoken: "3%"),
                             "AUS": .point(id: "AUS.\(Int(minute(9, 11)))", spoken: "64%"),
                             "TIE": .point(id: "TIE.\(Int(minute(9, 11)))", spoken: "35%")])
            : nil
        return CricketHistoryInput10868(
            title: "Win probability", series: series, domain: span,
            yTicks: [CricketHistoryTick10868(value: 0, lines: ["0%"]), CricketHistoryTick10868(value: 0.5, lines: ["50%"]),
                     CricketHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: [CricketHistoryTick10868(value: span.lower, lines: ticks[0]),
                     CricketHistoryTick10868(value: span.upper, lines: ticks[1])],
            context: "Recorded Kalshi closes through \(through) · times in Pacific Daylight Time",
            pregameKey: "Pregame",
            summary: "South Africa circles, Australia diamonds and draw or tie squares; only recorded closes through \(through).",
            plotHeight: 302, window: window, inspection: inspection,
            previous: CricketHistoryControl10868(label: "Previous recorded interval", isAvailable: true),
            next: CricketHistoryControl10868(label: "Next recorded interval", isAvailable: false),
            expand: CricketHistoryControl10868(label: "Open cricket probability chart", isAvailable: true))
    }

    private static func marker(_ id: String, _ x: Double?, _ label: String?, prominent: Bool = false) -> CricketHistoryMarker10868 {
        CricketHistoryMarker10868(id: id, x: x, emphasis: prominent ? .prominent : .subtle, label: label,
                                  spoken: "\(label ?? id) score report publication time; not an exact ball time",
                                  absentWords: x == nil ? "Report time not held" : nil)
    }

    private static func markers(_ moment: Moment) -> CricketHistoryMarkerContext10868 {
        let key = "Score-report publication times; not exact ball times"
        switch moment {
        case .before:
            // Later guides supplied before play: the leaf draws none of them.
            return CricketHistoryMarkerContext10868(phase: .before, markers: [marker("64", report64X, "64 overs")], key: key)
        case .over64:
            return CricketHistoryMarkerContext10868(phase: .during, markers: [marker("64", report64X, "64 overs")], key: key)
        case .over85:
            return CricketHistoryMarkerContext10868(
                phase: .during, markers: [marker("84", report84X, "84 overs"), marker("85", report85X, "85 overs")], key: key)
        case .final:
            return CricketHistoryMarkerContext10868(
                phase: .completed,
                markers: [marker("84", report84X, "84 overs"), marker("85", report85X, "85 overs"),
                          marker("final", finalX, "Final report", prominent: true)], key: key)
        }
    }

    // MARK: Stream and page

    private static func scope(_ moment: Moment) -> String {
        switch moment {
        case .before: "cricket-moment:before"
        case .over64: "cricket-moment:0"
        case .over85: "cricket-moment:3"
        case .final: "cricket-moment:final"
        }
    }

    /// Before play there is no stream: the reference offers only the history.
    private static func stream(_ moment: Moment, wide: Bool = false) -> StoryStreamPresentation10868? {
        let scope = scope(moment)
        func ref(_ id: String) -> StoryStreamPresentation10868.CardRef { .init(scope: scope, id: id) }
        typealias Card = StoryStreamPresentation10868.Card
        switch moment {
        case .before:
            return nil
        case .over64:
            return StoryStreamPresentation10868(
                scope: scope, eyebrow: nil, heading: "Match stories",
                cards: [Card(id: "shifts", name: "Changing expectations"), Card(id: "chase", name: "The chase"),
                        Card(id: "survival", name: "Holding on")],
                primary: ref("shifts"), companion: ref("chase"), companionLabel: "Next", wide: wide,
                position: "1 of 3", status: "Cards advance when you’re watching", playback: .pause,
                previous: nil, next: ref("chase"))
        case .over85:
            return StoryStreamPresentation10868(
                scope: scope, eyebrow: nil, heading: "Match stories",
                cards: [Card(id: "survival", name: "Holding on"), Card(id: "shifts", name: "Changing expectations"),
                        Card(id: "chase", name: "The chase")],
                primary: ref("survival"), companion: ref("shifts"), companionLabel: "Next", wide: wide,
                position: "1 of 3", playback: .pause, previous: nil, next: ref("shifts"))
        case .final:
            return StoryStreamPresentation10868(
                scope: scope, eyebrow: nil, heading: "After the match",
                cards: [Card(id: "expectations", name: "Expectations and result"), Card(id: "chase", name: "The final chase")],
                primary: ref("expectations"), companion: ref("chase"), companionLabel: "Next", wide: wide,
                position: "1 of 2", previous: nil, next: ref("chase"))
        }
    }

    private static func stories(_ moment: Moment) -> [CricketEventPageStory10868] {
        switch moment {
        case .before:
            return []
        case .over64:
            return [CricketEventPageStory10868(cardID: "shifts", card: .shifts, reason: "South Africa win chance fell 45.0 points from pregame."),
                    CricketEventPageStory10868(cardID: "chase", card: .chase, reason: "South Africa still need 267 runs to win."),
                    CricketEventPageStory10868(cardID: "survival", card: .survival, reason: "6 wickets remain at the 64.0-over report.")]
        case .over85:
            return [CricketEventPageStory10868(cardID: "survival", card: .survival, reason: "2 wickets lost since the 84.0-over report; 2 remain."),
                    CricketEventPageStory10868(cardID: "shifts", card: .shifts, reason: "Australia win chance rose 48.0 points from pregame."),
                    CricketEventPageStory10868(cardID: "chase", card: .chase, reason: "South Africa still need 220 runs to win.")]
        case .final:
            return [CricketEventPageStory10868(cardID: "expectations", card: .expectations),
                    CricketEventPageStory10868(cardID: "chase", card: .chase)]
        }
    }

    private static func reader(_ moment: Moment) -> CricketEventPageReaderHeader10868 {
        switch moment {
        case .before: CricketEventPageReaderHeader10868(title: "South Africa · Australia", state: "Before match · recorded probabilities")
        case .over64: CricketEventPageReaderHeader10868(title: "South Africa 154/4", state: "Score report · Day 5 · 64 overs · target 421")
        case .over85: CricketEventPageReaderHeader10868(title: "South Africa 201/8", state: "Score report · Day 5 · 85 overs · target 421")
        case .final: CricketEventPageReaderHeader10868(title: "Australia won by 214 runs", state: "Final · South Africa 206 all out")
        }
    }

    private static let about = CricketEventPageAbout10868(
        title: "Recorded final-day play",
        paragraphs: ["South Africa versus Australia, first Test in Durban, October 9–13, 2026.",
                     "Report times are publication times, not exact ball times. A target of 421 is not a projected finish.",
                     "Each outcome uses its own recorded Kalshi close; the three need not sum to 100%."])

    private static let copy = CricketEventPageCopy10868(
        storiesLabel: "Match stories", storyUnavailable: "This story is not available in this update.",
        headlineUnavailable: "Match chances unavailable in this update.", aboutLabel: "About this match",
        allPropsLabel: "All 3 original markets")

    /// Every leaf input is supplied in every moment; only the page phase and
    /// each leaf's own phase or mode decide what mounts.
    private static func page(_ moment: Moment, wide: Bool = false, headline: CricketHeadlineInput10868? = nil,
                             copy: CricketEventPageCopy10868? = nil) -> CricketEventPageInput10868 {
        let livePhaseFor: Moment = moment == .over85 ? .over85 : .over64
        return CricketEventPageInput10868(
            phase: phase(moment),
            title: CricketEventPageTitle10868(eyebrow: "Recorded · First Test · Durban", title: "South Africa · Australia"),
            reader: reader(moment), headline: headline ?? Self.headline(moment), secondaryProvenance: true,
            notice: moment == .over85 ? "No recent probability update · recorded history retained" : nil,
            history: history(moment), historyMarkers: markers(moment), readerPlotHeight: 350,
            shifts: shifts(livePhaseFor), chase: chase(moment == .final ? .final : livePhaseFor),
            survival: survival(livePhaseFor), expectations: expectations(),
            runsTint: .blue, wicketTint: .orange,
            stream: stream(moment, wide: wide), stories: stories(moment), about: about, copy: copy ?? Self.copy)
    }

    // MARK: Originals

    private static let originalsScope = "constructed.scope.cricket-live.aussa"

    private static func identity(_ index: Int) -> OriginalMarketDetails9483.Identity {
        OriginalMarketDetails9483.Identity(source: "kalshi", market: "\(event)-\(sides[index])", side: "Yes")
    }

    private static func selection(_ index: Int) -> OriginalMarketDetails9483.Selection {
        OriginalMarketDetails9483.Selection(scope: originalsScope, identity: identity(index))
    }

    private static func catalogue(_ moment: Moment, blankTitleAt blank: Int? = nil) -> OriginalMarketDetails9483.Catalogue {
        let later = recorded(moment)
        let originals = (0..<3).map { index -> OriginalMarketDetails9483.Original in
            let mode: OriginalMarketDetails9483.Mode = switch moment {
            case .before: .pregame
            case .over64, .over85: .comparison(.recorded)
            case .final: .result
            }
            return OriginalMarketDetails9483.Original(
                identity: identity(index), title: index == blank ? " " : titles[index], outcome: outcomes[index], mode: mode,
                pregame: .value(pregameTexts[index], placement: pregameValues[index], provenance: pregameDetail),
                later: later.map { .value($0[index].1, placement: $0[index].0, provenance: $0[index].2) },
                grade: moment == .final ? OriginalMarketDetails9483.Grade(words: gradeWords[index], provenance: settlementDetail) : nil,
                about: OriginalMarketDetails9483.About(
                    source: "Kalshi · \(event)-\(sides[index])", rules: .verified([rules[index]]),
                    provenance: [OriginalMarketDetails9483.Row(label: "Original pregame source time", value: "2026-10-09T00:00:00Z")],
                    historicalQuote: nil))
        }
        return OriginalMarketDetails9483.Catalogue(scope: originalsScope, originals: originals)
    }

    private static func originals(_ moment: Moment, selected: Int? = 1, blankTitleAt blank: Int? = nil,
                                  recorded: OriginalMarketDetails9483.RecordedHistory? = nil) -> CricketEventPageOriginals10868 {
        CricketEventPageOriginals10868(
            catalogue: catalogue(moment, blankTitleAt: blank), selection: selected.map { selection($0) },
            recorded: recorded, heading: "All 3 original markets", context: "3 retained originals",
            emptyWords: "No retained originals for this match", unavailableChoice: "Original unavailable", tint: .blue)
    }

    private static func activation(_ stream: StoryStreamPresentation10868, _ id: String,
                                   log: @escaping (String) -> Void) -> StoryStreamCardActivation10868 {
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: id)
        return StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
            if case .interaction(_, let card) = intent { log("hold:\(card?.id ?? "-")") } else { log("other") }
        }
    }

    private static func allPoints(_ series: CricketHistorySeries10868) -> [CricketHistoryPoint10868] {
        series.segments.flatMap(\.points)
    }

    // MARK: Phases

    @MainActor
    func testBeforeTheMatchMountsTheHeadlineHourlyHistoryAndOriginalsWithNoStoryStreamAndHidesEveryLaterInput() {
        let input = Self.page(.before)
        let model = CricketEventPageModel10868(input)
        let originals = Self.originals(.before)
        let view = CricketEventPagePresentation10868(input: input, originals: originals)

        // The headline shows each original's own pregame chance only.
        XCTAssertEqual(view.headlineContent()?.input, input.headline)
        XCTAssertEqual(input.headline.slots, [.pregame])
        XCTAssertEqual(input.headline.sourceInfo.subjects.map { $0.entries.map(\.text) }, [["48%"], ["47%"], ["9%"]])
        XCTAssertNil(input.headline.visibleState, "the supplied 154/4 state stays hidden before play")

        // The reference's before phase offers only the history as a reader
        // card: no story stream and no story link. Every later card is
        // supplied and not mounted.
        XCTAssertNil(input.stream)
        XCTAssertTrue(input.stories.isEmpty)
        XCTAssertNotNil(input.shifts)
        XCTAssertNotNil(input.chase)
        XCTAssertNotNil(input.survival)
        XCTAssertNotNil(input.expectations)
        XCTAssertNil(view.shiftsContent())
        XCTAssertNil(view.chaseContent())
        XCTAssertNil(view.survivalContent())
        XCTAssertNil(view.expectationsContent())
        XCTAssertEqual(CricketEventPageCard10868.allCases.filter(model.isMounted), [.history])
        XCTAssertTrue(model.readerShows(.history))
        XCTAssertNil(model.story("pregame"))

        // The three originals with the held original's Details.
        XCTAssertEqual(view.chooserContent()?.catalogue, originals.catalogue)
        XCTAssertEqual(view.chooserContent()?.selection, originals.selection)

        // The anchor is the owner's hourly history, ending at the pregame cutoff:
        // only that hour is hollow, the Draw/tie hours without a close are
        // separate runs, and the three last values stay 104%.
        let anchor = view.historyContent(reader: false)
        XCTAssertEqual(anchor.input, input.history)
        XCTAssertEqual(anchor.input.window, .caption("Hourly history"))
        XCTAssertEqual(anchor.input.series.map(\.name), Self.subjects)
        XCTAssertEqual(anchor.input.series.map { Self.allPoints($0).filter(\.isPregame).map(\.x) },
                       [[Self.pregameX], [Self.pregameX], [Self.pregameX]])
        XCTAssertTrue(anchor.input.series.allSatisfy { Self.allPoints($0).allSatisfy { $0.x <= Self.pregameX } })
        XCTAssertEqual(anchor.input.series[2].segments.map { $0.points.map(\.x) },
                       [[Self.hour(17), Self.hour(18)], [Self.hour(21)], [Self.hour(23), Self.pregameX]])
        let last = anchor.input.series.compactMap { Self.allPoints($0).last?.probability }
        XCTAssertEqual(last, Self.pregameValues)
        XCTAssertEqual(last.reduce(0, +), 1.04, accuracy: 1e-9)
        // The axis words are the owner's PDT date and clock for the hourly
        // window, Oct 8 10 AM to 5 PM, never the Oct 13 match day.
        XCTAssertEqual(anchor.input.xTicks.map(\.value), [Self.hour(17), Self.pregameX])
        XCTAssertEqual(anchor.input.xTicks.map(\.lines), [["Oct 8", "10 AM"], ["Oct 8", "5 PM"]])
        // The guides arrive at the page's phase; the leaf itself draws none before play.
        XCTAssertEqual(anchor.markers, input.historyMarkers)
        XCTAssertEqual(anchor.markers?.phase, .before)
    }

    @MainActor
    func testAtTheSixtyFourOverReportEveryLiveLeafMountsWithItsOwnChancesScoreAndClocks() {
        let input = Self.page(.over64)
        let model = CricketEventPageModel10868(input)
        let view = CricketEventPagePresentation10868(input: input)

        // Headline: pregame beside each original's own recorded close, and the
        // owner's score words under their own report clock.
        let headline = try? XCTUnwrap(view.headlineContent())
        XCTAssertEqual(headline?.input, input.headline)
        XCTAssertEqual(input.headline.sourceInfo.subjects.map { $0.entries.map(\.text) },
                       [["48%", "3%"], ["47%", "64%"], ["9%", "35%"]])
        XCTAssertEqual(input.headline.sourceInfo.subjects.map { $0.entries.map(\.detail) },
                       (0..<3).map { index -> [String?] in [Self.pregameDetail, Self.recorded(.over64)![index].2] })
        XCTAssertEqual(input.headline.accessibilityState,
                       "South Africa · batting: 154 for 4. 64 overs: Target 421 runs. \(Self.report64Detail)")

        // Changing expectations, the chase and holding on mount; the result
        // card does not.
        XCTAssertEqual(CricketEventPageCard10868.allCases.filter(model.isMounted), [.history, .shifts, .chase, .survival])
        XCTAssertNil(view.expectationsContent())

        let shifts = view.shiftsContent()
        XCTAssertEqual(shifts?.input, input.shifts)
        XCTAssertEqual(shifts?.input.isCompleted, false)
        XCTAssertEqual(input.shifts.map { input in input.rows.map { input.visibleMovement($0)?.text } },
                       ["↓ 45 points", "↑ 17 points", "↑ 26 points"])

        let chase = view.chaseContent()
        XCTAssertEqual(chase?.input, input.chase)
        XCTAssertEqual(chase?.input.visibleHeading, "267 runs still needed")
        XCTAssertNil(chase?.input.visibleContractResult, "no result while live")
        XCTAssertEqual(chase?.input.visibleState?.runs, .reported(text: "154", value: 154))
        XCTAssertEqual(chase?.input.visibleState?.target, .reported(text: "421", value: 421))
        XCTAssertEqual(chase?.input.visibleState?.reportDetail, Self.report64Detail)
        XCTAssertNotEqual(chase?.input.visibleState?.reportDetail, Self.recorded(.over64)![0].2,
                          "the report clock and the close's own clock stay separate facts")
        XCTAssertNil(chase?.limitedOvers, "the Test chase never takes the limited-over variant")

        let survival = view.survivalContent()
        XCTAssertEqual(survival?.input, input.survival)
        XCTAssertEqual(survival?.input.visibleCheckpoints.map(\.label), ["Day 5 · 64 overs"])

        // History ends at the report; the owner's guide sits at the report's publication time.
        let anchor = view.historyContent(reader: false)
        XCTAssertTrue(anchor.input.series.allSatisfy { Self.allPoints($0).allSatisfy { $0.x <= Self.report64X } })
        XCTAssertEqual(anchor.markers?.markers.map(\.x), [Self.report64X])
        // The axis words: Oct 13 from 2 AM PDT to the report's own clock, never
        // a "start" that could read as the first ball; steps are recorded intervals.
        XCTAssertEqual(anchor.input.xTicks.map(\.lines), [["Oct 13", "2 AM"], ["2:11 AM", "64-over report"]])
        XCTAssertEqual(anchor.input.previous?.label, "Previous recorded interval")
        XCTAssertEqual(model.storyCard("shifts"), .shifts)
        XCTAssertEqual(model.storyCard("chase"), .chase)
        XCTAssertEqual(model.storyCard("survival"), .survival)
        XCTAssertEqual(model.story("survival")?.reason, "6 wickets remain at the 64.0-over report.")
    }

    @MainActor
    func testAtTheFinalPregameChancesMeetTheReportedResultAndContractResultsStayApart() {
        let input = Self.page(.final)
        let model = CricketEventPageModel10868(input)
        let view = CricketEventPagePresentation10868(input: input)

        // Headline: pregame beside the reported match outcome — never a
        // later chance and never the contract result.
        XCTAssertEqual(view.headlineContent()?.input, input.headline)
        XCTAssertEqual(input.headline.sourceInfo.subjects.map { $0.entries.map(\.slot) },
                       Array(repeating: [.pregame, .outcome], count: 3))
        XCTAssertEqual(input.headline.sourceInfo.subjects.map { $0.entries.map(\.text) },
                       [["48%", "Lost"], ["47%", "Winner"], ["9%", "No draw or tie"]])

        XCTAssertEqual(CricketEventPageCard10868.allCases.filter(model.isMounted), [.history, .chase, .expectations])
        XCTAssertNil(view.shiftsContent())
        XCTAssertNil(view.survivalContent())

        // Expectations and result: the reported outcome and, separately, each
        // contract's own grade with its own later clock; no filled mark.
        let expectations = try? XCTUnwrap(view.expectationsContent()?.input)
        XCTAssertEqual(expectations, input.expectations)
        XCTAssertEqual(expectations?.rows.compactMap { expectations?.finalOutcome($0)?.word?.text }, Self.outcomeWords)
        XCTAssertEqual(expectations?.rows.compactMap { expectations?.finalGrade($0)?.word?.text }, Self.gradeWords)
        XCTAssertEqual(expectations?.rows.compactMap { expectations?.finalGrade($0)?.word?.detail },
                       Array(repeating: Self.settlementDetail, count: 3))
        XCTAssertEqual(expectations?.rows.map { expectations?.marks($0).comparison }, [nil, nil, nil])

        // The resolved chase: the match result as reported, the target as a
        // threshold, and the contract's own result apart from both.
        let chase = view.chaseContent()?.input
        XCTAssertEqual(chase?.visibleHeading, "Australia won by 214 runs")
        XCTAssertEqual(chase?.visibleHeadingDetail, Self.finalDetail)
        XCTAssertNil(chase?.visibleComparison, "a settled price is not a final chance")
        XCTAssertEqual(chase?.visibleContractResult, .graded(CricketChaseFigure10868(text: "Lost", detail: Self.settlementDetail)))
        XCTAssertEqual(chase?.visibleState?.runs, .reported(text: "206", value: 206))
        XCTAssertEqual(chase?.visibleState?.target, .reported(text: "421", value: 421))
        XCTAssertEqual(chase?.visibleState?.oversText, "Final overs not reported")

        // The history stops at the final report and gains no 0% or 100% point.
        let anchor = view.historyContent(reader: false)
        let points = anchor.input.series.flatMap(Self.allPoints)
        XCTAssertTrue(points.allSatisfy { $0.x <= Self.finalX })
        XCTAssertTrue(points.allSatisfy { $0.probability > 0 && $0.probability < 1 })
        XCTAssertEqual(anchor.markers?.markers.map(\.id), ["84", "85", "final"])
        XCTAssertEqual(anchor.input.xTicks.map(\.lines), [["Oct 13", "4 AM"], ["4:24 AM", "Final report"]])
        XCTAssertEqual(model.storyCard("expectations"), .expectations)
        XCTAssertEqual(model.storyCard("chase"), .chase)
    }

    @MainActor
    func testReducedHistoryKeepsOmittedSpansAsSeparateRunsAndTheFullSizeHistoryDropsOnlyItsExpand() {
        // At 85 overs: Draw/tie has no 11:06 close, so 11:05 and 11:07 are two runs.
        let live = Self.page(.over85)
        XCTAssertEqual(live.history.series.map { $0.segments.count }, [2, 2, 2])
        XCTAssertEqual(live.history.series[2].segments.map { $0.points.first!.x },
                       [Self.minute(11, 4), Self.minute(11, 7)])
        XCTAssertTrue(live.history.series.allSatisfy { Self.allPoints($0).allSatisfy { $0.x <= Self.report85X } },
                      "the 11:12 closes are later than the 85-over report")
        // At the final: Australia's left-out minutes split a third run; nothing bridges them.
        let final = Self.page(.final)
        XCTAssertEqual(final.history.series.map { $0.segments.count }, [3, 3, 3])
        XCTAssertEqual(final.history.series[1].segments.last?.points.map(\.x), [Self.minute(11, 23), Self.minute(11, 24)])

        for moment in [Moment.before, .over64, .over85, .final] {
            let input = Self.page(moment)
            let model = CricketEventPageModel10868(input)
            let reader = model.readerHistory
            XCTAssertNil(reader.expand)
            XCTAssertEqual(reader.plotHeight, 350)
            XCTAssertEqual(reader.series, input.history.series)
            XCTAssertEqual(reader.domain, input.history.domain)
            XCTAssertEqual(reader.yTicks, input.history.yTicks)
            XCTAssertEqual(reader.xTicks, input.history.xTicks)
            XCTAssertEqual(reader.context, input.history.context)
            XCTAssertEqual(reader.pregameKey, input.history.pregameKey)
            XCTAssertEqual(reader.summary, input.history.summary)
            XCTAssertEqual(reader.window, input.history.window)
            XCTAssertEqual(reader.inspection, input.history.inspection)
            XCTAssertEqual(reader.previous, input.history.previous)
            XCTAssertEqual(reader.next, input.history.next)

            let view = CricketEventPagePresentation10868(input: input, mode: .reader(.history), onHistoryExpand: {})
            let full = view.historyContent(reader: true)
            XCTAssertEqual(full.input, reader)
            XCTAssertEqual(full.markers, view.historyContent(reader: false).markers)
            XCTAssertNil(full.onExpand, "no nested expand inside the reader")
            XCTAssertNotNil(view.historyContent(reader: false).onExpand)
        }
        // Without an owner reader height the reader keeps the page's.
        var plain = Self.page(.over64)
        plain.readerPlotHeight = nil
        XCTAssertEqual(CricketEventPageModel10868(plain).readerHistory.plotHeight, 302)
    }

    @MainActor
    func testALeafFromAnotherPhaseIsNotMountedAndAStoryResolvesOnlyItsOneExactLink() {
        var input = Self.page(.over64, headline: Self.headline(.final))
        input.chase = Self.chase(.final)
        input.shifts = Self.expectations()
        input.historyMarkers = Self.markers(.final)
        let model = CricketEventPageModel10868(input)
        let view = CricketEventPagePresentation10868(input: input)

        XCTAssertNil(model.chase, "a final chase is not coerced into live play")
        XCTAssertNil(model.shifts, "a completed outlook is not the live comparison")
        XCTAssertNil(model.expectations, "the result card is final only")
        XCTAssertNil(view.headlineContent(), "a final headline shows the owner's unavailable words instead")
        XCTAssertNil(view.historyContent(reader: false).markers, "final guides are not drawn live")
        XCTAssertFalse(model.readerShows(.chase))

        // Exactly one link with the id, to a story this phase mounts.
        XCTAssertNil(model.story("shifts"))
        XCTAssertNil(model.story("chase"))
        XCTAssertEqual(model.storyCard("survival"), .survival)
        var links = Self.page(.over64)
        links.stories = [CricketEventPageStory10868(cardID: "chase", card: .chase),
                         CricketEventPageStory10868(cardID: "chase", card: .survival),
                         CricketEventPageStory10868(cardID: "history", card: .history),
                         CricketEventPageStory10868(cardID: "result", card: .expectations)]
        let linked = CricketEventPageModel10868(links)
        XCTAssertNil(linked.story("chase"), "two links for one id name no single story")
        XCTAssertNil(linked.story("history"), "the anchor is never a stream story")
        XCTAssertNil(linked.story("result"), "a story this phase does not mount")
        XCTAssertNil(linked.story("unknown"))

        // A survival card supplied at another phase is not mounted at the final.
        var final = Self.page(.final)
        final.survival = Self.survival(.over85)
        XCTAssertNil(CricketEventPageModel10868(final).survival)
    }

    // MARK: Holds

    /// Only a card the stream actually draws — its primary, or its companion
    /// when wide — carries the stream's interaction intent, so each visible
    /// card's action asks for that hold once before its exact owner callback,
    /// and a card the stream does not draw asks for none. No test taps a card
    /// the stream never drew.
    @MainActor
    func testAStreamCardActionRequestsTheHoldBeforeTheExactOwnerCallbackAndNothingFiresPassively() {
        var log: [String] = []
        func view(_ input: CricketEventPageInput10868) -> CricketEventPagePresentation10868 {
            CricketEventPagePresentation10868(
                input: input,
                onShiftsSelect: { log.append("shifts.select:\($0.market)") },
                onShiftsDetails: { log.append("shifts.details:\($0.market)") },
                onChaseDetails: { log.append("chase.details:\($0.market)") },
                onSurvivalSelect: { log.append("survival.select:\($0.checkpointID)") },
                onSurvivalDetails: { log.append("survival.details:\($0.checkpointID)") },
                onExpectationsSelect: { log.append("expectations.select:\($0.market)") },
                onInteraction: { log.append("page-hook") })
        }
        func hook(_ input: CricketEventPageInput10868, _ id: String) -> StoryStreamCardActivation10868 {
            Self.activation(input.stream!, id) { log.append($0) }
        }
        // Two checkpoints on ONE shared original are two exact targets.
        let selectTarget = CricketSurvivalTarget10868(checkpointID: Self.checkpoints[1].id, original: Self.tieRef)
        let detailsTarget = CricketSurvivalTarget10868(checkpointID: Self.checkpoints[3].id, original: Self.tieRef)

        // Narrow, 64 overs: only the primary, changing expectations, is drawn.
        let narrow64 = Self.page(.over64)
        let narrow64Shifts = view(narrow64).shiftsContent(activation: hook(narrow64, "shifts"))
        XCTAssertTrue(hook(narrow64, "chase").intents.isEmpty, "the next card is not drawn when narrow")
        XCTAssertTrue(hook(narrow64, "survival").intents.isEmpty)
        XCTAssertEqual(log, [], "building cards asks for nothing")
        narrow64Shifts?.onSelect?(Self.outlookRef(1))
        narrow64Shifts?.onDetails?(Self.outlookRef(1))
        XCTAssertEqual(log, [
            "hold:shifts", "shifts.select:constructed.market.AUS",
            "hold:shifts", "shifts.details:constructed.market.AUS",
        ], "the stream's activation once, then the exact owner callback; never the page hook too")

        // Narrow, 85 overs: only the primary, holding on, is drawn.
        log = []
        let narrow85 = Self.page(.over85)
        let narrow85Survival = view(narrow85).survivalContent(activation: hook(narrow85, "survival"))
        XCTAssertTrue(hook(narrow85, "shifts").intents.isEmpty, "the companion is not drawn when narrow")
        XCTAssertTrue(hook(narrow85, "chase").intents.isEmpty)
        XCTAssertEqual(log, [], "building cards asks for nothing")
        narrow85Survival?.onSelect?(selectTarget)
        narrow85Survival?.onDetails?(detailsTarget)
        XCTAssertEqual(log, [
            "hold:survival", "survival.select:\(Self.checkpoints[1].id)",
            "hold:survival", "survival.details:\(Self.checkpoints[3].id)",
        ])

        // Wide, 64 overs: changing expectations and its companion, the chase, are drawn.
        log = []
        let wide64 = Self.page(.over64, wide: true)
        let wide64View = view(wide64)
        let wide64Shifts = wide64View.shiftsContent(activation: hook(wide64, "shifts"))
        let wide64Chase = wide64View.chaseContent(activation: hook(wide64, "chase"))
        XCTAssertTrue(hook(wide64, "survival").intents.isEmpty, "a card neither primary nor companion is not drawn")
        XCTAssertEqual(log, [], "building cards asks for nothing")
        wide64Shifts?.onSelect?(Self.outlookRef(1))
        wide64Shifts?.onDetails?(Self.outlookRef(1))
        wide64Chase?.onDetails?(Self.chaseRef)
        XCTAssertEqual(log, [
            "hold:shifts", "shifts.select:constructed.market.AUS",
            "hold:shifts", "shifts.details:constructed.market.AUS",
            "hold:chase", "chase.details:constructed.market.SA",
        ])

        // Wide, 85 overs: holding on and its companion, changing expectations, are drawn.
        log = []
        let wide85 = Self.page(.over85, wide: true)
        let wide85View = view(wide85)
        let wide85Survival = wide85View.survivalContent(activation: hook(wide85, "survival"))
        let wide85Shifts = wide85View.shiftsContent(activation: hook(wide85, "shifts"))
        XCTAssertTrue(hook(wide85, "chase").intents.isEmpty, "a card neither primary nor companion is not drawn")
        XCTAssertEqual(log, [], "building cards asks for nothing")
        wide85Survival?.onSelect?(selectTarget)
        wide85Survival?.onDetails?(detailsTarget)
        wide85Shifts?.onSelect?(Self.outlookRef(1))
        wide85Shifts?.onDetails?(Self.outlookRef(1))
        XCTAssertEqual(log, [
            "hold:survival", "survival.select:\(Self.checkpoints[1].id)",
            "hold:survival", "survival.details:\(Self.checkpoints[3].id)",
            "hold:shifts", "shifts.select:constructed.market.AUS",
            "hold:shifts", "shifts.details:constructed.market.AUS",
        ])

        // Full-size content: the exact callbacks, no hold.
        log = []
        let reader = view(narrow85)
        reader.chaseContent()?.onDetails?(Self.chaseRef)
        reader.survivalContent()?.onSelect?(CricketSurvivalTarget10868(checkpointID: Self.checkpoints[0].id, original: Self.tieRef))
        XCTAssertEqual(log, ["chase.details:constructed.market.SA", "survival.select:\(Self.checkpoints[0].id)"])

        // At the final the expectations card relays the same way; no owner callback means no action.
        log = []
        let final = Self.page(.final)
        let finalView = CricketEventPagePresentation10868(input: final, onExpectationsSelect: { log.append("expectations.select:\($0.market)") })
        finalView.expectationsContent(activation: Self.activation(final.stream!, "expectations") { log.append($0) })?.onSelect?(Self.outlookRef(1))
        XCTAssertNil(finalView.expectationsContent()?.onDetails)
        XCTAssertNil(finalView.chaseContent()?.onDetails)
        XCTAssertEqual(log, ["hold:expectations", "expectations.select:constructed.market.AUS"])
    }

    @MainActor
    func testThePageHookHoldsOnceBeforeEachPageActionAndNeverForReadersStreamCardsOrPassiveReads() {
        var log: [String] = []
        let input = Self.page(.over64)
        func hooked(_ mode: CricketEventPageMode10868 = .page, hook: Bool = true) -> CricketEventPagePresentation10868 {
            CricketEventPagePresentation10868(
                input: input, mode: mode, originals: Self.originals(.over64),
                onAbout: { log.append("about") },
                onSourceInfo: { log.append("sources:\($0.subjects.count)") },
                onAllProps: { log.append("allProps") },
                onOriginalSelect: { log.append("original:\($0.identity.market)") },
                onStoryIntent: { _ in log.append("stream") },
                onHistoryPrevious: { log.append("previous") },
                onHistoryNext: { log.append("next") },
                onHistoryExpand: { log.append("expand") },
                onHistoryWindowChoice: { log.append("window:\($0)") },
                onHistoryPlotPosition: { log.append("plot:\(Int($0))") },
                onChaseDetails: { log.append("chase:\($0.market)") },
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        // Building and reading every leaf calls neither the hook nor an owner.
        let view = hooked()
        let headline = view.headlineContent()
        let anchor = view.historyContent(reader: false)
        let chooser = view.chooserContent()
        let catalogue = view.catalogueContent()
        _ = view.historyContent(reader: true)
        _ = view.aboutContent()
        _ = view.originalDetailsContent()
        XCTAssertEqual(log, [])

        // On the page: the hook once, then the exact owner callback with its exact value.
        view.openTitleAbout()
        headline?.openSourceInfo()
        anchor.onPrevious?()
        anchor.onNext?()
        anchor.onExpand?()
        anchor.onWindowChoice?("match")
        anchor.onPlotPosition?(Self.minute(9, 8))
        chooser?.onSelect?(Self.selection(2))
        view.openAllProps()
        catalogue?.onSelect?(Self.selection(0))
        XCTAssertEqual(log, ["hold", "about", "hold", "sources:3", "hold", "previous", "hold", "next", "hold", "expand",
                             "hold", "window:match", "hold", "plot:\(Int(Self.minute(9, 8)))",
                             "hold", "original:\(Self.event)-TIE", "hold", "allProps", "hold", "original:\(Self.event)-SA"])

        // Full-size content keeps the exact callbacks: its host already holds.
        log = []
        let reader = hooked(.reader(.history))
        reader.historyContent(reader: true).onPrevious?()
        reader.historyContent(reader: true).onWindowChoice?("day5")
        reader.openReaderAbout()
        hooked(.reader(.chase)).chaseContent()?.onDetails?(Self.chaseRef)
        XCTAssertEqual(log, ["previous", "window:day5", "about", "chase:constructed.market.SA"])

        // No owner callback: no action and no hook call.
        log = []
        let silent = CricketEventPagePresentation10868(input: input, originals: Self.originals(.over64), onInteraction: { log.append("hold") })
        XCTAssertNil(silent.headlineContent()?.onSourceInfo)
        XCTAssertNil(silent.historyContent(reader: false).onPrevious)
        XCTAssertNil(silent.historyContent(reader: false).onNext)
        XCTAssertNil(silent.historyContent(reader: false).onExpand)
        XCTAssertNil(silent.historyContent(reader: false).onWindowChoice)
        XCTAssertNil(silent.historyContent(reader: false).onPlotPosition)
        XCTAssertNil(silent.chooserContent()?.onSelect)
        XCTAssertNil(silent.catalogueContent()?.onSelect)
        silent.openTitleAbout()
        silent.openAllProps()
        silent.headlineContent()?.openSourceInfo()
        XCTAssertEqual(log, [])

        // No hook: each page callback is the owner's own, exactly as before.
        let plain = hooked(hook: false)
        plain.historyContent(reader: false).onExpand?()
        plain.chooserContent()?.onSelect?(Self.selection(1))
        plain.openAllProps()
        XCTAssertEqual(log, ["expand", "original:\(Self.event)-AUS", "allProps"])
    }

    // MARK: Sources, About and originals

    @MainActor
    func testTheSourcesAndAboutOpenTheirOwnContentWithTheHeadlinesExactPayload() {
        for moment in [Moment.before, .over64, .final] {
            var received: CricketHeadlineSourceInfo10868?
            let input = Self.page(moment)
            let view = CricketEventPagePresentation10868(input: input, onSourceInfo: { received = $0 })
            let headline = view.headlineContent()
            XCTAssertEqual(headline?.secondaryProvenance, true)
            headline?.openSourceInfo()
            XCTAssertEqual(received, input.headline.sourceInfo, "the headline's own payload, unchanged")
            if let received {
                let content = CricketEventPagePresentation10868(input: input, mode: .sourceInfo(received)).sourceInfoContent(received)
                XCTAssertEqual(content.info, received)
            }
            // Connected + secondary: provenance moves to the disclosure.
            XCTAssertEqual(input.headline.provenancePresentation(secondary: true, connected: true),
                           CricketHeadlineProvenancePresentation10868(offersInfo: true, inline: false))
        }
        // Unconnected: no control, and the headline keeps every provenance line inline.
        let input = Self.page(.over64)
        let unconnected = CricketEventPagePresentation10868(input: input)
        XCTAssertNil(unconnected.headlineContent()?.onSourceInfo)
        XCTAssertEqual(input.headline.provenancePresentation(secondary: true, connected: false).inline, true)
        // A later reading is never in the before payload; a contract grade never in the final one.
        XCTAssertEqual(Self.page(.before).headline.sourceInfo.subjects.flatMap { $0.entries.map(\.slot) },
                       Array(repeating: .pregame, count: 3))
        XCTAssertFalse(Self.page(.final).headline.sourceInfo.subjects.flatMap { $0.entries.map(\.text) }.contains("Won"))

        // The About opens only with readable words and a callback; full-size
        // content's compact heading offers it, the page uses the title's control.
        let model = CricketEventPageModel10868(input)
        XCTAssertEqual(model.about, Self.about)
        XCTAssertTrue(model.aboutAvailable(canOpen: true))
        XCTAssertFalse(model.aboutAvailable(canOpen: false))
        XCTAssertTrue(model.aboutEntry(mode: .reader(.chase), canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .page, canOpen: true))
        XCTAssertEqual(CricketEventPagePresentation10868(input: input).aboutContent()?.about, Self.about)
        var blank = input
        blank.about = CricketEventPageAbout10868(title: "  ", paragraphs: ["", "\n"])
        XCTAssertNil(CricketEventPageModel10868(blank).about)
        XCTAssertFalse(CricketEventPageModel10868(blank).aboutAvailable(canOpen: true))
        var called = false
        CricketEventPagePresentation10868(input: blank, onAbout: { called = true }).openTitleAbout()
        XCTAssertFalse(called)
    }

    @MainActor
    func testTheOriginalsChooserCatalogueAndDetailsMountTheExistingLeavesWithEachOriginalsOwnResult() {
        for moment in [Moment.before, .over64, .final] {
            let originals = Self.originals(moment)
            let view = CricketEventPagePresentation10868(input: Self.page(moment), originals: originals)

            let chooser = view.chooserContent()
            XCTAssertEqual(chooser?.catalogue, originals.catalogue)
            XCTAssertEqual(chooser?.selection, originals.selection)
            XCTAssertEqual(chooser?.heading, "All 3 original markets")
            let choices = OriginalMarketChooser9483.choices(catalogue: originals.catalogue, selection: originals.selection,
                                                            labels: originals.labels, unavailableChoice: originals.unavailableChoice)
            XCTAssertEqual(choices.map(\.label), Self.titles, "all three originals, in the owner's order")
            XCTAssertEqual(choices.map(\.isSelected), [false, true, false])

            let catalogue = view.catalogueContent()
            XCTAssertEqual(catalogue?.catalogue, originals.catalogue)
            XCTAssertEqual(catalogue?.context, "3 retained originals")
            let details = view.originalDetailsContent()
            XCTAssertEqual(details?.selection, originals.selection)
            XCTAssertNil(details?.recorded, "without an owner context the Details stay summary-only")
            XCTAssertNil(details?.onHistory)

            // Each original's own readings and, at the final only, its own contract result.
            for index in 0..<3 {
                let content = OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: Self.selection(index))
                XCTAssertEqual(content?.readings.first?.text, Self.pregameTexts[index])
                XCTAssertEqual(content?.rules, .verified([Self.rules[index]]))
                switch moment {
                case .before:
                    XCTAssertEqual(content?.readings.count, 1)
                    XCTAssertNil(content?.result)
                case .over64, .over85:
                    XCTAssertEqual(content?.readings.map(\.text), [Self.pregameTexts[index], Self.recorded(.over64)![index].1])
                    XCTAssertNil(content?.result, "no contract result while live")
                case .final:
                    XCTAssertEqual(content?.result?.words, Self.gradeWords[index])
                    XCTAssertEqual(content?.result?.provenance, Self.settlementDetail)
                }
            }
        }
        // Missing original metadata stays honest: the original stays listed,
        // unavailable, and never borrows a neighbour's or the match's words.
        let broken = Self.originals(.final, selected: 2, blankTitleAt: 2)
        let choices = OriginalMarketChooser9483.choices(catalogue: broken.catalogue, selection: broken.selection,
                                                        labels: broken.labels, unavailableChoice: broken.unavailableChoice)
        XCTAssertEqual(choices.count, 3)
        XCTAssertNil(choices[2].selection)
        XCTAssertFalse(choices[2].isSelected)
        XCTAssertEqual(choices[2].label, "Original unavailable")
        XCTAssertNil(OriginalMarketDetails9483.content(catalogue: broken.catalogue, selection: broken.selection))
        // No originals and no All props label: no panel content and no entry.
        let bare = Self.page(.over64, copy: CricketEventPageCopy10868(
            storiesLabel: "Match stories", storyUnavailable: "x", headlineUnavailable: "y",
            aboutLabel: "About this match", allPropsLabel: nil))
        let empty = CricketEventPagePresentation10868(input: bare, onAllProps: {})
        XCTAssertNil(empty.chooserContent())
        XCTAssertFalse(CricketEventPageModel10868(bare).allPropsAvailable(canOpen: true))
    }

    // MARK: Details recorded history

    private static let exploreID = "constructed.original.history.explore"

    /// CONSTRUCTED contract input, never history evidence: an owner context
    /// for Australia's held original at 64 overs. It has no points and an
    /// explicit plot absence, so no recorded closes are drawn or duplicated,
    /// and it offers only Explore. Its two readings reuse this fixture's own
    /// Australia pregame and 64-over words.
    private static func recordedContext() -> OriginalMarketDetails9483.RecordedHistory {
        let seriesID = "constructed.history.AUS"
        let later = recorded(.over64)![1]
        var history = FieldHistoryInput10868(
            title: "Recorded chance", caption: nil,
            series: [FieldHistorySeries10868(
                id: seriesID, name: titles[1], shape: .diamond, tint: .orange, runs: [], links: [], labelPointID: nil,
                before: .absent(words: "Unavailable"), recorded: .absent(words: "Unavailable"), absentWords: nil, choose: nil)],
            selection: .series(id: seriesID, missingWords: "This original isn’t in this history"),
            domain: FieldHistoryDomain10868(lower: minute(9, 0), upper: report64X), ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: [FieldHistoryTick10868(value: minute(9, 0), lines: xTickLines(.over64)[0]),
                     FieldHistoryTick10868(value: report64X, lines: xTickLines(.over64)[1])],
            guides: [], breaks: [], readout: .singleBefore(label: "Pregame"),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow: pregame", filled: "Filled: recorded"),
            comparisonExplanation: nil, notes: [], summary: "Australia wins: no recorded closes in this context.",
            plotHeight: 132, unboundReadingWords: "Unavailable", plotUnavailableWords: "Original history unavailable",
            windows: nil, scale: nil, moreOriginals: nil, details: nil, expand: nil, inspect: nil,
            previous: nil, next: nil, inspection: nil, layout: .expanded)
        history.showsKey = false
        history.plotAbsence = FieldHistoryPlotAbsence10868(title: "Recorded history not drawn", words: nil)
        return OriginalMarketDetails9483.RecordedHistory(
            selection: selection(1), mode: .comparison(.recorded), seriesID: seriesID,
            availability: "Recorded chances below · not a current chance",
            readings: [OriginalMarketDetails9483.RecordedReading(
                           label: "Pregame chance", marker: .hollow,
                           reading: .value(pregameTexts[1], placement: nil, provenance: pregameDetail)),
                       OriginalMarketDetails9483.RecordedReading(
                           label: "Recorded chance", marker: .solid,
                           reading: .value(later.1, placement: nil, provenance: later.2))],
            movement: nil, history: history, finishLabel: "Reported finish", finish: nil,
            preview: nil, expand: nil,
            explore: FieldHistoryAction10868(id: exploreID, label: "Explore history", spokenLabel: nil, isAvailable: true),
            unmatchedWords: "Recorded history unavailable for this original")
    }

    @MainActor
    func testDetailsForwardTheOwnersOptionalRecordedHistoryAndHoldOnceBeforeItsExactHistoryIntent() {
        var log: [String] = []
        var received: [OriginalMarketDetails9483.HistoryIntent] = []
        let context = Self.recordedContext()
        let originals = Self.originals(.over64, recorded: context)
        func view(hook: Bool = true, callback: Bool = true,
                  group: CricketEventPageOriginals10868? = nil) -> CricketEventPagePresentation10868 {
            CricketEventPagePresentation10868(
                input: Self.page(.over64), mode: .original, originals: group ?? originals,
                onOriginalHistory: callback ? { received.append($0); log.append("history:\($0.actionID)") } : nil,
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        // Building and reading the Details hands the leaf the owner's exact
        // context, catalogue and held selection, and calls nothing.
        let details = view().originalDetailsContent()!
        XCTAssertEqual(details.recorded, context)
        XCTAssertEqual(details.catalogue, originals.catalogue)
        XCTAssertEqual(details.selection, originals.selection)
        XCTAssertEqual(log, [])

        // The leaf's own Explore intent: the hook once, then the exact intent.
        guard case .recorded(let shown)? = OriginalMarketDetails9483.recorded(
                  catalogue: details.catalogue, selection: details.selection, context: details.recorded,
                  hasCallback: details.onHistory != nil),
              let intent = OriginalMarketDetails9483.intent(.explore, in: shown)
        else { return XCTFail("the constructed context resolves for the held original") }
        XCTAssertFalse(shown.showsPlot, "a constructed context draws no recorded closes")
        XCTAssertEqual(intent, OriginalMarketDetails9483.HistoryIntent(selection: Self.selection(1), entry: .explore,
                                                                       actionID: Self.exploreID))
        details.onHistory?(intent)
        XCTAssertEqual(log, ["hold", "history:\(Self.exploreID)"])
        XCTAssertEqual(received, [intent])

        // No hook: the owner's exact callback alone.
        log = []
        received = []
        view(hook: false).originalDetailsContent()?.onHistory?(intent)
        XCTAssertEqual(log, ["history:\(Self.exploreID)"])
        XCTAssertEqual(received, [intent])

        // No callback: the context still reaches the leaf, there is no
        // history action, and nothing holds.
        log = []
        let quiet = view(callback: false).originalDetailsContent()!
        XCTAssertEqual(quiet.recorded, context)
        XCTAssertNil(quiet.onHistory)
        XCTAssertEqual(log, [])

        // Default: no context, the existing summary-only Details. The page's
        // inline chooser is the same with or without a context.
        XCTAssertNil(view(group: Self.originals(.over64)).originalDetailsContent()?.recorded)
        let page = CricketEventPagePresentation10868(input: Self.page(.over64), originals: originals)
        XCTAssertEqual(page.chooserContent()?.catalogue, originals.catalogue)
        XCTAssertEqual(page.chooserContent()?.selection, originals.selection)
        XCTAssertEqual(log, [])
    }

    // MARK: Arrangement

    @MainActor
    func testCompactWideAndAccessibilitySizesChooseTheirArrangements() {
        XCTAssertEqual(CricketEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(CricketEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(CricketEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(CricketEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertEqual(CricketEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: true), [.stacked])

        // Every name survives whole in the inputs the leaves measure, the
        // headline and history agree on each original's shape and order, and
        // the page keeps the owner's plot height unchanged.
        let input = Self.page(.over64, wide: true)
        XCTAssertEqual(input.headline.rows.map(\.subject), Self.subjects)
        XCTAssertEqual(input.headline.rows.map(\.shape), [.circle, .diamond, .square])
        XCTAssertEqual(input.history.series.map(\.shape), [.circle, .diamond, .square])
        XCTAssertEqual(input.headline.cellsPerRow, 3)
        XCTAssertEqual(input.history.plotHeight, 302)
        XCTAssertEqual(input.stream?.wide, true)
        XCTAssertEqual(CricketEventPagePresentation10868(input: input).historyContent(reader: false).input.plotHeight, 302)
    }
}

// MARK: - The cricket-t20 composition

/// #10868 — the `cricket-t20` composition of the same shared cricket page
/// (`format: .t20`). A separate route outcome: nothing here is Test-match
/// evidence, and no app EventDetail id is joined to the India–West Indies
/// report evidence by name or date.
///
/// PREPARED / NOT RUN. Composition only: which actual leaf Views the page
/// mounts in each phase for the T20 format, that each receives the owner's
/// input unchanged, that the default Test format's offer is untouched by
/// supplied T20 inputs, the stream and full-size parity, the activation and
/// interaction holds and the exact callbacks. Each leaf's own rules stay with
/// its own tests; nothing here claims a rendered fit, a native runtime,
/// VoiceOver behaviour, a production binding or route readiness.
///
/// ARCHIVED raw values, from the retained-case receipts in
/// shipping-adoption-20261027 (T20-BEFORE-STORY-, T20-CHASE-REUSE-,
/// T20-SHIFT-REUSE- and T20-HISTORY-MARKERS-RETAINED-CASES.json): India v
/// West Indies, second T20I at Ranchi, Kalshi event
/// KXT20MATCH-26OCT090930WIIND —
/// - two independently traded winner markets (-IND, -WI); each one's last
///   minute close ending 12:57:00Z, before the 12:57:17Z pre-match report:
///   India 0.78, West Indies 0.23 — sum 1.01, never normalized, and no draw
///   row (a tie or no result settles at $0.50, a settlement amount);
/// - India 249/5 after 20 overs (report published 15:24:19Z), target 250;
/// - four West Indies chase reports (publication clocks, never ball times),
///   each market's own minute close at or before it: 13.0 overs 170/3 at
///   16:46:44Z (IND 0.44, WI 0.57; bar 16:46), 15.0 overs 187/4 at 16:57:47Z
///   (IND 0.67, WI 0.34; bar 16:57), 17.0 overs 223/4 at 17:06:58Z (IND 0.12,
///   WI 0.89; bar 17:06), 18.0 overs 240/4 at 17:12:01Z (IND 0.01, WI 0.99;
///   bar 17:12);
/// - the final report at 17:19:41Z: West Indies 252/4 at 18.3 overs, won by
///   6 wickets; the closes then (IND 0.01, WI 0.99; bar 17:19) — never a 0/100
///   point; each contract's own result (IND no, WI yes), settled 17:45:23Z,
///   later than and separate from the match result.
///
/// CONSTRUCTED (owner inputs, not retained facts): every label, figure text,
/// PDT provenance line, caption, state word, the ball and rate words and
/// values (15.0 overs is 90 legal balls and 18.3 is 111 only because the
/// owner says so), the rate ceiling, the stream metadata and card ids, the
/// history domain, tick words, one-point runs and marker geometry (epoch
/// seconds already resolved), About text, tints, catalogue identities and
/// every `constructed.*` reference — no production original or app id is
/// retained, and no public ticker is used as an action identity.
final class CricketEventPageT20Composition10868Tests: XCTestCase {

    // MARK: Retained facts

    private enum Frame { case before, over15, final }

    private static let sides = ["IND", "WI"]
    private static let subjects = ["India", "West Indies"]
    private static let tickers = ["KXT20MATCH-26OCT090930WIIND-IND", "KXT20MATCH-26OCT090930WIIND-WI"]
    private static let titles = ["India wins", "West Indies wins"]
    private static let rules = [
        "If India wins the India vs West Indies men's professional West Indies Tour of India T20s cricket match originally scheduled for Oct 9, 2026 at 9:30 AM EDT, then the market resolves to Yes.",
        "If West Indies wins the India vs West Indies men's professional West Indies Tour of India T20s cricket match originally scheduled for Oct 9, 2026 at 9:30 AM EDT, then the market resolves to Yes.",
    ]
    /// The first sentence of the retained secondary rule, shared by both.
    private static let tieRule = "If the India vs West Indies men's professional West Indies Tour of India T20s cricket match originally scheduled for Oct 9, 2026 at 9:30 AM EDT ends in a tie, draw, no result (NR), abandonment, or cancellation, and no official winner is declared, all markets will resolve to $0.50."
    private static let pregameValues = [0.78, 0.23]
    private static let pregameTexts = ["78%", "23%"]
    /// Each market's own close at the 15.0-over report.
    private static let recordedValues = [0.67, 0.34]
    private static let recordedTexts = ["67%", "34%"]

    /// Seconds since 1970 (the history's own domain unit).
    private static let domainLower: Double = 1_791_547_200    // 12:00:00Z
    private static let pregameBar: Double = 1_791_550_620     // 12:57:00Z
    private static let inningsReport: Double = 1_791_559_459  // 15:24:19Z
    private static let report13: Double = 1_791_564_404       // 16:46:44Z
    private static let report15: Double = 1_791_565_067       // 16:57:47Z
    private static let report17: Double = 1_791_565_618       // 17:06:58Z
    private static let report18: Double = 1_791_565_921       // 17:12:01Z
    private static let domainUpper: Double = 1_791_567_000    // 17:30:00Z

    /// Each market's own retained minute closes: bar end, then India and West Indies.
    private static let closes: [(x: Double, values: [Double])] = [
        (1_791_550_620, [0.78, 0.23]),   // 12:57, pregame
        (1_791_564_360, [0.44, 0.57]),   // 16:46
        (1_791_565_020, [0.67, 0.34]),   // 16:57
        (1_791_565_560, [0.12, 0.89]),   // 17:06
        (1_791_565_920, [0.01, 0.99]),   // 17:12
        (1_791_566_340, [0.01, 0.99]),   // 17:19
    ]

    private static func phase(_ frame: Frame) -> CricketHeadlinePhase10868 {
        switch frame {
        case .before: .before
        case .over15: .during
        case .final: .completed
        }
    }

    private static func chasePhase(_ frame: Frame) -> CricketChasePhase10868 {
        switch frame {
        case .before: .before
        case .over15: .during
        case .final: .final
        }
    }

    // MARK: Constructed owner words

    private static let tints: [Color] = [.blue, .orange]
    private static let outlookShapes: [CricketOutlookShape10868] = [.circle, .diamond]
    private static let historyShapes: [CricketHistoryShape10868] = [.circle, .diamond]
    private static let pregameDetail = "Kalshi trade close · minute 5:56–5:57 AM PDT, October 9, 2026"
    private static let recordedDetail = "Kalshi trade close · minute 9:56–9:57 AM PDT, October 9, 2026"
    private static let report15Detail = "Score report published 9:57:47 AM PDT, October 9, 2026 · not the exact ball time"
    private static let finalDetail = "Final score report published 10:19:41 AM PDT, October 9, 2026 · not the exact time of the last ball"
    private static let settlementDetail = "Contract finalized 10:45:23 AM PDT, October 9, 2026 · not the match finish time"
    private static let outcomeWords = ["Lost", "Winner"]
    private static let gradeWords = ["Lost", "Won"]
    private static let movements = [
        CricketOutlookMovement10868(text: "↓ 11 points", spoken: "Down 11 percentage points from pregame"),
        CricketOutlookMovement10868(text: "↑ 11 points", spoken: "Up 11 percentage points from pregame"),
    ]

    private static func outlookRef(_ index: Int) -> CricketOutlookRef10868 {
        CricketOutlookRef10868(event: "constructed.event.wiind", market: "constructed.market.\(sides[index])", outcome: "constructed.yes")
    }

    private static let chaseRef = CricketChaseRef10868(event: "constructed.event.wiind", market: "constructed.market.WI", outcome: "constructed.yes")

    /// One original's row. Its later reading and finish are supplied in EVERY
    /// frame, so phase gating, not their absence, keeps them off a foreign phase.
    private static func row(_ index: Int, before: CricketOutlookReading10868? = nil,
                            comparison: CricketOutlookReading10868? = nil) -> CricketOutlookRow10868 {
        CricketOutlookRow10868(
            id: sides[index], subject: subjects[index], shape: outlookShapes[index], tint: tints[index],
            ref: outlookRef(index),
            before: before ?? .observed(CricketOutlookObservation10868(probability: pregameValues[index], text: pregameTexts[index],
                                                                       detail: pregameDetail)),
            comparison: comparison ?? .observed(CricketOutlookObservation10868(probability: recordedValues[index],
                                                                               text: recordedTexts[index], detail: recordedDetail)),
            movement: movements[index],
            finish: CricketOutlookFinish10868(
                outcome: .admitted(CricketOutlookFinalWord10868(text: outcomeWords[index], symbolName: nil, detail: finalDetail)),
                grade: .admitted(CricketOutlookFinalWord10868(text: gradeWords[index], symbolName: nil, detail: settlementDetail))
            )
        )
    }

    private static func rows() -> [CricketOutlookRow10868] { [row(0), row(1)] }

    private static func headlineState(_ frame: Frame) -> CricketHeadlineState10868 {
        switch frame {
        case .final:
            return .reported(CricketHeadlineStateFrame10868(
                entries: [CricketHeadlineStateEntry10868(label: "West Indies", text: "252/4", spoken: "252 for 4"),
                          CricketHeadlineStateEntry10868(label: nil, text: "West Indies won by 6 wickets",
                                                         spoken: "West Indies won by 6 wickets")],
                detail: finalDetail))
        case .before, .over15:
            // Supplied before play too; the headline shows it only during and after.
            return .reported(CricketHeadlineStateFrame10868(
                entries: [CricketHeadlineStateEntry10868(label: "West Indies · batting", text: "187/4", spoken: "187 for 4"),
                          CricketHeadlineStateEntry10868(label: "15 overs", text: "Target 250", spoken: "Target 250 runs")],
                detail: report15Detail))
        }
    }

    private static func headline(_ frame: Frame, rows: [CricketOutlookRow10868]? = nil) -> CricketHeadlineInput10868 {
        let caption: String = switch frame {
        case .before: "Pregame chances"
        case .over15: "Recorded win chances"
        case .final: "Final · West Indies won by 6 wickets"
        }
        return CricketHeadlineInput10868(
            phase: phase(frame), caption: caption, beforeLabel: "Pregame", comparisonLabel: "Recorded",
            outcomeLabel: "Match", outcomeMissing: "Not reported", rows: rows ?? Self.rows(), state: headlineState(frame))
    }

    private static let pregameLabel = "Pregame chance to win"
    private static let pregameNote = "Two independently traded winner markets. No chase target or projected final is known in this retained pre-match frame."

    private static func pregame(phase: CricketHeadlinePhase10868 = .before,
                                rows: [CricketOutlookRow10868]? = nil) -> CricketPregameStoryInput10868 {
        CricketPregameStoryInput10868(phase: phase, eyebrow: "Before the first ball", title: "India starts as favorite",
                                      beforeLabel: pregameLabel, rows: rows ?? Self.rows(), notes: [pregameNote])
    }

    // MARK: The chase and its limited-over context

    private static let wiPregame = CricketChaseReading10868.observed(CricketChaseFigure10868(text: "23%", detail: pregameDetail))
    private static let wiAt15 = CricketChaseReading10868.observed(CricketChaseFigure10868(text: "34%", detail: recordedDetail))
    private static let wiMatchResult = CricketChaseMatchResult10868.reported(
        CricketChaseFigure10868(text: "West Indies won by 6 wickets", detail: finalDetail))
    private static let wiGrade = CricketChaseContractResult10868.graded(CricketChaseFigure10868(text: "Won", detail: settlementDetail))

    private static func wickets(lost: Int) -> [CricketChaseWicket10868] {
        Array(repeating: .lost, count: lost) + Array(repeating: .remaining, count: 10 - lost)
    }

    private static func chase(_ frame: Frame) -> CricketChaseInput10868 {
        switch frame {
        case .final:
            return CricketChaseInput10868(
                phase: .final, subject: "West Indies", eyebrow: "West Indies · chasing 250", headline: nil,
                pregameLabel: "Pregame win chance", pregame: wiPregame, comparisonLabel: "Recorded win chance",
                comparison: .withheld("Settled — not a chance"), resultLabel: "Original result",
                contractResult: wiGrade, matchResult: wiMatchResult,
                actual: .reported(CricketChaseState10868(
                    battingSubject: "West Indies", context: "The chase, completed", runs: .reported(text: "252", value: 252),
                    runsCaption: "runs scored", target: .reported(text: "250", value: 250), targetCaption: "target",
                    wickets: wickets(lost: 4), wicketsText: "6 wickets left", oversText: "18.3 overs played",
                    reportDetail: finalDetail)),
                detailsRef: chaseRef, notes: ["Rates describe the score; they are not predictions."])
        case .before, .over15:
            // Supplied before play too, as a during-play chase; never mounted then.
            return CricketChaseInput10868(
                phase: .during, subject: "West Indies", eyebrow: "West Indies · chasing 250",
                headline: "63 runs needed", pregameLabel: "Pregame win chance", pregame: wiPregame,
                comparisonLabel: "Recorded win chance", comparison: wiAt15,
                resultLabel: "Original result", contractResult: .unavailable("Not yet confirmed"),
                matchResult: .unavailable("Not yet reported"),
                actual: .reported(CricketChaseState10868(
                    battingSubject: "West Indies", context: "Chase · 15 overs", runs: .reported(text: "187", value: 187),
                    runsCaption: "runs scored", target: .reported(text: "250", value: 250), targetCaption: "target",
                    wickets: wickets(lost: 4), wicketsText: "6 wickets left", oversText: "15.0 overs played",
                    reportDetail: report15Detail)),
                detailsRef: chaseRef, notes: ["Rates describe the score; they are not predictions."])
        }
    }

    private static func task(_ label: String, lead: (String, String), connective: String,
                             trail: (String, String)) -> CricketChaseTask10868 {
        CricketChaseTask10868(label: label, reading: .reported(
            lead: .reported(text: lead.0, caption: lead.1), connective: connective,
            trail: .reported(text: trail.0, caption: trail.1), detail: nil))
    }

    private static let liveTask = task("Chase · 15 overs", lead: ("63", "runs needed"), connective: "from", trail: ("30", "balls left"))
    private static let finishPair = task("The chase, completed", lead: ("252", "runs scored"), connective: "with",
                                         trail: ("9", "balls to spare"))

    private static func balls(_ used: Int) -> CricketChaseBalls10868 {
        CricketChaseBalls10868(label: "Legal balls used",
                               reading: .reported(text: "\(used) of 120", used: Double(used), limit: 120, detail: nil),
                               notDrawn: "Ball progress not drawn")
    }

    private static func rates(achieved: (String, Double), required: (String, Double)?) -> CricketChaseRates10868 {
        CricketChaseRates10868(
            ceiling: 16, scaleText: "Both bars share one scale, 0 to 16 runs per over",
            achieved: CricketChaseRateRow10868(label: "Runs per over so far",
                                               reading: .reported(text: achieved.0, value: achieved.1, detail: nil)),
            required: required.map {
                CricketChaseRateRow10868(label: "Needed from here, runs per over", reading: .reported(text: $0.0, value: $0.1, detail: nil))
            },
            notDrawn: "Rate not drawn")
    }

    private static let liveContext = CricketChaseLimitedOvers10868(
        task: liveTask, finish: nil, balls: balls(90), rates: rates(achieved: ("12.47", 12.47), required: ("12.60", 12.60)))
    private static let finalContext = CricketChaseLimitedOvers10868(
        task: nil, finish: finishPair, balls: balls(111), rates: rates(achieved: ("13.62", 13.62), required: nil))
    /// Every phase's facts at once, for the before-play and wrong-phase cases.
    private static let everythingContext = CricketChaseLimitedOvers10868(
        task: liveTask, finish: finishPair, balls: balls(111), rates: rates(achieved: ("13.62", 13.62), required: ("12.60", 12.60)))

    // MARK: The expectation shift

    /// The four retained checkpoints, each with its own report clock and its
    /// own West Indies minute close.
    private static let checkpointRows: [CricketChaseShiftRow10868] = [
        ("constructed:checkpoint:13.0", "13.0 overs", "170/3", "9:46:44", 0.57, "57%", "9:45–9:46"),
        ("constructed:checkpoint:15.0", "15.0 overs", "187/4", "9:57:47", 0.34, "34%", "9:56–9:57"),
        ("constructed:checkpoint:17.0", "17.0 overs", "223/4", "10:06:58", 0.89, "89%", "10:05–10:06"),
        ("constructed:checkpoint:18.0", "18.0 overs", "240/4", "10:12:01", 0.99, "99%", "10:11–10:12"),
    ].map { id, label, score, reported, value, text, bar in
        CricketChaseShiftRow10868(
            id: id, label: label,
            score: .reported(CricketChaseFigure10868(
                text: score, detail: "Score report published \(reported) AM PDT, October 9, 2026 · not the exact ball time")),
            recorded: .observed(CricketChaseFigure10868(text: text, detail: "Kalshi trade close · minute \(bar) AM PDT, October 9, 2026")),
            position: value)
    }

    private static let checkpointIDs = checkpointRows.map(\.id)

    /// Before play the four rows are supplied for the leak case; in play only
    /// the 13.0 and 15.0 rows; at the final all four, and no finish row.
    private static func shift(_ frame: Frame, pregame: CricketChaseReading10868? = nil, pregamePosition: Double? = 0.23,
                              rows: [CricketChaseShiftRow10868]? = nil) -> CricketChaseShiftInput10868 {
        let final = frame == .final
        return CricketChaseShiftInput10868(
            phase: chasePhase(frame), subject: "West Indies", eyebrow: "West Indies · expectation shift",
            title: final ? "From outsider to winner" : "How the chase changed",
            pregameLabel: "Pregame", pregame: pregame ?? wiPregame, pregamePosition: pregamePosition,
            comparisonLabel: "Recorded win chance",
            // The final's settled 99% is supplied; the card must not show it as a chance.
            comparison: final
                ? .observed(CricketChaseFigure10868(text: "99%", detail: "Kalshi trade close · minute 10:18–10:19 AM PDT, October 9, 2026"))
                : wiAt15,
            resultLabel: "Actual result", matchResult: final ? wiMatchResult : .unavailable("Not yet reported"),
            originalResultLabel: "Original result", originalResult: final ? wiGrade : nil,
            recordedLabel: "Last trade before report",
            checkpointsLabel: "West Indies recorded win chances versus pregame at each captured score report, on a shared zero to 100 percent scale",
            scale: CricketChaseShiftScale10868(label: "Win chance", ticks: [
                CricketChaseShiftTick10868(value: 0, words: "0%"), CricketChaseShiftTick10868(value: 0.5, words: "50%"),
                CricketChaseShiftTick10868(value: 1, words: "100%"),
            ]),
            rows: rows ?? (frame == .over15 ? Array(checkpointRows.prefix(2)) : checkpointRows),
            baselineNotDrawn: "Pregame mark not drawn", rowNotDrawn: "Recorded mark not drawn",
            detailsRef: chaseRef, notes: ["Historical probabilities paired with separately timed score reports."])
    }

    // MARK: History and guides

    private static func closeCount(_ frame: Frame) -> Int {
        switch frame {
        case .before: 1
        case .over15: 3
        case .final: 6
        }
    }

    private static func upper(_ frame: Frame) -> Double {
        switch frame {
        case .before: pregameBar
        case .over15: report15
        case .final: domainUpper
        }
    }

    /// Each retained close is its own one-point run: these sparse closes are
    /// never joined into a synthetic trace.
    private static func history(_ frame: Frame) -> CricketHistoryInput10868 {
        let shown = closes.prefix(closeCount(frame))
        let span = CricketHistoryDomain10868(lower: domainLower, upper: upper(frame))
        let series = (0..<2).map { index in
            CricketHistorySeries10868(
                id: sides[index], name: subjects[index], shape: historyShapes[index], tint: tints[index],
                segments: shown.map { close in
                    CricketHistorySegment10868(id: "\(sides[index]).\(Int(close.x))", points: [
                        CricketHistoryPoint10868(id: "\(sides[index]).\(Int(close.x))", x: close.x,
                                                 probability: close.values[index], isPregame: close.x == pregameBar),
                    ])
                },
                absentWords: "No recorded trades")
        }
        let tickWords: [[String]] = switch frame {
        case .before: [["Oct 9", "5 AM"], ["5:57 AM", "Pregame"]]
        case .over15: [["Oct 9", "5 AM"], ["9:57 AM", "15-over report"]]
        case .final: [["Oct 9", "5 AM"], ["10:30 AM", "After the final report"]]
        }
        return CricketHistoryInput10868(
            title: "Win probability", series: series, domain: span,
            yTicks: [CricketHistoryTick10868(value: 0, lines: ["0%"]), CricketHistoryTick10868(value: 0.5, lines: ["50%"]),
                     CricketHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: [CricketHistoryTick10868(value: span.lower, lines: tickWords[0]),
                     CricketHistoryTick10868(value: span.upper, lines: tickWords[1])],
            context: "Recorded Kalshi trade closes · times in Pacific Daylight Time",
            pregameKey: "Pregame",
            summary: "India circles and West Indies diamonds; separately recorded trade closes, never joined.",
            plotHeight: 302, window: .caption("Recorded trades"), inspection: nil,
            previous: CricketHistoryControl10868(label: "Previous recorded minute", isAvailable: true),
            next: CricketHistoryControl10868(label: "Next recorded minute", isAvailable: false),
            expand: CricketHistoryControl10868(label: "Open T20 probability chart", isAvailable: true))
    }

    private static let markerKey = "Score-report publication times; not exact ball, innings-boundary or app-arrival times"

    private static let inningsMarker = CricketHistoryMarker10868(
        id: "constructed:innings-report", x: inningsReport, emphasis: .prominent, label: "Innings report",
        spoken: "India 249/5 after 20 overs. Score report published 8:24:19 AM PDT, October 9, 2026; not the exact innings end.",
        absentWords: nil)

    private static let scoreReportMarkers: [CricketHistoryMarker10868] = [
        ("13.0", report13, "170/3", "13", "9:46:44"), ("15.0", report15, "187/4", "15", "9:57:47"),
        ("17.0", report17, "223/4", "17", "10:06:58"), ("18.0", report18, "240/4", "18", "10:12:01"),
    ].map { id, x, score, overs, clock in
        CricketHistoryMarker10868(
            id: "constructed:score-report:\(id)", x: x, emphasis: .subtle, label: nil,
            spoken: "West Indies \(score) after \(overs) overs. Score report published \(clock) AM PDT, October 9, 2026; not the exact ball time.",
            absentWords: nil)
    }

    /// The innings report and the four score reports; no extra final guide.
    private static let allMarkers: [CricketHistoryMarker10868] = [inningsMarker] + scoreReportMarkers

    private static func markers(_ frame: Frame) -> CricketHistoryMarkerContext10868 {
        switch frame {
        case .before:
            // Every later guide supplied before play: the leaf draws none of them.
            CricketHistoryMarkerContext10868(phase: .before, markers: allMarkers, key: markerKey)
        case .over15:
            CricketHistoryMarkerContext10868(phase: .during, markers: Array(allMarkers.prefix(3)), key: markerKey)
        case .final:
            CricketHistoryMarkerContext10868(phase: .completed, markers: allMarkers, key: markerKey)
        }
    }

    // MARK: Stream and page

    private static func scope(_ frame: Frame) -> String {
        switch frame {
        case .before: "cricket-t20:before"
        case .over15: "cricket-t20:15.0"
        case .final: "cricket-t20:final"
        }
    }

    private static func stream(_ frame: Frame, wide: Bool = false) -> StoryStreamPresentation10868 {
        let scope = scope(frame)
        func ref(_ id: String) -> StoryStreamPresentation10868.CardRef { .init(scope: scope, id: id) }
        typealias Card = StoryStreamPresentation10868.Card
        switch frame {
        case .before:
            return StoryStreamPresentation10868(
                scope: scope, eyebrow: nil, heading: "Match stories", cards: [Card(id: "pregame", name: "Pregame outlook")],
                primary: ref("pregame"), companion: nil, companionLabel: nil, wide: wide, position: "1 of 1",
                previous: nil, next: nil)
        case .over15:
            return StoryStreamPresentation10868(
                scope: scope, eyebrow: nil, heading: "Match stories",
                cards: [Card(id: "chase", name: "The chase"), Card(id: "shift", name: "Expectation shift")],
                primary: ref("chase"), companion: ref("shift"), companionLabel: "Next", wide: wide,
                position: "1 of 2", previous: nil, next: ref("shift"))
        case .final:
            return StoryStreamPresentation10868(
                scope: scope, eyebrow: nil, heading: "After the match",
                cards: [Card(id: "shift", name: "Expectation shift"), Card(id: "chase", name: "The chase")],
                primary: ref("shift"), companion: ref("chase"), companionLabel: "Next", wide: wide,
                position: "1 of 2", previous: nil, next: ref("chase"))
        }
    }

    private static func stories(_ frame: Frame) -> [CricketEventPageStory10868] {
        switch frame {
        case .before:
            [CricketEventPageStory10868(cardID: "pregame", card: .pregame)]
        case .over15:
            [CricketEventPageStory10868(cardID: "chase", card: .chase),
             CricketEventPageStory10868(cardID: "shift", card: .expectationShift)]
        case .final:
            [CricketEventPageStory10868(cardID: "shift", card: .expectationShift),
             CricketEventPageStory10868(cardID: "chase", card: .chase)]
        }
    }

    private static let title = CricketEventPageTitle10868(eyebrow: "Recorded · Second T20I · Ranchi", title: "India · West Indies")

    private static func reader(_ frame: Frame) -> CricketEventPageReaderHeader10868 {
        switch frame {
        case .before: CricketEventPageReaderHeader10868(title: "India · West Indies", state: "Before the first ball · 20 overs per side")
        case .over15: CricketEventPageReaderHeader10868(title: "West Indies 187/4 · 15 overs", state: "Recorded chase report · target 250")
        case .final: CricketEventPageReaderHeader10868(title: "West Indies won by 6 wickets", state: "Final · 9 balls to spare")
        }
    }

    private static func about(_ frame: Frame) -> CricketEventPageAbout10868 {
        let common = [
            "India versus West Indies, second T20I in Ranchi, October 9, 2026.",
            "Pregame is the last traded minute before the pre-match report, not the market's opening probability.",
            "The two winner markets are traded independently and may not total 100%. A tie or no-result settlement at $0.50 is a settlement amount, not a third 50% prediction.",
        ]
        let later = ["Target 250 follows India’s 249/5. Rates are arithmetic from runs and legal balls, not forecasts."]
        return CricketEventPageAbout10868(title: "Recorded T20 match", paragraphs: frame == .before ? common : common + later)
    }

    private static let copy = CricketEventPageCopy10868(
        storiesLabel: "Match stories", storyUnavailable: "This story is not available in this update.",
        headlineUnavailable: "Match chances unavailable in this update.", aboutLabel: "About this match",
        allPropsLabel: "All 2 original markets")

    /// Every T20 leaf input is supplied in every frame — the later chase,
    /// shift and limited-over facts before play too — so only the format, the
    /// page phase and each leaf's own phase decide what mounts.
    private static func page(_ frame: Frame, format: CricketEventPageFormat10868 = .t20, wide: Bool = false,
                             headline: CricketHeadlineInput10868? = nil) -> CricketEventPageInput10868 {
        let context: CricketChaseLimitedOvers10868 = switch frame {
        case .before: everythingContext
        case .over15: liveContext
        case .final: finalContext
        }
        return CricketEventPageInput10868(
            phase: phase(frame), title: title, reader: reader(frame), headline: headline ?? Self.headline(frame),
            secondaryProvenance: true, notice: nil,
            history: history(frame), historyMarkers: markers(frame), readerPlotHeight: 350,
            chase: chase(frame == .final ? .final : .over15),
            runsTint: .orange, wicketTint: .gray,
            stream: stream(frame, wide: wide), stories: stories(frame), about: about(frame), copy: copy,
            format: format, pregame: pregame(), expectationShift: shift(frame == .before ? .final : frame),
            limitedOvers: context)
    }

    // MARK: Originals

    private static let originalsScope = "constructed.scope.cricket-t20.wiind"

    private static func identity(_ index: Int) -> OriginalMarketDetails9483.Identity {
        OriginalMarketDetails9483.Identity(source: "kalshi", market: "constructed.market.\(sides[index])", side: "Yes")
    }

    private static func selection(_ index: Int) -> OriginalMarketDetails9483.Selection {
        OriginalMarketDetails9483.Selection(scope: originalsScope, identity: identity(index))
    }

    private static func catalogue(_ frame: Frame) -> OriginalMarketDetails9483.Catalogue {
        let originals = (0..<2).map { index -> OriginalMarketDetails9483.Original in
            let mode: OriginalMarketDetails9483.Mode = switch frame {
            case .before: .pregame
            case .over15: .comparison(.recorded)
            case .final: .result
            }
            let later: OriginalMarketDetails9483.Reading? = frame == .over15
                ? .value(recordedTexts[index], placement: recordedValues[index], provenance: recordedDetail)
                : nil
            let grade: OriginalMarketDetails9483.Grade? = frame == .final
                ? OriginalMarketDetails9483.Grade(words: gradeWords[index], provenance: settlementDetail)
                : nil
            return OriginalMarketDetails9483.Original(
                identity: identity(index), title: titles[index], outcome: subjects[index], mode: mode,
                pregame: .value(pregameTexts[index], placement: pregameValues[index], provenance: pregameDetail),
                later: later, grade: grade,
                about: OriginalMarketDetails9483.About(
                    source: "Kalshi · \(tickers[index])", rules: .verified([rules[index], tieRule]),
                    provenance: [OriginalMarketDetails9483.Row(label: "Original pregame source time", value: "2026-10-09T12:57:00Z")],
                    historicalQuote: nil))
        }
        return OriginalMarketDetails9483.Catalogue(scope: originalsScope, originals: originals)
    }

    private static func originals(_ frame: Frame, selected: Int? = 1) -> CricketEventPageOriginals10868 {
        CricketEventPageOriginals10868(
            catalogue: catalogue(frame), selection: selected.map { selection($0) },
            heading: "All 2 original markets", context: "2 retained originals",
            emptyWords: "No retained originals for this match", unavailableChoice: "Original unavailable", tint: .orange)
    }

    // MARK: Test-only inputs, for the format cases

    private static func outlook(completed: Bool) -> CricketOutlookInput10868 {
        if completed {
            return CricketOutlookInput10868(
                eyebrow: "Pregame expectations → result", title: "West Indies was 23% pregame", beforeLabel: "Pregame",
                comparisonLabel: "Recorded", rows: rows(), selectedRowID: nil, notes: [],
                mode: .completed(CricketOutlookFinalFrame10868(outcomeLabel: "Match", outcomeMissing: "Not reported",
                                                               gradeLabel: "Original contract", context: [])))
        }
        return CricketOutlookInput10868(
            eyebrow: "Pregame → recorded chance", title: "How the outlook changed", beforeLabel: "Pregame",
            comparisonLabel: "Recorded", rows: rows(), selectedRowID: nil, notes: [])
    }

    private static func survival() -> CricketSurvivalInput10868 {
        CricketSurvivalInput10868(
            phase: .during, subject: "West Indies · original market", title: "Can they hold on?", pregameLabel: "Pregame",
            pregame: wiPregame, comparisonLabel: "Recorded win chance", comparison: wiAt15,
            checkpointsLabel: "Reported wickets remaining", checkpoints: [], selectedCheckpointID: nil, notes: [])
    }

    private static func activation(_ stream: StoryStreamPresentation10868, _ id: String,
                                   log: @escaping (String) -> Void) -> StoryStreamCardActivation10868 {
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: id)
        return StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
            if case .interaction(_, let card) = intent { log("hold:\(card?.id ?? "-")") } else { log("other") }
        }
    }

    private static func mounted(_ input: CricketEventPageInput10868) -> [CricketEventPageCard10868] {
        let model = CricketEventPageModel10868(input)
        return CricketEventPageCard10868.allCases.filter(model.isMounted)
    }

    private static func points(_ history: CricketHistoryInput10868) -> [CricketHistoryPoint10868] {
        history.series.flatMap { $0.segments.flatMap(\.points) }
    }

    // MARK: Format

    @MainActor
    func testTheTestFormatStaysTheDefaultAndMountsNoT20LeafEvenWhenSupplied() {
        // An input built without a format is a Test page with no T20 input.
        let bare = CricketEventPageInput10868(
            phase: .during, title: Self.title, reader: Self.reader(.over15), headline: Self.headline(.over15),
            history: Self.history(.over15), runsTint: .orange, wicketTint: .gray, copy: Self.copy)
        XCTAssertEqual(bare.format, .test)
        XCTAssertNil(bare.pregame)
        XCTAssertNil(bare.expectationShift)
        XCTAssertNil(bare.limitedOvers)

        for frame in [Frame.before, .over15, .final] {
            let supplied = Self.page(frame, format: .test)
            XCTAssertNotNil(supplied.pregame)
            XCTAssertNotNil(supplied.expectationShift)
            XCTAssertNotNil(supplied.limitedOvers)
            var plain = supplied
            plain.pregame = nil
            plain.expectationShift = nil
            plain.limitedOvers = nil

            let model = CricketEventPageModel10868(supplied)
            XCTAssertNil(model.pregame)
            XCTAssertNil(model.expectationShift)
            XCTAssertNil(model.limitedOvers)
            XCTAssertEqual(Self.mounted(supplied), Self.mounted(plain), "supplying T20 leaves changes nothing on a Test page")
            XCTAssertEqual(Self.mounted(supplied), frame == .before ? [.history] : [.history, .chase])
            XCTAssertFalse(model.readerShows(.pregame))
            XCTAssertFalse(model.readerShows(.expectationShift))
            for link in supplied.stories where link.card == .pregame || link.card == .expectationShift {
                XCTAssertNil(model.story(link.cardID), "a T20 story is never a Test story")
            }

            let view = CricketEventPagePresentation10868(input: supplied, onExpectationShiftDetails: { _ in XCTFail("no shift on a Test page") })
            XCTAssertNil(view.pregameContent())
            XCTAssertNil(view.expectationShiftContent())
            XCTAssertNil(view.chaseContent()?.limitedOvers, "the Test chase never takes the limited-over variant")
            XCTAssertEqual(view.chaseContent()?.input, CricketEventPagePresentation10868(input: plain).chaseContent()?.input)
        }
    }

    // MARK: Phases

    @MainActor
    func testBeforePlayTheStreamOffersOnlyThePregameOutlookBesideTheHeadlineHistoryAndTwoOriginals() {
        let input = Self.page(.before)
        let model = CricketEventPageModel10868(input)
        let originals = Self.originals(.before)
        let view = CricketEventPagePresentation10868(input: input, originals: originals)

        XCTAssertEqual(input.format, .t20)
        XCTAssertEqual(Self.mounted(input), [.history, .pregame])
        XCTAssertEqual(input.stream?.cards.map(\.id), ["pregame"])
        XCTAssertEqual(model.storyCard("pregame"), .pregame)
        XCTAssertTrue(model.readerShows(.pregame))

        // The pregame outlook: both originals' own pregame readings, 78% and
        // 23%, never normalized, complemented or joined by a draw row.
        guard let story = view.pregameContent()?.input else { return XCTFail("the pregame outlook mounts before play") }
        XCTAssertEqual(story, input.pregame)
        XCTAssertEqual(story.visibleRows.map(\.subject), Self.subjects)
        XCTAssertEqual(story.visibleRows.map(\.shape), [.circle, .diamond])
        let fills = story.rows.compactMap { story.fill($0) }
        XCTAssertEqual(fills, Self.pregameValues)
        XCTAssertEqual(fills.reduce(0, +), 1.01, accuracy: 1e-9, "two independent readings stay 101%")
        XCTAssertEqual(story.rows.count, 2, "no draw row is added for a tie rule's settlement amount")

        // The headline: each original's own pregame chance only.
        XCTAssertEqual(view.headlineContent()?.input, input.headline)
        XCTAssertEqual(input.headline.slots, [.pregame])
        XCTAssertEqual(input.headline.sourceInfo.subjects.map { $0.entries.map(\.text) }, [["78%"], ["23%"]])

        // The history: named and shape-keyed, each original's own pregame close.
        let anchor = view.historyContent(reader: false)
        XCTAssertEqual(anchor.input, input.history)
        XCTAssertEqual(anchor.input.series.map(\.name), Self.subjects)
        XCTAssertEqual(anchor.input.series.map(\.shape), [.circle, .diamond])
        let last = anchor.input.series.compactMap { $0.segments.last?.points.last?.probability }
        XCTAssertEqual(last, Self.pregameValues)
        XCTAssertEqual(last.reduce(0, +), 1.01, accuracy: 1e-9)
        XCTAssertTrue(Self.points(anchor.input).allSatisfy(\.isPregame))

        // No chase, shift or limited-over context before play, though all are supplied.
        XCTAssertNotNil(input.chase)
        XCTAssertNotNil(input.expectationShift)
        XCTAssertNotNil(input.limitedOvers)
        XCTAssertNil(view.chaseContent())
        XCTAssertNil(view.expectationShiftContent())
        XCTAssertNil(model.limitedOvers)

        // The two original winner markets, with the held original's Details.
        let choices = OriginalMarketChooser9483.choices(catalogue: originals.catalogue, selection: originals.selection,
                                                        labels: originals.labels, unavailableChoice: originals.unavailableChoice)
        XCTAssertEqual(choices.map(\.label), Self.titles)
        XCTAssertEqual(choices.map(\.isSelected), [false, true])
        XCTAssertEqual(view.chooserContent()?.catalogue, originals.catalogue)
        XCTAssertEqual(view.chooserContent()?.heading, "All 2 original markets")
    }

    @MainActor
    func testBeforePlayNoLaterTargetScoreBallRateComparisonOrResultIsShownOrSpoken() {
        let input = Self.page(.before)
        let originals = Self.originals(.before)
        let view = CricketEventPagePresentation10868(input: input, originals: originals)

        // Every later fact really is supplied, so the absence below is the
        // page's and each leaf's gating, not a missing input.
        XCTAssertEqual(input.headline.rows.map { $0.comparison.observation?.text }, ["67%", "34%"])
        XCTAssertEqual(input.expectationShift?.phase, .final)
        XCTAssertEqual(input.expectationShift?.rows.count, 4)
        XCTAssertNotNil(input.limitedOvers?.task)
        XCTAssertEqual(input.chase?.phase, .during)
        XCTAssertEqual(input.historyMarkers?.markers.count, 5)

        var outputs: [String] = [input.title.title, input.reader.title]
        outputs += [input.title.eyebrow, input.reader.state].compactMap { $0 }
        outputs += input.about.map { [$0.title] + $0.paragraphs } ?? []
        outputs += input.stream?.cards.map(\.name) ?? []
        if let headline = view.headlineContent()?.input {
            outputs += headline.rows.map { headline.accessibilityRowValue($0) }
            outputs += [headline.caption, headline.accessibilityState].compactMap { $0 }
            for subject in headline.sourceInfo.subjects {
                for entry in subject.entries {
                    outputs += [entry.label, entry.text] + [entry.detail].compactMap { $0 }
                }
            }
            XCTAssertNil(headline.sourceInfo.state, "the supplied 187/4 state stays hidden before play")
        } else {
            XCTFail("the before headline mounts")
        }
        if let story = view.pregameContent()?.input {
            outputs += [story.accessibilityHeader, story.accessibilityNotes].compactMap { $0 }
            outputs += story.visibleRows.compactMap { story.accessibilityRowValue($0) }
            for row in story.visibleRows {
                if let observation = story.reading(row)?.observation { outputs += [observation.text, observation.detail] }
            }
            outputs += story.visibleNotes
        } else {
            XCTFail("the pregame outlook mounts")
        }
        let anchor = view.historyContent(reader: false)
        XCTAssertEqual(CricketHistoryPlotArrangement10868.visibleMarkers(anchor.markers, domain: anchor.input.domain), [])
        XCTAssertEqual(CricketHistoryPlotArrangement10868.unavailableMarkerWords(anchor.markers), [])
        outputs += [anchor.input.title, anchor.input.summary] + [anchor.input.context].compactMap { $0 }
        outputs += anchor.input.xTicks.flatMap(\.lines)
        for index in 0..<2 {
            let content = OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: Self.selection(index))
            XCTAssertNil(content?.result, "no contract result before play")
            outputs += content?.readings.map(\.text) ?? []
        }
        XCTAssertNil(view.chaseContent())
        XCTAssertNil(view.expectationShiftContent())

        let later = ["67%", "34%", "57%", "89%", "99%", "249/5", "170/3", "187/4", "223/4", "240/4", "252/4",
                     "250", "Won", "Winner", "Lost", "won by", "balls", "12.47", "12.60", "13.62", "runs per over", "needed"]
        XCTAssertGreaterThan(outputs.count, 10)
        for output in outputs {
            for fact in later {
                XCTAssertFalse(output.contains(fact), "“\(fact)” reached before play: \(output)")
            }
        }
    }

    @MainActor
    func testDuringPlayTheChaseWithItsLimitedOverContextAndTheExpectationShiftMountAndNoTestOnlyCard() {
        let input = Self.page(.over15)
        let model = CricketEventPageModel10868(input)
        let view = CricketEventPagePresentation10868(input: input)

        XCTAssertEqual(Self.mounted(input), [.history, .chase, .expectationShift])
        XCTAssertNil(view.pregameContent(), "the pregame outlook is before play only")
        XCTAssertNil(view.shiftsContent())
        XCTAssertNil(view.survivalContent())
        XCTAssertNil(view.expectationsContent())
        XCTAssertEqual(model.storyCard("chase"), .chase)
        XCTAssertEqual(model.storyCard("shift"), .expectationShift)

        // Headline: each original's own pregame beside its own recorded close,
        // 67% and 34% still 101%, with the owner's score words under their own clock.
        XCTAssertEqual(input.headline.sourceInfo.subjects.map { $0.entries.map(\.text) }, [["78%", "67%"], ["23%", "34%"]])
        XCTAssertEqual(input.headline.sourceInfo.subjects.map { $0.entries.map(\.detail) },
                       [[Self.pregameDetail, Self.recordedDetail], [Self.pregameDetail, Self.recordedDetail]])
        XCTAssertEqual(Self.recordedValues.reduce(0, +), 1.01, accuracy: 1e-9)
        XCTAssertEqual(input.headline.accessibilityState,
                       "West Indies · batting: 187 for 4. 15 overs: Target 250 runs. \(Self.report15Detail)")

        // The chase, with the owner's limited-over context beside it.
        guard let chase = view.chaseContent() else { return XCTFail("the live chase mounts") }
        XCTAssertEqual(chase.input, input.chase)
        XCTAssertEqual(chase.limitedOvers, Self.liveContext)
        XCTAssertEqual(chase.input.visibleState?.runs, .reported(text: "187", value: 187))
        XCTAssertEqual(chase.input.visibleState?.target, .reported(text: "250", value: 250))
        XCTAssertEqual(chase.input.visibleState?.reportDetail, Self.report15Detail)
        XCTAssertNotEqual(chase.input.visibleState?.reportDetail, Self.recordedDetail,
                          "the report clock and the close's own clock stay separate facts")
        XCTAssertNil(chase.input.visibleContractResult, "no result while live")
        let limited = CricketChaseLimitedOversVisible10868(phase: chase.input.phase, context: chase.limitedOvers)
        XCTAssertEqual(limited?.accessibilityTask, "Chase · 15 overs: 63 runs needed from 30 balls left")
        XCTAssertEqual(limited?.ballFraction ?? -1, 0.75, accuracy: 1e-9)
        XCTAssertEqual(limited?.rateRows.map(\.label), ["Runs per over so far", "Needed from here, runs per over"])

        // The expectation shift: the 13.0 and 15.0 checkpoints against pregame on one scale.
        guard let shift = view.expectationShiftContent() else { return XCTFail("the live expectation shift mounts") }
        XCTAssertEqual(shift.input, input.expectationShift)
        XCTAssertEqual(shift.tint, input.runsTint, "the card follows the chasing side")
        XCTAssertEqual(shift.input.visibleRows.map(\.id), Array(Self.checkpointIDs.prefix(2)))
        XCTAssertEqual(shift.input.visibleRows.map { shift.input.rowPosition($0) }, [0.57, 0.34])
        XCTAssertEqual(shift.input.baselinePosition, 0.23)
        XCTAssertEqual(shift.input.visibleComparison, Self.wiAt15, "the owner's headline reading, not the last row's")
        XCTAssertNil(shift.input.visibleMatchResult)
        XCTAssertNil(shift.input.visibleOriginalResult)

        // History: only closes at or before the 15-over report, each its own
        // run, and the innings report plus two score-report guides.
        let anchor = view.historyContent(reader: false)
        XCTAssertTrue(Self.points(anchor.input).allSatisfy { $0.x <= Self.report15 })
        XCTAssertTrue(anchor.input.series.allSatisfy { $0.segments.allSatisfy { $0.points.count == 1 } },
                      "sparse closes are never joined into a trace")
        let guides = ["constructed:innings-report", "constructed:score-report:13.0", "constructed:score-report:15.0"]
        XCTAssertEqual(anchor.markers?.markers.map(\.id), guides)
        XCTAssertEqual(CricketHistoryPlotArrangement10868.visibleMarkers(anchor.markers, domain: anchor.input.domain).map(\.id), guides)
    }

    @MainActor
    func testAtTheFinalPregameMeetsTheReportedFinishBesideFourHistoricalCheckpointsAndEachOriginalsOwnGrade() {
        let input = Self.page(.final)
        let model = CricketEventPageModel10868(input)
        let originals = Self.originals(.final)
        let view = CricketEventPagePresentation10868(input: input, originals: originals)

        XCTAssertEqual(Self.mounted(input), [.history, .chase, .expectationShift])
        XCTAssertEqual(model.storyCard("shift"), .expectationShift)
        XCTAssertEqual(model.storyCard("chase"), .chase)

        // Headline: pregame beside the reported match finish — never a later
        // chance and never a contract grade.
        XCTAssertEqual(input.headline.sourceInfo.subjects.map { $0.entries.map(\.slot) },
                       Array(repeating: [.pregame, .outcome], count: 2))
        XCTAssertEqual(input.headline.sourceInfo.subjects.map { $0.entries.map(\.text) }, [["78%", "Lost"], ["23%", "Winner"]])
        XCTAssertFalse(input.headline.sourceInfo.subjects.flatMap { $0.entries.map(\.text) }.contains("Won"))

        // The expectation shift: exactly the four historical rows at
        // 57/34/89/99, no fifth finish row, no 0% or 100% point.
        guard let shift = view.expectationShiftContent()?.input else { return XCTFail("the final expectation shift mounts") }
        XCTAssertEqual(shift.visibleRows.map(\.id), Self.checkpointIDs)
        XCTAssertEqual(shift.visibleRows.map(\.label), ["13.0 overs", "15.0 overs", "17.0 overs", "18.0 overs"])
        XCTAssertEqual(shift.visibleRows.map { shift.rowPosition($0) }, [0.57, 0.34, 0.89, 0.99])
        XCTAssertTrue(shift.visibleRows.allSatisfy { row in row.position.map { $0 > 0 && $0 < 1 } ?? false })
        XCTAssertEqual(shift.baselinePosition, 0.23)
        XCTAssertNil(shift.visibleComparison, "the supplied settled 99% is not a final chance")

        // The reported match result and the contract's own result stay two facts.
        XCTAssertEqual(shift.visibleMatchResult, Self.wiMatchResult)
        XCTAssertEqual(shift.visibleOriginalResult, Self.wiGrade)
        guard case .reported(let match)? = shift.visibleMatchResult,
              case .graded(let grade)? = shift.visibleOriginalResult
        else { return XCTFail("both final results are supplied") }
        XCTAssertNotEqual(match.text, grade.text)
        XCTAssertNotEqual(match.detail, grade.detail, "the match report and the contract settlement keep their own clocks")

        // The resolved chase with its completed limited-over pair; no live task or required rate.
        guard let chase = view.chaseContent() else { return XCTFail("the resolved chase mounts") }
        XCTAssertEqual(chase.input.visibleHeading, "West Indies won by 6 wickets")
        XCTAssertEqual(chase.input.visibleHeadingDetail, Self.finalDetail)
        XCTAssertNil(chase.input.visibleComparison, "a settled price is not a final chance")
        XCTAssertEqual(chase.input.visibleContractResult, Self.wiGrade)
        XCTAssertEqual(chase.input.visibleState?.runs, .reported(text: "252", value: 252))
        XCTAssertEqual(chase.limitedOvers, Self.finalContext)
        let limited = CricketChaseLimitedOversVisible10868(phase: chase.input.phase, context: chase.limitedOvers)
        XCTAssertEqual(limited?.accessibilityTask, "The chase, completed: 252 runs scored with 9 balls to spare")
        XCTAssertEqual(limited?.rateRows.map(\.label), ["Runs per over so far"])

        // Each original's own grade in its Details, with its own settlement clock.
        for index in 0..<2 {
            let content = OriginalMarketDetails9483.content(catalogue: originals.catalogue, selection: Self.selection(index))
            XCTAssertEqual(content?.result?.words, Self.gradeWords[index])
            XCTAssertEqual(content?.result?.provenance, Self.settlementDetail)
            XCTAssertNotEqual(content?.result?.words, "West Indies won by 6 wickets")
        }

        // The history keeps the last retained closes (1% and 99%) and the
        // five report guides; no 0/100 point and no extra final guide.
        let anchor = view.historyContent(reader: false)
        XCTAssertTrue(Self.points(anchor.input).allSatisfy { $0.probability > 0 && $0.probability < 1 })
        XCTAssertEqual(anchor.markers?.markers.map(\.id),
                       ["constructed:innings-report", "constructed:score-report:13.0", "constructed:score-report:15.0",
                        "constructed:score-report:17.0", "constructed:score-report:18.0"])
        XCTAssertEqual(CricketHistoryPlotArrangement10868.visibleMarkers(anchor.markers, domain: anchor.input.domain).count, 5)
    }

    // MARK: Gating and links

    @MainActor
    func testALeafFromAnotherPhaseOrTheOtherFormatIsNotMounted() {
        // During play: the before-phase pregame outlook, a final shift and a
        // final chase are not coerced into live play.
        var live = Self.page(.over15)
        live.expectationShift = Self.shift(.final)
        live.chase = Self.chase(.final)
        XCTAssertEqual(live.pregame?.phase, .before)
        let liveModel = CricketEventPageModel10868(live)
        XCTAssertNil(liveModel.pregame, "the pregame outlook is before play only")
        XCTAssertNil(liveModel.expectationShift, "a final shift is not live play")
        XCTAssertNil(liveModel.chase, "a final chase is not live play")
        XCTAssertNil(liveModel.limitedOvers, "no limited-over context without a mounted chase")
        XCTAssertEqual(Self.mounted(live), [.history])

        // At the final: a live shift and a live chase are not the resolved ones.
        var final = Self.page(.final)
        final.expectationShift = Self.shift(.over15)
        final.chase = Self.chase(.over15)
        final.limitedOvers = Self.everythingContext
        let finalModel = CricketEventPageModel10868(final)
        XCTAssertNil(finalModel.expectationShift)
        XCTAssertNil(finalModel.chase)
        XCTAssertNil(finalModel.limitedOvers)
        XCTAssertEqual(Self.mounted(final), [.history])

        // Before play: an outlook the owner marked for another phase, or a
        // shift of any phase, is not shown.
        var before = Self.page(.before)
        before.pregame = Self.pregame(phase: .during)
        before.expectationShift = Self.shift(.before)
        let beforeModel = CricketEventPageModel10868(before)
        XCTAssertNil(beforeModel.pregame)
        XCTAssertNil(beforeModel.expectationShift)
        XCTAssertEqual(Self.mounted(before), [.history])

        // The Test-only cards are never mounted in the T20 format, whatever is supplied …
        var testOnly = Self.page(.over15)
        testOnly.shifts = Self.outlook(completed: false)
        testOnly.survival = Self.survival()
        XCTAssertNil(CricketEventPageModel10868(testOnly).shifts)
        XCTAssertNil(CricketEventPageModel10868(testOnly).survival)
        XCTAssertNil(CricketEventPagePresentation10868(input: testOnly).survivalContent())
        var testOnlyFinal = Self.page(.final)
        testOnlyFinal.expectations = Self.outlook(completed: true)
        XCTAssertNil(CricketEventPageModel10868(testOnlyFinal).expectations)
        // … while the same inputs on a Test page do mount: the format decides, not the inputs.
        testOnly.format = .test
        XCTAssertNotNil(CricketEventPageModel10868(testOnly).shifts)
        XCTAssertNotNil(CricketEventPageModel10868(testOnly).survival)
        testOnlyFinal.format = .test
        XCTAssertNotNil(CricketEventPageModel10868(testOnlyFinal).expectations)
    }

    @MainActor
    func testOnlyOneExactLinkToAStoryThisPhaseMountsResolves() {
        var links = Self.page(.over15)
        links.stories = [
            CricketEventPageStory10868(cardID: "pregame", card: .pregame),
            CricketEventPageStory10868(cardID: "shift", card: .expectationShift),
            CricketEventPageStory10868(cardID: "shift", card: .chase),
            CricketEventPageStory10868(cardID: "history", card: .history),
            CricketEventPageStory10868(cardID: "holding", card: .survival),
            CricketEventPageStory10868(cardID: "chase", card: .chase),
        ]
        let linked = CricketEventPageModel10868(links)
        XCTAssertNil(linked.story("pregame"), "the pregame outlook is not mounted during play")
        XCTAssertNil(linked.story("shift"), "two links for one id name no single story")
        XCTAssertNil(linked.story("history"), "the anchor is never a stream story")
        XCTAssertNil(linked.story("holding"), "a Test-only card is never a T20 story")
        XCTAssertNil(linked.story("unknown"))
        XCTAssertEqual(linked.storyCard("chase"), .chase)

        // Before play a link to a later card is unavailable; the pregame link resolves.
        var early = Self.page(.before)
        early.stories = [CricketEventPageStory10868(cardID: "shift", card: .expectationShift),
                         CricketEventPageStory10868(cardID: "chase", card: .chase),
                         CricketEventPageStory10868(cardID: "pregame", card: .pregame)]
        let earlyModel = CricketEventPageModel10868(early)
        XCTAssertNil(earlyModel.story("shift"))
        XCTAssertNil(earlyModel.story("chase"))
        XCTAssertEqual(earlyModel.storyCard("pregame"), .pregame)
        XCTAssertFalse(earlyModel.readerShows(.expectationShift))
        XCTAssertFalse(earlyModel.readerShows(.chase))

        // At the final a pregame link is unavailable too.
        var late = Self.page(.final)
        late.stories = [CricketEventPageStory10868(cardID: "pregame", card: .pregame)]
        XCTAssertNil(CricketEventPageModel10868(late).story("pregame"))
        XCTAssertFalse(CricketEventPageModel10868(late).readerShows(.pregame))
    }

    @MainActor
    func testAMissingValueKeepsItsValidNeighbourAndItsOwnWords() {
        // The pregame outlook: India's reading missing, West Indies keeps its 23%.
        var before = Self.page(.before)
        before.pregame = Self.pregame(rows: [Self.row(0, before: .unavailable("Pregame chance unavailable")), Self.row(1)])
        guard let story = CricketEventPagePresentation10868(input: before).pregameContent()?.input
        else { return XCTFail("the pregame outlook stays mounted") }
        XCTAssertNil(story.fill(story.rows[0]), "unknown is never a 0% rail")
        XCTAssertEqual(story.fill(story.rows[1]), 0.23)
        XCTAssertEqual(story.accessibilityRowValue(story.rows[0]), "\(Self.pregameLabel): Pregame chance unavailable")
        XCTAssertEqual(story.accessibilityRowValue(story.rows[1]), "\(Self.pregameLabel): 23%, \(Self.pregameDetail)")

        // The expectation shift: a missing pregame keeps every row …
        var live = Self.page(.over15)
        live.expectationShift = Self.shift(.over15, pregame: .unavailable("Pregame chance unavailable"), pregamePosition: nil)
        guard let noBaseline = CricketEventPagePresentation10868(input: live).expectationShiftContent()?.input
        else { return XCTFail("the shift stays mounted") }
        XCTAssertNil(noBaseline.baselinePosition)
        XCTAssertEqual(noBaseline.visibleRows.map { noBaseline.rowPosition($0) }, [0.57, 0.34])
        // … and a missing row reading keeps the pregame, its neighbour and its own report.
        let gap = CricketChaseShiftRow10868(id: Self.checkpointIDs[1], label: "15.0 overs", score: Self.checkpointRows[1].score,
                                            recorded: .unavailable("No trade before this report"), position: nil)
        live.expectationShift = Self.shift(.over15, rows: [Self.checkpointRows[0], gap])
        guard let oneGap = CricketEventPagePresentation10868(input: live).expectationShiftContent()?.input
        else { return XCTFail("the shift stays mounted") }
        XCTAssertEqual(oneGap.baselinePosition, 0.23)
        XCTAssertEqual(oneGap.visibleRows.map { oneGap.rowPosition($0) }, [0.57, nil])
        XCTAssertEqual(oneGap.rowSegment(oneGap.visibleRows[0]), CricketChaseShiftSegment10868(lower: 0.23, upper: 0.57))
        XCTAssertNil(oneGap.rowSegment(oneGap.visibleRows[1]), "never a neighbour's value or 0%")
        XCTAssertEqual(oneGap.visibleRows[1].score, Self.checkpointRows[1].score)

        // The chase: without the owner's limited-over context the actual chase
        // stands, and no ball limit or rate is invented.
        var bare = Self.page(.over15)
        bare.limitedOvers = nil
        let bareView = CricketEventPagePresentation10868(input: bare)
        guard let chase = bareView.chaseContent() else { return XCTFail("the chase stays mounted") }
        XCTAssertNil(chase.limitedOvers)
        XCTAssertEqual(chase.input.visibleState?.runs, .reported(text: "187", value: 187))
        XCTAssertNotNil(bareView.expectationShiftContent(), "the shift stands without the chase's context")

        // The headline: one original's recorded reading missing keeps the other's.
        let partial = Self.page(.over15, headline: Self.headline(
            .over15, rows: [Self.row(0, comparison: .unavailable("Current probability unavailable")), Self.row(1)]))
        XCTAssertEqual(CricketEventPagePresentation10868(input: partial).headlineContent()?.input, partial.headline)
        XCTAssertEqual(partial.headline.sourceInfo.subjects.map { $0.entries.map(\.text) },
                       [["78%", "Current probability unavailable"], ["23%", "34%"]])
    }

    // MARK: Parity and holds

    @MainActor
    func testTheStreamAndTheFullSizeReaderShowTheSameLeafInputsWithExactCallbacksAndOneHoldPerPageAction() {
        var log: [String] = []
        // Wide, so the owner displays the chase AND its companion shift: the
        // stream's activation applies only to a card it displays.
        let input = Self.page(.over15, wide: true)
        XCTAssertEqual(input.stream?.wide, true)
        func view(_ mode: CricketEventPageMode10868 = .page, hook: Bool = true) -> CricketEventPagePresentation10868 {
            CricketEventPagePresentation10868(
                input: input, mode: mode, originals: Self.originals(.over15),
                onAbout: { log.append("about") },
                onSourceInfo: { log.append("sources:\($0.subjects.count)") },
                onAllProps: { log.append("allProps") },
                onOriginalSelect: { log.append("original:\($0.identity.market)") },
                onStoryIntent: { _ in log.append("stream") },
                onHistoryPrevious: { log.append("previous") },
                onHistoryNext: { log.append("next") },
                onHistoryExpand: { log.append("expand") },
                onHistoryWindowChoice: { log.append("window:\($0)") },
                onHistoryPlotPosition: { log.append("plot:\(Int($0))") },
                onChaseDetails: { log.append("chase.details:\($0.market)") },
                onExpectationShiftDetails: { log.append("shift.details:\($0.market)") },
                onInteraction: hook ? { log.append("hold") } : nil)
        }
        guard let stream = input.stream else { return XCTFail("the live stream is supplied") }
        let page = view()
        let chaseHook = Self.activation(stream, "chase") { log.append($0) }
        let shiftHook = Self.activation(stream, "shift") { log.append($0) }
        let streamChase = page.chaseContent(activation: chaseHook)
        let streamShift = page.expectationShiftContent(activation: shiftHook)
        let readerChase = view(.reader(.chase)).chaseContent()
        let readerShift = view(.reader(.expectationShift)).expectationShiftContent()
        _ = page.headlineContent()
        _ = page.historyContent(reader: false)
        _ = page.chooserContent()
        _ = view(.original).originalDetailsContent()
        XCTAssertEqual(log, [], "building and reading calls nothing")

        // Parity: the stream card and the full-size reader are the same leaf with the same input.
        XCTAssertEqual(streamChase?.input, readerChase?.input)
        XCTAssertEqual(streamChase?.limitedOvers, readerChase?.limitedOvers)
        XCTAssertEqual(readerChase?.limitedOvers, Self.liveContext)
        XCTAssertEqual(streamShift?.input, readerShift?.input)
        XCTAssertEqual(streamShift?.tint, readerShift?.tint)
        XCTAssertTrue(CricketEventPageModel10868(input).readerShows(.chase))
        XCTAssertTrue(CricketEventPageModel10868(input).readerShows(.expectationShift))

        // A stream card's action: the stream's activation once, then the exact
        // owner callback — never the page hook as well.
        streamChase?.onDetails?(Self.chaseRef)
        streamShift?.onDetails?(Self.chaseRef)
        XCTAssertEqual(log, ["hold:chase", "chase.details:constructed.market.WI",
                             "hold:shift", "shift.details:constructed.market.WI"])

        // Full-size content: the exact callbacks, no hold — its host already holds.
        log = []
        readerChase?.onDetails?(Self.chaseRef)
        readerShift?.onDetails?(Self.chaseRef)
        view(.reader(.expectationShift)).openReaderAbout()
        XCTAssertEqual(log, ["chase.details:constructed.market.WI", "shift.details:constructed.market.WI", "about"])

        // Page, catalogue and Details actions: the hook once, then the exact
        // owner callback with its exact value.
        log = []
        page.openTitleAbout()
        page.headlineContent()?.openSourceInfo()
        let anchor = page.historyContent(reader: false)
        anchor.onPrevious?()
        anchor.onExpand?()
        anchor.onWindowChoice?("match")
        anchor.onPlotPosition?(Self.report13)
        page.chooserContent()?.onSelect?(Self.selection(0))
        page.openAllProps()
        view(.catalogue).catalogueContent()?.onSelect?(Self.selection(1))
        XCTAssertEqual(log, ["hold", "about", "hold", "sources:2", "hold", "previous", "hold", "expand",
                             "hold", "window:match", "hold", "plot:\(Int(Self.report13))",
                             "hold", "original:constructed.market.IND", "hold", "allProps",
                             "hold", "original:constructed.market.WI"])
        XCTAssertEqual(view(.original).originalDetailsContent()?.selection, Self.selection(1), "the held original's Details")

        // Full-card entry: the stream's own Open full card names the shift,
        // which this phase shows full size.
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let shiftRef = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: "shift")
        XCTAssertEqual(stream.intents(for: .open(shiftRef), resolved: resolved),
                       [.interaction(scope: stream.scope, card: shiftRef), .open(shiftRef)])
        XCTAssertEqual(CricketEventPageModel10868(input).storyCard(shiftRef.id), .expectationShift)

        // No owner callback: no action anywhere and no hold.
        log = []
        let silent = CricketEventPagePresentation10868(input: input, onInteraction: { log.append("hold") })
        XCTAssertNil(silent.expectationShiftContent()?.onDetails)
        XCTAssertNil(silent.expectationShiftContent(activation: shiftHook)?.onDetails)
        XCTAssertNil(silent.chaseContent(activation: chaseHook)?.onDetails)
        XCTAssertNil(silent.expectationShiftContent()?.input.detailsAction(canOpenDetails: false))
        XCTAssertEqual(log, [])

        // Before play: the pregame outlook is the same static leaf in the
        // stream and full size, has no action, and its full card is reachable.
        let before = Self.page(.before)
        let beforePage = CricketEventPagePresentation10868(input: before, onInteraction: { log.append("hold") })
        let beforeReader = CricketEventPagePresentation10868(input: before, mode: .reader(.pregame))
        XCTAssertEqual(beforePage.pregameContent()?.input, beforeReader.pregameContent()?.input)
        XCTAssertNotNil(beforeReader.pregameContent())
        XCTAssertTrue(CricketEventPageModel10868(before).readerShows(.pregame))
        guard let beforeStream = before.stream else { return XCTFail("the before stream is supplied") }
        let pregameRef = StoryStreamPresentation10868.CardRef(scope: beforeStream.scope, id: "pregame")
        XCTAssertEqual(beforeStream.intents(for: .open(pregameRef), resolved: beforeStream.resolve(reduceMotion: false, actionable: true)),
                       [.interaction(scope: beforeStream.scope, card: pregameRef), .open(pregameRef)])
        XCTAssertEqual(log, [], "a static card asks for nothing")
    }
}
