import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the racing event screen (`racing-live`) composed from the accepted
/// leaves.
///
/// PREPARED / NOT RUN. The view is SwiftUI and is not rasterised here. What is
/// asserted is the composition only: which actual leaf Views the page mounts
/// before the start, at a lap report and at the final, that each receives the
/// owner's input unchanged, each driver's own pre-race, recorded and finish
/// readings with their own clocks, the reported gap beside its own report
/// clock, phase-appropriate absence, the history's report guides at or before
/// its frame, the story stream's card-to-leaf wiring, the activation hook
/// before each card action, the owner's interaction hook before each page,
/// catalogue and Details action (and never for full-size content, stream
/// cards or passive reads), the full-size history without its expand control,
/// the readers' compact chances, each About, the original catalogue and
/// Details, the owner's category and Show more controls around the unchanged
/// catalogue, the arrangement candidates, and that nothing fires passively.
/// Each leaf's own rules stay with its own tests; nothing here claims a
/// rendered fit, a native runtime, VoiceOver behaviour, a stream hold
/// qualification, a production binding, or any other route.
///
/// ARCHIVED raw values come from the 2026 Singapore Grand Prix (ESPN event
/// 600057445; verified start 2026-10-11T12:00:00Z; 62 laps), as already
/// retained by the accepted racing component cases and reconciled with the
/// pinned reference `racingLiveCapture.json`, `racingEvidence.json`,
/// `racingLifecycleCapture.json` and `RACING-HISTORY-REUSE-REFERENCE.json`:
/// - winner contracts Max Verstappen (5229406), Charles Leclerc (5229402),
///   Lewis Hamilton (5229411), Kimi Antonelli (5229405), Lando Norris
///   (5229404) and their podium contracts (5229633, 5229629, 5229638,
///   5229632, 5229631), each on its own Yes token, with each original's own
///   last pre-race trade (Verstappen 0.6499999935 at 11:59:31Z / podium
///   0.8199999967 at 11:57:07Z; Leclerc 0.1399999999 at 11:59:46Z / 0.6666666667
///   at 11:59:00Z; Hamilton 0.16 at 11:59:19Z / 0.609999986 at 11:58:06Z;
///   Antonelli 0.08 at 11:59:09Z / 0.4799998464 at 11:59:15Z; Norris 0.025 at
///   11:52:54Z / 0.2899999884 at 11:49:21Z) — independent originals, never
///   normalized; their values sum past 1 and stay so;
/// - the lap reports (publication clocks, never lap crossings): lap 46 gap
///   15 s at 13:20:49Z, lap 52 9.1 s at 13:30:26Z, lap 58 9.0 s at 13:40:53Z;
///   the last-lap report at 13:46:18Z, never a finish time;
/// - each displayed winner's own last eligible trade before each report:
///   Verstappen 0.95 at 13:19:58Z, 0.909 at 13:29:48Z, 0.999 at 13:40:19Z;
///   Leclerc 0.0829999984 at 13:20:28Z, 0.1612595359 at 13:30:12Z, 0.001 at
///   13:40:33Z; Hamilton 0.002 at 13:19:40Z, 0.002 at 13:30:03Z and NO
///   qualifying quote at lap 58 — his last captured trade, 0.001 at 13:35:12Z,
///   stays in the history with its own clock and is never a recent chance;
/// - the ESPN classification captured 2026-10-12T07:47:00Z — Verstappen 1st,
///   Leclerc 2nd, Antonelli 3rd, Norris 4th, Hamilton 6th — and each
///   contract's own separately retained result (winner: Verstappen Won, the
///   rest Lost; podium: Verstappen, Leclerc and Antonelli Won, Hamilton and
///   Norris Lost). A classification is not a 0/100 quote and a contract
///   result is never read from a position;
/// - a REDUCED SUBSET of each displayed winner's recorded trades from the
///   accepted history reference, NOT the complete journey: per moment the
///   first two trades of the window and the last three before its frame
///   (reference sample indexes in the point ids). An omitted span starts a
///   new run, so no line joins across trades left out here. Before: the final
///   two hours before the start, all hollow, ending at each driver's last
///   pre-race trade. Race moments: from the start to the report, all filled;
///   the pre-race trade is an independent reading, not a drawn point. The
///   final stops at the last trade before the last-lap report (Verstappen
///   13:46:06Z); no result point and no line to now.
///
/// CONSTRUCTED owner input (this layer resolves none of it): the scope, every
/// display word, figure text (the reference `probabilityLabel.ts`), PT clock
/// line (from each sample's own archived time), source word, colour, shape,
/// tick, guide label, observation key, movement word, the race state, the
/// story stream and its order (equal to the reference's own result for each
/// moment; its ranking rule is not ported), the story links and reason words,
/// the reader words, each About, the selected driver pair (the reference's
/// default, Antonelli) and its five-driver window, the originals subset, its
/// labels and grades' words, and every hostile, mismatched or blank case.
final class RacingEventPagePresentation10868Tests: XCTestCase {

    // MARK: Moments

    /// The owner's actual moment: before the start, one of the three lap
    /// reports (0 = lap 46, 1 = lap 52, 2 = lap 58), or the final.
    private enum Moment: Equatable {
        case before
        case lap(Int)
        case final

        var phase: FieldOutlookPhase10868 {
            switch self {
            case .before: .before
            case .lap: .during
            case .final: .final
            }
        }

        var stage: Int? {
            if case .lap(let stage) = self { return stage }
            return nil
        }
    }

    private typealias Chance = (p: Double, figure: String, clock: String)
    private typealias Point = (index: Int, x: Double, p: Double)

    private struct Driver {
        let pairID: String
        let name: String
        let compact: String
        let key: FieldHeadlineKeyShape10868
        let shape: FieldHistoryShape10868
        let tint: Color
        let win: (market: String, outcome: String)
        let podium: (market: String, outcome: String)
        let winBefore: Chance
        let podiumBefore: Chance
        /// Lap 46, 52, 58: the own last eligible trade, or none.
        let recorded: [Chance?]
        /// CONSTRUCTED movement words from the archived raw change, or none.
        let movement: [String?]
        let place: String
        let winResult: String
        let podiumResult: String
    }

    // MARK: Archived clocks (epoch seconds)

    private static let beforeLower = 1_791_712_800.0     // 10:00:00Z — two hours before the start
    private static let beforeUpper = 1_791_719_999.999   // the reference's start minus one millisecond
    private static let startX = 1_791_720_000.0          // 12:00:00Z verified start
    private static let reportX = [1_791_724_849.0, 1_791_725_426.0, 1_791_726_053.0]  // laps 46, 52, 58
    private static let lastLapX = 1_791_726_378.0        // 13:46:18Z last-lap report, not a finish time

    private static let scope = "constructed:f1:singapore-2026:racing-page"
    private static let tradeSource = "Polymarket trade"
    private static let classification = "ESPN classification · captured Oct 12, 12:47 AM PT"
    private static let laps = [46, 52, 58]
    private static let reportClocks = ["Oct 11, 6:20:49 AM PT", "Oct 11, 6:30:26 AM PT", "Oct 11, 6:40:53 AM PT"]
    private static let gaps = ["15.0", "9.1", "9.0"]
    private static let gapSeconds = [15.0, 9.1, 9.0]
    private static let reportIDs = ["block-6acb8cf28f08ac9a3440593b", "block-6acb8f1e8f084a13d13c940d", "block-6acb91b58f084a13d13c9417"]
    private static let unavailable = "Driver unavailable in this update"
    private static let noRecent = "No recent probability"

    // MARK: Drivers — ARCHIVED ids and raw values; figures, clocks and words CONSTRUCTED

    private static let verstappen = Driver(
        pairID: "4665", name: "Max Verstappen", compact: "Verstappen", key: .circle, shape: .circle,
        tint: Color(red: 0.0, green: 0.36, blue: 0.75),
        win: ("5229406", "105026689771335810478914327541724319323338915766526076386906176141135574302746"),
        podium: ("5229633", "110857599143644098992681976807171712355534104947335334189871164576023031815555"),
        winBefore: (0.6499999935, "65%", "Oct 11, 4:59:31 AM PT"),
        podiumBefore: (0.8199999967, "82%", "Oct 11, 4:57:07 AM PT"),
        recorded: [(0.95, "95%", "Oct 11, 6:19:58 AM PT"), (0.909, "90.9%", "Oct 11, 6:29:48 AM PT"),
                   (0.999, "99.9%", "Oct 11, 6:40:19 AM PT")],
        movement: ["+30.0 pp", "+25.9 pp", "+34.9 pp"],
        place: "1st", winResult: "Won", podiumResult: "Won")
    private static let leclerc = Driver(
        pairID: "5498", name: "Charles Leclerc", compact: "Leclerc", key: .diamond, shape: .diamond,
        tint: Color(red: 0.78, green: 0.12, blue: 0.16),
        win: ("5229402", "92443082174901362958213182894863948289679800011664028904195269564952495193793"),
        podium: ("5229629", "81777712267167882804825483696208495691212603231475789493999361725169140070707"),
        winBefore: (0.1399999999, "14%", "Oct 11, 4:59:46 AM PT"),
        podiumBefore: (0.6666666667, "66.7%", "Oct 11, 4:59:00 AM PT"),
        recorded: [(0.0829999984, "8.3%", "Oct 11, 6:20:28 AM PT"), (0.1612595359, "16.1%", "Oct 11, 6:30:12 AM PT"),
                   (0.001, "0.1%", "Oct 11, 6:40:33 AM PT")],
        movement: ["-5.7 pp", "+2.1 pp", "-13.9 pp"],
        place: "2nd", winResult: "Lost", podiumResult: "Won")
    private static let hamilton = Driver(
        pairID: "868", name: "Lewis Hamilton", compact: "Hamilton", key: .square, shape: .square,
        tint: Color(red: 0.35, green: 0.35, blue: 0.38),
        win: ("5229411", "9518453683994039663103190001640433279731056992400699084747973794695685716810"),
        podium: ("5229638", "107223488373792995670853625575479347904333591818058137730381400388579385546848"),
        winBefore: (0.16, "16%", "Oct 11, 4:59:19 AM PT"),
        podiumBefore: (0.609999986, "61%", "Oct 11, 4:58:06 AM PT"),
        recorded: [(0.002, "0.2%", "Oct 11, 6:19:40 AM PT"), (0.002, "0.2%", "Oct 11, 6:30:03 AM PT"), nil],
        movement: ["-15.8 pp", "-15.8 pp", nil],
        place: "6th", winResult: "Lost", podiumResult: "Lost")
    private static let antonelli = Driver(
        pairID: "5829", name: "Kimi Antonelli", compact: "Antonelli", key: .circle, shape: .triangle,
        tint: Color(red: 0.0, green: 0.55, blue: 0.5),
        win: ("5229405", "5696133373196488147875236821860681766749634665413742392928884679633318673226"),
        podium: ("5229632", "93588786206279515298378425874328319850883491696258124247716491516547375534226"),
        winBefore: (0.08, "8%", "Oct 11, 4:59:09 AM PT"),
        podiumBefore: (0.4799998464, "48%", "Oct 11, 4:59:15 AM PT"),
        recorded: [nil, nil, nil], movement: [nil, nil, nil],
        place: "3rd", winResult: "Lost", podiumResult: "Won")
    private static let norris = Driver(
        pairID: "5579", name: "Lando Norris", compact: "Norris", key: .circle, shape: .triangle,
        tint: Color(red: 0.9, green: 0.5, blue: 0.0),
        win: ("5229404", "50434279802004157692776355100568844573677746234993201217816404234694902233906"),
        podium: ("5229631", "91266558960626318800007488387086012785670848799467791981959112065990484864616"),
        winBefore: (0.025, "2.5%", "Oct 11, 4:52:54 AM PT"),
        podiumBefore: (0.2899999884, "29%", "Oct 11, 4:49:21 AM PT"),
        recorded: [nil, nil, nil], movement: [nil, nil, nil],
        place: "4th", winResult: "Lost", podiumResult: "Lost")

    /// The headline, expectations and finish rows, in the owner's order.
    private static let displayed = [verstappen, leclerc, hamilton]
    /// The win/podium window, in the owner's order (pre-race podium chance, as the reference sorts).
    private static let window = [verstappen, leclerc, hamilton, antonelli, norris]

    // MARK: Owner identities and readings

    private static func winRef(_ driver: Driver) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "polymarket", marketID: driver.win.market, outcomeID: driver.win.outcome)
    }

    private static func podiumRef(_ driver: Driver) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "polymarket", marketID: driver.podium.market, outcomeID: driver.podium.outcome)
    }

    private static func winBeforeReading(_ driver: Driver) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Pre-race win", value: .recorded(text: driver.winBefore.figure, detail: "\(driver.winBefore.clock) · \(tradeSource)"))
    }

    private static func podiumBeforeReading(_ driver: Driver) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Pre-race podium", value: .recorded(text: driver.podiumBefore.figure, detail: "\(driver.podiumBefore.clock) · \(tradeSource)"))
    }

    /// The own recorded reading at a report, or the owner's words without a qualifying quote.
    private static func recordedReading(_ driver: Driver, _ stage: Int) -> FieldChooserReading10868 {
        guard let recorded = driver.recorded[stage] else {
            return FieldChooserReading10868(label: "Recorded win", value: .missing(noRecent))
        }
        return FieldChooserReading10868(label: "Recorded win", value: .recorded(text: recorded.figure, detail: "\(recorded.clock) · \(tradeSource)"))
    }

    private static func finishReading(_ driver: Driver) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Actual finish", value: .recorded(text: driver.place, detail: classification))
    }

    /// The one canonical subset for a moment: ten originals, every one an
    /// independent record. A displayed winner carries its recorded reading
    /// during the race; contract results ride only at the final.
    private static func catalogue(_ moment: Moment) -> [FieldChooserOriginal10868] {
        window.flatMap { driver -> [FieldChooserOriginal10868] in
            let winPlan: FieldChooserDisplayPlan10868
            if let stage = moment.stage, displayed.contains(where: { $0.pairID == driver.pairID }) {
                winPlan = .comparison(before: winBeforeReading(driver), later: recordedReading(driver, stage))
            } else {
                winPlan = .single(winBeforeReading(driver))
            }
            let final = moment == .final
            return [
                FieldChooserOriginal10868(
                    ref: winRef(driver), name: driver.name, plan: winPlan,
                    preview: FieldChooserPreview10868(history: nil, absence: "History supplied separately"),
                    movement: nil, clock: nil,
                    result: final ? FieldChooserResult10868(title: "Prop result", words: driver.winResult) : nil,
                    browseStatus: "Race winner", accent: driver.tint),
                FieldChooserOriginal10868(
                    ref: podiumRef(driver), name: driver.name, plan: .single(podiumBeforeReading(driver)),
                    preview: FieldChooserPreview10868(history: nil, absence: "History supplied separately"),
                    movement: nil, clock: nil,
                    result: final ? FieldChooserResult10868(title: "Prop result", words: driver.podiumResult) : nil,
                    browseStatus: "Podium finish", accent: driver.tint),
            ]
        }
    }

    /// The owner's association: the pre-race observation always; a later one,
    /// its movement words and key only at a report with a qualifying quote.
    private static func pair(_ driver: Driver, _ moment: Moment) -> FieldMovementPair10868 {
        let stage = moment.stage
        let later = stage.flatMap { driver.recorded[$0] }
        return FieldMovementPair10868(
            ref: winRef(driver),
            before: FieldMovementObservation10868(probability: driver.winBefore.p, reading: winBeforeReading(driver)),
            later: later.map { FieldMovementObservation10868(probability: $0.p, reading: recordedReading(driver, stage!)) },
            movement: stage.flatMap { driver.movement[$0] },
            observation: later.map { _ in "constructed:\(driver.win.market):lap\(laps[stage!])" })
    }

    private static func winChances() -> [FieldOutlookBeforeChance10868] {
        window.flatMap { driver in
            [FieldOutlookBeforeChance10868(ref: winRef(driver), probability: driver.winBefore.p, reading: winBeforeReading(driver)),
             FieldOutlookBeforeChance10868(ref: podiumRef(driver), probability: driver.podiumBefore.p, reading: podiumBeforeReading(driver))]
        }
    }

    /// Physical classification tied to each winner original; rides in every moment, read only at the final.
    private static let finishes = window.map { FieldFinishPlace10868(ref: winRef($0), reading: finishReading($0)) }

    private static let fullScale = FieldOutlookScale10868(
        ceiling: 1,
        ticks: [FieldOutlookTick10868(probability: 0, label: "0%"), FieldOutlookTick10868(probability: 0.5, label: "50%"),
                FieldOutlookTick10868(probability: 1, label: "100%")],
        words: "0–100% win probability")

    // MARK: Headline

    private static func state(_ moment: Moment) -> FieldHeadlineState10868 {
        switch moment {
        case .before:
            return FieldHeadlineState10868(
                figure: "62 laps", unit: nil, caption: "Scheduled start", detail: "Oct 11, 5:00 AM PT",
                spoken: "62 laps. Scheduled start Oct 11, 5:00 AM PT", progress: nil)
        case .lap(let stage):
            return FieldHeadlineState10868(
                figure: "Lap \(laps[stage])", unit: "/ 62", caption: "Verstappen leads", detail: "Leclerc +\(gaps[stage])s",
                spoken: "Lap \(laps[stage]) of 62, reported \(reportClocks[stage]). Verstappen leads; Leclerc \(gaps[stage]) seconds behind",
                progress: FieldHeadlineProgress10868(completed: Double(laps[stage]), total: 62))
        case .final:
            return FieldHeadlineState10868(
                figure: "62 laps", unit: nil, caption: "Race complete", detail: "Final classification · Oct 11, 2026",
                spoken: "62 laps. Race complete. Final classification, Oct 11, 2026",
                progress: FieldHeadlineProgress10868(completed: 62, total: 62))
        }
    }

    private static func headlineCopy(_ moment: Moment, compact: Bool = false) -> FieldHeadlineCopy10868 {
        let (eyebrow, graphic): (String, String) = switch moment {
        case .before: ("Formula 1 · Before the start", "Pre-race win chances")
        case .lap: ("Formula 1 · Recorded probabilities", "Pre-race and recorded win chances")
        case .final: ("Formula 1 · Final classification", "Pre-race chances and actual finishes")
        }
        return FieldHeadlineCopy10868(
            eyebrow: compact ? nil : eyebrow, title: compact ? nil : "Singapore Grand Prix", graphicLabel: graphic,
            beforeLabel: "Pre-race win", recordedLabel: "Recorded win",
            beforeUnavailable: "Not recorded", recordedUnavailable: noRecent,
            finishLabel: "Actual finish", finishUnavailable: "Finish not reported",
            empty: "No drivers in this update",
            aboutLabel: "About this race", aboutHint: "Opens how this race was recorded",
            openHint: "Opens this driver's win history")
    }

    private static func headline(_ moment: Moment, compact: Bool = false) -> FieldHeadlineInput10868 {
        FieldHeadlineInput10868(
            scope: scope, catalogue: catalogue(moment),
            displayed: displayed.map { FieldHeadlineSlot10868(ref: winRef($0), name: $0.name, compactName: $0.compact, keyShape: $0.key) },
            pairs: displayed.map { pair($0, moment) },
            finishes: finishes,
            state: compact ? nil : state(moment),
            phase: moment.phase, copy: headlineCopy(moment, compact: compact), unavailableWords: unavailable)
    }

    private static func figures(_ input: FieldHeadlineInput10868) -> [[String?]] {
        FieldHeadlineModel10868(input).competitors.map { $0.metrics.map(FieldChaseModel10868.figure) }
    }

    // MARK: History — a labelled subset of each displayed winner's own trades

    private static let verstappenSamples: [String: [Point]] = [
        "before": [(0, 1_791_713_032, 0.6599999992), (1, 1_791_713_122, 0.66)],
        "beforeLast": [(44, 1_791_719_913, 0.649999999), (45, 1_791_719_959, 0.64), (46, 1_791_719_971, 0.6499999935)],
        "start": [(47, 1_791_720_055, 0.6599999843), (48, 1_791_720_079, 0.65)],
        "lap52": [(191, 1_791_725_359, 0.8829999249), (192, 1_791_725_364, 0.909), (193, 1_791_725_388, 0.909)],
        "lap58": [(205, 1_791_725_947, 0.98), (206, 1_791_726_016, 0.999), (207, 1_791_726_019, 0.999)],
        "final": [(213, 1_791_726_325, 0.999), (214, 1_791_726_354, 0.999), (215, 1_791_726_366, 0.999)],
    ]
    private static let leclercSamples: [String: [Point]] = [
        "before": [(0, 1_791_714_552, 0.13), (1, 1_791_714_558, 0.1409359397)],
        "beforeLast": [(24, 1_791_719_955, 0.1299999948), (25, 1_791_719_968, 0.1318851082), (26, 1_791_719_986, 0.1399999999)],
        "start": [(27, 1_791_720_060, 0.149999997), (28, 1_791_720_084, 0.15)],
        "lap52": [(86, 1_791_725_341, 0.081), (87, 1_791_725_365, 0.1199999976), (88, 1_791_725_412, 0.1612595359)],
        "lap58": [(98, 1_791_725_854, 0.0157635468), (99, 1_791_725_970, 0.0015100306), (100, 1_791_726_033, 0.001)],
        "final": [(100, 1_791_726_033, 0.001), (101, 1_791_726_058, 0.001), (102, 1_791_726_225, 0.001)],
    ]
    private static let hamiltonSamples: [String: [Point]] = [
        "before": [(0, 1_791_713_070, 0.1399999832), (1, 1_791_713_109, 0.1417635384)],
        "beforeLast": [(38, 1_791_719_887, 0.16), (39, 1_791_719_941, 0.16), (40, 1_791_719_959, 0.16)],
        "start": [(41, 1_791_720_039, 0.1831325281), (42, 1_791_720_052, 0.1899999962)],
        "lap52": [(124, 1_791_725_274, 0.002), (125, 1_791_725_293, 0.002), (126, 1_791_725_403, 0.002)],
        "lap58": [(128, 1_791_725_548, 0.002), (129, 1_791_725_694, 0.001), (130, 1_791_725_712, 0.001)],
        "final": [(128, 1_791_725_548, 0.002), (129, 1_791_725_694, 0.001), (130, 1_791_725_712, 0.001)],
    ]

    /// Each displayed winner's subset, by pair id.
    private static let samples: [String: [String: [Point]]] = [
        "4665": verstappenSamples, "5498": leclercSamples, "868": hamiltonSamples,
    ]

    /// The last kept trade's figure and PT clock per moment, CONSTRUCTED from its archived value and time.
    private static let lastTrade: [String: [String: (figure: String, clock: String)]] = [
        "4665": ["lap52": ("90.9%", "Oct 11, 6:29:48 AM PT"), "lap58": ("99.9%", "Oct 11, 6:40:19 AM PT"), "final": ("99.9%", "Oct 11, 6:46:06 AM PT")],
        "5498": ["lap52": ("16.1%", "Oct 11, 6:30:12 AM PT"), "lap58": ("0.1%", "Oct 11, 6:40:33 AM PT"), "final": ("0.1%", "Oct 11, 6:43:45 AM PT")],
        "868": ["lap52": ("0.2%", "Oct 11, 6:30:03 AM PT"), "lap58": ("0.1%", "Oct 11, 6:35:12 AM PT"), "final": ("0.1%", "Oct 11, 6:35:12 AM PT")],
    ]

    /// The retained moments this subset covers: lap 46 is not prepared.
    private static func frameKey(_ moment: Moment) -> String {
        switch moment {
        case .before: "beforeLast"
        case .lap(let stage): stage == 2 ? "lap58" : "lap52"
        case .final: "final"
        }
    }

    private static func seriesID(_ driver: Driver) -> String { "polymarket:\(driver.win.market):\(driver.win.outcome)" }
    private static func pointID(_ driver: Driver, _ index: Int) -> String { "\(seriesID(driver))#\(index)" }

    private static func runs(_ driver: Driver, _ moment: Moment) -> [FieldHistoryRun10868] {
        let own = samples[driver.pairID]!
        let spans = moment == .before ? [own["before"]!, own["beforeLast"]!] : [own["start"]!, own[frameKey(moment)]!]
        return spans.enumerated().map { index, points in
            FieldHistoryRun10868(id: "\(seriesID(driver))#subset-run-\(index + 1)", points: points.map {
                FieldHistoryPoint10868(id: pointID(driver, $0.index), x: $0.x, probability: $0.p,
                                       style: moment == .before ? .hollow : .filled)
            })
        }
    }

    private static func historySeries(_ driver: Driver, _ moment: Moment) -> FieldHistorySeries10868 {
        let preRace = "Last pre-race · \(driver.winBefore.clock) · \(tradeSource)"
        let before: FieldHistoryReading10868 = moment == .before
            ? .observation(pointID: pointID(driver, samples[driver.pairID]!["beforeLast"]!.last!.index),
                           figure: driver.winBefore.figure, provenance: preRace)
            : .independent(figure: driver.winBefore.figure, provenance: preRace)
        var recorded = FieldHistoryReading10868.absent(words: "No race trades yet")
        if moment != .before, let last = samples[driver.pairID]![frameKey(moment)]!.last,
           let shown = lastTrade[driver.pairID]![frameKey(moment)] {
            recorded = .observation(pointID: pointID(driver, last.index), figure: shown.figure,
                                    provenance: "Last trade · \(shown.clock) · \(tradeSource)")
        }
        return FieldHistorySeries10868(
            id: seriesID(driver), name: driver.name, shape: driver.shape, tint: driver.tint,
            runs: runs(driver, moment), links: [], labelPointID: nil, before: before, recorded: recorded,
            absentWords: "No recorded trades",
            choose: FieldHistoryAction10868(id: "history.choose.\(driver.pairID)", label: driver.compact,
                                            spokenLabel: "Inspect \(driver.name) win probability", isAvailable: true))
    }

    private static func upper(_ moment: Moment) -> Double {
        switch moment {
        case .before: beforeUpper
        case .lap(let stage): reportX[stage]
        case .final: lastLapX
        }
    }

    /// Report guides at or before the frame; none before the start.
    private static func guides(_ moment: Moment) -> [FieldHistoryGuide10868] {
        let all = [FieldHistoryGuide10868(id: reportIDs[0], x: reportX[0], label: "L46"),
                   FieldHistoryGuide10868(id: reportIDs[1], x: reportX[1], label: "L52"),
                   FieldHistoryGuide10868(id: reportIDs[2], x: reportX[2], label: "L58"),
                   FieldHistoryGuide10868(id: "block-6acb92e38f08ac9a34405972", x: lastLapX, label: "L62 report")]
        return moment == .before ? [] : all.filter { $0.x <= upper(moment) }
    }

    private static func action(_ id: String, _ label: String, spoken: String? = nil) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: spoken, isAvailable: true)
    }

    private static func history(_ moment: Moment) -> FieldHistoryInput10868 {
        let before = moment == .before
        let lower = before ? beforeLower : startX
        let caption = switch moment {
        case .before: "Final 2 hours before the start"
        case .lap(let stage): "Race start → lap \(laps[stage]) report"
        case .final: "Race start → last-lap report"
        }
        let lastTick = switch moment {
        case .before: "Start"
        case .lap(let stage): stage == 2 ? "6:40 AM" : "6:30 AM"
        case .final: "6:46 AM"
        }
        return FieldHistoryInput10868(
            title: "Win probability", caption: caption,
            series: displayed.map { historySeries($0, moment) },
            selection: .series(id: seriesID(verstappen), missingWords: unavailable),
            domain: FieldHistoryDomain10868(lower: lower, upper: upper(moment)), ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.5, lines: ["50%"]),
                     FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: [FieldHistoryTick10868(value: lower, lines: [before ? "3:00 AM" : "5:00 AM"]),
                     FieldHistoryTick10868(value: upper(moment), lines: [lastTick])],
            guides: guides(moment), breaks: [],
            readout: before ? .singleBefore(label: "Pre-race trade")
                : .beforeAndRecorded(beforeLabel: "Last pre-race", recordedLabel: "Last recorded trade"),
            markKey: before ? FieldHistoryMarkKey10868(hollow: "Hollow · pre-race trade", filled: nil)
                : FieldHistoryMarkKey10868(hollow: nil, filled: "Filled · race trade"),
            comparisonExplanation: nil,
            notes: ["Lap markers are report publication times, not exact lap crossings.",
                    "A reduced subset of recorded trades; omitted spans are not joined."],
            summary: "Verstappen circles, Leclerc diamonds, Hamilton squares. Recorded win probability, zero to one hundred percent.",
            plotHeight: 260, unboundReadingWords: "Not recorded", plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: action("history.details", "History source and timing"),
            expand: action("history.expand", "Full chart", spoken: "Expand race probability chart"),
            inspect: nil, previous: nil, next: nil, inspection: nil)
    }

    // MARK: Story leaves

    private static let podiumCopy = FieldPodiumCopy10868(
        title: "Win and podium chances", explanation: "Podium means finishing in the top three.",
        beforeContext: "Pre-race chances", duringContext: "Pre-race chances · No recent update",
        finalContext: "Pre-race chances and reported finish", winLabel: "Win", podiumLabel: "Finish top 3",
        beforeLabel: "Pre-race", pairUnavailable: "Driver pairing unavailable in this update",
        chanceUnavailable: "Pre-race chance unavailable", noSelection: "Choose a driver",
        outsideWindow: "Selected driver is outside this group", finishLabel: "Reported finish",
        finishUnavailable: "Finish not confirmed", resultLabel: "Prop result", resultUnknown: "Result unconfirmed",
        previousLabel: "Previous driver", nextLabel: "Next driver", chooseHint: "Show this driver's two chances",
        originalHint: "Open this exact original prop", aboutLabel: "About the pre-race comparison",
        aboutHint: "Read observation sources and times")

    private static func winPodium(_ moment: Moment, phase: FieldOutlookPhase10868? = nil) -> FieldPodiumInput10868 {
        FieldPodiumInput10868(
            scope: scope, catalogue: catalogue(moment),
            pairs: window.map { FieldPodiumPair10868(id: $0.pairID, name: $0.name, win: winRef($0), podium: podiumRef($0)) },
            displayed: window.map { FieldPodiumSlot10868(pairID: $0.pairID, name: $0.name, compactName: $0.compact) },
            selectedID: antonelli.pairID, previousID: hamilton.pairID, nextID: norris.pairID,
            chances: winChances(), finishes: finishes, scale: fullScale, phase: phase ?? moment.phase,
            winTint: Color(red: 0.0, green: 0.36, blue: 0.75), podiumTint: Color(red: 0.78, green: 0.12, blue: 0.16),
            copy: podiumCopy)
    }

    private static func expectations(_ moment: Moment, phase: FieldOutlookPhase10868? = nil) -> FieldExpectationsInput10868 {
        FieldExpectationsInput10868(
            scope: scope, catalogue: catalogue(moment),
            displayed: displayed.map { FieldFinishSlot10868(ref: winRef($0), name: $0.name) },
            pairs: displayed.map { pair($0, moment) }, scale: fullScale, phase: phase ?? moment.phase,
            copy: FieldExpectationsCopy10868(
                eyebrow: "Pre-race → recorded chance", title: "How expectations shifted",
                context: "Recorded at different times", key: "Hollow = pre-race · solid = recorded",
                graphicLabel: "Pre-race and recorded win chances on one 0 to 100 percent scale",
                beforeLabel: "Pre-race win", recordedLabel: "Recorded win", beforeUnavailable: "Not recorded",
                recordedUnavailable: noRecent, offScale: "Above this scale", openLabel: "Win history",
                openHint: "Opens this driver's recorded win history"),
            unavailableWords: unavailable)
    }

    private static func report(_ stage: Int) -> FieldChaseReport10868 {
        FieldChaseReport10868(id: reportIDs[stage], lap: Double(laps[stage]), seconds: gapSeconds[stage], reading: FieldChooserReading10868(
            label: "Lap \(laps[stage])", value: .recorded(text: "\(gaps[stage]) sec", detail: "Reported \(reportClocks[stage]) · Guardian lap report")))
    }

    private static let chaseAxis = FieldChaseAxis10868(
        lapLower: 46, lapUpper: 58,
        lapTicks: [FieldChaseTick10868(value: 46, label: "L46"), FieldChaseTick10868(value: 52, label: "L52"), FieldChaseTick10868(value: 58, label: "L58")],
        secondsLower: 0, secondsUpper: 20,
        secondsTicks: [FieldChaseTick10868(value: 0, label: "0s"), FieldChaseTick10868(value: 10, label: "10s"), FieldChaseTick10868(value: 20, label: "20s")])

    private static func chase(_ moment: Moment, phase: FieldOutlookPhase10868? = nil) -> FieldChaseInput10868 {
        let stage = moment.stage ?? 1
        let headline = stage == 0 ? "15 seconds behind" : stage == 1 ? "5.9 seconds closer" : "6.0 seconds closer"
        return FieldChaseInput10868(
            scope: scope, catalogue: catalogue(moment),
            challenger: FieldFinishSlot10868(ref: winRef(leclerc), name: leclerc.name),
            pairs: [pair(leclerc, moment)],
            gap: FieldChaseGap10868(
                headline: headline,
                current: FieldChooserReading10868(label: "Reported gap · lap \(laps[stage])",
                                                  value: .recorded(text: gaps[stage], detail: "Reported \(reportClocks[stage]) · Guardian lap report")),
                runs: [(0...stage).map { report($0) }], highlighted: reportIDs[stage], axis: chaseAxis),
            phase: phase ?? moment.phase,
            copy: FieldChaseCopy10868(
                eyebrow: stage == 0 ? "Leclerc chasing Verstappen" : "Leclerc chasing Verstappen · since lap 46",
                currentUnit: "sec", gapUnavailable: "Gap not reported in this update",
                graphicLabel: "Reported gap behind Verstappen, seconds, zero to twenty. Smaller means closer.",
                caption: "Gap behind the leader · smaller is closer. Only reported laps are shown.",
                pointUnavailable: "Not shown on this scale", highlightWords: "This report",
                chancesLabel: "Pre-race and recorded win chances", beforeLabel: "Pre-race win", recordedLabel: "Recorded win",
                beforeUnavailable: "Not recorded", recordedUnavailable: noRecent,
                openLabel: "Leclerc's win history", openHint: "Opens this driver's recorded win history"),
            unavailableWords: unavailable)
    }

    private static func finish(_ moment: Moment, phase: FieldOutlookPhase10868? = nil) -> FieldFinishInput10868 {
        FieldFinishInput10868(
            scope: scope, catalogue: catalogue(moment), selected: nil,
            displayed: displayed.map { FieldFinishSlot10868(ref: winRef($0), name: $0.name) },
            finishes: finishes,
            chances: displayed.map { FieldOutlookBeforeChance10868(ref: winRef($0), probability: $0.winBefore.p, reading: winBeforeReading($0)) },
            scale: fullScale, phase: phase ?? moment.phase,
            copy: FieldFinishCopy10868(
                title: "The race, resolved", context: "Win chance before the start · finish from the classification",
                scaleLabel: "Pre-race win chance", graphicLabel: "Pre-race chances and actual finishes",
                finishLabel: "Actual finish", finishUnit: "finish", finishUnavailable: "Finish not confirmed",
                chanceUnavailable: "Pre-race chance unavailable", offScale: "Above the 100% scale",
                outsideDisplayed: "Selected driver is outside this group", empty: "No finishing positions captured",
                count: nil, openPrompt: "Tap a driver for their history.", openHint: "Open this driver's win history"),
            unavailableWords: unavailable)
    }

    // MARK: Stream and page

    private static func streamScope(_ moment: Moment) -> String {
        switch moment {
        case .before: "race-live-moment:before"
        case .lap(let stage): "race-live-moment:lap\(laps[stage])"
        case .final: "race-live-moment:final"
        }
    }

    /// The owner's stream for a moment. Its order equals the reference's own
    /// result for that moment; the rule that produced it is not ported.
    private static func stream(_ moment: Moment, wide: Bool = false) -> StoryStreamPresentation10868 {
        let scope = streamScope(moment)
        func ref(_ id: String) -> StoryStreamPresentation10868.CardRef { .init(scope: scope, id: id) }
        let podium = StoryStreamPresentation10868.Card(id: "win-podium", name: "Win or podium")
        switch moment {
        case .before:
            return StoryStreamPresentation10868(
                scope: scope, eyebrow: nil, heading: "Before the race", cards: [podium],
                primary: ref("win-podium"), companion: nil, companionLabel: nil, wide: wide, position: "1 of 1")
        case .lap:
            return StoryStreamPresentation10868(
                scope: scope, eyebrow: nil, heading: "Race stories",
                cards: [StoryStreamPresentation10868.Card(id: "chase", name: "Leclerc’s chase"),
                        StoryStreamPresentation10868.Card(id: "shifts", name: "Expectations"), podium],
                primary: ref("chase"), companion: ref("shifts"), companionLabel: "Next", wide: wide,
                position: "1 of 3", status: "Cards advance when you’re watching",
                dwellFraction: 0.4, playback: .pause, previous: ref("win-podium"), next: ref("shifts"))
        case .final:
            return StoryStreamPresentation10868(
                scope: scope, eyebrow: nil, heading: "After the race",
                cards: [podium, StoryStreamPresentation10868.Card(id: "finish", name: "Expectation and finish")],
                primary: ref("win-podium"), companion: ref("finish"), companionLabel: "Next", wide: wide,
                position: "1 of 2", previous: nil, next: ref("finish"))
        }
    }

    private static func stories(_ moment: Moment) -> [RacingEventPageStory10868] {
        let stage = moment.stage ?? 1
        let shifts = stage == 2 ? "Verstappen’s win chance rose 34.9 points from pre-race." : "Verstappen’s win chance rose 25.9 points from pre-race."
        let chase = stage == 2 ? "Leclerc trails by 9.0 seconds at the lap 58 report." : "Leclerc closed 5.9 seconds since the lap 46 report."
        return [RacingEventPageStory10868(cardID: "win-podium", card: .winPodium),
                RacingEventPageStory10868(cardID: "shifts", card: .expectations, reason: shifts),
                RacingEventPageStory10868(cardID: "chase", card: .chase, reason: chase),
                RacingEventPageStory10868(cardID: "finish", card: .finish)]
    }

    private static func readerHeader(_ moment: Moment) -> RacingEventPageReaderHeader10868 {
        switch moment {
        case .before: RacingEventPageReaderHeader10868(title: "Singapore · Before the race", state: "62 laps · Oct 11, 5:00 AM PT")
        case .lap(let stage): RacingEventPageReaderHeader10868(title: "Singapore · Lap \(laps[stage])/62 report",
                                                               state: "Verstappen leads · Leclerc +\(gaps[stage])s")
        case .final: RacingEventPageReaderHeader10868(title: "Singapore · Final", state: "Verstappen won · 62 laps")
        }
    }

    private static let raceAbout = RacingEventPageAbout10868(title: "Recorded race, separate clocks", paragraphs: [
        "Singapore Grand Prix, October 11, 2026. Lap numbers and the gap behind the leader come from timestamped reports. Publication times are not exact lap crossings.",
        "Lines show Polymarket trades for three exact winner contracts, through the selected report. Values are independently timed; they are not normalized or claimed to be a synchronized blend.",
        "Final classification is shown separately from contract settlement and historically recorded chances. The final chart stops at the last-lap report; no 0/100 result point is appended.",
    ])

    private static let winPodiumAbout = RacingEventPageAbout10868(title: "How to read this comparison", paragraphs: [
        "4 of 5 paired drivers in this group. Arrows visit every paired driver; every original remains in All props.",
        "Hollow marks are pre-race trades for two separate markets. They are independently timed; the connecting line is a visual comparison, not a combined probability.",
        "Win: Oct 11, 4:59:09 AM PT. Podium: Oct 11, 4:59:15 AM PT.",
    ])

    private static let copy = RacingEventPageCopy10868(
        storiesLabel: "Race stories",
        storyUnavailable: "This story isn’t available for this race moment. Every original is still in All props.",
        headlineUnavailable: "Race headline unavailable for this moment",
        allPropsLabel: "All 75 original outcomes")

    /// One coherent snapshot. `extras` carries every story payload in every
    /// moment, so the page's phase rule — not the fixture — hides the rest.
    private static func page(_ moment: Moment, wide: Bool = false,
                             headline: FieldHeadlineInput10868? = nil,
                             chase: FieldChaseInput10868?? = nil,
                             expectations: FieldExpectationsInput10868?? = nil,
                             stories: [RacingEventPageStory10868]? = nil,
                             raceAbout: RacingEventPageAbout10868?? = nil) -> RacingEventPageInput10868 {
        RacingEventPageInput10868(
            phase: moment.phase, reader: readerHeader(moment),
            headline: headline ?? Self.headline(moment), history: history(moment),
            winPodium: winPodium(moment),
            expectations: expectations ?? Self.expectations(moment, phase: .during),
            chase: chase ?? Self.chase(moment, phase: .during),
            finish: finish(moment, phase: .final),
            readerChances: RacingEventPageReaderChances10868(
                heading: moment == .final ? "Race results and pre-race chances" : "Race win chances",
                headline: Self.headline(moment, compact: true)),
            stream: stream(moment, wide: wide), stories: stories ?? Self.stories(moment),
            raceAbout: raceAbout ?? Self.raceAbout, winPodiumAbout: winPodiumAbout, copy: copy)
    }

    private static func activation(_ stream: StoryStreamPresentation10868, _ id: String,
                                   log: @escaping (String) -> Void) -> StoryStreamCardActivation10868 {
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: id)
        return StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
            if case .interaction(_, let card) = intent { log("hold:\(card?.id ?? "-")") } else { log("other") }
        }
    }

    // MARK: Phases

    @MainActor
    func testBeforeTheStartMountsTheHeadlineHistoryAndWinPodiumOnlyAndLaterInputsStayHidden() {
        let input = Self.page(.before)
        let view = RacingEventPagePresentation10868(input: input)
        XCTAssertEqual(view.mode, .page)
        XCTAssertEqual(view.headlineContent()?.input, input.headline)
        XCTAssertEqual(view.historyContent(reader: false).input, input.history)
        XCTAssertEqual(view.winPodiumContent()?.input, input.winPodium)
        // The expectations, chase and finish payloads ride along; the phase rule hides them.
        XCTAssertNotNil(input.expectations)
        XCTAssertNotNil(input.chase)
        XCTAssertNotNil(input.finish)
        XCTAssertNil(view.expectationsContent())
        XCTAssertNil(view.chaseContent())
        XCTAssertNil(view.finishContent())

        // Pre-race chances only, hollow keys, no progress — the finishes in the packet are not read.
        let headline = FieldHeadlineModel10868(input.headline)
        XCTAssertEqual(Self.figures(input.headline), [["65%"], ["14%"], ["16%"]])
        XCTAssertTrue(headline.keyIsHollow)
        XCTAssertNil(headline.progress)
        XCTAssertEqual(headline.state?.caption, "Scheduled start")

        // Win and podium: each original's own pre-race chance; no finish or result before the start.
        let podium = FieldPodiumModel10868(input.winPodium!)
        guard let selected = podium.selected else { return XCTFail("selected pair") }
        XCTAssertEqual(selected.slot.name, "Kimi Antonelli")
        XCTAssertEqual([selected.win?.reading, selected.podium?.reading].compactMap { $0.flatMap(FieldChaseModel10868.figure) }, ["8%", "48%"])
        XCTAssertNil(podium.selectedFinish)
        XCTAssertNil(podium.result(selected.win))

        // History: the final two hours before the start, every mark hollow,
        // ending at each driver's own last pre-race trade; no report guide.
        let history = input.history
        XCTAssertEqual(history.domain, FieldHistoryDomain10868(lower: Self.beforeLower, upper: Self.beforeUpper))
        XCTAssertEqual(history.guides, [])
        XCTAssertEqual(history.series.map { $0.runs.map(\.points.count) }, [[2, 3], [2, 3], [2, 3]])
        XCTAssertTrue(history.series.allSatisfy { $0.runs.flatMap(\.points).allSatisfy { $0.style == .hollow } })
        XCTAssertEqual(history.series.map { $0.runs.last?.points.last?.probability }, [0.6499999935, 0.1399999999, 0.16])
        XCTAssertTrue(history.series.allSatisfy { $0.runs.flatMap(\.points).allSatisfy { $0.x < Self.startX } })
        XCTAssertEqual(history.readout, .singleBefore(label: "Pre-race trade"))

        // Only the win/podium story resolves before the start.
        let model = RacingEventPageModel10868(input)
        XCTAssertEqual(model.storyCard("win-podium"), .winPodium)
        XCTAssertNil(model.storyCard("shifts"))
        XCTAssertNil(model.storyCard("chase"))
        XCTAssertNil(model.storyCard("finish"))
    }

    @MainActor
    func testAtTheLap52ReportEveryDuringLeafMountsWithItsOwnChancesGapAndClocks() {
        let input = Self.page(.lap(1))
        let view = RacingEventPagePresentation10868(input: input)
        XCTAssertEqual(view.headlineContent()?.input, input.headline)
        XCTAssertEqual(view.historyContent(reader: false).input, input.history)
        XCTAssertEqual(view.winPodiumContent()?.input, input.winPodium)
        XCTAssertEqual(view.expectationsContent()?.input, input.expectations)
        XCTAssertEqual(view.chaseContent()?.input, input.chase)
        XCTAssertNil(view.finishContent(), "The finish payload rides along; only the final mounts it")

        // Each driver's own pre-race and recorded chance; the state keeps its report clock.
        XCTAssertEqual(Self.figures(input.headline), [["65%", "90.9%"], ["14%", "16.1%"], ["16%", "0.2%"]])
        let headline = FieldHeadlineModel10868(input.headline)
        XCTAssertEqual(FieldChaseModel10868.detail(headline.competitors[0].metrics[1]), "Oct 11, 6:29:48 AM PT · Polymarket trade")
        XCTAssertEqual(headline.state?.figure, "Lap 52")
        XCTAssertEqual(headline.state?.detail, "Leclerc +9.1s")
        XCTAssertTrue(headline.state?.spoken.contains("Oct 11, 6:30:26 AM PT") == true)
        XCTAssertEqual(headline.progress, FieldHeadlineProgress10868(completed: 52, total: 62))

        // The chase: the physical gap beside its own report clock, Leclerc's two chances apart.
        let chase = FieldChaseModel10868(view.chaseContent()!.input)
        XCTAssertEqual(chase.headline, "5.9 seconds closer")
        XCTAssertEqual(chase.current, FieldChooserReading10868(label: "Reported gap · lap 52",
                                                               value: .recorded(text: "9.1", detail: "Reported Oct 11, 6:30:26 AM PT · Guardian lap report")))
        XCTAssertEqual(chase.readouts.map(FieldChaseModel10868.figure), ["14%", "16.1%"])
        XCTAssertEqual(chase.reports.map(\.lap), [46, 52])
        XCTAssertEqual(chase.highlightedID, Self.reportIDs[1])
        XCTAssertFalse(chase.reports.contains { $0.lap == 58 }, "No later report in an earlier moment")

        // Expectations: three independent pairs, never normalized (they sum past 1).
        let expectations = FieldExpectationsModel10868(view.expectationsContent()!.input)
        XCTAssertEqual(expectations.rows.map { expectations.readouts($0).map(FieldChaseModel10868.figure) },
                       [["65%", "90.9%"], ["14%", "16.1%"], ["16%", "0.2%"]])
        XCTAssertEqual(expectations.rows.map { expectations.movementWords($0) }, ["+25.9 pp", "+2.1 pp", "-15.8 pp"])

        // Win and podium during the race: still each original's pre-race chance; no result.
        let podium = FieldPodiumModel10868(input.winPodium!)
        XCTAssertNil(podium.selectedFinish)
        XCTAssertNil(podium.result(podium.selected?.podium))

        // History: race start to the lap 52 report; the pre-race trade is an
        // independent reading; each recorded reading binds to its own last trade.
        let history = input.history
        XCTAssertEqual(history.domain, FieldHistoryDomain10868(lower: Self.startX, upper: Self.reportX[1]))
        XCTAssertEqual(history.guides.map(\.label), ["L46", "L52"])
        XCTAssertTrue(history.guides.allSatisfy { $0.x <= history.domain.upper })
        XCTAssertEqual(history.series.map(\.before), [
            .independent(figure: "65%", provenance: "Last pre-race · Oct 11, 4:59:31 AM PT · Polymarket trade"),
            .independent(figure: "14%", provenance: "Last pre-race · Oct 11, 4:59:46 AM PT · Polymarket trade"),
            .independent(figure: "16%", provenance: "Last pre-race · Oct 11, 4:59:19 AM PT · Polymarket trade"),
        ])
        XCTAssertEqual(history.series[1].recorded, .observation(pointID: Self.pointID(Self.leclerc, 88), figure: "16.1%",
                                                                 provenance: "Last trade · Oct 11, 6:30:12 AM PT · Polymarket trade"))
        XCTAssertEqual(history.series.map { $0.runs.last?.points.last?.probability }, [0.909, 0.1612595359, 0.002])
        XCTAssertTrue(history.series.allSatisfy { $0.runs.flatMap(\.points).allSatisfy { $0.style == .filled && $0.x >= Self.startX } })

        // The owner's stories: chase, then expectations, then win/podium.
        let model = RacingEventPageModel10868(input)
        XCTAssertEqual(input.stream.cards.map { model.storyCard($0.id) }, [.chase, .expectations, .winPodium])
        XCTAssertNil(model.storyCard("finish"))
        XCTAssertEqual(model.story("chase")?.reason, "Leclerc closed 5.9 seconds since the lap 46 report.")
    }

    @MainActor
    func testAtTheFinalPreRaceChancesMeetTheClassificationAndContractResultsStayApart() {
        let input = Self.page(.final)
        let view = RacingEventPagePresentation10868(input: input)
        XCTAssertEqual(view.headlineContent()?.input, input.headline)
        XCTAssertEqual(view.winPodiumContent()?.input, input.winPodium)
        XCTAssertEqual(view.finishContent()?.input, input.finish)
        XCTAssertNil(view.expectationsContent())
        XCTAssertNil(view.chaseContent())

        // The headline: pre-race chance beside the physical finish — never a settled 100%/0%.
        XCTAssertEqual(Self.figures(input.headline), [["65%", "1st"], ["14%", "2nd"], ["16%", "6th"]])
        let headlineFigures = Self.figures(input.headline).flatMap { $0 }.compactMap { $0 }
        XCTAssertFalse(headlineFigures.contains("100%"))
        XCTAssertFalse(headlineFigures.contains("0%"))

        // The finish card: each driver's pre-race chance beside the classification.
        let finish = FieldFinishModel10868(view.finishContent()!.input)
        XCTAssertTrue(finish.isShown)
        XCTAssertEqual(finish.rows.map { FieldFinishModel10868.ordinal(finish.finish(for: $0.slot.ref)) }, ["1st", "2nd", "6th"])
        XCTAssertEqual(finish.rows.map { finish.figure($0) }, ["65%", "14%", "16%"])

        // Win and podium: Antonelli finished 3rd; his win contract Lost and his
        // podium contract Won — each its own retained result, never read from the position.
        let podium = FieldPodiumModel10868(input.winPodium!)
        guard let selected = podium.selected else { return XCTFail("selected pair") }
        XCTAssertEqual(podium.selectedFinish.flatMap(FieldChaseModel10868.figure), "3rd")
        XCTAssertEqual(podium.result(selected.win)?.words, "Lost")
        XCTAssertEqual(podium.result(selected.podium)?.words, "Won")
        XCTAssertEqual([selected.win?.reading, selected.podium?.reading].compactMap { $0.flatMap(FieldChaseModel10868.figure) }, ["8%", "48%"])

        // The history stops at the last trade before the last-lap report:
        // no result point, nothing at 0% or 100%, no line to now.
        let history = input.history
        XCTAssertEqual(history.domain, FieldHistoryDomain10868(lower: Self.startX, upper: Self.lastLapX))
        XCTAssertEqual(history.series[0].runs.last?.points.last?.x, 1_791_726_366)
        XCTAssertLessThan(history.series.compactMap { $0.runs.last?.points.last?.x }.max()!, Self.lastLapX)
        XCTAssertFalse(history.series.flatMap { $0.runs.flatMap(\.points) }.contains { $0.probability == 0 || $0.probability == 1 })
        XCTAssertEqual(history.guides.map(\.label), ["L46", "L52", "L58", "L62 report"])
        XCTAssertEqual(history.series[0].recorded, .observation(pointID: Self.pointID(Self.verstappen, 215), figure: "99.9%",
                                                                 provenance: "Last trade · Oct 11, 6:46:06 AM PT · Polymarket trade"))

        let model = RacingEventPageModel10868(input)
        XCTAssertEqual(input.stream.cards.map { model.storyCard($0.id) }, [.winPodium, .finish])
    }

    @MainActor
    func testAtLap58HamiltonsStaleTradeStaysHistoryAndTheHeadlineSaysNoRecentProbability() {
        let input = Self.page(.lap(2))
        let view = RacingEventPagePresentation10868(input: input)

        // The headline and expectations: no recent figure for Hamilton, his pre-race chance kept.
        XCTAssertEqual(Self.figures(input.headline), [["65%", "99.9%"], ["14%", "0.1%"], ["16%", nil]])
        let hamilton = FieldHeadlineModel10868(input.headline).competitors[2]
        XCTAssertEqual(FieldChaseModel10868.words(hamilton.metrics[1]), "No recent probability")
        let expectations = FieldExpectationsModel10868(view.expectationsContent()!.input)
        XCTAssertEqual(expectations.readouts(expectations.rows[2]).map(FieldChaseModel10868.figure), ["16%", nil])
        XCTAssertNil(expectations.movementWords(expectations.rows[2]))

        // The history keeps his last captured trade with its own clock, as history.
        let series = input.history.series[2]
        XCTAssertEqual(series.runs.last?.points.last?.x, 1_791_725_712)
        XCTAssertEqual(series.recorded, .observation(pointID: Self.pointID(Self.hamilton, 130), figure: "0.1%",
                                                     provenance: "Last trade · Oct 11, 6:35:12 AM PT · Polymarket trade"))
        XCTAssertEqual(input.history.readout, .beforeAndRecorded(beforeLabel: "Last pre-race", recordedLabel: "Last recorded trade"))

        // The chase at lap 58: the gap held, Leclerc's own recorded chance at its own clock.
        let chase = FieldChaseModel10868(view.chaseContent()!.input)
        XCTAssertEqual(chase.current?.label, "Reported gap · lap 58")
        XCTAssertEqual(chase.readouts.map(FieldChaseModel10868.figure), ["14%", "0.1%"])
        XCTAssertEqual(RacingEventPageModel10868(input).story("chase")?.reason, "Leclerc trails by 9.0 seconds at the lap 58 report.")
    }

    @MainActor
    func testALeafFromAnotherPhaseIsNotMountedAndAStoryResolvesOnlyItsOneExactLink() {
        // A chase or expectations input admitted for another phase is not
        // coerced into this one, and a headline from another phase is not drawn.
        let mismatched = RacingEventPagePresentation10868(input: Self.page(
            .lap(1), headline: Self.headline(.final),
            chase: .some(Self.chase(.lap(1), phase: .final)),
            expectations: .some(Self.expectations(.lap(1), phase: .before))))
        XCTAssertNil(mismatched.headlineContent())
        XCTAssertNil(mismatched.chaseContent())
        XCTAssertNil(mismatched.expectationsContent())
        XCTAssertEqual(mismatched.input.copy.headlineUnavailable, "Race headline unavailable for this moment")
        let model = RacingEventPageModel10868(mismatched.input)
        XCTAssertFalse(model.isMounted(.chase))
        XCTAssertNil(model.storyCard("chase"))
        XCTAssertFalse(model.readerShows(.chase))
        XCTAssertNil(model.readerChances(for: .chase))
        XCTAssertNotNil(model.storyCard("win-podium"), "Its neighbours keep theirs")

        // A win/podium input from another phase is not mounted either.
        let base = Self.page(.final)
        let podiumMismatch = RacingEventPageInput10868(
            phase: .final, reader: base.reader, headline: base.headline, history: base.history,
            winPodium: Self.winPodium(.final, phase: .during), expectations: nil, chase: nil, finish: base.finish,
            readerChances: base.readerChances, stream: base.stream, stories: base.stories,
            raceAbout: base.raceAbout, winPodiumAbout: base.winPodiumAbout, copy: base.copy)
        XCTAssertNil(RacingEventPagePresentation10868(input: podiumMismatch).winPodiumContent())
        XCTAssertNotNil(RacingEventPagePresentation10868(input: podiumMismatch).finishContent())

        // Stories resolve only by exactly one link to a mounted story; never the anchor, never a neighbour.
        let ambiguous = RacingEventPageModel10868(Self.page(.lap(1), stories: [
            RacingEventPageStory10868(cardID: "chase", card: .chase),
            RacingEventPageStory10868(cardID: "chase", card: .expectations),
            RacingEventPageStory10868(cardID: "chart", card: .history),
            RacingEventPageStory10868(cardID: "finish", card: .finish),
            RacingEventPageStory10868(cardID: "shifts", card: .expectations),
        ]))
        XCTAssertNil(ambiguous.storyCard("chase"))
        XCTAssertNil(ambiguous.storyCard("chart"))
        XCTAssertNil(ambiguous.storyCard("finish"), "Linked, but not a story of this phase")
        XCTAssertNil(ambiguous.storyCard("Shifts"))
        XCTAssertEqual(ambiguous.storyCard("shifts"), .expectations)
        XCTAssertNil(ambiguous.storyCard("win-podium"), "No link: no story")
    }

    // MARK: Stream wiring

    @MainActor
    func testAStreamCardActionRequestsTheHoldBeforeTheExactOwnerCallbackAndNothingFiresPassively() {
        var log: [String] = []
        let open = { (ref: FieldChooserOriginalRef10868) in ref.marketID }
        func callbacks(_ input: RacingEventPageInput10868, mode: RacingEventPageMode10868 = .page) -> RacingEventPagePresentation10868 {
            RacingEventPagePresentation10868(
                input: input, mode: mode,
                onAbout: { log.append("about:\($0.rawValue)") },
                onAllProps: { log.append("allProps") },
                onStoryIntent: { _ in log.append("stream") },
                onHeadlineOpen: { log.append("headline:\($0.ref.marketID)") },
                onHistoryAction: { log.append("history:\($0)") },
                onHistoryInspectionChoice: { log.append("inspect:\($0)") },
                onHistoryPlotPosition: { log.append("plot:\($0)") },
                onWinPodiumChoosePair: { log.append("pair:\($0)") },
                onWinPodiumOpenOriginal: { log.append("original:\(open($0))") },
                onExpectationsOpen: { log.append("expectations:\($0.ref.marketID):\($0.observation ?? "-")") },
                onChaseOpenHistory: { log.append("chase:\(open($0))") },
                onFinishOpenHistory: { log.append("finish:\(open($0))") })
        }

        // Lap 52, wide: the chase is primary and expectations the companion.
        let live = Self.page(.lap(1), wide: true)
        let view = callbacks(live)
        let chaseHook = Self.activation(live.stream, "chase") { log.append($0) }
        let shiftsHook = Self.activation(live.stream, "shifts") { log.append($0) }
        XCTAssertTrue(chaseHook.isAvailable)
        XCTAssertTrue(shiftsHook.isAvailable)

        // Building every leaf, in stream, page and reader form, acts on nothing.
        let chase = view.chaseContent(activation: chaseHook)!
        let expectations = view.expectationsContent(activation: shiftsHook)!
        _ = view.headlineContent()
        _ = view.historyContent(reader: false)
        _ = view.historyContent(reader: true)
        _ = view.winPodiumContent()
        _ = view.readerChancesContent(.chase)
        _ = view.aboutContent(.race)
        XCTAssertEqual(log, [])

        // In the stream: the hold first, then the exact owner action.
        chase.onOpenHistory?(Self.winRef(Self.leclerc))
        expectations.onOpen?(FieldMovementOpen10868(ref: Self.winRef(Self.hamilton), observation: "constructed:5229411:lap52"))
        XCTAssertEqual(log, ["hold:chase", "chase:5229402",
                             "hold:shifts", "expectations:5229411:constructed:5229411:lap52"])

        // The final, wide: win/podium primary and the finish companion.
        log = []
        let final = Self.page(.final, wide: true)
        let finalView = callbacks(final)
        let podiumHook = Self.activation(final.stream, "win-podium") { log.append($0) }
        let finishHook = Self.activation(final.stream, "finish") { log.append($0) }
        let podium = finalView.winPodiumContent(activation: podiumHook)!
        let finish = finalView.finishContent(activation: finishHook)!
        XCTAssertEqual(log, [])
        podium.onChoosePair?(Self.leclerc.pairID)
        podium.onOpenOriginal?(Self.podiumRef(Self.antonelli))
        podium.onAbout?()
        finish.onOpenHistory?(Self.winRef(Self.verstappen))
        XCTAssertEqual(log, ["hold:win-podium", "pair:5498", "hold:win-podium", "original:5229632",
                             "hold:win-podium", "about:winPodium", "hold:finish", "finish:5229406"])

        // Full-size content, the headline and the anchor: the exact callback, no hold.
        log = []
        callbacks(final, mode: .reader(.winPodium)).winPodiumContent()?.onChoosePair?(Self.norris.pairID)
        callbacks(live, mode: .reader(.chase)).chaseContent()?.onOpenHistory?(Self.winRef(Self.leclerc))
        view.headlineContent()?.onOpen?(FieldMovementOpen10868(ref: Self.winRef(Self.verstappen), observation: nil))
        view.headlineContent()?.onAbout?()
        view.historyContent(reader: false).onAction?("history.expand")
        view.historyContent(reader: true).onAction?("history.details")
        view.historyContent(reader: false).onInspectionChoice?("choice.193")
        view.historyContent(reader: false).onPlotPosition?(Self.reportX[0])
        view.openAllProps()
        XCTAssertEqual(log, ["pair:5579", "chase:5229402", "headline:5229406", "about:race", "history:history.expand",
                             "history:history.details", "inspect:choice.193", "plot:\(Self.reportX[0])", "allProps"])

        // Without host callbacks nothing acts, even inside the stream.
        log = []
        let quiet = RacingEventPagePresentation10868(input: final)
        XCTAssertNil(quiet.winPodiumContent(activation: podiumHook)?.onChoosePair)
        XCTAssertNil(quiet.winPodiumContent(activation: podiumHook)?.onOpenOriginal)
        XCTAssertNil(quiet.winPodiumContent(activation: podiumHook)?.onAbout)
        XCTAssertNil(quiet.finishContent(activation: finishHook)?.onOpenHistory)
        XCTAssertNil(quiet.headlineContent()?.onAbout)
        XCTAssertNil(quiet.headlineContent()?.onOpen)
        XCTAssertNil(quiet.historyContent(reader: false).onAction)
        XCTAssertNil(RacingEventPagePresentation10868(input: live).chaseContent(activation: chaseHook)?.onOpenHistory)
        quiet.openAllProps()
        quiet.openAbout(.race)
        XCTAssertEqual(log, [])
    }

    @MainActor
    func testThePageHookHoldsOnceBeforeEachPageActionAndNeverForReadersStreamCardsOrPassiveReads() {
        var log: [String] = []
        func hooked(_ input: RacingEventPageInput10868, mode: RacingEventPageMode10868 = .page,
                    hook: Bool = true) -> RacingEventPagePresentation10868 {
            RacingEventPagePresentation10868(
                input: input, mode: mode,
                onAbout: { log.append("about:\($0.rawValue)") },
                onAllProps: { log.append("allProps") },
                onStoryIntent: { _ in log.append("stream") },
                onHeadlineOpen: { log.append("headline:\($0.ref.marketID)") },
                onHistoryAction: { log.append("history:\($0)") },
                onHistoryInspectionChoice: { log.append("inspect:\($0)") },
                onHistoryPlotPosition: { log.append("plot:\($0)") },
                onExpectationsOpen: { log.append("expectations:\($0.ref.marketID)") },
                onChaseOpenHistory: { log.append("chase:\($0.marketID)") },
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        // Building and reading the page's leaves calls neither the hook nor an owner.
        let live = Self.page(.lap(1), wide: true)
        let view = hooked(live)
        let headline = view.headlineContent()!
        let anchor = view.historyContent(reader: false)
        _ = view.historyContent(reader: true)
        _ = view.readerChancesContent(.chase)
        _ = view.aboutContent(.race)
        XCTAssertEqual(log, [])

        // On the page: the hook once, then the exact owner callback with its exact value.
        headline.onOpen?(FieldMovementOpen10868(ref: Self.winRef(Self.verstappen), observation: nil))
        headline.onAbout?()
        anchor.onAction?("history.expand")
        anchor.onInspectionChoice?("choice.193")
        anchor.onPlotPosition?(Self.reportX[0])
        view.openAllProps()
        XCTAssertEqual(log, ["hold", "headline:5229406", "hold", "about:race", "hold", "history:history.expand",
                             "hold", "inspect:choice.193", "hold", "plot:\(Self.reportX[0])", "hold", "allProps"])

        // Full-size content — the history reader, a story reader, the race
        // About in the compact heading — keeps the exact callbacks: its host holds.
        log = []
        let reader = hooked(live, mode: .reader(.history))
        reader.historyContent(reader: true).onAction?("history.details")
        reader.openAbout(.race)
        hooked(live, mode: .reader(.chase)).chaseContent()?.onOpenHistory?(Self.winRef(Self.leclerc))
        XCTAssertEqual(log, ["history:history.details", "about:race", "chase:5229402"])

        // Stream cards: the stream's own activation once, never the page hook as well.
        log = []
        let chaseHook = Self.activation(live.stream, "chase") { log.append($0) }
        let shiftsHook = Self.activation(live.stream, "shifts") { log.append($0) }
        view.chaseContent(activation: chaseHook)?.onOpenHistory?(Self.winRef(Self.leclerc))
        view.expectationsContent(activation: shiftsHook)?
            .onOpen?(FieldMovementOpen10868(ref: Self.winRef(Self.hamilton), observation: "constructed:5229411:lap52"))
        XCTAssertEqual(log, ["hold:chase", "chase:5229402", "hold:shifts", "expectations:5229411"])

        // No owner callback: no action and no hook call.
        log = []
        let silent = RacingEventPagePresentation10868(input: live, onInteraction: { log.append("hold") })
        XCTAssertNil(silent.headlineContent()?.onOpen)
        XCTAssertNil(silent.headlineContent()?.onAbout)
        XCTAssertNil(silent.historyContent(reader: false).onAction)
        XCTAssertNil(silent.historyContent(reader: false).onInspectionChoice)
        XCTAssertNil(silent.historyContent(reader: false).onPlotPosition)
        silent.openAllProps()
        XCTAssertEqual(log, [])

        // No hook: each page callback is the owner's own, exactly as before.
        let plain = hooked(live, hook: false)
        plain.headlineContent()?.onOpen?(FieldMovementOpen10868(ref: Self.winRef(Self.verstappen), observation: nil))
        plain.historyContent(reader: false).onAction?("history.expand")
        plain.openAllProps()
        XCTAssertEqual(log, ["headline:5229406", "history:history.expand", "allProps"])
    }

    // MARK: Readers

    @MainActor
    func testTheFullSizeHistoryDropsOnlyItsExpandControlAndChaseAndPodiumReadersKeepTheOwnersChances() {
        for moment in [Moment.before, .lap(1), .final] {
            let input = Self.page(moment)
            let view = RacingEventPagePresentation10868(input: input, mode: .reader(.history))
            XCTAssertEqual(view.historyContent(reader: false).input.expand?.id, "history.expand")
            let reader = view.historyContent(reader: true).input
            XCTAssertNil(reader.expand)
            XCTAssertEqual(reader.layout, .expanded)
            let page = Mirror(reflecting: input.history).children.map { ($0.label ?? "", String(describing: $0.value)) }
            let full = Mirror(reflecting: reader).children.map { ($0.label ?? "", String(describing: $0.value)) }
            XCTAssertEqual(page.map(\.0), full.map(\.0))
            for (owner, shown) in zip(page, full) where owner.0 != "expand" && owner.0 != "layout" {
                XCTAssertEqual(owner.1, shown.1, "\(moment) \(owner.0)")
            }
            XCTAssertEqual(FieldHistoryGeometry10868.actions(reader).map(\.id),
                           FieldHistoryGeometry10868.actions(input.history).map(\.id).filter { $0 != "history.expand" })
            XCTAssertNil(RacingEventPageModel10868(input).readerChances(for: .history), "The history reader carries no chances context")
        }

        // The chase and win/podium readers carry the owner's compact chances at the page's phase.
        let live = Self.page(.lap(1))
        let liveModel = RacingEventPageModel10868(live)
        XCTAssertEqual(liveModel.readerChances(for: .chase)?.heading, "Race win chances")
        XCTAssertEqual(liveModel.readerChances(for: .winPodium), live.readerChances)
        XCTAssertNil(liveModel.readerChances(for: .expectations))
        let chances = RacingEventPagePresentation10868(input: live, mode: .reader(.chase), onAbout: { _ in })
            .readerChancesContent(.chase)
        XCTAssertEqual(chances?.input, live.readerChances?.headline)
        XCTAssertNil(chances?.onAbout, "Static context: no control")
        XCTAssertNil(chances?.onOpen)
        let compact = FieldHeadlineModel10868(live.readerChances!.headline)
        XCTAssertNil(compact.eyebrow)
        XCTAssertNil(compact.title)
        XCTAssertNil(compact.state)
        XCTAssertEqual(Self.figures(live.readerChances!.headline), [["65%", "90.9%"], ["14%", "16.1%"], ["16%", "0.2%"]])

        let final = RacingEventPageModel10868(Self.page(.final))
        XCTAssertEqual(final.readerChances(for: .winPodium)?.heading, "Race results and pre-race chances")
        XCTAssertEqual(Self.figures(final.readerChances(for: .winPodium)!.headline), [["65%", "1st"], ["14%", "2nd"], ["16%", "6th"]])
        XCTAssertNil(final.readerChances(for: .chase), "No chase at the final")

        // A compact headline from another phase is not drawn under a reader.
        let base = Self.page(.lap(1))
        let stale = RacingEventPageModel10868(RacingEventPageInput10868(
            phase: .during, reader: base.reader, headline: base.headline, history: base.history, winPodium: base.winPodium,
            expectations: base.expectations, chase: base.chase, finish: base.finish,
            readerChances: RacingEventPageReaderChances10868(heading: "Race win chances", headline: Self.headline(.before, compact: true)),
            stream: base.stream, stories: base.stories, raceAbout: base.raceAbout, winPodiumAbout: base.winPodiumAbout, copy: base.copy))
        XCTAssertNil(stale.readerChances(for: .chase))

        // Each phase's readers: the anchor and each story it shows; nothing else.
        XCTAssertEqual(RacingEventPageCard10868.allCases.filter { RacingEventPageModel10868(Self.page(.before)).readerShows($0) },
                       [.history, .winPodium])
        XCTAssertEqual(RacingEventPageCard10868.allCases.filter { liveModel.readerShows($0) },
                       [.history, .winPodium, .expectations, .chase])
        XCTAssertEqual(RacingEventPageCard10868.allCases.filter { final.readerShows($0) },
                       [.history, .winPodium, .finish])
        XCTAssertEqual(live.reader, RacingEventPageReaderHeader10868(title: "Singapore · Lap 52/62 report",
                                                                     state: "Verstappen leads · Leclerc +9.1s"))
    }

    // MARK: About

    @MainActor
    func testEachAboutOpensOnlyThroughItsOwnReadableEntryAndItsContentActsOnNothing() {
        var log: [String] = []
        let input = Self.page(.lap(1))
        let view = RacingEventPagePresentation10868(input: input, onAbout: { log.append("about:\($0.rawValue)") })

        // The headline's control opens the race About; the win/podium card's opens its own.
        XCTAssertNotNil(view.headlineContent()?.onAbout)
        XCTAssertNotNil(view.winPodiumContent()?.onAbout)
        view.headlineContent()?.onAbout?()
        view.winPodiumContent()?.onAbout?()
        XCTAssertEqual(log, ["about:race", "about:winPodium"])

        // Each About content is the owner's text verbatim and acts on nothing.
        log = []
        XCTAssertEqual(view.aboutContent(.race)?.about, Self.raceAbout)
        XCTAssertEqual(view.aboutContent(.winPodium)?.about, Self.winPodiumAbout)
        XCTAssertEqual(Mirror(reflecting: view.aboutContent(.race)!).children.map(\.label), ["about"])
        _ = RacingEventPagePresentation10868(input: input, mode: .about(.race), onAbout: { log.append("about:\($0.rawValue)") })
            .aboutContent(.race)
        XCTAssertEqual(log, [])

        // The readers' compact heading offers the race About; the page relies
        // on the headline's own control; other modes show none.
        let model = RacingEventPageModel10868(input)
        for card in RacingEventPageCard10868.allCases {
            XCTAssertTrue(model.aboutEntry(mode: .reader(card), canOpen: true), "\(card)")
        }
        for mode in [RacingEventPageMode10868.page, .catalogue, .original, .about(.race), .about(.winPodium)] {
            XCTAssertFalse(model.aboutEntry(mode: mode, canOpen: true), "\(mode)")
        }
        XCTAssertFalse(model.aboutEntry(mode: .reader(.chase), canOpen: false))

        // No About text, or only blank words: no control, nothing to open.
        let blank = RacingEventPagePresentation10868(
            input: Self.page(.lap(1), raceAbout: .some(RacingEventPageAbout10868(title: " ", paragraphs: ["", "  "]))),
            onAbout: { log.append("about:\($0.rawValue)") })
        XCTAssertNil(blank.headlineContent()?.onAbout)
        XCTAssertNil(blank.aboutContent(.race))
        XCTAssertFalse(RacingEventPageModel10868(blank.input).aboutEntry(mode: .reader(.chase), canOpen: true))
        blank.openAbout(.race)
        let none = RacingEventPagePresentation10868(input: Self.page(.lap(1), raceAbout: .some(nil)),
                                                    onAbout: { log.append("about:\($0.rawValue)") })
        XCTAssertNil(none.headlineContent()?.onAbout)
        XCTAssertNotNil(none.winPodiumContent()?.onAbout, "The other topic keeps its own entry")
        XCTAssertEqual(log, [])
        view.openAbout(.race)
        XCTAssertEqual(log, ["about:race"])
    }

    // MARK: Arrangement

    func testCompactWideAndAccessibilitySizesChooseTheirArrangements() {
        XCTAssertEqual(RacingEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(RacingEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(RacingEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(RacingEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertEqual(RacingEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: true), [.stacked])

        // Every name and absence word survives whole in the inputs the leaves
        // measure, and the history keeps the owner's plot height unchanged.
        let input = Self.page(.lap(2))
        XCTAssertEqual(input.headline.displayed.map(\.name), ["Max Verstappen", "Charles Leclerc", "Lewis Hamilton"])
        XCTAssertEqual(input.headline.displayed.map(\.compactName), ["Verstappen", "Leclerc", "Hamilton"])
        XCTAssertEqual(input.headline.displayed.map(\.keyShape), [.circle, .diamond, .square])
        XCTAssertEqual(input.history.series.map(\.shape), [.circle, .diamond, .square])
        XCTAssertEqual(RacingEventPageModel10868(input).readerHistory.plotHeight, input.history.plotHeight)
        XCTAssertEqual(input.history.plotHeight, 260)
    }
}

// MARK: - All props and the selected original's Details

/// The catalogue and Details content modes, made of the existing
/// `OriginalMarketCatalogueView9483` and `OriginalMarketDetailsView9483`:
/// those actual leaves are mounted with the owner's originals group and exact
/// callbacks unchanged, and each original keeps its own pre-race chance,
/// in-race trade and grade apart.
///
/// A SMALL, explicitly labelled SUBSET of the 75 retained originals — NOT the
/// catalogue obligation; it proves no full native fit and no family filter:
/// - Max Verstappen, winner (5229406): pre-race 0.6499999935 at 11:59:31Z;
///   last captured race trade 0.909 at 13:29:48Z at the lap 52 report;
///   contract Won;
/// - Charles Leclerc, podium (5229629): pre-race 0.6666666667 at 11:59:00Z; no
///   captured race trade; contract Won;
/// - Lewis Hamilton, podium (5229638): pre-race 0.609999986 at 11:58:06Z; no
///   captured race trade; contract Lost (he finished 6th);
/// - Alonso vs Stroll, Alonso side (5229600): pre-race 0.75 at 11:17:33Z; no
///   captured race trade; contract Won.
/// Rules are the first paragraph of each original's retained rule text.
/// CONSTRUCTED: scope, labels, figure text, grade words, heading, context and tint.
/// Also CONSTRUCTED: the category controls (the reference's four labels —
/// Winner, Podium, Matchups, Fastest lap — with constructed ids, selection and
/// an unavailable Fastest lap), the count words and Show more words, which are
/// not count claims about the retained catalogue, and each category's admitted
/// rows: the owner admits them; this layer never filters or pages.
@MainActor
extension RacingEventPagePresentation10868Tests {
    private typealias Originals = OriginalMarketDetails9483

    private static let verstappenWin = Originals.Identity(source: "polymarket", market: "5229406", side: "105026689771335810478914327541724319323338915766526076386906176141135574302746")
    private static let leclercPodium = Originals.Identity(source: "polymarket", market: "5229629", side: "81777712267167882804825483696208495691212603231475789493999361725169140070707")
    private static let hamiltonPodium = Originals.Identity(source: "polymarket", market: "5229638", side: "107223488373792995670853625575479347904333591818058137730381400388579385546848")
    private static let alonsoStroll = Originals.Identity(source: "polymarket", market: "5229600", side: "110909128388621583528027995078471646758296891348314740700292566482823861330730")

    private static let winnerRule = "This is a polymarket on the winner of the 2026 F1 Singapore Grand Prix, scheduled for Oct 11, 2026."
    private static let podiumRule = "This market will resolve to “Yes” if the listed driver finishes within the top three positions in the official \"Final Classification\" for the F1 Singapore Grand Prix, scheduled for Oct 11, 2026. Otherwise, this market will resolve to “No.”"
    private static let matchupRule = "This market will resolve according to the driver who finishes ahead of the other at the F1 Singapore Grand Prix, scheduled for Oct 11, 2026."

    private static func originalsScope(_ phase: FieldOutlookPhase10868) -> String { "\(scope):originals:\(phase)" }

    private static func original(_ identity: Originals.Identity, title: String, outcome: String,
                                 pregame: Originals.Reading, later: Originals.Reading, grade: String,
                                 rule: String, phase: FieldOutlookPhase10868) -> Originals.Original {
        Originals.Original(
            identity: identity, title: title, outcome: outcome,
            mode: phase == .final ? .result : phase == .during ? .comparison(.recorded) : .pregame,
            pregame: pregame, later: phase == .during ? later : nil,
            grade: phase == .final ? Originals.Grade(words: grade, provenance: "Retained contract result") : nil,
            about: Originals.About(source: "Polymarket", rules: .verified([rule]),
                                   provenance: [Originals.Row(label: "Market ID", value: identity.market)],
                                   historicalQuote: nil))
    }

    /// `admitting` is the owner's admitted rows for its current category and
    /// page (nil: all four); `controls` the owner's controls around them.
    private static func originals(_ phase: FieldOutlookPhase10868,
                                  holding held: Originals.Identity? = RacingEventPagePresentation10868Tests.verstappenWin,
                                  admitting: [Originals.Identity]? = nil,
                                  controls: RacingEventPageCatalogueControls10868? = nil)
        -> RacingEventPageOriginals10868 {
        let notRecorded = Originals.Reading.missing("Not recorded")
        let rows = [
            original(verstappenWin, title: "Singapore Grand Prix: Driver Winner", outcome: "Max Verstappen",
                     pregame: .value("65%", placement: 0.6499999935, provenance: "Oct 11, 4:59:31 AM PT · Polymarket trade"),
                     later: .value("90.9%", placement: 0.909, provenance: "Last captured race trade · Oct 11, 6:29:48 AM PT · Polymarket"),
                     grade: "Won", rule: winnerRule, phase: phase),
            original(leclercPodium, title: "Singapore Grand Prix: Driver Podium Finish", outcome: "Charles Leclerc",
                     pregame: .value("66.7%", placement: 0.6666666667, provenance: "Oct 11, 4:59:00 AM PT · Polymarket trade"),
                     later: notRecorded, grade: "Won", rule: podiumRule, phase: phase),
            original(hamiltonPodium, title: "Singapore Grand Prix: Driver Podium Finish", outcome: "Lewis Hamilton",
                     pregame: .value("61%", placement: 0.609999986, provenance: "Oct 11, 4:58:06 AM PT · Polymarket trade"),
                     later: notRecorded, grade: "Lost", rule: podiumRule, phase: phase),
            original(alonsoStroll, title: "Singapore Grand Prix: Head-to-Head", outcome: "Alonso — Alonso vs Stroll",
                     pregame: .value("75%", placement: 0.75, provenance: "Oct 11, 4:17:33 AM PT · Polymarket trade"),
                     later: notRecorded, grade: "Won", rule: matchupRule, phase: phase),
        ]
        let scope = originalsScope(phase)
        let admitted = admitting.map { ids in ids.compactMap { id in rows.first { $0.identity == id } } } ?? rows
        return RacingEventPageOriginals10868(
            catalogue: Originals.Catalogue(scope: scope, originals: admitted),
            selection: held.map { Originals.Selection(scope: scope, identity: $0) },
            labels: [verstappenWin: "Max Verstappen · Win", leclercPodium: "Charles Leclerc · Podium",
                     hamiltonPodium: "Lewis Hamilton · Podium", alonsoStroll: "Alonso vs Stroll · Alonso"],
            heading: "All props", context: "75 retained originals",
            emptyWords: "No retained originals for this race", unavailableChoice: "Unnamed original",
            tint: Color(red: 0.0, green: 0.36, blue: 0.75), controls: controls)
    }

    private static func category(_ id: String, _ label: String, selected: Bool = false,
                                 available: Bool = true) -> RacingEventPageCatalogueCategory10868 {
        RacingEventPageCatalogueCategory10868(
            action: FieldHistoryAction10868(id: id, label: label, spokenLabel: nil, isAvailable: available),
            isSelected: selected)
    }

    /// The reference's four categories with the owner's selection.
    private static func controls(selected: String) -> RacingEventPageCatalogueControls10868 {
        let families = [("winner", "Winner"), ("podium", "Podium"), ("matchup", "Matchups"), ("fastest", "Fastest lap")]
        return RacingEventPageCatalogueControls10868(
            categoriesLabel: "Race market category",
            categories: families.map { family in
                category("category.\(family.0)", family.1, selected: family.0 == selected, available: family.0 != "fastest")
            },
            more: action("catalogue.more", "Show more · 3 remaining", spoken: "Show more podium outcomes, 3 remaining"),
            context: "Showing 2 of 5 podium outcomes")
    }

    private static func cards(_ view: OriginalMarketCatalogueView9483) -> [OriginalMarketCatalogue9483.Card] {
        OriginalMarketCatalogue9483.cards(catalogue: view.catalogue, selection: view.selection,
                                          labels: view.labels, unavailableChoice: view.unavailableChoice)
    }

    func testAllPropsAndDetailsMountTheExistingOriginalLeavesWithEachOriginalsOwnReadingsAndGrades() {
        var log: [String] = []
        let originals = Self.originals(.during)
        let view = RacingEventPagePresentation10868(
            input: Self.page(.lap(1)), mode: .catalogue, originals: originals,
            onOriginalSelect: { log.append("select:\($0.identity.market)") },
            onOriginalHistory: { log.append("history:\($0.actionID)") })
        let catalogue = view.catalogueContent()!
        let details = view.originalDetailsContent()!
        XCTAssertEqual(catalogue.catalogue, originals.catalogue)
        XCTAssertEqual(catalogue.selection, originals.selection)
        XCTAssertEqual(details.catalogue, originals.catalogue)
        XCTAssertNil(details.recorded)

        // One card per supplied original, in the owner's order, each with its own readings.
        let cards = Self.cards(catalogue)
        XCTAssertEqual(cards.map(\.choice.label), ["Max Verstappen · Win", "Charles Leclerc · Podium",
                                                   "Lewis Hamilton · Podium", "Alonso vs Stroll · Alonso"])
        XCTAssertEqual(cards.map { $0.content!.readings.map(\.text) },
                       [["65%", "90.9%"], ["66.7%", "Not recorded"], ["61%", "Not recorded"], ["75%", "Not recorded"]])
        let held = Originals.content(catalogue: details.catalogue, selection: details.selection)!
        XCTAssertEqual(held.readings.map(\.label), ["Pregame chance", "Recorded chance"])
        XCTAssertEqual(held.rules, .verified([Self.winnerRule]))
        XCTAssertEqual(log, [], "Entering either mode selects nothing and opens no history")

        // A card tap hands the owner the exact scope and identity.
        for card in cards { OriginalMarketCatalogue9483.action(card, onSelect: catalogue.onSelect)?() }
        XCTAssertEqual(log, ["select:5229406", "select:5229629", "select:5229638", "select:5229600"])

        // Final: each separately retained grade beside its own pre-race chance —
        // Hamilton's podium Lost, Leclerc's podium Won, never read from a position.
        func shown(_ identity: Originals.Identity) -> Originals.Content? {
            let final = RacingEventPagePresentation10868(input: Self.page(.final), mode: .original,
                                                         originals: Self.originals(.final, holding: identity))
            let mounted = final.originalDetailsContent()!
            return Originals.content(catalogue: mounted.catalogue, selection: mounted.selection)
        }
        XCTAssertEqual(shown(Self.verstappenWin)?.result?.words, "Won")
        XCTAssertEqual(shown(Self.verstappenWin)?.readings.map(\.text), ["65%"])
        XCTAssertEqual(shown(Self.hamiltonPodium)?.result?.words, "Lost")
        XCTAssertEqual(shown(Self.leclercPodium)?.result?.words, "Won")

        // No callbacks: static; no originals group: no content.
        let quiet = RacingEventPagePresentation10868(input: Self.page(.lap(1)), mode: .catalogue, originals: originals)
        XCTAssertNil(quiet.catalogueContent()?.onSelect)
        XCTAssertNil(quiet.originalDetailsContent()?.onHistory)
        XCTAssertNil(RacingEventPagePresentation10868(input: Self.page(.lap(1)), mode: .catalogue).catalogueContent())
        XCTAssertNil(RacingEventPagePresentation10868(input: Self.page(.lap(1)), mode: .original).originalDetailsContent())
    }

    func testCatalogueControlsSelectionAndDetailsHistoryHoldOnceThenHandTheOwnerItsExactIntent() {
        var log: [String] = []
        // The owner's Podium category: it admitted the two podium originals, holding Leclerc's.
        let originals = Self.originals(.during, holding: Self.leclercPodium,
                                       admitting: [Self.leclercPodium, Self.hamiltonPodium],
                                       controls: Self.controls(selected: "podium"))
        func view(_ mode: RacingEventPageMode10868, hook: Bool = true, callbacks: Bool = true) -> RacingEventPagePresentation10868 {
            RacingEventPagePresentation10868(
                input: Self.page(.lap(1)), mode: mode, originals: originals,
                onOriginalSelect: callbacks ? { log.append("select:\($0.identity.market)") } : nil,
                onOriginalHistory: callbacks ? { log.append("history:\($0.actionID)") } : nil,
                onCatalogueCategory: callbacks ? { log.append("category:\($0)") } : nil,
                onCatalogueMore: callbacks ? { log.append("more:\($0)") } : nil,
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        // Building and reading the catalogue, its controls and Details calls nothing.
        let catalogue = view(.catalogue)
        let mounted = catalogue.catalogueContent()!
        let details = view(.original).originalDetailsContent()!
        let controls = originals.controls!
        let categories = controls.categories.map { catalogue.categoryAction($0) }
        let more = catalogue.moreAction()
        XCTAssertEqual(log, [])

        // Each live control: the hook once, then the owner's exact intent id.
        // The selected category stays the owner's to act on; the unavailable one does not act.
        categories[0]?()
        categories[1]?()
        categories[2]?()
        XCTAssertNil(categories[3])
        more?()
        XCTAssertEqual(log, ["hold", "category:category.winner", "hold", "category:category.podium",
                             "hold", "category:category.matchup", "hold", "more:catalogue.more"])

        // A card selection and a Details history control: the hook once, then the exact selection and intent.
        log = []
        for card in Self.cards(mounted) { OriginalMarketCatalogue9483.action(card, onSelect: mounted.onSelect)?() }
        let intent = Originals.HistoryIntent(selection: originals.selection!, entry: .explore, actionID: "original.history.explore")
        details.onHistory?(intent)
        XCTAssertEqual(log, ["hold", "select:5229629", "hold", "select:5229638", "hold", "history:original.history.explore"])

        // The admitted rows, their order and scope, and the held original reach
        // the leaf unchanged: a category intent filters, pages, clears and elects nothing.
        XCTAssertEqual(mounted.catalogue, originals.catalogue)
        XCTAssertEqual(mounted.catalogue?.originals.map(\.identity), [Self.leclercPodium, Self.hamiltonPodium])
        XCTAssertEqual(mounted.catalogue?.scope, Self.originalsScope(.during))
        XCTAssertEqual(mounted.selection, Originals.Selection(scope: Self.originalsScope(.during), identity: Self.leclercPodium))
        XCTAssertEqual(Self.cards(mounted).map(\.choice.label), ["Charles Leclerc · Podium", "Lewis Hamilton · Podium"])
        XCTAssertEqual(Self.cards(mounted).map(\.choice.isSelected), [true, false])
        XCTAssertEqual(catalogue.catalogueContent()?.selection, mounted.selection, "Still held after the category intents")
        XCTAssertEqual(mounted.heading, "All props")
        XCTAssertEqual(mounted.context, "75 retained originals")

        // No owner callbacks: no action and no hook call; the controls stay words.
        log = []
        let quiet = view(.catalogue, callbacks: false)
        XCTAssertNil(quiet.catalogueContent()?.onSelect)
        XCTAssertNil(view(.original, callbacks: false).originalDetailsContent()?.onHistory)
        XCTAssertTrue(controls.categories.allSatisfy { quiet.categoryAction($0) == nil })
        XCTAssertNil(quiet.moreAction())
        XCTAssertEqual(log, [])

        // No hook: the exact owner callbacks, as before.
        let plain = view(.catalogue, hook: false)
        plain.categoryAction(controls.categories[0])?()
        plain.moreAction()?()
        for card in Self.cards(mounted) { OriginalMarketCatalogue9483.action(card, onSelect: plain.catalogueContent()?.onSelect)?() }
        XCTAssertEqual(log, ["category:category.winner", "more:catalogue.more", "select:5229629", "select:5229638"])
    }

    func testCatalogueControlStatesAreTheOwnersAndTheCategoriesWrapOnPhoneAndStackAtAccessibilitySizes() {
        typealias Model = RacingEventPageModel10868
        let controls = Self.controls(selected: "podium")

        // Live only with a callback and when available; static otherwise. Selected is the owner's flag.
        XCTAssertEqual(controls.categories.map { Model.catalogueControlState($0.action, in: controls, hasCallback: true) },
                       [.live(id: "category.winner"), .live(id: "category.podium"), .live(id: "category.matchup"), .shownStatic])
        XCTAssertEqual(controls.categories.map { Model.catalogueControlState($0.action, in: controls, hasCallback: false) },
                       [.shownStatic, .shownStatic, .shownStatic, .shownStatic])
        XCTAssertEqual(controls.categories.map(\.isSelected), [false, true, false, false])
        XCTAssertEqual(Model.shownCategories(controls, hasCallback: false).map(\.action.label),
                       ["Winner", "Podium", "Matchups", "Fastest lap"])
        XCTAssertEqual(Model.catalogueControlState(controls.more, in: controls, hasCallback: true), .live(id: "catalogue.more"))
        XCTAssertEqual(Model.catalogueControlState(controls.more, in: controls, hasCallback: false), .shownStatic)
        XCTAssertEqual(Model.readable(controls.context), "Showing 2 of 5 podium outcomes")

        // Blank words draw no invisible control; a shared or empty id is static words, never a guess.
        let hostile = RacingEventPageCatalogueControls10868(
            categoriesLabel: "Race market category",
            categories: [Self.category("category.winner", "Winner", selected: true),
                         Self.category("category.blank", "  "),
                         Self.category("category.twin", "Podium"),
                         Self.category("category.twin", "Matchups"),
                         Self.category("", "Fastest lap")],
            more: Self.action("catalogue.more", " "), context: " ")
        let shown = Model.shownCategories(hostile, hasCallback: true)
        XCTAssertEqual(shown.map(\.action.label), ["Winner", "Podium", "Matchups", "Fastest lap"])
        XCTAssertEqual(shown.map { Model.catalogueControlState($0.action, in: hostile, hasCallback: true) },
                       [.live(id: "category.winner"), .shownStatic, .shownStatic, .shownStatic])
        XCTAssertEqual(Model.catalogueControlState(hostile.more, in: hostile, hasCallback: true), .hidden)
        XCTAssertNil(Model.readable(hostile.context))

        var log: [String] = []
        let view = RacingEventPagePresentation10868(
            input: Self.page(.lap(1)), mode: .catalogue, originals: Self.originals(.during, controls: hostile),
            onCatalogueCategory: { log.append("category:\($0)") }, onCatalogueMore: { log.append("more:\($0)") },
            onInteraction: { log.append("hold") })
        hostile.categories.forEach { view.categoryAction($0)?() }
        view.moreAction()?()
        XCTAssertEqual(log, ["hold", "category:category.winner"])

        // No controls supplied: nothing to act on, and the catalogue is unchanged.
        let bare = RacingEventPagePresentation10868(input: Self.page(.lap(1)), mode: .catalogue,
                                                    originals: Self.originals(.during),
                                                    onCatalogueMore: { log.append("more:\($0)") },
                                                    onInteraction: { log.append("hold") })
        XCTAssertNil(bare.moreAction())
        XCTAssertEqual(bare.catalogueContent()?.catalogue, Self.originals(.during).catalogue)
        XCTAssertEqual(log, ["hold", "category:category.winner"])

        // The arrangement the view switches on: an adaptive wrapping grid, one per row at accessibility sizes.
        XCTAssertEqual(Model.categoryArrangement(accessibilitySize: false), .wrapping)
        XCTAssertEqual(Model.categoryArrangement(accessibilitySize: true), .stacked)
    }
}
