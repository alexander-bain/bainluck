import SwiftUI

/// #9483 — the page's one route to every original market (web's
/// `QuestionCatalog`, #10809). Collapsed by default so it costs one row; open,
/// it is the existing family browser over `QuestionCatalog9483` groups.
///
/// A group shows its first six outcomes and offers the rest. An outcome with
/// no printable price says why, before the final (#10877): "Period finished"
/// for a period the server says closed, "No recent probability update" for a
/// stale live observation, and "Probability unavailable" when the reason is
/// unknown. After the final the graded cards above own results and the row
/// prints nothing. The venue, period, lines and when the price was seen sit behind
/// "About this market". Expansion is keyed by the group's stable id, so it
/// survives a refresh.
///
/// Equatable on its inputs, and mounted `.equatable()`: a live page re-renders
/// on every stream frame, and the catalog regroups up to ~1,600 rows, so it
/// rebuilds only when the markets payload or the game's status changes.
struct AllMarketsCatalogView9483: View, Equatable {
    let gameMarkets: GameMarketsResponse
    let eventStatus: String?

    /// Outcomes a group shows before the reader asks for the rest (Atlas v6).
    static let groupPreview = 6
    static let title = "All markets"
    static let noRecentPrice = "No recent probability update"
    static let periodFinished = "Period finished"
    static let unavailablePrice = "Probability unavailable"

    @State private var isOpen = LaunchRig.expandsCollapsedSections()
    @State private var expanded: Set<String> = []

    nonisolated static func == (a: Self, b: Self) -> Bool {
        a.gameMarkets == b.gameMarkets && a.eventStatus == b.eventStatus
    }

    var body: some View {
        let groups = QuestionCatalog9483.build(gameMarkets, status: eventStatus)
        if !groups.isEmpty {
            // The page's existing catalog header (`RelatedMarketsCatalogView`):
            // a plain button, so the title does not read as a tinted link.
            VStack(alignment: .leading, spacing: 10) {
                Button {
                    withAnimation(.easeInOut(duration: 0.15)) { isOpen.toggle() }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: isOpen ? "chevron.down" : "chevron.right")
                            .font(.caption.weight(.semibold))
                            .accessibilityHidden(true)
                        Text(Self.title)
                            .font(.subheadline.weight(.semibold))
                        Spacer()
                        Text(Self.countText(groups.count))
                            .font(.caption)
                            .monospacedDigit()
                            .foregroundStyle(.secondary)
                    }
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("\(Self.title), \(Self.countText(groups.count))")
                .accessibilityValue(isOpen ? "Expanded" : "Collapsed")

                if isOpen {
                    MarketBrowserView(
                        label: Self.title,
                        items: groups,
                        group: { $0.family.rawValue },
                        searchText: Self.searchText,
                        searchPrompt: "player, team or market",
                        chooserLabel: "Market type"
                    ) { group in
                        groupCard(group)
                    }
                }
            }
            .accessibilityIdentifier("all-markets-catalog")
            .padding(.horizontal, 16)
        }
    }

    static func countText(_ count: Int) -> String {
        "\(count) \(count == 1 ? "market" : "markets")"
    }

    static func searchText(_ group: QuestionCatalog9483.Group) -> String {
        ([group.question, group.venue ?? "", group.period ?? ""] + group.outcomes.map(\.label))
            .joined(separator: " ")
    }

    /// What an outcome prints in the price column.
    static func priceText(_ outcome: QuestionCatalog9483.Outcome, status: String?) -> String? {
        if let p = outcome.probability { return formatProbability(p) }
        if SettledQuote.isSettled(status) { return nil }
        switch outcome.absence {
        case .settled: return nil
        case .periodFinished: return periodFinished
        case .stale: return noRecentPrice
        case .unavailable, nil: return unavailablePrice
        }
    }

    /// The newest observation among the outcomes that print a price.
    static func seenStamp(_ group: QuestionCatalog9483.Group) -> String? {
        let seen = group.outcomes.filter { $0.probability != nil }.compactMap(\.observedAt).sorted().last
        return SourceAge.preciseStamp(seen)
    }

    @ViewBuilder
    private func groupCard(_ group: QuestionCatalog9483.Group) -> some View {
        let isExpanded = expanded.contains(group.id)
        let shown = isExpanded ? group.outcomes : Array(group.outcomes.prefix(Self.groupPreview))
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(group.question)
                    .font(.subheadline.weight(.medium))
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                if let venue = group.venue {
                    Text(venue).font(.caption).foregroundStyle(.secondary)
                }
            }
            ForEach(Array(shown.enumerated()), id: \.offset) { _, outcome in
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    Text(outcome.label)
                        .font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    if let price = Self.priceText(outcome, status: eventStatus) {
                        Text(price)
                            .font(outcome.probability == nil
                                  ? .caption : .subheadline.weight(.semibold).monospacedDigit())
                            .foregroundStyle(outcome.probability == nil ? .secondary : .primary)
                    }
                }
                .accessibilityElement(children: .combine)
            }
            if group.outcomes.count > Self.groupPreview {
                Button(isExpanded ? "Show fewer outcomes" : "Show all \(group.outcomes.count) outcomes") {
                    if isExpanded { expanded.remove(group.id) } else { expanded.insert(group.id) }
                }
                .font(.subheadline.weight(.semibold))
                .frame(minHeight: 44)
            }
            DisclosureGroup("About this market") {
                VStack(alignment: .leading, spacing: 2) {
                    detail("Market", group.question)
                    if let venue = group.venue { detail("Venue", venue) }
                    if let period = group.period { detail("Period", period) }
                    let lines = Self.lines(group)
                    if !lines.isEmpty { detail(lines.count == 1 ? "Line" : "Lines", lines.joined(separator: ", ")) }
                    if let seen = Self.seenStamp(group) { detail("Price seen", seen) }
                }
                .padding(.top, 2)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 8)
    }

    static func lines(_ group: QuestionCatalog9483.Group) -> [String] {
        var seen: [Double] = []
        for t in group.outcomes.compactMap(\.threshold) where !seen.contains(t) { seen.append(t) }
        return seen.map { $0.rounded() == $0 ? String(Int($0)) : String($0) }
    }

    private func detail(_ term: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(term)
            Text(value).foregroundStyle(.primary)
        }
        .accessibilityElement(children: .combine)
    }
}
