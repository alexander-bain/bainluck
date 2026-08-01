import SwiftUI

// MARK: - Comparison Card (cross_source_comparison / multi-outcome)

/// Leaderboard comparison card for cross-source or multi-outcome markets.
/// Uses `topOutcomes` from the futures data (not distribution_outcomes).
/// Probability bars fade below 40%. "Show more" footer with outcome count.
struct ComparisonCardView: View {
    let data: FeedFuturesData
    @Binding var navigationPath: NavigationPath
    var onOpen: (() -> Void)? = nil

    // MARK: - Derived data

    private var outcomes: [FeedFuturesOutcome] {
        data.topOutcomes ?? []
    }

    private var shownOutcomes: [FeedFuturesOutcome] {
        Array(outcomes.prefix(4))
    }

    private var maxProbability: Double {
        max(outcomes.compactMap(\.probability).max() ?? 0, 0.01)
    }

    private var totalOutcomeCount: Int {
        data.outcomeCount ?? outcomes.count
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
                .padding(.bottom, 14)

            // Leaderboard rows
            VStack(spacing: 0) {
                ForEach(Array(shownOutcomes.enumerated()), id: \.element.id) { index, outcome in
                    outcomeRow(outcome, isLeader: index == 0)
                }
            }

            // Footer
            Divider()
                .padding(.top, 10)

            HStack(spacing: 6) {
                if totalOutcomeCount > 4 {
                    Text("Show more")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(DS.emerald)
                }
                Spacer()
                Text("\(totalOutcomeCount) markets")
                    .font(.system(size: 11))
                    .foregroundStyle(DS.textMuted)
                // #490: confidence signal (1-3 bars) — renders nothing when absent.
                SignalBarsView(tier: data.confidenceTier)
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

    // MARK: - Outcome row

    @ViewBuilder
    private func outcomeRow(_ outcome: FeedFuturesOutcome, isLeader: Bool) -> some View {
        let probability = outcome.probability ?? 0
        let pct = Int((probability * 100).rounded())
        let barWidth = max(5, probability / maxProbability * 100)
        let barOpacity: Double = probability >= 0.4 ? 1.0 : 0.55

        VStack(spacing: 0) {
            Divider()

            HStack(spacing: 10) {
                // Outcome name
                Text(outcome.name)
                    .font(.system(size: 13, weight: isLeader ? .semibold : .medium))
                    .foregroundStyle(isLeader ? DS.textPrimary : DS.textSecondary)
                    .lineLimit(1)

                Spacer()

                // Probability bar
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 999)
                            .fill(DS.trackBg)
                        RoundedRectangle(cornerRadius: 999)
                            .fill(DS.emerald.opacity(barOpacity))
                            .frame(width: max(2, geo.size.width * barWidth / 100))
                    }
                }
                .frame(width: 100, height: 7)

                // Percentage
                Text(probability > 0 ? "\(pct)%" : "\u{2014}")
                    .font(.system(size: 14, weight: .bold, design: .monospaced))
                    .foregroundStyle(DS.textPrimary)
                    .frame(width: 36, alignment: .trailing)
            }
            .padding(.vertical, 8)
        }
    }
}

// MARK: - Previews

#if DEBUG
#Preview("Comparison - 6 outcomes") {
    ScrollView {
        ComparisonCardView(
            data: comparisonPreviewData(
                name: "Who will win the 2026 NBA MVP?",
                category: "basketball",
                outcomes: [
                    (name: "Luka Doncic", prob: 0.35),
                    (name: "Shai Gilgeous-Alexander", prob: 0.28),
                    (name: "Jayson Tatum", prob: 0.15),
                    (name: "Victor Wembanyama", prob: 0.10),
                    (name: "Anthony Edwards", prob: 0.06),
                    (name: "Giannis Antetokounmpo", prob: 0.04),
                ],
                outcomeCount: 12
            ),
            navigationPath: .constant(NavigationPath())
        )
        .padding()
    }
    .background(Color.groupedBackground)
}

#Preview("Comparison - 4 outcomes") {
    ScrollView {
        ComparisonCardView(
            data: comparisonPreviewData(
                name: "Which country will host the 2034 World Cup?",
                category: "soccer",
                outcomes: [
                    (name: "Saudi Arabia", prob: 0.82),
                    (name: "Australia", prob: 0.08),
                    (name: "Indonesia", prob: 0.05),
                    (name: "Field", prob: 0.03),
                ],
                outcomeCount: 4
            ),
            navigationPath: .constant(NavigationPath())
        )
        .padding()
    }
    .background(Color.groupedBackground)
}

private func comparisonPreviewData(
    name: String,
    category: String,
    outcomes: [(name: String, prob: Double)],
    outcomeCount: Int
) -> FeedFuturesData {
    let topOutcomes = outcomes.enumerated().map { idx, o in
        FeedFuturesOutcome(
            id: 9000 + idx,
            name: o.name,
            probability: o.prob,
            rank: idx + 1,
            movement: nil
        )
    }
    return FeedFuturesData(
        id: 997,
        name: name,
        sport: nil,
        sportName: nil,
        llmSportCategory: category,
        source: "kalshi",
        sourceCount: 1,
        sources: ["kalshi"],
        marketTier: 2,
        status: "open",
        resolutionDate: "2026-06-30T00:00:00Z",
        topOutcomes: topOutcomes,
        outcomeCount: outcomeCount,
        canonicalMarketKey: nil,
        groupId: nil,
        groupType: nil,
        imageUrl: nil,
        hookDescription: nil,
        matchedOutcomes: nil,
        discoverCard: FeedDiscoverCard(
            suggestedFormat: "cross_source_comparison",
            bundleCandidate: false,
            comparisonTheme: nil,
            thresholdPoints: nil,
            distributionOutcomes: nil,
            remainingOutcomeCount: nil,
            qaSignals: nil,
            publicSourceDisagreement: nil,
            reasons: nil
        ),
        confidenceTier: nil,
        confidenceScore: nil,
        // L2-225: preview fixture — an OPEN market, so it never trips the shared
        // terminal-lifecycle gate (`FeedLifecycle.futuresIsSettled`).
        resolved: nil,
        winner: nil,
        winnerOpeningProbability: nil
    )
}
#endif
