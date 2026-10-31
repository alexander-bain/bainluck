import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the economics EARNINGS page (route `economics`): the paired
/// headline (the dated pre-report chance to beat a fixed threshold beside the
/// company-reported diluted EPS, in different units, each with its own date
/// and phase), the earnings-versus-threshold card on a USD-per-share axis
/// from zero with the baseline chance beside it, the shared probability
/// history with all retained Yes observations, the original's Details and
/// catalogue with its rules and source, compact Info, the story stream and its
/// once-only holds, the owner's reader order, Back, and one phase-admitted
/// bundle behind every surface.
///
/// PREPARED, NOT RUN. Only `xcrun swiftc -parse` was run on this file.
///
/// RETAINED DATA (evidence only, never an app binding), under the approved
/// `totals-final-forecast-binding-20261024/prototype/src/`:
///   • `earnings-capture.json` (sha256
///     0847702f668965e3cc561d5594605933c16ce248587250c5ec90cea16c2eb80e) —
///     every field, the rules text verbatim and all 308 history observations
///     with every t and p exactly as retained;
///   • `atlas.json` (sha256
///     ff1fbc3ec9c491d3d402642ac7b8cf42a59138f3f655af213feaf44b0ef200a5) —
///     the economics event's key, label, source and detail, and its one
///     original row, every field verbatim;
///   • `fieldHeaders.json` (sha256
///     3a1c10a7dc1809be5e9d6a4c10791e39b3df14743b4d1b5bfbf687a82ab3adf5) —
///     the economics header entry, verbatim (its older notes predate the newer
///     capture and are never shown).
/// `retainedCapture` below is generated mechanically from those files by a
/// script outside the repository and spliced in by script; nothing is typed by
/// hand and nothing is sampled, deduplicated or reduced.
///
/// CONSTRUCTED here (the OWNER's preparation, test-side only): every word,
/// percentage, money and date label, the device time zone, the pre-report
/// observation (the reference's latest-strictly-before-publication rule,
/// ported test-side), the USD axis, its ticks and placements, the 10-cent
/// relation, the history ids, ticks and notes, the stream, the reader order,
/// Info sections and the per-phase bundles. The report-only bundle withholds
/// the provider's resolution deliberately: it is a rehearsal, not captured
/// evidence of an unresolved market, and no phase claim is made from it.
///
/// NOT claimed: native compilation or execution, rendered appearance, matched
/// 375×667 / 393×852 / wide / XXXL / AX3 visual acceptance, focus, scroll
/// restoration, touch, scrubbing, VoiceOver on a device, mounted app bindings,
/// genuine pre-report or report-only captures, or TestFlight. The hosted
/// measurements below are prepared checks of sizes and that laying out calls
/// nothing; none has run.
@MainActor
final class EarningsEventPagePresentation10868Tests: XCTestCase {
    typealias Page = EarningsEventPagePresentation10868
    typealias Model = EarningsEventPageModel10868
    typealias Input = EarningsEventPageInput10868
    typealias Bundle = EarningsEventPageBundle10868
    typealias Phase = EarningsEventPagePhase10868
    typealias Card = EarningsEventPageCard10868
    typealias Mode = EarningsEventPageMode10868
    typealias Reading = EarningsDatedReading10868
    typealias Headline = EarningsHeadlineModel10868
    typealias Comparison = EarningsComparisonModel10868
    typealias Geometry = EarningsComparisonGeometry10868
    typealias Rule = EarningsReadingRule10868
    typealias Details = OriginalMarketDetails9483
    typealias Stream = StoryStreamPresentation10868
    typealias History = FieldHistoryGeometry10868

    // MARK: Retained evidence

    struct Evidence: Decodable {
        struct Company: Decodable {
            let url: String
            let source: String
            let publishedAt: String
            let quarterEnded: String
            let dilutedEPS: Double
            let priorQuarterEPS: Double
            let netIncomeMillions: Double
            let verifiedVia: String
            let capturedAt: String
        }

        struct Original: Decodable {
            let marketID: Int
            let outcomeID: Int
            let probability: Double
            let observedAt: String
            let untimedOpening: Double
        }

        struct Capture: Decodable {
            let eventID: String
            let marketID: String
            let conditionID: String
            let title: String
            let threshold: Double
            let unit: String
            let company: Company
            let scheduledAt: String
            let closedAt: String
            let resolvedYes: Bool
            let original: Original
            let description: String
        }

        /// One retained observation, `[t, p]`, exactly as captured.
        struct Point: Decodable, Equatable {
            let t: Int
            let p: Double

            init(t: Int, p: Double) {
                self.t = t
                self.p = p
            }

            init(from decoder: Decoder) throws {
                var c = try decoder.unkeyedContainer()
                t = try c.decode(Int.self)
                p = try c.decode(Double.self)
            }
        }

        struct AtlasDetail: Decodable {
            let home_team: String
            let status: String
            let commence_time: String?
        }

        /// The atlas event verbatim except `rows`, which is retained as
        /// `atlasRow` beside its count `rowCount`.
        struct AtlasEvent: Decodable {
            let key: String
            let label: String
            let unit: String
            let detail: AtlasDetail
            let series: [String]
            let pregame_projection: String?
            let source: String
            let rowCount: Int
        }

        struct AtlasRow: Decodable {
            let id: Int
            let name: String
            let probability: Double
            let american_odds: Int
            let rank: Int
            let rank_change_24h: Double?
            let probability_change_24h: Double
            let opening_probability: Double
            let opening_american_odds: Int
            let is_winner: Bool?
            let resolution_source: String?
            let last_updated: String
            let price_changed_at: String
            let key: String
            let source_file: String
            let category: String
            let market_name: String
            let outcome_name: String
            let _market_id: Int
            let source: String
            let observed_at: String
        }

        struct Header: Decodable {
            let id: String
            let title: String
            let role: String
            let predicate: String
            let source: String
            let marketID: String
            let rowKeys: [String]
            let missingNote: String
            let historyNote: String
            let contextNote: String
        }

        let capture: Capture
        let history: [Point]
        let atlasEvent: AtlasEvent
        let atlasRow: AtlasRow
        let header: Header
    }

    static let evidence: Evidence = {
        // swiftlint:disable:next force_try
        try! JSONDecoder().decode(Evidence.self, from: Data(retainedCapture.utf8))
    }()

    static var capture: Evidence.Capture { evidence.capture }
    static var points: [Evidence.Point] { evidence.history }
    static var first: Evidence.Point { points[0] }
    static var last: Evidence.Point { points[points.count - 1] }

    // MARK: Owner simulation (test-side only)

    static let scope = "economics:originals"
    static let streamScope = "economics:stories"
    static let earningsCard = Stream.CardRef(scope: streamScope, id: "earnings")
    /// The simulated device's zone: every date the owner shows is local, never UTC.
    static let zone = TimeZone(identifier: "America/Los_Angeles")!
    static var seriesID: String { "polymarket:\(capture.marketID):yes" }

    /// An ISO-8601 clock as epoch seconds, fractional seconds kept.
    static func epoch(_ iso: String) -> Double {
        var text = iso
        var fraction = 0.0
        if let dot = text.firstIndex(of: ".") {
            let tail = text[text.index(after: dot)...]
            let digits = String(tail.prefix { $0.isNumber })
            fraction = Double("0." + digits) ?? 0
            text.removeSubrange(dot..<text.index(dot, offsetBy: digits.count + 1))
        }
        return ISO8601DateFormatter().date(from: text)!.timeIntervalSince1970 + fraction
    }

    static func formatted(_ epoch: Double, _ format: String) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = zone
        formatter.dateFormat = format
        return formatter.string(from: Date(timeIntervalSince1970: epoch))
    }

    /// The reader's full local date and time.
    static func full(_ epoch: Double) -> String { formatted(epoch, "MMM d, yyyy, h:mm a") }

    /// A compact local day for an axis label.
    static func day(_ epoch: Double) -> String { formatted(epoch, "MMM d") }

    /// The reference's archived-quote label, ported for the fixture only.
    static func percent(_ value: Double) -> String {
        guard value.isFinite, value >= 0, value <= 1 else { return "Unavailable" }
        if value == 0 { return "0%" }
        if value == 1 { return "100%" }
        let tenths = (value * 1000).rounded()
        if tenths == 0 { return "<0.1%" }
        if tenths == 1000 { return ">99.9%" }
        let whole = tenths / 10
        return whole == whole.rounded() ? "\(Int(whole))%" : "\(whole)%"
    }

    static func usd(_ value: Double) -> String { String(format: "$%.2f", value) }

    static func pointID(_ t: Int) -> String { "t\(t)" }

    static var publishedEpoch: Double { epoch(capture.company.publishedAt) }

    /// The owner's pre-report observation: the latest observation strictly
    /// before the company's publication, and only when exactly one — the
    /// reference rule, ported test-side. Never the untimed opening, the
    /// original quote or a settlement.
    static var preReport: Evidence.Point? { preReport(in: points) }

    static func preReport(in list: [Evidence.Point]) -> Evidence.Point? {
        let eligible = list.filter { Double($0.t) < publishedEpoch && $0.p.isFinite && $0.p >= 0 && $0.p <= 1 }
        guard let latest = eligible.map(\.t).max() else { return nil }
        let matches = eligible.filter { $0.t == latest }
        return matches.count == 1 ? matches[0] : nil
    }

    static var preReportPoint: Evidence.Point { preReport! }

    static func chance(_ point: Evidence.Point) -> Reading {
        Reading(id: pointID(point.t), figure: percent(point.p), date: full(Double(point.t)), placement: point.p)
    }

    static var preReportChance: Reading { chance(preReportPoint) }

    /// The owner's USD axis: $0 to $2 per diluted share.
    static let axisUpper = 2.0

    static var reportedActual: Reading {
        Reading(id: "company-release", figure: usd(capture.company.dilutedEPS),
                date: "Published \(full(publishedEpoch))", placement: capture.company.dilutedEPS / axisUpper)
    }

    static var thresholdPlacement: Double { capture.threshold / axisUpper }

    static var deltaCents: Int { Int(((capture.company.dilutedEPS - capture.threshold) * 100).rounded()) }

    static var resolution: EarningsResult10868 {
        EarningsResult10868(words: capture.resolvedYes ? "Yes · contract resolved" : "No · contract resolved",
                            provenance: "Provider resolution · separate from the company report")
    }

    static var threshold: EarningsThreshold10868 {
        EarningsThreshold10868(label: "Contract threshold", figure: usd(capture.threshold),
                               rule: "Strictly greater than \(usd(capture.threshold)) diluted GAAP EPS")
    }

    static var usdAxis: EarningsAxis10868 {
        EarningsAxis10868(lower: 0, upper: axisUpper,
                          ticks: [0.0, 1.0, 2.0].map { EarningsAxisTick10868(placement: $0 / axisUpper, label: "$\(Int($0))") },
                          words: "USD per diluted share · scale starts at $0", offAxis: offAxisWords,
                          unavailable: "Dollar scale unavailable")
    }

    static let offAxisWords = "Outside this dollar scale · not drawn"

    /// A constructed narrow axis ($0 to $1.50) on which the retained actual and threshold have no position.
    static var narrowAxis: EarningsAxis10868 {
        EarningsAxis10868(lower: 0, upper: 1.5,
                          ticks: [0.0, 0.75, 1.5].map { EarningsAxisTick10868(placement: $0 / 1.5, label: usd($0)) },
                          words: "USD per diluted share · scale starts at $0", offAxis: offAxisWords,
                          unavailable: "Dollar scale unavailable")
    }

    static func phaseWords(_ phase: Phase) -> String {
        switch phase {
        case .beforeReport: return "Before earnings · historical view"
        case .companyReport: return "Company report"
        case .settled: return "Settled market"
        }
    }

    static func stateWords(_ phase: Phase) -> String {
        switch phase {
        case .beforeReport: return "Before report"
        case .companyReport: return "Company report"
        case .settled: return "Market resolved"
        }
    }

    // MARK: Leaf inputs (a nil argument keeps the phase's retained value; `.some(nil)` is absent)

    static func headline(_ phase: Phase, chance: Reading?? = nil, actual: Reading?? = nil,
                         result: EarningsResult10868?? = nil) -> EarningsHeadlineInput10868 {
        let beat = usd(capture.threshold)
        return EarningsHeadlineInput10868(
            eyebrow: "UNTY · Q3 2026 · Archive",
            title: "Unity Bancorp",
            phaseWords: phaseWords(phase),
            chanceLabel: "Pre-report chance",
            chanceSubject: "to beat \(beat)",
            chance: chance ?? preReportChance,
            threshold: threshold,
            actualLabel: "Reported per share",
            actualUnit: capture.unit,
            actualRelation: "\(deltaCents)¢ above \(beat)",
            actual: actual ?? (phase == .beforeReport ? nil : reportedActual),
            settlementWithheld: "Company reported · settlement not included",
            resultLabel: "Contract result",
            result: result ?? (phase == .settled ? resolution : nil),
            resultUnavailable: "Contract result unavailable",
            reminder: nil,
            readingUnavailable: "Unavailable",
            aboutLabel: "About these earnings probabilities",
            aboutHint: "Opens the sources and rules")
    }

    static func comparison(_ phase: Phase, baseline: Reading?? = nil, actual: Reading?? = nil,
                           delta: EarningsDelta10868?? = nil, result: EarningsResult10868?? = nil,
                           axis: EarningsAxis10868? = nil, thresholdAt placement: Double? = nil) -> EarningsComparisonInput10868 {
        let beat = usd(capture.threshold)
        let before = phase == .beforeReport
        return EarningsComparisonInput10868(
            eyebrow: "Expectation → earnings per share",
            baselineLabel: "Last recorded before report",
            baselineSubject: "Chance to beat \(beat)",
            baseline: baseline ?? preReportChance,
            title: before ? "The number to beat" : "Above the bar",
            threshold: threshold,
            thresholdPlacement: placement ?? thresholdPlacement,
            actualLabel: "Reported actual",
            actual: actual ?? (before ? nil : reportedActual),
            delta: delta ?? (before ? nil : EarningsDelta10868(label: "Above threshold", figure: "+\(deltaCents)¢")),
            unit: "Diluted GAAP EPS · quarter ended Sep 30",
            axis: axis ?? usdAxis,
            summary: before
                ? "Contract threshold \(beat). Actual not yet shown."
                : "Reported actual \(usd(capture.company.dilutedEPS)) versus contract threshold \(beat). Dollar scale starts at zero.",
            caption: before
                ? "A result must be higher than \(beat) to count as a beat."
                : "Reported earnings cleared the fixed threshold by \(deltaCents)¢ per share.",
            settlementWithheld: "Company result shown · market settlement not included",
            resultLabel: "Contract result",
            result: result ?? (phase == .settled ? resolution : nil),
            resultUnavailable: "Contract result unavailable",
            readingUnavailable: "Unavailable")
    }

    static func historyPoint(_ point: Evidence.Point) -> FieldHistoryPoint10868 {
        FieldHistoryPoint10868(id: pointID(point.t), x: Double(point.t), probability: point.p, style: .hollow)
    }

    static func observation(_ point: Evidence.Point) -> FieldHistoryReading10868 {
        .observation(pointID: pointID(point.t), figure: percent(point.p), provenance: full(Double(point.t)))
    }

    /// The owner's history: every retained Yes observation in one run, hollow
    /// (before the report), on 0–100%. `inspected` −1 is the last observation.
    static func history(inspected: Int = -1, inspecting: Bool = true, recorded: FieldHistoryReading10868? = nil,
                        retained: [Evidence.Point]? = nil, splitAt split: Int? = nil, controls: Bool = true,
                        plotHeight: CGFloat = 220) -> FieldHistoryInput10868 {
        let index = inspected < 0 ? points.count - 1 : inspected
        let at: Evidence.Point? = inspecting ? points[index] : nil
        let pre = preReportPoint
        let beat = usd(capture.threshold)
        let drawn = (retained ?? points).map { historyPoint($0) }
        // An owner-admitted gap (test-side only): two runs with an explicit break between them.
        let runs = split.map { [FieldHistoryRun10868(id: "before-gap", points: Array(drawn[..<$0])),
                                FieldHistoryRun10868(id: "after-gap", points: Array(drawn[$0...]))] }
            ?? [FieldHistoryRun10868(id: "captured", points: drawn)]
        let breaks = split.map { [FieldHistoryBreak10868(id: "gap", lower: drawn[$0 - 1].x, upper: drawn[$0].x, mark: "//")] } ?? []
        let series = FieldHistorySeries10868(
            id: seriesID, name: "Yes", shape: .circle, tint: DS.blue,
            runs: runs,
            links: [], labelPointID: nil,
            before: observation(pre),
            recorded: recorded ?? at.map { observation($0) } ?? FieldHistoryReading10868.absent(words: "No observation inspected"),
            absentWords: "No captured history", choose: nil)
        let inspection: FieldHistoryInspection10868? = at.map {
            FieldHistoryInspection10868(
                x: Double($0.t), caption: "Recorded \(full(Double($0.t)))",
                selections: [seriesID: .point(id: pointID($0.t), spoken: percent($0.p))], choices: [],
                choicePresentation: .slider(label: "Inspect earnings probability history"),
                note: "Only captured observations are shown.")
        }
        return FieldHistoryInput10868(
            title: "Chance to beat \(beat)", caption: "Recorded · Polymarket · Yes only",
            series: [series], selection: .series(id: seriesID, missingWords: "This history is unavailable"),
            domain: FieldHistoryDomain10868(lower: Double(first.t), upper: Double(last.t)), ceiling: 1,
            yTicks: [0.0, 0.5, 1.0].map { FieldHistoryTick10868(value: $0, lines: [percent($0)]) },
            xTicks: [first, last, points[154]].map { FieldHistoryTick10868(value: Double($0.t), lines: [day(Double($0.t))]) },
            guides: [], breaks: breaks,
            readout: .beforeAndInspected(beforeLabel: "Last recorded before report",
                                         inspectedLabel: index == 0 ? "First recorded before report" : "Inspected before report"),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow marks: before the report.", filled: nil),
            comparisonExplanation: nil,
            notes: ["All \(points.count) observations precede the company report."],
            summary: "Chance to beat \(beat): last before report \(percent(pre.p)). \(points.count) pre-report observations on a zero to 100 percent scale. No probability point is added from the result.",
            plotHeight: plotHeight, unboundReadingWords: "Not recorded at this observation",
            plotUnavailableWords: "History unavailable", windows: nil, scale: nil, moreOriginals: nil, details: nil,
            expand: controls ? FieldHistoryAction10868(id: "expand-history", label: "Expand",
                                                       spokenLabel: "Expand earnings probability history", isAvailable: true) : nil,
            inspect: nil,
            previous: controls ? FieldHistoryAction10868(id: "earlier", label: "Earlier",
                                                         spokenLabel: "Earlier earnings observation", isAvailable: index > 0) : nil,
            next: controls ? FieldHistoryAction10868(id: "later", label: "Later",
                                                     spokenLabel: "Later earnings observation", isAvailable: index < points.count - 1) : nil,
            inspection: inspection)
    }

    // MARK: Info, sources, stream and reader order

    static func reader(_ phase: Phase) -> FieldEventPageReaderHeader10868 {
        FieldEventPageReaderHeader10868(title: "Unity Bancorp", state: "\(stateWords(phase)) · beat \(usd(capture.threshold))")
    }

    /// The retained rules, paragraph by paragraph: rejoined they are the description exactly.
    static var rulesParagraphs: [String] {
        var text = capture.description
        if text.hasSuffix("\n") { text.removeLast() }
        return text.components(separatedBy: "\n\n")
    }

    static var releaseLink: RugbyMatchEventPageLink10868 {
        RugbyMatchEventPageLink10868(id: "company-release", label: "Company earnings release", url: URL(string: capture.company.url)!)
    }

    static func about(_ phase: Phase) -> RugbyMatchEventPageAbout10868 {
        let beat = usd(capture.threshold)
        var sections = [
            RugbyMatchEventPageSection10868(title: "What did this market predict?", paragraphs: [
                "Unity Bancorp’s quarterly diluted GAAP earnings per share must be strictly greater than \(beat). That was the consensus estimate fixed when this contract was created, not a moving forecast.",
            ]),
            RugbyMatchEventPageSection10868(title: "Recorded chances", paragraphs: [
                "Polymarket supplies \(points.count) probability-history observations. First captured: \(percent(first.p)) on \(full(Double(first.t))). Last retained: \(percent(last.p)) on \(full(Double(last.t))). These are historical observations, not current quotes or verified trade closes.",
                "Only the Yes history is supplied. No complementary No line or terminal 100% endpoint is invented. Times follow your device.",
            ]),
        ]
        if phase != .beforeReport {
            sections.append(RugbyMatchEventPageSection10868(title: "Company report", paragraphs: [
                "The company reported \(usd(capture.company.dilutedEPS)) per diluted share. The release was published \(full(publishedEpoch)); the market’s scheduled date was an estimate.",
                phase == .settled
                    ? "The provider separately confirms Yes as the resolved winner. That evidence is separate from the company’s actual."
                    : "Market settlement is not included in this view. The company report does not supply the contract result.",
            ], link: releaseLink))
        }
        sections.append(RugbyMatchEventPageSection10868(title: "Original saved market", paragraphs: [
            "The original prop keeps its own last quote and an untimed opening in its Details; the opening is not a pre-report baseline.",
        ], sourceID: "rules"))
        return RugbyMatchEventPageAbout10868(title: "About these earnings", sections: sections)
    }

    static var sources: [RugbyMatchEventPageSource10868] {
        let row = evidence.atlasRow
        return [RugbyMatchEventPageSource10868(id: "rules", title: "Exact source identities and rules", sections: [
            RugbyMatchEventPageSection10868(title: "Identities", paragraphs: [
                "Polymarket event \(capture.eventID) · market \(capture.marketID)",
                "Condition \(capture.conditionID)",
                "Original market \(row._market_id) · outcome \(row.id) (\(row.outcome_name))",
            ]),
            RugbyMatchEventPageSection10868(title: "Rules", paragraphs: rulesParagraphs),
        ])]
    }

    static var stream: Stream {
        Stream(scope: streamScope, heading: "Earnings stories",
               cards: [Stream.Card(id: "earnings", name: "Earnings against expectations")], primary: earningsCard)
    }

    static var stories: [EarningsEventPageStory10868] {
        [EarningsEventPageStory10868(cardID: "earnings", card: .earnings)]
    }

    static var readerOrder: [EarningsReaderStop10868] {
        [EarningsReaderStop10868(card: .history, name: "Chance to beat \(usd(capture.threshold))"),
         EarningsReaderStop10868(card: .earnings, name: "Earnings against expectations")]
    }

    static var bundleCopy: EarningsEventPageBundleCopy10868 {
        EarningsEventPageBundleCopy10868(
            storiesLabel: "Earnings stories", storyUnavailable: "This story is no longer available",
            readerUnavailable: "This card is not part of this view", sourceUnavailable: "Source unavailable",
            sourceLabel: "Exact source identities and rules", detailsLabel: "Original market & source details",
            allPropsLabel: "All props", previousLabel: "Previous", nextLabel: "Next")
    }

    static let pageCopy = EarningsEventPageCopy10868(
        phaseUnavailable: "This earnings view is updating; nothing is shown until every part belongs to the same moment.",
        backLabel: "Back to earnings")

    // MARK: The original (the atlas row), its Details and side history

    static var identity: Details.Identity {
        Details.Identity(source: evidence.atlasRow.source, market: String(evidence.atlasRow._market_id),
                         side: String(evidence.atlasRow.id))
    }

    static var heldSelection: Details.Selection { Details.Selection(scope: scope, identity: identity) }

    static var quoteDate: String { full(epoch(evidence.atlasRow.observed_at)) }

    static var provenanceRows: [LadderOriginalProbabilityDetails9483.Row] {
        let row = evidence.atlasRow
        let pre = preReportPoint
        return [
            LadderOriginalProbabilityDetails9483.Row(label: "Original market", value: String(row._market_id)),
            LadderOriginalProbabilityDetails9483.Row(label: "Original outcome", value: "\(row.id) · \(row.outcome_name)"),
            LadderOriginalProbabilityDetails9483.Row(label: "First captured history observation",
                                                     value: "\(percent(first.p)) · \(full(Double(first.t)))"),
            LadderOriginalProbabilityDetails9483.Row(label: "Last recorded before report",
                                                     value: "\(percent(pre.p)) · \(full(Double(pre.t)))"),
            LadderOriginalProbabilityDetails9483.Row(label: threshold.label, value: threshold.rule),
        ]
    }

    /// The original as Details shows it in a phase: the untimed opening and
    /// the snapshot's last quote, each with its own words — never the
    /// pre-report baseline and never a current chance.
    static func original(_ phase: Phase) -> Details.Original {
        let row = evidence.atlasRow
        let settled = phase == .settled
        let quote = Details.Reading.value(percent(row.probability), placement: row.probability,
                                          provenance: "Last quote in the original snapshot · \(quoteDate)")
        return Details.Original(
            identity: identity, title: row.market_name, outcome: row.outcome_name,
            mode: settled ? .result : .comparison(.recorded),
            pregame: Details.Reading.value(percent(row.opening_probability), placement: row.opening_probability,
                                           provenance: "Untimed opening · not the pre-report baseline"),
            later: settled ? nil : quote,
            grade: settled
                ? Details.Grade(words: resolution.words,
                                provenance: "Provider resolution from the newer capture; the original record is unchanged")
                : nil,
            about: Details.About(source: "Polymarket · original saved prop", rules: .verified(rulesParagraphs),
                                 provenance: provenanceRows,
                                 historicalQuote: settled ? Details.HistoricalQuote(text: percent(row.probability), recorded: quoteDate) : nil),
            beforeLabel: "Untimed opening")
    }

    static func recorded(_ phase: Phase, selection: Details.Selection) -> Details.RecordedHistory {
        let pre = preReportPoint
        var mini = history(inspecting: false, controls: false, plotHeight: 160)
        mini.layout = .expanded
        mini.showsKey = false
        return Details.RecordedHistory(
            selection: selection, mode: original(phase).mode, seriesID: seriesID,
            availability: phase == .beforeReport
                ? "Current probability unavailable · before-report view"
                : "Current probability unavailable · recorded history below",
            readings: [Details.RecordedReading(label: "Last recorded before report", marker: .hollow,
                                               reading: .value(percent(pre.p), placement: pre.p, provenance: full(Double(pre.t))))],
            movement: nil, history: mini, finishLabel: "Reported actual",
            finish: phase == .beforeReport ? nil : .reported(words: "\(usd(capture.company.dilutedEPS)) per diluted share", spoken: nil),
            preview: nil,
            expand: FieldHistoryAction10868(id: "original-history", label: "Expand history", spokenLabel: nil, isAvailable: true),
            explore: nil, unmatchedWords: "This history is not linked to the selected original")
    }

    static func originals(_ phase: Phase, selection: Details.Selection?) -> FieldEventPageOriginals10868 {
        FieldEventPageOriginals10868(
            catalogue: Details.Catalogue(scope: scope, originals: [original(phase)]),
            selection: selection,
            recorded: selection.map { recorded(phase, selection: $0) },
            heading: "All props", context: "1 original outcome",
            emptyWords: "No original outcomes", unavailableChoice: "Original unavailable", tint: DS.blue)
    }

    // MARK: Bundles and pages

    static func bundle(_ phase: Phase, headline: EarningsHeadlineInput10868? = nil,
                       comparison: EarningsComparisonInput10868? = nil, history: FieldHistoryInput10868? = nil,
                       readerOrder order: [EarningsReaderStop10868]? = nil,
                       stories list: [EarningsEventPageStory10868]? = nil,
                       selection: Details.Selection? = nil, holdsOriginal: Bool = true,
                       withOriginals: Bool = true) -> Bundle {
        Bundle(phase: phase,
               headline: headline ?? Self.headline(phase),
               comparison: comparison ?? Self.comparison(phase),
               history: history ?? Self.history(),
               reader: reader(phase), about: about(phase), sources: sources, stream: stream,
               stories: list ?? stories, readerOrder: order ?? readerOrder, copy: bundleCopy,
               originals: withOriginals ? originals(phase, selection: holdsOriginal ? (selection ?? heldSelection) : nil) : nil)
    }

    static func input(_ phase: Phase, bundle: Bundle? = nil, readerPlotHeight: CGFloat? = 360) -> Input {
        Input(phase: phase, bundle: bundle ?? Self.bundle(phase), copy: pageCopy, readerPlotHeight: readerPlotHeight)
    }

    /// Every callback and the hook, recorded in call order.
    final class Log {
        var events: [String] = []
    }

    static func page(_ input: Input, _ mode: Mode = .page, log: Log, hook: Bool = true) -> Page {
        Page(input: input, mode: mode,
             onAbout: { log.events.append("about") },
             onHistoryAction: { log.events.append("history:\($0)") },
             onHistoryInspectionChoice: { log.events.append("inspect:\($0)") },
             onHistoryPlotPosition: { log.events.append("plot:\($0)") },
             onOpenOriginal: { log.events.append("details:\($0.scope):\($0.identity.market):\($0.identity.side)") },
             onAllProps: { log.events.append("allProps") },
             onStoryIntent: { log.events.append("story:\($0)") },
             onReaderStep: { log.events.append("step:\($0.rawValue)") },
             onBack: { log.events.append("back") },
             onOriginalSelect: { log.events.append("select:\($0.identity.market)") },
             onOriginalHistory: { log.events.append("originalHistory:\($0.actionID)") },
             onLink: { log.events.append("link:\($0.id):\($0.url.absoluteString)") },
             onSource: { log.events.append("source:\($0)") },
             onInteraction: hook ? { log.events.append("hold") } : nil)
    }

    static func activation(_ log: Log) -> StoryStreamCardActivation10868 {
        StoryStreamCardActivation10868(card: earningsCard,
                                       intents: [.interaction(scope: streamScope, card: earningsCard)],
                                       send: { log.events.append("stream:\($0)") })
    }

    static var interaction: String {
        "stream:\(Stream.Intent.interaction(scope: streamScope, card: earningsCard))"
    }

    // MARK: Words

    static func slotWords(_ slot: FieldHistoryReadoutSlot10868) -> [String] {
        switch slot.display {
        case .figure(let figure, let provenance): return [slot.label, figure, provenance]
        case .words(let words): return [slot.label, words]
        }
    }

    /// Every word the history draws: title, caption, ticks, key, readouts, notes and summary.
    static func historyWords(_ input: FieldHistoryInput10868) -> [String] {
        var words = [input.title, input.caption, input.summary].compactMap { $0 } + input.notes
        words += input.yTicks.flatMap(\.lines) + input.xTicks.flatMap(\.lines)
        words += [input.markKey.hollow, input.markKey.filled].compactMap { $0 }
        for series in input.series {
            words.append(series.name)
            words += History.readoutSlots(series, in: input).flatMap { slotWords($0) }
        }
        return words
    }

    /// Every word the page body reaches: the headline, the history and the earnings card.
    static func reachable(_ page: Page) -> [String] {
        var words: [String] = []
        if let headline = page.headlineContent() {
            words += headline.model.words
        } else {
            words.append(page.input.copy.phaseUnavailable)
        }
        if let history = page.historyContent(reader: false) {
            words += historyWords(history.input)
        }
        words += page.earningsWords(at: .stream(activation(Log())))
        return words
    }

    /// Whole-token mention: never a substring of a longer word or figure.
    static func mentions(_ words: [String], _ token: String) -> Bool {
        let pattern = "(?<![\\p{L}\\p{N}])" + NSRegularExpression.escapedPattern(for: token) + "(?![\\p{L}\\p{N}])"
        return words.contains { $0.range(of: pattern, options: .regularExpression) != nil }
    }

    /// A payload may name only the canonical original in its own scope.
    static func violations(_ selections: [Details.Selection]) -> [String] {
        selections.compactMap { selection in
            selection == heldSelection ? nil : "foreign \(selection.scope):\(selection.identity.market):\(selection.identity.side)"
        }
    }

    struct Unresolved: Error { let what: String }

    // MARK: - Retained evidence and roles

    func testTheRetainedCaptureKeepsEverySourceConditionMarketOutcomeClockRuleAndObservation() {
        let capture = Self.capture
        XCTAssertEqual(capture.eventID, "1106010")
        XCTAssertEqual(capture.marketID, "5144377")
        XCTAssertEqual(capture.conditionID, "0x61f0a0eb9fa05a2daa8097c212ec79a8b8ec07cb599cd6e8816e0562442d24f6")
        XCTAssertEqual(capture.title, "Will Unity Bancorp (UNTY) beat quarterly earnings?")
        XCTAssertEqual(capture.threshold, 1.6)
        XCTAssertEqual(capture.unit, "Diluted GAAP EPS · USD")
        XCTAssertEqual(capture.company.url,
                       "https://www.globenewswire.com/news-release/2026/10/13/3379462/0/en/unity-bancorp-reports-quarterly-earnings-of-17-4-million.html")
        XCTAssertEqual(capture.company.source, "Unity Bancorp, Inc. via GlobeNewswire")
        XCTAssertEqual(capture.company.publishedAt, "2026-10-13T10:00:00Z")
        XCTAssertEqual(capture.company.quarterEnded, "2026-09-30")
        XCTAssertEqual(capture.company.dilutedEPS, 1.7)
        XCTAssertEqual(capture.company.priorQuarterEPS, 1.42)
        XCTAssertEqual(capture.company.netIncomeMillions, 17.4)
        XCTAssertEqual(capture.company.verifiedVia,
                       "Public release read through web tool; lines 54 and 57. Facts transcribed, not a full-response archive.")
        XCTAssertEqual(capture.company.capturedAt, "2026-10-15T04:06:24.871378+00:00")
        XCTAssertEqual(capture.scheduledAt, "2026-10-12T20:00:00Z")
        XCTAssertEqual(capture.closedAt, "2026-10-13T12:16:28Z")
        XCTAssertTrue(capture.resolvedYes)
        XCTAssertEqual(capture.original.marketID, 63343098)
        XCTAssertEqual(capture.original.outcomeID, 240153004)
        XCTAssertEqual(capture.original.probability, 0.745)
        XCTAssertEqual(capture.original.observedAt, "2026-10-10T22:22:04.083317+00:00")
        XCTAssertEqual(capture.original.untimedOpening, 0.595)

        // The rules, verbatim: the paragraphs rejoin to the description exactly.
        XCTAssertEqual(Self.rulesParagraphs.joined(separator: "\n\n") + "\n", capture.description)
        XCTAssertEqual(Self.rulesParagraphs.count, 4)
        XCTAssertTrue(capture.description.hasPrefix(
            "As of market creation, Unity Bancorp is estimated to release earnings on October 12, 2026."))
        XCTAssertTrue(capture.description.contains("reports GAAP EPS greater than $1.60 for the relevant quarter"))
        XCTAssertTrue(capture.description.contains("Note: All figures are expressed in USD, unless otherwise indicated."))

        // Every observation, exactly: 308, strictly advancing, all before the report.
        let points = Self.points
        XCTAssertEqual(points.count, 308)
        XCTAssertEqual(Self.first, Evidence.Point(t: 1790730014, p: 0.53))
        XCTAssertEqual(Self.last, Evidence.Point(t: 1791831635, p: 0.88))
        XCTAssertEqual(points[154], Evidence.Point(t: 1791280816, p: 0.79))
        XCTAssertEqual(points[306], Evidence.Point(t: 1791828029, p: 0.885))
        XCTAssertTrue(zip(points, points.dropFirst()).allSatisfy { $0.t < $1.t }, "clocks strictly advance")
        XCTAssertEqual(points.map(\.p).min(), 0.53)
        XCTAssertEqual(points.map(\.p).max(), 0.89)
        XCTAssertTrue(points.allSatisfy { $0.p > 0 && $0.p < 1 }, "no retained 0% or 100% endpoint")
        XCTAssertTrue(points.allSatisfy { Double($0.t) < Self.publishedEpoch }, "every observation precedes the report")
        // No true gap: no step exceeds the reference's 90-minute break rule, so the owner admits one run and no break.
        let steps = zip(points, points.dropFirst()).map { $1.t - $0.t }
        XCTAssertLessThanOrEqual(steps.max() ?? .max, 90 * 60)
        XCTAssertEqual(steps.count, 307)

        // The atlas economics event and its one original row, verbatim.
        let event = Self.evidence.atlasEvent
        XCTAssertEqual(event.key, "economics")
        XCTAssertEqual(event.label, "Non-sport · earnings")
        XCTAssertEqual(event.unit, "")
        XCTAssertEqual(event.detail.home_team, "Unity Bancorp earnings")
        XCTAssertEqual(event.detail.status, "field")
        XCTAssertNil(event.detail.commence_time)
        XCTAssertEqual(event.series, [])
        XCTAssertNil(event.pregame_projection)
        XCTAssertEqual(event.source, "field-63343098.json")
        XCTAssertEqual(event.rowCount, 1)
        let row = Self.evidence.atlasRow
        XCTAssertEqual(row.id, 240153004)
        XCTAssertEqual(row.name, "Yes")
        XCTAssertEqual(row.probability, 0.745)
        XCTAssertEqual(row.american_odds, -292)
        XCTAssertEqual(row.rank, 1)
        XCTAssertNil(row.rank_change_24h)
        XCTAssertEqual(row.probability_change_24h, -0.050000000000000044)
        XCTAssertEqual(row.opening_probability, 0.595)
        XCTAssertEqual(row.opening_american_odds, -147)
        XCTAssertNil(row.is_winner, "the original snapshot predates the resolution")
        XCTAssertNil(row.resolution_source)
        XCTAssertEqual(row.last_updated, "2026-10-10T22:22:04.083317+00:00")
        XCTAssertEqual(row.price_changed_at, "2026-10-10T22:22:04.083317+00:00")
        XCTAssertEqual(row.observed_at, "2026-10-10T22:22:04.083317+00:00")
        XCTAssertEqual(row.key, "field-63343098.json:0")
        XCTAssertEqual(row.source_file, "field-63343098.json")
        XCTAssertEqual(row.category, "named")
        XCTAssertEqual(row.market_name, "Will Unity Bancorp (UNTY) beat quarterly earnings?")
        XCTAssertEqual(row.outcome_name, "Yes")
        XCTAssertEqual(row._market_id, 63343098)
        XCTAssertEqual(row.source, "polymarket")
        // The capture's original and the atlas row agree on every shared identity, figure and clock.
        XCTAssertEqual(row._market_id, capture.original.marketID)
        XCTAssertEqual(row.id, capture.original.outcomeID)
        XCTAssertEqual(row.probability, capture.original.probability)
        XCTAssertEqual(row.opening_probability, capture.original.untimedOpening)
        XCTAssertEqual(row.observed_at, capture.original.observedAt)
        XCTAssertEqual(row.market_name, capture.title)

        let header = Self.evidence.header
        XCTAssertEqual(header.id, "economics")
        XCTAssertEqual(header.title, "Unity Bancorp earnings")
        XCTAssertEqual(header.role, "binary")
        XCTAssertEqual(header.predicate, "Beat quarterly earnings")
        XCTAssertEqual(header.source, "polymarket")
        XCTAssertEqual(header.marketID, "63343098")
        XCTAssertEqual(header.rowKeys, ["field-63343098.json:0"])
        XCTAssertEqual(header.missingNote, "Last quotes are available in details.")
        XCTAssertEqual(header.historyNote, "Probability history was not captured.")
        XCTAssertEqual(header.contextNote, "Only captured questions are represented.")
    }

    func testTheOriginalFirstLastPreReportReportAndSettledRolesStayDistinct() throws {
        let capture = Self.capture
        let pre = try XCTUnwrap(Self.preReport)
        // Every observation precedes the report, so the pre-report role is the last observation…
        XCTAssertEqual(pre, Self.last)
        XCTAssertEqual(Self.percent(pre.p), "88%")
        // …by the owner's strictly-before, unique rule (test-side): an observation at publication does not
        // qualify, and two at the latest clock elect none.
        let atPublication = Evidence.Point(t: Int(Self.publishedEpoch), p: 0.9)
        XCTAssertEqual(Self.preReport(in: Self.points + [atPublication]), Self.last)
        XCTAssertNil(Self.preReport(in: Self.points + [Evidence.Point(t: Self.last.t, p: 0.87)]))
        // The first captured observation is not the opening; the opening is untimed and differs.
        XCTAssertEqual(Self.percent(Self.first.p), "53%")
        XCTAssertEqual(Self.percent(capture.original.untimedOpening), "59.5%")
        XCTAssertNotEqual(capture.original.untimedOpening, Self.first.p)
        // The original quote is older than the last observation and is not a current chance.
        XCTAssertEqual(Self.percent(capture.original.probability), "74.5%")
        XCTAssertLessThan(Self.epoch(capture.original.observedAt), Double(Self.last.t))
        XCTAssertNotEqual(capture.original.probability, Self.last.p)
        // The scheduled estimate, the company's publication, the market close and the capture are four clocks.
        let scheduled = Self.epoch(capture.scheduledAt)
        let closed = Self.epoch(capture.closedAt)
        XCTAssertLessThan(scheduled, Self.publishedEpoch)
        XCTAssertLessThan(Self.publishedEpoch, closed)
        XCTAssertLessThan(closed, Self.epoch(capture.company.capturedAt))
        XCTAssertNotEqual(Self.full(scheduled), Self.full(Self.publishedEpoch))

        // On the settled page every role keeps its own figure, date and surface.
        let page = Self.page(Self.input(.settled), log: Log())
        let headline = try XCTUnwrap(page.headlineContent()).model
        XCTAssertEqual(headline.chance, .value(figure: "88%", date: Self.full(Double(pre.t))))
        XCTAssertEqual(headline.actual, .value(figure: "$1.70", date: "Published \(Self.full(Self.publishedEpoch))"))
        XCTAssertEqual(headline.result, .result(words: "Yes · contract resolved",
                                                provenance: "Provider resolution · separate from the company report"))
        let card = try XCTUnwrap(page.comparisonContent()).model
        XCTAssertEqual(card.baseline, .value(figure: "88%", date: Self.full(Double(pre.t))))
        XCTAssertEqual(card.actual, .value(figure: "$1.70", date: "Published \(Self.full(Self.publishedEpoch))"))
        // The publication date, not the scheduled estimate or the close, dates the actual.
        XCTAssertFalse(Self.mentions(headline.words + card.words, Self.full(scheduled)))
        XCTAssertFalse(Self.mentions(headline.words + card.words, Self.full(closed)))

        // The original quote and the untimed opening are in Details only — never the page body.
        let words = Self.reachable(page)
        XCTAssertTrue(Self.mentions(words, "88%"), "positive control: the pre-report chance is reachable")
        for figure in ["74.5%", "59.5%"] {
            XCTAssertFalse(Self.mentions(words, figure), "\(figure) must stay in Details")
        }
        let details = try XCTUnwrap(page.originalDetailsContent())
        let settled = try XCTUnwrap(Details.content(catalogue: details.catalogue, selection: details.selection))
        XCTAssertEqual(settled.readings.map(\.label), ["Untimed opening"])
        XCTAssertEqual(settled.readings.map(\.text), ["59.5%"])
        XCTAssertEqual(settled.readings.map(\.provenance), ["Untimed opening · not the pre-report baseline"])
        XCTAssertEqual(settled.result?.words, "Yes · contract resolved")
        XCTAssertTrue(settled.about.contains(LadderOriginalProbabilityDetails9483.Row(
            label: Details.historicalLabel, value: "74.5%, recorded \(Self.quoteDate)")))
        XCTAssertTrue(settled.about.contains(LadderOriginalProbabilityDetails9483.Row(
            label: "First captured history observation", value: "53% · \(Self.full(Double(Self.first.t)))")))
        // Before the report the snapshot's quote is a dated recorded chance, never a current one.
        let earlier = try XCTUnwrap(Self.page(Self.input(.beforeReport), log: Log()).originalDetailsContent())
        let before = try XCTUnwrap(Details.content(catalogue: earlier.catalogue, selection: earlier.selection))
        XCTAssertEqual(before.readings.map(\.label), ["Untimed opening", "Recorded chance"])
        XCTAssertEqual(before.readings.map(\.text), ["59.5%", "74.5%"])
        XCTAssertNil(before.result)
        XCTAssertFalse(before.readings.contains { $0.label == Details.Later.current.label })
    }

    // MARK: - The paired headline

    func testBeforeTheReportTheHeadlineShowsOnlyTheDatedChanceAndTheFixedThreshold() throws {
        let date = Self.full(Double(Self.last.t))
        let model = try XCTUnwrap(Self.page(Self.input(.beforeReport), log: Log()).headlineContent()).model
        XCTAssertEqual(model.parts, [.eyebrow, .title, .phase, .chance, .threshold])
        XCTAssertEqual(model.chance, .value(figure: "88%", date: date))
        XCTAssertNil(model.actual)
        XCTAssertNil(model.result)
        XCTAssertEqual(model.words(.eyebrow), ["UNTY · Q3 2026 · Archive"])
        XCTAssertEqual(model.words(.title), ["Unity Bancorp"])
        XCTAssertEqual(model.words(.phase), ["Before earnings · historical view"])
        XCTAssertEqual(model.words(.chance), ["Pre-report chance", "88%", "to beat $1.60", date])
        XCTAssertEqual(model.words(.threshold),
                       ["Contract threshold", "$1.60", "Strictly greater than $1.60 diluted GAAP EPS"])
        XCTAssertEqual(model.words, model.parts.flatMap { model.words($0) })

        // Later facts handed to the earlier phase are never shown — no actual, relation or result.
        let leaky = Headline(phase: .beforeReport,
                             input: Self.headline(.beforeReport, actual: Self.reportedActual, result: Self.resolution))
        XCTAssertNil(leaky.actual)
        XCTAssertNil(leaky.result)
        for word in ["$1.70", "Reported per share", "10¢ above $1.60", "Yes · contract resolved"] {
            XCTAssertFalse(Self.mentions(leaky.words, word), word)
        }
        // Positive control: the same input at the report phase shows the actual, still not the result.
        let control = Headline(phase: .companyReport,
                               input: Self.headline(.beforeReport, actual: Self.reportedActual, result: Self.resolution))
        XCTAssertTrue(Self.mentions(control.words, "$1.70"))
        XCTAssertFalse(Self.mentions(control.words, "Yes · contract resolved"))
    }

    func testTheCompanyReportShowsTheActualInItsOwnUnitAndDateWithSettlementWithheld() throws {
        let chanceDate = Self.full(Double(Self.last.t))
        let actualDate = "Published \(Self.full(Self.publishedEpoch))"
        let model = try XCTUnwrap(Self.page(Self.input(.companyReport), log: Log()).headlineContent()).model
        XCTAssertEqual(model.parts, [.eyebrow, .title, .phase, .chance, .actual, .settlement])
        XCTAssertEqual(model.words(.phase), ["Company report"])
        XCTAssertEqual(model.words(.chance), ["Pre-report chance", "88%", "to beat $1.60", chanceDate])
        XCTAssertEqual(model.words(.actual),
                       ["Reported per share", "$1.70", "Diluted GAAP EPS · USD", "10¢ above $1.60", actualDate])
        XCTAssertEqual(model.words(.settlement), ["Company reported · settlement not included"])
        XCTAssertNil(model.result)
        // Two units, two dates: the chance is dated by its observation, the actual by the publication.
        XCTAssertNotEqual(chanceDate, actualDate)
        // Probability stays first and prominent; the actual follows it.
        XCTAssertLessThan(try XCTUnwrap(model.parts.firstIndex(of: .chance)), try XCTUnwrap(model.parts.firstIndex(of: .actual)))
        XCTAssertEqual(model.spokenChance, "Pre-report chance: 88% to beat $1.60, \(chanceDate)")
        XCTAssertEqual(model.spokenActual,
                       "Reported per share: $1.70, Diluted GAAP EPS · USD, 10¢ above $1.60, \(actualDate)")
        XCTAssertNil(model.spokenResult)

        // A result handed to the report phase stays withheld; the withheld words remain.
        let leaky = Headline(phase: .companyReport, input: Self.headline(.companyReport, result: Self.resolution))
        XCTAssertNil(leaky.result)
        XCTAssertFalse(Self.mentions(leaky.words, "Yes · contract resolved"))
        XCTAssertTrue(Self.mentions(leaky.words, "Company reported · settlement not included"))
        // A missing relation never borrows another figure.
        let bare = Headline(phase: .companyReport, input: EarningsHeadlineInput10868(
            eyebrow: nil, title: "Unity Bancorp", phaseWords: "Company report", chanceLabel: "Pre-report chance",
            chanceSubject: "to beat $1.60", chance: Self.preReportChance, threshold: Self.threshold,
            actualLabel: "Reported per share", actualUnit: Self.capture.unit, actualRelation: nil,
            actual: Self.reportedActual, settlementWithheld: "Company reported · settlement not included",
            resultLabel: "Contract result", result: nil, resultUnavailable: "Contract result unavailable",
            reminder: nil, readingUnavailable: "Unavailable", aboutLabel: "About", aboutHint: nil))
        XCTAssertEqual(bare.words(.eyebrow), [])
        XCTAssertEqual(bare.words(.actual), ["Reported per share", "$1.70", "Diluted GAAP EPS · USD", actualDate])
    }

    func testTheSettledMarketAddsTheSeparatelyAdmittedResultAndKeepsThePreReportReminder() throws {
        let model = try XCTUnwrap(Self.page(Self.input(.settled), log: Log()).headlineContent()).model
        XCTAssertEqual(model.parts, [.eyebrow, .title, .phase, .chance, .actual, .result, .reminder])
        XCTAssertEqual(model.words(.phase), ["Settled market"])
        XCTAssertEqual(model.words(.result),
                       ["Contract result", "Yes · contract resolved", "Provider resolution · separate from the company report"])
        // No technical reminder: the prominent dated pre-report chance is itself the reminder.
        XCTAssertEqual(model.words(.reminder), [])
        XCTAssertEqual(model.spokenResult,
                       "Contract result: Yes · contract resolved, Provider resolution · separate from the company report")
        // The pre-report chance is kept as recorded — never replaced by the result or a 100%.
        XCTAssertEqual(model.chance, .value(figure: "88%", date: Self.full(Double(Self.last.t))))
        XCTAssertFalse(Self.mentions(model.words, "100%"))
        XCTAssertFalse(Self.mentions(model.words, "Company reported · settlement not included"))

        // The result, the actual and the chance are independent evidence.
        let noActual = Headline(phase: .settled, input: Self.headline(.settled, actual: .some(nil)))
        XCTAssertEqual(noActual.actual, .unavailable("Unavailable"))
        XCTAssertEqual(noActual.result, model.result)
        XCTAssertEqual(noActual.chance, model.chance)
        let noResult = Headline(phase: .settled, input: Self.headline(.settled, result: .some(nil)))
        XCTAssertEqual(noResult.result, .unavailable("Contract result unavailable"))
        XCTAssertEqual(noResult.words(.result), ["Contract result", "Contract result unavailable"])
        XCTAssertEqual(noResult.actual, model.actual)
        let resolvedNo = Headline(phase: .settled, input: Self.headline(
            .settled, result: EarningsResult10868(words: "No · contract resolved", provenance: nil)))
        XCTAssertEqual(resolvedNo.words(.result), ["Contract result", "No · contract resolved"])
        XCTAssertEqual(resolvedNo.chance, model.chance)
        XCTAssertEqual(resolvedNo.actual, model.actual)
        // A blank reminder draws nothing; the chance it describes stays.
        let quiet = Headline(phase: .settled, input: EarningsHeadlineInput10868(
            eyebrow: "UNTY · Q3 2026 · Archive", title: "Unity Bancorp", phaseWords: "Settled market",
            chanceLabel: "Pre-report chance", chanceSubject: "to beat $1.60", chance: Self.preReportChance,
            threshold: Self.threshold, actualLabel: "Reported per share", actualUnit: Self.capture.unit,
            actualRelation: "10¢ above $1.60", actual: Self.reportedActual,
            settlementWithheld: "Company reported · settlement not included", resultLabel: "Contract result",
            result: Self.resolution, resultUnavailable: "Contract result unavailable", reminder: " ",
            readingUnavailable: "Unavailable", aboutLabel: "About", aboutHint: nil))
        XCTAssertEqual(quiet.words(.reminder), [])
        XCTAssertEqual(quiet.chance, model.chance)
        // Positive control: an owner's reminder, when supplied, is shown verbatim and only once settled.
        let reminded = EarningsHeadlineInput10868(
            eyebrow: nil, title: "Unity Bancorp", phaseWords: "Settled market", chanceLabel: "Pre-report chance",
            chanceSubject: "to beat $1.60", chance: Self.preReportChance, threshold: Self.threshold,
            actualLabel: "Reported per share", actualUnit: Self.capture.unit, actualRelation: "10¢ above $1.60",
            actual: Self.reportedActual, settlementWithheld: "Company reported · settlement not included",
            resultLabel: "Contract result", result: Self.resolution, resultUnavailable: "Contract result unavailable",
            reminder: "Recorded before the report", readingUnavailable: "Unavailable", aboutLabel: "About", aboutHint: nil)
        XCTAssertEqual(Headline(phase: .settled, input: reminded).words(.reminder), ["Recorded before the report"])
        XCTAssertEqual(Headline(phase: .companyReport, input: reminded).words(.reminder), [])
    }

    func testEveryDatedReadingNeedsItsIdFigureDateAndAValidPlacement() {
        let good = Self.preReportChance
        XCTAssertTrue(Rule.isShown(good), "positive control")
        XCTAssertEqual(Rule.display(good, unavailable: "Unavailable"), .value(figure: "88%", date: good.date))
        // Unknown: no id, figure or date — for a chance and for the actual alike.
        let unknown: [(String, Reading?)] = [
            ("absent", nil),
            ("blank id", Reading(id: " ", figure: good.figure, date: good.date, placement: good.placement)),
            ("blank figure", Reading(id: good.id, figure: "", date: good.date, placement: good.placement)),
            ("blank date", Reading(id: good.id, figure: good.figure, date: "\n", placement: good.placement)),
        ]
        // Unplaceable: known words, but no position inside 0…1 — unknown as a probability only.
        let unplaceable: [(String, Reading)] = [
            ("not a number", Reading(id: good.id, figure: good.figure, date: good.date, placement: .nan)),
            ("infinite", Reading(id: good.id, figure: good.figure, date: good.date, placement: .infinity)),
            ("below zero", Reading(id: good.id, figure: good.figure, date: good.date, placement: -0.01)),
            ("above one", Reading(id: good.id, figure: good.figure, date: good.date, placement: 1.01)),
        ]
        for (name, reading) in unplaceable {
            XCTAssertTrue(Rule.isKnown(reading), name)
            XCTAssertFalse(Rule.isShown(reading), name)
            XCTAssertEqual(Rule.display(reading, unavailable: "Unavailable"), .unavailable("Unavailable"), "\(name): a chance needs 0…1")
            XCTAssertEqual(Rule.known(reading, unavailable: "Unavailable"), .value(figure: good.figure, date: good.date),
                           "\(name): money is known by its words")
            let headline = Headline(phase: .settled, input: Self.headline(.settled, chance: .some(reading)))
            XCTAssertEqual(headline.chance, .unavailable("Unavailable"), name)
            let card = Comparison(phase: .settled, input: Self.comparison(.settled, baseline: .some(reading)))
            XCTAssertEqual(card.baseline, .unavailable("Unavailable"), name)
            XCTAssertEqual(card.actual, .value(figure: "$1.70", date: Self.reportedActual.date), "\(name): the actual is not the chance")
        }
        for (name, reading) in unknown {
            XCTAssertFalse(Rule.isKnown(reading), name)
            XCTAssertFalse(Rule.isShown(reading), name)
            XCTAssertEqual(Rule.display(reading, unavailable: "Unavailable"), .unavailable("Unavailable"), name)
            XCTAssertEqual(Rule.known(reading, unavailable: "Unavailable"), .unavailable("Unavailable"), name)
            let headline = Headline(phase: .settled, input: Self.headline(.settled, chance: .some(reading), actual: .some(reading)))
            XCTAssertEqual(headline.chance, .unavailable("Unavailable"), name)
            XCTAssertEqual(headline.actual, .unavailable("Unavailable"), name)
            XCTAssertFalse(Self.mentions(headline.words, "10¢ above $1.60"), "\(name): no relation without the actual")
            XCTAssertEqual(headline.spokenChance, "Pre-report chance: Unavailable", name)
            let card = Comparison(phase: .settled, input: Self.comparison(.settled, baseline: .some(reading), actual: .some(reading)))
            XCTAssertEqual(card.baseline, .unavailable("Unavailable"), name)
            XCTAssertEqual(card.actual, .unavailable("Unavailable"), name)
            XCTAssertNil(card.delta, "\(name): no difference without the actual")
            XCTAssertNil(card.actualPlacement, name)
            // A broken reading never borrows the threshold's position or the other unit's figure.
            XCTAssertEqual(card.thresholdPlacement, Self.thresholdPlacement, name)
            XCTAssertFalse(Self.mentions(card.words, "88%"), name)
        }
        // Real 0 and real 1 are readings, never refused or clamped.
        for edge in [0.0, 1.0] {
            XCTAssertTrue(Rule.isShown(Reading(id: good.id, figure: Self.percent(edge), date: good.date, placement: edge)))
        }
        // The contract result needs readable words; blank provenance is dropped, never invented.
        XCTAssertEqual(Rule.result(Self.resolution, unavailable: "U"),
                       .result(words: "Yes · contract resolved", provenance: "Provider resolution · separate from the company report"))
        XCTAssertEqual(Rule.result(EarningsResult10868(words: "Yes · contract resolved", provenance: " "), unavailable: "U"),
                       .result(words: "Yes · contract resolved", provenance: nil))
        XCTAssertEqual(Rule.result(EarningsResult10868(words: "  ", provenance: "Provider"), unavailable: "U"), .unavailable("U"))
        XCTAssertEqual(Rule.result(nil, unavailable: "U"), .unavailable("U"))
    }

    // MARK: - Earnings against the fixed threshold

    func testTheEarningsBarDrawsTheActualAgainstTheFixedThresholdOnAUSDAxisFromZero() throws {
        let baselineDate = Self.full(Double(Self.last.t))
        let actualDate = "Published \(Self.full(Self.publishedEpoch))"
        let before = try XCTUnwrap(Self.page(Self.input(.beforeReport), log: Log()).comparisonContent()).model
        XCTAssertEqual(before.parts, [.eyebrow, .baseline, .title, .figures, .unit, .bar, .caption])
        XCTAssertEqual(before.words(.eyebrow), ["Expectation → earnings per share"])
        XCTAssertEqual(before.words(.baseline), ["Last recorded before report", "Chance to beat $1.60", "88%", baselineDate])
        XCTAssertEqual(before.words(.title), ["The number to beat"])
        XCTAssertEqual(before.words(.figures), ["Contract threshold", "$1.60"])
        XCTAssertEqual(before.words(.unit), ["Diluted GAAP EPS · quarter ended Sep 30"])
        XCTAssertEqual(before.words(.bar), ["$0", "$1", "$2", "USD per diluted share · scale starts at $0"])
        XCTAssertEqual(before.words(.caption), ["A result must be higher than $1.60 to count as a beat."])
        XCTAssertEqual(before.barSpoken, "Contract threshold $1.60. Actual not yet shown.")
        XCTAssertTrue(before.isDrawable)
        XCTAssertEqual(before.ticks.map(\.label), ["$0", "$1", "$2"])
        XCTAssertEqual(before.ticks.map(\.placement), [0, 0.5, 1])
        XCTAssertEqual(before.thresholdPlacement, 0.8)
        XCTAssertNil(before.actual)
        XCTAssertNil(before.actualPlacement, "before the report there is no actual bar")
        XCTAssertNil(before.delta)
        XCTAssertNil(before.result)

        for phase in [Phase.companyReport, .settled] {
            let card = try XCTUnwrap(Self.page(Self.input(phase), log: Log()).comparisonContent()).model
            XCTAssertEqual(card.words(.title), ["Above the bar"], "\(phase)")
            XCTAssertEqual(card.words(.figures), ["Reported actual", "$1.70", actualDate, "Above threshold", "+10¢"], "\(phase)")
            XCTAssertEqual(card.words(.threshold),
                           ["Contract threshold", "$1.60", "Strictly greater than $1.60 diluted GAAP EPS"], "\(phase)")
            XCTAssertEqual(card.words(.caption), ["Reported earnings cleared the fixed threshold by 10¢ per share."], "\(phase)")
            XCTAssertEqual(card.barSpoken,
                           "Reported actual $1.70 versus contract threshold $1.60. Dollar scale starts at zero.", "\(phase)")
            XCTAssertEqual(card.actualPlacement, 0.85, "\(phase)")
            XCTAssertEqual(card.thresholdPlacement, 0.8, "\(phase)")
            XCTAssertEqual(card.delta, EarningsDelta10868(label: "Above threshold", figure: "+10¢"), "\(phase)")
            XCTAssertEqual(card.spokenActual, "Reported actual: $1.70, \(actualDate)", "\(phase)")
            XCTAssertEqual(card.spokenBaseline, "Last recorded before report, Chance to beat $1.60: 88%, \(baselineDate)", "\(phase)")
            XCTAssertEqual(card.words, card.parts.flatMap { card.words($0) }, "\(phase)")
        }
        let report = Comparison(phase: .companyReport, input: Self.comparison(.companyReport))
        XCTAssertEqual(report.parts, [.eyebrow, .baseline, .title, .figures, .unit, .bar, .threshold, .caption, .settlement])
        XCTAssertEqual(report.words(.settlement), ["Company result shown · market settlement not included"])
        XCTAssertNil(report.result)
        let settled = Comparison(phase: .settled, input: Self.comparison(.settled))
        XCTAssertEqual(settled.parts, [.eyebrow, .baseline, .title, .figures, .unit, .bar, .threshold, .caption, .result])
        XCTAssertEqual(settled.words(.result),
                       ["Contract result", "Yes · contract resolved", "Provider resolution · separate from the company report"])
        // The owner's unit words agree with the retained quarter end.
        XCTAssertEqual(Self.formatted(Self.epoch(Self.capture.company.quarterEnded + "T12:00:00Z"), "MMM d"), "Sep 30")

        // Positions come from the owner's placements on a finite width — never from dollars here.
        XCTAssertEqual(try XCTUnwrap(Geometry.x(0.85, width: 200)), 170, accuracy: 0.0001)
        XCTAssertEqual(try XCTUnwrap(Geometry.x(0.8, width: 200)), 160, accuracy: 0.0001)
        XCTAssertEqual(Geometry.x(0, width: 200), 0)
        XCTAssertEqual(Geometry.x(1, width: 200), 200)
    }

    func testTheBarRefusesAnInvalidAxisAndOutOfRangePlacementsWithoutClamping() throws {
        let words = Self.usdAxis.words
        let ticks = Self.usdAxis.ticks
        XCTAssertTrue(Geometry.isValid(Self.usdAxis), "positive control")
        let axes: [(String, EarningsAxis10868)] = [
            ("not from zero", EarningsAxis10868(lower: 1, upper: 2, ticks: ticks, words: words, offAxis: Self.offAxisWords, unavailable: "Dollar scale unavailable")),
            ("below zero", EarningsAxis10868(lower: -0.5, upper: 2, ticks: ticks, words: words, offAxis: Self.offAxisWords, unavailable: "Dollar scale unavailable")),
            ("empty", EarningsAxis10868(lower: 0, upper: 0, ticks: ticks, words: words, offAxis: Self.offAxisWords, unavailable: "Dollar scale unavailable")),
            ("reversed", EarningsAxis10868(lower: 0, upper: -2, ticks: ticks, words: words, offAxis: Self.offAxisWords, unavailable: "Dollar scale unavailable")),
            ("infinite", EarningsAxis10868(lower: 0, upper: .infinity, ticks: ticks, words: words, offAxis: Self.offAxisWords, unavailable: "Dollar scale unavailable")),
            ("not a number", EarningsAxis10868(lower: .nan, upper: 2, ticks: ticks, words: words, offAxis: Self.offAxisWords, unavailable: "Dollar scale unavailable")),
        ]
        let figures = Comparison(phase: .settled, input: Self.comparison(.settled)).words(.figures)
        for (name, axis) in axes {
            XCTAssertFalse(Geometry.isValid(axis), name)
            let card = Comparison(phase: .settled, input: Self.comparison(.settled, axis: axis))
            XCTAssertFalse(card.isDrawable, name)
            XCTAssertEqual(card.ticks, [], name)
            XCTAssertNil(card.thresholdPlacement, name)
            XCTAssertNil(card.actualPlacement, name)
            XCTAssertEqual(card.words(.bar), ["Dollar scale unavailable"], name)
            XCTAssertEqual(card.barSpoken, "Dollar scale unavailable", name)
            // The figures still read as text, each with its own date.
            XCTAssertEqual(card.words(.figures), figures, name)
        }

        // Ticks outside 0…1, not finite or unlabelled are not drawn; the rest keep the owner's order.
        let mixed = EarningsAxis10868(lower: 0, upper: 2, ticks: [
            EarningsAxisTick10868(placement: -0.1, label: "-$0.20"), EarningsAxisTick10868(placement: 0, label: "$0"),
            EarningsAxisTick10868(placement: 0.5, label: " "), EarningsAxisTick10868(placement: 1, label: "$2"),
            EarningsAxisTick10868(placement: 1.2, label: "$2.40"), EarningsAxisTick10868(placement: .nan, label: "?"),
        ], words: words, offAxis: Self.offAxisWords, unavailable: "Dollar scale unavailable")
        XCTAssertEqual(Comparison(phase: .settled, input: Self.comparison(.settled, axis: mixed)).ticks.map(\.label), ["$0", "$2"])

        // A threshold outside the axis is not drawn and never clamped; its words stay.
        for placement in [-0.2, 1.2, Double.nan, .infinity] {
            let card = Comparison(phase: .settled, input: Self.comparison(.settled, thresholdAt: placement))
            XCTAssertNil(card.thresholdPlacement, "\(placement)")
            XCTAssertEqual(card.words(.threshold),
                           ["Contract threshold", "$1.60", "Strictly greater than $1.60 diluted GAAP EPS"], "\(placement)")
            XCTAssertEqual(card.actualPlacement, 0.85, "\(placement): the actual keeps its own place")
        }
        // A known actual placed off the axis keeps its figure, date and difference; only its bar is withheld,
        // with the owner's off-axis words — never clamped to the end.
        let far = Reading(id: "company-release", figure: "$1.70", date: Self.reportedActual.date, placement: 1.4)
        let offScale = Comparison(phase: .settled, input: Self.comparison(.settled, actual: far))
        XCTAssertEqual(offScale.actual, .value(figure: "$1.70", date: Self.reportedActual.date))
        XCTAssertNil(offScale.actualPlacement)
        XCTAssertEqual(offScale.delta, EarningsDelta10868(label: "Above threshold", figure: "+10¢"))
        XCTAssertEqual(offScale.words(.figures), figures)
        XCTAssertEqual(offScale.offAxis, Self.offAxisWords)
        XCTAssertEqual(offScale.words(.bar).last, Self.offAxisWords)
        XCTAssertNil(Comparison(phase: .settled, input: Self.comparison(.settled)).offAxis, "positive control: on the scale")
        // An unknown actual (no figure) is unknown — no bar, no difference.
        let unnamed = Reading(id: "company-release", figure: " ", date: Self.reportedActual.date, placement: 0.85)
        let refused = Comparison(phase: .settled, input: Self.comparison(.settled, actual: unnamed))
        XCTAssertEqual(refused.actual, .unavailable("Unavailable"))
        XCTAssertNil(refused.actualPlacement)
        XCTAssertNil(refused.delta)
        XCTAssertEqual(refused.words(.figures), ["Reported actual", "Unavailable"])
        // A difference without words is not shown; the actual stays.
        let silent = Comparison(phase: .settled, input: Self.comparison(.settled, delta: EarningsDelta10868(label: "Above threshold", figure: " ")))
        XCTAssertNil(silent.delta)
        XCTAssertEqual(silent.words(.figures), ["Reported actual", "$1.70", Self.reportedActual.date])

        // Geometry refuses unusable widths and placements.
        for width in [CGFloat(0), -10, .nan, .infinity] {
            XCTAssertNil(Geometry.x(0.5, width: width), "\(width)")
        }
        for placement in [-0.1, 1.1, Double.nan, .infinity] {
            XCTAssertNil(Geometry.x(placement, width: 200), "\(placement)")
        }
    }

    func testProbabilityPlacementStaysIndependentOfTheUSDActualAndTheContractGrade() throws {
        let page = Self.page(Self.input(.settled), log: Log())
        let history = try XCTUnwrap(page.historyContent(reader: false)).input
        let headline = try XCTUnwrap(page.headlineContent()).model
        let card = try XCTUnwrap(page.comparisonContent()).model
        let resolvedNo = EarningsResult10868(words: "No · contract resolved", provenance: nil)
        let lower = Reading(id: "company-release", figure: "$1.50", date: Self.reportedActual.date, placement: 0.75)
        let variants: [(String, Bundle)] = [
            ("no actual", Self.bundle(.settled, headline: Self.headline(.settled, actual: .some(nil)),
                                      comparison: Self.comparison(.settled, actual: .some(nil)))),
            ("no grade", Self.bundle(.settled, headline: Self.headline(.settled, result: .some(nil)),
                                     comparison: Self.comparison(.settled, result: .some(nil)))),
            ("other grade", Self.bundle(.settled, headline: Self.headline(.settled, result: resolvedNo),
                                        comparison: Self.comparison(.settled, result: resolvedNo))),
            ("other actual", Self.bundle(.settled, headline: Self.headline(.settled, actual: lower),
                                         comparison: Self.comparison(.settled, actual: lower))),
        ]
        for (name, bundle) in variants {
            let other = Self.page(Self.input(.settled, bundle: bundle), log: Log())
            XCTAssertEqual(other.historyContent(reader: false)?.input, history, name)
            XCTAssertEqual(other.headlineContent()?.model.chance, headline.chance, name)
            XCTAssertEqual(other.comparisonContent()?.model.baseline, card.baseline, name)
        }
        // The pre-report mark sits at its own probability on the 0–100% scale.
        let series = try XCTUnwrap(history.series.first)
        let pre = try XCTUnwrap(History.uniquePoint(Self.pointID(Self.last.t), in: series))
        XCTAssertEqual(History.probabilityFraction(pre.probability, ceiling: history.ceiling), 0.88)
        XCTAssertEqual(history.ceiling, 1)
        XCTAssertEqual(history.probabilityLowerBound, 0)

        // The chance never moves the dollar bar.
        let earlierChance = Comparison(phase: .settled, input: Self.comparison(.settled, baseline: Self.chance(Self.first)))
        XCTAssertNotEqual(earlierChance.baseline, card.baseline)
        XCTAssertEqual(earlierChance.actualPlacement, card.actualPlacement)
        XCTAssertEqual(earlierChance.thresholdPlacement, card.thresholdPlacement)
        XCTAssertEqual(earlierChance.ticks, card.ticks)
        XCTAssertEqual(earlierChance.actual, card.actual)
        // And the probability is never a position on the dollar axis.
        XCTAssertNotEqual(card.actualPlacement, Self.last.p)
        XCTAssertFalse(card.ticks.contains { $0.placement == Self.last.p })
    }

    // MARK: - The shared probability history

    func testTheHistoryKeepsAll308YesObservationsWithTheirOwnClocksPositionsAndNoInventedPoints() throws {
        let retained = try XCTUnwrap(Self.page(Self.input(.beforeReport), log: Log()).historyContent(reader: false)).input
        for phase in Phase.allCases {
            let history = try XCTUnwrap(Self.page(Self.input(phase), log: Log()).historyContent(reader: false)).input
            XCTAssertEqual(history.series.count, 1, "\(phase): only the Yes history; no No line")
            let series = try XCTUnwrap(history.series.first)
            XCTAssertEqual(series.id, Self.seriesID)
            XCTAssertEqual(series.name, "Yes")
            let drawn = series.runs.flatMap(\.points)
            XCTAssertEqual(drawn.count, 308, "\(phase)")
            XCTAssertEqual(drawn.map(\.id), Self.points.map { Self.pointID($0.t) }, "\(phase)")
            XCTAssertEqual(drawn.map(\.x), Self.points.map { Double($0.t) }, "\(phase): original clocks")
            XCTAssertEqual(drawn.map(\.probability), Self.points.map(\.p), "\(phase): original positions")
            XCTAssertTrue(drawn.allSatisfy { $0.style == .hollow }, "\(phase): every mark is before the report")
            XCTAssertEqual(History.marks(series, in: history).count, 308, "\(phase)")
            let lines = History.lines(series, in: history)
            XCTAssertEqual(lines.map(\.count), [308], "\(phase): one run, no break invented")
            XCTAssertEqual(history.breaks, [], "\(phase)")
            XCTAssertEqual(history.domain, FieldHistoryDomain10868(lower: Double(Self.first.t), upper: Double(Self.last.t)))
            XCTAssertFalse(drawn.contains { $0.probability == 0 || $0.probability == 1 }, "\(phase): no terminal endpoint")
            XCTAssertFalse(drawn.contains { $0.x >= Self.publishedEpoch }, "\(phase): nothing after the report")
            XCTAssertEqual(history.ceiling, 1)
            XCTAssertEqual(history.probabilityLowerBound, 0)
            XCTAssertEqual(history.yTicks.map(\.lines), [["0%"], ["50%"], ["100%"]])
            // Endpoints first, then the middle, each a local day.
            XCTAssertEqual(history.xTicks.map(\.value), [Self.first, Self.last, Self.points[154]].map { Double($0.t) })
            XCTAssertEqual(history.xTicks.map(\.lines), [Self.first, Self.last, Self.points[154]].map { [Self.day(Double($0.t))] })
            XCTAssertTrue(History.drawsStyle(.hollow, in: history))
            XCTAssertFalse(History.drawsStyle(.filled, in: history))
            XCTAssertEqual(history, retained, "\(phase): a later phase adds no point, no smoother and no end")
        }
        let words = Self.historyWords(retained)
        // Never a UTC clock, never a live quote.
        XCTAssertTrue(Self.mentions(["Recorded 20:00 UTC"], "UTC"), "positive control")
        XCTAssertTrue(Self.mentions(["a live quote"], "live"), "positive control")
        for token in ["UTC", "GMT", "live", "Live", "current", "Current"] {
            XCTAssertFalse(Self.mentions(words, token), token)
        }
        // The plot stays compact: one short line beside the hollow-before-report key. The source caveats
        // (Yes history only, no complement or endpoint, device time) are in Info, not on the plot.
        XCTAssertEqual(retained.notes, ["All 308 observations precede the company report."])
        XCTAssertEqual(retained.markKey.hollow, "Hollow marks: before the report.")
        let info = try XCTUnwrap(Self.page(Self.input(.beforeReport), log: Log()).aboutContent())
        let recorded = try XCTUnwrap(info.sections.first { $0.title == "Recorded chances" })
        XCTAssertTrue(recorded.paragraphs.contains(
            "Only the Yes history is supplied. No complementary No line or terminal 100% endpoint is invented. Times follow your device."))
        XCTAssertTrue(recorded.paragraphs[0].contains("Polymarket supplies 308 probability-history observations."))
        XCTAssertFalse(words.contains { $0.contains("Times follow your device") }, "device-time copy belongs to Info")

        // The owner's own gap stays open: two runs, the break, every mark — the page never joins them.
        let gapped = Self.history(splitAt: 100)
        let shown = try XCTUnwrap(Self.page(Self.input(.settled, bundle: Self.bundle(.settled, history: gapped)), log: Log())
            .historyContent(reader: false)).input
        let series = try XCTUnwrap(shown.series.first)
        XCTAssertEqual(series.runs.map(\.id), ["before-gap", "after-gap"])
        XCTAssertEqual(History.lines(series, in: shown).map(\.count), [100, 208])
        XCTAssertEqual(History.marks(series, in: shown).count, 308)
        XCTAssertEqual(shown.breaks.map(\.id), ["gap"])
        XCTAssertEqual(shown.series, gapped.series)
        // An observation the owner leaves out stays out: nothing is interpolated in its place.
        let thinned = Array(Self.points.enumerated().filter { $0.offset % 2 == 0 }.map(\.element))
        let sparse = try XCTUnwrap(Self.page(Self.input(.settled, bundle: Self.bundle(
            .settled, history: Self.history(retained: thinned))), log: Log()).historyContent(reader: false)).input
        XCTAssertEqual(sparse.series.first?.runs.flatMap(\.points).map(\.x), thinned.map { Double($0.t) })
    }

    func testTheHistoryReadoutCollapsesOnlyForTheExactSameObservationAndInspectionNeverReplacesTheComparator() throws {
        let lastDate = Self.full(Double(Self.last.t))
        func shown(_ history: FieldHistoryInput10868) throws -> FieldHistoryInput10868 {
            try XCTUnwrap(Self.page(Self.input(.settled, bundle: Self.bundle(.settled, history: history)), log: Log())
                .historyContent(reader: false)).input
        }
        func slots(_ input: FieldHistoryInput10868) throws -> [[String]] {
            History.readoutSlots(try XCTUnwrap(input.series.first), in: input).map { Self.slotWords($0) }
        }
        // Inspecting the last recorded observation: one slot — the same observation is never shown twice.
        let atLast = try shown(Self.history())
        XCTAssertEqual(atLast.readout, .singleBefore(label: "Last recorded before report"))
        XCTAssertEqual(try slots(atLast), [["Last recorded before report", "88%", lastDate]])
        // Inspecting the first: two slots, and the comparator stays the pre-report observation.
        let atFirst = try shown(Self.history(inspected: 0))
        XCTAssertEqual(atFirst.readout, .beforeAndInspected(beforeLabel: "Last recorded before report",
                                                            inspectedLabel: "First recorded before report"))
        XCTAssertEqual(try slots(atFirst), [["Last recorded before report", "88%", lastDate],
                                            ["First recorded before report", "53%", Self.full(Double(Self.first.t))]])
        let middle = Self.points[154]
        XCTAssertEqual(try slots(try shown(Self.history(inspected: 154))),
                       [["Last recorded before report", "88%", lastDate],
                        ["Inspected before report", "79%", Self.full(Double(middle.t))]])
        // A reading bound to another observation is not shown as the inspected one — never a neighbour's figure.
        let mismatched = try shown(Self.history(inspected: 154, recorded: Self.observation(Self.points[153])))
        XCTAssertEqual(try slots(mismatched)[1], ["Inspected before report", "Not recorded at this observation"])
        // Nothing inspected: the pre-report slot stays; no collapse is claimed.
        let idle = try shown(Self.history(inspecting: false))
        XCTAssertEqual(idle.readout, .beforeAndInspected(beforeLabel: "Last recorded before report",
                                                         inspectedLabel: "Inspected before report"))
        XCTAssertEqual(try slots(idle)[0], ["Last recorded before report", "88%", lastDate])

        // Inspection never changes the headline, the earnings card or the held original.
        let base = Self.page(Self.input(.settled), log: Log())
        let headline = try XCTUnwrap(base.headlineContent()).model
        let card = try XCTUnwrap(base.comparisonContent()).model
        for index in [0, 154, 307] {
            let page = Self.page(Self.input(.settled, bundle: Self.bundle(.settled, history: Self.history(inspected: index))), log: Log())
            XCTAssertEqual(page.headlineContent()?.model, headline, "\(index)")
            XCTAssertEqual(page.comparisonContent()?.model, card, "\(index)")
            XCTAssertEqual(page.originalDetailsContent()?.selection, Self.heldSelection, "\(index)")
            XCTAssertEqual(page.earningsWords(at: .page), base.earningsWords(at: .page), "\(index)")
        }
    }

    func testTheReaderHistoryIsTallerOnlyByAFiniteOwnerHeightAndDropsOnlyExpand() throws {
        let page = try XCTUnwrap(Self.page(Self.input(.settled), log: Log()).historyContent(reader: false)).input
        XCTAssertEqual(page.plotHeight, 220)
        XCTAssertEqual(page.expand?.id, "expand-history")
        let heights: [(CGFloat?, CGFloat)] = [(nil, 220), (.nan, 220), (-1, 220), (0, 220), (.infinity, 220), (100, 220), (360, 360)]
        for (owner, expected) in heights {
            let reader = try XCTUnwrap(Self.page(Self.input(.settled, readerPlotHeight: owner), log: Log())
                .historyContent(reader: true)).input
            XCTAssertEqual(reader.plotHeight, expected, "\(String(describing: owner))")
            XCTAssertNil(reader.expand, "full size has no expand")
            XCTAssertEqual(reader.series, page.series)
            XCTAssertEqual(reader.domain, page.domain)
            XCTAssertEqual(reader.yTicks, page.yTicks)
            XCTAssertEqual(reader.xTicks, page.xTicks)
            XCTAssertEqual(reader.breaks, page.breaks)
            XCTAssertEqual(reader.readout, page.readout)
            XCTAssertEqual(reader.markKey, page.markKey)
            XCTAssertEqual(reader.notes, page.notes)
            XCTAssertEqual(reader.summary, page.summary)
            XCTAssertEqual(reader.previous, page.previous)
            XCTAssertEqual(reader.next, page.next)
            XCTAssertEqual(reader.inspection, page.inspection)
            XCTAssertEqual(reader.showsKey, page.showsKey)
        }
    }

    // MARK: - One phase-admitted bundle behind every surface

    func testEverySurfaceRefusesABundleFromAnotherPhaseAndKeepsOnlyBack() throws {
        for pagePhase in Phase.allCases {
            for bundlePhase in Phase.allCases {
                let name = "\(pagePhase) page, \(bundlePhase) bundle"
                let log = Log()
                let page = Self.page(Self.input(pagePhase, bundle: Self.bundle(bundlePhase)), log: log)
                let model = page.model
                let admitted = pagePhase == bundlePhase
                XCTAssertEqual(model.bundle != nil, admitted, name)
                let surfaces: [(String, Bool)] = [
                    ("headline", page.headlineContent() != nil),
                    ("earnings card", page.comparisonContent() != nil),
                    ("history", page.historyContent(reader: false) != nil),
                    ("full-size history", page.historyContent(reader: true) != nil),
                    ("full-size history card", model.readerShows(.history)),
                    ("full-size earnings card", model.readerShows(.earnings)),
                    ("Info", page.aboutContent() != nil),
                    ("source", page.sourceContent("rules") != nil),
                    ("catalogue", page.catalogueContent() != nil),
                    ("Details", page.originalDetailsContent() != nil),
                    ("side history", page.originalDetailsContent()?.recorded != nil),
                    ("story", model.story("earnings") != nil),
                    ("About action", page.aboutAction(at: .page) != nil),
                    ("Details action", page.detailsAction(at: .page) != nil),
                    ("stream Details action", page.detailsAction(at: .stream(Self.activation(log))) != nil),
                    ("All props", page.allPropsAction() != nil),
                    ("stream intents", page.storyIntent() != nil),
                    ("previous", page.stepAction(.previous, from: .earnings) != nil),
                    ("next", page.stepAction(.next, from: .history) != nil),
                ]
                for (surface, mounted) in surfaces {
                    XCTAssertEqual(mounted, admitted, "\(name): \(surface)")
                }
                if !admitted {
                    XCTAssertEqual(Self.reachable(page), [Self.pageCopy.phaseUnavailable], "\(name): only the owner's words")
                    XCTAssertEqual(page.earningsWords(at: .page), [], name)
                }
                XCTAssertTrue(log.events.isEmpty, "\(name): building calls nothing")
                // Back stays, exact, whatever the bundle.
                let back = try XCTUnwrap(page.backAction(), name)
                back()
                XCTAssertEqual(log.events, ["back"], name)
            }
        }
        // Without its callback, Back is not drawn as a dead control.
        XCTAssertNil(Page(input: Self.input(.settled, bundle: Self.bundle(.beforeReport))).backAction())
    }

    func testAnOldSettledBundleNeverLeaksIntoEarlierContent() throws {
        let leaked = Self.page(Self.input(.beforeReport, bundle: Self.bundle(.settled)), log: Log())
        XCTAssertNil(leaked.model.headline)
        XCTAssertNil(leaked.model.comparison)
        XCTAssertNil(leaked.model.history(reader: false))
        XCTAssertNil(leaked.model.originals)
        XCTAssertNil(leaked.originalDetailsContent())
        XCTAssertNil(leaked.catalogueContent())
        let words = Self.reachable(leaked)
        for word in ["$1.70", "Yes · contract resolved", "88%", "$1.60", "Above the bar", "Unity Bancorp"] {
            XCTAssertFalse(Self.mentions(words, word), word)
        }
        // Positive control: the matching bundle shows the chance and the threshold — still no actual or result.
        let matched = Self.page(Self.input(.beforeReport), log: Log())
        let shown = Self.reachable(matched)
        XCTAssertTrue(Self.mentions(shown, "88%"))
        XCTAssertTrue(Self.mentions(shown, "$1.60"))
        XCTAssertFalse(Self.mentions(shown, "$1.70"))
        XCTAssertFalse(Self.mentions(shown, "Yes · contract resolved"))
        let details = try XCTUnwrap(matched.originalDetailsContent())
        XCTAssertNil(Details.content(catalogue: details.catalogue, selection: details.selection)?.result)
        XCTAssertNil(details.recorded?.finish, "no reported actual in the before-report side history")

        // No forced final phase and no coercion either way: a report-only bundle under a settled page is refused too.
        let early = Self.page(Self.input(.settled, bundle: Self.bundle(.companyReport)), log: Log())
        XCTAssertEqual(Self.reachable(early), [Self.pageCopy.phaseUnavailable])
        let late = Self.page(Self.input(.companyReport, bundle: Self.bundle(.settled)), log: Log())
        XCTAssertEqual(Self.reachable(late), [Self.pageCopy.phaseUnavailable])
        // Positive control for the same pair, admitted.
        let report = Self.page(Self.input(.companyReport), log: Log())
        XCTAssertTrue(Self.mentions(Self.reachable(report), "Company reported · settlement not included"))
        XCTAssertFalse(Self.mentions(Self.reachable(report), "Yes · contract resolved"))
    }

    // MARK: - Actions, holds, traversal and selections

    static let allModes: [Mode] = [.page, .reader(.history), .reader(.earnings), .catalogue, .original, .about, .source("rules")]

    static var detailsEvent: String { "details:\(scope):\(evidence.atlasRow._market_id):\(evidence.atlasRow.id)" }

    func testEveryPageActionHoldsOnceStreamActionsRequestTheStreamAndFullSizeIsExact() throws {
        let input = Self.input(.settled)
        // On the page: the hook once, then the exact callback with its exact value.
        let log = Log()
        let page = Self.page(input, log: log)
        try XCTUnwrap(page.aboutAction(at: .page))()
        try XCTUnwrap(page.headlineContent()?.onAbout)()
        try XCTUnwrap(page.detailsAction(at: .page))()
        try XCTUnwrap(page.allPropsAction())()
        XCTAssertEqual(log.events, ["hold", "about", "hold", "about", "hold", Self.detailsEvent, "hold", "allProps"])
        log.events = []
        let history = try XCTUnwrap(page.historyContent(reader: false))
        history.onAction?("expand-history")
        history.onInspectionChoice?(Self.pointID(Self.first.t))
        history.onPlotPosition?(Double(Self.points[154].t))
        XCTAssertEqual(log.events, ["hold", "history:expand-history", "hold", "inspect:\(Self.pointID(Self.first.t))",
                                    "hold", "plot:\(Double(Self.points[154].t))"])
        log.events = []
        // The catalogue, Details and Info sheets are held the same way.
        try XCTUnwrap(page.catalogueContent()?.onSelect)(Self.heldSelection)
        try XCTUnwrap(page.originalDetailsContent()?.onHistory)(
            Details.HistoryIntent(selection: Self.heldSelection, entry: .expand, actionID: "original-history"))
        let about = try XCTUnwrap(page.aboutContent())
        try XCTUnwrap(about.linkAction(Self.releaseLink))()
        try XCTUnwrap(about.sourceAction("rules"))()
        let source = try XCTUnwrap(page.sourceContent("rules"))
        XCTAssertNil(source.sourceAction("rules"), "a source document opens no further source")
        XCTAssertEqual(log.events, ["hold", "select:\(Self.evidence.atlasRow._market_id)", "hold", "originalHistory:original-history",
                                    "hold", "link:company-release:\(Self.capture.company.url)", "hold", "source:rules"])

        // In a story card: the card's own action requests the stream's interaction once — never the page hook.
        let streamLog = Log()
        let streamPage = Self.page(input, log: streamLog)
        try XCTUnwrap(streamPage.detailsAction(at: .stream(Self.activation(streamLog))))()
        XCTAssertEqual(streamLog.events, [Self.interaction, Self.detailsEvent])
        streamLog.events = []
        // The shell's own intents reach the owner exactly; the shell requests its interaction itself.
        try XCTUnwrap(streamPage.storyIntent())(.open(Self.earningsCard))
        XCTAssertEqual(streamLog.events, ["story:\(Stream.Intent.open(Self.earningsCard))"])

        // Full size: exact callbacks, no hold.
        let readerLog = Log()
        let reader = Self.page(input, .reader(.earnings), log: readerLog)
        try XCTUnwrap(reader.detailsAction(at: .reader))()
        try XCTUnwrap(reader.aboutAction(at: .reader))()
        try XCTUnwrap(reader.historyContent(reader: true)).onAction?("earlier")
        try XCTUnwrap(reader.stepAction(.previous, from: .earnings))()
        try XCTUnwrap(reader.backAction())()
        XCTAssertEqual(readerLog.events, [Self.detailsEvent, "about", "history:earlier", "step:history", "back"])

        // Without a hook: the exact callback, still once.
        let bareLog = Log()
        try XCTUnwrap(Self.page(input, log: bareLog, hook: false).aboutAction(at: .page))()
        XCTAssertEqual(bareLog.events, ["about"])
    }

    func testWithoutCallbacksNothingActsAndBuildingOrLayingOutCallsNothing() throws {
        let page = Page(input: Self.input(.settled))
        let silent = StoryStreamCardActivation10868(card: Self.earningsCard, intents: [], send: nil)
        XCTAssertNil(page.aboutAction(at: .page))
        XCTAssertNil(page.aboutAction(at: .reader))
        XCTAssertNil(page.detailsAction(at: .page))
        XCTAssertNil(page.detailsAction(at: .stream(silent)))
        XCTAssertNil(page.detailsAction(at: .reader))
        XCTAssertNil(page.allPropsAction())
        XCTAssertNil(page.storyIntent())
        XCTAssertNil(page.stepAction(.previous, from: .earnings))
        XCTAssertNil(page.stepAction(.next, from: .history))
        XCTAssertNil(page.backAction())
        XCTAssertNil(try XCTUnwrap(page.headlineContent()).onAbout)
        let history = try XCTUnwrap(page.historyContent(reader: false))
        XCTAssertNil(history.onAction)
        XCTAssertNil(history.onInspectionChoice)
        XCTAssertNil(history.onPlotPosition)
        XCTAssertNil(try XCTUnwrap(page.catalogueContent()).onSelect)
        XCTAssertNil(try XCTUnwrap(page.originalDetailsContent()).onHistory)
        let about = try XCTUnwrap(page.aboutContent())
        XCTAssertNil(about.onLink)
        XCTAssertNil(about.onSource)
        XCTAssertNil(about.linkAction(Self.releaseLink))
        XCTAssertNil(about.sourceAction("rules"))
        // A control without its action is not offered in words either; the static content stays.
        let words = page.earningsWords(at: .page)
        XCTAssertFalse(Self.mentions(words, "Original market & source details"))
        XCTAssertTrue(Self.mentions(words, "$1.70"))
        XCTAssertTrue(Self.mentions(Self.page(Self.input(.settled), log: Log()).earningsWords(at: .page),
                                    "Original market & source details"), "positive control")

        // Building and laying out every mode, with every callback present, calls nothing.
        let log = Log()
        for mode in Self.allModes {
            let host = hostForMeasurement(Self.page(Self.input(.settled), mode, log: log), at: .large)
            host.view.frame = CGRect(x: 0, y: 0, width: 393, height: 2000)
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            _ = host.sizeThatFits(in: CGSize(width: 393, height: .greatestFiniteMagnitude))
        }
        XCTAssertTrue(log.events.isEmpty, "nothing acts on appear or layout")
    }

    func testPreviousAndNextFollowTheOwnersReaderOrderAndBackIsExact() throws {
        let history = EarningsReaderStop10868(card: .history, name: "Chance to beat $1.60")
        let earnings = EarningsReaderStop10868(card: .earnings, name: "Earnings against expectations")
        func names(_ order: [EarningsReaderStop10868], from card: Card) -> [String?] {
            let model = Model(Self.input(.settled, bundle: Self.bundle(.settled, readerOrder: order)))
            return [model.neighbour(.previous, of: card)?.name, model.neighbour(.next, of: card)?.name]
        }
        XCTAssertEqual(names([history, earnings], from: .history), [nil, "Earnings against expectations"])
        XCTAssertEqual(names([history, earnings], from: .earnings), ["Chance to beat $1.60", nil])
        // The owner's order, never the enum's.
        XCTAssertEqual(names([earnings, history], from: .history), ["Earnings against expectations", nil])
        XCTAssertEqual(names([earnings, history], from: .earnings), [nil, "Chance to beat $1.60"])
        // A card listed twice, a missing card or an unnamed neighbour is no position and no step.
        XCTAssertEqual(names([history, earnings, history], from: .history), [nil, nil])
        XCTAssertEqual(names([history, earnings, history], from: .earnings), [nil, nil])
        XCTAssertEqual(names([earnings], from: .history), [nil, nil])
        XCTAssertEqual(names([history, EarningsReaderStop10868(card: .earnings, name: " ")], from: .history), [nil, nil])
        XCTAssertFalse(Model(Self.input(.settled, bundle: Self.bundle(.settled, readerOrder: []))).readerShows(.history))
        XCTAssertFalse(Model(Self.input(.settled, bundle: Self.bundle(.settled, readerOrder: [earnings]))).readerShows(.history))
        XCTAssertTrue(Model(Self.input(.settled, bundle: Self.bundle(.settled, readerOrder: [earnings]))).readerShows(.earnings))

        // Steps hand back the owner's exact neighbour with no hold, even with the hook present.
        let log = Log()
        let reversed = Self.page(Self.input(.settled, bundle: Self.bundle(.settled, readerOrder: [earnings, history])),
                                 .reader(.history), log: log)
        try XCTUnwrap(reversed.stepAction(.previous, from: .history))()
        XCTAssertNil(reversed.stepAction(.next, from: .history))
        XCTAssertEqual(log.events, ["step:earnings"])
        // Back is exact in every mode and needs no admitted bundle.
        for mode in Self.allModes {
            let backLog = Log()
            let page = Self.page(Self.input(.beforeReport, bundle: Self.bundle(.settled)), mode, log: backLog)
            try XCTUnwrap(page.backAction(), "\(mode)")()
            XCTAssertEqual(backLog.events, ["back"], "\(mode)")
        }
        XCTAssertEqual(Self.pageCopy.backLabel, "Back to earnings")
    }

    func testOriginalDetailsAndCatalogueResolveOnlyTheExactCanonicalOriginal() throws {
        var payloads: [Details.Selection] = []
        let page = Page(input: Self.input(.settled), onOpenOriginal: { payloads.append($0) })
        XCTAssertEqual(page.model.heldOriginal, Self.heldSelection)
        try XCTUnwrap(page.detailsAction(at: .page))()
        try XCTUnwrap(page.detailsAction(at: .reader))()
        XCTAssertEqual(payloads, [Self.heldSelection, Self.heldSelection])
        XCTAssertEqual(Self.violations(payloads), [])

        // Bad future keys: another side, market, source or scope — refused, never the neighbour.
        let original = Self.identity
        let foreign: [(String, Details.Selection)] = [
            ("other side", Details.Selection(scope: Self.scope, identity: Details.Identity(
                source: original.source, market: original.market, side: "240153005"))),
            ("public market id", Details.Selection(scope: Self.scope, identity: Details.Identity(
                source: original.source, market: Self.capture.marketID, side: original.side))),
            ("other source", Details.Selection(scope: Self.scope, identity: Details.Identity(
                source: "kalshi", market: original.market, side: original.side))),
            ("other scope", Details.Selection(scope: "economics:later", identity: original)),
            ("blank side", Details.Selection(scope: Self.scope, identity: Details.Identity(
                source: original.source, market: original.market, side: ""))),
        ]
        for (name, selection) in foreign {
            XCTAssertEqual(Self.violations([selection]).count, 1, "\(name): the guard sees the foreign key")
            var refused: [Details.Selection] = []
            let other = Page(input: Self.input(.settled, bundle: Self.bundle(.settled, selection: selection)),
                             onOpenOriginal: { refused.append($0) })
            XCTAssertNil(other.model.heldOriginal, name)
            XCTAssertNil(other.detailsAction(at: .page), name)
            let details = try XCTUnwrap(other.originalDetailsContent(), name)
            XCTAssertNil(Details.content(catalogue: details.catalogue, selection: details.selection), name)
            XCTAssertTrue(refused.isEmpty, name)
        }

        // Two entries for one identity are none.
        let base = Self.bundle(.settled)
        let duplicated = FieldEventPageOriginals10868(
            catalogue: Details.Catalogue(scope: Self.scope, originals: [Self.original(.settled), Self.original(.settled)]),
            selection: Self.heldSelection, heading: "All props", emptyWords: "No original outcomes",
            unavailableChoice: "Original unavailable", tint: DS.blue)
        let twice = Bundle(phase: .settled, headline: base.headline, comparison: base.comparison, history: base.history,
                           reader: base.reader, about: base.about, sources: base.sources, stream: base.stream,
                           stories: base.stories, readerOrder: base.readerOrder, copy: base.copy, originals: duplicated)
        XCTAssertNil(Model(Self.input(.settled, bundle: twice)).heldOriginal)
        // Nothing held: no Details action; the catalogue still lists the one original.
        let unheld = Self.page(Self.input(.settled, bundle: Self.bundle(.settled, holdsOriginal: false)), log: Log())
        XCTAssertNil(unheld.detailsAction(at: .page))
        XCTAssertEqual(unheld.catalogueContent()?.catalogue?.originals.map(\.identity), [Self.identity])
        XCTAssertNil(unheld.originalDetailsContent()?.recorded)
        // No originals at all: no catalogue, Details, All props or Details action.
        let bare = Self.page(Self.input(.settled, bundle: Self.bundle(.settled, withOriginals: false)), log: Log())
        XCTAssertNil(bare.catalogueContent())
        XCTAssertNil(bare.originalDetailsContent())
        XCTAssertNil(bare.allPropsAction())
        XCTAssertNil(bare.detailsAction(at: .page))
    }

    func testHistoryAndOriginalSelectionsAreIndependent() throws {
        let base = Self.page(Self.input(.settled), log: Log())
        let history = try XCTUnwrap(base.historyContent(reader: false)).input
        // Changing the held original never changes the history, the headline or the earnings card.
        let unheld = Self.page(Self.input(.settled, bundle: Self.bundle(.settled, holdsOriginal: false)), log: Log())
        XCTAssertEqual(unheld.historyContent(reader: false)?.input, history)
        XCTAssertEqual(unheld.headlineContent()?.model, base.headlineContent()?.model)
        XCTAssertEqual(unheld.comparisonContent()?.model, base.comparisonContent()?.model)
        // Inspecting the history never changes the held original or its side history.
        let inspected = Self.page(Self.input(.settled, bundle: Self.bundle(.settled, history: Self.history(inspected: 0))), log: Log())
        XCTAssertEqual(inspected.model.heldOriginal, Self.heldSelection)
        XCTAssertEqual(inspected.originalDetailsContent()?.recorded, base.originalDetailsContent()?.recorded)
        // The side history keeps its own selection, series and mini composition.
        let recorded = try XCTUnwrap(base.originalDetailsContent()?.recorded)
        XCTAssertEqual(recorded.selection, Self.heldSelection)
        XCTAssertEqual(recorded.seriesID, Self.seriesID)
        XCTAssertNil(recorded.history.inspection)
        XCTAssertEqual(recorded.history.layout, .expanded)
        XCTAssertFalse(recorded.history.showsKey)
        XCTAssertEqual(recorded.history.series.first?.runs.flatMap(\.points).count, 308)
        XCTAssertEqual(recorded.expand?.id, "original-history")
        // Each selection's control hands back only its own value.
        let log = Log()
        let page = Self.page(Self.input(.settled), log: log)
        page.historyContent(reader: false)?.onInspectionChoice?(Self.pointID(Self.first.t))
        page.catalogueContent()?.onSelect?(Self.heldSelection)
        XCTAssertEqual(log.events, ["hold", "inspect:\(Self.pointID(Self.first.t))",
                                    "hold", "select:\(Self.evidence.atlasRow._market_id)"])
    }

    // MARK: - Info, sources, words, accessibility and layout

    func testInfoStaysCompactAndRulesSourcesAndTheReleaseLinkAreExact() throws {
        for phase in Phase.allCases {
            let page = Self.page(Self.input(phase), log: Log())
            let about = try XCTUnwrap(page.aboutContent(), "\(phase)")
            XCTAssertEqual(about.title, "About these earnings")
            let expected = phase == .beforeReport
                ? ["What did this market predict?", "Recorded chances", "Original saved market"]
                : ["What did this market predict?", "Recorded chances", "Company report", "Original saved market"]
            XCTAssertEqual(about.sections.map(\.title), expected, "\(phase)")
            XCTAssertEqual(about.sourceIDs, ["rules"], "\(phase)")
            XCTAssertEqual(about.sourceLabel, "Exact source identities and rules")
            XCTAssertEqual(about.sections.last?.sourceID, "rules")
            XCTAssertEqual(about.sections.first { $0.title == "Company report" }?.link, phase == .beforeReport ? nil : Self.releaseLink)
            // Compact: no original quote, no opening and no rules dump — those live in Details and the source.
            let words = about.sections.flatMap { [$0.title] + $0.paragraphs }
            for figure in ["74.5%", "59.5%"] {
                XCTAssertFalse(Self.mentions(words, figure), "\(phase): \(figure)")
            }
            XCTAssertFalse(words.contains { $0.contains("SeekingAlpha") }, "\(phase): the rules stay in the source")
            XCTAssertTrue(words.contains { $0.contains("strictly greater than $1.60") }, "\(phase): positive control")
            XCTAssertEqual(words.contains { $0.contains("separately confirms Yes") }, phase == .settled, "\(phase)")
        }
        let page = Self.page(Self.input(.settled), log: Log())
        let source = try XCTUnwrap(page.sourceContent("rules"))
        XCTAssertEqual(source.title, "Exact source identities and rules")
        XCTAssertEqual(source.sections.map(\.title), ["Identities", "Rules"])
        XCTAssertEqual(source.sections[0].paragraphs, [
            "Polymarket event 1106010 · market 5144377",
            "Condition 0x61f0a0eb9fa05a2daa8097c212ec79a8b8ec07cb599cd6e8816e0562442d24f6",
            "Original market 63343098 · outcome 240153004 (Yes)",
        ])
        XCTAssertEqual(source.sections[1].paragraphs.joined(separator: "\n\n") + "\n", Self.capture.description)
        XCTAssertEqual(source.sourceIDs, [])
        // Unknown, blank or duplicated ids open nothing.
        XCTAssertNil(page.sourceContent("terms"))
        XCTAssertNil(page.sourceContent(""))
        let base = Self.bundle(.settled)
        let twice = Bundle(phase: .settled, headline: base.headline, comparison: base.comparison, history: base.history,
                           reader: base.reader, about: base.about, sources: base.sources + base.sources, stream: base.stream,
                           stories: base.stories, readerOrder: base.readerOrder, copy: base.copy, originals: base.originals)
        let doubled = Self.page(Self.input(.settled, bundle: twice), log: Log())
        XCTAssertNil(doubled.sourceContent("rules"))
        XCTAssertEqual(doubled.aboutContent()?.sourceIDs, [])
        // Details carries the same rules, verbatim.
        let details = try XCTUnwrap(page.originalDetailsContent())
        XCTAssertEqual(Details.content(catalogue: details.catalogue, selection: details.selection)?.rules, .verified(Self.rulesParagraphs))
        // The release link hands back its exact URL.
        let log = Log()
        try XCTUnwrap(Self.page(Self.input(.companyReport), .about, log: log).aboutContent()?.linkAction(Self.releaseLink))()
        XCTAssertEqual(log.events, ["hold", "link:company-release:\(Self.capture.company.url)"])
    }

    func testNoProbabilityMovementOrMovingProjectionWordsAndEveryWordIsTheOwners() throws {
        let probabilityWords = ["%", "chance", "Chance", "probability", "points", "moved", "movement"]
        let projectionWords = ["projected", "projection", "forecast", "moving", "estimate", "expected"]
        // Positive controls: the guards see a planted word.
        XCTAssertTrue(["+10 points of probability"].contains { line in probabilityWords.contains { line.contains($0) } })
        XCTAssertTrue(["projected EPS $1.60"].contains { line in projectionWords.contains { line.contains($0) } })
        for phase in [Phase.companyReport, .settled] {
            let card = Comparison(phase: phase, input: Self.comparison(phase))
            let delta = try XCTUnwrap(card.delta)
            for word in probabilityWords {
                XCTAssertFalse(delta.label.contains(word) || delta.figure.contains(word), "\(phase): \(word)")
            }
            let headline = Headline(phase: phase, input: Self.headline(phase))
            XCTAssertFalse(probabilityWords.contains { headline.words(.actual).joined(separator: " ").contains($0) }, "\(phase)")
        }
        let threshold = Self.threshold
        for word in projectionWords {
            XCTAssertFalse([threshold.label, threshold.figure, threshold.rule].contains { $0.contains(word) }, word)
        }

        // Every word a leaf shows is one of the owner's own strings: nothing formatted or invented here.
        for phase in Phase.allCases {
            let input = Self.headline(phase)
            let ownedWords: [String?] = [input.eyebrow, input.title, input.phaseWords, input.chanceLabel, input.chanceSubject,
                                          input.chance?.figure, input.chance?.date, input.threshold.label, input.threshold.figure,
                                          input.threshold.rule, input.actualLabel, input.actualUnit, input.actualRelation,
                                          input.actual?.figure, input.actual?.date, input.settlementWithheld, input.resultLabel,
                                          input.result?.words, input.result?.provenance, input.resultUnavailable, input.reminder,
                                          input.readingUnavailable]
            let owned = Set(ownedWords.compactMap { $0 })
            let headline = Headline(phase: phase, input: input)
            XCTAssertTrue(Set(headline.words).isSubset(of: owned), "\(phase): \(Set(headline.words).subtracting(owned))")
            let card = Self.comparison(phase)
            let cardWords: [String?] = [card.eyebrow, card.baselineLabel, card.baselineSubject, card.baseline?.figure,
                                              card.baseline?.date, card.title, card.threshold.label, card.threshold.figure,
                                              card.threshold.rule, card.actualLabel, card.actual?.figure, card.actual?.date,
                                              card.delta?.label, card.delta?.figure, card.unit, card.axis.words, card.axis.offAxis,
                                              card.axis.unavailable,
                                              card.caption, card.settlementWithheld, card.resultLabel, card.result?.words,
                                              card.result?.provenance,
                                              card.resultUnavailable, card.readingUnavailable]
            let cardOwned = Set(cardWords.compactMap { $0 } + card.axis.ticks.map(\.label))
            let model = Comparison(phase: phase, input: card)
            XCTAssertTrue(Set(model.words).isSubset(of: cardOwned), "\(phase): \(Set(model.words).subtracting(cardOwned))")
        }
        // Positive control for the subset guard: a foreign word is caught.
        XCTAssertFalse(Set(["$1.70", "Live"]).isSubset(of: ["$1.70"]))
    }

    func testFullNamesAndOwnDatesFitAtEveryWidthAndTypeSize() throws {
        let log = Log()
        let layouts: [(CGFloat, DynamicTypeSize, UserInterfaceSizeClass)] = [
            (375, .large, .compact), (393, .large, .compact), (1030, .large, .regular),
            (375, .xxxLarge, .compact), (375, .accessibility3, .compact),
        ]
        for phase in Phase.allCases {
            let bundlePhases: [Phase] = [phase, phase == .settled ? .beforeReport : .settled]
            for bundlePhase in bundlePhases {
                for mode in Self.allModes {
                    for (width, size, sizeClass) in layouts {
                        let view = Self.page(Self.input(phase, bundle: Self.bundle(bundlePhase)), mode, log: log)
                            .environment(\.horizontalSizeClass, sizeClass)
                        let host = hostForMeasurement(view, at: size)
                        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)
                        host.view.setNeedsLayout()
                        host.view.layoutIfNeeded()
                        let fitted = host.sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude))
                        let name = "\(phase)/\(bundlePhase) \(mode) \(width) \(size)"
                        XCTAssertLessThanOrEqual(fitted.width, width + 0.5, "\(name) scrolls sideways")
                        XCTAssertTrue(fitted.height.isFinite && fitted.height > 0, name)
                    }
                }
            }
        }
        XCTAssertTrue(log.events.isEmpty, "laying out calls nothing")

        // The two leaves alone: finite, never wider than offered, and taller — never smaller — with larger text.
        let headline = Headline(phase: .settled, input: Self.headline(.settled))
        let card = Comparison(phase: .settled, input: Self.comparison(.settled))
        let leaves: [(String, AnyView)] = [
            ("headline", AnyView(EarningsHeadlinePresentation10868(model: headline))),
            ("earnings card", AnyView(EarningsComparisonPresentation10868(model: card))),
        ]
        for (name, leaf) in leaves {
            var heights: [CGFloat] = []
            for size in [DynamicTypeSize.large, .xxxLarge, .accessibility3] {
                let host = hostForMeasurement(leaf.frame(width: 343), at: size)
                let fitted = host.sizeThatFits(in: CGSize(width: 343, height: .greatestFiniteMagnitude))
                XCTAssertTrue(fitted.height.isFinite && fitted.height > 0, "\(name) \(size)")
                XCTAssertLessThanOrEqual(fitted.width, 343.5, "\(name) \(size)")
                heights.append(fitted.height)
            }
            XCTAssertLessThanOrEqual(heights[0], heights[1], name)
            XCTAssertLessThan(heights[1], heights[2], name)
        }
        // Full names and own dates are the leaves' words at every size — never shortened by the model.
        XCTAssertTrue(headline.words.contains("Unity Bancorp"))
        XCTAssertTrue(headline.words.contains(Self.full(Double(Self.last.t))))
        XCTAssertTrue(headline.words.contains("Published \(Self.full(Self.publishedEpoch))"))
        XCTAssertTrue(card.words.contains("Diluted GAAP EPS · quarter ended Sep 30"))
    }

    func testAccessibilityWordsReadEachUnitWithItsOwnDate() throws {
        let chanceDate = Self.full(Double(Self.last.t))
        let actualDate = "Published \(Self.full(Self.publishedEpoch))"
        let page = Self.page(Self.input(.settled), log: Log())
        let headline = try XCTUnwrap(page.headlineContent()).model
        XCTAssertEqual(headline.spokenChance, "Pre-report chance: 88% to beat $1.60, \(chanceDate)")
        XCTAssertEqual(headline.spokenActual, "Reported per share: $1.70, Diluted GAAP EPS · USD, 10¢ above $1.60, \(actualDate)")
        XCTAssertEqual(headline.spokenResult,
                       "Contract result: Yes · contract resolved, Provider resolution · separate from the company report")
        // The chance is never spoken in dollars, the actual never as a percentage.
        XCTAssertFalse(headline.spokenChance.contains("$1.70"))
        XCTAssertFalse(try XCTUnwrap(headline.spokenActual).contains("%"))
        let card = try XCTUnwrap(page.comparisonContent()).model
        XCTAssertEqual(card.spokenBaseline, "Last recorded before report, Chance to beat $1.60: 88%, \(chanceDate)")
        XCTAssertEqual(card.spokenActual, "Reported actual: $1.70, \(actualDate)")
        XCTAssertEqual(card.barSpoken, "Reported actual $1.70 versus contract threshold $1.60. Dollar scale starts at zero.")
        // Steps speak their label and the owner's neighbour name.
        XCTAssertEqual(page.model.stepSpoken(.next, from: .history), "Next, Earnings against expectations")
        XCTAssertEqual(page.model.stepSpoken(.previous, from: .earnings), "Previous, Chance to beat $1.60")
        XCTAssertNil(page.model.stepSpoken(.previous, from: .history))
        // Stable, distinct identifiers.
        let ids = [EarningsEventPageAccessibilityID10868.page, EarningsEventPageAccessibilityID10868.hero,
                   EarningsEventPageAccessibilityID10868.headline, EarningsEventPageAccessibilityID10868.anchor,
                   EarningsEventPageAccessibilityID10868.stories, EarningsEventPageAccessibilityID10868.phaseUnavailable,
                   EarningsEventPageAccessibilityID10868.back, EarningsEventPageAccessibilityID10868.details,
                   EarningsEventPageAccessibilityID10868.allProps, EarningsEventPageAccessibilityID10868.bar,
                   EarningsEventPageAccessibilityID10868.readerHeader, EarningsEventPageAccessibilityID10868.catalogue,
                   EarningsEventPageAccessibilityID10868.original, EarningsEventPageAccessibilityID10868.about,
                   EarningsEventPageAccessibilityID10868.source, EarningsEventPageAccessibilityID10868.card(.history),
                   EarningsEventPageAccessibilityID10868.card(.earnings),
                   EarningsEventPageAccessibilityID10868.step(.previous), EarningsEventPageAccessibilityID10868.step(.next)]
        XCTAssertEqual(Set(ids).count, ids.count)
    }

    // MARK: - Design E1: a known actual never depends on the dollar axis

    func testAKnownReportedActualStaysKnownWhenTheDollarAxisCannotPlaceIt() throws {
        let actualDate = "Published \(Self.full(Self.publishedEpoch))"
        let eps = Self.capture.company.dilutedEPS
        // (a) A constructed narrow axis: the retained actual's and threshold's owner placements lie beyond it.
        let narrow = Self.narrowAxis
        XCTAssertTrue(Geometry.isValid(narrow), "the narrow axis itself draws")
        let beyond = Reading(id: "company-release", figure: Self.usd(eps), date: actualDate, placement: eps / narrow.upper)
        XCTAssertGreaterThan(beyond.placement, 1)
        // (b) An invalid plot placement on the retained axis.
        let unplaced = Reading(id: "company-release", figure: Self.usd(eps), date: actualDate, placement: .nan)
        let cases: [(String, EarningsAxis10868, Reading, Double)] = [
            ("narrow axis", narrow, beyond, Self.capture.threshold / narrow.upper),
            ("invalid placement", Self.usdAxis, unplaced, Self.thresholdPlacement),
        ]
        for phase in [Phase.companyReport, .settled] {
            for (name, axis, reading, thresholdAt) in cases {
                let label = "\(phase) \(name)"
                let headline = Headline(phase: phase, input: Self.headline(phase, actual: reading))
                XCTAssertEqual(headline.actual, .value(figure: "$1.70", date: actualDate), label)
                XCTAssertEqual(headline.words(.actual),
                               ["Reported per share", "$1.70", "Diluted GAAP EPS · USD", "10¢ above $1.60", actualDate], label)
                let card = Comparison(phase: phase, input: Self.comparison(phase, actual: reading, axis: axis, thresholdAt: thresholdAt))
                XCTAssertEqual(card.actual, .value(figure: "$1.70", date: actualDate), label)
                XCTAssertEqual(card.delta, EarningsDelta10868(label: "Above threshold", figure: "+10¢"), label)
                XCTAssertTrue(card.isDrawable, label)
                XCTAssertNil(card.actualPlacement, "\(label): the bar does not draw it")
                XCTAssertEqual(card.offAxis, Self.offAxisWords, label)
                XCTAssertEqual(card.words(.bar).last, Self.offAxisWords, label)
                XCTAssertTrue(card.barSpoken.hasSuffix(Self.offAxisWords), label)
                // Outside the scale is not "no report".
                XCTAssertFalse(Self.mentions(headline.words + card.words, "Unavailable"), label)
                XCTAssertEqual(card.words(.figures), ["Reported actual", "$1.70", actualDate, "Above threshold", "+10¢"], label)
            }
            // The narrow axis also has no place for the threshold; the retained axis keeps it.
            XCTAssertNil(Comparison(phase: phase, input: Self.comparison(phase, actual: beyond, axis: narrow,
                                                                         thresholdAt: Self.capture.threshold / narrow.upper)).thresholdPlacement)
            XCTAssertEqual(Comparison(phase: phase, input: Self.comparison(phase, actual: unplaced)).thresholdPlacement, 0.8)
            // An undrawable axis withholds the whole bar; the known actual stays in both after-report phases.
            let invalid = EarningsAxis10868(lower: 1, upper: 2, ticks: Self.usdAxis.ticks, words: Self.usdAxis.words,
                                            offAxis: Self.offAxisWords, unavailable: "Dollar scale unavailable")
            let withheld = Comparison(phase: phase, input: Self.comparison(phase, axis: invalid))
            XCTAssertEqual(withheld.actual, .value(figure: "$1.70", date: actualDate), "\(phase)")
            XCTAssertEqual(withheld.words(.bar), ["Dollar scale unavailable"], "\(phase)")
            XCTAssertNil(withheld.offAxis, "\(phase): the unavailable words, not the off-axis words")
        }
        // Before the report: still no actual and no result, whatever the axis or placement.
        for reading in [beyond, unplaced] {
            let headline = Headline(phase: .beforeReport, input: Self.headline(.beforeReport, actual: reading, result: Self.resolution))
            XCTAssertNil(headline.actual)
            XCTAssertNil(headline.result)
            let card = Comparison(phase: .beforeReport, input: Self.comparison(.beforeReport, actual: reading, result: Self.resolution,
                                                                               axis: narrow))
            XCTAssertNil(card.actual)
            XCTAssertNil(card.actualPlacement)
            XCTAssertNil(card.result)
            XCTAssertFalse(Self.mentions(headline.words + card.words, "$1.70"))
        }
        // A missing id, figure or date is still unknown, even on the retained axis.
        for broken in [Reading(id: "", figure: "$1.70", date: actualDate, placement: 0.85),
                       Reading(id: "company-release", figure: "$1.70", date: " ", placement: 0.85)] {
            XCTAssertEqual(Headline(phase: .settled, input: Self.headline(.settled, actual: broken)).actual, .unavailable("Unavailable"))
            XCTAssertEqual(Comparison(phase: .settled, input: Self.comparison(.settled, actual: broken)).actual, .unavailable("Unavailable"))
        }
        // Through the admitted page bundle: the known actual and the off-axis words both reach the reader.
        let page = Self.page(Self.input(.settled, bundle: Self.bundle(
            .settled, headline: Self.headline(.settled, actual: beyond),
            comparison: Self.comparison(.settled, actual: beyond, axis: narrow, thresholdAt: Self.capture.threshold / narrow.upper))),
            log: Log())
        let words = Self.reachable(page)
        XCTAssertTrue(Self.mentions(words, "$1.70"))
        XCTAssertTrue(words.contains(Self.offAxisWords))
        XCTAssertFalse(Self.mentions(words, "Unavailable"))
    }

    // MARK: - Design E2: a 44pt Info control at every text size; E4: the bar's one filled extent

    func testTheInfoControlKeepsA44PointTargetAtTheSmallestTextAndGrowsWithLargerText() throws {
        typealias Control = EarningsInfoControl10868
        // The helper the control's hit frame uses: floored at 44pt, growing above it, never from a broken metric.
        XCTAssertEqual(Control.targetSize(30), 44)
        XCTAssertEqual(Control.targetSize(44), 44)
        XCTAssertEqual(Control.targetSize(62), 62)
        XCTAssertEqual(Control.targetSize(-4), 44)
        XCTAssertEqual(Control.targetSize(.nan), 44)
        XCTAssertEqual(Control.targetSize(.infinity), 44)
        // The actual control, hosted at the smallest, the default and the largest text sizes.
        let log = Log()
        var fittedSizes: [CGSize] = []
        for size in [DynamicTypeSize.xSmall, .large, .accessibility5] {
            let control = Control(label: "About these earnings probabilities", hint: "Opens the sources and rules",
                                  action: { log.events.append("about") })
            let host = hostForMeasurement(control, at: size)
            let fitted = host.sizeThatFits(in: CGSize(width: CGFloat.greatestFiniteMagnitude, height: .greatestFiniteMagnitude))
            XCTAssertGreaterThanOrEqual(fitted.width, 44, "\(size)")
            XCTAssertGreaterThanOrEqual(fitted.height, 44, "\(size)")
            fittedSizes.append(fitted)
        }
        XCTAssertGreaterThan(fittedSizes[2].height, fittedSizes[0].height, "the target grows with larger text")
        XCTAssertTrue(log.events.isEmpty, "building and laying out calls nothing")
        // The headline mounts this control with the owner's exact action, held once on the page.
        let page = Self.page(Self.input(.settled), log: log)
        let headline = try XCTUnwrap(page.headlineContent())
        try XCTUnwrap(headline.aboutAction)()
        XCTAssertEqual(log.events, ["hold", "about"])
        // The headline leaf at the smallest text keeps room for the 44pt control.
        let leaf = hostForMeasurement(EarningsHeadlinePresentation10868(model: headline.model, onAbout: {}).frame(width: 320), at: .xSmall)
        XCTAssertGreaterThanOrEqual(leaf.sizeThatFits(in: CGSize(width: 320, height: .greatestFiniteMagnitude)).height, 44)
        // Without the owner's About there is no control at all.
        XCTAssertNil(EarningsHeadlinePresentation10868(model: headline.model).aboutAction)
    }

    func testTheBarFillsToTheThresholdBeforeTheReportAndToTheActualAfterIt() throws {
        // Before the report: a muted extent to the fixed threshold — never an actual, a money figure or a chance.
        let before = Comparison(phase: .beforeReport, input: Self.comparison(.beforeReport))
        XCTAssertEqual(before.barExtent, .threshold(0.8))
        XCTAssertNil(before.actual)
        XCTAssertNil(before.actualPlacement)
        XCTAssertNil(before.result)
        XCTAssertEqual(before.words(.figures), ["Contract threshold", "$1.60"])
        XCTAssertFalse(Self.mentions(before.words, "$1.70"))
        XCTAssertFalse(Self.mentions(before.words, "+10¢"))
        // After it: only the known actual's own extent — never the threshold's as a fallback.
        for phase in [Phase.companyReport, .settled] {
            XCTAssertEqual(Comparison(phase: phase, input: Self.comparison(phase)).barExtent, .actual(0.85), "\(phase)")
            let far = Comparison(phase: phase, input: Self.comparison(
                phase, actual: Reading(id: "company-release", figure: "$1.70", date: Self.reportedActual.date, placement: 1.4)))
            XCTAssertNil(far.barExtent, "\(phase): off the axis, no extent")
            XCTAssertEqual(far.thresholdPlacement, 0.8, "\(phase): the dashed threshold stays")
            XCTAssertEqual(far.actual, .value(figure: "$1.70", date: Self.reportedActual.date), "\(phase): the known words stay")
            XCTAssertEqual(far.offAxis, Self.offAxisWords, "\(phase)")
            XCTAssertNil(Comparison(phase: phase, input: Self.comparison(phase, actual: .some(nil))).barExtent, "\(phase)")
        }
        // A threshold off the axis withholds the before-report extent; its words and the off-axis words remain.
        let offThreshold = Comparison(phase: .beforeReport, input: Self.comparison(.beforeReport, thresholdAt: 1.2))
        XCTAssertNil(offThreshold.barExtent)
        XCTAssertEqual(offThreshold.words(.figures), ["Contract threshold", "$1.60"])
        XCTAssertEqual(offThreshold.offAxis, Self.offAxisWords)
        // An undrawable axis withholds every extent in every phase; the known words remain.
        let invalid = EarningsAxis10868(lower: 1, upper: 2, ticks: Self.usdAxis.ticks, words: Self.usdAxis.words,
                                        offAxis: Self.offAxisWords, unavailable: "Dollar scale unavailable")
        for phase in Phase.allCases {
            let card = Comparison(phase: phase, input: Self.comparison(phase, axis: invalid))
            XCTAssertNil(card.barExtent, "\(phase)")
            XCTAssertEqual(card.words(.bar), ["Dollar scale unavailable"], "\(phase)")
            XCTAssertFalse(card.words(.figures).isEmpty, "\(phase)")
        }
        // Each extent ends at its own position on the width the view lays out.
        XCTAssertEqual(try XCTUnwrap(Geometry.x(0.8, width: 300)), 240, accuracy: 0.0001)
        XCTAssertEqual(try XCTUnwrap(Geometry.x(0.85, width: 300)), 255, accuracy: 0.0001)
    }
}

// MARK: - Retained fixture (generated)

private let retainedCapture = #"""
{
"capture":{"eventID":"1106010","marketID":"5144377","conditionID":"0x61f0a0eb9fa05a2daa8097c212ec79a8b8ec07cb599cd6e8816e0562442d24f6","title":"Will Unity Bancorp (UNTY) beat quarterly earnings?","threshold":1.6,"unit":"Diluted GAAP EPS \u00b7 USD","company":{"url":"https://www.globenewswire.com/news-release/2026/10/13/3379462/0/en/unity-bancorp-reports-quarterly-earnings-of-17-4-million.html","source":"Unity Bancorp, Inc. via GlobeNewswire","publishedAt":"2026-10-13T10:00:00Z","quarterEnded":"2026-09-30","dilutedEPS":1.7,"priorQuarterEPS":1.42,"netIncomeMillions":17.4,"verifiedVia":"Public release read through web tool; lines 54 and 57. Facts transcribed, not a full-response archive.","capturedAt":"2026-10-15T04:06:24.871378+00:00"},"scheduledAt":"2026-10-12T20:00:00Z","closedAt":"2026-10-13T12:16:28Z","resolvedYes":true,"original":{"marketID":63343098,"outcomeID":240153004,"probability":0.745,"observedAt":"2026-10-10T22:22:04.083317+00:00","untimedOpening":0.595},"description":"As of market creation, Unity Bancorp is estimated to release earnings on October 12, 2026. The Street consensus estimate for Unity Bancorp's GAAP EPS for the relevant quarter is $1.60 as of market creation. This market will resolve to \"Yes\" if Unity Bancorp reports GAAP EPS greater than $1.60 for the relevant quarter in its next quarterly earnings release. Otherwise, it will resolve to \"No.\" The resolution source will be the GAAP EPS listed in the company\u2019s official earnings documents.\n\nIf Unity Bancorp releases earnings without GAAP EPS, then the market will resolve according to the GAAP EPS figure reported by SeekingAlpha. If no such figure is published within 96h of market close (4:00:00pm ET) on the day earnings are announced, the market will resolve to \u201cNo\u201d.\n\nIf the company does not release earnings within 45 calendar days of the estimated earnings date, this market will resolve to \u201cNo.\u201d\n\nNote: Subsequent restatements, corrections, or revisions made to the initially announced GAAP EPS figure will not qualify for resolution, except in the case of obvious and immediate mistakes (e.g., fat finger errors, as with Lyft's (LYFT) earnings release in February 2024).\nNote: The strike prices used in these markets reflect the selected street consensus estimate for GAAP EPS as of market creation.\nNote: All figures will be rounded to the nearest cent using standard rounding.\nNote: For the purposes of this market, IFRS EPS will be treated as GAAP EPS.\nNote: GAAP EPS refers to diluted GAAP EPS, unless this is not published, in which case it refers to basic GAAP EPS.\nNote: All figures are expressed in USD, unless otherwise indicated.\nNote: For primarily internationally listed companies, this market refers specifically to the shares traded in the United States on U.S. stock exchanges such as the NYSE or Nasdaq. In cases where the company trades in the U.S. through an American Depositary Receipt (ADR) or American Depositary Share (ADS), this market will refer to the ADR/ADS.\n"},
"history":[
[1790730014,0.53],[1790733629,0.53],[1790737219,0.53],[1790740829,0.53],[1790744418,0.53],[1790748032,0.53],[1790751617,0.53],[1790755218,0.53],
[1790758819,0.53],[1790762414,0.53],[1790766018,0.53],[1790769619,0.53],[1790773218,0.55],[1790776819,0.55],[1790780423,0.55],[1790784019,0.545],
[1790787617,0.545],[1790791218,0.545],[1790794818,0.545],[1790798418,0.545],[1790802020,0.545],[1790805613,0.545],[1790809218,0.545],[1790812821,0.545],
[1790816417,0.545],[1790820019,0.545],[1790823632,0.545],[1790827233,0.545],[1790830817,0.545],[1790834419,0.545],[1790838017,0.545],[1790841633,0.545],
[1790845259,0.545],[1790848818,0.545],[1790852418,0.545],[1790856020,0.545],[1790859617,0.545],[1790863220,0.545],[1790866824,0.545],[1790870425,0.545],
[1790874018,0.545],[1790877620,0.545],[1790881219,0.545],[1790884820,0.545],[1790888422,0.545],[1790892019,0.545],[1790895619,0.545],[1790899219,0.545],
[1790902814,0.6],[1790906417,0.6],[1790910019,0.6],[1790913613,0.595],[1790917222,0.595],[1790920818,0.595],[1790924413,0.595],[1790928020,0.595],
[1790931618,0.595],[1790935218,0.595],[1790938818,0.725],[1790942419,0.72],[1790946017,0.72],[1790949622,0.72],[1790953225,0.72],[1790956826,0.72],
[1790960435,0.72],[1790964039,0.72],[1790967618,0.72],[1790971219,0.72],[1790974833,0.72],[1790978419,0.72],[1790982023,0.72],[1790985622,0.72],
[1790989219,0.72],[1790992832,0.72],[1790996419,0.72],[1791000018,0.72],[1791003618,0.72],[1791007220,0.72],[1791010833,0.72],[1791014415,0.72],
[1791018020,0.72],[1791021616,0.72],[1791025221,0.72],[1791028820,0.72],[1791032419,0.72],[1791036032,0.72],[1791039637,0.72],[1791043231,0.72],
[1791046818,0.72],[1791050420,0.72],[1791054033,0.72],[1791057632,0.72],[1791061221,0.72],[1791064815,0.72],[1791068419,0.72],[1791072019,0.72],
[1791075617,0.72],[1791079219,0.72],[1791082819,0.72],[1791086413,0.72],[1791090017,0.72],[1791093618,0.72],[1791097217,0.64],[1791100818,0.64],
[1791104432,0.64],[1791108018,0.64],[1791111618,0.64],[1791115221,0.64],[1791118818,0.79],[1791122420,0.79],[1791126022,0.79],[1791129621,0.79],
[1791133233,0.79],[1791136820,0.79],[1791140418,0.79],[1791144021,0.79],[1791147622,0.79],[1791151219,0.79],[1791154820,0.79],[1791158423,0.79],
[1791162016,0.79],[1791165618,0.79],[1791169220,0.79],[1791172815,0.79],[1791176424,0.79],[1791180020,0.79],[1791183618,0.79],[1791187218,0.79],
[1791190821,0.79],[1791194431,0.79],[1791198034,0.79],[1791201622,0.79],[1791205224,0.79],[1791208819,0.79],[1791212437,0.79],[1791216019,0.79],
[1791219619,0.79],[1791223220,0.79],[1791226819,0.79],[1791230420,0.79],[1791234021,0.79],[1791237620,0.79],[1791241222,0.79],[1791244821,0.79],
[1791248436,0.79],[1791252022,0.72],[1791255620,0.79],[1791259220,0.79],[1791262821,0.79],[1791266422,0.79],[1791270019,0.79],[1791273617,0.79],
[1791277219,0.79],[1791277252,0.79],[1791280816,0.79],[1791284422,0.79],[1791288025,0.79],[1791291621,0.79],[1791295227,0.79],[1791298824,0.79],
[1791302421,0.79],[1791306023,0.825],[1791309622,0.825],[1791313221,0.8],[1791316822,0.8],[1791320422,0.8],[1791324033,0.795],[1791327621,0.795],
[1791331224,0.795],[1791334820,0.795],[1791338421,0.795],[1791342024,0.795],[1791345622,0.795],[1791349223,0.795],[1791352823,0.795],[1791356436,0.795],
[1791360022,0.795],[1791363623,0.795],[1791367216,0.795],[1791370827,0.795],[1791374437,0.795],[1791378024,0.795],[1791381624,0.795],[1791385231,0.795],
[1791388835,0.795],[1791392426,0.795],[1791396031,0.795],[1791399623,0.795],[1791403223,0.795],[1791406831,0.795],[1791410418,0.71],[1791414031,0.725],
[1791417637,0.59],[1791421223,0.655],[1791424823,0.75],[1791428437,0.75],[1791432017,0.75],[1791435622,0.75],[1791439232,0.69],[1791442827,0.71],
[1791446415,0.71],[1791450029,0.69],[1791453615,0.695],[1791457226,0.715],[1791460846,0.715],[1791464434,0.695],[1791468019,0.715],[1791471629,0.695],
[1791475243,0.715],[1791478822,0.695],[1791482433,0.715],[1791486024,0.695],[1791489622,0.715],[1791493236,0.715],[1791496823,0.695],[1791500427,0.695],
[1791504037,0.715],[1791507623,0.695],[1791511223,0.715],[1791514831,0.715],[1791518420,0.715],[1791522037,0.695],[1791525648,0.715],[1791529238,0.82],
[1791532825,0.82],[1791536434,0.715],[1791540016,0.735],[1791543627,0.75],[1791547238,0.75],[1791550824,0.75],[1791554426,0.75],[1791558036,0.75],
[1791561624,0.75],[1791565231,0.795],[1791568840,0.795],[1791572426,0.795],[1791576024,0.79],[1791579635,0.795],[1791583223,0.795],[1791586846,0.795],
[1791590426,0.795],[1791594024,0.795],[1791597623,0.795],[1791601229,0.795],[1791604819,0.795],[1791608424,0.795],[1791612024,0.795],[1791615621,0.795],
[1791619222,0.795],[1791622825,0.795],[1791626423,0.795],[1791630024,0.795],[1791633631,0.795],[1791637223,0.795],[1791640825,0.795],[1791644429,0.795],
[1791648027,0.795],[1791651624,0.795],[1791655230,0.795],[1791658825,0.795],[1791662440,0.795],[1791666027,0.785],[1791669624,0.745],[1791673237,0.745],
[1791676831,0.745],[1791680424,0.745],[1791684033,0.745],[1791687624,0.745],[1791691223,0.745],[1791694823,0.69],[1791698438,0.68],[1791702020,0.685],
[1791705621,0.705],[1791709222,0.67],[1791712823,0.67],[1791716437,0.71],[1791720032,0.74],[1791723622,0.735],[1791727222,0.715],[1791730824,0.715],
[1791734422,0.715],[1791738031,0.715],[1791741625,0.715],[1791745222,0.715],[1791748821,0.73],[1791752425,0.745],[1791756022,0.76],[1791759624,0.8],
[1791763242,0.8],[1791766820,0.8],[1791770421,0.8],[1791774024,0.8],[1791777620,0.8],[1791781222,0.8],[1791784824,0.825],[1791788420,0.825],
[1791792021,0.825],[1791795623,0.825],[1791799220,0.89],[1791802820,0.855],[1791806428,0.855],[1791810021,0.855],[1791813616,0.855],[1791817223,0.855],
[1791820821,0.885],[1791824423,0.885],[1791828029,0.885],[1791831635,0.88]
],
"atlasEvent":{"key":"economics","label":"Non-sport \u00b7 earnings","unit":"","detail":{"home_team":"Unity Bancorp earnings","status":"field","commence_time":null},"series":[],"pregame_projection":null,"source":"field-63343098.json","rowCount":1},
"atlasRow":{"id":240153004,"name":"Yes","probability":0.745,"american_odds":-292,"rank":1,"rank_change_24h":null,"probability_change_24h":-0.050000000000000044,"opening_probability":0.595,"opening_american_odds":-147,"is_winner":null,"resolution_source":null,"last_updated":"2026-10-10T22:22:04.083317+00:00","price_changed_at":"2026-10-10T22:22:04.083317+00:00","key":"field-63343098.json:0","source_file":"field-63343098.json","category":"named","market_name":"Will Unity Bancorp (UNTY) beat quarterly earnings?","outcome_name":"Yes","_market_id":63343098,"source":"polymarket","observed_at":"2026-10-10T22:22:04.083317+00:00"},
"header":{"id":"economics","title":"Unity Bancorp earnings","role":"binary","predicate":"Beat quarterly earnings","source":"polymarket","marketID":"63343098","rowKeys":["field-63343098.json:0"],"missingNote":"Last quotes are available in details.","historyNote":"Probability history was not captured.","contextNote":"Only captured questions are represented."}
}
"""#
