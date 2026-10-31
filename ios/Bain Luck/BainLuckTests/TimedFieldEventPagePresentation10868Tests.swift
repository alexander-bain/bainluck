import CryptoKit
import SwiftUI
import XCTest
#if canImport(UIKit)
import UIKit
#endif
@testable import Bain_Luck

// #10868 — the timed-field page assembly, exercised with the retained
// Olympic women's 500m capture (route `olympic-skating`). Prepared model,
// binding and interaction checks; NOT RUN (no build, simulator, XCTest or
// typecheck grant for this package). Nothing here claims a rendered fit, a
// native runtime, VoiceOver behaviour, a device, an app route or a
// production binding.
//
// RETAINED FIXTURE: the approved `skatingCapture.json` (source sha256
// 1cfdd4a6…5b84efd) — Winter Games 2026, Speed Skating, Women's 500m, event
// 200646, 2026-02-15. 36 gold markets / 72 original Yes/No sides, 3632
// strictly positive-size 0 < p < 1 trades (1271 before race day, 2361 later;
// 40 populated side histories, 32 absent) and 29 reported finishers (12 with
// no linked gold market). Every block in the fixture extension at the end of
// this file is generated mechanically by
// `/tmp/cli-10868-skating/gen_fixture.py` from the source file and verified
// lossless by `/tmp/cli-10868-skating/verify_fixture.py`; none is hand-typed.
//
//   retainedEvent    one `key|<JSON literal>` line per top-level scalar, in
//                    source order, then `alias|<key>|<value>` per identity alias.
//   retainedRules    the one rules text every market carries, line by line.
//   retainedMarkets  one line per market in source order: id | name |
//                    condition | predicate | providerURL | resultID (∅ = null)
//                    | placeholder | rules key | Yes token | Yes won | No token
//                    | No won — each value the source text verbatim.
//   retainedTrades   an `@<market> <side>` header per populated side, then its
//                    trades in source order: `t p size tx token`, each value
//                    the source JSON text verbatim; the token column is `=`
//                    exactly when it equals that side's token (all 3632 do).
//                    Identical and same-second prints keep their own lines.
//   retainedResults  one line per reported finisher in source order: id |
//                    rank | name | country | time | ms | reportedGap | record |
//                    marketID (∅ = null).
//
// OWNER ROLE (TEST ONLY). The race-day cutoff 1771110000 (midnight Milan —
// not the closing quote and not the actual start), each side's last trade
// strictly before it, the featured cohort and its circle / triangle / diamond
// shapes and tints, every window, figure (the approved `probabilityLabel`
// rule), the reader's clock words in ONE simulated device time zone
// (America/Los_Angeles, readable local words; the raw source timestamps stay
// in each original's detailed source record), standing words, selected-outcome
// grade words, gap seconds and gap words, scope
// strings, ids and copy are the owner's, built here in the tests, never in
// the product. actualStart, actualEnd, actualSplits and projection are null
// in the source; nothing here or in the product invents one. reportAt is a
// published report time, not a finish. The published result report is kept
// apart from each original's own grade. Aliases are fixture correspondence
// only. The before and final frames are retained; the during frame used below
// is CONSTRUCTED (labelled so by its notice) and never counts as genuine
// in-race lifecycle evidence.
//
// PREPARED ROSTER (NOT RUN): see the `func test…` list; each name states the
// obligation it checks.

@MainActor
final class TimedFieldEventPagePresentation10868Tests: XCTestCase {
    private typealias Tests = TimedFieldEventPagePresentation10868Tests
    private typealias Page = TimedFieldEventPagePresentation10868
    private typealias Model = TimedFieldEventPageModel10868
    private typealias Details = OriginalMarketDetails9483
    private typealias Phase = RugbyMatchEventPagePhase10868
    private typealias Card = TimedFieldEventPageCard10868
    private typealias Stream = StoryStreamPresentation10868

    // MARK: - Decoded capture (test-side owner)

    private struct Trade: Equatable {
        let t: Int
        let pText: String
        let sizeText: String
        let tx: String
        let token: String
        /// The trade's place in its side's source order.
        let index: Int
        var p: Double { Double(pText)! }
        var size: Double { Double(sizeText)! }
    }

    private struct Side: Equatable {
        let market: String
        let side: String
        let token: String
        let won: Bool
        let trades: [Trade]
        var captured: Bool { !trades.isEmpty }
    }

    private struct Market: Equatable {
        let id: String
        let name: String
        let condition: String
        let predicate: String
        let providerURL: String
        let resultID: String?
        let placeholder: Bool
        let rulesKey: String
        let yes: Side
        let no: Side
        var sides: [Side] { [yes, no] }
        func side(_ name: String) -> Side { name == "Yes" ? yes : no }
    }

    private struct Result: Equatable {
        let id: String
        let rankText: String
        let name: String
        let country: String
        let time: String
        let msText: String
        let reportedGap: String
        let record: String
        let marketID: String?
        var rank: Int { Int(rankText)! }
        var ms: Int { Int(msText)! }
    }

    private static func lines(_ block: String) -> [Substring] {
        block.split(separator: "\n", omittingEmptySubsequences: false).filter { !$0.isEmpty }
    }

    private static func fields(_ line: Substring) -> [String] {
        line.split(separator: "|", omittingEmptySubsequences: false).map(String.init)
    }

    private static func nullable(_ field: String) -> String? { field == "∅" ? nil : field }

    /// Top-level scalars as their JSON literal text, by key.
    private static let event: [String: String] = {
        var result: [String: String] = [:]
        for line in Tests.lines(Tests.retainedEvent) {
            let field = Tests.fields(line)
            if field[0] != "alias" { result[field[0]] = field[1...].joined(separator: "|") }
        }
        return result
    }()

    private static let eventKeys: [String] = Tests.lines(Tests.retainedEvent).map { Tests.fields($0)[0] }.filter { $0 != "alias" }

    private static let aliases: [(String, String)] = Tests.lines(Tests.retainedEvent).compactMap { line in
        let field = Tests.fields(line)
        return field[0] == "alias" ? (field[1], field[2]) : nil
    }

    /// A JSON string literal's text, decoded by Foundation.
    private static func string(_ key: String) -> String? {
        guard let literal = event[key], let data = literal.data(using: .utf8),
              let value = try? JSONSerialization.jsonObject(with: data, options: .fragmentsAllowed) else { return nil }
        return value as? String
    }

    /// Keyed "<market> <side>"; tokens still raw ("=" or verbatim).
    private static let rawTrades: [String: [Trade]] = {
        var result: [String: [Trade]] = [:]
        var key = ""
        for line in Tests.lines(Tests.retainedTrades) {
            let field = line.split(separator: " ").map(String.init)
            if line.hasPrefix("@") {
                key = String(field[0].dropFirst()) + " " + field[1]
                result[key] = []
                continue
            }
            let index = result[key, default: []].count
            result[key, default: []].append(Trade(t: Int(field[0])!, pText: field[1], sizeText: field[2], tx: field[3],
                                                  token: field[4], index: index))
        }
        return result
    }()

    private static let markets: [Market] = Tests.lines(Tests.retainedMarkets).map { line in
        let field = Tests.fields(line)
        func side(_ name: String, _ at: Int) -> Side {
            let token = field[at]
            let trades = (Tests.rawTrades["\(field[0]) \(name)"] ?? []).map {
                Trade(t: $0.t, pText: $0.pText, sizeText: $0.sizeText, tx: $0.tx,
                      token: $0.token == "=" ? token : $0.token, index: $0.index)
            }
            return Side(market: field[0], side: name, token: token, won: field[at + 1] == "true", trades: trades)
        }
        return Market(id: field[0], name: field[1], condition: field[2], predicate: field[3], providerURL: field[4],
                      resultID: Tests.nullable(field[5]), placeholder: field[6] == "true", rulesKey: field[7],
                      yes: side("Yes", 8), no: side("No", 10))
    }

    private static let results: [Result] = Tests.lines(Tests.retainedResults).map { line in
        let field = Tests.fields(line)
        return Result(id: field[0], rankText: field[1], name: field[2], country: field[3], time: field[4], msText: field[5],
                      reportedGap: field[6], record: field[7], marketID: Tests.nullable(field[8]))
    }

    private static let rules = Tests.retainedRules
    private static func market(_ id: String) -> Market { markets.first { $0.id == id }! }
    private static func result(_ id: String) -> Result { results.first { $0.id == id }! }
    private static var sides: [Side] { markets.flatMap(\.sides) }
    private static var allTrades: [Trade] { sides.flatMap(\.trades) }

    private static func digest(_ text: String) -> String {
        SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    // MARK: - Owner constants and words (test only)

    private static let beforeDay = 1_771_110_000
    private static let reportAt = 1_771_181_329
    private static let scope = "timed-field|200646"
    private static let goldScope = "timed-field|200646|gold"
    private static let finishScope = "timed-field|200646|report"
    private static let source = "polymarket"
    private static let kok = "1347941", leerdam = "1347948", jackson = "1347949", pergher = "1347952"
    private static let inegawa = "1347946", thorup = "1347947", hiller = "1347959", placeholderOne = "1347961"
    private static let featured = [Tests.kok, Tests.leerdam, Tests.jackson]
    private static let shapes: [String: FieldHistoryShape10868] = ["1347941": .circle, "1347948": .triangle, "1347949": .diamond]
    private static let glyphs: [String: PreEventShiftGlyph10868] = ["1347941": .circle, "1347948": .triangle, "1347949": .diamond]
    private static let tints: [String: Color] = ["1347941": .blue, "1347948": .orange, "1347949": .gray]

    /// The approved `probabilityLabel` rule, owner-side.
    private static func pct(_ p: Double) -> String {
        if p == 0 { return "0%" }
        if p == 1 { return "100%" }
        let tenths = (p * 1000).rounded()
        if tenths == 0 { return "<0.1%" }
        if tenths == 1000 { return ">99.9%" }
        return tenths.truncatingRemainder(dividingBy: 10) == 0
            ? "\(Int(tenths / 10))%" : String(format: "%.1f%%", tenths / 10)
    }

    private static let clockFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = Tests.deviceTimeZone
        formatter.dateFormat = "MMM d, yyyy, h:mm:ss a zzz"
        return formatter
    }()

    /// The one simulated device time zone every visible reader date uses (test owner only).
    private static let deviceTimeZone = TimeZone(identifier: "America/Los_Angeles")!

    /// CONSTRUCTED local clock words in the simulated device zone ("Feb 14, 2026,
    /// 2:45:25 PM PST"); a real binding localizes through the owner's formatter.
    private static func clock(_ t: Int) -> String {
        clockFormatter.string(from: Date(timeIntervalSince1970: TimeInterval(t)))
    }

    /// The owner's frame of one side: before race day, or through the report.
    private static func shown(_ side: Side, _ phase: Phase) -> [Trade] {
        phase == .final ? side.trades.filter { $0.t <= reportAt } : side.trades.filter { $0.t < beforeDay }
    }

    /// The owner's before-race-day reference: the last trade strictly before the cutoff.
    private static func baseline(_ side: Side) -> Trade? { side.trades.last { $0.t < beforeDay } }
    /// The first captured trade before race day. Not an opening quote.
    private static func firstCaptured(_ side: Side) -> Trade? { side.trades.first { $0.t < beforeDay } }

    /// The owner's opaque point id: market, side and source position.
    private static func pointID(_ side: Side, _ trade: Trade) -> String { "\(side.market):\(side.side):\(trade.index)" }
    private static func seriesID(_ market: String, _ side: String = "Yes") -> String { "gold:\(market):\(side)" }

    /// A chooser control in plain words, for call logs.
    private static func words(_ control: FieldChooserControl10868) -> String {
        switch control {
        case .toggleMore(let id): "more:\(id)"
        case .toggleBrowse(let id): "browse:\(id)"
        case .chooseGroup(let id): "group:\(id)"
        }
    }

    /// A reader intent in plain words, for call logs.
    private static func words(_ intent: TimedFieldReaderIntent10868) -> String {
        switch intent {
        case .back: "back"
        case .previous(let card): "previous:\(card.rawValue)"
        case .next(let card): "next:\(card.rawValue)"
        }
    }

    // MARK: - Owner originals (72 Yes/No sides)

    private static func selection(_ m: Market, _ side: String, scope: String = Tests.scope) -> Details.Selection {
        Details.Selection(scope: scope, identity: Details.Identity(source: source, market: m.id, side: side))
    }

    private static func pregame(_ s: Side) -> Details.Reading {
        if let base = baseline(s) {
            return Details.Reading.value(pct(base.p), placement: base.p, provenance: "Before race day · " + clock(base.t))
        }
        return Details.Reading.missing(s.captured ? "No captured trade before race day"
                                                  : "History not captured for this original outcome")
    }

    /// The selected outcome's own grade, from that side's own `won` flag alone —
    /// never the other side's flag, a complement, or the reported finish.
    private static func gradeWords(_ s: Side) -> String { s.won ? "This outcome won" : "This outcome lost" }

    private static func grade(_ s: Side) -> Details.Grade {
        Details.Grade(words: gradeWords(s), provenance: "Original contract settlement")
    }

    /// The detailed source record: the retained predicate under its own label,
    /// the token and condition, and the raw source timestamps with the cutoff's
    /// meaning — never folded into the rules.
    private static func sourceRecord(_ m: Market, _ s: Side) -> [Details.Row] {
        var rows = [Details.Row(label: "Market predicate", value: m.predicate),
                    Details.Row(label: "Original token", value: s.token),
                    Details.Row(label: "Condition", value: m.condition),
                    Details.Row(label: "Race-day cutoff", value: "Midnight in Milan · \(beforeDay) (Unix seconds)")]
        if let base = baseline(s) {
            rows.append(Details.Row(label: "Before-race-day trade time", value: "\(base.t) (Unix seconds)"))
        }
        return rows
    }

    private static func original(_ m: Market, _ s: Side, _ phase: Phase) -> Details.Original {
        Details.Original(
            identity: Details.Identity(source: source, market: m.id, side: s.side), title: m.name,
            outcome: s.side == "Yes" ? "Yes · wins gold" : "No · does not win gold",
            mode: phase == .final ? .result : .pregame, pregame: pregame(s), later: nil,
            grade: phase == .final ? grade(s) : nil,
            about: Details.About(source: m.providerURL, rules: .verified(rules.components(separatedBy: "\n\n")),
                                 provenance: sourceRecord(m, s), historicalQuote: nil),
            beforeLabel: "Before race day")
    }

    private static func catalogue(_ phase: Phase, scope: String = Tests.scope, dropping: Details.Identity? = nil,
                                  duplicating: Details.Identity? = nil) -> Details.Catalogue {
        var originals: [Details.Original] = []
        for m in markets {
            for s in m.sides {
                let item = original(m, s, phase)
                if item.identity == dropping { continue }
                originals.append(item)
                if item.identity == duplicating { originals.append(item) }
            }
        }
        return Details.Catalogue(scope: scope, originals: originals)
    }

    /// The owner's catalogue windows: six markets (twelve originals) each.
    private static let windowSize = 6
    private static var windowCount: Int { (markets.count + windowSize - 1) / windowSize }

    private static func windowMarkets(_ index: Int) -> [Market] {
        Array(markets[(index * windowSize)..<min((index + 1) * windowSize, markets.count)])
    }

    private static func catalogueWindow(_ phase: Phase, index: Int = 0,
                                        override: Details.Catalogue? = nil) -> TimedFieldCatalogueWindow10868 {
        let identities = Set(windowMarkets(index).flatMap { m in ["Yes", "No"].map { Details.Identity(source: source, market: m.id, side: $0) } })
        let full = catalogue(phase)
        let window = override ?? Details.Catalogue(scope: full.scope, originals: full.originals.filter { identities.contains($0.identity) })
        return TimedFieldCatalogueWindow10868(
            catalogue: window,
            windows: CeremonyChoiceGroup10868(label: "Original windows", choices: (0..<windowCount).map { i in
                let slice = windowMarkets(i)
                return CeremonyChoice10868(id: "originals.window.\(i)", label: "\(i * windowSize + 1)–\(i * windowSize + slice.count)",
                                           detail: "\(slice.count * 2)", isSelected: i == index)
            }),
            heading: "All \(markets.count * 2) original outcomes",
            context: "Six markets at a time · every Yes and No keeps its own history and rules",
            emptyWords: "No originals in this window", unavailableChoice: "Original unavailable in this update")
    }

    private static let yTicks = [0.0, 0.5, 1.0].map { FieldHistoryTick10868(value: $0, lines: [Tests.pct($0)]) }
    private static let markKey = FieldHistoryMarkKey10868(hollow: "Hollow: before race day", filled: "Filled: later recorded")

    private static func action(_ id: String, _ label: String, available: Bool = true) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: nil, isAvailable: available)
    }

    private static func domain(_ phase: Phase) -> FieldHistoryDomain10868 {
        FieldHistoryDomain10868(lower: 1_770_415_351, upper: Double(phase == .final ? reportAt : beforeDay))
    }

    /// One singleton run per trade: dots only, never joined.
    private static func runs(_ s: Side, _ phase: Phase) -> [FieldHistoryRun10868] {
        shown(s, phase).map { trade in
            FieldHistoryRun10868(id: "run:" + pointID(s, trade), points: [
                FieldHistoryPoint10868(id: pointID(s, trade), x: Double(trade.t), probability: trade.p,
                                       style: trade.t < beforeDay ? .hollow : .filled),
            ])
        }
    }

    private static func observation(_ s: Side, _ trade: Trade, prefix: String = "") -> FieldHistoryReading10868 {
        FieldHistoryReading10868.observation(pointID: pointID(s, trade), figure: pct(trade.p), provenance: prefix + clock(trade.t))
    }

    /// One original side's own trades — never another side's, never a complement.
    private static func sideSeries(_ m: Market, _ s: Side, _ phase: Phase) -> FieldHistorySeries10868 {
        let before = baseline(s).map { observation(s, $0, prefix: "Before race day · ") } ?? FieldHistoryReading10868.absent(
            words: s.captured ? "No captured trade before race day" : "History not captured for this original outcome")
        let recorded = shown(s, phase).last.map { observation(s, $0, prefix: "Last recorded · ") }
            ?? FieldHistoryReading10868.absent(words: "No captured trade")
        return FieldHistorySeries10868(
            id: seriesID(m.id, s.side), name: "\(m.name) · \(s.side)", shape: shapes[m.id] ?? .circle,
            tint: tints[m.id] ?? .gray, runs: runs(s, phase), links: [], labelPointID: nil,
            before: before, recorded: recorded,
            absentWords: s.captured ? nil : "History not captured for this original outcome", choose: nil)
    }

    private static func sideInput(_ m: Market, _ s: Side, _ phase: Phase, mini: Bool) -> FieldHistoryInput10868 {
        let series = sideSeries(m, s, phase)
        return FieldHistoryInput10868(
            title: "\(m.name) · original \(s.side)", caption: nil, series: [series],
            selection: .series(id: series.id, missingWords: "Original unavailable"),
            domain: domain(phase), ceiling: 1, yTicks: yTicks, xTicks: [], guides: [], breaks: [],
            readout: phase == .final ? .beforeAndRecorded(beforeLabel: "Before race day", recordedLabel: "Last recorded")
                                     : .singleBefore(label: "Before race day"),
            markKey: markKey, comparisonExplanation: nil, notes: ["Only this original \(s.side) token is shown."],
            summary: "\(m.name), original \(s.side) trades, zero to 100%.", plotHeight: mini ? 140 : 320,
            unboundReadingWords: "Not bound to this trade", plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil, details: nil, expand: nil,
            inspect: mini ? nil : action("side.inspect", "Inspect trades"),
            previous: mini ? nil : action("side.previous", "Earlier trade"),
            next: mini ? nil : action("side.next", "Later trade"), inspection: nil,
            layout: mini ? .expanded : .cohortAbove,
            plotAbsence: s.captured ? nil : FieldHistoryPlotAbsence10868(
                title: "No captured history",
                words: "History was not captured for this original outcome; that does not mean it never traded."),
            showsKey: !mini)
    }

    /// The separately reported physical finish, linked only by the source's own market link.
    private static func finishWords(_ m: Market) -> Details.ReportedFinish {
        guard let id = m.resultID, let r = results.first(where: { $0.id == id }) else {
            return .unlinked(words: "No linked reported finish")
        }
        return .reported(words: "\(standing(r)) · \(r.time) s", spoken: "Reported finish \(standing(r)), \(r.time) seconds")
    }

    private static func recorded(_ m: Market, _ s: Side, _ phase: Phase) -> Details.RecordedHistory {
        let last: Details.Reading = shown(s, phase).last.map {
            Details.Reading.value(pct($0.p), placement: $0.p, provenance: "Last recorded · " + clock($0.t))
        } ?? Details.Reading.missing("No captured trade")
        return Details.RecordedHistory(
            selection: selection(m, s.side), mode: original(m, s, phase).mode, seriesID: seriesID(m.id, s.side),
            availability: "Current probability unavailable · historical records below",
            readings: [Details.RecordedReading(label: "Before race day", marker: .hollow, reading: pregame(s)),
                       Details.RecordedReading(label: "Last recorded", marker: .solid, reading: last)],
            movement: nil, history: sideInput(m, s, phase, mini: true),
            finishLabel: "Reported finish",
            finish: phase == .final ? finishWords(m) : nil,
            preview: action("original.preview", "Preview history"),
            expand: action("original.expand", "Full original history"),
            explore: s.captured ? action("original.explore", "Explore original history") : nil,
            unmatchedWords: "Recorded history unavailable for this outcome")
    }

    private static func sideHistory(_ m: Market, _ side: String, _ phase: Phase,
                                    admittedFor: Phase? = nil) -> CeremonySideHistory10868 {
        CeremonySideHistory10868(phase: admittedFor ?? phase, selection: selection(m, side),
                                 seriesID: seriesID(m.id, side), history: sideInput(m, m.side(side), phase, mini: false))
    }

    // MARK: - Owner gold chooser (36 markets, bounded six-market windows)

    private static func goldRef(_ id: String, scope: String = Tests.goldScope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: source, marketID: id, outcomeID: "\(id):Yes")
    }

    private static func beforeReading(_ s: Side) -> FieldChooserReading10868 {
        let value: FieldChooserValue10868 = baseline(s).map { .recorded(text: pct($0.p), detail: clock($0.t)) }
            ?? .missing(s.captured ? "No captured trade before race day" : "History not captured")
        return FieldChooserReading10868(label: "Gold chance before race day", value: value)
    }

    private static func goldOriginal(_ m: Market, _ phase: Phase) -> FieldChooserOriginal10868 {
        let later: FieldChooserValue10868 = shown(m.yes, phase).last.map { .recorded(text: pct($0.p), detail: clock($0.t)) }
            ?? .missing("No captured trade")
        return FieldChooserOriginal10868(
            ref: goldRef(m.id), name: m.name,
            plan: phase == .final
                ? .comparison(before: beforeReading(m.yes), later: FieldChooserReading10868(label: "Last recorded", value: later))
                : .single(beforeReading(m.yes)),
            preview: FieldChooserPreview10868(history: nil, absence: m.yes.captured
                ? "Captured history in Details" : "History not captured for this original outcome"),
            movement: nil, clock: nil,
            result: phase == .final ? FieldChooserResult10868(title: "Gold prop grade", words: gradeWords(m.yes)) : nil,
            browseStatus: m.placeholder ? "Unpriced placeholder · no captured trade"
                : (m.yes.captured ? "History captured" : "History not captured"),
            accent: tints[m.id])
    }

    private static func goldCatalogue(_ phase: Phase) -> [FieldChooserOriginal10868] {
        markets.map { goldOriginal($0, phase) }
    }

    private static func chooser(_ phase: Phase, window: Int? = 0, selected: String = Tests.kok) -> FieldChooserInput10868 {
        let groups: [FieldChooserGroup10868] = (0..<windowCount).map { i in
            let slice = windowMarkets(i)
            return FieldChooserGroup10868(id: "gold.window.\(i)", label: "\(i * windowSize + 1)–\(i * windowSize + slice.count)",
                                          countText: "\(slice.count)", refs: slice.map { goldRef($0.id) })
        }
        return FieldChooserInput10868(
            scope: goldScope, intro: "Pick a contender to keep in the chart.",
            featured: FieldChooserFeatured10868(title: "In your chart", badge: "3 featured",
                                                refs: featured.map { goldRef($0) }, emptyWords: "No featured contender"),
            context: "\(markets.count) gold markets, including unpriced placeholders; each stays selectable.",
            more: nil,
            browse: FieldChooserBrowse10868(
                id: "gold.browse", title: "Browse all \(markets.count) gold markets", expanded: true,
                note: "Six at a time · a market stays selectable when history is missing",
                groupsLabel: "Market windows", groups: groups, selectedGroupID: window.map { "gold.window.\($0)" },
                noGroupWords: "Choose a window", groupUnavailableWords: "That window is not available",
                emptyGroupWords: "No markets in this window"),
            catalogue: goldCatalogue(phase), frame: nil,
            selected: FieldChooserSelected10868(ref: goldRef(selected), words: "In focus",
                                                unavailableWords: "The selected market is not in this update"),
            unavailableWords: "Market unavailable in this update", chooseHint: "Keeps this contender in the chart")
    }

    private static func originals(_ phase: Phase, held: Details.Selection? = nil, catalogue: Details.Catalogue? = nil,
                                  sideHistory: CeremonySideHistory10868? = nil, chooser: FieldChooserInput10868? = nil,
                                  window: TimedFieldCatalogueWindow10868? = nil,
                                  admittedFor: Phase? = nil) -> TimedFieldOriginals10868 {
        var sides: [CeremonySideChoice10868] = []
        var recorded: Details.RecordedHistory?
        if let held, let m = markets.first(where: { $0.id == held.identity.market }) {
            sides = ["Yes", "No"].map { CeremonySideChoice10868(label: $0, selection: selection(m, $0)) }
            recorded = Tests.recorded(m, m.side(held.identity.side), phase)
        }
        return TimedFieldOriginals10868(
            bundle: CeremonyEventPageOriginals10868(
                phase: admittedFor ?? phase, catalogue: catalogue ?? Tests.catalogue(phase), selection: held,
                recorded: recorded, sides: sides, sideHistory: sideHistory, chooser: chooser, tint: .blue),
            window: window)
    }

    /// Every originals surface at once: chooser, window, sides, Details, side history.
    private static func fullOriginals(_ phase: Phase, admittedFor: Phase? = nil, held: String = Tests.kok,
                                      side: String = "Yes") -> TimedFieldOriginals10868 {
        let m = market(held)
        return originals(phase, held: selection(m, side),
                         sideHistory: sideHistory(m, side, phase, admittedFor: admittedFor ?? phase),
                         chooser: chooser(phase), window: catalogueWindow(phase), admittedFor: admittedFor)
    }

    // MARK: - Owner gold history (the anchor)

    private static let keyLabel = "Gold chance · before race day"

    private static func reportedFinish(_ id: String) -> FieldHistoryKeyContext10868? {
        guard let resultID = market(id).resultID else { return nil }
        let r = result(resultID)
        return FieldHistoryKeyContext10868(label: "Reported finish", words: standing(r), spoken: "Reported finish: \(standing(r))")
    }

    private static func goldSeries(_ id: String, _ phase: Phase,
                                   recorded override: FieldHistoryReading10868? = nil) -> FieldHistorySeries10868 {
        let m = market(id)
        let s = m.yes
        let before = baseline(s).map { observation(s, $0, prefix: "Before race day · ") } ?? FieldHistoryReading10868.absent(
            words: s.captured ? "No captured trade before race day" : "No captured gold trades")
        let later = phase == .final
            ? (shown(s, .final).last.map { observation(s, $0, prefix: "Last recorded · ") } ?? FieldHistoryReading10868.absent(words: "No captured trade"))
            : FieldHistoryReading10868.absent(words: "No trade inspected")
        return FieldHistorySeries10868(
            id: seriesID(id), name: m.name, shape: shapes[id] ?? .square, tint: tints[id] ?? .purple,
            runs: runs(s, phase), links: [], labelPointID: shown(s, phase).last.map { pointID(s, $0) },
            before: before, recorded: override ?? later,
            absentWords: s.captured ? nil : "No captured gold trades",
            choose: FieldHistoryAction10868(id: "choose:\(id)", label: m.name, spokenLabel: "Show \(m.name)'s gold history",
                                            isAvailable: true),
            keyContext: phase == .final ? reportedFinish(id) : nil)
    }

    private static func history(_ phase: Phase, selected: String = Tests.kok,
                                series override: [FieldHistorySeries10868]? = nil,
                                inspection: FieldHistoryInspection10868? = nil,
                                fullScale: Bool = false, plotHeight: CGFloat = 302) -> FieldHistoryInput10868 {
        let final = phase == .final
        let ids = featured.contains(selected) ? featured : featured + [selected]
        let ceiling = final || fullScale ? 1.0 : 0.9
        var input = FieldHistoryInput10868(
            title: "Gold medal probability",
            caption: final ? "Final · trades through the dated report" : "Before race day in Milan",
            series: override ?? ids.map { goldSeries($0, phase) },
            selection: .series(id: seriesID(selected), missingWords: "This contender is not in the compared group"),
            domain: domain(phase), ceiling: ceiling,
            yTicks: [0, ceiling / 2, ceiling].map { FieldHistoryTick10868(value: $0, lines: [Tests.pct($0)]) },
            xTicks: [FieldHistoryTick10868(value: 1_770_415_351, lines: ["Feb 6"]),
                     FieldHistoryTick10868(value: Double(final ? reportAt : beforeDay), lines: ["Feb 15"])],
            guides: final ? [FieldHistoryGuide10868(id: "guide:race-day", x: Double(beforeDay), label: "Race day · Milan")] : [],
            breaks: [],
            readout: final ? .beforeAndRecorded(beforeLabel: keyLabel, recordedLabel: "Last recorded") : .singleBefore(label: keyLabel),
            markKey: markKey, comparisonExplanation: nil,
            notes: ["Dots are dated trades; no continuous forecast is inferred."],
            summary: "Original gold-token trades for \(ids.map { market($0).name }.joined(separator: ", ")).",
            plotHeight: plotHeight, unboundReadingWords: "No trade at the inspected moment",
            plotUnavailableWords: "Gold history unavailable",
            windows: FieldHistoryWindows10868(groupLabel: "History window", choices: [
                FieldHistoryWindowChoice10868(action: action("window.before", "Before race day"), isSelected: !final),
                FieldHistoryWindowChoice10868(action: action("window.final", "Through the report"), isSelected: final),
            ]),
            scale: fullScale ? action("scale.auto", "Auto scale") : action("scale.full", "0–100%"),
            moreOriginals: action("more.contenders", "More contenders"),
            details: action("details.gold", "Gold prop details"),
            expand: action("expand.history", "Expand"),
            inspect: action("inspect", "Inspect history"),
            previous: action("trade.earlier", "Earlier"), next: action("trade.later", "Later"),
            inspection: inspection, layout: .focused)
        input.selectedReadout = final
            ? FieldHistorySelectedReadout10868(beforeLabel: "Before race day", inspectedLabel: "Recorded chance")
            : FieldHistorySelectedReadout10868(beforeLabel: nil, inspectedLabel: "Inspected before race day")
        input.inspectionRingShape = .circle
        return input
    }

    private static func historyBundle(_ phase: Phase, selected: String = Tests.kok, fullScale: Bool = false,
                                      readerPlotHeight: CGFloat? = 390) -> TimedFieldHistoryBundle10868 {
        TimedFieldHistoryBundle10868(phase: phase, history: history(phase == .during ? .before : phase, selected: selected,
                                                                    fullScale: fullScale),
                                     readerPlotHeight: readerPlotHeight)
    }

    // MARK: - Owner headline

    private static func dated(_ role: String, _ s: Side, _ trade: Trade?, missing: String) -> CeremonyDatedReading10868 {
        guard let trade else { return CeremonyDatedReading10868(role: role, value: .unavailable(words: missing)) }
        return CeremonyDatedReading10868(role: role, value: .recorded(observationID: pointID(s, trade), figure: pct(trade.p),
                                                                      placement: trade.p, date: clock(trade.t)))
    }

    private static func chance(_ id: String, _ phase: Phase) -> TimedFieldChanceContext10868 {
        let m = market(id)
        return TimedFieldChanceContext10868(
            name: m.name, shape: shapes[id] ?? .square, tint: tints[id] ?? .purple, meaning: "Chance of gold, not of a medal",
            earlier: dated("Before race day", m.yes, baseline(m.yes), missing: "No captured trade before race day"),
            later: phase == .final ? dated("Last recorded", m.yes, shown(m.yes, .final).last, missing: "No captured trade") : nil)
    }

    private static func phaseWords(_ phase: Phase) -> String {
        switch phase {
        case .before: "Before race day"
        case .during: "During the race · constructed frame"
        case .final: "Reported final"
        }
    }

    private static func headline(_ phase: Phase) -> TimedFieldHeadline10868 {
        let winner = results[0]
        return TimedFieldHeadline10868(
            copy: CeremonyHeadline10868(
                phase: phase, eyebrow: "Winter Games 2026 · Speed skating · Feb 15, 2026",
                title: phase == .final ? "\(winner.name) wins the women's 500m" : "Women's 500m",
                subtitle: phaseWords(phase),
                status: phase == .during ? "Live chances unavailable in this view" : "Dated probabilities, not current chances",
                aboutLabel: "About this view"),
            actual: phase == .final
                ? TimedFieldActual10868(label: "Reported winning time", figure: winner.time, unit: "s",
                                        standing: "\(standing(winner)) · \(winner.record)", spoken: nil)
                : nil,
            chanceLabel: keyLabel, chances: featured.map { chance($0, phase) }, readingUnavailable: "Reading unavailable")
    }

    // MARK: - Owner finish card

    private static func ordinal(_ n: Int) -> String {
        let suffix = (11...13).contains(n % 100) ? "th" : [1: "st", 2: "nd", 3: "rd"][n % 10] ?? "th"
        return "\(n)\(suffix)"
    }

    /// CONSTRUCTED standing words; a tie is any rank the source reports twice.
    private static func standing(_ r: Result) -> String {
        if results.filter({ $0.rankText == r.rankText }).count > 1 { return "Tied \(ordinal(r.rank))" }
        switch r.rank {
        case 1: return "Gold"
        case 2: return "Silver"
        case 3: return "Bronze"
        default: return ordinal(r.rank)
        }
    }

    private static func finishRef(_ id: String, scope: String = Tests.finishScope) -> TimedFinishResultRef10868 {
        TimedFinishResultRef10868(scope: scope, resultID: id)
    }

    /// Owner gap: the reported milliseconds behind the reported winner (test-side
    /// arithmetic), with the reported gap words; the winner's gap is a real zero.
    private static func gap(_ r: Result) -> TimedFinishGap10868 {
        TimedFinishGap10868(seconds: Double(r.ms - results[0].ms) / 1000, text: r.reportedGap.isEmpty ? "Winner" : r.reportedGap + "s")
    }

    private static func finishResult(_ r: Result) -> TimedFinishResult10868 {
        let linked = r.marketID.map { market($0) }
        return TimedFinishResult10868(
            ref: finishRef(r.id), name: r.name, detail: r.country, time: r.time, standing: standing(r), gap: gap(r),
            goldChance: linked.map { beforeReading($0.yes) }
                ?? FieldChooserReading10868(label: "Gold chance before race day", value: .missing("No linked gold prop")),
            original: linked.map { goldRef($0.id) })
    }

    private static let finishWindowSize = 10
    private static var finishWindowCount: Int { (results.count + finishWindowSize - 1) / finishWindowSize }

    private static func finishGroup(_ window: Int) -> [TimedFinishResultRef10868] {
        results[(window * finishWindowSize)..<min((window + 1) * finishWindowSize, results.count)].map { finishRef($0.id) }
    }

    private static let finishCopy = TimedFinishCopy10868(
        eyebrow: "ACTUAL RACE · SECONDS", title: "Hundredths from a medal", timeUnit: "s", timeLabel: "Actual time",
        timeSpokenUnit: "seconds", standingLabel: "Reported", gapLabel: "Time behind gold · shorter is faster",
        graphicLabel: "Actual time behind gold", distinction: "Finishing times, not probabilities",
        noGap: "Gap not reported", offAxis: "Not drawn on this scale", axisUnavailable: "Times listed without the scale",
        empty: "No reported finishers in this view", note: nil, openOriginal: "Explore this skater's gold history",
        openOriginalHint: nil, noOriginal: "No linked gold prop for this skater", chooseHint: "Shows this finisher")

    private static func finishInput(window: Int = 0, selected: String = "0", upper: Double = 3,
                                    group: [TimedFinishResultRef10868]? = nil) -> TimedFinishInput10868 {
        TimedFinishInput10868(
            scope: finishScope, catalogue: results.map(finishResult),
            selected: TimedFinishSelected10868(ref: finishRef(selected), words: "Selected",
                                               unavailableWords: "Selected finisher unavailable in this update"),
            group: group ?? finishGroup(window),
            axis: TimedFinishAxis10868(upper: upper, ticks: [0.0, 1, 2, 3].filter { $0 <= upper }.map {
                TimedFinishTick10868(seconds: $0, label: "\(Int($0))s")
            }),
            copy: finishCopy, unavailableWords: "Result unavailable in this update")
    }

    private static func finish(_ phase: Phase = .final, window: Int = 0, selected: String = "0",
                               upper: Double = 3) -> TimedFieldFinishBundle10868 {
        TimedFieldFinishBundle10868(
            phase: phase, finish: finishInput(window: window, selected: selected, upper: upper),
            windows: CeremonyChoiceGroup10868(label: "Finisher windows", choices: (0..<finishWindowCount).map { i in
                CeremonyChoice10868(id: "finish.window.\(i)",
                                    label: "\(i * finishWindowSize + 1)–\(min((i + 1) * finishWindowSize, results.count))",
                                    isSelected: i == window)
            }))
    }

    // MARK: - Owner expectations card

    private static func shiftPair(_ id: String, _ kind: PreEventShiftEndpointKind10868)
        -> (reading: PreEventShiftReading10868, observation: PreEventShiftObservation10868)? {
        let s = market(id).yes
        guard let trade = kind == .first ? firstCaptured(s) : baseline(s) else { return nil }
        let reading = FieldChooserReading10868(label: kind == .first ? "First captured" : "Latest before race day",
                                               value: .recorded(text: pct(trade.p), detail: clock(trade.t)))
        return (PreEventShiftReading10868(ref: goldRef(id), endpoint: kind, reading: reading),
                PreEventShiftObservation10868(ref: goldRef(id), endpoint: kind,
                                              observation: FieldMovementObservation10868(probability: trade.p, reading: reading),
                                              key: pointID(s, trade)))
    }

    private static let shiftCopy = PreEventShiftCopy10868(
        eyebrow: "GOLD EXPECTATIONS", title: "Before the race", phaseKey: "Both marks: before race day",
        firstKey: "Small: first captured", latestKey: "Large: latest before race day",
        graphicLabel: "First and latest gold chances before race day", firstLabel: "First captured",
        latestLabel: "Latest before race day", endpointUnavailable: "Not recorded for this comparison",
        offScale: "Above this scale", note: "Each chance keeps its own trade time",
        openHint: "Opens this gold history at that trade")

    private static func expectations(_ phase: Phase) -> PreEventShiftInput10868 {
        let pairs = featured.flatMap { id in PreEventShiftEndpointKind10868.allCases.compactMap { shiftPair(id, $0) } }
        return PreEventShiftInput10868(
            scope: goldScope, catalogue: goldCatalogue(phase == .during ? .before : phase),
            displayed: featured.map { PreEventShiftSlot10868(ref: goldRef($0), name: market($0).name, glyph: glyphs[$0] ?? .square) },
            readings: pairs.map { $0.reading }, observations: pairs.map { $0.observation },
            scale: FieldOutlookScale10868(ceiling: 1, ticks: [0, 0.5, 1].map { FieldOutlookTick10868(probability: $0, label: Tests.pct($0)) },
                                          words: "0–100% gold chance"),
            phase: RugbyMatchEventPageModel10868.leafPhase(phase), copy: shiftCopy,
            unavailableWords: "Contender unavailable in this update")
    }

    // MARK: - Owner page

    private static let copy = TimedFieldEventPageCopy10868(
        storiesLabel: "Race stories", chromeUnavailable: "This view's page details are not available for this update",
        storyUnavailable: "This story is not available in this update",
        headlineUnavailable: "The headline is not available for this update",
        readerUnavailable: "This card is not part of this view",
        historyUnavailable: "Gold history is not available for this view",
        finishUnavailable: "The reported finish is not available for this view",
        expectationsUnavailable: "Before-race expectations are not shown in this view",
        originalsUnavailable: "Original outcomes are not available for this view",
        heldOriginalUnavailable: "This original does not open in this update",
        sideHistoryUnavailable: "This outcome's own history is not available",
        chooserUnavailable: "Contender chooser unavailable", catalogueUnavailable: "Original catalogue unavailable",
        catalogueLabel: "All 72 original outcomes", sidesLabel: "Selected original outcome", backLabel: "Back",
        previousLabel: "Previous", nextLabel: "Next", historyName: "Gold history", finishName: "Actual finish gaps",
        expectationsName: "Before the race", expandLabel: "Expand")

    private static var resultLink: RugbyMatchEventPageLink10868 {
        RugbyMatchEventPageLink10868(id: "result-source", label: "Published results", url: URL(string: Tests.string("resultSource")!)!)
    }

    private static var podiumLink: RugbyMatchEventPageLink10868 {
        RugbyMatchEventPageLink10868(id: "podium-report", label: "Podium report", url: URL(string: Tests.string("podiumReport")!)!)
    }

    private static func about(_ phase: Phase) -> RugbyMatchEventPageAbout10868 {
        var sections = [
            RugbyMatchEventPageSection10868(title: "Before race day", paragraphs: [Tests.string("baselineMeaning")!]),
            RugbyMatchEventPageSection10868(title: "Official results",
                                            paragraphs: ["Official endpoint: " + Tests.string("officialResultAccess")!]),
        ]
        if phase == .final {
            let winner = results[0]
            sections.append(RugbyMatchEventPageSection10868(
                title: "Reported final", paragraphs: ["\(winner.name) won in \(winner.time) s (\(winner.record))."], link: resultLink))
            sections.append(RugbyMatchEventPageSection10868(title: "Podium report", paragraphs: ["Published report."], link: podiumLink))
        }
        return RugbyMatchEventPageAbout10868(title: phase == .final ? "About this final" : "About this view", sections: sections)
    }

    private static func stream(_ phase: Phase, finishFirst: Bool = true) -> Stream {
        let scope = "timed-field|\(phase.rawValue)"
        var cards = [Stream.Card(id: "expectations-card", name: "Before the race")]
        if phase == .final {
            cards.insert(Stream.Card(id: "finish-card", name: "Actual finish gaps"), at: finishFirst ? 0 : 1)
        }
        return Stream(scope: scope, eyebrow: "RACE STORIES", heading: phase == .final ? "Final stories" : "Race stories",
                      cards: cards, primary: Stream.CardRef(scope: scope, id: cards[0].id), companion: nil,
                      companionLabel: nil, wide: false, position: "1 of \(cards.count)", status: nil, dwellFraction: nil,
                      playback: nil, previous: nil, next: nil, readerOpen: false)
    }

    private static let storyLinks = [
        TimedFieldEventPageStory10868(cardID: "finish-card", card: .finish, reason: "Hundredths decided the podium"),
        TimedFieldEventPageStory10868(cardID: "expectations-card", card: .expectations, reason: "How gold chances moved before race day"),
    ]

    private static func views(_ phase: Phase) -> CeremonyChoiceGroup10868 {
        CeremonyChoiceGroup10868(label: "Dated view", choices: [
            CeremonyChoice10868(id: "view.before", label: "Before race day", isSelected: phase == .before),
            CeremonyChoice10868(id: "view.final", label: "Reported final", isSelected: phase == .final),
        ])
    }

    private static func notice(_ phase: Phase) -> String {
        switch phase {
        case .before: "Retained trades before race day · no live data"
        case .during: "CONSTRUCTED during frame · not live race evidence"
        case .final: "Final · retained trades through the dated report"
        }
    }

    /// One phase's chrome, carrying that phase.
    private static func chrome(_ phase: Phase, stream: Stream? = nil,
                               stories: [TimedFieldEventPageStory10868] = Tests.storyLinks,
                               readerOrder: [Card]? = nil) -> TimedFieldEventPageChrome10868 {
        TimedFieldEventPageChrome10868(
            phase: phase, notice: notice(phase), views: views(phase),
            reader: RugbyMatchEventPageReaderHeader10868(title: "Women's 500m · \(phaseWords(phase))",
                                                         state: "Dated probabilities, not current chances"),
            stream: stream, stories: stories, readerOrder: readerOrder, about: about(phase))
    }

    /// One page. By default every bundle is the page's own phase, except the
    /// finish, which is always the final's: an earlier page is offered the
    /// later finish and must withhold it.
    private static func input(_ phase: Phase, headline: TimedFieldHeadline10868? = nil,
                              chrome: TimedFieldEventPageChrome10868? = nil,
                              history: TimedFieldHistoryBundle10868? = nil,
                              finish: TimedFieldFinishBundle10868? = nil, withoutFinish: Bool = false,
                              expectations: PreEventShiftInput10868? = nil,
                              withoutExpectations: Bool = false) -> TimedFieldEventPageInput10868 {
        TimedFieldEventPageInput10868(
            phase: phase, headline: headline ?? Tests.headline(phase), chrome: chrome ?? Tests.chrome(phase),
            history: history ?? historyBundle(phase),
            finish: withoutFinish ? nil : (finish ?? Tests.finish(.final)),
            expectations: withoutExpectations ? nil : (expectations ?? Tests.expectations(phase)),
            copy: copy)
    }

    // MARK: - Collected words (phase-leak guard)

    /// Words that exist only in final bundles: the actual, standings, grades,
    /// finish times and the final chrome.
    private static let finalOnly = ["36.49", "Reported winning time", "wins the women's 500m", "Gold · OR", "Silver",
                                    "Bronze", "Tied 11th", "This outcome won", "This outcome lost",
                                    "Reported final", "Final ·", "Final stories", "About this final", "Last recorded",
                                    "Hundredths from a medal", "37.914", "38.010", "38.013"]

    /// Every word the page's models put in front of a reader for this input
    /// and originals: headline, actual, chances, notice, views, reader header,
    /// stream, story reasons, reader order names, Info, history readouts and
    /// key context, finish rows, expectations rows, the admitted originals'
    /// Details, recorded history, chooser results and side history.
    private static func texts(_ input: TimedFieldEventPageInput10868, _ originals: TimedFieldOriginals10868?) -> [String] {
        let model = Model(input)
        var words: [String] = []
        if let headline = model.headline {
            words += [headline.copy.title] + [headline.copy.subtitle, headline.copy.status, headline.copy.eyebrow].compactMap { $0 }
            for chance in headline.chances {
                words += Model.chanceSlots(chance, unreadable: headline.readingUnavailable).map(\.spoken)
            }
        }
        if let actual = model.actual { words.append(Model.spoken(actual)) }
        words += [model.notice].compactMap { $0 }
        words += model.views?.choices.filter(\.isSelected).map(\.label) ?? []
        if let header = model.readerHeader { words += [header.title, header.state].compactMap { $0 } }
        if let stream = model.stream { words += [stream.heading] + stream.cards.map(\.name) }
        for link in model.chrome?.stories ?? [] where model.storyLink(link.cardID) != nil {
            words += [link.reason].compactMap { $0 }
        }
        words += model.readerSequence.filter(model.isMounted).map(model.cardName)
        if let about = model.about {
            words += [about.title] + about.sections.flatMap { [$0.title] + $0.paragraphs }
        }
        if let history = model.presentedHistory {
            for series in history.series {
                words += FieldHistoryGeometry10868.readoutSlots(series, in: history).map(FieldHistoryGeometry10868.spokenSlot)
                if let context = FieldHistoryGeometry10868.keyContext(series) {
                    words.append(FieldHistoryGeometry10868.spokenKeyContext(context))
                }
            }
        }
        if let finish = model.finish {
            let leaf = TimedFinishModel10868(finish.finish)
            words += [finish.finish.copy.title] + leaf.rows.map(leaf.rowSummary)
        }
        if let expectations = model.expectations {
            let leaf = PreEventShiftModel10868(expectations)
            words += leaf.rows.map(leaf.rowSummary)
        }
        if let admitted = model.admitted(originals) {
            let bundle = admitted.bundle
            if let content = Details.content(catalogue: bundle.catalogue, selection: bundle.selection) {
                words += content.readings.map(\.text) + [content.result?.words].compactMap { $0 }
            }
            if case .recorded(let shown)? = Details.recorded(catalogue: bundle.catalogue, selection: bundle.selection,
                                                             context: bundle.recorded, hasCallback: true) {
                words += [shown.finish?.words, shown.content.result?.words].compactMap { $0 }
            }
            for item in model.chooser(originals)?.catalogue ?? [] {
                words += [item.result?.words].compactMap { $0 } + item.plan.readings.map(\.label)
            }
            if let side = model.sideHistory(originals) {
                words += side.series.flatMap { FieldHistoryGeometry10868.readoutSlots($0, in: side).map(FieldHistoryGeometry10868.spokenSlot) }
            }
        }
        return words
    }

    private static func leaks(_ words: [String], _ forbidden: [String]) -> [String] {
        words.filter { text in forbidden.contains { text.contains($0) } }
    }

    // MARK: - Retained capture

    func testTheRetainedCaptureBinds36Markets72Sides3632TradesAnd29Results() {
        XCTAssertEqual(Tests.markets.count, 36)
        XCTAssertEqual(Tests.sides.count, 72)
        XCTAssertEqual(Tests.allTrades.count, 3632)
        XCTAssertEqual(Tests.allTrades.filter { $0.t < Tests.beforeDay }.count, 1271, "before race day (Milan midnight)")
        XCTAssertEqual(Tests.allTrades.filter { $0.t >= Tests.beforeDay }.count, 2361)
        XCTAssertEqual(Tests.sides.filter(\.captured).count, 40)
        XCTAssertEqual(Tests.sides.filter { !$0.captured }.count, 32)
        XCTAssertTrue(Tests.allTrades.allSatisfy { $0.p > 0 && $0.p < 1 && $0.size > 0 && $0.t <= Tests.reportAt },
                      "every trade strictly positive-size, 0 < p < 1, at or before the report")
        XCTAssertTrue(Tests.sides.allSatisfy { side in side.trades.allSatisfy { $0.token == side.token } },
                      "every print carries its own side's token")
        XCTAssertEqual(Tests.results.count, 29)
        XCTAssertEqual(Tests.results.filter { $0.marketID == nil }.count, 12)
        XCTAssertEqual(Tests.markets.filter { $0.resultID != nil }.count, 17)
        XCTAssertEqual(Tests.event["eventID"], "\"200646\"")
        XCTAssertEqual(Tests.event["beforeDay"], "1771110000")
        XCTAssertEqual(Tests.event["reportAt"], "1771181329")
        for key in ["actualStart", "actualEnd", "actualSplits", "projection"] {
            XCTAssertEqual(Tests.event[key], "null", "\(key) is absent in the source and never invented")
        }
        XCTAssertEqual(Tests.string("officialResultAccess"), "HTTP403; not inspected")
        XCTAssertEqual(Tests.aliases.count, 6)
    }

    func testEveryMarketKeepsItsOwnPredicateRulesConditionTokensAndGrade() {
        XCTAssertEqual(Set(Tests.markets.map(\.rulesKey)), ["R0"], "one rules text, carried by every market")
        XCTAssertTrue(Tests.rules.hasPrefix("This market will resolve according to the participant"))
        XCTAssertEqual(Set(Tests.markets.map(\.providerURL)).count, 1)
        XCTAssertEqual(Set(Tests.markets.map(\.condition)).count, 36, "each market its own condition")
        XCTAssertEqual(Set(Tests.sides.map(\.token)).count, 72, "each side its own token")
        XCTAssertTrue(Tests.markets.filter { $0.name != "Other" }.allSatisfy { $0.predicate.contains($0.name) })
        XCTAssertTrue(Tests.market("1347976").predicate.hasPrefix("Will someone else win"), "Other keeps its own predicate")
        XCTAssertEqual(Tests.sides.filter(\.won).map { "\($0.market) \($0.side)" }.count, 36, "one won side per market")
        XCTAssertTrue(Tests.market(Tests.kok).yes.won)
        XCTAssertFalse(Tests.market(Tests.kok).no.won)
        XCTAssertTrue(Tests.markets.filter { $0.id != Tests.kok }.allSatisfy { !$0.yes.won && $0.no.won })
        let placeholders = Tests.markets.filter(\.placeholder)
        XCTAssertEqual(placeholders.count, 16, "fifteen numbered placeholders and Other")
        XCTAssertTrue(placeholders.allSatisfy { !$0.yes.captured && !$0.no.captured && $0.resultID == nil },
                      "unpriced placeholders: no trade, no finisher")
        XCTAssertEqual(Tests.market(Tests.placeholderOne).name, "Placeholder 1")
    }

    func testSameSecondPrintsStayDistinctTradesInSourceOrder() {
        var sameSecond = 0
        for side in Tests.sides {
            XCTAssertEqual(side.trades.map(\.index), Array(side.trades.indices), "source order kept")
            XCTAssertEqual(side.trades.map(\.t), side.trades.map(\.t).sorted(), "the source is already time-ordered")
            let counts = Dictionary(grouping: side.trades, by: \.t)
            sameSecond += counts.values.filter { $0.count > 1 }.reduce(0) { $0 + $1.count }
            let ids = side.trades.map { Tests.pointID(side, $0) }
            XCTAssertEqual(Set(ids).count, ids.count, "every print keeps its own owner point id")
        }
        XCTAssertEqual(sameSecond, 881, "same-second prints are separate trades, never merged")
        let kok = Tests.market(Tests.kok).yes
        XCTAssertEqual(kok.trades.count, 155)
        XCTAssertEqual(kok.trades.filter { $0.t == 1_770_914_027 }.count, 2)
    }

    func testResultsKeepExactPrecisionTheTieAndTheUnlinkedFinishers() {
        let winner = Tests.result("0")
        XCTAssertEqual([winner.name, winner.time, winner.msText, winner.reportedGap, winner.record],
                       ["Femke Kok", "36.49", "36490", "", "OR"])
        let tied = Tests.results.filter { $0.rankText == "11" }
        XCTAssertEqual(tied.map(\.id), ["10", "11"])
        XCTAssertEqual(tied.map(\.time), ["37.914", "37.914"])
        XCTAssertEqual(tied.map(\.reportedGap), ["+1.42", "+1.42"])
        XCTAssertEqual([Tests.result("13").time, Tests.result("14").time], ["38.010", "38.013"], "trailing zero kept")
        XCTAssertEqual(Tests.result("13").reportedGap, Tests.result("14").reportedGap, "same reported gap, different times")
        XCTAssertNil(Tests.result("2").marketID, "Takagi's bronze has no named gold market")
        for id in [Tests.inegawa, Tests.thorup, Tests.hiller] {
            XCTAssertNil(Tests.market(id).resultID)
            XCTAssertFalse(Tests.results.contains { $0.marketID == id }, "\(id) stays unlinked")
        }
        XCTAssertFalse(Tests.results.contains { r in r.marketID.map { Tests.market($0).placeholder } ?? false },
                       "no placeholder is assigned to a finisher")
        for r in Tests.results {
            if let id = r.marketID { XCTAssertEqual(Tests.market(id).resultID, r.id, "\(r.name): both directions agree") }
        }
    }

    // MARK: - The anchored gold history

    func testTheAnchorMountsTheSelectedContenderAndFeaturedPeersWithTheirOwnShapesUnchanged() throws {
        let owner = Tests.history(.before)
        let page = Page(input: Tests.input(.before))
        let shown = try XCTUnwrap(page.model.presentedHistory)
        XCTAssertEqual(shown.series, owner.series, "every series, run and point exactly as the owner admitted")
        XCTAssertEqual(shown.series.map(\.id), Tests.featured.map { Tests.seriesID($0) })
        XCTAssertEqual(shown.series.map(\.shape), [.circle, .triangle, .diamond])
        XCTAssertEqual(shown.series.map(\.name), ["Femke Kok (NED)", "Jutta Leerdam (NED)", "Erin Jackson (USA)"])
        XCTAssertEqual(shown.ceiling, owner.ceiling)
        XCTAssertEqual(shown.domain, owner.domain)
        XCTAssertEqual(shown.yTicks, owner.yTicks)
        XCTAssertEqual(shown.xTicks, owner.xTicks)
        XCTAssertEqual(shown.inspectionRingShape, .circle)
        XCTAssertEqual(shown.layout, .focused)
        XCTAssertTrue(shown.series.allSatisfy { $0.runs.allSatisfy { $0.points.count == 1 } }, "dots only, never a joined line")
        XCTAssertEqual(shown.series[0].runs.count, 47, "Kok's 47 trades before race day")
        XCTAssertEqual(try XCTUnwrap(Page(input: Tests.input(.final)).model.presentedHistory).series[0].runs.count, 155)
        XCTAssertFalse(shown.series.flatMap { $0.runs.flatMap(\.points) }.contains { $0.probability == 1 || $0.probability == 0 },
                       "no synthetic 0% or 100% endpoint")
        let pergher = Page(input: Tests.input(.before, history: Tests.historyBundle(.before, selected: Tests.pergher)))
        let withSelected = try XCTUnwrap(pergher.model.presentedHistory)
        XCTAssertEqual(withSelected.series.map(\.id).last, Tests.seriesID(Tests.pergher), "the selected contender joins the peers")
        XCTAssertEqual(withSelected.selection, .series(id: Tests.seriesID(Tests.pergher), missingWords: "This contender is not in the compared group"))
        XCTAssertEqual(Array(withSelected.series.prefix(3)), Array(shown.series), "the peers keep their runs and shapes")
    }

    func testTheBeforeReadingIsTheLastTradeBeforeMidnightMilanAndTheFinalPairsItWithTheLastRecorded() throws {
        let before = try XCTUnwrap(Page(input: Tests.input(.before)).model.presentedHistory)
        let kokBefore = FieldHistoryGeometry10868.readoutSlots(before.series[0], in: before)
        XCTAssertEqual(kokBefore, [FieldHistoryReadoutSlot10868(
            label: "Gold chance · before race day",
            display: .figure("78%", provenance: "Before race day · " + Tests.clock(1_771_109_125)))])
        XCTAssertLessThan(1_771_109_125, Tests.beforeDay, "the last retained trade before the cutoff, not a closing quote")
        XCTAssertEqual(Tests.clock(1_771_109_125), "Feb 14, 2026, 2:45:25 PM PST", "one simulated device zone, readable local words")
        XCTAssertEqual(Tests.clock(Tests.beforeDay), "Feb 14, 2026, 3:00:00 PM PST",
                       "the cutoff shown in device words keeps its meaning: midnight in Milan")
        XCTAssertEqual(Tests.string("baselineMeaning"),
                       "Last retained trade before race day begins at midnight in Milan. Not a verified closing quote.")
        let final = try XCTUnwrap(Page(input: Tests.input(.final)).model.presentedHistory)
        let kokFinal = FieldHistoryGeometry10868.readoutSlots(final.series[0], in: final)
        XCTAssertEqual(kokFinal.map(\.label), ["Gold chance · before race day", "Last recorded"])
        XCTAssertEqual(kokFinal[0].display, .figure("78%", provenance: "Before race day · " + Tests.clock(1_771_109_125)))
        XCTAssertEqual(kokFinal[1].display, .figure("99.9%", provenance: "Last recorded · " + Tests.clock(1_771_179_805)),
                       "the last real trade, never a 100% settlement endpoint")
        let leerdam = FieldHistoryGeometry10868.readoutSlots(final.series[1], in: final)
        XCTAssertEqual(leerdam[0].display, .figure("22.6%", provenance: "Before race day · " + Tests.clock(1_771_107_553)))
        let jackson = FieldHistoryGeometry10868.readoutSlots(final.series[2], in: final)
        XCTAssertEqual(jackson[0].display, .figure("1.4%", provenance: "Before race day · " + Tests.clock(1_771_107_825)))
        XCTAssertEqual(FieldHistoryGeometry10868.keyContext(final.series[0]),
                       FieldHistoryKeyContext10868(label: "Reported finish", words: "Gold", spoken: "Reported finish: Gold"),
                       "the reported finish is key words only, never a reading")
        XCTAssertNil(FieldHistoryGeometry10868.keyContext(before.series[0]))
    }

    func testFullSizeIsTheSameInputAtTheOwnersTallerHeightWithTheExactCallbacks() throws {
        var log: [String] = []
        let input = Tests.input(.final)
        let pageView = Page(input: input, onHistoryAction: { log.append("history:\($0)") },
                            onHistoryInspectionChoice: { log.append("choice:\($0)") },
                            onHistoryPlotPosition: { log.append("position:\($0)") }, onInteraction: { log.append("hold") })
        let reader = Page(input: input, mode: .reader(.history), onHistoryAction: { log.append("history:\($0)") },
                          onHistoryInspectionChoice: { log.append("choice:\($0)") },
                          onHistoryPlotPosition: { log.append("position:\($0)") }, onInteraction: { log.append("hold") })
        let compact = try XCTUnwrap(pageView.historyContent(reader: false))
        let full = try XCTUnwrap(reader.historyContent(reader: true))
        XCTAssertEqual(full.input.series, compact.input.series)
        XCTAssertEqual(full.input.ceiling, compact.input.ceiling)
        XCTAssertEqual(full.input.domain, compact.input.domain)
        XCTAssertEqual(full.input.readout, compact.input.readout)
        XCTAssertEqual(full.input.selectedReadout, compact.input.selectedReadout)
        XCTAssertEqual(full.input.scale, compact.input.scale)
        XCTAssertEqual(compact.input.plotHeight, 302)
        XCTAssertEqual(full.input.plotHeight, 390, "the owner's full-size height")
        XCTAssertEqual(compact.input.expand?.id, "expand.history")
        XCTAssertNil(full.input.expand, "full size has no expand of its own")
        compact.onAction?("expand.history")
        full.onAction?("trade.later")
        full.onInspectionChoice?("1347941:Yes:154")
        full.onPlotPosition?(1_771_179_805)
        XCTAssertEqual(log, ["hold", "history:expand.history", "history:trade.later", "choice:1347941:Yes:154",
                             "position:1771179805.0"])
        let short = Tests.input(.final, history: Tests.historyBundle(.final, readerPlotHeight: 120))
        XCTAssertEqual(Model(short).readerHistory?.plotHeight, 302, "never shorter than the page's own plot")
    }

    func testAutoAndFullScaleArePassedThroughWithImmutablePointsAndRuns() throws {
        var log: [String] = []
        let auto = Page(input: Tests.input(.before), onHistoryAction: { log.append($0) }, onInteraction: { log.append("hold") })
        let full = Page(input: Tests.input(.before, history: Tests.historyBundle(.before, fullScale: true)))
        let autoShown = try XCTUnwrap(auto.model.presentedHistory)
        let fullShown = try XCTUnwrap(full.model.presentedHistory)
        XCTAssertEqual(autoShown.ceiling, 0.9, "the owner's closer scale")
        XCTAssertEqual(fullShown.ceiling, 1, "the owner's full 0–100% scale")
        XCTAssertEqual(autoShown.series, fullShown.series, "points and runs never change with the scale")
        XCTAssertEqual(autoShown.domain, fullShown.domain, "the time domain is never recomputed")
        XCTAssertEqual(autoShown.scale?.label, "0–100%")
        XCTAssertEqual(fullShown.scale?.label, "Auto scale")
        auto.historyContent(reader: false)?.onAction?("scale.full")
        XCTAssertEqual(log, ["hold", "scale.full"], "the page hands back the owner's scale id; the owner rebuilds the input")
        XCTAssertEqual(auto.model.presentedHistory?.ceiling, 0.9, "nothing changes here until the owner supplies the new input")
    }

    func testTheHeadlineChanceContextShowsEachContendersOwnTradeUnderItsOwnRoleAndDate() throws {
        let before = try XCTUnwrap(Model(Tests.input(.before)).headline)
        XCTAssertEqual(before.chances.map(\.name), ["Femke Kok (NED)", "Jutta Leerdam (NED)", "Erin Jackson (USA)"])
        XCTAssertEqual(before.chances.map(\.shape), [.circle, .triangle, .diamond], "the same shapes as the history")
        XCTAssertEqual(before.chances.map(\.meaning), Array(repeating: "Chance of gold, not of a medal", count: 3))
        let kokBefore = Model.chanceSlots(before.chances[0], unreadable: before.readingUnavailable)
        XCTAssertEqual(kokBefore, [CeremonyComparisonSlot10868(
            role: "Before race day", style: .hollow, text: "78%", isValue: true, date: Tests.clock(1_771_109_125),
            placement: 0.7799999991, observationID: "1347941:Yes:46")])
        let final = try XCTUnwrap(Model(Tests.input(.final)).headline)
        let kokFinal = Model.chanceSlots(final.chances[0], unreadable: final.readingUnavailable)
        XCTAssertEqual(kokFinal.map(\.role), ["Before race day", "Last recorded"])
        XCTAssertEqual(kokFinal.map(\.style), [.hollow, .filled])
        XCTAssertEqual(kokFinal.map(\.text), ["78%", "99.9%"])
        XCTAssertEqual(kokFinal[1].observationID, "1347941:Yes:154")
        XCTAssertEqual(kokFinal[1].spoken, "Last recorded 99.9%, " + Tests.clock(1_771_179_805))
        XCTAssertEqual(final.chanceLabel, "Gold chance · before race day")
        let view = try XCTUnwrap(Page(input: Tests.input(.final)).headlineContent())
        XCTAssertEqual(view.headline, final, "the headline view receives the admitted headline exactly")
    }

    // MARK: - Headline phases and actuals

    func testTheActualAppearsOnlyOnAFinalPageFromAFinalHeadlineAndIsNeverAChance() throws {
        let final = Model(Tests.input(.final))
        let actual = try XCTUnwrap(final.actual)
        XCTAssertEqual([actual.label, actual.figure, actual.unit, actual.standing],
                       ["Reported winning time", "36.49", "s", "Gold · OR"], "the reported time verbatim, with its unit")
        XCTAssertEqual(Model.spoken(actual), "Reported winning time, 36.49 s, Gold · OR")
        XCTAssertEqual(try XCTUnwrap(Page(input: Tests.input(.final)).headlineContent()).actual, actual)
        XCTAssertNil(Model(Tests.input(.before)).actual)
        XCTAssertNil(Model(Tests.input(.during)).actual)
        // A final headline offered to an earlier page lends nothing.
        let early = Model(Tests.input(.before, headline: Tests.headline(.final)))
        XCTAssertNil(early.headline)
        XCTAssertNil(early.actual)
        XCTAssertNil(Page(input: Tests.input(.before, headline: Tests.headline(.final))).headlineContent())
        // A before headline offered to a final page lends nothing either.
        let late = Model(Tests.input(.final, headline: Tests.headline(.before)))
        XCTAssertNil(late.headline)
        XCTAssertNil(late.actual)
        // An actual with no readable figure is not shown.
        var blank = Tests.headline(.final)
        blank.actual = TimedFieldActual10868(label: "Reported winning time", figure: " ", unit: "s", standing: "Gold", spoken: nil)
        XCTAssertNil(Model(Tests.input(.final, headline: blank)).actual)
        // Positive control: a headline whose actual is supplied to a before page still never shows it.
        var leaky = Tests.headline(.before)
        leaky.actual = actual
        XCTAssertNil(Model(Tests.input(.before, headline: leaky)).actual, "the actual is final-only even inside a before headline")
        XCTAssertNotNil(Model(Tests.input(.before, headline: leaky)).headline)
    }

    func testADatedReadingNeedsAnIdFigureDateAndValidPlacementAndOnlyAnExactSameTradeCollapses() {
        let unreadable = "Reading unavailable"
        func chance(_ earlier: CeremonyReadingValue10868, _ later: CeremonyReadingValue10868?) -> TimedFieldChanceContext10868 {
            TimedFieldChanceContext10868(name: "Contender", shape: .circle, tint: .blue, meaning: nil,
                                         earlier: CeremonyDatedReading10868(role: "Before", value: earlier),
                                         later: later.map { CeremonyDatedReading10868(role: "Later", value: $0) })
        }
        let good = CeremonyReadingValue10868.recorded(observationID: "a", figure: "78%", placement: 0.78, date: "Feb 14")
        XCTAssertEqual(Model.chanceSlots(chance(good, nil), unreadable: unreadable).map(\.isValue), [true])
        for bad in [CeremonyReadingValue10868.recorded(observationID: " ", figure: "78%", placement: 0.78, date: "Feb 14"),
                    .recorded(observationID: "a", figure: "", placement: 0.78, date: "Feb 14"),
                    .recorded(observationID: "a", figure: "78%", placement: 0.78, date: " "),
                    .recorded(observationID: "a", figure: "78%", placement: 1.2, date: "Feb 14"),
                    .recorded(observationID: "a", figure: "78%", placement: .nan, date: "Feb 14")] {
            let slot = Model.chanceSlots(chance(bad, nil), unreadable: unreadable)[0]
            XCTAssertFalse(slot.isValue)
            XCTAssertEqual(slot.text, unreadable)
            XCTAssertNil(slot.placement, "never clamped")
        }
        let zero = Model.chanceSlots(chance(.recorded(observationID: "z", figure: "0%", placement: 0, date: "Feb 14"), nil),
                                     unreadable: unreadable)[0]
        XCTAssertTrue(zero.isValue, "a real 0% is a value")
        XCTAssertEqual(zero.placement, 0)
        let absent = Model.chanceSlots(chance(.unavailable(words: "No captured trade before race day"), nil), unreadable: unreadable)[0]
        XCTAssertFalse(absent.isValue, "absent is words, never a zero")
        XCTAssertEqual(absent.text, "No captured trade before race day")
        XCTAssertEqual(Model.chanceSlots(chance(good, good), unreadable: unreadable).count, 1, "one coherent trade shows once")
        let sameFigureOtherTrade = CeremonyReadingValue10868.recorded(observationID: "b", figure: "78%", placement: 0.78, date: "Feb 14")
        XCTAssertEqual(Model.chanceSlots(chance(good, sameFigureOtherTrade), unreadable: unreadable).count, 2,
                       "equal figures at different trades both stay")
        let conflicting = CeremonyReadingValue10868.recorded(observationID: "a", figure: "79%", placement: 0.78, date: "Feb 14")
        XCTAssertEqual(Model.chanceSlots(chance(good, conflicting), unreadable: unreadable).count, 2)
    }

    func testNoActualStartEndSplitsOrProjectedFinishIsInvented() {
        for phase in Phase.allCases {
            let words = Tests.texts(Tests.input(phase), Tests.fullOriginals(phase == .during ? .before : phase))
            for forbidden in ["Started at", "Start time", "Finished at", "Split", "Projected", "projected finish", "Lap "] {
                XCTAssertTrue(Tests.leaks(words, [forbidden]).isEmpty, "\(phase): no invented \(forbidden)")
            }
        }
        XCTAssertNil(Model(Tests.input(.during)).actual, "the constructed during view has no actual at all")
        XCTAssertEqual(Model(Tests.input(.during)).headline?.copy.status, "Live chances unavailable in this view")
        // Positive control: the guard does catch an invented split.
        XCTAssertFalse(Tests.leaks(["Split 10.41 s"], ["Split"]).isEmpty)
    }

    // MARK: - The actual finish card

    func testTheFinishCardIsPresentOnlyAtTheFinalAndWithheldEarlier() throws {
        for phase in [Phase.before, .during] {
            let page = Page(input: Tests.input(phase), onFinishChoose: { _ in }, onFinishWindow: { _ in }, onCardOpen: { _ in })
            XCTAssertFalse(page.model.isMounted(.finish), "\(phase): the finish is withheld, not shown as words")
            XCTAssertNil(page.model.finish)
            XCTAssertNil(page.finishContent(.page))
            XCTAssertNil(page.finishWindowsContent(.page))
            XCTAssertNil(page.expandAction(.finish))
            XCTAssertEqual(page.model.mountedCards, [.history, .expectations])
            XCTAssertFalse(page.model.directCards.contains(.finish))
        }
        let final = Page(input: Tests.input(.final), onFinishChoose: { _ in })
        XCTAssertTrue(final.model.isMounted(.finish))
        XCTAssertEqual(final.model.mountedCards, [.history, .finish, .expectations])
        XCTAssertEqual(try XCTUnwrap(final.finishContent(.page)).input, Tests.finishInput())
        XCTAssertNil(final.model.unavailableWords(.finish))
        // A final page offered a finish admitted for another phase shows the owner's words, no rows, no actions.
        let mismatched = Page(input: Tests.input(.final, finish: Tests.finish(.before)), onFinishChoose: { _ in }, onFinishWindow: { _ in })
        XCTAssertTrue(mismatched.model.isMounted(.finish), "the card is present at the final")
        XCTAssertNil(mismatched.finishContent(.page))
        XCTAssertNil(mismatched.finishWindowsContent(.page))
        XCTAssertEqual(mismatched.model.unavailableWords(.finish), "The reported finish is not available for this view")
        let missing = Model(Tests.input(.final, withoutFinish: true))
        XCTAssertTrue(missing.isMounted(.finish), "never silently dropped at the final")
        XCTAssertEqual(missing.unavailableWords(.finish), "The reported finish is not available for this view")
    }

    func testTheFinishShowsOwnerTimesStandingsGapsAndTheEarlierGoldChanceVerbatim() throws {
        let leaf = TimedFinishModel10868(try XCTUnwrap(Page(input: Tests.input(.final)).finishContent(.page)).input)
        XCTAssertEqual(leaf.rows.count, 10, "the owner's first window")
        let kok = try XCTUnwrap(leaf.rows[0].resolution.result)
        XCTAssertEqual([kok.name, kok.time, kok.standing, kok.gap?.text], ["Femke Kok", "36.49", "Gold", "Winner"])
        XCTAssertEqual(kok.gap?.seconds, 0, "the winner's gap is a real zero")
        XCTAssertEqual(leaf.rows[0].bar, .placed(0), "zero is drawn as a value, not dropped")
        XCTAssertEqual(kok.goldChance, FieldChooserReading10868(
            label: "Gold chance before race day", value: .recorded(text: "78%", detail: Tests.clock(1_771_109_125))))
        XCTAssertEqual(kok.original, Tests.goldRef(Tests.kok))
        let takagi = try XCTUnwrap(leaf.rows[2].resolution.result)
        XCTAssertEqual([takagi.name, takagi.time, takagi.standing], ["Miho Takagi", "37.27", "Bronze"])
        XCTAssertEqual(takagi.goldChance.value, .missing("No linked gold prop"), "no placeholder, no fallback")
        XCTAssertNil(takagi.original)
        let second = TimedFinishModel10868(Tests.finishInput(window: 1))
        let wojcik = try XCTUnwrap(second.rows[0].resolution.result)
        let chen = try XCTUnwrap(second.rows[1].resolution.result)
        XCTAssertEqual([wojcik.time, chen.time], ["37.914", "37.914"])
        XCTAssertEqual([wojcik.standing, chen.standing], ["Tied 11th", "Tied 11th"])
        XCTAssertEqual([wojcik.gap?.text, chen.gap?.text], ["+1.42s", "+1.42s"])
        let kim = try XCTUnwrap(second.rows[3].resolution.result)
        let boersma = try XCTUnwrap(second.rows[4].resolution.result)
        XCTAssertEqual([kim.time, boersma.time], ["38.010", "38.013"], "kept at the reported precision")
        XCTAssertEqual(second.input.group.map(\.resultID), ["10", "11", "12", "13", "14", "15", "16", "17", "18", "19"],
                       "the owner's order; nothing re-ranks here")
        XCTAssertEqual(Tests.finishCopy.gapLabel, "Time behind gold · shorter is faster")
        XCTAssertEqual(Tests.finishCopy.distinction, "Finishing times, not probabilities")
    }

    func testAll29FinishersAreReachableThroughTheOwnersBoundedWindows() throws {
        var log: [String] = []
        let page = Page(input: Tests.input(.final), onFinishWindow: { log.append("window:\($0)") }, onInteraction: { log.append("hold") })
        let windows = try XCTUnwrap(page.finishWindowsContent(.page))
        XCTAssertEqual(windows.group.choices.map(\.label), ["1–10", "11–20", "21–29"])
        XCTAssertEqual(windows.group.choices.map(\.isSelected), [true, false, false])
        var reached: [String] = []
        for index in 0..<Tests.finishWindowCount {
            let group = Tests.finishInput(window: index).group
            XCTAssertLessThanOrEqual(group.count, 10, "bounded windows, not a sprawling table")
            reached += group.map(\.resultID)
            XCTAssertTrue(TimedFinishModel10868(Tests.finishInput(window: index)).rows.allSatisfy { $0.resolution.result != nil })
        }
        XCTAssertEqual(reached, Tests.results.map(\.id), "every one of the 29 reported finishers, once, in the owner's order")
        windows.action(windows.group.choices[2])?()
        XCTAssertEqual(log, ["hold", "window:finish.window.2"])
        let third = Page(input: Tests.input(.final, finish: Tests.finish(window: 2)))
        XCTAssertEqual(try XCTUnwrap(third.finishContent(.page)).input.group.map(\.resultID).last, "28")
    }

    func testTheFinisherSelectionIsIndependentOfTheGoldHistorySelection() throws {
        var log: [String] = []
        let input = Tests.input(.final, finish: Tests.finish(selected: "2"))
        let page = Page(input: input, onFinishChoose: { log.append("finisher:\($0.resultID)") },
                        onFinishOpenOriginal: { log.append("open:\($0.marketID)") }, onInteraction: { log.append("hold") })
        let finish = try XCTUnwrap(page.finishContent(.page))
        let leaf = TimedFinishModel10868(finish.input)
        XCTAssertEqual(leaf.selectedResult?.name, "Miho Takagi", "an unlinked finisher stays selectable")
        XCTAssertNil(leaf.openAction(canOpen: true), "no gold prop, no borrowed original")
        XCTAssertEqual(leaf.noOriginalWords, "No linked gold prop for this skater")
        XCTAssertEqual(page.model.presentedHistory?.selection,
                       .series(id: Tests.seriesID(Tests.kok), missingWords: "This contender is not in the compared group"),
                       "the history keeps its own selection")
        let row = leaf.rows[4]
        if let ref = leaf.chooseAction(row, canChoose: true) { finish.onChooseResult?(ref) }
        XCTAssertEqual(log, ["hold", "finisher:4"])
        let jackson = TimedFinishModel10868(Tests.finishInput(selected: "4"))
        if let original = jackson.openAction(canOpen: true) { finish.onOpenOriginal?(original) }
        XCTAssertEqual(log, ["hold", "finisher:4", "hold", "open:1347949"])
        // An unlinked gold market stays selectable in the history with no finish row of its own.
        for id in [Tests.inegawa, Tests.thorup, Tests.hiller] {
            let history = try XCTUnwrap(Model(Tests.input(.final, history: Tests.historyBundle(.final, selected: id))).presentedHistory)
            XCTAssertEqual(history.series.last?.id, Tests.seriesID(id))
            XCTAssertNil(history.series.last?.keyContext, "\(id): no reported finish borrowed")
            XCTAssertFalse(Tests.finishInput().catalogue.contains { $0.original?.marketID == id })
        }
    }

    func testZeroAbsentOffAxisAndMissingAxisGapsStayDistinct() throws {
        let normal = TimedFinishModel10868(Tests.finishInput())
        XCTAssertEqual(normal.rows[0].bar, .placed(0))
        guard case .placed(let leerdam) = normal.rows[1].bar else { return XCTFail("Leerdam is placed") }
        XCTAssertEqual(leerdam, 0.66 / 3, accuracy: 1e-9, "the owner's seconds on the owner's zero-based axis")
        let tight = TimedFinishModel10868(Tests.finishInput(upper: 1))
        XCTAssertEqual(tight.rows[0].bar, .placed(0))
        XCTAssertEqual(tight.rows[6].bar, .offAxis, "1.04 s does not fit a 1 s axis; never clamped")
        var noAxis = Tests.finishInput()
        noAxis = TimedFinishInput10868(scope: noAxis.scope, catalogue: noAxis.catalogue, selected: noAxis.selected,
                                       group: noAxis.group, axis: nil, copy: noAxis.copy, unavailableWords: noAxis.unavailableWords)
        XCTAssertTrue(TimedFinishModel10868(noAxis).rows.allSatisfy { $0.bar == .noAxis })
        var catalogue = Tests.finishInput().catalogue
        let first = catalogue[1]
        catalogue[1] = TimedFinishResult10868(ref: first.ref, name: first.name, detail: first.detail, time: first.time,
                                             standing: first.standing, gap: nil, goldChance: first.goldChance, original: first.original)
        let gapless = TimedFinishInput10868(scope: Tests.finishScope, catalogue: catalogue, selected: nil,
                                            group: Tests.finishGroup(0), axis: Tests.finishInput().axis, copy: Tests.finishCopy,
                                            unavailableWords: "Result unavailable in this update")
        XCTAssertEqual(TimedFinishModel10868(gapless).rows[1].bar, .noGap, "an absent gap is words, never a zero")
        XCTAssertEqual(TimedFinishModel10868(gapless).rows[0].bar, .placed(0))
    }

    // MARK: - The before-race expectations card

    func testTheExpectationsCardStaysAtTheFinalWithBothOwnBeforeDayEndpoints() throws {
        for phase in [Phase.before, .final] {
            let page = Page(input: Tests.input(phase))
            let card = try XCTUnwrap(page.expectationsContent(.page), "\(phase): the expectations card is kept")
            XCTAssertEqual(card.input, Tests.expectations(phase))
            let leaf = PreEventShiftModel10868(card.input)
            XCTAssertTrue(leaf.isShown)
            XCTAssertEqual(leaf.rows.map(\.slot.name), ["Femke Kok (NED)", "Jutta Leerdam (NED)", "Erin Jackson (USA)"])
            XCTAssertEqual(leaf.rows.map(\.slot.glyph), [.circle, .triangle, .diamond], "the history's own shapes")
            let kok = leaf.rows[0]
            XCTAssertEqual(kok.first?.endpoint, .reading(FieldChooserReading10868(
                label: "First captured", value: .recorded(text: "68%", detail: Tests.clock(1_770_423_645)))))
            XCTAssertEqual(kok.latest?.endpoint, .reading(FieldChooserReading10868(
                label: "Latest before race day", value: .recorded(text: "78%", detail: Tests.clock(1_771_109_125)))))
            XCTAssertEqual(kok.first?.key, "1347941:Yes:0")
            XCTAssertEqual(kok.latest?.key, "1347941:Yes:46")
            XCTAssertNil(page.model.unavailableWords(.expectations))
        }
        let keys = Tests.expectations(.final).observations
        XCTAssertTrue(keys.allSatisfy { obs in
            let side = Tests.market(obs.ref.marketID).yes
            return side.trades.contains { Tests.pointID(side, $0) == obs.key && $0.t < Tests.beforeDay }
        }, "both endpoints are before race day, even on the final page")
        XCTAssertEqual(Tests.shiftCopy.firstKey, "Small: first captured", "the first capture is not an opening quote")
    }

    func testDuringTheExpectationsAreTheOwnersUnavailableWordsAndNothingIsCoerced() {
        for bundlePhase in Phase.allCases {
            let page = Page(input: Tests.input(.during, expectations: Tests.expectations(bundlePhase)), onExpectationOpen: { _ in })
            XCTAssertTrue(page.model.isMounted(.expectations), "the card is still present")
            XCTAssertNil(page.model.expectations, "\(bundlePhase) bundle: the leaf has no live state; nothing is coerced")
            XCTAssertNil(page.expectationsContent(.page))
            XCTAssertEqual(page.model.unavailableWords(.expectations), "Before-race expectations are not shown in this view")
        }
        XCTAssertNil(Model(Tests.input(.before, expectations: Tests.expectations(.final))).expectations, "a final bundle on a before page")
        XCTAssertNil(Model(Tests.input(.final, expectations: Tests.expectations(.before))).expectations, "a before bundle on a final page")
        XCTAssertNotNil(Model(Tests.input(.final, expectations: Tests.expectations(.final))).expectations)
        XCTAssertEqual(Model(Tests.input(.final, withoutExpectations: true)).unavailableWords(.expectations),
                       "Before-race expectations are not shown in this view", "absent is the owner's words, never dropped")
    }

    func testAnExpectationEndpointHandsBackItsExactOriginalAndKeyAfterOneHold() throws {
        var log: [String] = []
        let page = Page(input: Tests.input(.final), onExpectationOpen: { log.append("open:\($0.ref.marketID):\($0.observation ?? "-")") },
                        onInteraction: { log.append("hold") })
        let card = try XCTUnwrap(page.expectationsContent(.page))
        let leaf = PreEventShiftModel10868(card.input)
        for row in leaf.rows.prefix(2) {
            for side in row.sides {
                if let open = leaf.openAction(row, side, canOpen: true) { card.onOpen?(open) }
            }
        }
        XCTAssertEqual(log, ["hold", "open:1347941:1347941:Yes:0", "hold", "open:1347941:1347941:Yes:46",
                             "hold", "open:1347948:1347948:Yes:0", "hold", "open:1347948:1347948:Yes:50"])
        XCTAssertNil(Page(input: Tests.input(.final)).expectationsContent(.page)?.onOpen, "no callback, no control")
    }

    func testBaselinesAreNeverReplacedByAnInspectedLatestOrSettledValue() throws {
        let last = Tests.market(Tests.kok).yes.trades[154]
        let inspected = Tests.history(.final, series: [
            Tests.goldSeries(Tests.kok, .final, recorded: Tests.observation(Tests.market(Tests.kok).yes, last, prefix: "Inspected · ")),
            Tests.goldSeries(Tests.leerdam, .final), Tests.goldSeries(Tests.jackson, .final),
        ], inspection: FieldHistoryInspection10868(
            x: Double(last.t), caption: "Recorded " + Tests.clock(last.t),
            selections: [Tests.seriesID(Tests.kok): .point(id: "1347941:Yes:154", spoken: "99.9%")],
            choices: [], choicePresentation: .slider(label: "Inspect gold trade"), note: nil))
        let bundle = TimedFieldHistoryBundle10868(phase: .final, history: inspected, readerPlotHeight: 390)
        let model = Model(Tests.input(.final, history: bundle))
        let shown = try XCTUnwrap(model.presentedHistory)
        guard case .original(_, let slots) = FieldHistoryGeometry10868.selectedSummary(shown) else { return XCTFail("Kok is selected") }
        XCTAssertEqual(slots.map(\.label), ["Before race day", "Recorded chance"])
        XCTAssertEqual(slots[0].display, .figure("78%", provenance: "Before race day · " + Tests.clock(1_771_109_125)),
                       "the baseline stays its own trade")
        XCTAssertEqual(slots[1].display, .figure("99.9%", provenance: "Inspected · " + Tests.clock(last.t)))
        let expectations = PreEventShiftModel10868(try XCTUnwrap(model.expectations))
        XCTAssertEqual(expectations.rows[0].latest?.key, "1347941:Yes:46", "never the latest or settled trade")
        let chooserKok = try XCTUnwrap(Tests.chooser(.final).catalogue.first { $0.ref == Tests.goldRef(Tests.kok) })
        XCTAssertEqual(chooserKok.plan.readings.first?.value, .recorded(text: "78%", detail: Tests.clock(1_771_109_125)))
        let headlineKok = try XCTUnwrap(model.headline?.chances.first)
        XCTAssertEqual(Model.chanceSlots(headlineKok, unreadable: "x").first?.text, "78%")
        XCTAssertNotEqual(Tests.pct(last.p), "100%", "the last real trade is not a settlement endpoint")
    }

    // MARK: - Originals, Details, the chooser and the catalogue

    func testAll72OriginalsAreReachableInSixBoundedWindowsWithVerbatimRulesAndOwnReadings() throws {
        var reached: [Details.Identity] = []
        for index in 0..<Tests.windowCount {
            let bundle = Tests.originals(.final, window: Tests.catalogueWindow(.final, index: index))
            let page = Page(input: Tests.input(.final), mode: .catalogue, originals: bundle, onCatalogueSelect: { _ in })
            let view = try XCTUnwrap(page.catalogueContent())
            XCTAssertEqual(view.catalogue?.originals.count, 12, "six markets, both sides")
            let cards = OriginalMarketCatalogue9483.cards(catalogue: view.catalogue, selection: view.selection, labels: view.labels,
                                                          unavailableChoice: view.unavailableChoice)
            XCTAssertEqual(cards.count, 12)
            XCTAssertTrue(cards.allSatisfy { $0.content != nil }, "every original opens")
            reached += view.catalogue?.originals.map(\.identity) ?? []
        }
        let all = Tests.markets.flatMap { m in ["Yes", "No"].map { Details.Identity(source: Tests.source, market: m.id, side: $0) } }
        XCTAssertEqual(reached, all, "every one of the 72 originals, once, in the owner's order")
        for m in Tests.markets {
            for side in m.sides {
                let content = try XCTUnwrap(Details.content(catalogue: Tests.catalogue(.final), selection: Tests.selection(m, side.side)))
                XCTAssertEqual(content.title, m.name)
                guard case .verified(let paragraphs) = content.rules else { return XCTFail("\(m.id): verified rules") }
                XCTAssertEqual(paragraphs.joined(separator: "\n\n"), Tests.rules, "\(m.id) \(side.side): the source rules exactly")
                XCTAssertFalse(paragraphs.contains(m.predicate), "the predicate is not an invented rules paragraph")
                XCTAssertTrue(content.about.contains(Details.Row(label: "Market predicate", value: m.predicate)),
                              "the retained predicate stays reachable under its own label")
                XCTAssertTrue(content.about.contains(Details.Row(label: "Original token", value: side.token)))
                XCTAssertTrue(content.about.contains(Details.Row(label: "Race-day cutoff",
                                                                 value: "Midnight in Milan · 1771110000 (Unix seconds)")))
            }
        }
        let placeholder = try XCTUnwrap(Details.content(catalogue: Tests.catalogue(.before),
                                                        selection: Tests.selection(Tests.market(Tests.placeholderOne), "Yes")))
        XCTAssertEqual(placeholder.readings.first?.text, "History not captured for this original outcome",
                       "an unpriced placeholder stays reachable with its own absence")
        XCTAssertEqual(Page(input: Tests.input(.final), originals: Tests.fullOriginals(.final), onCatalogue: {}).model
            .catalogueAvailable(canOpen: true, originals: Tests.fullOriginals(.final)), true)
    }

    func testTheNoSideKeepsItsOwnHistoryAndIsNeverAComplement() throws {
        let m = Tests.market(Tests.kok)
        let bundle = Tests.originals(.final, held: Tests.selection(m, "No"), sideHistory: Tests.sideHistory(m, "No", .final))
        let page = Page(input: Tests.input(.final), mode: .sideHistory, originals: bundle)
        let history = try XCTUnwrap(page.sideHistoryContent()).input
        XCTAssertEqual(history.series.count, 1)
        let points = history.series[0].runs.flatMap(\.points)
        XCTAssertEqual(points.count, 206, "the No side's own 206 trades")
        XCTAssertEqual(points.map(\.probability), m.no.trades.map(\.p), "its own prices, never 1 − Yes")
        XCTAssertEqual(points.first?.probability, 0.29)
        XCTAssertNotEqual(points.first?.probability, 1 - m.yes.trades[0].p)
        XCTAssertEqual(history.series[0].id, Tests.seriesID(Tests.kok, "No"))
        let uncaptured = Tests.market(Tests.placeholderOne)
        let empty = Tests.originals(.final, held: Tests.selection(uncaptured, "No"), sideHistory: Tests.sideHistory(uncaptured, "No", .final))
        let emptyHistory = try XCTUnwrap(Page(input: Tests.input(.final), mode: .sideHistory, originals: empty).sideHistoryContent()).input
        XCTAssertTrue(emptyHistory.series[0].runs.isEmpty)
        XCTAssertEqual(emptyHistory.plotAbsence?.title, "No captured history", "an uncaptured history says so; it is not a zero")
    }

    func testAll36GoldMarketsAreReachableInTheContenderChoosersBoundedWindows() throws {
        var log: [String] = []
        let page = Page(input: Tests.input(.final), mode: .chooser, originals: Tests.fullOriginals(.final),
                        onChooserChoose: { log.append("choose:\($0.marketID)") }, onChooserControl: { log.append("control:" + Tests.words($0)) },
                        onInteraction: { log.append("hold") })
        let chooser = try XCTUnwrap(page.chooserContent())
        let model = FieldChooserModel10868(chooser.input)
        XCTAssertEqual(model.featuredRows.map(\.ref.marketID), Tests.featured)
        let groups = try XCTUnwrap(chooser.input.browse?.groups)
        XCTAssertEqual(groups.count, 6)
        XCTAssertTrue(groups.allSatisfy { $0.refs.count == 6 }, "six at a time, never 36 giant buttons")
        XCTAssertEqual(groups.flatMap(\.refs).map(\.marketID), Tests.markets.map(\.id), "all 36, once, in the owner's order")
        XCTAssertTrue(groups.flatMap(\.refs).allSatisfy { model.resolve($0) != .unavailable })
        XCTAssertEqual(model.groupRows.count, 6, "the owner's selected window")
        let placeholder = try XCTUnwrap(chooser.input.catalogue.first { $0.ref.marketID == Tests.placeholderOne })
        XCTAssertEqual(placeholder.browseStatus, "Unpriced placeholder · no captured trade")
        XCTAssertEqual(placeholder.plan.readings.first?.value, .missing("History not captured"))
        if let action = model.chooseAction(model.groupRows[2], canChoose: true) {
            action.perform(onChoose: chooser.onChoose, onControl: chooser.onControl)
        }
        if let action = model.groupAction(groups[5], canControl: true) {
            action.perform(onChoose: chooser.onChoose, onControl: chooser.onControl)
        }
        XCTAssertEqual(log, ["hold", "choose:1347943", "hold", "control:group:gold.window.5"])
    }

    func testTheOriginalGradeStaysApartFromThePhysicalFinish() throws {
        let kok = Tests.market(Tests.kok)
        let bundle = Tests.originals(.final, held: Tests.selection(kok, "Yes"))
        let content = try XCTUnwrap(Details.content(catalogue: bundle.bundle.catalogue, selection: bundle.bundle.selection))
        XCTAssertEqual(content.result?.words, "This outcome won", "the selected Yes outcome's own grade")
        guard case .recorded(let shown)? = Details.recorded(catalogue: bundle.bundle.catalogue, selection: bundle.bundle.selection,
                                                            context: bundle.bundle.recorded, hasCallback: true) else {
            return XCTFail("the recorded context matches")
        }
        XCTAssertEqual(shown.finish?.words, "Gold · 36.49 s", "the physical finish, separately")
        XCTAssertEqual(shown.content.result?.words, "This outcome won")
        let no = Tests.originals(.final, held: Tests.selection(kok, "No"))
        XCTAssertEqual(Details.content(catalogue: no.bundle.catalogue, selection: no.bundle.selection)?.result?.words,
                       "This outcome lost", "the losing No outcome keeps its own grade")
        let inegawa = Tests.market(Tests.inegawa)
        let unlinked = Tests.originals(.final, held: Tests.selection(inegawa, "Yes"))
        guard case .recorded(let unlinkedShown)? = Details.recorded(catalogue: unlinked.bundle.catalogue,
                                                                    selection: unlinked.bundle.selection,
                                                                    context: unlinked.bundle.recorded, hasCallback: true) else {
            return XCTFail("the recorded context matches")
        }
        XCTAssertEqual(unlinkedShown.finish?.words, "No linked reported finish", "no name match, no fallback")
        XCTAssertEqual(unlinkedShown.content.result?.words, "This outcome lost", "the losing Yes outcome")
        let inegawaNo = Tests.originals(.final, held: Tests.selection(inegawa, "No"))
        XCTAssertEqual(Details.content(catalogue: inegawaNo.bundle.catalogue, selection: inegawaNo.bundle.selection)?.result?.words,
                       "This outcome won", "a No outcome that won says so; never shown as a Yes result")
        XCTAssertTrue(inegawa.no.won)
        // Each side reads only its own flag: two losing sides both lose, nothing is complemented.
        let unsettledYes = Side(market: inegawa.id, side: "Yes", token: inegawa.yes.token, won: false, trades: [])
        let unsettledNo = Side(market: inegawa.id, side: "No", token: inegawa.no.token, won: false, trades: [])
        XCTAssertEqual([Tests.gradeWords(unsettledYes), Tests.gradeWords(unsettledNo)], ["This outcome lost", "This outcome lost"])
        XCTAssertNil(Details.content(catalogue: Tests.catalogue(.before), selection: Tests.selection(kok, "Yes"))?.result,
                     "no grade before the final")
    }

    // MARK: - Phase admission (headline, chrome, cards, originals)

    func testMatchingPhasesAdmitEveryBundleAndChromeSurface() throws {
        for phase in [Phase.before, .final] {
            let input = Tests.input(phase, chrome: Tests.chrome(phase, stream: Tests.stream(phase)))
            let page = Page(input: input, originals: Tests.fullOriginals(phase), onAbout: {}, onView: { _ in },
                            onCatalogue: {}, onReaderIntent: { _ in })
            let model = page.model
            XCTAssertNotNil(model.headline, "\(phase)")
            XCTAssertNotNil(model.chrome)
            XCTAssertEqual(model.notice, Tests.notice(phase))
            XCTAssertEqual(page.viewChoicesContent()?.group, Tests.views(phase))
            XCTAssertEqual(model.readerHeader?.title, "Women's 500m · \(Tests.phaseWords(phase))")
            XCTAssertEqual(model.stream, Tests.stream(phase))
            XCTAssertEqual(model.storyLink("expectations-card")?.card, .expectations)
            XCTAssertEqual(model.about, Tests.about(phase))
            XCTAssertTrue(model.aboutAvailable(canOpen: true))
            XCTAssertNotNil(page.headlineAboutAction)
            XCTAssertNotNil(page.readerAboutAction)
            XCTAssertNotNil(page.aboutContent())
            XCTAssertNotNil(model.presentedHistory)
            XCTAssertNotNil(model.expectations)
            XCTAssertEqual(model.finish != nil, phase == .final)
            XCTAssertNotNil(page.chooserContent())
            XCTAssertNotNil(page.catalogueContent())
            XCTAssertNotNil(page.sideChoicesContent())
            XCTAssertNotNil(page.originalDetailsContent())
            XCTAssertNotNil(page.sideHistoryContent())
            XCTAssertNotNil(page.catalogueAction)
            XCTAssertFalse(model.readerSequence.isEmpty)
        }
    }

    func testAnEarlierPageWithLaterBundlesShowsNoLaterWordsOrActions() throws {
        try assertNoLaterSurface(page: .before, bundles: .final)
        try assertNoLaterSurface(page: .during, bundles: .final)
    }

    func testALaterPageWithEarlierBundlesShowsNoEarlierContentOrActions() throws {
        try assertNoLaterSurface(page: .final, bundles: .before)
    }

    /// Each surface fails its own assertion if it read the raw channel.
    private func assertNoLaterSurface(page phase: Phase, bundles other: Phase) throws {
        var log: [String] = []
        let input = Tests.input(phase, headline: Tests.headline(other),
                                chrome: Tests.chrome(other, stream: Tests.stream(other), readerOrder: [.expectations, .history]),
                                history: TimedFieldHistoryBundle10868(phase: other, history: Tests.history(other), readerPlotHeight: 390),
                                finish: Tests.finish(other), expectations: Tests.expectations(other))
        let bundle = Tests.fullOriginals(other)
        func page(_ mode: TimedFieldEventPageMode10868 = .page) -> Page {
            Page(input: input, mode: mode, originals: bundle, onAbout: { log.append("about") }, onLink: { _ in log.append("link") },
                 onView: { _ in log.append("view") }, onHistoryAction: { _ in log.append("history") },
                 onChooserChoose: { _ in log.append("choose") }, onFinishChoose: { _ in log.append("finish") },
                 onFinishWindow: { _ in log.append("window") }, onExpectationOpen: { _ in log.append("expect") },
                 onCatalogue: { log.append("catalogue") }, onCatalogueSelect: { _ in log.append("select") },
                 onSide: { _ in log.append("side") }, onOriginalHistory: { _ in log.append("original") },
                 onSideHistoryAction: { _ in log.append("sideHistory") }, onStoryIntent: { _ in log.append("story") },
                 onCardOpen: { _ in log.append("card") }, onReaderIntent: { log.append("reader:" + Tests.words($0)) },
                 onInteraction: { log.append("hold") })
        }
        let model = page().model
        let label = "\(phase) page, \(other) bundles"
        // Headline.
        XCTAssertNil(model.headline, label)
        XCTAssertNil(model.actual, label)
        XCTAssertNil(page().headlineContent(), label)
        XCTAssertNil(page().headlineAboutAction, label)
        // Chrome (S1): notice, views, reader header, stream, links, order, Info.
        XCTAssertNil(model.chrome, label)
        XCTAssertNil(model.notice, "\(label): notice")
        XCTAssertNil(model.views, "\(label): views")
        XCTAssertNil(page().viewChoicesContent(), "\(label): view choices")
        XCTAssertNil(model.readerHeader, "\(label): reader header")
        XCTAssertNil(model.stream, "\(label): stream")
        XCTAssertFalse(model.showsCardsDirectly, "\(label): no stream decision, no direct cards")
        XCTAssertEqual(model.directCards, [])
        XCTAssertNil(model.storyLink("expectations-card"), "\(label): story link")
        XCTAssertNil(model.storyLink("finish-card"))
        XCTAssertEqual(model.readerSequence, [], "\(label): reader order")
        XCTAssertNil(model.about, "\(label): Info")
        XCTAssertFalse(model.aboutAvailable(canOpen: true))
        XCTAssertNil(page(.about).aboutContent(), "\(label): About mode content")
        XCTAssertNil(page(.reader(.history)).readerAboutAction)
        // Cards.
        XCTAssertNil(model.history, label)
        XCTAssertNil(page().historyContent(reader: false))
        XCTAssertNil(page(.reader(.history)).historyContent(reader: true))
        XCTAssertEqual(model.unavailableWords(.history), "Gold history is not available for this view")
        XCTAssertNil(model.finish, label)
        XCTAssertNil(page().finishContent(.page))
        XCTAssertNil(page().finishContent(.reader))
        XCTAssertNil(page().finishWindowsContent(.page))
        XCTAssertNil(model.expectations, label)
        XCTAssertNil(page().expectationsContent(.page))
        XCTAssertNil(page().expandAction(.expectations), "no admitted chrome, no direct card expand")
        // Originals.
        XCTAssertNil(model.admitted(bundle), label)
        XCTAssertTrue(model.originalsAreForAnotherPhase(bundle))
        XCTAssertNil(page(.chooser).chooserContent())
        XCTAssertNil(page(.catalogue).catalogueContent())
        XCTAssertNil(page(.catalogue).catalogueWindowsContent())
        XCTAssertNil(page().catalogueAction)
        XCTAssertNil(page(.original).sideChoicesContent())
        XCTAssertNil(page(.original).originalDetailsContent())
        XCTAssertNil(page(.sideHistory).sideHistoryContent())
        // Words.
        let forbidden = other == .final ? Tests.finalOnly : ["Before race day", "Retained trades before race day"]
        XCTAssertEqual(Tests.leaks(Tests.texts(input, bundle), forbidden), [], label)
        // Back stays; nothing else acts.
        XCTAssertEqual(log, [])
        page(.sideHistory).sideHistoryBack?()
        let controls = page(.reader(.history)).readerControls(.history)
        XCTAssertTrue(controls.canGoBack)
        XCTAssertNil(controls.previous)
        XCTAssertNil(controls.next)
        XCTAssertEqual(log, ["reader:back"], "Back is the exact intent, with no hold")
    }

    func testThePhaseLeakGuardCatchesTheLeaksItWasWrittenFor() {
        let finalWords = Tests.texts(Tests.input(.final), Tests.fullOriginals(.final))
        XCTAssertFalse(Tests.leaks(finalWords, Tests.finalOnly).isEmpty, "positive control: a final page does show final words")
        for word in ["36.49", "Reported final", "This outcome won", "Silver", "About this final"] {
            XCTAssertFalse(Tests.leaks(finalWords, [word]).isEmpty, "positive control for \(word)")
        }
        XCTAssertEqual(Tests.leaks(Tests.texts(Tests.input(.before), Tests.fullOriginals(.before)), Tests.finalOnly), [])
        // A raw-channel read would leak: the final chrome's own words are final-only.
        let chromeWords = [Tests.notice(.final), Tests.about(.final).title] + Tests.about(.final).sections.flatMap(\.paragraphs)
        XCTAssertFalse(Tests.leaks(chromeWords, Tests.finalOnly).isEmpty)
    }

    func testTheConstructedDuringPageIsAnExplicitPhaseThatNeverBorrowsBeforeOrFinalBundles() throws {
        let during = Model(Tests.input(.during))
        XCTAssertEqual(during.headline?.copy.subtitle, "During the race · constructed frame")
        XCTAssertEqual(during.notice, "CONSTRUCTED during frame · not live race evidence")
        XCTAssertNotNil(during.history, "the owner's during history bundle, admitted as during")
        XCTAssertNil(during.finish)
        XCTAssertNil(during.expectations)
        XCTAssertEqual(during.mountedCards, [.history, .expectations])
        XCTAssertNil(Model(Tests.input(.during, headline: Tests.headline(.before))).headline, "never coerced to before")
        XCTAssertNil(Model(Tests.input(.during, chrome: Tests.chrome(.final))).chrome, "never coerced to final")
        XCTAssertNil(Model(Tests.input(.during, history: Tests.historyBundle(.before))).history)
        XCTAssertNil(Model(Tests.input(.during)).admitted(Tests.fullOriginals(.before)))
        XCTAssertNotNil(Model(Tests.input(.during)).admitted(Tests.fullOriginals(.before, admittedFor: .during)),
                        "a bundle the owner admits for during is read as during")
    }

    // MARK: - Holds and exact callbacks

    func testEveryPageActionHoldsOnceThenHandsBackItsExactValue() throws {
        var log: [String] = []
        let page = Page(input: Tests.input(.final), originals: Tests.fullOriginals(.final),
                        onAbout: { log.append("about") }, onView: { log.append("view:\($0)") },
                        onHistoryAction: { log.append("history:\($0)") },
                        onHistoryInspectionChoice: { log.append("choice:\($0)") },
                        onHistoryPlotPosition: { log.append("position:\($0)") },
                        onFinishChoose: { log.append("finisher:\($0.resultID)") },
                        onFinishOpenOriginal: { log.append("gold:\($0.marketID)") },
                        onFinishWindow: { log.append("window:\($0)") },
                        onExpectationOpen: { log.append("expect:\($0.observation ?? "-")") },
                        onCatalogue: { log.append("catalogue") }, onCardOpen: { log.append("card:\($0.rawValue)") },
                        onReaderIntent: { _ in log.append("reader") }, onInteraction: { log.append("hold") })
        _ = (page.headlineContent(), page.historyContent(reader: false), page.finishContent(.page),
             page.expectationsContent(.page), page.catalogueAction, page.viewChoicesContent())
        XCTAssertEqual(log, [], "building and reading the page calls nothing")
        page.headlineContent()?.onAbout?()
        let views = try XCTUnwrap(page.viewChoicesContent())
        views.action(views.group.choices[0])?()
        page.historyContent(reader: false)?.onAction?("details.gold")
        page.historyContent(reader: false)?.onInspectionChoice?("1347941:Yes:46")
        page.historyContent(reader: false)?.onPlotPosition?(1_771_109_125)
        let finish = try XCTUnwrap(page.finishContent(.page))
        finish.onChooseResult?(Tests.finishRef("13"))
        finish.onOpenOriginal?(Tests.goldRef(Tests.kok))
        page.finishWindowsContent(.page)?.onChoose?("finish.window.1")
        page.expectationsContent(.page)?.onOpen?(FieldMovementOpen10868(ref: Tests.goldRef(Tests.jackson), observation: "1347949:Yes:12"))
        page.expandAction(.finish)?()
        page.expandAction(.expectations)?()
        page.catalogueAction?()
        XCTAssertEqual(log, ["hold", "about", "hold", "view:view.before", "hold", "history:details.gold",
                             "hold", "choice:1347941:Yes:46", "hold", "position:1771109125.0", "hold", "finisher:13",
                             "hold", "gold:1347941", "hold", "window:finish.window.1", "hold", "expect:1347949:Yes:12",
                             "hold", "card:finish", "hold", "card:expectations", "hold", "catalogue"])
        XCTAssertEqual(page.model.input.phase, .final, "a view choice requests; the owner decides the phase")
        XCTAssertNil(page.expandAction(.history), "the anchor expands through its own owner action")
    }

    func testChooserCatalogueAndDetailsActionsHoldOnceThenHandBackExactPayloads() throws {
        var log: [String] = []
        let bundle = Tests.fullOriginals(.final)
        func page(_ mode: TimedFieldEventPageMode10868) -> Page {
            Page(input: Tests.input(.final), mode: mode, originals: bundle,
                 onChooserChoose: { log.append("choose:\($0.marketID)") }, onChooserControl: { log.append("control:" + Tests.words($0)) },
                 onCatalogueWindow: { log.append("window:\($0)") },
                 onCatalogueSelect: { log.append("select:\($0.identity.market):\($0.identity.side)") },
                 onSide: { log.append("side:\($0.identity.side)") },
                 onOriginalHistory: { log.append("original:\($0.entry):\($0.actionID)") }, onInteraction: { log.append("hold") })
        }
        page(.chooser).chooserContent()?.onChoose?(Tests.goldRef(Tests.pergher))
        page(.chooser).chooserContent()?.onControl?(.toggleBrowse(id: "gold.browse"))
        let windows = try XCTUnwrap(page(.catalogue).catalogueWindowsContent())
        XCTAssertEqual(windows.group.choices.count, 6)
        windows.action(windows.group.choices[3])?()
        let catalogue = try XCTUnwrap(page(.catalogue).catalogueContent())
        let cards = OriginalMarketCatalogue9483.cards(catalogue: catalogue.catalogue, selection: catalogue.selection,
                                                      labels: catalogue.labels, unavailableChoice: catalogue.unavailableChoice)
        OriginalMarketCatalogue9483.action(cards[1], onSelect: catalogue.onSelect)?()
        let sides = try XCTUnwrap(page(.original).sideChoicesContent())
        sides.action(bundle.bundle.sides[1])?()
        let details = try XCTUnwrap(page(.original).originalDetailsContent())
        details.onHistory?(Details.HistoryIntent(selection: Tests.selection(Tests.market(Tests.kok), "Yes"), entry: .expand,
                                                 actionID: "original.expand"))
        XCTAssertEqual(log, ["hold", "choose:1347952", "hold", "control:browse:gold.browse",
                             "hold", "window:originals.window.3", "hold", "select:1347941:No", "hold", "side:No",
                             "hold", "original:expand:original.expand"])
    }

    func testFullSizeSideHistoryAndInfoKeepTheExactCallbacksWithNoHold() throws {
        var log: [String] = []
        let bundle = Tests.fullOriginals(.final)
        func page(_ mode: TimedFieldEventPageMode10868) -> Page {
            Page(input: Tests.input(.final), mode: mode, originals: bundle, onAbout: { log.append("about") },
                 onLink: { log.append("link:\($0.id)") }, onHistoryAction: { log.append("history:\($0)") },
                 onFinishChoose: { log.append("finisher:\($0.resultID)") }, onFinishWindow: { log.append("window:\($0)") },
                 onExpectationOpen: { log.append("expect:\($0.ref.marketID)") },
                 onSideHistoryAction: { log.append("side:\($0)") }, onReaderIntent: { log.append("reader:" + Tests.words($0)) },
                 onInteraction: { log.append("hold") })
        }
        page(.reader(.history)).historyContent(reader: true)?.onAction?("window.final")
        page(.reader(.finish)).finishContent(.reader)?.onChooseResult?(Tests.finishRef("1"))
        page(.reader(.finish)).finishWindowsContent(.reader)?.onChoose?("finish.window.2")
        page(.reader(.expectations)).expectationsContent(.reader)?.onOpen?(FieldMovementOpen10868(ref: Tests.goldRef(Tests.leerdam),
                                                                                                    observation: "1347948:Yes:50"))
        page(.reader(.history)).readerAboutAction?()
        page(.about).aboutContent()?.linkAction(Tests.resultLink)?()
        page(.sideHistory).sideHistoryContent()?.onAction?("side.previous")
        page(.sideHistory).sideHistoryBack?()
        XCTAssertEqual(log, ["history:window.final", "finisher:1", "window:finish.window.2", "expect:1347948", "about",
                             "link:result-source", "side:side.previous", "reader:back"])
    }

    func testACardInTheStreamHoldsThroughItsOwnActivationOnly() throws {
        var log: [String] = []
        let stream = Tests.stream(.final)
        let input = Tests.input(.final, chrome: Tests.chrome(.final, stream: stream))
        let page = Page(input: input, onFinishChoose: { log.append("finisher:\($0.resultID)") },
                        onFinishWindow: { log.append("window:\($0)") }, onExpectationOpen: { log.append("expect:\($0.ref.marketID)") },
                        onCardOpen: { log.append("card:\($0.rawValue)") }, onInteraction: { log.append("hold") })
        XCTAssertEqual(page.model.directCards, [], "with a stream the cards live in it")
        XCTAssertNil(page.expandAction(.finish), "the stream offers its own open")
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let ref = Stream.CardRef(scope: stream.scope, id: "finish-card")
        let activation = StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
            if case .interaction = intent { log.append("activate") } else { log.append("other") }
        }
        let finish = try XCTUnwrap(page.finishContent(.stream(activation)))
        finish.onChooseResult?(Tests.finishRef("3"))
        page.finishWindowsContent(.stream(activation))?.onChoose?("finish.window.1")
        page.expectationsContent(.stream(activation))?.onOpen?(FieldMovementOpen10868(ref: Tests.goldRef(Tests.kok), observation: nil))
        XCTAssertEqual(log, ["activate", "finisher:3", "activate", "window:finish.window.1", "activate", "expect:1347941"],
                       "the stream's activation once per action, never the page hook as well")
        XCTAssertEqual(page.model.storyLink("finish-card")?.card, .finish)
        XCTAssertEqual(page.model.storyLink("expectations-card")?.card, .expectations)
        XCTAssertNil(page.model.storyLink("unknown-card"))
        let doubled = Tests.input(.final, chrome: Tests.chrome(.final, stream: stream, stories: Tests.storyLinks + [Tests.storyLinks[0]]))
        XCTAssertNil(Model(doubled).storyLink("finish-card"), "two links for one card id name no card")
        let anchorLink = Tests.input(.final, chrome: Tests.chrome(.final, stream: stream, stories: [
            TimedFieldEventPageStory10868(cardID: "finish-card", card: .history)]))
        XCTAssertNil(Model(anchorLink).storyLink("finish-card"), "the anchor is never a stream card")
    }

    func testAbsentCallbacksOfferNoControlAndTheHookAloneDoesNothing() throws {
        var log: [String] = []
        let page = Page(input: Tests.input(.final), originals: Tests.fullOriginals(.final), onInteraction: { log.append("hold") })
        XCTAssertNil(page.headlineContent()?.onAbout)
        XCTAssertNil(page.headlineAboutAction)
        XCTAssertNil(page.viewChoicesContent()?.onChoose)
        XCTAssertNil(page.historyContent(reader: false)?.onAction)
        XCTAssertNil(page.historyContent(reader: false)?.onInspectionChoice)
        XCTAssertNil(page.historyContent(reader: false)?.onPlotPosition)
        XCTAssertNil(page.finishContent(.page)?.onChooseResult)
        XCTAssertNil(page.finishContent(.page)?.onOpenOriginal)
        XCTAssertNil(page.finishWindowsContent(.page)?.onChoose)
        XCTAssertNil(page.expectationsContent(.page)?.onOpen)
        XCTAssertNil(page.expandAction(.finish))
        XCTAssertNil(page.chooserContent()?.onChoose)
        XCTAssertNil(page.chooserContent()?.onControl)
        XCTAssertNil(page.catalogueContent()?.onSelect)
        XCTAssertNil(page.catalogueWindowsContent()?.onChoose)
        XCTAssertNil(page.sideChoicesContent()?.onSide)
        XCTAssertNil(page.originalDetailsContent()?.onHistory)
        XCTAssertNil(page.sideHistoryContent()?.onAction)
        XCTAssertNil(page.catalogueAction)
        XCTAssertNil(page.readerAboutAction)
        XCTAssertNil(page.sideHistoryBack)
        XCTAssertFalse(page.readerControls(.finish).canGoBack)
        XCTAssertEqual(log, [])
    }

    // MARK: - Reader order, Back and compact/full equivalence

    func testTheDefaultReaderOrderIsThePagesOrderOfPresentCards() {
        XCTAssertEqual(Model(Tests.input(.final)).readerSequence, [.history, .finish, .expectations])
        XCTAssertEqual(Model(Tests.input(.before)).readerSequence, [.history, .expectations])
        XCTAssertEqual(Model(Tests.input(.during)).readerSequence, [.history, .expectations])
        let final = Model(Tests.input(.final))
        XCTAssertEqual(final.neighbour(of: .history, offset: 1), .finish)
        XCTAssertEqual(final.neighbour(of: .finish, offset: -1), .history)
        XCTAssertEqual(final.neighbour(of: .finish, offset: 1), .expectations)
        XCTAssertNil(final.neighbour(of: .expectations, offset: 1))
        XCTAssertNil(final.neighbour(of: .history, offset: -1))
        XCTAssertEqual(Model(Tests.input(.before)).neighbour(of: .history, offset: 1), .expectations, "the withheld finish is not a stop")
    }

    func testTheOwnersReaderOrderDrivesNeighbourNamesAndExactIntentsThroughAStreamRerank() throws {
        var log: [String] = []
        let order: [Card] = [.expectations, .finish, .history]
        func page(_ finishFirst: Bool) -> Page {
            Page(input: Tests.input(.final, chrome: Tests.chrome(.final, stream: Tests.stream(.final, finishFirst: finishFirst),
                                                                 readerOrder: order)),
                 mode: .reader(.finish), onReaderIntent: { log.append(Tests.words($0)) })
        }
        let controls = page(true).readerControls(.finish)
        XCTAssertEqual(controls.previous, .expectations)
        XCTAssertEqual(controls.next, .history)
        XCTAssertTrue(controls.canGoBack)
        let reranked = page(false).readerControls(.finish)
        XCTAssertEqual(reranked.previous, .expectations, "the held reader order is independent of the stream's rerank")
        XCTAssertEqual(reranked.next, .history)
        XCTAssertEqual(page(true).model.cardName(.expectations), "Before the race")
        XCTAssertEqual(page(true).model.cardName(.history), "Gold history")
        Page.bind(page(true).onReaderIntent, .previous(.expectations))?()
        Page.bind(page(true).onReaderIntent, .next(.history))?()
        Page.bind(page(true).onReaderIntent, .back)?()
        XCTAssertEqual(log, ["previous:expectations", "next:history", "back"], "exact intents, no hold")
    }

    func testAnEmptyAbsentDuplicatedOrUnpresentReaderEntryOffersNoNeighbour() {
        let empty = Model(Tests.input(.final, chrome: Tests.chrome(.final, readerOrder: [])))
        XCTAssertNil(empty.neighbour(of: .history, offset: 1))
        let missing = Model(Tests.input(.final, chrome: Tests.chrome(.final, readerOrder: [.history, .expectations])))
        XCTAssertNil(missing.neighbour(of: .finish, offset: 1), "a card the owner did not list has no neighbour")
        XCTAssertEqual(missing.neighbour(of: .history, offset: 1), .expectations)
        let doubled = Model(Tests.input(.final, chrome: Tests.chrome(.final, readerOrder: [.history, .finish, .history, .expectations])))
        XCTAssertNil(doubled.neighbour(of: .history, offset: 1), "listed twice: no position")
        XCTAssertNil(doubled.neighbour(of: .finish, offset: 1), "the next entry is listed twice")
        XCTAssertNil(doubled.neighbour(of: .finish, offset: -1))
        let early = Model(Tests.input(.before, chrome: Tests.chrome(.before, readerOrder: [.history, .finish, .expectations])))
        XCTAssertNil(early.neighbour(of: .history, offset: 1), "never skips over a withheld card")
        XCTAssertNil(early.neighbour(of: .expectations, offset: -1))
    }

    func testAFinishReaderCarriedIntoAnEarlierPhaseKeepsBackAndShowsNoFinishData() throws {
        for phase in [Phase.before, .during] {
            var log: [String] = []
            let page = Page(input: Tests.input(phase), mode: .reader(.finish),
                            onFinishChoose: { _ in log.append("finisher") }, onFinishWindow: { _ in log.append("window") },
                            onReaderIntent: { log.append(Tests.words($0)) }, onInteraction: { log.append("hold") })
            let controls = page.readerControls(.finish)
            XCTAssertTrue(controls.canGoBack, "\(phase): Back stays")
            XCTAssertNil(controls.previous)
            XCTAssertNil(controls.next)
            XCTAssertFalse(page.model.isMounted(.finish))
            XCTAssertNil(page.finishContent(.reader), "\(phase): no finish rows")
            XCTAssertNil(page.finishWindowsContent(.reader))
            XCTAssertEqual(Tests.leaks(Tests.texts(page.model.input, nil), Tests.finalOnly), [], "\(phase): no actual or grade")
            Page.bind(page.onReaderIntent, .back)?()
            XCTAssertEqual(log, ["back"], "the exact Back intent, with no hold")
            #if canImport(UIKit)
            let host = hostForMeasurement(page, at: .large)
            let fitted = host.sizeThatFits(in: CGSize(width: 375, height: CGFloat.greatestFiniteMagnitude))
            XCTAssertTrue(fitted.height.isFinite && fitted.height > 0, "\(phase): the reader renders its Back and the owner's words")
            #endif
        }
        // The final positive: a mounted finish reader keeps Back and its neighbours.
        let final = Page(input: Tests.input(.final), mode: .reader(.finish), onReaderIntent: { _ in })
        let controls = final.readerControls(.finish)
        XCTAssertTrue(controls.canGoBack)
        XCTAssertEqual(controls.previous, .history)
        XCTAssertEqual(controls.next, .expectations)
        XCTAssertNotNil(final.finishContent(.reader))
        // A chrome for another phase keeps Back too.
        let refused = Page(input: Tests.input(.final, chrome: Tests.chrome(.before)), mode: .reader(.finish), onReaderIntent: { _ in })
        XCTAssertTrue(refused.readerControls(.finish).canGoBack)
        XCTAssertNil(refused.readerControls(.finish).previous)
        XCTAssertNil(refused.readerControls(.finish).next)
    }

    func testWithoutReaderIntentsThereIsNoBackControl() {
        for phase in Phase.allCases {
            let page = Page(input: Tests.input(phase), mode: .reader(.finish))
            XCTAssertFalse(page.readerControls(.finish).canGoBack, "\(phase): no callback, no Back")
            XCTAssertFalse(page.readerControls(.history).canGoBack)
            XCTAssertNil(page.sideHistoryBack)
            XCTAssertNil(Page.bind(page.onReaderIntent, .back))
        }
    }

    func testCompactAndFullSizeMountTheSameCardBodiesFromTheSameInputs() throws {
        let stream = Tests.stream(.final)
        let page = Page(input: Tests.input(.final), onFinishChoose: { _ in }, onExpectationOpen: { _ in })
        let streamed = Page(input: Tests.input(.final, chrome: Tests.chrome(.final, stream: stream)), onFinishChoose: { _ in },
                            onExpectationOpen: { _ in })
        let activation = StoryStreamCardActivation10868(card: Stream.CardRef(scope: stream.scope, id: "finish-card"), intents: [], send: nil)
        let compact = try XCTUnwrap(page.finishContent(.page))
        let full = try XCTUnwrap(page.finishContent(.reader))
        let inStream = try XCTUnwrap(streamed.finishContent(.stream(activation)))
        XCTAssertEqual(compact.input, full.input)
        XCTAssertEqual(compact.input, inStream.input)
        XCTAssertEqual(page.finishWindowsContent(.page)?.group, page.finishWindowsContent(.reader)?.group)
        XCTAssertEqual(try XCTUnwrap(page.expectationsContent(.page)).input, try XCTUnwrap(page.expectationsContent(.reader)).input)
        XCTAssertNotNil(compact.onChooseResult)
        XCTAssertNotNil(full.onChooseResult)
        XCTAssertNotNil(inStream.onChooseResult, "an activation without a sender relays the exact callback")
        XCTAssertEqual(page.model.cardName(.finish), "Actual finish gaps")
        XCTAssertEqual(page.model.directCards, [.finish, .expectations], "expand rows over the same bodies")
    }

    // MARK: - Arrivals, omissions, restores, foreign, duplicate and future keys

    func testTheHeldOriginalMissingRestoredDuplicatedOrForeignBorrowsNothing() throws {
        let kok = Tests.market(Tests.kok)
        let held = Tests.selection(kok, "Yes")
        let present = Tests.originals(.final, held: held)
        XCTAssertFalse(CeremonyEventPageModel10868.heldOriginalIsUnavailable(present.bundle))
        let omitted = Tests.originals(.final, held: held, catalogue: Tests.catalogue(.final, dropping: held.identity))
        XCTAssertTrue(CeremonyEventPageModel10868.heldOriginalIsUnavailable(omitted.bundle), "omitted: the owner's words, no neighbour")
        XCTAssertNil(Details.content(catalogue: omitted.bundle.catalogue, selection: held))
        let restored = Tests.originals(.final, held: held)
        XCTAssertEqual(Details.content(catalogue: restored.bundle.catalogue, selection: held)?.title, kok.name,
                       "restored by its exact identity")
        let duplicated = Tests.originals(.final, held: held, catalogue: Tests.catalogue(.final, duplicating: held.identity))
        XCTAssertTrue(CeremonyEventPageModel10868.heldOriginalIsUnavailable(duplicated.bundle), "a duplicated identity is ambiguous")
        let foreign = Tests.originals(.final, held: Tests.selection(kok, "Yes", scope: "timed-field|other-event"))
        XCTAssertTrue(CeremonyEventPageModel10868.heldOriginalIsUnavailable(foreign.bundle), "a foreign scope opens nothing")
        let page = Page(input: Tests.input(.final), mode: .original, originals: omitted)
        XCTAssertNotNil(page.originalDetailsContent(), "Details still mounts with the owner's own words")
        XCTAssertNil(page.sideHistoryContent())
    }

    func testTheSideHistoryShowsOnlyForExactlyTheHeldSideWithExactCallbacks() throws {
        let kok = Tests.market(Tests.kok)
        var log: [String] = []
        let exact = Tests.originals(.final, held: Tests.selection(kok, "No"), sideHistory: Tests.sideHistory(kok, "No", .final))
        let page = Page(input: Tests.input(.final), mode: .sideHistory, originals: exact,
                        onSideHistoryAction: { log.append("action:\($0)") }, onSideHistoryInspectionChoice: { log.append("choice:\($0)") },
                        onSideHistoryPlotPosition: { log.append("position:\($0)") }, onInteraction: { log.append("hold") })
        let history = try XCTUnwrap(page.sideHistoryContent())
        history.onAction?("side.next")
        history.onInspectionChoice?("1347941:No:3")
        history.onPlotPosition?(1_770_500_000)
        XCTAssertEqual(log, ["action:side.next", "choice:1347941:No:3", "position:1770500000.0"], "exact, with no hold")
        let otherSide = Tests.originals(.final, held: Tests.selection(kok, "Yes"), sideHistory: Tests.sideHistory(kok, "No", .final))
        XCTAssertNil(Page(input: Tests.input(.final), mode: .sideHistory, originals: otherSide).sideHistoryContent(),
                     "never another side's history")
        let otherPhase = Tests.originals(.final, held: Tests.selection(kok, "No"),
                                         sideHistory: Tests.sideHistory(kok, "No", .final, admittedFor: .before))
        XCTAssertNil(Page(input: Tests.input(.final), mode: .sideHistory, originals: otherPhase).sideHistoryContent(),
                     "a side history admitted for another phase is not shown")
    }

    func testTheCatalogueWindowMustBelongToTheAdmittedCatalogue() throws {
        let page = { (bundle: TimedFieldOriginals10868) in Page(input: Tests.input(.final), mode: .catalogue, originals: bundle) }
        XCTAssertNotNil(page(Tests.originals(.final, window: Tests.catalogueWindow(.final))).catalogueContent())
        let full = Tests.catalogue(.final)
        let foreignScope = Details.Catalogue(scope: "timed-field|other-event", originals: Array(full.originals.prefix(12)))
        XCTAssertNil(page(Tests.originals(.final, window: Tests.catalogueWindow(.final, override: foreignScope))).catalogueContent(),
                     "a foreign window lends no card")
        var altered = Array(full.originals.prefix(12))
        let first = altered[0]
        altered[0] = Details.Original(identity: first.identity, title: "Someone else", outcome: first.outcome, mode: first.mode,
                                      pregame: first.pregame, later: first.later, grade: first.grade, about: first.about,
                                      beforeLabel: first.beforeLabel)
        XCTAssertNil(page(Tests.originals(.final, window: Tests.catalogueWindow(.final, override: Details.Catalogue(scope: Tests.scope, originals: altered)))).catalogueContent(),
                     "a window original that is not the bundle's own is refused")
        let unknown = Details.Original(identity: Details.Identity(source: Tests.source, market: "9999999", side: "Yes"), title: "Unknown",
                                       outcome: "Yes", mode: .pregame, pregame: Details.Reading.missing("x"), later: nil, grade: nil,
                                       about: Details.About(source: nil, rules: .omitted, provenance: [], historicalQuote: nil))
        XCTAssertNil(page(Tests.originals(.final, window: Tests.catalogueWindow(.final, override: Details.Catalogue(scope: Tests.scope, originals: [unknown])))).catalogueContent(),
                     "an unknown key never borrows a neighbour")
        let duplicatedBundle = Tests.originals(.final, catalogue: Tests.catalogue(.final, duplicating: full.originals[0].identity),
                                               window: Tests.catalogueWindow(.final))
        XCTAssertNil(page(duplicatedBundle).catalogueContent(), "a duplicated bundle identity is ambiguous")
        XCTAssertFalse(Model(Tests.input(.final)).catalogueAvailable(canOpen: true, originals: duplicatedBundle))
    }

    func testSelectionsArriveDropAndRestoreOnlyByTheirExactKeys() throws {
        // Finisher selection: foreign scope, unknown id, restore.
        let foreign = TimedFinishModel10868(TimedFinishInput10868(
            scope: Tests.finishScope, catalogue: Tests.finishInput().catalogue,
            selected: TimedFinishSelected10868(ref: Tests.finishRef("2", scope: "timed-field|other"), words: "Selected",
                                               unavailableWords: "Selected finisher unavailable in this update"),
            group: Tests.finishGroup(0), axis: Tests.finishInput().axis, copy: Tests.finishCopy,
            unavailableWords: "Result unavailable in this update"))
        XCTAssertNil(foreign.selectedResult)
        XCTAssertEqual(foreign.selectionNotice, "Selected finisher unavailable in this update")
        XCTAssertNil(TimedFinishModel10868(Tests.finishInput(selected: "99")).selectedResult, "an unknown id borrows no neighbour")
        XCTAssertEqual(TimedFinishModel10868(Tests.finishInput(selected: "2")).selectedResult?.name, "Miho Takagi", "restored")
        // A duplicated result reference resolves to nothing.
        let input = Tests.finishInput()
        let duplicated = TimedFinishInput10868(scope: input.scope, catalogue: input.catalogue + [input.catalogue[0]],
                                               selected: input.selected, group: input.group, axis: input.axis, copy: input.copy,
                                               unavailableWords: input.unavailableWords)
        XCTAssertEqual(TimedFinishModel10868(duplicated).rows[0].resolution, .unavailable)
        XCTAssertNotNil(TimedFinishModel10868(duplicated).rows[1].resolution.result, "its neighbours keep theirs")
        // History selection: a contender who leaves the cohort shows the owner's words, never the first neighbour.
        var gone = Tests.history(.final)
        gone = FieldHistoryInput10868(
            title: gone.title, caption: gone.caption, series: Array(gone.series.dropFirst()),
            selection: gone.selection, domain: gone.domain, ceiling: gone.ceiling, yTicks: gone.yTicks, xTicks: gone.xTicks,
            guides: gone.guides, breaks: gone.breaks, readout: gone.readout, markKey: gone.markKey,
            comparisonExplanation: gone.comparisonExplanation, notes: gone.notes, summary: gone.summary, plotHeight: gone.plotHeight,
            unboundReadingWords: gone.unboundReadingWords, plotUnavailableWords: gone.plotUnavailableWords, windows: gone.windows,
            scale: gone.scale, moreOriginals: gone.moreOriginals, details: gone.details, expand: gone.expand, inspect: gone.inspect,
            previous: gone.previous, next: gone.next, inspection: gone.inspection, layout: gone.layout)
        let shown = try XCTUnwrap(Model(Tests.input(.final, history: TimedFieldHistoryBundle10868(phase: .final, history: gone))).presentedHistory)
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(shown), .words("This contender is not in the compared group"))
        // Chooser selection in a foreign scope resolves to nothing.
        let chooser = Tests.chooser(.final)
        let foreignChooser = FieldChooserInput10868(
            scope: chooser.scope, intro: chooser.intro, featured: chooser.featured, context: chooser.context, more: chooser.more,
            browse: chooser.browse, catalogue: chooser.catalogue, frame: chooser.frame,
            selected: FieldChooserSelected10868(ref: Tests.goldRef(Tests.kok, scope: "timed-field|other"), words: "In focus",
                                                unavailableWords: "The selected market is not in this update"),
            unavailableWords: chooser.unavailableWords, chooseHint: chooser.chooseHint)
        XCTAssertEqual(FieldChooserModel10868(foreignChooser).selectionNotice, "The selected market is not in this update")
    }

    func testAFutureKeyedPayloadIsRefusedAndBindsInItsOwnFrame() {
        // The finish card's stream key on a before page names a card this phase does not present.
        let early = Model(Tests.input(.before, chrome: Tests.chrome(.before, stream: Tests.stream(.final))))
        XCTAssertNil(early.storyLink("finish-card"), "a future-keyed card is refused")
        XCTAssertEqual(early.storyLink("expectations-card")?.card, .expectations, "control: a present card still binds")
        // Positive control: the same key binds in its own final frame.
        let final = Model(Tests.input(.final, chrome: Tests.chrome(.final, stream: Tests.stream(.final))))
        XCTAssertEqual(final.storyLink("finish-card")?.card, .finish)
        // A future-keyed held original: a final-only selection key on a before page's catalogue still opens, but its grade does not.
        let held = Tests.selection(Tests.market(Tests.kok), "Yes")
        XCTAssertNil(Details.content(catalogue: Tests.catalogue(.before), selection: held)?.result)
        XCTAssertEqual(Details.content(catalogue: Tests.catalogue(.final), selection: held)?.result?.words, "This outcome won")
        // A future observation key: a reading whose id is not a drawn point of this frame does not show a figure.
        let kok = Tests.market(Tests.kok).yes
        let later = kok.trades[154]
        let input = Tests.history(.before, series: [
            FieldHistorySeries10868(id: Tests.seriesID(Tests.kok), name: "Femke Kok (NED)", shape: .circle, tint: .blue,
                                    runs: Tests.runs(kok, .before), links: [], labelPointID: nil,
                                    before: Tests.observation(kok, later, prefix: "Before race day · "),
                                    recorded: .absent(words: "No trade inspected"), absentWords: nil, choose: nil),
        ])
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(input.series[0], in: input).first?.display,
                       .words("No trade at the inspected moment"), "a later trade's key is unbound in the before frame")
        let bound = Tests.history(.before)
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(bound.series[0], in: bound).first?.display,
                       .figure("78%", provenance: "Before race day · " + Tests.clock(1_771_109_125)), "control: its own key binds")
    }

    // MARK: - Layout, targets, words and hosted measurements (prepared, NOT RUN)

    func testLayoutPlansStackOnPhonesAndAccessibilitySizesAndKeepOneReadingOrder() {
        XCTAssertEqual(RugbyMatchEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked], "375 / 393")
        XCTAssertEqual(RugbyMatchEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked], "wide")
        XCTAssertEqual(RugbyMatchEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked], "AX3")
        XCTAssertEqual(Model.chanceArrangements(accessibilitySize: false), [.sideBySide, .stacked], "normal and XXXL try side by side")
        XCTAssertEqual(Model.chanceArrangements(accessibilitySize: true), [.stacked])
        XCTAssertFalse(DynamicTypeSize.xxxLarge.isAccessibilitySize)
        XCTAssertTrue(DynamicTypeSize.accessibility3.isAccessibilitySize)
        XCTAssertEqual(Model.readingOrder, [.headline, .notice, .choices, .anchor, .stories, .catalogue])
        XCTAssertGreaterThan(Model.sortPriority(.headline), Model.sortPriority(.anchor))
        XCTAssertGreaterThan(Model.sortPriority(.anchor), Model.sortPriority(.stories))
        XCTAssertGreaterThan(Model.sortPriority(.stories), Model.sortPriority(.catalogue))
    }

    func testEveryControlTargetIsAtLeastTheMinimum() {
        XCTAssertEqual(EsportsEventPageModel10868.minimumTarget, 44)
        XCTAssertEqual(EsportsEventPageModel10868.targetHeight(.nan), 44)
        XCTAssertEqual(EsportsEventPageModel10868.targetHeight(30), 44, "smaller text never shrinks a control")
        #if canImport(UIKit)
        let metrics = UIFontMetrics(forTextStyle: .body)
        func scaled(_ size: UIContentSizeCategory) -> CGFloat {
            metrics.scaledValue(for: 44, compatibleWith: UITraitCollection(preferredContentSizeCategory: size))
        }
        XCTAssertEqual(EsportsEventPageModel10868.targetHeight(scaled(.large)), 44)
        XCTAssertEqual(EsportsEventPageModel10868.targetHeight(scaled(.extraExtraExtraLarge)), scaled(.extraExtraExtraLarge))
        XCTAssertEqual(EsportsEventPageModel10868.targetHeight(scaled(.accessibilityExtraExtraExtraLarge)),
                       scaled(.accessibilityExtraExtraExtraLarge), "AX3 grows the control")
        #endif
    }

    func testSpokenWordsCarryWholeNamesRolesFiguresUnitsAndDates() throws {
        let final = try XCTUnwrap(Model(Tests.input(.final)).headline)
        let slots = Model.chanceSlots(final.chances[1], unreadable: final.readingUnavailable)
        XCTAssertEqual(slots.first?.spoken, "Before race day 22.6%, " + Tests.clock(1_771_107_553))
        XCTAssertEqual(final.chances[1].name, "Jutta Leerdam (NED)", "the whole name")
        let leaf = TimedFinishModel10868(Tests.finishInput(window: 1))
        let tied = leaf.rowSummary(leaf.rows[0])
        XCTAssertTrue(tied.contains("Andżelika Wójcik"), tied)
        XCTAssertTrue(tied.contains("37.914"), tied)
        XCTAssertTrue(tied.contains("Tied 11th"), tied)
        let shift = PreEventShiftModel10868(Tests.expectations(.final))
        let row = shift.rowSummary(shift.rows[2])
        XCTAssertTrue(row.contains("Erin Jackson (USA)"), row)
        XCTAssertTrue(row.contains("1.4%"), row)
        XCTAssertTrue(row.contains(Tests.clock(1_771_107_825)), row)
        let absent = Model.chanceSlots(TimedFieldChanceContext10868(
            name: "Placeholder 1", shape: .square, tint: .gray, meaning: nil,
            earlier: Tests.dated("Before race day", Tests.market(Tests.placeholderOne).yes, nil, missing: "No captured trade before race day"),
            later: nil), unreadable: "x")
        XCTAssertEqual(absent.first?.spoken, "Before race day: No captured trade before race day", "absence is spoken, never a zero")
    }

    func testThePageAndEveryModeHaveAFiniteHeightAtPhoneWideXXXLAndAX3() {
        #if canImport(UIKit)
        let bundle = Tests.fullOriginals(.final)
        let modes: [TimedFieldEventPageMode10868] = [.page, .reader(.history), .reader(.finish), .reader(.expectations), .chooser,
                                                     .catalogue, .original, .sideHistory, .about]
        for phase in [Phase.before, .final] {
            for width in [CGFloat(375), 393, 1024] {
                for size in [DynamicTypeSize.large, .xxxLarge, .accessibility3] {
                    for mode in modes {
                        let page = Page(input: Tests.input(phase), mode: mode, originals: phase == .final ? bundle : Tests.fullOriginals(.before),
                                        onAbout: {}, onFinishChoose: { _ in }, onCatalogue: {}, onCardOpen: { _ in },
                                        onReaderIntent: { _ in })
                        let host = hostForMeasurement(page, at: size)
                        let fitted = host.sizeThatFits(in: CGSize(width: width, height: CGFloat.greatestFiniteMagnitude))
                        XCTAssertTrue(fitted.height.isFinite && fitted.height > 0, "\(phase) \(mode) at \(width) / \(size)")
                    }
                }
            }
        }
        #endif
    }

    func testTheHeadlineReflowsTallerAtLargerTextInsteadOfShrinking() {
        #if canImport(UIKit)
        let headline = TimedFieldHeadlineView10868(headline: Tests.headline(.final), actual: Model(Tests.input(.final)).actual, onAbout: {})
        var heights: [CGFloat] = []
        for size in [DynamicTypeSize.large, .xxxLarge, .accessibility3] {
            let host = hostForMeasurement(headline, at: size)
            let fitted = host.sizeThatFits(in: CGSize(width: 375, height: CGFloat.greatestFiniteMagnitude))
            XCTAssertTrue(fitted.height.isFinite)
            XCTAssertLessThanOrEqual(fitted.width, 375 + 0.5, "\(size): fits the phone width by reflow")
            heights.append(fitted.height)
        }
        XCTAssertLessThan(heights[0], heights[1], "XXXL reflows taller")
        XCTAssertLessThan(heights[1], heights[2], "AX3 reflows taller still; nothing is dropped")
        #endif
    }
}

// MARK: - Retained capture (generated, verbatim)

extension TimedFieldEventPagePresentation10868Tests {
    fileprivate static let retainedEvent = #"""
eventID|"200646"
title|"Winter Games 2026: Speed Skating - Women's 500m"
raceDate|"2026-02-15"
beforeDay|1771110000
baselineMeaning|"Last retained trade before race day begins at midnight in Milan. Not a verified closing quote."
reportAt|1771181329
actualStart|null
actualEnd|null
actualSplits|null
projection|null
resultSource|"https://en.wikipedia.org/wiki/Speed_skating_at_the_2026_Winter_Olympics_%E2%80%93_Women%27s_500_metres"
podiumReport|"https://www.theguardian.com/sport/2026/feb/15/femke-kok-dominates-500m-speed-skating-to-end-jacksons-hopes-of-retaining-olympic-title"
officialResultAccess|"HTTP403; not inspected"
identityMeaning|"Explicit isolated fixture correspondence, including reordered names and diacritics, never a production registry merge. Hiller-Donnelly remains unlinked to Hiller; no placeholder is assigned to Takagi."
alias|Na-Hyun Lee (KOR)|Lee Na-hyun
alias|Andzelika Wojcik (POL)|Andżelika Wójcik
alias|Min-Sun Kim (KOR)|Kim Min-sun
alias|Ying-Chu Chen (TPE)|Chen Ying-chu
alias|Ruining Tian (CHN)|Tian Ruining
alias|Beatrice Lamarche (CAN)|Béatrice Lamarche
"""#

    fileprivate static let retainedRules = #"""
This market will resolve according to the participant (country team or individual participant as applicable to the event) that is awarded the gold medal at the 2026 Milano-Cortina Winter Olympics for Winter Olympics 2026: Speed Skating - Women's 500m event at the time of the corresponding medal/podium ceremony. Subsequent disqualifications or amendments will not be considered.

If at any point it becomes impossible for a listed participant to win the 2026 Milano-Cortina Winter Olympics gold medal for Winter Olympics 2026: Speed Skating - Women's 500m event per the rules of IOC (e.g., participant is eliminated), the corresponding market will resolve to "No".

If multiple participants are awarded the gold medal, this market will resolve in favor of the participant whose listed name comes first alphabetically, as listed in this market group.

If this event is postponed after March 31, 2026, 11:59 PM ET, canceled, or a gold medal has not been declared within this timeframe, this market will resolve to "Other".

The resolution source will be official information from the International Olympic Committee (https://www.olympics.com/).
"""#

    fileprivate static let retainedMarkets = #"""
1347941|Femke Kok (NED)|0xbddee0620337135c0954d8536fcaeebbef430c796dcad072ca934cc710a5d000|Will Femke Kok (NED) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|0|false|R0|8015203451758424254624644018470563478761525048434806320115142348030067468557|true|6871475823121509807575753550545899827766388996691185372123240045395047814247|false
1347942|Yukino Yoshida (JPN)|0x68e2d9ebea1b410ab6c420c2fe060569d20007febc7f8ab4c98afad5dec37c83|Will Yukino Yoshida (JPN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|12|false|R0|80757224497303745581312684734267598582183119004792363331312432200956841867750|false|58527056358583447982424231640345476909285464714032683194057561130675357514432|true
1347943|Na-Hyun Lee (KOR)|0xc384f795181a487c6524c5fbcbe4a7e51903c891446b2b5f43ec73c9c8bfc2bc|Will Na-Hyun Lee (KOR) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|9|false|R0|54470245468144884217138371516853294810987211731323940498288448311812758508755|false|9783908006606713370378469904559321753694616024276183637669732064894854488336|true
1347944|Sophie Warmuth (GER)|0xf12625127a6dba014537a3db5fe599e182abd71df041d5fba6fe1244d7d61249|Will Sophie Warmuth (GER) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|7|false|R0|9984284712541184249732166617584326758480231222016162863567347396996572234993|false|34538998697754145318399369581106864845920010664829166795969935443121486754480|true
1347945|Andzelika Wojcik (POL)|0x138c4d8dc170d099f756a1fc0731ec67a849dd86c99dfc250f953693a82d7a35|Will Andzelika Wojcik (POL) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|10|false|R0|34219849858976950145342334651143152652869502729803539303931285897587276023621|false|42445084512493667311355307092441333715896094423353954259840154110300379630019|true
1347946|Kurumi Inegawa (JPN)|0x0e648bc6195a231aaf5d71270ba3c3a4ce93998fc11eddd0ed00ebd5180b581a|Will Kurumi Inegawa (JPN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|false|R0|115383264068919153806342475725002892324016091237438259615017337877802675713483|false|96477809409767878657493587540968140681574247941534676671528453546441458663595|true
1347947|Sofia Thorup (DEN)|0x00fd994e88ec955b2ad676bf9444661def72e822a2a01dc2fda7203fdb18a27c|Will Sofia Thorup (DEN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|false|R0|67550474322530414400902582688130777298007003929018644764967175347902871615594|false|47217582353736125352232670597724701894558762836950220925933975208614088748495|true
1347948|Jutta Leerdam (NED)|0x345e88b65346f1d7bd2ef488480c734cb689ff7f9075a2b68b6f7a232178e537|Will Jutta Leerdam (NED) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|1|false|R0|79914460156377571131066368245251308998571925540235970541258802787200179848437|false|102525208756289394060444361330722301526096628077651244334178251747608850688794|true
1347949|Erin Jackson (USA)|0xf127343e771e039f6b7285be09d97a851a44b2b40f3d31e0c9c8e54884a5456b|Will Erin Jackson (USA) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|4|false|R0|53304661739730347120669901078624402642379665537751793251399570729507588207289|false|14798132093109604289265564224154855324049688055172459256995792195995591502443|true
1347950|Min-Sun Kim (KOR)|0xe368cb8d0d01dbbeb49c39717bccb0dd3f37627ad21204bb6d6e69861c73fdc5|Will Min-Sun Kim (KOR) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|13|false|R0|59185097511900317797207472791119465676284870440372333737358127870713564592186|false|62011287867569879672109829072641441600607529253649872808680458217133991825112|true
1347951|Kristina Silaeva (KAZ)|0xb67b87df8cca682f17f645f7a0d6810d0c9bd87f7363959b0364db7afe7c144e|Will Kristina Silaeva (KAZ) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|17|false|R0|94208938346537204255140774934705269587933953284504286976483801855798523496760|false|98308456963826535343588955302258246710899318012949345673862343849169979731034|true
1347952|Serena Pergher (ITA)|0x813f671e9d3c8f6ab0e6b8fdbc8ecd0d3cdc7c6d8c335cdb2c13776f11c070fa|Will Serena Pergher (ITA) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|3|false|R0|112764826100350613023415955892958715542256188524722567887553665786815759034589|false|94976151210547564230681863896089037510993337069935266603588849490783668495139|true
1347953|Martyna Baran (POL)|0x78d1130be1751570bc77a0558c33d49f82d8dfdc52679875726df5b1533bdece|Will Martyna Baran (POL) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|16|false|R0|58965699085436488888710276609270231808986263341433545921203562032269946965555|false|64729820406041239175900006138681064464214162159582956068468552002002305597947|true
1347954|Rio Yamada (JPN)|0x963231bff495f4469fc938b26a04ff3e37f9a88c76c1ad914bb17c4509e90a66|Will Rio Yamada (JPN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|8|false|R0|7360852252490635503902163256873444875528123877515272011089620729620308292093|false|59690026392203814884009321286055161406674194342540014437638634127699617340991|true
1347955|Kaja Ziomek-Nogal (POL)|0x583e3a65d79bc5d4b091a69fbd9132452a37587f1a090c5eee8e37369d00e4fc|Will Kaja Ziomek-Nogal (POL) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|5|false|R0|97791940625327001884259604224033053996905487851083039006363842758707099763010|false|44809634389925324580031834870793153416916099665672922577240125009706286517479|true
1347956|Anna Boersma (NED)|0xf9d05f0c56f768f3a27f03a0862dd8f07dadbc937653d2124f114fe878933024|Will Anna Boersma (NED) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|14|false|R0|5730199196272005366858957280272156121753635672685108219725579760286712479376|false|81643381936687016471346040357752832885455877517305024262390057459938169295965|true
1347957|Ying-Chu Chen (TPE)|0x864b078182003ee07eaf2d03e41c9d47d0d94da0082f5eef18864ec414a7db71|Will Ying-Chu Chen (TPE) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|11|false|R0|5264409802799244007835773237536735658553673679612683564394820677313362076225|false|29721104688385670103900064197904569578187074496185791759393610236655442854069|true
1347958|Ruining Tian (CHN)|0xeff59630d43cab5f1f6f00215e15616042c91509e4e81c485a9d90ac0c8325d8|Will Ruining Tian (CHN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|15|false|R0|108483596313252950585997338627933686840246112149685728601645115544202163432774|false|9605657252626233085276172686864920827306462519258890940262550519949474864556|true
1347959|Carolina Hiller-Donnelly (CAN)|0x252daef35d280c052eaa4816301c2e24828b2dedb2972f34907dea1f5a213c71|Will Carolina Hiller-Donnelly (CAN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|false|R0|103713987399403510887165716948141523290195915355322761129780913656336085396549|false|21797853819588533146388626080907754952254146115524737174512127895981833028467|true
1347960|Beatrice Lamarche (CAN)|0x222c6a674f574b23975b7e5d7ac20c5bb9630b15faa46c032e71ca6824a549ba|Will Beatrice Lamarche (CAN) win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|6|false|R0|9308950558874653568417808775837977382512379211364090855641941572083682521316|false|37219052966665631380330949579060082470185008741546386515810913770100300649012|true
1347961|Placeholder 1|0xea205507d8185dcd7f588c7ad3163c6531111459dea2c95604b890034c192dca|Will Placeholder 1 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|61680656042266483160282676640795006386998850942153393593686251863913853882142|false|37274609157685698074372673156378825191684363434189281220083803262442739319172|true
1347962|Placeholder 2|0x089bae7684c782564cf1f7a7c16af4e5751e9d7301e9bc50b27c6ca8929b1e89|Will Placeholder 2 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|64048532526008245458993333408649670283445079347030846270200235689304227010467|false|64054556671354862452743148554909293356385004211701904981447960687770673717064|true
1347963|Placeholder 3|0x831c06073fbf7d90202bc0777959daa00e27916fce0d99e5a9a379b8b452059c|Will Placeholder 3 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|36548233049873696904025513254673248378978853185915926812782657929010984468513|false|30470474606579490619705058157990406898406303459117707228175084519785387263797|true
1347964|Placeholder 4|0xdd4a76aa9907e1dcad2ff120ca2a54689b687ec7fb084aaaf9c62fea5bc433fe|Will Placeholder 4 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|15411369643859339293945322530270992382558643534075802856114043096494933353784|false|38667837275395437969680323758443942475550189736538201837741782948604307234298|true
1347965|Placeholder 5|0x3f2e43f0ed8357dbdd1cfcc0368e7b192c8a9beaa48deff89749f30664707468|Will Placeholder 5 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|53454586381392869911831938804333856275965161588790633421900637522779363730848|false|61738616682796880971851853751746826340219764057959748306791813190462539679039|true
1347966|Placeholder 6|0xf0ebc2b4c2e343d3c663df637f377e75a3403c676947b8e5188d4bf0bbd4e837|Will Placeholder 6 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|80498140964099726429442490716993021425596554433251874416167540355287252552981|false|20204336620015946973776929471882852680424549292955016318821266009311697504048|true
1347967|Placeholder 7|0xe220b6d39b7d13196b41b90c90b6e406c7ce74bbdee461a23ad3901cd3632f8b|Will Placeholder 7 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|30733359246408372318492700541830082061118477363762469169279840970952975892437|false|14563047763400416026439043884715124898881842888688619319460231675358634845605|true
1347968|Placeholder 8|0x46244808357962d8405a468c12429f83f506e205a892b7f2803e47487696deeb|Will Placeholder 8 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|76146743306215709343664321424631829355661935345693011323359313249134093366735|false|42797414819210711731681714418132058314570199023703108501990521511720169760409|true
1347969|Placeholder 9|0xa2cc0809e1312ea4a53c8522b820d80ed604bc25934ec10878dc04494e7ede48|Will Placeholder 9 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|61547143992996816033480262158773177997454693436675370871832107387872942438790|false|109803531446080058411710871245951176376372424877927240633331832299406887943041|true
1347970|Placeholder 10|0xbf89d2f1d2a1ea82d6f14f31b6019ee43c37aed9bc08f106d0ab9d08071481c7|Will Placeholder 10 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|103961239728138252345531784141550263445057855265905840436492749755106147088451|false|58594305788073462048224173721736488102056871137298976399326768644782303713668|true
1347971|Placeholder 11|0xefe12888f0db6d9c918f6435b6f9646a26ded3daa5079040a17704ff17525ab6|Will Placeholder 11 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|53279252861712075914107878640126469286683484290828411575149550743744448321914|false|11457293463491477466990266691953443575473579700306720809611716819742415649160|true
1347972|Placeholder 12|0x700110bdc177ce22de47e488b7c1f8a44440dee20cb6fd204da4a9f343f5624b|Will Placeholder 12 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|109730412749446824577362531940457676463489721065131089124458678666239046449261|false|55555806217624073758963557633460284374794605407665705825140343460107732999264|true
1347973|Placeholder 13|0x13a1d1dbfcf2c8469667038e414257b0bb7a490ee4f0f8342ac55667f672c1fb|Will Placeholder 13 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|22332823261581306982523282585006371548363822998739473611833456171072406242250|false|76264636885697822790614449164161798385260850346190386329537378307919841070321|true
1347974|Placeholder 14|0x94de0f76b7f59196b12cc3f529abbaa7d07604150bad4ed34d8b80dc990733d7|Will Placeholder 14 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|38070753631629231722410334310837842715977135012354140165591642990329229174114|false|115052118549455877966081569561363312707576415257024809261062750753847514107618|true
1347975|Placeholder 15|0x2eb8d776fd61c6ee7a1826bf3a6c40e9bc759eace3c8edb13d8de19bbcc172bf|Will Placeholder 15 win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|67267342083906583266913023174084141932291470821416239167449449381841545515567|false|67157512511388936120847313259458566187653413151186460448289980349344588628374|true
1347976|Other|0x0b1c3d671d1a42f11642592391cdfd03e9e0688fdd7acbc5c7cd7ff7cf6375d6|Will someone else win the gold medal for Winter Olympics 2026: Speed Skating - Women's 500m at the 2026 Milano Cortina Winter Olympics?|https://polymarket.com/event/winter-games-2026-speed-skating-womens-500m|∅|true|R0|45780348319042106941702214903993047663556896969759796769835526695785486818919|false|93335880340836532353521519749109188255017348985778173675339065539220325565559|true
"""#

    fileprivate static let retainedResults = #"""
0|1|Femke Kok|Netherlands|36.49|36490||OR|1347941
1|2|Jutta Leerdam|Netherlands|37.15|37150|+0.66||1347948
2|3|Miho Takagi|Japan|37.27|37270|+0.78||∅
3|4|Serena Pergher|Italy|37.30|37300|+0.81||1347952
4|5|Erin Jackson|United States|37.32|37320|+0.83||1347949
5|6|Kaja Ziomek-Nogal|Poland|37.39|37390|+0.90||1347955
6|7|Béatrice Lamarche|Canada|37.53|37530|+1.04||1347960
7|8|Sophie Warmuth|Germany|37.75|37750|+1.26||1347944
8|9|Rio Yamada|Japan|37.78|37780|+1.29||1347954
9|10|Lee Na-hyun|South Korea|37.86|37860|+1.37||1347943
10|11|Andżelika Wójcik|Poland|37.914|37914|+1.42||1347945
11|11|Chen Ying-chu|Chinese Taipei|37.914|37914|+1.42||1347957
12|13|Yukino Yoshida|Japan|37.98|37980|+1.49||1347942
13|14|Kim Min-sun|South Korea|38.010|38010|+1.52||1347950
14|15|Anna Boersma|Netherlands|38.013|38013|+1.52||1347956
15|16|Tian Ruining|China|38.14|38140|+1.65||1347958
16|17|Martyna Baran|Poland|38.15|38150|+1.66||1347953
17|18|Kristina Silaeva|Kazakhstan|38.33|38330|+1.84||1347951
18|19|Brooklyn McDougall|Canada|38.36|38360|+1.87||∅
19|20|Julie Nistad Samsonsen|Norway|38.37|38370|+1.88||∅
20|21|Carolina Hiller|Canada|38.38|38380|+1.89||∅
21|22|Wang Jingziqian|China|38.57|38570|+2.08||∅
22|23|Fran Vanhoutte|Belgium|38.63|38630|+2.14||∅
23|24|Maybritt Vigl|Italy|38.66|38660|+2.17||∅
24|25|Ellia Smeding|Great Britain|38.93|38930|+2.44||∅
25|26|Nikola Zdráhalová|Czech Republic|39.00|39000|+2.51||∅
26|27|Anna Ostlender|Germany|39.02|39020|+2.53||∅
27|28|Sarah Warren|United States|39.19|39190|+2.70||∅
28|29|Arina Ilyachshenko|Kazakhstan|39.38|39380|+2.89||∅
"""#

    fileprivate static let retainedTrades = #"""
@1347941 Yes
1770423645 0.6799999728 7.35294 0x4d7e4656e88569b3e0de0867f268f2703487f17b69a28f07d16378ac73255414 =
1770426181 0.7147481584 139.909414 0xb69e84945161e4ef680ed5645349c30d94df538a70dff51c2010be19d302099c =
1770458431 0.7085484698 58.49 0x5d3bce510283efccb82c07325dd64bfe96e98600879a72964a171f236d1df023 =
1770464343 0.7555583756 63.04 0x36a1bf904af9da473c7e5e4ccdda89cdc45ee5350a988c62dcb5b0e928668fe6 =
1770539111 0.71 0.25 0x32094aef7cf98521aa6920b382e9de258f08640f425d9776862afe8d38874bc4 =
1770627641 0.9 1.11111 0xcb232a24cb2dea9846fc8256e734a90ea599b41cecd42c2ad7fd2be79b1f79cd =
1770658559 0.8613385827 38.1 0x4bdd48c6eafc573acc3eead13bb20ace2932a7a731dca8019e153a3f5ffca6da =
1770675191 0.859999914 1.162785 0xb17e4db71bfa8a43f2a7d8d404688b8accac3a9e480df620eaddad09d11cb506 =
1770688423 0.8099999854 12.345678 0x5a7135c36666915aa26b5de24f835caa40d17cc103bd678a86bf316346728a78 =
1770713555 0.73 0.47 0xc6b9f34a29973ad7be598395335b89f66f0429af8eeeb6bb8d69b758d5c8f414 =
1770788227 0.82 5 0xf0505caae44ce8de7891212dc842f89b3f69db4873b85de598ee3bc9531880a8 =
1770788231 0.82 153 0xc1fc179a59cb50af385e54bee5662e4456b0f5c5cccd8b28663f23aec64f525b =
1770788347 0.82 5 0xfa843c6a45ac5d21ecdcd5f1fe2623ea4f661b2399373ef1a458a5ecc9c7e5ae =
1770803445 0.8199999836 6.097555 0xf50604940371382d7c14559894cd3fa0ceeaa905b0f51d0ffa43e87618f82b9e =
1770806843 0.82 30.4878 0xd38adecc8d6498a08765fe60555e5f2612ab40fa067779f89e43e6ebf37f6fcb =
1770821609 0.8199999996 107.317072 0x2e29a75fc2b9bb6af4c785454f07a6e59eaef45e2946b4eef3fb3705ec95bee0 =
1770824277 0.82 5 0x3e60fdb12d8c3276c3a073acb681d905cbff993e8d1ba9bee7ec43bb356d1509 =
1770824401 0.82 5 0x72ea9ffcc99fa970626c2180bb826539d8b95ac72902151947aca0a92abc4eba =
1770825603 0.82 300 0x2c087328e45ed09a005f84c52d05597f864fa4448f1f0f38508bc771d1cb267e =
1770832915 0.81 10 0xbf0d03577c6261ea42e96a74b07ba01c2ba3e6eba0ebc5b989345df8a92aafa3 =
1770846253 0.8099999554 2.469131 0x0f04994f69dc8f9278cb64e6d9ccee24bc96a5b58dd2f3c08cf0ebadfa118718 =
1770898373 0.8299999792 2.409635 0x568eb099fb919448d97a76d13669f4024c44d92f2aba727f24593540eaf12726 =
1770914027 0.77 1.46 0x89a0e62bf2923b442ce734b92b2dd231c8b8c8d0577062def85b31c8a78c0ece =
1770914027 0.7699999987 37.532465 0xe9401c5e561df0e07f5f1a14704dae1a6dab7ca7ffc20799335971ee788670d5 =
1770916607 0.77 1.46 0x9cc622cd5bdc849c70c8a39b2eb4f886e5386662c13fd0b1615d54f3534a79da =
1770916607 0.7699999987 37.532465 0xbeedc3b90bb74b2879c80f1e66b8493e3339a8bca1c1539bb6872220756d4786 =
1770929877 0.8313821556 144.33795 0x8ea052c2e8c1e368fb3e4038b9afc30a68d9f5658ddeba6e2204936ab0713ab2 =
1770941197 0.8213544018 221.5 0x648c3e3d03cb6dad090add929ca412aa67fb4ae48950cbc9cf6c7df56360a5c5 =
1770946279 0.849999915 1.176466 0x810a077c8e254909d39be73de0764396347b743dc423386ba270109ab70f415b =
1770959909 0.85 45.5 0x5874b81f6e637b7068d23eb5bd9484e6fd8de47a7fe85a8fe283382fe43a3f6b =
1770991535 0.8299999975 24.096382 0x83b5ee960544446abab56772544408e33b9e7948849c4c84c7ba24493a433e9b =
1771064721 0.8299999966 47.614452 0x756374735ed4292174752a450281e4472a5602a0d1e9f0107015f3ba8c8a25cb =
1771065747 0.838633987 81.859307 0x3ff3508ca81c3f7c3a61f624f35857315a10eb4538994b9d2154c64aacf8c336 =
1771075529 0.8299999975 24.096382 0xf828befe5d2cbbdb9427d2d6c0caa0e0447ea570950677bac266394e3f6b66f6 =
1771088981 0.83 20 0x67e0028626a2931ad367873753bf7c3ed75e87752645259a0c0c30b162a5fd56 =
1771088985 0.83 2 0x4b1ef9e72356c46e3b65dcbf83a50a2a5c08322bf833a2a2bb87600dfbfb8e5f =
1771088985 0.83 9.43 0xd9ff4670d90cc4244d71980483241c95e4487eb37df0efb636d457febce3c3aa =
1771089711 0.83 24 0x2aac0181eff08a95f1a8fa9096e789c318d0ecd98c337122605e870d9ce9cfd7 =
1771106049 0.822173913 46 0xd4a0361c1caf38b0b9fdfdb8fa20a7478f9853952810cffc5e0b94d848e1c6a3 =
1771106053 0.85 10 0x62e4cb36ebc8a611718bb1e1d66ae7de34c3a5c3dedea655d45fccd26714d0e5 =
1771107721 0.7844736842 1.9 0x7e55bed69cfe44174887a71b6717af03f6ba488d989ff0c1954716782c1c9925 =
1771107825 0.78 4.08 0xfbe80b396f56325ca1d9d0be5c07e280442d78d51d8989a2249672e06b76b47f =
1771108969 0.78 15 0xba642e7d32991d590b7469310e697bfe4ea7936757e4bc65d22bd8c380346629 =
1771109093 0.79 22 0xce4f83d61d0e85d3b5a733de55b9694c110c1fd6f428dd34eb069e023e7e06ef =
1771109097 0.7699999822 2.246752 0x8a7ba7116d54a926896c1afdd2f1b4102afe80cead6f04137d7609bc635dd0a1 =
1771109105 0.77 374 0x232bd61099259781c2dfbe983fc1868713e18fed51dcde0a3576ca2d347c62ad =
1771109125 0.7799999991 128.192304 0x700b0fded4ba3abd72c57b870264303a2eb528c2d53806f46295c0c08ea8c25b =
1771113901 0.77 15 0xfd22ae319f235a4e57ec4434fb40dbd1250a3678dba1053f2b9daa1f6aa66006 =
1771113905 0.7699999464 1.493504 0x832b0379fcc34e45631c06dc085468912f3e43aa3a4f43035fe2b2bfee4ef346 =
1771114083 0.77 22 0x979a9970dbaf19a79ab3783e38764669980f966f00f25068d8dcd1cad9dc93ac =
1771114087 0.7699999636 2.194804 0xaea3495c44199f30fe8124232b8e4e0c27de9b6933c4e1b58b78d242a954f6f8 =
1771115387 0.75 24 0x397d7fec0e730f7000842335dd8f516cde5212e027e498bb85b56acab28be055 =
1771116457 0.76 22 0x07d89c8c9596abd54696ecc01661593bdc1deb7f1dc3d742022de9a12a6be687 =
1771116461 0.7599999272 2.197366 0x1bc47c6c7fe4262868620af39b4395a521ec13b7647be3f052b85a9439c7254d =
1771117395 0.76 22 0xbf35cbc1f29482c61270ee47676633c5c1909bf3f77cc381f4f8a9270ee2ba80 =
1771117399 0.7599999272 2.197366 0x512979acec543ab346d84b2b869437ec7d5554f679372e48326490ea5ea28ae8 =
1771118713 0.7599999088 1.315787 0xb055cc2d9397c443c2cfc1bc63c0b252e5b183c1916857cf45c2531ed2c488bc =
1771119799 0.7641437505 132.73 0x814019ba083dd84f3c77d572518267ea6b4e680b5788cfa8f1aab6c7f52c1a0a =
1771119901 0.78 77 0xbcf0e970edcc9e09118923404bbb441d1f9c69c5a9253c16392a08696735165c =
1771120137 0.77 37.4 0xa0a0775150eafdbeb178a4e974f407efcb5289faa7ff86000a9ff8c91c35daa4 =
1771130567 0.77 14 0xf2893ef9c6e5eb39fa92291e15359a51fcea069ffee5d2717e0b866e0acbde4e =
1771130571 0.74 32 0x17cea96bd349d92e4601a35a053c02a558e2b75ae536ae3e7d3b50785e868054 =
1771130571 0.75 1.426664 0x7edb89e4a8e493b7a74b954dc7a6ad2bb08b4d04cd447e7ea81c676642cd7b53 =
1771130631 0.75 32 0x32b54f5ac3938f92982f0fdddb7d70e4516e63cea751aad052df8600512b2e05 =
1771135851 0.7950708661 635 0x42732711bacd96c67ac113ce8e3f6a6407ff1f95e5d1fd2c5d4743567cbed55a =
1771136045 0.7952310345 290 0x8904bc8e51ae20177232a1d586a7613eb14ebc02d5a6bd1394b9a59f568af510 =
1771137993 0.78 1.28205 0x3c8a4eeada5df131c2ad95c514138ea8c7f5a8458e9b4520ca83c335cfd92157 =
1771144941 0.7699999877 3.246752 0xf8fb36f55f537168abd5984542665ea2c57b33aea17152b64bd6859ec3fc3ac5 =
1771148817 0.7746976875 1543.40205 0xe921a97495e2798f94c17c3d55b7fa3b3b72bf44334ed78abec7aa06b977e859 =
1771149815 0.7899999824 1.708857 0xa8ea28051e14cd80840e8603518cf748fa6d29d4c4ae9da42322cacb4fe14ebf =
1771152317 0.7899999921 1.265819 0x9b78f198bfa32b4360e3b5d6b37001fb36d93e85649ee54613f7ecb12bd5ca0e =
1771153219 0.79 51 0x9381fe0964dae2a6f12fcc541800bc3626eb198529a3147c1666ececcda42ed7 =
1771153587 0.7899999631 3.797466 0xb3ea5a2ef82aac2335faf84866f178d56936ca2acbab5f2080efda8def63007b =
1771154965 0.78 20 0x9ad1a542e615ba467d01fd3f426fafa5f71811fdf3fa424040c6dc005c7af29c =
1771155201 0.78 20 0x647577b461cd57c5e075d70238bf61b0af7608b20503f9ed094f36632d7431cf =
1771156195 0.7899999866 12.658223 0x25fbf29caf69bf50b7c3c7c03fa2d592052dc346c95bed53f0a5fd5d46c3f221 =
1771156869 0.7899999631 3.797466 0xaad80e921375b9226fa16251077ea8bef49f39e0da444b052dbc0e61e97e2bbd =
1771156977 0.7899999866 12.658223 0xdfdf10cccbdff6d41fe731fc2b28b6586fabc6da32c6ad31e3b72e1d6d62806e =
1771157435 0.7899999997 126.582276 0xa32184a3f2cd99035bfa323d1f5b01b6a27986028e2373e82c5a2a2fb99aab6e =
1771157837 0.8 12.5 0x4510f1ebc01551a10684b452d7806ce7c621a2dec006e1f2f7a87a7afeda2afe =
1771160817 0.8041697688 373.055552 0xda21590953a8eaa02e6665ed408a699a4853318496bd932b2429dee79484728b =
1771161779 0.8 45 0x1d5c3b00fb08b97edd0cab648d4a84be1d81fc8eed5fd3b104b70aaeceb1ed66 =
1771161937 0.8 30 0xb54896fa1dbb6062fcc6c01ede021a64fb82735f7c3afa3b3bbec514e6002e96 =
1771163015 0.8 28 0xf816a4493f43616f5857e1ecdf7a59d49a81eb69eef5f09a1357c8a7d705cba3 =
1771165337 0.8018212623 1.247157 0xfa5990c2d5f0c47c1e5772b97357b9fb2b91e99ab5d3f26788a07abc69e1fbc1 =
1771165573 0.79 31 0x0b3eb01cc40c34aa8df0cc2e39455952f1692c9048ce0621c596a6396cacacdf =
1771165573 0.79 8.86 0x8e7eb8fbb2bbd1b01e9582608377021a9d357c17a8871025cc7827d22037e299 =
1771165761 0.78 33.7 0x67ab5b80f96aa1b6738a1d71ccac926f729817f4c4830dd6235565b09eded2cb =
1771165777 0.79 80.14 0x01b5bf0a5f48ec33525fa249f88711bd9ebd34ef2f721b0774b669ab9abce5a7 =
1771166201 0.8129285012 123.012047 0x9dc92751a68e065a97eceffc9015fea6bcd444410f909c77601cbcf05c6cb0f6 =
1771166483 0.8 7.5 0x2bd107b6ff941f9500ee776983236bf89601ce2df96c7d04c8b1110e2ae9ddfe =
1771167003 0.8 261 0x6ffba283efd2927a771d78e96e3bbcd9dd8ea18096a582e1488aa3bd35a87487 =
1771167025 0.8134193315 672.469876 0x58d41a06a8fe41e09bfa11f3b428bd8544b797182515a04dc806584618d6ada6 =
1771167671 0.8 18 0x2175671b720793136eb4bf68250ed188e398f33e66cdca956e3b7fdac4943c8a =
1771167675 0.81 8.47 0xb3d37d5acbece0ce09889cb019ce22294588e99bcc5cd1daf2bfc41b20455244 =
1771167681 0.8 1.8 0x6277c3022c6279dca48dffb6c1323d77709677d5ca1b247ab3dde852f9c2be07 =
1771169029 0.7799999984 12.820509 0xc8637eaa54700c72bf80a7611eca28efd76205de6f0606e0ea6ff0ae2e0c0d9b =
1771169105 0.77 44 0xaf40e8313640efb905ac710afb4e097acaf8a192c59766917b402745343ca960 =
1771169369 0.7799999995 128.205127 0x1f972a52503a34749e79b17cf58ec6d40730c2a8573c9002fb438b26c23cc375 =
1771169477 0.7799999995 128.205127 0xacaaa0b20ea7316607675d69ee6246d468379aecb0df143ef932d0d3ca62c0cf =
1771169561 0.78 51.28205 0x7c18fb86d9726ae80f91ce861fc06d2c42d7a821b28a3ae7d6b54ad196c0a2b1 =
1771170091 0.82 5 0x174d5798aab2a066d5782f8424e0a934ded6f52c09b8534634180084e2e48d4e =
1771170193 0.8099999554 2.469131 0x7cc0b1c609a812f0fe22b7d4159aaf2a306e4c2839c00e396d3d4656798ecff9 =
1771170207 0.8099999757 1.234563 0x58dc6ef5632254f83ae56317f27ea8979754fe11ade1ea04802c540f9bb9e46b =
1771170541 0.8 12.5 0x7321829e3b1fa2673268c485fa6b4ac951baca0d9f36e91df27a334e6804f906 =
1771170713 0.8 23.7 0x92b0f8d3caab6829f35280d6d86a0e194316dba7e82ee879f94fd54f816ec019 =
1771171095 0.8143246995 92.10085 0x388bb4db178b84788ba97a7fed699240f2cb80ae009e19c6586c1b590f820456 =
1771171249 0.8199999996 46.341461 0xf7bb4057fe3364baa8f9d80eaa244344704a6144002815d6405a283d029e80df =
1771171341 0.8299999967 12.048188 0xfe3b53985ffc28143f6afe8b200d0aff5a6cd0e280c2e85e632a5375af06691a =
1771171573 0.78 3.52 0x4e1f2816afdb4aad8638022dc701c15c17029668e1faae31518265c558274c40 =
1771172157 0.8099999757 1.234563 0x8967f023785e583b560e3048d3cb257746d7403fffc3fb3d8524105d2ba427ae =
1771172195 0.809999937 2.382715 0xf308a6233aee0bd20bbbcf4b49e8ab43f0dca8a75ace047a6c44c54af6695cef =
1771172295 0.81 165 0x8559797f16c40c96839adaf845b5d900536bb394477f242f3fc3fdc8407f1c36 =
1771172339 0.78 12.04 0x4709a31a7698371d20872ee42b10e01374bfb55add208fd392ee1b6aae5a0f91 =
1771172377 0.8299999967 12.048188 0x7a63cbcc2f806d9bbda09b22613145d65b43ea55587406cc3525797366946463 =
1771172477 0.8381509434 53 0x37a492bf47773a6edc9e9bf281a1194d93dd0d58f31c638fb338e6ebe9d0bb3f =
1771172853 0.8 25 0xc76a42fb250f41878d5e8b66576dba92ddff7f8aeeaff59683f94c90faa86f97 =
1771173083 0.8 6 0x6edf134e2a439acd38468d948187b2c8b2d9404cf117612da3a878ac9b5259e4 =
1771173157 0.8070769231 130 0xcbf515e09a4f6a968ceb151f5d4404d8be6637bd15fef700c858bd97ddf139c8 =
1771173229 0.8167330671 24.4878 0xaf7ebcfcf59bed43184b60c3a08374f59818e7eca9d276f616af5c5e616db615 =
1771173385 0.8467120274 29.525976 0xabfe99879f274ccd921960c5a3c04daaad0fecba5d7d191f287aeb05d7851e2f =
1771173453 0.8399999395 5.952379 0x25b5d81920b7c4b0ecd4f4db89bc3a664ec099cfd82921b5fdda3a07c8d36435 =
1771173769 0.83 7 0xcd4b166406404c8d6a625ac18d228df9861cf399ec3f63f8450dc79ecffa9253 =
1771173815 0.8361045047 11.960225 0x1bc206dacd4c25561110440203fd9ef5a824e22bf3e0b2fc5979d69c3f75127a =
1771173829 0.8499999787 23.52941 0x0c64d9263000f333a45d9baeee8c7b9b2244ed36f7bb05b3d3618d247de506e4 =
1771173835 0.8954545455 44 0x5a0a71e397cea7829487c51d6ec0c7bc5aae9ef5e865e2d25182b43676bbefd7 =
1771173841 0.9 11.11111 0xb83d980c6b9474285c2e8254c6a1f846c7d5cc4005bca0e99661662d9e747cb5 =
1771173845 0.9597223004 603.89 0x75b346e14ce3c273d7ac68fcef3ee283e76e3caabd781ff131d04e08c8487dce =
1771173871 0.99 5 0x2c42022353e62ed5155c927ea0a9482c5b35d971def4e3d6581ad65029be38bd =
1771173913 0.99 29.52 0xf1ec9839c4c6607aaaf93bfec402a2b52c12b0adbc8d58097c3eba98eeb7bd04 =
1771173925 0.99 12.05 0x1a228fb4a4e27900f9dfc8be2e176c626ff54dff46750217012bbdf8505bfcec =
1771174009 0.991 3.79 0x45934add25e25e51ef26eeeb198d8943e85730725bd340617e914196dcbf9e55 =
1771174019 0.991 4.01 0x7ab84498ad556100c5bfdf07d8b58e72322a7576309f10b534facb2372139637 =
1771174053 0.998 126.58 0x8e1e78187dd3957d82c3e0fd27827d0509ea98271cec9c46ba358505e1d63bdd =
1771174097 0.998 1.28 0x540a48078e77a5d71ff2beb32c51b0e95f0d6c37dbdb789ed614ec076473bfcd =
1771174111 0.998 128.2 0x6ce1bc898cdd138d31d471d1859e3ed0ce1036292c7a353b33198c40c05fe02e =
1771174269 0.998 30.48 0x20d35305d8865bf929754783447956d565d0e90326616dc6b9481497ea3abc56 =
1771174447 0.999 10 0x4735db6c4231c74b71388ddc7cc5f421b863cea0db038ed21c529a512f99a62c =
1771174449 0.999 20 0x9535f37962e7700f0491620fbc8001d992712e250b3202685288e36b86d23752 =
1771174475 0.998 713.46 0x299a15c49cc9562ad5b3ac0606fef96281a5c65a12114fe7cb8d8794eb6e8a51 =
1771174483 0.99 1041.48 0x2bc1a4f1714441e83f881207ee02549685c3f6ec6f3f244fc38cef1bca22c96f =
1771174527 0.99 713.46 0xd54973ad1d8c229bfe0941ed38487af8fe824cf600bc480440ec7b887e0f88a5 =
1771174787 0.9953638846 51.28 0xbaf5e4633d4be7ff0a40e7d5c91f773568c3c6f5462d7c511f268f94ec71618e =
1771174879 0.999 2002.002 0x20108ef65bb6329a211829887cd65cd60ae485063f150702e86fbc42839f5b5d =
1771174939 0.999 100 0x3ded5d1fada2e61dce612adf384fab5de4e74b957387e09e929e705dd815a7cd =
1771175223 0.9957394068 160.48 0xe452019156deafca6781d76002f84b868dcd1a6d2e6996c1d9dbed3c893d3344 =
1771176287 0.998 17.9 0x8b14a59dd6e5429591b18d49bec75f44477842fe4d208671fbdae683c4f9f61c =
1771176537 0.998 46.34 0x6ee9864319c3ef5433931014a626c50cd28e5aa0cba43fa24f41291ea4f21034 =
1771176693 0.998 4.49 0x75e51e56abdd8a1b4e205985667b3f451bcdb0457eff94a3982bea1d039e187a =
1771177987 0.999 797 0x4ddb2b2dc75c8f8f96edfca47bb5ac46fb5339666ed78ecf740e36eabcb3f830 =
1771177987 0.999 797 0x627c65701eac7286938596a215de22d7bc575b55b6d4eeac53b9bcbf21ea8c72 =
1771177987 0.999 266.81 0x8d66df0926e6cbfc4a4c0e524f37f34741428f29ff3176bc090ff09c0c14c363 =
1771178309 0.999 92.1 0x016834a9270e71381f39a9fc244d6b877c95aa1c46c3efe15396e608ce7b07f9 =
1771179087 0.999 431 0x4e9abd8e450aa9ecccdb82575303e73a022b00354d233f54188d985942c034ec =
1771179805 0.999 5 0xf5ee37270b190122fd990f16fc74a0283724546dcb909ded3fbc2176ea4f6f13 =
@1347941 No
1770462375 0.29 7.04 0x08d33b1d73f0b0a664aee7650364ef90a3b892ebd2f3cfc7396672ed0c9d8562 =
1770462393 0.3 5.23 0xaff685cc9a8623b3fdcf64fc8217facb30473a66ddba81bac7ca7eb85f46db09 =
1770466975 0.32 8.09375 0x2481d05e4d0485c28a0e5d9eae8240d9ccc3fb74b241c0f45c46adeb65c6b958 =
1770473065 0.31 57 0xca0f0063c548b9c516bde3270c412343c699da0ff3ebab2f51e34ec675d475e2 =
1770475253 0.33 13.88 0x59b56a08c88f12d6df4a1bce94eb3b8fcbc2c166d027fb03d7d0478f587f895c =
1770489125 0.2802945065 103.034481 0xb234d5304ea365c27bc571220e479784bdef91e5d0624a839ed92d5472b33de1 =
1770553495 0.29 34 0x03e01bf20b10a04f0f70e0ca02dec6cb43f51c465045ce8bbce989876a5ee01b =
1770571925 0.29 5 0x520eb4c02ca37bf5e46b6eade8568e3c2f77185876db3c58263bc44373347d67 =
1770638383 0.2909795424 6.873332 0xcc1e03dc2917b470aec56be7dfbe5d2c8fd9515329f56d6e10e37a45d77d2377 =
1770669221 0.289999964 17.241378 0xfe38d236d8ab564e730ecc6d14e957505571c9a5a399142cee9a513444bac60a =
1770706297 0.2 10 0xc14351d809b32511b6044f5bd83c83697a4d974c664ef3f136b6567f00f2440b =
1770706301 0.22976 20 0xcc7ddf9aed47dfbcc668a9d31082335020a2147cb1b3cf40919b605f2de9fe29 =
1770713319 0.27 17 0x678672dd07fa6ce44814ad8d9c0c298d99f2aacda2a4ed9d2eb8971a559a7291 =
1770713725 0.27 23 0x13fd839cdcd7e330eedd20c1055d59ffa7394cdedbe950d9b0da3e19de054f6b =
1770713725 0.27 30 0x77286ddc95be7583ae7b1814e90a56c6b25a387a1ca6caa9b39b6fc804f31527 =
1770713725 0.27 10 0xad2d39dadbd8c43ed5424ef7eee557de8436bd080eeef08bbb3aa881a9271ebe =
1770738887 0.2399999674 20.833332 0xa1104fad9bde3dfe15073a2ad4531ecc1eacdb750748a7c9369914c18bf4b3a0 =
1770757167 0.23 6.46 0x7ac8fa0173880456450ecb4cf7e5e3f9b55230a92cb723f6c3b9029a65bea240 =
1770827589 0.22 10 0x12eadcb96c6a7446215b5b6b676cbeb5ce4b3a81e27e2f4eaf33ecd3853a8a10 =
1770871293 0.2399998986 5.916665 0x990a08f7ebbe363dcfb7ce9334df12655c144185b5b7c70c1b7801dfa2f3103f =
1770871753 0.2478166667 30 0x22b0ef4fa847930a9da69bd8133e54c1429a9b54c158d2c10ac5276fa3b91532 =
1770905533 0.2616587007 56.49 0x8bc7d64024a7863360b9b16145b54f15c5e42f56235f65eb6de7d8b6dfc44158 =
1770927899 0.2799999916 71.42857 0xa81b50c409c221bfe2a19ee20898d87c929cf66c5a1f19c9dbb4f081f798a125 =
1770929069 0.2699998542 3.703702 0x8b72457de6c8839dfe32db058940254f08ff7c2cb381bf3177172671d24e8959 =
1770935453 0.2 5 0x8fa3a615b46e3872ed790b4419634a1fbc7bc179c114e0270e96b3e16b5bff3d =
1770946273 0.2 5 0x66100ed22f422bf65e21d8555f8c330355eba66ab3d5978586d0429db0f6a51a =
1770950449 0.2 5 0x34dbf9a4852ee93d0f083d4e590609f005487dfdd836a041bcab29cc10c16c59 =
1770951709 0.21 35 0x78a79cfa0f9880ab787b834e0ad8d380995bbb76d2496d0818dcba6367df4193 =
1770994443 0.2099998915 7.095237 0xa4006181587f017fc4aa3da3ebd52b971b94951ddad7d119716e5c01e73298d9 =
1771009699 0.21 50.02 0xfc32c1fb8ba20992396055515e7c8e0b17743eac89f98423d1b1596e3ba73d97 =
1771062147 0.22 5.91 0x181e76db168f16f7c304c6914fca162cc39c83864aed3a22d148bae09de0410c =
1771076085 0.20571 20 0x7f4d1aff481eb72d8a7b120004d6e30868048c8beea002a321d74abecc6c0c34 =
1771085531 0.21 20 0xd287b6acbc3aba499deef2dac222754b2609827b9e7a734cbee221ec39bc56e6 =
1771086149 0.21 5.78 0x8fca2842e016c6fad1291a78460fbfbd18f8812fdedc8aed7ecc82449fbad069 =
1771097607 0.1899998784 5.263156 0xb61cfe569575b21a1d9263615da2b1c50b48af920626ddd481aa12ad71fc1819 =
1771103733 0.2 20 0x4675f6efc183e9902bd6781b6110f1a5dbb75a50c32a00a7730fe542d643e4da =
1771107445 0.1996994922 100.150475 0xc2d9631af4f9342ff2ff7f798176d7cc714b20e8c6f5b209eabe65260800690e =
1771107551 0.21 30 0x52ec5a12adcd99380def81bafac2c7b62e533591893ee135e63b4439d50568f3 =
1771107551 0.21 15 0xdaeb6b6a8e166741850c2044db2c16153f7328f629531e68026decad8f4e63fc =
1771107551 0.21 10 0xff269023fc5c2951f1f714fda038ae3997b423e7960956ee1c0290230e740570 =
1771108623 0.22 56.53 0xc10a6fdaef014feb29aeeb7cbcf5ddad5872eec8f7ccb3e884a3a00f48ac5365 =
1771108685 0.22 29 0x888dffe4f5026a0d2fae65a20c610161cd6009eca66c2191b1dc7ba1ef11cd3a =
1771108685 0.22 5 0xe2d42d8f36ddb3a74c91600f7dc79bae0991e17b37267bd730025109e3dc9326 =
1771108861 0.23 5 0xf76f5eb22bbf5b7d47a91de647197fc88a80afeca1b0f3c6b13df4a3d7e6481e =
1771108881 0.22 5 0x3e1e6f70105c9d3d29dbab2702a835145633adbc8247086283e2c8f3f4c03589 =
1771108881 0.22 5 0x8e35bf4f5dba4289cc8703168d2c2ed8ed28afea3b59512e4ea9a81dbaaf56e0 =
1771108903 0.22 5 0x4960d8fbdebfa993342a6a3d9921ca7b3b3112faed6762b891e10ec60fe941c9 =
1771108905 0.22 38.09 0x83737c2d15a461610dda6a7e03cde3b64256fa1e8eead5baa64637da724c7383 =
1771108921 0.22 10 0x3a0aaefdda6b9db592a7b31165ece2b5f59e3280e7b02c831fd606cb82864f3f =
1771108921 0.22 89.22 0x56f79c2b8c5b2fa1f14a1fbd193978048c2e3c7aeeb21cbe053d076d9f1f2171 =
1771108967 0.23 35 0x1bd56e47ed9afc674f6452aecf0f062a65ad100038ce7f45ff24cadfbd0c0ca3 =
1771110711 0.25 12.59 0xdca6d98014bf73f555125e76e3297116f455a9bc4138d23749ff6d9ca5339a2d =
1771113111 0.25 39 0x0d07220dacbf81b4a9a2b7c4f2c7319c3dcdb0476301ae3b4af7186777057ee9 =
1771113883 0.259795 20 0x555a998f1b6d529d5c828e5eaa9f61dddcc73de6b76f4b28c7f140c8390ba913 =
1771113895 0.26 16.21 0xb7274a40cfa8b42f6c991c75ee7755ef469712b57d456769272f8214425cb8f2 =
1771114083 0.25 5 0x8bb0a5f9d40a56dc3fd1a2ae20a70f0e51c58a478ba112e8b7e40319e77cb9d3 =
1771114089 0.25 5 0xe5138b56828ab32dc7ba96282090ee3c54dd684bb9d648a144e3465fb5cbf465 =
1771115383 0.25 11.49 0x3c148bc8988563ed1f708e3f515ef4b073ba198e4a14ac2f9f4cf3eae0e970cb =
1771119901 0.22 50 0x326427fa433fdee3eb699cb40e68bf29ea6040b22e86eed68dea8ae41cd6d3d9 =
1771119903 0.22 100 0xacc9c7c1f1f16f41ded5936006c7ef417593c55359e8ba7be93871a959da1caa =
1771119903 0.22 5 0xc054dad2ab9bc0ee8653e5a57ae0d26077a876a1514a7a3c1718e86ab2ac65cf =
1771119925 0.26 5 0x857eb9b4b6fd11b9970c5abce906df6e2301e622996c63973daf6bc5aaaa2499 =
1771120137 0.23 5 0x526aa8ac6d6644eb7cc4ca29d954cbb4a93147e48a7044a2839eb8daeef8e614 =
1771120137 0.23 5 0x6833af53387175a5fd24b6c2f55139b3e47a53050b84262cd26b8ae83446b3af =
1771120151 0.23 5 0x2d471c673eb598df3fa57677fac15f4ea150abb8dc9bcde080ea0895933fd9e4 =
1771130469 0.26 10.94 0xf7e64ae04a15f7c9319a9a77e5623e00e7a03767a5e402b81b160d6b30a81bce =
1771130527 0.26 21.22 0xb9cdbb3e683bba22d5dc650760dc93340b086f961670914843d45e08b7c5acdf =
1771130545 0.26 16 0xfa0b3c481401de7d94dac734138156f021c78546e72350ad4251568f7cc596f5 =
1771130547 0.26 5.97 0x89e5a3c50ba1305f9e175f7f68985a875ceca3d3f8540ec6fef3dede44f5c5ae =
1771130547 0.26 17 0xb5f961c9985c8cd39e4a9c2181a150dc8615427bc6f57e8c17f927666d086e0d =
1771130555 0.26 16 0xe97e03d781caa2b572a7093535bf94f596af5c2ca4f737882e5f711c9316e969 =
1771130563 0.2625463744 17.79 0xf27ae4dcf5dcbd775a83ea74654ae713cbbc410665e5166e0d7780e3732edb29 =
1771130579 0.3 8.19 0x142ad1b6e4cfd3e290473fc33dee133cb74f3584b27731ad0f3da623bb41af9e =
1771130633 0.24 5.81 0x4d36a21a98dbc7afa914da14b1dea4811be79c2735767528830a26d7347fe9e5 =
1771135865 0.25 5.43 0x5b784d5510f6f524e5331388a034b36f5b1ecf63706891a318f9bde4d9d78ef2 =
1771135867 0.25 0.38 0xb494048d7485a9e3cd7a8e9e43eac994ae2d2e2e625a460ae6367576605027ad =
1771135879 0.2 0.1 0x7c7d46de45c68769656ffe79413a01a5db46445e4550c317ccb57663e043e551 =
1771135883 0.21 0.1 0x9320274b90765e546d6c3c56cccdec222045cbee60b0cee0b84e4e3b6ca6034a =
1771136201 0.22 5 0xcf2022f716385c9908c7edf61ef8ee2f04aa606672cf9b9fb9a09d039c0685f1 =
1771136203 0.22 5 0xf5ec6252a832a4ec04157748ea1dd564514110bb73d4e99c2f009fbbc8d6e6c8 =
1771136741 0.24 5 0x0ea78a0ad1adbe7db15da2c19494f9b020158fc419c4e812147243a55fae0c53 =
1771136907 0.23 30 0x7eb0ebf160ecf76719b2b5849c68310ea025375bad92d618cd9c045f63fa1d85 =
1771137995 0.25 4.9 0x4976b4ff45efca5254418da0098ee12cb6e7800d6b938b2dacdaa58501a45352 =
1771137995 0.25 35 0xb778c48730f2470d14c0e83693de26b7c9024549b0c8a07f49ceb5000623610c =
1771138003 0.26 6.36 0x94087bda6ff0b11667cb0808cb33da69bc3007139ac0f24bc84428cfe2bb82c0 =
1771138011 0.22 0.1 0x00efa448c9b0f3127ad26feb5d459b52c9e5b149892c29426f8fe94bf94513e9 =
1771138387 0.27 10 0x5754e60080d0001bba011e7d8225bf610d2f2362f41697a60e71d25f669f40bd =
1771138387 0.22 10 0x781a6e42bf32d64eb13b6f62a1f5575065e1f9ed9f9178c4431b8940fa807810 =
1771138465 0.25 22.64 0xe7111f227779459bb668e888fbde6b3e7bd066065b5883ca02b7bf090219e091 =
1771141607 0.25 50 0xcc74c176061b353b8e41a89e4f1b670c493bc590642e719a283bb65c64cd0fd5 =
1771154053 0.21 6 0xb8339d5f740448767b4a3906546390a29cc62a1a9d05f715cfde80aa544453c1 =
1771155109 0.22 10 0x6f53c75057b9b496149dc48d2c48982383fd359e78db9445fbb07706b47d4bec =
1771155109 0.22 0.1 0x71d975296d4759ef5d9e478f5a276f2a932aee253271bd31a89b595689c6adc8 =
1771155109 0.22 10 0xbe80853bbac0e821f9aa4b1fb8f013e2567b8316891053652b25d60101759020 =
1771162141 0.19 2.5 0x8da3e6c530ef603fdc6a3fe2db9c248e1022f183c4f92e0a85a8b2d952d40f34 =
1771165497 0.22 40 0x9fb93d6dd2991aff2fd2b8ffc21f4e4beb61008521ab5e58ec9a26c8a78570cb =
1771165507 0.22 18 0x970a36e9f9e8879c8d353968e45789027b4a13e7e0419597abc8cb5e13d8476c =
1771165779 0.22 26 0x445ded986d889b2afb59b2dbad0ce234c3b8a9c6e73492a3d4ba73987e675e8b =
1771165781 0.22 14 0x731f6e1b6375e975cf5d05bd919b8ba7226c981a4aa66c14bdfc709209d0b1b8 =
1771166865 0.23 7.18 0xe7776079894487eeaae9ab2816bcdcce5ddb5bafbfcc21d426cd66d9f6df421a =
1771167017 0.2 5 0x6a20bb076ab682b437baabfa2351097801ea3f36e11950d70bd668410a90ec1c =
1771167677 0.2146 20 0xb36543d1ed2a139f58c1ab83e444fab09aca3996f18ea114ff3408a6867b2441 =
1771167677 0.2270971638 480.22 0xf2312ffa437bf0f96aa5f5ad660f8b1db17e9013a49e5f307429e5348ae90713 =
1771168577 0.2160714226 101.81818 0xbfa0f3f12e6df8dc37f15e5bda463265b4416bdc352172c6a546f0ef26e5e8ef =
1771168991 0.22 344.66 0x77f0698ee2f65b602ed2d821c8ab28a8bce84ea6869ed8ff03cf543c2ff934ff =
1771169113 0.23 56 0x15c25066e08d783bece4f18e8a52c84010da15ff6e57bbec2629c036aa9dcc0b =
1771169115 0.23 23 0x6af203d9426d166adf7e163ef217f0ecdad46425f446e598ca15e0f1f18c9a50 =
1771169175 0.22 16 0xb714cd87f94bd2348a8ba936464c533169a4034ed69ed881312d8ed6efdf05c6 =
1771169541 0.23 50.87 0x4c98d68316098300fbe8d167f5f0d24a2c95545b173e9b7c883660da6579af93 =
1771170011 0.23 54.49 0x80bec7934b13f72394de8a758ffbc2b8e2767d0ef25151c62efd2b563a846829 =
1771170343 0.2260384606 17.165216 0x5a7d8c40e50a6fbafcafb4011a6d8ad9943a802c18d091b8791d973c3356ea40 =
1771170353 0.23 219 0x387ffd1e9bda1aa5c90b3d50ad4cc7d00641c25edad5253278fef539fac129c4 =
1771170353 0.23 30 0x43437d82c20f11f5d0195f5361b5ed104bda71ea79995311a406bf7109a5f862 =
1771170719 0.2 75 0x9011e66d9b54dff006df9d8014636b70f773953d19240ac227f935d8fdbf658d =
1771170721 0.2 5 0xe4613730caaf6d37dbb9d1cf00ffd8ff5dee25c9cd057de506c261f7767474dc =
1771170755 0.2 14 0xcecf818eb2b5f8b9e391ec669af692b7e21180c85ecab811dc1206fbd1de2688 =
1771170813 0.2 32 0x945e5d005c03e6f81e9efe9d4c0d18854e27f02ff159ba2955d772f544d53318 =
1771170835 0.2 5 0xafce0a31dea8d614c0716023623dd5892d977759d4092d4512f3c84b31394c7f =
1771170931 0.2 10 0xbd04029376e545d71983400ad1b97b58e53320bbc3feac8ebdab5b69ee51a5e7 =
1771170985 0.2 5 0x8b8bef3ee31dede144adedbf6bec03f5c2e9e6c4d9b73b1786b1bfd12add01eb =
1771170993 0.2 10 0xd0090da520af40a27b7cc7889a0bebc66669a1b99afc648c7001c7517fe386f5 =
1771171053 0.2 5 0xa4ed9a3862d83c25245a5ae2aee9d12d3185c5a814dd6e4ff53d736ec68042cf =
1771171085 0.2 5.4 0x42d416a62ade8a25ca6a55f925d6b47ef223d5ebcfc10172d49261fcb83749d8 =
1771171129 0.2 7.6 0x6fe71ba47bb9ad0dc2cf28c01282e40047c5658949bd7fba0b849ff1ec95d68c =
1771171235 0.2 2.29 0x21a0ec4aa495397ef7ffd2e6791627f3bc0e6291556d19df7dc3dc0b7414d76e =
1771171339 0.21996 5 0x51a27f33431418726807448bd6d410aa1acc8ef262b2f8027588a6aaf526ed72 =
1771171339 0.2276880795 151 0x5c2fecd8290c23e3bcf10535652d1c25dbbd605c7fa9b8722bb9caed6cdd8ba2 =
1771171341 0.23 30 0x71e55f326d1cd51cedb008af57dded855ac046d35e1244be0071e23f96c583fd =
1771171357 0.21 13 0x388087815e09d263ade945971eef13652b208fc74c0ef5b97db8e07350bdd503 =
1771171369 0.21 7 0xf07943cc6d5ded6819feac0d8bdf062b10898c0b2f32272df4f9709d53b1a5fb =
1771171411 0.216 50 0xdde4a15ff51c37a9237ce56afa49dd9834992b41973cd66bb81769cb27dcba53 =
1771171539 0.22 37 0x980d9f1c238c112cd19d0a7be4a0e7bc93edc4bc3f6bd2eeca4385a9142b7ec3 =
1771171563 0.22 21 0x5a20884d2f95db4139513b41c14dd23463f14dee37a66ac9315d022fa97a81a8 =
1771171633 0.22 5 0x68a2e566625ae34c234f41e680c022cf5e338bfeabf5e9ef33ecd8ce879271cc =
1771171647 0.22 70 0x7ae8b50632b8d039897fc571f28a875f66020952874f69607e15386e31871cd2 =
1771171647 0.2296842105 19 0xcf62ada214cbed6379c1685ec90bc60c8eb4fb6b504e7a8ce9b27947babf0cbf =
1771171663 0.22 7 0x405aa40d33472cab4ad7add5be6aeba7d512e42edd6ff4670478337545fdd9e8 =
1771171695 0.23 15 0x55e760de3749c0bc4859d4adc1764d9b75eeb12f06a6e9a9bb87fc6fcc9f3562 =
1771171697 0.23 7 0xb5e12bce7ca41da31a3039088f802db5ef1ffe2201eac4f8584511dc74792294 =
1771171733 0.22 12 0x0840948074d5955b4da5a2a6fe98e80bf247ddaf9af50e15d48e65ef889f6cea =
1771171737 0.22 10 0x614d78de493ca7a1788aafe800c746f3eb0a0028c6a684d73576c4c26482fe74 =
1771171747 0.23 30 0x331d0232d85db98cebf4e42f9f0b4f4be323d19bececc7523777c6a55ffac37e =
1771171749 0.22 20 0x8ccaeb31553785f8382ee7382e729b0b0301030541a856914922f5327201b0ee =
1771171763 0.23 3 0xc32ec14249e3e59e35a4b2871dc2f9ebf56056fdfd348f3cb655365a378226a2 =
1771171793 0.229999916 8.695651 0x1bd459b828737d5f5fa812c484130639150880c9c1b6b1b99eb8266b2faf07df =
1771171859 0.23 25 0x50681f36b9ea68b7ca2256587ddee9c35ee6a4467e35fb0f4e499d0fd7d6dbd9 =
1771171879 0.22 25 0x87aff210a49633503e16dd3eeddd6a3eb1063f7ea2462f342a674fdcd40d0b25 =
1771171905 0.23 17 0x15199cb6555f238c0a157df95d571e08013673289832bd217708412831d72617 =
1771171927 0.2 15 0x2c08c57b632eb3f90e08985a9557638a5ac55495788c01b6109cc4e46642a428 =
1771171927 0.2 15 0x8cd347e53cbfb9612ea7775bf876e640649c341ab83f05a600085569bee2d4e8 =
1771171955 0.2 20 0x5cc4b8049958e771f73192867e1dd8fb2bb840594a158e090ee7e58879c6a863 =
1771171979 0.2 15 0x332e25468f760e9a608ddd0382d0189d6c69cc94fcc3f70330505e80c845939c =
1771171979 0.2292574257 202 0x76c6d2ed19138bbd32984c6b7e0ebf792f65e5103a63d8a672cc72fca5d6b046 =
1771171979 0.2 30 0x7eb4a8e7e75da2819e78c9eed8edf9682c60f064400561a1e3096695991bb4ca =
1771172049 0.22 12 0x878eb718403cc52edeab6501c86f24e7403cf808980f9d010254a8a2d65e7d92 =
1771172113 0.22 13 0x10318ecb44468ff05e051330e18e9bcc4032dc5c9dace67aac9aa44589248c54 =
1771172221 0.21 5.84 0xb521543e0b63f14873873470e90e4d6540559154309d3b6b4ac3cf707f0cc82d =
1771172225 0.21 10 0xaae6f9c5bccc68a7715a15faac8a538d6c0c01cc123211498e9e5802788e971b =
1771172239 0.21 6.14 0x95610a4577a3d62af484f1c5658f48ece2c826250286769803613a1837cc2c60 =
1771172247 0.21 11 0x0aba957e0cc1744c1f4ad2d1c4f94903c1624e08a39c2557dc9bfc28c5313204 =
1771172249 0.21 18 0xd649d6047fa31d15cc394625b2b457a712125f3f227ebfba72924ee03d311c00 =
1771172253 0.21 5 0x6e09693f03d71c3f6fe0e124d96955c6bf41550f6f5e2241021d0219d8b1e9ff =
1771172253 0.21 4 0xbbe3b5f3b334e29d8280b87b7e9020c23ab0c8aa703ed7e453640ecdda05ddf1 =
1771172253 0.21 7 0xff6ac110f00299a1ba7927ba28ba1db77d625d149c1a3c2fca15dda9e46a31b8 =
1771172259 0.21 7.2 0xcc03adf00801bde82606442ab7e2ae5f05aa0625851ddb6d75b742f969ac40b2 =
1771172261 0.21 30 0x67c81a869f1bda79dc0d04d40322a9333dacedc5eeabf3e2a5c3f8f22030bdc0 =
1771172291 0.2116702703 37 0xf8c8374957f9e590bdc4272c199194a83fd789a1f01791c4fa38ec729dfb2130 =
1771172475 0.21 17 0xb26b435a7464ee345d6a0803727140ce910b3ad8712e9a69391a252c5fe61ce7 =
1771172557 0.2 51 0x81481c767debd875699ef93b4570b8134be5147dec9199b2c27ae1564d0242b1 =
1771172637 0.2 5.99 0xa1b65872ea66f645ebfa0f0518b1bcb1f215953d5cd7f8299bc8f4455897c77d =
1771172641 0.2 10 0x6e0c5374da91628a9c704a7f6019434d783159460686fbb2be10b7f27db2c610 =
1771172675 0.2021154619 49.476665 0xcfca1e1f74b5dfbe8f3e50bc3cb0262a619043aa9b91791528774ef01e2f20eb =
1771172843 0.2099998677 4.761903 0xd0c0462f4b0d7cf771fd79e10dd79870c9b9b013554d59f553cf2526eaca860a =
1771172943 0.21 28 0x4c95cb6d466ce18a701b13c72565cafe2cd87cbbc0e0d4b8a29b4f561b43de3a =
1771172995 0.2 15.7 0x8a8bd4f29b7e309144a8350a9f46060d0cfe83667c130db14e45b78d58845a37 =
1771173191 0.21 5 0x2d67e23285b33e3eb74db68039c52c1a014bd501c40b3b9eb2cd72e290fb3a32 =
1771173251 0.21 25 0xda7c1ac6f1bf818301b9c8ddb7ac3e5265c01837c65c130019c63125e330a8fd =
1771173253 0.21 10 0x3cbafc4782b6edc1c2d0ab2b556aeef829fe6ef020c8510a60c0f1314ed9a612 =
1771173255 0.21 9 0xcb0fbba5b3cc636ec1e2b03c113f7f039cc7b070949064e57e2fefb311280a9a =
1771173323 0.21 38 0x8d6e5aef488f3ac266f97ecdf5c6d86f2e76b31435d2c73fe3e5d7c3c67d5b5a =
1771173359 0.21 50 0x4e5da84d46af2790314f03fbb25fe996fc188da9c8c354c9d39d7bc2b6d5050d =
1771173359 0.2114285714 7 0x705e2330f3fe273935e4f02aea48d4ba80742cb047a34b2d8dadc9282f6b3860 =
1771173359 0.21 30 0xb109cb2ef5fd7e1ff1af94f0a5d9231fb858f9dd2495c8f94d8fc5b983398d61 =
1771173359 0.21 10 0xf452ff23b76d75295d4657f7bc7a4e5723e8016f4f6fc40e34ca0f3028ccd622 =
1771173369 0.22 50 0xdc0ffb84485173ae7691d80a2a1adfbfe2acafacb75d54a191b17f87bf8d3d1d =
1771173387 0.22 50 0xe3f73d1c612d49c4861408da1d311fdf7a0e0eb56f6456fd562100aadabaa616 =
1771173403 0.2287856779 498.632607 0xcff33c4c8e3c1410785855914001f60e2ae4446ae8a464a20bec94c24dfb51e1 =
1771173437 0.2 5.42 0xeefde81d387f5e71bb4ceee7c4aad69712abb92d3a6c3c3ef1a1443c030e921f =
1771173743 0.19 10 0x08217faf4f5505f5b8d015f404caf9087919669bee54b408fe1061ea8195aab7 =
1771173743 0.2 10 0x277dfc8363dbd4f88aabe8f1411f45065040fbd8e340c7f8bec37c1b8e856a19 =
1771173743 0.2 10 0x658dab8199a654369b40d3311222986375943e23edbf9e685018a0a63f6c479f =
1771173743 0.19973 10 0xc2ab4c92af8d9f2d2795abcad969decdcc118462c93eb8b70377035eb9016b81 =
1771173743 0.2 25 0xc9091877fc36d254152b82e1aa51bbbc649c448cc3c0d5412614d07ecd284c0f =
1771173743 0.2 35.2 0xeea9d2ece4197fb29e35f2c015d058558dd887dfd358191acb2dd98b6550fb32 =
1771173745 0.2 10 0x9f37a2aebf1f8ccf0d43ee886049fcbb82d7b3d8ed6c766d865c63afacb29a60 =
1771173843 0.01 110 0xfc51d216d23d314e26ef8cf062929b49df6bef9f8d456a1ac0aee6aa3d109034 =
1771173845 0.01 18.29 0xf46babd608e0880e5331ab0555abebe25ce96847f27aad5bd3c239631f04c409 =
1771173879 0.01 11.54 0xfb9438edaed75480f3847294704230d2409ab387e1b2eaace18267eb2abcb853 =
1771173911 0.01 11.83 0x1b3640acf9d56ae36bb910f0563879777b0aa0ac46eca050041ac2c11f0ac687 =
1771174137 0.001 49.47 0x9ae3745026076c1509bd7c4d6337b0cd33f248009676cd5e5136d06a008212fe =
1771174553 0.001 7.6 0xdede4953f4c377898a2ca896cc081878ffe00b5fdd547b098729aa5d6b893148 =
1771174567 0.001 28 0xe047c3f26c9dc0fe3cdef45aff72505e0daa8e936983949c7416649f223dcc5c =
1771174575 0.001 6.13 0x248dde79a053ddf4f0bd01a7b486392cf9302f2d54e2084034cf4870a347d74d =
1771174875 0.001 5.26 0x433ae0763d961dde86deddd56aa8dd047ac1f60f585f39552d1ce15594e578b1 =
1771175387 0.001 8.69 0x3646b05ae4d0813c97348b972be7e360c685538f17a3ccc907d2a50d06b91e5c =
1771178527 0.001 1000 0x0499fb033cdd1183f5d085d0d0684ef826abafc734a93151dfe8b9f16d0ceca6 =
@1347942 Yes
1770483001 0.001 104.77 0x68a738f7c1169723b31ceef3f2b8689442b9483cf3d95b70a3bb20282be03b9c =
1770539111 0.001 0.25 0x501d3f4291e7c5ec4dd1a708933042c9f38e94cad85f6ac20f69a44d685fc7f0 =
1770544493 0.01 100 0xd25051e16be3237da409b03fafc7775522440b13ae2d766a4705ad083b745d85 =
1770713555 0.004 0.47 0x8077f64fdf9519fa55c85955a7549b3fef9f84117c39d88f50de3b34d48e230e =
1770849459 0.009 100 0x16646095920c50a4b704a7cdb0da65f5c2b909eff87d8f36cc075271cfb8a100 =
1770871755 0.0126526599 86.938162 0x1c4644abb066fcef646635ad50ff9f3a756bd2c5bf6b5c7b5493e52ecf4a7fdd =
1770898647 0.004 2.41 0xf19b07313cd58d84ea7d0d825c440d577e9b7d7a0f60dc7aacbbd27d16841968 =
1770936873 0.01 20 0x3302f6b99dffd6a7bdff68c71b6d5b99baac78f0cd66cc8fed3f4f31d2b323e0 =
1770941691 0.002 36 0x31dbb6032f49ece8b1df2d891ba16272300116cac0f47494207f79f3b15f6fa0 =
1770948143 0.002 5 0xcfdf32534ad23165c0580a142965c3858bd9e6d42ce5438f0d0b3c6bfef158d8 =
1771107825 0.001 4.08 0xf8578220b0a4a456e9a9d1073ad2c7ac36acdb09d5b8ef01c9dfaf4d517d885d =
1771108789 0.007 114 0xc7e57cc7e86d79b198057570656af02d8424ca843ed429d102cc423a5aaeb403 =
1771123533 0.007 6 0x4ec5e0efd46a89ffa8cde3a6124ea53da59fdf2e1646cc3f1ad121953a6cfa77 =
1771130619 0.008 64 0xc8a9ab77744f6ebd0dbcffc7855387bee70628680099f84bcfb512d47c0641e6 =
1771135859 0.0289999736 36.206895 0x0b4e697cdd8a98c20d01e464e26e64c9c61cbb28f0d0b15b05792ab4c5ac0b40 =
1771135867 0.0289999736 36.206895 0x1be341d174ff96e70d866051cb85a79a4d96f361cbc00f92f219f8db06d2f3cb =
1771135873 0.008 0.2 0x3f19eef8602d5e4f72eba205d2e6b9a3ccb364f3df65c4ec2763259ccbed9052 =
1771135881 0.009 0.14 0x19130b5b78098fe85feca4aeaec95a9ecff280d7ec453b85aaf2cde94c7d1276 =
1771136983 0.008 107 0x83e94adcab71ebac743edda06039fe7604e2bc4516215bf122dc03716592c399 =
1771137995 0.0289999748 37.931033 0xa2d26eda34e556f90812cb23a19dab571a29a652b76efab871c5f7ec54311bc8 =
1771138019 0.009 0.1 0x51c10b372eea449302ef9d88acb2c98a67f45b7a6e395a61b328a94eca059d13 =
1771171573 0.007 3.52 0x436b883bd0f3d7dde55f8953e492492a2426738033354f122ef6eb8fb7e3adb4 =
1771172559 0.0257753859 271.576923 0x2732f6afc8ea13e3c99e6c3eabc720c39f9abc3fbdb6261d06fbca5857b42013 =
1771173631 0.0128 50 0x00d8cd8ab1be9b0a68b4cb4f0c080e5ffcc5e2053187dd94fde069d14f0c5ba0 =
1771173665 0.042 50 0xe48f3426ab5082366496bf4caa2e1e242543529100283e7f73ed3dbb751e0ad8 =
1771178527 0.001 1000 0x2cbc592e3285d1d5f9280d8ba768fe388e7acc002a0205ea8ed0e1af9367efd2 =
@1347942 No
1770423659 0.98 7.35 0x7bff30f542d30f1f172ee15af41b060e1e23f382cf928599d4944756be44d6b2 =
1770426179 0.98 18.0306 0xcd12bc88cf3da6dc150bba027ec3f282c4626c5a7c973a71a1e1126a75e8e801 =
1770426181 0.98 10 0x4461bd9deae42e384148980afd912d89e2a6dcc6658dc950c0c211678237e396 =
1770458431 0.99 10 0xbad33375011b3a3909e46d5ab4c801bf298d4d1292e2138ba9c48fabe5060cac =
1770462375 0.99 7.04 0x07372727c25d7b2d759f73d2d4afed06aa863a807806d7e6cb693c3d14de7547 =
1770462393 0.99 5.23 0x2c91d3421f52cbe76cce857667b1c4b9117a063c9e59691c6185f8366d596313 =
1770464353 0.99 28 0x22ab00ef0db07c676968ce21b2497bc118f7b6edb0ca58063d78fa6f33053018 =
1770464365 0.99 28 0xc3cd6c1836e42731543bab7c554c974d63df4073a406834f1528646a7731641f =
1770466975 0.99 8.0909 0xce884b51c93643330c70bc51fe0ab91b39139f3b365ea7b217b7f638c267e1fb =
1770473065 0.9968478947 57 0x98e23bb8fa6adabd3a4b8fee5a1d3d4df6a45a765955ede1c90236c74aea3c7d =
1770475253 0.999 13.88 0x6f0aa87f05006d1c95e67b3a25d9fff93583181126ab16d99ae8196aed25c049 =
1770706299 0.996 10 0xcecd5b449cf6531393bdc401c1ff5198e15e84f33aa4835a35ad816fd2569d66 =
1770706301 0.996 20 0x61b466fca9a2efd229a6c5344db85cca58ac10ba3700fd49774ededb8b2f4b96 =
1770713321 0.996 17 0x22c125eb78e95a3b3fe09c6ae15c6c843ac60c4978a277ccb075f6429222241c =
1770713725 0.996 30 0x07bbe445226cdfd97fd6061920944a619e7e9a8dbe4db0f954a4885db683071a =
1770713725 0.996 10 0x4e4e2165f2b7ad3a42ea321b9c303f3c9f87146df6f23a6734412c0ecc8c0fd5 =
1770713725 0.996 23 0x6a8df00326e83eada1ee17cc12182ec69eeffc1b37a9d4b670f19d81d23332a2 =
1770757169 0.994 6.46 0x8c87734c5f3966877c810f5b92908c0c84a67a0268d89f0a14db005bb3f7e903 =
1770827589 0.998 10 0x1944c85fb8993010baa26de00a0442e66b37d300685064c94430e5cc4e4f6954 =
1770871293 0.998 5.8815 0x240cfc71b7c39db937f5abf74be824bb971e9fb6f6f8cc47972ec1a289cbeca3 =
1770871753 0.998 30 0x7f5676fca03845c75db9f67af876c81a18ff89a0c8606223967f695a0388102f =
1770935453 0.996 5 0x55232628ff926e3f5f80057e21c70d5d494fbba090bc99b1838eead7b9a3c359 =
1770941195 0.993 30 0x3965a82eab694cc723286e2c2aa5d839bb06374eae002569d6cf2358267b9e13 =
1770941205 0.996605614 71.25 0x29bd16cb8592424881630767542dd1ddcec13ac1168b759befbdb33ff9180ee3 =
1770941221 0.997 71.25 0x575f1b7233de17ac99d9d524906163fdf48bb9e8bec981af6c5ee4fe6d76b4e1 =
1770946273 0.998 5 0x2fa2c1b39a17f47a12400f641edbb0336ecaf9c1bba08703a617ab3926fd819f =
1770950449 0.998 5 0xfa89046480d417d4fbbbd57cc4abd0ed2fe3a441feb20d47e410dcb5222f0369 =
1770951707 0.998 35 0x3b9921160e55596880642c113a1fefb155761874189d346f2141e0e9adb82c09 =
1771062147 0.999 5.91 0xe55f42c4e8bbb2d2776562729f100188a746b2e8c8861ca1475cd67117e973ee =
1771064729 0.999 17.61 0x8a07c3550448b013765fef4209fd44ec3482ed892bd11f2c5529faf4d3f45044 =
1771065747 0.999 20 0x28d829b075343efb78ef331c619c03d22c38a1ff8cda5192a2af5a8223a2670c =
1771076085 0.999 20 0x0b3682d7162093199c3576f56b35fdf6c8358447a3d4262f77a150cd8c66055a =
1771085531 0.999 20 0x0afe023bb884df1ebea0ea9b2407188ffc82b77af42672d4cf54133fcb51b9b5 =
1771086149 0.999 5.78 0xc63def4c16aa1b7f41acd3985a9639757fecd61e4623e851e7386e0b845e727a =
1771088985 0.999 5.56 0xdc2f0c9898976dd7496818ed0c2f471f780a4259694fa179a7461ff85507b372 =
1771089711 0.999 20 0x797998b65ca5ab068575fcdbe0abffd7bb29f4bb76771dceca633f1b2ef0d93b =
1771103733 0.999 20 0xb2da8683bd5dccff9fe268f141b21cedb5e115ba2ab8a436bee210862d71c8d7 =
1771107441 0.999 1.9 0x77ce914b19046113b9097912203fb384ec14f1f52380fec0498c8e41bb24f3c4 =
1771107551 0.999 10 0x56b78ba7a173a2f57fa0c497ebecbff7151de8b0b7aa8cfc890bd1d24b245521 =
1771107551 0.999 30 0x638a2493455de1d6940f6c2469cad59cc5d4c54aadb5007e7ee788745f7ee056 =
1771107553 0.999 15 0x8dab48c03cfa286dfe2d7406c1ca80cab96e77045478189a19d78b43f15bee04 =
1771108623 0.997 56.53 0xf36d559e94112ae6653a0a3f93712c16ba4db24392b4e910452feab5568b307e =
1771108685 0.996 5 0x29dd26e66531ba9b80caf1bdc2e9578076a9aa9ae60a3e1e724add7e71776878 =
1771108685 0.9969655172 29 0x72fb797f486d62c5fa40f714535a0387ba0a94d3d7e0e4620149459ee67bbcbd =
1771108861 0.993 5 0x547183c76cb692ce9dfc49de6e6dc10beafccd67beb9e5c3aeb5cb89a4711cc4 =
1771108879 0.993 5 0xe3bb9912ace0bcd17631594a3998b298dc49264bfb0a35c71601f80257c705af =
1771108881 0.993 5 0x83459be3d62945138d1b168b7c4efc55c4a01b90f874542097b26a033cb9762f =
1771108903 0.993 5 0xdb658e3f8e3574ce1a113fd9a195733dadd7929a498d0976cb90fc43d0090f76 =
1771108905 0.993 38.09 0x93743fb3872f066f7d875fdac5a0546840f6b2c7de30ed23bc8ec6605cd3534a =
1771108921 0.993 10 0x0a3c8524d6f7d3924613891c97ee372b255bf90df78e489328c099a6a556dae2 =
1771108923 0.993 89.22 0x8ff414a9eb2281a101a91f75c8632f0064e65d8cc2fae1cee594445193d90df3 =
1771108967 0.993 35 0x5cdbe5f0c43cff6fe1f4d22ead51c0cf8b5b1076ad7ed9e1aee14ed0aa4fab6a =
1771108969 0.993 15 0x75e6898203e762e0ad2af5157ca930a1f1fdb48ab7e5539ac807d65d0610eb18 =
1771109105 0.993 176 0xe769cc6ecfd74e9ab6d2d1f4705ca62e5699ddbd35da07fd549b43208582c1f9 =
1771110711 0.993 12.59 0xe48e449fd4954555386ad58d3a6160953d626d39c932b316acca8e4dc9cb7014 =
1771113111 0.993 39 0x9b388e111715b1c413b4e5f04cb106d2451973fd92f6621b76417938731cceaa =
1771113883 0.993 20 0xcc4dc3114fb07066ffcc95b0bfbc18214d23678f19be9e3df5d13ab25b0e2581 =
1771113895 0.993 16.21 0xaae0fd3b695beb67674d05537929e3f5986a21b53b87b0d789264bf9ec1987f4 =
1771117403 0.993 22 0xc6e84cb47acb4bbd710692e6ccef23bb762d6ba0af32828bc20d68f56829157d =
1771119799 0.993 55 0x6bb0c661b4db898ee5b3987b8c6cebc9fcec06968a7a198ed6dac9a37a180e15 =
1771119805 0.993 45.73 0xfcd689763ea37598452ef9892019546a86ac9732f25c15b6cd50f34a065e4962 =
1771119901 0.993 5 0xdb12fa9f8c7ccdb9c0d8b0325d89a0cbf60d9b370485cade4e16ff4b88e74cd3 =
1771119903 0.993 20 0x15b3b98354119687a9013f4cfd0c1c4b532d2c34f1b49b29458d7fc81c8f2bb6 =
1771119903 0.993 100 0x9c1443c1188299c78ff20540a1f496a0045a4ce955c6bdd739aeea35bc5491a4 =
1771119903 0.993 50 0xe454d39a565f8fe672cfd363762c421a5eb5b93bb6a554d7d3f56ad08a1e3708 =
1771119905 0.993 28 0xb6ea882f85c67ee1cdbb989868e2eb04b60a0d10810049ad05eaefaa38cb7443 =
1771119909 0.993 57 0xe0cf759fe8771fe05a790fe78c52549960b90ce681a1b763e37e4fba2d3b775a =
1771119925 0.993 5 0x98b425ce9d294eda1a5b3263820e50472c96d60275ed31841233629600ffa761 =
1771120137 0.993 5 0x100c2e744764badac7b1b5ceab6e8d292693bf522a4b9a19c44ca8a5271af8ba =
1771120137 0.993 5 0x34ddc59ae24f27c39133cca9254ab65381c2c1bee88b9ebb31ba123eec0bcce0 =
1771120137 0.993 20 0x650d4dfac06d29374fc63290629e38c1ba4d003520c96c209eedfb24675a9049 =
1771120151 0.993 5 0x076a7db70c514a035066b87b2035958112a758ef807378fe675b0a8c79668113 =
1771130469 0.993 10.94 0x6afd09addec4ee120032e9629f2c1207ded6bea5b28a77582f1b5c093f6f91db =
1771130527 0.993 21.22 0x7cc94cdd26052c158d7f031fa39a5dec2a11bc0ddb8ab1a2161d47d42ef8bc82 =
1771130545 0.993 16 0x4b2f9f96b63f736bf2d7fa559dd5ff0f86cbd4e279f3fdb60577e9f1ea4d6e36 =
1771130547 0.993 17 0x9e6d47f75778f32d7018e9d758257730e9bf16779b97a5d5fd48c20b96f5679a =
1771130547 0.993 5.97 0xa46bc3228f91b7dd59f4128eaf46de6b2bb3c7a6786c895c0f9febc57ed90cfd =
1771130555 0.993 16 0xfa0233dc9f5f2bfc8d7eccb71dcb2f62995cf9ca402af3e270aa246d49df231a =
1771130565 0.993 17.79 0xc8ffd92794d0fa61e8ebc0f4fa4d45dde9b787c5543c842aa6d1148a55a43338 =
1771130579 0.993 8.19 0xad0e8158d25087ae6a4c92c8b2db8174f0d9c3812ee12fe9f99aa41748ebc96c =
1771135849 0.99 30 0xb054e2922221536023394395878f899c891759a941461933070bf97e006fbc9e =
1771135851 0.98975 20 0xc2827d0b00aa37ec0e64088e277cee0a5b69d951e92c8b01a4d0d1fa0e8723ae =
1771135851 0.9917225951 447 0xe04f2b6dfc62ac88a3f0f5ec9380d90461ebbbad0ad0ba281f6d5194a08d0fb8 =
1771135857 0.9919298246 71.25 0xeece76ec1ef007bdd519bc12f10309710a9fe937de365bd75238dda3c1d326d9 =
1771135863 0.992 5.43 0x233a187dc43f55fc649ccc4082baa3df5ea0f285f16ea51b02b77e178b546e00 =
1771136045 0.991 20 0x075f814403de1b409697d35deb5d44e98717e7473c5c8489c2d87aa12989b246 =
1771136045 0.9918636641 131 0xf6989bd4a45eca86bf655de8a41326828f9e639e5e9356719f114666bed8d728 =
1771136053 0.992 71.25 0x4203ffbdd441f4d05af3e99fa9671c6d29dd840e707c0e5da492150f13d0f8c7 =
1771136201 0.992 5 0x23ddb233de40312308f69cd3a4b282a844b75a7236dadedd3d178493deb6ec5d =
1771136201 0.992 5 0xd5b2cc3c7eed839e08af5589ecce5fc204ce73459512dcecca2dd3b329e7ad63 =
1771136741 0.992 5 0x08d33727474e721655029cc4bd26c4fc23905017a20dabe01793452431fc1237 =
1771136907 0.9926 15 0x44e4affeb1ddd9c002487829673dfe9c9f9e50c7ebf7162c02433ba5f50238ec =
1771137993 0.992 1.28 0xc52ab49acfc0fb43a11be2d3da5e0be5f5c77c5c9cdec5f133f0b3238b58a5ad =
1771137995 0.972 35 0x6e97bfe3ab26e6f6284d927d807c62c66719da032bc69c0471494c52a9b183b5 =
1771137995 0.972 143.57 0x87a8cb66be801bc5cdf8b4b6e00cecd6dd14ca9ba75255bca84f64b881027551 =
1771138005 0.991 6.36 0x768f49454e6ce999b2be3fdcd6fa37f3b6ea2486ddc554aa16e12dc24b1630c0 =
1771138387 0.99 10 0x14e221aa776c3d016058684c65330a9afb3f6c95ecc2aa16549dab3f0585a20c =
1771138387 0.99 10 0x6ed9cd4da730ebd66d65f1fd152322f318d16820586cfa519f2b790a0036f264 =
1771148817 0.992 1059 0x4f02ffc5bd834171674afdbaaaa410a2283a323a14be51b0540c23627e33cd80 =
1771153219 0.992 20 0x541c04df3a336c7174f7a1931121d628f8eaa7cc4eac03dcc4b4e3804d8766b0 =
1771153227 0.9920322581 31 0xf582bd871e79e5560f944f5a4cfe7765ddec4d993fbf7832543b203c30cbbde1 =
1771155109 0.993 20.1 0x11719038316502174198ec1118f77b1a336f625bdd3249b470003f89bf1d5ace =
1771155109 0.993 10 0x93a4ca38295fbe07137e24f201b9ff813eb6d16a42b6ba8a5e9c468f524c3e0e =
1771155109 0.993 10 0xaf0620037aa126377be13cb02ae4602a128fb643e15becaa92924258b078e7ef =
1771157435 0.993 569 0x07eece4d554d15b272096607ff70844c72e62e8a3ca8c615540402c8074bfa27 =
1771157837 0.993 12.5 0x695f3b3aedce8d8f0e8bfe9c6954c8b7b85a88a0c8e26d8432fe00c12217eb90 =
1771160815 0.993 299 0x3b8437a3ae26f72502218d0c0b4e3a5f2d21ed3f472b43ebad7b28ef5f3b6949 =
1771160817 0.993 15 0x41bf333d74a76ed624ce9fd53a47a8e7aef104dd21cd58a8d3ea0bf9af8f9e24 =
1771160825 0.993 57 0xda3e0160b88e8fcf241c78aa2a8e38291a89f2faaa53b393d6ea2f203a0b4e62 =
1771161779 0.993 15 0x20fbc192f41067b75814763479c5cb44375a4bdd2a90f0fa08f4cee4d9d6b38c =
1771161937 0.993 15.51 0x516072b974791e2e33fd878b7f6b2db4aff450132db3fa6b5b2cf5c0292ce098 =
1771161937 0.993 14.49 0x631971af20ce52e06def732571d9115825fcffa24f63b0fb849e63882206d421 =
1771165497 0.993 40 0x19d791e4f980b4fcef4531fee5c950432171ed261d29f8d66fb63674ea4fa4e5 =
1771165761 0.993 20 0x5d2634322a2fd710f161ba3454e46087a63262d007db79fc828a89cf43fb72fe =
1771165763 0.993 13.7 0x07dc9ce4a23954bcf9d587e679a0ecb59ed43805b528a38505a0888bfa3df736 =
1771165777 0.993 20 0xe3cd33bbc077fbbd98c734b398dbea1063a4f7d0fbeba15c7fd9b87fc83bbeb1 =
1771165779 0.993 26 0xdfca4f97aa4d58f57abbbb67324d01da3f2586ba4f111cb1c8c3fde46fea2fd5 =
1771165781 0.993 14 0x0946c687991fcbe5a474ab583352e93e583c952cfc249f12843203c12a606a0a =
1771166201 0.993 20 0x506e1e0ecb3b5bedb4fd2c60399bb00e2d4179ba224bb4a57ee5045016142be6 =
1771166483 0.993 7.5 0x01e2239bfaaf58b7098ab8eb120ea6f86503f1f5abf8ac41dc9b277c42411dff =
1771166865 0.993 7.18 0x27c89c121bf03925201c8fd4b70bb69eaf5f7e47df9441f6b32e09266257390c =
1771167003 0.993 20 0x441a71adc71746bea6685eab5b9630e952ad2857bcd8deb38576721a28fa862c =
1771167003 0.993 15 0x7c1195ce0c042f84d417acc59f410c39fe7aba438c3d61d10b08b3b1916ac0fe =
1771167003 0.993 227 0xa04174af142d05805e2b82bd6405a41d124de6cdec6c99311c8f07e37aac7537 =
1771167017 0.993 5 0xb9fb041553d019972bc3ebdc2d6e978e3fe2cda08be469aeecfff056110bbd32 =
1771167025 0.993 30 0x02baa736e277a8fd1aa9cde2bf65e64c44ce5a9e9309359878377e06fdb3571c =
1771167025 0.993 40 0xbc036073a79cae62b589f6bb9c9c6cc35fac8f5489060f1cb97e971a81ae7bd4 =
1771167329 0.993 402 0x156da974a7312e20932a380f7bf64a4b9833bc8ef9bc266c6a42618382bb38b6 =
1771167675 0.993 8.47 0xf39493480f778aac658d75dfd27cbe36f9144153e0849bce49010bafb1b9c876 =
1771167677 0.993 20 0x5beb7db02507f83b8d228978064dbd0242510a100b3a6c8bafe6b373f4324602 =
1771167677 0.993 280 0xc3ba855243bbe8d63d52e6306cf2f9ee2d248b437d93b6096bc2dc2f74eb7306 =
1771169541 0.992 50.87 0xa68e37c246ae1b51b1bfaed7baaec1085dba5febccd22a079eb080c8fee18a22 =
1771170013 0.992 54.49 0xe6adace98d3223b6821652c7d75b4bb75c8a10043fef8b5c4d2cfa56500e1eda =
1771170343 0.993 16.858 0xd321cc44067ed12bc20ff00434deb7ec062df571421ac9ffca0dccdc1f559158 =
1771170353 0.993 218 0x3f2e331cc6f2911b68222524512d6bddeef73e1e1ca843495f89d6f3650d9185 =
1771170353 0.993 30 0x7828ae06d99d81b484fccf0a87481c3a17815021ccc417b339f41aa127ab0f10 =
1771170719 0.992 75 0x5f220e742201db3b30a474133607c640d5ab59ed0de560c5f284293f2e29b25c =
1771170721 0.992 5 0x70836e9ddbbd363e1d61db3532a354ac3043e88d33709e927584783399d2a9cd =
1771170755 0.9929714286 14 0xaf6b003732753e244aa799c28f9e68238df7ae9291442222606e0ec9c375592a =
1771170813 0.993 32 0x862921e3786e2853aa520ecf271cd52ff23ed592260acb1231b301ed8a75e9e1 =
1771170835 0.993 5 0x10e6be1bfc9ac9fa139accecfe29a02b94be2a68ebb97c855517511dde2e42b0 =
1771170931 0.993 10 0x08b9616c06b4a9024ceee428854b1c2a80152e5d3a2a5ea517f38026cd516a18 =
1771170993 0.993 10 0x4218badb1d1152b26526fcfc464675b2c15c51dd52557a6597076829a761b6cf =
1771171053 0.993 5 0xbced5eb3653cfc55d04c003e9308e441c3e61140e92b80e2a06393131dbe7a6d =
1771171085 0.993 5.4 0xd28a770c72e4a1b7493acbf6e6807cc54bba5ef60ccfb3a978d187707ced8cb2 =
1771171095 0.993 40 0xf8feda07283f7dc34e1679823dca8a51bec4dd279de1d95f9af97f052507358b =
1771171097 0.993 12.27 0x2a4b5ee702074a9bb792dbd8392b959d6cb66bac93b09f8d03cb7b4dec2bbd6c =
1771171129 0.993 7.6 0x83d45fc56ee3bcb45687e651c8ed0ea6cde2db0d5c3b4435e9e5bb8814fd2272 =
1771171235 0.993 2.29 0x24b06358e5b6a556b7333b8352294964be6f4be8ce0980ee3517aa6bcdba4993 =
1771171249 0.993 41 0x69cad9c6412bbf9002a9748b7a8453927226054f827a1edce9e0497fe321578f =
1771171339 0.993 151 0x9557d44fb9e16cee31b22c36062b2245312c03014de302a4c7e9de1d882fc881 =
1771171339 0.993 30 0xfe365bad2ad096f4970a8366e24ad06b34ca786bb42ea4655a72edc546096f7c =
1771171341 0.993 5 0xae9b9906c5ba4983efb2c7d247672da1bfe007d771efe288226af3534d73edad =
1771171357 0.993 25 0x9b689e9bebd842111af9e0a207ac6e9ac5dd9aa6038cb0115a1123ef31bb4078 =
1771171369 0.993 6 0x351dc1011ff2d5bbcdf4afd7c9fef2752c30b021bee631d70c3f6215c3e8d5d1 =
1771171533 0.993 38 0x9d6289f8febf1c1b110d0426a06eb76c1272ac637b3467c2139c88e2d42463cd =
1771171563 0.993 21 0x86c9f06f595f3b652a1023c98f89ab7e0c79eb4f43a7f0c9e8b47bf559123c9b =
1771171633 0.993 5 0x30abfc916690dbebb6e278066ec3f627427a4e448a56eae5f38f9e2a18a67e8c =
1771171647 0.993 70 0x3cb68160f039ef63784f7d4bfa35e516471ab8f2fc64ecd8b9846462f46db758 =
1771171647 0.993 19 0x419674832f88919bc125d0defc03a1a74a4d0e170967876256cb95226d425fc1 =
1771171663 0.993 7 0xd9401bf1a03263f1c1431a7a6681574b678adfc4f5aec652bdf4097f6082f868 =
1771171747 0.993 30 0xb7b7d93034f016c4dcd3427a98e0c3135e29b0e2ce9c12e21090fc91359eb206 =
1771171749 0.993 20 0x6e2c7306813161040111362ae73842f9ae2f516b1995cd35c24912be2269310b =
1771171763 0.993 3 0x741a82480c0a82257e2d5f03fdd9cb900399b0f09304cdd3eedcfec8e83168e9 =
1771171859 0.993 25 0x888559cee0d06233392176860dd30a94c60416d84418f95e85f40ea064a56654 =
1771171879 0.993 25 0x74cc823b917334fb35d2ec200530bcd0db5b9c77937a88201629d7b556a0d04e =
1771171927 0.992 15 0x94debbd1a244fe1a31eb255fc44419a383b107e5f4f452031e0a5cb48a32e4f9 =
1771171927 0.992 15 0xa525ebe6c0f525fd1319d4eb4f506c8bccd752429d87fb989e6145560fba8bb0 =
1771171979 0.9927562189 201 0x24057fc887a9d0ab54dbd5fdb35920df35104a22004f47881cae8b917f570d04 =
1771171979 0.992 30 0x9a23e400e356e4152a78fb1d667fd4c56babb551adaa40a72ccc8ec3dfff3cd2 =
1771171979 0.992 15 0xc9b79799f8c1858d434fd96208cf1177a964d921df52ebd350aac43e8e25946a =
1771172049 0.993 13 0xbf770042921f0221ce94b753869f8264f72c5fa04f5557037f180e4e2a408590 =
1771172113 0.993 13 0xd7c1b54085cb89e1672880ba96d09c666806be4ef8ca9785c6232593eaae9b8c =
1771172221 0.993 5.84 0x6591988957655036f377820aab8eef51b5e64e4de550ca5a5bd03a9c6d222b10 =
1771172225 0.993 10 0x74262b7c3f9640895d69ab604b9abb525f502c0d4c2282c59e0f0aaee5fc3e34 =
1771172239 0.993 6.14 0xe55384b0897d7209d6e8710da46d94216dfe9cb9398c585870dc1f7008dfea93 =
1771172247 0.993 11 0x59570141bc79350827bc34a1573f4c02c9f683ffd10696ee991b9915b2a5f92f =
1771172249 0.993 18 0x127ed5151432ce7428004e809781274eb7a4d035ca10d1b65003946260301745 =
1771172251 0.993 4 0x08e596024521d34ef8b23ba2eb46a9dc6202eb1024c14dfb1315ee11c92d347f =
1771172251 0.993 5 0x382df1aada9c0fbaba85206808df87d93873d6c15229e3fa674a6d5fae71a536 =
1771172251 0.993 7 0x4e235e55eed492ba6504219fa28f9eec139820137a7e191d4ae2212449b5eb36 =
1771172261 0.993 7.2 0x05422114ab7face3ce8788515cd8e6eb86ba452966bbd0b1575da4f0c9ec0bb8 =
1771172261 0.993 30 0x2dd07ee97867438d7d551abc1ae4bf5e63658399ca319470d35a8a9a8a16b31f =
1771172291 0.998 37 0x4e555942d0e664775fa677dcc83c8d4ead732bc55f9337d72ec80f8976fed340 =
1771172295 0.998 25 0xa66fdb5914d1636257e0758a960ad16ba50e4e9979085b96d3abcaecf73c5641 =
1771172385 0.998 12.04 0x5ab4f871458650c3c6f7101087b0e2f4c62cdc28a3ff2b9ce98cb7ca5a016e8f =
1771172481 0.998 38 0x29e9558b6438381c62a4a9b6ff3edddea096edc70c051a0be94eaf8c9911a047 =
1771172549 0.998 50 0x52018d34436ecaa267609312af7608c7b876b2caa516209918cdb90f5bb286da =
1771172635 0.997 5.99 0xf0ebbcd7c9d1db55c523c27a821aa876c50cfc9c39485a1f83864c1a9f8d648d =
1771172641 0.99 10 0x609337e019b2d9dce258ff2401fff5e2d607d394e16ec7d6c664babc41ead6b3 =
1771172853 0.997 26 0xe87231f8747289b214c7b005600961a03bd6c15c8757e031936e5d2fe02ef909 =
1771173251 0.997 25 0x27f0b560dbb4d4f45de922eb338f0a1e93a81e6eec39fa37f19c00211853c260 =
1771173253 0.997 10 0x35a77feaada882d380713cbaffecbc6be34b5af4e9bbcc53b80cf30a61c5350b =
1771173255 0.997 9 0x6874dad226f6e3cb8ca78f67f2a9abdadf4917964eeb17d8e37154b293eda1d5 =
1771173359 0.997 30 0x55850971527569d2fb78fac180604d25f26e4bf863a237c3a15d17b281c769f9 =
1771173359 0.997 52 0xa895260e91db726d7eda30068dda032503013a94597cbdadebb58a6a1c4cf575 =
1771173359 0.997 10 0xc955b2df15a3c85ac6de84153d747a34ba73a5d41cd201b4a9a41897840df28d =
1771173383 0.997 7 0x5fc76498bc3e4184bf157cdbc10a8a7fdaa286e6f9b4f9d833c62b85e8fe86be =
1771173699 0.9985981201 6783.17 0x837d792389a6e2db118c12f4812b6ba10f4abe53a98af2c66bb03a6672295368 =
1771173931 0.999 6783.17 0xce1a345f216860b4734ac3a3c31fc1d22a7e989101528fa70736f73f3bb9345c =
1771174551 0.999 7.6 0x8e76b1f405f019430d56cd5679374f6aff467eda56201b0539cf7fd9edbd5f13 =
1771174567 0.999 28 0x843d2da05133365a7db33d4a98749bf0bd293455e2e9385fa9160e493c63ab20 =
1771174573 0.999 6.13 0x6f5278d0b7bec391d9e5e788db1846884d1afd9407faf7e254b60ef8156af345 =
@1347943 Yes
1770539111 0.01 0.25 0x5be8a8448082022ad7da1184da828eae22a579097bc866356dae2c51089ff9a2 =
1770713555 0.002 0.47 0x7654f1756bb641a08bd10bb4f413b3af99d9295d0bd52cfa199298e8791ba590 =
1770757313 0.001 6.46 0xa029ac68683a5e4f5dd722b8bdb6c4f9ce6bdcc29300209c292666a8ced4e91e =
1770850195 0.01 56 0xc514d3aaee7e0478b8db230ddab03826c30bae2ae77904468f369b982169ad7e =
1770850197 0.01 44 0x974b095dec70c5b59da9d4fd0cc6dcdf1c3c281db5695e7674781f80899ca4ed =
1770851579 0.001 70 0x88d66724479bc774c54883435a432a4b05b9ff13cdb1a275af7e1224545e511e =
1770851585 0.001 57 0xed78ee0fbfa9e8cb4063001fb375ce9295c336e8235866ffb77e8fbac1bd20c4 =
1770851595 0.001 7 0xc1902dafb4be9d4fb846b694f602be8b5b591cdb1a022dc1a8ac95754296fdac =
1770851597 0.001 5 0xf39f8290e41d22974c30ce7d189d154d82717b7f0726ddd17883e10f0a712562 =
1770898647 0.001 2.41 0x8d66101944088f06e983b1cc027953aa3975f231bc6f7cd9990b0a1acf1e9ddf =
1771030883 0.0130299401 167 0x9da4ebc1abe4b9b9431a63ad597e8b55d9da50aa0ca84cb2a429cc83a1f5397b =
1771086151 0.004 26.01 0xc0de1e0712b3cdfd5e7696ee1bb1674b41cf84731ce689bbc37d07c6714c4411 =
1771107825 0.001 4.08 0xbc174a29827391b9bd9c27ca9e2e23170ddad633fdf43e0a8aab95366fa1962e =
1771109079 0.002 15 0x821b85a8081437a305681f81622be111f4917d3ebab471c9f9c2a3695592c975 =
1771123529 0.004 5 0xc93263d374bdd1021c6db977352d6d55ce155edf31bb8706d89362d42e1adfd9 =
1771130483 0.0106907895 97.28 0x7f3b60ce21ee32698cdb18ffe065c0dc48197ca6773fc8e042296d831f5ecbde =
1771130493 0.003 0.1 0x974ad2b141a09ba9f4a7150aef1292a6a9eaef0eceaed0f25402239a12aa0c3b =
1771130503 0.026376274 39.429375 0xe54986dd0af448ea190f619f29e423dd7142dc5ebd374c2e081c3f4e32850cbc =
1771130517 0.003 0.4 0xbfebf8d7ed7edc522cd463d6a05b5ae91c5f029bbb3ea8bf2bdb28582016dfbf =
1771130527 0.048999957 21.224488 0x66fea30f7d414d6c868a5dcc8eedb1392287f9f695098585cdb04ef211172e53 =
1771130553 0.0749999369 13.866665 0x8a1c5a4124d214b12eee12c7dd15afc146ecf809fa9346cdfd72d3a969df1f02 =
1771130561 0.0769999345 13.506492 0x8093e6e62306768e5a9b43678434bee49cd7ca011e7f57e2909cd305e9478e40 =
1771130569 0.0769999345 13.506492 0xd63b4d2a81e91fa96865220077e83e9374f7493f7347f4b71c8f342eea6d40b4 =
1771135859 0.0289999737 35.862067 0x39bc068eeef4d088ee6b5c62d72ca10cd2cbd56578079a1e488dfcdc681fb523 =
1771135867 0.0289999737 35.862067 0x98dce24f3dba9e35c4e2596f42e11c367e3ad2d9f526cb2a208f3c24c60c3c85 =
1771135877 0.004 0.27 0xebac1b274ec365248412391f35c0f079418fd6ad8fa9c31606c199f12660421d =
1771135889 0.004 0.26 0xfbe6b0d338466435c215ce618d51fd38956866b0e838116d71b35336cd9024fe =
1771137015 0.0044169611 226.4 0x5bd60ebcdd1bbf3a70ea94ca32fc60b67060102271241e66ec1ce8b20e93648e =
1771137995 0.0118790497 92.6 0x18bc714aadb4075b8c5e0b9fe7668b3ef86d38f2541e961aa7cae9082b7abf62 =
1771137995 0.012 61 0x418433d209ecadb068f5f1b177c71032679ce58d170e825145bc7e79a08aa2b2 =
1771138973 0.027 300 0x49fd13fbdb3a7192fd9a5b785b61edae05b85ef8d2649799ca67a3f974b12e21 =
1771157435 0.004 447 0x4cc5c1a92b6861710ff7c75ea1b60434484b8d490219d3bbe0252e72901efd1d =
1771162435 0.004 74.28 0x00f529c562e26a7ae5c054c51969a761a073dbf3d4ec7773e6bc6927c2f81174 =
1771166203 0.0063675832 172.75 0xf73fa2643f25506854627e56dfdf881c04d39ca9548f4def16a003ef2807d742 =
1771167329 0.005 71 0xb6bf0dc21a14f8b5040111f0383d5382fd467866aaa4cfdc3668d8749e782a45 =
1771170835 0.0065082981 384.125 0x9266c8d0eb6418f40463b78ebbccc1450ce44eb1cca833be5e8555e31950475f =
1771171573 0.003 3.52 0x6af5e0f01261034d3d6d92a23779307e89a14f4c018db3ca4493e86ade843daf =
1771172565 0.002 11.2 0xe4ed046974b2e3fb90c10703324d56a976515333aee805599a155b679536d048 =
1771172819 0.002 5.84 0xb9accbd6122e73a5b30ac713500c73994b947bb3008ff22c3c749a5fee01b151 =
1771173527 0.0013408518 17344.78 0x130f29960783e38081303143eb42917d6f818d56229315621dc3825f2a044440 =
1771173529 0.001 655.22 0x5e7ce6f02c4a5608d7c3fb58885a707250194fb3fabc3b396acb21b35da9d653 =
1771173613 0.001 5 0xd2eaaeffdf4f1504817240d1f6964307ee8ef292e9d3971e83c6dade6c2d5237 =
1771178527 0.001 1000 0xe33dcc2d25a3dea1cdab2edd021719cb0a4c4822ddac90d2664c5022f84771d9 =
@1347943 No
1770426165 0.99 10 0xd1a217fbdfc7619336b0ac39468c5aa20b2e448ccb344894ac8ae03da0caddc2 =
1770426181 0.99 18.0303 0x48a3e810641f8b4de8e6a3faed783138274d5eaca5a4a1a0b19b2b8d9319beaf =
1770458431 0.99 10 0x1e451e235f39d78773c06f4777c6298f4fc69869d3809fe0b284ccb61ff0d097 =
1770462375 0.99 7.04 0xf8b87f2830e53ec11a2303f1fdd416e413b3843df2011554dff8bf1a412e78ab =
1770462395 0.99 5.23 0xd2ed19e19ba730f4b4530d79339b4a9212aebcd939668ea4e57ec6a9dc5a50f0 =
1770466975 0.99 8.0909 0xb64a7a085482f8d57b90c469b04ca3267da6837d08f31dd82d5b8658d8af96fd =
1770706299 0.99 10 0x3194dd9c19a398d7476c63bd5ac2a992d5146f4c01f9a8d891e86476d32f3db3 =
1770706301 0.99 20 0x8863c4abf949d04b69e78ff02db40d48d708d6a40a1e0fd16c35e085e9bdbd4e =
1770713319 0.9926635294 17 0xe632d5862bd72995fce2bedf2ec9406afc9af58628cb58035188c5e8d9d7ac67 =
1770713725 0.998 23 0x2999e9a9153cba385bc52c4a25b92bba183a035a04d930b995733e4d26e8da6a =
1770713725 0.998 10 0xc7dfd49178dfa57fa725a35b7fdb50ca565576dbd8f9a44dc4a1b8b4f471f297 =
1770713725 0.998 30 0xcfbc7d04161ccf1bdda9f42990a8a031d0ca62d88204c96545808773a043b001 =
1770827589 0.999 10 0x136fef5d95a2b9214ead84787d7830b696fe785bc5d2e02268fa6a8c5c723bb2 =
1770871293 0.999 5.88 0x2526c0b56756c6986a04795f14bc04112ce5d723269ce0c8e2beeef98c822d1a =
1770871753 0.999 30 0x754ddef6e43f19966009c7823ec4220d1852f78a8818afe9943745c1f853433e =
1770905533 0.999 56.49 0x9375a6d1fd490a8cce3bdd4e400f301837f9ad5683f6863ab07cc975b722908a =
1770935453 0.996 5 0xfbc9830edceb14aeb53bd07cdf438049f8d49d1058057a049ac2fbca4747c848 =
1770941197 0.993 30 0xe0001caba0283806a5d096dee4614ab070394b838fbd698679bfe91fce0aaff3 =
1770941205 0.996 71.25 0x837af013accf5f5f063a02be51ffd429d5fce70f480ce26202d8f4ea2b58b93a =
1770941221 0.996 71.25 0x316f84fd1bdb84d5cec2fa4cb818315bbc65e963edcbf71ce8ddf305afa91af6 =
1770946273 0.997 5 0x6501ae1d669801f3693cd2c126e99707115360246369418926bfd79b9aea064c =
1770950449 0.997 5 0x3f05a38c3ba048dcf9d131a52a33085dd3bbf8b2b981b125ca290d25c2cdacb7 =
1770951709 0.997 35 0xf0ef7a4d77ee78587ff4a3ef3a44dcba537decdeed44c1162b5fc9345a1c569e =
1771065747 0.995 20 0x8840df088dcf62e6e08445b42106c1586b4b757bbcd162a541468b81050fe0ae =
1771076085 0.99475 20 0x35976aad27a904990ee7c8874b1aa2c92b9952bd74ed7bbfc6049566abed4bf5 =
1771085531 0.99555 20 0x58d78a9391d94478b11db810e4e1a6687671cbe6a4601964b15895eeebce9b26 =
1771086149 0.996 5.78 0xfdca460e6dc60665e077a69c96629e865f9e60e0e1363f8315dc678e1c827577 =
1771088985 0.9979244604 5.56 0xe052ff9c77605eb0eabe49a36ab37305a04b53a1d0f78a122c02099e5ef46df5 =
1771089711 0.998 20 0xe503b71ccc2d0cb5fe8a1e8f74defd9111cf1e553e19732ca431682cc234bfe5 =
1771103735 0.999 20 0xa786b8f1eb151e6f1568d0651a3b03c79663e53b4670a239e5193aab93cfc49b =
1771107441 0.999 1.9 0x99a92028821f1bf7b98622d36baeec0046bd8e726615c322544eddd297935264 =
1771107551 0.999 10 0x53307606703f7617d9722c32145b5034425b683d8234bfd570a7b6dd9e5084bb =
1771107551 0.999 15 0x7b6f3596370a621b2d3a31458acaa13efa048d898ad90f1534f94b78c83a6458 =
1771107551 0.999 30 0xb387477d03df4ddfe4a96470ac783ad1912368ec943806ca638a2bd2306fd522 =
1771108623 0.998 56.53 0x7cb90323240c6e4b6df92ab91bf20f87ecce42a5ea7d233ac232f328fbe1fdfa =
1771108685 0.998 5 0x97a6367331f26a69a93c2cb1446df9a51626f76a97f25f98a9a83b32cd4a1371 =
1771108685 0.998 29 0xed893fd3e4dae7afb7686ac42557b5df2eb226030c7a814e2289259ca809820c =
1771108861 0.998 5 0xa6c58e242925c62a6feafb665381184e76e7f2de23a87ab2f1788a455d6361f9 =
1771108881 0.998 5 0xab418d7d30fe6e7e978babc9923bfd9b3fcf802fab36088a0d9c723495a195f2 =
1771108903 0.998 5 0xe28c8ea0daeb5cfe25d0ee265c6c2aeff82272af3149b8e748c212a4d55337a5 =
1771108905 0.998 38.09 0x3e729d69665dab34324be658b31903948ae0f703f8cfb2a54f2a23d41e7bf85e =
1771108923 0.998 89.22 0x118db7dd66c5c46ca5bf6caa7de3a40631ebf9a0e8b28d0f7174ad5de3c8e604 =
1771108967 0.998 35 0x4ad5b9ed1778d12a8cd89755e6c12c569dd4a92decb24d463368fcfa20991fbe =
1771108969 0.998 15 0x306c401dd4d9322543866f3ff870b03675866288715c2c7c32e1203c3ac43065 =
1771109105 0.998 176 0xf1992c1011540282b2eec52a11c438d471fc17c60600d058aacfd484feb87ff1 =
1771110711 0.998 12.59 0x03b35f5486da904f4f16e65d5c64a1634cfb7391b25297b5bb4654c1fdc2f72a =
1771113111 0.998 39 0xd84306cdd5c98ff5a8545b22396cb7bb55e8e9ef32c1642bff6f677d82e9abfd =
1771113883 0.998 20 0x43c0fc575440bc16cc3cd5dabb0a0af094502d543d13b7c5a341f0ce04bec6e7 =
1771113897 0.998 16.21 0x70aa46f082c8b1062fec6c442324d3c02974a3b0f1849364741b575f1f05ae78 =
1771117403 0.997 22 0x6f10f167123026f5095360d68736901698df39b95224d29ef71391e71c959e0c =
1771119801 0.997 55 0xf5e7581db3aff4bb534dfed6bf6b7317b4b4cb3ea13c0c8c7076ad71d8e64c9d =
1771119807 0.997 45.73 0x573dac073cfe7588dfca3982160e537b50b93823fc86288b5dc8bce1ae7fc596 =
1771119901 0.997 5 0x8aa5ce544bca45c6aa87e883acf64f741828f5ccdbb94d4358ed572ebb495f77 =
1771119901 0.9967 20 0xffb5039712bcb9ed2a10cb2c427f5e71148654bde219fcd78f575e9e0b8fb50f =
1771119903 0.997 100 0x583650316ee01ae23d8ddf1661fb3895f22c561dfa58496dc4dc5c0a2f97741a =
1771119903 0.997 50 0x7921c772d15b180df1b28a8d5bab58afa454cbb055f36f4b895e61ab7af7e6cf =
1771119909 0.997 57 0xb358db3928339cb586ae6ee09a436b8514758258bed4d51cd278d77a9916645f =
1771119925 0.997 5 0x083c30f73651be7cac91788b0b1f23d3069b5e216d59a6db5e764ec72e8e4267 =
1771120137 0.996 5 0x6440597818c941335132cb74e50ad41a26c50b569ef70c61780743a9ce687ea6 =
1771120137 0.9955 20 0xb2f0030a108d7e9a8ef1c4e5015b6ad6796f3daa921e94f0b5fc04c6c95f9876 =
1771120137 0.996 5 0xef005c1742e14248a122c19cf419abce4eb45daf16c9fb052fe9249ba4da7237 =
1771120151 0.996 5 0x2f221ea91220a4290358ff7cca2d72390c2c9ba0a238364910762f3ba8c29f08 =
1771130469 0.997 10.94 0xc4bfb230be40fd8a2c2b806f3460d3f7c56145be3be898c800f08af263b09a69 =
1771130545 0.997 14 0xef674e66f895e587bf186dede16dd8780b1b150a330567628534a53d792b1c7a =
1771130547 0.997 5.97 0x4d6688dee67e196da39aecabf2c301e72885300c91c66182ba93b7a37ad2248e =
1771130547 0.997 17 0x90dc67ba8e3e69dd1022bdb42840b62c962b3a203c25b99d3946851a0d79eefd =
1771130565 0.996 17.79 0x9642327317e7c1bf210857351f727803aa13d2d0c93ae7c14ad9797277c28aaf =
1771130579 0.996 8.19 0xff20c125c293b8ced7bfbb47059a10767fbe0366dabde638d5c9ab2bfaac04b6 =
1771135849 0.996 20 0xcb2e3dff0f7871d74f636ba6c269cb986110db058e56bc656fc0cfb4b77dfe1d =
1771135851 0.9969609747 513 0x94efb7ea27c6af84a556528492a2660f8459f05a72557e578024c136dc7215a4 =
1771135851 0.996 30 0xc42df65e702227b6b695d4d461528188f539b3c4bf2e63d12f9532ec7cbf4e89 =
1771135857 0.997 71.25 0x6532aac1827bf8b50761f097105beea685f49a1afc475cc3db3e9aa12e27b528 =
1771135865 0.997 5.43 0x2a08cb904382d36d496b1c351a1ad8ef32d91bce387ce3de2f7dff37d9217038 =
1771136045 0.996 20 0x4816529ec234a50867f1580b70b581a78fa42785d2a1390d524aaeead385dcf7 =
1771136045 0.996781 130 0x5dfbc564897b87a9d0aa9efad481386cf197f1bf07ff0124c388bda846b10593 =
1771136053 0.997 71.25 0xbc0a9dd2856c3c6c809486fa268ff61224dab06e5b91709d4ceca9439fd26005 =
1771136201 0.997 5 0xc67d3c16945f4621065d811a1a194cd2d5bd43241c3db91866fce7a333e471c3 =
1771136203 0.997 5 0x7be631ca945222eb12a65a7cb0bee165961d90c497888c7f93f0a188a9bafc6e =
1771136741 0.996 5 0x5b08d7876585b879dd64599cc02297d9798b93e2fc3afb45f648259f10039bc3 =
1771136907 0.9966666667 15 0xa15966e6f2a05592cb87988e85fb55e6f5354c0d472666ca904425241ae26d16 =
1771137995 0.997 35 0x9f4af9d1ef18b2b3264aa0ec3b812c8797515a7d2be1da131517c36d982eb60c =
1771137995 0.997 132 0xaf2253ed5acc8fa623b309cfd3b1f689dba7fd036907d69756a69d98e2e34719 =
1771137995 0.997 1.28 0xff5118ec67c4c2a125fc0ee8fda18dbe174b3b10fd58b201460d06750fa1c764 =
1771138003 0.977 6.36 0xe90c71cc9683e88ff6771918f9afd49c659b5c54c41f6f1deffc6157aa7e3c1f =
1771138387 0.996 10 0xdaba8b3c8d2c4baf3502389bfe933086f67d4777bb188d4d2eb816e44fb2f727 =
1771138387 0.996 10 0xeb9673f1a0ea657246bd3d43dbe834df92dd82c310f3ddfdf4481588db8368e3 =
1771148817 0.993 116.78 0x5b35fadf3b9f36d8625cdda48acebad3e697810d1a72f39d9c79ad4a3d486dcb =
1771153219 0.996 20 0x368f64b5bffd66bccf601a57da02578307a757c0411befc5ffd6edfe4f89a1f1 =
1771153227 0.996 31 0xa92efc5cad018ca91605333bb7d6b056cfeb6b7df26eb5d2f86a6e1ed68f1a4a =
1771155107 0.996 10 0x6977dd49f231bb849b79a5d140ac3b25b72f865b001935ff3057e132ab6d2059 =
1771155109 0.996 20.1 0x739c22938d825cda2b1fceff5a5d1cd7b048b63c99a5de9f3b19f57fe9b80a26 =
1771155109 0.996 10 0x9e41570222e947a42f8cced8db34d16b339a9a26d6784952882f1e0f0284a80c =
1771157435 0.996 100 0xa3349d1cb3823c0d57ebafa78cd31b72881b2b62293f255e5e926fda885c6a77 =
1771157837 0.996 12.5 0x54fe0fa0797b547226cf114a1c4f5b65514d80f89964788685310b6a3dd32448 =
1771160815 0.998 711 0x6a5023390d9bec81e4807bf7d83bf96332971c28062e611644fc13b48650bb54 =
1771160817 0.998 15 0x349aa614c6d59696dd28ec0b982dbf1bca8cfa94580bfa5ece8e65d6b1d53ba9 =
1771160825 0.998 57 0x740b4731f7a765085515c864e9a06c4b2dfcd762abbea1d13df64b954c29408e =
1771161779 0.998 15 0xe1ab5a0b9c6c1b32d08582b71d0e2887b1b547e7395a64f0073b60622dfadf9b =
1771161937 0.997 15.51 0x40c62491dae2ad5e3bb328b292a5d03eba84122ee7330a69e1e6b1fe6e759cdd =
1771161939 0.997 14.49 0xee4a8e9649d1faabdc0c4a6d684d6734a88166489c4410f9220631f852a78cf0 =
1771165497 0.996 40 0x0dc1fa08bc03ac365cb769112fb70d222c7d4526c6d42f4bddb5b77c42421a58 =
1771165761 0.996 20 0x33c823485b36a083045cd5d5a60f90c9ad49b2753a571f6e4c1fa07555f6d1db =
1771165763 0.996 13.7 0xe7ba3975086944dab11f5d8e9377e285731c4fb015d33fe26ffb761f875e58e0 =
1771165777 0.996 20 0xdd937ff2f18d9663369852e9645948cd9231eef67c7208f049b7e33630ed8b84 =
1771165777 0.996 26 0xee605d79b104abff065a5ec2ff0cc71f0903deaae8fd420807062a867cb3840b =
1771165781 0.996 14 0x5d81635df9514c64fed2ff59a2277436472037c1d498c4d868f5144785b27c0e =
1771166201 0.997 20 0xfb7181c61546466afcd01ebe7164379c3d46fbe1ff19fc9dbe299aa11fb61dfd =
1771166483 0.996 7.5 0xf4fac2ddfc76b853a779f53c871f47e59b134d74b9024d9f5b359439fb208c08 =
1771166865 0.995 7.18 0xe3ebbe3b49abb1e82c65f4f29427b0a35d3f54cb77a182f34ca92ddcad0c47e6 =
1771167003 0.995 20 0x28d4aceb465daac9408a4eddf7437ce50bc7093b57733ea8c331cd85f97112da =
1771167003 0.995 97.82 0xcc2580860dfeaeff3bf06019212acaf56275d84b784de9b9b02fd5b46fbff515 =
1771167003 0.996 15 0xe1bfb4c9bd0036cc019e88702a4a7a66f83ad366822785333f988a1894a44295 =
1771167017 0.994 5 0x5f3f922ccbc3b09cf00a843becc55a871b4522bbde5adf522674d1461ba1a7bb =
1771167017 0.994 117 0xe4146cd9507fb370927af77c5909fcdeee6137909409290b8620bf200cf06f2f =
1771167025 0.995 40 0xbee1bc06ed459208a4291e420e37626c0dc099591e3fa4ddad5f54fe170bb331 =
1771167025 0.995 30 0xf2d704accbd80f94c754370190c35061615793b8b02025a805a823fce6d60630 =
1771167025 0.995 415 0xfa33689468de693ea980000e43323534cf18e6d6a0d3a5999e2da6798071a948 =
1771167675 0.996 8.47 0x5ef4d8e19aa35ae0faf92338c60759dd35a72e2fea690d708fb7c2dc0c2118ab =
1771167677 0.996 20 0x4541b179baf26757c7d895757fffebf217ec8d2831c708e6d9e3b7ace955f577 =
1771167677 0.996 56.53 0xf517becdfe0dbab3a1c9e57d8d955e615810ed8e335d0c03b5b1fb25824b2135 =
1771169541 0.998 50.87 0x293e5acfafa47f3185fd67ecb5ffe474ea0291dfb68e726ada7ed8ec66dc55aa =
1771170011 0.997 54.49 0x1ac8223b21a80fbf8dea6dd70caa7c0a94a66a37dd19a572ae444777a2de5f81 =
1771170343 0.998 16.8535 0x9da6712c7b182fbd8e728fd2cd6ff2fb55ba89d4fb6f6ceb1ed7fa37392ebfc4 =
1771170353 0.998 30 0xc6a77c9eb9ab9289f36a3c88b396894484e6ff257dc9f9a0db0bd040b1090a05 =
1771170353 0.998 441 0xd6aeedcd12633fde6b226816ef835178845c8dfe94e3342a363063dacf10e8ed =
1771170719 0.998 75 0x16d93926a6b6ebea41e655e365f4a8275b2874fe1cd9696bbfb23823b976b397 =
1771170721 0.998 5 0x9cdc6896c3b7994cc991a454da1590892f381d4db44db2f4dad2a8e4a4a93212 =
1771170755 0.998 14 0x0ac97852f0a40fb6b422faabe464abf4b889746117d660bc703e7d6d49208cdf =
1771170813 0.998 32 0x5eae716e35b5fafad1e5dbf4dc559ec803d52b4810e0e04c09cc6c614471f632 =
1771170835 0.997 5 0xd3266c5767a7ba41d90344a442f5f1728fa80a226ae6aec7e1607f623e13fbab =
1771170931 0.997 10 0xb33bd64ed2ae6eb92b990d9b7567c71a463dd7691cd5093e939a41f063e77325 =
1771170993 0.996 10 0xdee033dd4ae5d7a575cd06e1dbe7c373511efdf814648cf9b1c49c1241a7e93c =
1771171053 0.996 5 0x3cccd9357f541ca4127d9b122151092e78e5f1d51eae5900204b2722e4c6247c =
1771171085 0.996 5.4 0x6aca2b8f325b77c1dbf0881169022dd0637b406302abf67dda3602f1c44101a1 =
1771171095 0.996 41 0x9dba720bcc952ab393aff49907487c79f75bdd7636200f1137c05e4fb4ce0ce2 =
1771171097 0.996 12.27 0x86e7f07636808b039cb04127aa002ff6e2aed45b07bd8391fc02e4e27f54a7ba =
1771171235 0.996 2.29 0xfe73942ad1085434b061bbbe14bde2b096b50335b8a3f25ed435fa5edf077eda =
1771171249 0.996 40 0xa5ff18a82df7877dceab61c69ef612be150097a76a990cec3d46249569b40b9c =
1771171339 0.996 5 0x6c152799bac5d0370007fdb9250882780bb0e932efe1bb2678d74e9aa6ca1d28 =
1771171339 0.9969864901 151 0x9af1440de4599a960d962343ad8ea2ddd37c06c01a5c38116752498ce3530bec =
1771171341 0.997 30 0xfd6700b2ff21a15a9e63758eda50be119adda44dfbd0d264c3bb3ea5c9f5de14 =
1771171357 0.997 25 0xe887b370ecb9bc6d7afa67222dd3bfb25b2293d4970a5a8dfc008cc3eeeb2143 =
1771171367 0.997 7 0xb2500cb0dd343b491a1e6718eb11ce4ee01c4accf67370c2c4d7ab1c931a4aee =
1771171533 0.997 37 0x240eff63a58a58641c350ec3fd12511aab97f6ee55707892a53a02858f75fe9a =
1771171563 0.997 21 0xcbf59b408b28cfa1be1cb7ddea9dc61fa7eede77dd1d5c531fe84b1f0b9d96a6 =
1771171633 0.997 5 0xb08266a92828da1d69390c5113fd39b0f06760ab8e2556f9cdd9be06c1f14d4c =
1771171647 0.996 70 0x81a07f973cf4912c0d01574df0dafeb5adb2589db34308a71ab980f82c8e4201 =
1771171647 0.997 19 0xbb31d3b3c7ece375d99ce5e1a576a9da1f0d7f7e3bb13e653903fa1a1bfdfcf4 =
1771171663 0.996 7 0x1734fa7277b303b537b577c45c1cea88f3a19583c03b56e171fb4500a327b82e =
1771171747 0.996 30 0x2488c185c91f4135614c2c4162818a34cf90bc690ee505185735f02876a8fffb =
1771171749 0.997 20 0xf5329aeabec05909b2d396ae467d3ba72134059d59c2107029a74b7acb7a7653 =
1771171763 0.997 3 0xcfed0c1c6a98dec8e6de69356d421eecc1d7024e6d8722e12b3c519dc000cc2b =
1771171859 0.997 25 0x6193f7dfb31af3bdd14e4bf789eaea2d6c34e37ef3976f2fb0fafa30ac512ac2 =
1771171879 0.997 25 0x446627d96eed15096e5c907bffbb1a1198d93083252edeae598e882534ce892e =
1771171927 0.998 15 0x2199d5fe635fbe6cde568d6071c2ac508e01f63c036d8d15ac55a31510ed3923 =
1771171927 0.998 15 0xed4087a3cc0d74122a72d910ea2c67f69f028856530c6daf3b3c5b680fdbae6d =
1771171979 0.998 30 0x34922e6cc8e0cc07899325bd015ce57a43a7f603743129197aeea2b4e910fb83 =
1771171979 0.998 202 0x68dab30c4590aa18e06b2a26f3f91dc4025106c4861be0c85ed551f4cfc4839b =
1771171979 0.998 15 0xc4515c5d77c1bc644190b2c1218fde27a9a0ba2b44af754997b68e2659e004b2 =
1771172049 0.997 12 0xf500cfb3edddfb1b511a69e628ea6a27b296648cc61dc514b1f38269159d7b3d =
1771172113 0.997 13 0xb55f5da29f30770e8c39c575cb4dff3e2344f24941a65cf3da43257fde739be1 =
1771172225 0.997 10 0x03711a1437f3a6884ef2b86936b2170cedd60da03e21b0f9d6c85ded863a0162 =
1771172241 0.997 6.14 0xb92685cdee838f18e0d6eb224bd49563d2306bff021eb2792d1b797f322fa44a =
1771172247 0.997 11 0x02a5e67e67a14680efc3073eee7ca01f00079cee23394a3e93df670547031efe =
1771172247 0.997 18 0xe01bcb7b299409ab226fcae92582fe6c0b98e16063b5bcdf82167b75dc977b6b =
1771172251 0.997 5 0x72286e76140166f1a8d43d2967ea6bc016c08cf9e8697054b2c69361ce43c469 =
1771172251 0.997 7 0x9707d15ae8bedaf6b7bff101f72fe4262abb22104b8d74917673fa5478f2e15b =
1771172259 0.997 30 0xcfa3f2b7c6309489ad9a285a02d39bf12f0ec429a498af312c0c489c6871e5bf =
1771172291 0.997 37 0x453c17cb15ef3e8bf73b3c6499e5df27e85d852e25123b9e2dc215417170a39b =
1771172295 0.997 26 0x2196ba7b865d0836e9cf9fc1eb342f225fecb32f71b0b30d877f0c8d38f44815 =
1771172351 0.997 37 0x9cbe45ab3f92c8cb88fc8d66740c6261f32095837d29a899e1547fc4ae53319f =
1771172385 0.998 12.04 0x10bfb1a0d018573a2a3cd38ea558ca949205cce3cdbe7b5a39392d38ce48f46a =
1771172477 0.998 37 0x582d53aece647a9ad6ef705578a92b8ae5264f93f7e1fed606a803bcba5128e4 =
1771172559 0.998 51 0xb7774e6f7d6282dcd255fc0c9be82bdbbc3362a70b2cb8becf92d7f2321a3eff =
1771172637 0.998 5.99 0xbabfc78f7b4fe58ef7b4bf06638379423fcb09ff8ad593503ca458bef66e3fe9 =
1771172641 0.998 10 0x8f8342520b9c4d27e80bab140907482a9bae9368cd036e7f8df27a079529a199 =
1771172853 0.998 77 0xd09f0a404f9e318158fce9318306e37a5c368c61aec6d6531b3b0b5261053f26 =
1771173251 0.998 25 0x0d5d75a9f7c74c0b8962515a263bb00e02f41a0a1e930d7575663a539506119b =
1771173253 0.998 10 0x9159724bd74fec88becabd1a484fa9a5620ece0532acfec72e5a9f8905320b92 =
1771173255 0.998 9 0x7639a216b6a9fdb0c9a2cb78af97eecacd759cb1ab679dc5e30540be738b2416 =
1771173359 0.998 51 0x0f8dc71c4dbe2e8d292259ed7746f32639f1ee9c782f1b0ca213fee41ea2815f =
1771173359 0.998 10 0x556cdd85e61d4bdbea7d2d0c7e8f09e95951dc324374a20e1fa85ec8f82afa9f =
1771173359 0.998 30 0xb1ab63af19ef5f3e84091690dabda5e0fb0a2089c40015fd38154d67b3e9bc47 =
1771173383 0.998 7 0xa5ee624eec127e108a9562181433b195c2503e4e3244a6638783a36dbe969eb1 =
1771173525 0.998 500.93 0xae4f8b0a18ba10b35910ca23e6466efd5ad3dad86e07412253912bf78130836e =
1771174575 0.999 6.13 0xad4aec50d3fe47472b2a76cdab1c63104c9c6232accf3928b6779c28fc372478 =
@1347944 Yes
1770483059 0.001 6.12 0x859fd8535987731000e6a643932ca436740ddda9705940263b47bcf1ea24ecb4 =
1770483061 0.001 49 0x095fa880573d0c2aa258035cee78901946c8b7c8053cae6c93dcb49e24f592d2 =
1770483063 0.001 27.86 0xfc73832a72235a8b99494e4aa40d9defb1896622d4de3ca6f040c513211df4d0 =
1770849489 0.001 100 0xd2a7327331cb90bf24d9e8e6918fc5f4477a1f6e22be81e1295b21ab7372176c =
1770855867 0.001 29.14 0xfbb3afcb42366c61d1fceb4560b1eb1446cc30e9d96f309847d5a28bdd139463 =
1770855879 0.01 37.72 0xed547a206b2a3243dfdecd62bd5a2b232724acf2b4b8e0a9c2c6fd5e0182d4e8 =
1770855911 0.01 6.46 0xb07310e48ea73eeb97f5b44b1d496241b6a6bb1562f1ecaf1cf15790b276829e =
1770871757 0.018 61.111111 0x4c0736e4cf69a99ae17982ffb19455663b701bf7fd6c034a42ef721e1a450951 =
1770898647 0.003 2.41 0x14f50a0764f3c797cc7f9cbc6e73e1c267eee44caab3c949c4f6de2abd4ebd5a =
1770948167 0.003 5 0x9ab67850a889dd478d99f949a9277d1ad3e63c180343154c35b2a1403a9350db =
1771107825 0.001 4.08 0x00d0238039c37904e907b8ab4784668ea26bb22253e0b7efd89b715457a1c7d3 =
1771109127 0.004 94.74 0x975b78bfdd7e0b4c8f5d5346267f0da3927aff94f41561a9b03e48c834eb38c6 =
1771123543 0.004 6 0xf39481291ca8fdca42059d814e088768f6e57de7cc9b1f77e77d2474362ec273 =
1771167997 0.002 5 0xfc4113dfda9422a8e856a66c52d838db053dad06d67e0332d9efa010331aba5c =
1771171301 0.002 5.4 0x8cbe079dcd400e47b664d7d85fc57b8716025b4bbe60ec4b784ed8e541c893eb =
1771171573 0.002 3.52 0x51c2fcf176dcf9214403015c650bd0dc9a7a13da6c040c63a5f32344691f922c =
1771171599 0.002 2.29 0x7c4df3565eec61fa48efae2b3a3230d4c9758c5b01ae9c5bf963d1bc9ea38937 =
1771172565 0.001 11.2 0x250cc67ece2c88ea5cfebba9a67d68c8ce3c77dca273c51578b41ff2b25ec426 =
1771172821 0.001 11.83 0xea25cf9293b3e82c712ebc68f9a40b5c04de274feb1e0000fae90a1109144367 =
1771173371 0.001 1748.95 0xc30dcc30ef03afa7649ae62a5ffa170c2b9edf14cd97c44ed499379d91fe5e7b =
1771178529 0.001 1000 0x0d997c051022a6bdc1421a06d4e39d16b31de432cb254c92da2011509214674d =
@1347944 No
1770426171 0.99 10 0x9d6f0e46eaad03b0e8e27f444b58973327b997ff09fc288c8b3c67e8213a6538 =
1770426181 0.99 18.0303 0xce41bcfb94b6653ecb3c1a15b78d16f30431dd7c98c8a06257c9fa82c42203ee =
1770458431 0.99 10 0xbf4489645a76b79321a91fb4354a1ad647cf7d7c30f91860940c4647e2a476e8 =
1770462375 0.989 7.04 0x14295ed540d0947f9c0d21ea468e15c73ec366b0b3ab2fde0d90ed8521c4abb7 =
1770462393 0.989 5.23 0x0a1b2001de9a8aae251a44418ab1a4f1e248e1eeaa85165c3153b3578f4732a8 =
1770464351 0.989 28 0x9286489632461b0c50b71deb89ddd7f6a4bc0947fa6063cd68feabc245b0ccfc =
1770464367 0.989 28 0xf25473d335828c31ce86f2c7c7b049a648c0cc948ffd832c9bd2fcb671d83c0d =
1770466975 0.99 8.0909 0xe61e491c1314f5d66413a8c5c4cdd808f03d1b4f68f05de183654d9e452800c1 =
1770473065 0.9904957895 57 0x463b4e7e55ff8a7e9fa2f6b81b0fc9c0882f215955b3c203a3d7a998949bfb97 =
1770475253 0.999 13.88 0x1c88b8544b2b709c1d646ee681b2b74cc8863fdff12e29fc8818e25aec1bac5d =
1770871293 0.99 5.8888 0x97d0181b85a3805a902fe8523e631fd6fec1e41d07671d7c516681b5423aaf61 =
1770871755 0.992763 30 0x058014ca0844937d1d4e73a27856cb8638e9d55d219da227120467f5f75ed00a =
1770905533 0.997 56.49 0x0a5521d3bdc666480c156dc66630fda66f22f351e935d72cbe22b10bf416de05 =
1770935455 0.997 5 0x3b047bfd5a35b9dab31d7cf2b7a63b285459bb647fbf74aee27db27ecefacdbf =
1770941197 0.997 30 0xc96ec5cea34590a08ad894bb884faf57aa394f69f4237b27e2aa6dfc03560358 =
1770941205 0.997 71.25 0x5cf29cff224e7b45b3f44e8d69deb8f9d4184dad55f348b136a45df518f9853b =
1770941223 0.997 71.25 0x340cbea9a0ef8fc94bbff4bdf9d4cbca2f3ab1b17145ab813ea53538c1f02f86 =
1770946273 0.997 5 0xe3e6d1d4d5821cdfa3a1ee45436f386cb2d15cb3bf14a0562067d40b3fc231f2 =
1770950449 0.997 5 0x8d05cfbcc68d9640d12a808dc3225d53b3518ab03867cb22df91cbc8b2192124 =
1770951709 0.997 35 0x9b6a4f5aac1b92ab5a7cb1d77eb9ec933e9df81d00a42225ea5ba55ac7f71026 =
1771062147 0.999 5.91 0xf854f4ef445ece5eee31b7a397de524e71d6413af34887c7476c0b307b348f56 =
1771064729 0.999 17.61 0x4f1aedb72e36572688080c69383bfd4bc901a61b25e21a0c89053fda260d4529 =
1771065747 0.999 20 0x8e698c2de07e14116c90fe89a90f6d7d86422f794837f3408e209e2436020d9b =
1771076085 0.999 20 0x06e1e29bfed73518662554180d9f733c957d67b1033f73168ce6235c4cf80d0d =
1771085531 0.999 20 0xc504cdd53aba56e3d3ec77bc396936b739d03252fa7175c846e495c01222f519 =
1771086149 0.999 5.78 0xbcf75deffb02acb609ab9a4473aacc92681c60297af1afd70029ef5c531da7a4 =
1771088985 0.999 5.56 0x72749b6e998708ffd1f9b706ef21caa346d97e811126c16899506ec46bfe0712 =
1771089711 0.999 20 0xde3bdadefd074d055e2fc3a5bed632711d2ca12b8133add1f793e4719064c652 =
1771103733 0.999 20 0xe5eb3ce40d0c9ee167f3ae89bd4d8f54c2ae72944b477bd5b2d7f4eebb91e8b1 =
1771107441 0.999 1.9 0xbad4881df97b2d7e1cdec4f3030cb583ff0e851a67d54dc2a1930a0dff498419 =
1771107551 0.999 30 0xc84b1fdfd4b172745c1a96fe7395398cdf714f27d626a97155a2278e78d08098 =
1771107551 0.999 10 0xffe6875ecaefec456c6927e60dc2421e683b7aa959eaf9c70b0515c5c9871cfd =
1771107553 0.999 15 0x332c0e8a709bf3abdf2ea7413c9d7744afe97f2b80b5bc0db793fad6be794e9b =
1771108621 0.997 56.53 0xd1a31e80489df1bd3a0de95e2a61439d6f436d4e6ea75a1e759250d8ba6cb749 =
1771108685 0.997 5 0x1726ebe87c1f0fbfb1b980f43c1b5fad8bee1bea36c8b8f1a9eb425b17855877 =
1771108685 0.997 29 0x3dab8a7d9a4ba704e6f94af59cba97878a079ecce37b0655dc314730de8aec0e =
1771108861 0.996 5 0xf322f213b7070ea68f35432f00be3840dee5fbd079a9956d73195e89583b6208 =
1771108881 0.996 5 0x7d510aa10405d9f4e8d5dfa08310573f6d7c94a1ce6583507cdcb3272ece6649 =
1771108881 0.996 5 0xb0da33cdd29ec419d163bfe49fa4af56a9a1e838d4c307901468655205902b51 =
1771108903 0.996 5 0x7da32efbc0bcf608be6a270fb7ff18cef10498be803056096005aecc03b63834 =
1771108905 0.996 38.09 0x3e0c99e3a85d3d818742b8927fb4de275922b804020f6cf63fcd2d03117c5da8 =
1771108921 0.996 10 0x2ae53821de43e3260b45bd09d00553f0cd8a5d65d6df5f3519846fc5453068bb =
1771108923 0.996 89.22 0x8da55027b099b9e33171d0e5cebfe2e3a94b929968d8329443fefec03db714cc =
1771108967 0.996 35 0x9ba8ecda289da5664d8a709635a9d91a7587d4feec3e7cb89f63e1f286172284 =
1771108971 0.996 15 0x02c29f00305d9aa4cb5f4c54a1dea1f1273864792c4f33e9df06be5d434bce4e =
1771109105 0.996 176 0x786ff58ed4989e3b7381b75b6714f85ea3785d2957a2fa52290c59d09ecc383c =
1771110711 0.996 12.59 0xb1fad12d722bd5637c108ea5476971991ab32f3f899599604e37f31ba712632e =
1771113111 0.996 39 0x92606c96e789b29f3a3da555de497ee319650db07bc6d423828f750698033d51 =
1771113883 0.996 20 0x5eadd962cad37a6093a7e456495258d1388605e4048fbf366f8bf2ac72f5b607 =
1771113895 0.996 16.21 0xd8363029920f03ac8ec0f38de619111bd00fa339282cf402bdb02ac1d796ce2a =
1771117403 0.996 22 0x76eb7466aee5e44cadeae87dd34993ef64346eb646ad5cd0219b9047b31d51cf =
1771119801 0.996 55 0xad835282298cb6ee5ea6218131fa7c9dbd5f8048e6b7162496b82b889afdac21 =
1771119807 0.996 45.73 0x572a7f5868a35fd0ef03e031567ca3780fe40c74626bafa56ce09a1f7b73c502 =
1771119901 0.996 20 0x1499ba106e8ba4592b36b7c156319d95ef28f42ad8b201a63d79eae9badce741 =
1771119903 0.996 100 0x5d066a6485092e0fa976bae7a88eff8a7b980fe66a56872956fa741accc1bc5a =
1771119903 0.996 5 0x88e1d2e052b4761c8f330cda7439a95ee23a855af80497b6b33f054bcf0948df =
1771119903 0.996 50 0x999e6bb8a2c1e53ff06ac139e8df49d9472775e9f66b2ffbda1f4eb9d511e402 =
1771119905 0.996 28 0xc7c80098245a35442e702dfb25b1a669e8b2a3a383ed4625b1e93a53c16c0a49 =
1771119909 0.996 57 0x5938a252f64f6ee40a9d95cf0746b7732ea375f7301d908185578a1208425249 =
1771119925 0.996 5 0xcdb63c15f5dace67776d43bdab315b1326ffd600b24a7eca18b1c1fa0446ccb4 =
1771120137 0.996 5 0x7d1548652e261cfa519f5537b46dbc9ebc9d8b715c40422bada2fb77eec49f16 =
1771120137 0.996 20 0x9b6aae6085f3a68f464bc4180a34b42824193244af7b1e373a49b61f9a47a02b =
1771120137 0.996 5 0xce5bfc00a58b5bac5c67c6d07a8292284e21f9014268ef547c0193575af366f2 =
1771120151 0.996 5 0x87ba9bc648691424f860c988bf623a98ff3f65bc7763ca4a14d52ab4c1b36775 =
1771130469 0.996 10.94 0xd84b0ef4672484ffdb9caa9f4587774e41d358e0ab25176329fbc79f7b6d8f2f =
1771130527 0.996 21.22 0xc9865711192169c0b00ec61ff1d32d08b7e655db26541cea0c9d37116e00384f =
1771130545 0.996 16 0x70d9b5b6ba665cd6081d47b7c59fe4e3793b5671bfe44ec9cf932bee26edac66 =
1771130547 0.996 17 0x23a02764e85eb6435578ef80dd1ebae0a90bff211c893f54f5261e2e5527ec39 =
1771130547 0.996 5.97 0xcaf6f3cf9ec8d01c28235758faae63621fdc888ac20b0050764ce5dd8897c04e =
1771130555 0.996 16 0xd7b2649f84bf64206d0719f42d539e1f98bd9ec107582929e19513c5b05a3173 =
1771130559 0.996 16 0xb36a0396f6f2da1638df1a2d764304849f6f23b5d3b597aaad22bf13f61fe92a =
1771130563 0.996 17.79 0xa76e98b18183c2755f63f834063e5a32cacfca435b17121751cb1bcb427affa0 =
1771130581 0.996 8.19 0x9e7f0ccf8c6f6c0ae6ec640ab881e00115446bbb39577be6264514febbf6fa71 =
1771135849 0.996 30 0x9be5590e07a9ce0212942f64c7143e41b44a400ca79be8c6049c01a3ae59945f =
1771135851 0.996 20 0xb02ebb76227707e28bd2931fa721933b3319e73fe4b49c254a517220d06edb1d =
1771135851 0.996 495 0xfcaa583393de0561ec37913f5412287bfaff41400591a28f95e840b0d737570e =
1771135857 0.996 71.25 0x5ca21682bb55d087ce5e835d7d8d4078c08a62b3e47d436d14af75e150238387 =
1771135865 0.996 5.43 0xdefc8ce6ed5bcdcbfaa11109cfc5aede725d9ad2670ad3514c54915e0577ae92 =
1771136045 0.996 20 0xed62e95e49b92c11c847cfa4348354f2042bedc821388811cc53ea27b1d555ae =
1771136047 0.996 131 0x03c55b34532eb70182e95a54c3a894f86129d957b714cfc5bd35134fe9fa55ce =
1771136047 0.996 131 0x1d54d347d858aa7d53612ef183b73cd99d29363cbee9e81fc99aeef22b4bc1a8 =
1771136053 0.996 71.25 0xce2576fb6e1f65cb1d3ce8885ca0951aeaef1a4676bfd38e308439bbe36fbb1a =
1771136201 0.996 5 0x158a56f9f3fee49da8f345f87f30519657bdf49653ef1e33ecfd19b14daf466c =
1771136201 0.996 5 0x5f85e66aa15c95193995027ff221126633fb3aef1dcb52e14d4bf449afcaf8d8 =
1771136741 0.996 5 0x5e992be6ca1a67433838451fb22177d915926e9344aab583299aa50e9806ece8 =
1771136907 0.996 15 0x1c76d89b0a2bf9a8a87afff9b2a970bec56365d91818c6bed2a77a604c346bb5 =
1771137995 0.996 1.28 0x02790c61d22628feebbf3671ba6f0a4647264a0c4570e0aa6fa21069ffd14cf7 =
1771137995 0.996 35 0x7d534d83f68b33e2ad8b5abda4903ce0b4a680ea2db532baa3661a5aeed7284c =
1771137995 0.996 132 0x9bd9a2a78920be54ed2a29ddd99c7dc72b3d16dd196e852934342472c187125a =
1771138003 0.996 6.36 0xde8f526fd4b0e8a1a4b158d71db0bee22f13740d7b15d481128c65568d5aac04 =
1771138387 0.996 10 0x7bed72fba8a14c42b20a66d1fff7f388aeb8bc54e9c024c030c2277dfbc88f61 =
1771138387 0.996 10 0x9634ff17e0063425606bf88e70314f5b8fe56b569e748a68ea8672b9ced7f61e =
1771148817 0.998 1053 0x4b4de73b397310d969777b83745a3f121ae741c0bd5b6da11325b6176efbe8d9 =
1771153221 0.998 20 0xfa7484f5e7b5509632cbf08d18b89d0d03f9ab45bde0fd47204e899e393315cb =
1771153227 0.998 31 0xa2e84c169567d5e8c0a40ee8367a4de7041213c0866cc252dc38aa6b3e9e52df =
1771155107 0.998 10 0xf80c53cfc697d596c9033885151992b05f1b9d77a901f6bbf06f1ca520829211 =
1771155109 0.998 10 0x36b78d9d40782afdda759a4a86366ee0361742428dbd6a86566dfc701ab1a0c5 =
1771155109 0.998 20.1 0x4270dca6f4630d7bac75802a66523c0d6b157aa22e07b2469d862bec4dbbc8c3 =
1771157435 0.998 455 0x93bdc99093f690b96ff0274d8f2ebfd6a01864b66fce1849cddac6812ee8c88f =
1771157839 0.998 12.5 0xf4c42010b6af938ad8a4b4a982bc7811b67941963cbc161e17d2118e5a1d14fc =
1771160817 0.998 299 0x07ec3dae07163267e2a247e46158e3d33bb13e8dd73575e6ee972f7fbab109e8 =
1771160817 0.998 15 0x9f5f4e037fb6f98b84808b1b696264829f336c6e5e5692886ead8a3caa5ece5e =
1771160825 0.998 57 0x813e04cbbdb973ef674a5991cfd8929a10741488ef11ead8a7c3b799e6c7f01f =
1771161779 0.998 15 0x52c068d795069b855ff7a0a50b5fab6275d61d01a787030ee2e55f2df84e9460 =
1771161937 0.998 15.51 0x05be02c043a96af59e10de641e9b00981832904bd0771bc74cc059a0d9b55551 =
1771161937 0.998 14.49 0x650fa337cd098d77f2269224b86f828bb36e3ba87ce79fec869dd415ca05f3df =
1771165497 0.998 40 0x3f45c61b4e26d34ef3672705eb847d0fc03b4a6366ef50337f63e9e9aeaab6e5 =
1771165761 0.998 20 0x79713dfb11f3495dabfe580e0de9d2f4cc11ec944c9b4c8cadf9c9768ae522b8 =
1771165763 0.998 13.7 0x713f5d58878ad671b77a129a41c909a119beb758fdd6eec4046b845b6e16251c =
1771165777 0.998 20 0x5d2bb36742362e32743771cd35b90c9d31ed933fa617d1113684c64b177c2413 =
1771165777 0.998 26 0xd9bc750614d1ef22c90e232f5eb2bb9979d41ead9bada9ce22e1457759a47cab =
1771165781 0.998 14 0x01b0e1d1d1de9d71e5ea9db1e6d2dca1437e37167c815cd61d25d8835124fadc =
1771166201 0.998 20 0x91c29e788f0b5a89b4c6261d2f85dbcf90de0c57f6e3317ddcc856d9ec0da3f7 =
1771166483 0.998 7.5 0x93a10a1c80bed7e88d0432000b16307233673bdfe03eb0c89e98c078e6e2a7ee =
1771166867 0.998 7.18 0x39066594b7f384ce1587963d5bd6db5e174cd21dc9109ecb950198b0631c8429 =
1771167003 0.998 227 0x3b2f896e7cf9746c233a70378f6fc225f4fb3178b3b5c4f4a8986a3c87a01f3e =
1771167003 0.998 15 0x99f7d15a6d53a6c7ed4f03a7f49ff8a448981eea3b932a3121bb29050cd010a0 =
1771167003 0.998 20 0xb0e987f1f64136b1c318f79c261bf8f744d15f6efd345ed769a17b5b7142ade2 =
1771167025 0.998 30 0x6e9ec5b44b52b9e7cd4d24836b3d1f302bacbab0729ef7ef243ca69c9ae70b89 =
1771167025 0.998 40 0x9130dfcfddd4f5f6f366e58444cbfc77520cd782f5380ca9ef447989a7c9689b =
1771167331 0.998 403 0x65c6b84d14c1ecea0e71b6d53fa74d4f903cd8b2cbe5a87c7ec762fbe394406e =
1771167675 0.998 8.47 0x8731654775d6cb5462afd2b9b868f38283a0e5f40df090b5425a8c614795a045 =
1771167677 0.998 280 0xa64682af9b0542e02ead7521a2dc868a015430abdf44e74d34386343a8f932e0 =
1771167677 0.998 20 0xcfe92f90f8690fccf18af7c25988b5da7feb0588c2edbc40b958cf30a5e0e35c =
1771169541 0.998 50.87 0x409d17efa48171d81dfa08f5bef0b4a56541eec93c491eba6fe1be8ac1a004f8 =
1771170013 0.998 54.49 0xdf8519e125d1911fa3de2a9c87f8d7a4701c5dd7238cace04c004e22b714cd64 =
1771170343 0.998 16.8535 0xf95225c35f0513e807beac6496bb6ee299ebbe8d807b4caacec16558ff91dc01 =
1771170353 0.998 218 0x4a648edcd35412926ee89274d1b3bb03cf4bd2f10a393cf11cbe7f055c4497bd =
1771170353 0.998 30 0x76894428a9a6dac18befc50ab06892cc3dfd3c39d16b5ae4885cf9a4f9ca6688 =
1771170719 0.998 75 0xc3239cc0b413545612aa4f501e615f7ed1730e70dbc3a0edd2f6f58e0fee6758 =
1771170721 0.998 5 0xd610b599d1619e991f1c1595b48ed54a28a78592a478ec0ba8bb919aee54aa08 =
1771170755 0.998 14 0x47357aa951eaa9dcfe2f3e86a5e203371e0eacb3f3b1bb6396c68acda3a59242 =
1771170813 0.998 32 0x76a1c1f4dee45e395c9b5647b6d8a7dd469a36f6e53c5aa9444d7ea1d5cd29fd =
1771170835 0.998 5 0x38cf8bccab665fd612df431f139f643e920f7179481636b8705e7905e4145d4c =
1771170931 0.998 10 0x80224e63085ec1ea9f22eb0bc279ef4277972acd2790b500f5e00d280a493e9b =
1771170993 0.998 10 0xff17dd040e9e87d6e9c618b88486260087fbc6f4f22e251c8e5567edcba1e890 =
1771171053 0.998 5 0x12db6e9e14f00306ae2ccc2e52a12877cc35685d1b7f62df6fdb4b47ad51e6c8 =
1771171097 0.998 40 0x74bf15ec2cc5be4e001bbed2e094b797fce221dcf1192cd685af19b33a4fb437 =
1771171097 0.998 12.27 0xc87bb5d1c0a487c5be21aa96095ead86cb8ff67dc09dab0e3f1e4a17b504d601 =
1771171249 0.998 41 0x1bc561465fc83cbecebcfd6c7051ea60fffe817d9776602f590f7bf3a126ccdc =
1771171341 0.998 150 0x8dd19cf8d88187d34d09b97cb71b03888555f46b3a81ed771c37557d84c0dc35 =
1771171341 0.998 30 0x92ab42a54cd8947dddf4eab0fa20d59fb7d94adb9b72dea5ead128cfdb95cfd9 =
1771171341 0.998 5 0xe2727407f57d00359832e601cc70e973fd635e47c84f7d64a85493f5e73f33b5 =
1771171357 0.998 25 0x641b64ac49aabda10b39f4eb47ddc183cc9da660ff05ccb6388e84fb09b58943 =
1771171369 0.998 7 0x42293da497048a6180e75210a6e533c559d0e5eac443663157b0b9dc9daf9e13 =
1771171533 0.998 38 0x2f65222740659e88f17ed6fa3560448346f4421fa1890a429f571c1a66aa5c5d =
1771171563 0.998 21 0x6b564b08a382632500663c0951d71898086815eb738d43d5d0ef749b46ca7fe7 =
1771171633 0.998 5 0x3d25d74cd36aee26ba65d3eebfde09597fd26675f6f0ffba00fbfcca5377b5df =
1771171647 0.998 70 0x48db4031332c9d984d118ffaa1540aa7a162d6ee2492ec94c0ed4a126def7b89 =
1771171647 0.998 18 0x6715ce6e96774a05963296876fcde3195607a8799c21c40d5dc03b52b48e9890 =
1771171663 0.998 7 0xf61ad0c3d9e456a9b561cb197a16a4e4bd35b44e032e473880e84366886df26f =
1771171747 0.998 30 0xa09bcb96b66502c98d8a685bd57d3a33f58f5e303a877e8474d01688f939e102 =
1771171749 0.998 20 0x598e1eb40530351046f4ea8b48fe02005fb01b27e2c58b14d81d6b3e53c47f76 =
1771171763 0.998 3 0xbaa2b3695402aa6904723698e0c4f59c4d86417797350ac89c4a380326f754c3 =
1771171859 0.998 25 0x05a459454a50638a3413e8eb8d519e90953365d7e825e5d8c22fe93480e5cf6e =
1771171879 0.998 26 0xc1abc8a3b0e666384890eff2b413d860793b7c2e8679457e8834a234067f4333 =
1771171927 0.998 15 0xa4a7077ecc759c258ebbd80a7dede85e504c8aa93b80007a8532f410be3defd3 =
1771171927 0.998 15 0xe5e3d928d02fa1929e6dea5b68804128b64213a97122fc48b4c2ca6e15694b80 =
1771171979 0.998 15 0x8b1c28bbd9aeb6a84a66c49d2221cb6d76755a4c5a7f24ad1ebe7f056e22e35a =
1771171979 0.998 201 0xb618349bc9691727f3c43a72d8000b6646245f69bd465fcb2ea00f06f211539e =
1771171979 0.998 30 0xbd97f3bc3f7634d630b0b6568fa7e6d88a68ee089f4c4759bf87d77616814abc =
1771172049 0.998 12 0xb83f3f714a50a05526620d52362e1465aa765bfb9ce737c1a9dd1698f0946c2b =
1771172113 0.998 13 0xee6e6454316bc3112cd65f56f41112cef7d2651c2f5c11f894506a4c71e0f181 =
1771172225 0.998 10 0x82ba35ea878dd815b7257e746b79647f5e892b1652d8b20c31b9e518efdd2edd =
1771172247 0.998 11 0x9a0f59525868c47f5a9d474c90cb6eb102bdb874b524ea6cd703d5207d7d5165 =
1771172249 0.998 18 0x7ffdec095d4fd44a929a79c94765ec35edb0474b8272aaf1c01c2eba3d4e3f65 =
1771172251 0.999 7 0x23ea585939d6b460b9fd7ac43e573f10e2afd34b8b3040d59d15c09df6ecabec =
1771172251 0.999 5 0x351bc94c715aa8309ccd40cd739563e17b71718d35b15a6211007448cf067495 =
1771172259 0.999 30 0x56d997ad021da7935e63adb5ea66dd46156afaed8a54b959627a3aa30ee8f8a7 =
1771172291 0.999 38 0x1959798be7ad2bf9017b323085a2f98eeb9d3a2d2f10fb03b55d7bd901da02b6 =
1771172295 0.999 25 0x26480a818584ab21dcc1034fd1081f369f697f85e1452131ed595a7d0cfe9080 =
1771172383 0.999 12.04 0x482480cdfc9e1a8b6eebabfef821e0df3477bf9c7e7324eaa5d93388c8649a34 =
1771172479 0.999 38 0xdc8d23a635c4b827d4ffbc6151fdd20c82f29d2a7c814550d347a3adeb2978b4 =
1771172557 0.999 50 0x670c0fdbb88d5d8ee6a6e73abdef4e3cb714f01f16df17b629c240bc5425e991 =
1771172641 0.999 10 0x1d51db0807200122eb750b23a2371f368012ba2bf095fc92a93f291856716eaa =
1771172855 0.999 77 0x3bbf8e331e395aeea12c98d19100ee859dbcdc3aadaa2c15c74deabbae593425 =
1771173253 0.999 10 0x5fb2b72c0d38065a9e9a1373edb6b76517e97f0ac6c81876a020e9e3e61a6293 =
1771173253 0.999 25 0xe23c7b395d8078f8ee8b506fc7f2a8faec74c9e23420542e45b6b34e0e6ab11c =
1771173255 0.999 9 0xe46847e6caf2dca30f8c8d6893a8860392e4ac16a826c390b02ca7c860076eb7 =
1771173359 0.999 51 0x0f5b2b456f88898e82a5d0edc9845f67e8d77835d4a8e0ea60d587318726f886 =
1771173359 0.999 10 0x254645ff677b743fabc25ca314311eaa93bf3123e98eb2159334455999cc5825 =
1771173359 0.999 30 0x47b406d7ddd8772bdec290a7d7af241dc3a977d04a44e7d01d7f037ecd46d08a =
1771174567 0.999 28 0xc1caa134695497664d10176f4b1fc98466792d663d6b8f5ab8309ae4d9c62d42 =
@1347945 Yes
1770415351 0.02 59.99 0x7badbc706fbdb4e0c06876dbbb7a1a7eed38bb2ee6b88cdcc62be0876dd78bff =
1770483023 0.01 6.12 0x421673825d351841a1ef8b982a26fee34c1da825f38cab6c516242b4b0431202 =
1770483025 0.01 18.58 0xa3f87aea5d9b2397b06372609894b59ab4cd3ffc30b4d926c3c86b403b243684 =
1770483339 0.001 63.12 0x24e693385678d047d01d01be486cdf074d430b445b4c1adba23e48b852ea006b =
1770499611 0.001 24.3 0x96f6c6aef07195ccdc8f17c27b3362eb8777f68f52499a39edb6f0d21a5fb65d =
1770539111 0.001 0.25 0x4c34c57f51c16700e8bbb179d6b761679db071f09190a1ad01c3c7e259d5e049 =
1770855867 0.001 87.67 0xec7c48208a51ac5c0623f79abfa97b4ea62d78bfa3f559a29eaf2f83e545cc03 =
1770855879 0.01 12.33 0xe274ef1487b0b54dbf86fb380e405a1d43185c7b3f4f385647e2f3ec7b3474be =
1770856231 0.001 6.46 0xac7f1c50c89db582a4bcfbaaab61bbc7714630e9e1b7a8c42a8749759069125c =
1770856233 0.001 15.14 0xfc505c8396022c01ffd6f05fc46fcc3b2f44914c04692f6ff3937b45457fb76d =
1770871755 0.0098126673 112.1 0x05318868f5fbf58e5430d22329f30182679c0414c70bf9f6c7acd2942f8cbdbd =
1770898647 0.001 2.41 0xc166cd59ae00426e4e90bf8ee717bb6bc847b6408ba9d8228c357f2241a66f15 =
1770948021 0.004 2 0x4bf87ccb1706cd49c3153319337f0813abe20f1cd228b8066a3c5099d8beaf5e =
1771107825 0.001 4.08 0x8b116e2906b18b5cb6a3289a649f86fcb0a624b2ddfd3fbda7a8d6142c8fc6e7 =
1771108931 0.001 38.09 0xbae93f9c83b944108e02bdcbd745b27a01b01a6c53362e3d9ef603913ab0f576 =
1771108949 0.001 89.22 0x3166982b2524dd105d961bb0c3966da655eaff8e50eda6af1037a31af7b51a13 =
1771109083 0.001 15 0x78fc3af7e717443c44ece6312cd0c8ef30e9191c8d1ff6457b35cfa34163459d =
1771120499 0.001 10 0x32fef98e02f9243df51522bf4a67e54fcd9b4894bd13c02809538ac71a390192 =
1771120783 0.001 22 0x1e3dadadd912206c7e780f57c11881d9b116334011b11c0ab559d95782cfbde0 =
1771121197 0.001 102 0x277467771dbdb34337d9383bf6bdc3f429f1d32d13903a9ae08361ea48e46782 =
1771123527 0.001 6 0xb50822faa441db551c5e815ea6a02151471da0112f89d0c8323eb233caccf310 =
1771135861 0.0095607673 108.777776 0x84d78652a78de79e2817bd5aa58869c9021ff1817617543ddd4108c69520156a =
1771135879 0.001 108.77 0x45c024c253234e49671125d7a5bd250bf921d7b9cdf227107cfb014d74d3c5ec =
1771138005 0.0096429921 238.09 0xdccb43ec26414272c6b5d56d24b00ba7ff6126238d37c138306f3dd0451c4e8b =
1771178529 0.001 1000 0x8b2c87e469e99a6e1e17327c5a34000da148bd8803b435ad97f8240e5be9b1ce =
@1347945 No
1770426179 0.98 10 0xc26238992a345a7928bd60367785095a75f0bf0fb14330ca3c6da51280652dc3 =
1770426179 0.98 18.0306 0xda0abf034887db8798a60972e9a3d249d33b7e073f1d5100b1340350bc74dd5f =
1770458431 0.98 10 0xa9c9fa11078c8b24d63adee808c6b3de5d45f4cf0222f4415abd2ff0e69cbdef =
1770462375 0.98 7.04 0x470773504399aac2430afe6ce6675d6cd7d797cc09e194864789ec343f85f8a5 =
1770462393 0.98 5.23 0x5f29d4c3c074710131224a2cc5ba9bdcd44d885bd3bb337f6d552e98f52282a6 =
1770464353 0.9865428571 28 0x72c887115e1515eee8454f99772358cc55515e08e9e41d09c85a0f27a9935c06 =
1770464367 0.99 28 0x6a58950d6cca65f7a4758f899197a232e37276c3512e84c94b5bb87d1e50b1f1 =
1770466975 0.99 8.0909 0x8237db74bb099add63dc51ff9a6ed8fcbd940dda10e5fa0223faf3c0b92955c6 =
1770473065 0.99 57 0xde4d5ad93bd2976822d5159cfd62f800b8b29488669263cda7db68b7c8ff4c89 =
1770475253 0.99 13.88 0x0f75c1574248e85363bbcd9b9a56e47784cb300a981156cb4175d9de6d383c85 =
1770706299 0.999 10 0x875192431a95488d2e70e09bcae98347143eab4b259c4adea57b724ffa54eaa9 =
1770706301 0.999 10 0x1cc345101832ea965c9cdea23bd02f23d7aa68f2872a16a9ed7fe69c37f9c257 =
1770871293 0.999 5.88 0x03f87207a62aed5473ba779a463eac98c3ea314f29ff842ca13dc7e362196d07 =
1770871753 0.999 30 0xf2347c2bd5746eb6b330cec1ab39697879a28a32a53d61916383eba7f5a3435f =
1770905533 0.999 56.49 0x18090e25c27ecb245e8ae58da51e4be0bfb01dfa8a250883511c597bd4ca68cb =
1770935453 0.999 5 0x97ee4ae96754b753988e5356bf4e00ea38f8b4a67f42b5ea855e86ecad2c5b1d =
1770941197 0.999 30 0x19124868844169d25bca627f76435ced83612fee67501412456ef2d35daa46ab =
1770941207 0.999 71.25 0xc4cdc716c13fd29a356f3b623c90b8e673ef6ef88c5532b7453045bb9e15d37b =
1770941221 0.999 71.25 0xed29cec92449156257dc44603ca70cc4919ddfc71d7febc4dae693c12a35fe8c =
1770946273 0.996 5 0x21d76e941b3d886c47df1b7638338652952fef1a4bbb689827e1236692d169eb =
1770950449 0.997 5 0x60f5d2e5eac82123651df15dc85c4792a8ff40899fddd29a468f54f021031761 =
1770951709 0.997 35 0xf22ca638c22aa9e594c35b86fd2c579c92c3832d0cb1d14128f11b11d27c4700 =
1771062147 0.999 5.91 0xd7fb8ab32f8394c78603669d31abc0b8b274531c41ac5c6c50e573bec3f672ed =
1771064729 0.999 17.61 0xe4a69e1670e9a4d83d8268bfb169a76cd764f1393daf06e1f6012b5db6a30872 =
1771065747 0.999 20 0x2e6ac3b13473d0a5917cbf2cd43d77df66267f366db43a3499167ae27a7a89d6 =
1771076085 0.999 20 0xffb14aac860a7d78018f2fd7c9b617d2fa7e3bf26889409c9f95ab8c82e37894 =
1771085533 0.999 20 0x8abe6f72714e3f15b77e1c90fcb97b0f4ab245a4826c448e313f6c4066a444d1 =
1771086149 0.999 5.78 0x75a6b9771d6a49ab9006bed1e05716d30f8ead8c4d8758be141a29387b6d3988 =
1771088985 0.999 5.56 0xefb19f611c039485152212916e744c303419b066e9cd400422e11bcb14b0775d =
1771089711 0.999 20 0xb2785334459948334a986a970fe3895415995bdf0425ca8975585ad936de7be6 =
1771103735 0.999 20 0xabce3f0a221010211ef27010c32f3a0722cd34b4c891c916a193b0c3a9b04d8c =
1771107441 0.999 1.9 0x702de785dc0630722b399505ca673a6de5e6dc0b3fa0c9a47ce1419d2c9ef8f3 =
1771107551 0.999 15 0x34986d507acab29dc7e5a237e169775c6aa544c7d656f89f80db382dbfd6e82c =
1771107551 0.999 30 0x4d908973d9ddbe5f672ecb0821e7e2b79d231b52f67df9523c37b1ce0b3626b8 =
1771107551 0.999 10 0xe0f90d65ef40a9d99a2573fedb3bd8db015c9e7a18a4bc9f99dfbe8893140e48 =
1771108621 0.999 56.53 0xc8d6a973bc51b035486aaab76ce51a8cb1553410910462edd3752dcc98990e76 =
1771108685 0.999 5 0x088bc6b811d6c159d89319763e0e9b82009735f7feea2d6137c067239d2df38a =
1771108685 0.999 29 0x62c609f871aba9306643a23003e66eb3aa1917dec82f720669fec6539e6d580d =
1771108861 0.999 5 0x60caed57e08eb21906d3601c8bc128041f919706c1867efa6ae191658e39b282 =
1771108881 0.999 5 0x0f1b28f2b998c2a622efb3b1d36749c11d54d55f1c3ad511be7a427fae467325 =
1771108901 0.999 5 0x53d3e4ea9ee0c6efda7dc38ee2a411801b57da0da10fc1b1b6c56361b9b91295 =
1771108967 0.999 35 0x5dd0487bc28817e3cea8f5ff969d972a9d82e05ccc42c4fc66f78d5d4811a1c5 =
1771108971 0.999 15 0xea36ae413312a309dbc18f425ff78dfcd98b791698ea7ee0cc6067be5adbae21 =
1771109105 0.999 176 0xa2344e3207165476168ff5000501ca01def1c7600c254e5fc7b7f30d781a112a =
1771110711 0.999 12.59 0xa6215ee937164ecba9381fdb6f495a28d6568339a49a63a175c627e55a6298fd =
1771113111 0.999 39 0x957791e6a5aa099f844d591f10873eabec9706fea3fc10e8508056eaa0bdd18d =
1771113883 0.999 10 0x5a574ff04b52f4de6801469ec8eb3d5f2ec0c5ee068b2b86bbb5635415a065e0 =
1771130469 0.999 10.94 0xddbd680cb59ad98f7f55d3c5e14510d1a1785d7353a1747e587d6f782be1aaf6 =
1771130527 0.999 21.22 0xf97f76ed5188a9bb8ea7a0d97d6270762546f695d0f684e66f77938a36716ee5 =
1771130545 0.999 16 0x3763bc721c129c9d682e03c923f23c802d823b60b398ea6c6fb85ade745c1493 =
1771130547 0.999 17 0x1af679650d7eea42ba0cb12ed9634fcffb06d391751717d7309590d174e0dd8f =
1771130547 0.999 5.97 0xda89770f23c4d6c1a2c535203a287d953b98b5056bd03bd81016f749a3791ed5 =
1771130555 0.999 16 0x45c1c299fd33d197cdc6f48d4adb8e1016b057858d11ee9826dcbdc1e3b5183d =
1771130565 0.999 17.79 0x700c2ff3d1500b497d4b2de2aa39461a498877697e835db29e4a30f5a34942c1 =
1771130581 0.999 8.19 0x1eec736f3c80b02bcd175e2a71b3c7a56ba8f3e19b3715e2207d63bad623687d =
1771135849 0.999 20 0x99fd5658cceb2cb8631ed7948decb481cee4075fbfcdc0275345ee72d8aff0c5 =
1771135849 0.999 511 0xa06dd5d428e88d271bc80586b6cda66aa20b2a6e86df08da253100a769335912 =
1771135851 0.999 30 0xd8f60ac280bae21dfd798f2c2bbb6454730447a2c784a39380f6733340e4d0a1 =
1771135859 0.999 71.25 0x91eeda88b1b36ee266fc4984fda99a073f234cabb26f2e34904c39c8ba7f9115 =
1771135863 0.999 5.43 0x1d25f01b93363a48e2bd112c26c2ac61047e863ab625e79ff218366d81cc0de1 =
1771136045 0.99845 20 0x684eacd3e910a5fd610f94af5bd4c221c054abbb13951420df50194d97a1d234 =
1771136045 0.999 131 0xf799db3febaf8123d52608f6aef49539f85eac8f9e06ec225beb394e0b5f13dd =
1771136053 0.998845614 71.25 0x639e3ae10b409f2faff2cbeb593e29fa82f45ee44d8fe87f66ef5dada7b3a14f =
1771136203 0.997 5 0x26c5ebbf3869d9abe20615be10e393313c145028ca680d96e2af132b1cba62f2 =
1771136203 0.997 5 0x2d4a23cd1f3816316489ba01ace5fde58e6cc0d494f910b5f73c9ed7999ff72e =
1771136741 0.996 5 0x860ec8db8434690d39ac851154f051edf3441ae92c3e825e4f1c5e63d52298e9 =
1771136907 0.996 15 0x6a90d5fea59ebcab9098d14a3191309d368b41f23c779260b7a447bb5c62be1c =
1771137995 0.997 1.28 0x1f5b592fe19179f9852f24d0ebcb3d99295b0f02abf5bf9a7c43d9f65c674055 =
1771137995 0.997 35 0x6d981f478efe64a338d7b1e349d23cfc3ea67eb6d870580a8eaef36ddb6fff44 =
1771137995 0.997 178.72 0xbf5656113aa2bcd06846ebb82c1e77211c1e454121629ad8fe891d8e5807788e =
1771138003 0.999 6.36 0x3b957dee21b19c34cfb0ca20239f407c3c034bf3c442c07c999dcd8b845d6abe =
1771138387 0.999 10 0x35a966ed78220936c48ec5d86040037e40c4ff98ee9a095651954d8641f4d1b1 =
1771138387 0.999 10 0xf23fb9fc2444d2d806d5164df6c79e0d848e9f6d5e995e4cd7986b5d9b3bac4f =
1771153219 0.999 5 0xdbf1d04753cc4c07a35588e3b0b43d351931d79c34778129dcca3e6d1941c09c =
@1347946 Yes
1770483019 0.01 48.12 0xe31afb704f86d36b8aa2932dddf6f02d9a2b15d240150ea2c008888d98b80d95 =
1770483021 0.01 64 0x22dcb5e443b7cd1892def0ca89b83162445e0f9f58a044e71dbc5bd626558fa9 =
1770539111 0.01 0.25 0x245bb29108506643cc8341ab4b00403ab8076f891ff7193a7a6752758b7083e1 =
1770654355 0.0198148631 151.4015 0x04418943efca55a91e7fab6f3c9a916465a64fe2bfd211f7d4f3b1b53b4270bf =
1770664925 0.01 30 0xd0da2825266c13fa3f6d9ba4245a23783cd8c67f479c2abfa14ef07719cfe083 =
1770713555 0.001 0.47 0x0aabcc935fa0d28ab680dfa9a0cd67fda2db26488dfdf9e9e105c751b4da0283 =
1770760013 0.01 29.99 0x9c0d4ca40c2fae1dbc8eda0b234988bc5f6808c2f276113d1ba55c883e30898b =
1770809535 0.02 250 0x89bbcae312077a2e08f60fe5d389f1b7602408abf1c5200d5f748a01cab7810b =
1770898647 0.001 2.41 0xd1c68ae3ed008f3fafae560a9c0f4093a969aece3a6f72cbfbb20db6b43b720d =
1771091029 0.003 25.66 0x6f114fcf820f98bbbfd8de245f2ffdb010bdd01e9e2e3cff24652f3a561aa2ed =
1771107825 0.001 4.08 0x525da2423a121892338b32eb82974ea67c41f81cb7a442c56a21420b33df70c9 =
1771108929 0.001 38.09 0x672fa85f5d4fe8ad3f2ac97412f0db031c8c17f3360ca9fff1611a83595d0679 =
1771108949 0.001 89.22 0xabf141c750e9f30e25c0f1bdedf187b7465df94ada8d1490263d791c6dbacf0e =
1771109085 0.001 15 0xb3bae3e37182121555398e9b2bc58196a64602bb330819512f384eb2cd7e551f =
1771120255 0.001 5 0xa5bf32ba129d6605a50827015a0a0fe481c5637a5a2243e1265019452c413638 =
1771123523 0.001 6 0x20aabd412a6389de352fc1eb7d619dd62581e92e47c0eda2fdb37ba7190cd0bd =
1771130563 0.0077935054 133.444444 0x3fb703a9572c7f17af5ef52c090e728d723cf1b87fd8b077219829e940cc20c7 =
1771130571 0.0114350231 90.94857 0x18094bcfd714b9a804e7945972ca5d6370ea9e924d11e0b0ee94c00ecdca0d48 =
1771130573 0.0769999345 13.506492 0x4350f49c977089aee60cdc045e2399ff25cfcfa74d3208b5896858bdb4035b11 =
1771130581 0.0769999345 13.506492 0xb529b89e6548ea8347064aedc3669a6ce6e6f6692adda3e2c7f2b2561b5d4a82 =
1771130585 0.002 1.42 0x8c16db7be167fd00bb1c3bc389775e79c0c5fc626fdf1ad53cb0372b9e1156e2 =
1771130593 0.002 0.24 0x39b4855c89c3f011ca47ef9c22d1a033e70303dead4bf1a76c2c6708aec9486a =
1771135869 0.0280000001 37.142857 0xbe4c9dc56814a7ae43283d4fbf1f867469f01c9fbd8bda4188bb81895677367b =
1771135891 0.001 0.57 0xc580ac9f033026d92b8c7ff8595c943887964d91776ccabc204dfc668bd1e26f =
1771138005 0.0143825864 238.09 0xf76a013e48eecece7ad7b3a729fea84262d2fc40abf4071411fd2f386bddb2a6 =
1771178529 0.001 1000 0x79f63634f10d44106f5505c85f394675495ba572662203524e564ca0479962aa =
@1347946 No
1770426175 0.98 18.0306 0x203408ace7db7856da7d0724b16730ad47bb5a93bb7c0f3c005f712ff17089ea =
1770426181 0.98 10 0x788c47dd9d67b840d2c31b6e688f9c1583c9b41e23e1aa748634e37cbd14c485 =
1770458431 0.98 10 0x886b39dda01e68438a03d78d4d50dd80df2d7b46cee483b580898201f8c1b5fe =
1770462375 0.98 7.04 0x369ba759225068696d2ebfb94fcfb0f2369bc34ceffc2d48ee8510a84fa4b43c =
1770462393 0.98 5.23 0x4331dd30728c5b2708606d55d15ebf338d142961f4f6e8814a9ca64292768d51 =
1770464351 0.9800964286 28 0x57d3220bf8572199c59b9a9a18c979b0127bfe7c9e9dca5131a116120362bec5 =
1770464365 0.99 28 0x4d472c7baff3b03a10f425156899ac389f9b049b245ac6ef5a29c3683a03c4cb =
1770466975 0.99 8.0909 0x8adc9104b2af6cf7c646045a5417eeadcdeaf5af08f6b6bea0af10e23b0d0a4c =
1770473065 0.99 57 0x3de979f6b4a254a4f502e90db4791e3ebacd5f795a862a8e93df1028e3d0d28a =
1770475253 0.99 13.88 0x5d19b42aadff8505cd65487863c24f97e339fcc965f7655efd27c09f33e364ef =
1770706297 0.9986581026 10.003 0x58338e95a0e84d4bbc645ee5b593d772df66192b405966290ecc7fc60f890cd6 =
1770706301 0.999 20 0x3137de3a7d430ccea10ae4af8042262ff29a5d57cff6188da4985ff2000b71c5 =
1770713319 0.999 17 0xa0fd6144aead21cee4212945fe67f1bc5f3e583bae14109d0ca381cdc143eec4 =
1770713725 0.999 10 0x0f4b3014524eb3c6dd3a0f377b411234a12f1731be4d5678753bc7269d50cfd0 =
1770713725 0.999 30 0x90d1b7b3c9c3e6db0900ccc57f20961ce502a4e98b6124cba4d2b3b18f7020d6 =
1770713725 0.999 23 0xe618117e1e77250a270cabc73e55007959254e5c96a72bf4299eef31728336f0 =
1770757167 0.99 6.46 0x835c1d8c5439803fe236a45e26739ba567dc2fcd5af51ad20d0b73712936d43b =
1770763003 0.99 21.05 0x5a37d3d173bcb1db05446aae727eebebe88b4baac789b4351fc8d014af8d84d7 =
1770827589 0.999 10 0xddea97cc9be1b1b9564b0cfd82ee82132cd7a8bcd5a8e7fe09c6dd8aa23b55fb =
1770871293 0.999 5.88 0xa5db1bd1be648b84f1eb0b280d03095cdfc8d94f335e7efbf7e0914601d64b05 =
1770871753 0.999 30 0xe7b6a385148d5aef3c8697f0d460fe0485df3f17e8362f7b6dd95104e4ed1e9c =
1770905533 0.999 56.49 0x952d7eb42e9e34759b51c36eb617107b51b1457c6af6491ef3e46ba1022de8ac =
1770935453 0.999 5 0xd6d69453b8708e2df87cfbb9fdee283f1072b22f04f153d4035fe581a4160020 =
1770941195 0.9945 30 0x6d58dbef04e7a0686dd9c85a229fe0bf66e8471f6dd7feec4c6affcc4c3471c4 =
1770941205 0.999 71.25 0xe567534f3a3e34ad4ad2e25aa37ff02a5fbb7f55275b4019d50adb0ba190bfdf =
1770941223 0.999 71.25 0xf24d2d15d204cd2de3b07751d2723ba7f8960b2a64a8b111ffc66018777f44f0 =
1770946273 0.999 5 0x0ced621962f740b05186c1be0872ade2a8c4daae7461e79de7ad643a148c7db7 =
1770950449 0.999 5 0xe92fa90f2c38a8622e90535bc1f8542b1fc78fd059396813787a2a73ac4eddf9 =
1770951707 0.999 35 0x0069b00d043809a0021742352d7ec6ef3683125da4cf202cde4965a14a2261cd =
1771065747 0.996 20 0xcb63946835f834768ebde54630ec24e8c636d49e11fc2e2c4c2584c027d1aae5 =
1771076085 0.996 20 0x1876aa21985321f1c7996ff23cf589c6c96a101dd0b5d4737eddbe7f5160048a =
1771085531 0.996 20 0x2f37133d72073e996da674420fc0d4f74e5f69612397260e0073ba0e75ca3429 =
1771086149 0.996 5.78 0x65814f47bb65d17c6e85ab9fcbfd4836d110c298eb426444a1788ab3ed160a98 =
1771088985 0.9964208633 5.56 0x62c01576ef8faafc03093f45ca5361e7d1c34db6b1e8b067fe1e7458113c2809 =
1771089711 0.997 20 0x8489a943ac0f3559dba1da4e629570ea37509274f7b4719e2bb25b6d1412466f =
1771103735 0.999 20 0xf2d74e89bbfa4046619e3ed2f18d9009a9ff8d60a3b00f05d3c72bf0e74bc99e =
1771107441 0.999 1.9 0xe78c0f6f76ac13d49e7b2ca525e3eec8a27698d578a6fb8181d350eeb5bbece3 =
1771107551 0.999 10 0xbed6ce90cb7f1b6d3eca091812e6274ea431504270b667a57141e2d569e31fdf =
1771107551 0.999 30 0xd48330e4f12366ac284caf48b4bd4d4b752f6e6840aab793ef21c8aad90949c5 =
1771107553 0.999 15 0xa3a1204c975de93ec10960f22ff7e314514d79723aff48d5297cce8124ff5875 =
1771108623 0.999 56.53 0xe009907590f9636bc3d02a53cd60d8bf990f0120a69a248142d3a23e9bc63e64 =
1771108685 0.999 5 0xde781abfd1a289bf0c98bc3da198e3e93fc60bb4028aa79546781f762db0d47c =
1771108685 0.999 29 0xf9d66da95428436ec02dd8e984c635fd8e7887d9f05aa6ff4ce624703f8fddb7 =
1771108861 0.999 5 0x349d983b9943dffdadf58ac535efbed55f08cdab5925b7522d3d596d8a7541e8 =
1771108881 0.999 5 0x6bc410560552852999abec7bd83af9f890351df78bdb3ca3ada64109032f27a9 =
1771108903 0.999 5 0xe3db45371fe4dfeb142a45080b98d01293e8e85e95000b3a5926514986def08e =
1771108967 0.999 35 0xe931e4ade83ff2e1229d43e49296bfda0b32e80fbdd9499f8062d57484664ae5 =
1771108971 0.999 15 0x28c0345c70f46cd4d9ad746b1b661378fda689a4dc10c788cb66a247a28eac4f =
1771109105 0.999 176 0x4ae0e8f178ab82c44b7a353c4f60798462fa0206bfb7e87c97f10b1703a4df2b =
1771110711 0.999 12.59 0x14ca611af43c9fad19643a6bf23523d090a74b19affe8d18c73b11ae698f8de2 =
1771113111 0.999 39 0x7a1df019329d0cf2f2d3b679a766bb56f31f32a62f04c954dc6f7960e56593bb =
1771113883 0.999 20 0x7deee055bd696f9a364c1c092774e61ed02aacbb6337eaf8a69ddd35615e6941 =
1771113895 0.999 16.21 0x93dbadc059e868cc5129174886633d99b206a896fee4254a32d4489887b8a904 =
1771117403 0.999 22 0x9b4efb8cb01ecc0cb181c55fecb4043f7325da2d5d27f692b92e10e6fbd575ef =
1771119801 0.999 55 0x483547b0453eaf4792322e225e0ee47525ede673594cd0fa59ad1c32d990ab04 =
1771119807 0.999 45.73 0x1ecddb24a7066a8adfad312d9d41d125f07e5cfe78d729537eed773054c24856 =
1771119901 0.999 5 0xc5a1e3ee0ce9c349474c08f56297864f02e16f78247d9526cb4d77a2f54d73d9 =
1771119903 0.999 50 0x3bad5d5a126f196b23e664799cbccfbbebf253eea91ac16f96534ae75eb8f72b =
1771119903 0.999 100 0xcd20f19b9ef458d777ab1b4f3d85af965f43ecb67a7d06ec1d9dda1d77428ac3 =
1771119903 0.999 20 0xf58b11a484c322721809eaf5d068d8bb070b93ca3fc481bd961bb0d69ec58b66 =
1771119909 0.999 57 0x8d72100fefc74c30d870c420096775391bd0e0eae27c0d965c8f55ba960d98bf =
1771119925 0.999 5 0x64dfec80b4323baa30ec4372cec996164920ad7bc9442ac012fc4dcbd8b200eb =
1771120137 0.999 5 0x856564f0865d0c22f3cffc04a2130fddaa6967e2e595b8b6f449782f476719b1 =
1771120137 0.99875 20 0xc1a27d985c45a0b16c5174e045a860a75faab2404719b82554cf8e84db0daa46 =
1771120137 0.999 5 0xff15678f0289edb9c04a3ed80f4a8bfab982e0586106bfd5266fa88a3a9ee612 =
1771130469 0.999 10.94 0x1860c18ede7078e975d9e661475d7786bd991c54879a22f578c8e0d415d1c9f0 =
1771130527 0.999 21.22 0x826300b55d966b8fc65ee03cef9f25e3953c68aed66236c40908301439a3a26d =
1771130545 0.999 16 0xea09edfa5f2f9dcbaa1a4a1029c55451990d9da9aabcac4af5a339a6136c0346 =
1771130547 0.999 17 0x5357e19efd0c455d28852b5c9e38ef3c97a4d93c3de63830baedadf57c29cec6 =
1771130547 0.999 5.97 0xa4ca2ff0f1d2f6deb0097b62f955ba6d13b04181f638d224d38d6cd3452195cc =
1771130555 0.999 16 0xe7ef42de8987cfcc9ba8f9230d3e602c24a27911353584dcf3015cfc93f41adc =
1771130565 0.998 17.79 0x94b05584c4cad12006c1728295f79cd0edfac3f4258123841b726fd8b890e21f =
1771130581 0.998 8.19 0xb25f2bd4be158b78ed871626d8baa1ce5339cd6dd29fdf166cc90fa503ff930c =
1771135849 0.999 479 0x63d2d43e0a12c37c6e93e0f5f64b19558036e406b8558359a856d2dccd6322ac =
1771135849 0.999 20 0xa0cc3ea49ca4ff28a3c4a745a63e84611aeb4277a55721f143aa955864108755 =
1771135851 0.999 30 0xaaf2f8d4db1c5d9c3028416d9e71a7a1d6bf85b52f32bc2db07d116db3df4a17 =
1771135857 0.999 71.25 0xa689deb2694345eaca06e954bd6dd136a49aceb88529d0b147aabf03a45a6de8 =
1771135865 0.999 5.43 0x0a768b83e5c258a05b4b3d3e68ac38e847a403a53b18b0a31453c0db7dd0cba7 =
1771136045 0.999 20 0x52b25f5ac9fd63dba0d4e6aa93df10d9699744d8a7fb48d3acafe79ce2a5e26a =
1771136045 0.999 131 0xa2532b774e77b86cef1969307bece633222cfab39e35d66c7893134bc822f08a =
1771136053 0.999 71.25 0x4ee8e8cb70030678bdfd29fd5e6b06b0b182d69fa76e7459b8aa8b25e98f974f =
1771136201 0.997 5 0x203087ab1da308376731ea8cfd0766f16a0d6bf961eaeade6f3e2b251d3d607d =
1771136201 0.997 5 0xb10e28c1d70eed615d2deab1fd9a1c4b55f74242bf9953a9c7b281cd4f75a3a4 =
1771136741 0.992 5 0xbc380584c279577b52874ca5f54deedcd3fd088e7cd3c3eac873a37f65998cbe =
1771136907 0.994 15 0xcbc592bb2ba5b263494dd85607e6f6a415b0389a8a787cecf0204d2ba3dad429 =
1771137993 0.994 1.28 0x347749fcee0da472a520cf2c870580fd265f03dfedbc5094338abb50cef3e34c =
1771137995 0.994 165.72 0x06b66e90479e81bbd4ae3e2817a75e78c0cb8781be6d54719b2960546e20a0ae =
1771137995 0.994 35 0x47d740ff0e7d476a1d175e6cc03d3283ada1f5ac161c3913a141a252f17a7403 =
1771138003 0.999 6.36 0xe96a51711059c2620968c6811f461516c2ae4b6ca96ed582ac976988e729a5ad =
1771138387 0.999 10 0x7429923c5832a627d7b8a4321043ed86de0aceb4c6d5f8f42114580fe5968c22 =
1771138387 0.999 10 0xc5e7c2d2aadd0e4bdf2eaaa4b5bf4381908837e300234faf95edcaa7d5a66488 =
1771153219 0.999 5 0xd168a864b6f2f63fd87d8276191f077cf74fe27c0ed4d92ecae748dc68814742 =
@1347947 Yes
1770483043 0.01 6.12 0x3708395121d57434b5071c8836c04c8255668bb7691455dc2c32eac0f7a42045 =
1770483043 0.01 57 0xf32d6745799958bfdd1d95ad10a50f0f59087d87b41516be1079837f9a7c9d15 =
1770483045 0.01 29.63 0x686590451953a5db583418a1fd9224a2826f9d4762ca8c483c668b655997173b =
1770488605 0.001 19.37 0xf660c509892de758e76907eec682afd237e165081d66fb1aa19c03e25d2dbb3b =
1770576755 0.001 0.25 0x4a8ad681789a0f5761f0e43ee4fa59ebfd489a2db2d801be990b0f4cc5e59267 =
1770713421 0.001 5 0x2f8adc27583461ce5a54d953790c807efae9963ccdde526668a638c895164e0f =
1770749259 0.002 22.72 0x20aa1ecce4fb91550b5db15ae9d8fb909ee0dc12d3e8a81054afa4bdfa6cb5d5 =
1770796423 0.001 6.46 0xa9850fee21f0618d579756b442838c3b635cb309e441fbc10e1c35e28689973d =
1770850001 0.005 19 0x0353e90b69909a86d8b37daf6f79af7e4da36e1e38351bb1eec2ed2cfc615d5e =
1770898647 0.01 2.41 0xd09a4006fe3a4bdb40a478021be1b2c64ed34244fdf00f9d6b1532b52a5e43ad =
1770948123 0.001 5 0x0f7aeed83bb92c74a1c8795d005e94af182af6b381eab0e0be14a9bc92bb7a07 =
1771107825 0.001 4.08 0xaab34442d1f22b3def3e7ae553feaa0ae40db5d6d66722354cbb38579ca01f49 =
1771108931 0.001 38.09 0x481c9915540fefdaf6a02f4cd8f2d6c8ac72d775ec6108271f4f02a3bdad34b0 =
1771108947 0.001 89.22 0x45b827b04571a846692278288099d32238401878f546eb04a66ebf223276c290 =
1771109085 0.001 15 0x97f22d2c6dbdcde7fa54f1f94cc8460cb19fa32adfba3c67b590a21e3511e62a =
1771120255 0.001 5 0x3f6a77516e7525ed1798c8fe72ec71e14b00f944d1bdf790561eb636b86a23ca =
1771123533 0.001 6 0x444fda0a7af6993b938e7de5e79e3cc475743cc5a865aa50e70e7e47a6a71057 =
1771130439 0.0053640321 193.884 0xb275f84cbd4c5455d0f06522e42cc10e18fb381c2b1c920c9a457cb5f420c4dd =
1771130459 0.001 2.9 0x9c2aa136ae5a3a32a8545def6df1ee314c38b962c0b471105cd4b4fe99b912f9 =
1771130469 0.0198874431 52.294254 0x19f5d26311fcaefc9cbb7051d8cbd06ddee1cb819d64788c3bf52a8efb150a55 =
1771130547 0.0452601305 22.978259 0xa949a28bf21aca09c07ee9809622163efbc87fcda0515479ebba2f45a0b30f91 =
1771137995 0.01 110 0xef84b0b25663cd7f8dd8c17bc571c64e3d61bc060137b749258271e43c930c96 =
1771137997 0.01 238.09 0x454ac9d9f155940448ef42f834d5846bb68e4244fa833c687be29d1cd7258faf =
1771137997 0.0093573859 238.09 0xc96e26e7675eb2722865690f5349f380aa3d4df0bb14b9f07ddbe17af69b6042 =
1771137997 0.01 238.09 0xd6dbba7367812ed9eef66bd5894de6f693e4032128e71602d0d34917e1ec5f39 =
1771138005 0.021 0.26 0x7cf1a4b1d45616f782f9abc0d3563feb07f3d33580d8afd5d5ed391632affc03 =
1771178529 0.001 1000 0xd0dbf3bb427a2467a60ee31193c843dec052e0b9f25485c361523c39cc01546f =
@1347947 No
1770426171 0.98 18.0306 0x057b9634bae771ed8eb896ee049bd12c94827790e0160f80bae23398e79d8949 =
1770426177 0.98 10 0xad4ff541554dde3f3c996d0bf33a801eb7d6877f34fcad0f6fa780a209ca0f3e =
1770458431 0.98 10 0xb2530806cb8e4421ed09267b5f85c584165b878541c64b4389f671077a3b1eaf =
1770462375 0.98 7.04 0x67b076b7d276bef8be0ee73e46f3d518f8195e8057fdd7c42da1c83f4553b6c3 =
1770462393 0.98 5.23 0xe051494246e5b89e79883f4fcadfcdfb9809b9dce3396587e06b959603591a1b =
1770464351 0.9800964286 28 0xd55b52dc1162dba74815e10aec55e77bac6ea397f1191b494110ec6892ec3c89 =
1770464365 0.99 28 0x28ae53aa090d031490f05a1b24ca58fbb2e957922c0a342e0b3bb0f93d0abd0a =
1770466975 0.99 8.0909 0xe7e6f64509aacf0530c2f5d1d50a55370696deb74a8b6d8d7d4b4d52aaeb5a96 =
1770473065 0.99 57 0xe0d49f210ab8c81f3abf3e9838548f8db6033324ef868689de31e2db558fc90c =
1770475253 0.99 13.88 0x4c05ebffc36f89b0a60a08e2a0ab521de3eba90a6ddc840f4695399dd3f155e5 =
1770706297 0.999 10 0x2e83bf78a7717e9861a7f3ad9b7d7affed893bb1b48619bdfff8d2fc60703360 =
1770706301 0.999 9.75 0x2ea350df24e64cbe27379712fd70a8f8b78408a4631e469e1290c6be207da247 =
1770827589 0.999 10 0x7726ea240ceda64a82081bf4f99b9cd87bd0f475d5ec428d493e57f3ff7eb3b5 =
1770871293 0.99 5.8888 0x8f587b0f5a64561e6d8efbfe8839016ca41a8e94ccee8df40fc753916556af18 =
1770871753 0.99 30 0x6e8531a366e0007d1878bb4f030e91713fa33388203a2fcddaeb8a3c051f84ec =
1770905533 0.992197026 56.49 0x6fbbe31660ff51140d8dbc189b4f02b0cb8a833ab9f38f33aae68962d65a89f8 =
1770935453 0.999 5 0x302dceec7ef682c18eef5031914b3a86c2dd04217869e28127331fafe36c9b7d =
1770941197 0.9945 30 0x3b2e9bb31c3c91c9e7acc116a797a248f79f00191b783021cbafb96f61a69eb7 =
1770941207 0.999 71.25 0x36972aa4a356d3136776d5f09725023fafc40ef07c2d7d648d22a80b1babe874 =
1770941223 0.999 71.25 0xcae27606b17ccf2ba360a158b180dd52129b9bac401a3a97625029e041fef1af =
1770946273 0.999 5 0x509e329c72bb56c2fb03a92db6c9e122f08f5b4d78dc7c5f4079e93ec46d8a3d =
1770950449 0.999 5 0xa4bf82cf4ab53864acba1956cc1e5ed9ffc395264470efd195e9255a2f701764 =
1770951709 0.999 35 0xc677c16b9d1ed0c9efb1f896c52e907afcc7cc515908bc28dd964e536348b1ac =
1771062147 0.996 5.91 0x786ec8a39726d0671cc7f95a36ec4e21382a2fd14a4dbb28568e9edde1d24dc9 =
1771064729 0.996 17.61 0x7c60e2eeccfb1ae91647c9d87c4bd9b5f017724cde3b5a41c1ce6d4faf4593fa =
1771065747 0.996 20 0xbed81fda6d883d0288a5f398122be71e56b0513bb18b1660773a941c368ff8ef =
1771076085 0.996 20 0x704c8446bc3ca29f4c2c62187eebee71e3e02291cf6556e4eb522fc957733eef =
1771085531 0.996126 20 0xa0335fef63261ecc85e7d37be4d6c1e32d7dec2699d376081587189b707adcbb =
1771086149 0.997 5.78 0x57dd4c5f134e9fa6658b3449c9b01672c898cfbeac9aade516bff4780ac24628 =
1771088985 0.997 5.56 0xb2d9e53795e7ac29d578c3b2d55b172cc672ff50fb9858722de79398a3eeade3 =
1771089711 0.997 20 0xc0eedf052f580a4d3bf7365efb28f62030e1261576e1840e68d7352940316e7e =
1771103735 0.997 20 0xcc493f40c8f48bdb93ef4c4dffcb0a449e3dc17b7e8fbde32f48e3bfb7d7a4be =
1771107439 0.997 1.9 0xa1472432f9c66888170b025977b03afde3fb7264befe3fcad6b02117d67a4922 =
1771107551 0.9974506667 30 0x364455e7687268ee68484ed3aec338ee2d8ca3229a174b15fef84a5bff07688f =
1771107551 0.999 10 0x56fbff689aee64ce1e6d964fddd760b94e05b5be720755016bdf8ebab9a6c434 =
1771107553 0.999 15 0x4941b6c7562697001babdddace9df33c4033e46c7b7a8bbfeb43bc69d76c818d =
1771108623 0.999 56.53 0xeebe865391a0c36b1f7c28ff290da3a2d284692d6802209cf2f95559d275f2ae =
1771108685 0.999 29 0xb2d6247ae77031bf8b32115ad647a7c61e5147caa497359df1352c222e535ef0 =
1771108685 0.999 5 0xc3eb14525bb6e26a5df4ea7f504d0ed12e0382a0b29ac4031ec0800ecffc4160 =
1771108861 0.999 5 0x06b8d75ecbee2a30da38a36b3234db81549124f5cee052f20ef5c48c0c24f3a8 =
1771108881 0.999 5 0xb1dbdf1aba8b3cd7b3c036884a8ba99fe6bc35805c8f6717ac2b5424594fa6a0 =
1771108901 0.999 5 0x5ed8520decd0a125b09bc93592e2dd3ce450fa3667479c16bf01881190a992ba =
1771108967 0.999 35 0xc41f91740bf06b4ed09b3e4b0e7cdbc67095dcea4256a215b0f1aaa9b982082a =
1771108971 0.999 15 0xbf7119ea74368b7be8b1ae3611eb9ff632251d3f8b5e3e1c6bae6eba89c64b31 =
1771109105 0.999 176 0x2547553828c8996b869af725a5f2795f69b9752249adf87e5116ddb5b90ec0ea =
1771110711 0.999 12.59 0xa7e0490ee0b39b3b43b8e6fd1c4a9c7c6299e173bd0813bf03cf7c2c24f0d365 =
1771113111 0.999 39 0xeb37fd747fa5a4bc2f78ac96d730aac7fae9258fef8ba35c31da30a39972ec1e =
1771113883 0.999 20 0x27d05f124c38ae2b94d6263951f350e3f2fbde8d3d5598a551a96829144a2b61 =
1771113895 0.999 16.21 0x186f049bdae1e7fbd3156cf79d8ca57a1a33d9ab9a5fe1481a36ad8ceb3b0593 =
1771117403 0.999 22 0x64aebaa7e6b0ba8daa2009e20f212d3b8157643b12d9f62a75957f7afa74f0cc =
1771119801 0.999 55 0x05643752535e3ebf7142778abc1bbd9036b43c18842f86f6e71900bbfe8c2c7a =
1771119807 0.999 45.73 0xe06a39181568b58b3fe7215759dc3db3986630bdc508969e8625c12624830c83 =
1771119901 0.999 20 0x2097018c60e3692297842f6a59a074b51807069952dd0834396061e6481501e4 =
1771119903 0.999 50 0x35af8a7e1710ca6bc5253f1c66775af35c37477e9f06403247b0a1886c99831e =
1771119903 0.999 5 0x5703bf6a677acdb372f2e4ce797b0bc851c13d943031a01a80e69a563c2d0803 =
1771119903 0.999 100 0xca9659c93a95708441d53283e334969580c74f87fa02c42838dae70a49d8caa7 =
1771119909 0.999 57 0xc749c6fe63f794ef0e3c5074b202dc4e77abcbff23b33e3cf3329162d549295e =
1771119925 0.999 5 0xac4eaa9e1f22cc2ff05c87462745c99c74f7c0f4873a12848d8649579a44bf19 =
1771120137 0.999 5 0x379e6c9ca591911d5b9c6a89d6cd0a1f26b9a9a2795d50f8d673790849f57b03 =
1771120137 0.999 5 0x79e0584e8a3e63efbd20392bdaffea2ede3ad33c49f40a2f6731861047937017 =
1771120137 0.999 20 0xcd08e68e392256d43e77895e9ec953e77f297d88601386bfba2258bf611dbb91 =
1771130263 0.999 6.456 0xc4938996f88115fb384cf0cccc6c1611c145c6d00fcdc6df7d5ba67e32cba610 =
1771130345 0.995 5.38 0xc63ab1c3e0c9a8b901859997cd7b4338e9a59d17864d2a698913c9b03e24bab0 =
1771130527 0.999 21.22 0xc7b6c1a045617ceb3d80c4b74a85ecd6c1e9f81154dea90c35d0220649f74ca0 =
1771130559 0.998 32 0xc249fa82d9d308f501e203b0ac90c2af5292d6c8b3199c8b6c57e529008dd3ef =
1771130565 0.999 17.79 0xe7bea93ce53afeb229468074d4eb3b3a5e057f9bf8c3220c4faa51552b00dc6d =
1771130579 0.999 8.19 0xe05b25639ed29ac82acd7112950483a3dce64e2ee8d0cf17366ffbd2a4948dcf =
1771135849 0.999 30 0xff9d8d7d5bfb53ce7be2c875cc622f4c542fd27999f518a6fd7e3b8490b59ed2 =
1771135851 0.999 511 0x53a6049f421fae9ab1d34ce30ef3c137c12f7f4dd95060e67bbcdaf098cdcf02 =
1771135851 0.999 20 0xf2a725b23c2fd986f95ec79d6c4ec56907d86acc57c0aa88b92e6253b0604eb5 =
1771135857 0.999 71.25 0xccbfa4277032f8c19ea09dbc117e8870fa6af8d0cdf99b548f20295ed1cd0675 =
1771135863 0.999 5.43 0xe964564ee8c38f3adc4481e37577df5ff74ec7eb46de0a0a7078d62cc3b75e61 =
1771136045 0.999 131 0x98bf5dd857e9389804334c4f4d882717c8823fd25cd8db27f0ddf015a27230b4 =
1771136045 0.999 20 0xa1265515849dc653c5ff948b7b325dc19a60c1d758ee722eb62ec399c8ece594 =
1771136053 0.999 71.25 0x894ab379602e6c9c46a5b9d6e85dd4382b84c7ab03b42fb33076e39428d80ade =
1771136201 0.997 5 0x2333a1cd58293b738c9d921fe4649a5f99f2e4d9d47fe342b0a50df7bb66562e =
1771136203 0.997 5 0xe2ed831cdb3d79f03ebf02f1a3447055ad2a642b86e7d4bb36435c81bf930fc6 =
1771136741 0.998 5 0x343133ecfd37f414c22b2fc2f6b0dfedb124c45ef35804fb3d5b0e19bf659419 =
1771136907 0.999 15 0x647ce6c017e0b41c3eca8727f90df27fb618d252dea2819a45164626407cb370 =
1771137995 0.999 263 0x2a2824e669c26cdd59cebd354141439e1d32e25dad15a3f04b525e8de420437d =
1771137995 0.999 1.28 0xb56753123983f07d4ea5a11a72049e49a766f72614e91e0f8530ae2fe289dab6 =
1771137995 0.999 35 0xd09f09e66df3c6025525a6a1c0be3d843067feeccae1dc79dcf06ca794c92777 =
1771138005 0.999 6.36 0xd7f13806cf47f1b0aa1a887f6453ba049ad98b8ffed29774b50e83f56755dd0a =
1771138013 0.979 230 0xdd221e94090d29d446335c578c6960880b8cd4aa4eb147d11c17ecd90dda574e =
1771138387 0.978 10 0x2c47364e462bc30537a694141349bd1f5dadb0708a66b96f723405439dec344f =
1771138387 0.978 10 0x5bedafd45ded06ea82a143a5d66bd02c1860943f94a04bb206f556821209185a =
1771138391 0.9781627154 20.017095 0xd2687b9f6d0a83a5555eaf652701d51125563a1a4a13908da411848b0db968e0 =
1771138399 0.977999993 1.993863 0x6a0ccab06784d87b7bb81a95e64a0a7bc8bb724a2b994d7d28448fb7e905fe1d =
1771138401 0.9779999997 30.030636 0x04ffeca3d658c23533d68bbe49eb80b8d774d372b8ed21ae4267128362cf42f3 =
1771145967 0.984690831 218.0684 0x0a67873d5bd4968100748255e26f7c8dd04219b8ed1177918faac21ef6c0f25d =
1771145969 0.989 101.73 0x061f64f693c360f9dd9a595a27e1243fd0d5871098cd53e7a59d0e302bb7fb24 =
1771148247 0.995 100 0x19ec73252d9e7872644b165051f5ea83a01d5e357cc5aa25bc9deb6233f0e17a =
1771148817 0.998 1053 0x16a40acce35d6c6e176e6770b4189c45db28d726812d4ae7fd236efddbac86de =
1771153219 0.997 20 0xba16db8fc08dc21eec4ed3c9111df9987e1d66512857ea670439a9c18e132d6b =
1771153227 0.997 31 0x09282389560e95e35b34ac99fb197d0c6e023e5c5cbebc51039d25452f1783a7 =
1771155109 0.997 10 0x4f6022bf027806bbb5dc5dc0784ba4056d3a66fc0d645a99185142a306019bbd =
1771155109 0.997 20.1 0x6871d61b54512408343a9ff2570eeb250f1af54946fe65857879063fdfb978d0 =
1771155109 0.997 10 0xcd9af4228a0fcb7f208dc6c6493918da22f836b9053ebde70dac4e27aa89ee69 =
1771157435 0.997 59.9 0xe7b7e051efbd06ad2549620213cef35cc442795f0b1bc33e2776befe2eee13f4 =
1771157839 0.998 12.5 0x4633c86d042cb632276b2e98b7cf80eced15db7d21a4d87ff7a10f73eccbf6ef =
1771160817 0.998 332 0x0332bc2586a8b14e345ac4ed15bb4fc09d5715803530a56c1ef617aae7a38777 =
1771160817 0.998 15 0x1d1e37e5f04712a94f7da311fc8f759df64ea4f78047f2b9a64fae3fd2e92e0a =
1771160825 0.998 57 0x4472f9dac2fb889f746c2b6b39adab4aac3c0dd2c68317c7171d3d4435e2bd40 =
1771161163 0.997 101.73 0x3e85053ccfac7f1c81059abfa2f642dfebed401e25ed47ba0ad6eedf0b5d793b =
1771161779 0.998 15 0xd5672baa9dbf9548ffd19b2dd38138b6ebaa0860882b1cb145dbd3f83405f693 =
1771161937 0.998 15.51 0x21f83292692da6b582611d531d6a4bddca43dcc8423b74315d87503cae2217db =
1771161939 0.998 14.49 0x75b4196185327e3acab43739b8e0a7169238596fff8d72a97495b312904f62d2 =
1771164245 0.998 1000 0xd939edff50e64470e6fbcf4c4292bd62bcf46a4e7b8be33d09148aac486ff539 =
1771164669 0.998 538.5 0x74619af7bf4a24070bf48e47be43fa2b0adda3fdbae93d36ad8dfcd0eafbacda =
1771165499 0.999 40 0x744b46898194fc2022e772c009e5f8fb4a3473a22b464315e3c76722632813be =
1771165503 0.999 115 0xdd1f63e4a96b4fb28f0b861eb6e1bb1323e2b3ec9938e86d7bba0a093512415b =
@1347948 Yes
1770446333 0.04 1.95 0xac0c36f893d540e3e8b6d2d3caa5a705e79bb072a43cd86339dc18a47c508819 =
1770446517 0.03 29.98 0x91bdbecca1621d8774203531642a7b1eb190a48d805f0902d4f2aedc6545777a =
1770446737 0.03 47.05 0x47b19d789dbb448f5c73d8eb5176e077fb99f2d1d37085077e980882c8d39ad1 =
1770446745 0.03 57 0xa8138e48b2c0019fcaf7d58aa957d632f85ce5fafe69d5f053ebcde82a44c5b9 =
1770446747 0.03 7 0x2d36dd1628b1766a965fa6d4f6cf0dbdb86280bc81b11edb53c64f831f08df28 =
1770466975 0.2469999373 8.097164 0xfde693dee6fd0a12ac3a426c9b4f06e80475c086a0beb03ba2f4530b00f7bbcf =
1770473057 0.2209999928 90.497736 0x40752283e8dc54694c0c00ba91ee0152d650b2fb47391e194c4b02edfa3d61cb =
1770475247 0.2159999574 13.888887 0x0f4e4832d18d4f529727fdf93ba179624f938fec8d260a199658d06cd7f53589 =
1770539111 0.03 0.25 0x7d8b0ebebd843c2878d118f3b4dca191cf5ee7224ca9443013137140b97c338b =
1770627921 0.1340751493 149.170067 0x62cce926e31bbe53e13ca554ccc555fb466a1286cb884c58a65d41441c0bac3f =
1770629393 0.1449999427 13.793102 0x76c92bf067f89a78e4575dec0aa3c0ddd3cb348a5d3cd9fb62e4e23a7d63a57f =
1770637041 0.1449999778 34.482757 0xc4486707af555a6c36c358ee7b2566bfa4dedf466bd1f81645b8d43911c42998 =
1770638779 0.1456937296 34.31856 0xb37e3c102431e635e6cf42be762b4cf43310f18cd7d574a1e50b33aad7997ead =
1770645681 0.1477486012 135.365065 0xdb419f1d340f06c85d0374e0994262bc35b9a2f83e84708d2e77844cfe28a0bc =
1770658007 0.15 20 0xc4a8afeaee585819141eb7fa6728c7aa7cf790f84ee31af9b6709ed3a3cca9ba =
1770660409 0.148999882 6.711408 0x8bf1277d4691ead5db0fe038c7ab432ea28b49001b3c49518091be192fa1de3c =
1770665725 0.15 20 0xeb40a5efe38bb35ec7e46525c46f9599dc7ae5c4e75e11d1791df468b43f2379 =
1770667369 0.15 120 0xe88fbc0e8de06c96be2b3a1ef0eab5e43e41eed852955f0bc78873ff1573b2f1 =
1770668131 0.149999976 33.333332 0x5a80c34e65123dc3154a17fc0f5220a31bb69869d7512445430769931bf90127 =
1770668831 0.14999994 13.333332 0x33122e2eee60884440dacfb3fb0dc5614a8ffb04992722c06a961d38f91c81a5 =
1770669733 0.1499998875 6.666665 0xb64d69ddc0a634a44e2d5160b366d82409ecf2e46636dced08099c1a210abf4d =
1770671715 0.1499998875 6.666665 0x0b5a5a5ed82b22ef3019fc619b0fece661439549d666a7aaf72d2e68e7597305 =
1770672839 0.14999994 13.333332 0x325a2acbaab32af0548118500b5863e9d44bbe9d6f013d7ecdce6020bb40915f =
1770682119 0.15 20 0x40084b0db161f989eaaed6b0e9208d126ea581e56a99d64469b5cd10b10bb383 =
1770706299 0.1951381988 768.685982 0x195a9f23085268bbd879ada74eb35b1933be032dde91660b557537777860ae85 =
1770706543 0.131 0.25 0xce5e33930e4d064c7a22151375aa3fa8cdeda280c706e0fed5012557a812a34f =
1770713319 0.4213679446 47.464453 0x3a0db4eb34de05da8d7ac39d5da9e04934de998ae84fe6da5c2260642d5b2fbe =
1770756549 0.189 10 0xe6f91bc5c65898273ef9bdc04193c63533b99f2690c5fa88785b349c9904340b =
1770760261 0.16 156.25 0x1d02e17fb5564d650f8009658b42ca969abe86bb31d5eb275100632193554995 =
1770764117 0.16 100 0xa7f89fc0f14a3718e4d4380a58766acc378630938240a53e0fc6212355bae594 =
1770803425 0.104 13.33 0x2776e7382e6bbe7ca3ee5dfe2b16c0bda547765426811f4f8b45a23336cd08d9 =
1770809415 0.1671566949 59.824101 0xe846f6225ba7d47970c7aa77e514866d451b7091fb739910379260f6924f552f =
1770827589 0.1978130967 25.27638 0xaa7e74e5c8f4a400ecd05c991c0be1c6f1c6efe5e4aa53ec0214c218ae34c53c =
1770835889 0.1949999735 25.641024 0x67ba946dca2007c3c858a3df81e13f9522bd04bb9e959f52381af916b59ab2ef =
1770871293 0.1699998861 5.882351 0x970b974c979add13cc9da66c813ba6ff9b81fc88b97a16dc44ae0b509ffcec9b =
1770871753 0.179505028 60.61111 0xd4ef061f47ab37728fe91bbf063f6a66d97d4feab556db17cb04de6ef3b453bf =
1770898647 0.11 2.41 0x066562f17705b45b86d016e459329a1445b1b6fe6c24a8aace32401e6583fcf8 =
1770905523 0.1769999859 56.497174 0x8c0d1cdcf487cbc1237682a6b98de1ef22ff52c56e75dd696cdb576dcda8ef43 =
1770915407 0.1779999748 28.089886 0xe993bbdb27c8ddcbf90291d28f1363562bdc425af0624a1dce783e1afc9acf21 =
1770930909 0.1085020444 90.49 0xb02931a296c20a5ecd5d50faf1ca127ba57916944cc6a0588cb95ff645079b07 =
1770937909 0.1691542038 29.558822 0x2e137a55280bcc5854fce85ed75d5128d26826c75ff58284f2c586ffc32e14ed =
1770998627 0.156999958 19.108279 0x428eeeba5071743aa47a34da96f8f23ec2f2d60afac4c52039c1b5397f2f49bd =
1771010277 0.1574792843 93.89 0x25df483fc7fcab21280276ff974a4ddfd3db2b3f625c3beb3f9de51b4a21e81d =
1771010301 0.16 27.26 0x9353099a6f474dde80eb5b12e2cea0da6b8a086e8f4041fee804ba37b1beb3d3 =
1771018881 0.1749999533 17.142856 0x2122790cbdb0fecb2effbe3086f204a07196fe1f4eec909d76f461d21c08a4a6 =
1771062139 0.1689998814 5.917158 0xf997ea11412e0673ef6f6a7417ebc6cb6d9f4d31d16fcd30ead33493565a4541 =
1771085531 0.1542927489 129.623713 0x0a5dc713bb5a998196bb1afdd60d0f3065a6731f9a0f37a040cc8e0f1dd12fdd =
1771086139 0.1729998815 5.780345 0xda72267403bb6bdbdf34824d42b4c57cb9a80246678f7b6a8927eda5eae4a58a =
1771095607 0.1699999759 29.411763 0xa4b44e13b40f5af3ed170f7edf7e5efb486266c05af070b3136b0fc1598b2036 =
1771100389 0.1679999429 11.90476 0xc995cb98798f21c9d0f28822f5aa50ed8a3de89a3350a3c62a5dfa6e4c3617f5 =
1771107553 0.2257564719 177.18207 0xe75608aa6a2f2118a67f0dde82e9edca3bf4392696aa5858b270a1a41743ad11 =
1771123149 0.1608948575 31.076189 0xf86b0038c54e94acc5665e35d3d9f78ec4e3965f8e59f50c9ec6380a78bf3687 =
1771126591 0.144 3.33 0x937ce9d3a093d61d9d3a2f6b3040cbed70c6b5bee9567db3efe77a0a35274b27 =
1771138003 0.1569998862 6.369425 0x520e76ae563b0a968e0388a112efcf4718e8f482417b0d433541db0089d97cb1 =
1771149427 0.123 1.29 0x35e158418dcafc9b16fc9ff35c9607c00d013c57932cd4ac93ec4cc1d948643b =
1771149427 0.1499998875 6.666665 0x5eba15f0c785f457d43d383a1c50efc72769e70ba7e77c14a9e2808a9235bdfd =
1771151981 0.1407328834 142.11319 0x7ffbe6412531537b70494e9a6c2b38bef02bf12c7aa38de285ea7ec2369978eb =
1771153241 0.1474774942 12.747701 0xd377be516a1794cfc0c1d76fe270517ba5f47bb3e9ca62595d38ab7bf8d98494 =
1771154279 0.1475188367 122.018309 0x96f2233a7219aee7d6cfde0033defa58aaeb0667fecd5e937c6d2ac5ae72a417 =
1771154289 0.128 12.74 0x98f65a820db7bcb3c444c36507539784f98297ce291d6cae9621ebf03fb06772 =
1771157851 0.142 6.62 0x52d1fdc8371e903918f9cb57daf0047427434112710dbdd910e24e617372967f =
1771160955 0.146 100 0xa74467321cd2ba4d8f8e23ab6cbdc9a2682c649805d39c4f34bbf7993f6c7be2 =
1771162689 0.1379999714 28.985506 0x7470bdc1bd7e072c63a3ea82cc9b33ed50a3d698055dfd0332f00903923fb4d6 =
1771163001 0.137 28 0x2301c64f595748cd9934f8ffbcb2fc6dbec0103af37feb6457eca910b2a92ea0 =
1771163217 0.1349998906 7.407406 0x12012ff96659e35549a2c96b4c7e5065bc550888241de8a2b8b738d66f207808 =
1771164835 0.1389999422 14.388488 0x3ef0ade7cced3e34b9cdccdeba46658abcae992b4c76f4603ce3cc3ffd266561 =
1771165487 0.139 27.08 0x464b850d8a7e1527367bd89a7359d1178938503cb63728e6b971de5c6d4ff3a9 =
1771165491 0.14 39.84 0x2d9a2fc6b1b8da1598bebe5a6fa5cc034c5eb491254614e405cb7e5b30205a23 =
1771165497 0.142 40 0x0f7765a96581b067923f15f1f8c6b79cc37a7b4c0cfeaf489a6532ea3b7b6df3 =
1771165587 0.151 53 0xc707f9f0bf2be8a38dd75ee33a90b6ae0b18454f5b08b8ae3444741153f9dada =
1771165671 0.151 20 0xd203bb8cc7f2e979c1e555c22eafc8683c732affafc6157d6c7731a3175e6c2c =
1771166181 0.1509999937 132.45033 0x14480aa65556402c5c63350c41f9a2e73105611e43ee7fe48befd282bac6e240 =
1771166491 0.1509998845 6.622515 0x80770b2fa4c0c3c30e9f6ecf91d080ec550a0e360f11c33dad4de3dcb8e90519 =
1771166681 0.151 87.91 0x2a635e7e6783d20dfabff7db14009218b4a99eebf36c1abb904f1bb679038606 =
1771166865 0.127 6.62 0x0138fd00f55d91c06b265e0ef9c2802541dcdbd7d17a22c91198939156b62620 =
1771166867 0.1529998925 7.189541 0x5a96a6af6c9ed0501c19fc33576a2426c2de6c8d73c6a5b5fa672cd85d459fdd =
1771167677 0.1595387057 472.2365 0x827770f0c40d137dec5ebdf7091e42802b1c3f94857e85863a8fecfb09f44206 =
1771167679 0.129 0.62 0xb84badbac7e76050650f2473e102ad6753617cbc38532286ff5b4d8375bb7c8b =
1771168951 0.1359998858 7.35294 0xfabdc8b2e8a671dfa436267524d5e4084d21d32ef4e3dc8dcd1f8230d47b658b =
1771168981 0.136 46.11 0x6bd57020ec83c02823ebea55b59ca853d757835db7a9e5e2f932e76b74b7f96f =
1771169037 0.1369999777 36.496349 0xd8c8166749e57ee2d850ebd23b96e4b372fc732c85b6778014eceec09042921b =
1771169039 0.136 3.47 0xed2243556b9048826bec48e19e6cd0525734daabb07b193e1b6e3768b23fa473 =
1771169039 0.136 5 0xf2af9923f481ae690d60eb7588b1b54beef36f5ad2b05bc303c7f2acf83bbadc =
1771169535 0.170999987 50.877191 0xbfd50b3a21553e8c718b99c70e7798da8ee320fbf512c8877f019dce4556ce45 =
1771170007 0.172 87 0xc8c28052c854882f1642a20045f7a57d3cfa1db83237b12c599358aee094511e =
1771170009 0.144 3.09 0xeff2afefabee90eb2abd32f8f88c8b024fe5e25f98b92a429f2533ec35f233b1 =
1771170153 0.1979998432 5.050504 0x3ef174b6a9e34c877d176a3604281e034ca907a177790bcb0aeb9ff1cfa46858 =
1771170343 0.1755918993 28.475112 0x678e26f686e2d7c32ab6f762991c3ce3241b231b4ce8db32dc4bb48fd6ee9623 =
1771170353 0.1743375174 286.8 0xe55096d6b438ca8998c915cda24490775f4f05e60ffe61c3d215c5f576a09ea6 =
1771170479 0.184 9.65 0xad94cb431ceae443101aae384d6037fd38c93623f6850145cec46ab453d6bfe4 =
1771170619 0.187 9.76 0x499089f4fae335c7465b764facb1bc961a82352a1051cdf4835c4416c53879d5 =
1771170811 0.175 10 0xf56ec925c1bfad172ef615a73728ef752c580c3ac5b570c244dbe89a4f540e68 =
1771170845 0.1829998798 5.464479 0xb6bb0aaed1f2e0dccd06bc635c19c80caa417312289662f2223858468c2bf6a3 =
1771170973 0.1771064319 11.292639 0x6af234fe527bd6ad67ba128e6e516446637cc84c3d5d94316f1d557a37881677 =
1771171097 0.129 5.67 0x18877db70666f77c4cda78f6d96095327dc1db916ce6b07135cf8582cf6278b9 =
1771171129 0.148 10 0x97468aff85b42c84b68a1a22dff7479c764b9c13047c0b9aca9b544eef7430d2 =
1771171129 0.1363076923 13 0xaa90e20a051c6a4bb4570dde0ef22d35300518c488107e2249657e1e29ca92c2 =
1771171303 0.1609998681 6.211179 0x3a3084d840404c499d323ca277cf011592944bcef6a22f09bb0153c6a6590fc2 =
1771171303 0.132 2.36 0x78b055f7ce530ed11514719db6d87d8961cf1703116ae9111be31e8385f6da07 =
1771171307 0.1626316333 122.977299 0xb65aa36945f0473bfda24297265ac76654a0f3ec08ab27b35612bcde071f1479 =
1771171357 0.1600194808 49.993913 0x1a2c0b30753d10e1c81dab293b4e4b1c34cb532290d5c97db78a4ddfb12b980f =
1771171361 0.1355287061 11.67 0x3caa8d26ebf9e2a0fa7337670970144998059f23e8ae1721651c491c0c7656b5 =
1771171369 0.16 6.25 0x998518efb8fd188719d1fa3fcfe65d0062f5e74f1415a3d9f77230eb3313a86a =
1771171499 0.137 13.79 0xaf04197cc6cfc5bf2f68908ed4301836a1ac6082b2473109c208e052fce61775 =
1771171573 0.136 3.52 0xd9d7cabea6d4de10d10099fc32ef8faa833e46ad1c0566c779183209e3cfeea4 =
1771171749 0.1429999488 13.986012 0x9e4d26d87da19e81f77e1f98d4e14600bd403e2742381116024e61ec9711ac5b =
1771171773 0.1431115523 69.875554 0x307889182fafa2ea52414ed7dd487ac16a903359649b86b42365f7dfd9a34199 =
1771171859 0.1619999756 30.864196 0x06d7efbcb7c16928714fd35f9f2fe578e8709bf3a9f2b665d01ca242278ed53b =
1771171879 0.1805486147 55.386739 0xbf210a85f8483168fd724b5c9405ad53d86b8f2c4b5a0b10590f964ef0f31611 =
1771171979 0.1649440598 369.822345 0xa3de57030aac4b0ca9d17b38bd07fa79de508672a92143c0ee2c6460eb77b904 =
1771172049 0.1493500256 33.478394 0x6bad404f6b9d93188a49249a0b8b3ee48e4b80a7b5674c6516c3b478ca5a0f07 =
1771172095 0.1440757159 6.940788 0x9b15055a13ed753d58b604ce5405a635a147d6512882edf47bf2737859499997 =
1771172113 0.2161923397 74.008168 0x3739d273a970c7ed2ab9d0bedae3b26230f0404313b9f24cb720b85c9e8b4521 =
1771172291 0.1777923307 84.368088 0xc9b1ca1a82e3b4a020744cb29c833cdcf502fdb7cd9bbdacdcdf41b50c49cbfd =
1771172371 0.131 0.32 0xa02a2692139fe1f4c04f637d957e74510510c980eea30ce2bff5f90a608aee7e =
1771172415 0.092 6.25 0xa18538d5778f5a9fecaef661235fa51a5f42a5bc17bd411f800cd8701becca71 =
1771172543 0.1610000001 61.863354 0xcedb94147dfe08c3f0b02f5cc6425a1a1cb9fe32693e053ad5af4512e375de01 =
1771172847 0.133 56 0x912570be7845aa03a16ea08d60484add5376f75f4230db26e6ab29d473803a88 =
1771172847 0.132 13 0x9d0f188ffc510e2534fbf1b33b90a1e3788b931b42b656ac4ca78a4b3aec86c0 =
1771172849 0.133 5.67 0xe5927367edeaf6fd8c5f563a7d010845aaed9a4c47bd7c4bcb711e9763ca2797 =
1771173047 0.132 13 0x18a6c07780db5507c25d1f596d2ba06f9c1aa471619b04c8728e8a67434522fc =
1771173251 0.132 0.2 0xf4db9ae06a27908e2de4d6a585e0b7dcae6ffed4e8da92f6ad34fb7597235a8b =
1771173303 0.154 20 0xefa0be5ccb65f0fa140801acd1f8af45e89b2f20be65bbb5dc947d9aeaa5d8ad =
1771173359 0.1946099476 646.99 0xd5cecb3fa5dfd8976dc7de0ddb0978b6a1a7355fe237d789327b623875f5760c =
1771173363 0.0950024272 103 0xd597cda179fc51d171372761f8b0702005f5edfa2c58711e0ecbf4636dab2e04 =
1771173381 0.0915666289 132.45 0x4f3a27197a1384b4691a5650c784709259007f67fa6412832d3738620bdccaf1 =
1771173537 0.101 45.38 0xb131bed84623c0e4302a23aa53f76fc15173536bfe7471d7d456ea0265556da6 =
1771173559 0.1719999432 11.627905 0x59f241f1073451c4649ba694e5345ef21631d38ce589817f48fc7c4ad6273a74 =
1771173627 0.148157658 120.07 0x3018c349491620dbf53234521085d886c51ee492b37488d5a8c2fbf719e2af18 =
1771173735 0.178 12.88 0x8972eeb4748d778a1b70487518199232a6c37d9e6c8c05d41f04572b5536037b =
1771173749 0.179 15 0xbbbf92cac433a3a8683ca498b02393becb17fa93e9a3a79e2029db862999f78c =
1771173751 0.2489998289 4.016063 0x234e613c34e8915690658398707b213fab8195e5036ebd5e6759dd91f51da0d5 =
1771173801 0.2493351064 12.032 0x8bf91f9f919db69ee4fdfd74536d389bee799a07a6d207538c24c4abe17d5504 =
1771173841 0.001 69.87 0x2aa2a57e99338eeb3ce7cf74ba3db6ca15808f20ecd9d785b3dacfc2057c7d8d =
1771173881 0.001 850.11 0x4e4a3c64e1b24e339e54d2d38af8bce210e24e169877878a892403e44aedfd07 =
1771173883 0.001 11.9 0xd1c83e87dca40e056e2dbb1910f5e041e030a38d1df255fe4be6195f2b780426 =
1771173937 0.001 11 0x5c24ce8b23b09972b522dec7a75f24de0ecc912240cf4e3e7ffb521c08deb3b3 =
1771173981 0.001 2000 0xe95f3d2dd70a81d1215293a825271a79f69e86ad71e6f50ff05ec0e36f74e205 =
1771178529 0.001 1000 0x96c0309caf50f1cca2c1215976b027c2d7afa08352fe00b6a3ce09ab0ac11d1a =
@1347948 No
1770426179 0.96 18.03125 0x891990526c53714ac99adb1e214d86b949357226b4cf5287e582bbcd09f881d6 =
1770426179 0.96 10 0xc4c1cd4bd9e9005fdd62a983e5c2f3eaf7e94a0c6b194c10fb69fe087dd823ee =
1770458431 0.97 10 0x0e20e628981b94188d6731f491faad95fddb3fb32f4fffb32a368f7c3367601c =
1770462375 0.97 7.04 0x8d5b3e0e2336b7c62637f98edc16023c382498039e2246b5c47134a6c4bca7b9 =
1770462393 0.97 5.23 0x9063be225ce0e4acc54e6dd2c0a8d92178fe2071e927b223b9f312c836dca51a =
1770713725 0.82 10 0x26e8f7de161612b3d2502c4f4a3183c2846fc373b89d4e54b7978b79c297adf4 =
1770713725 0.81 30 0x7f41f02cef3389406da021e3cebff1e25cdc199431b83814f7e8d780d78e63bf =
1770713725 0.81 23 0xf9694243b23fd296ca57a47bf8ead81c7a7a5faf61b4de70c09f45d6e0d2d09a =
1770757167 0.869 6.46 0x6560e0077c16d0a2835c4615c6ee0d25b202d1da6fb0d0abf6ffeb89a56ffc8b =
1770757181 0.87 10 0xfb28712e9c004d4c6c289d1ca9711a1623315f1a1880f097e2f35334396c4787 =
1770809623 0.807 0.8 0x69b39d74c6c6dd44a76a736d14578ba98eb05b5e860683a749b14de2b62a1e41 =
1770935453 0.865 5 0x040e15160e756739202f7b4283beaa2e99b30d2f50fbfde68c1e7b4f97ad3eeb =
1770941195 0.8675 30 0x8da3fd072c0851b52a193c565d4f002cb26224ec1ba458b2cf581ea55a92c744 =
1770941207 0.8688517895 71.25 0x1b3cf72dd5e9ed95845e4c352d8e0747a6de4e5a85c785fb9ba42d6c40d768f8 =
1770941221 0.869813193 71.25 0x28ea78303d74d9bafef300fe5c5791c17f21dfb62530dcac25411dc867c51008 =
1770946273 0.87 5 0xa22428f9314dd08d00926ae7ef78961987c7a2c624d8a6e3f4f2d85d8ec89f10 =
1770950449 0.87 5 0xb0c772f2a98f05bced34dc1dbebd3bbd0da39aacf8628d711995923493616ffb =
1770951707 0.872016 35 0x6ce96f4b3ec6230a31d94b4e32918636f3de6b87e280ad57ef9a3c865e867806 =
1771064729 0.89 17.61 0xf33fff4aae9cf393fd3cf7c34725cec10faf90a215c69fcd1c28ac0377494f2c =
1771065747 0.887 20 0xb963a7d64b9163a4879975e3c65089061c2175ad6caf59fdcf17044e50f63c4e =
1771076085 0.879 20 0x169137d343ff78657a458264ace6e2f6b2e3dbae79a836347ecdde9c3e1c7fb8 =
1771088985 0.879 5.56 0x5d7d9861b86c3fe89dc5176261fbf122f8a5d87aef163eb688b3913b4ed65942 =
1771089711 0.88048 20 0xfc848e2cc4bf6c05fb3de75b645f9a421cee7d92db3d15aede95488b6918de80 =
1771103743 0.861 20 0x7fecb611dd93e2631515c7f452f53349d40f542ad12dd828cfdd43e5ef891972 =
1771107439 0.834 1.9 0x50c3d2cf75456799f7f83153abc93b9b9992e37f1e4a87f671b9e474e5cda125 =
1771108623 0.847 56.53 0x4b9e723c4b2205c6feacd42cdae6317199866358bacc271769c098165259f258 =
1771108685 0.8449655172 29 0x4069add67449ce6e68db736f7aff01f76d9b58ed583a62c7f4b98f9213908c3a =
1771108685 0.844 5 0x6361536f7648e5f550e08c5c9fa94a4f7a16038639733ddb573e1e54c8c01903 =
1771108861 0.842 5 0x758645a24ed445071e0d7a5c0803caf9b8334070b3485cf5d9fa5582f3f80eb7 =
1771108879 0.843 5 0xf16b3395b551a39ec6fe8596a9bf1e217ad4f8490197147b149c827e07f03fb6 =
1771108881 0.845 5 0x5465f20452836e8090bea6c245bf2ed6798dd277e55fb92de6456ee5aa7daa22 =
1771108903 0.845 5 0xed6c75dd6fb7926d35798b4e6106d542b630c0c94888ef5c39ab4b268b4f4fb5 =
1771108905 0.845 38.09 0xba8cd05e9a8bb52c8208ad3bf2dfdf1e6f4c7d7201b7aebe945421db8c126444 =
1771108919 0.845 10 0x35ae0a26773867ed8405ecf215c5668f604aaf13b35249028bebe89b072f4188 =
1771108923 0.845 89.22 0x63a394a10a92f22b4d4f740ca51c3f9df66a21436bb025cfa98d04ba7a904089 =
1771108967 0.845 35 0xad6cc6312932f35be638e8901bd6bfa9fec10a782a0168b0e6e0abb64cfeec7a =
1771108969 0.845 15 0xe000a0c5156a4cea654708b20d6059b7aa1b45be7b2e822e6a183277d7e5b0ee =
1771109105 0.845 176 0xf74081e0b3d98d41d61dec6bb39079e7442617bc7ced56eaa40ab67eac4d4d13 =
1771110711 0.845 12.59 0x2403d4952809b621f7a59c6d8daa4443d8ee908cb5888763861da1604047714d =
1771113111 0.844 39 0x8016a15de03f119cd7f92c8f5b608fa872c278825b86bc3f3f1f5d03f8d3b2f6 =
1771113189 0.844 10 0xd3ba25a2951a253027a082506552f2cabed9cc7a2b02b0f0e4d9906e56e34e33 =
1771113197 0.844 10 0x0dba3e55d5df329e48fdb6721d303fdeb0ca5d5281bac96678b89118ac11aafe =
1771113205 0.844 20 0x385b004db4f5fbe774d604069acd2938b8d10a51b486147d8ae2ad6e5e821f53 =
1771113883 0.844 20 0xc67c9a5bef67ab4a08935fabf9b64ae52498123ab0a6f6521c97a441a89166b8 =
1771113895 0.844 16.21 0xa990fe09f8dd2f21eba0774c133d73f85930c90baf9422105fc309fe0244bfa1 =
1771117403 0.844 22 0x16b499900f57eeface551b61fa18aa47c3b89c788fe4fa5c6dc1696763650835 =
1771118387 0.845 50 0x7219c047fed7a262edf9a206b6596ead9cbcc5dcc3f7c7e3c09c720ebc7ad4ed =
1771118607 0.844 31.6 0x0b209eef0df05bd5097b39a6df17b6aa066a78fcc80080ee8694ae37b7049103 =
1771119801 0.845 55 0xd63932ffd8e2e3356b79aad733ff38b3fc8f439c813b2e379d5855203e259571 =
1771119807 0.845 45.73 0x1013a36ee03df99dcd7e5ad9ece56ba04fde1b1b18042e0d017217db102bb19d =
1771119901 0.845 20 0x03b128239899b0fb047736e464a38c94776f3b5300941769dab28e975d6467b7 =
1771119901 0.845 100 0x2498960c3e52b81447f71a3a9382584ac3734e6bfbae480c6690bf4f1898ef37 =
1771119901 0.845 5 0xb3c4d3e2d67a98ab767c7365962694593407c664bd8ae895ab2167498719b11a =
1771119903 0.845 50 0xf980a4add1ed4f11dc47db6e6fed5f093f64566eb6006ab273a548b818c6a93f =
1771119905 0.845 28 0xa045f21936ff13ea4ba627fc10f3385ee228a3415b777817e6b40240cf20aa81 =
1771119909 0.845 57 0x6b0ffab278156d44e2b62ff373ba3a31948d47666753e4fa3ba432ef63b22a52 =
1771119925 0.845 5 0x0f8b0002b4c943e3a10138b8f96a261b1f8e3b1565ec34adb593d5a888e99edd =
1771119933 0.845 170.37 0x6985e1fc8f28915fdb463dca9cdd6079a165f49d07b20ffef3f26a3f758c4d14 =
1771119971 0.856 10 0x0eef6afd0b7b483bb9f52b9ae718f75b45a67f8452ba736339b1fcfe78d4a6ac =
1771119981 0.856 12 0x7a6e77515adb89f8425366bf545b5c264f5dac3ae003726dca9bc3269d1e81e3 =
1771119985 0.856 6 0x73a999e3afdb41684eb69ccda9be58b73b434a1be935bc5e93dfd9b630bea015 =
1771120137 0.856 5 0x0f3ff5c0c32163aa5e4adcc484eb247dc4c70e846231ed90aca28ea459c4d5dc =
1771120137 0.856 5 0x5b10e8cd7cea343219b70c8b9e2818bb3f387e720ce56de890f3f58abccf8f7e =
1771120137 0.856 20 0x801a95b4079628e9589f0f4e01407ed6a77b6fef42594daaf713c639013cd5f2 =
1771120151 0.856 5 0x6b760ba00ac82e6f7f2deb0af88e87dbcd7b3d5c553822bb6273e19e333a01c3 =
1771130469 0.872 10.94 0x00e5bf75e9aa5ea05191ec70000777f86bbce7cf1447a5f2675222a9f0d1539b =
1771130527 0.872 21.22 0xddd7dcff2965c49af1e7a2cef31c5ca5cf234d91b759edfea47af285f9492c92 =
1771130545 0.872 16 0x0f9b3274ff6e48c4f3bedc39a6174baab9783c4494669033bd3a8cc4cedcb502 =
1771130547 0.872 17 0x098424736aebe8f8f7d619b24efcbc97704acf694234252e997720fcb7e5cf8f =
1771130547 0.872 5.97 0x5f1e9008fd3253f1df4ca2e39a701c4ba1d91d0069954d5154e070903363243e =
1771130555 0.872 16 0x552f6b8cf31b5a67f87aadad33e4728384a97fb9f7d920b60fde03aa7abdad50 =
1771130563 0.872 17.79 0xdbb76b5ba2264a2996c5a25e1215ebdb985119afaf94b2dbda89e3d1c6827efa =
1771130581 0.872 8.19 0xeeaa01642c669b0b544aa9c6b007a552f91508d2494b2a55de8cb6333e04927b =
1771135849 0.87 511 0x67a26a8f4f2109f02a475d96fc4d5b4c90f2615ca99396505e38fc405fe00b8c =
1771135849 0.87 20 0xc2d67d0944da2533234a288752bc71141e0296db686540bb1ec8834afa63c812 =
1771135851 0.87 30 0x813e5fce01beca40044baf1cc9e2b25db2bd32be2bf23176cfd97e35fb3ad44a =
1771135857 0.87 71.25 0xa328935339f04367020e0be37a0175dc3b2abfab7b25cb02578b643183e3073a =
1771135863 0.87 5.43 0x1b01dac2be973e4d74c8c92e6d77dc6ebf62e6795081be7b48cf1c0f70b18b91 =
1771136045 0.869 20 0x016c6087c40d65e44be00b7a57ca250deabd9406a530847e2100ed03c8cb25b8 =
1771136045 0.8696335878 131 0x1018d00d75cdb85627282f646d18b0ecb5046db8888ef44ca1708080258968c5 =
1771136053 0.8685263158 71.25 0xb28203a53a1dcc30999f3ce428122fe6553c52c98a7ebd80094132128244c711 =
1771136201 0.869 5 0x7d45fcfdf927f822fe76f01850fb2f703e60d79bb57d76216a585326f513a299 =
1771136201 0.87 5 0xca27cbf9da0754c3f19066ef18d64823081a404efa7f05e11f6e52e8ba4e5cc7 =
1771136741 0.87 5 0xba7fa1020aae9677dfeb27562276fec8b15d6434d8e3a4d6d06f6facac033bdd =
1771136907 0.87 15 0xb90d1b0fbf09fbe32db964149533894a4b9c8d765c0c023f06a2e2874b8d42c5 =
1771137993 0.869 1.28 0xccfc6d4e3499243e3c1b247d15b1131c1bb08f426eb91b9e1335c1c46d69b83d =
1771137995 0.869 35 0x5161492625d4b029a445d54c1406e3974b16f72659dd775dcace7a6733e9f157 =
1771137995 0.869 122 0xc1fb5e0f85e92a130371a7832d95c74fd5b61ef25810fbac817be310f41f5b23 =
1771138005 0.869 141 0xe04fab07ecc45a3d987251642b791bbb2aa182fd7a73b67965a61b2ddb6db467 =
1771138387 0.869408 10 0x086f5f39eb86f0ed8a2443cee142d86626da7834f384d1e0254813d5dc9494b3 =
1771138387 0.869 10 0x9d008a2837ae1e6f17f053557023547a7707eb87c67d91daf77ad81d461dc040 =
1771144591 0.865671603 23.103447 0xdbdf20fffa5676f1f7e6abfb3f9f603c8463179f9c1d5e4829d8cb9f7b63e20b =
1771148399 0.868 50 0xa1d771def5fe053a39129f16cbd783ce27626663ef707ee470cc99b4250dfc2f =
1771148817 0.87 288.84 0x21e04bfc8022e6550df215e5b0fbea5c6c3f3b2197f475aff02f8b1c22638248 =
1771153219 0.874 20 0x39e11a8cf1c5a4552bf2cc630326f64824e9cdc22d96d9e56c5f7957c7a4814c =
1771153229 0.8737848387 31 0xa579907d60b4ac436e82609e24efb621f54d6c26941c505ab75e829097247f72 =
1771155107 0.87 10 0xe60e4c4e8aaaff540a406ae99c1ee53e107bb3aeffc51d4173de774531370e89 =
1771155109 0.87 20.1 0x8074de235fe4dbf6797cdb81e94540aca455ff141b14c1ba68093170f0b8b441 =
1771155109 0.87 10 0xdb25981b1c3bd6589d93f9bc649dd0693639bf4d3f33218a75bfbebac526e67b =
1771155729 0.869 150 0x328eef2e666c26dac845093ce68aee3024206bbae8d78c737a3ce6fcdabf8769 =
1771157435 0.87 40 0x4c4f8c2f6975602d3bbb7e413a4b5ff372a0cca063e3247103ef988d8171083c =
1771157837 0.873 6.62 0xc311e828128dd4958766c6eb4fb9a12afb3f134a68fb9bd59a52e9fae0977d62 =
1771157845 0.874 5.88 0x117d510be340cbded698060bbf918d13d04ee79086e737ea430815d893fab84d =
1771160815 0.874 56 0x73a708dac1f7c01bf784fb44bffaf150b1594f87889cf7dcc1b2ff5863e51def =
1771160817 0.874 15 0xfc68a25a06878a74b6cb060cdffc4ed8b7af6e45e7e0ed7c62e06f413686fbdc =
1771160827 0.875 57 0x4a2217c79fc52c705453e8a6dc1916870d81a3f5b985fccc3a247547892ae90b =
1771161769 0.86 75 0xce77038d036e219dbb796da005bac3385cab407e0e76abfa7932bf42efa0a1a5 =
1771161779 0.874 6.67 0xab67c820517dfb5f17479fda31a14a806d2149650d0b82f0447f5d2ea3dda38c =
1771161785 0.875 8.33 0x2ea6e9c16da6dec8fb896c868373edf1da31da9311348c1ce85cf186989c5eb7 =
1771161937 0.875 14.49 0x253a2508a1696bf20ad6a110cf65d562f7a98cfcfa461735a68a5c3c07912bb4 =
1771161937 0.875 15.51 0x2e0fd9f711c6b01a574ab805c19609e70462f454db7a60bbbd6305a773dba53c =
1771165761 0.85 13.7 0x8e7fd2d6427471e3f530c54b3953e171177648b913670681a610b3de5611f6db =
1771165763 0.85 20 0x810d724ab6f656c1ae84f0d5293564689b059a46063ba554327d6a05766613c4 =
1771165777 0.85 20 0x8b2e14a42fcef48fb32ef91633472f14d6d0609d3ac428215cab9bbc3d0470e4 =
1771165777 0.85 26 0xaad6d7cd75e9869b05f6455873c0dce746b9f193e878c799f3016a8d5602b56d =
1771165781 0.85 14 0xf86a0d9f8ee3c261450f065dabe78582d90acd02ef73a701d0d3238213638810 =
1771165899 0.8546428571 11.76 0x899551539cf5cb32c6ea3cd6bd36e2cbca2aa161b212fc0f01cbfe20970dcbae =
1771165905 0.8661394558 11.76 0x0b9ecb490d796b4c20e697f96a16d3eb8d661d1fa90f1910b30003ce64ec2d37 =
1771166201 0.87 20 0x3b4699747c1d0603d75caebc1cae12c1d707572aa5f1c3c977f8e2a30915b4ae =
1771166483 0.869 7.5 0x1842fec46044b78741c61e8da48e83b003c904d7d685dd57e098e2f35647c729 =
1771166735 0.871 95 0x36d85b95a4103765d330c80c755e3bf756e61e55a165088158e02d2ce5d154b4 =
1771166917 0.871 41 0x4cd76bf024aaf668593e37fd5cb935d1f4c3d96cf42324ac0c95ff74719aabd2 =
1771167003 0.871 15 0xd432b95eafc86dea7d0866fdc9dd1966f83a4f53a17cf81d4d845f0b70a6b9cb =
1771167003 0.8706795 20 0xda53a5a50ff3a4e74a3a826ee9a6cb1816a79f7f06829bea917164a78eac94c1 =
1771167017 0.87 5 0x2030bfac9318dcf64176a5c4f3b741ce6071aece3b8e088fb63d6295ee13942e =
1771167025 0.871 0.41 0xb68946d781f12715df5921ae886f8d703828fb1df3a19b9b5c1af21326d44bd8 =
1771167025 0.871 40 0xd794d7c10f37a965129a10fbbb7def9c41c2f925638ee9321f2e0e9287ddc169 =
1771167025 0.8724597753 29.617409 0xe6d4c62701efaf8ac6c255f93bd3ec1691caa8536b2ba0660d16de5addf1e030 =
1771167675 0.872 8.47 0x14ea96228cfa0191caab41d9ef35d3f0808980cf846bff16973a6782873463f3 =
1771167689 0.8693149606 127 0x3b04ab133660bd763bb7378759c5947d081f492bef42f0efbbc0df5a04f35351 =
1771168981 0.864 531 0x3b7ecf614abe778635e01dd30f46bc2812f149492b46a186e3af7c573e0975b5 =
1771170249 0.8603541618 42.41 0xb4ff9e3ad0968b5d05703f1fa28092cf6ad9b8f8635b560907efd14fdbab4f2c =
1771170357 0.863928861 135.65 0x70481eba15ace595de196e38be398e418fba6f28ea6ac054f333ed9f39d11e3e =
1771170417 0.859 49.76 0x624a27cc545f45477ca77b99b40cc1b72807c3026b9e80d36847c2b0cf470447 =
1771170719 0.8683321333 75 0x83ac087e7dab236ce64e3b43aab4503c33b42c9fed57572c9bf15996606366fc =
1771170721 0.868 5 0x7737aa65d7c2e8eebdac8bf78a11bdd3552bc8aa339d3f84f1a4d4f29dc7f210 =
1771170739 0.86 500 0xea9bb0967c2f6f644e0e504811d50daff444240759cc751f245af51cab458571 =
1771170755 0.872 80 0x5bc444e07588e624fab37ec85d31d2a61f949da4f2d008bd97428bef9f3198e1 =
1771170813 0.825 32 0xffd9a9461d7ca7191e2d3f2c45a123387413359c26d493d6d93c5531bd146000 =
1771170835 0.869 5 0x3174a1b8891079eeb066c9101059e63548645e01e15ff1ece9287af5aedac0b0 =
1771170931 0.868 10 0x7246d575a00b7daa9f41324233a81b1ab40b2bc88dd3cd87c2abe378032bab86 =
1771170993 0.869 10 0x2619e94e4c67443158396fc60e3b585ca3babc2d7c863fb4e6401d7826dcd988 =
1771171053 0.87 5 0x17a608bcf20a8277189287281e5067d8ddcbd3d981fd18ce190f0a4b35811290 =
1771171085 0.871 5.4 0x1001ddee1946d8dea23c6bf88bf78d418a3219d23b07dc74a1b95a54b3722e52 =
1771171095 0.871 6.6 0x45a97552c86445847c45f50971030220e0eaa15b5cf80fc27a9e0477b0475588 =
1771171097 0.8725520346 231 0x938b860b8896c36cf0c991c67ff896561edeaa90802b21c395be44b120f7e6e6 =
1771171129 0.852 7.6 0x9bd67497315257bf076576193889f9e5ac5be2fef99dce9d926d57b16d057eca =
1771171235 0.869 2.29 0xae5bd2b499e9548d026f6f915b517bcb1baf6dd0e7772cb7c7e552e4a1589c79 =
1771171249 0.8673760976 41 0xb017c31b7ab2b221a90a9e163bbe3e6ffb1b77bda132233ad8953d54728b162f =
1771171339 0.864 5 0xb9114a7dbad27b5a2f70013ad56a76a04568119e27022e564c2e3b2407e04a33 =
1771171339 0.865 150 0xefb95db43038638dd9ed34ca02156aa3ff28232b519e5b384267f01a75514f15 =
1771171341 0.865 30 0x2cc17ba604e0dcc6de63c5f31d7a819e14e90871d81d24f77d1c9e759c155f67 =
1771171533 0.863478 50 0xb7c86f4aac2ab5a17030b22c4f4538e3ea97ae0c184dc1900d439f972dbe4522 =
1771171563 0.864 21 0x1eb1bcde4e447432876e68d7c77a86f27d9ab09ba04f7124b5e53f1096d83a83 =
1771171633 0.864 5 0x09a8606cd49903b49af1bd9e674e5bf3697408e7a7cecf91c6808fddf2c2b6ec =
1771171647 0.8658336842 19 0x9dfb48e59e6940e7c5432a502b3ff2fdd4168b7676b76d7efa01873a5d0041d8 =
1771171647 0.866 70 0xb39eef9f6b1038322d763a2d8607e1a192aa4a28a2306eb9409ae7af3aa8bfe8 =
1771171663 0.866 7 0x64990ce30990f74ec8a51fe998940c0f1ae314b63a6b3222eb0b57c3a4a6a19f =
1771171749 0.866 20 0xa894a27849cdc18572c18e95e39ae3598e2b31e76906587ef98c4ae0918b3526 =
1771171749 0.865 30 0xbdaa012e3680a9f3d8ee200b3401a21ced7ab3aa1e0258f18d20e0a5a3c8e79f =
1771171763 0.866 3 0xcefb0ec4011c47262c582a391c90da9c73db9544861aec2d0dd09a33c36cfb6a =
1771171927 0.864 15 0x316aae3399dd69874faa3d093b83699b96beebb15929c70c5b4aa43a0b5262cf =
1771171927 0.864 15 0xae7881fc42615fae3acbe2dd78593952d5db43ce85c715f9cf574550518eb1da =
1771171965 0.8692974292 985.68 0xb09a41d54bde5bbc6329e96f9c57001873a3a24ef44c568f04f8a21ad9bc9faf =
1771172221 0.853 5.84 0xc92448fd28ae5b776f328a5efa6c8da44fe606aa7c9b3c50754192056d383df2 =
1771172225 0.844 10 0x73664faa790f23e227de43d464cd4ead5cbf7f2a6b3d0950146865bb3d71a060 =
1771172237 0.8469999819 6.139313 0xab6c4c033a015f88629138df6cd1253b77be61191b0c53d5e732de8e776547ac =
1771172247 0.852 11 0x0fa7132f1f9d27a040a2f61c030e2b5efc127b50a54659f7eeba9822d6419b0e =
1771172249 0.853 18 0x4fde05df22300d8e221b73aa828fbfb5c2430226d72da57fa81063fc587567b1 =
1771172251 0.853 4 0x6c0e744bfe1956a901f25e2c7349f9bf1c4182ad1d8fa223f7f11aec8325d75d =
1771172253 0.854 5 0x9a5284ecba2b39bf5bf238efd9395f76193ad7fdcd4d697e791ef48b94a4ce73 =
1771172253 0.857436225 7.020928 0xd231bb9019c455b113de1ee3964999cda7d0b0b51757210e3d8c0b574d098455 =
1771172261 0.853 30 0x727e595da4531cc39f201d437f308ab68678342a832a84429b6b0f5e93c966c8 =
1771172261 0.8562388889 7.2 0xf1bb1e78d777b0f6d14fa7d3596be3c55a2bb9e0ece974a90a1ec25a4f12132e =
1771172295 0.8674230769 26 0x033da0c499aa0054289aa11b29de2d4ca27945b4a2f77626421476beaf95d284 =
1771172385 0.8691852159 12.04 0x8b7e6473445ec659eda46c804ef0b3985cbc88217ad37c25dd170804691b3a68 =
1771172405 0.8729101398 3.436773 0x8efe3c1f663a49a874df998240aeba1d2b797b82ee46b8049eb9d8ddabcf3c65 =
1771172483 0.8829556757 37 0x8c74565180c56516f6e127bba5f2116fd0f6a6e318fc957455cdac50c5abbbe3 =
1771172635 0.865 5.99 0xb575b7ad0af1718d0823a4ea90d8dfb0e1b5ec935fd4a0d340bd661d16e57c9f =
1771172641 0.868 10 0x7359208fc7f7cc0919d6033810f99600c5fabb639539de747824499fd74265c5 =
1771172853 0.867 50.33 0x6ce83c21b328cde88ac8b95e70e5f28b23b94f51cf2fbdfe68aa7f729c67be94 =
1771173251 0.868 25 0xc2940a261ba7d275bb42338770f6ac9d71eaaa4947bd9341eb33296b00d093e7 =
1771173253 0.868 10 0xbc66ac5916bebb3a7faf9ff9e470cdc2b6d7379267ccbb74af751f023d769bdd =
1771173255 0.868 9 0xec4893731dc2b6ce6f40628333592f0c54a2d5fc05f8388c4e9d6aa25d8617a0 =
1771173271 0.867 26.14 0x799d7a182df36633d0cf398f48ccd67d13ab9e2639bc9548274f9036c5883b32 =
1771173383 0.909 9 0x8110116df8e9da520e489a473c5ae70f49599f2e76ed1f427ef3ed285871712b =
1771173437 0.899 5 0x53957e2c3ecebc3e46ba1e6628d7be0ff767839c06bb4a85f9a8fcaa9c338d30 =
1771173637 0.878 35 0x5bb06e9a06fc7fa2279e04385c56f4f49960a48dd472045e53f61043c3fc87f0 =
1771173743 0.822 25 0x24d318e69c7c5eb4ef63e39930e05445cc17ec90bca988c436c711c5fc45850c =
1771173743 0.822 10 0x4aeb6a8a46d196c6e3df95829f5626d45e9f619b46aabf1194445d375de6bac1 =
1771173743 0.822 10 0x543f8b234be8404754b3478b2f0ba261425ee1424368056080e25890e5067cbb =
1771173743 0.822 10 0x7d4d9ae88a223e433bb62a3fa04fedde9634d3c6f219c45670922d567088dfac =
1771173743 0.822 10 0xbf0a167c866cd687311c5ef11e487ef24550c66872d7ac0fcacc5a2c7b7f9934 =
1771173743 0.822 10 0xe798d00b9c3bc606c71b48dc1030ee57a67d6de79fdfba2050c945c44e7f63f2 =
1771173745 0.822 35.2 0xea1b86a6112cad24d722a16fe04b9770d5c363fa39c2567fb6dff88a88989bd0 =
1771173767 0.8217996159 1082.92 0xe1c539218eb28c3e9a94edd3fcef5e52efe2ffedc2699707a5c2d46cbe3f3268 =
1771173827 0.9678968197 896.789 0x12c79dec6662c60da02c673d15540c32dad914907b95c171308e36cf9a17ae0a =
1771173843 0.999 110 0x3814ee1b10aca26571ba5e024639bf55d1c9783c833c43524490579c53e925a1 =
1771173879 0.908 11.54 0xd46b0fce488377ab5503f7c62d11df0bcfd2eea0f6a9f139f50d0fef85e8fc20 =
1771173901 0.999 896.78 0x87dc6b84e4e137185ce112c9596ff4da69fdb16f6fc227f8238b079dce011404 =
1771173909 0.999 3.43 0x32ff3a7f681a15829de473a0126d71d117664c6722a3323cf2e4de3073a58c6d =
1771174521 0.999 1082.92 0x76f92eb4959eb741fb6cc30cf7cddafacb433336eff0abb119612480da5a426d =
1771174553 0.999 7.6 0xf9b4c55d53a0e48a5e36d8b8ebdec522f6ff562b85233b028a43a303202dd043 =
1771174567 0.999 28 0x76d5671ba258453978c7beda523c4a92d0d54ba94c99249cb9e62f1ee92d568a =
1771174575 0.999 6.13 0x4a285b3bb59a2bce98dcb842e28269555db7e57a723469ca2555bcf69a81be31 =
@1347949 Yes
1770477175 0.021 29.12 0xc6a7418cae812931f6732e6cc55afc1db6587934f6c0a142901c927b7ed3eca5 =
1770485931 0.0275864655 72.499284 0xaf9a12fc86bd51e753039879ebcbb23d571f7641217ed9ddc6e134f6244dbc44 =
1770538841 0.0308774907 32.386019 0xdb29d442779ffcdf8b24cb2b6e0bbac6e1a08e4c7bd901ac8df19eedc96a79a2 =
1770713555 0.01 0.46 0xc1d463928a49842e3dd8ec800e3d62085ab4771028c3881fdcea5e665c6ae2f3 =
1770809435 0.0743751519 67.22674 0x86fb565b6435520fd6eba07bd97e33e4a7856ffdac0a78560366ba7f631bf038 =
1770898647 0.012 2.41 0x019b6ef0cf0f1f3348bd1684dba15ae05273c32d1f42a05a2fbb5365cbeebb69 =
1770951701 0.0426315789 76 0xd519c58ab4f2cfdef0b7f6df63a8dc1586f007e8b93e72b4c95f62e0984c43b0 =
1771026709 0.0525867323 60.471508 0x9117cc63b72a262f5d44e40b804e8894236ce089a73b9d453d1dcc94c455168c =
1771029047 0.0520184965 40.754715 0x1e4de001496fe2d9d498c86ad23a2cc2f6d8f16c4479c38d19ad33fbbdaf32a9 =
1771050417 0.0562559056 24.352981 0x920bbab7ebce068c30fb521c19e8930c7394bfec2ea4f47c962d4f84fa1f1c64 =
1771076085 0.0421824787 30.581394 0x286c8946ffe5446782c4a48685f0a7bae2f9ff2566b2f4758a79e9210ec78e9c =
1771103735 0.0447239817 162.999776 0xef51222839c167aaa242c09c50a3e3869591b26bdbb48cbbde1ba853a841d00c =
1771107825 0.014 4.08 0x2e472627f92a8dab0ede779734fe53c5be2fac36a8b80c3d106105bb1e2281d5 =
1771110711 0.0400845426 30.68512 0xc125c765220763b5c9062495e1afe7cf3be11e32c42f33fd3eff731f4cc538de =
1771110729 0.0298181818 55 0x114521a9c452acf3f1171f8b134fecdc041e69c6384a114973a200f73a1961c1 =
1771113111 0.0523515732 195.98263 0xa73a7de6b60314c5d759d04ae61e02ee355c53e20cdeaa7a9a14b72bfa5f426e =
1771113881 0.0560171955 20.350876 0x50952a885509c56a9ecea3d740a761deefc8b8c9e67413803253fde91006e318 =
1771113895 0.057 20 0x95daebf4aabb40bffd6558615825513da850920498eabb0b79b06002d1db6c91 =
1771130547 0.028 5.97 0x8aba443be67d103facfc6ac83246d332e2992b2fd72925be37afbb1ba9b56ee5 =
1771130585 0.0341331014 36.914284 0xf32a1a95feb8a26ce16048e8b77da8d72587be0af97af5c3c371168c88145717 =
1771130637 0.0332094241 152.8 0xa31334172bc3e4dea7a65122e7874c2e7c8677eb97fb4e70b7ccbe50688c8585 =
1771136549 0.025 6 0x8dafd43217c035e673495f7373674e3f26f0d8e72923c0a35d5cff0698f4f36c =
1771136855 0.0260276498 217 0x32bc9739a9b3342fcbcb127b9420a45e7334603a936ba5f9012dbf958ccbac35 =
1771140917 0.0278 50 0x701070f72a20bada1d1ca2655ea1bac33733f9d9f2e4fffdbd4225fa94617cc5 =
1771146467 0.029 22 0xe298a7520a978ae2cb2e4227a26178a0974e56ec3e4312618ab7779c575e7dac =
1771147453 0.028 50 0x01c5bcb25588d6a564140cdf5bc925236b329f79a44dfa14e5040dc80fef1c54 =
1771151741 0.0290000001 68.965517 0x490139bae30232782535eb8219f5ff356bc3291cacf78fe7b27c641d507045e7 =
1771153617 0.0289999724 34.482757 0x6b984df8086c07586a59237a05fe3c054b0422079045e834d58a1057d01ae52d =
1771155135 0.029 506 0xc58da641a75d5f945dafc09f1ee614d983cbbaab76241493bd7d5b0e4794b9b5 =
1771157673 0.0269409191 380.833332 0xd0746adff234f323731f3443fe491a8f2bb0748c16a8c8108d42640b852b90f7 =
1771160921 0.0267010191 616.26 0x84a93169793340ed8fcb04fd9279f55c90220cb677242158380ab399f3c6ab63 =
1771160923 0.025 30 0xa48e7bb7959a6b26f32922d3e47db6056a37e55f661484c94855a29c9225d9a9 =
1771160925 0.0390124918 107.27 0x8d571177b162050476ac28685409f0843771c35e5bfaa986c356814034c9e3f6 =
1771161767 0.0393125573 76.37 0x78996c9dfc08474a1e81a316c4e09a69c90a8fe78e89564b7ae65dbd31820087 =
1771161769 0.069 16.81 0x950332e21586bc928e9e72ef51b84a00fc8cef17a375a22ec93c13e6ca21299a =
1771165689 0.049 21 0x8a71773fd57c82c69918903ec4d349dbb31e1e78757de2a581bc6a269a1369bd =
1771166201 0.0397380899 27.68125 0x5b517d41823932b159e42ad82ffffa15f68751eae59090efe35ba967e6480dc0 =
1771167315 0.0260000004 63.076922 0x33f777bd347569ec5b3a6bf8b0bda56a5bda4e0a19b605ec3d9aad53688667dc =
1771167327 0.038 14 0x186b8dfe8cccb842b2ecc21068ef2cf6f82e1417fd3ab9674d0df8258354a38d =
1771167495 0.036 100 0xc961f6af29c9b8828afd9928bfad5cb0f39dc0217508d125a82c33a77606eede =
1771167497 0.037 17.72 0x5954839f3f00abb488a79cb60f53e5f04a95ea0d50baf9755129b1e13dab1a5c =
1771167933 0.024 3.12 0x0f4a5708884bf5cf279e3e89527cc92a052bec3883708d1dce8abc874a45ecd9 =
1771167933 0.028 65.17 0x56b3a23ddafe946fe0b522a3bd822520a1686c49976f15f40fcb1eaaf952670b =
1771167933 0.027 390 0xe82ad004f1943fe984dec1c613c38f1c728ab82186b6c632d7b2a03df69398b6 =
1771167935 0.024 4 0xa05842db93ccad176e60f51b3fa2b2427a485282616a5493658a732b351de8ec =
1771168939 0.027 37.037037 0x60c2a4481f1de90146a42709f42fd82faef9f451fb215d6ea4870ec093c5ce8c =
1771169387 0.028 14.79 0x13ea4f43b0776991cc5564a48f82a7dced412559d11a8e1db52a86616777b34e =
1771169387 0.0277991511 100.7225 0xc0f40552d9a80380ffc89862018d51859d049e224463e52a7ddd88cd9c7b95d6 =
1771169387 0.024 4.95 0xfb6c5a1c234ec3098a4bd11e7d85abea7a85f7c8be90ab51c3521ee42cd93163 =
1771169389 0.024 0.9 0xead4a72077d3e2cd210100c9051d6de239f803f21adf08508723e47384d2895b =
1771169397 0.028 95 0x6624c6211efed228be6c2d5b66b5c2170ab22bdccb96e812604358fadf7e5f56 =
1771169399 0.028 13.84 0x5631994c2e71a5d841dac98e2d98563f527cc28a77d2c28602578b1e98e576f3 =
1771169399 0.024 0.85 0xbd00fe817d4472680ebcf141cc866ec0fc3712612a98d95c9d0e8026bc291dbd =
1771169399 0.024 5.84 0xfacecea8b43df11c42518b258c8b390a54da87c1a24848c5a000f2f162338d44 =
1771170581 0.031 33 0xececaf0419f9727d3070098ab58fd1defcf4c2bf367f720990e0fb5137ff3816 =
1771170697 0.0269341135 230.562591 0x2caa746f760626f133e3826804964bb0e13171b3fad97f300099265e425de0b7 =
1771170699 0.025 1.74 0x46fa2ad0bcb04c860d3147727b101adc046b9bb9892e3dcfff1930dea5198a1e =
1771170699 0.0277625841 37.15 0xed55d550f1d85906a53f44209c9244fb73f0bf7df63821d831fd6f721ca2665c =
1771170741 0.026 8 0x36639b04fa5a228b7d6da6cc343005d5531fcf170aed70ec7f4360b0973613dd =
1771170755 0.0293932936 34.021332 0x2dde98eb99b565900e18b266ac16976b5905151489c68cb8e4d485a99d96be7a =
1771170773 0.026 34.02 0x89874d4d8f92bfae6f42c9cf2346d2e802d183b1efc3fddf4401d9891e8d5713 =
1771170967 0.0345776319 57.840832 0x02dbaeb8a0b8312fafeae5800a743c6b744180755b32c41b549cdfe20dfcfbca =
1771170979 0.0439999593 22.727271 0x14b4f1267cc0f43a8edee161d8352a65b836ae60dfe6c3d68aa79a6f921f9c85 =
1771171367 0.0387387209 51.627905 0x22ed0229b2c40a31a3313eb02d6d02d6198cbeef053bb6a11ad386546debc515 =
1771171435 0.0317132533 31.532558 0xa0421689fb1d417a61a45fcafa17a78ddb6b6242ed30e86f691bda24e2420f73 =
1771171533 0.0403670669 47.068047 0xe5dd61916149f6bebad442f6fee0846983491dd4b86cc9b8b3d84e2b34c0efc0 =
1771171563 0.0403478748 30.484877 0x587964182353214887ee928c137faa16faa6b1705358588afc808e8d42d84c5d =
1771171565 0.054 12 0x1475120a33a7833ca2f3b67b4f6605df54edd1b70d000346a68daa82d526ba78 =
1771171573 0.026 3.52 0xa117c542ef72a94c3c3e4fdddeb8e604607d845f54b672fae84b42b693f151db =
1771171647 0.0549999486 18.181817 0x6a517048fa4c234b8d2dafb2a26fca83e7e72eb337a4998ac0ab6f9c3f5da62e =
1771171657 0.0559999498 17.857141 0xe75b4aa3c25849ff878b821f6b4315356ebb43909166d50064d4967bcd1d4a62 =
1771171675 0.0487562191 41.020408 0x5127c502d6b71edaefaeb91c1feae61aed4183b030784e2395189b5c2eb0a91f =
1771172097 0.037451632 50.55 0x24ad54952b8f84e015fe3deb16d6709d074abb11d25f9f529cc796eecfd69350 =
1771172119 0.026573689 22.12 0x5c934c2641e692b05b66af7eb386fc79c4a348bacedf11bc9642d2ebd59c161a =
1771172189 0.0412021026 61.161903 0x5d676ca6ce8cc01a3c688cab10c71ff4014cfa15c18ceed4a038c61a69131b11 =
1771172251 0.034 8.8 0x1880a1a76936ca10658c0741b92fa8e9f138751d68398d28c9a455c07a73b402 =
1771172261 0.0406766019 49.168291 0x3c6b41766d24b7b16c6e97ea71fba4b3c48646c31877e5732d37dbbe08a69a87 =
1771172293 0.0395061728 50.625 0xb183c732f234c8a8918c301f358d9c8e875fad3d172b51cfb4eb4b17904b9c29 =
1771172295 0.0407074975 49.130974 0xa5e40cd6af5be8487b540fc47f5f60b4f8b07026fb9e69cf897a3f36293fb379 =
1771172631 0.03 70 0x4d831a1d596187f04afd78356cab46207bd47ef717a7abb844885033cc0182ed =
1771172715 0.0306936161 70.698708 0x9aa854aef4955393ddf520abf454c6a6b1f470ae1fd04ee16a09d16a3e2f18da =
1771172717 0.031 142.96 0xbe7f75edfb907e226a27f6413e3dc323d3753eb4f68338358e62e088cb0e8998 =
1771172725 0.0409002318 80.19512 0x6b3c4adb58ddc01231081a10f13aebfd1e41ae1cfeed5f1c64de0a5a1b389217 =
1771172955 0.042 0.92 0x13eac96eaaffce4cf417ac28b8d660a1a1770d63876a8e19288d8c59abdf2ad0 =
1771172955 0.0494087985 192.678213 0xdc3b94abbcf7bdd76142c9c7e7fa75ce159da379c2a1e2d7212f628a2e01a90a =
1771173565 0.0515571003 113.078489 0x88e458bd5942dd9a14052102c1a8cd45beafa26eb3926fd239f4ffed9ccbf018 =
1771173607 0.054336214 736.157271 0x50400b8309c166fdcda3cc87b9eb72b0d18029db8981571754223bea69632193 =
1771173609 0.0358313679 8.48 0x1b1501dd272158014fce400a4a507a41940201c3d2093cb31967c29dcb0241f4 =
1771173665 0.054 20 0x2836bc2054b3bb50ef2d125ad781c4840362127934cbc674a5db9215ba12d32e =
1771173677 0.0706799633 90.549 0x5ac3987317ba26d16f93047620700e145b6393df69b8080c3d5b035a724d8454 =
1771173729 0.0794039936 62.969125 0xcdcff12146fba38f948333cdffe74a41c2f4586665b9c9de5857e9a8916cc929 =
1771173743 0.042 10 0xa6a4d66a5220963983dc561064b10095e006a6d7a72a7bc3ef79bb0be9240e85 =
1771173839 0.079 25 0xbfff46fe2afbc158565bcdf0102a711276e19bbc7cce90e1df7bdfb3037e5358 =
1771173857 0.001 31.53 0xdd04ee76d1e35dc2d2868523cc48bef101aaa96a3e54e43cb87bb797ce4e6dee =
1771173865 0.001 4662.47 0x02e5aca0476625a20ca5d91310ddf293bc935a013c3e2353007106c72cadfe7f =
1771173865 0.001 3660 0x68df7aef7a07c9027b1010ea1bd42701092fcb0f8a5f9b6ebe05e38e191c0800 =
1771173913 0.001 470.38 0x5b4541393c2d18f2f4b31926569e0e2cac0571588d4e98e2c9b5be049eab0984 =
1771178529 0.001 1000 0x01433fae9580731b5290c496b249da52a7206199015f564d93aafeb7a114e117 =
@1347949 No
1770423659 0.96 7.35 0x86f9a0f9186993f794a882deac9919b54e2e598bcffdfa50482bcba421940499 =
1770426179 0.9699999981 5.391733 0x01e88340be27db215b5ba1e12149dd0ecdf4a1ccd4e4f7a688c53a350d1cdfb8 =
1770426179 0.96 10 0x669666fbc2ecc0685a159cd5413882c4876909ec3bafd28983091f48785421a6 =
1770426181 0.96 12.64 0xa2fc0bb6415e355be8a97361ef7db3300604ed93ed6f8efe1c42a61d02a2a738 =
1770426191 0.97 57 0x542a75d00f83a8837921d13ec6f0d4d22cd9824c735d75ffc6a151ab01d1500c =
1770458431 0.98 10 0xb1a351fa0c76ad6c7773c8bdd3301d20cadc6dc707956170b11b8c3e04be6cb8 =
1770462375 0.98 7.04 0xc0ef9009f380969850fadb5959097bb2706da9be0778d4a5daa370db06921ccf =
1770462393 0.98 5.23 0x2ce626e845985b05c0c88d826624894b6b0c475f4fcddf16c560bb9ff23d3d6b =
1770466975 0.98 8.0918 0x25bc67b807aa922138ba7d63323b9de0f08c8c8c2776bed8c1b3b6f01e77fb31 =
1770473065 0.979 57 0xe7ae04131f47fa766edd90431ee5dd80f694e421e785eb30bf82ce797f1a0706 =
1770475253 0.979 13.88 0xdc902a3a789739c0b01882a5250ad3d7e57e5d230115bf9569cb281924337bd0 =
1770561155 0.987999997 1.346083 0x8addc2994758a4cac1a420bc5b8af54d4024a0fa7d0866b4b31bc3def85b6853 =
1770706297 0.99 10 0xab6df23986183c099e57d121e680c36e14cd83350a57db49a472c2ac3a061a51 =
1770706301 0.99 20 0x398cdcb3df4ab7cb9cce756d684425650a98f548bbb739adb30508c440caa9af =
1770713319 0.99 17 0x397b24eb50d68797b1fe850298aaf790549830b53f56950fe559176bf8a0bef0 =
1770713725 0.99 10 0x9003f412524e5fc477d5ed1106a1aa85326c751a4f8d1efdc902c00ab4002884 =
1770713725 0.99 30 0xa747b2ad8af14a380b388e18e5d05c4d9f86cdb378d42de4f0608be0fa5b1840 =
1770713725 0.99 23 0xd0411d0263b05a61272f6c9aaecf989c72bf108f216c1746dafe36af0da232b8 =
1770757167 0.988 6.46 0x24b73fe9443aef236ad45e085e0f778ef0c116f75712911d365be0c444ac3c66 =
1770827589 0.988 10 0xf9be5d1b8e498ec1dd6950b3c1a6a9bb3c14e958c0d2402867b38d1d628de02f =
1770871293 0.9879999626 5.880565 0x7865020d2817848cb4367ca42abbceebaedaf03b5ef42a568a78c07333669b4d =
1770871753 0.988 30 0xfd35f215128e679d813ac4c61a740524233d5e0bc7694258cf67092964da0d7b =
1770905533 0.9887218977 56.49 0x8ee615ac5ec99249ee2e3067db49c11f7192885f2a79afed1133056c5ac88df6 =
1770935453 0.987 5 0xe797cc463fff5053fd50d22cd0910f30617da4d7c5e5c11a4a2bfc35239d5fee =
1770941195 0.987 30 0xc9d12959af8051b1394836ba86363166ba45d34074d466136ee54a88b8f90ac3 =
1770941205 0.9888596491 71.25 0x4aafee60343b463453ac8baf09918334f672fd24f77e9b7fc599d61b2868fa1d =
1770941221 0.989 71.25 0xd10b077aff417474dff9dcf87ad5c2ae705a41010cd3f5f076bc38ef12d7a24b =
1770946273 0.988 5 0x7ada61b35d412c161f6e955ce9f4cbabb64727448407425a5dfafc72e6f8b897 =
1770950449 0.984 5 0x6223f02375db3ca1dee6ef9ddecb2ad60368ece56083d2db6e36951195971880 =
1770981579 0.9859999996 20.283928 0x5489c0400bcb6c659ff967fac6c7b3c77b13e5ed442ffeb9b1db2fb96b9cb6b6 =
1771062147 0.981 5.91 0x387957cb2c832cafba9320b429ded0da513d603c94ca2d30ccae64cffc29fbe1 =
1771064729 0.981 17.61 0xf47ba89faecacf26191f53f946b374516c84e699da34585f813f0aad1f99cf6e =
1771065747 0.981 20 0xf438cb4f638b562e4aa4fea5a3739f78184ebc1787474cc40d0e79d7a05181b7 =
1771085531 0.973 20 0x6196fae70221dfb95108a9e024f5c5d25b179405f21294d1b7d423f85438aec4 =
1771086149 0.9734723183 5.78 0xf360117e1d4d32ba9f4a142556ad8e80eb4d80f598c40b8129a18571c58663c6 =
1771088985 0.98 5.56 0x21435730b8622ba25bbe559e97652322f5f567a0c392404275edd964bd456792 =
1771089711 0.98 20 0x0ffa314ad4928b3da54ee58edc8f509a946127dc96b73e2afccccf72a02576ed =
1771107439 0.989 1.9 0x2263586d25f4cfac3c63fd81e7d8b72973f28eae7725b329463afca21c55887d =
1771107551 0.988 30 0x0dd2656e106c9637fe7671dfa68266dfca67c4821aa28d1ec0bfccc68b43fa2b =
1771107551 0.988 10 0x296bf8232ed56e91fb3c4662bc87c4e1c95fb8c5fbcd22585974531d72e8a0be =
1771107551 0.988 15 0x87a4c9f71f5f17b0f25a08bcbe168e8bdfe39ec02d76ed5f4d89cae83f5c2315 =
1771108623 0.978 56.53 0xe7708a2cbfe1e3d5ba76efa5dc4d514fd00a44b0ae152f9d9509100db1e5986a =
1771108685 0.978 29 0x22130c163e630b51007270fecb0584cb4cc460c4679e397072cf20a411ea26ce =
1771108685 0.978 5 0xb915b4ae5f33aa57685542df085e4456937f228f5b91ccbe1d91c71b5d087477 =
1771108861 0.976 5 0x5b673652e063a960f1b1a4d704e02e76f6f63c455d42798d7facc8b38b358980 =
1771108879 0.976 5 0x3ad3ba8a518de637987279b2e698e0c5dad31ca6ac68f2e936a32226c7bc7582 =
1771108881 0.976 5 0xeec2fd4a300436e409003483503a845462b45aea16d1a31408d8d004b04a68c0 =
1771108903 0.976 5 0x5c802d32bab27e3f6b5e5b77432283910abf952c29b552254f7c9f9a42dd8aad =
1771108905 0.976 38.09 0xdfbdddaa90c54c282cf2b511c1e1dad6cddc81ea442f30ee8688dd499f67865e =
1771108919 0.976 10 0x3b08a8fa28ec850c9136e855e6020901636c0803eb1a4071caada00fbd39bcf5 =
1771108923 0.977 89.22 0x91e0328377aef0f1fa78f166fa87372955dd8fb65e045fa35531ee79856aeb74 =
1771108967 0.976 35 0x37ea84c8b363a344b8e8dd0216f823097ff1388dce9bc68012c4ba75f704a490 =
1771108969 0.976 15 0xb3b95d53859a5d6e3dfd7e9f8efb6d017ed9ce41941556fba42566210d0d4e71 =
1771109105 0.975 176 0x6bdfda680f5ac7eb17e236350fed4cd47e0781a21d704f0be024797d12fbedd7 =
1771110131 0.974 20 0x5311337ee3f98f91f0c22aba95a4542f16258211a6ac724a65a85bcc2e77ec49 =
1771117403 0.963 22 0xcde2d16541e39bf132cbcca5cea36a14782d102de7c09128fe6e73eca1398ad4 =
1771119801 0.969 55 0x26524aa8e41eebb32f2bf37c6b837c29a6c320229efb989b4d3d4622201ea144 =
1771119807 0.969 45.73 0x2d231d0b22d77bf5fe63b2e39e1b18fd73a8fa4b34410ee725353710531eb392 =
1771119901 0.968 100 0xb5ba7d02c8038ad45de426dd20ecd8e40034761754bbc471ec7567fffe9527ef =
1771119901 0.968 5 0xd78233be2c97529e4b0886cef62c17b2d7b236dc0341892a68e37e0b4746be92 =
1771119903 0.968 50 0x18a48b72bcc0b47ea7652fcb6e6c617eb35f2baa35f34a7c45b6c46eab1f4077 =
1771119903 0.968 20 0xd4d22ef713de7746015b7b99a6f827a90dde1f3f478287763862545434f2eed1 =
1771119905 0.9537142857 28 0x5e4f2d45bf72f41168265bb060375b90367777b7d8cc47b082cf3ac842d6adaa =
1771119909 0.966245614 57 0x057f4e0c2fdda816814606b3c7521185b873ee1affdf729919d08be61371cca0 =
1771119925 0.948 5 0x1ab8bd9dac7070e2e4dcad14a7b095053cf4b8d6d23ee7423bc907d98513fc62 =
1771120137 0.969 5 0x8f0e146e724641ea53f65526ca90cb70a8b1bc5ef703b4d14a6ce66f06284260 =
1771120137 0.96725 20 0xe0cb7e3bf21812766f051cb0f785a6537fb7a8db0a54533266f13f91912ab62e =
1771120137 0.969 5 0xfb53093607d7647bfd39fb74089ec3579691bd87964c5383f5c81540c29643ae =
1771120151 0.969 5 0xc83c65b6296a65675751b39c42aa95db04ef34d942f8a58d7c8acacbed06648a =
1771130471 0.972 10.94 0x5f8832465633f48157d888ae08bb3ffe2aeee0b9ecd5cd392f4bd17de5994886 =
1771130527 0.972 21.22 0x85767431159bab5ab4d93e88ed6f35daaf1b7df7096b3229b99274bb7ab140de =
1771130545 0.972 16 0x99073009bdc9239a4489daf26d92c26f6e485c69a7c8425819a875790caa5bc8 =
1771130547 0.972 17 0xcc8643a8fe0c063d260d46d556680137a74893dc2485f0d521dba812cfcb96fe =
1771130555 0.972 16 0xdebf9f495bad800d97b0ff31a874b6cbfd5df4cf0a195c94778004133d66d3b6 =
1771130563 0.973 17.79 0xad79fc9ed34647fcaaf848193ae90e31018f7cbf569f28cfb37c6c7c9b334e2f =
1771130579 0.972 8.19 0x70d3330d1caebb8012d2e010d2cfa2a7e3d8a707cad6f4fe757a7f9699e14c89 =
1771135849 0.9759816331 447 0x2a9dbd6355b97fc9847b523df6f5b4cb3f8d139d6354978c20fb29a07c4fdcd6 =
1771135849 0.975 30 0x957673c090fc3fd43665a7abe6356c73cd2272745358a8a92c94e7264ec4063a =
1771135851 0.973179 20 0xd2cc5f0d9afaf4db32d1cbe67450c188839a2f3f0c7e3aae60a589806569a271 =
1771135857 0.9754385965 71.25 0x3e7abcc21bf41063d9a5432dcbe3bde3466c444cf190d2019080bf8ec1b03111 =
1771135863 0.976 5.43 0x66dd692a8bde67038b6a7ea161c348705b45b3824d65a8e55c2d047c23f1aced =
1771136045 0.976 20 0x90bb87df5c58159e82ca45f7ee7e43da1d19e2a7029de7e13520d11b51c4becd =
1771136045 0.976 131 0xedd2547e7a85ab49c459382a6f3bc6f5492deefdee53f23179c6541caad2070b =
1771136053 0.976 71.25 0x04c31dd717921b2f6c49bd87005e8369a4f3fa3d0cea19b820d9bffe83a84b09 =
1771136201 0.976 5 0xe95ac96d6a461cefa18ea8af0f3b86a95af622719173c9e9c3970586cf9baae5 =
1771136203 0.976 5 0xb2728569dfe969e1764f1ef6651eb5b41cdb9edd96fc1fae25d778a5088ae58c =
1771136741 0.976 5 0x0f41627968fef98115265e34e9799968c483e2671353d570f9dd33f235d73ac6 =
1771136907 0.974 15 0x18db923f2baffae055013ae5afecc9cc4adc919ab5c566eb0c37e7e26fe5ed9c =
1771137995 0.9753251429 35 0x433dfa8473bdb25666ad2aebf5d45c23dceb7486473ce237f68eafee4875bd6c =
1771137995 0.975 1.28 0xb185fc1124827643412b102c3783c2837190030caa08e496022b4fd3b35d135e =
1771137995 0.9748113636 132 0xce5d9569924135a32f41affc03997f6c5878b8e1492d7b378f6f9f3cbc50c6f5 =
1771138003 0.975 6.36 0x899e13d20644ea62fe47405443b3ffda1d8e5e516f567aabaa26bc0722d14d5a =
1771138387 0.975 10 0x0eab641931d2d0defa874b0dbe395ada44706e790ce3b24d82456c1a64cb2ca1 =
1771138387 0.975 10 0xd652b087e27a13e075b748061d1ef89a7bf245ad719ab7798b90e00d3f2a7fdd =
1771148817 0.975 100 0x4cb8681066638f4946d47d66819e5b0fe6ed2bc0dc2bc630bc7005f931cbc41a =
1771153219 0.975 20 0x1d9472b0f2337254082a2e495b1567a29da10f5838434c63376f6dddc610c4f4 =
1771153227 0.975 31 0xc93c50fc1b44532ab082ade57641ccf67e582fb2176e753b065c7daf99f72554 =
1771155109 0.975 20.1 0x402ded0330766a593ddebdbb3c19998970581617516173e7e0dc700b2eb78a92 =
1771155109 0.975 10 0x41a884642541da3ce8874fb5b603f2b502a101f236be2752e8ebf93f1b8d8929 =
1771155109 0.975 10 0xfc19990940d4543c1314e4c11590dae70f03e47fcf256189cc60d6d3f23f7031 =
1771155137 0.974 37.1 0x70d9bd7464e7b81866c66f4459e151d5f4f7fec0f9b6faa1f9c325e8ee319185 =
1771155197 0.974 33 0xf88c57d138f8f0b5728b7f853a9fca35cd838497901e3b163468d80d802319a9 =
1771155257 0.974 183 0xe6b2c4016911000e6ed1920363ace500b1c7572f69847a5798c50ecda610c0d1 =
1771155317 0.974 58 0xee56b8425460628ca70e95bb68bd26d2229614d55623b9b1cf65485e7a02a839 =
1771155547 0.974 22.5 0x1a11f09ef3a95ca246948c9c971e58f8bd03b11632e164f196b8fb1560ba89b6 =
1771155609 0.974 22.5 0x323af4ac9e577ac5a558ddd78da9f38e33ead73a48b27a5b0f4859f031884377 =
1771155731 0.974 23 0xa8dfee683a7bb18017234d580b9caf0ba9ebd226143bfc57f289bd2534657c6d =
1771157229 0.974 192 0x48c1382e66a8d7be114118099f5f8dfbe99701a1bfe8ac56e7abbc52ec0e6687 =
1771157435 0.975 368.9 0xe3820e0d9dccbe182f5a71325c5e11f261d45f0c4c24a9214c96a8be223b62fa =
1771157837 0.974 12.5 0x57f080471c594fe749b795640e2fc93e50c1cf38be599c6a71dfad46a0a7e451 =
1771160815 0.974 27.4 0x253b87d8c225b281f4c1b0b50dc4dfe8b0af03814973a01875ac0f4c366a4500 =
1771160817 0.975 15 0x7a7cfd49ab9d7df507b51e714ac0033a959af5b2ac6f1459b921b129b943a781 =
1771160825 0.975 57 0xd57e9cc4a54f964130d67d9648560d8085682226c0e5291af25279907391c758 =
1771160837 0.974 100 0xd5c3fb4b495a8d4abefa873b0ea2c130a1255b85eb10e1bb87ddfe47d81647be =
1771161779 0.974 15 0x559d9b519bcb6e8469f74ddf0cbc8de232d2dec805bc4b24aeb4b959a861ef53 =
1771161937 0.973065764 15.51 0x1814d2020a7621e15b75d4890c60a55eefa296dd99f4e76343ec987156e55289 =
1771161937 0.974 14.49 0x4f36824bc21885f921fff6325268c15653c4593bd1cc1f7f02dd11f1e0750f6e =
1771165497 0.972 40 0x016a34ac05c8cc51c56a0e9ed1891ad1120191bdc19f866b05e623b4b81ebf4c =
1771165761 0.972315 20 0xc1ccd8d24008e3affc9448f794743fca4bba7029b3e7b19d43b33431e0facf71 =
1771165763 0.972 13.7 0xe232946b7358e243405455d488cb3b928cc6f71c8f4a3659542e26fa469ac90c =
1771165777 0.973 20 0x1be97bbcaa30ce80aaa3412d477422914645a9c444167255e2c96281d13a4084 =
1771165779 0.973 26 0xe8bf5e48a4fa9215614aa81c89fca6ef3a6a595a7f328cfa8456ac06354a4a44 =
1771165781 0.973 14 0x77b516aa71afca034ff77b54f39069444af8c9b17009fe2f6ec9d5035e94820f =
1771166201 0.9742575 20 0x397b012bb8c2e2c73d08e66d1e7b9a508e040363ff2b6da6cf36795373f060d2 =
1771166483 0.972 7.5 0xbb2d9972b9c2e821d3efba19246b1f4c7f5899970eac187fa88b6fb846d38576 =
1771166867 0.972 7.18 0xb9235db546d808cfda56380886eea4460c34072b44f449c8d38392c807f765f9 =
1771167003 0.974 20 0x3353eddcbad27af2af7d4ebd098abf98cf83350f93a3609dad8d2b55c9364a49 =
1771167003 0.974 17.99 0x9a70d59edf66baa27f46323419d2f0f464c452f904ae4f7a7850d16cc16416ac =
1771167009 0.975 15 0xa54a790527e00c32d23ea651b1b1c49afaab24e3fa4c8f9e842a801d8ae4bc6f =
1771167015 0.974 25 0xfb37098274e011afd4a3ed6416721049954421a4bfd99b59110a91952b3fd15b =
1771167017 0.974 5 0xc9ab9601a2777d4c549d41122967b3727bafa29d120e21b1a6127a6c5bb17154 =
1771167025 0.975 40 0x0f2831913aae34221bea5535f0417cfc2a543a61124837c0554d7a666a6b146e =
1771167025 0.975 30 0xcfd5eb5d8b4fbbd44346d2a34edfd9b62ad6e2337d2048c2e15abc3c6938e6d7 =
1771167315 0.974 51 0x612fe41aefcd3e50af1cf15af88ac80b737262aa01ea84d5a53580ec5be5dd8d =
1771167509 0.974 40 0x1e7b24e2be59eefd6d9aa772984d991522588c27ea3f208345344368e1eb59bf =
1771167675 0.975 8.47 0x9a888ed44102573162320933ee875470008f2f6d56251da6638b91d7c4e3857b =
1771167677 0.975 331.53 0x19394e3de9752333ea30c146eea4098d7a2dbe15daf51e52d2f3d65629a7eaf9 =
1771167677 0.975 20 0xbfc8211c4051b853e39730abf4d5f300cedc32bbc4ef1e1a89c9287506c42635 =
1771169541 0.975 50.87 0xd8b602d1064df1cbc36481770e077c594fb711d6c7493103d774e5394d70b1ef =
1771170011 0.97355735 54.49 0x64f8630b1545f6ac8c188c05e3df64ba8564197b0991c03a7e843c3f040654ca =
1771170343 0.9739999989 16.858307 0xb435748da54d7b3686d0f7818f702c4b906fa09e7cacb62735f6c83493308ade =
1771170353 0.973 30 0xa185f02a3ed47c70b308b7e7fbc661cfd605f2a05b9af5b4d790567281b859d8 =
1771170353 0.973 15.45 0xc6a80ec22c014edc14d6217414619a30ffe6c9b298fb645bffd1af7762022d5f =
1771170719 0.975 75 0x3c6396e0dacadefde9d1176b5ff9fef797b936930e46ddb588cf99ff7342c559 =
1771170721 0.975 5 0x9e736e61a9bb0d74aa0022328dc4ef1339ee66efef144eb5b85df1b7ebf4fc2c =
1771170813 0.974 32 0x9000c3bb5178a1d8b1874b03a2ccd50f25953f13e3cdcb32772e75eeebfd104f =
1771170835 0.974 5 0x2f846e5f678615b3306915468379eee03662571534368c03d7cd10d44ce5731b =
1771170931 0.975 10 0x02e4f726142e19ceef5c16591c94e1320abda8332e66f92dd70ac185dc122b22 =
1771170993 0.973 10 0x5196fd75a83114b135bf02943c9c792e39085300fa52c436cb9be4c74d6f4a1d =
1771171053 0.973 5 0x7c4514e764990d2a59d700d5a14dfe896c17eb394ab5605b7022209090d6317e =
1771171085 0.973 5.4 0xa25120ed4dc5164ecb66e5c437dda1a36ddac66ac0aad2d465d695607fae7587 =
1771171097 0.9735 40 0xca070ba3e68d5ceedf4426ca3c6ca75e9b768ad115493c39d54fd2d06deb9c97 =
1771171103 0.973 12.27 0xafd2bd55b882c07f4e41733e2d67cc760af5de6120119f5a2b83b3f4223cebc0 =
1771171129 0.973 7.6 0xc289e4c37be4f0242a61793dfa5cab1d9852a0809eee20b01e049123dc4b5667 =
1771171235 0.973 2.29 0x64fddebc821d8b6907e10024d99506c8cc34a41c9353eb04e488225970cbba6a =
1771171249 0.9733241463 41 0x67051591287fbb4ea74c0f68af037b1f8e698bb303a16c529283c3a4c82c4a06 =
1771171339 0.975 30 0x192dce4ad1b9ea7d73824800fdff46d502b3064c318ac0238945b825197f89bf =
1771171339 0.9749706 150 0x862aa4b7c16839895b979d409271948884941140ab6616fee448238d5c0d821f =
1771171339 0.974 5 0xce6b6bb070fa3a3355dadeb2ae78e6d8e76ca0b58e4052a0692a191b66bf9965 =
1771171357 0.975 26 0x462f207bba646abe6b2935e044b760116948d23aaea63bdec292e4299a49b03c =
1771171367 0.975 6 0xf7d07de09d9a0708322286f57cdaf320b9b03cfa644baafd022b95f3c47b06ea =
1771171633 0.951 5 0xc50c71e6f21e656a6bf35bddc999ed7b2d602659969cb878a657bfdfa697ac38 =
1771171647 0.951 70 0xb7263019e718d1eafae6f2d8348a5ec12db8ec7f08bdbea11eac1fd6b6d3b95c =
1771171663 0.951 7 0xa6db81a298e728cf5ca0e6b1882b4b9817fcfa5f4688c874cd5aa3b15e8bfdd8 =
1771171749 0.951 30 0x0b72a5fa971cf0b04b48ec12a8f163f705f12b99bc155b34cfd54eaddadee7ce =
1771171749 0.951 20 0xc5a671a6fa46c2e76a5d226d053ca9288306400451de4a024154b2098fd9763e =
1771171763 0.951 3 0x1732f2d2f9d31435a260272ed09c120596e88cdb90f0f3d7a7f93234653aa8da =
1771171859 0.9723014815 27 0xb86d7e749e25b8a71bbf241608feb907d20b8daec064849dbe434b49016e198c =
1771171879 0.972296 25 0x73b32c848036c36ab61435555bbdb536ac3851ce44ad3652c2b857bce2fd3354 =
1771171927 0.973 15 0x48065a11e7b0eb5ea29d7efa36a9584e2528dc977611a934211ff12687fc8425 =
1771171927 0.9739246667 15 0xf0b7693f9aa60b09eed645cbd6bb31e1cb466d4ea783b086ec213bb31e04ffde =
1771171979 0.974 15 0x1349dfffcd86329b3e5da9deec38f259a45ca313ae76535ac33f3635e0f844e8 =
1771171979 0.9754172637 201 0xd123f2b4ee18313e54a79c450ba3f1bd11ee0d5315ad6ae02dedb68b009aec74 =
1771171979 0.9740956667 30 0xf46aa95e4e98ccf01e8bf0363698cbafbf8b074b4a8f8ad98146935a03ea4ea1 =
1771172049 0.976 13 0x48fbc96f6bb23fc881f099fcad4fa2be852c1e3c501753264e08a08228e54ac9 =
1771172113 0.976 13 0xeeac441def04798e88f9d2f3e07dc136018f5780c7b9c4768c68da371df97b32 =
1771172221 0.974 5.84 0x4a1b46d2247916b292657c43efb7700f6bb736c6388b731561f022fe8e49c95a =
1771172225 0.974 10 0xb23b39ae0f738702b13116d44f3f1fc10819615346cd1438a0cf1de726971a38 =
1771172241 0.975 6.14 0x5782df4c56c43ae1d92746edc88babf8e08e8da8110f146f7741ea6a70cecbca =
1771172247 0.975 18 0x3ac3601b9e5134522aea9de3e226de7b9176c3525ec246621342d0005c7b316d =
1771172247 0.975 11 0xf672ce1c4b5efdcedf8aacf8dfee884e4751467edae08d7694673ed03398041b =
1771172251 0.966 7 0x96935e8fecb6b5fde52b9537a1709d228d7c2d6c4666dbd864fa606e60feae9d =
1771172253 0.966 4 0x514061c3ad566ffef1b629eea59304373341432b216a6ae787150adad1372e81 =
1771172253 0.966 5 0x9a3d4314b1bb20f2d516033a51fb5be4663b1061dff0abc5402e7e795786face =
1771172261 0.975 30 0x975ba2ae2cd3b8bb3f8340a8cd0727fb63d392b24b7e1a95475b235b6d61c5ab =
1771172261 0.966 7.2 0xb7aab27cdd88f942855b60983e3fafd4027cec100756fbfcba6a422fa93b3fd8 =
1771172291 0.9743918919 37 0xe2279cde016cd8a31d36c92d7af588e49230790d1919d14f76279b19d16a8209 =
1771172295 0.975 25 0xe88144cef6a1f47df6f527cb7271958fb51fdec8dc66c7cd91781ab085952843 =
1771172385 0.974 12.04 0x2e906974f134b492f216ba45062a27983d3e2c67e9400581c7cb660b98e03d74 =
1771172481 0.9708805263 38 0x2a6898bf33c36aff989dc4c2e0ec90b31ac39d3fccf08e57d283ada287002537 =
1771172547 0.973286 50 0xf95e1e64c0a8383b7ad8f356baed6df599bcded132195743b60f1bc7ad1cba36 =
1771172637 0.973 5.99 0x56269904755636b7c58ef302d20572548e5d2d0ced465bfa5ca7db2cf779d0c9 =
1771172641 0.973 10 0x1782b2fe4b6d758f6bf772b38823134b7542034e94327f211055dacc6395a7fc =
1771172855 0.966 29 0xa4cccecb28875d14d8bb9a3f742ad39b1e03cf32978821c27eddfbeb4c0847f0 =
1771173251 0.954 25 0x5ed4e90531ead5a35630792924cc8e5a6d2bcb8fa4e53ffe9411a3dec1bbb2be =
1771173253 0.954 10 0x6672dfd6aeb0813c42d5599d778c7fe8fd15613948a7fef7afbbfaeb7171fc72 =
1771173255 0.954 9 0x0d05361e5ecd2802bdc543e37655311789e51868bd94b6f9fbbd8f2394b0bc44 =
1771173289 0.954574745 177.47 0xff9b883cf98c3eefe1c60c190847d38e05610363062dec59a85fb73606584776 =
1771173359 0.966 10 0x163864fda8ac6130b1199a7db55ee30598a2e7873d21517fb34676b91a3c608f =
1771173359 0.966 30 0x2c5f54933b2c5d5702e951af0c206abcd85811a2f2fb3885d02374a216a68911 =
1771173359 0.966 51 0xfb3963a5a49fed55b85eb1f784dc9e31b88129c3be9af6b57fc485e569e8c9e1 =
1771173383 0.966 7 0x63983e40631cf57d23e75de1cdfdf1504ea8e738f4c037e35a8e30a552010c96 =
1771173569 0.959 27.23 0xfe675e1f2da19102a26cdcb87bc4200c72ea73568021a33f5a6f1e9927d9de22 =
1771173743 0.958 25 0x283b08cec19fb179c013d0455e1812c585b68b59e8128c9a94c651b3e4885a24 =
1771173743 0.967 10 0x8d7012def669bbf9480e520956a23af18cb2973cf0eea01a384ba031f0424f59 =
1771173743 0.964 10 0x94ff1cc8cf719f800c18c0b4f237165daa90b8728b90a0dbdd3fe34abf69f3ca =
1771173743 0.967 10 0xa269f0c0ae80ec304d358fd1b08cfbc20b1f30c195e984ac05f02016316550ee =
1771173745 0.964 10 0x904ff34dca3925040b76e57239260d62fe865da21a08f63d058dc7e64f01ef7b =
1771173745 0.967 35.2 0xfab8bcbf0b84ffe4fc4b5239fea6667d6a6a5b6b4552b20e36cab66b5d028a2c =
1771173843 0.9786198182 110 0x3387bc0d907d2dd733d372f239350be52cd7b08b2365de579dbd1a466014afe7 =
1771173843 0.961464 150 0x944f4f210f7ddc81f76483ebee2a24fcac1de2f1f2b7b6cf997361f8bdedb66e =
1771173847 0.998 2.77 0xa004e7af00f9d47b9140b330e95f4ddcbe7a92aa71335a5103c0e0761754d08b =
1771173847 0.9868421282 918.34 0xb6afff138bd00f7749030a2fd472167437975017a667b770dce4fd618db01fc3 =
1771173919 0.999 921.11 0xa7540fda00086fd865a536c5d8216c6163b17491a84822c3a7796ae2deefc986 =
1771174551 0.999 7.6 0xad308825af17fe727250145a2a84cc388e2353d3f1c113a3baa2825f1b978ab7 =
1771174565 0.999 7.6 0x6a6df820998ba394dcc2e8a54643ce2bf14099d1baf682acc159fab30499ff63 =
1771174573 0.999 6.13 0x261aa7dead060cd375196445b3e3f927cf74bfa5b52e6fb427b73d7354003c97 =
1771175665 0.999 20.41 0x1205c5f7ab77f58cd41309ab2559fdef06ce510a827e3b7db96ab4916a97aa85 =
1771178947 0.999 20 0xdd6f6fb5270d72d91855ced8a200628b63f4993e685e3fc0d068cdf98ead3716 =
@1347950 Yes
1770483037 0.001 6.12 0x39ea5958c0ba30a3497aca11381b720666e9113f4057295a0d25407e5b89d155 =
1770483039 0.001 57 0xce609ae63b3f9bad87ce5b25641264f9c0343561af41d18713ddaecda6222d7c =
1770483041 0.001 19.86 0x79e4cadab4beab310d9e5e3138340d09b2e57bde928bcbfd5619f661d3948ccc =
1770629223 0.0087142552 229.509 0xb4b5698a4bbdf99f1ed27cf5cd45214489decb03ce83dc94c21aa8d6c844d1c9 =
1770629367 0.001 0.25 0xe903b585890ac24abc5abe2e5be56e083f76ababc6b041fce358185128163233 =
1770713555 0.011 0.47 0xcfef6ce620df9878a8977c579a12e80404c82eabdf1b80430d12e903026d278c =
1770713657 0.0194174757 51.5 0x2d275c114207b35305e3995d83610301a37d2214fd880738a232ccbf0e48cfd4 =
1770813029 0.0199547847 386.3735 0xacd9e598f1e2fa8da0f2ba15648bd75fdbff898ac7dd6407c8b8dd7f4ef85aff =
1770898647 0.001 2.41 0x993cc127b7be0cc54ebb44978218d2afa42e0efe19f1b15636c21926cd3c7b79 =
1770948055 0.003 5 0xc66edab62bf66caa312a137bc9458842506563d3d3ae10a2a43bd237301892ec =
1771089713 0.008 137.5 0x4273b603147a1c1acd306c595da610940beffa513b5750f62ff346c1e1cfd098 =
1771107825 0.001 4.08 0x27e65d38d0247870e355592dca886d72b554d3f7d7d479bae7c75db3401cc87e =
1771108929 0.002 38.09 0xc84820e0dd97d8c3908e8d1024e3616c74aa8da1b3b13723edfbce75d005cb9c =
1771109149 0.002 5 0x6d8923c28e2405400a73b603a2f55efc0e30e07b7c2f38724af2d66ec83a0ada =
1771123533 0.003 6 0xf1869da615b6787b10d570eb80f5b4732e76291a13b731f83879e4d5bf94ef8d =
1771130481 0.0084897959 122.5 0xcaa9eebafad7861a604b070cb58fda556f1a74a6e7966fa413333977a032a76b =
1771130545 0.0759999354 13.684209 0x7869b939b830b806545e26c0bf5d5ebb057646b918bac30f184e84bdd12059f0 =
1771133181 0.004 10.1 0x78baddc25bcdad467dea6f95d073eb0cb3055844f842f20dc122aac21bb0a537 =
1771135863 0.004 22.74 0x382f13d737d997eae9533df8c7ba4360a0a3e3727cf17e465cd01e0b471e7700 =
1771135865 0.0087186645 119.284209 0x938ba76489bfebcec55ec9ef33102a566f41cd24f31a2219e54626848bebe52a =
1771135881 0.004 0.27 0xab6cd11994525c9076bad180cf189c61e46aad0af679485633128fb7d1d84151 =
1771138005 0.0188159989 217.39 0x228289c0fe0b2abe780db3245126b7818713cc615e4c09c656e56b5cd7a0b79e =
1771138019 0.004 0.83 0x5bec5a231bc98d0fd7272b98143e16e8fb0ab3a9cd224d79a0879ec57e823ece =
1771138835 0.007 500 0x5b5b52922d5d82821d9abc5e9a56506bdc7596d999f64bb25346f925a9e656f1 =
1771142843 0.006 100 0x8b3740c931667799cee47de97e8405f1b9addaf661740d1f133f24b8a9281b98 =
1771169223 0.0041237454 242.498 0x64bce6b2eb83107fda468c8f003ffb88dec2a7edb12189d63e96f7c44864b49b =
1771171339 0.0140179681 1426.740227 0xf6c7f50126a00fce40d59f5df6c0dd9ec4876974640f2db3c6c7faf6e9a6bffc =
1771171341 0.003 217.39 0x69bd76d456f61713d1ee08fb1fffa2b040923dc1da203bcb9fed476651d8ed2c =
1771172561 0.004 11.2 0xb76e3d17709c48e4634477a631debd87e20d119b93191f50e0df566f07767bcb =
1771172817 0.004 5.84 0xdab80587297205b33b3b7ed0e2b7703cea63dfdd0ea665a651049d95ee529319 =
1771173043 0.001 1207.71 0xe48e2d3a9a7f9d2ea750aaf9d1398df50285f24bd6fd53bb8ad5fbef00608410 =
1771178529 0.001 1000 0x15344beeb0817258571aa0e19defe96211d965a10be06f989f38e87ee1ef83c1 =
@1347950 No
1770426179 0.99 10 0x41eb00bdec4416ddfd37e92dbd3a0a8f24134b8cb3060a5214398759d70436ac =
1770426179 0.99 18.0303 0x6e36e5ee80be2b18e797149910c585a648d0551b940b029a6c223a898c22962a =
1770458431 0.99 10 0x862824886b998ee7df838ed581e63d1afd98a4a4e9f5be618d11f690cfd3dffc =
1770462375 0.989 7.04 0x5bdd5f11e031c90e718ebee4ac063d84055cd0614c43180459741ea6fed073c4 =
1770462393 0.989 5.23 0x11c2be3a56cc68ef593bb4d7f2cf63185df212131d5505a38d792542039137cc =
1770464351 0.989 28 0x70cc5fcb77c5bce9240af53d58be5ffb2340a551bb04f358c2f103caef356449 =
1770464365 0.989 28 0x9d744012dffed10ff612ee3c76c369aad6290d474f6dfae57a06c038a3bdfff6 =
1770466975 0.99 8.0909 0x57c3b56bc2b81e2e11070360ac0ba0892f94e9ef53a027510d54eb3dd2943c6b =
1770473065 0.9904957895 57 0xa189abc9930ca2e3175a4d476f14480c701456b552cfdd47acce3b4e0b8a9f3e =
1770475253 0.999 13.88 0xdf4ea4cf45d71de3df84f48a5f915d52cbcc13fb221a728aed2335f5c98706dd =
1770706299 0.999 10 0x1266585b5b3fe101d6b493f29f44341f9716f8cea07b7e253954b8c62db70c99 =
1770706301 0.999 20 0xe33f3344bcbe1a4ceba594a5a5513d805dcbb81f090dd94317d66ee1cb669312 =
1770713319 0.989 17 0xfe639956870409203a3945036896c20abb93fa357996f552abc1f92da2220202 =
1770713725 0.989 10 0x047cf951c3df75f0a18481059c4ec684fa68ce1d6b69d3a5c4f3e68b4ffa18fe =
1770713725 0.989 23 0x0b2cd27e137169086a819d568a4350cbf284568c033245b12ec737cc677341f3 =
1770713725 0.989 30 0x0d7835efdaf2296c92f494f847b7a8e46e450a2e21228f733f74114163f6b848 =
1770757167 0.99 6.46 0xf3d8f4f1bd58835d027947bfc0294409bb14fb2f5d088e5aacf8485c7f36f9f7 =
1770827589 0.996 10 0xfdfb5b70f2d08c7c31b1651d3df7ffcd5c0525b6fbcf3e33290ad4279a0b261d =
1770871293 0.999 5.88 0xe00db6f9f76ba75c84c4fe12952915e924cf653cf2249de7886aaf1bddc9b41f =
1770871753 0.999 30 0x4145b9050ebc3c224806bc87c3c10bcb62c3806778160c9b63b0d7a32d2996b5 =
1770905533 0.999 56.49 0x5685280c34a8a76587e9a2b6d0a9c18b8f6e233804c7eb620cded656509aea8b =
1770935453 0.996 5 0x70d9563cdb7691a06772c736a6d4c3a71cf5274c794805c42ca83885714135ea =
1770941197 0.993 30 0xbdb94cfd0a02cbfe97e847449418eb6585645a5ed99444f87b35c67efb476b1b =
1770941207 0.996 71.25 0xc9d5bbd5ce35c9e0a84f3183d1e0f7c5b7b3fccedbe5030787e40a4ceadb4a35 =
1770941223 0.996 71.25 0x91c7b58e1056408ed59a4b8523e36d6b4ab0020a82831d6deb318457ac7a47f3 =
1770946273 0.997 5 0xf01eb6dd2902cf2b08b7a7db5035c57d5dd5f60e5bd2adf343c1e7fa0705d2ba =
1770950449 0.997 5 0x7fe497f2ac9f775573f7f9873f5d4cd977d4626d295ad2b67dd411327fefffd9 =
1770951707 0.997 35 0x239c29f6e12b9370e6ac47ad6448b2db6aeccaf473243bd8e9fc42c171540721 =
1771062147 0.997 5.91 0x4a6ccf6bc11f85dcad7f6daaed05093da7e2572b36c9846d079d032686d2034f =
1771064729 0.997 17.61 0x1276b6fdbc34dbb2106b45b5b6078be7786fcdfa9a84c8f6824aa9b1578923a7 =
1771065747 0.997 20 0x1a8205e9e5fe61da304e4a7e78381d9bdb3fffa921a3eafc6c6b619feda7e3c5 =
1771076085 0.999 20 0xea392a10c126b41a1550824eca78480a99ada633086db1d3b4afe8d3c966a35c =
1771085531 0.999 20 0x706015de9510328dd53a436ed652e3f558106facd1e1faf9906c1c22b6f13e2c =
1771086149 0.999 5.78 0xd7ae40f2944351af945cdc103e6529416743413c4721c86763172d4a814be239 =
1771088985 0.998 5.56 0xbbf1d5de5c5bfe4607a5c695e40930f4162a06015888c283a94cd866786f4832 =
1771089711 0.998 20 0x6966cef18d98fa028a4203f497219285190393b898ad8994fec4aed5df12f131 =
1771103735 0.999 20 0x3cb5fa71a5ec7e19c7313ceea6ce50d45a9251aaeeab4ef3939cbf6fc2468279 =
1771107439 0.999 1.9 0x7949dc5a8181bb68916ef65246dfa6a6f9743d0c3c30b827c06b12e856667098 =
1771107551 0.999 10 0xa15645994ed95e9d792240083fd9d989fa3a8a9b1e04abb94f1205365dbd8940 =
1771107551 0.999 30 0xdce843af0baa749f22597d4008dedc8ad59f4be5365f28149304f852da93d4cd =
1771107553 0.999 15 0x850b7839aa6fb4c8dd6e5dbe9c857b693ab8904ad093cb4e90091a5a71ff357b =
1771108623 0.998 56.53 0xb8775f3e34299b3dd345a0dcab95fa9b9ab315063970c57c1fee147c440789d5 =
1771108685 0.998 5 0x05293a3c4ea30bac3d334a9547da257c9ba1ab482235b7f8ec3769f975a768d9 =
1771108685 0.998 29 0xdfdb9348d50c9572acc646997b6741235c0338e920cf64629f0fbcde957cceb4 =
1771108861 0.998 5 0x33dd6c010e62da1017315034f23c0a28620fb6623786352e2101eed966dd5529 =
1771108881 0.998 5 0x1210a9a72c6044f81161de459df4201d280cf8e9ca040319883c1e6acfdfc8ac =
1771108903 0.998 5 0x9227bdb5708e8159241555d30e7392a0e67b46582fe7aa0b2b6c18646ed33a74 =
1771108921 0.998 10 0xfd9ad21040fdc5dfe17a77e60828116f5564f7ba2b03e64bd95a37a852d8897e =
1771108923 0.998 89.22 0x548577677a1a10f6775e995c6f51dae8a58569bcf0e1a303b4e8b27fac0203cc =
1771108967 0.998 35 0xfef22fe2a4ce47a97c7a04ea7738fe0f0d5ade71c76f8926e5213a4e65a793b7 =
1771108969 0.998 15 0x86b5da724317fdccb0160d9446f1b7c201892c18f84b28ddf4a7faa7543b9c7c =
1771109105 0.998 176 0x825421ee087e15ebd0be15dc940f8c61c8500bcff156d95800ecca1b0e3832e6 =
1771110711 0.997 12.59 0xc3078a6f47bdcf7bc901263abab834869113a500ee933f7449157dc1d7296210 =
1771113111 0.997 39 0xede70fc9a2e7b5eda814cb0c00e1ee24f7553ee1c31b0fdbc7e1b86f749b8eec =
1771113883 0.997 20 0x8137a38401875c313d7aed7735d15f2effafcd57f9f339ce47a26701dba518cb =
1771113895 0.9971110426 16.21 0x3b1b07936ad9ca095f0de5f4696da2fa3be9c231268ccbe98853e5d47572f70f =
1771117403 0.997 22 0x7b2de34d48883527fff592336d8b76bc7b332be70a086db5ceb93bcccd43260f =
1771119801 0.997 55 0x2588ac215b7cd56ae3bf49e360be0dceb32d793ded352ca97a07868c42c32cff =
1771119807 0.997 45.73 0x9711c69c841c1c0514fb23105ca86cd1c27b683216bcc2b9745bc55b84ccefd9 =
1771119901 0.9967 20 0xf8fccc13acea8a711e1cddb182e32c1b0423712dc77eefc3d7226e20605e5ec0 =
1771119901 0.997 5 0xfb2e4f437ddb1d9c9462c5a2d15c7ad71fef172ea06e1fc05990fa701c1d2ae9 =
1771119903 0.997 50 0xb93f55ba0a4e81e14ec936021a259d8415984a6a260e44a7156a7965a136cdf6 =
1771119903 0.997 100 0xf7884bf0aa820764b757ac6096139d26b8cdca6939df617d24f6111dfce4d63a =
1771119905 0.997 28 0x206da8190db50951bc27e37999c4c9b76a5434201bb1dd7bfac4f0fd84d59353 =
1771119909 0.997 57 0x0d9bc43a10a4f3e66be20e55cc2ab2a805526e485e18b9b0a97f448c8523952c =
1771119925 0.997 5 0x1b0049eb1a77ed008d3724c2a3cc0dbf10655c06c7965df17d7496cbfe80a990 =
1771120137 0.996 5 0x0f225a235187867ae8a3b984f6122a60f5bcd42b06bb6ad9302b17ac4e117e8a =
1771120137 0.996 5 0x0fdcb9e9aacde89d38239bc3f34ca12e02d17aea203a9c793bb50df5adea08d5 =
1771120137 0.99575 20 0x47fc68fbd9bbfca83cee8d5af3ae2ef1ca8a37d32bb64bde14fdbf78cced8a57 =
1771120151 0.996 5 0xbe4aa20ee8cebd504aa0cf8a5fbde6a8f477c1420b52c7b9377f38e47db6f552 =
1771130469 0.997 10.94 0x5723c4848dff3e1b90f9aca52b5e23e243becf6b9c53a72ba7d98bd9c3609c94 =
1771130527 0.997 21.22 0xd846add514ebc32b3effd23b90ba3abe103980da54d4306b24ae0ccadcf5a707 =
1771130547 0.996 5.97 0x0ad2e47fc1291f9fd72812fb4a69625f09fb42c651bcd2426ac3b9386387a487 =
1771130547 0.996 21 0xc5a78750b24c969d89d1df1fdb787d0781c19299a26949ee3a11f2b8ce275474 =
1771130555 0.996 14 0xe4515717f1b76ab1fe56e281a9ea807337af6aa30d5296b64e9b42cefa2f3ec4 =
1771130563 0.996 17.79 0x73f639b92d124bc85f6da2144dd179bd093cb04c52a1d4d40831a2a3403a9e5a =
1771130579 0.996 8.19 0xd5840bc8a593fa4e95aa4980a0f25b88164f41324f51792ef1810e12e3eae77c =
1771135849 0.997 30 0x10a6dfc29ea465edef0d9c27c0650d0a0903078c9b2798c109f0200a2e607afb =
1771135849 0.997 20 0xc8effe49e2d21996cfe8e941f2e898958ce47fbe83d4a46abb81a4c7fc10443f =
1771135849 0.997 511 0xf8bd3ad4301a422262836e932c61a6fb005c8e04402fc306ad720175be218001 =
1771135857 0.997 71.25 0x997d0c66edad1769e14b7d6d1ed29bddacac61755f164e30f226992664ea43c2 =
1771135863 0.996 5.43 0x43f69b7c0ab592f18a7736e4c7f55c01135e22546ed5628ff4d0acfc96f8c65a =
1771136045 0.997 131 0x3fc8665d61405a201dfd5e3ad639e3b47710509895481ac56bfa58d6c2562f9c =
1771136045 0.997 20 0xc5c90d0a1b92fa0d0b54c730140fd789d25e71fde7551489cfedda23bbd8091e =
1771136053 0.997 71.25 0xcffdf26c34ae11cf971f06b6f738af40bc389241cc553d6c7a888cadd6a5f346 =
1771136201 0.997 5 0x4904d48add19d8b44173c6b502301c69ffb473b40cb0e89394f7b436aa63c8e7 =
1771136201 0.997 5 0x67a495893d192970c118cff8064889e99c87438c2897400859370f2299d9f130 =
1771136741 0.996 5 0xc4db05f10a0d86a9d40ba028be546e0e3d49d6e77217e9dccac78e99cab81442 =
1771136907 0.996 15 0xc9e86e2da4243acb7e24c79ef1f6f8b480505672da8cb9b8f974278e4d12a1cf =
1771137995 0.996 1.28 0x1db48740b54a36a943dcc99896d00896746e650a8a6c3f9c7f7d7e59e0328234 =
1771137995 0.996 35 0x67221c247b9ae4d474329ae5e1079b78202f59717e8d98d2fec8e5a2c1517f07 =
1771137995 0.996 158.72 0x8515f47e90477a802a30bf968612727b62414330d3748c8f17395bd89ff7c3f6 =
1771138005 0.997 6.36 0x46816cb404d9a9a11ad34d51833a140b604d86e7ab55d4cd3b8e4884cc85b328 =
1771138007 0.996 105 0x7b726a60e4065f338dfb4f7b4a1a30561431905fbacade3da378b27fc1703b1f =
1771138387 0.997 10 0x1f4f0dcdd34e95e26976c07ea39b8a88adcfcfc7dcb463ad0f0de6a708b79524 =
1771138387 0.997 10 0x88e685dcee4d233120a24e93bf9dbeeac716c1b6a4c0a4a8cfea5122c38d3532 =
1771148817 0.996 100 0xa4416ff2622bb734ac2c6bae2a706d24b1916a06fd56a76c5d8a18168727bbb7 =
1771153219 0.997 20 0x8564c7857320c1b7fe4dd2b2df77ac286aa0bfe8d63b4af3e2d915de73703d6a =
1771153227 0.997 31 0x3a3c3496c61e3ccf709dcf62dc5dcd0d052ffd5cca8ff490e8ba6c2056a03827 =
1771155107 0.997 10 0x913f860cca410c817ce43e8bc26bd5e5063188837b02476e400266a49c70a33c =
1771155109 0.997 10 0x4c7ab34b29824e20017a29d358e75bd68ee261c6f6ff77da3985aecacc115926 =
1771155109 0.997 20.1 0xd601e01c0962ba3618cd5e97e4c168ce90f0d8962942ee3cbe2fd8af17c157c1 =
1771157435 0.9979901982 908 0x496e6ce7e1513247b2d6c1150076751169b02da61eca847441b4e51dde8c40ba =
1771157839 0.997 12.5 0xf01e79bf7bfbe0a581a4d20caec97db4a3a269f5f9b7ecb6705ab03510d7bec7 =
1771160815 0.998 299 0x77ec88ddbc7a7c5c4e7fe008df9aabc9f5fedb98c78b6e8865aa21b47d893ad6 =
1771160817 0.998 15 0x741a224f345a9e0412028307dc549ca522313e8616c626fee1da39bd953ecca0 =
1771160825 0.998 57 0xc7b376669fbaacdf7c51078eb2f2008f72574ad09136108745a11ac762e50d15 =
1771161781 0.998 15 0x27b506e3d4864d7bc86f53c6aac2d3c5efd87611723848f69272484a3951b575 =
1771161937 0.998 15.51 0xa63399b82a361233c8c57d8b3597b639e763f482d5dbe52ef7135d1a32f9aed7 =
1771161937 0.998 14.49 0xbf9d32ffcf6f2e934b141579dd880d2f51f0a126929b56b552cdec6d83f44801 =
1771165497 0.998 40 0x70b8af12a6ab57cece4831865ea72a2518bf8d2bc8b0c454ad82612429128edf =
1771165761 0.998 20 0xc3cea009d4c3f0c7c3d2aa899f61b3454b5d5029d33983264b2751aa77d32e91 =
1771165763 0.998 13.7 0x89e7fbb86734c02b8d7a62af799cc1e6f675087fd066a760b5ceb58ae9840008 =
1771165777 0.998 20 0x781964cec91ba4f16857c153ae7e6d0ace3ad0b5b99cb2c22ab89a19ad780840 =
1771165779 0.998 26 0xf0c61a208f407897936455106d2219086d97f934281463f5b7fbf595a404b7ac =
1771165781 0.998 14 0xc8cbf75d582b1720458aaec71663f6becb15881f0c21cb9641b88740ac6eef63 =
1771166201 0.998 20 0x34e851a355e3aa3a749df1cdc4591cf4a6d2d50fa6008f5b831c5088444801ef =
1771166483 0.998 7.5 0xd80e8d483b9a0c8f7974fa0cddbf9cba30f5037ac40cfff181f148a1289007c6 =
1771166867 0.998 7.18 0x25f7776aa698527842f322d8f12c8274efd42310d5c508a8b7150882385d8a3e =
1771167003 0.998 20 0xae85959c2d05a58712630e6f701874138f51537c0d6572442e2ed93263278983 =
1771167003 0.998 227 0xb9d45e62ad1edcb27f24e5dc16a8aa12248cd50646da369ec45dfc28382bfa3d =
1771167003 0.998 15 0xfcb89e4dc1636ec8ed84d20684d781de65c7cf26ee6c5c0c4527bfe345a62dd6 =
1771167017 0.998 5 0xe1189a70234c23bbcdd3172e65b8a8db72fc18d79ec1aa6bcb88f5ac9fa54b53 =
1771167025 0.998 40 0x243e1937c987f7bf765af36dd9bf27d6d37a0e7d5ee3d843a9bb464bee238fa1 =
1771167025 0.998 30 0xfd87101056dab0b9ac428a6ecc7b3738312fa967b93a6ead27a9c8f60eed285c =
1771167675 0.998 8.47 0x9eaf8615711c37491331b7ef554e5e65b5bafa67f5d5b511efc1fcd85090087a =
1771167677 0.998 20 0x90be69c49ff34a617f631261fe88ddab58dc0c51509fa661913f45705c685304 =
1771167677 0.998 682 0x9a2f1151975893fce2bbfd4dcf19fa0bc5190c9da957bf9a95e888b11e24031e =
1771169541 0.998 50.87 0xea923ffa57a1a5193d00f4bdf6aace888c12ccaf1ffbd67535e385a05144d3f2 =
1771170013 0.998 54.49 0x7b9d6ea887416043fc618f36f03b44e85b675d325427c9b836f06ddfe51a5efb =
1771170343 0.9969999999 16.850333 0xd932327b0c81a3d9b2f05c6a89ad491800f4cc12b1a7b15f376c562a52be8d31 =
1771170353 0.997 53.14 0x69e66a607191b940b9a9d7bdcac38624c36a5d1fa94c08efe7696c6b24533957 =
1771170353 0.997 30 0xcecc2303da92dd9754fb2d5174b5aece702165a4611a37325fe01859257eee3f =
1771170719 0.998 75 0xf43ca8d93bcda1a76eba4dd1c4db671c51de226bad34a0f9a59b74e8000cfba9 =
1771170721 0.998 5 0xb6ae63ec93f05961cff256b5ab690012f40fefdae12d5c1832d2a54f266fe882 =
1771170755 0.998 179 0xe74a68000a3b63b6c8fcdf21e3100c6c8b89b0d67864f2a5613eef92d21e2003 =
1771170813 0.998 32 0x7f9f6dd24f209c4cda3bc32a0ab88a9275ce52b6aa3fb3549022358fbb533124 =
1771170835 0.998 5 0x1ac309bad6dcd08994978de5222b0344eb1b9b2f8d043c56246a7dd241c31af2 =
1771170931 0.998 10 0xf69850aceb64f002a41b1b2570eb6b235014f0d864ade2bc001e186f5d81109e =
1771170993 0.998 10 0x09e8b8587a1ce329c09570ccda8240dad99b71a6cd0225a3ef8ac70160467b45 =
1771171053 0.997 5 0x799076071317714135bafc4a034181582b766fbb8cd46744297443aaf77978a1 =
1771171085 0.997 5.4 0x54358bf551324ffe49f19c7e5663fc415abdb997f9865c6b0b3c16627991c16b =
1771171095 0.997 40 0xaa745762045d0a75f6244e8e8beac827193a8a4045da016f51fc435ac3ea23d6 =
1771171097 0.997 12.27 0x0e6ac6b3abeeb709be1224864d4ba0ea33d501cef00651a8913816e75a503bfb =
1771171235 0.997 2.29 0x57d84f471be059a3cbaa01d9aa1eb9eb121a08d47fed18fdf2ce8ba91da2ebea =
1771171249 0.9971453659 41 0xc5d53e1ddb4e4c8bcf3c0fc5898a43c7ad5352682da9e85bb5be4dd8a2e89bcb =
1771171357 0.9976503846 26 0xca9bc1572557fbf48e590cec7f81220bd896335f303824e047681ef8d0ebd857 =
1771171367 0.997 6 0x05292c8c2b59f035cafa481661eb28f78f65e7df0a40c942e80ef2c53ba283cb =
1771171547 0.997 38 0x9357bad96fa4c9aed65e0c12d1a88870f75dcb9186434eb22a3381c101e49f7f =
1771171563 0.997 21 0x65d4e81a196e33923d68f69a727d7eafda15e044271bf4decb03cdf2d2acc5ec =
1771171633 0.997 5 0x8f6539cca5c8bd567571b809f0f021e77896597912cb84988d9557d32701786a =
1771171647 0.997 70 0xb9cdbd2f30250e407c3ea984940d00a9f4c2318274d0a4f14ccb3025676ddea3 =
1771171647 0.997 19 0xe20aec65c201a6613ba09df5a2151f25172d5be3573c007899024b2f7b2ac188 =
1771171663 0.997 7 0x4e74d33c432f6c6d67e92b3c19eaa84aacb9618cb208d16d18cd77a9616bf876 =
1771171749 0.997 30 0x483728749161b1fe11b369f77bb825bd49fc6498ca7e64c475de79d1c6c67aa9 =
1771171749 0.997 20 0x58af1ac0b543c8f5a8b0dc293e0eabf0f27750c8c486f9e3d0e663e3cf18a619 =
1771171763 0.997 3 0x4f0f67c8feeea43cc940b75bfdebe4cf58a7aa53461f5064a24f30c8a03992b8 =
1771171859 0.997 25 0x93f3076e5361154d317ef95f489a26fe7b1955bb9b7984336412cbb5ddad9d38 =
1771171879 0.995 25 0x12cc66ca0f53a88acfd250e3a9dcef106eb9478891e84f5ea3f55dc5d3ce2182 =
1771171927 0.995 15 0x164b0b6d98bdab8c5318976d9416252b1027e6d3cb89f9e882134f59ba82dbb5 =
1771171927 0.996 15 0x42f4948354cbe4889917b3ec930bd601d19168dbb3fe3590e95e8bf85f0091c5 =
1771171979 0.996 30 0x4e25e3636ce27b94690951de90840aa1f9a7d2fdb0dd4066ba309c775c711233 =
1771171979 0.996 15 0x70ab680e282abebd79e84f2c3a9974f0abcb8516bf8fff5a1288574792a22143 =
1771171979 0.996681592 201 0xdfaf07b737355bf6efd44167c194ebb783192f90a13b64fea21c24a100b7d966 =
1771172049 0.996 13 0x8318fa53228708fc54b66cd5120df5ee23c7c83e10938488d735ce91e5c90f62 =
1771172113 0.996 13 0x0bc0e5088ac24ff5c8f72cb812e83cea4a1d11f17e4906aabbb45901d10b6597 =
1771172225 0.996 10 0xe37adf5449300c21695c07e1563705d2b74e7409efbed014a222bbb54111358b =
1771172239 0.996 6.14 0x50b78004e5834a3caa5968f892b8f608823548e773efad6c5a7ebfaf41244213 =
1771172247 0.996 11 0xedd6ce71023a818bc40724cbd649eb478b0f2776e3a33a75b2adc43a89d7cd31 =
1771172249 0.996 18 0xde5348faefd4a10006c8e2e272f167aa34c7a124f9e6ee4bed7ba5a8ea309810 =
1771172251 0.996 7 0x3a5cbf613e52c50647c9220e8c148c72732620166b11c9e47f3198686b805547 =
1771172251 0.996 5 0x8b93ddbcde62d853a56e558e82d0346f5837bef2972b84cb89944942afde2941 =
1771172259 0.996 30 0x25a24a14482a8584152ad93a9b58c2874f09f3c3ac990678a54cfbcf96516a6b =
1771172291 0.996 37 0xe7b9588c12a4379d7269d95d1ccb5d064361f47fdeb6ea33047db9205d2d2f41 =
1771172295 0.996 25 0x115c1bb676e23384a417f294f0093f309e546d18fe2164abab87533ef60089e1 =
1771172385 0.996 12.04 0xf4e1dd867571042d5771bb8de65af76a034d223206cb0e79428077f00a58f4fe =
1771172477 0.996 38 0xb2c2d6d5827c023e64c38cbb5849105a69a398ca4308600b92035e7df7ad0fa4 =
1771172541 0.996 50 0x9f5fde0b1e11d277cb4e7c632c4e05e5577067d0aec59dc23fbc138e5e69fdce =
1771172635 0.996 5.99 0x7e0da995f334fdae3a9e1347dbea4dc12dd46deb7c1bb82d1ad0b5db5171a7eb =
1771172641 0.996 10 0x1cf539ec712d13a781640e9cc1517111a9027a866726448706e98150c1891e7e =
1771172853 0.9975592208 77 0x39e054e01fdd505dbf467c9ff51d883c4c6028821197152adcc5e9480c320b65 =
1771172989 0.998 61.162 0x241350555a8c6b72bb2a61b9ec6b7175bc3750229e619221f1ee559d94df6862 =
1771173005 0.998 1000 0x648d55a2fb985af98b4a4981cbde9f2ee25da40bf7b06cbbf6aaeed4d50718fa =
1771173009 0.998 200 0x2a5a0027e343f6f9a25e202677da9f7c7924aef6175c84db4bd4fdd780ed18a2 =
1771173041 0.9987889013 16792.29 0xceedec52380bc7aa0b7dbb47cb9fdc9e130fa4471bffd80153b63a53c3d67597 =
1771174567 0.999 28 0x4d73f9cdbc06dc08afd5a7ced46990ac9c6c7c13f2b271202a1822babca3ed04 =
1771174573 0.999 6.13 0x71ffb8147697f7ad2d396f5a4ab57fc9f1bd179ec738e73ec65c1e9bed06b8eb =
@1347951 Yes
1770415371 0.02 59.99 0xfc8b9b897a4839767588baad063d5b17e9c68ad737ec1b6410737f605364e053 =
1770483053 0.001 6.12 0x692a0fc2a6a0e5742eff7fac66d31c1783158ceba42a6f67d90c225f72a44c75 =
1770483055 0.001 9.59 0x4ff69efc272a8c44a5373189cd70dcaaff20a99eaadf1c5f3684bcad8f34de9d =
1770483055 0.001 49 0x5839f89d9ce3e3cbcc0b547a7fe36b6799009bfb73a031781751ccd9281abdd5 =
1770850013 0.001 100 0x2a2ec92666d23c63eb79615a3ee97e7ede090ead9abc032b9391f6d80a3b429d =
1770855869 0.001 47.41 0xca5e78b9622da930f90e90c630db0807ab02873270644df5b778b74b6238f78d =
1770855879 0.01 37.72 0xba97e3d20bead7945f7b80602deca5eba9c2e6bf0208dfe8584f6d32f1dda2af =
1770855911 0.01 6.46 0x2c7153e25bab7cd2ec39f56aaf81f27b3cfd486d95dde3a1c05edcb1b55e8ab5 =
1770871755 0.0189999833 57.894735 0x5d84ff49a6a47bfb80721315bb53c3189db45a465bc5a2a69ca83a481b1408fc =
1770898647 0.001 2.41 0xaa764e1e957b53cf27fcc19db9de782312051ea3a8663437230b02f5ebe08181 =
1770948155 0.003 5 0xaa781e5b9276f594921befae3fcdc6187930214693a43f6bfe4fffac5dabecf5 =
1771107825 0.001 4.08 0x92aae3ddc0c94ee7001f190758bbc059c3c5faa2e79231373a9c8a2d046cdc1f =
1771108931 0.001 1.57 0x49b88e02ff53d2aaa95ce63c49e61a60616910d12988c64bdbba502d45845136 =
1771108949 0.001 5 0x57a7a272a886052020eaf9744bc4de5205320f65e5d84584eea1dbd075b77f3c =
1771120433 0.001 120.74 0x99ff810de8282cb05120dfaefc8608ee7b53eb45ba8d8f0d3ab5c0f5329d6b4f =
1771120437 0.001 25 0x025b59d8a956c83fd4ea41493ecafd83674eb28eb95cd8ea67554018bfd25b9c =
1771120785 0.001 22 0x3250851251f774dc098dfa6accb49977c8cc9d7cc023b6dac4f3f7e5afacca87 =
1771121201 0.001 67.26 0x26d5b2c7e362ff87ff5440815440764dfe58942cb975a2c3e3207061644cf501 =
1771178529 0.001 1000 0xc70e321d3c90d123a6c6e6d91a674cb440433b7636fe2c79657a84e5c426cddf =
@1347951 No
1770426165 0.99 10 0x6e88718cf179615c697e82ed67f04c0236c56da24f74e45e5210bf43962b7d80 =
1770426167 0.99 18.0303 0x99ca3b11792725afa875207e2268e939ee643b6f2db62de0ffb4235f420c8c97 =
1770458433 0.99 10 0xe36ba8af3d28ac36d20f8e1cdeeb437d1c77d746c120d1272390aa55a207436b =
1770462375 0.99 7.04 0xcb627a058a7aec405b1f08cf83c5ed36b490da941e6194c711796857fac233c0 =
1770462393 0.99 5.23 0xe71aec05ae1b71e58e44df1b23f98a5b6138dd7de4a9eecbe0b1bcb9ec17ebc1 =
1770464351 0.99 28 0x8f89f5e9df11b54868ee856a0acee8ba29172d9c3e9e2eab64ff7c80f063c3e0 =
1770464365 0.99 28 0x5c8dd22c75f99a10d987804297d0ebb5350b8720c9f3d6811036e91c166478e0 =
1770466975 0.99 8.0909 0xd48b6ac6c8e7f5b5701284b9fbd52bf3f58f35e0919136b662b8579131821227 =
1770473065 0.9933805263 57 0x33731e38da8ae40841022ea61075b073aa1f0d6170062e4529668f26ff87a244 =
1770475253 0.999 13.88 0xaa14d263eb5d6aca3fc142d19f3940ad3fb6dc2d5558066d711591f0e4a4a4f1 =
1770871293 0.99 5.8888 0xee4f588e4ceed78f7bfdbd54f981bfde6bf8f8a8eb73aa2e4882c0978782fa9a =
1770871753 0.998244 30 0x8b1faac6934310b62b5211c6052646ced2fcd12830bae1abd02e9e66cb1e1df6 =
1770905533 0.999 56.49 0x1a3ca8e894ec4fc187bc72caf8cf00e15816c91a98abb121bc4839a8a2dfb60a =
1770935453 0.996 5 0x66694bba9e154e6ceea4170c064ac005b4305d98325053cd34c00cec759cafb3 =
1770941195 0.997 30 0x5dbcae618968a718b9e61b76ebbe4f33b7ced34d3f878cf4770f4325cb2b0a0c =
1770941207 0.997 71.25 0xfe9b7e35147f2c6f4e3dfb96f466ed36bcdb431f1460b0d6b31f330b7a3ad7b6 =
1770941221 0.997 71.25 0x6b0b1d309cf276caa67e7d793595f49bf7ad4fc3247eaf33bd6db5af0f2d310a =
1770946273 0.997 5 0x5246028ef27d58cc6341bf55e9a38dd15a83ff49d9c82f49534e812ba1df003b =
1770950449 0.997 5 0xc519bd207c6908a1ab97fd7957fffdc17daa8289c1b277258d631fba7f60cf03 =
1770951709 0.997 35 0x0de26bccdeb4a1d31bec68f9184ac8359e84cc94f926cc41207b4208d135cb62 =
1771007599 0.999 2.022 0xc0f9737d44c67450c93a4f0ecafe57e2a958a623952ab0879b9487cd85a3e4bd =
1771007611 0.995 1.01 0x5d051ece44a488c32460528b0c08b6aa5941a48c5b698afaca26acb7b1d13f38 =
1771062147 0.999 5.91 0x2d46fa43f156fa8842a4c5a368fc0b87f9a2387f4fe03692ac31a21af9ebe46a =
1771064729 0.999 17.61 0x2fdd55bdc5eb6bf52012692afecdac56dd7b5f46bc84d2d736ff89059e058031 =
1771065747 0.999 20 0xc9f472218d4907ae69ed9c7047d41f19ab2bc5048b566d511ace160489f0aca3 =
1771076085 0.999 20 0xaa431eba4191a58abfce043aaaf56e670a596012d159ef40c28aa81b7b76d6d8 =
1771085531 0.999 20 0x850634bc4d4749ea517924db647c4cb0494adc1a059f282887f0a069608b8513 =
1771086149 0.999 5.78 0x095765606c0e1f878891b5e29f9235251d382e9900302cae94198f82b63f248c =
1771086975 0.999 25.025 0x8666728c93653dec55d59acacdb6c14bf19ac94f4c6bf85b07127a6081bda39a =
1771088985 0.999 5.56 0x31f9e89b667278265286b4950d954cc4d671b6cfcc931eae78ff3dd25fa6fb58 =
1771089711 0.999 20 0x209a6ddf6744c0b7cffac6ba82b3aa36e14ef1a655017ce8d546c1927c3b2242 =
1771103733 0.999 20 0xed684d93b640753f2db72d62f1b868ecf13fe8e6e72b46252ecee83f459671a4 =
1771107439 0.999 1.9 0x99005a01c1f774c8657ce301b07d2ebec3e189d1171bba365f508f25a0e8a343 =
1771107551 0.999 10 0x530c7492e4b55f007d56c818a848979b3fd71b7e7b6082d5faa5c71d005d4e65 =
1771107551 0.999 30 0x7e075d24eec39739f5f14239a09c5805a3200cf322de974790e68a43711361c9 =
1771107553 0.999 15 0xd5e28864d5d09cbb898487eb00cf66df530902bf81d5aafa0eb9d0db25d3b30f =
1771108623 0.999 56.53 0x2429f7ab27b9b40306123762239c32e5762dd3a5e3a253caff1fb1e314b400dd =
1771108685 0.999 5 0x9d9ff280f3d0654a4138d4e2c75d5971c2ef670250c89f67293135bc7fa9135e =
1771108685 0.999 29 0xb5a461bf1f6e462c304140dcec5e58499fa22f867d1df661bc13f864d0652d94 =
1771108861 0.999 5 0x5960c2ec75476e1524edbdb278a95c6d6233771082ba02f5c7540a32c31aa04c =
1771108881 0.999 5 0x10c45d8aa3d954e28cebbf0f2ff1228445d2d94752fffe7514c6d49cd40d523c =
@1347952 Yes
1770483015 0.01 49 0x3197838f2b7b78401f438278f8ee1036b415b68cfe3f9231b8b91ecee8ae84bc =
1770483015 0.01 6.12 0x957a8f7c3125f626595041a7f028dc92a0f6e2fe929294d47945700cc5d052e4 =
1770483017 0.01 19.58 0xb84232b6a75e10fedf279639176f5009c2aea87f124868bcc165534d7471bc15 =
1770489453 0.001 37.42 0xd3b1189c979f680c52843bb9a5ffd58248c3ed8b5058ae4f8af64aa4c8f13abb =
1770539111 0.002 0.25 0xf2f06e6ed12b3df479fd91ce06d28037f25cde1149ea41bd29efdb62f8f4a151 =
1770713555 0.002 0.47 0xf98897c2700ec0dd62e9332af40860d324ed9225db6d3eceb6b29520ef16b9e9 =
1770849603 0.009 37 0xb7968e4d2270d93455d5cf6e10cff46f4cd3d34f49b81bcbba8ce3f9aeedc924 =
1770898647 0.01 2.41 0xe1bdded814b3ffc3d58169a95fdbd2a69cfb0e0ce09261044b7b94c68a24d1df =
1770947957 0.004 1 0xbb530061f9f888ad185fccb0233841c065d72b9672b00fa75581f3433fdbca9c =
1771107825 0.001 4.08 0x16ee30bdf1271be8e581d39ebbd7eaa172d567336542a8c4384de8bc952a23f0 =
1771108931 0.001 38.09 0x5f57e540b49adbddf7cb186b2776b92edcd2db99857b73bd27a62acb62dabeed =
1771108949 0.001 89.22 0x272ef648f8b814fe0159059cb166cc547f8a1eb5eda29492309f70961478ceff =
1771109081 0.001 15 0xa6cbb867d863069440e54651aae33924a3927a45e1e2323baf7d0d20f4826a0e =
1771120073 0.001 5 0x85a6aa8732a5ea66e27a0e779a6be65f585f7ff81486f307300cecf483c7ee79 =
1771123545 0.001 7 0x4c151f38ae5f8189661912b3c1971e048e245114719b62fc3c485638235e3f34 =
1771130567 0.0049563145 209.833333 0xed5ef69210b820fc6552c0478ebccbe3dae69b47ada38a85724243851ddcf63f =
1771130571 0.0070228294 148.088461 0x8db85b8ab924bbf8dab4b702a62f65b375a4e1249b05cb32bf532a31a38431c2 =
1771130577 0.013 80 0x44238770ecf57b9541369bda266aa361dfbac05684d97e57659051a785c5e0a4 =
1771130579 0.0014414394 357.92 0xf43f1338774bffb98acb14fc364e1173bac378d8af9e0d3c0d504368a16f735a =
1771130579 0.0284762841 36.521584 0xfd663034ca11dd36d51cc06d552f48871303d7a4ac8a8163a724f956aa10d7b7 =
1771130587 0.001 0.11 0x188f5ded6415dba9fccfd6d78f5b91bf63b3c6758080d72329fb4244321af8cb =
1771137557 0.003 142 0xe50489ee3550baa91a8fcdc5340dbca1efd204272658950b59fd7a8ba0a54521 =
1771138005 0.008 238.09 0x6f693fb45351f70020a3ce8895824d18dc098966b2fb9711a44d62cede3f7885 =
1771178531 0.001 1000 0x203d51f72a798690e622ae5f7132a4ba7759b575b0c95892cea4d240f06be569 =
@1347952 No
1770415193 0.98 59.99 0xc05a6007905c85d9799cfed997c342ddd30db630685c1b773aaee463f4ae5f7a =
1770426165 0.98 18.0306 0xbefe4687046eb44a7ff36a5885888834aab040ff3fb50e1fbd32f485ed57324d =
1770426179 0.98 10 0xd2d2e484012d46834702711512203527fbf77f5929385ba97e4f8fc9f58ef2f2 =
1770458431 0.98 10 0xf2c24865297d669cf7ef51765371911aad00d3c5dce82d17ca1e2fcbc45ed827 =
1770462375 0.98 7.04 0x4bd0afe1f8991bfb7ece31872431b2aaf7fd939785faf745821ce617a2ed0887 =
1770462393 0.98 5.23 0x36387e1b0cbfa7b751c86c36622dcab71478895775684f0cdb74082a1099b785 =
1770464351 0.9865428571 28 0x47940e56629f02ebe53e4bbbae4d590a6b64e25627598238aa99561fa1daebe3 =
1770464365 0.99 28 0x9d0914248ab6db3d71183f7809075aabfde0738aff0cd2f23de793ba8b27ec5d =
1770466975 0.99 8.0909 0xb284f3cc36f916d829f9457c93d01cb850785ed23c32812ac4fc0836874eee54 =
1770473065 0.99 57 0x2905c3080925f0e91e9c2b5a89edfc2b8316ec5a93af29d1a974af5af827f19e =
1770475253 0.99 13.88 0xf5ddcf480adab8294e7b6ff1dca23de22942ade62cdecb0f96b827611e866c35 =
1770706299 0.998 10 0x254a9373afb159f68754e75436f9ce9e9f82f4a02375dc69cb80d2595cf766bb =
1770706301 0.998 20 0xfeb9d0a1e1394c7d28ba20c6922317550c6b666981aa02430080fe38413e76a8 =
1770713319 0.998 17 0xede54aeb957614eea1e043c68e0b668d36eea20d017f172afafa702a63452f34 =
1770713725 0.998 10 0x4a5ce34ca634cab2d766d0826b27738d9d42059a6b8fb353ac155a2c218896b9 =
1770713725 0.998 23 0xab483bbc659546a1c86380a92acaddf6521f0c9b7de5d4c108734ee774b090b8 =
1770713725 0.998 30 0xbea1e15ad8d5840c61c5511f89139d5d7c8de6ace008c3f66b66e782e4a5e65d =
1770757167 0.994 6.46 0x059b111d90b63b5be7195153fb2f9caeb3f3d290ae3eefc687bb5d39766c212d =
1770827589 0.999 10 0x0d443bcb4b1f4041808ffe1d046fe63b83f8e3d378183aee14ed72959c98df59 =
1770871293 0.99 5.8888 0x5b22cd54f9d261f5714aa0699fbee2ccec2c87733048be9ad66c9181c12ff17a =
1770871753 0.99 30 0x3383fd2e52899196d2e4660660ca05a7793d2f5d289446f930658a47f2eb5b26 =
1770905533 0.9950647902 56.49 0xa5db9eec2aebeb9fbe384f6ae221c58ecbb876f19d90b6f39a20ebfb4b4d499f =
1770935453 0.999 5 0xcda87dceac13be80f45bfb8618d2f2e53ab11140be78389020799a732e27beb6 =
1770941195 0.999 30 0x4ee0701d8c27102edeef87e0430363015b525c8a3decdb797ca7117f137148dc =
1770941205 0.999 71.25 0x127fa20aa76ecbdf1ddb7d4cd42787ddd21767220ad57e650b263c468de97f88 =
1770941221 0.999 71.25 0x2336104b7f4ed00b7f616d8ff447805f13088a005b4fd2327b3e3108b9424c96 =
1770946273 0.996 5 0x40ffdc8f9fad9b9bd4cab89424d88bc6d1d2a69af2358507542e7eb45488a3a4 =
1770950449 0.997 5 0x9597a55d10e128531b2ad431b9364f839c5fc9ea00b4c2ce57edf9c1606bc4c6 =
1770951709 0.997 35 0x9a4a282499c730fa00680b34333dd1905b02e66e00a474ca4d7c95d6e96217e5 =
1771062147 0.997 5.91 0x9fce5f1da431d38220c6595b01051cf919fe0c8ddee6729a8d87db3ba43673c2 =
1771064729 0.997 17.61 0x870627fba928241c1f034aafe2ad2c02bc1bf5bfd33ad15e2bbdbbca310c60d4 =
1771065747 0.997 20 0xe60b30ba24104e40a59eba6effcdf755f9cef14b5173e014bca74c0b45e75124 =
1771076085 0.997 20 0x5deb7036b86c6cdb55919e02d18fb1bfdb220ff18e42e8d2e8128239bef6b56b =
1771085531 0.997 20 0x2cba3d8440b75513262be69d6dea855558d9b83e91127dd4175cd3bfb23657d4 =
1771086149 0.997 5.78 0x0ac94c5a87985f4f2a17653770713146ff233d9b7aada7297b07447eab011597 =
1771088985 0.997 5.56 0x31eb4a3e7e575cbd7c940c28e6df975ed43be5dcd05521c27cf2f5c9dcc81eee =
1771089711 0.997 20 0x624b64398280cea6ae893be2b9d59be7fd0adbed4709bdbba447f68eff487ed5 =
1771103733 0.999 20 0x9f7475dcc6855a5d2e5752e93db098edf90a9aad0abc65e400e1b4857b29aa76 =
1771107441 0.999 1.9 0x0a1526c2a5700ad3585706b20b43a97a1d9fd3db634bcbcf2a0bfaa87b1184ae =
1771107551 0.999 30 0xc3747ae7be29009e25a2d4b5378e6b333c58c8fb7aebfb87b526edb4025a115c =
1771107551 0.999 10 0xd5ad985ed9154b21c9fff7055ebd86c6e9ad4d00e833a4443b89d4e35681ce00 =
1771107553 0.999 15 0x0809d93e0e3cc57f601d71a0ab8456b6e75728474420104217c9b57e92b54cc4 =
1771108623 0.999 56.53 0x4d1886fc685ff46fc65e6c3b8fa4ff674fefcba2250d602ebaf0b02d83d83c23 =
1771108685 0.999 5 0x5f487147d9061ffb088084b247542b69b75da45412fceb2f9635e410eaa4119d =
1771108685 0.999 29 0x928e5f02cba21ee79ba80f14d205f81ddcc4c26e9023f8f410952c04876425fd =
1771108861 0.999 5 0xa2a91a8d7f9b46ee84b08c18e635fbb6c64b628b1f4ffb07e8d7aac006c0c0b4 =
1771108881 0.999 5 0xd083bdadc7da6a3d5f22d4c8dccfcf1f4616e6cfc745c509b13b5697cec7d712 =
1771108901 0.999 5 0x087e9bf24129a4a233858a846b9ae73556dd3b1b282e71a0e04ab0ceeda9c5cd =
1771108967 0.999 35 0x1a335236bc64ddee620f46c510fc0cf4941fa606d8f530d820cf1e128e95acf3 =
1771108971 0.999 15 0x3f05ae0c0bbd4e069be24b1c37bf881fbaf088213e30029f56a7a79a90f3f5cf =
1771109107 0.999 176 0x356d8f74dc76a54f15de49aacb8f24ab5f7b5fc3166ef8aa3f79078b17319669 =
1771110711 0.9985234313 12.59 0x3051d035d838e108877083208e3eae2fc03171566e1ace3a17f8ea42e4839fe8 =
1771113111 0.999 39 0xb0c6b96f78088771052dabc17e79d9d50557ba15d1f35c87bad97e69443e922b =
1771113883 0.999 20 0x3b3ff45b21017427faabe2547590f989e6d6f131c05624b5feb4a82b973844d2 =
1771113895 0.999 16.21 0xd599166653eb529d0472bd28b263e8774dd6aea0dbda82c2c54686930db26586 =
1771117403 0.999 22 0xfee1774a14caa5e10349291b56df6402c0e3bd94dd31075805fa65dc29d50a1b =
1771119799 0.999 55 0xe5d4871622f462f6bb964e0d6586e5899784d590107b7290af9248255359cec5 =
1771119805 0.999 45.73 0xbc060c03cae97426c1afa69b031d575fb1fa1b7683c65f89fc582326bc716517 =
1771119901 0.99875 20 0x2ff496ceb36aa9c69fd1c4c26b4f2d9019c9d73fb8477090aa97f0fa131e3429 =
1771119901 0.999 100 0xc5b2e5e96204b71dcb5a90d0e327370f0bc0a9151991c7aee5d7eb00f38e064e =
1771119903 0.999 50 0x65ae82c39b57e49628724724a897f66e3043c1519f399121b55bbcd0dd394bf9 =
1771119903 0.999 5 0xa4de9b762251b4d5f7064c746b0df297c5841ce9326889f80a656133e88cc987 =
1771119909 0.999 57 0x8aff31244e2f675ce30ea11fd9770cb70db0b8fe32f3a8046bc3a85d5d350010 =
1771120137 0.999 20 0x5d3db3ec50b4c7b5e75fd0b2b8604b2942c367735556c465d469c56d78fcc419 =
1771120137 0.999 5 0xb27b1d370675da5b3c88a7ba633a7e08e6f0fd95a9ff06f8e757bc5f726f34d6 =
1771120137 0.999 5 0xd6ba2bcfb36abe1dc80405c1224b6c4a122ad3919ed7e002823dc9a8fa9eb754 =
1771120151 0.999 5 0x9e4e4f0a4749b03f7cae829d2c66ca200404addaf0ad9b04bf018ce65e9ac8fe =
1771130469 0.999 10.94 0xc124037aa1df0493581d626304ef15364efe5aad912e52ded5c83d8d837e1af5 =
1771130527 0.999 21.22 0x4a993d35db74fa29dcff2e6ba4365de9501b752f20f11507c1afcac7799d0698 =
1771130545 0.999 16 0xfa162ff8a9ef28dab90f39d8742832b4944f8f417aa988b87593cddad7fffdb9 =
1771130547 0.999 17 0xc09fa6e493ed48678c995405ee7868b47104915186b6590c4df9180c5aed2e39 =
1771130547 0.999 5.97 0xfa544323fae9761ac2c0b91e754691454ea477587d6aea176e3d51d6c97140fd =
1771130555 0.999 16 0x3c9e7d9bde9069c70968f32a5d6a211dce2dd3c1f34acb833ee15635fdddeef1 =
1771130563 0.999 17.79 0xd4ac38cd21c249bf9811b1aade3681ff6c159e01850d272cbfb70f7e8ff0f822 =
1771135849 0.999 30 0x130d1dbf649bb2a8fe896304e6fc97b38ba2f1decdf311ac200e4109060f27b0 =
1771135849 0.999 20 0xcc4b80e9973037d9e5c39ea3fe86058a86f6546ab471f617243cfb7a7d97dd53 =
1771135851 0.999 479 0x34a30874a0e88a5a241b511d1752c40d48f06a87f654aedc23b8122a55d3a0bb =
1771135863 0.999 5.43 0x89f67c1c948c54212287bf87d457b1799de2daf10ef203a41ed8f5ca81561bb9 =
1771136045 0.9989312977 131 0x7120dd43206195ae306bf768ae5964b240d20b0053ca0a6360bfa2c7ba62035a =
1771136045 0.998 20 0x98080a4dee3735de6ac9bc1c92994833c857f8fa39f12fa9ed912ebecb99e4d9 =
1771136201 0.9978 5 0xb88b12a5eef6394a24b68606e1ee82810ce0ea34591858f09349906b84fe4e91 =
1771136203 0.997 5 0x6d1441faab4ab1fd1c765b94033c10ee87a91a76e76fbde973675e7252727d07 =
1771136741 0.997 5 0x1b6b3b77b92d2cffc8be32787b90771e7e54356a0c682b85ecfe2cb9f14b304e =
1771136907 0.996 15 0x5e47fb126d62b8ee054a996ce714233b1653b49314bee0702ae5d0204177b643 =
1771137995 0.997 33 0x7d205c96aa7fe47a0dc8cf542c1c035298fb188a9dcedea2b9bf309cb823d4ba =
1771137995 0.997 35 0xe9fee836144fd40c3c59934f316eec733cfb3ed235335369aa7e546e0739e9cc =
1771138005 0.999 6.36 0x8eeb2cf830d51af63a1d1cfe505c2e028574066902e675c45dcd659b8f185e7e =
1771153219 0.999 5 0xed7e085eab8c3833569f7a0c0a6a55525a0501faf87a753e79a2df7b06f67498 =
@1347953 Yes
1770483033 0.01 6.12 0xef5f2ec0da9cfd1a090ec41e6519505fac520f32da20eabf2e3db19dea193181 =
1770483035 0.01 57 0xa20e90a7dfe4240dfbb6bb966be00a1da5ea6679492f0cd2675e5ca89415b259 =
1770483037 0.01 11.58 0xcdd817e29076a676ae42c72a92de91884d9a476844a1e762e45209f4e42ccf59 =
1770488689 0.001 37.42 0x73faeb8d367768acc10c7a0d59da3c54f7d68b9d8ea53a8e94bde73d64e557ab =
1770551451 0.0127638685 156.692307 0xf7a6c33478898db199e8ea9b6fc08ac1963b5d324c0e1de4d1d2a3956da5648d =
1770551551 0.001 0.25 0x4c3e6886ecd12a4f6b62503e4eaeb66ed965087a39670636288b7dd14485b4ae =
1770713555 0.011 0.47 0x1bd1d9a56cb12f585c5bec6fb3a49a66d2ceb1685b245ca73dba623a27f28829 =
1770898647 0.01 2.41 0xe888685a6636920a5763ad56d66113b0f51716f7b64c65ee19310251ce75b2ea =
1770948053 0.011 2 0xb7f651cf3a663ce4a5893bd9a9e21187542c2c6b39c2b9d9683b95f0a5783adf =
1771107825 0.001 4.08 0xcae79e2be3987515d2676741c2303bfd396dc45853de7271729cac2671189052 =
1771108931 0.001 38.09 0x199a92075c9c0ac8fc08afff055e290867123aa0cd4f85a8de8244e38510511b =
1771108949 0.001 89.22 0xce0ebd774e7b7c0e1d49ac6f6cafa8ce4e754eca23f567de37cd141ca6e3dd51 =
1771109083 0.001 15 0xd3ba8f3e75a1258bf86e943426214c34eea935d060f716bb9be74dc0a2df6bfe =
1771120435 0.001 10 0x17a6d3e4d146bb8ea12ef07a02580e8fee121fe4b0658c0a8965780ff8a76ef8 =
1771120785 0.001 22 0x3793e446c23ab9792c7a5114fc8ffb96e1ef175b5d6af2246e62cdd258d46d9f =
1771121199 0.001 102 0x9d4954a1ca801b62b887b42d453d2602077e4ee83bbfb44cb82a24c94732b339 =
1771123531 0.001 6 0x09b170b3f29f227293147e1691732e9e45e8cba25b8e14b44bd133aeee7dcce5 =
1771135863 0.0083397231 124.704261 0xf7ec817c243b016c413d22cb5479f9ed335688479255d520196efde8c2f04e39 =
1771137587 0.004 71 0x9674f936df98c81d88a7d1de8a07da1de3f8abd061ebebe39ba5216400d0038d =
1771137995 0.008 238.09 0x9f4b9b54aecf31ef428c06cf90ed5cc34c3c747ba7edc58e89b44981373a2c3f =
1771137995 0.0081756696 134.545555 0xdfa33388c3f0a568d44725521532e1049bfd08421a25eb1fbbb0e3f4bb0fb7f3 =
1771137997 0.009 238.09 0x0a79fe5edf24f8b80db87b5ca305efe8e54fb6a1a16f8094b1d325f2518b3319 =
1771137997 0.009 238.09 0x291ea933b9bdbd8129e093f95f5dd0d673e36dfadb3060b4af91e9faaaea13c1 =
1771137997 0.009 238.09 0xf5aaf06d05047d3b0ca9db0bfd4ce27343d86add6b95b5aba07556018fbd1ace =
1771137999 0.001 21.75 0x0e62f1a1d765a37c40dd85039b3f070d9971bd58d3915f2664eaebb2c7b42682 =
1771137999 0.009 238.09 0xcc792fe946b03143c40a9059104a8663264d24104eb76b3d9c0eeca879a26a3c =
1771138001 0.001 31.36 0x6d6be9660d5d20e379e4531ab074f87733c432595f91e6458f0f817e7f4a92da =
1771138001 0.0090726196 238.09 0xba2d1951676eafdce0e449534a62052ed3e72f00bb9859170b8295a4304ad4fd =
1771138003 0.001 30.94 0xad0ea44fbbb165cf3bce0562643c019c9c809b11ea639b13c3fd249eafc41a8f =
1771138005 0.01 238.09 0xf13867993f315bda57088934ad46a71933273f83d264b569c67b47ef9935a226 =
1771138005 0.01 238.09 0xf2cd43af10c5db1bdbcb9345c55e271f667a1802f407435bbc7f71db7ee11ae4 =
1771138009 0.01 238.09 0x7e5de044953823c92eb6a482f9460fda0083d2172e232e5af2645263151d8a46 =
1771138009 0.001 124.7 0xd2b167084a6e9538d5ddae68ba4381d9455bfa4885af85a9fac891d6ac9d93d5 =
1771158059 0.003 83.1 0x1686412344990490651c1f178a057d62bcf215a0aa87c8b75c28a77cab5a2359 =
1771167999 0.001 5 0x05d86cf1e0d53eba1fc429fed077bc5c9d89068eb1fef14921e2274e5524a16b =
1771178531 0.001 1000 0x4bea05855d831eafab607aa86ca4faefab78157fb7f2fd32a4d30c1213bb999f =
@1347953 No
1770415073 0.98 59.99 0xfb7a3f6cc05fc167bbb8040c62f33e4267329232ca4a642bca967d904c3ae908 =
1770426179 0.98 10 0xbf628c145da49392aba8ed02d8281011316f6d00627fc44c13b53b95dd112d9b =
1770426179 0.98 18.0306 0xd32b7e81cfb37d02b16c52b0cbe931a08dbaf3fb11bc7f3df862c143611e4938 =
1770458431 0.98 10 0xa87d764ee43b4a5ec42b4494cbbc1ff95db6de247c443bd1eb043b87ccee5e8e =
1770462375 0.98 7.04 0x709f0d570c64d92f2474b64ae940c6da881a2ede6164e00452cd9703a75ffd34 =
1770462393 0.98 5.23 0x1de5348d478f853d5c70dcd4a554864a547845adfb72ba305c70ab29e7635adf =
1770464351 0.9865428571 28 0xbe2af4c09d34036fdacb533ccda2cbbc9129b4f44fbc153d09c5759b2175660c =
1770464365 0.99 28 0x86312c8eb3fa73096afbad9fcf90b051f60cbbcc5d55c18a6ffcce0bdd41dc79 =
1770466975 0.99 8.0909 0x427edd466d7a902f8a924bcedabe90e246df0c0e7e071f71f9f8639b5dcf4851 =
1770473065 0.99 57 0xa77a51cb15637cf17de381ebc4f615a55e5a518ac4d1c169b57c28e6d9441509 =
1770475253 0.99 13.88 0x69d2a711111c2f7eed7927153f419dbc4fbdc146bdbfa0f39db52e803666a2b2 =
1770706299 0.999 10 0xedb15761b82207eb08d7c14f29aed0ee589f227e00b1fb9b1de5ba8d2dcd6741 =
1770706301 0.999 20 0x97ec01e4a0de05cfb186ade56dedf4178a981531fcb891bf158f0fa18e02977d =
1770713319 0.989 17 0xb7dbf52b5ce7c9d7e3cbc118aae060f83f95a543fd407c9afbde33db35c176dc =
1770713725 0.989 23 0x066f037f343964b2dd79a941be2b378d2787f5bf648e11dfa617d188ae015d95 =
1770713725 0.989 10 0x2081c541befd3a8a90a5a08e0ca0957ba054cd89ffa15383751414727eb9ab9f =
1770713725 0.989 30 0x703fd940d82d062e4e029057d353be98bf14ce26bc8dd0495944bcd43abe0bf7 =
1770757167 0.993 6.46 0x7a6158c37344048d1c6cc255cee721ce4e312a9d95d42fcba36af994db509d58 =
1770762825 0.993 64.94 0x69ee2e3d0c115ac146f3d2cea81c936df20930678590c303513e9aa7adf38898 =
1770827589 0.999 10 0x29f2f3112425a7d0c50ba5e033ca3c253d3592e5f96a563beb5c6109d0c086dc =
1770871293 0.99 5.8888 0x2f08c52434ac9d86669766a5cba654863f5f73af540f67c7a67f47e08706f97a =
1770871753 0.99 30 0x271189b17d0ef0b54417228d99492c173c96de392fbbaecae3c9c86337c57d64 =
1770905533 0.99 56.49 0xc203e20985965e30f9afaf044c7e9897ad9759d9962ada32a3c7fbf4c6f378bd =
1770935453 0.99 5 0x8bb4d7b9a431a124d745bba6ad7e52af1440b002ddb193e3ed12d00878a29f38 =
1770941197 0.998937 30 0xb70b1fd9e7eb37f543bc3592d3b4a84a225b4b9b311d7c8e975f5a88f386bb2d =
1770941205 0.999 71.25 0x94b69695735f6e00b45b5da0500784cb336dd77e6dc13a60a19c399e458d35cc =
1770941223 0.999 71.25 0xdb0b901e9e7fcc52c60414193682850015ad3743a33c6ad42b3e6a41ebdfa920 =
1770946273 0.989 5 0x0d01836c551e329384d3968c16ba6874d79a7624226ae3f82e85dd231ecbe9ae =
1770950449 0.99 5 0xbfc36fee7df7ff303a4acc272720468f4598b2a69acf7d706594464e56370ba7 =
1770951707 0.9964285714 35 0xcf21059c31327333c8d042877c3461bf41cb36976c267bdc3e9295d1ce1d4075 =
1771062147 0.996 5.91 0xb7e3a50fab1bef6d3507efe5f71a067c4ae009f7b448d4310033a5bb1342e61e =
1771064729 0.996 17.61 0x9b12b42e988a852dd25e41e051a0fdbe545eb41502dd0657b4a6f06dfec15e55 =
1771065747 0.996 20 0x2f4e69cc54531b59bb2f26b487c6bd65f34ac89884fda0c1a87e57726c0ceb8b =
1771076085 0.996726 20 0x9259f31e390012b8e14e5f7f3305a9d6d2f985166aab395d5835be774fa908a4 =
1771085531 0.997 20 0x0506cdaaefb1155356d13ebf340b6913685a41a78a794ba4e5d0b72c9b8d7e62 =
1771086149 0.997 5.78 0xca7d8ef1d1a5bef236fda9e6c9fd25e83637d4d283cc0186d2f609137142b2a5 =
1771088985 0.997 5.56 0xf9d1b8961503ac1983b2f4801e3110754c90d52f4bdc2c373a5db0c841f50004 =
1771089711 0.998786 20 0x72e030e9bd48d2f8b68bfa301ccdedc98134183b10fb9412b913f8326dce6083 =
1771103733 0.999 20 0xcd20c55c542276440d46512d2b35b4964cfd0a8d1134de19ad84339d6fa56fe9 =
1771107441 0.999 1.9 0x814e35659a89e7961ba256b3b39db35fa132d6af7bcb1c817a82f64ab5fbdf2a =
1771107551 0.999 30 0x3bcebf8f05857a03c9a181d41f95db20df28c1119351263c791d1a6ea8f2a04b =
1771107551 0.999 10 0x92db5247c234cf8a2c974a136a776b93a7af579d9f4d449924c22c508b1f5982 =
1771107553 0.999 15 0x949de679dd04f64c4866b5f83208062a2844fdc8cfada3c18a0226f3cdfc3ae7 =
1771108623 0.999 56.53 0xd1d4b2c602f9cb864dabe8b19aeeac62dcb8615377575802761cdeb09118b667 =
1771108685 0.999 5 0x415af5610c13ca609029c819c0c8b70ec3862b2b7755bbba42f3f70d8cea8b43 =
1771108685 0.999 29 0xc2f36854e59c6373909aa9c65071654656bf285ea2533843f4967d71a821893e =
1771108861 0.999 5 0x9326851d48cd5bfccea2df452b2873c303b9d301cc12e4d3e6b4b812a6bf4bec =
1771108881 0.999 5 0x9d70717699e84fe31732900d58f115b2f8f6c314cbc126612432ae0b5a07517f =
1771108903 0.999 5 0xfa75a75ac40f03d4267b1d678cdb470e39de6f55d5b26fd706e648f6d1461402 =
1771108967 0.999 35 0xf148c8fa0084832b9aaf4ceca5329fa8072303125b30e4b90f292c49e9faeaf0 =
1771108971 0.999 15 0xcbdedd5091a8c87493cc24a3c7e03d04fb631f2815fbe705196101907d9228ff =
1771109105 0.999 176 0xa52dc930320e2ec27ae1f573573dee0bb4413cb722d2ff9fea93b83888d62a80 =
1771110711 0.999 5 0xc91b73366bb1a8493ba6652bb652e417829bcaebc106bb3891986b003662053b =
1771130469 0.999 10.94 0xddd5c54fd55f192c60b00c26ffa15e59819e810550d22c8c15384fbbd59786ec =
1771130527 0.999 21.22 0x0a8313e68d21a97d7d7bbe2fc3e1afb925c568ca38ff04d3b1b4868be77b7464 =
1771130545 0.999 16 0xa8654f9d9a34d54974b61afb75cd948688a22260a80b060ea7dd1e6a325f7417 =
1771130547 0.999 17 0xd0c32b6fd1302d516acb8011982991a3c8dcd829e0d22dd7a348820a4daeed05 =
1771130547 0.999 5.97 0xf6a274d5bea38057effe62861b6112b692e9f2e5f3fae3559a608b279acb12cb =
1771130555 0.999 16 0x4b6e97e8280ef1f4f165ffc591e20596e41f66735983f5ff7f8316828291ed62 =
1771130565 0.999 17.79 0x91418c359075020bdbf7ad604d105991141a24ada649e492d723f60009776fd6 =
1771130581 0.999 8.19 0x8822dd397cc087e71f990ef22ca2e6587fe95e130ad348afee751adb4413ea4b =
1771135849 0.999 20 0x32d598a7a17557547d985013c1c1ea022483268c5fe28e562eeec0d7631e6577 =
1771135851 0.999 30 0x810b3de1620ed7579e24ea710b41337825c2ec896437bf1b5a5aea686b5654c9 =
1771135851 0.999 511 0xb1017264e55c966157c422285970a2bf516fc522e42e7dad3c03e7ec093e8f63 =
1771135857 0.999 71.25 0x6e09a03e28fa72b6f7e9f0a72497b9a6aed61206c038072f084a04f9097a0752 =
1771136045 0.999 131 0xc14784691b8f3bad99c480489723920450c1fe6b104dd3c061c3d72d2bb040c4 =
1771136045 0.999 20 0xfb6d6edcafe68b6d9c9d0cb1ebd0ba68524b2949a7b67d834dcf623a093ea8fb =
1771136201 0.997 5 0xcad014019626936a96fba3f547322c7857bd628a053ba1d97362a65ffbac678c =
1771136203 0.997 5 0xdb135038b6dc5034d59d8aadf0249f68da3344d6d60ac788b67d73a2f161c933 =
1771136741 0.995 5 0xd8029d5a8537fb5f813bd2999afba2ec639f836d2ca0e31ed68e7f4a5ddf7ddb =
1771136907 0.996 15 0x7509430d7b053238b44af51fb413ea45473e59df0f8cc31b25a9cf8a8514a2f8 =
1771137995 0.999 263 0x9e0eb3a9d1d502f0d5dfa5738e7bd458f0733a8236337984d7fd1a44ff773d8e =
1771137995 0.999 35 0xd67aa15eb536762186d8a640ce3871b39f1206c7c26a47ece29acfcfc6ddb928 =
1771137995 0.999 1.28 0xf7dfc1ab9f7a295d6985761eebbf2e0f52d09c22c72810cb5bcb52d3646fda97 =
1771137997 0.999 263 0x8de0af9a156f5d1d337af374197a8d369561be3a1758234fe1c80977c4be20dd =
1771138005 0.999 6.36 0x24fc000e78a19e2e6880e4168f502ebcaf1def34d527ebbed31d5ebfd760856e =
1771138387 0.998 10 0xbc3945c0c75299442c5b18ce8e8db9ae0a2b3b140155704faa8245457f60978c =
1771138387 0.998 10 0xff088281309a6d5d5c06e650981653248311db9610c8bce0862338d30e91a6ba =
1771148817 0.997 321 0x56e05f09ab82a89ef68a474d0f650abf66ab44aa7d9cc5882a4dac63bdd62c6f =
1771148819 0.997 331 0xab0c2170cd6388e4bd36e8f20889c2c01ff9d8108a53562b74133fe3b8f3c809 =
1771148929 0.997 238 0xe3d2ffc50946933320d95f67ac75541ce3b3f3c0594cb44361b26fee112086bb =
1771153219 0.997 20 0x157fa7e31d443d29d7c8388cc0b18a7c7c0f26fee724ac6f97e3d83683dc22bd =
1771153227 0.997 31 0x1896506f8cd0d49ddf24798297d54840236c62d44e201aa2644191753bb3d8d2 =
1771155107 0.997 10 0x329829df264fa3efea117f42dfba4aff6a8df6f529264537ad85c79b784cd69b =
1771155109 0.997 20.1 0x0e60cb2251848e96ee0258e6aec828b0bc78c57641126e5f81336d51d943adf1 =
1771155109 0.997 10 0xf2d80694964c0050c7daffd7039b667f7eb2cc7aa4305b2dd2f61879a3cc20ae =
1771157435 0.9979032609 92 0xf600e87b3013a865f5add9ac69a8d57972bdcb9e4ee22a910fe4df2bc153650e =
1771157837 0.997 12.5 0xad4c346c3f38b54ac454b1d9c017e7f547d5c132688a5e8bb5e3ca6a948a807c =
1771160817 0.998 299 0x5eddb921bc343f12a1c532db277ac69469f709b69866b97f2b069017eafd8f27 =
1771160817 0.998 15 0xd9804ef5e2b569578d3a553f67699bf8d542150fb9a84be48e0cb84c42667e2c =
1771160825 0.998 57 0xe77911bb884af5e070477a326a74533a2564157c8421ec61cdbbcd3a5254cefc =
1771161779 0.998 15 0x2586c0b271f32dd1a696cc0712722cb4b350ccb9a84c5baa30655d7876a332b8 =
1771161937 0.998 14.49 0x59e29d464d6c81d36704f80137322c565b7f471ee9dacd6a9c2770f894ecc0a8 =
1771161937 0.998 15.51 0xa61591f825706f635eef13b51963cd2ef8323652ccf0a46238af6fc172b034e8 =
1771165497 0.998 40 0xf8d455972904a89654e092b61b04733a2706a36f1a041c7cc3fb8818a232e520 =
1771165763 0.998 13.7 0x7ed954971004c2a395050949aabed6ebfaed77cef71f35c5309fba4aa2cbd9a4 =
1771165763 0.998 20 0xcd7289054f0871aaaaf2c9d803a47805ab811ed75f66d156d4e5429910c0ff29 =
1771165777 0.998 20 0x0c1e7aacf30044ba652203f0c5cca6acf242ea6a68059ad5ca7c2ca1f9f18d23 =
1771165779 0.998 26 0x6edcf07c2f51b2d7d4e1bcc18bee8139d51c7de7835ba7a2b8a61880f1f184a4 =
1771165781 0.998 14 0xd020454599982ab4eb988f16cd0c2d6efbdb6aac2447d03c9c3840d90366945e =
1771166201 0.998 20 0xdb905ac52a2e9c6822a85d6c0b56cb3e0cb0d5ec735c54cf8b740dc66ba76d78 =
1771166483 0.998 7.5 0x20f8b035814efa5e3f41480605a1bfa608b889ef21f8aae97df85aaa8ee1013e =
1771166867 0.998 7.18 0x782b42d465c6e0301941abec45007bff9d57ae47b6a391ce24e5f16abead5a63 =
1771167003 0.998 20 0x21e03a54b83820320e6f07ea1b2137f1e42d2c5a20d6f785194aee1fc5baf04c =
1771167003 0.9989448458 227 0x4ab2eb0d8bdf8c45fbd8a2906bfe4b4320ee1c776ee2c4142bdd0be03157e21a =
1771167003 0.999 15 0xa5729363dc98b51b3ccda8d502a27ba866429f1efda5f9ef889a0fc0e683a8c5 =
1771167025 0.999 30 0x57ecce1ffc2de398fbd8882f1921ca0cda5fd39be84ac7f202b0e8aca6cc6e39 =
1771167025 0.999 40 0x8be1bffcbd4de17bda9f74620521e463d067eb54a453b7ec63b428ee37a2aeb5 =
1771167331 0.999 403 0x0139c5935dfb0dba28058a286c08980dd2bf69c4f9ee9bb7dca3adeeefe8110d =
1771167675 0.999 8.47 0x8f3ccd8bfe7e21af3b13ea78f8de9cc6f0b52c1d74640d47bcb0fc2bb2598ecc =
1771167677 0.999 20 0x71f3519103f042fb55a1e551497c54f3d8387757b120b763f891fa35cac2add4 =
1771169541 0.999 50.87 0x5d7bb777565692d6df62f47d66ef8f0efd282d890d81c9ed0ae51000798c154d =
1771170011 0.999 54.49 0xda321dcbd89ad9f5f504fa2bbb8a2a7565933cd45418734d1fd3a2e9ab86255c =
1771170249 0.999 281 0x8bac0910d1772d17136c10908dbc0acef6bd2a8462c099f6001b768e98949a11 =
1771170343 0.999 16.856 0x8876c0df61909004d749c3daf3a8113a8790df18ba352fc3eb11f3b0e7503939 =
1771170353 0.999 30 0x42125c84cfcb66571ec5cbc57b2dd387a48ad8fe21633b30a04151752d68551e =
1771170353 0.999 45.83 0xdb562100d0f8c34098c27163e3fdc35e534bdc708d51e4e6cf84c7c21293ccae =
1771170403 0.999 5 0xff35f0ea72e563716dc4a2458e01f29aa5573e5ceb23e86ae261e615a339b005 =
@1347954 Yes
1770483047 0.001 48.12 0x774c21f481a56bd784fe2e9cab70b6d1e827c00eeff86e7bd97eaf9c6727990e =
1770483047 0.001 16.59 0xab4c6b2f07f2ac11821327375ca59e1b6815c1664f5b0acc755b87f8838ac834 =
1770855869 0.001 100 0x2c76316289fd83ea3b10c92c0258cfc50a1752aee3571c36e7a35cf17ea96e95 =
1770941013 0.001 47.41 0x9e3ea2c0557bd66939165ccefff33ef7e593b26d43dac8715d9bd1577269da74 =
1770941023 0.01 52.59 0x93628ccc34be6aa2ae94c60e937e09c376d4d2d63840aef53aa7e42e9012d839 =
1770941241 0.001 17.54 0xc2778e6504115d65118008cff890b66df97a350b4c7172d81f0a0d231f4e991f =
1770941259 0.001 6.46 0xdf5e2fadb4ce47cce1f3d020b7bffff69cc22dd4d06250d1b8c8802d4c50a000 =
1770941427 0.001 30 0x753e1db4cdb2cade7043ba66fa40b5227f8a2a14b583026cd4f3c373966a0ac6 =
1770942099 0.001 198 0x06c1a8338bde2f32f146aba575728fa297ce7859ecb45f4c770f07a5c0f6508d =
1770946399 0.001 5 0x00dc2d72d4dcab4b82bc804214700b34b09dbe83cf8cb53d12d4b79076518d18 =
1770948137 0.001 5 0xaea2d4568c67c1dc0e63d2877d52930ec1698c2c5f5dcc2daab260682c80a98e =
1771142999 0.004429 100 0x5401440374e539d51c6a3d037952fe009254f50161812b8519e9e1dac6f4f839 =
1771143565 0.001 30 0x2389935cfff1db675e6a335998564bef2080d0072f0c424efdf9e97362985823 =
1771143569 0.001 4.08 0xde75706eb6a04d1030fcc3b38f85aa59824b92353bcdc529f4af8c077ec33ea5 =
1771143577 0.001 86.53 0xc26dbec7f65e794d433a8a8e99124a78daec2f2f87249779058b1f6968b6501a =
1771143579 0.001 5.39 0x36641e8d05a29c6085a881b6c0d28aaa0325d215f9bf1ceed3da1c1e90ece2d6 =
1771143641 0.001 5 0x00830ecf636dc4cda0c8571b4b4b440dae32e3beec28e987a5ffba59bf168818 =
1771143707 0.001 50 0x61d5d1b2846508c055207299cd91952081dcf7ba1e7ef8b482d835d35b1fdda2 =
1771178531 0.001 1000 0x10dc210e55505948a128f8747ef4a742b2c66846678e9a14d4a5d504425d3e4c =
@1347954 No
1770415161 0.98 59.99 0x82dd7e40d375b2652b13adefc0fb156644869f71b6af4d7256873c2e5d4fc853 =
1770426169 0.99 18.0303 0x39484b6b7fadd955db20955fb67b585d24f96b64f8432ef6aa0ef9aa3eb97e5d =
1770426179 0.99 10 0x7901fe3358054a25b57289b0ad98a03bb74083a466ddf49e926cc299e1749784 =
1770458431 0.99 10 0x335cafb0db32178621193838ecbe62c138e3eab811a7bfa5900e2182a87c0f59 =
1770462375 0.99 7.04 0x8e07e5758063fe183ea8ad916075daefee36e928e2c39763a07b66a9bc0352a6 =
1770462393 0.99 5.23 0x7e09e2ebf5e0d95f20cd6b058e87451ba0ef27a4a2e313aaf0597ffe024bf216 =
1770464351 0.99 28 0xdd36969c01aa1d2beaad1d38968e734f2fbc0f77bf01d60ac025cdf13294f960 =
1770464367 0.99 28 0xd6baa8bbb53ec4c6ffe1c5fd3deb9843c58e3869b0eb4748e83bf871caee15f7 =
1770466975 0.99 8.0909 0x9eae3127243011e58cc0a88f73949c8dee3183b5f35f040b81610003271c1739 =
1770473065 0.9933805263 57 0xe549979780f0760241203d370e363fefda5422ec717d3a9a9c29d0b0edacd702 =
1770475253 0.999 13.88 0x0d86a0f5495a9fa5465ef8044f9cdf84d5e85aec80f1e192dca1d18ee0c0f4f3 =
1770950449 0.999 5 0xb584320f1eccada62c70d400571406db2c7ba47edf699c44053c8813b7a67105 =
1770951707 0.999 35 0xd354e5192a902cdaadb39965752e0b50877b6555ac026fd93f8dbba26bfec985 =
@1347955 Yes
1770483057 0.03 48.12 0x6b4798ebb605b145e8035e9228d2821afdb5aecc79e15883ee84892f8a0947a0 =
1770483059 0.03 64 0xd199d827519e5fd1ad4bcfdc93f2c7517585e6dcaf833be2f447e6dc6084e436 =
1770539111 0.03 0.25 0x9b738f08883ffc723d292097c30179461d61900651f2d01023c8008f7eef751b =
1770713555 0.03 0.47 0xd56b25717a29bb1b5ea189c633c8ed1146e30040fe7dd197a4c0172b14bdbb3f =
1770898647 0.032 2.41 0x2913e1f0889e1a1fd17402dc4f4c86b5d2c184b398a3c197f459d0eafd310797 =
1770948165 0.011 5 0x5357556da46f58a71831cff21243eac3d26e952eea47d7996411c153664cc10c =
1770951529 0.019 100 0xf5faf50e955e2cb34e1add19a260677f7ab37ab9ae91c6b0831ee6397aae1fef =
1771104241 0.0479015817 45.52 0xac5b62a3425cc097b07591850f0c5476349a65561125fc8cc75894063ef3618f =
1771107825 0.016 4.08 0x3f55636f1da2a1cc3c741f8a1bb6cac699817ff9fbae061a9e8175e877acc684 =
1771136833 0.026 6 0xe90f1dca784769402f4a87d59963c9a1210a68d1374fa03b0b626db57a9744d8 =
1771139861 0.025 25 0x3a3bc2c88448764367342822c8df2a2b73f32d178e207233a67b59b20cbfe9af =
1771139911 0.025 425.75 0xe585b97161ca82ca9a217fa3922eb4a5885d4808007319d287a272ef76222a08 =
1771139913 0.026 5 0x8ab6a37aee23bf9279949b56a10de98209a628108c3bbca89aee531f39a6bdaf =
1771149285 0.031 15.04 0x08707aa6dd1bdd448ea5d9e30cff3274c11bd742a9fe3a5d6b97fe2cdecd1af4 =
1771149287 0.031 15.04 0xaeb2422552c7f1a41bed269b9d6e796a1348bf2da73bee6790e5d472f07c7b04 =
1771151775 0.032 31.25 0xacf56381db240aa50cf3bdba7669b8bd6fc7b953cbe6cd0125b96c367f0c45b3 =
1771153793 0.031 9.98 0x2f7103206163225f3628953f7d2547e9e9227fcece373ca5eb7eabe82c736678 =
1771155441 0.032 50 0xb11f2a6d48aca6ad238ad38cbcd3d0b352fadcc8bfb3a542c686e5496d540724 =
1771169009 0.0357320101 27.986111 0x77f9d70fd7da5cb617acd346b274b9998cee32ca0697c16820f94e07a4c578fe =
1771170287 0.038 40 0xaf2a5a0c0c6ffac5970129604d37ebb9e727f45438c341a7d7893af106962e84 =
1771171473 0.0313836952 76.91 0x4d05a0f27e9cd4e50e99bd30a6d7de80053a1e5919a1702649cd58ef25a4e34e =
1771171573 0.027 3.52 0xb9fc14ac0fb5d7458e046a7285c943cd42000bd43318ddc4416d75c38ca904fc =
1771171887 0.0476409171 209.9036 0x89500579aa2e33c23f7fb0955de31af174bd4832e09d6a7b70597f00b0092df8 =
1771172111 0.0462919011 43.20408 0x877c19efe3c6c9d0284ca181bd1be3f7484c0c6eac651cc7c2198f15280586a7 =
1771172759 0.024 8.52 0x06d81e2298e8c8786f68e12b123844491f20f21fd0918f5742817814ae624175 =
1771172769 0.025 182.83 0x55c2385371affd20914a8a2c2de40670c5ae1ab96cddcd72c19f0923f010b2fc =
1771172769 0.024 15.98 0xcc9ea8386486907768011e03ff8540c00e190c4887d21c02a5e4337b81b2113e =
1771173525 0.0257202 50 0x46b39baa97a7e24fff232b1f312af37aeef7ba465b76652c2e5c8c3147407597 =
1771173537 0.0010592718 4724 0x12f18abe774278552bb09fa866a175df704873aef7960cce447d34cec1c029d3 =
1771173537 0.001 3660 0x9ae50742a2ff17152e5e5b87e4307a783bf6dd2361b02f90f2275c6d701ec292 =
1771178533 0.001 1000 0x1206e60f3254970a2d955fd9fa80780e9bf716db4fc604bc66c1d355d0f77657 =
@1347955 No
1770426179 0.96 18.03125 0xb05fcf5779cccf725f5ece1219dd06f5cf05375acadf0820fc050a9d35973192 =
1770426179 0.96 10 0xcb62c7bf16cd67f5a99aaced765fba202c6c3e942afa6cfeee636a3f139287b3 =
1770458431 0.9680539116 10.0201 0x6eb5bbbaa33f551424913d78f8ac278e11647b84305d0d1dd3476e2460783981 =
1770462375 0.97 7.04 0xb1ad73da9e3a75ac38c00536ed5495394a07245319d58ce9ff1a7c5984c13116 =
1770462393 0.97 5.23 0xa4ae0ede1b50275ffd70e63270084bdfc8d62d6c447e54a6f4257dff881ba434 =
1770464351 0.97 28 0xcf09496cacf311a95e5ce5474ebaf519bc1214a53e48c7a9ec1d9d94ecd2b515 =
1770464365 0.97 28 0xa8868d3e35b9eadf90969592bdef322c9f47b106e79aa4602e54bfc1bcc416e8 =
1770466975 0.9699999975 8.092766 0x35910ed95b0ad834aa7c2f97d57a0547177902d4544b2b700fc2daee78197971 =
1770473065 0.97 57 0x5496f462d0045dae04fdf41cf04ff5afde35e3cd0740d66ef2f31e9ead3c3e0e =
1770475253 0.97 13.88 0x1592a6f6439e3b0d90fe7094dd29ae926bf112b752a5ce102438c4f051aa925f =
1770706299 0.97 10 0x223607aa627899b54a5974350e2819c63a0a9548bc1ce67f559ab129a76c48e2 =
1770706301 0.97 20 0x19024abbe86e53f01289188795a59de1293fdfddad3a7f0525c4f5cd1a76f2ec =
1770713319 0.97 17 0xda37b23444586cebd210057394b7d17ba8a68d3226ec9cd2ab0932b94edbddd8 =
1770713725 0.97 23 0x4fc2c1e7522a0ebcf8a222e0c595014fd87d8e31befb31561f56e45c680a5478 =
1770713725 0.97 10 0x5128cf61ab3139d3e5897c6249e0dbd1c516959cbf675a7e10d757e985cdb0a2 =
1770713725 0.97 30 0xf9f6fe52204319593711fd52b27d73533b9a7e0794946d7cb8db798f8c2d6b17 =
1770757167 0.968 6.46 0xf84536833ea05b83c83086272462f43275e0ee9adacdf6b7fdaaecd140c678fb =
1770827589 0.959 10 0x3a263c7f7a4c9531e8529e711b2ebe5d10efbc8352f2acf4d120e4549c10bfcc =
1770871293 0.9699999966 5.886566 0xda870bbfbcd8b490618b3adce3ed79c405513420fb222ecbabaa3c2cd3174198 =
1770871755 0.97 30 0xffa332ba3e58cf5e732f0a0108b1ce137072e235a1a1b5be253fa9afda7eb237 =
1770905533 0.9687144627 56.49 0x9b7828d4821b3e50a7d330cc7edfccaa75296753b2d653bec411ddd41d301362 =
1770935453 0.987 5 0x5e968960f06c57703a5b757fc4e1fc6959acab9e655e6c4d34028159538ae900 =
1770941197 0.987 30 0xebb1e9e1011b88557097a1f0238102bb7ee08cc30567bae74a7619e9e0042225 =
1770941207 0.9881578947 71.25 0xa4113e066f2af34d7f8903836a6bf793b82ef08df910b9a45a58ace67e178375 =
1770941221 0.9886491228 71.25 0x6075b490325bcce4b38887d8a363cab1cc3fcf1e4bc8ae54005e651c64c8a85e =
1770946273 0.988 5 0xb85dfaa0f9f51972b09728a0f40da43e7ad3e4908222215659d9a8a840a71d74 =
1770950449 0.989 5 0xbfce43d80e390f2913f177e6950d700966d19f88ecd8da9386724eff7916660c =
1770951709 0.9882857143 35 0x199604dd0f471c43b92449c0f9c4ef334267f49e955f2d7c4f8675c45f8add70 =
1771065747 0.989 20 0x5c26b79f1390ce636c5d149d3a534a0b76455f304cfcbb392dd7663e32004d80 =
1771076085 0.99 20 0x3dda2d39c36ec8bbcd911e6699308b5482473ad20d57a607de1508b35373cb53 =
1771085531 0.99 20 0x4c0e032cddccfd4f8ad4974607e1fea6b779eb6751754e22cee856a0843cf49c =
1771086149 0.99 5.78 0xc0bb8506275ebc8c937a9aa7fcb248771f8565673b34f91f8936c24d221b402f =
1771088985 0.989 5.56 0x4f8b2e00fb00521ecf555aa752c3753455f6df9a86947ec4b8de30247fd2e9b3 =
1771089711 0.989 20 0x919e1d6a669012a6aa2391c9af2aafa79284026d0dc6ca18ac7f48c462a41139 =
1771103741 0.986 20 0x7047d02298438b7ef52cd0476248abccc0ecbdede40da18c9a05af95dc4513a7 =
1771107439 0.984 1.9 0x5ed8df3f0ce4a797e413d0da68a8c9c24d3c98a4acc1032d1d07df651fe08630 =
1771107551 0.985 10 0x46cc58fb6b88e7c55c2928b5d42d79fb39b15a91d3f0bdfeed36298b4915bf9b =
1771107551 0.985 15 0x6d52037888ff5916278b815cd9a9ac005eecc8a88e7e4c4c2500fb5cc73f14fe =
1771107551 0.9843966667 30 0xeb4c5b88d101d838d83b6868a20074ddc1e8521bba2ad7e0832741c5eb117892 =
1771108621 0.979 56.53 0x8484521e4250d5fe983143421ce9b54b8f18719416431bc1ef5acb18f321e174 =
1771108685 0.978 5 0x5582cb0e7875cba45abd0d8178015be757ea56e5b4d8319bce9abb88c3da8de3 =
1771108685 0.978 29 0xf36cad0970a132556aac93c7b455e35c2cbc6adba96177180b982ff30684bfb7 =
1771108861 0.977 5 0x1a277c3aec648a59c0f76ea0c5f242b840d704341e7a1ce3205b0e2bcdb81ba1 =
1771108881 0.977 5 0x54f34255724d60655cbb632db298cf52969a59f885ba64169eec82cdd119893a =
1771108881 0.977 5 0x6376cfb93d27092d946247eee7c6c9e7228f6093206b5538a85d8a790e627f41 =
1771108903 0.977 5 0x5e95edbbede4f4c1de35731b0af3d4e0424da5b39015c2f8df486eb63cec6997 =
1771108905 0.977 38.09 0xc32dc537e54d9055b022a55c952f915e342abc36b011237f17007556edf948b3 =
1771108921 0.977 10 0xbe99232dc60ce32ce026c7cb7264df9fa2c6416794a7c64226983df6d68bc982 =
1771108923 0.977 89.22 0x99e2cc36251cb484ec869ce4dbcda2c0c975cd6679c80025991f57fe80fb0c31 =
1771108967 0.976 35 0xf981f14a82ea73bfa3984926b247b7a66d566fca4b8dcf644d15f9f196ed4bb3 =
1771108969 0.976 15 0x3eafab02c45591bd5d58610b5aa90234edbd526a895392e55f54d265a0748df5 =
1771109105 0.976 176 0xc052c91da2233c50ea37ef12f4b976a43563cba90146fc1ad2d94e15fa780541 =
1771110711 0.975 12.59 0xfb7601948dc732a10de70f383b8568192283f9f9969d54cb6f145ff8fe8ce63a =
1771113111 0.975 39 0x250bb293c99828bb969a503e788dc98ca8291458a3de7e3c2af9b5f7f431f605 =
1771113883 0.97075 20 0x7525f0079c5ba240766e5405dc2e624881581eacd970610d3b376114fb1c5110 =
1771113895 0.976 16.21 0x84ef2b3b34ca81a1c6579ee008af59daa618ac34c625786fa8a324848d893e97 =
1771117403 0.976 22 0x9ea9ae82377c8fadac2373e8aa0c5604f9fb93709537c4ba973ff468ab3c577d =
1771119799 0.976 55 0x9e6e747d6a41c972af99f5a353d309e9f275055d3363130d009220ae0760ba03 =
1771119807 0.975 45.73 0xcf5619e37f42f2fe8e12f00a2791e1f052d4dc1eb4e4512ed53883f8d47bcda5 =
1771119901 0.976 100 0x32ccff4d590b11a8b3495c7988063de296471310097ca041116b2478ef824b64 =
1771119901 0.976 20 0xaff76c81a365d3454df58ad6819f26f04ec52e3dff0b5e40ff6e70edfcee39db =
1771119903 0.976 50 0x9ac5c2b99c3320818fada19e9c63cd0d7dde81bab9d670fd48602bbfeac6c580 =
1771119903 0.976 5 0xc08ff259e9a822112ce8d3711b919a190a8e936e4f88ff5e6459f35a5f1acdfc =
1771119905 0.976 28 0x5aa3b16b3c3d94cf756f69495351f375345307ce32086738e560b35dd8642d2a =
1771119909 0.976 57 0x1e31eb515cb376ab4ed1aaef0423ba29b07e1f59759180fb676a68c134aac79f =
1771119925 0.976 5 0x292b2e6081f5694f7a22c614d438e25421f82a49c6617cfc83346b4e91ccaa26 =
1771120137 0.976 5 0x09e9081be34955594cfb85cc1a14e92caec0642d5fbbaa72566b47bcecb36259 =
1771120137 0.976 5 0xe056a638e2e0970fd03dd513b8e413e95d09e5b5d26ef7fc20f115ed9d0465dc =
1771120137 0.976 20 0xe1e6a8d454c313552d44dac743ff486d0365fb9e6a938595aae3327df73ada60 =
1771120151 0.976 5 0x1467b98b3ebf91e71e7093b4166d89d997e6bb802fc8d80e127d3eddd4039fe3 =
1771130469 0.975 10.94 0x0bb540cf8645adedc3ff81402f684bf5a0e364ed89b0e31d5bdef0a4493222ce =
1771130527 0.975 21.22 0xe37b4f3d9dddf999f88d59252b277b70983db2f26ad8409ae9d8605d37d811dc =
1771130545 0.975 16 0x8ec96800ae6d4cdbe510c25ae756db220391508d161da9c7d5c5ab36d90da6e0 =
1771130547 0.975 5.97 0x48e89e995237743b686f61310c9e3f4d93c3566f0198f4b81fe704eaba0cfb5d =
1771130547 0.975 17 0x887dc3f4a78c2d89eee2e1e2f9ad3a57ff945d7c2c2155fef9752a9cdc009860 =
1771130555 0.975 16 0x370dad4eccaa53873ea7ecca4a0c47025a77561470bd7d2d3b790f6ee16109b4 =
1771130559 0.975 16 0x684eb0a1d6384067249a12991b762be95df0171b62d530e80477a855edadba61 =
1771130563 0.975 17.79 0x8a04c2e269ddd6bab78e40bb1e93f5e3b0be17f3b6722e5612ec3cde897eea26 =
1771130581 0.975 8.19 0x2f95000a0f41b2860baeebdd2e7acf9053dd34e73eb71e111050b463ca3a3ec6 =
1771135849 0.9746040404 495 0x373307312bf870b89058c9b83ad5a15330a96c8dbc1a75353b6807f20f55f651 =
1771135849 0.974 30 0xb600e2d88eaa534e2640828caeaff9606b1b9d003a546415277221135f24bb8b =
1771135849 0.974 20 0xbab3c8ce09f3ee83f27c700ee5012e43126401bc2aa98ad657f7ddd46b886d8e =
1771135859 0.974 71.25 0xb9844bd8b25c461ae858d49187b71215fe94226a870dc244f78f9645d6d7e6f4 =
1771135863 0.974 5.43 0x1fcc2aa0d423b00a2f841b62ae6439d0b9fb51a8dcf9e592487698e076fab5d4 =
1771136045 0.974 20 0xa51100ead5caf86ec18768d37a98f510f3aac87bc8fb83082ae217c175869982 =
1771136045 0.974 131 0xe9f1400d19898dc0cba89461626702acc97dc8256e9d5fbb5c06aad18ea533f8 =
1771136053 0.974 71.25 0x6e7d2c8eb9a2853ede00fca884b23b2c28c6f8f4b539403f50cfa0fca8656dab =
1771136201 0.975 5 0xa6700db3545a2e12731e7c2f21802f44cddb7be8d8878dd70ee7314ab9eb8736 =
1771136201 0.975 5 0xcc92735ec60ae0714263b7233e2295fa92a8c047d19b084fb880c0e92ababa0a =
1771136741 0.974 5 0xb126c526a08df6c203d67d08014d998d4268d4b7b34b021e604de59faf45a7e6 =
1771136907 0.974 15 0x64b62f4a1c779ed2cb57dcb3559092048119c633617a259f52e863f7bfd0b813 =
1771137993 0.974 1.28 0x3376c2cbc97a345f8a417ef4b40d42260a394a532b42c85e6f0ed6dd2b75b7e5 =
1771137995 0.975 35 0x4cfd5171ecf1a2a8bb05de6274448a4e0b2b7ed445bfece0804de88c77978405 =
1771137995 0.975 263 0x5727d0b510b554fd04d66af905483a543484cd066d75f813c0bf99cfa896d2bf =
1771137997 0.974095057 263 0x12cf975b85fa8b3773f016d795600da63f84eeae9c44b70f51ed7b665d252c97 =
1771138005 0.974 6.36 0xc9b547582b2a7d2eeb4e52884edd538c6abe2087a66d59ebf581fefa0eaf9656 =
1771138387 0.975 10 0xc82ff9f459bdf600d1f239ae496d033f10fa591bd91ff048e75ea75160f83a41 =
1771138387 0.975 10 0xf315ca5446bb8bf07c530770e52263f34a228bc3c0e2198dff01cc282bfae1ce =
1771148399 0.9660038023 263 0x6b6c0e2ea1ca150c95eabfcd1ad8d352e214a0063281400e83a19e0fb6bd809a =
1771148817 0.9679689655 290 0x9520f1d71c211a092f8c633e773966003e3c76da607efa190d2d62bb028155fb =
1771148831 0.968 28 0xb67b40b1a033a26986d6b4a3cc50d08a06a10e052deb93a32e7b132a1bd06654 =
1771153219 0.969 20 0x1ac07b3bf2cc3b53cad75181aef7f300efb0acf46716f947c660e094146af60c =
1771153229 0.969 31 0xe32e2d951937535aa94c1789905f6a1c549780a4d75a054a773f16880ac28cca =
1771155109 0.969 10 0x1bfd76146dd8a47e43ad8dc3ddd9e8b5aeb2325e8aacb2107d34fb44bf74b93a =
1771155109 0.969 20.1 0xb23e1e859d3273be00ecd1f3d638465bb7e89bafdbc886c55f95af1263c29435 =
1771155109 0.969 10 0xfd409f06ecafbfc9ac9ac1dcb6111f83c38560fa9e88844c673de5e24b0d8e00 =
1771155863 0.968 76 0x2d750f99e32a740e20deda05b96373db5801ea9f55c99166daaab7eecbdf794c =
1771156425 0.968 208 0x68a187ab89864fb4fd9d58d088a4f020402f7badc58c4f11270df20a2c06876c =
1771157435 0.969 168.84 0x4dab405ac637c22f3bcde2464608dd5bd61d06f9d1bd9de2ef831fe39fc1d873 =
1771157837 0.97 12.5 0xf550eb869aa5bc7582561499d9e700d9a3a860e4bb1663b3f462e5242bf8e0a6 =
1771157883 0.97 8.567 0x219dd8d094ca9b971e9ca52327bcf117d7faf804752dc59d4c9c91677308568f =
1771160817 0.97 78.93 0x42d5221ae4fc571e2f9d502a4552205e25371e30e774e62249b8b3ef1ba5430c =
1771160823 0.974 15 0x336d49a6fd29f7289d841531564802950554a567df22cfdee917406422b5452c =
1771160825 0.974 57 0x831df23dd600dffc9181b7e01fb1b62d466c0d507995c88b2bb76080ed30b3ad =
1771161779 0.973 15 0x17b31f26a6ed28917e5769903c128d1f9bed44e913705a9f36b0f1baa46aba20 =
1771161937 0.974 12.49 0x5df64fb5cc1757dbc9eb9ecdadeb68d6a0683bb2d38d9cb8015389cc6555a4dd =
1771161937 0.974 15.51 0xa7847c296c495c5f484a2a076d1d366cf68d093467216a71d6967a3ff86e75ef =
1771161943 0.975 2 0xad4b05d2bc1941acbaa1bf387681ec54167a18c9147bab7a1bad3e888db641e8 =
1771165497 0.974 40 0xf300b81ff6ce81d8e90cac9d50dc463c5dfc3e0b092069b0bf7bf03e7d75a82c =
1771165761 0.974 20 0x3902a5be60873299cfc17b51447c9a035aa2b24bc036fd2f803a2bb981521724 =
1771165763 0.974 13.7 0xe8e72bf0098fd8af781ad955ee829f5581adb0faf199e6363b477396ac45b394 =
1771165777 0.974 26 0x39b5f208d11206cdab83c9e018515299098840c665f6347d71144aa5f8df7464 =
1771165777 0.974 20 0xe7f8828b629441b88aff291be34b2a5f54484aae3fcf2d8f0b052734dcf6348c =
1771165781 0.974 14 0xae16869e90f55ffa51aff8069c33700283b7e93d1a8e4090fd228285e7c5fc76 =
1771166201 0.974 20 0x18a7e5f302d3158cfe65cb4c9abfafed781b03525bf891119f841c08fba96e75 =
1771166483 0.974 7.5 0xb0517ac337ff55fa34491a5f8dcb63866f7df6e30920a646e023e2e88cd4b715 =
1771166865 0.974 7.18 0x795b35dbde301ca2e00af7ceac39bb2c3b92d43b04ea73bea27b0f615bc9e288 =
1771167003 0.975 15 0x87a5965c7d46810c41eee4d6b0877a4c0ef65e3825301d7cddb0566af35466a6 =
1771167003 0.9748538756 627 0x9d800854f613a6a744cb24dc339ec561214d1ec95c03917a67d9f2eccc7137bd =
1771167003 0.974 20 0xf82841ec2b0655d1b8229912ac96c6f932ed9be671b261f300160ad182e79510 =
1771167017 0.975 5 0x7415d2c958cd41fb55f58667ca2da7d9fe1a10fc0175d5cd58dc030697ebc477 =
1771167025 0.975 30 0x514954850848acce30afe38eb3fc94b9b3458fa0658c55b6ff1eefbe6428737a =
1771167025 0.975 40 0xeba528bb9afda9dc339c8c17462690d87552fd52ce630cc46f7764fcc0e14943 =
1771167331 0.975 403 0xf3875fc432a0ba4e673458d2adeab12e7fe0900d6f8e4e52737ec954834909aa =
1771167675 0.975 8.47 0x8965c46c4ef72fedf15c4ec7bae630aff5785fae4da8ccd1c45034b32537c71f =
1771167677 0.975 280 0x092d31ac5839f21c85e86ba85836e2ed00627f745ee2bcc2b667d587fdfeb44e =
1771167677 0.975 20 0x3488f460ac94afdf43b4e7e98186f42689b56502fc98fab8c903b57cec1147d2 =
1771169541 0.974 50.87 0x31d8a79e3023948d7720d86826cfac5f6c19a3f8cecc123c1bbf81e2bba9f899 =
1771170011 0.9745681776 54.49 0x2e68820268b11456285e27081287827a94812b95313bad879cd573a62abd5883 =
1771170343 0.9739999989 16.858307 0xaf44af28631c3597bd18064e28284dabf8836321ebff407a363f7de3e1473e39 =
1771170353 0.9742292761 30.02372 0x78c00a5a06add31c546ee4307942f47eaa112d10777632bbbd023c651d47a2fc =
1771170719 0.975 75 0xf0f74ce319681ce53fc70a149f28a3026a1e3fcdff065de927d553878ca3fef3 =
1771170721 0.975 5 0x895926a0224d12929e53e9e7ad44734a4f2c0f28f4aee8b25d57c3c5a8191bd5 =
1771170755 0.975 232 0x0f0ef1eae9a07d4c74191ab27afddb45384f64da7bf7fa9f98676476cca71c30 =
1771170813 0.975 32 0x19fa3f793a955c878bd4c229ab3154e2c59df8b85526e28547f0b34eefda6919 =
1771170835 0.975 5 0x65f2c5f3602d9e203ccf675a660521c800ab2cd9a8c51601992680f25981f26e =
1771170931 0.975 10 0x4f34fe30d9936b181b1c76515d69c32d859abf7a42ce37f2c376f81ab4d8aecb =
1771170993 0.975 10 0xd1c50f7c3951c3735884def7e40206290a061035dda2b847bce790264a0a6024 =
1771171053 0.975 5 0xc9354e82c3b2514ea890491e851eaab6cbf7b1696e74d5a1c84ab026ed61c49f =
1771171085 0.975 5.4 0x8cf45d3cc32049523fedc48d48e3c8246c65207d2dba1be6582cf6b8d17c0480 =
1771171095 0.975 40 0xd2ecaa1f6cdb3d12af4772cfda287e11b370e573361762822c85c0c6b915e0a4 =
1771171097 0.975 12.27 0x15c5c934613d6f56f9bab999e27a3ebb5f0bbf630dca86e5b461a3ef6f411db8 =
1771171129 0.975 7.6 0x5db7978b30e194fa7bcd24b00da4fd2f40b0db7215b874c6ce39c48ab9f9dd29 =
1771171235 0.976 2.29 0xc8bc70abf24ed5669395bf7cfab7560a0f83bfdcaeee48ed19a91b881d9b824c =
1771171249 0.976 41 0xab83cbf677122fe821bcd265358e548110e6bf72a64171f0186d98fa4bb04b31 =
1771171339 0.976 150 0x38b730c75ac9ab4acb5807d9364dd6b1417a4bdbbff726eb368eb814536be6f1 =
1771171339 0.976 30 0x3e6b4c090939d09f68e7933b3b98c2760fc7a9152fdd3a8cf67ae7524c7eeb3c =
1771171339 0.976 5 0x809d0dcd42f622851998636d49b6bdbe7d976b7644273e56a42c95b1f3752b33 =
1771171357 0.976 25 0x6889db17422929aab8c769043a0224e262d622b2d96e5630a54f60e6ac88da22 =
1771171369 0.976 7 0xfd0a7c3e1b0ca396be014671bff21f12b1aaa15ee1357a8751c830ed2760ffeb =
1771171533 0.973 38 0x347f8ebd1e009ab78dd4fd111cd2e7af5a74b1f580e044efe2b31f1d8307d728 =
1771171563 0.974 21 0x7c5464bd906c6e3b3ec22c1e6deb031ca717f4d38871d2776f14bb3e45f4ee8c =
1771171633 0.973 5 0x95b0b366209016749d00ee2b7096260181aeb82993b82decf3156034dcab0df1 =
1771171647 0.974 18 0x49d171766278b6a71c409f9ac250121d1f8ccd36c33d38505c08f03cb91d9201 =
1771171647 0.974 70 0x4fa2c2bcae2fac62381c13677abcdc32dd59783e28c7072c627e058fd524ccf3 =
1771171663 0.974 7 0x94687d9ac073d487c9853c7095cc59670c106a984951917d480a37ecc2ca5a2a =
1771171747 0.974 30 0x2cf11ccfdf142501f1534ebda834cfcf7b1d8156d7903425b1ab5cea2fbe4e16 =
1771171749 0.974 20 0xc9dad7f6a1be45d96efd5475d86d6e8159c7d45e5bc56b1a32e8e21caffe8446 =
1771171763 0.974 3 0x3a89918781e4a87c09583666bd46bc532c54965af81550eea42bd5f56214b5ea =
1771171859 0.974 25 0x57ca0304437a3a85229bc8a5e8eef37edc6460d4b648671d349e00eb72869790 =
1771171879 0.974 26 0x5ce211f12061f026a0c6de8d369e2a1784052a483ee4f1f2dc727a2320ae59a5 =
1771171927 0.974 15 0x2f503171810e5ec5df5617c354b3a9e817a1cdddeade0d85afd13f19f0c985c1 =
1771171927 0.974 15 0xc24567834c2d3d4ecbf5969fceb277dd6cc47fefb09a10d2ac5e9c8441df6b75 =
1771171979 0.973340445 15.010153 0x19b2bc8c73335c6260cc0d563c6d2f7011abe4a116c1253d4c7fd561290e5635 =
1771171979 0.974 30 0x6ff8ada082886084b7652348db481ee3860af1773b71073f0af7359e891c9add =
1771171979 0.9742045771 201 0x86057f4d23e2d31f8248889ec8d2ad7c7b6c30f1a5c3354b3c22fd9a84c328b4 =
1771172049 0.96725 12 0x6f91e9779115fa6da3cd7d184c554962a4c90c8b8d223fac3adf27e7b4eaa00f =
1771172113 0.976 13 0x7ad1d338cd7a1e7da7c51c01493456a9e0d7ea355bad1b6c9c72964b7bb72606 =
1771172221 0.975 5.84 0x5672731341530ffa96b60902955b23d1681321af1b63f2d04b83bc98743119f2 =
1771172227 0.975 10 0x98648083feb5decab88ca9cb75a2c2299570b17ed6b3f2b3e5eae1653ee0da10 =
1771172241 0.975 6.14 0x61ece226f4748e83d6b872ffb9a4afce5f795ac7804bbacef0cf5d1d4b339e3b =
1771172247 0.975 18 0x1e14c5e35e27b1f1feb3328cb684379b0c598311c3fe1b94f0f1e94f1d1219f5 =
1771172247 0.975 11 0x98270da98fdb6fff2aa0d3aaa310e3a8b98a580e961fce174d91b716a1a4daa2 =
1771172251 0.975 5 0x22f30a36268a76a733b03e895d36dc0cdba1bef7018bbcc4188c2288810c361c =
1771172253 0.975 4 0x8f2e42e25cf7f4c7d0740aedf150563c94b13f7869533b951f80458fceaf5b55 =
1771172253 0.9754714286 7 0xab3f754d2869215340fb3f249acf78ee6800fd39c781abe4f342181632300cec =
1771172259 0.976 7.2 0x8fec5556656ff85a0c954997fed2de70bb7a7604a63ce43f93c625d9e54ffde7 =
1771172259 0.976 30 0x9884c927c8211aa1daacc042dbb777960d1dd885d850f79b6d6d5c24b6b187c7 =
1771172291 0.976 38 0xebb746a8d0a7347bcc24369fba2f1d7e540dd3d6166cedfce8594db85e52040b =
1771172295 0.976 25 0x91810aecef8cfd58305ef7f7a4eae8263aba1a58397c33d7c9f93fdcd371e34f =
1771172385 0.976 12.04 0x35635ecdcbcc060eb060ae3d91c5ba9069dc7d88d59a1bd4fdda71548ae033e7 =
1771172479 0.976 38 0x632fb6e1e9cb5e7794fb646f386413de72b2eb4ca94799538ec5d570a35882ac =
1771172551 0.976 50 0xcc0b0fcc8a8a798eddcd3c0fec10846f303b977dc26da7b010aa3325e6bf6113 =
1771172635 0.976 5.99 0x61d6fdd890573c3ffed33de7218e711089c230a5f93750a1846c818c3e2aa991 =
1771172641 0.976 10 0x2545a717c7f4fa65062310bcbb94421d3feac2b66bbdbc14e4086ff42ec988b2 =
1771172699 0.976 103.05 0x0c53a13caad0db0a9374b04b045b4b0f738f2d129510b87024e43cb1a404df54 =
1771172853 0.976 25 0x6c065f0586ec00506b547b254a893345b75a6b02dd87aec52b99e5b541a91b48 =
1771173251 0.975 25 0x9fea59c063e0cfa4dc7326f3cd29fc33b8e35b050b9ed0e9956283b5677b0096 =
1771173253 0.975 10 0x59adb2b5bcff853647e221ea125fdf6a16dd65cf89375763088bb751a842d4e6 =
1771173255 0.975 9 0x156d061e3440b249d676bfddca9d10ae869b1f864e5eb6378522e94df1431d4b =
1771173359 0.974 30 0xbef1f7c24b6e52788f9f1ac822bc56be8a715ac366b1d1860196b636014e7a91 =
1771173359 0.9740196078 51 0xd30b1158b4e7faecc2cfe7e834af61170c39abcc87993a9ba1ed521cdd71d977 =
1771173359 0.974 10 0xf29aa33918bafca7d27efff287b76544c83cca4763e4564e53733f0a4a252206 =
1771173383 0.9873857143 7 0x592e327f38904e70e6571097e5aec05941dded53b2f2c017e25870b2328a20e5 =
1771173509 0.99 248.44 0xdef90c6590fb29c4f2e2c6c0a77bdd000986df5dca87e21a0f79e8cea6482f69 =
1771173545 0.999 248.44 0x4e80e381fc86be24d645c334494ec87925b78288015509576be16233f599a3e5 =
1771174339 0.999 103.05 0xf69b593b4aff890811ce64ec72e99153f8078e312429432b7def95e0070bc00d =
1771174551 0.999 7.6 0x88b4d40deec4844d933806761277ac409b8ebec2e1dfe09766cf128a179d9bfb =
1771174565 0.999 7.6 0x02177ac4bc5e9dc0ac3a191eb2be5879f1a8777fc2267d17bcab08a03096b725 =
1771174575 0.999 6.13 0x927c1a719831987e0ac25028a27886aed03c0c023f7591fa856919bb0574a58f =
1771175665 0.999 20.41 0xb76c692218cae557f8e2484ae545c3247bd55faa650b9cbc6f2675f8bf0430ff =
@1347956 Yes
1770482999 0.001 104.77 0x402f5bb3fe789a6fe709306de76352b964b2ee2c8d43d9ae6c31e5c30dd055db =
1770539111 0.001 0.25 0x57ed03c9a5e444401e3213905f4ac932ca543d6fde4442cd475be6c61627769d =
1770713555 0.001 0.47 0x113a6baeea328a90812978693878e57fd3f7400e9d2f6134c08cfe5734d21430 =
1770898647 0.002 2.41 0xb5fffeaba36cd5d3917a6daa9b697a99b6620d1ad3ed4b896e99d711eb15ba74 =
1770941031 0.0093184 100 0xf20ed2e699708139769a41ae216857c1e4eec2f423b805e79054b39be4749df5 =
1770948051 0.002 5 0xfd2431f60ef0f6ee45c0dc69e4bfb0ec13a1b0687f25145756c43b8d0ab79111 =
1771107825 0.001 4.08 0x6377c79e412698c1cf5b91ed7660901b5b87765d69072817fa2cf8148f9ef48a =
1771108607 0.004 134.31 0x7bb68258b31d5256ad28283c4a843b25acaaf83639356c423d222dca6093377f =
1771108779 0.005 167 0x96372ba16ce34a750908a5c613fa352f379c88e99f61eb56423df8692531a30e =
1771120165 0.0190127971 54.7 0x4377c8320a14d4fffe1af87988a5e8bf8329dc5ef202074848e26a29a850d4f5 =
1771123531 0.008 6 0x33e3d3a3173ec69b29e5e3c65ce891c9bb63e4b465a8338ce12ca87dd9b1c0af =
1771130577 0.018279354 56.894735 0xfbbdac749e0afc4e97c0ec1554880bad89dfdff7c9ab6b43c648b65aea9acab9 =
1771135067 0.018 82 0xb8ad324f031edac2577cb1b5791962613f16fcf21587cde9f34de404982392ec =
1771135723 0.018 26.4 0xce7ee94006c240f811796e5318f13108a5b30f46784b29ad2552b32335534c81 =
1771136523 0.006 117 0x15814ffe222ca280051c06ef35670cf0a6ce293abd71479991d78ef052f434c5 =
1771137995 0.0186759909 185.18 0x25f8edda377e8ea9397dd13736d3317ad87fbee6f24dc391bc29196007307dd7 =
1771137995 0.0167805379 185.18 0x6321d223259d9f5f540c54bebf7a303f2eece9951eea30fded193edf51e0aede =
1771137995 0.0189999833 57.894735 0x784aed02277d2d73d586c6ec2d0b7511d7fdcfc8cbf54526653900a4b640b864 =
1771138007 0.007 0.11 0xb0073e6c8bc3fdbddd3e64b3695ca7281b029751fd0a8f58b257c59e3c980ad5 =
1771138009 0.019 185.18 0x49adb02aea7afb33cf31784debf3b1114103ee87281bce464812feb2c37ba686 =
1771138009 0.008 18.09 0x967e09d4cf1bd60c91387dc830c61906854612f076ea3a3bbc0f24eb865a80e6 =
1771138017 0.009 0.11 0xd03938c370815b853c087d7c09111a457e91c6bcfcdc36f70ceb037310bde91c =
1771138019 0.009 0.51 0xebd5f407052976c924cbaefa800b86ffc89801219829f955480dd936a9d9aa6b =
1771138021 0.008 18.09 0x2e654eb0a2e7e483847e55ddf3cfc2a31cf1fd93338b3cc447a767bd210e0eee =
1771138021 0.019 185.18 0x9c053bd7edf283218ed00ac768c8d85d035fa17b3c130263f957818cf2673bc0 =
1771138021 0.007 0.28 0xabb488300da3026769da6d226dfebe05a921935ea1888a33a4376cf0cb8b2484 =
1771138037 0.007 0.89 0x26e19a326b3c9998624e3a6a87b2edb1593a92dc718640218a6c52aca3dad5ed =
1771170415 0.0079701121 376.40625 0x039b34bd98fe8a882ca289a81422e2dd1963aef018df1be0d7a6b24074420fae =
1771170415 0.006 15.7 0xfc99491a4eb91bbca4496ec37112fc278880671c645fcadafdb4ef17b3198d0d =
1771170417 0.006 740.72 0x0efca3062289a9f5729347707d7cc381d033fea815ae7c2e3aa274d652c66c61 =
1771171573 0.006 3.52 0xc8810aa172085dcb7a24542332a1e86cb7ec546615006e8c6064bae89acd19a5 =
1771172479 0.007 11.25 0xee1731361fb5d5e2aad06b36163495aa4bbb8419aa6d4372cfea0add305342ab =
1771172559 0.007 51 0xa290ffa5b56affec4d4b8a0c67f6a66c111985105bd8ccb8a029a22dd48aaf83 =
1771172561 0.006 11.2 0x08c2eeb6baf59469ead36e4123a98a92593462ef0e55b7a1b99ec6babe5365d1 =
1771173601 0.008 80.15 0x42f94c4f88e8ecc9e8bf7483d6b9435e3328195a5b1c91ae2aea54e5ce78f67e =
1771173601 0.0073808835 62.25 0x694ec4939b7eb98fd8ea5980ed461bfafbc5eaf2c240be1da1e3bc3505d87a6b =
1771173603 0.008 1.87 0x0faea93b25f2d0e162a406cbde4470edabb7ea12ecbe4eebbdc8766d4b7bada1 =
1771173677 0.01299 50 0x820c27679cfa12e722f0b53928cfc3dd0a81224736aa6414cb9a3b61e344b3c0 =
1771173703 0.005 720.57 0xbd6407ee4863c331c5fe4f37cdae78de854e56a3db9db0b39d9ce039ed3bfbd7 =
1771173713 0.001 1358.06 0xea12cae8cf1dbdf73c599765e98bde8580364292a606cd3ad72ce2a0a3849449 =
1771173755 0.001 196.38 0xbe723c54fc6646f2a5518b103fd621346fc0ab5b435267a0de5bf4f949913e93 =
1771178531 0.001 1000 0x675fa242d61445ee9e2812160d5780535202f0f0dc945e840b27f7f3c9bb8b67 =
@1347956 No
1770423659 0.98 7.35 0x0bcf4e915880a72b84b95b528eb4209f9b5b93d643f26fe0392f51c8d7180ddd =
1770426167 0.98 10 0xd4ea5595a6e766b5096ac602c6726c0da8a65cb4161c44061ba0fc9017754836 =
1770426179 0.98 18.0306 0xd75195348d5eb55e2d12ffb0f0264f4cef84527f1f23bda06e2c4161f7e18e08 =
1770458431 0.99 10 0x51dfd52b81b6427006749cb157b45a19689d69135bdce18a7a7781d59fffe887 =
1770462375 0.99 7.04 0x7388bce7a97299e79251526f12b9560007e85b2ca71be8cf60667e761f14df88 =
1770462393 0.99 5.23 0x80746780853786a25f261307080c7b0b8bcc76f7a776523eb1b8e08b82c08638 =
1770464351 0.99 28 0x9c955ae7c90aff81dcfb6b526f56e9c95a06fddb09e9f41436c2c8f7adfaa9b9 =
1770464365 0.99 28 0xe0503ce892950889353ded95c4fcf879283824201b3bb4d908341da46987347f =
1770466975 0.99 8.0909 0x4697fe38313e090b8a005ba90ae3b1b6bdff2f6917581a26bf151b976ee21cce =
1770473065 0.9968478947 57 0x8e2acd348e0d42e0aa10786fc112490ce128087d49ac732388076daa0f201323 =
1770475253 0.999 13.88 0xb99395be5f52975dad477a17207bafd0bf9de6653f25140ae7af0cc1a7811866 =
1770706299 0.999 10 0xf77508f7230f68ae2b6b9ea96e26e5d2123fc1ad07c46d6acf8879baffd5abb2 =
1770706301 0.999 20 0x949c0fd995bc5ea88c0ae40c3f404882ace0f028eb0b6e384ce8d4979da7b00f =
1770713319 0.999 17 0x18689af6b9ea73ec7f44fa3be6dc1e86522a12a81b45165b33ebd38d2a58c781 =
1770713725 0.999 23 0x477806c96ea26be7a7581dff57e353ff7903185e0d4de9109206f65cc7c3d5a7 =
1770713725 0.999 30 0x648acb598b45357ad251434b2d926189f4ddd667de68237daabe2fb329248425 =
1770713725 0.999 10 0x9432d7bee84e27469e5fe6021d21205e69f6b273820c3da479107322971114f9 =
1770757167 0.997 6.46 0x60eb8bb988cb0abf3afadd46c9bc1676a8d9f8125289d27beea021364cf17031 =
1770827589 0.997 10 0xcac5896d956f4c32afbe4256a58ba0bb289a09fbe2aac62c19e112e76dc2635e =
1770871293 0.9969999998 5.887333 0x8a44747f3ed8e5a67a9eb1a6c6dc33a09e921e287e599e62e70d7b43b8f7c678 =
1770871753 0.997 30 0xeb6021b5fd61e3af9e6033b2bb8bff0a2929c2bfdff529d68a3cb280fb8bb3b9 =
1770905533 0.998 56.49 0x31375e65ae3d2ff0a2fd5ed3fa22bc054a4295cfc32f39fe35c598c47701c75c =
1770935453 0.997 5 0xa453c88faa274e8c1b45236b0ed93baa01756416825ca27c325cd54338547e4d =
1770941197 0.9958333333 30 0x107781dffe6d9fe44e7851cc88567ff76db2692f889c3927d02136d8296f35f4 =
1770941205 0.996 71.25 0x9c3fbc4b2e823b4bdb88f025ae9c6dfb1638b16cc5184039da92daeee21a41d7 =
1770941221 0.996 71.25 0xc428808c11bc9cc7d8caf9b71493eff853185fd7936bbf8fd0c530a25af4769c =
1770946273 0.998 5 0x5f6d23c655b81345a3c345fca8382bca08c80eb1ba8dbbee245e43b99092702a =
1770950449 0.998 5 0x271385228b986b68b662351a577513257e573d16d10f0131696cf86ed1377499 =
1770951709 0.998 35 0xc11a3fd090ac3bca4e9ae72fe7b84a16193caba59015601fb7dd16b84784e425 =
1771062147 0.999 5.91 0xe90ad3e1e10ca59369f9ccd67310b091d025d0c8f84b43271ee0263c2b6111fa =
1771064729 0.999 17.61 0xedbad27154033735058f32b711cc7202ff8fa2fa7dba11221ffa197ff776b106 =
1771065747 0.999 20 0x990d3045aaaeda9ea6566adb385bbae0716019f4c77d8cc1716600b3a453d55b =
1771076085 0.999 20 0x5fd263a3b4ff56f2bf0807c84e54e90f95df4f2904c7b40c79789fbbb19a4168 =
1771085531 0.999 20 0xbf678c97dee1d59569d6667fc4b146fae35bc0e93cc806c3dc173f3b0a40ecc8 =
1771086149 0.999 5.78 0x240154b3b6c664aade72b54ee1dd8d3577fdcd3ad9ebeebe969b2e777753ff09 =
1771088985 0.999 5.56 0xad0421dd6eba67d577b091a52b138d4386733362bf11cd900b1098014c1d61cb =
1771089711 0.999 20 0x1b150c402d54408b47ac3339f456a76842b0c5daff6bc9db916cb9366720c9c6 =
1771103733 0.999 20 0x40cddfae3892ce50a5bbaf65b940bf861eb08662ea3166030f694ae7cf0ba914 =
1771107441 0.999 1.9 0xadbab92065478fd27aaa32fb4ac32bd3aed04295aea2d0d3b8947e0cd2272266 =
1771107551 0.999 10 0x4be28de525cfdbdbda477661b4aa40ebb702dcd4bb7bcb81dfc767864b834fdd =
1771107551 0.999 30 0x58e8b653348d0d98b3959dd6fdb61834b1407ef5f8e21573662735972e72bd67 =
1771107553 0.999 15 0x4d3cff16c6cd4eb01dd6354e1978db4b59c5d4046ff562c7ff57c7f44458358c =
1771108623 0.996 56.53 0x6e4dd062ed4db66ee8b07c54fae47b99c931bb8839043b30f4cff9c97b550f29 =
1771108685 0.996 29 0x024abadb125e1507f45dd3b6683929f646fac4c6175128c0ee6b0472d1bef02a =
1771108685 0.996 5 0xf79098e7b8c3a14bd4c9d3cf5fa2c612ceac065940946db862012d2c8c51adf9 =
1771108861 0.994 5 0x65d8cedb61147816f7e208ef521a75985815c180d1331f3fce219c35cbeddc79 =
1771108879 0.994 5 0x3cb0734d4c25d7a1d23c1315822a69087baecdc2b829b7166ea27d4e72485eaf =
1771108881 0.994 5 0xf3437c39359cd112ee0bee5d68c50c8123c2fc495b18489e53d4802f0cb2fb33 =
1771108901 0.994 5 0x13ddddc554645730591a6d363692a085d16f0c55a66249efb8f4b41c0147b7f9 =
1771108905 0.995 38.09 0xc6f5e7c437669820fa7aa1f132d1138b3e31afe6e995effe978cba0f25cdcb2b =
1771108921 0.995 10 0x10d886c8de0a6fb3db1647007a8cc338282e73eed596d6d8c1e55aee32f83f66 =
1771108923 0.995 89.22 0xf1d32997d24b0b61c7252660c8a1f69369df65a629788cb47860bae283c3ae29 =
1771108967 0.995 35 0x4df9fab9a771d4c82701329bb606d590e018fdd9abff9ed7fa6d15aa6535f53d =
1771108969 0.995 15 0x4ac6f1b3b3cbea5ee424a69f33e0b7acb239247ebe8215c59e90a0c1ad13246a =
1771109105 0.994 176 0x94bc1c619a53aa0f3b88edde29d681622fdca84e428a6a6596cadf25a4e1730f =
1771110711 0.993 12.59 0xd74c65c22a3ef5f6fc8f884bbe7c12a0989bc7582d3cb80a76b386c9c2fccca0 =
1771113111 0.993 39 0x2ed17f8c6e911f3eb07b853fef6da9039ed7082678fc936944132e490bdfaf91 =
1771113883 0.994 20 0x33dd3e6d1c11bc9fe9f2cab573ee1415b5dc52c177b5795d13b5340ff56af3b4 =
1771113895 0.994 16.21 0x8ded105047c8511992cee1a466de51f0fa318cab79d52d47674bb55b364a95a2 =
1771117403 0.993 22 0x00a7c032c478b17b7c4901fc8a79661368cdd32ac4880f72d521758a0f19c278 =
1771119801 0.993 55 0x21f8d65e037c16dfc5166d643f5646c093402d8665e3c44be2928b7b5271f70e =
1771119805 0.993 45.73 0xf6057662f1795dccd0891bf604c5386dedb1175ee146ca88eb247952d90bf48f =
1771119903 0.993 50 0x55d21aab324842e0623d6fb26d6b8de34971b150db7a6424e8d23a84ee3b503a =
1771119903 0.993 5 0x6f9162be4cd057e1d190d78721d965669866b1bbf52294a4bc2831e43795d46a =
1771119903 0.993 20 0x7bc49e10502d93df7b184b70d517b3b67d17f718ad8bde1841542b127eb827e6 =
1771119903 0.993 100 0x855c4863f366fc6a42a6b02a7fae3c59d5607e7be8e4ed27fa29908f3ec197b7 =
1771119905 0.993 28 0x3967637691ce06959faa413e804ebe70f65169417ab1f85db733bcd48482c1ee =
1771119909 0.993 57 0xdfd25e7d9b406c1cb10a0d0ead4edb8f3b533919fff119d13e84157389e8b980 =
1771119925 0.993 5 0xbb98f8fdee835ed59f0fecdb435de16f70017f1b12b5133128726c6cde36f38a =
1771120137 0.991 5 0x06aff5232ce8e07f99ebb6c17eb721129104742a6839565ad9d24f27616121c5 =
1771120137 0.991 20 0x2fa3c4d7b41f2f578b1cac90c6b5c1a675ce9bf16efbdb0d9c1f5aafd5b58b0a =
1771120137 0.991 5 0xacc9ea34ee0e05da9d9a5687478408178f79cfa3e06705a4debaa022a109f957 =
1771120151 0.993 5 0x415c00b740f4058cb7c04feec17e39718222f62250fe5f9d8d9e39e23e7f0d59 =
1771130469 0.991 10.94 0xf32235142623f8636247c70fbefcf11ecfec3bf1ae09cc1327229d2ef3d8ead1 =
1771130527 0.991 21.22 0xbc3c7a3f158359837f991a401c0fdfc5c125d1126bb6556d0d6b5c922b145d02 =
1771130545 0.991 16 0xbf24a40965c099251fa8d095af152d13ba759db5d96be59f217043262a71a8bf =
1771130547 0.991 5.97 0x23d867ee4ceaabe75a15e19756dd5c42c972d9a3d5b509921ee951e6cad7ce4d =
1771130547 0.991 17 0xde92c6161230b45819f46c09997e61cf8f2ef43a4c62f1768260e63c43b1a232 =
1771130555 0.991 16 0x36bc48638d643d6a189abd24e80daa1ea9b903a9eec456dc43bdd82b5540d182 =
1771130563 0.9923400787 17.79 0xe18145e1339fa3fa6cd98448d2a8fa22797ce1c1e64f7bdf9c1cf052fda87a17 =
1771130579 0.992 8.19 0xe501ac5f166c3bfc1b0b5913c293b6a5dd25bff76e683a233204e34a97a3c07d =
1771135849 0.982 30 0xd6d4f6a7c99ef8019061ce432b402cc693a6ce49c1e5a5cb41e045257cc77ecd =
1771135851 0.982 20 0x8473b5fdf0f3ec3589a0267a3587c10b26f2eec6c496798ce1151a40745975af =
1771135851 0.9877935354 495 0xe13e9def93c91fd5a768c3d1da59ff404251d2afed7b2caffff6a1f7f56e39e9 =
1771135857 0.994 71.25 0x6a842c56d23f6c325610092ecacbac116cb1ed5ed70aca8920ca77fe056552d0 =
1771135865 0.994 5.43 0x82776a488037abe51cfb3b131c029cf0b94b6b65ae6b4a90e5a7255af4a3f1a2 =
1771136045 0.993 20 0x47a01c31b89b164b92bfb66307be04fe9de9f8310052782bacfd9fbd5ab87e4c =
1771136045 0.993 131 0xc1689f59886a436c428da948a9974dcdd5fcddf22b638769b1326bf04ce9a46f =
1771136053 0.993 71.25 0x80cb844f0d020c39645ca0c7da16584cd38e9b4dfe65f4ca8e032c86e92eaa50 =
1771136201 0.993 5 0xdaf8da09109abad60444ced04d3964e17681490eedf949d55314f17f365a100f =
1771136203 0.993 5 0x85f4731b6afe2f4caef1f3a17df84bd9058619d17d308ae8f05ff842133b3f72 =
1771136741 0.992 5 0x716d09eb0b31d660cb246ae83523e7878767d5a4c95ce2d08ae9741a02b934e6 =
1771136907 0.993 15 0x3d2fa91662c6aec0ca33085cb71db9b18da436db16f6e5500cdfedef1715c79d =
1771137993 0.993 1.28 0x373449f305be63a2b7cd955e5108f7753b7016fcdb1b9427aed3b31742dfa9d8 =
1771137995 0.993 35 0xab0ff7e47632011a05a043e19ed414f5c937891a6a8aa458ac46f0dddde90ff1 =
1771138003 0.991 6.36 0x7fa55a175f372bf163465509f8ddbe4c7f83edabef320692c37194907ca52297 =
1771138387 0.991 10 0x01f0e1ce0f5ac63b318582e6c14c0b34fa33b53e8840271fdb1f8d20bb6bca62 =
1771138387 0.991 10 0xa4bd8ed04fb0c59b83133ad3ebbd21528dbdbd037a41734247bb8ccf7cc101bd =
1771148817 0.991 42.5 0xa46f9282432189d98516ce1f6e4755826b17f9e386927a96988455b7a7d3bfb6 =
1771153219 0.992 20 0xf441798cd6071163c0dbd2f67b9d81adeeb7a660423c6b6bbfa78408bf55b30c =
1771153227 0.992 31 0x3ecf596e850267557798c1552574a455f18d1ec4acef88c9a8f8ab7d255c3e3e =
1771155109 0.992 20.1 0x13ee126c98bb03a2805c3dc65d428c42caa189e68c2e63dcf967f0125351b58e =
1771155109 0.992 10 0x1b65d48b49929ba430d6d4a1ca8e5e8e665a47a9b6b9465685e01bc198c805e9 =
1771155109 0.992 10 0x6d63b258410156e67e47e4c87da9f0bdeb253b223263780da19bade51ffaac54 =
1771157435 0.993 227 0xc0d5d9e03fa5a308bc8f47213ec1a15b4c20e7a1fd969f15a648282db5d6f25d =
1771157837 0.993 12.5 0x0d8b893767e2cd678131409580d6e620626512729e4a385d0612a057bb838ca5 =
1771160817 0.994 15 0x9a1ec43a56cd52a87c10904d51eb6a3f16e51c1ba49f7b86558817dc8c91a17f =
1771160817 0.994 1057 0xda40ac3846e4d77aa86215747e407417f754b1b547383268434d05b8c27ab7cf =
1771160825 0.994 57 0x909daa0cf8962df1ccdc606621e0cc4aae89155dd5fe45e83c77cf85877a46c5 =
1771161779 0.994 15 0xd48e9833676d216025a139dd36302188cfb66071bcdc15850d74bb4f182544da =
1771161937 0.994 14.49 0x19184e76b9be46e7407b7b524e2e19a7343975a2cf40c76926bea71c1e8ca119 =
1771161937 0.994 15.51 0xa7c4b5e42ea0b00df486c3dcce8b1ae07102b75f73a8c9352bbd4d85b842d262 =
1771165497 0.994 40 0xaa4e206d557b7f889d49d60e2b3caddebb727015a67050ef84b6a4f3af4eab67 =
1771165763 0.994 20 0xa7d50264805d924603526721fac341a1da45522bcfa92a44cece596c5ff4e05d =
1771165763 0.994 13.7 0xbaccec6eb66e9eba37b5a4a3232e62d65d616e1bd141e69711305b9b02974c27 =
1771165777 0.994 20 0xab3cb06e114091a0a8f43c38e85d9e210a85428a7f72ce0b80887a8c1a0173fd =
1771165777 0.994 26 0xb4544a97168a6733610f0f3d25f4cf610c5c5cc26ff83be19952502d8e60d558 =
1771165781 0.994 14 0xc4a87fbad8b9b227831c0225cc52dff7aa8a2218ef78fc7c339703513b3bcc3b =
1771166201 0.994 20 0x3072a8838aeb7e21f1bef5eaa49a78ab03a587585a5a458b72d0cfd51c4a2a1c =
1771166483 0.994 7.5 0x90964dc6f68bf701033584c9a3e06de64a200db7d88fe9571ebd593a9100f22b =
1771166865 0.994 7.18 0xaab380b1ff31fe55b6b5f5954de46980a3aa6729a7726bf64a4873c38ac83c8f =
1771167003 0.994 15 0x447ad188f6f5b5ef4d1dbc365a639c13121b0cf98d93f8252c95adf8ad48dcd9 =
1771167003 0.994 20 0x80172ee1fd6c37b6b284cc6d5950c68fb5ea905a7c232e98ba4db894da0697b4 =
1771167003 0.994 839 0x9b5971c90d04a11736d6d1eae0e21b71f2ab6c952048d6d1f9f9ce5c4209781d =
1771167017 0.994 5 0xda8c7e8ba22d6587a404da0732b51209f61e4e72c3434ebc6d4dc7acabe7e840 =
1771167025 0.994 40 0x006b0477b5a5150b9a406b9bc2503cdeabd4569b23a1a30a1aa190f4fe8807a9 =
1771167025 0.994 30 0x25e57df3e42f2e282863f161f3d0e63b9c4b434f46edc5e1fc595a21a443bb84 =
1771167331 0.994 402 0xa0078c26300ea58bf973bbf6058f7139f1d0acf6c4e5d432a8978c510cdcf69b =
1771167675 0.994 8.47 0x15ab98b746db045057dc4f26f1088e48710204c637588b8a29ba0c874857a2e1 =
1771167677 0.994 20 0x56c407fe3901c4a788cf46c94fd4ee3d36ba2129323586eae0ee1dc3f78703d5 =
1771167677 0.994 280 0xf8d44233b45a2256f5df275054eb0ba4bc89b8e5302a15a8f244e4322b2ab93a =
1771169541 0.994 50.87 0xf03c2015eb0061c07341eac56579da244163a6defb15270f217e8e582afe5726 =
1771170011 0.994 54.49 0x9eea6eb3e37b877dbfff9a1d2f98091fb561b9466a85df8e5398de1fc94a7bd6 =
1771170343 0.994 16.851 0x5c12b825023ba38505d6e5b37e50c3a05b28f32533ebb5732cc1ccb827e40fa9 =
1771170353 0.994 30 0x60c979eff2b24d01667894e7272c9c836ca517d0034c48802880947ec9ca2eea =
1771170353 0.994 218 0xfe505300d6c1640c94722c55e4bcbbe9dbc6325ccc0c3dc50b04c0795a643c35 =
1771170719 0.994 75 0xc2d2ede749b57dde34adf5b406e4458572bfcca6defbf54d202e4c049282f26b =
1771170721 0.994 5 0xdd9c87373d48017e429a9c55ac5ffe37ff53b5b1ed300213e8716c8d19cb45a8 =
1771170755 0.994 14 0x2a70001372ddb8a98499520b1c99aac86ba865e4fd5befc9de1393cc4e133de4 =
1771170813 0.994 32 0x7d16d2e70741f24a3f43bd26e46c77b8799fca2c27ab302f4aac6bd363ed8881 =
1771170835 0.994 5 0x73801ea7dea7b3a56e994545f0adce00c17a77a7d5d416c1928be7a5527799fc =
1771170931 0.994 10 0x9d8e45c1018ed53ecb49844ef14298aab93d482d429fb32545b334e4efea6de5 =
1771170993 0.994 10 0xe67f0d4384078a3d3748c36199bbea0b6724141002d00775b66ccae55ecd8db3 =
1771171053 0.994 5 0x85a3cf5fc94ceb0d6f5b3ad644cd1b2d9d54e228be4d9ad722cdce74fee20e18 =
1771171085 0.994 5.4 0xe8f38964dcd5c2d42ea62393d4b4196056b828ca2ee0e8e28511130ead7b9637 =
1771171097 0.994 41 0x95e2f706178d10828eb45ea983f0080055ad00fb38d0bd74c934f8498f1f2738 =
1771171097 0.994 12.27 0xe3da02406ed10b7d1d5d22d2515eb1cefe961cf1d9e09f83e4f684f9ecc6c255 =
1771171129 0.994 7.6 0x6838c1010aa7db528ba8a9ea788a940d974f65a95abfb6a3a186a6f6e7616be2 =
1771171235 0.994 2.29 0x425a0d1c73047799b9affedfbf46ad1ee95ea34ba14c9d14e5a21f58c21c8963 =
1771171249 0.994 40 0x52becfdf90289513014c3182ed4ed5b4147881dc68a0c8e744010dc768aff5e4 =
1771171339 0.994 30 0x7f10119b494233c1c237a04f06ffcb9824763a6aca39b52b206139d70c426282 =
1771171339 0.994 5 0x8ea37c42c005e5f6c6e7791112138c2ffc078467e70282e824207d2467f8b17d =
1771171339 0.994 151 0xfcf08a43b198d9da864a8487d70b27eddb2f252d76e5bbd24406d64e2ec21a2f =
1771171357 0.994 25 0x8c23f514a943bfc21690316ad1958994058e694c74e7e7c43141591efeeceddd =
1771171369 0.994 7 0xf0a703f6753bd046039c1e9df8a2e3e4e24a168f58cef0270e0cc03e15cd1caa =
1771171533 0.994 37 0x4e154f35f3cee458211e298dda55dce472deecdab9ef880204aca98510fbd720 =
1771171563 0.994 21 0xc08b662df993eafd88d34a5aaeca85b61006a0668ed2a1ba8d78364ff2b201e1 =
1771171633 0.994 5 0x999a446e32f1cb623dd0491dd5377b05f60b5481890c2a668f4f898b3d493b70 =
1771171647 0.994 19 0x47629d2d61c4810eb168a0d8fe695c2bf22fc4b3283d5df5f65b9dfb5390cf71 =
1771171647 0.994 70 0x490dd6fb8c44ddcf829404fa9c869add6c87416b4e175bb8c6c62211939ff514 =
1771171663 0.994 7 0x9e9c65051a53d962818b6ad3cbfd4714ad8192d2d13b4d5dfba3aebb4db2850d =
1771171749 0.994 30 0x01930f6d1801762d2dded001317d10b0131b59e151d88f53b93885e569b66778 =
1771171749 0.994 20 0x4b2df1923ecc761c95eab4ec34665f51246f51e6f6d39aeee9e6bba3c81d8fb8 =
1771171763 0.994 3 0x38f68be14fb82ecf1ef2983ff38eb3bb90c1166db7ab378296cd86c76508c075 =
1771171859 0.994 25 0x5caf416eda7a6dab3f16f63c3871dcbb6acd0af777ef21536093025f485e337e =
1771171879 0.994 25 0x0ff02100a46298c44fe9a4fe278d2b27188ac20b114f8cb5db592dc6839d0ef2 =
1771171925 0.994 15 0x968c3a59027acbc57acd871f2d5ad991ee46432722257f4984bf913626d7b365 =
1771171927 0.994 15 0x8e74983bd66b029fc8c93e14b7a878c64ccaad931d8863b4a2eddbf24c18f295 =
1771171979 0.994 30 0x4ac5ad590f4c5db58909abf7a68df316fbc6957c08f333cbf7367f10e5e3f7ef =
1771171979 0.994 202 0x87ffa6ef0034503840250383d15db1583df58dc49f83631de55d913f12810c22 =
1771171979 0.994 15 0xbe386251c694aae1abd3966396dffa2fb51d84921ec5230e01efba8cc4de2a25 =
1771172049 0.994 13 0x36ebd366f808485bba9051bae6c693ec703dae0758a4d4dd5165fe58ce21d103 =
1771172113 0.994 13 0xbc4314b1157b257f222a637cc1239205b32c3fd0bd2d6d11ac5b6225f8e02a23 =
1771172221 0.994 5.84 0xe9640887beee782577dc7388cd3328324666e41a4c08a6233cadffe555fd432a =
1771172225 0.994 10 0xd3bc00f01793bd728202d3f8acbbe3c46c2c86c7a611136c039d15330d648f67 =
1771172239 0.994 6.14 0xbd3ad11aee8eeb61d490b9487bc7587bfccb76eb5852576679bfdfa4baee1b9c =
1771172247 0.994 18 0x77d6bfa36ae6ef2639cc908c5bb43c9d61b296d555b6b6e6fbdea4b37e0d6964 =
1771172247 0.994 11 0x88f230ec16bbde950c099c540b6b10e4bfc9a74007e9df6a76764f7923dc1ef8 =
1771172251 0.994 7 0xbcfd07f46fc8ac5988c85c1c8f56b64f731e100b08c449b6014b45374f4b86b0 =
1771172253 0.994 5 0x9c2b6cf76693078cc7a3be556046234bd3ed14f9bb4da80fbc86b75368bde7e2 =
1771172261 0.994 30 0x424bf2d4d867f39745ddff09cc6d6410b6ba4853cbaa0efeaea479ffdab60a7f =
1771172291 0.994 36 0x73bf7b9e8d5fecd34e66cee06ed0a7fb353e118ff5c260d7e691c040ec9981ce =
1771172295 0.994 26 0x4fdda11d5b8f3d1efca12a543c7afd0e144b69d2a255e04e6956fabc7401e8d3 =
1771172385 0.994 12.04 0x79f61ee472deb519114d20218e57a06b1f361de53ed2651f8c4c0c36b240cb10 =
1771172477 0.994 37 0x3109191889547bd737d92b772ee8267fc64134ab06d4726d81f865f3d5d7a23c =
1771172559 0.994 51 0x5564fc2815ac1c3e51c16cf40b794d8c8187e53cc70dfa5557c3304a7751bda7 =
1771172637 0.994 5.99 0xa3e28bcacb5ced598fbc288f600b0a7cad65a59d56e8772955a1de886dd143d3 =
1771172641 0.994 10 0x15992759aa9cafd3d7b4db5d66d7f6635ce52d9596be845f29ba3ad91e9114ca =
1771172853 0.994 26 0xaefdf6212d6a439c84037b91f9011156b2ba36773e1c6809a1bd3788fe0576ac =
1771173251 0.993 25 0xbce0205cfe7f721578266340d30214cc1cf8738616f5628e861040336f3faffb =
1771173253 0.993 10 0x19896eb2eba0fdf3590af0e5220ca379b4896614113d6e7a39d4068f7aba2623 =
1771173255 0.993 9 0xe532bdaaf2e7950ca7a9e757d289d1fa5cf158e34a4d90567010fd7c4b3275ea =
1771173359 0.993 30 0x1deafdcdf78a829e562f429aa143b878ff778d28a6715f141ce7ad7a90dab55e =
1771173359 0.993 10 0xb8d2d8def32f7f20c052363d5ec2216999c4c5799d838e1320413552131b4215 =
1771173359 0.9935882353 51 0xbb3a138da52730dac73c4f68698f19eecdd071cba18bf521040f7ae56259ac76 =
1771173385 0.994 7 0xfddda6c7170d005701fa90b759b4d76606e061917f3d4a4690e15346e6cfeccf =
1771173693 0.9939862177 725.57 0xbdf098626d71b833096a17e49d578eb3025aa07fe6c5388bb5844277f9e38c17 =
1771173703 0.9947142428 2660.16 0x1c73df9a396bcf9ab807784615137e5661851c887d18ad4a0f86d6d175b601dc =
1771173703 0.999 100.1 0xca658f058cd0252fb698beecbccf952792282d857d92daabed2e504fbd84ab83 =
1771173717 0.999 725.57 0xb1fa37c87d4d852706d5dc48a557b9f794a6e636b0162ada61723108f96b45c6 =
1771174551 0.999 7.6 0xcc04c7117421aa768808a778a6791c38492e760286ecbfb449bed7b08aeebaa0 =
1771174567 0.999 28 0x9f3639e0807008420d211e5e9fcf6a8d33c6565087f9373649bc957af5c69a72 =
1771174573 0.999 6.13 0xf248b1218acc11e4cf8f6fca15ddb516c28b30a7c53fd42ffed2e3ba21342510 =
@1347957 Yes
1770483027 0.01 6.12 0x8ee81624c8479c88c977a3f0fbac065029d9df037e79dfcf1ca12091e7f8d3f5 =
1770483029 0.01 49 0xc4c5c42e7a899bd537fdafa96daf71e2e3bb97bffaa4d24075cf6c6a67e7b150 =
1770487361 0.01 19.58 0x2fd62db04c83f7a8047fbbb8aaf11d063ae03bb0534124f78b08ce38a4840b49 =
1770488687 0.001 37.42 0x417629272a388acf04aaf41a5275d4c31819e01117be72d6307b0348f48ff04f =
1770576767 0.001 0.25 0x9fb5233754445c1e982383a507a0e61465b68f9c72aeadec990a9910c03742ea =
1770713421 0.001 5 0xb9c92a6cf7a9ac0c585630e7a57ba8ea10f12a42517e1034c2d8874e86b224fa =
1770749259 0.002 22.72 0xd3e721dd5095d89810e3b5d21c3c2a81d3b9452a6af31f4638aabb1a64d1bb91 =
1770850301 0.005 37 0x12e3cce71d52c92f8797ff8afb2c5bb6332f66cc7eacb28f67ab7d2a1b0dfcc6 =
1770898647 0.01 2.41 0x7791e1f5d43c786ee8f41d5de1e344498686d38b5837b991a15d01e3fb1661a2 =
1770948041 0.001 5 0xce4139914f04ecec14e7bea86f908207cb048f7cd9e6e4651c576027c99f80a8 =
1771107825 0.001 4.08 0x5e7c6c95de471688bfb4b8145eb3260e3d24a15735914418c356508515ed487c =
1771108931 0.001 38.09 0x6f4bdb574c038faabce10c3eb89117ccafc845a4f1cac020ad9c10df9e0568ec =
1771108949 0.001 89.22 0x47ffbf439cb4ce5eb17c527f6bc0671326ed4427c3a1e66ee7e18d866b87b8ec =
1771109153 0.001 15 0x246137563555f16a9ed188e81746c300f92e104b25427162033358e571917d4b =
1771123527 0.001 6 0x98776c319df247981ffe978940374b85c9121d98cb548d397ffd4686360d28cf =
1771130487 0.0091468777 113.7 0x1473b5f2527419b3f6dc66a6ab9545a4ba3bb0a13dc1315663c7e1a0021c2c13 =
1771130539 0.0118871661 87.489229 0xe9381d9d1182735a38249af753c54fb3287879783b867913e83b96ccf03cec0d =
1771130559 0.001 0.2 0xf34406296812d16194952a463b3bd6548f924656fd14d4d31c23d1922fbb3c82 =
1771130573 0.0128030303 81.230769 0x1cc1e29fb1003cbfff4d77a00cdf5d72a378f47ae9c52a3f9c60a132a13ddbc9 =
1771135867 0.009 115.555555 0x742b3c9d7d185e7a816fa65bca139498e5c70daa40392c847b61c4e652f93567 =
1771135885 0.002 0.79 0x6654515efb9b5178a16f4660fe335d9eee06dcf7c8f61786cda0234305da80eb =
1771138005 0.0097312781 238.09 0x7650c720502c63a4eb4560e21e005914417ca652dafd0e81c0f181b834f269a0 =
1771138027 0.01 238.09 0x0e785abac9e0f9cdf231d46a9ec34f85c0b597d03af9c152a3c3ec868263b268 =
1771138027 0.001 396.98 0x1fb2b64f7bd8a4597b8ffbe155932541abb0d65b32a3c3d731d1bc10b40afa3b =
1771178533 0.001 1000 0x298f849431d9844df78701b39de6c6fa6c0458f85aa3d0a0e95afae2358b9505 =
@1347957 No
1770415037 0.98 59.99 0x57e92ccfc500cce78c7bb8f37f562d2f66f72aec8467abe5060b508c413827fc =
1770426165 0.98 10 0x5887c724ea92e3fe643c0cac721f614e1f143fee498e8da36d278c09072dfa27 =
1770426179 0.98 18.0306 0xe2f7059921122e7f5f3419a06bd88f15d008d8aa89f94e8c5a6b07ed93ffa107 =
1770458431 0.98 10 0xa0856e3dd6d37c2a7cf51374a6168b2555dc38f75ff5dc013a57a8d6a9142492 =
1770462377 0.98 7.04 0xaabbde4e9dcfd5f55e3589648958b5f2eac2e94d449d29c8548b12b1d7071f4d =
1770462393 0.98 5.23 0xae216912c75f016ff86cc62d3732a7f2680275e36763817ee9bc5e4e53dbb808 =
1770464351 0.9865428571 28 0x6432f8336bce0571e24b2f6e95f6e6eba37b03649f8d1fade41ba89665b69bfb =
1770464365 0.99 28 0x98fb7f429e917fa70a72a3aa3546bfa5473c847a9f8eb91545c3c617b4d1c52b =
1770466975 0.99 8.0909 0x72117dd6b6ccc17d388c7ddd98ca603811e0fa358b14e29cff5d8cdfbb1aa048 =
1770473065 0.99 57 0xeb1e44669d7180952861a316748d9666a4fb30fd93b00a844993198c2be44b11 =
1770475253 0.99 13.88 0x8b8a80b5eb83006d11aa50a82074080f1e906cbff07b1c55dc459132ec72a50b =
1770706297 0.999 10 0xb356cb9a62781858404db1fb6075bbde9a75844398522b08129fe38e2195a89c =
1770706301 0.999 9.75 0xd1c681e8400cb9a2092c3942a9a588973d147ee683f1f94e78521bbaf1af653f =
1770757167 0.999 6.46 0x2c41fd63d371a63743f4aa9b3c5ccffdc9bafb5bfd6026ea864ff6a849441401 =
1770827589 0.999 10 0x2f98cc8d0a78e2f661615ed4d537b60903442848e712d222cb35c2ffd1d1bc3e =
1770871293 0.99 5.8888 0x4d53d5a9fc7f9afbc3d76dccc8a6810d3c84a6400c28f26527c89f58b85c528f =
1770871753 0.99 30 0x2a7638681eedf85360f8941ad771ab16af6722b5e82e33ed2f70d1b3ac5b23f7 =
1770905533 0.9950647902 56.49 0x30a0cb932a4947a6474794092105063a0f0e9a31ee84997c2fd1a16ff9dcc365 =
1770935453 0.999 5 0x9ab9d1afb486c230d96e94d6bf765067ee3a8d08ef306cd410bb33ed9feb6684 =
1770941197 0.999 30 0xaadf48ae9236834988a5210c64d248c30a6f496745944ff9ab2947a5eac81392 =
1770941207 0.999 71.25 0xe1f73d7289865c3775671a44ea337fa96740d2f2859a8e93d12576d22fd0bbc1 =
1770941221 0.999 71.25 0xe26f75211c6c45c9d67e53c55b5faa651a6834dda897d2d9a9ac7d6ad993aabc =
1770946273 0.999 5 0x5ba48796fb0ce0e610fe9f1e82d88ecc0e1041ffcc282d9ebd96711e0ca2bd0a =
1770950449 0.999 5 0xe2fd9fb1ab2c89ee824522c5766e1facf91da47e02dfc4f0c0d430b33e5def11 =
1770951707 0.999 35 0x165c8d593aaf3b238ac837032327ca548e099babc61ff01605b24473296aeba4 =
1771062147 0.997 5.91 0x58f2ac072bb8ec7036d76b346391fe1b0bc309ee3149f911ad970f2534a5c3d5 =
1771064729 0.997 17.61 0xcec5d816917f8c833f3bd5a7565dfabefa8315af2363727e5d60270e5c407dea =
1771065747 0.997 20 0x377766e156d0039567020f79535ee7eedd7ebb5727b9365882f26bb92a3c257d =
1771076085 0.997 20 0x4255aa3647fe2b050d0e7a06e9d8af6a9342f3af964019075d4a74650305c2b2 =
1771085531 0.997 20 0x291e84acd89fcf35abb6d987e468a188bc8dc826fd159be1ea18e0d8a59e157e =
1771086149 0.997 5.78 0x52adbd1529c18e7da1eeb67ae2ea5f02db5c3541e18b8776aa128f47deb3e58d =
1771088985 0.997 5.56 0x582bfdf16a79ffe782f24945913c3eda901a5be0e50dea339fb2657bb5d6ad47 =
1771089711 0.998786 20 0x6eeee78792d0ab548832084ed4ed98c9a64b2454bacb0b2961a6ef6cfa11f14d =
1771103745 0.999 20 0x67f73184a2752a3b26c7604ff9817caf96559ffd265fa4f49aacabb1916d0eb0 =
1771107441 0.999 1.9 0x83a0c0acea3c1e680e85ccf20656333c06d737b0a5356af5a9149006600d834e =
1771107551 0.999 30 0x189dc8bda1a17834feb25ce5083b9f4f0537bb54c010aab8611b5af5c0299ef8 =
1771107551 0.999 10 0x21cbfd2b7e133e95f820b14e9215032d6388633f26beec40918e542652108466 =
1771107553 0.999 15 0x6a3ab37826837e1cb2c9ec717bc598fb2c95aef07dfa28145d6205fef00d037b =
1771108623 0.999 56.53 0x881c948e91b43a123f5ad4e8d90dce5d552893fdfbdac8baa96103fc384a9849 =
1771108685 0.999 5 0x31e464f6f3373d5826144afd244405a978135ba2c7489ab7b10a0b603914e6a3 =
1771108685 0.999 29 0x413ca8616aed45da53a50228e33363653d0d45ec50aaa8d9ad22689bd882e711 =
1771108861 0.999 5 0x414f1e16c453615e55afcb1f816808cc8f1dd1cbbb9ede0c76984a6a1bf1b8b0 =
1771108881 0.999 5 0xa9a064d510cb117e685104e0d68e7387fc89022c97f9daeecb3c7be10d0c75d3 =
1771108903 0.999 5 0xe8c3d3c4b7c2429f05af1643db6199ed93cf28d7d9b7f613c9f46a9235c77fd4 =
1771108967 0.999 35 0x1bf97297b463a7b73c76d44cb75780fa76dd6f407a7c6db48f95764806dc6b5c =
1771108971 0.999 15 0x06499867172de16dd177e1676b5b7089e895b00ec55fd2bbbc0d8e68478620f3 =
1771109105 0.999 176 0x0b4d4f0146ec7e57ad419680bc151398cea7ea18174db0de6e62af80775dd7e0 =
1771110711 0.999 12.59 0xe1e7845639da9bf7d5c7d3d6178fff670b2327bbf34a3f58d881d2630b7d9d59 =
1771113111 0.999 39 0x1def0bac7f58d443f148241b6e207f234b68141e08f4600acffd7972888123b2 =
1771113883 0.999 20 0xd252a1f60e09382289958b9ecbd1bdef740b06e0b150ff680f16a949666343f9 =
1771113897 0.999 16.21 0xe0fce90755c405304734d894a135edd66c38dcddc2ff38c6e4aabe2bb9570eb3 =
1771117403 0.999 22 0x0a8f9921fd8b802b2d5f4874efd8acf4dd8676edfca240b3f6735f53c4b43433 =
1771119801 0.999 55 0xf576058aa055eab7357de4bdd4dab777c6f81ed5c1d6f5adadcbb0ceb57d784f =
1771119807 0.999 45.73 0x70f2a6d8108c3cdc39784f51896fd518b704ac54d93c4ac1288d972c22ccfaf4 =
1771119901 0.999 20 0x1bb8a82048db1d61f12d53b07ee2b053b081e580012e8c4ef427c2f55e872a8f =
1771119901 0.999 5 0xe7b56e4ae65c06af212812953a9c6f7c4b6b22b6a78a4aaa08cd33a521033c33 =
1771119903 0.999 100 0x524c30b3d3c57305737f4b47e0ace37d08be6a3f6143870202e8ba88314b9c03 =
1771119903 0.999 50 0x76382b0528581ed7914ea6c37c39827823126cc1164e5e4dce9c527397892e64 =
1771119909 0.999 57 0x973d69a556237d24b63b906347cb138a119d31efce81750c6a27ae8cf398b3c9 =
1771119925 0.999 5 0xf427a9c7b5c6584dc2486910f1ff0b6b76db951e720fd534be3065014c30f1b4 =
1771120137 0.999 20 0x0f9e9d48549497a183486934b6d439dbb785cde989042c4102c376b6b1471fa7 =
1771120137 0.999 5 0x6dc1b022689bfbc46bd95b9999341ad66037bdc86bdaa8ebed4fa4b3119f3d89 =
1771120137 0.999 5 0xf74499b9e32f6f2938f66d526124671bd03b94111be23853be4ef2e7b57c7b8a =
1771120151 0.999 5 0xd4534d3406182fd07a856bf8d8d295bcea2007f80107f1d87e4a948873506b63 =
1771130469 0.999 10.94 0x51f9aa23c35b9375fc7525ad00b0e54b1737fa76e91bf2bd8d0af800c6fa16b9 =
1771130527 0.999 21.22 0x3b00e5bbb890011bf7d38a599faea03ee04704c913ac8f323beb8c61682eb569 =
1771130545 0.998 16 0xa060334717108bd9bcd7c996a08d21c4c6a3c27739eefd86ab6d393e71934446 =
1771130547 0.998 17 0x0f752777a3e016d9ae287853c1c2b5eb49877342789655d86c8c013cc52c1d19 =
1771130547 0.999 5.97 0xa52155600f46d084aabcc78c4105ab55a61474d8d1a329f41dc3b767da650830 =
1771130555 0.998 16 0xc4417f54a47fafcb848f6c655fa22f1e5e4bda051fb21652c774068e058ffb36 =
1771130565 0.998 17.79 0xdf1b14790ec075db07c6f70b7b7604be0d16f25fdbb24228304709a03a5b2bd6 =
1771130579 0.998 8.19 0xbefe0d0a85c94777ae91f3f1096af03f9adc69bc23585ba41a33326ed556290e =
1771135849 0.999 495 0xd772a83bb5aaa8db8f9461534d611d723c9d837024a0ab03db7b3c822d04619b =
1771135851 0.999 20 0x046c21aa508907754c66a165e07628aa549dfce4bde47d12051b9655b3f8dffa =
1771135851 0.999 30 0x236e28f5d6a3743de3ae64d172cfe3daf0a5329520e34edb8ebc29814dc1b6d6 =
1771135857 0.999 71.25 0x1b8c3541fdd97c78aed33e3866ddde9307407c9ebde1c84a7f1b4f165e712938 =
1771135865 0.999 5.43 0xae033de08df8e1dab1bae7f091d8259e3f3fe26a3c1e54da59647af27dab8347 =
1771136045 0.998 20 0x0417680d6e1925487385eca146f10cd8f1d9d6a871c380763317b3f5c437249c =
1771136045 0.9987770229 131 0x140371fce4f0fe5a87c31141fa5c9ddb5c1df125e246e381839b4e93e3634d69 =
1771136053 0.999 71.25 0x335c9bc2fae067140843854a18625963ebb99bf3f088187ad7623f1006ef6da6 =
1771136201 0.997 5 0x57e4421b2466099af064f82bc169781c03b58e0dfc186a2b8404d8a78b28dfd1 =
1771136201 0.997 2 0xc97ddb1909ca0c6a41fcbda7cfbc5ec7e90a6993abb4421f98b8654f4eb3a7b6 =
1771136741 0.997 5 0x8f6e5fcc57de66ffc45293156d9acef021c57241c24ce6574a53cf273bcae0a8 =
1771136907 0.997 15 0xb46f8439dfd9cf18a2b898389a625ec9225f65936ce186e176db8e3bba75f2bb =
1771137995 0.997 1.28 0x666e8bc1285fff63d9e6ac6dff4a94708f7f0b7b8fc78511e108579f84cd9198 =
1771137995 0.997 158.72 0x70aa7f656af8e432f08aaa9cc9ecf78ada5064044d58c396d0a267d5251c6364 =
1771137995 0.997 35 0xe7d419d01826c92150dc913e89a2889c0fbeca7eed84e3c27095c2e568aa54d8 =
1771138003 0.999 6.36 0x06013ea37fd47cc9d11d716c9a7e7712659a69e5d919f64738a37225d292b447 =
1771138179 0.997 40 0x187df3e5b609983efe542ca849cfa1ebc756fb6f09a848a7b703a7d18964b3b3 =
1771138387 0.999 10 0x9cde41b443d5c23a9af8928965c41c90f970235ff5aec515fc21668099a87d78 =
1771138387 0.999 10 0xf99a5382dce60759eecc0ff2cfea25f46d48d68d2ee64ed77211e7a29bacff62 =
1771148819 0.999 85 0x4927fe6b17604b1a8e9f487ee46548ccb17fbd7d7fee6d832def6b05e0a2b1a1 =
@1347958 Yes
1770483007 0.001 6.12 0xf7c5241816b19d4aaaf98a4b590a129d2ecec04a96efe2a87f53f8f1e9524bf8 =
1770483011 0.001 57 0x8d0d80592d3a03cdfb994a334b4e9faaf39cacd4986b86418871962dfe174c6f =
1770483011 0.001 49 0x9eaf15e94f94e6feda78b7ae8f4edf4a7b8ce2dcc8650e526f37060a2861751c =
1770539111 0.001 0.25 0xb28086432895b59b4e7cb96fd6e8be50594030acb80847c7cef4857acfd6bc17 =
1770713555 0.001 0.47 0x20f9442678247ff9d5b30d75cb89a505321ca0bddb4f8fdf710074241dd324b2 =
1770809571 0.01807524 276.6215 0xb7d58f9405881ba9ad0d45a043b4b8a6ba02b73e50295818c7fc79ca55cfa75e =
1770898647 0.01 2.41 0xd9c17c28a8c2a18d679bf27b5ff38301815f11115a22ef04a98cfb209569275e =
1770947949 0.004 2 0x6ea06bcfb5b0e42a5daf147364200e9337412088fe18df8b1c221af2fd149574 =
1771107825 0.001 4.08 0xdbb02e1dae011e811f3264755b14a3dbba3846e031c4a05fb51411a1cc1c8a64 =
1771108929 0.001 38.09 0x79e3a2c06c57f3dfe43bced4a05fbc522e728bde94f5fb103479b3a2f6d8920b =
1771108947 0.001 89.22 0x62954f7949bbda6ee12057f752122ec4dfe9b6ad95728847fff7dfb9dd36f911 =
1771109079 0.001 15 0xcb7d92cc535e53f9aa8455ce2e7f517f043ef21ca4d3521218121de92e9ba964 =
1771123521 0.001 6 0x501bab195e5e27d9a0adf7a22301e2b9e86dc1a1ac3158fedace25d464880395 =
1771130575 0.0063569682 163.6 0x2a6c85f7f8fe4e5e099ecd3c5a7d596304488347b63799501d5fc0021a728f30 =
1771138005 0.0088319963 238.09 0xecf581a42d98317547839c0ff0d402aff9087f004d1d43e3a3f1916d825d0f73 =
1771138025 0.001 0.49 0x8fa3fa9ae398cca093e11e2808291c4342576e98d86c0448adf6c26093b0ba08 =
1771138027 0.01 238.09 0x815933cf4071949900714ffd08543903d8bea8e9f153212a68b136ca53c90aa8 =
1771178533 0.001 1000 0xea7dd44ee997ac5272d50b4e5d06aadcd08d14c58b25d7d5ce144de7cb86f4e3 =
@1347958 No
1770415127 0.98 59.99 0x7395909a19576b0c3caef9d792d2c8bac03b3dd22c28a94c7b18d80aa29d5723 =
1770426179 0.99 10 0x4ab3f7b337ed4763361b6f0506aafb1b715329c11881fee630b6b1016cdb1c00 =
1770426181 0.99 18.0303 0xfb18c4c48c10d00b35a6fa2ee95f15f377c80d7a816fca7ecac86d7da5e79dde =
1770458431 0.99 10 0x7fd0b7cc5bd8092ddeda7d65ffaa8207d18f08f5f2c8eb7fee207fd1a1a17dc7 =
1770462375 0.99 7.04 0x15d21e77e695572943b1a2cddac18e9b24024b15a51a57c6a2e86bd70bd5329c =
1770462393 0.99 5.23 0x0a9b4778af5fe252b1cc9fe1e69b68fb2e280bebce723385a00227f1017e7bea =
1770464351 0.99 28 0x4dea725cc0c1f94bdb5593dc40abb7da596229697d46e404deb1841a7fb7c569 =
1770464365 0.9920282143 28 0xb23c4682ab0a7791669f88b173753c52eefa45f83a27a5e7cd32e81c9d7a43cd =
1770466975 0.999 8.09 0x696c877e77c572327c63e6edef4496f96a569770f4da99126f1891cb3804c9e7 =
1770473065 0.999 57 0x02b69d2c1a56f04db965836b57afa80fb1e0a75efde8cac5cc6bcebab3c0146f =
1770475253 0.999 13.88 0xb5600a4960e16c9e0f64377438022135bf5a58e50a62c8b29c80b3f1e03bd5ba =
1770706297 0.999 10 0x0f7f70db13ca8557a5617220c441d68bd6550f696641c945cff4c048664c1feb =
1770706301 0.999 20 0x932a7b6a88ebbf1e3021f1dda8ef9418713afa2a4e17db33be0ca0b81ae6baf5 =
1770713319 0.999 17 0xb16cf4391672a4e331185ddaa8dda1a9ccfd9ad775c1eae3fc46b96eebffcb7a =
1770713725 0.999 23 0x6dbd857f4f149ffed130bbf308769bc6306e5569fe3543ab2d0330a8406b8b22 =
1770713725 0.999 30 0x9247ce2395016663e483e0b270e7157012d5202c75fa91c8746ae88e58081dde =
1770713725 0.999 10 0xaef86f1c2045ad09e992cc5f94ac464679d6d3316eaa28bf6581253277ad4f32 =
1770757167 0.999 6.46 0xcae7ddde20dbe11faa660f167b70e43967218f4b2bd29c84b914974bc0664165 =
1770827589 0.999 10 0x6812b3efb8ff7b7f5ec9532a6167b6b3c8b713b2faba2d12fcd4f75540a6f305 =
1770871293 0.99 5.8888 0xea24c70c4601bb55d79d2116f8af2b88f02568060d1bdec881be77c74ac4f639 =
1770871753 0.99 30 0xea725ed67e20ff42ec4320731a410bd49e09f775e2e90d69a640b472bd4bbe39 =
1770905533 0.99 56.49 0x59b5df96e7312779335db2ed7c0a26f170c9c17500a854d28d3e93725d305d62 =
1770935453 0.99 5 0xc8eb3bcb28e24c4206225714a7bf3b5bfb9317c871e94d019f5e3b6f3ce1dd05 =
1770941197 0.994437 30 0xa4f3d6a11693d5ab3e4d7b9e1cc70775e620edca1e10ab39fe99135443710169 =
1770941205 0.999 71.25 0xe4660b4c09d6d18f4b5e48cb3f7efa810c9f75180d9b76f8dd3924fe1f1ff43d =
1770941221 0.999 71.25 0xdfff8a531f50af29b806a1a95939a66335e207664a646b546b7ba582690758dd =
1770946273 0.996 5 0x1b34b6bc8ac139600dc5a785f8c9811dbde061d65a6ac16103c46db8968ac2cf =
1770950449 0.997 5 0x2d1098b45b7d5126e4af8fb246ad76388c3cc4ea3e8a97021325ffcdc72f0217 =
1770951707 0.997 35 0xe681adf9576f9a66718c35d55266ca30f87d197255b613db14d33fc84c055493 =
1771062147 0.997 5.91 0x88c9880c08d3fe5f31f0a31ff59f62fd2564bf1e9916827a80350c0e0ab120a3 =
1771064729 0.997 17.61 0x234f8c19e74fbc8e044b486103bff0b49c09b08a5c00801c8926297a9527f3a0 =
1771065747 0.997 20 0xe2e6d4e8671328e81a4bc53616e2d51c9b4d42ec2cfa2c1b26e5b8abc8a89e6b =
1771076085 0.997 20 0x20ea17cf19ba4d8197499d2b484f9a86c2d3dc0fbb40726f95bdd50ad43b83e3 =
1771085531 0.997 20 0x7f085554d42e8c560eb3b755f7395c9f5123f49c24823d50cc1304690e6a1a65 =
1771086149 0.997 5.78 0x21d31055420882e463034cd2345a2921842ddd3f208a1b4cdcaf6d7cf39eacc9 =
1771088985 0.999 5.56 0xa8ab5aa519bd2ac95a0158b526fe7858db71de6617c23aa4b11594c7de03508e =
1771089711 0.999 20 0x977f77928a78680afb33fd0c5b5afaab4c9d0ed9409fbf26f101924891cf0654 =
1771103733 0.999 20 0x700b83c3b9d2fbc8f5d73893de2e604511bc2ea9bdf5ec361d9ee9333496f18e =
1771107441 0.999 1.9 0x6cbd96acf92bcb515a3c5e1943d64c290c82332d658b9f562e991a08b820a130 =
1771107551 0.999 15 0x6231acddd7e80179fbb84a8757e2baf7085fd76f71a20a750b315399aef304ac =
1771107551 0.999 30 0xc0868c5fb214f0978d9b4d452a75a431e3b79be2ade0abd2906cf0090486ec78 =
1771107551 0.999 10 0xd59609448fa1ea0493b416f0faf4f5fdd80f6d82152cff193d6dbf6319615066 =
1771108623 0.999 56.53 0xe00ddedb085a01d73989beab05d1cb8a57c8aaf6301112dd808a6a8c81522388 =
1771108685 0.999 29 0xc40f5ba2adeed922411c89bc3db85a50c89a2e0b87d8f656af3b0e75034b0f9c =
1771108685 0.999 5 0xf2669364243daea937082323f8e1e06666d102321f5762228877b873ea85d12b =
1771108861 0.999 5 0x4259996078f00510d0de683b144623cdbdad1b98c7537047f796f28fabb1e006 =
1771108881 0.999 5 0xd418ddca752e4cb253a32dc00bbbc5c2c163cbf9ebd9df2d3497229224660e4b =
1771108903 0.999 5 0x1cff0e2b4de4a2c92f709d247e5766f6bf9b75f9d58183cfd9a9b531fe628b68 =
1771108967 0.999 35 0x17999cff74ae9a360b2b092bc757df582110eee6f9d3c54549c980d4ac9beeec =
1771108971 0.999 15 0xba3e1d8920141b8d79fd26c140a69c6fde3ec00a8bf2e866e8bfd9f0ef537157 =
1771109105 0.999 176 0xebc2840626f8c89d3bb7726bc4e7712f119bd6c11b1062958736405b12ff167b =
1771110711 0.999 12.59 0xb670d1a404bb8e275150dd988a2f946ff2b3b50d5b5908ffe85a7b96c1dbe8c2 =
1771113111 0.999 39 0x4c856086e765f47248254eaa1a94984ea2bc7f3eedec26e601f0ec151520b08b =
1771113883 0.999 20 0x217f16bb08a60ddc1e67cb9d03743dc47af5a3f9a827232b950508f1303bab14 =
1771113897 0.999 16.21 0xa13d38bbc3014a8587ee298dd20f05f0366e0b8f7ba79acad52c153b72bb8005 =
1771117403 0.999 22 0xcfe36522d5d67f29d54a71803632f84441d43526905519d57999c9a4b19f9282 =
1771119801 0.999 55 0xa1b57f958554092b0a3834395da187fb245304c08235a94ff25f2979ed22ed84 =
1771119807 0.999 45.73 0xdb8c6a4751d4f23133bc229d391bf27f6e7d1163e6917a869f5cca1064ddc77a =
1771119901 0.999 20 0xb41c5b9667cbe8d9a7ff822a47ae565ff3a5da5ee28023cf74a9f6a46a905be8 =
1771119901 0.999 5 0xd37c8cd3398b5dcf850f0c4220b7f14c5296aea8a0942fbcab1067c22788d152 =
1771119903 0.999 100 0x1c0381444d0466ff7db52222dfee6e8875ac4079b34b8e21cc40bfecbd5aebbd =
1771119903 0.999 50 0xc739bd07bb8db3b384834367fd9956769a7f8c6616df03e3ed70f8a8a9cdeba5 =
1771119909 0.999 57 0x9bfde7016608659eab1e55ab174ff22b2e4de9a1bb1a84b80783a9bb1746810a =
1771119925 0.999 5 0x2ebea82af972906277573f7db8124839d13fc35830b016c14029bfd68ec0f7eb =
1771120137 0.999 5 0x7da1d70629dfee79f0d40f541e4542844020c8c075dbd473bb5befccb81f5bc2 =
1771120137 0.999 5 0x83713516db9af92787609dcfc99eda4e528c2b494356b33688a8c1b18f761031 =
1771120137 0.999 20 0xc1369760af57a8ff076409ca087aeada3b40d86306791dfbbf89eee4f0093d7b =
1771120151 0.999 5 0x45fbbb26f3ea84f793215ee37203f90bdf252013129acdcf564c8e2dc8af921e =
1771130469 0.999 10.94 0xcc663ec0baa5c593ae01bfdcbdfc417c345ba7f5a8828dc29bb435cb24accc84 =
1771130527 0.999 21.22 0x6a7cca2d494d870faa4cf2cccf61da10678251bcf0b877eae0171e516c212552 =
1771130545 0.999 16 0x91f9a69a3b6a7df8374dda2ef38acf8cb7e7d5b378aec7607040d3ddf67254d4 =
1771130547 0.999 17 0x52752d7cd39d25f2012aaf27a499c279fbfd331e0b067c01b6260114731fad98 =
1771130547 0.999 5.97 0xafbd35a948c27bbbe027d6d0162ba698d4ad7ce3acc6d27b3e4812f67ee89677 =
1771130555 0.999 16 0x9aa69066fcd838ffcd7f6ca32e3f3184b9f3e31053ea9e2313e92448c3ee7981 =
1771130559 0.999 16 0x9f1bb95eb5584a6b9fe9617d113ab750c6d6db3de4002d72c3e41d1eef198291 =
1771130565 0.999 17.79 0xac754eff3c5f9cfa1bbcf74b56f34e8c92e95ad19a409e78acf67002c82547c0 =
1771130579 0.999 8.19 0xe5045343286ecf07938a4c7c71bac63d8697d3f0adfffe6b24b6abc2fb8e7aa8 =
1771135849 0.999 30 0x5d5c741d851053b897f665d9cc28e3d1a7f6f4373f1158c320e12d960b76efc7 =
1771135849 0.999 20 0xdb06a8fe408a35d5137fd972b7f4543595c29f810bd229c25bad60e5e1284ad7 =
1771135851 0.999 479 0xf3e1e84a5be896e7a08454875d360a280fe310ffeb7782143e26b1e13d02a8d9 =
1771135857 0.999 71.25 0xf67d7602f45268bd89b86ca8819d063484662117dd8aed25eb4d856be8764e31 =
1771135865 0.999 5.43 0x175615902f93e061a114ff2e68c5b77312c2a5f7301d681ee039ecdbf35b2ede =
1771136045 0.998 20 0xc88650d098f065cca71b73f1b30551d351a99fc5236ef1e83a2443e32f153bec =
1771136045 0.998870229 131 0xfc58a81d5f14ceeb2e28bb1e120d5e53c3dbfff0f287652f163464d7b6f11962 =
1771136053 0.999 71.25 0xcacc98d5decfcbf32cc9dd714b95eabfc56f8cb73dcda1386de7041b9895aff4 =
1771136203 0.997 5 0x531e6988c2b18e2c8d057dae5e135079eb5f15822211ce59640c32037d7a5bb8 =
1771136203 0.9978 5 0xf8f4819077a90c979f6b3a2ff766fff36f8c155aa125c7dbee9314de5346aa7b =
1771136741 0.997 5 0x8a9c48a234c0d64590d50d7c3b470e73b40daed6119ad29c741d0cc3ac38f124 =
1771136907 0.997 15 0xf7c02d439d92a0119dd4fd743acaeace6a6491d21650bb6474f98d1213d51c10 =
1771137995 0.997 35 0x5b20f111a8a99c4b6c7368fc304e9d2d028a05a8ed33ce7450d5f51bcf99da0f =
1771137995 0.997 158.72 0x9b31a6e461a30eec862aa03ff1098b6ea1e862710ee5011aa887be6801b1752e =
1771137995 0.997 1.28 0xb262eb88833474867471ad40755e2349154ea1e0896eedb3e9abd3919a911ca6 =
1771138005 0.999 6.36 0x9c8285d450848a6bb6f49349fb38f8abd253db106a5f56a1d9d7a20b36eface5 =
1771138387 0.999 10 0xb98d80216ee83318d32116ed3b37bcc4e900d16f71c3517870d5e6079337c590 =
1771138387 0.999 10 0xc400b58955a25e0252976e73024b2653a66ca93b66430f7c9e61159b7dc3bb17 =
1771148817 0.999 1052 0x0c35d64a3f201cee8f4d36b7b3212a63d12949e3a74e340b2b6daf971180031c =
1771153219 0.996 20 0x1543858c8603d3a70789dc4faa727e539f827b67eda8afc181ef032b14221311 =
1771153227 0.9960322581 31 0xa2d7f84582cc73507b970a9978c264ba2df3f3356788342eb5482edfe234c2bd =
1771155109 0.997 10 0x36ab7ac8dd293378db01401c4df88918045974642c87eb266be0779a2518870c =
1771155109 0.997 10 0x6855ada4ce7059f9632cc136c07cad8044c3816d17b509ff2fc1f104a7cea67b =
1771155109 0.997 20.1 0x7f545e41797b9f7732c650197f402a3377a27b858a3c3532811cdc4ae6769f89 =
1771157435 0.997 545 0x40ff678cf24e835cbb41dcfd96d0188d4299fd9c3aef447ca6a90d59af2b003c =
1771157839 0.997 12.5 0xa4621784e889bc9e7eaa845a31d8b9ed8cc448856d9b27fe83959a3c363f620d =
1771160815 0.997 299 0x1dfe81127654266c9a816b796eeb9e194f0b759d4336a64a857017d17460cbab =
1771160817 0.997 15 0xf8af5d288cc379b6491a4eb48af976e6cf3a8a58322d29f017d6a580ca3f682b =
1771160825 0.997 57 0xeb562d2132115cfaa7fdee9002186d51cb45c33156e109543f6bf912e53d65b2 =
1771161779 0.997 15 0x08c2cf1e09d18a98834af660557242124c19de1c661ed0c2c54ef02f79a85033 =
1771161937 0.997 15.51 0x24542751ebd223ede90436066bd70cb41655611cd5d32272f9c59742784b5c68 =
1771161937 0.997 14.49 0xecc97b945120cf6f56e4bd2bdcabd69bbc019746eda4a47f8442203eda246419 =
1771164465 0.997 985.4 0x1ff14ed9ee84d33ab4a31b387b68d351923f92d0e62f72bef3fe230e3f22c5fc =
@1347959 Yes
1770415409 0.02 59.99 0x94d371defafa494ac0e567b2266ec4b9b471e692d7a03b9ab8d6efedc4ca72c2 =
1770483003 0.001 57 0x69ac6539a1fa05f1d3883d52dc8aa09814c638dd02b27dfdffbae21c5b193c7c =
1770483003 0.001 6.12 0x9ec71e84e8f1dc503186d3d32064548c4a3d999f6572c76f27248a4f66805e1b =
1770483003 0.001 49 0xf52213d90361eb92e46684683b4178e67d9702084b2a8e1f2e82668040bca4bd =
1770539111 0.001 0.25 0x23facf5011994606d81baae75f2ffe17b6128a791b997ace93f9220864d4c009 =
1770638847 0.0197628849 252.9995 0x06fc730c266a55254f925bb384fb4bc92732c41c4e95610d1b5607801515a3eb =
1770713555 0.001 0.47 0x03ebe9e158191c77dc893eb9c68acb2fee7c3008c4d261ca7a94e4dfcf2b4783 =
1770898647 0.01 2.41 0xe905ea76653977c639959f34d144d799a6a14e5c5062b83a42e5793ad5e84efd =
1770947941 0.004 2 0x83fa12e2b5daf66e982f2d95172cbdd8f620f0235b62f6ef12bc2e923ca8b9bd =
1771107825 0.001 4.08 0xb3574100213ad8f83fd4d6bcb2d35f91d30635d1c5bea8300a3968d1ccf7de46 =
1771108929 0.001 38.09 0x9406147003fdc90a7ddbe892bad52d2d1e02b966f1854258b6d9e91afeaf092b =
1771108949 0.001 89.22 0xde545db3489327f2b345460644a48c14d71d75be8e19b939fbe77aa758894390 =
1771109149 0.001 15 0x7d00f0ef1b34c07f1ab29a446a3cf701f252d30fa415e3cb0323c5fc0e3f3ab4 =
1771123521 0.001 6 0x352f50fc7b04f3fbdca4b5e14ff5286bf681f303c7f7e5ce0ea96ee0ecc8a492 =
1771130559 0.0067885117 153.2 0x595865cae4e26e256f17fdc2b2d6dbcf9a40f63ccb6c05f49667628167320922 =
1771130565 0.030061322 34.595917 0xcaadb8a7c10c967d94a1a855dec2028a5e7412b727e316b090a0012156967fcb =
1771130569 0.0759999354 13.684209 0x14c1637f946e3d16635c3a38b3598c35e2d4b8a593ea66d6a4ec39d8811e2944 =
1771130571 0.0769999345 13.506492 0x9e1a872b3b13a6cb9c9307913deba7d16b243e930a713f27d4ff8e85aa9c9887 =
1771130577 0.0769999345 13.506492 0x51299f54c09f8b3b8dd20dbacb6fd6861579bce72691be1ebce7ab94be807c24 =
1771138005 0.0084791885 238.09 0x5d70f2897e8b1d032a045b9c942375e246352f6ef7a3429d3fa46027b3e14013 =
1771138029 0.001 0.45 0xc220c6197f1d968a8f28c7934284b3eda50425996a6c465b04ea100d01c66286 =
1771138031 0.009 238.09 0x93654f7c6de7edbfaa2df966e28a52ebea19a66b1e148cc0a865deb8a4567ca3 =
1771178533 0.001 1000 0xb41bec1e7604512dd194941cccf9809a11de7d7237c0c89bd5d74056673f4a61 =
@1347959 No
1770426165 0.99 10 0x088a38886fc0bb0a093899eef5e53dd80dec441abc0f52a65cea837b559f22ab =
1770426169 0.99 18.0303 0xe11d2ec31855e69d8089a5222a8e99a5e35b1744ad140da8b8623339c54ec061 =
1770458431 0.99 10 0x2c5e8b2f52fc0d62aa22cec25586c8ebebc385d53c6b59b969f7a7c1aa735f4c =
1770462375 0.99 7.04 0x9910f105de326d68af040ebfe83782f92b1c646c9b12cedf9fd4fca4c93240c2 =
1770462393 0.99 5.23 0x300bc6c055497d81e4769ac22b69200c9206f8da67ecd8ef0ea8671c922f909e =
1770464351 0.99 28 0xaf86162cd4ead03ab4df70169a5d99183af9ec2b0616bdcc309f5ca71e240fae =
1770464365 0.99 28 0x347809a54e6a6ce687ea63edf3b9d8a455abb66626f8cd67febc7b519bee2b8d =
1770466975 0.99 8.0909 0xc136b4656a291bb378ad45f3919de29f44fd6e47f08eeb6047109cfc61bc4008 =
1770473065 0.9933805263 57 0xc45892ea3d442ded9f0bc76b76331aa868b95aa2ade89654748d8d5ec4e18622 =
1770475253 0.999 13.88 0x7d654ad2ff69104d96790c725f541cd5175261c78256f4dbcdbc2ba661682f85 =
1770706299 0.999 10 0xc67c4bce04bf3814324f8c7d887eebcbe898e949bcb41c9a582319933fa31063 =
1770706301 0.999 20 0x5344e284b6448dc2665bc7552dba79170dd14eab03069a96cf883a34cc53510e =
1770713319 0.999 17 0x675206c81b98731d26917ff2f37d16b863039ff9faa4cd3a7d4dfc0b833cd6ce =
1770713725 0.999 23 0x211a66f0ac3c713a8db0a1ef468cfd82b545a230052ea07cc3347b2443c68ef3 =
1770713725 0.999 30 0x832370a9d38ec0fd86d6b1fe29db73038d5e04cc490e5972054f253daab67acb =
1770713725 0.999 10 0xcb0a6f58fadfd0161b58bd4e73696b73dcb65db2c9869b81f852ab24c4843f1d =
1770757169 0.99 6.46 0xcc6b38e9053574da65908b9d0853176f5bfb6ce626260f201fef4ab01a64d852 =
1770762893 0.99 64.34 0x831dfef0bcccd34364bf47bb8b615d77c6e1524aa43969faa2152d8b6a41fd1f =
1770827589 0.999 10 0x0e9e5b406ce3178eb79bfd5521e90b628a94e91c6e47baf1b8a7468c6aff6934 =
1770871293 0.99 5.8888 0x1338c0c4386fba07bf661ce6d722e8ed4ffdef333ca2019a1d910b0d934524ff =
1770871753 0.99 30 0x6a36e8a1fc2e3e3e0970a7470eef31cfcb21626e5b24bb7740106cfd389fe1e1 =
1770905533 0.99 56.49 0x44bbc435ae0e366c3cccc37a2e96a208a0bd1c51c96d006dc3b44e502c38dcb0 =
1770935453 0.99 5 0x4a216ebef4797fba15bca35e53ef1b8d981ce1ceebdad39566d959950f3a0fb8 =
1770941197 0.994437 30 0x190f09e0102215f8d2e3da131b07be0d3beb5b75e46bca008d5282184424336e =
1770941207 0.999 71.25 0x970546e78cfb23188253944d3f6c20434ffd881babd563be11186a33f48cb3e5 =
1770941221 0.999 71.25 0x8e1dd9d3c7f46ed46dacacd120771f32ece15a7d531de0caaeb0170d20d77047 =
1770946273 0.996 5 0x17e4cb1fffe8a0e21014ada22ebd0e9839c0a69295e5a10911af06cbd944e41a =
1770950449 0.997 5 0xcb8f0bb68b591a28d6f2afec7e45e0eacf05fb904cb139219f5dafaa38009b07 =
1770951709 0.997 35 0xd08defbc0df66182d440943a87a84736e800117edb93ae3f6aeeec53045ab6ec =
1771062147 0.997 5.91 0x76f1ba0d9ce2db65540fee1bc33f1482abf64caaffec9334ad123ccf222ce676 =
1771064729 0.997 17.61 0x324c3f9f1134a87a9438f85515b59f4c62a0514fa1fd55e4eaa362526b6f6b7d =
1771065747 0.997 20 0x101b9def2d096088e82e2524035e1d05b299b0750a7f4689ea491502d198ef43 =
1771076085 0.997 20 0x0c4e3a38888b2cedcddf1f56d393a0008b25875d7ffd7e77fe983a2b293eb956 =
1771085533 0.997 20 0xb9babd29465e6a8b00c42f157f0182dc71c56722886a55205d398f237243e009 =
1771086149 0.999 5.78 0x7052215c78da50373dfb3c6a825602b02e79a06f2ccddfd906602aa20b56198a =
1771088985 0.999 5.56 0x827f4169fb770029491aa8a7a6e2e8cb21313e094b929ad18fa26d26726c6a6e =
1771089711 0.999 20 0x06f9fca99d9fb3f23362ed87ce62a3f137a3d0cde1af80e587f6e313b607d961 =
1771103733 0.999 20 0x70583eef74aac606681ebf4bc9db8a407ccc15674cd561b067e3578af51d2ea5 =
1771107441 0.999 1.9 0xfbcf5406095eab95010257f9194d13886b2c5292458f423637f3b3f23495b04e =
1771107551 0.999 10 0x00e771fb9d27924ecec2f0be8ea6f2e10368f637a7bad5aa19b17032cbe37475 =
1771107551 0.999 30 0x207266f98597bb46f8bbfb2244918291ed181f76fe593cd719fe9a81cc487393 =
1771107553 0.999 15 0x7da317c11494b9e146eb379b45af85307067aedfae1f4dae3269b925eb0b67fa =
1771108623 0.999 56.53 0xe6ae8c83e99cf1db6f2bded47fa38da197934d11d294ff52a5ee3b9ad3f1202b =
1771108685 0.999 29 0x3b6556b374974557f95704dd93cbff56feb9a6954a687cfc15e829a2a5ebe26a =
1771108685 0.999 5 0xa0e5b7a6e6c976545a5d54284d2f2bfbcb5b6aba1a262b71079799e0d5fa26dd =
1771108861 0.999 5 0x517b1da385f810bc8d35aea78eede275a348f4dddfb4ca3c9af941242fc99b07 =
1771108881 0.999 5 0xe96e218f959329401f1055e670b5a5b95901432dce7c9e69a2170e26eda66108 =
1771108903 0.999 5 0x253bb2e9d55c7af5de4efc455dc81a89ff6210730c392a843be9985e25b40bfa =
1771108967 0.999 35 0xf4f4d58b1afe6b32c559cc4135991077cf01584c6dd09ab88980192817298c69 =
1771108971 0.999 15 0xad08131eac1e2cb0c9a8c5f598f069b9ba8220ec4ee909ca83a99a3dd5369a4a =
1771109105 0.999 176 0x17509c040437d3200741b032c3bd97acac45be0eb9232dd317f9670c75efc5d3 =
1771110711 0.999 12.59 0xb0a1462f6e0f0544aeb5a4689e0024bd418d57bf801df94031d4ffc0a7f9d62d =
1771113111 0.999 39 0x64a7565247a1d029329203b8389663efebcacf55c054a6e386f9876bcb4d082a =
1771113883 0.999 20 0x42aa9a88c7e61da0aee4750cc779006f1072866181a0197edd015fbd94c78420 =
1771113895 0.999 16.21 0x3186936bf91b626abd0d5c6ec89a052dd49692ddb06658e587065091ce4f1f15 =
1771117403 0.999 22 0xfc8130961990e922d7b9c2bdd8c75fbe801403ca3d0922cfa8d92dd0cd3ccfe6 =
1771119801 0.999 55 0xa0d58c1104cd8eda619797d4468c4b793bc1dc9291603d88b3a1bc21f8f1c062 =
1771119807 0.999 45.73 0x8c7a3b1cace91a2dc743620e2500a694a1b14250ad011f20bcfd25d928e1ca9a =
1771119901 0.999 5 0xf9af5e5d36759ca79fdb5303e6ca24d33de6a9b50fca70b6b4bd2855bd8d6a06 =
1771119903 0.999 20 0x1c1dc72ce79c3e95f92bc17c1d2d7ccb3739e319dba22de7f61d537cb9f6a8b6 =
1771119903 0.999 100 0x808ffec660a9f6bfec04dea13bbff843995b4dc5f3e39d9043c5cb9403986bc9 =
1771119903 0.999 50 0x9e528734d0899dc8f7c83cfcc7812fa875c3c96c1903e096c8f5e2ad1761d8d5 =
1771119909 0.999 57 0xde167b344be9ac32b5449d6b76cffb31b0125e0455550702569ea064edc60b74 =
1771119925 0.999 5 0x5bcfc25f5d2b600603a8f5e3f19b9e01c7f56f415a8fd309cfd084ac68d9e885 =
1771120137 0.999 5 0x0a90b28c96f2ab2ef08f222cccc556323b3c1cd72a1c6a74f00001519897dfa9 =
1771120137 0.999 5 0x4d54e2ed4721f1ee56cb0222b645a3cc12ab63a495a7aab4d5455e785d6c8599 =
1771120137 0.999 20 0x53037b87a43e7108f0cfa92db49cce60b832df7577f9baeab79456d273d82258 =
1771120151 0.999 5 0x3e51e80e1cce053c0d0d5a8c53a1e992a1fc9a272e670f5679369a53508a9ccb =
1771130469 0.999 10.94 0xba041ee5ae55698a51a89eb194bdb5dc0235dd6e575b2a3918c930abf43e6198 =
1771130527 0.999 21.22 0x1bfee14f6d46d666f31a62b759e65fd75d32c95b8b58512c8aeef91202b5f4c3 =
1771130545 0.999 16 0x312206814ceb1229638e864c85e04250c851a8bef922bb2bef349b8f17ae0cfd =
1771130547 0.999 5.97 0xc93f35f78502566a06d0635c9081656f370eaa7a77963b08403988f352ed7a06 =
1771130547 0.999 17 0xcf7c4c485feb1e831f4f150273494ea29e7ecc93ab32b0340589bbd21186537a =
1771130555 0.999 16 0x9a884a813210c5bf51e9b1371ebd76d4df4efb64c050b1d6aabe67193435c37e =
1771130559 0.999 16 0x566a87ce34d95c2f0d5bfa42a1c03822654ef09890f3949571a9663ace592d39 =
1771130581 0.998 8.19 0x1eca27ce357f85d3ce7cb2f9b9a57afc415cc1fd2b3e4a7d4d245025d2705a4d =
1771135849 0.999 30 0xb7d9f740f773e0da1d68acf5d849ce3811b2bb918ceb83e16d8307dfeef3de1f =
1771135851 0.999 481 0x6b5538c70bdf060e21c9f636603160ff81fc8c79463661a86904530f3233d8f1 =
1771135851 0.999 20 0xcecf7f175b9e69fcfc5c0e679d5f27882cceecec170616d6613f4f184a6f15b8 =
1771135857 0.999 71.25 0x3b3e8b6e38697f636217496880609e2eaefbaf0f554a17579d8470ebc663a288 =
1771135863 0.999 5.43 0x4262abc181b1019475d64a03f1ea327d6057a737418d32fea9ebb8346bd6025f =
1771136045 0.9989160305 131 0x1c421c1271ac4fcbd93080d0d95cc2bde7397600115df9185a671d98ced2333f =
1771136045 0.998 20 0xad571a40e503119e9d64fc52cf264484624106359875cfdf001881204c940e03 =
1771136053 0.999 71.25 0xbe48345f824fc327d1f0549f4a370677c9e9424f220c4e77139485b43bec0854 =
1771136201 0.997 5 0x3a06d17eafecbbc8466338ca2a9f2d33cf6c1812c701ac0216468663418ddcb9 =
1771136203 0.997 4 0x3e7e1257a1d4894cd37f7f18b533f548014a74e42c707f243b4e7b2ada52b29d =
1771136741 0.997 5 0x7f5014ba979bba0cd7af0eff9e98aea2c75094a9224f557b918141eb37048044 =
1771136907 0.997 15 0x3f205f7f8f76b702a28a24e8b3c91366d72e52757dc278dc6a9398439f90d2ea =
1771137995 0.997 160 0xba100c34418ce75dd9ee6596095f6977957d1b697bebf6a2f18e373553652999 =
1771137995 0.997 35 0xe73802df6f12b078cc6112156202e84330828b562f1a7b4bb6ada57afe589c8c =
1771138005 0.999 6.36 0xd37a85afb92d470e8f8d7387665011633a4426d21ae73d5788fc617ad18eb56f =
1771138387 0.999 10 0x7d4c64dba4e0eee8c84fcec40f6ecb5e7bb3ff8a372a8c33550c0bb8802e3f4d =
1771138387 0.999 10 0xb9c565ecfe37ae4c83be2445913f1a10685e81a2cca674177e578540c11b5a45 =
1771148817 0.998 100 0xe59fbebe7409a538048f70812db33dcc68df1fcd600ef88553467bc38378c77f =
1771153219 0.999 5 0xb885d9b84c46f898879c1419ebeae1c48ff9492c5ed821d514fc29682030649e =
@1347960 Yes
1770483049 0.01 14.71 0xa99fc0f9df87bf10b0e2d819d71e8264239a4e6f634b5c37881bcae701f86476 =
1770483345 0.001 48.12 0xc70f7367ebb16577699b0e65e15915d772c90c85d87c2af26af86a6e1bc9e528 =
1770488691 0.001 49.29 0xc3d3c3d01d7e968c1914d21315cb783c078baa60d0148ff6d2a84918442e1046 =
1770539111 0.001 0.25 0xfcdd0e44cce34d506cd8a39eaed08801970529c17312d9ed8edf85bd72081342 =
1770713323 0.01 97.41 0xbd05a180c5f92bb967b323261905580842c6852153cb903f7ddd7ffac9e13474 =
1770713555 0.011 0.47 0x88cca78885e510ee696e37a004e5dcd319cbb1d4a3cb82eb37576d94b25e6598 =
1770898647 0.001 2.41 0x3c9bb88709d285a6f5a62ab3e8a851f8fedf5a08fb173ee656ec175f1b36b990 =
1770946399 0.001 5 0x4ec9705f745d606667ce74cabf57972e50e10a480da8fae38bbd4bd7d866b6dd =
1771107825 0.001 4.08 0x469222e510f67e36d44f65ab23939814a71fae470481ed2cc3480dd4ad21bab2 =
1771108931 0.001 38.09 0xcdd1675ce8ac3310357d63da30ac4c9f0ee7464511fa5a3ffcfbb89176211796 =
1771108949 0.001 89.22 0xb6cc8ea67163400bdb98d800a0f7ee33b894f26e760af1f31508465de5939ee7 =
1771109081 0.001 15 0xe6b6bc93d881ad04f1a28331b3801bf526abcee9a0c0e3e12bfc9f68118ecd1f =
1771120071 0.002 5 0x3014783fb9384800f559e72dac24fdb0dd1086dc39fa6b2fc66456a9b07d799e =
1771123577 0.001 8 0x4da382161515560bdc4cc0b7007dfe3fb17c7d3d88194e52c46be5c10b581cbe =
1771130543 0.009 115.555555 0xce69ebe5f8fef4af87dca0daec0f7fc1571ceebe33d9af53ca7ba55c2f3d8bf7 =
1771130557 0.009353275 111.191 0x86eb9df853d7d244bef6513658223a2c68e28a1333aeb160b5b98f9e5e4a6a08 =
1771130559 0.0107485355 96.757368 0x1b8e76085a83acfd3d4a0f9c3dd46d0bd5ea8c2d96e3856954dbd6abbafa6806 =
1771130575 0.0184328186 56.421051 0xea4e69da63e6a00d863210bcc27f1c62246e9c4b9d06e8d6e089083845c2f828 =
1771130579 0.0303841761 34.22831 0x08706d4160ddb58984ab61dd2e86aa9b1f31dc9d56c5403ad3414f21cdad3f4e =
1771130581 0.002 0.37 0x82bef4a49190d82e98804c998373f45dcdb19630c2f3dc93f13ef2238dd6aff6 =
1771130599 0.001 0.82 0x8ed22b0b2fbdc992f4902b1d0487134a49a9296e528afc7e2eb6192a6335ae26 =
1771135863 0.01 104 0x999977211e0ed18bb3f7310de2767f2be0a8d8c975c8ba9e4a160e4bdff599df =
1771135863 0.01 104 0xb1faf19218c0cf2d179db85c981bb65d5ad83d317e61dd99d8681749106e189d =
1771135863 0.01 104 0xfda926f549ba68683b124500e38b5e8370c10a9221ff7e2a48bfbc8327687fd2 =
1771135865 0.01 104 0x1c0388db3f505737f5c96c8b996cae2f7b5058a3455563a4c4a68dd5324fa58c =
1771137995 0.0084455878 238.09 0x5a2819bec64f1afaa2765d1ddbb510577d7c98317d8221b8f604ee6623939947 =
1771137997 0.009 238.09 0xc78a9300a7fbe391a38ef04199e3ad94786475ead3dda585d3140449042e65d8 =
1771137997 0.0082523836 238.09 0xccea77195a637b280656f02285222018f6a913a9ffebbe185732bd5035e3768c =
1771138005 0.009 238.09 0x56fe600c6cc46864649e15787ed2c417090fe7e6dbd8281ba013a464875b7e48 =
1771138011 0.002 0.82 0x16e60e1419b0be0d478dcf1aca8cf8d3a747e39a737876cf0c6dcb3bd1a0ce6e =
1771138011 0.001 0.82 0x5e154a2900248e6b4cea51714e81e73ad17fe9c23553d0ecaf5848f2a90ea760 =
1771138011 0.0086933933 238.09 0xf30c31f543c8c257104256cb8609b0cfbe2053b3b06f4fdcf1e3f1811f3bc7a0 =
1771138013 0.001 1.65 0xa9ffeeb6950fe23cf8c9c4b3a6118d83611256e812047362cdda6d681415e38c =
1771138015 0.009 238.09 0x53099f69f6066c432d11830b3c1955a5d974d157c37e05c218996423fa87815a =
1771138023 0.01 238.09 0x0e9c6b5d96622839560d7a118d33efebba2317118b72f24c042a23fe0c7c2958 =
1771138023 0.001 2.47 0x7bf67cd3ff5c891f65901454ebb65487b27dc5471b91b927f9b79822c599a5c1 =
1771138023 0.0098665211 238.09 0xbbb1b2e9d4d056faa89677a3f7294e1f3f5ad7c0982036305c474e2734971d43 =
1771138023 0.001 3.3 0xcb971e9884862759d36cd0ae2b55a3bddcf5c2ef47eeac7e7d9e920e8a22d6fb =
1771138025 0.01 238.09 0x3dbcd97e4545599473f1557b3650727340ddb8e84bffdade592b1835a2cd2d5f =
1771138025 0.001 4.95 0x66606de128991cb40dd3b4284a1e65d294ef3a6671c9b7dc923618ec1504d730 =
1771138039 0.001 0.81 0x9156d8886d80d15bdd635fc3eccde759f6e0f8ddee15a865af2e764fbcdcbbe6 =
1771159037 0.002 87.5 0x3771d54a88d60dc8ef9b2ef9bc3f83effb94a42116c57c148a08e1cda3d42f99 =
1771178533 0.001 1000 0x8d2054429573ba4924bbba42b5efdb8a67ad2e63fa038bc6aeff422bb12f44a0 =
@1347960 No
1770415109 0.98 59.99 0xce49f3d9c513ed1e2da0bec91064db439aa464a743e164335bc5f99ef9d9489e =
1770426171 0.99 18.0303 0x6e6814e2da29c7ed62dd37037f394b271688235c7986769693303f94a0e4227a =
1770426181 0.99 10 0x000dbad50f4b96d7e336b9118d4e1b0fc281f5421279113fe78b88b3d643c8de =
1770458431 0.99 10 0x64782114969a3508ccf3a42ebdfa8cc9f8535f3a8ef6ef854fbdea9323ae1fb0 =
1770462375 0.99 7.04 0x31814d58e3159c9c8cbdede415b0c57447af8e49205285499b9b00d5ef8c5fa9 =
1770462393 0.99 5.23 0xc6abfb5a962524b7295a166cb34fb8fffa31878810c455cfdcb4f4784c6b1540 =
1770464353 0.99 28 0x43afa99d66339916aa489163f1b43a1b942773d22232d54d28a9b518d700ad79 =
1770464365 0.99 28 0x59e61c8dd679897d647b6cc725d3d3264045460550c49e836cb24ff108ba33cf =
1770466975 0.99 8.0909 0x7d05b4fdb5ed8e2e082344436b0fd27a151fb12c23ee0ecbaaf18ed61b3bf6a2 =
1770473065 0.99 57 0xc75ff7fd1f44aa20ac5d884eb3beace017109074d99e58777e1055c7f0cb1afe =
1770475253 0.99 13.88 0x41c0c5788ea569b7a044192f2a31c1b3e3a79168706d98acbc986819d8e23ccb =
1770706299 0.999 10 0xb96f7331beb78749020a63620df6cc43ab6a97681e44167cab52fca5d6da6c5a =
1770706301 0.999 20 0xd6910019dccd082a160a61f0df60589f68f7063ba42dc80cd69290770c3d6469 =
1770713319 0.999 17 0xba917ed6090eb3faf5f43c5509e128e849cd2cd5e884b307e9335f36c2dc98fd =
1770713725 0.989 30 0x56c3e0dbea054f1b2b99f38b53969a7a760bc3ca61393b075d6528fff3cc9ae2 =
1770713725 0.989 10 0x65036a82ed31a1074cb0c3b025a1c0f57555b13653c2a7d12d126aa948b855d1 =
1770713725 0.989 23 0xa61e35ffc59ecf1d2d0666e574279b3540d52b063b8eed29e90298ec41a51c16 =
1770757167 0.999 6.46 0x987e6be3d868d7a2062267aadf09906eb55dc0af138e1bd0e16d2c4a1e7dc405 =
1770827589 0.999 10 0xf6506e4c3d9ab05784accea2c0788e6f28660c2fdd45b0091511d7fd60871648 =
1770871293 0.999 5.88 0xf0c0a53fee700ee86e60e45ec2ebabb3a0cb7cc42ec08c6ea4758bdf7e06281c =
1770871753 0.999 30 0xe53a7b03c6de71268da780ee56d504190fb5825d4e799ed5a7861ea79e71fe05 =
1770905533 0.999 56.49 0xf214aa8654394aec4106dd48fdc9f9ddf965fbbc11956c6794af19125667bebb =
1770935453 0.999 5 0x007a048fb050dd19cd17742bc7ec727d44759bbf8f321c497de51d6855a68c32 =
1770941197 0.9945 30 0xf1cc14c81d4bb30cbadc88b9fdfe7508048d16f5f717afc8554a904fb4beb865 =
1770941207 0.999 71.25 0xd2d5b5c183681a4c97fb86131579d02236b51e9eb47490709ead0a61abf7cbe3 =
1770941221 0.999 71.25 0x506a6876f5a52db82815d7bf48a0a38ea59ea4e8c1a6f1f1f61097893dbb378c =
1770950449 0.999 5 0x2efd693f76936ba6300566f76e378d39e1e72c3db15767eef2d3c16003716341 =
1770951707 0.999 35 0x2f78024e6078ca2a9bcd06332a5d976235a593ebcdd21b1e05e58a35a567f3de =
1771062147 0.996 5.91 0xbff4c514b8b24f823eec44b56a21714e0fea519b8c3a7ba13f44c40963dbbd58 =
1771064729 0.996 17.61 0x5b306a13ae79362921754cc8453c82c42269e40d5a74cddac6a832e88fd79d8f =
1771065747 0.996 20 0xbb1b1c98ce397d957115ad1589dbe96c444efbcbcdad0ef04d13cd68196bcd52 =
1771076085 0.996726 20 0x3244c17d9405260ba09f412f296ace5bb965f836a0bc17a705b8cd9390bd4ed8 =
1771085533 0.997 20 0xc96eade28a0cdf6b30318f2ebe496d8cf6c667d88841c03b74633762fa04bcfb =
1771086149 0.997 5.78 0xd218dc204ad8bf5c382138d67439796859163dfaf36b30602e64b8a18d27bd72 =
1771087533 0.9981460101 18.033 0x7cb36797a20b922e9b86b18106435ec2f87ecf43cc7867dbadae2cb7d4ce50c1 =
1771088985 0.999 5.56 0x597aa8ad574c30b89e9dfc6f95f9be83ef5a82cd2686cb665351e8bf8cbc6e0b =
1771089711 0.999 20 0xb1fef5ec55e71303f57b1ed563054339e697824e99df3d85c6e9aa4309ac4daf =
1771103733 0.999 20 0x61491e3c9caeedd2dd150c565bf954e06ddee52753e3d5be45600f7b95159758 =
1771107441 0.999 1.9 0xc95940cbc29a01cfd119c7ad9f590633fea3c063679ab8f36fb1fb4e86cab1bc =
1771107551 0.999 10 0x2ff9f850cb816795c1b5b51a8e11cf1f5e48eae5ff0818641c8c2722bd4c91d0 =
1771107551 0.999 30 0xbcfcd0c54b0b5803e160196d6a60fb09ad37d19946c4d3fee09fc55f14ed5888 =
1771107553 0.999 15 0xd2fa4eced19b3b401252530bd8cf2c1b35e495aecb9bfe80e79d4cfa0afd1428 =
1771108623 0.999 56.53 0x1134f7e7c647cdaa3aad64410d8466da9a64ecf7c15c2f4c76c0590d99c60bb7 =
1771108685 0.999 29 0xd0821e4873effd2c5a8012d85998a0b89e6456c5c19f8e6b6f63948d71ff395c =
1771108685 0.999 5 0xefdb9f7cc85c5ce05d6c5d3763713fecccd80daeb752ea5f4c3e8f5b737b2d14 =
1771108861 0.999 5 0x87b0f008c9d10d7d6ddd77ed24687e3ec0749db66e8b1a586fc5a11f06b24aa3 =
1771108881 0.999 5 0x0d65b164ed2b081a85fed1e5a2c80f947aca7e7292f994d7333ddb1b4e6e68fa =
1771108901 0.999 5 0xbc776d7d2c2c086e5d2e8460ca698f2d5d010fe858a99d9b23ae539a0d3814a1 =
1771108967 0.999 35 0x5f201080821cc7d5a9d9f7cf3210b1bb07b415570165c7d9085cfd577f6dc85c =
1771108971 0.999 15 0x60d9a67840ec6c5ea3c06f2c40eee6d44858f18132e71a72983881656f0361ca =
1771109105 0.999 176 0x4c6a9d3886a8a124c730ed3ae938d64e6924c32bfd6931853f979e9cb4ce8c88 =
1771110711 0.999 12.59 0xec0b7fa9e855bede123f4e243323496c6964d947cfcb1a5c36a92a69950c4b8e =
1771113111 0.999 39 0x8f280cc58946e838ee32a05dd43d3ed7d013fc855b508bb05b6c374d88533e92 =
1771113883 0.999 20 0x6a2c1eb215f35470dd65894ed651ee9b2494e531a4b5bbcc8068c34962af6798 =
1771113895 0.999 16.21 0x5e57860e6803d4a6bd6cf4d79497e61c80f0ece5de43903d299e815cfe2de980 =
1771117403 0.999 22 0x3cdfeadcd2ee610d9d7584762b9274273aafd59b5351561453cb1c88ba252fc0 =
1771119799 0.999 55 0xd68ece31e520a9baa5ad7479aa2aa557b00ccf87f662208e9be1f15e69cd11f1 =
1771119807 0.999 45.73 0x3e880a80e239971005273b93fdcc28baa5b16f49bd74fc83a02c835ff5f6be86 =
1771119901 0.999 5 0x19477438db5043a2ecfae109fd7a6000777ba788441213ca47b4ffddb0233fe1 =
1771119903 0.999 20 0x52a4bdabb061bd6d84f646f3af0524542875dc66e48fe13bae96a4aff7783499 =
1771119903 0.999 100 0x5323050d09310bd3d267996c3d7171d70b2707d48b056644df40e4f8465307b6 =
1771119903 0.999 50 0x76f114e47b51b9fea756677dfb4f9e518d3c9ba984c57aedc753d04fea090ab9 =
1771119909 0.999 57 0x8c0c6f6ad222d551954a8bf686ab31c11c8663bc57ad6d1fed3df18ff77c381a =
1771120137 0.999 20 0x29e25255510ac378f986627abf7a07245123ab3d8032bc1b6ceb84f4128ee583 =
1771120137 0.999 5 0x672e49176750593d154cccf48b9e82e450ee47992e63279d55f6e8c84edc7152 =
1771120137 0.999 5 0x78c182c7bfe0db467952f24bd6747b9db93c967dabdf977f0f743603cd2ced53 =
1771120151 0.999 5 0xe21a63b4b980c6a09633cf895a6fb629067f42def7f3ce4bcd0572f42647c517 =
1771130469 0.999 10.94 0x8c62ff7eca3d4cc97ffb8301a02f07e79a6a33f9f3f53035b2860680e0806914 =
1771130527 0.999 21.22 0xdc2671bb94d4573854e2a39f237d6b34d73550ee799f9e3b4da38e63feb818d1 =
1771130545 0.999 16 0xf5cd5c520d45a2965f7fc58b00b359182ddcd3b081e08abc96a02f4e259c9428 =
1771130547 0.999 17 0x5272d10d9ec211e587896ab99021e40af5af420c0f6bf44bad10a09ba030b60e =
1771130547 0.999 5.97 0xc61c5510c2f8df397436b65a87a623d6b86e1e826e50470c0164a17e193e1fd6 =
1771130555 0.999 16 0x7503474b0b547d7c678cc043d04290de6f65b8f2e3ddbdfdf056899520968ce3 =
1771130563 0.999 17.79 0xb306289b08d8774c9b3677a1a8eb64361f29cb5ca56bcaaabe84608de69ba272 =
1771130579 0.998 8.19 0x21f13fc29496262951c9f1900a4e11e568a47c97534d37885d1c4a95e4f627df =
1771135849 0.999 20 0x0845f03134eb853eb8befe389f0ac5c6242798a64524188cdea255b207018d32 =
1771135849 0.999 30 0x163ed9105dacb56f8dc06bdafe5261c9540ffa1b826eb6c353ff32dca42ebe6a =
1771135849 0.999 479 0x4021ec0222fbff4ff38715e0a58529d50b8c54a478b93b3d34f4c3a35b696f73 =
1771135857 0.999 71.25 0x2ab0e23ed318bc79e8e7ecf20aacc58a6298985b68809297656eb7daf82624c1 =
1771135863 0.999 5.43 0x2499e316c0b6de38d2d0f87cb471ca3d61401c612e47df44a7ac84d3929c5f20 =
1771136045 0.999 20 0x5ca4f0d93c730b71ee62892ee38c80ae7dd47dcc5d9e52588ff4e008229d9f0a =
1771136045 0.999 131 0x9b13750b168761ae47d24a67d0c9e02e380b4f1d77f0dd7cc181d143f7e71db2 =
1771136053 0.999 71.25 0x2955d594ad77e2c5f18168d8487306f94959010484bb092eb6f90b1c7c70c2a6 =
1771136203 0.997 5 0x63bdb3672b131c2004654eb77cfe95ac5d8d10d3740d0031c56288212f835ede =
1771136203 0.997 5 0x7b0f0e407ef4c5020bc9de94cf35cef3e3ec1df47c5a9a906321d1c486f98fb7 =
1771136741 0.998 5 0xbc19eefc979179beb07f2e629aa0f23b83b90d7e3249d19690d879f1b270d3e3 =
1771136907 0.999 15 0xca3f1a4702d777418344ce3f1a443795d9fdef5ed0b468d2b9fc4f26bf1ac7a0 =
1771137995 0.999 263 0x0c6b2adc84ffa1f072b776e7a11ffa025f2dd581293413d0182a9461c42a0dd6 =
1771137995 0.999 1.28 0x64e6c799742d3cd99def16131e3e25e1dc82bbcad6a297ec35ed9ca27c98e488 =
1771137995 0.999 35 0xf2c2782ecb3b5f4c0c8128719a4aaf80776ca842787ce5925509b4aed6cf59a8 =
1771138003 0.999 6.36 0x3d1ad7d9a5c29057e968841829c8f81be4e1250dd114c0d56a97f568c4b44a51 =
1771138387 0.999 10 0x43eb3510bd91024975d0acaa1fc0d6798cbb9912d2c5d28885eeefbac2cdb53b =
1771138387 0.999 10 0xabdbce24d027856c03a2a0b3ac25ab14e4179e22a9eb8aca638672e7e787079c =
1771148817 0.997 134 0x9011921b64da239ad8361f46cc8dc289d8dd8b9c2d6320e881881131c3e38368 =
1771153219 0.998 20 0xe486c9347c15aa710c7fd9bb39862f4c24bbbfa0d87c0db48ef6262fc4c6a137 =
1771153227 0.998 31 0xde91a41e0f2fff67f33664c6cd0d32b79a44f82625a4eeb3d8bed33e49780aea =
1771155109 0.998 10 0x68456adbee4cd3106a718cc271cb835304f801a58a007727c92de819681dd6cc =
1771155109 0.998 10 0x7dd408405729fc00d34b05b6b180e4e523a622b79b9a4dc34cf01778b26397ae =
1771155109 0.998 20.1 0xd16894e78ffdb7b232753760e6cae12861ad4fdfa41eecbfd755afc0900675da =
1771157435 0.9989915399 1052 0xd3280e9924e0253cb7530f1c3e7323ddc10afc0b3f0e5f6d6043e7f4f3131c72 =
1771157839 0.998 12.5 0x88423cf6dddcb229c059d66491985e4d3fbf954523d450eed67a06d10e500c55 =
1771160815 0.999 489 0x95a584a0dfad7ba73157567e8d4021dd3b21c939926845651ae9754cb09a2edc =
1771160817 0.999 15 0x1faf52c00573704760a1f7b114105d6da659f1fbf88e680c9542065041eed6c4 =
1771160825 0.999 57 0x9df240da52093ef3752106520285b39dd377c17d529f47a40a925e5f41f70e56 =
1771161779 0.999 15 0xad60ebdd3379cfed9c4b0379db0e44a93375c29f010aa8f94691debbbc7aa909 =
1771161937 0.999 15.51 0x236a86b5d087dfdefb1f7c6271cd5178d1cb46f0a410fe56546c0c63afc226e9 =
1771161937 0.999 14.49 0x7a0f57bc63882aa44f8a20c9bb3a6ea3761f18e0b6c13413dcc9f152d783b83e =
1771165497 0.999 40 0xf4fc0dcf8c64726af03f87fe59d84891a6983d00789745c3c493c25a67a18fc9 =
1771165763 0.999 20 0x55e420bdb397fbdaa898d7fec27c18320872ed137316c042e9429a6eb7d9cd7b =
1771165763 0.999 13.7 0xbcd4315211e55393ddeb2a1b0cf28fdad5ebdb352614bf5b86d40fe0c9b62061 =
1771165777 0.999 20 0x9c83d6df198784082a1be76ca81fe7473b0c2195f72b14f97dee99bca895420c =
1771165777 0.999 26 0xa1d481714353353f1daa31542ab6b071bc47c53ab0e9133c82a7663336d8cbc5 =
1771165781 0.999 14 0x694429818e3655ee341fd91fbd71b9a7716276831be34e1284bdd67fd945cf16 =
1771166201 0.999 20 0x80c654bfb440ef7b8c4c57f2d6c7359fa49c0fc88dd507bf27b58613f8e91949 =
1771166483 0.999 7.5 0x6d015736011682119c2135ccf57b71ee69b34d413129d815965fb74c0fac458c =
1771166865 0.999 7.18 0x96baceab96b972c7cd4d0e385fab3b546eab215754a1a8e951b900ad41226414 =
1771167003 0.999 227 0x196d7c4c1234e347592d4dc31ee9a257ed641d808e66f87e1be5ca9f0a9d8cef =
1771167003 0.999 20 0x4c8b98fe982558c7c35345a85fe27ea898b5f0e0433516d9e22e257aed65191a =
1771167005 0.999 15 0x2009e26090216f387b8f2848213ac3f01fb32c17fac970fcf8cbdb3e4aac33d9 =
1771167025 0.999 40 0x3628da26e290bf7cd651b3b50696ac22e8849f6f7eb9f151744affba0a149df8 =
1771167025 0.999 30 0x77b502df6f270e383504dd5b84643b784ac9454494206bcf98123c85f0d37c3a =
1771167333 0.999 65.52 0x92c56d517e20fdffd393102c0678caf313408520ebb00def9273e448c0a4f677 =
1771167409 0.999 10 0x2e6138a9de1984ec6fafb1a26edde29147d0c424ba8dc988bf71fb06bf8b0f5a =
"""#
}
