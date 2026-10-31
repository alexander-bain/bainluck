import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the poker tournament page (`poker-tournament`) as a composition of
/// the accepted leaves, in the owner's explicit before-final-table and final
/// roles.
///
/// PREPARED / NOT RUN. The view is SwiftUI and is not rasterised here. What is
/// asserted is the composition the page defers to: the role gates and the leaves
/// each role mounts with which exact owner input; every retained trade as its
/// own singleton mark in its player's stable shape and phase fill, same-second
/// and identical prints kept as separate positions; the equal-size, own-dated
/// readouts tied to the history's own inspection ring; the starting chip share
/// beside the separately traded win chance on the host's one scale; the country
/// card; final-only standings, prizes and country apart from every chance; the
/// independent Yes and No originals with their verbatim rules; the role-matching
/// outcome reader; once-only holds, the stream's own interaction, exact
/// payloads and passive reads; and the arrangement candidates. Nothing here
/// claims a compile, a rendered fit, VoiceOver, a native runtime or a live route.
///
/// ARCHIVED, generated mechanically by `/tmp/poker-fixture-gen.py` from
/// `pokerCapture.json` (sha256 39e96a1b…a2094bb410e) into the "Retained fixture
/// (generated)" section at the end of this file: all 13 props and 26 sides with
/// their ids, names, kinds, predicates, conditions, verbatim rules, provider
/// URLs, transcribed chip counts, finishes and prizes, side tokens and
/// resolutions, and all 5,329 trades as (position, t, p, size, tx) in capture
/// order — every point's token equals its side's token, which the generator
/// asserts before emitting the token once per side; the scheduled final-table
/// time, the result report time, the null actual final-table start and null
/// tournament baseline, and the capture's baseline and result meanings.
///
/// CONSTRUCTED: every display string, figure, Pacific clock word (from each
/// trade's own t), label, tint, shape, scope, id, action id, position key,
/// heading, About text, story, scale, the owner's before-table election (the
/// last retained position strictly before the scheduled final table), chip
/// shares (this test divides the transcribed chip counts; the view never does),
/// the reported country words, and every rejected, rogue, withdrawn, foreign,
/// duplicate, changed and bad-payload case. Each owner supplies only what it
/// could know in its role; the rogue owners exist to prove the page withholds.
@MainActor
final class PokerEventPagePresentation10868Tests: XCTestCase {
    private typealias Tests = PokerEventPagePresentation10868Tests
    private typealias Screen = PokerEventPagePresentation10868
    private typealias Model = PokerEventPageModel10868
    private typealias Chance = PokerChanceComparisonModel10868
    private typealias Originals = OriginalMarketDetails9483
    private typealias Role = PokerEventPageRole10868
    private typealias Ref = FieldChooserOriginalRef10868

    // MARK: - Retained shapes (filled by the generated fixture)

    /// One retained trade exactly as captured: its position in its side's list,
    /// its clock, its price and size as the capture's own number text, and its
    /// transaction.
    fileprivate typealias RetainedTrade = (position: Int, t: Int, p: String, size: String, tx: String)

    fileprivate struct RetainedSide {
        let side: String
        let token: String
        let resolved: Bool
        let trades: [RetainedTrade]
    }

    fileprivate struct RetainedMarket {
        let id: String
        let name: String
        let kind: String
        let predicate: String
        let condition: String
        let rules: String
        let providerURL: String
        let chips: Int?
        let finish: Int?
        let prize: Int?
        let sides: [RetainedSide]
    }

    // MARK: - Retained, read

    private struct Trade: Equatable {
        let position: Int
        let t: Int
        let p: Double
        /// The capture's own price text.
        let text: String
        let size: String
        let tx: String
    }

    private struct Side {
        let label: String
        let token: String
        let resolved: Bool
        let trades: [Trade]
    }

    private struct Market {
        let id: String
        let name: String
        let kind: String
        let predicate: String
        let condition: String
        let rules: String
        let providerURL: String
        let chips: Int?
        let finish: Int?
        let prize: Int?
        let yes: Side
        let no: Side

        var sides: [Side] { [yes, no] }
    }

    private static func read(_ retained: RetainedMarket) -> Market {
        func side(_ label: String) -> Side {
            let found = retained.sides.first(where: { $0.side == label })!
            return Side(label: label, token: found.token, resolved: found.resolved, trades: found.trades.map {
                Trade(position: $0.position, t: $0.t, p: Double($0.p)!, text: $0.p, size: $0.size, tx: $0.tx)
            })
        }
        return Market(id: retained.id, name: retained.name, kind: retained.kind, predicate: retained.predicate,
                      condition: retained.condition, rules: retained.rules, providerURL: retained.providerURL,
                      chips: retained.chips, finish: retained.finish, prize: retained.prize,
                      yes: side("Yes"), no: side("No"))
    }

    private static let markets: [Market] = retainedMarkets.map { read($0) }
    private static func byID(_ id: String) -> Market { markets.first(where: { $0.id == id })! }

    private static let wasnock = byID("563320")
    private static let mizrachi = byID("563321")
    private static let dunaway = byID("563322")
    private static let bojovic = byID("563325")
    private static let american = byID("557372")
    /// The nine named final-table players, in the capture's (chip) order.
    private static var players: [Market] { Array(markets.prefix(9)) }
    /// Every winner prop: the nine players and the three placeholders.
    private static var winners: [Market] { Array(markets.prefix(12)) }
    private static var placeholders: [Market] { Array(markets[9..<12]) }
    /// The chart's featured players: circle, triangle, diamond.
    private static var featured: [Market] { [mizrachi, wasnock, dunaway] }

    private static var scheduledFinalTable: Int { retainedScheduledFinalTable }
    private static var resultReportAt: Int { retainedResultReportAt }

    // MARK: - Owner (CONSTRUCTED)

    private static let scope = "constructed:poker:main-event"
    private static let originalsScope = "constructed:poker:originals"
    private static let storyScope = "constructed:poker:stories"
    private static let source = "polymarket"
    private static let unavailablePlayer = "Player unavailable in this update"

    private static let clockFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "America/Los_Angeles")
        formatter.dateFormat = "MMM d, h:mm:ss a"
        return formatter
    }()

    private static func clockTime(_ t: Int) -> String {
        clockFormatter.string(from: Date(timeIntervalSince1970: TimeInterval(t))) + " PT"
    }

    private static func clock(_ t: Int) -> String { clockTime(t) + " · Polymarket trade" }

    /// The test owner's figure: whole percent when it is one, else one decimal.
    private static func percent(_ p: Double) -> String {
        let value = p * 100
        let whole = value.rounded()
        if abs(value - whole) < 0.05 { return "\(Int(whole))%" }
        return String(format: "%.1f%%", value)
    }

    private static func ordinal(_ n: Int) -> String {
        switch n {
        case 1: return "1st"
        case 2: return "2nd"
        case 3: return "3rd"
        default: return "\(n)th"
        }
    }

    private static func dollars(_ amount: Int) -> String {
        let digits = Array(String(amount))
        var grouped = ""
        for (index, digit) in digits.enumerated() {
            if index > 0 && (digits.count - index) % 3 == 0 { grouped.append(",") }
            grouped.append(digit)
        }
        return "$" + grouped
    }

    /// Each side's own meaning. Yes and No are independent originals; No is never "loses".
    private static func meaning(_ market: Market, _ side: Side) -> String {
        switch (market.kind, side.label) {
        case ("nationality", "Yes"): return "American winner"
        case ("nationality", _): return "Winner from outside the USA"
        case (_, "Yes"): return "Wins the tournament"
        default: return "Doesn’t win the tournament"
        }
    }

    private static func ref(_ market: Market, _ side: Side, scope other: String? = nil) -> Ref {
        Ref(scope: other ?? Self.scope, source: source, marketID: market.id, outcomeID: side.token)
    }

    private static func seriesID(_ market: Market, _ side: Side) -> String { "\(market.id):\(side.label)" }

    private static func pointID(_ market: Market, _ side: Side, _ index: Int) -> String {
        "\(market.id):\(side.label):\(index)"
    }

    /// The test owner's election: the last retained position strictly before
    /// the scheduled final table. Not pre-tournament.
    private static func baselineIndex(_ side: Side) -> Int? {
        side.trades.lastIndex(where: { $0.t < scheduledFinalTable })
    }

    /// What an owner in `role` holds: before the table only earlier trades;
    /// at the final every trade through the result report.
    private static func visible(_ side: Side, _ role: Role) -> [(Int, Trade)] {
        side.trades.enumerated().compactMap { pair -> (Int, Trade)? in
            let shown = role == .final ? pair.element.t <= resultReportAt : pair.element.t < scheduledFinalTable
            return shown ? (pair.offset, pair.element) : nil
        }
    }

    private static func shape(_ market: Market) -> FieldHistoryShape10868 {
        if market.id == mizrachi.id { return .circle }
        if market.id == wasnock.id { return .triangle }
        return .diamond
    }

    private static func tint(_ market: Market) -> Color {
        if market.id == mizrachi.id { return Color(red: 0.15, green: 0.39, blue: 0.92) }
        if market.id == wasnock.id { return Color(red: 0.85, green: 0.47, blue: 0.02) }
        return Color(red: 0.49, green: 0.23, blue: 0.93)
    }

    // MARK: History and readouts (CONSTRUCTED owner)

    /// One original side: every visible trade its own singleton run, hollow
    /// before the scheduled final table, filled later; ids are positions.
    private static func series(_ market: Market, _ side: Side, _ role: Role, choose: Bool) -> FieldHistorySeries10868 {
        let runs = visible(side, role).map { pair in
            FieldHistoryRun10868(id: "run:" + pointID(market, side, pair.0), points: [
                FieldHistoryPoint10868(id: pointID(market, side, pair.0), x: Double(pair.1.t), probability: pair.1.p,
                                       style: pair.1.t < scheduledFinalTable ? .hollow : .filled),
            ])
        }
        let before: FieldHistoryReading10868
        if let index = baselineIndex(side) {
            before = .observation(pointID: pointID(market, side, index), figure: percent(side.trades[index].p),
                                  provenance: clock(side.trades[index].t))
        } else {
            before = .absent(words: "No earlier captured trade")
        }
        let action = FieldHistoryAction10868(id: "choose:" + seriesID(market, side), label: "Show \(market.name)",
                                             spokenLabel: nil, isAvailable: true)
        return FieldHistorySeries10868(
            id: seriesID(market, side), name: market.name, shape: shape(market), tint: tint(market), runs: runs,
            links: [], labelPointID: nil, before: before, recorded: .absent(words: "No retained trade for this outcome"),
            absentWords: "No retained trades", choose: choose ? action : nil)
    }

    private static let dayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "America/Los_Angeles")
        formatter.dateFormat = "MMM d"
        return formatter
    }()

    private static let shortFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "America/Los_Angeles")
        formatter.dateFormat = "h:mm a"
        return formatter
    }()

    /// The reference's dated axis ticks: first trade, midpoint, horizon — each
    /// a date line and a Pacific clock line. The earlier role's horizon is the
    /// scheduled final-table restart, labelled scheduled; the final's is the
    /// result report.
    private static func dateTicks(lower: Int, upper: Int, role: Role) -> [FieldHistoryTick10868] {
        func lines(_ t: Int) -> [String] {
            let date = Date(timeIntervalSince1970: TimeInterval(t))
            return [dayFormatter.string(from: date), shortFormatter.string(from: date) + " PT"]
        }
        let horizon = role == .final ? "Result reported" : "Final table · scheduled"
        return [FieldHistoryTick10868(value: Double(lower), lines: lines(lower)),
                FieldHistoryTick10868(value: Double(lower) + Double(upper - lower) / 2, lines: lines(lower + (upper - lower) / 2)),
                FieldHistoryTick10868(value: Double(upper), lines: lines(upper) + [horizon])]
    }

    /// The owner's history: the first pick is selected and inspected; the
    /// domain spans `span` (default: the picks) from its first visible trade to
    /// the role's horizon, as the reference does. `mini` is the Details
    /// composition (no key, ticks, chart control or inspection).
    private static func history(_ role: Role, _ picks: [(Market, Side)], inspect: Int?, span: [Side]? = nil,
                                mini: Bool = false) -> FieldHistoryInput10868 {
        let lead = picks[0]
        let positions = visible(lead.1, role)
        let times = (span ?? picks.map { $0.1 }).flatMap { side in visible(side, role).map { $0.1.t } }
        let upper = role == .final ? resultReportAt : scheduledFinalTable
        let lower = times.min() ?? upper - 86_400
        var inspection: FieldHistoryInspection10868?
        if !mini, let index = inspect {
            let trade = lead.1.trades[index]
            let choices = positions.map { pair in
                FieldHistoryInspectionChoice10868(id: pointID(lead.0, lead.1, pair.0), lines: [clockTime(pair.1.t)],
                                                  spoken: "\(percent(pair.1.p)), \(clockTime(pair.1.t))",
                                                  isSelected: pair.0 == index)
            }
            inspection = FieldHistoryInspection10868(
                x: Double(trade.t), caption: "Inspected trade · \(clockTime(trade.t))",
                selections: [seriesID(lead.0, lead.1): .point(id: pointID(lead.0, lead.1, index), spoken: percent(trade.p))],
                choices: choices, choicePresentation: .slider(label: "Inspected trade"),
                note: "Only exact retained trades are shown.")
        }
        func action(_ id: String, _ label: String) -> FieldHistoryAction10868? {
            mini ? nil : FieldHistoryAction10868(id: id, label: label, spokenLabel: nil, isAvailable: true)
        }
        let guides = role == .final && !mini
            ? [FieldHistoryGuide10868(id: "final-table", x: Double(scheduledFinalTable), label: "Scheduled final table")]
            : []
        let absence = positions.isEmpty
            ? FieldHistoryPlotAbsence10868(title: "No retained trades",
                                           words: "This original outcome has no traded history in this capture.")
            : nil
        return FieldHistoryInput10868(
            title: "Win chance by trade",
            caption: role == .final ? "Every retained trade through the reported result"
                : "Every retained trade before the scheduled final table",
            series: picks.map { series($0.0, $0.1, role, choose: !mini) },
            selection: .series(id: seriesID(lead.0, lead.1), missingWords: unavailablePlayer),
            domain: FieldHistoryDomain10868(lower: Double(lower), upper: Double(upper)),
            ceiling: 1,
            yTicks: [0.0, 0.25, 0.5, 0.75, 1.0].map { FieldHistoryTick10868(value: $0, lines: [percent($0)]) },
            xTicks: mini ? [] : dateTicks(lower: lower, upper: upper, role: role),
            guides: guides,
            breaks: [],
            readout: .singleBefore(label: "Before final table"),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow: a trade before the scheduled final table",
                                              filled: role == .final ? "Filled: a later trade" : nil),
            comparisonExplanation: nil,
            notes: ["Each mark is one retained trade. Trades are never joined."],
            summary: "Win chance, one mark per retained trade",
            plotHeight: 260,
            unboundReadingWords: "Not tied to a retained trade",
            plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil, details: nil,
            expand: action("history.expand", "Open full size"),
            inspect: nil,
            previous: action("history.previous", "Earlier trade"),
            next: action("history.next", "Later trade"),
            inspection: inspection,
            layout: .expanded,
            plotAbsence: absence,
            showsKey: !mini)
    }

    /// The same history with only the named parts replaced.
    private static func rebuilt(_ h: FieldHistoryInput10868, series: [FieldHistorySeries10868]? = nil,
                                inspection: FieldHistoryInspection10868?? = nil) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: h.title, caption: h.caption, series: series ?? h.series, selection: h.selection, domain: h.domain,
            ceiling: h.ceiling, yTicks: h.yTicks, xTicks: h.xTicks, guides: h.guides, breaks: h.breaks,
            readout: h.readout, markKey: h.markKey, comparisonExplanation: h.comparisonExplanation, notes: h.notes,
            summary: h.summary, plotHeight: h.plotHeight, unboundReadingWords: h.unboundReadingWords,
            plotUnavailableWords: h.plotUnavailableWords, windows: h.windows, scale: h.scale,
            moreOriginals: h.moreOriginals, details: h.details, expand: h.expand, inspect: h.inspect,
            previous: h.previous, next: h.next, inspection: inspection ?? h.inspection, layout: h.layout,
            probabilityLowerBound: h.probabilityLowerBound, probabilityRangeExplanation: h.probabilityRangeExplanation,
            selectedReadout: h.selectedReadout, inspectionRingShape: h.inspectionRingShape,
            plotAbsence: h.plotAbsence, showsKey: h.showsKey)
    }

    /// The same series with other runs or another id.
    private static func reseries(_ s: FieldHistorySeries10868, id: String? = nil,
                                 runs: [FieldHistoryRun10868]? = nil) -> FieldHistorySeries10868 {
        FieldHistorySeries10868(id: id ?? s.id, name: s.name, shape: s.shape, tint: s.tint, runs: runs ?? s.runs,
                                links: s.links, labelPointID: s.labelPointID, before: s.before, recorded: s.recorded,
                                absentWords: s.absentWords, choose: s.choose)
    }

    private static let chanceCopy = PokerChanceCopy10868(
        baselineLabel: "Before final table", inspectedBeforeTableLabel: "Inspected before final table",
        inspectedEarlierLabel: "Inspected earlier trade", recordedLabel: "Recorded chance",
        sameObservationLabel: "Before final table · selected trade",
        baselineUnavailable: "Unavailable", baselineUnavailableDetail: "No earlier captured trade",
        inspectedUnavailable: "No trade", inspectedUnavailableDetail: "No retained trade for this outcome",
        preTournamentUnavailable: "Pre-tournament chance unavailable", resultLabel: "Reported finish")

    private static func reading(_ market: Market, _ side: Side, _ index: Int) -> PokerChanceReading10868 {
        let trade = side.trades[index]
        return PokerChanceReading10868(pointID: pointID(market, side, index), probability: trade.p,
                                       figure: percent(trade.p), date: clock(trade.t))
    }

    /// The reported result words for one original side; final only.
    private static func resultWords(_ market: Market, _ side: Side) -> String {
        if market.kind == "winner", side.label == "Yes", let finish = market.finish { return "Finished \(ordinal(finish))" }
        return side.resolved ? "Happened" : "Didn’t happen"
    }

    /// `rogue`: final-only fields ride along on a before-table owner.
    private static func comparison(_ role: Role, _ market: Market, _ side: Side, inspect: Int?,
                                   rogue: Bool = false) -> PokerChanceComparisonInput10868 {
        let later = role == .final || rogue
        return PokerChanceComparisonInput10868(
            role: role, seriesID: seriesID(market, side), name: market.name, meaning: meaning(market, side),
            baseline: later ? baselineIndex(side).map { reading(market, side, $0) } : nil,
            inspected: inspect.map { reading(market, side, $0) },
            result: later ? resultWords(market, side) : nil,
            copy: chanceCopy)
    }

    private enum Inspect {
        /// Before: the before-table position. Final: the last retained position.
        case standard
        case none
        case at(Int)
    }

    private static func inspectIndex(_ role: Role, _ inspect: Inspect, _ side: Side) -> Int? {
        switch inspect {
        case .standard: return role == .final ? side.trades.indices.last : baselineIndex(side)
        case .none: return nil
        case .at(let index): return index
        }
    }

    // MARK: Cards (CONSTRUCTED owner)

    private static func chooserOriginal(_ market: Market) -> FieldChooserOriginal10868 {
        let side = market.yes
        let reading: FieldChooserReading10868
        if let index = baselineIndex(side) {
            reading = FieldChooserReading10868(label: "Before final table",
                                               value: .recorded(text: percent(side.trades[index].p), detail: clock(side.trades[index].t)))
        } else {
            reading = FieldChooserReading10868(label: "Before final table", value: .missing("No earlier captured trade"))
        }
        return FieldChooserOriginal10868(ref: ref(market, side), name: market.name, plan: .single(reading),
                                         preview: FieldChooserPreview10868(history: nil, absence: "No preview in this list"),
                                         movement: nil, clock: nil, result: nil,
                                         browseStatus: side.trades.isEmpty ? "No retained trades" : "Retained trades")
    }

    /// Every winner prop's Yes side and the country Yes side.
    private static let catalogue: [FieldChooserOriginal10868] = (winners + [american]).map { chooserOriginal($0) }

    private static let chipScale = FieldOutlookScale10868(
        ceiling: 0.4, ticks: [0.0, 0.1, 0.2, 0.3, 0.4].map { FieldOutlookTick10868(probability: $0, label: percent($0)) },
        words: "0–40% · chip share and win chance on one scale")

    private static let wholeScale = FieldOutlookScale10868(
        ceiling: 1, ticks: [0.0, 0.5, 1.0].map { FieldOutlookTick10868(probability: $0, label: percent($0)) },
        words: "0–100% chance")

    private static let chipCopy = PokerChipCopy10868(
        eyebrow: "STARTING STACKS", title: "How the field shaped up", shareKey: "Share of chips",
        chanceKey: "Win chance before final table", measureNote: "Before final table",
        note: "Chip share describes the starting stack. Win chances come from separate markets.",
        graphicLabel: "Chip share and win chance by player", shareUnavailable: "Chip count unavailable",
        chanceUnavailable: "No earlier captured trade", offScale: "Above this scale", resultLabel: "Reported finish",
        empty: "No players", chooseHint: "Shows this player in the chart")

    /// The test divides the transcribed chip counts; the owner hands the result to the view.
    private static var totalChips: Int { players.compactMap { $0.chips }.reduce(0, +) }

    private static func share(_ market: Market) -> PokerChipMeasure10868? {
        guard let chips = market.chips else { return nil }
        let value = Double(chips) / Double(totalChips)
        return PokerChipMeasure10868(value: value, text: String(format: "%.1f%%", value * 100))
    }

    private static func winChance(_ market: Market) -> PokerChipMeasure10868? {
        guard let index = baselineIndex(market.yes) else { return nil }
        let p = market.yes.trades[index].p
        return PokerChipMeasure10868(value: p, text: percent(p))
    }

    private static func prizeWords(_ market: Market) -> String? {
        guard let finish = market.finish, let prize = market.prize else { return nil }
        return "\(ordinal(finish)) · \(dollars(prize))"
    }

    private static func chipRow(_ market: Market, scope other: String? = nil) -> PokerChipRow10868 {
        PokerChipRow10868(ref: ref(market, market.yes, scope: other), label: market.name, share: share(market),
                          chance: winChance(market))
    }

    private static func chips(_ role: Role, rows: [PokerChipRow10868]? = nil, scale: FieldOutlookScale10868? = nil,
                              selected: Market? = nil, rogue: Bool = false) -> PokerChipCardInput10868 {
        let chosen = selected ?? mizrachi
        let chosenDate = baselineIndex(chosen.yes).map { clock(chosen.yes.trades[$0].t) }
        return PokerChipCardInput10868(
            scope: scope, catalogue: catalogue, rows: rows ?? players.map { chipRow($0) },
            selected: PokerChipSelected10868(ref: ref(chosen, chosen.yes), name: chosen.name, share: share(chosen),
                                             chance: winChance(chosen), chanceDate: chosenDate,
                                             result: role == .final || rogue ? prizeWords(chosen) : nil),
            scale: scale ?? chipScale, copy: chipCopy, unavailableWords: unavailablePlayer,
            toggle: FieldHistoryAction10868(id: "chips.leading", label: "Show the leading four", spokenLabel: nil, isAvailable: true),
            source: FieldHistoryAction10868(id: "chips.source", label: "Chip counts at the final table", spokenLabel: nil, isAvailable: true))
    }

    /// The same chip input with only the named parts replaced.
    private static func chips(_ input: PokerChipCardInput10868, rows: [PokerChipRow10868]? = nil,
                              scale: FieldOutlookScale10868? = nil,
                              toggle: FieldHistoryAction10868?? = nil) -> PokerChipCardInput10868 {
        PokerChipCardInput10868(scope: input.scope, catalogue: input.catalogue, rows: rows ?? input.rows,
                                selected: input.selected, scale: scale ?? input.scale, copy: input.copy,
                                unavailableWords: input.unavailableWords, toggle: toggle ?? input.toggle,
                                source: input.source)
    }

    private static let countryCopy = PokerCountryCopy10868(
        eyebrow: "WINNER’S COUNTRY", title: "An American champion?", graphicLabel: "Chance of an American winner",
        chanceUnplaced: "Not drawn on this scale", offScale: "Above this scale",
        actualUnknown: "Winner’s country not reported", actualLabel: "Actual winner", note: nil,
        entryLabel: "Original prop & both outcomes", entryHint: "Opens the original Yes and No outcomes")

    /// CONSTRUCTED from the resolved country Yes and the reported 1st place.
    private static var countryActual: PokerCountryActual10868 {
        PokerCountryActual10868(label: "Actual winner", words: "USA", detail: mizrachi.name)
    }

    private static func country(actual: PokerCountryActual10868?, scope other: String? = nil,
                                reading: FieldChooserReading10868? = nil) -> PokerCountryCardInput10868 {
        let side = american.yes
        let trade = side.trades[baselineIndex(side)!]
        let before = FieldChooserReading10868(label: "Before final table · Yes",
                                              value: .recorded(text: percent(trade.p), detail: clock(trade.t)))
        return PokerCountryCardInput10868(
            scope: scope, catalogue: catalogue, ref: ref(american, side, scope: other), reading: reading ?? before,
            probability: trade.p, actual: actual, scale: wholeScale, copy: countryCopy,
            unavailableWords: "Country prop unavailable in this update")
    }

    private static let resultCopy = HistoricalChanceCopy10868(
        eyebrow: "MIZRACHI’S CHANGING CHANCE", title: "From one in five to the title",
        beforeLabel: "Before final table", checkpointLabel: "Last retained trade",
        endpointUnavailable: "Not recorded for this comparison",
        beforeKey: "Outline: last trade before the scheduled final table", checkpointKey: "Filled: the last retained trade",
        graphicLabel: "Two win chances", chanceUnplaced: "Not drawn on this scale", offScale: "Above this scale",
        actualTitle: "ACTUAL RESULT", actualLabel: "Reported finish", actualUnavailable: "Finish not confirmed",
        context: "Each chance is one dated trade; the finish was reported separately",
        expandLabel: "Open the chance story full size", expandHint: nil, detailsLabel: "How to read this story",
        detailsHint: nil, openHint: "Opens this trade in the history")

    /// The champion's chance-to-result card.
    private static func result(phase: FieldOutlookPhase10868) -> HistoricalChanceInput10868 {
        let side = mizrachi.yes
        let before = baselineIndex(side)!
        let last = side.trades.count - 1
        let subject = ref(mizrachi, side)
        func endpoint(_ index: Int, _ label: String) -> FieldChooserReading10868 {
            FieldChooserReading10868(label: label, value: .recorded(text: percent(side.trades[index].p),
                                                                     detail: clock(side.trades[index].t)))
        }
        let beforeReading = endpoint(before, "Before final table")
        let laterReading = endpoint(last, "Last retained trade")
        let finish = FieldChooserReading10868(label: "Reported finish",
                                              value: .recorded(text: ordinal(mizrachi.finish!), detail: "PokerNews report"))
        return HistoricalChanceInput10868(
            scope: scope, catalogue: catalogue, subject: HistoricalChanceSubject10868(ref: subject, name: mizrachi.name),
            readings: [HistoricalChanceReading10868(ref: subject, endpoint: .before, reading: beforeReading),
                       HistoricalChanceReading10868(ref: subject, endpoint: .checkpoint, reading: laterReading)],
            observations: [
                HistoricalChanceObservation10868(ref: subject, endpoint: .before,
                                                 observation: FieldMovementObservation10868(probability: side.trades[before].p, reading: beforeReading),
                                                 key: pointID(mizrachi, side, before)),
                HistoricalChanceObservation10868(ref: subject, endpoint: .checkpoint,
                                                 observation: FieldMovementObservation10868(probability: side.trades[last].p, reading: laterReading),
                                                 key: pointID(mizrachi, side, last)),
            ],
            actuals: [HistoricalChanceActual10868(place: FieldFinishPlace10868(ref: subject, reading: finish), outcome: "Won the tournament")],
            scale: wholeScale, phase: phase, copy: resultCopy, unavailableWords: unavailablePlayer)
    }

    private static func stream(_ withResult: Bool, cards extra: [StoryStreamPresentation10868.Card] = []) -> StoryStreamPresentation10868 {
        var cards = [StoryStreamPresentation10868.Card(id: "chips", name: "How the field shaped up"),
                     StoryStreamPresentation10868.Card(id: "country", name: "Winner’s country")]
        if withResult { cards.append(StoryStreamPresentation10868.Card(id: "result", name: "Chance to result")) }
        return StoryStreamPresentation10868(
            scope: storyScope, heading: "Main Event stories", cards: cards + extra,
            primary: StoryStreamPresentation10868.CardRef(scope: storyScope, id: "chips"),
            companion: StoryStreamPresentation10868.CardRef(scope: storyScope, id: "country"),
            wide: true)
    }

    private static func stories(_ withResult: Bool) -> [PokerEventPageStory10868] {
        var stories = [PokerEventPageStory10868(cardID: "chips", card: .chips),
                       PokerEventPageStory10868(cardID: "country", card: .country)]
        if withResult {
            stories.append(PokerEventPageStory10868(cardID: "result", card: .result, reason: "The champion’s chance, start to finish"))
        }
        return stories
    }

    private static var chooser: FieldChooserInput10868 {
        FieldChooserInput10868(
            scope: scope, intro: nil,
            featured: FieldChooserFeatured10868(title: "In your chart", badge: nil, refs: featured.map { ref($0, $0.yes) },
                                                emptyWords: "No players in your chart"),
            context: nil, more: nil, browse: nil, catalogue: catalogue, frame: nil,
            selected: FieldChooserSelected10868(ref: ref(mizrachi, mizrachi.yes), words: "In focus", unavailableWords: unavailablePlayer),
            unavailableWords: unavailablePlayer, chooseHint: "Shows this player in the chart")
    }

    private static func pageCopy(_ role: Role) -> PokerEventPageCopy10868 {
        PokerEventPageCopy10868(
            eyebrow: "POKER · MAIN EVENT", title: "Who wins the Main Event?", context: "Nine players at the final table",
            status: role == .final ? "Final · result reported" : "Before the final table",
            aboutLabel: "About", aboutHint: "How these chances were recorded",
            comparisonUnavailable: "Chances for this view are unavailable",
            originalsUnavailable: "Original outcomes for this view are unavailable", storiesLabel: "Main Event stories",
            storyUnavailable: "This story is not available in this update", allPropsLabel: "All 26 original outcomes")
    }

    private static func readerHeader(_ role: Role) -> FieldEventPageReaderHeader10868 {
        FieldEventPageReaderHeader10868(title: "Main Event winner",
                                        state: role == .final ? "Final · win chances by trade" : "Before the final table · win chances by trade")
    }

    private static func about(_ role: Role) -> FieldEventPageAbout10868 {
        FieldEventPageAbout10868(title: "About these chances",
                                 paragraphs: role == .final ? [retainedBaselineMeaning, retainedResultMeaning] : [retainedBaselineMeaning])
    }

    private struct Parts {
        var role: Role
        var copy: PokerEventPageCopy10868
        var reader: FieldEventPageReaderHeader10868
        var comparison: PokerChanceComparisonInput10868
        var history: FieldHistoryInput10868
        var readerPlotHeight: CGFloat?
        var chips: PokerChipCardInput10868?
        var country: PokerCountryCardInput10868?
        var result: HistoricalChanceInput10868?
        var stream: StoryStreamPresentation10868
        var stories: [PokerEventPageStory10868]
        var chooser: FieldChooserInput10868?
        var about: FieldEventPageAbout10868?

        var input: PokerEventPageInput10868 {
            PokerEventPageInput10868(role: role, copy: copy, reader: reader, comparison: comparison, history: history,
                                     readerPlotHeight: readerPlotHeight, chips: chips, country: country, result: result,
                                     stream: stream, stories: stories, chooser: chooser, about: about)
        }
    }

    /// The page an owner in `role` builds. `rogue`: a before-table owner that
    /// also passes every final-only field, which the page must withhold.
    private static func parts(_ role: Role, inspect: Inspect = .standard, rogue: Bool = false) -> Parts {
        let side = mizrachi.yes
        let index = inspectIndex(role, inspect, side)
        let later = role == .final || rogue
        return Parts(
            role: role, copy: pageCopy(role), reader: readerHeader(role),
            comparison: comparison(role, mizrachi, side, inspect: index, rogue: rogue),
            history: history(role, featured.map { ($0, $0.yes) }, inspect: index, span: players.map { $0.yes }),
            readerPlotHeight: 520,
            chips: chips(role, rogue: rogue),
            country: country(actual: later ? countryActual : nil),
            result: later ? result(phase: .final) : nil,
            stream: stream(later), stories: stories(later), chooser: chooser, about: about(role))
    }

    // MARK: Originals, sides and the outcome reader (CONSTRUCTED owner)

    /// Each side's own exact identity: the side token, never "Yes"/"No" alone.
    private static func identity(_ market: Market, _ side: Side) -> Originals.Identity {
        Originals.Identity(source: source, market: market.id, side: side.token)
    }

    private static func selection(_ market: Market, _ side: Side, scope other: String? = nil) -> Originals.Selection {
        Originals.Selection(scope: other ?? originalsScope, identity: identity(market, side))
    }

    private static func paragraphs(_ rules: String) -> [String] { rules.components(separatedBy: "\n\n") }

    private static func original(_ market: Market, _ side: Side, _ role: Role,
                                 rules: Originals.Rules? = nil) -> Originals.Original {
        let pregame: Originals.Reading
        if let index = baselineIndex(side) {
            let trade = side.trades[index]
            pregame = .value(percent(trade.p), placement: trade.p, provenance: clock(trade.t))
        } else {
            pregame = .missing("No earlier captured trade")
        }
        let grade = Originals.Grade(words: side.resolved ? "Happened" : "Didn’t happen",
                                    provenance: "Reported \(clockTime(resultReportAt))")
        let about = Originals.About(
            source: "Polymarket", rules: rules ?? .verified(paragraphs(market.rules)),
            provenance: [Originals.Row(label: "Condition", value: market.condition),
                         Originals.Row(label: "Outcome token", value: side.token),
                         Originals.Row(label: "Provider", value: market.providerURL)],
            historicalQuote: nil)
        return Originals.Original(identity: identity(market, side), title: market.predicate, outcome: meaning(market, side),
                                  mode: role == .final ? .result : .pregame, pregame: pregame, later: nil,
                                  grade: role == .final ? grade : nil, about: about, beforeLabel: "Before final table")
    }

    /// Every one of the 26 sides, optionally without one exact identity.
    private static func originalsCatalogue(_ role: Role, without omitted: Originals.Identity? = nil) -> Originals.Catalogue {
        Originals.Catalogue(scope: originalsScope, originals: markets.flatMap { market in
            market.sides.map { original(market, $0, role) }.filter { $0.identity != omitted }
        })
    }

    private static func recordedHistory(_ role: Role, _ market: Market, _ side: Side) -> Originals.RecordedHistory {
        let held = original(market, side, role)
        var readings = [Originals.RecordedReading(label: "Before final table", marker: .hollow, reading: held.pregame)]
        if role == .final, let last = side.trades.indices.last {
            let trade = side.trades[last]
            readings.append(Originals.RecordedReading(
                label: "Last retained trade", marker: .solid,
                reading: .value(percent(trade.p), placement: trade.p, provenance: clock(trade.t))))
        }
        // The player's separately reported finish, for either side of its winner prop; never the contract result.
        var finish: Originals.ReportedFinish?
        if role == .final {
            finish = market.finish.map { Originals.ReportedFinish.reported(words: ordinal($0), spoken: nil) }
                ?? .unlinked(words: "No player finish for this prop")
        }
        func action(_ id: String, _ label: String) -> FieldHistoryAction10868 {
            FieldHistoryAction10868(id: id, label: label, spokenLabel: nil, isAvailable: true)
        }
        return Originals.RecordedHistory(
            selection: selection(market, side), mode: held.mode, seriesID: seriesID(market, side),
            availability: "Current probability unavailable · recorded history below", readings: readings, movement: nil,
            history: history(role, [(market, side)], inspect: nil, mini: true), finishLabel: "Reported finish",
            finish: finish, preview: action("original.preview", "Preview history"),
            expand: action("original.expand", "Expand chart"), explore: action("original.explore", "Explore history"),
            unmatchedWords: "Recorded history unavailable for this outcome")
    }

    private static func originals(_ role: Role, _ market: Market, _ side: Side,
                                  catalogue: Originals.Catalogue? = nil) -> FieldEventPageOriginals10868 {
        FieldEventPageOriginals10868(catalogue: catalogue ?? originalsCatalogue(role), selection: selection(market, side),
                                     recorded: recordedHistory(role, market, side), heading: "All props",
                                     context: "26 original outcomes", emptyWords: "No original outcomes",
                                     unavailableChoice: "Original outcome", tint: tint(market))
    }

    /// The originals handed to the page with the owner role they were built for.
    private static func bundle(_ role: Role, _ market: Market, _ side: Side,
                               catalogue: Originals.Catalogue? = nil) -> PokerEventPageOriginals10868 {
        PokerEventPageOriginals10868(role: role, originals: originals(role, market, side, catalogue: catalogue))
    }

    private static func sides(_ market: Market) -> PokerOriginalSides10868 {
        PokerOriginalSides10868(label: "Outcome", sides: market.sides.map {
            PokerOriginalSide10868(label: $0.label, meaning: meaning(market, $0), selection: selection(market, $0))
        })
    }

    /// One side's own full history and readouts, built by an owner in `role`.
    private static func outcome(_ role: Role, _ market: Market, _ side: Side) -> PokerOutcomeReaderInput10868 {
        let index = inspectIndex(role, .standard, side)
        return PokerOutcomeReaderInput10868(
            comparison: comparison(role, market, side, inspect: index),
            history: history(role, [(market, side)], inspect: index),
            readerPlotHeight: 480,
            note: role == .final ? "Reported finish shown apart from every chance" : "Each mark is one retained trade")
    }

    // MARK: Callbacks

    /// Records every callback and hook, in order, with its exact value.
    private final class Log {
        var events: [String] = []
        var refs: [Ref] = []
        var controls: [FieldChooserControl10868] = []
        var selections: [OriginalMarketDetails9483.Selection] = []
        var histories: [OriginalMarketDetails9483.HistoryIntent] = []
        var stream: [StoryStreamPresentation10868.Intent] = []
        var opens: [FieldMovementOpen10868] = []
        var ids: [String] = []
        var positions: [Double] = []
    }

    private static func screen(_ input: PokerEventPageInput10868, mode: PokerEventPageMode10868 = .page, log: Log,
                               originals: PokerEventPageOriginals10868? = nil, sides: PokerOriginalSides10868? = nil,
                               outcome: PokerOutcomeReaderInput10868? = nil, hold: Bool = true) -> Screen {
        let interaction: (() -> Void)? = hold ? { log.events.append("hold") } : nil
        return Screen(
            input: input, mode: mode, originals: originals, sides: sides, outcome: outcome,
            onAbout: { log.events.append("about") },
            onAllProps: { log.events.append("allProps") },
            onOriginalSelect: { log.events.append("select"); log.selections.append($0) },
            onOriginalHistory: { log.events.append("history"); log.histories.append($0) },
            onStoryIntent: { log.events.append("story"); log.stream.append($0) },
            onHistoryAction: { log.events.append("historyAction"); log.ids.append($0) },
            onHistoryInspectionChoice: { log.events.append("historyChoice"); log.ids.append($0) },
            onHistoryPlotPosition: { log.events.append("historyPosition"); log.positions.append($0) },
            onOutcomeAction: { log.events.append("outcomeAction"); log.ids.append($0) },
            onOutcomeInspectionChoice: { log.events.append("outcomeChoice"); log.ids.append($0) },
            onOutcomePlotPosition: { log.events.append("outcomePosition"); log.positions.append($0) },
            onChoose: { log.events.append("choose"); log.refs.append($0) },
            onChooserControl: { log.events.append("control"); log.controls.append($0) },
            onOpenOriginal: { log.events.append("open"); log.refs.append($0) },
            onCardAction: { log.events.append("card"); log.ids.append($0) },
            onResultOpen: { log.events.append("resultOpen"); log.opens.append($0) },
            onResultDetails: { log.events.append("resultDetails") },
            onInteraction: interaction)
    }

    // MARK: Reachable text

    private static func words(_ items: [String?]) -> [String] { items.compactMap { $0 } }

    private static func readingText(_ reading: FieldHistoryReading10868) -> [String] {
        switch reading {
        case .observation(_, let figure, let provenance): return [figure, provenance]
        case .independent(let figure, let provenance): return [figure, provenance]
        case .absent(let reason): return [reason]
        }
    }

    /// Everything the shared history can show for this input.
    private static func historyText(_ h: FieldHistoryInput10868) -> [String] {
        var texts = words([h.title, h.caption, h.comparisonExplanation, h.summary, h.unboundReadingWords,
                           h.plotUnavailableWords, h.markKey.hollow, h.markKey.filled, h.probabilityRangeExplanation,
                           h.plotAbsence?.title, h.plotAbsence?.words, h.inspection?.caption, h.inspection?.note,
                           FieldHistoryGeometry10868.selectionWords(h)])
        texts += h.notes + h.guides.map { $0.label } + (h.yTicks + h.xTicks).flatMap { $0.lines }
        texts += FieldHistoryGeometry10868.actions(h).map { $0.label }
        switch h.readout {
        case .singleBefore(let label): texts.append(label)
        case .beforeAndRecorded(let first, let second), .beforeAndInspected(let first, let second): texts += [first, second]
        }
        for choice in h.inspection?.choices ?? [] { texts += choice.lines + [choice.spoken] }
        for selected in (h.inspection?.selections ?? [:]).values {
            switch selected {
            case .point(_, let spoken): texts.append(spoken)
            case .absent(let reason): texts.append(reason)
            }
        }
        for series in h.series {
            texts += words([series.name, series.absentWords, series.choose?.label])
            texts += readingText(series.before) + readingText(series.recorded)
            for slot in FieldHistoryGeometry10868.readoutSlots(series, in: h) {
                texts.append(slot.label)
                switch slot.display {
                case .figure(let figure, let provenance): texts += [figure, provenance]
                case .words(let reason): texts.append(reason)
                }
            }
        }
        return texts
    }

    private static func comparisonText(_ model: Chance) -> [String] {
        var texts = [model.input.name, model.input.meaning, model.input.copy.preTournamentUnavailable, model.spoken]
        for slot in model.slots { texts += [slot.label, slot.words, slot.detail] }
        if let result = model.result { texts += [model.input.copy.resultLabel, result] }
        return texts
    }

    private static func chipText(_ input: PokerChipCardInput10868, role: Role) -> [String] {
        let model = PokerChipCardModel10868(input)
        var texts = words([input.copy.eyebrow, input.copy.title, input.copy.shareKey, input.copy.chanceKey, input.copy.note,
                           input.copy.graphicLabel, input.scale.words])
        texts += model.ticks.map { $0.label }
        for bar in model.bars { texts += [model.rowSummary(bar), model.shareWords(bar), model.chanceWords(bar)] }
        if let selected = model.selected {
            texts += words([selected.name, model.figure(selected.share) ?? input.copy.shareUnavailable,
                            model.figure(selected.chance) ?? input.copy.chanceUnavailable, selected.chanceDate,
                            input.copy.measureNote])
            if let result = model.result(role: role) { texts += [input.copy.resultLabel, result] }
        }
        texts += [model.live(input.toggle, canAct: true), model.live(input.source, canAct: true)].compactMap { $0?.label }
        return texts
    }

    private static func countryText(_ input: PokerCountryCardInput10868, role: Role) -> [String] {
        let model = PokerCountryCardModel10868(input)
        var texts = words([input.copy.eyebrow, input.copy.title, input.copy.note, input.copy.entryLabel, model.barWords(),
                           model.summary(role: role)])
        texts += model.ticks.map { $0.label }
        if let reading = model.reading { texts.append(FieldChooserModel10868.spoken(reading)) }
        if let actual = model.actual(role: role) { texts += words([actual.label, actual.words, actual.detail]) }
        return texts
    }

    private static func resultText(_ input: HistoricalChanceInput10868) -> [String] {
        let leaf = HistoricalChanceModel10868(input)
        var texts = words([leaf.eyebrow, leaf.title, leaf.context, leaf.subjectName, input.copy.beforeKey,
                           input.copy.checkpointKey, input.copy.actualTitle, leaf.outcome])
        texts += leaf.sides.map { FieldMovementModel10868.spoken($0.endpoint) }
        if let actual = leaf.actual { texts.append(FieldMovementModel10868.spoken(actual)) }
        return texts
    }

    private static func chooserText(_ input: FieldChooserInput10868) -> [String] {
        var texts = words([input.featured.title, input.unavailableWords, input.selected?.words])
        for original in input.catalogue {
            texts += [original.name, original.browseStatus] + original.plan.readings.map { FieldChooserModel10868.spoken($0) }
        }
        return texts
    }

    /// Every original's Details and the held side's recorded history, as the shared leaves resolve them.
    private static func originalsText(_ originals: FieldEventPageOriginals10868) -> [String] {
        var texts = words([originals.heading, originals.context, originals.emptyWords])
        for original in originals.catalogue?.originals ?? [] {
            let held = Originals.Selection(scope: originals.catalogue?.scope ?? "", identity: original.identity)
            guard let content = Originals.content(catalogue: originals.catalogue, selection: held) else { continue }
            texts += [content.title, content.outcome]
            for reading in content.readings { texts += words([reading.label, reading.text, reading.provenance]) }
            if let result = content.result { texts += words([Originals.resultLabel, result.words, result.provenance]) }
            texts += content.about.flatMap { [$0.label, $0.value] }
            switch content.rules {
            case .verified(let kept): texts += kept
            case .unavailable(let reason): texts.append(reason)
            case .omitted: break
            }
        }
        if case .recorded(let shown)? = Originals.recorded(catalogue: originals.catalogue, selection: originals.selection,
                                                           context: originals.recorded, hasCallback: true) {
            texts.append(shown.availability)
            for reading in shown.content.readings { texts += words([reading.label, reading.text, reading.provenance]) }
            texts += words([shown.movement, shown.finish?.label, shown.finish?.words])
            texts += historyText(shown.history)
            texts += [shown.preview, shown.expand, shown.explore].compactMap { $0?.label }
        }
        return texts
    }

    /// Every text a reader can reach from this page in this role: the page,
    /// its readouts, compact and full-size history, mounted cards, stories,
    /// chooser, About, originals, sides and the admitted outcome reader.
    private static func reachable(_ input: PokerEventPageInput10868, originals: PokerEventPageOriginals10868? = nil,
                                  sides: PokerOriginalSides10868? = nil,
                                  outcome: PokerOutcomeReaderInput10868? = nil) -> [String] {
        let model = Model(input)
        let view = Screen(input: input, originals: originals, sides: sides, outcome: outcome)
        var texts = words([input.copy.eyebrow, input.copy.title, input.copy.context, input.copy.status, input.copy.aboutLabel,
                           input.copy.aboutHint, input.copy.storiesLabel, input.copy.storyUnavailable,
                           input.copy.allPropsLabel, input.reader.title, input.reader.state, input.stream.heading])
        if let comparison = model.comparison {
            texts += comparisonText(Chance(comparison, history: model.history(reader: false)))
        } else {
            texts.append(input.copy.comparisonUnavailable)
        }
        texts += historyText(model.history(reader: false)) + historyText(model.history(reader: true))
        if let chips = input.chips { texts += chipText(chips, role: input.role) }
        if let country = input.country { texts += countryText(country, role: input.role) }
        if let result = model.result { texts += resultText(result) }
        for story in input.stories where model.story(story.cardID) != nil { texts += words([story.reason]) }
        texts += input.stream.cards.filter { model.story($0.id) != nil }.map { $0.name }
        if let chooser = input.chooser { texts += chooserText(chooser) }
        if let about = model.about { texts += [about.title] + about.paragraphs }
        if let admitted = view.admittedOriginals {
            texts += originalsText(admitted)
            if let sides { texts += [sides.label] + sides.sides.flatMap { [$0.label, $0.meaning] } }
        } else if originals != nil {
            texts.append(input.copy.originalsUnavailable)
        }
        if let admitted = view.admittedOutcome {
            let full = Model.outcomeHistory(admitted)
            texts += comparisonText(Chance(admitted.comparison, history: full)) + historyText(full)
            texts += words([view.outcomeNote()])
        }
        return texts
    }

    /// Facts only an owner after the final table could know. Meaning-aware:
    /// "Winner from outside the USA" is a side's meaning, "USA" alone is the
    /// reported country; "20%" is a chance, "1st" a finish.
    private static let finalFacts = ["Reported finish", "Finished", "Actual winner", "Won the tournament", "Happened",
                                     "Didn’t happen", "Final standings", "result reported", "Result reported",
                                     "PokerNews", "ACTUAL RESULT"]
    private static let resultPatterns = [#"(?<![\w.])[1-9](st|nd|rd|th)\b"#, #"\$\s?\d"#, #"^USA$"#]
    private static let clockPattern = #"[A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d{2}:\d{2} [AP]M PT"#

    private static func isResult(_ text: String) -> Bool {
        finalFacts.contains { text.contains($0) }
            || resultPatterns.contains { text.range(of: $0, options: .regularExpression) != nil }
    }

    private static func clocks(in text: String) -> [String] {
        var found: [String] = []
        var rest = text.startIndex..<text.endIndex
        while let match = text.range(of: clockPattern, options: .regularExpression, range: rest) {
            found.append(String(text[match]))
            rest = match.upperBound..<text.endIndex
        }
        return found
    }

    /// Every trade clock at or after the scheduled final table, and the report time.
    private static let laterClocks: Set<String> = Set(
        markets.flatMap { $0.sides }.flatMap { $0.trades }.filter { $0.t >= scheduledFinalTable }.map { clockTime($0.t) }
            + [clockTime(resultReportAt)])

    private static func leaks(_ texts: [String], role: Role) -> [String] {
        guard role == .beforeFinalTable else { return [] }
        return texts.filter { text in isResult(text) || clocks(in: text).contains { laterClocks.contains($0) } }
    }

    // MARK: Payloads

    private enum Payload: Equatable {
        /// A result endpoint's exact original and position key.
        case open(FieldMovementOpen10868)
        /// An inspection choice's position key.
        case key(String)
        /// An exact original a card or the chooser hands back.
        case ref(Ref)
    }

    private static func payloads(_ input: PokerEventPageInput10868,
                                 outcome: PokerOutcomeReaderInput10868? = nil) -> [Payload] {
        let model = Model(input)
        let view = Screen(input: input, outcome: outcome)
        var found: [Payload] = []
        var histories = [model.history(reader: false)]
        if let admitted = view.admittedOutcome { histories.append(Model.outcomeHistory(admitted)) }
        for history in histories { found += (history.inspection?.choices ?? []).map { Payload.key($0.id) } }
        if let result = model.result {
            let leaf = HistoricalChanceModel10868(result)
            found += leaf.sides.compactMap { leaf.openAction($0, canOpen: true).map { Payload.open($0) } }
        }
        if let chips = input.chips {
            let leaf = PokerChipCardModel10868(chips)
            found += leaf.bars.compactMap { leaf.chooseRef($0, canChoose: true).map { Payload.ref($0) } }
        }
        if let country = input.country, let opened = PokerCountryCardModel10868(country).entryRef(canOpen: true) {
            found.append(.ref(opened))
        }
        if let chooser = input.chooser {
            found += FieldChooserModel10868(chooser).featuredRows.compactMap { row in row.resolution.original.map { Payload.ref($0.ref) } }
        }
        return found
    }

    /// A position key whose trade an owner before the final table could not hold.
    private static func late(_ key: String, role: Role) -> String? {
        guard role == .beforeFinalTable else { return nil }
        let parts = key.split(separator: ":").map(String.init)
        guard parts.count == 3, let market = markets.first(where: { $0.id == parts[0] }),
              let side = market.sides.first(where: { $0.label == parts[1] }), let index = Int(parts[2]),
              side.trades.indices.contains(index) else { return "\(key) is not a retained position" }
        return side.trades[index].t < scheduledFinalTable ? nil : "\(key) is after the final table"
    }

    private static func violations(_ found: [Payload], role: Role) -> [String] {
        found.compactMap { payload -> String? in
            switch payload {
            case .open(let opened):
                if opened.ref.scope != scope { return "foreign original \(opened.ref.marketID)" }
                return opened.observation.flatMap { late($0, role: role) }
            case .key(let key):
                return late(key, role: role)
            case .ref(let handed):
                return handed.scope == scope ? nil : "foreign original \(handed.marketID)"
            }
        }
    }

    // MARK: Retained arithmetic

    private struct SideFact: Equatable {
        let market: String
        let side: String
        let trades: Int
        let beforeTable: Int
        let sameSecondGroups: Int
        let identicalGroups: Int
    }

    private static func fact(_ market: Market, _ side: Side) -> SideFact {
        var seconds: [Int: Int] = [:]
        var prints: [String: Int] = [:]
        for trade in side.trades {
            seconds[trade.t, default: 0] += 1
            prints["\(trade.t) \(trade.text) \(trade.size)", default: 0] += 1
        }
        return SideFact(market: market.id, side: side.label, trades: side.trades.count,
                        beforeTable: side.trades.filter { $0.t < scheduledFinalTable }.count,
                        sameSecondGroups: seconds.values.filter { $0 > 1 }.count,
                        identicalGroups: prints.values.filter { $0 > 1 }.count)
    }

    /// The first two positions of `side` that share a second; with `identical`,
    /// that also share price and size (they differ only by transaction).
    private static func pair(_ side: Side, identical: Bool) -> (Int, Int)? {
        for first in side.trades.indices {
            for second in side.trades.indices where second > first && side.trades[second].t == side.trades[first].t {
                let a = side.trades[first], b = side.trades[second]
                if !identical || (a.text == b.text && a.size == b.size) { return (first, second) }
            }
        }
        return nil
    }


    // MARK: - The outcome reader's one role-matching outcome (P2)

    func testTheOutcomeReaderReadsOneRoleMatchingOutcomeForItsReadoutsHistoryNoteAndActions() {
        let side = Self.mizrachi.no
        let cases: [(Role, Role)] = [(.beforeFinalTable, .final), (.final, .beforeFinalTable),
                                     (.beforeFinalTable, .beforeFinalTable), (.final, .final)]
        for (pageRole, outcomeRole) in cases {
            let label = "\(pageRole) page, \(outcomeRole) outcome"
            let log = Log()
            let input = Self.parts(pageRole).input
            let outcome = Self.outcome(outcomeRole, Self.mizrachi, side)
            let originals = Self.bundle(pageRole, Self.mizrachi, side)
            let sides = Self.sides(Self.mizrachi)
            let reader = Self.screen(input, mode: .outcome, log: log, originals: originals, sides: sides, outcome: outcome)
            // The raw outcome carries every surface, so each nil below is the guard, not an empty input.
            XCTAssertNotNil(FieldEventPageModel10868.readable(outcome.note), label)
            XCTAssertNotNil(outcome.comparison.inspected, label)
            XCTAssertNotNil(outcome.history.inspection, label)
            let choice = outcome.history.inspection?.choices.first?.id ?? ""
            let position = outcome.history.domain.lower
            if pageRole == outcomeRole {
                XCTAssertEqual(reader.admittedOutcome, outcome, label)
                XCTAssertEqual(reader.outcomeComparisonContent()?.input, outcome.comparison, label)
                XCTAssertEqual(reader.outcomeComparisonContent()?.history, Model.outcomeHistory(outcome), label)
                XCTAssertEqual(reader.outcomeHistoryContent()?.input, Model.outcomeHistory(outcome), label)
                XCTAssertEqual(reader.outcomeNote(), outcome.note, label)
                // Full size: the exact callbacks with their exact values and no hold.
                reader.outcomeHistoryContent()?.onAction?("history.previous")
                reader.outcomeHistoryContent()?.onInspectionChoice?(choice)
                reader.outcomeHistoryContent()?.onPlotPosition?(position)
                XCTAssertEqual(log.events, ["outcomeAction", "outcomeChoice", "outcomePosition"], label)
                XCTAssertEqual(log.ids, ["history.previous", choice], label)
                XCTAssertEqual(log.positions, [position], label)
                // Its readouts are the held side's own, with its own figure.
                let model = Chance(outcome.comparison, history: Model.outcomeHistory(outcome))
                XCTAssertEqual(model.series?.id, Self.seriesID(Self.mizrachi, side), label)
                XCTAssertTrue(model.slots.contains { $0.figure != nil }, label)
                XCTAssertEqual(model.result == nil, pageRole == .beforeFinalTable, label)
            } else {
                XCTAssertNil(reader.admittedOutcome, label)
                XCTAssertNil(reader.outcomeComparisonContent(), label)
                XCTAssertNil(reader.outcomeHistoryContent(), label)
                XCTAssertNil(reader.outcomeNote(), label)
                XCTAssertEqual(log.events, [], label)
                XCTAssertNotNil(FieldEventPageModel10868.readable(input.copy.comparisonUnavailable), label)
            }
            // The held main, original and side identities stay exactly as the host gave them.
            XCTAssertEqual(reader.outcome, outcome, label)
            XCTAssertEqual(reader.originals?.originals.selection, Self.selection(Self.mizrachi, side), label)
            XCTAssertEqual(reader.sides, sides, label)
            XCTAssertEqual(reader.model.comparison, input.comparison, label)
            XCTAssertEqual(reader.model.comparison?.seriesID, Self.seriesID(Self.mizrachi, Self.mizrachi.yes), label)
        }
    }

    func testAMismatchedOutcomeReachesNoTextNoPayloadAndNoCallback() {
        let side = Self.mizrachi.no
        // Before the final table, a retained final outcome adds nothing a reader could reach.
        let before = Self.parts(.beforeFinalTable).input
        let finalOutcome = Self.outcome(.final, Self.mizrachi, side)
        let withFinal = Self.reachable(before, outcome: finalOutcome)
        XCTAssertEqual(Self.leaks(withFinal, role: .beforeFinalTable), [])
        XCTAssertEqual(withFinal, Self.reachable(before))
        XCTAssertEqual(Self.payloads(before, outcome: finalOutcome), Self.payloads(before))
        // Positive control: the same final outcome on a final page is reachable and leaks to a before reader.
        let final = Self.parts(.final).input
        let finalTexts = Self.reachable(final, outcome: finalOutcome)
        XCTAssertTrue(finalTexts.contains("Reported finish shown apart from every chance"))
        XCTAssertFalse(Self.leaks(finalTexts, role: .beforeFinalTable).isEmpty)
        XCTAssertGreaterThan(Self.payloads(final, outcome: finalOutcome).count, Self.payloads(final).count)
        // At the final, a retained before-table outcome adds no text and no position.
        let beforeOutcome = Self.outcome(.beforeFinalTable, Self.mizrachi, side)
        XCTAssertEqual(Self.reachable(final, outcome: beforeOutcome), Self.reachable(final))
        XCTAssertEqual(Self.payloads(final, outcome: beforeOutcome), Self.payloads(final))
        XCTAssertFalse(Self.reachable(final, outcome: beforeOutcome).contains("Each mark is one retained trade"))
        // The matching before outcome is reachable on the before page and still leak-free.
        let matching = Self.reachable(before, outcome: beforeOutcome)
        XCTAssertTrue(matching.contains("Each mark is one retained trade"))
        XCTAssertEqual(Self.leaks(matching, role: .beforeFinalTable), [])
        XCTAssertEqual(Self.violations(Self.payloads(before, outcome: beforeOutcome), role: .beforeFinalTable), [])
    }

    // MARK: - The originals' one role-matching bundle (P3)

    func testTheOriginalsReadOneRoleMatchingBundleForTheCatalogueDetailsHistoryAndSides() {
        let side = Self.mizrachi.no
        let sides = Self.sides(Self.mizrachi)
        let cases: [(Role, Role)] = [(.beforeFinalTable, .final), (.final, .beforeFinalTable),
                                     (.beforeFinalTable, .beforeFinalTable), (.final, .final)]
        for (pageRole, bundleRole) in cases {
            let label = "\(pageRole) page, \(bundleRole) originals"
            let input = Self.parts(pageRole).input
            let bundle = Self.bundle(bundleRole, Self.mizrachi, side)
            let raw = bundle.originals
            // The raw bundle is complete in its own role, so each refusal below is the guard, not an empty input.
            XCTAssertEqual(raw.catalogue?.originals.count, 26, label)
            XCTAssertNotNil(raw.recorded, label)
            XCTAssertNotNil(Originals.content(catalogue: raw.catalogue, selection: raw.selection), label)
            XCTAssertNotNil(Screen.sideSelection(sides.sides[1], in: raw, canSelect: true), label)
            for mode in [PokerEventPageMode10868.catalogue, .original] {
                let log = Log()
                let page = Self.screen(input, mode: mode, log: log, originals: bundle, sides: sides)
                let modeLabel = "\(label), \(mode)"
                if pageRole == bundleRole {
                    XCTAssertEqual(page.admittedOriginals?.selection, raw.selection, modeLabel)
                    XCTAssertEqual(page.catalogueContent()?.catalogue, raw.catalogue, modeLabel)
                    XCTAssertEqual(page.catalogueContent()?.selection, raw.selection, modeLabel)
                    XCTAssertEqual(page.originalDetailsContent()?.catalogue, raw.catalogue, modeLabel)
                    XCTAssertEqual(page.originalDetailsContent()?.selection, raw.selection, modeLabel)
                    XCTAssertEqual(page.originalDetailsContent()?.recorded, raw.recorded, modeLabel)
                    XCTAssertTrue(page.isHighlighted(sides.sides[1]), modeLabel)
                    XCTAssertFalse(page.isHighlighted(sides.sides[0]), modeLabel)
                    // Each action holds once, then hands back its exact value.
                    page.catalogueContent()?.onSelect?(Self.selection(Self.mizrachi, Self.mizrachi.yes))
                    let intent = Originals.HistoryIntent(selection: raw.selection!, entry: .expand, actionID: "original.expand")
                    page.originalDetailsContent()?.onHistory?(intent)
                    page.sideAction(sides.sides[0])?()
                    XCTAssertEqual(log.events, ["hold", "select", "hold", "history", "hold", "select"], modeLabel)
                    XCTAssertEqual(log.selections, [Self.selection(Self.mizrachi, Self.mizrachi.yes),
                                                    Self.selection(Self.mizrachi, Self.mizrachi.yes)], modeLabel)
                    XCTAssertEqual(log.histories, [intent], modeLabel)
                } else {
                    XCTAssertNil(page.admittedOriginals, modeLabel)
                    XCTAssertNil(page.catalogueContent(), modeLabel)
                    XCTAssertNil(page.originalDetailsContent(), modeLabel)
                    XCTAssertFalse(page.isHighlighted(sides.sides[1]), modeLabel)
                    XCTAssertFalse(page.isHighlighted(sides.sides[0]), modeLabel)
                    XCTAssertNil(page.sideAction(sides.sides[0]), modeLabel)
                    XCTAssertNil(page.sideAction(sides.sides[1]), modeLabel)
                    XCTAssertEqual(log.events, [], modeLabel)
                    XCTAssertNotNil(FieldEventPageModel10868.readable(input.copy.originalsUnavailable), modeLabel)
                }
                // The held bundle and its exact identity stay exactly as the host gave them.
                XCTAssertEqual(page.originals?.role, bundleRole, modeLabel)
                XCTAssertEqual(page.originals?.originals.selection, Self.selection(Self.mizrachi, side), modeLabel)
                XCTAssertEqual(page.sides, sides, modeLabel)
            }
        }
        // An unknown held original in the right role never borrows another: its Details resolve to nothing,
        // and only the sides still in the catalogue act.
        let omitted = Self.bundle(.final, Self.mizrachi, side,
                                  catalogue: Self.originalsCatalogue(.final, without: Self.identity(Self.mizrachi, side)))
        let page = Self.screen(Self.parts(.final).input, mode: .original, log: Log(), originals: omitted, sides: sides)
        XCTAssertNil(Originals.content(catalogue: page.originalDetailsContent()?.catalogue,
                                       selection: page.originalDetailsContent()?.selection))
        XCTAssertNil(page.sideAction(sides.sides[1]))
        XCTAssertNotNil(page.sideAction(sides.sides[0]))
    }

    func testAWrongRoleBundleReallyCarriesLaterFactsAndThePageReachesNoneOfThem() {
        let side = Self.mizrachi.no
        let sides = Self.sides(Self.mizrachi)
        // Positive control: the raw final bundle carries the later grade, finish and after-table history.
        let finalRaw = Self.originals(.final, Self.mizrachi, side)
        XCTAssertEqual(Originals.content(catalogue: finalRaw.catalogue, selection: finalRaw.selection)?.result?.words, "Didn’t happen")
        if case .recorded(let shown)? = Originals.recorded(catalogue: finalRaw.catalogue, selection: finalRaw.selection,
                                                           context: finalRaw.recorded, hasCallback: true) {
            XCTAssertEqual(shown.finish?.words, "1st")
            XCTAssertEqual(shown.content.readings.last?.text, "1%")
            XCTAssertTrue(shown.history.series[0].runs.contains { run in run.points.contains { $0.style == .filled } })
        } else {
            XCTFail("the final bundle's recorded history")
        }
        XCTAssertFalse(Self.leaks(Self.originalsText(finalRaw), role: .beforeFinalTable).isEmpty)
        // Through a before-table page it reaches no text, no side and no meaning.
        let before = Self.parts(.beforeFinalTable).input
        let through = Self.reachable(before, originals: Self.bundle(.final, Self.mizrachi, side), sides: sides)
        XCTAssertEqual(Self.leaks(through, role: .beforeFinalTable), [])
        XCTAssertTrue(through.contains("Original outcomes for this view are unavailable"))
        XCTAssertFalse(through.contains("Doesn’t win the tournament"))
        XCTAssertFalse(through.contains("All props"))
        // The matching before bundle is reachable on the same page and stays leak-free.
        let matching = Self.reachable(before, originals: Self.bundle(.beforeFinalTable, Self.mizrachi, side), sides: sides)
        XCTAssertTrue(matching.contains("Doesn’t win the tournament"))
        XCTAssertTrue(matching.contains("All props"))
        XCTAssertEqual(Self.leaks(matching, role: .beforeFinalTable), [])
        // A final page with a before-table bundle reaches none of it either.
        let final = Self.parts(.final).input
        let mixed = Self.reachable(final, originals: Self.bundle(.beforeFinalTable, Self.mizrachi, side), sides: sides)
        XCTAssertTrue(mixed.contains("Original outcomes for this view are unavailable"))
        XCTAssertFalse(mixed.contains("Doesn’t win the tournament"))
        XCTAssertFalse(mixed.contains("All props"))
        let finalMatching = Self.reachable(final, originals: Self.bundle(.final, Self.mizrachi, side), sides: sides)
        XCTAssertTrue(finalMatching.contains("Didn’t happen"))
        XCTAssertTrue(finalMatching.contains("Doesn’t win the tournament"))
    }

    // MARK: - Retained capture

    func testTheRetainedCaptureKeepsThirteenPropsTwentySixSidesAndEveryTradePosition() {
        XCTAssertEqual(Self.markets.count, 13)
        let sides = Self.markets.flatMap { $0.sides }
        XCTAssertEqual(sides.count, 26)
        XCTAssertEqual(sides.map { $0.trades.count }.reduce(0, +), 5329)
        XCTAssertEqual(Self.players.map { $0.name }, ["John Wasnock", "Michael Mizrachi", "Braxton Dunaway", "Kenny Hallaert",
                                                     "Leo Margets", "Luka Bojovic", "Adam Hendrix", "Daehyung Lee", "Jarod Minghini"])
        XCTAssertEqual(Self.placeholders.map { $0.name }, ["Player A", "Player B", "Other"])
        XCTAssertEqual(Self.winners.map { $0.kind }, Array(repeating: "winner", count: 12))
        XCTAssertEqual(Self.american.kind, "nationality")
        // Every side's counts, same-second groups and identical (t, p, size) prints, recomputed from the fixture.
        let facts = Self.markets.flatMap { market in market.sides.map { Self.fact(market, $0) } }
        let expected: [(String, Int, Int, Int, Int, Int, Int, Int, Int)] = [
            ("563320", 352, 161, 28, 17, 439, 283, 74, 20), ("563321", 355, 118, 7, 2, 499, 265, 65, 17),
            ("563322", 287, 167, 25, 14, 336, 206, 50, 17), ("563323", 263, 110, 10, 6, 414, 248, 56, 19),
            ("563324", 100, 66, 4, 1, 274, 244, 47, 17), ("563325", 151, 81, 3, 2, 353, 269, 67, 20),
            ("563326", 146, 110, 10, 4, 279, 253, 48, 20), ("563327", 186, 170, 22, 18, 264, 242, 46, 16),
            ("563328", 142, 125, 12, 7, 240, 217, 43, 14), ("563329", 0, 0, 0, 0, 0, 0, 0, 0),
            ("563330", 0, 0, 0, 0, 0, 0, 0, 0), ("563331", 0, 0, 0, 0, 0, 0, 0, 0),
            ("557372", 155, 108, 0, 0, 94, 77, 1, 0),
        ]
        XCTAssertEqual(facts, expected.flatMap { row in [
            SideFact(market: row.0, side: "Yes", trades: row.1, beforeTable: row.2, sameSecondGroups: row.3, identicalGroups: row.4),
            SideFact(market: row.0, side: "No", trades: row.5, beforeTable: row.6, sameSecondGroups: row.7, identicalGroups: row.8),
        ] })
        // Positions are capture order; clocks never run backwards; every trade is inside the report and qualified.
        for market in Self.markets {
            for side in market.sides {
                XCTAssertEqual(side.trades.map { $0.position }, Array(side.trades.indices), "\(market.id) \(side.label)")
                XCTAssertTrue(zip(side.trades, side.trades.dropFirst()).allSatisfy { $0.t <= $1.t }, market.id)
                XCTAssertTrue(side.trades.allSatisfy { $0.t <= Self.resultReportAt && $0.p > 0 && $0.p < 1 }, market.id)
                XCTAssertTrue(side.trades.allSatisfy { (Double($0.size) ?? 0) > 0 }, market.id)
            }
            XCTAssertNotEqual(market.yes.token, market.no.token, market.id)
        }
        // Every transaction and every token is its own: nothing deduplicated, nothing shared.
        XCTAssertEqual(Set(sides.flatMap { side in side.trades.map { $0.tx } }).count, 5329)
        XCTAssertEqual(Set(sides.map { $0.token }).count, 26)
        // Resolutions, transcribed standings, prizes and chips.
        XCTAssertEqual(Self.players.filter { $0.yes.resolved }.map { $0.name }, ["Michael Mizrachi"])
        XCTAssertTrue(Self.winners.allSatisfy { $0.yes.resolved != $0.no.resolved })
        XCTAssertTrue(Self.american.yes.resolved)
        XCTAssertFalse(Self.american.no.resolved)
        XCTAssertEqual(Self.players.compactMap { $0.finish }.sorted(), Array(1...9))
        XCTAssertEqual(Self.players.compactMap { $0.prize }.reduce(0, +), 31_050_000)
        XCTAssertEqual([Self.mizrachi.finish, Self.mizrachi.prize, Self.mizrachi.chips], [1, 10_000_000, 93_000_000])
        XCTAssertEqual([Self.wasnock.finish, Self.wasnock.prize, Self.wasnock.chips], [2, 6_000_000, 108_100_000])
        XCTAssertEqual(Self.totalChips, 584_400_000)
        XCTAssertTrue(Self.placeholders.allSatisfy { $0.chips == nil && $0.finish == nil && $0.prize == nil })
        XCTAssertTrue(Self.placeholders.allSatisfy { $0.yes.trades.isEmpty && $0.no.trades.isEmpty })
        // The capture names a scheduled restart only: no actual start, no tournament baseline.
        XCTAssertEqual(Self.scheduledFinalTable, 1_752_609_600)
        XCTAssertEqual(Self.resultReportAt, 1_752_706_740)
        XCTAssertNil(Self.retainedActualFinalTableStart)
        XCTAssertNil(Self.retainedTournamentBaseline)
        // The owner's before-table election: the last position strictly before the scheduled restart.
        let elected = Self.markets.flatMap { market in market.sides.compactMap { side in
            Self.baselineIndex(side).map { "\(market.id) \(side.label) \($0) \(side.trades[$0].t) \(side.trades[$0].text)" }
        } }
        XCTAssertEqual(elected, [
            "563320 Yes 160 1752609236 0.15", "563320 No 282 1752609368 0.85",
            "563321 Yes 117 1752609236 0.2", "563321 No 264 1752609242 0.8",
            "563322 Yes 166 1752609236 0.13", "563322 No 205 1752609242 0.87",
            "563323 Yes 109 1752609236 0.17", "563323 No 247 1752609242 0.83",
            "563324 Yes 65 1752609236 0.08", "563324 No 243 1752609242 0.92",
            "563325 Yes 80 1752609246 0.11", "563325 No 268 1752609242 0.91",
            "563326 Yes 109 1752609236 0.11", "563326 No 252 1752609238 0.89",
            "563327 Yes 169 1752609236 0.04", "563327 No 241 1752609242 0.96",
            "563328 Yes 124 1752609238 0.036", "563328 No 216 1752609242 0.964",
            "557372 Yes 107 1752603463 0.66", "557372 No 76 1752603469 0.34",
        ])
        // Wasnock's two before-table trades in the same second stay two; the later position is elected.
        XCTAssertEqual(Self.wasnock.yes.trades[159].t, Self.wasnock.yes.trades[160].t)
    }

    func testYesAndNoStayIndependentOriginalsAndNoSideIsAComplement() {
        let catalogue = Self.originalsCatalogue(.final)
        XCTAssertEqual(catalogue.originals.count, 26)
        XCTAssertEqual(Set(catalogue.originals.map { $0.identity }).count, 26)
        for market in Self.markets {
            let yes = Originals.content(catalogue: catalogue, selection: Self.selection(market, market.yes))
            let no = Originals.content(catalogue: catalogue, selection: Self.selection(market, market.no))
            XCTAssertNotNil(yes, market.id)
            XCTAssertNotNil(no, market.id)
            XCTAssertNotEqual(yes?.outcome, no?.outcome, market.id)
            XCTAssertEqual(Self.selection(market, market.yes).identity.side, market.yes.token)
        }
        // A No side shows its own before-table trade, never one minus the Yes trade.
        let yesBefore = Self.bojovic.yes.trades[Self.baselineIndex(Self.bojovic.yes)!]
        let noBefore = Self.bojovic.no.trades[Self.baselineIndex(Self.bojovic.no)!]
        XCTAssertGreaterThan(abs(yesBefore.p + noBefore.p - 1), 0.005)
        let noContent = Originals.content(catalogue: catalogue, selection: Self.selection(Self.bojovic, Self.bojovic.no))
        XCTAssertEqual(noContent?.readings.first?.text, "91%")
        XCTAssertNotEqual(noContent?.readings.first?.text, Self.percent(1 - yesBefore.p))
        // The champion's last No trade is its own, not the complement of the last Yes.
        let lastNo = Self.recordedHistory(.final, Self.mizrachi, Self.mizrachi.no).readings.last?.reading.figure
        XCTAssertEqual(lastNo, .value("1%"))
        XCTAssertNotEqual(lastNo, .value(Self.percent(1 - Self.mizrachi.yes.trades.last!.p)))
        // Meanings reach the reader through the shared Details: the country No is neutral.
        let countryNo = Originals.content(catalogue: catalogue, selection: Self.selection(Self.american, Self.american.no))
        XCTAssertEqual(countryNo?.outcome, "Winner from outside the USA")
        XCTAssertFalse((countryNo?.outcome ?? "").localizedCaseInsensitiveContains("not"))
        XCTAssertFalse((countryNo?.outcome ?? "").localizedCaseInsensitiveContains("lose"))
        XCTAssertEqual(Originals.content(catalogue: catalogue, selection: Self.selection(Self.mizrachi, Self.mizrachi.no))?.outcome,
                       "Doesn’t win the tournament")
        // Both sides act, each handing back its own exact selection.
        let page = Self.originals(.final, Self.american, Self.american.yes)
        let selections = Self.sides(Self.american).sides.map { Screen.sideSelection($0, in: page, canSelect: true) }
        XCTAssertEqual(selections, [Self.selection(Self.american, Self.american.yes), Self.selection(Self.american, Self.american.no)])
        XCTAssertNotEqual(selections[0], selections[1])
    }

    func testEveryTradeIsItsOwnMarkAndSameSecondOrIdenticalPrintsStaySeparatePositions() {
        for role in [Role.beforeFinalTable, .final] {
            let history = Self.history(role, Self.featured.map { ($0, $0.yes) }, inspect: nil)
            for market in Self.featured {
                guard let series = history.series.first(where: { $0.id == Self.seriesID(market, market.yes) }) else {
                    XCTFail(market.name)
                    continue
                }
                let visible = Self.visible(market.yes, role)
                XCTAssertEqual(FieldHistoryGeometry10868.lines(series, in: history), [], market.name)
                let marks = FieldHistoryGeometry10868.marks(series, in: history)
                XCTAssertEqual(marks.map { $0.id }, visible.map { Self.pointID(market, market.yes, $0.0) }, market.name)
                XCTAssertEqual(Set(marks.map { $0.id }).count, visible.count, market.name)
                XCTAssertEqual(marks.filter { $0.style == .hollow }.count,
                               visible.filter { $0.1.t < Self.scheduledFinalTable }.count, market.name)
                XCTAssertEqual(marks.filter { $0.style == .filled }.count,
                               role == .final ? visible.filter { $0.1.t >= Self.scheduledFinalTable }.count : 0, market.name)
                XCTAssertEqual(series.shape, Self.shape(market), market.name)
            }
            // Stable identity shapes in either role: circle, triangle, diamond.
            XCTAssertEqual(history.series.map { $0.shape }, [.circle, .triangle, .diamond])
        }
        // Two prints in one second, and two identical prints, stay two marks with two ids.
        let side = Self.mizrachi.yes
        let final = Self.history(.final, [(Self.mizrachi, side)], inspect: nil)
        let marks = FieldHistoryGeometry10868.marks(final.series[0], in: final)
        guard let sameSecond = Self.pair(side, identical: false), let identical = Self.pair(side, identical: true) else {
            return XCTFail("the capture's same-second and identical prints")
        }
        for (first, second) in [sameSecond, identical] {
            XCTAssertEqual(side.trades[first].t, side.trades[second].t)
            XCTAssertNotEqual(side.trades[first].tx, side.trades[second].tx)
            XCTAssertEqual(marks[first].x, marks[second].x)
            XCTAssertNotEqual(marks[first].id, marks[second].id)
            XCTAssertNotNil(FieldHistoryGeometry10868.uniquePoint(marks[first].id, in: final.series[0]))
            XCTAssertNotNil(FieldHistoryGeometry10868.uniquePoint(marks[second].id, in: final.series[0]))
        }
        XCTAssertEqual(side.trades[identical.0].text, side.trades[identical.1].text)
        XCTAssertEqual(side.trades[identical.0].size, side.trades[identical.1].size)
        XCTAssertEqual(marks[identical.0].probability, marks[identical.1].probability)
        // The inspection ring sits on exactly the inspected position, in the player's own shape.
        let before = Self.baselineIndex(side)!
        let inspected = Self.history(.final, Self.featured.map { ($0, $0.yes) }, inspect: before)
        let ringed = inspected.series[0]
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedPoint(ringed, in: inspected)?.id, Self.pointID(Self.mizrachi, side, before))
        XCTAssertEqual(FieldHistoryGeometry10868.inspectionRingShape(ringed, in: inspected), .circle)
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(inspected.series[1], in: inspected))
        // The key below the chart: each featured player's own before-table chance and its own clock.
        for series in inspected.series {
            let market = Self.featured.first(where: { Self.seriesID($0, $0.yes) == series.id })!
            let trade = market.yes.trades[Self.baselineIndex(market.yes)!]
            XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(series, in: inspected), [
                FieldHistoryReadoutSlot10868(label: "Before final table", display: .figure(Self.percent(trade.p), provenance: Self.clock(trade.t))),
            ])
        }
        XCTAssertEqual(FieldHistoryGeometry10868.blocksBelowPlot(inspected), [.selectionWords, .key])
    }

    // MARK: - Readouts

    func testBeforeTheFinalTableTheReadoutIsTheInspectedEarlierTradeAndNeverPreTournament() {
        let side = Self.mizrachi.yes
        let input = Self.parts(.beforeFinalTable).input
        let page = Model(input)
        guard let comparison = page.comparison else { return XCTFail("before-table readouts") }
        let model = Chance(comparison, history: page.history(reader: false))
        let before = Self.baselineIndex(side)!
        let trade = side.trades[before]
        XCTAssertEqual(model.slots, [PokerChanceSlot10868(label: "Inspected before final table", figure: "20%", words: "20%",
                                                          detail: Self.clock(trade.t), pointID: Self.pointID(Self.mizrachi, side, before))])
        XCTAssertNil(model.result)
        XCTAssertTrue(model.spoken.hasSuffix("Pre-tournament chance unavailable"))
        // Every earlier position: its own figure and its own date, never relabelled pre-tournament.
        for index in [0, 5, 60, before] {
            let parts = Self.parts(.beforeFinalTable, inspect: .at(index))
            let slots = Chance(parts.comparison, history: parts.history).slots
            XCTAssertEqual(slots.map { $0.pointID }, [Self.pointID(Self.mizrachi, side, index)], "\(index)")
            XCTAssertEqual(slots.map { $0.detail }, [Self.clock(side.trades[index].t)], "\(index)")
            XCTAssertEqual(slots.map { $0.figure }, [Self.percent(side.trades[index].p)], "\(index)")
            XCTAssertFalse(slots.contains { $0.label.localizedCaseInsensitiveContains("tournament") }, "\(index)")
        }
        // No input can supply a pre-tournament chance: the words stay in both roles.
        let final = Self.parts(.final)
        XCTAssertTrue(Chance(final.comparison, history: final.history).spoken.contains("Pre-tournament chance unavailable"))
        XCTAssertEqual(input.copy.status, "Before the final table")
        // A filled (after-table) trade under the before role is never relabelled before-table.
        let later = side.trades.count - 1
        let rogueHistory = Self.history(.final, [(Self.mizrachi, side)], inspect: later)
        let rogue = Chance(Self.comparison(.beforeFinalTable, Self.mizrachi, side, inspect: later), history: rogueHistory)
        let none: [String?] = [nil]
        XCTAssertEqual(rogue.slots.map { $0.figure }, none)
        XCTAssertEqual(rogue.slots.map { $0.words }, ["No trade"])
        // Positive control: the same trade does show at the final.
        let finalRogue = Chance(Self.comparison(.final, Self.mizrachi, side, inspect: later), history: rogueHistory)
        XCTAssertEqual(finalRogue.slots.last?.figure, "99.7%")
        // Readouts whose role is not the page's are withheld whole, never coerced.
        var mismatched = Self.parts(.beforeFinalTable)
        mismatched.comparison = Self.comparison(.final, Self.mizrachi, side, inspect: before)
        XCTAssertNil(Model(mismatched.input).comparison)
        XCTAssertNil(Screen(input: mismatched.input).comparisonContent(reader: false))
    }

    func testAtTheFinalEachReadoutKeepsItsOwnDateAndOnlyTheSameExactPositionCollapses() {
        let side = Self.mizrachi.yes
        let before = Self.baselineIndex(side)!
        let last = side.trades.count - 1
        func slots(_ inspect: Inspect) -> [PokerChanceSlot10868] {
            let parts = Self.parts(.final, inspect: inspect)
            return Chance(parts.comparison, history: parts.history).slots
        }
        let baseline = PokerChanceSlot10868(label: "Before final table", figure: "20%", words: "20%",
                                            detail: Self.clock(side.trades[before].t), pointID: Self.pointID(Self.mizrachi, side, before))
        // A later recorded trade: two equal slots, each with its own date.
        XCTAssertEqual(slots(.at(last)), [baseline, PokerChanceSlot10868(
            label: "Recorded chance", figure: "99.7%", words: "99.7%", detail: Self.clock(side.trades[last].t),
            pointID: Self.pointID(Self.mizrachi, side, last))])
        // The same exact position collapses into one slot.
        XCTAssertEqual(slots(.at(before)), [PokerChanceSlot10868(
            label: "Before final table · selected trade", figure: "20%", words: "20%",
            detail: Self.clock(side.trades[before].t), pointID: Self.pointID(Self.mizrachi, side, before))])
        // An equal value at another, earlier position stays two slots with two dates.
        guard let equal = side.trades.indices.first(where: { $0 != before && side.trades[$0].p == side.trades[before].p }) else {
            return XCTFail("an earlier trade at the before-table value")
        }
        XCTAssertEqual(equal, 5)
        let pair = slots(.at(equal))
        XCTAssertEqual(pair.count, 2)
        XCTAssertEqual(pair.map { $0.figure }, ["20%", "20%"])
        XCTAssertEqual(pair.map { $0.label }, ["Before final table", "Inspected earlier trade"])
        XCTAssertNotEqual(pair[0].detail, pair[1].detail)
        XCTAssertNotEqual(pair[0].pointID, pair[1].pointID)
        // Result words stay apart from every chance.
        let parts = Self.parts(.final)
        let model = Chance(parts.comparison, history: parts.history)
        XCTAssertEqual(model.result, "Finished 1st")
        XCTAssertFalse(model.slots.contains { $0.words.contains("1st") || $0.detail.contains("1st") || $0.label.contains("Finished") })
    }

    func testAMissingForeignDuplicateOrChangedInspectionIsUnavailableNeverTheLatestOrANeighbour() {
        let side = Self.mizrachi.yes
        let last = side.trades.count - 1
        let before = Self.baselineIndex(side)!
        let base = Self.history(.final, Self.featured.map { ($0, $0.yes) }, inspect: last)
        let comparison = Self.comparison(.final, Self.mizrachi, side, inspect: last)
        func inspected(_ history: FieldHistoryInput10868, _ input: PokerChanceComparisonInput10868? = nil) -> PokerChanceSlot10868? {
            Chance(input ?? comparison, history: history).slots.last
        }
        func replacing(inspected reading: PokerChanceReading10868?,
                       baseline: PokerChanceReading10868? = nil) -> PokerChanceComparisonInput10868 {
            PokerChanceComparisonInput10868(role: .final, seriesID: comparison.seriesID, name: comparison.name,
                                            meaning: comparison.meaning, baseline: baseline ?? comparison.baseline,
                                            inspected: reading, result: comparison.result, copy: comparison.copy)
        }
        // Positive control: the intact owner shows the recorded trade.
        XCTAssertEqual(inspected(base)?.figure, "99.7%")
        let unavailable = PokerChanceSlot10868(label: "Recorded chance", figure: nil, words: "No trade",
                                               detail: "No retained trade for this outcome", pointID: nil)
        // No inspection at all.
        XCTAssertEqual(inspected(Self.rebuilt(base, inspection: .some(nil))), unavailable)
        // The ring sits on another player's trade.
        let other = Self.wasnock.yes
        let foreignRing = FieldHistoryInspection10868(
            x: Double(other.trades[0].t), caption: "Inspected trade",
            selections: [Self.seriesID(Self.wasnock, other): .point(id: Self.pointID(Self.wasnock, other, 0), spoken: "16%")],
            choices: [], choicePresentation: .slider(label: "Inspected trade"), note: nil)
        XCTAssertEqual(inspected(Self.rebuilt(base, inspection: foreignRing)), unavailable)
        // The reading names another player's position.
        XCTAssertEqual(inspected(base, replacing(inspected: Self.reading(Self.wasnock, other, 0))), unavailable)
        // The inspected position appears twice in the subject's series.
        let subject = base.series[0]
        let duplicated = Self.reseries(subject, runs: subject.runs + [subject.runs[last]])
        XCTAssertEqual(inspected(Self.rebuilt(base, series: [duplicated] + Array(base.series.dropFirst()))), unavailable)
        // A changed raw value behind the same figure, and a reading without its own date.
        let changed = PokerChanceReading10868(pointID: Self.pointID(Self.mizrachi, side, last), probability: 0.996,
                                              figure: "99.7%", date: Self.clock(side.trades[last].t))
        XCTAssertEqual(inspected(base, replacing(inspected: changed)), unavailable)
        let undated = PokerChanceReading10868(pointID: Self.pointID(Self.mizrachi, side, last), probability: side.trades[last].p,
                                              figure: "99.7%", date: " ")
        XCTAssertEqual(inspected(base, replacing(inspected: undated)), unavailable)
        // The ring and the reading name two different positions: never the neighbour.
        XCTAssertEqual(inspected(Self.history(.final, Self.featured.map { ($0, $0.yes) }, inspect: last - 1)), unavailable)
        // Two series share the subject's id: neither slot borrows either.
        let twins = Self.rebuilt(base, series: [subject, Self.reseries(base.series[1], id: subject.id)])
        let both = Chance(comparison, history: twins).slots
        XCTAssertEqual(both.map { $0.figure }, [String?]([nil, nil]))
        XCTAssertEqual(both.map { $0.words }, ["Unavailable", "No trade"])
        // A before-table reading on a filled position is never relabelled before-table.
        let filled = Chance(replacing(inspected: Self.reading(Self.mizrachi, side, before),
                                      baseline: Self.reading(Self.mizrachi, side, last)),
                            history: Self.history(.final, Self.featured.map { ($0, $0.yes) }, inspect: before))
        XCTAssertEqual(filled.slots.first, PokerChanceSlot10868(label: "Before final table", figure: nil, words: "Unavailable",
                                                                detail: "No earlier captured trade", pointID: nil))
        XCTAssertEqual(filled.slots.last?.figure, "20%")
        // None of these ever shows the latest trade.
        for history in [Self.rebuilt(base, inspection: .some(nil)), Self.rebuilt(base, inspection: foreignRing)] {
            XCTAssertFalse(Chance(comparison, history: history).slots.dropFirst().contains { $0.words == "99.7%" })
        }
    }

    func testStandingsPrizesAndTheCountryResultAppearOnlyInTheFinalRoleApartFromEveryChance() {
        // A rogue before-table owner passes every final-only field; the page withholds each.
        let rogue = Self.parts(.beforeFinalTable, rogue: true).input
        let before = Model(rogue)
        XCTAssertNotNil(rogue.result)
        XCTAssertNil(before.result)
        XCTAssertFalse(before.isMounted(.result))
        XCTAssertNil(before.story("result"))
        XCTAssertNotNil(rogue.comparison.result)
        XCTAssertNil(Chance(rogue.comparison, history: rogue.history).result)
        XCTAssertNotNil(rogue.chips?.selected?.result)
        XCTAssertNil(rogue.chips.flatMap { PokerChipCardModel10868($0).result(role: .beforeFinalTable) })
        XCTAssertNotNil(rogue.country?.actual)
        XCTAssertNil(rogue.country.flatMap { PokerCountryCardModel10868($0).actual(role: .beforeFinalTable) })
        XCTAssertEqual(Self.leaks(Self.reachable(rogue), role: .beforeFinalTable), [])
        // The final role shows each, apart from every chance.
        let input = Self.parts(.final).input
        let final = Model(input)
        XCTAssertEqual(final.result, input.result)
        XCTAssertEqual(Chance(input.comparison, history: input.history).result, "Finished 1st")
        XCTAssertEqual(input.chips.flatMap { PokerChipCardModel10868($0).result(role: .final) }, "1st · $10,000,000")
        XCTAssertEqual(input.country.flatMap { PokerCountryCardModel10868($0).actual(role: .final) },
                       PokerCountryActual10868(label: "Actual winner", words: "USA", detail: "Michael Mizrachi"))
        guard let result = final.result else { return XCTFail("final chance-to-result card") }
        let card = HistoricalChanceModel10868(result)
        XCTAssertTrue(card.isShown)
        XCTAssertEqual(card.actual, .reading(FieldChooserReading10868(label: "Reported finish",
                                                                      value: .recorded(text: "1st", detail: "PokerNews report"))))
        XCTAssertEqual(card.outcome, "Won the tournament")
        let fractions: [Double?] = [0.2, 0.997]
        XCTAssertEqual(card.sides.map { $0.chance.fraction }, fractions)
        XCTAssertFalse(card.sides.contains { FieldMovementModel10868.spoken($0.endpoint).contains("1st") })
        // A final page whose card is not in its own final phase mounts none.
        var notFinal = Self.parts(.final)
        notFinal.result = Self.result(phase: .during)
        XCTAssertNil(Model(notFinal.input).result)
        XCTAssertNil(Model(notFinal.input).story("result"))
        // An unreported country at the final keeps the owner's unknown words — never a loss, never blank.
        let unknown = PokerCountryCardModel10868(Self.country(actual: nil))
        XCTAssertEqual(unknown.actual(role: .final),
                       PokerCountryActual10868(label: "Actual winner", words: "Winner’s country not reported", detail: nil))
        let blank = PokerCountryCardModel10868(Self.country(actual: PokerCountryActual10868(label: "Actual winner", words: " ", detail: nil)))
        XCTAssertEqual(blank.actual(role: .final)?.words, "Winner’s country not reported")
        XCTAssertNil(unknown.actual(role: .beforeFinalTable))
    }

    // MARK: - Chip share against win chance

    func testTheChipCardDrawsTheHostsShareBesideTheSeparateWinChanceOnOneScaleAndNeverDivides() {
        let input = Self.chips(.beforeFinalTable)
        let model = PokerChipCardModel10868(input)
        let bars = model.bars
        XCTAssertEqual(bars.map { $0.resolution.original?.name }, Self.players.map { Optional($0.name) })
        for (bar, market) in zip(bars, Self.players) {
            guard let share = Self.share(market), let chance = Self.winChance(market) else { XCTFail(market.name); continue }
            XCTAssertEqual(bar.share, .value(probability: share.value, fraction: share.value / 0.4), market.name)
            XCTAssertEqual(bar.chance, .value(probability: chance.value, fraction: chance.value / 0.4), market.name)
            XCTAssertEqual(model.shareWords(bar), share.text, market.name)
            XCTAssertEqual(model.chanceWords(bar), chance.text, market.name)
            XCTAssertEqual(model.rowSummary(bar),
                           "\(market.name). Share of chips: \(share.text). Win chance before final table: \(chance.text)")
        }
        // The chip leader is not the chance leader: two measures, never one read as the other.
        XCTAssertEqual(model.shareWords(bars[0]), "18.5%")
        XCTAssertEqual(model.chanceWords(bars[0]), "15%")
        XCTAssertEqual(model.shareWords(bars[1]), "15.9%")
        XCTAssertEqual(model.chanceWords(bars[1]), "20%")
        XCTAssertNotEqual(input.copy.shareKey, input.copy.chanceKey)
        // The view never divides chip counts: a host share unrelated to the counts is drawn exactly.
        var rows = input.rows
        rows[0] = PokerChipRow10868(ref: rows[0].ref, label: rows[0].label,
                                    share: PokerChipMeasure10868(value: 0.05, text: "5.0%"), chance: rows[0].chance)
        let owned = PokerChipCardModel10868(Self.chips(input, rows: rows))
        XCTAssertEqual(owned.bars[0].share, .value(probability: 0.05, fraction: 0.05 / 0.4))
        XCTAssertEqual(owned.shareWords(owned.bars[0]), "5.0%")
        // The host's scale: a narrower ceiling moves every bar, and a value above it is off scale, not clamped.
        let narrow = FieldOutlookScale10868(ceiling: 0.16, ticks: [FieldOutlookTick10868(probability: 0.16, label: "16%")],
                                            words: "0–16%")
        let scaled = PokerChipCardModel10868(Self.chips(input, scale: narrow))
        XCTAssertEqual(scaled.bars[0].chance, .value(probability: 0.15, fraction: 0.15 / 0.16))
        XCTAssertEqual(scaled.bars[1].chance, .offScale)
        XCTAssertEqual(scaled.chanceWords(scaled.bars[1]), "20% · Above this scale")
        XCTAssertEqual(scaled.bars[0].share, .offScale)
        // Partial and missing rows keep their own words; unknown is never a zero bar.
        let partial = [
            PokerChipRow10868(ref: rows[0].ref, label: "John Wasnock", share: nil, chance: rows[0].chance),
            PokerChipRow10868(ref: rows[1].ref, label: "Michael Mizrachi", share: input.rows[1].share, chance: nil),
            Self.chipRow(Self.placeholders[0]),
            Self.chipRow(Self.dunaway, scope: "constructed:other"),
            Self.chipRow(Self.bojovic), Self.chipRow(Self.bojovic),
        ]
        let missing = PokerChipCardModel10868(Self.chips(input, rows: partial))
        let shown = missing.bars
        XCTAssertEqual(shown[0].share, .unavailable)
        XCTAssertEqual(missing.shareWords(shown[0]), "Chip count unavailable")
        XCTAssertEqual(missing.chanceWords(shown[0]), "15%")
        XCTAssertEqual(shown[1].chance, .unavailable)
        XCTAssertEqual(missing.chanceWords(shown[1]), "No earlier captured trade")
        XCTAssertNotNil(shown[2].resolution.original)
        XCTAssertEqual([shown[2].share, shown[2].chance], [.unavailable, .unavailable])
        XCTAssertNil(shown[3].resolution.original)
        XCTAssertEqual(missing.rowSummary(shown[3]), "Braxton Dunaway. Player unavailable in this update")
        XCTAssertEqual(shown[4].resolution, .unavailable)
        XCTAssertEqual(shown[5].resolution, .unavailable)
        XCTAssertFalse(shown.contains { $0.share == .value(probability: 0, fraction: 0) || $0.chance == .value(probability: 0, fraction: 0) })
        // A genuine zero is a zero mark, not a fill; unknown draws nothing.
        let zero = PokerChipCardModel10868.barPlan(share: 0, chance: nil, ticks: [], in: CGSize(width: 200, height: 22),
                                                   barHeight: 9, gap: 4, lineWidth: 1.5)
        XCTAssertNil(zero?.share)
        XCTAssertNotNil(zero?.shareZero)
        XCTAssertNil(zero?.chance)
        XCTAssertNil(zero?.chanceZero)
        // Both bars share one zero and one span on the same common axis as the ticks.
        guard let plan = PokerChipCardModel10868.barPlan(share: 0.5, chance: 0.5, ticks: [0.25, 0.5, 0.75, 1],
                                                         in: CGSize(width: 203, height: 22), barHeight: 9, gap: 4, lineWidth: 1.5),
              let shareBar = plan.share, let chanceBounds = plan.chanceBounds, let outline = plan.chance
        else { return XCTFail("bar plan") }
        XCTAssertEqual(shareBar.minX, chanceBounds.minX)
        XCTAssertEqual(shareBar.maxX, chanceBounds.maxX)
        XCTAssertEqual(plan.tickXs.first, shareBar.minX)
        XCTAssertEqual(plan.tickXs.count, 5)
        XCTAssertEqual(chanceBounds.minY, 13)
        XCTAssertTrue(chanceBounds.contains(outline))
        // The selected player's two measures, final-only result apart.
        XCTAssertEqual(model.selected?.ref, Self.ref(Self.mizrachi, Self.mizrachi.yes))
        XCTAssertEqual(model.figure(model.selected?.share), "15.9%")
        XCTAssertEqual(model.figure(model.selected?.chance), "20%")
        XCTAssertTrue(model.isSelected(bars[1]))
        XCTAssertFalse(model.isSelected(bars[0]))
        XCTAssertNil(model.result(role: .final))
        XCTAssertEqual(PokerChipCardModel10868(Self.chips(.final)).result(role: .final), "1st · $10,000,000")
        // The owner's two actions: live only with a callback and distinct ids.
        XCTAssertEqual(model.live(input.toggle, canAct: true)?.id, "chips.leading")
        XCTAssertEqual(model.live(input.source, canAct: true)?.id, "chips.source")
        XCTAssertNil(model.live(input.toggle, canAct: false))
        let clash = PokerChipCardModel10868(Self.chips(input, toggle: input.source))
        XCTAssertNil(clash.live(clash.input.toggle, canAct: true))
        XCTAssertNil(clash.live(clash.input.source, canAct: true))
    }

    func testTheCountryCardKeepsTheYesChanceWithItsOwnDateAndOpensTheOriginalOutcomes() {
        let input = Self.country(actual: Self.countryActual)
        let model = PokerCountryCardModel10868(input)
        let side = Self.american.yes
        let trade = side.trades[Self.baselineIndex(side)!]
        XCTAssertEqual(model.reading, FieldChooserReading10868(label: "Before final table · Yes",
                                                               value: .recorded(text: "66%", detail: Self.clock(trade.t))))
        XCTAssertEqual(model.chance, .value(probability: trade.p, fraction: trade.p))
        XCTAssertNil(model.barWords())
        XCTAssertEqual(model.entryRef(canOpen: true), Self.ref(Self.american, side))
        XCTAssertNil(model.entryRef(canOpen: false))
        var opened: [Ref] = []
        PokerCountryCardPresentation10868(input: input, role: .final, onOpenOriginal: { opened.append($0) }).open()
        PokerCountryCardPresentation10868(input: input, role: .final).open()
        XCTAssertEqual(opened, [Self.ref(Self.american, side)])
        // A foreign reference reads nothing and opens nothing.
        let foreign = PokerCountryCardModel10868(Self.country(actual: nil, scope: "constructed:other"))
        XCTAssertNil(foreign.reading)
        XCTAssertEqual(foreign.chance, .unavailable)
        XCTAssertNil(foreign.entryRef(canOpen: true))
        XCTAssertTrue(foreign.summary(role: .final).contains("Country prop unavailable in this update"))
        // The owner's absence words stay as they are; no bar is drawn for them.
        let absent = PokerCountryCardModel10868(Self.country(actual: nil, reading: FieldChooserReading10868(
            label: "Before final table · Yes", value: .missing("No earlier captured trade"))))
        XCTAssertEqual(absent.chance, .unavailable)
        XCTAssertEqual(absent.barWords(), "Not drawn on this scale")
        XCTAssertTrue(absent.summary(role: .beforeFinalTable).contains("No earlier captured trade"))
        // The entry opens both independent outcomes through the shared Details.
        let originals = Self.originals(.final, Self.american, side)
        let sides = Self.sides(Self.american).sides
        XCTAssertEqual(sides.map { $0.meaning }, ["American winner", "Winner from outside the USA"])
        XCTAssertEqual(sides.compactMap { Screen.sideSelection($0, in: originals, canSelect: true) }.count, 2)
        XCTAssertNil(Screen.sideSelection(sides[1], in: originals, canSelect: false))
    }

    // MARK: - Holds, the stream's interaction and passive reads

    func testEachPageActionHoldsOnceStreamCardsUseTheStreamsInteractionAndReadersHoldNothing() {
        let log = Log()
        let input = Self.parts(.final).input
        let side = Self.mizrachi.no
        let originals = Self.bundle(.final, Self.mizrachi, Self.mizrachi.yes)
        let sides = Self.sides(Self.mizrachi)
        let outcome = Self.outcome(.final, Self.mizrachi, side)
        let page = Self.screen(input, log: log, originals: originals, sides: sides, outcome: outcome)
        // Building and reading the page calls nothing.
        _ = (page.model, page.comparisonContent(reader: false), page.historyContent(reader: false), page.chipsContent(),
             page.countryContent(), page.resultContent(), page.chooserContent(), page.catalogueContent(),
             page.originalDetailsContent(), page.outcomeComparisonContent(), page.outcomeHistoryContent(),
             page.aboutContent(), page.admittedOutcome, page.outcomeNote())
        XCTAssertEqual(log.events, [])
        func expect(_ events: [String], _ line: UInt = #line, _ act: () -> Void) {
            log.events = []
            act()
            XCTAssertEqual(log.events, events, line: line)
        }
        let choice = input.history.inspection?.choices.first?.id ?? ""
        let position = Double(Self.scheduledFinalTable)
        let mizrachiRef = Self.ref(Self.mizrachi, Self.mizrachi.yes)
        // Page, chooser, catalogue, Details and side actions: exactly one hold, then the exact value.
        expect(["hold", "about"]) { page.openPageAbout() }
        expect(["hold", "allProps"]) { page.openAllProps() }
        expect(["hold", "historyAction"]) { page.historyContent(reader: false).onAction?("history.expand") }
        expect(["hold", "historyChoice"]) { page.historyContent(reader: false).onInspectionChoice?(choice) }
        expect(["hold", "historyPosition"]) { page.historyContent(reader: false).onPlotPosition?(position) }
        expect(["hold", "choose"]) { page.chooserContent()?.onChoose?(mizrachiRef) }
        expect(["hold", "control"]) { page.chooserContent()?.onControl?(.toggleMore(id: "more")) }
        expect(["hold", "select"]) { page.catalogueContent()?.onSelect?(Self.selection(Self.mizrachi, side)) }
        let intent = Originals.HistoryIntent(selection: Self.selection(Self.mizrachi, Self.mizrachi.yes), entry: .explore,
                                             actionID: "original.explore")
        expect(["hold", "history"]) { page.originalDetailsContent()?.onHistory?(intent) }
        expect(["hold", "select"]) { page.sideAction(sides.sides[1])?() }
        XCTAssertEqual(log.ids, ["history.expand", choice])
        XCTAssertEqual(log.positions, [position])
        XCTAssertEqual(log.refs, [mizrachiRef])
        XCTAssertEqual(log.controls, [.toggleMore(id: "more")])
        XCTAssertEqual(log.selections, [Self.selection(Self.mizrachi, side), Self.selection(Self.mizrachi, side)])
        XCTAssertEqual(log.histories, [intent])
        // Stream cards: the stream's own interaction for that card, then the exact value; no page hold.
        let card = StoryStreamPresentation10868.CardRef(scope: Self.storyScope, id: "chips")
        let resolved = input.stream.resolve(reduceMotion: false, actionable: true)
        let intents = input.stream.activationIntents(for: card, resolved: resolved)
        XCTAssertEqual(intents, [.interaction(scope: Self.storyScope, card: card)])
        let activation = StoryStreamCardActivation10868(card: card, intents: intents, send: {
            log.events.append("interaction")
            log.stream.append($0)
        })
        log.refs = []
        log.ids = []
        log.opens = []
        expect(["interaction", "choose"]) { page.chipsContent(activation: activation)?.onChoose?(mizrachiRef) }
        expect(["interaction", "card"]) { page.chipsContent(activation: activation)?.perform(input.chips?.toggle) }
        expect(["interaction", "open"]) { page.countryContent(activation: activation)?.open() }
        let open = FieldMovementOpen10868(ref: mizrachiRef, observation: Self.pointID(Self.mizrachi, Self.mizrachi.yes, 117))
        expect(["interaction", "resultOpen"]) { page.resultContent(activation: activation)?.onOpen?(open) }
        expect(["interaction", "resultDetails"]) { page.resultContent(activation: activation)?.onDetails?() }
        XCTAssertNil(page.resultContent(activation: activation)?.onExpand)
        XCTAssertEqual(log.refs, [mizrachiRef, Self.ref(Self.american, Self.american.yes)])
        XCTAssertEqual(log.ids, ["chips.leading"])
        XCTAssertEqual(log.opens, [open])
        XCTAssertEqual(log.stream.count, 5)
        XCTAssertTrue(log.stream.allSatisfy { $0 == .interaction(scope: Self.storyScope, card: card) })
        // Full size: the exact callbacks, no hold inside an already-held reader.
        let reader = Self.screen(input, mode: .reader(.chips), log: log, originals: originals, sides: sides, outcome: outcome)
        expect(["choose"]) { reader.chipsContent()?.onChoose?(mizrachiRef) }
        expect(["open"]) { reader.countryContent()?.open() }
        expect(["resultDetails"]) { reader.resultContent()?.onDetails?() }
        expect(["historyAction"]) { reader.historyContent(reader: true).onAction?("history.previous") }
        expect(["about"]) { reader.openAbout() }
        expect(["outcomeAction"]) { reader.outcomeHistoryContent()?.onAction?("history.next") }
        expect(["outcomeChoice"]) { reader.outcomeHistoryContent()?.onInspectionChoice?(choice) }
        XCTAssertNil(reader.historyContent(reader: true).input.expand)
        // Without a callback there is no control and no hook call.
        let bare = Screen(input: input, originals: originals, sides: sides, outcome: outcome,
                          onInteraction: { log.events.append("hold") })
        log.events = []
        bare.openPageAbout()
        bare.openAllProps()
        bare.openAbout()
        XCTAssertEqual(log.events, [])
        XCTAssertNil(bare.aboutOpener())
        XCTAssertNil(bare.chipsContent()?.onChoose)
        XCTAssertNil(bare.chipsContent()?.onAction)
        XCTAssertNil(bare.countryContent()?.onOpenOriginal)
        XCTAssertNil(bare.resultContent()?.onOpen)
        XCTAssertNil(bare.resultContent()?.onDetails)
        XCTAssertNil(bare.chooserContent()?.onChoose)
        XCTAssertNil(bare.chooserContent()?.onControl)
        XCTAssertNil(bare.catalogueContent()?.onSelect)
        XCTAssertNil(bare.originalDetailsContent()?.onHistory)
        XCTAssertNil(bare.historyContent(reader: false).onAction)
        XCTAssertNil(bare.outcomeHistoryContent()?.onAction)
        XCTAssertNil(bare.sideAction(sides.sides[0]))
        XCTAssertFalse(bare.model.aboutAvailable(canOpen: false))
        XCTAssertFalse(bare.model.allPropsAvailable(canOpen: false))
        let chips = PokerChipCardModel10868(input.chips!)
        XCTAssertNil(chips.chooseRef(chips.bars[0], canChoose: false))
        XCTAssertNil(PokerCountryCardModel10868(input.country!).entryRef(canOpen: false))
    }

    // MARK: - Payloads and reachable text

    func testEveryHandOffCarriesTheExactOriginalAndAnAdmittedPositionAndABadFutureKeyIsCaught() {
        let side = Self.mizrachi.yes
        let before = Self.baselineIndex(side)!
        let last = side.trades.count - 1
        func keys(_ found: [Payload]) -> Int { found.filter { if case .key = $0 { return true } else { return false } }.count }
        // Before the final table: every position key is before the scheduled restart.
        let beforeFound = Self.payloads(Self.parts(.beforeFinalTable).input)
        XCTAssertEqual(Self.violations(beforeFound, role: .beforeFinalTable), [])
        XCTAssertEqual(keys(beforeFound), before + 1)
        XCTAssertFalse(beforeFound.contains { if case .open = $0 { return true } else { return false } })
        let refs = beforeFound.filter { if case .ref = $0 { return true } else { return false } }
        XCTAssertEqual(refs, Self.players.map { Payload.ref(Self.ref($0, $0.yes)) } + [Payload.ref(Self.ref(Self.american, Self.american.yes))]
                        + Self.featured.map { Payload.ref(Self.ref($0, $0.yes)) })
        // The final: the result endpoints carry their own exact positions.
        let finalFound = Self.payloads(Self.parts(.final).input)
        XCTAssertEqual(Self.violations(finalFound, role: .final), [])
        let ref = Self.ref(Self.mizrachi, side)
        XCTAssertTrue(finalFound.contains(.open(FieldMovementOpen10868(ref: ref, observation: Self.pointID(Self.mizrachi, side, before)))))
        XCTAssertTrue(finalFound.contains(.open(FieldMovementOpen10868(ref: ref, observation: Self.pointID(Self.mizrachi, side, last)))))
        XCTAssertEqual(keys(finalFound), side.trades.count)
        // Deliberately bad control: a later position offered before the final table is caught.
        var bad = Self.parts(.beforeFinalTable)
        guard let inspection = bad.history.inspection else { return XCTFail("before-table inspection") }
        let future = FieldHistoryInspectionChoice10868(id: Self.pointID(Self.mizrachi, side, last), lines: ["later"],
                                                       spoken: "later", isSelected: false)
        bad.history = Self.rebuilt(bad.history, inspection: FieldHistoryInspection10868(
            x: inspection.x, caption: inspection.caption, selections: inspection.selections,
            choices: inspection.choices + [future], choicePresentation: inspection.choicePresentation, note: inspection.note))
        XCTAssertEqual(Self.violations(Self.payloads(bad.input), role: .beforeFinalTable), ["563321:Yes:\(last) is after the final table"])
        XCTAssertEqual(Self.violations(Self.payloads(bad.input), role: .final), [])
        // A foreign original and a position that was never retained are caught.
        let foreign = Payload.open(FieldMovementOpen10868(ref: Self.ref(Self.mizrachi, side, scope: "constructed:other"), observation: nil))
        XCTAssertEqual(Self.violations([foreign], role: .final), ["foreign original 563321"])
        XCTAssertEqual(Self.violations([.key("563321:Yes:99999")], role: .beforeFinalTable),
                       ["563321:Yes:99999 is not a retained position"])
        // A foreign chip row hands back nothing at all.
        let foreignRow = PokerChipCardModel10868(Self.chips(Self.chips(.final), rows: [Self.chipRow(Self.mizrachi, scope: "constructed:other")]))
        XCTAssertNil(foreignRow.chooseRef(foreignRow.bars[0], canChoose: true))
    }

    func testEveryReachableTextBeforeTheFinalTableCarriesNoLaterFactWithAFinalPositiveControl() {
        // Meaning-aware tokens: a side's meaning, a chance or a date is not a result.
        for text in ["Winner from outside the USA", "American winner", "An American champion?", "20%", "15.9%", "0.1%",
                     "Wins the tournament", "Doesn’t win the tournament", "Final table · scheduled", "Jul 15"] {
            XCTAssertFalse(Self.isResult(text), text)
        }
        for text in ["USA", "1st · $10,000,000", "Finished 2nd", "9th", "Reported finish", "Won the tournament"] {
            XCTAssertTrue(Self.isResult(text), text)
        }
        // Final positive control: every later fact is reachable at the final and the guard sees it.
        let finalTexts = Self.reachable(Self.parts(.final).input, originals: Self.bundle(.final, Self.mizrachi, Self.mizrachi.yes),
                                        sides: Self.sides(Self.mizrachi), outcome: Self.outcome(.final, Self.mizrachi, Self.mizrachi.no))
        XCTAssertFalse(Self.leaks(finalTexts, role: .beforeFinalTable).isEmpty)
        for fact in ["USA", "Finished 1st", "1st · $10,000,000", "Won the tournament", "Happened", "Result reported"] {
            XCTAssertTrue(finalTexts.contains { $0.contains(fact) }, fact)
        }
        XCTAssertTrue(finalTexts.contains(Self.retainedResultMeaning))
        let lastClock = Self.clockTime(Self.mizrachi.yes.trades[Self.mizrachi.yes.trades.count - 1].t)
        XCTAssertTrue(finalTexts.contains { $0.contains(lastClock) })
        XCTAssertTrue(Self.laterClocks.contains(lastClock))
        // Before the final table, in every reachable surface, nothing later leaks.
        let cases: [(Parts, PokerEventPageOriginals10868?, PokerOutcomeReaderInput10868?)] = [
            (Self.parts(.beforeFinalTable), nil, nil),
            (Self.parts(.beforeFinalTable, inspect: .at(0)), Self.bundle(.beforeFinalTable, Self.mizrachi, Self.mizrachi.no), nil),
            (Self.parts(.beforeFinalTable, inspect: .none), Self.bundle(.beforeFinalTable, Self.american, Self.american.no),
             Self.outcome(.beforeFinalTable, Self.american, Self.american.no)),
            (Self.parts(.beforeFinalTable, rogue: true), Self.bundle(.final, Self.mizrachi, Self.mizrachi.no),
             Self.outcome(.final, Self.mizrachi, Self.mizrachi.no)),
        ]
        for (index, item) in cases.enumerated() {
            let texts = Self.reachable(item.0.input, originals: item.1, sides: Self.sides(Self.mizrachi), outcome: item.2)
            XCTAssertEqual(Self.leaks(texts, role: .beforeFinalTable), [], "case \(index)")
            XCTAssertFalse(texts.contains { $0.localizedCaseInsensitiveContains("actual start") }, "case \(index)")
            XCTAssertTrue(texts.contains("Pre-tournament chance unavailable"), "case \(index)")
            XCTAssertTrue(texts.contains("Final table · scheduled"), "case \(index)")
        }
        // Rules state conditions known beforehand; they are not later facts.
        XCTAssertEqual(Self.leaks(Self.markets.map { $0.rules }, role: .beforeFinalTable), [])
    }

    // MARK: - Readers, modes, held selections and the shared dated ticks

    func testFullSizeReadersAndTheCompactPageShareTheOwnersDatedTicksAndInspection() {
        for role in [Role.beforeFinalTable, .final] {
            let input = Self.parts(role).input
            let model = Model(input)
            let page = Screen(input: input)
            let ticks = input.history.xTicks
            // The reference's dated endpoints: first retained trade of any named player, and the role's horizon.
            let first = Self.players.flatMap { Self.visible($0.yes, role).map { $0.1.t } }.min()!
            let horizon = role == .final ? Self.resultReportAt : Self.scheduledFinalTable
            XCTAssertEqual(ticks.map { $0.value }, [Double(first), Double(first) + Double(horizon - first) / 2, Double(horizon)])
            XCTAssertEqual(ticks.first?.value, input.history.domain.lower)
            XCTAssertEqual(ticks.last?.value, input.history.domain.upper)
            XCTAssertEqual(ticks.last?.lines.last, role == .final ? "Result reported" : "Final table · scheduled")
            XCTAssertEqual(FieldHistoryGeometry10868.placedXTicks(input.history), ticks)
            // The same ticks, inspection and series reach both the compact and the full-size shared history.
            for reader in [false, true] {
                let shown = page.historyContent(reader: reader).input
                XCTAssertEqual(shown.xTicks, ticks, "\(role) reader \(reader)")
                XCTAssertEqual(shown.series, input.history.series, "\(role) reader \(reader)")
                XCTAssertEqual(shown.inspection, input.history.inspection, "\(role) reader \(reader)")
                XCTAssertEqual(shown.domain, input.history.domain, "\(role) reader \(reader)")
                XCTAssertEqual(model.history(reader: reader).xTicks, ticks, "\(role) reader \(reader)")
            }
            XCTAssertEqual(model.history(reader: false), input.history)
            XCTAssertEqual(model.history(reader: true).plotHeight, 520)
            XCTAssertNil(model.history(reader: true).expand)
            XCTAssertNotNil(model.history(reader: false).expand)
            // Each selected trade keeps its own date: the readout's date is its own position's clock.
            let comparison = Chance(input.comparison, history: model.history(reader: true))
            let inspected = Self.inspectIndex(role, .standard, Self.mizrachi.yes)!
            XCTAssertEqual(comparison.slots.last?.detail, Self.clock(Self.mizrachi.yes.trades[inspected].t))
            XCTAssertEqual(page.comparisonContent(reader: true)?.history, model.history(reader: true))
        }
        // The Details composition deliberately omits ticks and every chart control.
        let mini = Self.recordedHistory(.final, Self.mizrachi, Self.mizrachi.yes).history
        XCTAssertEqual(mini.xTicks, [])
        XCTAssertTrue(Originals.isMiniHistory(mini))
    }

    func testReadersModesAndHeldSelectionsUseTheSameInputsAndRestoreOnlyByExactIdentity() {
        let before = Model(Self.parts(.beforeFinalTable).input)
        let final = Model(Self.parts(.final).input)
        XCTAssertEqual(PokerEventPageCard10868.allCases.map { before.readerShows($0) }, [true, true, true, false])
        XCTAssertEqual(PokerEventPageCard10868.allCases.map { final.readerShows($0) }, [true, true, true, true])
        XCTAssertEqual(before.story("chips")?.card, .chips)
        XCTAssertNil(before.story("result"))
        XCTAssertNil(before.story("history"))
        XCTAssertEqual(final.story("result")?.card, .result)
        // A duplicated link, an unmounted card and an unknown id resolve to no story.
        var duplicated = Self.parts(.final)
        duplicated.stories += [PokerEventPageStory10868(cardID: "country", card: .chips)]
        XCTAssertNil(Model(duplicated.input).story("country"))
        XCTAssertEqual(Model(duplicated.input).story("chips")?.card, .chips)
        var missing = Self.parts(.final)
        missing.chips = nil
        XCTAssertNil(Model(missing.input).story("chips"))
        XCTAssertFalse(Model(missing.input).readerShows(.chips))
        XCTAssertNil(Screen(input: missing.input).chipsContent())
        XCTAssertNil(final.story("unknown"))
        // The stream's own slots: foreign, missing, duplicated and withdrawn cards are explicit absences.
        let withdrawn = StoryStreamPresentation10868.Card(id: "gone", name: "Gone", available: false)
        let twin = StoryStreamPresentation10868.Card(id: "chips", name: "How the field shaped up")
        let stream = Self.stream(true, cards: [withdrawn, twin])
        let foreignRef = StoryStreamPresentation10868.CardRef(scope: "constructed:other", id: "country")
        XCTAssertEqual(stream.slot(foreignRef), .unavailable(foreignRef, .foreignScope))
        let unknownRef = StoryStreamPresentation10868.CardRef(scope: Self.storyScope, id: "unknown")
        XCTAssertEqual(stream.slot(unknownRef), .unavailable(unknownRef, .missing))
        let chipsRef = StoryStreamPresentation10868.CardRef(scope: Self.storyScope, id: "chips")
        XCTAssertEqual(stream.slot(chipsRef), .unavailable(chipsRef, .duplicate))
        let goneRef = StoryStreamPresentation10868.CardRef(scope: Self.storyScope, id: "gone")
        XCTAssertEqual(stream.slot(goneRef), .unavailable(goneRef, .withdrawn))
        // The reader height: the owner's taller finite height, never shorter, never infinite.
        var height = Self.parts(.final)
        for (owner, expected) in [(CGFloat?(nil), CGFloat(260)), (520, 520), (100, 260), (.infinity, 260), (.nan, 260), (-4, 260)] {
            height.readerPlotHeight = owner
            XCTAssertEqual(Model(height.input).history(reader: true).plotHeight, expected, "\(String(describing: owner))")
        }
        XCTAssertEqual(Model.outcomeHistory(Self.outcome(.final, Self.mizrachi, Self.mizrachi.no)).plotHeight, 480)
        // Held originals: an omitted identity is unavailable and restored only by that exact identity.
        let side = Self.mizrachi.no
        let held = Self.selection(Self.mizrachi, side)
        let omitted = Self.originals(.final, Self.mizrachi, side,
                                     catalogue: Self.originalsCatalogue(.final, without: Self.identity(Self.mizrachi, side)))
        XCTAssertNil(Originals.original(in: omitted.catalogue, selection: held))
        XCTAssertNil(Screen.sideSelection(Self.sides(Self.mizrachi).sides[1], in: omitted, canSelect: true))
        let restored = Self.originals(.final, Self.mizrachi, side)
        XCTAssertEqual(Originals.original(in: restored.catalogue, selection: held)?.identity, Self.identity(Self.mizrachi, side))
        XCTAssertEqual(Screen.sideSelection(Self.sides(Self.mizrachi).sides[1], in: restored, canSelect: true), held)
        let neighbour = Originals.Selection(scope: Self.originalsScope,
                                            identity: Originals.Identity(source: Self.source, market: Self.mizrachi.id, side: "No"))
        XCTAssertNil(Originals.original(in: restored.catalogue, selection: neighbour))
        XCTAssertNil(Originals.original(in: restored.catalogue, selection: Self.selection(Self.mizrachi, side, scope: "constructed:other")))
        // The held side's recorded history matches its own selection, never another side's.
        if case .recorded(let shown)? = Originals.recorded(catalogue: restored.catalogue, selection: held,
                                                           context: restored.recorded, hasCallback: true) {
            XCTAssertEqual(shown.selection, held)
            XCTAssertEqual(shown.content.readings.map { $0.text }, ["80%", "1%"])
            XCTAssertEqual(shown.finish?.words, "1st")
            XCTAssertEqual(shown.content.result?.words, "Didn’t happen")
        } else {
            XCTFail("the held side's recorded history")
        }
        let other = Originals.recorded(catalogue: restored.catalogue, selection: Self.selection(Self.mizrachi, Self.mizrachi.yes),
                                       context: restored.recorded, hasCallback: true)
        if case .unmatched(_, let words)? = other {
            XCTAssertEqual(words, "Recorded history unavailable for this outcome")
        } else {
            XCTFail("another side never borrows this recorded history")
        }
        // Content modes mount only with their own input.
        XCTAssertNotNil(Screen(input: Self.parts(.final).input, mode: .chooser).chooserContent())
        var noChooser = Self.parts(.final)
        noChooser.chooser = nil
        XCTAssertNil(Screen(input: noChooser.input, mode: .chooser).chooserContent())
        XCTAssertNil(Screen(input: Self.parts(.final).input, mode: .catalogue).catalogueContent())
        XCTAssertNotNil(Screen(input: Self.parts(.final).input, mode: .catalogue,
                               originals: PokerEventPageOriginals10868(role: .final, originals: restored)).catalogueContent())
        XCTAssertNotNil(Screen(input: Self.parts(.final).input, mode: .about).aboutContent())
    }

    func testPhoneWideAndAccessibilitySizesStackWithoutShrinkingLongNamesOrTheTallPlot() {
        XCTAssertEqual(FieldEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(FieldEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(FieldEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(FieldEventPageModel10868.arrangements(sizeClass: .regular,
                                                             accessibilitySize: DynamicTypeSize.xxxLarge.isAccessibilitySize),
                       [.sideBySide, .stacked])
        XCTAssertEqual(FieldEventPageModel10868.arrangements(sizeClass: .regular,
                                                             accessibilitySize: DynamicTypeSize.accessibility3.isAccessibilitySize),
                       [.stacked])
        XCTAssertEqual(Chance.arrangements(accessibilitySize: DynamicTypeSize.xxxLarge.isAccessibilitySize), [.sideBySide, .stacked])
        XCTAssertEqual(Chance.arrangements(accessibilitySize: DynamicTypeSize.accessibility3.isAccessibilitySize), [.stacked])
        // CONSTRUCTED intrinsic long names stay whole in every spoken and summarized place.
        let long = "Michael “The Grinder” Mizrachi of Hollywood, Florida, United States of America"
        let row = PokerChipRow10868(ref: Self.ref(Self.mizrachi, Self.mizrachi.yes), label: long, share: Self.share(Self.mizrachi),
                                    chance: Self.winChance(Self.mizrachi))
        let catalogue = Self.catalogue.map { original in
            original.ref == row.ref
                ? FieldChooserOriginal10868(ref: original.ref, name: long, plan: original.plan, preview: original.preview,
                                            movement: nil, clock: nil, result: nil, browseStatus: original.browseStatus)
                : original
        }
        let base = Self.chips(.final)
        let chips = PokerChipCardModel10868(PokerChipCardInput10868(
            scope: base.scope, catalogue: catalogue, rows: [row], selected: base.selected, scale: base.scale, copy: base.copy,
            unavailableWords: base.unavailableWords, toggle: base.toggle, source: base.source))
        XCTAssertTrue(chips.rowSummary(chips.bars[0]).hasPrefix(long + ". "))
        let comparison = Self.comparison(.final, Self.mizrachi, Self.mizrachi.yes, inspect: 354)
        let renamed = PokerChanceComparisonInput10868(role: .final, seriesID: comparison.seriesID, name: long,
                                                      meaning: comparison.meaning, baseline: comparison.baseline,
                                                      inspected: comparison.inspected, result: comparison.result, copy: comparison.copy)
        let history = Self.history(.final, [(Self.mizrachi, Self.mizrachi.yes)], inspect: 354)
        XCTAssertTrue(Chance(renamed, history: history).spoken.hasPrefix(long + ". "))
        // The tall plot keeps the owner's height at every size; full size only grows it, finitely.
        let input = Self.parts(.final).input
        XCTAssertEqual(input.history.plotHeight, 260)
        XCTAssertEqual(Model(input).history(reader: true).plotHeight, 520)
        XCTAssertTrue(Model(input).history(reader: true).plotHeight.isFinite)
        // The chip bars keep one finite common axis at phone and wide widths, and draw nothing when they cannot.
        for width in [CGFloat(120), 390, 900] {
            guard let plan = PokerChipCardModel10868.barPlan(share: 0.185, chance: 0.15, ticks: [0.25, 0.5, 0.75, 1],
                                                             in: CGSize(width: width, height: 22), barHeight: 9, gap: 4, lineWidth: 1.5),
                  let share = plan.share, let chance = plan.chanceBounds else { XCTFail("\(width)"); continue }
            XCTAssertEqual(share.minX, chance.minX, "\(width)")
            XCTAssertTrue(share.maxX > chance.maxX, "\(width)")
            XCTAssertTrue(plan.tickXs.allSatisfy { $0.isFinite && $0 <= width }, "\(width)")
        }
        XCTAssertNil(PokerChipCardModel10868.barPlan(share: 0.2, chance: 0.2, ticks: [], in: CGSize(width: 3, height: 22),
                                                     barHeight: 9, gap: 4, lineWidth: 1.5))
        XCTAssertNil(PokerChipCardModel10868.barPlan(share: 0.2, chance: 0.2, ticks: [], in: CGSize(width: 300, height: 10),
                                                     barHeight: 9, gap: 4, lineWidth: 1.5))
    }

    func testEveryOriginalKeepsItsRulesByteExactAndItsOwnIdentityTokenAndOutcome() {
        XCTAssertEqual(Set(Self.winners.map { $0.rules }).count, 1)
        XCTAssertNotEqual(Self.american.rules, Self.mizrachi.rules)
        for role in [Role.beforeFinalTable, .final] {
            let catalogue = Self.originalsCatalogue(role)
            for market in Self.markets {
                for side in market.sides {
                    let label = "\(role) \(market.id) \(side.label)"
                    guard let content = Originals.content(catalogue: catalogue, selection: Self.selection(market, side)) else {
                        XCTFail(label)
                        continue
                    }
                    guard case .verified(let kept) = content.rules else {
                        XCTFail(label)
                        continue
                    }
                    XCTAssertEqual(kept.joined(separator: "\n\n"), market.rules, label)
                    XCTAssertEqual(content.title, market.predicate, label)
                    XCTAssertTrue(content.about.contains(Originals.Row(label: "Outcome token", value: side.token)), label)
                    XCTAssertTrue(content.about.contains(Originals.Row(label: "Condition", value: market.condition)), label)
                    XCTAssertTrue(content.about.contains(Originals.Row(label: "Provider", value: market.providerURL)), label)
                    XCTAssertEqual(content.result == nil, role == .beforeFinalTable, label)
                }
            }
        }
        // Rules the owner cannot prove are shown as its own unavailable words, verbatim.
        let unproved = Self.original(Self.mizrachi, Self.mizrachi.yes, .final, rules: .unavailable("Rules not verified for this outcome"))
        let catalogue = Originals.Catalogue(scope: Self.originalsScope, originals: [unproved])
        XCTAssertEqual(Originals.content(catalogue: catalogue, selection: Self.selection(Self.mizrachi, Self.mizrachi.yes))?.rules,
                       .unavailable("Rules not verified for this outcome"))
        // The capture's rule text keeps its own paragraphs and quotation marks.
        XCTAssertEqual(Self.paragraphs(Self.mizrachi.rules).count, 4)
        XCTAssertTrue(Self.mizrachi.rules.contains("resolve to \"Yes\""))
    }

}

// MARK: - Retained fixture (generated)
// @@BEGIN GENERATED FIXTURE@@
// GENERATED by `python3 -I /tmp/poker-fixture-gen.py pokerCapture.json <out>` from pokerCapture.json
// sha256 39e96a1bd70d070113e93b97020e1066fa1e744cab28660e4dc22a2094bb410e. Mechanical and lossless; never edit by hand.
extension PokerEventPagePresentation10868Tests {
    fileprivate static let retainedEvent = "2025 WSOP Main Event"
    fileprivate static let retainedScheduledFinalTable = 1752609600
    fileprivate static let retainedActualFinalTableStart: Int? = nil
    fileprivate static let retainedResultReportAt = 1752706740
    fileprivate static let retainedTournamentBaseline: Double? = nil
    fileprivate static let retainedBaselineMeaning = "Last retained trade strictly before scheduled final-table restart. Not pre-tournament."
    fileprivate static let retainedResultMeaning = "Final standings and prizes transcribed from the report; chip counts refer to the nine-player final table. Exact hand times and actual finish time unverified."
    fileprivate static let retainedScheduledSource = "https://www.pokernews.com/news/2025/07/wsop-main-event-final-table-mizrachi-margets-final-nine-49179.htm"
    fileprivate static let retainedResultSource = "https://www.pokernews.com/news/2025/07/michael-mizrachi-wins-2025-wsop-main-event-49219.htm"
    fileprivate static let retainedMarkets: [RetainedMarket] = [
        RetainedMarket(
            id: "563320", name: "John Wasnock", kind: "winner",
            predicate: "Will John Wasnock win the 2025 WSOP Main Event?",
            condition: "0x6a63de1658fc2bb962da2df3e15a493e646257e4649592fb9362d4b98cba983c",
            rules: "This is a market to predict which player will win the 2025 World Series of Poker (WSOP) Main Event.\n\nThis market will resolve to \"Yes\" if the listed player wins the 2025 WSOP Main Event tournament. Otherwise, it will resolve to \"No\".\n\nIf the 2025 WSOP Main Event is canceled or not completed by August 10, 2025, this market will resolve to \"Other\".\n\nThe primary resolution source for this market will be wsop.com. However, a consensus of credible reporting may also be used.",
            providerURL: "https://polymarket.com/event/world-series-of-poker-main-event-winner-139",
            chips: 108100000, finish: 2, prize: 6000000,
            sides: [
                RetainedSide(side: "Yes", token: "93611809205549567854660809781112606464105761378957984383432604017724323700599", resolved: false, trades: retained563320Yes),
                RetainedSide(side: "No", token: "22591889011179095147189817701557758225268476403474365228384663581611891565675", resolved: true, trades: retained563320No),
            ]),
        RetainedMarket(
            id: "563321", name: "Michael Mizrachi", kind: "winner",
            predicate: "Will Michael Mizrachi win the 2025 WSOP Main Event?",
            condition: "0x2eb93075f572715b2d6255916879f4e524de31916106311d5e47a57ede334c1d",
            rules: "This is a market to predict which player will win the 2025 World Series of Poker (WSOP) Main Event.\n\nThis market will resolve to \"Yes\" if the listed player wins the 2025 WSOP Main Event tournament. Otherwise, it will resolve to \"No\".\n\nIf the 2025 WSOP Main Event is canceled or not completed by August 10, 2025, this market will resolve to \"Other\".\n\nThe primary resolution source for this market will be wsop.com. However, a consensus of credible reporting may also be used.",
            providerURL: "https://polymarket.com/event/world-series-of-poker-main-event-winner-139",
            chips: 93000000, finish: 1, prize: 10000000,
            sides: [
                RetainedSide(side: "Yes", token: "39446832113971808797432436553920176959607168994314237450098929604414361597335", resolved: true, trades: retained563321Yes),
                RetainedSide(side: "No", token: "113196065454979311698297798878489296504988790841634496752022138546447787698799", resolved: false, trades: retained563321No),
            ]),
        RetainedMarket(
            id: "563322", name: "Braxton Dunaway", kind: "winner",
            predicate: "Will Braxton Dunaway win the 2025 WSOP Main Event?",
            condition: "0x43c314bc5d1efd09d3e97332631dad6388bf5ce7f9b63f205947ac3b5e694ed6",
            rules: "This is a market to predict which player will win the 2025 World Series of Poker (WSOP) Main Event.\n\nThis market will resolve to \"Yes\" if the listed player wins the 2025 WSOP Main Event tournament. Otherwise, it will resolve to \"No\".\n\nIf the 2025 WSOP Main Event is canceled or not completed by August 10, 2025, this market will resolve to \"Other\".\n\nThe primary resolution source for this market will be wsop.com. However, a consensus of credible reporting may also be used.",
            providerURL: "https://polymarket.com/event/world-series-of-poker-main-event-winner-139",
            chips: 91900000, finish: 3, prize: 4000000,
            sides: [
                RetainedSide(side: "Yes", token: "54007411526122961012175150260188279181775330745260082874671440185034557637335", resolved: false, trades: retained563322Yes),
                RetainedSide(side: "No", token: "31643998685776613219415760780962077861532580878534948645487911905233929930230", resolved: true, trades: retained563322No),
            ]),
        RetainedMarket(
            id: "563323", name: "Kenny Hallaert", kind: "winner",
            predicate: "Will Kenny Hallaert win the 2025 WSOP Main Event?",
            condition: "0x81ea46365403f183e0bc8b631fb3951a989e65ae85d6f6c0ea8afc2cea0cd408",
            rules: "This is a market to predict which player will win the 2025 World Series of Poker (WSOP) Main Event.\n\nThis market will resolve to \"Yes\" if the listed player wins the 2025 WSOP Main Event tournament. Otherwise, it will resolve to \"No\".\n\nIf the 2025 WSOP Main Event is canceled or not completed by August 10, 2025, this market will resolve to \"Other\".\n\nThe primary resolution source for this market will be wsop.com. However, a consensus of credible reporting may also be used.",
            providerURL: "https://polymarket.com/event/world-series-of-poker-main-event-winner-139",
            chips: 80500000, finish: 4, prize: 3000000,
            sides: [
                RetainedSide(side: "Yes", token: "16973950857859431886137122398793310406820795875101347344403889880036092057759", resolved: false, trades: retained563323Yes),
                RetainedSide(side: "No", token: "79050479605575074831498814850042018434519707703375057218766746852713667546636", resolved: true, trades: retained563323No),
            ]),
        RetainedMarket(
            id: "563324", name: "Leo Margets", kind: "winner",
            predicate: "Will Leo Margets win the 2025 WSOP Main Event?",
            condition: "0x7fed109beefcab5f5f4dbfafcf912d024b9036214e70511fbbf2df53efe3db96",
            rules: "This is a market to predict which player will win the 2025 World Series of Poker (WSOP) Main Event.\n\nThis market will resolve to \"Yes\" if the listed player wins the 2025 WSOP Main Event tournament. Otherwise, it will resolve to \"No\".\n\nIf the 2025 WSOP Main Event is canceled or not completed by August 10, 2025, this market will resolve to \"Other\".\n\nThe primary resolution source for this market will be wsop.com. However, a consensus of credible reporting may also be used.",
            providerURL: "https://polymarket.com/event/world-series-of-poker-main-event-winner-139",
            chips: 53400000, finish: 7, prize: 1500000,
            sides: [
                RetainedSide(side: "Yes", token: "70525845656210028812193973017256795129882120675272812298186600537134359545675", resolved: false, trades: retained563324Yes),
                RetainedSide(side: "No", token: "56256288161446537027497184993047732119334888842312499054403019134676898509560", resolved: true, trades: retained563324No),
            ]),
        RetainedMarket(
            id: "563325", name: "Luka Bojovic", kind: "winner",
            predicate: "Will Luka Bojovic win the 2025 WSOP Main Event?",
            condition: "0xf751e59cffde0c8a2fab132f3ee136a709c9bf403236e4710c084866b5b5af38",
            rules: "This is a market to predict which player will win the 2025 World Series of Poker (WSOP) Main Event.\n\nThis market will resolve to \"Yes\" if the listed player wins the 2025 WSOP Main Event tournament. Otherwise, it will resolve to \"No\".\n\nIf the 2025 WSOP Main Event is canceled or not completed by August 10, 2025, this market will resolve to \"Other\".\n\nThe primary resolution source for this market will be wsop.com. However, a consensus of credible reporting may also be used.",
            providerURL: "https://polymarket.com/event/world-series-of-poker-main-event-winner-139",
            chips: 51000000, finish: 5, prize: 2400000,
            sides: [
                RetainedSide(side: "Yes", token: "95261709399889885514699021173114047832650025047822916833605063642428558797037", resolved: false, trades: retained563325Yes),
                RetainedSide(side: "No", token: "98749479055139835128534568810754685761828700484714777413784975096358189962066", resolved: true, trades: retained563325No),
            ]),
        RetainedMarket(
            id: "563326", name: "Adam Hendrix", kind: "winner",
            predicate: "Will Adam Hendrix win the 2025 WSOP Main Event?",
            condition: "0x3715ee1a84aa476342ac40db1c3144a093e9e1b2a5d50825ccc92e99e34785bd",
            rules: "This is a market to predict which player will win the 2025 World Series of Poker (WSOP) Main Event.\n\nThis market will resolve to \"Yes\" if the listed player wins the 2025 WSOP Main Event tournament. Otherwise, it will resolve to \"No\".\n\nIf the 2025 WSOP Main Event is canceled or not completed by August 10, 2025, this market will resolve to \"Other\".\n\nThe primary resolution source for this market will be wsop.com. However, a consensus of credible reporting may also be used.",
            providerURL: "https://polymarket.com/event/world-series-of-poker-main-event-winner-139",
            chips: 48000000, finish: 6, prize: 1900000,
            sides: [
                RetainedSide(side: "Yes", token: "102078752822659324685315257935616842319084887274219330977071319879514696736211", resolved: false, trades: retained563326Yes),
                RetainedSide(side: "No", token: "33441822698425029020771837583281011069614081638401926915211849344199213636253", resolved: true, trades: retained563326No),
            ]),
        RetainedMarket(
            id: "563327", name: "Daehyung Lee", kind: "winner",
            predicate: "Will Daehyung Lee win the 2025 WSOP Main Event?",
            condition: "0xb00516a5638f073f5781b779c9be59c506072f97d8e70f0fcf2d21fb743fc0cd",
            rules: "This is a market to predict which player will win the 2025 World Series of Poker (WSOP) Main Event.\n\nThis market will resolve to \"Yes\" if the listed player wins the 2025 WSOP Main Event tournament. Otherwise, it will resolve to \"No\".\n\nIf the 2025 WSOP Main Event is canceled or not completed by August 10, 2025, this market will resolve to \"Other\".\n\nThe primary resolution source for this market will be wsop.com. However, a consensus of credible reporting may also be used.",
            providerURL: "https://polymarket.com/event/world-series-of-poker-main-event-winner-139",
            chips: 34900000, finish: 9, prize: 1000000,
            sides: [
                RetainedSide(side: "Yes", token: "99474896870379630387133111921915430894547118770016796001026499530168455559627", resolved: false, trades: retained563327Yes),
                RetainedSide(side: "No", token: "37226321411575671532503212584946085279042982949929174550322539599077656040233", resolved: true, trades: retained563327No),
            ]),
        RetainedMarket(
            id: "563328", name: "Jarod Minghini", kind: "winner",
            predicate: "Will Jarod Minghini win the 2025 WSOP Main Event?",
            condition: "0x880d15ee6ede16d9f1efe2591157aa4d894085802796740b530c509d4da89ff8",
            rules: "This is a market to predict which player will win the 2025 World Series of Poker (WSOP) Main Event.\n\nThis market will resolve to \"Yes\" if the listed player wins the 2025 WSOP Main Event tournament. Otherwise, it will resolve to \"No\".\n\nIf the 2025 WSOP Main Event is canceled or not completed by August 10, 2025, this market will resolve to \"Other\".\n\nThe primary resolution source for this market will be wsop.com. However, a consensus of credible reporting may also be used.",
            providerURL: "https://polymarket.com/event/world-series-of-poker-main-event-winner-139",
            chips: 23600000, finish: 8, prize: 1250000,
            sides: [
                RetainedSide(side: "Yes", token: "52253537439679771622833694180588921373701800090156621514027725400757805378578", resolved: false, trades: retained563328Yes),
                RetainedSide(side: "No", token: "100651713412622837529135557738292393699942968016389835035699990267905771956197", resolved: true, trades: retained563328No),
            ]),
        RetainedMarket(
            id: "563329", name: "Player A", kind: "winner",
            predicate: "Will Player A win the 2025 WSOP Main Event?",
            condition: "0x75fe6dce852749fdad3dfd13b4005cf027af40c49983599f864468e2dd0c61a6",
            rules: "This is a market to predict which player will win the 2025 World Series of Poker (WSOP) Main Event.\n\nThis market will resolve to \"Yes\" if the listed player wins the 2025 WSOP Main Event tournament. Otherwise, it will resolve to \"No\".\n\nIf the 2025 WSOP Main Event is canceled or not completed by August 10, 2025, this market will resolve to \"Other\".\n\nThe primary resolution source for this market will be wsop.com. However, a consensus of credible reporting may also be used.",
            providerURL: "https://polymarket.com/event/world-series-of-poker-main-event-winner-139",
            chips: nil, finish: nil, prize: nil,
            sides: [
                RetainedSide(side: "Yes", token: "34713531279409200765517588601685555230784409098270920345788005644007018292323", resolved: false, trades: retained563329Yes),
                RetainedSide(side: "No", token: "55952123937355907337831046932564274319844748922698587930204384697698571232162", resolved: true, trades: retained563329No),
            ]),
        RetainedMarket(
            id: "563330", name: "Player B", kind: "winner",
            predicate: "Will Player B win the 2025 WSOP Main Event?",
            condition: "0x08e7ec8e8ff36091380795cb03fa87633b977338082e4872b809015e5e33af35",
            rules: "This is a market to predict which player will win the 2025 World Series of Poker (WSOP) Main Event.\n\nThis market will resolve to \"Yes\" if the listed player wins the 2025 WSOP Main Event tournament. Otherwise, it will resolve to \"No\".\n\nIf the 2025 WSOP Main Event is canceled or not completed by August 10, 2025, this market will resolve to \"Other\".\n\nThe primary resolution source for this market will be wsop.com. However, a consensus of credible reporting may also be used.",
            providerURL: "https://polymarket.com/event/world-series-of-poker-main-event-winner-139",
            chips: nil, finish: nil, prize: nil,
            sides: [
                RetainedSide(side: "Yes", token: "25365922095310170048788903174939493561498184499908479690193761146690525195459", resolved: false, trades: retained563330Yes),
                RetainedSide(side: "No", token: "66271306431664375284301275923230934174771948101728671961486612680252882531373", resolved: true, trades: retained563330No),
            ]),
        RetainedMarket(
            id: "563331", name: "Other", kind: "winner",
            predicate: "Will another player win the 2025 WSOP Main Event?",
            condition: "0x4f4b272676c111b092ec6ccaae910fbcdaa2bbd96c6f103fe3518b6a90b4483c",
            rules: "This is a market to predict which player will win the 2025 World Series of Poker (WSOP) Main Event.\n\nThis market will resolve to \"Yes\" if the listed player wins the 2025 WSOP Main Event tournament. Otherwise, it will resolve to \"No\".\n\nIf the 2025 WSOP Main Event is canceled or not completed by August 10, 2025, this market will resolve to \"Other\".\n\nThe primary resolution source for this market will be wsop.com. However, a consensus of credible reporting may also be used.",
            providerURL: "https://polymarket.com/event/world-series-of-poker-main-event-winner-139",
            chips: nil, finish: nil, prize: nil,
            sides: [
                RetainedSide(side: "Yes", token: "77750324196314535874903146994108803316053205391731118939375960764448462224069", resolved: false, trades: retained563331Yes),
                RetainedSide(side: "No", token: "39641883941988186541551498392366122408828729134452481377523251459798542970484", resolved: true, trades: retained563331No),
            ]),
        RetainedMarket(
            id: "557372", name: "American winner", kind: "nationality",
            predicate: "World Series of Poker – American winner?",
            condition: "0x98ba1e814d62d6a99a2b1798a86987d508858a6e457873f55b1e9131e06dad83",
            rules: "This market will resolve to \"Yes\" if a player representing the United States of America wins the 2025 World Series of Poker (WSOP) Main Event. Otherwise, this market will resolve to \"No.\"\n\nIf all players from United States of America are eliminated before the final table, this market will resolve to \"No.\"\n\nThe primary resolution source for this market will be wsop.com, specifically the listed country of the winning player. If necessary, a consensus of credible reporting may also be used.",
            providerURL: "https://polymarket.com/event/world-series-of-poker-american-winner",
            chips: nil, finish: nil, prize: nil,
            sides: [
                RetainedSide(side: "Yes", token: "97576174155356432818447765427616895362845594466343950003439153954771002930685", resolved: true, trades: retained557372Yes),
                RetainedSide(side: "No", token: "81236142643039463252039511403318754401052348257158243813496804646250775983463", resolved: false, trades: retained557372No),
            ]),
    ]

    fileprivate static let retained563320Yes: [RetainedTrade] = [
        (0, 1752501561, "0.16", "12.5", "0xcaf4639d148a927aa67552afdaa743dc584abcb33e73648f07710d515b3ac1db"),
        (1, 1752509496, "0.1399999888", "71.42857", "0xfdd2f5749f20e1ec85d95c631e27b311438816df221ec4f608795b865a01f4c4"),
        (2, 1752510476, "0.1399999965", "242.142856", "0xdcd23b6a47e77b3ab923062a6a25661e8ca4e74ed51899ab73af2f44a47f8a83"),
        (3, 1752510490, "0.1399999175", "9.214284", "0x49a04c1b616dc4da1f6b850f14a5ceead01e766dee568bf6f70b7e7d8938fa93"),
        (4, 1752510508, "0.1497005988", "6.68", "0x88372890bd35def8fe59691df75e95e657ee1b73086b7f36300373c1d04cfe61"),
        (5, 1752510650, "0.1499999993", "1106.666665", "0xc6e917e5a813a2aded791bf6c3476385c5d197d80c807488422a3672c0286a52"),
        (6, 1752510666, "0.15", "9.8", "0x5f4e4954ac58a53d3286e941529fb9612bff8a68e401b9bc2bd59c692ccb5146"),
        (7, 1752511726, "0.15", "0.05", "0x635f6c91e0ce6a669001e8153ea64c5b24861f6cbf45737a9783568e48524062"),
        (8, 1752519157, "0.16", "433", "0x192d8029350b9f1985be23f58db44aab55878294c0e4ce91c799e7f65b35cecf"),
        (9, 1752520291, "0.17", "10", "0xb3681a68e1cbf00dd9aa8c321f45e94a31ae347f37335d2b7844326ecac5c36e"),
        (10, 1752520513, "0.16", "8", "0x34d7c598d82badfed11036f59663d949c860215ef4587303d4f360f130771fc4"),
        (11, 1752521447, "0.1699999422", "11.764704", "0x9ff524d9c6a566a418141c9a0312b24f7bbf2a04f93d50f866ecea95a91adb1c"),
        (12, 1752523079, "0.16", "1.2", "0xe50a060faf34d918524f4e01ebea9da1d0186dac6f1ae5d276b1a717776fb52f"),
        (13, 1752524540, "0.1699999609", "17.647057", "0x777612bfb573cbfdf349b3d60fd78bb8d57f65704aff674ea069f44acf308358"),
        (14, 1752526050, "0.1699999609", "17.647057", "0xe9408d0ad47fc7fbaad86a0b1de304715adeda4f94a5ffda77a89808e0b91d1c"),
        (15, 1752528071, "0.1699998861", "5.882351", "0xb72742075a7c9aca81a59d3be17322e127b26c1d9091903f3ba73fd76ea73208"),
        (16, 1752543849, "0.16", "31.25", "0x5b88a6a9c83bde89dbbf4cb665dabef5ca007e60b3e0e750b62b2dff73970716"),
        (17, 1752545211, "0.16", "30", "0xd4451843c9ebf5f97c9b549802c53d40c4feec4d5651ba15672e0f33717ed8b8"),
        (18, 1752545815, "0.15", "11.63", "0xec097f70b335baa0c9b82791decfe4096ed24ce5ed6dc5ae8604b775893ebd40"),
        (19, 1752545823, "0.15", "23.25", "0x06f1e4a4f9fcab24528b85434ea93191579fe90e552294104edda42f92dd738b"),
        (20, 1752545823, "0.16", "44.88", "0xfd3aa386bb97e62edfe683da2c33a9574f0c247aa2b64d95d9206ebc81baa095"),
        (21, 1752548342, "0.16", "12.5", "0x3522eabaee41dc5665ba2160f507dc596253a65835666807b69a0bce727b7f87"),
        (22, 1752552377, "0.14", "5", "0xb5c1bf81ca77a99fe2fe15e35a097ec73c2380e3e8f644759156bea98a30c806"),
        (23, 1752552389, "0.14", "3.01", "0x6208135b2d618dd3fa7e5fb927a3674111c4a851b3b43f986e898369216a825b"),
        (24, 1752552401, "0.14", "3.99", "0x54b577be1e0acbc1a109364bc5b0b1fd5525615b22887179452d2c1c69743ed9"),
        (25, 1752552403, "0.14", "21.01", "0xf79b088bc80701196f26f405f58761108d94385e35fc769b42211b91c8c8c04a"),
        (26, 1752552407, "0.13", "5.99", "0xdd24c1ebe917c8291e89c55c26203b3e979fc0a88fb889a6f4c58edfae7fd6e5"),
        (27, 1752552411, "0.13", "27", "0x9908c40f4277d3f5e9112a907e82b89cf110591a7a6ae6ce12d580dd3e96eadb"),
        (28, 1752552415, "0.14", "11.01", "0x5d8c721d4dac48f727b8c474c2b42d8d4649a705031a8efa7cc91b6c45fb467d"),
        (29, 1752553137, "0.14", "1.99", "0x69de47cedafebe710fdc87e5468d1f60b5ba90039c28f6d91e2d8da76c4ba7c6"),
        (30, 1752556423, "0.150364", "100", "0x94ab7a3bf921ac8ce2e49b79246a1c583c8a08a4fa986d56e16ef09878228362"),
        (31, 1752559625, "0.16", "250", "0x6c55fd7a7038194912639d7d1f7030e28559248314cf2a5660834dc108623874"),
        (32, 1752559651, "0.16", "5.56", "0xf45414516cea5b5851e3df4b8243ce4a96d932d4778af89ee9888b85304f9cf1"),
        (33, 1752566381, "0.13", "103.83", "0x06a8921a43f5a4b71050bff1161ac16cd0f1a67a5140c1f36b7c5f1c94bf76aa"),
        (34, 1752566658, "0.14", "6.25", "0x09c9086c31840da64e518cefe14e93f61eac9c0dc336466674ca91d139e71f9d"),
        (35, 1752566658, "0.14", "6.25", "0xc6865baa409e05e6d9a1890217723d0ef4466683f99c2f039d0dae114dcd59d5"),
        (36, 1752566734, "0.14", "6.25", "0x09e7f5e4f0d52cecf3d093f7e27f12d62922289b40a234931ba0f18e1c495bbc"),
        (37, 1752566734, "0.14", "25", "0x46e05f9bb36777366464d10467734934dc6d5ec147f18a38ab5d0dc865f9dc7d"),
        (38, 1752566750, "0.13", "22", "0x0b56f147b1b72fce3b8137dd3dd3eb5fa281512f2f51c09b549611b60877bd33"),
        (39, 1752566752, "0.14", "25", "0x1e5032b7c12768a7c8cfd970b02dfc6674f3f186c98bd32d6851c83066e32a87"),
        (40, 1752566764, "0.13", "11.66", "0x7c143cc35217df8e23554eadda1b651b2cdbffcd0eefd1ac3cb8e835ed0a3a38"),
        (41, 1752566814, "0.15", "288.62", "0x5d2f35ab321b989637e602d8cdaa01a5c3acc466b4038ea4bf357f88f016f9a9"),
        (42, 1752566814, "0.15", "206.62", "0xc39e5fcd7acaeee36046f17b5ac76f9b093bc34ea5cf1bbabee92d4bd98058c6"),
        (43, 1752566818, "0.16", "5.56", "0x63c93b6fcb9592ce232d2ba296803964b038ff834a166120d05b1450ea36d732"),
        (44, 1752566818, "0.16", "5.56", "0x7a852198aea8f7ca19a7d24610134325f9c0aac778cacf73d9b25e75f1769f95"),
        (45, 1752566818, "0.16", "5.56", "0x8e0e1b24b1c518d0c16801b7aabc270a59506bb067085491f25bd2c50659943d"),
        (46, 1752566818, "0.16", "5.56", "0xcc21115ad6a7a2546a6ea808aa8cacb63aee7bbc1b5ad3c6bd44adb9d7996c0b"),
        (47, 1752566822, "0.16", "5.56", "0x9c88bac4b073ee5def1c2b986ab633c8f4de625f0eb985365744fd76004b01ac"),
        (48, 1752566824, "0.16", "5.56", "0x7798ea56ccbc1b5f03170da22d7c808697fc30fb524da2d1178ffb9dda1add09"),
        (49, 1752566848, "0.16", "5.56", "0x2148c35a01135e1014438c45b3b0c9a7181f5ca3b9f3bf9fc2d6787b0c8fc2a0"),
        (50, 1752566856, "0.16", "5.56", "0x75ae88b62467e4e7c56f48979600cadf087000f6e6a71921da4ece419efd07d6"),
        (51, 1752566864, "0.16", "5.56", "0x1f9b4bfef98e0509244ba4c7ecac8d1d55dd7ac0e5605f3c546b4f9f96956ee2"),
        (52, 1752567084, "0.16", "5.56", "0xb2b2d963d8ff73d1cb9e2c63052f795ac08f112cff0d3c949d1d8f583f78a355"),
        (53, 1752567937, "0.16", "5.56", "0x882c7f55afc32608d55f4b79105ecc5256c470212a18240951224d5a98b3f571"),
        (54, 1752567965, "0.16", "5.56", "0x3aab1ebddfdbbef6e8588c7102a49610208e17b5a37c5ce85936658022061628"),
        (55, 1752567965, "0.16", "5.56", "0x8162c7e13db3b06a4cf5676e85e7fd1d3c28f5f4862a2f4fc482edd5b064641c"),
        (56, 1752568064, "0.16", "5.56", "0x6854b33bd917d69cac4eebad2434e87f22ead5994f8b52d2dac7bf25173eeb38"),
        (57, 1752568196, "0.16", "5.56", "0x03057396c3f4066205a43690865a42f6dd110ca2e3b2a3c34d0484ccb16305e1"),
        (58, 1752568202, "0.16", "5.56", "0x624276ea6e2c73704ca0f288d8794afe66db0d341a229bbea953975433c56619"),
        (59, 1752568204, "0.16", "5.56", "0xef3571b559696172b3d0732e3d1460cc6c5bf52d383d6717e25396c1312e0ee4"),
        (60, 1752568514, "0.16", "5.56", "0x76ecb427015d8269497f72ce4fd48e6449cabb4ada0c79ce304c8710ba82dbe6"),
        (61, 1752568522, "0.15", "1.91", "0x439fa3c5581315d67edd4522eb5fe0d2041b2e2eb91b9cc49cec82aea0b1c200"),
        (62, 1752568580, "0.16", "5.56", "0xf820f91b2bb7fa95195f56eca4c713e5d1b888171fb4dd8f7f4680b1e4537ca5"),
        (63, 1752568714, "0.15", "5", "0x59771aca23159ddece9724b156c429eafba4e0e14c1f729093e5c7acc98637f8"),
        (64, 1752569749, "0.16", "626", "0x359c03a795dd99fd7e541332e94e7a859f99828aaff7553dea54b878272114e1"),
        (65, 1752569779, "0.16", "5.56", "0xfebecb1d39863dabce2f10e996e9844d90b0b171aee4836e8c982babf23e5ca7"),
        (66, 1752569783, "0.16", "5.56", "0xc029220eb46366441ffa57a8ffdf6e2be636fb30583308778c767f5313f70469"),
        (67, 1752569795, "0.16", "5.56", "0xa75847eb4c720dd034b4ba0b5aef14a43adf33efab9c13305b93f1e4f0ecc752"),
        (68, 1752569809, "0.15", "10", "0x8f3d89c2e7ccf34b665e8e4f6c79f0f35d547476a96a1b16c9e35fbc19e422ad"),
        (69, 1752569811, "0.16", "5.56", "0x60f5092a9c595b0926918919dc77d59af4bca677ec88a1ced7fe064996ee65cf"),
        (70, 1752569817, "0.16", "5.56", "0x16e8a1002dd09e4b81f2efcd670c31a86825618c9da24e82f8791823c38777d7"),
        (71, 1752570171, "0.16", "5.56", "0xc874aa0c4bdedcae878e18fabd4ab991031b9a5b2672aa70d103fc8cc0062968"),
        (72, 1752570173, "0.16", "5.56", "0x1b03fe894c32d30806b545ace472a92976ace35b25585c9c4b85a4d1860d1381"),
        (73, 1752570173, "0.16", "5.56", "0xa1076e93cd00b3900616d04e8c744cf63fd1d5dcef2209bfda6ac0909dbc3c80"),
        (74, 1752570173, "0.16", "5.56", "0xb1f5aa6fc4eabd7c32e4390ec87af0db7ca20cc7adccd360a12f48fc5e7a76d4"),
        (75, 1752570173, "0.16", "5.56", "0xe4a21b54dd71a7111359fe2bc38d5d5e70c945c1f26ee2b0c432b87a509d1dc4"),
        (76, 1752570177, "0.16", "5.56", "0x9efef8fcb7923cb25044acad59336e7eb99ba4da5fe57eb640a771de07614c36"),
        (77, 1752570177, "0.16", "5.56", "0xbd4d9ce25e79728ee9f344b711e83889a885a4f3e1491de355d4820312194a7b"),
        (78, 1752570179, "0.16", "5.56", "0x603beb0936e35bf1c1422c0c00d80c2fe60148fb93681b9d5f2802f3c0229636"),
        (79, 1752570181, "0.16", "5.56", "0x2f1ae4a2457f315f4783dc2cbb94aabbca550213da242f610d1c302bac795951"),
        (80, 1752570181, "0.16", "5.56", "0x6703fe6a5ba59b1dcb7a5e8b4e1a8b5373557905ad8ef3c0b6d7102fc1aed4a9"),
        (81, 1752570183, "0.16", "5.56", "0x05c1e0b01f9bd069d448d2d6ff96daf51a08f6ad0834a1032c3cf885f9102186"),
        (82, 1752570183, "0.16", "5.56", "0x8e1e441d5c030f19cc3e051e92f292746abf2541ef191426782883d1eee012b4"),
        (83, 1752570185, "0.16", "5.56", "0xc79e2b01729648be8048093f6e1bd88294aa094b9fcdb18fbf66b6687d3c8c7a"),
        (84, 1752570189, "0.16", "5.56", "0xdf685b855ea42f561c2cfdcaa576960d90f21fd08797a82e04b1fc6bbe8e4e40"),
        (85, 1752570209, "0.16", "5.56", "0x36689d116d7dc080f313532d238f54f0e365966c1b8d7477f0a703909e8bf063"),
        (86, 1752570209, "0.16", "5.56", "0x978fe7dac0fd10a2df1e47f92cb11deb07f349c466012d7b252bd9cbdfe0c3e3"),
        (87, 1752570209, "0.16", "5.56", "0xc5bf79ac6c1f20dead6023b83be95f77fd300f28906b7f3b8898e69114cc8f7c"),
        (88, 1752570209, "0.16", "5.56", "0xd5522b1be968f2b78a2053d5365cfecbbd88f8657543d6d6ab32ac4a3c99a298"),
        (89, 1752570213, "0.16", "5.56", "0x327176c515d6238cc7b892fa70f8bdbb73e3a155c299ec6690a19d4f5b0b35c9"),
        (90, 1752570329, "0.16", "5.56", "0x3b6a2155a70856daf8fa2fb283b48af4566d2395c7ec400c983ad8275b468246"),
        (91, 1752570331, "0.16", "5.56", "0xeba4361c990017eef84ea007907edb14d87ca8a962662a120ef21c6f674e44a4"),
        (92, 1752570575, "0.16", "5.56", "0x1e4213d7dc5fdc7ddf4b753ad7ccd099abec1b489b85cf482f7d8dc6cddccaab"),
        (93, 1752570575, "0.16", "5.56", "0x4be85a2410970bbc4ee73fea78ebcfc4c54d61a1f647ad1c9fb1a6410fbba114"),
        (94, 1752570577, "0.16", "5.56", "0x7a5c9bc4d408d2f6bef9dcf4451caaf073bf218187f7956cc34ab036f0b5fc02"),
        (95, 1752570643, "0.15", "223.09", "0x73f5145b109b6444d2550b703aad0d269edf2234cad2f10d64e64f592dc74ea3"),
        (96, 1752570647, "0.16", "5.56", "0xcbf66092af9acd71bff164a23b36bfa842d48b0eb37bca71b853816c8c475f5f"),
        (97, 1752570647, "0.16", "5.56", "0xe76df1ad9fd3f23b959159c31c2a97c54f3a394589c6d9017408de1e66dca42e"),
        (98, 1752570647, "0.16", "5.56", "0xfe40289c5b34b1507ba2e0b23b80a48b4a98dc71df3b363314039410cd9a3d3b"),
        (99, 1752570649, "0.16", "5.56", "0x7c7b566cf14000cc448e895910cec9efc66eaf15b05afd4fbd2427764160cd7c"),
        (100, 1752570651, "0.16", "5.56", "0xbee41b02550cae0ee87925861e97ed500151608f363ede3c1989004f05867067"),
        (101, 1752570651, "0.16", "5.56", "0xf3e8d61845702d1de110757aa3e01dc8fb451e5675a63eeeee6e5cdd8da1078c"),
        (102, 1752570655, "0.16", "5.56", "0xddc8c07489911fb3a02a11514b91a34048648f7cfd0ab11212f55f8b753c382a"),
        (103, 1752570829, "0.16", "5.56", "0x37224a0b949accd829ba782a4245622a3c92f568fd85d6f1ab3f2faccf42c022"),
        (104, 1752570829, "0.15", "240", "0xeaae5fd68b9a28aa1511c160ec9e71a37c132824e390f5b534a468aa823353a6"),
        (105, 1752570831, "0.16", "5.56", "0x2d310b4e007657dcc96749c20a2eb87564fda76ad717b48c4b1fb4deda5b32b8"),
        (106, 1752570831, "0.16", "5.56", "0x4914da651e0fd03fe0e44290601b7370d265b7ce92ad11e1e3bf4e87c1654c21"),
        (107, 1752570831, "0.16", "5.56", "0x58e2292f1d03368cc03524f627556d48d65f121561812858c4d673f2ed11fcf2"),
        (108, 1752570831, "0.16", "5.56", "0xbe005edf21f107b96493b4efd72591d49a8e354be0334962972c59a8f3a4fe41"),
        (109, 1752570841, "0.16", "5.56", "0x498cc1e3d18a5aa28c46c09130df15baa19fe0f0c6429fc8f7042ea34f6fbb86"),
        (110, 1752570857, "0.16", "5.56", "0xb527040a8306c5eeea30cc797be089274118224d0296ee18638928c9310ad387"),
        (111, 1752570863, "0.15", "5.28", "0x01853f07df7243a9311f8c10dc48d00f7ffaa4c5052a4d68af5175f1134f54f6"),
        (112, 1752570863, "0.16", "5.56", "0xbeb7dc80382e37046f6f72f1cb719883b7855a58dba72b0887b2c0ed7cda2fca"),
        (113, 1752570867, "0.15", "195", "0x0d73f0d92c58a74e396ca7871c8f68ddfcaacf890f60a9d7f0acee3f488f0baf"),
        (114, 1752570869, "0.15", "39.72", "0x5975d8d95b6a7a43878662f953c16765031a1d4ab8f3f5ddcc4f08cded301341"),
        (115, 1752570869, "0.16", "5.56", "0xbfedf843cd7cda7caf4832341c2bc76f2e139441b4d624c299196cab7b9f5684"),
        (116, 1752570871, "0.16", "5.56", "0x1d82a7d4ceeb68ae0a467d35b099b97ae08279197fb2cc97c776b496a23135c6"),
        (117, 1752570871, "0.16", "5.56", "0x8b9bc91fdf85b90569bcea0f1b9939f1b26d1dcb1861637ddfbfcb7bb23a0189"),
        (118, 1752570881, "0.16", "5.56", "0x20ff0623d3f7d7da9fcedc970ccbe64079573003e171ccb965926394f5431b78"),
        (119, 1752570891, "0.16", "5.56", "0x2fa1db22e0d3c03076a94fabc5e21665733b7e76bc5eca3c7ae2d370347117d0"),
        (120, 1752570891, "0.16", "5.56", "0xbce585cd5d0db1d968e7a648deb2d9ef56397ecd24157f901d482de8ba7e830c"),
        (121, 1752570891, "0.16", "5.56", "0xca55eb11e75622192f27738ce7311d8d99417391cc5c73a054c29f981e07fe0e"),
        (122, 1752570893, "0.16", "5.56", "0x1d8f5f8f1968afd5ebf0785e75ae23c863de4e904ae203977814787d026de2b5"),
        (123, 1752570895, "0.16", "5.56", "0xe2de488ad72a3c550dc2697d5a6adf341635d8eb9cd0e827ab79661fc53fa268"),
        (124, 1752570987, "0.15", "240", "0x79248736090909932a7747d322a8f834d348b1e5f25262101a6674a6cfc685f5"),
        (125, 1752571297, "0.15", "45", "0x90606b6a14c09e55cd95a89a8ae97e27d8811160f8cea783944876bb3652511b"),
        (126, 1752571303, "0.16", "5.56", "0x0359e430d2f57f45bcceda2b904b5489ab01b28358615738203fda23dd5b2289"),
        (127, 1752571303, "0.16", "5.56", "0x8c94d242e6dab082c9da11eba47fc5e612edb23e34c52aa48ff35bb9449fa047"),
        (128, 1752571441, "0.16", "5.56", "0xe60423cde4c7878685013b1d2595d3fb4a81f78ef28bc800352c4bf70245c2a1"),
        (129, 1752573067, "0.16", "5.56", "0xcea87c5eeeb8b1684782ccf14a5ada21d970235cdad35a035e3bfa7d67b29bf8"),
        (130, 1752578841, "0.15", "344", "0xe98497ddbbf6669dba1622dd1a4f009e50a4bff1f892bdc2281227961926e376"),
        (131, 1752578843, "0.16", "5.56", "0x525303a65d52707d50c40874c57d66a53e1d06ff5a495774c1c0a275093ca45f"),
        (132, 1752578907, "0.15", "1.41", "0x65819b94c9f93a3e2eaa74f5974dc17a7e4904c79b9f6c4aa040238bb1c3d454"),
        (133, 1752579313, "0.14", "18", "0xf71674de9fcb648240146af0b85ac934e854c2a4e79807b8f2f16231621564d2"),
        (134, 1752579317, "0.16", "5.56", "0x1342ae560e598e40ce4fffa57f014bab3208945057eae0b4cb071ea304dfca54"),
        (135, 1752579317, "0.16", "5.56", "0x1b3556e3fa645d797b9f1e9017d0a9a550a814c7ad382cd898627330d15709ad"),
        (136, 1752585737, "0.16", "31.25", "0xa1486fb85e0081da94295718ef5aa382c2d44af4fe43455efb9b44b8456c1b73"),
        (137, 1752587561, "0.1499999757", "30.866665", "0xe799c9ec26dcd3c54aef9dd00aa4a1c5f81f1e826e7eea53f22ed1d8e8329b05"),
        (138, 1752588081, "0.14", "3", "0xa3f477d2dbbdd0056c7a1fff40d5f961e039098627585107db2afe245ed86789"),
        (139, 1752591261, "0.14", "26.09", "0x82541c4f79c572821df7e65f28b733cb2fb486f524f016be61ee27ac4a541e6d"),
        (140, 1752595398, "0.15", "121", "0xd364eb7e6d8005ddeb338ae7ca5d78dad5df4c13500efff11ed788a17abb21a0"),
        (141, 1752600151, "0.16", "6.25", "0xcfbcc612db60e0b10aed010dc081c8e74d5ac616f4712c003344fe98e3238ad6"),
        (142, 1752600177, "0.16", "6.25", "0x83f649bae1d2f2737b9fac61857bbe3b6e9f0e42b71d16ffb7db56b777ae7e95"),
        (143, 1752600783, "0.16", "15.625", "0xac8334d668b5641899d4128cf5bd239bc776662816792615f84d8469427d08c8"),
        (144, 1752603351, "0.14", "5", "0x942dfa4d33255dc4ae8e8fa5ce656c67d35dec43793cf16610449521df247a9b"),
        (145, 1752603429, "0.14", "86.99", "0x3ae34fdafb052456b69afae099a7eaa5b8b4751a677034af8762764c22950b30"),
        (146, 1752603523, "0.15", "23", "0xd0f48f501c88b2d5a465cd3458090a1b69b4549870f481c284b4097c1ea29d02"),
        (147, 1752603796, "0.14", "3", "0x53ba29e3ef12a043d6a7ca1c3f9ccba84910c78747717f9195e361ad31a96b03"),
        (148, 1752605766, "0.15", "2.96", "0x2741c8d6f814188aed9f05f39ba77fda95f5f8e1455b1959a3a244f2313d6b07"),
        (149, 1752607434, "0.1510290268", "662.124375", "0x0cd3bd2be4ad7a0a51daf86e5807020284770d0a74b226869abe9af41aa69d64"),
        (150, 1752607556, "0.14", "167.24", "0xe13a4f891f7e6e88438c87b987930feffc5f74534d00fcd505d271a098d6e7a5"),
        (151, 1752607566, "0.15", "24", "0xf05a2c7ccbde43cd2302f88fe16f0c6d8fc9888e6ceb3506d9e494ebb8692a6d"),
        (152, 1752607576, "0.15", "16", "0xd3917e737aca24c63b1505f033aa17c1e11c8ce425a31bb4898ee6d502a2d6f7"),
        (153, 1752607578, "0.15", "8", "0xc87c57764254cb4de463721a22b2f186be165fde63cc45a200a319df644ee23b"),
        (154, 1752607582, "0.15", "5", "0x29c566431ccdcfb6bbe9ae5d3a0cb65dee242259db605b60da1a290c2e8746ca"),
        (155, 1752607588, "0.15", "24", "0x9e137f708d07a20d6998d5d3f4edf528c63753f90ac5679c2f37fa6f20c80f9b"),
        (156, 1752607800, "0.15", "820", "0xfdf741440ffbf53d478acc187f55c274de82f033a7c09d94ec3433d53f635b7b"),
        (157, 1752607990, "0.15", "165.03", "0x2856a087d6bec9ef4d45809ede923cefd18396df5c9e2a80b9eff3b0e9ea76bc"),
        (158, 1752608596, "0.15", "209.97", "0xd39ee1934211fac6183113c3cc1a79dabfabebcae6dc5168c74614c11d50149d"),
        (159, 1752609236, "0.15", "56.65", "0xa3a2b21c254dc27328305291713a8b9d14476e0d86f855f109519a7a79ac2007"),
        (160, 1752609236, "0.15", "10", "0xdf41b18c4ffe625f7079947d246460f6687b56bb4d84abf37709b11f6d2c0687"),
        (161, 1752609704, "0.14", "5", "0x741f54e147113a03c239f305d51b5013c86d1fef9bcc324ab5fdcdc3eabb81b5"),
        (162, 1752610290, "0.15", "30", "0x2b34d16d6e3762b17e82e5a6a5415d213f9f59b82c5a535d5d029c6cb653a191"),
        (163, 1752610426, "0.15", "1000", "0xa7ac46e8aa5c6455387abfc9d389640b87d1dff75e86c1260d516ec8db3b3e8e"),
        (164, 1752610580, "0.15", "20", "0x46937fac35447364f0fbe462d5f5c0eec00319ab2b069db7af587eb71609fa2e"),
        (165, 1752610662, "0.15", "1000", "0x0cf333685bf42983dc1317620d761237009c0fb91922c8b66ecec94d828c1a61"),
        (166, 1752610958, "0.14", "9", "0x0d35c1cd208268393f1342d24a65e227f0fefd62ba69ba36d08a70f56e4dc725"),
        (167, 1752611158, "0.15", "5000", "0x0d205aeed86cd9408b82f321ed5df36c00906fc765dd4ab854d69d6d2d8546e9"),
        (168, 1752612409, "0.14", "5", "0x53a555a849b00dbe8eee5b5ce19b61d8715650a2847757a9cdccb5f493266587"),
        (169, 1752612489, "0.14", "6.25", "0x15a04a41703e894edf0b0163d23c72bf3209b9312b29ee3d0b6329106bc44ff3"),
        (170, 1752612845, "0.139230075", "8000", "0x6f64559f7b1d657b13649222bb7b17ac2d7a65ac1b49628867aa9b94491859ef"),
        (171, 1752614923, "0.12984", "2000", "0x0521d0e21677c8d101d4a8ece2f4daae0f87b693efd3b2bcd3ad5838a20e8e26"),
        (172, 1752616433, "0.09", "5", "0x79ca12611ffc3fb6cf256815c7a1d128162c52422aa6b594a6925e0b3d56bc75"),
        (173, 1752617261, "0.1212121212", "165", "0xbd54b29a2b6e77da697a1ccd0e55bcba79ab5e00c19365c2ad6423e3496e3128"),
        (174, 1752617277, "0.1299999932", "122.307691", "0x7d6436b20561e417acb872f9ba4d87fbdbe5d13a5b728ccee0e92a525d1a391c"),
        (175, 1752617289, "0.13", "9.69", "0x783adffd2d5b0d6c47dd93a38cfd89c6ffe1172efe3231a51ad1ed5bb0a4af71"),
        (176, 1752617305, "0.1399999925", "109.285713", "0xd4b2e9cfde71534c0cc2762fbe22a6c10fde89035a4b433376de11f277a99d39"),
        (177, 1752617351, "0.16", "50", "0x5950607bacc97413720b61d3d02bda6079d0ea2ccbed55e9fe456822820afb51"),
        (178, 1752617479, "0.1799999755", "27.777776", "0x8a557ab228ba25cb348e3a46614465bd29afcdd5adfe0d3d4692150abf0da51f"),
        (179, 1752618177, "0.1699998861", "5.882351", "0xda2fd3990620138833df32d57c5c59c705965f212515d0324ca01710c3e51301"),
        (180, 1752618501, "0.1699999764", "28.764704", "0x779a502f07f68065e706bb5852e445abe9dd2a910ab1491394c605d582ada249"),
        (181, 1752618521, "0.1819414504", "225.45", "0x9fcfe25922184b841fdb4a127519a2f8066b55b3dd5bc6ce31ee453c66d537aa"),
        (182, 1752618523, "0.2", "4.55", "0x866314f20b5e4ead317c946248819df5e6a98691bfae786ac8526b2e07684344"),
        (183, 1752618549, "0.1966082533", "88.45", "0xefd34dd6d62ba6505c9d78e13e88af4c861e4a6ce71281dd87b6c1702603bd25"),
        (184, 1752618557, "0.2", "4.55", "0xa1696ffcf07ede1c2dea2a34c9f152325ec041a68cbd98451ae6d15224876a45"),
        (185, 1752618813, "0.2", "10", "0xf9e4a75a95c8111bcc14312b6bc678e2f36efd8b63116b10dce051adf3a5c5e2"),
        (186, 1752619297, "0.1699999759", "29.411763", "0xa30e116f3d9efe24fc2ba92ec6caafcfcc3198d2432f1cd69e165ba84990eb66"),
        (187, 1752619299, "0.16", "50", "0xb2e11b69f745fc211fbc1c73d7d4ddb858dac59f57b5f9260e8011025abcdb8a"),
        (188, 1752619305, "0.15", "61.54", "0x4342cd634538384c96972a606b5d2c3e0930e1d110d71eb5b5fe686f297d1e21"),
        (189, 1752619735, "0.15", "106.24", "0x22397e51d5996562190f264a66c4d85a9eb67256865080908a92073efb0bff1f"),
        (190, 1752619881, "0.17", "30", "0xba9a6a10a34384fed39a9fadd6a8da235800bb8331ff6ac590a3a0d1ba29f0d5"),
        (191, 1752621021, "0.0699999363", "14.285713", "0x6c2872ba9969c60431d23dd76c972775263bbe0c9a93189069054fe69e885d2e"),
        (192, 1752621053, "0.07", "165.71", "0xd22c97b38a2be202933c90be73a0bfd421c8a2286c88efbfc614cfa0cd54ed4d"),
        (193, 1752621441, "0.1610154318", "99.058822", "0x6e3ab9fce9d1eb69ee555fa4bea2d011f4c08b7941fec5b255c34884e853f267"),
        (194, 1752621629, "0.2", "62.94", "0xfd33d063c93896186e82698ad2697e698fbfa048a3cce1009918dce1dce9f5d5"),
        (195, 1752621719, "0.21", "285.12", "0x38fe861b54e2c6518d6aec8c4e4d8fc7785012638df33251bb133b5e79773210"),
        (196, 1752621833, "0.25", "75", "0xd7a4c80d10b13b7f8fd7505f4a509da4d8f391e06cb60147979e6adfa5f201eb"),
        (197, 1752621847, "0.24", "12.5", "0x2aeea8355e1718ffcbbf9ecfe1c0aed55d8f5a4876df1ede1b555b8edd061499"),
        (198, 1752622013, "0.2146341358", "55.909089", "0x7a48d97f6b2a4134e1df7833355e73c0abf63c7ff53b7c58350685ad3788374d"),
        (199, 1752622061, "0.2199999968", "204.545453", "0x0c947986c095a418a15b7e5d2bccec2a7d82074583e5129421e3699efe28434e"),
        (200, 1752622235, "0.1225500446", "235.29", "0x09636a6ff76b8a5d778df5513a6a7dd68c42492cb021c6b42b6f26a9eac27987"),
        (201, 1752622395, "0.1376133652", "209.5", "0x450ecc08dc349112a8749278e49fa94675c5708b6856b7d473b054c2f416cc8c"),
        (202, 1752622987, "0.1199998992", "8.333332", "0x31fb9f557e9c00eb05b15a1c45d22369b3a4470338c5f7edd7c1b534f0d72ac7"),
        (203, 1752622987, "0.1199998992", "8.333332", "0x54f2df40c408ff553dcf90d76b5c288968025930ee18bf5e28b1d668ba19471e"),
        (204, 1752622987, "0.1199998992", "8.333332", "0x739348f228b10509082506ff25b8ba3531254234cf6ddc536840dedcd8ae6dd8"),
        (205, 1752622987, "0.08", "48.74", "0x7c212ce87ed053cc02ec408a8ebc4dc2344ba5e7404bb4f7d046ab73a97f3f55"),
        (206, 1752622987, "0.1199998992", "8.333332", "0xfeb8fd1a3c8a42f1ff279b8cd64543567861607c922d4e2d11e755608ce2d772"),
        (207, 1752623117, "0.0969405561", "51.578", "0xd48a9ee6131d523b193435b034d6be1ed5c52efbad40faba0ca17d4ef3d33522"),
        (208, 1752623139, "0.1", "60", "0x681300d237e87e123544781533350c8026307bb2fc221536c26b5196c5144029"),
        (209, 1752623181, "0.08", "50", "0x43fc271436a76234286dc704972d5b3500fe3b19b7c2452350daf0c9414b8c2b"),
        (210, 1752623183, "0.1023550725", "55.2", "0xd779da023b3ad7b02a89352902d90c129a0c5d76252d31f7f6851183ff715726"),
        (211, 1752623287, "0.1130298113", "53.083332", "0x71c5479edbc9d2925a647847660afe9042f6f5de426371189d8c0b2bbe155f71"),
        (212, 1752623421, "0.1199999808", "41.666665", "0x3b4e5b9e5ea10cc1ee10a1fd42b564d5773297620087f3a491871c9ae238fb5c"),
        (213, 1752623559, "0.0899999804", "44.444443", "0x7280959eae80401f54c142730a82dd09df7b705e4a40bcd070f532436cac8078"),
        (214, 1752623589, "0.1023255587", "39.090908", "0x3127afec9d73e1189a215994e919292f021a042c5ca35d8fba330ebaed0e79c2"),
        (215, 1752623603, "0.1099999032", "9.090908", "0x0b79c0ec6a001c9f1d962f41cfd228752231805342b264cd3cc9a3e57fed5a08"),
        (216, 1752623869, "0.09", "35", "0xa81d143568845096d3a1e8cb8865923989c286a17184cc112b5d32f75ae956ef"),
        (217, 1752623873, "0.08", "2.01", "0x4d5d6002e9e15350c18c29ec5604fa8b77a509749991333056ae84dcd4f413d9"),
        (218, 1752623921, "0.09", "16.99", "0xf3758a2026059f5141723cab50be99d388db3c716075b7e90333e4153707f9fe"),
        (219, 1752623941, "0.08", "53.03", "0x7138e63a55ac05ba18157c3b902708b6317772286573340b01a93b4cc9a2bbeb"),
        (220, 1752623949, "0.08", "10.01", "0x482fc21bb87965bb2685acdf9ec417f9a88c21804d27d294374f5d03c6f788a4"),
        (221, 1752623973, "0.1", "16", "0x4a4d3da99b32d104b54ab93a2004dccee30653d9e5a12f279ed2c8c976b1f8ea"),
        (222, 1752624033, "0.1", "139", "0xd95da96de5502a564ba6d77efc3417ac1f9ce8d00369aa2fab91ee3762e9e74f"),
        (223, 1752624119, "0.09", "22.46", "0x10cd4bcab11aeb19a920d4f9a44465b37b8f05d9214aec5df5aa51d3fd3e40ee"),
        (224, 1752624151, "0.09", "1", "0x2c16ccc3a7e7206f98a61885aae27eb7ed4346f5a2ece83e8f156b1bac7a659f"),
        (225, 1752624169, "0.09", "1.09", "0x1318e2660c879ceb2fc957ecef1d16fdf6bd8315a08a0396f096be7b344e008a"),
        (226, 1752624181, "0.08", "29", "0xcf910bb1fbe66828a8bc1a9e562d3245f3a81ad8d39659281f6de9f158dcd255"),
        (227, 1752624185, "0.08", "10", "0xa8acdb1cb8def4c134b81add2e1e953d65e3267dcfa3bd7189973a89296245b3"),
        (228, 1752624189, "0.07", "9.87", "0x6e2d78006e0215e8f04d8a1e5ff430d36f58213f5d20bf51a977c8904ea4394f"),
        (229, 1752624219, "0.08", "20.99", "0x566590f94b913a46a99828af1a49ac4eef0fa7c9fb2366fa1d31c9ef3237bf44"),
        (230, 1752624261, "0.09", "16", "0x57315cc05b394bf3ba1a960f0ee55a4696473fa8e1df0c626c0a8d4d8a979d74"),
        (231, 1752624379, "0.07", "446.12", "0x3b83fe0e472abdf39e9f5e9a4258c2f8f16d501122e4776e2ca5aafe57c326e2"),
        (232, 1752624453, "0.08", "16", "0x0fff39e525b6e920815838b4a65d35e15a24875310a876763424a853f580a2cf"),
        (233, 1752624513, "0.06", "5", "0x2961c7174a62aaee34acee3d8c19291be7202daeb2ee2ce99bfe0cbf8a3e7f4c"),
        (234, 1752624567, "0.06", "110", "0xa654152c5b4b850b7f6036c21823d10b3df09cc7ba0768edc0a1daa9bedb1321"),
        (235, 1752624853, "0.078099", "100", "0x525129669a474b1da3492e285f2b4e8f2c08f6a15de08547992aaf492bc49846"),
        (236, 1752624885, "0.08", "100", "0x8fa6ea91aa1ea20939e111cc610badf704386d691a87367198f85881052d1263"),
        (237, 1752624937, "0.06", "50", "0xe06f872883c163983b0857c7cf9e232d5f98f0552c63d57190a4b33c2cb8902f"),
        (238, 1752625113, "0.08", "31", "0x475d7e96933c685128ca67ff69908e767e8a103f4c4ce0f8dddd3d569a8309be"),
        (239, 1752625183, "0.08", "446.84", "0xd428b53697652873396e952d4b012fd06abdc0bb8410390d1fd47ed6c744500e"),
        (240, 1752625265, "0.054", "12.5", "0x571669a0149ad913927f7822908b683cebf2622a4d1f72a6854c148d88852774"),
        (241, 1752626663, "0.11", "50", "0x27df09a5ca551a616779e5c0259dc64f4413b95b65ae5ad4aa96f32b64f3794e"),
        (242, 1752626741, "0.1", "10", "0xf68868d5229f308d53fb6537ffa5117cc0a7f24a98d9738e5af41b123b9c6b96"),
        (243, 1752627397, "0.09", "12.5", "0xe8e9a57a713e9e2cf2b7ef6bb492892f0fcb9c123e5017e346777ea618172006"),
        (244, 1752627703, "0.08", "25", "0xbfc380b6165a13d24baf535d9aa74ccd3bc13b88f392b95066262a66cb9c7aa8"),
        (245, 1752628003, "0.12", "102.28", "0x8fd2e329401afc2468fd4e6adb60b755fd33d6f1b41346f1ae7e19eb74d96a92"),
        (246, 1752628017, "0.12", "110", "0x4344eafa35f033a55ff84538455bfd0b1bfc4d213a92c88447a38d608fe04bb6"),
        (247, 1752628297, "0.12", "25", "0xf8300414611afa5ef046a80170a569d1e01917869f1feed7ec7760eec5814765"),
        (248, 1752628425, "0.11", "63", "0x583ba52e6224759cec2a1a2e4b60613fe512172874dd497702eb06e67de717b5"),
        (249, 1752628425, "0.11", "219", "0x791af4aee992c69568a14888304d510ea1864eb294104dfd92fdc742b61f78a1"),
        (250, 1752628525, "0.1299998986", "7.692306", "0x8f66318753fad28af171245e6352efdef2bc64b6cc6b0d0dd89612c9abc120a3"),
        (251, 1752628601, "0.13", "42.3", "0x22dd2601a328e64ca9e72c076166ebd017c1f3f9bcba2fe32b77d5cd3ddca3cf"),
        (252, 1752628929, "0.11", "31.25", "0x39c6afb9c5aafb1dbff08bf5cb3b3864edaf2e12a75c8b57c8788da503fdf811"),
        (253, 1752629133, "0.1199998992", "8.333332", "0x0d02048f213555a96ace9f49c4d1c7df198891e73f44e0a24ac3945982695f39"),
        (254, 1752629411, "0.1", "200.93", "0x514c93d0a0689bbddd00a6a0f5f4dadbe2b9878e2ee49642cad38bfbc27102cc"),
        (255, 1752629523, "0.1364993602", "879.125", "0x67133a999177ef0e2eb40a5298d77c1ef51113ea6f524e4827c0e25f8bb91339"),
        (256, 1752629605, "0.1199999899", "83.333332", "0x52d2a5a4358dd21293a1461b00e63084b299776ec44293ecaf72e343a8525cf5"),
        (257, 1752629737, "0.11", "25", "0x431a4fa55a2f3da6495a98376511cc50e14e1ea81c44bf5f83468ab5594c7e27"),
        (258, 1752629741, "0.11", "99.28", "0x230ca90f96030e67c2550077ac8f2754ca7054306c15d56fb69085a9d808102f"),
        (259, 1752629817, "0.12", "30", "0xb03a609fa789be69fcbb7b28b44267befd6cc2445e3d2f5206d46d92e06904bf"),
        (260, 1752629963, "0.1", "30", "0xbb9d4389da288a10aeb926378e0272142c1fd9322ced98bc6bc78e198821bf6a"),
        (261, 1752629991, "0.09", "98.66", "0x5eb0d7d29d32c2a8e871bc382443a4f8b6009a88663f4827b12168fbc4c5034b"),
        (262, 1752630037, "0.1299999769", "32.846152", "0xa95d2fd3ea48752382ed253b8157f06fdcaa109cbbb4c9d3388f6bae43a6e0cd"),
        (263, 1752630045, "0.08", "5095", "0x6b8a6f98d46bebf6a44e8c482dc91fb2b106819b7043449d55f45cf182dc082b"),
        (264, 1752630275, "0.13", "10", "0xe4428ba8d68831ff3ca1db9de310bcc3d8921c99765204fcb5a147a82d68b43d"),
        (265, 1752630279, "0.1578811959", "633.387646", "0x19a92f2b9a4b4ec2f331bb55f985d25d3c4b9903a7d2147a46d29cd9a2042b07"),
        (266, 1752630291, "0.1475389571", "81.266665", "0xdd2cefcef3319e8863adc27d0d59a4ee206898cc12b5cf623fd86f1d31d5542a"),
        (267, 1752630517, "0.11", "50", "0x86bdc284eee43a5e60319d477a790458726e0d0e9ef564004b1a085ac20fa4c6"),
        (268, 1752630537, "0.11", "5.67", "0x48eef3cff31a27054153e016bc0d43aca714aeded73a65346a94cc24d9b69616"),
        (269, 1752630563, "0.1", "75", "0x7f53615e53dcef313853293cc8441ef5d876aaa10245219381698c97bf6e31ff"),
        (270, 1752630563, "0.11", "72", "0xe2b66b28694ab2a042316b9f7a35e0aa7f7601b569291ceddd13a5677218bee5"),
        (271, 1752630651, "0.1", "140", "0x02e34a6d4d30cff99596ba504955c14d8c5bf58d1f2996dca1c60612fdd98d75"),
        (272, 1752631125, "0.11", "29", "0xb8de4130457a8d3fbfe5163cdb647f95ee233289bfd64d67722bb1dbf98e8f7c"),
        (273, 1752631369, "0.09", "472.28", "0x40c8f8ccb176a089f43486de740fe55246b0cdf95f087d803795ea7b7d0de4e6"),
        (274, 1752631387, "0.1", "10", "0x694835e26ad305bdbb25fc95e4f39461b811956ad407f467898f9f84eb05ce33"),
        (275, 1752631397, "0.1", "45", "0x7b713d6056987a7fec2b3c66bd3148aad924dd5441b31a3ef57ab385a1cbba01"),
        (276, 1752632449, "0.1", "52", "0x4033a99f6e5c816624f49f1af359f26fcd599c927b4cf2acbcb3754eb5a76da7"),
        (277, 1752632473, "0.1099884733", "190.929089", "0x2134ab95290148d5685b071d20d9db89d631ef432012ebddeaeafd76c4b2a4b6"),
        (278, 1752633703, "0.1", "19", "0x841ef7ab37c8d291f53d0d2e156e61c2e99e32eaaf38243abfb2f6bb7bcb6890"),
        (279, 1752633947, "0.1", "10", "0x5a750b844f68282870a04229249706530b3e393af9d33c5f896b0c96102f6dac"),
        (280, 1752634456, "0.09", "200", "0xa2c9ef776d63db8fc3dd3480ceb192bd02a2a1b3c815b8555b6a845659d7c6f0"),
        (281, 1752634598, "0.09", "21492", "0xf804d4249c11123e8850c5bba91c5f63ed368fa634d747dfc8bb322f061e7e8c"),
        (282, 1752635132, "0.08", "121.17", "0x7dba325041fc49798ff054c6be9629a89efc12fd0702421d3ddc3553f32e7906"),
        (283, 1752636174, "0.08", "121.18", "0x943b0e0f83637fa03d778b86716dd3486e4448a15ecadeb526191e4ec922c0e3"),
        (284, 1752641658, "0.1", "101.4", "0x0fa6425d51aea7db759740dbaf1877e7b2b35528de85af00d3860588503087ac"),
        (285, 1752642338, "0.1", "1200", "0xb827f239169174178052dc019e9a788cb944ebc783def9260e34b0a6c75dc1f4"),
        (286, 1752642440, "0.09", "401", "0x61c3447c8153c531a79a260d608450332f327fb83479730cd57422ada5462bab"),
        (287, 1752642504, "0.1", "600", "0xa2978e336a816e4c6d6949a8d86829daa0c0ce624b8761604d4b2a874444ddf3"),
        (288, 1752643645, "0.1", "10", "0x333edf7c8ee63545956552350b30a6e2098180751bc4e2464d60312b533c3d9e"),
        (289, 1752643683, "0.0839089", "1000", "0xfeaa71b2fe4a0c74be1eab88e851b705966c6642fddaee50cc15a5813943ecfd"),
        (290, 1752644198, "0.1", "10", "0x368b943d307f9b3e632092e2dfeaca7b0d1712b5621e421bb72212190066cfde"),
        (291, 1752645787, "0.1", "1000", "0x9c6d75bfa2076597f17fe558f9a0b32f31740fc15eaaf70eb1e666a8e67634ac"),
        (292, 1752650303, "0.09", "18.46", "0x542e2a7884659320dbab8e6f371fd602a41c5cf9fb98069e6b5a24d0ece7e9c4"),
        (293, 1752650971, "0.1", "9.99", "0x85f6349045a558991c251574b265099d1f6d94dcbf0e93d73cfcc7d5526e38f6"),
        (294, 1752650971, "0.1", "1624.46", "0xd0cee1d32b9439fc6bae1829664e305571e988cb77873b10f4672901d5aa88ec"),
        (295, 1752651117, "0.1", "74.19", "0x38768983cd1cb6863525bfaead0d1cb6a62453d7307384f37373e2e56cfdd2ff"),
        (296, 1752652859, "0.1", "6.08", "0xb86ec69ae7c8b2d124dfa927a378bad05ed2ca39d4b3e0b587d0ed78697fb372"),
        (297, 1752653011, "0.1099999766", "36.363635", "0x9cb654f28bda63d57b98909ee753bd52fd0ff04c8ba9335a44d6ca8d8110b8f3"),
        (298, 1752655263, "0.109999999", "909.090908", "0xac66201a2ce13d89c86514849a86f57d1c1fea77c42c313d8079ba94288550f5"),
        (299, 1752656199, "0.1", "5.88", "0x62826c43cec38ae171136282d5030072094ee4976ee860035cabdfa599034e8c"),
        (300, 1752658465, "0.1", "32", "0x34deff6a05ce51ef89b5931c7c0b8e0adbbb47fe693280fbaf549f32e65c665c"),
        (301, 1752663578, "0.1099999685", "27.272726", "0xa2167bfdb9dc9f969db69cdf1a73ac28f40e429be4d577736b2b33992979fa5c"),
        (302, 1752663590, "0.1099999815", "45.454544", "0x04b0367e28eccbdba038b9649cfdda4b9b2b5e1d740561bbbf19f97bf2d595ca"),
        (303, 1752664021, "0.11", "50", "0x46b57d7a79b111ecd6823cfdecbee8a7f5ec39ffd8514930983f02a414ac47a7"),
        (304, 1752666019, "0.11", "100", "0xc8764d14abac0e6030a6d25ad55c05727df1a691611593d900ad6dd9da6e61c2"),
        (305, 1752666143, "0.11", "300", "0xe486adbb65a6b840a77505a324afce0046f38e526d060109c7a5e29e624a5a0d"),
        (306, 1752671970, "0.11", "20", "0xdbb1b360bcb8e6fd1de393617cf6e606e08f55c478cbbb48d00a0c5ec1dc5f57"),
        (307, 1752678190, "0.11", "1500", "0xebbdad4c24543ddfd3f2ae4bcdd4c2092c4adf6795d69ca8ef2af888334e7b8b"),
        (308, 1752678648, "0.11", "20000", "0x44d610c0ec3463448b1c3eb0d2e2394f60ea96f6fdcd48e45852b2e0f57ef99f"),
        (309, 1752681106, "0.11", "404", "0x33137d3779a0d2c5fa88bed47c2bcec5eab1fb142bd97c19070ceebbd022d405"),
        (310, 1752682644, "0.1099999871", "63.636362", "0xf24239b188b057134b6efd8c5b300264e622615fa6239fa1ed87270bd58db860"),
        (311, 1752685680, "0.1099999985", "544.545453", "0xa7ba9f5dd722579dbe4c4d3324324c6800547751af510677d7f16c8a74196105"),
        (312, 1752685824, "0.1099999994", "1409.090908", "0x1e1481d95fbe3b1a93cc52870f216b14d0d08ee9700d7691d0aaf1b26036bdd5"),
        (313, 1752686734, "0.1099999815", "45.454544", "0xff0c60a1efa8b430f6e58e93588375a3ad4de60963b79e166b4487ca3a5aa06a"),
        (314, 1752688544, "0.1", "879.12", "0x2ef6059e15c910828ac1c355fc5c912de74be30f00ab6a62749ceeb5bf691e64"),
        (315, 1752690492, "0.1099999213", "10.545453", "0xb5092dfb46c6311d3e8cb79d0fa848d4291991e23d1649da13e2f255d786b28d"),
        (316, 1752691174, "0.1195309533", "15000", "0x5c1d6a47f1739023044accccccce1fece7573dcfeadd05fbfe18e395681cc423"),
        (317, 1752692078, "0.12", "50", "0xcdc3143492a4e70173fa78534935c04520d3512ff2cb703d8d9fb5ea8aff4ddf"),
        (318, 1752692176, "0.12", "3.8", "0x84eb881476faf106316a7c55d1412bb7cdf8ef5a6887702d359806c3aab19369"),
        (319, 1752692316, "0.12", "30", "0x6ac1b7a364b72d20ac054c392572be0f5c99671e0847fbaeb4715b62ece041d7"),
        (320, 1752692330, "0.12", "23.28", "0xcfc1097d82b463f77ae09b819e8e02893b7601bec437e2bc01e530801d0b0dda"),
        (321, 1752692746, "0.12", "261", "0xd10e6beb95a0f1343362833deb192a0b24e658a5de8bfa86c1be171d3d683d6f"),
        (322, 1752693458, "0.12", "350", "0x3ee26b62a98823f21a8b4e53c03d038792a2d9df6703b7fd8ee2903ebcbf75d2"),
        (323, 1752694004, "0.12", "20", "0x9005d591d8f8ca8766a18f111cc4105e288a2037daef01294142c5d5884c1134"),
        (324, 1752694834, "0.13", "42.86", "0xb1d680261222092fc0219da039feddd1017e2b18c5caf03c9cd0801275184129"),
        (325, 1752696860, "0.13", "10", "0x2316ab3b80a88378388aeff54851999d38af52d2fab948b084ac145520df9c33"),
        (326, 1752698150, "0.13", "8", "0xebca8de48137ed46c6545cec8b0c0ad34febc178a24db595d2198e0ea83f28ef"),
        (327, 1752699632, "0.1299999789", "38.461537", "0x71d358287abd85d474d729bdbf01342b4cb46998a717c8be8932bcf718623735"),
        (328, 1752700912, "0.13", "124", "0x60ab77f5a8ff838bb32e1aabe98f5ee53bbed8b88e32f6cef17b880701055a0f"),
        (329, 1752701008, "0.13", "0.53", "0xe1cec7ada43df22f0abc40d395f8c950a2d95719f66b04f739cf49c72b43c445"),
        (330, 1752701568, "0.14", "360", "0xaa232f602a23d2cae9ac3d84ae4264a75b52901a0802cb313399d7a697ddb51e"),
        (331, 1752701908, "0.1410411622", "545.16", "0xef4e9f61db7987de92f19e3f6eed54526273ed1758fd5a7b1e851b20dab2e9e6"),
        (332, 1752701942, "0.15", "12.2", "0xc4a06efe05950d3d0137d83b08274a9173487fffa36569190cb0c5284c20912d"),
        (333, 1752702260, "0.15", "736", "0xe3a4c3415378f2acc59d116cab1ecf76ca02b65c6c7d4fa8a460a84d59f047a3"),
        (334, 1752702280, "0.15", "854", "0x5e71f6b560aa8c0105e5740553952dab1d9af6db8bbeb3636fde572446a83e92"),
        (335, 1752703060, "0.09", "30", "0x879b2a4d5415f12888f16a9d311e11b52605d679dfb35dc8ab4a5f8b8b1e5c75"),
        (336, 1752703124, "0.129999975", "30.769229", "0xa0bc3a647ef9e458c30260367a637b86b8e4483c24b778046726e27bfede81aa"),
        (337, 1752703128, "0.13", "94.23", "0x1771f5d4f1babbedc43ce4f5b28291bb7061df5816f625644e9ad8d01d72354c"),
        (338, 1752703128, "0.13", "246.23", "0x620735a7adaa463ee72081519db2d20c741a4accaae0b80e813a64cbcc32d619"),
        (339, 1752703140, "0.14", "20", "0x3ca469ea805b9b71d272140986b40a3094ab7ac95d08f08cd24e49bc14e232cb"),
        (340, 1752703268, "0.14", "200", "0x0676646e846d67a28eec2dfc81321137aeccf412992d3087363cfc9087fbf452"),
        (341, 1752703480, "0.05", "50.54", "0xf37c7fa6df285211c023daf5143566c98614b971d358d186d7662607d68d135d"),
        (342, 1752703942, "0.12", "30", "0x419517e940bc29b981ed36c7222ca7838abfd5a0689532e466499e28dad7a490"),
        (343, 1752704012, "0.1", "51", "0x86fa68f812ee4d76d6ca5321a9bd6f2eba53ee690f05b4dade688b448514b79a"),
        (344, 1752704014, "0.02", "84", "0x90bae0dc6ea45bce14925ca80fc060f100c7242c5cd6a5c39b3b360aa69d793a"),
        (345, 1752704062, "0.01", "149", "0x9ba63c7c335806bdb639aaa1214fa8fdd29ccbd3c5cec9060fa15398b1582d16"),
        (346, 1752704120, "0.02", "57", "0xde391cf64be1bbdd893de8c6fb06ccf02ecd03a4e7fce8b9fc9806623fc62610"),
        (347, 1752704364, "0.01", "900", "0xa1becf08ca9ca8347bcc7d944ef9febcaf5d8ae446cce38468a02ebab6f84c83"),
        (348, 1752705776, "0.002", "1000", "0x057ba5774a0a92f1316890e989e3f980f3f7a53c4ff4442c4671f26185510083"),
        (349, 1752705828, "0.0029913252", "33430", "0x356aea8075f20c3b8a388234906f0b324377863dccf695e2a1f2c9b2a174371d"),
        (350, 1752705902, "0.003", "1666.666665", "0x1f7c62f9c2a6b56351c40321fe8f1769cf0b634a2a4ae4a7e3f55ba43875a383"),
        (351, 1752706472, "0.0017198336", "1442", "0x5c1a3551811d554b72992a463123f194dc6ab2f3fcf58042913daa66c5b11ffe"),
    ]

    fileprivate static let retained563320No: [RetainedTrade] = [
        (0, 1752516056, "0.85", "10", "0xfd0580b747cbf608207f44588920e4b801e7b941a76488da8ba8652b20a19d24"),
        (1, 1752516060, "0.85", "1.15", "0xa8bdfc9411209ca41f5002994afd61add7390c6768f3ea0d1ae2c092d3e2709a"),
        (2, 1752531497, "0.84", "105", "0xfeac7256f5c31c8915c270e769ee1989923655db383c9dc30eaf482edfe522a6"),
        (3, 1752531593, "0.84", "5.21", "0xabe9a3fe5796d7ef34f297c1b136009d5a3618cac76e883d5907a0596792ae7c"),
        (4, 1752531593, "0.84", "70", "0xe10f41e645e1c7a8f1182d7cd226d44d2304c00e376faefa1b61b0b97472fb2d"),
        (5, 1752531597, "0.85", "1.15", "0x623cf5c9b32e6758ca0f299d7344ef6a7ab3d4986733a46c4d71c19ad65c5368"),
        (6, 1752533235, "0.84", "2000", "0x21dbed5be3c8ed6379cc688820c29686f952ef6699915cc01cc64280584741c9"),
        (7, 1752533243, "0.85", "1.15", "0x5dffc90b2cc19e05de71978f00ebb3fcc4b209ef3eee31c7fa54c27ae83cf191"),
        (8, 1752543221, "0.85", "13.37", "0xa937d8125d26fbb36c63eb3d126fc5660af618f7f04cccdd2cd0281736677471"),
        (9, 1752543221, "0.85", "10", "0xf2d5121297b80c1c9f4aad65bcae2ecd7cddbf49d0d8538f0db804820e4624e4"),
        (10, 1752543223, "0.85", "1.15", "0x2ba07b814af763c2cddf87b032609bae005ff1a9f28d9cb2b52ff67894c4b405"),
        (11, 1752545215, "0.85", "1.15", "0x0af8521b3f8729aff059c4e4d80d498c2e29c417e2507731f0fadd1775d01a2c"),
        (12, 1752545815, "0.85", "10", "0x6af0492f96bb2e9a42009bcee9634c513c6bed66cb67ccc9ba2875f46c1bf885"),
        (13, 1752545817, "0.85", "11.63", "0x8c46de3e1ba6748a7d5f3d6a78523a6d35265394e492e96d1a3299c0d2895862"),
        (14, 1752545819, "0.85", "1.15", "0x88a6bc208f0901488064efa3fa87c0c5240769dd2305b0d762234303d5cee5c0"),
        (15, 1752545823, "0.85", "44.88", "0x8e197a182898f59710e538c7cccdf9882e73d84a3c67e3e46fb4f9eabc97cce5"),
        (16, 1752545825, "0.85", "1.15", "0x086c2ea89269c0432276532aa450c8ba505db9340f5e96501b7250fc376f8995"),
        (17, 1752545825, "0.85", "11.63", "0x772d7f6a8be4c41c4c8655b2eebe79b2df798435fe8203a0e9a53c86cc3b69d0"),
        (18, 1752545827, "0.85", "1.15", "0x028f5f4bb61e43dfb480967ce4ebbcc855e14e2e781afbc3c97674bf72f58c58"),
        (19, 1752545827, "0.85", "16.67", "0xc2d0b081a7fba2e1c04647e0a0873cddcc0d4658b5d46c691824b0929fb23118"),
        (20, 1752548344, "0.85", "1.15", "0xa7846b5ed92ffa1907636dd4b875dae06cf570791d06faf94bb3cdc318778e69"),
        (21, 1752548828, "0.85", "370", "0x5694e31e33dde200784891addef226b3e752b33ea0db7e38e6b1f9f7b7c42faa"),
        (22, 1752548830, "0.85", "330", "0x8691365a5089642df3f970c6bcaa8c91addc2037d1a854a7acf8a22bdcc9557c"),
        (23, 1752548832, "0.85", "20", "0x23ffdbf25315cd3f8405198e93b42646fe980854962cd2084e9444a049a5b5d2"),
        (24, 1752548832, "0.85", "1.15", "0x784410f2d06ffa05474a06e4ad53d55480523db30d05c4885b380197ae4e2553"),
        (25, 1752548834, "0.85", "20", "0xe2cbee4b7e8c2d29efc2b34b9eb3a723e480819d0b1dcae698fd9fc4f31b3b5e"),
        (26, 1752552353, "0.85", "2220", "0x20b86358f0b3dbb681fb9a53f6b4fda4feb611579a99c49a404940908e04141e"),
        (27, 1752552355, "0.85", "8.92", "0xea881621d15014d3761c1c9b5ce1d650f0bc949b25b411d84dc1938d483b3759"),
        (28, 1752552355, "0.86", "1.14", "0xf3a25b5245d9739f952a63be4f7f70a517dde7fa40619ac5a4ae76f67212cb91"),
        (29, 1752552377, "0.86", "21.99", "0xb560559cb44c553c1d6b0ac3c99b975ce0f7ab3eafa35677382a1611a793e5c5"),
        (30, 1752552399, "0.86", "25", "0xad0bc46cf9f82b49fd45c89d96e4fb71525ff70f3c0c0db78de3c4a23c793928"),
        (31, 1752552431, "0.86", "9", "0x3f7049d1db8df90a828b0c50c2373ffe921838c1a3dd2c74954ad43a9bf6b074"),
        (32, 1752552435, "0.86", "8", "0x6842b7ea1fdd0e0716e5ee206c400f20dac46d3055528d792bbf17ae3eccef22"),
        (33, 1752555149, "0.87", "30", "0xd68b48e049f6b70ce33cc5206031d0c8bbefe06cfbd9e0f8d29f4f866e1ab443"),
        (34, 1752555151, "0.87", "37", "0xa7d052abb838e81cb6bd2b8ed4dcec2b7a275a7519ba331e10ba16db4f43f409"),
        (35, 1752557959, "0.8699999983", "5.747123", "0x1890d83f6946e65935b382163ec7a18de4e291d596e6d673069694eb36359089"),
        (36, 1752559303, "0.87", "66", "0x8aba34f4273a961f3c9009337882abee3c31b370dc557338ef38a478bb5615dd"),
        (37, 1752559647, "0.87", "100", "0x558ee150e4925922b2119f617d0171a11998c830eab35dfe09a02e986539b5fe"),
        (38, 1752566345, "0.87", "9.21", "0xbad996ff412270d08482a34ef4ed281d297e962e361236734da8d41b57ed5fef"),
        (39, 1752566381, "0.87", "30", "0x101d8f3cca4cc64c6205c31440513e6860e3150b9765508aa86a49fbd595b926"),
        (40, 1752566381, "0.87", "39.99", "0x1506a5b349079bff222582f070d6ff02c267361d6e6d11ce5992dccfe33049cf"),
        (41, 1752566383, "0.87", "66", "0x00a9ccc49a2ee3dd2ca625e2b7e8922c674c054166ee47865599b50ad1925d30"),
        (42, 1752566385, "0.87", "156.25", "0x4669e3b64ffd8c9f4ae933a195e931b45a891befe877f20d560191fe17209b3a"),
        (43, 1752566385, "0.87", "53.75", "0x58875bfd41a90eb9ac385f017cd933eafe12839e1a767cd5921af24beb4b2dd0"),
        (44, 1752566385, "0.87", "66", "0x5d57ee7ae61d6ce85299a4b0725c210e1abeaa9c992f53303871099a2bb7c426"),
        (45, 1752566654, "0.87", "40", "0x37f90e8c0c60cdb309ff4d389995257b049235c3ad00bb2e8a2910987ed0d8f3"),
        (46, 1752566654, "0.87", "40", "0xcc3432132549de0d7810a221d94b08219b028ec9fb37d3742574fe55385d9d92"),
        (47, 1752566702, "0.86", "24.99", "0x6d77e0f282ee9738b4b051689941c4afddb75804abfd7750e190d2475d7f54da"),
        (48, 1752566730, "0.87", "18.05", "0xce3e1e8082e7e91b063ff49b3c6c2e5d66d6671c3c0ff39502f9920473925287"),
        (49, 1752566814, "0.85", "39.99", "0x5186a092b0fccb825c3b9cf9f39faf3ed015c6a4af9872488760dee5c63e42ab"),
        (50, 1752566816, "0.85", "102.22", "0xe5e1f0227184833508cfef93d4515a203f595a76640fcecbfcafbe92e8185ec9"),
        (51, 1752566818, "0.85", "12.92", "0x528d93afc5db911afed416393f2833597f2ab3681559bd56bc672ee3e7e58361"),
        (52, 1752566820, "0.85", "13.33", "0x25c6165db9852accfc024767f98e6b683a3f11db4aee24c63c828672128e5e40"),
        (53, 1752566820, "0.85", "5.01", "0x83ef9e232ae17b2014402da0bb096bb6001d77eb893cb788eb27cdc2dc341d32"),
        (54, 1752566822, "0.85", "1.15", "0x0a5cc4b13fe18d3163bfa94712bc996bc1d184985e400c78cb26eaa1dc4e0f58"),
        (55, 1752566822, "0.85", "1.15", "0x16f3da8eb8122f687ee1db673eabdd759fd2ca07060a7a833fbb6dcd4d67b335"),
        (56, 1752566822, "0.85", "1.15", "0x32d2255043bb4bc1ac3cef4d7b95338e373fe833a25839d6af7a2e463e30136f"),
        (57, 1752566822, "0.85", "5.56", "0x5fb4b62e21975d13af94089e255af1a40492c22de58a88155a9e2c93364480cc"),
        (58, 1752566822, "0.85", "1.15", "0x67058806c9931ef02a9047288048309f07f45cf6c2c4ba84466e128b881dc05c"),
        (59, 1752566822, "0.85", "1.15", "0xbb2e8d12071ecf649f20ebfdea11dd818b9d6e6cdd9405c379ada7cd9f0431e3"),
        (60, 1752566824, "0.85", "5.56", "0x73974a1ac7d44cecbb2af71b8464bb29d90fbab821a660bf40c7b89648878b30"),
        (61, 1752566824, "0.85", "1.15", "0xb492550171de568ebe91faee99c209d484ddf5f18d965f4985192d916daeb6d1"),
        (62, 1752566830, "0.85", "1.15", "0x38a8233a4e2a79a1ef19d6219565d5327be191e2d126bc9dee5cbfb427b841bf"),
        (63, 1752566834, "0.85", "1.15", "0x0159782c70d9bff4b92e80f7c13cfe5a5bd9061ae4cc2f50f8e9d67c5c41af6e"),
        (64, 1752566834, "0.85", "27", "0x36778ae2ba2e9c5c1f857572114e9cf6fe014cacea56c7881c6289d592112774"),
        (65, 1752566848, "0.85", "27", "0x641d4e82583608cb4362735adf446549c38744894fc6339fe4b13d4f99fecee1"),
        (66, 1752566856, "0.85", "5.56", "0x1403817d50b6ec7a78c060415ba87ea74778b5ef4ba3158b70f1388244387eff"),
        (67, 1752566856, "0.85", "1.15", "0x5ec9102b6b417331384663028506cc85fb70ee16f866198994851569fb7dd3bd"),
        (68, 1752566860, "0.85", "27", "0xf7284d081a8af898e40fa92f6013b723e181f96761cd4a055353c4d575d4bfea"),
        (69, 1752566862, "0.85", "1.15", "0xf4d6bc918c373808507362d25d64a55ab21030f8af66981bbdc7307783ed7aee"),
        (70, 1752566864, "0.85", "1.15", "0xd3d7b95e61cc8393b39992a331babf40c47e478f5b8aced07468934ddde2a256"),
        (71, 1752566868, "0.85", "1.15", "0x545b7dcae273f64fc085ac305ddb9f9694998329c2cecdcbbbcdba27fe31c737"),
        (72, 1752567082, "0.85", "31.25", "0x1660767193c544e9aa38b59f5acc62f5bc7a8ff6298f2e9e8e6bc693cd8c6835"),
        (73, 1752567086, "0.85", "1.15", "0x4e061aaf8bd132ab2f227c5be89b7a9b50638faa1962f8c6b92f68dcb695a096"),
        (74, 1752567086, "0.85", "1.15", "0xa62d1c6f90b5c4ba69113694776eca2ec6dd09faf33a690212bd2d279c47ace8"),
        (75, 1752567933, "0.85", "70", "0xe780b479eb115b6bf1d60fd95f4d237d482def672ce40b3a7696ab8599f6ac59"),
        (76, 1752567937, "0.85", "1.15", "0xc999e54356411c6e91990a96b9ae3ba7fd948750c833dabbed77de4b8267f78b"),
        (77, 1752567941, "0.85", "1.15", "0xdf7f3f1d88edecf1d9953fa48b4d13892fe435af41962c8578ade6554173451c"),
        (78, 1752567961, "0.85", "66", "0x6957a23dc4ee5a15c6ea0052fa68a5306c417b2228b0e83176e5c6c99afdd98f"),
        (79, 1752567961, "0.85", "15.28", "0xc6f3765f60c37232adee630ce440c37dfc5a014a925404af0a8cc284d00e1e20"),
        (80, 1752567967, "0.85", "1.15", "0x5683ca939b074bb0ae7690d1e507bf278a6bbc6802ad4a5e881dc3158cc83564"),
        (81, 1752567967, "0.85", "1.15", "0x6d29f6d4aeec957fdb6faf89aa2c61a8a50a7ece29a39f3abf60c6674ebe0f0c"),
        (82, 1752568033, "0.8499999998", "518.917646", "0xfa08598ba2b762dadc7c6bd71eabd714bbaa85efcaccc23fe574e714943e2ef6"),
        (83, 1752568080, "0.85", "1.15", "0x5763b963b4450825bd3890b2440c8ee916e014e0cefdc41e74d6ed8d1c65bb87"),
        (84, 1752568194, "0.85", "23.8", "0x4d3b4fb018948198ebe161e3cf60b8dcddfed7a7a9b0793bf69d5a3160ab001a"),
        (85, 1752568198, "0.85", "13.34", "0x71bcc55bc39fedd05ddce974b0cb3d5ea1d3760bd144bbb57711ac6a8a3e3ebf"),
        (86, 1752568198, "0.85", "1.15", "0xdf51ed0c869a117ff1cea160e26ca842a9f0490f49ab246aefd057369978e5eb"),
        (87, 1752568202, "0.85", "1.15", "0x8627d2d4c02a28094e907d7144dd5c08b27e5e3e86eb93e0d6c879a35e09a163"),
        (88, 1752568202, "0.85", "11.12", "0x8e35bb5352d1c2567b9015666e942e34369425a38b933f27f2736fdc4fba1f0e"),
        (89, 1752568204, "0.85", "1.15", "0xe93cab0156f0f3a3d43dbe15cbbd8a9e9d73ff9ec1baed0199e3411b282b2d89"),
        (90, 1752568208, "0.85", "1.15", "0x27f1e6e527f45519098a51812332c7ce64781424473441a20715c4d0ea969006"),
        (91, 1752568208, "0.85", "1.15", "0xc916d4a560200af65dd47824e03287adbbcf66a9f24ae36a8e3b1ef1bd14447e"),
        (92, 1752568512, "0.85", "510", "0x315a7917f301c9cb3d094bf3e3c8a1557ab175dd1aac5a546bcd87e8baa2b8ae"),
        (93, 1752568518, "0.85", "1.15", "0x37455a3eb077b7478f91b9b018c4b3428c6d97be06a6723695a246e6712e3f78"),
        (94, 1752568518, "0.85", "1.15", "0x3ac8f5fadd172a4ab4230f844fe43a467024ce7b58ec5191311578862ff36e43"),
        (95, 1752568576, "0.85", "30", "0x8519c22921b5dcb67a961a6d631a8a8875af5985840c01621cba8abfe67e1974"),
        (96, 1752568578, "0.85", "1.15", "0xf0512b726098c98f2d89c86340a42d17acc4b998f0f58ceae6fd3bc4caa92317"),
        (97, 1752568582, "0.85", "1.15", "0xf0c807fca5f9f81c0412f524ad87c6264091a4ffa9386f24b3bdc713d207fe8b"),
        (98, 1752569693, "0.85", "6.66", "0xc2e7241e27c7cab2ca1c9a53ab108561a153c554b3143a646d51e1e9125f2802"),
        (99, 1752569775, "0.85", "66", "0xa44c216c7902066a4d685037496092a541ea3ff857f2e3a78fa2387f7e3ce523"),
        (100, 1752569779, "0.85", "14.29", "0xaad70e2f83b9fbd363729557a3cf350739fc25cbfee12a4362d99b39b49a9771"),
        (101, 1752569791, "0.85", "190", "0xd8985a08771b5a5edf50fe6948479a985c2321cd566717172a52d52c01a6ba92"),
        (102, 1752569813, "0.85", "5.56", "0x77ec99f614226ede7e54a2dd56a8f50f4e08dd79d5fb60f3d551c293e1fc3a35"),
        (103, 1752569813, "0.85", "13.34", "0xc6323a4572c20b8bc22d40b6f8a46d32caac73f8c5e39b71cc8d93584d110517"),
        (104, 1752569817, "0.85", "5.56", "0x74c92db78f91173a1e3412d8faf2ddd5321c4316c46fce4992204a6ef3c11b37"),
        (105, 1752569817, "0.85", "1.15", "0x9f9c6adc9eef1bf390bacd62e0c0f1edec7ddb5752223e4616f744db2c052f19"),
        (106, 1752570167, "0.85", "15", "0xed374bc665d7c61fe13b861ad0a621910a29f638c6b992bd6844a0c49422b1b7"),
        (107, 1752570169, "0.85", "170", "0x7306270a08d249666320cd9b7661d8a0ecc377533c6f089fece624b20485248d"),
        (108, 1752570169, "0.85", "66", "0x76ff011bb109f96bcdb4c63eeef90ef1b30f96a31dff15ae4806e6b10fa01386"),
        (109, 1752570169, "0.85", "15", "0x7e2598692cb0bbf35bc421724f79824736b78baa204a7ead7a56fc13386d2974"),
        (110, 1752570169, "0.85", "173.19", "0xbca16460e1c5ddb3fa19e1edf5fbbe306f417d2d970af9628dfb7693d3bd441d"),
        (111, 1752570171, "0.85", "5.56", "0xce804d664fcb33ab03b3d6e64b33922ad6f6ae9e7742a0448384002ee1c505d1"),
        (112, 1752570171, "0.85", "5.56", "0xd7fc5c2866b0e04791943ae5c79667bfd7ddfaf605d87cb4aaf3772879e0a8b8"),
        (113, 1752570173, "0.85", "16.67", "0x1140a0f15a671a13fb4d6c9cfde0b26287bb8a2a1b2c357e918e12c7d05aa60e"),
        (114, 1752570173, "0.85", "16.67", "0x85c037d4a6d5190bc3db329be6e45af22efe57ff892754a502e79254028565dd"),
        (115, 1752570173, "0.85", "1.15", "0xf131282d89fab998129500b7a4fbc0ba7f19dd7d203469d747d5c89d484bd507"),
        (116, 1752570175, "0.85", "5.56", "0x2003afa37871cb885f52aa316b905c6a0f32bc89beaa047fd6335533f59c3092"),
        (117, 1752570175, "0.85", "5.55", "0xc5e1b324140a3cbd587c2e6edc6fa4909e6e3f775d18f4d2ba212bf6563c8430"),
        (118, 1752570175, "0.85", "6.67", "0xf37e5a4783faaaa3c79dc430966a0fd7fad4baa887a7a459037baa6569f08662"),
        (119, 1752570177, "0.85", "16.66", "0x969bb9d6a486c875fa90df441c1505b9a73780fe380570b6fd679dc74a439066"),
        (120, 1752570177, "0.85", "6.67", "0xb995d2bfe32b4be8ff0d3fdb35cf707d84551b671b49cea3588ac6b589cbdb51"),
        (121, 1752570179, "0.85", "5.57", "0x0d51bf6a69d456950a13f741ac96342043e605a6912cedbeb65a824e00a14414"),
        (122, 1752570179, "0.85", "6.67", "0x3a67a112dc7de8808bfe27104841998d45e231d331e06d0d79146056ed5fb58a"),
        (123, 1752570179, "0.85", "6.67", "0xac5931340e7cb5dbb637f608496c4cd44f81520e8922f18957392b2d5a194b00"),
        (124, 1752570181, "0.85", "5.55", "0x3f90333a0f2da79c8434bf8c8cfea0674115c22498fc62d86464307a71d87963"),
        (125, 1752570181, "0.85", "6.67", "0xfea6419292d5c822f1c92b23f01fbbe642d1ccf491c986bd4fd45cd2c0b933a3"),
        (126, 1752570183, "0.85", "6.66", "0x16f52f51da1c48a04abfb79e1a623f0415769bebcdc6140ce15878d943987327"),
        (127, 1752570183, "0.85", "5.57", "0x3b56b52cdf64bdee5d5ab691b68751413b27ef112bd8f780738fec85581c6a55"),
        (128, 1752570183, "0.85", "6.67", "0x7d26c37ed78357187eaf1d902f0ba09de6e52afbaf8e3ee6434789a1aaf13e55"),
        (129, 1752570205, "0.85", "15", "0x092566a6701eb80478f6610b38af87200bfbe3782d86a25b07b42a5e64b98bea"),
        (130, 1752570205, "0.85", "150", "0x0eca4f27029ed7c48b933fb2525f941c27452a70dd1d7cc4c6087f3d7e1c3a3d"),
        (131, 1752570205, "0.85", "300", "0xbbd31a0b8b7596ef0c9d2a432a75f62b3e38e3d33705fbf9ce798ebe76efd939"),
        (132, 1752570205, "0.85", "15", "0xd267d60b72c6187765be92401174a612fb76124756148b8f97322bdf64c4fd6b"),
        (133, 1752570209, "0.85", "13.34", "0x74cac720e27f2b3252256443664be050722fa1ed79d00310e52de4297f8cdb03"),
        (134, 1752570213, "0.85", "1.15", "0x3b55e56443838916b6ea1514929c2b4e421f4af1278132a2fb432b92413a6c88"),
        (135, 1752570327, "0.85", "66", "0x5201164b33bd5793f05cc76555ff3ce75cab38574422ee4e292a1f6508201b85"),
        (136, 1752570327, "0.85", "10", "0xdabbb09ae2e5a82019d6257732270db29f5a59ca0e0ca9795a539ab2aaa2fdf6"),
        (137, 1752570329, "0.85", "1.15", "0xde49066078f4836c5db3cbc9ed3fcee33328f150628f76e4bae07916c9264715"),
        (138, 1752570571, "0.85", "133.28", "0x7d60eee8dd54fe5a4dc903ba13e2150288d20064fd9acede98bbd4046a83e997"),
        (139, 1752570571, "0.85", "66", "0xf4b22a9012de113c1de29e01adfd30b0fe8c370ce2f18d8f940e0ff1f1a36008"),
        (140, 1752570575, "0.85", "1.15", "0x3392cf4c4104934645fa68c15205aede45daa66ac8be75858669ac762ef63650"),
        (141, 1752570575, "0.85", "13.34", "0x9185a4ac267d1655a6e9d7df4af25f0af9a0c3cc5a2472120da4bf93dfbd824a"),
        (142, 1752570579, "0.85", "1.15", "0x06f9e8c488a5b44d49424591580bfdbc531c2302094a02932b2db84313a04833"),
        (143, 1752570643, "0.85", "1000", "0x163498de716b7342188c1f3b9a0ac73263baf9d71b686262bec764da1775f74b"),
        (144, 1752570643, "0.85", "39.99", "0xa6858dbf8a78269033d97e106429b2794788fb3c0e4565bbecedba415e53ba2b"),
        (145, 1752570647, "0.85", "1.15", "0x1678aaa67d0d2a6f35033e6e6c391e49a2d4516d44fb27e6b9b2b3922af9f5e0"),
        (146, 1752570647, "0.85", "14.29", "0x285e61b7ae4b87ee7d310d1df0d681770ba3d33622e648055afed7ee5edf88d0"),
        (147, 1752570647, "0.85", "14.29", "0x7fb918305cb79afdffd945fb808227f98d973a771ca03297dd2302d8c091ee39"),
        (148, 1752570649, "0.85", "14.29", "0x9e158efffc31a49691bae5a05b15ec0ca80a2c93fc75aeb5db7a53a5d315ed21"),
        (149, 1752570653, "0.85", "20", "0x6e579026927107939594212d21f0bca1fe744232a0cbf2640180b5281b63318b"),
        (150, 1752570827, "0.85", "66", "0xa429be59262b48d30780759d2f865f1a1bf2680374503e60a86b6cb3599ce6a9"),
        (151, 1752570827, "0.85", "329.94", "0xc2815bfa5ed84b5a72f3510d1e6aace42dec073a1b738388c6538d877d4832b3"),
        (152, 1752570827, "0.85", "39.99", "0xcb95c2227bba6b1f6b44718d17b948d0aae4c34a2bda555f63542a403cbe5ab9"),
        (153, 1752570827, "0.85", "452.13", "0xfc60cea8e2b9818d0d19084e5aaf24065f5a1699944fb6bef2d242a43bb20e35"),
        (154, 1752570829, "0.85", "5.57", "0x8052956b86f42a92d824d82adbfc441f8d88417dbdb61b349b61e7e51cb9a630"),
        (155, 1752570837, "0.85", "37.03", "0xb9411d299c6e5ca836269b464c27b74a8a3f1c7ce94ef0f7beea7877ccb0044f"),
        (156, 1752570845, "0.85", "5.55", "0x2cf496efcb8499d66ae80179ca5c5a953f6efc6e8652529fe69de1e9939a4d1a"),
        (157, 1752570845, "0.85", "4.15", "0xd0e2451d182f2522b1253d01d83c2efdb83e94831df3fa859517ca86d9f6c152"),
        (158, 1752570851, "0.85", "1.1", "0x6470bbf15c07a6d898af09ec7489df34380b11c71ec1f0f4adce3b98629c3cdd"),
        (159, 1752570855, "0.85", "6.69", "0xe32d0cc2ce6a58db2481cdf4482742522b2e811aa6b4695b84d43aa8e9714fb2"),
        (160, 1752570859, "0.85", "95.51", "0xd536fce05d1bd77c0016dcf1dd24ce60f3ae156705a78ae49e4e8e4bc9150f01"),
        (161, 1752570865, "0.85", "16.67", "0x1f79ba0b18bf79a10a6dacdeeed92fbd3f6984ad3ae1f741b1cac03cc4f24e12"),
        (162, 1752570867, "0.85", "244.7", "0x2a5edceac42df452161496b7d082b31994536514c8dce9c598dacc90570349be"),
        (163, 1752570885, "0.85", "16.67", "0x5f1a89425ac832df972dbddf08f24ce8ebaa14fd6b69ce0d13a0518980775cd9"),
        (164, 1752570885, "0.85", "27.46", "0x60189febcd4476fb5625498220c70eebbe7200c0410a23614c71cfb96d250e81"),
        (165, 1752570885, "0.85", "16.67", "0x6e197c251e55698ed764577e7cc0886911a2e13dfe5e2290447226a52db35e99"),
        (166, 1752570885, "0.85", "5.56", "0xbcdc1863f60f45bf086ec3e6637f007996821f94bb32bfccbbe18164f2390125"),
        (167, 1752570889, "0.85", "28.44", "0xe52041804e880b632b4800d99b1bea0ec50ff12856d65f07f9f81ea00fa124ec"),
        (168, 1752570891, "0.85", "39.99", "0x8748ff5e6aa243654f8fa6763fc60c7b7ed36bf217a2113ec576f6efa7f72db6"),
        (169, 1752570893, "0.85", "15.98", "0x186877c65cf4d45c2d7b32e52e9dc77b02762e0057227bb7b6081309b7f5481b"),
        (170, 1752570893, "0.85", "3.19", "0x42966c01efbb6a523401fc346a25328040cb8c3da31b1d4a0c430b82eb32660d"),
        (171, 1752570899, "0.85", "62.48", "0x0ded971d84461426fa632657cf691258dfdc51accb899d770a2480abf1ab3673"),
        (172, 1752570899, "0.85", "9", "0xb4c62699a61cece5d35b3ff3232e76db04da6bf373a8558b3c1959d16daff649"),
        (173, 1752570909, "0.85", "242.29", "0xd2e70f16d9414d135908bba8354a9e73b4c318734c355e7050f4a607ed786222"),
        (174, 1752570917, "0.85", "60.34", "0xb65459f2eaabdbde07a819c719172fc04491043014fb67dc86d2896e90f525db"),
        (175, 1752570923, "0.85", "6.77", "0x79fe7b1481ce26ba570883b0341cb07705ee969b7aaf45285223ca9bfbb8317d"),
        (176, 1752570933, "0.85", "271.67", "0xc2560b8b88c9f4428a6a1da99f862ae1b8a3afc8bc87a5de7914f0ecd7a9d2ec"),
        (177, 1752570939, "0.85", "84.12", "0x35d2e5d83a8a1373c12d7bd9998656efdca7a0a405847834a24932c93a909b55"),
        (178, 1752570949, "0.85", "15.46", "0x0ca0ec4076b427270fbc423302e00f6e64fe0efbf09203c7b231857bcb8f3e91"),
        (179, 1752570953, "0.85", "39.99", "0xcfafb4463205b5fd18e9da3713881749cbeacb5090ccc8e87ca7ca55f3dee5d9"),
        (180, 1752570957, "0.85", "1.74", "0xe586e0a262aca2d6140c63ddbe8b80e125416ad09ab96746e99522c7e4b98690"),
        (181, 1752570965, "0.85", "242.52", "0x1886703fdce729b53010a2a4fec73f3c5af52df63725e1330e64fb68dfc5dddd"),
        (182, 1752570973, "0.85", "5", "0xdcff1121279f911f78515e904623df7f9357cbe346755c60544f9c4a26d2efd5"),
        (183, 1752570977, "0.85", "6.66", "0x2f206340a63eba75c62a0f8572cd30d6764b3a4421f244eb99a3e58a15560baa"),
        (184, 1752570983, "0.85", "110.73", "0x330f8f3d23d0c07062ce6545f13808f04bd9b0175ad79f1db492b5caa397dbeb"),
        (185, 1752570985, "0.85", "10.02", "0x03d5857187a92c610351461601013eeab2453fe743537f65f33bfa1b080cf2da"),
        (186, 1752570989, "0.85", "112.27", "0xf3d7e78a55277757642887a0871d4dc66fd84046e364f2d7c76ebbceab59da49"),
        (187, 1752570997, "0.85", "14.41", "0x6887827de587b5f5845211d62ea756a127d0ed93deda0f325595e9d17a68d7a3"),
        (188, 1752570997, "0.85", "661", "0x7a809465c08a2e0545f842890b4e990b7318257ca08006e21f751e1d1b9a1c86"),
        (189, 1752570999, "0.85", "1.15", "0x9f673c5eb7bdfdd348cc20668371efd050b6065bc43c381a52993ad6c308f7e9"),
        (190, 1752570999, "0.85", "190", "0xcf0c65c6b84b9eda60420d5ca398d962e76c914b8912cd1920de447a8ce0f71b"),
        (191, 1752571001, "0.85", "1.15", "0xe19e74a0dcfc6aadfcf6690423739d96b24345c297308a0389946f5794b3f2e4"),
        (192, 1752571013, "0.85", "15.55", "0xbf5f7a45fd06e3bb0a72aab1b4bb4952c7fe936ee81f1158a0930a96a07d7115"),
        (193, 1752571159, "0.85", "66", "0x0051a5d8bdfd2073d714525656c3be8e09c5941113958d451cc17913671c1db7"),
        (194, 1752571159, "0.85", "250", "0x23f91c4ed570b0ff17956173aba18e4f391c3e04f566be7f141ddcae57f53887"),
        (195, 1752571159, "0.85", "253.36", "0x3f8a70dc4fc819084722b6de274562bd5cd65b1e0f1539dcedeb206687a3d66a"),
        (196, 1752571163, "0.85", "1.15", "0xd4c368b18ab58d42ba78913f838ee1a361f863732d29642502a67e8a56fc7cb8"),
        (197, 1752571165, "0.83", "4.1", "0x6d9c657de968e61b0158c5c84511f07302ef3e348d508fd204b112c8757940fa"),
        (198, 1752571297, "0.85", "40", "0xf6a59b5100b4affd585b187f922ca69d41b0b999bcd4b5165e7dc60b33b9e99d"),
        (199, 1752571303, "0.85", "1.15", "0x5d142cd463f53797ea025a8e9283881e9af77ad0b65f6f005af9a24ede5eba24"),
        (200, 1752571439, "0.85", "13.34", "0xe5a5ba37e45edb593ed72f23d0b18ce8188bbf89a058c0fd98b75468c696085e"),
        (201, 1752571441, "0.85", "1.15", "0x06b3243694ad457fd879b41b69c82f76c371d19e61fcea671b74661aaffc7c74"),
        (202, 1752573051, "0.85", "1101", "0x55bf4e70c28fadac8bc6b7591f865809ad855a55d8849ea996cca4f256aaeb5f"),
        (203, 1752573065, "0.8666383255", "14.873561", "0x54086daf32c858b74e5c5d86e63bcfdf9244cc767278ec19db228771e058f0a3"),
        (204, 1752578907, "0.85", "4.15", "0x3d82f4baf2c964f542eef154cbae6c8902c22de9abe4094dd61577f194fb3cad"),
        (205, 1752579313, "0.86", "17.99", "0x0d2b684d2bae6aa54fdcb8db7fd1f608f40910e6db41f06fbce4520c49123e05"),
        (206, 1752582529, "0.86", "20", "0x1b5d65cfa932291cd355312d5053d663e52df356f5eb7b3bcc7235278c7c5ef8"),
        (207, 1752588041, "0.86", "9", "0x5d3adb04ef402e080adbab8e450b7d31852b1a741c17be51ed0fb7051b116273"),
        (208, 1752588081, "0.86", "9", "0x019530ac71655a67d2e30de0ffc3360870e223f6c2169c29216529f4f24daa5d"),
        (209, 1752589031, "0.87", "92", "0x183bdd22db6393594fb0c95fd21791db02de6a9cf80f4aed5ca612f967ef7692"),
        (210, 1752589811, "0.85", "4.1", "0x502705e191374097d49d82ca3ad737885531557003b685dd2943da83014ed27d"),
        (211, 1752591253, "0.86", "66", "0x2b9cdb7620031fd23fb6ee494b178d9e24e119ae0935772a4a596fe225f80de9"),
        (212, 1752591255, "0.86", "20", "0x44b5c970c80def72079116d8b5248bc7ae3806a9322f336c68f1ae36559f1f00"),
        (213, 1752591263, "0.86", "26.08", "0x4141cc8df68b09c05f57d01189ee8d915aa114a78d0e1e8bcd7003fc774ab10a"),
        (214, 1752598682, "0.85", "15", "0x0dcbe49e6fc7601b5c1c509df466cf4e20875b8e5e1a63b1f5b4c4e627be6a91"),
        (215, 1752598682, "0.85", "200", "0xb2bc072a802bf1d1221cc2a144c9b26cb7da02f935b36cf9180fe3255072ed69"),
        (216, 1752598682, "0.85", "15", "0xbef3a18280c11935f63101f283190b222f93f8afc31082d8d17f4434cc17f1fc"),
        (217, 1752598686, "0.85", "1.15", "0x406a1d581b9334f4e3acb10c9ef555bc341afd44260a607d3778c8c988e71a17"),
        (218, 1752598686, "0.85", "1.15", "0x6a45bdb8eb0654680cf8a02e42e3512d8b876b51b208023011addf39a7311f16"),
        (219, 1752598686, "0.85", "1.15", "0xa16963e822f66a4ae379995c4648dad8d2ef7b5125cd69fdd4959a5bf8a5d825"),
        (220, 1752598740, "0.85", "125", "0x8b86b6602e2a3f4ebd37c3d2885bd6d3cce5f5140a737d6d920e0c2885d6701b"),
        (221, 1752598742, "0.85", "1.15", "0xf9fdac5a0556cbe9c4559373f6fa54cfce09b1f322e33731b1262fe6b17b6e75"),
        (222, 1752598894, "0.85", "38.5", "0xf1c81dcf8866bdac0535b4e59b3eabb20c5351ff4d96d9c435ea5825abc71316"),
        (223, 1752598898, "0.85", "5.56", "0x00c3d56369054fed51b15cdf654edcba14045ffab2e712a630dc11eb02a253d1"),
        (224, 1752598898, "0.85", "1.15", "0x64732ae0de78dff42583fe5de7a02590280291024e0e931a2734044ce3531611"),
        (225, 1752598910, "0.85", "119.44", "0x5cf2ccb59b504ee6dc80559eb55196014ce0c54930e39270ac11cca6f3733206"),
        (226, 1752598914, "0.85", "1.15", "0x5720636723ac119c7a976aef2c731564197984c2479e25d8b3478c83f9d01ec7"),
        (227, 1752599261, "0.85", "29.99", "0x16a93b3c49cd0d01030ac81989149806432a1ed00e04fdd0800058a8553447f1"),
        (228, 1752599263, "0.8499999031", "7.741175", "0x8a18c0e256a276849c569c5456301853231b8271fbf00c6d7282981e26bab182"),
        (229, 1752599265, "0.85", "1.15", "0x22aa27937d0328986a97f0e0a559d639037f42e695d665d5c76ecfd0f7801621"),
        (230, 1752599265, "0.85", "1.15", "0x2b1ff02c115fc36158ac0e18878c8d18334c5e56a7dd08fc2c6aa0fe217ed3c1"),
        (231, 1752599267, "0.85", "1.15", "0xa3e1c2c461c6e4cea80d1817c6f499b7850e329771e6186a6f95b6c007ec9d0d"),
        (232, 1752600801, "0.85", "20", "0x10851641b7ad05b5eb17cde0dc90cfb27d4da26dee0df4ac76b06dcf6da6350e"),
        (233, 1752600805, "0.85", "1.15", "0xe6c23adc4c772e34ffb8612c56889924d7fed4bdd3b2b3f40dddfb43024b2976"),
        (234, 1752601815, "0.85", "10", "0x71b128659647016029f72229e1bbbb07804fcad08edd8421488c3caf885c2b7f"),
        (235, 1752601819, "0.85", "1.15", "0xc217788494e602ea706c217c4463ecec2e77afc06e3a5dfad98dfcfcd79fefc1"),
        (236, 1752602569, "0.85", "312.18", "0x6ffc6ceccb67816f73e5a1e624d3ae79b5bfb800a0667f656a3d3b58ec176329"),
        (237, 1752603431, "0.86", "80", "0x4d37bafb62937d2145c9a0f6dcf50a2d1d76083682291b441560e0284e9bc173"),
        (238, 1752603435, "0.86", "1.14", "0x6dec8b5b24215b43c140cc93a8f3d46eda40b5cabb6b5ce68f57ffb4e21570a8"),
        (239, 1752603501, "0.86", "597", "0xbe0d1b76fcf7156bd79c50e4815e423c9ea67fc7ed9305df48acf0fec61cdace"),
        (240, 1752603537, "0.86", "30", "0xf3ac04e29bb4184c4855c45373f737a8f545fd8afd6768352c75737a8a41c3c6"),
        (241, 1752603539, "0.86", "1.14", "0x69c1d30730ff01610ef4f2d85220f69a814a59ba7843e1ee4ec6192dbeed78a3"),
        (242, 1752603543, "0.86", "33", "0x88dbc7fac99f684c322ea840a2bcefeca05ee77b189918ae376cd5d515093c6c"),
        (243, 1752603545, "0.86", "20", "0xd3dad98a819d12bfc047149af47f770c2da18947441855e30a910cc4dc521237"),
        (244, 1752603549, "0.86", "1.14", "0x7afa8d527a93375b02208cd35dbfaeaee39a935203eab745557072f91e8ca3d9"),
        (245, 1752605436, "0.86", "111.05", "0x851a0fa571f8ab2fdbd019483aadea896004d724d8d4b929c1fd55523556c80b"),
        (246, 1752605694, "0.86", "40", "0x4db49ede8a018cb78b9db413e73df1966a30d56a3e87e768cff293798b86f3e0"),
        (247, 1752605698, "0.86", "1.14", "0x8c3102d63ef70d785f78ba3ec147e88931da365d256e18b1c10fd70cc4c88c25"),
        (248, 1752605920, "0.85", "270", "0xb4982550ec7e60e29b7a85f540620b0a4b4476537ecb46c59c5e6f96354edddf"),
        (249, 1752605924, "0.85", "1.15", "0xaef3f8dbcf0e069bdde306a0590052e7f406e05eb00e47faa99a0409596f191b"),
        (250, 1752606524, "0.85", "40", "0x6f45a72c1a18a98dcfab37602cca7d9c242fbc28898aa7bdd37834ca96ed82f4"),
        (251, 1752606972, "0.85", "51", "0x1a581ebecfcd950b24d62fe826053f9c85ff65c50d2b9ade2a8bbc00a86111fc"),
        (252, 1752606976, "0.85", "1.15", "0x552bc6306a0b845a05c712a3fdee2badf952fa9d4e92b290a292dea0805ff60a"),
        (253, 1752607254, "0.85", "40", "0x253aeb3a50a397966a8cb6658ae4712c2b424cae3a21a7d65482d72e50d339cb"),
        (254, 1752607254, "0.85", "5", "0xd2f227c680e3ef91df85e445a207cd21e7e0eb56a9cb458492d00bf97832d693"),
        (255, 1752607258, "0.86", "1.14", "0xe3e365e075d1ed433a14aa39ca6c1c5cafa25893a788d81cc2a8faab70918e03"),
        (256, 1752607340, "0.86", "40", "0x9fab4d387b8b47e3935b54cb4e73e894eb55b938493c6f5fc4002ada34b2077e"),
        (257, 1752607340, "0.86", "490", "0xd7d7782b64c69c1239a4a439065199e32bd7cf1b4f085d1a9e01f02002e71079"),
        (258, 1752607344, "0.86", "1.14", "0x404e4653031c7c487e9aebfb3bd32737429faef0c176aab5112127297fe715e3"),
        (259, 1752607394, "0.86", "250", "0x47242b8d89f155674cc8985b04e9b17a4755e7defc2703f82e88bce7e9015465"),
        (260, 1752607428, "0.86", "1600", "0x9ea9567d639b796a1659f3634f46c618be516672fbedfcbd234f2baf6c06939c"),
        (261, 1752607428, "0.86", "40", "0xb6be8cf7d89daf490ee548ff9e7ed3219ef7dcb47733ca043bdf1754909b04be"),
        (262, 1752607556, "0.86", "167.24", "0x076a5162f115a586ee2567b05f55b708c8b89578b0960bc590ae363c4547c1a3"),
        (263, 1752607556, "0.86", "160", "0x188a80a845c73b4ba4ac2e31678d43a75a7aa309de51d9d812c50d20424a92e9"),
        (264, 1752607556, "0.86", "39.99", "0x590ff6ecfd8221664234da898c91eeec9bc900a77ff29fc0e596def834e46fb8"),
        (265, 1752607570, "0.86", "40", "0xd2f1707a734fc47eed7c042687e6077afb7243659abc50371651c929ad535ec4"),
        (266, 1752607592, "0.86", "8.93", "0x8b4b3692a32e4c307a00fa35beaa73219538666eb8484c0dc57cf516ac9e6557"),
        (267, 1752607602, "0.86", "31.07", "0x6522b76e5207c9af98649f40c9e9c9a23ebd7cfe45268b419a6fdb1d09ba3d2b"),
        (268, 1752607634, "0.86", "10", "0x285836cad36a8f0ba7c70ba2b680124bb3dc709bb120a5062734ceb1e5507fd6"),
        (269, 1752607640, "0.86", "14.29", "0x04e5eb9a79f4ed0f3f1062b63cd8bae93400f8f977e9a37cbc223d9459fe9ac2"),
        (270, 1752607800, "0.85", "39.99", "0x548ec51f360f7d967df8411175281566695dc7fb5bf9d67ea986275c71b62bc7"),
        (271, 1752607800, "0.85", "140.01", "0x729c21f0ea3396ed5b38d95b15d1eef9ee03ac005073b1a646157d1b6c1a847a"),
        (272, 1752607990, "0.85", "160", "0xbf75819eb417cc97b59b50a343f289a19db2b897c56157dcbf3375452d1d41ab"),
        (273, 1752608596, "0.85", "200", "0x7b002ea523c489dbc4874c686211dba5158339659464a948d7a58d7d94258ee7"),
        (274, 1752608598, "0.85", "40", "0x1cf5b43dcc70cb10ee6938a0f4d8c075ca666e6bec45c48ff21a883900b6840f"),
        (275, 1752608598, "0.85", "209.97", "0x32e68c8ed65945d2e744541ea1952812f260834259dec42b922d84e6e2c349ae"),
        (276, 1752608600, "0.85", "16.67", "0x4d37c709a65ca4ba72b90443dbf889a33b0e747e030df7cfaef26b28a9c71fcd"),
        (277, 1752608602, "0.85", "16.66", "0x2c888ae030c74f9f5b26ae4f7eb5bb27995c488e9c66fa562ab47c82a5d7d203"),
        (278, 1752608602, "0.85", "16.67", "0x2d5236e8fb3ff170e6642ad278b047e241a300e9388bbb17b9ff74ac09dac2e0"),
        (279, 1752608602, "0.85", "16.67", "0xac63805bb0399e3a6dcdba67c68060acd751fa146f0b9e03c698d8ca9e7aa9a5"),
        (280, 1752609072, "0.86", "599.91", "0x9386c5f1fd12501de11c9923bae8bba225f4611e0e76a199ef385a419e2d1e37"),
        (281, 1752609242, "0.85", "13.86", "0xcf775a0634270342a3b1646b7f38315116072365623dd71624dddfcde3d69db1"),
        (282, 1752609368, "0.85", "1024.49", "0xe559d157e910f8b610e8d0674f970e63cda4841c35374e8e10df588deef9188a"),
        (283, 1752610080, "0.86", "5", "0x381330cf423e0a5d6e51685f720144225ffe523ee1d21f1a4aa2704eebda37f5"),
        (284, 1752610776, "0.86", "50", "0x00d476d4eda36112b8fc09212f523f5dfbdf6029f5f8557adfe49d4a005af6f3"),
        (285, 1752610776, "0.86", "5", "0x112a8d71fed26294ee36137052e1fc76ab962fe212e0b1722ffafb56b3327704"),
        (286, 1752610776, "0.86", "346", "0x5aedca3ce570b7727e00e3eb2be9d7ede08b00badb0d909c2ae9f26eb858b20c"),
        (287, 1752610776, "0.86", "346.67", "0x5efcd8902c4f8175c2a6d87738ae22a56d09e9997da76e371d88f2c943a8779b"),
        (288, 1752610958, "0.86", "20", "0x148950104f3f6b286780213b8d87fd613dcc57875c74d12588b68aebeea797bd"),
        (289, 1752610962, "0.86", "1.14", "0x793a45c4b62422f9ec4aef7bb7ae24778b9bf43848c1ae64553e2c7836a7a33c"),
        (290, 1752612397, "0.86", "100", "0x7ef58e1fae5f1e2477b65b7c3f9421b99b4821f608b7280549e4843da25b53b1"),
        (291, 1752612411, "0.86", "14.95", "0xc59bd8e1f7b923a090e56b618151e37f90cbcad5d426c1474c2eb4b2345a6f51"),
        (292, 1752612485, "0.87", "579.1954", "0x4decab3910a050db4a8a2f588bcde591481a09c78b381e079300582f94fc08c7"),
        (293, 1752612675, "0.8799745935", "4431.946133", "0x1644b9dabb495cd90da21fbcb3a848f4854f89cdd86865776caf58d729d78764"),
        (294, 1752613869, "0.87", "100", "0xef1443e16df2ff29b7d8e7f40d97b4d3b8a9e69741330d6e09c4f69a4181d191"),
        (295, 1752613893, "0.88", "2000", "0xd0a49d5cc1d1f1c14eebda2d653e8bc7c06b3d5ff19bc8db79f0f20347ae5338"),
        (296, 1752613959, "0.88", "20", "0x66d0e3519dfb19139750579fa06c496dbc8f2c98557e977c919fe214343171ac"),
        (297, 1752614159, "0.88", "33", "0xb77b61abdd3573742bd93208da8f6bbc4f714570c9c97130dccfb854ab2a10b0"),
        (298, 1752614449, "0.88", "1000", "0x4356774f702680eb106520acc5ea9a1a91ad540f7298f0523967891ed0f7d0bc"),
        (299, 1752614927, "0.91", "1.08", "0xce659b7ea88f3e442a357a963eab822fabd394ff1d13d4d2d444252b42dfab31"),
        (300, 1752616303, "0.88", "5", "0x3b1d48d740980fcb8bcd9e56318f4b69f01413185b78f7faa6764f07b05fd388"),
        (301, 1752617199, "0.9", "50", "0x5b318c5d1d374ba15b5a3f8e2f625f2bd1850a7680d2e0046f41e377cf7ef9e2"),
        (302, 1752619339, "0.85684", "90", "0xfbe850a65e23fa36917002b695af17d50ba4db40c1ef282e87438a51031f8f4f"),
        (303, 1752619487, "0.8565682466", "154.44", "0x5ba94f8e55d503818ddbdcb6f972c3acbfae1401b6fe230b8260a05378084d75"),
        (304, 1752620881, "0.9187288136", "236", "0x650ce24c26f426ea466e5eb95670d7a41eda2c4f22b149e0edfe3127f33f0d33"),
        (305, 1752620933, "0.93", "300", "0x6b70004f4a74b87110f9803018a1a78c14825ad99a2e1504b6f6f339717091b7"),
        (306, 1752621117, "0.92", "735.7", "0x18f4a8c9e34a3df46274cca7bcc5ed93d57c3fb0efae3fb9ac6f4da774998bee"),
        (307, 1752621823, "0.7983290011", "1131.06", "0x28b3c11b16618cc5216068eabb3d3822e2aa500c4c486adf7d29937bf62f74fa"),
        (308, 1752621989, "0.8599999997", "116.279064", "0xd429f3ab041d2e04f3e892fd31c5d657620760a310d40ebdd1a6ab98fc4efd38"),
        (309, 1752622987, "0.91", "50", "0x5eb1258d839477f4c2a1120b4b4f999294c422f55dc0ab5239803f4fe8fc5932"),
        (310, 1752622987, "0.91", "38", "0xf0d1cae2361fea6920fb55b353e5745efadb3d92e1c3d7f0053ebe93e5cf2cce"),
        (311, 1752623395, "0.96674", "50", "0x73d4440143eb61dbd97afc8afbd243757b54b795b722704e7b57c800517f5935"),
        (312, 1752623519, "0.97", "50", "0x42ad11657d4b7aff5e1bf9214021ba36b8679e937e5c74ce40b9129c3498c3bc"),
        (313, 1752623519, "0.97", "85.26", "0x6096214e573c3b8a589cc66182bbf33ec15a327bbac8b7c2615ee596be3fe5d8"),
        (314, 1752623749, "0.96", "10", "0x3a4647002a00442f48ce4002cbf2d1dcb3ccbe5eb5474e5e1274ee9722b131d6"),
        (315, 1752623749, "0.96", "19", "0x6e03769a8e699ba0c55dd94ace7854fa30f006f8ccb7fc692bb499a91f4db590"),
        (316, 1752623827, "0.96", "15", "0x5c9a20724449eed3648f8c316b7bbdc9ee22668e2b8533f2b70da4fdaa17b435"),
        (317, 1752623827, "0.96", "102", "0x7d6d62d01ac03f0e41bbfbfebf2d3c2c0ac0cb9e8aa9fe7cd4d31d18cd602d59"),
        (318, 1752623827, "0.96", "100", "0x8d6e64a456a0f27662d06c42b1a9bf1c00391c6cdd3a818de35da544b43b9fe8"),
        (319, 1752623827, "0.96", "15", "0xe3e58282d729a6c028ca7f277fb17915e1019e51e3a7572b620bbeef751cf2f0"),
        (320, 1752623869, "0.92", "40", "0xf217cc7fe84908be7bcc590f2d7cf5610f7d9caa1fbc2f89532579ecf0f3dc09"),
        (321, 1752623941, "0.92", "50", "0x388ba61ab1646be11a1dfdebbd5783cec0adf329186a4462b629a5d159077a3c"),
        (322, 1752623941, "0.92", "39.99", "0xda5e6e5b117fadc016cd9f41f4f9b3f947b2be8ea7d1968e9e02909fca272570"),
        (323, 1752623973, "0.9", "10", "0xd20093abda61aca548db5f455aa5cf70c558470c113fa99ff6d564ec35adf0bb"),
        (324, 1752624117, "0.9", "100", "0x7a0e97a83978502f550831310f33954624fd5c8b4e3b999442007b80c274f7f1"),
        (325, 1752624119, "0.91", "20", "0x5544c55fb8062cf2d7305c5a5ad709a8ff60fbe9946108beb6436f3f1df3ba9d"),
        (326, 1752624119, "0.91", "22.45", "0xff5a6cb190617256ed5c998bedd316fd77fa31c7bff302a5d943da10fc804358"),
        (327, 1752624159, "0.91", "23", "0xffc5d1a4f8f378fd7bcf3af65578dda4b3ef2958330439013d2b960cf4b4f4c2"),
        (328, 1752624167, "0.91", "110", "0x0c6e8a56123d2b213c47165f8684a7360cc866b8bbd590e3f65c0c04168c0b00"),
        (329, 1752624271, "0.92", "100", "0x787d9d9bedf5421e4d13067954aa8b39a74b9269e4cf3d9bb1b24859a5b0d452"),
        (330, 1752624273, "0.92", "22.05", "0x40dababfb89ab8becf9a5168622a6d8d5fe189ee18584ce0d32c93b44815bb4f"),
        (331, 1752624301, "0.93", "5", "0x63f4c839fc72742676d96990082dcc4a21058af3aec269f0ae05bd8ac8c46a05"),
        (332, 1752624329, "0.93", "6.81", "0xa9986ae5a2f5af26f5e4ac04227cd885356bb1d58938c40348adef8c4ce269c5"),
        (333, 1752624331, "0.93", "39.99", "0x36ae7ddf5fc06800767015f86f5c04d06493d68a4de71653303ca5e9f7151734"),
        (334, 1752624331, "0.93", "110", "0xdcb62db2ef3899c65e2ec254e6b842afe8defa404e9edaa4105810a95fc25413"),
        (335, 1752624559, "0.95", "220", "0x4b059555617f26ab70934c9cbbd6408d6bfe03a48d97bc5a087c10345aeb5998"),
        (336, 1752624935, "0.92", "100", "0xb2d1fe7d0d36ccf12ff206b817d34b4f4918a49ca71c0aa1abaa3508ee44c682"),
        (337, 1752625003, "0.94", "250", "0x18d25365d397f1a32ca52d82c9b5d562cbdc234faf93c6bc8d503ad7a731388a"),
        (338, 1752625003, "0.94", "50", "0x47b8ab6d4d1b0fb86d981c1b76a3a3176922ce773ba684cfff5a776f1368d331"),
        (339, 1752625005, "0.94", "155", "0x83e5f01cc865ec9c3748a758a1c4d1e12360f34770d7cbafcfc4185023994e71"),
        (340, 1752625787, "0.9055555556", "1170", "0x42b41339c58cf9d4fb9c7ae73f214a047bde93564507514264817ec705ececc5"),
        (341, 1752626741, "0.9", "10", "0x0e39492a04d3dd8b6cc7b0d5af812fadb76e4e679d9663f24b7bfdc921597f4e"),
        (342, 1752626741, "0.9", "10", "0xe44cca4e7a51d861e55116346e6f8c07f436c16f44169b4c29521a1f0c1de38c"),
        (343, 1752626741, "0.9", "9.99", "0xf7171d6a234aad67c486542a5b59284b7ffc70f118310e294ef45e564f3a2180"),
        (344, 1752626741, "0.9", "10", "0xfcc03547fa3b134fbdb41581aa9a0b7df2c6002b061fa7de4ea92a9023d308f1"),
        (345, 1752626933, "0.9", "40", "0x8f6c8f268cc49be6384adaaa8226a64a31b86eb970460dd2c532a480f46d50fd"),
        (346, 1752627703, "0.92", "20", "0x9b5bb71f08d5a24e22c06cfc673e6c3743d80e84e43142ec0c70f1be2a4dea06"),
        (347, 1752627703, "0.92", "24.99", "0xa6ead01fcbeab77c92767ca9b969535978b21cdba15ac332110a54b290d65eb6"),
        (348, 1752627909, "0.9", "546", "0x2a6e3e02cd0a3d0543e76098cf32073a2d88dcaa424593f7bad0f0c8042791fc"),
        (349, 1752628137, "0.8964850368", "223.093515", "0x1b11f4f25b6b6ee1587586569175a3a40cfcafdb5d6b20212d1440f2ca565639"),
        (350, 1752628621, "0.87", "49", "0x337d5e15ccea54f28a75dee6f9934fc0f9c3ae9aac495bc8f51bcf77d751ddec"),
        (351, 1752628625, "0.87", "8.7", "0xccc5f4f99fbb9bd63281e3f63333d097ccfd066426606a6ce25e6bdf231fa3ce"),
        (352, 1752628775, "0.9", "130", "0x3844da30780db9e0e87f703145428e39efacd52e8043d6354d7a8986b7e756f5"),
        (353, 1752628935, "0.8981699787", "222.675", "0x985dbbe1cd8b7401ca802bd2a8e058ad16974ce39c9d36df39ce6a5d1fe03081"),
        (354, 1752629399, "0.9", "5", "0x1682d95bc2c3546738e11e6ecc4ea40ff9214e6afafacb93b9ae2f7c001d4d1c"),
        (355, 1752629399, "0.9", "49.07", "0x88e7df04f69f00f927b7e6b2aff92158d21f9fdc75c4afc1f1f73118fd99495f"),
        (356, 1752629399, "0.9", "112", "0x8f642b9696e1db4fe69bada116ebf0590427bdb7bd36189839d49f631128ff0f"),
        (357, 1752629399, "0.9", "250", "0xc9594219a341719adfca9c2668439965d253931069c861ac5ce6a190f5d6d7a0"),
        (358, 1752629399, "0.9", "5", "0xd2b08c391675800372a1315e5c4e4e263c0dc8aaaf5b08c39b6a01f6cc472a38"),
        (359, 1752629571, "0.88", "58", "0xd8f5b917526da5db02f8cefcbcf1643d54e7a43ed4f8e91c9c5f60c55a4c024c"),
        (360, 1752629579, "0.89", "224.7191", "0x70aab4263b3a98832ac82f7443c974b731b12d66e88f9e72c630af703c5fe761"),
        (361, 1752629627, "0.88", "8.66", "0x9dee730a69cf75119487795387b396ed99f581f83c7829f9625d75b0ba8fee83"),
        (362, 1752629737, "0.89", "20", "0x543af084af6eb2f0f7ade944c3ef6e3b2331739da9512de26bc11d703b3ee3c7"),
        (363, 1752629737, "0.89", "20", "0xc1cee4b440ce1869ced3a390d75ac961ab1c39cfc6bdcdb587244ed32a4e4845"),
        (364, 1752629807, "0.9", "1038.14", "0x99b616ca71fa181c2d54fe424abaaa6f4092b12191a4f8ec06a762d5982e7bb4"),
        (365, 1752629809, "0.91", "1372.66", "0x2dcfd8aefe9c297b9e26979e658b72aa73c7e6dc64ba5effa52f343d3ef33bee"),
        (366, 1752629813, "0.92", "160", "0x6ca7a93383e14ab8c95b5d70c8c1a616e7132db6c7faa2f3ce546de34a38c96b"),
        (367, 1752629983, "0.91", "121.34", "0x12869966be7b81055319cf78478a79f092ecfd12f4121d137bbc4828a1fb04bb"),
        (368, 1752630177, "0.9196458978", "10336", "0xf93bedfa20a5a5290cec63a8384468d0915cd162289aea3ea9c2baae1652c7f0"),
        (369, 1752630299, "0.9164949361", "11246.3", "0xdf468b742d27d2a1d0c3dff905251e973c897fc98725e0e070cb969af81a09fe"),
        (370, 1752630481, "0.8899999978", "224.325841", "0x3f51dcb39789ab29c666b853b5f05c680dc8f6b2dd33491171053b7a2dc29bc9"),
        (371, 1752630537, "0.89", "20", "0x15d7411a02d05c3772c49436798eb3b17fc5aed13f134266931d8de551f2d23b"),
        (372, 1752630563, "0.9", "80", "0x948cc7752a097a85b4760c6ec508d5d45264411cd5ee2887c24a39ffc38f9b83"),
        (373, 1752630675, "0.9099958506", "12050", "0x93921a09de782ea07718a4ed2bb8cdbdd59f7a17b02d0b4be18982fa1dd84c14"),
        (374, 1752631179, "0.9099959047", "12209", "0xe5e849ec73cb937f2a91ce83c286fc7e3baee16189910c6f851318155547a944"),
        (375, 1752631375, "0.9099999993", "54.945044", "0x957bb6ec20145a6f595e2314160da265bd8b4e701ed7a05a9025de74270d4558"),
        (376, 1752631391, "0.9", "5", "0x77ca11e57ac9f9552810312bb07dd88abe2f05b0ecc1c173c56fcec3f464d996"),
        (377, 1752632623, "0.8802159118", "894.81", "0xb8d4690684773689e092907513cfc274117232376b5128c7c9d72d7d7db9784a"),
        (378, 1752633603, "0.9", "209", "0x61b0a627f390c394902f68a8bd37c69b59b4b1b82e37065dc60cdf24a91cc146"),
        (379, 1752633635, "0.91", "195", "0x268aa6632c79a6d3c4cf9d8c62a0222986a7cfbdefbf0570f5d5f8dbe01050ac"),
        (380, 1752634452, "0.91", "810", "0xf484555bde2bb3d55b3dfa91a28234016f51df07f1b6b51794c942f4ed00b98d"),
        (381, 1752636682, "0.92", "4000", "0x72029f162d2a36906613a1e17f4f7fc0a6882f769f58780278681b42f445f1d1"),
        (382, 1752637190, "0.92", "29.293475", "0x4944d870474c75b49445fc94ba687d4e67603f9e5f9b54eca1b0a87e836afa03"),
        (383, 1752639680, "0.92", "10", "0x48832e0afb674a94c244eb7c7a779bbc1881733b8a6970f4e8a729b04398d520"),
        (384, 1752643298, "0.9099999947", "15.109888", "0xf25bedb1fa6c798746d7f17610e801134f617923dba1934edab4d93098c2235a"),
        (385, 1752646479, "0.9", "100", "0x92429e07ae1506f7d32086be2bf5fb3f2b4a0da8aa07c36c009efdc53a67b95c"),
        (386, 1752647757, "0.91", "90", "0x465a66c8dfa66ee71cc354156123f1a4403a8b6ec7603e8424101652b1b97321"),
        (387, 1752647765, "0.91", "299.64", "0x8391162d609e56758a4f212de4bce2d7b86bdd3008660b366087111f0ddb8248"),
        (388, 1752650971, "0.9", "220", "0x29eebc9ec17946dc6249edb3b07f4d3d9b674ff7eec0ffd70719c11fd8b9628d"),
        (389, 1752651117, "0.9", "70", "0x1bd4de477d087f3513ab266c8c903bb65f984babf758342096dd7c859c7440d9"),
        (390, 1752653053, "0.9", "10", "0x80fba910b869a359f604f0b6d006d70ee7c1465002dfa76de5ec8d105d53d399"),
        (391, 1752657458, "0.9", "34.48", "0x32616e987ff9e37a7e76b82ff1124d0cfa5ff48d04d0fe62af4c526745d8a668"),
        (392, 1752658685, "0.9", "111.11111", "0xa404bff283d9422403ff6e216a972fd10c0f6e16abd206434f42558cb8499627"),
        (393, 1752659201, "0.9", "152.58", "0x2d1906b2dbaa6993ded6d16d482948bf903afad1c75decfee4ae789dee558e15"),
        (394, 1752659201, "0.9", "10", "0xe86c81f48d260b8cca249a953a8d6e7c1a25142251ec6f86ded10b1953b89924"),
        (395, 1752659291, "0.9", "20", "0xf1728ab85de28459150a58216210cff440e0bdae7175f767263e42498a50585a"),
        (396, 1752659301, "0.9", "50", "0x9339123f0e12e510f06faa46b49b2756acaac0236e700604aecc07e035281014"),
        (397, 1752663552, "0.9", "49", "0x0571b65c8da0f18263fcf3d8304c6187be6ae99ba6cd55a5da0cf280b276fe9b"),
        (398, 1752663552, "0.9", "19.99", "0x7b5bf91e3568b30835d3c687993712dd49bad3955e1dd68b850892a1d9d581b8"),
        (399, 1752663586, "0.9", "10", "0xe9ca8cfbc0cdd83c240948cdd3dbab143fac45415c176d9c606cffb242bd02d6"),
        (400, 1752664029, "0.9", "30", "0xec0080ce1368b15bf292e4c576626cfc39cc7460e877d89a2c09b60c17d8c38e"),
        (401, 1752668956, "0.9", "10", "0xf5c3d0d1c11340afdda3debb9cad7a08ce23b1a20f70f4cfc48d2773db8a2346"),
        (402, 1752670542, "0.9", "55.55555", "0x5a80b2865038ebe7c2a00b8880f0bbbf6ce3a058b1d23b7de3e0a762ce763e4b"),
        (403, 1752671336, "0.9", "90.05", "0x9b57cfbc4b0770ad8980273407d14f3fe211e5b8fa3245f0361f2067185b485a"),
        (404, 1752672938, "0.9", "150", "0x489d63bd2683dc61daf94ca84ea57a1a2f31a5d903b496d701026f7fc37e7a4a"),
        (405, 1752677262, "0.89", "1386.25", "0xe2cf0cfca67bd5d85db18fc2691a49e9224bb12f720a2a0038bacb164a2ddebc"),
        (406, 1752678232, "0.9", "222.22222", "0x2c3e972c737614de88b4cec61cef034f3a31cb29b288817545d12261d5cb5f2c"),
        (407, 1752686006, "0.9", "600", "0xf4d72d5afe4a30c6fd3fb806c712912521b97dbc2f8f3e7e59b6bd5ae22aa3bf"),
        (408, 1752686272, "0.9", "700", "0xaab4f2693b4c60a53abdd80c419a75561d5b45b4c698ec87f5828bbc6d490d32"),
        (409, 1752686398, "0.9", "500", "0x6c71dbcd207feb149e51046188481f435e8676730200b1a42ee4f7658c647a63"),
        (410, 1752686400, "0.89", "425.5", "0x47a2b85d5666ad572b735a99920dde30dbdbc3874268f7fe25f058eae8c2fd66"),
        (411, 1752686522, "0.9", "800", "0xa1a4c98b252796f865e2dba12d67d53de7cf55f4fd1ba662c02edecfaf43cbb1"),
        (412, 1752690522, "0.9", "80", "0x3a0e40d3356a7bfbe5da48646baa15b16be9267ae41f85c96b47f6f34d622797"),
        (413, 1752690610, "0.9", "80", "0x437ff1afd3038bd30166c8ca7491720c26009220a0f703b96d5fa853635ad866"),
        (414, 1752691928, "0.88", "16.32", "0x898528cb5233cb87738fa14ca1e03b7575576767e418e20382fd16ed7eded565"),
        (415, 1752691934, "0.88", "29.68", "0x80a7f78e236f3bf1957fe59d164b601ed5bc84c3433103221a5ee1e95c288ec0"),
        (416, 1752692078, "0.88", "9", "0x2f8a988085fd833ebf3ea97eb25dcf3eb2acf6cdbea70fcb3e379ec7c4fcf943"),
        (417, 1752692078, "0.88", "50", "0x918d397945117c083cb0e1642688538179c3faae1fcdbb0c039f1c801496c0f0"),
        (418, 1752692230, "0.88", "736.77", "0x51871c2b663ce012917bd0d59fe0ba15dbd4b9d8262b0dd76942d8cb49fb198b"),
        (419, 1752692230, "0.88", "203", "0xd89b40c8ac58799381ccb31aeb08b63d3055299da101ad5e4c0a972bdcfa0a91"),
        (420, 1752693152, "0.8899999979", "33.707863", "0x22bec698289de24126d95113aae90bd85575bce2a10024d4584cf1accc154f8f"),
        (421, 1752693552, "0.8799999648", "1.136358", "0xb208e04883ac877a2d2d3030c5d641261a2a0befb88505a89bba227506548467"),
        (422, 1752693582, "0.87", "1.13", "0x6e0b6074d93eb3e426b0b9daca992a328d2a373499493a1c742f5c554f8c811e"),
        (423, 1752693720, "0.87", "201", "0x9ad2fbf106b1610120de26d2f5b7ae0ca7f763fcd5f44f470e6745a361d53b3e"),
        (424, 1752694180, "0.8799999648", "1.136358", "0xcd78c21b876b3322ec626c80645b3c82473010f6b9069508f3169c6d4082226b"),
        (425, 1752694390, "0.87", "1.14", "0x27dbac43d052e33a895d24eb85fddca265770ed772585a2e01f8910fbd01c394"),
        (426, 1752694830, "0.88", "50", "0xa48a52b0be94a9499a5afe2307895ba9213d2dad35ac29c91d6b2c77f50306bb"),
        (427, 1752694838, "0.88", "22.47", "0x09b33d20adfd515084b081ba20f25c1e4e9c5a3096595c418931070024f0fa47"),
        (428, 1752698154, "0.88", "3.37", "0x290a48797e420e35dfbfc7b0e63fa73512936005eecd1e42b8aed053393342a4"),
        (429, 1752702692, "0.87", "420", "0x1d6d024c3bb80b4688d072862a87f1d739c861399d7e1b6d330d46aa64bb9d1b"),
        (430, 1752703128, "0.87", "90", "0xc7166101ef9a935be7dbe0e69ca6205c35c7286039a1f93c6009d2eab3f8c191"),
        (431, 1752703986, "0.94", "100", "0x827a28fc2331bdc36b0fafc291b3e1c126c1584b12ab795e268a9052e140123c"),
        (432, 1752704012, "0.98", "8.46", "0x4820c2903d5943e51d294583bae7b9371c575154ee26cffd25e80a76b48ac21b"),
        (433, 1752704012, "0.9757612678", "351.520407", "0x8d354edacd6b63fc041c43f0978b9276fcdf59a27ed42bc72e3758e5f5f38c3c"),
        (434, 1752704020, "0.99", "138", "0xc215eab734c7e04038737a5eb939802fd3aa464f7515fc72b7412db798a29def"),
        (435, 1752704068, "0.99", "751", "0xbe89a59709d3d2cdb101c28860a03d917595880af2d10fc9677f39712d5652c9"),
        (436, 1752704174, "0.99", "350", "0x1dc3a750d0c91fe4cb007bd0b0e6206394f92420e992ae4f2e3b0fc8f231e831"),
        (437, 1752704202, "0.99", "30.01", "0x1cb7f26899a902663c8f967efd84396b269f5525aabf16fb2ca0ccf947b0adbc"),
        (438, 1752705122, "0.999", "786", "0x9868afdad1790044061e5079b4d1fe2246f03db839e4f7b2734dc0e81645a13b"),
    ]

    fileprivate static let retained563321Yes: [RetainedTrade] = [
        (0, 1752501243, "0.25", "10", "0x83d580417865b650312ca5806552f865d37b4ab4f1ccc4ace57a25daf95691e9"),
        (1, 1752502181, "0.24", "5", "0xb91bbd096b7a5bfa1840896aac9cfe1071c12ae8fb60ed967a10cd1b1d8c4457"),
        (2, 1752504404, "0.2364531876", "42.291665", "0x29ebefab3c0bc2c26de690167557eda34f413c103636f9526af526af2c6bdfd7"),
        (3, 1752505625, "0.22", "200", "0xa0c9ee1e1fcef2fbad1ca2fc5c90d6bf56e33e8f0567a88d26e9b21dc4f43407"),
        (4, 1752508381, "0.2199999164", "9.090908", "0x08006507eba435b0d7c2a685fafc45e63a60a0ca2e8c6624f63941fecfe69189"),
        (5, 1752509282, "0.2", "10", "0x8571bef98abadad68b1eeba5c2b3d93efd677cc0db67e4afac5ccaeb884c21bc"),
        (6, 1752510264, "0.2284125256", "87.560868", "0xd415954032d96a9002fca9f727c538a6c678854218423753ade96c9f2639a81a"),
        (7, 1752511790, "0.23", "10", "0x4ff61b19a57ba73eda97b75eb80c2684817afebb1467cd721060ec6fb9b7b2af"),
        (8, 1752513612, "0.23", "339.33", "0x5e6ce5b3f8390e54adfb3af569a75330e6bc5a5a298ba79a6b68d3367d8e0061"),
        (9, 1752516914, "0.2399999949", "133.333332", "0x512e56c1f0036538ee51a51601821859c463677aa6894f7aeb8b46d50fd0881e"),
        (10, 1752519969, "0.23", "500", "0xb55ca63fe37b7198eec1a850fcc66fd8ff43901c0705400062e95ac349c9f244"),
        (11, 1752520513, "0.22", "8", "0x27b00bc33fbd6b8dd63f822a5288c4f2b69c5658ef650c94ce64f5afc9a56765"),
        (12, 1752522667, "0.22", "5", "0xb47f4f1c4f76df00a34d0dc216ab91efd5ec92e5aa7b6bea313f0ee3018cbe77"),
        (13, 1752523956, "0.2231825072", "67.209564", "0x640133a5e734f21be7c861f6846466d8d3969d31ffad51eb41494e20d7dcf64b"),
        (14, 1752527917, "0.1899998784", "5.263156", "0x62daaa7acc8988475a07816b52bbde7e0cfe023d8b5c1242e9b9b431128a6c64"),
        (15, 1752528051, "0.1899999373", "10.526314", "0xabffcc88542043b3ee47f3c509bd756e952e8ff0e34ab9018bf95812b0c139c1"),
        (16, 1752528085, "0.1899999569", "15.789472", "0xd9deaa2ceffb8d9ac1a630ca96f30059de680bb33fd86cf579b4edec169659e7"),
        (17, 1752529019, "0.1957251666", "510.9205", "0xf6ca6d4986b22d31bca9d3c2eb77e81b8dac10e16b3d41a2ffc80f2d89c932a7"),
        (18, 1752532753, "0.2", "500", "0x013e5075a967ad751b3170df0b0045ce1dc6c89c343a6f8484168a07fbbc1408"),
        (19, 1752532887, "0.2", "500", "0x8266993d302a94f142897df739a0db3e570ee2b1c1ab8dc05d03f0b2a6874b49"),
        (20, 1752533663, "0.2", "500", "0xc59698bef21e593d8aebdfd48c245b37e61092a582c3d049a4c89b7051f76f00"),
        (21, 1752540069, "0.2", "500", "0xce5361a3c66e29cf3096540ea7eccaa03430cc618d7cc18ddbaf4cb62bf4ac92"),
        (22, 1752541667, "0.2", "100", "0x961297c19da04d22835a8a14f432c244a06eb48410c3570bba549c33a8593b67"),
        (23, 1752543163, "0.2", "500", "0x357526b5b7129d89cf5274e02e2997f284e2152f230c788a60ed40b1133159f0"),
        (24, 1752545221, "0.2", "30", "0x8693cb9ebabe4e93c25c906d1c767cbb3384b357af654366b61a0812a11b646c"),
        (25, 1752545815, "0.19", "11.63", "0x8ffdb8fda1209f60ffa02bebce67ffeda6778635ade6a812917a98221fad1470"),
        (26, 1752545823, "0.2", "44.88", "0x1cb8a327141b3411b9262caaba8eb06a624b4fd5f324f30008c89276c3f282e9"),
        (27, 1752545823, "0.19", "23.25", "0xbbe399e38a812e3d73012f4a1ade4a619003d5fae7d74f30ef3b3093ac9a7d0c"),
        (28, 1752548342, "0.2", "10", "0x7fcd5761aa5f7fd464eb39aa090a6e47bb08fd90ad1ab3c69f59f63536fd42c1"),
        (29, 1752551993, "0.2", "172.6", "0xc462ddf14789dac03eb8a19bd7bfc082d216ba16f714b8ca97fcab011ac0466e"),
        (30, 1752552377, "0.2", "5", "0x5a7588c190c39f24c5a4b2ccdd45801afb94f5d046241820588b08a910b3f975"),
        (31, 1752552389, "0.2", "3.01", "0x244669047fc0851ae6d34ded94925ecc42ff45d11ff003825de7723a8369513c"),
        (32, 1752552401, "0.2", "3.99", "0x5cefac12133dc6c17cd5b6cc88347643124cc62892a72e8cb681ba6d468fd036"),
        (33, 1752552403, "0.2", "21.01", "0x9b840bae0d79e22a4776895bcb6ab5ae654ceca64a4301f74b6580e774241042"),
        (34, 1752552407, "0.2", "5.99", "0xf2b40cedfddbe688402513402cc724ec0ab974bf9235c6d71be4290612de2b31"),
        (35, 1752552411, "0.2", "27", "0x4f1cd8a318ff7ed1bf82ad4e1ed0e99e2997f2a3cc1f8726cc030be0ab3af802"),
        (36, 1752552413, "0.21", "5", "0x5ca2e2ce90df32ac18b91559a6c9faf6516eaae1e5ecde40119b5494cce7ad0f"),
        (37, 1752552415, "0.21", "11.01", "0x5371c8053d75568ba4d9f1809a91604f1fa01c8b64a925299757227519051024"),
        (38, 1752557065, "0.2199999993", "993.954544", "0xad38fde3543bad44120c8fa0cee8eb485fe076f15aa5e85dab77538be12d4184"),
        (39, 1752563119, "0.209999999", "690.476189", "0xd8fea2b358f675c92f1a03cdfb2450c779df832b0b3de7146d789981e59dccce"),
        (40, 1752564995, "0.21", "954.52", "0xa464c96842691894e5aee033275f000e9ab6366bbd98a4c72a800e50074b2be2"),
        (41, 1752566381, "0.21", "103.83", "0xf3102a0149e885eded7ea82260cc65422b5eb24264776045a9b6330771776837"),
        (42, 1752566658, "0.22", "4.17", "0xd2d9a240a1025263fc9b6e7113591e96be46307aa1d3918a04e78e356cb28353"),
        (43, 1752566658, "0.22", "4.17", "0xe0e42225a7d25f0812d36b8f6851d92a188a38767969563b366c98e0eb54cb5e"),
        (44, 1752566662, "0.22", "4.17", "0x545ae35031a6fa8598ea4092ba491cc7b4aedfe551c8144c49c770563d43b18b"),
        (45, 1752566662, "0.22", "4.17", "0x5c77397a188b3faca2202b79000804bb33d2dfce941a7f59dc2066b91fc181ee"),
        (46, 1752566702, "0.21", "25", "0xd780e2c92647257cf49724bd9fda6226295d8926f4eccabb2a9b76aaffa33c6c"),
        (47, 1752566704, "0.22", "4.17", "0x42eeae81ca280e90885271592efe0b30e2df90207a96f444c4bcb65f713a10e4"),
        (48, 1752566706, "0.22", "4.17", "0x8a653884c203a27e139a168f60703071a46784e58a8316eed806c67430c8bc75"),
        (49, 1752566734, "0.22", "4.17", "0x5c0bd14646011bba6272265b381e4cb0395a7fceb9249e1e4891c1af72bf0c0b"),
        (50, 1752566736, "0.22", "4.17", "0x6eb6bb64e3e7cc08c5ab6a2f4428853db3fbb8d7b01a9e11c3a09d832cddc837"),
        (51, 1752566738, "0.22", "4.17", "0xf4365ce46a8e17a1895fc98dcda7c52f42e4d59b0e8423cdd2e7bb79c31d3d6d"),
        (52, 1752566750, "0.21", "22", "0x283b58e6d3e178e6639c0f587ccc3cc687fc30e7ff17019ecdce58073e05adaf"),
        (53, 1752566754, "0.22", "4.17", "0x37f090c7a56d3af09b3601ab2fee562a104254d00d4aba6a748ae6ee88a5c641"),
        (54, 1752566764, "0.21", "11.66", "0x2eddba972e78f0428813166f2b84b0025fd47ac5d90026b659c06a5fa5b0a221"),
        (55, 1752566768, "0.22", "4.17", "0x9c609efc2275236e8c98bb00e07f266834b275c3235c55e9836dc4f73e6e18e1"),
        (56, 1752566814, "0.2", "206.62", "0x2ef1d733b918c423ef02475709f026a83550d51aadfd1c6b319f7389e5aa05c4"),
        (57, 1752567933, "0.2193857194", "1139.545453", "0x69e5753a5bf090a8038f712e9323117902236949941daf8ddc55b179209fc5a9"),
        (58, 1752568194, "0.209999974", "23.809522", "0x4dc3a89e2ff497a0334314121f4fe1b59341c07ff1aa7394faabec6d3511d948"),
        (59, 1752568522, "0.2", "1.91", "0x0240bc1b495df47943dbbbb44fe8ef61a77111a7394f418cf6aabcc3cbc0b030"),
        (60, 1752568714, "0.2", "5", "0xdd3f57839241aab1f775889cb51fc8b606eb2c4b46c85f0473718eff6c7f130d"),
        (61, 1752568830, "0.2199999936", "90.909089", "0x1028366a07e0f26c920f731ccd0671d1fd3581d5dc2304e5c7e28519a41f3404"),
        (62, 1752569177, "0.22", "45", "0x9410b4918477cd8fe1eedd42a3f82a4d37ca85187fd4602a15f298eb29ea6848"),
        (63, 1752569745, "0.2199999445", "10.81818", "0xfa0a80064e4719257e4615d4d02f4dd1c74fe006d98d9dab861e9203bcd64e3b"),
        (64, 1752569807, "0.2", "10", "0x60bf5a78ebaf639fde3f314552e6a5caf91008585b3e0e9058cb6e71e19011a1"),
        (65, 1752570643, "0.19", "223.09", "0x035fd487cd377324c9b3f631222f9eee9870c4322e202428a70f665b01e56400"),
        (66, 1752570653, "0.2", "20", "0xa74ae9cee9bd2ff358714cd1e5dc75854d0eff544b046624f27c95388e961c62"),
        (67, 1752570829, "0.19", "240", "0xdcb3163fe9901a3539413cb134863acb34071eda9e79effa5d4241bf77869dd4"),
        (68, 1752570865, "0.19", "5.28", "0x8a9d519e9d0701562e1be21d6370e0c11b20c4b2fe7935ab4652625f137f9baf"),
        (69, 1752570867, "0.19", "195", "0xc140c16b1d33d4fdeef3ff38c7fc7270a6742e5e87fe9895ddb75ae47574d623"),
        (70, 1752570869, "0.19", "39.72", "0x6d8d213304e95705ed9c30747ea2a9ba155efd70b5d8bf57714e51182c72418d"),
        (71, 1752570989, "0.19", "240", "0x50038dc525dca5090e59016247f8098666a9727c9446a763640b00b101bb9d02"),
        (72, 1752571175, "0.1993755558", "1003.132", "0x5019d284faef151bf63fcd29257d2d2c11737972738c13dd2a0c82cbba312658"),
        (73, 1752571297, "0.18", "45", "0x848ed2445524ce8f2086694ca1dce6b2c7922215ac2db94093016d33df3daac4"),
        (74, 1752578845, "0.21", "4.35", "0xc0482e28e1b82e2885dcbc9a76e8685c8b3a53d72a00520417501b9483d5860b"),
        (75, 1752578907, "0.19", "1.41", "0xcec24f4779b8d2334f11904680eb7b87392b22924f28bf79dfc81757d244515c"),
        (76, 1752579313, "0.2", "18", "0xbb8d668d0d610da57ea6437094f97b3bfd8d4776d9e23ebad75d86889017696c"),
        (77, 1752579605, "0.21", "139", "0x03e27963c23805d1f1dbed58c1666d873bad95efe4d73394593b79a60a5ffbff"),
        (78, 1752584965, "0.21", "150", "0xcb3a8798c6d99304b29780c6e1a3d168107677be90b0ccbcdcd5a20e19d71681"),
        (79, 1752585721, "0.2", "25", "0xdce98c8d1054e4d4ffb7f1aab556eab88fe7c85b6b68e771f513c208d6158c54"),
        (80, 1752587823, "0.2", "9", "0x669b8fc3bfa20776aa37c0188d0bd63547ede26d698c6c82aec50f2ed8b3fda4"),
        (81, 1752588081, "0.19", "3", "0xe026dc488478fd48e8cb8708a626f3114164435acc4c76e4da3ad1c576a32f68"),
        (82, 1752588531, "0.19", "16", "0x9f531363a6412e40b6912f8221816555b316bbab7f619dda5fc52f51c1bad101"),
        (83, 1752588819, "0.2", "250", "0xf10d7eb2c0fb7feb42a976aa3d2f7d4a96335f83e3f0eaf72a4cc7118918a297"),
        (84, 1752589483, "0.2", "25", "0xe756f91364e188e5e4e4a1337c72cb432a8492927943712a34132f71a3f85774"),
        (85, 1752591191, "0.2", "170", "0x97fec78c64cfab52a34554bce6ee8f8c1547ec2afceeac3ff62bc03d78a4c283"),
        (86, 1752591263, "0.19", "26.09", "0xe675a1b8309108eb2017586b201cec9ccd2b395835c50da0941bb46b111e4468"),
        (87, 1752596194, "0.19", "190", "0x4f9be1e4ea027d2d95f71b71cd5c1b0dae0b36d7eee4dd353de7e225ef671e77"),
        (88, 1752596600, "0.1899998784", "5.263156", "0xed80bc5ccaf15e854fc8a7302d0cef300b5052c3ef6dd3c7af7f946fe999ac43"),
        (89, 1752596884, "0.1899999939", "105.263156", "0x59af6b48f82631a1204963ec60e85e18703b45cf6ff294d520e2aabfbe642499"),
        (90, 1752597574, "0.189999998", "368.947367", "0xb6566b8fb62c5a7f27aa3c62403d02e8bf25ed2052152820d0a4dd662111bc9a"),
        (91, 1752598496, "0.1899999726", "26.315788", "0x19533d0d11b660e0bcbade58e8be8aa45c81722b9553614b1b998b89681cd380"),
        (92, 1752598682, "0.2187002299", "137122.4896", "0x0b9ba5b94a8db6c7d84ea61724c1a5f04fca8e71e62a6aaf0cc726fed1ad2b52"),
        (93, 1752598894, "0.2", "38.5", "0xeee4d6a65d0dfbe7c39425ce78a3b7c358d806adea13b52632f465e14ad584e6"),
        (94, 1752599223, "0.2099998677", "4.761903", "0xd842c99e8952ab3a53061d95845081eff1b7ea350b6c495f727c93f0ea5eb9ed"),
        (95, 1752599261, "0.212346428", "32.965", "0x3a818c9103dabaacf0ae84721b33681911c5f5a5f701a9414ae26040affbead9"),
        (96, 1752600157, "0.2099998677", "4.761903", "0x986827f80f7a527e82f7296b509c7f4d18f0e7f4bed196272f022ef374a8161a"),
        (97, 1752600171, "0.2099998677", "4.761903", "0x92c6664e6387b99329c6fa8d969f47b42577585a8f6c45dd10d645d96637613d"),
        (98, 1752602445, "0.21", "95", "0xbfc1d8d47467a2e99328d58b3dd97738c2835e31f90d07c0882c514b249a413c"),
        (99, 1752603351, "0.2", "5", "0x45c25c56720ce5da279a307dc58de15295e0147e7cce00d8f3048c70e35e62c9"),
        (100, 1752603431, "0.2", "86.99", "0x8f467385cead858c84299bcbabe05011d767fed7809f973c8490d1bff1cff789"),
        (101, 1752603796, "0.21", "3", "0x3d2829d480c2bb64253fbaa06f8bc0fe7f1a00305c62398758da302526e53a51"),
        (102, 1752605434, "0.2199999941", "111.045453", "0x819150daf6166cfdd05cf94c48e2f167208b95c2b6da8a7ec961bee91814e22c"),
        (103, 1752605766, "0.21", "2.96", "0x5fd28079661f5f60316b963f77a250001d668e0510a514642efa92233ab2dbb4"),
        (104, 1752605920, "0.22", "270", "0x4861115b9b0820a6e6a92a3030be91da7f469a57fdb986e9a57d2ee61b8b74a6"),
        (105, 1752606522, "0.219999985", "45.454544", "0x0ac5c1e2527b7d0364e7cd0bd51cb74fe68d630e47a0f0796c920f5c3d0796fa"),
        (106, 1752607258, "0.21", "200", "0x40eddff994c747a93cda0dd5695048aeb7f8b1102f17403eabe5f688bf14f2b3"),
        (107, 1752607556, "0.2", "167.24", "0xd70933c075127f5ac46e2098048b0f57f8f8559c730f6de18a557b4f0417943e"),
        (108, 1752607570, "0.2184008", "500", "0x28f0a00ad5bb89b87f854b3fa33adfb48d3d7c81f791ff3b044626eb248ac01f"),
        (109, 1752607578, "0.2", "8", "0x880fc58b175ebcf60095191ddfb35271fb9a3efc3ebe63ec0a43da78b39c8558"),
        (110, 1752607582, "0.2", "5", "0x21c97e9c8f157b6355a3ddc0d7725ea8be2f7d56a192a9852961be3bafd9e937"),
        (111, 1752607588, "0.2", "24", "0x5e73f8968c9f42a5e983886c136d9b8b29ed781300a90f8a2606b773f08ccb44"),
        (112, 1752607654, "0.21", "10", "0xfa68b59cb8d805eb974e72dbed1060105350190608ba16f09dd7e64705a57210"),
        (113, 1752607798, "0.2099999985", "471.42857", "0x8f7cf023d225c2ab875945d876908b56e5b5c904d7245a7801c7ff82c75837c3"),
        (114, 1752607992, "0.2", "165.03", "0x104a204578d37fd3115d72f17f4be5763ef0e66decbb1c0eac5f4cd82368d4cc"),
        (115, 1752608596, "0.2", "209.97", "0x7024d28ceb428bf893b03eb07e4769cee0d685a24626e7ec36e3e2eb8c85398d"),
        (116, 1752609222, "0.2", "300", "0x2926a308518644abaf049524d7f1ff11f311e69d8643efbcf6945f936e20e4cb"),
        (117, 1752609236, "0.2", "10", "0xcaf3f3f040b8279b45810737999723be95ec923efc57b34a9ef228083223a549"),
        (118, 1752609704, "0.2", "5", "0xc510648a439816dac717ecacaf6ed88dcd0c213c4c9c13e179bb6a93647aaa4b"),
        (119, 1752610678, "0.2120958786", "3606.435", "0x3b96bfefe651be23b91f338afcdb8d51c04a2e948e8565bf55c555739eb1d110"),
        (120, 1752610810, "0.2199999936", "90.909089", "0x7339dada26879ba9f76fa381165e62294290108e9dfb8bbbab8120e471127e49"),
        (121, 1752610958, "0.21", "2", "0xff92c0440514aa771e745467e71a569bb25666ae58b04a772ff283e774880021"),
        (122, 1752612375, "0.2", "255.46", "0x6fb75a847977bbdbc8b5f38cb9ab0a1034e5784b0c6a42c5754a2466b4291ec7"),
        (123, 1752612389, "0.2099999989", "585.714284", "0xec960fe235de8a73160cf052e54d9e0d78b6df304f86a34a9c8bf83b81bd4ca0"),
        (124, 1752612409, "0.2", "5", "0x53b6cd8c5f68b9263680195de2e91319c223191144bceb4d5036bdbd82127832"),
        (125, 1752612627, "0.2099999964", "190.476189", "0x64cb3edfaef83192e6b7baefb30ddfcd5ab52cedef5c175b0234eeee877a2672"),
        (126, 1752612949, "0.2099999902", "71.42857", "0xc2c73fa4c7bac8700b30145b617067b175115e5035e3e7ad82aa5ad1a0ab0046"),
        (127, 1752613105, "0.2099999934", "119.047618", "0x9779eac5df9952ac5f5084ababb0232683d59dd7ae9578b96db44c11bf1997ea"),
        (128, 1752613929, "0.2099999809", "30.952379", "0x57100d3b5b4fb51db5a353b5fe2c6d4396cc928acc96bf5319f13273e20fdb9b"),
        (129, 1752614373, "0.2099999573", "14.761903", "0x9d1585013853ea3bc4998cbf8193afdfec9d1227ddd0f48d8f4d1596f7051ab9"),
        (130, 1752615001, "0.21", "250", "0xcddc0f0a1be8a0501be6924dfceee6137cd01626ba6cf4cdefa2dfa65cd4ca92"),
        (131, 1752615691, "0.2099999984", "476.190475", "0x567784e5658e8c95564fac295007ee5b63f26570652b2df981ef9e6385ef0fc4"),
        (132, 1752617199, "0.4138959498", "395.461705", "0x7f5af4a98bb87f1988de083ed50b294b6b151973b47cb9a4758573953d30fb3f"),
        (133, 1752619705, "0.31", "70", "0xafe020616c6cd6c43cb9d11b54f37065f6efd0861202272091e7af0ea3aa5c0f"),
        (134, 1752620639, "0.26", "30", "0xcc42b9052c9de1425590d649d6a4ec133171ea23c3c9efd198b61c0ed2be78be"),
        (135, 1752620641, "0.27", "41.99", "0x96dc4e0ea7090f0277f621f80cd609ac497d1c921f5f697d6d3082cb3dc3f2a0"),
        (136, 1752620645, "0.3553571429", "2100", "0xddcc9abbf986d1085195edc31ed1a6342454fedc8e7dc940ad491c79b496764e"),
        (137, 1752620651, "0.36983875", "2000", "0x4ad9e7db94ab0ce53fef69dc5a351beec164a3cb6ab25ceeff2fa40ea65f8a1f"),
        (138, 1752620787, "0.3895475167", "2094", "0x0fa0a682a5a54e63c1321c63b8aeff09002d552e8338d7ec1818c2443716bd0b"),
        (139, 1752621353, "0.2088785714", "70", "0xcff564d7becbd7006ac2ab3d7e70bf064a394feefc9b1194d8b93848dd48f629"),
        (140, 1752621863, "0.3458497947", "72.285713", "0x51a2a41b9e4ee07fe726c19ad477dd33fa1cc3b22379890686ad11fd0b8e3742"),
        (141, 1752622059, "0.3499998775", "2.857141", "0x118c3e71ebb24cbee45bffd089e4b393e31a5873b6e0a6e961a9a232ab62b7d2"),
        (142, 1752622195, "0.1810456", "500", "0x50389515dbc7c3351c7d989d8fd3b65cccfa434adeb2e4e6d452505cfe0ba4ed"),
        (143, 1752622221, "0.25", "76.67", "0xd1e768f3276025b2ed077ae4f5018076d1068a5007ec55d36adf44e114a092d4"),
        (144, 1752622225, "0.3440115536", "1133.85", "0xd093bc2b715e99bfd8a4e0893d92e8329f82a8e6ba89d375fe0073a0566dfbee"),
        (145, 1752622469, "0.36", "55.23", "0x0d5fe91083bba61d6b01cc16bcc8c7c7882f9067e9fb438b2d7b90d518d6dce3"),
        (146, 1752622875, "0.4691308127", "345.15", "0x603f8bdc7d45d6b94fbf37f6fbe57c5ff07187d92e0a0526d8c20675eec8649d"),
        (147, 1752622879, "0.48", "2", "0x84528b498d2e2c50c829118b2795c4601738c4b0f3e8c291dabc34a28c85484d"),
        (148, 1752622959, "0.48", "48", "0xd6b8a36fbc071cf7e393d0f1bfb07e1a750b7060cd7ce884d03c0ddbe4aeb6f3"),
        (149, 1752623037, "0.663168473", "1470.74", "0xb9b68bba032055a7aac6b68dc118a8cc83b5084293213101e27899dc337a252e"),
        (150, 1752623091, "0.65", "307", "0x45a2766be012294dec2e41ad4d3d6fb553f51628473ca5121748a571016298a2"),
        (151, 1752623103, "0.6545454545", "550", "0x9ab62a13c3953937656e0f450c37bea57e1ae408e24f63c2df3497ae0d47eec4"),
        (152, 1752623107, "0.65", "400", "0x0bc3f61ec2d89ac30d797a1f5f051a21a6d0123f8b43fa4846f661e775c02d74"),
        (153, 1752623339, "0.6899999869", "14.492751", "0x796b7fbef54bdef6c65726d5f8692b8383db2e262adb364cb755168b51d7b3c8"),
        (154, 1752623429, "0.6899999917", "7.246374", "0x4691f40b5e1a3b53981fda85999cdbfaf034a00292abe781da7fee8678a04bd0"),
        (155, 1752623735, "0.5", "16", "0x8780ec6dd3e43ac0b487e2501dd0721aa9bbbc1e78a125e6fa88092afda1e4cc"),
        (156, 1752623751, "0.51", "10", "0xa043a747322ad898c973f8b4fe8fd2e72fed924eff4aa30f64fd50dfc25540c9"),
        (157, 1752623763, "0.5995699946", "1084.87", "0x293a73fdc3bd7f1931d24a306909053a9e051ded391e61ad95cfe3c28560227d"),
        (158, 1752623869, "0.6", "202", "0x049877b4fb277b393e2fe099b460a188a6c7cadcf74338d83f0310190f58f074"),
        (159, 1752623869, "0.6", "35", "0xc5ef968e1b028354b96312eaa3d3fc0f39f654a27777ae8a48cf8561373b9f0c"),
        (160, 1752623873, "0.6", "2.01", "0x946bf3c8430dc57ada51b59bd945c30e7f3fa2906e5faaa779ee87c344e75e05"),
        (161, 1752623941, "0.52", "13.04", "0xfd1a25c1446ba9da68abbd3c30db3b04b9135d0b69c5928aeafc6790d699dc68"),
        (162, 1752623949, "0.52", "10.01", "0x757a99c2c7999ba0391da5b521dfd73336f221ecb4b53ca93ae5ab37fd0c2339"),
        (163, 1752623973, "0.46", "16", "0x797f12e309e4ffe1d3c4ba60930e2d77d577bd7f29ef72265d5a4a7680e5c181"),
        (164, 1752623981, "0.46", "10", "0xd2a0ce5df4cc2018dd7f29e301f5b2aac9c2d632332b564f3aea434bc25e710e"),
        (165, 1752624041, "0.54", "10", "0x08fa0479964b58ae36ca6dca971cf34d4bbcedb11107d05a3e5395c4d6728058"),
        (166, 1752624119, "0.48", "2.46", "0x3d79ef4cf7458a133ba2264dc807d6379bd50d9bc1608ee9d14e942d7e9431e7"),
        (167, 1752624151, "0.47", "1", "0x8f66208f099382621e2378df8d07e6e515b1b8a33f97f1f7b15e3f932731c91d"),
        (168, 1752624169, "0.48", "111.09", "0xdf0ad5fe831874619cb6dc439027311483b207909e7ae6d5f4c7b92c1f35ad40"),
        (169, 1752624179, "0.49", "29", "0xc25a07c7c72aef00b33980514dd85c9349c4b271041e91cb939488b34f30bfdb"),
        (170, 1752624187, "0.49", "21", "0x3429dfb331e80dc1f36d6f269dee60700fc746ebd9573d557b1862b13c077d67"),
        (171, 1752624189, "0.5", "9.87", "0xf18303be9e440614109ed29ac1f780287247b0304ddf73b9fa62d177f0aaf63a"),
        (172, 1752624325, "0.5101234568", "202.5", "0x0271da021855d8063f73006ee5a4f38c0b02cc30a90aad4ecc62b4c70a6491d3"),
        (173, 1752624329, "0.51", "23", "0xc2797c16f2d031fc78d926d4f3dffbbac9f0eb840d72f074d590a1049e299693"),
        (174, 1752624513, "0.44", "5", "0x9136f00e46f2ac13aee16b19ca8134fdd51ee352f1250cc41d0092c58da5a5e7"),
        (175, 1752624637, "0.4699999969", "159.574467", "0xd8d0c3237645f6d5e80ed5d033f67a0e35b06cfea0152d7058ad28eb5beb9c31"),
        (176, 1752624659, "0.4821507051", "931.09", "0xdc41ab65768e6d7c594b6d37137ff54a521c53b5d5d7ef518af9d020c3b5abac"),
        (177, 1752624783, "0.48625", "80", "0x2bd50899d37b1ec8d3c7ca63bba18399bac0e360e834c8afd8d36ecd74a1876c"),
        (178, 1752624801, "0.4990670946", "535.96", "0xff89bae4d02021349889241b113e35946f9a39224a1d00551f856cf2e179a3c0"),
        (179, 1752624937, "0.49", "50", "0xefee4f04dcceda511190bcd3e1c62620353978a18a39a147da9ef6d8f5d10c14"),
        (180, 1752624993, "0.4929763676", "167.99", "0x78e5bf3d045d920bb121a2e8726deaeffc8e98baa8362d1567ef839472f7a792"),
        (181, 1752625003, "0.51", "801", "0x90e7ce4dcbe4d6eb4b256c0bb7252b9d9b505a809dd66a1c79b094c4757f5c18"),
        (182, 1752625015, "0.5199999813", "19.230768", "0xb4657747c150092489e2c5a66d2a35881b884b444752c88def0d2cb00ecde672"),
        (183, 1752625113, "0.54", "31", "0x266c88d9bf2ba14e236ee194b7baf206474938a7cffc4ca1ab07c80eecc05856"),
        (184, 1752625329, "0.5199999813", "19.230768", "0x32ae093604f7f18dc149e1cc1befaae8a5dacf590ecd13774a4acd423f39ca62"),
        (185, 1752625761, "0.48", "10", "0x5bbaa51dc8a620699971a3bfea75453821ce18c1480cef3b6d0b5887af85a969"),
        (186, 1752625913, "0.5313664778", "409.52", "0x55a7a500519a1b951321dd1fa4477bf30f775fdada8e8071d7b12dcbf568caee"),
        (187, 1752626015, "0.7663588111", "65.243586", "0x2b42e03927b36f7585e589e42d02f4b50e91059183653563c002825740ae0683"),
        (188, 1752626167, "0.62", "5", "0x6462d40968c85ee6a53cada64e3f05210d31bf590f28466d6daeef4a0759da6c"),
        (189, 1752626201, "0.6199999974", "68.467739", "0x93117414b16819be7f4320d58b6d79d6b3480fc9fa0b9c0460a5a6eb50ffc21b"),
        (190, 1752626659, "0.62", "50", "0xacb77716d73b5c59024bd0b5408485170afe816c4b87acf4ac6991d23012082b"),
        (191, 1752626689, "0.6276711083", "351.97", "0x3375315d45853c7db8602ac9c1998f83549aee33cd02e1d1649112657e952db6"),
        (192, 1752626919, "0.5998722498", "1409", "0x5d612ea00996f7eabec552bddad8c2172ad0d0f69db4ba6b585f77da3503b2c8"),
        (193, 1752626925, "0.6581768584", "43.99", "0x38cdc79935512246e444403c4cd2a855f9719180c22ab656fe2dfce0c7444e5d"),
        (194, 1752626931, "0.75", "40", "0x59ccb56f630ec315a6e1998a63ee3dafaea9772740c3e33e5b76b869e128a603"),
        (195, 1752626937, "0.53", "349.06", "0x67d597f7d555f38228e7fa4e09ff1943e592665f4ec3b75c4172be392f85e9a8"),
        (196, 1752626993, "0.6683333333", "300", "0xc9e6a716d33df7e39fa52f34d114d9d2549a01fe76b8ee71bcfbae64e418d401"),
        (197, 1752627127, "0.6386187845", "362", "0x0e92ff179eb5bf52bb2ed9c39cfc3fb8b88510ef1eba3c7eb9d4b16be544f95b"),
        (198, 1752627149, "0.6533004231", "709", "0x8e36a4fae88750a90366cdb8c926f27ef9268ab4006d81e2af4786dd6305fee6"),
        (199, 1752627153, "0.6655017606", "1136", "0x4ceb90d677af6ec59608410a728215f72ac1be2a1ad542072d15417206b2d488"),
        (200, 1752627159, "0.6895", "1000", "0xcfe5b2b90188eab1b36eb20effef0c33f816ee4f826dc31d3fe7a94eae13d457"),
        (201, 1752627159, "0.63", "256", "0xd3c86baf44cca4c185f401593af82442cd273b261b6b18df4ea4d66db779e2be"),
        (202, 1752627339, "0.716218518", "1374.99", "0x4f3928850e7e6c98503973125dacb9dc8ed73a25071e65539dcb1fa35e9ac0f9"),
        (203, 1752627365, "0.7899999739", "25.316454", "0x5c1b5faf18afce67fbd6b8403b3073c10830fa0bd3acdd4b04c35c8bc1b35a87"),
        (204, 1752627409, "0.7454833837", "1324", "0x2dcc10237a4b6900d6045a7d7361d96ac85efdb4d53c3e57d731298a1e4d1b59"),
        (205, 1752627549, "0.75", "50", "0xd77381acf1508b1f1252dee96a6d470a3809f764b9da042c999323624fc0e51b"),
        (206, 1752627553, "0.77", "50", "0x9f76a628f3443699e22662a93e3acd0dee43ab443e25a4d08502a4691ed037ad"),
        (207, 1752627625, "0.77", "50", "0xc2c700fcf0b1081bfc42d73672bbfd9b9e8cca4f05c176102bd51a3f405f7957"),
        (208, 1752627653, "0.7699999969", "32.46753", "0xdcff1274c96cdffa1ab212fbdc1e91bd76b1018f1509154343bb7c025b34ca3c"),
        (209, 1752627667, "0.77", "17.53", "0x759a60792c00bfc0295ae64c0922cde2df1b7d365cc6e9cde65c7c8c7dbadc4a"),
        (210, 1752627675, "0.7799468746", "88.47", "0xf11a0253d2e2c1993ae48f38c1779bd3877386c7a81a48c61b2b16a45ee89afe"),
        (211, 1752627703, "0.84", "25", "0xbe4b171ec3612ae99f45994926da989af2a6c0fc80bee24bd6f1c01b711bc817"),
        (212, 1752627975, "0.752", "250", "0xe52311342e3c34f172df6cd641b70e5311f71db15cdbac756e04bf4071c2b77f"),
        (213, 1752628071, "0.7599999954", "26.315787", "0x017875d0c68fa472920491092b76d27b5ab1c1935a604f2f1502bcc63822d6af"),
        (214, 1752628201, "0.79", "200", "0x995129f2633cca3f51b62d457f5338df09fda2b22435c693e9cb515602b57d2c"),
        (215, 1752628737, "0.78", "20", "0xb86e306f71024bf73ab2e6921a65bada220f51d70f2af7fa7f1e3db85f57afeb"),
        (216, 1752628747, "0.78", "47.53", "0xc496f8a8a4bfe8ed7495c135ba39ea52a9f70cf20a271d4835828d92e58e404e"),
        (217, 1752628845, "0.79", "100", "0x54531821e477e09be2f15cc8c744e9f9c85d0d865507f4c5096e52c9edbc4c1c"),
        (218, 1752628879, "0.7909909141", "293.0375", "0x15f22532075a661ff09fa6b605792d200a60728f149fc6444aab50a83eb2938b"),
        (219, 1752628967, "0.7799999868", "10.602563", "0x1335d80df169520e4810696a6e262b2fa79c0578aa99e503b098c970ad9ebc0c"),
        (220, 1752629083, "0.7899999959", "39.240504", "0xbd60825b23f00cf5dd0f58c4749d5b54942d4054689808f640e63960d5c87934"),
        (221, 1752629173, "0.79", "60.75", "0xe9e654b9980bb34200f6c8aed21b9f500ef516dea046e7cdfac09d0c7b44bf47"),
        (222, 1752629229, "0.8", "975.96", "0x4c45d0572b3ad00a8a9dc5c7b418960465ec78203fe1c0b279e802987a4a5f7b"),
        (223, 1752629241, "0.81", "1000", "0xd27f33e013b1926ebce546b2320cdb87de49f94bd0c6fdf482fe6c678e3b6d76"),
        (224, 1752629261, "0.8299999991", "43.373488", "0x7a052fd006cfb9b306472481a5001965b751b2ca9b1178a30159a8e0f99e94fd"),
        (225, 1752629275, "0.83", "6.62", "0xefe5df68ff6793bdf28619a5e038f497e37a525cdb31f692f03137706811485c"),
        (226, 1752629303, "0.8499999864", "58.823528", "0x9129c831fa325551cef7f1397904522b88f61a3e7219ec9eae37f4b0a231e96b"),
        (227, 1752629323, "0.8451958871", "799.44", "0x895ebbc7a10adf793437f61a7a41bcb084261945fac5e59c3789875149b9c95a"),
        (228, 1752629399, "0.8751611563", "1028.382018", "0x061b2f5b5b04828451a14fde298454b80b221666400111b3a36a6915bb495106"),
        (229, 1752629403, "0.8899999555", "2.24719", "0xf63d76a92440eb3f128501e3503020316f530221e7cb3ee196c29e8f523cc789"),
        (230, 1752629737, "0.86", "25", "0x5242d6cf41080b7d97a9f5f6e6f44ba9d5df8c42cd820720f1b6fa18931c7893"),
        (231, 1752629741, "0.87", "99.28", "0x8e6720ad9db9e876a5271923d747d8e03aac4b08438836ae9ead7e212011fa8f"),
        (232, 1752629885, "0.84", "100", "0xde645939929601874e6098639162610c7ea7a50afac4f3092237b6f89c601402"),
        (233, 1752629989, "0.8690796446", "1150.642523", "0x9ba3f326042c1984b18bfd247125f8ae480ad4b01fefdbc1982bc161503db882"),
        (234, 1752629995, "0.8718629027", "1146.969317", "0x27cbbf38214f0d58932171069649612dcebaae6e547768b2b9598bc2f653d22f"),
        (235, 1752630103, "0.8139427683", "160.75", "0xd520e4c92345b8db7a2cdee90b8c59fb38735dfe0cc43d50e98b30757f328c69"),
        (236, 1752630189, "0.82", "301.52", "0x311329f029e606a4959cbf247a4e1380c6b7ecc9a72b74245bf49234de4881c1"),
        (237, 1752630275, "0.82", "10", "0x026b32089d39852b310931ed8e86d481f0848657b186ec3ab35db0f43c8dca53"),
        (238, 1752630385, "0.8561393274", "1049.04", "0xb537b4c2f91cb49df7a70ea1eefefe8cbd573e1f91f192bbc463d7971bf42ff2"),
        (239, 1752630515, "0.84", "50", "0x657d126d0665a5edb88dbc3c931541bdcd9c235872334ce66256799148a892c0"),
        (240, 1752630537, "0.85", "5", "0x1fcd3f430d89bebfa353a00180e641a51047610e90ee0207cb876710e4244562"),
        (241, 1752630537, "0.85", "25.67", "0x2541b7d68e6a6b6155e97a12e0b5cf9f451dbbebe828e0cacc8ca5208fdf5ebd"),
        (242, 1752630563, "0.85", "75", "0xe664240c837024cf0a1e54e7be9295b793e90020ac8412b76ca97738643ea1d9"),
        (243, 1752630705, "0.85", "100", "0xa8ddecab1bcd68a67845a32227b8504f6bbade9928d64414cd70bc031b56a304"),
        (244, 1752630895, "0.83", "150", "0x45b97ba2115f40dc9a52770d29108982f09004cb52447ca53d375612bad58950"),
        (245, 1752631171, "0.82", "50", "0x8eb8682cc13056d3c40dfb659aad4d127b9930c09fdf7931cff9f63745099798"),
        (246, 1752631173, "0.83", "10", "0x51a4201b36d456983cfdeb5f61105dbc1402d9845e933ba2d91ecd46665b1b2d"),
        (247, 1752631187, "0.83", "10", "0xd4b86b08efe651a3c4751ddbc2c12584c7a290927a14e21105333f6463ab2e9f"),
        (248, 1752631243, "0.83", "10", "0x433e6d9c38cee4ca0ed8f650b3f9a59ca939595632be9dfc0eb1cfee72c7b403"),
        (249, 1752631517, "0.82", "40", "0xc23971cf75bc23f08cab900a89d2551039d1330665d30ca8cd60da9390f3a173"),
        (250, 1752632589, "0.82", "371.5", "0x66efb362da5601fd8b9b1ad338517eb2cb9913071d0fa3cc1ab0d81524533915"),
        (251, 1752632917, "0.83", "10000", "0x65e74c5e6011cb49ad6d5328b989914803488ce7e20d78e61742449dec66df28"),
        (252, 1752633427, "0.83", "5", "0x5d55d34192195ea44fe38e5805de3eefde370343dc1854f0a1d9bc4f09898a31"),
        (253, 1752634678, "0.8405023182", "118.976469", "0xf73885cb8d11e79caca8f4ae386c36ae764d6715086b2089ed276c3d23d3be00"),
        (254, 1752635172, "0.8399999202", "11.535713", "0xb61e086c7a289205eafa89ddaf0386eca6b96e19e52870d20ef4b1f0eec744ac"),
        (255, 1752635386, "0.84", "225.46", "0xf4cc09c38ecf7e9f86517b8ed8b9c1bfbd5da2444cc290a1ac3041dc42bc7d68"),
        (256, 1752636118, "0.83", "121", "0xe9cdc7e593afb33a58af5353ed545c509cacb403b8ccc0703b2fabfeb4686227"),
        (257, 1752636198, "0.8399999896", "11.547618", "0x6fd858ce0b8c08d3903cfaf98aca0022683aec616c58b842471768714edca509"),
        (258, 1752638366, "0.83", "4806", "0x352f40a7ce5683587ffd1629def6e38c628fe202ba835b4bf7681dee275b6166"),
        (259, 1752639110, "0.83", "100", "0x7a7166200e767a8e1918bc3fc24466c871c12d78c455f10db28737ed193768d1"),
        (260, 1752639328, "0.83", "275", "0xc76fd051537d242b320544dbf697d8c73ac9966fefceb0ce446e0badb38e573f"),
        (261, 1752642058, "0.84", "200", "0x9a8514fd511c5a4b38ecdadb66b27e9542bb042c48951ae31aa355d00b9627a7"),
        (262, 1752642726, "0.83", "585.71", "0xf48a8efeaf8c93f524f5b1e37d92a7c15a85853a0a7c3c4dd7d5720c993aaeac"),
        (263, 1752642946, "0.83", "133.33", "0x0d6683d3ac6b05809eef69d43bf4bf60dfc766f9634420f07d4cb89111a7438f"),
        (264, 1752643739, "0.83", "1354.98", "0xdfc7235106eb3af45551ea99723f10fd8cf60d48135ed6f4bfa9e062518dd8c7"),
        (265, 1752645445, "0.84", "100", "0x409925a0ffd8aafadaea9461a739b8a9ee869b08c754191a34f2779f419eab6b"),
        (266, 1752645463, "0.84", "100", "0x17c0fd45636a4644545da8976d2e60722746e869a7169771791fe7dd645c96a8"),
        (267, 1752645929, "0.84", "808.87", "0x47db7af1ab34df7602f24991e1f36183222c1c71cb45b8da33d42d8aeb0496c5"),
        (268, 1752646159, "0.84", "1000", "0x195923a6e3541e9012de758165dc8f4067174b5feca2efca996891fcfc0b50e8"),
        (269, 1752646501, "0.83", "200", "0xfa37259955baf561c324185c51930d91cc18aeea3211985b1d544c705e706d36"),
        (270, 1752646683, "0.83", "40", "0x98e51085c7531ada38e4a5edc766c2ac8ca3836ebd55693678f5bcb2c8ffbd00"),
        (271, 1752648549, "0.83", "23.8", "0x687c2ddf4f8ec320b6f2cad22a58ed3a218ca0d373450069bc3cf1fc2fd88b53"),
        (272, 1752648619, "0.8399999754", "24.416665", "0x71bcf887ead7744736c2096ec18aca7f32db6cd7ed609741a020a7a994cc62a4"),
        (273, 1752649715, "0.83", "504.02", "0xf542fbbd1c9117f3fc91bccc4f8a41108a3653c1091d0352f11a0f6e33565635"),
        (274, 1752650199, "0.8472296125", "5463.64", "0x1abcfce1820d58bd29f1852e49bc674d61989d53e520cb251c3f892c1700dfe7"),
        (275, 1752650303, "0.85", "18.46", "0xfd34ba4bb517db6f492bf36c3f78d2ab25e07eea3b03f5b8fb23447fe5a14261"),
        (276, 1752650607, "0.86", "59.88", "0x11ea408f59b5384c71d82f33c59123ac889f8f0eac061c23b75b07a8bc4891a5"),
        (277, 1752650765, "0.86", "11.6279", "0xd8f7419742234e37f9de791dd7c6920b5f48fa2b93ffba407b8b6b312fa3a67a"),
        (278, 1752650789, "0.8599999987", "46.511621", "0x3621f58141a43f4080003f954d3c8c2b0f38d54c8f246e6c2a5212ab844b8735"),
        (279, 1752650971, "0.85", "9.99", "0x033d7c3b8850f95f5a1fe179f95acbe0eb80dfbc4151cf4193469f5a2bc88f94"),
        (280, 1752651117, "0.85", "74.19", "0xf337362c67252ff97c8b31cf69423096d756c2f047db87ca31d18e44e3f09bb7"),
        (281, 1752652243, "0.86", "174.4186", "0xe0a6985b4360e868ba4b2a4a911be9d045524b4ebe9a9a5523bda712ecd71951"),
        (282, 1752652773, "0.85", "310", "0x89f727358035efb0a52cf7829085ae3cf47d6b0137bfcae111e33859ed922815"),
        (283, 1752652781, "0.844689089", "3189.98", "0xd03cdad50004df8cceec77782ca44b685780519cdb0b4c36781ebfe5ede8bb8f"),
        (284, 1752654313, "0.8599999988", "64.034878", "0xb02f961257c772e1f02562b38448e2b910d6640c021830ca9af6ca92236505fa"),
        (285, 1752655129, "0.84", "1003.13", "0x73e2042e62e81e293d18cdba96dec090aa63152c524a53e0416492f2294407a1"),
        (286, 1752656293, "0.85", "26.31", "0x92f3df3d1d634d8e48d1c8f5a6ce7bf95396015a0da99feff9b39b40bdff3281"),
        (287, 1752656361, "0.859999914", "1.162785", "0x42b3133dae2312253892b74e1d6e13bf366ebc658ce9f5b9e255c938505f2a90"),
        (288, 1752660344, "0.84", "64.03", "0x232a0de4f1e6fde9d8e56a7ff53d3b6d2c5dda9acb4a83201a3c8daaf469ea98"),
        (289, 1752660522, "0.8599999656", "2.325578", "0x09747416d8a4b653d9b185e303e2bd8a061506f2e15c5f7c414d489b1dafecfc"),
        (290, 1752662235, "0.8499999961", "12.941173", "0x7c2b626c302c831aba9a60f202afa4cf7407e49c5f282dd3f789aa4f116e3176"),
        (291, 1752663552, "0.8499999968", "30.823526", "0xd97be6514b7923aaa206d37f2d13109439c039a5be56359c8bb1977d1853bac1"),
        (292, 1752664001, "0.86", "55.81395", "0x7fc3b807e0fc532fcb15789bf1aff0c453135f7744e381e4a3261586bb7e495b"),
        (293, 1752668956, "0.85", "50", "0x29e66211cfec25043eb0fe72a0dabbf8bedd1e1d1e2d2f3b3601193f4aaaf5cd"),
        (294, 1752670610, "0.8499994475", "1.176469", "0x3e566510ab0fa3c723740beb357972e0bc6930c6667b2dba73d26ee7012e9213"),
        (295, 1752671032, "0.84", "19.23", "0x1464600cd340e2eb7f78db25c2826870cebc15d3e77e3014b050390199a3256b"),
        (296, 1752673106, "0.85", "10", "0x256b6421b6968e2519fca8086401c9d8f1fcbf757758e5258d55e1293ebe1e07"),
        (297, 1752674610, "0.84", "178.46", "0xa5cd315ab2f82dd42d2e1a27ed3c6fe1829a23f747894bae78f44b82bac2a474"),
        (298, 1752676176, "0.85", "5", "0xe38d935cf4da8b427748d3a4ab4595cc92983860c397c4ed2954f5898b1f787b"),
        (299, 1752676320, "0.85", "400", "0xc5948a98cd5d3ce57df17b6e24606fa08c7d15b09dce831e40204bde5ebaaa53"),
        (300, 1752676838, "0.8499994475", "1.176469", "0x9a42110af6a7b267123b38bf0f4d56b03b2854defb8bb4d4987446b825b0b6f5"),
        (301, 1752677786, "0.84", "4925.46", "0x0fa15f23b1cba328ee1725343229ac295c6e532404c0a9486387cefc602c45bf"),
        (302, 1752677826, "0.83", "15", "0x3bee26c5f77f06e629fbceaf3a914b424e7a87ef8fd3c787254c34e24a58f5bb"),
        (303, 1752677888, "0.83", "5", "0x51dd10b5e0aa89b9c9f1592fd4794b56ff050b4e0abe344b9be91c8721a56ff4"),
        (304, 1752678740, "0.8399999983", "373.369046", "0x8c96fbb2ffca43af985b21e605d8bf017d96197dd0f4ab16517953f37d4b717a"),
        (305, 1752679788, "0.839999796", "3.726189", "0x6fd83946499f37aede1a3449462876e5d3ea7096e86394bb303fc6a35b9b4a36"),
        (306, 1752680232, "0.83", "263.81", "0x292e88a672e9606a7cf653e2c6b628327263f7b7953ce59fae6f5505ab8da208"),
        (307, 1752681858, "0.83", "1500", "0x59f8f44aa4f9b45d76f6fd4cd08443672e44aca47ae1f683979f0fc4953f11bd"),
        (308, 1752682468, "0.83", "72.28", "0x7c035f46d33372d3940ea7989178a6b4c34938ef6fbeb7595c73449fe4857e2a"),
        (309, 1752683154, "0.83", "32.96", "0x7a3ad7384a6698f0781ed1a501e849f8760467c9d454389a0251b0ae36f4e788"),
        (310, 1752683780, "0.84", "400", "0x7e0b578ef5f3e180b962535db51cc3454763aa5a173195ff6f33d4c7f4f2b64c"),
        (311, 1752683800, "0.83", "400", "0x6fdfc461171cbe053cfbe4327296420597c43f677e2325ec8d5cfcfe86d5c32c"),
        (312, 1752684120, "0.8399996472", "2.380951", "0xa12ab3f60120a6fd9c43329f8e8ca5e55308445c17d74f53e320230cafdb5bee"),
        (313, 1752684290, "0.83", "1000", "0x9c8b6187887a630207af0fc7b9416d4b18b5c1999482bb72e735f6a0171b04b1"),
        (314, 1752684496, "0.8399999798", "23.809522", "0xaecebf133d4d46042570772a0c6ebd2c45c3a0c56a4c87f66c03909ef752880e"),
        (315, 1752685170, "0.83", "500", "0x1aae9837bd36012967214e62a4b0842adc2bd6b1594e155abc28c3dd36a21f93"),
        (316, 1752685252, "0.8399996472", "2.380951", "0xcdaba8eebcf9f2b15da51d08b660c373a23325963d58707905ffb1e56934cefa"),
        (317, 1752685370, "0.83", "3093.94", "0xb05b6e0563861ba9e7b7a5ec5b84cc7279ea3d92b39ed4409d04c3a6afbb4352"),
        (318, 1752686944, "0.84", "50", "0x2af499e30ea78674ce335e3ad8a9edd34b4514e24321470f30c5837d3e1d42da"),
        (319, 1752687328, "0.84", "1.190475", "0xf34854942a2f2b47e8c172923ae18108db267404622926ec55817318869dc7f9"),
        (320, 1752688442, "0.83", "71.42", "0xad22da0f021a0aae2203e1bae2aabf601c151a7702c95e833141ecb3cd8fce66"),
        (321, 1752688560, "0.84", "2000", "0x9ec64336b6707adc68ebb9f7dce33b4a2bead34f603b396990389f03453cb73e"),
        (322, 1752688710, "0.83", "50", "0x473e0fb2a6864d4b666a6816c396f8b2d22e7e219d5e9292475e7a8ae2e98091"),
        (323, 1752689740, "0.83", "4.76", "0x923f6f9fd01922bed8633c2bbd3c386a2d94117755a40e4cf0b0dc70f42f7d64"),
        (324, 1752690194, "0.84", "1.190475", "0x1cf3dd1538887c2586a7b0a3fc698cd4af126360d8b40911135a4ada6c21676a"),
        (325, 1752690476, "0.8399999316", "10.523808", "0x483afdc2019803e1b7958c815de8e9818f5755369dbe255b62208f6e0c6ad271"),
        (326, 1752691928, "0.83", "46", "0xbb15c60706c6d9c75dc3a42078c8ff433f681331929d3cb55d67486cbcc34dab"),
        (327, 1752691942, "0.84", "40", "0x10cdde5b35f782a4075ad2817c68d8721f35c036a9d56603cb2c52cfc29c61df"),
        (328, 1752692228, "0.83", "939.77", "0x5f237a03e48960be85243aeba6450dc24b3d54d541b647e15e9a7dc52a48b4fe"),
        (329, 1752692984, "0.83", "951", "0x09c8e0c8302dfadc5c652c9ce5917038b4b2925efbdf0d8bc5bee25b3e3a7335"),
        (330, 1752693550, "0.8199999836", "1.219511", "0x3f5e2cc4ffbf4d3002b272acaede26b132ffc3a6f47d6f18743cd443cf167b42"),
        (331, 1752693582, "0.81", "1.21", "0x2d6d3b01dbd3120e065e6a8306e1bde30a192a8f3f9150a64cb39e693dc94611"),
        (332, 1752694178, "0.8199999836", "1.219511", "0x4eaab2181e94ad0f3f9845e8b212340076fa78afb1635b2007941f101eacd043"),
        (333, 1752694386, "0.81", "1.22", "0xf198f5dd3a392132f4933a3a7d361db149bc8d84cf461234484906b835a4c7d0"),
        (334, 1752694872, "0.82", "20", "0xd680d0161557fb42fb63df1ca41766cb669a337ddf7257af414bf9757448acd6"),
        (335, 1752695872, "0.82", "780.48", "0x7c3f2dc95be0ec6696d590cfab9b4756cd4e71d95fc44bbd5715d53616fdf4a2"),
        (336, 1752697202, "0.82", "646", "0xac41bdadc14eff2fe4e5746fb31a231a8192e7ac2a1648330a9c0bf846736a88"),
        (337, 1752700422, "0.8283803553", "957", "0x30758d53bf195e65b0c967a4527d284fb5c69a7c972cc66460d359ce07d0cada"),
        (338, 1752700916, "0.85", "124", "0x985486498091cf3aa465e49b55560b8e6c7fec6126d52cceac82231672d8e3f6"),
        (339, 1752701176, "0.8596574036", "2203.121838", "0xe694ceb629be9c098334ccd26248fe4842eafa6b3207a1042325a9379c59d922"),
        (340, 1752702668, "0.86", "75", "0xf64afbad760c105eb57471067af6a42822cd0009afd9f5c23a9b70afc1b1e7ff"),
        (341, 1752702692, "0.87", "976.47", "0x7a6d006b614ba51c943a4c555a89a68624212245c8e8f980781ac8c7a0bc2be1"),
        (342, 1752702770, "0.88", "50", "0x95a98868d07841467301bfa6d5133584fffa24d72ee218194dd701b549ee37f8"),
        (343, 1752703316, "0.86", "15", "0x1f04238d33870dc22218e386c5746509dfbed077764a2335a532604fac785c3a"),
        (344, 1752703536, "0.86", "79.23", "0x871051be383731fc74b548cda9151145c2d28936baf81b5466e0f50bfd41f300"),
        (345, 1752703542, "0.87", "85", "0x28eecca685cf34d412e83d5868635e7e92ac696a5e4602a4b6997a71433d249d"),
        (346, 1752703986, "0.932137931", "725", "0xef8664b42d1461a3c4be1d6cfbecd3a6a2889a26e437b52fe380e0c5555c2bce"),
        (347, 1752704012, "0.9771573604", "197", "0x959f1688c41be625d8d7fe3539e81d98600abedfedbf9686e21307daf81de06e"),
        (348, 1752704012, "0.99", "149", "0xb5b0f7350bfc839f03c5483a719f5f3627059f7b3dc0a0c374f20388316f9eae"),
        (349, 1752704024, "0.99", "148", "0xeca69f132b3ae4903c85b89004ea3f1e694e5e0306994e26e1aae938981fe296"),
        (350, 1752704168, "0.99", "539.23", "0x7fadbeca3ebbb661af972ef614926afc0c101e313d058da2eb0d00b7c2734127"),
        (351, 1752704258, "0.99", "100", "0x966f1edb996805202d2aaedc1cb04c69a92b45837c17d1b4c0e0cb6a44591f10"),
        (352, 1752704920, "0.999", "605", "0xae844924b641d3148c2003b35b3f97c849d5b3e47262765f4eb1aca210b55bbd"),
        (353, 1752705056, "0.992", "2.24", "0x7ead51662873211b8e23cacb44de612dd1e83b50ce758d5eed3d660fe5b49c4a"),
        (354, 1752705616, "0.997", "200", "0x444305e5b7b0dfc6faf21023051323318854475c4cc087a21df9a1480f23a49b"),
    ]

    fileprivate static let retained563321No: [RetainedTrade] = [
        (0, 1752514614, "0.77", "500", "0xabe6a89fd005c3dfb5b747ac9e250c1957740567b716f81afe0c9ba9ba6b58d8"),
        (1, 1752514964, "0.77", "1500", "0x207eb077125a0eb5fb7036a0c2bc88f00f5e2c6cbfba1ca17f88a8832e2fac14"),
        (2, 1752515482, "0.7699999846", "10.389608", "0x605feefe8d4c11de405570eaa716df243fba7f60e1aa562573461de931a07cb3"),
        (3, 1752516056, "0.77", "10", "0x0808ea247aaa35086522d7535afdf1762e4d16c9821abb1c52b45d01cc6dd987"),
        (4, 1752516060, "0.77", "1.27", "0x2ae02fd4c602f7fdb78b8c2148ce0254b9a376d7b4fe835559701e197ace4b93"),
        (5, 1752516952, "0.77", "999", "0x99d02aaaa39ba6494851ef4d73aa924046d1c76fa8b14f7418c0fcdc9a916214"),
        (6, 1752519041, "0.77", "740.01", "0x64f009afe1ae382f0e09499cee720ae5e8a3e86eb4e60fefef082a428fb9db0b"),
        (7, 1752521737, "0.78", "30", "0x9fc9a2d2a5abea2bf090264f9361d95a5af9d54ea4f56f3fc23e4f66a51de38d"),
        (8, 1752522571, "0.7799999984", "12.820509", "0x6f6186a4fb50e94d6cbe23fee6339de7e09917abc476b77c2c83d47d67893ca8"),
        (9, 1752524364, "0.77", "99.99", "0x5e8d102ff0918efb8785792f924a9f3757d181e5cd322f73858d63e681a63eca"),
        (10, 1752525886, "0.7987767416", "1823", "0x9737b58a8de922ec435cc06f98c5e5f9293a2af2defeef341261c7cd2f7005ea"),
        (11, 1752528073, "0.82", "25", "0x4320cb3bf3854b14525ed042ca72279559741e30c2ce159c42eecd3338c04735"),
        (12, 1752531495, "0.81", "10", "0xb0ffa045e7ceb386a9c3c46968c8726ac2fbf2d41d3670e47b4d5801c29152e5"),
        (13, 1752531497, "0.81", "105", "0x3751bb46a333ed534021a17e002a7cfda410cebfe21eb026ebce23ba2a532b7d"),
        (14, 1752531593, "0.81", "70", "0x16e50a3f22e11ee93ef6b25bf67c901f5c68384e8524810cf600f8130e813bf6"),
        (15, 1752531593, "0.81", "75.2", "0xa76a5cac2bda246ec69d8bba097c6c558d3d232d1c1bb515b76b1d19e4804af5"),
        (16, 1752543221, "0.81", "10", "0x1ee62e317618977c6a08817cee8322991d1690e7f3a85da99f50df08dd570538"),
        (17, 1752543221, "0.81", "13.37", "0x8141e82e3715ff135871e724cfeddd9cb3bc51b037ece18eedf63cd05590c24d"),
        (18, 1752545817, "0.81", "11.63", "0x632a466a698191422e78b5a50b2d175cbbac344c4acf2367701b4b6c1651584a"),
        (19, 1752545817, "0.81", "10", "0xffe01d484cb9a4e69fc569cf5fcd8e7efcb257dbc0d860ab1bc909c070513d12"),
        (20, 1752545823, "0.81", "44.88", "0xb526c1cceaf21bb42ab279d2c80e32b191c77b8af0a5a4d9ecde74726198b7d5"),
        (21, 1752545825, "0.81", "11.63", "0xaf4e2aa6a926077bffb38c63833837521f8ee8d35da7c4370eeede00da534297"),
        (22, 1752545829, "0.81", "16.67", "0x0aa117061b5515e34c60f1c0f9ea383310fed31cb29fd7a2e1483445477efa23"),
        (23, 1752548828, "0.81", "330", "0xb5edd0e572bd00f282b75978a73790a9df30b27d4a41718a7581ab1773efe0da"),
        (24, 1752548830, "0.81", "370", "0x76361a1d8e3e2c5bdd182a27e4b9869b2abfafe8512ccae80364e880d3109d98"),
        (25, 1752548832, "0.81", "20", "0x7c870bbdc17d80d872d40a420e32bf9d24d0b7b1432b9a92a495fe60e4218d08"),
        (26, 1752548834, "0.81", "20", "0xb22091d54acda9fa7cf3893d263815d8ff3bbd83a98391353939c6f2ffe4ebdf"),
        (27, 1752552271, "0.8", "1.2625", "0xe6649d8bc138464595e5a671610e3e6138b8e098335dd9d3045f68767f9f77fe"),
        (28, 1752552353, "0.8", "868.32", "0x0ec763fd339bb2e7f5b7580b8ba38d9b61fc448d68be03ae97bb125f7b78b1f9"),
        (29, 1752552353, "0.8", "2220", "0xa742ace5c8eb417cb117bd162b6af78a597928bd481c030c5a0e8c8267634b48"),
        (30, 1752552357, "0.8", "1.22", "0x9ddc5506f57f7bdd452687d3ef7ff9cb5c50eeb1dd77680c289116f25c312a2e"),
        (31, 1752552377, "0.8", "21.99", "0x6c421ea75f3d8424a13d982de97b2caa50036b79eaa91e0971724e2a27a48fcd"),
        (32, 1752552377, "0.8", "16.1125", "0xadacfb52b9faf972c291075ae553751f6a6a0b9a67a59e3a7af2629d552f698b"),
        (33, 1752552399, "0.8", "25", "0x02a4196efff65d199ab4e815a4f1be88ad2aeac31e8022437fce6c9a14c319db"),
        (34, 1752552415, "0.7999115214", "677", "0x9d080890508f59cdaa2ea064ed4f04de7bdcad9dde49535caee66163ab07bc60"),
        (35, 1752552431, "0.79", "9", "0xd503263dd85f2c411c5a15cd2410a4f7412b9a2e95629caa5f25da65cdc59d45"),
        (36, 1752552433, "0.79", "8", "0x4222602f68dc07fefe78709532d985b5e1cb039c39a03f706dfb97ab30bfba59"),
        (37, 1752552817, "0.79", "34", "0xfc4db5217dde89f0dcb525eac190ca27b269a7a82231c8c1ca4fa9152db43ce1"),
        (38, 1752552819, "0.8", "1.22", "0x0dbd03eb61e13001611f7e51cc5458518deac3ba64efea48cc080b2c6c1b6dbc"),
        (39, 1752552819, "0.8", "30.49", "0xd8a7d45407cccee8e4a667cc7a089453cedc60da7ffbcab8ee1d7130907b3e99"),
        (40, 1752554507, "0.8", "2.875", "0x54a5a1771f3c2eac9ba51b9bd4fbdd08ac02ebf067f353f1caf1f90e366b5c63"),
        (41, 1752555149, "0.8", "37", "0x78e05913bde406d8f5a2b768fe0ca77ca8e14f665c9776860f6925d0da15bb91"),
        (42, 1752555149, "0.8", "30", "0x98e721ea355cee9e3e297e0b074ae844b4a0ddeba57ef3cdee6a834ebbc8677f"),
        (43, 1752555151, "0.8", "1.22", "0x7f569ae93f94f2cad15cd46c10e9e1fcec3e1da5059838115b366196d38f7205"),
        (44, 1752555365, "0.8", "3.75", "0xaa4b0ab5433772b6714e78b4de2d1b6c7d88320455b8d850a40b3e827831211d"),
        (45, 1752557165, "0.79", "555", "0x62f66d8b97347e2b22bc468c5af4470ba11d75c88f4747d69dacd56338e24137"),
        (46, 1752559303, "0.8", "66", "0x0b97a3009e48503fe3f4c51caa64baefaf5ae4ed7223253097cf3e011fbb5b59"),
        (47, 1752559647, "0.8", "100", "0x43f43976f90d25ee5d9a3416ed19a67cf1b5f84c7711977014ee9eba38c0d778"),
        (48, 1752559649, "0.8", "1.22", "0xd916444a65a599e433cfe9664f16d9b0a9be623ccc4372b59887f4ea951a4a47"),
        (49, 1752566345, "0.79", "9.21", "0x95b3ad2f589c60bac503f2a373e26fac49b779afc84d26fc326dcd9f477dfaed"),
        (50, 1752566381, "0.79", "30", "0x11094528f0134c29f5b8f4bb1f342e133e48f695a4a1a18c314e3215fedb60eb"),
        (51, 1752566381, "0.79", "39.99", "0x1f392c3fa947ff7ac212bedc0181ed3b6aea2f01b792e813c5be902a7be2b080"),
        (52, 1752566381, "0.79", "66", "0x78318b8153c6445174faa07abb17cfcd3fd87cb6be9f09d3dee6172ddaa2ded8"),
        (53, 1752566385, "0.79", "53.75", "0xb3ee3ac98d4d0626a922d77ace6cf1381345eba5f207629d773e27a8254af1b7"),
        (54, 1752566385, "0.79", "156.25", "0xbd9413d3667a6d6d111ccebf80d0db70d0caab1f04b0d3ca033bac762705c00b"),
        (55, 1752566385, "0.79", "66", "0xcc860743424eaf3d09bddfe45e8a9a0134168af9956905fe68225d0271bfb26c"),
        (56, 1752566654, "0.79", "40", "0x20df92448e2e0cbea408339e1a79ce9d2ae3cef708b8c3ebefc44b379155d0b3"),
        (57, 1752566654, "0.79", "40", "0xa2ae2483d5073e35e0705cab497563b0ee34828bd85724da70419330ef7827ee"),
        (58, 1752566658, "0.79", "6.25", "0x034b499edf5fcff59c64e35a066036516abf4d96a3bd0f2c3eb7d30548c211c0"),
        (59, 1752566658, "0.79", "6.25", "0x9aaf7a6265f68bedaf0edc25476ccd7c4670db1d7e89b7e24db95bdbac611d06"),
        (60, 1752566702, "0.79", "24.99", "0xf48a2f0bb5bdee17649d4e4f533e8f65834958d762455a4544c11e49f100e44a"),
        (61, 1752566730, "0.79", "18.05", "0x82026612cbf1cbbc9a067f3b38f03da64407e8d58d803cfc5abf576bd93d15cd"),
        (62, 1752566734, "0.79", "6.25", "0x38ca97d05c57c19c5b56c83d897f5e6513b56483a8cc38052cbc8b7df2314302"),
        (63, 1752566734, "0.79", "25", "0x5b82e60519cddf9d252f3cec20cde14a5e85db0094b2e1db6254e8efd627dcdc"),
        (64, 1752566772, "0.8", "1.22", "0x356323c6c3e1d564f75f88839040a1dc2c9d611da2424fb8b1a206fe2f3d140b"),
        (65, 1752566814, "0.8", "39.99", "0x21a1f0d19272601afd363aae0181fe763d38c39848f1fafbd1ec7dd97cb461de"),
        (66, 1752566816, "0.8", "102.22", "0x0adc18fb5ee8e15a4f4ccb3eea1b955ce5648fa4380e397e9ec698dd7a30413d"),
        (67, 1752566818, "0.8", "12.92", "0x36432ff1d2fd9fe231c702c47f811ad849b8972cdc34576bc7df081b3b83c3f9"),
        (68, 1752566820, "0.8", "5.01", "0x073f9ac9bcd408daaa9d5a237d21f8bc5762fdfbab72fb5c14e1b4f7befc24f4"),
        (69, 1752566820, "0.8", "13.33", "0x455d4be5a0c44b676d4ccc55671bac6be7fc41acd8e4f6fc8c9a5e3e6aa5fb6b"),
        (70, 1752566822, "0.8", "5.56", "0x38da7ca86154ea5428ba2a852c2cdc1dd956e987448f6e2c8780f9e31d8f8a5d"),
        (71, 1752566822, "0.8", "1.22", "0x48544e1ffb8d7051c8530358eb56a78aaff249c0ba0a89c15379968a662bf2f1"),
        (72, 1752566822, "0.8", "1.22", "0xb82b1d0a23289046a453da2b0053885fa9161c6837c7483c7f6f95410c436d0f"),
        (73, 1752566824, "0.8", "5.56", "0x2710ea81dcb35fb1b2ff0cb8e7898a4cc951fa5812dbdf4d3d3065094c1e9e52"),
        (74, 1752566834, "0.8", "27", "0xa254290c993edb4d5375853eb24d9072d40974021f6936abef7447a515bc326b"),
        (75, 1752566848, "0.8", "27", "0x39cede4ad3803721392f7853602e5a8fe58cf6652238f1e44b7dc06a17950782"),
        (76, 1752566848, "0.8", "5.56", "0x582f2703c9c6553a401d2f1acc23ede714223ed4be5a6476b3f4e5cbcda77710"),
        (77, 1752566860, "0.8", "27", "0x7236ab7a3b80c5f12d20966f0a25b3a33bba3c1f3dc845b42379c5d4808e3ddd"),
        (78, 1752566864, "0.8", "1.22", "0x76cc4a1549c6d30b53fe47198064775138de56bf4a701b35f9374ba5ff7f6d8c"),
        (79, 1752567078, "0.8", "31.25", "0x7cf915b454d5f2ead94ab238ea6374819aa86317a9abf5526dd12aadc1662d39"),
        (80, 1752567082, "0.8", "1.22", "0xf4bfeb8ea83d64dca9d7ab53455261881d96a64808f0047894921323b0b83483"),
        (81, 1752567937, "0.8", "1.22", "0x537c8c174985457cd2c0db5332f5fe9361e7ca700a357189689d446739cd4204"),
        (82, 1752567937, "0.8", "1.22", "0xd499726e9ae511e56c5abd3e9445f96ea5fb40452f48b76a090e309537b0b055"),
        (83, 1752567961, "0.8", "66", "0x6bda9cfe1805d2898b2deb109b0ecb90f8b9c5361a3b6f93ac5f69bc4b5eb8e8"),
        (84, 1752567961, "0.8", "15.28", "0xb88c880431151fd5e66dffd823bb8086ada5a7bc13fe96c9fcfe885b14790726"),
        (85, 1752568198, "0.8", "13.34", "0xde22c96c49f25afec2dd07fcb66ac968e3b7e28c4527953534b241669462f512"),
        (86, 1752568200, "0.8", "1.22", "0xde23521a4ac8423594b56de5a55acff5878758b9765fc80361d75283a092b5cd"),
        (87, 1752568202, "0.8", "11.12", "0xcb1f29b5816f2b435a12a185d08f9058bbe4264203cda76b3d338127967b9ad5"),
        (88, 1752568204, "0.8", "1.22", "0xe9c68173755bf5b47c032d5158668160b584598ac425d09f280427193c9c2181"),
        (89, 1752568512, "0.8", "510", "0x361d405001f6a643519c6afcbafa9c180a9ac02a8c5301872c90bf3546ef3509"),
        (90, 1752568514, "0.8", "1.22", "0xb6fabdb12d84f7ad480701321574a471e111f00c949c3ff0ae46c825451178ca"),
        (91, 1752568576, "0.8", "30", "0x241ac53bbb68a188d628b30c9fc3b00662237b49673978bae6eb97d98d1c1ae0"),
        (92, 1752568580, "0.8", "1.22", "0x882e69f3edc9bd842569dbba7d826ee491d441dcfa2690749a19083055cc5d1d"),
        (93, 1752568834, "0.8", "1.22", "0x05c554ec748ad6fcdcb41719f00fcc9edcd7b8a8f1126690f68cb42a61ae95d7"),
        (94, 1752569179, "0.8", "1.22", "0x152bcd6e6407b0dc2b6e06bc1954404691947efc9c5298e106b5e6ca4e11feaa"),
        (95, 1752569645, "0.8", "1.5375", "0x8289955f9adf3a70da4bedc4a60ec1dca5dcf0df4db44cf8a7d3ad9d2eb4deb9"),
        (96, 1752569695, "0.8", "6.66", "0xfb18dfd697845be522202ac64baff147aeb56028c12474c5034e355728a8cb0e"),
        (97, 1752569749, "0.8", "1.22", "0x9ac4215c7ac7b3272da0a2dcc6546b3f4fcaf0fa80c787a0319ede3884a1089b"),
        (98, 1752569775, "0.8", "66", "0x200c7b14966486b31dfeca5ec68a940975336c9c5f7f54018e070b26f0619b37"),
        (99, 1752569779, "0.8", "14.29", "0x1c4a6bece55e26fbe25d62f913cb943eee0e22f6c56846341ded241f4705783e"),
        (100, 1752569791, "0.8", "190", "0xeb2bdf796c8dfa8844b713ddb2911732a0db22bd4a56534948d9cdda4886d7eb"),
        (101, 1752569811, "0.8", "5.56", "0x31125cdd5a9dcd1eaae6a54a5ef45141e5fe930857fc74dfd18cec9b4d9beaf7"),
        (102, 1752569813, "0.8", "13.34", "0x700519709b3babf7b2f3bba88f826c6242b87e51d1e29127cf5d3ccde77507ee"),
        (103, 1752569817, "0.8", "1.22", "0x19bf0d3887b8271dd976194ca473be1835da2b21100e42b79790830ac5387683"),
        (104, 1752569817, "0.8", "5.56", "0x74f26861070bc4c3f87cd450875f736f45d6456e946d6382837c9bcc3fa4839c"),
        (105, 1752570003, "0.8", "1.575", "0x23269d7eb766651d7b58a82d322b7ea51d88feba479ccb17ef0d1e5182cba10f"),
        (106, 1752570167, "0.8", "170", "0x340216a3378b1ba8b8978cf925517d907951af6c23c4edeb3dfe20f27fb0d5df"),
        (107, 1752570167, "0.81", "66", "0xbed12e9da3b763f098baefeb485281ef3d782eca91f2c7d76d6530a03c5688f6"),
        (108, 1752570167, "0.8", "3.19", "0xd433fca84f2de12ddadb401677dfec111506c8038aacb433024ff1adffe8ea18"),
        (109, 1752570169, "0.8099999915", "11.81481", "0xbec189d62393de5ce24739fec20eef7c6e3c346e14d3670f6c329bc0f61096eb"),
        (110, 1752570169, "0.81", "15", "0xe5361b706cd3af10c653a6ec03e9ebd10661e96cdab397dc93c2e63e118154d7"),
        (111, 1752570171, "0.81", "5.56", "0xa4b204ec61bf56bb8cc705eddeba7d375ade809204769d52cfcdd9d71dd2ef9f"),
        (112, 1752570171, "0.81", "5.56", "0xfdc5f1f478d8f221f3466be0e8e3062ac453f72b6858f81e274b0df6996a8cea"),
        (113, 1752570173, "0.81", "5.56", "0x32cee20b11372d147297ac282aa39e7e1d89e36d886ba3ea829f4fafe32ac69b"),
        (114, 1752570173, "0.81", "16.67", "0x3560d9c7ea0396b0b6ae10b46f1c97035f75676aad28bcb7bf978d1c86c6a793"),
        (115, 1752570173, "0.81", "16.67", "0x898862b933f5a80c4a9730ebf485e6c2606fc935b190bf8443a46259202bebf3"),
        (116, 1752570175, "0.81", "6.67", "0x4f178d6f4c16c2d46dd4eebebd6df6c89d488a184f21ef6bb48990e51212314c"),
        (117, 1752570175, "0.81", "5.55", "0xf1b719dfbbd6ae91dff022daef31cc666497e68e91dd1740d7490c77525d420c"),
        (118, 1752570177, "0.81", "6.67", "0x88d23055b7fc4c6873bae5ada61ca4bf761da35037fdc38c5ce6d393b0cf89a4"),
        (119, 1752570177, "0.81", "16.66", "0xa36581aeb8f2cc299012d4f5044150c48f9031e197bb4be4347fc817e4e968bc"),
        (120, 1752570177, "0.81", "6.67", "0xf46ea28c7979847413885e1e5bbf6632faff9874f9c6481138e5a243544d0655"),
        (121, 1752570179, "0.81", "6.67", "0xefb2f52de466f757750ae238dfc9233d22f32f22dec3092a6e9cff542e20cbb9"),
        (122, 1752570179, "0.81", "5.57", "0xf4d348924175e838e6ac7ede4ca52eb3c9a44f11b6a0b5211380417bc00e7fe3"),
        (123, 1752570181, "0.81", "6.67", "0xad861d89bc38462086ac436d30c5d4fbacb40b577d4d5a609f04e6c1ca41c6b3"),
        (124, 1752570181, "0.81", "5.55", "0xb410fb1c93e664b9024ae49fdee87c6fa7b044271873d880d51c1913dd58459d"),
        (125, 1752570181, "0.81", "6.67", "0xe86dc8e5c797756cab51e2052edb6653fa37e2c81beac087a8770fdf7516fed0"),
        (126, 1752570183, "0.81", "6.66", "0x3e72f056847fcf4ffc35979657f962a34bc1f894ca4aca0114a9590ebfd5b5ac"),
        (127, 1752570183, "0.81", "5.57", "0x48cb60eb2a75df6593d13153a3fa2536335d6fca139cb91f2bb74fd4a53f6c39"),
        (128, 1752570203, "0.81", "300", "0x5c13863ab14ea843b1c2270ad4d824a27310b9590986b876e9d1e13918700d27"),
        (129, 1752570203, "0.81", "15", "0xe73d84aafd361461d7214bd671104d1a17ffc42d4f082c51bbf028ba5170ed73"),
        (130, 1752570203, "0.81", "15", "0xeddf8bb3271d746820fca13a1c43e9b2a041c01bb7b25f89b20b05176d139231"),
        (131, 1752570203, "0.81", "150", "0xef083324adb12a06dfa1a800d77a90e99ba53b36274f63617d8a525906718ef4"),
        (132, 1752570207, "0.81", "13.34", "0xd360e83e422ba2b3ac39ab9bc4c73b8adde5448153a4a224c297780830b0efed"),
        (133, 1752570327, "0.81", "66", "0xa0ec6309af77dabcce5fd6862f8f10971fe18c6a1015028704cab8e6438fd49d"),
        (134, 1752570327, "0.81", "10", "0xe858d94f6b6da7a3ab8af7a9985277909e0e4305e72e89d80b0ed9a5ccbd0193"),
        (135, 1752570571, "0.81", "133.28", "0x63d735b5c73200b2d492073a8a10c118ebb78437098a4261e4c3c3eeb1f135da"),
        (136, 1752570571, "0.81", "66", "0xd3698201e200db6fcabd10be47b71a4576d06c75a2734c40c1619a507a2d1314"),
        (137, 1752570575, "0.81", "13.34", "0x318dc17ce606994554ce00bd778651e16ee2880f6c7900a02f8a68b4a86956d2"),
        (138, 1752570643, "0.81", "39.99", "0x72ec97097fbc706d9f004d09b37a58b1a9e21188323a6197b3b3af8be831e1bf"),
        (139, 1752570643, "0.81", "1000", "0x79d6e55b7938013e2cdd4ccb78dd2caa04d9150cbf3e784a4ca47528a20653aa"),
        (140, 1752570647, "0.81", "14.29", "0x647848d625aaeb45feabe5b2e78e6832ebc787ab1943fbaf4562b2aa8a56b3f2"),
        (141, 1752570647, "0.81", "14.29", "0xeabfd4d97377d9ed7aed18558c7bf26a4d2511d9f3b53731df36355327a5f990"),
        (142, 1752570647, "0.81", "14.29", "0xfaa4f8fd7f5eb245883b5c463394673a371f695abecdc26d374e06c7abcdfa75"),
        (143, 1752570827, "0.81", "66", "0x053806f66ac5b73585ab8a47ff69fba671d806725661221bafc45ee1c79623d5"),
        (144, 1752570827, "0.81", "452.13", "0x1b11432daabda8d73751c3f9eca178577c89788297d9aa1ebc88de63941fef80"),
        (145, 1752570827, "0.81", "39.99", "0x5bbf2034e1a18df493404a556c43f718fcf804eb86da4e9338bea7ec8a48b482"),
        (146, 1752570827, "0.81", "329.94", "0xf0b765c645efb714fd05882524f084e0982fe6df5236b5109e8cb16e95426e05"),
        (147, 1752570831, "0.81", "5.57", "0xdb46192e604b9fe9cde6657740abf4eb5f15362326d47a35e8efb153aa652bce"),
        (148, 1752570835, "0.81", "37.03", "0xb724b8e5685cb812c402e7ad072457d552fe016c57ed08d5ae86746562085e05"),
        (149, 1752570843, "0.81", "4.15", "0x222d9ba7bb691598c7a9536962ab5c6e3bf891d2d8184d03657b74c977802c04"),
        (150, 1752570845, "0.81", "5.55", "0x3a44ad2d050c64a48347bf4810c9f746f6978eddd3d3b7ba17b3f186c1ae0886"),
        (151, 1752570853, "0.81", "1.1", "0x649b4a5da149d01e62342235e541d91acdc37186e2eb9941ce42ebfec4debbbf"),
        (152, 1752570855, "0.81", "6.69", "0x0f17cf5be3afc37b3c1ad79788885e96d81fb5a57ac45cd6723e91d01f3bcba2"),
        (153, 1752570859, "0.81", "95.51", "0x95e6b960d59fd4c97388cbd87b73f6306131b18b303e2e82eaa7b9c0bfb3c94e"),
        (154, 1752570865, "0.81", "16.67", "0xea402a53f661ce34166e1818af4622a3d51ed7138be186c25aa4edc04c2dcc6e"),
        (155, 1752570867, "0.81", "244.7", "0xfde84eda0f01af6adc6cfa5acb3c4923a88c021ac4a0eb31cef2e3172d6b052b"),
        (156, 1752570869, "0.81", "5.56", "0x223836e1842bea2aa66b70d6bfc3f02b2e285737459dc130e3395af10ccd62ec"),
        (157, 1752570871, "0.81", "5.56", "0x14bc5496545e7ffc489ad25e710a9a63db172f768b9c1219938ba9ac36b4b83a"),
        (158, 1752570871, "0.81", "5.56", "0xecb44a20ab3132feb23917ed61c3ba67029093c1530fc875b4b2f359330b6c31"),
        (159, 1752570885, "0.81", "27.46", "0x3287ac5ff900a0a3e1822c10afe1c4f74a594a7a888e97deecd25de93e73bbab"),
        (160, 1752570885, "0.81", "5.56", "0x3c36e1487fc9f45928f794663e65fa14ec8fe13e32177cad458581af5bf22c71"),
        (161, 1752570885, "0.81", "16.67", "0x5ddcddae75ec91f1a21316b723c0325324a4b316af950503683e6d56e12d7cef"),
        (162, 1752570885, "0.81", "5.56", "0x88926a2ad1f65fced1b8f73ffafe6bd861e19a068c2ba79de89c5757f4a22d8b"),
        (163, 1752570885, "0.81", "16.67", "0xec213468fa7ef2dedd8ae497b2c2d819a905ec212a400941f1a25e4463f3a390"),
        (164, 1752570889, "0.81", "28.44", "0x0267aca7f2a89b31969d30db49eb91b6d5ec668b37cc31b29d7f28f6c1ec0af1"),
        (165, 1752570891, "0.81", "5.56", "0x4efbf0814328dfd287863f87a90be5539d5ff794975aac590a3f98b164bdc4ac"),
        (166, 1752570891, "0.81", "3.19", "0x737db180559bfe0e39c56da2556532b2a7c157e05d68ddc28fc2e30054168150"),
        (167, 1752570891, "0.81", "39.99", "0x8deb837749af33670ad27c8a60e6bea7d7c15533708bd40aa8cca948ea826fbd"),
        (168, 1752570893, "0.81", "5.56", "0xb6c645abc2009d72af4c638bfb6565ce643aaa98494037ff4b2ef5d0885da3d4"),
        (169, 1752570893, "0.81", "5.56", "0xfe0d472d7fc2b368da11e159c2711f476ae219f3b2c35c57b36bde7627af3f44"),
        (170, 1752570895, "0.81", "15.98", "0x317ea7028a02add08eeba72151983b449d432a6164b41aaf7d2e2c23a3bad59f"),
        (171, 1752570895, "0.81", "5.56", "0x4d3e2687cb37f3dadab8337503824e64d8a86d64e64768c7e92db52be77b0479"),
        (172, 1752570897, "0.81", "5.56", "0x87dedf4816cacab4ad4fd8dc9e6ce2bcfce9109429c1fc43b361434900585d7c"),
        (173, 1752570899, "0.81", "62.48", "0x2197e1c48a44d340a7af79350e06bb3b3ffb52b9647d20b6f87bef73cc7520d3"),
        (174, 1752570907, "0.81", "242.29", "0x61e09ccf4a6c53a76112b56f6c25aa32425d326d8de11f1a2b25edfc55888c3f"),
        (175, 1752570915, "0.81", "60.34", "0x37b619a4541114eb3be5276ba0317bec51ae25f446387257b6084c0fbfa02d81"),
        (176, 1752570923, "0.81", "6.77", "0x67fd6919a49d67f4c8550cef7d9b85553854244f1d904983a3b03bce23130dab"),
        (177, 1752570933, "0.81", "271.67", "0xd12461ee820fd999221bdb5e12f69f644ec36c2cf4c7df3fa7016fa2620071bc"),
        (178, 1752570941, "0.81", "84.12", "0x36140b0f46feb605a6a29eed697c6d3084774953466eb6a6bcfacaad0ac32379"),
        (179, 1752570949, "0.81", "15.46", "0xd356db320e12dd95ffbb80f7080303f03875a319cafcabf97c0ddeeffdc01708"),
        (180, 1752570953, "0.81", "39.99", "0xd6c4410ac137fb346ce7c7915e774ad885721fddf2802b011a14e78489776258"),
        (181, 1752570957, "0.81", "1.74", "0x86fb6e9b55881017c1d1bdd5b78aa26ac8a85ab60bc4fab835e4585e5dbe0b2a"),
        (182, 1752570963, "0.81", "242.52", "0x0effba7713019bbb89ca4f5b6b60f69070bb2711788642a00fe668af35277300"),
        (183, 1752570973, "0.81", "5", "0x2a3483d059ac358c0f5cde1a79ef81ae89624fc68e54570f9a9d880b6f55024c"),
        (184, 1752570977, "0.81", "6.66", "0xca04a410aa8b7d23fb799101aa3b67577f2b9ffd610fc0e65299c7f1fb70e882"),
        (185, 1752570983, "0.81", "110.73", "0xc62173e9479a0395e3f9e52851f33f1e040646a2d49ddfa8789b200008108150"),
        (186, 1752570985, "0.81", "10.02", "0xc85d830c1079c7956af2f3c9b5ae01d6c8f06f9b91aa15f25675699eddb0ad3b"),
        (187, 1752570989, "0.81", "112.27", "0xc6cf21b765a003c0b940b69f5e9e8981c54fc5b477f65814cdf38713932439a5"),
        (188, 1752570995, "0.81", "14.41", "0xe22ebca53f3cf095f16b7496da6c7ed05c3d8eae217594028d61e61ada8d62d7"),
        (189, 1752570997, "0.81", "661", "0xaaf9a404c178b7b9fdda5e34b38f984a16326356175b470feed9d64d62043da0"),
        (190, 1752570997, "0.81", "190", "0xe074d17db34edee2b52734b36170ff07e9e8b50026284fad5ba5d70e872b7572"),
        (191, 1752571017, "0.81", "15.55", "0xe2d22db58b3c752929f9768441ce7e5509e8526c1d047939ac9cc4ee03110e63"),
        (192, 1752571159, "0.81", "66", "0x28c684d7d18fc427a7a094762b45f2c23e24aeadcc7ee1e39782ac107256fab2"),
        (193, 1752571159, "0.81", "187.36", "0x4a03b68595a5f45076e72c2e6530fb25c5b00ff3dc0cd3841f9250180d943384"),
        (194, 1752571297, "0.82", "40", "0x543392e1af3a4cc2b3365a27f298145fa4ec4237c42a9a45f865debb22e80ffd"),
        (195, 1752571305, "0.82", "5.56", "0x4db9bd7a3856eb87307834c1d8f050b859b973f02153b412eb161b48a6645c17"),
        (196, 1752571305, "0.82", "5.56", "0xd19aa22eae40765c6bbe836aa5cd29bac5a973be886d2347f824f734b189abce"),
        (197, 1752571389, "0.8199998849", "1.390238", "0x33ddf82ad28cfb4b79faf378cc958c80a1bc336d8aa847f6d23458c4877da94c"),
        (198, 1752571437, "0.82", "13.34", "0xdf79d3a383797f5d0175908e2fcf7181c7e2e0212a01b86f14bea45bd9a4422a"),
        (199, 1752571443, "0.82", "5.56", "0x5c853fb84c7450253b3da6bb3f6e218579a5c15107016b22594698346bc36825"),
        (200, 1752572445, "0.8199999745", "6.268288", "0x80eb28e8473a0fe656b1b89d24f87adf10b071c335b0e5debb3be9d01b52277a"),
        (201, 1752578841, "0.81", "50", "0x60d90bec60356ed5c266b4e7a92f72e0a2a2390cddf0d8fda24ee44870ec3e77"),
        (202, 1752579313, "0.8", "17.99", "0x03eff3b39b790576ac7625fce9a76f8cf68ae6c312adde100048f60d9569e01e"),
        (203, 1752579313, "0.8", "9", "0x74edc6238dcc8c8dd17ecced53f2c0e1eeeb08b7520a9887b8c13286850e36f9"),
        (204, 1752580463, "0.8", "1045.49", "0xf33d1753a9015f12a7e8da58481fdf6ad4c7f7e71cd104fc37dfa6b146c9707f"),
        (205, 1752581815, "0.8195902042", "122.012194", "0xbf912f19bebe67831b67a92f220bdba7b195cf2359e6ef0635db6715ecc2e77b"),
        (206, 1752582529, "0.81", "20", "0x3d1a9467b35cc94859a51bbc2403643b046b598a7abe31ca6850d5b63df7b53a"),
        (207, 1752591253, "0.81", "66", "0xcde9b49b53663446638c42e743ad9c715827f9b12326a61bc0d9077588e7fd05"),
        (208, 1752591255, "0.81", "20", "0x68d240e2a7a7c2ecb6299bfd5c60ee56b5421b05ed25f4e92965bf19ed493386"),
        (209, 1752591263, "0.81", "26.08", "0xf3d21eacaf90b2b102faf0fdca9e1d4a08653bef4800c31375b99a907af6ffc3"),
        (210, 1752594902, "0.81", "1097.83", "0x7b3f5b69706bd9d437b288c130f5f10483b39450e26177e17c688e1ea08f3cdb"),
        (211, 1752598298, "0.82", "7340.29", "0x527c2e04509e609579b835ccb76cb7b808c42e7722497f18fc301d17737fe45b"),
        (212, 1752598300, "0.83", "1.18", "0x3d62be21e80c75008b01dbc5d04de5a8fce534f5fd30021a19565c096636499a"),
        (213, 1752598738, "0.81", "125", "0xd628fe3e283447169cead3adbf4378e858dd87fb602941665ce71956b745d5b2"),
        (214, 1752598900, "0.81", "5.56", "0xae9d8c657ad195dc1f31bcb186703ac475ad6bf921ee56a1948caf645f6588f6"),
        (215, 1752598910, "0.8", "119.44", "0xdfa41d03c6bfb39e19af89cf4eafe847787abfbb7e51dddfd5a0c6c064271f1c"),
        (216, 1752599909, "0.8", "6.25", "0x0a6d9ccecb7aa31780f0e7f8ae7af3e7d2c856a47c3d27b5ff1fe004319281f1"),
        (217, 1752600733, "0.8", "5", "0x054d959352555fc589bec82018522ee0ecd62217a3756b7b98899cdbc6b50cdd"),
        (218, 1752600801, "0.8", "20", "0x3d4cc4143e50f750b4ac6f339295e3a6836081a08c65b989ef31a6194eb9a23c"),
        (219, 1752600805, "0.8", "1.22", "0xf9ae962b4731880c067b7321048436f097082da64ebad64a0d209853d58a217a"),
        (220, 1752601815, "0.79", "1935.32", "0x663b90b9b73b7139722f7c5930f2716dd195cd470270aeee6a2c1049dacd883a"),
        (221, 1752601819, "0.8", "1.22", "0xa5ca455b0dbfd36a1d4837684143a07b0db94b434cf10ef6cb08dfa87800aa6f"),
        (222, 1752602613, "0.79", "305", "0x3219b9945cfddf289e6b0f7989df603f54423ebaf67e927f5cb2cfa4b47c0bdc"),
        (223, 1752603431, "0.8", "80", "0x1b34154b2582c39a41247532380e13edcab4f19021b5412d9fe4918c9947e704"),
        (224, 1752603435, "0.8", "1.22", "0x68a2a97a822a5ede382acb7c7e6753c88a17b7fb5a77c569a87b5dc2be3558e8"),
        (225, 1752603501, "0.78", "1217", "0xf2dc2f726f45fa5bda38aad107272340417e22dced7d51ec637dc0c5ec193170"),
        (226, 1752603535, "0.78", "30", "0xf7a13dfc5cfa891bb4713acddb333c3f2c8128e1a96adc2ae5d70877364f82c3"),
        (227, 1752603537, "0.8", "1.22", "0x9a684ebc5b30da098cbdd7901768e9c5f732e3828f08e8b089eae09d868b1c79"),
        (228, 1752603543, "0.78", "53", "0xe7ffa087653aa4e0b15036b5f05068a8b855c87be1131c5e7456f59583a25595"),
        (229, 1752603547, "0.8", "1.22", "0xc5e614482f1a0a12f124dbe21858f4fe4d83170bf632119ebf9ce6ff1075239e"),
        (230, 1752604512, "0.78", "2820.17", "0xd8a704b7653b8c2d3401308b2018310af04cef668d87aed98e8f7eb95832577c"),
        (231, 1752605692, "0.79", "40", "0x836531c1be723846c9058097e3ec289a281b5ed99d188fadf4abcc838cbf1901"),
        (232, 1752606972, "0.79", "51", "0xaaec05d19638827244d37af392da6e66373766eee8fdb7ba1d2f14c95e304617"),
        (233, 1752607258, "0.79", "200", "0x2f400f599600e9653239f782ebada9cebea1313f1ee8821ca8bb075058098ec4"),
        (234, 1752607258, "0.79", "200", "0xc4ed34fda9bf4d38329041ab9068427b2072a71f571d5fdfa4496a5a5060b1a2"),
        (235, 1752607258, "0.79", "40", "0xf94498a40ad2c295251f3cec303e42d0de4f762275432a47451745c6f81ddfdc"),
        (236, 1752607338, "0.79", "40", "0x3de161dfe6b244e45ab72358989ccfa18bb000b791086195eddfcffd88d079a7"),
        (237, 1752607338, "0.79", "450.04", "0xd63344ebffcaa3ba6661494e6e307ddec8aa16f3ef3135805d0f7bdf39ad9757"),
        (238, 1752607342, "0.8", "1.22", "0x3148dc5c81f0c65cae430f450ea61b568c1fd4b6d62990539d11f09d64e76a25"),
        (239, 1752607394, "0.8", "250", "0x516851f2daaae6f6fa4fc10c47cdd11afa1e9f420f5dfecc678c40bf0bffca31"),
        (240, 1752607428, "0.8", "1600", "0x2dd329d7649a2112084f0960e99d8ed922d03ba1757b34dbd0870ec44dc865c2"),
        (241, 1752607428, "0.8", "40", "0xdde6add85c2968c33967b49fc6b5da38f8a454c4bf9cc864364a48bdfea3087d"),
        (242, 1752607556, "0.8", "160", "0x35985088c72dbfb043965403d7d69a837b8937f6927ebaa2a838372d108d4d0d"),
        (243, 1752607556, "0.8", "39.99", "0x3d879348fbde0f9e46f659accb0c07dfed105b36b3c1f843e78b9fe96267b07f"),
        (244, 1752607556, "0.8", "167.24", "0xebec46805d8d7a5da36dd3c49b889c4ee64b432bc4dcd2de9e4cfee6651079e0"),
        (245, 1752607566, "0.8", "24", "0xfb29b666313c641425def2c2a218e9ad7cc0adf9cd4af01caa13665d6e2600e8"),
        (246, 1752607578, "0.8", "16", "0x9b0208f86e7221f794752e1ca3b2f92eadaa206acccc10cef9566b47d11cfaec"),
        (247, 1752607592, "0.8", "8.93", "0xff6d394452308a0b013be5f7dcd1cc197f88581835d18db03469de8f77e861eb"),
        (248, 1752607602, "0.8", "31.07", "0x3d9c1bddc7df560c65a8beea158471b42eb550bf3b453db29eb0649939652c8b"),
        (249, 1752607634, "0.8", "10", "0x77829b1979dd8556378f69cd56c47547eccc6c4d80f90118bf64a197f0c571a8"),
        (250, 1752607638, "0.8", "14.29", "0x450d0c4bba0618c528b62e51d0d49f2e204cb4e76eb45bf85271e551060ea14d"),
        (251, 1752607800, "0.8", "820", "0x59ba0efbbfeecbe0a3b9e01e488f2676228f0b33e8b87bdcf9089a0d12c6b6a9"),
        (252, 1752607800, "0.8", "39.99", "0xd926c6a9e92fa1c2954d0a36d3c5a68f73b4d69fd17af8a4d0ccfecf6ca3b88a"),
        (253, 1752607802, "0.8", "138.16", "0xb6cd5b27fb27d10ba25129ec6b88f69c8a91164f14a8b882b452ecdae8b8e505"),
        (254, 1752607992, "0.8", "160", "0x9e28f4d6499e87a2d12222bcc9e0b53de08992a3102eb87e99f780d76fb73a1c"),
        (255, 1752608352, "0.8", "10", "0x22ab5ed7b24336912a8584f0cea6a2b84da0cf0009bc710c24e9553cde3c6d1b"),
        (256, 1752608596, "0.81", "40", "0x2a49fdb3f1e0c709c643a2c0700c21cdad31019832506d162796a38fec88a9ed"),
        (257, 1752608602, "0.81", "16.67", "0x311242202a23aceebd36989ebc2fb0c64dce20814ece5f88d4f0eca9bbe5e4d2"),
        (258, 1752608602, "0.81", "16.67", "0x7e3eb958f9d79b9866c64569dcec1b7fd6367d120e8ac9243223a48b6516b12a"),
        (259, 1752608602, "0.81", "16.66", "0xa7a431a7a978c33165809664ba9909bc0ba39cb97c12ec210f9d0035485cf073"),
        (260, 1752608602, "0.81", "16.67", "0xc6f7d638da9997f42073898665341eac3555f2efe4c3762f8b1ccd21da2a3ce8"),
        (261, 1752608664, "0.81", "1278", "0x0060b021e623dbf8a4267621edf52a38ab80a2fb0cef6b872dbb33a18323c397"),
        (262, 1752609072, "0.81", "599.91", "0x4407201496e35092440aafb5721a9bd663d82a704f940a9a7e65c08a864d4c6d"),
        (263, 1752609238, "0.8", "10", "0xde0f9410044dc84a4328fc9e5bcd8ec261844c8be65aeb2892ffe8ba594bb5ec"),
        (264, 1752609242, "0.8", "13.86", "0x69e6a5d52960c03c557b4ff4934465cc21ad6cb12cf56c4d3abd5505c207eb05"),
        (265, 1752610080, "0.8", "5", "0xe09e3f9db37c119dfb644f4e22f509b2a217e5863ce0fb04f240266cb1547e21"),
        (266, 1752610776, "0.8", "50", "0x31166f288abda791e526bf439c401a9153aded4d8fc9fd4a7baf34afa2ea39ee"),
        (267, 1752610776, "0.8", "346.67", "0x7c49f40afb2279a8ca6c1972417f7f879b2ed1570d5c132b93cb238d0037ea2c"),
        (268, 1752610776, "0.8", "346", "0x9954fd9f2c0bef5d232e8e542393b05b96cbfdb1ed3a91c60723277e99de81f7"),
        (269, 1752610776, "0.8", "5", "0xaf78c0e4c9779a840fc347fd308f9b5c49b1a0ecde96615f519883bc744d805b"),
        (270, 1752610958, "0.79", "20", "0x5395bd14a1dc3d4b2300d4615bf73620eb7711c72f8d9b02c761983a522c7be2"),
        (271, 1752610962, "0.8", "1.22", "0x19618b24e79d0b637f83ab91447343740e096e6f8cec809e4dc52bb445557353"),
        (272, 1752612036, "0.8", "50", "0x4d580e515e876567d9c934454d0c91fe058c64e79590d38f13d53fa0b49aa480"),
        (273, 1752612393, "0.8", "1.22", "0xb514a55eb1b68c00e5ca68a8f9f7fe17e8fb5ff0cdeb7ba88c98a1dd9dd4b813"),
        (274, 1752612397, "0.8", "100", "0x2e19bc1e4fc56d3a94d10ce84e62426fce8ce5c4cb1d1d365e0bf6b4512a518f"),
        (275, 1752612411, "0.8", "14.95", "0x475f535112c01de3ec64babba9185e730123ea232d0240ef0a1979a7c177136b"),
        (276, 1752612411, "0.8", "5", "0xf1e1d7ec37016336137df8f44066d1ca5f5041239485c9cabbefcc778eb6e56f"),
        (277, 1752612629, "0.8", "1.22", "0x6bd2b391a91fc0ef6a46eddb92727ef8065ead2999e7b33d57f4eef6461d1c47"),
        (278, 1752613959, "0.8", "20", "0x3eb9c093f44c2e0fa475af3bd9f3a6a94cff26e14dea210496d8508b35bdf3b5"),
        (279, 1752614159, "0.8", "33", "0x75da97390e193174c6ef80dd578864aef327c59a3fda23dc9d00d9d7c7e1ebf0"),
        (280, 1752614923, "0.8", "17", "0x445cfcb50a9182334fb1cebc894f872277bec74655f85c867ad1dda19bf7aa3a"),
        (281, 1752614923, "0.8", "10", "0x7afe5d1ed408ff6b34beff615524d7b08358d77baa00057bc9c12b5268392267"),
        (282, 1752614925, "0.8", "5", "0x6f5d2de9ada2eae5b2069f91a51ae2b96cbebff474fc0a85443cb841a6391e9f"),
        (283, 1752614927, "0.8", "1.22", "0x45bcd001e1dbcd0ac47fd9c67e537d5582487985095ebf46a394c1ffdddbe8d0"),
        (284, 1752615279, "0.8", "1.25", "0x77ee497427db7851d697612c4196662268dd9f290918f77ea9fcf243b2ed2f63"),
        (285, 1752616079, "0.79", "100", "0x865da2ebcd75f00f2c73814e68ddf3963a12dc2a027e2a41a3ac0ff7851b18c6"),
        (286, 1752616929, "0.766680953", "79.33", "0xa002c28bd38ac5b866d8a8fdcf237ca1d1ae49da8990b6f2ff8dc594d6f5c4f1"),
        (287, 1752617305, "0.72", "14", "0x70f5db9714c41849ffa4bf1810b05ad38249efee7535e6e778ec1a84b439e842"),
        (288, 1752618005, "0.7899999831", "56.962024", "0x98dfb2ba3a13c41460b40a0a5b565f004ede1f6b6ae005e026446f3cc575a7ac"),
        (289, 1752618029, "0.7899997551", "3.797467", "0x39855c8222cdf7b38cf36cf9b734e9126ac1070fdb8a43950629adb678b3b3c2"),
        (290, 1752618671, "0.7899999994", "46.708857", "0x9f06ac3a2dc23ecd11a4ce55d516346d6b234e8250c1b440008c96146ab14124"),
        (291, 1752618775, "0.7998706939", "101.31", "0xa99d6b22e729cff5117c08dc8fd35a5d835c82d42c8b54b0dbd49356c52a0341"),
        (292, 1752618889, "0.82", "44", "0x03761375c23093930b799db03093a721e8541615c2aa9bda81f698192b711326"),
        (293, 1752618891, "0.8378680203", "394", "0x802ad8290393cd25de6e119496ac541c948b22afdde3122322c0c4a262e23dce"),
        (294, 1752620861, "0.7699999867", "42.857141", "0xcefa23b42096a37aef6a354952c4ee923f049317e97485fc072197c966b259f4"),
        (295, 1752620885, "0.7799999786", "34.615383", "0x3e931661c9810acd7e79fa74f01c18e2a1d44e769c261a01ea587d118b1585c1"),
        (296, 1752620943, "0.7799999979", "19.230768", "0x28d45a85c3ff10b2c3bae2bad6a33bb1cfd15dc472c2eeaefbd3ebb8ec50fc74"),
        (297, 1752620973, "0.7681503742", "58.582277", "0xd61c37ef3bc29d2893dc9d7e91be9b4b41109ae2e6f2bed7a5483b01fccc8d5d"),
        (298, 1752621177, "0.7899999573", "12.658226", "0x8098b8a8d9845117e80d7266e8e5c374e73b04ac70b875cb0e31892a6d18c091"),
        (299, 1752621361, "0.64", "5", "0xe44a6d5b86e05546ca39c6b374eea946562e7477b40a83904b8c0e78b7e4ef6e"),
        (300, 1752621531, "0.8", "252", "0xcf9041b5bf6a0a2c6999e5bcbbf68edd9162b0b9c5b0960d6fdca97bfdd4c718"),
        (301, 1752621613, "0.64", "0.15", "0x7aa507534bc2c7d490e9e5b4a862747554e32e14deb8d8e2def1b1d7b41355a8"),
        (302, 1752622041, "0.75", "26.666664", "0xb922f05ca2c45e4948d1fc1bb6c7294f61af735b21a563ced4926cecc6f37b1e"),
        (303, 1752622133, "0.75", "23.33", "0xe1b2657745324d2aaa5b8b94869980a15e7174b9d5c20d8db24de4482301aa77"),
        (304, 1752622403, "0.6531506849", "292", "0xc050a1f6c7bd63283af87dc6d16a900ad1c282716fcae014d03f46a7b4637857"),
        (305, 1752622597, "0.64", "208", "0xbd2dc01f84c6cc13ce70df939b6b0231dcaeb6281bba6227c582d0e2ae75b96c"),
        (306, 1752622603, "0.6599999842", "15.151514", "0x16140d0a37b1682d94a722a2fcea369a60115141b88bca841399d09825649029"),
        (307, 1752622701, "0.64", "92", "0x06ee1dce1ec1a8c9a242999b4127a7d11af79e3d37ce5bcf4bd60ed37d9ae380"),
        (308, 1752622701, "0.64", "300", "0x9ac5075e51f94dd52c8fa214192fe846d3918c1df34dad70bf6bae5549a1295f"),
        (309, 1752622701, "0.5725", "2400", "0xa385684bbd6b580aa6555103c86c90df01b7632f655db7de6d2b5b572f5aece0"),
        (310, 1752622947, "0.63", "99", "0x43dacacbe54ef23705495241b4768de1c889e5b4c161080cad8e8546a4703bf4"),
        (311, 1752622949, "0.63", "0.99", "0xd67b55d9ea7d1901fc8a592994588a232e14d1c5d6dfbd10db3c8df19146c885"),
        (312, 1752622951, "0.65", "10", "0x56946250a2f14ca484df2b767d75c52d2e9cfab0d6b724dcb41a0dda5a25f7bd"),
        (313, 1752622987, "0.3", "10.01", "0x350b66c8862f903cf85230b0d3e9127deba12694a77fc65e3455b0831bf8775f"),
        (314, 1752622987, "0.3", "39.99", "0x6c1b7f61e90e6915e13839213de7fa2dcbd7f09d94da6ecfbeb31886acdc50a5"),
        (315, 1752622989, "0.66", "22", "0x5d1ef7a7ce0704e4f2222ac79fc1b053de3566322b638b4a8c2200a046f339c1"),
        (316, 1752623135, "0.64", "39.99", "0xc29a1804381c7ecd03935dab829e7f631b024b446c8dd788d4801d84dfd511d2"),
        (317, 1752623169, "0.3304524887", "2210", "0xb36c469febe5bc8510defbe6da2916ec553c8b177d642808513a3132b7f087e5"),
        (318, 1752623173, "0.32", "37.5", "0x62e93bb7f29ffb5aa97314d910059515d2c5e51d4da54cc7ee8095dc2b7756a6"),
        (319, 1752623175, "0.35", "14", "0x29d7605bac95a811054e9cb48af799cd4bd644dec412c1ea853ee7ec69950289"),
        (320, 1752623187, "0.593452243", "20.220665", "0xafc7c793d1c9c3795138f7ba61f05b654b6c23183b3e2f40530a3f5f9a7b1039"),
        (321, 1752623189, "0.32", "2200", "0xe92d59bab35a222bff3bae023dd44c6ea2b63f199178fc6e446ee60e8379524a"),
        (322, 1752623275, "0.2805258033", "1027", "0x4a41ea21967888fc768aa00e722be1809fbed95a101057caafbafc594c57cc09"),
        (323, 1752623295, "0.4418999622", "45.25911", "0xae8ce6487ebb138a5ecd952666c84102f3dc6513c4d004608efc815bfee35d59"),
        (324, 1752623357, "0.3899999866", "17.948716", "0xdcb9f7f311604de661659c3daf6f3208f69ed48a4b446672c4d51326a53cc43b"),
        (325, 1752623361, "0.3102440169", "1065.5", "0xef57a445e9abe751dbb7d438bf49f2c92e732dbff3504317a72a9730022558da"),
        (326, 1752623395, "0.38", "50", "0x956334b59b340d5f1796105ca0ec5a721574d7ce1464f4f06d4c639db96b2cae"),
        (327, 1752623483, "0.35", "50", "0x2728111477e8356bb6fa6a362a40dc3c48901c64a8d34bc019be33e11f92bb24"),
        (328, 1752623519, "0.38", "85.26", "0x189a4f2b620bea21e0dc21d42863bebafa0d65c229a56caba928a998c087db6b"),
        (329, 1752623519, "0.38", "50", "0xd15b4099dad72e2e05f4d333de035c3d94211d145aadcd5198a180b0a704fb74"),
        (330, 1752623533, "0.3941652567", "715.13", "0xa2f6e2f7aa068398c11c2d8588ac3a9c4d48b2376314b94441e138f6e4952fb5"),
        (331, 1752623553, "0.45", "291.4", "0x54be0a1ae9ec4011dc3dd72bfc7ee8d111126ca65b9e4c7ca1b5244c924c47bf"),
        (332, 1752623559, "0.44", "1000", "0x4ef4568408c4ae4b5d807dd4d95f0b523068825565aa7641cf441c596e16463c"),
        (333, 1752623559, "0.5", "200", "0x5dca3ebd19f55d49eccceba53a3e0724b6ab17378cf695038d6c8c7fb91e9094"),
        (334, 1752623591, "0.6", "60", "0x561d8bf68cbc88115f8605369619b6f0c54d676e9caee368012844cd39691f9c"),
        (335, 1752623749, "0.45", "100", "0x3eea977db96ec7bd27375a120545b4dd3e144ab01a5185f28ed33372538b771c"),
        (336, 1752623749, "0.49", "9", "0x5edd5004417cbe04eaf2f919231065e0efafde73c09b7ada0c0dae07e7d5cf82"),
        (337, 1752623749, "0.49", "10", "0xb97b9db42ec3781cbe4ef9acb077390e1a355b2d393c7f2833f53e3f54cd693e"),
        (338, 1752623827, "0.3659758336", "1900.99", "0x70ca13ddcba460060860f831f5b28cb90a8858bd9ea6c9415c9d1b18a065f25f"),
        (339, 1752623869, "0.4", "16.99", "0x009be64cb2d94e1b4e185bcd2a71dd8295242ff9ed49c32bc4bdcaa21e96a1a5"),
        (340, 1752623869, "0.4", "40", "0x42eb66bb214fd98f0990e96c713130f27572734c28d60f252ca96b0b23ffc77f"),
        (341, 1752623869, "0.4", "10", "0x8ce411244476ff06a4553d5677d91311ba98f7d2802a0015d53a913dc2fb9096"),
        (342, 1752623941, "0.48", "39.99", "0x115c73486dce408546385ab8ea31b97c697fd670d641bf7163fa387c36f4f627"),
        (343, 1752623949, "0.48", "89.99", "0x981f6b730098acb821033217cdd7ea31a33178dbfc2f4c7211f149a215bf9cb0"),
        (344, 1752623973, "0.5399999982", "56.166665", "0xbaa46d7c217124e42e1b0c52f30e90193134dc5af2bc1a0b3989b385c9e43298"),
        (345, 1752624045, "0.45", "1000", "0x698475e8632be2d306be9b936c39ccacd4cf0f10e7a19633f487e653fff90caa"),
        (346, 1752624117, "0.52", "100", "0xc1842fcad0eaece09de38065e73415379206a8f2157a260ce06c5a962e070eb4"),
        (347, 1752624119, "0.52", "20", "0x35629f5d12fc2a90c4c823c1930c12a9ece395f97ab2bfaf2503f5305ed5fb68"),
        (348, 1752624135, "0.52", "42.45", "0x857cb75602ed346efb57a934f7484fedc5e41b39628598e27813fa1e22ef8f8a"),
        (349, 1752624159, "0.53", "23", "0xa2592eba1b3de3f2af436dabfcba5601902a26f020cb95503c15ada41426b91d"),
        (350, 1752624167, "0.52", "110", "0xfb9eefb29d7747847c60a4696a15295bd8dc3f6457673adc23520ffac85e12cd"),
        (351, 1752624185, "0.51", "20.99", "0xbbae23c936500911fc4c1b7aeab38a4af22340f8dba984581612cf6949db4031"),
        (352, 1752624201, "0.46", "1.38", "0x49a7d06791c92e7b6f5516363daf339b82c78eb028676f2e27201817497b22c4"),
        (353, 1752624271, "0.48", "100", "0xd7cd3f32fc27ce670b5fb2279d3b65faa9f2c6153f4551269b5ba8117fca3e41"),
        (354, 1752624273, "0.48", "22.05", "0x7be2967bdd4b80148f5006020d175ae9c22c78341c18959376f9fc96c6ccbb88"),
        (355, 1752624303, "0.48", "5", "0x5a40ae8479129b6338432081d84014b820a35553f99a8f4a884c2b1eda2f5c25"),
        (356, 1752624327, "0.5", "6.81", "0xe9df04ac81e19cccfe01296059298f07dec1379f907ba09be1f99b05097c607a"),
        (357, 1752624331, "0.5", "110", "0xde96af93f33794eda96844c97d7b698ba75031a012359a2aece110c9d521363f"),
        (358, 1752624331, "0.5", "39.99", "0xe58427c8f4ca80c8cfcfd14a08928466f34b330c8d58b2b11aa1bac04209d5e1"),
        (359, 1752624513, "0.56", "5", "0x0285b3c3d8498e8a45a08b62927791e8f68431c9a40ead4cbf6e416982da8a40"),
        (360, 1752624539, "0.56", "20", "0x54110839276ae1d268b1ab8ae41de69c62df6c2066b7f99fe836344832fbfa48"),
        (361, 1752624787, "0.5", "110", "0xdfa516a8c0b5590edb01e88338147468d0f485db0343eb5a6bf10e93f9008562"),
        (362, 1752624935, "0.51", "100", "0x0788c19cfcc543652d9717cc3d843af51d74be359932b3f4495a18c86205c3bb"),
        (363, 1752624937, "0.51", "1", "0x6d6bf6aa51437acc5545abae6bbe059fdedafe9c965bab97e8a4c7e77520b19d"),
        (364, 1752625305, "0.4984485169", "650.99", "0xfaf699f1e963af791b69bdd0027c714c779e4ce5bdc412f6e3dd0331b21276d0"),
        (365, 1752625317, "0.5099999956", "29.411763", "0x378bf4763485db802f2552db5a15348d35277366eec38e7fc3973681a0c0dcea"),
        (366, 1752625891, "0.5099999941", "37.058822", "0x65f275134bac32ceb72f942631c4b197354f980cab84030667aab30c121442af"),
        (367, 1752626365, "0.4099999983", "160.975608", "0x4b6ca50dcf10572c126133b1f48f41d400304176cd577a5e6a39c51b71c77d71"),
        (368, 1752626465, "0.4", "50", "0xf9faa775dca77f20f30f5db1d71a45b630f8d9d72f0bb6533b581ca1af216cb1"),
        (369, 1752626475, "0.41", "273.46", "0x079001ca54b589921faf6148cd63ef6f4a554cb9dbedbeb5a4ffce3533a712e7"),
        (370, 1752626697, "0.32", "222", "0x8b32af32aa4d4107854d1223719f1eca27bc612d9c1873ebab06cbf93c32f7f5"),
        (371, 1752626741, "0.32", "10", "0x8300609edbd90c88491ab9c1838123fcf6b0ba2c8266fb734936a8c894d72802"),
        (372, 1752626821, "0.4673938852", "715.97", "0xcbf4efa686afc8d12fbda6a789f518cc2b94cd2959edb1ff8aa8985ec46bca95"),
        (373, 1752627111, "0.4036239656", "495.510713", "0x39bdbd7ce668dc9241f0285807035a8e18b16b796618dd13c3ce0c160d960ae2"),
        (374, 1752627163, "0.3790523686", "527.631577", "0xd58125f2bd2f4fa8e71958798532d140be9e7719a36b3e7c4db8e84bf1a655d3"),
        (375, 1752627255, "0.3899999899", "30.769229", "0x0fb0f5b0acf9026de5408cf3fb94053108d58caecba8de36a19d5e60bbeb0842"),
        (376, 1752627285, "0.3899999982", "256.410255", "0x8203fd05e3129a6cf42c77c14960d748e05eb73bcbaa2fd04396869d6bd40d9d"),
        (377, 1752627285, "0.3899999899", "30.769229", "0xd980151cf5fcf796831319595c5812a6a099ff50b37d7f6b69d60c1e7685af4d"),
        (378, 1752627289, "0.4079206517", "245.145713", "0x3df97c5315dd0c78b4eb02cac3f7502191370810acd1219cdf6d139ae1d7f478"),
        (379, 1752627347, "0.3699999771", "27.027026", "0x15a55b6d07742fb93a3f9fd07d4958f08d70ab864be30d48ae65c3c93d86ea4b"),
        (380, 1752627377, "0.3519061438", "28.416665", "0xea24ff5e09682c2ea3a849cac427f1dfc88004cfd995ddba7def329d04139a1f"),
        (381, 1752627387, "0.3499999842", "28.571427", "0x33dfb2ea0d8c86c023f168bef468096cac1cd56dfe5c35a22f5e64137db45131"),
        (382, 1752627397, "0.3499999842", "28.571427", "0x36584ed5713c47ce834792a03c4f375dedec20b3a0068d7f3bfca1d9cc18ed56"),
        (383, 1752627465, "0.321637406", "31.090908", "0x353a3cba25f950159a0dc677049da1be9169f119dcb0d2cac7f0337c286653c0"),
        (384, 1752627475, "0.3219700538", "31.058786", "0x43fd11e608eb827fff8d4ba8625555bdedf7a7640186176221e6b00f90c03f6f"),
        (385, 1752627521, "0.2899999857", "48.275861", "0xd3370229809f98ee8d86547dd9e05c0e221f4e5e38acb3c3875e731338395590"),
        (386, 1752627533, "0.2699999806", "37.037036", "0x7101d2e15a002b65ca7d4888cf86feefd0a3a049995956cf4c535de881a728c9"),
        (387, 1752627545, "0.2699999806", "37.037036", "0xdcfee4ae6b128391dc79f7c61ce4cc9ccf11d52b8e3c0fe43c68acc84d3d0c3e"),
        (388, 1752627557, "0.2399999856", "41.666665", "0x08f336c1a426bcafa245202f7b1d9f43ee48d16c840cd4d0f7c13e2dd529534d"),
        (389, 1752627699, "0.17", "27.8", "0x6e373d8c4566162759eb8344f512ca3162442c5d7937ec7928742bdd2b7538c5"),
        (390, 1752627703, "0.1794747303", "422.64", "0x59921140899b2382634da08923855928aac9276c894dded06f322f7739ddcc6c"),
        (391, 1752627703, "0.16", "20", "0xc24e7ed04ac6277d16faac4dfda544cbce17869080c4da0470756a06b09c8e2f"),
        (392, 1752627703, "0.16", "24.99", "0xfcfcfe5421deba9e696e52798bf7d4a7fd18b79b213698bbd70bfd329c1c8f4b"),
        (393, 1752627739, "0.2151887385", "13.94125", "0x479180f4245b978a9fe91150db587e0daba4f415cba50c134a5ac90e7b89905a"),
        (394, 1752628191, "0.22", "96", "0x86b4355545a856af41c26d58b0a07a0c79b1a012f961d035956158d96766ed5b"),
        (395, 1752628199, "0.22", "500", "0x45652bad9912f8b9a01afe7c7fa90df7cfc5e88c9382a67cf26dbe2bc54472d6"),
        (396, 1752628205, "0.22", "48.19", "0x55aae5a06f48c0a276eb421458caeb5dabaa063e8e66183509c5fef69004e376"),
        (397, 1752628205, "0.2198889911", "9008.29", "0xf0e9809fbd0861fd4f0eb3682a184d4da3d663d7be11ba4dd5241e6902ebe19e"),
        (398, 1752628621, "0.25", "50", "0x644c18e7b10d15e022b87eaf4c397863b8f4afce3691fbfa69135e285897770b"),
        (399, 1752628625, "0.25", "49", "0xbd457c017635de8440f9787541e6443f4996635fa552c96df1a9c2121ccd0786"),
        (400, 1752628967, "0.2595555556", "225", "0xe58b0bcab21094cb097bcf68ab7b14869246c659dfff68834696ba4336b8c7d5"),
        (401, 1752629737, "0.14", "20", "0x39e18f526b587603e6d60d2a16425bef5da04c1d5b195710d9ce0a8dcc95d526"),
        (402, 1752629737, "0.143603936", "813", "0x649905d9c1e33dbdac7801c0c67f0686dbe1c808cc913090ba6fa261330b7da6"),
        (403, 1752629811, "0.1632932195", "612.395293", "0x2cb25b31246c6cc87abfddc6d2a371183fec1f4c987364774648a154d2985c69"),
        (404, 1752629975, "0.15", "10", "0xb6e0027e247cc1977bb2c5973a7bfe38cfff4a592eec2062c0237c6cc7aecb0f"),
        (405, 1752630277, "0.18", "29.99", "0x80397caa27f4d977cbf93ff145db60c8a3b6a8a02e1b03b084f40ff9ee85198c"),
        (406, 1752630291, "0.18", "20", "0x316bacf894c20c6db4255a91ea4fa3029e7b02de01674d3fca6810ea6d73ca29"),
        (407, 1752630345, "0.1817826427", "153.48", "0xdbd770aa322a576767104db6315d34b68d3016cb233c623a4181f384bfe5d628"),
        (408, 1752630369, "0.1903846154", "52", "0xa2124075078d54e51448aa9bfc64c8e04f0b92961abf2bcf54957fae6b0ed25a"),
        (409, 1752630457, "0.18", "100", "0xf33c19a28b4824176747cb77a9e48b846e8ae6890ec2dc101b1f5c64f9fa7fe6"),
        (410, 1752630537, "0.15", "20", "0xa143ca00c0ceb7f5babeda94f7fe96505c4a51b5db8506fce0c02b785a79bb0b"),
        (411, 1752630563, "0.15", "150", "0x2e0e658b56fecfda29d42562a24556b30ba73b4f98e3cbb77de5b25e83a6aaaf"),
        (412, 1752630563, "0.15", "155", "0x8f7fa0d5250c9488af693fb1a64d6a5a67390a8caa8ae732dbb985b15d8fe161"),
        (413, 1752630563, "0.15", "52", "0xc28f6e334ed73789be694f005bbdaed4722bce5dcb99923116b3a13444d1935e"),
        (414, 1752630563, "0.15", "70", "0xc6591990c8a323b1778f3640a728c83ebf8326687efa7acd5e84496c1f7ac6dc"),
        (415, 1752630615, "0.15", "77.33", "0x54440688f0dc7f54c2a4b1b59559f90380dc44bf4a79cb60738a19f5bba018d4"),
        (416, 1752630827, "0.16", "327.33", "0xae178ab6257fe31da4cc1382ade6800b4ba2f98c1d1f174c84c5d9a01acdc294"),
        (417, 1752630905, "0.17", "50", "0xb70a24a29465cd5624c2a49df935d3d8169ac0726931954461d2725d1bbc5290"),
        (418, 1752630909, "0.24", "37.5", "0xe71728b15d45ad6306109087263eee243ce4727033feacb15191867440670d1c"),
        (419, 1752631299, "0.16", "260", "0x557c402ef5e274193d4a0903c0fcacc0f9eee98f6113577a4699b23cc924d448"),
        (420, 1752631359, "0.16", "750", "0x17670e429211ccbb450a40763a559e85a3397423ff83a7efd8f0e6f439bd4d5c"),
        (421, 1752631781, "0.18", "3692.7", "0xbedd9d65f74c74193e7ddb89c77c304baecb2b3f1392734e9b01b00ee961fb43"),
        (422, 1752632521, "0.1699999968", "211.764704", "0x6f9fcc7134678591f556b0395e5339231d41363130f8a8cd4fd512456d9b5061"),
        (423, 1752632929, "0.1799999432", "13.722221", "0xd2671b8000691ae775bc596b6ba051dca632555a3ebd23faca4a3cf69477ff41"),
        (424, 1752633623, "0.17", "195", "0xba2227224a088dc5957e0344d484179e4a1899b8a906c4e4f77f6b7b407b6646"),
        (425, 1752634886, "0.17", "95.22", "0x97c24e52636d420a03b958c7aee9942050e8c447649527fb002c7a3c44c433a0"),
        (426, 1752634946, "0.1798722", "1000", "0xaced96169b1625135a4701c0485d9aae15bc73ad89ca4c157a8ac7aee557cae4"),
        (427, 1752636632, "0.17", "3895", "0x88a9f43b0c7d0c9dce7d37b4b788bf24ac316d83ee8d13687b5bca46cd908586"),
        (428, 1752639676, "0.17", "10", "0xa6122a600cc56b3921885163b7874adc0f052c162e283b380006df872e7f6eee"),
        (429, 1752643645, "0.1699998861", "5.882351", "0xdc88b4d662d90497803a538291538a88554fd01c705d84789b70bb80b74fda8d"),
        (430, 1752645735, "0.17", "1000", "0xe57a4ec8015e72b62be81cf5b50e70311d70a9a58a5cf17c9b1c2c60f2912b4b"),
        (431, 1752647195, "0.17", "1722.64", "0x5a8bb0926185f7a00c1988f3b6b25d1e8b6e44162fbe7f9a27b9645329a9d76e"),
        (432, 1752647757, "0.17", "90", "0x64351004970205082e889359446dcf780f2b61706df2afb56acb3d933b3ac55f"),
        (433, 1752647765, "0.17", "299.64", "0xa59dbc040f289630588f23338bd5547297ea67025db5e282a905ebaa0fa95586"),
        (434, 1752650303, "0.15", "5", "0x3c6c131bda9906b716ed33c003f40fc91c671b2aae085e3557fb3b846f210ca9"),
        (435, 1752650971, "0.15", "220", "0x24ca78eda735baa77b36d17b179526be7bf3d34381652caf09f06ac490e1683f"),
        (436, 1752651117, "0.15", "70", "0x62954b8cb33a93208ac642fc80b4dbce4d387ff8a16e5291655d5189e819311b"),
        (437, 1752653053, "0.16", "10", "0xd9f5968209461110c263c25d946689515f43ef7fc572266df0881a2a93211007"),
        (438, 1752655215, "0.16", "125", "0x741830397de8c2d41077718c8f0f494919e91560e6cd085c5c2b8bc14b10c29d"),
        (439, 1752656697, "0.149999976", "33.333332", "0x33bfaf3649480d922b8ef30a9fdd13fe449cb7b3c0ef21b2af05e23428094d95"),
        (440, 1752656790, "0.1499999887", "66.666665", "0xfbcb09fd10416453c8cabceed45b8d6e17c62dd0d145dad6b008d02830bf6a43"),
        (441, 1752657346, "0.1499998875", "6.666665", "0xda8973cf56527db4c1fff0ae48730c065ad950670d60a79eac70f0a6512c8ed1"),
        (442, 1752657440, "0.149999976", "33.333332", "0xdd3861988501a2451be45379067469e691c45b043ad53cdfe2075727c375c83b"),
        (443, 1752657458, "0.15", "34.48", "0xea112058e1a9d4d928b6c98fedaf4981d314c47688fd76014f07410aeff41858"),
        (444, 1752658755, "0.15", "8", "0x34ce38e3824f50270193e1b60da7892ace957f1a608f4c3e38ed6bbb8ebb8658"),
        (445, 1752659199, "0.15", "152.58", "0x1af459bc63efb3d92fee92f0fdf8ad84b8c2daabda79b292bcb1ccd17bf74573"),
        (446, 1752659201, "0.15", "10", "0x86db3de68f5c2220a2060ba5bc38378b668b82dd8708b363febabedd5505938b"),
        (447, 1752659291, "0.15", "20", "0x213f01f4d6fb103c849a6c818f59d0a80664278d41f406426e7ee10e707300c0"),
        (448, 1752659301, "0.15", "50", "0x3badb798c2580baf47f36573b6db7247abbf4b74b3b977b916e447ca335eedbc"),
        (449, 1752659309, "0.15", "58.61", "0xa1e094844892259c6fc4fce318af98dd1d5b096c9cc87f35d7eef7b824978c9f"),
        (450, 1752662537, "0.16", "112.5", "0x4945e9f506b18147cb85abb722241b6d75b0e551d5bea1d3277503fbb8340ad7"),
        (451, 1752663586, "0.16", "10", "0x7d633f330d4f60f793be664b4492ab03136435d4e73a290c47e8b61aa344563d"),
        (452, 1752664029, "0.16", "30", "0xf989c49c259f8d7f14b59284d6cee09ded7fe3200380f3baf9add7ddae340bbb"),
        (453, 1752667788, "0.16", "6.25", "0xf254a74a7d299f0993f09b51ef8162b1514c95da9e329795087650fad7b9f5f8"),
        (454, 1752668238, "0.16", "12.5", "0x3194774c1514fb58b9a2ae98ed53c7b0f7846efce3a6feb74379085d31baefd9"),
        (455, 1752668698, "0.16", "273.125", "0x66f2dc62215583b6925810ce72b00cf3bde0dd9512ca0b080fd44dce246a9898"),
        (456, 1752671336, "0.16", "90.05", "0x49e9bfe81043d66bcc9cbc703612c536bef0f24e6f479147ab734441b88f4721"),
        (457, 1752675624, "0.16", "6.25", "0xbd0419c965480daf22e53985a530d4290e41e1d95062f52af35204e15f4e31d8"),
        (458, 1752676324, "0.15", "6.25", "0x0236c8513051951e41806f38ccb9ba3a059e9282b333cd164b3eca1b508292cf"),
        (459, 1752677228, "0.15", "2499.99", "0xb76771806d6dd9f79af0f8b0eb1cc1e5778faaa5412e890546b9d364fea69287"),
        (460, 1752677258, "0.16", "772.375", "0x82fb1d89bcf6d50b0df8c95939a61d1da38529a668d070d8ee1b979c83ad5a57"),
        (461, 1752677442, "0.16", "70", "0x1648c834a1119605d8984d6adc4fcecaddf056ce0a747352b04e0c3526d0235c"),
        (462, 1752677986, "0.17", "60", "0x429b9b3f35de5d3ab49c645c9b12d44d5747def9101d54f65a1a16d1287b2aa4"),
        (463, 1752678924, "0.1699999937", "105.882351", "0xe039d66a25fb0234a762b54d61c3fb5e4e7cc1116d753509417da6ed1dcbec04"),
        (464, 1752678990, "0.17", "10000", "0x2070d9ce92c3e651ab7d8fdfbb83247f20e142dfedccf099539b81cb65725b67"),
        (465, 1752679776, "0.17", "182", "0x1256c1b6e320ca8bae6d7110936b989bba479fa4e996c5dacbf567664eaa23ef"),
        (466, 1752679864, "0.17", "0.19", "0x8e0a10fc182af2e5ddeb1f47b1c9b746bb2f603daa247b45ea8271e1f2ffcd63"),
        (467, 1752680856, "0.1699999871", "58.823528", "0xaaca777846d217f1985e33a9110c592423a56133cf488341f66e7488419b701f"),
        (468, 1752683432, "0.16", "33.33", "0xca219ec0397d05431e6bbb9557a41d1d3ed075a0a54ecca198f952cbda9428ae"),
        (469, 1752684838, "0.1699999969", "235.294116", "0xb8ea0435458467986d3ed21fd10723b69a652b6244500b1a25ea5349d13d1696"),
        (470, 1752687640, "0.1699998861", "5.882351", "0x241d1e5dc0eb6b7a445cd9ca3bea5bf2c5266a68bde4cb4d691f0917bacb2f47"),
        (471, 1752687650, "0.1699998861", "5.882351", "0xc5640b017572ac241043aadc12743af5e564f51bde95c1ef204c6de85af85b71"),
        (472, 1752690020, "0.1699999986", "588.235293", "0x432c4046b96a1ab273d874eae0c6c8c9fef01edb82628098526b6c8655ea650b"),
        (473, 1752690522, "0.17", "80", "0x17f31be6caa8c4f8c120a963605d914f55d0a873f93d291d9b0e9f9a56a2a959"),
        (474, 1752690610, "0.17", "80", "0x3d2fdc99aad8ac9868e4f561888837c15ceba987597290cef3822b127febb474"),
        (475, 1752691066, "0.1699999969", "235.294116", "0xfe76d379ac00d48ff3c1f480df538d1f334d8d5f92184a2618010a84120777d8"),
        (476, 1752691172, "0.17", "30", "0xa4fbdaf59ffac5a80a2f0628bff0de468153b30cdf963231c3d282ea3237409e"),
        (477, 1752691190, "0.179370405", "20000", "0xed5fa74ec53a2cefa6ab193b7c7a6ac90ff4c351106c215bbb7d2f2057866624"),
        (478, 1752691846, "0.18", "30", "0x2a3751cd0ee88e7d14d10599f19a965f44c3bfcb115e0a570ae7fe3f8d42bf19"),
        (479, 1752692078, "0.17", "50", "0x8ce61c444a0e6a1dc10dec7174910e5b79edef100c43ae4d697c6dfcd6438a89"),
        (480, 1752693470, "0.18", "1165.39", "0x758eaf22bbde03229cb3524155257460fe9a841e1c645ffba5599d062c4989c5"),
        (481, 1752694472, "0.19", "20", "0x27e1eed9d4e4e0428f17f8644d990ebb5b8b75cb89f7e7495c6069c1e6f32fbf"),
        (482, 1752694876, "0.19", "18", "0x990e9d60e11dbd71dff87975594627a88b573121769404c31ec29b0fb3a6504a"),
        (483, 1752695874, "0.19", "81.01", "0x0fe273b2e30568bb7262abab5fd5d7e2a741dc29712f72c2a2ad127337d1bafd"),
        (484, 1752697206, "0.19", "55", "0x973540ed9e85274c3db751205d2a5491ada28e9c3f42f58ed2d4185acf10d838"),
        (485, 1752698342, "0.1899999939", "105.263156", "0x2ac829e6c2ebe33fdfc6a12489fb6a4ed86b4da6eacb876b66301c7598566495"),
        (486, 1752699828, "0.19", "1397.29", "0x1a45966a91ee541c457995cc288939ef153fed2e53a69e0a9ee81a421209b87b"),
        (487, 1752699830, "0.21", "9.09", "0x2ec1425da915831158bd0b014b152f2bdb171cb4ae3fee077d7f59ac715a3644"),
        (488, 1752700132, "0.2099999922", "95.238094", "0x713ebebd07e1607c29ac44d0b3b465c2a2ab81af8c07b179da0a0ac184793896"),
        (489, 1752702280, "0.15", "560", "0x17196524f62d31afc67a3ce9dd305514931678b8b4acf6bad4b64172dd4fdbbf"),
        (490, 1752702332, "0.157790927", "31.6875", "0xd8b5d7de23800058c66cf0f4da06b94f6710f0f158af5747cbbe0ef7407de335"),
        (491, 1752703070, "0.12", "100", "0x776a15539c1dbaa44de8e37a512fb3d654b6d10e68b733956a3e578bbd8c0374"),
        (492, 1752703124, "0.13", "30.77", "0x68d13ee7f2d9e7c8b323b1663da80e10c7e503ebbcadfda5f06d2ba01bc1ce08"),
        (493, 1752703128, "0.14", "10", "0x1a93863feae3c0e0a1f497fe40bc885f430f0288a847f84ef4b5e9779bf519cb"),
        (494, 1752703128, "0.13", "90", "0x3c6875a0582bfde0cafbd9e275fc2f0d6a66bfc3522384df242c9ecbdc0492ef"),
        (495, 1752703128, "0.13", "4.23", "0xdc11c360334994f30b87a7e73c340e4b7c3043b1646cdf53aa2f1c59731e260d"),
        (496, 1752703140, "0.15", "20", "0xe7724ff8f3c4d144f2ec339e3faa5e8759dd8f7db1b49647f5e0cbd8d65dfb99"),
        (497, 1752704012, "0.1", "43", "0xbb4c02151f4f797a74a2b7bd513e8a6b3b829fa0245299c14b3bc377f74aa92e"),
        (498, 1752704012, "0.01", "202", "0xdeb55125488e203b5a45f8f2c6e09022ccca51dc3f2f3f155e582a70116933a0"),
    ]

    fileprivate static let retained563322Yes: [RetainedTrade] = [
        (0, 1752509278, "0.15", "100", "0xe839e518513af39921c186755a36350977c73f2eb6f4d0508b2eebc494e93a4f"),
        (1, 1752510580, "0.1399999962", "192.857141", "0x4ffd838569a50e10f7d3391e04de8f66e782d253bd83bedef48d5d73edbce13b"),
        (2, 1752511760, "0.14", "10", "0x602c8ff9e2ac3b9ed039869eb81ce3dae61348f6f4429815d2a2a2561cf50eae"),
        (3, 1752520219, "0.13", "9", "0x5ee6a3f621fdb4e8990da23acf2d50503ca2378d8b736f3943312adc7d5a246d"),
        (4, 1752520513, "0.12", "8", "0xad74b55e817d50709c8535b11498516811dc6ec61e5039797e85e59c43f41ac2"),
        (5, 1752521655, "0.1299999307", "11.53846", "0x6244fce283f3dd96f96ae00d547b7c81fd6823baa4e53bcadad968d801ee338e"),
        (6, 1752527715, "0.13", "79.46", "0xca858373fce632d01208ec272dde9e19df2fafa8a255443f53dd5334f8160ef5"),
        (7, 1752545195, "0.13", "23.37", "0x9a58dea3d4f9b74b8142f9dc6a235156656e17c56f6dbb565064b7315df89ea1"),
        (8, 1752545815, "0.13", "1.63", "0x998c5a7470d1cedd86a0ba82a1e00409cf038cebc8093cd388f2c2e0b0abfee5"),
        (9, 1752545823, "0.13", "23.25", "0x05cd46d3084c09d734c8f61a6069d38dba736d28b9035230dc22b7c6d0c6268e"),
        (10, 1752545823, "0.13", "21.63", "0x971f36985c024d16a012d6a0e5aa524afbba90b105c8111f8e98f4559c0e9671"),
        (11, 1752552355, "0.1367102658", "166.67", "0x0b2992730f0edcdc0f0bb2b7dccbdf2f9fc7c298ec4ff75305bdcef3ef605d62"),
        (12, 1752552355, "0.13", "6.67", "0x79f6b8730f9a093a733d9fc790e5a687e4505fb94b76e29e8706d4b2fc2a06d3"),
        (13, 1752552357, "0.14", "6.67", "0xcf33886641e6196f742c4271a6810e9a722a76186d5998c3bff4b84898836f1c"),
        (14, 1752552357, "0.14", "166.67", "0xe76464f382102cdf8894f75262a82f2af7957db9cdb1435c382d18acd51b7ad1"),
        (15, 1752552377, "0.13", "5", "0xc95e64b4070212335df7884ab6af6d7006e5c56fb643a27f05883072549e6b49"),
        (16, 1752552389, "0.13", "3.01", "0xc8f4d7882e22306fa03956984c9d861d83fca9d5db211d9aee03949c6c23f73e"),
        (17, 1752552401, "0.13", "3.99", "0xe24528529c7fa54823e7ad81a7186602d4c6806ded2868a7170c75a28da10d9c"),
        (18, 1752552403, "0.13", "21.01", "0xcd3d91c85a26561c3a67edef4a6bc49f7f2243e44df2cee06f71c5ba925d3f93"),
        (19, 1752552407, "0.13", "5.99", "0x73ff1ab867498e270298ab6545a632b8d29a20c92f409405f8768e8a1c1f75f2"),
        (20, 1752552411, "0.13", "27", "0xffbeaab527432d4ec3cea53e9c17e7633387461d05d12dab8bd527597edead0c"),
        (21, 1752552415, "0.12", "11.01", "0x6f3e414a4ff82e70e230373d201e75b16a44be27a76ae07bc69250e95593ce2c"),
        (22, 1752552417, "0.14", "6.25", "0x317840afe94b2ae64e4fe61a8133968d29446572109ce828fc779e2cae096254"),
        (23, 1752552417, "0.14", "156.25", "0xd0c30be55698b5e2b106050374601ade54b48725813c014bb7c8d0f86686bec8"),
        (24, 1752552433, "0.14", "6.25", "0x6df66ed051541e55bb5e06c43722954774e5a77551dca9e7fced14259144a0a1"),
        (25, 1752552433, "0.14", "156.25", "0xd7496c7f95e2f85eab75e0e551c1f901fe06555ae8c02de69d5d896e835b2328"),
        (26, 1752555153, "0.14", "156.25", "0x10e82848ecbc454d9ac84fa9446f78a7454f861cf84a2a0451a9c8e21c59a6ee"),
        (27, 1752555153, "0.14", "156.25", "0x334a13b3de8da5771fc2f3fcd1fa147f9ba34e6aaadbc2333f8cdea8db0099fe"),
        (28, 1752555153, "0.14", "6.25", "0x51437b90fd94b1436f7e7278c9e8e6fdf69f80ac464ec9d36b18eea0d5cf10b9"),
        (29, 1752555153, "0.14", "6.25", "0xb315733a144c1f972191d6e6d481afb79f38442522b4491ef52be275adb2031a"),
        (30, 1752556525, "0.14", "100", "0x47f3fba8cf1f3cba919cbbea78e2baab2dec54181a4eb8d353b87456d14229b5"),
        (31, 1752559307, "0.14", "6.25", "0xcdc929ef1be1fe5babbebedc23280ff84a5af66d680a007ce49367a7c0d1cd90"),
        (32, 1752559307, "0.14", "156.25", "0xf80bc8609beb3ef8b64aa9c0bc1ac31cc6ed01d87c0233ba529d6aea30ddfbb5"),
        (33, 1752559649, "0.14", "156.25", "0xa6982ec51208003d78ea26ea3b883786c8ec075071650a9197d681c30c779b82"),
        (34, 1752559651, "0.14", "6.25", "0x33ba473b4e7d7ee2ec2aab367906bc76257d62aba52f511fd3292e54ac8d3fa1"),
        (35, 1752563135, "0.1404441758", "356.013332", "0x84ed7cd577b92b6a096ee6bf9cf2bd8583e1b047992a8f142c8fc5562814afbf"),
        (36, 1752566349, "0.15", "147.06", "0xf5d834c6549b558256b7cfaa02c193390286e1be1baeb3d89f59fb2f72648ab1"),
        (37, 1752566381, "0.12", "103.83", "0x05801e24011600f8c9015ab833163ae45283f16e39d04322f84c90ec4fec4cee"),
        (38, 1752566385, "0.15", "156.25", "0x006f77202c2df1bdc4622851619bf2704f79f83198b71d7447a2c75a9abaa0ce"),
        (39, 1752566385, "0.142736", "156.25", "0x27fc02dbf1f4c8a18f0f9909b39c21e096baedb58d4f6fa8f02f3f30b95c8647"),
        (40, 1752566385, "0.15", "6.25", "0x2e50415375cf307c7a7ce4861f616cb157337d883358aeead6759c92a43a466e"),
        (41, 1752566385, "0.14", "6.25", "0x45fb81122d377a1522c92df50d41bdb5de8ce5489f25510f18d68a72b432b808"),
        (42, 1752566385, "0.14", "156.25", "0xdeb560797e07e8417b9d8d7d84ce45e82b5b18ce54b5a969425fafd7bf661ca7"),
        (43, 1752566385, "0.15", "147.06", "0xf7346d3c40c938cf60e6c1429b07c83aaa08eb12de2408d062382f98ba5cd2d1"),
        (44, 1752566654, "0.13", "80", "0x67ff9a0905b2833c22e353b24ac7f5118e7f88c7742bfb07c7f8530ca128dcc0"),
        (45, 1752566702, "0.12", "25", "0x74d45aa1a116e3c48d0563604f814164d248ee4ff7d94bd19f894ec1bf3c7168"),
        (46, 1752566704, "0.14", "6.25", "0x79c49a39a658f5b9aed225be908edab674f24f0c2490628d6a60d7786ea320e2"),
        (47, 1752566706, "0.14", "6.25", "0xf1031e88551a5441070ba66be742997e56ef6266d9fd78eee767db2068353dac"),
        (48, 1752566734, "0.14", "6.25", "0x65efa710077a7b806892043e4a48ba2e3c1bdfdd499b967e762164454e8b4ff0"),
        (49, 1752566738, "0.14", "6.25", "0x2d9a7cde713c1a3292dcc75420513862e5be340e3f3c46fc0c2ebc735b5fc9f7"),
        (50, 1752566750, "0.12", "22", "0x43a7a16a2460d70b4c8a025a625707e2e8382bc17f14ddc20a79251e2ebc6e33"),
        (51, 1752566754, "0.13", "6.25", "0x765ce69ee68907afdda7841bf6b8e50497618803d5dd50a7c9b396dc0a6b9f0e"),
        (52, 1752566764, "0.12", "11.66", "0x68cec7caf42601adeb8d7cc7efc3f8f63f1d921d2c0844a9e4d8c3fb5979c003"),
        (53, 1752566766, "0.14", "6.25", "0x19bf8a56f00b98acb38524cbb7bf1e79ce1de70dab0ce830bcfdd5886095a9d1"),
        (54, 1752566814, "0.12", "206.62", "0xe102d7a64350f28a446feef02747d4dade659ae3f662629dd1233f4a9af04324"),
        (55, 1752566818, "0.13", "6.67", "0x5f6d68205924e3aa0fcbf70ac13fa3b4570dfe451d43d93bb168ff65c5d7195e"),
        (56, 1752566818, "0.13", "6.67", "0xd421c0d94146f7e8a0c9ec6de6367e8ccb58919d91d18640035e166ef0e62006"),
        (57, 1752566820, "0.13", "6.67", "0x13bde3f71ca9650c82782cde77b00eae43ca691de76aa67cea55b7107113673e"),
        (58, 1752566834, "0.13", "27", "0xac7e681a356603bb67e428df95abc1ff0a152bb2cfa1da58a3116fdb1351ef06"),
        (59, 1752566848, "0.13", "27", "0x98db979f273232da9295b7720ea8ded930463974dec100b2fde42c199aaed7a5"),
        (60, 1752566860, "0.13", "27", "0xfaa0e11246b8a1261dc9621ebbff13edbbddae1e24aea0609f378ea8ba6809aa"),
        (61, 1752567939, "0.13", "6.67", "0xcd1977f49b73324f231a0b042929aeaca0796a104809b7532733b26a1530bb5d"),
        (62, 1752567963, "0.14", "6.25", "0xafe33a88259a908cbfbaeaad99f1e5d4ad9085ee73abcbf21bebc7f2310b978e"),
        (63, 1752567965, "0.14", "6.25", "0x8906a444d667c4d2a6fcacb7812fb37fc34872c4befbb4f8cacdfdbecba9f436"),
        (64, 1752568198, "0.13", "6.67", "0x5f2ab116c149bad7befe6ece4e047181645f3e86d76a342d510a5c7bea5c145a"),
        (65, 1752568208, "0.13", "6.67", "0x9e9bbfbea828799b2cf6d35414194e17c44c69131bf4dc052afaa090cddd838e"),
        (66, 1752568514, "0.14", "6.25", "0x6b43b1f38cba49f9bc85e6769931e834e17464667b4e018453f730aab6b6a78a"),
        (67, 1752568522, "0.12", "1.91", "0x2a379eac117bca8a8c46b0fd39940ecb49a64d104a878f3b243eb2f6a4ae1c2b"),
        (68, 1752568578, "0.14", "6.25", "0x3b376f80d6b846203094f294c04bd226731f74fa72a2aaa3b3ad87696468dc11"),
        (69, 1752568714, "0.12", "5", "0xbd3bbaca230088983c24adb2a6f755e6bc6900c96ee6c816fd3e397b4ebe0114"),
        (70, 1752569323, "0.1399999627", "21.42857", "0xaea0b9fe6f3789deeba6c1ffadc82f810e2f5dfb0a9725a320e17a752a82bd39"),
        (71, 1752569809, "0.12", "10", "0x14c5745c5cdc8a31d1d90395a7f3a4bfc08155423ff2ff361a4c98a7d5aa1362"),
        (72, 1752569811, "0.14", "6.25", "0x414a9e1f7277c982154e76db97a904ea3004b057fdcd09743ec8c1054328ccd8"),
        (73, 1752569817, "0.14", "6.25", "0x78db20e68d2f428bf7985148974988dd2dea3baedfb65a0af2ed9714867c9d6e"),
        (74, 1752570173, "0.13", "6.67", "0x0bc079afe93d7bac96a23d46abb77c42137e637ee44c3c4565494ff72340b3e4"),
        (75, 1752570173, "0.13", "6.67", "0x21bd1eebce227dbb94fd2b3adb91f421c007eba2bb778b3a6577a9e27ce09046"),
        (76, 1752570173, "0.13", "6.67", "0x32e0609019a799080d4e1d46f9932b8a875b42a659d08df7242718af6a4ef323"),
        (77, 1752570173, "0.13", "6.67", "0x582080380f34f796190aaaf812a5c54765316076f3597544f68699c2f3f40e27"),
        (78, 1752570173, "0.13", "6.67", "0xc5c7e28c30c30bdb7eb1ddcf3bab2a6c43863be07c31e705f82a3855cf82be4f"),
        (79, 1752570177, "0.13", "6.67", "0x5bd1b8de664530f6e2c1d59fa05f3c703273914d3a86d42199527a02e7ad449b"),
        (80, 1752570177, "0.13", "6.67", "0xc0e57c1da80b8fc1bb4f56fe809ac5db5f2f081ceeff3cc39f49e72a3b7af841"),
        (81, 1752570181, "0.14", "6.25", "0x065348ba1629aac37363d42c912ddc3251fa49900f28dc1eb7465ed2cf64e678"),
        (82, 1752570209, "0.14", "6.25", "0x422a6247d6249c939f84499e04aef2156dffd3f6af9fd39a6e2d56ed14cd21a0"),
        (83, 1752570209, "0.14", "6.25", "0x4b5b56081163c2c8e7868bdad2f4ddfc01e88d1e1911c9cc54be3ed7b1afd468"),
        (84, 1752570209, "0.14", "6.25", "0x934379a3badadf333f5aac47f3a91ced1572034310a451d9e83557f112b896ed"),
        (85, 1752570209, "0.14", "6.25", "0xb778541aaeb15eabc4a1f771ac5cc6792e5dc67c2576188cb759a495c7681e73"),
        (86, 1752570215, "0.14", "6.25", "0xd6171933c16f3df8a2d9abed43adc630fc54d648fbca661c4043662cbbf972a6"),
        (87, 1752570329, "0.14", "6.25", "0x276b7b339ec6569b69ad4bc5bf4d84c6ac3af74f15906e8a4acbc7d08b842131"),
        (88, 1752570331, "0.14", "6.25", "0x6ea25d93870221531c576069b9024784a201afe8b3db4cc1471721a54d6602c2"),
        (89, 1752570575, "0.13", "6.67", "0x123a18b2ac280d9811e8c4e378470d5fe519264f94d92a58e8d45e61fe251a51"),
        (90, 1752570575, "0.13", "6.67", "0xb1865b547b8ec6d51fc65916180002c6d0ccd06497e37d13fd05350aa0de9307"),
        (91, 1752570643, "0.12", "223.09", "0x1c626ec0fd72dd82cd1c1f9b398cdf9a5a93f31d22c33ceba9a2f7bb6958b0de"),
        (92, 1752570647, "0.13", "6.67", "0x951e13c930b6691cfd1d55219db6f48549bacd2e86b366fc76cc4fddf4cdf86e"),
        (93, 1752570647, "0.13", "6.67", "0xa33731a714841401cc677de314bd22f89d68c7728e0c327a5004786d8484d58f"),
        (94, 1752570647, "0.13", "6.67", "0xefcb434e7b21858e8356b29227db5866aa3abcb71e0165d843ec4482f4d9a477"),
        (95, 1752570651, "0.13", "6.67", "0x0fa48a1a567d9a89c221d6e45cd74a9a77d2a85e1d1336fd5aad91238e912d61"),
        (96, 1752570651, "0.13", "6.67", "0x60ac7453fed74878cec37df6a7ab901aedad1e4c286c355f8cb09ff7032e519b"),
        (97, 1752570651, "0.13", "6.67", "0xe076f48b78da636e49dae12804259e4ecec21d70430695a16e7e86f6992ffc57"),
        (98, 1752570655, "0.13", "6.67", "0x2a39adda90fec6950b7a664262ce3d248a45cd0ceba3d048d586ffaa5837258c"),
        (99, 1752570829, "0.12", "240", "0x4b551c6d54b47ad9946dfd90a16282cfdce76f0c655332357f6cf16ba10c9971"),
        (100, 1752570831, "0.13", "6.67", "0x855e84c2974ec17ca47131e1e76cbe7bf05cd61d0bf7f06bb6e0d2f0a6fc21f6"),
        (101, 1752570831, "0.13", "6.67", "0xb3e9450dd54cb3eef16fdffc50e638b20f8e0a8d8666b24a98aea2756e8df787"),
        (102, 1752570831, "0.13", "6.67", "0xcae0e80bc156be434c26fca7231848c8222eeb2818b8c570023a9cb7fa2aba3b"),
        (103, 1752570831, "0.13", "6.67", "0xdb124c80daa86e8ee6463a9fd2fcb503f4cdb583f2acaee07430b5be9044aa0d"),
        (104, 1752570831, "0.13", "6.67", "0xfafae8dd0dae91913ddd8b4227a31a28cbb97248ebfcbd5021bd1b558487beff"),
        (105, 1752570837, "0.13", "6.67", "0x6c7cf7a0d3e035407049f22faf021614dcafb206526195f7c0d9539bba4cde7c"),
        (106, 1752570863, "0.13", "6.67", "0xad00a58b881ca96c60499a72353b762024731c9773cf9afd6aa0a7c4ef3fdb52"),
        (107, 1752570865, "0.12", "5.28", "0xfb9f8dee47ec07f0118d816af484a5181d7e2c9052dcb24cf9c862b2b1ba5617"),
        (108, 1752570867, "0.13", "6.67", "0x9a9623c402f4190e0ab3cf1dfdc43fba94c06e1451be85ce8ff1a87b996a08e0"),
        (109, 1752570867, "0.12", "195", "0xc34f70d13fe07b945b228e293180c1f887be8b27cd455e57b9b9dbe5e7579ed9"),
        (110, 1752570869, "0.12", "39.72", "0x96bf54cade3f8d95a93cf8edb0ee50a992578ec88b06dd6f1789d04f077baaad"),
        (111, 1752570871, "0.13", "6.67", "0xe87a83dc2d96e1a8469efc05bc83fbd0d9bdb37002dcc74fd4909d8f2f94bd8d"),
        (112, 1752570877, "0.13", "6.67", "0xf9fe2692394a998b36504b00e331b03e063052ac43ece7a173d2dc7031cf7f98"),
        (113, 1752570885, "0.13", "6.67", "0x70f39fa652045c9ede3fd45cf43c00b8a6dae688ea6f3a793146d73f7da11b65"),
        (114, 1752570891, "0.13", "6.67", "0xd394bea90d224abd2963ae63fdd3ae1f1586c4d31837a0befceb59788e0de08d"),
        (115, 1752570891, "0.13", "6.67", "0xecd8b6fb9c312832f11732c82e915981ae50d27dd88fd52dc6757bd3edf1a3ff"),
        (116, 1752570891, "0.13", "6.67", "0xfda6e8752c0dcbc3fbe78793a7a9531d03f93d94e34a901b29d1adab06c805a7"),
        (117, 1752570893, "0.13", "6.67", "0xf79a83c4b6833f8bd4e23707981d32c984a0cce66e19881cf641365ab8ee68e5"),
        (118, 1752570895, "0.13", "6.67", "0xef2c9640aa7db2fa97250afc08d2be266d5fa5c69c9920229c93e5d22c08b2eb"),
        (119, 1752570899, "0.13", "6.67", "0xb1ace9c006aa39d6692cb296fd6654b634da22de12ca20beb2470ebce0098019"),
        (120, 1752570905, "0.13", "6.67", "0x321d40e77de38d06d2c0d2b7699d0bee5f1e55533ee2e1fccc2f693c625c62db"),
        (121, 1752570915, "0.13", "6.67", "0x0e5e37997ad6c8e0ad1c9da4ada07a56e6bef2223c504b79d3f3ee632dacc7a0"),
        (122, 1752570921, "0.13", "6.67", "0xac4c6aa961b2da44dfa75ca4da7012cb77f9ddf18648cf7dbe0aa36ddc2e794c"),
        (123, 1752570937, "0.13", "6.67", "0x8aeb0c4e4eb7476be465a60f6d2302b66a55b150ca254b6f596471aaa254230f"),
        (124, 1752570941, "0.13", "6.67", "0xc4327c2e585324d8b87db9652f27b5c642b8d7c3ec5c475e83798366309286a2"),
        (125, 1752570953, "0.13", "6.67", "0x88b671f0788fd23eb88113eb7139e39cd65692ddebadf76157330a7774a3c226"),
        (126, 1752570957, "0.13", "6.67", "0xbec549e08de09a7530453a35a2c821e81944761ab158aa4dad9183f1953c261e"),
        (127, 1752570969, "0.13", "6.67", "0x057cd5889ed45e4091cfdd29bb7dc2fd946c9ae45e226548c9c7aecd4a89725f"),
        (128, 1752570985, "0.13", "6.67", "0x395242639e1c72d6b4ad329a828c815ef0e06f2ac8af432f2abbdcb95e719264"),
        (129, 1752570989, "0.13", "6.67", "0x076a41f942f58ad17896a33372edbf2b5032f6b5fda074bded28fc5936268626"),
        (130, 1752570989, "0.12", "240", "0xb128107f8c4910b82a321246306a589ebd10b1e855391db5699236a7e2e6ebbf"),
        (131, 1752570993, "0.13", "6.67", "0x7aca1b0ce9b9224f1a8e795aeffc718c365049f5052b617eb52352abffdd25c4"),
        (132, 1752570993, "0.13", "6.67", "0xfb895b7765fa274198b8c7816217d7bc561b5e926da2bc07f3c49636bc8b0f26"),
        (133, 1752571001, "0.13", "6.67", "0x22d44c1f317e2acc5ebe0637db3ae655b5e4102c6aef23f054fbfa690ac75379"),
        (134, 1752571001, "0.13", "6.67", "0x240bf02e3179dc2040c02a90801b3a8a75895b58c055306e742ec6f8bd9063c8"),
        (135, 1752571001, "0.13", "6.67", "0x8d47dc84ef3b0e31122ec6493728e333d4c08dd44974476afdbb3bb0416b8793"),
        (136, 1752571021, "0.13", "6.67", "0xc2c41d7a1edac359d2e61fbbf358f12d804cdf1db2e819f5edfe5c74695ca5a2"),
        (137, 1752571163, "0.13", "6.67", "0x6ce9e549eb5813c0e8f1759b8c7b22785ef0e15af6f23542092213f8e610d9e1"),
        (138, 1752571163, "0.13", "6.67", "0x93ef4b57e6f7a88f84cdbeace72538759503c63ef20e9b3f78478a62b44e2480"),
        (139, 1752571163, "0.13", "6.67", "0xb45cedf9216e0eb17d3fc29126ab3a4f8e59bbbc09e3e23b352199df1169ffa3"),
        (140, 1752571191, "0.136510029", "1086.51357", "0xd72d42d77dd8abef2621b9e76b6c394a060a3ee6faaf56dcb93f3f2782bc20c8"),
        (141, 1752571297, "0.14", "45", "0x0cc6af6314327c23b60890c002c472c77b82918f6483430586ea8214290e0196"),
        (142, 1752571751, "0.13", "50", "0xab89b15fea95ffe2bae77ddff974ab3f239915528dfd3c6cb21155de33e8e459"),
        (143, 1752578907, "0.13", "1.41", "0x7decec99a5c0084660e20efec4624f43e7b7f663bb74e8e1fcf9915fbd983ac6"),
        (144, 1752579313, "0.13", "18", "0x21d190ee20dbffaa9d954c30702ab83cca421910c4080b1faa5b574f8ba76326"),
        (145, 1752579557, "0.14", "184", "0x1931b2a358641d19921d919c14b5f71c507d625aafc53a3d152861cc9dde780d"),
        (146, 1752588081, "0.13", "3", "0x4a29c65f506b9465e6f65b0c404947b3ca7b9c90e0799e0501310411948b7ae3"),
        (147, 1752589827, "0.13", "77.63", "0x075a30cbf6cc6ee5334335c87a2ae611396380c62e484c5de200be3b672beb60"),
        (148, 1752591261, "0.13", "26.09", "0x372a292a30a80cac53e6a5e1764f60c2ad290c42e3338a4800905096c210a0c3"),
        (149, 1752595188, "0.1210444167", "1200", "0x6a8d9c604f04ffa155f937864dd27d716547c3eb166e131fda4634e4bd6bba4f"),
        (150, 1752595432, "0.14", "150", "0x2ddb280c6734b1496f92f188b431462f92d0cf75f496ebce49849694da7cdd1a"),
        (151, 1752598768, "0.1399999888", "71.42857", "0x9adbe6d28d134697e42c5f953a028f5efd4076c18b0f580f78d542559f3157fc"),
        (152, 1752599751, "0.1399999868", "63.642856", "0xc84815a6656614972100db266a48a94454dc1d5d78794fa647677760ecf7d052"),
        (153, 1752601347, "0.14", "217.22", "0xf3b711525d5930a1a104bee3489b9a0f9bc99c42ef246feda37d9448fb8eda18"),
        (154, 1752603351, "0.14", "5", "0xa032df797c7f5a27f30acff07de82ad921f05c61429ea6fe3108d1fda5a481e3"),
        (155, 1752603429, "0.14", "86.99", "0xea697fedadaee0ff7592a33682498975eb05d0ef310b02be0ba9165037746b93"),
        (156, 1752603796, "0.13", "3", "0x4a82b74d701093faf6fce0e5453c6d461e77a3c4702a79f926c7ed108b484d92"),
        (157, 1752605764, "0.13", "2.96", "0xff0d37de89d0afbaa975a7caa5e3c6d4d9be6fc8a7a3bcd211c897763c356edf"),
        (158, 1752607254, "0.12", "200", "0x03174054381f6058f91b6822fdff9c7ff6d05faf0e41d4c88a5e4e1aa396a56d"),
        (159, 1752607394, "0.14269468", "770.876665", "0x32c0d6cc1eb70fd98014210089dc933d3fc89d5fb4d484b1ab6b744939c7eb80"),
        (160, 1752607556, "0.13", "167.24", "0x1e8d4a2f27e4e5c135fd0316bf062a51e2db8a286e172156d9261851d906178a"),
        (161, 1752607578, "0.13", "8", "0x938e850a6123ecf0cf410156b852b92eb01ad497e22d53cc47db92524d4d1025"),
        (162, 1752607582, "0.13", "5", "0x39666bd5a1356a638e7d588db05ab22a6a17a4c93543ddd8aab15f0a1d0d83a6"),
        (163, 1752607588, "0.13", "24", "0x24610c1124c4e224579480741e6e998d6bfa57319c50287ce5f0ee1d5fae7d06"),
        (164, 1752607990, "0.13", "165.03", "0xb3a2cc1500d4df6175dd5275b527143ec09e2e84137c9d8a96ef60ec684c57bb"),
        (165, 1752608596, "0.13", "209.97", "0xa5f9a26f653e48992172e60a5c5d37412062fcf2e96b19cef61869da429b5ff7"),
        (166, 1752609236, "0.13", "10", "0xfa4998276ebc34b71b057e109952ab9fcddbc6d66c1e6178f9f66a0698c211d9"),
        (167, 1752609704, "0.13", "5", "0x6b4b377e38eb9f35842e3fe15844a298ce57b5ac9ebed5e9cd4018c91cb6c575"),
        (168, 1752609952, "0.1492537313", "67", "0xffa887355bc99e646d3513d68f5fd61208a180cd268510f14e3b8233bd3cfe70"),
        (169, 1752610250, "0.15", "1000", "0x6d14aaaccecf74e89faeff01d903f6e877b7db8e6cc6b352b6282d95e79b8ea2"),
        (170, 1752610538, "0.15", "7454", "0x6488c5068e0668313c922dcf0958c110a2a2b2b4ee41b07a98dac912f5768c19"),
        (171, 1752610958, "0.12", "9", "0xef0cb6f496abf2730d67cd780883a2cab6319a4e727998b53ffe38681769a8e3"),
        (172, 1752611094, "0.13", "330", "0xbf4362121f72a5c5da6064171f4cf63aaf45435b43184dd0bcf2eb0bd0b56ce1"),
        (173, 1752612409, "0.12", "5", "0x56189c726dd6245f2e1d5581b6b0d8141059d59aa788187709fdd450cc897529"),
        (174, 1752613177, "0.1299999975", "307.692306", "0xb0d68c6e01ef620c982248a97452c11b95b24c65b943d2c1d9087a837f3b241b"),
        (175, 1752613959, "0.16", "25", "0x874c2b476a112ec49837f101072a440549d987af6531b7178bac8d09ce462d9e"),
        (176, 1752619297, "0.16", "18.75", "0x0237013317a9da9da0025c3c14bdd07690fcbeee8e8c57d855b8746e33000be9"),
        (177, 1752619315, "0.1", "400", "0x1ff3a969059178b797bdad128b1b4f945d8cf437107ee0ac5b64d7b1203af876"),
        (178, 1752620729, "0.166240763", "150.444443", "0x0e19140d6a5a8b1bb544bcfbda416419302496195ec747879e5b3735039c005f"),
        (179, 1752623437, "0.1199998992", "8.333332", "0x7ea25075cf0135278f03706667194de523744f8f4b711893022888930ae0d204"),
        (180, 1752623537, "0.0952380952", "63", "0xe59c01021fa8fe2e2c3004fef0fc948c9062454ce249066f155261158d0d45a0"),
        (181, 1752623597, "0.07", "8.33", "0x3f468749e3b9e404c26c1d3ffad9026e99ccada05b14e892b14168bc3f3bef35"),
        (182, 1752623651, "0.0975927131", "30.74", "0x60a50e94d173cff673be00b10566cf602b63200cde728d4c26c25190d7157874"),
        (183, 1752623869, "0.07", "35", "0xda94be058734a04ba0ec370b250f8cc2a8aa6b6292c26501267239443ec5f628"),
        (184, 1752623873, "0.06", "2.01", "0xbb8859dca7d378984072afa9cad3c00f63a74245505e2f5b37abec745a86fe36"),
        (185, 1752623883, "0.0531490833", "1200", "0xd8ff9897047004b9e864a85b3750784026898f0e4f90378aa09f5e105f67d02e"),
        (186, 1752623925, "0.0898725299", "312.23", "0x4b45a5fac61e18735588f3934aafaee6292c582d0fcddb1bd1e0ef42f48cb5b6"),
        (187, 1752623941, "0.1", "53.03", "0xb7d97ee626821439626f307bae4edbabca93a7daeb0178071e7e059e52b00846"),
        (188, 1752623949, "0.1", "10.01", "0x862b72fa92ad123d6f31c824c0d2d57a895cbc7238234083b9935231b6f089af"),
        (189, 1752623973, "0.1", "16", "0x3e1e7cf6d9a291ee7f69accfbbfc78ecf46e1ac4e05ef65079eda3eaa383d6a0"),
        (190, 1752624075, "0.1", "44.85", "0xf4e9047ffad4d5832d9f96f85c21ab49f117d055cec77da0febb22f4c67c4041"),
        (191, 1752624117, "0.1240251954", "806.287776", "0x4e7dc7e67981d5dc381edb81103845d4d2298eab1ad6fe19aa1c488f6e5de88b"),
        (192, 1752624119, "0.1", "22.46", "0xe0f59451febd86af67476ea490c1dbddc0efaafdbf76a88dab24bf005a5f3658"),
        (193, 1752624121, "0.1", "36.14", "0x1a15cb73a3418a721b16c4c8bd0df9b90fd4a0973f9c9d25128064278612bf33"),
        (194, 1752624151, "0.11", "1", "0x0241562c522ae1f57c7059cf1df967b6a7cc1d5c415c23338356a07b796ea381"),
        (195, 1752624169, "0.1", "111.09", "0x05803db05b0ccb2a96e07540814ece79ce84768e7e4a8c570a93698ef925fb9d"),
        (196, 1752624181, "0.1", "29", "0x25303c33ddf479c577c53abc0e79cd50e82d64a20627529c29e190f852d271d5"),
        (197, 1752624185, "0.1", "21", "0xca678cc1f3cf70b786fcedfeea70c1d583596ad917dea49b321b450f1cf43d66"),
        (198, 1752624189, "0.1", "9.87", "0x8a341a3acdc3680176a0f2d3fe120264f30ef2e5eeeadb0d7d50b9450f24db60"),
        (199, 1752624335, "0.08", "16", "0x4798dd0972eb2a07c153a65a73c0755119dae9423368950d477dc6ca453e6eb0"),
        (200, 1752624369, "0.08", "23.99", "0x926d01fd4e0e7b7df60cb9a40e6dcd3147516a5151f61649119ba941037e0367"),
        (201, 1752624377, "0.1838904306", "543.802082", "0x0e390a323caae91ab57ed7242f921a168d1db677322d40968af690a3626ced97"),
        (202, 1752624457, "0.12", "23.99", "0x7caa90422c0f0956b1919ba6eafad7eeac09fdc1cbad4e3ee38066063e290ca7"),
        (203, 1752624501, "0.2", "16", "0xb986ede13f42d3b53e4bb4c8d8b67fed2e3e867ededaf220648c4c4c91d2d5e5"),
        (204, 1752624513, "0.13", "5", "0xb9e2cc2b84b29f3d3a8cfc103627ffb4e24d9f8274c9b8c71752fc1f691958ae"),
        (205, 1752624935, "0.09", "38.99", "0x2d138f03de004b1404e63fc52ff7a1d789d97dcf9ea42e1c58255d133ebb611b"),
        (206, 1752624935, "0.09", "39", "0xae3907e50333e78e934072f63c3752f117e32403e85ba6016f5ba8ae90097e87"),
        (207, 1752625113, "0.0938166311", "117.25", "0x9657c0acec68415d965cb4463e117fa2a4b3aaef306a79ab4ede4c2e0bd481d5"),
        (208, 1752625345, "0.09", "31", "0xbf4823a782e0efec6a87ff53c716b04195136068c315ebdb7d09b6457150d0e2"),
        (209, 1752626083, "0.11", "100", "0x7639777ad58c11b1ff1cf810c7a719ca9a76f8ef19371bddf228c085097b056b"),
        (210, 1752626661, "0.08", "50", "0x96a26e658209f97d24391c74bafda2b2d05e74a9eea6db3dc42732748863970d"),
        (211, 1752626741, "0.07", "10", "0x27f813e33b2585f0566437ce18d8f1493d4ef3380616b3bc17d99b01d8838990"),
        (212, 1752626899, "0.08", "103", "0xb25b080769f7ff08295b1a3a68fda9f72fb929c7540ae58d6e91a300a9b2cf0d"),
        (213, 1752626973, "0.07", "32", "0x0b1851c9d009ef82bd96498a35a1a695e65763ce77fddfdc6446f8a21d79fdca"),
        (214, 1752627231, "0.07", "10", "0x069cf8caf5a7295b5fcfde64c138505aea1d7950438018de0901e95f20e2ca4a"),
        (215, 1752627387, "0.0558861844", "291.7", "0xd536ac450e74cb57e631ed4761c4303ce498698959851070948f83685dc6ba0f"),
        (216, 1752627465, "0.06", "64", "0x3d6c6ec95fb1283454501029d1497aea6edfd41a64823320eef305ea90ad9800"),
        (217, 1752627703, "0.04", "25", "0x885dc725c11072a96ea613f3ea769fb94ae69a973ee5d0b1d6855790eb27c79f"),
        (218, 1752629737, "0.011", "25", "0x7f061ef4630f519edada126842aaa1f678171911dd6161574051de1912324d1e"),
        (219, 1752629741, "0.011", "99.28", "0x95998e667776b7eae3f9e10164cab61e15a2a443c415dc12eaa3c8d216e72982"),
        (220, 1752629893, "0.0188736667", "1500", "0xefa5ef782338757c2b7860a48647a6acec5167d5bae26abef423f8c803c6488a"),
        (221, 1752630275, "0.011", "10", "0x74d37849be7ef487df4e064de460c1917b03a15d2e61cacbbb0420cf3d7c59e4"),
        (222, 1752630517, "0.02", "50", "0x3ea01db253a320d872e4731f780e5403ed54714a6fd70f100d8626c20e72b6b8"),
        (223, 1752630537, "0.02", "25.67", "0x9a05e49a45b694c3fca476d888e96bc4667e74c1f4aa30103dc304558d81635c"),
        (224, 1752630563, "0.021", "5", "0x414efdcd46652e7fd997b21a7a7fc07eb7444e417ebe6cfe5811ddaf8adfcebf"),
        (225, 1752630563, "0.021", "305", "0xfd4142adffef881956b9bf9d600255a99ca406ec29b9a9d2888bcd4325c4d85b"),
        (226, 1752630579, "0.021", "70", "0x5e9a66e9281191cc8abc959a7e056246b5829f006d69a90a0dda4de4b84d0e04"),
        (227, 1752630957, "0.025", "20000", "0x0c83d304c5f7366ba45dbf3417cad137785eda2f1b088725d42a6b5d4705c869"),
        (228, 1752631057, "0.023999977", "41.666665", "0xc22339a48a98c15b3e1bab41c7294baedb0b7faeeca9a1f0471c27d96a87c930"),
        (229, 1752631619, "0.023", "200", "0x3e98ddaee523fff277baf51737606b8c1a6a74d1392537ba447da4ad73fdf533"),
        (230, 1752631803, "0.0229999972", "339.130433", "0x6a4b1aa3457ccc82b8bff73a28f38201f6bc69c405332ba8fd6932060be3c2af"),
        (231, 1752632237, "0.022", "458.33", "0xf0b7284376dcbd8332c39af5e4077579a22b7eea4fa12e7d2cb9353d9f0a664f"),
        (232, 1752633791, "0.023", "352", "0xb2324a6d1c94213bbf78802988efe9bd2418bd9298759c1db29b554bec380e6d"),
        (233, 1752633793, "0.022", "541.67", "0xfd05d26fdb58a9ba3ccef1dd9c600f5d03368ffd2b438916b46882aad8766fc5"),
        (234, 1752633893, "0.0200188864", "20385", "0x4c0b2dc44915fb47c84fd4da91a5c5976eaa007989db107bdb470ddbbbf7c110"),
        (235, 1752633917, "0.0229357798", "43.6", "0x7c14a0adaa99aea9ea6955d25911201fc695e8c220e76ba2ebeb9f5894c528bd"),
        (236, 1752634772, "0.017", "5", "0xea9394a73db1c434e1045642bb3cb778a8e47b51119aa472b54264e4878937bc"),
        (237, 1752635306, "0.02", "19935", "0x5dd78c8238950e8b9482c30594e05b4ce025484861772badccb9bf7371e4a527"),
        (238, 1752635370, "0.014", "4059.41", "0x66464f5b04864a6b67f7623850813d9bcfa0a24fb073ea05f567e44a60de9201"),
        (239, 1752636702, "0.027", "222.222222", "0xb376fb29b7af7bd96cc04ca351210890927ed70702261393254e09cb89fb695a"),
        (240, 1752637044, "0.025", "40", "0xdc0e2e1df230b355683941a7c3a42f1ef42571319a96219e6197c2cc424bd487"),
        (241, 1752639212, "0.0181679453", "2959", "0x2d813ab1a58c93d9492ac0b98a6363b2ba6637099e66e70122f3ce557a8b3fef"),
        (242, 1752639434, "0.0259044616", "732.69", "0x8ddddbb0eae7916d00695baf0115739cd1fa6296b173bd1d6c245070be708069"),
        (243, 1752641052, "0.026", "60", "0xd401d9a72102f1ba0c0f65e235442db1bc79da8dae4acfc237a50306c78062c6"),
        (244, 1752641568, "0.028", "123", "0xd4f42900106dd5658fed7bba38fe8cd7ec7116bc482e3e9c55009bb4460bfebf"),
        (245, 1752643090, "0.0265", "20", "0x0688401e30cb505acbcffe23b182ec8e3696db2146430c540a3ebfa61f6cad28"),
        (246, 1752643329, "0.029", "505.13", "0xe2c94faff1877ecbd8d282fc2240c53df52bad0d091c2f5f2e17ebbd3ea7144e"),
        (247, 1752643673, "0.0299999712", "33.333332", "0x9438e9bdb7ffb6c2e7320d1a7b0d15323ed033792116da9844906eab940e6c7c"),
        (248, 1752644202, "0.0289999724", "34.482757", "0x4a29a00efeedb184515177319238ba5264f279bf1c1935b08355e94f10bd24e2"),
        (249, 1752645017, "0.028", "10", "0xe127b273674c713e812d440e4559ab7e9d658a0582211fed95823758ed89a173"),
        (250, 1752646705, "0.028", "10", "0x2e9d399392dd848c31c5a571286613cff97abd3c3eb13d6c2f717eca64962222"),
        (251, 1752648783, "0.023", "200", "0x7b7eb3a9283fe19dbcb1db06ca0f02c5d386b0ddd2dd8bde65f2ef9c5d66873b"),
        (252, 1752650303, "0.02", "18.46", "0xceef0afb0791d0c26cffeea0e85cab4cf072e14c7de7d135a3a5a9ae4a093dcd"),
        (253, 1752650919, "0.0191638798", "183", "0xb16a14c215552b0d07fe147919f56c895641fe9541e38768e7ea11b2e629279c"),
        (254, 1752650971, "0.019", "9.99", "0xb4cf97706816840123f4ca94ce30dac8aee52a1e3dc1d027e9088a23216b8a6c"),
        (255, 1752651117, "0.019", "74.19", "0x8ec52f04860de736f6b61f905dcf8f9a36b3cbbf12cba336995fb04b5a7520ba"),
        (256, 1752652899, "0.019", "5", "0x9b4255ff0d2df1ed18e48dae1f735a828324d43ce125434a41e3f23ca91ba8fb"),
        (257, 1752652907, "0.018", "50", "0x53c5aa366042c130196dac86c227cf5bbe5222f51f296182fc1d269a4a64fb97"),
        (258, 1752652913, "0.0208112346", "1026.83", "0x44d758d11f767a05179b6162e14953a51686ddf95ade2675b8f6c73717d3ed6a"),
        (259, 1752653027, "0.0348213958", "28.717947", "0x5992aac52d60f8a6fb7e5d57d2372ac938c2b94fbdc46ae4094223524f91d089"),
        (260, 1752653051, "0.0398714961", "250.805713", "0x4b71971dd3197e38163ac37bc458ac733b7253e0937896b0b5d3a25899ebf6d7"),
        (261, 1752659199, "0.0307539685", "162.580644", "0x9a69a5ff40057fa5b73b8bbc8f65a20ea2ad7f9150528c95c6ad4725eeedca54"),
        (262, 1752659301, "0.028625", "80", "0x0ca0da0c808ab0cc6f71bcaf96629d81c1f1822b96a1a02a8820db44d2e95ef8"),
        (263, 1752661576, "0.0321100815", "93.42857", "0x680a4d1e432337acc222b2da833f38e7da598a9472be03d2fa23f4c01e5a0630"),
        (264, 1752666065, "0.0295", "100", "0x04a4d6fc1a515a71dc33d186f6c110f6c844b5a829c348c7634c74f9a0fcc00e"),
        (265, 1752666297, "0.03045", "100", "0xa4f73ea5ad81a704acdcdb8ae49dad9e47aca5838901627fa52b3ceb12ce8de2"),
        (266, 1752676414, "0.03", "1320", "0x30aed0b3e254d3f3c06bdcea580c1d27463e963b4fa750ad8f77048d133b36ec"),
        (267, 1752679832, "0.0319148906", "313.333332", "0x5e8c09422a3f99eb82193c6606ef238073664d9b19962656e72f1f3acdc2817c"),
        (268, 1752681264, "0.024", "76", "0x4604fed04526a94af059bfa3ba85b9a38271039eae0401b7ce59586bb4915ace"),
        (269, 1752682406, "0.025", "2990", "0xeec95c54087c9f819d73b420abaf96a1118955eec6f5755c9d97ed6377ad8937"),
        (270, 1752682662, "0.0331186597", "60.388887", "0x3a3ae036a1fead3a4e01ed8e12bcae7e8336bda8f20a708b5c6758fbb4a62457"),
        (271, 1752683394, "0.0339152039", "117.941175", "0x9acd4a54ba2d4f031b4efdcae921f0dea9404abceceed9eda3463a5706296fe2"),
        (272, 1752685656, "0.034", "588.235294", "0x1f0d4e709f7934a36c984ceef88142c6ac405a369bbf888b6ed32f8517ccff47"),
        (273, 1752686752, "0.0339321358", "147.352941", "0x6abe27fce7c07463ad00d27050eefba60d5cad83e0c6742577312e23f9698721"),
        (274, 1752690608, "0.0376473694", "3984.342104", "0x28ddbb6ab0e8bd2db662d231525212eee7dbe3bd6806ea4faad7845363c25bbe"),
        (275, 1752692078, "0.024", "9", "0x109e66b48e05d4104364821209bb210d16ba7adb106076af62fb6f410948236f"),
        (276, 1752692078, "0.024", "41", "0x98c0c0eb77c12623c2e2c356eeb192bfffb937426a3168651b0b5500bc4b872f"),
        (277, 1752693790, "0.023", "76", "0x7969f5784bb308a1190894fcf25c308f052cf11f4addec63ed1218e6a12c049d"),
        (278, 1752693974, "0.024", "105", "0x5ba1200b3cd2f81eb3e22609422aa88cfa91850615623fb9037f15e934f5106c"),
        (279, 1752696930, "0.0331161122", "169.705881", "0x2573613e579bb3fbf50335ebf947d6a4d54dea1566d44aa7b1de0bbea64fe639"),
        (280, 1752700464, "0.001", "803", "0x5d5cdb6bff49b4c56dd1620b7d05e8aff7b5137a6bf17ef7fd87e9786e33ec30"),
        (281, 1752700470, "0.001", "10", "0xaeb441b6b41a7e3b13c20441648d1ca5656bf92a4115dac0e794889f9415b6f9"),
        (282, 1752700770, "0.002", "600", "0x6bedc9601b05feca6cd7a8324b24e49b9056d158492458efe85b019ac79ca4dc"),
        (283, 1752702268, "0.001", "679.99", "0xdf57e82ca12fbc0374feb5a956df668c981bbc55c7f9b691097173ba04ee2efd"),
        (284, 1752702546, "0.0016666667", "600", "0x3ce805f434ab260fbdb494e2aee529d0f3a898f89322ed13938ad6a6535ccda6"),
        (285, 1752703128, "0.001", "26.23", "0xf1677e250ed070ce50d188e74f59057d839a41be05fa1f78d917c28b4df2b8d8"),
        (286, 1752703858, "0.001", "157.23", "0xfc964fc6ab6df034b396a990dbf2a3a6254d374ce6a8dea44f73fc81f0069405"),
    ]

    fileprivate static let retained563322No: [RetainedTrade] = [
        (0, 1752509648, "0.86", "500", "0x06edebc54788fb643ee67d2bc9a7c329d32396c4c50e8186b24942ad6dc053e6"),
        (1, 1752516056, "0.88", "10", "0xdbf86dfc4904452bf75cbe236064027d88353ac39ff86d8467103bc569c7cadb"),
        (2, 1752531497, "0.87", "105", "0x3c4fafefd1d2cf5cb1846ad3f2f90e5fbd3042bd762b665aef715c6a77b9cfe6"),
        (3, 1752531593, "0.87", "70", "0x4a6bbdb83e3f48ffd3cde7a0a4fd468c1e407962461625c03f20bfd423116b99"),
        (4, 1752531595, "0.87", "45.54", "0x130b575d9bac0504650ff4792514b6e475e1df5a385b8ab94f284f4353df8887"),
        (5, 1752543221, "0.88", "13.37", "0x3cd39de41b6fab9b8ac8587f720a50808d79a2a77a74e772a0d987f9bbab5f73"),
        (6, 1752543221, "0.88", "10", "0x4490fc968ed31debbdc44e035d299fc73d19621f8c338caec753c45666a8611f"),
        (7, 1752545815, "0.87", "10", "0x8ec1cfdd1caa1e0ec93fbdcf27ff959ab2b4073c5c09c89310cee10c5574e45e"),
        (8, 1752545829, "0.88", "16.67", "0x61b86832cb6e5ba87bec693d889eac3e7316f847ad4f86aa9a6879f143c6b662"),
        (9, 1752548828, "0.88", "370", "0xea4e1a469a4336e33c4620c1d1073102ad0c4671382ef821133daad7b2e0273f"),
        (10, 1752548830, "0.88", "330", "0x87a3084780400754a1533a875634697617d84c152741a9cb86f252cf50208648"),
        (11, 1752548832, "0.88", "20", "0x58b52d77c510c86447cabf14f21924c3584af6c7d01ac1272622acb169608fb0"),
        (12, 1752548834, "0.88", "20", "0x5a2f86db9a24ad2c65216d9d63e5ed0a457efcc203fd598431bd7338c1d9455c"),
        (13, 1752552353, "0.88", "868.32", "0x1ecda0db6a767adcbd6378e8d0562d9446484d28de9c7ce23967d70796180745"),
        (14, 1752552353, "0.88", "2220", "0x5e5beff9e16db2ded57679a9a9d64f2831c37dbb643f571a30036df6e7f9e619"),
        (15, 1752552377, "0.87", "21.99", "0xbd8dd593f5ca81a4e76fc1197a6720de64354d5fcc5f327d177dcc35ced0467d"),
        (16, 1752552399, "0.87", "25", "0xe69cae42d393b561c5bd96f756db54c5baf9d531a8011af86ff94042c9ca2c85"),
        (17, 1752552431, "0.88", "9", "0x23cda96530449e91e0170acbe611ee123f5513dc04727865f123d25b80804a66"),
        (18, 1752552433, "0.88", "8", "0x82dc02941f48f27d5b334db721e3732c8ba542cd4d17c945e265ea6b90a1dbfc"),
        (19, 1752555149, "0.88", "37", "0x800d2dc3eca90cb64d1b4122dae9ce08eed023581dcff9ab98afbd44bae49eae"),
        (20, 1752555149, "0.88", "30", "0xa27fc61a8796583344313a589c02e7d510276d6ebe437430ae1040bb4483e068"),
        (21, 1752559303, "0.88", "66", "0xe3739676840f470fe96940cb54b091d07aa09b9857de6ab2b2c149cb937bd8e0"),
        (22, 1752559647, "0.88", "100", "0x4adad1d761decadc4422c7b1d53df11a076d98efa6db177c9b2e75a45f4a9561"),
        (23, 1752566345, "0.88", "9.21", "0x7309750505259197892f93352c2e4c92990eef157f410fa5d391ed2dd607b046"),
        (24, 1752566381, "0.88", "39.99", "0x62024805ec839392adaa56bb241b176d0628acbc9db7632235b48c8cabe05742"),
        (25, 1752566381, "0.88", "66", "0xa3fa17ca84dae75113482e1258b93c325a889c47fe84abe3ca8940bb7b183dbd"),
        (26, 1752566381, "0.88", "30", "0xbb368b4f47b3b40851252a47afe381d8f12a0a0659631fefa4643b7a282ce67f"),
        (27, 1752566658, "0.88", "6.25", "0x2aab992d975aaf3f592f4e7b268ea758d17e0fc9939f5a384ec2fbdf34bad726"),
        (28, 1752566660, "0.88", "6.25", "0x21e144a0d35016f9215fb89cdcfe5a32cd322622091bba8d86d517101e2781e5"),
        (29, 1752566702, "0.88", "24.99", "0xc02207266bcf242e6148b4aadc63369142887b1ee36edde43c9d7b1f626518b7"),
        (30, 1752566730, "0.88", "18.05", "0xc7d62999df3f3133c9e09c4c5c4c5f1b95ca2c329fc74f40324b2a8bf080779b"),
        (31, 1752566734, "0.88", "6.25", "0xa07487d7499ce96a0ac87d775125ec4b020b4b1745decc12745461d7b8339169"),
        (32, 1752566734, "0.88", "25", "0xfe8053023c92fb1354e27f5e2d6c12c30513a0c0b29c2e24e37882bd57e4351d"),
        (33, 1752566814, "0.88", "39.99", "0x65c8ec62b69cb77d72b826dc2da75feaf8cfd897d05bb0db96009b7525dfeaac"),
        (34, 1752566816, "0.88", "102.22", "0x79e75609fb41d1b6becb083b5e2bd1759b29d4b15353e6029a6c185daca92609"),
        (35, 1752566820, "0.88", "5.01", "0x3b55256781c69778a5abb634333e54bb2b2ddddbc368697ec4ebbfb308792173"),
        (36, 1752566822, "0.88", "5.56", "0x351274572bce8ee427f6d249989ab465d3fb627d790c17b492f5688c8badc0b1"),
        (37, 1752566824, "0.88", "5.56", "0xe41d79b569eca45f1687d1c233f8d9181ff6ae280a7395c4f8a263c23b1d5b23"),
        (38, 1752566848, "0.88", "5.56", "0x030cba30ab15f8846c297fa4629b55a18613f20d3e1b6752d9d8eba70527b88b"),
        (39, 1752566856, "0.87", "27", "0x102714107d336e215ab9c69aa67b2adca295d6cd0f6277e3082793775b694c82"),
        (40, 1752567078, "0.87", "31.25", "0x21adb86b428026b56f6d1cb70e82795a88c6817b4ab32e5077cd1304bfee6c44"),
        (41, 1752567935, "0.88", "70", "0x9ea66d728370180adc9eb3021fd1ffe8e2aaf71f3c444cd0bc763acf5a56cfac"),
        (42, 1752567961, "0.88", "15.28", "0xc6ad54429777234240df79b4878e564b3a47b6a72010c0b93e5c5cdad80b6746"),
        (43, 1752567961, "0.88", "66", "0xd6392e2356024801a73e05f2312dfd6ea8f5d98b6b5032c0bfb6ab338d6db066"),
        (44, 1752568194, "0.88", "23.8", "0x948ff46b83c68fb5b2542ffb2f3af3e6b34178a1fc268c7df62a697d6ebcc36f"),
        (45, 1752568202, "0.88", "11.12", "0x9d981c7422e1409fb67d0183bade948c254f7924b685953282241d87088c4fe8"),
        (46, 1752568512, "0.88", "510", "0x0af25b0ada8f49e50d1f372a3c2f0d2f161504ea9b8b8d7ddb4ab94fe96a93b9"),
        (47, 1752568576, "0.88", "30", "0xa51da299e68ccf7bba5a218ffa3b27ea1a1b6e80aaaf37c9ff13f608980a2197"),
        (48, 1752569695, "0.88", "6.66", "0xe24a5fd52883fda4414ed6d65aee794b9e0329cc8f3f718979bb25d71e0b148e"),
        (49, 1752569775, "0.88", "66", "0x0801e3ae9ff4b8eed6541245666111b63c592738fae80eeecf0bed446a5b9824"),
        (50, 1752569779, "0.88", "14.29", "0xaaa1b31d177ea2eb0ff95fd9cd85683075934bf92edcb17af4165932eb8b6d68"),
        (51, 1752569791, "0.88", "190", "0x80a24eafd7ea85fd900b0faea7d4c1956160d7d9944d9aecb79d28d477628c75"),
        (52, 1752569813, "0.88", "13.34", "0x785224d6a163ed98958aeb7fda68a5cfaadd27efb0fc0331a460a601748982d3"),
        (53, 1752569813, "0.88", "5.56", "0x8eb747e4611e4f3fac54cc8dc2249e4622e991554f6114bb815fdeff69cd9940"),
        (54, 1752569817, "0.88", "5.56", "0x5bf14948bc8dd43b2f9d084327ef18a862201b6509493c81375c8072eddb8379"),
        (55, 1752570169, "0.88", "15", "0x05f6294af54355048de6d5db2c5ddd3ad84f4dac7a168233913ea7c19edd7c9e"),
        (56, 1752570169, "0.88", "66", "0x5d9ffb79e8ef5a3e429dcbb52a3f78ea5facc14d690ab9b5204eaabf57bf9dd3"),
        (57, 1752570169, "0.88", "173.19", "0x69e1d8e5d62a660fcf318ff249297fb83ffddbb7ae0fa073c02cef4af395d9c9"),
        (58, 1752570169, "0.88", "15", "0x6be734293452bc1bcfe55f53ba318120ef41c8d1b77b16a61bac5f2104e9317d"),
        (59, 1752570169, "0.88", "170", "0x6d2353c517d51d45ffa9aaed3f0f4178912441ccfc35e6700409b1abe667a952"),
        (60, 1752570171, "0.88", "5.56", "0x2e5df07f60ce2977dd7cdf40713a2ead180cb0316f55ca25fd711f6d3e279f6f"),
        (61, 1752570171, "0.88", "5.56", "0x5d323e743d00f71cc91ed2a08a004fe39f62a430613edb18bc6f1076cfc9856f"),
        (62, 1752570173, "0.88", "16.67", "0xa4ddc5dbe8a5cb3b10a9d167691e58c479ab39b35538019adb2ff46ebd512d23"),
        (63, 1752570173, "0.88", "16.67", "0xcca0d88361e298ad4a7ab99d4fae842b35f3de8d7d6fccab39b1eeb64e8c3afa"),
        (64, 1752570175, "0.88", "5.55", "0x4d053f2bffcd7679549ac3ea8f10d20e5273f514c6c6b0c1e65fa0b3f6aa22c5"),
        (65, 1752570175, "0.88", "5.56", "0xf36a746d95c5ba7cb727e02d15f10d3d0b0e1fe2c172ce4e0b6449e826dec405"),
        (66, 1752570177, "0.88", "16.66", "0x47e6fb967f7f72d1d12065176b6868c018a2c174bf6b49fde7cfa6cb03281b30"),
        (67, 1752570179, "0.88", "5.57", "0x597335b5346117a512ae591dda054d4a3f0912210042dfd707033599c47b098a"),
        (68, 1752570181, "0.88", "5.55", "0x7ce1f55e6ef96b31e2dcdeb63ac25b768eb06b0a7a55cbaaa391419cb260d341"),
        (69, 1752570183, "0.88", "5.57", "0xe8bdfd116e6849ddc78db5b65d7f3df97f3aac3f26266991008346de73689416"),
        (70, 1752570205, "0.88", "15", "0x18669e9b5b610b058b5caac08453037463aa511a8aa5f9defc180bc99c424598"),
        (71, 1752570205, "0.88", "15", "0x5b4ebd203b91a0e6cf52c8dedd5ef1d2f4bd23baa9af30aa3d1c9e043a3205df"),
        (72, 1752570205, "0.88", "150", "0x7811ac41b9a4a6fbbe2b5d0bb30c6b60ec7e16bfb59f893facb51040b1c0b3a9"),
        (73, 1752570205, "0.88", "300", "0xf6ac04acbd6703dfa72bc19c40515a780754f74d6dfb9bfa48f5916e1e597a8d"),
        (74, 1752570211, "0.88", "13.34", "0x2fa4b6871ea5ce6340b1ca144a54ec435d1ae56ed1d08a4b24783cdda87e702d"),
        (75, 1752570327, "0.88", "10", "0x71eb787a82c332d20f9d0fee1690e29055147c8636ce769b5712f383bda37658"),
        (76, 1752570327, "0.88", "66", "0x9b8eea98590801860bc16f39c9068f2090fe683839f92ba0d0bacb02ae5a248f"),
        (77, 1752570571, "0.88", "66", "0x207608954b82786677efbc662cda8b858a6c2da18f5d0626c8f47429f9f63aae"),
        (78, 1752570571, "0.88", "133.28", "0x79fe907b0dec99fb40d5122b70675b2ab69976f2c78253484a9871132d3edfb1"),
        (79, 1752570643, "0.88", "1000", "0x2cfe69b00d59a241831ae3c76e6b26434016c635f2872eed6bfd8b05fa969a5e"),
        (80, 1752570643, "0.88", "39.99", "0x7b9239545fc2ca230e94471bdab4aeacf7662793263bccaa43afb6f38667ad2f"),
        (81, 1752570647, "0.88", "14.29", "0x6f804e692e00d933aea6e23b26ca0ac35609cf20f969000d032aaff8af9ff22a"),
        (82, 1752570647, "0.88", "14.29", "0xce9d4a92848b38b34511b92744316dd55c30eddbeb515718a8a1d547d29084e2"),
        (83, 1752570649, "0.88", "14.29", "0x5cc5aa6172eda5c1b54dd1c143442d33c043f2b5c436ae44b17f4c52ed7918a5"),
        (84, 1752570653, "0.88", "20", "0xf497ee2d08e97bf7b37cf5f7ba74f9ca7f1c2ead0d7d323f3b2aed7dbe4df70f"),
        (85, 1752570827, "0.88", "329.94", "0x52ce6cad40bf95843312452c81b3726d347c38ab0895487cf99b6614fdbedc6b"),
        (86, 1752570827, "0.88", "39.99", "0x950dd7e2eaa640dfa8a0f8c0dba22d6069c793d5fecdc9d184175c6f65200189"),
        (87, 1752570827, "0.88", "66", "0xfd91334da315765990bbec47c0914064c1aaf021943205e0c81b95da897f90cb"),
        (88, 1752570829, "0.88", "5.57", "0x42928a14ddeeba55318278ad3f9bd58c5bd3d90b96a0b2a3eff05f2d2f132eae"),
        (89, 1752570829, "0.88", "452.13", "0x6714d972f84cf9dc88f5e607ae9317d34c18c07340f3147712af00b4c4853492"),
        (90, 1752570835, "0.88", "37.03", "0x207fdd9950cd71e39059be3831d1248f1ccf0b3b0f25e424a99eb1c28a301b8c"),
        (91, 1752570843, "0.88", "4.15", "0x12d665f4dc0d48d101f5aa1003ccf306e3b6323dede304e2a079c302be52eec8"),
        (92, 1752570845, "0.88", "5.55", "0xb490a50f8095728fe811d110d9f3332bfa1a47d8b831b72559823553c90ba529"),
        (93, 1752570851, "0.88", "1.1", "0xcba08810f8d9495936f2e0f4fb93ee66fcb1d6057271c7c09e10fddc306127cd"),
        (94, 1752570855, "0.88", "6.69", "0xa78d0b67d617696d3fa5d0aebe1f9e9d6c7c427d8a61f8ff8630d66b899f5cca"),
        (95, 1752570861, "0.88", "95.51", "0x6590836fc03015ecc09b889fba57c365130003fc6517458b50699ba2b1f3cec5"),
        (96, 1752570865, "0.88", "16.67", "0x96661de782050c4d3b188bc12c46f8aafba4010aa7158a6e37becf9e9d08ad4d"),
        (97, 1752570869, "0.88", "244.7", "0x812e7c6e0da167756f6477c9c44728ac88f9394a4d7913c2c1ba1116b99baf10"),
        (98, 1752570869, "0.88", "5.56", "0x8984a6c4561574c2a90d7da0cf152d863308be899bd1cf17afe49bac995ee37e"),
        (99, 1752570871, "0.88", "5.56", "0x1b7dc01524558c37bce62bd61f23f7ca7524e7a225a661a7804735995406a640"),
        (100, 1752570871, "0.88", "5.56", "0xc689ce02152ef42ab2cdb5074fa2f2a2a7c68dc08112c7ab755025b4c064f946"),
        (101, 1752570885, "0.88", "27.46", "0x6e898756a77692ff4f961fd8402ea7884913b550f303a622ea929010b4e962c9"),
        (102, 1752570885, "0.88", "5.56", "0x7d71219c5facfcaf7d7820f54429173d1e2e9b86125d04640fca9c6201691b52"),
        (103, 1752570885, "0.88", "16.67", "0x8046e104b12047dd08599a62a2501842a07f86206d1cdc32c0158c6ac11b9795"),
        (104, 1752570885, "0.88", "5.56", "0xb264a0670832b8cea28bf5ccc2a51e10084f5b9019a86d356e535a68379668be"),
        (105, 1752570885, "0.88", "16.67", "0xed2189942d11b56d2bdbadefd1f3c79bab125cc7abea801253e8ee465240830e"),
        (106, 1752570889, "0.88", "28.44", "0xa4be35984da909b5f5b12c8924c6f68ac8a5c6ed844d3cf72f6bf0796547fd8c"),
        (107, 1752570891, "0.88", "39.99", "0x4ed1c270de00689023c22297a341bfa9593433dbffdc5923f0115ef8386fee7b"),
        (108, 1752570891, "0.88", "5.56", "0xa3b95e5c07e314b561284256d3cc6175c4e25c4fbf53c8111a07a7904a51ce5d"),
        (109, 1752570893, "0.88", "3.19", "0x299cdf0f356e32c400750d32effe7e4c1f6297036cb983228f295eec7b0b1962"),
        (110, 1752570893, "0.88", "5.56", "0x5858f8001259b712f3416b41c86f53fd7265446cedca8365aa12ae95936379aa"),
        (111, 1752570893, "0.88", "5.56", "0xd5483ef6fcce71c492c71038b374e48508789486f9f67ce1d56b79dc35eb35b8"),
        (112, 1752570895, "0.88", "5.56", "0x17706087a20176f4f835dd5303640fd609c781e96b46ba22c08f2546a3128da5"),
        (113, 1752570895, "0.88", "15.98", "0xc615e90de359c8c205a01f9f7f2cc66552f7985a7c4fe51947f23407cb14f000"),
        (114, 1752570897, "0.88", "5.56", "0x1912c9e53e9f17b41b7aad2c7f7e7e95ff3f5defa7401a224cd9451d38bcfec2"),
        (115, 1752570901, "0.88", "62.48", "0x96e9d320572b766e7df670235cabf1083260130b0ed0f7157ade44144de5afaa"),
        (116, 1752570909, "0.88", "242.29", "0x95c1694e364fe67c6b4c8abb92cbf673fab3ad5aa5c8ccf0910f7e40aa2fe72c"),
        (117, 1752570917, "0.88", "60.34", "0xf657c15e22dbe93b775203732495fc046c388a4013dddadc52e6babc01d599f3"),
        (118, 1752570925, "0.88", "6.77", "0xbc514451ee5d24a042b836ab2f427e9359ff281600de258d2c01d6741cd51394"),
        (119, 1752570933, "0.88", "271.67", "0xb8743a9b11d96cf355d6a2aa0e0c23733b2148de90f3699d8dbae5a037e43244"),
        (120, 1752570939, "0.88", "84.12", "0x0e3e9a533e11d1bf219d7935c14ec605d38820bc7ec41179660cd9683d82c5dd"),
        (121, 1752570949, "0.88", "15.46", "0xbcd138e723ffbb97d40754ef014af2d378fb24b349d560f6e1be6005bae96e8e"),
        (122, 1752570953, "0.88", "39.99", "0x42e2cc704947a628eb8e0c4d871103ab1f54555d48e821fad872f175678d8857"),
        (123, 1752570955, "0.88", "1.74", "0x90424d010d00245361262daeda7bef317676ef5172d9bfbbd5f4235f0e26d636"),
        (124, 1752570965, "0.88", "242.52", "0xc526ff50c8a7ce16be4e3426bc3cc942b5322f32143da81be3e2667dd57d8ae6"),
        (125, 1752570971, "0.88", "5", "0x8008fbb4aafcee92764cd8ef2f27bac40f9954010968c0c17b6343342673dec3"),
        (126, 1752570977, "0.88", "6.66", "0xb13c3b77e60efa6e1ab8be5f3907e32e34b3977cfffcd76f47072a0f778bea59"),
        (127, 1752570983, "0.88", "110.73", "0x6110bf428c40b82746fa715ba8dc54ce91c4f5f2eb03d7f9c69e3ec5716362f6"),
        (128, 1752570985, "0.88", "10.02", "0x71df01dc296f149a4d43c71e8cc9400c397c7a196aca0521afcfa6a25768b046"),
        (129, 1752570989, "0.88", "112.27", "0x3c3c86e50a79136468e31f830be586a51b1e91d8620efd7e65207aa50b06a644"),
        (130, 1752570997, "0.88", "14.41", "0xbcfeb46c154403545a28a421cfd7e20176e52f7d65f5c38488e890abd3385b6a"),
        (131, 1752570997, "0.88", "661", "0xef1f9e277d21200c1ee4b8b4a3b7c71fab61fb4baf7df59c7cb86183b9e7f25d"),
        (132, 1752570997, "0.88", "190", "0xf1865c30d2910bcb86a8f758df9c632eb7a2326a52ae1b12a5c431ae7aefa29c"),
        (133, 1752571017, "0.88", "15.55", "0xbb0b5666a1db65172063d108e4a9b1663f2b57c245ac87cf6beea83966f3ad63"),
        (134, 1752571159, "0.88", "250", "0x1228cd29b435590ee80073d91a95101257170e16b2248cb35f34e07b5d6210f6"),
        (135, 1752571159, "0.88", "66", "0x5e76105b13ad60bda684addfc6326ad0478f5b895b757ebeb868220ee0d59656"),
        (136, 1752571159, "0.88", "253.36", "0xf3900b5dd28849a2607c60364248e5e3ba385db9c68d74062aa2bd92cf852a7e"),
        (137, 1752571297, "0.86", "40", "0x7091afb917b25cb6cddaaec1ac1a1c46b3e75044872978e3c38f06b5b4f3f877"),
        (138, 1752571305, "0.86", "5.56", "0x8603333c523f732b4ea0bf90345ef257920e05419b03720862b51a08ecb9cb9b"),
        (139, 1752571305, "0.86", "1.14", "0xabe0fbe3611348dbe1d9ddbdd52a88490684a47eba5e6cea2068288e8ade23ff"),
        (140, 1752571305, "0.86", "5.56", "0xca1d777cb410d6ddc6ff7b27e61fe3d001a64b8dd842ff7c0e27fff289712199"),
        (141, 1752571437, "0.86", "13.34", "0x5c09498dfa546d58296634b7e92c041ad04f24e43eaeb14db71fcb1ad6126751"),
        (142, 1752571441, "0.86", "1.14", "0xbd1f0e0bba74bde54bb82e9ffef1f15a81236dab49e9bbf80748abb6a2325ed7"),
        (143, 1752571443, "0.86", "5.56", "0x34c9ef2d3b14a11dce969d258b49ab18c729c464b26e1308e3a28b53dc847afe"),
        (144, 1752571571, "0.86", "137.7", "0x2a4ac6f38eac7370d95ff40e55dfa2af88ac40bf4dcd9b471d05fe97c12592b0"),
        (145, 1752578841, "0.87", "50", "0xa0b8091bc79789f929bd69bbf4e051bbc8e1ffd2cbae178c6edf9e48be52667c"),
        (146, 1752579317, "0.87", "17.99", "0x8f4f1a00463acd9b1bd6b39203fc68db77cd6f2a8246e4a47f078bb047d8fbbb"),
        (147, 1752582529, "0.87", "20", "0xe7ea28f26f3e876a2c51c24e1a2d9e4cc85b8147a241768734f055f788c4fa5e"),
        (148, 1752587579, "0.87", "1100", "0xbd529e9d71a1e88c06f2b08cbb59579fd7f37bbf351eca2c629ff067194979f2"),
        (149, 1752591253, "0.87", "20", "0x2b63aa97858f4a1fe2d4a7994cb7bc528262ee513f129a4cf8dd4ac90dea7cc1"),
        (150, 1752591255, "0.87", "66", "0x1575928cebfe1431821bbdf687d3b05b73aab0414cbb38f6d858d5bafa367ee6"),
        (151, 1752591263, "0.87", "26.08", "0x3720bf5d346e0a072b13a8690131bd8aed147521030d909e2bc13cc84ae516cd"),
        (152, 1752598682, "0.87", "200", "0x0b6934ff4f5f563f780c2368612137b8a91178719e30d14af59020b691a48a0b"),
        (153, 1752598682, "0.87", "15", "0x639b56a72fb82c84dd4d6796105c74d0f7cff00f653da9afdfe698f4fd459b89"),
        (154, 1752598682, "0.87", "15", "0x77826522aa0d5692183502e827497a28295c2cf6039e02d400f92248351f6012"),
        (155, 1752598740, "0.87", "125", "0xf90dfc718f78666a04eccf27d064ac3995727c9a5d8eab5e5d28169f00469674"),
        (156, 1752598898, "0.87", "5.56", "0x078c0b5ace2185c7b2620694862c281ca17ad3ce6b99ae70959c415b58f3045c"),
        (157, 1752598898, "0.87", "38.5", "0x0fa28969da1368f612d72a2b9ab16b944d692627f1e34ced500832fd384d549f"),
        (158, 1752598910, "0.87", "119.44", "0x57b0c372041bfbd7992c48134f1444aadf1a76913fdff8491d4139127bdf3511"),
        (159, 1752599261, "0.87", "29.99", "0xf0e52293b1eff8fc64c1df05f0a02373915cf5e10cf4e94831b58d0ca750315c"),
        (160, 1752599263, "0.8699999871", "7.73563", "0x88ccb11308ff0b5fea13bd0368d587de33f2f7f36e45ded62b983ba5893e68a9"),
        (161, 1752600801, "0.87", "20", "0xe0c09841d883ed4f9bdb0778920992a418791a42e63be4a93300df08ce729d42"),
        (162, 1752601815, "0.86", "10", "0x4b99ceaf271337a35989fc04a8998d5984d0d733a4bbdba18d1650aa6a3c5609"),
        (163, 1752601819, "0.86", "1.14", "0x0dfc7bc7360ef1b5f7769beafa1db6e3188a739b97eed2e92efab9fc962eabfd"),
        (164, 1752603429, "0.86", "80", "0x6acd629614f73ca4773eca73a6bdff8ab37b6854f25304ad9be7002a7023581a"),
        (165, 1752603433, "0.86", "1.14", "0x94b7b18f3f0873b013a7579a29c204bfff6ddc3dff272cda568202a30943b5cc"),
        (166, 1752603501, "0.8694326633", "597", "0x4b9c786506ea8f68a4c89787a1ff0ed7052ee1f1e73290e4a0b5dab2ba0281dc"),
        (167, 1752603535, "0.87", "30", "0xc7b75f3b0e94880bf9d2beb7f36cccc2f9bc6ba06d0711f5db28af005109918d"),
        (168, 1752603543, "0.87", "33", "0x6e29723814429c6d4c535d0e64977c472a5fd03a57fadc91c35a9967761a18ef"),
        (169, 1752603543, "0.87", "20", "0xca54c2065b19dd9ecb2db5b01ff1fe64d4b81460546cb4a72da2b8af982fe486"),
        (170, 1752605434, "0.87", "111.05", "0xccf0f0c81b31704ad30d6a189fa0590fd68deee178651dff01313aef291d4cba"),
        (171, 1752605694, "0.87", "40", "0xd4daee9ab507d4db9554e9f7ae551d86e90903cf09f67c54b4bdd9a999d843a6"),
        (172, 1752605920, "0.87", "270", "0x794d433b4b6ea9d8ef1881a8a8426825af2248c57b20ba22a7699058716f9876"),
        (173, 1752606524, "0.88", "40", "0x0bc218391bc1213fe6c4c9fc4226e62a9dd43f6f7b80e99f528b11d5e772aeac"),
        (174, 1752606972, "0.88", "51", "0xb138d3f9b88722b2aa092e8fd959246ee58d09a3c95878e9fcbd069196a7b372"),
        (175, 1752607258, "0.88", "200", "0x1893aef11ab3931f263787b9ac03bd6f4c7a4d909b1a0b9d97a8d50cda4f2ff7"),
        (176, 1752607258, "0.88", "200", "0x64c5708e2b0a666a3fd0b1b6481e87ee21f7c4d66746681019a1cb3f39931fec"),
        (177, 1752607258, "0.88", "40", "0xfb7fef36143efc57be1027f700b3516ee2a897da9e7d3e8de32dcc569e2e4077"),
        (178, 1752607340, "0.88", "40", "0xdeb047752c0c900b8fed4f7e23d169e5d761342026877d3c7c26c49916f76d20"),
        (179, 1752607340, "0.88", "490", "0xe48c9ceb1ff72c8b2fcf4bcaf66961fde7644536883f3eea6481f4f22cd394f8"),
        (180, 1752607428, "0.88", "40", "0x22d10c3c34acd0773cf82ec4e934261dc3b321498e75ca355f4522448be46755"),
        (181, 1752607428, "0.88", "1600", "0xad44d5dde7f14e0a803f3eac014f85654ea5c8fcc4173572544e117cac3b169e"),
        (182, 1752607556, "0.87", "160", "0x2576c5747b5a054ac7c301160b6735252cd8094ba4d8498db64c9197f9642816"),
        (183, 1752607556, "0.87", "39.99", "0xbe7f7f1c3aeb2f6fe7925eb47e33bc95129c7fd34ddeddd77de8955bbca2ee3e"),
        (184, 1752607556, "0.87", "167.24", "0xef1d673621fea7458f6030976ef19e1e1d78f45b8dc4a4c4aa42273e54b4e9f7"),
        (185, 1752607566, "0.87", "24", "0xe1f00588e70580db8058665b1cbd11243018a9b794b91104231195646c3d201c"),
        (186, 1752607570, "0.87", "40", "0xf6acce20cb1ddb3ee9e8d4ef0118b2ac2ba6dd55bf7a8f81bedc93e106f321e1"),
        (187, 1752607578, "0.87", "16", "0xdbd8c6e01ff358a33239b079bbd4f8110dcf50766bef75b628be3f4591275c8f"),
        (188, 1752607592, "0.87", "8.93", "0xc64e043da1af355a7e25d1b4da7b53fa8b0d97116a4de544b5d36092faa5d1da"),
        (189, 1752607600, "0.87", "31.07", "0x694c1d23dadc5a49112db83e97773b0535161e26067f338b961fa7161d5d54c5"),
        (190, 1752607634, "0.87", "10", "0xfb24b1536135e7708ba384841e4dbc1baf76bfb4bdf5379bbd49601d8f035ec9"),
        (191, 1752607638, "0.87", "14.29", "0x5be89d1230115f932074b907c12f9d7da5300ae5c1dd19fa6eba14f529711886"),
        (192, 1752607800, "0.87", "820", "0x14485d0030dd8e6db78330d83193390f0afaf2193de0c7357c250c5693cad32e"),
        (193, 1752607800, "0.87", "39.99", "0x2b3fde15e2d73c5120b32d771c2d8421dadc4d4bfe85f2e3531b4d66e65238e3"),
        (194, 1752607802, "0.87", "140.01", "0x67880d4ca807f7ecca0603fe1d223d5a19737975f228e71e6756942ba7eadf5b"),
        (195, 1752607990, "0.87", "160", "0xa7ba4d1b20ae43144684a4bbdc386b507b552d20650f0a44eed052162c7b5787"),
        (196, 1752608596, "0.87", "200", "0x3cee8e4fa5769536a311e71472bbe67e30d5065a284a9fc8a63f9e9dab55ceb3"),
        (197, 1752608596, "0.87", "40", "0x9eb3be49d05a26e44294bbf2d69ee94429a4490fbfe5ac4242737471f7d54aba"),
        (198, 1752608598, "0.87", "209.97", "0x26882da7d03ee193015936cc76e8e988a4240c8fbf08fdcb2db31331236f7eb8"),
        (199, 1752608600, "0.87", "16.67", "0xf03463ffa3998788b242fb25a0976a2e9ae5e963d1d1004e1ef3f16f8588e17d"),
        (200, 1752608602, "0.87", "16.66", "0x21b77c9dfed198d071809402ad3a6acde7ca958d7bca948ca533173eb9ca2189"),
        (201, 1752608602, "0.87", "16.67", "0x2250776aa02086f0112a995e3b0d260ca5c6d5e9f9981885c6fc325c5cbc4dbf"),
        (202, 1752608602, "0.87", "16.67", "0x9caf2b3db0c57e21d515b600a144ef558263de0a2237682beab266f1a415b8f6"),
        (203, 1752609072, "0.87", "599.91", "0xebafb45aa2af0cb20c3eaec95d4d6ff9d4c95521475b9635d8200fcc3095dfab"),
        (204, 1752609238, "0.87", "10", "0x9e8bb7b4aec815724dfa4784cd8dc6b4c26b8f540d1f6b7c08af3b340a8ec4ec"),
        (205, 1752609242, "0.87", "13.86", "0x7a4a4379ad9fb9d3f1747a45cb92ef30e68f3ac8f8804a8e7510cb833d2b90ce"),
        (206, 1752610776, "0.87", "346", "0x89499b85cca4a75f753c27fcf1555925874db9a2999b5df754d395fe8f8df149"),
        (207, 1752610958, "0.88", "20", "0x122f1ac9ec6d2a614605fef162df109773cfdecb91ba2aa034970c0404e7b1da"),
        (208, 1752612397, "0.88", "50", "0xf4521992479acc58fe220e4c58b1301ef7d77b3af46aa80c0217df57774df259"),
        (209, 1752612411, "0.88", "14.95", "0x97f3e5380feeaedb8330abf9b4fd670081ae7d2ce10c544de1efae643fe1e880"),
        (210, 1752614035, "0.86", "130.05", "0x9c1b8959e7d02256317a635ca6bf62f9c3dfe5c01397f3dce74630a7c57187ac"),
        (211, 1752614161, "0.89", "33", "0x8ab2ab304adc644f221d5fcd4e66033a72b959d0defcd934e3b522055bde1cf8"),
        (212, 1752614923, "0.89", "10", "0x2fa778ae049301b16bba4a1d7d99208508fbcb5dbeb6f4cd02aa3abdd5cae0f6"),
        (213, 1752614923, "0.89", "7", "0x42669ffb08a7c64b648aab1ab1149f831d75ac710e73cbcd925ecd493bbca802"),
        (214, 1752614925, "0.92", "5", "0xa3e3a76c08bff133d1c2737d8a4c14c329ed4c8516a7fa2be0933decb0880521"),
        (215, 1752617199, "0.92", "50", "0x99ce9d4f427592f0209e4e27538b528dcb3c89668cb9b3844f50b5e6c3c4d003"),
        (216, 1752622985, "0.9", "39.99", "0xa5049f3030cee10c0ef21fcb7fadd4d60c2fe42d0405b9ead0acded1b113c7de"),
        (217, 1752622987, "0.90825", "50", "0xe4d74a047a5d1be94f0023b40f6144f27fefe52e14ea8133b513e7715de8c5e4"),
        (218, 1752623395, "0.97", "50", "0x50e0cc316a185772c6c416db05a551138e1525736e543654eff3bde40591a258"),
        (219, 1752623517, "0.94", "50", "0xec06414f622e3e33dfc966ddcd8bdf0153215f57429904049a642281ecf7e4de"),
        (220, 1752623519, "0.94", "85.26", "0xff124a228a5ab42f34d5ab4c469e1a641ab3ff09400b7366c32125c3b2501e4b"),
        (221, 1752623749, "0.93", "10", "0xb8056ce8a6275292e6701c6be3bdb9717b7d82dd521d1fcf5c38adac8838b1ee"),
        (222, 1752623749, "0.93", "19", "0xd6b80b081ff6d0093833cb4066365f8da5d723b2ece980bf83c025a28b12bf25"),
        (223, 1752623827, "0.9299999997", "103.096771", "0x2db94c531c34c33ab76d66bc7afe3f8e29a0ec3dc744cf36bea6b8f654fbcede"),
        (224, 1752623827, "0.93", "15", "0x93bd0f52871c3f5bca6f78984d5c9759d8b12f9676ce79bac75cbdc848be3b9d"),
        (225, 1752623827, "0.9299999967", "15.161285", "0xd447402202295ecf970b897e4890ef9524b24e906add958ecb8267473f82c9a4"),
        (226, 1752623827, "0.9328547292", "100.76595", "0xd689ef946df2490594be9fe0f9b83c0983afa57ebee1c883d57c992e85e9dd5a"),
        (227, 1752623867, "0.93", "40", "0xb1f1d7b7c104d4012ca21fbc3cd4ba0d3b44bd8d05d7139b7112aa6e4b84a175"),
        (228, 1752623941, "0.9", "50", "0x32e9b87d6baab96fafa22576b154000f4f2c90f777ba10bad3d414c3eb370100"),
        (229, 1752623941, "0.9", "39.99", "0xdb6d76b8377761793559bee477955c763810787718ca620221fc7466ef1ea5a6"),
        (230, 1752623973, "0.9", "10", "0xdcd5d84e42771ab2a1833539303a55811056a3891901adcbc1daf2b990cdf8c1"),
        (231, 1752624021, "0.9", "8.74", "0x65b8b22463e666e5bc6c5ab0f1c08f7226b7d8170ddec31ccaa49ae927d6cdc9"),
        (232, 1752624043, "0.95", "10", "0x63beff24d09565de0f763a33989db7077ffd41c08bbc1ea115d211ec71a4489c"),
        (233, 1752624119, "0.9", "22.45", "0x2b24f8da8d12b79538bb3e08c4dfa02f614028ced579d62901104cfec9384664"),
        (234, 1752624119, "0.9", "20", "0x4b9769b3ab9c3f5aa62a77864380b0cd70d4e784863a217c73aadde6c0e00830"),
        (235, 1752624157, "0.89", "23", "0xc22f6d72fa19bbd1ac665fa133055653033bff7b4d22323c326fca1a862e000a"),
        (236, 1752624169, "0.9", "110", "0xf0f2583a4d962504347efed14d1416e23a669ccd1080112241fab518b0e37c07"),
        (237, 1752624185, "0.9", "20.99", "0x4b25e264c9910d9e05f1d9bee0139a477b7e46fcce060ab638cbac6dfe25049a"),
        (238, 1752624273, "0.94", "100", "0x7835c60867652f2007682d9577b2db332ec544b6fde90d8326962521cd9f4ff8"),
        (239, 1752624273, "0.94", "22.05", "0x9ce3f62eb418f77c2eae5fd08715d609e1b9d94773aec45349c242f6d57d1b2c"),
        (240, 1752624303, "0.91", "5", "0x7eef77cf1288e9c228c69142839c863d89343987da1e5d355255e2951f1a1955"),
        (241, 1752624329, "0.92", "110", "0x2c9fd8941c77df39644a9fd89d132c92e61e1ab14e4453c6e9bb38ea21f356d1"),
        (242, 1752624329, "0.92", "4.64", "0x76e6ad5217bd169339f15a538ddb283933099e0c4435d29352e7d4d8ed180eea"),
        (243, 1752624329, "0.93", "6.81", "0xac72d5c38ad3bc46d669fa4dd4a7bb98743f5551a8475a9c63be961d9b0845ee"),
        (244, 1752624513, "0.87", "5", "0x25fbdc8c5fb635ed9441ebe98ef18da0e664c956ffb513e23f31f9996d3f727d"),
        (245, 1752624937, "0.92", "100", "0xa45ebf49387973de0cdd97d4d82dea37dc41eb3a02d5589743d56c12d9b67b0a"),
        (246, 1752624961, "0.91", "11", "0x5e764e0d98a4eb338d7f216eef35c06db8e8253624f1b19de58e254bcf512e64"),
        (247, 1752624981, "0.92", "315.05", "0x6547d95ac099f7890a9f16002b9c82d242e6e64276ba1e53bd1c53754a8a809b"),
        (248, 1752624999, "0.92", "55", "0x2943982c0535b54296aab776129b83f3c6c40f26dd7a35a697106c58618c58d5"),
        (249, 1752625003, "0.93", "250", "0x87ba965ca7f11617036884f1f27b66e19363e806d0e393564f93baf8f8cff554"),
        (250, 1752625005, "0.95", "250", "0x890e5c9d71a2a0ad30a8eb5e67db424426ff3dc3fd6ab3e3c18a78902b796573"),
        (251, 1752625213, "0.9292891761", "619", "0xdcb97490e936ee14c0847377827dbcd442f7b8f0ab53a3e4f07f45fd6094d623"),
        (252, 1752626367, "0.92", "5.434775", "0xa3ea77ab57ea890cb37a0565e63d79dcddb327789184a57c6c4701f6cd52eed1"),
        (253, 1752626741, "0.93", "10", "0xa4e5579e120d2a929643107213879027b5d26952699e3549e5851883ee398c43"),
        (254, 1752626741, "0.93", "10", "0xe3ac7c5022a9bcda7358ee6108b5f2fddfbf38db99b5f387a4d5fa1c98fc52fe"),
        (255, 1752626741, "0.93", "9.99", "0xe78ae909229103f832df71a98e4cdc5aa2307fcb1c67cc4c6032395a116b8f58"),
        (256, 1752626741, "0.93", "10", "0xf3a7db1fa11edf4ef6b0dcd87b69901cf73e800b85447008a0af9d23ba210727"),
        (257, 1752626933, "0.93", "40", "0x0f153fdb620f8c37731a69e8f3406cd37351d03f3645b8631104b7a6a6d8038a"),
        (258, 1752627239, "0.931", "50", "0xa6270ca089056567ebb7606dcf410d8b9347f75bd671020b3dd1caf5ff3dd886"),
        (259, 1752627261, "0.94", "28.7234", "0x06ab40f037a03f60977cbc3dcd22dfd3d86dc1022f9ee7285d638667cff69a70"),
        (260, 1752627279, "0.94", "50", "0xdfa55b2874cebc0303dc0d058960e5fc0c23fbdf0f9f75051763ab66689be662"),
        (261, 1752627703, "0.96", "20", "0x3bd483a88506b26d4d755ebf76a028a14382719cf28f890d5f3739fe3482a9a3"),
        (262, 1752627703, "0.96", "8.34", "0x6203b1b87f3b28c2c90cb661d3eb6ac7fe2a6bc04574abc56de440de8e928c00"),
        (263, 1752627891, "0.96", "16.65", "0xad0d5ea06ed10ced263ba498b8f334806884a5697f103366ec5674a5014e913f"),
        (264, 1752628241, "0.98", "405", "0xc58fdd5b564b140f02ed5987574770f0ef64b5520183e468407dc9f59745799b"),
        (265, 1752628621, "0.98", "49", "0xef3395ed59e84dc00c1b227af24a86cc7c89ab252f0f417ae8fd7f93dc6e45be"),
        (266, 1752628625, "0.98", "50", "0x3d0a5b1a257d167ffdda0d2aed1cdbbbc2d4fea0a1a708e5dcdfb194231c2b48"),
        (267, 1752629107, "0.9899223", "10000", "0x382a4ab622ed06a9cb0a32afa6e4eaf0c2bbe2acfc7d06d3f9edcb20c9cc5ac0"),
        (268, 1752629377, "0.99", "5.0505", "0x71b216e27187de5535ac3ce0cfd64ef9380869bbef1a8d2bdad3a041721aeb26"),
        (269, 1752629399, "0.99", "5", "0x13e430a45ea63e8874f279cefd8fbdb98426f2e25a19c4b9ba513fa1f1295a17"),
        (270, 1752629399, "0.99", "250", "0x34ae5f27465eff61fe7137cc132cc062e9fd97a9e40be8b3a8e6c4d056bcf0c5"),
        (271, 1752629399, "0.99", "100", "0x4e25823cf28c0c394f7788ca4498f5ac0d0bc2e9a9c7eb70cccaa5c1f083e55f"),
        (272, 1752629399, "0.99", "250", "0x70d42362b8f0d592a5e3ad2337a5aa69805b312d46a5e1140d1053f5e8775eeb"),
        (273, 1752629399, "0.99", "5", "0x7cf295c2377665fbedfa59b9083b13b8e6cb02d9374f0411651efed782aab68d"),
        (274, 1752629737, "0.989", "20", "0x42b0425c7947e71de7eeeb31bc0b3fb0a92ce98479beb6c7e4b0a0991ac6054d"),
        (275, 1752629737, "0.989", "20", "0x77db7f8647e8feec72dc5126d4815aa920811607360bc050b5c1d87a4684d554"),
        (276, 1752629919, "0.989", "29.99", "0xc0482bf555c9042b8d40ce8ecbaeaba361e67465ca4bc1b835860313f9cc5ca2"),
        (277, 1752630099, "0.967", "113.34", "0xc4868e8cf76aabe7708b8d74a8652b37a6ea8d6c7c255ed387d10d1e954a4b3d"),
        (278, 1752630111, "0.99", "5", "0xf36148f791d3e1d8886b972845a6b7ceba13631d137a4d864f5fcd079ed9b817"),
        (279, 1752630123, "0.995", "5.05", "0xab716447c4d8f619f69b0cffc2b5302b4e8bc65857860a11961a03169ca0bca8"),
        (280, 1752630277, "0.989", "29.99", "0xc7e6db2e717a9e8ae17ef1290f2a4fdb2902d816447b8d016afb9c15aea6939c"),
        (281, 1752630291, "0.989", "20", "0x4499c78f5d6b733ebf4da0b970f69fe25c4ecfcd43dbe3b2bd3dc17abc61239a"),
        (282, 1752630537, "0.98", "20", "0xa5eada530d2192db5b29bf82cbff3398b4bd6683d69ce874beadaf3c1d685d18"),
        (283, 1752630563, "0.979", "70", "0x645c959246f65873bfd88f283c4396d75198bf7f44f86d454d071da6c89fc8b0"),
        (284, 1752630563, "0.98", "52", "0xf0e2bd6ccec001f6a5354c075ada27ba4f483ab339d15b0ead340ecefda4ab8f"),
        (285, 1752630645, "0.9799751932", "20357.33", "0xe63d9ab5d0adfe08ff1010a03a7b964845d445c8fb285c0f2e04d9a24387b007"),
        (286, 1752630879, "0.9789999996", "5.107238", "0xfb904fa16785e45bdd6fc2246382ff98a84694451fc1a028aeb9980046896150"),
        (287, 1752633807, "0.9789836066", "305", "0x80ee0c6bd7cf8d203c87467d2c0c375da9dbd8d50c0e38d9baf45cc050f1fd00"),
        (288, 1752635044, "0.985", "35", "0x2d2f084b59d59ea27797e2e42d3540cbef2aceee279df15a55d7c226e53c985c"),
        (289, 1752635080, "0.98", "65", "0x960d8bb030019de5e3bf503c2517e28d023607e567a477c81db9be496e75c3d6"),
        (290, 1752635320, "0.986", "5.1", "0x2a1772e5d5c4ffb701434eb69ae6e41f633039f37b349ace241e110062e5cc34"),
        (291, 1752636490, "0.982", "4000", "0xb2c70cc5b5ed6680e8a7e2d515c0745e515cb3323bcbb04629d9664a756b0489"),
        (292, 1752639710, "0.981", "10", "0xf4253e92b3527e1d41156d2e8ce304569ba7a872b0e8c1c3dc1fa80b0ef77997"),
        (293, 1752641552, "0.979", "10", "0xd48a2311406f31955aae47a52ad179413a9d281f030ae511cea26465791f8e53"),
        (294, 1752643176, "0.972", "5.13", "0x982fe67580aedebc3d0a40c5fdfa7921036dc198df27d2872bca7ffabb40a292"),
        (295, 1752647757, "0.978", "90", "0xa844e8a6ce49cdf41d7a55d9067a7e287bd8aeaf29101f24642533f9b66c3b0d"),
        (296, 1752647765, "0.981", "299.64", "0x9ace87e927510a918786945015076dcccb818e6ada33c3bcd4268a39dae4af5c"),
        (297, 1752648809, "0.975", "30", "0xf427db09c5d117c88505dcffd5d02076bbf23eb5295c15510a78ca9b8517891d"),
        (298, 1752650971, "0.981", "220", "0xbba17db7f88f0ef1d526b15d219bb98e9fe16d724522be3dd9636df2b8e7126f"),
        (299, 1752651117, "0.981", "70", "0xe50125b4ca09a8f51911edccd514d62e706a4da374674edcfd3b194eb1f103d8"),
        (300, 1752657458, "0.978", "34.48", "0xafc7c5a15719e9da329cab771efae34a5e1ddea37e031e26c42da4b9d3639c13"),
        (301, 1752659291, "0.977", "20", "0xefe0c0d50186b7d7d7754b20f1c2463b2ec41cfea05fde8b8c7c91f5c378f353"),
        (302, 1752663552, "0.974", "19.99", "0x5abb0248ac5a0330e6480bbd2649307a8530413bf230ff0d99a8584cfd78f1ee"),
        (303, 1752663552, "0.974", "19", "0xc9496a0220fc2be0aaa2c0c777bc29b0182c7445c2ad3d0f16519df1b0134ed4"),
        (304, 1752663586, "0.975", "10", "0x8594d5bc009e39918a4e2a7df6ff5bf26303eb711644e2e7920278b034884ed6"),
        (305, 1752664029, "0.976", "30", "0x3b2b938c14f76979d59e8d2d669cd4c47ebe3708c095a10def454aa888133e84"),
        (306, 1752665731, "0.979", "5.99", "0x2e13ddb41a58f6c9b2dc101add6c27d2dc8d3e1047fdf6a51e02041296fdc649"),
        (307, 1752668956, "0.976", "10", "0x6e435d0b142c31993efebda1b50d31f9fa2484f043bff10e4f7fe58f3f8c58c0"),
        (308, 1752670522, "0.9797108873", "204.14185", "0x8cbbf0bd0c29b2354f7eb883fb9691d6868c1b8b043e2d45cd7e8361c32f8ca3"),
        (309, 1752671334, "0.9698458285", "130.05", "0x52103c47227956b7644c11d89b32eb158095fbf2fb4eaf1fb22e77856d76a7c7"),
        (310, 1752673252, "0.975", "10.01", "0x1015f7a4f321cd9e055cb62a269549c72b925614976fc534ab6bb03910186df2"),
        (311, 1752673294, "0.976", "1050", "0x49b99903e0b4b46f0021442fca8fd2acadefda5e9ff2db472c49869c00357189"),
        (312, 1752679842, "0.964", "3.33", "0xb4c4b3543d23ffd74a9745daecd5f2ba1ceb9f0b0a956a28cdbf3c09df32a2a1"),
        (313, 1752680900, "0.975", "10", "0xde9338e1b9ea796a3d5d7fc2ae0fedc699211e66d3a9f633370eb2ce329e3fe0"),
        (314, 1752690522, "0.97", "80", "0xd66271399dac01a7d0064562d87fad00be7dd9a76619ca9502a0e31bd2675230"),
        (315, 1752691174, "0.97", "30", "0xbf153452baf1a816404f237b96c60887a98f3b1245d0519b3f9a6137e9ca5cba"),
        (316, 1752691930, "0.974", "16.32", "0x0993492e988cfdcf62e2a806e29cc4d87f31d35a7e77e5dfe113263032544b01"),
        (317, 1752691934, "0.974", "13.68", "0x67d14c9cd23461fcf7a8343fadcc4df6fb1a628dc4e2c310419b37f2c2871cf5"),
        (318, 1752692078, "0.976", "50", "0x38417b56528c26465aae0e282e9c7831e8f5857fe346615585fdd7d6c067eff7"),
        (319, 1752692228, "0.976", "203", "0x6135de7544e68c920458244892da4c3056cf23171b523281073d5ae0defe3132"),
        (320, 1752692230, "0.976", "630", "0xd653946e6f40f83685bcbbc3cb1e7631c1e4f8f42b3365d8707dd68566d5b9cb"),
        (321, 1752692842, "0.977", "104", "0xc774f40f6b9ade6442bffd3b6643fd37eb1bfdcb0e6c4b399d34aaab53ffd058"),
        (322, 1752692850, "0.977", "59", "0xaa55f43a4140a00ca97cf275076934a875415ab7737c3b49432a9cd6ed1f5fd9"),
        (323, 1752693558, "0.9779998494", "1.022493", "0x1b7e172ba2820001c4a888284c00b0c3521da472b0ec8af029e20e52b1efc3b9"),
        (324, 1752693590, "0.976", "1.02", "0x3ca5071c1f91398934dafa0d3adb967b1d8e3767a9dd3a72eb2b0cb99e39b3ca"),
        (325, 1752693976, "0.978", "20.2", "0x548f5ae12c4d87b2ced20a9b57dc380411d94029c36c23d7b0849394cda2b08a"),
        (326, 1752694188, "0.9779998494", "1.022493", "0xb1e3def0d582a5d235a0ab06068425c1afe5bce61174417b849f11f7c0baa0da"),
        (327, 1752694386, "0.9738823529", "1.02", "0xea21a7da34b8994e751dd0b2da25cdc3063b3ab355c6f241e2bd72926a93c334"),
        (328, 1752700404, "0.973", "10", "0x2c822bf65e0ea52c189a44dcdaa0f27fc48037928341daa6b6963a34c3cd5008"),
        (329, 1752700444, "0.9989120611", "4309.81", "0x6e49a484d11c92e27d53cbb37450ebe465188eba9b2ef2c51783d71e67fc9b30"),
        (330, 1752700478, "0.999", "3266", "0x579c73165818c65522f7552bed50d2c48a96e65352608f1d638df3d822a5d9ad"),
        (331, 1752700772, "0.999", "3726", "0xb6c3efa813c3750fc43ce0a3c5b31c9fef2fad0587a82ea8657bb7c7dfeaefd0"),
        (332, 1752702280, "0.999", "560", "0x5cc2e541a1b1fe0e66c4eb7d682cf134d33d18ca4bfe19617c123d77010ab3dd"),
        (333, 1752702298, "0.999", "960.01", "0x6f83a1f8e34ac7e0d2fc9429b68d664e19ffaf7d94259b660a22c0ae8239d92f"),
        (334, 1752703124, "0.999", "30.77", "0x8f7a6dc6bf40eb1c261041845afe2b46cad6a09b7f817dccac367349add2bb3a"),
        (335, 1752703128, "0.999", "90", "0x789e6db52510d192d3948bbc978b4b3bcc6dcd1272f5eb0957bfd6eb291c9715"),
    ]

    fileprivate static let retained563323Yes: [RetainedTrade] = [
        (0, 1752504374, "0.2", "50", "0x0d11d4a957ffb46ef9441870b633e232fb6b85aa78cb761cef7fa904596332bd"),
        (1, 1752505637, "0.19385", "200", "0x939130948690be3be2f966a86fa8150f6dcbe741a31d9a8a0566c13d0c7f539b"),
        (2, 1752507383, "0.1923076923", "260", "0x5f41c55d1459ea0cdea4bbb98160a300480af57319335ebf3e43be16db8a4603"),
        (3, 1752509388, "0.2", "5", "0x05d860b3bd664d014315817328830101b6adf37ab0dc5b25886195ac4ac59820"),
        (4, 1752510268, "0.2", "100", "0xe0863200b0be0fb6f51ccadeac3c013718fb040552e698973d5b138b0857ca4b"),
        (5, 1752519907, "0.19", "10", "0x064a14f59c4c2b1e309e2ddbd147711458a52d261a89a398da80951cbc50e35c"),
        (6, 1752520513, "0.18", "8", "0x268d64ef1d3ccde7e059655f94b23bcf9ed36d916d8f5b73c4d8e2d3ee10145e"),
        (7, 1752522635, "0.18", "5", "0xac8a5c73204a3ad69b08d89cf35a513961f6f50e6919a28a7096ca613408360e"),
        (8, 1752527929, "0.1799998704", "5.555554", "0x9eb0af7ef187146e38372c1bfd205aeafb9d6a1bc4de8f018efc13ccf868be4b"),
        (9, 1752528051, "0.179999928", "11.11111", "0x167c30a3998ca996ec2d58b4269b3f50bdfd0ba2d37a0889b9f8f44007764221"),
        (10, 1752541683, "0.17", "100", "0x90706b704dcfe6d7f0a7284e406402a3a8f8a4c1fb0f26a98168610776463db3"),
        (11, 1752545815, "0.16", "11.63", "0x11b70a50eac484db482b4fdf9a406ecd8768f8bab0032cd78236ba2fd8ebf4b8"),
        (12, 1752545823, "0.16", "23.25", "0x2050fd62715503abada8a74718da94f4d81b06fabfe7a7b97840a975e4218bbd"),
        (13, 1752549861, "0.16", "5", "0xd7cedff0951d5859281a5cd3ff60b87b1d794d212ae3b680ff9ef0279cb0dc15"),
        (14, 1752552377, "0.16", "5", "0x14b2de69d279226e19bfba9a68b0d2e94cfda3772f67b086c18ded942f0c2db0"),
        (15, 1752552389, "0.16", "3.01", "0xee79124d26b15876c3307f5dd8645341b34432644c2d9fbae8d4cc5a342f63f0"),
        (16, 1752552401, "0.16", "3.99", "0x57bcd55cab1cbcb0bb43dccfb51bc239e958b112838cfbad568e7dd1871f48b8"),
        (17, 1752552403, "0.16", "21.01", "0x84fc6f29266c18931c002d9b79a3f0dbb24ee126d5f2e8771639205ea063deb6"),
        (18, 1752552407, "0.16", "5.99", "0xedfe8b395f49c577bb9717eb34efbc70f690c705a45a62426f10480e6bf10d15"),
        (19, 1752552411, "0.16", "27", "0x2de3aa7c98c14a12f12a2f094c9cd13a6c99f111a62d8b2a7da65ad4421feef8"),
        (20, 1752552415, "0.16", "11.01", "0xefddedc73b4f7c5d8df89f757e08bff572e1a1b9f784a9ff0127500c9a3774f8"),
        (21, 1752561477, "0.1699999972", "294.117646", "0xe59c03b6ba6db2f04039ece9881ecafe4ff787ac16d3952baa5880c7334afac4"),
        (22, 1752566381, "0.16", "103.83", "0xa37cafc46bb29f6e7b22ca1156a47146d2cc3f9ed5afe45fe46350c051033d86"),
        (23, 1752566389, "0.16", "5.56", "0x53613a87d485dc404579aa15555814e0742dc25896d6970421b69119d268419d"),
        (24, 1752566658, "0.16", "5.56", "0x2e37089e51ed70de1b580095932c07f944ffb6f58532908d6abe6d8223271fd8"),
        (25, 1752566658, "0.16", "5.56", "0xcd91b63c5c71a2314f2b6ed773b97b2614db6b0b1cac84225db93ca9b9a3700e"),
        (26, 1752566700, "0.16", "22", "0x8626d0d9b76193becadec98d255e2ac9329eeac24ba0166a2d2cecfbca41c14d"),
        (27, 1752566702, "0.15", "25", "0x11f3f0b035cee52c0b4afdb280ef1eedc1d025f78f40f353f0d0f6dd720b1b50"),
        (28, 1752566704, "0.16", "5.56", "0x93d8b8742c0c4fcfbe0c1166265e946cb7a15d30125854801cc10d7884fdd5f3"),
        (29, 1752566706, "0.16", "5.56", "0x7b6e07882cc5c2f4fdd8d77dd05249c754fc7952b08cfb8cba40de963c3cb231"),
        (30, 1752566730, "0.16", "22", "0x8fce26261cd29c3378df9255d01b72a7a34b1eb7aa4363bb4bcc29f9e7fb9bb9"),
        (31, 1752566750, "0.16", "22", "0xd30b8d87b10673496c4caa142fb1764cfe311f7e0ea4dd22b6c2c6f27e5c2186"),
        (32, 1752566814, "0.15", "206.62", "0xc98bc9616542272221e1df06d4d0276f5432b8784fa086b80dfdd2ff7e5766a7"),
        (33, 1752566816, "0.16", "5.56", "0xa6c7dded36d942142bc3ec92b8c24b61cda05d64d8839099d27139ac25359c08"),
        (34, 1752566818, "0.16", "5.56", "0x674365c2e7aed93ec794b65d755587e63d07c3dd2af43ee0a2eaabf5250bee06"),
        (35, 1752566820, "0.16", "5.56", "0x951abff7ebbf8d4d208b2f84c8408b3e5a2394ace0146a0cf425a48a25967177"),
        (36, 1752566822, "0.16", "5.56", "0x06f3e036637b57bdfa4bf8a87a9a7def047c88f887dfc0f6e6743e8d1281e7e3"),
        (37, 1752566822, "0.16", "5.56", "0x3c19e13fb759f07e7011c6584a9b8c9e8ce960242e5d47578f86623756b7d4ef"),
        (38, 1752566848, "0.16", "5.56", "0xa5b597a9af44fb962f32c2bca9b8e230cb240ce0b5ad794c2895364e91230bf5"),
        (39, 1752566864, "0.16", "5.56", "0x967aa1e0537053fc5578402a47684e6678aca3c8f5bbd2651657f1dc2a365f1a"),
        (40, 1752568196, "0.16", "5.56", "0x2cb81af30a1aab071930917520343214399231f14af078dbf095b19205f21ae7"),
        (41, 1752568202, "0.16", "5.56", "0x0c7297d90b04c33e32963cf7aeb72fe91d3b4dc1a4928334516cfd88f0eb62b0"),
        (42, 1752568522, "0.15", "1.91", "0xf0b1a887dd5632daa32efcf3eeb195a08b96f8afca0a1f0550421f2aa995d976"),
        (43, 1752568714, "0.15", "5", "0x3b4f139e8bdb622e5730eba792b5212938f08dc60ee38cfea534b659dcba5462"),
        (44, 1752569775, "0.17", "596", "0x9db9f5032dd8bd55a3fb2d2dc94e95b3b3f02dc37149c11f1af9dd2271c31d34"),
        (45, 1752569809, "0.15", "10", "0x3c567c54589a968b54676979d6e6d1472ea5cbdbe1385580be3898884ccffe66"),
        (46, 1752569811, "0.16", "5.56", "0x34424094bc581bad3d65b5e3912937af34464636a0195809fbdba3726f864e89"),
        (47, 1752569817, "0.16", "5.56", "0xb871ff9bd6d6d25198ea3b5c1e9c5ce9e78c7cc8f3497c06ebdb40e6fff861c5"),
        (48, 1752570171, "0.16", "5.56", "0x50cd7a809f35323cc1b07c7327d001f8c5db3ef29637a8a6410661634b34197f"),
        (49, 1752570171, "0.16", "5.56", "0xcde9353e6875aadc57e1c39c0af553d40175d94c480ea92205130fe0aa7c3a4a"),
        (50, 1752570171, "0.16", "5.56", "0xe7994bd6b20aadfdd2052d7eb18a5e98ffcc700349a98220ffe19bc73818122a"),
        (51, 1752570173, "0.16", "5.56", "0xa7e209911e219f7c9acadeb1fdfbda3ec78e730c6bc596ed28882a7786d87457"),
        (52, 1752570173, "0.16", "5.56", "0xd8572abeb1ecca404a2dc3988dddc6a60e48d2ac4c838bc3897f85f54b5be4de"),
        (53, 1752570177, "0.16", "5.56", "0x27105a9bd11f5b5e0a0ebacaa218424228b2d9591fb1a4dbb5d34bc2ef4fd321"),
        (54, 1752570177, "0.16", "5.56", "0xd53ef7b61b5e3870914cd992c117246ad85d4c32db90684b6cf24c08286ae5da"),
        (55, 1752570209, "0.18", "5", "0x1fbd4bebb3f9ece7aa3b58cdf81b375ec573dd1a1b16fac4ea1d729117ae7f6c"),
        (56, 1752570209, "0.18", "5", "0x4ea34a88d32289f451e7d0bcf575db50180e27321f84b51cfba4067d9e6bc8b8"),
        (57, 1752570209, "0.18", "5", "0x910523d63bc3d0211d5285827655621c78f792c74a75587523d17813bb5a9eae"),
        (58, 1752570209, "0.18", "5", "0x938fe7dcb63179eddf4db8abc5dede01c3c51e9dd1d7ce6fd9e4d77741cdfa80"),
        (59, 1752570213, "0.18", "5", "0xef07aec43847ee3b13ad83966f27a04bafb9c210dea1b559cde0c5545c1fd8ef"),
        (60, 1752570643, "0.16", "223.09", "0x47c5b4889e2e255e19f3a8dd395f3abeb9501a8e19ab416c0ee50dff279780e7"),
        (61, 1752570643, "0.16", "1000", "0xeefeffcccf523fb8998efe27ad42113c4150b552e6cfac16a3d3bce576820272"),
        (62, 1752570829, "0.16", "240", "0x1add4bdceb37f46681c0ea57a9c2ebf63822361ac17e430c4c357fc9a2204195"),
        (63, 1752570865, "0.16", "5.28", "0xc90448b0281e3f009bcddf53ae6519750cfac61972db433da59d7602db0c7c41"),
        (64, 1752570867, "0.16", "195", "0xbec0dd372900305851b0e296dda20882f37c286c8fbd91e1065b8b19478ed0c9"),
        (65, 1752570869, "0.16", "39.72", "0x82b333fec6e4167bce33b0cefb915eb98843bfb6933228c12906575d9da62b9d"),
        (66, 1752570989, "0.16", "240", "0x574c9ef6af35247dcbdec6618eed15cdf30defed9c17a3b39350372b34f6fce8"),
        (67, 1752571157, "0.1702997275", "880.8", "0xf245148dd8ab24c5e7553589666eb7f772f625b9737508aa8d1b623dffaa6873"),
        (68, 1752571297, "0.16", "45", "0x29fdbabc2be97f1dfa6548e262f45fee755cc1cddc8129ad0d401fb0ac870d27"),
        (69, 1752575261, "0.16", "50", "0x3e9ab7cce46bbbb487f43fac117d79c6d091feba81d26178943ba4c19c734a0e"),
        (70, 1752578845, "0.16", "5.56", "0x57dfbce901e9ebe106facb542901ed227d241c72527d113222e4461c35daf8af"),
        (71, 1752578907, "0.15", "1.41", "0x3c3d7a8b46b826769a2a5691e491aa69b6bdd5d659a0b6c794b9161fb4da8a75"),
        (72, 1752579313, "0.16", "18", "0xc5d523d3369dc15ee7bb57bc7967b107524a5a615365f1412b26da1e6d504b5e"),
        (73, 1752584819, "0.16", "100", "0x6e19f4992440ed62e5912d508b9541e23862c8cf8074b489f1c88dcc040b915b"),
        (74, 1752585129, "0.16", "550", "0x7ee1dc0304228ab4219a71a6ed4b7b9c2426a99f7e03b6dd608c95a6015f3b7a"),
        (75, 1752585727, "0.1699999759", "29.411763", "0x679f109d74c00bfb18d1d70e856fcbfffb2cfd1b34e40de560133dd6002bef6a"),
        (76, 1752587555, "0.1699999702", "26.470587", "0x3d6d1bc43477ae7e5b7843ad70e615f6ecf6464195653880a2bb36a1745bc945"),
        (77, 1752588081, "0.16", "3", "0x747951be8b4f333fe0bedbdabf26720eeda120cd0ecb54c1ed4b42402eccc1ac"),
        (78, 1752589479, "0.1699999759", "29.411763", "0xafbe026c75f6b6413fed9008815fa9a7dde2b7b9b21b592c5f7167af20c61a53"),
        (79, 1752589811, "0.16", "84.93", "0x26c0be2bf01f30346994c7345c79a2be266e254445bd127d08f60cccc44a217b"),
        (80, 1752591263, "0.15", "26.09", "0x0f8d43f6d61b916bea52310c13e6efa63957a1598de09ecd217e33fdd2544b43"),
        (81, 1752597970, "0.16", "60", "0x3a7b3b22d155ebf21022ffec80858d715a62c248e9c5de8da49e9e84c1431f87"),
        (82, 1752598152, "0.16", "62.5", "0xa23c295e6182d06f133260b21d84f5a7e610a19e664850e1b07694c56e21bc9d"),
        (83, 1752598160, "0.1674287101", "238.907646", "0x2dc15f32a8275d75e8f16d2161c62a8ce25993cd05e029bd461758631268e567"),
        (84, 1752598738, "0.16", "125", "0x7cb3f1edd58bbc60f809ffada2b60da7059bf685863b3ed97fb56111b15de66a"),
        (85, 1752598898, "0.16", "5.56", "0x098125ea5b98afa37d087dc96c144751309dac408c196d8cfea692283a6b1719"),
        (86, 1752599227, "0.1699998861", "5.882351", "0x199139196c507a017350e6eaca43f414a3fb4320b1bc14641b2c2b0af2e6bfd2"),
        (87, 1752600153, "0.1699998861", "5.882351", "0xd4851b8ea95bf896eb6ecf115dcc320c55d04a051bedbed9f3b5d2d4fd0a336a"),
        (88, 1752600173, "0.1699998861", "5.882351", "0xaf2fd4619a1f921754b12122f99af03ddac8af2c4aed614bcfa7fe14266810ce"),
        (89, 1752600801, "0.1666666667", "60", "0xa35dc31d5536cd33216a7082c4584b3c925ece5560caa8a8063ad8311bcfd51e"),
        (90, 1752603351, "0.15", "5", "0xb739740084b0697dcc9f81f31ffb7a9f8a9cd5212e52271977c57f10575a13bc"),
        (91, 1752603429, "0.16", "281", "0x8f852a824bdc280140050496a3c2781275ab968032e3eb3e653aec039a74b46c"),
        (92, 1752603429, "0.16", "86.99", "0x97629eb7a7ce9afa39646ec58863fa60e295db82e950df71c31d449d613a49e0"),
        (93, 1752603796, "0.16", "3", "0x18f122a5cdeca88d010a0be1a5d3f086335a6da55ec50c4e8e4b3322cd93f5a4"),
        (94, 1752603956, "0.1699999987", "580.058822", "0x103e45faf5a0297fcac80edda493f2021d9645a5a2d4d7a20a101f8c9a98bdde"),
        (95, 1752604200, "0.1699999759", "29.411763", "0xd2b64a88d32aabe68b89c2728b27e6bc2b82dd001b0ebe11a7e03781434cedc3"),
        (96, 1752605764, "0.16", "2.96", "0x93a7a8d24d3bd183e45e5ce35308f610f2b8ff0a0367b8570dd2062586d91f07"),
        (97, 1752607254, "0.16", "200", "0x3ae2f3c8d683a8de0961eda690b2b6f2b4f7ad2f9cf45b52d708def65b5e359a"),
        (98, 1752607258, "0.16", "1002.01", "0x5063571a2dc704b7c83d2d019799d812695b9f527674ecfe043a591f3ddc38a4"),
        (99, 1752607370, "0.17", "10152.45", "0x0f8332c169511459c2fb11a09181b5ef83e3e74715434373d8ec53e3b877d33a"),
        (100, 1752607382, "0.1799999432", "13.722221", "0x7b678d65565e241646205d2c10e6552b762cc0cb401a413c387ca04e95c664cd"),
        (101, 1752607556, "0.16", "167.24", "0x9143b9dd8f97b75dc71366306418ff7b8bd2d02ec954ce95b9122aac3ce80dfc"),
        (102, 1752607578, "0.16", "8", "0x5694423b4264418a86f4db9900967ab33c64d040a72e3cf3ef306e939e3c4e29"),
        (103, 1752607582, "0.16", "5", "0x658eca770ef7ccdc8dfacbdfb4ad4e4bb76f34b28f1a6e85275c0c4e72643d3c"),
        (104, 1752607588, "0.16", "24", "0x844996f8bdc76b1d28714e53ea4df660f3962000bec34a67c023e0e0b6b2b084"),
        (105, 1752607634, "0.17", "10", "0x0fe292a32f3176c20966fcc81dbc57c81b8d9b6edb5e35ceab3cd7a562b17c30"),
        (106, 1752607992, "0.16", "165.03", "0xcc2307138ef05e40962ae0406ef5e4562d819b69c212ff2c68a005b40291a5d4"),
        (107, 1752608596, "0.16", "209.97", "0x19502fdbc96970d2a92c6b0bf29a377bb8da93a8e782f879ca404513da7c377d"),
        (108, 1752609106, "0.17", "10", "0xa63d722083257db3257a787b83b9c11de23a5591890c26e82a70cfe94b925f88"),
        (109, 1752609236, "0.17", "10", "0xc92a15d725ee186dbf58b1ccfb26f522399bc53654373d9fb7f3599eb82179f3"),
        (110, 1752609704, "0.18", "5", "0xf5ab0395f82ee1fc5331abc7275f12cc16a200452ce3bc060406991d3cfa4093"),
        (111, 1752610480, "0.18", "363.3", "0xb90ccdd04e529c0edfbeefe4d52d15b6ef88427077deaad1d5594c1d236a346f"),
        (112, 1752610958, "0.17", "9", "0x2470c66388ea4d7eb1e16f23021b5c99830f49f2f6c2666dac7a4f16a1004a52"),
        (113, 1752612397, "0.1980885262", "620.9345", "0x45c92f0814ac07b9d4b0767de3bbfb8960ed47a3142cfbf6e887ae383b41ea99"),
        (114, 1752612409, "0.19", "5", "0x73c4cbccca44939ad3bcc17b3b6fad2cc7e92c3442e751e472bfb86553e2da40"),
        (115, 1752614965, "0.22", "500", "0x1ed1cff5292c48fa1c81c4d0c11f5a9f34c9feb002e2f3c2bbedf1dc075e9a5c"),
        (116, 1752618371, "0.21", "20", "0x7ebae174420e9a5b0ebd0575ed42a35b50db55546a94b5ccf02c3abadf4cc018"),
        (117, 1752618715, "0.2178217524", "22.954544", "0xc2eeb62040666668e17c988bdc0c1daf244acd08e6b23f191b314316cd434c58"),
        (118, 1752618841, "0.2199999963", "167.727271", "0x59ef924da49a881b4490a4cbb95ea0e1413e48f5c930e65328f129e5be3909cd"),
        (119, 1752618855, "0.2199999571", "16.772726", "0x7ba85f45fa55caca9196f453f4c12e33099c1e137c40a5e0bedace46c05ae244"),
        (120, 1752619261, "0.25", "20", "0xf56614883dc5ffae53d9a5cde78aa3f63bc05a5b6eecbc8e596c58be3f37e5ce"),
        (121, 1752619481, "0.25", "80", "0x8fb7575204bc51f256ce83ad771ec2094b9831e06e3cbdb8480e4f3ccaf080ad"),
        (122, 1752620413, "0.24", "52", "0x7fcc24ae195f24c92ec74c7b165af18bba5e02ad2dd943ffd5e792d4c61ce0f2"),
        (123, 1752620419, "0.25", "30.01", "0x81d82f5ba3d100efb532379617c02e642f28545e0cf043d4d15d64a71f213866"),
        (124, 1752623035, "0.09", "63.74", "0x027630df7e705b8a47f466c971e42c6d835df6cf48bf3fa8de22af67e05b90c9"),
        (125, 1752623135, "0.2341463254", "42.708332", "0x8389a821e71d0d8a6a27b1c49ff7e83807f525711503eaac6dbe86fa59ee28ae"),
        (126, 1752623749, "0.2651282051", "39", "0x4b71d68369da3fe7f1dbac09a3123f075b462dcf398e7dfa299555d4955fbea2"),
        (127, 1752623869, "0.21", "17", "0x03050f4380acc5594c08b78e5c4cd5726b7fe55fae2a5e2c2b96b5f4963bbcb7"),
        (128, 1752623869, "0.1838461538", "26", "0xcab9c4c99465442ba06e9a5fcc85387d45aa35411ab8907665203ae9e05a21c0"),
        (129, 1752623873, "0.18", "2.01", "0xb8af8f31b6ddbe58b3cdd5bdc9650d755cf1d3eb7a47fe5d52ef6f9c0b2346aa"),
        (130, 1752623941, "0.19", "53.03", "0x01f22b82859b47f7771aa40576ae7db96219257b40d344ddff6c9c2878412b33"),
        (131, 1752623949, "0.19", "10.01", "0xd8fcc93dc3b0addccddd52219763e3d3ae6f00b3403aefadb395e9afb5a080c5"),
        (132, 1752623965, "0.2", "18", "0x226cbb20c54267b4458f06238d5d817b08c4698d10dd1a006eeba701cbf53162"),
        (133, 1752623973, "0.2", "16", "0x56cfb0a7612f5274b9fc129c57cce0125daae1400bed93eb4b209fe03a1c9da2"),
        (134, 1752624015, "0.2099999593", "15.714284", "0x051c4cbd54df07ab1d86e0e791b7578c55aea5cbb5f4d611d60bab58372027da"),
        (135, 1752624031, "0.21", "1.27", "0x19b193e7ce4f083dbc928198c6081015eecfe71407a369999061602061442a37"),
        (136, 1752624119, "0.2", "22.46", "0x8a3e78c462042f9c5e53ed53d3f8a9093d380e152614365689d1477a1dca3343"),
        (137, 1752624151, "0.21", "1", "0x4eb8425adcab546acd8f5acf5a141800ded0ee2356dc9a4513d4dcf68d275f6d"),
        (138, 1752624167, "0.21", "111.09", "0x110b8bab07a67ad396412ef8ce0f975a83c3634719d69f04f090a93d0b8731ed"),
        (139, 1752624179, "0.2", "29", "0x4fea3ae264a5d4e04f0bf7bfca817f44c08633de223a164442c66c7506a85ac6"),
        (140, 1752624185, "0.21", "21", "0x8c159626eb35ce7e903fef529dd75529d61f8c5f88cc25758f015700d5324cd0"),
        (141, 1752624189, "0.21", "9.87", "0xcf4cdf44f62cdef9ab1a51d642b96382569497c30e7f26ea30251a50e596ef29"),
        (142, 1752624243, "0.2332457648", "44.416665", "0x273f6ed6d4ea087399d445200ac9679a0e09a0a2787429f87e36b4d57672c43b"),
        (143, 1752624271, "0.22", "122.05", "0xd3a1c1488be994bebf91efeabdbf7541010b6bb846ba015ffea1336e93688311"),
        (144, 1752624327, "0.219999912", "6.81818", "0x942fabe798ef380fa6c04d8558d0c1404bde9a334b55c33fe76e116b29c3e3da"),
        (145, 1752624513, "0.23", "5", "0x5fa9e2d8a5a72e566081eeee0d6efc4a3c0f38e970fe72717443f43adaa3f67f"),
        (146, 1752624937, "0.25", "50", "0x0afc02ec695ae34ba3f9a28939daa0670be1dd2cae51772ca09303032d303641"),
        (147, 1752625039, "0.2599999064", "5.769229", "0x5120855ef0c05adf976bfe215a2960e8e0d2cd2ed500cf7d2b9e8a8e758f3019"),
        (148, 1752625169, "0.26", "30", "0xf989241dd90ca111a9f09422545ee549d3ea812f32e201f779f12526cd24ceb0"),
        (149, 1752625257, "0.26", "300", "0x8ef32a28102e0e50e9606fc7624020e04f15637b29613099c6aebb898a7e5cbe"),
        (150, 1752625261, "0.26", "150", "0x12ce31cf580cdcd2748969004db3d7bd2df74d9e34e2b4c4b0dd87637a7f38a9"),
        (151, 1752625327, "0.24", "45.05", "0x6cd52e1516f5fa6b40831c76fb16739e3c6a900c088cea295a0add2e72d0f361"),
        (152, 1752625475, "0.24", "11.76", "0x44d62f0d456f0ae2383c3cb3a26dd8c38f100c42d053ecf8b6ff461f654d98f3"),
        (153, 1752625633, "0.2586649528", "684.62", "0xeb5c01548df8a67cc9883c520e9ed411cabacc1845227c7c2617175e53110bee"),
        (154, 1752625993, "0.15", "310", "0x56283fb7c58a8b45fd596aab12a8d3ea3d8840f2cff04f5e1153b3908f28fa44"),
        (155, 1752626031, "0.1407692308", "260", "0x57c1c665e50e09057b507cf58ba2162aec7391a37338077afba96e74b142c836"),
        (156, 1752626117, "0.1527777778", "180", "0x213240c8daaa4a19207bc6b951c5222cbb4393943ab25a611e76e4ebc71969ca"),
        (157, 1752626129, "0.12", "25", "0xf1d2bb8cf1c7677eafd02c2d4187787e975f26090139fb51854d3f8afd87dc7b"),
        (158, 1752626175, "0.1770731707", "205", "0xbbf0d80812a08eaed750f7e2b12a51f9a3beca18f88b9bebb930342f20365053"),
        (159, 1752626229, "0.153029385", "165.05", "0xe4bdde937ea014ddb9b9044e0199a99a3b4a8462c783a6cd09aa40fd4a845b7b"),
        (160, 1752626337, "0.16", "28.94", "0x79389f1b2228d51379648322c28f1dd42c01675e71657ccfdfab26cbd8bf3833"),
        (161, 1752626337, "0.15", "15.05", "0x8c9b365fd817f7b9ead5dcb7d4b3da5c108998725a51a606b861e6dc45812ef1"),
        (162, 1752626357, "0.15", "670", "0xfad6e8d4af639528ebea5de8f9587690cff8891cffaddaaebcc3fb2c5e2f9691"),
        (163, 1752626473, "0.2", "100", "0x4fe866b6e65b9f72b833bc5433cab8b96ceab4ba0183249fdaf52d7fd09d22d9"),
        (164, 1752626565, "0.2", "60", "0xa66ddd35b149a4cc8007b9000b9194f96a648cc1f6428d8be3e25ad1b385b660"),
        (165, 1752626595, "0.2", "495", "0x3b7ded4feaa7be0fc7d0f3bbddcea96f6dd588d8a34f21d1de97f863a174afff"),
        (166, 1752626661, "0.12", "50", "0xcd2da426500311d926b834d7d275d135acb6ce729877a3b8ffccb787fc2c6813"),
        (167, 1752626741, "0.1466666667", "45", "0xd6458dfb24d8b8b2a9fa9e03e622dc4399fafef351d37119c6cf2a291501fe1d"),
        (168, 1752626743, "0.16", "10", "0x26fd04b4bd7e411bcb6b394344e8d9797c79d71682ada811ba8c22503e773021"),
        (169, 1752627033, "0.1573770492", "38.125", "0x0679ff54cde153335043e5efbbd0410d635a72fe6d55619aef831f5543c3a7bb"),
        (170, 1752627041, "0.1697433642", "38.882221", "0x29169986ccfd0643f3ae7a4bd6e623cf0e55293bb3d527aeb4adf9b2be42ebea"),
        (171, 1752627417, "0.1116278832", "35.833332", "0xff34ede9da8f6f3e8f0293889e26bc93424356f36fb74eb18007d9f05ae18676"),
        (172, 1752627427, "0.12", "225", "0x9302d8c835ef21851eba43bdfd8bef31b853298e189b6180b5e84e73c07dc50c"),
        (173, 1752627513, "0.125", "50", "0xfed60fbdff9d768ee6bfc3032fded71f7271de988e2ee07c31788232e451f184"),
        (174, 1752627675, "0.0599999966", "266.666665", "0xe0af674112d046882356589768f1902454bfd844a686fd7ca0f8f0b89c1be290"),
        (175, 1752627703, "0.04", "25", "0x802f7a65b073aad1f44015f16eb296697a32ba54890415d150dd03fa589a9c75"),
        (176, 1752627717, "0.0413821643", "48.33", "0x7d3f180b7030de2a6020ecfad595927cd02cf69407f2e939a07efe6f3a628771"),
        (177, 1752627855, "0.05", "230", "0x43fc389f7c7f04725315653a3520bb837f76ff7c3828737a641bfa42398b02b5"),
        (178, 1752627859, "0.0699999982", "514.285713", "0x323825cdba9ac4be282fe28db2f3b9f493fbdfcf66f815a2838116748a19888a"),
        (179, 1752627971, "0.1099999662", "24.545453", "0xc1fd0df16b2d655d4b02c9377de9b081b8e4303b2cae5fd8e0c6d9370ba47a5a"),
        (180, 1752628015, "0.09", "25", "0x03fbdcd7b2d9cc1d97d43100fde931ad3211747a0aebadbae3492820439d576e"),
        (181, 1752628023, "0.1", "30", "0xf5db5df1e4af55b26d54e5dedda75e668a742943f89dd4cf69cb23d76794afa8"),
        (182, 1752628153, "0.1199998992", "8.333332", "0xdfb4891d93ed83d282425740919524c14da777f6e182a79a0e11ce370d7dfe14"),
        (183, 1752628187, "0.1199999899", "83.333332", "0x5263d80efc40a747a07bb5b90e8ab2a6df0a2a949fe5b24224969715d7df2045"),
        (184, 1752628221, "0.1099999521", "18.181817", "0x007698fd9af52b0de63587eb34ebbd3db29e319984a4730f4519ccc4be460cb3"),
        (185, 1752628251, "0.1099999815", "45.454544", "0x2c69b98410967d85545c75863fc5ec4d538e1b5547d9d8fe345ac58331298917"),
        (186, 1752628321, "0.0956175299", "125.5", "0x00fa84619db4b40797ef6cffaed1a70c8a7b226c9f959d6433b0190e00a7561d"),
        (187, 1752628377, "0.1", "129", "0x582e6a8e4d41005ca779905e75d3419fccc4957b451112de862ff923468cc77d"),
        (188, 1752628389, "0.1099999846", "51.81818", "0xf44c1440634688f28d06cb7b95b49c7d70690b020579f1b67b8c398559de14ea"),
        (189, 1752628621, "0.1", "100", "0x47c87cb1326dcc7fe30f2f426e52731520208f1a15d75db17676b5ae01ae24c5"),
        (190, 1752628633, "0.1099999032", "9.090908", "0x107db7c4ee8e40fc5552b939e2c6a6e283145bac2acc4638d4696be01a514150"),
        (191, 1752628935, "0.1", "10", "0x56f38be2501142aa517fb662ab4d8a0e1a0430a90da10f97b6d227a7a157c48f"),
        (192, 1752629069, "0.08", "9", "0xe76d850795590c1f4d38b1d4cdd01b273503553d0179e94574d7a697b9dd951f"),
        (193, 1752629133, "0.089999919", "11.11111", "0x75adf9b6c4037e0745f8d137cdec16914e23aba923efc139c98b3f748397bdc4"),
        (194, 1752629173, "0.07", "130", "0x2f6eafbeba041ee4104403c89825463bc98b4a05411974716e6259843e005cf4"),
        (195, 1752629193, "0.05", "100", "0x02da28fcbd320ee1e6c21c18f42f222ce0fc58b25783b4b0689375e33c7a455c"),
        (196, 1752629229, "0.03", "959.99", "0xe6464c90049afd431b955bc30240c92781043b9861de3c82b9f5ed00e3deaf31"),
        (197, 1752629741, "0.01", "99.28", "0x0cdde81b7f4963c0202e6eb18a6b110f827dd5be3132e889cd38a6f6d5a51013"),
        (198, 1752629889, "0.02", "10", "0xd023e3277309b27f5e306785771c0be80d03023dc16b356bf3b6dcbf834e80f9"),
        (199, 1752629915, "0.02", "47.77", "0x05bf1acca384792726b2ca6dc50d143a8430574eb1579ba2ee2d7ce2f303c37a"),
        (200, 1752629981, "0.021", "230", "0x09268eed087dd2e3a9f54e10b0b00cfccdaf14ba6b735c275d08f90b2591dff0"),
        (201, 1752630009, "0.0207277314", "206.12", "0x0b6618ba4d1902e1073ff7c79fabdb648dc392208a7e3a87249232613fd8bd1e"),
        (202, 1752630245, "0.0441106236", "385.394665", "0x2f69570f4bb65d975adeee3f86083445db5762d5178059c4dca57bf3452d0001"),
        (203, 1752630275, "0.04", "10", "0xb6b8ca343da3523ddb8516d32afe936fad257911a887f60a6ee8cfa510f8da26"),
        (204, 1752630493, "0.03", "500", "0x77ef284ac12d4162eb202fca0a43cdb202d012137e2e704eb411df0ce73c4b4f"),
        (205, 1752630515, "0.03", "50", "0x971a69e213e870979bd981253e42bd9925e7864d4b91c065910b721f2f90a622"),
        (206, 1752630537, "0.03", "25.67", "0x5be61a2c4ff3efd1e9d2f1d6a3ac64948eedbcf5d000c0e5249c486521523b4c"),
        (207, 1752630563, "0.031", "75", "0xa1512809395ca46c9375afd92713dad837aa4e74dd599544dae2f4835fe32fa5"),
        (208, 1752630809, "0.03", "100", "0x4ff692a063227e786dfa1c4045653524fc000b565f2a28aed84dc232264c496b"),
        (209, 1752630853, "0.03", "1223.56", "0xabb7ac46404353cb120c0a2019b6de92900dd531a89f825a22cd7bb756ad47ab"),
        (210, 1752630983, "0.03", "500", "0x1797d2cbb88121511ce532de8c8ad5bac67cb198f4eec9bfab66e06f37e06ee2"),
        (211, 1752631537, "0.02", "100", "0xf93cf5e696cd5866eea680113caa4cfb1d894faa05fcc934d9b0cacc254ebfa0"),
        (212, 1752632251, "0.025", "500", "0xeb7cdf0d2533340f3397e338957d7cbc35f3a2d6548673c9315de935166a919d"),
        (213, 1752633363, "0.025", "4505", "0x4f16a3108a3df8d333b6e060e953069737c7b3c947e2af6d6d8d7537e3d875ad"),
        (214, 1752633913, "0.0254716983", "39.259259", "0x37d1b6d88510a025bb17931b4fea8e90e5164b643e03cf0f7bad8c0519818041"),
        (215, 1752634309, "0.0200008414", "17826.45", "0xf85dbe9f90f83d656e176651d5a29e2ef83dd25df12177109356c732a2a68de3"),
        (216, 1752634612, "0.02", "0.74", "0x93478f87002a4beaad25a6e188c89b7010ba92b55c25c6ab5d65bd895c9fbdce"),
        (217, 1752635554, "0.027", "30", "0x0fda8ab1b8c9496c48aa682f3cd17a841a954e8f19112fad7b704adf770f4381"),
        (218, 1752636786, "0.0277227458", "36.071427", "0xd43491c522dc33f0c6a21b26b5dc4922fc18af125c9a503d8e5fbc0d87eefed4"),
        (219, 1752641072, "0.026", "30", "0xa7f5ef2d35a38176e50a17205d174a579e44f15288a0a96b1f94fc84fd6e618e"),
        (220, 1752641396, "0.026", "160", "0x7370a94f77635b3a9426de25b3b821737eb6a6ec0794956bfbd737e665e7f7b3"),
        (221, 1752641522, "0.022", "10", "0x82a553c1fbd809d171c0a82d7dcb6238d4693211fa372c617a44ef85526365a8"),
        (222, 1752642282, "0.021", "5", "0xcb74a62135e4a20192617a3ea897b6c7735e830021a6158c7f6120642c7a089c"),
        (223, 1752643669, "0.02", "999.99", "0xefbb268972463620c6b04cc48181b66a17ec4c2429df15edf6ef47abfa00d2cf"),
        (224, 1752643707, "0.0277227458", "36.071427", "0x36c96eef80a541bf58c2862f6f9b870146b530fb9f51a0904c9b2af95a6bd1a3"),
        (225, 1752644208, "0.0279999733", "35.714284", "0xf9ccc80de8db770a68153608f785b538d086f8b36a925cd0f65f055297eaab82"),
        (226, 1752647091, "0.0386250256", "5811.57", "0x1a0a9d13f654c326758f1975e96eaa923a8e5d7c905cf3f9895496714b16f496"),
        (227, 1752650303, "0.041", "18.46", "0x8f0592f664b8647f42a69e8bbdf948ffbbab7c9a7037b808029f334195242414"),
        (228, 1752650971, "0.033", "9.99", "0xa12dfe8ec48fcc395c2b1d215c62d690c9d247c32f2b7b63aaeced5ebd8fce4f"),
        (229, 1752650977, "0.0416946259", "84.183487", "0xe979e9e0285fefbf8b49f836a1be68517539ffacde6cb35b71a7067b37447f99"),
        (230, 1752651117, "0.032", "4.19", "0xb2b345248c352304c042f8a4858772e4b38a22a393c1edd918d520b13f9b68f0"),
        (231, 1752655085, "0.032", "312.5", "0x09fcb360be0b06711276087995a93e765845264d24176d71f41baea78e86e400"),
        (232, 1752657458, "0.0289999724", "34.482757", "0xdd9279b7277e42f4d2c6ce133e51d3b6df7422cb652c37682255869e677569e9"),
        (233, 1752659291, "0.0314137931", "290", "0x484bf971d7175cbe88e4e27f82965557a069ead4674fe6a962ece8d794238e2e"),
        (234, 1752661560, "0.0329004174", "60.789472", "0xeeb4aa445c2cca1006b65d03134a311264e2338a336cba1d6a6de075d6aaabc4"),
        (235, 1752663586, "0.034072908", "43.729728", "0x46a0ac8c6064e0c0c7e1e612b9c35419432c983a993455008a6e9b751f727039"),
        (236, 1752664029, "0.0374647719", "56.05263", "0xfa528658a516e71255699e06be71b8148e2561645542dbc894c5287eaeb47492"),
        (237, 1752665000, "0.038", "219", "0xda6b42550c538f462e66cbd220894c18119f0dda01ce9d75cdaec5124518354a"),
        (238, 1752665753, "0.03", "27.2", "0x14965c8dd1745498fc38832271319b6053dbf9d10f256cf4d748662cc9427fd2"),
        (239, 1752666027, "0.0379", "100", "0xcf0f3931769316d6893e6b5f09e60734d7a414cc50b57eca092c8c9503cfe91c"),
        (240, 1752666285, "0.038", "100", "0x42516eca74223dedd5a21d664ebcabf4d52eb0afed4c83e12d46a000d47d3d8a"),
        (241, 1752672860, "0.035", "67", "0x11ff8d5557646adc32e0dcefb7801dc852bafe8fe9999d390d7234d8a0dffa47"),
        (242, 1752674634, "0.03", "100", "0x3a925dcb9fdd516c8c665322928a0c2823ba8c4e0077bac09c3166f5c64038c5"),
        (243, 1752676568, "0.033", "126", "0xb249206a70ea14fbfa5706b3c204c02b8ab057b94199d9b4a8003b8b95a970c2"),
        (244, 1752679830, "0.0347490315", "287.777776", "0x5d63ca0fc4e336c15cad0517c7c0a8184f6483ceaf63bb0411bb8ba1b3c35dc3"),
        (245, 1752682610, "0.0358803991", "83.61111", "0xe70a0056af7608cf3ebebaae57313d53929cd414682aaef95674232f915a1d5f"),
        (246, 1752683376, "0.0365699283", "109.379487", "0xe42eb024c68bc6188b1f05d1b7c56300e6da39a7c165353f1298623cd506fe5f"),
        (247, 1752684822, "0.037", "135.135135", "0x6e457a56771d2474aef103b5ac4df787cee2d51f55d28a8c3fd2642b12ec5e23"),
        (248, 1752685334, "0.034", "67", "0x0673d3e6218576c095c0018fe7657b9f1b4369b3523075ba34e52cbbee6a60b9"),
        (249, 1752685656, "0.0369999983", "540.540539", "0x675ce866ef31e0e14f03b95fe88c5310e1b7933b40e25cb28a5686d5bca4bbb9"),
        (250, 1752686730, "0.0369261407", "135.405404", "0x10bb1d15183397e69402e15cd3f7a6a793b47c04f3303549c4a2772895d2bb05"),
        (251, 1752687878, "0.0398886957", "11500", "0xce4299ece762dd3f292a9c7712a3b181e8694a5eb2a61a8fe16f11c13e3e36f3"),
        (252, 1752688120, "0.0399857384", "7502.675", "0xff9bbee5c99e71e40bbff603074001b7762625d3e0c7fb91db8c822cfad373ab"),
        (253, 1752690452, "0.039", "30", "0x65e0f2fe47dc7c663eb240f28deaf0f4d0bbcc74fdf90de3abcd6ad2388607a5"),
        (254, 1752690522, "0.0394662287", "3800.717857", "0x3f8e102720c54c7b3faa356d14e3d13773fa7408977998adaa3bd8f5cde40180"),
        (255, 1752692078, "0.031", "50", "0xad575a2426efb5e9e5652b2cce916b6d031d252c70932b1a6166ea6cf4828e94"),
        (256, 1752696920, "0.0338039827", "166.25257", "0x7d36e141b320aa88bf12affdaede5cd3d2d2503179628bcb05d876671882584f"),
        (257, 1752699878, "0.032", "38", "0x406f6d3c9e43489d30973fe1cf67aff2b33557a7f865d2e21f33fbc149270368"),
        (258, 1752699888, "0.032", "424", "0x8e319ca23954d701c5b732106b6dbb117d6da21548055ec197d9a6a531af82bd"),
        (259, 1752700596, "0.016", "480", "0xebcee69ff1c1332824f9321e7d3eb412b87198f3ac484ad3c93d8ebd14626c30"),
        (260, 1752701836, "0.005", "2000", "0x06ce297459317210dea77c9c33a9864e7a933532a343fd1cc8e6a1850ccbcba3"),
        (261, 1752702312, "0.0028329167", "1200", "0xd4da54a8064df406a7835d628cc84da6e0ed5c24047741fae5b86123a89fb057"),
        (262, 1752703232, "0.002741654", "364.743332", "0x5f3aa9d6e82442c2699b84bc7a4374060ce6c37adcace32ed32c30b78f42a597"),
    ]

    fileprivate static let retained563323No: [RetainedTrade] = [
        (0, 1752506007, "0.83", "70", "0x917328ce7ade9f35fdde99affb5b5f4739e8dba4181ee4ab36cd2984afafd55f"),
        (1, 1752516056, "0.81", "10", "0x12dd5ba9bbc75f489af3c808e050a50e25bad4c853c35ce2e063a50b8b09c923"),
        (2, 1752521521, "0.82", "650", "0xadffd2e1a05121b39d0798df120566d9d11dbea08bafd39a660f31a42fafdb3b"),
        (3, 1752531315, "0.83", "6000", "0xbc9c00c60172977a6258b52324c20181ab11dfafdf3d7362ffe7fe1254deb0c2"),
        (4, 1752531497, "0.84", "105", "0x03554bf7b59e0dc1188a563f4459bba66f5f826f92b4c1026aa40e5ca8689bce"),
        (5, 1752531593, "0.84", "75.2", "0xd06784e666f4fc47b98574d880fa56aefb0ae6b1abb95e71244f11718e04266e"),
        (6, 1752531595, "0.84", "70", "0x290621fcae98157e63e37ce4fe5412aa1734163cce2b6172ff1327fd2f40825f"),
        (7, 1752543221, "0.84", "13.37", "0x9677bcf73bb0ab62e8442b2e11ef8bf705b3562a1579a00c46f9c1532e2004c0"),
        (8, 1752543221, "0.84", "10", "0xdd5617b206ddca7625b74f9ad8c024c02fcdcbe0757773fe7a38bc46afa63870"),
        (9, 1752545815, "0.84", "10", "0xba2bb8163ff8a27ff7c464d0006c1eab91d3f79eb6a97b9dc76be7311a82e5b4"),
        (10, 1752545817, "0.84", "11.63", "0xf8eb1d7cbc9915fb3fa835a93e8fcbd0eec40d91bbe3db331d7a86db851760ca"),
        (11, 1752545823, "0.84", "44.88", "0x3633b3972920ba46cd61126184f18686a05c90079436ca7460bf48e45cd93359"),
        (12, 1752545825, "0.84", "11.63", "0xfcb9a0de9c0a0094f4c41425b63c29d91a67c8ac53fa00f5cd958b936cc76d9f"),
        (13, 1752545829, "0.84", "16.67", "0x7d15ee930ed879a86c457a3c057cb169ff9f45a8f5de39b2ed7ebd9b200ef434"),
        (14, 1752548828, "0.84", "370", "0x03854107d6ce064be6d9b78f83116a3e066644a0d0d7792ff53ee01122a3088f"),
        (15, 1752548828, "0.84", "330", "0xe112f2d96c96d9253a46e839979855aa2cdfb1a47d80bfb837d556001ba6d83b"),
        (16, 1752548832, "0.84", "20", "0x271ff9616ceb8e09ba7ec14d0b7bdc74e16a3ec6b12175b2817844ef95907c67"),
        (17, 1752548834, "0.84", "20", "0x5696f5c1ff113bd80b355c10b54316db78a5f4b5c191e0c7231f3d27039e1a6f"),
        (18, 1752552353, "0.84", "2220", "0x67fba51ad9847c3fec95745ae4706408f3fef0d9be77a3a172d9db8131728907"),
        (19, 1752552355, "0.84", "868.32", "0x3dfe7e8e7b14f1b983d17d6303130725ccf45a8a8bc72291fa763d4c98856cfe"),
        (20, 1752552375, "0.8399999948", "15.345237", "0x0ee671e41dfed1c5be3f7ae20d305248beddef10bd6779669337296192e2053d"),
        (21, 1752552377, "0.84", "21.99", "0x306a85d9b3b98ae562783c1fe140862e8c58a5ec42d5dd22a4feeb46a7e284ae"),
        (22, 1752552399, "0.84", "25", "0xc0b19e676293a64861fdddbf0b3640540d80c0b25c78e3263ae66964966e8777"),
        (23, 1752552431, "0.84", "9", "0xa59c5bbebece990decb275f71148b11acb9a62b35e97e2d453f89cf76a8def48"),
        (24, 1752552433, "0.84", "8", "0xb03abf31bdf3b0771da36c16c0ec0e7b287f41515c577c6f3a8a06da35dc23ec"),
        (25, 1752555149, "0.84", "30", "0x7d8fbc8b85dbef3598a8081e3ab7c1d4fecb0e0c7b6df769006114d26e8f7c45"),
        (26, 1752555151, "0.84", "37", "0x470d1d4a2a1a7748a98c713650c3922e3b435dcd734a8de1d64041f1f6f9cf24"),
        (27, 1752559303, "0.84", "66", "0x2358d65fa4222d6ae64846d391a4a09a5c573e2398f73dd140622b8d63a00d10"),
        (28, 1752559599, "0.84", "320", "0x3720e19e8f4963150cf6778b7638fbbbbbe32595da932668e2a8ce239ca22fa0"),
        (29, 1752559647, "0.84", "100", "0x12d6d94cee9bdcc5e9978cbb3f5a29471cc6cd836e06e3544415b78053ae22b8"),
        (30, 1752566345, "0.84", "9.21", "0x966313c52c462c7c5a5eb66219db3580dda964df5823085296dce18a93716126"),
        (31, 1752566381, "0.84", "66", "0x5d6e99c17fa13913338ae4c3dc22ace6721b4e6132766b3ed66957d4aeb1d8ae"),
        (32, 1752566381, "0.84", "39.99", "0x7c9c334b2a8176e6abd1b984957ad0327b8095ad99164726b576f3136751235c"),
        (33, 1752566381, "0.84", "30", "0xcf87fa11d3615bc098acf433efb127b47565601d8349e1bf80ef6cf1842e9b87"),
        (34, 1752566385, "0.84185", "66", "0x47b632f2549cd7fcd6dba31fcac45cdf494ff356fe0878171bb6c9fd337643fa"),
        (35, 1752566385, "0.84", "156.25", "0xbf924488dd239b49395335e28174a0efb331e4fba31301ee7197a42146410e8f"),
        (36, 1752566389, "0.85", "1.15", "0xaf50a486165d8686c3c860d11fec201872b907faa35ba337c4fbf185aa559da2"),
        (37, 1752566393, "0.85", "1.15", "0x5966647d1a9a081f6957390cef37ea6e7b7f3adcfaba944d510efc310d346ebf"),
        (38, 1752566654, "0.85", "40", "0x066ec2a663c3376a33455ade157eb1a6383e530c7120a97f7a5687a888646d8f"),
        (39, 1752566654, "0.85", "40", "0x47c9ec459e9f1e5c6768f38cecee63d81fd75a45b1707c40da7d18f0505196a9"),
        (40, 1752566658, "0.85", "1.15", "0x060804b265bb3c57086ac2bee3ab32014057a70256a8024d9edf57eee0ae8368"),
        (41, 1752566658, "0.85", "6.25", "0x16a1de60c78da6065c922d091e77f2f83b01ac2ac70cfbbf66803e2b5bda1c6b"),
        (42, 1752566658, "0.85", "6.25", "0x777a786c6171538bbb14fec6f2807dc80036eb20efbf3c719adaffe824f4bce1"),
        (43, 1752566662, "0.85", "1.15", "0x92edca249e137dc04c219acfdaba3a56f561c1d67d559cfb7b62cc7275436894"),
        (44, 1752566662, "0.85", "1.15", "0xcd3de3948b4d454fa2c71ade33a7d810c1779c5328c36a6da4a0a5836b1e9430"),
        (45, 1752566702, "0.85", "1.15", "0x3b5d0d4a05985ab9bee7e7d9871f0240fce7dd6cb202c6a08bc3dc27ade84846"),
        (46, 1752566704, "0.85", "24.99", "0xb681931f2499f13a231c23d8136ef7704c779f4db9bce413f3110df143f58ae2"),
        (47, 1752566706, "0.85", "1.15", "0xfb856c658683dcdea0959474d2572f7b7ea11c8a17199ffd5a29d7a61aef5979"),
        (48, 1752566708, "0.85", "1.15", "0xda907713d7396493d5390ca7b83b47636255b40fef4ab48e9d901944543314c0"),
        (49, 1752566734, "0.85", "1.15", "0x5293b8409b14ea8a2ce6dd1d2de8217e97dab7edecd295e8527e124fd6e76e0a"),
        (50, 1752566734, "0.85", "6.25", "0xf5c98043b68eb06a25a48c26539002aef7d4a19402f91f3f4c640b1d1da9240f"),
        (51, 1752566736, "0.85", "25", "0x5c64edb0309b2c83385bb3419525966d186a4ca36687fd3596fb935ef8ecbfb3"),
        (52, 1752566764, "0.84", "22", "0x7578a2f4a4a0dbfb29cd8b627857227cc78f8bb1d2ed6d92bbe8a7989080d553"),
        (53, 1752566814, "0.85", "39.99", "0x1c4546ccb39ee055cf6811162275b5b563673538d8368f41853c8237fc6bb6cb"),
        (54, 1752566816, "0.85", "102.22", "0xbfe1ef31de79f1cb80f1f28de6a2d75944e5bf5a3a01a02e595c05b4db53d6e0"),
        (55, 1752566818, "0.85", "12.92", "0x3d396b162dfc7aa154356337ee347ee3bce83ce013af88c9565437702dc83c8c"),
        (56, 1752566820, "0.85", "1.15", "0x5fa3d199d350143e3ff3f58f77226219660d1eceee9ce09665d0a75f4831df24"),
        (57, 1752566820, "0.85", "13.33", "0x63483ac41a9aae8a26e50d8ad53f3de5a5c3935f89704241cdcb4913db626a7a"),
        (58, 1752566824, "0.85", "1.15", "0x92621c237dd11895784d01c1c0da23e6c0049a40ef421c028c0067e04aaa8fc0"),
        (59, 1752566838, "0.85", "27", "0x03343dd9bb43aa6bdf05ee9a5192dae16d850aa85c0d0a54cf39b16961c150f9"),
        (60, 1752566848, "0.85", "27", "0x44856e27c317a85fbe34beba4a171ca1160fc52345bf6b776d9356e39f045064"),
        (61, 1752566860, "0.85", "27", "0x3855dacae23c81f45eaf5085a82417ef2f74ccdf35cca33f5f93e36d538082e5"),
        (62, 1752566864, "0.85", "1.15", "0x6f27829aa4cab60628ba574e2deb44090ddca0c6ca0ec017847c442a862f1806"),
        (63, 1752566868, "0.85", "1.15", "0xb7b08f3c64fa64721f5792e1a88a496c2c773d9c026668e848d9d15008f4b749"),
        (64, 1752567078, "0.85", "31.25", "0x9e3d62a799e2e9c664dc976aa2b2ad665b00e0ddbcc9c1c5841d9acdb256eec7"),
        (65, 1752567082, "0.85", "1.15", "0x26cce35d72225ef53d5fc2cd4dbd1a0fb67ffcc2bae474f1dc82788b64ae4e66"),
        (66, 1752567933, "0.85", "70", "0x64887ca29db30bee024b1569eb7e1fa119c865e094fab346d41948e443ef25c8"),
        (67, 1752567937, "0.85", "1.15", "0xffbd9a896cdcdc772988ee3fd8011a95e07fd2b9b207fc6b15967005282ebfbf"),
        (68, 1752567961, "0.85", "15.28", "0x0df48fd52ce3df1354ab29cbd75f69e96f06dc63f824bb18138fa6f9e4c5a296"),
        (69, 1752567961, "0.85", "66", "0x33b849fa5e6c47c0238acfb56ce11636d9ebfac2698a9bac044f962d2ad1cb84"),
        (70, 1752568194, "0.85", "23.8", "0x56d384e9b2d262c1eab10cb49c04ea9e86fe74ba8cf5d869adc49e3bb6f4e061"),
        (71, 1752568198, "0.85", "13.34", "0x2a4358aab9bd3cdf929820ff9aa179963b189b537ccc5c7424984b3060b93988"),
        (72, 1752568198, "0.85", "1.15", "0x4620ba8255e518ba760b34c98eecc33b6dc7b3f467dbd4475538fd5b9b7b0c45"),
        (73, 1752568202, "0.85", "1.15", "0x41bb6170d4a40693f1aef76f48a67ac657782431e056889b25f9195ed5f2bcee"),
        (74, 1752568208, "0.85", "1.15", "0x79e284c4a18b0125a6c1e7f2aa0f4e2971ad0f88e2cc9b21040c0f3c9cd845f6"),
        (75, 1752568512, "0.85", "510", "0x80bb1e858fe9267b1d431179cb11d3d810db8d4567bbca86c050fc31332cdb27"),
        (76, 1752568518, "0.85", "1.15", "0x4753442d85bb9bb5d050e81c341788e664f79d46270c0e62fb402634401e1edf"),
        (77, 1752568576, "0.85", "30", "0x4e40a0bbaf4923a0b6dfdf2815e7f808dc4efb30c44b142f0ea4662c383cef63"),
        (78, 1752568580, "0.85", "1.15", "0x5445fa2557c099843fa9955d13f413d4d351b6a1983256040464eff2f79fbfbb"),
        (79, 1752569233, "0.83", "70", "0xb840710f0d600a5656def39abc727281afc803a2701c1048f2b2855772525841"),
        (80, 1752569693, "0.85", "6.66", "0x750cec7eb7949de01aa7420075ca898dcb5f0dd5e1f18a5da4c746f87331fc61"),
        (81, 1752569779, "0.85", "14.29", "0xacd5a4712870fe232cde67e61cc4728a7c0af19c97331e60145da536e6d98790"),
        (82, 1752569789, "0.84", "190", "0x14b7262a8f0a57a54dd454606a14e7c23e4b2a3fe9a3713893a9186c0db132e2"),
        (83, 1752569813, "0.85", "13.34", "0xeb078ef905e9962a8b849ec46674db9c6cc401be363b15166ba564e6050e38e2"),
        (84, 1752569817, "0.85", "1.15", "0x5c740fcd6f3a60daeb968af95f99ee81ac873ceb9da840a09a21ae9b6344cc9a"),
        (85, 1752570167, "0.85", "15", "0x06bf443cfdca204ca88756f22e02dc45c80eaa263de82568e50f680045572fe2"),
        (86, 1752570167, "0.85", "66", "0xf0e7268735feac0e3ecaceb7376a77bce7a65bcec72b97b746437dfd381dde4b"),
        (87, 1752570169, "0.85", "170", "0x2514466b97f343a4dd5aa733372daf2568e8ddc4f84d6130a2f91e434bb819de"),
        (88, 1752570169, "0.85", "173.19", "0x3e8fe18283b1074836d84417519a23e8eef716b89def8af93db6ca2c6b493584"),
        (89, 1752570169, "0.85", "15", "0xd954876bc51107d50676c11fde56cfea3cd43fd1b0f962bf23d14494d79d22a7"),
        (90, 1752570173, "0.85", "16.67", "0x5a375d9753c648801bc11b65691c41720c1ab1ec1b2cebe57b7fabb42dd77c20"),
        (91, 1752570173, "0.85", "1.15", "0xbfabfb8d44d51af558ae981489b42f51965d212edd12f73eaeb082ec5afea172"),
        (92, 1752570173, "0.85", "16.67", "0xd2adb3f84cb6be3de2645bc38577ef9df4cfab76dd99a16b5b0df89095a5e097"),
        (93, 1752570175, "0.85", "6.67", "0xb4de75393e497fba481a3b03d4c481efe6ded38bfeeedd3d9054302c158909ab"),
        (94, 1752570177, "0.85", "6.67", "0x4fc187c71b2cfdb86cf2f4e2261aa9453808a4d2282792a0ec33a46a4aa9bd55"),
        (95, 1752570177, "0.85", "16.66", "0x567157ae84dd9560d6ee3f6833f238d8c9cf1a688ca167e37277e95454aaf7e4"),
        (96, 1752570177, "0.85", "6.67", "0xc26ce7b17b86bf27ed086d516dc0da6e1b4dd6a0240d76a0ffb0efebfe2f39f8"),
        (97, 1752570179, "0.85", "6.67", "0xddaefc5bc1063fc7ad0d61d8b9753222150e8ac38520bf2a7f5520222f4647b3"),
        (98, 1752570181, "0.85", "6.67", "0x22d2bc9db9c10979d00a3ad3ec84f341f1ab7ac057ddc177aef63fcc35173b74"),
        (99, 1752570181, "0.85", "6.67", "0xabbce4bb2b522e0b6e550cd18f3c7633f7d9cc24e4cd0b23dd37cc14a573f2e4"),
        (100, 1752570185, "0.85", "6.66", "0x3633ba89d2a2ef39a9b2a48de81ebd7a5e9affed376753c804a3e3f2650079af"),
        (101, 1752570205, "0.85", "15", "0x779fb68c7b1cc379478e0462ee881a24e4e2fd58dcc588e05e5c69797e52a0e2"),
        (102, 1752570205, "0.85", "150", "0x7d2ba1e64edb80f25bbddc6a1b247eb55dae46b3bd9838c5eab8fdcb5071dc21"),
        (103, 1752570205, "0.85", "300", "0x7df610e4e5ff732febcc2ac1b8aaacbba5c52fbcb734aba4ba33b58d06155a01"),
        (104, 1752570205, "0.85", "15", "0xf9e163e58a31a01dbf0d66cf782f3ba39cc36af4f45407ea7389a87e6950f22b"),
        (105, 1752570209, "0.85", "13.34", "0x5bb8002fdea2056db9ceef3843630e37ea2bdafde19fe21299f78bf5d3c8c17e"),
        (106, 1752570213, "0.85", "1.15", "0x33009383bc14997c3ec9a75c170812bc519daab5f40430f855a513e5705238b0"),
        (107, 1752570327, "0.85", "10", "0x0d9a1d7d1735ce44921039c2c34b10a0a744fb5fbd5e39505b36abac07ad0cae"),
        (108, 1752570327, "0.85", "66", "0x2435e6645e36619288405bd487b5e8b78916ab08883e25d7e0f38e24266e7082"),
        (109, 1752570329, "0.85", "1.15", "0x13422ce050808f42ace1dbcb595a7b3054a68dfb6108365cf755ef637eb7c331"),
        (110, 1752570571, "0.85", "133.28", "0x38c1aaaf7284c54d21a898c5e965f6c409ed3af813b2517cf06713c750cbeb50"),
        (111, 1752570571, "0.85", "66", "0x5be26a7d8b0491a3813ace2040b8a8128b1921c4fc0d19a4eeb0076d15a5d0e4"),
        (112, 1752570573, "0.85", "1.15", "0xfdfd0b0863eaafc6be4164cac7d5279a0c323e9cc77a184a78e233e9e4d1a271"),
        (113, 1752570575, "0.85", "13.34", "0x411793a438f249f0c925c3f3dbc5f08b719f78207edda9638cc3756db7efcba5"),
        (114, 1752570577, "0.85", "1.15", "0xd95ca6252d6094f88d4dfd9110838df79863f2c6aad1e13bcafce05444d5d3dd"),
        (115, 1752570643, "0.84", "39.99", "0x077ca856fdc946397d5aa4bceb3181514f13b3886a66ce6479843c8cbe8fa768"),
        (116, 1752570647, "0.84", "14.29", "0xbf160235c0a88be8999a46a260c1a87fad06f28fcbdf887ff0061714a6669407"),
        (117, 1752570647, "0.84", "14.29", "0xc47a16026dafebedc5f9fd119f8b8b774c427761a83bccd9edd924d5b33bc0e0"),
        (118, 1752570649, "0.84", "14.29", "0x16d1e9d11428d3a49d8b275228334ffd51edc689d020d5b4a7d57c0fa714c440"),
        (119, 1752570653, "0.84", "20", "0xdd03a5b486c72e54803c92e33e8c979efa80e01bac88639d305c41600144e934"),
        (120, 1752570827, "0.84", "329.94", "0x7c281d3f28a0c70f49e3f4778af10c94efa221f633e34c184324ea061b1a1b45"),
        (121, 1752570827, "0.84", "39.99", "0x85d6cb15d2e323fe824de6ec34ef52cd2bc6b13c91332c26c81513f1fee79989"),
        (122, 1752570827, "0.84", "66", "0xcb468a730a80d3f350c829db4a407195493699f785a437bee6e36e45c2dadfdb"),
        (123, 1752570827, "0.84", "452.13", "0xd7dcdc87c6438ab7351da6eea465220465f0d731876d14a9b95b9b09795cac8d"),
        (124, 1752570829, "0.84", "5.57", "0x90cddb4c28ba78730fe213c5f3d1cca5152bb3c4da2ed7ef929921c52ffbb076"),
        (125, 1752570835, "0.84", "37.03", "0x329912c2145834898f7537fe6663da3b726611b83f613dbc9da35b73ccec5d62"),
        (126, 1752570843, "0.84", "4.15", "0x3e9648481070fb0d56a676bfb466e04a39c6b8cba11a073882a2508a5777cb88"),
        (127, 1752570845, "0.84", "5.55", "0xed607740143460ae7f967787533910499b13598b11181341ab70e8dc9b0ef4ee"),
        (128, 1752570853, "0.84", "1.1", "0x81df97fc9646917438f3b80fbf0854512accd5caa2e3bc2446bd127d499e4599"),
        (129, 1752570855, "0.84", "6.69", "0x2e621da9040f56412cc6ccb320fe3b0dfc16740e0e9251d565545978d64d5ebf"),
        (130, 1752570861, "0.84", "95.51", "0xbb660ccaf8df43de15a1e7c53675729d5f37d3e7e51201b2b21c250a01559d4f"),
        (131, 1752570865, "0.84", "16.67", "0xe6f6caa45c7e076ef3c299e1181206abce509b6a0ca70595b61ea666391a8dc3"),
        (132, 1752570867, "0.84", "244.7", "0xbe7f7c5498c6b2fe7a6ed2c8151726c34f64e060a5c45af6fffe0e6fd469792c"),
        (133, 1752570869, "0.84", "5.56", "0x872ecbec8ad81579efc01fe29e28435826a9ee05fdc5fbcc31d43e2715287ef1"),
        (134, 1752570871, "0.84", "5.56", "0x81202f80401e86156fcecdd9cd6dae2e7186147bceb1de95e479152b96176192"),
        (135, 1752570871, "0.84", "5.56", "0xe67036d8aa604f6753c5eeb9b91d4658393e632a9dbc401258c9d2aebeafdf46"),
        (136, 1752570885, "0.84", "5.56", "0x22a7f92687abc3706e1779597951b0d22e3cdb9a69fbf6476caab23fe778d004"),
        (137, 1752570885, "0.84", "5.56", "0x2c7a6b3d48baedd43a359d49716edeb24db293ee11794245727c7737a2331b11"),
        (138, 1752570885, "0.84", "27.46", "0x6356fb8a1417a1301436d6b3417362dc66c684b70c21678f2defe03be8ec36f0"),
        (139, 1752570885, "0.84", "16.67", "0x978a7a92f8602d1c5e0809832d61435d3ab1620365aa65625bcfe08b5ba69c1a"),
        (140, 1752570885, "0.84", "16.67", "0xf741e1b9445cf15d7c66b0c2e8df0a36f9805a3f12c12dda73aff1cfaf551fec"),
        (141, 1752570889, "0.84", "28.44", "0xa341ea62e0da6fdbb8d864c0629a7383f5fe20c530cf1dca6516a1bd1fbde6df"),
        (142, 1752570891, "0.84", "39.99", "0x601220b7b70bf626cbb9adf619f8e6ad7d7ff7b876fee6781a77686a28a52e9a"),
        (143, 1752570891, "0.84", "3.19", "0xa87fc797bcaf3922e6fb2cc7cc548c6cacc72e3731742f92c0be302c2a2d312e"),
        (144, 1752570893, "0.84", "5.56", "0x0eefb67d22794c8b5c0653b79aea0987c30a13c00dfb17660324517a2372bf5a"),
        (145, 1752570893, "0.84", "5.56", "0x202407629e7eb22a4e5f046b800872e2f8a35d336e6681a94fe3b335f24edacc"),
        (146, 1752570893, "0.84", "5.56", "0xb2f2d94134a45d24b89a0f5778bf42212ece19fb30a50235f8d130ba4c89c858"),
        (147, 1752570895, "0.84", "15.98", "0x1568cb6ac1baf015bd05cfe3c5b7fef5a12937233090e86f98261eb2acd47016"),
        (148, 1752570895, "0.84", "5.56", "0x66c581c8dc6fdff1c6d59f68096abd6b9ab19707bdcced3a150049941bb45769"),
        (149, 1752570897, "0.84", "5.56", "0x8fccabfe9679f2cab1aaed7719c4a2ee45a9646ee542e6706c053b9dda55a95e"),
        (150, 1752570899, "0.84", "62.48", "0x537543544e76dd5422d823844accdccb66d2ca2b1fef01435d7fb0486663bd24"),
        (151, 1752570907, "0.84", "242.29", "0xce0ae8e968b14016c840815eab24d7a3cb2b08e78af87b2cb2609dfb2210fbc8"),
        (152, 1752570915, "0.84", "60.34", "0x600c0e862d5144a852c364af4b5d9b6822a65c77f0487f6d3569cae9f1ed65bc"),
        (153, 1752570923, "0.84", "6.77", "0xa90190dada00fb6556569e6d80764cfd485319a33a5becec9fa0f094d680838a"),
        (154, 1752570933, "0.84", "271.67", "0xdf39f58f103951463cb0e08a9c6f0cf4fa6d14875e85d7923ac8c906f2c7e4dc"),
        (155, 1752570939, "0.84", "84.12", "0x4d5efc661681d30fa3f130be12269adbe21f2bf96f994956c471db776f3e281c"),
        (156, 1752570949, "0.84", "15.46", "0x0b21959b9bed6a8742e44fce2e6a8f68136ecaf9ed85da1e9d69ce9c131c24e2"),
        (157, 1752570953, "0.84", "39.99", "0x4f5c17297081370a76e5910a6217fd65a7fd3d351125afbfe55c1b3f64c0a59d"),
        (158, 1752570957, "0.84", "1.74", "0x7371fb138a51fdab62c9c4b2db2a2cdb089012b094021ac06338527f6da10ba3"),
        (159, 1752570965, "0.84", "242.52", "0x446295796b1ec8b5930ddf754dc129ef4f1a5fb53b7490b43b321ab990f972da"),
        (160, 1752570971, "0.84", "5", "0x1699c22c1a73c32e2ca18b6df371de200312b7be66d056db121dcdb4dfbfa83f"),
        (161, 1752570977, "0.84", "6.66", "0xf40f0fbc020f2f26fd0255c8052bf8bfcd67aa357b9331f16105b7e9bbc78f3b"),
        (162, 1752570983, "0.84", "110.73", "0xebb172d7b2c445b5118ceb78258a5bfdc1909da24d76dbcf244fbfdd16adf055"),
        (163, 1752570985, "0.84", "10.02", "0x86811d84f74a374e334538bcd241b07db6904dc5768cf1a7c500af88ce3b19b8"),
        (164, 1752570989, "0.84", "112.27", "0x414293367078ca53bd064cd56e4ee9c3cab660eb16e16bddc10d54e397e00dc7"),
        (165, 1752570997, "0.84", "190", "0x13dbac9ea779e483e3d1137088d582aebee552378b6f42a596772deb82ea8cc6"),
        (166, 1752570997, "0.84", "661", "0x3a94ac35f06f044ec961cb2910fcb4fbd1b554ab82d9da2ff9918cccfaba8a3b"),
        (167, 1752570997, "0.84", "14.41", "0xd5c19a1a6185ac1118beff0c362474ed5db497af6ae1cae7ac7a40b3472dab0d"),
        (168, 1752571017, "0.84", "15.55", "0x7db3d2a452c1ef2a6f4a9f1e7c55b71e68c395b6e025528a9021e6aceafd87b2"),
        (169, 1752571297, "0.84", "40", "0x195522c67423c40fbfd0b640b42f88f24ae6b9138f2a08a91f0cc241f6559ee2"),
        (170, 1752571305, "0.84", "5.56", "0xd4a413bfc89f827cfdc3e48dafaa8d659468d2fae2eaa9604091172ed88385d4"),
        (171, 1752571305, "0.84", "5.56", "0xe050605f3b6f6141a7c6b1198b931bc5733204bc143058dea660fc6e85476704"),
        (172, 1752571437, "0.84", "13.34", "0x1ae2474de0a6ff7c29226bbf13df708f1e3d4fed6fc684588426f3251cb1096f"),
        (173, 1752571443, "0.84", "5.56", "0x2474c09d8f64541a28b4e3343eba68442f2f27d4168296d36dc4fab60e4ecdff"),
        (174, 1752575871, "0.83", "200", "0x5c0df100fd7af0a8386c3632332dd79c5696221eea2ecf17c5cfda3e1d74c51e"),
        (175, 1752578795, "0.84", "781.98", "0xc963129b71aeb114f3270a3fc4d7cec5395bdf460fd0ff16d17642425e0b8cb1"),
        (176, 1752578797, "0.85", "1.15", "0x7dd2ed62ca7dff1a2dc9e891fdeb4b0ffc186983acf6e3fa6aafae7529a5fdbb"),
        (177, 1752578841, "0.85", "50", "0x53bab068c1309aad3f940abb4ebbb2c7ea914d919d93ac090d805e706f550ed9"),
        (178, 1752578845, "0.85", "1.15", "0x5c9130c86f69fc2a60f9fa97d9ef4147a79e29be59ace69c5279e2f10a3e2c64"),
        (179, 1752578847, "0.85", "1.15", "0x92dc85b5b6eb966224c954f1d1c116093142142cc278d75c54542af847770c61"),
        (180, 1752579313, "0.84", "17.99", "0xa94de0e4f2f609b092fc17c19d973fb4d0da088734d03575a787813cf2696d6f"),
        (181, 1752582529, "0.85", "20", "0x666df6180256c998cbf31634d4a1b656be4787514e51c7a3e35e635867c4f016"),
        (182, 1752586065, "0.84", "9450", "0x48eb344fc7c9cce93faa24757541bdd348384fcee322ca3e1b196967893808ee"),
        (183, 1752591253, "0.85", "66", "0x869555ee3f314804312abfc77ac61145ee2afaf21e0954b172ed40b0e701978a"),
        (184, 1752591255, "0.85", "20", "0xf5e2ce12218dfd249c77cc7c790022d96163a16f641490c82c806fafbfa1ae14"),
        (185, 1752591263, "0.85", "26.08", "0xd1072c1b384b332de149dca6a33a44b44b86622d1aa1d9ac24113fd624009c55"),
        (186, 1752598682, "0.84", "7", "0x156d4c5cdbd612b667e513623a5e5085a302972b6754272f1aa864b121106fb4"),
        (187, 1752598682, "0.84", "200", "0x15e147a900b2a185acb77c409fe4b1c3ee55a34d777bb7da5948937031518e0c"),
        (188, 1752598682, "0.85", "15", "0xec5943d736c1894ec2b27da4bbf13ec66ad14f21b31bd55eb57edabfa2832eff"),
        (189, 1752598684, "0.85", "1.15", "0x29391d3f65c1fdc6c6963dfb82aa5664a6391b8440d71437ad7b4a11b4181909"),
        (190, 1752598684, "0.85", "8", "0x5e703761d34e48a0fc61a1c020912db88bd73a88624d033fabcbe91d35cab3d1"),
        (191, 1752598686, "0.85", "1.15", "0x2ab1afa9937372d57019da43184abc845b0b244a46e370c5413e4b0e75ca108d"),
        (192, 1752598686, "0.85", "1.15", "0x7f0b8002788587e01250937c2ce5d93495f69ed90f38fe7dd625ada60cfd8abb"),
        (193, 1752598688, "0.85", "1.15", "0x22af836dbc14f39e0964a517ffd2dbc6938ecd4cb4384b67a5ad8e2bd6e99560"),
        (194, 1752598688, "0.85", "1.15", "0x41a3169c55b1b94575ad5308f147ff119182409fcbb24459606f44eb0a020900"),
        (195, 1752598740, "0.85", "1.15", "0x3c083baf23a07b6859ad674940ab97fb46340940bec3cec47f39e5e09b1b1b20"),
        (196, 1752598894, "0.85", "38.5", "0x61e2bb5a0b3516a3faa0a6054b557b3333a439f12fba16bda67cb46a53dffc70"),
        (197, 1752598898, "0.85", "1.15", "0x9a2c987e2522f7b4112c46d309f9f64e733512cab5b8ceb9832a4d242489247f"),
        (198, 1752598910, "0.85", "119.44", "0x6983cc0a737ec11203cf43863a9ac6fec73b7567a5f8f625b596bd9e42ec5e86"),
        (199, 1752598914, "0.85", "1.15", "0x3777dfb1f5c8b938614651a01fa6c65486ea97e9e4b0d083f021d812dc385587"),
        (200, 1752599261, "0.85", "29.99", "0x536aab63005e6d14ec3009e5072070337ee216482054bfd5ff70e3bd32685a9a"),
        (201, 1752599263, "0.85", "1.15", "0x2938b7972b414349f698a88b19775f963c8e4363559cdac42ff1012c67ec0534"),
        (202, 1752599263, "0.8499999935", "7.741173", "0x78f0ac0496f91d452974adad3cbd7a4901b72463e75605a061fa44538bb33576"),
        (203, 1752599267, "0.85", "1.15", "0x19d74e93b92a41baf7964c2e12607b38893267a0e725e08e9f72cc2380d369cf"),
        (204, 1752599267, "0.85", "1.15", "0xf5bfab28c6862b6c376c82f284d2c0210cd0bc822f4e1cff7b6ff7e2abfa05ce"),
        (205, 1752600805, "0.85", "1.15", "0x52f970846b422e89396a5b8d8c51a5d9fded24641388fc51cbd121d0019c413f"),
        (206, 1752601815, "0.85", "10", "0xdb770e582fe074372ded716ce59f7675c1066ff861d064a492511626f15793a0"),
        (207, 1752601819, "0.85", "1.15", "0xb9f3068f7980047486deb828fed762ff1105fdc5bca4478199995ddfa94b0cfd"),
        (208, 1752603501, "0.84", "597", "0x35bebe05ffa9a9d18207b4e3963b1b40d2289dc630d7bf187f6cfdeddf59d7df"),
        (209, 1752603535, "0.84", "30", "0x2b960d6a09c029fbe57affde090af06eef54119e355234dfcbe1a2e519ccaa2f"),
        (210, 1752603543, "0.84", "33", "0xccad974cb13377bfe96a51010d8751194d8229e968df07559d81bf5fdbf526ff"),
        (211, 1752603543, "0.84", "20", "0xe10043c4b63894ea9e22d10d48489b66f88520f970b0adfcd27a176dba854dfc"),
        (212, 1752605434, "0.84", "111.05", "0xb49fe46d9ddb5a09864efa78cd6bccfcb2b938a123bfd441c1547cab4011630f"),
        (213, 1752605692, "0.84", "40", "0xde4723321dbfdeb3b3adaf00903e37e65ee90d59b4a663cdeb664e0a4f852956"),
        (214, 1752605920, "0.85", "270", "0x1db51a7d553120e20613680c4cc0856ec69fb780c4a742c802df93c0cf0437bc"),
        (215, 1752605924, "0.85", "1.15", "0x5aeb4c1c908a89f6f085ed85a3228802d5abf8156ea5eceab3760c45cefa3af0"),
        (216, 1752606524, "0.85", "40", "0xfbf44f8ace81d872a3f1e428db2a8bf11dcaa89a8ce9ab97e2cc8c30087a859f"),
        (217, 1752606972, "0.85", "51", "0xe4feef5a6e750173222daf68f80e4ea93d87c5c591ef0a015619e577c75c3056"),
        (218, 1752606976, "0.85", "1.15", "0x1307a461f3e905dab3d2281893c397a0c572340449c18db8627db735d34eb3f5"),
        (219, 1752607258, "0.84", "5", "0x3eb4945d56bd748a6b7a66cf81d4dc5b5b8a151f6c5daa98d5c78634b4d475d4"),
        (220, 1752607338, "0.84", "40", "0xa8c773f0f7d9805d3b470ea9962431a5512c2b3e648977a44b3ecc375521d33c"),
        (221, 1752607340, "0.84", "490", "0xa5f5d9080bb66c77b47595f114fe1e1b08cfa66df5f0897053cab4a796efec00"),
        (222, 1752607394, "0.84", "250", "0x239fbc092fca525c56c570255b03ca70e2718a13297e859c2ad5f5d86caf8f22"),
        (223, 1752607428, "0.84", "1600", "0xaa62b51d0ee267da03ce8d9b8e0966313e5a27fd0d31c74057af87a4e629e2f3"),
        (224, 1752607428, "0.84", "40", "0xd6974feeb4cc331fdb88d338e7dbf3187c9b067a48ad684bf2d99b85db8c33a1"),
        (225, 1752607556, "0.84", "160", "0x439cf8a7b3307b8bf4da075d6c90c8d9c56fd6da4564b434128f100224484a94"),
        (226, 1752607556, "0.84", "167.24", "0x72e53ee44ced51fc03c469374f506cc73a39d7cb0f759473daca4172d1f4f0c7"),
        (227, 1752607556, "0.84", "39.99", "0xaec74bdbdde2c739fe59f1559e1b240564e479a6a7153b0644509a780a50059a"),
        (228, 1752607566, "0.84", "24", "0xf7a9291c475a201890d0608b4f9d0c3bc3f29b0137c0f244f61dda17cb71079e"),
        (229, 1752607570, "0.84", "40", "0x1c867eb5a0fc5dde66ac913f20ff29fdf0bddcc42c176b8c8d4f5958c45f0ebc"),
        (230, 1752607578, "0.84", "16", "0x490927c4279b621f9f036c9f4178116619b0a8441fe9c31e5e611450a4caac01"),
        (231, 1752607592, "0.84", "8.93", "0x51990f0bc8cc9e22f415ded4a905e806adfb8ccf81c1cf6a5bd104e943c8e08f"),
        (232, 1752607602, "0.84", "31.07", "0x16213c5714b5e60e059967f871e552c96b7c4ffb52cf058a1d5e7911fe3419c2"),
        (233, 1752607638, "0.84", "14.29", "0x005a958ed43e583106eda4640eb12104ae1aa234a28202bce743f090cf3dd75b"),
        (234, 1752607800, "0.84", "39.99", "0x0815365a8f33198a4b8fdc765c270edc85424482f5b99be9a9a3585264ef959a"),
        (235, 1752607800, "0.84", "820", "0xde44d586690abc02c708489f8b3e7a917e11ecf57a200acf7fd376627ea50f7e"),
        (236, 1752607802, "0.84", "140.01", "0xea2dd0f171769e7381fe9a40a9f7e76f9b1d9e63c888f9bcf459616628c2ddbe"),
        (237, 1752607992, "0.84", "160", "0x84e7ecae293bbdcbd025d29e6fa54cb452c394764463595e23eea315a19f5506"),
        (238, 1752608596, "0.84", "40", "0x773c9b825244d31c059abb12e5df827e6169dae38eabc8c15a7881fa44ea7bed"),
        (239, 1752608596, "0.84", "209.97", "0x87d75c098ee83a49c70068346f7192cef173a537e61b268e949f5b18084cbf18"),
        (240, 1752608598, "0.84", "200", "0x35269d6d9f8eaa54ff976d1bf72e1cd3ba3b29f26512c71190ead9d799fa6afd"),
        (241, 1752608602, "0.84", "16.67", "0x05d2108333e57fbcd1596e8ad9722d17c1ff54792d473ea85af1fa6499814f55"),
        (242, 1752608602, "0.84", "16.67", "0x29100b44a5bd5a6824afac69076876989afbfb07e1f9cdbd7fcdfe49ae5c6e40"),
        (243, 1752608602, "0.84", "16.67", "0x778a72fdcdf947fe29d2e7403101b1cb97dabd7ff5649f0a88209ab0cea853eb"),
        (244, 1752608604, "0.84", "16.66", "0x07fcd57c97baa1baa9651803b4f32185ae1d0d1d48eefbadb08fad1df36502bd"),
        (245, 1752609072, "0.83", "599.91", "0xd1e3e0cb4c5e7b1906e2308e07a56fd668a33220e2097744af39d5f7da3a1612"),
        (246, 1752609238, "0.83", "10", "0x8c0c5d388c0ab17d7b6999c7b40c897e38724823959a3071f0678321f6610627"),
        (247, 1752609242, "0.83", "13.86", "0x8a476ed97de50cd6a40cd48b952bbf600354b7f5c53e5dfed99c6348a85005dd"),
        (248, 1752610776, "0.83", "50", "0x57eaadc10b4d3beff9fce00626a9a95095056788d786e7ecc16c6c7447363e76"),
        (249, 1752610776, "0.83", "346.67", "0x9eb513156596debd2740c8133227b5a1ef5f173e5ea8b954826fddf73c098ebc"),
        (250, 1752610776, "0.83", "346", "0xa28f1cc8cb38aa13fbadaace4c84724ba07f7394d01aec2ce878d7bee03b3ae9"),
        (251, 1752610958, "0.83", "20", "0x0fe1f14ff71aff364c99d077fca597b8d26c38912d060cb4c2f3e851a9c7dd81"),
        (252, 1752610962, "0.83", "1.18", "0x21548605c530a3b57a2870d5560564df53a142915ce2eb1ae9183ebcb5fbb3e6"),
        (253, 1752612411, "0.81", "14.95", "0x70c5e83e4abb23e4b771ecd76f521ac0d88c43023847d45b5cdfb3b92f05bb74"),
        (254, 1752612411, "0.81", "5", "0xa85e79b93b8bdec13637a76542d80a113729c8ed8feda9ce62ff92e746599dfc"),
        (255, 1752613959, "0.81", "20", "0x096e6918b817b3d769ac31cce5a530280f9ca60f96a9451cb8db54e6aacf7711"),
        (256, 1752614161, "0.81", "33", "0xaaaf443d31406e703e9ce414390f17be217c39158fc979b5434e4e330fa1b167"),
        (257, 1752614923, "0.8", "17", "0x4f5b62e28fac1b74e28e2dac7896bc468ddeb6e17e5471c95e033ed5b00f9875"),
        (258, 1752614923, "0.8", "10", "0xee4359e82198a283c4738699b80ccda362799d2127d6e3f1e98fa78c8804d01b"),
        (259, 1752614927, "0.8", "1.22", "0xa89a80335bbaaa51a6f22132500ce0d30c2c6f9117c09d0a18f174b436984754"),
        (260, 1752614941, "0.8", "5", "0x7311ad3f1c600111472ac268547c37f2178fd9ebfffaab312370b353527df891"),
        (261, 1752615275, "0.8", "1.25", "0xe5527974606e2dd84520458994b4bf4a61f09dfe5e465d035fa03cdb9f5c7438"),
        (262, 1752617199, "0.84", "50", "0x4a1158540a4526bbdcc02605efffb029ebe7d166c3f5d8d45c5c835855dfcc62"),
        (263, 1752619807, "0.75", "149.99", "0xcc1e9497b5f3a922438844e09974538858e2ea1b6fd8826c664e62ec652aa331"),
        (264, 1752622987, "0.91", "50", "0x2c6cc9774043f6ec7f58901ba6a8719870d7286989416319d66a5b90873cfa8b"),
        (265, 1752622987, "0.91", "24.99", "0x959b5358511537d924ad5c8c85547b81507b58a3d542de459cbec8ca34f875d4"),
        (266, 1752623395, "0.826462", "50", "0x6c9ad479e9e77a3534246b47bca0def74fc5d59f0fc26ddfc7d6c7a25b5f41ba"),
        (267, 1752623517, "0.84", "50", "0xb142f967e65d3903cb4f65add1cb7b73c7813c0937024434cca11913dee7fe2e"),
        (268, 1752623519, "0.84", "35.26", "0x30d7b8a5f5a4303e313446ec07f57984a3ace7804a2bcc0b8d7acbd33615a5d2"),
        (269, 1752623827, "0.83", "15", "0xd9b1a36ee391b8af1d3c11d2eb4837416253ecc096c5b537bb9fc7f34348b9af"),
        (270, 1752623827, "0.8233798923", "15.1206", "0xe3d9a0bf199a3384d762322a3cb63c5cc8d296d2148ba49e122a02d541b573c4"),
        (271, 1752623827, "0.83", "102", "0xe4a738a26345748b285aa827be543736c88b77bf182f3ef12e55303516912a5b"),
        (272, 1752623827, "0.83", "100", "0xe574a2dd7065a261bcc6522e871f4728ac62a51e5d023f42ac2dba2e843ce290"),
        (273, 1752623869, "0.8120833333", "24", "0x6563790a310a81b8531dab250b7ed8fd825e84d264dbd55d9e79918aebe56a20"),
        (274, 1752623941, "0.81", "39.99", "0x56b883e2e723ed5cc9655047bd67c4d6a7cb6580828f91ec26cb8bfd700f7523"),
        (275, 1752623941, "0.81", "50", "0x70dcbd7b5c4c32abec0f008835151e66301b4c736ce9b8d5a573eb7d1cae9b0f"),
        (276, 1752623977, "0.8", "10", "0x9b113f301048bb6abb6fdf2d334c734a9fe8cd2720d83f8544579da0ce65531f"),
        (277, 1752624041, "0.79", "10", "0xacf081a1ad6ae755734b21421be803233980c6df26aef2e91bfca5ee4d8fdf4f"),
        (278, 1752624117, "0.8", "100", "0x2399fadf352a745aa57f2a730f17a3ce52df8d76675b9904fc95b49e02109171"),
        (279, 1752624121, "0.8", "20", "0xd7e6b4e1d7e92256e75e53502d261a0fb4d32603d646951bd18a09edd1b708d3"),
        (280, 1752624121, "0.8", "22.45", "0xe14a7fdd3e8fc21cdb6c5c995c99c80500f296a3693ae027ed562eae8a2e869d"),
        (281, 1752624159, "0.79", "23", "0x68ff031a9c95c32f1757147f567562cac9c11135f7a5376268f3fccc36bfc2ef"),
        (282, 1752624169, "0.79", "110", "0x12690219b0682412a6caa19f56b9eb649ed3dd2233eefa0dfb5d39ae390a1390"),
        (283, 1752624185, "0.79", "20.99", "0xdf0c61a3fde74b3153e7d22bf8ed451a793fe7161b7856ad9e0df00317681935"),
        (284, 1752624301, "0.8", "5", "0x1e2e479bcee7caa1a09e271b8008ca394b98739588eb1ce79ffb0c7518af98cf"),
        (285, 1752624329, "0.78", "39.99", "0x19d9301b1049dae9f049c6339f9c0927db317f96978ffba10096dd1be7b9d8cc"),
        (286, 1752624329, "0.78", "110", "0xb2adfaf8e54e9cac355749eaba18cafe4dc7e63ac3c931ee83176017101cdd62"),
        (287, 1752624513, "0.77", "5", "0x8881dab6f290a82279decc5a0cf9f597e3a930fd99bbd166d7eda5e51eef8f16"),
        (288, 1752624935, "0.745", "100", "0x22a9e98db153f39668ef7f942c4ce414de149ee97abeb4f4e1eae3b1b244225f"),
        (289, 1752625003, "0.75", "50", "0x2def8fda048024df77bd7fb7ef4db521b5ef744c098c4ea0962f17d62c2e0c7b"),
        (290, 1752625003, "0.75", "250", "0x476e8d4b557020fa160245652b6e4c6fe02ec0886741b5ab631bfa0ded470b57"),
        (291, 1752625003, "0.75", "250", "0xb2a2ddf0f1bc0b94bf4c6e1bb25093a9b646d71874cf134c121e1b03d7a8e9b1"),
        (292, 1752625907, "0.7869786771", "2048.97", "0xad4da2dc4fb74a579ca433db48b767ba9361cbdad14db6ddc71ad3345f2766a0"),
        (293, 1752626143, "0.87", "30", "0x0bb85048d96b53f1f9247a55b26655333059b0204a8ebd264f53b2f632a610c0"),
        (294, 1752626307, "0.85", "34.95", "0xe6aab88051966c17dfa8c34083fc3f59aa3db35bfb62838243d5caebf5f10d65"),
        (295, 1752626625, "0.84597045", "1489", "0x7262616297d256647a5726c48275124f7f9b38243a41b0332afc80816af6233a"),
        (296, 1752626629, "0.88", "500", "0x9c18fb2026d61fa9518f2a7cfe6f7185b20e81f6b8557fefb071c548aca72a74"),
        (297, 1752626741, "0.84", "10", "0x118eb714528e1fddfc1210fa20292d6b05f8d18744dfef93ebefe716be160281"),
        (298, 1752626741, "0.84", "9.99", "0x5d8b01a1113c7034f3919e53375441ce747ea0ecfa0eb7ae43d4ddb3843d768d"),
        (299, 1752626795, "0.859078341", "1085", "0xfa4b1c86f7b99c6fd07a36515b42b1ee8ec10be4d6381c2b5db2d9401f8a610f"),
        (300, 1752626859, "0.9099999827", "10.989009", "0x911e7458709b61c11e8961ed8306a94a15768057b43b885e834e9a6bab1783a4"),
        (301, 1752626933, "0.92", "40", "0x7139991cff60ffa37b69ad8564aedc53665b94513ff2274d8b327ba5fe5247b6"),
        (302, 1752627283, "0.9025084857", "1805.99", "0x4bed067330b1e27f35682193c0e76ac4e75895258dc8d4870aad4f419d7bbd39"),
        (303, 1752627311, "0.87", "75", "0x004312a9a21d93f03b11d7c1658502dc345a8e146992f9c1b2adcc299a2aaf48"),
        (304, 1752627435, "0.9497371048", "3005", "0xdbbe850759a6d1364c5083e786c6d76133a1aef5fac9d99ef324509e182dd2ca"),
        (305, 1752627443, "0.95", "74", "0xbcf421416efeeed135c07c4648cf5a7e4b30a698c94cf7499f204a436ce51a30"),
        (306, 1752627503, "0.94", "1029.01", "0x2be89e796b95bc291f217acfdf81fabf20e84331fa04429f6197b026b060265c"),
        (307, 1752627513, "0.9454", "500", "0xfe66e328d6077e45f41e84b97096b6a39bd2d1d0bf3ea686ed41e9fdb8022709"),
        (308, 1752627517, "0.95", "230", "0xdba98c507851fe1910ffac81db3dbe736ee289e562c2899faa2a1b2f77c20667"),
        (309, 1752627591, "0.92", "25", "0xfae66411e827dbe6443b583c522541b1c04951af1610aa941e542491cb776f6e"),
        (310, 1752627611, "0.93", "25", "0xd7b5db3be34523c3d73fed2950f054ba585d0ac124c200aa64d2602a05ab1127"),
        (311, 1752627923, "0.95", "133", "0x5e447f41396b0f9ee0288ae35bee3365217734e295d1920587a912bf810ec707"),
        (312, 1752628303, "0.9583637676", "2702.55", "0x2ed4de26eae27491e7379eba37c9498ccd057600d12f33c60804325f92beade6"),
        (313, 1752629109, "0.92", "91", "0xd3406979648ff19baf429dd61e53f83af498600e17514e2729bbbeef6bbcec46"),
        (314, 1752629177, "0.93", "25", "0x93438c68958b04d3240834a643a4d4d46a72598040b89af161b2d1125b1052af"),
        (315, 1752629177, "0.94", "150", "0xd1b79e67ef2219fa348ef0816220521d4aaf777fe7d79c6e8181713d5065b8a2"),
        (316, 1752629209, "0.9676573664", "426.87", "0x8f21303f6f96dae9bcf809c6bc062734740426e9fae164c33e74f4244bee8a87"),
        (317, 1752629233, "0.962", "250", "0xafead541867209a1db5ef67b5fe24e0bf8073bbfc06621de96abc87b2b405074"),
        (318, 1752629399, "0.99", "5", "0x3375a496a52747f813fe34952f0f83d83fd03ae17a8541a1c19b6e24a3a117b2"),
        (319, 1752629399, "0.99", "5", "0xb6529a92b2a1d18429f7d4dea7cd3059003d68805014231004cacb12e0550fbd"),
        (320, 1752629399, "0.97", "250", "0xbfe234dd18a4e99200eefce1a5be47973e96667b7e9d24b13a7dd469ad9ebe70"),
        (321, 1752629547, "0.96", "25", "0x6f2e5dc2ef6576c2e226289e6e05615f8740d5bda83b14bfd5129949803e4642"),
        (322, 1752629665, "0.98", "26", "0xbb813af0ea4a8733eba53e7c81cfc1af2b283fff59f732ee54acac14bf5b93a4"),
        (323, 1752629737, "0.98", "20", "0x870b583ad52124c809d65c9011e917a4a0470d9bf22a61634abed7be4a8e848f"),
        (324, 1752629737, "0.98", "5", "0xd71b79733ff0a23fa052d1ec3841f21a790edf6e8643b5ed1e7845a97c03ac39"),
        (325, 1752629825, "0.99", "30895.72", "0x55d1cb5e8ce5739128ba418099661c27742e90d71a3fb155a89fcb7edc3fbe0a"),
        (326, 1752629851, "0.98", "40", "0x387b0599d2e2ae29656ccdff4a8eb42a321171278aa6ab36d409cb886cb0fbba"),
        (327, 1752629893, "0.99", "5", "0x87b977f9bf798ae9273ebfad30c89293652ee3c11f6b3ff411b46003ac01e99c"),
        (328, 1752629953, "0.98", "400", "0x5126fcf49318783c73c97f85fec10a1b929d5fbd2567c1bcee8702ba995f742c"),
        (329, 1752630081, "0.958", "122", "0xe594893c043f4fe34bd7c354b366a818b320acec429ecd794ff1f37d3a3c1477"),
        (330, 1752630277, "0.965", "29.99", "0x07212e7ac963e755e5cc1366120ec9c092cd4784b7960db715ee2fbd967674d0"),
        (331, 1752630291, "0.968", "20", "0x6d2a5c287661b3710257e524e07ad30f7f10ee1d4dd27cb8a0f33b2953e49305"),
        (332, 1752630453, "0.9699231951", "3255", "0xd10e34051f481a9ec2c54da12a4433350196e39dcffe648c832292ae4a113694"),
        (333, 1752630465, "0.96", "520.41", "0x947ecf9a451746c3ecf17ac9e47a9cfe173bf3641707a2393b7409feb39c5852"),
        (334, 1752630537, "0.97", "20", "0x2fb378380574ce3c8391c0ef06f222d356e0dfc33a9633e21936ec42888cd2d2"),
        (335, 1752630563, "0.969", "150", "0x458021c03d5bbdc15c4f52ba495c0a5ea084eef307c0f71edf7f7c62218d75c0"),
        (336, 1752630563, "0.9693653846", "52", "0x6fe9034296b08a2a2e862de17ae9cf4739a435c8d1871fba9c4b4062ccee3b9e"),
        (337, 1752630563, "0.97", "70", "0x70caa2d492515504e618c9359b58ea1fbee607a3d407274eb1d1609d0f02f150"),
        (338, 1752630563, "0.97", "155", "0xae7e56417b0fe01ac563dd7ac3b8f55aab535fde94cbfea3acf5fb192a58bd30"),
        (339, 1752630577, "0.97", "4165.33", "0xe1cebf82d8ef5e1f4885d2518c49b2fa3476c823cce35bada88739866fa4ebf7"),
        (340, 1752630661, "0.979905", "16000", "0xc42b710c3bca887278686287e68c28694f49d998f42584c404762d333c381aa4"),
        (341, 1752631249, "0.97", "3311.44", "0x2768da105865f16000e25a6b295717939514b641efe652069000b791d8145e97"),
        (342, 1752631451, "0.9799753719", "20505", "0xf1d7907506f84f53b0232aa650084ce82f402cba5a62cf1e2a8334825e36a12f"),
        (343, 1752633859, "0.979", "405", "0xd6cad433b4910ddcf7d5b17420dbe4e0452d035004728f974db98d23dfcc8cc4"),
        (344, 1752635038, "0.98", "100", "0x14e1c39937a50afda24b7a50f2584ef51857b5d29e041c6d5d4fb2304f74e0ab"),
        (345, 1752635096, "0.98", "100", "0x872336d94b1b1843805984e6bb766ade260d21766d7ac2715060e67335fbfa35"),
        (346, 1752636074, "0.979", "2.5", "0xcc0108a7f629812141db6260faf0c36a0121fccf15c5939fb4fd23f9071d762d"),
        (347, 1752636812, "0.97994375", "4000", "0x5426346b80a0100c6f6e693a90921ee5b6c4d4511881d193054b9b7048b8ea04"),
        (348, 1752639686, "0.978", "10", "0x5515a9c901f0a36336cbd53689f4e646ac9428898a6959f944d3c10478c3b375"),
        (349, 1752640962, "0.978", "90", "0x16b4a61e862b8795d0d681137748ac9d0e805456cbd7b2481edb0120719871d1"),
        (350, 1752641044, "0.9789999986", "7.20119", "0xe9f6118200806f6d32e9bea5926ebd9fb48954ada6248ac781bb26bef85d32fc"),
        (351, 1752641226, "0.974", "10", "0x451d4981135965b3e4084f7b776680ea826e8ea49a0bf02c505d2d6e24e2e2a5"),
        (352, 1752642612, "0.98", "6", "0x898c0e1ce60f3d88d9103082e91164a96b238af40e985af1e7c07c4fa4a16a82"),
        (353, 1752643150, "0.98", "5.1", "0x88b111146f86d246eee9142929636d50ec37e81f0986ef4ad900d9eabf01443d"),
        (354, 1752646639, "0.972", "36.14", "0xc99847ad4a3e8b08b1a7b12c625bd95cbb8b3d57cd4a21e8e03324c3f0b9b798"),
        (355, 1752647753, "0.9410469043", "533", "0xd24ffc20e85c472f4944e074852ebaac387b8c3ceb9cf5d7e3ccf683a70644b7"),
        (356, 1752647757, "0.94", "90", "0xcafd8a9def1e854cbc7729d03671272d6acf4d3b37211b95c22323b879aab891"),
        (357, 1752647765, "0.9207398765", "405", "0xa0c0cbe1a4b3d0398fe9caeb2fb617d7619863d4f67c66ab82a4e962916d2f20"),
        (358, 1752648461, "0.941", "1.25", "0xc85ccbaa5933ae74dfbe3defda43c81452586abd3152ca99773ed55b83ab875f"),
        (359, 1752650229, "0.9581789763", "36.527609", "0x311f6de3b91891326007ac67f421e18999e221fa11211ad860709db2fd85e3dd"),
        (360, 1752650971, "0.968", "210.01", "0x5c9e2df5ed68b517108f0cc1d09e0d9f6b70e3dbc4dafc510864b632a1ee8f2c"),
        (361, 1752651117, "0.968", "70", "0xcc31c7539afaa65f350b24f1e739783e178b84e79a42f1a36ba31a56863d809b"),
        (362, 1752652805, "0.9708929088", "4146", "0xa10a882eaf343d8fe3725ef128f7bb7edb47b38326e6830cbf30266ef363ba81"),
        (363, 1752652835, "0.9729302326", "301", "0x53b7b6ada652f2ffdbf07aa6d20702d6b0b0ef8f367105edbf4599d7e1560b67"),
        (364, 1752653007, "0.97", "4302.27", "0xce2aeeec2d150af299e62132134cef2c8b8531319aa93cea36bcd2db53a48ba2"),
        (365, 1752653051, "0.977", "10", "0x9f043f20ca2b044b1ae292df88a64413953f3aa08883b8dbeebc109bff90a4d8"),
        (366, 1752653181, "0.967", "10.98", "0xfafa7bd821f73565e953d09fc86b1e17bf7af83615272a37e46fe1904bc4c2e2"),
        (367, 1752659201, "0.9786286538", "152.58", "0x89c8f9067e6287747d6ae5e47fadedd5b2279895ce3d2688f538a610aac3eebe"),
        (368, 1752659301, "0.978", "50", "0xba3e47b100a760f0a6e6659762b4979ee02a11d6d2f14ce409c2f97fe7b6352f"),
        (369, 1752663552, "0.971", "19.99", "0x9387655536b24943a8b534ea30f913a5a6aa8335092c3f4c906234fec2997a2d"),
        (370, 1752663552, "0.9718931068", "103", "0xf43cbd54f4a845aef5bfb10a90e67dd9b38e3666d66dec5a3a0372bb44c83a00"),
        (371, 1752663602, "0.964", "1.72", "0x44947d3fabfc204c2c003a4be96c623b061e5ff1fa82a11835d45f82d87f1fd6"),
        (372, 1752668470, "0.97", "3", "0xb75a136c8fe38156674c083095edd2cdb3ee246d3251679a404d7fe84bbc5324"),
        (373, 1752668956, "0.97", "10", "0xb6d0e6e21c15771c8ba9a1ba04202fc8a702343c6d7a07e295681f580eed1f35"),
        (374, 1752669318, "0.97", "2.134", "0xb057d5fb16601b93ff584dd53d9e73ae5667bd17b40b23b2636c4610ce793c1c"),
        (375, 1752670558, "0.9699999998", "103.092766", "0xb3252aad57e8f254410062cca05a5e7d42eae2dea5b75015a662a7a367e135e5"),
        (376, 1752671336, "0.97", "90.05", "0x783095b7dd7bbce7a68fa1f637e4c57ef03922fd45adf962056f739f1576c812"),
        (377, 1752673280, "0.966", "750", "0x5bd4ca06af75a1abdcbec22859fec8d1d02d7321d82c55ea1b48e13e838fea79"),
        (378, 1752675230, "0.97", "29", "0xea718bbb95e122b5a66d5a482f7ff4c3968323f21e9815b39a0d2a26b5939fea"),
        (379, 1752686268, "0.9689999415", "10.319916", "0xe84f1ae6662fc2ca7384268289c985f613aa3b06531447d63691d85d8a1430bc"),
        (380, 1752690608, "0.966", "80", "0x6f7a7eaaa908f2120e5e8098c41c772eab886d580b476d45a20222d7340fc735"),
        (381, 1752691172, "0.966", "30", "0xd6971f7287c23f8ee81d05b73ff7ff8531e7da58885b23841375fc66679a3a77"),
        (382, 1752691928, "0.969", "16.32", "0xdace992b91189f581124b2c84970b1c47981f5b54a0859de41abe2c0e4de8da1"),
        (383, 1752691934, "0.969", "13.36", "0xce8927cd7ce31982f54d869851333586359289f8f89fce193b0e118cde8404e6"),
        (384, 1752691944, "0.97", "10", "0xe2cba55a4d0b3f7adae4438ae8874c3998acc548dfacb99339d24eae17c66b0b"),
        (385, 1752692078, "0.969", "50", "0x4fe5328d3ffc4828a40f1a09a70b5b9bb2d9809a9306f11d330bdfb1f1bdbb30"),
        (386, 1752692228, "0.969", "203", "0x1950105322327879434f35a875b9e514ceb4992dd0ea6ad7ce92fa5c1ebc6b82"),
        (387, 1752692230, "0.969", "685", "0xd474e9944da86a6a29e8f6262d6841afb1c6da6693f9ad5ae3e2b751f09a5d0e"),
        (388, 1752692586, "0.970849", "1000", "0x7b380320c5b4eaf5723b4efe7d77e1e0e522a247435b7031b8dba7795309621a"),
        (389, 1752693556, "0.9699997866", "1.030926", "0xe186bb7f9288bbe8992692dec503487c0b3a3ff98b8f7f890b119dae3edcda7f"),
        (390, 1752693584, "0.969", "1.03", "0xde59e67d345db0e6e30372915b3881c0ac746efa74589636ff3ebf21d2128f16"),
        (391, 1752693602, "0.9699998081", "3.752576", "0xe3082adde3201276c6bca17eacaec1557d7a380ddaa9b8182ed6170471d5a5f0"),
        (392, 1752694184, "0.9699997866", "1.030926", "0xd77f17b2a4dd104ee3baceba9244b90335c8fec74ac018ab85e72a5081e26abf"),
        (393, 1752694388, "0.969", "1.03", "0xa9eff6c229d3d68ee42ab71119bfe630a7e99eafe7b5b1d7e752851b8d394233"),
        (394, 1752697952, "0.9706333333", "30", "0x908ba389618f379eac0157dd1d734ead262eea1651e1ca775838dceb00964cb5"),
        (395, 1752699024, "0.9699999968", "6.185566", "0xa2c6861131aecc45602ca6bb0c9a39be971b22ffb942be164cfe8e991ac89961"),
        (396, 1752699894, "0.968", "92", "0x5740a70291e41502dace98fb5087ca39c95564bd81998290fef3b3140bd4e733"),
        (397, 1752699896, "0.968", "95", "0x3b4d38a6b952570a8600de2fdddcc63f6722d2218e9e7fa14616bd9d4ecd9bb4"),
        (398, 1752699980, "0.969", "12", "0x131344a33a649af3bd092e79b4c756f69e369192f84a45c04071f2d204862146"),
        (399, 1752699980, "0.969", "19", "0xfa2897e9bddccf49823da208cac63964ac456bda1567f5802ebe7801c955a9ad"),
        (400, 1752699984, "0.969", "7", "0xdd7457f25b22e0d5991f25ce3a87db0270f8de128ccc8dab2f2cbe7019807852"),
        (401, 1752700008, "0.965", "38", "0x6fd04e9470723a40e86de31a7eb5b454ef1dc6086e9142839d607f7e65394e3e"),
        (402, 1752700258, "0.9708414083", "619.2", "0x321030aad4023c4460ec86fb676e3060f90798b7a101440b63899e0cf873217a"),
        (403, 1752700332, "0.9943351955", "89.5", "0x38c9574ed3b887e72aba9ee63c317801595ab5557f0dfbcab629daedfbe7b5bc"),
        (404, 1752700388, "0.999", "992", "0xa37d8defe982879be1ed7bcca4f5c1d86f197b446078f46a3b429e05c238cbd1"),
        (405, 1752700502, "0.999", "1240", "0xdb873409e1307eb81f34f04bd763eef467dd86be78addffecaf890dc6d679a50"),
        (406, 1752700716, "0.999", "39.99", "0x2c118fdf4431c9870a281d7e2dcc65069b736f1d3fc65b36ab155008091b9cb9"),
        (407, 1752701674, "0.998", "3066", "0xc45149c6d437924bc2d282473fb21fc31b2a39a488d716a7dac16d5f4d22112b"),
        (408, 1752701680, "0.999", "148", "0x8cf0b498518ca109e5112aeb33e80f20a1ce96ac0b126266cd10c04e304fff7b"),
        (409, 1752701716, "0.999", "148", "0x72f76f32e2d9d33591c601951afd1cec92effec984c066ea9ad7517ed6966316"),
        (410, 1752702126, "0.999", "3266", "0xdcd40d5e29048b345914a2730fcbb2964fe4f9903d6d7754495cf9f8ba208636"),
        (411, 1752702630, "0.996", "95", "0x136cc059195a61e4d8d18f989ef489b825a1bfba3471cb2a995e66a93038a7bc"),
        (412, 1752702692, "0.999", "420", "0x33d1de3c4871181ff35a4e395428a1f640b2e2b372ecb58d4a0244eb5e0f9e1b"),
        (413, 1752702710, "0.999", "6.87", "0xc523018f3f2de713855b5afe91ab80abf39d6dc2b34cf7f7933882e9aa6c42e6"),
    ]

    fileprivate static let retained563324Yes: [RetainedTrade] = [
        (0, 1752508335, "0.1", "10", "0x194b5b86321983afd651e21fefd8e169113922dd83f1fff76d75716bbcef02ba"),
        (1, 1752509472, "0.1", "100", "0x0c40b91bba65b05b95f19b0cfca884cf4cb9390c9f77ff1be554a81c094e6bd4"),
        (2, 1752510380, "0.09", "1677", "0x8c48d1d45f2bbc741e504e1bebb50e67bb3119406284714adc17155c3e939072"),
        (3, 1752520513, "0.08", "8", "0x3f77b8b5382a9147effa9e1a3b8ce93752f3211f014613d7a02da93e928a04e1"),
        (4, 1752521751, "0.09", "100", "0x4510b1b1b5660698672dd90c49438f84dcfdc05b3ab14a4873521147940c8d61"),
        (5, 1752521961, "0.089999919", "11.11111", "0x54cee195676bc0d0ecbf91c4129cccfc9f0e500bb5813e2868eac07075b93c0f"),
        (6, 1752522185, "0.0899999992", "1111.11111", "0x9241ee6944307b7705cfaa66535a080256fb0cfd45dd1651c05f34852e3a472a"),
        (7, 1752526704, "0.09", "1177.76", "0xe7095f21a68734b145c277de7a15aa3c4a7dcb38d621d364ba31d8b70ae95481"),
        (8, 1752529495, "0.1", "2000", "0x18545e4cf65dfb0296f40fb514f67cea1ce7807233c23fa52ee4f52a0f5667e8"),
        (9, 1752532275, "0.1", "60", "0xc2df68d67091ba1fb01b76f90fd484eb885e558e9728d530677e2b0a3fc89858"),
        (10, 1752543219, "0.1", "2386.37", "0x73efc794d156aa62e3de7d7786cf88bce097a7b0df333c0d70ae558a6daeb1ab"),
        (11, 1752545815, "0.1", "11.63", "0x1036550def378fe4be4be2501397321f7abf47549143a741b2f777fa8b09a87e"),
        (12, 1752545815, "0.1", "21.63", "0xe8f79b87844c80e6bd8512741645ae0bf79be7ecd40dec827f4b196528884810"),
        (13, 1752545823, "0.1", "23.25", "0x21552068bc3b58156592222481b1c345ee4f0c8a53b20736af10ed7b1d01d611"),
        (14, 1752549787, "0.09", "5", "0x56211f19cfff555e25fe370e2263150a7f50f63345d0572c411fe68d9f27587b"),
        (15, 1752552377, "0.09", "5", "0x68865c26df97ed17d97d03fb650d115c0b6b30d02396efd47e0935456395bc82"),
        (16, 1752552389, "0.09", "3.01", "0x2535e00e7bbd657ad7a88fbe790a2a65cdf9ea23fdfcfc25e5dfeeb07e656845"),
        (17, 1752552401, "0.09", "3.99", "0x544db22325c4b0cec8f2989c88f83c099085270f122d2109e1ce024e103ce984"),
        (18, 1752552403, "0.09", "21.01", "0x363c4c4be9fe7880ed5aeb192afebb78361b259ec81ee7f31db527af0f01a50d"),
        (19, 1752552407, "0.09", "5.99", "0x3d6e610c16a8910cf85fd9ecc71ebf257424623dd1e246ef48567a6601579f1f"),
        (20, 1752552411, "0.09", "27", "0xed87f3ba7251aea20e43af17f08081355effc17ccda61641194ce1670ff3cb69"),
        (21, 1752552415, "0.09", "11.01", "0xa2aec9ed8f98dc0308f4c4372bc42e7f5d3d507678ab671eefa84fbeb6ab6176"),
        (22, 1752556469, "0.1", "10", "0x147e999e13b5ba2f686b776cc265f105238943ecd47c92ca9d8680d096ec0973"),
        (23, 1752556659, "0.09", "228.63", "0x624f7473e30f321dbc606a012cddefbf7d4527955f2b5b2baac7fc24880417f2"),
        (24, 1752566381, "0.09", "103.83", "0x8f8aeffc7056649dda43f4bf3ee54efae2469e0090435c7dd755f101f8a1faff"),
        (25, 1752566702, "0.09", "25", "0xe2d9e715be20dfc48965e76fc8bb6a0360333df688ec7899f84d9c3f1da203a9"),
        (26, 1752566750, "0.09", "22", "0xcc787ce633e3978ef61d79b7b4a81b8a9102c0ef1fb35310c6762aa8225f13cb"),
        (27, 1752566764, "0.09", "11.66", "0x803c7447cb3f421825966cbb106ccb70732915ddc36197d4e52a33279d78d854"),
        (28, 1752566814, "0.09", "206.62", "0x6ac3adcefdb069d2096d4f7be54d53bcef5ddbda40ca579a58ae25b7b043cb6b"),
        (29, 1752568522, "0.08", "1.91", "0x691d90baf27dff365dd962f5a6a63c1e14b6b8a1e641db76d3f1d98c35ffb264"),
        (30, 1752568714, "0.08", "5", "0x1203bf43449d3f49b1804efa44e205dfae944d3747fa4ba3d8e159728c28c85c"),
        (31, 1752569809, "0.08", "10", "0xa79ff989093f17ff935aa6ac80a09e659dbbf3850d76f7b50811e87c106ff700"),
        (32, 1752570643, "0.08", "223.09", "0x0657d1eb1650f9ef581819c717ecd7c95b24b347b82b3379b2757948f4fb05ab"),
        (33, 1752570829, "0.08", "240", "0xa38c870cb1959ea78cf70663b01ee48d723b1fcb04610e9ff8d3b3f630b5cfdd"),
        (34, 1752570865, "0.08", "5.28", "0xea5d1000e9b3dfd31b523b4eb6c47d29f55858e7c387148fda0ef1909d2d9956"),
        (35, 1752570867, "0.08", "195", "0x31c33453048b020a1ca2a9d330924c4452852b5267953d425690456cb05e99b0"),
        (36, 1752570869, "0.08", "39.72", "0xd85fd6c6b08e4cf73069b2d9c564af111040790def622353c6582d290f7faedb"),
        (37, 1752570989, "0.08", "240", "0x3fcae91798239957172f3515412c0580c30c9fcf6107d7aa74100413ba04462f"),
        (38, 1752571297, "0.08", "45", "0x023aa41083cc88b414b6a48b2a0d83ca02912c0a75a8f02dd878c06437476d89"),
        (39, 1752578907, "0.08", "1.41", "0x3ea8034f77f0d9a835b3187b65dbb7ddb5dcabe3d72537c3dec69429e4b699f7"),
        (40, 1752579313, "0.08", "18", "0xce3daf65a4eb48a648736409dc0df66d658e1470f9b9628ad3a1fcab7a5c750a"),
        (41, 1752584899, "0.09", "100", "0x952510312ed90ffb88cf2bcaba8a167f9319ad3938e625d04967a94079b5788e"),
        (42, 1752587043, "0.0989834566", "1082", "0x1a03eb4d8b62f8374317c85d207a11624972d135edb2ea9fe84217b58cb68632"),
        (43, 1752588081, "0.09", "3", "0x926a2f47743a7c0b58f29385370f175cfe423c2bff9e755798557d7a560cc769"),
        (44, 1752591159, "0.1", "151.97", "0x9dfcee8fb4e539a67c30587ea4e7d7ccea73fca1a6b5b5c34caf3391666e50eb"),
        (45, 1752591263, "0.09", "26.09", "0x400b646d8b550c002016c330d335d2b7f06ad2fe3e503f8458b084cabf225321"),
        (46, 1752592750, "0.11", "100", "0xcae61f7bfed8597433874199c0cb0904ba995cdea3c7c7ff7b50b19d307b5a17"),
        (47, 1752592904, "0.11", "569", "0xcd1d4fd6307c5d7a805695c0e08861ebb47ca6675057116391276bff073a7525"),
        (48, 1752598504, "0.1099999815", "45.454544", "0x149f1aa6e891436bd9fa74759bc726022ce30efb3c88abbcf6ae7f9b7b61dfd5"),
        (49, 1752600751, "0.1", "53.6", "0x7b930b999a3a9da88b5b1261055c74244df35e42fd8638a3f4cd415fc110d0eb"),
        (50, 1752603351, "0.07", "5", "0xd10d094fece05eba03746a5d81bbe144e335cccf2800900ffafd990bccdda4d0"),
        (51, 1752603429, "0.07", "86.99", "0x8dcfa7101c55cf6cb6fe9d4c262110627f0ae9ff1c021095b7eb2abc42e5e826"),
        (52, 1752603796, "0.08", "3", "0x279e0d56e603d02ccc9d5951fb786d6fbc1c0b20c79f6cdfae6de224d9447645"),
        (53, 1752605692, "0.08", "120.89", "0x165abb0b9479307d7c5cad501a3740cd00a8ba2009c94b46d1bf499f467a673c"),
        (54, 1752605766, "0.07", "2.96", "0xa979c98c57bc30b06b0b6ff0c492ecf7c5365ccbfa1ae04f3e953c43c855466c"),
        (55, 1752607258, "0.08", "200", "0x066b8648ed96ec67ce205d2b5b7b5fa92dbbb4c79d6f0bd27b0f98d9b9a62877"),
        (56, 1752607318, "0.0886340597", "1128.234443", "0x30f14b3218b544966e63ca5cc174ea11cecea38f218fff551d173fab87ecb947"),
        (57, 1752607442, "0.08", "130.125", "0x2ee924b34dcb4c93e6080debac04b5667951ea77df9045f2c6ffdb8564482951"),
        (58, 1752607556, "0.08", "687.11", "0x0e82d3a62b34e3bc793d77e98b0bd8c3e0e2e122aa5be845865e9d6e0f1d83ac"),
        (59, 1752607556, "0.08", "167.24", "0xb4cb85ef1a06b8ed2053d491fbca4dbb716fd3644335a300da07aa6ee9c00e38"),
        (60, 1752607578, "0.08", "8", "0x017c8f1e09550fac98b3152fb4a96af8912bde91bc38ee3778abafda035d9285"),
        (61, 1752607582, "0.08", "5", "0x6bcbe35d84fcf76646915ce0ff174474979017e3e597f0d5656a66a450d3cf4c"),
        (62, 1752607586, "0.08", "24", "0x031dd8a44b3a76a10591097e96ba0563dc6e7123a82bfd8bdcbb1a3fe1345a6d"),
        (63, 1752607990, "0.08", "165.03", "0xad2ab0307d9bc18526899d072593d63b5125a08e337b310cac1d48579824f0a0"),
        (64, 1752608596, "0.08", "209.97", "0xc52b882524cf93d7b5ac5499445c84e1060d748539c3896fc3b969bfa6c5137f"),
        (65, 1752609236, "0.08", "10", "0x4627b257c142e158b0013adc35f3fad72bd982e5ec3c637db45d391765188443"),
        (66, 1752609704, "0.08", "5", "0x7137cbac7f5e43d520ab07e3dee815f599dd55da74f4b438f4ea86533d8758b6"),
        (67, 1752610958, "0.07", "9", "0x4c3f710e5d0ab0b82788469b634d51b7350994e1eb4a68cf6f8fa4ae2ea58f80"),
        (68, 1752611310, "0.08", "12.5", "0x1695ca09136ed8073a2d4c9665f759cfba6ee958be13b8055b24b909867c5fad"),
        (69, 1752612409, "0.07", "5", "0xf325f9c647a6ad59c2668ff2d27f7ce6b3b6e9b13ecfba518ffe4a15a9403b0b"),
        (70, 1752612665, "0.0899999931", "122.666665", "0x548022dafc60979e3c5e31a2c1b19f6cf386950f8e8776629bba122006dd98cc"),
        (71, 1752614057, "0.09", "40", "0x65081f363e80c7ab2f93c5c5b31bd662b26a5e88dbc13acaaa7e04b9dd07577a"),
        (72, 1752617377, "0.08", "100", "0x57ffb3563b9e45555d7272912c629e41f76d9beb48d542a52ea75cd1f28aa04d"),
        (73, 1752617563, "0.0899999599", "22.222221", "0x08707134a3f17bf88fa4a5b8e12d60c89afb26572c0693daffb003d06687b983"),
        (74, 1752618493, "0.0966329966", "59.4", "0x63b65a2c37f15b3002342e4afb147c867bba91c2031373b7bf241c17e4293ae2"),
        (75, 1752618787, "0.1", "20", "0xae47733d6803e28e0408fedb8bf6e522b9781e863f8b0967dff3cc4cdd861bfe"),
        (76, 1752619263, "0.08", "494.99", "0x550072cb941fdf97762dfd859fa39cc31507dc0053d12878bdf05b31169394e7"),
        (77, 1752620491, "0.03", "500", "0x8b9f402c024e99355c6e3f1ce6e51f4213216cbbfef637e4c72fc3dba87b9e93"),
        (78, 1752620611, "0.03", "300", "0x4e0b7c0fbe12d38aa0043841ea5186563284921f3c21b6b88d9a8f65f254abbc"),
        (79, 1752620999, "0.0292462", "5000", "0x31ccba36236ba3970f5153681c71267adfb5512b1f433c33cd11456ec5d1e6d1"),
        (80, 1752621027, "0.001857102", "34.99", "0x4dc1ec1e5fe1064b5927398aaf7eb2bd2afff25affb73b15b243a9ca6d09a598"),
        (81, 1752621059, "0.001", "154", "0xee82e70f09c5b4484ac61bcfa7a8cc5789527a520fecdbc3c3142f1fcfd91b37"),
        (82, 1752621071, "0.03", "3000", "0xd18ea39675f869d7d23e5991006471722504bbf404440f1cef09b0d3d18a06e2"),
        (83, 1752621465, "0.019", "154", "0xfb5115384fecbfdc001e2b11c66a81888d4714d0c06ed1e3c05c63abb3e883ae"),
        (84, 1752621567, "0.0139705885", "71.578946", "0x6c79f0c0998f42793eccf94028a8e635f125d6b9be447f5f3f08727fefcc8733"),
        (85, 1752621665, "0.005", "211.01", "0x7c84d31a538f080394907a4835db573b68e627b1430c971e0ba0a4fb9be3d0f5"),
        (86, 1752621865, "0.001", "200", "0x527b97f4be109a2ffb2f54019f03a0fabe7040ee1be553ecb7fde108c6e17a0a"),
        (87, 1752621959, "0.001", "200", "0x22dd9e072946a18d368c13fcfb296d253319c7398cc92f7ee0107664c9c464ec"),
        (88, 1752622313, "0.0022613065", "1326.666666", "0xd5d674f938ee63fbeb1903b9e2cb15294a613d7e3afc82c42e0e48187d5c1d31"),
        (89, 1752622535, "0.0039119804", "1022.5", "0x77f565bc33b5e7574374be92722ed7b8c74de0cd36645dc7495cf10b5c7f6c75"),
        (90, 1752622727, "0.004", "250", "0x456ff61eff9c5949390fdebd5d3a6d86c44df997c77ba62496dc256cf5145024"),
        (91, 1752622745, "0.004", "2475", "0x98d32b998e558170e9926bba298de367d5db54a9845c026d8dfe9a38047a350d"),
        (92, 1752622803, "0.003", "1000", "0xf2f81dbb1ec5cae191caf0b66b2e7b00dee5bedf1c4ab8c830c67959a7aefaef"),
        (93, 1752622835, "0.003", "360", "0xff21b52c7018e5a9ba27b87d551723af4e0102046a07996b8f696b7df82df8cd"),
        (94, 1752622845, "0.003", "3000", "0x4a25b9f8517b981fb1becfbcc1feb5c57683926e9066df847ec7260fd3886c71"),
        (95, 1752622845, "0.003", "1000", "0xf8efd4294d97862bf06093fdcc07e04203870ea40b387d993c64b3f355e48ddb"),
        (96, 1752622847, "0.003", "1000", "0x7bbe6c40d1b9bedabbaddba032e6a93db91f86084f51f09d7c687d75a8b1ecda"),
        (97, 1752622847, "0.003", "1000", "0xa408b5f7a8b1316774b5c62dcd30a80c52efb6d75135f4c768f0ff0730de05bb"),
        (98, 1752624201, "0.001", "16", "0x4216348fc2fbfae8418f0b48e814dd4c8b1a001a96cf403ef7ae386b6192bc31"),
        (99, 1752624333, "0.001", "16", "0x01b7c2249572e2dd0912186406165d355db539ecd2752c292ce47fbb1e8b4a11"),
    ]

    fileprivate static let retained563324No: [RetainedTrade] = [
        (0, 1752507997, "0.91", "500", "0x3f3380e3015a505b8158096b6dd8e34d7c8ee5992bad4998d41bd70db6524736"),
        (1, 1752510124, "0.91", "323", "0x3991990e591ed46bc72a6311ff74605fe7cd7f38c440bc0b7f41240e19348e1d"),
        (2, 1752516056, "0.92", "10", "0x53c929749916d376a8efff14d11dda985aae3ef7688e78f70744a0ce4252a3ed"),
        (3, 1752526754, "0.91", "827.24", "0x3f75cc0148ebac5ce9f821922a6244fb8d4c1471a7e8669b9d21b6c5f1bfa4cc"),
        (4, 1752528123, "0.91", "2.1978", "0xd900b83ea1f68e385916e98164f0dc747417f6db6a712d93909f7a300ab962e9"),
        (5, 1752529547, "0.91", "10.989", "0xb8797f0d728bedf1b5c217de200649adbee21b151c180e3d804a11d247bd45db"),
        (6, 1752531497, "0.91", "105", "0xd9178254a5198ef958a3a06d98f221328fc367f02ef2bb27bca4dae375f9f615"),
        (7, 1752531593, "0.91", "70", "0x23bf23fb04327695df4534d4a1d0cbc7f1dd67cee7e2c88ed7e5062f4ef77ee7"),
        (8, 1752531595, "0.91", "75.2", "0x77a9b60bfc4c5f875088d7db7aa1e715a05f376331fb605d01fbc6f076febec6"),
        (9, 1752531597, "0.91", "1.08", "0x57e128968c830233fe508a231f48781faf51fa1510c6ab5b194755352bc283a2"),
        (10, 1752538679, "0.91", "10", "0x432533c7420ae0b0057cd07b320665a3ca53663a8a52c5f89aa54d9cf7a8f420"),
        (11, 1752543221, "0.91", "1.08", "0x47caa562d8b1f67e40c8e03d1475534a18216363adf11f4169058c15ceb5f005"),
        (12, 1752545819, "0.9", "1.09", "0x1f1d091c9ab80177a080dbfec257209fb5a687568235869586f9450279375497"),
        (13, 1752545823, "0.9", "44.88", "0x1b6c1ebaa1631fd819c7c2f1df7abe72ed4c976abba8793a3376fddce91bec2c"),
        (14, 1752545825, "0.9", "11.63", "0xae0b6de9109e50926a9a895044a28a666656006f07ae949e778e499dcac69cf3"),
        (15, 1752545827, "0.9", "1.09", "0x7f47d9dd022a1c040800b4436d8c497415832d71c76c54111eb883c0ad37ba7c"),
        (16, 1752545827, "0.9", "16.67", "0xfe742cea3e701254220d722e523fb4b92c89c78e13e6b19fbb7beb835361e38e"),
        (17, 1752548828, "0.9", "370", "0x97fef20cb160f174a6fcf401b40efd589789fb643b8e0ccaf46cae4633734b00"),
        (18, 1752548828, "0.9", "3.13", "0xdda06ec6dad4224544900549d2e3b99a1ddb7da40ea694228a0058f592c36c92"),
        (19, 1752548832, "0.91", "20", "0x6e194a854fd4fb869b6dba4c591a8a2807b293c9a9a9ff56bd9f03c69b8ea68a"),
        (20, 1752548832, "0.91", "1.08", "0xcbfe050e2b71af089c3196633a0d2b03c6345ccaf38033e2a8c4161a97784c82"),
        (21, 1752548834, "0.91", "20", "0x7c2d0ef8361951c1c12328737dc216e88db1aa367e593e01e15ed17b3639bd31"),
        (22, 1752552353, "0.91", "868.32", "0x459e297f7349701b378c3f45d07366f99a931063b128d1c8d41010dfa3bbcaf6"),
        (23, 1752552353, "0.91", "2220", "0x774fe8e46a07c8906382fcbc355fea025cbf01ea5c4baf003432737a57df8179"),
        (24, 1752552357, "0.91", "1.08", "0x687f034b50b31a9e655ab9b7eca8780415c7688e486d7dce50aafeb3f4c26b14"),
        (25, 1752552375, "0.9099999979", "14.164833", "0x1ab5a279d2b2c1caa6ac19cc051807551de1c84cd42f6e67f2e10ff6aaf2bb7b"),
        (26, 1752552377, "0.91", "21.99", "0xace3dacf1a4a19231af070372e088e43fa223948ffc292f78383f3250097124a"),
        (27, 1752552399, "0.91", "25", "0x7ca3536f72ac06d8ae5209af97db6d849b3b1b31e305fd7191115c6ed7326717"),
        (28, 1752552431, "0.91", "9", "0xdffd5c920159ea88ae024990c6a1b031efabe56e43451b4c70952934fb0c8e85"),
        (29, 1752552435, "0.91", "8", "0xc3ea6fb46090941c5c61a5af6404c56f65dcf65628f76e9913915ff8359ea174"),
        (30, 1752555149, "0.91", "37", "0x383bef92da246d3743d2c24ec64fe6b4febc24379982984193f25861249c7d47"),
        (31, 1752555149, "0.91", "30", "0x3add09261bfa57c352bcbc6110698a0d5cf74af85566c2477f4a2144a876fc5f"),
        (32, 1752555153, "0.91", "1.08", "0x2e50d4b9d78568454dff15837c694116e97db60156411658703ae12eb33d5d91"),
        (33, 1752559303, "0.91", "66", "0x0aa148c77ce44b79c0603a36329d15c2d101c0ddc45f5ec992a6efb53b98e82d"),
        (34, 1752559647, "0.91", "100", "0x9998ab92e42f1e33a7a188d4f10bb11707b486a8327fce40b72798cea49ac1c7"),
        (35, 1752559651, "0.91", "1.08", "0x0a3dea60a32cfa0fe74e20aa1961e0ec0b48f43b6820a2fd4d9abe575604fbdd"),
        (36, 1752566345, "0.91", "9.21", "0x42097929beaa974357adaee5aa11e1b6576fb70c323238cb0537c97247276b9e"),
        (37, 1752566381, "0.91", "39.99", "0x2944391d3e4800abcf9e71fe587ad55db17a62050a0d0978b743ee16b85e3eb1"),
        (38, 1752566381, "0.91", "66", "0x34729a74ee2efaec9e788f14bc299698698e4a6ea27f8fc0336256965dc7de07"),
        (39, 1752566381, "0.91", "30", "0xa83ab33034b6c1a371537afee2f67e49350217fcb43d65ac5594f2571eec94ea"),
        (40, 1752566385, "0.91", "156.25", "0x01e8adfc420f0d99055adcbe11996341af253b6e6cec858bf899612d9fb246a5"),
        (41, 1752566385, "0.91", "53.75", "0x4ddfd1b85cb5825540246cdfb26b0cd55dc8eeac6fd0ebf3ebf0cf66c59391fa"),
        (42, 1752566385, "0.91", "66", "0x6c4525a80707ef2514c0c52c82250dd42938aaa3947e988f54e037d9c425b2e7"),
        (43, 1752566385, "0.91", "1.08", "0x6fa6ecd3f70ffb89e813e5827dae99d6b5ab42bcde55bd568f34c8faf83e399b"),
        (44, 1752566389, "0.91", "1.08", "0x4420979aa19699a532911414035ea360facb3b8f6b2fe529b37c2c5f54537a6b"),
        (45, 1752566389, "0.91", "1.08", "0x5870b58760cbf5ef432c54b9cdbb7cf872ec690ed4886909da1b29f092925f0a"),
        (46, 1752566654, "0.91", "40", "0xa3b49f9a0a32857b45e9f3196098f995b57a9b16dc9527318e21f0eb1afeb6ad"),
        (47, 1752566658, "0.91", "40", "0x4f9327c32ac180c57f0a614fae5f7f941e49f1c34b0d773feba55f9e396992f8"),
        (48, 1752566658, "0.91", "1.08", "0x552dbc32304c1a7c936974dbb007ddcdc975bd98853a043b02e84295fb141cbf"),
        (49, 1752566658, "0.91", "6.25", "0x874161f0cc0ffc3ff76c1c5bc06fe4f909ed1fdb38c44b4d7381269301e421fa"),
        (50, 1752566660, "0.91", "6.25", "0xef95ad2743a5e2dd46ad6b82ced78a2c286f325704699f33ece3ec46d0f2c816"),
        (51, 1752566702, "0.91", "24.99", "0x610c69d7d1bc167568d3ce74af764de0e05b827fac81683908e213c4faab5736"),
        (52, 1752566730, "0.91", "18.05", "0x328265c43e2685d59dda26ddd8ff76902a6aa82587c74a8130db0bbcd67f23b1"),
        (53, 1752566734, "0.91", "25", "0x152b40fc5728f3f3394a25fc53984850a44a6717e7300f7f9e43b3e948c2b651"),
        (54, 1752566734, "0.91", "6.25", "0x4557f9a24288225492786f0f73063fbe278f20876e6acaa2dfe0c95d301766fa"),
        (55, 1752566814, "0.91", "102.22", "0x59c83f3fa8fff9ea78e83cfc1e5e67dc761da823a60d50e1329bde3d1cf7d9e9"),
        (56, 1752566818, "0.92", "12.92", "0x28b89a54e4c59f8b869cd0cf32b6a1a7e3c1d9647bd73f9cfaa3a63eefdca802"),
        (57, 1752566820, "0.92", "5.01", "0x174afbb0217fce05977c74c2c9359945250a6579a4aac9e8d494b3f0d8839fdb"),
        (58, 1752566820, "0.92", "13.33", "0x5327b319073ccf287becb90ca5a0c3cd5683790dad99fd24ff842edbee66ddc6"),
        (59, 1752566822, "0.92", "5.56", "0x99a573c68c07453e6b4e0a73c29253cc9b66708c8c890d04f2765e106ec6878b"),
        (60, 1752566824, "0.92", "5.56", "0x4ec55c40ccbfa75d5bcada816b1e6b0fb38cca6f18a61ae6a784827d2d470bf4"),
        (61, 1752566834, "0.92", "27", "0x12b37b88e7391f93bc227062d222865a8fc32ce0d04cd9350b51e412485af587"),
        (62, 1752566848, "0.92", "5.56", "0xaf1310f3924b2626e77e4f54589cae8912067b96f4fb1d079a96873a74a25c86"),
        (63, 1752566848, "0.92", "27", "0xca51a071b8d677cc2bf3ca66e330dc300d0d2a309f400ce130e90bc663e6543e"),
        (64, 1752566860, "0.92", "27", "0xfaed942c8d57a22f494665980f3ebcf23e50575e2ea49e09f9259314a383da70"),
        (65, 1752567078, "0.92", "31.25", "0xb984cb3341507dac40eb7e7b671fbbfeb6b1c9477a811ffafdc5e3714a295f26"),
        (66, 1752567933, "0.92", "70", "0x406505e3b18590fe62a428f5bf55f165d33bc9b6c55b3fcd73a681651c032c78"),
        (67, 1752567961, "0.92", "15.28", "0x0c732eb5dca35e966399f2cb0891462ddfe0d74ed9655b2a7abd8612300b0bce"),
        (68, 1752567961, "0.92", "66", "0x9d076a1b19747d72b5117d42954deadd8a90a8395826302a400031e0bf77e887"),
        (69, 1752568194, "0.92", "23.8", "0x7fb7f6b5027e0b1076a1466261c83ae1ff258871c8e4bfcc02f210e8ec97e5b7"),
        (70, 1752568198, "0.92", "13.34", "0x7c351d38b152332162a0113497cfaab56b19a3544f361648233213f7eeffab08"),
        (71, 1752568202, "0.92", "11.12", "0xcf32710cf1e081263ea7dd73e1efb745160193951b11251a646fd0cc2edefb0e"),
        (72, 1752568512, "0.92", "510", "0x6a5a6cde6fb832afe60aae9d7d6242b680290451942578147a03858838f9c2fd"),
        (73, 1752568576, "0.92", "30", "0x06587d50e5ba5f1232c94fc6d47ff4fb35ff0f88ac20ece668243c0094e4c3f7"),
        (74, 1752569695, "0.92", "6.66", "0x6eac6d2e5068e182959707e20d98f2506794b0d4077ef5a0fd2608493da983c0"),
        (75, 1752569775, "0.92", "66", "0xc8592b4452c4fad489a42e310eb160c29a59c227841cbb706908b4dc8a3b7685"),
        (76, 1752569779, "0.92", "14.29", "0x80459d51fc6e03ff76c4e7503c48cc414fb27e83935f795b97cfdc80baa0ac6e"),
        (77, 1752569791, "0.92", "190", "0xf6f46da81fdc4b2c410fd1f26d2b21389552e6a5dbdccb5fbca4cc1d55197fea"),
        (78, 1752569813, "0.92", "5.56", "0x36be22dad53712df53fb2dec1f69e9f8f08e59e2824335fdad5d714a7cdd29a0"),
        (79, 1752569813, "0.92", "13.34", "0x89300f0c1b3b040932a79e619794e529b022ffbfa0b18dea1b274e6d7ac05fb9"),
        (80, 1752569817, "0.92", "5.56", "0x9e146bd846eda0c5f9539ec2f0b7d2bafd176cd9dce2eeecbfb0856ac39a305d"),
        (81, 1752570167, "0.92", "170", "0x5bbc8560ddd0c85486d2a6211c123650fdae0bb1789ccb4fe51bc50de6f31814"),
        (82, 1752570167, "0.92", "15", "0xb7f9e135e90b4a2a59e1607fba6dc02e873928630336b38aa890e0e4617243e2"),
        (83, 1752570167, "0.92", "15", "0xba24d3afc12126efa2ee54a25c9bdd42c18c1dcc31221526b48a7e6a16c68726"),
        (84, 1752570167, "0.92", "66", "0xfaeeb2f477f4ec7d2d962b95b8c77027fa4ae06456585334f1177250f3d1449f"),
        (85, 1752570169, "0.92", "173.19", "0x17ac47b260f2fcf6982aeab5c03d40053597b34ae5a89bd21866c18a11109eee"),
        (86, 1752570171, "0.92", "5.56", "0x0d783be5b00a57b32852f05b3e2d1edae73b462dc6b6605fd6e233ea11fc352a"),
        (87, 1752570171, "0.92", "5.56", "0xc1f17c9e7dbc9daac33270d845942feea53929eb0dcce4771b9705c8d8825132"),
        (88, 1752570173, "0.92", "16.67", "0x2f07adf08dd2a26c1ec5de6df7020dd50344d17c808bbc39ecf8eb08bd3ffe46"),
        (89, 1752570173, "0.92", "16.67", "0x33eb0c28ec17f3d91dd5762418e91adb18bbd586c7539dbf9a316155f45a7a78"),
        (90, 1752570173, "0.92", "5.56", "0x35e2cb34c3d4770b5ab67e9e10146b2d03927f2ec7d865d94d36ec7ba388fb99"),
        (91, 1752570175, "0.92", "5.55", "0x53a85e09f47976ed9c91054e06894ccea96bb0fc4cb74e57133b2c48b6e621ea"),
        (92, 1752570175, "0.92", "6.67", "0xcab38153692e93b1435792383d303ec9ca7deabd958e3d764552fbe01c735983"),
        (93, 1752570177, "0.92", "16.66", "0x754c1adfac7c2301982334daf2eb5429614c568acfb4ad54c591f5b24045ba60"),
        (94, 1752570177, "0.92", "6.67", "0x91b33816c41e3df9177ab7514b8769025bab04e91c7e61a1e1d1f7731237c7e8"),
        (95, 1752570179, "0.92", "5.57", "0x0036f5618d425223b482c9d17ecd0a334d992c4bf2c0951110e4204066e02250"),
        (96, 1752570179, "0.92", "6.67", "0x22b51683ecebdab91586fce3281bf18fc024d9eb2d0ba18b0f53b2d87d1fa785"),
        (97, 1752570179, "0.92", "6.67", "0x461264c3d118e2859b710e78fb1aaac23926954f9220fd47fb1fb15b80122a10"),
        (98, 1752570181, "0.92", "6.67", "0x23b297a377cc55ca6899f6281b70c0f2a7aeeb49a703a5b95b8f08df82c63764"),
        (99, 1752570181, "0.92", "6.67", "0x2c28dd441d5612fb667791421db72c717558ee0bd71aedd51b4e4f9c50e97ca0"),
        (100, 1752570181, "0.92", "5.55", "0xc2d8117e3935a6f1f57597a30972e296a0d963cb1a57331cef27b75f3089f5e3"),
        (101, 1752570183, "0.92", "5.57", "0x3daf230c4ae95c2923b5cabf6f57669d196ec0cb14c208d033d4fd490b53ff9e"),
        (102, 1752570183, "0.92", "6.66", "0x40de387da1742b6a000f6b0b20ae840ee27233f42cb9855b20fa152d791dad58"),
        (103, 1752570203, "0.92", "300", "0x6130c30d0c77d7586ccf5c75a22ae0d5e4e56ab09af2550fb6b2ae1cf38dadb9"),
        (104, 1752570203, "0.92", "15", "0x8bebe3e7229462578f2e4002f99f780bcc05ce2cee7a88b243a7c98f231c472e"),
        (105, 1752570203, "0.92", "15", "0xe3fffbebe89cbd07135db878c4504bc7210dcb5e0140359f7850bb70e6619c53"),
        (106, 1752570205, "0.92", "150", "0xceb0c1e1aa6a3f5e9791439c5a27a50c88a3e49a0d5e93f5ab66d525ae908cc4"),
        (107, 1752570209, "0.92", "13.34", "0x05cb41d31d911888a63a7df0513bf65dc331c722bd0c3ea34b0b55e54334bb51"),
        (108, 1752570327, "0.92", "66", "0x7513fae479cdd0304d9f4ae192ef684f1d0d66920b5466154d992419fe25b018"),
        (109, 1752570327, "0.92", "10", "0xb3cb9baf6266d46dcb0664f1655f244c98f8757a510f308bcf75b327da097ffd"),
        (110, 1752570571, "0.92", "66", "0xae10f091a7b943a89a79abadbc16fe68591d223d239f0caab2040121f8b92a5e"),
        (111, 1752570571, "0.92", "133.28", "0xdb80dc69ab9be58fa6f70d110c6e4f944dcea1581b89fd49f692fe2f80ff3669"),
        (112, 1752570575, "0.92", "13.34", "0xabc1746728bc40b3732ac120eba1ce9237618c4ec6393ca9d41e057f8eba9155"),
        (113, 1752570643, "0.92", "1000", "0x68ecac08da21ff540a6f983045b11d1f379d346131a56628c91ad75bb6331d6c"),
        (114, 1752570643, "0.92", "39.99", "0xcca25f3175cca1a75a403bfe4ffbe3f7703bbb294a5d0899b95ad9c9a85fec6a"),
        (115, 1752570647, "0.92", "14.29", "0x38258dd54dbf7fe628b47cd95e823d4a3a37f65dacd826521bc546f9bc0f8a5c"),
        (116, 1752570647, "0.92", "14.29", "0x71f3d55fdf5b0492be55f4e7018c544c6ea28fd2d3ce738f665c85714f7e7dbd"),
        (117, 1752570649, "0.92", "14.29", "0x92b26a0860e276041a70772689d476eeb49600699d43f17d1ac7c98cf0097732"),
        (118, 1752570653, "0.92", "20", "0xdafa78ab9cea053303d5d56405475da406f4edf197deb3f9a14f67c9a8d68ad7"),
        (119, 1752570827, "0.92", "329.94", "0x9541f350f707430397ce61e5175af00112e9b6341790c626427358c04f95e670"),
        (120, 1752570827, "0.92", "66", "0xedf276578719d703a0a28adfd20d212e218880297e2479d51201aaa8ad4011cb"),
        (121, 1752570827, "0.92", "39.99", "0xfbd25395c3289bcf82f8141eb60fb522338aa37814dfdfedbeae2fe32032d8e7"),
        (122, 1752570829, "0.92", "452.13", "0xec8c09c045571475f48c68134774b94ed6da28a4d17c9bb39b8f1ab0e9e97669"),
        (123, 1752570831, "0.92", "5.57", "0x96ef816c6394a4a2f3139e0d5f78033420c7b3bbd8398337bdf1562474766560"),
        (124, 1752570835, "0.92", "37.03", "0xbf9831e7695a0cb61925267d2ecd7f5742e90f9a4544979f6f3427d94c27e063"),
        (125, 1752570845, "0.92", "4.15", "0x08aae068219c069e1128edb46a636b4da1ed3c410e176a8d1907e0a762f7391a"),
        (126, 1752570845, "0.92", "5.55", "0x96d77e7dced2e150030739caff71bf9f96d3ec6f92bafad2d9a2b136ffee844f"),
        (127, 1752570853, "0.92", "1.1", "0xec86dab653f85bc9b4e351bed8512af922f9dffb5a32c0b931cd34e8648e3b39"),
        (128, 1752570855, "0.92", "6.69", "0xfad00f044363c7eb4caee703d6c8ca5bf354e21e4733fa03b9c765afca708e7c"),
        (129, 1752570859, "0.92", "95.51", "0xa7481ff0abe4425b45d088500047ade616dd346363ad0d16cbf0013ae2ad7f5c"),
        (130, 1752570865, "0.92", "16.67", "0x9a9144ad47c0f106cca91b6d54903186b3a6921764e034fb7bc1f52679af7b7c"),
        (131, 1752570867, "0.92", "244.7", "0xc5e652fe08ffc444bf60716d1a0f46e27ae752dd716bbcf450dd8d53fca568e7"),
        (132, 1752570869, "0.92", "5.56", "0xfd6f959c20068db6581019f51dff7402c8a06ed13f0b5480f1fb18896b7f7ea9"),
        (133, 1752570871, "0.92", "5.56", "0x1311c99116a6c21cb87df9db49450c4b752c07156155897dc13e263daff87816"),
        (134, 1752570871, "0.92", "5.56", "0x1d6db2664d3f1c1d706ed3ecee6fdd7ed08059a4483c7812127579ae07df4433"),
        (135, 1752570885, "0.92", "16.67", "0x06f303804ea75705283cac3db7b20c93bfc96445e83ac34349174c45a2710840"),
        (136, 1752570885, "0.92", "16.67", "0x0999dc1027262905192f7834e63d0ff00488d5cb4b22449aba97828c50c8d012"),
        (137, 1752570885, "0.92", "5.56", "0x49d5325d973e88e7e7a7aa6841e2a4c41e05bbc948b9498505bb3e6371d73c50"),
        (138, 1752570885, "0.92", "27.46", "0x73c242c1c9d6a904ca701d0bb5643f8b2ab8d9d58fe0b3d99d8c3d5a88749399"),
        (139, 1752570885, "0.92", "5.56", "0xfc46c5b0025cd25635aae18e3842f355fd249134b9c6599d9db3dd2e5657e24e"),
        (140, 1752570889, "0.92", "28.44", "0xf015c3390b35fd4aabbb5d1b81ba77fa63ca2f67313c41991d4fb8cda273b2db"),
        (141, 1752570891, "0.92", "5.56", "0x283bc178c85e59eaa9876f45b8fc8478181fe8b95cdc213e3cff4b053c89fba9"),
        (142, 1752570891, "0.92", "39.99", "0xe14d27e1d2fef6f938b938e0f45c4e3ba4a1639bed8ed5a212084ee7344b6169"),
        (143, 1752570893, "0.92", "5.56", "0x82e00569fcfc95cc85bc3ae5d502bc3f9aa77dc9eab09a3beb3ea690b2ba9cb2"),
        (144, 1752570893, "0.92", "5.56", "0xf5054f004c867516f0b8bc1aa7c9a4fe0958de88806144196c468ac13b27543a"),
        (145, 1752570893, "0.92", "3.19", "0xf856fbb07b67eed9c9a24eaf6c9868dfcca06ba56cbd522dcaa7047dc5d50007"),
        (146, 1752570895, "0.92", "15.98", "0x1204bf288cb7bf1b736886fe6d345992bf417cf2f79cc092619e8319d652f81b"),
        (147, 1752570895, "0.92", "5.56", "0x83f069e605b596ab4e0a58959097cfef2fbc775355b57aafda29e596867bf8e9"),
        (148, 1752570895, "0.92", "5.56", "0xc95cc582e5c5ac95201eac98ccf9bf8722cdefe0639363a467f24fa9ec4ce6e5"),
        (149, 1752570899, "0.92", "62.48", "0x04a26983ab4cdeb1f2c6b5f42fad2d2e9a4a71e6f63d9bd10da09efe9d83b2fc"),
        (150, 1752570909, "0.92", "242.29", "0x92d81ea9630397d2054f11f200ca73822ea6ed8571bbba4df8e75e091e0b6bdc"),
        (151, 1752570917, "0.92", "60.34", "0xe55d144ecf8ee36b9b69b1c322b65f243ba9b2fa777bedc521b650cfe609e711"),
        (152, 1752570923, "0.92", "6.77", "0xd00e9cefb3c72750c378e84aa61baa2ae885959341c143d91a6336666de44ccb"),
        (153, 1752570933, "0.92", "271.67", "0xd5dcca754badc774430a918afa372b130654748dd5cdbac703eec4d49fdc335e"),
        (154, 1752570939, "0.92", "84.12", "0xf2c75e0b509525000ef461da634ff59e938ad0c1c7d33b55964f6c7e11ffcf1d"),
        (155, 1752570949, "0.92", "15.46", "0x3d29d8ba737c01fbbdd24d586a46d0d7380fea6f6288233ff3ab9fd557022bde"),
        (156, 1752570953, "0.92", "39.99", "0xafaf919b956c7b51196df9bd54d2d63968790562ea9bcd3fe01033775cfefbe6"),
        (157, 1752570955, "0.92", "1.74", "0x3c55a45a293b74880e7ab4b401b8cad4be06fa7e758e0480d385c9f430306a70"),
        (158, 1752570965, "0.92", "242.52", "0xaeb3718e6f6e82a64674c18834d8785f713ef4c55be351fbc6e6b707da4ac405"),
        (159, 1752570973, "0.92", "5", "0x204818512366e6f2c6bf36494816dcd5591eb793b65b74fe8ffdf6139735b71e"),
        (160, 1752570977, "0.92", "6.66", "0x51a6498dacf7869e99153922a221a156835b9fa504eb16d3e06253132a00ec6f"),
        (161, 1752570979, "0.92", "110.73", "0x9247cf565e01eaba3a7aba8e8e55bf5b71a7799f79f9780e6db225820a680778"),
        (162, 1752570985, "0.92", "10.02", "0x17030ffda7c2760701979509d1ee8b94cdf9836805888feca87791c5ba09b189"),
        (163, 1752570989, "0.92", "112.27", "0xf3e332c676099d39047678f80a477874ff75d508007db16be02114e3aed96a0c"),
        (164, 1752570997, "0.92", "661", "0x777e33af94dce82cdcad77ac1758083ceb7756fe18518905f254d133a3d12f11"),
        (165, 1752570997, "0.92", "14.41", "0xd40f30277b06eec1392afd833941f8addf156ab4d7a57135d955d50d5b18f397"),
        (166, 1752570999, "0.92", "190", "0x62cfb18458acf61f02930e12b6e7b791990b979e61ef82385cf522e539317bdf"),
        (167, 1752571017, "0.92", "15.55", "0xded7f1166a2af916037d4fc65919ad45ecca18054a2f72c2ef1017626808779f"),
        (168, 1752571159, "0.92", "66", "0x18b5707519a316434d65c4537394aaa49c5395d7c892f65d149b749acfd44f1f"),
        (169, 1752571159, "0.92", "250", "0x8dc1758bb6703d003d76b4bfddcf6788efba2949f95b07f5eb332f75e9b63cba"),
        (170, 1752571159, "0.92", "253.36", "0xab7e727a4c9fe04d56923103dda5ea1ad0a0621438ffff6342ae50f803f67864"),
        (171, 1752571297, "0.92", "40", "0x4a70b7d187559bc8d1683240818d01e94d83c51f1915dccbf138500ffa8a4ecb"),
        (172, 1752571303, "0.92", "5.56", "0xf90d390141bba027b696c8985cec547c7a31a8bf79ddbfbbf7d880d0ad2f6d55"),
        (173, 1752571305, "0.92", "5.56", "0xa2d80ca4b319a04dff99ee9d7811f9c15e7c897246a0d2a1e0eb0d6f62bd4422"),
        (174, 1752571437, "0.92", "13.34", "0xc685d6a74f880e423f90ffd2bd8bf34bfd77baac9c28ec900e144d299d833b4b"),
        (175, 1752571443, "0.92", "5.56", "0xd63736ca02a345d5a1f57f9785f5d386d847654cbb918e7d6e89621dcf425324"),
        (176, 1752573915, "0.9199999935", "6.119562", "0xba55ffb8cf0b3401fab377d53cd94597eb9478d196d89188eb01223ba7b96ea2"),
        (177, 1752578841, "0.92", "50", "0x71894cdddd4b074ad530bd0ded33820e46aa2ff6bc09b51091348ed2e3799c09"),
        (178, 1752579313, "0.92", "17.99", "0xdd2bec3fa6492b97c0ff7665616ecc760011a8428bf315d93dede1b751d53251"),
        (179, 1752582529, "0.92", "20", "0xa865fac295cca10770906f3f41d5ddd85c4e34ecf5d7db4c7a6b19b27da5e0bb"),
        (180, 1752591253, "0.91", "20", "0x1b8b1e2a9de0e8584c9b906ce52f4ddd1602164a07722e786ab3a3bda3a6ce39"),
        (181, 1752591255, "0.91", "66", "0x0a3bb515de6f6c30b459b60c1faef61366c0c71aff3a5f296f176d9d8b1eb3ec"),
        (182, 1752591261, "0.91", "26.08", "0xe1835caa16c8bbfee2fb26ee3c93fba1b6714eccc3929c2cb0016a9f1f02a15b"),
        (183, 1752598506, "0.9", "1.09", "0x1bcd624e588bd59c19cfe13664a83413586e6468796abb3b6f9f2991bd9a7de0"),
        (184, 1752598682, "0.9", "15", "0x4f351abd45894bb2ad59ecc875df1854e0220c2424d876b524cc6095613ca8ea"),
        (185, 1752598682, "0.9", "15", "0x504f1bb9a513ea6f22c941918905333766c1842374eb56fe27c450dab9d4eead"),
        (186, 1752598682, "0.9", "200", "0x56cd470cf546a9a34fdf27736b6408158c4a8eef68f11d1bd2fb13348621b615"),
        (187, 1752598686, "0.9", "1.09", "0x05b895efb6fd7685c5afefd29e39b524e797ffde940b4b532531b7e5b4564224"),
        (188, 1752598686, "0.9", "1.09", "0xb3002842760588a9b6dd3a49791c953c08a4ee416be019221eb7c6468b9daa01"),
        (189, 1752598686, "0.9", "1.09", "0xcb496d57682a1a0f64c015035b0469437478aec2f04ccde19f28c1855def12ea"),
        (190, 1752598738, "0.9", "125", "0x045bb28c4a607dc3faef2e3daba782f1145f5f9d6c73cb26018d1c6390a06740"),
        (191, 1752598740, "0.9", "1.09", "0xed460b68d23c7b2c6188a60f98863d6db62e646b5324c015581784a4d4882408"),
        (192, 1752598894, "0.9", "38.5", "0x77a6778d8b3a5f51a1531bdb5bb21300519aeead13848b8ed94418cbaa04d065"),
        (193, 1752598898, "0.9", "1.09", "0xb25bc646ced762ef53e211e02ed59899d5429645c3405b6692a8e50032e1d378"),
        (194, 1752598898, "0.9", "5.56", "0xbd73abf39cd68fffa519960cdfe06f965a29a15073b4b86364a73a2aa74ccf96"),
        (195, 1752598910, "0.9", "119.44", "0xf7779c671b37341e50611181d8ae4e8975098822da9abb1eff34891925a1fe3e"),
        (196, 1752598914, "0.9", "1.09", "0xb5d9015bfcdfd6d01652d49fb03cf62e9acc5f063cb74567eb7e6b8ff8e7ee1b"),
        (197, 1752599261, "0.9", "25.87", "0x6fbdab6be7c6b8f09b7a5b846797fa25bc98bcdc1587145a6352d48a799c272b"),
        (198, 1752599263, "0.9099999457", "7.736262", "0xebf200414a6846c11224cfea01b7eaddb0efd4e89f8c322eccddefab1527b73e"),
        (199, 1752599265, "0.91", "1.08", "0x10fde2583981c2f153af2a8bad8a5f1a56bb7827f048050703b78a97932226a2"),
        (200, 1752599265, "0.91", "1.08", "0x987f40eddb97aa6f8946d3ab6c14e05a3f50db088779fdbb05d9c9c64c8a4aaf"),
        (201, 1752599267, "0.91", "1.08", "0xeacd3d24d422b4110eb9930d55fabcfddcbd1ed9f9fc457aaf5f9aeb228b1a77"),
        (202, 1752600801, "0.91", "20", "0xeca55881758a21fcad481259148f1f3a35e6f97b65a19a8470cc68396824a72a"),
        (203, 1752600805, "0.91", "1.08", "0xe36cba01e4da1fff6dcc4ddbe5667f3bf90881624fb367e1d929893ad826b71c"),
        (204, 1752601815, "0.92", "10", "0x37edb00b6b05b2c9d74ad580b3bea1de59954a19dbc10ea8a0286f720318cd25"),
        (205, 1752603431, "0.93", "80", "0x1428cc96eb6220b94e573e771fba5c2d16e40526aa0f58fd64167b5cfb909ca2"),
        (206, 1752603501, "0.93", "597", "0x851e46297cee45622fb865172779dbee7ce5ab5eeeb6029340da7928df215d4d"),
        (207, 1752603535, "0.92", "30", "0xd4fe7d028397e23dd0e9a1117b69606dd78111597c71a674031baf12fa24442c"),
        (208, 1752603543, "0.92", "33", "0x644099b0a20d9ec2ea627eba37c62eea242e6ca08de8e9f5019567bcc18fbf07"),
        (209, 1752603543, "0.92", "20", "0xd77101fdff15d0ca10d444bdc09e3de80d7835122d647dfc4b868b92fa92e8c0"),
        (210, 1752605436, "0.93", "111.05", "0xa25bd355fed2b867ab67038f9e88f9421dc36f72d4719cec7acd19a62c3c95d9"),
        (211, 1752605920, "0.93", "270", "0xe9a038100f4265b1308a45a91b8a9590f495aed026ee989408a99560836406f4"),
        (212, 1752606522, "0.93", "40", "0x5b5369d7c606467ea24dc2ef079e0102149f82ab03f44c8d8ee172af118dfb25"),
        (213, 1752606972, "0.92", "51", "0xb212bae87a89fe281118bd1757c6370a71f2b12b8d6783a963167d90690dfab7"),
        (214, 1752607258, "0.92", "200", "0x80acf2ed409071d62399593c6417f63fab7ea544e741b3c6dd127f6eaa8d33d9"),
        (215, 1752607258, "0.92", "145.89", "0xac2f588e4b3882bab83eac5ea3dff5c373b597eecd439b43acca42ef7b46f0d4"),
        (216, 1752607258, "0.92", "40", "0xd5ed56ccf93034d06ac628730be103b4a22fb2a013b5ac4c0fff4eff06166ffa"),
        (217, 1752607338, "0.92875", "40", "0xfc341742f27fd4b3d56d4533eb390ca41348c5bf2625eabda6b96ead5d1e6d60"),
        (218, 1752607394, "0.93", "250", "0x7c696cacbcfa0715edfe0062a5500cd3983d06871d39b074bebee0064aa760c2"),
        (219, 1752607424, "0.93", "40", "0x232b2e7cdb9b0b53d14ce988a163ebb93db46b7e444988f98f2f1a41256edd9a"),
        (220, 1752607428, "0.93", "1600", "0xfbb9c95d7c18b922d1635a9c6ba2d69d6453a9c1baa423c5ba9882a0f1771562"),
        (221, 1752607444, "0.9299999986", "13.860214", "0xfa246c3103d0cd7dcf5680f18d663c92e60e17dd386768362a655f978ec5f493"),
        (222, 1752607556, "0.92", "39.99", "0x8f714bf7a9c0a9e84bccd046677d80e449b1335632756209783849bb28a04595"),
        (223, 1752607566, "0.92", "24", "0xd1c9c8bf73ea730c34db28341c4b933cf9d83564eb61eb28181f5ade9c5155a9"),
        (224, 1752607570, "0.92", "40", "0x6dc5354d8fb0c7815e348a11e5ba7b9b7d89aa21c73702cc29d007e0951b488e"),
        (225, 1752607578, "0.92", "16", "0xb5178e5777fd95c4dc6020f3ac372b11a572102a7275c5660146a0b5d89e670a"),
        (226, 1752607592, "0.92", "8.93", "0x8fbce1dec47b01b441bcbe90baba92a99bf4069f263be6d87ba51a13b19f7976"),
        (227, 1752607600, "0.92", "31.07", "0x874dc645d51ea066c617a5a02a46a8dfb08a943404fbec6822c64142df4afc64"),
        (228, 1752607636, "0.92", "10", "0xb7c07c6df1a58c7720a8466e345f7ab2d4b580c754fd7c3168b30330ddc52520"),
        (229, 1752607638, "0.92", "14.29", "0x4d620c103d239be6e36a05681d4772ec91db04fcbf0cebcb54cf0b15ea03b124"),
        (230, 1752607800, "0.92", "820", "0x1db3af31fedc4816d5d4085f0fc54ff98523fada630d04ce3eede499cb37499e"),
        (231, 1752607800, "0.92", "39.99", "0xe80cafcadbd8ad4857002e654cba6214304400c4b773a1209d33d0530d4d1c55"),
        (232, 1752607802, "0.92", "69.38", "0x23934339adfb1cf0b9bc4c4fbb4412acdb5a048a08f7b5b65a57edb0dde66929"),
        (233, 1752607992, "0.92", "160", "0x72599e3140b2118c51e418d9e5897c796d52b00bc9123d69a5aa6d14dbe0b77a"),
        (234, 1752608596, "0.92", "209.97", "0x4c9350f3b79b36a5f63826c48a8aff3d34ecb9e1e06468a712fe3c880b25c438"),
        (235, 1752608598, "0.92", "200", "0x270eb393157982833896df3b3c9ace7f3876d323af9ed1dc7e89d9e0271cf873"),
        (236, 1752608598, "0.92", "40", "0x9de87fe8b52dea546a27763223c0d3475474dc8b57984056581b765ce71721d0"),
        (237, 1752608600, "0.92", "16.67", "0x0218c9bfafcf129f76c178b724b7bf71b8c366ab0340df71a22c8172a9f46ac1"),
        (238, 1752608602, "0.92", "16.66", "0x6d24bb776439fe050d0e31c1d3aa6685db824e0d426206ad116d8353e6233e5a"),
        (239, 1752608602, "0.92", "16.67", "0x84d91f91d88c8fd203f09e67567a8bac5a381f613b8bb4d429548b0580e73181"),
        (240, 1752608602, "0.92", "16.67", "0xd4ec401dfeb2ba1704b5e983446c8d64684b35264869b24e38d5c9d180cdc997"),
        (241, 1752609072, "0.92", "599.91", "0xf95f5db43e8ceb3feb9afbdf6e417ff258fd62178d0860df8f22681771134fd2"),
        (242, 1752609238, "0.92", "10", "0x41ec08e351a3232756a74320a4e81fb782054f39974d5a74aae0521a15b96b29"),
        (243, 1752609242, "0.92", "13.86", "0x5c27e684724e3ca128a34b450bb7b14488c78737ddeec1b90191ca3caea9a80d"),
        (244, 1752610080, "0.92", "5", "0x2596315271e1c36583c805ed09b2f67fe969db8487a5e7c5bd290aacf6f715ec"),
        (245, 1752610776, "0.92", "197.33", "0x150793386629467bad55f533ec5912d9c421561006a80e643597b4af0f8e340f"),
        (246, 1752610776, "0.92", "5", "0xa4d7c2c78f2c8869c42532e50fc2e71d52b2dee064dce1477354c085c3baa7fc"),
        (247, 1752610776, "0.92", "346.67", "0xefcbcc9aa40f10c465fd7145b43b6b819b35a3b6956a5ded994d6ee01fe8bad5"),
        (248, 1752610958, "0.93", "20", "0xc61a7a1b317a797da66c553cebdac69f1a9ccdfbd3c170eb4620827f470ecba3"),
        (249, 1752612397, "0.93", "108", "0x9ddc222889d82e8cdc809eeafa8ef10aa5eb93e90e9536a6b8d47729afc5377c"),
        (250, 1752612399, "0.93", "30", "0xccbed77329f131d9182782a9d662cedb61c1383ca5a895be47d6cb822099fd9e"),
        (251, 1752612411, "0.92", "14.95", "0x63fbd926fdf96863c35424272c8f6bf6ced8d975276a6452c56a2b49c5e3bea7"),
        (252, 1752613959, "0.92", "20", "0x2bec9bd3a8a1682fcb7b2112afe83071f0f031574fdc49d368b824f45d6297f6"),
        (253, 1752614159, "0.92", "32", "0x52fd42bff64d20ad7d56ac5eecafd1819d04737b1452a39662873df04c368fe1"),
        (254, 1752614923, "0.92", "10", "0xa79234b5862376ff82e3530b031062367421689c736346f2ba83d18f7f282987"),
        (255, 1752614923, "0.92", "17", "0xf13d20a55913ced2533a2eb0a4bb5b94e28106e232aff9e7dbe5e98a6e433aab"),
        (256, 1752614941, "0.92", "5", "0x2a2a5b1edfed683564b20b38c6ef2c51b400d97c6fea859287d905a3ee5be70c"),
        (257, 1752617199, "0.92", "50", "0xd954821d8628f2cd7f2565f11f5bd28cd5843420a7ed60f67e4b74aba5df4bd4"),
        (258, 1752617781, "0.93", "100", "0x019298dc798626524d8e7db028fc7e0e8296a61b2ff0fd0729398a4c8df787aa"),
        (259, 1752619513, "0.93", "253", "0x844c50bb988a90397af65ac2eed02412ac2aa0d287b950d11a805d93b58bab85"),
        (260, 1752619543, "0.99", "15", "0x7073d97e957415001b578a1703dc0ac08c300549b7ed62e9f8fd46e5ca7d3cb7"),
        (261, 1752620619, "0.98", "500", "0xda9a7e896ee3161880cbf8bb338316e29d2ffd74e19fb10af12c29aa830947df"),
        (262, 1752620645, "0.9989521785", "941", "0xdcc9ba1d0cf815f6352fca79c66f2d2c50fd72bc7ed15970961ee1b37dedd904"),
        (263, 1752620667, "0.9964779319", "793", "0x0969584fda5b654ae1dd5d0d34bbc423a4f3aa5a11386ef8e0cf28c018551312"),
        (264, 1752620673, "0.999", "440", "0xc970d0f5a57c5f11b7d0b3c81684b6f22b9ba71ccfc43e2d1c0e8321e4e52f21"),
        (265, 1752620979, "0.999", "200", "0xe83bfefcce2a1d5af5c6bd43760d98f04065d0dea381e23029713e9b234ea7ff"),
        (266, 1752621531, "0.986", "20", "0x949e57491ed35ecdbe4f7ff6da973bc71197c070932e8c610f80277a5686f3e8"),
        (267, 1752621547, "0.9924511278", "266", "0xaaa307c40f3bb16c61aa0f2c85c854cd5bc31efc6027fd151e24e5526c365b4c"),
        (268, 1752621565, "0.99729274", "3416", "0x11ff6efc01f478a6fbf6cfc9cbfc6cdd6024cd4c2025330bc07b3e273e15d009"),
        (269, 1752621739, "0.9961413147", "1103.99", "0x5edcd6c90d9cb4d1a4a594788b727e0cdd11cb43eb619c89e2ee9181f3b26522"),
        (270, 1752621899, "0.999", "4205", "0x53eb6c8e0612b00f12880f20ef725097ce45ebb7a295cff6fedc6e0b86d4fa99"),
        (271, 1752622047, "0.999", "2415", "0x0eab4e8289b1666e31a9cbdaba94fdc0a8ea0e8df0ada02b408c2cb34cb09fa5"),
        (272, 1752622533, "0.999", "2295", "0x5ed4997cca166b1a054b33df4f9e09a18254866fb8f5a7571cb8149a2602ca04"),
        (273, 1752630845, "0.999", "100", "0xaf51314d82181818fba7db278f0df0e3d3c7d4a8c057b69940c1bd5a3ee4a41f"),
    ]

    fileprivate static let retained563325Yes: [RetainedTrade] = [
        (0, 1752508343, "0.08", "12.5", "0x11ebaa85eccb3c0926b18e0f39983af6135834cf105193d883dfe1ec5baeb42b"),
        (1, 1752510286, "0.08", "123.75", "0x79273cba814fabc207792021552c3832d6ca788cb7da8c8e0c85b0520d4e64af"),
        (2, 1752510334, "0.08", "299.25", "0x103a3f988d2eeafb92066c6bafb1631379297f75efda3f8841e0e32db245c4bc"),
        (3, 1752516112, "0.08", "12.5", "0x3c3ea257dcc9fd41067e698028143ae304ba23ad877dba1e2a9ca510466cce74"),
        (4, 1752518079, "0.08", "1887.5", "0xabb892bd804982521808836befb67a581a446f97132f934b7102038e6eef15af"),
        (5, 1752520513, "0.08", "8", "0x1bb43eb7d2536766dbab999ae6611573655ff1045491e7e0cb9671a548fe735f"),
        (6, 1752523700, "0.09", "223", "0x73ee6b3c9caf9ba5fbd4ffdc5dd4a6381b5b28315f3e01d6b2ee3da7b29b02e5"),
        (7, 1752523716, "0.1", "100", "0x5936ac08a8dfaa80a9c866f5b7a87be82601b8fe8bc07b4854f8e314c1c1abfe"),
        (8, 1752532289, "0.11", "60", "0xbf352ee893756d9509d7b1c8e99deff82c33585ff6c913ab8f713029a37dc61b"),
        (9, 1752533277, "0.11", "1749", "0xbd5934af1d13791f9e8d2a026e289787e608ab468c99739c422d31cdbcbf2152"),
        (10, 1752545815, "0.1", "11.63", "0x830b6e81e52ef3bb5393a79d69ba1e9d76a531078f58314a5b6463be279c1116"),
        (11, 1752545823, "0.1", "23.25", "0x154fa4bb58c71d28b77f22e265bb76930ac721e325c7e3b3f962b2665603edfe"),
        (12, 1752548828, "0.11", "1000", "0xa26775040a104c02b15d970fd61474f2c8279b3432b9f83ebaf83d405ac63593"),
        (13, 1752552377, "0.1", "5", "0xe85e90490aac586165c37342bd98d18fef837f74d3c8dcdff83a4ccd45245696"),
        (14, 1752552389, "0.1", "3.01", "0xef207791307ede68754cf571dffdfe485e626ec0e8a77333001003dae719ba27"),
        (15, 1752552401, "0.11", "3.99", "0x3c81b06d3dc9197e357d9949d51c1cdc05e111a204695098f52df86545b7aa15"),
        (16, 1752552403, "0.11", "21.01", "0xea5a37dedc254aba13b58c07230b1c39e8234ac0cf35ab4d29ca0a12be5d4ae7"),
        (17, 1752552407, "0.11", "5.99", "0x93e1c72e8e0d29d1443aedad6841e7424671c9de1b3b19f83a90bc4eaa8c04da"),
        (18, 1752552411, "0.11", "27", "0x6c06fa981b382fe558abed9818fbd24d0794234b140e6b8dc1b4be900412ea49"),
        (19, 1752552415, "0.11", "11.01", "0xb213e17bc46d7393db5abb011f87da968304c708c1eafc74e33b5fc11c23367d"),
        (20, 1752552719, "0.11", "5", "0x91dc6e087b47755420c64f27d128043dec2185d353438b5069468963c193cde8"),
        (21, 1752556479, "0.1199998992", "8.333332", "0x589360d226f182462eaceaf99404d8079413e645ce181daf96377f88d158c98b"),
        (22, 1752559189, "0.119999996", "208.333332", "0x6fca9da8f2396487fb662babce9ac7e5eee196cff7ae394827185c074092c8cf"),
        (23, 1752566381, "0.1", "103.83", "0x3e7330dca77d7f488d01a6dd6be33ba8c2159e9394a061163b02e1f4408ff140"),
        (24, 1752566401, "0.1", "30", "0xc706f542f299f9d8809d2495fcbc0cd895baf74aef16771540e5f1ee2e16b5f0"),
        (25, 1752566670, "0.1", "36", "0xcea22652bb585fee9c3c511d62222e0d571d52db6458abc5036bb5f76cddc80d"),
        (26, 1752566702, "0.1", "25", "0xf98617584cd8cc5b95163e956c369e859d70e3adee340516a5c727ab99fb44a3"),
        (27, 1752566750, "0.09", "22", "0x528fbb5ee797c130712beb7025c7c5a6addbe4d3408105ca3eae33a19c1b6148"),
        (28, 1752566764, "0.09", "11.66", "0x57c91c47c0bd3fbfcea2cda7ac3f619984d0b697aa401d706d4d9f46459d9cde"),
        (29, 1752566814, "0.09", "206.62", "0xb92ddb74d9edc4ef56187774aeb4978b86beb9a4dd4d1c42d1f9744c11598bba"),
        (30, 1752568522, "0.09", "1.91", "0xec1bcc5bbca3a2244c08058c7d9ebdc0201d9130c064770c30d0ce0bea7b1411"),
        (31, 1752568714, "0.09", "5", "0xf15fcabafd2d13bb5516237fa77bb09e95dffae83e2e26fa56dbb561f7edfc60"),
        (32, 1752569693, "0.1", "8.99", "0x3d904a9ef9f862b043e59445852acde6db15fb2cc5d8d05dfba0706f092ad6bf"),
        (33, 1752569809, "0.1", "10", "0xf57f790ed1c510918b2ceca2bac42b8458e3743208bd66c35970efc5c02ad67d"),
        (34, 1752570203, "0.1381377307", "2533.703125", "0x709d6440f8150f596fb0df03fb288ad6f2e58e382ef9a84312a4fd134e961c94"),
        (35, 1752570643, "0.1", "223.09", "0x69ec46b03763d0da30348ac39a16cc8a716a8c1a72bc2bafbd6850b56a217c0d"),
        (36, 1752570829, "0.09", "240", "0x6e01d7b0539555681121969218afbe13b0646224e847387c0db781fa1147a993"),
        (37, 1752570865, "0.09", "5.28", "0x30daea4667de1fd1e3142c654320216026a264b752375efd9cdbaf3a14bee4f0"),
        (38, 1752570867, "0.09", "195", "0x48adc059f6adfc3232923cc69e4bbcfc1f241284e902d121ac12077a518ce59d"),
        (39, 1752570869, "0.09", "39.72", "0x61eb512a9ef34b8ffc4a5ffb73a49570914b3ff6b6fff260aa584348dce7fcd6"),
        (40, 1752570989, "0.09", "240", "0xac593451c406d920bc12f65f46e94f0107fc20d0e4519bcc7fb9817ca3aa358d"),
        (41, 1752570997, "0.1", "190", "0xa297c7891869c7d861a05acf3123fca3f261c6cdbbf4e868d16b6cfe6ddb3633"),
        (42, 1752571297, "0.09", "45", "0xc6eb99a1f9d18762d52e1d30c79d9c3c080a2246eaba4acc8c98c99c2b0f3423"),
        (43, 1752574011, "0.11", "100", "0x2b814f15aa0c12407391a404d6ea345de5bfd53dd5d738aaf74407ed52652c84"),
        (44, 1752578907, "0.11", "1.41", "0x2d8811099108f74639f591d96cf8c86323f6b8a028960de007b4988d028da8c8"),
        (45, 1752579313, "0.1", "18", "0x65bde33d9c5b7e981d08586be61f8b83fca36a86bd8d1cb939c3d0f16f974114"),
        (46, 1752582527, "0.12", "50", "0xceb2302392c5896f3136edadfd1eebc2ea55d39aba7e78452588741fc3ec9ae2"),
        (47, 1752582529, "0.13", "20", "0x8330c2bca420e82c44d24afb2d82183861513f810eca3bca67f85733e189c2f0"),
        (48, 1752583933, "0.11", "605", "0x0063b584494f702d40e409f3c386df8efb3244c296609f852c9e8b4a778f13d6"),
        (49, 1752585057, "0.12", "100", "0xa6bbee78581446a588022cd732be7817db9e99f73a7a1aa03764924fcec68a68"),
        (50, 1752587069, "0.1", "1844.99", "0x239755fc4c257fe18335358e17b6c9962088222ec0816377e1e4bc5a683028e5"),
        (51, 1752588081, "0.09", "3", "0xba950431b61236a7b260c862fc19a6a95bd2dce89970424a9201d69e9f845aa1"),
        (52, 1752588857, "0.1", "316", "0x71b736c97dbb0efb99de513cf9f60f0f97d49695786ec95179810a24d264c43a"),
        (53, 1752591253, "0.11", "207", "0xa394529d0ec8d5d71314bea33bdf1ef6b5cbe3bdc1546a1b44016f77e84c23e5"),
        (54, 1752591261, "0.1", "26.09", "0xea442867a2016f09658484a0be2262ac6452b0feda22d129f374a710ef24f8b0"),
        (55, 1752593956, "0.1", "1053.83", "0x7d77f8e17425907029e3b5ac87ea4d0d4081ec07583159a41d8c3c64b3d5c87e"),
        (56, 1752599329, "0.1", "36", "0x4f59b51afcc05533e2461fdbb21ba0cd7c49740b5ff6c93f42db9217b047aa4b"),
        (57, 1752599383, "0.1", "36", "0x501457313153ae20a730308a6e8f06fdcbadeeda2d53afb931c4e7b816c5e028"),
        (58, 1752603351, "0.1", "5", "0x2621d1c530419835d0610dcc14ce876942aca5fec5acb9e47e348fbbc4b68412"),
        (59, 1752603429, "0.09", "86.99", "0xa36102dce5eeda46fb55810d86a8dd65397c87d7c6008b87f8c711e70b672422"),
        (60, 1752603796, "0.09", "3", "0x4b68558050ee603eb069f51215c07fad000dc9b8efae92a23e2ef188922b1276"),
        (61, 1752605764, "0.09", "2.96", "0x7dc0f28ccf9ff15e743261ac991d3cf78a6c0c78fffa130104cf5f4b0a1bdf40"),
        (62, 1752607258, "0.09", "200", "0x1b1fc5375f005a65e60b456ea03935b87b08f4b3e81daf1245095bf8a116aaff"),
        (63, 1752607338, "0.1014841589", "985.375453", "0x568aa949c49897a013895eb2469f71273731653c911dcdde86cd5cd7ac1aa9fd"),
        (64, 1752607556, "0.09", "167.24", "0xa66c3b329dbd70e339bdd85bd70c2062488ad4d9b12afde1e5b670ed39a215bb"),
        (65, 1752607578, "0.09", "8", "0x4c89db3d0d2520748b530528f3741ffd5158e10ccadfe8eec109db894832b067"),
        (66, 1752607582, "0.09", "5", "0x28f7992ec0ad0729affbd437f60c4da99845321049d07de0c5099973dc6b09bb"),
        (67, 1752607586, "0.09", "24", "0x745bdd5541258b3c1b64a176c20857cefffd4f1e782620a3c83529c7192d82ed"),
        (68, 1752607804, "0.11", "15.38", "0x4c2281f4b0fac6fea184ac35c8c339fc8d00eddc255eb8b042cde681f58ad39a"),
        (69, 1752607804, "0.11", "15.38", "0x9941aa92b68be6421ce1d7f7b3738066c3f306469631ea04b9849b5a7a2916c8"),
        (70, 1752607808, "0.11", "15.38", "0x582876692de745784397feeda6418738530306cf6bf79d074f2d56ca45217d67"),
        (71, 1752607990, "0.09", "165.03", "0xe9e925087e06544bfb17e25211879cfe9661a1e0b8e01e056791aa8362bd6028"),
        (72, 1752607994, "0.11", "15.38", "0xa659b389f0e2825d75ff03c89ac1d1969468ae4beef814a810a1869912fccd3f"),
        (73, 1752607996, "0.11", "15.38", "0x4727444c23febb42691d528c5b2c28d3673caeb27b24be817ea8ecaad90b0d79"),
        (74, 1752608596, "0.09", "209.97", "0xffa3816d043f4900e40ed83fb029bdf0644690e473a9dd4aa5943995c48c861f"),
        (75, 1752608600, "0.1", "16.67", "0x4052e03c69d3ea03d930ea22d2f94ed895bc36d867d39df0f4b235689303c205"),
        (76, 1752608600, "0.1", "16.67", "0x685cc1f51439dd6bc7f92c80de3b73a3694850bedca18e6ca50d1cd8319de199"),
        (77, 1752608600, "0.1", "16.66", "0xbda2e61e57d27c5aa0e57e808967ef09955f5fb8989852985bbcf72c6fe2d059"),
        (78, 1752608602, "0.1", "16.67", "0xaddba5e328e80f2d749365936ba99de03bdd85e105b7c15515c0701c71808070"),
        (79, 1752609236, "0.09", "10", "0xc6bbb789b96d26bd6f7c0c3eb57d66956b38c587ba2301d796688273c9d16a44"),
        (80, 1752609246, "0.11", "15.38", "0xf8fb6b8b51fdb5094f767bbb70b440ca25325afcdee760e1810fa519ea43f486"),
        (81, 1752609704, "0.09", "5", "0x12e39719e345f3fab9a1de33a9b13e8eb92822f5a24077aeeb7c362a8adb4fdf"),
        (82, 1752610958, "0.09", "9", "0xbe304d0e1cf54b342f51499acf62ff2d3d8e4c4db27dc5b5f649511044333a61"),
        (83, 1752612243, "0.09", "2000", "0x13b485728e10ea5d5bda7ab70a3e825ee00ee64bcc18942a175752f470ccd9c1"),
        (84, 1752612409, "0.08", "5", "0xaaeeedf54f1ca9226a4e1241795cb7d69e361b4d960a620e14d8ccce6045396d"),
        (85, 1752612839, "0.1", "400", "0x14bd300d66509109df40b3d83f9c296c95ca9494c4592e46015f8e5d0640d958"),
        (86, 1752612887, "0.1", "500", "0xb985ac0570b14cc93c2e516c9f9019bc85e18809c1635d4a584febc2cb044234"),
        (87, 1752614159, "0.12", "32.5", "0xc2459f7b114338fb4e2ab68f51e369fbca5f1a7952d58c7af37b34defba561f6"),
        (88, 1752617331, "0.02", "100", "0x5b6c97940b6caa5a58576139e5ac20b9bcedb71dc241cfc97cadd9937a6dbe2a"),
        (89, 1752618391, "0.09", "45", "0xfb63e5ababfdae7e917d882adeb6973b0eefc2e10f4f570efa02c58c5d8eb5d5"),
        (90, 1752619951, "0.33", "15", "0x86bb7dfc5f70faed3eb99a74285e3d0d26bf49c80704a25ff92bbadc02a94202"),
        (91, 1752620067, "0.35", "20", "0x4092a26967279af922e0785ac0da641a9171b41ca1ad0a5b4e8de4fd1b3a84d9"),
        (92, 1752621323, "0.0165359477", "45.9", "0x318a47a053499f8c462bfc1a4ce3c0b917e846fcace5837873cf10cc0c560d12"),
        (93, 1752622987, "0.04", "24.01", "0xa66fe5f7a3b3162eff278e9f89f77a9849f78a2c71abe6c9818f44477414bbc4"),
        (94, 1752623395, "0.173552427", "576.19476", "0x7ca99c1e06daf2e85e9fbacd0778939130d9066563a4dcbc9e45ac8e9dfbb2a2"),
        (95, 1752623517, "0.1746841365", "286.230908", "0x0e32a76a743c8c32de73c421bfd0645b60ad2884c901699b6e6ee2178200ba38"),
        (96, 1752623869, "0.09", "35", "0x7eb593d5b186e7d53794f61f5f56fabfd8f52f473035d71d92562ce4da025b4e"),
        (97, 1752623873, "0.09", "2.01", "0xb8b9b395c20eaf827de33c127bb65e2de0956c7e4982143a4886ff51f162e68a"),
        (98, 1752623941, "0.13", "53.03", "0xe315d724f41577509556614389be29e95df7ca33b7030509fcbde29b7e22ad59"),
        (99, 1752623949, "0.13", "10.01", "0xa54f9734eec4437c8096ac7a1746174d1d2ae9e78a29c533473ede035b217bdc"),
        (100, 1752623973, "0.15", "16", "0xcc5e33dbdfca94c536c6d6c2bee54ef96e19098b573d341716bbcf483b8aeae4"),
        (101, 1752624151, "0.13", "1", "0xee8b1c2a46783758a042c1ead079772ff78a3fd2bad48f389fd7f192cfc24ff1"),
        (102, 1752624159, "0.1583700912", "631.432351", "0x94bc6ea55d85671a87b71b94d0e109a5b01d709cf863200e57fe6e9417b7dd61"),
        (103, 1752624167, "0.13", "111.09", "0x1c23f2a2c7761b491dd602055e6b6f589d92ca475a6cf58eb8dd5e57b4608aeb"),
        (104, 1752624181, "0.14", "29", "0x7846d42e4ef95efdb97aa5bbe2c4b6b1410d9eee50e4d0e547320362801a0b09"),
        (105, 1752624185, "0.13", "21", "0x6e1f9f70d438774e0506ddbfdb4f5ffa62351be096ad067921c87a63db05a747"),
        (106, 1752624189, "0.13", "9.87", "0xbfd0ba71d93470a33d196eab944ca5be5242125e10fa98837aaef790501353d6"),
        (107, 1752624325, "0.1630906627", "613.155881", "0x471f7607d1c72737651b002a6734f4823eb3fb74caef24ac983273d45e8560cd"),
        (108, 1752624331, "0.17", "16", "0x1de2a91bd09e80dbf1f1d1739ca172249a71d06b20649a71eb5a3d7a1c57a724"),
        (109, 1752624457, "0.1691249277", "591.278887", "0x33d4005f938227d237b8af3c045bcc62e456ae3b8875af7827aee27ffd5e1dd5"),
        (110, 1752624457, "0.2", "16", "0x33df8bccaa1feef44c392761d8f27beb17dcbaafdc12afd929301a69f9002cea"),
        (111, 1752624457, "0.183629773", "544.574", "0xaba3ed002c8904b3de3abe27483238d62d12f39bec6537512e4b31596e7594de"),
        (112, 1752624513, "0.15", "5", "0xf29ecbbf67c98196952ba0063b7e2de8269b818f35bac42f49185883b7317184"),
        (113, 1752624937, "0.12", "50", "0x66e2c83f78db41fdf15c95b349153165561ca60c3575112b26ed65d054e72bd6"),
        (114, 1752625733, "0.0771084337", "103.75", "0x74de531cb29c1d83d363dbd3994612116113eb2853ca21b3b0f03a96940d7949"),
        (115, 1752626055, "0.077", "100", "0xf5f5a8e50b13068ea9d70612302adbc08ce17cc5ba8631c85792be1858ad231a"),
        (116, 1752626659, "0.02", "50", "0x5e43973a5731d35c3b3782393db8ec96d01d8be79d3ca6bbdbeb2b91472accb5"),
        (117, 1752626701, "0.02", "150", "0xcb20fb0d27f22cf71f82b0400fde1bd9c69e09e79138d37bfeff50994f48b97a"),
        (118, 1752626741, "0.001", "10", "0x64d111928a78231b773599eebcaebc8aaabb6abff5b3eb7f5e35df4ce96a2897"),
        (119, 1752626947, "0.001", "852.01", "0xd85f63a77bdb1f6b13f3299fc5c69edb1628d92c2db65e47d8e5ed390bcc588a"),
        (120, 1752627061, "0.001", "32", "0xb9fca2d5668d7b879dc5d8a642f0031718647724d34bac4a5fbe237da1a5b405"),
        (121, 1752627067, "0.001", "5", "0xa2257b219be0d3c38545f5e312c53fb819588d4a00b17f43121cb15c8efe3d59"),
        (122, 1752627161, "0.001", "5", "0x5cfd866f228d862b552c96888eb1251a4f36885b637fe06aad0e209582a73360"),
        (123, 1752627253, "0.001", "5", "0xe865844f32f44ff763a922a93e86b7b01c4688c320f10cb5213c79c3517e88ec"),
        (124, 1752627349, "0.002", "72", "0x4c149808eea6edb62e45cbd539462c4603e5645ed437094e52f9055328aaebd4"),
        (125, 1752627545, "0.005", "275", "0xc1441bd17d1e50d2933f82a08a7e5cb5f3fa6ac16f0abc6356c3e4a8013b2a55"),
        (126, 1752627609, "0.005", "1392", "0xfb92d606ba2a2f1e438b7f16faf0dea45d5ba5cd9e1a856e679580c0c2364b6b"),
        (127, 1752627625, "0.002", "171", "0x559049d7548b87c20430e85d2e27d52576315cf673761f8f89b5c8872c0fd3f1"),
        (128, 1752627635, "0.005", "792", "0xda84d564da5a6ef9d0e97ae6f8b6db63c2a10c48201832972dff1f6fa6d4e447"),
        (129, 1752627703, "0.001", "25", "0x790d711d901f0fbca9136955b34ce6ccc0076e8809b79e886e205d7144fd48de"),
        (130, 1752627871, "0.0046296296", "216", "0x4717eaec098533bf9246014226cbe5f5f4891206830f646fee87568b539782a2"),
        (131, 1752627885, "0.0050352721", "992.995", "0x03f94fc0e2a6bce60e1dab71026f86a22fedec3c4fcc2123ca93d414c7006ba3"),
        (132, 1752627899, "0.01", "171", "0x84be6c64a005a7cde97f9e3b6f8d632685a7b7c34aa334229c32e9f20a67a308"),
        (133, 1752628073, "0.005", "1998", "0x1417e9be00d0773e3381bd789140c1150ec356f5c3de6b3645f4f387d6eea293"),
        (134, 1752628375, "0.002", "100", "0xca3c02ff851cce0449e270bbbf0301adcbed7971b555bb0bdae40fb0aebe9bc3"),
        (135, 1752628443, "0.0049601417", "2258", "0xd9579e1fbec70d3dca929cbea854342d62a9a45f4c836b3a095f8ee89aa8d448"),
        (136, 1752628755, "0.005", "200", "0x8dd2e711abe88918935b1d71ae1233112724b1e085ea1e7ebfaae85312d530cd"),
        (137, 1752628761, "0.005", "500", "0xad8932f6e764dfc9740952ed61d0005f2d72b305714254bc1bba8b0f5b6c541d"),
        (138, 1752628783, "0.0045333333", "300", "0x45709980c8e9d0732e16f01610ef6d6cf9fedff1d329055a54da665987eabb45"),
        (139, 1752628815, "0.001", "100", "0x1a118b19be1df9e5b9dd850caccd5253924c383541aca79a3ceec09485c569cd"),
        (140, 1752628855, "0.004", "250", "0x66a15e49d3c075a17c651dfedb2132190217a583dd5da8ad8ef389e78ea4b6a5"),
        (141, 1752628869, "0.004", "250", "0x13c2c381d7a862b4c80b39e2a4479ae7945e85ec303e34762eee37a5f199c4a7"),
        (142, 1752628895, "0.002972973", "3330", "0x29f48401489f3fda963d38afe22c2a3dab1a7aacd3f2f3ddc0e027c77e12dd50"),
        (143, 1752628963, "0.002", "1000", "0x4a65cea5c2309f5a019db47a6db92d4cc1f288ef0c7ad1672934e89be5eff16e"),
        (144, 1752629067, "0.0027779005", "34399", "0xcab385d53768ebb2bbb03078a6b77d535fbdd55a418f069c75d82f27c95af61a"),
        (145, 1752629337, "0.0018348624", "545", "0xae5ecf0ed426280d5b8c010cd2e0b96888bfda35ba9f967b39023ec6da0ab3b6"),
        (146, 1752629357, "0.002", "1500", "0x361638b55ad4ce68dfd9259dc3daccf488af451d69830f5e58697d6400541647"),
        (147, 1752629377, "0.002", "1500", "0xe587a65698b7d0c9a8b4b6de25f9eb04a70023465f5ca9f6f87e3110a3bc95c1"),
        (148, 1752629395, "0.002", "4950", "0xb313e20e7ce108e7963e462f14387d04282ddfb9490fa150ca542455c518a520"),
        (149, 1752629421, "0.002", "500", "0xf5a7f4b7fd85e9c7d4fccc9776a065775953af3d146a7c3635e06a4808b82137"),
        (150, 1752629453, "0.001", "100", "0xecae0c1c2de9521547c00cebc3efcc6d8759f7d52f77763519d49d6aaa1d18b8"),
    ]

    fileprivate static let retained563325No: [RetainedTrade] = [
        (0, 1752510556, "0.92", "100", "0xdf363efcac56ef301014691b6352f600bbfa1bb4b0af526bb73325afe9d36a2d"),
        (1, 1752516056, "0.94", "10", "0x15a16c58a83508fa13470b43829e8ae378d00365b8b22684ef63059e9c0d9443"),
        (2, 1752523852, "0.92", "1005", "0x37ef6c29dfbcb55202ba0995b6eb3ee8625112e62b21996c82ceed4f691d0c13"),
        (3, 1752529475, "0.91", "1065", "0xf0917b4cdc83a25bf819530f7deabff9dfb6c1064726a8d154dafb82858d5301"),
        (4, 1752531497, "0.9", "105", "0xa9753839ba82a7e5b4337a6e86c00275a16a2e191a27c84ef1d598d3b64ff579"),
        (5, 1752531593, "0.9", "70", "0x2a05f48edd9b2ead0f3136f4be63693c735199cb571cf4ef8b0bc240d1dc3594"),
        (6, 1752531595, "0.9", "75.2", "0xc3ad37015664d1f1aa9c0131e8266bd59ee473918c3afbeb6ef875c286fcece0"),
        (7, 1752531597, "0.9", "1.09", "0x6e0edc6391a8c27b4690ccae4a82268c6fca21903232a7599e96be91a66b6710"),
        (8, 1752543221, "0.9", "10", "0x480a0ff2c4fee09e1f2eba8a36b48e315b6ac1a5dd41dffa8ef342dc2a6410d5"),
        (9, 1752543221, "0.9", "13.37", "0xf08a1b3d612f5171b012253974792ebdc0ca552e55d497987095551620977221"),
        (10, 1752543223, "0.9", "1.09", "0x9b9bdde4d05a6d2469c2d753567b549b66c32dc352ecaf243982e4239cdfaff9"),
        (11, 1752545817, "0.9", "10", "0xc0ab62a6f0ae554187da0a091eebaf412f07e864aa8199175ca35282cdfb3b14"),
        (12, 1752545817, "0.9", "11.63", "0xc81c669a5a6355fd95f512941481d6d1136d8ff2417af2957bf6d230f355ae09"),
        (13, 1752545821, "0.9", "1.09", "0xc57e0e611bc60a7b3e1785b2733094c9efca02e7f0c811c9c3b2bec70d4b74f1"),
        (14, 1752545823, "0.9", "11.63", "0x66ae3828aa81a09403f1ac7a7c2e571c3dd3b548ffec7b684f09e70a6b6419a0"),
        (15, 1752545825, "0.9", "44.88", "0x4d8f6607233cc717cf1e9d5f252e75bc05dae712428c1af85c3290b1d7143f53"),
        (16, 1752545829, "0.9", "16.67", "0x0c5effb3ef5e337fd759ba1c8ef8aab079119d9463d9f721babebbf64f6fe1d7"),
        (17, 1752545829, "0.9", "1.09", "0x7276da86986a04688c1755072f9ce075829d8e51bd595662295e415ff024047e"),
        (18, 1752548832, "0.9", "20", "0x8a69513ecdc7f54d968779ba7bef16f9ebb8f6b5c6c309091ae1269453cc1a31"),
        (19, 1752548832, "0.9", "1.09", "0xf4b33c61bfbe7b0582612fafe0850c4c67fd14339bed29cc3754d8385b2253fb"),
        (20, 1752548834, "0.9", "20", "0xdc59c9b5a4111d8b1a914637a1628d321ed8d3bba33a2e36b94445340eca97cf"),
        (21, 1752552353, "0.9", "2220", "0x35a6e89a67aaba22535170509bd1ecd4cd69d78cf0f20ce68a96dce8e30f894e"),
        (22, 1752552353, "0.9", "868.32", "0xf264577022d52f8835fccc323a0c8c7678827531893730608c320d9fb74f57b9"),
        (23, 1752552357, "0.9", "1.09", "0xf5ae6f563812d4ed472d065be080579a5047ff6d716012bdef8d6036eca63aee"),
        (24, 1752552377, "0.9", "21.99", "0xd999ba549f8f8bcfb0fad3a13072a94b55c41c5750edb768686666b436b8af69"),
        (25, 1752552399, "0.9", "25", "0x19593ca191e0b6088533367b823066d888471cc0cd024ffb5f145a11bb58a74f"),
        (26, 1752552431, "0.89", "9", "0xa1c9115760e16a033ad2d40f27b3289b6a20dde6f76bb5a1d21be3f65a3022e4"),
        (27, 1752552435, "0.89", "8", "0x4ce31783e2a8be8403f27a574247461f67547ef6d3230d0a8aedc324351d0ecc"),
        (28, 1752555149, "0.89", "30", "0x6fd2c51feea5c00ab946f6224a534ab7fc73051e1011ba7c73d45ffb6645000c"),
        (29, 1752555149, "0.89", "7", "0xa1518c11b91876ac80a24adb17767efa47cf6f802ef010cff5f99939ded04d14"),
        (30, 1752555153, "0.9", "1.09", "0x353d0df426e8b619e0d3b8e040b811f6e0d4dde2b1175b64ffba7e65813d84f5"),
        (31, 1752559303, "0.9", "66", "0xce8e246942411ef66b1e41b4a2f9e3bdc3d23d38df67a5856b3653427128159d"),
        (32, 1752559647, "0.9", "100", "0x4e4fe803e90bc46ce970e09716d7f51e84eebad9da5e379b50479e2849e14283"),
        (33, 1752559651, "0.9", "1.09", "0x997f09ce36ccb5fb28e4bd7ef7a88cdb9f0117948dd6d115298fd9c25473859b"),
        (34, 1752559667, "0.9", "450", "0x41d98b2f05ac27fc33c5ffcbf76f1726449aa7ada1bdfc61b42e1710f3214bec"),
        (35, 1752566097, "0.9", "500", "0x599bb43d53edecdf50db76c0ffca7aa9fad62937145ed456c9414ad56f248719"),
        (36, 1752566345, "0.9", "9.21", "0xbdf69534f2d930c46f3d3a99289034df87f33f3b276fef272aa4c265294d5474"),
        (37, 1752566381, "0.91", "66", "0x6d78795704bea422e3b4ff03a0d67c308e4dd7e964a9e6b1bcc2cec3ce2ce468"),
        (38, 1752566381, "0.9", "39.99", "0x7c28c42ad259beaa50dfa5fce433ea9c2b37433d7d8a2eb03326930084d81fd9"),
        (39, 1752566385, "0.91", "156.25", "0x1bfe15f1a6cbe4578ad607ed9b002f4b3effc5272c671c61d3712bb267dbbe69"),
        (40, 1752566385, "0.91", "66", "0xd15ed26906a25dffc0a77aacee8579d17f5311b07b3012b5307787acc4fc980b"),
        (41, 1752566387, "0.91", "53.75", "0xcdb4af7e5a5ac0f79df7cdc489178c590dad67e2e4c8118d63373848e8406733"),
        (42, 1752566389, "0.91", "1.08", "0x94a8fea60e9d4d7bc717a62ab3cdae985f48424e0fe30bf842765f1481c183e1"),
        (43, 1752566391, "0.91", "1.08", "0xe29ede1bc03b03df24aff9a73b680c0385072fd237168249e7169b294045788d"),
        (44, 1752566405, "0.9", "1.09", "0x295601c2eb70fb49d8d3a9aa87b26b279147a82722f043eaabf9f12423bb6b38"),
        (45, 1752566654, "0.9", "1", "0x1a63584c9c7809b0b5e326e9dc0c412322da1fc4de92aac72381954ef5897555"),
        (46, 1752566654, "0.9", "40", "0x43d1b1353c613bedaa5259b16a017a0725fc663f942c071aec1dc983f101dcfb"),
        (47, 1752566658, "0.91", "1.08", "0x97f704d8fc8e704a4023ed6fb6d584872b2c36690e6c5c69d17753c15370078d"),
        (48, 1752566660, "0.91", "6.25", "0x7c0a924863e614bffd1d7a374d7f352c32caedd0221a6edb25d54011410a45dd"),
        (49, 1752566702, "0.9", "16", "0x13845db32f1d9dd5fb25aa32adf875b0d84dafc9424256fcb4fe6a260d4c9429"),
        (50, 1752566730, "0.91", "18.05", "0x646872e987ad280d9e2fdaabedded51bf0a4f8c8c7e2b24b8eb6a02c1ee52392"),
        (51, 1752566734, "0.91", "6.25", "0xfc91b3d512b4aae24a99b23c680b916ef6b5d364d0d1fe5db01fc039aa7816df"),
        (52, 1752566736, "0.91", "25", "0xac37ab19c0c9d3ac9e0ad2d866135b57bf9aa8ea026f0f31c7d3d9cbe5da3d7c"),
        (53, 1752566814, "0.91", "102.22", "0x8190b494adb6cbde98aa2d7c462581a352cf0d1021593bb1d6e4f8fa8e0c9aa4"),
        (54, 1752566814, "0.91", "39.99", "0xb8a7f14f5adfcf69c7038956d0aae67681dd4d4082b90a4276e9323d69ca5ac5"),
        (55, 1752566818, "0.91", "12.92", "0x066a23f7aa3e03d09a07e9b6c587d0955819e11c00d44f9f5cb3458aef9cbe93"),
        (56, 1752566820, "0.91", "5.01", "0xc72386d326c69b5f5b99846418e4633eaffc58ff2b6ce40af8e8edf34a93ae1d"),
        (57, 1752566820, "0.91", "13.33", "0xe8ce808d47f8a5e4edd45e0ab16dfe27dc7ef50128a3f33a08970e4568f20df5"),
        (58, 1752566822, "0.91", "1.08", "0x1bc05f99d6bbe154a139365d69e6d4deeceb113b7d978c8a0e1fdc59647d6d61"),
        (59, 1752566822, "0.91", "5.56", "0x3aa0af0a77079a6f2b216e07286c4281a138167c710f93e5b2ccc0cc0c38a214"),
        (60, 1752566824, "0.91", "1.08", "0x968a23d97ac19adfe72d8c549b92298f245ba7df065949cf733343a03dad61a3"),
        (61, 1752566824, "0.91", "5.56", "0xed76948fd58b0225c5d33cfe98d025550eb8a14a3e971ba851b2ac5bef8ec3f5"),
        (62, 1752566834, "0.91", "27", "0xe04725e0ae1b3b3ec95afa381203c764efc6f690b5110439fb21b801e94b7982"),
        (63, 1752566848, "0.91", "27", "0x3eebb747f674ce723fff58f961530dd20f1e94b811d83147239962ab34ab74d5"),
        (64, 1752566856, "0.91", "5.56", "0x9785f7f9101fc5c4e1a28fa4411e7c99ecb7d675bf14fef3d8900c8b35b690fe"),
        (65, 1752566860, "0.91", "27", "0x352cf5282b19e373117752c59ee46c5fb1679bfcb5b4216de7aa71ec8df1a7f8"),
        (66, 1752566864, "0.91", "1.08", "0x78db69f4e21b9ef2891d7898dba8275e31e83b449360bf7bdccbb97ca061e8c2"),
        (67, 1752567082, "0.91", "31.25", "0xc3dd8e25c68dc36cb693ad785ce0df5967b7cd89682bb8fe03e830216c537e73"),
        (68, 1752567084, "0.91", "1.08", "0xcd3f800e4ed5e2b1013d0a5f3364be52135b954c0a3a2fbeb646c837ea146011"),
        (69, 1752567935, "0.91", "70", "0xb0f1cb7e5f80fc48fc93dca447a41a8009bb1aa75d9f03209170c4ce61f076c7"),
        (70, 1752567937, "0.91", "1.08", "0x18b865b947c7dc819b80a66e3f7aed4c89aeeb96eaa12502711f762ddba8b294"),
        (71, 1752567961, "0.91", "66", "0x4bc55104356faf0470c084dc4f7318a76a0d1dae46b48ee18d8dc74033c20297"),
        (72, 1752567961, "0.91", "15.28", "0xa2ad22058974054be026bf8b419128c86df4449b1ae94815782483ff70e34f68"),
        (73, 1752568194, "0.91", "23.8", "0x50d9cd613c85e9992f1ffeceb2a84f97c32f9a8a6eb9070b1a82663dc0472958"),
        (74, 1752568198, "0.91", "13.34", "0x40d75569117ba5dd8fa056e8721a0d9110779ee45b8a14ec209648767d1d9110"),
        (75, 1752568202, "0.91", "11.12", "0x2141055b64f49b8bea6329657dc36302d92ab0598a7be4fda5a31d03294e7638"),
        (76, 1752568202, "0.91", "1.08", "0xc368b9807756c3c7789998eac04a5b6124d977f784917e1fd3eda89f79821034"),
        (77, 1752568208, "0.91", "1.08", "0x3ddbbb02816abede181f45737f849f0e6cee6acb867cc3aa542edbff8dae8084"),
        (78, 1752568512, "0.91", "510", "0x50093bc25b801ddce8b50b950c88d1c735da82c8ef9336d1eb02aeb70563406a"),
        (79, 1752568514, "0.91", "1.08", "0xb3c434814c1d5f39d0bc0b31a6204f2bf2b09b34bc8ad149f84a7addaac36bb0"),
        (80, 1752568576, "0.91", "30", "0x983a5e192f2c61abe3f3636bf943ef30ae77f6e381e52d1f2af60191df7c1f46"),
        (81, 1752568578, "0.91", "1.08", "0xa16059147779360865841219596f7db752b57bddd29249c942a26c95c6177713"),
        (82, 1752569695, "0.9", "6.66", "0xda734d636f77267d57746a178de716f3b18eb72d2d9297d6024e2189563f877f"),
        (83, 1752569775, "0.9", "66", "0xb7a5c1264746d45862eec82671696c5cc2f60eba9928a5591f2f255d3f72030b"),
        (84, 1752569779, "0.9", "14.29", "0xe2c4b06ade6d045843e7bb20c3f7d961bec1ced5068cd51a22ce99632a8c3b93"),
        (85, 1752569791, "0.9", "190", "0xe5fa328f4f791b1ea4a8c74c7369657388387808adad1edd2a4f83cdbf675ae1"),
        (86, 1752569813, "0.9", "13.34", "0x3344567321e8d1155a2c6300178e3f9feaf2da0f12f946b9da287aaa034ea2bd"),
        (87, 1752569813, "0.9", "5.56", "0xada6e7e894628c767095932730f5f622bf47c6cb39da5ab14f68a6221a4bc47d"),
        (88, 1752569817, "0.9", "5.56", "0x7c99ccdcb92a63acc10b506ddbf6f01fc53a7b6c6dac37ebb21d6c0480f42245"),
        (89, 1752569817, "0.9", "1.09", "0xe285d836741291850fd7772d1d9339d5461178ddf2c5ad659efe2de4e8d6d00d"),
        (90, 1752570167, "0.9", "66", "0x2ea874d26c78ff338f88a9cbc9017a39eea39d503573ca48edc8d827be35166f"),
        (91, 1752570167, "0.9", "15", "0xa7a8e0d84c5b22b9ad3737abd8374b609b28c9414f1aa91a02a76297f1e09620"),
        (92, 1752570167, "0.9", "170", "0xae4f4b237c31b1067cb21e4dcbf09ee61fedd57764f4844dc5070eda722c5efa"),
        (93, 1752570169, "0.9", "173.19", "0x17a398c36261591800cd7f8819ca1269389c892564a444779f436dfc569fbb35"),
        (94, 1752570169, "0.9", "15", "0xe5efd30773f7eeb90c508ae527dc7c8022f35d6fa5fb7215c55c2f24ad3687e7"),
        (95, 1752570171, "0.9", "5.56", "0x2981c1a3146cd300c3dd8dd510916096f149f4d59201577632340b170a6b272d"),
        (96, 1752570171, "0.9", "1.09", "0x436cc60b662177378fe11744dcdfcac312e7922849745a8d270880740e797188"),
        (97, 1752570171, "0.9", "5.56", "0xd29e3f06c804a3c8f777904c0efddce13d9d3c25a1da9ab7ac94fa591deaf70a"),
        (98, 1752570173, "0.9", "16.67", "0xae3453316d77eac1454cbb49c67ba05a790c871a7ee34c31d5824f121cfd33f8"),
        (99, 1752570173, "0.9", "5.56", "0xbe754d0ba5530b51be915e5c8b755b5fd43b786efcda75bd40a27704f9ad0446"),
        (100, 1752570173, "0.9", "16.67", "0xf7c68114e696afa22df8ada0a9efb25f291308a07d9513aea2e83875a14aa804"),
        (101, 1752570175, "0.9", "16.66", "0x184c42018ac97418a3c7e2362b3782ef4258e99238c2e82faa800860d9fef31c"),
        (102, 1752570175, "0.9", "6.67", "0x97d715fad9d071bd54439f1da54cfff127308f7360939162c04e0b725403cec8"),
        (103, 1752570175, "0.9", "5.55", "0xc750eaa2226edd512e518c993b33e10976a7cd7fb717a1e09fed65d8ca1b4e01"),
        (104, 1752570177, "0.9", "6.67", "0xf4640d2285c5d750bb2821cf95e1179c2ae5af1edcdf09066ff147f9d475fcdc"),
        (105, 1752570177, "0.9", "6.67", "0xfd13cc8a395ca2e1e33336aad11e13c298a47e234151761970bd98e776a0c110"),
        (106, 1752570179, "0.9", "5.57", "0x23c95ea4e1ae4191c93c09c5b162361a1710eaa977b91389321e0d6c4ce70553"),
        (107, 1752570179, "0.9", "6.67", "0xf69d08b78c90105c7f4a3031222a53a8fed65495802ec24c67905d2c91a22d9e"),
        (108, 1752570181, "0.9", "6.67", "0x1d95e3dce21de8f902d4db54bb3352e29b4f313880800e0458e7dc7eafc41cef"),
        (109, 1752570181, "0.9", "5.55", "0xf040f4c1d5c05ac759f6d125e8893fa2b8795abdc8e7949dd19f66b544282437"),
        (110, 1752570181, "0.9", "6.67", "0xf73032d7bf0cbf0a03e0881ff038e64ef551cd2f71326a9e27194d8634344d02"),
        (111, 1752570183, "0.9", "6.66", "0x3567e5162d084d03f021dba53f7b868cdd8a84141b989da86d5d66ae679895a3"),
        (112, 1752570183, "0.9", "5.57", "0xf251e0f8190052b38e83d4b484d8a56dcfa997075ff87be476342f9eaec29b66"),
        (113, 1752570207, "0.9", "13.34", "0x4c8b116de34c21d32ffab3b7820fce8cd8bf2279fd29fa6966a7d14a19ea05a0"),
        (114, 1752570211, "0.9", "1.09", "0xcf8b81e0022c8c9e8ed7817358079597dfc062b44eb1c8da0e2749a535b725d9"),
        (115, 1752570327, "0.9092424242", "66", "0xddc701241886d4c3dae57b1909fb1fc0b630bcd03a44721c4f9cda09dd0b9caa"),
        (116, 1752570327, "0.9", "10", "0xf0123a8f935ef50b1e83f1ff21103ff11cb16b2f512664480f6853c4bd519bff"),
        (117, 1752570329, "0.9", "1.08", "0x87e7f4dcc9be1a0338f088f7c67aab1a2d73d1475ad3336530dc4b50f9b2ee2d"),
        (118, 1752570571, "0.9", "133.28", "0xc85bf533f5ee0c6f95582a7ef1a0c49b33f77463412ed7f3d22fc2c2242774be"),
        (119, 1752570571, "0.9", "66", "0xd26d76217f1ba19709773c2e8a86950879a3affabef8d3067ea7e45b6f12ebe6"),
        (120, 1752570573, "0.9", "1.09", "0x509afe9e9e903bc41f05e448a5dc813f2d3c44e450ec67d123a33d6130b8f27a"),
        (121, 1752570575, "0.9", "13.34", "0x226288bd5ca05952148d997ab9f382e6fa0ea4726655687a57715631d77f48cc"),
        (122, 1752570577, "0.9", "1.09", "0x0efd905e00f3e12c16380ddfcfc9102fb10ff94356c748c9d2f94c6e52babfe3"),
        (123, 1752570643, "0.9", "1000", "0x40ca2b38cb7873af10e771e27fd505247e70be485ff941efaf16a94cf689b4b7"),
        (124, 1752570643, "0.9", "39.99", "0x76e9ac6a676a13d7a44c7ca94771947e6159c4d3e175be0681eb6d1326eb010b"),
        (125, 1752570645, "0.9", "1.09", "0x1290cd962583e4e9b097ca4a9172a191ffa11cfa2a995c9faa0007ef4c7be82f"),
        (126, 1752570647, "0.9", "14.29", "0x23f454f7b451441d64184d6c6672f174b6d37d63f5c10b65316de56108463506"),
        (127, 1752570647, "0.9", "14.29", "0x47ff92a0428cf7208c87f9c3d78142c002254466b300df5e20b9bcdedf5376f0"),
        (128, 1752570647, "0.9", "14.29", "0xf0cddf3f551f5d9791c813c23f3a34e2c178b2fe01d073649bf4e347d07af768"),
        (129, 1752570653, "0.9", "20", "0x9d03552632d9e205f4e5fe6886173b7739505e6257205e39cd9bfb9a07195583"),
        (130, 1752570827, "0.91", "329.94", "0x4c7691b73119708b0c6849f27e984ab1de8480b1a081055added9e536af7bd9d"),
        (131, 1752570827, "0.91", "9", "0xab5e1a925197263af7e126bbadcaf6c73256358037858b82f503eef328ebeaf9"),
        (132, 1752570827, "0.9092424242", "66", "0xf1d64d1f037e29b34ff47c6c9dbaef80cf1b1bb19c00a4bdb7836b202d0b9c38"),
        (133, 1752570829, "0.91", "452.13", "0x6bcacd486c4ef3c57a71591643d0449c9556918f3201106f34e9de83abb338b1"),
        (134, 1752570829, "0.91", "39.99", "0xe54e32b95c42078b5aa853798c055e55a34307f49bb56dea6dcf97fc550ea47c"),
        (135, 1752570829, "0.9", "9", "0xe695c839d594616632268471e4eeed5c22cb71b97dbe70001a42a456770842a6"),
        (136, 1752570831, "0.9", "5.57", "0x3738a1f24c2b4f1fe5986c635896d9d321282aa142938e7ceaa974b6be4ed814"),
        (137, 1752570835, "0.91", "37.03", "0x9a177f6212d234d5c89df53b297efeeedd12098629ba9d27bd02b4e247d2e7b0"),
        (138, 1752570845, "0.91", "4.15", "0x844f9cb0ab1de98d86b045d4bbb91d4cb42977ac7fc357a675627edd1b12137a"),
        (139, 1752570845, "0.91", "5.55", "0xc791c33407fb85c6aeafd09f023cd341c4130b5641ae89fd734ca3bb2ffd7ca5"),
        (140, 1752570853, "0.91", "1.1", "0x95066e026019a285ee0ba05e3c95f34746b80cd194cc20331e4be4623841ae8d"),
        (141, 1752570855, "0.91", "6.69", "0xb5b08e97d4afdc54dd17e617638e4754ecfc8f8ba5edebf362b6f3a69fc33b7f"),
        (142, 1752570861, "0.91", "95.51", "0x55153d67b35225d41de85edb051c2e996dbb9e90a2ea1778c01f216a1ab215fa"),
        (143, 1752570865, "0.91", "16.67", "0x6da4f1f55593e4eb46b6f0f94e72aadd67166ac2a564bf38c25f3d71436021fa"),
        (144, 1752570869, "0.91", "5.56", "0x0bbf86fb5bebbad30fd2694237a6ce09d34e034e066f7d3a9a9978c004799285"),
        (145, 1752570869, "0.91", "244.7", "0x945a5d00c12b971fc7116cb3b29c7ac0583bf16eb1205a6e6968f12d251c5e93"),
        (146, 1752570871, "0.91", "5.56", "0x5131b13c1d4e71834ecbafd2b40eb9d4b261a282ed8712b0bf0a6c24cff44053"),
        (147, 1752570871, "0.91", "5.56", "0x6f2019bfca859deadecc388b5996818902d76c0beb69b5f50843526288c18f24"),
        (148, 1752570881, "0.91", "5.56", "0x38a20f963ffa93f4cc251e6ae0de87c3c5bf6471e938a2f5abf4ff9ccf6869ef"),
        (149, 1752570885, "0.91", "16.67", "0x2b3dd6de490481e59ec4430c7adb4db0988c81b89eebdee58e4356b583ff8b41"),
        (150, 1752570885, "0.91", "27.46", "0x2c65223b23939ed05a622ae40cf279fbbfbe107e3ee0ea938658e6a65d413016"),
        (151, 1752570885, "0.91", "16.67", "0xa94ed712b48061f7cd0347aa4ea207476925ba3d30b117ded370713d8ac74d00"),
        (152, 1752570885, "0.91", "5.56", "0xfa38dd0feb09be87f9020b2661c3c6cf2e23a1470504371b46eb7cf59060359d"),
        (153, 1752570889, "0.91", "28.44", "0x91dfcb8294b49ce280352ac936c04361162efdf6f1ec43b22864254f677b7541"),
        (154, 1752570891, "0.91", "39.99", "0xd5f306634916cd9c89a838d83c0f99676eece4158bce01fc93e7215dfe817926"),
        (155, 1752570893, "0.91", "5.56", "0x00b05eaa425db031c186df9b1b1f90678283396ca4807336da1eecbabe8f8039"),
        (156, 1752570893, "0.91", "5.56", "0xb69d8a5c0b9a5b11ace33370795f69b716c474861ef1bcf49de9ae469987ddbc"),
        (157, 1752570893, "0.91", "3.19", "0xefa54c4f9275d8cf7fe3ea5292cdd88af70bc2f5242da0a378fb650468c850e9"),
        (158, 1752570893, "0.91", "5.56", "0xf09b0a18c4c101227a8fee4934a8deda55645539c9fbf260f0c600f044b0c0c6"),
        (159, 1752570895, "0.91", "5.56", "0x66b795e83ac7eb567c540f487823b1c6129524eb7a7c6822fed987d404958dd7"),
        (160, 1752570895, "0.91", "5.56", "0x905f44dd0895df8fbe4e2ec48da3669b5dd45368f8a1fe57d5ae1d6a6d0c7e65"),
        (161, 1752570895, "0.91", "15.98", "0xdd2e71ed524575f06f2bc3ecfe8ea5c747adfb26c9ef2c9697b653f350207287"),
        (162, 1752570899, "0.91", "62.48", "0xf882b8fe4488f525ab9b93361d370c625c63dcac0015c5e8aaee194bb5738f64"),
        (163, 1752570909, "0.91", "242.29", "0x4b3f9534daa262d95313617a9636357fb659a9c729ce5fe9cd1efeeae4d47ee8"),
        (164, 1752570917, "0.91", "60.34", "0x56769818ef19478a81d24bb37ef92c9517ab754dc4c20c93d0b86d706f9e8ff2"),
        (165, 1752570925, "0.91", "6.77", "0xd912b5cea610c07d035a8cb03a8ff149a8ec7282fb6982484cb24aa4e5b11d41"),
        (166, 1752570933, "0.91", "271.67", "0x72d4efc3494e827887516f5de630c8387e42ba16c5a5f3718bebe350ba30398d"),
        (167, 1752570939, "0.91", "84.12", "0x8d3c04da56d074faaf6b368668cf0bbddd73c48fcbc3f34949960007d963e5ea"),
        (168, 1752570949, "0.91", "15.46", "0x91027d7f4926b9600480d5e47ec71a4142d065d4ebc734849827519ec4237585"),
        (169, 1752570953, "0.91", "39.99", "0xde4750bfe30755c2224f09cb27da262ca2a76070ce4fe38b36e6193d673fac7c"),
        (170, 1752570957, "0.91", "1.74", "0x428877775ceebedbe45d7b1051b69a89b53cc71cc63556ad25ba0d5bfbb393e9"),
        (171, 1752570965, "0.91", "242.52", "0x9063ffa3ec9924dda502ac079213308613f3f85f5a085442014b88f577f99bf7"),
        (172, 1752570973, "0.91", "5", "0x6f25f79f3fac963938bb677201ef63e96a558771994af6cde94b440212b0923d"),
        (173, 1752570977, "0.91", "6.66", "0x934da2831f6609d9fb2b550eb2c5ac7315e31ed2038cc331cd8c52e92a551366"),
        (174, 1752570983, "0.91", "110.73", "0x2d3bf674e7e0eff8ec78646448476790e7d3003e0ad8a1bb8bb1376e60e8c952"),
        (175, 1752570985, "0.91", "10.02", "0xa93a1f3d1df9f2f66b7227d5d545d00e89eadb238477d4b0006d032a4dc7a62b"),
        (176, 1752570989, "0.91", "112.27", "0x91b441e7431fb99323a655d6c76594a41e79c9544da7a992289c84fba8e3c53e"),
        (177, 1752570997, "0.9", "661", "0x2c1167cbb68777586bd0e33d2b8b43ebadfaf42bfcd35d8de72178f3d5f533f8"),
        (178, 1752570997, "0.91", "14.41", "0x677fb419b399564939bee9feff6eb1a04e839e9fd4ec35a87e395c1c24367763"),
        (179, 1752571001, "0.91", "1.08", "0x025ac86fe2e9b4276db826d2b404e2dee80982b9bbcc63e1c69ec26c24b313e8"),
        (180, 1752571001, "0.91", "1.08", "0x99a9fce125f77453e19c2c7cb3defb2d79d84b8675b49fca105ce2956826d755"),
        (181, 1752571007, "0.91", "9", "0x2288ffdaf5a647be44e42a9e13f46e7030f6b30e2ed190c705cfd1fb21734c1d"),
        (182, 1752571007, "0.91", "9", "0x2cfbe78d9f78b01712a9323490bd7fca0bac4b197723f31b33715da664ced82b"),
        (183, 1752571017, "0.91", "15.55", "0x1821e3ff1ee244d56ce16a8c5ad0acfc869cecd95097ed2655ee8629d4b4132b"),
        (184, 1752571159, "0.91", "66", "0x0282a826c3bc75d8598a16288bd12532690105d3aa31cf74c862e7b4d27ac372"),
        (185, 1752571159, "0.91", "250", "0x29bb8c2cfbbbe3cf53eadafcafd9a4990ac85d7f18f665fc0f07d1f8059bf6dc"),
        (186, 1752571159, "0.91", "253.36", "0x45ef6e985218b89c03c7c82a6bf880fb430d849ad2ae208f91d9314e6466cec7"),
        (187, 1752571163, "0.91", "1.08", "0x3708ca4578f0258346c178f5790f349e3c5b552d46286ba0cf897043d0881a7d"),
        (188, 1752571297, "0.91", "9", "0x28a4e398c81ad196e135a2d7c94076bf9712dbf28c372ad279675a14c0483b80"),
        (189, 1752571297, "0.91", "40", "0xea32317c297f2cc739562f94475c57e3c28c10bb489b7a999ef5008f33dd376a"),
        (190, 1752571305, "0.91", "1.08", "0x1c9785971c9241866ed1f6de4e3b0572e894172b70620d48d5ba06a6d757b18e"),
        (191, 1752571305, "0.91", "5.56", "0x5b063bded126305a067a969de2e48f9a04a10d652ad034633da44774e5c715c4"),
        (192, 1752571305, "0.91", "5.56", "0x7f827ffeef78fcf29be61cafb0b9560e0e559b7e5db5040cf4ecac0fa5f96eb6"),
        (193, 1752571439, "0.91", "13.34", "0x58bedced09f91de658f1126b2fde00b17f2415142d514026fa05b65ad940022b"),
        (194, 1752571441, "0.91", "1.08", "0x10b5d5b359f909dc01e89f6c42b1314ab8675b337fa87a33d3033748c209109c"),
        (195, 1752571443, "0.91", "5.56", "0x4ff17e7067d540657afce6ad726378df95a10eb4b9d46a98dcc493126acb4637"),
        (196, 1752576527, "0.9099999971", "6.868122", "0x60c0ddf65399ca0eab841c907e941561b2a0eb67958cdb3403c2cb66e92f01bd"),
        (197, 1752578841, "0.89", "50", "0x25b8f473d1ca8c1c9a0c73855d0de5744fbb23622d29239fd8a6aa905e9c8120"),
        (198, 1752578843, "0.89", "1.1", "0xc79cee711578cf8e1281e1f1b0de5c14947664bbe3cb25c806e69a6e953c7810"),
        (199, 1752579313, "0.9", "17.99", "0x53d355716e80bdc34c4ea185f3c65e7e0aa4daf2097160e7f3b722873606aaed"),
        (200, 1752586235, "0.9", "3333.33333", "0xe1f0fead883b4d2acc3c96de445dd758879be9d642fab62a845186708f54f63c"),
        (201, 1752589053, "0.9", "290", "0x24f3b4613c963c17ae1f74520bb65eac71f748bf2b0cf868b91777e1fbaa1d95"),
        (202, 1752591263, "0.9", "26.08", "0x3805b8293c8cc34719dbb5c6bccc87ed157d60e970cd7ae1acbe12e1ddaea0fb"),
        (203, 1752598682, "0.9", "200", "0x0d7766d38f9d864998665ff232724b7f3f1afefa2e4ab5c3ed6fb0949b703ad7"),
        (204, 1752598682, "0.9", "15", "0x7f944d67a52faa7ab97a3e5ba977570edf6dcadb857fb8bff81dfa65e84c8646"),
        (205, 1752598682, "0.9", "15", "0x9416535895ce65c67d6630128d1532ea42167e76cb931da0e2c34b907bd4381f"),
        (206, 1752598686, "0.9", "1.09", "0x1cdd2a20793eca972f9d736e454dd3876084ccca6be21685d58cd9aecc9bc6e5"),
        (207, 1752598686, "0.9", "1.09", "0xdaf7c14f8a7d104752ec9be0dae6891df309d21d9f8c411d1ad3e4aacd38286d"),
        (208, 1752598686, "0.9", "1.09", "0xfb82b0c9272b25754eab21b9a91ae6bf5e30e6d2cc10befb95aa8e4d91aa665f"),
        (209, 1752598740, "0.9", "125", "0xdf58f8519bd45c9f07fbad2d161410059995c18e081b3b4b05f54f8e4c321743"),
        (210, 1752598742, "0.9", "1.09", "0xa4f592136226aff2e5b39ec12ce8a1622d9c915d32f986192e0fed7f09cf24df"),
        (211, 1752598894, "0.9", "38.5", "0x6d0cd009abbd029b8d3b69e0211fc6489321b8f90867e256364646499d476159"),
        (212, 1752598898, "0.9", "5.56", "0x22fefbb3c141cf029faf533b3612bf43500e59d87b99faa2f7c81b83ecaa1d88"),
        (213, 1752598898, "0.9", "1.09", "0x4cb496ac6213f73795cb44b85ece9ddc5d70b8818ffa9d8724c95f34bc76bf58"),
        (214, 1752598910, "0.9", "119.44", "0xcf1f5dae856aaf82414f18f894636f2bec997cbb524a20d1a1ecfe5a41f7053c"),
        (215, 1752598914, "0.9", "1.09", "0xc1fb9dd11fff6feb53660a217174423f47e855b84e2efcb08e32ecaf1c5b880b"),
        (216, 1752599261, "0.91", "29.99", "0x91eab471b0045b6c502db1fa7f2d7da4956e0d48071c464daefeb6b911612dae"),
        (217, 1752599263, "0.9099999935", "7.736255", "0x01467d2bf68020d935e0718210dfb5c3b105b642c0122ea150ddf6ee0137b586"),
        (218, 1752599263, "0.91", "1.08", "0xc4448c93807ec71c9d6fc94b0495cb63541887033706cb79e916ef4725000d83"),
        (219, 1752599267, "0.91", "1.08", "0x0b66e2dde268221ae4af7fe93889a505aa5feb596ea243fd1a0974655bf3c990"),
        (220, 1752599267, "0.91", "1.08", "0x3e94deb501c07a275168a4a407aab29c4241d09d26b25eeb757c28db20e38dbc"),
        (221, 1752600801, "0.9", "20", "0xaa1a74687d6f5cd36ce79998bf03399fdb8c897247aa851cacb5a3f9f35b211f"),
        (222, 1752600805, "0.9", "1.09", "0x28805f4a92c0a8c30ac41bbd5135368049a21e3ac0fd0e3880150236b50cd88e"),
        (223, 1752601815, "0.9", "10", "0xb8edbdd1a673a34ad610b76ddcd3c70c09d1380676a20c00f932a6aad19798a1"),
        (224, 1752601819, "0.9", "1.09", "0xffbcf76b498689aebbb3605b9179c61fd7d0b858ef9d8efcb72c6ea681270a82"),
        (225, 1752603431, "0.91", "80", "0x5ab8d817626aa0c6d492813c9e7aed6efe98b009cff5fef1361f9f049b511fb7"),
        (226, 1752603435, "0.91", "1.08", "0x6ca0fd718cc6c4f7cddcc3304a65c05af534355ef075eebf23a5e72dcefd153a"),
        (227, 1752603501, "0.91", "597", "0x301373f5e9bf3ee3c7861c5edd588e08eb203990b4192e71074288e42379ce98"),
        (228, 1752603535, "0.91", "30", "0x222193945148866657e2b6756861aaa28b2a69f3faee74e30bd546cbd95959a5"),
        (229, 1752603537, "0.91", "1.08", "0xa4671c7e12b53629203a199fbb8885d6533d2ed8c1c8be704c1faff3c65318c2"),
        (230, 1752603543, "0.91", "33", "0x5fc2f84668824fd35a7baebc1228626401a1379a443e762f80511a2b9cd4be7d"),
        (231, 1752603543, "0.91", "20", "0x7b26a249cd19f206b6b26b942a24db1d4b3b5bfb2e7d8125bc03c868fd730e4c"),
        (232, 1752603547, "0.91", "1.08", "0x5857965483772d896312174632e90b710581040b4f1b64f60ec2ac6903bdeb2b"),
        (233, 1752605436, "0.91", "111.05", "0xa0ca9efe5e74eeb080897055c107b3fb0ec48b457850bd66f3929b43e96acdaf"),
        (234, 1752605694, "0.91", "40", "0x9e097a7b24ba6a1511a12327a00550bba7029c56666330b573ea66d70d3e8bb3"),
        (235, 1752605698, "0.91", "1.08", "0x183265f09069405105b32888f960783b0a0ff93cec2a9be1857a407dc6087862"),
        (236, 1752605920, "0.91", "270", "0xf15dd6be925561c46456084d6ecbc80f4ceea0265cbdbed1fe04aef3a12baeab"),
        (237, 1752605924, "0.91", "1.08", "0x037c59b6cfe48efbc7e60ec168b400080710949121710b662e96f694d93ea55c"),
        (238, 1752606524, "0.91", "40", "0xc27bb490db0c263bf5c7f41956c8e4ff0cadf0c4a9c8801bc9d951491027bde9"),
        (239, 1752606972, "0.91", "51", "0x7f5984a6741688fbd53d460fc9a19154e0efd8e9a8e22eded08a798e60570c39"),
        (240, 1752606976, "0.91", "1.08", "0xe40675637bd49ee5b3994c3c115861c9bd90578bb1ebba53a1213226884c0893"),
        (241, 1752607258, "0.91", "200", "0x5f2d683c0544dc44c4576905e595d42ade678b5a9e9eebda311725c427748f1e"),
        (242, 1752607258, "0.91", "200", "0xa1f2823e89a5b41417064ef5e444cf3dd43cc316a416267f533bb8f112a4a138"),
        (243, 1752607258, "0.91", "40", "0xa6d41f9ce8267995ccda1f17166d413d13e6d45eb91dc99223ffafb791a30c05"),
        (244, 1752607264, "0.91", "1.08", "0x7a854b96681cf37aa6602a000893ec546f3ebb75d393dfe695b222cfeb93ff40"),
        (245, 1752607342, "0.91", "1.08", "0xe5aa75fbacbac410c134c0825c1cddd55917f035fe45c9fb11467acf21367e70"),
        (246, 1752607394, "0.91", "250", "0x87a016714387d46cb6761c74387057594d11d75aac573016c8734f89f610ee2f"),
        (247, 1752607428, "0.91", "40", "0xa8c38088f5a7712020830f27e28799c4ca2c28f653cf88f848e1cb9183419bbf"),
        (248, 1752607430, "0.91", "1600", "0x20065744a141ea9f32d71cd59456cb74ffc3d4770a5a09aeecd227c83a6fb21a"),
        (249, 1752607556, "0.91", "39.99", "0x01797c2448cc99c32361b5ef19975edfe19d813881e9abcf775d9bb719860d6e"),
        (250, 1752607556, "0.91", "160", "0x86ccd2b3afd291ef9e3dfc84202f68803a91410f9da31ec812fac19874538b68"),
        (251, 1752607556, "0.91", "167.24", "0x87476926500739bfee9753cc2c54a0a79aa417861cfaff04a6e776a1abb2be5a"),
        (252, 1752607566, "0.91", "24", "0x2eea7c6021c2fdd893c84c9ea0cd623c45123d0a671f480a58e7995e65ef4979"),
        (253, 1752607570, "0.91", "40", "0x2ac1c0fec8644b5db94c49e571c6bc22a47a619546fdcc78f6648769a35c8ad7"),
        (254, 1752607578, "0.91", "16", "0x3e23cca16557742a460a679980816e78229b46df7041e2f799fdd0fe5832ef31"),
        (255, 1752607592, "0.91", "8.93", "0x4d67b5c4317e19e14f0109023ce017b891031ad8e31a24a37cf432aa6412518d"),
        (256, 1752607602, "0.91", "31.07", "0x809c4ea12db4a9ec832bed262e48c232c0862b92b9795ec2d655d15e7455fc0f"),
        (257, 1752607636, "0.91", "10", "0xe28809f42be0405eda0689fdd393c5c78c846e9f185cbcbb08605b7857b02266"),
        (258, 1752607638, "0.91", "14.29", "0xd05949e6da53f6de9dd531dd37e92b24f5e127957a3a1a5606fe550490685918"),
        (259, 1752607800, "0.91", "39.99", "0x5c6ffea74c189339e6436c86624838f63433b00a11921e12c0d3df1ca2324d8e"),
        (260, 1752607800, "0.91", "820", "0xaa78d2b4f2d8a7663648892f8e26ad3f4ae32cf99a7b603976cf9641122687a1"),
        (261, 1752607802, "0.91", "140.01", "0xbafc67a6f5056c8c37ef489171e7e297f043c1301c497f95df91fbd655a23ef9"),
        (262, 1752607992, "0.91", "160", "0x5149276951d2b18095d44d5aba655c8c2e945924b6598713cb9920f23f7ef1c8"),
        (263, 1752608596, "0.91", "209.97", "0x07f01b29b24a8ade6fc84da8ffa9e0021226e61d895deebe52f1b45418282c0e"),
        (264, 1752608596, "0.91", "40", "0x8e238dc0feec625d47e7ac41b61fdbbb966dba32219b029ddb71a49ffd1fbf74"),
        (265, 1752608598, "0.91", "200", "0xa3ffc40dd614ad0979af9c97e6993269ffb427f874e4f8abc104fb855bd3324a"),
        (266, 1752609072, "0.9", "599.91", "0xd837d63ed9fdc455eedd790a3528c9bcc15c311afa060586b10c6750b18c301f"),
        (267, 1752609238, "0.91", "10", "0x2699470c2215e72a67a1d74be1b13f527db3a5d33f6ab5c8b2eb4bf9b0dd0954"),
        (268, 1752609242, "0.91", "13.86", "0x5a232b3cd1bd5bd286c99c441cffabe69541c194d7c355d6ac175c9542261861"),
        (269, 1752610080, "0.91", "5", "0xf692ad6fb09160aee1a006a2880e6fc36eba8ea61b5485eec7fb93d072a548a4"),
        (270, 1752610184, "0.91", "500", "0xf57112681018de30d2e65dd6f9ff491882973e0ecba922e142b2503db618185f"),
        (271, 1752610776, "0.91", "50", "0x1a175c84fdf6337133e35ae71e4b979b945073b23610b5543d084835f76bba13"),
        (272, 1752610776, "0.91", "346.67", "0x3dce1a602eb37b34c08780e074df71c5a9faba7a3321b49d6e973272bf1f5f74"),
        (273, 1752610776, "0.91", "5", "0x6cb4e084c3f226a1a2f8b1e0e27ab93d8a14508b8e36dee8d18e53aca0be10ac"),
        (274, 1752610776, "0.91", "346", "0x8b0b1e9ef1fd9f23064a609300efc61838a4505de2cd0e4b3a82de157b17eecd"),
        (275, 1752610958, "0.91", "16", "0x7d7a17244f9a2d56cb1e52bbccbad55b28f674cd83d4d3ce6753fa38849e21af"),
        (276, 1752612397, "0.92", "100", "0xfacc8798c749bce2e250b92800201ed6dde4c4237298e02d679d4578d5d46679"),
        (277, 1752612411, "0.92", "14.95", "0x64d5f84941daf73bb12cc16b86a76bb73d01d27bd75d7a06515a9f7cfc1486bb"),
        (278, 1752613959, "0.9", "20", "0x235c15f370156afd09466c545fc2f81fd2bfb168b410cdbfd4da05d14df0b9ee"),
        (279, 1752614923, "0.9", "17", "0x4301b6b858dd71698c53b2133664ec17b4ecb719d1ba4db6713b16af79cb933b"),
        (280, 1752614923, "0.9", "10", "0xeec20191fe99f5608ce28c11933046affe057d62d25120867abda517e3dcafe7"),
        (281, 1752614925, "0.9", "5", "0xb6aba54f58f1e640391ed0c1eb183bc4508ba9c62bef72dd0c28a3f095841142"),
        (282, 1752614927, "0.9", "1.09", "0x69e3a1c011648244fe610d9ef263dfa81f850a5718e4779a4f02d81922a4e925"),
        (283, 1752617199, "0.99", "50", "0x50ff4a596d8741ff39850025e53a112e21b867b7089c12fca1b6b1dfa693c35a"),
        (284, 1752620217, "0.65", "10.9", "0xeaa321c1a2e1019fc0c8e50e22533186b40890745c01b0d1778de8618561549f"),
        (285, 1752622987, "0.96", "39.99", "0x5d6a7c57b29088858545c7da84d6de6ba88a3b1f83c60bd3537465bcc85f2bca"),
        (286, 1752622987, "0.96", "50", "0xf6730a043247c2865048cae06b69efb1ab6a32e0a39e38ab44068c5e2c19c6b0"),
        (287, 1752623711, "0.81", "42", "0x17d3a6ba7c2ad42a3ecf30da742c176c5abd0b9372f0643c562dca22103695b3"),
        (288, 1752623749, "0.87", "19", "0x505794816119938185aeab8135877bdb26e840ee07b2cc33895177b845467bce"),
        (289, 1752623749, "0.87", "10", "0x859881fd37c7fa033f4e44c17ea8d39a18914e9465e2577451a29fe742da8eb7"),
        (290, 1752623827, "0.9073676351", "15.043511", "0x0f6360aef0cd14ba8529471f5d89307733d71ead5d197f725bfe18cf998f895f"),
        (291, 1752623827, "0.9199999578", "15.163042", "0x196dd2fa8aae50a6f92b0df103a85721e657b04a1991f3e5b703f25230d1fb35"),
        (292, 1752623827, "0.9298120378", "100.020214", "0x950e7fb66431073837629131949e978597c5792c977a2264d3377f15244b9cdb"),
        (293, 1752623827, "0.9255119591", "102.494614", "0xb64d8ef27765d8bb32c07e721e6d7a4c29af8662955100835aa9c2284f3c3e36"),
        (294, 1752623869, "0.91", "16.99", "0x243bddf1ad902cb8f4daacd4b3cc66108e40ba23cbf72c56019d72f2715edf97"),
        (295, 1752623869, "0.91", "10", "0x6b5471e07bee9f174d2f38bce65c1b8312ac63d6be9d253af22c007b45f2715f"),
        (296, 1752623869, "0.9154975", "40", "0xdc48c066a1b7c97a5e6fb5dac8dde020aae8e965d3d0253f1db9c5717b56b413"),
        (297, 1752623941, "0.87", "50", "0x23e3ba72492c068e50141486f324fc803fb46e04884a9e0fec822a585a6f75ee"),
        (298, 1752623941, "0.87", "39.99", "0x2560d5da764e2363260adf2bf4044f50b29ae03f14d10cf14e785b3076ee53b0"),
        (299, 1752623973, "0.85", "10", "0x15187b684eb2c0188378fec781906c49d1846785cfe83e6c4e2ed9b2f32da11a"),
        (300, 1752623977, "0.85", "5.34", "0x747f9e8f7d98a9c62f7a31c49f8c1b9d5695d4bb2023a1b4f6fcb82bd8af82f7"),
        (301, 1752624041, "0.87", "10", "0xb1247385797edd67895f2d4a4c47916adf2c59b346a81ab9b19582b0a06b1d29"),
        (302, 1752624117, "0.87", "100", "0xb9b59f26aad515d46b84663743696c8321e976f0e298a707a0497752d06f0de1"),
        (303, 1752624119, "0.86", "20", "0x10910a2097a3dafd36f31c4ae3fd34c8e831f17e290ea68829e15847dbc59dc1"),
        (304, 1752624119, "0.86", "5", "0x1111835b9b046bf252d5b685811d84ea8e97dce6a4159631f7010898096b3e03"),
        (305, 1752624169, "0.87", "110", "0x62cac8c0fcb925d68677e93d27b4a048d6184a967533424c67fabd16df6183fc"),
        (306, 1752624185, "0.87", "20.99", "0x611f4b04f68dde51bde611d1d8b27679d0d918c565e783f1fd0cbb09033683e7"),
        (307, 1752624271, "0.87", "100", "0xce0a409ce046446749ebb8a0b9d155dd9ddd8bb01818e390f9e4d5e898ba8a7c"),
        (308, 1752624273, "0.87", "22.05", "0x00bd9a18ceb2f6c56b3c684665fa868a0de74c37cf5224d6a1283b06e42a5838"),
        (309, 1752624303, "0.87", "5", "0x64c5ad6b539fdfc150a96f4e1e9739d8661749e7fd2c0e0ffc5edc6164c099b9"),
        (310, 1752624329, "0.86", "39.99", "0x966244715a44ddca69f53f1bfc8cbf36e7e887cd0d47742f88ba2fbfb050ecd2"),
        (311, 1752624329, "0.87", "6.81", "0x98a44eceda6a019667fd8c1d1e2a3dd36dc8efdf8588ecbaaec837fa79146c8a"),
        (312, 1752624329, "0.86", "110", "0xcfdc306fd8373010ec6e08e7a6cdcd3652cdf43170c5ffcfcbae19279362cb77"),
        (313, 1752624385, "0.8690950276", "637.92", "0xc0bfaeddecb68904f2fda0d09656a4fe917576b06ae5bbc3c3c1f35fd16659e6"),
        (314, 1752624513, "0.85", "5", "0xa87085a83ff9a126c5d027f71390d70525035f22840989e967078dcf69243780"),
        (315, 1752624597, "0.8489007703", "1137.16", "0x64b7bb4f986ef7391533ab0ec44681c389c1d4d85070a489be8c9f45ad9d2a99"),
        (316, 1752624645, "0.86", "535", "0x7e335baab83e6b02017172d36014bfee2bd956700e1389cf8f15b8937d0c538d"),
        (317, 1752624935, "0.8795", "100", "0x1b907ea7cbc47c6e6948c0d6e0a2e3444f69fd6a816a904d5addbfd3a52a46d8"),
        (318, 1752624935, "0.88", "30", "0xb4d2d403f4b7cc27c49dd67cd42734daa4d90d5a7dd330b0a39c1c6b34224eee"),
        (319, 1752624937, "0.88", "38.99", "0x8ab6438614a1361201c48c66cad8ea175d3d34901f3a4dfedbbdc3d1d50a9759"),
        (320, 1752625003, "0.88", "50", "0x3df96625a253829022b9fe9fbeba44c6415018dca9c37df09a08ed6b3e70b114"),
        (321, 1752625005, "0.88", "250", "0x2d14497368a9f4273fbc94e9e42708546bfeac4195901a4b4f4e9c871a684aae"),
        (322, 1752625005, "0.88", "250", "0xc22aeebbe20003b4dfd7089e39bbe7af4cb56976174e4be11cf7a6377bef6a4f"),
        (323, 1752625129, "0.88", "400", "0xd9da609433dd9c7a606bcd23d7334db4eb769b6a5d9d3418e2fa06c2b9eab467"),
        (324, 1752625149, "0.88", "1341.01", "0x478259bacc6de7a1cca6b9c2630a6fc5ec10b8fb0ea318559b1efda93169d986"),
        (325, 1752625901, "0.9699998332", "5.154638", "0x3758b3dba30c48db649af8365d8f10cc8f382772b0b15a8725cb04b44c4b77c9"),
        (326, 1752626141, "0.9738337459", "1304.99", "0x0747e70f49e08fd25aaba951a40efdcfa4e52a5f64f98a50e78a78dbc3c24866"),
        (327, 1752626309, "0.99", "35.01", "0xdeb7e468bcf9eed74b5406af1116ec474974629ace43de863f44f7f1edea87d8"),
        (328, 1752626741, "0.999", "9.99", "0x311f93af7d7129e16cdb998e6c9f5ced68c24ec322008fc6de838f25df6d8630"),
        (329, 1752626741, "0.999", "10", "0x3857b8fe67d5760d91d83258b3d6d64429fad7ef110ddab0da3d2624dd3de47d"),
        (330, 1752626741, "0.999", "10", "0x4a23462f16017a539df3c19cee4cfafd0288afc7c9dc71ba64001aae6fd8d07b"),
        (331, 1752626741, "0.999", "10", "0x6211f5f81f8a59c4ba3bbea9f8c83080807b0dadc13b33220b4432d1aacdf3ed"),
        (332, 1752626933, "0.999", "40", "0xcd8cd6818fce6150dedeae7f09ad559052e59181c29fb865540a472c91f8be79"),
        (333, 1752627473, "0.9980252143", "1983", "0xbeac9fb320ac8d13c3f90d0ca9277f068a24b0173352161986ff177030b6c7a9"),
        (334, 1752627483, "0.999", "50", "0x8c1e4c7bcf35c786d8afe5615a70fe1a02f0ae4860ae6be891bea62494ec6967"),
        (335, 1752627663, "0.999", "105", "0x1a43bf67fbfedc49bb55f50c39158ddaa8c71b10e0d698643955e1b0368eb242"),
        (336, 1752627699, "0.999", "55", "0x91d0e05e17ed126fee087a364965b94cd5096069abd73f7291c5c81b94e22223"),
        (337, 1752627703, "0.999", "24.99", "0x34fbc25a899c8cbdd4451eaa85e0ea83c2795f4d66e8febc1f079cc81da5f29c"),
        (338, 1752628251, "0.9978700565", "2655", "0xe83a596152106f01eb5b83ab3e4dca0b546295e978d01f81778fc3c3d1e28b49"),
        (339, 1752628257, "0.999", "50", "0x7072b30e4d8dafe61d01eee3f39bc8617ef97c5fac5f9edbd0fe61cc490d2f1c"),
        (340, 1752628395, "0.998", "66", "0x7a5ba3b0a220d3d64ab611a2407181474020371d96095cdf49cb8ba6e9d08f12"),
        (341, 1752628423, "0.999", "50", "0x6dc03fcec66e5017f92bc27c8e892f5087852ab660d29999e434650ca26ee345"),
        (342, 1752628625, "0.998", "49", "0x2a19b319ae4f43d9143292ed40d9f894a797ca92d26c24d17c28e59f721a97f9"),
        (343, 1752628741, "0.9986642359", "6308", "0x08836ed2c00de1aa22e9402752c6f7ad95c32b7c985d02b74097d114d38cb2da"),
        (344, 1752628887, "0.999", "4035", "0x0e2355f2eff9519bb9ff632dfaea5dffacc66189052058635b48030336ef27b9"),
        (345, 1752629163, "0.999", "4145", "0xac6cfe1a3c1ac17714424c994d92e65c1b457e427dc1322c15ff12fa83c61925"),
        (346, 1752629399, "0.999", "250", "0x0d77def179efdc1465bb6c44d6b18ba71791aaa9df77e0f9516546878d1b31cc"),
        (347, 1752629399, "0.999", "5.005", "0x609682a25fa735aadd021c1bfa72310dd21e30910ef00699966dd5fc6e420f26"),
        (348, 1752629399, "0.999", "5.005", "0x78357e219e93f9d4ecfeb5481700046f23c213872b00be93b8ff398491e1fd98"),
        (349, 1752629399, "0.999", "250", "0x92f09691e8973618e9faaa946c9be9f1913156b69c5e92a5a6d698e1d90ee189"),
        (350, 1752629485, "0.999", "3494.98", "0xd2729ea5331e6220132e1dd0abcc766160b43dd8f95b31c415e89ca8a6cd3027"),
        (351, 1752629487, "0.999", "50", "0x3d05ba6a7d6ea8eb6433458b4431486b12de6ec4188e2f5b679d949a546824c3"),
        (352, 1752633595, "0.999", "400", "0xbec9f4483a23bb6bd938e8b49e66ad86b4663b840c64384b6802b685b6bfdb8f"),
    ]

    fileprivate static let retained563326Yes: [RetainedTrade] = [
        (0, 1752504917, "0.09", "123", "0xb7cca775d06df194d32a2bf92220f98cb87621d7fa3a4282268234134c901a3d"),
        (1, 1752507421, "0.1", "200", "0x2b7b7f9a8287253d45fdbf868523420f6e76947438e814799f980a54d0d21ec2"),
        (2, 1752508331, "0.1", "10", "0x753fc7d305ec196d39dbb42d86bd56d78d1d69242853be1f9e2210b287138f97"),
        (3, 1752520347, "0.09", "12", "0x17cbbba5d92b08e7b472c540c00a19d2370cf034ad35da2821714bdbf94d87dd"),
        (4, 1752520513, "0.08", "8", "0x7c528c2f6dadbac69023fec597271b4248eac15b0bda882ffec773d5da484351"),
        (5, 1752523328, "0.09", "1575", "0x1ae32e657daa58a0ea58915bad5f6a5610d4cf56e8801294dfe6d2fc742776aa"),
        (6, 1752523346, "0.1", "100", "0xa6262e1eedfcc179380b18c144d0a826fb2cebf2bf88042c23a36db2c0aab591"),
        (7, 1752526502, "0.1", "20", "0x8327ff1efc3b26595910d453a13e57660e5639adcad39f88b2774cafe8047041"),
        (8, 1752529049, "0.1005818707", "109.363635", "0xe8b6c6162a13742c9bdd4f213dff28b6d962357659da725eb8c6c21df0df26c6"),
        (9, 1752531593, "0.1", "145.2", "0x86746cf95abaab6c52240ff9ec554f4a0caf0f4850fa57ce832f6c42f88ae2bc"),
        (10, 1752537417, "0.11", "2000", "0x1b257f7b272fb0570159627c43d7e03a78418454a4ed5e9180ea64e53ea56b6e"),
        (11, 1752541697, "0.11", "91.63", "0xf645014475fbdb921e462bf3db61ef4b08a79c17cb3c326617479c90d841e95a"),
        (12, 1752545181, "0.12", "30", "0xb14275092417ddb2574a88fc60d2743abaf58d997ffaebff5a287308a958cdde"),
        (13, 1752545815, "0.1", "11.63", "0x64828609ce40b83ef8e587c17a97c9779adafceaca308696cafa74c1e9f3b173"),
        (14, 1752545823, "0.1", "23.25", "0x3e7e159a336bb8f7f1f2d0559e52db38b0aeeed13a3e68724f771fb9d56abc13"),
        (15, 1752545823, "0.11", "44.88", "0x6b1255ed5bc7285c73799d50eb3a736e4920e957abe1f091d04d83af6041ccf6"),
        (16, 1752552353, "0.11", "3088.32", "0xc6a887a929d78c373b6f12d3725b380dce5e799d9f15c983222615c183cc68dc"),
        (17, 1752552355, "0.12", "178.57", "0x879ac879551769c75dec6ccbe6b45ff404f669845aef839efb855a73d8dd70f2"),
        (18, 1752552377, "0.11", "5", "0x06b442e6c8fa76bdaf83e76c759a3290f55d8fc5bf7548192733ac58452350dd"),
        (19, 1752552389, "0.11", "3.01", "0x3c87c12ab65c1cb60dc92d9c4e46f60d18cad44559f9c4eb4ff50a92b3668c07"),
        (20, 1752552401, "0.11", "3.99", "0x309b97eaca63a4283f01ab61db70765b9b6a11c560876129b36fa46ae1d57e61"),
        (21, 1752552403, "0.11", "21.01", "0xc19584f13d6902145eb5b12089721a358ec2bb450d33af1681fd6848eaf27cfe"),
        (22, 1752552407, "0.11", "5.99", "0x2d990a8540d6676e36dba7f196d91412bedabdfc6d820014d03b42ac809fe329"),
        (23, 1752552411, "0.11", "27", "0xeefe3c814e3db3e53a26231aa0d27617b6190f733094d053f4cb3557b8eb58e8"),
        (24, 1752552415, "0.11", "11.01", "0x5e5dc3e01e54047395a73c361b46007c9a2bbb09b2b7e11e6dd921db816722bf"),
        (25, 1752555149, "0.1246216294", "264.801537", "0x20a35e951cb9c6677f67c85596427310ff2dc3a15f777ccc5e9aad61981b423d"),
        (26, 1752559301, "0.1482213394", "168.666665", "0x9039a35af121531245b03a7bc80133df1df0bb341146ab6606aef61d488a4ecf"),
        (27, 1752559647, "0.15", "100", "0x47f2c36f3b662b22ae44d313693ebd12eab276713cf3aaf33b1df39a760aeb99"),
        (28, 1752566041, "0.12", "29.99", "0xa767dbf48b8be8e108176f0f09809ff2d8e4e2ccf3bc0b9cb3de4749a9d215e2"),
        (29, 1752566381, "0.11", "33.84", "0x3610c338ed77b10ceca0d7a7280d3a633d85f4c91fbdd75ea907e1b6c1b73172"),
        (30, 1752566441, "0.11", "69.99", "0x208d384925f9e4a19524a8b55d9bec3676b6dcfc572c791068a04e107ea8e481"),
        (31, 1752566702, "0.11", "25", "0x240a64e531ec540458533a7c365e7039ff465ccef85178d3b846b872cb1507e7"),
        (32, 1752566750, "0.11", "22", "0x2a3e5125edc6bb70cc2d7f5e2b3be997e3e8627bd924dd3c663c45ed8001f15a"),
        (33, 1752566764, "0.11", "11.66", "0x56b9c30f9c15f5297651394ca575e9291583d1a2fb1299f6f8639d316826e2f1"),
        (34, 1752566814, "0.11", "206.62", "0x623eca9a4d7ddb215ee245a8f10ab2fc4261899b917032b1a1a95898bbfe57e1"),
        (35, 1752567961, "0.1250560341", "1199.462306", "0x099a72b2faf92d227243faac1e928011b40f2c1807d3d61b5ed8072fb42505a9"),
        (36, 1752568522, "0.12", "1.91", "0x13dc85e0d8172c2e8c59d54fe6b5f0a2993466f14b467ede6c8a1437a7758a5c"),
        (37, 1752568576, "0.12", "30", "0x7cacdec775a8c31cdc230a63092d22d8df8321ba63d180462df69460a10bd998"),
        (38, 1752568578, "0.13", "6.67", "0x8b00a9159f41ffd672e3de219bb1356623617d10a02b92dc167e6253b41ea0d4"),
        (39, 1752568714, "0.12", "5", "0x27e4a64991952d749eb80b8410f375cb86f4ae6becbd41b881276f4fba71ba05"),
        (40, 1752569795, "0.12", "6.67", "0xb8ae1b16c3507c9318ca569ccf60a25f2826dfa77b7b87e726313fd6ee8e4c7a"),
        (41, 1752569809, "0.11", "10", "0xc175630d34a2e4bb1a7fb11cba29af7cb1789b37a4ddf71c6f621c9f067ccdd4"),
        (42, 1752569813, "0.12", "6.67", "0x2d9e31c265a70211ffbfd9843a46a2b32ab9699478ba1b3f0691cc9194f704c0"),
        (43, 1752570167, "0.1389260323", "2159.4225", "0xe9a67cc912e63ab479c202a8f35363ddc9ba6399ea7ae572a46313375640c725"),
        (44, 1752570207, "0.13", "6.67", "0x54e20a92048d6636e968ad94913517dfd6fad6555d6bc89b1ad7740dd1389751"),
        (45, 1752570207, "0.13", "6.67", "0xdd8134b26c36f0899bb638cc082b3b5ab96636e4538e824d962ba3b103661b72"),
        (46, 1752570211, "0.13", "6.67", "0xd897a344b25527362e1a10d81ed89d02fb93264a64567aae576b4e4939b90a3f"),
        (47, 1752570643, "0.12", "6.38", "0x6e529e241de57129548b77ae24740f07e8f3d8e997d4d4a696351740a31ffe25"),
        (48, 1752570827, "0.1275564017", "1050.5", "0x12da23b738aa939a62f781d23ad5dcfc7ab12e9719faf811f4cfbf14fbd3de82"),
        (49, 1752570829, "0.13", "240", "0xecc8d1b324b66516a4f15306817067e54170b667dd25e1416c4588c583dab1b8"),
        (50, 1752570865, "0.13", "5.28", "0xc7738d356ecc8f16912dd6870a45de99f1f13d7d1c4a05d2995c07f42b09de09"),
        (51, 1752570867, "0.13", "39.72", "0x2c1df6f77efb3d106ee4635d7fdc044d98db2e5e85318b957718fda9befa486d"),
        (52, 1752570867, "0.13", "195", "0x64ef3ea4f391e4f5a55097186722a1d5033bc424dd9c9624395297f4511506de"),
        (53, 1752570989, "0.13", "240", "0x49ffb0beef7398f6299ca9ca856478ee112aec4f419d713896d603554673afac"),
        (54, 1752571297, "0.11", "45", "0x6cd7cde23537dbd568c0576f7ceca727e845fe02b19c747df873ba8566283d7c"),
        (55, 1752571303, "0.13", "6.67", "0x324802fd4811e1aaa0d7617103b6e921a09f87bc6bc194c25cb1faf0f6e72d41"),
        (56, 1752571303, "0.13", "6.67", "0xbb18d850bd4d2c5b0aa64e870ec701f1c7720f9bff3d4c46420cc2f8a963bc76"),
        (57, 1752578845, "0.14", "6.25", "0x4621b81483deb7569c5942bc58300f9576553301fb94c40d85e56bfec0d1b85e"),
        (58, 1752578907, "0.11", "1.41", "0x8bc91573ab6510100426b78cc3507337ff4f313a349569e099748fe5b1be574d"),
        (59, 1752579313, "0.11", "18", "0xa7361db6cce820ddc55ee33629bbef26b256d6140de3715e804a8a4ab9843f5f"),
        (60, 1752579317, "0.14", "6.25", "0x7dcd9ea5b8550219e064fc2b4e2cb7ea5d66460440c7573b9cbf0f3b169286ea"),
        (61, 1752579317, "0.14", "6.25", "0xdcb26ca015a98783a5b5491f00d130871a7fc35c0b3065077101e506179d73ce"),
        (62, 1752584911, "0.14", "51.25", "0x2aa09e0b75def2f1ed2c36249645636316477abcc87aefdf53d1322f13c5604d"),
        (63, 1752585081, "0.14", "30", "0xeb01f7da157f08b9f725228254d80091fd724d2f32017ad1c3e60a563ca2b882"),
        (64, 1752588081, "0.12", "3", "0xe9f60c9f091a5b562fddb235c796a7900ef69af95bdeb8cb5f95e8e41e0c2743"),
        (65, 1752591263, "0.12", "26.09", "0x073a350ea3b1159242ab67022234d3fa9697639ff3ef57bd786636614e092e87"),
        (66, 1752600767, "0.1099999872", "68.181817", "0xfa978da8104bad84ba9e525b6950f6c7aad9e1a08a0c3e298be4f2c17c1d9f13"),
        (67, 1752601661, "0.11", "117.8", "0x2ad88a7a9ced6e8f4bf7a885f3c9fb446774bd6929bc3287a4fe5ee3278fe03d"),
        (68, 1752601683, "0.11", "101", "0x3ad9a78f33d1d4fcb4e5a06d12a92434d65edc464eac1844bf3906d6fe4113c8"),
        (69, 1752602673, "0.11", "224.21", "0x7396e193e4b617a96e5cc4d498e6ada344d388001eaa8cef1e3a084f48c62988"),
        (70, 1752603351, "0.11", "5", "0x0fa34cfe3795058c533be9a7fe8604ee97734a1bb1893429ee9c8559e2e675e2"),
        (71, 1752603429, "0.11", "86.99", "0xdc628f2a1e1cf87fc18066e05a9a77c326bbf38f15e2fdad59abba886aeec0b3"),
        (72, 1752603517, "0.12", "30", "0x426fc04f0584bec19c103a66c7fa78e9326b8a4c27742f2aae6565b4052079ed"),
        (73, 1752603523, "0.12", "30", "0x123c3b376b6f9c4da65aa483646092b46e4d4ad653e1cd52fd3258681d2f8220"),
        (74, 1752603531, "0.12", "30", "0x80f8c265c8e5fd1165e3a963abbaec648b6687b680a38428bdea070391c78362"),
        (75, 1752603541, "0.12", "30", "0xe1467d38a3656d43bdf5d0457f8a06631eef053cc17629881d170b365a724d2b"),
        (76, 1752603796, "0.11", "3", "0x388386d2a5a1bbbd753630f0f28f469c2c655e1f085b40f40e55c45d8cd3894c"),
        (77, 1752605698, "0.12", "14.29", "0xb19db87676e17721c70282d98cc3efb46e3067aaeea0d6db40d6ded8955efce6"),
        (78, 1752605764, "0.11", "2.96", "0xd3748cf09bd2746e43c7c057ec21b364ed8527021c529e5e8d79888dc9706b56"),
        (79, 1752605924, "0.12", "14.29", "0x9b88961dece4ce0acd127cdba5367f3ef34353891bdaf07932d97b0a6103eb64"),
        (80, 1752606304, "0.12", "14.29", "0x73829edfcdc571d065c211a0fe7db4f2efad2edb7e727b2bc3d94b2aea4f5fb2"),
        (81, 1752606976, "0.12", "14.29", "0xdcd2858cd703097d8869deeeba434d17f982fab5fc0de35b0cd2df69456461cb"),
        (82, 1752607258, "0.11", "200", "0x4009b21a84174e0d2af84928b8a81473343a5d3cb61ed73758576ae96d42fd34"),
        (83, 1752607258, "0.12", "14.29", "0xc83f5054ca2a27d27e7359e035a2813c377ab45616c256303f76ae4e2c8a1b65"),
        (84, 1752607262, "0.12", "14.29", "0xcb516624bff9cdfb7d9ad3846cd76f5e69511eca74de21da18a929771a59e234"),
        (85, 1752607262, "0.12", "14.29", "0xd167aefe543b40e29600a16d031d1ed245fe9ee46ad7fb942def8dbcb2309005"),
        (86, 1752607264, "0.12", "14.29", "0xb6e28a30598b115e077bc359ccafc5f7ea225b884a0d141de63b0350d649f339"),
        (87, 1752607342, "0.12", "14.29", "0x02099e60e397298aa46d64f3ad80b5f0a9bfe957e082088b7c321c7436760d79"),
        (88, 1752607344, "0.12", "14.29", "0x016f661c0bbdd3ca5c5c0728fa3f9c401d3512d9224aa0d63cb1ec5e1f0f1f43"),
        (89, 1752607352, "0.1241474403", "805.493845", "0x3fd984d18d60c844efd376e875b94182094b0a2ef76a4d9ac74a5ec6daff85ed"),
        (90, 1752607430, "0.1460633533", "13452.998", "0xaea3e334b65aacb353455bc72d831ffab29763971ab5900cfd5abbe543261654"),
        (91, 1752607556, "0.12", "167.24", "0xc7b1d4ae377bd934340a2c5d5bf1236e221c0ab6f80b094d0a6a9452b4b2a3fb"),
        (92, 1752607570, "0.12", "14.29", "0x34630ebdcce2f8ba8eccc9bc783240b80f8123bd1edf2699f875157df4a467e3"),
        (93, 1752607572, "0.12", "14.29", "0x3d134ee00eda333705c35a030f1a12e95d3cbbd74b550c949c4ea7ca229f149b"),
        (94, 1752607578, "0.12", "32", "0x63b6ac876cc21f176390038ed3dbb0e81010d87ca27daa918de57009eae0f093"),
        (95, 1752607578, "0.11", "8", "0xd0a231650027760da5fd7c4c86ccc27051beb904d04253bf3749b28c57a74bc8"),
        (96, 1752607582, "0.12", "14.29", "0x6a5d368be07b19bf5913c6fb97c0825c0ebebd9e864687fd1a40d4c92aa028df"),
        (97, 1752607582, "0.11", "5", "0x9fea7b2ac98daf8a5b94da6a32bfe0ec8649d9c9529623e854721b0da887566e"),
        (98, 1752607588, "0.11", "24", "0xbf84f67481cbaecb65453b5cc654855a1ff2353408da043e9f9650524e1c935b"),
        (99, 1752607590, "0.12", "14.29", "0xdde43eba204f930556bb3e4dbd4e9f065611ec688969b3413a92a919810e494c"),
        (100, 1752607592, "0.12", "32", "0xb1279cd410801b0c0da415bc03bf107d5314363cf1acfa966333f0f2699797ba"),
        (101, 1752607600, "0.12", "31.07", "0x8f3937cbe0cf6e47c73d973b7d80daafcd4718dd95102efbad12db5b989f9c78"),
        (102, 1752607638, "0.12", "14.29", "0x2c7b5e1fa3b16c34fd9f2057cd47f8070a710a594aa17339e89e225d601fa634"),
        (103, 1752607802, "0.13", "13.33", "0x57ef6341e56e08c24cc865b633e9c12f29cd0bf00defef1ef50b3ce522c31fbe"),
        (104, 1752607804, "0.13", "13.33", "0x2b29a6c84874639c3945d2387aa101e8d85205fb9da849ff2c23e77d2a6a1bdd"),
        (105, 1752607808, "0.13", "13.33", "0x3267fd290455342925d566a25596f1b09247934c979a5d85c56273964efaaf3c"),
        (106, 1752607990, "0.11", "165.03", "0x10d483d522594cc533580689585565fa36d06ba555b527b685dff589df249ae2"),
        (107, 1752607994, "0.11", "15.38", "0xe8fbcb0d2e30485c7cac941427a5b23ab5f34cc31a478f1b8fd1369a589765cd"),
        (108, 1752608596, "0.11", "209.97", "0xeb15483162db7464dfe726524275b2e13ee2b7d86b66c31cbbc2d6213ed4a59a"),
        (109, 1752609236, "0.11", "10", "0xa9b9ef6f39b90852c26da550f0dd951fe4c0440f557ff833caa900a9e62a084f"),
        (110, 1752609704, "0.11", "5", "0x93e326c9704ae3d00d14518f7ab7a8c26bb96a4eb39c64006ae38bf33cb7ac33"),
        (111, 1752609966, "0.119999988", "66.666665", "0x0f6e09502e5aa033f15ace7c55238f898a71fe6d664efbe5e949936608be8cc9"),
        (112, 1752610080, "0.119999999", "833.333332", "0x5daf48d66f3050ba2d40e94e66152a7b1c122c72c39487e8d8e55a7b0ffe279c"),
        (113, 1752610776, "0.1326537218", "3769.212", "0x06b95640d99601dd20cbf37c6e78eecfdf99f8f3f51732e07987906cb0024a0d"),
        (114, 1752610792, "0.1465616631", "3411.533332", "0x0f96d47b36b71f044a8d331bfd2cf298a9c64b4a12129f2e7ce006179f88165b"),
        (115, 1752610956, "0.15", "20", "0x85347bd33743f3b3ac7f4ffb334194c38b1235ccda5b93bdbde963d16fb8207a"),
        (116, 1752610958, "0.15", "9", "0x4a5693de2ae56cf4105e6347ba1becd4c460bfe15fe271a88571a383c94b34d6"),
        (117, 1752612409, "0.12", "5", "0x5d8afc142229ee6e7d022ea1fd233fddec7786f3d76389e4f2598875fe562909"),
        (118, 1752613439, "0.1199999931", "116.666665", "0xe6b105b51243d5599929cd10a2bff89c4eb146c1903f3e2e054baf12f6220009"),
        (119, 1752614033, "0.13", "30", "0x0e4a685f84b1f46679245d40bbde0702232b0fedc4068026911478f0e1e5c9f5"),
        (120, 1752616561, "0.2142857005", "46.666665", "0x036f2419e38eaa1f83c8ee8c194e10a305428a060443668a94ef7aa711cfd6ee"),
        (121, 1752620649, "0.02", "11600", "0x9998b8ec8b59378de1317bbbbfc82535b4b05a322081c5835a54ed0b0c4d74b8"),
        (122, 1752620667, "0.03", "30120", "0x9fb461b46470cbfbcb09cf93a1dada539a4a05cbb33ed6e0f625f79954657ee1"),
        (123, 1752620815, "0.06", "30", "0x159d76c10549325dcb76690471541332ac5a62378cad76bd7cdb26edc711e233"),
        (124, 1752621361, "0.0086", "100", "0xb66149492f2b917fe0195030a5e60bba5d9634ac71dbed2b87b47e2a4fd97e31"),
        (125, 1752621445, "0.0299999712", "33.333332", "0x2e17e7ac47a5498e04b7de755899cead686b18953560ce11c79aa43081a8c00e"),
        (126, 1752621447, "0.0299999712", "33.333332", "0xa78c9d9f5ac91aa5a788c0c9cef3cac7c246fe265366a8ce4569e932d2b8ec0a"),
        (127, 1752621877, "0.001", "200", "0x97b26edd69076490393a29cb67aa1e1161877197ec88000aadc3853da0f13111"),
        (128, 1752621939, "0.0267421595", "7478.827585", "0x4f61cd485d27ad1a63cb7e87aba0c124ff7e6a529d74a37f7c039f47a1370680"),
        (129, 1752621967, "0.0184713379", "54.13793", "0x88574a2d6c2930d1b7cc550a53f39a9edf0913eca7fcfc389efbb5523886d80e"),
        (130, 1752622061, "0.0228346236", "43.793102", "0xcb1d4be3adce1a37b4ead74f43caa74355f2c96a189ee9e3b445623cf6128b68"),
        (131, 1752622081, "0.0288853253", "3461.965516", "0xd4997d59176a400acb8723a408f6829c0a72ea1aa40115282303058efbe4800b"),
        (132, 1752622107, "0.029", "3448.275861", "0x6b158aa2cc6dabbd939d184c4874a162216aa1690a6718e1a1fbb989a0b1fc33"),
        (133, 1752622141, "0.001", "171", "0xa4597e004c72a2a6153aef9760699f4e729520737fdf0b0bafe15734dae8d7ea"),
        (134, 1752622477, "0.0096786682", "516.6", "0x11bc0899edd63167d37414f306966905cb04f0ab636fbbd51c7b7cbe0e0f2674"),
        (135, 1752622509, "0.01", "500", "0x2573713583c478461cab175b6bb75e29fd802fcf34abc152a63386c86969c081"),
        (136, 1752622701, "0.001", "2805", "0x5d55e1e07222db2a69db576a703e2340a5bc1f38a43f384f93edb79498129ba6"),
        (137, 1752622701, "0.001", "200", "0x7e3c6f2312f9506b9465b833792e9215e64db68414ba35329094ddcefdcbc019"),
        (138, 1752622705, "0.001", "3000", "0x6fd08035e55f3d504604a02787452a61a5c5f904a76f3be33fa2dc7af34de054"),
        (139, 1752622771, "0.001", "200", "0xd4e6927fe335fa186e1e1422e1bb95724732458e575bea0160ce9820ea30b4bb"),
        (140, 1752623067, "0.001", "4000", "0x1bb7740e672fb52cbb062a7578951ebe6049acae32d9bf75104cf531aa41c644"),
        (141, 1752623135, "0.001", "20057.74", "0x762a2874c84078ab7eebc420b1f6f45841d87c146c1c4132f7321842fe8571d4"),
        (142, 1752623227, "0.001", "3000", "0x23d404c07f7c16afee42dacf930a3ef2dc738777b9e289ac11849cf2da31c183"),
        (143, 1752623363, "0.001", "4000", "0x08d9d0642e7733950ecdaefc4e3b04b711118661a892f397022779f4cbae40ec"),
        (144, 1752624211, "0.001", "16", "0x4c16db69787f807c91a64386e5624861c4cb89680dfa67ba7bbe5b2442a9f699"),
        (145, 1752624355, "0.001", "16", "0x38be508d80386c9744edc6b58990a948b83c510a3ca8f9fab5eec40ee9037cb0"),
    ]

    fileprivate static let retained563326No: [RetainedTrade] = [
        (0, 1752510350, "0.91", "623", "0x6251e3f1cfba01a7c9d07d0502e84f4266d977506abf3fadbe4e8755850e1b10"),
        (1, 1752526786, "0.91", "1005", "0x41e15e9e3479e2ba7a494f9ea8700f8ed1141c2261635ffcbb1a61d35c342fac"),
        (2, 1752531497, "0.91", "105", "0x2d9fc3a87841caf86d275a35e1ff41615cf6b16d66816be9f75c1f9167cf562d"),
        (3, 1752531597, "0.91", "1.08", "0xd59cdb9d19b30e1a9fa6e0879a64359d8a03ef5f7d5f354c776ccc4583258397"),
        (4, 1752543219, "0.89", "10", "0xc1dd3946a9108cb9d08a3c9fbbf2afd4b297077ed3c7b49a32e04c8ac294989c"),
        (5, 1752543221, "0.89", "3.37", "0x6c85df6730cb1e82c5391f5d3661912b6f0c821172963abe9691f39e80101d22"),
        (6, 1752543221, "0.9", "1.09", "0xc6ad901c7eb54357aed5a663e0632a8f921c5c1d96b689c22ff0fd9a9c0ea478"),
        (7, 1752545815, "0.9", "10", "0x342c7103a609f6a585c0ec6b64ea9defb262c5427dd16d810fe665c935ec8f57"),
        (8, 1752545817, "0.9", "11.63", "0x6fc9b6dd5a161f4b55d13a9b88bbf04eaca38dde9305d543377492a055d12c9b"),
        (9, 1752545819, "0.9", "1.09", "0x6f58c71c29baec98e289fb41f07248f83c47d29a95882c855e49135aebe20acb"),
        (10, 1752545825, "0.9", "11.63", "0x3e7b93d853371b5eed7843b8366bb535cfcf147cbd508114b323dce6f0ec215e"),
        (11, 1752545827, "0.9", "1.09", "0xd88d31f82d78d3c99e2fdf8c75bf0eaafe67b72de9044de24d2d46a31effc77e"),
        (12, 1752545829, "0.9", "16.67", "0xbdc154d04c9935bbad078def8377a2e73dc4457359dfda1c47b42b9ef034ef59"),
        (13, 1752548830, "0.9", "330", "0x51400f6883894a82576a9d461eea9bf708ae1c2a4e14b92e0101769b10731b50"),
        (14, 1752548830, "0.9", "370", "0x5ebc8f9a1784613432778eb2e1fac90cc137b505923e7ecf1d40b38e7c1765f7"),
        (15, 1752548832, "0.9", "1.09", "0x7caba9988523c8a168faba3734ee0e7c6d45e6fac3380dca07a4673107fb4d04"),
        (16, 1752548832, "0.9", "20", "0xd553e5e7e37109cf0fda5e00e34c654bc209f3f7618a7a1571b1524b5a7af70d"),
        (17, 1752548834, "0.9", "20", "0x276d14c415460f74a3402424f19197676b2ee72744cb86ef0b63bde3f7a817c7"),
        (18, 1752549546, "0.89", "5", "0xe0f7c27f3ff9a66cd27806d1c0a5c68b4eb28546b17c48a1615d134754fa8e1e"),
        (19, 1752552355, "0.9", "1.09", "0xb2272500a4cce81199b82b4120a3a5ce9d3cbca9d7d04f06a277a525ba1fe0dd"),
        (20, 1752552377, "0.89", "21.99", "0xf46c66dc6a417f64716eab00f6600ea9761d06521b5e24e9933cf449f04f6d9c"),
        (21, 1752552399, "0.89", "25", "0x88c416316b52430e053d7d13f2bc93f7eed41869c28071274cc7279e56c46f18"),
        (22, 1752552431, "0.89", "9", "0x5a3c8358ad7504cf079231a41cb5aa67b5ca53e723ab64e9c53ca95c79e6267f"),
        (23, 1752552435, "0.9", "8", "0x9563c66a0c297d06684cc9f7c99f64d2220ee33e15d711529bee8c739b2911c0"),
        (24, 1752555153, "0.9", "1.09", "0x215e7ae57a10e7a0ba50f0c072a13eac06aaa8fa1120a94f38c2eebbfbe6a1c4"),
        (25, 1752566345, "0.89", "9.21", "0xbd5a2a1579bb8c32d4ade92f83954dd93beba67fcf92428e7e7b8cda6c838425"),
        (26, 1752566381, "0.9", "66", "0x6c43a5a063f8a4a48024fdc36922327d6cb68c017e219aed6d4a0a392882502d"),
        (27, 1752566381, "0.89", "30", "0xc12fa4b45322315e8e20b311c6e2368e63a760d5e9b8d12bde28322cecc0ef7e"),
        (28, 1752566381, "0.89", "39.99", "0xd5b4999349451167ee55c58f2e4ebef490bbb5927eb2acda9b71aff57bdb6118"),
        (29, 1752566385, "0.9", "1.09", "0x0da9385f6a06a616adb14e35fa5f7a467efbd4d2738ca3aac12c2a353a9aca51"),
        (30, 1752566385, "0.9", "156.25", "0x7c0c0436036086a1c835ee0aa8e8e2e922f732433535b405847a8178f1ce1c1b"),
        (31, 1752566385, "0.9", "66", "0xc947b315ebcb3b50739748ade9a80dbe1532f6eb7f0187ddbff6b57a99c9d290"),
        (32, 1752566387, "0.9", "53.75", "0x086d794e21a2c2e11a598c90fc6b78f116d1ed3756b0a2ca39900033077d2299"),
        (33, 1752566389, "0.9", "1.09", "0x500d812eb065b4d59fcd399643c4f733f8f5d16fd8283cb688bd6001e1d75526"),
        (34, 1752566391, "0.9", "1.09", "0x2cd23558e69c677844a6fb28119e28c23a9a15f30df8aa125e1dbfd1920086e0"),
        (35, 1752566654, "0.89", "40", "0x2b7bf44d03d3238e932d02b43d50b3edd3d2077ccfbbd809d29207f9111ceb0a"),
        (36, 1752566654, "0.89", "40", "0x8418ee0ebdaa5cdd1c6158778e9452f5a58d3bf53f77c5c279a057cbace0f091"),
        (37, 1752566658, "0.89", "6.25", "0x2fcff286b3dcc6b733cc001570cd1ac9cac9fd1d7b91db30ceb7aaa80bae7f6f"),
        (38, 1752566658, "0.89", "6.25", "0x6c8d5bb04d76b4252c1b2b06fe35621afd46a9a14cbd3317f9f13cbe1e55f71f"),
        (39, 1752566658, "0.89", "1.1", "0x7e3a028c8985fbeb652f907bf0479655fdba9d96442803b7459a12b0bdf0622e"),
        (40, 1752566704, "0.89", "24.99", "0xd9740acba258aedf4448145ea5ccd9c9ca3eac44693a392c3afac399891f1c67"),
        (41, 1752566730, "0.89", "18.05", "0xf1004f494db01e49166d33a2e8bd5062f6c54f1769ebb02c9ee3ac741f1ba6f2"),
        (42, 1752566734, "0.89", "6.25", "0xc2c55ce7c47ab63ade7e811ad95755193498c326bb2ca0662e7585923e90e3ea"),
        (43, 1752566736, "0.89", "25", "0xeecba331d83bfef0ae135257018b335e420cda337cb306ee1cad7c6de4dda416"),
        (44, 1752566814, "0.89", "39.99", "0xf24221e239e2c1156018fdaa8c72a1a747733d80508b3a338249336b6fc597b7"),
        (45, 1752566816, "0.89", "102.22", "0xffac2d06c3a52ba664784b71972ab053df76b83adb31f782715f92233d213868"),
        (46, 1752566818, "0.89", "12.92", "0xd69245bcd9d61e83051f1b5dde4c2e1d7d8c3545be512253c5be19e369fc23c6"),
        (47, 1752566820, "0.89", "13.33", "0x2538e7c1adf38cab0eb9c694b3e4306a21ff4291b727c85222cf76f7409e298d"),
        (48, 1752566820, "0.89", "5.01", "0x36cde41298945c4ba37f0e15e415076a99e893a7152253b85802fc8c4045e0a3"),
        (49, 1752566822, "0.89", "1.1", "0x286e234b159dc558b4a84eec5c873eebd7cf7d0f9aa8394f2eab9ecfbc04467b"),
        (50, 1752566822, "0.89", "1.1", "0x3dbafd9d0631478f4929ac01f8377a30fcc896e3fd5eb04618aa4a331340f0ef"),
        (51, 1752566822, "0.89", "5.56", "0x78e05e53940b5831dc005f3043f44d24caf1f0ac0dcb3353e242c20f023493cf"),
        (52, 1752566824, "0.89", "5.56", "0xa0c7bdeaeb8e611f6d2640eafda699d499bd7e3f4ebcafeac67ecab35daaf91f"),
        (53, 1752566838, "0.89", "27", "0xca44e873ec65e2c7ad50f4d37537104a6a53a7e7007a7fb31ea96517c6115838"),
        (54, 1752566848, "0.89", "5.56", "0x8c1ec39f93806841b88b58f18dc432c118662407356e37486c96a0040f3b698b"),
        (55, 1752566848, "0.89", "27", "0x8fb86470c8e6ddab2c8199598ee0ceb39855d127c04128a7cee16cff2ca214c0"),
        (56, 1752566860, "0.89", "27", "0x8c6f557efeb258d262f1c14c4785f7db8bfd8f3acf995bef90b82cfd010a6757"),
        (57, 1752566864, "0.89", "1.1", "0xfc23ee296040ab9e0d1a3596fb47237d35108effa5c8732997a7f09d53b88ac9"),
        (58, 1752567078, "0.89", "31.25", "0x33cda7693492ef21472dd2cce66a0b1b9750e6f2a3450821e0fc2399a458caaf"),
        (59, 1752567082, "0.89", "1.1", "0x2aef54988103aa1530bcffaed1ef605f7948c46393e0b38337856185105a0cc3"),
        (60, 1752567933, "0.89", "70", "0xa0ac769359bf83c039662af13b424c01b33ab353dcbfab85e13e1660a3596588"),
        (61, 1752567937, "0.89", "1.1", "0x0ce69ba42498455b9f8f00af815d5a124842ba26124e575202aa1795d004f41b"),
        (62, 1752568194, "0.88", "23.8", "0x97ac0835d720105bab517c7b22ebe544aa0de8657521fc5f4a9addf63ab3d919"),
        (63, 1752568198, "0.88", "13.34", "0xc3ca12a5f4591d649481698e5741457264239cdc09721d418a33c68be7e00851"),
        (64, 1752568200, "0.88", "11.12", "0x0cc312e2f3be529399ca0ed96a20da1268124c3cb83b97455de5437d612e9025"),
        (65, 1752568510, "0.88", "510", "0x997f20565ece068dddbb93f70d11fff88b08b35e061fda7e6c697c91e4f6ba3a"),
        (66, 1752568580, "0.89", "1.1", "0x6f410fe5e010def77d2ca25a9c824228464a943d46452e1d0e2fd2ec384c41b7"),
        (67, 1752569693, "0.88", "0.01", "0x0329e4b8eb76711c4f7171bb5ef33ef02e5132a73a813f17b8646dd7c3a6b07a"),
        (68, 1752569693, "0.88", "6.66", "0xc5381c251c628f64ee5f4a4d8bdbf2442ba0e7d2d439371f84089c8a96ee135c"),
        (69, 1752569775, "0.89", "66", "0x0a4d72af56533d81b5966783a75485dfae4932eaf8cc7a43bd15f0acc91ea03b"),
        (70, 1752569779, "0.89", "14.29", "0xf0f715430e1132a595985655d1c2d4b5c0f249f928dab6eec076073a58029c01"),
        (71, 1752569791, "0.89", "190", "0xd97a0d646fbf36f3bcd259dd37fbcc093dd6e9f7163cb4f8baaa62baeea24331"),
        (72, 1752569799, "0.89", "1.1", "0x9a8130665174203a697d8d9bcf79d8667762ea5ba6bae2809c02fd90a44920bb"),
        (73, 1752569813, "0.89", "5.56", "0x9d0d231182ac7a67a00116e6f06415ed36a8331595856b6a3198c46e08449546"),
        (74, 1752569817, "0.89", "1.1", "0x62dacf142666f0141b06082513f92ea1d9afe4f0b9572c1d8c1948830cb9cb37"),
        (75, 1752569817, "0.89", "5.56", "0x881bf9c87e60190011acbf51f448fa3a690eaef744b15e0ecabd91e04714b91a"),
        (76, 1752570171, "0.88", "5.56", "0x458685fab93b78eee938174741dbe88970ae125a1bc31400602334d6110a8110"),
        (77, 1752570171, "0.88", "5.56", "0x9e19029ca7babe20d2e332395f4813b01399aeb2d30dd106b2ab77f0ac80e615"),
        (78, 1752570173, "0.88", "16.67", "0x6327f8bf5c4de56407ecf1d50a6f481de3c717563cf0439561ef8a46c3c85bdc"),
        (79, 1752570173, "0.88", "16.67", "0x675decdfe38dc2dac9b4f02394ac4a6026b518f2e8c320c35a6f3a2e5f882876"),
        (80, 1752570173, "0.88", "5.56", "0xcd8eaefce4673b66445c4ff317d934a8f7593517b013d56ef295933ef856ca39"),
        (81, 1752570175, "0.88", "6.67", "0x5bb99c8a48cf60f87ac836aa474df550bef2c4ca03ea96add996de4350af0ae7"),
        (82, 1752570175, "0.88", "5.55", "0xe9ef5b8dcff9291119251accaffd0e24c4c7bdd74db41bcfb4bb9c91d770825a"),
        (83, 1752570177, "0.88", "6.67", "0x2650036799a8adeb117f711bdddcc3a0c18f40216d8f3a8c00bdca0692bc4d99"),
        (84, 1752570177, "0.88", "16.66", "0x773dddc6ed1d02dfb8ce73cc0317caabc6254bcb7ee70221777c4177eb3fa0f9"),
        (85, 1752570177, "0.88", "6.67", "0x94c368ab8f54b838093d9f4f7abbde9315c3ce6201465e05b104b3237d6dc102"),
        (86, 1752570179, "0.88", "5.57", "0x07b35f6cf7a57b974da08bcb27480852af4aba560cb2092fc865a72255cff5f1"),
        (87, 1752570179, "0.88", "6.67", "0x9335decd554f12c9c970f19816c203646c60a18e9318ef7b00afd50263110781"),
        (88, 1752570181, "0.88", "6.67", "0x6baab4f4867ae9ee5f978c3c2f74c01d27713168a5e308b9d3f9052aa6bbb91f"),
        (89, 1752570181, "0.88", "5.55", "0x99897b21aad706cb0b4c829a11dfa515207d2da60e1deba02c4c83f878c0cb76"),
        (90, 1752570181, "0.88", "6.67", "0xddebd60b48befaf39eb683f4957ff3a7bb89a9fc1d63e4942b65b135ff176c0d"),
        (91, 1752570183, "0.88", "5.57", "0xa27c2917620b11db4f8ab95f4bedf25ce45245b5336df185eaef020615b10ff8"),
        (92, 1752570183, "0.88", "6.66", "0xf0ba75e9a123ac191a817be83ad231a0707d2f50be6fc6895eaa809db94e6ef6"),
        (93, 1752570203, "0.8877132241", "150.3864", "0xc8649bfaf9c4280a6881bf6626185281f61f6a4266e21b331e1f0c66267e1cfa"),
        (94, 1752570203, "0.88", "15", "0xdcea54fd5ff8050300d0b9218c624c42b7dfb892f124ceae03b7f2ab6a240102"),
        (95, 1752570203, "0.89", "300", "0xf14190be1dcff1e24249c905d6b05815b90d1f56626194881cd8444b8e2560dc"),
        (96, 1752570205, "0.89", "15", "0x9460eaaeebf3cd539228537707438a71eca8e6d9906a140235151425ef71d97b"),
        (97, 1752570211, "0.89", "1.1", "0x3b80bd57475042ad1f504ea439e38de239047e2b7b58b84667aef3719fe71bb3"),
        (98, 1752570211, "0.89", "1.1", "0xf4efc95bc2d661427b04579970d96d0b6a70e9cb74b7cd4ebbcd7b7bf0e1a971"),
        (99, 1752570215, "0.89", "1.1", "0x13754783013435b5d98d26716c2225d5e8f68e15a3659f890f2a9ad7be54c8bd"),
        (100, 1752570327, "0.88", "66", "0x55c81e118007ee85ef38a12b728566f9bbdff12b0308e57fd012f4e340e06d13"),
        (101, 1752570327, "0.88", "10", "0xc5f9a2e3b0a3afe71dc642eccdc53cb74b104b29166995f85d1c899ad51a9835"),
        (102, 1752570571, "0.88", "133.28", "0x8b520368b367018d970e890c693a0bd7b8c4480c93c363a3fbca628f2611afe2"),
        (103, 1752570571, "0.88", "66", "0xcd3fbe9e147f4db6bcd19d64c4e3bd473eb27465e35be969ac122a2d0c2d7773"),
        (104, 1752570575, "0.88", "13.34", "0x37c8873b4f060051512664a4bea87a6b0546d149f7403087bebbea33bc85e272"),
        (105, 1752570643, "0.88", "1000", "0x00047c27c8ef5f04ccf597c9f6068540d0e0ba1653b72f2a30e60557ca13ecf3"),
        (106, 1752570645, "0.89", "1.1", "0x34e6c20296a81b95ec41193865803b891e89c1b989a660ee039c967c10a87e6a"),
        (107, 1752570647, "0.89", "14.29", "0x3b3c98ad3762b4dc795405a73a7685db06247b63f432484b4bef4f4944447d08"),
        (108, 1752570647, "0.89", "14.29", "0x5cea3a621b4ef8e809dcb9b908b513f9fd78809d123d2526a2b87a3e4f6971b5"),
        (109, 1752570649, "0.89", "14.29", "0x564e1368fef9c9e82b03a5f2fb29ad9033156bf7214c288c71e3013006993f52"),
        (110, 1752570653, "0.89", "20", "0x58a8de94e7b18ece49d6b323f62a48663a5f64f6450ce88f12e075691d73cdf4"),
        (111, 1752570827, "0.87", "329.94", "0x25bc311d9919530047566b425de733388eac8cb607080cec535d8c017ca76eb9"),
        (112, 1752570827, "0.87", "39.99", "0x3a17b77b8b827f2a06b4065eefecb62dab070a68937f4d066a390d59698cf514"),
        (113, 1752570827, "0.87", "452.13", "0x9d402c2e572302f990eafe9dc20a66ce81866bc70086d3d9b6ddcdfd87d7c85f"),
        (114, 1752570829, "0.87", "5.57", "0x387196d93707cc7963e6bb237684d013c44aa3b920f728633ee85d415c181f90"),
        (115, 1752570835, "0.87", "37.03", "0xb6f6e12d0275d8fc8097efa408b9babc69c3507ebac1778525dcf647367a57f4"),
        (116, 1752570843, "0.86", "5.55", "0xd4ba44582d8b3291f277a9486ba463f52b48f7edf03941d48fdac29b2febc7f5"),
        (117, 1752570843, "0.86", "4.15", "0xdaedae88fb8e00ad246202e72baa63ce89781900ac5d38622d3f55e09421e6cb"),
        (118, 1752570851, "0.86", "1.1", "0x63875a530cd9327c93bb9929aa3378bf93c5c2c7e46a5a9b1d196d7945e735dc"),
        (119, 1752570853, "0.86", "6.69", "0x01698112c695ab009904a76e90f208429aeecf6c7676074f35acf6445312d742"),
        (120, 1752570859, "0.86", "95.51", "0x60501f5cf376571a50ec83a3eaec7473967835c4d1c541a116e9b7126675e3cd"),
        (121, 1752570865, "0.87", "16.67", "0x4d549317f85254f773861f6dfa4af5df7027d481b3b9af4e48ed3c3da898ac7a"),
        (122, 1752570867, "0.87", "244.7", "0x4fee65d5a52e9ae2f7b3a4f1e347186d913e335ad39fc48f1bb6826b58439d26"),
        (123, 1752570869, "0.87", "5.56", "0x05965d4c2b9b42e6b23e7641de22e2519ae3db80169045ec809d3a0454e04627"),
        (124, 1752570871, "0.87", "5.56", "0x1e47b7d6ce7807e906c4f243fe708c53138ef70aaacc1a6619777303149e60ef"),
        (125, 1752570871, "0.87", "5.56", "0xa7d18579d74659f5a8e015851b9914a8fcf6ee82ef1c8494b7a9eb6e55e7dd14"),
        (126, 1752570885, "0.87", "27.46", "0x57f99b64cf4cd09c58452f528b3c26956958c37472d9790b4516a67a3f6130ff"),
        (127, 1752570885, "0.87", "16.67", "0x5d4db4bfa9b277ec409a1f6b8a1053bd03a54afb58620e0f8a9c28c152f66b68"),
        (128, 1752570885, "0.87", "16.67", "0x73e8343f3498397ef0e46d46df07858450d85bbd8f4fef174827ffe5b4efa154"),
        (129, 1752570885, "0.87", "5.56", "0x9c2c6e35315914a4eb5b86b5d80ad40a170207060797b7d6a9bae9ea4f3b6153"),
        (130, 1752570885, "0.87", "5.56", "0xe3a95d0b7870d3a888657cbc6bff0fffb83244bcd39baec054500bc61d071cdd"),
        (131, 1752570889, "0.87", "28.44", "0x4c35145ff19c6338e30435523378cf663065415912b6515b943177f38f079214"),
        (132, 1752570891, "0.87", "5.56", "0x17576fe02c509e3c7b5b1e4ec9c167670546eb909e7086c2050b4aed5ac54921"),
        (133, 1752570891, "0.87", "39.99", "0x31161a6579d037dad6b42512f4de0deb5895b8f291824056d44cf4a1431e1d39"),
        (134, 1752570891, "0.87", "3.19", "0x889c99743fb975cbd51485516b1698ef7172c5ca6d8d654aa732d2bf631a5ff3"),
        (135, 1752570893, "0.87", "5.56", "0x01b4093c01faf966f952196892c9fbdcd777f826eefe8651d9fd3bb85e49e8b0"),
        (136, 1752570893, "0.87", "5.56", "0x8f5c5e11a4d5dafafedb6d2eebb3e395a3cb056a940b136771d81b1d1901d1ce"),
        (137, 1752570895, "0.87", "5.56", "0x08af9e7798e205599b804f5c39d787a37aae7712dfc48e7e25545b72e2cc41ce"),
        (138, 1752570895, "0.87", "15.98", "0x90b3c75d74e90d28dd6484ba4b0fe7ac3c1426d343dd84b3733faf2db8fb706e"),
        (139, 1752570895, "0.87", "5.56", "0xf07a5a17009cb85333727f7d34081d5ddd8429dce7b317db29fa02f94bb43f24"),
        (140, 1752570899, "0.87", "62.48", "0x611218c7f00bf6d78ad62ab3782be90caeaedff0f3cb24054eb9148ad210aabf"),
        (141, 1752570907, "0.87", "242.29", "0x4e019a6adf4e21c259619cc60d1b9506e6f26f4ea81e5adb6f299d30bbd3bad1"),
        (142, 1752570915, "0.87", "60.34", "0x4ae8d60d6dcd520c122fae41e2f8990bbcbe74040ef2dedc64b19a88ad28356d"),
        (143, 1752570923, "0.87", "6.77", "0x4b11a4aeeff208f040adfb0df096acd3e10ee9348ab5504372652dacb9d5dfb7"),
        (144, 1752570933, "0.87", "271.67", "0x9a55853c354e1e351c111f44b2bfa09d0e3c260fd7ff50bdcdaa97b1bf1bae34"),
        (145, 1752570939, "0.87", "84.12", "0x75068ca28493d84c8c4eb704b05092b39c6ccb4a64fc395fb67a225ce4ceec75"),
        (146, 1752570949, "0.87", "15.46", "0x53b0101567909ed0ce57afb7854267a6145e0dd7b05af80cc2a7748f1d03b80a"),
        (147, 1752570953, "0.87", "39.99", "0x5bc3fa49e42bc24f588ba548dd97f2766cb1252e279c0664a1ed1d8f08f19105"),
        (148, 1752570953, "0.86", "9", "0xb66327aef46d7feadaf310602d400000c1a066cde9f42231c5fc113900684579"),
        (149, 1752570955, "0.86", "1.74", "0xf010d05ed0dbfdcd55293b9778dae14c0e9c6df27fb1375b665e9435a495bd28"),
        (150, 1752570963, "0.86", "242.52", "0xdfa04cfd62d9e23e96155615e3f8616bd92d6d8a79c17c6518379e572bfc8b4a"),
        (151, 1752570971, "0.86", "5", "0x4b11bb8a0ad75f42e38c20b594112791146a0049982817d676d0dd406b686fa0"),
        (152, 1752570975, "0.86", "9", "0x9029dab039f02fe1384253f8ac44479dadfa063357306ffbfa7ecc70a3e540ff"),
        (153, 1752570975, "0.86", "6.66", "0xf79b464b4f71cc6236cf8cd71689ea627189ed93204a623fc8768cb62b347eb3"),
        (154, 1752570979, "0.86", "110.73", "0xe4329969ab2a2bb48ec83994375358d1a64ef5598387b2fb8f711885d7506101"),
        (155, 1752570985, "0.86", "10.02", "0x7eeed75b3c26d007003642517873d9c03e5f9484610ad98ead83bcae0d96a2b9"),
        (156, 1752570989, "0.87", "112.27", "0x7ba26cca30954647792278a4f8c5005bcefdd0ff53c4b8b8c3e3b08e7d2e88ee"),
        (157, 1752570997, "0.88", "190", "0x07607a593682665caaa7346110d5d31186056c5c9e1fe109878cfd9a3faa0dcc"),
        (158, 1752570997, "0.87", "14.41", "0x7759275a9602e73d6e11958a217f2b6dc8bc3fe93e0dc8a9b133acc6b94e6005"),
        (159, 1752570997, "0.88", "661", "0xc9e8570be9327ce6fbe3a481211faa623185f385e70d1cda1e120468d45fd51a"),
        (160, 1752571009, "0.88", "5", "0x0ab7474b73653feaf2c13a78fbc274b8a54049220d1eef8114b3c1d2f30e9d27"),
        (161, 1752571009, "0.88", "9", "0x8fba1dfadaa9e92f260db372046186cdd867138183e820d86b7950019185a970"),
        (162, 1752571011, "0.88", "9", "0xf23dbc70b971162994515826b73f2aa5d34f1d60b36fcfba161888d8d96410cb"),
        (163, 1752571013, "0.88", "9", "0x0e78dcd633489863271879744eea2e00b4faefc8e224c74a45710ec114727306"),
        (164, 1752571017, "0.88", "15.55", "0x65501b80915bc1d7bf8d0c6c7773ac9cd712fb8af6f05177a03ba635482c3c1d"),
        (165, 1752571159, "0.88", "1", "0x21d09401d84da05e460f7b9247309d271ad20beb08edeb73f7f34cc58d555a19"),
        (166, 1752571159, "0.88", "250", "0x44d7127fed3ca20f95009ebe7ea53d1615118f697c4ea1327b3cdc500f1a5476"),
        (167, 1752571159, "0.88", "66", "0xc0e00f491f440c251d1f4b74a58e3289d0b352cd38a20428278697dc2f28b69a"),
        (168, 1752571163, "0.89", "1.1", "0xc0c6feca867882bfb94b0019899b90fbe8c7949383e1ae2ee01558e84752b85b"),
        (169, 1752571297, "0.89", "40", "0x5c8946f5ed8c3df4aa018932c13c904a5aa0fa74955bc43038e15e2bbf14ff78"),
        (170, 1752571305, "0.89", "5.56", "0x7b5a05dc3ef6c4c8f86e471fc5af87de81667851c2506c9ffc41f960fddfe72d"),
        (171, 1752571305, "0.89", "5.56", "0xc92d643bf1721da978a9e0e44bba560b1660a064eac5962d730fed463f91a572"),
        (172, 1752571305, "0.89", "1.1", "0xd22940c05ee22ce3cab4f40cccc3b6a6d75481332169130e3e9d8491ecc4eb5d"),
        (173, 1752571437, "0.88", "13.34", "0x259ad017e8c952d8a119e0dd99599623dc1c7f6838b1b5bdf3cfca921206d7b9"),
        (174, 1752571441, "0.89", "1.1", "0x0dfd38d8740bea8254c24de8bade73b0bc5bd2112ef6b6eb1bbde28b182f69ff"),
        (175, 1752571443, "0.89", "5.56", "0x8c516c2b86218ca9a627cd3f8a97a6b9612ef58dfcbd8ca4f8b2624db0bc9aaf"),
        (176, 1752578841, "0.89", "50", "0x63e223a8dbe90c5a7b4a01de8e65facc5f210eb7b7aff73c07e913b4db2f4ef3"),
        (177, 1752578845, "0.89", "1.1", "0x7d2e28c1270156c40cfb64562ba2334995b43fbb01d671fcce0c4a42376456a7"),
        (178, 1752579313, "0.89", "17.99", "0x73978b0f4c614078f484e8c0a79e7964ccf5883889bc435e13cbb43271b24baf"),
        (179, 1752582529, "0.89", "20", "0x3eef9d7f6f54153074aba2da8887295c041a4d208f94fb06b6d528eec3240cef"),
        (180, 1752587915, "0.88", "9", "0x1e5190d70c3056162d2d9d23a863024ee02e536edf5bc12b8dabe6c70b5a8ce6"),
        (181, 1752589123, "0.88", "40", "0x23d756f160522722d4f4309807cecb3f3648e016134c904cae163ca0cb50fa69"),
        (182, 1752590343, "0.8799999998", "215.909083", "0xfe43a0e6edcf533b38eac8ffd00ec03abbe09d91e6339b6d94c2b1f52a7d2fc4"),
        (183, 1752591253, "0.88", "20", "0x0a65ac4824a35d180dc9a1a9df7561865150cf934c90a622589d7db9d8f1a981"),
        (184, 1752591253, "0.88", "66", "0xe9ad892e6894b694e6307823b63832a5e8b1cc7d3e979f90e5628c1359e461cb"),
        (185, 1752591731, "0.89", "705", "0x5aa8207c2b960c23a98832b414735e482c6c753923cf19a2924a5991c2fbbe5a"),
        (186, 1752592806, "0.89", "205", "0xd427b8e0386dd4f6886aee13007225995fdab02e80fe5d00c9a13073bcb3c490"),
        (187, 1752593626, "0.9", "269", "0xab2a50bbd7bd27f4b166ddb787455e96ac45b3465e255d0fd1c77b57c3e47b66"),
        (188, 1752598682, "0.9", "15", "0x6255dcc9148cfa827d768836b8cb625dd2c3ad89eb7b9ac346a9cc72c2a2c509"),
        (189, 1752598682, "0.9", "15", "0xca188f86b6f413fedfe3c088815c3c11f07c7076c9dc3be8547758e73b5a8126"),
        (190, 1752598682, "0.9", "200", "0xe055eaf461cafc2ca4fbf81c910383cc451e5309b32ff93afbbc8e268bb3a251"),
        (191, 1752598686, "0.9", "1.09", "0x2a6e1b0f9839d5ea05ff1cae7d507eebb43b6f5e6a9a82df95e32e66fb122151"),
        (192, 1752598686, "0.9", "1.09", "0x2c9c6c49fb97e386883c00fba7ca37a27c62fed64939898065163d3b8ecf0ed3"),
        (193, 1752598686, "0.9", "1.09", "0xada97edbbf5ac8d47468298eb2e1f2fbd86af340014aca6e356b928fe838ea66"),
        (194, 1752598740, "0.9", "125", "0x0b79cd6932dc780b9fe64068981a55a3e487edf6a28dc539c9ad9d47eabdb587"),
        (195, 1752598742, "0.9", "1.09", "0x20e1c6e229fcbcc7080839a3c95a792af466733ada595d3105cef47828d0cc04"),
        (196, 1752598898, "0.9", "38.5", "0x2cef4dfcaad9a9a94578ff7965e11c8f93807c3a8c95ec58eee4acd0d0e9a6ea"),
        (197, 1752598900, "0.9", "5.56", "0x0ac91d0dc50ebb8fb801b4fd78743966820356d95b54968eb735bf856e8d498d"),
        (198, 1752598902, "0.9", "1.09", "0xa59b197812628b7c333eb965dcc45bbdfb219870f3381cdf46bd0a977d65cb72"),
        (199, 1752598910, "0.9", "119.44", "0x15660106d332dbf29bb549375bbb6cb2764f36c8f217237724a4d2e9dc10e58b"),
        (200, 1752598914, "0.9", "1.09", "0x98e80e1c6d42cd24bd7ef3dcbf8e5813c5dd6010f9ba26bbfe4ca9930dcd1559"),
        (201, 1752599263, "0.9", "29.99", "0x5d6cc4df5bce50035d2ee155a5abe5f43e2a62c9225ada54e8906172d3b540ad"),
        (202, 1752599263, "0.9", "7.73333", "0xe9110f3576ecad36747d22f6ee46d3781277cb7bef728204334519548f3ceb2f"),
        (203, 1752599265, "0.9", "1.09", "0x0662ebdeae8b179467be08587cf47c15beae9b5be39dd2bb95964d7288d29d65"),
        (204, 1752599267, "0.9", "1.09", "0x49718343b5cdfa2153cb960be48c61eaee573f305c9bc87ba941e89292ca4ffe"),
        (205, 1752599267, "0.9", "1.09", "0xdc89220c8d0be5e48a121bf40df2e2eee70a23fb9d0f377ce2831a4f9f620ff3"),
        (206, 1752600801, "0.9", "20", "0x9a6a53038177dc212eb28a732d29cf1fe13c0e3093c900debefa7c893696a6ba"),
        (207, 1752600805, "0.9", "1.09", "0xed69e10b6dd25ab4edd56f8188fee420e86dd9a34e03e241d3ecef46c94532fa"),
        (208, 1752601815, "0.9", "10", "0xc50c42669bb442a2014d89f76b162fdfa68bb53b349d3afc3536cd3bfb510f31"),
        (209, 1752601819, "0.9", "1.09", "0xa8a2f328761651c7788d3ef568d4df129e082824868458837d9d2f29be9ba952"),
        (210, 1752603431, "0.89", "80", "0xba38d782aa22f9f2d9f6c27771197ea7edab11683e05a473fc165d6a935794a6"),
        (211, 1752603435, "0.89", "1.1", "0xd9d9409e2f0b89c29f25cf6c456ac3a75c846044bf42b292b44328348f69f7e7"),
        (212, 1752603501, "0.89", "597", "0x00b10d8b82cfbbd61e1e9a6bca17ba82392ec62208fc694e85397132e1938c91"),
        (213, 1752603537, "0.89", "30", "0xc35c28a09af84e09b1f2d239bf559606df573651d43bd31a0c867775bd22d949"),
        (214, 1752603541, "0.89", "1.1", "0x3eaacf7e32b20d2237dc06bd4b87ae6e5a9c767038b2b81eda9b0774e9f1b74b"),
        (215, 1752603543, "0.89", "20", "0xb6159ea06825326ef58d9c6f1935cf44c9ef502006be190d7a799e62e7298766"),
        (216, 1752603543, "0.89", "33", "0xe65803220552b8560106c9243649398c082a4a3001e78734e873496843f09265"),
        (217, 1752603547, "0.89", "1.1", "0x394bab6f5dc1335d7ad834cb02fbc99f09ff0419d5b7bc820386f3522ea55d66"),
        (218, 1752605434, "0.89", "111.05", "0xccdaf3921b297e9e86b9cc43625c9d341ff3abbe87331832c4b2daeaa61ea90f"),
        (219, 1752605694, "0.89", "40", "0x486b842628d94f2c364340e8f151a93e2738804fa7a519044e0432e7e9ed3b01"),
        (220, 1752605696, "0.89", "1.1", "0x16ce37f7875e2a3f927e5b9e38f879b03207d77618ad43ab9406a7e7d1d37258"),
        (221, 1752605920, "0.89", "270", "0x5de15234afb46f72c5bd19642a7a8bc6ef6a3cc397f8c0f2b4cb087997bdfa4a"),
        (222, 1752605924, "0.89", "1.1", "0x39961a90b650cd69a97141d80cc9dad2511b8317f0e783f4748c4663ed33307a"),
        (223, 1752606302, "0.89", "13.7528", "0x794ce16d0ef0dee5adae03a59824bc0feba300e617eb44259b836b9cc5fac1d9"),
        (224, 1752606524, "0.88", "40", "0xca36e03c2785f2fb3f2a39c7b41cef92c6b545fdc5c25841af075b0ac9e62249"),
        (225, 1752606972, "0.89", "51", "0x388a00a722c88bf27eabe602933960e34bd14b21ddcb364f7eab646ab6202f09"),
        (226, 1752606976, "0.89", "1.1", "0xab61348bfd7d6be6b86d9b2b2ee70bc20bf6245239ab77c6e8974f847a25e374"),
        (227, 1752607254, "0.89", "40", "0xe59b5e8d1593d136da0ca0ad9edf9e625c1b4b44b8065b3e73912e091d12373a"),
        (228, 1752607258, "0.89", "200", "0xb5c1410dd423fb55c001188b693f7b5f9e92dc56288660528745d4d177344a82"),
        (229, 1752607258, "0.89", "200", "0xb8f206d91b671e34984d11cd16ae7591b9ef3713941b936ed723b0863fa15d57"),
        (230, 1752607262, "0.89", "1.1", "0x734aafa557eac4e64379bb44d6de27bed662d53e949781157594a366d3e2a09f"),
        (231, 1752607338, "0.89", "40", "0xa656cb570a1d456bc788accc6a62d0f5af1a270f2321663bb628c0a740bd0e1d"),
        (232, 1752607340, "0.89", "490", "0xd094907033e080a7fef6fb57dbc6403b279a07192c31efe5b0f483419b974d9d"),
        (233, 1752607342, "0.89", "1.1", "0x7022b462d00e15dd18061724d7b38d2cd1d4a9269de32f6f99b43466b079be58"),
        (234, 1752607394, "0.88", "250", "0x613271b6f4f02ee0ee8ed7f9a17526515aee2c011d80f712639e22b74b99defc"),
        (235, 1752607434, "0.89", "2.2", "0x4ff2a9a7d2d237f992f684d3081d58719671678e39575ade5efd9815b1044d4d"),
        (236, 1752607556, "0.88", "47.77", "0x9b303ee90f61815666e534ee59c0d0b5ab9ca70400c05e7036c7e40eca73c5a2"),
        (237, 1752607556, "0.88", "39.99", "0xb887f3a270317709814d3644339c4cd8ae555177e0ca21b26fb0b58f9936102b"),
        (238, 1752607568, "0.89", "24", "0x3d35d8deff95e681afa468de293d3b5e49832b36413e2be01fc50062a338c311"),
        (239, 1752607570, "0.89", "40", "0xc8fa5a1479489c228a187a4845d9fc5ae280b8523d6894008de310ef01974794"),
        (240, 1752607578, "0.89", "16", "0xb94ce08bd3dbb2c17db99c11da4339a0682f2f5c57dc71d9c41e41ffdb0a028f"),
        (241, 1752607634, "0.89", "10", "0x5db74c4286bc50f0b80c06c6528e6a4a60942399547987403ebb892f3e9d1152"),
        (242, 1752607800, "0.89", "820", "0x2beae09a0fd4adb8ca3a2c3a9c38f24ce5d8afb9b653f86940e49c67cc32dbe3"),
        (243, 1752607800, "0.89", "39.99", "0xb6b2cd1a65a1b876c38f935d25eedbd5e4f3920b67b292ca576627d6222df54e"),
        (244, 1752607802, "0.89", "140.01", "0x0296a30792ff4c62885205338a2eb9f0d1c2af4f34354d009ec10ced6c8c7ea6"),
        (245, 1752608596, "0.89", "594.59", "0x844237299629052cc096fc8267f1ce6f2b9a098d86a2938d00661268113664e8"),
        (246, 1752608600, "0.89", "16.67", "0x8adf5684f9b3783c5b2f532bc08696e7a5998d3466d5bfc5a29b8a49bf179f4a"),
        (247, 1752608602, "0.89", "16.67", "0xc4e9ca44f50e810b1a9b2a84dbfb3b5d899619de62ee13d3ab0d6adfe413fe7c"),
        (248, 1752608602, "0.89", "16.67", "0xcb56344f03ef9aec9b9e702e7ab457bb79c030fd762b7cd5748d47253bbf88f3"),
        (249, 1752608602, "0.89", "16.66", "0xcc6f80890b97ddf2aaa5930e9c36b41cabb0e9857412ef54c0544ea887fe504d"),
        (250, 1752609072, "0.89", "599.91", "0xdecc47ba05035b34b71ae6c999080efc060f823c9e9f77718ef16fcdce1063a2"),
        (251, 1752609236, "0.89", "10", "0xd80939dc2b27d7d2949f1ca50fc16219a76ce831126cef4b1d28b3e4324918ea"),
        (252, 1752609238, "0.89", "13.86", "0xb84916fca7d8ec62d8ede03e5fab6ee24451757dc5332d0dceb1c45f18aa637d"),
        (253, 1752610960, "0.86", "1.14", "0x28637a7002b4c58e23a59fe046e7e906c7ed8898f6dfbc0e819cb494200bc231"),
        (254, 1752610966, "0.8627938", "3000", "0x901e1a44e63d6da01f245d93fed6fecaf71564029a6f6eb5b39ae7b3a60bf93f"),
        (255, 1752611002, "0.85", "1600", "0x649a8e0d2d7cf9983f82c04c4581b8f7560e17c2394f293e0fb301a72d47e92c"),
        (256, 1752612397, "0.88", "100", "0xb1e99408be5f60e87cc43f91a25b106090a95739c47691ba0b882ee39ee0ee4b"),
        (257, 1752612411, "0.88", "14.95", "0x04fa6f9dad8c59675e8490179fd76c2624295fd2c39b8120db1957335cc3a7f3"),
        (258, 1752613959, "0.88", "20", "0x8e0f87154dc6362a03d1f275e66835cbd4d4089b993f00c4b4aa6d0249ea2919"),
        (259, 1752614159, "0.88", "33", "0x208962e535aadc5641f704e90c74277b6cbbcc0d1135b12ab97a64da14eb800b"),
        (260, 1752614923, "0.88", "10", "0x48beee4a28e6976dbb53837ec0e55587c3292e9f7dce509cfa77c53f468adc7d"),
        (261, 1752614923, "0.88", "17", "0x74c72db8963bf8e8b8d1f11fee7420463949305ef69fdeba8541ab9a48d51485"),
        (262, 1752614941, "0.88", "5", "0xa5864dedc1a2b06d8320c98f3be766fc6a781b23c44addf7b726f202493c53d5"),
        (263, 1752617197, "0.92", "50", "0xecff6662ff104249dfccb189ee263fe8e0fde055d9fb7549524efa28593c6db1"),
        (264, 1752619583, "0.64", "60", "0xe5386c72c88510c9ec34fbb814fa7c858d8b7a70cc17fa4ce8171c69afb75b27"),
        (265, 1752620025, "0.9898192771", "830", "0x51df5ceb966750dfafdd99dc80d4304945e069029bfb9f4fe8a8b03a97eca546"),
        (266, 1752620081, "0.99", "805", "0x393098390d311fda5c076ea3fadc815c4a4b50b79e43937b6e7fead6296bbd79"),
        (267, 1752620697, "0.99", "805", "0xf810bcde8548d7b62b5cbd3c4d61be239b773a7f04cda68db8d547c73e84df04"),
        (268, 1752620853, "0.99", "34.99", "0x87a82f78abda7ebbab1db014fa8c3b3fdfaf689148c85f2807f1bc859f733943"),
        (269, 1752621577, "0.9951351351", "1850", "0x62ab40e7b294ba97a2e3018d97a4c4111ecb4a7e0b1ed32389e22d572cf68cfe"),
        (270, 1752621645, "0.9989766249", "1282.99", "0x0870dcf82bb955cc727e0f4c15c42331561e26ab721965a0f5430eaff446c3d1"),
        (271, 1752622053, "0.999", "1176", "0x42dd7e3c1b7b8b71e1cbcc6336e79755de7c5cafd943de330ea6fbfc3e1ce309"),
        (272, 1752622115, "0.9981667222", "29.99", "0xe6ea0de2acbb8c5425e26806db0214f411bef448e2c1ba6392e3450babf756bd"),
        (273, 1752622255, "0.999", "100205", "0x2ba754b178284a5059bbd4ead6ae541fef5a1dbb02f769e040b61028aff83c1a"),
        (274, 1752622527, "0.999", "205", "0xc36c65da4999df21fed10c23d74d7c124be5be66b8abf6c9b6971b4935deb7a9"),
        (275, 1752622563, "0.9980292398", "171", "0x17071fea643bf309fc31ae957f8b38fbeab58cd545e72393e204878b55405a2c"),
        (276, 1752622747, "0.999", "205", "0x772c25a0bf0915c02b3ef78f06d8749c95993f7f8eb9053dcd04a4dfb6dbee4b"),
        (277, 1752622791, "0.999", "3805", "0x807b2dcfe1aeda8cb4a8c0600de440d3425b9c1e5ff155a4d37d4b4f1a7011da"),
        (278, 1752622843, "0.999", "3205", "0xb57dabe17ddc7e4f5e3328d06cefc1bb20bbf7536b72c99a3849c7b7d605e72d"),
    ]

    fileprivate static let retained563327Yes: [RetainedTrade] = [
        (0, 1752510202, "0.05", "923", "0x959d7395ff5dc3014d80f2116b2e6832940184a12227e610f525d13d43c14988"),
        (1, 1752516056, "0.05", "10", "0x304403a00f7f4a5325148096af43224b8569df047256d4679b480e5d91f084ab"),
        (2, 1752520513, "0.05", "8", "0x7500bd6e3dc39051a6a7f2f6f4ff3aafc3985bfd165bb9bc7ac2cd0560ff3f12"),
        (3, 1752529025, "0.0589285666", "186.666665", "0xa8f47338a95115a783a83be1456ab3fdf7988637b790e3e5c3951ff17c84801e"),
        (4, 1752531501, "0.06", "12.5", "0x49767cdd5601f0c5e4397eb2b581826ed8a83692c4512b064e5d51616ffe7021"),
        (5, 1752531597, "0.06", "12.5", "0x4bbb930614ec78d1e6e3b83db13211ca250de7b6b5a6a87c5e0165db48b3fe7f"),
        (6, 1752531597, "0.06", "12.5", "0xff08c1a04e9c2df960cce2b94580c88062121c6546c3ca006754c305f84366d7"),
        (7, 1752545815, "0.05", "11.63", "0xaf9e572ab4665321ba9cd50dcac5abdc2a1561228279dc8a344b8a2aca2ccd9e"),
        (8, 1752545823, "0.05", "23.25", "0xb46fbb5853c502552317f810fb9c1b4ba2a123acb3b9dc3535d4cf0d082d79c2"),
        (9, 1752545827, "0.06", "12.5", "0x08435f79c326ed4779ef9635bc42899b36af3e058fb91ecab7d2f8e575b24c63"),
        (10, 1752545827, "0.06", "12.5", "0x72d4dd10cdd48c2aaa52ad74f427b5113fbca23eb93f4d6b4375c9b9afaae2dc"),
        (11, 1752548832, "0.06", "12.5", "0x6ad724eb62fe564b1a45e1b33c48a7d52e0e90f57e505e7b8ed4653dea1089ef"),
        (12, 1752548832, "0.06", "12.5", "0xca514722b892121dd6f7cdec8544cc4363d441bf67438844b33cbf6cf18525d5"),
        (13, 1752548834, "0.06", "12.5", "0xe4a81a05fdcfcc882bc51dc2b4aabc9815156882162089b369d144e80630469f"),
        (14, 1752548836, "0.06", "12.5", "0x0e0a0521ce1931622787feeda0773178659b8f7d7d3d8b9de954c0099e0dffd4"),
        (15, 1752552357, "0.06", "12.5", "0x226f5f0f313c5442473518a6e46bce67ef424c7c0d9e8dc194500dbc6e1af4e7"),
        (16, 1752552357, "0.06", "12.5", "0xc923326637ef9b370a3814889c69f3997d79da0f8266a507e4ba18138aa1936b"),
        (17, 1752552377, "0.05", "5", "0xadbb0a8bd2a132c40ddd82cd11b77d2165273b2ad4e002820c52b37e90c004e2"),
        (18, 1752552379, "0.06", "12.5", "0x0bb0ab56df91ebb10b4568f58649638fa37e10358cdbbeebdac126884b117b0e"),
        (19, 1752552389, "0.05", "3.01", "0xf41c1af112797b0fe3761e61d91362ce2c0ca65f873616ce69d0ba8120bfcd3e"),
        (20, 1752552401, "0.05", "3.99", "0x98fdbc5e2e56c4d32200d55cbaf7ed11215eabb4f06f54ea6616763229491ca1"),
        (21, 1752552403, "0.06", "12.5", "0x043caf79ae5803e3ee2ba1f34ce3ccd22f32301846b62d948a158bbc2a635057"),
        (22, 1752552403, "0.05", "21.01", "0x8df64114e39308f97d05d109d9bb694bee72ddccfc4125e5798f157db29b07c3"),
        (23, 1752552405, "0.06", "12.5", "0x848ec42445b4c23a7d9a45962241b675661028ad71c7ca58b581e4c5e5339549"),
        (24, 1752552407, "0.05", "5.99", "0x41034d4a00a2c3c0f63767af807019d49d5f65dbadd1b76d841a8608d98ed968"),
        (25, 1752552411, "0.05", "27", "0x64dddc564467837adad5c878eb5e325ab62609f9be3380bc05e3669f82878314"),
        (26, 1752552413, "0.06", "12.5", "0x3fb3700507d029032bd0a8a457f84aa633d5fbe9b88458282c98ab19d2c5ccaf"),
        (27, 1752552415, "0.05", "11.01", "0xe3d5b2fdcfa1a87ae8ef29ea79e4a508a2b4357af91beb1d814fcc5756a5ab28"),
        (28, 1752552441, "0.06", "12.5", "0x05f3bdd81aec9ac55ce18884adf9aa7c7d08cb1fe666bd75521d932c11b7ef49"),
        (29, 1752553011, "0.04", "5", "0xe951f41fca7ccc6af198d0629b4f6f0961187319ff052487e6c10561b332a169"),
        (30, 1752563145, "0.0599999972", "319.666665", "0x97cf662d0887a22376eaf22d665a864534a8b0cdf92e3da842f4bd51adc7777b"),
        (31, 1752566381, "0.05", "96", "0x6bd5a63e407b3c747ddcce21c6f466f302e4b84ba7722a355db8fe7948565230"),
        (32, 1752566381, "0.05", "103.83", "0x8df75538bb9a9c29cca159c1b70dc88a6be8c9b4f0ca6e19b8afe714da349243"),
        (33, 1752566385, "0.06", "12.5", "0x0e9ad9ab45c1c279e18e91b56a416e478749936839031d08e797ccba2ca308ce"),
        (34, 1752566385, "0.06", "12.5", "0x100cf8dd1484867b29a48039ea4770934d47acd76a3837d812d736c5186154e6"),
        (35, 1752566385, "0.06", "12.5", "0xcafb2c786aa4bb5620d98489c4dd1cb502c36389971d824a540cec33fd69db15"),
        (36, 1752566389, "0.06", "12.5", "0x0e1acdbe9c6d3042e99509db9cdfaa55d1c553cc1f590bb5ead14426e770ff7e"),
        (37, 1752566389, "0.06", "12.5", "0x2429e0a392468f6c77ee63997b7f09b1264247bb2dce850b279721bc48ee6644"),
        (38, 1752566391, "0.06", "12.5", "0x939fbeb0a618303d8fb8f071e709cc2b2bc7cba057950eff0338641f576b0ef1"),
        (39, 1752566560, "0.06", "20", "0x751a4b14f8bcccfd05aebdee5a09ad22f4d255bcf84d14498771e4720a7c22f4"),
        (40, 1752566626, "0.06", "350", "0xbc30b80777a40c1b84af296f9517b5dd34dfffe534b2b9f9ceec1d035005c78c"),
        (41, 1752566658, "0.06", "12.5", "0xa6bc933a100c62a4418b643edf317b73f1c56557e798cb775d006a576cae9827"),
        (42, 1752566662, "0.06", "12.5", "0xcd22895cb90df7e43ac2d30547e88a27def2a0863f394dd4b476acd16517611f"),
        (43, 1752566702, "0.05", "25", "0x1990a3bfcb31990c4f8b3c7bc2d78f805ee2682fa0ab199169d294440d0c1ec7"),
        (44, 1752566704, "0.06", "12.5", "0x1467ce5eeeaaf9f7df6a508b14ffd160f160119bfcec408ad58ca3f0bd4a5bd8"),
        (45, 1752566706, "0.06", "12.5", "0x80de64245b676a3699e13a63cd27b04a7566674f232b03f920c89aa0df4371eb"),
        (46, 1752566746, "0.06", "12.5", "0x0d7f8ff0ba6b71d12a4889ea3dd0ceb8b1f90934b4c122cc7d0cd19fc8494945"),
        (47, 1752566750, "0.05", "22", "0xe30c2d264b6ec976d03a6c1ef3e764cbe54cab93ff58dd5b63d7fa87f0cd7f96"),
        (48, 1752566754, "0.06", "12.5", "0xa2533326d3499c10aec698bcfc8658801c3c0e57eaa0cc23ba344f2978e74f33"),
        (49, 1752566764, "0.05", "11.66", "0x5e75088a2aa9502086a1d25352fbabf059a0019d4e61ba460a738610392362cd"),
        (50, 1752566814, "0.05", "206.62", "0x95718c3b02a561c8e635ba5d20902b119d6eb4d558bb4ae8a785837e8bb3fb27"),
        (51, 1752566818, "0.06", "12.5", "0x11845717b726d18c280194a28774f6ea069c9b8271360c29bbe30c1ef42e9a9f"),
        (52, 1752566818, "0.06", "12.5", "0x87b64d9069d50fad68ee63c43c64a0a3656a8e8f6757afb39013b953db1e0689"),
        (53, 1752566818, "0.06", "12.5", "0xf6b48b08d2e8120dd32942517ce122cdf1cbb7ddc24c7b53d204613efab02c86"),
        (54, 1752566848, "0.06", "12.5", "0x8597499e1d6288266a3b066d79ba293b47550d1689d53d47fc789aabf30c9835"),
        (55, 1752566856, "0.06", "12.5", "0x7dea4b507a3b5ed2625e217ef3506363992a6f0a124975c484899457b4aa9631"),
        (56, 1752566864, "0.06", "12.5", "0xa588a9cfde04cf9df8f2cf650bc074bfda72d5656ef1c4f05c7b7c40dfce5fc8"),
        (57, 1752567086, "0.06", "12.5", "0xcf6b979b8ab557571bd9d397ba15b2a4ad2e80c31f1224162ec5e67b91ff1b94"),
        (58, 1752567937, "0.06", "12.5", "0x31be0c7782b216e998e50ee90843c5ef2da46cf651da423c87ce6b29a4db191a"),
        (59, 1752567965, "0.06", "12.5", "0xa672c9b8f0c78a0103bd605bcbfa2697d08c76ec7420ec7308dbd87c62fae53b"),
        (60, 1752568198, "0.06", "12.5", "0x7aec4150c260127465c1f797e7b1964310d492e533bfdc2325d8f9adb56c4b67"),
        (61, 1752568514, "0.06", "12.5", "0xa56107a6a109e8e82fa54f96d52b7525a50506b9cc7b3ca92d960ec15ef18ed2"),
        (62, 1752568522, "0.05", "1.91", "0x6f5a583574d50dcb0e7463cced628e02dac5768abea6b703069ee5e60b982f54"),
        (63, 1752568578, "0.06", "12.5", "0x46dc0a2aab215cae7cee52fbb9dd9bbb0d6f501016762d157cae20dd18105f43"),
        (64, 1752568714, "0.05", "5", "0x74cf8fed21ce4bd5b2574c90b6deb17c4f0a9eb969fd5917cb901e8e1150e63a"),
        (65, 1752569727, "0.06", "1500", "0x32a62d77ba17c369e83676f7076345d097b0e848853aedc96458b79751d44538"),
        (66, 1752569779, "0.06", "12.5", "0x972a5ce2019ed4ad3d94570d206370c5e338e5809040c32fc09dc22e49de716e"),
        (67, 1752569795, "0.06", "12.5", "0xdabb9beb270f845703c2dac18f2f00e6daeaaa17a3a9fb82b77455d8717c65df"),
        (68, 1752569809, "0.05", "10", "0xbb9f8028e3dfc218ac10e9060bbd9bbcb58afb3fbc4ba7d54334bae6b9e4e73c"),
        (69, 1752570173, "0.06", "12.5", "0x03cd894634d492fa7f12281a9781ad73a5f36c0e4da694c5b866f518e1541c2b"),
        (70, 1752570173, "0.06", "12.5", "0x72363c3e7c76f23f35dfcc4dad420c62c3ff189d0e23c0371679e72d9be42f00"),
        (71, 1752570173, "0.06", "12.5", "0xa66698143f783207cfa4f43a24f75961cc367dd0a0548ed08087dc2815ccdcab"),
        (72, 1752570211, "0.06", "12.5", "0x1ed00525d702fff5af404d26af3bee75b2bcf2938e1f866bc7e7b9cb52e95dde"),
        (73, 1752570211, "0.06", "12.5", "0xb6286b7a8adda49721603014d3988ef95e60b2211fd345ca5e96e09613eea001"),
        (74, 1752570329, "0.06", "12.5", "0x12363b3c9dc77f5054ad68945b140cbc00a176c170abdbeac6897ff63b51058f"),
        (75, 1752570575, "0.06", "12.5", "0x0de1e09c9273afb26b6b3f57087d782d7206f8a321303b2964f845212f0bdac3"),
        (76, 1752570575, "0.06", "12.5", "0x944634bc4b40257e139fed824bf16af6c8072f65a8556d36afa081bae2031003"),
        (77, 1752570643, "0.05", "223.09", "0x54a1c883cae2f6631034445dc92fcf258c3e7d314805fd52f2daca2be88257cb"),
        (78, 1752570645, "0.06", "12.5", "0x03bec7b285f40b47ab15c60e7f0d065c638edef0a9b973d48eb2d682283f240a"),
        (79, 1752570645, "0.06", "12.5", "0x67eabbffde71aedfe48c6412575bb932ec804ed7e431b45e7d5f7279ce267a04"),
        (80, 1752570647, "0.06", "12.5", "0x267ce0f0a283077c602e2f0a267aa55e0b7416a7ed575d30e6081f0f32508b5b"),
        (81, 1752570655, "0.06", "12.5", "0x3fd9939b906109761c4fbdda5c759e1211506fe8b0fd59281513481cf2b2ed8d"),
        (82, 1752570829, "0.05", "240", "0x7f3a08a37fa542a99720d47b27f8a0f90caea735d9c54ca7f6b21b8e5b7faa42"),
        (83, 1752570831, "0.06", "12.5", "0x85404e943ed401b8914f1afdcc829eccef2ce75c8f0da8fc9e614689e8904c38"),
        (84, 1752570831, "0.06", "12.5", "0xb1b166a34db229a814dc1eea1a6d0828640daaf98b2904052e34ed26c02d252f"),
        (85, 1752570831, "0.06", "12.5", "0xc8b87de1a51053cd24ffe17b1a7628dabb88295dfab6b2a0d4898889957524d7"),
        (86, 1752570833, "0.06", "12.5", "0x8a0fc3bf1d3fa9b85abfa8a255f5ef82e9cf23720ac2957f4f826bebdcb8972f"),
        (87, 1752570833, "0.06", "12.5", "0x8c799014f4dced65368a69ad0eabcbff75bfb53b5784247191c5b8776d74933b"),
        (88, 1752570837, "0.06", "12.5", "0xbff3af32beb3b5b93cf52dba67d37d0370cd518ae4bb867e3e8abb2d7814ced2"),
        (89, 1752570861, "0.06", "12.5", "0x2397cf8989d6e83d7384a55a7aed333f0aa4831f4c812690a9ad05108cfe7101"),
        (90, 1752570865, "0.05", "5.28", "0xf1b4d563b76e3515b56ae71d9097a0e420a37604e41e4e7056e7109b08a7b347"),
        (91, 1752570867, "0.05", "195", "0x509dec05940fc6ca62c1603b35c42e87f092325104d60a036be840805ef8dd6e"),
        (92, 1752570869, "0.05", "39.72", "0xc26298905645b0ccca9bad41a839b31ac066b216327f967397bd27fa5150f84c"),
        (93, 1752570871, "0.06", "12.5", "0x4243ec2d8bd600538a503cded515a3654010a0de6b6f64031af684161bbbab5d"),
        (94, 1752570877, "0.06", "12.5", "0x8688b750e10759d9cb6b3491aacd55723345ccd3543fd73e2ff8ae87eb617621"),
        (95, 1752570877, "0.06", "12.5", "0xa7b40f1d4b11200d673b528613fe3f1f3ffd425391ec1cd731196390c9e33b2e"),
        (96, 1752570891, "0.06", "12.5", "0xfe172b3902a645979a242f4c79865485ebf54b6333b6ed9aaa4a5a47f79a7c34"),
        (97, 1752570893, "0.06", "12.5", "0x8e766ed46c6a4a98a54a978dc46d1b6623a4a7e8564a210b42a3abb822b8384e"),
        (98, 1752570895, "0.06", "12.5", "0xc3e99f7520fc01b17438751296c229e248db8ed0d5198232db1e3a28b57ceb3c"),
        (99, 1752570903, "0.06", "12.5", "0xdf5ebce1e58c23e443181753b8e30c128eefdec0f5fdf44627a33f81a8890ebb"),
        (100, 1752570915, "0.06", "12.5", "0x36fd5d0dfef4170b48b8adbb58e0e2386f2906cb6cb4527f7c94cdf2460b5eaf"),
        (101, 1752570919, "0.06", "12.5", "0x95f97be7631b383687ea1dd8e4a3a9d909388f8c3673de1946563aabb4ba5c51"),
        (102, 1752570935, "0.06", "12.5", "0xfbe45ccf055e9aa15fc66b444fe9b58dfeabff2cd8f22d1e33e1808fc325a998"),
        (103, 1752570943, "0.06", "12.5", "0x04679eb6cd24756dd0711bbf2c89f1160833cdae9a10368e6024f891b04a9e50"),
        (104, 1752570955, "0.06", "12.5", "0x992457566b874f3da04b86a45c8728b83745cefb18bdc651d3036289c5014f44"),
        (105, 1752570967, "0.06", "12.5", "0x521b3622c73c93145dae0808e2af3c4d7e029c52dc9a5a2906304d3f3a11d6eb"),
        (106, 1752570987, "0.06", "12.5", "0x8180e49ddf50d8a91a544bf36590ce03a36a570fd2436b39e35ea81f351a0ecc"),
        (107, 1752570989, "0.06", "12.5", "0x71d830f91814a9f3f6814dd7b056ac3b6cd78ccd68a98ace2426fe6059460bd7"),
        (108, 1752570989, "0.05", "240", "0xc2cf79ea205237425bdc810c96fe45e302b2160ddba12e8f52f51ed4fbde804d"),
        (109, 1752570991, "0.06", "12.5", "0xb114d1177c7a5e44a6d3b3da031bcc3f77cae4fdf5e31274fb0e843aad0b73fb"),
        (110, 1752571001, "0.06", "12.5", "0xfe558dbe771f8c1045de652aebb1ac8efa028ef9c91cab2c5e5aeff47e91204e"),
        (111, 1752571003, "0.06", "12.5", "0xe98e18e7761af013cbd17058d4ecc92327d16fd67da1fdcaacfe1cce09195ceb"),
        (112, 1752571163, "0.06", "12.5", "0x282582dd86b7564a4192c744d1c74ecf729fa16b63b1fae9003f5c010cf7be0b"),
        (113, 1752571163, "0.06", "12.5", "0x6f17c10578070dd68b9f00b91bb36d2c6ef35b6ac67a878d883e433c5ab8818e"),
        (114, 1752571163, "0.06", "12.5", "0xce471d2fb3a634133d8f8076e19b1d6aeae51398f1bcae60d6e0edd524736255"),
        (115, 1752571297, "0.05", "45", "0x4165b1d642982053a7a6f04b517642406daff934c87b97dfdb8315bf94a2c489"),
        (116, 1752571303, "0.06", "12.5", "0x9ad259fac37ae54a659d8f6167960d5028a07ccf03d408238130d187222ec2ad"),
        (117, 1752571305, "0.06", "12.5", "0xd888776cd8b355669ccf3b3ee09f559f7d1db2568e700f773c2e839e8205b7c0"),
        (118, 1752571785, "0.05", "50", "0x165d39404f6c8a4f33ae5127d7f34574bc5224ca8a47a70c74437d65b63af3fe"),
        (119, 1752571787, "0.06", "12.5", "0x8e7cbc3044940136fc6a66a9c0aa2e317e53fd3e3f4eae91376d39107fe4fb20"),
        (120, 1752577545, "0.06", "100", "0xce423032a5c89792319a141a11e5af24dd4f1381fac6d216a1a16d3f46b99fe4"),
        (121, 1752578845, "0.06", "12.5", "0x560b6ee0df91eaaefc42dd7fa581577fac3cf4946873132739e9a83dd3a78253"),
        (122, 1752578907, "0.05", "1.41", "0x129c0ebd946a650b99bed36b2e67dc4771947714e649db6a06b14c2746c7a6e5"),
        (123, 1752579313, "0.05", "0.01", "0xbb6588352f3c194b39f8a9993425883c0570b8bdc40d8d7677f3d7f9d78a666a"),
        (124, 1752584453, "0.05", "200", "0x0a7617c931a2553725c3468b39353d0b56e0f39b4da0d323a100cef0dbc2c17e"),
        (125, 1752587913, "0.05", "180.99", "0x12627ba9e784f5071a3988fe0e01394b091a954a5aa9ba6a9d85ce93a7785ed3"),
        (126, 1752588081, "0.05", "3", "0xc8bf4153b6318532be196d0d9f6603594cc05870f25e2aafd07116cf3e96e6b7"),
        (127, 1752590933, "0.05", "485", "0xfae5efdb4ae87cac90899981941a03b4f2ee406d04384bdd17b5220d6cb9e81e"),
        (128, 1752591263, "0.05", "26.09", "0x8897449f59a21fb6231432b5fc976cb6cbc5da66cca2717775631329b468154c"),
        (129, 1752595372, "0.05", "100", "0xa8e0f3911b30f4cc4d6d3b53aa1e69a8b78e30ccbfd6e276036f4b88f6c804f6"),
        (130, 1752598686, "0.05", "14.29", "0x9f7607c34f5b595a3842af8f664b5e6e71c14ba734612a4930050c09436e1e69"),
        (131, 1752598742, "0.05", "14.29", "0x11bd0b282804f237a6f7e9198cf5fc7072a606dfcfac193dcd6bc213569d4c71"),
        (132, 1752598902, "0.05", "14.29", "0x7898650f79de08f8c8fe0f8eb71ea34cc2e189d3c0f6ac17ca37c3f3a2da86c0"),
        (133, 1752598914, "0.05", "14.29", "0x2192f3524d704124b55ccdce30c3f63107c7334cd6aabe7ca4730822e2460ae4"),
        (134, 1752599267, "0.05", "14.29", "0xc22749ee60d390934e0aa10d751d1f64fa89a6c8abe0a310ec003d9f41fdf95d"),
        (135, 1752602457, "0.05", "398.51", "0x90bed49a81f9538a645c15efddd6142272652dcb059eade9b0a2a340d73f86ff"),
        (136, 1752602461, "0.06", "12.5", "0xd09cbac9e43daa5e018d780f9f83a25f435b40b2a00b2c198d3fb68a4e7fde8e"),
        (137, 1752603351, "0.05", "5", "0x18b3ead70a14bfadb2756d76ea1095475e568483928e5182962a39e0a1e31d84"),
        (138, 1752603429, "0.05", "86.99", "0xa25351c66a5e1148d5a5b84722aa36af6f9bdd111b7fa23ebf8ac3ec65f43d78"),
        (139, 1752603431, "0.06", "12.5", "0x4a31211833c4b98fe2b73f1bf1a8ec357bd442be14f57649e7a596cc75101b2c"),
        (140, 1752603435, "0.06", "12.5", "0x88c4e9a1a81eda7143c82d73a363fbe455df7cc5c4e2cad5f26cc4e2a85e62b3"),
        (141, 1752603505, "0.06", "12.5", "0xf392f1d4074ed6c54b791c35dc934a3f048a5a37a95a5007d3027d5331b53d11"),
        (142, 1752603539, "0.06", "12.5", "0x9455b108b823f411ddfc05ffaf3eb225982aa98a03ce25fe58e745f4a880b80e"),
        (143, 1752603547, "0.06", "12.5", "0x30a535a9fef76d020c6eaf6fa2005285d0d4fea56ba492b7b617066fcefbef7b"),
        (144, 1752603549, "0.06", "12.5", "0xd42a3e6e18b82e13b7be244d621bdd74446fc4d8012f911cd742c5a42161c69e"),
        (145, 1752603796, "0.05", "3", "0x0507c4274c2827d3099465af0794f4aa1f1206dc945c93cf19e1d7a8f91ae8da"),
        (146, 1752605698, "0.06", "25", "0x676c9e6dbca4444d633d52b0169472eb743ece343efdb0b7a042ba2679bc8163"),
        (147, 1752605764, "0.05", "2.96", "0x897f4a24cf88d5e0a3b5c1258280eb6941868808aa349a66db79583c0e67c4c7"),
        (148, 1752605924, "0.06", "25", "0x7e962b6ccdcf5e8bd1829a17bc0079911f5da52e54062e3a5d771c8020340ebc"),
        (149, 1752606528, "0.06", "25", "0x07945d113711f6950a77c70628e436907b2ac2793b9d9a1d93b03a531d5a4b44"),
        (150, 1752606976, "0.06", "25", "0x59eaa86cfaf168b9e9b93fe94cf9fc4cbee93faf4a182b8a3bd6b3b875d78c3d"),
        (151, 1752607258, "0.05", "200", "0xa23889450ebe699aa02a633a2374e156bc0f7595338d32a1d3bf9c8b84ebb94f"),
        (152, 1752607264, "0.06", "25", "0x87155e60391eb2b46c393d26cc14c481518be45d8a3d1159f497ef312f8d0b8e"),
        (153, 1752607264, "0.06", "25", "0x9a4f95e215a20267f0009e2b32b21439b7e34224ade18c793febc3c03c7f6521"),
        (154, 1752607264, "0.06", "25", "0xb8b75a3fb95911827ee52694f9f9e636a75e3a4c3246588eeff797c24340a423"),
        (155, 1752607264, "0.06", "25", "0xc00634cc73f3e30ab257386fba2ec31117283021878568175c29d2cc06d87a26"),
        (156, 1752607342, "0.06", "25", "0xb5335dda82581d87378e868c64d9e57c5a0b0bff0a2c288fb0f9f36d244b2fe8"),
        (157, 1752607342, "0.06", "25", "0xd311e91c7c773661d78c5fdfc5b6ca581c8e1d68243fa5029ae6f4f69ee71a8d"),
        (158, 1752607398, "0.06", "25", "0xdfc4b4f41b50dfcf73ecf98990b90de17fc7b35436e92ea41794d6f52fa40f97"),
        (159, 1752607432, "0.06", "25", "0x09200666af21ce544e4222dfb7428b7d563a0efe89bb2c2a5649015fcee13607"),
        (160, 1752607432, "0.06", "25", "0x9da3bf0ffc339b02a19accfc167a8fe0a43853bad65a30f57a62ea2ca245e4c8"),
        (161, 1752607556, "0.05", "167.24", "0x8a7dc58024b5039c551b4e6854bf0440185040481601bdd9b1a115bd8e1d5396"),
        (162, 1752607560, "0.06", "25", "0x81a4b450975c8ae2bd0a9ee2af75039336a15b9457be502ec547a34414fe9f3b"),
        (163, 1752607578, "0.05", "8", "0x94d8bf6a0c8e093e9186826773f4670053ba4022068cb81d5c8d1c32782f54e2"),
        (164, 1752607582, "0.05", "5", "0x71a0e310b7e267c3b065f282370fefead6bcc3ae749f66c21b14317b603309fe"),
        (165, 1752607586, "0.05", "24", "0x6d2e147d8702ce23f6a17b5e7e4dc92218acaefd3b2ac9e35ec92db9354dab04"),
        (166, 1752607990, "0.05", "165.03", "0x190452ff77ddd59dd517516a2eef1eeae8ba19237026433cd62e8241ddd7faf9"),
        (167, 1752607990, "0.05", "299.68", "0x436b4bf3abc42dca6edd897745c0d181fb5aaeb43d1c185a6db6f9c899f5d133"),
        (168, 1752608596, "0.05", "209.97", "0xb558843d38dc663cd1b9c81df199c2b6ac222336c49828fc1763c77ff4ac29f3"),
        (169, 1752609236, "0.04", "10", "0x45cbe95c546a97e6d460e21713c6be504f5048ee91b8dc5d24c09e328f0cd456"),
        (170, 1752609704, "0.04", "5", "0xbcf706dec2dec3adb24ce47ca423854a209fa3a3d589c8a6478abe9ae872dd7a"),
        (171, 1752610088, "0.05", "100", "0x248df5cce79538450f867bdaeb8846c9884e325242884d525021a9405724cf70"),
        (172, 1752610958, "0.02", "9", "0xa4bb9f4e95af5f410ff25af261dbd2537295abd1ff7fcf0f63cee6d49b4ef58d"),
        (173, 1752612409, "0.04", "5", "0xb7881581d3bd5ca9240aa64c8f3a3230c3c14bbaebf78fb20723ee2e0bf84ed2"),
        (174, 1752614155, "0.0294761905", "105", "0xf5e7a3cf3a129806fbb0c8976196b731d5db1aade33f533bd1e40877a52c2ab8"),
        (175, 1752616117, "0.0279999733", "35.714284", "0xe305f30161021a0f9d984717d351ee50128000a37e82f9381df42b7c36ccd7b9"),
        (176, 1752617163, "0.0165853497", "60.294116", "0x6446c4e235fe6dd848ab1cba4c3187a8c8499b50933a27a963ee5677c87c5af5"),
        (177, 1752617191, "0.0189504337", "263.846152", "0x031a8f84f845bca838359022ea2f97e50ab6d2d6d502183a129d74dada715a47"),
        (178, 1752617323, "0.0013152681", "983.29", "0x4be6595a85671440b33e3e5020bd587d7c2b9030a14b50e24ce6b9c15e7cd96a"),
        (179, 1752617343, "0.001", "299.56", "0x09751811f51f9c95cf75919e6acabe862ab855a2d22f6fb10218711103fc8680"),
        (180, 1752617365, "0.001", "2706.14", "0x5f2c45c213c257e96cb5b316e39f4643e720cf8da28dbf10f6f3bea04e34405b"),
        (181, 1752617661, "0.001", "3000", "0xf775a9445a7455f90aa2cded7ac12709351dc8bd0179fb881516ce82f6ad49af"),
        (182, 1752617967, "0.001", "3000", "0x542cbd1bce095bbeb9c13189aa82d66b141637b1ade00c5eb10bc233591cdf00"),
        (183, 1752622333, "0.001", "6000", "0x6b7c5c273f82e3bdc3a1bb136645f8414617522fbc51d2f212a0dc5218b1883f"),
        (184, 1752624241, "0.001", "16", "0x297ae389710d9c59cd520b24b2cf5b91474d8ed8a67d8c80aa2a6679930ab40a"),
        (185, 1752624389, "0.001", "16", "0xd6721ea2b2ab12cf631d784fdf2ba81a1e3f496c3de81f412f0620677611c932"),
    ]

    fileprivate static let retained563327No: [RetainedTrade] = [
        (0, 1752531497, "0.95", "105", "0xfaf83f35bad5bfc8bf874cb3ab14d2fd2414b52c95c0cea8c7cc7247eff14925"),
        (1, 1752531593, "0.95", "70", "0xa4f2fd466617eb7476d2013d8e31dd700144fa5e9e08fcd2320d5e44aa08408f"),
        (2, 1752531595, "0.95", "75.2", "0x38a6ad581d25b23b25b3bb8d8a9a9bd712c0d9892528e217486b91b93d178f37"),
        (3, 1752543219, "0.95", "10", "0x485a9d27aff2e366a3e60282d4ab7da209f3b7bb58d275b1eb8cdf4705f6eb14"),
        (4, 1752543221, "0.95", "13.37", "0x338a80666f360242577e7034f66b212e010cf7a3b1a1ddd586e3eea63accc0c1"),
        (5, 1752545815, "0.95", "10", "0x6a7602f56b655ea9d74c97c89c605b1d5a528dca47ac10ab0dd3b3e512f08c81"),
        (6, 1752545817, "0.95", "11.63", "0x512f8cc26279a3a899f4ba911227068e6afcee038185c21f2c6409cafa6dbc82"),
        (7, 1752545823, "0.95", "44.88", "0x4a8e8b4ac5acf5b31edc1885b299cf7ef872bb59a24f5f0dc1874399d30d032a"),
        (8, 1752545825, "0.95", "11.63", "0xc89db290da6d1974d43c67576592310a1f2b7fff3aefd01e2a6ce69d0f0e87d2"),
        (9, 1752545827, "0.95", "16.67", "0x7411f3b6290169f78253b1735e45afd87a5cd31a9f41b91843191a3b82541d41"),
        (10, 1752548828, "0.95", "370", "0xee8a66fd220b029ea3bdd0f817a92cc850117d948e96040046ce8b5000e89e9a"),
        (11, 1752548830, "0.95", "330", "0xcd9e5d9579ff8910a95057b99136095d0a5a0e04ecd15104ede83fd7be985aa5"),
        (12, 1752548832, "0.95", "20", "0xf7d177b14933b3d80ea3bdecb3f1026f6fb7297aaef4fd94c5adadbb79cfceb5"),
        (13, 1752548834, "0.95", "20", "0x1a262df1934689eff8015c0df48a0e3d06e958b12ae591e3cfbb8ddb18df028e"),
        (14, 1752552353, "0.95", "2220", "0x53ded2a9daac723aaff606a45c69ea587f860f170d2c44bf9d41ba8d32a41337"),
        (15, 1752552355, "0.95", "868.32", "0x74453fcf778d51ab703c51f25df2c6e0ce20ddd2a835b66beea705596b866c0e"),
        (16, 1752552377, "0.95", "21.99", "0x35681c6c7edda2665650bf790eeedbc48a0d33c864c240e352b7a9b0aab820ae"),
        (17, 1752552399, "0.95", "25", "0xe60af40f7e24e2e280abd18472e4f908e9f5d9ddb4b79985c8eea6e703976c7d"),
        (18, 1752552431, "0.95", "9", "0x8e225af71bc620bd9a73d0b2411a7a444756b66ad5b1b1a4e077190e01287876"),
        (19, 1752552435, "0.95", "8", "0xfb1e9325c670d852fcfd22588daa397d2bf93c41864710b7fd5e445f13b73126"),
        (20, 1752552439, "0.95", "632.42", "0xbe042f793ec913c3a82e352e77b71c869fd26539cb9e485814ec1be2c0f2452d"),
        (21, 1752552441, "0.96", "25.51", "0x5cc4026bd67be00ef02824bf9b7e505bc4b396b805d184921337456122781f4d"),
        (22, 1752555149, "0.96", "37", "0x23ad58cb77119c777434e0eaaa6d86c5d5314525a4a1d2f6b6b548047f3fcc97"),
        (23, 1752555149, "0.96", "30", "0xc0552f088eb9d6d6f93642fe3ca091209b2b49a7fa7623ed4b4882189a8b3cd2"),
        (24, 1752559303, "0.9692424242", "66", "0xbf000b75a7e343c54ec399699f4335937f67c9b7a515d04d293ae5eac391a486"),
        (25, 1752559647, "0.97", "100", "0x763dbca8daa7324673bd803e8e7639ae3c30e45ecf167e0fbab7cd25a6da9250"),
        (26, 1752563147, "0.97", "25.25", "0xe840fa1caa32bf155fe46c1bbbba7363b5607f2ab1e423150e08bc8786f7128f"),
        (27, 1752566345, "0.97", "9.21", "0x9200253962578648e86515457009855b0e080db945420d3173b5d1a8c695edfb"),
        (28, 1752566381, "0.95", "39.99", "0xb6c66ac821e28b1ad4375f5cf7d88e707751c8907cdde43f952b138f6488e4cd"),
        (29, 1752566385, "0.95", "66", "0x2a90f1a87328e548fb2c5abdb2c6aba4cdfaa1043b4ed7f4b8ae9014eddbb862"),
        (30, 1752566385, "0.95", "156.25", "0x538e87c0d2db329844ca61752e0593c37ce91cd2c5d62ea64c647c9a668137a6"),
        (31, 1752566387, "0.95", "53.75", "0xd8d256e7688aa00e726b9a3530dec90f7afaf91f91e9c616f1ef94d923aa0063"),
        (32, 1752566393, "0.95", "12.5", "0x4db0448906cba87f6e19a88c53e8d8ee1eef21686e6d063c79b78ef14c423d3b"),
        (33, 1752566564, "0.95", "1.49", "0x393e3bb483e01d5bfbb1e47c8cf344f92d689675bcf14947792fa5a4f2b7a19c"),
        (34, 1752566654, "0.95", "40", "0x58aba21664fd07b65dd5ffcb6140ab1dff72875ab11f0f99db17f4cbad7848e3"),
        (35, 1752566658, "0.95", "6.25", "0xb8534eba4af7b1ebb9e2c3b21561fa816b820f064f4cf8bc09b8605a75e017ea"),
        (36, 1752566658, "0.95", "40", "0xe450952c9181b99a735e2b1c0caebab2e14cdd1139839f3ff87c7c8d1620b0b5"),
        (37, 1752566660, "0.95", "6.25", "0xe55a1a33053eb54301708d9d2f7c5e218a6986914e910c7e6b1eaf0e777810dd"),
        (38, 1752566702, "0.95", "24.99", "0xd4a77ab8924dd69bd3675423d3949185ded8493757a5fb1c298d713fd9f1cd40"),
        (39, 1752566730, "0.95", "18.05", "0xf6e0722021496881816bbb3a616061bed52a808c44752aae8bef165db444780a"),
        (40, 1752566734, "0.95", "6.25", "0x0eeb95386e968c8c7de165454cb9d407bb03104c82f7bb3c030f51823177c6de"),
        (41, 1752566736, "0.95", "25", "0x84ca6182aee508813dafe92ecc8e0a61996d69f83d2210c8ca128fe5203d082c"),
        (42, 1752566814, "0.95", "39.99", "0xc4010917e099387f5ce081e8895db54f6186853b39e984ef9ecbba11774bcc27"),
        (43, 1752566816, "0.95", "102.22", "0xa675d7ca0112166e19a5ff1f8fd1cd933f7fe656fd665b8e6bde52e18f733f16"),
        (44, 1752566818, "0.95", "12.92", "0xe2694e40ef7f82892d8abc415bb3c4f58586bb7852cc7985b87eb0cf8295add7"),
        (45, 1752566820, "0.95", "13.33", "0xd22d4f3ccf50160b04fdfcc837a880deb3945903c6d4b4a27a4e96b050f1cf98"),
        (46, 1752566820, "0.95", "5.01", "0xf62f736bd182ba6dd93ba4c8d0e192cb095ff3dac396bb3ab78ea133f92ebb76"),
        (47, 1752566822, "0.95", "5.56", "0x0fae6aa52ad4adabdf3cbd345cbc4850ed93a8ae41280f353b15ab89731af187"),
        (48, 1752566824, "0.95", "5.56", "0xd748712d6bd7271e04c3755232d16034774e84a7b0847bed77f46f5a0cd8d729"),
        (49, 1752566838, "0.95", "27", "0x72cc6f5b0a2a7db716645e6d4b28d50f4ec890c57689453a3b26ff9cbb445a0d"),
        (50, 1752566848, "0.95", "5.56", "0x2b39aa6eef7b505c720530742561adb1539ede89bca76b2b45aa4c015772f486"),
        (51, 1752566848, "0.95", "27", "0xd32135eb1483c3506373fc0312169e508fbae75525fde5f00ce06ce3e32f4d1b"),
        (52, 1752566860, "0.95", "27", "0x79fd906bf85e815fdc8c4bc4cc96f7e2d07b42ee5c913343b667cd266b77e576"),
        (53, 1752567082, "0.95", "31.25", "0x3ccee44cd8f58e5748f765ff12c41c9d6a5e1052c2da43a9ce8638c4c864a110"),
        (54, 1752567935, "0.95", "70", "0x471cc81675ea962c049926a26ba465cdff65ac65ed627965874cb91006ca78a4"),
        (55, 1752567961, "0.95", "15.28", "0x2258e606a329f96972e0077d71d753fc0f6721c4d5a811218c4f1f89012e4b0a"),
        (56, 1752567961, "0.95", "66", "0x657572ef973ed4dc3a16cb82ff7a058bfb2e5c288564cc1ac323e006702438a6"),
        (57, 1752568196, "0.95", "23.8", "0xbba6389ee3b611a10d91ef7c2f2107d236c1ac7c458ab682b5be9172b467d1a5"),
        (58, 1752568198, "0.95", "13.34", "0x80aa9a14d0a929409471397f5d63a162a8f495dcf66924696ce231fc1a966448"),
        (59, 1752568202, "0.95", "11.12", "0x4b2a4fe78311f885eba85838c8ef770b16d78aadda88a9b82b5fe869c69b9ccc"),
        (60, 1752568512, "0.95", "510", "0x76c3755083b525aa7eb82385f2aa1eeea836c3591e8521eccfc327b833df7e4c"),
        (61, 1752568576, "0.95", "30", "0x996959b2a3de85e0170eb02a6142620cca042459d7bea8917aca52a574b028b4"),
        (62, 1752569695, "0.95", "6.66", "0x81af795f24594b5579f33e6c0205bff89fd1e195b805f191b782ae1368bdc08a"),
        (63, 1752569745, "0.95", "5.22104", "0x5e7f78e906c2df6735f24f42e8ea10f7ca71ceb4951599a5be115300e7dd4e7e"),
        (64, 1752569775, "0.95", "66", "0xd36437b4497b4a2a7a74165d6cdec4f3fec1bba58345ee8b30bc61b09df7e43f"),
        (65, 1752569779, "0.95", "14.29", "0x95b19bd804112b597ab4b11dda93aa37f85bfbdb2261908f4715b1be284862ae"),
        (66, 1752569791, "0.95", "190", "0xac64a481af4247c567f9977e06a1da4216444d791ef2171855490f9411bd3cb9"),
        (67, 1752569813, "0.95", "13.34", "0x0aceef3348ac528aaa577cc8f46fb4850d9cae9ad96b83521e89db613576ec86"),
        (68, 1752569813, "0.95", "5.56", "0xdf151901a57632151fd3503bef089a282ab40b74b273e80d879155a97d43b24b"),
        (69, 1752569817, "0.95", "5.56", "0x1876a2781564f854d8b0540043e6c727287d331e6429017a9a21f4d99fc0ce60"),
        (70, 1752570169, "0.95", "15", "0x07cc5437e57a3fd62beb73e9ff8fc020a026ae7a1990e5418a8b11e09574f756"),
        (71, 1752570169, "0.95", "170", "0x43285d67391d6e587021f48c85b848317ca9f35c439921096f8f05f9addc4996"),
        (72, 1752570169, "0.95", "66", "0x6ae4450e8fc90f8f0532f3fa904d5a9734e59e1168086abb01ed2d6911566fe0"),
        (73, 1752570169, "0.95", "173.19", "0x83a18f6a718a86017e63d1cdbbaa85b899f7471e378d66b167b82a8ad585157f"),
        (74, 1752570169, "0.95", "15", "0x8fe2b1f6843ef4b59da1ea8cf3e5aafb7dfe21a4c7e07a61fe623bb132ae1b6a"),
        (75, 1752570171, "0.95", "5.56", "0x35870b1cfb895de36b5cef8809bd19ac8a8d7f5363f7d97a80a558249031db78"),
        (76, 1752570171, "0.95", "5.56", "0x42a1f74cf0a24a35728b7dae5528501587a29ea85e21fe2c8d5d48f96015f554"),
        (77, 1752570173, "0.95", "16.67", "0xcff76cfc9316749d375710246705a92b5667595e240070e2bc3e3324234b23ae"),
        (78, 1752570173, "0.95", "16.67", "0xf10c96e2b3652f0a123776568cd44d01670fb971a017157954f22a8e7409b963"),
        (79, 1752570175, "0.95", "6.67", "0x5175c0e3c9dfddd4439fd1dfead5e4ea7d6f2ee6416ab96ba8d0b426097baf6b"),
        (80, 1752570175, "0.95", "5.56", "0xb66b735510eb8d290c78ffb4a99a841e7a8e22dd460428b6c04755768a8c42fc"),
        (81, 1752570175, "0.95", "5.55", "0xf6901c5bb6232fc1540072dc1bcd29a7ef15ac8b21e09e5251d0deb18b5c36f1"),
        (82, 1752570177, "0.95", "16.66", "0x54339d66d1f74690d23b7c8ed1fa4d13d6d4f362e05a005ad1f1fdd78041561a"),
        (83, 1752570177, "0.95", "6.67", "0xae01a38d384dd3cf01c68ff88d47d4512e59bfff740b786bbe5d7c8b5b81d470"),
        (84, 1752570177, "0.95", "6.67", "0xeb736b15d2b3283836879d9e7faf37fa455e1cb748fe6dabbd4a8d2d4f2621f5"),
        (85, 1752570179, "0.95", "6.67", "0x4d882220ded82d50cbec9904ac14913a47abbc8e328d1ab26ecbc5ebb7c51571"),
        (86, 1752570179, "0.95", "5.57", "0xcc71c24652c7ed0a0ff0a6b0e9997cc1257ede65ebc4a69f0b233b3171eaeb97"),
        (87, 1752570181, "0.95", "5.55", "0x61ea8f0ef04a958aae22a82143206300792c5e4f79f39361d12281b571b96a18"),
        (88, 1752570181, "0.95", "6.67", "0x7969379e1f30ec747f199001af3ec069a09cdc774580bb89e2354e928e99ecde"),
        (89, 1752570181, "0.95", "6.67", "0x865cb62998846bcb1e23f1b32e091842a97726b1d7f6e794019365997c700c3c"),
        (90, 1752570183, "0.95", "6.66", "0x464288adde51098791942e451bb8fbf4432a0ddf4373f3d18105cadd0698d611"),
        (91, 1752570183, "0.95", "5.57", "0xd70370113e4efef594f219c8e202b6776f1ef50581806ef9e6306c23b421bc67"),
        (92, 1752570205, "0.95", "300", "0x377969af5142e71b5a74ea5ec8128be35905f65b93832f74664ee387aa9c6dd5"),
        (93, 1752570205, "0.95", "15", "0x61daeb9f535e578316f81de9bbfb9b6cebb94802a095b3b8b2d3d4eb760c3765"),
        (94, 1752570205, "0.95", "150", "0x8be0b0bb90d47535b2ad7da3a66084f8a10e1229febd5e4e7c304644b1aaece7"),
        (95, 1752570205, "0.95", "15", "0x97343de5b50601941ec960ce61020762627e0220316f497038f451d52c0f8619"),
        (96, 1752570209, "0.95", "13.34", "0x1689a36f5e5a9a4142d5f4d96727c1d10e4d31134cf7bc86663ae484f515bb1c"),
        (97, 1752570327, "0.95", "66", "0xbe41e45ec3f3c4f88e8ff2f68808c0d85ecfea2800c081fe0f0f7ae499d03f0d"),
        (98, 1752570327, "0.95", "10", "0xfd349d7174bc67f3bb09fba04711bae2d0084f1b48a9c7fec37da2e70dbad846"),
        (99, 1752570571, "0.95", "133.28", "0x18639df6c8a86771ba743e0a437c011b17cfdb0f80274df61b884ce4e74958a0"),
        (100, 1752570571, "0.95", "66", "0xfced546153146d76a73131d2988daca0fa98cbe74eb0335eb0b0a41b481ec0b9"),
        (101, 1752570575, "0.95", "13.34", "0x2ee5bce0c6a2c8724be2f47398d61153449f46dd882b117ad706cd464c5d7ebb"),
        (102, 1752570643, "0.95", "1000", "0x0e955c1242d51782ba2bc83122ad5bf953497819032dc3e933501135edbcdf9a"),
        (103, 1752570643, "0.95", "39.99", "0x822c2e5da137efb610e5c0edb098233468eb8a466fa2bf19c29d6adc599202c7"),
        (104, 1752570647, "0.95", "14.29", "0x59c2a3d34a6309f96522817529cefc7c45d9b70c3ca0c360b2ebb8c6bc7a1173"),
        (105, 1752570647, "0.95", "14.29", "0xf43d748061158b70cdfc723ad5d3cfc960722c8e12eb55cf367b8f6e34b144bb"),
        (106, 1752570649, "0.95", "14.29", "0xe385ac41ff27d53d7cb118fb03394de7b7199d3159d314b583ac731afc453aff"),
        (107, 1752570653, "0.95", "20", "0x1e83bca8c6b4269c2d0f3ade26a204e908a6df93a544e5a3a3fa4b21c9645913"),
        (108, 1752570827, "0.95", "39.99", "0x66f27655e1c096ebe37a15bb894153d5bfca79d22c08e37fe634568cbcea318f"),
        (109, 1752570827, "0.95", "66", "0x713a25f635e966567080fe744475257892d7680a78161a557f3767d0b3c4946c"),
        (110, 1752570829, "0.95", "452.13", "0x87f9cf339cad964d3354af124ece4543b2883a361f6005cbedc49ff753898906"),
        (111, 1752570829, "0.95", "329.94", "0xc7dab158e48d314ad80c72304811b69c8cb3e8b6fa1784b62e15a836cc1d05c8"),
        (112, 1752570831, "0.95", "5.57", "0xdfac12cedb20a767ee45390f4b77097189f0eec894fa536e262a6e21008347f0"),
        (113, 1752570835, "0.95", "37.03", "0x9230b2a71c57480c652be02fb291a3c5bcd327cb87782511d865d21901500b05"),
        (114, 1752570845, "0.95", "4.15", "0x295d3b23ce3fbced77cbba401da2f8d22088d0863a04e765e1a3b9b454ef6e4a"),
        (115, 1752570845, "0.95", "5.55", "0x486ca67381737dfaa552a7afed9312662b266f7ac5a6068d856a24069a1dafdd"),
        (116, 1752570851, "0.95", "1.1", "0x11ee2e99e5cae1cbcb1444504fb43128b05ed4ab1ec42543a6508099bd40fff9"),
        (117, 1752570853, "0.95", "6.69", "0x674bc3e4fc3a47f3ee98c511a90124f331bee8be7739190329db08b9e4248373"),
        (118, 1752570859, "0.95", "95.51", "0x1ec824c0dd740dc1351bbfc0d34c64135d0b8241470ac6db6cc085495e7bd49a"),
        (119, 1752570865, "0.95", "16.67", "0xd048255f34d8962bad8ae368ea314be1e3f8dfeb05377ea633ef32ebec1aadb5"),
        (120, 1752570869, "0.95", "5.56", "0x628f45639dc00b5911adc4b3c915aba1b8793f074af8ab79767f46806364985f"),
        (121, 1752570869, "0.95", "244.7", "0x8ccb99d19380748d0f2ac87852da7df93eaa03b414857099ce42506b808b954d"),
        (122, 1752570871, "0.95", "5.56", "0xc8435552c57232d9878d6d50b7d9a88bceb448cd5f9aad56dd43717c8d14c942"),
        (123, 1752570871, "0.95", "5.56", "0xd10a60b1f51e0d1b596ed612323a597c77750b59e8d9192dd7fbd78e745e2ca0"),
        (124, 1752570885, "0.95", "16.67", "0x3c275975f3c45c211f25efb6b275ce520a97191e29ad6e3619be79003aafe20d"),
        (125, 1752570885, "0.95", "27.46", "0x3eef61024abb7802e64b4323ffb9112a0cad6b90c8ab10fc7681b6678127d373"),
        (126, 1752570885, "0.95", "16.67", "0x7c9512fcfb0c7e16a9d0a13458cdb377710d29e65ee5fd540fd59543ff2a9701"),
        (127, 1752570885, "0.95", "5.56", "0x8725b186d9d370a07a964ae7167059b21c2f40b6cd913787da65b11ef77b4840"),
        (128, 1752570885, "0.95", "5.56", "0xe9511cab3f1bb874057e31395fa0786813165cde98e239218560772c354df7df"),
        (129, 1752570889, "0.95", "28.44", "0x1e72efbbdb4d5fd2051b86ea07f62958ec667c57c749dc857d5992cc1156e4a6"),
        (130, 1752570891, "0.95", "39.99", "0x7290ea5461291706cd4081d32e7fcfecf44347f7bc481e82cf0e4aa9da128922"),
        (131, 1752570891, "0.95", "3.19", "0xd33e87469d3c6a97eb987ff622b03869499a113366d9fd3530ab890f781ce141"),
        (132, 1752570893, "0.95", "5.56", "0x42238998be3a6fccffd8589b4707b1b76504ac13067f0fdd698533c0b0694a77"),
        (133, 1752570893, "0.95", "5.56", "0x52d0da45070abad3244502b5696daeebbe23da2ee64aef53b0460fb2834a6262"),
        (134, 1752570893, "0.95", "5.56", "0xb848302ff288beed1a2627fc4a8b47a6e0bfbb97419ee7b2c5dc1f1e7e64790e"),
        (135, 1752570895, "0.95", "15.98", "0x1f8c1f7ab6c26a064adc442d04c2d054f8c1ce3b64d27990cda7d98095dd683a"),
        (136, 1752570895, "0.95", "5.56", "0xc3c64b1878864411487e2b4e30cbc922676d3ab49840cf7b979eb8265a9fae31"),
        (137, 1752570897, "0.95", "5.56", "0x73c5d2ad0749537a00aaa4e5b87efb17bf78713d155819e3289cb832c52e653b"),
        (138, 1752570901, "0.95", "62.48", "0x69b875b7ad8decd16117aa5595ea82b39a83045c84e495567dea9a4b7b7aaf8b"),
        (139, 1752570909, "0.95", "242.29", "0xc294b7477cc5303a2d82f4867ceef94b78b3b0906664c4504290804ac6fc931f"),
        (140, 1752570915, "0.95", "60.34", "0x9282e1a9125efa33b9ec1374a8d7246da70e372584ec4ddaa5c203a76e909f3c"),
        (141, 1752570923, "0.95", "6.77", "0xb12d36d65dda4308e5afe8b508b98db0fee47f0b025d3b3529624fe93ef7217f"),
        (142, 1752570933, "0.95", "271.67", "0x5351f0c8efc5e49ca9831fcaca60e2597dc24a9ec9aef4e1da0cac696acfc6ae"),
        (143, 1752570941, "0.95", "84.12", "0x8c51911120cfbe5f7874a81a3ac8bd4504239b8142d960489ba07fb6c4efba55"),
        (144, 1752570949, "0.95", "15.46", "0x6eb676fd29c6b93b19cb6c0f55c9d89c4c1431d09a38b9dd5ff0b1c4f759c5c6"),
        (145, 1752570953, "0.95", "39.99", "0x3c0418104ba151a7a13f18bb0f633823cf523a926172146642ce8b2b97e2eab0"),
        (146, 1752570955, "0.95", "1.74", "0x585d347ef0da66e0abc41b7b110e2efa34fb40f9d394549995968f81eafeb784"),
        (147, 1752570963, "0.95", "242.52", "0x7344e3b644f7a7ac6446b8ddfb49846081b8af7bf844b8049b1b02bd3466312f"),
        (148, 1752570973, "0.95", "5", "0x44e00ebc5d7297c1bbcb782d66ead6b86931235a40325ad2552fa4641491dc2f"),
        (149, 1752570977, "0.95", "6.66", "0xd15fc6d063cf9658e4f180bfdf28da525b64d1d30148d9e5199715343f554e35"),
        (150, 1752570983, "0.95", "110.73", "0xbe03495fb9df3eb6e4974a2a85d6e7cbaeacc0ebf07c45ed0c87ec00a400e206"),
        (151, 1752570985, "0.95", "10.02", "0x8e573e2bf4191af2b43ebd4b8abeb136654d16fb3115f9e36c18c17f3927ede0"),
        (152, 1752570987, "0.95", "112.27", "0x1e2becc4bd923c8e36ef6fdca6dea437bb35122add4da8028debfa38508e13b4"),
        (153, 1752570997, "0.95", "661", "0x7b3049e57e68bbc10fe8c6dbaa9251ef064e9c6c0885e97c78052afd56b44d7b"),
        (154, 1752570997, "0.95", "14.41", "0x948fce68a2c5dbf15fd4c30f82b0c11742eeb64a52408dbd8ae54f1fc6a3b6af"),
        (155, 1752570999, "0.95", "190", "0xbd7fb12fa8049274c99cd48be62e39db5c502ecb5d40f2dc228bf6993167abe3"),
        (156, 1752571017, "0.95", "15.55", "0xcbbdc56c8423981f1c674c0da40b40c0a4e7b9438db9b61f2fad1be6987fb752"),
        (157, 1752571159, "0.95", "66", "0x6669136721d471fce0e347f0ae429a49b4dceccf42765f435f39d952c0c70de8"),
        (158, 1752571159, "0.95", "250", "0x8984ab00f9e11331c7ad58e4274a2774ff7cc42428e76f93ea2039ab8e5d412c"),
        (159, 1752571159, "0.95", "253.36", "0xe88d970bb7ce411cd892a89cf57bad9bb0e9984437be988e85dad2a1a18d708b"),
        (160, 1752571297, "0.95", "40", "0x5e4e4201f88a6d532591c2339c0d6a1e9557b407373e2242050f2cd4f5d737ad"),
        (161, 1752571305, "0.95", "5.56", "0x5ddc9691b4d3a01d65fb5fc7c6d997cb98102e4d0205621e20c953b229fb4b77"),
        (162, 1752571305, "0.95", "5.56", "0xd00d1f7a44b0636cf57bd4e5778f1206b066e89d56ce317ff1e02a5d86320ea4"),
        (163, 1752571437, "0.95", "13.34", "0x23aa518a698bb0e9052eb9df2a68e73fc0b4429074c6c4c66750f1ba77bcbd59"),
        (164, 1752571443, "0.95", "5.56", "0xaeba9c9e9f8e7817796e549def74f23c0da9ea60deafc08be1d1b64613172ad6"),
        (165, 1752578841, "0.95", "50", "0x0543d97a0663f0aa0b1307afc358b0457207ded018f6172659d8d7d88af77a6b"),
        (166, 1752579313, "0.95", "17.99", "0xf7f2dffe7893e771e9f62cdd2613e966b26933c3c3c0dc3fbdecc651437b3f08"),
        (167, 1752582529, "0.96", "20", "0xd29df474a7a481efcc5f61daea899bb9d8f3a35a18e378aa1d945eed8f9eb530"),
        (168, 1752585603, "0.96", "5.2", "0x275d0e571b33fbd2c06ad0ad9a247a941bb4277fe8ed8eea5f5ce9913a19f51b"),
        (169, 1752588131, "0.95", "821.01", "0x07f1d11d373998b7412e3fa42ff24053d63b92856f620c037be55e87e596da66"),
        (170, 1752591253, "0.95", "20", "0x0b49e640dabb6c06937b0ffd21af33e4e411ddee1b33656ba4ad4bf034158297"),
        (171, 1752591253, "0.95", "66", "0x6a4cbd3b6bda2b7a0c6873b7bf168d5395b5e6c732a9533d2385f3c744b67606"),
        (172, 1752591263, "0.95", "26.08", "0xb5467bcdd66657b968398bca301628d3112716a801776408d36dee6be12e3539"),
        (173, 1752592047, "0.95", "477.83", "0x6b5e11da075a233a3fbb4b679e1943c30dcbb2c99156af9ea9aa08112faee322"),
        (174, 1752598682, "0.96", "15", "0x608b753e60042fc526ab221f151a555a017a7f7f5bc41f4bbc0b1cec8098e121"),
        (175, 1752598682, "0.96", "200", "0xfbc886c4f2b2e9d532f78be3e0518b9212a2d54cf985f2762e922468b0022177"),
        (176, 1752598684, "0.96", "15", "0xe693297faa84f7867770b62f7c53d7ce3d1400eb41f006278bb517d902eb8d0e"),
        (177, 1752598740, "0.96", "125", "0x6bf51ef2d4a7757e6955dc89b2f39318799ed830a5df9ff0492de8a86a0f6705"),
        (178, 1752598898, "0.96", "38.5", "0x0ddd61da0731d9256467d8d78bb0705fe9faaf323dcd2cd8e07db5bd280fec4b"),
        (179, 1752598898, "0.96", "5.56", "0x1391003a168a46ea98c57caa936322893dea8c9708c5356193e0b4122ecd72b0"),
        (180, 1752598910, "0.96", "119.44", "0xd83c9c97b85036b79de41a46ec93a7632082cdc3bdb025f9ab774e82d9f7b443"),
        (181, 1752599263, "0.96", "7.739575", "0x526e2bf52608b43639c9b8e03852c1eeab22662f8f34bb67f8a75f9fb6197249"),
        (182, 1752599263, "0.96", "29.99", "0x7114358ebd900b70553b7509175427fc3d37556e43c74f2c1d58ed776aad4939"),
        (183, 1752600801, "0.96", "20", "0x47de36374d4e643046b5010c5b8e0340d058c45009ca51a3c32721de0cd838b5"),
        (184, 1752601815, "0.96", "10", "0x3f6e65ce7ddcd56f17e76eed32f69e6a660534da924cd59c9e8efb6ef080f66a"),
        (185, 1752603431, "0.95", "80", "0x31a4bb4951e407843f936e2ade65a7dbe31e3dd9df1204e06d402f9120178c0e"),
        (186, 1752603501, "0.95", "597", "0x1236488aab97fd7cb46380821d3bc72b570cecbb7de4645407b499bda85f65e5"),
        (187, 1752603537, "0.95", "30", "0x29d01e43f680a24986e74ef5b5856a7304ebe04a8de900751fff463b8e30c07a"),
        (188, 1752603543, "0.95", "20", "0x632dec91d0af90f32ede022438a247ee5bedc2867ccab3c01887395a1f5afdcf"),
        (189, 1752603545, "0.95", "33", "0x3ea77da7d72c6236da73be0f461127ff32e4372c9441ff4a062da86be7acb2cf"),
        (190, 1752605436, "0.95", "111.05", "0x7e3a6e879e00412cfbbd65fa7e7344b8420496cfd61bfbd3f54e71a44c8d1baa"),
        (191, 1752605694, "0.95", "40", "0x2a9e62e3b828f3ef8e3eaa38e70754d78fa90a4be47cc11bd264e76748379756"),
        (192, 1752605702, "0.95", "2.06", "0xa639db275dc568d9807bc3ad5556dc70c40e6c5b9f2902c33ffceaf28eea23b0"),
        (193, 1752605920, "0.95", "270", "0x3242ba17e1028fea35256f72fc11fcbc26fb2e0c86b88a78436dd03ce89cf197"),
        (194, 1752605926, "0.95", "2.06", "0xa0b2ad4d81333ee0a0ae6a3179b454951588da3abdd471025eeb9f1c83f4ffb1"),
        (195, 1752606524, "0.95", "40", "0x6ca626111162b69d2ab3724ca5909bb0940dc5be92581fff142581019121b0d5"),
        (196, 1752606530, "0.95", "2.06", "0x2f16fbfe6a91f47318354266536c9442e6b6583cc04440f809301d9dcff739ef"),
        (197, 1752606972, "0.95", "51", "0x16fe1d68373025a9ababc9477cee472ae3500e89919e140851cd5c54b3d38a9d"),
        (198, 1752606990, "0.95", "2.06", "0x26e86007577ef32f194a2a3672c58cd91d2f486ce75347a91ade9e86e4a3dd4f"),
        (199, 1752607258, "0.95", "200", "0x8c09becf36b5252eff580bf9fd5f2f0a442d819ec45f177d295607141a2b24ff"),
        (200, 1752607258, "0.95", "200", "0xb2635051d1c755e405b3079e5f8d4b0fabb976fa691b2010611e7ad95b819011"),
        (201, 1752607258, "0.95", "40", "0xb6516fcf9c26b6c436bff5a80ec7bbbca530f674fb9eb0af4728741a8511900f"),
        (202, 1752607268, "0.95", "2.06", "0x2a7f5f9fc7cbb153f035466058bad2a5f97649f56b3ee9ac8de6ba6420e7e334"),
        (203, 1752607268, "0.95", "2.06", "0x87be2102d0285703fbc93fdbfded37a31c1a2629706885210756977c0e64432c"),
        (204, 1752607268, "0.95", "2.06", "0xb404887201bfdff76ffbd62429743faa4035689ac4844d609202b859f358ce46"),
        (205, 1752607268, "0.95", "2.06", "0xc04e7c44f2391732253ee4ac450da7a1b4a23f096c3378dbf1e85517b3fa49a9"),
        (206, 1752607338, "0.95", "490", "0x5475095272877f74e4e7b708ee0b2e7d86691f1d0ed8acad00cd344fec2ffafd"),
        (207, 1752607338, "0.95", "40", "0xf178d6ef3b148056b59fd1b8cdbc03212df769662e6608179a92af994a0acb3c"),
        (208, 1752607346, "0.95", "2.06", "0x8143a954dae8114dec4b2dea91ac08d1cdd892a11e01c24011fcba504a4bf8ae"),
        (209, 1752607346, "0.95", "2.06", "0xfafe860a7b3724ccd5a3d0046398ca52698137956eb79d93863421a3790bf6ca"),
        (210, 1752607394, "0.95", "250", "0x5935ccf1741b54f94c08f503003726789db3fd1df3b7aceef14c5c61badee5a7"),
        (211, 1752607404, "0.95", "2.06", "0xb7dca35a7e4bea286233db70e9a348980e7884db38a6c8cf9eae4129d23289b2"),
        (212, 1752607428, "0.95", "1600", "0xbe6028671497419b34626481baffb4128056261cdf06f04c6925a2422b1a640d"),
        (213, 1752607430, "0.95", "40", "0xc74e366b5da014a650d2ca0a2240f6a9dd75756c30bd90dd518c359e4e5e3c35"),
        (214, 1752607434, "0.95", "2.06", "0x25d90b24d05e837016f8d18b0b061a6c23d3d9394618126c3562f94cdb7e25c3"),
        (215, 1752607436, "0.95", "2.06", "0x5f88ef59cb9b5d5832ccc8155b696ec87b3da783900038d75b41cb39422a05c6"),
        (216, 1752607444, "0.95", "13.56842", "0x6c323e0cef9e9e0a56397e0dfd2c335ce8ae3ed8f6d45c7d10ad1b4c751fcc00"),
        (217, 1752607556, "0.95", "160", "0x372b6c4df60e5a45786a3f2bac8438550f42a04753b14bd7ddf992de5addc592"),
        (218, 1752607556, "0.95", "39.99", "0x99ee8c75bfac88f0b3b7f834bb4982b2d466a1c51d4a956c650c8ec81aa5c486"),
        (219, 1752607556, "0.95", "167.24", "0xa2f5e4eb6d2501cd0824773b660b7e1d1337628923a1c208283a0ec31c6ad816"),
        (220, 1752607564, "0.95", "2.06", "0x7b331ea611dbbe030759937f8934e224ffb9960c436708d054f4288eee403d29"),
        (221, 1752607566, "0.95", "24", "0x7b55fd5979bb8b6a4a1747b83cdfe76ee891dba7f0cbb1ed2e968bba7728ce6e"),
        (222, 1752607570, "0.95", "40", "0x4326cdcfac8c4597ce55572abf3fdc184eb6e075b595dc13d610e563bac65743"),
        (223, 1752607578, "0.95", "16", "0x1abb426e00766bd17ac7ff5a6d0c35a3f997c7983778770cc57f4da4039448cf"),
        (224, 1752607592, "0.95", "8.93", "0x1e9df9c6f56d198898c4b47b2ab73f6f7a93162e29835b12b7edb16b7a2658f9"),
        (225, 1752607602, "0.95", "31.07", "0x3044ce30e27042d24717b721cbb02bee7afc5c7beea7d0c7b25db586c3c1ae2d"),
        (226, 1752607634, "0.95", "10", "0x07b06ad31219c342e98fe0c22dd235ccbd532f782bfc8f5480635ee336a83805"),
        (227, 1752607638, "0.95", "14.29", "0x2acc250e9d6272e44f0a44920f4bb7b17be93584a2a85d7156dedf5092edf8f1"),
        (228, 1752607800, "0.95", "0.31", "0x0e138ce3719df1fc7669834af0f92a03aafafba326232ef614bce4818dfd692d"),
        (229, 1752607800, "0.95", "820", "0x60a997bd019108507668ca490d97bdca37c235c7c7f9aac8a345b344c393216e"),
        (230, 1752608596, "0.95", "209.97", "0x4f975c196ecdaabd806d2e51a4767f62e0c3b68762d3ad18fe86f1055a3fe37b"),
        (231, 1752608596, "0.95", "200", "0xa15a3a0cf5c48ae2607b0ad5b960895971c6397b8e0a2e79ce50b56f3995aba6"),
        (232, 1752608598, "0.95", "40", "0x7c25509a091525f14dc35b43f3053c8c564e8a88edf83e1270ac7a37dd414723"),
        (233, 1752608600, "0.95", "16.67", "0x4794a3db0ecf0a0451ebb4c484ed5d22a6cc5e83329db65ae3b46e6e3fc79fa4"),
        (234, 1752608602, "0.95", "16.67", "0x4ec0ce999655a483a1549a55fa181c32de052a16c42bcb6fe27aafa2567908ab"),
        (235, 1752608602, "0.95", "16.67", "0xd09fe2fc607bc85015f91a001cd9aa9f6ab9711371f7de49149a6e05f7ad855e"),
        (236, 1752608602, "0.95", "16.66", "0xda34453406a2d8d5100c536a29e8daf75de021d92975988647c243060d74eaf1"),
        (237, 1752608628, "0.95", "813.68", "0x950742bcf4182e1fdf9cf1ada6704c1dd63e9999e3e82c4b03b0696c7aecf53b"),
        (238, 1752608674, "0.96", "5.333325", "0x82d95fa3a34529407c2b981f7abe9e460791740410ea5d8cecb56cf5b0e11eb0"),
        (239, 1752609072, "0.96", "599.91", "0xf912c95f293ed659ec3b783a50005c6d795114fc2b0b8c0b5e09a7bc6be2ef5d"),
        (240, 1752609238, "0.96", "10", "0x3111093839897b44b7b02640511c8ab373a4df0230ad07b12fee25ff467ad512"),
        (241, 1752609242, "0.96", "13.86", "0x375bbd7899b6cfe3c967e356a967703760c86421a8a8511b699431dc2c0360d8"),
        (242, 1752610080, "0.97", "5", "0xa34438bfd8c504e91af4ed6cc571e97c1d528ec6bd4b4aaf61b00ef5f94d4fb3"),
        (243, 1752610776, "0.97", "5", "0x186f8bc7df0f9a235b1db895f25f40c908d452db14ff2bc522f1d0084e8dd140"),
        (244, 1752610776, "0.97", "50", "0x37c99684798bd589c4d2985444f651b6d9ddba7f83c8c55a13c7fa0521d4e2fd"),
        (245, 1752610776, "0.97", "346.67", "0xe98d210b105896471493af73459a8dc5668286d10b816bbb4fb3f387bc0d53b5"),
        (246, 1752610958, "0.98", "20", "0xe6ae6d5df059438f93602052e384638fd96f2fc3abb1c0fa7bea348e25f73e57"),
        (247, 1752612399, "0.96", "100", "0x21bfed328a7d554ef6ed83554ad620e99042e73eda3afe76c53ef3934139ae2a"),
        (248, 1752612411, "0.969", "14.95", "0xedc40b25354367008484752795583abc96a991433a2e752845e4689aa8982e7a"),
        (249, 1752613933, "0.98", "5.33", "0x36024958b3ecc2e05a9d0561e9cbc6b3531711ec067661fb2d3ee1431f76e8a6"),
        (250, 1752613959, "0.999", "20", "0xba4e79ca63aaf212565d0cbb803cc40095edb498049a24e67b3898fdee2db656"),
        (251, 1752614157, "0.97", "25", "0x2a6d61f4e66af0ac09b85d495d07f4868f248a682d1bacd3ac1c0e6122a0049a"),
        (252, 1752614159, "0.97", "33", "0xcf1ab7cb139c3b60a3c5dbd1491e662eb7c0913422a93d834e98708949e88512"),
        (253, 1752614923, "0.965", "17", "0x3c881ee340af95f503ee1a7a336afce32bf7f3fd57ec51dd917107fdcba87023"),
        (254, 1752614923, "0.965", "10", "0xbdba0bff7e66ae8b070d97cb697345942e2d08ede0f2021aa143cf10d324a746"),
        (255, 1752614925, "0.965", "5", "0x2599a60681b05b4f2d5ba4f348925fe4e16ab3c3a39cf8ae157e89a062934f76"),
        (256, 1752615137, "0.9694606497", "5972", "0xd3924b2e060fc34caa2781cc7389fea158b5fafe6026d2dfb755ea98daef4e2f"),
        (257, 1752615201, "0.99", "29.99", "0xd134b629f871a322a0c2bb9f4b2a0c853f554dfff991c8572f915cf968d4143b"),
        (258, 1752615207, "0.989", "20", "0x8bc6f65aee2c2a4732189743ef98ae5d32beea62456cdb6fd2cfc6e016fab301"),
        (259, 1752616233, "0.9880869102", "65.7", "0x4ebd94171d340ecbc0bc807494ff31434a8cb32ccf38a4aff3977a50855e13b3"),
        (260, 1752616261, "0.997", "202", "0x4153b4a2fcbfeefd1f59a98e04f22da4ffbb684efbd85409589d30ad243b504a"),
        (261, 1752617199, "0.9985002", "50", "0x838ad6122a2f283010ebe43d2a790547b192bdb90700955dba7b1e3c94bb4fa1"),
        (262, 1752617377, "0.999", "60", "0xe3413cf72f88d7b2a26e7907f18831feff8c1bdb44b1ca6037fe3ccd7a809f05"),
        (263, 1752617383, "0.999", "238.86", "0x9f208423ba9eab8a287d45d34063b78c73733343550089d34c2d044e610e05ff"),
    ]

    fileprivate static let retained563328Yes: [RetainedTrade] = [
        (0, 1752510082, "0.0320051307", "123.105262", "0xc56d05799410e351cb554e6b3d9594f07d18aee6e5f4a5441cf93fcb15ac06b8"),
        (1, 1752512680, "0.0369999921", "118.648647", "0xeb8d6b93e84dbec75e23a7fe1717b6e76c9a75d1852978ecb9767a8bcb3152ea"),
        (2, 1752514728, "0.0369999986", "675.675674", "0x07c66374fd78d386eb4a6c6ba28e69b15b0b9c4746ac247a9944a70655839937"),
        (3, 1752514746, "0.0370000001", "675.135134", "0x8fce414c87d6c824c5fa3a76a82c697ce68cbd25b394e6926289323cf7842072"),
        (4, 1752516038, "0.037", "30", "0x936dab5ec28edffb08badc7bb7c8194f7e967d25d71996566da5fa8b6f7d901b"),
        (5, 1752520513, "0.032", "8", "0xaf7b846b8ba070bfd626edaa6c2058f5ebbb0d0c346444a6eefb50fd5b0051ec"),
        (6, 1752529021, "0.0359999969", "305.555554", "0x655660ee09b13987a9666929345d01e5f44250e0c39130a38d7e2d17d9d6ea3c"),
        (7, 1752545181, "0.036", "30", "0xafac4ab332fa65aab273977fdc28b4161d208fcf8dc7ed684ae7e42354358154"),
        (8, 1752545815, "0.03", "11.63", "0x845dda2282e506de0edbc941689e8a35fb734de9137acd6e7b98a790397685f6"),
        (9, 1752545823, "0.03", "23.25", "0x43300c7789ef2aa4e74dcf12ede5404dc82ed6035a24f053d9e4dad9822a00de"),
        (10, 1752545823, "0.036", "44.88", "0x43852cf7d12f204e6f213e5a2c042ceafd001bc7a2f34af4ce40e2009971378b"),
        (11, 1752545827, "0.035", "16.67", "0x2e26f8eb752f30e4e5690a784f6fd290c4ff305ce0b0f76a9dc4f805485c3524"),
        (12, 1752548832, "0.031", "20", "0x11e265aa3e5aa6c4201938c6d765ba9846bfa16a664a597c447949dd1d013190"),
        (13, 1752548832, "0.031", "20", "0x95029d4d8c286bb8c9160e34db11d47a6cc0f36e8a3bcb237313004ba73c679a"),
        (14, 1752552355, "0.036", "16.67", "0x53a015edaf105226f48b84c8201784b0a6edc0e3d39ab7cdc178e514909e8053"),
        (15, 1752552355, "0.036", "16.67", "0x99a40b67191fec5969f228e4f35fb013cdcfbcd53f35b8f0e5cabb23da9804b8"),
        (16, 1752552377, "0.03", "5", "0x88f6d3b32b75a2c82c6b293d8816986d75035b1582d40095d3a89196ae1c5851"),
        (17, 1752552389, "0.03", "3.01", "0xebec3d3e4483caf0888d1e65a330868e53389ab004a2f8850f5f09de7f12914a"),
        (18, 1752552401, "0.03", "3.99", "0xee75040c8d3783ac11bca0c2ca7976d5d1d39330c271ffdb3b5801b9fb6b6d04"),
        (19, 1752552403, "0.03", "21.01", "0x7969cdabf970727a134d9cf8b452214fd6a58e9bfb0aac8a7afd41a6b87f51a9"),
        (20, 1752552407, "0.03", "5.99", "0xfc2e0af79d98e33bc124e4bf8ead9fa80447b208ba9de3d20263fd91dbfaec6b"),
        (21, 1752552411, "0.03", "27", "0x03c5a0782d9a11ca86a8b6cf858b684c52b33a703f440a53676c3ca52e0060cd"),
        (22, 1752552415, "0.03", "11.01", "0x41bb71d36165a53d6b95589a4a21c03ac725f925a5b88e66caf4dd1faef142c2"),
        (23, 1752553085, "0.03", "5", "0x4af25d8a8395b668b614dbfecf9e48d02075fc780b35349b219514a1cdbd462f"),
        (24, 1752556457, "0.0359999663", "27.777776", "0x00b9c7cfe27bf228f8177d6705ba83c4cc0f6e76ecb1be96e193e476176cd883"),
        (25, 1752559307, "0.036", "16.67", "0x5707eda4458438da5bedcaeb2776c49f022ade56b29b444d94de8d3c49d384ec"),
        (26, 1752559649, "0.036", "16.67", "0xe5741f8afc7eae8b17538978bb30ea6aff5064f3dc74ff7f01b2be17e9f01042"),
        (27, 1752566327, "0.0369881917", "2125.63", "0x32ac8e9c790b32da69e435a5bc5386eb92eb872d2fb1407fc7d33a5df9900b5e"),
        (28, 1752566331, "0.05", "21211", "0x15dd3bb537af59c80bd06d39bfa6c68d20b6850d965a72705c8a85bdd17ff55d"),
        (29, 1752566331, "0.04", "16.67", "0xd9f00677a19f268f57eb99838d164a2f5586b1e7ec691a28990fc24918726d1b"),
        (30, 1752566333, "0.052", "14.29", "0x092d05a0c59f4f576a1e848f2ae683dcd9903bd203a19b442fb9c2b857edfd5c"),
        (31, 1752566345, "0.050187232", "49.215685", "0x492902b230b262c52409408bbc2f4a4bc86cefccb7cfa8ad1b068b22f6eee0a7"),
        (32, 1752566381, "0.036", "103.83", "0xead80c96ecf926de22773e57907be67a217a9890f8154a9979fc887ac7faa53b"),
        (33, 1752566604, "0.036", "69.99", "0x963d2985bd2466380eb9710fbbec41736dab4be605226c13bdd882df8735c994"),
        (34, 1752566702, "0.036", "25", "0xb186dd3ad21c6fbf3f4a2f01b6da8b7e8fd83ef4322bea8f424649e1b05f38b3"),
        (35, 1752566704, "0.044", "199.94", "0x10cb4efbdd40d1797fd5f0825ca81e3808a6a98d92971c8d132dd6e00475b7e1"),
        (36, 1752566706, "0.049", "14.29", "0xd71a032e3ca33affe4f05acea5abe6f3eaf948230f9315021fd0d743f7c1e813"),
        (37, 1752566750, "0.041", "22", "0x6d6b0e1048a5a9b6d1dd5544e198a3ccde26de98fd37c5674e79ab6213a00967"),
        (38, 1752566764, "0.041", "11.66", "0xa0c2a853c7caf57520ace79bf3fe4d636720521cb23c02cd9cee104c8d89aa95"),
        (39, 1752566814, "0.041", "206.62", "0x564d2435663a208d06ea9fc2ea5c6157a35f8f7c2f732be78df9e38452030efe"),
        (40, 1752566920, "0.0497159091", "140.8", "0x7deead56f492f856992320608e9406a3dbdb5d6ed3b2693a471f39440b20e2dc"),
        (41, 1752567965, "0.0416670666", "16.67", "0xb5d950c1f03293140c4418016404d728431e1ea89e9faca61e146b681ea348e2"),
        (42, 1752568510, "0.041", "510", "0x7824609eea339a9b24cc764faa33581b6263b25f24e64b4d07fbc8510a831419"),
        (43, 1752568514, "0.0493974808", "14.29", "0x83742d4334acb7f4f617043a08dc744240abe978aceac632969517015cef7c19"),
        (44, 1752568522, "0.041", "1.91", "0x6d47c32e2ebcdcdedaf006bcb5653e5abad6ab4de4d18a36fd9da318f271f9e3"),
        (45, 1752568524, "0.048", "14.29", "0x97d500a6430e241c78151a761744ba50399177d88b4a7649b5868ce392542501"),
        (46, 1752568714, "0.041", "5", "0x800042fcd3ce6bb8234c024709588a8318b954ac3c3d50ce0bd52bb0bcf6c47b"),
        (47, 1752569779, "0.046", "14.29", "0x2a892a4b2384b8d5fe3adf7c53bd670421d14399307fca3b0a59fbb55fe94edd"),
        (48, 1752569795, "0.048", "14.29", "0x9ebe2a88f71d85a8f8b4ecb52e14d5036c70a11ffa1474e0724baa60b3ace0f0"),
        (49, 1752569809, "0.041", "10", "0x5406f4403b6d9c6baa1088e40ebfbbd9e0c0290f6f6e6931ba5497117e10ec68"),
        (50, 1752569813, "0.048", "14.29", "0x9819d6cc37d4425425d7c84a1acb003cf0ef57a63317301ce1513099e09eabd7"),
        (51, 1752570171, "0.041", "16.67", "0x6854afdeb7de80dd4d2ccf913e9a034c4f55d223cb4435def7973b22f422ecd2"),
        (52, 1752570173, "0.041", "16.67", "0x5e844972e4857668a8504c892da504347b9fc9a2dbd951ccb59d4011c20b5bf2"),
        (53, 1752570173, "0.041", "16.67", "0x7d01c516b64cf106f49d9ba5d1e4239b19234f7a936a0eb53db460035294c81f"),
        (54, 1752570207, "0.05", "14.29", "0x7560c2568061f63fe2706729d9fb5cca0c930ebe50d847bfe46e3d3b0f8c232a"),
        (55, 1752570209, "0.05", "14.29", "0xf607c8c99ed4eb69d2567f75f51fac4ecfc2b02a27ae3a726f928903161e4b98"),
        (56, 1752570277, "0.04", "4303.71", "0x775d5778364718b62f04c1404b0ca7ccd8ed25e51feb955b8d1276d39ff619ff"),
        (57, 1752570279, "0.05", "14.29", "0x7c1bb3e1ed1b8d4b6f4f06ec542a9e50fb9327ec6755f2013971801bfbf60cbc"),
        (58, 1752570327, "0.0558046437", "3494.332856", "0xf672519c3d9233bfed032afff77659879878cce86a71f5f86c777e8c66ce878c"),
        (59, 1752570571, "0.041", "195", "0x9d2a2e4939625366c8bae868e0f8b85b66b2a8abb062be83bd257b5b4692574e"),
        (60, 1752570643, "0.04", "223.09", "0xbea39710f9d62cf015b6bec645030000ed9a345e48a64f1a6d301c2b26d13e16"),
        (61, 1752570647, "0.045", "14.29", "0xb8c26a0e721ff54664b4f6b507e3490fa160853c45743af38285345627329268"),
        (62, 1752570647, "0.045", "14.29", "0xbcd24c4a410fa0423ad2ba8b8f9a2e99b377159c90e981277d95805f4475ac5a"),
        (63, 1752570647, "0.045", "14.29", "0xde29dfa412b8ec0902276b7062c3213cc672683c0da79cc31f7657083100bbf4"),
        (64, 1752570829, "0.04", "240", "0x1bfcb6d2db32c32b8cfd5ce59328af8550d78e0816ce46fb0b3d575fc33bec3e"),
        (65, 1752570831, "0.046", "14.29", "0x4af82faef929a780af37817529a6ebf6c0bd37e8b8dea8a33ef8e366a40c2abd"),
        (66, 1752570831, "0.046", "14.29", "0x5a8b99bdf61c79548db3b75ba2cb7e693e68d98056e6f7e414036ad779c4efdd"),
        (67, 1752570831, "0.046", "14.29", "0x9c33e9c5488479623ad6b2c78038b641fef2a3e1178850d79c2dccf301deaf29"),
        (68, 1752570831, "0.046", "14.29", "0xb3711073cc1a51e76920d16f4c8bc256cf483ca7bdbc5cd37f0205f6491196c5"),
        (69, 1752570831, "0.046", "14.29", "0xe551b5f7d5ebe37e2832e51a32b4b69f28ea7c57735037a16eca51a20fb99f55"),
        (70, 1752570841, "0.045", "14.29", "0x2a7e631d479ccdc69db8ffd5af7b4a87488f50dd572903c07522e86ccf8f2f8f"),
        (71, 1752570865, "0.044", "16.67", "0xb1304e6d0526eb46d4d3713215bd92108bda5c743b831488a5de8db6ee385eb6"),
        (72, 1752570865, "0.041", "5.28", "0xdafc91386d15f0a291155110c06630f9e152eea331b17ac4b979adfe803ec57f"),
        (73, 1752570867, "0.041", "195", "0xb875b8e59fe42136bc2b87810da7f23c5f3e158af42bdfc62334efa562431a68"),
        (74, 1752570869, "0.04", "39.72", "0x4271a56bab5bdf5b757058a2e3edd820129553b47033fa2535a1390ce16456fe"),
        (75, 1752570877, "0.044", "16.67", "0x7f15011c1e15f01b6028c903a2a6053434ac35af252a7db90d1694bffe8f4c65"),
        (76, 1752570881, "0.044", "16.67", "0x63f3b2a1f50b772e418bfde789d61a14ec856ff5a9365701f48408bb95bf8e0b"),
        (77, 1752570893, "0.046", "14.29", "0x6951ae1e0c8cb478e43c7659d361b42a8c90d17b7b44abec6f103ba3e3d35c6d"),
        (78, 1752570893, "0.0440815837", "16.67", "0x9beff345564adb149b7e81c124b39c41872e728438166338e0a3cb8bb113e4aa"),
        (79, 1752570895, "0.046", "14.29", "0x326c1a05827acdf15539b727d46400428fe458eba4aaf12003440f33ab4fec3e"),
        (80, 1752570905, "0.046", "14.29", "0xa4061df294ba0fe346302f0baa20e57cc4b2f2ef54c1ff9797447ef09dd8994b"),
        (81, 1752570915, "0.046", "14.29", "0x54041e7572e7eb3a4c71f269215ff020f912a85c83424260150ae7578bf3da54"),
        (82, 1752570919, "0.046", "14.29", "0xbf08e1ed0e869d7c46cdb6292cfcaaa4d73fb648d4da4b06b2e3a5625fc173c1"),
        (83, 1752570937, "0.046", "14.29", "0xf95a3ca7c44bc93da9515e5d9d4dbfaddb865448e1e83e367ed73eacfc6ccd2d"),
        (84, 1752570941, "0.046", "14.29", "0xe7f5e6cb6ab2b252c07cb7bfe9b08f6dbef1951807e883336523cce3588fd954"),
        (85, 1752570957, "0.046", "14.29", "0x30a009c6761d7ce5fb5a530f6e6ba852bb8927a469f6d19628df38167a525af3"),
        (86, 1752570967, "0.046", "14.29", "0x41c7f30c836813df3f61eefd92530b52df1969b1749935f429042d5ccea24895"),
        (87, 1752570985, "0.046", "14.29", "0xce77964dc0d44e1d4ce8bb69352584b67dc74ac608a31abd262581e50390681a"),
        (88, 1752570989, "0.04", "240", "0x5ad68c2145883f27a7f37e88f3fe25beabf4c8e5a6c3eca008018392251ba6c3"),
        (89, 1752570993, "0.056", "12.5", "0x9cd989cd19ca2d1c4bc7d6ec2c98821321f9edab1c5d196eb78a71ba317e9864"),
        (90, 1752570993, "0.056", "12.5", "0xd5556a4bfbaf88df94f7582b266bbedf0455a01ee730d5fb702126b73ca5ef4f"),
        (91, 1752571001, "0.053", "14.29", "0x6aea7a5129026fb0542d2fd1e42114f73cff927a6a24a9861c4b320505ad3ffc"),
        (92, 1752571001, "0.053", "14.29", "0xcb6e5753a76da816fcda93a696c05a2907acc1940f8980cbd103105cd0b7bd7d"),
        (93, 1752571163, "0.055", "16.67", "0x5641d79e676017b219ae267042e83ff55f5a9d7d137876b0a8b89e40af3644fd"),
        (94, 1752571163, "0.0552891422", "16.67", "0xbb5d680bc607ae95753950b24dfd3961e9b647c7ab3e451dd3f2202eca97e078"),
        (95, 1752571163, "0.0506412717", "16.67", "0xd992c1753918eb74709715d94344c323518e897f9e3ec7277c044f261abf06a1"),
        (96, 1752571297, "0.041", "5", "0xad9900fab42595475da4850eb6481f444ee8efe5d210adce9c38713abe52bf5b"),
        (97, 1752571805, "0.04", "10", "0xfbf29c7c559417cd34b5b31a59059e76a44c4395c7588a6dec0ef459dcb6b4e2"),
        (98, 1752573111, "0.036", "40", "0xd102f8b9200baf4b11b188f8f80a67e039635f745f17b238268598b7c0244975"),
        (99, 1752574059, "0.037", "40", "0xad0aa0d4ac3a6d192db889590351091a0643d583e3cf77ce9f5c02653e937a9d"),
        (100, 1752578907, "0.037", "1.41", "0xa895cf573318b0f90bbbc1b7b0662a0eca54c4278fe36ac0e77a99935f83bec4"),
        (101, 1752579313, "0.038", "18", "0xb3976897f0533167186cb9a35681a16cec1dac45405275518b4cc593043b1653"),
        (102, 1752580549, "0.0411474291", "1322.67", "0x0bb0f349d08d718f9fd14d233d0387ad92639f295e28139da1bec21f4e9b14cf"),
        (103, 1752582713, "0.0420743252", "23.76744", "0x353df31782bd1275b7e7d9697cf106ddbd4f47039c435a28097137f046d77ce8"),
        (104, 1752588081, "0.039", "3", "0x25a8661daa94b2b012de733eff9749edf929b7674fff2aff63df218fb33554cd"),
        (105, 1752591261, "0.038", "26.09", "0xad49e4df3491ae543b531c4b51c120d864396e6960a68b399f67532b40382ba3"),
        (106, 1752595320, "0.04395", "200", "0x77751c46a482426cfc1eb73b79abd2be05b1ced7d85a2886d40fc5fd07b8d49e"),
        (107, 1752595344, "0.044", "100", "0x82b39508072fc3add4093c8dad2b0a4d4d88fbd1bfb0924d27f24e268f69167e"),
        (108, 1752599747, "0.0445578193", "669.467233", "0xf3506fd847950fc5c617eceae86bdd1062f490a3d48c5b88a17f7a7ef2593fb9"),
        (109, 1752603351, "0.041", "5", "0x94c9b2b9f3bf63178b937d6b5191f0399118d12ee9af9f0d325fb30af899fdce"),
        (110, 1752603429, "0.041", "86.99", "0x18b8572644f91e622328a847994745574a8e11f47b629fe0488910e68f545cc8"),
        (111, 1752603796, "0.038", "3", "0xe0e868e915a5a25511e51558ea44a9a3716abebbc1a3e803360cc39e09385b3b"),
        (112, 1752605762, "0.0468571249", "6381.1", "0x84aafe8154f638a7f37352cc59615db67d7a6ed4edaea755153445e2210af00d"),
        (113, 1752605764, "0.039", "2.96", "0x2ca41bcc7957adbfd8d689adaee36d68cfc3835bf19ca08ed942f2efd9995fb2"),
        (114, 1752606872, "0.04", "10", "0xf5d98f33f3d4ca1e5de1487a156206db88c2b40b07def2b62ddcfec80819d3ac"),
        (115, 1752607258, "0.039", "200", "0x4f634cf34eacfadbe2847184da71247457b835b56a8634d3ed2802b8b5c95820"),
        (116, 1752607556, "0.0360432911", "167.24", "0xc20e3cc9da9c8d0de7e09b67abf1624ed5911b9eb6764a27fc4f53533c9c22bc"),
        (117, 1752607578, "0.036", "8", "0x390e37439dd62104438586e3784b61eb1f540f5acfb7df073dcbd18184dfa4dd"),
        (118, 1752607582, "0.036", "5", "0xe204ae4ac2f101d54792ffe67b6b304f46ec399faf252723b1cbb142e74d0da3"),
        (119, 1752607588, "0.036", "24", "0x7a194201f72b5bb0b1005fff1035965e1eb558dbd089f9b23ce347ce0e80c3be"),
        (120, 1752607666, "0.037", "207.23", "0x21040ca374561c48fe72e896d7cc8f2d8efc2bc882b5cf234143f240a20e86f3"),
        (121, 1752607990, "0.037", "165.03", "0x6860de07f8191e389d8fafe1bb7a081c7c57341771b816a7b7860766fa5a450b"),
        (122, 1752608596, "0.037", "209.97", "0x207d898792859180d2c96cc073d21a0d7d335983ffdb419a663109ed21152532"),
        (123, 1752609072, "0.0415841951", "2404.75976", "0xf90a67d446ace4284bf0843e7884980e1d6c525ff3c9f5ca2524024bbc923695"),
        (124, 1752609238, "0.036", "10", "0x1a6600b15bfc666403aea4482d6641bad779bc48eea9ef9500429bcd2ded9711"),
        (125, 1752609700, "0.037", "1000", "0x2bcee4e7d9583082e03264e563dbb1a96c54382d036e0c5ee5985557dfc5c70d"),
        (126, 1752609704, "0.037", "5", "0xc25e1b16e1313eee464a49b385406511d64a032173466265afdad2d97e794894"),
        (127, 1752610132, "0.04", "100", "0x750008215a08ad87d0ffe1a9745e1fdcc611bab06de92d1783c73abe0349975b"),
        (128, 1752610322, "0.0404560496", "2471.81818", "0x3dc5895c5a00aeb99ba7e2506394a593577089d3b28ea409b60a826be62d8f26"),
        (129, 1752610958, "0.034", "9", "0x32154e4e258090cbb8ceda0a26aad21739034f9c5f960cab6d97f1a3eb80b9fa"),
        (130, 1752611670, "0.049", "10", "0x0778e80664743eba9e3194b131bf96b3e9fe90061a9576712b834a62240998a7"),
        (131, 1752612409, "0.044", "5", "0x6662abf57f5a56de9f10ef1d5dc7690939bfebf70f2dff1e2b78748292c3b56f"),
        (132, 1752616109, "0.013392844", "74.666665", "0xb56865b0603701f44a3e5c6341abb8323d3086775b9b842e2c6db7f844cca1a6"),
        (133, 1752617103, "0.006", "162", "0x81ac40fb96fbdfe59dc48df33810ac9930fa40d045b9806229813ddfd84490e7"),
        (134, 1752617111, "0.0090529159", "110.461537", "0xda02df24bdf9401bff882e23145af9216c5a8c12ab02b73f2b30c9ce09cf914e"),
        (135, 1752618009, "0.001", "100", "0x26e6dbd81eb16019f109679f00ac5b37bbb6b2fc282c61fa6d091dad5a4988d3"),
        (136, 1752618193, "0.0062532569", "319.833332", "0x20aa7ddaecb1ff397ef0872fbc2a1325499ed01a28196bd0c1aed956313f6d77"),
        (137, 1752618231, "0.0106796118", "93.636362", "0x63046a0ff6c0ee5a9291ecfc5405f01e28e5d75d62c68455a6975be15cbcf5af"),
        (138, 1752618569, "0.001", "3000", "0xc6fb0056f61de8ab45394e2e0fd7d06f4ead030cc20c8e53a38a71355602ee0e"),
        (139, 1752622461, "0.001", "5000", "0xbb3959d22824a26aec3f12913098fa11c87a8b9b943f962a1d3910a0a31fabcd"),
        (140, 1752624155, "0.001", "16", "0xb733eb4679479414ad7d0e310a0883978329277fcc83f447b6247c1d840369c0"),
        (141, 1752624263, "0.001", "16", "0x53445b8497d87b3a741798b2f092f1c58a34347e720b00bc4b566eaa94ead740"),
    ]

    fileprivate static let retained563328No: [RetainedTrade] = [
        (0, 1752516056, "0.968", "10", "0x548be9759439b1aac1ffbbc427ba5f79ac108d4aa76390e1bd529e074b178d01"),
        (1, 1752531495, "0.968", "105", "0x98f205e10d77ee44ccd0637d82e287dbb0b79c0f2a8a986f4e0908442f4dca80"),
        (2, 1752531593, "0.973", "53", "0x2e702d00d5c95164c0379a0ecd6c7a4bb99757379e99edf137061484d7872368"),
        (3, 1752531593, "0.973", "70", "0x9577b473528b664b91144ad9c45cd670c7f2d448c25b5d6c0c39d7e5f8837e1d"),
        (4, 1752543221, "0.97", "13.37", "0x68161ae5faec0fa5370fd86c0efee35a64bc821f9899e41cfd664b6da36dd22f"),
        (5, 1752543221, "0.97", "10", "0x8e6694e05ab928f74df1f2848e7aeebde2d3c3fdca3d5968423164ed50619b01"),
        (6, 1752545815, "0.97", "11.63", "0x9e2e2a88501169b719c6c1f978f3841e2ceee46cf50665279a350f5f26fa367e"),
        (7, 1752545815, "0.97", "10", "0x9f377846a64bc83b4ac12c0f72295e1e0f94c3dfad668bdf6483877a915e967b"),
        (8, 1752545823, "0.97", "44.88", "0x4e8615be589deb94e7907cd75391abe5772f56e33526f65d748d59a2f2603215"),
        (9, 1752545825, "0.97", "11.63", "0x6adee6a8ef09683e6fe1631d37d5cfd80031659fc88f852a209638cbba55ef75"),
        (10, 1752548828, "0.97", "370", "0xdad808ba82306e00dda218467a65ab9882e999a61086eb580b85acd3500f8af7"),
        (11, 1752548828, "0.97", "330", "0xeb265eec995c073de265b5795289aabf66ea889713311c7c3fdf3d46dae773ac"),
        (12, 1752552353, "0.97", "868.32", "0x2baa9197629855dd5d58b978b9108ffe41f17ad0adb14bef31a3fa0c69b8d317"),
        (13, 1752552353, "0.97", "2220", "0x56e15432216d0668953318124be1ada5631ba49803a9c8117e7278c55c2cba5b"),
        (14, 1752552377, "0.97", "21.99", "0x948c4a63ad1525e3b68a5433b710a3c0e96989ef76865a4c376193d6fdf210c0"),
        (15, 1752552399, "0.97", "25", "0xf04cf0e364e67a6e0b3abfff85bef467ec7ccc42bc75dd91a0f5518f1dbe9f27"),
        (16, 1752552431, "0.97", "9", "0x9ed969039b59e218cffbea4e2fb80b84ce385213e4acada25d59e7d4e0a28fb8"),
        (17, 1752552435, "0.97", "8", "0xee102bdc24451e1fc944e476e59e1ee81948d9879f8e4c238dc5581c527ef4c0"),
        (18, 1752555149, "0.97", "30", "0x3a3186fe14e68a438fc54f175a3433e26368368fc28534f8a4f6793473e80425"),
        (19, 1752555149, "0.97", "37", "0xe95c4c0a4376d787d5a17a0d24ba80f1eadaae97c1dd10ced9d99a43bddd104a"),
        (20, 1752559303, "0.97", "66", "0x8a68fc5f8eb138fe921101c24d6e5ff79d747001fec2e65fbe2cef35e76cabbc"),
        (21, 1752559647, "0.97", "100", "0x4a2c95a0376baaafae8f61887ed74dda4e09a9fbdc8d35c776022482b08636cc"),
        (22, 1752566381, "0.9665669697", "66", "0x69878567c4eb7d571281d5d10a07655b015b66a30c5e4cd06931ceaba24e659c"),
        (23, 1752566385, "0.967", "156.25", "0x397e3db32929e11540c430bcf7880ac807148036b4d93ad554cb16a0379e4a03"),
        (24, 1752566385, "0.967", "53.75", "0x7c00c388d3dd01aa8de0480dabcaef84a7e3170905847214a3ccbb5e17cae6d8"),
        (25, 1752566385, "0.967", "66", "0xa84cbc1bb719380ad4ab173439b55117f6f24858a6c3128a29a456ad00c26c56"),
        (26, 1752566654, "0.964", "40", "0x609dedcc7d3754be66df5aeeb7398ba5b9155ad13c671f6bc86410d039d003bb"),
        (27, 1752566654, "0.964", "40", "0xe592d6968589361b2ff5268ac40ab2d841a2d0c46cf24f3fa6661968cbe988f0"),
        (28, 1752566658, "0.964", "6.25", "0x2318d435a25e2f36e405f06bd84a972dc6b4f4cc1970a4dc26b7d8aa1f1bc574"),
        (29, 1752566658, "0.964", "6.25", "0x93bc95469724604bd1e6157460ec94beb86b95b79f66802c21ae3c678e02f532"),
        (30, 1752566702, "0.964", "24.99", "0x44284782759861595a972cbb0435fb13c41e6e376c33f0c08051563f804c9e93"),
        (31, 1752566730, "0.959", "18.05", "0x84aab5a42c890832e98e57488c2c89f92aa3d9fb8e18240b2d0c64ddfab18e5d"),
        (32, 1752566734, "0.959", "6.25", "0x30fb104f3130fac1c4b05f6f51d6875c52c6f4bbfcc025f1f93fe50b372588e2"),
        (33, 1752566734, "0.959", "25", "0x9ae7a455274df0467f28a9fd708a7cd261f3e2662a6e0d2306e177738c029e43"),
        (34, 1752566812, "0.959", "39.99", "0x3cdbc88c6caf64b19bf2c6ee3431800b74fbd387bfeadad82a5fc3d1b3f7d690"),
        (35, 1752566816, "0.959", "102.22", "0xf89c65c6edcb7f9206e4016e07b914b3a9343c1154d99acd57a0645990523aca"),
        (36, 1752566818, "0.959", "12.92", "0x9aaaf338b7437964364bd64a05ae12f32f9577d39f417d31b6d7ba82dab0c39e"),
        (37, 1752566820, "0.959", "5.01", "0xa0595d26faf99781349fecd95cf22d9c6890cf80deb08a5ba62a8ccb55dacbcd"),
        (38, 1752566820, "0.959", "13.33", "0xeeec1354007f90d8583713f136afe39ec374a0fbc9cab4f63d2c7fb16d1c95d2"),
        (39, 1752566822, "0.959", "5.56", "0xcc77a2a369a0f77e8f8b30d490184be0271ae52fc7ac056e0900abeae5685d65"),
        (40, 1752566824, "0.959", "5.56", "0x50fcf5450c6330b7877b576e31835385a241c25b012ab9273660657a66ba670b"),
        (41, 1752566838, "0.959", "27", "0x3e1d1a751157a04eb0a2932dffec154ca2735e98ac570f6401cc93c0f714d0f8"),
        (42, 1752566848, "0.959", "27", "0x9cabb32edfe2fe2181f8b8d8b9bd685e30b2a58838c2d89d279b3edc48d26674"),
        (43, 1752566856, "0.959", "5.56", "0x8e53967ccf06bb8c3ad31551551331a54f42cf0282dd413cc4e7bb517a528c78"),
        (44, 1752566860, "0.959", "27", "0x99bcff4216b3d7b43a7c1d85a084fac6e485990060ac318ac3062c425ccc31c3"),
        (45, 1752567078, "0.957", "31.25", "0x2ed98557c4041226ea7fc59d15e88a8ce00a8b872e7b325eac11d123b1dd856f"),
        (46, 1752567933, "0.959", "70", "0xf216f34472346a9b56bca579cf54b96b02f578130c49fc32a9a2246a90e68f7b"),
        (47, 1752567961, "0.9597684848", "66", "0x222daabb1dc22dcfc0af78870710966f5296f7a410c00e9c349ea68af43885e4"),
        (48, 1752568194, "0.96", "23.8", "0xca1b8dae1c05c833bd1eb81bcfd034128448d3189265ed10b21ea61d858c8c03"),
        (49, 1752568198, "0.96", "13.34", "0x01f76a3ff9adef3b3693d2a5cfcccde8badfeb996791848fdbb95fff056fb666"),
        (50, 1752568202, "0.96", "11.12", "0xda62ed4b7469d2d5682c0990ce0430d9c22ab1448d2a7534501bf5eeda5b81f9"),
        (51, 1752568522, "0.9599182898", "99.008425", "0xc2183803a58076c51ece1ab38c0b4f340ee0a6fc6bfe0b7c881b7854c65ec015"),
        (52, 1752568576, "0.958", "30", "0xaf452c18bdf86835968c99b3521709cbdf65bdcac4c571feeee9a24231b07da8"),
        (53, 1752569695, "0.96", "6.66", "0xab849643bc03f7176d699375307cab499a148d12247af6c53d8404ab90c858c4"),
        (54, 1752569775, "0.96", "66", "0x0f8b1a137e4d28dc6932b9e182781ecca292a4855c06166cb4ab8b0137f52fdd"),
        (55, 1752569791, "0.96", "190", "0xd42bc6038adf8931ce64df984225579c38a3a05ed9e7435c317a8f0169651cd0"),
        (56, 1752569809, "0.96", "99", "0x95e6d7769b43c92a129aeccef9f5972f2f3c9b60155f543ca92318519443f806"),
        (57, 1752569813, "0.96", "5.56", "0x24bf6567985109401f0150cc7213cd418f13c9880e5490b0fd0d229085679e89"),
        (58, 1752569813, "0.96", "13.34", "0xaddf2c3a6ce68908b27e265562ac0f3f544d5eeaaabd7977c3abf6b012d6eb0a"),
        (59, 1752569817, "0.96", "5.56", "0xdec12c6bbf889680f575c413bc9deef9d8ff981e7dbed4c76a37e87f8e31c4a3"),
        (60, 1752569957, "0.96", "22", "0x57152712f76f1f883708976b3ee5424c08d724e49211e4abe1ddfbc867a77a2b"),
        (61, 1752570125, "0.959", "4.28", "0x5fff5194f4c9cf43f577c181d36f7691b4fa4ad39ea4499197e897a1e84e9b17"),
        (62, 1752570167, "0.96", "15", "0x8c2513e58f7de66e85763471885596e47c4429d2a64b41126d65089a67363081"),
        (63, 1752570167, "0.96", "170", "0xda456f430ea324b2ed82ff74593b5b4fff5c0087b5a0984c4b19aefbc7e29c73"),
        (64, 1752570167, "0.96", "15", "0xe290fd55b338910a114817d3ba93b5fc33bab15fbf45ed1934d62c0ed31b0727"),
        (65, 1752570169, "0.96", "173.19", "0x13ead4fb7ecbeabc873a37254de987e32f1a6157bb1ddbbeae553c8bcd4ca641"),
        (66, 1752570169, "0.96", "66", "0xa82d4db0e561b4c0db1e01fec7efdf7ffe557ceb6c0206bff48bff2dae1e54a1"),
        (67, 1752570171, "0.96", "5.56", "0x3238607f885072a1be49ab8c18bc83130a3881c8d77bbb92d1c5d8e3c5ef852e"),
        (68, 1752570171, "0.96", "5.56", "0x9e62892c144bd087524dfe0d8ecef0cf79623c606982eb98a36cd0a0327a3652"),
        (69, 1752570173, "0.96", "5.56", "0x0a61bc0bade4a3e9853eaa47d50df82205ba13464c931ea9eec522f51eec8247"),
        (70, 1752570175, "0.96", "5.55", "0x9edc67226fa83d5d75863a60b7dc7c77929411bfa9a8976782846da7c4c5263e"),
        (71, 1752570175, "0.96", "6.67", "0xbbea2372404420b42ef128b1aa9c08d2bf8e88cd8b0992b31a4bc1373cb47c11"),
        (72, 1752570177, "0.96", "6.67", "0x6cde4de7d6d06a9ab2e1f47d45e3b67779faceb8472e93f3baf2f190064accd7"),
        (73, 1752570177, "0.96", "6.67", "0xfad78eae939e9edbc6e485a99b5e34ba85261c4fca518659b11ce7d10dbfc644"),
        (74, 1752570179, "0.96", "6.67", "0x1c2fc405bf439a964dc0da6926da8ebed36b781fc36b2e10c4a0e9df9f9a27ff"),
        (75, 1752570179, "0.96", "5.57", "0x2a332960e03632afdf1c566dda8047fa708f26fca3d361a6b0140c37dee9c4ae"),
        (76, 1752570181, "0.96", "6.67", "0x68b322c17fbd8b5ce40d9eb9721353887e2401e77bbfb177528986d8875b00f2"),
        (77, 1752570181, "0.96", "5.55", "0x9c7c0b267fcd9114e147dbed3de43dae50a61bdbf9d330531c5bdddb3fcd1612"),
        (78, 1752570181, "0.96", "6.67", "0xb59bd65b887c417bfbb4f12e0b31d3fb24a19eb0e2c12594f65501437e420ba9"),
        (79, 1752570183, "0.96", "5.57", "0x708ebac505fd2adbc028b3d7dab4c0c317a5021bb7f2cb9afbc5226744e6d0a0"),
        (80, 1752570183, "0.96", "6.66", "0xa01a832a6b8638ec6a0c84a0710578bbca7c3d4d8701e49dcedd2b76abd1f6a1"),
        (81, 1752570203, "0.96", "300", "0x2fc70de7a8a30e5e235147f3843b92cd0c934fe9df8af7547aff15e014a08c05"),
        (82, 1752570203, "0.96", "15", "0x49d0e4c3b283936bae8b109f97452ccff01a758b6ddf57f28d2caf310e50d2bf"),
        (83, 1752570203, "0.96", "15", "0xf115a68858da6620a44937a216c8d151339db44a6633520b00a184ebabe3411b"),
        (84, 1752570205, "0.96", "150", "0xb1a549afca3017fd3d37ef93fdd0de286850a6a82737b0ec309a46837700389b"),
        (85, 1752570209, "0.96", "13.34", "0xa82f7203d3920968ad6870d813a36ef4fad86422e9bd803657f4c586fc7bffe8"),
        (86, 1752570575, "0.96", "13.34", "0x3e9842ed332cfd1d9b0237caa3fd619911ff640af2b75cdd5fad9162aa692558"),
        (87, 1752570643, "0.96", "1000", "0x2855377969e495a28d76fa96227e5a88fb6c54f0433b95eb62014fc496ae2372"),
        (88, 1752570643, "0.96", "39.99", "0x388a5c9ee780bd6a4ce56c1a7e055e47248a80b88ced02c1380e5a97f1e1dbb3"),
        (89, 1752570653, "0.96", "20", "0xc00242dcf9ed74e1ca781778fb02868693db892ce52da1a422bbb9601c0045c8"),
        (90, 1752570827, "0.96", "66", "0x187398674826edb0b50b75d22594b9557b54add26529e71e55c627b77c65419c"),
        (91, 1752570827, "0.96", "329.94", "0xaef28859db3862bff596257897d908619f8a656aaff6b71f61c96622acc81190"),
        (92, 1752570827, "0.96", "9", "0xc0afb3ac7957d4aee1aa59d45ea0a1b0b55d3fb741114fd99350dac2e40ca846"),
        (93, 1752570827, "0.96", "39.99", "0xce80b5b79453f496fba27660136cb58b7567b72b14806bb4a16ce6a0455102c2"),
        (94, 1752570827, "0.96", "452.13", "0xf429063515cd488ed522cdd1af87a36b704805b1252302aa4af00e70aed9054e"),
        (95, 1752570829, "0.96", "5.57", "0xf78824b01cbd6467112fd2dbcbe92009f0c2b5b3de97b26d9c9317f13585fb1a"),
        (96, 1752570837, "0.96", "37.03", "0xc49b8cee45b8ce11d4d754ad1c398165135272ba9deb7e15c39019b5dbcce6c4"),
        (97, 1752570841, "0.96", "9", "0x2357622bdb400b05a49e7359ae6bdab73ad8155cf2a240c2bf4c407df79711c4"),
        (98, 1752570841, "0.96", "9", "0xd5293504a4421a1d75682243a6670520bdfcb1b616c5c03bd875e66375272ea3"),
        (99, 1752570845, "0.9598900125", "9.001025", "0x482858e308d77b91665d36eb7d7dd02abf674958207e18eca7b18e743e3e14a4"),
        (100, 1752570845, "0.958999967", "9.009383", "0x53bd15dc0a6a1746d95a73e7520daae98bd30c573062de1caad445a635cbf2fe"),
        (101, 1752570845, "0.96", "5.55", "0x8814f30e11e96f035b6a8baff786f072e6db885c0ac54e10af23ce39d444e34b"),
        (102, 1752570845, "0.96", "4.15", "0xc4ebf3c66528c9e1466a1e4a78948c2e4f71c0281476764105d8f4587c88a9c2"),
        (103, 1752570849, "0.96", "9", "0x8ac43d9194ac6a8b38480183aa6e4ea1e6fb346212abef51e4dc079236d0241f"),
        (104, 1752570851, "0.96", "9", "0x19b1e9ede553441dfb78e5ee148b2461cbb4b999bbca627d453d7c05fb109db5"),
        (105, 1752570853, "0.96", "1.1", "0xaab8f831dddd71b9a8080b41b9e21dbeb869d42ce0e75fcb6bc9b55ee091cd97"),
        (106, 1752570855, "0.96", "6.69", "0x8198edfb879ca0bcee7443fcfb2466895c85a1a30b25377b0317e2b77ce11a74"),
        (107, 1752570857, "0.96", "9", "0xa82d05b84e8a3a83efa9e9e785b8591953b6aa407a21bc7b644d8a2ce14165c3"),
        (108, 1752570861, "0.96", "95.51", "0x2f1e7e993fb431acaec922a9861fd9f0ff41d1f2ef5d26b701b31e41481ba910"),
        (109, 1752570861, "0.96", "9", "0xd900fad0831299b05cdf0b122bc4d345214b88d2a18a119032106620653e9bc3"),
        (110, 1752570863, "0.958999967", "9.009383", "0xb4bd4bdc5abe8249125148407301160de7e1b0155114995ace980bc6824fd028"),
        (111, 1752570867, "0.96", "9", "0xc6b7412f12e5ac8acc7a0407f501c685d0ea8dac74a0765c16f3b12dc3279ef8"),
        (112, 1752570869, "0.96", "244.7", "0x0de923d75b262a50e28df6f44211a08b1c4ba98954e5169128c0bd2abd7d35a1"),
        (113, 1752570869, "0.96", "5.56", "0x76fd50bf3aca30a18ffbdc2b2ec755c6c4e5573ae540fd88c681750afb8051b2"),
        (114, 1752570871, "0.96", "5.56", "0x755689c25671aee5541e8360f3218a5509633350d91f7c060040649eb5b1613d"),
        (115, 1752570871, "0.96", "5.56", "0x9741ee0f167fda9e4ee8f63604818f9a3f9009bddaac5d8ce17ee0f39c62861a"),
        (116, 1752570881, "0.96", "5.56", "0x7e037877959c8f4994f2e1238d4c63df01e80de98979a3e4f236a74c5d344172"),
        (117, 1752570885, "0.96", "27.46", "0x879fcf595f502f82e7a649aa8620890a155b0a8290cba97a06356e50d0b84818"),
        (118, 1752570885, "0.96", "5.56", "0x9a96c0fff9cb13b9ae67c3cbb7831669247da2db27389c268f86bae1fe6df726"),
        (119, 1752570889, "0.96", "28.44", "0xf9c7347634a9838a39363cd62892091c87396ffda0d064faccd52c5ce4ff0936"),
        (120, 1752570891, "0.96", "39.99", "0xcddd830327b25b0a03fb5e3eec85dadd890cba2cbbd1d19eada927fbaab908ca"),
        (121, 1752570893, "0.96", "5.56", "0x2de82f2dffa86ff3b9466b099dab2b21c6ed41f7701fbd15b9f0fceae75dcbd0"),
        (122, 1752570893, "0.96", "3.19", "0x8ef1af8c32be3fe38ab5d8cc0c6110d6ebc78eca9e158a4425f88d8566e9e9bd"),
        (123, 1752570893, "0.96", "5.56", "0xb87345636cc9d6ce8b21dfbcf4d4deb276f2e8737aab2bb8cc4a174f02e28356"),
        (124, 1752570893, "0.96", "5.56", "0xb94f2c757fa1ccc4a61285eec0893fb6e94f469c46d6b9b3ec13f8c53b73a40c"),
        (125, 1752570895, "0.96", "5.56", "0x003fd00fe349acc10e4948d67e807bea7d863ec466364cf44e44ae472e248e7f"),
        (126, 1752570897, "0.96", "5.56", "0x83f941afbfd202957ec3d821bf435f51b3508665ef958ce921ff958a8378da77"),
        (127, 1752570901, "0.96", "62.48", "0x00777dc71b8b427953c14a02cab0d744334c344f284e7f10168446917467c7e6"),
        (128, 1752570909, "0.96", "242.29", "0x85882778fa4726563ef876618970de2fbd52724d16d155400c74be1b7e885622"),
        (129, 1752570915, "0.96", "60.34", "0x308c2f451963b88f1cf5203a4fa2b0739aad9fc9cb73249eb69a5b3f42f79b71"),
        (130, 1752570923, "0.96", "6.77", "0xde6400a853dd8ab72184ec5af98493b7466d2688ad425236a79696be3ef4edee"),
        (131, 1752570933, "0.96", "271.67", "0x3334ca99ff7f8727dea35b748282da8d74713150e1f082c9f9095a981e6a04b3"),
        (132, 1752570939, "0.96", "84.12", "0x6d7c20a9afd63b95471d9c3b5b307de6826d57cf41b730c1b4362efc98e444e2"),
        (133, 1752570949, "0.96", "15.46", "0x1df8187836769ebd0ce934b99f9cc0688d86d44007e136c8f94a1a3aa1a58977"),
        (134, 1752570953, "0.96", "39.99", "0x08f96af142e12d06023b2ff38a345a3477a1c34dccfaab3be27f87508b2bab88"),
        (135, 1752570957, "0.96", "1.74", "0x7a226aa291301a2f36af82fe66840d06c1eda483bf0f5814f2f8cb49ff3ba1a7"),
        (136, 1752570963, "0.96", "242.52", "0x9d2d94db88d232b9f316531265fa1195ceaaf27351afaf5ab13436c594e39d6c"),
        (137, 1752570971, "0.96", "5", "0x4440ec61637360f39310c6fd8dc09257161f5e74f1b42aae4b92298ef07edde9"),
        (138, 1752570977, "0.96", "6.66", "0xd0e404edd15472a33b7fb06602b5801f5326e7ae924098f613980de8fe7c6bf7"),
        (139, 1752570979, "0.96", "110.73", "0x0d2edba647c4a7f764c7a492c970566bcfb582857dae50558d53deeaa0c5fb26"),
        (140, 1752570989, "0.96", "112.27", "0xb53268bf818c9daa859de81e78554f517c0ad10e38515ee354e313b5a6d8dcea"),
        (141, 1752570993, "0.96", "9", "0x3a547f6d1064fa324cc1e30102efda9195e6306199be4e2eb09f05d9a74fa0e8"),
        (142, 1752570993, "0.96", "9", "0x8a185acbfb184c772321b883349ba37bd122631bfb25a45c2357fb310ab47ff3"),
        (143, 1752570997, "0.96", "14.41", "0x1a9ada26110922fa1a5d3a6d7317142390ede8bd1f89147dabfadfbf9ab08f3b"),
        (144, 1752570997, "0.96", "661", "0x1adfa0a9a0add9605809d5b66ea606f07081747492513927a3fe2f92ca7a129e"),
        (145, 1752570999, "0.96", "190", "0x7e4957fd914706125759bd72dfeea87c4fe7fa99214cfbf977c4c181abd4d25b"),
        (146, 1752571007, "0.958999967", "9.009383", "0x8a1155eaff076c9db33d1da4ec6a35192523a6832fc35e5cb90c42aa551ba373"),
        (147, 1752571007, "0.958999967", "9.009383", "0x9a949f8c892dc4225fa7a485db1c8f1e97d9f07d19cd3abdfef1c25133ae7ed4"),
        (148, 1752571013, "0.959", "5.2", "0xb70f3767be09326f80c8f1988b353cce9316ca34835f37f49af4981b00cf3d41"),
        (149, 1752571013, "0.959", "10.36", "0xba52a7681248cd8a985746ce06bbfab586895a20d2548e3771934e81954dccd2"),
        (150, 1752571159, "0.96", "253.36", "0x8e38317f776897182f56ba96afb8a916aae99c70a035c800c95307819d534a30"),
        (151, 1752571159, "0.96", "66", "0xa190334c7f52730a35afd84d17ea56059649f3e3d6913a34949d78fceb046637"),
        (152, 1752571159, "0.96", "250", "0xc79c0900c839a6eaaaaa1cd69c782faaa4b01aaad97fe4b63888d81638158f59"),
        (153, 1752571297, "0.959", "40", "0x2f96a82ce8ca4c90509658c5592fab26fee0e1fcd7260e6786ce5f5e0e0a27b4"),
        (154, 1752571303, "0.96", "5.56", "0xf0e102f3cc06e5b83ef36508d2c7d40c7ff38be359027ca04fb64767a939193e"),
        (155, 1752571305, "0.96", "5.56", "0x8b2cbf9a554c643fb2923b3904da9cfb3899085babc965578326fc7b3559ba40"),
        (156, 1752571437, "0.96", "13.34", "0x66170a595071223a32b68b24ae02c97c6721cb9ea25359959534347d4fbc688e"),
        (157, 1752571443, "0.96", "5.56", "0x7fbf6c7fafb66b9b0f16b0297574cf4aabc257c8ec1514035f5cb1e17a703ee2"),
        (158, 1752578841, "0.963", "50", "0xf6dbec989c7a98b4eb45124ec054fc15d08ffd875ca0288a94b7d4f9808f7c4f"),
        (159, 1752579313, "0.962", "17.99", "0xfa963d3d0a1ef3979376e078f927d093cddfc5b40cb884684fb694bb70723517"),
        (160, 1752582113, "0.963", "2.83", "0xedab6f79ffe38f06accab76820ef56980ec6a63822ea2e6ce8191ac61ceecd45"),
        (161, 1752582529, "0.963", "20", "0x080331265b219bddbf55559d71585e0e8a3ff48f491bcc2b28e8312bf9348704"),
        (162, 1752591253, "0.961", "20", "0x05e5452b85fab9952e055de72b11c065f00462d619aee6c10a2dab8eab834e3c"),
        (163, 1752591253, "0.9619763636", "66", "0x41cb1d3960a8341a3e52b104dcf074bab5e755ce5c37025f2631a7e6163cf846"),
        (164, 1752591263, "0.962", "9.47", "0x9fa783db0e24bacd000e93b9831c5c5e88cca5f94c3bec4c868a8ebd07d76e48"),
        (165, 1752594304, "0.962", "16.61", "0x47fa4925b7ced99d049dee08b5bc7b4ac7ab447635a1b6d9f3d587998505fc50"),
        (166, 1752596404, "0.962", "6.4", "0xd36881f9e8255992f8d12b44371e13bce7c311c19a88f65747c0810e3bbae913"),
        (167, 1752598682, "0.962", "15", "0x2b4f5f5801a3ce58234e6a45bae06bceb561b36fed0da7ac4e0bb41fcbf884f5"),
        (168, 1752598682, "0.962", "15", "0xbe5d4e6fc7a9c2788c9e90436d6f8e4847766b7754ec087917f2f72c3d94d8d0"),
        (169, 1752598682, "0.962", "200", "0xd550bde1547860aa18e8efeee59baf9b5c87a50d558d23d10e524ac64bb1306d"),
        (170, 1752598740, "0.962", "125", "0x6fb0b7d38857de3daa929d54200e39e7ba4120e20b8aa3e720365d2f0b70e446"),
        (171, 1752598894, "0.962", "38.5", "0x69c6f70b76d74e9bd0bc98485b1124e2c158e54cedc4f1e90df62015b36aff0d"),
        (172, 1752598900, "0.962", "5.56", "0x7e6cce5bc3e7ba194b80030a81eb42e3016aef6923127dc00b01cd34fe94cc5f"),
        (173, 1752598910, "0.962", "119.44", "0x9299c19600037c5322e03248f643d7e1f94688151d55d0a27896cc985b078a42"),
        (174, 1752599261, "0.962", "29.99", "0x306593e6e3696cc9263501eb24896e8f480702956f111997345adba4a48662b9"),
        (175, 1752599263, "0.9619999571", "7.733886", "0x76261e1fe93d0f4071597b471b6513339b56f90890b67c148fdbc71bebab0382"),
        (176, 1752600801, "0.961", "20", "0xba077c6b15b39e52693b3929e9ba0b763093e35a0e93377929173cad8a1ce736"),
        (177, 1752601815, "0.96", "10", "0x8eb94304aefa4f3ccfbf26ed4e0f2b54871b447ce4279db04e2d66a45d8d1791"),
        (178, 1752603351, "0.958999967", "9.009383", "0x5fefcc04ce2818e277c87a4652a640a3c3171ebe5e7e100012c412e11056564f"),
        (179, 1752603501, "0.9619773534", "597", "0x52f35c7c59c7d24c158fd51c205fb38840f2df33d6776882f9d9ef7da2ef0e31"),
        (180, 1752603535, "0.962", "30", "0x424aea8757cd0b5db6c9d98039a688b4786f0df006dfe07e9766163770c5bbe2"),
        (181, 1752603543, "0.962", "33", "0x15bda9c1ea50bbd6f58588ba0f87045290758940aeb36e4b46a512d9104c5189"),
        (182, 1752603543, "0.962", "20", "0xa1a6e4e73885bb9414e2430d2d634c6f086ebf0c080bb197032d252fc0ecb094"),
        (183, 1752605436, "0.962", "111.05", "0x24d1024b155715013d3f1f8b0f10134039bdcc92291e015633d6637c9cf4b6de"),
        (184, 1752605694, "0.962", "40", "0x5bfb007afa9152661d96c53222575b4052bb9b761422bc3f01ab1777db127f22"),
        (185, 1752605766, "0.961", "2.04", "0x4eb1e59885e9d885e0cba8edf5d865b4a5bf7b016ba15338558e6d4d8731fc26"),
        (186, 1752605920, "0.961", "270", "0xfb15fbb660d734d3c839947427f27864e932521c22da9359867a9066035fb741"),
        (187, 1752606522, "0.961", "40", "0x6804ebb77104fc86ef5f8e4d4288549c8db9704947ad4567e5f331c3ee4e94f8"),
        (188, 1752606972, "0.959", "51", "0xd432aad4e8707d7a572f6fac1ac5972559e12980c3cc20601e976dd588ea5b3c"),
        (189, 1752607254, "0.96", "200", "0xa43bf56c95102792c5d19f14ee70a11980b8f035ecba3736cf4b3eec5834b917"),
        (190, 1752607258, "0.96175", "40", "0xa3f17442d2e05b0eb21b25c120feed2d0607e03e27619bb9303cae386ac9ad21"),
        (191, 1752607338, "0.961", "490", "0x6de87350eaa74e910c7f38ff7c598f9ad21d2857e31bb0758f0d51eb48652d95"),
        (192, 1752607340, "0.962", "40", "0x562d6925feabdeaea0dd398144dec37ec262fc95983521bc152450d8b153b8a8"),
        (193, 1752607394, "0.962", "250", "0x70f0603759b6cbad4e7b3739629c8301001db7501d3d09bb45f2579e6f628482"),
        (194, 1752607424, "0.962", "1600", "0x17358e42bf294e28e307fdc6cbb37f324d95a2dd0428d7db0f1a391a34686aed"),
        (195, 1752607428, "0.962838", "40", "0x54a7a4ca1d4fb1db5c55b5060a2baff043ddda5cb50c4d563fb522ca1c868c62"),
        (196, 1752607556, "0.963", "160", "0xac0964ab3e2fbdfb97d16ea2832556e62f5bbdb598236c4fdee01d005991f64d"),
        (197, 1752607568, "0.964", "24", "0xf1f57949f0037a1be4b7f0d73356fcf03d81cf847ed7b044be312480eb81e822"),
        (198, 1752607570, "0.964", "40", "0x7e4671fb12d04d3b156b7770c717853b557f5847b16c74ced7a81a1080a913cb"),
        (199, 1752607578, "0.964", "16", "0x0e789b55ddc8798fb83423d3e43aef803c13719f9ad123bc5b1aa62a7710076f"),
        (200, 1752607592, "0.964", "8.93", "0xe9227bcd842740688dc4acc549c5b1ddd9dc199a36c556b13c6de93c1e7c73da"),
        (201, 1752607600, "0.964", "31.07", "0x7693853345cbfeaa7bf2d8bd17635e64f1a226ee4df80752915ce0197ad2aec4"),
        (202, 1752607634, "0.964", "10", "0x3f58a90228debd243dbce19cede9466673cdea5ce92b25545c1b36d3a284da9d"),
        (203, 1752607638, "0.964", "14.29", "0x58ec433e1fc5e284f2c15eed37dcc0896a422803ae82f225cb7910b310766901"),
        (204, 1752607800, "0.963", "39.99", "0x018bf39cddeffa03537f5df03ac47b7ff488822a9c79f2f0c6856349063675fb"),
        (205, 1752607800, "0.963", "820", "0x31c846a907e8004af63c0a5e44d9e77fc95b403103d32c6c99ad2f4bc7b9ef96"),
        (206, 1752607802, "0.963", "140.01", "0x016f6c7c35a7bc555182d4d4d92c7afca45a39513adfae0e2a8586f967a8e06a"),
        (207, 1752607992, "0.963", "160", "0xdb5896d370a21f684ccdfcc5e49d5fdc13b922e5b6edaa7bfb531577f87214db"),
        (208, 1752608596, "0.963", "40", "0x44f3f284b9baedf800d1d21fe979af8a15bdd4e52534d72638c0095763f96f5b"),
        (209, 1752608596, "0.963", "209.97", "0xc5b013321c6f80e27389c194691925875447deae884974dee8dd09e661c458bb"),
        (210, 1752608598, "0.963", "200", "0xf2b7b66ca9ada3d3e01852dc1fa96304795c7592f57daf654e7e97c9b0503986"),
        (211, 1752608602, "0.963", "16.67", "0x38c170171cbd677bb92484afd4c3b6e1a9d9b0de164cbfbb292babd0301f0ddf"),
        (212, 1752608602, "0.963", "16.67", "0x6fd77df8bafe695d00f1311a28fd784d9d47eceb37ffe8fe1fc005f4d03031d2"),
        (213, 1752608602, "0.963", "16.67", "0x9cdc304c539acb19d3fd1bdc2b150ad27f95caa4f0600fcb307d85e37a4c9baf"),
        (214, 1752608602, "0.963", "16.66", "0xaf2659ad90e98978df72adb0766bba7a39235b0953aa2ed2150b0275ab88a00b"),
        (215, 1752609236, "0.963", "10", "0x9566cdf03253dad4c2b2d42f43f1e4b23e88b9d3204242e5772458da43168749"),
        (216, 1752609242, "0.964", "13.86", "0x43e29d280a3658bc969d394d03bfc777a78af940d5953fbc7eae86d15192ee5d"),
        (217, 1752610080, "0.964", "5", "0xa965b23dba752adbb77405818a03b2e3830ba47a715f36eec8dd1a6d9d51e211"),
        (218, 1752610132, "0.964", "189.85", "0x8db85b6fc59b1f449d9a22f32114a7918ec9cf0ae2a14eb2b9a1b5d82b35e729"),
        (219, 1752610776, "0.965", "5", "0x206d65b0ff740b294bd7b42b37e66006457315de57a40d94a87aa48a4ba7efc6"),
        (220, 1752610776, "0.965", "50", "0x5fccbd50e06dcc75eee3212e7901ed0096e3baafe776914265f47ef578d66d07"),
        (221, 1752610776, "0.965", "346.67", "0x6553967c0af68ea9dca137a600691c9f4f17259a91ecf8fbfdf21a4e9ddc1aba"),
        (222, 1752610958, "0.966", "20", "0xdf04638674577343cb8b62296666109ec1d70eb97193fa18edb48be4938234c2"),
        (223, 1752611670, "0.951", "11", "0x4d98a2a9557d0bf2307d425a76743263505d231307fcf3828a784e42bf63b20f"),
        (224, 1752612399, "0.955", "100", "0x4e40ca2527c0a6860f5a4e9b28ce5fcbed8272f1ff86b4cd095ea8f0e952b299"),
        (225, 1752612411, "0.955", "10.99", "0x661b9708670feb3db2a8a34af14f5771d844c52f25f8619986c31d759d377cd3"),
        (226, 1752613959, "0.961", "20", "0x39f0cc54fd5e7975f7a38abb0dabe26b876fe259b4e4d50c288ea95e9e71f6d0"),
        (227, 1752614159, "0.965", "33", "0x5556f8de9f36f4ca6592b8fb1854bf121bb0f9882ada870d697dec2aa377f085"),
        (228, 1752614923, "0.956", "10", "0x53d90ae573c8d786953261555222be01fb84f2f49e9566055c9ac2bfaecb6786"),
        (229, 1752614923, "0.956", "17", "0x7db46b8485c9acdf9ce023c8f34468b0811f5a30e3b18ee898bb0b7abbde2773"),
        (230, 1752614941, "0.956", "5", "0xbd6a35b27ab4a01aada25dc1f43321ce3772fecc6a3f70592d1faa4cf3e4de44"),
        (231, 1752615125, "0.9716427445", "2536", "0x6889cb7ac2e10fdf8232befcdac59bbd1d4109ce6dc909d719f4d0770c8076cd"),
        (232, 1752616249, "0.9971883521", "226.65", "0xc28030217a09fca2d788ea71b96561acd309e53c18a0b43d555591d68d003029"),
        (233, 1752617197, "0.999", "50", "0xb77364a8cf927db80965038b47ee6339ade5d3bd4a2b1c2159ecc2fac1b33e64"),
        (234, 1752617875, "0.9983437604", "3005", "0x76e45031031211823ad64fb820ded7e9fe2be5245b6b96049ff6ac6654d615c8"),
        (235, 1752617893, "0.999", "1302", "0x515f06ea7d9840b9675df3048a068951bd30b123d37c4fc92c10f710ae6f2254"),
        (236, 1752617955, "0.999", "55", "0x544866d23bfe9a643fa37d4ba25e0adc8acfc910b910f6beaa4699cf90febb62"),
        (237, 1752618133, "0.999", "2955", "0x9763c24acadad4c063d2e84ad35cddac839e8537102bee1cddf50a6408a90482"),
        (238, 1752618277, "0.9952606394", "1833.99", "0xce3c46ccc8b66ffa0779015c612d54b81b1e7648f809177594eca7ff548760db"),
        (239, 1752618279, "0.999", "10", "0x6e435c45d3940325ae3f21704c6769fe1708e3d20645d72dec3094b5a208734c"),
    ]

    fileprivate static let retained563329Yes: [RetainedTrade] = [
    ]

    fileprivate static let retained563329No: [RetainedTrade] = [
    ]

    fileprivate static let retained563330Yes: [RetainedTrade] = [
    ]

    fileprivate static let retained563330No: [RetainedTrade] = [
    ]

    fileprivate static let retained563331Yes: [RetainedTrade] = [
    ]

    fileprivate static let retained563331No: [RetainedTrade] = [
    ]

    fileprivate static let retained557372Yes: [RetainedTrade] = [
        (0, 1751246368, "0.38", "50", "0xe109200525db8ef78727f9cea585fec972066c2ab3ddbe169d315718f4eea5af"),
        (1, 1751246396, "0.38", "13.48", "0x7beff7c9d97a9fdb811fb3c4e37097262603e24e39c6c1dfc3f622f86a2af1aa"),
        (2, 1751246404, "0.38", "206.52", "0x50a35363ec41fb78fd9d949483244804e3cc9fbdc1908385d7c18e3767a23577"),
        (3, 1751247712, "0.5", "5", "0x92aa18c82c114c35b12aeef6984413bb225234e95d7c1f00636ab0d4bd6c5802"),
        (4, 1751256620, "0.6007846976", "582.571426", "0x1668d207a7f1ad5d4709e2d65cf42c5467050e68d1cbcc7a1678863580c488a6"),
        (5, 1751260608, "0.6899999577", "4.492751", "0xcbf8505d666d9deead2f23d35d172e09513a7f1c74b16d64196a0a6af412c184"),
        (6, 1751267060, "0.6099998597", "1.639343", "0x4cf019eb7ed890a2b2f5ef0c9e07c3df9b3c96dc96cc4edce883945bab3b715d"),
        (7, 1751268642, "0.6099998597", "1.639343", "0x41bcadc1e284dc6cae8325d3d65344dc19d6b2dbcfd4bfe604df1755450c18c3"),
        (8, 1751268668, "0.45", "1.63", "0x34f6125e88d24ece4e7e813d99c0e21aa007d647101395e3626fe2f02579e5af"),
        (9, 1751269844, "0.609999939", "4.91803", "0xf603a76a357e8e13240a86ef641bcc3dd29fa1d20bbb93ba609ba6a5c20effe1"),
        (10, 1751287836, "0.6", "10", "0xe7fdc86631e7865d864212c6956b70472dc9f375b7da9b205c62f0b85731a780"),
        (11, 1751307098, "0.55", "61.99", "0x2e66bffb0f0f55b26bad9e85c960dbe867f7e5f00a1b37fc893da72f628dd923"),
        (12, 1751307142, "0.57", "95", "0x6e361fef6dc09d592bba41b1b6d360e2ee62b49d586ea6dfa40934d03a3c7010"),
        (13, 1751307222, "0.6185085693", "329.08", "0xa57d14035f1ddbb7154730f6ff4f46af4da178100c8725829dcd3f47456b79d7"),
        (14, 1751307428, "0.6599999754", "13.030302", "0xa99f82cab304e6eb970fb5fe7d4fa3a6fd8cd6b0b1a5c401baf8bb97e8f5d10c"),
        (15, 1751317114, "0.6", "42", "0x9c44a0c37168766bd29317548ea778ff7245761ab1b8c6739225b5ad67e367b1"),
        (16, 1751317516, "0.6", "131", "0x602f984af7a8740b6f4c4e332a4de4fa913e9e50d64157c5f7a3d992197e584a"),
        (17, 1751317546, "0.6", "62", "0x4175efdfa5c92410ecc7a4d550306adfb40e422e6ce8adae3f1e02f320c7bd47"),
        (18, 1751318368, "0.59", "40", "0x72376ba0331e0fafc14cf86e1f7c872725da01c94bf0b94f0db03958d5a2b103"),
        (19, 1751318378, "0.59", "21", "0x36b310c1ffc27cee63a99a43b485a7467e5d9c2e9a8427327df18534ca88151f"),
        (20, 1751319504, "0.6", "43", "0x73b4d1050bcf6dceae7d70d755f95968f25974569f0011d68cb7b47c10241bf0"),
        (21, 1751319632, "0.58", "72", "0x15b5297c57bec1859d8a4a06c9321eec126bbc5586e05164608a46bd76d7dae9"),
        (22, 1751320312, "0.58", "47", "0x4b248515cc5227ea46c459a150d27cef67fb29d9431910deaa2c9d9decb838d6"),
        (23, 1751320322, "0.58", "122", "0xa5ace6d6cb2cbc5f815640855d877de7ba0154f20ecba58b2f9e4167b3078fee"),
        (24, 1751320370, "0.57", "20", "0xee215e1b41a296fd1f10a8542bb1adaed9fa1f959b783dca4d5975956ee94c61"),
        (25, 1751358437, "0.605", "10", "0x10ac10dfb495cdbd6c5c7b7fe7cbe6e1b636128182d8f68165eb3b5dd832d02e"),
        (26, 1751361161, "0.6199998016", "4.838708", "0x416c58dcb5cbecf63b53222b94277afc678da3e3d70c1efc2107cbcae22d504b"),
        (27, 1751361169, "0.56", "3", "0x7f90837a70e7f90e94c1fc85c5f8c62762674087a1dbd7a4c60cfeeca2b42df6"),
        (28, 1751361173, "0.6299999454", "4.761902", "0xe17266883673efb5ff8ef63eba587ba91c34682597da420a5e5e7fbdbdb16320"),
        (29, 1751381881, "0.62", "7.30645", "0x6b1a986403374072be9894619382d79095815a3d43db724912c62e76ac029574"),
        (30, 1751388145, "0.58", "15", "0xe64d9ee07d61f3eda98bfacf1a21c56d944f92bf4711a402b10ab1a173412791"),
        (31, 1751440774, "0.55", "10", "0xcf3f31889b8533f730d85b135e95acf250de821e54743ef46514c8a13a1271b8"),
        (32, 1751447972, "0.6", "122.07", "0xd3e330a26187aea8b47ed0e2aa430d6b22c441006d60d83cc9642ee3001dd322"),
        (33, 1751468977, "0.59", "2.22", "0x7cb2cf7c817ec78da68c503f1e0b6157ecade6c530e658ae36473dc8b7952d41"),
        (34, 1751489013, "0.6099998597", "1.639343", "0x90f088668fcb7ddfda61f329924cfff4db44b4ae91f93c5791207c760fdbd4ae"),
        (35, 1751756279, "0.5574183976", "13.48", "0xdd4fbd5768f7f5a7e850374bb5054428e5292477f135d613d34ab74af0395662"),
        (36, 1751876992, "0.55", "13.03", "0x7a721a4b43fc95db557ac25130aefcb84973ef6013fd42f38fe94d46eaf9a6aa"),
        (37, 1751885655, "0.59", "2", "0x707091d80b3be976685a813a79c44cab0a4caffa15f0f30b908e72be65588ed5"),
        (38, 1751913822, "0.549999962", "3.945453", "0xde87317d8fcb977c08725b344d4b3dc8ebafac8648a7e57c61bcd78529442c3e"),
        (39, 1752008439, "0.51", "21", "0xa1b7df1d800f551fc85a6f4869bd3caec9ba8873998b96d0f492e83d610ae201"),
        (40, 1752008979, "0.51", "21", "0xed2e5ee64a78e9a52cdc505985123129ed6a863b728372c32a0e0b670f2f553b"),
        (41, 1752052496, "0.52", "292", "0xb21a18b812babbd5221b8c8e2171f88fb534b5753d33175f95af4abb5d600f0a"),
        (42, 1752141994, "0.5199999861", "5.769229", "0x65370352a9129d8bd6aea5cf1e91b17dca4791057855dab77815f735812fe815"),
        (43, 1752144026, "0.5199999861", "5.769229", "0x028af3e7fd54683b96e52f9257cf4126c751a4310438c88f91fbe1d7cd8cbb14"),
        (44, 1752144102, "0.4699999702", "6.382977", "0xdab02c1c83e9c6845e25702dc8f41916f72f9f108b11be266c31a0851f860eb5"),
        (45, 1752144462, "0.4699999702", "6.382977", "0x192963f90e155ced452beeca5c3390458a6da31792cb343cc0f6b5f3ac3ad325"),
        (46, 1752144748, "0.4699999702", "6.382977", "0x87577b3cf59f61516581aa3cfa4bafb4395e4a703fd1588a2ec6878225b26675"),
        (47, 1752147434, "0.479999952", "4.166665", "0x47353da8e6c9539865f4d2a5c6f3bcb8e64d7697e0f67894820e11e90f361a8f"),
        (48, 1752149804, "0.5699994984", "1.754384", "0x736d9e71b648396c4d341d4fb5785510f1372447489215df93d00a0cb28dc902"),
        (49, 1752150218, "0.51", "22.27", "0xcbfa3b1b5285f83638b9e66eb9fba7a648dfc8bb1f7b0a6d5444ed40fac3c1a0"),
        (50, 1752152300, "0.5199999896", "3.846152", "0x2435de7532a0a99013dd7ad55fb53bbc05e585178e32d4e07a5526c25bb3dd04"),
        (51, 1752152866, "0.52", "1.923075", "0x9140583be1b265964aecf2397b4e8ebfd9265abcb5e9e2d8d8e064a2c3918ca4"),
        (52, 1752153652, "0.5199999896", "3.846152", "0x322a9147afe5c62c313471fa285a6a0deed085178175c195a4a381257d6e8bac"),
        (53, 1752155454, "0.5799999014", "3.448273", "0xe948793382fdf64b0c193832a6224c360abb19b2ca31301024f276f757c05bbc"),
        (54, 1752156844, "0.6499997942", "4.615383", "0xe0eee7c35d8aac116f628d1bdb8274cc82c99156d3d4749cf4a1a6df77c21903"),
        (55, 1752158752, "0.59999994", "3.333332", "0xf3e9c3262f31030d17f183a25f54a14777aab9bb9e671bf0b11b3a72ebc5c38d"),
        (56, 1752160434, "0.6099998597", "1.639343", "0xab63b2a4019a1508facfa65bce006efc5aea7299b501eb2d6c66c68e3ca58c20"),
        (57, 1752160704, "0.6099999786", "3.278687", "0xb453a81c8332a2da885cbb9273f7f01e4081e6c31d2737640f42487089b1cd5e"),
        (58, 1752160848, "0.6199998512", "1.612902", "0x23f655a41c40dee615806831dc5b4d8556c96873a39f2a667441d3eae7613171"),
        (59, 1752161472, "0.5599999253", "5.35714", "0xb0dcbb587fd798f80388afda882d954cbf79f664e319e0366c79c7a929b3c697"),
        (60, 1752175231, "0.5006976744", "43", "0x5e890cc759a2ca0d9bd589f1b1670ac62df72c5a4cc6e755e7013663a018804f"),
        (61, 1752175321, "0.51", "15", "0xb433479752e4fd70a43ed5000b33320aad09771da895afc528ac40fd90f57bdf"),
        (62, 1752175790, "0.52", "28", "0xd69d74fe95aeaf985e83be99cae6e306ed78b25d9c4f37679761cf49cc2a12ef"),
        (63, 1752175818, "0.510108", "25", "0xafccd0d450b02e911c99a663c758de150f78066b451d00298523b2e0973faf0e"),
        (64, 1752175860, "0.51", "0.27", "0x11567e1fb7b77c6b075f02bc583535ab5207fcd35ecd0e4627864a8471810755"),
        (65, 1752175940, "0.49", "25", "0xd478a6b1a11f3ae19bf8544e401766802e6d1158e18e9704c1308ce53fbe6ea4"),
        (66, 1752176094, "0.51", "267", "0xc430164f81ae2de51a3a61ac9c1f2b23356b46af569e3df5f53b768e0357f581"),
        (67, 1752176685, "0.51", "24", "0xe7f2a036f11802f5ebe1968e48a1b71ec411e06590c60e010fcafaa957684b2e"),
        (68, 1752182250, "0.4861538462", "65", "0x1a7b0559640f160fb7082de72bcc1932666f012f1b2f4b8c21e95479021ec8db"),
        (69, 1752189873, "0.51", "25", "0xa8bf1d670a490dc009f7705f9360a80777f7a6d14ff56da9130fb05a1fcf77e6"),
        (70, 1752190510, "0.51", "25", "0x25d734aeda7e0ce4ea4f29a8c193cdc9580abbbc6e357afd651aa7a056217c58"),
        (71, 1752191400, "0.44", "16.51", "0xf291c1db8eb079b0c464b7676c7441099ee3593bfab140d33ce577735aa85327"),
        (72, 1752214965, "0.5", "10", "0xb9e256506bb07c57d026525bb309d8c863590c13d5aacc2bf9496a30294f244a"),
        (73, 1752222794, "0.51", "14.27", "0x9deab508a826f9632621154ea9c68c9b9c2cd3acd5d585cc6e748c581ca8be89"),
        (74, 1752230514, "0.5099999341", "4.705881", "0xc10668313f432215d80a7e21c093a05d4e276211b3647b29d2d23d146f0370b0"),
        (75, 1752233766, "0.42", "5.38", "0x015d75ebdf9339c29434d28f42e895f05ef4b844e08d914b40c219a69631da15"),
        (76, 1752316057, "0.42", "40", "0x5e65f6fd2e197348ce066ea64e9ba9d1aa2f3123c7f1837d5dc4e2b135cdd9bc"),
        (77, 1752340460, "0.44", "99.99", "0xcfc065d115c65e5feea69b03ccf1618f903dd1b27d8632aa65847c081ea85729"),
        (78, 1752340663, "0.45", "25", "0xe49eb74da48ea411f9dc146e73a1926e634b9b14dcd1fd3ad06fe0795eebcc49"),
        (79, 1752349551, "0.43", "25", "0x0d0b58c7cd9df21026a820b6e7303e8217b5605cb7b3cb143b45a91bd1a4cdf1"),
        (80, 1752349831, "0.44", "16", "0xc0d896fdb093c406240c34d78a6fbd9a5b95233c4186843611f4f17fce47fc25"),
        (81, 1752355126, "0.44", "9", "0x728cb414109ee26eca884b46cd5e0a942f211efb33a2f87326ba0a0be4a57688"),
        (82, 1752356084, "0.4043808344", "104.98", "0xd1340e311a69677d03e4db708f705ff3eb466507f7d26464ba2ee5e3b5ca6f69"),
        (83, 1752363290, "0.44", "16", "0x1d40f95b05cceb0363eef4f42b59ff1f62087f3d2ca1220d1ed0b1eb49240569"),
        (84, 1752381121, "0.31", "3.94", "0x8a79e900cfce2713f34fb234424b839bab2882489410365360660eb5e88d909c"),
        (85, 1752390422, "0.43", "126.54", "0x8b85edc5cba4a0300308776a5895ed3bdfb41c802f8db0823acb1061ce634c83"),
        (86, 1752447961, "0.5", "18", "0x47cf07c8c99a07c4f3ea1915db80a2c00eaf8e23ea89a286eefd7de219a7463b"),
        (87, 1752448499, "0.51", "25", "0xab72e470838cb1d4cc384b235ffb5d7bfcc3734dbc72b42666a742b26993a988"),
        (88, 1752449177, "0.51", "25", "0x64753f6ba5bcc5ef14e4145d101dd672ff9bfb32056cb8e9bc547f6aaabe779c"),
        (89, 1752449683, "0.52", "30", "0x849733aae9dd056e2c53b1baf3d9ddc026922c43b9dba649839bbb878ecb9a80"),
        (90, 1752449811, "0.54", "30", "0xf5d311a05da66b720369ecaee495296abc96767d8fb80c51a73cd2b75582bc87"),
        (91, 1752450285, "0.55", "0.97", "0x505b821495563e1c3e85c0d07f30d08dd3d561c4dc2d992468771df6b8c2fd14"),
        (92, 1752450473, "0.54", "30", "0xfbc6b3ae431735d74c31b18562e89e71ecf5a683399081a8c8070772914ecf14"),
        (93, 1752468322, "0.64", "5", "0xdca7d5f8b2e5a0e470f2f603b4fa2bf2174d87606f14bad0ce6c04423ad1331c"),
        (94, 1752481439, "0.6999999898", "19.642856", "0xc91069c34d58f086a798b5ee4e0cfca8c371ad794ea936bd5011de4cdcb1d5dd"),
        (95, 1752500601, "0.7", "0.35", "0xfb02154500a31801f681e33671e22bb13747bc8076f143ff3becf6e1bd2dddc7"),
        (96, 1752506887, "0.66", "2000", "0x3bd7d59003bfb67fbd2a0fc41739badc14bf241299ca5edc10bd3d286669eeab"),
        (97, 1752507059, "0.6799999999", "1999.85294", "0x7f1973db50fc0a93f59d3168df1564ba3152a1bdae6271d1b23eabc6e8b5ab94"),
        (98, 1752522137, "0.6857847774", "1807.71", "0x57ce6076a83ad001061a0bda7474c8c9815e9f63296ff6e6c8940b450019ab33"),
        (99, 1752527709, "0.6982367751", "141.785713", "0x05b00970b01ae3b5b32fee5362cf1caac26c1ec198b6dd37020e9cbf9ed7fdd7"),
        (100, 1752528067, "0.7199998416", "5.555554", "0xdaf696b27ae0767108619491fe2a54f875878ec6426de77b0627b0491469bfe4"),
        (101, 1752539767, "0.6899999586", "1.449274", "0x3eb619d1bc5b49d6a533b8cbe24d7bc8898f4fb7691f3e85343a048cb288d0cf"),
        (102, 1752545139, "0.69", "5", "0xc0e79021d668abe2ba53a85173c0987e2154691f0ba179f78c979eb14c39a7e5"),
        (103, 1752591225, "0.68", "25", "0xdce2c80aa8f5ef5f99f12a7b6bf5e75e2e38883c3efb51adb9e6ab8f8a9e00b2"),
        (104, 1752598508, "0.66", "1920", "0x9e91b74d026867859a6022277343fcc8648152462241d9eab690dd712fd413da"),
        (105, 1752603177, "0.6599999842", "15.151514", "0x3df10b918838d89f6769d947f7d0e622eca27671372e45ac38e4972b7550f687"),
        (106, 1752603267, "0.6599999842", "15.151514", "0x2c5c03ad1c072ece537cb72944fa4ffa90cba24534f6334cc5df616ca5871fda"),
        (107, 1752603463, "0.66", "100", "0x0056e2da106c94e6a86feeaf551906109c1a9e5d3c7c3b28a17cf2e318d45434"),
        (108, 1752617421, "0.6699999974", "22.835818", "0x1f19dfa5b7a6b72e03ba7253e455b9a42a4bf209fc59d364b6e0afa2b5302002"),
        (109, 1752617769, "0.6699999196", "1.492536", "0xd3feaeee64137e5edaff7a555bec4cca5b94700a6f73b928206a0a6a6d979907"),
        (110, 1752617887, "0.6699999933", "4.477609", "0xceba6eca52785c8886999d0f1691001d6ee4ba090dc0b35111fbbaf2000751c4"),
        (111, 1752617925, "0.6699999821", "17.880596", "0x154f10da1b42b18fc7b947d83d929d447accd4aba5d605fc73eae4616d5d1447"),
        (112, 1752618041, "0.68", "199.88", "0xf789da8022ba43c9543f80ed42029608df73c7b68679dcb72a54a41b85c8b757"),
        (113, 1752620475, "0.6199999948", "58.064515", "0x6c34852063e14a4cd1c0702d425fb19a2723ec229f96a02d0ef73ecbe525bca3"),
        (114, 1752620529, "0.6199999927", "43.548386", "0x479ce6f652576d9b376425f158f0e17554cfa2d9b40728323e006eb5d3ec33fd"),
        (115, 1752621267, "0.62", "5", "0x8f4f88ac6ee6564c80ad2163020258a6b48cc489c169eaaba182a08d9a63bc5c"),
        (116, 1752622999, "0.6980342422", "157.7", "0xa29b4dc25667046088e76bf018c1a3ca8b41594db8c0bf4da5a69ccc33d0bca8"),
        (117, 1752623015, "0.6999999685", "28.571427", "0x7c7e0ff5735fdb194916b0cab5332245e59278897c88dce284b982c6aef797c4"),
        (118, 1752623119, "0.7093351835", "713.43", "0xc60511d9226fc75e9ecd2fee414b1271287fea9c5cfa08bb13ae411aa3a27d02"),
        (119, 1752623501, "0.74", "496.25", "0x5b8d3b9070f8206ba26b5922d9e46d91bf9f4d1470c9e64060ef42443723e4a3"),
        (120, 1752625105, "0.75", "50", "0x2ec5012c01fae330d843c4bb72b20db02a750f859c05a9afefd9134e9057f143"),
        (121, 1752625269, "0.75", "80", "0xd307203a2d7992d744139ff78dc1e8615efe53f212aaf5ab88b6244c57970936"),
        (122, 1752626733, "0.7784635674", "90.99", "0xc63a38fe81a8a79278c4afc5469552dd4a4fb665a3377028aa5e353ff08bc153"),
        (123, 1752626927, "0.8067272727", "495", "0x09e74087438a101aebb38d2c1d588b321dddaaf5d89788545f9ac1d3f4bcf36c"),
        (124, 1752627033, "0.81", "1.44", "0x7a5a4963c7d4c6f84a531956751e6cd5f72882424ec64d3a1838fc80fd563928"),
        (125, 1752627473, "0.87695", "200", "0x0abf531409e6ac75217ade0c5cd2f6a89ddc88e6acb0eef0777067d5e89e3c19"),
        (126, 1752627477, "0.88", "5", "0x90a763b1c23b1ad7e46683b48c70e5842c58ca88e30c081f9bc9a31bd68ca9fb"),
        (127, 1752629929, "0.98", "2.69", "0x92779803577b51dc2f8450957777817accac62b4a08491d1e492e38992aff264"),
        (128, 1752637434, "0.952", "30.3", "0x4cb0e05ea2560b9ab14a8dd8f5d10597f86003a8d6d5f57c6ba4ef07ff8de891"),
        (129, 1752638478, "0.97", "60", "0xb24a68bf1a1ba966adbd2373d604f8507aeb011282c7a023c5b31d30e905b8c0"),
        (130, 1752638504, "0.98", "500", "0x7f285718f26de7bf207f417cea5079dcd6d9d77fdb98f63ffd0c319d49fefdf8"),
        (131, 1752638522, "0.99", "1190.14", "0x6cbede1cf92b7647864a31b6a35352c1952e5011d3dc8894923acec713be3718"),
        (132, 1752640290, "0.98", "8442.87", "0x21123bad891ca6441bfc237e57b291a10c80d22524b25d119a1b1301c4b4eecd"),
        (133, 1752650499, "0.98", "6970.42", "0x1693019d205b00b80e8fee8e54c337ad83b908e423138c7521771a9c8efb89e9"),
        (134, 1752652663, "0.975", "29.99", "0xc279f782fe54bdbd8b867648dbf4b1c281d34852b533de9361a9cf3fe8e7403b"),
        (135, 1752652683, "0.978943414", "529.99", "0x38ff3fef9368a66f9046eb8d82499e5ff38dae416ee49770b7cef83d6fbb10de"),
        (136, 1752652709, "0.979", "40", "0x7a28350cff3f1e40dbbcf4e800fffaf7e23bc429acc9b23b0b5ba24c4085730c"),
        (137, 1752654639, "0.98", "4586.71", "0xf78eff0a6d177713278a6b0621334313b3909e2e1226b7600c4f5fd080ecaaa4"),
        (138, 1752660584, "0.9789999995", "26.241047", "0x062b5bcd2310a1effeafce4578b774720119691f60dc2c956076572105be4503"),
        (139, 1752663827, "0.9662", "100", "0x5f323ae75d4f5ad4a6fc026041acc057f978a901024312d72f014175f6561d8e"),
        (140, 1752664858, "0.9570456621", "219", "0x587dae18688c898b1e7ef740b5b5361fc169a71d9e83fe8eb9c05423b3bf2a1e"),
        (141, 1752667328, "0.97", "10", "0xcbc981129b89fc5d546fc6f8a9f9fbd19e293d6047bf631f7ca620e955f53730"),
        (142, 1752667356, "0.9771019916", "79.009142", "0x881adbb0db521c4c56681afc612364404ef4dcac98978064918023f6870341c8"),
        (143, 1752667982, "0.978", "40.29", "0xe02cba0b40638d7ee856134ae03c4b8bb73c014f9834e52073cdbec611249f37"),
        (144, 1752670994, "0.968", "28.57", "0x8ac84dfc95643906f5a345ee9a3ec4d9f1d8465e5aa3cd0fb301419b128c6435"),
        (145, 1752674556, "0.9765722187", "16.475952", "0x3678e116d199305f8ecfd1ef79f1488b0b9fbf85b58c43f207f1554eb2677cd0"),
        (146, 1752676978, "0.975", "9.7846", "0xaa263a7f30d465236f1a50ff0fa9d2146792c4be0ee2222696dcba8c390d0b3c"),
        (147, 1752677466, "0.975", "205", "0x6a055420512135dd6b5687ea4c77cba671150a64deb6c54c4cdbe98c3f3eb725"),
        (148, 1752677476, "0.977", "204", "0xb0d3d942213040786d26b9a74c80293181ba97eae5d8d4fecb28322f14165e02"),
        (149, 1752682008, "0.97", "5", "0x05fdf4ec271a346fd2bfc760bd67711065e11f0017eee93950df16f80a60a8e2"),
        (150, 1752693118, "0.977", "59.01", "0xdad9f577ada9c8814c35334b5c59a3f61d3ba7510f3f2fb0256f7a387217903a"),
        (151, 1752693140, "0.982", "203", "0x91ad84a30b77c10ac905fea48940ab0fe8f86ddb39a9d55288c5c06c08861bf5"),
        (152, 1752700514, "0.99685264", "1000", "0x64b617fa772243088cccf1bc284fcacb6b3338e4929703a10478e477e2fe4e97"),
        (153, 1752700616, "0.999", "2807.78", "0x9c6c55ac9c2f31f213c733b68b5eb96d506db76750b3595f62168bc5561cdf9d"),
        (154, 1752702750, "0.995", "95.48", "0x9f33bacb274b74b58baf4efc53966567b28c5004348857e0f5e5e215aaeaec68"),
    ]

    fileprivate static let retained557372No: [RetainedTrade] = [
        (0, 1751237963, "0.6451612903", "155", "0x5dbfd675fac4f10c7527fc2227f1f04dfeb6732cfc09a451bf95d607a219f425"),
        (1, 1751246364, "0.62", "30", "0xd9ddd7bc649ae75a251d1a1aa18668e99dbabe5a452ed66958b0776958787b77"),
        (2, 1751253926, "0.6", "5", "0xb7493f19cd9662167154b2828faf541b260c6444576bbcc393710dfa6a2d7c3a"),
        (3, 1751270736, "0.5499999436", "7.090908", "0x2a98607446e5bc728830f5682c8362865b43385335eca9ea2224b526dece7bba"),
        (4, 1751275800, "0.43", "100", "0x825b7dbd60994bc161f2da63ec7fa7728876a69304ae0910e3bb21a1134c5f64"),
        (5, 1751296011, "0.4799998272", "2.083332", "0x41832c12962b5493eb98d98c79d0b98011e576779d395bb2ca12a0045cfd2136"),
        (6, 1751298003, "0.4699999915", "21.276594", "0x0a31c657714ae2587e846836a02a286504eef89bd33481785fa6c5ea7a9c44d8"),
        (7, 1751315468, "0.42", "104", "0x4662df19e74496453d429cac159f30537b9e28c737ebee49a86de80fb232f539"),
        (8, 1751315860, "0.42", "21", "0xce73d15fbaecfb0b146793bab2ba844d80fddae84d76482a7bba9a339cd60a4d"),
        (9, 1751315872, "0.42", "21", "0xadc89a3002e4f94cad0ede67e6a00eb81dccc4318110459a96373bb5acdb9f51"),
        (10, 1751317250, "0.39", "110", "0x5d18ba2cd9c1972d97f886db06626fd9a9d454f10f2b9053798ad82fed7e3ba9"),
        (11, 1751317276, "0.39", "113", "0x6c2fb4e1d6291b3c9187ad7dc0634be8cc8fdffc6865c760ee91beebb47f931b"),
        (12, 1751317280, "0.39", "84", "0xdbd9abf2d7d127dc50573fdd344839ff6e2d24299ee4f817aaa57ac1a5b290d7"),
        (13, 1751317394, "0.4", "57", "0x1491fb1c76ecffe1eb6b84e413fdb0dbac9ca86f2569d0cee8154ae083eba104"),
        (14, 1751317480, "0.39", "100", "0x2a8824888345ed636be5d5e58f88733de2fd89271529631930004ecb6ba3d370"),
        (15, 1751318498, "0.41", "0.72", "0x1bd95419f1de5b2812fa893d6dfe913a334aa14b53075085b52ffdfced364c6e"),
        (16, 1751320790, "0.4499997975", "2.222221", "0x04d50cb22c0f49ebfb1d421d4d9e69c90e7b434df7a0b9ca0665d1ccfe5f71e6"),
        (17, 1751368843, "0.4399999648", "11.363635", "0x52797a34f0b908e5619b87e3e4fcc81240ad3eed82a1e55d1b55ef9f73fda1f9"),
        (18, 1751372215, "0.44", "3.2", "0x3808d3e7f8c672785b277f33fc5728089aaf801d5facf49b86516925ff29effb"),
        (19, 1751424791, "0.45", "55", "0x498e72822a1d15b7c88e528ce707bc6d02cb4d4579d3e328f2678f162cc5b667"),
        (20, 1751424869, "0.45", "55", "0x70b97ad04e8513b513ddddbba8362308e3e2d635a86e003be0cddec7b38a8afd"),
        (21, 1751471461, "0.4", "4.49", "0x664092decea2825f85176526c099645e38db3fca5ce353b3a2c2f15717c74ad2"),
        (22, 1751475173, "0.4099998237", "2.439023", "0x19fae564b3a134d2ad0f01806be615a48f0e92ae4807f7656cb897748c4274e4"),
        (23, 1751588679, "0.41", "155", "0x81177c3b942a8f0f1417b3152c1887a04c7d5a1854afca181dd4e04893ef66d5"),
        (24, 1751649980, "0.41", "300", "0xc29a193038a9f8ba74d6eb0491e5b3b2c8fa80fa8fdb76a85c53b66cd87f1944"),
        (25, 1751747879, "0.41", "450", "0x832624edd47f6ccb7e40a03721021ab9e045efa8b0db0002d2c0107f032e4c0c"),
        (26, 1751958639, "0.4971491227", "326.3206", "0xf149aeebdbcc0921b8fc2dc2e73c3431a6ec5d0a7bc77732a3275a5e6511868f"),
        (27, 1752008229, "0.4870105771", "1616.7", "0x3db99e39194fc97e7d6bb0b15fc3dda080f42132ba3c6e24f75bb254338d6df8"),
        (28, 1752077869, "0.47", "416", "0x5d9588efd47719f1117685866bbe4b39045d4452d560a99ec9ec677c6ef8ba54"),
        (29, 1752085041, "0.43", "14.2", "0x376e71e4756ffe998cc78c35604d3e92ae87baf024fd1d3a59ddf73039852cb9"),
        (30, 1752097701, "0.55", "6.27", "0x9b19c4b0d1346ac700081d71ff4f094d3686c216fc3e0d0cf69acfcf39e1add0"),
        (31, 1752130219, "0.55", "41.99", "0x0c36a264392a71854db01518ab377bc0f6931248b57bbece659d06efedb773cd"),
        (32, 1752135933, "0.52", "25", "0x117bfc5246d49814c37c9aab6cfe4544aa73b0393549c5ca2498732ae9bfe179"),
        (33, 1752135941, "0.48", "23.26", "0xd81d97b56ba2a2bbf4762356205777db4c9caa45afc9113040c89eddc3d0a84c"),
        (34, 1752139810, "0.5899999675", "3.389829", "0xd860b9b38179366bbe7913785505b433c40598ddcbb867eea81f7c62b2333f0a"),
        (35, 1752144568, "0.5399999712", "5.555554", "0x4f53abb8ea4fe31e3c992f4be59ed947f5fb17ecd317decc513c6a55f7a6d89e"),
        (36, 1752146462, "0.52", "14.19", "0x701258ae984b1d3be0f9cab8bb3df586ca8929ff3bd2bc7e941d20b630578f10"),
        (37, 1752149368, "0.5199999896", "3.846152", "0x6233a0645a665c3adebf475aa81f55a7b8a1dbf1be5bcacb5cfa6e019c8e19bc"),
        (38, 1752150204, "0.51", "269", "0x4c7ce58cc217ec919821f195fe3c54994171315210f66c25a5dd9d277d014236"),
        (39, 1752150246, "0.51", "227", "0x5699d8d81ba96966df041c76687295561d83717c3f3b1911137e252632fcef02"),
        (40, 1752151442, "0.55", "1.81818", "0xea5a2df3e486c08b96aa00a172ab81853726a5f3da3d73f2df53d7f4e57e0143"),
        (41, 1752154086, "0.59999994", "3.333332", "0xe5e5443ad9bf618e05a9d9a269c6b86ed08afbf13f2a0b46f4242e3c436498ca"),
        (42, 1752154526, "0.5499999633", "5.454544", "0xc8ed947af5fd6b5eb97c50c25a7ccb51468c06ffaf09d9222408819a69c07cfd"),
        (43, 1752154816, "0.5699998233", "1.754383", "0xdda7690420cba7ab9d6ff312284f3aef0048e465563606c11e6eadd40ce75cbe"),
        (44, 1752154846, "0.6", "5", "0xb687faa5e128bfb77a93ea599c5bb5a9b81e9c039d7f8254ddd70a303db7b86a"),
        (45, 1752156384, "0.5399999784", "3.703702", "0xbcb1d98075ce1fcd639062b3c64a6beb89e2f6456bb3de0682bdc9a9bb24c76f"),
        (46, 1752156768, "0.5568961917", "1.795665", "0xed1a0f75a2216d7399eb40deb0853fc185724caf3f56e79aa459e07a7996051c"),
        (47, 1752157348, "0.5599998432", "1.785713", "0x40931428a0618520577650dc4bb8026baf21ac6d8fc0dcf89c791148a66cbd75"),
        (48, 1752169642, "0.53", "52.01", "0xc20da1aab1e4cecebeb3065ca0426bfc877dc352e47e5a071bbc6f2fc0ec00e2"),
        (49, 1752177907, "0.51", "25", "0xaa91c524b35ff454dd6d1607d99d8ab2f5a54e1eb4b29d970137c3beef390a3b"),
        (50, 1752179419, "0.52", "275", "0x7dfebaea939c7189aa03e4480b640776664a0d358aea27bfcd4042a1b822b590"),
        (51, 1752185268, "0.52", "65", "0xe1f6c9629da1561ddbda14545f6f322182715bdb8a160b6b13d60a724950f05b"),
        (52, 1752185478, "0.53", "74", "0xa1f34ffe6ee6002e1d528e9534e96e242e6dd3defc58049dd81673d446f38c31"),
        (53, 1752185518, "0.53", "80", "0x5a4a7799efb1fb5392a6b9cb3afb13506cae2434d2c7cf4480a740c6cbe1555f"),
        (54, 1752191169, "0.5", "190", "0x5f63ac7a0df994e6bc4e186131537a90063687ac6a8dcd9de704ae24b73269bb"),
        (55, 1752192406, "0.48", "40", "0xa00ac6cd54ddf39afae6110f9e9565ab265d26662941949925f34a8ff8966c17"),
        (56, 1752201692, "0.52", "33.49", "0xeabf01677f72464b0937d2e5e738740d8e7927bf0646cb50fa4cf4f6078fe8b8"),
        (57, 1752202551, "0.53", "16.46", "0x11c55db28da62d77581261eedaab8e1fc317dd6ae1684b450ed8fa5cfb158b09"),
        (58, 1752202575, "0.53", "10", "0x67882ebad7b80d7e678f9f008b43421f1213bb214d3bf390ca8d5888b437bb90"),
        (59, 1752240784, "0.5", "10", "0xc3394bdffac9b00c34071b7b48592d1b0e0f585192bd37449deb9eeeb789573c"),
        (60, 1752278960, "0.54", "5", "0x3fb2025de4468dee164281952f108a40231e63b5cadde0172fc0f2e58a94714a"),
        (61, 1752279022, "0.53", "43.6", "0xe3464fc1b52a71fd06d24aa1aa90d8805859ade92bd5efff5420e7378f6964bb"),
        (62, 1752365796, "0.53", "30", "0x26067d80a8b415351319abc1e0d2e45cf8294bc1d52efa22007114cd73977c67"),
        (63, 1752367950, "0.6075384615", "65", "0x48a24eac090ec2adddbd0ea7b1ca929815468fd0e234e0015246a2d7371041d9"),
        (64, 1752373933, "0.61", "1", "0xf859be3806fced8c6519c127a2eec8c027df3552c61a2ce93834e69986009cad"),
        (65, 1752376283, "0.6838453888", "29.246374", "0x221513d0e0ad6d28b2a9ffd9f55efe3cb185aa327d4df0dbad031766d01c03c7"),
        (66, 1752420181, "0.6", "40", "0xc170cbf745d6d60179a6613bbd55f8a9d335a6bf3fc742e9fcba28331b70242f"),
        (67, 1752431177, "0.6099999985", "163.934425", "0x954b224a3da7311f5b1cbb0996579227c391473d5d0cfd34e7bf522df5188f2b"),
        (68, 1752449723, "0.4593172043", "279", "0xec8316db18d79d9fdf6735b491c72c5ba95991bc65487781f7b253611f968074"),
        (69, 1752450245, "0.45", "380", "0x322f4f0e1c2285f0541148e24f43641cd8e61dc1853e58e15dc8cb43ab4f9d39"),
        (70, 1752470167, "0.3699998631", "2.702701", "0x727d10974656d0e2f3229fd4a5fd5cc0d63a6b5c32ef60d81e0588fa1ef782d3"),
        (71, 1752470685, "0.3799999012", "2.631577", "0x6467819368b58a49a203121cfeb2035b46875f632a599a148da92873f9412ba0"),
        (72, 1752545285, "0.3316666667", "30", "0x70ab9556bf80b66cd97f895433e6080f6201e60e91225ba8b2b26160d391cb06"),
        (73, 1752545823, "0.34", "44.88", "0xc11e92fc0d32cca2bed6d990485f3e202e6dbcebf0610be132dd612753a1e233"),
        (74, 1752596210, "0.34", "80", "0x17fed9e2e67ec35304c980c16d217caba66b47934ba4069a81f2a66b6bd7cbd6"),
        (75, 1752603229, "0.359999987", "27.777776", "0x5b93e18ce58f3b7821bed195ded14c1a2693d93d267728a241392b15634b2bda"),
        (76, 1752603469, "0.34", "27.77", "0x1561fccb6bc76856385b2bdeeab4e11309d819269fb754d583b5d968096b4b6d"),
        (77, 1752618425, "0.39", "22.84", "0x1a36ca7976f2621619ac7325ae7a84b6deade457976dcb52337b86578fb5b8e9"),
        (78, 1752620169, "0.3980742834", "123.85", "0xa3daf8865b4306408da3b6b3a2a7e8b1b7075406c36211ea53f5853ddcaeaf8b"),
        (79, 1752624041, "0.45", "10", "0x9c8243f71acde08fe958fe4d0b5be68b8f92ec6e50705fd1cd5f4dcf16097c8e"),
        (80, 1752625113, "0.25", "31", "0xc745ff3d20e9db4923f5e9fd9ad463d270364745be4e41b504111ab10d7a5df3"),
        (81, 1752625405, "0.25", "439", "0xd1e0bf639a4494ade3deb4f1bb0fcb7db0f4ad9ae056f09b81413ccd6de9d302"),
        (82, 1752625761, "0.2", "10", "0x03ae3cbd1073e87d9c72cdccc85f5d788beea0b6bdb38f8f3a651faf68059d74"),
        (83, 1752625761, "0.4271030993", "252.96", "0x31011f4b6b093d020b700ea3a8aee65d1ccf98be86e7f5842c777f9e2230d773"),
        (84, 1752628059, "0.02", "7.31", "0xeb5ca6aad15b3fa87a644976eeada6f5a28c658f4e36291dc0215f535448ca29"),
        (85, 1752628209, "0.05", "21.93", "0xec16af920de0e774675d89ead20b94bcf69c5eece94d42272441aee2e82aba71"),
        (86, 1752652711, "0.021", "2000", "0x6b46a4828ddfb0f64a2b173381ca62accd894a8069cd560fcb66236ffa3dcd69"),
        (87, 1752652727, "0.021", "5448.27", "0xe28bc80168ff474384baf19abafac62aeab816f852efd65173f09cc242840038"),
        (88, 1752655189, "0.02", "117.39", "0x3e0f4be3c5c28e2eca6ad43634afcc3d0439d630a8e11376cd741d35dc05fd98"),
        (89, 1752668962, "0.026", "30", "0x7302b1bc4ce4e0bb3f38e4d129064e028b6b58727e3ed9bdc3fa40a00d00f757"),
        (90, 1752669186, "0.029", "10", "0x80d404967743637b713c6b98a71aa2346d6fce93b52c55c9eb94dc0139ea85d5"),
        (91, 1752675222, "0.029", "29", "0x3a77e396b1733e95f297100e9bd7834a5eb530ae4ad1b7cba2ad720d783d1f6e"),
        (92, 1752697148, "0.021", "106.61", "0x53d604d62c40163572c2bac5c5c197188786312c6b7cabacdb81d085aeaf293b"),
        (93, 1752697946, "0.027", "30", "0x9c35fa4a381caf923650bdff3cc38b78f09a63e612d51eed95fb81c9fc2e461d"),
    ]
}
// @@END GENERATED FIXTURE@@
