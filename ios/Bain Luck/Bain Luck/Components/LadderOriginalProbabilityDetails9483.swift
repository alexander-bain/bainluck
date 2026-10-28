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
        return Content(title: card.title, selected: point.label, readings: readings,
                       result: result, about: about(card.phase, point.detail))
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
    /// once play has started; the last recorded value is historical and
    /// secondary — never "current", never on the rail. `Detail.result` is never
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
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 28

    private typealias Model = LadderOriginalProbabilityDetails9483
    private static let ringSize: CGFloat = 16
    private static let dotSize: CGFloat = 9

    var body: some View {
        if let content = Model.content(card: card, optionKey: optionKey) {
            VStack(alignment: .leading, spacing: 16) {
                summary(content)
                DisclosureGroup("About this market") {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(content.about, id: \.label) { row in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(row.label).font(.footnote).foregroundStyle(.secondary)
                                Text(row.value).font(.subheadline)
                            }
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .accessibilityElement(children: .combine)
                        }
                    }
                    .padding(.top, 8)
                }
                .font(.subheadline)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } else {
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

    private func summary(_ content: Model.Content) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(content.title)
                .font(.title3.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            Text("\(Text("Selected line · ").font(.subheadline).foregroundStyle(.secondary))\(Text(content.selected).font(.headline))")
                .fixedSize(horizontal: false, vertical: true)
            figures(content.readings)
            if !content.marks.isEmpty {
                rail(content.marks)
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

    /// Two readings sit side by side only when both fit whole; otherwise they
    /// stack before anything squeezes, and accessibility sizes always stack.
    @ViewBuilder private func figures(_ readings: [Model.Reading]) -> some View {
        if readings.count < 2 || typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 16) {
                ForEach(readings, id: \.label) { reading($0) }
            }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 24) {
                    ForEach(readings, id: \.label) { reading($0).fixedSize() }
                }
                VStack(alignment: .leading, spacing: 16) {
                    ForEach(readings, id: \.label) { reading($0) }
                }
            }
        }
    }

    private func reading(_ reading: Model.Reading) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Label {
                Text(reading.label).foregroundStyle(.secondary)
            } icon: {
                Image(systemName: reading.marker == .solid ? "circle.fill" : "circle")
                    .foregroundStyle(tint)
            }
            .font(.subheadline)
            if reading.value != nil {
                Text(reading.text)
                    .font(.system(size: figureSize, weight: .bold).monospacedDigit())
                    .foregroundStyle(tint)
            } else {
                Text(reading.text)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.primary)
            }
            if let line = reading.dateLine {
                Text(line).font(.footnote).foregroundStyle(.secondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    /// A 0–100% reference, not a history: each existing reading is one mark at
    /// its raw value — hollow ring for the earlier reading, solid dot for the
    /// current or published one, concentric when they coincide. Nothing joins
    /// the marks.
    private func rail(_ marks: [Model.Reading]) -> some View {
        VStack(spacing: 4) {
            GeometryReader { geo in
                let inset = Self.ringSize / 2
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.secondary.opacity(0.25))
                        .frame(width: max(geo.size.width - 2 * inset, 0), height: 4)
                        .position(x: geo.size.width / 2, y: geo.size.height / 2)
                    ForEach(marks, id: \.label) { mark in
                        if let value = mark.value {
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
                            .position(x: Model.railX(value, width: geo.size.width, inset: inset),
                                      y: geo.size.height / 2)
                            .zIndex(mark.marker == .solid ? 1 : 0)
                        }
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
