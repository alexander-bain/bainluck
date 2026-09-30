import Foundation

/// Selected Discover A (#9642): seat related questions together without
/// hiding a lone fourth member or making every standalone market a group.
enum DiscoverGroupRows {
    static let showsEveryRowUpTo = 4
    static let collapsedSeatCount = 3

    static func showsEveryRow(itemCount: Int, expanded: Bool) -> Bool {
        expanded || itemCount <= showsEveryRowUpTo
    }

    static func visibleCount(itemCount: Int, expanded: Bool) -> Int {
        let count = max(0, itemCount)
        return showsEveryRow(itemCount: count, expanded: expanded) ? count : collapsedSeatCount
    }

    /// Even a short theme group can open full member cards. Short comparison
    /// groups already show all their rows and need no extra control.
    static func canExpand(itemCount: Int, kind: String?) -> Bool {
        itemCount > 0 && (kind != "comparison" || itemCount > showsEveryRowUpTo)
    }

    static func footerTitle(itemCount: Int, kind: String?, expanded: Bool) -> String? {
        guard !expanded, canExpand(itemCount: itemCount, kind: kind) else { return nil }
        return itemCount > showsEveryRowUpTo ? "All \(itemCount) questions" : "Expand"
    }

    /// Reuse the card's existing date/threshold rule, never the maximum price.
    static func markedRung(in points: [FeedDiscoverThresholdPoint]) -> FeedDiscoverThresholdPoint? {
        let priced = points.filter { $0.probability != nil }
            .sorted { ($0.value ?? 0) < ($1.value ?? 0) }
        return heatMapBetterThanEvenRung(priced)
    }

    struct CompactSummary: Equatable {
        let label: String?
        let probability: Double?
        let movement: Double?
    }

    enum FullCardStyle: Equatable { case heatmap, distribution, comparison, futures }

    /// The same existing-card eligibility as a standalone Discover member.
    static func fullCardStyle(for data: FeedFuturesData) -> FullCardStyle {
        if data.discoverCard?.suggestedFormat == "threshold_heatmap",
           (data.discoverCard?.thresholdPoints ?? []).filter({ $0.probability != nil }).count >= 2 { return .heatmap }
        if data.discoverCard?.suggestedFormat == "outcome_distribution",
           (data.discoverCard?.distributionOutcomes ?? []).filter({ $0.probability != nil }).count >= 4 { return .distribution }
        if data.discoverCard?.suggestedFormat == "cross_source_comparison"
            || (data.topOutcomes?.count ?? 0) >= 4 { return .comparison }
        return .futures
    }

    static func compactSummary(for data: FeedFuturesData) -> CompactSummary {
        let points = (data.discoverCard?.thresholdPoints ?? []).filter { $0.probability != nil }
        if fullCardStyle(for: data) == .heatmap,
           let rung = markedRung(in: points) {
            let matching = data.topOutcomes?.first {
                $0.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                    == rung.label.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            }
            return CompactSummary(label: rung.label, probability: rung.probability, movement: matching?.movement)
        }
        // Ordinary and all-below-even cards retain their served leader; missing
        // probability stays missing rather than turning into a fabricated zero.
        let leader = data.topOutcomes?.first
        return CompactSummary(label: leader?.name, probability: leader?.probability, movement: leader?.movement)
    }
}
