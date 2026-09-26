import SwiftUI

// MARK: - Heatmap Cell Grid

/// Renders a threshold heatmap as a horizontal strip of 3-8 emerald-intensity cells.
/// Each cell represents a binary market threshold; probability drives the emerald
/// opacity ramp so you can read at a glance where belief crosses 50%.
struct HeatMapCardView: View {
    let data: FeedFuturesData
    @Binding var navigationPath: NavigationPath
    var onOpen: (() -> Void)? = nil

    /// #6343 — the price-age reveal, open or closed. See `PriceAgeMarkView`.
    @State private var revealedPriceAge: String?

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

    /// #4081 — a UTC-midnight `resolution_date` is a declared calendar date, not
    /// an instant; localising it drew the day before west of UTC.
    /// #8836 — a date ladder whose rungs run past the served date prints no line
    /// at all rather than one rung's close as the card's; see
    /// `heatMapDateLadderRunsPastResolution`. Internal so the guard reads the
    /// header the card draws, not only the helper it calls.
    var resolvesText: String? {
        if heatMapDateLadderRunsPastResolution(sortedPoints, resolutionDate: data.resolutionDate) { return nil }
        guard let text = CalendarDeadline.format(data.resolutionDate, style: .monthDay) else { return nil }
        return "Resolves \(text)"
    }

    private var lastAbove50Label: String? {
        // Derive from ALL thresholds (not the capped cells) so the crossover
        // summary stays correct even when cells overflow past maxCells.
        guard let rung = heatMapBetterThanEvenRung(sortedPoints) else { return nil }
        return compactThresholdLabel(rung.label)
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
                    // #4645 — the caption composes with the rung's own words
                    // instead of prefixing them. "Above 50% through" was written
                    // for the DATE ladder it shipped with, where the rung label
                    // is a date and the sentence closes ("Above 50% through
                    // Before 2027"). Every other ladder's label carries its own
                    // comparator, so the line stacked two of them on two
                    // unrelated quantities and stopped mid-sentence: the phone
                    // printed "Above 50% through ≥$6.40"
                    // (artifacts-native-091/before-ladder-s9000.png), the web
                    // twin "Above 50% through Above 67" (#4645). The thing worth
                    // saying is the same for both ladders — this is the furthest
                    // rung the market still calls better than even — and saying
                    // it this way needs no branch. Web says the same words
                    // (FuturesCard.tsx, PR #4656): one card family, notice 35.
                    // #8647 — which end of the ladder is "furthest" depends on
                    // the axis; `heatMapBetterThanEvenRung` says which.
                    Text("More likely than not:")
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
                // #4351: named, or not drawn.
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

// MARK: - The rung the caption names

/// #8647 — the rung "More likely than not:" names: the MOST SPECIFIC rung the
/// market still calls better than even. `points` is in ladder order (ascending
/// `value`), and which end of the over-even rungs that is depends on the axis.
/// On a comparator ladder ("Above 52 / Above 58 / Above 64") chances fall as the
/// rungs climb, so it is the last one. On a date ladder every rung is a
/// cumulative "before this date" question and chances RISE, so the last one is
/// the loosest: the phone captioned the Anthropic-IPO ladder (futures 8430022,
/// 6% by Nov 1, 56% by Dec 1 … 90% by Apr 1) "Before Apr 1, 2027". The earliest
/// rung over even is the answer. An exclusive date ladder ("Before 2027 / 2027 /
/// 2029 or later") has at most one rung over even, so it reads the same. Web
/// applies the same rule (FuturesCard.tsx, PR #8650): one card family, notice 35.
func heatMapBetterThanEvenRung(_ points: [FeedDiscoverThresholdPoint]) -> FeedDiscoverThresholdPoint? {
    let above = points.filter { ($0.probability ?? 0) >= 0.50 }
    let isDateLadder = !points.isEmpty && points.allSatisfy { $0.source == "date_bucket" }
    return isDateLadder ? above.first : above.last
}

// MARK: - The date the header may print

/// #8836 — does a date ladder carry a rung that runs past the date the card would
/// print as "Resolves <date>"?
///
/// Production, 2026-09-26 14:57Z: "Will the U.S. confirm that aliens exist?"
/// (futures 109435, Kalshi KXALIENS) headed its ladder "Resolves Jan 1, 2027" over
/// rungs running to "Before Jan 20, 2029". Kalshi closes each rung on its own date;
/// the served `resolution_date` is the "Before 2027" rung's close. The payload
/// carries no per-rung close, so the card cannot print the right date — it can only
/// stop printing the wrong one.
///
/// A date-bucket rung's `value` is YYYYMMDD (`_date_bucket_points`; month-only and
/// year-only rungs carry day 00, "Before 2028" is 20280100). A value outside that
/// shape is not read as a date and the card keeps its line. The two-day slack keeps
/// a rung the venue closes the evening before its label's date from counting as
/// later than itself. Reads EVERY rung, not only the five drawn cells: the "+N more"
/// footer names the rest, and a hidden 2029 rung makes a 2027 header just as wrong.
/// Web applies the same rule (FuturesCard.tsx `dateRungRunsPastResolution`,
/// PR #8844): one card family, notice 35.
func heatMapDateLadderRunsPastResolution(
    _ points: [FeedDiscoverThresholdPoint],
    resolutionDate: String?
) -> Bool {
    guard !points.isEmpty, points.allSatisfy({ $0.source == "date_bucket" }),
          let resolves = heatMapResolutionInstant(resolutionDate) else { return false }
    let values = points.compactMap(\.value)
    guard values.count == points.count, let latestValue = values.max(),
          latestValue.rounded() == latestValue, latestValue >= 19_000_000, latestValue <= 29_991_231
    else { return false }
    let latest = Int(latestValue)
    let month = (latest / 100) % 100
    guard month <= 12 else { return false }
    var cal = Calendar(identifier: .gregorian)
    cal.timeZone = TimeZone(identifier: "UTC")!
    guard let rungDate = cal.date(from: DateComponents(
        year: latest / 10_000, month: max(month, 1), day: max(latest % 100, 1)
    )) else { return false }
    return rungDate.timeIntervalSince(resolves) > 2 * 24 * 3600
}

/// The served `resolution_date` as an instant: a full timestamp as written, a bare
/// calendar date (`CalendarDeadline.declaredDay`) as its UTC midnight.
private func heatMapResolutionInstant(_ raw: String?) -> Date? {
    guard let raw else { return nil }
    if let date = raw.asDate { return date }
    guard let day = CalendarDeadline.declaredDay(raw) else { return nil }
    var cal = Calendar(identifier: .gregorian)
    cal.timeZone = TimeZone(identifier: "UTC")!
    return cal.date(from: DateComponents(year: day.year, month: day.month, day: day.day))
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
                name: "Dune: Part Three \u{2014} Rotten Tomatoes score",
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
