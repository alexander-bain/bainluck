import Charts
import SwiftUI

// MARK: - Main View

struct CalibrationView: View {
    @StateObject private var viewModel = CalibrationViewModel()
    @Environment(\.horizontalSizeClass) private var sizeClass

    private var contentMaxWidth: CGFloat {
        #if os(macOS)
        return 900
        #else
        return sizeClass == .regular ? 900 : .infinity
        #endif
    }

    var body: some View {
        Group {
            if viewModel.loading {
                ProgressView("Loading calibration data...")
            } else if let error = viewModel.error {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundStyle(.secondary)
                    Text(error).font(.subheadline).foregroundStyle(.secondary)
                    Button("Retry") { Task { await viewModel.load() } }.buttonStyle(.borderedProminent)
                }
            } else { scrollContent }
        }
        .navigationTitle("Calibration")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task { await viewModel.load() }
    }

    private var scrollContent: some View {
        ScrollView {
            VStack(spacing: 24) {
                heroSection; statCardsSection; cohortToggleBanner
                sourceComparisonSection; benchmarkSection
                calibrationChartSection; tradingActivitySection; categoryBreakdownSection
                nicheSection; correctionsSection
            }
            .padding(.horizontal).padding(.bottom, 32)
            .frame(maxWidth: contentMaxWidth)
            .frame(maxWidth: .infinity)
        }
    }

    // MARK: - Hero

    private var heroSection: some View {
        VStack(spacing: 6) {
            Text("Do Prediction Markets Predict Anything?").font(.title2.weight(.bold))
            Text("We compare \(viewModel.formattedTotalOutcomes) resolved predictions with what actually happened. A well-calibrated market saying 30% should happen about 30% of the time.")
                .font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
            Text("\(viewModel.dateRangeLabel.map { "Data \($0)" } ?? "\(viewModel.formattedTotalOutcomes) resolved outcomes") \u{00B7} Updated \(viewModel.updatedLabel)")
                .font(.caption2).foregroundStyle(.tertiary)
        }.padding(.top, 8)
    }

    // MARK: - Stat Cards

    private var statCardsSection: some View {
        VStack(spacing: 10) {
            eceHeroCard
            HStack(spacing: 10) {
                miniStatCard("OUTCOMES", viewModel.formattedCohortOutcomes, "checkmark.circle.fill", .blue)
                miniStatCard("MARKETS", viewModel.formattedMarkets, "chart.bar.fill", .purple)
                miniStatCard("BRIER", String(format: "%.3f", viewModel.cohortBrier), "target", .orange)
            }
        }
    }

    // ECE-first (#894): the n-weighted error is the headline — it reflects the
    // outcomes users actually see. MCE (equal-weighted, worst-bucket sensitive) is
    // demoted to a secondary line.
    private var eceHeroCard: some View {
        VStack(spacing: 4) {
            Text("CALIBRATION ERROR (ECE)")
                .font(.caption2.weight(.medium)).foregroundStyle(.secondary).tracking(0.5)
            HStack(alignment: .firstTextBaseline, spacing: 2) {
                Text(String(format: "%.1f", viewModel.cohortECE))
                    .font(.system(size: 44, weight: .bold, design: .monospaced))
                    .foregroundStyle(viewModel.eceColor(viewModel.cohortECE))
                Text("pp").font(.title3.weight(.medium)).foregroundStyle(.secondary)
            }
            Text("n-weighted \u{00B7} worst-bucket (MCE) \(String(format: "%.1f", viewModel.cohortMCE))pp")
                .font(.caption2).foregroundStyle(.tertiary)
            if let ciLo = viewModel.data?.mceCiLower, let ciHi = viewModel.data?.mceCiUpper {
                Text("95% CI: \(String(format: "%.1f", ciLo))\u{2013}\(String(format: "%.1f", ciHi))pp")
                    .font(.caption2).foregroundStyle(.tertiary)
            }
            Text(viewModel.eceQualityLabel).font(.caption2.weight(.medium)).foregroundStyle(viewModel.eceColor(viewModel.cohortECE))
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(viewModel.eceColor(viewModel.cohortECE).opacity(0.12), in: Capsule())
        }
        .frame(maxWidth: .infinity).padding(.vertical, 16)
        .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 14))
    }

    private func miniStatCard(_ label: String, _ value: String, _ icon: String, _ color: Color) -> some View {
        VStack(spacing: 6) {
            Image(systemName: icon).font(.caption).foregroundStyle(color)
            Text(value).font(.callout.weight(.bold).monospacedDigit())
            Text(label).font(.system(size: 9, weight: .medium)).foregroundStyle(.secondary).tracking(0.3)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 12)
        .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - Cohort toggle (well-traded default + include-thin)

    // L2-74 §C (#940): default to WELL-TRADED; a visible toggle layers in
    // thin/untraded markets. It never hides — both counts are always shown.
    private var cohortToggleBanner: some View {
        HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                if viewModel.includeThin {
                    Text("Showing all markets (\(viewModel.formattedCohortOutcomes))")
                        .font(.caption.weight(.medium)).foregroundStyle(.primary)
                    Text("Including thin / untraded.").font(.caption2).foregroundStyle(.secondary)
                } else {
                    Text("Showing well-traded markets (\(viewModel.formattedCohortOutcomes))")
                        .font(.caption.weight(.medium)).foregroundStyle(.primary)
                    Text("Where real trading moved the price. Thin markets can be noisy.")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 8)
            Button {
                viewModel.includeThin.toggle()
            } label: {
                Text(viewModel.includeThin
                     ? "Well-traded only"
                     : "Include thin (+\(fmtN(viewModel.thinAddN)))")
                    .font(.caption2.weight(.medium))
                    .padding(.horizontal, 12).padding(.vertical, 7)
                    .background(Color.systemGray5, in: Capsule())
            }
            .buttonStyle(.plain)
        }
        .padding(12)
        .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Calibration Chart

    private var calibrationChartSection: some View {
        cardSection(viewModel.includeThin ? "All-Markets Calibration Curve" : "Well-Traded Calibration Curve",
                    sub: "The diagonal line is perfect calibration. Points above it happened more often than predicted; points below it happened less often. Point size reflects sample count and thin buckets fade.") {
            calibrationChart(points: viewModel.points(from: viewModel.cohortBuckets), color: .blue, height: 300)
        }
    }

    private func calibrationChart(points: [CalibrationChartPoint], color: Color, height: CGFloat,
                                  secondSeries: (pts: [CalibrationChartPoint], color: Color)? = nil) -> some View {
        Chart {
            ForEach(0..<21, id: \.self) { i in
                let x = Double(i) * 5
                AreaMark(x: .value("P", x), yStart: .value("Lo", max(0, x - 5)), yEnd: .value("Hi", min(100, x + 5)))
                    .foregroundStyle(.blue.opacity(0.05))
            }
            LineMark(x: .value("X", 0), y: .value("Y", 0)).foregroundStyle(.gray.opacity(0.5)).lineStyle(StrokeStyle(lineWidth: 1, dash: [5, 5]))
            LineMark(x: .value("X", 100), y: .value("Y", 100)).foregroundStyle(.gray.opacity(0.5)).lineStyle(StrokeStyle(lineWidth: 1, dash: [5, 5]))

            ForEach(points) { p in
                LineMark(x: .value("P", p.predicted), y: .value("A", p.actual), series: .value("S", "primary"))
                    .foregroundStyle(color).lineStyle(StrokeStyle(lineWidth: 2.5))
                PointMark(x: .value("P", p.predicted), y: .value("A", p.actual))
                    .foregroundStyle(color.opacity(p.opacity)).symbolSize(p.size)
            }
            if let s2 = secondSeries {
                ForEach(s2.pts) { p in
                    LineMark(x: .value("P", p.predicted), y: .value("A", p.actual), series: .value("S", "secondary"))
                        .foregroundStyle(s2.color).lineStyle(StrokeStyle(lineWidth: 2))
                    PointMark(x: .value("P", p.predicted), y: .value("A", p.actual))
                        .foregroundStyle(s2.color.opacity(p.opacity)).symbolSize(p.size * 0.7)
                }
            }
        }
        .chartXScale(domain: 0...100).chartYScale(domain: 0...100)
        .chartXAxis { pctAxis([0, 25, 50, 75, 100]) }
        .chartYAxis { pctAxis([0, 25, 50, 75, 100]) }
        .frame(height: height)
    }

    private func pctAxis(_ values: [Int]) -> some AxisContent {
        AxisMarks(values: values) { value in
            AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5)).foregroundStyle(.gray.opacity(0.2))
            AxisValueLabel { Text("\(value.as(Int.self) ?? 0)%").font(.caption2.monospacedDigit()) }
        }
    }

    // MARK: - Source Comparison

    private var sourceComparisonSection: some View {
        cardSection("Source Comparison", sub: "How each data source performs independently, sorted by ECE (n-weighted, the headline metric). MCE is the worst-bucket sensitivity number. Lower is better.") {
            VStack(spacing: 0) {
                HStack(spacing: 0) {
                    Text("Source").frame(maxWidth: .infinity, alignment: .leading)
                    Text("N").frame(width: 54, alignment: .trailing)
                    Text("ECE").frame(width: 48, alignment: .trailing)
                    Text("MCE").frame(width: 46, alignment: .trailing)
                    Text("Brier").frame(width: 52, alignment: .trailing)
                }
                .font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                .padding(.horizontal, 12).padding(.vertical, 8)
                Divider()
                ForEach(viewModel.sourceRows) { row in
                    sourceRow(row)
                    if row.id != viewModel.sourceRows.last?.id { Divider().padding(.leading, 12) }
                }
                Divider()
                HStack(spacing: 0) {
                    Text("Combined").font(.caption.weight(.semibold)).frame(maxWidth: .infinity, alignment: .leading)
                    Text(viewModel.formattedCohortOutcomes).frame(width: 54, alignment: .trailing).monospacedDigit()
                    Text(String(format: "%.1f", viewModel.cohortECE)).frame(width: 48, alignment: .trailing)
                        .monospacedDigit().foregroundStyle(viewModel.eceColor(viewModel.cohortECE)).fontWeight(.semibold)
                    Text(String(format: "%.1f", viewModel.cohortMCE)).frame(width: 46, alignment: .trailing)
                        .monospacedDigit().foregroundStyle(.secondary)
                    Text(String(format: "%.3f", viewModel.cohortBrier)).frame(width: 52, alignment: .trailing).monospacedDigit()
                }
                .font(.caption).padding(.horizontal, 12).padding(.vertical, 10)
                .background(Color.systemGray5.opacity(0.5))
            }
            .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 10))
        }
    }

    private func sourceRow(_ row: CalSourceRow) -> some View {
        HStack(spacing: 0) {
            HStack(spacing: 6) {
                Circle().fill(sourceColor(row.source)).frame(width: 8, height: 8)
                Text(row.name).lineLimit(1)
            }.frame(maxWidth: .infinity, alignment: .leading)
            Text(fmtN(row.n)).frame(width: 54, alignment: .trailing).monospacedDigit()
            Text(String(format: "%.1f", row.ece)).frame(width: 48, alignment: .trailing)
                .monospacedDigit().foregroundStyle(viewModel.eceColor(row.ece)).fontWeight(.semibold)
            Text(String(format: "%.1f", row.mce)).frame(width: 46, alignment: .trailing)
                .monospacedDigit().foregroundStyle(.secondary)
            Text(String(format: "%.3f", row.brier)).frame(width: 52, alignment: .trailing).monospacedDigit()
        }
        .font(.caption).padding(.horizontal, 12).padding(.vertical, 10)
    }

    // MARK: - Trading Activity

    @ViewBuilder
    private var tradingActivitySection: some View {
        let movedN = viewModel.movedN, unchangedN = viewModel.unchangedN
        if movedN > 0 && unchangedN > 0 {
            let movedECE = viewModel.movedECE, unchangedECE = viewModel.unchangedECE
            cardSection("Does Trading Activity Matter?",
                        sub: "The calibration curve split by whether real trading moved the price. Markets that keep trading tend to be better calibrated than markets that stay stale at their opening price.") {
                calibrationChart(points: viewModel.points(from: viewModel.movedBuckets), color: .green, height: 220,
                                 secondSeries: (pts: viewModel.points(from: viewModel.unchangedBuckets), color: .red))
                HStack(spacing: 10) {
                    tradingCard("Active Trading", movedECE, movedN, .green)
                    tradingCard("Opening Price Only", unchangedECE, unchangedN, .red)
                }
                if movedECE > 0 && unchangedECE > 0 {
                    Text("Markets with active trading are \(String(format: "%.1f", unchangedECE / movedECE))x more accurately calibrated.")
                        .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center).frame(maxWidth: .infinity)
                }
            }
        }
    }

    private func tradingCard(_ label: String, _ ece: Double, _ count: Int, _ color: Color) -> some View {
        VStack(spacing: 4) {
            HStack(spacing: 4) { Circle().fill(color).frame(width: 8, height: 8); Text(label).font(.caption2.weight(.medium)) }
            Text(String(format: "%.1fpp", ece)).font(.callout.weight(.bold).monospacedDigit()).foregroundStyle(color)
            Text("\(fmtN(count)) outcomes").font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity).padding(.vertical, 10)
        .background(color.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - Category Breakdown

    private var categoryBreakdownSection: some View {
        cardSection("Category Breakdown",
                    sub: "Raw leagues are rolled up into product-level categories, sorted by ECE. Categories below \(fmtN(viewModel.minCategoryOutcomes)) resolved outcomes are held out — see below.") {
            if let best = viewModel.bestCategoryRow, let worst = viewModel.worstCategoryRow {
                HStack(spacing: 10) {
                    categorySummaryCard("Best calibrated", best, .green)
                    categorySummaryCard("Needs attention", worst, .orange)
                }
            }

            VStack(spacing: 0) {
                HStack {
                    Text("Category").frame(maxWidth: .infinity, alignment: .leading)
                    Text("Outcomes").frame(width: 72, alignment: .trailing)
                    Text("ECE").frame(width: 48, alignment: .trailing)
                    Text("MCE").frame(width: 46, alignment: .trailing)
                }
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)

                Divider()

                ForEach(Array(viewModel.topCategoryRows.enumerated()), id: \.element.id) { idx, row in
                    categoryMetricRow(row, color: Self.catColors[idx % Self.catColors.count])
                    if row.id != viewModel.topCategoryRows.last?.id { Divider().padding(.leading, 12) }
                }
            }
            .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 10))
        }
    }

    private func categorySummaryCard(_ label: String, _ row: CalCategoryRow, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(label)
                .font(.caption2.weight(.medium))
                .foregroundStyle(.secondary)
            Text(row.name)
                .font(.caption.weight(.semibold))
                .lineLimit(1)
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(String(format: "%.1fpp", row.ece))
                    .font(.callout.weight(.bold).monospacedDigit())
                    .foregroundStyle(color)
                Spacer()
                Text(fmtN(row.n))
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(color.opacity(0.07), in: RoundedRectangle(cornerRadius: 10))
    }

    private func categoryMetricRow(_ row: CalCategoryRow, color: Color) -> some View {
        HStack(spacing: 8) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(row.name)
                .font(.caption.weight(.medium))
                .lineLimit(1)
                .frame(maxWidth: .infinity, alignment: .leading)
            Text(fmtN(row.n))
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
                .frame(width: 72, alignment: .trailing)
            Text(String(format: "%.1f", row.ece))
                .font(.caption.weight(.semibold).monospacedDigit())
                .foregroundStyle(viewModel.eceColor(row.ece))
                .frame(width: 48, alignment: .trailing)
            Text(String(format: "%.1f", row.mce))
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
                .frame(width: 46, alignment: .trailing)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
    }

    // MARK: - Niche & Long-Shot (held-out categories)

    // Honest note (payload-driven from small_sample_categories): we don't publish a
    // curve for any category below the sample bar — under it, it's noise, not signal.
    @ViewBuilder
    private var nicheSection: some View {
        let thin = viewModel.smallSampleCategories
        if !thin.isEmpty {
            let examples = Array(thin.prefix(8))
            cardSection("What About Niche & Long-Shot Markets?",
                        sub: "A calibration curve is only honest with enough resolved outcomes behind it, so we don't publish one for any category below \(fmtN(viewModel.minCategoryOutcomes)) resolved outcomes. Right now \(thin.count) \(thin.count == 1 ? "category is" : "categories are") still accumulating (\(fmtN(viewModel.smallSampleTotal)) outcomes). The moment one crosses the bar it appears above automatically.") {
                FlowChips(chips: examples.map { "\(CalibrationViewModel.nicheDisplayName($0.category)) \(fmtN($0.outcomes))" })
                if thin.count > examples.count {
                    Text("+\(fmtN(thin.count - examples.count)) more")
                        .font(.caption2).foregroundStyle(.tertiary)
                }
            }
        }
    }

    // MARK: - Corrections (collapsed technical log)

    @ViewBuilder
    private var correctionsSection: some View {
        let rows = viewModel.corrections
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: 0) {
                DisclosureGroup {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(rows) { c in
                            VStack(alignment: .leading, spacing: 2) {
                                HStack(alignment: .firstTextBaseline, spacing: 8) {
                                    Text(c.date).font(.caption2.monospaced()).foregroundStyle(.tertiary)
                                    Text(c.title).font(.caption.weight(.medium))
                                    if let r = c.rows {
                                        Text("\(fmtN(r)) rows").font(.caption2).foregroundStyle(.tertiary)
                                    }
                                }
                                Text(c.description).font(.caption2).foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.vertical, 8)
                            if c.id != rows.last?.id { Divider() }
                        }
                    }
                    .padding(.top, 8)
                } label: {
                    HStack(spacing: 6) {
                        Text("Technical: data corrections log").font(.subheadline.weight(.semibold))
                        Text("(\(rows.count))").font(.caption2).foregroundStyle(.tertiary)
                    }
                }
            }
            .padding(16)
            .background(Color.systemGray6.opacity(0.5), in: RoundedRectangle(cornerRadius: 14))
        }
    }

    // MARK: - Benchmark

    private var benchmarkSection: some View {
        cardSection("How We Compare", sub: "Our aggregate error compared to published calibration benchmarks.") {
            VStack(spacing: 8) {
                benchmarkRow("Bain Luck", viewModel.cohortMCE, "\(viewModel.formattedCohortOutcomes) outcomes", true)
                benchmarkRow("Metaculus", 2.5, "Self-reported", false)
                benchmarkRow("Iowa Electronic Markets", 1.5, "Berg et al. 2008", false)
                benchmarkRow("Academic consensus", 3.5, "Arrow et al. 2008 (2\u{2013}5pp)", false)
            }
            Text("Lower is better. Most prediction markets achieve 2\u{2013}5pp MCE.")
                .font(.caption2).foregroundStyle(.tertiary)
        }
    }

    private func benchmarkRow(_ label: String, _ value: Double, _ detail: String, _ highlight: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label).font(.caption.weight(highlight ? .bold : .regular))
                    .foregroundStyle(highlight ? .primary : .secondary)
                Spacer()
                Text(String(format: "%.1fpp", value)).font(.caption.weight(.semibold).monospacedDigit())
                    .foregroundStyle(viewModel.eceColor(value))
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3).fill(Color.systemGray5).frame(height: 6)
                    RoundedRectangle(cornerRadius: 3)
                        .fill(highlight ? Color.blue : Color.gray.opacity(0.5))
                        .frame(width: min(geo.size.width, geo.size.width * value / 10), height: 6)
                }
            }.frame(height: 6)
            Text(detail).font(.system(size: 10)).foregroundStyle(.tertiary)
        }
    }

    // MARK: - Helpers

    private func cardSection<C: View>(_ title: String, sub: String, @ViewBuilder content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.headline)
            Text(sub).font(.caption).foregroundStyle(.secondary)
            content()
        }
        .padding(16)
        .background(Color.systemGray6.opacity(0.5), in: RoundedRectangle(cornerRadius: 14))
    }

    private static let catColors: [Color] = [
        .blue, .green, .red, .orange, .purple, .pink, .teal, .yellow, .indigo, .cyan,
        .mint, .brown, Color(hex: "059669"), Color(hex: "9333ea"), Color(hex: "c2410c"),
    ]

    private func sourceColor(_ source: String) -> Color {
        switch source {
        case "kalshi": return .green
        case "polymarket": return .purple
        case "odds_api": return .blue
        default: return .teal
        }
    }

    private func fmtN(_ n: Int) -> String {
        n >= 1000 ? String(format: "%.1fK", Double(n) / 1000) : "\(n)"
    }
}

// MARK: - Supporting Views & Models

/// Wrapping chip row (SwiftUI has no built-in flow layout target we depend on, so
/// this uses the Layout protocol for a simple left-to-right wrap).
private struct FlowChips: View {
    let chips: [String]

    var body: some View {
        FlowLayout(spacing: 6) {
            ForEach(Array(chips.enumerated()), id: \.offset) { _, chip in
                Text(chip)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(Color.systemGray6, in: Capsule())
            }
        }
    }
}

// FlowLayout lives in Utilities/FlowLayout.swift (single source of truth, gotcha #28).
// The FlowChips row above calls FlowLayout(spacing:6) explicitly, so the shared
// struct's default spacing is irrelevant here.

struct CalibrationChartPoint: Identifiable {
    let id = UUID()
    let predicted: Double, actual: Double, size: CGFloat
    let n: Int
    let opacity: Double
}
