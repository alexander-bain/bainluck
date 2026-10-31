import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the horse-racing page (`horse-racing`) composed from the shared
/// leaves and its picks and catalogue leaves.
///
/// PREPARED / NOT RUN. The views are SwiftUI and are not rasterised here. What
/// is asserted is the composition: which leaf each phase mounts and with which
/// exact owner input, the before and live isolation of every finish, report and
/// settlement word across every reachable output, the schedule kept apart from
/// any actual clock, isolated trades with no synthetic endpoint, the missing
/// pre-schedule chances (Goodie Two Shoes included), the selected observation
/// in its distinct, equal-valued, same and missing forms, the five known
/// finishes, the unknowns and Other, all 25 rows and 50 Yes/No actions across
/// the owner's groups on one scale, unresolved rows, the callbacks and the
/// once-only hold, the full-size inputs and the layout plans. Each shared
/// leaf's own rules stay with its own tests; nothing here claims a compile, a
/// rendered fit at 375×667 or 393×852, VoiceOver behaviour, a production
/// binding or route readiness.
///
/// ARCHIVED (prototype `horseRacing.json`, `horseOutcomeCapture.json`,
/// `horseRacingTiming.json`): Melbourne Cup, Flemington, 3,200 m, November 4,
/// 2025; the 25 winner markets (24 named horses and Other) with their ids and
/// names; each market's last Yes trade strictly before the PUBLISHED schedule
/// (1762228800000 ms, 3:00 PM Melbourne = Nov 3, 8:00 PM PT) for the 20 that
/// have one, and none for More Felons, Parchment Party, Goodie Two Shoes,
/// Torranzino and Other; the last pre-schedule No trades where retained; every
/// retained Yes trade of Half Yours, Al Riffa, Presage Nocturne and Goodie Two
/// Shoes; Sporting Life's reported places (Half Yours 1st by 2¾ lengths, Goodie
/// Two Shoes 2nd, Middle Earth 3rd, River of Stars 4th, Al Riffa 7th; no other
/// place captured); actual start and finish unknown; and, verbatim, every
/// market's own predicate (`markets[].predicate`) and the one rules text all 25
/// markets carry (`markets[].rules`, identical in `horseOutcomeCapture.json`
/// sha256 a0352bd6… and `horseRacing.json` sha256 35c30bcc…).
///
/// CONSTRUCTED (owner inputs, not retained facts): every label, figure text,
/// PT clock line, caption, header, About, source and result wording, scope,
/// identity string, side label, group and step, tint and shape; the history's
/// owner coordinate (minutes from the published schedule) and its frames; the
/// contract grade words; the equal-valued 15% observation; and the whole
/// DURING frame — no live specimen exists, so live stays applicable but
/// evidence-missing and every live value is a construction.
@MainActor
final class HorseRacingEventPagePresentation10868Tests: XCTestCase {

    // MARK: Runners

    private struct Runner {
        let market: String
        let name: String
        /// The last Yes trade strictly before the published schedule.
        let yes: (figure: String, raw: Double, clock: String)?
        /// The last No trade strictly before the published schedule — its own, never a complement.
        let no: (figure: String, clock: String)?
        /// The independently reported finish.
        let place: String?
    }

    private static let runners: [Runner] = [
        Runner(market: "662191", name: "Al Riffa", yes: ("18%", 0.1799999755, "Nov 3, 7:58:15 PM"), no: ("88%", "Nov 3, 2:29:47 PM"), place: "7th"),
        Runner(market: "662192", name: "Buckaroo", yes: ("10%", 0.1, "Nov 3, 6:12:39 PM"), no: nil, place: nil),
        Runner(market: "662193", name: "Arapaho", yes: ("3.3%", 0.0329999897, "Nov 3, 2:07:21 PM"), no: nil, place: nil),
        Runner(market: "662194", name: "Vauban", yes: ("6%", 0.0599999724, "Nov 3, 3:13:47 PM"), no: nil, place: nil),
        Runner(market: "662195", name: "Chevalier Rose", yes: ("2.7%", 0.027272722, "Nov 3, 6:13:35 PM"), no: nil, place: nil),
        Runner(market: "662196", name: "Presage Nocturne", yes: ("18%", 0.1799999928, "Nov 3, 7:46:51 PM"), no: nil, place: nil),
        Runner(market: "662197", name: "Middle Earth", yes: ("49.9%", 0.499, "Nov 3, 7:59:47 PM"), no: nil, place: "3rd"),
        Runner(market: "662198", name: "Meydaan", yes: ("6.4%", 0.063636344, "Nov 3, 3:44:51 PM"), no: nil, place: nil),
        Runner(market: "662199", name: "Absurde", yes: ("7.2%", 0.072493317, "Nov 3, 4:21:35 PM"), no: nil, place: nil),
        Runner(market: "662200", name: "Flatten The Curve", yes: ("33.9%", 0.3391304071, "Nov 3, 7:58:39 PM"), no: ("96%", "Nov 3, 7:45:55 PM"), place: nil),
        Runner(market: "662201", name: "Land Legend", yes: ("2%", 0.02, "Nov 3, 6:13:45 PM"), no: nil, place: nil),
        Runner(market: "662202", name: "Smokin' Romans", yes: ("2.2%", 0.0216368726, "Nov 3, 5:25:41 PM"), no: ("99%", "Nov 3, 12:22:11 PM"), place: nil),
        Runner(market: "662203", name: "Changingoftheguard", yes: ("2%", 0.02, "Nov 3, 5:25:13 PM"), no: nil, place: nil),
        Runner(market: "662204", name: "Half Yours", yes: ("15%", 0.15, "Nov 3, 7:55:27 PM"), no: ("86%", "Nov 3, 7:54:47 PM"), place: "1st"),
        Runner(market: "662205", name: "More Felons", yes: nil, no: nil, place: nil),
        Runner(market: "662206", name: "Onesmoothoperator", yes: ("4%", 0.04, "Nov 3, 6:12:15 PM"), no: nil, place: nil),
        Runner(market: "662207", name: "Furthur", yes: ("4%", 0.04, "Nov 3, 6:13:17 PM"), no: ("98%", "Nov 3, 1:50:27 PM"), place: nil),
        Runner(market: "662208", name: "Parchment Party", yes: nil, no: ("97%", "Nov 3, 12:22:51 PM"), place: nil),
        Runner(market: "662209", name: "Athabascan", yes: ("2%", 0.02, "Nov 3, 6:14:23 PM"), no: ("98%", "Nov 3, 12:30:29 PM"), place: nil),
        Runner(market: "662210", name: "Goodie Two Shoes", yes: nil, no: nil, place: "2nd"),
        Runner(market: "662211", name: "River of Stars", yes: ("39%", 0.3899999774, "Nov 3, 7:59:39 PM"), no: nil, place: "4th"),
        Runner(market: "662212", name: "Royal Supremacy", yes: ("4.4%", 0.0440674894, "Nov 3, 7:43:53 PM"), no: ("98.1%", "Nov 3, 4:44:09 PM"), place: nil),
        Runner(market: "662213", name: "Torranzino", yes: nil, no: nil, place: nil),
        Runner(market: "662214", name: "Valiant King", yes: ("11%", 0.1099999982, "Nov 3, 7:21:53 PM"), no: nil, place: nil),
        Runner(market: "662215", name: "Other", yes: nil, no: ("99.9%", "Nov 3, 7:59:39 PM"), place: nil),
    ]

    private static let raceScope = "constructed.scope.horse.melbourne-2025"
    private static let originalsScope = "constructed.scope.horse.melbourne-2025.originals"
    private static let beforeLabel = "Before scheduled start"
    private static let noPreSchedule = "Pre-race chance unavailable"
    private static let otherStatus = "Special outcome · tie and cancellation rules apply"
    private static let otherFinish = "Special outcome · see the tie and cancellation rules"
    private static let unavailableRunner = "Runner unavailable in this update"
    private static let selectedMissing = "Selected runner unavailable in this update"

    private static func runner(_ name: String) -> Runner { runners.first { $0.name == name }! }

    private static func ref(_ name: String) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: raceScope, source: "polymarket", marketID: runner(name).market, outcomeID: "yes")
    }

    private static func beforeReading(_ runner: Runner) -> FieldChooserReading10868 {
        guard let yes = runner.yes else {
            return FieldChooserReading10868(label: beforeLabel, value: .missing(noPreSchedule))
        }
        return FieldChooserReading10868(
            label: beforeLabel,
            value: .recorded(text: yes.figure, detail: "\(yes.clock) PT · last trade before the published schedule"))
    }

    private static var catalogue: [FieldChooserOriginal10868] {
        runners.map { runner in
            FieldChooserOriginal10868(
                ref: ref(runner.name), name: runner.name, plan: .single(beforeReading(runner)),
                preview: FieldChooserPreview10868(history: nil, absence: ""), movement: nil, clock: nil, result: nil,
                browseStatus: runner.name == "Other" ? otherStatus : "", accent: nil)
        }
    }

    private static var chances: [FieldOutlookBeforeChance10868] {
        runners.compactMap { runner in
            guard let yes = runner.yes else { return nil }
            return FieldOutlookBeforeChance10868(ref: ref(runner.name), probability: yes.raw, reading: beforeReading(runner))
        }
    }

    private static let scale = FieldOutlookScale10868(
        ceiling: 0.5,
        ticks: [FieldOutlookTick10868(probability: 0.25, label: "25%"), FieldOutlookTick10868(probability: 0.5, label: "50%")],
        words: "0–50%")

    /// The five reported places and Other's own special words; nobody else's.
    private static var finalFinishes: [FieldFinishPlace10868] {
        var places: [FieldFinishPlace10868] = runners.compactMap { runner in
            guard let place = runner.place else { return nil }
            let detail = runner.name == "Half Yours" ? "Sporting Life · by 2¾ lengths" : "Sporting Life"
            return FieldFinishPlace10868(ref: ref(runner.name), reading: FieldChooserReading10868(
                label: "Reported finish", value: .recorded(text: place, detail: detail)))
        }
        places.append(FieldFinishPlace10868(ref: ref("Other"), reading: FieldChooserReading10868(
            label: "Reported finish", value: .missing(otherFinish))))
        return places
    }

    private static func selected(_ name: String) -> FieldChooserSelected10868 {
        FieldChooserSelected10868(ref: ref(name), words: "In the chart", unavailableWords: selectedMissing)
    }

    private static func selectedName(_ phase: HorseRacingPhase10868) -> String {
        switch phase {
        case .before: "Al Riffa"
        case .during: "Presage Nocturne"
        case .final: "Half Yours"
        }
    }

    // MARK: Retained trades (owner coordinate: minutes from the published schedule)

    private struct Trade {
        let x: Double
        let p: Double
        let figure: String
        let clock: String
    }

    private static let trades: [String: [Trade]] = [
        "Half Yours": [
            Trade(x: -353.12, p: 0.14, figure: "14%", clock: "Nov 3, 2:06:53 PM"),
            Trade(x: -125.92, p: 0.1399999962, figure: "14%", clock: "Nov 3, 5:54:05 PM"),
            Trade(x: -91.32, p: 0.1399999948, figure: "14%", clock: "Nov 3, 6:28:41 PM"),
            Trade(x: -45.08, p: 0.1372548997, figure: "13.7%", clock: "Nov 3, 7:14:55 PM"),
            Trade(x: -4.55, p: 0.15, figure: "15%", clock: "Nov 3, 7:55:27 PM"),
            Trade(x: 6.45, p: 0.2397668998, figure: "24%", clock: "Nov 3, 8:06:27 PM"),
            Trade(x: 6.55, p: 0.24, figure: "24%", clock: "Nov 3, 8:06:33 PM"),
            Trade(x: 6.68, p: 0.9062555855, figure: "90.6%", clock: "Nov 3, 8:06:41 PM"),
            Trade(x: 10.82, p: 0.99, figure: "99%", clock: "Nov 3, 8:10:49 PM"),
            Trade(x: 11.65, p: 0.99, figure: "99%", clock: "Nov 3, 8:11:39 PM"),
            Trade(x: 20.78, p: 0.999, figure: "99.9%", clock: "Nov 3, 8:20:47 PM"),
            Trade(x: 71.62, p: 0.999, figure: "99.9%", clock: "Nov 3, 9:11:37 PM"),
            Trade(x: 158.62, p: 0.9984913803, figure: "99.8%", clock: "Nov 3, 10:38:37 PM"),
            Trade(x: 164.32, p: 0.9970686952, figure: "99.7%", clock: "Nov 3, 10:44:19 PM"),
        ],
        "Al Riffa": [
            Trade(x: -405.32, p: 0.1699999759, figure: "17%", clock: "Nov 3, 1:14:41 PM"),
            Trade(x: -375.28, p: 0.15, figure: "15%", clock: "Nov 3, 1:44:43 PM"),
            Trade(x: -368.02, p: 0.15, figure: "15%", clock: "Nov 3, 1:51:59 PM"),
            Trade(x: -255.78, p: 0.1699999422, figure: "17%", clock: "Nov 3, 3:44:13 PM"),
            Trade(x: -45.78, p: 0.16, figure: "16%", clock: "Nov 3, 7:14:13 PM"),
            Trade(x: -1.75, p: 0.1799999755, figure: "18%", clock: "Nov 3, 7:58:15 PM"),
            Trade(x: 20.78, p: 0.001, figure: "0.1%", clock: "Nov 3, 8:20:47 PM"),
        ],
        "Presage Nocturne": [
            Trade(x: -241.78, p: 0.1299999536, figure: "13%", clock: "Nov 3, 3:58:13 PM"),
            Trade(x: -86.98, p: 0.1299999935, figure: "13%", clock: "Nov 3, 6:33:01 PM"),
            Trade(x: -44.75, p: 0.13, figure: "13%", clock: "Nov 3, 7:15:15 PM"),
            Trade(x: -38.48, p: 0.1460526284, figure: "14.6%", clock: "Nov 3, 7:21:31 PM"),
            Trade(x: -13.15, p: 0.1799999928, figure: "18%", clock: "Nov 3, 7:46:51 PM"),
            Trade(x: 4.62, p: 0.1939393939, figure: "19.4%", clock: "Nov 3, 8:04:37 PM"),
            Trade(x: 20.75, p: 0.001, figure: "0.1%", clock: "Nov 3, 8:20:45 PM"),
            Trade(x: 30.78, p: 0.001, figure: "0.1%", clock: "Nov 3, 8:30:47 PM"),
        ],
        "Goodie Two Shoes": [
            Trade(x: 6.82, p: 0.9112277228, figure: "91.1%", clock: "Nov 3, 8:06:49 PM"),
            Trade(x: 7.48, p: 0.001, figure: "0.1%", clock: "Nov 3, 8:07:29 PM"),
        ],
    ]

    private static func pointID(_ name: String, _ index: Int) -> String { "\(runner(name).market).\(index)" }

    /// The phase's frame: before the published schedule, the CONSTRUCTED live
    /// frame through minute 5, or every retained trade at the final.
    private static func shown(_ name: String, _ phase: HorseRacingPhase10868) -> [(index: Int, trade: Trade)] {
        (trades[name] ?? []).enumerated()
            .filter { phase == .final || (phase == .before ? $0.element.x < 0 : $0.element.x <= 5) }
            .map { (index: $0.offset, trade: $0.element) }
    }

    /// The last trade strictly before the published schedule, or none.
    private static func beforeIndex(_ name: String) -> Int? {
        (trades[name] ?? []).lastIndex { $0.x < 0 }
    }

    private static func shape(_ name: String) -> FieldHistoryShape10868 {
        switch name {
        case "Half Yours": .circle
        case "Al Riffa": .triangle
        default: .diamond
        }
    }

    private static func tint(_ name: String) -> Color {
        switch name {
        case "Half Yours": .blue
        case "Al Riffa": .orange
        default: .gray
        }
    }

    private static func cohortNames(_ phase: HorseRacingPhase10868) -> [String] {
        phase == .final ? ["Half Yours", "Al Riffa", "Presage Nocturne"] : ["Al Riffa", "Presage Nocturne", "Half Yours"]
    }

    // MARK: History

    private enum Inspect {
        /// The owner's default: the selected runner's last shown trade.
        case owner
        case trade(Int)
        /// A CONSTRUCTED distinct observation with the before figure.
        case constructedEqual
        /// The selected minute has no trade.
        case absent
        case none
    }

    private static let constructedEqual = FieldHistoryPoint10868(id: "662204.constructed", x: -30, probability: 0.15, style: .filled)
    private static let noPreScheduleTrade = "No trade before the scheduled start"
    private static let noTradeHere = "No trade at this time"
    private static let unbound = "Not selected"
    private static let schedule = FieldHistoryGuide10868(id: "schedule", x: 0, label: "Scheduled start")

    private static func historySeries(_ name: String, _ phase: HorseRacingPhase10868,
                                      recorded: FieldHistoryReading10868?, constructed: Bool) -> FieldHistorySeries10868 {
        var runs = shown(name, phase).map { item in
            FieldHistoryRun10868(id: "run.\(pointID(name, item.index))", points: [
                FieldHistoryPoint10868(id: pointID(name, item.index), x: item.trade.x, probability: item.trade.p, style: .filled),
            ])
        }
        if constructed { runs.append(FieldHistoryRun10868(id: "run.constructed", points: [constructedEqual])) }
        let all = trades[name] ?? []
        let before: FieldHistoryReading10868
        if let index = beforeIndex(name) {
            before = .observation(pointID: pointID(name, index), figure: all[index].figure,
                                  provenance: "\(all[index].clock) PT · last trade before the published schedule")
        } else {
            before = .absent(words: noPreScheduleTrade)
        }
        let last: FieldHistoryReading10868
        if let item = shown(name, phase).last {
            last = .observation(pointID: pointID(name, item.index), figure: item.trade.figure, provenance: "\(item.trade.clock) PT")
        } else {
            last = .absent(words: "No retained trade in this view")
        }
        return FieldHistorySeries10868(
            id: runner(name).market, name: name, shape: shape(name), tint: tint(name),
            runs: runs, links: [], labelPointID: nil, before: before, recorded: recorded ?? last,
            absentWords: runs.isEmpty ? "No retained Yes trades in this view" : nil, choose: nil)
    }

    private static func action(_ id: String, _ label: String, available: Bool = true) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: nil, isAvailable: available)
    }

    /// The owner's same-snapshot history for one phase.
    private static func history(_ phase: HorseRacingPhase10868, cohort: Bool = false, selected: String? = nil,
                                inspect: Inspect = .owner) -> FieldHistoryInput10868 {
        let name = selected ?? selectedName(phase)
        let all = trades[name] ?? []
        let frame = shown(name, phase)
        var inspectedIndex: Int?
        switch inspect {
        case .owner: inspectedIndex = frame.last?.index
        case .trade(let index): inspectedIndex = index
        default: inspectedIndex = nil
        }
        let constructed = { if case .constructedEqual = inspect { return true } else { return false } }()
        let sameAsBefore = inspectedIndex != nil && inspectedIndex == beforeIndex(name)
        var recorded: FieldHistoryReading10868?
        var selections: [String: FieldHistorySelection10868] = [:]
        var inspection: FieldHistoryInspection10868?
        if let index = inspectedIndex {
            let trade = all[index]
            recorded = .observation(pointID: pointID(name, index), figure: trade.figure, provenance: "\(trade.clock) PT")
            selections[runner(name).market] = .point(id: pointID(name, index), spoken: trade.figure)
            inspection = FieldHistoryInspection10868(x: trade.x, caption: "Selected trade · \(trade.clock) PT",
                                                     selections: [:], choices: [], choicePresentation: .slider(label: "Inspect recorded trade"),
                                                     note: "Only exact recorded trades are shown.")
        } else if constructed {
            recorded = .observation(pointID: constructedEqual.id, figure: "15%", provenance: "CONSTRUCTED · Nov 3, 7:30:00 PM PT")
            selections[runner(name).market] = .point(id: constructedEqual.id, spoken: "15%")
            inspection = FieldHistoryInspection10868(x: constructedEqual.x, caption: "Selected trade · CONSTRUCTED",
                                                     selections: [:], choices: [], choicePresentation: .slider(label: "Inspect recorded trade"),
                                                     note: "Only exact recorded trades are shown.")
        } else if case .absent = inspect {
            selections[runner(name).market] = .absent(words: noTradeHere)
            inspection = FieldHistoryInspection10868(x: -200, caption: "Selected time · Nov 3, 4:40 PM PT",
                                                     selections: [:], choices: [], choicePresentation: .slider(label: "Inspect recorded trade"),
                                                     note: "Only exact recorded trades are shown.")
        }
        let names = cohort ? [name] + cohortNames(phase).filter { $0 != name } : [name]
        for other in names where other != name {
            selections[runner(other).market] = .absent(words: unbound)
        }
        if let current = inspection {
            inspection = FieldHistoryInspection10868(x: current.x, caption: current.caption, selections: selections,
                                                     choices: current.choices, choicePresentation: current.choicePresentation,
                                                     note: current.note)
        }
        let series = names.map {
            historySeries($0, phase, recorded: $0 == name ? recorded : nil, constructed: $0 == name && constructed)
        }
        let ceiling: Double = phase == .final ? 1 : 0.5
        let upper: Double = phase == .before ? 0 : (phase == .during ? 5 : 170)
        let endClock = phase == .before ? "8:00 PM" : (phase == .during ? "8:05 PM" : "10:50 PM")
        let pressed = inspectedIndex ?? 0
        return FieldHistoryInput10868(
            title: "Win chance history",
            caption: phase == .before
                ? "\(beforeLabel) · Nov 3, 8:00 PM PT"
                : (phase == .during ? "Recorded trades through the constructed frame · Pacific time" : "Recorded probabilities · Pacific time"),
            series: series,
            selection: .series(id: runner(name).market, missingWords: "Selected runner has no history in this view"),
            domain: FieldHistoryDomain10868(lower: -410, upper: upper),
            ceiling: ceiling,
            yTicks: ceiling == 1
                ? [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.5, lines: ["50%"]), FieldHistoryTick10868(value: 1, lines: ["100%"])]
                : [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.25, lines: ["25%"]), FieldHistoryTick10868(value: 0.5, lines: ["50%"])],
            xTicks: [FieldHistoryTick10868(value: -410, lines: ["Nov 3", "1:10 PM"]), FieldHistoryTick10868(value: upper, lines: ["Nov 3", endClock])],
            guides: [schedule],
            breaks: [],
            readout: sameAsBefore ? .singleBefore(label: beforeLabel) : .beforeAndInspected(beforeLabel: beforeLabel, inspectedLabel: "Selected trade"),
            markKey: FieldHistoryMarkKey10868(hollow: nil, filled: "Each dot is one retained Yes trade"),
            comparisonExplanation: nil,
            notes: ["Dots are individual trades, not a continuous forecast.",
                    "Scheduled start is labelled; the actual start and finish are unknown."],
            summary: "Recorded Yes probabilities for \(names.joined(separator: ", ")). Zero to \(ceiling == 1 ? 100 : 50) percent. Dots are individual trades, not a continuous forecast.",
            plotHeight: 260, unboundReadingWords: unbound, plotUnavailableWords: nil,
            windows: nil,
            scale: phase == .final ? nil : action("scale.full", "0–100%"),
            moreOriginals: nil, details: nil,
            expand: action("history.expand", "Expand the win chance history"),
            inspect: nil,
            previous: action("trade.earlier", "Earlier", available: pressed > 0),
            next: action("trade.later", "Later", available: pressed < max(0, frame.count - 1)),
            inspection: inspection,
            layout: .focused,
            selectedReadout: sameAsBefore
                ? FieldHistorySelectedReadout10868(beforeLabel: nil, inspectedLabel: phase == .before ? "Selected pre-race trade" : "\(beforeLabel) · selected trade")
                : FieldHistorySelectedReadout10868(beforeLabel: beforeLabel, inspectedLabel: "Selected trade"),
            plotAbsence: frame.isEmpty && !cohort
                ? FieldHistoryPlotAbsence10868(title: "No retained Yes trades", words: "This original stays available. No probability is inferred from other runners.")
                : nil)
    }

    // MARK: Picks, catalogue and finish

    private static func picks(_ phase: HorseRacingPhase10868, cohort: Bool = false, selected: String? = nil) -> HorseRacingPicksInput10868 {
        HorseRacingPicksInput10868(
            scope: raceScope, catalogue: catalogue, selected: Self.selected(selected ?? selectedName(phase)),
            groupLabel: "Featured runner histories",
            picks: cohortNames(phase).map { HorseRacingPick10868(ref: ref($0), shape: cohort ? shape($0) : nil) },
            cohort: HorseRacingToggle10868(id: "cohort", label: cohort ? "Solo" : "Compare 3", isOn: cohort),
            unavailableWords: unavailableRunner, chooseHint: "Shows this runner’s recorded trades")
    }

    private static var groups: [HorseCatalogueGroup10868] {
        (0..<5).map { group in
            HorseCatalogueGroup10868(
                id: "group.\(group + 1)", label: "\(group * 5 + 1)–\(group * 5 + 5) of 25",
                rows: runners[(group * 5)..<(group * 5 + 5)].map { FieldFinishSlot10868(ref: ref($0.name), name: $0.name) })
        }
    }

    private static func step(_ group: Int, _ label: String) -> HorseCatalogueStep10868? {
        (1...5).contains(group) ? HorseCatalogueStep10868(groupID: "group.\(group)", label: label, spokenLabel: "\(label) runners") : nil
    }

    private static let catalogueCopy = HorseCatalogueCopy10868(
        heading: "25 props · 50 original Yes / No outcomes",
        note: "Recorded at different times · not a current forecast",
        scaleLabel: "Pre-race win chance", pagerLabel: "Browse horse props",
        finishLabel: "Reported finish", finishUnit: "finish", finishUnavailable: "Finish not recorded",
        chanceUnavailable: "Not shown on this scale", offScale: "Above the 50% scale",
        unavailableWords: unavailableRunner, sideUnavailable: "Original unavailable",
        noGroup: "Choose a group of runners", groupUnavailable: "Group unavailable in this update",
        emptyGroup: "No runners in this group", openHint: "Opens this runner’s recorded history")

    private static func catalogueInput(_ phase: HorseRacingPhase10868, group: Int = 1,
                                       groups: [HorseCatalogueGroup10868]? = nil,
                                       currentGroupID: String? = nil,
                                       runnerCatalogue: [FieldChooserOriginal10868]? = nil,
                                       finishes: [FieldFinishPlace10868]? = nil,
                                       selected: String? = "Half Yours") -> HorseCatalogueInput10868 {
        HorseCatalogueInput10868(
            scope: raceScope, catalogue: runnerCatalogue ?? catalogue,
            selected: selected.map { Self.selected($0) },
            groups: groups ?? Self.groups, currentGroupID: currentGroupID ?? "group.\(group)",
            previous: step(group - 1, "Previous"), next: step(group + 1, "Next"),
            chances: chances, scale: scale, finishes: finishes, phase: phase, copy: catalogueCopy)
    }

    private static let finishCopy = FieldFinishCopy10868(
        title: "How the race finished", context: "Before scheduled start · recorded at different times",
        scaleLabel: "Pre-race win chance", graphicLabel: "Reported finishes", finishLabel: "Reported finish",
        finishUnit: "finish", finishUnavailable: "Finish not confirmed for this runner",
        chanceUnavailable: "Not shown on this scale", offScale: "Above the 50% scale",
        outsideDisplayed: "The selected runner is not among the reported finishes",
        empty: "No finishing positions captured", count: "5 reported finishes",
        openPrompt: "Tap a horse for its history.", openHint: "Opens this runner’s recorded history")

    private static let finishOrder = ["Half Yours", "Goodie Two Shoes", "Middle Earth", "River of Stars", "Al Riffa"]

    private static func finishCard(phase: FieldOutlookPhase10868 = .final) -> FieldFinishInput10868 {
        FieldFinishInput10868(
            scope: raceScope, catalogue: catalogue, selected: selected("Half Yours"),
            displayed: finishOrder.map { FieldFinishSlot10868(ref: ref($0), name: $0) },
            finishes: finalFinishes, chances: chances, scale: scale, phase: phase, copy: finishCopy,
            unavailableWords: unavailableRunner)
    }

    private static let resultSource = HorseRacingText10868(title: "Result source & meaning", sections: [
        HorseRacingSection10868(title: nil, paragraphs: [
            "Sporting Life reports Half Yours won on November 4, 2025, by 2¾ lengths, with Goodie Two Shoes 2nd, Middle Earth 3rd and River of Stars 4th. Al Riffa was 7th. Other finishing positions were not captured.",
            "Each dot shows the last retained Yes trade strictly before the published schedule, not a verified closing or blended probability. The result appends no 100% endpoint, and the source does not establish exact start or finish times.",
        ]),
    ], link: HorseRacingLink10868(id: "result.report", label: "Read the race report"))

    private static func finish(phase: FieldOutlookPhase10868 = .final) -> HorseRacingFinishInput10868 {
        HorseRacingFinishInput10868(eyebrow: "Pre-race trade → actual finish", card: finishCard(phase: phase),
                                    source: resultSource, expandLabel: "Expand the race finish")
    }

    // MARK: Header, About, source and page

    private static func header(_ phase: HorseRacingPhase10868) -> HorseRacingHeader10868 {
        let eyebrow: String = switch phase {
        case .before: "BEFORE RACE · MELBOURNE CUP · NOV 4, 2025"
        case .during: "CONSTRUCTED LIVE EXAMPLE · MELBOURNE CUP · NOV 4, 2025"
        case .final: "FINAL · MELBOURNE CUP · NOV 4, 2025"
        }
        let title: String = switch phase {
        case .before: "Before the race"
        case .during: "During the race"
        case .final: "Half Yours won"
        }
        let status: String = switch phase {
        case .before: "Before scheduled start · published 3:00 PM Melbourne (Nov 3, 8:00 PM PT)"
        case .during: "Constructed live example · no race-state feed"
        case .final: "Final · reported finish"
        }
        return HorseRacingHeader10868(eyebrow: eyebrow, title: title, place: "Flemington · 3,200 m",
                                      date: "November 4, 2025 · Melbourne", status: status,
                                      aboutLabel: "About this race", aboutHint: "Opens the race, its schedule and its sources")
    }

    private static func reader(_ phase: HorseRacingPhase10868) -> HorseRacingReaderHeader10868 {
        switch phase {
        case .before: HorseRacingReaderHeader10868(title: "Melbourne Cup · Before race", state: "Before scheduled start · historical trades")
        case .during: HorseRacingReaderHeader10868(title: "Melbourne Cup · Constructed live example", state: "Recorded trades so far")
        case .final: HorseRacingReaderHeader10868(title: "Half Yours won · Melbourne Cup", state: "Final result · dated trade history")
        }
    }

    /// Before and live About name no report, result or settlement; the final
    /// links the schedule report that carries the results.
    private static func about(_ phase: HorseRacingPhase10868) -> HorseRacingText10868 {
        let middle = phase == .during
            ? "Constructed live example: no race-state, position or progress feed exists for this race."
            : "This view is reconstructed from later-retained trades; receipt at the time is unverified. It is not a live forecast, and provider market dates are not race times."
        return HorseRacingText10868(title: "About this race", sections: [
            HorseRacingSection10868(title: "Race", paragraphs: ["Melbourne Cup · Flemington · 3,200 m · November 4, 2025."]),
            HorseRacingSection10868(title: "Probabilities", paragraphs: [
                "Probabilities are retained Polymarket trades. Before is bounded by the published 3:00 PM Melbourne schedule (Nov 3, 8:00 PM PT); the actual start and finish are unknown.",
                middle,
            ]),
            HorseRacingSection10868(title: "Contracts", paragraphs: [
                "25 original contracts: 24 named horses and Other. Special tie and cancellation rules remain in each original. Compared runners are not normalized or a complete field probability.",
            ]),
        ], link: phase == .final ? HorseRacingLink10868(id: "schedule.source", label: "Published race schedule (report includes results)") : nil)
    }

    private static func source(_ phase: HorseRacingPhase10868) -> HorseRacingText10868 {
        var paragraphs = [
            "Pre-race trades are timestamped strictly before the published 3:00 PM Melbourne schedule. This is not a verified actual start, an opening or closing quote, or a live forecast.",
            "Trades may be isolated or disagree with the wider market; no current probability or Bain Luck blend is inferred, and no trades are joined into a continuous forecast.",
        ]
        if phase == .final { paragraphs.append("Contract settlement is separate from the reported finishing position.") }
        return HorseRacingText10868(title: "History & source details", sections: [HorseRacingSection10868(title: nil, paragraphs: paragraphs)])
    }

    private static let pendingWords = "No live positions or progress are reported for this race. The finish appears here after it is reported."

    private static func page(_ phase: HorseRacingPhase10868, history: FieldHistoryInput10868? = nil,
                             cohort: Bool = false) -> HorseRacingPageInput10868 {
        HorseRacingPageInput10868(
            phase: phase, header: header(phase), reader: reader(phase),
            notice: phase == .during ? "Current probability unavailable · recorded trades retained" : nil,
            picks: picks(phase, cohort: cohort),
            history: history ?? Self.history(phase, cohort: cohort),
            readerPlotHeight: 340,
            finish: phase == .final ? finish() : nil,
            finishPending: phase == .during ? pendingWords : nil,
            catalogue: catalogueInput(phase, finishes: phase == .final ? finalFinishes : nil),
            catalogueDisclosure: HorseRacingToggle10868(id: "catalogue", label: "All 25 winner props", isOn: true),
            about: about(phase), source: source(phase),
            copy: HorseRacingPageCopy10868(sourceLabel: "History & source details",
                                           allOriginalsLabel: "All 50 original Yes / No outcomes"))
    }

    // MARK: Originals (shared Details)

    /// ARCHIVED, verbatim: each market's own predicate, `markets[].predicate`
    /// in `horseOutcomeCapture.json` (identical in `horseRacing.json`), keyed by
    /// market id. Other's is the special "another horse" predicate.
    private static let retainedPredicates: [String: String] = [
        "662191": "Will Al Riffa win the 2025 Lexus Melbourne Cup?",
        "662192": "Will Buckaroo win the 2025 Lexus Melbourne Cup?",
        "662193": "Will Arapaho win the 2025 Lexus Melbourne Cup?",
        "662194": "Will Vauban win the 2025 Lexus Melbourne Cup?",
        "662195": "Will Chevalier Rose win the 2025 Lexus Melbourne Cup?",
        "662196": "Will Presage Nocturne win the 2025 Lexus Melbourne Cup?",
        "662197": "Will Middle Earth win the 2025 Lexus Melbourne Cup?",
        "662198": "Will Meydaan win the 2025 Lexus Melbourne Cup?",
        "662199": "Will Absurde win the 2025 Lexus Melbourne Cup?",
        "662200": "Will Flatten The Curve win the 2025 Lexus Melbourne Cup?",
        "662201": "Will Land Legend win the 2025 Lexus Melbourne Cup?",
        "662202": "Will Smokin' Romans win the 2025 Lexus Melbourne Cup?",
        "662203": "Will Changingoftheguard win the 2025 Lexus Melbourne Cup?",
        "662204": "Will Half Yours win the 2025 Lexus Melbourne Cup?",
        "662205": "Will More Felons win the 2025 Lexus Melbourne Cup?",
        "662206": "Will Onesmoothoperator win the 2025 Lexus Melbourne Cup?",
        "662207": "Will Furthur win the 2025 Lexus Melbourne Cup?",
        "662208": "Will Parchment Party win the 2025 Lexus Melbourne Cup?",
        "662209": "Will Athabascan win the 2025 Lexus Melbourne Cup?",
        "662210": "Will Goodie Two Shoes win the 2025 Lexus Melbourne Cup?",
        "662211": "Will River of Stars win the 2025 Lexus Melbourne Cup?",
        "662212": "Will Royal Supremacy win the 2025 Lexus Melbourne Cup?",
        "662213": "Will Torranzino win the 2025 Lexus Melbourne Cup?",
        "662214": "Will Valiant King win the 2025 Lexus Melbourne Cup?",
        "662215": "Will another horse win the 2025 Lexus Melbourne Cup?",
    ]

    /// ARCHIVED, verbatim: the one rules text every retained market carries —
    /// `markets[].rules`, 742 ASCII bytes, identical for all 25 markets in both
    /// files. Kept whole here as the receipt.
    private static let retainedRules = "This market will resolve to \"Yes\" if the listed horse places first in the 2025 Lexus Melbourne Cup. Otherwise, this market will resolve to \"No\".\n\nThis market will close on November 4, 2025, 2:00 AM ET, allowing time to account for any disputes or disqualifications that might occur post-race. If the race is permanently cancelled or doesn't take place by November 5, 2025, 11:59 PM ET, this market will resolve to \"Other\". \n\nIn the event of a tie between two or more horses, the market will resolve in favor of the horse whose name appears first in alphabetical order. \n\nThe primary resolution source for this market will be official information from Melbourne Cup race organizers, however a consensus of credible reporting will also be used."

    /// The same text as the owner's four verified paragraphs, split only at the
    /// retained blank lines; two keep their retained trailing space.
    private static let retainedRulesParagraphs = [
        "This market will resolve to \"Yes\" if the listed horse places first in the 2025 Lexus Melbourne Cup. Otherwise, this market will resolve to \"No\".",
        "This market will close on November 4, 2025, 2:00 AM ET, allowing time to account for any disputes or disqualifications that might occur post-race. If the race is permanently cancelled or doesn't take place by November 5, 2025, 11:59 PM ET, this market will resolve to \"Other\". ",
        "In the event of a tie between two or more horses, the market will resolve in favor of the horse whose name appears first in alphabetical order. ",
        "The primary resolution source for this market will be official information from Melbourne Cup race organizers, however a consensus of credible reporting will also be used.",
    ]

    private static func identity(_ name: String, _ side: String) -> OriginalMarketDetails9483.Identity {
        OriginalMarketDetails9483.Identity(source: "polymarket", market: runner(name).market, side: side)
    }

    private static func selection(_ name: String, _ side: String) -> OriginalMarketDetails9483.Selection {
        OriginalMarketDetails9483.Selection(scope: originalsScope, identity: identity(name, side))
    }

    /// Each side's retained predicate and verbatim rules, its own reading and,
    /// at the final, its own CONSTRUCTED grade words — never read from a
    /// finish, never a complement of the other side.
    private static func original(_ runner: Runner, _ side: String, _ phase: HorseRacingPhase10868,
                                 grade: Bool = true) -> OriginalMarketDetails9483.Original {
        let isOther = runner.name == "Other"
        let title = retainedPredicates[runner.market] ?? ""
        let outcome: String
        if isOther {
            outcome = side == "Yes" ? "Yes · another horse wins · special rules apply" : "No · another horse does not win · special rules apply"
        } else {
            outcome = side == "Yes" ? "Yes · wins the race" : "No · does not win the race"
        }
        let pregame: OriginalMarketDetails9483.Reading
        if side == "Yes", let yes = runner.yes {
            pregame = .value(yes.figure, placement: yes.raw, provenance: "\(yes.clock) PT · last trade before the published schedule")
        } else if side == "No", let no = runner.no {
            pregame = .value(no.figure, placement: nil, provenance: "\(no.clock) PT · last trade before the published schedule")
        } else {
            pregame = .missing("No retained \(side) trade before the scheduled start")
        }
        var gradeWords: OriginalMarketDetails9483.Grade?
        if phase == .final, grade {
            let happened = (runner.name == "Half Yours") == (side == "Yes")
            gradeWords = OriginalMarketDetails9483.Grade(words: happened ? "Happened" : "Didn’t happen",
                                                         provenance: "Contract resolved on Polymarket · separate from the reported finish")
        }
        var original = OriginalMarketDetails9483.Original(
            identity: identity(runner.name, side), title: title, outcome: outcome,
            mode: phase == .final ? .result : .pregame, pregame: pregame, later: nil, grade: gradeWords,
            about: OriginalMarketDetails9483.About(
                source: "Polymarket",
                rules: .verified(retainedRulesParagraphs),
                provenance: [OriginalMarketDetails9483.Row(label: "Provider market", value: "Polymarket · market \(runner.market)"),
                             OriginalMarketDetails9483.Row(label: "Schedule", value: "Published 3:00 PM Melbourne · not the actual start")],
                historicalQuote: nil))
        original.beforeLabel = beforeLabel
        return original
    }

    private static func detailsCatalogue(_ phase: HorseRacingPhase10868) -> OriginalMarketDetails9483.Catalogue {
        OriginalMarketDetails9483.Catalogue(scope: originalsScope, originals: runners.flatMap { [original($0, "Yes", phase), original($0, "No", phase)] })
    }

    private static var sides: [HorseCatalogueSide10868] {
        runners.flatMap { runner in
            ["Yes", "No"].map { side in
                HorseCatalogueSide10868(ref: ref(runner.name), label: "\(side) details",
                                        spokenLabel: "\(runner.name): \(side) details", selection: selection(runner.name, side))
            }
        }
    }

    /// The anchor's original entry for one frame: the selected runner's exact
    /// Yes original and the position of ITS selected, admitted observation in
    /// that same frame — nil when no observation is selected, and no entry at
    /// all when no runner is. Owner-side composition; the page adds no policy.
    private static func open(_ phase: HorseRacingPhase10868, history frame: FieldHistoryInput10868? = nil) -> HorseRacingOriginalOpen10868? {
        let input = frame ?? Self.history(phase)
        guard case .series(let id, _) = input.selection,
              let runner = runners.first(where: { $0.market == id }) else { return nil }
        let series = input.series.first { $0.id == id }
        let point = series.flatMap { FieldHistoryGeometry10868.inspectedPoint($0, in: input) }
        return HorseRacingOriginalOpen10868(label: "Explore Yes / No outcomes", selection: selection(runner.name, "Yes"),
                                            selectedPosition: point?.x)
    }

    /// Whether an entry is the selected runner's Yes original at exactly that
    /// runner's selected observation in this frame — or nil with none selected.
    private static func isAdmitted(_ open: HorseRacingOriginalOpen10868?, in input: FieldHistoryInput10868) -> Bool {
        guard let open, case .series(let id, _) = input.selection,
              open.selection.identity.market == id, open.selection.identity.side == "Yes",
              let series = input.series.first(where: { $0.id == id }) else { return false }
        return open.selectedPosition == FieldHistoryGeometry10868.inspectedPoint(series, in: input)?.x
    }

    /// An entry's whole payload as handed back: market, side and position.
    private static func payload(_ open: HorseRacingOriginalOpen10868) -> String {
        "open:\(open.selection.identity.market):\(open.selection.identity.side)@\(open.selectedPosition.map { String($0) } ?? "none")"
    }

    /// The ACTUAL entry one page draws and the payloads `onOriginalOpen`
    /// receives when it is opened, after the hold hook.
    private static func openPayloads(_ input: HorseRacingPageInput10868,
                                     _ originals: HorseRacingOriginals10868) -> (entry: HorseRacingOriginalOpen10868?, log: [String]) {
        var log: [String] = []
        let view = HorseRacingEventPagePresentation10868(
            input: input, originals: originals,
            onOriginalOpen: { log.append(Self.payload($0)) }, onInteraction: { log.append("hold") })
        let entry = view.originalEntry()
        view.openOriginal()
        return (entry, log)
    }

    private static func originals(_ phase: HorseRacingPhase10868, held: OriginalMarketDetails9483.Selection? = nil,
                                  catalogue: OriginalMarketDetails9483.Catalogue? = nil,
                                  history frame: FieldHistoryInput10868? = nil) -> HorseRacingOriginals10868 {
        HorseRacingOriginals10868(
            catalogue: catalogue ?? detailsCatalogue(phase), selection: held ?? selection(selectedName(phase), "Yes"),
            heading: "Original Yes / No outcomes", context: "50 retained originals",
            emptyWords: "No retained originals for this race", unavailableChoice: "Original unavailable", tint: .blue,
            sides: sides,
            open: open(phase, history: frame))
    }

    private static func withSelection(_ input: FieldHistoryInput10868, _ selection: FieldHistoryOriginalSelection10868) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: input.title, caption: input.caption, series: input.series, selection: selection, domain: input.domain,
            ceiling: input.ceiling, yTicks: input.yTicks, xTicks: input.xTicks, guides: input.guides, breaks: input.breaks,
            readout: input.readout, markKey: input.markKey, comparisonExplanation: input.comparisonExplanation, notes: input.notes,
            summary: input.summary, plotHeight: input.plotHeight, unboundReadingWords: input.unboundReadingWords,
            plotUnavailableWords: input.plotUnavailableWords, windows: input.windows, scale: input.scale,
            moreOriginals: input.moreOriginals, details: input.details, expand: input.expand, inspect: input.inspect,
            previous: input.previous, next: input.next, inspection: input.inspection, layout: input.layout,
            probabilityLowerBound: input.probabilityLowerBound, probabilityRangeExplanation: input.probabilityRangeExplanation,
            selectedReadout: input.selectedReadout, inspectionRingShape: input.inspectionRingShape,
            plotAbsence: input.plotAbsence, showsKey: input.showsKey)
    }

    // MARK: Reachable outputs

    /// A fact as a whole token — no letter or digit directly before or after
    /// it — so "7th" is never found in "17th" and a probability is never an ordinal.
    private static func mentions(_ output: String, _ fact: String) -> Bool {
        let pattern = "(?<![\\p{L}\\p{N}])" + NSRegularExpression.escapedPattern(for: fact) + "(?![\\p{L}\\p{N}])"
        return output.range(of: pattern, options: .regularExpression) != nil
    }

    private static func historyOutputs(_ input: FieldHistoryInput10868) -> [String] {
        var outputs = [input.title, input.summary, input.unboundReadingWords]
        outputs += [input.caption, input.plotUnavailableWords, input.markKey.hollow, input.markKey.filled,
                    input.plotAbsence?.title, input.plotAbsence?.words, FieldHistoryGeometry10868.selectionWords(input)].compactMap { $0 }
        outputs += input.notes + input.xTicks.flatMap(\.lines) + input.yTicks.flatMap(\.lines) + input.guides.map(\.label)
        outputs += FieldHistoryGeometry10868.actions(input).flatMap { [$0.label] + [$0.spokenLabel].compactMap { $0 } }
        for series in input.series {
            outputs += [series.name] + [FieldHistoryGeometry10868.absentWords(series, in: input)].compactMap { $0 }
            outputs += FieldHistoryGeometry10868.readoutSlots(series, in: input).map(FieldHistoryGeometry10868.spokenSlot)
        }
        if case .original(_, let slots) = FieldHistoryGeometry10868.selectedSummary(input) {
            outputs += slots.map(FieldHistoryGeometry10868.spokenSlot)
        }
        outputs.append(FieldHistoryGeometry10868.spokenValue(input))
        if let inspection = input.inspection { outputs += [inspection.caption] + [inspection.note].compactMap { $0 } }
        return outputs
    }

    private static func finishOutputs(_ card: FieldFinishInput10868) -> [String] {
        let model = FieldFinishModel10868(card)
        guard model.isShown else { return [] }
        var outputs = [card.copy.title, card.copy.scaleLabel, card.scale.words, card.copy.finishUnit]
        outputs += [card.copy.context, card.copy.count, model.openPrompt(canOpen: true), model.notice].compactMap { $0 }
        for row in model.rows {
            outputs.append(model.rowSummary(row))
            outputs += [FieldFinishModel10868.ordinal(row.finish), FieldFinishModel10868.finishWords(row.finish),
                        model.figure(row), model.dotLabel(row), model.stateWords(row)].compactMap { $0 }
        }
        return outputs
    }

    private static func withGroup(_ input: HorseCatalogueInput10868, _ id: String) -> HorseCatalogueInput10868 {
        HorseCatalogueInput10868(scope: input.scope, catalogue: input.catalogue, selected: input.selected, groups: input.groups,
                                 currentGroupID: id, previous: input.previous, next: input.next, chances: input.chances,
                                 scale: input.scale, finishes: input.finishes, phase: input.phase, copy: input.copy)
    }

    private static func catalogueOutputs(_ view: HorseCatalogueView10868) -> [String] {
        var outputs = [view.input.copy.heading, view.input.copy.scaleLabel, view.input.copy.pagerLabel]
        outputs += [view.input.copy.note, view.input.previous?.label, view.input.next?.label].compactMap { $0 }
        for group in view.input.groups {
            let paged = HorseCatalogueView10868(input: withGroup(view.input, group.id), sides: view.sides, originals: view.originals)
            let model = paged.model
            outputs += [model.position, model.groupWords, model.notice, model.scaleWords].compactMap { $0 }
            for row in model.rows {
                outputs += [row.slot.name, model.rowSummary(row)]
                outputs += [row.resolution.original?.name, model.figureLabel(row), model.figure(row), model.stateWords(row),
                            HorseCatalogueModel10868.ordinal(row), HorseCatalogueModel10868.finishWords(row), model.status(row)].compactMap { $0 }
                if HorseCatalogueModel10868.ordinal(row) != nil { outputs.append(view.input.copy.finishUnit) }
                outputs += paged.sideStates(row).flatMap { [$0.side.label] + [$0.side.spokenLabel].compactMap { $0 } }
            }
        }
        return outputs
    }

    private static func textOutputs(_ content: HorseRacingTextContent10868?) -> [String] {
        guard let content else { return [] }
        return [content.text.title] + content.text.sections.flatMap { [$0.title].compactMap { $0 } + $0.paragraphs }
            + [content.link?.label].compactMap { $0 }
    }

    /// Every word a reader can see or hear from one page, collected through the
    /// same Views in every content mode with every callback supplied: header,
    /// Info, notice, picks, page and full-size history, original and source
    /// entries, finish card and result source, live words, every catalogue
    /// group, About and source content, the held sides and every original's
    /// Details and speech.
    private static func reachableOutputs(_ input: HorseRacingPageInput10868, _ originals: HorseRacingOriginals10868) -> [String] {
        let header = input.header
        var outputs = [header.title, header.aboutLabel, input.reader.title]
        outputs += [header.eyebrow, header.place, header.date, header.status, header.aboutHint, input.reader.state,
                    input.notice, input.copy.sourceLabel, input.copy.allOriginalsLabel, input.catalogueDisclosure?.label].compactMap { $0 }
        let modes: [HorseRacingMode10868] = [.page, .fullHistory, .fullFinish, .catalogue, .original, .about, .source]
        var opened: [String] = []
        for mode in modes {
            let view = HorseRacingEventPagePresentation10868(
                input: input, mode: mode, originals: originals,
                onAbout: {}, onSource: {}, onLink: { _ in }, onRunner: { _ in }, onRunnerHistory: { _ in }, onToggle: { _ in },
                onHistoryAction: { _ in }, onHistoryInspectionChoice: { _ in }, onHistoryPlotPosition: { _ in },
                onOriginalOpen: { opened.append(Self.payload($0)) }, onFinishExpand: {}, onCatalogueGroup: { _ in },
                onOriginalSelect: { _ in }, onOriginalHistory: { _ in }, onAllOriginals: {})
            if let picks = view.picksContent() {
                let model = HorseRacingPicksModel10868(picks.input)
                outputs += [picks.input.groupLabel] + model.rows.map(model.spoken)
                outputs += [model.notice, picks.input.cohort?.label, picks.input.chooseHint].compactMap { $0 }
            }
            outputs += historyOutputs(view.historyContent(reader: false).input)
            outputs += historyOutputs(view.historyContent(reader: true).input)
            // The entry's words AND its payload, then the payload the callback actually receives.
            outputs += [view.originalEntry()?.label, view.originalEntry().map(Self.payload)].compactMap { $0 }
            view.openOriginal()
            for card in [view.finishContent(reader: false), view.finishContent(reader: true)].compactMap({ $0 }) {
                outputs += finishOutputs(card.input)
            }
            outputs += [HorseRacingPageModel10868(input).finish?.eyebrow, HorseRacingPageModel10868(input).finish?.expandLabel,
                        HorseRacingPageModel10868(input).finishPending].compactMap { $0 }
            outputs += textOutputs(view.resultSourceContent(reader: false)) + textOutputs(view.resultSourceContent(reader: true))
            if let catalogue = view.catalogueContent() { outputs += catalogueOutputs(catalogue) }
            outputs += textOutputs(view.aboutContent()) + textOutputs(view.sourceContent())
            outputs += view.originalSides().flatMap { [$0.side.label] + [$0.side.spokenLabel].compactMap { $0 } }
        }
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
        outputs += [originals.heading, originals.emptyWords] + [originals.context].compactMap { $0 }
        return outputs + opened
    }

    // MARK: Phases

    func testBeforeTheRaceMountsTheAnchorAndCatalogueWithNoFinish() {
        let input = Self.page(.before)
        let model = HorseRacingPageModel10868(input)
        let view = HorseRacingEventPagePresentation10868(input: input, originals: Self.originals(.before))

        XCTAssertEqual(view.historyContent(reader: false).input, input.history)
        XCTAssertNil(model.finish)
        XCTAssertNil(view.finishContent(reader: false))
        XCTAssertNil(model.finishPending)
        XCTAssertFalse(model.readerShows(.fullFinish))
        XCTAssertTrue(model.readerShows(.fullHistory))
        XCTAssertNil(view.resultSourceContent(reader: false))

        // The selected runner's dated pre-schedule trade, labelled as such; the
        // owner's single-slot intent for the very same observation.
        let summary = FieldHistoryGeometry10868.selectedSummary(input.history)
        guard case .original(let series, let slots) = summary else { return XCTFail("Al Riffa is the selected runner") }
        XCTAssertEqual(series.name, "Al Riffa")
        XCTAssertEqual(slots, [FieldHistoryReadoutSlot10868(label: "Selected pre-race trade", display: .figure("18%", provenance: "Nov 3, 7:58:15 PM PT"))])
        XCTAssertEqual(Self.slots(input.history)[0], [FieldHistoryReadoutSlot10868(
            label: "Before scheduled start", display: .figure("18%", provenance: "Nov 3, 7:58:15 PM PT · last trade before the published schedule"))])
        XCTAssertEqual(input.history.caption, "Before scheduled start · Nov 3, 8:00 PM PT")

        // The catalogue's first group with no finish in any row.
        guard let catalogue = view.catalogueContent() else { return XCTFail("the before catalogue mounts") }
        let rows = catalogue.model.rows
        XCTAssertEqual(rows.map(\.slot.name), ["Al Riffa", "Buckaroo", "Arapaho", "Vauban", "Chevalier Rose"])
        XCTAssertEqual(rows.map { catalogue.model.figure($0) }, ["18%", "10%", "3.3%", "6%", "2.7%"])
        XCTAssertTrue(rows.allSatisfy { $0.finish == nil })
        XCTAssertFalse(catalogue.model.showsFinish)
    }

    func testDuringTheRaceShowsOnlyOwnerStateAndRecordedTradesSoFar() {
        let input = Self.page(.during)
        let model = HorseRacingPageModel10868(input)
        let view = HorseRacingEventPagePresentation10868(input: input, originals: Self.originals(.during))

        XCTAssertNil(model.finish, "no live placing or finish")
        XCTAssertEqual(model.finishPending, Self.pendingWords)
        XCTAssertEqual(model.notice, "Current probability unavailable · recorded trades retained")
        XCTAssertNil(view.finishContent(reader: true))

        // The CONSTRUCTED frame ends at owner minute 5: Presage Nocturne's dated
        // pre-schedule trade beside its distinct later recorded trade.
        guard case .original(_, let slots) = FieldHistoryGeometry10868.selectedSummary(input.history) else {
            return XCTFail("Presage Nocturne is selected")
        }
        XCTAssertEqual(slots, [
            FieldHistoryReadoutSlot10868(label: "Before scheduled start", display: .figure("18%", provenance: "Nov 3, 7:46:51 PM PT · last trade before the published schedule")),
            FieldHistoryReadoutSlot10868(label: "Selected trade", display: .figure("19.4%", provenance: "Nov 3, 8:04:37 PM PT")),
        ])
        XCTAssertEqual(Self.allPoints(input.history).map(\.x).max(), 4.62)

        // A final card handed to the live page is not mounted; a live catalogue
        // without an admitted channel shows no finish.
        var foreign = input
        foreign.finish = Self.finish()
        XCTAssertNil(HorseRacingPageModel10868(foreign).finish)
        guard let catalogue = view.catalogueContent() else { return XCTFail("the live catalogue mounts") }
        XCTAssertTrue(catalogue.model.rows.allSatisfy { $0.finish == nil })

        // Only an owner-admitted actual-so-far channel is read — never the final.
        let live = Self.catalogueInput(.during, finishes: [FieldFinishPlace10868(
            ref: Self.ref("Al Riffa"),
            reading: FieldChooserReading10868(label: "Running state", value: .missing("CONSTRUCTED · no position reported")))])
        let liveRows = HorseCatalogueModel10868(live).rows
        XCTAssertEqual(HorseCatalogueModel10868.finishWords(liveRows[0]), "CONSTRUCTED · no position reported")
        XCTAssertEqual(HorseCatalogueModel10868.finishWords(liveRows[1]), "Finish not recorded")
        XCTAssertNil(HorseCatalogueModel10868.ordinal(liveRows[0]))
    }

    func testAtTheFinalTheFinishCardSitsBesideTheAnchorAndTheCatalogue() {
        let input = Self.page(.final)
        let model = HorseRacingPageModel10868(input)
        let view = HorseRacingEventPagePresentation10868(input: input, originals: Self.originals(.final))

        XCTAssertEqual(view.finishContent(reader: false)?.input, Self.finishCard())
        XCTAssertTrue(model.readerShows(.fullFinish))
        XCTAssertEqual(model.resultSource, Self.resultSource)
        XCTAssertNil(model.finishPending)

        guard case .original(_, let slots) = FieldHistoryGeometry10868.selectedSummary(input.history) else {
            return XCTFail("Half Yours is selected")
        }
        XCTAssertEqual(slots, [
            FieldHistoryReadoutSlot10868(label: "Before scheduled start", display: .figure("15%", provenance: "Nov 3, 7:55:27 PM PT · last trade before the published schedule")),
            FieldHistoryReadoutSlot10868(label: "Selected trade", display: .figure("99.7%", provenance: "Nov 3, 10:44:19 PM PT")),
        ])

        // A finish card whose own phase is not final is not mounted.
        var early = input
        early.finish = Self.finish(phase: .during)
        XCTAssertNil(HorseRacingPageModel10868(early).finish)
    }

    // MARK: Truth

    func testBeforeAndLiveCarryNoFinishReportOrSettlementInAnyReachableOutput() {
        // The final Half Yours trade position (164.32) is a later fact too: it
        // may reach a before or live entry payload only by leaking.
        let later = ["1st", "2nd", "3rd", "4th", "7th", "won", "Sporting Life", "2¾", "lengths", "Happened",
                     "Didn’t happen", "resolved", "FINAL", "Final", "99.7%", "Reported finish", "race report", "164.32"]

        // Positive control: the same collector over the final page reaches every one.
        let final = Self.reachableOutputs(Self.page(.final), Self.originals(.final))
        for fact in later {
            XCTAssertTrue(final.contains { Self.mentions($0, fact) }, "the collector reaches “\(fact)” at the final")
        }

        // Meaning-aware tokens: a probability is never an ordinal or a score.
        XCTAssertFalse(Self.mentions("Absurde 7.2%", "7th"))
        XCTAssertFalse(Self.mentions("Reported finish: 17th", "7th"))
        XCTAssertFalse(Self.mentions("Royal Supremacy 4.4%", "4th"))
        XCTAssertFalse(Self.mentions("No retained Yes trade before the scheduled start · resolves", "resolved"))
        XCTAssertTrue(Self.mentions("Reported finish: 7th, Sporting Life", "7th"))

        for phase in [HorseRacingPhase10868.before, .during] {
            let outputs = Self.reachableOutputs(Self.page(phase), Self.originals(phase))
            XCTAssertGreaterThan(outputs.count, 300, "\(phase) collector reads the whole page")
            // Allowed: each runner's own pre-schedule chance, Other's status and the schedule.
            for words in ["18%", "49.9%", Self.noPreSchedule, Self.otherStatus, "Scheduled start", "Yes details", "No details"] {
                XCTAssertTrue(outputs.contains { $0.contains(words) }, "\(phase) shows “\(words)”")
            }
            for output in outputs {
                for fact in later {
                    XCTAssertFalse(Self.mentions(output, fact), "“\(fact)” reached \(phase): \(output)")
                }
            }
        }
    }

    func testTheOriginalEntryCarriesOnlyTheSelectedRunnersAdmittedObservation() {
        let label = "Explore Yes / No outcomes"
        // Each phase's default: the selected runner's Yes and ITS selected observation in that frame.
        let defaults: [(phase: HorseRacingPhase10868, name: String, position: Double, payload: String)] = [
            (.before, "Al Riffa", -1.75, "open:662191:Yes@-1.75"),
            (.during, "Presage Nocturne", 4.62, "open:662196:Yes@4.62"),
            (.final, "Half Yours", 164.32, "open:662204:Yes@164.32"),
        ]
        for item in defaults {
            let history = Self.history(item.phase)
            let originals = Self.originals(item.phase, history: history)
            let read = Self.openPayloads(Self.page(item.phase, history: history), originals)
            XCTAssertEqual(read.entry, HorseRacingOriginalOpen10868(label: label, selection: Self.selection(item.name, "Yes"),
                                                                    selectedPosition: item.position), "\(item.phase) entry")
            XCTAssertEqual(read.entry?.selection, originals.selection, "\(item.phase) entry and Details hold one exact selection")
            XCTAssertEqual(read.log, ["hold", item.payload], "\(item.phase) callback payload")
            XCTAssertTrue(Self.isAdmitted(read.entry, in: history), "\(item.phase) position is the selected observation")

            // Positive control: the old fixture — the final Half Yours position in
            // every phase — reaches the same entry and callback, and is caught
            // everywhere but the final, where it is the admitted observation.
            var leaked = originals
            leaked.open = HorseRacingOriginalOpen10868(label: label, selection: Self.selection(item.name, "Yes"), selectedPosition: 164.32)
            let old = Self.openPayloads(Self.page(item.phase, history: history), leaked)
            XCTAssertEqual(old.log, ["hold", "open:\(Self.runner(item.name).market):Yes@164.32"], "\(item.phase) control reaches the callback")
            XCTAssertEqual(Self.isAdmitted(old.entry, in: history), item.phase == .final, "\(item.phase) control")
            XCTAssertEqual(old.log == read.log, item.phase == .final, "\(item.phase) control payload")
            let oldOutputs = Self.reachableOutputs(Self.page(item.phase, history: history), leaked)
            XCTAssertTrue(oldOutputs.contains { Self.mentions($0, "164.32") }, "\(item.phase) control is visible to the phase guard")
        }

        // A held selected time moves the position with it — or to nil when the
        // selection admits no observation in that frame.
        let held: [(phase: HorseRacingPhase10868, name: String, frame: FieldHistoryInput10868, position: Double?)] = [
            (.before, "Al Riffa", Self.history(.before, inspect: .trade(1)), -375.28),
            (.during, "Presage Nocturne", Self.history(.during, inspect: .trade(2)), -44.75),
            // A later trade the constructed live frame does not admit.
            (.during, "Presage Nocturne", Self.history(.during, inspect: .trade(6)), nil),
            (.final, "Half Yours", Self.history(.final, inspect: .trade(8)), 10.82),
            (.final, "Half Yours", Self.history(.final, inspect: .trade(4)), -4.55),
            (.final, "Half Yours", Self.history(.final, inspect: .constructedEqual), -30),
            (.final, "Half Yours", Self.history(.final, inspect: .absent), nil),
            (.final, "Half Yours", Self.history(.final, inspect: .none), nil),
        ]
        for item in held {
            let read = Self.openPayloads(Self.page(item.phase, history: item.frame), Self.originals(item.phase, history: item.frame))
            let market = Self.runner(item.name).market
            XCTAssertEqual(read.entry, HorseRacingOriginalOpen10868(label: label, selection: Self.selection(item.name, "Yes"),
                                                                    selectedPosition: item.position), "\(item.phase) held \(String(describing: item.position))")
            XCTAssertEqual(read.log, ["hold", "open:\(market):Yes@\(item.position.map { String($0) } ?? "none")"])
            XCTAssertTrue(Self.isAdmitted(read.entry, in: item.frame))
            let old = HorseRacingOriginalOpen10868(label: label, selection: Self.selection(item.name, "Yes"), selectedPosition: 164.32)
            XCTAssertFalse(Self.isAdmitted(old, in: item.frame), "\(item.phase) held control")
        }

        // Nothing selected: no entry, no payload, in every phase.
        for phase in HorseRacingPhase10868.allCases {
            let unselected = Self.withSelection(Self.history(phase), .none)
            let read = Self.openPayloads(Self.page(phase, history: unselected), Self.originals(phase, history: unselected))
            XCTAssertNil(read.entry, "\(phase)")
            XCTAssertEqual(read.log, [], "\(phase)")
        }

        // An exact held Details selection stays exactly itself beside the anchor's own entry.
        var log: [String] = []
        var selected: [OriginalMarketDetails9483.Selection] = []
        let heldNo = Self.selection("Half Yours", "No")
        let heldOriginals = Self.originals(.final, held: heldNo)
        let view = HorseRacingEventPagePresentation10868(
            input: Self.page(.final), originals: heldOriginals,
            onOriginalOpen: { log.append(Self.payload($0)) }, onOriginalSelect: { selected.append($0) })
        XCTAssertEqual(heldOriginals.selection, heldNo)
        XCTAssertEqual(view.originalDetailsContent()?.selection, heldNo)
        XCTAssertEqual(view.originalCatalogueContent()?.selection, heldNo)
        XCTAssertEqual(view.originalEntry()?.selection, Self.selection("Half Yours", "Yes"))
        view.openOriginal()
        view.originalCatalogueContent()?.onSelect?(Self.selection("Buckaroo", "Yes"))
        if let side = view.originalSides().first(where: { $0.selection == heldNo }) { view.selectSide(side) }
        XCTAssertEqual(log, ["open:662204:Yes@164.32"])
        XCTAssertEqual(selected, [Self.selection("Buckaroo", "Yes"), heldNo])
    }

    func testEveryOriginalCarriesItsRetainedPredicateAndRulesVerbatim() {
        // The receipt: the four verified paragraphs ARE the retained 742-byte
        // text, split only at its blank lines, trailing spaces kept.
        XCTAssertEqual(Self.retainedRules.utf8.count, 742)
        XCTAssertEqual(Self.retainedRulesParagraphs.joined(separator: "\n\n"), Self.retainedRules)
        XCTAssertEqual(Self.retainedRules.components(separatedBy: "\n\n"), Self.retainedRulesParagraphs)
        XCTAssertTrue(Self.retainedRulesParagraphs[1].hasSuffix("resolve to \"Other\". "))
        XCTAssertTrue(Self.retainedRulesParagraphs[2].hasSuffix("alphabetical order. "))
        XCTAssertTrue(Self.retainedRules.contains("allowing time to account for any disputes or disqualifications that might occur post-race"))
        XCTAssertTrue(Self.retainedRules.contains("The primary resolution source for this market will be official information from Melbourne Cup race organizers"))

        // 25 retained predicates, one per market, each naming its own horse exactly.
        XCTAssertEqual(Self.retainedPredicates.count, 25)
        XCTAssertEqual(Set(Self.runners.map(\.market)), Set(Self.retainedPredicates.keys))
        for runner in Self.runners where runner.name != "Other" {
            XCTAssertEqual(Self.retainedPredicates[runner.market], "Will \(runner.name) win the 2025 Lexus Melbourne Cup?")
        }
        XCTAssertEqual(Self.retainedPredicates["662202"], "Will Smokin' Romans win the 2025 Lexus Melbourne Cup?")

        // Every one of the 50 exact sides opens Details with its own market's
        // predicate and the retained rules, unchanged, in every phase.
        XCTAssertEqual(Self.sides.count, 50)
        XCTAssertEqual(Set(Self.sides.map(\.selection.identity)).count, 50)
        XCTAssertTrue(Self.sides.allSatisfy { $0.selection.scope == Self.originalsScope })
        for phase in HorseRacingPhase10868.allCases {
            let catalogue = Self.detailsCatalogue(phase)
            XCTAssertEqual(catalogue.originals.count, 50)
            XCTAssertEqual(Set(catalogue.originals.map(\.identity)).count, 50)
            for side in Self.sides {
                guard let content = OriginalMarketDetails9483.content(catalogue: catalogue, selection: side.selection) else {
                    XCTFail("\(side.spokenLabel ?? side.label) resolves at \(phase)")
                    continue
                }
                XCTAssertEqual(content.title, Self.retainedPredicates[side.selection.identity.market], "\(phase) \(side.selection.identity)")
                XCTAssertEqual(content.rules, .verified(Self.retainedRulesParagraphs), "\(phase) \(side.selection.identity)")
            }
        }

        // Other keeps its special predicate, its own Yes / No words and status;
        // its special rules are the retained ones — cancellation resolves to
        // "Other" and a tie goes to the first name alphabetically.
        let other = Self.runner("Other")
        XCTAssertEqual(Self.retainedPredicates[other.market], "Will another horse win the 2025 Lexus Melbourne Cup?")
        let final = Self.detailsCatalogue(.final)
        XCTAssertEqual(OriginalMarketDetails9483.content(catalogue: final, selection: Self.selection("Other", "Yes"))?.outcome,
                       "Yes · another horse wins · special rules apply")
        XCTAssertEqual(OriginalMarketDetails9483.content(catalogue: final, selection: Self.selection("Other", "No"))?.outcome,
                       "No · another horse does not win · special rules apply")
        XCTAssertEqual(Self.catalogue.first { $0.name == "Other" }?.browseStatus, Self.otherStatus)
        XCTAssertTrue(Self.retainedRules.contains("If the race is permanently cancelled or doesn't take place by November 5, 2025, 11:59 PM ET, this market will resolve to \"Other\"."))
        XCTAssertTrue(Self.retainedRules.contains("the market will resolve in favor of the horse whose name appears first in alphabetical order."))
    }

    func testTheScheduleIsAnOwnerGuideAndNeverAnActualRaceClock() {
        for phase in HorseRacingPhase10868.allCases {
            let history = Self.history(phase)
            XCTAssertEqual(history.guides, [Self.schedule], "\(phase): one labelled schedule guide")
            let labels = history.guides.map(\.label) + history.xTicks.flatMap(\.lines) + history.yTicks.flatMap(\.lines)
            XCTAssertFalse(labels.contains { $0.localizedCaseInsensitiveContains("actual") || $0.localizedCaseInsensitiveContains("finish") })
        }
        // Before ends at the published schedule, labelled as before the scheduled start.
        let before = Self.history(.before)
        XCTAssertEqual(before.domain.upper, Self.schedule.x)
        XCTAssertTrue(Self.allPoints(before).allSatisfy { $0.x < Self.schedule.x })
        XCTAssertEqual(Self.header(.before).status, "Before scheduled start · published 3:00 PM Melbourne (Nov 3, 8:00 PM PT)")

        // The finish has no clock channel at all: an ordinal and its source.
        let card = Self.finishCard()
        XCTAssertEqual(card.finishes.first { $0.ref == Self.ref("Half Yours") }?.reading, FieldChooserReading10868(
            label: "Reported finish", value: .recorded(text: "1st", detail: "Sporting Life · by 2¾ lengths")))
        XCTAssertFalse(card.finishes.contains { reading in
            if case .recorded(_, let detail) = reading.reading.value { return detail.contains("PM") || detail.contains("AM") }
            return false
        })
        // The final frame's end is the owner's frame, beyond the last trade, never a finish point.
        let final = Self.history(.final)
        XCTAssertGreaterThan(final.domain.upper, Self.allPoints(final).map(\.x).max() ?? .infinity)
        XCTAssertTrue(Self.allPoints(final).allSatisfy { $0.probability > 0 && $0.probability < 1 })
    }

    func testEveryTradeIsAnIsolatedMarkWithNoLineAndNoSyntheticEndpoint() {
        let final = Self.history(.final)
        let halfYours = final.series[0]
        XCTAssertEqual(FieldHistoryGeometry10868.marks(halfYours, in: final).count, 14)
        XCTAssertTrue(FieldHistoryGeometry10868.lines(halfYours, in: final).isEmpty)
        XCTAssertEqual(FieldHistoryGeometry10868.marks(halfYours, in: final).map(\.probability).max(), 0.999)

        let cohort = Self.history(.final, cohort: true)
        XCTAssertEqual(cohort.series.map(\.name), ["Half Yours", "Al Riffa", "Presage Nocturne"])
        XCTAssertEqual(cohort.series.map(\.shape), [.circle, .triangle, .diamond])
        XCTAssertEqual(cohort.series.map { FieldHistoryGeometry10868.marks($0, in: cohort).count }, [14, 7, 8])
        XCTAssertTrue(cohort.series.allSatisfy { FieldHistoryGeometry10868.lines($0, in: cohort).isEmpty })
        XCTAssertEqual(Self.picks(.final, cohort: true).picks.map(\.shape), [.circle, .triangle, .diamond])
        XCTAssertEqual(Self.picks(.final).picks.map(\.shape), [nil, nil, nil])

        let before = Self.history(.before)
        XCTAssertEqual(FieldHistoryGeometry10868.marks(before.series[0], in: before).count, 6)
        XCTAssertEqual(before.ceiling, 0.5, "the owner's auto scale, with an owner full-scale action")
        XCTAssertEqual(before.scale?.label, "0–100%")
        XCTAssertEqual(before.probabilityLowerBound, 0, "no hidden crop")
    }

    func testAMissingPreScheduleChanceStaysMissingIncludingGoodieTwoShoes() {
        // The history: Goodie's later trades never stand in for its before slot.
        let goodie = Self.history(.final, selected: "Goodie Two Shoes")
        guard case .original(_, let slots) = FieldHistoryGeometry10868.selectedSummary(goodie) else { return XCTFail("Goodie is selected") }
        XCTAssertEqual(slots, [
            FieldHistoryReadoutSlot10868(label: "Before scheduled start", display: .words(Self.noPreScheduleTrade)),
            FieldHistoryReadoutSlot10868(label: "Selected trade", display: .figure("0.1%", provenance: "Nov 3, 8:07:29 PM PT")),
        ])
        let beforeGoodie = Self.history(.before, selected: "Goodie Two Shoes")
        XCTAssertEqual(beforeGoodie.plotAbsence?.title, "No retained Yes trades")
        XCTAssertTrue(Self.allPoints(beforeGoodie).isEmpty)

        // The catalogue: all five without a pre-schedule trade keep their own words and no dot.
        var missing: [String] = []
        for group in 1...5 {
            let model = HorseCatalogueModel10868(Self.catalogueInput(.final, group: group, finishes: Self.finalFinishes))
            for row in model.rows {
                if case .value = row.chance { continue }
                missing.append(row.slot.name)
                XCTAssertEqual(model.figure(row), Self.noPreSchedule)
                XCTAssertNil(model.stateWords(row), "a missing reading is its own words, not a scale state")
                XCTAssertFalse(model.isRecorded(row))
            }
        }
        XCTAssertEqual(missing, ["More Felons", "Parchment Party", "Goodie Two Shoes", "Torranzino", "Other"])

        let fourth = HorseCatalogueModel10868(Self.catalogueInput(.final, group: 4, finishes: Self.finalFinishes))
        let row = fourth.rows[4]
        XCTAssertEqual(row.slot.name, "Goodie Two Shoes")
        XCTAssertEqual(HorseCatalogueModel10868.ordinal(row), "2nd")
        XCTAssertFalse(fourth.rowSummary(row).contains("0.1%"))
        XCTAssertFalse(fourth.rowSummary(row).contains("91.1%"))

        // The finish card: Goodie's figure is its absence words, with no dot label.
        let card = FieldFinishModel10868(Self.finishCard())
        let goodieRow = card.rows[1]
        XCTAssertEqual(card.figure(goodieRow), Self.noPreSchedule)
        XCTAssertNil(card.dotLabel(goodieRow))
        XCTAssertEqual(FieldFinishModel10868.ordinal(goodieRow.finish), "2nd")
    }

    func testTheSelectedObservationKeepsItsOwnMeaningDistinctEqualSameOrMissing() {
        // Distinct: the dated pre-schedule trade beside a later selected trade.
        let distinct = FieldHistoryGeometry10868.selectedSlots(Self.history(.final).series[0], in: Self.history(.final))
        XCTAssertEqual(distinct.map(\.label), ["Before scheduled start", "Selected trade"])

        // Equal-valued but distinct (CONSTRUCTED 15%): two slots, each with its own clock.
        let equal = Self.history(.final, inspect: .constructedEqual)
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSlots(equal.series[0], in: equal), [
            FieldHistoryReadoutSlot10868(label: "Before scheduled start", display: .figure("15%", provenance: "Nov 3, 7:55:27 PM PT · last trade before the published schedule")),
            FieldHistoryReadoutSlot10868(label: "Selected trade", display: .figure("15%", provenance: "CONSTRUCTED · Nov 3, 7:30:00 PM PT")),
        ])

        // The very same observation: the owner's single-slot intent.
        let same = Self.history(.final, inspect: .trade(4))
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSlots(same.series[0], in: same), [
            FieldHistoryReadoutSlot10868(label: "Before scheduled start · selected trade", display: .figure("15%", provenance: "Nov 3, 7:55:27 PM PT")),
        ])

        // A selected time with no trade stays absent — never a neighbour's figure.
        let absent = Self.history(.final, inspect: .absent)
        let absentSlots = FieldHistoryGeometry10868.selectedSlots(absent.series[0], in: absent)
        XCTAssertEqual(absentSlots[1], FieldHistoryReadoutSlot10868(label: "Selected trade", display: .words(Self.noTradeHere)))
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(absent.series[0], in: absent))

        // Restored: the exact trade's own figure returns.
        let restored = Self.history(.final, inspect: .trade(8))
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSlots(restored.series[0], in: restored)[1].display,
                       .figure("99%", provenance: "Nov 3, 8:10:49 PM PT"))
        // And the full-size history carries the same selection.
        XCTAssertEqual(HorseRacingPageModel10868(Self.page(.final, history: restored)).readerHistory.inspection, restored.inspection)
    }

    func testFiveKnownFinishesUnknownsAndOtherStayFixedWhileOlderTradesAreInspected() {
        let card = FieldFinishModel10868(Self.finishCard())
        XCTAssertEqual(card.rows.map(\.slot.name), Self.finishOrder)
        XCTAssertEqual(card.rows.map { FieldFinishModel10868.ordinal($0.finish) }, ["1st", "2nd", "3rd", "4th", "7th"])
        XCTAssertEqual(card.rows.map { card.dotLabel($0) }, ["15%", nil, "49.9%", "39%", "18%"])
        XCTAssertEqual(card.rowSummary(card.rows[0]), "In the chart. Reported finish: 1st, Sporting Life · by 2¾ lengths. Before scheduled start: 15%, Nov 3, 7:55:27 PM PT · last trade before the published schedule")

        // The catalogue at the final: five ordinals, nineteen unknowns, Other's own words.
        var ordinals: [String: String] = [:]
        var unknown = 0
        var otherWords: String?
        for group in 1...5 {
            let model = HorseCatalogueModel10868(Self.catalogueInput(.final, group: group, finishes: Self.finalFinishes))
            for row in model.rows {
                if let ordinal = HorseCatalogueModel10868.ordinal(row) { ordinals[row.slot.name] = ordinal }
                if HorseCatalogueModel10868.finishWords(row) == "Finish not recorded" { unknown += 1 }
                if row.slot.name == "Other" {
                    otherWords = HorseCatalogueModel10868.finishWords(row)
                    XCTAssertEqual(model.status(row), Self.otherStatus)
                }
            }
        }
        XCTAssertEqual(ordinals, ["Half Yours": "1st", "Goodie Two Shoes": "2nd", "Middle Earth": "3rd", "River of Stars": "4th", "Al Riffa": "7th"])
        XCTAssertEqual(unknown, 19)
        XCTAssertEqual(otherWords, Self.otherFinish, "Other is a special outcome, not an ordinary missing finish")

        // Before the race Other keeps its status words and no finish.
        let early = HorseCatalogueModel10868(Self.catalogueInput(.before, group: 5, finishes: Self.finalFinishes))
        XCTAssertEqual(early.status(early.rows[4]), Self.otherStatus)
        XCTAssertNil(early.rows[4].finish, "a final channel handed to the before catalogue is never read")

        // Inspecting an older trade changes the history only.
        let page = Self.page(.final)
        let inspected = Self.page(.final, history: Self.history(.final, inspect: .trade(2)))
        XCTAssertNotEqual(inspected.history, page.history)
        XCTAssertEqual(HorseRacingPageModel10868(inspected).finish, HorseRacingPageModel10868(page).finish)
        XCTAssertEqual(HorseRacingPageModel10868(inspected).catalogue, HorseRacingPageModel10868(page).catalogue)

        // The finish and the contract grade are separate channels.
        let details = Self.detailsCatalogue(.final)
        XCTAssertEqual(OriginalMarketDetails9483.content(catalogue: details, selection: Self.selection("Middle Earth", "Yes"))?.result?.words, "Didn’t happen")
        XCTAssertEqual(ordinals["Middle Earth"], "3rd")
        let ungraded = OriginalMarketDetails9483.Catalogue(scope: Self.originalsScope, originals: [Self.original(Self.runner("Half Yours"), "Yes", .final, grade: false)])
        XCTAssertEqual(OriginalMarketDetails9483.content(catalogue: ungraded, selection: Self.selection("Half Yours", "Yes"))?.result?.words,
                       OriginalMarketDetails9483.resultUnavailable, "a missing grade is never read from the finish")
        XCTAssertEqual(FieldFinishModel10868.ordinal(card.rows[0].finish), "1st")
    }

    func testNoIsItsOwnOriginalNeverAComplementOfYes() {
        let details = Self.detailsCatalogue(.before)
        let yes = OriginalMarketDetails9483.content(catalogue: details, selection: Self.selection("Half Yours", "Yes"))
        let no = OriginalMarketDetails9483.content(catalogue: details, selection: Self.selection("Half Yours", "No"))
        XCTAssertEqual(yes?.readings.map(\.text), ["15%"])
        XCTAssertEqual(no?.readings.map(\.text), ["86%"], "its own trade, not 100 − 15")
        XCTAssertEqual(no?.readings.map(\.label), ["Before scheduled start"])
        let buckarooNo = OriginalMarketDetails9483.content(catalogue: details, selection: Self.selection("Buckaroo", "No"))
        XCTAssertEqual(buckarooNo?.readings.map(\.text), ["No retained No trade before the scheduled start"])
        let otherNo = OriginalMarketDetails9483.content(catalogue: details, selection: Self.selection("Other", "No"))
        XCTAssertEqual(otherNo?.outcome, "No · another horse does not win · special rules apply")
        XCTAssertNil(yes?.result, "no grade before the race")
    }

    // MARK: Catalogue

    func testAll25RowsAnd50YesNoActionsAreReachableAcrossTheGroupsOnOneScale() {
        var names: [String] = []
        var selections: [OriginalMarketDetails9483.Selection] = []
        var scaleWords = Set<String>()
        var tickSets: [[Double]] = []
        let details = Self.detailsCatalogue(.final)
        var group: String? = "group.1"
        var visited: [String] = []
        // Walk the owner's own next steps from the first group.
        while let current = group, visited.count < 10 {
            visited.append(current)
            let index = (Self.groups.firstIndex { $0.id == current } ?? -1) + 1
            let view = HorseCatalogueView10868(input: Self.catalogueInput(.final, group: index, finishes: Self.finalFinishes),
                                               sides: Self.sides, originals: details, onRunner: { _ in }, onSide: { _ in }, onGroup: { _ in })
            let model = view.model
            scaleWords.insert(model.scaleWords ?? "")
            tickSets.append(model.ticks.map(\.fraction))
            for row in model.rows {
                names.append(row.slot.name)
                XCTAssertNotNil(model.openRef(row, canOpen: true))
                let states = view.sideStates(row)
                XCTAssertEqual(states.map(\.side.label), ["Yes details", "No details"])
                selections += states.compactMap(\.selection)
            }
            group = model.stepTarget(view.input.next, canMove: true)
        }
        XCTAssertEqual(visited, ["group.1", "group.2", "group.3", "group.4", "group.5"])
        XCTAssertEqual(names, Self.runners.map(\.name))
        XCTAssertEqual(selections.count, 50)
        XCTAssertEqual(Set(selections.map(\.identity)).count, 50)
        XCTAssertEqual(scaleWords, ["0–50%"], "one catalogue-wide scale")
        XCTAssertEqual(Set(tickSets.map { $0.map { ($0 * 100).rounded() } }).count, 1)

        // The previous step at the first group and the next at the last are absent.
        XCTAssertNil(HorseCatalogueModel10868(Self.catalogueInput(.final, group: 1)).stepTarget(Self.catalogueInput(.final, group: 1).previous, canMove: true))
        XCTAssertNil(HorseCatalogueModel10868(Self.catalogueInput(.final, group: 5)).stepTarget(Self.catalogueInput(.final, group: 5).next, canMove: true))
        // Dots sit on the shared scale: Middle Earth 49.9% at 0.998 of the 0–50% scale.
        let middle = HorseCatalogueModel10868(Self.catalogueInput(.final, group: 2)).rows[1]
        XCTAssertEqual(middle.chance.fraction ?? -1, 0.998, accuracy: 1e-9)
        XCTAssertEqual(HorseCatalogueModel10868(Self.catalogueInput(.final, group: 1)).position, "1–5 of 25")
    }

    func testArbitraryDuplicateForeignAndWithdrawnRowsKeepTheirNamesAndBorrowNothing() {
        let foreign = FieldChooserOriginalRef10868(scope: "constructed.scope.other-race", source: "polymarket", marketID: "662192", outcomeID: "yes")
        let withdrawn = FieldChooserOriginalRef10868(scope: Self.raceScope, source: "polymarket", marketID: "constructed.withdrawn", outcomeID: "yes")
        var duplicated = Self.catalogue
        duplicated.append(Self.catalogue[2]) // Arapaho twice: ambiguous
        let rows = [
            FieldFinishSlot10868(ref: Self.ref("Al Riffa"), name: "Al Riffa"),
            FieldFinishSlot10868(ref: withdrawn, name: "CONSTRUCTED withdrawn runner"),
            FieldFinishSlot10868(ref: Self.ref("Arapaho"), name: "Arapaho"),
            FieldFinishSlot10868(ref: foreign, name: "Buckaroo (another race)"),
            FieldFinishSlot10868(ref: Self.ref("Vauban"), name: "Vauban"),
            FieldFinishSlot10868(ref: Self.ref("Vauban"), name: "Vauban"),
            FieldFinishSlot10868(ref: Self.ref("Chevalier Rose"), name: "Chevalier Rose"),
        ]
        let input = Self.catalogueInput(.final, groups: [HorseCatalogueGroup10868(id: "constructed", label: "CONSTRUCTED group", rows: rows)],
                                        currentGroupID: "constructed", runnerCatalogue: duplicated, finishes: Self.finalFinishes)
        let view = HorseCatalogueView10868(input: input, sides: Self.sides, originals: Self.detailsCatalogue(.final))
        let model = view.model
        let shown = model.rows
        XCTAssertEqual(shown.map(\.slot.name), rows.map(\.name), "every row keeps its place and name")
        XCTAssertEqual(shown.map { $0.resolution.original != nil }, [true, false, false, false, false, false, true])
        for row in shown where row.resolution.original == nil {
            XCTAssertEqual(model.rowSummary(row), "\(row.slot.name). \(Self.unavailableRunner)")
            XCTAssertNil(model.figure(row))
            XCTAssertNil(row.finish)
            XCTAssertNil(model.openRef(row, canOpen: true))
            XCTAssertTrue(view.sideStates(row).isEmpty)
        }
        XCTAssertEqual(model.figure(shown[0]), "18%")
        XCTAssertEqual(HorseCatalogueModel10868.ordinal(shown[0]), "7th")
        XCTAssertEqual(model.figure(shown[6]), "2.7%")
        XCTAssertEqual(view.sideStates(shown[6]).compactMap(\.selection).count, 2)

        // A side the shared Details do not resolve draws no action; its neighbour keeps its own.
        let withoutNo = OriginalMarketDetails9483.Catalogue(
            scope: Self.originalsScope,
            originals: Self.detailsCatalogue(.final).originals.filter { $0.identity != Self.identity("Al Riffa", "No") })
        let partial = HorseCatalogueView10868(input: input, sides: Self.sides, originals: withoutNo)
        XCTAssertEqual(partial.sideStates(shown[0]).map { $0.selection != nil }, [true, false])

        // The groups themselves: an unknown current group shows the owner's words and no other group's rows.
        let lost = HorseCatalogueModel10868(Self.catalogueInput(.final, currentGroupID: "group.9"))
        XCTAssertEqual(lost.groupWords, "Group unavailable in this update")
        XCTAssertTrue(lost.rows.isEmpty)
        XCTAssertNil(lost.position)
    }

    // MARK: Callbacks

    func testPageActionsHoldOnceAndFullSizeAndTextContentKeepExactCallbacks() {
        var log: [String] = []
        let input = Self.page(.final)
        let originals = Self.originals(.final)
        let intent = OriginalMarketDetails9483.HistoryIntent(selection: Self.selection("Half Yours", "Yes"), entry: .explore, actionID: "explore")
        func view(_ mode: HorseRacingMode10868 = .page, hook: Bool = true) -> HorseRacingEventPagePresentation10868 {
            HorseRacingEventPagePresentation10868(
                input: input, mode: mode, originals: originals,
                onAbout: { log.append("about") },
                onSource: { log.append("source") },
                onLink: { log.append("link:\($0)") },
                onRunner: { log.append("runner:\($0.marketID)") },
                onRunnerHistory: { log.append("history-of:\($0.marketID)") },
                onToggle: { log.append("toggle:\($0)") },
                onHistoryAction: { log.append("history:\($0)") },
                onHistoryInspectionChoice: { log.append("inspect:\($0)") },
                onHistoryPlotPosition: { log.append("plot:\($0)") },
                onOriginalOpen: { log.append("open:\($0.selection.identity.market):\($0.selection.identity.side)@\($0.selectedPosition ?? -1)") },
                onFinishExpand: { log.append("finish:expand") },
                onCatalogueGroup: { log.append("group:\($0)") },
                onOriginalSelect: { log.append("select:\($0.identity.market):\($0.identity.side)") },
                onOriginalHistory: { log.append("details:\($0.actionID)") },
                onAllOriginals: { log.append("all-originals") },
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        // Building and reading every leaf calls nothing.
        let page = view()
        let picks = page.picksContent()
        let anchor = page.historyContent(reader: false)
        let finish = page.finishContent(reader: false)
        let result = page.resultSourceContent(reader: false)
        let catalogue = page.catalogueContent()
        _ = page.originalCatalogueContent()
        _ = page.originalDetailsContent()
        _ = page.aboutContent()
        _ = page.sourceContent()
        _ = page.historyContent(reader: true)
        _ = page.finishContent(reader: true)
        _ = page.originalSides()
        _ = page.originalEntry()
        XCTAssertEqual(log, [])

        page.headerAbout()?()
        picks?.onChoose?(Self.ref("Al Riffa"))
        if let id = picks?.cohortID { picks?.onToggle?(id) }
        anchor.onAction?("history.expand")
        anchor.onInspectionChoice?("trade.8")
        anchor.onPlotPosition?(10.82)
        page.openOriginal()
        page.openSource()
        finish?.onOpenHistory?(Self.ref("Middle Earth"))
        page.openFinish()
        if let link = result?.link { result?.onLink?(link.id) }
        page.toggleCatalogue()
        catalogue?.onRunner?(Self.ref("Al Riffa"))
        catalogue?.onSide?(Self.selection("Al Riffa", "No"))
        catalogue?.onGroup?("group.2")
        page.openAllOriginals()
        view(.catalogue).originalCatalogueContent()?.onSelect?(Self.selection("Buckaroo", "Yes"))
        view(.original).originalDetailsContent()?.onHistory?(intent)
        if let no = view(.original).originalSides().last { view(.original).selectSide(no) }
        XCTAssertEqual(log, [
            "hold", "about", "hold", "runner:662191", "hold", "toggle:cohort",
            "hold", "history:history.expand", "hold", "inspect:trade.8", "hold", "plot:10.82",
            "hold", "open:662204:Yes@164.32", "hold", "source", "hold", "history-of:662197",
            "hold", "finish:expand", "hold", "link:result.report", "hold", "toggle:catalogue",
            "hold", "history-of:662191", "hold", "select:662191:No", "hold", "group:group.2",
            "hold", "all-originals", "hold", "select:662192:Yes", "hold", "details:explore",
            "hold", "select:662204:No",
        ])

        // Full-size and text content: the exact callbacks, no hold.
        log = []
        view(.fullHistory).historyContent(reader: true).onAction?("scale.full")
        view(.fullFinish).finishContent(reader: true)?.onOpenHistory?(Self.ref("River of Stars"))
        if let link = view(.fullFinish).resultSourceContent(reader: true)?.link {
            view(.fullFinish).resultSourceContent(reader: true)?.onLink?(link.id)
        }
        view(.fullFinish).openReaderAbout()
        if let link = view(.about).aboutContent()?.link { view(.about).aboutContent()?.onLink?(link.id) }
        XCTAssertEqual(log, ["history:scale.full", "history-of:662211", "link:result.report", "about", "link:schedule.source"])
        XCTAssertTrue(HorseRacingPageModel10868(input).aboutEntry(mode: .fullFinish, canOpen: true))
        XCTAssertFalse(HorseRacingPageModel10868(input).aboutEntry(mode: .page, canOpen: true))

        // No callback: no control and no hold.
        log = []
        let silent = HorseRacingEventPagePresentation10868(input: input, originals: originals, onInteraction: { log.append("hold") })
        XCTAssertNil(silent.headerAbout())
        XCTAssertNil(silent.picksContent()?.onChoose)
        XCTAssertNil(silent.picksContent()?.cohortID)
        XCTAssertNil(silent.historyContent(reader: false).onAction)
        XCTAssertNil(silent.finishContent(reader: false)?.onOpenHistory)
        XCTAssertNil(silent.resultSourceContent(reader: false)?.link)
        XCTAssertNil(silent.catalogueContent()?.onRunner)
        XCTAssertNil(silent.catalogueContent()?.onSide)
        XCTAssertNil(silent.catalogueContent()?.onGroup)
        XCTAssertNil(silent.originalEntry())
        XCTAssertNil(silent.originalCatalogueContent()?.onSelect)
        silent.openSource()
        silent.openAllOriginals()
        silent.openFinish()
        silent.openOriginal()
        silent.toggleCatalogue()
        silent.openReaderAbout()
        XCTAssertEqual(log, [])

        // Two toggles sharing one id: neither acts.
        var shared = input
        shared.catalogueDisclosure = HorseRacingToggle10868(id: "cohort", label: "All 25 winner props", isOn: true)
        XCTAssertNil(HorseRacingPageModel10868(shared).cohortID(canToggle: true))
        XCTAssertNil(HorseRacingPageModel10868(shared).catalogueToggleID(canToggle: true))
        // A collapsed disclosure keeps the toggle and hides the catalogue.
        var collapsed = input
        collapsed.catalogueDisclosure = HorseRacingToggle10868(id: "catalogue", label: "All 25 winner props", isOn: false)
        XCTAssertNil(HorseRacingEventPagePresentation10868(input: collapsed, onToggle: { _ in }).catalogueContent())
        XCTAssertEqual(HorseRacingPageModel10868(collapsed).catalogueToggleID(canToggle: true), "catalogue")
        // An original entry the shared Details do not resolve draws nothing.
        let unresolved = Self.originals(.final, catalogue: OriginalMarketDetails9483.Catalogue(scope: Self.originalsScope, originals: []))
        XCTAssertNil(HorseRacingEventPagePresentation10868(input: input, originals: unresolved, onOriginalOpen: { _ in }).originalEntry())

        // No hook: each page callback is the owner's own.
        view(hook: false).openAllOriginals()
        view(hook: false).finishContent(reader: false)?.onOpenHistory?(Self.ref("Half Yours"))
        XCTAssertEqual(log, ["all-originals", "history-of:662204"])
    }

    // MARK: Full size and held state

    func testFullSizeContentIsTheSameViewsWithTheSameInputs() {
        let input = Self.page(.final, cohort: true)
        let model = HorseRacingPageModel10868(input)
        let reader = model.readerHistory
        XCTAssertNil(reader.expand)
        XCTAssertEqual(reader.plotHeight, 340)
        XCTAssertEqual(reader.layout, input.history.layout)
        XCTAssertEqual(reader.series, input.history.series)
        XCTAssertEqual(reader.guides, input.history.guides)
        XCTAssertEqual(reader.selection, input.history.selection)
        XCTAssertEqual(reader.inspection, input.history.inspection)
        XCTAssertEqual(reader.selectedReadout, input.history.selectedReadout)
        XCTAssertEqual(reader.previous, input.history.previous)
        XCTAssertEqual(reader.next, input.history.next)
        XCTAssertEqual(HorseRacingEventPagePresentation10868(input: input, mode: .fullHistory).historyContent(reader: true).input, reader)

        let page = HorseRacingEventPagePresentation10868(input: input)
        let full = HorseRacingEventPagePresentation10868(input: input, mode: .fullFinish)
        XCTAssertEqual(full.finishContent(reader: true)?.input, page.finishContent(reader: false)?.input)
        XCTAssertEqual(full.resultSourceContent(reader: true)?.text, page.resultSourceContent(reader: false)?.text)

        var plain = input
        plain.readerPlotHeight = nil
        XCTAssertEqual(HorseRacingPageModel10868(plain).readerHistory.plotHeight, 260)
    }

    func testHeldRunnerOriginalGroupAndInspectionSurviveOmissionRestoreAndModes() {
        // The held runner omitted from the update: the owner's words, no other runner selected.
        let omitted = Self.catalogue.filter { $0.name != "Half Yours" }
        let picks = HorseRacingPicksInput10868(
            scope: Self.raceScope, catalogue: omitted, selected: Self.selected("Half Yours"),
            groupLabel: "Featured runner histories",
            picks: Self.cohortNames(.final).map { HorseRacingPick10868(ref: Self.ref($0), shape: nil) },
            cohort: nil, unavailableWords: Self.unavailableRunner, chooseHint: nil)
        let picksModel = HorseRacingPicksModel10868(picks)
        XCTAssertEqual(picksModel.notice, Self.selectedMissing)
        XCTAssertEqual(picksModel.rows.map { $0.resolution.original?.name }, [nil, "Al Riffa", "Presage Nocturne"])
        XCTAssertFalse(picksModel.rows.contains { picksModel.isSelected($0) })
        XCTAssertEqual(HorseCatalogueModel10868(Self.catalogueInput(.final, group: 3, runnerCatalogue: omitted)).notice, Self.selectedMissing)
        // Restored: selected again.
        let restored = HorseRacingPicksModel10868(Self.picks(.final))
        XCTAssertNil(restored.notice)
        XCTAssertEqual(restored.rows.map { restored.isSelected($0) }, [true, false, false])

        // The held history selection omitted: the owner's words in place of any neighbour.
        let history = Self.history(.final, cohort: true)
        let withoutHeld = FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: Array(history.series.dropFirst()), selection: history.selection,
            domain: history.domain, ceiling: history.ceiling, yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides,
            breaks: history.breaks, readout: history.readout, markKey: history.markKey, comparisonExplanation: nil, notes: history.notes,
            summary: history.summary, plotHeight: history.plotHeight, unboundReadingWords: history.unboundReadingWords,
            plotUnavailableWords: nil, windows: nil, scale: nil, moreOriginals: nil, details: nil, expand: history.expand, inspect: nil,
            previous: history.previous, next: history.next, inspection: history.inspection, layout: .focused,
            selectedReadout: history.selectedReadout)
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(withoutHeld), .words("Selected runner has no history in this view"))

        // The held original through every mode and phase, never replaced.
        let modes: [HorseRacingMode10868] = [.page, .fullHistory, .fullFinish, .catalogue, .original, .about, .source]
        for phase in HorseRacingPhase10868.allCases {
            let held = Self.selection("Half Yours", "No")
            for mode in modes {
                let view = HorseRacingEventPagePresentation10868(input: Self.page(phase), mode: mode, originals: Self.originals(phase, held: held))
                XCTAssertEqual(view.originalDetailsContent()?.selection, held)
                XCTAssertEqual(view.originalCatalogueContent()?.selection, held)
                XCTAssertEqual(view.originalSides().map(\.side.label), ["Yes details", "No details"])
                XCTAssertEqual(view.historyContent(reader: mode == .fullHistory).input.inspection, Self.page(phase).history.inspection)
            }
        }
        // The held original omitted: no Details, no sides borrowed from a neighbour.
        let held = Self.selection("Half Yours", "No")
        let without = OriginalMarketDetails9483.Catalogue(scope: Self.originalsScope,
                                                          originals: Self.detailsCatalogue(.final).originals.filter { $0.identity != held.identity })
        XCTAssertNil(OriginalMarketDetails9483.content(catalogue: without, selection: held))
        let omittedView = HorseRacingEventPagePresentation10868(input: Self.page(.final), mode: .original,
                                                                originals: Self.originals(.final, held: held, catalogue: without))
        XCTAssertEqual(omittedView.originalDetailsContent()?.selection, held)
        XCTAssertEqual(omittedView.originalSides().map { $0.selection != nil }, [true, false])

        // The held group: omitted from an update, the owner's words; restored, the same rows.
        let fewer = Array(Self.groups.prefix(2))
        XCTAssertEqual(HorseCatalogueModel10868(Self.catalogueInput(.final, groups: fewer, currentGroupID: "group.4")).groupWords,
                       "Group unavailable in this update")
        XCTAssertEqual(HorseCatalogueModel10868(Self.catalogueInput(.final, group: 4)).rows.map(\.slot.name),
                       ["Onesmoothoperator", "Furthur", "Parchment Party", "Athabascan", "Goodie Two Shoes"])
        // A catalogue from another phase is not mounted.
        var foreign = Self.page(.before)
        foreign.catalogue = Self.catalogueInput(.final)
        XCTAssertNil(HorseRacingPageModel10868(foreign).catalogue)
    }

    // MARK: Layout

    func testCatalogueAndPickPlansReflowForPhoneWideAndAccessibilitySizes() {
        func columns(_ available: CGFloat?, ax: Bool = false) -> Int {
            HorseCatalogueGeometry10868.columns(count: 5, available: available, minimumWidth: 150, spacing: 10, maximum: 4, accessibilitySize: ax)
        }
        // 375- and 393-point phones (311 and 329 points inside the page and card padding).
        XCTAssertEqual(columns(311), 2)
        XCTAssertEqual(columns(329), 2)
        XCTAssertEqual(columns(900), 4, "at most the owner's maximum")
        XCTAssertEqual(columns(240), 1)
        XCTAssertEqual(columns(900, ax: true), 1)
        XCTAssertEqual(columns(nil), 1)
        XCTAssertEqual(HorseCatalogueGeometry10868.columns(count: 1, available: 900, minimumWidth: 150, spacing: 10, maximum: 4, accessibilitySize: false), 1)
        XCTAssertEqual(HorseCatalogueGeometry10868.lines(count: 5, columns: 2), [[0, 1], [2, 3], [4]])
        XCTAssertEqual(HorseCatalogueGeometry10868.lines(count: 5, columns: 4), [[0, 1, 2, 3], [4]])

        // Picks wrap at their whole widths; one wider than the line keeps a line of its own.
        XCTAssertEqual(HorseCatalogueGeometry10868.wrap(widths: [90, 140, 100], available: 311, spacing: 6), [[0, 1], [2]])
        XCTAssertEqual(HorseCatalogueGeometry10868.wrap(widths: [90, 400, 100], available: 311, spacing: 6), [[0], [1], [2]])
        XCTAssertEqual(HorseCatalogueGeometry10868.wrap(widths: [90, 140, 100], available: 900, spacing: 6), [[0, 1, 2]])
        XCTAssertEqual(HorseCatalogueGeometry10868.symbol(.triangle), "triangle.fill")

        XCTAssertEqual(HorseRacingPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(HorseRacingPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(HorseRacingPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(HorseRacingPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
    }

    // MARK: Helpers

    private static func slots(_ input: FieldHistoryInput10868) -> [[FieldHistoryReadoutSlot10868]] {
        input.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: input) }
    }

    private static func allPoints(_ input: FieldHistoryInput10868) -> [FieldHistoryPoint10868] {
        input.series.flatMap { $0.runs.flatMap(\.points) }
    }
}
