import Charts
import SwiftUI

// MARK: - Main View

/// Owns the view model for the production navigation path. The surface itself
/// takes the model as an `@ObservedObject` so it can also be driven from a fixed
/// payload — see `CalibrationSurfaceView`.
struct CalibrationView: View {
    @StateObject private var viewModel = CalibrationViewModel()

    var body: some View { CalibrationSurfaceView(viewModel: viewModel) }
}

/// The calibration surface.
///
/// Split out from `CalibrationView` by L2-231 Item 2 so the rendered states can
/// be proven. The states this queue is about — dated last-good, population
/// version mismatch, empty payload — are states of the SERVER, so which one
/// appears in a live screenshot is whatever `/api/calibration` happens to be
/// serving. Taking the model as an `@ObservedObject` lets `ImageRenderer` drive
/// the real view from a fixed payload instead (the L2-225 pattern).
///
/// `@StateObject` cannot do that job: under `ImageRenderer` the injected
/// instance is not adopted and the view renders its default (loading) state, so
/// every fixture rasterised identically — which is how this split was found.
struct CalibrationSurfaceView: View {
    @ObservedObject var viewModel: CalibrationViewModel
    @Environment(\.horizontalSizeClass) private var sizeClass

    /// Whether the loaded content is wrapped in a `ScrollView`. Always true in
    /// the app.
    ///
    /// `ImageRenderer` proposes no scrollable height, so a `ScrollView` lays out
    /// to nothing and every payload rasterises to the same empty frame — which
    /// is not a rendering bug, just an un-renderable container. Dropping only
    /// the container keeps the render evidence on the REAL body, branches and
    /// all, instead of on a test-only copy of it.
    var scrolls: Bool = true

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
            } else if let unavailable = viewModel.unavailableMessage {
                // L2-231 Item 1: a payload that decoded but carries no curve. Every
                // metric here divides by a bucket count, so rendering it anyway
                // produces "0.0pp \u{2014} Excellent" — a confident claim assembled out
                // of no data. Say what happened instead.
                VStack(spacing: 12) {
                    Image(systemName: "chart.xyaxis.line")
                        .font(.largeTitle).foregroundStyle(.secondary)
                    Text(unavailable)
                        .font(.subheadline).foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Retry") { Task { await viewModel.load() } }.buttonStyle(.borderedProminent)
                }
                .padding(.horizontal, 24)
            } else if viewModel.isIncompatible {
                // L2-231 Item 2: a payload built under a population contract this
                // build does not know cannot be rendered under this build's labels
                // — that is how an older curve gets presented as the current one.
                // Refusing is the honest answer; a stale-looking number is not.
                VStack(spacing: 12) {
                    Image(systemName: "arrow.triangle.2.circlepath")
                        .font(.largeTitle).foregroundStyle(.secondary)
                    Text(viewModel.incompatibleMessage ?? "")
                        .font(.subheadline).foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Retry") { Task { await viewModel.load() } }.buttonStyle(.borderedProminent)
                }
                .padding(.horizontal, 24)
            } else { scrollContent }
        }
        .navigationTitle("Calibration")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task { await viewModel.loadIfNeeded() }
    }

    @ViewBuilder
    private var scrollContent: some View {
        if scrolls {
            ScrollView { loadedStack }
        } else {
            loadedStack
        }
    }

    private var loadedStack: some View {
        VStack(spacing: 24) {
            staleBanner; refreshFailureBanner; partialDataBanner
            heroSection; statCardsSection; cohortToggleBanner
            sourceComparisonSection; benchmarkSection
            calibrationChartSection; tradingActivitySection; categoryBreakdownSection
            nicheSection; correctionsSection
        }
        .padding(.horizontal).padding(.bottom, 32)
        .frame(maxWidth: contentMaxWidth)
        .frame(maxWidth: .infinity)
    }

    // MARK: - Stale banner

    // Queue 297 Item 1, ported to native by L2-231 Item 2. When the server is
    // serving a last-good snapshot rather than a current one, say so and date it.
    // A stale curve is fine; a stale curve presented as live is not — and native
    // had no decode for the freshness envelope at all, so it presented every
    // degraded payload as current.
    @ViewBuilder
    private var staleBanner: some View {
        if let detail = viewModel.staleBannerDetail {
            VStack(alignment: .leading, spacing: 3) {
                Text("Showing the last complete snapshot.")
                    .font(.caption.weight(.semibold)).foregroundStyle(.primary)
                Text(detail).font(.caption2).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 12))
        }
    }

    // L2-231 Item 1. A refresh that failed while good numbers are already on
    // screen used to replace the whole surface with an error page — discarding a
    // readable curve because one later poll timed out. The curve stays; this
    // says it is not current, and names when it was built.
    @ViewBuilder
    private var refreshFailureBanner: some View {
        if let note = viewModel.refreshFailureNote {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "arrow.clockwise.circle").font(.caption)
                Text(note).font(.caption2)
                Spacer(minLength: 8)
                Button("Retry") { Task { await viewModel.load() } }
                    .font(.caption2.weight(.medium)).buttonStyle(.plain)
            }
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 12))
        }
    }

    // L2-231 Item 1. Buckets the server sent that this build could not read. A
    // curve quietly built from fewer groups than the payload offered reads
    // exactly like a complete one, so the shortfall is stated.
    @ViewBuilder
    private var partialDataBanner: some View {
        if let note = viewModel.partialDataNote {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "exclamationmark.circle").font(.caption)
                Text(note).font(.caption2)
            }
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 12))
        }
    }

    // MARK: - Hero

    private var heroSection: some View {
        VStack(spacing: 6) {
            Text("Do Prediction Markets Predict Anything?").font(.title2.weight(.bold))
            // L2-231 Item 0 found this leading with total_outcomes while the web
            // hero leads with the COHORT count — two different numbers whenever
            // the default cohort is on, presented as the same claim on two
            // surfaces. It now names the same population the web page does, and
            // the same one the OUTCOMES card below it already showed. L2-237: the
            // clause is web's `heroClause`, so the qualifier is the predicate.
            Text("We compare \(viewModel.heroPopulationText) with what actually happened. A well-calibrated market saying 30% should happen about 30% of the time.")
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

    // MARK: - Cohort toggle (price-moved + sportsbook default; never-moved opt-in)

    // L2-74 §C (#940): default to `price_moved != false`; a visible toggle layers
    // the never-moved outcomes back in. It never hides — both counts are shown.
    private var cohortToggleBanner: some View {
        HStack(alignment: .center, spacing: 10) {
            // L2-231 Item 2 / L2-237: EVERY string here comes from the view model
            // so a label cannot drift from what it describes. The default cohort
            // is `price_moved != false`, which is NOT the same set as "where real
            // trading moved the price" and is not a liquidity cohort at all.
            VStack(alignment: .leading, spacing: 2) {
                Text(viewModel.cohortHeadline)
                    .font(.caption.weight(.medium)).foregroundStyle(.primary)
                Text(viewModel.cohortDetail)
                    .font(.caption2).foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            Button {
                viewModel.includeThin.toggle()
            } label: {
                Text(viewModel.cohortToggleLabel)
                    .font(.caption2.weight(.medium))
                    .padding(.horizontal, 12).padding(.vertical, 7)
                    .background(Color.systemGray5, in: Capsule())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(viewModel.cohortToggleAccessibilityLabel)
        }
        .padding(12)
        .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Calibration Chart

    private var calibrationChartSection: some View {
        // L2-237: the curve is named by the cohort it draws, from the same
        // property the banner above it uses — web's `shortLabel`, in the subtitle
        // where web puts it, so the two surfaces cannot drift apart.
        //
        // The name leads the SUBTITLE rather than the title on purpose. This
        // section's `Text`s truncate to one line at 390pt (the `Chart` sibling
        // carries no width constraint, so the stack sizes to the chart's ideal
        // width and the text is clipped rather than wrapped — pre-existing, and
        // why the old explainer was already cut at "perfect calibrati…"). A title
        // reading "Calibration Curve: Price moved + sport…" would be a truncated
        // claim; leading the subtitle puts the whole cohort name and its count
        // inside the visible width. The clip itself is a layout defect and is
        // out of this queue's gate — reported, not fixed.
        cardSection("Calibration Curve",
                    sub: "\(viewModel.cohortShortLabel) (\(viewModel.formattedCohortOutcomes) outcomes). The diagonal line is perfect calibration. Points above it happened more often than predicted; points below it happened less often. Point size reflects sample count, and small-sample buckets fade.") {
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
            let activity = viewModel.activity
            cardSection("Does Trading Activity Matter?",
                        sub: "The calibration curve split by whether real trading moved the price. The two cohorts differ in source, category and market-shape mix, so whichever side lands lower here is an observed ordering \u{2014} not evidence that trading caused it.") {
                calibrationChart(points: viewModel.points(from: viewModel.movedBuckets), color: .green, height: 220,
                                 secondSeries: (pts: viewModel.points(from: viewModel.unchangedBuckets), color: .red))
                // L2-230: the value colour is part of the claim. Hard-coding moved
                // green and unchanged red asserted "moved is better" in pixels even
                // on the day moved measured 1.7pp against unchanged's 1.0pp, so it
                // follows the same direction the sentence below does.
                HStack(spacing: 10) {
                    tradingCard("Active Trading", movedECE, movedN,
                                Self.cohortColor(isHigher: activity.direction == .movedHigher,
                                                 isLower: activity.direction == .unchangedHigher))
                    tradingCard("Opening Price Only", unchangedECE, unchangedN,
                                Self.cohortColor(isHigher: activity.direction == .unchangedHigher,
                                                 isLower: activity.direction == .movedHigher))
                }
                if let sentence = activity.sentence {
                    Text(sentence)
                        .font(.caption).foregroundStyle(.secondary).multilineTextAlignment(.center).frame(maxWidth: .infinity)
                }
                // L2-231 Item 2: `price_moved` is a tri-state. The two cards above
                // cover `true` and `false`; the `null` rows (sportsbook lines,
                // where the test does not apply) were named nowhere, so the two
                // counts silently fell short of the population the page claims.
                if let partition = viewModel.activityPartitionNote {
                    Text(partition)
                        .font(.caption2).foregroundStyle(.tertiary)
                        .multilineTextAlignment(.center).frame(maxWidth: .infinity)
                }
            }
        }
    }

    /// Orange for the higher-error cohort, green for the lower, neutral on a tie
    /// or when no honest ordering exists.
    private static func cohortColor(isHigher: Bool, isLower: Bool) -> Color {
        if isHigher { return .orange }
        if isLower { return .green }
        return .secondary
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
