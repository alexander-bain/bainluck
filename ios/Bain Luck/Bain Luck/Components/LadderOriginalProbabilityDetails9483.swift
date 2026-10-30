import SwiftUI

/// #9483 — the Details content for one NBA ladder original (a total or a
/// winning-margin line): the selected line's own probability first, a 0–100%
/// reference rail, the final result kept apart from the probability, and the
/// original market's provenance behind "About this market".
///
/// Presentation only. The owner holds the card, ages it with
/// `NBALadderCard9483.current(at:)` and supplies the selected `optionKey`; this
/// file runs no timer, admits no value and keeps no selection. The headline and
/// the rail read `Point.chance` / `Point.now` / `Point.result` and nothing
/// else — `Detail` is provenance, never a stronger permission to print a number,
/// so a quote, a baseline or a raw result in it never fills a missing reading.
///
/// Phase decides which readings exist:
/// - before tip-off: one Pregame chance (`Point.chance`, solid, dated by
///   `Point.observedAt`) — the owner's published pregame reading;
/// - during play: Pregame chance (`Point.chance`, hollow, dated by
///   `Detail.baselineObservedAt`) and Current chance (`Point.now`, solid,
///   dated by `Point.observedAt`), equally prominent and never subtracted;
/// - after the final: the historical Pregame chance (hollow) and the
///   producer's `Point.result`. No current chance, whatever the inputs carry.
///
/// GAP, NOT PAID HERE: the card value carries no event id. The host must pass
/// the held card of the selected event and refresh or withdraw it together
/// with the event; this file cannot detect a card from another event.
enum LadderOriginalProbabilityDetails9483 {
    enum Marker: Equatable { case hollow, solid }

    struct Reading: Equatable {
        /// "Pregame chance" / "Current chance".
        let label: String
        /// The owner-qualified probability, or nil — never drawn at zero.
        let value: Double?
        /// The shared formatter's text, or the explicit missing words.
        let text: String
        /// The reading's own clock (or "Time unknown"); nil when there is no
        /// reading to date.
        let time: String?
        let marker: Marker

        var dateLine: String? {
            guard let time else { return nil }
            return time == LadderOriginalProbabilityDetails9483.timeUnknown ? time : "Recorded \(time)"
        }
    }

    enum Outcome: Equatable {
        case hit, miss, unavailable

        var text: String {
            switch self {
            case .hit: return "Result: Hit"
            case .miss: return "Result: Miss"
            case .unavailable: return "Result unavailable"
            }
        }

        var symbol: String {
            switch self {
            case .hit: return "checkmark.circle.fill"
            case .miss: return "xmark.circle.fill"
            case .unavailable: return "minus.circle"
            }
        }
    }

    struct Row: Equatable {
        let label: String
        let value: String
    }

    struct Content: Equatable {
        /// The selected original's own `Detail.marketName`, exactly as supplied;
        /// the card's generic family title only when that name is empty.
        let title: String
        let selected: String
        let readings: [Reading]
        /// After the final only.
        let result: Outcome?
        let about: [Row]

        /// What the rail draws: only readings that exist. Empty ⇒ no rail.
        var marks: [Reading] { readings.filter { $0.value != nil } }
    }

    static let unavailableTitle = "Selected market unavailable"
    static let unavailableNote = "No probability is shown for it in this update."
    static let noRecentUpdate = "No recent probability update"
    static let unavailable = "Unavailable"
    static let timeUnknown = "Time unknown"

    /// The selected point by exact identity. A nil, missing or ambiguous key is
    /// no point — never the first, the default or a neighbouring line.
    static func point(in card: NBALadderCard9483?, optionKey: String?) -> NBALadderCard9483.Point? {
        guard let card, let optionKey else { return nil }
        let matches = card.points.filter { $0.optionKey == optionKey }
        return matches.count == 1 ? matches[0] : nil
    }

    static func content(card: NBALadderCard9483?, optionKey: String?) -> Content? {
        guard let card, let point = point(in: card, optionKey: optionKey) else { return nil }
        let readings: [Reading]
        var result: Outcome?
        switch card.phase {
        case .before:
            readings = [reading("Pregame chance", point.chance, at: point.observedAt,
                                .solid, missing: noRecentUpdate)]
        case .during:
            readings = [
                reading("Pregame chance", point.chance, at: point.detail.baselineObservedAt,
                        .hollow, missing: unavailable),
                reading("Current chance", point.now, at: point.observedAt,
                        .solid, missing: noRecentUpdate),
            ]
        case .after:
            readings = [reading("Pregame chance", point.chance, at: point.detail.baselineObservedAt,
                                .hollow, missing: unavailable)]
            result = point.result.map { $0 ? .hit : .miss } ?? .unavailable
        }
        return Content(title: title(point.detail, card), selected: point.label, readings: readings,
                       result: result, about: about(card.phase, point.detail))
    }

    /// The visible and spoken title is the selected original's own market name,
    /// never the generic family title ("Scoring expectations" / "Winning
    /// margin") and never a name taken from another row. Only an empty name
    /// falls back to the family title, as a presentation default.
    static func title(_ detail: NBALadderCard9483.Detail, _ card: NBALadderCard9483) -> String {
        detail.marketName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? card.title : detail.marketName
    }

    private static func reading(_ label: String, _ value: Double?, at iso: String?,
                                _ marker: Marker, missing: String) -> Reading {
        guard let value else {
            return Reading(label: label, value: nil, text: missing, time: nil, marker: marker)
        }
        return Reading(label: label, value: value, text: formatProbability(value),
                       time: stamp(iso), marker: marker)
    }

    private static func stamp(_ iso: String?) -> String {
        SourceAge.preciseStamp(iso) ?? timeUnknown
    }

    /// The original's provenance. The admitted pregame baseline appears only
    /// once play has started; the last recorded value (`Detail.quoted`) is
    /// historical and secondary — it may appear here, explicitly dated, but
    /// never as "current", never in the summary and never on the rail. `Detail.result` is never
    /// printed: the result is `Point.result`, after the final.
    static func about(_ phase: NBALadderCard9483.Phase, _ detail: NBALadderCard9483.Detail) -> [Row] {
        var rows = [Row(label: "Market", value: detail.marketName),
                    Row(label: "Outcome", value: detail.label)]
        if let name = SourceLabels.label(for: detail.source) {
            rows.append(Row(label: "Source", value: name))
        }
        if phase != .before {
            rows.append(Row(label: "Pregame baseline", value: detail.baseline.map {
                dated(formatProbability($0), detail.baselineObservedAt)
            } ?? unavailable))
        }
        if let quoted = detail.quoted {
            rows.append(Row(label: "Last recorded probability",
                            value: dated(formatProbability(quoted), detail.observedAt)))
        }
        return rows
    }

    private static func dated(_ text: String, _ iso: String?) -> String {
        guard let when = SourceAge.preciseStamp(iso) else { return "\(text), time unknown" }
        return "\(text), recorded \(when)"
    }

    /// One coherent spoken summary: line, each reading's meaning, value and
    /// date, then the result.
    static func spoken(_ content: Content?) -> String {
        guard let content else { return "\(unavailableTitle). \(unavailableNote)" }
        var parts = [content.title, "Selected line: \(content.selected)"]
        for reading in content.readings {
            if let time = reading.time {
                parts.append("\(reading.label) \(reading.text), \(time == timeUnknown ? "time unknown" : "recorded \(time)")")
            } else {
                parts.append("\(reading.label): \(reading.text)")
            }
        }
        if let result = content.result { parts.append(result.text) }
        return parts.joined(separator: ". ") + "."
    }

    /// A raw probability's position on a rail of `width`, inset so a 0 or 1
    /// mark is drawn whole. The admitted value is used unchanged — not the
    /// rounded text.
    static func railX(_ value: Double, width: CGFloat, inset: CGFloat) -> CGFloat {
        inset + CGFloat(value) * (width - 2 * inset)
    }
}

/// Replaces the List content of the existing line Details sheet; the host keeps
/// its NavigationStack, Done, scrolling, hold and focus.
struct LadderOriginalProbabilityDetailsView9483: View {
    let card: NBALadderCard9483?
    let optionKey: String?
    let tint: Color

    private typealias Model = LadderOriginalProbabilityDetails9483

    var body: some View {
        if let content = Model.content(card: card, optionKey: optionKey) {
            VStack(alignment: .leading, spacing: 16) {
                summary(content)
                ProbabilityDetailsAbout9483(rows: content.about)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            ProbabilityDetailsUnavailable9483()
        }
    }

    private func summary(_ content: Model.Content) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(content.title)
                .font(.title3.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            Text("\(Text("Selected line · ").font(.subheadline).foregroundStyle(.secondary))\(Text(content.selected).font(.headline))")
                .fixedSize(horizontal: false, vertical: true)
            ProbabilityDetailsFigures9483(figures: content.readings.map {
                ProbabilityDetailsFigure9483(label: $0.label, marker: $0.marker, text: $0.text,
                                             isValue: $0.value != nil, dateLine: $0.dateLine)
            }, tint: tint)
            if !content.marks.isEmpty {
                ProbabilityDetailsRail9483(marks: content.marks.compactMap { mark in
                    mark.value.map { ProbabilityDetailsRailMark9483(id: mark.label, marker: mark.marker, value: $0) }
                }, tint: tint)
            }
            if let result = content.result {
                Label(result.text, systemImage: result.symbol)
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Model.spoken(content))
    }
}

// MARK: - Original market Details (#10868)

/// #9483 / #10868 — the Details content for one selected ORIGINAL market (a
/// cricket Test original such as "South Africa wins"): that original's own
/// pregame chance first, beside either a separately admitted later reading or
/// the original contract's own result, on the same 0–100% reference rail, with
/// title, outcome, rules and provenance behind "About this market".
///
/// Presentation only, and no NBA card in between: the host resolves every
/// word and number. It holds the exact selected original (or nothing), picks
/// the display `Mode`, writes each reading's figure text and provenance with
/// the owners' formatter and clock, and admits the result words. This file
/// formats no number or date, elects no reading, complements nothing and runs
/// no timer. The `Mode` is the MARKET's display state as the owner admitted
/// it — never inferred here from the game: a settled original may show its
/// result while the match is live, and an open one does not settle because the
/// match finished.
///
/// GAP, NOT PAID HERE: the host keeps event/scope admission, latest-payload
/// reconciliation, Done/Back/focus and Details routing. `Catalogue.scope` is
/// only compared, never derived.
enum OriginalMarketDetails9483 {
    typealias Marker = LadderOriginalProbabilityDetails9483.Marker
    typealias Row = LadderOriginalProbabilityDetails9483.Row

    /// The original's exact identity as the host holds it — never built here
    /// from a ticker, a label or an array position.
    struct Identity: Hashable {
        let source: String
        let market: String
        let side: String
    }

    /// The host's held selection: an exact identity inside the exact scope it
    /// was chosen in.
    struct Selection: Equatable {
        let scope: String
        let identity: Identity
    }

    /// The host's latest admitted originals for one scope.
    struct Catalogue: Equatable {
        let scope: String
        let originals: [Original]
    }

    /// What the later reading is, as the owner admitted it.
    enum Later: Equatable {
        case current, recorded

        var label: String {
            switch self {
            case .current: return "Current chance"
            case .recorded: return "Recorded chance"
            }
        }
    }

    /// The original market's display state, chosen by the owner.
    enum Mode: Equatable {
        /// One admitted pregame reading.
        case pregame
        /// The pregame reading beside a separately admitted later reading.
        case comparison(Later)
        /// The pregame reading beside the original contract's own result.
        case result
    }

    struct Reading: Equatable {
        enum Figure: Equatable {
            /// The owner's formatted figure, printed verbatim ("0%" included).
            case value(String)
            /// The owner's reason this slot has no figure.
            case missing(String)
        }

        let figure: Figure
        /// Where the owner places the reading on the 0–100% rail (0...1).
        /// Geometry only: an absent, non-finite or out-of-range placement
        /// draws no mark and is never clamped; the figure text still shows.
        let placement: Double?
        /// The reading's own provenance in full — calendar, granularity,
        /// source — as the owner wrote it.
        let provenance: String?

        static func value(_ text: String, placement: Double?, provenance: String?) -> Reading {
            Reading(figure: .value(text), placement: placement, provenance: provenance)
        }

        static func missing(_ reason: String) -> Reading {
            Reading(figure: .missing(reason), placement: nil, provenance: nil)
        }
    }

    /// The original contract's own grade, independently admitted by its owner
    /// ("Resolved No", "Void", "Not yet confirmed") — never the match result.
    struct Grade: Equatable {
        let words: String
        /// The grade's own settlement provenance; nil stays unknown.
        let provenance: String?
    }

    /// The last recorded value, explicitly historical and separately dated.
    struct HistoricalQuote: Equatable {
        let text: String
        let recorded: String?
    }

    enum Rules: Equatable {
        /// Proved rule text, paragraph by paragraph.
        case verified([String])
        /// The owner's words for "no proved rules".
        case unavailable(String)
        /// No rules section.
        case omitted
    }

    struct About: Equatable {
        let source: String?
        let rules: Rules
        /// Phase-admitted provenance rows, exactly as supplied.
        let provenance: [Row]
        let historicalQuote: HistoricalQuote?
    }

    struct Original: Equatable {
        let identity: Identity
        let title: String
        let outcome: String
        let mode: Mode
        let pregame: Reading
        /// Read in `.comparison` only.
        let later: Reading?
        /// Read in `.result` only.
        let grade: Grade?
        let about: About
    }

    struct ShownReading: Equatable {
        let label: String
        let marker: Marker
        /// The owner's figure text, or this slot's own missing reason.
        let text: String
        let isValue: Bool
        /// Nil only for a missing reading.
        let provenance: String?
        /// A valid rail position, or nil — no mark.
        let placement: Double?
    }

    struct ShownResult: Equatable {
        let words: String
        /// Nil only when no grade was supplied at all.
        let provenance: String?
    }

    struct Content: Equatable {
        let title: String
        let outcome: String
        let readings: [ShownReading]
        /// `.result` mode only.
        let result: ShownResult?
        let about: [Row]
        let rules: Rules

        /// What the rail draws: only readings with a valid placement.
        var marks: [ShownReading] { readings.filter { $0.placement != nil } }
    }

    static let pregameLabel = "Pregame chance"
    static let resultLabel = "Original market result"
    static let resultUnavailable = "Result unavailable"
    static let resultTimeUnknown = "Settlement time unknown"
    static let historicalLabel = "Last recorded probability (historical)"
    static let rulesLabel = "Rules"
    static let unavailable = LadderOriginalProbabilityDetails9483.unavailable
    static let timeUnknown = LadderOriginalProbabilityDetails9483.timeUnknown

    /// The selected original by exact identity inside the selection's own
    /// scope. A nil, blank, out-of-scope, withdrawn or duplicated identity is
    /// no original — never the first, a default or a neighbour.
    static func original(in catalogue: Catalogue?, selection: Selection?) -> Original? {
        guard let catalogue, let selection, !blank(selection.scope), selection.scope == catalogue.scope,
              !blank(selection.identity.source), !blank(selection.identity.market),
              !blank(selection.identity.side) else { return nil }
        let matches = catalogue.originals.filter { $0.identity == selection.identity }
        return matches.count == 1 ? matches[0] : nil
    }

    static func content(catalogue: Catalogue?, selection: Selection?) -> Content? {
        guard let original = original(in: catalogue, selection: selection),
              !blank(original.title), !blank(original.outcome) else { return nil }
        let readings: [ShownReading]
        var result: ShownResult?
        switch original.mode {
        case .pregame:
            readings = [shown(pregameLabel, original.pregame, .solid)]
        case .comparison(let later):
            readings = [shown(pregameLabel, original.pregame, .hollow),
                        shown(later.label, original.later, .solid)]
        case .result:
            readings = [shown(pregameLabel, original.pregame, .hollow)]
            if let grade = original.grade, let words = nonBlank(grade.words) {
                result = ShownResult(words: words, provenance: nonBlank(grade.provenance) ?? resultTimeUnknown)
            } else {
                result = ShownResult(words: resultUnavailable, provenance: nil)
            }
        }
        return Content(title: original.title, outcome: original.outcome, readings: readings,
                       result: result, about: about(original), rules: rules(original.about.rules))
    }

    /// A slot keeps its own figure or its own reason; it never borrows the
    /// other reading, a quote or zero.
    private static func shown(_ label: String, _ reading: Reading?, _ marker: Marker) -> ShownReading {
        if let reading, case .value(let text) = reading.figure, !blank(text) {
            return ShownReading(label: label, marker: marker, text: text, isValue: true,
                                provenance: nonBlank(reading.provenance) ?? timeUnknown,
                                placement: railPlacement(reading.placement))
        }
        var reason = unavailable
        if case .missing(let supplied)? = reading?.figure, let words = nonBlank(supplied) { reason = words }
        return ShownReading(label: label, marker: marker, text: reason, isValue: false,
                            provenance: nil, placement: nil)
    }

    /// Geometry validation only, apart from the reading's truth.
    static func railPlacement(_ value: Double?) -> Double? {
        guard let value, value.isFinite, (0...1).contains(value) else { return nil }
        return value
    }

    /// Title, outcome, source, the owner's provenance rows, then the
    /// historical quote — dated, labelled historical, never a current chance.
    static func about(_ original: Original) -> [Row] {
        var rows = [Row(label: "Market", value: original.title),
                    Row(label: "Outcome", value: original.outcome)]
        if let source = nonBlank(original.about.source) {
            rows.append(Row(label: "Source", value: source))
        }
        rows += original.about.provenance.filter { !blank($0.label) && !blank($0.value) }
        if let quote = original.about.historicalQuote, !blank(quote.text) {
            let value = nonBlank(quote.recorded).map { "\(quote.text), recorded \($0)" }
                ?? "\(quote.text), time unknown"
            rows.append(Row(label: historicalLabel, value: value))
        }
        return rows
    }

    /// Blank paragraphs drop; nothing proved left ⇒ no rules section.
    static func rules(_ rules: Rules) -> Rules {
        switch rules {
        case .verified(let paragraphs):
            let kept = paragraphs.filter { !blank($0) }
            return kept.isEmpty ? .omitted : .verified(kept)
        case .unavailable(let words):
            return blank(words) ? .omitted : .unavailable(words)
        case .omitted:
            return .omitted
        }
    }

    static func spoken(_ content: Content?) -> String {
        guard let content else { return LadderOriginalProbabilityDetails9483.spoken(nil) }
        var parts = [content.title, "Selected outcome: \(content.outcome)"]
        for reading in content.readings {
            if let provenance = reading.provenance {
                parts.append("\(reading.label) \(reading.text), \(provenance)")
            } else {
                parts.append("\(reading.label): \(reading.text)")
            }
        }
        if let result = content.result {
            parts.append("\(resultLabel): \(result.words)" + (result.provenance.map { ", \($0)" } ?? ""))
        }
        return parts.joined(separator: ". ") + "."
    }

    private static func blank(_ text: String) -> Bool {
        text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private static func nonBlank(_ text: String?) -> String? {
        guard let text, !blank(text) else { return nil }
        return text
    }
}

/// The selected original's Details inside the host's existing container; the
/// host keeps its NavigationStack, Done, scrolling, held updates and focus.
struct OriginalMarketDetailsView9483: View {
    let catalogue: OriginalMarketDetails9483.Catalogue?
    let selection: OriginalMarketDetails9483.Selection?
    let tint: Color

    private typealias Model = OriginalMarketDetails9483

    var body: some View {
        if let content = Model.content(catalogue: catalogue, selection: selection) {
            VStack(alignment: .leading, spacing: 16) {
                summary(content)
                ProbabilityDetailsAbout9483(rows: content.about, rules: content.rules)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            ProbabilityDetailsUnavailable9483()
        }
    }

    private func summary(_ content: Model.Content) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(content.title)
                .font(.title3.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            Text("\(Text("Selected outcome · ").font(.subheadline).foregroundStyle(.secondary))\(Text(content.outcome).font(.headline))")
                .fixedSize(horizontal: false, vertical: true)
            ProbabilityDetailsFigures9483(figures: content.readings.map {
                ProbabilityDetailsFigure9483(label: $0.label, marker: $0.marker, text: $0.text,
                                             isValue: $0.isValue, dateLine: $0.provenance)
            }, tint: tint)
            if !content.marks.isEmpty {
                ProbabilityDetailsRail9483(marks: content.marks.compactMap { mark in
                    mark.placement.map { ProbabilityDetailsRailMark9483(id: mark.label, marker: mark.marker, value: $0) }
                }, tint: tint)
            }
            if let result = content.result {
                VStack(alignment: .leading, spacing: 4) {
                    Text(Model.resultLabel).font(.subheadline).foregroundStyle(.secondary)
                    Text(result.words).font(.headline)
                    if let provenance = result.provenance {
                        Text(provenance).font(.footnote).foregroundStyle(.secondary)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Model.spoken(content))
    }
}

// MARK: - Shared Details pieces

/// Internal only so tests can read the layout decision; the views below are
/// private to this file.
enum ProbabilityDetailsLayout9483 {
    /// Fewer than two readings, or any accessibility size, always stack; two
    /// readings otherwise sit side by side only when both fit whole.
    static func alwaysStacks(readings: Int, accessibilitySize: Bool) -> Bool {
        readings < 2 || accessibilitySize
    }
}

private struct ProbabilityDetailsFigure9483 {
    let label: String
    let marker: LadderOriginalProbabilityDetails9483.Marker
    let text: String
    let isValue: Bool
    let dateLine: String?
}

/// Two readings sit side by side only when both fit whole; otherwise they
/// stack before anything squeezes, and accessibility sizes always stack.
private struct ProbabilityDetailsFigures9483: View {
    let figures: [ProbabilityDetailsFigure9483]
    let tint: Color
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 28

    var body: some View {
        if ProbabilityDetailsLayout9483.alwaysStacks(readings: figures.count,
                                                     accessibilitySize: typeSize.isAccessibilitySize) {
            VStack(alignment: .leading, spacing: 16) {
                ForEach(figures, id: \.label) { figure($0) }
            }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 24) {
                    ForEach(figures, id: \.label) { figure($0).fixedSize() }
                }
                VStack(alignment: .leading, spacing: 16) {
                    ForEach(figures, id: \.label) { figure($0) }
                }
            }
        }
    }

    private func figure(_ figure: ProbabilityDetailsFigure9483) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Label {
                Text(figure.label).foregroundStyle(.secondary)
            } icon: {
                Image(systemName: figure.marker == .solid ? "circle.fill" : "circle")
                    .foregroundStyle(tint)
            }
            .font(.subheadline)
            if figure.isValue {
                Text(figure.text)
                    .font(.system(size: figureSize, weight: .bold).monospacedDigit())
                    .foregroundStyle(tint)
            } else {
                Text(figure.text)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.primary)
            }
            if let line = figure.dateLine {
                Text(line).font(.footnote).foregroundStyle(.secondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

private struct ProbabilityDetailsRailMark9483 {
    let id: String
    let marker: LadderOriginalProbabilityDetails9483.Marker
    let value: Double
}

/// A 0–100% reference, not a history: each existing reading is one mark at
/// its raw value — hollow ring for the earlier reading, solid dot for the
/// current or published one, concentric when they coincide. Nothing joins
/// the marks.
private struct ProbabilityDetailsRail9483: View {
    let marks: [ProbabilityDetailsRailMark9483]
    let tint: Color

    private static let ringSize: CGFloat = 16
    private static let dotSize: CGFloat = 9

    var body: some View {
        VStack(spacing: 4) {
            GeometryReader { geo in
                let inset = Self.ringSize / 2
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.secondary.opacity(0.25))
                        .frame(width: max(geo.size.width - 2 * inset, 0), height: 4)
                        .position(x: geo.size.width / 2, y: geo.size.height / 2)
                    ForEach(marks, id: \.id) { mark in
                        Group {
                            if mark.marker == .hollow {
                                Circle()
                                    .strokeBorder(tint, lineWidth: 2.5)
                                    .background(Circle().fill(Color.systemBackground))
                                    .frame(width: Self.ringSize, height: Self.ringSize)
                            } else {
                                Circle()
                                    .fill(tint)
                                    .frame(width: Self.dotSize, height: Self.dotSize)
                            }
                        }
                        .position(x: LadderOriginalProbabilityDetails9483.railX(mark.value, width: geo.size.width,
                                                                                 inset: inset),
                                  y: geo.size.height / 2)
                        .zIndex(mark.marker == .solid ? 1 : 0)
                    }
                }
            }
            .frame(height: Self.ringSize + 4)
            ZStack {
                Text("0%").frame(maxWidth: .infinity, alignment: .leading)
                Text("50%")
                Text("100%").frame(maxWidth: .infinity, alignment: .trailing)
            }
            .font(.caption2.monospacedDigit())
            .foregroundStyle(.secondary)
        }
        .accessibilityHidden(true)
    }
}

/// "About this market": provenance rows, then — originals only — the proved
/// rules or the owner's unavailable words. Rules wrap and scroll inside the
/// host's container.
private struct ProbabilityDetailsAbout9483: View {
    let rows: [LadderOriginalProbabilityDetails9483.Row]
    var rules: OriginalMarketDetails9483.Rules = .omitted

    var body: some View {
        DisclosureGroup("About this market") {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(row.label).font(.footnote).foregroundStyle(.secondary)
                        Text(row.value).font(.subheadline)
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityElement(children: .combine)
                }
                rulesSection
            }
            .padding(.top, 8)
        }
        .font(.subheadline)
    }

    @ViewBuilder private var rulesSection: some View {
        switch rules {
        case .verified(let paragraphs):
            VStack(alignment: .leading, spacing: 6) {
                Text(OriginalMarketDetails9483.rulesLabel).font(.footnote).foregroundStyle(.secondary)
                ForEach(Array(paragraphs.enumerated()), id: \.offset) { _, paragraph in
                    Text(paragraph).font(.subheadline)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
        case .unavailable(let words):
            VStack(alignment: .leading, spacing: 2) {
                Text(OriginalMarketDetails9483.rulesLabel).font(.footnote).foregroundStyle(.secondary)
                Text(words).font(.subheadline).foregroundStyle(.secondary)
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
        case .omitted:
            EmptyView()
        }
    }
}

private struct ProbabilityDetailsUnavailable9483: View {
    private typealias Model = LadderOriginalProbabilityDetails9483

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(Model.unavailableTitle).font(.headline)
            Text(Model.unavailableNote)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Model.spoken(nil))
    }
}

// MARK: - Original market chooser (#10868)

/// #10868 — the small original-outcome chooser above the selected original's
/// Details: every original the owner supplied (India / West Indies, or South
/// Africa / Australia / Draw/tie), in the owner's order, as one compact group
/// of named choices, with the existing Details for the HELD selection below.
///
/// Controlled and stateless. The host keeps the catalogue, the held selection,
/// refresh and withdrawal, navigation, Done/Back and focus; this file keeps no
/// selection, elects no first or default original, sorts and caps nothing and
/// moves no focus. A choice acts only through the existing
/// `OriginalMarketDetails9483.content(catalogue:selection:)` contract — the
/// one the Details below read — so an original whose scope, identity, title or
/// outcome would not open its own Details is never a button: it stays
/// visible, labelled and unavailable, and its neighbours keep theirs. A tap
/// hands the host the catalogue's scope and the original's identity,
/// unchanged; rendering and passive updates call nothing.
///
/// GAP, NOT PAID HERE: like the Details, the catalogue carries no event id;
/// the host keeps event and scope together.
enum OriginalMarketChooser9483 {
    typealias Details = OriginalMarketDetails9483

    struct Choice: Equatable {
        /// The owner's label for this exact identity, else the original's own
        /// title verbatim, else the owner's unavailable-choice words.
        let label: String
        /// The exact selection a tap hands back — the catalogue's scope and
        /// this original's identity, unchanged — or nil when this original
        /// does not open its own Details.
        let selection: Details.Selection?
        /// The held selection opens this exact original.
        let isSelected: Bool
        /// Shown under a readable label that cannot open; nil otherwise.
        let status: String?

        var isAvailable: Bool { selection != nil }
    }

    enum Arrangement: Equatable {
        /// No originals: the owner's empty words only.
        case empty
        /// Choices sit side by side and wrap at the actual width; a label
        /// wider than the row wraps inside its own choice.
        case wrapping
        /// One full-width choice per line.
        case stacked
    }

    static let unavailableStatus = Details.unavailable

    /// Every supplied original, in the owner's order — none dropped, sorted,
    /// capped or merged, a malformed one included as unavailable.
    static func choices(catalogue: Details.Catalogue?, selection: Details.Selection?,
                        labels: [Details.Identity: String], unavailableChoice: String) -> [Choice] {
        guard let catalogue else { return [] }
        return catalogue.originals.map { original in
            let candidate = Details.Selection(scope: catalogue.scope, identity: original.identity)
            let opens = Details.content(catalogue: catalogue, selection: candidate) != nil
            let own = ownLabel(original, labels: labels)
            return Choice(label: own ?? nonBlank(unavailableChoice) ?? unavailableStatus,
                          selection: opens ? candidate : nil,
                          isSelected: opens && candidate == selection,
                          status: opens || own == nil ? nil : unavailableStatus)
        }
    }

    /// The owner's label for the exact identity, else the title verbatim —
    /// never parsed, shortened or taken from another original.
    static func ownLabel(_ original: Details.Original, labels: [Details.Identity: String]) -> String? {
        nonBlank(labels[original.identity]) ?? nonBlank(original.title)
    }

    /// The only way a choice acts: the host's callback with the choice's own
    /// exact selection. Nil — static content, never an inert button — when
    /// there is no callback or the original does not open. The view's buttons
    /// run exactly this closure.
    static func action(_ choice: Choice,
                       onSelect: ((Details.Selection) -> Void)?) -> (() -> Void)? {
        guard let onSelect, let selection = choice.selection else { return nil }
        return { onSelect(selection) }
    }

    /// Accessibility sizes always stack; otherwise the choices wrap at the
    /// actual width, whatever the device.
    static func arrangement(choices: Int, accessibilitySize: Bool) -> Arrangement {
        guard choices > 0 else { return .empty }
        return accessibilitySize ? .stacked : .wrapping
    }

    /// The label, then why it cannot open. "Selected" is the trait, not text.
    static func spoken(_ choice: Choice) -> String {
        choice.status.map { "\(choice.label), \($0)" } ?? choice.label
    }

    private static func nonBlank(_ text: String?) -> String? {
        guard let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return text
    }
}

/// The chooser and the held original's existing Details, inside the host's
/// container; the host keeps scrolling, held updates, navigation and focus.
struct OriginalMarketChooserView9483: View {
    let catalogue: OriginalMarketDetails9483.Catalogue?
    let selection: OriginalMarketDetails9483.Selection?
    let heading: String
    let emptyWords: String
    let unavailableChoice: String
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    let tint: Color
    var onSelect: ((OriginalMarketDetails9483.Selection) -> Void)?

    private typealias Model = OriginalMarketChooser9483
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        let choices = Model.choices(catalogue: catalogue, selection: selection, labels: labels,
                                    unavailableChoice: unavailableChoice)
        VStack(alignment: .leading, spacing: 16) {
            chooser(choices)
            OriginalMarketDetailsView9483(catalogue: catalogue, selection: selection, tint: tint)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func chooser(_ choices: [Model.Choice]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if !heading.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Text(heading)
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
            }
            switch Model.arrangement(choices: choices.count, accessibilitySize: typeSize.isAccessibilitySize) {
            case .empty:
                Text(emptyWords)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            case .wrapping:
                FlowLayout(spacing: 8) {
                    ForEach(Array(choices.enumerated()), id: \.offset) { _, choice in
                        control(choice, fullWidth: false)
                    }
                }
            case .stacked:
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(choices.enumerated()), id: \.offset) { _, choice in
                        control(choice, fullWidth: true)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func control(_ choice: Model.Choice, fullWidth: Bool) -> some View {
        if let action = Model.action(choice, onSelect: onSelect) {
            Button(action: action) {
                face(choice, fullWidth: fullWidth)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(Model.spoken(choice))
            .accessibilityAddTraits(choice.isSelected ? .isSelected : [])
        } else {
            face(choice, fullWidth: fullWidth)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(Model.spoken(choice))
                .accessibilityAddTraits(choice.isSelected ? .isSelected : [])
        }
    }

    /// Selected: a checkmark and a heavier outline, not colour alone.
    /// Unavailable: a minus mark, a dashed outline and its status line.
    private func face(_ choice: Model.Choice, fullWidth: Bool) -> some View {
        let shape = RoundedRectangle(cornerRadius: 10)
        return HStack(alignment: .firstTextBaseline, spacing: 6) {
            if choice.isSelected {
                Image(systemName: "checkmark.circle.fill").foregroundStyle(tint)
            } else if !choice.isAvailable {
                Image(systemName: "minus.circle").foregroundStyle(.secondary)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(choice.label)
                    .font(.subheadline.weight(choice.isSelected ? .semibold : .regular))
                    .foregroundStyle(choice.isAvailable ? Color.primary : Color.secondary)
                if let status = choice.status {
                    Text(status).font(.caption).foregroundStyle(.secondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(minWidth: 44, maxWidth: fullWidth ? .infinity : nil, minHeight: 44, alignment: .leading)
        .background(shape.fill(choice.isSelected ? tint.opacity(0.10) : Color.clear))
        .overlay(shape.strokeBorder(choice.isSelected ? tint : Color.secondary.opacity(0.35),
                                    style: StrokeStyle(lineWidth: choice.isSelected ? 2 : 1,
                                                       dash: choice.isAvailable ? [] : [4, 3])))
        .contentShape(shape)
    }
}

// MARK: - Set and game handicaps (tennis, final only) (#10868)

/// #10868 — the tennis-final "Set and game handicaps" card: panels under the
/// owner's unit headings (two set panels under "Win at least one set", then a
/// game panel under "Finish level or ahead on games"). Each panel shows ONE
/// original's own pre-match chance on its own hollow 0–100% rail, the owner's
/// separately admitted actual (a set count with blocks, or a named game pair)
/// and that original's own result, and opens that exact original.
///
/// Presentation only, from the approved `TennisHandicapStory.tsx` +
/// `tennisHandicapStory.css`. It composes the original-market Details above
/// rather than a second model: a panel's chance and result are exactly what
/// `OriginalMarketDetails9483.content(catalogue:selection:)` resolves for its
/// original in `.result` mode, and a panel acts only through
/// `OriginalMarketChooser9483.action`. The outcomes overlap and stay separate:
/// nothing is normalised, complemented, multiplied or combined.
///
/// The owner supplies the phase, the catalogue, each panel's exact original,
/// the subject and predicate words (proved for this match's format — never
/// parsed from a title or a handicap), the actual with its own provenance and
/// spoken words, the block states, the explanation and any result decoration.
/// This file parses no title, does no score arithmetic, elects no baseline,
/// reads no later quote, formats no number or date and infers no grade: a
/// result decoration shows only beside the original's own supplied grade.
///
/// By default before and during play the card shows nothing. An explicit
/// during-play option preserves the owner phase and market mode. Selection, Details, Back,
/// focus, held refresh and withdrawal, and the explanation's disclosure stay
/// with the host; with no callback the panels are static and no tap is asked
/// for. The Details and chooser above are unchanged.
enum OriginalHandicapCard9483 {
    typealias Details = OriginalMarketDetails9483
    typealias Chooser = OriginalMarketChooser9483

    /// The game's phase as the owner holds it — not the market's mode.
    enum Phase: Equatable { case before, during, final }

    /// The owner's set count for a set panel.
    struct Count: Equatable {
        /// "2" — the owner's figure, verbatim.
        let figure: String
        /// "sets won · final"
        let unit: String
        /// Display geometry only, one block per set slot, filled for a set
        /// won. Blocks count wins; they do not show playing order.
        let blocks: [Bool]
        /// The actual's own provenance; nil stays unknown.
        let provenance: String?
        /// "Fokina won 2 sets, final"
        let spoken: String
    }

    struct PairSide: Equatable {
        /// "18"
        let figure: String
        /// The player's name, verbatim.
        let name: String
    }

    /// The owner's named score pair for a game panel.
    struct Pair: Equatable {
        /// "Final games"
        let caption: String
        let first: PairSide
        /// The owner's relation word between the figures ("level").
        let relation: String
        let second: PairSide
        let provenance: String?
        /// "Final games: Fokina 18, Tiafoe 18, level"
        let spoken: String
    }

    /// A compact owner-formatted progress statistic, not a set count or a
    /// calculated score difference. Native proves its association independently.
    struct DisplayStat: Equatable {
        let figure: String
        let unit: String
        let provenance: String?
        let spoken: String
    }

    /// Context, never a grade: it neither selects nor settles an original.
    enum Actual: Equatable {
        case count(Count)
        case pair(Pair)
        /// The owner's words for no admitted actual.
        case missing(String)
    }

    /// The owner's explicit decoration for an original's own result.
    /// Supplementary to the result words, which carry the meaning.
    enum ResultMark: Equatable {
        case positive, negative

        var symbol: String {
            switch self {
            case .positive: return "checkmark.circle.fill"
            case .negative: return "xmark.circle.fill"
            }
        }
    }

    struct Panel: Equatable {
        /// The exact original this panel shows; nil when the owner has none.
        let original: Details.Identity?
        /// "Fokina" — the panel's name.
        let subject: String
        /// "Fokina to win at least one set" — the owner-proved predicate.
        let predicate: String
        /// "+1.5 sets" — the original's own condition, verbatim.
        let condition: String
        let actual: Actual
        /// Shown only beside the original's own supplied grade.
        let resultMark: ResultMark?
        /// "Opens the original +1.5 sets prop." — only when the panel acts.
        let openHint: String
        /// Owner-updated market context; admitted only with live comparison
        /// content, never used as a grade or inferred from physical progress.
        var pendingMarketContext: String? = nil
        /// Optional compact live statistic; owner proves its association with actual.
        var liveProgress: DisplayStat? = nil
    }

    struct Group: Equatable {
        /// "Win at least one set"
        let heading: String
        /// In the owner's order — never sorted by chance or result.
        let panels: [Panel]
    }

    struct Words: Equatable {
        let eyebrow: String
        let title: String
        /// "How these props work"
        let explanationTitle: String
        /// The owner's paragraphs, verbatim.
        let explanation: [String]
        /// Shown only when a displayed panel can act.
        let tapInvitation: String
        /// In place of every panel when the catalogue's scope is unusable.
        let scopeUnavailable: String
        /// A panel whose original cannot be named exactly.
        let panelUnavailable: String
        /// A panel whose original is not in result mode.
        let comparisonUnavailable: String
    }

    struct Input: Equatable {
        let phase: Phase
        let catalogue: Details.Catalogue?
        /// The host's held selection; only marked, never changed here.
        let held: Details.Selection?
        let groups: [Group]
        let words: Words
        /// Nonbreaking opt-in. It does not change the final presentation.
        var showsDuringPlay: Bool = false
        /// Separately admitted before-only presentation; live/final remain unchanged.
        var showsBeforePlay: Bool = false
    }

    /// A placed panel's final readings, from the Details' own content.
    struct Shown: Equatable {
        /// The original's pregame reading (hollow) or its own missing words.
        let chance: Details.ShownReading
        /// The original's own result words and settlement provenance.
        let result: Details.ShownResult
        let mark: ResultMark?
    }

    /// Bounded presentation of the existing content, with no new market policy.
    struct LiveShown: Equatable {
        let readings: [Details.ShownReading]
        let result: Details.ShownResult?
        let mark: ResultMark?
        let pendingMarketContext: String?
    }

    /// A before-only projection: no place to carry actual/later/result channels.
    struct BeforeShown: Equatable {
        let chance: Details.ShownReading?
        /// A non-pregame original still opens its exact Details, but its mode
        /// is not silently rewritten. Only its admitted before reading survives.
        let unavailable: String?
    }

    enum State: Equatable {
        case before(BeforeShown)
        case live(LiveShown)
        case shown(Shown)
        /// The exact original resolves but is not in result mode; it still opens.
        case comparisonUnavailable(String)
        /// No exact original; nothing attaches and nothing opens.
        case unavailable(String)
    }

    enum ExplanationStyle: Equatable {
        case none
        /// The host's disclosure binding drives it.
        case disclosure
        /// No binding: the content shows in full, never an inert control.
        case expanded
    }

    static let actualLabel = "Actual"

    /// Final by default; live only on the true during phase with explicit opt-in.
    static func isShown(_ input: Input) -> Bool {
        input.phase == .final || isLive(input) || isBefore(input)
    }

    static func isBefore(_ input: Input) -> Bool {
        input.phase == .before && input.showsBeforePlay
    }

    static func isLive(_ input: Input) -> Bool {
        input.phase == .during && input.showsDuringPlay
    }

    /// The catalogue, in a displayed phase, with a nonblank scope; else no panel resolves.
    static func catalogue(_ input: Input) -> Details.Catalogue? {
        guard isShown(input), let catalogue = input.catalogue, nonBlank(catalogue.scope) != nil else { return nil }
        return catalogue
    }

    static func panels(_ input: Input) -> [Panel] {
        input.groups.flatMap(\.panels)
    }

    /// The panel's exact selection — the catalogue's scope and the panel's
    /// identity, unchanged — when that identity opens its own Details, the
    /// panel has its predicate and no other panel names the same original.
    /// Membership is the Details' exact-identity match, never a whole-payload
    /// comparison, so an ignored value (NaN included) cannot close an original.
    static func selection(_ panel: Panel, in input: Input) -> Details.Selection? {
        guard let catalogue = catalogue(input), let identity = panel.original, nonBlank(panel.predicate) != nil,
              panels(input).filter({ $0.original == identity }).count == 1 else { return nil }
        let candidate = Details.Selection(scope: catalogue.scope, identity: identity)
        return Details.content(catalogue: catalogue, selection: candidate) == nil ? nil : candidate
    }

    /// Nil when the card shows no panels. A result-mode original shows its
    /// pregame reading and its own result; any other mode keeps the comparison
    /// unavailable rather than reading a later chance as final.
    static func state(_ panel: Panel, in input: Input) -> State? {
        guard isShown(input) else { return nil }
        guard let catalogue = catalogue(input) else {
            return (isLive(input) || isBefore(input)) ? .unavailable(nonBlank(input.words.scopeUnavailable) ?? Details.unavailable) : nil
        }
        guard let selection = selection(panel, in: input),
              let original = Details.original(in: catalogue, selection: selection),
              let content = Details.content(catalogue: catalogue, selection: selection) else {
            return .unavailable(nonBlank(input.words.panelUnavailable) ?? Details.unavailable)
        }
        if isBefore(input) {
            return .before(BeforeShown(chance: content.readings.first { $0.label == Details.pregameLabel },
                                       unavailable: original.mode == .pregame ? nil : "Pregame presentation unavailable"))
        }
        if isLive(input) {
            let pending: String?
            if case .comparison = original.mode {
                pending = nonBlank(panel.pendingMarketContext)
            } else {
                pending = nil
            }
            let graded = content.result != nil && original.grade.flatMap { nonBlank($0.words) } != nil
            return .live(LiveShown(readings: content.readings, result: content.result,
                                   mark: graded ? panel.resultMark : nil, pendingMarketContext: pending))
        }
        guard original.mode == .result, let chance = content.readings.first, let result = content.result else {
            return .comparisonUnavailable(nonBlank(input.words.comparisonUnavailable) ?? Details.unavailable)
        }
        let graded = original.grade.flatMap { nonBlank($0.words) } != nil
        return .shown(Shown(chance: chance, result: result, mark: graded ? panel.resultMark : nil))
    }

    static func isSelected(_ panel: Panel, in input: Input) -> Bool {
        guard let selection = selection(panel, in: input) else { return false }
        return selection == input.held
    }

    /// The only way a panel acts: the chooser's own action with the panel's
    /// exact selection. Nil — static content, never an inert button — before
    /// the final, without a callback, or when the panel's original does not
    /// open. The view's buttons run exactly this closure.
    static func action(_ panel: Panel, in input: Input,
                       onSelect: ((Details.Selection) -> Void)?) -> (() -> Void)? {
        let choice = Chooser.Choice(label: panel.predicate, selection: selection(panel, in: input),
                                    isSelected: isSelected(panel, in: input), status: nil)
        return Chooser.action(choice, onSelect: onSelect)
    }

    /// True only when a displayed panel carries a real action.
    static func showsTapInvitation(_ input: Input, onSelect: ((Details.Selection) -> Void)?) -> Bool {
        nonBlank(input.words.tapInvitation) != nil
            && panels(input).contains { action($0, in: input, onSelect: onSelect) != nil }
    }

    /// Blank paragraphs drop.
    static func explanation(_ input: Input) -> [String] {
        input.words.explanation.filter { nonBlank($0) != nil }
    }

    static func explanationStyle(_ input: Input, hasBinding: Bool) -> ExplanationStyle {
        guard !explanation(input).isEmpty else { return .none }
        return hasBinding && nonBlank(input.words.explanationTitle) != nil ? .disclosure : .expanded
    }

    /// "Won · +1.5 sets" — the original's own result words beside its condition.
    static func resultLine(_ result: Details.ShownResult, condition: String) -> String {
        nonBlank(condition).map { "\(result.words) · \($0)" } ?? result.words
    }

    static func actualProvenance(_ provenance: String?) -> String {
        nonBlank(provenance) ?? Details.timeUnknown
    }

    /// The predicate, the original's chance with its provenance, the actual
    /// with its own provenance, then the original's result — each named.
    static func spoken(_ panel: Panel, in input: Input) -> String {
        guard let state = state(panel, in: input) else { return "" }
        if isBefore(input) {
            var parts = [nonBlank(panel.predicate) ?? nonBlank(input.words.panelUnavailable) ?? Details.unavailable]
            if let condition = nonBlank(panel.condition) { parts.append(condition) }
            switch state {
            case .before(let shown):
                if let chance = shown.chance {
                    parts.append("\(chance.label): \(chance.text)" + (chance.provenance.map { ", \($0)" } ?? ""))
                }
                if let unavailable = shown.unavailable { parts.append(unavailable) }
            case .unavailable(let words), .comparisonUnavailable(let words):
                parts.append(words)
            case .live, .shown:
                break // No later/actual/result channel is spoken before play.
            }
            return parts.joined(separator: ". ") + "."
        }
        if case .live(let shown) = state {
            var parts = [nonBlank(panel.predicate) ?? nonBlank(input.words.panelUnavailable) ?? Details.unavailable]
            if let condition = nonBlank(panel.condition) { parts.append(condition) }
            for reading in shown.readings {
                parts.append("\(reading.label): \(reading.text)" + (reading.provenance.map { ", \($0)" } ?? ""))
            }
            parts.append(isLive(input) ? spokenLiveActual(panel) : spokenActual(panel.actual))
            if let result = shown.result {
                parts.append("\(Details.resultLabel): \(result.words)" + (result.provenance.map { ", \($0)" } ?? ""))
            }
            if let pending = shown.pendingMarketContext { parts.append("Market context: \(pending)") }
            return parts.joined(separator: ". ") + "."
        }
        var parts = [nonBlank(panel.predicate) ?? nonBlank(input.words.panelUnavailable) ?? Details.unavailable]
        if isLive(input), let condition = nonBlank(panel.condition) { parts.append(condition) }
        if case .shown(let shown) = state {
            let chance = shown.chance
            parts.append(chance.provenance.map { "\(chance.label) \(chance.text), \($0)" } ?? "\(chance.label): \(chance.text)")
        }
        parts.append(isLive(input) ? spokenLiveActual(panel) : spokenActual(panel.actual))
        switch state {
        case .before, .live:
            break // Handled above without borrowing final channels.
        case .shown(let shown):
            parts.append("\(Details.resultLabel): \(shown.result.words)"
                         + (shown.result.provenance.map { ", \($0)" } ?? ""))
        case .comparisonUnavailable(let words), .unavailable(let words):
            parts.append(words)
        }
        return parts.joined(separator: ". ") + "."
    }

    static func spokenLiveActual(_ panel: Panel) -> String {
        guard let stat = panel.liveProgress else { return spokenActual(panel.actual) }
        return "\(actualLabel): \(nonBlank(stat.spoken) ?? "\(stat.figure) \(stat.unit)"), \(actualProvenance(stat.provenance))"
    }

    static func spokenActual(_ actual: Actual) -> String {
        switch actual {
        case .count(let count):
            return "\(actualLabel): \(nonBlank(count.spoken) ?? "\(count.figure) \(count.unit)"), \(actualProvenance(count.provenance))"
        case .pair(let pair):
            return "\(actualLabel): \(nonBlank(pair.spoken) ?? pair.caption), \(actualProvenance(pair.provenance))"
        case .missing(let words):
            return "\(actualLabel): \(nonBlank(words) ?? Details.unavailable)"
        }
    }

    /// Stable ids so the host can return focus to the originating panel.
    static func accessibilityID(_ panel: Panel, group: Int, index: Int) -> String {
        guard let id = panel.original else { return "originalHandicap9483.slot.\(group).\(index)" }
        return "originalHandicap9483.panel.\(id.source).\(id.market).\(id.side)"
    }

    static func nonBlank(_ text: String?) -> String? {
        guard let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return text
    }
}

/// Internal only so tests can read the layout decision.
enum OriginalHandicapLayout9483 {
    static let minimumTarget: CGFloat = 44

    /// The equal width at which a group's panels share one row, or nil to
    /// stack them at full width. They share only when that width still holds
    /// every panel's whole ideal width (and a 44 pt target); a lone panel,
    /// accessibility sizes and malformed input always stack.
    static func sharedWidth(available: CGFloat, ideals: [CGFloat], spacing: CGFloat,
                            accessibilitySize: Bool) -> CGFloat? {
        guard ideals.count > 1, !accessibilitySize, ideals.allSatisfy({ $0.isFinite && $0 >= 0 }),
              spacing.isFinite, spacing >= 0, !available.isNaN, available >= 0 else { return nil }
        let widest = max(ideals.max() ?? 0, minimumTarget)
        guard available.isFinite else { return widest }
        let share = (available - spacing * CGFloat(ideals.count - 1)) / CGFloat(ideals.count)
        return share >= widest ? share : nil
    }
}

/// One group's panels: side by side at an equal width when every panel fits
/// whole, else stacked at full width. The size it reports is what it places.
private struct OriginalHandicapPanelsLayout9483: Layout {
    let spacing: CGFloat
    let accessibilitySize: Bool

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        plan(width: proposal.width, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let frames = plan(width: bounds.width, subviews: subviews).frames
        for (subview, frame) in zip(subviews, frames) {
            subview.place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                          anchor: .topLeading, proposal: ProposedViewSize(frame.size))
        }
    }

    private func plan(width: CGFloat?, subviews: Subviews) -> (frames: [CGRect], size: CGSize) {
        let minimum = OriginalHandicapLayout9483.minimumTarget
        let ideals = subviews.map { $0.sizeThatFits(.unspecified).width }
        if let share = OriginalHandicapLayout9483.sharedWidth(available: width ?? .infinity, ideals: ideals,
                                                               spacing: spacing, accessibilitySize: accessibilitySize) {
            let tallest = subviews.map { $0.sizeThatFits(ProposedViewSize(width: share, height: nil)).height }.max() ?? 0
            let height = max(tallest, minimum)
            let frames = subviews.indices.map { index in
                CGRect(x: CGFloat(index) * (share + spacing), y: 0, width: share, height: height)
            }
            let count = CGFloat(subviews.count)
            return (frames, CGSize(width: count * share + (count - 1) * spacing, height: height))
        }
        let full = width.flatMap { $0.isFinite ? $0 : nil } ?? max(ideals.max() ?? 0, minimum)
        var frames: [CGRect] = []
        var y: CGFloat = 0
        for subview in subviews {
            let height = max(subview.sizeThatFits(ProposedViewSize(width: full, height: nil)).height, minimum)
            frames.append(CGRect(x: 0, y: y, width: full, height: height))
            y += height + spacing
        }
        return (frames, CGSize(width: full, height: max(y - spacing, 0)))
    }
}

/// The handicap card inside the host's container; the host keeps scrolling,
/// held updates, Details, Back and focus.
struct OriginalHandicapCardView9483: View {
    let input: OriginalHandicapCard9483.Input
    let tint: Color
    /// The host's disclosure state for the explanation; nil shows it expanded.
    var explanationExpanded: Binding<Bool>? = nil
    var onSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil

    private typealias Model = OriginalHandicapCard9483
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var countSize: CGFloat = 25
    @ScaledMetric(relativeTo: .title) private var gameSize: CGFloat = 30
    @ScaledMetric(relativeTo: .caption) private var blockWidth: CGFloat = 24
    @ScaledMetric(relativeTo: .caption) private var blockHeight: CGFloat = 9

    var body: some View {
        if Model.isShown(input) {
            VStack(alignment: .leading, spacing: 18) {
                header
                if Model.catalogue(input) != nil || Model.isLive(input) || Model.isBefore(input) {
                    ForEach(Array(input.groups.enumerated()), id: \.offset) { index, group in
                        groupView(group, index: index)
                    }
                    if Model.showsTapInvitation(input, onSelect: onSelect) {
                        Text(input.words.tapInvitation)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    explanation
                } else {
                    Text(Model.nonBlank(input.words.scopeUnavailable) ?? OriginalMarketDetails9483.unavailable)
                        .font(.headline)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let eyebrow = Model.nonBlank(input.words.eyebrow) {
                Text(eyebrow).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            }
            Text(input.words.title)
                .font(.title3.weight(.bold))
                .accessibilityAddTraits(.isHeader)
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    private func groupView(_ group: Model.Group, index: Int) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if let heading = Model.nonBlank(group.heading) {
                Text(heading)
                    .font(.subheadline.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
            }
            OriginalHandicapPanelsLayout9483(spacing: 10, accessibilitySize: typeSize.isAccessibilitySize) {
                ForEach(Array(group.panels.enumerated()), id: \.offset) { offset, panel in
                    control(panel, group: index, index: offset)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func control(_ panel: Model.Panel, group: Int, index: Int) -> some View {
        let selected = Model.isSelected(panel, in: input)
        if let action = Model.action(panel, in: input, onSelect: onSelect) {
            Button(action: action) {
                face(panel, selected: selected, acts: true)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(Model.spoken(panel, in: input))
            .accessibilityHint(Model.nonBlank(panel.openHint) ?? "")
            .accessibilityAddTraits(selected ? .isSelected : [])
            .accessibilityIdentifier(Model.accessibilityID(panel, group: group, index: index))
        } else {
            face(panel, selected: selected, acts: false)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(Model.spoken(panel, in: input))
                .accessibilityAddTraits(selected ? .isSelected : [])
                .accessibilityIdentifier(Model.accessibilityID(panel, group: group, index: index))
        }
    }

    /// Selected: a heavier tinted outline and fill, not colour alone.
    private func face(_ panel: Model.Panel, selected: Bool, acts: Bool) -> some View {
        let shape = RoundedRectangle(cornerRadius: 14)
        return VStack(alignment: .leading, spacing: 10) {
            if let subject = Model.nonBlank(panel.subject) {
                Text(subject).font(.headline)
            }
            if (Model.isLive(input) || Model.isBefore(input)), let condition = Model.nonBlank(panel.condition) {
                Text(condition).font(.subheadline.weight(.semibold))
            }
            switch Model.state(panel, in: input) {
            case .before(let shown)?:
                if let before = shown.chance { chance(before) }
                if let unavailable = shown.unavailable {
                    Text(unavailable).font(.subheadline.weight(.semibold)).foregroundStyle(.secondary)
                }
            case .live(let shown)?:
                ForEach(shown.readings, id: \.label) { reading in
                    chance(reading)
                }
                liveActual(panel)
                if let originalResult = shown.result, let before = shown.readings.first {
                    result(Model.Shown(chance: before, result: originalResult, mark: shown.mark),
                           condition: panel.condition, acts: acts)
                }
                if let pending = shown.pendingMarketContext {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Market context").font(.caption).foregroundStyle(.secondary)
                        Text(pending).font(.subheadline.weight(.semibold))
                    }
                }
            case .shown(let shown)?:
                chance(shown.chance)
                actual(panel.actual)
                result(shown, condition: panel.condition, acts: acts)
            case .comparisonUnavailable(let words)?, .unavailable(let words)?:
                if !Model.isBefore(input) {
                    if Model.isLive(input) { liveActual(panel) } else { actual(panel.actual) }
                }
                Text(words)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
            case nil:
                EmptyView()
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: OriginalHandicapLayout9483.minimumTarget, alignment: .topLeading)
        .background(shape.fill(selected ? tint.opacity(0.10) : Color.clear))
        .overlay(shape.strokeBorder(selected ? tint : Color.secondary.opacity(0.35), lineWidth: selected ? 2 : 1))
        .contentShape(shape)
    }

    /// The original's own figure and its rail, reusing the Details' pieces.
    /// Provenance stays in the spoken summary and the original's Details, out
    /// of the compact panel.
    private func chance(_ reading: OriginalMarketDetails9483.ShownReading) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            ProbabilityDetailsFigures9483(figures: [
                ProbabilityDetailsFigure9483(label: reading.label, marker: reading.marker, text: reading.text,
                                             isValue: reading.isValue, dateLine: nil),
            ], tint: tint)
            if let placement = reading.placement {
                ProbabilityDetailsRail9483(marks: [
                    ProbabilityDetailsRailMark9483(id: reading.label, marker: reading.marker, value: placement),
                ], tint: tint)
            }
        }
    }

    private func liveActual(_ panel: Model.Panel) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(Model.actualLabel).font(.caption).foregroundStyle(.secondary)
            if let stat = panel.liveProgress {
                progressFigure(stat.figure, unit: stat.unit)
            } else {
                actual(panel.actual)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The actual's provenance is spoken, not printed in the compact panel.
    @ViewBuilder
    private func actual(_ actual: Model.Actual) -> some View {
        switch actual {
        case .count(let count):
            VStack(alignment: .leading, spacing: 6) {
                if Model.isLive(input) {
                    progressFigure(count.figure, unit: count.unit)
                } else {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(count.figure).font(.system(size: countSize, weight: .bold).monospacedDigit())
                        Text(count.unit).font(.footnote).foregroundStyle(.secondary)
                    }
                }
                if !count.blocks.isEmpty {
                    HStack(spacing: 4) {
                        ForEach(Array(count.blocks.enumerated()), id: \.offset) { _, won in
                            block(won)
                        }
                    }
                    .accessibilityHidden(true)
                }
            }
        case .pair(let pair):
            VStack(alignment: .leading, spacing: 6) {
                Text(pair.caption).font(.footnote).foregroundStyle(.secondary)
                gamePair(pair)
            }
        case .missing(let words):
            Text(Model.nonBlank(words) ?? OriginalMarketDetails9483.unavailable)
                .font(.subheadline.weight(.semibold))
        }
    }

    /// Stacked, bounded figure/unit avoids an unbreakable progress group at AX.
    private func progressFigure(_ figure: String, unit: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(figure).font(.system(size: countSize, weight: .bold).monospacedDigit())
            Text(unit).font(.footnote).foregroundStyle(.secondary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Filled for a set won, outlined otherwise — shape, not colour alone.
    private func block(_ won: Bool) -> some View {
        let shape = RoundedRectangle(cornerRadius: 2)
        return shape
            .fill(won ? Color.primary : Color.clear)
            .overlay(shape.strokeBorder(Color.secondary.opacity(0.5), lineWidth: 1))
            .frame(width: blockWidth, height: blockHeight)
    }

    /// Each figure stays over its player's name; the relation word sits between
    /// them in a row, or between them in a stack when the row does not fit.
    @ViewBuilder
    private func gamePair(_ pair: Model.Pair) -> some View {
        if typeSize.isAccessibilitySize {
            stackedPair(pair)
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .center, spacing: 8) {
                    pairSide(pair.first).fixedSize()
                    Spacer(minLength: 8)
                    Text(pair.relation).font(.footnote).foregroundStyle(.secondary).fixedSize()
                    Spacer(minLength: 8)
                    pairSide(pair.second).fixedSize()
                }
                stackedPair(pair)
            }
        }
    }

    private func stackedPair(_ pair: Model.Pair) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            pairSide(pair.first)
            Text(pair.relation).font(.footnote).foregroundStyle(.secondary)
            pairSide(pair.second)
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    private func pairSide(_ side: Model.PairSide) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(side.figure).font(.system(size: gameSize, weight: .bold).monospacedDigit())
            Text(side.name).font(.footnote).foregroundStyle(.secondary)
        }
    }

    /// The settlement provenance is spoken and stays in the original's Details.
    private func result(_ shown: Model.Shown, condition: String, acts: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(OriginalMarketDetails9483.resultLabel).font(.caption).foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                if let mark = shown.mark {
                    Image(systemName: mark.symbol)
                        .foregroundStyle(mark == .positive ? tint : Color.primary)
                        .accessibilityHidden(true)
                }
                Text(Model.resultLine(shown.result, condition: condition))
                    .font(.subheadline.weight(.semibold))
                if acts {
                    Image(systemName: "chevron.right")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .accessibilityHidden(true)
                }
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private var explanation: some View {
        let paragraphs = Model.explanation(input)
        switch Model.explanationStyle(input, hasBinding: explanationExpanded != nil) {
        case .none:
            EmptyView()
        case .disclosure:
            if let binding = explanationExpanded {
                DisclosureGroup(isExpanded: binding) {
                    explanationText(paragraphs).padding(.top, 6)
                } label: {
                    Text(input.words.explanationTitle)
                        .font(.subheadline.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, minHeight: OriginalHandicapLayout9483.minimumTarget,
                               alignment: .leading)
                        .contentShape(Rectangle())
                }
            }
        case .expanded:
            VStack(alignment: .leading, spacing: 6) {
                if let title = Model.nonBlank(input.words.explanationTitle) {
                    Text(title).font(.subheadline.weight(.semibold))
                }
                explanationText(paragraphs)
            }
        }
    }

    private func explanationText(_ paragraphs: [String]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(paragraphs.enumerated()), id: \.offset) { _, paragraph in
                Text(paragraph).font(.footnote).foregroundStyle(.secondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
