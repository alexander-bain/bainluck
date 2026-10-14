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
            .chartXAxis { AxisMarks(values: .stride(by: 7)) { AxisValueLabel(anchor: .top) } }
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

    var body: some View {
        let selected = state.selectedIndex(in: card)
        let rung = selected.map { card.rungs[$0] }
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(card.stat)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(card.player)
                        .font(.title3.weight(.bold))
                        .lineLimit(2)
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
            HStack(spacing: 4) {
                Button { state.move(in: card, by: -1) } label: {
                    Image(systemName: "chevron.left").frame(width: 44, height: 44)
                }
                .disabled(selected.map { $0 == 0 } ?? true)
                .accessibilityLabel("Previous line")
                Button {
                    if let rung { state.detailsRowID = rung.rowID }
                } label: {
                    VStack(spacing: 2) {
                        if let rung {
                            Text("\(PlayerPropsFamily.targetLabel(rung.threshold)) · \(formatProbability(rung.chance))")
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(color)
                            Text(verdict(rung))
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityHint("Shows this line's exact quote")
                Button { state.move(in: card, by: 1) } label: {
                    Image(systemName: "chevron.right").frame(width: 44, height: 44)
                }
                .disabled(selected.map { $0 >= card.rungs.count - 1 } ?? true)
                .accessibilityLabel("Next line")
            }
        }
    }

    private func verdict(_ rung: NFLMilestoneCard9483.Rung) -> String {
        switch rung.hit {
        case true?: return "Reached · details"
        case false?: return "Not reached · details"
        case nil: return card.basis == .pregamePrice ? "Details" : "Pre-game chance · details"
        }
    }

    private func chart(_ profile: PlayerMilestoneProfile.Profile, selected: NFLMilestoneCard9483.Rung?) -> some View {
        let upper = max(profile.domain.upperBound, (card.actual ?? 0) * 1.08)
        return Chart {
            if let actual = card.actual {
                RectangleMark(xStart: .value("Start", profile.domain.lowerBound), xEnd: .value("Final", actual),
                              yStart: .value("Chance", 0), yEnd: .value("Chance", 1))
                    .foregroundStyle(color.opacity(0.07))
                RuleMark(x: .value("Final", actual))
                    .foregroundStyle(color)
                    .lineStyle(StrokeStyle(lineWidth: 2))
                    // Near the right edge the label reads leftward, so it is never clipped.
                    .annotation(position: .top,
                                alignment: actual > profile.domain.lowerBound + (upper - profile.domain.lowerBound) * 0.6
                                    ? .trailing : .leading) {
                        Text("Final \(NFLFinishCardView9483.points(actual))")
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(color)
                    }
            }
            RuleMark(y: .value("Chance", 0.5))
                .foregroundStyle(Color.secondary.opacity(0.35))
                .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
            ForEach(card.rungs) { rung in
                let isSelected = rung.rowID == selected?.rowID
                RuleMark(x: .value("Line", rung.threshold),
                         yStart: .value("Chance", 0), yEnd: .value("Chance", rung.chance))
                    .foregroundStyle(color.opacity(isSelected ? 0.9 : 0.3))
                    .lineStyle(StrokeStyle(lineWidth: isSelected ? 2 : 1.5))
                PointMark(x: .value("Line", rung.threshold), y: .value("Chance", rung.chance))
                    .symbol {
                        Circle()
                            .strokeBorder(isSelected ? color : Color.secondary, lineWidth: isSelected ? 2.5 : 1.5)
                            .background(Circle().fill(Color.cardBackground))
                            .frame(width: isSelected ? 13 : 8, height: isSelected ? 13 : 8)
                    }
            }
        }
        .chartXScale(domain: profile.domain.lowerBound...upper)
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
            AxisMarks(values: profile.axisLines) { value in
                AxisValueLabel(collisionResolution: .greedy) {
                    if let line = value.as(Double.self) { Text(PlayerPropsFamily.targetLabel(line)) }
                }
            }
        }
        .frame(height: expanded ? 240 : 150)
        .padding(.top, card.actual == nil ? 0 : 14)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(PlayerMilestoneProfile.spokenSummary(profile, stat: card.stat)
            + (card.actual.map { ". Final \(NFLFinishCardView9483.points($0))" } ?? ""))
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
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(alignment: .top, spacing: 12) {
                    ForEach(cards) { card in
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
        }
        // Back from the reader returns focus to the card it was opened from.
        .onChange(of: state.openCardID) { old, new in
            if old != nil, new == nil { focused = state.returnCardID }
        }
    }
}
