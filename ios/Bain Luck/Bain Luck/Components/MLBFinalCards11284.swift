import Charts
import SwiftUI

/// #11284 — the final MLB page's story cards (design ref #10868 v471 MLB /
/// v472 native baseball). Drawn compact in the deck under the chart and full
/// size in the reader (`NFLCardReader9483`), from the same card value and the
/// same selection, so opening a card never changes what it says (v110).
/// Every number is the card's own (`MLBFinalReader11284`); these views only
/// draw it, each named for what it is.

/// One final MLB card, whichever slot.
struct MLBFinalCardView11284: View {
    let card: MLBFinalCard11284
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false

    var body: some View {
        switch card {
        case .homeRuns(let homeRuns):
            MLBHomeRunCardView11284(card: homeRuns, awayColor: awayColor, homeColor: homeColor,
                                    state: state, expanded: expanded)
        case .strikeouts(let milestone):
            MLBMilestoneCardView11284(
                card: milestone,
                color: PlayerPropsTeam.color(for: milestone.side, home: homeColor, away: awayColor),
                state: state, expanded: expanded)
        case .totals(let totals):
            MLBTotalsCardView11284(card: totals, color: homeColor, state: state, expanded: expanded)
        case .extraInnings(let extra):
            MLBExtraInningsCardView11284(card: extra, state: state, expanded: expanded)
        case .series(let series):
            MLBSeriesCardView11284(card: series, color: homeColor, state: state, expanded: expanded)
        }
    }
}

/// A card's kicker, title and the one line saying why it is here.
struct MLBStoryHeading11284: View {
    let kicker: String
    let title: String
    let reason: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(kicker.uppercased())
                .font(.caption.weight(.bold))
                .foregroundStyle(.secondary)
            Text(title)
                .font(.title3.weight(.bold))
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if let reason {
                Text(reason)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// The hollow pregame key the cards share.
private struct MLBPregameKey11284: View {
    let color: Color
    var label = "Pregame chance"

    var body: some View {
        HStack(spacing: 6) {
            Circle().strokeBorder(color, lineWidth: 2).frame(width: 10, height: 10)
            Text(label)
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
        .accessibilityHidden(true)
    }
}

/// A labelled figure: what it is above, the value below.
private struct MLBFigure11284: View {
    let label: String
    let value: String
    var color: Color = .primary

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.headline.monospacedDigit())
                .foregroundStyle(color)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Home runs

struct MLBHomeRunCardView11284: View {
    let card: MLBHomeRunCard11284
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false
    @Environment(\.dynamicTypeSize) private var size

    private var ticks: [Double] {
        let step = card.scaleCeiling <= 0.25 ? 0.05 : card.scaleCeiling <= 0.5 ? 0.1 : 0.25
        return Array(stride(from: 0, through: card.scaleCeiling + 1e-9, by: step))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            MLBStoryHeading11284(kicker: "Home runs · chance of at least one", title: card.headline,
                                 reason: card.reason)
            ForEach(Array(card.entries.enumerated()), id: \.element.id) { index, entry in
                if expanded {
                    Button { state.detailsRowID = entry.original.id } label: {
                        row(entry, axis: index == card.entries.count - 1)
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("Shows this prop's exact original")
                } else {
                    row(entry, axis: index == card.entries.count - 1)
                }
            }
            MLBPregameKey11284(color: .secondary)
        }
    }

    private func finalText(_ entry: MLBHomeRunCard11284.Entry) -> String {
        entry.finalCount.map { "\($0) HR · Final" } ?? "Final unavailable"
    }

    private func row(_ entry: MLBHomeRunCard11284.Entry, axis: Bool) -> some View {
        let color = PlayerPropsTeam.color(for: entry.side, home: homeColor, away: awayColor)
        let name = Text(entry.player).font(.headline).foregroundStyle(color)
        let chance = Text("\(formatProbability(entry.saved)) pregame")
            .font(.subheadline.weight(.semibold).monospacedDigit()).foregroundStyle(color)
        let final = Text(finalText(entry))
            .font(.subheadline.weight(.bold))
            .foregroundStyle(entry.finalCount == nil ? Color.secondary : Color.primary)
        return VStack(alignment: .leading, spacing: 4) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 8) { name; chance; Spacer(minLength: 8); final }
                VStack(alignment: .leading, spacing: 2) { name; chance; final }
            }
            Chart {
                RuleMark(xStart: .value("Zero", 0.0), xEnd: .value("Pregame", entry.saved),
                         y: .value("Player", 0.0))
                    .foregroundStyle(color.opacity(0.3))
                    .lineStyle(StrokeStyle(lineWidth: 3))
                PointMark(x: .value("Pregame", entry.saved), y: .value("Player", 0.0))
                    .symbol {
                        Circle().strokeBorder(color, lineWidth: 2)
                            .background(Circle().fill(Color.cardBackground))
                            .frame(width: 12, height: 12)
                    }
            }
            .chartXScale(domain: 0...card.scaleCeiling)
            .chartYScale(domain: -1...1)
            .chartYAxis(.hidden)
            .chartXAxis {
                AxisMarks(values: ticks) { value in
                    AxisGridLine().foregroundStyle(Color.secondary.opacity(0.15))
                    if axis {
                        AxisValueLabel {
                            if let v = value.as(Double.self) { Text("\(Int((v * 100).rounded()))%") }
                        }
                    }
                }
            }
            .frame(height: axis ? (size.isAccessibilitySize ? 72 : 48) : 28)
            .accessibilityHidden(true)
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(entry.player). Pregame chance of a home run \(formatProbability(entry.saved)). "
            + (entry.finalCount.map { "Official final \($0) home \($0 == 1 ? "run" : "runs")." }
                ?? "Official final unavailable."))
    }
}

// MARK: - Strikeout milestones

struct MLBMilestoneCardView11284: View {
    let card: MLBMilestoneCard11284
    let color: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false
    @Environment(\.dynamicTypeSize) private var size
    @ScaledMetric(relativeTo: .caption2) private var scaledAxisFont: CGFloat = 12
    private var axisFontSize: CGFloat { EventChartTypography.labelSize(scaled: scaledAxisFont) }

    private var slot: String { "\(card.eventID)|mlb:strikeouts" }

    private var selectedIndex: Int? {
        guard let key = state.mlbSelection(slot) else { return card.defaultIndex }
        return card.targets.firstIndex { $0.rowID == key }
    }

    private var domain: ClosedRange<Double> {
        let xs = card.targets.map { Double($0.milestone) } + (card.finalCount.map { [Double($0)] } ?? [])
        return ((xs.min() ?? 0) - 1)...((xs.max() ?? 1) + 1)
    }

    var body: some View {
        let target = selectedIndex.map { card.targets[$0] }
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(([card.stat] + [SourceLabels.label(for: card.source)].compactMap { $0 })
                        .joined(separator: " · ").uppercased())
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                    Text(card.player)
                        .font(.title3.weight(.bold))
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                }
                Spacer(minLength: 4)
                VStack(alignment: .trailing, spacing: 0) {
                    Text(card.finalCount.map(String.init) ?? "—")
                        .font(.title.weight(.bold).monospacedDigit())
                        .foregroundStyle(card.finalCount == nil ? Color.secondary : Color.primary)
                    Text(card.finalCount == nil ? "final unavailable" : "final")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(card.finalCount.map { "Official final \($0) \(card.unit)" }
                    ?? "Official final unavailable")
            }
            Text(card.reason)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Text("Chance before first pitch to reach each count")
                .font(.subheadline)
            MLBPregameKey11284(color: color, label: "Pregame")
            chart(selected: target)
            chips(selected: target)
            if let target {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        milestoneLabel(target); Spacer(minLength: 4); performance(target)
                    }
                    VStack(alignment: .leading, spacing: 4) { milestoneLabel(target); performance(target) }
                }
                .accessibilityElement(children: .combine)
                let readouts = Group {
                    MLBFigure11284(label: "Pregame",
                                   value: target.pregame.map { formatProbability($0) } ?? "Unavailable",
                                   color: target.pregame == nil ? .secondary : color)
                    MLBFigure11284(label: "Recorded in game", value: "Not captured", color: .secondary)
                }
                if size.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 12) { readouts }
                } else {
                    HStack(alignment: .top, spacing: 24) { readouts }
                }
                if expanded {
                    Button("Line details") { state.detailsRowID = target.original.id }
                        .font(.callout.weight(.semibold))
                        .frame(minHeight: 44)
                        .accessibilityHint("Shows both original sides of this line")
                }
            }
        }
    }

    private func milestoneLabel(_ target: MLBMilestoneCard11284.Target) -> some View {
        Text("\(target.milestone)+ \(card.unit)").font(.headline)
    }

    private func performance(_ target: MLBMilestoneCard11284.Target) -> some View {
        Text(MLBMilestoneResult11284.result(actual: card.finalCount.map(Double.init),
                                            milestone: Double(target.milestone)))
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func chips(selected: MLBMilestoneCard11284.Target?) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(card.targets) { target in
                    let isSelected = target.rowID == selected?.rowID
                    Button { state.selectMLB(target.rowID, slot: slot) } label: {
                        Text("\(target.milestone)+")
                            .font(.subheadline.weight(.bold).monospacedDigit())
                            .frame(minWidth: 52, minHeight: 44)
                            .background(isSelected ? color : Color.secondary.opacity(0.08),
                                        in: RoundedRectangle(cornerRadius: 8))
                            .foregroundStyle(isSelected ? Color.white : Color.primary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(target.milestone) or more \(card.unit)")
                    .accessibilityAddTraits(isSelected ? .isSelected : [])
                }
            }
        }
    }

    private func chart(selected: MLBMilestoneCard11284.Target?) -> some View {
        let milestones = card.targets.map { Double($0.milestone) }
        return Chart {
            if let final = card.finalCount {
                RuleMark(x: .value("Final", Double(final)))
                    .foregroundStyle(Color.primary)
                    .lineStyle(StrokeStyle(lineWidth: 2))
            }
            RuleMark(y: .value("Chance", 0.5))
                .foregroundStyle(Color.secondary.opacity(0.35))
                .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
            ForEach(card.targets.filter { $0.pregame != nil }) { target in
                let isSelected = target.rowID == selected?.rowID
                PointMark(x: .value("Count", Double(target.milestone)), y: .value("Chance", target.pregame ?? 0))
                    .symbol {
                        Circle()
                            .strokeBorder(isSelected ? color : Color.secondary, lineWidth: isSelected ? 2.5 : 1.5)
                            .background(Circle().fill(Color.cardBackground))
                            .frame(width: isSelected ? 14 : 9, height: isSelected ? 14 : 9)
                    }
            }
        }
        .chartXScale(domain: domain)
        .chartYScale(domain: 0...1)
        .chartYAxis {
            AxisMarks(position: .leading, values: [0, 0.5, 1]) { value in
                AxisGridLine().foregroundStyle(Color.secondary.opacity(0.15))
                AxisValueLabel {
                    if let chance = value.as(Double.self) { Text("\(Int((chance * 100).rounded()))%") }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: milestones) { value in
                NFLStatAxisLabels9483.reservedLabel(
                    value.as(Double.self).map { "\(Int($0))+" } ?? "", fontSize: axisFontSize)
            }
        }
        .chartOverlay { proxy in
            GeometryReader { geo in
                NFLStatAxisLabels9483(values: milestones, texts: card.targets.map { "\($0.milestone)+" },
                                      keep: card.targets.firstIndex { $0.rowID == selected?.rowID },
                                      fontSize: axisFontSize, proxy: proxy,
                                      plotFrame: geo[proxy.plotAreaFrame], ticks: true)
            }
        }
        .frame(height: expanded ? 220 : 150)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spokenChart)
    }

    private var spokenChart: String {
        let points = card.targets.map { target in
            "\(target.milestone) or more, \(target.pregame.map { formatProbability($0) } ?? "unavailable")"
        }
        let final = card.finalCount.map { "Official final \($0)." } ?? "Official final unavailable."
        return "\(card.player), pregame chance to reach each count: \(points.joined(separator: "; ")). \(final)"
    }
}

// MARK: - Run totals

struct MLBTotalsCardView11284: View {
    let card: MLBTotalsCard11284
    let color: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false
    @Environment(\.dynamicTypeSize) private var size
    @ScaledMetric(relativeTo: .caption2) private var scaledAxisFont: CGFloat = 12
    private var axisFontSize: CGFloat { EventChartTypography.labelSize(scaled: scaledAxisFont) }

    private var slot: String { "\(card.eventID)|mlb:totals" }

    private var selectedIndex: Int? {
        guard let key = state.mlbSelection(slot) else { return card.defaultIndex }
        return card.lines.firstIndex { $0.optionKey == key }
    }

    private var domain: ClosedRange<Double> {
        let xs = card.lines.map(\.line) + (card.actualTotal.map { [Double($0)] } ?? [])
        return ((xs.min() ?? 0) - 1)...((xs.max() ?? 1) + 1)
    }

    private var ticks: [Double] {
        let low = domain.lowerBound.rounded(.up), high = domain.upperBound.rounded(.down)
        let step: Double = high - low > 12 ? 4 : 2
        return Array(stride(from: low, through: high, by: step))
    }

    var body: some View {
        let selected = selectedIndex.map { card.lines[$0] }
        VStack(alignment: .leading, spacing: 10) {
            MLBStoryHeading11284(kicker: "Runs · final result", title: "Where the total finished",
                                 reason: card.reason)
            let figures = Group {
                MLBFigure11284(label: "Actual final", value: card.actualTotal.map { "\($0) runs" } ?? "Unavailable")
                MLBFigure11284(label: "Pregame projection", value: "Unavailable", color: .secondary)
            }
            if size.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) { figures }
            } else {
                HStack(alignment: .top, spacing: 24) { figures }
            }
            chart(selected: selected)
            HStack(spacing: 12) {
                ForEach(legend, id: \.self) { result in
                    Label(result.label, systemImage: Self.glyph(result))
                }
                Spacer(minLength: 0)
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
            .accessibilityHidden(true)
            HStack(spacing: 4) {
                Button { move(-1) } label: {
                    Image(systemName: "chevron.left").frame(width: 44, height: 44)
                }
                .disabled(selectedIndex.map { $0 == 0 } ?? true)
                .accessibilityLabel("Previous line")
                if expanded {
                    Button {
                        if let selected { state.detailsRowID = selected.original.id }
                    } label: { readout(selected) }
                    .buttonStyle(.plain)
                    .accessibilityHint("Shows this line's exact original")
                } else {
                    readout(selected).accessibilityElement(children: .combine)
                }
                Button { move(1) } label: {
                    Image(systemName: "chevron.right").frame(width: 44, height: 44)
                }
                .disabled(selectedIndex.map { $0 >= card.lines.count - 1 } ?? true)
                .accessibilityLabel("Next line")
            }
        }
    }

    private func move(_ delta: Int) {
        guard let current = selectedIndex, card.lines.indices.contains(current + delta) else { return }
        state.selectMLB(card.lines[current + delta].optionKey, slot: slot)
    }

    /// The results this card's lines carry, in a fixed order.
    private var legend: [MLBVenueResult11284] {
        [.won, .lost, .open, .pending, .notConfirmed].filter { result in
            card.lines.contains { $0.venueResult == result }
        }
    }

    private static func glyph(_ result: MLBVenueResult11284) -> String {
        switch result {
        case .won: return "checkmark"
        case .lost: return "xmark"
        case .open, .pending: return "questionmark"
        case .notConfirmed: return "minus"
        }
    }

    private func readout(_ line: MLBTotalsCard11284.Line?) -> some View {
        VStack(spacing: 2) {
            if let line {
                Text(line.label)
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                if let comparison = card.comparison(line) {
                    Text(comparison).font(.caption2).foregroundStyle(.secondary)
                }
                Text("Venue result: \(line.venueResult.label)"
                     + (line.pregame.map { " · pregame \(formatProbability($0))" } ?? "")
                     + (expanded ? " · details" : ""))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .multilineTextAlignment(.center)
        .frame(maxWidth: .infinity, minHeight: 44)
        .contentShape(Rectangle())
    }

    private func chart(selected: MLBTotalsCard11284.Line?) -> some View {
        Chart {
            if let total = card.actualTotal {
                RuleMark(x: .value("Actual", Double(total)))
                    .foregroundStyle(Color.primary)
                    .lineStyle(StrokeStyle(lineWidth: 2.5))
                    .annotation(position: .top, alignment: .center, spacing: 2) {
                        Text("\(total) actual").font(.caption2.weight(.bold))
                    }
            }
            ForEach(card.lines) { line in
                let isSelected = line.optionKey == selected?.optionKey
                PointMark(x: .value("Line", line.line), y: .value("Row", 0.0))
                    .symbol {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(line.venueResult == .won ? color : Color.secondary.opacity(0.1))
                            .overlay(RoundedRectangle(cornerRadius: 2)
                                .stroke(isSelected ? Color.primary : Color.secondary.opacity(0.35),
                                        lineWidth: isSelected ? 2 : 1))
                            .overlay(Image(systemName: Self.glyph(line.venueResult))
                                .font(.system(size: 7, weight: .bold))
                                .foregroundStyle(line.venueResult == .won ? Color.white : Color.secondary))
                            .frame(width: 10, height: 26)
                    }
            }
        }
        .chartXScale(domain: domain)
        .chartYScale(domain: -1...1)
        .chartYAxis(.hidden)
        .chartXAxis {
            AxisMarks(values: ticks) { value in
                NFLStatAxisLabels9483.reservedLabel(
                    value.as(Double.self).map(NBALadderCard9483.number) ?? "", fontSize: axisFontSize)
            }
        }
        .chartOverlay { proxy in
            GeometryReader { geo in
                NFLStatAxisLabels9483(values: ticks, texts: ticks.map(NBALadderCard9483.number), keep: nil,
                                      fontSize: axisFontSize, proxy: proxy,
                                      plotFrame: geo[proxy.plotAreaFrame], ticks: true)
            }
        }
        .frame(height: expanded ? 130 : 100)
        .padding(.top, 14)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spokenChart)
    }

    private var spokenChart: String {
        let counts = legend.map { result in
            "\(card.lines.filter { $0.venueResult == result }.count) \(result.label.lowercased())"
        }
        let actual = card.actualTotal.map { "Actual final \($0) runs. " } ?? "Actual final unavailable. "
        return actual + "\(card.lines.count) run lines: venue results \(counts.joined(separator: ", ")). "
            + "These are results, not chances."
    }
}

// MARK: - Extra innings

struct MLBExtraInningsCardView11284: View {
    let card: MLBExtraInningsCard11284
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            MLBStoryHeading11284(kicker: "Extra innings · venue market", title: "Extra innings",
                                 reason: "Pregame chance unavailable for this market")
            ForEach(card.outcomes) { outcome in
                if expanded {
                    Button { state.detailsRowID = outcome.original.id } label: { row(outcome) }
                        .buttonStyle(.plain)
                        .accessibilityHint("Shows this outcome's exact original")
                } else {
                    row(outcome)
                }
            }
        }
    }

    private func row(_ outcome: MLBExtraInningsCard11284.Outcome) -> some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text(outcome.label).font(.headline)
                if let venue = outcome.venue {
                    Text(venue).font(.caption2).foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 8)
            Text("Venue result: \(outcome.venueResult.label)")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(outcome.venueResult == .won ? Color.primary : Color.secondary)
            if expanded {
                Image(systemName: "chevron.right").font(.caption).foregroundStyle(.secondary)
            }
        }
        .frame(minHeight: 44)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

// MARK: - The series

struct MLBSeriesCardView11284: View {
    let card: MLBSeriesCard11284
    let color: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false
    @Environment(\.dynamicTypeSize) private var size

    private var questionSlot: String { "\(card.eventID)|mlb:series#question" }
    private var optionSlot: String { "\(card.eventID)|mlb:series#option" }

    /// The chosen question, else the producer's first. A question the card no
    /// longer carries selects nothing.
    private var question: MLBSeriesCard11284.Question? {
        guard let key = state.mlbSelection(questionSlot) else { return card.questions.first }
        return card.questions.first { $0.questionKey == key }
    }

    private func selectedOption(in question: MLBSeriesCard11284.Question) -> MLBSeriesCard11284.Option? {
        guard let key = state.mlbSelection(optionSlot) else { return nil }
        return question.options.first { $0.optionKey == key }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            MLBStoryHeading11284(kicker: "Series · separate from this game",
                                 title: question?.label ?? "The series", reason: card.reason)
            if card.questions.count > 1 {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(card.questions) { q in
                            let isSelected = q.questionKey == question?.questionKey
                            Button { state.selectMLB(q.questionKey, slot: questionSlot) } label: {
                                Text(q.label)
                                    .font(.caption.weight(.semibold))
                                    .lineLimit(2)
                                    .frame(maxWidth: 200, minHeight: 44)
                                    .padding(.horizontal, 10)
                                    .background(isSelected ? color.opacity(0.14) : Color.secondary.opacity(0.06),
                                                in: RoundedRectangle(cornerRadius: 8))
                            }
                            .buttonStyle(.plain)
                            .accessibilityAddTraits(isSelected ? .isSelected : [])
                        }
                    }
                }
            }
            if let question {
                let selected = selectedOption(in: question)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), alignment: .top),
                                         count: size.isAccessibilitySize ? 1 : 2), spacing: 8) {
                    ForEach(question.options) { option in
                        tile(option, selected: option.optionKey == selected?.optionKey)
                    }
                }
                if expanded, let selected {
                    Button("Outcome details") { state.detailsRowID = selected.original.id }
                        .font(.callout.weight(.semibold))
                        .frame(minHeight: 44)
                }
            }
            Text("\(card.optionCount) series \(card.optionCount == 1 ? "outcome" : "outcomes") · all in the Series section")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    private func tile(_ option: MLBSeriesCard11284.Option, selected: Bool) -> some View {
        Button { state.selectMLB(option.optionKey, slot: optionSlot) } label: {
            VStack(alignment: .leading, spacing: 6) {
                Text(option.label)
                    .font(.subheadline.weight(.bold))
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
                MLBFigure11284(label: "Chance before this game",
                               value: option.pregame.map { formatProbability($0) } ?? "Unavailable",
                               color: option.pregame == nil ? Color.secondary : color)
                Text("Venue result: \(option.result.label)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(10)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(option.result == .won ? color.opacity(0.07) : Color.secondary.opacity(0.04),
                        in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10)
                .stroke(selected ? color : Color.secondary.opacity(0.2), lineWidth: selected ? 1.5 : 1))
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(option.label). Chance before this game "
            + "\(option.pregame.map { formatProbability($0) } ?? "unavailable"). Venue result \(option.result.label).")
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

// MARK: - Exact original

/// The exact original behind a story's line, as frozen in the held card.
struct MLBOriginalDetails11284: View {
    let original: MLBOriginal11284
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text(original.title).font(.headline)
                    Text("Current probability unavailable")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                ForEach(Array(original.sections.enumerated()), id: \.offset) { _, section in
                    if !section.fields.isEmpty {
                        Section {
                            ForEach(Array(section.fields.enumerated()), id: \.offset) { _, field in
                                LabeledContent(field.label) {
                                    Text(field.value)
                                        .multilineTextAlignment(.trailing)
                                        .textSelection(.enabled)
                                }
                            }
                        } header: {
                            if let title = section.title { Text(title) }
                        }
                    }
                }
            }
            .navigationTitle("Prop details")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }
}
