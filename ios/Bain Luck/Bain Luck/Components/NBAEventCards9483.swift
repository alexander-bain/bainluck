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
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .caption2) private var scaledAxisFont: CGFloat = 12
    /// Half the height of the chance axis's top label, which is centred on
    /// the plot's top edge and grows with Dynamic Type.
    @ScaledMetric(relativeTo: .caption2) private var chanceLabelReach: CGFloat = 8
    private var axisFontSize: CGFloat { EventChartTypography.labelSize(scaled: scaledAxisFont) }

    private var isMargin: Bool { card.family == .margin }

    var body: some View {
        let selected = state.selectedIndex(in: card)
        let point = selected.map { card.points[$0] }
        VStack(alignment: .leading, spacing: 10) {
            Text(card.title.uppercased())
                .font(.caption.weight(.bold))
                .foregroundStyle(.secondary)
            if card.phase == .during && (card.actual != nil || card.forecast != nil) {
                // Large, keyed actual-vs-pregame comparison; the key replaces
                // the caption line below the controls.
                NBAScoringFigures9483(card: card, awayColor: awayColor, homeColor: homeColor)
            } else if card.actual != nil || card.forecast != nil {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 24) { figures }
                    VStack(alignment: .leading, spacing: 6) { figures }
                }
            }
            if card.phase == .during {
                NBAScoringChanceComparison9483(point: point,
                                               tint: point.map { color($0) } ?? .secondary)
            }
            Text(card.phase == .during
                 ? (isMargin ? "Chance to win by more than each margin" : "Chance to finish above each line")
                 : card.caption)
                .font(card.phase == .during ? .subheadline : .caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            chart(selected: point)
            // The comparison above keys hollow/filled whenever it has a line;
            // with the selection unavailable it carries no key, so this does.
            if card.phase == .during && point == nil {
                chanceKey
            }
            if isMargin {
                sideKey
            }
            lineControls(selected: selected, point: point)
            if card.phase != .during, card.forecast != nil {
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

    /// Hollow = pregame, filled = current; whole words, stacked at
    /// accessibility sizes rather than broken mid-word.
    private var chanceKey: some View {
        Group {
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 4) {
                    Label("Pregame", systemImage: "circle")
                    Label("Current", systemImage: "circle.fill")
                }
            } else {
                HStack(spacing: 16) {
                    Label("Pregame", systemImage: "circle")
                    Label("Current", systemImage: "circle.fill")
                }
            }
        }
        .font(.subheadline)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityLabel("Hollow marks: pregame chance. Filled marks: current chance.")
    }

    /// Which side each half of the margin axis favours. The arrow is held to
    /// its name (no-break space); at accessibility sizes the halves stack,
    /// away still leading and home still trailing.
    private var sideKey: some View {
        let away = Text("←\u{00A0}\(card.awayShort) by")
        let home = Text("\(card.homeShort) by\u{00A0}→")
        return Group {
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 2) {
                    away
                        .fixedSize(horizontal: false, vertical: true)
                    home
                        .multilineTextAlignment(.trailing)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
            } else {
                HStack {
                    away
                    Spacer(minLength: 8)
                    home
                }
            }
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
        .accessibilityHidden(true)
    }

    /// Previous / selected line / next. During play the comparison above
    /// already names the selected line, so the compact card shows only the
    /// steps (each naming the adjacent line) and full size adds the details
    /// action; at accessibility sizes the steps stack under it.
    @ViewBuilder private func lineControls(selected: Int?, point: NBALadderCard9483.Point?) -> some View {
        let previous = stepButton(-1, selected: selected)
        let next = stepButton(1, selected: selected)
        if card.phase == .during && !expanded {
            HStack {
                previous
                Spacer(minLength: 16)
                next
            }
        } else if card.phase == .during && typeSize.isAccessibilitySize {
            VStack(spacing: 4) {
                selection(point)
                HStack {
                    previous
                    Spacer(minLength: 16)
                    next
                }
            }
        } else {
            HStack(spacing: 4) {
                previous
                selection(point)
                next
            }
        }
    }

    private func stepButton(_ delta: Int, selected: Int?) -> some View {
        Button { state.move(in: card, by: delta) } label: {
            Image(systemName: delta < 0 ? "chevron.left" : "chevron.right")
                .frame(minWidth: 44, minHeight: 44)
                .contentShape(Rectangle())
        }
        .disabled(delta < 0 ? (selected.map { $0 == 0 } ?? true)
                  : (selected.map { $0 >= card.points.count - 1 } ?? true))
        .accessibilityLabel(card.phase == .during
                            ? NBAScoringLineControls9483.stepLabel(card, selected: selected, by: delta)
                            : (delta < 0 ? "Previous line" : "Next line"))
    }

    @ViewBuilder private func selection(_ point: NBALadderCard9483.Point?) -> some View {
        if expanded && card.phase == .during {
            detailsButton(point)
                .accessibilityLabel(NBAScoringLineControls9483.detailsLabel(point))
        } else if expanded {
            detailsButton(point)
        } else {
            readout(point)
                .accessibilityElement(children: .combine)
        }
    }

    private func detailsButton(_ point: NBALadderCard9483.Point?) -> some View {
        Button {
            if let point { state.detailsRowID = point.optionKey }
        } label: {
            readout(point)
        }
        .buttonStyle(.plain)
        .disabled(point == nil)
        .accessibilityHint("Shows this line's recorded probability and timing")
    }

    private func color(_ point: NBALadderCard9483.Point) -> Color {
        point.side == .away ? awayColor : homeColor
    }

    private func readout(_ point: NBALadderCard9483.Point?) -> some View {
        VStack(spacing: 2) {
            if let point, card.phase == .during {
                // The comparison above names the line and its chances once;
                // this keeps only the existing source action. Its spoken label
                // names the line (`NBAScoringLineControls9483.detailsLabel`).
                HStack(spacing: 4) {
                    Text("Details & timing")
                    Image(systemName: "chevron.right").imageScale(.small)
                }
                .font(.subheadline)
            } else if let point {
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
        let drawn = card.points.filter { $0.chance != nil || (card.phase == .during && $0.now != nil) }
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
                    .lineStyle(NBAScoringFigures9483.forecastStroke)
            }
            if let actual = card.actual {
                RuleMark(x: .value("Actual", actual))
                    .foregroundStyle(Color.primary)
                    .lineStyle(NBAScoringFigures9483.actualStroke)
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
                }
                if card.phase == .during, let current = point.now {
                    // Already admitted/expired by the existing production card.
                    // A filled mark never substitutes for the hollow pregame pin.
                    PointMark(x: .value("Line", point.x), y: .value("Current chance", current))
                        .symbol {
                            Circle().fill(color(point))
                                .frame(width: isSelected ? 9 : 6, height: isSelected ? 9 : 6)
                        }
                }
                if isSelected && point.chance == nil && (card.phase != .during || point.now == nil) {
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
        // The stack's spacing clears the "100%" label at the default size; this
        // adds only what the label has grown since, so the caption above never
        // touches it. The plot's height and domain are unchanged.
        .padding(.top, hasDots ? max(0, chanceLabelReach - 8) : 0)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spokenSummary(drawn))
    }

    private func spokenSummary(_ drawn: [NBALadderCard9483.Point]) -> String {
        var text = "\(card.title). "
        if card.phase == .during {
            text += drawn.isEmpty ? "No recorded pregame or current probabilities."
                : drawn.map { NBAScoringChanceComparison9483.accessibilitySummary(for: $0) }
                    .joined(separator: "; ")
        } else {
            text += "\(card.caption): "
            text += drawn.isEmpty ? "none recorded"
                : drawn.map { "\($0.label) \(formatProbability($0.chance ?? 0))" }.joined(separator: ", ")
        }
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
