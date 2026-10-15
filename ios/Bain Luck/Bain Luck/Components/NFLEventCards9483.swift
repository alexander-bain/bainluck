import Charts
import Combine
import SwiftUI

/// #9483 — the NFL page's visual cards (design ref #10868 native v107):
/// one renderer per family, drawn compact in the deck under the chart and
/// full size in the reader (`NFLCardReader9483`). Compact and full size read
/// the same card value and the same selection, so opening a card never
/// changes what it says (v110).

// MARK: - Selection shared by compact and full size

/// The reader's state, owned by the page so it survives the deck → reader →
/// deck round trip and a size-class rebuild: which card is open, and which
/// original row each milestone card has selected.
@MainActor
final class NFLCardDeckState9483: ObservableObject {
    /// The card open full size, or nil.
    @Published var openCardID: String?
    /// The card the reader returns focus to when it closes.
    @Published private(set) var returnCardID: String?
    /// Selected original row per milestone card. A row that is no longer
    /// served selects nothing — never a neighbouring line (v110).
    @Published private var selectedRow: [String: String] = [:]
    /// The original row whose exact details are showing, or nil.
    @Published var detailsRowID: String?

    func open(_ cardID: String) {
        returnCardID = cardID
        openCardID = cardID
    }

    func close() {
        detailsRowID = nil
        openCardID = nil
    }

    func selectedIndex(in card: NFLMilestoneCard9483) -> Int? {
        guard let row = selectedRow[card.id] else { return card.defaultRung }
        return card.rungs.firstIndex { $0.rowID == row }
    }

    func move(in card: NFLMilestoneCard9483, by delta: Int) {
        guard let current = selectedIndex(in: card), card.rungs.indices.contains(current + delta) else { return }
        selectedRow[card.id] = card.rungs[current + delta].rowID
    }
}

// MARK: - Projected finish

struct NFLFinishCardView9483: View {
    let card: NFLFinishCard9483
    let awayName: String
    let homeName: String
    let awayColor: Color
    let homeColor: Color
    var expanded = false
    @ScaledMetric(relativeTo: .caption2) private var scaledAxisFont: CGFloat = 12

    private var later: NFLFinishCard9483.Pair? { card.final ?? card.projectedNow }
    private var laterLabel: String? {
        card.final != nil ? "Final" : card.projectedNow != nil ? "Projected now" : nil
    }
    private var domainMax: Double {
        let values = [card.pregame.away, card.pregame.home, later?.away ?? 0, later?.home ?? 0]
        return max(14, ((values.max() ?? 0) / 7).rounded(.up) * 7 + 3.5)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(card.kicker.uppercased())
                .font(.caption.weight(.bold))
                .foregroundStyle(homeColor)
            Text(card.headline(awayName: awayName, homeName: homeName))
                .font(.title3.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            Chart {
                ForEach([false, true], id: \.self) { isHome in
                    let name = isHome ? homeName : awayName
                    let color = isHome ? homeColor : awayColor
                    PointMark(x: .value("Points", isHome ? card.pregame.home : card.pregame.away),
                              y: .value("Team", name))
                        .symbol { Rectangle().stroke(color, lineWidth: 2).frame(width: 9, height: 9) }
                    if let later {
                        PointMark(x: .value("Points", isHome ? later.home : later.away),
                                  y: .value("Team", name))
                            .symbol(card.final != nil ? .cross : .square)
                            .foregroundStyle(color)
                    }
                }
            }
            .chartXScale(domain: 0...domainMax)
            .chartYScale(domain: [awayName, homeName])
            .chartXAxis {
                AxisMarks(values: pointTicks) { value in
                    NFLStatAxisLabels9483.reservedLabel(value.as(Double.self).map(Self.points) ?? "",
                                                        fontSize: axisFontSize)
                }
            }
            .chartOverlay { proxy in
                GeometryReader { geo in
                    NFLStatAxisLabels9483(values: pointTicks, texts: pointTicks.map(Self.points),
                                          keep: nil, fontSize: axisFontSize,
                                          proxy: proxy, plotFrame: geo[proxy.plotAreaFrame])
                }
            }
            .frame(height: expanded ? 220 : 120)
            .accessibilityHidden(true)
            ForEach([false, true], id: \.self) { isHome in
                HStack(alignment: .firstTextBaseline) {
                    Text(isHome ? homeName : awayName)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(isHome ? homeColor : awayColor)
                    Spacer(minLength: 8)
                    number(isHome ? card.pregame.home : card.pregame.away, label: "pregame projection")
                    if let later, let laterLabel {
                        number(isHome ? later.home : later.away, label: laterLabel.lowercased())
                            .frame(minWidth: 72, alignment: .trailing)
                    }
                }
            }
            Text(card.final != nil ? "Points · outline = pregame · cross = final"
                 : card.projectedNow != nil ? "Points · outline = pregame · filled = projected now"
                 : "Projected points")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityText)
    }

    private var axisFontSize: CGFloat { EventChartTypography.labelSize(scaled: scaledAxisFont) }
    /// One tick per touchdown (7 points) across the axis.
    private var pointTicks: [Double] { Array(stride(from: 0, through: domainMax, by: 7)) }

    private func number(_ value: Double, label: String) -> some View {
        VStack(alignment: .trailing, spacing: 0) {
            Text(Self.points(value))
                .font(.headline.monospacedDigit())
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    /// A projection keeps its half point; a final score is whole.
    static func points(_ value: Double) -> String {
        value.rounded() == value ? String(Int(value)) : String(format: "%.1f", value)
    }

    private var accessibilityText: String {
        var parts = [card.kicker, card.headline(awayName: awayName, homeName: homeName),
                     "Pregame projection \(awayName) \(Self.points(card.pregame.away)), \(homeName) \(Self.points(card.pregame.home))"]
        if let later, let laterLabel {
            parts.append("\(laterLabel) \(awayName) \(Self.points(later.away)), \(homeName) \(Self.points(later.home))")
        }
        return parts.joined(separator: ". ")
    }
}

// MARK: - Player milestones

struct NFLMilestoneCardView9483: View {
    let card: NFLMilestoneCard9483
    let color: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false
    @ScaledMetric(relativeTo: .caption2) private var scaledAxisFont: CGFloat = 12
    private var axisFontSize: CGFloat { EventChartTypography.labelSize(scaled: scaledAxisFont) }

    var body: some View {
        let selected = state.selectedIndex(in: card)
        let rung = selected.map { card.rungs[$0] }
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(card.stat)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    // #11061 — a hyphenated name needs a third line at
                    // accessibility sizes ("Jaxon / Smith- / Njigba").
                    Text(card.player)
                        .font(.title3.weight(.bold))
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 4)
                if let actual = card.actual {
                    VStack(alignment: .trailing, spacing: 0) {
                        Text(NFLFinishCardView9483.points(actual))
                            .font(.title.weight(.bold).monospacedDigit())
                            .foregroundStyle(color)
                        Text("final")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            Text(card.caption)
                .font(.caption)
                .foregroundStyle(.secondary)
            if let profile = card.profile {
                chart(profile, selected: rung)
            }
            if card.profile == nil {
                // Every price on the card has stopped being observed: the
                // lines stay, the shape does not.
                Text("No recent prices")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: expanded ? 120 : 60)
            }
            HStack(spacing: 4) {
                Button { state.move(in: card, by: -1) } label: {
                    Image(systemName: "chevron.left").frame(width: 44, height: 44)
                }
                .disabled(selected.map { $0 == 0 } ?? true)
                .accessibilityLabel("Previous line")
                if expanded {
                    // Details sheet lives on the full-size reader only; the
                    // compact card opens through its "Open full size" control.
                    Button {
                        if let rung { state.detailsRowID = rung.rowID }
                    } label: {
                        readout(rung)
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("Shows this line's exact quote")
                } else {
                    readout(rung)
                        .accessibilityElement(children: .combine)
                }
                Button { state.move(in: card, by: 1) } label: {
                    Image(systemName: "chevron.right").frame(width: 44, height: 44)
                }
                .disabled(selected.map { $0 >= card.rungs.count - 1 } ?? true)
                .accessibilityLabel("Next line")
            }
        }
    }

    private func readout(_ rung: NFLMilestoneCard9483.Rung?) -> some View {
        VStack(spacing: 2) {
            if let rung {
                Text(rung.chance.map {
                    "\(PlayerPropsFamily.targetLabel(rung.threshold)) · \(formatProbability($0))"
                } ?? "\(PlayerPropsFamily.targetLabel(rung.threshold)) · \(noChance)")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(rung.chance == nil ? Color.secondary : color)
                Text(verdict(rung))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .multilineTextAlignment(.center)
        .frame(maxWidth: .infinity, minHeight: 44)
        .contentShape(Rectangle())
    }

    /// What a line with no number says, by basis: a quote that stopped being
    /// observed, or a line the server served no pregame mark for.
    private var noChance: String {
        card.basis == .pregamePrice ? "No recent price" : "No pregame chance"
    }

    private func verdict(_ rung: NFLMilestoneCard9483.Rung) -> String {
        let more = expanded ? " · details" : ""
        switch rung.hit {
        case true?: return "Reached" + more
        case false?: return "Not reached" + more
        case nil:
            if rung.chance == nil { return !expanded ? "" : card.basis == .pregamePrice ? "Last quote in details" : "Details" }
            return (card.basis == .pregamePrice ? "Pregame chance" : "Before kickoff") + more
        }
    }

    private func chart(_ profile: PlayerMilestoneProfile.Profile, selected: NFLMilestoneCard9483.Rung?) -> some View {
        let domain = NFLMilestoneCard9483.statDomain(profile.domain, actual: card.actual)
        return Chart {
            // The final is a rule on the stat axis. Its value is printed large
            // in the card's header, so the rule carries no second label to clip.
            if let actual = card.actual {
                RectangleMark(xStart: .value("Start", domain.lowerBound), xEnd: .value("Final", actual),
                              yStart: .value("Chance", 0), yEnd: .value("Chance", 1))
                    .foregroundStyle(color.opacity(0.07))
                RuleMark(x: .value("Final", actual))
                    .foregroundStyle(color)
                    .lineStyle(StrokeStyle(lineWidth: 2))
            }
            RuleMark(y: .value("Chance", 0.5))
                .foregroundStyle(Color.secondary.opacity(0.35))
                .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
            ForEach(card.rungs.filter { $0.chance != nil }) { rung in
                let isSelected = rung.rowID == selected?.rowID
                let chance = rung.chance ?? 0
                RuleMark(x: .value("Line", rung.threshold),
                         yStart: .value("Chance", 0), yEnd: .value("Chance", chance))
                    .foregroundStyle(color.opacity(isSelected ? 0.9 : 0.3))
                    .lineStyle(StrokeStyle(lineWidth: isSelected ? 2 : 1.5))
                PointMark(x: .value("Line", rung.threshold), y: .value("Chance", chance))
                    .symbol {
                        Circle()
                            .strokeBorder(isSelected ? color : Color.secondary, lineWidth: isSelected ? 2.5 : 1.5)
                            .background(Circle().fill(Color.cardBackground))
                            .frame(width: isSelected ? 13 : 8, height: isSelected ? 13 : 8)
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
            AxisMarks(values: card.rungs.map(\.threshold)) { value in
                NFLStatAxisLabels9483.reservedLabel(
                    value.as(Double.self).map(PlayerPropsFamily.targetLabel) ?? "", fontSize: axisFontSize)
            }
        }
        // Every quoted line has a tick, priced or not, so a line with no
        // recent price still stands where it is; each label is centred under
        // its own tick and stem. A row too dense for every label keeps the
        // selected line's label first and drops whole labels, never overlaps.
        .chartOverlay { proxy in
            GeometryReader { geo in
                NFLStatAxisLabels9483(values: card.rungs.map(\.threshold),
                                      texts: card.rungs.map { PlayerPropsFamily.targetLabel($0.threshold) },
                                      keep: card.rungs.firstIndex { $0.rowID == selected?.rowID },
                                      fontSize: axisFontSize, proxy: proxy,
                                      plotFrame: geo[proxy.plotAreaFrame], ticks: true)
            }
        }
        .frame(height: expanded ? 240 : 150)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(PlayerMilestoneProfile.spokenSummary(profile, stat: card.stat)
            + (card.actual.map { ". Final \(NFLFinishCardView9483.points($0))" } ?? ""))
    }
}

// MARK: - Stat-axis labels

/// The cards' stat-axis labels, drawn by us and centred on their ticks — the
/// #8481 rule, for the same reason (`ChartTimeAxisLabels`): on iOS 27 an
/// `AxisValueLabel` hangs RIGHT of its tick whether it is `anchor: .top` or
/// `collisionResolution: .greedy`, so on a 5- or 10-yard ladder every label
/// printed under the NEXT stem ("40+" under the 50+ stem, native's runtime
/// review of PR #11038). The framework keeps an invisible label per tick for
/// the row's height; this view draws the visible one.
struct NFLStatAxisLabels9483: View {
    let values: [Double]
    let texts: [String]
    /// The label kept first when the row cannot hold them all (the selected line).
    let keep: Int?
    let fontSize: CGFloat
    let proxy: ChartProxy
    let plotFrame: CGRect
    var ticks = false

    /// The framework's label, kept for the row's height, never for its ink.
    static func reservedLabel(_ text: String, fontSize: CGFloat) -> some AxisMark {
        AxisValueLabel(anchor: .topTrailing) {
            Text(text).font(.system(size: fontSize)).foregroundStyle(Color.clear)
        }
    }

    /// The width a label's ink takes at `fontSize`, measured in the font it is
    /// drawn in.
    static func labelWidth(_ text: String, fontSize: CGFloat) -> CGFloat {
        #if canImport(UIKit)
        return (text as NSString).size(withAttributes: [.font: UIFont.systemFont(ofSize: fontSize)]).width
        #else
        return CGFloat(text.count) * fontSize * 0.62
        #endif
    }

    /// Which labels are drawn, and where each one's centre sits in plot points.
    ///
    /// Every label is centred on its tick, then moved inward only as far as it
    /// must go to stay inside the plot (`OddsChartView.xAxisLabelCenters`).
    /// Where two would come closer than `xAxisLabelMinGap`, the later one in
    /// priority order is dropped WHOLE — the kept label (the selected line),
    /// then the two ends, then the rest left to right — so no label is ever
    /// printed over another or under a neighbour's stem.
    static func placements(tickPositions: [CGFloat], widths: [CGFloat], plotWidth: CGFloat,
                           keep: Int?) -> [(index: Int, center: CGFloat)] {
        let count = min(tickPositions.count, widths.count)
        guard count > 0 else { return [] }
        let centers = (0..<count).map {
            OddsChartView.xAxisLabelCenters(tickPositions: [tickPositions[$0]], plotWidth: plotWidth,
                                            labelWidth: widths[$0])[0]
        }
        var order = [keep, 0, count - 1].compactMap { $0 }.filter { (0..<count).contains($0) }
        order += (0..<count).filter { !order.contains($0) }
        var kept: [Int] = []
        for index in order where !kept.contains(index) {
            let clear = kept.allSatisfy { other in
                abs(centers[index] - centers[other])
                    >= (widths[index] + widths[other]) / 2 + OddsChartView.xAxisLabelMinGap
            }
            if clear { kept.append(index) }
        }
        return kept.sorted().map { ($0, centers[$0]) }
    }

    var body: some View {
        let count = min(values.count, texts.count)
        let placed: [(index: Int, x: CGFloat)] = (0..<count).compactMap { index in
            proxy.position(forX: values[index]).map { (index, $0) }
        }
        let labelY = plotFrame.maxY + ChartTimeAxisLabels.labelCenterOffset * fontSize / 9
        let shown = Self.placements(tickPositions: placed.map(\.x),
                                    widths: placed.map { Self.labelWidth(texts[$0.index], fontSize: fontSize) },
                                    plotWidth: plotFrame.width, keep: placed.firstIndex { $0.index == keep })
        if ticks {
            ForEach(Array(placed.enumerated()), id: \.offset) { _, item in
                Rectangle()
                    .fill(Color.secondary.opacity(0.6))
                    .frame(width: 1, height: 4)
                    .position(x: plotFrame.minX + item.x, y: plotFrame.maxY + 2)
            }
            .accessibilityHidden(true)
            .allowsHitTesting(false)
        }
        ForEach(shown, id: \.index) { label in
            Text(texts[placed[label.index].index])
                .font(.system(size: fontSize))
                .foregroundStyle(Color.primary)
                .lineLimit(1)
                .fixedSize()
                .position(x: plotFrame.minX + label.center, y: labelY)
                .accessibilityHidden(true)
                .allowsHitTesting(false)
        }
    }
}

// MARK: - One card, either family

struct NFLEventCardView9483: View {
    let card: NFLEventCard9483
    let awayName: String
    let homeName: String
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false

    var body: some View {
        Group {
            switch card {
            case .finish(let finish):
                NFLFinishCardView9483(card: finish, awayName: awayName, homeName: homeName,
                                      awayColor: awayColor, homeColor: homeColor, expanded: expanded)
            case .milestone(let milestone):
                NFLMilestoneCardView9483(
                    card: milestone,
                    color: PlayerPropsTeam.color(for: milestone.side, home: homeColor, away: awayColor),
                    state: state, expanded: expanded)
            }
        }
        .padding(16)
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.secondary.opacity(0.15)))
    }
}

// MARK: - The deck under the chart

/// The compact cards, side by side, each with an explicit "Open" control —
/// the page scrolls vertically, so a tap on a chart inside a card is never
/// taken as a request to expand it.
struct NFLEventCardDeckView9483: View {
    let cards: [NFLEventCard9483]
    let awayName: String
    let homeName: String
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    @AccessibilityFocusState private var focused: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Game stories")
                    .font(.headline)
                Spacer()
                Text(cards.count == 1 ? "1 card" : "\(cards.count) cards")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            // Re-read each minute so a pregame price that stops being observed
            // loses its number on the page too, not only in the reader.
            TimelineView(.periodic(from: .now, by: 60)) { tick in
            ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(alignment: .top, spacing: 12) {
                    ForEach(cards.map { $0.current(at: tick.date) }) { card in
                        VStack(spacing: 6) {
                            NFLEventCardView9483(card: card, awayName: awayName, homeName: homeName,
                                                 awayColor: awayColor, homeColor: homeColor, state: state)
                            Button { state.open(card.id) } label: {
                                Label("Open full size", systemImage: "arrow.up.left.and.arrow.down.right")
                                    .font(.caption.weight(.semibold))
                                    .frame(maxWidth: .infinity, minHeight: 44)
                            }
                            .accessibilityLabel("Open \(card.title) full size")
                        }
                        .containerRelativeFrame(.horizontal) { width, _ in cards.count > 1 ? width * 0.86 : width }
                        .accessibilityFocused($focused, equals: card.id)
                        .id(card.id)
                    }
                }
                .scrollTargetLayout()
            }
            .scrollTargetBehavior(.viewAligned)
            // #11060 — Back lands on the card it was opened from, on screen,
            // even when a rotation under the reader re-laid this deck out.
            .onChange(of: state.openCardID) { old, new in
                guard old != nil, new == nil, let back = state.returnCardID else { return }
                proxy.scrollTo(back, anchor: .leading)
            }
            }
            }
        }
        // Back from the reader returns focus to the card it was opened from.
        .onChange(of: state.openCardID) { old, new in
            if old != nil, new == nil { focused = state.returnCardID }
        }
    }
}
