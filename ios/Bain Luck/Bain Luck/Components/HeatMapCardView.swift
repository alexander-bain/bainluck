import SwiftUI

// MARK: - Heatmap Cell Grid

/// Renders a threshold heatmap as a horizontal strip of 3-8 emerald-intensity cells.
/// Each cell represents a binary market threshold; probability drives the emerald
/// opacity ramp so you can read at a glance where belief crosses 50%.
struct HeatMapCardView: View {
    let data: FeedFuturesData
    @Binding var navigationPath: NavigationPath
    var onOpen: (() -> Void)? = nil

    /// Cap visible cells so each is wide enough to read at 375pt phone width
    /// (#902-follow-up: 8 cells crammed the labels to ~7pt and truncated them).
    /// Overflow is surfaced as "+N more" rather than shrinking everything.
    private let maxCells = 5

    /// Dynamic-type-aware label size so the threshold labels respect the user's
    /// text-size setting instead of a hardcoded 11pt.
    @ScaledMetric(relativeTo: .caption) private var labelFontSize: CGFloat = 12

    // MARK: - Derived data

    private var sortedPoints: [FeedDiscoverThresholdPoint] {
        (data.discoverCard?.thresholdPoints ?? [])
            .filter { $0.probability != nil }
            .sorted { ($0.value ?? 0) < ($1.value ?? 0) }
    }

    private var cells: [HeatMapCell] {
        Array(sortedPoints.prefix(maxCells)).map { point in
            HeatMapCell(
                label: compactThresholdLabel(point.label),
                probability: point.probability ?? 0
            )
        }
    }

    private var overflowCount: Int {
        max(0, sortedPoints.count - maxCells)
    }

    private var categoryLabel: String {
        sportCategoryDisplayName(data.sportName ?? data.llmSportCategory).uppercased()
    }

    private var resolvesText: String? {
        guard let rd = data.resolutionDate, let date = rd.asDate else { return nil }
        let fmt = DateFormatter()
        fmt.dateFormat = "MMM d"
        return "Resolves \(fmt.string(from: date))"
    }

    private var lastAbove50Label: String? {
        // Derive from ALL thresholds (not the capped cells) so the crossover
        // summary stays correct even when cells overflow past maxCells.
        let above = sortedPoints.filter { ($0.probability ?? 0) >= 0.50 }
        guard let last = above.last else { return nil }
        return compactThresholdLabel(last.label)
    }

    // MARK: - Body

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Chrome: category + resolves
            HStack {
                Text(categoryLabel)
                    .font(.system(size: 10, weight: .heavy))
                    .tracking(0.5)
                    .foregroundStyle(.secondary)
                Spacer()
                if let resolvesText {
                    Text(resolvesText)
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                }
            }
            .padding(.bottom, 3)

            // Market name
            Text(data.name)
                .font(.system(size: 15, weight: .semibold))
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.bottom, 16)

            // Cell grid
            HStack(spacing: 3) {
                ForEach(Array(cells.enumerated()), id: \.offset) { _, cell in
                    cellView(cell)
                }
            }

            // Threshold labels — readable size, wrap to 2 lines instead of
            // truncating, and respect Dynamic Type (#902-follow-up).
            HStack(alignment: .top, spacing: 3) {
                ForEach(Array(cells.enumerated()), id: \.offset) { _, cell in
                    Text(cell.label)
                        .font(.system(size: labelFontSize, weight: .medium, design: .monospaced))
                        .foregroundStyle(DS.textSecondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                        .lineLimit(2)
                        .minimumScaleFactor(0.85)
                }
            }
            .padding(.top, 7)

            // Summary footer
            Divider()
                .padding(.top, 14)

            HStack(spacing: 6) {
                if let threshold = lastAbove50Label {
                    Text("Above 50% through")
                        .font(.system(size: 12))
                        .foregroundStyle(DS.textSecondary)
                    Text(threshold)
                        .font(.system(size: 13, weight: .bold, design: .monospaced))
                        .foregroundStyle(DS.emerald)
                } else {
                    Text("All below 50%")
                        .font(.system(size: 12))
                        .foregroundStyle(DS.textSecondary)
                }
                if overflowCount > 0 {
                    Text("+\(overflowCount) more")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(DS.textMuted)
                }
                Spacer()
                if let src = data.source {
                    Text(src.uppercased())
                        .font(.system(size: 9, weight: .heavy))
                        .foregroundStyle(.blue)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(Color.blue.opacity(0.10), in: Capsule())
                }
            }
            .padding(.top, 12)
        }
        .padding(16)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5)
        )
        .shadow(color: .black.opacity(0.07), radius: 8, x: 0, y: 3)
        .contentShape(Rectangle())
        .onTapGesture {
            navigationPath.append(Route.futuresDetail(id: data.id))
            onOpen?()
        }
    }

    // MARK: - Cell view

    @ViewBuilder
    private func cellView(_ cell: HeatMapCell) -> some View {
        let pct = Int((cell.probability * 100).rounded())
        let color = cellTextColor(cell.probability)
        (
            Text("\(pct)")
                .font(.system(size: 14, weight: .bold, design: .monospaced))
                .foregroundColor(color)
            +
            Text("%")
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .foregroundColor(color)
        )
        .frame(maxWidth: .infinity)
        .frame(height: 56)
        .background(cellBackground(cell.probability), in: RoundedRectangle(cornerRadius: 6))
    }

    // MARK: - Color ramp

    /// Emerald intensity ramp matching the web implementation.
    /// Full green (#10B981) at >=85%, stepping down with opacity for lower probabilities.
    private func cellBackground(_ probability: Double) -> Color {
        let emerald = Color(red: 16.0/255, green: 185.0/255, blue: 129.0/255) // #10B981
        if probability >= 0.85 { return emerald }
        if probability >= 0.65 { return emerald.opacity(0.76) }
        if probability >= 0.50 { return emerald.opacity(0.52) }
        if probability >= 0.30 { return emerald.opacity(0.26) }
        return emerald.opacity(0.11)
    }

    /// White text for high probabilities (>=50%), dark for low.
    private func cellTextColor(_ probability: Double) -> Color {
        if probability >= 0.50 { return .white }
        if probability >= 0.30 { return DS.textPrimary }
        return DS.textMuted
    }

    // MARK: - Label formatting

    private func compactThresholdLabel(_ label: String) -> String {
        label
            .replacingOccurrences(of: "Above ", with: "\u{2265}")
            .replacingOccurrences(of: "Below ", with: "<")
            .replacingOccurrences(of: " or more", with: "+")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - Cell model

private struct HeatMapCell {
    let label: String
    let probability: Double
}

// MARK: - Previews

#if DEBUG
#Preview("Heatmap - 5 cells") {
    ScrollView {
        HeatMapCardView(
            data: heatmapPreviewData(
                name: "Dune: Part Three -- Rotten Tomatoes score",
                category: "entertainment",
                cells: [
                    (label: "\u{2265}70", prob: 0.92),
                    (label: "\u{2265}75", prob: 0.81),
                    (label: "\u{2265}80", prob: 0.64),
                    (label: "\u{2265}85", prob: 0.38),
                    (label: "\u{2265}90", prob: 0.15),
                ]
            ),
            navigationPath: .constant(NavigationPath())
        )
        .padding()
    }
    .background(Color.groupedBackground)
}

#Preview("Heatmap - 4 cells") {
    ScrollView {
        HeatMapCardView(
            data: heatmapPreviewData(
                name: "Phoenix July average high temperature",
                category: "weather",
                cells: [
                    (label: "\u{2265}105\u{00B0}", prob: 0.88),
                    (label: "\u{2265}108\u{00B0}", prob: 0.67),
                    (label: "\u{2265}110\u{00B0}", prob: 0.41),
                    (label: "\u{2265}112\u{00B0}", prob: 0.19),
                ]
            ),
            navigationPath: .constant(NavigationPath())
        )
        .padding()
    }
    .background(Color.groupedBackground)
}

private func heatmapPreviewData(
    name: String,
    category: String,
    cells: [(label: String, prob: Double)]
) -> FeedFuturesData {
    let points = cells.enumerated().map { idx, cell in
        FeedDiscoverThresholdPoint(
            source: "outcome",
            label: cell.label,
            value: Double(idx),
            unit: nil,
            direction: "above",
            probability: cell.prob,
            needsSiblingMarkets: nil
        )
    }
    return FeedFuturesData(
        id: 999,
        name: name,
        sport: nil,
        sportName: nil,
        llmSportCategory: category,
        source: "kalshi",
        sourceCount: 1,
        sources: ["kalshi"],
        marketTier: 2,
        status: "open",
        resolutionDate: "2026-12-31T00:00:00Z",
        topOutcomes: [],
        outcomeCount: cells.count,
        canonicalMarketKey: nil,
        groupId: nil,
        groupType: nil,
        imageUrl: nil,
        hookDescription: nil,
        matchedOutcomes: nil,
        discoverCard: FeedDiscoverCard(
            suggestedFormat: "threshold_heatmap",
            bundleCandidate: false,
            comparisonTheme: nil,
            thresholdPoints: points,
            distributionOutcomes: nil,
            remainingOutcomeCount: nil,
            qaSignals: nil,
            publicSourceDisagreement: nil,
            reasons: nil
        ),
        confidenceTier: nil,
        confidenceScore: nil
    )
}
#endif
