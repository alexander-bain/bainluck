import CryptoKit
import SwiftUI
import XCTest
@testable import Bain_Luck

// #10868 — darts set-comeback page (`darts-sets`). Prepared source checks; NOT
// RUN (no build, simulator, XCTest or typecheck grant for this package).
//
// RETAINED FIXTURE: World Grand Prix, Gerwyn Price vs Luke Humphries, Oct 4
// 2026 — Polymarket event 1128105, market 5263083, the exact retained condition
// and both outcome tokens, from the approved `dartsSetsCapture.json`. The
// scheduled 18:00Z (1791136800) is the listed start, not an actual start; the
// report's 22:05Z (1791151500) is a publication cutoff, not an actual end.
// Actual start, actual end, set wall clocks and a projection are null. Only
// SIX positive-size exact-token trades exist through the report cutoff: five
// for Price and one for Humphries, retained below with their raw time,
// probability, size and transaction. Humphries has NO captured pre-match
// trade. The 252 sampled CLOB quotes are unqualified source evidence and are
// retained here as a receipt only: no fixture uses them. The ten cumulative
// set rows, the source-text bindings and the contract rules are retained
// verbatim. These rows were read from the capture by the test author; NOTHING
// here ports an election into the product: the owner elects, validates and
// formats.
//
// PHASE-ADMITTED OWNER FIXTURES. Every ordinary input carries only what its
// phase admits: before play the pre-match chance or its absence, the trades
// strictly before the listed start, the originals at their pre-match readings
// and a before About (contract rules may show verbatim; the six-trade report
// paragraph never does); during play the same plus the trades up to a
// CONSTRUCTED in-play cut (20:10Z, `constructedLiveCut`) — genuine live
// evidence does not exist, so every in-play value is CONSTRUCTED from that cut
// and is labelled so here and in the owner's own notice — with no set score,
// result or report; at the final everything, with the reported actual sets
// kept apart from the contract grades and from the historical chances. Inputs
// that hand a later fact to an earlier phase are named hostile controls; they
// show the page's structural phase gates and never authorize a history or
// prose filter. Fixture clock words are CONSTRUCTED UTC copy and figures are
// the test's stand-in for the owner formatter (at most one decimal); real
// production binding must use the existing owner formatter.
//
// PREPARED ROSTER (NOT RUN): see the `func test…` list; each name states the
// obligation it checks.

@MainActor
final class DartsSetEventPagePresentation10868Tests: XCTestCase {
    private typealias Tests = DartsSetEventPagePresentation10868Tests
    private typealias Page = DartsSetEventPagePresentation10868
    private typealias Model = DartsSetEventPageModel10868
    private typealias SetModel = DartsSetStoryModel10868
    private typealias Details = OriginalMarketDetails9483
    private typealias Phase = DartsSetEventPagePhase10868

    // MARK: - Retained data

    private static let retainedEventID = "1128105"
    private static let retainedMarketID = "5263083"
    private static let retainedCondition = "0x956e7aba0296fe77c918134d53f361e929187522cdd046d0fff0dfb01c078c80"
    private static let retainedTitle = "World Grand Prix: Gerwyn Price vs Luke Humphries"
    private static let retainedTitleHash = "0cc64be5f461444b87ba00b9d78dca240412616f46a867fc58f9532cce8ded30"
    private static let retainedProviderURL = "https://polymarket.com/event/pdcdarts-price-humphri-2026-10-04"
    private static let retainedResultSource = "https://www.skysports.com/darts/news/13595109/world-grand-prix-darts-luke-humphries-beats-gerwyn-price-6-4-after-epic-comeback-to-claim-major-title"
    private static let retainedActualUnit = "sets"
    /// `actualStart`, `actualEnd`, `setWallClocks` and `projection` are null in the capture.
    private static let retainedNullFields = ["actualStart", "actualEnd", "setWallClocks", "projection"]
    private static let retainedQuoteSamples = 252
    private static let retainedQuoteAdmission = "252 CLOB price samples retained only in source evidence. Book age/spread unavailable; they do not become trusted traded probabilities."
    private static let retainedSourceText = [
        "firstThree": "rallied from 3-0 down",
        "fourThroughSeven": "four consecutive sets from Humphries",
        "eighth": "sweeping the eighth set",
        "ninthAndTenth": "racing through the next set in straight legs",
    ]

    private static let retainedRulesParagraphs = [
        "This market refers to the darts match between Gerwyn Price and Luke Humphries in the World Grand Prix, originally scheduled for October 4 at 2:00PM ET.",
        "This market will resolve to 'Gerwyn Price' if Gerwyn Price wins against Luke Humphries. This market will resolve to 'Luke Humphries' if Luke Humphries wins against Gerwyn Price.",
        "If the match is canceled (not played at all), ends in a tie, or is delayed beyond 7 days from the scheduled date without a winner determined, this market will resolve to 50-50.",
        "If the match begins but is not completed, and one player advances due to the opponent's retirement, default, or disqualification, this market will resolve to the player who advances.",
        "If the match ends in a walkover (player withdraws before the start and the other advances automatically), this market will resolve to 50-50.",
        "Resolution will be based on official PDC results.",
    ]
    private static let retainedRulesHash = "75d98f8e3f011526e89e80867a9389522cce241688681e0002bbcd1725a2c2d8"

    private static let scheduledStart = 1_791_136_800
    private static let reportAt = 1_791_151_500
    /// CONSTRUCTED: the in-play instant the during page is drawn at.
    private static let constructedLiveCut = 1_791_144_600

    /// One retained exact-token trade, raw.
    private struct Trade: Equatable {
        let player: String
        let at: Int
        let probability: Double
        let size: Double
        let tx: String
    }

    private static let retainedTrades: [Trade] = [
        Trade(player: "P", at: 1_791_122_669, probability: 0.4699999944, size: 21.276596,
              tx: "0x915184c18e3590e28a730cf90c206ac34e0a23a37378087557ee3cddb824ae32"),
        Trade(player: "P", at: 1_791_126_269, probability: 0.47, size: 206.106383,
              tx: "0xf1bb9f7c0caf2a85a9adda7ebed365650f852d9318047bba895b1c193a2f59b9"),
        Trade(player: "P", at: 1_791_144_481, probability: 0.5999999976, size: 83.333332,
              tx: "0xaa0ec37ee24b516ebed95ba35566c9a12c3776044ab4f7f7667097b2e8345860"),
        Trade(player: "P", at: 1_791_145_033, probability: 0.5, size: 50,
              tx: "0x2d47b0f3dde1b953b5129453b0720b9996bc122a5f172021828bf02248548969"),
        Trade(player: "P", at: 1_791_147_763, probability: 0.01, size: 100,
              tx: "0x36c921e108e4a2e0284b9016d2ee5a78af393145f01a26d427a48d6b4d07c102"),
        Trade(player: "H", at: 1_791_150_784, probability: 0.999, size: 133.33,
              tx: "0x1b82b456783dc72ec6d73f7bb9eb014aa23d6e06c011145898875669dff916c5"),
    ]

    /// One retained set row: its winner (0 Price, 1 Humphries) and both cumulative counts after it.
    private struct SetResult {
        let number: Int
        let winner: Int
        let price: Int
        let humphries: Int
    }

    private static let retainedSets: [SetResult] = [
        SetResult(number: 1, winner: 0, price: 1, humphries: 0),
        SetResult(number: 2, winner: 0, price: 2, humphries: 0),
        SetResult(number: 3, winner: 0, price: 3, humphries: 0),
        SetResult(number: 4, winner: 1, price: 3, humphries: 1),
        SetResult(number: 5, winner: 1, price: 3, humphries: 2),
        SetResult(number: 6, winner: 1, price: 3, humphries: 3),
        SetResult(number: 7, winner: 1, price: 3, humphries: 4),
        SetResult(number: 8, winner: 0, price: 4, humphries: 4),
        SetResult(number: 9, winner: 1, price: 4, humphries: 5),
        SetResult(number: 10, winner: 1, price: 4, humphries: 6),
    ]

    // MARK: Players

    private struct Player {
        let key: String
        let name: String
        let short: String
        let keyShape: FieldHeadlineKeyShape10868
        let shape: FieldHistoryShape10868
        let tint: Color
        let token: String
        let resolvedWinner: Bool
    }

    private static let price = Player(
        key: "P", name: "Gerwyn Price", short: "Price", keyShape: .diamond, shape: .diamond,
        tint: Color(red: 0.05, green: 0.55, blue: 0.55),
        token: "77616035823760463744825756450493662050911352744116903639399747436459540222844", resolvedWinner: false)
    private static let humphries = Player(
        key: "H", name: "Luke Humphries", short: "Humphries", keyShape: .circle, shape: .circle,
        tint: Color(red: 0.0, green: 0.36, blue: 0.75),
        token: "12592960662531790896288371028211542189310855716633384850751024654749890811962", resolvedWinner: true)
    private static let players = [price, humphries]

    private static func trades(_ player: Player) -> [Trade] { retainedTrades.filter { $0.player == player.key } }

    /// The owner's pre-match election, simulated by the fixture only: the last
    /// trade strictly before the listed start. Humphries has none.
    private static func baseline(_ player: Player) -> Trade? { trades(player).filter { $0.at < scheduledStart }.last }

    private static func cutoff(_ phase: Phase) -> Int {
        switch phase {
        case .before: return scheduledStart - 1
        case .during: return constructedLiveCut
        case .final: return reportAt
        }
    }

    /// The trades each phase admits; the page never filters them.
    private static func admitted(_ player: Player, _ phase: Phase, omitting: Int? = nil) -> [Trade] {
        trades(player).filter { $0.at <= cutoff(phase) && $0.at != omitting }
    }

    private static func lastAdmitted(_ player: Player, _ phase: Phase) -> Trade? { admitted(player, phase).last }

    /// CONSTRUCTED in-play trade: the player's last trade at or after the listed start, up to the cut.
    private static func liveTrade(_ player: Player) -> Trade? {
        admitted(player, .during).filter { $0.at >= scheduledStart }.last
    }

    // MARK: Fixture words (CONSTRUCTED owner copy)

    private static func clock(_ at: Int) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "MMM d, h:mm a"
        return formatter.string(from: Date(timeIntervalSince1970: TimeInterval(at))) + " UTC"
    }

    /// The test's stand-in for the owner formatter: at most one decimal; the
    /// raw value stays the coordinate.
    private static func figure(_ probability: Double) -> String {
        let tenths = (probability * 1000).rounded() / 10
        return tenths == tenths.rounded() ? "\(Int(tenths))%" : String(format: "%.1f%%", tenths)
    }

    private static let noBaseline = "No captured pre-match trade"

    // MARK: - History

    private static func pointID(_ player: Player, _ at: Int) -> String { "\(player.key)@\(at)" }

    /// Every admitted trade time of both players, in order.
    private static func instants(_ phase: Phase, omitting: Int? = nil) -> [Int] {
        Array(Set(players.flatMap { admitted($0, phase, omitting: omitting).map(\.at) })).sorted()
    }

    private static func windowEnd(_ phase: Phase) -> Int {
        switch phase {
        case .before: return scheduledStart
        case .during: return constructedLiveCut
        case .final: return reportAt
        }
    }

    /// The owner's history for a phase: each admitted trade its own isolated
    /// mark (one run per trade, no links, no endpoint label). `inspecting` is
    /// an exact trade time the host holds; `windowOverride` is the hostile
    /// control that hands another phase's trades to this one; `omitting` drops
    /// one trade from the owner's arrival.
    private static func history(_ phase: Phase, inspecting: Int? = nil, windowOverride: Phase? = nil,
                                omitting: Int? = nil, choosing: Bool = false,
                                keyContext: FieldHistoryKeyContext10868? = nil,
                                injecting: Trade? = nil) -> FieldHistoryInput10868 {
        let window = windowOverride ?? phase
        /// The owner's trades for a player; `injecting` is the hostile control
        /// that feeds a non-trade in as if it were one.
        func traded(_ player: Player) -> [Trade] {
            (admitted(player, window, omitting: omitting) + [injecting].compactMap { $0 }.filter { $0.player == player.key })
                .sorted { $0.at < $1.at }
        }
        let shownTimes = Array(Set(players.flatMap { traded($0).map(\.at) })).sorted()
        func series(_ player: Player) -> FieldHistorySeries10868 {
            let mine = traded(player)
            let shown = inspecting.flatMap { at in mine.first { $0.at == at } } ?? mine.last
            return FieldHistorySeries10868(
                id: player.key, name: player.name, shape: player.shape, tint: player.tint,
                runs: mine.map { trade in
                    FieldHistoryRun10868(id: "\(pointID(player, trade.at))#run", points: [
                        FieldHistoryPoint10868(id: pointID(player, trade.at), x: Double(trade.at - scheduledStart),
                                               probability: trade.probability,
                                               style: trade.at < scheduledStart ? .hollow : .filled),
                    ])
                },
                links: [], labelPointID: nil,
                before: baseline(player).map {
                    FieldHistoryReading10868.observation(pointID: pointID(player, $0.at), figure: figure($0.probability),
                                                         provenance: "\(clock($0.at)) · last pre-match trade")
                } ?? FieldHistoryReading10868.absent(words: noBaseline),
                recorded: shown.map {
                    FieldHistoryReading10868.observation(pointID: pointID(player, $0.at), figure: figure($0.probability),
                                                         provenance: "\(clock($0.at)) · recorded trade")
                } ?? FieldHistoryReading10868.absent(words: "No captured trade"),
                absentWords: mine.isEmpty ? "No recorded trades in this window" : nil,
                choose: choosing && player.key == price.key
                    ? FieldHistoryAction10868(id: "history.choose.P", label: player.name, spokenLabel: nil, isAvailable: true) : nil,
                keyContext: player.key == price.key ? keyContext : nil)
        }
        let inspection = inspecting.map { at -> FieldHistoryInspection10868 in
            var selections: [String: FieldHistorySelection10868] = [:]
            for player in players {
                if let trade = traded(player).first(where: { $0.at == at }) {
                    selections[player.key] = .point(id: pointID(player, at), spoken: figure(trade.probability))
                } else {
                    selections[player.key] = .absent(words: "No trade at this instant")
                }
            }
            return FieldHistoryInspection10868(
                x: Double(at - scheduledStart), caption: "Inspecting · \(clock(at))", selections: selections,
                choices: shownTimes.map { time in
                    FieldHistoryInspectionChoice10868(id: "trade@\(time)", lines: [clock(time)],
                                                      spoken: "Recorded trade at \(clock(time))", isSelected: time == at)
                },
                choicePresentation: .buttons(groupLabel: "Inspect exact recorded trade times"),
                note: "Only a trade at this exact time is shown. The other player stays unavailable.")
        }
        let readout: FieldHistoryReadoutIntent10868
        if inspecting != nil {
            readout = .beforeAndInspected(beforeLabel: "Pre-match", inspectedLabel: "Inspected")
        } else if phase == .before {
            readout = .singleBefore(label: "Pre-match")
        } else {
            readout = .beforeAndRecorded(beforeLabel: "Pre-match", recordedLabel: "Last recorded")
        }
        // The owner's step targets: the admitted trade before and after the
        // held one, or the last and first admitted trades with nothing held.
        let held = inspecting.flatMap { shownTimes.firstIndex(of: $0) }
        let previousTarget = held.map { shownTimes.indices.contains($0 - 1) ? shownTimes[$0 - 1] : nil } ?? shownTimes.last
        let nextTarget = held.map { shownTimes.indices.contains($0 + 1) ? shownTimes[$0 + 1] : nil } ?? shownTimes.first
        let lower = Double(shownTimes.first! - scheduledStart), upper = Double(windowEnd(window) - scheduledStart)
        var xTicks = [FieldHistoryTick10868(value: lower, lines: [clock(shownTimes.first!)]),
                      FieldHistoryTick10868(value: 0, lines: [clock(scheduledStart)])]
        if window != .before {
            xTicks.append(FieldHistoryTick10868(value: upper, lines: [clock(windowEnd(window))]))
        }
        let count = players.map { traded($0).count }.reduce(0, +)
        return FieldHistoryInput10868(
            title: "Win probability",
            caption: phase == .before ? "Last captured pre-match trades" : "Historical readings · each trade has its own time",
            series: players.map(series), selection: .none,
            domain: FieldHistoryDomain10868(lower: lower, upper: upper), ceiling: 1,
            yTicks: [0, 0.5, 1].map { FieldHistoryTick10868(value: $0, lines: ["\(Int($0 * 100))%"]) },
            xTicks: xTicks,
            guides: [FieldHistoryGuide10868(id: "listed-start", x: 0, label: "Listed start")],
            breaks: [], readout: readout,
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow · before the listed start",
                                              filled: "Filled · recorded after the listed start"),
            comparisonExplanation: nil,
            notes: ["Each mark is one exact recorded trade on its own player’s outcome token. No line joins the marks, and a missing player is never filled in.",
                    "Sampled quotes without age or spread never become a chance here."],
            summary: "\(count) recorded trades on two independent outcome tokens, on a 0 to 100% scale.",
            plotHeight: 302, unboundReadingWords: "Not recorded at this trade", plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: FieldHistoryAction10868(id: "history.details", label: "History & source details", spokenLabel: nil, isAvailable: true),
            expand: FieldHistoryAction10868(id: "history.expand", label: "Full chart", spokenLabel: "Expand recorded win chances",
                                            isAvailable: true),
            inspect: inspecting == nil ? nil
                : FieldHistoryAction10868(id: "history.inspect.done", label: "Last recorded trades", spokenLabel: nil, isAvailable: true),
            previous: previousTarget.map {
                FieldHistoryAction10868(id: "history.inspect@\($0)", label: "Previous", spokenLabel: "Previous recorded trade", isAvailable: true)
            },
            next: nextTarget.map {
                FieldHistoryAction10868(id: "history.inspect@\($0)", label: "Next", spokenLabel: "Next recorded trade", isAvailable: true)
            },
            inspection: inspection,
            layout: .expanded)
    }

    // MARK: - Headline

    private static let headlineScope = "polymarket|5263083|winner"

    private static func ref(_ player: Player, scope: String = Tests.headlineScope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "polymarket", marketID: retainedMarketID, outcomeID: player.token)
    }

    private static func reading(_ label: String, _ text: String, _ detail: String) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: label, value: .recorded(text: text, detail: detail))
    }

    private static func beforeReading(_ player: Player, hasBaseline: Bool = true) -> FieldChooserReading10868 {
        guard hasBaseline, let base = baseline(player) else {
            return FieldChooserReading10868(label: "Pre-match", value: .missing(noBaseline))
        }
        return reading("Pre-match", figure(base.probability), "\(clock(base.at)) · last pre-match trade")
    }

    /// CONSTRUCTED in-play reading, or its words.
    private static func laterReading(_ player: Player) -> FieldChooserReading10868 {
        guard let trade = liveTrade(player) else {
            return FieldChooserReading10868(label: "Last recorded", value: .missing("No recorded trade"))
        }
        return reading("Last recorded", figure(trade.probability), "\(clock(trade.at)) · recorded trade")
    }

    private static func finalSets(_ player: Player) -> Int {
        player.key == price.key ? retainedSets[retainedSets.count - 1].price : retainedSets[retainedSets.count - 1].humphries
    }

    private static func state(_ phase: Phase) -> FieldHeadlineState10868 {
        switch phase {
        case .before:
            return FieldHeadlineState10868(figure: "Before match", unit: nil, caption: "Listed start", detail: clock(scheduledStart),
                                           spoken: "Before match. Listed start \(clock(scheduledStart)).", progress: nil)
        case .during:
            return FieldHeadlineState10868(figure: "In play", unit: nil, caption: "Constructed snapshot · score not captured",
                                           detail: "Trades recorded to \(clock(constructedLiveCut))",
                                           spoken: "In play. Constructed snapshot. Score not captured.", progress: nil)
        case .final:
            return FieldHeadlineState10868(figure: "Final", unit: nil, caption: "Price 4–6 Humphries in sets",
                                           detail: "Sky Sports report · \(clock(reportAt))",
                                           spoken: "Final. Price 4, Humphries 6, in sets. Sky Sports report, \(clock(reportAt)).",
                                           progress: nil)
        }
    }

    private static func headlineCopy(_ phase: Phase) -> FieldHeadlineCopy10868 {
        let eyebrow: String
        switch phase {
        case .before: eyebrow = "DARTS · WORLD GRAND PRIX · BEFORE MATCH"
        case .during: eyebrow = "DARTS · WORLD GRAND PRIX · IN PLAY"
        case .final: eyebrow = "DARTS · WORLD GRAND PRIX · FINAL"
        }
        return FieldHeadlineCopy10868(
            eyebrow: eyebrow, title: "Gerwyn Price vs Luke Humphries",
            graphicLabel: phase == .final ? "Pre-match chances and final sets" : "Players’ win chances",
            beforeLabel: "Pre-match", recordedLabel: "Last recorded", beforeUnavailable: noBaseline,
            recordedUnavailable: "No recorded trade", finishLabel: "Final sets",
            finishUnavailable: "Final sets not reported", empty: "No players in this update",
            aboutLabel: "About this match",
            aboutHint: phase == .final ? "Opens the set-by-set report, timing and sources" : "Opens timing and sources",
            openHint: "Opens this player’s recorded trades")
    }

    /// The owner's phase-admitted headline. `baseline: false` withholds both
    /// pre-match chances; `supplyingLater` is the hostile control that hands
    /// the in-play reading and the final sets to any phase.
    private static func headline(_ phase: Phase, baseline hasBaseline: Bool = true, supplyingLater: Bool = false,
                                 scope: String = Tests.headlineScope) -> FieldHeadlineInput10868 {
        let suppliesLater = supplyingLater || phase == .during
        let suppliesFinal = supplyingLater || phase == .final
        return FieldHeadlineInput10868(
            scope: scope,
            catalogue: players.map { player in
                FieldChooserOriginal10868(
                    ref: ref(player, scope: scope), name: player.short,
                    plan: phase == .during
                        ? .comparison(before: beforeReading(player, hasBaseline: hasBaseline), later: laterReading(player))
                        : .single(beforeReading(player, hasBaseline: hasBaseline)),
                    preview: FieldChooserPreview10868(history: nil, absence: "History in the chart"),
                    movement: nil, clock: nil, result: nil, browseStatus: "Polymarket outcome token", accent: player.tint)
            },
            displayed: players.map {
                FieldHeadlineSlot10868(ref: ref($0, scope: scope), name: $0.name, compactName: $0.short, keyShape: $0.keyShape)
            },
            pairs: players.map { player in
                let base = hasBaseline ? baseline(player) : nil
                let later = suppliesLater ? liveTrade(player) : nil
                return FieldMovementPair10868(
                    ref: ref(player, scope: scope),
                    before: base.map { FieldMovementObservation10868(probability: $0.probability, reading: beforeReading(player)) },
                    later: later.map { FieldMovementObservation10868(probability: $0.probability, reading: laterReading(player)) },
                    movement: nil, observation: later.map { pointID(player, $0.at) })
            },
            finishes: suppliesFinal
                ? players.map {
                    FieldFinishPlace10868(ref: ref($0, scope: scope),
                                          reading: reading("Final sets", "\(finalSets($0))", "Sky Sports report · \(clock(reportAt))"))
                }
                : [],
            state: state(phase), phase: Model.headlinePhase(phase), copy: headlineCopy(phase),
            unavailableWords: "Player unavailable in this update")
    }

    // MARK: - Actual-set story

    private static func count(_ player: Player, _ value: Int, scope: String = Tests.headlineScope) -> DartsSetCount10868 {
        DartsSetCount10868(ref: ref(player, scope: scope), value: Double(value), figure: "\(value)")
    }

    /// The owner's state words after a set, from the report: CONSTRUCTED copy.
    private static func stateWords(_ result: SetResult) -> String {
        if result.number == retainedSets.count { return "Humphries won" }
        if result.price == result.humphries { return "Level" }
        return result.price > result.humphries ? "Price leads" : "Humphries leads"
    }

    private static func setRow(_ result: SetResult) -> DartsSetRow10868 {
        let words = stateWords(result)
        let heading = result.number == retainedSets.count ? "Final" : "After set \(result.number)"
        return DartsSetRow10868(
            id: "set-\(result.number)", label: "\(result.number)", readoutLabel: heading,
            counts: [count(price, result.price), count(humphries, result.humphries)],
            winner: ref(result.winner == 0 ? price : humphries), stateWords: words,
            spoken: "\(heading): Price \(result.price), Humphries \(result.humphries) sets. \(words).")
    }

    private static func setRows(_ source: [SetResult] = Tests.retainedSets) -> [DartsSetRow10868] { source.map(setRow) }

    /// The owner's separately supplied actual origin: no sets won by either player.
    private static func origin() -> DartsSetOrigin10868 {
        DartsSetOrigin10868(id: "start", counts: [count(price, 0), count(humphries, 0)])
    }

    private static let setsCopy = DartsSetStoryCopy10868(
        eyebrow: "ACTUAL SETS WON", title: "From 0–3 to the title", unit: "Sets won",
        orderLabel: "Completed sets in order · not elapsed time",
        graphicLabel: "Cumulative actual sets won by each player after every completed set",
        note: "Each step is a completed set. Set times were not captured, so the probability cursor stays independent.",
        rowsEmpty: "No completed sets in this update", selectionPrompt: "Choose a set",
        selectionMissing: "That set is not in this update", selectHint: "Shows the cumulative score after this set",
        pickerLabel: "Inspect actual set scores", checkpointsLabel: "Turning points",
        countUnavailable: "Player unavailable in this update", reportLabel: "Match report",
        expandLabel: "Expand the set comeback", contextLabel: "Pre-match chances")

    private static let checkpointList = [
        DartsSetCheckpoint10868(id: "cp-three", setID: "set-3", label: "3–0 up", detail: "Price won the first three sets"),
        DartsSetCheckpoint10868(id: "cp-run", setID: "set-7", label: "Four in a row", detail: "Humphries won sets four to seven"),
        DartsSetCheckpoint10868(id: "cp-eighth", setID: "set-8", label: "Level 4–4", detail: "Price won the eighth"),
        DartsSetCheckpoint10868(id: "cp-last", setID: "set-10", label: "Won 6–4", detail: "Humphries won the last two"),
    ]

    private static let defaultScale = DartsSetScale10868(
        lower: 0, upper: 6, ticks: [0, 3, 6].map { DartsSetTick10868(value: Double($0), label: "\($0)") }, label: "Sets won")

    private static func sets(rows: [DartsSetRow10868]? = nil, origin hasOrigin: Bool = true, selected: String? = "set-10",
                             scale: DartsSetScale10868? = nil, players storyPlayers: [DartsSetPlayer10868]? = nil,
                             checkpoints: [DartsSetCheckpoint10868]? = nil, readerHeight: CGFloat? = 300,
                             copy: DartsSetStoryCopy10868? = nil) -> DartsSetStory10868 {
        DartsSetStory10868(
            players: storyPlayers ?? players.map { DartsSetPlayer10868(ref: ref($0), name: $0.short) },
            origin: hasOrigin ? origin() : nil, rows: rows ?? setRows(), scale: scale ?? defaultScale,
            orderTicks: [("start", "Start"), ("set-3", "Set 3"), ("set-7", "Set 7"), ("set-10", "Set 10")]
                .map { DartsSetOrderTick10868(rowID: $0.0, label: $0.1) },
            checkpoints: checkpoints ?? checkpointList, selectedSetID: selected, plotHeight: 220,
            readerPlotHeight: readerHeight, copy: copy ?? setsCopy)
    }

    // MARK: - Page

    private static let provider = DartsEventPageSource10868(id: "polymarket-market", label: "Polymarket market",
                                                            url: URL(string: retainedProviderURL)!)
    private static let report = DartsEventPageSource10868(id: "sky-sports-report", label: "Sky Sports match report",
                                                          url: URL(string: retainedResultSource)!)

    private static func readerHeader(_ phase: Phase) -> DartsEventPageReaderHeader10868 {
        switch phase {
        case .before: return DartsEventPageReaderHeader10868(title: "Price vs Humphries", state: "Before match · listed start \(clock(scheduledStart))")
        case .during: return DartsEventPageReaderHeader10868(title: "Price vs Humphries", state: "Constructed in-play snapshot · score not captured")
        case .final: return DartsEventPageReaderHeader10868(title: "Price vs Humphries", state: "Price 4–6 Humphries · Final sets")
        }
    }

    private static func notice(_ phase: Phase) -> String? {
        switch phase {
        case .before: return "No projected score is captured."
        case .during: return "Constructed in-play snapshot for review · no live evidence · score not captured"
        case .final: return nil
        }
    }

    private static var preMatchParagraph: String {
        "The last Gerwyn Price trade before the listed \(clock(scheduledStart)) start was at \(clock(baseline(price)!.at)), nearly three hours earlier. It is historical context, not a current quote. Luke Humphries has no captured pre-match trade, so his chance stays unavailable: it is never the complement of Price’s."
    }

    private static let quoteParagraph = "Sampled quote history is retained in source evidence only. Its spread and quote age were not captured, so it never becomes a chance here."

    /// The owner's About for the phase: only the facts admitted by then.
    private static func about(_ phase: Phase) -> DartsEventPageAbout10868 {
        let chances = DartsEventPageAboutSection10868(title: "Pre-match chances", paragraphs: [preMatchParagraph])
        let history = DartsEventPageAboutSection10868(
            title: "Market history", paragraphs: [quoteParagraph, "Each mark is one exact recorded trade. No line joins them."],
            source: provider)
        switch phase {
        case .before:
            return DartsEventPageAbout10868(title: "About this match", sections: [
                DartsEventPageAboutSection10868(title: "Before the match", paragraphs: [
                    "Recorded trades before the listed start only. Each player’s outcome token trades on its own; a missing chance stays unavailable.",
                ]),
                chances, history,
            ])
        case .during:
            return DartsEventPageAbout10868(title: "About this match", sections: [
                DartsEventPageAboutSection10868(title: "In-play snapshot (constructed)", paragraphs: [
                    "This in-play view is a constructed review snapshot: no live evidence was captured. Recorded trades run to \(clock(constructedLiveCut)). The score is not captured in this update.",
                ]),
                chances, history,
            ])
        case .final:
            return DartsEventPageAbout10868(title: "About this match", sections: [
                DartsEventPageAboutSection10868(title: "The comeback", paragraphs: [
                    "Sky Sports reports Price won sets 1–3, Humphries 4–7, Price 8 and Humphries 9–10, for a 4–6 final. Set scores count sets won, not individual legs or checkout points.",
                ], source: report),
                DartsEventPageAboutSection10868(title: "Timing", paragraphs: [
                    "The report was published \(clock(reportAt)). This is not the exact match finish. Actual start and end, set and leg wall clocks and a projected final remain unverified. No set is aligned to a market timestamp.",
                ]),
                DartsEventPageAboutSection10868(title: "Recorded trades", paragraphs: [
                    "Only six positive-size original-token trades are admitted through the report cutoff; all \(retainedQuoteSamples) sampled quote observations remain unqualified. No opposite-player complement or line through sparse trades is invented.",
                ]),
                chances, history,
            ])
        }
    }

    private static func pageCopy(_ phase: Phase) -> DartsSetEventPageCopy10868 {
        DartsSetEventPageCopy10868(
            storiesLabel: "Match stories", storyUnavailable: "This story is not available in this update.",
            headlineUnavailable: "Player chances unavailable for this update",
            comparisonLabel: "Pre-match and recorded chance comparison",
            heldOriginalUnavailable: "Your selected outcome is not in this update", backLabel: "Back to match",
            doneLabel: "Done", previousLabel: "Previous card", nextLabel: "Next card",
            historyName: "Recorded win chances", setsName: phase == .final ? "The set comeback" : "Actual score")
    }

    private static func stream() -> StoryStreamPresentation10868 {
        let scope = "darts-sets:final:stories"
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: nil, heading: "Match stories",
            cards: [StoryStreamPresentation10868.Card(id: "sets", name: "The set comeback")],
            primary: StoryStreamPresentation10868.CardRef(scope: scope, id: "sets"), companion: nil,
            companionLabel: nil, wide: false, position: "1 of 1", status: nil,
            dwellFraction: nil, playback: nil, previous: nil, next: nil, readerOpen: false)
    }

    private static let storyLinks = [
        DartsSetEventPageStory10868(cardID: "sets", card: .sets, reason: "Price led 3–0; Humphries won six of the last seven sets"),
    ]

    /// The owner's phase-admitted page input. `withSets: true` is the hostile
    /// control that hands the set story to any phase (or, during play, the
    /// CONSTRUCTED owner-supplied in-play set state).
    private static func input(_ phase: Phase, headline: FieldHeadlineInput10868? = nil, history: FieldHistoryInput10868? = nil,
                              sets: DartsSetStory10868? = nil, withSets: Bool? = nil,
                              stream: StoryStreamPresentation10868? = nil,
                              about: DartsEventPageAbout10868? = nil,
                              readerHeight: CGFloat? = 370) -> DartsSetEventPageInput10868 {
        let admitsSets = withSets ?? (phase == .final)
        return DartsSetEventPageInput10868(
            phase: phase, reader: readerHeader(phase), headline: headline ?? Tests.headline(phase), notice: notice(phase),
            history: history ?? Tests.history(phase), readerPlotHeight: readerHeight,
            sets: admitsSets ? (sets ?? Tests.sets()) : nil,
            stream: stream, stories: phase == .final ? storyLinks : [], about: about ?? Tests.about(phase),
            copy: pageCopy(phase))
    }

    // MARK: Originals

    private static let originalsScope = "polymarket|5263083|originals"

    private static func identity(_ player: Player) -> Details.Identity {
        Details.Identity(source: "polymarket", market: retainedMarketID, side: player.token)
    }

    private static func selection(_ player: Player, scope: String = Tests.originalsScope) -> Details.Selection {
        Details.Selection(scope: scope, identity: identity(player))
    }

    /// Each outcome at its phase: the pre-match reading or its absence; during
    /// play the CONSTRUCTED cut's recorded reading; at the final the contract's
    /// own grade, which is not the reported set score, and the last retained
    /// trade as a dated historical quote. Rules verbatim.
    private static func original(_ player: Player, _ phase: Phase) -> Details.Original {
        let pregame: Details.Reading = baseline(player).map {
            Details.Reading.value(figure($0.probability), placement: $0.probability, provenance: "\(clock($0.at)) · last pre-match trade")
        } ?? Details.Reading.missing(noBaseline)
        let mode: Details.Mode
        var later: Details.Reading?
        var grade: Details.Grade?
        var quote: Details.HistoricalQuote?
        switch phase {
        case .before:
            mode = .pregame
        case .during:
            mode = .comparison(.recorded)
            later = liveTrade(player).map {
                Details.Reading.value(figure($0.probability), placement: $0.probability, provenance: "\(clock($0.at)) · recorded trade")
            } ?? Details.Reading.missing("No recorded trade")
        case .final:
            mode = .result
            grade = Details.Grade(words: player.resolvedWinner ? "Resolved Yes" : "Resolved No",
                                  provenance: "Polymarket resolution · time not captured")
            quote = lastAdmitted(player, .final).map { Details.HistoricalQuote(text: figure($0.probability), recorded: clock($0.at)) }
        }
        return Details.Original(
            identity: identity(player), title: retainedTitle, outcome: player.name, mode: mode, pregame: pregame, later: later,
            grade: grade,
            about: Details.About(source: "Polymarket", rules: .verified(retainedRulesParagraphs),
                                 provenance: [Details.Row(label: "Polymarket market", value: retainedMarketID),
                                              Details.Row(label: "Condition", value: retainedCondition),
                                              Details.Row(label: "Outcome token", value: player.token)],
                                 historicalQuote: quote))
    }

    private static let labels: [Details.Identity: String] = [
        Tests.identity(Tests.price): "Gerwyn Price to win",
        Tests.identity(Tests.humphries): "Luke Humphries to win",
    ]

    private static func originals(_ phase: Phase, list: [Details.Original]? = nil,
                                  selection held: Details.Selection? = Tests.selection(Tests.price)) -> DartsEventPageOriginals10868 {
        DartsEventPageOriginals10868(
            catalogue: Details.Catalogue(scope: originalsScope, originals: list ?? players.map { original($0, phase) }),
            selection: held, labels: labels, heading: "Match winner · 2 players",
            context: "Polymarket · two original outcome tokens",
            emptyWords: "No outcomes supplied in this update", unavailableChoice: "Outcome unavailable", tint: price.tint)
    }

    // MARK: - Reachable text

    /// Every string a reader can reach from one input through the models the
    /// views draw from: the reader heading, notice and controls; the headline
    /// as drawn and spoken; the page and full-size history with the paired
    /// comparison over each; every set row (each is reachable by selection),
    /// tick, checkpoint and the report entry; the stream; the About and its
    /// sources (with the URL a source hands back); and, with `originals`,
    /// every catalogue card, each original's Details and spoken Details.
    private static func reachableText(_ input: DartsSetEventPageInput10868,
                                      originals: DartsEventPageOriginals10868?) -> [String] {
        let model = Model(input)
        var texts = [input.reader.title, input.copy.storiesLabel, input.copy.backLabel, input.copy.doneLabel,
                     input.copy.comparisonLabel]
        texts += [input.reader.state, input.notice].compactMap { $0 }
        for card in model.mountedCards {
            for offset in [-1, 1] {
                if let neighbour = model.neighbour(of: card, offset: offset) {
                    texts += [offset < 0 ? input.copy.previousLabel : input.copy.nextLabel, model.cardName(neighbour)]
                }
            }
        }
        if let headline = model.headline {
            let leaf = FieldHeadlineModel10868(headline)
            texts += [leaf.eyebrow, leaf.title, leaf.stateSummary, leaf.aboutLabel(canAbout: true), headline.copy.openHint]
                .compactMap { $0 }
            texts += [leaf.aboutHint(canAbout: true), headline.copy.graphicLabel]
            if let state = leaf.state {
                texts += [state.figure, state.unit, state.caption, state.detail, state.spoken].compactMap { $0 }
            }
            for competitor in leaf.competitors {
                texts += [competitor.slot.name, leaf.competitorSummary(competitor)] + [competitor.slot.compactName].compactMap { $0 }
                for endpoint in competitor.metrics {
                    texts.append(FieldChaseModel10868.label(endpoint))
                    texts += [FieldChaseModel10868.figure(endpoint), FieldChaseModel10868.words(endpoint),
                              FieldChaseModel10868.detail(endpoint)].compactMap { $0 }
                }
            }
            for original in headline.catalogue {
                texts += [original.name, original.browseStatus, original.preview.absence]
            }
        } else {
            texts.append(input.copy.headlineUnavailable)
        }
        for reader in [false, true] {
            let page = Page(input: input, mode: reader ? .reader(.history) : .page)
            texts += historyText(page.historyContent(reader: reader).input)
            texts += comparisonText(page.comparisonContent(reader: reader))
        }
        for story in [model.setsModel, model.readerSetsModel].compactMap({ $0 }) {
            texts += setsText(story)
        }
        if let stream = input.stream {
            texts.append(stream.heading)
            texts += [stream.eyebrow, stream.companionLabel, stream.position, stream.status, stream.pending,
                      stream.nextHint, stream.basis].compactMap { $0 }
            for card in stream.cards {
                texts.append(card.name)
                if let link = model.storyLink(card.id) {
                    texts += [link.reason].compactMap { $0 }
                } else {
                    texts.append(input.copy.storyUnavailable)
                }
            }
        }
        if let about = model.about {
            texts.append(about.title)
            for section in about.sections {
                texts += [section.title] + section.paragraphs
                if let source = section.source {
                    texts += [source.id, source.label, source.url.absoluteString]
                }
            }
        }
        if let originals {
            texts += originalsText(originals)
            if Model.heldOriginalIsUnavailable(originals) {
                texts.append(input.copy.heldOriginalUnavailable)
            }
        }
        return texts
    }

    private static func historyText(_ history: FieldHistoryInput10868) -> [String] {
        typealias Readout = FieldHistoryGeometry10868
        var texts = [history.title, history.summary, history.unboundReadingWords] + history.notes
        texts += [history.caption, history.markKey.hollow, history.markKey.filled, history.comparisonExplanation,
                  history.plotUnavailableWords, history.windows?.groupLabel, Readout.probabilityRangeExplanation(history),
                  Readout.selectionWords(history), history.plotAbsence?.title, history.plotAbsence?.words].compactMap { $0 }
        texts += (history.yTicks + history.xTicks).flatMap(\.lines)
        texts += history.guides.map(\.label) + history.breaks.map(\.mark)
        texts += Readout.actions(history).flatMap { [$0.label, $0.spokenLabel].compactMap { $0 } }
        for series in history.series {
            texts.append(series.name)
            texts += [series.absentWords].compactMap { $0 }
            for slot in Readout.readoutSlots(series, in: history) + Readout.selectedSlots(series, in: history) {
                texts += [slot.label, Readout.spokenSlot(slot)]
                switch slot.display {
                case .figure(let figure, let provenance): texts += [figure, provenance]
                case .words(let words): texts.append(words)
                }
            }
        }
        if let inspection = history.inspection {
            texts += [inspection.caption] + [inspection.note].compactMap { $0 }
            for choice in inspection.choices {
                texts += choice.lines + [choice.spoken]
            }
            for selection in inspection.selections.values {
                switch selection {
                case .point(_, let spoken): texts.append(spoken)
                case .absent(let words): texts.append(words)
                }
            }
        }
        texts.append(Readout.spokenValue(history))
        return texts
    }

    /// Every string the accepted comparison View draws or speaks.
    private static func comparisonText(_ comparison: RugbyMatchEventPageComparisonPresentation10868) -> [String] {
        var texts = [comparison.label]
        for entry in comparison.entries {
            texts += [entry.series.name, RugbyMatchEventPageComparisonPresentation10868.spoken(entry)] + [entry.note].compactMap { $0 }
            for slot in entry.slots {
                texts.append(slot.label)
                switch slot.display {
                case .figure(let figure, let provenance): texts += [figure, provenance]
                case .words(let words): texts.append(words)
                }
            }
        }
        return texts
    }

    private static func setsText(_ model: SetModel) -> [String] {
        let copy = model.copy
        var texts = [copy.title, copy.unit, copy.orderLabel, copy.graphicLabel, copy.rowsEmpty, copy.selectionMissing,
                     copy.pickerLabel, copy.checkpointsLabel, copy.countUnavailable, copy.expandLabel]
        texts += [copy.eyebrow, copy.note, copy.selectionPrompt, copy.selectHint, copy.reportLabel, model.story.scale.label]
            .compactMap { $0 }
        texts += model.scaleTicks.map(\.label) + model.orderTicks.map(\.label)
        texts += model.story.players.map(\.name)
        for row in model.story.rows {
            texts += [row.label, row.readoutLabel, row.stateWords, row.spoken]
            let shown = model.shownCounts(row)
            texts += shown.compactMap(\.figure)
            // The drawn score line: each player's count with the dash between.
            texts.append(shown.map { $0.figure ?? copy.countUnavailable }.joined(separator: "–"))
        }
        for placed in model.checkpoints {
            texts += [placed.checkpoint.label] + [placed.checkpoint.detail].compactMap { $0 }
        }
        if let shown = model.shownContext {
            texts += comparisonText(RugbyMatchEventPageComparisonPresentation10868(history: shown.history, label: shown.label))
        }
        return texts
    }

    private static func originalsText(_ originals: DartsEventPageOriginals10868) -> [String] {
        var texts = [originals.heading, originals.emptyWords, originals.unavailableChoice] + [originals.context].compactMap { $0 }
        let cards = OriginalMarketCatalogue9483.cards(catalogue: originals.catalogue, selection: originals.selection,
                                                      labels: originals.labels, unavailableChoice: originals.unavailableChoice)
        for card in cards {
            texts += [card.choice.label, OriginalMarketCatalogue9483.spoken(card)] + [card.choice.status].compactMap { $0 }
        }
        var contents = cards.compactMap(\.content)
        let held = Details.content(catalogue: originals.catalogue, selection: originals.selection)
        contents += [held].compactMap { $0 }
        texts.append(Details.spoken(held))
        for original in originals.catalogue?.originals ?? [] {
            let own = Details.content(catalogue: originals.catalogue,
                                      selection: Details.Selection(scope: originals.catalogue?.scope ?? "", identity: original.identity))
            texts.append(Details.spoken(own))
            contents += [own].compactMap { $0 }
        }
        for content in contents {
            texts += [content.title, content.outcome]
            for reading in content.readings {
                texts += [reading.label, reading.text] + [reading.provenance].compactMap { $0 }
            }
            if let result = content.result {
                texts += [result.words] + [result.provenance].compactMap { $0 }
            }
            texts += content.about.flatMap { [$0.label, $0.value] }
            switch content.rules {
            case .verified(let paragraphs): texts += paragraphs
            case .unavailable(let words): texts.append(words)
            case .omitted: break
            }
        }
        return texts
    }

    /// Everything a phase reaches: its own input, the same input inspecting
    /// each of its admitted trade times (each trade is reachable by
    /// selection), and at the final the stream presentation too.
    private static func phaseTexts(_ phase: Phase) -> [String] {
        var texts = reachableText(input(phase), originals: originals(phase))
        for at in instants(phase) {
            texts += reachableText(input(phase, history: history(phase, inspecting: at)), originals: originals(phase))
        }
        if phase == .final {
            texts += reachableText(input(.final, stream: stream()), originals: originals(.final))
        }
        return texts
    }

    // MARK: Phase-text patterns

    /// Every set-score pair the final shows as a pair: each cumulative row,
    /// the deficit the title names and the winner's own order.
    private static var scorePairs: [String] {
        retainedSets.map { "\($0.price)–\($0.humphries)" } + ["0–3", "6–4"]
    }

    /// A score pair as a whole token: never inside a longer number, a clock, a
    /// date or a percentage.
    private static func pairPattern(_ pair: String) -> String {
        let sides = pair.split(separator: "–")
        return "(^|[^0-9.:])\(sides[0])\\s*[–-]\\s*\(sides[1])([^0-9%:]|$)"
    }

    /// Final facts by meaning, all reachable at the final (the positive
    /// control). A bare count or set number is a whole string, never a digit
    /// inside a chance, a clock, a date or an id.
    private static var finalFacts: [String] {
        scorePairs.map(pairPattern) + [
            "^\\s*(10|[0-9])\\s*$",
            "\\bsets?\\b", "\\bfinal\\b", "\\bwon\\b", "\\bresolved\\b", "\\bSky Sports\\b", "\\breport",
            "\\bcomeback\\b", "\\bleads\\b", "\\blegs?\\b", "\\bcheckout\\b", "\\bsix\\b",
            "(^|[^0-9.:])252([^0-9%:]|$)", "(^|[^0-9.])1%", "(^|[^0-9.])99\\.9%",
            NSRegularExpression.escapedPattern(for: clock(reportAt)),
        ]
    }

    /// Clock words of every retained trade strictly after `instant`.
    private static func clocksAfter(_ instant: Int) -> [String] {
        Array(Set(retainedTrades.filter { $0.at > instant }.map { NSRegularExpression.escapedPattern(for: clock($0.at)) })).sorted()
    }

    /// What a before page must not reach: every final fact, every trade at or
    /// after the listed start (the 50% trade by its clock: "50%" is also the
    /// owner's axis tick), the in-play figure and the constructed cut.
    private static var beforeForbidden: [String] {
        finalFacts + clocksAfter(cutoff(.before)) + [
            "(^|[^0-9.])60%", "\\bin[ -]play\\b", "\\bconstructed\\b",
            NSRegularExpression.escapedPattern(for: clock(constructedLiveCut)),
        ]
    }

    /// What a during page must not reach: every final fact and every clock after the CONSTRUCTED cut.
    private static var duringForbidden: [String] { finalFacts + clocksAfter(constructedLiveCut) }

    private static func leaks(_ texts: [String], _ patterns: [String]) -> [String] {
        patterns.flatMap { pattern in
            texts.filter { $0.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil }
                .map { "\(pattern) ⟵ \($0)" }
        }
    }

    private static func reaches(_ texts: [String], _ pattern: String) -> Bool {
        texts.contains { $0.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil }
    }

    // MARK: - Action payloads

    /// Every payload an action reachable from this input hands its owner,
    /// through the page's own wrappers: headline opens, history actions and
    /// inspection choices (page and full size), original selections, the set
    /// story's set, checkpoint and expand actions (page and full size).
    private static func payloads(_ input: DartsSetEventPageInput10868,
                                 originals: DartsEventPageOriginals10868?) -> [String] {
        var log: [String] = []
        func page(_ mode: DartsSetEventPageMode10868) -> Page {
            Page(input: input, mode: mode, originals: originals,
                 onSource: { log.append("source:\($0.id)") },
                 onOriginalSelect: { log.append("original:\($0.scope)|\($0.identity.market)|\($0.identity.side)") },
                 onHeadlineOpen: { log.append("headline:\($0.ref.outcomeID)@\($0.observation ?? "none")") },
                 onHistoryAction: { log.append("history.action:\($0)") },
                 onHistoryInspectionChoice: { log.append("history.choice:\($0)") },
                 onCardOpen: { log.append("card:\($0.rawValue)") },
                 onSetSelect: { log.append("set:\($0)") })
        }
        let main = page(.page)
        if let headline = main.headlineContent() {
            let leaf = FieldHeadlineModel10868(headline.input)
            for competitor in leaf.competitors {
                if let opening = leaf.openAction(competitor, canOpen: true) { headline.onOpen?(opening) }
            }
        }
        for history in [main.historyContent(reader: false), page(.reader(.history)).historyContent(reader: true)] {
            for action in FieldHistoryGeometry10868.actions(history.input) where action.isAvailable {
                history.onAction?(action.id)
            }
            for choice in history.input.inspection?.choices ?? [] {
                history.onInspectionChoice?(choice.id)
            }
        }
        if let originals, let catalogue = main.catalogueContent() {
            for card in OriginalMarketCatalogue9483.cards(catalogue: originals.catalogue, selection: originals.selection,
                                                          labels: originals.labels, unavailableChoice: originals.unavailableChoice) {
                OriginalMarketCatalogue9483.action(card, onSelect: catalogue.onSelect)?()
            }
        }
        for card in [main.pageSetsContent(), page(.reader(.sets)).readerSetsContent()].compactMap({ $0 }) {
            for position in card.model.positions {
                SetModel.selectAction(position, onSelect: card.onSelect)?()
            }
            for placed in card.model.checkpoints {
                if let id = placed.setID { card.onSelect?(id) }
            }
            card.onExpand?()
        }
        return log
    }

    /// Every epoch a payload carries.
    private static func epochs(_ payload: String) -> [Int] {
        guard let regex = try? NSRegularExpression(pattern: "@([0-9]{10})") else { return [] }
        let range = NSRange(payload.startIndex..., in: payload)
        return regex.matches(in: payload, range: range).compactMap { match in
            Range(match.range(at: 1), in: payload).flatMap { Int(payload[$0]) }
        }
    }

    /// Payloads carrying a key or time later than the phase admits.
    private static func payloadLeaks(_ payloads: [String], admittedThrough bound: Int) -> [String] {
        payloads.filter { epochs($0).contains { $0 > bound } }
    }

    // MARK: - Qualified-quote guard

    /// HOSTILE CONTROL: a CONSTRUCTED unqualified sampled quote (no size, no
    /// transaction, no quote age or spread) handed in as if it were a trade.
    private static let sampledQuoteAsTrade = Trade(player: "P", at: 1_791_140_400, probability: 0.55, size: 0, tx: "sampled-quote")

    /// The retained trade a mark names: same player, exact point id, raw
    /// probability and position. Nil for anything else.
    private static func retainedTrade(_ seriesID: String, _ point: FieldHistoryPoint10868) -> Trade? {
        retainedTrades.first {
            $0.player == seriesID && "\($0.player)@\($0.at)" == point.id && $0.probability == point.probability
                && Double($0.at - scheduledStart) == point.x && $0.size > 0
        }
    }

    /// Whether a shown figure and its date are one retained trade of that player.
    private static func isRetainedReading(_ seriesID: String, _ display: FieldHistoryReadingDisplay10868) -> Bool {
        guard case .figure(let shown, let provenance) = display else { return true }
        return retainedTrades.contains { $0.player == seriesID && figure($0.probability) == shown && provenance.contains(clock($0.at)) }
    }

    /// Marks and figures in a composed history that are not one of the six
    /// retained trades: mark ids, then "series:figure".
    private static func unqualified(_ history: FieldHistoryInput10868) -> [String] {
        var found: [String] = []
        for series in history.series {
            found += series.runs.flatMap(\.points).filter { retainedTrade(series.id, $0) == nil }.map(\.id)
            for slot in FieldHistoryGeometry10868.readoutSlots(series, in: history) where !isRetainedReading(series.id, slot.display) {
                if case .figure(let shown, _) = slot.display { found.append("\(series.id):\(shown)") }
            }
        }
        return found
    }

    /// Figures in the composed comparison that are not one of the six retained trades.
    private static func unqualified(_ entries: [RugbyMatchEventPageComparisonEntry10868]) -> [String] {
        entries.flatMap { entry in
            entry.slots.filter { !isRetainedReading(entry.series.id, $0.display) }.compactMap { slot -> String? in
                guard case .figure(let shown, _) = slot.display else { return nil }
                return "\(entry.series.id):\(shown)"
            }
        }
    }

    // MARK: - Shown words helpers

    private static func shown(_ endpoint: FieldMovementEndpoint10868) -> String {
        let label = FieldChaseModel10868.label(endpoint)
        if let figure = FieldChaseModel10868.figure(endpoint) { return "\(label)=\(figure)" }
        return "\(label): \(FieldChaseModel10868.words(endpoint) ?? "")"
    }

    private static func metrics(_ headline: FieldHeadlineInput10868?) -> [[String]] {
        guard let headline else { return [] }
        return FieldHeadlineModel10868(headline).competitors.map { $0.metrics.map { Tests.shown($0) } }
    }

    private static func slots(_ history: FieldHistoryInput10868) -> [[FieldHistoryReadingDisplay10868]] {
        history.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: history).map(\.display) }
    }

    private static func words(_ intent: DartsSetReaderIntent10868) -> String {
        switch intent {
        case .previous(let card): return "previous:\(card.rawValue)"
        case .next(let card): return "next:\(card.rawValue)"
        case .back: return "back"
        case .done: return "done"
        }
    }

    private static func sha256(_ text: String) -> String {
        SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    // MARK: - Retained receipt

    func testTheRetainedReceiptMatchesTheCapture() {
        XCTAssertEqual([Self.retainedEventID, Self.retainedMarketID], ["1128105", "5263083"])
        XCTAssertEqual(Self.retainedCondition.count, 66)
        XCTAssertEqual(Self.sha256(Self.retainedTitle), Self.retainedTitleHash)
        XCTAssertEqual([Self.price.token.count, Self.humphries.token.count], [77, 77])
        XCTAssertEqual([Self.price.resolvedWinner, Self.humphries.resolvedWinner], [false, true])
        XCTAssertEqual(Self.retainedActualUnit, "sets")
        XCTAssertEqual(Self.retainedNullFields, ["actualStart", "actualEnd", "setWallClocks", "projection"])
        XCTAssertEqual([Self.clock(Self.scheduledStart), Self.clock(Self.reportAt)], ["Oct 4, 6:00 PM UTC", "Oct 4, 10:05 PM UTC"])
        XCTAssertEqual(Self.retainedQuoteSamples, 252)
        XCTAssertTrue(Self.retainedQuoteAdmission.hasPrefix("252 CLOB price samples"))
        XCTAssertEqual(Self.retainedSourceText.count, 4)
        // Six exact-token positive-size trades, raw.
        XCTAssertEqual(Self.retainedTrades.count, 6)
        XCTAssertEqual([Self.trades(Self.price).count, Self.trades(Self.humphries).count], [5, 1])
        XCTAssertTrue(Self.retainedTrades.allSatisfy { $0.size > 0 })
        XCTAssertEqual(Set(Self.retainedTrades.map(\.tx)).count, 6)
        XCTAssertEqual(Self.retainedTrades.map(\.at), [1_791_122_669, 1_791_126_269, 1_791_144_481, 1_791_145_033, 1_791_147_763, 1_791_150_784])
        XCTAssertEqual(Self.retainedTrades.map(\.probability), [0.4699999944, 0.47, 0.5999999976, 0.5, 0.01, 0.999])
        XCTAssertEqual(Self.retainedTrades.map(\.size), [21.276596, 206.106383, 83.333332, 50, 100, 133.33])
        // Ten sets, a cumulative path and the final.
        XCTAssertEqual(Self.retainedSets.map { [$0.price, $0.humphries] },
                       [[1, 0], [2, 0], [3, 0], [3, 1], [3, 2], [3, 3], [3, 4], [4, 4], [4, 5], [4, 6]])
        XCTAssertEqual(Self.retainedSets.map(\.winner), [0, 0, 0, 1, 1, 1, 1, 0, 1, 1])
        XCTAssertEqual([Self.finalSets(Self.price), Self.finalSets(Self.humphries)], [4, 6])
    }

    // MARK: - Phases

    func testEachPhaseMountsOnlyItsOwnLeavesAndNeverShowsSetsBeforePlay() throws {
        let before = Model(Self.input(.before))
        XCTAssertEqual(Self.metrics(before.headline), [["Pre-match=47%"], ["Pre-match: \(Self.noBaseline)"]])
        XCTAssertNil(before.sets)
        XCTAssertNil(before.setsModel)
        XCTAssertNil(before.readerSetsModel)
        XCTAssertEqual(before.mountedCards, [.history])
        XCTAssertTrue(Self.input(.before).history.series.allSatisfy { series in
            series.runs.flatMap(\.points).allSatisfy { $0.x < 0 && $0.style == .hollow }
        }, "the before history holds only trades strictly before the listed start")

        let during = Model(Self.input(.during))
        XCTAssertEqual(Self.metrics(during.headline), [
            ["Pre-match=47%", "Last recorded=60%"],
            ["Pre-match: \(Self.noBaseline)", "Last recorded: No recorded trade"],
        ], "CONSTRUCTED in-play readings, each with its own clock or its words")
        XCTAssertNil(during.sets, "the constructed in-play owner supplies no set state")
        XCTAssertEqual(during.mountedCards, [.history])

        let finished = Model(Self.input(.final))
        XCTAssertEqual(Self.metrics(finished.headline), [
            ["Pre-match=47%", "Final sets=4"], ["Pre-match: \(Self.noBaseline)", "Final sets=6"],
        ])
        XCTAssertNotNil(finished.setsModel)
        XCTAssertEqual(finished.mountedCards, [.history, .sets])

        // Hostile control: the final set story and later headline readings
        // handed to the before page are never mounted or shown.
        let hostile = Model(Self.input(.before, headline: Self.headline(.before, supplyingLater: true), withSets: true))
        XCTAssertNotNil(hostile.input.sets)
        XCTAssertNil(hostile.sets)
        XCTAssertNil(hostile.setsModel)
        XCTAssertNil(hostile.readerSetsModel)
        XCTAssertEqual(hostile.mountedCards, [.history])
        XCTAssertEqual(Self.metrics(hostile.headline), [["Pre-match=47%"], ["Pre-match: \(Self.noBaseline)"]])
        XCTAssertNil(Page(input: hostile.input, mode: .reader(.sets)).readerSetsContent())
        XCTAssertNil(Page(input: hostile.input).pageSetsContent())
        // A headline from another phase is not coerced.
        XCTAssertNil(Model(Self.input(.final, headline: Self.headline(.before))).headline)
    }

    func testBothNamedPreMatchChancesOrTheirExplicitAbsenceLead() throws {
        let base = try XCTUnwrap(Self.baseline(Self.price))
        XCTAssertEqual([Double(base.at), base.probability], [1_791_126_269, 0.47])
        XCTAssertNil(Self.baseline(Self.humphries), "Humphries has no captured pre-match trade")
        let headline = try XCTUnwrap(Model(Self.input(.before)).headline)
        let leaf = FieldHeadlineModel10868(headline)
        XCTAssertEqual(leaf.competitors.map { leaf.competitorSummary($0) }, [
            "Pre-match: 47%, Oct 4, 3:04 PM UTC · last pre-match trade",
            "Pre-match: \(Self.noBaseline)",
        ])
        XCTAssertEqual(leaf.competitors.map(\.slot.name), ["Gerwyn Price", "Luke Humphries"])
        XCTAssertNil(headline.pairs[1].before, "never a complement")
        // The absence stays words in every phase, whatever Humphries traded later.
        for phase in Phase.allCases {
            for held in [nil] + Self.instants(phase).map({ Optional($0) }) {
                let history = Self.history(phase, inspecting: held)
                XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(history.series[1], in: history).first?.display,
                               .words(Self.noBaseline), "never his later trade (\(phase), \(String(describing: held)))")
            }
            XCTAssertFalse(Self.reaches(Self.phaseTexts(phase), "(^|[^0-9.])53%"), "never complemented to 53% (\(phase))")
        }
        // The last pre-match Price trade is nearly three hours before the listed start.
        XCTAssertEqual(Self.scheduledStart - base.at, 10_531)
    }

    // MARK: - Retained trades

    func testTheSixRetainedTradesKeepRawPrecisionAsIsolatedMarksWithNoEndpoint() {
        let history = Self.history(.final)
        let points = history.series.map { $0.runs.flatMap(\.points) }
        XCTAssertEqual(points.map(\.count), [5, 1])
        XCTAssertEqual(points.flatMap { $0 }.map(\.probability), Self.retainedTrades.map(\.probability), "raw values stay coordinates")
        XCTAssertEqual(points.flatMap { $0 }.map(\.x), Self.retainedTrades.map { Double($0.at - Self.scheduledStart) })
        XCTAssertEqual(points.flatMap { $0 }.map(\.style), [.hollow, .hollow, .filled, .filled, .filled, .filled])
        // Isolated dots only: one point per run, no links, nothing joined.
        XCTAssertTrue(history.series.allSatisfy { $0.links.isEmpty && $0.runs.allSatisfy { $0.points.count == 1 } })
        XCTAssertTrue(history.series.flatMap { series in
            series.runs.flatMap { FieldHistoryGeometry10868.drawnRuns($0, in: history) }
        }.allSatisfy { $0.count == 1 })
        // No synthetic settled 0/100 endpoint and no endpoint label.
        XCTAssertFalse(points.flatMap { $0 }.contains { $0.probability == 0 || $0.probability == 1 })
        XCTAssertTrue(history.series.allSatisfy { $0.labelPointID == nil })
        XCTAssertEqual(history.domain.upper, Double(Self.reportAt - Self.scheduledStart))
        // Owner figures, at most one decimal.
        XCTAssertEqual(Self.retainedTrades.map { Self.figure($0.probability) }, ["47%", "47%", "60%", "50%", "1%", "99.9%"])
        XCTAssertEqual(Self.slots(history), [
            [.figure("47%", provenance: "Oct 4, 3:04 PM UTC · last pre-match trade"), .figure("1%", provenance: "Oct 4, 9:02 PM UTC · recorded trade")],
            [.words(Self.noBaseline), .figure("99.9%", provenance: "Oct 4, 9:53 PM UTC · recorded trade")],
        ])
        // No sampled quote is substituted anywhere a reader can reach: every
        // mark and every figure in the ACTUAL composed histories (page and full
        // size, each inspected trade) and comparisons is one of the six trades.
        let texts = Self.phaseTexts(.final)
        XCTAssertFalse(Self.reaches(texts, "\\bCLOB\\b"))
        for held in [nil] + Self.instants(.final).map({ Optional($0) }) {
            let input = Self.input(.final, history: Self.history(.final, inspecting: held))
            for reader in [false, true] {
                let page = Page(input: input, mode: reader ? .reader(.history) : .page)
                XCTAssertEqual(Self.unqualified(page.historyContent(reader: reader).input), [], "\(String(describing: held))")
                XCTAssertEqual(Self.unqualified(page.comparisonContent(reader: reader).entries), [], "\(String(describing: held))")
            }
        }
        // Positive bad control: a hostile owner feeds a sampled quote in as a trade.
        let hostileInput = Self.input(.final, history: Self.history(.final, inspecting: Self.sampledQuoteAsTrade.at,
                                                                    injecting: Self.sampledQuoteAsTrade))
        let hostile = Page(input: hostileInput)
        XCTAssertEqual(Self.unqualified(hostile.historyContent(reader: false).input), ["P@1791140400", "P:55%"])
        XCTAssertEqual(Self.unqualified(hostile.comparisonContent(reader: false).entries), ["P:55%"])
        // The honest wording that explains the missing quote age and spread stays allowed and reachable.
        XCTAssertTrue(texts.contains(Self.quoteParagraph))
        XCTAssertTrue(Self.reaches(texts, "\\bspread\\b"))
        XCTAssertEqual(Model(Self.input(.final)).readerHistory.series, history.series, "the full-size history keeps every mark")
    }

    func testTheTwoFortySevenPercentTradesAreDistinctObservations() throws {
        let earlier = Self.retainedTrades[0], baseline = Self.retainedTrades[1]
        XCTAssertNotEqual(earlier.probability, baseline.probability)
        XCTAssertEqual(Self.figure(earlier.probability), Self.figure(baseline.probability))
        let before = Self.history(.before)
        XCTAssertEqual(Set(before.series[0].runs.flatMap(\.points).map(\.id)).count, 2, "two marks, never deduplicated by figure")
        // Inspecting the baseline trade: both slots bind the SAME observation.
        let same = Self.history(.before, inspecting: baseline.at)
        guard case .observation(let beforeID, _, _) = same.series[0].before,
              case .point(let inspectedID, _)? = same.inspection?.selections["P"] else { return XCTFail("bound slots") }
        XCTAssertEqual(beforeID, inspectedID)
        XCTAssertEqual(Self.slots(same)[0], [
            .figure("47%", provenance: "Oct 4, 3:04 PM UTC · last pre-match trade"),
            .figure("47%", provenance: "Oct 4, 3:04 PM UTC · recorded trade"),
        ])
        // Inspecting the earlier equal figure: a DIFFERENT observation with its own clock.
        let distinct = Self.history(.before, inspecting: earlier.at)
        guard case .point(let otherID, _)? = distinct.inspection?.selections["P"] else { return XCTFail("bound slot") }
        XCTAssertNotEqual(beforeID, otherID)
        XCTAssertEqual(Self.slots(distinct)[0], [
            .figure("47%", provenance: "Oct 4, 3:04 PM UTC · last pre-match trade"),
            .figure("47%", provenance: "Oct 4, 2:04 PM UTC · recorded trade"),
        ])
    }

    func testExactTimeInspectionShowsOnlyThatOriginalsTradeAndTheOpponentStaysAbsent() {
        let priceTrade = Self.history(.final, inspecting: 1_791_144_481)
        XCTAssertEqual(priceTrade.series.map { FieldHistoryGeometry10868.inspectedDisplay($0, in: priceTrade) }, [
            .figure("60%", provenance: "Oct 4, 8:08 PM UTC · recorded trade"), .words("No trade at this instant"),
        ])
        XCTAssertEqual(FieldHistoryGeometry10868.spokenValue(priceTrade),
                       "Inspecting · Oct 4, 8:08 PM UTC; Gerwyn Price: 60%; Luke Humphries: No trade at this instant")
        let humphriesTrade = Self.history(.final, inspecting: 1_791_150_784)
        XCTAssertEqual(humphriesTrade.series.map { FieldHistoryGeometry10868.inspectedDisplay($0, in: humphriesTrade) }, [
            .words("No trade at this instant"), .figure("99.9%", provenance: "Oct 4, 9:53 PM UTC · recorded trade"),
        ])
        XCTAssertEqual(priceTrade.inspection?.choices.map(\.id), Self.retainedTrades.map { "trade@\($0.at)" })
        XCTAssertFalse(Self.reaches(Self.reachableText(Self.input(.final, history: priceTrade), originals: nil), "(^|[^0-9.])40%"),
                       "the opponent is never the complement")
    }

    func testTheAcceptedComparisonMountsInlineAndFullSizeOverTheSameHistoryCopy() {
        for phase in Phase.allCases {
            for history in [Self.history(phase)] + Self.instants(phase).map({ Self.history(phase, inspecting: $0) }) {
                let input = Self.input(phase, history: history)
                let model = Model(input)
                let inline = Page(input: input).comparisonContent(reader: false)
                let full = Page(input: input, mode: .reader(.history)).comparisonContent(reader: true)
                // The actual composed View reads the history copy the leaf beside it draws.
                XCTAssertEqual(inline.history, model.presentedHistory, "\(phase)")
                XCTAssertEqual(full.history, model.readerHistory, "\(phase)")
                XCTAssertEqual(Page(input: input).historyContent(reader: false).input, model.presentedHistory)
                XCTAssertEqual([inline.label, full.label], ["Pre-match and recorded chance comparison",
                                                            "Pre-match and recorded chance comparison"])
                // The owner's input stays whole; each entry is the owner's own series.
                XCTAssertEqual(inline.entries.map(\.series), history.series)
                XCTAssertEqual(inline.entries.map(\.series.shape), [.diamond, .circle], "shape-keyed")
                // Exactly the shared resolver's slots — missing values as words, separate dates.
                XCTAssertEqual(inline.entries.map(\.slots), history.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: history) })
                XCTAssertEqual(full.entries.map(\.slots), inline.entries.map(\.slots), "the same readouts full size")
                XCTAssertEqual(inline.entries.map(RugbyMatchEventPageComparisonPresentation10868.spoken), history.series.map { series in
                    ([series.name] + [FieldHistoryGeometry10868.keyNote(series, in: history)].compactMap { $0 }
                        + FieldHistoryGeometry10868.readoutSlots(series, in: history).map(FieldHistoryGeometry10868.spokenSlot))
                        .joined(separator: ". ")
                })
            }
        }
        // Paired slots at the final: both players carry two equally ranked slots.
        XCTAssertEqual(Page(input: Self.input(.final)).comparisonContent(reader: false).entries.map { $0.slots.map(\.label) },
                       [["Pre-match", "Last recorded"], ["Pre-match", "Last recorded"]])
        XCTAssertEqual(Page(input: Self.input(.before)).comparisonContent(reader: false).entries.map { $0.slots.map(\.label) },
                       [["Pre-match"], ["Pre-match"]])
    }

    func testTheComparisonStandsInForTheSharedKeyOnlyWhileTheKeyWouldRepeatIt() {
        let input = Self.input(.final)
        let model = Model(input)
        XCTAssertTrue(model.hidesSharedKey)
        XCTAssertTrue(input.history.showsKey, "the owner's history input is never changed")
        XCTAssertEqual([model.presentedHistory.showsKey, model.readerHistory.showsKey], [false, false])
        // Every other field of both copies is the owner's.
        XCTAssertEqual(model.presentedHistory.series, input.history.series)
        XCTAssertEqual(model.presentedHistory.inspection, input.history.inspection)
        XCTAssertEqual(model.presentedHistory.readout, input.history.readout)
        XCTAssertEqual(model.presentedHistory.expand, input.history.expand)
        XCTAssertEqual(model.presentedHistory.plotHeight, input.history.plotHeight)
        XCTAssertEqual(FieldHistoryGeometry10868.actions(model.presentedHistory), FieldHistoryGeometry10868.actions(input.history))
        // A choose control or an owner key context keeps the owner's key.
        let choosing = Model(Self.input(.final, history: Self.history(.final, choosing: true)))
        XCTAssertFalse(choosing.hidesSharedKey)
        XCTAssertEqual([choosing.presentedHistory.showsKey, choosing.readerHistory.showsKey], [true, true])
        XCTAssertNotNil(choosing.presentedHistory.series[0].choose)
        let context = FieldHistoryKeyContext10868(label: "Outcome token", words: "Price to win", spoken: nil)
        let keyed = Model(Self.input(.final, history: Self.history(.final, keyContext: context)))
        XCTAssertFalse(keyed.hidesSharedKey)
        XCTAssertTrue(keyed.presentedHistory.showsKey)
        XCTAssertEqual(keyed.presentedHistory.series[0].keyContext, context)
    }

    // MARK: - Full-size heights

    func testFullSizeHeightsAreFiniteAndNeverShorterThanInlineForBothPlots() {
        // (owner full-size height, full-size history, full-size set plot); inline 302 and 220.
        let cases: [(CGFloat?, CGFloat, CGFloat)] = [
            (nil, 302, 220), (0, 302, 220), (-40, 302, 220), (CGFloat.nan, 302, 220), (CGFloat.infinity, 302, 220),
            (-CGFloat.infinity, 302, 220), (100, 302, 220), (260, 302, 260), (400, 400, 400),
        ]
        for (owner, history, sets) in cases {
            let words = owner.map { "\($0)" } ?? "nil"
            let model = Model(Self.input(.final, sets: Self.sets(readerHeight: owner), readerHeight: owner))
            XCTAssertEqual(model.readerHistory.plotHeight, history, words)
            XCTAssertEqual(model.readerSetsModel?.story.plotHeight, sets, words)
            XCTAssertTrue(model.readerHistory.plotHeight.isFinite, words)
            XCTAssertTrue(model.readerSetsModel?.story.plotHeight.isFinite ?? false, words)
            XCTAssertGreaterThanOrEqual(model.readerHistory.plotHeight, model.input.history.plotHeight, words)
            XCTAssertGreaterThanOrEqual(model.readerSetsModel?.story.plotHeight ?? 0, model.setsModel?.story.plotHeight ?? .infinity, words)
            XCTAssertEqual(model.setsModel?.story.plotHeight, 220, "the inline set plot keeps the owner's height")
        }
        // The rule is the accepted pure geometry, for both plots.
        XCTAssertEqual(RugbyMatchEventPageModel10868.readerPlotHeight(CGFloat.nan, history: 220), 220)
        XCTAssertEqual(RugbyMatchEventPageModel10868.readerPlotHeight(500, history: 220), 500)
    }

    // MARK: - Pre-match context on the set story

    func testTheSetStoryKeepsTheHistoricalPreMatchContextInlineAndFullSize() throws {
        var log: [String] = []
        let input = Self.input(.final)
        let page = Page(input: input, onAbout: { log.append("about") }, onSetSelect: { log.append("set:\($0)") },
                        onInteraction: { log.append("hold") })
        let inline = try XCTUnwrap(page.pageSetsContent()?.model.shownContext)
        let full = try XCTUnwrap(Page(input: input, mode: .reader(.sets)).readerSetsContent()?.model.shownContext)
        XCTAssertEqual(inline, full, "the same context inline and full size")
        XCTAssertEqual(inline.label, "Pre-match chances")
        XCTAssertEqual(inline.history, Model(input).preMatchContext)
        XCTAssertEqual(inline.history.series, input.history.series, "the owner's own series: nothing elected or formatted")
        XCTAssertEqual(inline.history.readout, .singleBefore(label: "Pre-match"), "the owner's own pre-match label")
        XCTAssertEqual(Self.slots(inline.history), [
            [.figure("47%", provenance: "Oct 4, 3:04 PM UTC · last pre-match trade")], [.words(Self.noBaseline)],
        ])
        let entries = RugbyMatchEventPageComparisonPresentation10868(history: inline.history, label: inline.label).entries
        XCTAssertEqual(entries.map(\.note), [nil, nil])
        XCTAssertEqual(log, [], "building the card and its context calls nothing; the context has no control")
        // The stream cell carries the same context.
        let stream = Self.stream()
        let streamed = Page(input: Self.input(.final, stream: stream), onSetSelect: { log.append("set:\($0)") })
        let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: "sets")
        let activation = StoryStreamCardActivation10868(
            card: ref, intents: stream.activationIntents(for: ref, resolved: stream.resolve(reduceMotion: false, actionable: true))) { _ in }
        XCTAssertEqual(streamed.streamSetsContent(activation: activation)?.model.shownContext, inline)
        // Neither a held set nor an inspected trade moves it.
        let held = Model(Self.input(.final, history: Self.history(.final, inspecting: 1_791_144_481), sets: Self.sets(selected: "set-3")))
        XCTAssertEqual(held.setsModel?.shownContext.map { Self.slots($0.history) }, Self.slots(inline.history))
        XCTAssertNil(held.setsModel?.shownContext?.history.inspection)
        // It never invents a complement or borrows a later trade.
        let texts = Self.setsText(try XCTUnwrap(Model(input).setsModel))
        XCTAssertFalse(Self.reaches(texts, "(^|[^0-9.])53%"))
        XCTAssertFalse(Self.reaches(texts, "99\\.9%"))
        XCTAssertTrue(texts.contains(Self.noBaseline))
        // Unknown chances never remove the actual counts.
        var absent = Self.history(.final)
        absent.plotAbsence = FieldHistoryPlotAbsence10868(title: "No retained trades", words: nil)
        let unknown = Model(Self.input(.final, history: absent))
        XCTAssertEqual(unknown.setsModel?.positions.count, 11)
        XCTAssertEqual(unknown.setsModel?.shownContext.map { Self.slots($0.history) },
                       [[.words("Not recorded at this trade")], [.words(Self.noBaseline)]])
        var unlabelled = Self.setsCopy
        unlabelled.contextLabel = nil
        let noContext = try XCTUnwrap(Model(Self.input(.final, sets: Self.sets(copy: unlabelled))).setsModel)
        XCTAssertNil(noContext.shownContext)
        XCTAssertEqual(noContext.positions.count, 11)
        // The constructed in-play set state carries the same historical context.
        let partial = Self.sets(rows: Array(Self.setRows().prefix(3)), selected: "set-3")
        XCTAssertEqual(Model(Self.input(.during, sets: partial, withSets: true)).setsModel?.shownContext.map { Self.slots($0.history) },
                       Self.slots(inline.history))
    }

    // MARK: - Actual sets

    func testTenSetsKeepTheSuppliedCumulativePathAndTheFinalFourSix() throws {
        let model = try XCTUnwrap(Model(Self.input(.final)).setsModel)
        XCTAssertEqual(model.story.rows.map(\.id), (1...10).map { "set-\($0)" }, "exact supplied order")
        XCTAssertEqual(model.story.rows.map { model.shownCounts($0).map { $0.figure ?? "" } },
                       Self.retainedSets.map { ["\($0.price)", "\($0.humphries)"] })
        XCTAssertEqual(model.story.rows.map(\.winner),
                       Self.retainedSets.map { Optional(Self.ref($0.winner == 0 ? Self.price : Self.humphries)) })
        XCTAssertEqual(model.story.rows.map(\.stateWords), [
            "Price leads", "Price leads", "Price leads", "Price leads", "Price leads", "Level",
            "Humphries leads", "Level", "Humphries leads", "Humphries won",
        ])
        guard case .row(let held, let index) = model.selection else { return XCTFail("the held set shows") }
        XCTAssertEqual([held.id, held.readoutLabel, "\(index)"], ["set-10", "Final", "9"])
        XCTAssertEqual(model.shownCounts(held).map(\.figure), ["4", "6"])
        // The owner's origin starts both lines, is not a set and is not selectable.
        let positions = model.positions
        XCTAssertEqual(positions.count, 11)
        XCTAssertEqual([positions[0].rowID, positions[0].selectableID ?? "none"], ["start", "none"])
        XCTAssertNil(positions[0].row)
        XCTAssertEqual(model.lines.map { $0.ys.first ?? nil }, [0, 0])
        // The origin is not a probability point: the history holds only the six trades.
        XCTAssertEqual(Self.history(.final).series.flatMap { $0.runs.flatMap(\.points) }.count, 6)
        // Ticks and checkpoints at their own sets.
        XCTAssertEqual(model.orderTicks, [
            DartsSetPlacedTick10868(position: 0, label: "Start"), DartsSetPlacedTick10868(position: 0.3, label: "Set 3"),
            DartsSetPlacedTick10868(position: 0.7, label: "Set 7"), DartsSetPlacedTick10868(position: 1, label: "Set 10"),
        ])
        XCTAssertEqual(model.scaleTicks.map(\.label), ["0", "3", "6"])
        XCTAssertEqual(model.checkpoints.map(\.setID), ["set-3", "set-7", "set-8", "set-10"])
        XCTAssertEqual(model.checkpoints.map(\.isSelected), [false, false, false, true])
        XCTAssertEqual(model.earlierID, "set-9")
        XCTAssertNil(model.laterID)
        // The owner's final headline agrees with the owner's last row; neither is computed here.
        XCTAssertEqual(Self.metrics(Model(Self.input(.final)).headline).map { $0.last }, ["Final sets=4", "Final sets=6"])
    }

    func testTheStepLinesUseSetOrderNeverTimeAndBreakAtUnplacedCounts() throws {
        let model = try XCTUnwrap(Model(Self.input(.final)).setsModel)
        let xs = model.positions.map(\.x)
        XCTAssertTrue(zip(xs, xs.dropFirst()).allSatisfy { abs(($1 - $0) - 0.1) < 1e-12 }, "evenly spaced by order")
        let counts: [[Int]] = [[0, 1, 2, 3, 3, 3, 3, 4, 4, 4, 4], [0, 0, 0, 0, 1, 2, 3, 4, 4, 5, 6]]
        XCTAssertEqual(model.lines.map(\.ys), counts.map { $0.map { Optional(Double($0) / 6) } },
                       "each owner count on the owner's scale, origin first")
        XCTAssertEqual(model.lines.map(\.segments.count), [1, 1])
        XCTAssertEqual(model.lines.map { $0.segments[0].count }, [21, 21], "each later set adds a hold and a step")
        let first = model.lines[1].segments[0]
        XCTAssertEqual([first[1].x, first[1].y], [0.1, 0], "the count holds until the next set")
        XCTAssertEqual(model.lines.map(\.style.accent), [Self.price.tint, Self.humphries.tint])
        XCTAssertEqual(model.lines.map(\.style.shape), [.diamond, .circle])
        // Taps hand back sets by order; the origin hands back nothing.
        XCTAssertNil(model.setID(atFraction: 0))
        XCTAssertEqual(model.setID(atFraction: 0.3), "set-3")
        XCTAssertEqual(model.setID(atFraction: 1), "set-10")
        XCTAssertNil(model.setID(atFraction: .nan))
        // The owner's scale is the extent: a count outside it is unplaced, never clamped.
        XCTAssertEqual(DartsSetGeometry10868.fraction(4, in: Self.defaultScale), 4.0 / 6.0)
        XCTAssertNil(DartsSetGeometry10868.fraction(7, in: Self.defaultScale))
        XCTAssertNil(DartsSetGeometry10868.fraction(.infinity, in: Self.defaultScale))
        XCTAssertNil(DartsSetGeometry10868.fraction(1, in: DartsSetScale10868(lower: 3, upper: 3, ticks: [], label: nil)))
        var rows = Self.setRows()
        let fifth = rows[4]
        rows[4] = DartsSetRow10868(id: fifth.id, label: fifth.label, readoutLabel: fifth.readoutLabel,
                                   counts: [DartsSetCount10868(ref: Self.ref(Self.price), value: 7, figure: "7"), fifth.counts[1]],
                                   winner: fifth.winner, stateWords: fifth.stateWords, spoken: fifth.spoken)
        let broken = SetModel(story: Self.sets(rows: rows), headline: Self.headline(.final))
        XCTAssertNil(broken.lines[0].ys[5])
        XCTAssertEqual(broken.lines[0].segments.count, 2, "an unplaced count breaks only its own line")
        XCTAssertEqual(broken.lines[1].segments.count, 1)
        XCTAssertEqual(broken.positions.count, 11, "an unplaced count keeps its position")
        // A wider owner scale moves every mark: the extent is the owner's, not derived.
        let wide = SetModel(story: Self.sets(scale: DartsSetScale10868(lower: 0, upper: 10, ticks: [], label: "Sets won")),
                            headline: Self.headline(.final))
        XCTAssertEqual(wide.lines[1].ys.last ?? nil, 0.6)
        // Without an origin the first set leads the order.
        let noOrigin = SetModel(story: Self.sets(origin: false), headline: Self.headline(.final))
        XCTAssertEqual(noOrigin.positions.count, 10)
        XCTAssertEqual(noOrigin.positions.first?.rowID, "set-1")
    }

    // MARK: - Independence and absence

    func testSelectingASetMovesNoOtherCursorOrCard() throws {
        var log: [String] = []
        let input = Self.input(.final)
        let page = Page(input: input, originals: Self.originals(.final),
                        onHistoryAction: { log.append("history:\($0)") },
                        onHistoryInspectionChoice: { log.append("choice:\($0)") },
                        onSetSelect: { log.append("set:\($0)") })
        page.pageSetsContent()?.onSelect?("set-3")
        XCTAssertEqual(log, ["set:set-3"], "a set selection hands back only its own id")
        let held = Self.input(.final, sets: Self.sets(selected: "set-3"))
        XCTAssertEqual(held.history, input.history)
        XCTAssertEqual(held.headline, input.headline)
        XCTAssertEqual(Model(held).readerHistory, Model(input).readerHistory)
        XCTAssertEqual(Page(input: held).comparisonContent(reader: false).entries,
                       Page(input: input).comparisonContent(reader: false).entries)
        XCTAssertEqual(Model(held).setsModel?.shownContext, Model(input).setsModel?.shownContext)
        XCTAssertEqual(Self.metrics(Model(held).headline).map { $0.last }, ["Final sets=4", "Final sets=6"],
                       "the final headline stays 4–6 while set 3 is held")
        let model = try XCTUnwrap(Model(held).setsModel)
        guard case .row(let row, _) = model.selection else { return XCTFail("set 3 shows") }
        XCTAssertEqual([row.readoutLabel, row.stateWords] + model.shownCounts(row).map { $0.figure ?? "" },
                       ["After set 3", "Price leads", "3", "0"])
        XCTAssertEqual(model.copy.unit, "Sets won", "an explicit sets unit")
        // An inspected trade never moves the held set.
        let inspected = Self.input(.final, history: Self.history(.final, inspecting: 1_791_147_763), sets: Self.sets(selected: "set-3"))
        XCTAssertEqual(Model(inspected).setsModel?.selectedID, "set-3")
    }

    func testMissingChancesKeepTheActualsAndMissingHistoryKeepsTheSets() throws {
        let noBaseline = Model(Self.input(.final, headline: Self.headline(.final, baseline: false)))
        XCTAssertEqual(Self.metrics(noBaseline.headline), [
            ["Pre-match: \(Self.noBaseline)", "Final sets=4"], ["Pre-match: \(Self.noBaseline)", "Final sets=6"],
        ])
        XCTAssertEqual(noBaseline.setsModel?.story.rows.count, 10)
        // The owner's explicit plot absence keeps the set story whole.
        var history = Self.history(.final)
        history.plotAbsence = FieldHistoryPlotAbsence10868(title: "No retained trades", words: "This update carries no trades.")
        let absent = Model(Self.input(.final, history: history))
        XCTAssertEqual(absent.setsModel?.positions.count, 11)
        XCTAssertEqual(Page(input: absent.input).comparisonContent(reader: false).entries.map { $0.slots.map(\.display) }, [
            [.words("Not recorded at this trade"), .words("Not recorded at this trade")],
            [.words(Self.noBaseline), .words("Not recorded at this trade")],
        ], "unbound readings show the owner's words, never a figure")
        // A withheld set story does not erase the headline finish.
        let noSets = Model(Self.input(.final, withSets: false))
        XCTAssertEqual(noSets.mountedCards, [.history])
        XCTAssertEqual(Self.metrics(noSets.headline).map { $0.last }, ["Final sets=4", "Final sets=6"])
    }

    func testArbitraryDuplicateForeignAndWithdrawnIdentitiesFailClosedWhileNeighboursWork() throws {
        // Arbitrary players and rows: three constructed players, two sets, no headline.
        let refs = (1...3).map { FieldChooserOriginalRef10868(scope: "constructed", source: "owner", marketID: "m", outcomeID: "p\($0)") }
        let arbitrary = SetModel(story: DartsSetStory10868(
            players: refs.enumerated().map { DartsSetPlayer10868(ref: $1, name: "Player \($0 + 1)") },
            origin: DartsSetOrigin10868(id: "o", counts: refs.map { DartsSetCount10868(ref: $0, value: 0, figure: "0") }),
            rows: [
                DartsSetRow10868(id: "a", label: "A", readoutLabel: "After A", counts: refs.map { DartsSetCount10868(ref: $0, value: 1, figure: "1") },
                                 winner: nil, stateWords: "Even", spoken: "After A"),
                DartsSetRow10868(id: "b", label: "B", readoutLabel: "After B", counts: refs.map { DartsSetCount10868(ref: $0, value: 2, figure: "2") },
                                 winner: refs[0], stateWords: "Even", spoken: "After B"),
            ],
            scale: DartsSetScale10868(lower: 0, upper: 2, ticks: [], label: nil), orderTicks: [], checkpoints: [],
            selectedSetID: "b", plotHeight: 200, copy: Self.setsCopy), headline: nil)
        XCTAssertEqual(arbitrary.lines.count, 3)
        XCTAssertEqual(arbitrary.positions.count, 3)
        XCTAssertTrue(arbitrary.lines.allSatisfy { $0.style.accent == nil }, "no headline: neutral colour")
        XCTAssertEqual(arbitrary.lines[2].ys, [0, 0.5, 1])

        // A duplicated set id is not selectable and a held duplicate is missing.
        var rows = Self.setRows()
        let second = rows[1]
        rows[1] = DartsSetRow10868(id: "set-1", label: second.label, readoutLabel: second.readoutLabel, counts: second.counts,
                                   winner: second.winner, stateWords: second.stateWords, spoken: second.spoken)
        let duplicated = SetModel(story: Self.sets(rows: rows, selected: "set-1"), headline: Self.headline(.final))
        XCTAssertEqual(duplicated.positions.prefix(4).map(\.selectableID), [nil, nil, nil, "set-3"])
        XCTAssertEqual(duplicated.selection, .missing("That set is not in this update"))
        // A foreign count shows the owner's words; the neighbour keeps its figure.
        var foreignRows = Self.setRows()
        let fourth = foreignRows[3]
        foreignRows[3] = DartsSetRow10868(id: fourth.id, label: fourth.label, readoutLabel: fourth.readoutLabel,
                                          counts: [fourth.counts[0], Self.count(Self.humphries, 1, scope: "polymarket|OTHER|winner")],
                                          winner: Self.ref(Self.humphries, scope: "polymarket|OTHER|winner"),
                                          stateWords: fourth.stateWords, spoken: fourth.spoken)
        let foreign = SetModel(story: Self.sets(rows: foreignRows, selected: "set-4"), headline: Self.headline(.final))
        guard case .row(let row, _) = foreign.selection else { return XCTFail("set 4 shows") }
        XCTAssertEqual(foreign.shownCounts(row).map(\.figure), ["3", nil])
        XCTAssertNil(foreign.lines[1].ys[4])
        XCTAssertEqual(foreign.lines[0].ys[4], 0.5)
        XCTAssertNil(foreign.style(row.winner).accent, "a foreign winner draws the neutral colour")
        XCTAssertEqual(foreign.style(foreignRows[4].winner).accent, Self.humphries.tint)
        // A player listed twice resolves no count at all.
        let twice = SetModel(story: Self.sets(players: [DartsSetPlayer10868(ref: Self.ref(Self.price), name: "Price"),
                                                        DartsSetPlayer10868(ref: Self.ref(Self.price), name: "Price again")]),
                             headline: Self.headline(.final))
        XCTAssertTrue(twice.lines.allSatisfy { $0.ys.allSatisfy { $0 == nil } })
        // A checkpoint naming a withdrawn set keeps its words, no control.
        let withdrawn = SetModel(story: Self.sets(checkpoints: Self.checkpointList + [
            DartsSetCheckpoint10868(id: "cp-gone", setID: "set-11", label: "Gone", detail: nil),
        ]), headline: Self.headline(.final))
        XCTAssertNil(withdrawn.checkpoints.last?.setID)
        // A held original from another scope or duplicated identity opens nothing.
        XCTAssertTrue(Model.heldOriginalIsUnavailable(Self.originals(.final, selection: Self.selection(Self.price, scope: "polymarket|OTHER|originals"))))
        let doubled = Self.originals(.final, list: [Self.original(Self.price, .final), Self.original(Self.price, .final), Self.original(Self.humphries, .final)])
        XCTAssertNil(Details.content(catalogue: doubled.catalogue, selection: doubled.selection))
        XCTAssertNotNil(Details.content(catalogue: doubled.catalogue, selection: Self.selection(Self.humphries)))
        XCTAssertFalse(Model.heldOriginalIsUnavailable(Self.originals(.final)))
    }

    func testHeldSetHistoryAndOriginalSurviveOmissionAndRestoreOnlyByExactIdentity() throws {
        let gone = SetModel(story: Self.sets(rows: Self.setRows(Self.retainedSets.filter { $0.number != 3 }), selected: "set-3"),
                            headline: Self.headline(.final))
        XCTAssertEqual(gone.selection, .missing("That set is not in this update"))
        XCTAssertFalse(gone.positions.contains(where: \.isSelected), "no neighbour stands in")
        XCTAssertNil(gone.earlierID)
        XCTAssertNil(gone.laterID)
        XCTAssertEqual(gone.positions.count, 10)
        let back = SetModel(story: Self.sets(selected: "set-3"), headline: Self.headline(.final))
        guard case .row(let row, let index) = back.selection else { return XCTFail("the exact set restores") }
        XCTAssertEqual([row.id, "\(index)"], ["set-3", "2"])
        XCTAssertEqual([back.earlierID, back.laterID], ["set-2", "set-4"])

        // The held trade time omitted from an arrival: the owner's words, never a neighbour's figure.
        let held = 1_791_144_481
        let omitted = Self.history(.final, inspecting: held, omitting: held)
        XCTAssertEqual(omitted.inspection?.x, Double(held - Self.scheduledStart), "the held instant stays")
        XCTAssertEqual(omitted.series.map { FieldHistoryGeometry10868.inspectedDisplay($0, in: omitted) },
                       [.words("No trade at this instant"), .words("No trade at this instant")])
        let restored = Self.history(.final, inspecting: held)
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedDisplay(restored.series[0], in: restored),
                       .figure("60%", provenance: "Oct 4, 8:08 PM UTC · recorded trade"))

        let withdrawn = Self.originals(.final, list: [Self.original(Self.humphries, .final)])
        XCTAssertTrue(Model.heldOriginalIsUnavailable(withdrawn))
        XCTAssertNil(Details.content(catalogue: withdrawn.catalogue, selection: withdrawn.selection))
        let again = Self.originals(.final)
        XCTAssertEqual(Details.content(catalogue: again.catalogue, selection: again.selection)?.outcome, "Gerwyn Price")
    }

    // MARK: - Interaction

    func testThePageHoldsOnceBeforeEachActionNeverPassivelyAndNeverInAReaderOrTheAbout() throws {
        var log: [String] = []
        let input = Self.input(.final)
        let originals = Self.originals(.final)
        func page(_ mode: DartsSetEventPageMode10868) -> Page {
            Page(input: input, mode: mode, originals: originals,
                 onAbout: { log.append("about") }, onSource: { log.append("source:\($0.id)") },
                 onOriginalSelect: { log.append("original:\($0.identity.side == Self.humphries.token ? "H" : "P")") },
                 onOriginalHistory: { _ in log.append("originalHistory") },
                 onHeadlineOpen: { log.append("headline:\($0.ref.outcomeID == Self.price.token ? "P" : "H")") },
                 onHistoryAction: { log.append("history:\($0)") },
                 onHistoryInspectionChoice: { log.append("choice:\($0)") },
                 onHistoryPlotPosition: { log.append("position:\($0)") },
                 onCardOpen: { log.append("open:\($0.rawValue)") },
                 onSetSelect: { log.append("set:\($0)") },
                 onReaderIntent: { log.append("reader:\(Tests.words($0))") },
                 onInteraction: { log.append("hold") })
        }
        let main = page(.page)
        _ = (main.headlineContent(), main.historyContent(reader: false), main.comparisonContent(reader: false),
             main.pageSetsContent(), main.catalogueContent(), main.originalDetailsContent(), main.aboutContent())
        XCTAssertEqual(log, [], "building the page and its leaves calls nothing")
        main.headlineContent()?.onAbout?()
        main.historyContent(reader: false).onAction?("history.expand")
        main.historyContent(reader: false).onInspectionChoice?("trade@1791147763")
        main.pageSetsContent()?.onSelect?("set-3")
        main.pageSetsContent()?.onExpand?()
        main.pageSetsContent()?.onReport?()
        main.catalogueContent()?.onSelect?(Self.selection(Self.humphries))
        XCTAssertEqual(log, ["hold", "about", "hold", "history:history.expand", "hold", "choice:trade@1791147763",
                             "hold", "set:set-3", "hold", "open:sets", "hold", "about", "hold", "original:H"])
        log.removeAll()
        // Full-size content and the About keep the exact callbacks.
        let reader = page(.reader(.sets))
        reader.readerSetsContent()?.onSelect?("set-4")
        reader.readerSetsContent()?.onReport?()
        reader.openReaderAbout()
        page(.reader(.history)).historyContent(reader: true).onAction?("history.details")
        page(.about).aboutContent()?.onSource?(Self.report)
        Page.bind(reader.onReaderIntent, .back)?()
        Page.bind(page(.original).onReaderIntent, .done)?()
        XCTAssertEqual(log, ["set:set-4", "about", "about", "history:history.details", "source:sky-sports-report",
                             "reader:back", "reader:done"])
    }

    func testAStoryInTheStreamHoldsThroughItsOwnActivationOnly() throws {
        var log: [String] = []
        let stream = Self.stream()
        let input = Self.input(.final, stream: stream)
        let page = Page(input: input, onAbout: { log.append("about") }, onSetSelect: { log.append("set:\($0)") },
                        onInteraction: { log.append("hold") })
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: "sets")
        let activation = StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
            if case .interaction = intent { log.append("activate") } else { log.append("other") }
        }
        XCTAssertNil(page.pageSetsContent(), "with a stream the card lives in the stream")
        let card = try XCTUnwrap(page.streamSetsContent(activation: activation))
        XCTAssertNil(card.onExpand, "the stream offers its own open")
        card.onSelect?("set-8")
        card.onReport?()
        XCTAssertEqual(log, ["activate", "set:set-8", "activate", "about"])
        XCTAssertEqual(Model(input).storyLink("sets")?.card, .sets)
        XCTAssertNil(Model(Self.input(.before, stream: stream)).storyLink("sets"), "before play no set story mounts")
    }

    func testAbsentCallbacksOfferNoControlAndTheHookAloneDoesNothing() throws {
        var log: [String] = []
        let page = Page(input: Self.input(.final), originals: Self.originals(.final), onInteraction: { log.append("hold") })
        XCTAssertNil(page.headlineContent()?.onOpen)
        XCTAssertNil(page.headlineContent()?.onAbout)
        XCTAssertNil(page.historyContent(reader: false).onAction)
        XCTAssertNil(page.historyContent(reader: false).onInspectionChoice)
        let sets = try XCTUnwrap(page.pageSetsContent())
        XCTAssertNil(sets.onSelect)
        XCTAssertNil(sets.onExpand)
        XCTAssertNil(sets.onReport)
        XCTAssertTrue(sets.model.positions.allSatisfy { SetModel.selectAction($0, onSelect: nil) == nil })
        XCTAssertNil(page.catalogueContent()?.onSelect)
        XCTAssertNil(page.originalDetailsContent()?.onHistory)
        XCTAssertNil(page.aboutContent()?.onSource)
        let controls = page.readerControls(.sets)
        XCTAssertFalse(controls.canGoBack)
        XCTAssertNil(controls.previous)
        page.openReaderAbout()
        XCTAssertEqual(log, [])
    }

    func testFullSizeCardsReuseTheSameViewsAndAreNeverShorterThanInline() throws {
        var intents: [DartsSetReaderIntent10868] = []
        let input = Self.input(.final)
        let model = Model(input)
        let inline = try XCTUnwrap(model.setsModel), full = try XCTUnwrap(model.readerSetsModel)
        XCTAssertEqual(full.story.rows, inline.story.rows)
        XCTAssertEqual(full.story.selectedSetID, inline.story.selectedSetID)
        XCTAssertEqual(full.story.checkpoints, inline.story.checkpoints)
        XCTAssertEqual([inline.story.plotHeight, full.story.plotHeight], [220, 300])
        XCTAssertGreaterThanOrEqual(full.story.plotHeight, 300)
        XCTAssertEqual([input.history.plotHeight, model.readerHistory.plotHeight], [302, 370])
        XCTAssertNil(model.readerHistory.expand)
        XCTAssertEqual(model.readerHistory.series, input.history.series)
        XCTAssertEqual(model.readerHistory.inspection, input.history.inspection)
        // An owner reader height shorter than inline never shrinks either chart.
        let short = Model(Self.input(.final, sets: Self.sets(readerHeight: 100), readerHeight: 100))
        XCTAssertEqual(short.readerHistory.plotHeight, 302)
        XCTAssertEqual(short.readerSetsModel?.story.plotHeight, 220)
        let page = Page(input: input, mode: .reader(.sets), onReaderIntent: { intents.append($0) })
        XCTAssertEqual(page.readerSetsContent()?.model, full)
        XCTAssertEqual(page.comparisonContent(reader: true).entries.map(\.slots), page.comparisonContent(reader: false).entries.map(\.slots))
        XCTAssertEqual(page.comparisonContent(reader: true).history.plotHeight, 370)
        let controls = page.readerControls(.sets)
        XCTAssertEqual(controls.previous, .history)
        XCTAssertNil(controls.next)
        XCTAssertTrue(controls.canGoBack)
        XCTAssertEqual(page.readerControls(.history).next, .sets)
        Page.bind(page.onReaderIntent, .previous(.history))?()
        Page.bind(page.onReaderIntent, .back)?()
        XCTAssertEqual(intents, [.previous(.history), .back])
        // A card the phase does not mount has no full-size content or neighbours.
        let before = Page(input: Self.input(.before), mode: .reader(.sets), onReaderIntent: { intents.append($0) })
        XCTAssertNil(before.readerSetsContent())
        XCTAssertFalse(before.readerControls(.sets).canGoBack)
        XCTAssertNil(Model(Self.input(.before)).neighbour(of: .history, offset: 1))
    }

    func testLayoutPlansForCompactWideAndAccessibilitySizes() {
        XCTAssertEqual(Model.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertEqual(Model.readoutArrangements(accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(Model.readoutArrangements(accessibilitySize: true), [.stacked])
        XCTAssertEqual(Model.readingOrder, [.headline, .notice, .anchor, .cards, .originals])
        XCTAssertGreaterThan(Model.sortPriority(.headline), Model.sortPriority(.cards))
        XCTAssertEqual(AflMatchScoringGeometry10868.plotFrame(in: CGSize(width: 300, height: 220), gutter: 32, room: 12),
                       CGRect(x: 32, y: 12, width: 256, height: 196))
        XCTAssertNil(AflMatchScoringGeometry10868.plotFrame(in: CGSize(width: 30, height: 220), gutter: 32, room: 12))
        XCTAssertEqual(DartsSetGeometry10868.y(0, in: CGRect(x: 0, y: 10, width: 100, height: 200)), 210, "the scale's lower end sits low")
        XCTAssertEqual(DartsSetGeometry10868.y(1, in: CGRect(x: 0, y: 10, width: 100, height: 200)), 10)
    }

    // MARK: - Live, actual and settlement

    func testTheConstructedDuringSnapshotIsLabelledAndClaimsNoLiveOrFinalFact() throws {
        let during = Self.phaseTexts(.during)
        XCTAssertTrue(Self.reaches(during, "\\bconstructed\\b"), "the in-play snapshot names itself constructed")
        XCTAssertTrue(during.contains("Constructed in-play snapshot for review · no live evidence · score not captured"))
        for phase in Phase.allCases {
            let texts = Self.phaseTexts(phase)
            XCTAssertFalse(Self.reaches(texts, "\\blive\\b(?! evidence)"), "\(phase)")
            XCTAssertFalse(Self.reaches(texts, "projected final(?! remain unverified)"), "\(phase)")
            XCTAssertFalse(texts.contains("Current chance"), "\(phase)")
        }
        // An owner may admit its own in-play set state (CONSTRUCTED here, the
        // first three rows): it shows during play, never before.
        let partial = Self.sets(rows: Array(Self.setRows().prefix(3)), selected: "set-3")
        XCTAssertEqual(Model(Self.input(.during, sets: partial, withSets: true)).setsModel?.positions.count, 4)
        XCTAssertNil(Model(Self.input(.before, sets: partial, withSets: true)).setsModel)
    }

    func testTheReportedActualStaysApartFromContractGradesAndHistoricalChances() throws {
        let originals = Self.originals(.final)
        let price = try XCTUnwrap(Details.content(catalogue: originals.catalogue, selection: Self.selection(Self.price)))
        let humphries = try XCTUnwrap(Details.content(catalogue: originals.catalogue, selection: Self.selection(Self.humphries)))
        XCTAssertEqual([price.result?.words, humphries.result?.words], ["Resolved No", "Resolved Yes"])
        XCTAssertEqual(humphries.result?.provenance, "Polymarket resolution · time not captured")
        XCTAssertEqual(humphries.readings.map(\.text), [Self.noBaseline], "his Details never borrow a later trade as pre-match")
        XCTAssertTrue(humphries.about.contains(Details.Row(label: Details.historicalLabel, value: "99.9%, recorded Oct 4, 9:53 PM UTC")))
        XCTAssertFalse((price.readings + humphries.readings).contains { $0.text == "4" || $0.text == "6" },
                       "the contract never carries the set score")
        // The headline finish is the report, apart from the grade.
        let headline = try XCTUnwrap(Model(Self.input(.final)).headline)
        XCTAssertEqual(FieldHeadlineModel10868(headline).competitors.compactMap { $0.metrics.last.flatMap(FieldChaseModel10868.detail) },
                       ["Sky Sports report · Oct 4, 10:05 PM UTC", "Sky Sports report · Oct 4, 10:05 PM UTC"])
        // The history's readings are recordings, never current.
        let history = Self.history(.final)
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(history.series[0], in: history).map(\.label), ["Pre-match", "Last recorded"])
        XCTAssertFalse(Self.reaches(Self.phaseTexts(.final), "current probability"))
    }

    // MARK: - Phase-admitted reachable text

    func testEachPhaseReachesOnlyItsOwnAdmittedFactsOnEverySurface() {
        let before = Self.phaseTexts(.before)
        let during = Self.phaseTexts(.during)
        let finished = Self.phaseTexts(.final)

        XCTAssertEqual(Self.leaks(before, Self.beforeForbidden), [])
        XCTAssertEqual(Self.leaks(during, Self.duringForbidden), [])
        // Contract rules may show verbatim before play.
        XCTAssertTrue(before.contains(Self.retainedRulesParagraphs[2]))
        for pattern in ["(^|[^0-9.])47%", NSRegularExpression.escapedPattern(for: Self.noBaseline)] {
            XCTAssertTrue(Self.reaches(before, pattern), pattern)
            XCTAssertTrue(Self.reaches(during, pattern), pattern)
            XCTAssertTrue(Self.reaches(finished, pattern), pattern)
        }
        XCTAssertTrue(Self.reaches(during, "(^|[^0-9.])60%"))
        // Positive control: the final reaches every final fact and every trade.
        for pattern in Self.finalFacts + Self.clocksAfter(0) + ["(^|[^0-9.])60%"] {
            XCTAssertTrue(Self.reaches(finished, pattern), pattern)
        }
    }

    func testThePhaseTextGuardCatchesTheLeakItWasWrittenForAndIsMeaningAware() {
        // The leak class Design caught on AFLW and squash: a final About behind
        // Info on an earlier page.
        let leaked = Self.reachableText(Self.input(.before, about: Self.about(.final)), originals: Self.originals(.before))
        let hits = Self.leaks(leaked, Self.beforeForbidden)
        for pattern in ["\\bSky Sports\\b", Self.pairPattern("4–6"), "\\bsix\\b", "(^|[^0-9.:])252([^0-9%:]|$)", "\\blegs?\\b"] {
            XCTAssertTrue(hits.contains { $0.hasPrefix("\(pattern) ⟵") }, pattern)
        }
        XCTAssertFalse(Self.leaks(Self.reachableText(Self.input(.during, about: Self.about(.final)), originals: nil),
                                  Self.duringForbidden).isEmpty)
        // The final originals handed to the before page are caught too.
        XCTAssertFalse(Self.leaks(Self.reachableText(Self.input(.before), originals: Self.originals(.final)),
                                  Self.beforeForbidden).isEmpty)
        // Meaning-aware: a chance, a clock, a date, a rule or an id is never a set count.
        XCTAssertEqual(Self.leaks(["47%", "46%", "64%", "4%", "6%", "60%", "Pre-match: 47%, Oct 4, 3:04 PM UTC · last pre-match trade",
                                   "0.4699999944", "1791126269", "P@1791122669", "October 4 at 2:00PM ET", "50-50", "7 days",
                                   Self.retainedProviderURL, Self.price.token],
                                  Self.finalFacts), [])
        XCTAssertFalse(Self.leaks(["4–6"], Self.finalFacts).isEmpty)
        XCTAssertFalse(Self.leaks(["3–0"], Self.finalFacts).isEmpty)
        XCTAssertFalse(Self.leaks(["6"], Self.finalFacts).isEmpty)
        XCTAssertFalse(Self.leaks(["Final sets"], Self.finalFacts).isEmpty)
        XCTAssertFalse(Self.leaks(["Humphries leads"], Self.finalFacts).isEmpty)
    }

    // MARK: - Action payloads

    func testEveryActionPayloadCarriesOnlyItsPhasesAdmittedKeys() {
        for phase in Phase.allCases {
            let payloads = Self.payloads(Self.input(phase), originals: Self.originals(phase))
            XCTAssertFalse(payloads.isEmpty, "\(phase)")
            XCTAssertEqual(Self.payloadLeaks(payloads, admittedThrough: Self.cutoff(phase)), [], "\(phase)")
            XCTAssertTrue(payloads.allSatisfy { !$0.hasPrefix("original:") || $0.hasPrefix("original:\(Self.originalsScope)|") })
            XCTAssertEqual(payloads.contains { $0.hasPrefix("set:") }, phase == .final, "\(phase)")
        }
        // Before play the history steps carry pre-start trades only; the
        // headline opens carry no observation.
        let before = Self.payloads(Self.input(.before), originals: Self.originals(.before))
        XCTAssertTrue(before.contains("history.action:history.inspect@1791126269"))
        XCTAssertTrue(before.contains("history.action:history.inspect@1791122669"))
        XCTAssertEqual(before.filter { $0.hasPrefix("headline:") },
                       ["headline:\(Self.price.token)@none", "headline:\(Self.humphries.token)@none"])
        XCTAssertEqual(before.filter { $0.hasPrefix("original:") }, [
            "original:\(Self.originalsScope)|5263083|\(Self.price.token)", "original:\(Self.originalsScope)|5263083|\(Self.humphries.token)",
        ])
        // During play the headline opens the CONSTRUCTED cut's own key; the
        // opponent with no recorded trade carries none.
        let during = Self.payloads(Self.input(.during), originals: Self.originals(.during))
        XCTAssertEqual(during.filter { $0.hasPrefix("headline:") },
                       ["headline:\(Self.price.token)@P@1791144481", "headline:\(Self.humphries.token)@none"])
        // At the final every set and checkpoint hands back its own exact id.
        let finished = Self.payloads(Self.input(.final), originals: Self.originals(.final))
        XCTAssertEqual(Array(finished.filter { $0.hasPrefix("set:") }.prefix(14)),
                       (1...10).map { "set:set-\($0)" } + ["set:set-3", "set:set-7", "set:set-8", "set:set-10"])
        XCTAssertTrue(finished.contains("card:sets"))
        // An earlier held trade, a missing held original and a missing held
        // set change the payloads exactly.
        let earlier = Self.payloads(Self.input(.before, history: Self.history(.before, inspecting: 1_791_122_669)),
                                    originals: Self.originals(.before, list: [Self.original(Self.humphries, .before)]))
        XCTAssertTrue(earlier.contains("history.choice:trade@1791122669"))
        XCTAssertEqual(Self.payloadLeaks(earlier, admittedThrough: Self.cutoff(.before)), [])
        XCTAssertEqual(earlier.filter { $0.hasPrefix("original:") }, ["original:\(Self.originalsScope)|5263083|\(Self.humphries.token)"])
        let missingSet = Self.payloads(Self.input(.final, sets: Self.sets(selected: "set-11")), originals: Self.originals(.final))
        XCTAssertFalse(missingSet.contains("set:set-11"), "a held id no row carries is never handed back")
        XCTAssertEqual(missingSet.filter { $0.hasPrefix("set:") }, finished.filter { $0.hasPrefix("set:") },
                       "every control keeps its own exact id; no neighbour stands in for the missing one")
    }

    func testThePayloadGuardCatchesAFutureKeyUsedBeforePlay() {
        // The horse leak class: a later default position sent before play.
        let hostile = Self.payloads(Self.input(.before, history: Self.history(.before, windowOverride: .final)),
                                    originals: Self.originals(.before))
        let caught = Self.payloadLeaks(hostile, admittedThrough: Self.cutoff(.before))
        XCTAssertTrue(caught.contains("history.action:history.inspect@1791150784"))
        XCTAssertFalse(Self.payloadLeaks(["headline:\(Self.price.token)@P@1791147763"], admittedThrough: Self.cutoff(.before)).isEmpty)
        XCTAssertFalse(Self.payloadLeaks(["history.choice:trade@1791145033"], admittedThrough: Self.cutoff(.during)).isEmpty)
        XCTAssertEqual(Self.payloadLeaks(["history.choice:trade@1791144481"], admittedThrough: Self.cutoff(.during)), [])
    }

    // MARK: - Rules fidelity

    func testOriginalRulesAreVerbatimRetainedText() throws {
        XCTAssertEqual(Self.sha256(Self.retainedRulesParagraphs.joined(separator: "\n\n")), Self.retainedRulesHash)
        XCTAssertEqual(Self.sha256(Self.retainedTitle), Self.retainedTitleHash)
        for phase in Phase.allCases {
            let originals = Self.originals(phase)
            for player in Self.players {
                let content = try XCTUnwrap(Details.content(catalogue: originals.catalogue, selection: Self.selection(player)))
                XCTAssertEqual(content.rules, .verified(Self.retainedRulesParagraphs))
                guard case .verified(let paragraphs) = content.rules else { return XCTFail("verified rules") }
                XCTAssertEqual(Self.sha256(paragraphs.joined(separator: "\n\n")), Self.retainedRulesHash)
                XCTAssertEqual(content.title, Self.retainedTitle)
                XCTAssertEqual(content.outcome, player.name)
            }
        }
    }
}
