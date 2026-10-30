import Charts
import SwiftUI

/// #11284 — the final MLB run-totals story as one comparison (design ref
/// `baseball-total-targets-20261023`, adoption brief
/// `mlb-total-target-adoption-20261027`): the final total as a stacked team
/// bar on a zero-based runs axis, every offered full-game line as a tick on
/// that same axis, and the selected line as a hollow diamond on a stem.
///
/// Stateless. The host resolves which line is selected (its existing
/// `NFLCardDeckState9483` selection), supplies the score tuple the page
/// already prints, and owns Details routing and return focus; this view only
/// reports intents — `onSelect(optionKey)` and `onDetails(original.id)`.
/// Every number is the card's own (`MLBTotalsCard11284`): an offered line is
/// not a projected score, the source's result is its own field, and the
/// sporting comparison is `card.comparison`, never the source's verdict.

/// What the run-totals comparison says, decided once from the card and the
/// host's inputs so the view and its tests read the same answers.
struct MLBTotalTargetsPresentation11284: Equatable {
    /// The final total as the page may draw it.
    enum Bar: Equatable {
        /// Both team counts are supplied, nonnegative, and add up — without
        /// overflow — to the card's total.
        case stacked(home: Int, away: Int)
        /// The card's total with no team split: a count is missing, negative,
        /// overflows, or does not add up to the total.
        case totalOnly(Int)
        /// No final total. Nothing is drawn — never a total read off a line
        /// or a source result.
        case none
    }

    /// One offered line in the choice strip.
    struct Choice: Equatable, Identifiable {
        let optionKey: String
        let text: String
        let isSelected: Bool
        let accessibilityLabel: String
        var id: String { optionKey }
    }

    /// A display check only: a breakdown that adds up establishes no
    /// finality and settles nothing.
    static let missingBreakdown = "Team breakdown unavailable"

    let card: MLBTotalsCard11284
    let selectedOptionKey: String?
    let homeName: String
    let awayName: String
    let homeScore: Int?
    let awayScore: Int?

    /// The card's line the host selected; nil when it selected none or the
    /// card no longer carries it. Never the card's default.
    var selected: MLBTotalsCard11284.Line? {
        guard let selectedOptionKey else { return nil }
        return card.lines.first { $0.optionKey == selectedOptionKey }
    }

    /// The card's total as a run count; a negative one is not drawn.
    var total: Int? {
        guard let total = card.actualTotal, total >= 0 else { return nil }
        return total
    }

    var bar: Bar {
        guard let total else { return .none }
        guard let home = homeScore, let away = awayScore, home >= 0, away >= 0 else { return .totalOnly(total) }
        let (sum, overflow) = home.addingReportingOverflow(away)
        return !overflow && sum == total ? .stacked(home: home, away: away) : .totalOnly(total)
    }

    // MARK: Axis

    /// The runs axis's top: the next label at or above every offered line and
    /// the total. It does not depend on the selection, so choosing a line
    /// never rescales the bar.
    var axisUpper: Double { max(axisStep, (top / axisStep).rounded(.up) * axisStep) }

    var axisStep: Double { top <= 25 ? 5 : top <= 50 ? 10 : (top / 5).rounded(.up) }

    private var top: Double { (card.lines.map(\.line) + (total.map { [Double($0)] } ?? [])).max() ?? 0 }

    var axisLabels: [Double] { Array(stride(from: 0, through: axisUpper, by: axisStep)) }

    /// Every offered line, ticked on the axis whichever is selected.
    var lineTicks: [Double] { card.lines.map(\.line) }

    /// Where the diamond stands: the selected line's own coordinate.
    var marker: Double? { selected?.line }

    // MARK: Words

    var actualValue: String { total.map(String.init) ?? "Unavailable" }
    var actualLabel: String { "Final total runs" }

    var pregameValue: String { selected?.pregame.map { formatProbability($0) } ?? "Unavailable" }
    var pregameLabel: String { selected.map { "Pregame chance · \($0.label)" } ?? "Pregame chance" }

    var heading: String { selected?.label ?? "Selected line unavailable" }

    /// The score against the selected line, from the card; nil without a
    /// selection or a total.
    var comparison: String? {
        guard total != nil, let selected else { return nil }
        return card.comparison(selected)
    }

    var sourceResult: String? { selected?.venueResult.label }

    var breakdownNote: String? {
        if case .totalOnly = bar { return Self.missingBreakdown }
        return nil
    }

    var markerKey: String? { selected.map { "Selected line · \(NBALadderCard9483.number($0.line))" } }

    /// The original Details opens, read from the built card — not the
    /// option key. Nil when no line is selected.
    var detailsID: String? { selected?.original.id }

    var choices: [Choice] {
        card.lines.map { line in
            Choice(optionKey: line.optionKey, text: NBALadderCard9483.number(line.line),
                   isSelected: line.optionKey == selected?.optionKey,
                   accessibilityLabel: "\(line.label). Source result \(line.venueResult.label).")
        }
    }

    // MARK: Spoken

    var actualAccessibilityLabel: String {
        guard let total else { return "Final total unavailable." }
        switch bar {
        case .stacked(let home, let away):
            return "Final total, \(total) runs. \(homeName) \(home), \(awayName) \(away)."
        case .totalOnly, .none:
            return "Final total, \(total) runs. \(Self.missingBreakdown)."
        }
    }

    var selectedAccessibilityLabel: String {
        guard let selected else { return "Selected line unavailable." }
        return "Selected line, \(selected.label)." + (comparison.map { " \($0)." } ?? "")
    }

    var pregameAccessibilityLabel: String {
        "Pregame chance, \(selected?.pregame.map { formatProbability($0) } ?? "unavailable")."
    }

    var sourceAccessibilityLabel: String? { sourceResult.map { "Source result, \($0)." } }
}

/// The run-totals card: the final total, the selected line's pregame chance,
/// the bar against every line, the source's result and the choice strip.
struct MLBTotalTargetsCardView11284: View {
    let card: MLBTotalsCard11284
    /// Resolved by the host; nil or withdrawn selects nothing.
    let selectedOptionKey: String?
    let homeName: String
    let awayName: String
    let homeColor: Color
    let awayColor: Color
    /// The page's printed final score; nil wherever it prints none.
    let homeScore: Int?
    let awayScore: Int?
    var expanded = false
    let onSelect: (String) -> Void
    let onDetails: (String) -> Void
    @Environment(\.dynamicTypeSize) private var size
    @ScaledMetric(relativeTo: .caption2) private var scaledAxisFont: CGFloat = 12
    private var axisFontSize: CGFloat { EventChartTypography.labelSize(scaled: scaledAxisFont) }

    var presentation: MLBTotalTargetsPresentation11284 {
        MLBTotalTargetsPresentation11284(card: card, selectedOptionKey: selectedOptionKey,
                                         homeName: homeName, awayName: awayName,
                                         homeScore: homeScore, awayScore: awayScore)
    }

    /// A choice's intent: the line's own option key.
    func select(_ choice: MLBTotalTargetsPresentation11284.Choice) {
        onSelect(choice.optionKey)
    }

    /// Details' intent: the selected line's original, or nothing.
    func requestDetails() {
        if let id = presentation.detailsID { onDetails(id) }
    }

    var body: some View {
        let p = presentation
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Runs · \(card.lines.count) full-game lines".uppercased())
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)
                Text("Where the total finished")
                    .font(.title3.weight(.bold))
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
            }
            if size.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 12) { figures(p) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 24) { figures(p) }
                    VStack(alignment: .leading, spacing: 12) { figures(p) }
                }
            }
            if size.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 6) { keys(p) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 14) { keys(p) }
                    VStack(alignment: .leading, spacing: 6) { keys(p) }
                }
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(p.heading)
                    .font(.headline)
                    .foregroundStyle(p.selected == nil ? Color.secondary : Color.primary)
                if let comparison = p.comparison {
                    Text(comparison)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(p.selectedAccessibilityLabel)
            chart(p)
            if let result = p.sourceResult, let spoken = p.sourceAccessibilityLabel {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text("Source result").foregroundStyle(.secondary)
                    Text(result).fontWeight(.semibold)
                }
                .font(.subheadline)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(spoken)
            }
            Text("Offered run lines")
                .font(.subheadline.weight(.semibold))
            strip(p)
            if expanded, p.detailsID != nil, let selected = p.selected {
                Button("Details") { requestDetails() }
                    .font(.callout.weight(.semibold))
                    .frame(minHeight: 44)
                    .accessibilityLabel("Details, \(selected.label)")
                    .accessibilityHint("Shows this line's exact original")
            }
        }
    }

    // MARK: Figures

    @ViewBuilder
    private func figures(_ p: MLBTotalTargetsPresentation11284) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(p.actualValue)
                .font(p.total == nil ? Font.title2.weight(.semibold) : Font.largeTitle.weight(.bold).monospacedDigit())
                .foregroundStyle(p.total == nil ? Color.secondary : Color.primary)
            Text(p.actualLabel)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(p.actualAccessibilityLabel)
        VStack(alignment: .leading, spacing: 2) {
            Text(p.pregameValue)
                .font(p.selected?.pregame == nil ? Font.title2.weight(.semibold)
                      : Font.largeTitle.weight(.bold).monospacedDigit())
                .foregroundStyle(p.selected?.pregame == nil ? Color.secondary : Color.primary)
            Text(p.pregameLabel)
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(p.pregameAccessibilityLabel)
    }

    // MARK: Keys

    @ViewBuilder
    private func keys(_ p: MLBTotalTargetsPresentation11284) -> some View {
        switch p.bar {
        case .stacked(let home, let away):
            swatch(homeColor, "\(homeName) \(home)")
            swatch(awayColor, "\(awayName) \(away)")
        case .totalOnly:
            if let note = p.breakdownNote {
                swatch(Color.primary.opacity(0.45), note)
            }
        case .none:
            EmptyView()
        }
        if let key = p.markerKey {
            HStack(spacing: 6) {
                diamond(side: 8)
                Text(key)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityHidden(true)
        }
    }

    private func swatch(_ color: Color, _ text: String) -> some View {
        HStack(spacing: 6) {
            RoundedRectangle(cornerRadius: 2).fill(color).frame(width: 10, height: 10)
            Text(text).foregroundStyle(.primary)
        }
        .font(.caption)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityHidden(true)
    }

    private func diamond(side: CGFloat) -> some View {
        Rectangle()
            .fill(Color.cardBackground)
            .overlay(Rectangle().stroke(Color.primary, lineWidth: 2))
            .frame(width: side, height: side)
            .rotationEffect(.degrees(45))
    }

    // MARK: Chart

    /// Rows on the plot's hidden y scale: the line ticks under the bar, the
    /// bar, and the diamond above it on its stem.
    private enum Row {
        static let tickLow = 0.2, tickHigh = 0.6
        static let barLow = 0.7, barHigh = 1.5
        static let diamond = 2.3
    }

    private struct Segment: Identifiable {
        let id: String
        let from: Double
        let to: Double
        let color: Color
    }

    /// The bar's drawn pieces; a zero count draws nothing, and no total
    /// draws no bar at all.
    private func segments(_ p: MLBTotalTargetsPresentation11284) -> [Segment] {
        switch p.bar {
        case .stacked(let home, let away):
            return [Segment(id: "home", from: 0, to: Double(home), color: homeColor),
                    Segment(id: "away", from: Double(home), to: Double(home + away), color: awayColor)]
                .filter { $0.to > $0.from }
        case .totalOnly(let total):
            return total > 0 ? [Segment(id: "total", from: 0, to: Double(total), color: Color.primary.opacity(0.45))] : []
        case .none:
            return []
        }
    }

    private func chart(_ p: MLBTotalTargetsPresentation11284) -> some View {
        Chart {
            RectangleMark(xStart: .value("Runs", 0.0), xEnd: .value("Runs", p.axisUpper),
                          yStart: .value("Row", Row.barLow), yEnd: .value("Row", Row.barHigh))
                .foregroundStyle(Color.secondary.opacity(0.15))
            ForEach(segments(p)) { segment in
                RectangleMark(xStart: .value("Runs", segment.from), xEnd: .value("Runs", segment.to),
                              yStart: .value("Row", Row.barLow), yEnd: .value("Row", Row.barHigh))
                    .foregroundStyle(segment.color)
            }
            ForEach(p.lineTicks, id: \.self) { line in
                RuleMark(x: .value("Line", line),
                         yStart: .value("Row", Row.tickLow), yEnd: .value("Row", Row.tickHigh))
                    .foregroundStyle(Color.secondary)
                    .lineStyle(StrokeStyle(lineWidth: 1))
            }
            if let marker = p.marker {
                RuleMark(x: .value("Selected", marker),
                         yStart: .value("Row", Row.tickLow), yEnd: .value("Row", Row.diamond))
                    .foregroundStyle(Color.primary)
                    .lineStyle(StrokeStyle(lineWidth: 1.5))
                PointMark(x: .value("Selected", marker), y: .value("Row", Row.diamond))
                    .symbol { diamond(side: 10) }
            }
        }
        .chartXScale(domain: 0...p.axisUpper)
        .chartYScale(domain: 0...2.8)
        .chartYAxis(.hidden)
        .chartXAxis {
            AxisMarks(values: p.axisLabels) { value in
                AxisGridLine().foregroundStyle(Color.secondary.opacity(0.12))
                AxisValueLabel {
                    if let runs = value.as(Double.self) {
                        Text(NBALadderCard9483.number(runs)).font(.system(size: axisFontSize).monospacedDigit())
                    }
                }
            }
        }
        .frame(height: expanded ? 132 : 108)
        .accessibilityHidden(true)
    }

    // MARK: Choice strip

    private func strip(_ p: MLBTotalTargetsPresentation11284) -> some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(p.choices) { choice in
                        Button { select(choice) } label: {
                            Text(choice.text)
                                .font(.body.weight(choice.isSelected ? .bold : .regular).monospacedDigit())
                                .padding(.horizontal, 8)
                                .frame(minWidth: 52, minHeight: 44)
                                .background(choice.isSelected ? Color.secondary.opacity(0.15) : Color.cardBackground,
                                            in: RoundedRectangle(cornerRadius: 9))
                                .overlay(RoundedRectangle(cornerRadius: 9)
                                    .stroke(choice.isSelected ? Color.primary : Color.secondary.opacity(0.3),
                                            lineWidth: choice.isSelected ? 2 : 1))
                                .foregroundStyle(Color.primary)
                        }
                        .buttonStyle(.plain)
                        .id(choice.optionKey)
                        .accessibilityLabel(choice.accessibilityLabel)
                        .accessibilityAddTraits(choice.isSelected ? .isSelected : [])
                    }
                }
                .padding(3)
            }
            .onAppear {
                if let key = p.selected?.optionKey { proxy.scrollTo(key, anchor: .center) }
            }
            .onChange(of: p.selected?.optionKey) { _, key in
                if let key { proxy.scrollTo(key, anchor: .center) }
            }
        }
    }
}
