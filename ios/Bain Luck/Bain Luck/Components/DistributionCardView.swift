import SwiftUI

// MARK: - Distribution Card (outcome_distribution)

/// Ranked leaderboard card for multi-outcome distribution markets.
/// Shows top 4 outcomes with probability bars, rank numbers, and percentages.
/// Leader row is bold; remaining outcomes collapsed behind "Show more".
struct DistributionCardView: View {
    let data: FeedFuturesData
    @Binding var navigationPath: NavigationPath
    var onOpen: (() -> Void)? = nil

    /// #6343 — the price-age reveal, open or closed. See `PriceAgeMarkView`.
    @State private var revealedPriceAge: String?

    // MARK: - Derived data

    private var outcomes: [FeedDiscoverDistributionOutcome] {
        (data.discoverCard?.distributionOutcomes ?? [])
            .filter { $0.probability != nil }
    }

    private var shownOutcomes: [FeedDiscoverDistributionOutcome] {
        Array(outcomes.prefix(4))
    }

    private var remainingCount: Int {
        let explicit = data.discoverCard?.remainingOutcomeCount ?? 0
        let overflow = max(0, outcomes.count - 4)
        return explicit + overflow
    }

    private var maxProbability: Double {
        max(outcomes.compactMap(\.probability).max() ?? 0, 0.01)
    }

    private var categoryLabel: String {
        sportCategoryDisplayName(data.sportName ?? data.llmSportCategory).uppercased()
    }

    /// #4081 — a UTC-midnight `resolution_date` is a declared calendar date, not
    /// an instant; localising it drew the day before west of UTC.
    private var resolvesText: String? {
        guard let text = CalendarDeadline.format(data.resolutionDate, style: .monthDay) else { return nil }
        return "Resolves \(text)"
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
                ForEach(Array(shownOutcomes.enumerated()), id: \.offset) { index, outcome in
                    outcomeRow(outcome, rank: index + 1, isLeader: index == 0)
                }

                // "Show more" row
                if remainingCount > 0 {
                    HStack(spacing: 0) {
                        Text("\(shownOutcomes.count + 1)")
                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                            .foregroundStyle(DS.textMuted)
                            .frame(width: 20, alignment: .leading)

                        Text("Field and remaining outcomes")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(DS.textMuted)
                            .lineLimit(1)

                        Spacer()

                        Text("+\(remainingCount)")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(DS.textMuted)
                    }
                    .padding(.vertical, 8)
                }
            }

            // Footer
            Divider()
                .padding(.top, 10)

            HStack(spacing: 6) {
                Text("Distribution")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(DS.textMuted)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(DS.trackBg, in: Capsule())
                Spacer()
                // #490: confidence signal (1-3 bars) — renders nothing when absent.
                SignalBarsView(tier: data.confidenceTier)
                // #6343 — the same mark the hero futures card draws, on the same
                // rule (`discoverPriceAgeMark`). Four card views render a futures
                // card and wiring only one would leave the mark on the MINORITY of
                // the feed: in the read this shipped against, 11 of 16 datable
                // cards were `outcome_distribution` and the 60.2h PGA ladder — one
                // of the two genuinely stale specimens — was one of them.
                if let mark = data.discoverPriceAgeMark(
                    onReveal: { revealedPriceAge = revealedPriceAge == $0 ? nil : $0 }
                ) {
                    mark
                }
                // #4351: named, or not drawn — was `src.uppercased()`, which is
                // how this card printed `ODDS_API`.
                if let src = SourceLabels.label(for: data.source) {
                    Text(src)
                        .font(.system(size: 9, weight: .heavy))
                        .foregroundStyle(.blue)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(Color.blue.opacity(0.10), in: Capsule())
                }
            }
            .padding(.top, 12)

            // #6343 — the tap reveal, inline under the footer for the reason
            // `LiquidityMarkView` gives: a popover on a phone covers the number
            // the reader just asked about. Present on all four futures cards so
            // the affordance does not differ by card shape.
            if let revealedPriceAge {
                LiquidityRevealCaption(sentence: revealedPriceAge)
                    .padding(.top, 8)
            }
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
    private func outcomeRow(
        _ outcome: FeedDiscoverDistributionOutcome,
        rank: Int,
        isLeader: Bool
    ) -> some View {
        let probability = outcome.probability ?? 0
        let pct = Int((probability * 100).rounded())
        let barWidth = max(5, probability / maxProbability * 100)

        HStack(spacing: 8) {
            // Rank number
            Text("\(rank)")
                .font(.system(size: 12, weight: .semibold, design: .monospaced))
                .foregroundStyle(DS.textMuted)
                .frame(width: 20, alignment: .leading)

            // Name + bar
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 4) {
                    Text(outcome.label)
                        .font(.system(size: 13, weight: isLeader ? .bold : .semibold))
                        .foregroundStyle(DS.textPrimary)
                        .lineLimit(1)

                    if let movement = outcome.movement, abs(movement) >= 0.01 {
                        movementBadge(movement)
                    }
                }

                // Probability bar
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 999)
                            .fill(DS.border)
                        RoundedRectangle(cornerRadius: 999)
                            .fill(isLeader ? DS.emerald : DS.textMuted.opacity(0.35))
                            .frame(width: max(2, geo.size.width * barWidth / 100))
                    }
                }
                .frame(height: 6)
            }

            // Percentage
            Text(probability > 0 ? "\(pct)%" : "\u{2014}")
                .font(.system(size: 13, weight: .bold, design: .monospaced))
                .foregroundStyle(DS.textPrimary)
                .frame(width: 40, alignment: .trailing)
        }
        .padding(.vertical, 6)
    }

    // MARK: - Movement badge

    @ViewBuilder
    private func movementBadge(_ movement: Double) -> some View {
        let points = abs(movement * 100)
        let color = movement > 0 ? DS.kalshiGreen : DS.danger
        HStack(spacing: 2) {
            Image(systemName: movement > 0 ? "arrow.up.right" : "arrow.down.right")
                .font(.system(size: 7, weight: .bold))
            Text(String(format: "%.1f", points))
                .font(.system(size: 9, weight: .semibold, design: .monospaced))
        }
        .foregroundStyle(color)
        .padding(.horizontal, 4)
        .padding(.vertical, 2)
        .background(color.opacity(0.08), in: Capsule())
    }
}

// MARK: - Previews

#if DEBUG
#Preview("Distribution - 6 outcomes") {
    ScrollView {
        DistributionCardView(
            data: distributionPreviewData(
                name: "Who will win Best Picture at the 2027 Oscars?",
                category: "entertainment",
                outcomes: [
                    (label: "The Brutalist Part II", prob: 0.32, movement: 0.05),
                    (label: "Sinners", prob: 0.21, movement: -0.03),
                    (label: "Mickey 17", prob: 0.15, movement: nil),
                    (label: "A Complete Unknown", prob: 0.11, movement: 0.02),
                    (label: "Wicked: For Good", prob: 0.08, movement: nil),
                    (label: "The Amateur", prob: 0.05, movement: nil),
                ],
                remaining: 4
            ),
            navigationPath: .constant(NavigationPath())
        )
        .padding()
    }
    .background(Color.groupedBackground)
}

#Preview("Distribution - 4 outcomes") {
    ScrollView {
        DistributionCardView(
            data: distributionPreviewData(
                name: "Who will be the next Supreme Court Justice?",
                category: "politics",
                outcomes: [
                    (label: "J.D. Vance", prob: 0.40, movement: 0.12),
                    (label: "Ron DeSantis", prob: 0.25, movement: -0.05),
                    (label: "Ted Cruz", prob: 0.18, movement: nil),
                    (label: "Amy Coney Barrett", prob: 0.09, movement: nil),
                ],
                remaining: 0
            ),
            navigationPath: .constant(NavigationPath())
        )
        .padding()
    }
    .background(Color.groupedBackground)
}

private func distributionPreviewData(
    name: String,
    category: String,
    outcomes: [(label: String, prob: Double, movement: Double?)],
    remaining: Int
) -> FeedFuturesData {
    let distOutcomes = outcomes.map { o in
        FeedDiscoverDistributionOutcome(
            label: o.label,
            probability: o.prob,
            movement: o.movement
        )
    }
    return FeedFuturesData(
        id: 998,
        name: name,
        sport: nil,
        sportName: nil,
        llmSportCategory: category,
        source: "polymarket",
        sourceCount: 1,
        sources: ["polymarket"],
        marketTier: 2,
        status: "open",
        resolutionDate: "2027-03-15T00:00:00Z",
        topOutcomes: [],
        outcomeCount: outcomes.count + remaining,
        canonicalMarketKey: nil,
        groupId: nil,
        groupType: nil,
        imageUrl: nil,
        hookDescription: nil,
        matchedOutcomes: nil,
        discoverCard: FeedDiscoverCard(
            suggestedFormat: "outcome_distribution",
            bundleCandidate: false,
            comparisonTheme: nil,
            thresholdPoints: nil,
            distributionOutcomes: distOutcomes,
            remainingOutcomeCount: remaining,
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
        winnerOpeningProbability: nil,
        // #1885: a preview fixture belongs to no story family.
        storyKey: nil,
        priceObservedAt: nil,
        // #2088: a preview fixture makes no claim about a card total.
        cardSumReason: nil
    )
}
#endif
