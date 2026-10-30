import Charts
import SwiftUI

/// #11284 — the strikeout card's comparison (design ref #10868,
/// `native-baseball-paired-home-runs/strikeout-first`): one pitcher, a strip
/// of strikeout targets, and for the chosen target its pregame chance beside
/// the official final count at the same size, above the full milestone chart.
///
/// Stateless, and only a drawing of `MLBMilestoneCard11284`. The card's builder
/// owns the ladder, its order, every target's admitted milestone, the saved
/// pregame chances and the typed official final; the host owns which target
/// is selected (its default included), update holds, navigation and focus.
/// This view never picks a default, never reconstructs a missing number from
/// the original's sections, and supplies no current probability: none is
/// delivered for a final game.
///
/// A nil `selectedRowID` stays unselected. An ID the card no longer carries is
/// "unavailable in this update" — never another target, never a withdrawal.
///
/// The chart's count axis is fixed by the card alone (zero, every milestone
/// and the final), so choosing a target never moves it. The final is a rule on
/// that count axis; it never changes a chance.
///
/// "Against this target" is the pitcher's performance against the count
/// (`MLBMilestoneResult11284`), not the venue's grade of the market.
struct MLBStrikeoutComparison11284: View {
    let card: MLBMilestoneCard11284
    /// Resolved by the host; nil is unselected.
    let selectedRowID: String?
    let color: Color
    let expanded: Bool
    /// Receives `target.rowID` unchanged.
    let onSelect: (String) -> Void
    /// Receives the selected `target.original.id` unchanged. Nil draws no
    /// details button.
    var onDetails: ((String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var size
    /// Both figures share one scaled size, so neither reads as the footnote
    /// of the other.
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = Self.figurePointSize
    /// The narrowest a column may be before the pair stacks.
    @ScaledMetric(relativeTo: .body) private var columnMinimum: CGFloat = 120
    @ScaledMetric(relativeTo: .caption2) private var scaledAxisFont: CGFloat = 12
    private var axisFontSize: CGFloat { EventChartTypography.labelSize(scaled: scaledAxisFont) }

    /// The figures' size at the default text size (Design: at least 28pt).
    static let figurePointSize: CGFloat = 28
    /// No target or details control is a smaller target than this.
    static let minimumControlHeight: CGFloat = 44
    static let stripLabel = "Pregame chance to reach each count"
    static let pregameLabel = "Pregame chance"
    static let finalLabel = "Official final"
    static let againstLabel = "Against this target"
    static let unavailableText = "Unavailable"
    static let detailsTitle = "Line details"
    static let detailsHintText = "Shows both original sides of this line"
    static let selectHintText = "Shows this target's pregame chance"

    var comparison: Comparison { Self.comparison(card, selectedRowID: selectedRowID) }
    var detailsAvailable: Bool { onDetails != nil && comparison.detailsID != nil }

    func select(_ choice: Choice) {
        onSelect(choice.id)
    }

    /// Hands back the selected target's original ID; with no selected target
    /// there is nothing to show and nothing is sent.
    func details() {
        guard let id = comparison.detailsID else { return }
        onDetails?(id)
    }

    var body: some View {
        let comparison = self.comparison
        VStack(alignment: .leading, spacing: 12) {
            heading
            strip
            figures(comparison)
            key
            chart
            if detailsAvailable {
                Button(Self.detailsTitle) { details() }
                    .font(.callout.weight(.semibold))
                    .frame(minHeight: Self.minimumControlHeight)
                    .accessibilityHint(Self.detailsHintText)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Heading and targets

    private var heading: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(Self.kicker(card).uppercased())
                .font(.caption.weight(.bold))
                .foregroundStyle(.secondary)
            // The whole name, wrapping between words; never truncated.
            Text(card.player)
                .font(.title3.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            Text(card.reason)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// Every target, in the card's order, in one horizontal strip.
    private var strip: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(Self.stripLabel)
                .font(.subheadline)
                .fixedSize(horizontal: false, vertical: true)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(Self.choices(card, selectedRowID: selectedRowID)) { choice in
                        Button { select(choice) } label: {
                            Text(choice.label)
                                .font(.subheadline.weight(.bold).monospacedDigit())
                                .padding(.horizontal, 10)
                                .frame(minWidth: 52, minHeight: Self.minimumControlHeight)
                                .background(choice.isSelected ? color : Color.secondary.opacity(0.08),
                                            in: RoundedRectangle(cornerRadius: 8))
                                .foregroundStyle(choice.isSelected ? Color.white : Color.primary)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(choice.spoken)
                        .accessibilityHint(Self.selectHintText)
                        .accessibilityAddTraits(choice.isSelected ? .isSelected : [])
                    }
                }
            }
        }
    }

    // MARK: The comparison

    private func figures(_ comparison: Comparison) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(comparison.targetHeading)
                .font(.headline)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityLabel(comparison.targetSpoken)
            if Self.stacks(at: size) {
                stacked(comparison)
            } else {
                // Side by side in equal columns; stacked when the width runs
                // out, so numbers keep their size instead of shrinking.
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 16) {
                        pregameColumn(comparison)
                            .frame(minWidth: columnMinimum, maxWidth: .infinity, alignment: .leading)
                        finalColumn(comparison)
                            .frame(minWidth: columnMinimum, maxWidth: .infinity, alignment: .leading)
                    }
                    stacked(comparison)
                }
            }
            if let against = comparison.againstText {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .firstTextBaseline, spacing: 6) { againstParts(against) }
                    VStack(alignment: .leading, spacing: 2) { againstParts(against) }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(comparison.againstSpoken ?? "")
            }
        }
    }

    private func stacked(_ comparison: Comparison) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            pregameColumn(comparison)
            finalColumn(comparison)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func pregameColumn(_ comparison: Comparison) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                Self.hollowDot(color: color, side: 8)
                Text(Self.pregameLabel)
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)
            if let pregame = comparison.pregameText {
                Text(pregame)
                    .font(.system(size: figureSize, weight: .bold).monospacedDigit())
                    .foregroundStyle(color)
                    .lineLimit(1)
                    .fixedSize()
            } else {
                unavailable
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(comparison.pregameSpoken)
    }

    private func finalColumn(_ comparison: Comparison) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                Self.finalBar(side: 8)
                Text(Self.finalLabel)
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)
            if let final = comparison.finalText {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(final)
                        .font(.system(size: figureSize, weight: .bold).monospacedDigit())
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                        .fixedSize()
                    Text(card.unit)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                unavailable
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(comparison.finalSpoken)
    }

    /// Legible words, not a figure-sized word posing as a number.
    private var unavailable: some View {
        Text(Self.unavailableText)
            .font(.headline)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder private func againstParts(_ against: String) -> some View {
        Text(Self.againstLabel)
            .font(.subheadline)
            .foregroundStyle(.secondary)
        Text(against)
            .font(.subheadline.weight(.semibold))
            .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: The chart

    /// What the two marks are, said beside the plot (VoiceOver hears the
    /// chart's own summary instead).
    private var key: some View {
        HStack(spacing: 14) {
            HStack(spacing: 6) {
                Self.hollowDot(color: color, side: 10)
                Text(Self.pregameLabel)
            }
            if Self.shownFinal(card) != nil {
                HStack(spacing: 6) {
                    Self.finalBar(side: 10)
                    Text(Self.finalLabel)
                }
            }
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
        .accessibilityHidden(true)
    }

    private var chart: some View {
        let domain = Self.domain(card)
        let axis = Self.axisLabels(card, selectedRowID: selectedRowID)
        return Chart {
            if let final = Self.shownFinal(card) {
                RuleMark(x: .value("Final", Double(final)))
                    .foregroundStyle(Color.primary)
                    .lineStyle(StrokeStyle(lineWidth: 2.5))
                    .annotation(position: .top, alignment: .center, spacing: 2,
                                overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        Text(Self.finalRuleLabel(final))
                            .font(.system(size: axisFontSize, weight: .bold))
                    }
            }
            RuleMark(y: .value("Chance", 0.5))
                .foregroundStyle(Color.secondary.opacity(0.35))
                .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
            ForEach(Self.points(card, selectedRowID: selectedRowID)) { point in
                PointMark(x: .value("Count", point.count), y: .value("Chance", point.chance))
                    .symbol {
                        Self.hollowDot(color: color, side: point.isSelected ? 15 : 9,
                                       lineWidth: point.isSelected ? 2.5 : 1.5)
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
            AxisMarks(values: axis.values) { value in
                NFLStatAxisLabels9483.reservedLabel(
                    value.as(Double.self).flatMap { v in axis.values.firstIndex(of: v).map { axis.texts[$0] } } ?? "",
                    fontSize: axisFontSize)
            }
        }
        .chartOverlay { proxy in
            GeometryReader { geo in
                NFLStatAxisLabels9483(values: axis.values, texts: axis.texts, keep: axis.keep,
                                      fontSize: axisFontSize, proxy: proxy,
                                      plotFrame: geo[proxy.plotAreaFrame], ticks: true)
            }
        }
        .frame(height: Self.chartHeight(expanded: expanded, axisFontSize: axisFontSize,
                                        hasFinal: Self.shownFinal(card) != nil))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Self.chartSpoken(card, selectedRowID: selectedRowID))
    }

    static func hollowDot(color: Color, side: CGFloat, lineWidth: CGFloat = 2) -> some View {
        Circle()
            .strokeBorder(color, lineWidth: lineWidth)
            .background(Circle().fill(Color.cardBackground))
            .frame(width: side, height: side)
    }

    static func finalBar(side: CGFloat) -> some View {
        Rectangle()
            .fill(Color.primary)
            .frame(width: 2.5, height: side + 2)
            .frame(width: side, height: side + 2)
    }

    static func stacks(at size: DynamicTypeSize) -> Bool { size.isAccessibilitySize }
}

// MARK: - What the card says

extension MLBStrikeoutComparison11284 {
    /// One target control: "7+" and whether it is the host's selection.
    struct Choice: Equatable, Identifiable {
        /// `target.rowID`, sent to `onSelect` unchanged.
        let id: String
        let label: String
        let spoken: String
        let isSelected: Bool
    }

    /// The selected target as words, decided once from the card and the
    /// host's selection.
    struct Comparison: Equatable {
        let targetHeading: String
        let targetSpoken: String
        /// The formatted pregame chance, or nil when unavailable or unselected.
        let pregameText: String?
        let pregameSpoken: String
        /// The official final count ("2"), or nil when unavailable. Never "0"
        /// for a missing count; a typed zero is "0".
        let finalText: String?
        let finalSpoken: String
        /// Performance against the selected count, or nil without both a
        /// selected target and an official final.
        let againstText: String?
        let againstSpoken: String?
        /// `target.original.id`, or nil with no selected target.
        let detailsID: String?
    }

    /// A drawn pregame point. A target with no chance has none.
    struct Point: Equatable, Identifiable {
        let id: String
        let count: Double
        let chance: Double
        let isSelected: Bool
    }

    /// The host's selection, read without fallback: nil is unselected, and an
    /// ID the card does not carry is unavailable.
    enum Selection: Equatable {
        case unselected
        case unavailable
        case target(MLBMilestoneCard11284.Target)
    }

    static func selection(_ card: MLBMilestoneCard11284, selectedRowID: String?) -> Selection {
        guard let selectedRowID else { return .unselected }
        return card.targets.first { $0.rowID == selectedRowID }.map(Selection.target) ?? .unavailable
    }

    /// "STRIKEOUTS · POLYMARKET": the venue's stat words and the source label.
    static func kicker(_ card: MLBMilestoneCard11284) -> String {
        ([card.stat] + [SourceLabels.label(for: card.source)].compactMap { $0 }).joined(separator: " · ")
    }

    static func choices(_ card: MLBMilestoneCard11284, selectedRowID: String?) -> [Choice] {
        card.targets.map { target in
            Choice(id: target.rowID, label: "\(target.milestone)+",
                   spoken: "\(target.milestone) or more \(card.unit)",
                   isSelected: target.rowID == selectedRowID)
        }
    }

    /// The official final the card types, when it is a count (the
    /// performance helper's own bounds: a negative count is unavailable).
    static func shownFinal(_ card: MLBMilestoneCard11284) -> Int? {
        card.finalCount.flatMap { $0 >= 0 ? $0 : nil }
    }

    static func comparison(_ card: MLBMilestoneCard11284, selectedRowID: String?) -> Comparison {
        let final = shownFinal(card)
        let finalSpoken = final.map { "\(finalLabel), \($0) \(card.unit)" } ?? "\(finalLabel) unavailable"
        switch selection(card, selectedRowID: selectedRowID) {
        case .target(let target):
            let pregame = target.pregame.map { formatProbability($0) }
            let against = final.map {
                MLBMilestoneResult11284.result(actual: Double($0), milestone: Double(target.milestone))
            }
            return Comparison(
                targetHeading: "\(target.milestone)+ \(card.unit)",
                targetSpoken: "Selected target, \(target.milestone) or more \(card.unit)",
                pregameText: pregame,
                pregameSpoken: pregame.map { "\(pregameLabel), \($0)" } ?? "\(pregameLabel) unavailable",
                finalText: final.map(String.init), finalSpoken: finalSpoken,
                againstText: against, againstSpoken: against.map { "\(againstLabel), \($0)" },
                detailsID: target.original.id)
        case .unselected:
            return Comparison(
                targetHeading: "Choose a target", targetSpoken: "No target selected",
                pregameText: nil, pregameSpoken: "\(pregameLabel) unavailable, no target selected",
                finalText: final.map(String.init), finalSpoken: finalSpoken,
                againstText: nil, againstSpoken: nil, detailsID: nil)
        case .unavailable:
            return Comparison(
                targetHeading: "This target is unavailable in this update",
                targetSpoken: "Selected target unavailable in this update",
                pregameText: nil, pregameSpoken: "\(pregameLabel) unavailable",
                finalText: final.map(String.init), finalSpoken: finalSpoken,
                againstText: nil, againstSpoken: nil, detailsID: nil)
        }
    }

    /// Zero through the largest of every milestone and the final, plus one
    /// count of room on the right. The selection never enters it.
    static func domain(_ card: MLBMilestoneCard11284) -> ClosedRange<Double> {
        let counts = card.targets.map { Double($0.milestone) } + (shownFinal(card).map { [Double($0)] } ?? [])
        return 0...(max(0, counts.max() ?? 0) + 1)
    }

    /// Hollow points at each target's admitted milestone, in the card's
    /// order; a missing chance draws nothing, and nothing is interpolated.
    static func points(_ card: MLBMilestoneCard11284, selectedRowID: String?) -> [Point] {
        card.targets.compactMap { target in
            target.pregame.map {
                Point(id: target.rowID, count: Double(target.milestone), chance: $0,
                      isSelected: target.rowID == selectedRowID)
            }
        }
    }

    /// Zero, then a tick for every target, priced or not, so each stands where
    /// it is. The selected target's label is kept first when the row is full.
    static func axisLabels(_ card: MLBMilestoneCard11284,
                           selectedRowID: String?) -> (values: [Double], texts: [String], keep: Int?) {
        let zero: [(Double, String)] = card.targets.contains { $0.milestone == 0 } ? [] : [(0, "0")]
        let pairs = zero + card.targets.map { (Double($0.milestone), "\($0.milestone)+") }
        let offset = zero.count
        let keep = card.targets.firstIndex { $0.rowID == selectedRowID }.map { $0 + offset }
        return (pairs.map(\.0), pairs.map(\.1), keep)
    }

    static func finalRuleLabel(_ final: Int) -> String { "Final \(final)" }

    /// At least 150pt compact and 220pt expanded, plus a row for the final's
    /// label, which grows with the axis type.
    static func chartHeight(expanded: Bool, axisFontSize: CGFloat, hasFinal: Bool) -> CGFloat {
        (expanded ? 220 : 150) + (hasFinal ? axisFontSize + 6 : 0)
    }

    /// Every plotted value in words, so none depends on colour or sight.
    static func chartSpoken(_ card: MLBMilestoneCard11284, selectedRowID: String?) -> String {
        let points = card.targets.map { target in
            "\(target.milestone) or more, \(target.pregame.map { formatProbability($0) } ?? "unavailable")"
                + (target.rowID == selectedRowID ? ", selected" : "")
        }
        let final = shownFinal(card).map { "\(finalLabel), \($0) \(card.unit)." } ?? "\(finalLabel) unavailable."
        return "\(card.player), pregame chance to reach each count: \(points.joined(separator: "; ")). \(final)"
    }
}
