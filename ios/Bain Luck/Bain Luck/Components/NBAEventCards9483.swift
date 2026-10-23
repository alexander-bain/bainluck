import Charts
import SwiftUI

/// #9483 — the NBA ladders drawn compact in the deck and full size in the
/// reader (design freeze v328; web twin `LadderCardView` in
/// `frontend/components/event/NFLEventCards.tsx`). Compact and full size read
/// the same card value and the same selection (`NFLCardDeckState9483`).
///
/// Two axes, never merged: the stat axis (points, or a signed margin with the
/// tie in the middle) and the chance axis. The actual and the pregame
/// projection are values on the stat axis, never probabilities. With no chance
/// to draw — a final whose lines carry no admitted pin — the chance axis goes
/// and the plot becomes a strip of the lines with the actual marked on it.
struct NBALadderCardView9483: View {
    let card: NBALadderCard9483
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false
    @ScaledMetric(relativeTo: .caption2) private var scaledAxisFont: CGFloat = 12
    private var axisFontSize: CGFloat { EventChartTypography.labelSize(scaled: scaledAxisFont) }

    private var isMargin: Bool { card.family == .margin }

    var body: some View {
        let selected = state.selectedIndex(in: card)
        let point = selected.map { card.points[$0] }
        VStack(alignment: .leading, spacing: 10) {
            Text(card.title.uppercased())
                .font(.caption.weight(.bold))
                .foregroundStyle(.secondary)
            if card.actual != nil || card.forecast != nil {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 24) { figures }
                    VStack(alignment: .leading, spacing: 6) { figures }
                }
            }
            Text(card.caption)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            chart(selected: point)
            if isMargin {
                HStack {
                    Text("← \(card.awayShort) by")
                    Spacer(minLength: 8)
                    Text("\(card.homeShort) by →")
                }
                .font(.caption2)
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            }
            HStack(spacing: 4) {
                Button { state.move(in: card, by: -1) } label: {
                    Image(systemName: "chevron.left").frame(width: 44, height: 44)
                }
                .disabled(selected.map { $0 == 0 } ?? true)
                .accessibilityLabel("Previous line")
                if expanded {
                    Button {
                        if let point { state.detailsRowID = point.optionKey }
                    } label: {
                        readout(point)
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("Shows this line's exact quote")
                } else {
                    readout(point)
                        .accessibilityElement(children: .combine)
                }
                Button { state.move(in: card, by: 1) } label: {
                    Image(systemName: "chevron.right").frame(width: 44, height: 44)
                }
                .disabled(selected.map { $0 >= card.points.count - 1 } ?? true)
                .accessibilityLabel("Next line")
            }
            if card.forecast != nil {
                Text(card.actual != nil ? "Solid line = actual · dashed = pregame projection"
                     : "Dashed line = pregame projection")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    /// The actual and the pregame projection, each named for what it is.
    @ViewBuilder private var figures: some View {
        if let actual = card.actual {
            figure(card.phase == .after ? "Actual final" : "So far", value: actual)
        }
        if let forecast = card.forecast {
            figure("Pregame projection", value: forecast)
        }
    }

    private func figure(_ label: String, value: Double) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            // Wraps like its value at large sizes: "Pregame projection",
            // never "Pregame proje…".
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Text(card.words(value) + (isMargin ? "" : " points"))
                .font(.headline.monospacedDigit())
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }

    private func color(_ point: NBALadderCard9483.Point) -> Color {
        point.side == .away ? awayColor : homeColor
    }

    private func readout(_ point: NBALadderCard9483.Point?) -> some View {
        VStack(spacing: 2) {
            if let point {
                let text = Self.readout(card, point)
                Text(text.main)
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                    .foregroundStyle(point.chance == nil ? Color.secondary : color(point))
                let more = expanded ? (text.sub.isEmpty ? "Details" : " · details") : ""
                if !text.sub.isEmpty || !more.isEmpty {
                    Text(text.sub + more)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .multilineTextAlignment(.center)
        .frame(maxWidth: .infinity, minHeight: 44)
        .contentShape(Rectangle())
    }

    /// The readout's two lines. Before tip-off a line with no dot is a price
    /// that stopped being observed; afterwards the caption already says the
    /// pregame chance is unavailable, so the readout does not repeat it. The
    /// grade and the current quote are named on their own, never as the chance.
    static func readout(_ card: NBALadderCard9483, _ point: NBALadderCard9483.Point) -> (main: String, sub: String) {
        let main: String
        if let chance = point.chance {
            main = "\(point.label) · \(formatProbability(chance))"
        } else {
            main = card.phase == .before ? "\(point.label) · No recent probability update" : point.label
        }
        var parts: [String] = []
        if let result = point.result {
            parts.append(result ? "Hit" : "Miss")
        } else if point.chance != nil {
            parts.append(card.phase == .before ? "Pregame chance" : "Before tip-off")
        }
        if let now = point.now { parts.append("now \(formatProbability(now))") }
        return (main, parts.joined(separator: " · "))
    }

    /// The stat axis: every line, the actual and the projection inside it,
    /// padded; a margin axis is symmetric about the tie.
    static func domain(_ card: NBALadderCard9483) -> ClosedRange<Double> {
        let xs = card.points.map(\.x) + [card.actual, card.forecast].compactMap { $0 }
        let low = xs.min() ?? 0, high = xs.max() ?? 1
        let pad = max((high - low) * 0.06, 1)
        if card.family == .margin {
            let reach = (xs.map(abs).max() ?? 1) + pad
            return -reach...reach
        }
        return (low - pad)...(high + pad)
    }

    static func ticks(_ card: NBALadderCard9483, domain: ClosedRange<Double>) -> [Double] {
        let span = domain.upperBound - domain.lowerBound
        let step: Double = card.family == .margin ? (domain.upperBound > 24 ? 10 : 5) : (span > 60 ? 20 : 10)
        let first = (domain.lowerBound / step).rounded(.up) * step
        return Array(stride(from: first, through: domain.upperBound, by: step))
    }

    static func tickText(_ card: NBALadderCard9483, _ value: Double) -> String {
        guard card.family == .margin else { return NBALadderCard9483.number(value) }
        return value == 0 ? "Tie" : NBALadderCard9483.number(abs(value))
    }

    private func chart(selected: NBALadderCard9483.Point?) -> some View {
        let domain = Self.domain(card)
        let ticks = Self.ticks(card, domain: domain)
        let drawn = card.points.filter { $0.chance != nil }
        let hasDots = !drawn.isEmpty
        return Chart {
            if hasDots {
                RuleMark(y: .value("Chance", 0.5))
                    .foregroundStyle(Color.secondary.opacity(0.35))
                    .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
            }
            if isMargin {
                RuleMark(x: .value("Margin", 0.0))
                    .foregroundStyle(Color.secondary.opacity(0.5))
            }
            if let forecast = card.forecast {
                RuleMark(x: .value("Projection", forecast))
                    .foregroundStyle(Color.secondary)
                    .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [4, 3]))
            }
            if let actual = card.actual {
                RuleMark(x: .value("Actual", actual))
                    .foregroundStyle(Color.primary)
                    .lineStyle(StrokeStyle(lineWidth: 2))
            }
            ForEach(card.points) { point in
                let isSelected = point.optionKey == selected?.optionKey
                if let chance = point.chance {
                    RuleMark(x: .value("Line", point.x),
                             yStart: .value("Chance", 0), yEnd: .value("Chance", chance))
                        .foregroundStyle(color(point).opacity(isSelected ? 0.9 : 0.3))
                        .lineStyle(StrokeStyle(lineWidth: isSelected ? 2 : 1.5))
                    PointMark(x: .value("Line", point.x), y: .value("Chance", chance))
                        .symbol {
                            Circle()
                                .strokeBorder(isSelected ? color(point) : Color.secondary, lineWidth: isSelected ? 2.5 : 1.5)
                                .background(Circle().fill(Color.cardBackground))
                                .frame(width: isSelected ? 13 : 8, height: isSelected ? 13 : 8)
                        }
                } else if isSelected {
                    // A selected line with no number still shows where it is.
                    RuleMark(x: .value("Line", point.x),
                             yStart: .value("Chance", 0), yEnd: .value("Chance", 0.12))
                        .foregroundStyle(color(point))
                        .lineStyle(StrokeStyle(lineWidth: 2.5))
                }
            }
        }
        .chartXScale(domain: domain)
        .chartYScale(domain: 0...1)
        // With no chance drawn there is no chance axis to label.
        .chartYAxis {
            AxisMarks(position: .leading, values: hasDots ? [0, 0.5, 1] : [Double]()) { value in
                AxisGridLine().foregroundStyle(Color.secondary.opacity(0.15))
                AxisValueLabel {
                    if let chance = value.as(Double.self) { Text("\(Int((chance * 100).rounded()))%") }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: ticks) { value in
                NFLStatAxisLabels9483.reservedLabel(
                    value.as(Double.self).map { Self.tickText(card, $0) } ?? "", fontSize: axisFontSize)
            }
        }
        // Each line has its own small tick; the stat labels are drawn by us,
        // centred, and dropped whole rather than overlapped (#8481's rule).
        .chartOverlay { proxy in
            GeometryReader { geo in
                ZStack {
                    ForEach(card.points) { point in
                        if let x = proxy.position(forX: point.x) {
                            Rectangle()
                                .fill(Color.secondary.opacity(0.6))
                                .frame(width: 1, height: 4)
                                .position(x: geo[proxy.plotAreaFrame].minX + x, y: geo[proxy.plotAreaFrame].maxY + 2)
                        }
                    }
                    NFLStatAxisLabels9483(values: ticks, texts: ticks.map { Self.tickText(card, $0) },
                                          keep: nil, fontSize: axisFontSize, proxy: proxy,
                                          plotFrame: geo[proxy.plotAreaFrame])
                }
                .accessibilityHidden(true)
                .allowsHitTesting(false)
            }
        }
        .frame(height: hasDots ? (expanded ? 220 : 150) : (expanded ? 96 : 64))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spokenSummary(drawn))
    }

    private func spokenSummary(_ drawn: [NBALadderCard9483.Point]) -> String {
        var text = "\(card.title). \(card.caption): "
        text += drawn.isEmpty ? "none recorded"
            : drawn.map { "\($0.label) \(formatProbability($0.chance ?? 0))" }.joined(separator: ", ")
        if let actual = card.actual {
            text += ". \(card.phase == .after ? "Final" : "So far") \(card.words(actual))"
        }
        if let forecast = card.forecast { text += ". Pregame projection \(card.words(forecast))" }
        return text
    }
}

/// The served option behind a ladder line, frozen with the held card: what
/// the venue last quoted (dated), the admitted pregame pin or its absence, and
/// the producer's grade — each named for what it is, never merged.
struct NBAOptionDetails9483: View {
    let detail: NBALadderCard9483.Detail
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text(detail.label).font(.headline)
                    LabeledContent("Market", value: detail.marketName)
                }
                Section {
                    LabeledContent("Pregame baseline", value: detail.baseline.map {
                        formatProbability($0) + (SourceAge.preciseStamp(detail.baselineObservedAt).map { " · \($0)" } ?? "")
                    } ?? "Unavailable")
                    // Always dated: a quote's number without its time cannot
                    // say whether it is current.
                    if let quoted = detail.quoted {
                        LabeledContent("Last quote", value: formatProbability(quoted))
                        LabeledContent("Quoted", value: SourceAge.preciseStamp(detail.observedAt) ?? "Time unknown")
                    }
                    if let name = SourceLabels.label(for: detail.source) {
                        LabeledContent("Venue", value: name)
                    }
                }
                if let result = detail.result {
                    Section("Result") {
                        LabeledContent("Graded", value: result ? "Hit" : "Miss")
                    }
                }
            }
            .navigationTitle("Line details")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }
}
