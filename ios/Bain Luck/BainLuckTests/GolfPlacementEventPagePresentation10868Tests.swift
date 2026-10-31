import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the golf TOP-10 PLACEMENT final page (route `golf-top10`): the
/// hero over the shared field headline, the one-golfer recorded history anchor
/// with its readout, the expectations map (each priced original's own dated
/// pre-event chance on one 0–100% scale inside the result band its own
/// admitted result names), two independent held golfer selections, the finite
/// first-name chooser, the originals' Details and rules, and the once-only
/// holds. Design corrections L1 (a dense dot chooses itself: the uniquely
/// closest drawn centre) and L2 (annotated marks name their golfer beside the
/// figure, measured and stacked without overlap) are covered below.
///
/// PREPARED, NOT RUN. Only `xcrun swiftc -parse` was run on this file.
///
/// RETAINED DATA (evidence only, never an app binding): `placementEvidence.json`
/// (sha256 1c05c9b027e7addae8bdba469b7dc41a14863671ccdf05a47830e3f822df5b89)
/// under the approved `totals-final-forecast-binding-20261024/prototype/src/`.
/// `retainedEvidence` below is a field subset of it, generated mechanically and
/// unaltered: the event fields (id, name, baseline cutoff, exact-start flag,
/// actual capture time, default key, aliases, history and baseline policies)
/// and, per row in source order, key, name, source, result, score, round count,
/// map offset, the baseline [value, volume, t, at], every history point
/// [t, value, volume, segment, phase, at], the verbatim rules, the final
/// record's id, market id, settlement probability, winner flag, source, market
/// and outcome names, resolution source and observation time, the venue's last
/// price (Kalshi), and the earlier raw record's id, probability, category and
/// observation time where one is retained. Nothing is invented.
///
/// The OWNER's words, figures, bands, counts, offsets' band spans, compact
/// names, groups, pages, suggestions and reader order are simulated here from
/// that evidence (the reference's own label, ceiling, suggestion and paging
/// rules, ported test-side only): the presentation only follows them.
///
/// NOT claimed: native compilation or execution, rendered appearance, matched
/// 375×667 / 393×852 / wide / XXXL / AX3 visual acceptance, focus, Back, touch,
/// scrubbing, VoiceOver on a device, mounted app bindings, genuine pre-event or
/// live phase evidence, or TestFlight. The before/during checks isolate the
/// hero and the map only — the history and readouts stay final-archive input —
/// and the history fixture carries no time-axis labels. The hosted
/// measurements below are prepared checks of sizes and that laying out calls
/// nothing; none has run. Tap checks call the leaf's own `choice` helper — the
/// one its tap handler calls — never a parallel test path.
@MainActor
final class GolfPlacementEventPagePresentation10868Tests: XCTestCase {
    typealias Model = GolfPlacementEventPageModel10868
    typealias Page = GolfPlacementEventPagePresentation10868
    typealias Input = GolfPlacementEventPageInput10868
    typealias Map = GolfPlacementMapPresentation10868
    typealias Geometry = GolfPlacementMapGeometry10868
    typealias Ref = FieldChooserOriginalRef10868
    typealias Role = GolfPlacementChooserRole10868
    typealias Details = OriginalMarketDetails9483
    typealias Target = GolfPreTournamentChooserTarget10868
    typealias Row = Evidence.Row

    // MARK: Retained evidence

    struct Evidence: Decodable {
        struct Event: Decodable {
            let eventID: String
            let name: String
            let baselineCutoff: String
            let exactStartAvailable: Bool
            let actualCapturedAt: String
            let defaultKey: String
            let aliases: [String: String]
            let historyPolicy: String
            let baselinePolicy: String
        }

        struct Baseline: Decodable {
            let value: Double
            let volume: Double
            let t: Int
            let at: String

            init(from decoder: Decoder) throws {
                var c = try decoder.unkeyedContainer()
                value = try c.decode(Double.self)
                volume = try c.decode(Double.self)
                t = try c.decode(Int.self)
                at = try c.decode(String.self)
            }
        }

        struct Point: Decodable {
            let t: Int
            let value: Double
            let volume: Double
            let segment: Int
            let phase: String
            let at: String

            init(from decoder: Decoder) throws {
                var c = try decoder.unkeyedContainer()
                t = try c.decode(Int.self)
                value = try c.decode(Double.self)
                volume = try c.decode(Double.self)
                segment = try c.decode(Int.self)
                phase = try c.decode(String.self)
                at = try c.decode(String.self)
            }
        }

        /// A venue id as retained: a string (Kalshi) or a number (Polymarket).
        struct Identifier: Decodable, Equatable {
            let text: String
            let isNumber: Bool

            init(from decoder: Decoder) throws {
                let c = try decoder.singleValueContainer()
                if let number = try? c.decode(Int.self) {
                    text = String(number)
                    isNumber = true
                } else {
                    text = try c.decode(String.self)
                    isNumber = false
                }
            }
        }

        struct Final: Decodable {
            let id: Identifier
            let _market_id: Identifier
            let probability: Double?
            let is_winner: Bool
            let source: String
            let market_name: String
            let outcome_name: String
            let resolution_source: String
            let observed_at: String?
        }

        /// The earlier raw record retained beside three originals.
        struct Earlier: Decodable {
            let id: Int
            let probability: Double?
            let category: String
            let observed_at: String?
        }

        struct Row: Decodable {
            let key: String
            let name: String
            let source: String
            let result: Bool
            let score: String?
            let roundCount: Int
            let mapY: Double?
            let baseline: Baseline?
            let history: [Point]
            let rules: String
            let final: Final
            let lastPrice: String?
            let original: Earlier?
        }

        let event: Event
        let rows: [Row]
    }

    static let evidence: Evidence = {
        // swiftlint:disable:next force_try
        try! JSONDecoder().decode(Evidence.self, from: Data(retainedEvidence.utf8))
    }()

    static var rows: [Row] { evidence.rows }

    static func named(_ name: String, source: String = "kalshi") -> Row {
        rows.first { $0.name == name && $0.source == source }!
    }

    static var defaultRow: Row { rows.first { $0.key == evidence.event.defaultKey }! }

    /// The cutoff's own epoch, read from the retained baseline at the cutoff (evidence only).
    static let cutoffEpoch = 1791417600

    // MARK: Owner simulation (test-side only)

    static let scope = "golf-top10:final"
    static let streamScope = "golf-top10:stories"
    static let mapCard = StoryStreamPresentation10868.CardRef(scope: streamScope, id: "expectations")

    static func ref(_ row: Row) -> Ref {
        Ref(scope: scope, source: row.final.source, marketID: row.final._market_id.text, outcomeID: row.final.id.text)
    }

    static var defaultRef: Ref { ref(defaultRow) }

    static func row(_ ref: Ref) -> Row? {
        rows.first { self.ref($0) == ref }
    }

    /// The reference's archived-quote label, ported for the fixture only.
    static func percent(_ value: Double) -> String {
        guard value.isFinite, value >= 0, value <= 1 else { return "Unavailable" }
        if value == 0 { return "0%" }
        if value == 1 { return "100%" }
        let tenths = (value * 1000).rounded()
        if tenths == 0 { return "<0.1%" }
        if tenths == 1000 { return ">99.9%" }
        let figure = tenths / 10
        return figure == figure.rounded() ? "\(Int(figure))%" : "\(figure)%"
    }

    static func sourceName(_ row: Row) -> String {
        switch row.source {
        case "kalshi": return "Kalshi"
        case "polymarket": return "Polymarket"
        default: return row.source
        }
    }

    static let chanceLabel = "Pre-event · top 10"
    static let noBaseline = "No qualifying pre-event trade captured"
    static let resultTitle = "Final result · includes ties"
    static let unavailable = "Golfer unavailable in this update"
    static let captured = "Final classification · captured 2026-10-12T08:22:55.276141+00:00"

    static func provenance(_ row: Row, _ baseline: Evidence.Baseline) -> String {
        "\(sourceName(row)) hour-ending trade · \(baseline.at) · before opening day"
    }

    static func chance(_ row: Row) -> FieldChooserReading10868 {
        guard let baseline = row.baseline else {
            return FieldChooserReading10868(label: chanceLabel, value: .missing(noBaseline))
        }
        return FieldChooserReading10868(label: chanceLabel,
                                        value: .recorded(text: percent(baseline.value), detail: provenance(row, baseline)))
    }

    static func resultWords(_ row: Row) -> String {
        row.result ? "Made top 10" : "Missed top 10"
    }

    static func result(_ row: Row) -> FieldChooserResult10868 {
        FieldChooserResult10868(title: resultTitle, words: resultWords(row))
    }

    static var frame: (start: Int, end: Int) {
        let times = rows.flatMap { $0.history.map(\.t) }
        return (times.min()!, times.max()!)
    }

    static func original(_ row: Row) -> FieldChooserOriginal10868 {
        let segments = Dictionary(grouping: row.history, by: \.segment).sorted { $0.key < $1.key }.map { entry in
            entry.value.map { FieldChooserPoint10868(time: Double($0.t), probability: $0.value) }
        }
        return FieldChooserOriginal10868(
            ref: ref(row), name: row.name, plan: .single(chance(row)),
            preview: FieldChooserPreview10868(
                history: row.history.isEmpty ? nil
                    : FieldChooserHistory10868(segments: segments, emphasis: nil, beforeReference: nil, gaps: []),
                absence: "No recorded history"),
            movement: nil, clock: nil, result: result(row),
            browseStatus: row.history.isEmpty ? "No recorded history" : "Recorded history available")
    }

    /// The reference's score words, ported for the fixture only.
    static func scoreWords(_ score: String) -> String {
        score == "E" ? "Even" : score.replacingOccurrences(of: "-", with: "−")
    }

    static func report(_ row: Row) -> GolfPlacementReport10868 {
        GolfPlacementReport10868(
            ref: ref(row),
            score: row.score.map {
                FieldChooserReading10868(label: "Reported score", value: .recorded(text: scoreWords($0), detail: captured))
            } ?? FieldChooserReading10868(label: "Reported score", value: .missing("Score not reported")),
            rounds: row.roundCount > 0 ? "\(row.roundCount) rounds reported" : nil)
    }

    /// The reference's known order: priced rows by pre-event chance, highest
    /// first, ties in source order (a stable sort).
    static var known: [Row] {
        rows.enumerated().filter { $0.element.baseline != nil }.sorted { a, b in
            let x = a.element.baseline!.value
            let y = b.element.baseline!.value
            return x > y || (x == y && a.offset < b.offset)
        }.map(\.element)
    }

    static let madeResult = FieldChooserResult10868(title: resultTitle, words: "Made top 10")
    static let missedResult = FieldChooserResult10868(title: resultTitle, words: "Missed top 10")

    static var mapBands: [GolfPlacementMapBand10868] {
        let made = known.filter(\.result).count
        return [
            GolfPlacementMapBand10868(id: "made", label: "Made top 10", count: "\(made) priced golfers",
                                      result: madeResult, lower: 5, upper: 10),
            GolfPlacementMapBand10868(id: "missed", label: "Missed top 10", count: "\(known.count - made) priced golfers",
                                      result: missedResult, lower: 0, upper: 5),
        ]
    }

    /// The owner's compact annotation name: the last word of the whole name (test-side only).
    static func compactName(_ row: Row) -> String {
        row.name.split(separator: " ").last.map(String.init) ?? row.name
    }

    static func point(_ row: Row, label: String? = nil) -> GolfPlacementMapPoint10868 {
        GolfPlacementMapPoint10868(
            chance: FieldOutlookBeforeChance10868(ref: ref(row), probability: row.baseline!.value, reading: chance(row)),
            band: row.result ? "made" : "missed", offset: row.mapY!, labelled: row.result,
            label: label ?? compactName(row))
    }

    static let ticks = [0, 0.25, 0.5, 0.75, 1].map { FieldOutlookTick10868(probability: $0, label: percent($0)) }

    static let unplaced = "This prop stays available, but has no recorded pre-event probability to place on the map."
    static let withheld = "Final results are not available in this view."

    static let mapCopy = GolfPlacementMapCopy10868(
        eyebrow: "Expectations, graded · top 10 including ties", title: "Which chances held up?",
        caption: "Each circle is a golfer's pre-event chance. The two bands show the final result.",
        graphicLabel: "Fourteen pre-event top-10 chances on a zero to one hundred percent scale: two made the top 10, twelve missed. Vertical offsets only separate overlapping marks.",
        axis: "Pre-event top-10 chance → · choose a golfer to highlight",
        unplaced: unplaced, withheld: withheld,
        note: "14 of 132 Kalshi golfers have captured pre-event trades. All 132 plus 13 retained Polymarket props remain available. Independent top-10 chances do not add to 100%.",
        previousLabel: "Previous", nextLabel: "Next", chooseHint: "Highlights this golfer on the map")

    static func mapInput(selected: Ref?, phase: FieldOutlookPhase10868 = .final,
                         points: [GolfPlacementMapPoint10868]? = nil, bands: [GolfPlacementMapBand10868]? = nil,
                         traversal: [Ref]? = nil) -> GolfPlacementMapInput10868 {
        GolfPlacementMapInput10868(phase: phase, bands: bands ?? mapBands, points: points ?? known.map { point($0) },
                                   ticks: ticks, selected: selected, traversal: traversal ?? known.map { ref($0) },
                                   copy: mapCopy)
    }

    /// The reference's zero-anchored closer ceiling, ported for the fixture only.
    static func ceiling(_ values: [Double]) -> Double {
        let valid = values.filter { $0.isFinite && $0 >= 0 && $0 <= 1 }
        guard let top = valid.max() else { return 1 }
        let target = min(1, max(0.005, top * 1.02))
        return [0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 0.75, 1].first { $0 >= target } ?? 1
    }

    static func runs(_ row: Row) -> [FieldHistoryRun10868] {
        var runs: [FieldHistoryRun10868] = []
        var current: [FieldHistoryPoint10868] = []
        var segment: Int?
        for point in row.history {
            if let open = segment, open != point.segment {
                runs.append(FieldHistoryRun10868(id: "\(row.key)#\(open)", points: current))
                current = []
            }
            segment = point.segment
            current.append(FieldHistoryPoint10868(id: "\(row.key)@\(point.t)", x: Double(point.t), probability: point.value,
                                                  style: point.phase == "before" ? .hollow : .filled))
        }
        if let open = segment, !current.isEmpty {
            runs.append(FieldHistoryRun10868(id: "\(row.key)#\(open)", points: current))
        }
        return runs
    }

    static func history(_ row: Row, full: Bool = false, inspection: FieldHistoryInspection10868? = nil,
                        plotHeight: CGFloat = 200) -> FieldHistoryInput10868 {
        let top = full ? 1 : ceiling(row.history.map(\.value) + (row.baseline.map { [$0.value] } ?? []))
        let series = FieldHistorySeries10868(
            id: row.key, name: row.name, shape: FieldHistoryShape10868.circle, tint: DS.blue, runs: runs(row),
            links: [], labelPointID: nil,
            before: row.baseline.map {
                FieldHistoryReading10868.independent(figure: percent($0.value), provenance: provenance(row, $0))
            } ?? FieldHistoryReading10868.absent(words: noBaseline),
            recorded: .absent(words: "No trade inspected"),
            absentWords: "Recorded trade history unavailable", choose: nil)
        return FieldHistoryInput10868(
            title: "The top-10 journey", caption: "\(row.name) · recorded chance · 0–\(percent(top))", series: [series],
            selection: .series(id: row.key, missingWords: "Golfer unavailable in this history"),
            domain: FieldHistoryDomain10868(lower: Double(frame.start), upper: Double(frame.end)), ceiling: top,
            yTicks: [0, top / 2, top].map { FieldHistoryTick10868(value: $0, lines: [percent($0)]) },
            xTicks: [], guides: [], breaks: [],
            readout: .beforeAndInspected(beforeLabel: chanceLabel, inspectedLabel: "Inspected trade"),
            markKey: FieldHistoryMarkKey10868(hollow: "Before opening day", filled: "Later trades"),
            comparisonExplanation: nil,
            notes: ["Pre-event cutoff: before \(evidence.event.baselineCutoff). Exact first-tee time unavailable. Final results are separate from traded chances.",
                    evidence.event.baselinePolicy, evidence.event.historyPolicy],
            summary: "\(row.name): \(row.history.count) recorded hourly trade closes, not settlement endpoints",
            plotHeight: plotHeight, unboundReadingWords: "Trade not bound", plotUnavailableWords: nil, windows: nil,
            scale: FieldHistoryAction10868(id: "scale", label: full ? "Use closer scale" : "Show 0–100%", spokenLabel: nil, isAvailable: true),
            moreOriginals: nil,
            details: FieldHistoryAction10868(id: "details", label: "Details & timing", spokenLabel: nil, isAvailable: true),
            expand: FieldHistoryAction10868(id: "expand", label: "Expand history", spokenLabel: nil, isAvailable: true),
            inspect: FieldHistoryAction10868(id: "inspect", label: "Inspect trades", spokenLabel: nil, isAvailable: true),
            previous: nil, next: nil, inspection: inspection)
    }

    static let headlineUnavailable = "The final result is not available for this view."

    static func headline(_ catalogue: [FieldChooserOriginal10868], subject row: Row,
                         phase: FieldOutlookPhase10868) -> FieldHeadlineInput10868 {
        FieldHeadlineInput10868(
            scope: scope, catalogue: catalogue,
            displayed: [FieldHeadlineSlot10868(ref: ref(row), name: row.name, compactName: nil)],
            pairs: [FieldMovementPair10868(ref: ref(row),
                                           before: row.baseline.map { FieldMovementObservation10868(probability: $0.value, reading: chance(row)) },
                                           later: nil, movement: nil, observation: nil)],
            finishes: [FieldFinishPlace10868(ref: ref(row), reading: FieldChooserReading10868(
                label: resultTitle, value: .recorded(text: resultWords(row), detail: "\(sourceName(row)) contract result")))],
            state: FieldHeadlineState10868(
                figure: "Final", unit: nil, caption: "Who made the top 10?",
                detail: "The chance before play. The result after four rounds.",
                spoken: "Final. Who made the top 10? The chance before play. The result after four rounds.", progress: nil),
            phase: phase,
            copy: FieldHeadlineCopy10868(
                eyebrow: "DP World Tour · final · Oct 8–11", title: evidence.event.name,
                graphicLabel: "Pre-event top-10 chance and final result", beforeLabel: chanceLabel, recordedLabel: "Recorded",
                beforeUnavailable: "Not recorded", recordedUnavailable: "No recent probability",
                finishLabel: resultTitle, finishUnavailable: "Result not reported", empty: "No golfer in this view",
                aboutLabel: "About these results", aboutHint: "Opens what these records mean",
                openHint: "Opens this golfer's history"),
            unavailableWords: unavailable)
    }

    // MARK: Chooser hierarchy (the archive chooser's rules, test-side only)

    static let bands = ["A–C", "D–G", "H–L", "M–P", "Q–S", "T–Z"]

    static func normalized(_ name: String) -> String {
        name.folding(options: .diacriticInsensitive, locale: Locale(identifier: "en_US_POSIX"))
            .trimmingCharacters(in: .whitespaces).uppercased()
    }

    static func band(_ name: String) -> String {
        let c = normalized(name).first ?? "A"
        if c <= "C" { return "A–C" }
        if c <= "G" { return "D–G" }
        if c <= "L" { return "H–L" }
        if c <= "P" { return "M–P" }
        if c <= "S" { return "Q–S" }
        return "T–Z"
    }

    /// One band's originals in the owner's first-name order, both sources kept apart.
    static func members(_ band: String) -> [Row] {
        rows.filter { self.band($0.name) == band }.sorted {
            (normalized($0.name), $0.source, $0.key) < (normalized($1.name), $1.source, $1.key)
        }
    }

    static func pages(_ band: String) -> [[Row]] {
        let members = self.members(band)
        return stride(from: 0, to: members.count, by: 6).map { Array(members[$0..<min($0 + 6, members.count)]) }
    }

    static func groupID(_ band: String, _ page: Int) -> String { "\(band)|\(page)" }

    /// The reference's three placement suggestions: the highest chance, the
    /// highest that missed, the lowest that made, then the highest others.
    static var suggestions: [Row] {
        let high = known
        let lowestMade = high.filter(\.result).sorted {
            ($0.baseline!.value, $0.key) < ($1.baseline!.value, $1.key)
        }.first
        let candidates: [Row?] = [high.first, high.first { !$0.result }, lowestMade] + high.map { Optional($0) }
        var picks: [Row] = []
        for case let row? in candidates where !picks.contains(where: { $0.key == row.key }) {
            picks.append(row)
            if picks.count == 3 { break }
        }
        return picks
    }

    static func groups() -> [FieldChooserGroup10868] {
        var groups = [FieldChooserGroup10868(id: "suggested", label: "Suggested", countText: nil,
                                             refs: suggestions.map { ref($0) })]
        for band in bands {
            for (index, page) in pages(band).enumerated() {
                groups.append(FieldChooserGroup10868(id: groupID(band, index), label: "\(band) · \(index + 1)", countText: nil,
                                                     refs: page.map { ref($0) }))
            }
        }
        return groups
    }

    static func navigation(_ groupID: String, held: Row) -> GolfPreTournamentChooserNavigation10868 {
        let parts = groupID.split(separator: "|").map(String.init)
        let all = parts.count == 2
        let current = all ? parts[0] : band(held.name)
        let page = all ? Int(parts[1])! : 0
        let count = members(current).count
        let pageCount = pages(current).count
        return GolfPreTournamentChooserNavigation10868(
            modesLabel: "Golfer choices",
            modes: [Target(label: "Suggested", groupID: "suggested", isSelected: !all),
                    Target(label: "All \(rows.count)", groupID: self.groupID(current, 0), isSelected: all)],
            context: all ? "A–Z by first name" : "Starting chances, final results",
            bandsLabel: "First-name groups",
            bands: all ? bands.map { Target(label: $0, countText: "\(members($0).count)", groupID: self.groupID($0, 0),
                                            isSelected: $0 == current) } : [],
            page: all ? "\(page * 6 + 1)–\(min(count, page * 6 + 6)) of \(count) · \(current)" : nil,
            previous: all && page > 0 ? Target(label: "Previous", spokenLabel: "Previous golfers", groupID: self.groupID(current, page - 1)) : nil,
            next: all && page + 1 < pageCount ? Target(label: "Next", spokenLabel: "Next golfers", groupID: self.groupID(current, page + 1)) : nil)
    }

    static func chooser(_ catalogue: [FieldChooserOriginal10868], selected: Ref?, groupID: String) -> GolfWinnerArchiveChooser10868 {
        GolfWinnerArchiveChooser10868(
            chooser: FieldChooserInput10868(
                scope: scope, intro: nil,
                featured: FieldChooserFeatured10868(title: "Suggested", badge: nil, refs: suggestions.map { ref($0) },
                                                    emptyWords: "No suggestions"),
                context: nil, more: nil,
                browse: FieldChooserBrowse10868(
                    id: "browse", title: "All \(rows.count)", expanded: true, note: "A–Z by first name",
                    groupsLabel: "First-name pages", groups: groups(), selectedGroupID: groupID,
                    noGroupWords: "Choose a group", groupUnavailableWords: "Group unavailable",
                    emptyGroupWords: "No golfers in this group"),
                catalogue: catalogue,
                frame: FieldChooserFrame10868(start: Double(frame.start), end: Double(frame.end), ceiling: 1,
                                              key: "Captured history · same time and 0–100% scale",
                                              referenceKey: nil, scale: "0–100%", provenance: "Hourly trade closes"),
                selected: selected.map { FieldChooserSelected10868(ref: $0, words: "In view", unavailableWords: "Golfer unavailable") },
                unavailableWords: unavailable, chooseHint: "Shows this golfer"),
            navigation: navigation(groupID, held: selected.flatMap { row($0) } ?? defaultRow))
    }

    static let readoutCopy = GolfPlacementReadoutCopy10868(
        resultLabel: resultTitle, resultUnavailable: "Result not reported", scoreLabel: "Reported score",
        scoreUnavailable: "Score not reported", roundsUnavailable: "Round count not reported",
        detailsLabel: "Details & timing", detailsHint: "Opens this golfer's original and rules",
        unavailableWords: unavailable)

    static let about = FieldEventPageAbout10868(title: "About these results", paragraphs: [
        "Pre-event chances are hourly trade closes before the opening calendar day; final results are reported separately.",
        "Independent top-10 chances are not normalized and do not add to 100%.",
    ])

    static func input(_ catalogueRows: [Row]? = nil,
                      historyRow: Row? = nil,
                      historySelection: Ref? = GolfPlacementEventPagePresentation10868Tests.defaultRef,
                      mapSelected: Ref? = GolfPlacementEventPagePresentation10868Tests.defaultRef,
                      historyGroup: String = "suggested", mapGroup: String = "suggested",
                      headlinePhase: FieldOutlookPhase10868 = .final, mapPhase: FieldOutlookPhase10868 = .final,
                      points: [GolfPlacementMapPoint10868]? = nil, mapBands: [GolfPlacementMapBand10868]? = nil,
                      traversal: [Ref]? = nil, reportRows: [Row]? = nil,
                      full: Bool = false, inspection: FieldHistoryInspection10868? = nil,
                      readerPlotHeight: CGFloat? = 320, stories: [GolfPlacementStory10868]? = nil) -> Input {
        let catalogue = (catalogueRows ?? rows).map { original($0) }
        let subject = historyRow ?? defaultRow
        return Input(
            copy: GolfPlacementCopy10868(
                headlineUnavailable: headlineUnavailable, storiesLabel: "Tournament stories",
                storyUnavailable: "This story is not available in this order.", allPropsLabel: "All \(rows.count) original props",
                historyEntry: GolfWinnerArchiveChooserEntryCopy10868(caption: "Golfer in history", action: "Change", hint: "Opens the golfer chooser"),
                mapEntry: GolfWinnerArchiveChooserEntryCopy10868(caption: "Golfer on the map", action: "Change", hint: "Opens the golfer chooser")),
            reader: FieldEventPageReaderHeader10868(title: evidence.event.name, state: "Final archive"),
            scope: scope, catalogue: catalogue,
            headline: headline(catalogue, subject: subject, phase: headlinePhase),
            history: history(subject, full: full, inspection: inspection),
            historySelection: historySelection,
            reports: (reportRows ?? rows).map { report($0) },
            map: mapInput(selected: mapSelected, phase: mapPhase, points: points, bands: mapBands, traversal: traversal),
            readout: readoutCopy,
            historyChooser: chooser(catalogue, selected: historySelection, groupID: historyGroup),
            mapChooser: chooser(catalogue, selected: mapSelected, groupID: mapGroup),
            stream: StoryStreamPresentation10868(scope: streamScope, heading: "Stories",
                                                 cards: [StoryStreamPresentation10868.Card(id: "expectations", name: "Which chances held up?")],
                                                 primary: mapCard),
            stories: stories ?? [GolfPlacementStory10868(cardID: "expectations", card: .map)],
            about: about, readerPlotHeight: readerPlotHeight)
    }

    static let marketScope = "golf-top10:originals"

    static func identity(_ row: Row) -> Details.Identity {
        Details.Identity(source: row.final.source, market: row.final.id.text, side: "yes")
    }

    static func originals(selection: Row?) -> FieldEventPageOriginals10868 {
        let catalogue = Details.Catalogue(scope: marketScope, originals: rows.map { row in
            Details.Original(
                identity: identity(row), title: row.final.market_name, outcome: row.final.outcome_name, mode: .result,
                pregame: row.baseline.map {
                    Details.Reading.value(percent($0.value), placement: $0.value, provenance: provenance(row, $0))
                } ?? Details.Reading.missing(noBaseline),
                later: nil,
                grade: Details.Grade(words: row.final.is_winner ? "Resolved Yes" : "Resolved No",
                                     provenance: row.final.observed_at.map { "Settled · \($0)" }),
                about: Details.About(source: sourceName(row), rules: .verified([row.rules]),
                                     provenance: [LadderOriginalProbabilityDetails9483.Row(label: "Contract", value: row.final.id.text)],
                                     historicalQuote: nil),
                beforeLabel: chanceLabel)
        })
        return FieldEventPageOriginals10868(
            catalogue: catalogue,
            selection: selection.map { Details.Selection(scope: marketScope, identity: identity($0)) },
            heading: "All props", emptyWords: "No originals", unavailableChoice: "Original unavailable", tint: DS.blue)
    }

    /// Every callback and the hook, recorded in call order.
    final class Log {
        var events: [String] = []
    }

    static func page(_ input: Input, _ mode: GolfPlacementEventPageMode10868 = .page, log: Log,
                     hook: Bool = true, originals: FieldEventPageOriginals10868? = nil) -> Page {
        Page(input: input, mode: mode, originals: originals,
             onAbout: { log.events.append("about") },
             onHeadlineOpen: { log.events.append("open:\($0.ref.outcomeID):\($0.observation ?? "-")") },
             onHistoryAction: { log.events.append("history:\($0)") },
             onHistoryInspectionChoice: { log.events.append("inspect:\($0)") },
             onHistoryPlotPosition: { log.events.append("plot:\($0)") },
             onOpenChooser: { log.events.append("chooser:\($0.rawValue)") },
             onChoose: { log.events.append("choose:\($0.role.rawValue):\($0.ref.outcomeID)") },
             onChooserControl: { log.events.append("control:\($0.role.rawValue):\($0.control)") },
             onOpenOriginal: { log.events.append("details:\($0.outcomeID)") },
             onStoryIntent: { log.events.append("story:\($0)") },
             onAllProps: { log.events.append("allProps") },
             onOriginalSelect: { log.events.append("select:\($0.identity.market)") },
             onOriginalHistory: { log.events.append("originalHistory:\($0.actionID)") },
             onInteraction: hook ? { log.events.append("hold") } : nil)
    }

    static func activation(_ log: Log) -> StoryStreamCardActivation10868 {
        StoryStreamCardActivation10868(card: mapCard,
                                       intents: [.interaction(scope: streamScope, card: mapCard)],
                                       send: { log.events.append("stream:\($0)") })
    }

    static var interaction: String {
        "stream:\(StoryStreamPresentation10868.Intent.interaction(scope: streamScope, card: mapCard))"
    }

    // MARK: Reachable words

    static func words(_ endpoint: FieldMovementEndpoint10868) -> [String] {
        switch endpoint {
        case .reading(let reading): GolfWinnerArchiveEventPageModel10868.words(reading)
        case .unavailable(let label, let words): [label, words]
        }
    }

    /// Every word the page body reaches: the mounted headline or its words,
    /// the history readout and every word or VoiceOver label of the map card.
    static func reachable(_ page: Page) -> [String] {
        var words: [String] = []
        if let headline = page.headlineContent() {
            let model = FieldHeadlineModel10868(headline.input)
            words += [model.eyebrow, model.title].compactMap { $0 }
            for competitor in model.competitors {
                words.append(competitor.slot.name)
                words += competitor.metrics.flatMap { self.words($0) }
            }
            if let state = model.state { words += [state.figure, state.unit, state.caption, state.detail].compactMap { $0 } }
        } else {
            words.append(page.input.copy.headlineUnavailable)
        }
        switch page.model.readout(role: .history) {
        case .shown(let readout): words += Model.words(readout)
        case .unavailable(let notice): words.append(notice)
        case .notHeld: break
        }
        words += page.mapWords(at: .stream(activation(Log())))
        return words
    }

    /// Whole-token mention: never a substring of a longer word or figure.
    static func mentions(_ words: [String], _ token: String) -> Bool {
        let pattern = "(?<![\\p{L}\\p{N}])" + NSRegularExpression.escapedPattern(for: token) + "(?![\\p{L}\\p{N}])"
        return words.contains { $0.range(of: pattern, options: .regularExpression) != nil }
    }

    /// A payload may name only a catalogue original, and an observation key
    /// only when it names a drawn point of the shown history.
    static func violations(_ opens: [FieldMovementOpen10868], history: FieldHistoryInput10868, refs: Set<Ref>) -> [String] {
        let points = Set(history.series.flatMap { $0.runs.flatMap(\.points) }.map(\.id))
        return opens.compactMap { open in
            guard refs.contains(open.ref) else { return "foreign \(open.ref.outcomeID)" }
            guard let key = open.observation else { return nil }
            return points.contains(key) ? nil : "unbound \(key)"
        }
    }

    /// The marks' centres in one band's strip of `size`, by the leaf's own geometry.
    static func centres(_ map: GolfPlacementMapModel10868, band: Int, strip: CGSize,
                        radius: CGFloat = 9) -> [GolfPlacementMapPlacedMark10868] {
        Geometry.placed(map.marks(inBand: band), in: Geometry.markArea(CGRect(origin: .zero, size: strip), radius: radius))
    }

    static func distance(_ a: CGPoint, _ b: CGPoint) -> CGFloat {
        let dx = a.x - b.x
        let dy = a.y - b.y
        return (dx * dx + dy * dy).squareRoot()
    }

    struct Unresolved: Error { let name: String }

    static func shown(_ model: Model, _ ref: Ref) throws -> GolfPlacementReadout10868 {
        guard case .shown(let readout) = model.readout(ref) else {
            XCTFail("\(ref.outcomeID) must resolve")
            throw Unresolved(name: ref.outcomeID)
        }
        return readout
    }

    // MARK: Receipt

    func testTheRetainedEvidenceKeepsEveryIdentityRuleResultClockAndPoint() {
        let event = Self.evidence.event
        XCTAssertEqual(event.eventID, "golf-top10")
        XCTAssertEqual(event.name, "Open de España")
        XCTAssertEqual(event.baselineCutoff, "2026-10-08T00:00:00+00:00")
        XCTAssertFalse(event.exactStartAvailable)
        XCTAssertEqual(event.actualCapturedAt, "2026-10-12T08:22:55.276141+00:00")
        XCTAssertEqual(event.defaultKey, "espana-kalshi:KXDPWTTOP10-OPDEPBM26-LABE")
        XCTAssertEqual(event.aliases, ["Eugenio Lopez-Chacarra": "Eugenio Chacarra", "Ludvig Aberg": "Ludvig Åberg",
                                       "Jayden Schaper": "Jayden Schaper"])
        XCTAssertEqual(event.historyPolicy, "Positive-volume hourly closes only; gaps over two hours stay open; no settlement endpoints.")

        let rows = Self.rows
        XCTAssertEqual(rows.count, 145)
        XCTAssertEqual(rows.filter { $0.source == "kalshi" }.count, 132)
        XCTAssertEqual(rows.filter { $0.source == "polymarket" }.count, 13)
        XCTAssertEqual(Set(rows.map(\.key)).count, 145)
        XCTAssertEqual(Set(rows.map { Self.ref($0) }).count, 145, "every original keeps its own identity")
        XCTAssertEqual(Set(rows.map(\.name)).count, 136)
        XCTAssertEqual(Set(rows.map(\.rules)).count, 133)
        XCTAssertEqual(rows.filter { $0.source == "kalshi" && $0.result }.count, 10)
        XCTAssertEqual(rows.filter { $0.source == "kalshi" && !$0.result }.count, 122)
        XCTAssertEqual(rows.filter { $0.source == "polymarket" && $0.result }.count, 10)
        XCTAssertEqual(rows.filter { $0.source == "polymarket" && !$0.result }.count, 3)

        let priced = rows.filter { $0.baseline != nil }
        XCTAssertEqual(priced.count, 14)
        XCTAssertEqual(priced.filter(\.result).count, 2)
        XCTAssertEqual(priced.filter { !$0.result }.count, 12)
        XCTAssertTrue(priced.allSatisfy { $0.source == "kalshi" })
        let sum = priced.reduce(0) { $0 + $1.baseline!.value }
        XCTAssertGreaterThan(sum, 1, "independent placement chances never add to one")
        XCTAssertEqual(sum, 4.11, accuracy: 1e-9)
        XCTAssertEqual(rows.filter { $0.baseline == nil }.count, 131)
        XCTAssertEqual(rows.reduce(0) { $0 + $1.history.count }, 73)
        XCTAssertEqual(rows.filter { !$0.history.isEmpty }.count, 24)
        XCTAssertEqual(rows.filter { $0.history.isEmpty }.count, 121)
        XCTAssertEqual(rows.filter { !$0.history.isEmpty && $0.baseline == nil }.count, 10)
        XCTAssertEqual(rows.flatMap(\.history).filter { $0.phase == "before" }.count, 19)
        XCTAssertEqual(rows.flatMap(\.history).filter { $0.phase == "later" }.count, 54)
        XCTAssertEqual(rows.filter { $0.score == nil }.count, 21)
        XCTAssertEqual(rows.filter { $0.roundCount == 4 }.count, 70)
        XCTAssertEqual(rows.filter { $0.roundCount == 2 }.count, 54)
        XCTAssertEqual(rows.filter { $0.roundCount == 0 }.count, 21)
        let shared = Dictionary(grouping: rows, by: \.name).filter { $0.value.count > 1 }
        XCTAssertEqual(shared.keys.sorted(), ["Adrian Otaegui", "Ben Schmidt", "Daniel Brown", "Eugenio Lopez-Chacarra",
                                              "Grant Forrest", "Jacob Skov Olesen", "Joel Girrbach", "Oliver Lindell", "Victor Perez"])
        XCTAssertTrue(shared.values.allSatisfy { Set($0.map(\.source)) == ["kalshi", "polymarket"] },
                      "one name, two independent source originals")

        let aberg = Self.defaultRow
        XCTAssertEqual(aberg.name, "Ludvig Aberg")
        XCTAssertEqual(aberg.source, "kalshi")
        XCTAssertEqual(aberg.final.id.text, "KXDPWTTOP10-OPDEPBM26-LABE")
        XCTAssertFalse(aberg.final.id.isNumber)
        XCTAssertEqual(aberg.final._market_id.text, "KXDPWTTOP10-OPDEPBM26")
        XCTAssertEqual(aberg.baseline?.value, 0.53)
        XCTAssertEqual(aberg.baseline?.volume, 45.66)
        XCTAssertEqual(aberg.baseline?.t, 1791417600)
        XCTAssertEqual(aberg.baseline?.at, "2026-10-08T00:00:00+00:00")
        XCTAssertTrue(aberg.result)
        XCTAssertEqual(aberg.score, "-10")
        XCTAssertEqual(aberg.roundCount, 4)
        XCTAssertEqual(aberg.mapY, 7.0)
        XCTAssertEqual(aberg.history.count, 8)
        XCTAssertEqual(aberg.history.first?.value, 0.68)
        XCTAssertEqual(aberg.history.first?.t, 1791392400)
        XCTAssertEqual(aberg.history.last?.value, 0.99)
        XCTAssertEqual(aberg.lastPrice, "0.9900")
        XCTAssertNil(aberg.final.probability, "the venue's own final carries no chance")
        XCTAssertEqual(aberg.final.resolution_source, "venue_finalized")

        let chacarra = Self.named("Eugenio Lopez-Chacarra")
        XCTAssertEqual(chacarra.baseline?.value, 0.33)
        XCTAssertEqual(chacarra.baseline?.volume, 144.94)
        XCTAssertTrue(chacarra.result)
        XCTAssertEqual(chacarra.mapY, 7.0)
        XCTAssertEqual(chacarra.score, "-13")
        let chacarraPM = Self.named("Eugenio Lopez-Chacarra", source: "polymarket")
        XCTAssertNil(chacarraPM.baseline)
        XCTAssertTrue(chacarraPM.history.isEmpty)
        XCTAssertEqual(chacarraPM.final.probability, 1.0)
        XCTAssertTrue(chacarraPM.final.id.isNumber)
        XCTAssertEqual(chacarraPM.final.id.text, "245877574")

        // The three earlier raw Polymarket records read 0 — evidence of a raw
        // field, never a pre-event chance: none of the three has a baseline.
        let earlier = rows.filter { $0.original != nil }
        XCTAssertEqual(earlier.map(\.name), ["Alejandro Rodriguez", "Ben Schmidt", "Daniel Bradbury"])
        for row in earlier {
            XCTAssertEqual(row.original?.probability, 0.0)
            XCTAssertEqual(row.original?.category, "field")
            XCTAssertEqual(row.original?.id, Int(row.final.id.text))
            XCTAssertNil(row.baseline, row.name)
        }

        let kalshiPrefix = "in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\n"
        for row in rows {
            XCTAssertEqual(row.final.is_winner, row.result, row.key)
            XCTAssertEqual(row.final.outcome_name, row.name, row.key)
            XCTAssertEqual(row.final.source, row.source, row.key)
            XCTAssertEqual(row.score == nil, row.roundCount == 0, "a missing score and no reported rounds coincide: \(row.key)")
            XCTAssertEqual(row.mapY != nil, row.baseline != nil, "map offsets exist only for priced rows: \(row.key)")
            switch row.source {
            case "kalshi":
                XCTAssertTrue(row.rules.hasPrefix("If \(row.name) finishes in the top 10 (including ties) \(kalshiPrefix)"), row.key)
                XCTAssertEqual(row.final.market_name, "Open de España · Top 10, including ties")
                XCTAssertEqual(row.final._market_id.text, "KXDPWTTOP10-OPDEPBM26")
                XCTAssertNil(row.final.probability, row.key)
                XCTAssertNil(row.final.observed_at, row.key)
                XCTAssertNotNil(row.lastPrice, row.key)
            default:
                XCTAssertTrue(row.rules.hasPrefix("This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties."), row.key)
                XCTAssertEqual(row.final.market_name, "DP World Tour: Open de Espana Top 10")
                XCTAssertEqual(row.final._market_id.text, "64366411")
                XCTAssertEqual(row.final.probability, row.result ? 1 : 0, "the settlement is a result, never a chance: \(row.key)")
                XCTAssertEqual(row.final.resolution_source, "api_settlement")
                XCTAssertNil(row.baseline, row.key)
                XCTAssertTrue(row.history.isEmpty, row.key)
                XCTAssertNil(row.score, row.key)
            }
            if let baseline = row.baseline {
                XCTAssertTrue(row.history.contains { $0.t == baseline.t && $0.value == baseline.value && $0.phase == "before" }, row.key)
                XCTAssertTrue(baseline.volume > 0 && baseline.value > 0 && baseline.value < 1, row.key)
                // Evidence only: the owner's offsets sit on its result's half of the reference map.
                XCTAssertTrue(row.result ? (5...10).contains(row.mapY!) : (0..<5).contains(row.mapY!), row.key)
            }
            for (a, b) in zip(row.history, row.history.dropFirst()) {
                XCTAssertGreaterThan(b.t, a.t, row.key)
                XCTAssertEqual(a.segment == b.segment, b.t - a.t <= 7200, "segments break exactly at gaps over two hours: \(row.key)")
            }
            for point in row.history {
                XCTAssertTrue(point.value > 0 && point.value < 1 && point.volume > 0, "no settlement endpoint: \(row.key)")
                XCTAssertEqual(point.phase == "before", point.t <= Self.cutoffEpoch, row.key)
            }
        }
    }

    // MARK: Golfers

    func testEveryOriginalHasItsOwnReadoutResultScoreAndBaselineMissingness() throws {
        let model = Model(Self.input())
        var recorded = 0
        var missingScores = 0
        var points = 0
        var made: [String: Int] = [:]
        for row in Self.rows {
            let readout = try Self.shown(model, Self.ref(row))
            XCTAssertEqual(readout.original.name, row.name)
            XCTAssertEqual(readout.original.ref, Self.ref(row))
            XCTAssertEqual(readout.chance, Self.chance(row))
            XCTAssertEqual(readout.resultLabel, "Final result · includes ties")
            XCTAssertEqual(readout.resultWords, row.result ? "Made top 10" : "Missed top 10")
            XCTAssertEqual(readout.report, Self.report(row))
            XCTAssertEqual(readout.score, Self.report(row).score)
            XCTAssertEqual(readout.rounds, row.roundCount > 0 ? "\(row.roundCount) rounds reported" : "Round count not reported")
            if case .recorded = readout.chance.value { recorded += 1 }
            if case .missing = readout.score.value { missingScores += 1 }
            points += readout.original.preview.history?.segments.reduce(0) { $0 + $1.count } ?? 0
            made[row.source, default: 0] += row.result ? 1 : 0
            let words = Model.words(readout)
            // Never a settlement, the venue's last price or an earlier raw zero as a chance.
            if let settlement = row.final.probability {
                XCTAssertFalse(words.contains(Self.percent(settlement)), row.key)
            }
            if let last = row.lastPrice.flatMap({ Double($0) }), last != row.baseline?.value {
                XCTAssertFalse(words.contains(Self.percent(last)), "the venue's last price is not a chance: \(row.key)")
            }
            if row.baseline == nil {
                XCTAssertEqual(readout.chance.value, .missing("No qualifying pre-event trade captured"), row.key)
                XCTAssertFalse(words.contains("0%"), "a missing baseline is never zero: \(row.key)")
            }
        }
        XCTAssertEqual(recorded, 14)
        XCTAssertEqual(missingScores, 21)
        XCTAssertEqual(points, 73)
        XCTAssertEqual(made, ["kalshi": 10, "polymarket": 10])

        // The same name in both sources: two originals, each with its own facts.
        let kalshi = try Self.shown(model, Self.ref(Self.named("Eugenio Lopez-Chacarra")))
        let polymarket = try Self.shown(model, Self.ref(Self.named("Eugenio Lopez-Chacarra", source: "polymarket")))
        XCTAssertNotEqual(kalshi.original.ref, polymarket.original.ref)
        XCTAssertEqual(Model.words(kalshi), [
            "Eugenio Lopez-Chacarra", "Pre-event · top 10", "33%", "Kalshi hour-ending trade · 2026-10-08T00:00:00+00:00 · before opening day",
            "Final result · includes ties", "Made top 10", "Reported score", "−13", Self.captured, "4 rounds reported",
        ])
        XCTAssertEqual(Model.words(polymarket), [
            "Eugenio Lopez-Chacarra", "Pre-event · top 10", "No qualifying pre-event trade captured",
            "Final result · includes ties", "Made top 10", "Reported score", "Score not reported", "Round count not reported",
        ])

        // A duplicated report is no report: the copy's words, never a borrowed score.
        let duplicated = Model(Self.input(reportRows: Self.rows + [Self.defaultRow]))
        let readout = try Self.shown(duplicated, Self.defaultRef)
        XCTAssertNil(readout.report)
        XCTAssertEqual(readout.score.value, .missing("Score not reported"))
        XCTAssertEqual(readout.rounds, "Round count not reported")
    }

    // MARK: Hero

    func testTheHeroShowsTheGolfersOwnDatedTop10ChanceBesideItsAdmittedPlacementResult() throws {
        let page = Self.page(Self.input(), log: Log())
        let headline = try XCTUnwrap(page.headlineContent())
        let model = FieldHeadlineModel10868(headline.input)
        XCTAssertEqual(model.title, "Open de España")
        XCTAssertEqual(model.eyebrow, "DP World Tour · final · Oct 8–11")
        let competitor = try XCTUnwrap(model.competitors.first)
        XCTAssertEqual(model.competitors.count, 1)
        XCTAssertEqual(competitor.resolution.original?.name, "Ludvig Aberg")
        XCTAssertEqual(competitor.metrics, [
            .reading(FieldChooserReading10868(label: "Pre-event · top 10",
                                              value: .recorded(text: "53%", detail: "Kalshi hour-ending trade · 2026-10-08T00:00:00+00:00 · before opening day"))),
            .reading(FieldChooserReading10868(label: "Final result · includes ties",
                                              value: .recorded(text: "Made top 10", detail: "Kalshi contract result"))),
        ])
        XCTAssertEqual(model.state?.caption, "Who made the top 10?")
        let pair = try XCTUnwrap(headline.input.pairs.first)
        XCTAssertEqual(pair.before?.probability, 0.53)
        XCTAssertNil(Self.defaultRow.final.probability)
        XCTAssertNotEqual(pair.before?.probability, Self.defaultRow.lastPrice.flatMap { Double($0) }, "never the venue's last price")
        // An untied reading (the venue's last price) is not shown, and borrows nothing.
        let untied = FieldHeadlineInput10868(
            scope: headline.input.scope, catalogue: headline.input.catalogue, displayed: headline.input.displayed,
            pairs: [FieldMovementPair10868(ref: pair.ref, before: FieldMovementObservation10868(
                probability: 0.99,
                reading: FieldChooserReading10868(label: "Pre-event · top 10", value: .recorded(text: "99%", detail: "Venue last price"))),
                                           later: nil, movement: nil, observation: nil)],
            finishes: headline.input.finishes, state: headline.input.state, phase: headline.input.phase,
            copy: headline.input.copy, unavailableWords: headline.input.unavailableWords)
        let untiedWords = (FieldHeadlineModel10868(untied).competitors.first?.metrics ?? []).flatMap { Self.words($0) }
        XCTAssertFalse(untiedWords.contains("99%"))
        XCTAssertFalse(untiedWords.contains("53%"))
        XCTAssertTrue(untiedWords.contains("Made top 10"), "the admitted result stays its own fact")
    }

    func testTheHeroAndTheMapEachMountOnlyAtTheirOwnFinalPhaseWithAPositiveControl() {
        for phase in [FieldOutlookPhase10868.before, .during] {
            let page = Self.page(Self.input(headlinePhase: phase, mapPhase: phase), log: Log())
            XCTAssertNil(page.model.headline, "\(phase)")
            XCTAssertNil(page.headlineContent(), "\(phase)")
            XCTAssertFalse(page.model.map.isFinal)
            XCTAssertTrue(page.model.map.bands.isEmpty, "\(phase)")
            XCTAssertTrue(page.model.map.marks.isEmpty, "\(phase)")
            XCTAssertNil(page.model.map.notice)
            let words = Self.reachable(page)
            XCTAssertTrue(words.contains(Self.headlineUnavailable), "\(phase)")
            XCTAssertTrue(words.contains(Self.withheld), "\(phase)")
            XCTAssertFalse(words.contains("2 priced golfers"), "no result band before the final: \(phase)")
            XCTAssertFalse(words.contains("12 priced golfers"), "\(phase)")
            XCTAssertFalse(words.contains("Kalshi contract result"), "\(phase)")
        }
        // Positive control: the same guards see the final hero and map.
        let page = Self.page(Self.input(), log: Log())
        let words = Self.reachable(page)
        XCTAssertTrue(words.contains("Kalshi contract result"))
        XCTAssertTrue(words.contains("2 priced golfers"))
        XCTAssertTrue(words.contains("12 priced golfers"))
        XCTAssertFalse(words.contains(Self.headlineUnavailable))
        XCTAssertFalse(words.contains(Self.withheld))
        XCTAssertEqual(page.model.map.marks.count, 14)
        // The two phases are independent: a final hero never relabels a withheld map, or the reverse.
        let mixed = Model(Self.input(headlinePhase: .final, mapPhase: .before))
        XCTAssertNotNil(mixed.headline)
        XCTAssertTrue(mixed.map.marks.isEmpty)
        let reverse = Model(Self.input(headlinePhase: .during, mapPhase: .final))
        XCTAssertNil(reverse.headline)
        XCTAssertEqual(reverse.map.marks.count, 14)
    }

    // MARK: Anchor

    func testTheHistoryCopyKeepsEveryPointRunScaleAndControlAndOnlyChangesHeightAndExpand() {
        let cases = [Self.defaultRow, Self.named("Eugenio Lopez-Chacarra"), Self.named("Angel Ayora Fanegas"),
                     Self.named("Eugenio Lopez-Chacarra", source: "polymarket")]
        XCTAssertEqual(cases.map(\.history.count), [8, 11, 5, 0])
        for row in cases {
            for full in [false, true] {
                let input = Self.input(historyRow: row, historySelection: Self.ref(row), full: full)
                let model = Model(input)
                let page = model.history(reader: false)
                let reader = model.history(reader: true)
                XCTAssertEqual(page, input.history, row.key)
                XCTAssertEqual(reader.series, input.history.series, "raw coordinates unchanged: \(row.key)")
                XCTAssertEqual(reader.ceiling, input.history.ceiling)
                XCTAssertEqual(reader.domain, input.history.domain)
                XCTAssertEqual(reader.scale, input.history.scale)
                XCTAssertEqual(reader.markKey, input.history.markKey)
                XCTAssertEqual(reader.notes, input.history.notes)
                XCTAssertNil(reader.expand)
                XCTAssertEqual(reader.plotHeight, 320)
                let series = input.history.series[0]
                XCTAssertEqual(FieldHistoryGeometry10868.marks(series, in: page).count, row.history.count,
                               "every recorded close is placed on its own scale: \(row.key) full=\(full)")
                XCTAssertEqual(FieldHistoryGeometry10868.lines(series, in: page).count,
                               Self.runs(row).filter { $0.points.count >= 2 }.count, "runs never join across a gap: \(row.key)")
                XCTAssertEqual(series.runs.flatMap(\.points).filter { $0.style == .hollow }.count,
                               row.history.filter { $0.phase == "before" }.count, "hollow before opening day: \(row.key)")
                XCTAssertFalse(series.runs.flatMap(\.points).contains { $0.probability == 1 || $0.probability == 0 },
                               "no settlement or zero endpoint: \(row.key)")
                XCTAssertEqual(input.history.ceiling, full ? 1 : Self.ceiling(row.history.map(\.value) + (row.baseline.map { [$0.value] } ?? [])))
            }
        }
        // The full-size height is finite and never shorter.
        for (owner, expected) in [(CGFloat?.none, CGFloat(200)), (.some(.nan), 200), (.some(-5), 200),
                                  (.some(150), 200), (.some(.infinity), 200), (.some(480), 480)] {
            let model = Model(Self.input(readerPlotHeight: owner))
            XCTAssertEqual(model.history(reader: true).plotHeight, expected, "\(String(describing: owner))")
            XCTAssertEqual(model.history(reader: false).plotHeight, 200)
        }
        // The default golfer's own journey: its auto scale and its two hollow closes.
        let aberg = Self.history(Self.defaultRow)
        XCTAssertEqual(aberg.ceiling, 1, "a 0.99 close needs the full scale")
        XCTAssertEqual(aberg.caption, "Ludvig Aberg · recorded chance · 0–100%")
        XCTAssertEqual(aberg.series[0].runs.count, 8, "eight closes, every gap over two hours stays open")
    }

    func testInspectingTheHistoryNeverChangesTheHeroMapOrReadouts() {
        let row = Self.defaultRow
        let point = row.history[3]
        let inspection = FieldHistoryInspection10868(
            x: Double(point.t), caption: "Hour ending \(point.at)",
            selections: [row.key: .point(id: "\(row.key)@\(point.t)", spoken: Self.percent(point.value))],
            choices: [], choicePresentation: .slider(label: "Top 10 trade observation"), note: nil)
        let still = Self.page(Self.input(mapSelected: Self.ref(Self.named("Shane Lowry"))), log: Log())
        let inspected = Self.page(Self.input(mapSelected: Self.ref(Self.named("Shane Lowry")), inspection: inspection), log: Log())
        XCTAssertNotEqual(still.input.history, inspected.input.history)
        XCTAssertEqual(still.input.headline, inspected.input.headline)
        XCTAssertEqual(still.model.map.marks, inspected.model.map.marks)
        XCTAssertEqual(still.model.readout(role: .history), inspected.model.readout(role: .history))
        XCTAssertEqual(still.model.readout(role: .map), inspected.model.readout(role: .map))
        XCTAssertEqual(Self.reachable(still), Self.reachable(inspected))
        let words = Self.reachable(inspected)
        XCTAssertTrue(words.contains("Made top 10"), "the final result stays fixed while inspecting")
        XCTAssertTrue(words.contains("−10"), "the reported score stays fixed while inspecting")
        XCTAssertFalse(words.contains("42%"), "the inspected close never becomes the pre-event chance")
    }

    // MARK: Map points

    func testEveryMapPointSitsAtItsOwnChanceInsideItsOwnResultBandAndNothingElseIsDrawn() {
        let model = Model(Self.input())
        let marks = model.map.marks
        XCTAssertEqual(marks.count, 14)
        XCTAssertEqual(marks.map(\.original.ref), Self.known.map { Self.ref($0) }, "the owner's order, never re-ranked")
        XCTAssertEqual(Self.known.map(\.name), [
            "Ludvig Aberg", "Tom McKibbin", "Tyrrell Hatton", "Shane Lowry", "Eugenio Lopez-Chacarra", "Sergio Garcia",
            "Patrick Reed", "David Puig", "Marco Penge", "Sam Bairstow", "Bernd Wiesberger", "Jayden Schaper",
            "Joakim Lagergren", "Angel Hidalgo",
        ])
        let rect = CGRect(x: 10, y: 0, width: 200, height: 50)
        for mark in marks {
            guard let row = Self.row(mark.original.ref), let baseline = row.baseline, let mapY = row.mapY else {
                XCTFail("\(mark.original.name) must be a priced original")
                continue
            }
            XCTAssertEqual(mark.x, baseline.value, row.name)
            XCTAssertEqual(mark.band, row.result ? 0 : 1, row.name)
            XCTAssertEqual(mark.level, row.result ? (mapY - 5) / (10 - 5) : (mapY - 0) / (5 - 0), row.name)
            XCTAssertEqual(mark.figure, Self.percent(baseline.value), row.name)
            XCTAssertEqual(mark.original.result, Self.result(row))
            XCTAssertEqual(Geometry.x(mark.x, in: rect), 10 + 200 * CGFloat(baseline.value), row.name)
        }
        XCTAssertEqual(model.map.marks(inBand: 0).map(\.original.name), ["Ludvig Aberg", "Eugenio Lopez-Chacarra"])
        XCTAssertEqual(model.map.marks(inBand: 1).count, 12)
        XCTAssertTrue(model.map.marks(inBand: 1).allSatisfy { $0.original.result == Self.missedResult })
        XCTAssertEqual(marks.reduce(0) { $0 + $1.x }, 4.11, accuracy: 1e-9, "drawn raw: never normalized to one")
        let drawn = Set(marks.map(\.original.ref))
        XCTAssertEqual(Self.rows.filter { !drawn.contains(Self.ref($0)) }.count, 131, "no baseline, no mark — never a zero")
        XCTAssertEqual(model.map.ticks.map(\.label), ["0%", "25%", "50%", "75%", "100%"])

        // Geometry: the common scale and the band's own head and foot.
        XCTAssertEqual(Geometry.x(0, in: rect), 10)
        XCTAssertEqual(Geometry.x(1, in: rect), 210)
        XCTAssertNil(Geometry.x(1.2, in: rect))
        XCTAssertNil(Geometry.x(.nan, in: rect))
        XCTAssertEqual(Geometry.y(1, in: rect), 0)
        XCTAssertEqual(Geometry.y(0, in: rect), 50)
        XCTAssertEqual(Geometry.markArea(CGRect(x: 0, y: 0, width: 280, height: 88), radius: 9),
                       CGRect(x: 9, y: 11, width: 262, height: 66))

        // Not drawn, while every healthy sibling keeps its own mark.
        func drawn(_ input: Input) -> [String] { Model(input).map.marks.map(\.original.name) }
        let aberg = Self.defaultRow
        let lowry = Self.named("Shane Lowry")
        let others = Self.known.filter { $0.key != aberg.key }
        let healthy = Self.known.map { Self.point($0) }
        func replacing(_ row: Row, with point: GolfPlacementMapPoint10868) -> [GolfPlacementMapPoint10868] {
            healthy.map { $0.chance.ref == Self.ref(row) ? point : $0 }
        }
        // A point listed twice.
        XCTAssertEqual(drawn(Self.input(points: healthy + [Self.point(aberg)])), others.map(\.name))
        // A foreign or unknown identity.
        let foreign = GolfPlacementMapPoint10868(
            chance: FieldOutlookBeforeChance10868(ref: Ref(scope: "other", source: "kalshi", marketID: "KXDPWTTOP10-OPDEPBM26",
                                                           outcomeID: aberg.final.id.text),
                                                  probability: 0.53, reading: Self.chance(aberg)),
            band: "made", offset: 7)
        XCTAssertEqual(drawn(Self.input(points: replacing(aberg, with: foreign))), others.map(\.name))
        let unknown = GolfPlacementMapPoint10868(
            chance: FieldOutlookBeforeChance10868(ref: Ref(scope: Self.scope, source: "kalshi", marketID: "KXDPWTTOP10-OPDEPBM26",
                                                           outcomeID: "KXDPWTTOP10-OPDEPBM26-NONE"),
                                                  probability: 0.53, reading: Self.chance(aberg)),
            band: "made", offset: 7)
        XCTAssertEqual(drawn(Self.input(points: replacing(aberg, with: unknown))), others.map(\.name))
        // A withdrawn original: gone from the catalogue, its point kept.
        XCTAssertEqual(drawn(Self.input(Self.rows.filter { $0.key != aberg.key }, historySelection: nil, mapSelected: nil)),
                       others.map(\.name))
        // A band its own result does not name; an offset outside its band.
        let wrongBand = GolfPlacementMapPoint10868(chance: Self.point(lowry).chance, band: "made", offset: 7)
        XCTAssertFalse(drawn(Self.input(points: replacing(lowry, with: wrongBand))).contains("Shane Lowry"))
        XCTAssertEqual(drawn(Self.input(points: replacing(lowry, with: wrongBand))).count, 13)
        let outside = GolfPlacementMapPoint10868(chance: Self.point(aberg).chance, band: "made", offset: 4)
        XCTAssertEqual(drawn(Self.input(points: replacing(aberg, with: outside))), others.map(\.name))
        // An invalid or duplicated band draws none of its members.
        let inverted = [GolfPlacementMapBand10868(id: "made", label: "Made top 10", count: nil, result: Self.madeResult, lower: 10, upper: 5),
                        Self.mapBands[1]]
        XCTAssertEqual(drawn(Self.input(mapBands: inverted)).count, 12)
        XCTAssertEqual(drawn(Self.input(mapBands: Self.mapBands + [Self.mapBands[0]])).count, 12)
        // A settlement substituted as a Polymarket chance; a missing baseline sent as zero.
        let pm = Self.named("Eugenio Lopez-Chacarra", source: "polymarket")
        let settlement = GolfPlacementMapPoint10868(
            chance: FieldOutlookBeforeChance10868(ref: Self.ref(pm), probability: pm.final.probability!,
                                                  reading: FieldChooserReading10868(label: Self.chanceLabel,
                                                                                    value: .recorded(text: "100%", detail: "Settled"))),
            band: "made", offset: 7)
        XCTAssertEqual(drawn(Self.input(points: healthy + [settlement])), Self.known.map(\.name))
        let noBaseline = Self.named("Angel Ayora Fanegas")
        let zero = GolfPlacementMapPoint10868(
            chance: FieldOutlookBeforeChance10868(ref: Self.ref(noBaseline), probability: 0, reading: Self.chance(noBaseline)),
            band: noBaseline.result ? "made" : "missed", offset: noBaseline.result ? 7 : 1)
        XCTAssertEqual(drawn(Self.input(points: healthy + [zero])), Self.known.map(\.name))
        // A raw value that is not a probability; a reading that is not its own.
        for bad in [1.2, -0.1, Double.nan, .infinity] {
            let point = GolfPlacementMapPoint10868(
                chance: FieldOutlookBeforeChance10868(ref: Self.ref(aberg), probability: bad, reading: Self.chance(aberg)),
                band: "made", offset: 7)
            XCTAssertEqual(drawn(Self.input(points: replacing(aberg, with: point))), others.map(\.name), "\(bad)")
        }
        let lastPrice = GolfPlacementMapPoint10868(
            chance: FieldOutlookBeforeChance10868(ref: Self.ref(aberg), probability: 0.99,
                                                  reading: FieldChooserReading10868(label: Self.chanceLabel,
                                                                                    value: .recorded(text: "99%", detail: "Venue last price"))),
            band: "made", offset: 7)
        XCTAssertEqual(drawn(Self.input(points: replacing(aberg, with: lastPrice))), others.map(\.name))
    }

    func testTheHighlightIsOnlyTheHeldOriginalsOwnMarkAndAnUnknownSelectionNeverBorrowsANeighbour() throws {
        let model = Model(Self.input())
        XCTAssertEqual(model.map.highlighted?.original.name, "Ludvig Aberg")
        XCTAssertEqual(model.map.marks.filter(\.isSelected).map(\.original.name), ["Ludvig Aberg"])
        XCTAssertNil(model.map.notice)

        let lowry = Model(Self.input(mapSelected: Self.ref(Self.named("Shane Lowry"))))
        XCTAssertEqual(lowry.map.highlighted?.original.name, "Shane Lowry")
        XCTAssertEqual(lowry.map.marks.filter(\.isAnnotated).map(\.original.name),
                       ["Ludvig Aberg", "Shane Lowry", "Eugenio Lopez-Chacarra"], "the held mark and the owner's labelled marks")
        XCTAssertEqual(lowry.entryName(.map), "Shane Lowry")
        XCTAssertEqual(lowry.entryName(.history), "Ludvig Aberg", "the history golfer is untouched")

        // The Polymarket namesake of a drawn mark: its own readout, no borrowed mark.
        let pm = Self.named("Eugenio Lopez-Chacarra", source: "polymarket")
        let namesake = Model(Self.input(mapSelected: Self.ref(pm)))
        XCTAssertNil(namesake.map.highlighted, "never the Kalshi original with the same name")
        XCTAssertEqual(namesake.map.notice, Self.unplaced)
        let readout = try Self.shown(namesake, Self.ref(pm))
        XCTAssertEqual(readout.chance.value, .missing("No qualifying pre-event trade captured"))
        XCTAssertEqual(namesake.readout(role: .map), .shown(readout))

        // A Kalshi original without a qualifying baseline: reachable, unplaced.
        let unpriced = Model(Self.input(mapSelected: Self.ref(Self.named("Angel Ayora Fanegas"))))
        XCTAssertNil(unpriced.map.highlighted)
        XCTAssertEqual(unpriced.map.notice, Self.unplaced)

        // Foreign, unknown and duplicated identities: the owner's words, nothing borrowed.
        let aberg = Self.defaultRow
        let foreign = Ref(scope: "other", source: "kalshi", marketID: "KXDPWTTOP10-OPDEPBM26", outcomeID: aberg.final.id.text)
        let unknown = Ref(scope: Self.scope, source: "kalshi", marketID: "KXDPWTTOP10-OPDEPBM26", outcomeID: "KXDPWTTOP10-OPDEPBM26-NONE")
        for odd in [Model(Self.input(mapSelected: foreign)), Model(Self.input(mapSelected: unknown)),
                    Model(Self.input(Self.rows + [aberg], historySelection: nil, mapSelected: Self.defaultRef))] {
            XCTAssertNil(odd.map.highlighted)
            XCTAssertNil(odd.map.notice, "an identity that does not resolve is not an unplaced original")
            XCTAssertEqual(odd.readout(role: .map), .unavailable(Self.unavailable))
            XCTAssertEqual(odd.entryName(.map), Self.unavailable)
            XCTAssertTrue(odd.map.marks.allSatisfy { !$0.isSelected })
            XCTAssertNil(odd.map.neighbour(.next))
        }
        // Nothing held: nothing highlighted, no words.
        let none = Model(Self.input(mapSelected: nil))
        XCTAssertNil(none.map.highlighted)
        XCTAssertNil(none.map.notice)
        XCTAssertEqual(none.readout(role: .map), .notHeld)
        XCTAssertNil(none.entryName(.map))
    }

    // MARK: Dense taps (Design L1)

    func testEveryDrawnDotChoosesItsOwnOriginalByTheUniquelyClosestCentre() throws {
        let model = Model(Self.input())
        let strip = CGSize(width: 280, height: 88)
        var chosen: [Ref] = []
        for band in model.map.bands.indices {
            let placed = Self.centres(model.map, band: band, strip: strip)
            for entry in placed {
                // Dense: in the missed band every dot's reach also holds another dot.
                let crowded = placed.contains { $0.mark != entry.mark && Self.distance($0.center, entry.center) <= 22 }
                XCTAssertEqual(crowded, band == 1, entry.mark.original.name)
                let ref = Map.choice(at: entry.center, in: strip, band: band, model: model.map, radius: 9, target: 44)
                XCTAssertEqual(ref, entry.mark.original.ref, "the dot touched chooses itself: \(entry.mark.original.name)")
                chosen.append(entry.mark.original.ref)
            }
        }
        XCTAssertEqual(chosen.count, 14)
        XCTAssertEqual(Set(chosen), Set(Self.known.map { Self.ref($0) }))

        // Near a dot, with neighbours in reach: the uniquely closest one.
        let missed = Self.centres(model.map, band: 1, strip: strip)
        let hidalgo = try XCTUnwrap(missed.first { $0.mark.original.name == "Angel Hidalgo" })
        let near = CGPoint(x: hidalgo.center.x - 3, y: hidalgo.center.y)
        XCTAssertGreaterThan(missed.filter { Self.distance($0.center, near) <= 22 }.count, 1)
        XCTAssertEqual(Map.choice(at: near, in: strip, band: 1, model: model.map, radius: 9, target: 44), hidalgo.mark.original.ref)
        // Out of every reach: nothing.
        XCTAssertNil(Map.choice(at: CGPoint(x: 270, y: 5), in: strip, band: 1, model: model.map, radius: 9, target: 44))
        XCTAssertNil(Map.choice(at: CGPoint(x: -40, y: -40), in: strip, band: 0, model: model.map, radius: 9, target: 44))

        // Geometry: an exact tie is no choice; a unique closest is; out of reach is none.
        let centres = [CGPoint(x: 0, y: 0), CGPoint(x: 10, y: 0), CGPoint(x: 100, y: 0)]
        XCTAssertNil(Geometry.hit(CGPoint(x: 5, y: 0), centers: centres, radius: 22), "equally close: no choice")
        XCTAssertEqual(Geometry.hit(CGPoint(x: 4, y: 0), centers: centres, radius: 22), 0)
        XCTAssertEqual(Geometry.hit(CGPoint(x: 6, y: 1), centers: centres, radius: 22), 1)
        XCTAssertEqual(Geometry.hit(CGPoint(x: 99, y: 0), centers: centres, radius: 22), 2)
        XCTAssertNil(Geometry.hit(CGPoint(x: 50, y: 0), centers: centres, radius: 22))
        XCTAssertNil(Geometry.hit(CGPoint(x: 5, y: 0), centers: centres, radius: 0))
        XCTAssertNil(Geometry.hit(CGPoint(x: CGFloat.nan, y: 0), centers: centres, radius: 22))
        XCTAssertNil(Geometry.hit(CGPoint(x: 0, y: 0), centers: [], radius: 22))

        // Two originals the owner places on one exact centre: a tie, never a pick;
        // both stay reachable through the chooser and the steps.
        let garcia = Self.named("Sergio Garcia")
        let reed = Self.named("Patrick Reed")
        let stacked = Self.known.map { row -> GolfPlacementMapPoint10868 in
            row.key == reed.key ? GolfPlacementMapPoint10868(chance: Self.point(reed).chance, band: "missed", offset: garcia.mapY!)
                : Self.point(row)
        }
        let tied = Model(Self.input(points: stacked))
        let tiedCentres = Self.centres(tied.map, band: 1, strip: strip)
        let garciaCentre = try XCTUnwrap(tiedCentres.first { $0.mark.original.name == "Sergio Garcia" }).center
        XCTAssertEqual(tiedCentres.first { $0.mark.original.name == "Patrick Reed" }?.center, garciaCentre)
        XCTAssertNil(Map.choice(at: garciaCentre, in: strip, band: 1, model: tied.map, radius: 9, target: 44))
        XCTAssertEqual(tied.map.marks.count, 14, "a tied dot is still drawn")

        // The leaf's own choice needs a callback; the page's tap payload is the
        // exact original for the map role after exactly one hold.
        XCTAssertNil(Map(model: model.map).choice(at: hidalgo.center, in: strip, band: 1))
        let ref = try XCTUnwrap(Map.choice(at: hidalgo.center, in: strip, band: 1, model: model.map, radius: 9, target: 44))
        let log = Log()
        let page = Self.page(Self.input(), log: log)
        let place = Page.Place.stream(Self.activation(log))
        try XCTUnwrap(page.mapContent(at: place).onChoose)(ref)
        XCTAssertEqual(log.events, [Self.interaction, "choose:map:\(Self.named("Angel Hidalgo").final.id.text)"])
        let reader = Log()
        try XCTUnwrap(Self.page(Self.input(), .reader(.map), log: reader).mapContent(at: .reader).onChoose)(ref)
        XCTAssertEqual(reader.events, ["choose:map:\(Self.named("Angel Hidalgo").final.id.text)"])
        let held = Log()
        try XCTUnwrap(Self.page(Self.input(), log: held).mapContent(at: .page).onChoose)(ref)
        XCTAssertEqual(held.events, ["hold", "choose:map:\(Self.named("Angel Hidalgo").final.id.text)"])
    }

    // MARK: Named marks (Design L2)

    func testAnnotatedMarksNameTheirGolferBesideTheFigureMeasuredWithoutOverlap() throws {
        // Identity: the owner's compact name, else the whole name — never a fixture branch.
        let model = Model(Self.input())
        let made = model.map.marks(inBand: 0)
        XCTAssertEqual(made.map(\.name), ["Aberg", "Lopez-Chacarra"])
        XCTAssertEqual(made.map(\.figure), ["53%", "33%"])
        XCTAssertTrue(made.allSatisfy(\.isAnnotated))
        XCTAssertEqual(model.map.marks(inBand: 1).filter(\.isAnnotated).count, 0, "only the held and the owner's labelled marks")
        let whole = Self.known.map { row in
            GolfPlacementMapPoint10868(chance: Self.point(row).chance, band: row.result ? "made" : "missed", offset: row.mapY!,
                                       labelled: row.result, label: row.key == Self.defaultRow.key ? "  " : nil)
        }
        let wholeNames = Model(Self.input(points: whole)).map.marks(inBand: 0).map(\.name)
        XCTAssertEqual(wholeNames, ["Ludvig Aberg", "Eugenio Lopez-Chacarra"], "nil or blank prints the whole name")
        // The map card's words carry each annotation's name and figure, and every mark's own words.
        let words = Self.page(Self.input(mapSelected: Self.ref(Self.named("Shane Lowry"))), log: Log()).mapWords(at: .reader)
        for pair in [["Aberg", "53%"], ["Lopez-Chacarra", "33%"], ["Lowry", "38%"]] {
            let index = try XCTUnwrap(words.firstIndex(of: pair[0]), pair[0])
            XCTAssertEqual(words[index + 1], pair[1], pair[0])
        }
        XCTAssertTrue(words.contains("Ludvig Aberg. Pre-event · top 10: 53%, Kalshi hour-ending trade · 2026-10-08T00:00:00+00:00 · before opening day. Final result · includes ties: Made top 10"))

        // The lane rule: crowded annotations step up a row; none overlaps, shrinks or leaves the lane.
        let crowded = [GolfPlacementMapAnnotation10868(x: 200, size: CGSize(width: 60, height: 28), required: true),
                       GolfPlacementMapAnnotation10868(x: 150, size: CGSize(width: 70, height: 28), required: false),
                       GolfPlacementMapAnnotation10868(x: 100, size: CGSize(width: 70, height: 28), required: false)]
        let narrow = Geometry.lane(crowded, width: 262, spacing: 4)
        XCTAssertEqual(narrow.rects, [CGRect(x: 170, y: 32, width: 60, height: 28), CGRect(x: 115, y: 0, width: 70, height: 28),
                                      CGRect(x: 65, y: 32, width: 70, height: 28)])
        XCTAssertEqual(narrow.height, 64)
        let wide = Geometry.lane(crowded.map {
            GolfPlacementMapAnnotation10868(x: $0.x * 3, size: $0.size, required: $0.required)
        }, width: 786, spacing: 4)
        XCTAssertEqual(wide.height, 32, "room for every annotation on one row")
        let ax = Geometry.lane(crowded.map {
            GolfPlacementMapAnnotation10868(x: $0.x, size: CGSize(width: $0.size.width * 2, height: $0.size.height * 2), required: $0.required)
        }, width: 262, spacing: 4)
        XCTAssertEqual(ax.height, 3 * 56 + 3 * 4, "larger text: more rows, never smaller text")
        for plan in [narrow, wide, ax] {
            for a in plan.rects.indices {
                for b in plan.rects.indices where b > a {
                    XCTAssertFalse(plan.rects[a].intersects(plan.rects[b]), "\(a) \(b)")
                }
            }
            XCTAssertTrue(plan.rects.allSatisfy { $0.minX >= 0 && $0.minY >= 0 && $0.maxY <= plan.height })
        }
        XCTAssertTrue(narrow.rects.allSatisfy { $0.maxX <= 262 })
        XCTAssertEqual(narrow.rects[0].maxY, narrow.height - 4, "the held mark's annotation sits nearest the marks")
        // Edges keep the whole annotation inside; an empty lane takes no room.
        let edges = Geometry.lane([GolfPlacementMapAnnotation10868(x: 2, size: CGSize(width: 60, height: 20), required: false),
                                   GolfPlacementMapAnnotation10868(x: 260, size: CGSize(width: 60, height: 20), required: false)],
                                  width: 262, spacing: 4)
        XCTAssertEqual(edges.rects.map(\.minX), [0, 202])
        XCTAssertEqual(Geometry.lane([], width: 262, spacing: 4), GolfPlacementMapLanePlan10868(rects: [], height: 0))
        XCTAssertEqual(Geometry.flipped(narrow).rects.map(\.minY), [4, 36, 4], "the axis reads the same rule downward")

        // Hosted: the measured lane grows with Dynamic Type and with a narrower width, never shrinking.
        func height(_ width: CGFloat, _ size: DynamicTypeSize) -> CGFloat {
            let host = hostForMeasurement(Map(model: model.map).frame(width: width), at: size)
            host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            return host.sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude)).height
        }
        XCTAssertGreaterThan(height(343, .accessibility3), height(343, .large))
        XCTAssertGreaterThanOrEqual(height(343, .large), height(900, .large))
        XCTAssertGreaterThanOrEqual(height(343, .xxxLarge), height(343, .large))
    }

    // MARK: Selections

    func testHistoryAndMapSelectionsAreIndependentAndSurviveOwnerFrames() throws {
        let lowry = Self.named("Shane Lowry")
        let base = Self.input(historySelection: Self.defaultRef, mapSelected: Self.ref(lowry))
        let model = Model(base)
        guard case .shown(let history) = model.readout(role: .history),
              case .shown(let map) = model.readout(role: .map) else { return XCTFail("both resolve") }
        XCTAssertEqual(history.original.name, "Ludvig Aberg")
        XCTAssertEqual(map.original.name, "Shane Lowry")
        XCTAssertEqual(model.map.highlighted?.original.name, "Shane Lowry")

        // A map choice acts for the map role only; the history chooser for the history role only.
        let log = Log()
        let page = Self.page(base, .reader(.map), log: log)
        try XCTUnwrap(page.mapContent(at: .reader).onChoose)(Self.ref(Self.named("Tom McKibbin")))
        try XCTUnwrap(Self.page(base, .chooser(.history), log: log).chooserContent(.history)?.onChoose)(Self.ref(Self.rows[5]))
        XCTAssertEqual(log.events, ["choose:map:\(Self.named("Tom McKibbin").final.id.text)", "hold",
                                    "choose:history:\(Self.rows[5].final.id.text)"])

        // Owner frames: reordered catalogue and reader order keep both; omission
        // shows the owner's words for that role only; restoration returns the exact golfer.
        let reordered = Model(Self.input(Self.rows.reversed(), historySelection: Self.defaultRef, mapSelected: Self.ref(lowry),
                                         traversal: Self.known.reversed().map { Self.ref($0) }))
        XCTAssertEqual(reordered.readout(role: .history), model.readout(role: .history))
        XCTAssertEqual(reordered.readout(role: .map), model.readout(role: .map))
        XCTAssertEqual(reordered.map.highlighted?.original.ref, Self.ref(lowry))
        let withoutLowry = Self.rows.filter { $0.key != lowry.key }
        let omitted = Model(Self.input(withoutLowry, historySelection: Self.defaultRef, mapSelected: Self.ref(lowry)))
        XCTAssertEqual(omitted.readout(role: .map), .unavailable(Self.unavailable))
        XCTAssertEqual(omitted.readout(role: .history), model.readout(role: .history))
        XCTAssertNil(omitted.map.highlighted, "the withdrawn golfer's mark is gone, and nothing else is highlighted")
        XCTAssertEqual(omitted.map.marks.count, 13)
        let restored = Model(Self.input(historySelection: Self.defaultRef, mapSelected: Self.ref(lowry)))
        XCTAssertEqual(restored.readout(role: .map), model.readout(role: .map))
        XCTAssertEqual(restored.map.highlighted, model.map.highlighted)

        // Withdrawing the history golfer leaves the map golfer and the map intact.
        let withoutAberg = Model(Self.input(Self.rows.filter { $0.key != Self.defaultRow.key },
                                            historySelection: Self.defaultRef, mapSelected: Self.ref(lowry)))
        XCTAssertEqual(withoutAberg.readout(role: .history), .unavailable(Self.unavailable))
        XCTAssertEqual(withoutAberg.readout(role: .map), model.readout(role: .map))
        // The chooser's own notice for its withdrawn selection.
        let notice = FieldChooserModel10868(try XCTUnwrap(omitted.chooserPresentation(.map))).selectionNotice
        XCTAssertEqual(notice, "Golfer unavailable")
    }

    func testPreviousAndNextFollowTheOwnersReaderOrderNeverCatalogueOrEnumOrder() throws {
        func names(_ input: Input) -> (String?, String?) {
            let map = Model(input).map
            return (map.neighbour(.previous)?.name, map.neighbour(.next)?.name)
        }
        let aberg = Self.defaultRow
        let lowry = Self.named("Shane Lowry")
        let hidalgo = Self.named("Angel Hidalgo")
        XCTAssertTrue(names(Self.input()) == (nil, "Tom McKibbin"))
        XCTAssertNotEqual(Self.rows[1].name, "Tom McKibbin", "the reader order is the owner's, not the catalogue's")
        XCTAssertTrue(names(Self.input(mapSelected: Self.ref(lowry))) == ("Tyrrell Hatton", "Eugenio Lopez-Chacarra"))
        XCTAssertTrue(names(Self.input(mapSelected: Self.ref(hidalgo))) == ("Joakim Lagergren", nil))
        let reversed = Self.known.reversed().map { Self.ref($0) }
        XCTAssertTrue(names(Self.input(traversal: reversed)) == ("Tom McKibbin", nil))
        // Not in the order, listed twice, or a neighbour that does not resolve: none — never the next one along.
        XCTAssertTrue(names(Self.input(mapSelected: Self.ref(Self.named("Eugenio Lopez-Chacarra", source: "polymarket")))) == (nil, nil))
        XCTAssertTrue(names(Self.input(traversal: Self.known.map { Self.ref($0) } + [Self.ref(aberg)])) == (nil, nil))
        let mckibbinTwice = Self.known.map { Self.ref($0) } + [Self.ref(Self.named("Tom McKibbin"))]
        XCTAssertTrue(names(Self.input(traversal: mckibbinTwice)) == (nil, nil))
        XCTAssertTrue(names(Self.input(Self.rows.filter { $0.name != "Tom McKibbin" })) == (nil, nil))
        XCTAssertTrue(names(Self.input(traversal: [])) == (nil, nil))

        // The steps' exact payloads: the stream's interaction, full size exact, the page hook once.
        let stream = Log()
        let page = Self.page(Self.input(mapSelected: Self.ref(lowry)), log: stream)
        let place = Page.Place.stream(Self.activation(stream))
        try XCTUnwrap(page.stepAction(.previous, at: place))()
        try XCTUnwrap(page.stepAction(.next, at: place))()
        XCTAssertEqual(stream.events, [Self.interaction, "choose:map:\(Self.named("Tyrrell Hatton").final.id.text)",
                                       Self.interaction, "choose:map:\(Self.named("Eugenio Lopez-Chacarra").final.id.text)"])
        let reader = Log()
        try XCTUnwrap(Self.page(Self.input(mapSelected: Self.ref(lowry)), .reader(.map), log: reader).stepAction(.next, at: .reader))()
        XCTAssertEqual(reader.events, ["choose:map:\(Self.named("Eugenio Lopez-Chacarra").final.id.text)"])
        let held = Log()
        try XCTUnwrap(Self.page(Self.input(mapSelected: Self.ref(lowry)), log: held).stepAction(.next, at: .page))()
        XCTAssertEqual(held.events, ["hold", "choose:map:\(Self.named("Eugenio Lopez-Chacarra").final.id.text)"])
        XCTAssertNil(Self.page(Self.input(), log: Log()).stepAction(.previous, at: .page), "no neighbour, no control")
        XCTAssertEqual(Array(Self.page(Self.input(mapSelected: Self.ref(lowry)), log: Log()).mapWords(at: .reader).suffix(3)),
                       ["Previous", "Next", Self.mapCopy.note!])
    }

    // MARK: Chooser

    func testTheChooserReachesAll145ThroughBoundedModesBandsAndPagesNeverAWallOfButtons() throws {
        let expected: [(String, Int, String, String)] = [
            ("A–C", 21, "Adrian Meronk", "Connor Syme"), ("D–G", 31, "Dan Bradbury", "Guido Migliozzi"),
            ("H–L", 32, "Hennie Du Plessis", "Luke List"), ("M–P", 26, "Manuel Elvira", "Paul Waring"),
            ("Q–S", 20, "Quim Vidal", "Stefano Mazzoli"), ("T–Z", 15, "Thomas Aiken", "Zhou Yanhan"),
        ]
        XCTAssertEqual(expected.map(\.0), Self.bands)
        var reached: Set<Ref> = []
        for (band, count, first, last) in expected {
            let members = Self.members(band)
            XCTAssertEqual(members.count, count, band)
            XCTAssertEqual(members.first?.name, first, band)
            XCTAssertEqual(members.last?.name, last, band)
            let pages = Self.pages(band)
            XCTAssertEqual(pages.count, (count + 5) / 6, band)
            for index in pages.indices {
                let log = Log()
                let input = Self.input(mapGroup: Self.groupID(band, index))
                let page = Self.page(input, .chooser(.map), log: log)
                let shown = try XCTUnwrap(page.model.chooserPresentation(.map))
                XCTAssertEqual(shown.browse?.groups.map(\.id), [Self.groupID(band, index)], "one group, not every page")
                let rows = FieldChooserModel10868(shown).groupRows
                XCTAssertLessThanOrEqual(rows.count, 6)
                XCTAssertEqual(rows.compactMap { $0.resolution.original?.ref }, pages[index].map { Self.ref($0) })
                reached.formUnion(rows.compactMap { $0.resolution.original?.ref })
                // Every row chooses its exact original for the map role, after one hold.
                let chooser = try XCTUnwrap(page.chooserContent(.map))
                for row in rows { chooser.onChoose?(row.ref) }
                XCTAssertEqual(log.events, rows.flatMap { ["hold", "choose:map:\($0.ref.outcomeID)"] })
            }
            for index in Set([0, pages.count / 2, pages.count - 1]) {
                let navigation = try XCTUnwrap(Model(Self.input(mapGroup: Self.groupID(band, index))).chooserNavigation(.map))
                XCTAssertEqual(navigation.control(navigation.navigation.previous, canControl: true),
                               index > 0 ? .chooseGroup(id: Self.groupID(band, index - 1)) : nil, "\(band) \(index)")
                XCTAssertEqual(navigation.control(navigation.navigation.next, canControl: true),
                               index + 1 < pages.count ? .chooseGroup(id: Self.groupID(band, index + 1)) : nil, "\(band) \(index)")
                XCTAssertEqual(navigation.navigation.bands.map { navigation.control($0, canControl: true) },
                               Self.bands.map { Optional(FieldChooserControl10868.chooseGroup(id: Self.groupID($0, 0))) })
                XCTAssertNil(navigation.control(Target(label: "Next", groupID: "\(band)|99"), canControl: true), "a foreign page id hands back nothing")
                XCTAssertNil(navigation.control(navigation.navigation.next, canControl: false))
            }
        }
        XCTAssertEqual(reached, Set(Self.rows.map { Self.ref($0) }), "every original is reachable")
        XCTAssertEqual(reached.count, 145)
        XCTAssertEqual(Self.rows.filter { reached.contains(Self.ref($0)) && $0.source == "polymarket" }.count, 13)
        XCTAssertEqual(Self.rows.filter { reached.contains(Self.ref($0)) && $0.history.isEmpty }.count, 121)
        XCTAssertEqual(Self.rows.filter { reached.contains(Self.ref($0)) && $0.baseline == nil }.count, 131)
        XCTAssertEqual(Self.rows.filter { reached.contains(Self.ref($0)) && $0.score == nil }.count, 21)

        // The page's navigation control: one hold, then the exact role-tagged group.
        let log = Log()
        let page = Self.page(Self.input(historyGroup: Self.groupID("H–L", 3)), .chooser(.history), log: log)
        let pages = try XCTUnwrap(page.chooserNavigationContent(.history, .pages))
        pages.choose(pages.model.navigation.next)
        pages.choose(pages.model.navigation.previous)
        XCTAssertEqual(log.events, ["hold", "control:history:\(FieldChooserControl10868.chooseGroup(id: "H–L|4"))",
                                    "hold", "control:history:\(FieldChooserControl10868.chooseGroup(id: "H–L|2"))"])

        // Suggested mode: the owner's suggestions, its own group.
        XCTAssertEqual(Self.suggestions.map(\.name), ["Ludvig Aberg", "Tom McKibbin", "Eugenio Lopez-Chacarra"])
        let suggested = try XCTUnwrap(Model(Self.input(mapGroup: "suggested")).chooserPresentation(.map))
        XCTAssertEqual(FieldChooserModel10868(suggested).groupRows.compactMap { $0.resolution.original?.name },
                       ["Ludvig Aberg", "Tom McKibbin", "Eugenio Lopez-Chacarra"])
    }

    // MARK: Originals

    func testEveryOriginalKeepsItsRulesVerbatimItsOwnClocksAndItsExactDetails() throws {
        let originals = Self.originals(selection: nil)
        for row in Self.rows {
            let selection = Details.Selection(scope: Self.marketScope, identity: Self.identity(row))
            let content = try XCTUnwrap(Details.content(catalogue: originals.catalogue, selection: selection), row.key)
            XCTAssertEqual(content.rules, .verified([row.rules]), "byte-exact rules: \(row.key)")
            XCTAssertEqual(content.outcome, row.name)
            XCTAssertEqual(content.result?.words, row.result ? "Resolved Yes" : "Resolved No")
            XCTAssertEqual(content.readings.first?.text, row.baseline.map { Self.percent($0.value) } ?? Self.noBaseline)
            XCTAssertEqual(content.readings.first?.provenance, row.baseline.map { Self.provenance(row, $0) })
        }
        // The held original's Details, mounted with one hold on its history control.
        let log = Log()
        let page = Self.page(Self.input(), .original, log: log, originals: Self.originals(selection: Self.defaultRow))
        let details = try XCTUnwrap(page.originalDetailsContent())
        XCTAssertEqual(details.selection?.identity.market, "KXDPWTTOP10-OPDEPBM26-LABE")
        details.onHistory?(Details.HistoryIntent(selection: details.selection!, entry: .explore, actionID: "explore"))
        let catalogue = try XCTUnwrap(Self.page(Self.input(), .catalogue, log: log, originals: originals).catalogueContent())
        let pm = Self.named("Eugenio Lopez-Chacarra", source: "polymarket")
        catalogue.onSelect?(Details.Selection(scope: Self.marketScope, identity: Self.identity(pm)))
        XCTAssertEqual(log.events, ["hold", "originalHistory:explore", "hold", "select:245877574"])
        // Each readout's Details hand back that golfer's exact original.
        let readoutLog = Log()
        let both = Self.page(Self.input(mapSelected: Self.ref(pm)), log: readoutLog)
        try XCTUnwrap(both.detailsAction(.history, at: .page))()
        try XCTUnwrap(both.detailsAction(.map, at: .reader))()
        XCTAssertEqual(readoutLog.events, ["hold", "details:KXDPWTTOP10-OPDEPBM26-LABE", "details:245877574"])
        // Clocks stay separate: the baseline hour, the capture time, the calendar words and the cutoff.
        let words = Self.reachable(Self.page(Self.input(), log: Log()))
        XCTAssertTrue(words.contains("Kalshi hour-ending trade · 2026-10-08T00:00:00+00:00 · before opening day"))
        XCTAssertTrue(words.contains(Self.captured))
        XCTAssertTrue(words.contains("DP World Tour · final · Oct 8–11"))
        XCTAssertTrue(Self.input().history.notes[0].contains("Exact first-tee time unavailable."))
        XCTAssertFalse(words.contains { $0.contains("UTC") }, "no UTC terminology")
    }

    // MARK: Holds and payloads

    func testEveryPageActionHoldsOnceStreamActionsUseTheStreamAndFullSizeIsExact() throws {
        let input = Self.input(mapSelected: Self.ref(Self.named("Shane Lowry")))
        let log = Log()
        let page = Self.page(input, log: log)
        page.openPageAbout()
        let headline = try XCTUnwrap(page.headlineContent())
        let competitor = try XCTUnwrap(FieldHeadlineModel10868(headline.input).competitors.first)
        let open = try XCTUnwrap(FieldHeadlineModel10868(headline.input).openAction(competitor, canOpen: true))
        headline.onOpen?(open)
        let history = page.historyContent(reader: false)
        history.onAction?("scale")
        history.onInspectionChoice?("choice-3")
        history.onPlotPosition?(1791417600)
        try XCTUnwrap(page.entryAction(.history, at: .page))()
        try XCTUnwrap(page.detailsAction(.history, at: .page))()
        try XCTUnwrap(page.allPropsAction())()
        let aberg = Self.defaultRow.final.id.text
        XCTAssertEqual(log.events, ["hold", "about", "hold", "open:\(aberg):-", "hold", "history:scale",
                                    "hold", "inspect:choice-3", "hold", "plot:1791417600.0", "hold", "chooser:history",
                                    "hold", "details:\(aberg)", "hold", "allProps"])

        // Inside the stream card: the stream's own interaction is the hold — no second hold.
        let stream = Log()
        let card = Self.page(input, log: stream)
        let place = Page.Place.stream(Self.activation(stream))
        let hatton = Self.ref(Self.named("Tyrrell Hatton"))
        try XCTUnwrap(card.mapContent(at: place).onChoose)(hatton)
        try XCTUnwrap(card.entryAction(.map, at: place))()
        try XCTUnwrap(card.detailsAction(.map, at: place))()
        try XCTUnwrap(card.stepAction(.next, at: place))()
        let lowry = Self.named("Shane Lowry").final.id.text
        XCTAssertEqual(stream.events, [Self.interaction, "choose:map:\(hatton.outcomeID)", Self.interaction, "chooser:map",
                                       Self.interaction, "details:\(lowry)",
                                       Self.interaction, "choose:map:\(Self.named("Eugenio Lopez-Chacarra").final.id.text)"])

        // Full size: exact callbacks, no hold.
        let reader = Log()
        let full = Self.page(input, .reader(.map), log: reader)
        try XCTUnwrap(full.mapContent(at: .reader).onChoose)(hatton)
        try XCTUnwrap(full.entryAction(.map, at: .reader))()
        try XCTUnwrap(full.detailsAction(.map, at: .reader))()
        full.historyContent(reader: true).onAction?("scale")
        full.openAbout()
        XCTAssertEqual(reader.events, ["choose:map:\(hatton.outcomeID)", "chooser:map", "details:\(lowry)", "history:scale", "about"])

        // Payloads: catalogue originals only, and no observation key at the final.
        let refs = Set(Self.rows.map { Self.ref($0) })
        XCTAssertEqual(Self.violations([open], history: input.history, refs: refs), [])
        XCTAssertNil(open.observation)
        // Controls: a key after the capture, and a foreign original, are caught.
        let future = "\(Self.defaultRow.key)@1791820800"
        XCTAssertEqual(Self.violations([FieldMovementOpen10868(ref: Self.defaultRef, observation: future)], history: input.history, refs: refs),
                       ["unbound \(future)"])
        XCTAssertEqual(Self.violations([FieldMovementOpen10868(ref: Ref(scope: "x", source: "kalshi", marketID: "1", outcomeID: "2"), observation: nil)],
                                       history: input.history, refs: refs), ["foreign 2"])
        XCTAssertEqual(Self.violations([FieldMovementOpen10868(ref: Self.defaultRef, observation: "\(Self.defaultRow.key)@1791417600")],
                                       history: input.history, refs: refs), [], "positive control: a drawn close is bound")
    }

    func testWithoutCallbacksNothingActsAndBuildingCallsNothing() {
        var holds = 0
        let input = Self.input(mapSelected: Self.ref(Self.named("Shane Lowry")))
        for mode in [GolfPlacementEventPageMode10868.page, .reader(.history), .reader(.map), .chooser(.history),
                     .chooser(.map), .catalogue, .original, .about] {
            let page = Page(input: input, mode: mode, originals: Self.originals(selection: Self.defaultRow), onInteraction: { holds += 1 })
            XCTAssertNil(page.aboutOpener(), "\(mode)")
            XCTAssertNil(page.headlineContent()?.onAbout)
            XCTAssertNil(page.headlineContent()?.onOpen)
            XCTAssertNil(page.historyContent(reader: false).onAction)
            XCTAssertNil(page.historyContent(reader: true).onInspectionChoice)
            XCTAssertNil(page.historyContent(reader: false).onPlotPosition)
            for role in Role.allCases {
                XCTAssertNil(page.entryAction(role, at: .page))
                XCTAssertNil(page.detailsAction(role, at: .reader))
                XCTAssertNil(page.chooserContent(role)?.onChoose)
                XCTAssertNil(page.chooserContent(role)?.onControl)
                XCTAssertNil(page.chooserNavigationContent(role, .pages)?.onControl)
            }
            XCTAssertNil(page.mapContent(at: .page).onChoose)
            XCTAssertNil(page.mapContent(at: .reader).onChoose)
            XCTAssertNil(page.stepAction(.previous, at: .page))
            XCTAssertNil(page.stepAction(.next, at: .reader))
            XCTAssertNil(page.allPropsAction())
            XCTAssertNil(page.catalogueContent()?.onSelect)
            XCTAssertNil(page.originalDetailsContent()?.onHistory)
            let words = page.mapWords(at: .page)
            XCTAssertFalse(words.contains("Change") || words.contains("Details & timing") || words.contains("Previous"),
                           "no dead control words: \(mode)")
        }
        XCTAssertEqual(holds, 0)
    }

    // MARK: Words

    func testTop10IsAPlacementNeverATournamentWinAndVoiceOverReadsTheOwnersWords() throws {
        let page = Self.page(Self.input(), log: Log())
        let words = Self.reachable(page)
        for token in ["win", "wins", "won", "Won", "winner", "Winner", "Tournament winner", "champion", "Champion", "victory"] {
            XCTAssertFalse(Self.mentions(words, token), token)
        }
        XCTAssertTrue(Self.mentions(words, "Made top 10"))
        XCTAssertTrue(Self.mentions(words, "includes ties"))
        // Positive controls: the same guard sees win wording, and the pipeline carries an owner's word through.
        XCTAssertTrue(Self.mentions(["Tournament winner"], "winner"))
        XCTAssertFalse(Self.mentions(["Winners"], "Winner"), "a fragment of a word is not a mention")
        let mislabelled = Model(Self.input()).readout(for: FieldChooserOriginal10868(
            ref: Self.defaultRef, name: "Ludvig Aberg", plan: .single(Self.chance(Self.defaultRow)),
            preview: FieldChooserPreview10868(history: nil, absence: "No recorded history"), movement: nil, clock: nil,
            result: FieldChooserResult10868(title: "Tournament result", words: "Won"), browseStatus: ""))
        XCTAssertTrue(Self.mentions(Model.words(mislabelled), "Won"), "positive control: an owner's win word would be caught")

        // VoiceOver: the readout and each mark in the owner's words.
        guard case .shown(let aberg) = page.model.readout(role: .map) else { return XCTFail("default resolves") }
        XCTAssertEqual(Model.spoken(aberg), [
            "Ludvig Aberg",
            "Pre-event · top 10: 53%, Kalshi hour-ending trade · 2026-10-08T00:00:00+00:00 · before opening day",
            "Final result · includes ties: Made top 10",
            "Reported score: −10, \(Self.captured)",
            "4 rounds reported",
        ].joined(separator: ". "))
        let marks = page.model.map.marks
        XCTAssertEqual(page.model.map.spoken(marks[0]),
                       "Ludvig Aberg. Pre-event · top 10: 53%, Kalshi hour-ending trade · 2026-10-08T00:00:00+00:00 · before opening day. Final result · includes ties: Made top 10")
        XCTAssertTrue(marks.allSatisfy { page.model.map.spoken($0).hasPrefix($0.original.name + ". ") }, "every dot is labelled by its whole name")
        XCTAssertEqual(GolfPlacementMapModel10868.bandSpoken(Self.mapBands[0]), "Made top 10. 2 priced golfers")
        XCTAssertEqual(GolfPlacementMapModel10868.bandSpoken(Self.mapBands[1]), "Missed top 10. 12 priced golfers")
        // No finish ladder or win slot this route never carried.
        for token in ["Top 5", "Top 20", "Pre-event win chance"] {
            XCTAssertFalse(Self.mentions(words, token), token)
        }
        XCTAssertTrue(Self.mentions(["Finish · Top 20"], "Top 20"), "positive control for the finish-ladder guard")
    }

    // MARK: Stories and parts

    func testTheStreamCardIdNamesOnlyTheMapAndTheMapCardIsTheSameEverywhere() throws {
        let model = Model(Self.input())
        XCTAssertEqual(model.story("expectations")?.card, .map)
        XCTAssertNil(model.story("missing"))
        let doubled = Model(Self.input(stories: [GolfPlacementStory10868(cardID: "expectations", card: .map),
                                                 GolfPlacementStory10868(cardID: "expectations", card: .map)]))
        XCTAssertNil(doubled.story("expectations"), "two links for one id name no single story")
        let history = Model(Self.input(stories: [GolfPlacementStory10868(cardID: "expectations", card: .history)]))
        XCTAssertNil(history.story("expectations"), "the anchor is never a stream story")

        // One card: the same parts on the page, in the stream and full size — no hidden second state.
        XCTAssertEqual(Page.mapParts, [.eyebrow, .title, .caption, .plot, .entry, .readout, .notice, .steps, .note])
        XCTAssertEqual(Set(Page.mapParts).count, GolfPlacementMapPart10868.allCases.count)
        let page = Self.page(Self.input(), log: Log())
        let stream = page.mapWords(at: .stream(Self.activation(Log())))
        let reader = Self.page(Self.input(), .reader(.map), log: Log()).mapWords(at: .reader)
        XCTAssertEqual(stream, reader, "the full card shows the same content with its exact callbacks")
        XCTAssertEqual(Array(stream.prefix(3)), ["Expectations, graded · top 10 including ties", "Which chances held up?",
                                                 "Each circle is a golfer's pre-event chance. The two bands show the final result."])
        let entry = try XCTUnwrap(stream.firstIndex(of: "Golfer on the map"))
        XCTAssertEqual(Array(stream[entry..<min(stream.count, entry + 4)]), ["Golfer on the map", "Ludvig Aberg", "Change", "Ludvig Aberg"])
        XCTAssertEqual(Page.minimumTarget, 44)
        XCTAssertEqual(Map.minimumTarget, 44)
    }

    // MARK: Measured layout

    func testEveryModeLaysOutAtCompactWideXXXLAndAX3WithoutCallingAnything() {
        let log = Log()
        let input = Self.input(historyRow: Self.named("Angel Ayora Fanegas"),
                               historySelection: Self.ref(Self.named("Angel Ayora Fanegas")),
                               mapSelected: Self.ref(Self.named("Shane Lowry")))
        let modes: [GolfPlacementEventPageMode10868] = [.page, .reader(.history), .reader(.map), .chooser(.history),
                                                        .chooser(.map), .catalogue, .original, .about]
        let layouts: [(CGFloat, DynamicTypeSize, UserInterfaceSizeClass)] = [
            (375, .large, .compact), (393, .large, .compact), (1030, .large, .regular),
            (375, .xxxLarge, .compact), (375, .accessibility3, .compact),
        ]
        for mode in modes {
            for (width, size, sizeClass) in layouts {
                let view = Self.page(input, mode, log: log, originals: Self.originals(selection: Self.named("Shane Lowry")))
                    .environment(\.horizontalSizeClass, sizeClass)
                let host = hostForMeasurement(view, at: size)
                host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                let fitted = host.sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude))
                XCTAssertLessThanOrEqual(fitted.width, width + 0.5, "\(mode) \(width) \(size) scrolls sideways")
                XCTAssertTrue(fitted.height.isFinite && fitted.height > 0, "\(mode) \(width) \(size)")
            }
        }
        XCTAssertTrue(log.events.isEmpty, "laying out calls nothing")

        // The map leaf alone: finite at every size, never wider than offered, and taller — never smaller — with larger text.
        let model = Model(input).map
        var heights: [CGFloat] = []
        for size in [DynamicTypeSize.large, .xxxLarge, .accessibility3] {
            let host = hostForMeasurement(Map(model: model).frame(width: 343), at: size)
            let fitted = host.sizeThatFits(in: CGSize(width: 343, height: .greatestFiniteMagnitude))
            XCTAssertTrue(fitted.height.isFinite && fitted.height > 0, "\(size)")
            XCTAssertLessThanOrEqual(fitted.width, 343.5, "\(size)")
            heights.append(fitted.height)
        }
        XCTAssertLessThanOrEqual(heights[0], heights[1])
        XCTAssertLessThan(heights[1], heights[2])
        // The page card with the map beside its readout on a wide screen is no taller than stacked on a phone.
        func card(_ width: CGFloat, _ sizeClass: UserInterfaceSizeClass) -> CGFloat {
            let host = hostForMeasurement(Self.page(input, .reader(.map), log: log).environment(\.horizontalSizeClass, sizeClass), at: .large)
            host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            return host.sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude)).height
        }
        XCTAssertLessThanOrEqual(card(1030, .regular), card(375, .compact))
        XCTAssertTrue(log.events.isEmpty)
    }
}

// MARK: - Retained evidence subset (generated from placementEvidence.json, unaltered values)

private let retainedEvidence = #"""
{"event":{"eventID":"golf-top10","name":"Open de España","baselineCutoff":"2026-10-08T00:00:00+00:00","exactStartAvailable":false,"actualCapturedAt":"2026-10-12T08:22:55.276141+00:00","defaultKey":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-LABE","aliases":{"Eugenio Lopez-Chacarra":"Eugenio Chacarra","Ludvig Aberg":"Ludvig Åberg","Jayden Schaper":"Jayden Schaper"},"historyPolicy":"Positive-volume hourly closes only; gaps over two hours stay open; no settlement endpoints.","baselinePolicy":"Last positive-volume hourly trade close in 24 hours before opening calendar day; exact first tee unavailable."},
"rows":[
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-LABE","name":"Ludvig Aberg","source":"kalshi","result":true,"score":"-10","roundCount":4,"mapY":7.0,"baseline":[0.53,45.66,1791417600,"2026-10-08T00:00:00+00:00"],"history":[[1791392400,0.68,1.43,0,"before","2026-10-07T17:00:00+00:00"],[1791417600,0.53,45.66,1,"before","2026-10-08T00:00:00+00:00"],[1791478800,0.45,21.39,2,"later","2026-10-08T17:00:00+00:00"],[1791496800,0.42,568.15,3,"later","2026-10-08T22:00:00+00:00"],[1791608400,0.27,7.04,4,"later","2026-10-10T05:00:00+00:00"],[1791655200,0.31,20.0,5,"later","2026-10-10T18:00:00+00:00"],[1791691200,0.25,6.92,6,"later","2026-10-11T04:00:00+00:00"],[1791734400,0.99,205.0,7,"later","2026-10-11T16:00:00+00:00"]],"rules":"If Ludvig Aberg finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-LABE","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":true,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Ludvig Aberg","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.9900","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-TAIK","name":"Thomas Aiken","source":"kalshi","result":false,"score":"+3","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Thomas Aiken finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-TAIK","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Thomas Aiken","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-KAPH","name":"Kiradech Aphibarnrat","source":"kalshi","result":false,"score":"-5","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Kiradech Aphibarnrat finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-KAPH","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Kiradech Aphibarnrat","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-MARM","name":"Marcus Armitage","source":"kalshi","result":false,"score":"+9","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Marcus Armitage finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-MARM","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Marcus Armitage","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-AAYO","name":"Angel Ayora Fanegas","source":"kalshi","result":false,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[[1791432000,0.24,39.56,0,"later","2026-10-08T04:00:00+00:00"],[1791630000,0.48,10.05,1,"later","2026-10-10T11:00:00+00:00"],[1791655200,0.81,39.56,2,"later","2026-10-10T18:00:00+00:00"],[1791676800,0.82,10.05,3,"later","2026-10-11T00:00:00+00:00"],[1791684000,0.85,2.32,3,"later","2026-10-11T02:00:00+00:00"]],"rules":"If Angel Ayora Fanegas finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-AAYO","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Angel Ayora Fanegas","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.8500","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-SBAI","name":"Sam Bairstow","source":"kalshi","result":false,"score":"-3","roundCount":4,"mapY":3.2,"baseline":[0.23,4.12,1791392400,"2026-10-07T17:00:00+00:00"],"history":[[1791392400,0.23,4.12,0,"before","2026-10-07T17:00:00+00:00"],[1791705600,0.05,18.75,1,"later","2026-10-11T08:00:00+00:00"]],"rules":"If Sam Bairstow finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-SBAI","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Sam Bairstow","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0500","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JBAL","name":"Jose Luis Ballester Barrio","source":"kalshi","result":false,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"If Jose Luis Ballester Barrio finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JBAL","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Jose Luis Ballester Barrio","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-GBAN","name":"Gonzalo Banos Ramos","source":"kalshi","result":false,"score":"+8","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Gonzalo Banos Ramos finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-GBAN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Gonzalo Banos Ramos","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DBRA","name":"Dan Bradbury","source":"kalshi","result":false,"score":"+2","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Dan Bradbury finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DBRA","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Dan Bradbury","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DBR","name":"Daniel Brown","source":"kalshi","result":true,"score":"-11","roundCount":4,"mapY":null,"baseline":null,"history":[[1791730800,0.99,209.0,0,"later","2026-10-11T15:00:00+00:00"]],"rules":"If Daniel Brown finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DBR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":true,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Daniel Brown","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.9900","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DBRY","name":"Davis Bryant","source":"kalshi","result":false,"score":"+2","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Davis Bryant finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DBRY","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Davis Bryant","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-RCAB","name":"Rafa Cabrera Bello","source":"kalshi","result":false,"score":"+2","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Rafa Cabrera Bello finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-RCAB","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Rafa Cabrera Bello","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JCAM","name":"Jorge Campillo","source":"kalshi","result":false,"score":"E","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Jorge Campillo finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JCAM","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Jorge Campillo","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-ICAN","name":"Ivan Cantero Gutierrez","source":"kalshi","result":false,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"If Ivan Cantero Gutierrez finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-ICAN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Ivan Cantero Gutierrez","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-FCEL","name":"Filippo Celli","source":"kalshi","result":false,"score":"+3","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Filippo Celli finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-FCEL","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Filippo Celli","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-TCLE","name":"Todd Clements","source":"kalshi","result":false,"score":"+3","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Todd Clements finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-TCLE","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Todd Clements","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-UCOU","name":"Ugo Coussaud","source":"kalshi","result":false,"score":"+6","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Ugo Coussaud finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-UCOU","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Ugo Coussaud","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-MCOU","name":"Martin Couvra","source":"kalshi","result":false,"score":"-9","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Martin Couvra finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-MCOU","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Martin Couvra","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-SCRO","name":"Sean Crocker","source":"kalshi","result":false,"score":"-8","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Sean Crocker finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-SCRO","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Sean Crocker","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-MDAF","name":"MJ Daffue","source":"kalshi","result":false,"score":"-4","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If MJ Daffue finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-MDAF","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"MJ Daffue","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JDAN","name":"Jens Dantorp","source":"kalshi","result":false,"score":"E","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Jens Dantorp finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JDAN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Jens Dantorp","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-GDEL","name":"Gregorio De Leo","source":"kalshi","result":false,"score":"+5","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Gregorio De Leo finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-GDEL","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Gregorio De Leo","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JDEA","name":"Joe Dean","source":"kalshi","result":true,"score":"-11","roundCount":4,"mapY":null,"baseline":null,"history":[[1791727200,0.99,0.67,0,"later","2026-10-11T14:00:00+00:00"],[1791734400,0.99,571.33,0,"later","2026-10-11T16:00:00+00:00"]],"rules":"If Joe Dean finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JDEA","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":true,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Joe Dean","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.9900","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-ADEL","name":"Alejandro Del Rey","source":"kalshi","result":false,"score":"-6","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Alejandro Del Rey finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-ADEL","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Alejandro Del Rey","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-SDES","name":"Sebastian Desoisa","source":"kalshi","result":false,"score":"+3","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Sebastian Desoisa finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-SDES","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Sebastian Desoisa","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-TDET","name":"Thomas Detry","source":"kalshi","result":false,"score":"+9","roundCount":2,"mapY":null,"baseline":null,"history":[[1791442800,0.25,190.02,0,"later","2026-10-08T07:00:00+00:00"],[1791723600,0.01,46.75,1,"later","2026-10-11T13:00:00+00:00"]],"rules":"If Thomas Detry finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-TDET","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Thomas Detry","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0100","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-WDIN","name":"Wenyi Ding","source":"kalshi","result":false,"score":"-4","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Wenyi Ding finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-WDIN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Wenyi Ding","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-HDUP","name":"Hennie Du Plessis","source":"kalshi","result":false,"score":"-6","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Hennie Du Plessis finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-HDUP","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Hennie Du Plessis","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-MELV","name":"Manuel Elvira","source":"kalshi","result":false,"score":"-4","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Manuel Elvira finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-MELV","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Manuel Elvira","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-NELV","name":"Nacho Elvira","source":"kalshi","result":false,"score":"E","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Nacho Elvira finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-NELV","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Nacho Elvira","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-EFER","name":"Ewen Ferguson","source":"kalshi","result":false,"score":"+5","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Ewen Ferguson finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-EFER","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Ewen Ferguson","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-RFIS","name":"Ross Fisher","source":"kalshi","result":false,"score":"+10","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Ross Fisher finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-RFIS","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Ross Fisher","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-GFOR","name":"Grant Forrest","source":"kalshi","result":true,"score":"-14","roundCount":4,"mapY":null,"baseline":null,"history":[[1791651600,0.88,2.0,0,"later","2026-10-10T17:00:00+00:00"],[1791734400,0.99,206.0,1,"later","2026-10-11T16:00:00+00:00"]],"rules":"If Grant Forrest finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-GFOR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":true,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Grant Forrest","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.9900","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DFRI","name":"Dylan Frittelli","source":"kalshi","result":false,"score":"+2","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Dylan Frittelli finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DFRI","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Dylan Frittelli","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-SGAR","name":"Sergio Garcia","source":"kalshi","result":false,"score":"-4","roundCount":4,"mapY":2.6500000000000004,"baseline":[0.31,3.07,1791392400,"2026-10-07T17:00:00+00:00"],"history":[[1791392400,0.31,3.07,0,"before","2026-10-07T17:00:00+00:00"],[1791630000,0.37,7.76,1,"later","2026-10-10T11:00:00+00:00"]],"rules":"If Sergio Garcia finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-SGAR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Sergio Garcia","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.3700","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-AGAR","name":"Alfredo Garcia-Heredia","source":"kalshi","result":false,"score":"-5","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Alfredo Garcia-Heredia finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-AGAR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Alfredo Garcia-Heredia","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DGAV","name":"Daniel Gavins","source":"kalshi","result":false,"score":"+10","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Daniel Gavins finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DGAV","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Daniel Gavins","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JGIR","name":"Joel Girrbach","source":"kalshi","result":true,"score":"-10","roundCount":4,"mapY":null,"baseline":null,"history":[[1791734400,0.99,205.0,0,"later","2026-10-11T16:00:00+00:00"]],"rules":"If Joel Girrbach finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JGIR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":true,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Joel Girrbach","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.9900","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-RGOU","name":"Ricardo Gouveia","source":"kalshi","result":false,"score":"+3","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Ricardo Gouveia finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-RGOU","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Ricardo Gouveia","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JGUE","name":"Julien Guerrier","source":"kalshi","result":false,"score":"+4","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Julien Guerrier finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JGUE","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Julien Guerrier","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-OGUI","name":"Oihan Guillamoundeguy","source":"kalshi","result":false,"score":"+4","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Oihan Guillamoundeguy finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-OGUI","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Oihan Guillamoundeguy","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JGUM","name":"Jordan Gumberg","source":"kalshi","result":false,"score":"+7","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Jordan Gumberg finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JGUM","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Jordan Gumberg","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-THAT","name":"Tyrrell Hatton","source":"kalshi","result":false,"score":"+6","roundCount":2,"mapY":1.55,"baseline":[0.4,2.39,1791392400,"2026-10-07T17:00:00+00:00"],"history":[[1791392400,0.4,2.39,0,"before","2026-10-07T17:00:00+00:00"],[1791630000,0.01,93.51,1,"later","2026-10-10T11:00:00+00:00"],[1791723600,0.01,46.75,2,"later","2026-10-11T13:00:00+00:00"]],"rules":"If Tyrrell Hatton finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-THAT","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Tyrrell Hatton","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0100","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-MHEL","name":"Marcus Helligkilde","source":"kalshi","result":false,"score":"E","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Marcus Helligkilde finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-MHEL","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Marcus Helligkilde","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-AHID","name":"Angel Hidalgo","source":"kalshi","result":false,"score":"-5","roundCount":4,"mapY":1.0,"baseline":[0.14,33.68,1791403200,"2026-10-07T20:00:00+00:00"],"history":[[1791403200,0.14,33.68,0,"before","2026-10-07T20:00:00+00:00"],[1791612000,0.09,272.63,1,"later","2026-10-10T06:00:00+00:00"]],"rules":"If Angel Hidalgo finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-AHID","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Angel Hidalgo","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0900","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-CHIL","name":"Calum Hill","source":"kalshi","result":false,"score":"+4","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Calum Hill finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-CHIL","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Calum Hill","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DHIL","name":"Daniel Hillier","source":"kalshi","result":false,"score":"-6","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Daniel Hillier finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DHIL","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Daniel Hillier","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-NHOJ","name":"Nicolai Hojgaard","source":"kalshi","result":false,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"If Nicolai Hojgaard finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-NHOJ","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Nicolai Hojgaard","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-MHOL","name":"Michael Hollick","source":"kalshi","result":false,"score":"+7","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Michael Hollick finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-MHOL","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Michael Hollick","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-RHOS","name":"Rikuya Hoshino","source":"kalshi","result":false,"score":"+1","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Rikuya Hoshino finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-RHOS","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Rikuya Hoshino","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-SJIM","name":"Sergio Jimenez Romero","source":"kalshi","result":false,"score":"+2","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Sergio Jimenez Romero finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-SJIM","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Sergio Jimenez Romero","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-RJOH","name":"Ryggs Johnston","source":"kalshi","result":false,"score":"+8","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Ryggs Johnston finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-RJOH","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Ryggs Johnston","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-MJOR","name":"Matthew Jordan","source":"kalshi","result":false,"score":"-6","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Matthew Jordan finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-MJOR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Matthew Jordan","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-YKAT","name":"Yuto Katsuragawa","source":"kalshi","result":false,"score":"+3","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Yuto Katsuragawa finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-YKAT","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Yuto Katsuragawa","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-NKIM","name":"Nathan Kimsey","source":"kalshi","result":false,"score":"-3","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Nathan Kimsey finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-NKIM","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Nathan Kimsey","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JKO","name":"Jeong-Weon Ko","source":"kalshi","result":false,"score":"+6","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Jeong-Weon Ko finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JKO","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Jeong-Weon Ko","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-KKOB","name":"Kazuma Kobori","source":"kalshi","result":false,"score":"+7","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Kazuma Kobori finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-KKOB","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Kazuma Kobori","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JKRU","name":"Jacques Kruyswijk","source":"kalshi","result":false,"score":"+7","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Jacques Kruyswijk finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JKRU","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Jacques Kruyswijk","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-FLAC","name":"Frederic Lacroix","source":"kalshi","result":false,"score":"E","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Frederic Lacroix finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-FLAC","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Frederic Lacroix","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JLAG","name":"Joakim Lagergren","source":"kalshi","result":false,"score":"-9","roundCount":4,"mapY":1.55,"baseline":[0.18,26.26,1791403200,"2026-10-07T20:00:00+00:00"],"history":[[1791403200,0.18,26.26,0,"before","2026-10-07T20:00:00+00:00"],[1791421200,0.17,83.39,1,"later","2026-10-08T01:00:00+00:00"],[1791464400,0.21,9.02,2,"later","2026-10-08T13:00:00+00:00"],[1791673200,0.6,5.0,3,"later","2026-10-10T23:00:00+00:00"],[1791684000,0.6,3.24,4,"later","2026-10-11T02:00:00+00:00"],[1791702000,0.53,1050.38,5,"later","2026-10-11T07:00:00+00:00"],[1791734400,0.03,411.0,6,"later","2026-10-11T16:00:00+00:00"]],"rules":"If Joakim Lagergren finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JLAG","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Joakim Lagergren","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0300","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-RLAN","name":"Romain Langasque","source":"kalshi","result":false,"score":"-2","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Romain Langasque finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-RLAN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Romain Langasque","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-FLAP","name":"Francesco Laporta","source":"kalshi","result":false,"score":"-5","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Francesco Laporta finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-FLAP","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Francesco Laporta","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-PLAR","name":"Pablo Larrazabal","source":"kalshi","result":false,"score":"-3","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Pablo Larrazabal finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-PLAR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Pablo Larrazabal","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DLAW","name":"David Law","source":"kalshi","result":false,"score":"+4","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If David Law finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DLAW","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"David Law","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-TLAW","name":"Thriston Lawrence","source":"kalshi","result":false,"score":"-8","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Thriston Lawrence finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-TLAW","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Thriston Lawrence","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-NLEM","name":"Niklas Lemke","source":"kalshi","result":false,"score":"-7","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Niklas Lemke finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-NLEM","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Niklas Lemke","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-MLIN","name":"Mikael Lindberg","source":"kalshi","result":false,"score":"-4","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Mikael Lindberg finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-MLIN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Mikael Lindberg","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-OLIN","name":"Oliver Lindell","source":"kalshi","result":true,"score":"-10","roundCount":4,"mapY":null,"baseline":null,"history":[[1791673200,0.46,5.0,0,"later","2026-10-10T23:00:00+00:00"],[1791684000,0.46,4.18,1,"later","2026-10-11T02:00:00+00:00"],[1791734400,0.99,205.0,2,"later","2026-10-11T16:00:00+00:00"]],"rules":"If Oliver Lindell finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-OLIN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":true,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Oliver Lindell","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.9900","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-LLIS","name":"Luke List","source":"kalshi","result":false,"score":"-4","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Luke List finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-LLIS","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Luke List","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-ELOP","name":"Eugenio Lopez-Chacarra","source":"kalshi","result":true,"score":"-13","roundCount":4,"mapY":7.0,"baseline":[0.33,144.94,1791417600,"2026-10-08T00:00:00+00:00"],"history":[[1791392400,0.45,2.13,0,"before","2026-10-07T17:00:00+00:00"],[1791417600,0.33,144.94,1,"before","2026-10-08T00:00:00+00:00"],[1791475200,0.75,32.76,2,"later","2026-10-08T16:00:00+00:00"],[1791543600,0.64,401.45,3,"later","2026-10-09T11:00:00+00:00"],[1791565200,0.55,200.0,4,"later","2026-10-09T17:00:00+00:00"],[1791608400,0.75,2.62,5,"later","2026-10-10T05:00:00+00:00"],[1791612000,0.75,45.45,5,"later","2026-10-10T06:00:00+00:00"],[1791630000,0.75,6.55,6,"later","2026-10-10T11:00:00+00:00"],[1791684000,0.66,4.43,7,"later","2026-10-11T02:00:00+00:00"],[1791691200,0.6,10.98,7,"later","2026-10-11T04:00:00+00:00"],[1791730800,0.99,205.0,8,"later","2026-10-11T15:00:00+00:00"]],"rules":"If Eugenio Lopez-Chacarra finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-ELOP","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":true,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Eugenio Lopez-Chacarra","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.9900","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-SLOW","name":"Shane Lowry","source":"kalshi","result":false,"score":"-8","roundCount":4,"mapY":1.0,"baseline":[0.38,126.1,1791417600,"2026-10-08T00:00:00+00:00"],"history":[[1791410400,0.38,100.88,0,"before","2026-10-07T22:00:00+00:00"],[1791417600,0.38,126.1,0,"before","2026-10-08T00:00:00+00:00"],[1791630000,0.99,0.2,1,"later","2026-10-10T11:00:00+00:00"],[1791651600,0.24,7.69,2,"later","2026-10-10T17:00:00+00:00"]],"rules":"If Shane Lowry finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-SLOW","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Shane Lowry","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.2400","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JLUI","name":"Joost Luiten","source":"kalshi","result":false,"score":"-8","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Joost Luiten finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JLUI","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Joost Luiten","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-MMAN","name":"Matteo Manassero","source":"kalshi","result":false,"score":"E","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Matteo Manassero finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-MMAN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Matteo Manassero","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-RMAN","name":"Richard Mansell","source":"kalshi","result":false,"score":"+3","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Richard Mansell finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-RMAN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Richard Mansell","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-SMAZ","name":"Stefano Mazzoli","source":"kalshi","result":false,"score":"-8","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Stefano Mazzoli finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-SMAZ","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Stefano Mazzoli","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-TMCK","name":"Tom McKibbin","source":"kalshi","result":false,"score":"+3","roundCount":2,"mapY":3.2,"baseline":[0.41,2.34,1791392400,"2026-10-07T17:00:00+00:00"],"history":[[1791392400,0.41,2.34,0,"before","2026-10-07T17:00:00+00:00"],[1791630000,0.01,93.51,1,"later","2026-10-10T11:00:00+00:00"]],"rules":"If Tom McKibbin finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-TMCK","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Tom McKibbin","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0100","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-AMER","name":"Adrian Meronk","source":"kalshi","result":false,"score":"+5","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Adrian Meronk finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-AMER","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Adrian Meronk","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DMIC","name":"David Micheluzzi","source":"kalshi","result":false,"score":"+3","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If David Micheluzzi finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DMIC","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"David Micheluzzi","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-GMIG","name":"Guido Migliozzi","source":"kalshi","result":false,"score":"+9","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Guido Migliozzi finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-GMIG","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Guido Migliozzi","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-FMOL","name":"Francesco Molinari","source":"kalshi","result":false,"score":"-7","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Francesco Molinari finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-FMOL","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Francesco Molinari","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JMOR","name":"James Morrison","source":"kalshi","result":false,"score":"+5","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If James Morrison finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JMOR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"James Morrison","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DNAI","name":"Dylan Naidoo","source":"kalshi","result":false,"score":"+15","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Dylan Naidoo finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DNAI","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Dylan Naidoo","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-ANOR","name":"Alex Noren","source":"kalshi","result":false,"score":"+1","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Alex Noren finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-ANOR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Alex Noren","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-NNOR","name":"Niklas Norgaard","source":"kalshi","result":false,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"If Niklas Norgaard finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-NNOR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Niklas Norgaard","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JOLE","name":"Jacob Skov Olesen","source":"kalshi","result":true,"score":"-12","roundCount":4,"mapY":null,"baseline":null,"history":[[1791421200,0.23,61.88,0,"later","2026-10-08T01:00:00+00:00"],[1791630000,0.59,4.94,1,"later","2026-10-10T11:00:00+00:00"],[1791691200,0.93,4.94,2,"later","2026-10-11T04:00:00+00:00"],[1791730800,0.99,206.0,3,"later","2026-10-11T15:00:00+00:00"]],"rules":"If Jacob Skov Olesen finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JOLE","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":true,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Jacob Skov Olesen","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.9900","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-AOTA","name":"Adrian Otaegui","source":"kalshi","result":true,"score":"-10","roundCount":4,"mapY":null,"baseline":null,"history":[[1791734400,0.99,205.0,0,"later","2026-10-11T16:00:00+00:00"]],"rules":"If Adrian Otaegui finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-AOTA","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":true,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Adrian Otaegui","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.9900","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-RPAR","name":"Renato Paratore","source":"kalshi","result":false,"score":"+1","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Renato Paratore finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-RPAR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Renato Paratore","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JPAU","name":"Jeremy Paul","source":"kalshi","result":false,"score":"+2","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Jeremy Paul finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JPAU","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Jeremy Paul","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-MPEN","name":"Marco Penge","source":"kalshi","result":false,"score":"-7","roundCount":4,"mapY":1.0,"baseline":[0.24,39.56,1791403200,"2026-10-07T20:00:00+00:00"],"history":[[1791403200,0.24,39.56,0,"before","2026-10-07T20:00:00+00:00"]],"rules":"If Marco Penge finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-MPEN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Marco Penge","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.2400","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-EPEP","name":"Eddie Pepperell","source":"kalshi","result":false,"score":"E","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Eddie Pepperell finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-EPEP","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Eddie Pepperell","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-VPER","name":"Victor Perez","source":"kalshi","result":true,"score":"-13","roundCount":4,"mapY":null,"baseline":null,"history":[[1791734400,0.99,205.0,0,"later","2026-10-11T16:00:00+00:00"]],"rules":"If Victor Perez finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-VPER","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":true,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Victor Perez","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.9900","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-YPRE","name":"Yurav Premlall","source":"kalshi","result":false,"score":"+11","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Yurav Premlall finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-YPRE","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Yurav Premlall","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DPUI","name":"David Puig","source":"kalshi","result":false,"score":"-4","roundCount":4,"mapY":1.55,"baseline":[0.26,36.56,1791406800,"2026-10-07T21:00:00+00:00"],"history":[[1791392400,0.42,2.28,0,"before","2026-10-07T17:00:00+00:00"],[1791406800,0.26,36.56,1,"before","2026-10-07T21:00:00+00:00"],[1791630000,0.26,3.65,2,"later","2026-10-10T11:00:00+00:00"]],"rules":"If David Puig finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DPUI","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"David Puig","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.2600","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DRAV","name":"David Ravetto","source":"kalshi","result":false,"score":"+5","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If David Ravetto finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DRAV","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"David Ravetto","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-PREE","name":"Patrick Reed","source":"kalshi","result":false,"score":"+2","roundCount":2,"mapY":2.1,"baseline":[0.31,76.92,1791417600,"2026-10-08T00:00:00+00:00"],"history":[[1791403200,0.32,29.83,0,"before","2026-10-07T20:00:00+00:00"],[1791417600,0.31,76.92,1,"before","2026-10-08T00:00:00+00:00"],[1791630000,0.01,46.75,2,"later","2026-10-10T11:00:00+00:00"],[1791723600,0.01,46.75,3,"later","2026-10-11T13:00:00+00:00"]],"rules":"If Patrick Reed finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-PREE","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Patrick Reed","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0100","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JRIT","name":"JC Ritchie","source":"kalshi","result":false,"score":"E","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If JC Ritchie finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JRIT","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"JC Ritchie","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-BROB","name":"Brandon Robinson-Thompson","source":"kalshi","result":false,"score":"-1","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Brandon Robinson-Thompson finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-BROB","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Brandon Robinson-Thompson","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DROD","name":"Daniel Rodrigues","source":"kalshi","result":false,"score":"+5","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Daniel Rodrigues finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DROD","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Daniel Rodrigues","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-AROD","name":"Alejandro Rodriguez Andreu","source":"kalshi","result":false,"score":"+2","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Alejandro Rodriguez Andreu finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-AROD","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Alejandro Rodriguez Andreu","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-SROD","name":"Sebastian Rodriguez Garcia","source":"kalshi","result":false,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"If Sebastian Rodriguez Garcia finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-SROD","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Sebastian Rodriguez Garcia","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JROS","name":"Justin Rose","source":"kalshi","result":false,"score":"+2","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Justin Rose finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JROS","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Justin Rose","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-TROS","name":"Thomas Rosenmueller","source":"kalshi","result":false,"score":"+2","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Thomas Rosenmueller finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-TROS","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Thomas Rosenmueller","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-AROZ","name":"Antoine Rozner","source":"kalshi","result":false,"score":"-7","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Antoine Rozner finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-AROZ","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Antoine Rozner","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JSAL","name":"Juan Salama","source":"kalshi","result":false,"score":"+7","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Juan Salama finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JSAL","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Juan Salama","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JSCH","name":"Jayden Schaper","source":"kalshi","result":false,"score":"+2","roundCount":2,"mapY":2.1,"baseline":[0.19,24.9,1791403200,"2026-10-07T20:00:00+00:00"],"history":[[1791403200,0.19,24.9,0,"before","2026-10-07T20:00:00+00:00"]],"rules":"If Jayden Schaper finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JSCH","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Jayden Schaper","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.1900","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-BSCH","name":"Ben Schmidt","source":"kalshi","result":false,"score":"+2","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Ben Schmidt finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-BSCH","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Ben Schmidt","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-FSCH","name":"Freddy Schott","source":"kalshi","result":false,"score":"+3","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Freddy Schott finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-FSCH","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Freddy Schott","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JSCR","name":"Jason Scrivener","source":"kalshi","result":false,"score":"E","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Jason Scrivener finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JSCR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Jason Scrivener","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JSEN","name":"Jack Senior","source":"kalshi","result":false,"score":"+5","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Jack Senior finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JSEN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Jack Senior","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-MSIE","name":"Marcel Siem","source":"kalshi","result":false,"score":"+9","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Marcel Siem finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-MSIE","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Marcel Siem","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-ESMY","name":"Elvis Smylie","source":"kalshi","result":false,"score":"+3","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Elvis Smylie finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-ESMY","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Elvis Smylie","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-SSOD","name":"Sebastian Soderberg","source":"kalshi","result":false,"score":"+2","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Sebastian Soderberg finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-SSOD","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Sebastian Soderberg","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-MSTE","name":"Maximilian Steinlechner","source":"kalshi","result":false,"score":"+6","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Maximilian Steinlechner finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-MSTE","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Maximilian Steinlechner","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-RSTE","name":"Richard Sterne","source":"kalshi","result":false,"score":"+5","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Richard Sterne finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-RSTE","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Richard Sterne","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-MSTE2","name":"Michael Stewart","source":"kalshi","result":false,"score":"-2","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Michael Stewart finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-MSTE2","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Michael Stewart","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-BSTO","name":"Brandon Stone","source":"kalshi","result":false,"score":"+4","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Brandon Stone finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-BSTO","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Brandon Stone","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-OSTR","name":"Ockie Strydom","source":"kalshi","result":false,"score":"+4","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Ockie Strydom finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-OSTR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Ockie Strydom","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-ASUL","name":"Andy Sullivan","source":"kalshi","result":false,"score":"+9","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Andy Sullivan finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-ASUL","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Andy Sullivan","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-CSYM","name":"Connor Syme","source":"kalshi","result":false,"score":"-4","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Connor Syme finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-CSYM","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Connor Syme","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-TVAI","name":"Tom Vaillant","source":"kalshi","result":false,"score":"-7","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Tom Vaillant finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-TVAI","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Tom Vaillant","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-SVAL","name":"Sami Valimaki","source":"kalshi","result":false,"score":"-8","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Sami Valimaki finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-SVAL","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Sami Valimaki","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DVAN","name":"Darius Van Driel","source":"kalshi","result":false,"score":"-3","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Darius Van Driel finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DVAN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Darius Van Driel","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JVEE","name":"Johannes Veerman","source":"kalshi","result":false,"score":"+5","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Johannes Veerman finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JVEE","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Johannes Veerman","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-QVID","name":"Quim Vidal","source":"kalshi","result":false,"score":"-4","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Quim Vidal finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-QVID","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Quim Vidal","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-NVON","name":"Nicolai Von Dellingshausen","source":"kalshi","result":false,"score":"-3","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Nicolai Von Dellingshausen finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-NVON","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Nicolai Von Dellingshausen","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-PWAR","name":"Paul Waring","source":"kalshi","result":false,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"If Paul Waring finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-PWAR","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Paul Waring","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-BWAT","name":"Bubba Watson","source":"kalshi","result":false,"score":"+3","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Bubba Watson finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-BWAT","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Bubba Watson","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-BWIE","name":"Bernd Wiesberger","source":"kalshi","result":false,"score":"-8","roundCount":4,"mapY":2.6500000000000004,"baseline":[0.2,4.73,1791392400,"2026-10-07T17:00:00+00:00"],"history":[[1791392400,0.2,4.73,0,"before","2026-10-07T17:00:00+00:00"]],"rules":"If Bernd Wiesberger finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-BWIE","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Bernd Wiesberger","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.2000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-DWIL","name":"Danny Willett","source":"kalshi","result":false,"score":"+10","roundCount":2,"mapY":null,"baseline":null,"history":[],"rules":"If Danny Willett finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-DWIL","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Danny Willett","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-JWIN","name":"Jeff Winther","source":"kalshi","result":false,"score":"-6","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Jeff Winther finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-JWIN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Jeff Winther","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-AWU","name":"Ashun Wu","source":"kalshi","result":false,"score":"-3","roundCount":4,"mapY":null,"baseline":null,"history":[],"rules":"If Ashun Wu finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-AWU","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Ashun Wu","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"espana-kalshi:KXDPWTTOP10-OPDEPBM26-ZYAN","name":"Zhou Yanhan","source":"kalshi","result":false,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"If Zhou Yanhan finishes in the top 10 (including ties) in the 2026 Open de España presented by Madrid, then the market resolves to Yes.\nIf a golfer forfeits, withdraws, or doesn't participate:\nPrior to teeing off: Market resolves to Fair Market Price\nAfter teeing off: Market resolves to No\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners.","final":{"id":"KXDPWTTOP10-OPDEPBM26-ZYAN","_market_id":"KXDPWTTOP10-OPDEPBM26","probability":null,"is_winner":false,"source":"kalshi","market_name":"Open de España · Top 10, including ties","outcome_name":"Zhou Yanhan","resolution_source":"venue_finalized","observed_at":null},"lastPrice":"0.0000","original":null},
{"key":"field-64366411.json:245877572","name":"Adrian Otaegui","source":"polymarket","result":true,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties. Otherwise, this market will resolve to \"No\". If final results are not announced by October 18, 2026 at 11:59PM ET this market will resolve to \"No\". The primary resolution source will be the official results published by the DP World Tour website (https://www.europeantour.com/).","final":{"id":245877572,"_market_id":64366411,"probability":1.0,"is_winner":true,"source":"polymarket","market_name":"DP World Tour: Open de Espana Top 10","outcome_name":"Adrian Otaegui","resolution_source":"api_settlement","observed_at":"2026-10-12T05:47:20.049168+00:00"},"lastPrice":null,"original":null},
{"key":"field-64366411.json:245877573","name":"Daniel Brown","source":"polymarket","result":true,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties. Otherwise, this market will resolve to \"No\". If final results are not announced by October 18, 2026 at 11:59PM ET this market will resolve to \"No\". The primary resolution source will be the official results published by the DP World Tour website (https://www.europeantour.com/).","final":{"id":245877573,"_market_id":64366411,"probability":1.0,"is_winner":true,"source":"polymarket","market_name":"DP World Tour: Open de Espana Top 10","outcome_name":"Daniel Brown","resolution_source":"api_settlement","observed_at":"2026-10-12T05:47:20.049168+00:00"},"lastPrice":null,"original":null},
{"key":"field-64366411.json:245877574","name":"Eugenio Lopez-Chacarra","source":"polymarket","result":true,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties. Otherwise, this market will resolve to \"No\". If final results are not announced by October 18, 2026 at 11:59PM ET this market will resolve to \"No\". The primary resolution source will be the official results published by the DP World Tour website (https://www.europeantour.com/).","final":{"id":245877574,"_market_id":64366411,"probability":1.0,"is_winner":true,"source":"polymarket","market_name":"DP World Tour: Open de Espana Top 10","outcome_name":"Eugenio Lopez-Chacarra","resolution_source":"api_settlement","observed_at":"2026-10-12T05:47:20.049168+00:00"},"lastPrice":null,"original":null},
{"key":"field-64366411.json:245877575","name":"Grant Forrest","source":"polymarket","result":true,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties. Otherwise, this market will resolve to \"No\". If final results are not announced by October 18, 2026 at 11:59PM ET this market will resolve to \"No\". The primary resolution source will be the official results published by the DP World Tour website (https://www.europeantour.com/).","final":{"id":245877575,"_market_id":64366411,"probability":1.0,"is_winner":true,"source":"polymarket","market_name":"DP World Tour: Open de Espana Top 10","outcome_name":"Grant Forrest","resolution_source":"api_settlement","observed_at":"2026-10-12T05:47:20.049168+00:00"},"lastPrice":null,"original":null},
{"key":"field-64366411.json:245877576","name":"Jacob Skov Olesen","source":"polymarket","result":true,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties. Otherwise, this market will resolve to \"No\". If final results are not announced by October 18, 2026 at 11:59PM ET this market will resolve to \"No\". The primary resolution source will be the official results published by the DP World Tour website (https://www.europeantour.com/).","final":{"id":245877576,"_market_id":64366411,"probability":1.0,"is_winner":true,"source":"polymarket","market_name":"DP World Tour: Open de Espana Top 10","outcome_name":"Jacob Skov Olesen","resolution_source":"api_settlement","observed_at":"2026-10-12T05:47:20.049168+00:00"},"lastPrice":null,"original":null},
{"key":"field-64366411.json:245877577","name":"Joel Girrbach","source":"polymarket","result":true,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties. Otherwise, this market will resolve to \"No\". If final results are not announced by October 18, 2026 at 11:59PM ET this market will resolve to \"No\". The primary resolution source will be the official results published by the DP World Tour website (https://www.europeantour.com/).","final":{"id":245877577,"_market_id":64366411,"probability":1.0,"is_winner":true,"source":"polymarket","market_name":"DP World Tour: Open de Espana Top 10","outcome_name":"Joel Girrbach","resolution_source":"api_settlement","observed_at":"2026-10-12T05:47:20.049168+00:00"},"lastPrice":null,"original":null},
{"key":"field-64366411.json:245877578","name":"Joseph Dean","source":"polymarket","result":true,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties. Otherwise, this market will resolve to \"No\". If final results are not announced by October 18, 2026 at 11:59PM ET this market will resolve to \"No\". The primary resolution source will be the official results published by the DP World Tour website (https://www.europeantour.com/).","final":{"id":245877578,"_market_id":64366411,"probability":1.0,"is_winner":true,"source":"polymarket","market_name":"DP World Tour: Open de Espana Top 10","outcome_name":"Joseph Dean","resolution_source":"api_settlement","observed_at":"2026-10-12T05:47:20.049168+00:00"},"lastPrice":null,"original":null},
{"key":"field-64366411.json:245877579","name":"Ludvig Aaberg","source":"polymarket","result":true,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties. Otherwise, this market will resolve to \"No\". If final results are not announced by October 18, 2026 at 11:59PM ET this market will resolve to \"No\". The primary resolution source will be the official results published by the DP World Tour website (https://www.europeantour.com/).","final":{"id":245877579,"_market_id":64366411,"probability":1.0,"is_winner":true,"source":"polymarket","market_name":"DP World Tour: Open de Espana Top 10","outcome_name":"Ludvig Aaberg","resolution_source":"api_settlement","observed_at":"2026-10-12T05:47:20.049168+00:00"},"lastPrice":null,"original":null},
{"key":"field-64366411.json:245877580","name":"Oliver Lindell","source":"polymarket","result":true,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties. Otherwise, this market will resolve to \"No\". If final results are not announced by October 18, 2026 at 11:59PM ET this market will resolve to \"No\". The primary resolution source will be the official results published by the DP World Tour website (https://www.europeantour.com/).","final":{"id":245877580,"_market_id":64366411,"probability":1.0,"is_winner":true,"source":"polymarket","market_name":"DP World Tour: Open de Espana Top 10","outcome_name":"Oliver Lindell","resolution_source":"api_settlement","observed_at":"2026-10-12T05:47:20.049168+00:00"},"lastPrice":null,"original":null},
{"key":"field-64366411.json:245877581","name":"Victor Perez","source":"polymarket","result":true,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties. Otherwise, this market will resolve to \"No\". If final results are not announced by October 18, 2026 at 11:59PM ET this market will resolve to \"No\". The primary resolution source will be the official results published by the DP World Tour website (https://www.europeantour.com/).","final":{"id":245877581,"_market_id":64366411,"probability":1.0,"is_winner":true,"source":"polymarket","market_name":"DP World Tour: Open de Espana Top 10","outcome_name":"Victor Perez","resolution_source":"api_settlement","observed_at":"2026-10-12T05:47:20.049168+00:00"},"lastPrice":null,"original":null},
{"key":"field-64366411.json:0","name":"Alejandro Rodriguez","source":"polymarket","result":false,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties. Otherwise, this market will resolve to \"No\". If final results are not announced by October 18, 2026 at 11:59PM ET this market will resolve to \"No\". The primary resolution source will be the official results published by the DP World Tour website (https://www.europeantour.com/).","final":{"id":244621746,"_market_id":64366411,"probability":0.0,"is_winner":false,"source":"polymarket","market_name":"DP World Tour: Open de Espana Top 10","outcome_name":"Alejandro Rodriguez","resolution_source":"api_settlement","observed_at":"2026-10-12T05:47:20.049168+00:00"},"lastPrice":null,"original":{"id":244621746,"probability":0.0,"category":"field","observed_at":"2026-10-09T20:11:37.765251+00:00"}},
{"key":"field-64366411.json:1","name":"Ben Schmidt","source":"polymarket","result":false,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties. Otherwise, this market will resolve to \"No\". If final results are not announced by October 18, 2026 at 11:59PM ET this market will resolve to \"No\". The primary resolution source will be the official results published by the DP World Tour website (https://www.europeantour.com/).","final":{"id":244621747,"_market_id":64366411,"probability":0.0,"is_winner":false,"source":"polymarket","market_name":"DP World Tour: Open de Espana Top 10","outcome_name":"Ben Schmidt","resolution_source":"api_settlement","observed_at":"2026-10-12T05:47:20.049168+00:00"},"lastPrice":null,"original":{"id":244621747,"probability":0.0,"category":"field","observed_at":"2026-10-09T20:12:38.034691+00:00"}},
{"key":"field-64366411.json:2","name":"Daniel Bradbury","source":"polymarket","result":false,"score":null,"roundCount":0,"mapY":null,"baseline":null,"history":[],"rules":"This market will resolve to \"Yes\" if the listed player finishes in the top 10 at the 2026 Open de Espana tournament, including ties. Otherwise, this market will resolve to \"No\". If final results are not announced by October 18, 2026 at 11:59PM ET this market will resolve to \"No\". The primary resolution source will be the official results published by the DP World Tour website (https://www.europeantour.com/).","final":{"id":244621748,"_market_id":64366411,"probability":0.0,"is_winner":false,"source":"polymarket","market_name":"DP World Tour: Open de Espana Top 10","outcome_name":"Daniel Bradbury","resolution_source":"api_settlement","observed_at":"2026-10-12T05:47:20.049168+00:00"},"lastPrice":null,"original":{"id":244621748,"probability":0.0,"category":"field","observed_at":"2026-10-09T20:12:49.206211+00:00"}}
]}
"""#
